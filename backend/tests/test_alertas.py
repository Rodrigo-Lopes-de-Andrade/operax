"""O ciclo, a fila e o remetente — e as três coisas que não podem falhar calado.

Um desvio em exatamente um ciclo, uma mensagem entregue exatamente uma vez, e
nenhuma mensagem antes do gate G4. As duas primeiras são cláusulas de SQL e estão
conferidas no texto do statement; a terceira é uma pergunta ao banco, e está
conferida rodando o remetente contra um banco que responde as duas respostas.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest

from operax.alertas import ciclo, outbox, sender
from operax.alertas.provedores.base import Delivery, Message, NullProvider, render
from operax.core.tenant import SystemContext, bind_tenant

TENANT = UUID("dddddddd-0000-0000-0000-000000000001")
UNIT = UUID("dddddddd-0000-0000-0000-00000000ac01")
RULE = UUID("dddddddd-0000-0000-0000-0000000000r1".replace("r", "a"))


def _ciclo(**kwargs) -> ciclo.Cycle:
    base = dict(
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


# ---------------------------------------------------------------------------
# Um desvio em exatamente um ciclo
# ---------------------------------------------------------------------------
def test_a_reserva_so_pega_quem_nao_esta_em_ciclo_nenhum():
    """É a cláusula inteira do "exatamente um". Sem ela, o mesmo desvio sai duas vezes."""
    assert "report_cycle_id is null" in ciclo._RESERVE_SQL
    assert "mode = 'production'" in ciclo._RESERVE_SQL
    assert "status = 'active'" in ciclo._RESERVE_SQL


def test_a_reserva_nao_tem_piso_de_data():
    """O desvio detectado tarde pertence ao dia D e ao ciclo C+1, e tem que entrar.

    Um `reference_date >= period_start` derrubaria exatamente as ocorrências que o
    gestor mais precisa ouvir — as que ninguém tinha visto ainda.
    """
    assert "reference_date <= %(ate)s::date" in ciclo._RESERVE_SQL
    assert "reference_date >=" not in ciclo._RESERVE_SQL


def test_todo_statement_do_ciclo_liga_o_tenant():
    for statement in (
        ciclo._UNITS_SQL,
        ciclo._CREATE_CYCLE_SQL,
        ciclo._RESERVE_SQL,
        ciclo._CLOSE_CYCLE_SQL,
        ciclo._DROP_EMPTY_SQL,
    ):
        bind_tenant(statement, {}, SystemContext(tenant_id=TENANT, task="teste"))


# ---------------------------------------------------------------------------
# A divergência declarada
# ---------------------------------------------------------------------------
def test_o_ciclo_declara_as_ocorrencias_de_dias_anteriores():
    """Sem essa frase o gestor abre o painel, vê outro número e conclui que o
    sistema está errado — e disso não se volta com explicação depois."""
    texto = _ciclo(from_previous_days=3).declaration

    assert texto == ("Inclui 3 ocorrências de dias anteriores detectadas após o último envio.")


def test_uma_ocorrencia_anterior_fala_no_singular():
    assert (
        "1 ocorrência de dias anteriores detectada após" in _ciclo(from_previous_days=1).declaration
    )


def test_sem_ocorrencia_anterior_nao_ha_o_que_declarar():
    assert _ciclo().declaration is None


# ---------------------------------------------------------------------------
# A fila
# ---------------------------------------------------------------------------
def test_o_link_abre_o_painel_ja_recortado():
    """O número da mensagem e o número da tela têm de ser a mesma consulta."""
    link = outbox.facts(_ciclo(), base_url="https://app.exemplo/")["link"]

    assert link == (f"https://app.exemplo/dashboard?un={UNIT}&de=2026-08-18&ate=2026-08-24")


def test_os_fatos_saem_como_texto_e_nunca_como_frase_pronta():
    """Regra 11: o provedor recebe variáveis, não uma sentença montada."""
    dados = outbox.facts(_ciclo(), base_url="https://x")

    assert dados["total_events"] == "7"
    assert dados["unit"] == "Centro"
    assert all(isinstance(v, str) for v in dados.values())


def test_a_chave_de_idempotencia_muda_com_o_conteudo():
    c = _ciclo()
    base = outbox.facts(c, base_url="https://x")
    outro = {**base, "total_events": "8"}

    assert outbox._key(RULE, c, "+5511999999999", base) == outbox._key(
        RULE, c, "+5511999999999", base
    )
    assert outbox._key(RULE, c, "+5511999999999", base) != outbox._key(
        RULE, c, "+5511999999999", outro
    )
    assert outbox._key(RULE, c, "+5511999999999", base) != outbox._key(
        RULE, c, "+5511888888888", base
    )


def test_reenfileirar_o_mesmo_nao_duplica():
    assert "on conflict (idempotency_key) do nothing" in outbox._ENQUEUE_SQL


# ---------------------------------------------------------------------------
# O contrato do provedor
# ---------------------------------------------------------------------------
def test_a_ordem_dos_valores_e_a_que_o_template_declarou():
    mensagem = Message(
        destination="+55",
        template="deviation_summary",
        variables=("unit", "total_events"),
        facts={"total_events": "7", "unit": "Centro"},
    )

    assert mensagem.ordered() == ["Centro", "7"]


def test_o_render_troca_o_placeholder_pelo_valor_declarado():
    mensagem = Message(
        destination="+55",
        template="t",
        variables=("unit", "total"),
        facts={"unit": "Centro", "total": "7"},
    )

    assert render("{{1}}: {{2}} ocorrências", mensagem) == "Centro: 7 ocorrências"


def test_placeholder_sem_valor_some_em_vez_de_sair_literal():
    """ "{{4}}" no meio de uma mensagem é pior do que uma lacuna."""
    mensagem = Message(destination="+55", template="t", variables=("unit",), facts={})

    assert render("{{1}} e {{4}}", mensagem) == " e "


@pytest.mark.anyio
async def test_o_provedor_nulo_registra_e_nao_entrega():
    nulo = NullProvider()
    entrega = await nulo.enviar(Message(destination="+55", template=None, variables=(), facts={}))

    assert entrega.status == "failed"
    assert "gate G4" in (entrega.error or "")
    assert len(nulo.sent) == 1


# ---------------------------------------------------------------------------
# O remetente
# ---------------------------------------------------------------------------
def test_a_fila_e_reservada_com_skip_locked():
    """É o que permite mais de um sender sem entrega duplicada."""
    assert "for update skip locked" in sender._CLAIM_SQL
    # E marcada `sending` na MESMA transação: uma linha lida e solta antes de ser
    # marcada é uma linha que dois senders pegam.
    assert "set status = 'sending'" in sender._CLAIM_SQL


def test_o_backoff_sobe_e_para():
    assert [sender._wait_minutes(n) for n in range(6)] == [1, 5, 15, 60, 360, 360]
    assert sender.MAX_ATTEMPTS == 5


def test_o_log_de_longo_prazo_nao_guarda_o_telefone():
    numero = "+5511999999999"

    assert numero not in sender.destination_hash(numero)
    assert len(sender.destination_hash(numero)) == 64


def test_o_gate_pergunta_ao_banco_em_vez_de_ler_uma_flag():
    assert "mode = 'production'" in sender._GATE_SQL
    assert "status = 'completed'" in sender._GATE_SQL


class FakeCursor:
    """Um banco endereçado por statement, com a fila em memória."""

    def __init__(self, estado: FakeDB, context: Any) -> None:
        self.estado = estado
        self.context = context
        self.linhas: list[dict[str, Any]] = []

    async def execute(self, statement: str, params: Any = None) -> None:
        bind_tenant(statement, params or {}, self.context)
        self.linhas = self.estado.responder(" ".join(statement.split()), params or {})

    async def fetchone(self):
        return self.linhas[0] if self.linhas else None

    async def fetchall(self):
        return self.linhas


class FakeScope:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor = cursor

    async def __aenter__(self) -> FakeCursor:
        return self.cursor

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeDB:
    def __init__(self, *, promovido: bool, fila: list[dict[str, Any]]) -> None:
        self.promovido = promovido
        self.fila = fila
        self.log: list[dict[str, Any]] = []
        self.marcadas: list[tuple[str, Any]] = []

    def responder(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if "from app.detection_run" in sql:
            return [{"promovido": self.promovido}]
        if "update app.alert_queue q" in sql:
            return list(self.fila)
        if "insert into app.alert_sent" in sql:
            self.log.append(dict(params))
            return []
        if "set status = 'sent'" in sql:
            self.marcadas.append(("sent", params["queue_id"]))
            return []
        if "then 'discarded' else 'failed'" in sql:
            final = "discarded" if params["max_attempts"] <= 1 else "failed"
            self.marcadas.append((final, params["queue_id"]))
            return [{"status": final}]
        if "from app.message_template" in sql:
            return [{"variables": ["unit"], "body": "{{1}}"}]
        return []


def _fila(**kwargs) -> dict[str, Any]:
    base = dict(
        id=uuid4(),
        rule_id=RULE,
        channel="whatsapp",
        destination="+5511999999999",
        payload={"unit": "Centro"},
        template_code="deviation_summary",
        provider="meta_cloud",
        attempts=0,
    )
    return {**base, **kwargs}


def _sender_db(monkeypatch: pytest.MonkeyPatch, estado: FakeDB) -> FakeDB:
    monkeypatch.setattr(
        sender, "tenant_scope", lambda context, schema="app": FakeScope(FakeCursor(estado, context))
    )
    return estado


class SpyProvider:
    name = "meta_cloud"

    def __init__(self) -> None:
        self.enviadas: list[Message] = []

    async def enviar(self, message: Message) -> Delivery:
        self.enviadas.append(message)
        return Delivery(status="sent", provider_message_id="wamid.1", cost_cents=4)


@pytest.mark.anyio
async def test_com_o_gate_aberto_nada_sai_da_fila(monkeypatch: pytest.MonkeyPatch):
    """A regra 8 é perguntada, não lembrada: sem execução em produção, ninguém entrega."""
    estado = _sender_db(monkeypatch, FakeDB(promovido=False, fila=[_fila()]))
    espiao = SpyProvider()

    resultado = await sender.dispatch(
        SystemContext(tenant_id=TENANT, task="teste"), {"meta_cloud": espiao}
    )

    assert resultado.gate_open is True
    assert resultado.sent == 0
    assert espiao.enviadas == []
    # E a tentativa fica registrada com o motivo — silêncio não é resultado.
    assert "gate G4 aberto" in estado.log[0]["error"]


@pytest.mark.anyio
async def test_com_o_motor_promovido_a_mensagem_sai(monkeypatch: pytest.MonkeyPatch):
    estado = _sender_db(monkeypatch, FakeDB(promovido=True, fila=[_fila()]))
    espiao = SpyProvider()

    resultado = await sender.dispatch(
        SystemContext(tenant_id=TENANT, task="teste"), {"meta_cloud": espiao}
    )

    assert (resultado.gate_open, resultado.sent, resultado.failed) == (False, 1, 0)
    assert espiao.enviadas[0].destination == "+5511999999999"
    assert espiao.enviadas[0].variables == ("unit",)
    # O custo entra desde o primeiro envio, e o telefone não vai para o log.
    assert estado.log[0]["cost_cents"] == 4
    assert estado.log[0]["destination_hash"] == sender.destination_hash("+5511999999999")
    assert "999999999" not in estado.log[0]["destination_hash"]


@pytest.mark.anyio
async def test_provedor_nao_configurado_volta_para_a_fila_com_o_motivo(
    monkeypatch: pytest.MonkeyPatch,
):
    estado = _sender_db(monkeypatch, FakeDB(promovido=True, fila=[_fila(provider="z_api")]))

    resultado = await sender.dispatch(SystemContext(tenant_id=TENANT, task="teste"), {})

    assert resultado.failed == 1
    assert "não configurado" in estado.log[0]["error"]
