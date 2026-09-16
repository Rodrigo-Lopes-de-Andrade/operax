"""O webhook `/start` do Telegram: a ordem dos passos é o contrato (SPEC-CANAIS §6).

Sete portões (SPRINTS-CANAIS, C3, onda 2b):

1. **a ordem** — rate limit por IP → resolução pelo `path_token` → rate limit
   por token → header em tempo constante → **só então** o corpo. Uma linha do
   tempo compartilhada entre os dois limitadores, a resolução, o `tenant_scope`
   e o `Request.body` registra em que ponto cada coisa aconteceu;
2. **404 seco** para `path_token` desconhecido e para header ausente ou errado,
   com o corpo **não lido** — quem não tem o segredo não recebe nem a
   confirmação de que o endereço existe, nem o parse do que mandou;
3. **`hmac.compare_digest`** — grep no fonte: nenhum `==` entre o header e o segredo;
4. **429 sem corpo**, por IP antes de resolver e por token depois;
5. **update ignorado é 200 vazio** e o log leva só o tipo — nunca o texto, o
   `chat_id`, o `from`. O bot não responde;
6. **`/start`** — o válido cria a identidade, consome o convite e audita sem
   `chat_id`; as três recusas são distinguíveis no log pelo código e não
   escrevem nada; `chat_in_use` sai da transação (rollback) sem consumir o
   convite; o segundo `/start` da mesma pessoa revoga a anterior;
7. **varredura sob DEBUG** — o corpo do update, com um `chat_id` e um nome de
   sonda, não aparece em log nenhum, em cenário nenhum.

⚠️ O QUE ESTA SUÍTE NÃO PODE PROVAR
O `for update` segurando dois `/start` do mesmo link, o índice parcial
recusando o mesmo `chat_id` para duas pessoas, o rollback desfazendo o
`used_at`, e a segunda adesão deixando exatamente uma vigente são
`scripts/97_teste_canais.py`, contra o banco real, com o SQL importado deste
módulo. Aqui o banco é um stub que responde pelo assunto da instrução e
registra o que foi pedido.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from psycopg import errors

from operax.core import tenant as tenant_module
from operax.core.tenant import (
    AmbiguousWebhookTokenError,
    SystemContext,
    bind_tenant,
    context_for_webhook,
)
from server.ratelimit import RateLimiter
from server.routers import canais, webhooks
from tests.conftest import TENANT_ID
from tests.test_canais_credencial import _all_text
from tests.test_canais_templates import AnsweringScope, TimedScopeContext, _statements

INTEGRATION_ID = UUID("33333333-3333-4333-8333-333333333334")
INVITE_ID = UUID("55555555-5555-4555-8555-555555555551")
IDENTITY_ID = UUID("66666666-6666-4666-8666-666666666661")
PREVIOUS_IDENTITY_ID = UUID("66666666-6666-4666-8666-666666666660")
EMPLOYEE_ID = UUID("77777777-7777-4777-8777-777777777771")
CONTACT_ID = UUID("77777777-7777-4777-8777-777777777772")

#: A cauda pública da URL, na forma de `secrets.token_urlsafe(24)`.
PATH_TOKEN = "cauda-publica-de-teste-0123456789AB"
#: O segredo do header. Valor de teste, óbvio de propósito.
WEBHOOK_SECRET = "segredo-do-webhook-de-teste-nao-e-real-000000"
#: O token do convite (o que vai em `?start=`), e o hash que o banco guarda.
INVITE_TOKEN = "convite-de-teste-0123456789abcdefXYZ"
INVITE_HASH = hashlib.sha256(INVITE_TOKEN.encode("ascii")).hexdigest()
#: As sondas: o que não pode aparecer em log, resposta nem auditoria.
CHAT_ID = 987654321012
PROBE_NAME = "Sonda Silva"
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)

WEBHOOK_SOURCE = Path(webhooks.__file__).read_text(encoding="utf-8")
TENANT_SOURCE = Path(tenant_module.__file__).read_text(encoding="utf-8")


def update(
    text: str | None = f"/start {INVITE_TOKEN}",
    *,
    chat_id: Any = CHAT_ID,
    chat_type: str = "private",
    kind: str = "message",
) -> dict[str, Any]:
    """Um update como o Telegram o manda, com as sondas em `from` e `chat`."""
    message: dict[str, Any] = {
        "message_id": 7,
        "from": {"id": chat_id, "is_bot": False, "first_name": PROBE_NAME},
        "chat": {"id": chat_id, "type": chat_type, "first_name": PROBE_NAME},
        "date": 1789560000,
    }
    if text is not None:
        message["text"] = text
    else:
        message["photo"] = [{"file_id": "AgAC", "width": 1, "height": 1}]
    return {"update_id": 1, kind: message}


class RecordingLimiter(RateLimiter):
    """Um `RateLimiter` que anota na linha do tempo quando foi consultado."""

    def __init__(self, timeline: list[str], name: str, limit: int) -> None:
        super().__init__(limit=limit, window=60.0)
        self.timeline = timeline
        self.name = name

    def retry_after(self, key: Any) -> int | None:
        self.timeline.append(self.name)
        return super().retry_after(key)


class _UniqueRefusal(errors.UniqueViolation):
    """O `23505` do Postgres, com o `constraint_name` do índice e a mensagem
    real — que carrega a chave duplicada, ou seja, o `chat_id`."""

    def __init__(self, constraint: str) -> None:
        super().__init__(
            f'duplicate key value violates unique constraint "{constraint}"\n'
            f"DETAIL:  Key (tenant_id, channel, external_id)=(…, telegram, {CHAT_ID}) "
            "already exists."
        )
        self._constraint = constraint

    @property
    def diag(self) -> Any:
        return SimpleNamespace(constraint_name=self._constraint)


@dataclass
class FakeInvite:
    contact_id: UUID | None = None
    employee_id: UUID | None = EMPLOYEE_ID
    used_at: datetime | None = None
    expired: bool = False

    def row(self) -> dict[str, Any]:
        return {
            "id": INVITE_ID,
            "contact_id": self.contact_id,
            "employee_id": self.employee_id,
            "used_at": self.used_at,
            "expired": self.expired,
        }


@dataclass
class Stubs:
    bound: AnsweringScope
    bound_ctx: TimedScopeContext
    timeline: list[str]


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Stubs]:
    def install(
        *,
        invite: FakeInvite | None | str = "default",
        secret: str | None = WEBHOOK_SECRET,
        resolves: bool = True,
        insert: Any = "default",
        revoked: list[dict[str, Any]] | None = None,
        ip_limit: int = 1000,
        token_limit: int = 1000,
    ) -> Stubs:
        if invite == "default":
            invite = FakeInvite()
        assert invite is None or isinstance(invite, FakeInvite)
        if insert == "default":
            insert = {"id": IDENTITY_ID}
        timeline: list[str] = []

        def invite_row(params: Any) -> dict[str, Any] | None:
            if invite is None or params["token_hash"] != INVITE_HASH:
                return None
            return invite.row()

        bound = AnsweringScope(
            {
                "vault.decrypted_secrets": {"decrypted_secret": secret} if secret else None,
                "from app.messaging_invite": invite_row,
                "update app.messaging_invite": {"id": INVITE_ID},
                "update app.messaging_identity": revoked or [],
                "insert into app.messaging_identity": insert,
                "insert into app.audit_log": None,
            }
        )
        bound_ctx = TimedScopeContext(bound, timeline, "tenant_scope")
        monkeypatch.setattr(webhooks, "tenant_scope", lambda _c: bound_ctx)

        async def resolve(*, provider: str, path_token: str, task: str) -> Any:
            timeline.append("resolve")
            assert provider == "telegram" and task == webhooks.TASK
            if resolves and path_token == PATH_TOKEN:
                return SystemContext(tenant_id=TENANT_ID, task=task), INTEGRATION_ID
            return None

        monkeypatch.setattr(webhooks, "context_for_webhook", resolve)
        monkeypatch.setattr(
            webhooks, "_ip_limiter", RecordingLimiter(timeline, "ip_limit", ip_limit)
        )
        monkeypatch.setattr(
            webhooks, "_token_limiter", RecordingLimiter(timeline, "token_limit", token_limit)
        )
        monkeypatch.setattr(webhooks, "unknown_path_tokens", 0)

        original_body = Request.body

        async def body(self: Request) -> bytes:
            timeline.append("body:read")
            return await original_body(self)

        monkeypatch.setattr(Request, "body", body)
        return Stubs(bound=bound, bound_ctx=bound_ctx, timeline=timeline)

    return install


def _post(
    client: TestClient,
    body: Any = None,
    *,
    path_token: str = PATH_TOKEN,
    secret: str | None = WEBHOOK_SECRET,
    headers: dict[str, Any] | None = None,
) -> Any:
    """Sem `Authorization`, nunca: quem chama é a plataforma."""
    if body is None:
        body = update()
    content = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    sent: dict[str, Any] = dict(headers or {})
    if secret is not None:
        sent[webhooks.SECRET_HEADER] = secret
    return client.post(f"/webhooks/telegram/{path_token}", content=content, headers=sent)


def _writes(scope: AnsweringScope) -> list[str]:
    markers = ("update app.messaging", "insert into app.messaging", "insert into app.audit_log")
    return [s for s in scope.statements if any(m in s for m in markers)]


def _log(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == webhooks.logger.name]


def _app_log(caplog: pytest.LogCaptureFixture) -> str:
    """O que o SERVIDOR logou, em qualquer logger — menos as linhas do próprio
    `TestClient` (`httpx*`), que nomeiam a URL que ELE pediu: a cauda pública
    estaria lá pelo motivo errado. (Em produção essa linha é o access log do
    uvicorn, que carrega o caminho de toda rota; o `path_token` é público por
    decisão da onda 2a — a autenticação é o header.)"""
    return "\n".join(
        r.getMessage() for r in caplog.records if not r.name.startswith(("httpx", "httpcore"))
    )


VALID_TIMELINE = [
    "ip_limit",
    "resolve",
    "token_limit",
    "tenant_scope:enter",
    "tenant_scope:exit",
    "body:read",
    "tenant_scope:enter",
    "tenant_scope:exit",
]


# ---------------------------------------------------------------------------
# Gate 1 — a ordem
# ---------------------------------------------------------------------------
def test_a_ordem_dos_passos_e_o_contrato(client: TestClient, db: Callable[..., Stubs]) -> None:
    """IP → resolução → token → header (um `tenant_scope` só para o segredo,
    FECHADO) → corpo → a transação do vínculo. ⛔ Mutação: ler o corpo antes do
    header, ou resolver antes do limite por IP, muda a lista."""
    stubs = db()

    resposta = _post(client)

    assert resposta.status_code == 200
    assert resposta.content == b""
    assert stubs.timeline == VALID_TIMELINE


def test_a_rota_nao_le_o_corpo_por_parametro_de_fastapi() -> None:
    """Se a assinatura ganhasse um corpo Pydantic, o FastAPI leria (e ecoaria
    no 422) antes do header. Só `path_token` e `request`."""
    import inspect

    parametros = inspect.signature(webhooks.telegram_update).parameters
    assert set(parametros) == {"path_token", "request"}


# ---------------------------------------------------------------------------
# Gate 2 — 404 seco, corpo não lido
# ---------------------------------------------------------------------------
def test_path_token_desconhecido_e_404_seco_sem_ler_o_corpo_e_sem_log(
    client: TestClient, db: Callable[..., Stubs], caplog: pytest.LogCaptureFixture
) -> None:
    stubs = db(resolves=False)

    with caplog.at_level(logging.DEBUG):
        resposta = _post(client)

    assert resposta.status_code == 404
    assert resposta.content == b""
    assert stubs.timeline == ["ip_limit", "resolve"]
    assert stubs.bound_ctx.opened == 0
    assert webhooks.unknown_path_tokens == 1
    assert PATH_TOKEN not in _app_log(caplog)
    assert _log(caplog) == []  # um contador, não um log por requisição


@pytest.mark.parametrize("bad", ["curto", "a" * 129, "com.ponto-0123456789ABCDEF"])
def test_path_token_fora_de_forma_nem_chega_a_resolucao(
    client: TestClient, db: Callable[..., Stubs], bad: str
) -> None:
    stubs = db()

    resposta = _post(client, path_token=bad)

    assert resposta.status_code == 404
    assert resposta.content == b""
    assert stubs.timeline == ["ip_limit"]
    assert webhooks.unknown_path_tokens == 1


@pytest.mark.parametrize("secret", [None, "", "segredo-errado-000000000000000000000000000"])
def test_header_ausente_ou_errado_e_404_seco_e_o_corpo_nao_foi_lido(
    client: TestClient, db: Callable[..., Stubs], secret: str | None
) -> None:
    """Não 401, não 403: a existência do endpoint não se confirma a quem não tem
    o segredo. E o `tenant_scope` do cofre já fechou quando a resposta sai."""
    stubs = db()

    resposta = _post(client, secret=secret)

    assert resposta.status_code == 404
    assert resposta.content == b""
    assert "body:read" not in stubs.timeline
    assert stubs.timeline == VALID_TIMELINE[:5]
    assert not any("messaging_invite" in s for s in stubs.bound.statements)
    assert _writes(stubs.bound) == []


@pytest.mark.parametrize("header", [WEBHOOK_SECRET, None], ids=["com header", "sem header"])
def test_sem_segredo_no_cofre_e_404_e_o_corpo_nao_foi_lido(
    client: TestClient, db: Callable[..., Stubs], header: str | None
) -> None:
    """Integração resolvida mas sem `webhook_secret` no cofre (bot nunca
    conectado, ou desconectado e rotacionado): nada a comparar, nada a ler.
    ⛔ Sem header também: `compare_digest(b"", b"")` é verdadeiro, e um
    `secret or ""` antes da comparação abriria o endpoint a quem não manda
    header nenhum."""
    stubs = db(secret=None)

    resposta = _post(client, secret=header)

    assert resposta.status_code == 404
    assert resposta.content == b""
    assert "body:read" not in stubs.timeline


def test_o_segredo_e_lido_do_cofre_pela_chave_que_conectar_grava(
    client: TestClient, db: Callable[..., Stubs]
) -> None:
    stubs = db()
    _post(client)
    [(_, params)] = _statements(stubs.bound, "vault.decrypted_secrets")
    assert params["key"] == webhooks.WEBHOOK_SECRET_KEY == canais._WEBHOOK_SECRET_KEY
    assert params["integration_id"] == INTEGRATION_ID


# ---------------------------------------------------------------------------
# Gate 3 — tempo constante
# ---------------------------------------------------------------------------
def test_o_header_e_comparado_por_compare_digest_e_nunca_por_igualdade() -> None:
    """⛔ Mutação: `presented == secret` deixa isto vermelho. A comparação em
    tempo constante é a única forma de `==` que o segredo aceita."""
    assert "hmac.compare_digest(" in WEBHOOK_SOURCE
    for line in WEBHOOK_SOURCE.splitlines():
        if "==" in line and not line.strip().startswith("#"):
            assert "secret" not in line and "presented" not in line and "header" not in line, line
    # Bytes dos dois lados: `compare_digest` com `str` levanta em não-ASCII, e
    # o header é dado hostil.
    assert re.search(r"compare_digest\(presented\.encode\(.*secret\.encode\(", WEBHOOK_SOURCE)


def test_header_com_nao_ascii_e_404_e_nao_500(client: TestClient, db: Callable[..., Stubs]) -> None:
    db()
    # Bytes latin-1, como um header não-ASCII chega pela rede; o Starlette o
    # decodifica em `str` com acento, e `compare_digest` de `str` levantaria.
    acentuado: dict[str, Any] = {
        webhooks.SECRET_HEADER: "segrédo-çom-acento-000000000000000000".encode("latin-1")
    }
    resposta = _post(client, secret=None, headers=acentuado)
    assert resposta.status_code == 404
    assert resposta.content == b""


# ---------------------------------------------------------------------------
# Gate 4 — 429 sem corpo
# ---------------------------------------------------------------------------
def test_429_por_ip_sem_corpo_e_antes_da_resolucao(
    client: TestClient, db: Callable[..., Stubs]
) -> None:
    stubs = db(ip_limit=2)
    assert _post(client).status_code == 200
    assert _post(client).status_code == 200
    stubs.timeline.clear()

    excedente = _post(client)

    assert excedente.status_code == 429
    assert excedente.content == b""
    assert int(excedente.headers["retry-after"]) > 0
    assert stubs.timeline == ["ip_limit"]


def test_429_por_token_sem_corpo_depois_da_resolucao_e_antes_do_cofre(
    client: TestClient, db: Callable[..., Stubs]
) -> None:
    stubs = db(token_limit=2)
    assert _post(client).status_code == 200
    assert _post(client).status_code == 200
    stubs.timeline.clear()
    opened = stubs.bound_ctx.opened

    excedente = _post(client)

    assert excedente.status_code == 429
    assert excedente.content == b""
    assert stubs.timeline == ["ip_limit", "resolve", "token_limit"]
    assert stubs.bound_ctx.opened == opened


def test_o_limite_por_token_e_do_token_e_nao_do_ip(
    client: TestClient, db: Callable[..., Stubs]
) -> None:
    """Um `path_token` desconhecido não gasta a janela do conhecido: o
    limitador por token só é consultado depois da resolução."""
    stubs = db(token_limit=2)
    for _ in range(5):
        assert _post(client, path_token="outro-token-que-nao-existe-000000").status_code == 404
    assert stubs.timeline.count("token_limit") == 0
    assert _post(client).status_code == 200
    assert _post(client).status_code == 200
    assert _post(client).status_code == 429


def test_o_retry_after_nao_registra_a_batida_recusada() -> None:
    """Insistir não empurra a janela: a terceira e a quarta são recusadas pela
    mesma marca, e a espera não cresce."""
    limiter = RateLimiter(limit=2, window=60.0)
    assert limiter.retry_after("k") is None
    assert limiter.retry_after("k") is None
    primeira = limiter.retry_after("k")
    segunda = limiter.retry_after("k")
    assert primeira is not None and segunda is not None
    assert segunda <= primeira
    assert len(limiter._hits["k"]) == 2


# ---------------------------------------------------------------------------
# Gate 5 — update ignorado: 200 vazio, o log leva o tipo, o bot não responde
# ---------------------------------------------------------------------------
IGNORED: list[tuple[str, Any]] = [
    ("sem_mensagem", update(kind="edited_message")),
    ("sem_texto", update(None)),
    ("texto_livre", update("oi, quero receber os alertas")),
    ("texto_livre", update("/help")),
    ("start_sem_token", update("/start")),
    ("start_sem_token", update("/start abc")),
    ("start_sem_token", update("/start token com espaço 000000000000")),
    ("start_sem_token", update(f"/start {INVITE_TOKEN} ")),
    ("start_sem_token", update("/startar " + INVITE_TOKEN)),
    ("chat_nao_privado", update(chat_type="group", chat_id=-100123456789)),
    ("chat_nao_privado", update(chat_type="supergroup", chat_id=-100123456789)),
    ("chat_nao_privado", update(chat_type="channel", chat_id=-100123456789)),
    ("chat_id_invalido", update(chat_id=str(CHAT_ID))),
    ("chat_id_invalido", update(chat_id=True)),
    ("chat_id_invalido", update(chat_id=None)),
    ("sem_chat", {"update_id": 1, "message": {"text": f"/start {INVITE_TOKEN}"}}),
    ("nao_e_objeto", [update()]),
    ("nao_e_objeto", "texto"),
]


@pytest.mark.parametrize(("tipo", "body"), IGNORED)
def test_update_ignorado_e_200_vazio_e_o_log_so_tem_o_tipo(
    client: TestClient,
    db: Callable[..., Stubs],
    caplog: pytest.LogCaptureFixture,
    tipo: str,
    body: Any,
) -> None:
    """⛔ `chat_nao_privado`: um `/start` num grupo traria o `chat_id` do grupo,
    e o alerta individual da pessoa iria para o grupo inteiro — a regra 7 pela
    porta que `validate_alert_target` não vigia."""
    stubs = db()

    with caplog.at_level(logging.DEBUG):
        resposta = _post(client, body)

    assert resposta.status_code == 200
    assert resposta.content == b""
    [registro] = _log(caplog)
    assert registro.levelno == logging.INFO
    assert registro.getMessage() == f"telegram webhook: update ignorado ({tipo})"
    assert str(CHAT_ID) not in _app_log(caplog)
    assert PROBE_NAME not in _app_log(caplog)
    assert INVITE_TOKEN not in _app_log(caplog)
    # Nenhum vínculo tentado: o `tenant_scope` abriu só para o segredo.
    assert stubs.bound_ctx.opened == 1
    assert _writes(stubs.bound) == []


@pytest.mark.parametrize(
    "raw",
    [
        b"{nao e json " + str(CHAT_ID).encode() + b" " + PROBE_NAME.encode(),
        b"\xff\xfe" + str(CHAT_ID).encode(),
        b"",
    ],
)
def test_corpo_invalido_e_200_com_aviso_sem_o_corpo(
    client: TestClient, db: Callable[..., Stubs], caplog: pytest.LogCaptureFixture, raw: bytes
) -> None:
    db()

    with caplog.at_level(logging.DEBUG):
        resposta = _post(client, raw)

    assert resposta.status_code == 200
    assert resposta.content == b""
    [registro] = _log(caplog)
    assert registro.levelno == logging.WARNING
    assert registro.getMessage() == "telegram webhook: corpo inválido"
    assert str(CHAT_ID) not in _app_log(caplog)
    assert PROBE_NAME not in _app_log(caplog)


# ---------------------------------------------------------------------------
# Gate 6 — o /start
# ---------------------------------------------------------------------------
def test_start_valido_cria_a_identidade_consome_o_convite_e_audita_sem_chat_id(
    client: TestClient, db: Callable[..., Stubs], caplog: pytest.LogCaptureFixture
) -> None:
    stubs = db()

    with caplog.at_level(logging.DEBUG):
        resposta = _post(client)

    assert resposta.status_code == 200
    assert resposta.content == b""
    assert stubs.bound_ctx.exited_with is None  # commit

    [(invite_sql, invite_params)] = _statements(stubs.bound, "from app.messaging_invite")
    assert "for update" in invite_sql
    assert invite_params == {"channel": "telegram", "token_hash": INVITE_HASH}
    [(_, consume)] = _statements(stubs.bound, "update app.messaging_invite")
    assert consume == {"invite_id": INVITE_ID}
    [(revoke_sql, revoke)] = _statements(stubs.bound, "update app.messaging_identity")
    assert revoke == {
        "channel": "telegram",
        "reason": "novo /start",
        "contact_id": None,
        "employee_id": EMPLOYEE_ID,
    }
    assert "revoked_at is null" in revoke_sql and "set revoked_at = now()" in revoke_sql
    [(_, insert)] = _statements(stubs.bound, "insert into app.messaging_identity")
    assert insert == {
        "channel": "telegram",
        "external_id": str(CHAT_ID),
        "contact_id": None,
        "employee_id": EMPLOYEE_ID,
    }
    [(audit_sql, audit)] = _statements(stubs.bound, "insert into app.audit_log")
    assert "'insert', 'messaging_identity'" in audit_sql
    assert audit["entity_id"] == str(IDENTITY_ID)
    assert audit["depois"].obj == {"channel": "telegram", "invite_id": str(INVITE_ID)}
    assert str(CHAT_ID) not in _all_text(audit)
    assert PROBE_NAME not in _all_text(audit)

    # A ordem das escritas: consumir, revogar, inserir, auditar.
    assert [
        m
        for s in stubs.bound.statements
        for m in (
            "update app.messaging_invite",
            "update app.messaging_identity",
            "insert into app.messaging_identity",
            "insert into app.audit_log",
        )
        if m in s
    ] == [
        "update app.messaging_invite",
        "update app.messaging_identity",
        "insert into app.messaging_identity",
        "insert into app.audit_log",
    ]

    [registro] = _log(caplog)
    assert registro.getMessage() == (
        f"telegram webhook: identidade vinculada para o tenant {TENANT_ID}"
    )
    assert str(CHAT_ID) not in _app_log(caplog)


def test_o_token_do_convite_vai_ao_banco_como_hash_e_nunca_em_claro(
    client: TestClient, db: Callable[..., Stubs]
) -> None:
    """Regra 3 da §3.3: `token_hash`, nunca o token. Nem em parâmetro, nem no
    texto de instrução nenhuma."""
    stubs = db()
    _post(client)
    for statement, params in zip(stubs.bound.statements, stubs.bound.params, strict=True):
        assert INVITE_TOKEN not in statement
        assert INVITE_TOKEN not in _all_text(params)
    assert any(INVITE_HASH in _all_text(p) for p in stubs.bound.params)


@pytest.mark.parametrize(
    ("invite", "code"),
    [
        (None, "invite_unknown"),
        (FakeInvite(used_at=NOW), "invite_used"),
        (FakeInvite(expired=True), "invite_expired"),
        (FakeInvite(used_at=NOW, expired=True), "invite_used"),
    ],
)
def test_as_tres_recusas_sao_distinguiveis_no_log_e_nada_e_escrito(
    client: TestClient,
    db: Callable[..., Stubs],
    caplog: pytest.LogCaptureFixture,
    invite: FakeInvite | None,
    code: str,
) -> None:
    """200 para o Telegram (senão ele reenvia), o código no log, o convite
    intacto, e a transação saindo por exceção — que é o rollback do pool."""
    stubs = db(invite=invite)

    with caplog.at_level(logging.DEBUG):
        resposta = _post(client)

    assert resposta.status_code == 200
    assert resposta.content == b""
    [registro] = _log(caplog)
    assert registro.levelno == logging.INFO
    assert registro.getMessage() == (
        f"telegram webhook: /start recusado para o tenant {TENANT_ID} ({code})"
    )
    assert _writes(stubs.bound) == []
    assert stubs.bound_ctx.exited_with is webhooks._RefusedError
    assert str(CHAT_ID) not in _app_log(caplog)
    assert INVITE_TOKEN not in _app_log(caplog)


def test_chat_in_use_desfaz_a_transacao_e_nao_consome_o_convite(
    client: TestClient, db: Callable[..., Stubs], caplog: pytest.LogCaptureFixture
) -> None:
    """⛔ O irmão da regra 7 (§3.4): o mesmo `chat_id` vigente já é de outra
    pessoa do tenant. O índice recusa, a transação inteira volta — inclusive o
    `used_at` já escrito —, e a mensagem do Postgres, que carrega a chave (o
    `chat_id`), morre no `from None`."""
    violation = _UniqueRefusal("messaging_identity_vigente_external_uk")
    assert str(CHAT_ID) in str(violation)  # o positivo: a mensagem carregaria o chat_id
    stubs = db(insert=violation)

    with caplog.at_level(logging.DEBUG):
        resposta = _post(client)

    assert resposta.status_code == 200
    assert resposta.content == b""
    [registro] = _log(caplog)
    assert registro.getMessage() == (
        f"telegram webhook: /start recusado para o tenant {TENANT_ID} (chat_in_use)"
    )
    # O consumo foi executado dentro da transação; o que o desfaz é a saída por
    # exceção, que o pool traduz em rollback (`97` prova o `used_at` intacto).
    assert len(_statements(stubs.bound, "update app.messaging_invite")) == 1
    assert stubs.bound_ctx.exited_with is webhooks._RefusedError
    assert _statements(stubs.bound, "insert into app.audit_log") == []
    assert str(CHAT_ID) not in _app_log(caplog)
    assert "duplicate key" not in _app_log(caplog)


async def test_a_recusa_chat_in_use_nasce_from_none_e_a_cadeia_nao_carrega_o_chat_id(
    db: Callable[..., Stubs],
) -> None:
    """⛔ Mutação: tirar o `from None` deixa isto vermelho. Quem formatar a
    exceção com a cadeia (`exc_info=True`, Sentry) veria a mensagem do Postgres
    — e a chave duplicada nela é o `chat_id`."""
    import traceback

    db(insert=_UniqueRefusal("messaging_identity_vigente_external_uk"))
    context = SystemContext(tenant_id=TENANT_ID, task=webhooks.TASK)

    with pytest.raises(webhooks._RefusedError) as erro:
        await webhooks._bind(context, INVITE_TOKEN, CHAT_ID)

    assert erro.value.code == "chat_in_use"
    assert erro.value.__suppress_context__ is True
    assert erro.value.__cause__ is None
    formatado = "".join(traceback.format_exception(erro.value))
    assert str(CHAT_ID) not in formatado
    assert "duplicate key" not in formatado


def test_outra_violacao_unica_nao_e_chat_in_use_e_sobe(
    client: TestClient, db: Callable[..., Stubs]
) -> None:
    """O índice do titular estourando é corrida ou schema mudado — não é "chat
    em uso", e fingir que é mandaria o operador olhar a pessoa errada."""
    db(insert=_UniqueRefusal("messaging_identity_vigente_employee_uk"))

    with pytest.raises(errors.UniqueViolation):
        _post(client)


def test_o_segundo_start_da_mesma_pessoa_revoga_a_anterior_e_insere_a_nova(
    client: TestClient, db: Callable[..., Stubs]
) -> None:
    """A pessoa trocou de aparelho (ou de conta) e clicou num convite novo: a
    vigente anterior do MESMO titular ganha `revoked_at` e `novo /start`, e só
    depois a nova entra. Que sobra exatamente uma vigente é o `97`."""
    stubs = db(revoked=[{"id": PREVIOUS_IDENTITY_ID}])

    resposta = _post(client)

    assert resposta.status_code == 200
    [(revoke_sql, revoke)] = _statements(stubs.bound, "update app.messaging_identity")
    assert revoke["reason"] == "novo /start"
    assert revoke["employee_id"] == EMPLOYEE_ID and revoke["contact_id"] is None
    assert "contact_id is not distinct from %(contact_id)s" in revoke_sql
    assert "employee_id is not distinct from %(employee_id)s" in revoke_sql
    assert "delete" not in revoke_sql.lower()
    posicoes = [
        next(i for i, s in enumerate(stubs.bound.statements) if m in s)
        for m in ("update app.messaging_identity", "insert into app.messaging_identity")
    ]
    assert posicoes[0] < posicoes[1]


def test_start_de_um_responsavel_liga_o_contact_id(
    client: TestClient, db: Callable[..., Stubs]
) -> None:
    stubs = db(invite=FakeInvite(contact_id=CONTACT_ID, employee_id=None))
    assert _post(client).status_code == 200
    [(_, insert)] = _statements(stubs.bound, "insert into app.messaging_identity")
    assert insert["contact_id"] == CONTACT_ID and insert["employee_id"] is None


# ---------------------------------------------------------------------------
# Gate 7 — a varredura sob DEBUG, em todo cenário
# ---------------------------------------------------------------------------
def test_varredura_sob_debug_o_corpo_nunca_aparece_em_log_nenhum(
    client: TestClient, db: Callable[..., Stubs], caplog: pytest.LogCaptureFixture
) -> None:
    """Todos os cenários, um atrás do outro, com o logger raiz em DEBUG: o
    `chat_id`, o nome e o token do convite não aparecem em linha nenhuma, e
    nenhuma resposta tem corpo."""
    cenarios: list[tuple[dict[str, Any], Any, str | None]] = [
        ({}, update(), WEBHOOK_SECRET),
        ({"resolves": False}, update(), WEBHOOK_SECRET),
        ({}, update(), "errado-0000000000000000000000000000000000"),
        ({"invite": None}, update(), WEBHOOK_SECRET),
        ({"invite": FakeInvite(used_at=NOW)}, update(), WEBHOOK_SECRET),
        ({"invite": FakeInvite(expired=True)}, update(), WEBHOOK_SECRET),
        (
            {"insert": _UniqueRefusal("messaging_identity_vigente_external_uk")},
            update(),
            WEBHOOK_SECRET,
        ),
        ({}, update("oi " + PROBE_NAME), WEBHOOK_SECRET),
        ({}, update(chat_type="group"), WEBHOOK_SECRET),
        ({}, b"{" + PROBE_NAME.encode() + str(CHAT_ID).encode(), WEBHOOK_SECRET),
    ]
    with caplog.at_level(logging.DEBUG):
        for kwargs, body, secret in cenarios:
            db(**kwargs)
            resposta = _post(client, body, secret=secret)
            assert resposta.content == b"", (kwargs, body)
    # O positivo: as sondas ESTÃO no que foi mandado.
    assert str(CHAT_ID) in json.dumps(update()) and PROBE_NAME in json.dumps(update())
    assert str(CHAT_ID) not in _app_log(caplog)
    assert PROBE_NAME not in _app_log(caplog)
    assert INVITE_TOKEN not in _app_log(caplog)
    assert WEBHOOK_SECRET not in _app_log(caplog)
    assert PATH_TOKEN not in _app_log(caplog)


# ---------------------------------------------------------------------------
# A superfície: fora do OpenAPI, sem JWT, SQL ligado ao tenant
# ---------------------------------------------------------------------------
def test_a_rota_nao_esta_no_openapi_e_nao_exige_jwt(
    client: TestClient, db: Callable[..., Stubs]
) -> None:
    assert webhooks.router.include_in_schema is False
    paths = client.get("/openapi.json").json()["paths"]
    assert not any("webhook" in p for p in paths)
    assert "/canais/conexoes" in paths  # o positivo: o schema tem as outras

    db()
    # Um `Authorization` inválido não é olhado: não há usuário aqui.
    resposta = _post(client, headers={"Authorization": "Bearer nao-e-um-jwt"})
    assert resposta.status_code == 200


def test_as_instrucoes_do_passo_6_ligam_o_tenant_e_nao_apagam_nada() -> None:
    context = SystemContext(tenant_id=TENANT_ID, task="test")
    statements = {
        name: sql
        for name, sql in vars(webhooks).items()
        if name.endswith("_SQL") and isinstance(sql, str)
    }
    assert set(statements) == {
        "_INVITE_SQL",
        "_CONSUME_INVITE_SQL",
        "_REVOKE_PREVIOUS_SQL",
        "_INSERT_IDENTITY_SQL",
        "_AUDIT_SQL",
    }
    for sql in statements.values():
        assert bind_tenant(sql, {}, context)["tenant_id"] == TENANT_ID
        assert "delete" not in sql.lower()
    assert "tenant_id = %(tenant_id)s" in webhooks._INVITE_SQL
    assert "tenant_id = %(tenant_id)s" in webhooks._CONSUME_INVITE_SQL
    assert "tenant_id = %(tenant_id)s" in webhooks._REVOKE_PREVIOUS_SQL
    assert "(%(tenant_id)s, %(channel)s" in webhooks._INSERT_IDENTITY_SQL
    assert "(%(tenant_id)s, null, 'insert'" in webhooks._AUDIT_SQL
    assert "external_id" not in webhooks._AUDIT_SQL


def test_a_rota_usa_a_constante_do_provedor_para_o_caminho() -> None:
    from operax.alertas.provedores import telegram

    assert telegram.WEBHOOK_PATH == "/webhooks/telegram"
    assert "{telegram.WEBHOOK_PATH}/{{path_token}}" in WEBHOOK_SOURCE


# ---------------------------------------------------------------------------
# `context_for_webhook` — o segundo SQL que atravessa tenants
# ---------------------------------------------------------------------------
class FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, Any]] = []

    async def execute(self, statement: str, params: Any = None) -> None:
        self.calls.append((statement, params))

    async def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    async def __aenter__(self) -> FakeCursor:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self, row_factory: Any = None) -> FakeCursor:
        return self._cursor

    async def __aenter__(self) -> FakeConnection:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakePools:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.schemas: list[str] = []

    def pool(self, schema: str) -> Any:
        self.schemas.append(schema)
        return SimpleNamespace(connection=lambda: FakeConnection(self._cursor))


@pytest.fixture
def pool(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[dict[str, Any]]], FakeCursor]:
    def install(rows: list[dict[str, Any]]) -> FakeCursor:
        cursor = FakeCursor(rows)
        monkeypatch.setattr(tenant_module, "get_pools", lambda: FakePools(cursor))
        return cursor

    return install


async def test_context_for_webhook_devolve_o_contexto_do_tenant_dono_e_a_integracao(
    pool: Callable[[list[dict[str, Any]]], FakeCursor],
) -> None:
    cursor = pool([{"id": INTEGRATION_ID, "tenant_id": TENANT_ID}])

    resolved = await context_for_webhook(
        provider="telegram", path_token=PATH_TOKEN, task="telegram-webhook"
    )

    assert resolved is not None
    context, integration_id = resolved
    assert context == SystemContext(tenant_id=TENANT_ID, task="telegram-webhook")
    assert integration_id == INTEGRATION_ID
    [(statement, params)] = cursor.calls
    assert statement == tenant_module._WEBHOOK_INTEGRATION_SQL
    assert params == {"provider": "telegram", "path_token": PATH_TOKEN}
    assert "tenant_id" not in params  # não há tenant a ligar: é ele que se procura


async def test_context_for_webhook_sem_integracao_e_none(
    pool: Callable[[list[dict[str, Any]]], FakeCursor],
) -> None:
    pool([])
    assert await context_for_webhook(provider="telegram", path_token="x" * 32, task="t") is None


async def test_context_for_webhook_com_dois_donos_levanta_em_vez_de_escolher(
    pool: Callable[[list[dict[str, Any]]], FakeCursor],
) -> None:
    outro = UUID("22222222-2222-4222-8222-222222222223")
    pool(
        [
            {"id": INTEGRATION_ID, "tenant_id": TENANT_ID},
            {"id": INTEGRATION_ID, "tenant_id": outro},
        ]
    )
    with pytest.raises(AmbiguousWebhookTokenError):
        await context_for_webhook(provider="telegram", path_token=PATH_TOKEN, task="t")


def test_o_sql_do_webhook_exige_integracao_ativa_de_tenant_ativo_e_le_so_ids() -> None:
    sql = tenant_module._WEBHOOK_INTEGRATION_SQL
    assert "i.provider = %(provider)s" in sql
    assert "i.active" in sql
    assert "t.active" in sql
    assert "config ->> 'webhook_path_token' = %(path_token)s" in sql
    assert re.search(r"select\s+i\.id,\s+i\.tenant_id\s+from", sql)
    assert "config," not in sql and "select *" not in sql


def test_so_tres_instrucoes_de_tenant_py_alcancam_uma_tabela_sem_ligar_o_tenant() -> None:
    """O grep que o docstring de `_WEBHOOK_INTEGRATION_SQL` promete: toda
    constante `_SQL` de `tenant.py` que lê uma tabela de `app` e não liga
    `%(tenant_id)s` é uma das três nomeadas — a do bootstrap (filtrada pelo
    usuário), a dos tenants ativos e a do webhook. Uma quarta é achado."""
    constants = dict(re.findall(r'^(_[A-Z_]+_SQL) = """(.*?)"""', TENANT_SOURCE, re.S | re.M))
    unfiltered = {
        name for name, sql in constants.items() if "app." in sql and "%(tenant_id)s" not in sql
    }
    assert unfiltered == {"_MEMBERSHIP_SQL", "_ACTIVE_TENANTS_SQL", "_WEBHOOK_INTEGRATION_SQL"}
    assert set(constants) == {*unfiltered, "_ACT_AS_USER_SQL"}
