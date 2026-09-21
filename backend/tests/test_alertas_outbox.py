"""O roteamento por pessoa (SPEC-CANAIS §8): Telegram se houver identidade
vigente E bot ativo; WhatsApp caso contrário; e-mail intocado.

Quatro coisas, e o falso verde previsto para cada uma:

1. **`route` é puro e tem tabela** — e a tabela tem o par (identidade sim, bot
   não). Um roteamento que olhasse só a identidade passaria com fixtures que
   sempre têm bot.
2. **`_TARGETS_SQL` liga o tenant nas três fontes** — regra, identidade e
   integração. Uma `lateral` sem `tenant_id` leria a identidade de outro
   cliente com o mesmo `contact_id` (impossível por FK, mas a asserção é
   sobre a forma, não sobre a sorte).
3. **`both` vira `telegram` + `email` quando há identidade**, e `whatsapp` +
   `email` sem bot — pela `enqueue` inteira, contra um banco falso que responde
   por instrução.
4. **A chave de idempotência não muda com a rota**, e **nenhuma linha de
   relatório carrega destino** — o de uma linha `telegram` é o chat_id.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from operax.alertas import capacidades, ciclo, outbox
from operax.alertas.capacidades import TELEGRAM_CHANNEL, WHATSAPP_CHANNEL, providers_of
from operax.alertas.saude import HEALTH_CONNECTED
from operax.core.tenant import SystemContext, bind_tenant

TENANT = UUID("dddddddd-0000-0000-0000-000000000001")
UNIT = UUID("dddddddd-0000-0000-0000-00000000ac01")
RULE = UUID("dddddddd-0000-0000-0000-0000000000a1")
CONTACT = UUID("dddddddd-0000-0000-0000-0000000000c1")
PHONE = "+5511999999999"
EMAIL = "gestora@exemplo.test"
CHAT_ID = "987654321012"
WHATSAPP_PROVIDER = capacidades.WHATSAPP_PROVIDERS[0]


def _ciclo(**kwargs: Any) -> ciclo.Cycle:
    base: dict[str, Any] = dict(
        cycle_id=uuid4(),
        unit_id=UNIT,
        unit_name="Centro",
        period_start=date(2026, 8, 18),
        period_end=date(2026, 8, 24),
        total_events=7,
        deviation_minutes=213,
        from_previous_days=0,
    )
    return ciclo.Cycle(**{**base, **kwargs})


def _alvo(**overrides: Any) -> dict[str, Any]:
    """Uma linha de `_TARGETS_SQL`, com os dois campos que `route` lê."""
    base: dict[str, Any] = {
        "rule_id": RULE,
        "rule_name": "Resumo diário",
        "channel": WHATSAPP_CHANNEL,
        "template_code": "deviation_summary",
        "content": "aggregate",
        "contact_id": CONTACT,
        "contact_type": "person",
        "whatsapp": PHONE,
        "email": EMAIL,
        "telegram_external_id": None,
        "telegram_ready": False,
    }
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# 1. `route`, em tabela
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("half", "identity", "bot", "expected"),
    [
        # A regra inteira: identidade E bot → Telegram, ao chat_id.
        (WHATSAPP_CHANNEL, CHAT_ID, True, (TELEGRAM_CHANNEL, "telegram", CHAT_ID)),
        # ⛔ O par do falso verde: identidade SEM bot pronto → WhatsApp. Um
        #    roteamento que olhe só a identidade mandaria a mensagem para um chat
        #    sem bot — ou para um bot que o vigia mediu como desconectado.
        (WHATSAPP_CHANNEL, CHAT_ID, False, (WHATSAPP_CHANNEL, WHATSAPP_PROVIDER, PHONE)),
        # Bot sem identidade → WhatsApp: ninguém aderiu.
        (WHATSAPP_CHANNEL, None, True, (WHATSAPP_CHANNEL, WHATSAPP_PROVIDER, PHONE)),
        # Nada → WhatsApp, como era antes do C3.
        (WHATSAPP_CHANNEL, None, False, (WHATSAPP_CHANNEL, WHATSAPP_PROVIDER, PHONE)),
        # Identidade vazia (string) não é identidade.
        (WHATSAPP_CHANNEL, "", True, (WHATSAPP_CHANNEL, WHATSAPP_PROVIDER, PHONE)),
        # E-mail é intocado, mesmo com identidade e bot.
        ("email", CHAT_ID, True, ("email", "smtp", EMAIL)),
        ("email", None, False, ("email", "smtp", EMAIL)),
    ],
)
def test_route_decide_pela_identidade_e_pelo_bot(
    half: str, identity: str | None, bot: bool, expected: tuple[str, str, str]
) -> None:
    alvo = _alvo(telegram_external_id=identity, telegram_ready=bot)

    assert outbox.route(alvo, half, whatsapp_provider=WHATSAPP_PROVIDER) == expected


def test_route_por_telegram_nao_depende_do_numero_de_whatsapp() -> None:
    """Quem aderiu é alcançado pelo chat mesmo sem número em cadastro — e quem
    não aderiu e não tem número não é alcançado por esta metade."""
    aderiu = _alvo(telegram_external_id=CHAT_ID, telegram_ready=True, whatsapp=None)
    assert outbox.route(aderiu, WHATSAPP_CHANNEL, whatsapp_provider=WHATSAPP_PROVIDER) == (
        TELEGRAM_CHANNEL,
        "telegram",
        CHAT_ID,
    )
    sem_nada = _alvo(whatsapp=None)
    assert outbox.route(sem_nada, WHATSAPP_CHANNEL, whatsapp_provider=WHATSAPP_PROVIDER) == (
        WHATSAPP_CHANNEL,
        WHATSAPP_PROVIDER,
        None,
    )


def test_o_provedor_de_telegram_vem_da_matriz() -> None:
    """`outbox` não escreve o nome: ele é o único provedor do canal na matriz."""
    assert outbox.TELEGRAM_PROVIDER == providers_of(TELEGRAM_CHANNEL)[0]
    assert capacidades.channel_of(outbox.TELEGRAM_PROVIDER) == TELEGRAM_CHANNEL
    assert outbox.TELEGRAM_PROVIDER not in capacidades.WHATSAPP_PROVIDERS


# ---------------------------------------------------------------------------
# 2. `_TARGETS_SQL` liga o tenant nas três fontes
# ---------------------------------------------------------------------------
def test_targets_sql_liga_o_tenant_na_regra_na_identidade_e_na_integracao() -> None:
    sql = outbox._TARGETS_SQL
    bind_tenant(sql, {}, SystemContext(tenant_id=TENANT, task="teste"))
    assert "r.tenant_id = %(tenant_id)s" in sql
    assert "mi.tenant_id = %(tenant_id)s" in sql
    assert "i.tenant_id = %(tenant_id)s" in sql
    assert "ur.tenant_id = %(tenant_id)s" in sql


def test_targets_sql_escolhe_o_responsavel_entre_os_ativos_antes_do_limit_1() -> None:
    """Por responsabilidade, o primário desativado cai para o próximo ativo: o
    filtro de `active` está DENTRO da subconsulta, antes de `order by … limit 1`
    — fora dela, o escolhido era descartado e a regra entregava a ninguém."""
    sql = outbox._TARGETS_SQL
    inicio = sql.index("(select ur.contact_id from app.unit_responsible ur")
    sub = sql[inicio : sql.index("limit 1))")]
    assert "join app.contact rc on rc.id = ur.contact_id and rc.active" in sub
    assert sub.index("rc.active") < sub.index("order by ur.is_primary desc")


def test_targets_sql_le_so_a_identidade_vigente_do_contato_e_so_o_bot_pronto() -> None:
    sql = outbox._TARGETS_SQL
    lateral = sql[sql.index("left join lateral") : sql.index(") mi on true")]
    assert "from app.messaging_identity mi" in lateral
    assert "mi.revoked_at is null" in lateral
    assert "mi.contact_id = c.id" in lateral
    assert "mi.channel = %(telegram_channel)s" in lateral
    # Só o `external_id` sai da lateral — e sai com um nome que diz o que é.
    assert lateral.count("select") == 1 and "select mi.external_id" in lateral
    assert "mi.external_id as telegram_external_id" in sql

    inicio = sql.index("exists (select 1 from app.integration i")
    bot = sql[inicio : sql.index(") as telegram_ready")]
    assert "i.active" in bot
    assert "i.provider = any(%(telegram_providers)s)" in bot
    # PRONTO, não só ativo: o mesmo predicado de `fn_channel_readiness` — a
    # saúde do vigia em `connected`, por `join` (sem linha de saúde, não pronto).
    assert "join app.channel_health h on h.integration_id = i.id" in bot
    assert "h.status = %(telegram_health)s" in bot
    assert "left join app.channel_health" not in bot
    # Nenhum nome de provedor no texto: a lista vem da matriz, como parâmetro.
    for nome in capacidades.CHANNEL_PROVIDERS:
        assert f"'{nome}'" not in sql


# ---------------------------------------------------------------------------
# 3 e 4. `enqueue` inteira contra um banco que responde por instrução
# ---------------------------------------------------------------------------
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
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor = cursor

    async def __aenter__(self) -> FakeCursor:
        return self.cursor

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeDB:
    def __init__(self, *, alvos: list[dict[str, Any]], provider: str | None) -> None:
        self.alvos = alvos
        self.provider = provider
        self.targets_params: list[dict[str, Any]] = []
        self.enqueued: list[dict[str, Any]] = []

    def responder(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if "select provider from app.integration" in sql:
            return [{"provider": self.provider}] if self.provider else []
        if "from app.alert_rule r" in sql:
            self.targets_params.append(params)
            return list(self.alvos)
        if "from app.message_template" in sql:
            return [{"code": params["code"], "variables": ["unit", "link"]}]
        if "insert into app.alert_queue" in sql:
            self.enqueued.append(dict(params))
            return [{"id": uuid4()}]
        raise AssertionError(f"instrução inesperada: {sql[:60]}")


def _db(monkeypatch: pytest.MonkeyPatch, estado: FakeDB) -> FakeDB:
    monkeypatch.setattr(
        outbox, "tenant_scope", lambda context, schema="app": FakeScope(FakeCursor(estado, context))
    )
    return estado


async def _enqueue(estado: FakeDB) -> list[outbox.Queued]:
    return await outbox.enqueue(
        SystemContext(tenant_id=TENANT, task="teste"), [_ciclo()], base_url="https://app.x"
    )


@pytest.mark.anyio
async def test_both_vira_telegram_e_email_quando_ha_identidade_e_bot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    estado = _db(
        monkeypatch,
        FakeDB(
            alvos=[_alvo(channel="both", telegram_external_id=CHAT_ID, telegram_ready=True)],
            provider=WHATSAPP_PROVIDER,
        ),
    )

    enfileiradas = await _enqueue(estado)

    assert [q.channel for q in enfileiradas] == [TELEGRAM_CHANNEL, "email"]
    telegram, email = estado.enqueued
    assert (telegram["channel"], telegram["provider"], telegram["destination"]) == (
        TELEGRAM_CHANNEL,
        "telegram",
        CHAT_ID,
    )
    assert (email["channel"], email["provider"], email["destination"]) == ("email", "smtp", EMAIL)


@pytest.mark.anyio
async def test_sem_bot_pronto_a_identidade_nao_roteia(monkeypatch: pytest.MonkeyPatch) -> None:
    """O par do falso verde, pela `enqueue` inteira: identidade vigente, bot não
    pronto (inativo, ou ativo e `disconnected`, ou sem medição — a SQL não
    distingue, e é o que se quer)."""
    estado = _db(
        monkeypatch,
        FakeDB(
            alvos=[_alvo(channel="both", telegram_external_id=CHAT_ID, telegram_ready=False)],
            provider=WHATSAPP_PROVIDER,
        ),
    )

    enfileiradas = await _enqueue(estado)

    assert [q.channel for q in enfileiradas] == [WHATSAPP_CHANNEL, "email"]
    whatsapp = estado.enqueued[0]
    assert (whatsapp["provider"], whatsapp["destination"]) == (WHATSAPP_PROVIDER, PHONE)
    assert CHAT_ID not in str(estado.enqueued)


@pytest.mark.anyio
async def test_a_chave_de_idempotencia_e_a_mesma_por_telegram_e_por_whatsapp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mesma regra, o mesmo ciclo, o mesmo contato: quem aderiu entre duas
    execuções recebe UMA mensagem, não uma por canal."""
    por_whatsapp = _db(
        monkeypatch, FakeDB(alvos=[_alvo(telegram_ready=True)], provider=WHATSAPP_PROVIDER)
    )
    c = _ciclo()
    await outbox.enqueue(SystemContext(tenant_id=TENANT, task="teste"), [c], base_url="https://x")
    por_telegram = _db(
        monkeypatch,
        FakeDB(
            alvos=[_alvo(telegram_external_id=CHAT_ID, telegram_ready=True)],
            provider=WHATSAPP_PROVIDER,
        ),
    )
    await outbox.enqueue(SystemContext(tenant_id=TENANT, task="teste"), [c], base_url="https://x")

    (a,) = por_whatsapp.enqueued
    (b,) = por_telegram.enqueued
    assert (a["channel"], b["channel"]) == (WHATSAPP_CHANNEL, TELEGRAM_CHANNEL)
    assert a["idempotency_key"] == b["idempotency_key"]
    assert PHONE not in a["idempotency_key"] and CHAT_ID not in b["idempotency_key"]
    assert str(CONTACT) in a["idempotency_key"]


@pytest.mark.anyio
async def test_enqueue_pergunta_a_identidade_pelo_canal_e_o_bot_pela_matriz(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    estado = _db(monkeypatch, FakeDB(alvos=[], provider=None))

    await _enqueue(estado)

    (params,) = estado.targets_params
    assert params["telegram_channel"] == TELEGRAM_CHANNEL
    assert params["telegram_providers"] == list(providers_of(TELEGRAM_CHANNEL))
    assert params["telegram_health"] == HEALTH_CONNECTED == "connected"
    assert params["unit_id"] == UNIT and params["tenant_id"] == TENANT


@pytest.mark.anyio
async def test_nenhuma_linha_de_relatorio_carrega_o_destino(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    estado = _db(
        monkeypatch,
        FakeDB(
            alvos=[
                _alvo(channel="both", telegram_external_id=CHAT_ID, telegram_ready=True),
                _alvo(rule_id=uuid4(), contact_id=uuid4(), whatsapp="+5511888888888"),
            ],
            provider=WHATSAPP_PROVIDER,
        ),
    )

    enfileiradas = await _enqueue(estado)
    texto = outbox.relatorio(enfileiradas)

    assert not hasattr(enfileiradas[0], "destination")
    assert texto == "3 mensagem(ns) na fila · email 1 · telegram 1 · whatsapp 1"
    for segredo in (CHAT_ID, PHONE, "+5511888888888", EMAIL):
        assert segredo not in texto
    assert outbox.relatorio([]) == "0 mensagem(ns) na fila"
    # E o `__main__` que imprime a fila não conhece a palavra.
    fonte = (Path(outbox.__file__).parent / "__main__.py").read_text(encoding="utf-8")
    assert "destination" not in fonte and "outbox.relatorio(" in fonte
