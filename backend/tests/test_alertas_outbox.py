"""O roteamento por pessoa (SPEC-CANAIS §8): Telegram se houver identidade
vigente E bot ativo; WhatsApp caso contrário; e-mail intocado.

Cinco coisas, e o falso verde previsto para cada uma:

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
5. **A regra doente é pulada e nomeada, nunca fatal** (C7) — uma por regra,
   não uma por destino. O estado commitado que o `raise` deixava para trás só
   se vê pelo banco, e está em `scripts/85_teste_ciclo_mudo.py`.
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


class FakeDB:
    def __init__(
        self,
        *,
        alvos: list[dict[str, Any]],
        provider: str | None,
        sem_template: tuple[str, ...] = (),
        meta_status: str = "approved",
    ) -> None:
        self.alvos = alvos
        self.provider = provider
        #: Os códigos que `_TEMPLATE_FOR_CYCLE_SQL` não acha — apagado,
        #: desativado, ou nunca criado neste cliente. É como uma regra adoece
        #: depois de ligada.
        self.sem_template = sem_template
        #: O estado do template na Meta. `meta_cloud` só entrega `approved`, e
        #: quem recusa o resto é `util.validate_alert_template`, de dentro do
        #: insert — a C7 pergunta antes para poder PULAR em vez de estourar.
        self.meta_status = meta_status
        self.targets_params: list[dict[str, Any]] = []
        self.enqueued: list[dict[str, Any]] = []

    def responder(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if "select provider from app.integration" in sql:
            return [{"provider": self.provider}] if self.provider else []
        if "from app.alert_rule r" in sql:
            self.targets_params.append(params)
            return list(self.alvos)
        if "from app.message_template" in sql:
            if params["code"] in self.sem_template:
                return []
            return [
                {
                    "code": params["code"],
                    "variables": ["unit", "link"],
                    "meta_status": self.meta_status,
                }
            ]
        if "insert into app.alert_queue" in sql:
            self.enqueued.append(dict(params))
            return [{"id": uuid4()}]
        raise AssertionError(f"instrução inesperada: {sql[:60]}")


def _escopo(estado: FakeDB) -> FakeCursor:
    """O escopo entra por parâmetro desde o C7 — quem abre a transação é quem chama.

    Não há mais `tenant_scope` a estubar aqui: `enqueue` não abre transação
    nenhuma, e é isso que a torna a MESMA de `ciclo.assemble`.
    """
    return FakeCursor(estado, SystemContext(tenant_id=TENANT, task="teste"))


async def _enqueue(estado: FakeDB) -> outbox.Outbox:
    return await outbox.enqueue(_escopo(estado), [_ciclo()], base_url="https://app.x")


@pytest.mark.anyio
async def test_both_vira_telegram_e_email_quando_ha_identidade_e_bot() -> None:
    estado = FakeDB(
        alvos=[_alvo(channel="both", telegram_external_id=CHAT_ID, telegram_ready=True)],
        provider=WHATSAPP_PROVIDER,
    )

    resultado = await _enqueue(estado)

    assert [q.channel for q in resultado.queued] == [TELEGRAM_CHANNEL, "email"]
    telegram, email = estado.enqueued
    assert (telegram["channel"], telegram["provider"], telegram["destination"]) == (
        TELEGRAM_CHANNEL,
        "telegram",
        CHAT_ID,
    )
    assert (email["channel"], email["provider"], email["destination"]) == ("email", "smtp", EMAIL)


@pytest.mark.anyio
async def test_sem_bot_pronto_a_identidade_nao_roteia() -> None:
    """O par do falso verde, pela `enqueue` inteira: identidade vigente, bot não
    pronto (inativo, ou ativo e `disconnected`, ou sem medição — a SQL não
    distingue, e é o que se quer)."""
    estado = FakeDB(
        alvos=[_alvo(channel="both", telegram_external_id=CHAT_ID, telegram_ready=False)],
        provider=WHATSAPP_PROVIDER,
    )

    resultado = await _enqueue(estado)

    assert [q.channel for q in resultado.queued] == [WHATSAPP_CHANNEL, "email"]
    whatsapp = estado.enqueued[0]
    assert (whatsapp["provider"], whatsapp["destination"]) == (WHATSAPP_PROVIDER, PHONE)
    assert CHAT_ID not in str(estado.enqueued)


@pytest.mark.anyio
async def test_a_chave_de_idempotencia_e_a_mesma_por_telegram_e_por_whatsapp() -> None:
    """A mesma regra, o mesmo ciclo, o mesmo contato: quem aderiu entre duas
    execuções recebe UMA mensagem, não uma por canal."""
    por_whatsapp = FakeDB(alvos=[_alvo(telegram_ready=True)], provider=WHATSAPP_PROVIDER)
    c = _ciclo()
    await outbox.enqueue(_escopo(por_whatsapp), [c], base_url="https://x")
    por_telegram = FakeDB(
        alvos=[_alvo(telegram_external_id=CHAT_ID, telegram_ready=True)],
        provider=WHATSAPP_PROVIDER,
    )
    await outbox.enqueue(_escopo(por_telegram), [c], base_url="https://x")

    (a,) = por_whatsapp.enqueued
    (b,) = por_telegram.enqueued
    assert (a["channel"], b["channel"]) == (WHATSAPP_CHANNEL, TELEGRAM_CHANNEL)
    assert a["idempotency_key"] == b["idempotency_key"]
    assert PHONE not in a["idempotency_key"] and CHAT_ID not in b["idempotency_key"]
    assert str(CONTACT) in a["idempotency_key"]


@pytest.mark.anyio
async def test_enqueue_pergunta_a_identidade_pelo_canal_e_o_bot_pela_matriz() -> None:
    estado = FakeDB(alvos=[], provider=None)

    await _enqueue(estado)

    (params,) = estado.targets_params
    assert params["telegram_channel"] == TELEGRAM_CHANNEL
    assert params["telegram_providers"] == list(providers_of(TELEGRAM_CHANNEL))
    assert params["telegram_health"] == HEALTH_CONNECTED == "connected"
    assert params["unit_id"] == UNIT and params["tenant_id"] == TENANT


@pytest.mark.anyio
async def test_nenhuma_linha_de_relatorio_carrega_o_destino() -> None:
    estado = FakeDB(
        alvos=[
            _alvo(channel="both", telegram_external_id=CHAT_ID, telegram_ready=True),
            _alvo(rule_id=uuid4(), contact_id=uuid4(), whatsapp="+5511888888888"),
        ],
        provider=WHATSAPP_PROVIDER,
    )

    resultado = await _enqueue(estado)
    texto = outbox.relatorio(resultado)

    assert not hasattr(resultado.queued[0], "destination")
    assert texto == "3 mensagem(ns) na fila · email 1 · telegram 1 · whatsapp 1"
    for segredo in (CHAT_ID, PHONE, "+5511888888888", EMAIL):
        assert segredo not in texto
    assert outbox.relatorio(outbox.Outbox(queued=[], skipped=[])) == "0 mensagem(ns) na fila"
    # E o `__main__` que imprime a fila não conhece a palavra.
    fonte = (Path(outbox.__file__).parent / "__main__.py").read_text(encoding="utf-8")
    assert "destination" not in fonte and "outbox.relatorio(" in fonte


# ---------------------------------------------------------------------------
# 5. A regra doente é pulada e nomeada, nunca fatal (C7)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_a_regra_doente_e_pulada_e_nomeada_sem_calar_a_saudavel() -> None:
    """Uma regra que não consegue montar a mensagem cala a própria audiência.

    Antes do C7 ela levantava, e o `raise` derrubava a transação inteira: a
    regra de e-mail ao lado perdia a mensagem dela, e — porque a reserva já
    tinha commitado noutra transação — os desvios daquele dia ficavam presos
    num ciclo sem mensagem nenhuma, para sempre. O estado commitado está
    preso em `scripts/85_teste_ciclo_mudo.py`, contra o banco; aqui fica o que
    não precisa de banco: enfileirar não levanta, e quem ficou de fora tem
    nome, template e motivo.
    """
    saudavel = uuid4()
    estado = FakeDB(
        alvos=[
            _alvo(rule_name="Doente", template_code="nao_existe"),
            _alvo(
                rule_id=saudavel,
                contact_id=uuid4(),
                rule_name="Saudável",
                channel="email",
                template_code=None,
            ),
        ],
        provider=WHATSAPP_PROVIDER,
        sem_template=("nao_existe",),
    )

    resultado = await _enqueue(estado)

    assert [q.rule_name for q in resultado.queued] == ["Saudável"]
    assert [(s.rule_name, s.template_code) for s in resultado.skipped] == [("Doente", "nao_existe")]
    assert "não existe ou está inativo" in resultado.skipped[0].reason
    # E o relatório diz as duas coisas, sem nenhum destino no meio.
    texto = outbox.relatorio(resultado)
    assert texto.splitlines()[0] == "1 mensagem(ns) na fila · email 1"
    assert "regra 'Doente' ficou de fora" in texto
    for segredo in (PHONE, EMAIL, CHAT_ID):
        assert segredo not in texto


@pytest.mark.anyio
async def test_a_regra_doente_aparece_uma_vez_mesmo_com_varios_destinos() -> None:
    """Uma linha por REGRA: o template é atributo dela, e todo destino adoece junto.

    Repetir a mesma regra por contato faria o relatório dizer "três regras
    fora" onde há uma, e o número é o que decide se alguém vai consertar.
    """
    estado = FakeDB(
        alvos=[
            _alvo(rule_name="Doente", template_code="nao_existe", contact_id=uuid4()),
            _alvo(rule_name="Doente", template_code="nao_existe", contact_id=uuid4()),
        ],
        provider=WHATSAPP_PROVIDER,
        sem_template=("nao_existe",),
    )

    resultado = await _enqueue(estado)

    assert resultado.queued == []
    assert [s.rule_name for s in resultado.skipped] == ["Doente"]


@pytest.mark.anyio
async def test_o_template_reprovado_na_meta_e_pulado_como_os_outros_dois_motivos() -> None:
    """O terceiro motivo do gatilho — e o que faltava.

    `util.validate_alert_template` recusa o insert quando o provedor é o
    oficial e o template não está `approved`. Esse motivo é o único dos três
    que o Python não perguntava: a recusa vinha de dentro do `insert`, estourava
    a transação e derrubava o turno do cliente inteiro — que é exatamente o que
    a C7 existe para impedir. Agora ele é uma frase, como os outros dois.
    """
    doente, saudavel = uuid4(), uuid4()
    estado = FakeDB(
        alvos=[
            _alvo(rule_id=doente, rule_name="Doente", template_code="reprovado"),
            _alvo(
                rule_id=saudavel,
                contact_id=uuid4(),
                rule_name="Saudável",
                channel="email",
                template_code=None,
            ),
        ],
        provider=WHATSAPP_PROVIDER,
        meta_status="rejected",
    )

    resultado = await _enqueue(estado)

    assert [q.rule_name for q in resultado.queued] == ["Saudável"]
    assert [s.rule_name for s in resultado.skipped] == ["Doente"]
    assert "'rejected' na Meta" in resultado.skipped[0].reason
    for segredo in (PHONE, EMAIL, CHAT_ID):
        assert segredo not in outbox.relatorio(resultado)


@pytest.mark.anyio
async def test_o_provedor_nao_oficial_entrega_template_que_a_meta_nao_aprovou() -> None:
    """A pergunta é a do gatilho, e o gatilho só recusa o oficial.

    Pular aqui o que o banco aceitaria seria a tela mentir ao contrário:
    a regra pararia de entregar por uma regra que não existe. Quem decide é a
    matriz de capacidades (`requires_templates`), nunca o nome do provedor.
    """
    nao_oficial = next(
        p
        for p in capacidades.WHATSAPP_PROVIDERS
        if not capacidades.capabilities_for(p).requires_templates
    )
    estado = FakeDB(
        alvos=[_alvo(rule_name="Pendente na Meta")],
        provider=nao_oficial,
        meta_status="pending",
    )

    resultado = await _enqueue(estado)

    assert [q.rule_name for q in resultado.queued] == ["Pendente na Meta"]
    assert resultado.skipped == []


@pytest.mark.anyio
async def test_a_regra_sem_destino_no_canal_e_pulada_e_nomeada_em_vez_de_sumir() -> None:
    """Era um `continue` mudo: nem fila, nem `Skipped`, nem log.

    O ciclo era desfeito "sem culpado" e o turno seguinte repetia, para sempre,
    sem ninguém saber que a regra existia. `ligar` não exige que o contato tenha
    o canal da regra, então o estado é alcançável pela tela.
    """
    estado = FakeDB(
        alvos=[_alvo(rule_name="Sem número", whatsapp=None, template_code=None)],
        provider=WHATSAPP_PROVIDER,
    )

    resultado = await _enqueue(estado)

    assert resultado.queued == []
    assert [s.rule_name for s in resultado.skipped] == ["Sem número"]
    assert "não tem por onde receber" in resultado.skipped[0].reason
    # O motivo não nomeia o contato: o relatório e o log não carregam destino.
    for segredo in (PHONE, EMAIL, CHAT_ID):
        assert segredo not in resultado.skipped[0].reason


@pytest.mark.anyio
async def test_o_aviso_da_regra_pulada_sai_uma_vez_por_regra(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Dois destinos, um aviso. Num cliente com trinta unidades e cadência de
    quinze minutos, repetir por destino e por ciclo é ruído que esconde o resto."""
    estado = FakeDB(
        alvos=[
            _alvo(rule_name="Doente", template_code="nao_existe", contact_id=uuid4()),
            _alvo(rule_name="Doente", template_code="nao_existe", contact_id=uuid4()),
        ],
        provider=WHATSAPP_PROVIDER,
        sem_template=("nao_existe",),
    )

    with caplog.at_level("WARNING", logger="operax.alertas.outbox"):
        await _enqueue(estado)

    avisos = [r for r in caplog.records if "ficou de fora" in r.getMessage()]
    assert len(avisos) == 1
    for segredo in (PHONE, EMAIL, CHAT_ID):
        assert segredo not in avisos[0].getMessage()
