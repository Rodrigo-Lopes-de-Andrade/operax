"""O ciclo, a fila e o remetente — e as três coisas que não podem falhar calado.

Um desvio em exatamente um ciclo, uma mensagem entregue exatamente uma vez, e
nenhuma mensagem antes do gate G4. As duas primeiras são cláusulas de SQL e estão
conferidas no texto do statement; a terceira é uma pergunta ao banco, e está
conferida em `tests/test_alertas_sender.py`, rodando o remetente contra um banco
que responde as duas respostas. O roteamento por pessoa (C5) está em
`tests/test_alertas_outbox.py`.
"""

from __future__ import annotations

import inspect
from datetime import date
from uuid import UUID, uuid4

import pytest

from operax.alertas import ciclo, outbox, sender
from operax.alertas.provedores.base import Message, NullProvider, render
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


def test_a_chave_de_idempotencia_muda_com_o_conteudo_e_o_contato_nao_com_a_rota():
    """A chave nomeia regra, período, contato e metade da regra. O destino ficou
    de fora de propósito (C5): a rota é atributo, e a pessoa que adere ao
    Telegram entre duas execuções não pode transformar uma mensagem em duas."""
    c = _ciclo()
    base = outbox.facts(c, base_url="https://x")
    outro = {**base, "total_events": "8"}
    contato, outro_contato = uuid4(), uuid4()

    assert outbox._key(RULE, c, contato, "whatsapp", base) == outbox._key(
        RULE, c, contato, "whatsapp", base
    )
    assert outbox._key(RULE, c, contato, "whatsapp", base) != outbox._key(
        RULE, c, contato, "whatsapp", outro
    )
    assert outbox._key(RULE, c, contato, "whatsapp", base) != outbox._key(
        RULE, c, outro_contato, "whatsapp", base
    )
    # As duas metades de `both` são duas mensagens para o mesmo contato.
    assert outbox._key(RULE, c, contato, "whatsapp", base) != outbox._key(
        RULE, c, contato, "email", base
    )
    # E a assinatura não aceita destino: não há como a rota entrar na chave.
    assert "destination" not in inspect.signature(outbox._key).parameters


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
    # A segunda metade, desde 11/09/2026: promover o motor deixou de ser "a sombra
    # fechou". A liberação é uma linha, e uma linha revogada não conta.
    assert "from app.alert_release" in sender._GATE_SQL
    assert "revoked_at is null" in sender._GATE_SQL
