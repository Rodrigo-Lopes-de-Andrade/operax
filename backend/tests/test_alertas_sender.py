"""O sender que entrega de verdade (C5, onda 1, metade A).

Oito portões, cada um com o falso verde que ele fecha:

1. **Gate aberto → zero escrita.** Afirmado pela lista de instruções: nenhum
   `update`/`insert` foi emitido — um "não reserva" que reservasse e desfizesse
   passaria pelo status final.
2. **Três fases, HTTP fora de transação** — pela linha do tempo compartilhada
   entre o escopo falso e o provedor: `tenant_scope:exit` antes do primeiro
   `enviar`, `tenant_scope:enter` depois do último.
3. **`Message` completo** — os cinco campos do template chegam ao provedor.
4. **O scrub do link** — só `telegram_invite`, só em `sent`/`discarded`; o
   alerta comum mantém o link do painel. O texto das três instruções aqui; a
   execução contra o gatilho de verdade é a sétima parte de
   `scripts/97_teste_canais.py`.
5. **`blocked` no Telegram** — revoga com a razão, audita sem `chat_id`, e
   re-roteia para WhatsApp (ou descarta nomeado). Um `blocked` numa linha de
   WhatsApp não chega perto disto.
6. **`sending` presa** — a cláusula na reserva, e a contagem no relatório.
7. **Token e destino em lugar nenhum do log**, sob `DEBUG`, com o provedor de
   verdade atrás de um `MockTransport` — e o positivo primeiro: um `AsyncClient`
   cru vaza a URL, e a URL é o token.
8. **`alert_sent` roteado** — canal e provedor da linha, não da regra.
"""

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from psycopg import errors
from psycopg.types.json import Jsonb

from operax.alertas import capacidades, sender
from operax.alertas.capacidades import TELEGRAM_CHANNEL, WHATSAPP_CHANNEL
from operax.alertas.provedores import PROVIDERS, fabrica, telegram
from operax.alertas.provedores.base import Delivery, Message, verification_client
from operax.core.tenant import SystemContext, bind_tenant
from server.routers import canais, webhooks
from tests.test_canais_credencial import BOT_TOKEN, Recorder, _reset_http_loggers

TENANT = UUID("dddddddd-0000-0000-0000-000000000001")
RULE = UUID("dddddddd-0000-0000-0000-0000000000a1")
CONTACT = UUID("dddddddd-0000-0000-0000-0000000000c1")
BOT_INTEGRATION = UUID("dddddddd-0000-0000-0000-0000000000d2")
WA_INTEGRATION = UUID("dddddddd-0000-0000-0000-0000000000d1")
IDENTITY = UUID("dddddddd-0000-0000-0000-0000000000e1")
PHONE = "+5511999999999"
CHAT_ID = "987654321012"
WA_PROVIDER = capacidades.WHATSAPP_PROVIDERS[0]
WA_TOKEN = "token-de-whatsapp-de-teste-nao-e-real"
CONTEXT = SystemContext(tenant_id=TENANT, task="teste")


def _template(**overrides: Any) -> dict[str, Any]:
    return {
        "variables": ["unit", "link"],
        "body": "FastPark: {{1}} — {{2}}",
        "language": "pt_BR",
        "meta_template_name": "fastpark_resumo",
        **overrides,
    }


def _fila(**overrides: Any) -> dict[str, Any]:
    """Uma linha como `_CLAIM_SQL` a devolve."""
    return {
        "id": uuid4(),
        "rule_id": RULE,
        "channel": WHATSAPP_CHANNEL,
        "destination": PHONE,
        "payload": {"unit": "Centro", "link": "https://app.x/dashboard?un=1"},
        "template_code": "deviation_summary",
        "provider": WA_PROVIDER,
        "attempts": 0,
        "previous_status": "pending",
        **overrides,
    }


def _telegram_row(**overrides: Any) -> dict[str, Any]:
    return _fila(channel=TELEGRAM_CHANNEL, destination=CHAT_ID, provider=telegram.NAME, **overrides)


def _integration(provider: str, id: UUID, **config: str) -> dict[str, Any]:
    return {"id": id, "provider": provider, "config": config}


# ---------------------------------------------------------------------------
# O banco falso: responde por instrução, guarda tudo por escopo, e anota a
# linha do tempo. Cada `tenant_scope` é uma transação: o que um escopo escreveu
# só entra no estado quando ele sai sem exceção — com exceção, some, como o
# `pool.connection()` do psycopg faz.
# ---------------------------------------------------------------------------
class _TriggerRefusal(errors.RaiseException):
    """O `P0001` do gatilho, com o `diag.message_primary` que o psycopg preenche.

    O `str()` leva `HINT:`/`CONTEXT:` de propósito, como o do psycopg: só a
    frase (`message_primary`) pode ir para `alert_sent.error`."""

    def __init__(self, message: str) -> None:
        super().__init__(f"{message}\nHINT: sonda de contexto\nCONTEXT: PL/pgSQL function")
        self._message = message

    @property
    def diag(self) -> Any:
        return SimpleNamespace(message_primary=self._message)


@dataclass
class FakeDB:
    promovido: bool = True
    liberado: bool = True
    fila: list[dict[str, Any]] = field(default_factory=list)
    templates: dict[str, dict[str, Any]] = field(default_factory=dict)
    integrations: list[dict[str, Any]] = field(default_factory=list)
    #: `(integration_id, chave)` → valor, como o cofre responderia.
    secrets: dict[tuple[UUID, str], str] = field(default_factory=dict)
    #: O titular por trás de um chat_id — `None` quando não há identidade.
    holder: dict[str, Any] | None = None
    #: Se a identidade do titular está vigente (o revoke devolve a linha).
    identity_current: bool = True
    whatsapp_provider: str | None = None
    contact_has_whatsapp: bool = True
    #: A frase com que o gatilho recusa `_REROUTE_SQL` — `None` aceita.
    reroute_refusal: str | None = None
    #: Erro do banco (não do gatilho) em `_REROUTE_SQL` — tem de propagar.
    reroute_outage: bool = False
    timeline: list[str] = field(default_factory=list)

    #: `(escopo, sql, params)` de TUDO que foi executado, comitado ou não.
    statements: list[tuple[int, str, dict[str, Any]]] = field(default_factory=list)
    scope_no: int = 0
    rolled_back: set[int] = field(default_factory=set)
    #: O estado COMITADO.
    status: dict[UUID, str] = field(default_factory=dict)
    due: dict[UUID, bool] = field(default_factory=dict)
    log: list[dict[str, Any]] = field(default_factory=list)
    marks: list[tuple[str, UUID]] = field(default_factory=list)
    revokes: list[dict[str, Any]] = field(default_factory=list)
    audits: list[dict[str, Any]] = field(default_factory=list)
    reroutes: list[dict[str, Any]] = field(default_factory=list)
    _buffer: list[Callable[[], None]] = field(default_factory=list)

    def __post_init__(self) -> None:
        for row in self.fila:
            self.status.setdefault(row["id"], row.get("previous_status", "pending"))
            self.due.setdefault(row["id"], True)

    def _write(self, apply: Callable[[], None]) -> None:
        self._buffer.append(apply)

    def commit(self) -> None:
        for apply in self._buffer:
            apply()
        self._buffer.clear()

    def rollback(self) -> None:
        self._buffer.clear()
        self.rolled_back.add(self.scope_no)

    def _eligible(self, row: dict[str, Any]) -> bool:
        # Linhas acrescentadas à `fila` depois da construção entram aqui.
        status = self.status.setdefault(row["id"], row.get("previous_status", "pending"))
        self.due.setdefault(row["id"], True)
        return status == "pending" or (status in ("failed", "sending") and self.due[row["id"]])

    def responder(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.statements.append((self.scope_no, sql, params))
        if "from app.detection_run" in sql:
            return [{"promovido": self.promovido, "liberado": self.liberado}]
        if "select count(*) as waiting" in sql:
            return [{"waiting": len(self.fila)}]
        if "set status = 'sending'" in sql:
            lote = [
                {**row, "previous_status": self.status[row["id"]]}
                for row in self.fila
                if self._eligible(row)
            ]
            for row in lote:
                self._write(lambda i=row["id"]: self.status.__setitem__(i, "sending"))
            return lote
        if "from app.message_template" in sql:
            t = self.templates.get(params["code"])
            return [t] if t else []
        if "select provider from app.integration" in sql:
            return [{"provider": self.whatsapp_provider}] if self.whatsapp_provider else []
        if "provider = any(%(providers)s)" in sql:
            return list(self.integrations)
        if "vault.decrypted_secrets" in sql:
            value = self.secrets.get((params["integration_id"], params["key"]))
            return [{"decrypted_secret": value}] if value is not None else []
        if "insert into app.alert_sent" in sql:
            self._write(lambda p=dict(params): self.log.append(p))
            return []
        if "set status = 'sent'" in sql:
            self._mark("sent", params["queue_id"], due=False)
            return []
        if "then 'discarded' else 'failed'" in sql:
            final = "discarded" if params["max_attempts"] <= 1 else "failed"
            self._mark(final, params["queue_id"], due=False)
            return [{"status": final}]
        if "set status = 'failed', attempts = attempts + 1" in sql:
            self._mark("parked", params["queue_id"], status="failed", due=True)
            return []
        if "from app.messaging_identity" in sql and "external_id" in sql:
            return [self.holder] if self.holder else []
        if "update app.messaging_identity" in sql:
            self._write(lambda p=dict(params): self.revokes.append(p))
            return [{"id": IDENTITY}] if self.identity_current else []
        if "insert into app.audit_log" in sql:
            self._write(lambda p=dict(params): self.audits.append(p))
            return []
        if "from app.contact c" in sql and "set channel" in sql:
            if self.reroute_refusal is not None:
                raise _TriggerRefusal(self.reroute_refusal)
            if self.reroute_outage:
                raise errors.OperationalError("connection lost")
            self._write(lambda p=dict(params): self.reroutes.append(p))
            if self.contact_has_whatsapp:
                self._mark("rerouted", params["queue_id"], status="failed", due=True)
                return [{"id": params["queue_id"]}]
            return []
        if "set status = 'discarded'" in sql:
            self._mark("discarded", params["queue_id"], due=False)
            return []
        raise AssertionError(f"instrução inesperada: {sql[:70]}")

    def _mark(self, label: str, queue_id: UUID, *, status: str | None = None, due: bool) -> None:
        def apply() -> None:
            self.marks.append((label, queue_id))
            self.status[queue_id] = status or label
            self.due[queue_id] = due

        self._write(apply)

    def writes(self) -> list[str]:
        return [
            sql for _, sql, _ in self.statements if sql.lower().startswith(("update", "insert"))
        ]

    def in_scope(self, n: int) -> list[str]:
        return [sql[:40] for scope, sql, _ in self.statements if scope == n]


class FakeCursor:
    def __init__(self, estado: FakeDB, context: Any) -> None:
        self.estado = estado
        self.context = context
        self.linhas: list[dict[str, Any]] = []

    async def execute(self, statement: str, params: Any = None) -> None:
        bound = bind_tenant(statement, params or {}, self.context)
        self.linhas = self.estado.responder(" ".join(statement.split()), bound)

    async def fetchone(self) -> dict[str, Any] | None:
        return self.linhas[0] if self.linhas else None

    async def fetchall(self) -> list[dict[str, Any]]:
        return self.linhas


class FakeScope:
    def __init__(self, cursor: FakeCursor, estado: FakeDB) -> None:
        self.cursor = cursor
        self.estado = estado

    async def __aenter__(self) -> FakeCursor:
        self.estado.scope_no += 1
        self.estado.timeline.append("tenant_scope:enter")
        return self.cursor

    async def __aexit__(self, exc_type: type[BaseException] | None, *exc: object) -> None:
        self.estado.timeline.append("tenant_scope:exit")
        if exc_type is None:
            self.estado.commit()
        else:
            self.estado.rollback()
        return None


@dataclass
class SpyProvider:
    """Um provedor construído pela fábrica estubada: anota e responde o combinado."""

    name: str
    timeline: list[str]
    answer: Callable[[Message], Delivery]
    sent: list[Message] = field(default_factory=list)

    async def enviar(self, message: Message) -> Delivery:
        self.timeline.append(f"enviar:{self.name}")
        self.sent.append(message)
        return self.answer(message)


@dataclass
class Built:
    """O que a fábrica estubada recebeu e devolveu."""

    calls: list[dict[str, Any]] = field(default_factory=list)
    providers: dict[str, SpyProvider] = field(default_factory=dict)


def _ok(message: Message) -> Delivery:
    return Delivery(status="sent", provider_message_id="msg-1", cost_cents=4)


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Callable[..., tuple[FakeDB, Built]]:
    """Instala o escopo falso e a fábrica estubada; devolve os dois registros."""

    def install(
        estado: FakeDB, *, answers: dict[str, Callable[[Message], Delivery]] | None = None
    ) -> tuple[FakeDB, Built]:
        built = Built()
        answers = answers or {}

        def build(provider: str, *, config: Any, secrets: Any, http: Any) -> SpyProvider:
            built.calls.append(
                {
                    "provider": provider,
                    "config": dict(config),
                    "secrets": dict(secrets),
                    "http": http,
                }
            )
            spy = SpyProvider(provider, estado.timeline, answers.get(provider, _ok))
            built.providers[provider] = spy
            return spy

        monkeypatch.setattr(fabrica, "build", build)
        monkeypatch.setattr(
            sender,
            "tenant_scope",
            lambda context, schema="app": FakeScope(FakeCursor(estado, context), estado),
        )
        return estado, built

    return install


async def _dispatch(estado: FakeDB, **kwargs: Any) -> sender.SendResult:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500))
    ) as http:
        return await sender.dispatch(CONTEXT, http, **kwargs)


def _bot_ready(estado: FakeDB) -> FakeDB:
    estado.integrations.append(_integration(telegram.NAME, BOT_INTEGRATION, public_identity="@Bot"))
    estado.secrets[(BOT_INTEGRATION, "bot_token")] = BOT_TOKEN
    return estado


def _whatsapp_ready(estado: FakeDB) -> FakeDB:
    # O `config` como `save_credential` o grava: todo campo não-secreto do `FIELDS`.
    config = {s.name: "1" for s in PROVIDERS[WA_PROVIDER].FIELDS if not s.secret}
    estado.integrations.append(_integration(WA_PROVIDER, WA_INTEGRATION, **config))
    for key in sender._secret_keys(WA_PROVIDER):
        estado.secrets[(WA_INTEGRATION, key)] = WA_TOKEN
    estado.whatsapp_provider = WA_PROVIDER
    return estado


# ---------------------------------------------------------------------------
# 1. Gate aberto: zero escrita, `waiting` contado
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("promovido", "liberado", "motivo"),
    [
        (False, True, "nunca rodou em produção"),
        (True, False, "nunca foi liberada"),
        (False, False, "nunca rodou em produção"),
    ],
)
async def test_com_o_gate_aberto_nada_e_reservado_nem_escrito(
    db: Callable[..., tuple[FakeDB, Built]], promovido: bool, liberado: bool, motivo: str
) -> None:
    estado, built = db(
        _whatsapp_ready(
            FakeDB(promovido=promovido, liberado=liberado, fila=[_fila(), _fila(), _fila()])
        )
    )

    resultado = await _dispatch(estado)

    assert resultado.gate_open is True and resultado.claimed == 0 and resultado.sent == 0
    assert resultado.waiting == 3
    assert motivo in (resultado.gate_reason or "")
    # ⛔ Pela lista de instruções: NENHUM update ou insert foi emitido — nem a
    #    reserva, nem o log. Um "não reserva" que reservasse e desfizesse
    #    passaria pelo status final; não passa por aqui.
    assert estado.writes() == []
    assert [sql[:30] for _, sql, _ in estado.statements] == [
        "select exists ( select 1 from ",
        "select count(*) as waiting fro",
    ]
    assert built.calls == [] and "enviar" not in "".join(estado.timeline)
    assert f"{resultado.waiting} mensagem(ns) esperando" in sender.relatorio([resultado])
    assert "nenhuma reservada" in sender.relatorio([resultado])


def test_a_contagem_de_espera_e_a_mesma_elegibilidade_da_reserva() -> None:
    for clausula in (
        "status in ('pending', 'failed')",
        "next_attempt_at <= now()",
        "scheduled_for <= now()",
    ):
        assert clausula in sender._WAITING_SQL
        assert clausula in sender._CLAIM_SQL
    assert sender._WAITING_SQL.lower().lstrip().startswith("select")


# ---------------------------------------------------------------------------
# 2. Três fases: HTTP fora de transação
# ---------------------------------------------------------------------------
async def test_o_http_acontece_entre_as_duas_transacoes(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    estado, built = db(
        _bot_ready(
            _whatsapp_ready(
                FakeDB(
                    fila=[_fila(), _telegram_row()],
                    templates={"deviation_summary": _template()},
                )
            )
        )
    )

    resultado = await _dispatch(estado)

    assert (resultado.sent, resultado.failed) == (2, 0)
    assert estado.timeline == [
        "tenant_scope:enter",
        "tenant_scope:exit",
        f"enviar:{WA_PROVIDER}",
        f"enviar:{telegram.NAME}",
        "tenant_scope:enter",
        "tenant_scope:exit",
    ]
    # E a fábrica recebeu o que o contrato diz: config da integração, os
    # segredos pelo nome do campo, e o `http` do chamador.
    assert sorted(c["provider"] for c in built.calls) == sorted([WA_PROVIDER, telegram.NAME])
    bot = next(c for c in built.calls if c["provider"] == telegram.NAME)
    assert bot["config"] == {"public_identity": "@Bot"}
    assert bot["secrets"] == {"bot_token": BOT_TOKEN}
    assert isinstance(bot["http"], httpx.AsyncClient)


async def test_sem_linha_na_fila_nao_ha_segunda_transacao_nem_fabrica(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    estado, built = db(_whatsapp_ready(FakeDB(fila=[])))

    resultado = await _dispatch(estado)

    assert resultado == sender.SendResult(tenant_id=TENANT, gate_open=False)
    assert estado.timeline == ["tenant_scope:enter", "tenant_scope:exit"]
    assert built.calls == []
    # A reserva rodou (é um update) e devolveu nada; o cofre não foi lido.
    assert not any("vault" in sql for _, sql, _ in estado.statements)


async def test_o_segredo_e_lido_na_fase_a_e_a_fabrica_recebe_na_b(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    """Uma leitura de cofre por chave declarada em `FieldSpec.secret`, dentro da
    primeira transação; a fábrica só é chamada depois de ela fechar."""
    estado, built = db(
        _bot_ready(FakeDB(fila=[_telegram_row()], templates={"deviation_summary": _template()}))
    )

    await _dispatch(estado)

    leituras = [p for _, sql, p in estado.statements if "vault.decrypted_secrets" in sql]
    assert [(p["integration_id"], p["key"]) for p in leituras] == [(BOT_INTEGRATION, "bot_token")]
    assert estado.timeline.index("tenant_scope:exit") < estado.timeline.index(
        f"enviar:{telegram.NAME}"
    )
    assert built.calls[0]["secrets"] == {"bot_token": BOT_TOKEN}


@pytest.mark.parametrize("provider", capacidades.CHANNEL_PROVIDERS)
def test_a_chave_do_cofre_e_o_nome_do_campo_secreto(provider: str) -> None:
    assert sender._secret_keys(provider) == [s.name for s in PROVIDERS[provider].FIELDS if s.secret]
    assert sender._secret_keys(provider)


async def test_provedor_sem_credencial_no_cofre_falha_nomeado_e_nao_e_construido(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    estado = FakeDB(fila=[_telegram_row()], templates={"deviation_summary": _template()})
    estado.integrations.append(_integration(telegram.NAME, BOT_INTEGRATION))  # sem segredo
    estado, built = db(estado)

    resultado = await _dispatch(estado)

    assert (resultado.failed, resultado.sent) == (1, 0)
    assert built.calls == []
    assert "sem credencial completa: bot_token" in estado.log[0]["error"]
    assert estado.marks == [("failed", estado.fila[0]["id"])]


async def test_integracao_sem_campo_no_config_falha_nomeada_em_vez_de_keyerror(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    """A fábrica da metade B recusa com `KeyError(campo)` o campo que falta do
    lado que `FieldSpec.secret` nomeia; o sender pergunta antes, pelos mesmos
    `FIELDS`, e a linha volta para a fila com o nome do campo — nunca o valor."""
    estado = FakeDB(fila=[_fila()], templates={"deviation_summary": _template()})
    estado.integrations.append(_integration(WA_PROVIDER, WA_INTEGRATION))  # config vazio
    for key in sender._secret_keys(WA_PROVIDER):
        estado.secrets[(WA_INTEGRATION, key)] = WA_TOKEN
    estado, built = db(estado)

    resultado = await _dispatch(estado)

    faltando = [s.name for s in PROVIDERS[WA_PROVIDER].FIELDS if not s.secret]
    assert resultado.failed == 1 and built.calls == []
    assert estado.log[0]["error"] == (
        f"provedor {WA_PROVIDER!r} sem credencial completa: {', '.join(faltando)}"
    )
    assert WA_TOKEN not in estado.log[0]["error"]


async def test_provedor_sem_integracao_ativa_volta_para_a_fila_com_o_motivo(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    estado, _ = db(FakeDB(fila=[_fila(provider=WA_PROVIDER), _fila(provider="smtp")]))

    resultado = await _dispatch(estado)

    assert resultado.failed == 2
    assert all("não configurado" in linha["error"] for linha in estado.log)
    assert [m[0] for m in estado.marks] == ["failed", "failed"]


async def test_a_fabrica_e_chamada_uma_vez_por_integracao_nao_por_linha(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    estado, built = db(
        _whatsapp_ready(
            FakeDB(fila=[_fila(), _fila(), _fila()], templates={"deviation_summary": _template()})
        )
    )

    await _dispatch(estado)

    assert len(built.calls) == 1
    assert len(built.providers[WA_PROVIDER].sent) == 3


def test_a_fabrica_tem_a_assinatura_do_contrato() -> None:
    """O que a metade B entrega e o que esta metade chama: a mesma forma."""
    assinatura = inspect.signature(fabrica.build)
    assert list(assinatura.parameters) == ["provider", "config", "secrets", "http"]
    for nome in ("config", "secrets", "http"):
        assert assinatura.parameters[nome].kind is inspect.Parameter.KEYWORD_ONLY


# ---------------------------------------------------------------------------
# 3. `Message` completo
# ---------------------------------------------------------------------------
async def test_o_message_leva_os_cinco_campos_do_template_e_os_fatos(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    estado, built = db(
        _whatsapp_ready(
            FakeDB(
                fila=[_fila()],
                templates={
                    "deviation_summary": _template(
                        language="en_US", meta_template_name="fp_summary"
                    )
                },
            )
        )
    )

    await _dispatch(estado)

    (mensagem,) = built.providers[WA_PROVIDER].sent
    assert mensagem == Message(
        destination=PHONE,
        template="deviation_summary",
        variables=("unit", "link"),
        facts={"unit": "Centro", "link": "https://app.x/dashboard?un=1"},
        body="FastPark: {{1}} — {{2}}",
        language="en_US",
        provider_template="fp_summary",
    )
    assert mensagem.ordered() == ["Centro", "https://app.x/dashboard?un=1"]


async def test_sem_template_o_message_vai_sem_corpo(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    estado, built = db(_whatsapp_ready(FakeDB(fila=[_fila(template_code=None)])))

    await _dispatch(estado)

    (mensagem,) = built.providers[WA_PROVIDER].sent
    assert (mensagem.template, mensagem.variables, mensagem.body) == (None, (), None)
    assert mensagem.provider_template is None


def test_o_template_e_lido_com_os_quatro_campos() -> None:
    for coluna in ("variables", "body", "language", "meta_template_name"):
        assert coluna in sender._TEMPLATE_SQL
    # Só o template ATIVO: um desativado entre a fila e o envio não renderiza.
    assert "and active" in " ".join(sender._TEMPLATE_SQL.split())


def test_so_a_integracao_ativa_e_carregada_e_so_as_de_canal() -> None:
    """Uma integração desligada pelo administrador não tem o segredo lido nem o
    provedor construído; e `secullum` (ativa em produção) não é de canal."""
    sql = " ".join(sender._INTEGRATIONS_SQL.split())
    assert "where tenant_id = %(tenant_id)s and active and provider = any(%(providers)s)" in sql


def test_o_batch_nao_representa_os_segredos() -> None:
    lote = sender._Batch(
        rows=[], templates={}, integrations=[], secrets={telegram.NAME: {"bot_token": BOT_TOKEN}}
    )
    assert BOT_TOKEN not in repr(lote) and "secrets" not in repr(lote)


# ---------------------------------------------------------------------------
# 4. O scrub do link
# ---------------------------------------------------------------------------
def test_o_link_do_convite_some_em_sent_e_discarded_e_so_nele() -> None:
    codigo = canais._INVITE_TEMPLATE_CODE
    scrub = f"template_code = '{codigo}'"
    for sql in (sender._MARK_SENT_SQL, sender._MARK_FAILED_SQL, sender._DISCARD_SQL):
        assert scrub in sql and "payload - 'link'" in sql
        # O `case` guarda o scrub: sem a condição, `payload` fica como está.
        assert "else payload end" in sql
    # Na falha, o scrub é SÓ no ramo que descarta — a linha que volta para a
    # fila ainda precisa do link para a próxima tentativa.
    falha = sender._MARK_FAILED_SQL
    assert "attempts + 1 >= %(max_attempts)s and template_code" in " ".join(falha.split())
    # E nenhuma outra instrução mexe no payload.
    for sql in (sender._CLAIM_SQL, sender._REROUTE_SQL, sender._LOG_SQL):
        assert "payload -" not in sql and "payload =" not in sql


def test_o_gatilho_deixa_a_linha_terminal_passar(
    last_migration_with: Callable[[str], str],
) -> None:
    """A migration `ch_queue_telegram` abre a validação para `sent`/`discarded`
    — sem isso o scrub é recusado ("Payload não cobre … link"), medido antes."""
    fonte = last_migration_with("validate_alert_template")
    assert "ch_queue_telegram" in fonte or "new.status in ('sent', 'discarded')" in fonte
    assert "tg_op = 'UPDATE' and new.status in ('sent', 'discarded')" in fonte
    assert "alert_queue_channel_check" in fonte and "'telegram'" in fonte


# ---------------------------------------------------------------------------
# 5. A degradação do Telegram: `blocked`, credencial morta, último backoff
# ---------------------------------------------------------------------------
def _blocked(message: Message) -> Delivery:
    return Delivery(status="failed", error="blocked")


def _falha(codigo: str) -> Callable[[Message], Delivery]:
    def answer(message: Message) -> Delivery:
        return Delivery(status="failed", error=codigo)

    return answer


def _degradavel(**overrides: Any) -> FakeDB:
    """Um tenant com bot e WhatsApp, uma linha de Telegram e o titular dela."""
    return _whatsapp_ready(
        _bot_ready(
            FakeDB(
                fila=[_telegram_row(**overrides)],
                templates={"deviation_summary": _template()},
                holder={"contact_id": CONTACT, "employee_id": None},
            )
        )
    )


async def test_blocked_revoga_audita_sem_chat_id_e_reroteia_para_whatsapp(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    estado, _ = db(_degradavel(), answers={telegram.NAME: _blocked})

    resultado = await _dispatch(estado)

    assert (resultado.failed, resultado.discarded, resultado.sent) == (1, 0, 0)
    # A revogação é a instrução do webhook, com a razão e o titular.
    (revoke,) = estado.revokes
    assert revoke == {
        "tenant_id": TENANT,
        "channel": TELEGRAM_CHANNEL,
        "reason": sender.BLOCKED_REASON,
        "contact_id": CONTACT,
        "employee_id": None,
    }
    assert any(
        sql == " ".join(webhooks._REVOKE_PREVIOUS_SQL.split()) for _, sql, _ in estado.statements
    )
    # A auditoria nomeia a identidade e a razão — e não o chat_id.
    (audit,) = estado.audits
    assert audit["entity_id"] == str(IDENTITY)
    assert json.loads(json.dumps(audit["depois"].obj)) == {
        "channel": TELEGRAM_CHANNEL,
        "reason": sender.BLOCKED_REASON,
    }
    assert isinstance(audit["depois"], Jsonb)
    # O re-roteamento: a mesma linha, WhatsApp, provedor ativo, o contato — o
    # número vem do banco (`c.whatsapp`), não daqui.
    (reroute,) = estado.reroutes
    assert reroute == {
        "tenant_id": TENANT,
        "queue_id": estado.fila[0]["id"],
        "contact_id": CONTACT,
        "channel": WHATSAPP_CHANNEL,
        "provider": WA_PROVIDER,
    }
    # (c1) estacionou a linha; (c2) a re-roteou. Nada ficou `sending`.
    assert estado.marks == [("parked", estado.fila[0]["id"]), ("rerouted", estado.fila[0]["id"])]
    assert estado.status[estado.fila[0]["id"]] == "failed" and estado.due[estado.fila[0]["id"]]
    # E o log registra a tentativa de Telegram como falha nomeada — uma linha só.
    (linha,) = estado.log
    assert (linha["channel"], linha["provider"], linha["status"], linha["error"]) == (
        TELEGRAM_CHANNEL,
        telegram.NAME,
        "failed",
        "blocked",
    )


async def test_a_degradacao_roda_em_tres_transacoes_proprias_depois_da_c1(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    """Escopo 1: fase (a). Escopo 2: (c1), log + marca de TODAS as linhas.
    Escopos 3, 4: a degradação — titular + revogação, depois a re-rota. Cada
    um comitado sozinho: é o que impede a recusa de um derrubar os outros."""
    estado = _degradavel()
    estado.fila.append(_fila())  # uma de WhatsApp no mesmo lote, entregue
    estado, _ = db(estado, answers={telegram.NAME: _blocked})

    await _dispatch(estado)

    # A ordem inteira, não a contagem: (c2) aninhada dentro de (c1) daria os
    # mesmos quatro escopos — e, no banco real, a re-rota esperaria para
    # sempre pela linha que o `_PARK_SQL` deixou travada na transação aberta.
    assert estado.timeline == [
        "tenant_scope:enter",
        "tenant_scope:exit",
        f"enviar:{telegram.NAME}",
        f"enviar:{WA_PROVIDER}",
        "tenant_scope:enter",
        "tenant_scope:exit",
        "tenant_scope:enter",
        "tenant_scope:exit",
        "tenant_scope:enter",
        "tenant_scope:exit",
    ]
    c1, holder, reroute = estado.in_scope(2), estado.in_scope(3), estado.in_scope(4)
    assert [sql[:22] for sql in c1] == [
        "insert into app.alert_",
        "update app.alert_queue",  # parked
        "insert into app.alert_",
        "update app.alert_queue",  # sent
    ]
    assert [sql[:32] for sql in holder] == [
        "select contact_id, employee_id f",
        "update app.messaging_identity se",
        "insert into app.audit_log (tenan",
    ]
    assert [sql[:24] for sql in reroute] == [
        "select provider from app",
        "update app.alert_queue q",
    ]
    assert estado.rolled_back == set()


async def test_a_re_rota_recusada_pelo_gatilho_descarta_so_aquela_linha(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    """O ALTO do ciclo 1: o gatilho recusa `_REROUTE_SQL` (meta_cloud com
    template não aprovado). As outras linhas do lote mantêm log e marca, a
    recusada vira `discarded` com o motivo, a revogação sobrevive, nada fica
    `sending`, e uma segunda chamada não entrega nada de novo."""
    estado = _degradavel()
    entregues = [_fila(), _fila(), _fila(), _fila()]
    estado.fila.extend(entregues)
    estado.reroute_refusal = "Template deviation_summary está draft e o provedor é meta_cloud."
    estado, built = db(estado, answers={telegram.NAME: _blocked})

    resultado = await _dispatch(estado)

    assert (resultado.sent, resultado.failed, resultado.discarded) == (4, 0, 1)
    # As quatro entregues: log e marca comitados em (c1), intocados pela recusa.
    for row in entregues:
        assert ("sent", row["id"]) in estado.marks and estado.status[row["id"]] == "sent"
    assert [linha["status"] for linha in estado.log[:5]] == [
        "failed",
        "sent",
        "sent",
        "sent",
        "sent",
    ]
    # A recusada: estacionada em (c1), revogada no escopo 3 (comitado), a
    # re-rota do escopo 4 desfeita, descartada no escopo 5.
    telegram_id = estado.fila[0]["id"]
    assert estado.rolled_back == {4}
    assert estado.reroutes == []
    assert len(estado.revokes) == 1 and len(estado.audits) == 1
    assert [m for m in estado.marks if m[1] == telegram_id] == [
        ("parked", telegram_id),
        ("discarded", telegram_id),
    ]
    assert estado.status[telegram_id] == "discarded"
    assert "sending" not in estado.status.values()
    # O motivo fica no log, como segunda linha da mesma fila — pelo canal que
    # recusou — e é a frase do gatilho, sem payload.
    recusa = estado.log[-1]
    assert (recusa["queue_id"], recusa["channel"], recusa["provider"], recusa["status"]) == (
        telegram_id,
        WHATSAPP_CHANNEL,
        WA_PROVIDER,
        "failed",
    )
    frase = "Template deviation_summary está draft e o provedor é meta_cloud."
    assert recusa["error"] == f"{sender.REROUTE_REFUSED}: {frase}"
    assert "link" not in recusa["error"] and CHAT_ID not in json.dumps(estado.log, default=str)
    # E a segunda chamada: a fila está terminal, nenhum `enviar` de novo.
    enviados = len(estado.timeline)
    segunda = await _dispatch(estado)
    assert segunda == sender.SendResult(tenant_id=TENANT, gate_open=False)
    assert "enviar" not in "".join(estado.timeline[enviados:])
    assert sum(len(spy.sent) for spy in built.providers.values()) == 5


async def test_um_erro_do_banco_na_re_rota_propaga_e_nao_vira_descarte(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    """Só a recusa do gatilho (`RaiseException`) vira `discarded`. Um erro
    transitório do banco em (c2) tem de PROPAGAR: a linha fica `failed` e
    devida, a próxima execução tenta de novo. Um `except` largo aqui seria
    perda de mensagem silenciosa — o descarte é terminal."""
    estado = _degradavel()
    estado.fila.append(_fila())
    estado.reroute_outage = True
    estado, _ = db(estado, answers={telegram.NAME: _blocked})

    with pytest.raises(errors.OperationalError):
        await _dispatch(estado)

    telegram_id = estado.fila[0]["id"]
    assert estado.status[telegram_id] == "failed"
    assert estado.reroutes == []
    assert not any(m[0] == "discarded" for m in estado.marks)
    assert not any(sender.REROUTE_REFUSED in (linha["error"] or "") for linha in estado.log)
    # (c1) comitou: a de WhatsApp está entregue; a revogação do escopo 3 também.
    assert estado.status[estado.fila[1]["id"]] == "sent"
    assert len(estado.revokes) == 1
    assert "sending" not in estado.status.values()


async def test_identidade_ja_revogada_entre_a_fila_e_o_envio_nao_audita_mas_reroteia(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    """A pessoa foi desvinculada pelo painel depois de a linha entrar na fila
    e antes de sair: o `blocked` acha zero linhas vigentes para revogar —
    nenhuma auditoria fantasma — e a mensagem ainda vai pelo número."""
    estado = _degradavel()
    estado.identity_current = False
    estado, _ = db(estado, answers={telegram.NAME: _blocked})

    resultado = await _dispatch(estado)

    assert (resultado.failed, resultado.discarded) == (1, 0)
    assert len(estado.revokes) == 1 and estado.audits == []
    assert len(estado.reroutes) == 1 and estado.reroutes[0]["contact_id"] == CONTACT
    assert estado.rolled_back == set()


@pytest.mark.parametrize(
    ("codigo", "attempts", "revoga", "reroteia"),
    [
        # `blocked` é o único que revoga — e re-roteia.
        ("blocked", 0, True, True),
        ("blocked", 4, True, True),
        # Credencial morta: é do bot do tenant, não da pessoa — re-roteia sem revogar.
        ("http_401", 0, False, True),
        ("unauthorized", 0, False, True),
        # Falha comum: backoff, até o último — que re-roteia em vez de descartar.
        ("unreachable", 0, False, False),
        ("malformed", 3, False, False),
        ("http_500", 4, False, True),
        ("unreachable", 4, False, True),
    ],
)
async def test_a_tabela_da_degradacao(
    db: Callable[..., tuple[FakeDB, Built]],
    codigo: str,
    attempts: int,
    revoga: bool,
    reroteia: bool,
) -> None:
    estado, _ = db(_degradavel(attempts=attempts), answers={telegram.NAME: _falha(codigo)})
    queue_id = estado.fila[0]["id"]

    resultado = await _dispatch(estado)

    assert (len(estado.revokes) == 1) is revoga and (len(estado.audits) == 1) is revoga
    assert (len(estado.reroutes) == 1) is reroteia
    if reroteia:
        assert estado.marks == [("parked", queue_id), ("rerouted", queue_id)]
        assert resultado.failed == 1 and estado.status[queue_id] == "failed"
    else:
        assert estado.marks == [("failed", queue_id)]
        assert resultado.failed == 1 and not estado.due[queue_id]
    assert estado.log[0]["error"] == codigo and len(estado.log) == 1


@pytest.mark.parametrize("codigo", ["blocked", "http_401", "unreachable"])
async def test_em_whatsapp_nada_disso_degrada(
    db: Callable[..., tuple[FakeDB, Built]], codigo: str
) -> None:
    """A linha re-roteada é `whatsapp`, e o WhatsApp segue o backoff comum até
    descartar — nunca volta a Telegram. É o que faz a re-rota acontecer no
    máximo uma vez por linha, com `attempts` zerado sem risco de laço."""
    estado = _whatsapp_ready(
        FakeDB(
            fila=[_fila(attempts=0), _fila(attempts=4)],
            templates={"deviation_summary": _template()},
            holder={"contact_id": CONTACT, "employee_id": None},
        )
    )
    estado, _ = db(estado, answers={WA_PROVIDER: _falha(codigo)})

    resultado = await _dispatch(estado)

    assert estado.revokes == [] and estado.audits == [] and estado.reroutes == []
    assert [m[0] for m in estado.marks] == ["failed", "failed"]
    assert resultado.failed == 2 and resultado.discarded == 0
    assert not any("messaging_identity" in sql for _, sql, _ in estado.statements)
    esperas = [p["wait_minutes"] for _, sql, p in estado.statements if "then 'discarded'" in sql]
    assert esperas == [1, 360]


def test_a_re_rota_zera_as_tentativas_e_e_so_de_telegram_para_whatsapp() -> None:
    reroute = " ".join(sender._REROUTE_SQL.split())
    assert "attempts = 0," in reroute and "attempts + 1" not in reroute
    assert "status = 'failed'" in reroute and "next_attempt_at = now()" in reroute
    # A marca de (c1) conta a tentativa e não mexe no horário.
    park = " ".join(sender._PARK_SQL.split())
    assert "set status = 'failed', attempts = attempts + 1 where" in park
    assert "next_attempt_at" not in park
    # E o descarte não conta de novo.
    assert "attempts" not in sender._DISCARD_SQL
    # `_degrades` só aceita linha de Telegram.
    entrega = Delivery(status="failed", error="blocked")
    assert sender._degrades(_telegram_row(), entrega)
    assert not sender._degrades(_fila(), entrega)
    assert not sender._degrades(_fila(attempts=4), Delivery(status="failed", error="unreachable"))
    assert sender._degrades(_telegram_row(attempts=4), Delivery(status="failed", error="x"))
    assert not sender._degrades(_telegram_row(attempts=3), Delivery(status="failed", error="x"))
    assert not sender._degrades(_telegram_row(), Delivery(status="sent"))


async def test_o_provedor_de_telegram_diz_http_401_a_um_token_morto() -> None:
    """O conjunto `CREDENTIAL_ERRORS` prende o que o provedor de verdade diz."""

    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    async with verification_client(transport=httpx.MockTransport(unauthorized)) as http:
        provider = fabrica.build(
            telegram.NAME, config={}, secrets={"bot_token": BOT_TOKEN}, http=http
        )
        entrega = await provider.enviar(
            Message(destination=CHAT_ID, template="x", variables=(), facts={}, body="oi")
        )
    assert entrega.status == "failed" and entrega.error in sender.CREDENTIAL_ERRORS
    assert entrega.error == "http_401"


def test_unauthorized_e_o_codigo_da_verificacao_do_mesmo_modulo() -> None:
    fonte = Path(telegram.__file__).read_text(encoding="utf-8")
    assert 'InvalidCredentialError("unauthorized")' in fonte
    assert sender.CREDENTIAL_ERRORS == {"unauthorized", "http_401"}
    assert sender.BLOCKED_ERROR not in sender.CREDENTIAL_ERRORS


@pytest.mark.parametrize(
    ("holder", "whatsapp_provider", "contact_has_whatsapp", "revoked"),
    [
        # Sem WhatsApp ativo no tenant: não há para onde ir.
        ({"contact_id": CONTACT, "employee_id": None}, None, True, True),
        # Contato sem número (ou inativo): o re-roteamento devolve zero linhas.
        ({"contact_id": CONTACT, "employee_id": None}, WA_PROVIDER, False, True),
        # Titular colaborador: o outbox de hoje não o alcança; sem número de contato.
        ({"contact_id": None, "employee_id": uuid4()}, WA_PROVIDER, True, True),
        # Chat sem identidade nenhuma: nada a revogar, nada a re-rotear.
        (None, WA_PROVIDER, True, False),
    ],
)
async def test_blocked_sem_whatsapp_para_onde_ir_descarta_nomeado(
    db: Callable[..., tuple[FakeDB, Built]],
    holder: dict[str, Any] | None,
    whatsapp_provider: str | None,
    contact_has_whatsapp: bool,
    revoked: bool,
) -> None:
    estado = _bot_ready(
        FakeDB(
            fila=[_telegram_row()],
            templates={"deviation_summary": _template()},
            holder=holder,
            contact_has_whatsapp=contact_has_whatsapp,
        )
    )
    estado.whatsapp_provider = whatsapp_provider
    estado, _ = db(estado, answers={telegram.NAME: _blocked})

    resultado = await _dispatch(estado)

    assert (resultado.discarded, resultado.failed) == (1, 0)
    assert estado.marks == [("parked", estado.fila[0]["id"]), ("discarded", estado.fila[0]["id"])]
    assert (len(estado.revokes) == 1) is revoked and (len(estado.audits) == 1) is revoked
    # Uma linha de log só, a da tentativa: sem recusa de gatilho não há segunda.
    assert [linha["error"] for linha in estado.log] == ["blocked"]
    assert estado.rolled_back == set()


async def test_o_provedor_de_telegram_responde_blocked_no_403() -> None:
    """A palavra que o sender espera é a que o provedor de verdade diz."""

    def forbid(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"ok": False, "description": "Forbidden: bot was blocked"})

    async with verification_client(transport=httpx.MockTransport(forbid)) as http:
        provider = fabrica.build(
            telegram.NAME, config={}, secrets={"bot_token": BOT_TOKEN}, http=http
        )
        entrega = await provider.enviar(
            Message(destination=CHAT_ID, template="x", variables=(), facts={}, body="oi")
        )
    assert entrega == Delivery(status="failed", error=sender.BLOCKED_ERROR)


def test_o_reroute_e_o_holder_ligam_o_tenant_e_nao_carregam_o_numero() -> None:
    for sql in (
        sender._IDENTITY_HOLDER_SQL,
        sender._REROUTE_SQL,
        sender._DISCARD_SQL,
        sender._AUDIT_SQL,
        sender._WAITING_SQL,
        sender._CLAIM_SQL,
        sender._TEMPLATE_SQL,
        sender._INTEGRATIONS_SQL,
        sender._MARK_SENT_SQL,
        sender._MARK_FAILED_SQL,
        sender._LOG_SQL,
    ):
        assert bind_tenant(sql, {}, CONTEXT)["tenant_id"] == TENANT
    reroute = " ".join(sender._REROUTE_SQL.split())
    assert "destination = c.whatsapp" in reroute  # o número vem do banco
    assert "c.tenant_id = %(tenant_id)s" in reroute and "q.tenant_id = %(tenant_id)s" in reroute
    assert "c.active" in reroute and "c.whatsapp is not null" in reroute
    assert "status = 'failed'" in reroute and "next_attempt_at = now()" in reroute
    holder = " ".join(sender._IDENTITY_HOLDER_SQL.split())
    assert "select contact_id, employee_id from app.messaging_identity" in holder
    assert "external_id" not in holder.split("from")[0]  # não seleciona o chat_id
    assert "and channel = %(channel)s" in holder
    # A vigente primeiro: um chat_id revogado de A e vigente de B aponta B.
    assert "order by (revoked_at is null) desc, opted_in_at desc limit 1" in holder


# ---------------------------------------------------------------------------
# 6. `sending` presa
# ---------------------------------------------------------------------------
def test_a_reserva_retoma_sending_presa_e_carimba_a_reserva() -> None:
    sql = " ".join(sender._CLAIM_SQL.split())
    presa = "q.status = 'sending' and q.next_attempt_at < now() - make_interval(mins => "
    assert presa + "%(stuck_minutes)s)" in sql
    assert "set status = 'sending', next_attempt_at = now()" in sql
    assert "q.status as previous_status" in sql and "alvo.previous_status" in sql
    assert sender.STUCK_MINUTES == 10


async def test_a_recuperada_e_contada_no_relatorio(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    estado, _ = db(
        _whatsapp_ready(
            FakeDB(
                # Uma presa e DUAS pending: "conta sending" e "conta pending"
                # deixam de dar o mesmo número.
                fila=[_fila(previous_status="sending"), _fila(), _fila()],
                templates={"deviation_summary": _template()},
            )
        )
    )

    resultado = await _dispatch(estado)
    (claim,) = [p for _, sql, p in estado.statements if "set status = 'sending'" in sql]

    assert claim["stuck_minutes"] == sender.STUCK_MINUTES and claim["batch"] == sender.BATCH
    assert (resultado.claimed, resultado.recovered, resultado.sent) == (3, 1, 3)
    texto = sender.relatorio([resultado])
    assert "3 reservada(s) · 3 enviada(s) (whatsapp 3)" in texto
    assert "1 recuperada(s)" in texto


# ---------------------------------------------------------------------------
# 7. Token e destino em lugar nenhum do log
# ---------------------------------------------------------------------------
@pytest.fixture
def transport() -> Iterator[Recorder]:
    recorder = Recorder()
    _reset_http_loggers()
    yield recorder
    _reset_http_loggers()


async def test_o_token_e_o_chat_id_nao_aparecem_no_log_em_debug(
    monkeypatch: pytest.MonkeyPatch, transport: Recorder, caplog: pytest.LogCaptureFixture
) -> None:
    """Com a fábrica DE VERDADE e o provedor de Telegram de verdade. Positivo
    primeiro: um `AsyncClient` cru escreve a URL — o token — no log do `httpx`.
    Com o `verification_client`, que é o que `run` constrói, não."""
    transport.refuse_echoing_the_token(BOT_TOKEN)

    def instalar() -> FakeDB:
        estado = _bot_ready(
            FakeDB(fila=[_telegram_row()], templates={"deviation_summary": _template()})
        )
        monkeypatch.setattr(
            sender,
            "tenant_scope",
            lambda context, schema="app": FakeScope(FakeCursor(estado, context), estado),
        )
        return estado

    _reset_http_loggers()
    estado = instalar()
    with caplog.at_level(logging.DEBUG):
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport.handler)) as raw:
            await sender.dispatch(CONTEXT, raw)
    assert BOT_TOKEN in caplog.text

    caplog.clear()
    estado = instalar()
    with caplog.at_level(logging.DEBUG):
        async with verification_client(transport=httpx.MockTransport(transport.handler)) as http:
            resultado = await sender.dispatch(CONTEXT, http)
    assert BOT_TOKEN not in caplog.text
    assert CHAT_ID not in caplog.text
    # Token morto é credencial: degrada; sem titular (o fake não tem), descarta.
    assert resultado.discarded == 1 and estado.log[0]["error"] == "http_401"
    # Nem o token nem o chat_id passam por instrução alguma da fase (c) — o
    # destino vai para o log de longo prazo como hash.
    for _, sql, params in estado.statements:
        assert BOT_TOKEN not in sql and BOT_TOKEN not in json.dumps(params, default=str)
    assert estado.log[0]["destination_hash"] == sender.destination_hash(CHAT_ID)
    assert CHAT_ID not in json.dumps(estado.log, default=str)
    # E o relatório não conhece destino nenhum.
    assert CHAT_ID not in sender.relatorio([resultado])
    _reset_http_loggers()


def test_run_constroi_o_cliente_pelo_verification_client() -> None:
    fonte = Path(sender.__file__).read_text(encoding="utf-8")
    assert "verification_client()" in fonte
    assert "httpx.AsyncClient(" not in fonte
    assert "NullProvider" not in fonte and "default_providers" not in fonte


async def test_um_tenant_que_morre_no_lote_nao_leva_os_outros(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dívida nomeada no fechamento do C5: `run()` era uma list comprehension,
    e o cofre de um tenant fora do ar silenciava a fila de todos. Agora o tenant
    que falhou aparece no relatório pelo nome, e o seguinte é despachado."""
    tenant_a = SystemContext(tenant_id=UUID("aaaaaaaa-0000-4000-8000-000000000001"), task="teste")
    tenant_b = SystemContext(tenant_id=UUID("bbbbbbbb-0000-4000-8000-000000000002"), task="teste")
    despachados: list[UUID] = []

    async def tenants(_task: str) -> list[SystemContext]:
        return [tenant_a, tenant_b]

    async def dispatch(ctx: SystemContext, _http: object, *, batch: int) -> sender.SendResult:
        despachados.append(ctx.tenant_id)
        if ctx is tenant_a:
            raise RuntimeError("cofre fora do ar")
        return sender.SendResult(tenant_id=ctx.tenant_id, gate_open=False, claimed=1, sent=1)

    monkeypatch.setattr(sender, "active_tenants", tenants)
    monkeypatch.setattr(sender, "dispatch", dispatch)

    resultados = await sender.run(batch=5)

    # O segundo tenant foi despachado apesar do primeiro.
    assert despachados == [tenant_a.tenant_id, tenant_b.tenant_id]
    falhou, seguiu = resultados
    assert falhou.error == "RuntimeError" and falhou.claimed == 0
    assert seguiu.error is None and seguiu.sent == 1
    # E o relatório nomeia o tenant e o motivo, sem esconder o que seguiu.
    texto = sender.relatorio(resultados)
    assert f"tenant {tenant_a.tenant_id}: ✗ o lote morreu (RuntimeError)" in texto
    assert f"tenant {tenant_b.tenant_id}: 1 reservada(s) · 1 enviada(s)" in texto


# ---------------------------------------------------------------------------
# 8. `alert_sent` roteado por canal e provedor
# ---------------------------------------------------------------------------
async def test_o_log_grava_o_canal_e_o_provedor_da_linha_roteada(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    estado, _ = db(
        _bot_ready(
            _whatsapp_ready(
                FakeDB(
                    fila=[
                        _fila(),
                        _telegram_row(),
                        _fila(channel="email", provider=None, destination="a@b"),
                    ],
                    templates={"deviation_summary": _template()},
                )
            )
        )
    )

    resultado = await _dispatch(estado)

    assert [(row["channel"], row["provider"], row["status"]) for row in estado.log] == [
        (WHATSAPP_CHANNEL, WA_PROVIDER, "sent"),
        (TELEGRAM_CHANNEL, telegram.NAME, "sent"),
        ("email", "smtp", "failed"),
    ]
    assert estado.log[1]["destination_hash"] == sender.destination_hash(CHAT_ID)
    assert estado.log[0]["cost_cents"] == 4
    assert resultado.sent_by_channel == {WHATSAPP_CHANNEL: 1, TELEGRAM_CHANNEL: 1}
    assert "(telegram 1 · whatsapp 1)" in sender.relatorio([resultado])


async def test_a_falha_comum_volta_com_backoff_e_a_quinta_descarta(
    db: Callable[..., tuple[FakeDB, Built]],
) -> None:
    def falha(message: Message) -> Delivery:
        return Delivery(status="failed", error="unreachable")

    estado, _ = db(
        _whatsapp_ready(
            FakeDB(
                fila=[_fila(attempts=0), _fila(attempts=4)],
                templates={"deviation_summary": _template()},
            )
        ),
        answers={WA_PROVIDER: falha},
    )
    # O banco falso decide o ramo pelo `max_attempts` que recebe; aqui o que se
    # afirma é o `wait_minutes` de cada tentativa e o log de cada uma.
    resultado = await _dispatch(estado)

    esperas = [p["wait_minutes"] for _, sql, p in estado.statements if "then 'discarded'" in sql]
    assert esperas == [1, 360]
    assert resultado.failed == 2 and all(row["error"] == "unreachable" for row in estado.log)
