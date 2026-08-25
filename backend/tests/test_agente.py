"""O catálogo fechado — as quatro recusas e o que nunca chega perto do SQL.

A regra 9 do projeto diz "nada de text-to-SQL". Ela não é uma instrução de
prompt: é o fato de o modelo devolver um `code` e um dicionário, e de tudo entre
isso e o banco viver aqui. O que estes testes cercam é o "entre".
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from operax.agente import catalogo
from operax.agente.catalogo import Choice, Metric, Refusal, build, choose

DESVIOS = Metric(
    code="daily_trend",
    title="Tendência diária de desvios",
    description="Série por dia",
    target="vw_deviation_daily_trend",
    dimensions=("unit",),
    filters=("start_date", "end_date"),
    domain=None,
)
FOLHA = Metric(
    code="payroll_summary",
    title="Resumo da folha",
    description="Valor total",
    target="vw_payroll_summary",
    dimensions=("company", "unit", "payroll_period"),
    filters=("year", "month"),
    domain="compensation",
)
RANKING = Metric(
    code="ranking_by_employee",
    title="Ranking",
    description="Ordenado",
    target="fn_ranking_by_employee",
    dimensions=("employee", "unit"),
    filters=("start_date", "end_date"),
    domain=None,
)
CATALOGO = (DESVIOS, FOLHA, RANKING)
PERIODO = {"start_date": "2026-08-01", "end_date": "2026-08-24"}
TUDO = frozenset({"pii", "compensation", "health", "disciplinary"})


# ---------------------------------------------------------------------------
# As cinco recusas
# ---------------------------------------------------------------------------
def test_metrica_fora_do_catalogo_e_recusada_com_a_lista_do_que_existe():
    """ "Não sei responder isso" não ensina nada; a lista ensina a próxima pergunta."""
    resposta = choose(CATALOGO, "custo_por_hora", PERIODO, domains=TUDO)

    assert isinstance(resposta, Refusal)
    assert resposta.code == "fora_do_catalogo"
    assert "daily_trend" in resposta.reason


def test_metrica_de_dominio_fora_de_alcance_e_recusada():
    resposta = choose(CATALOGO, "payroll_summary", {"year": 2026, "month": 8}, domains=frozenset())

    assert isinstance(resposta, Refusal)
    assert resposta.code == "sem_dominio"


def test_parametro_que_a_metrica_nao_aceita_e_recusado_pelo_nome():
    resposta = choose(CATALOGO, "daily_trend", {**PERIODO, "cargo": "x"}, domains=TUDO)

    assert isinstance(resposta, Refusal)
    assert resposta.code == "parametro_desconhecido"
    assert "cargo" in resposta.reason


def test_periodo_ausente_e_recusado_em_vez_de_varrer_o_historico():
    resposta = choose(CATALOGO, "daily_trend", {"unit": "u1"}, domains=TUDO)

    assert isinstance(resposta, Refusal)
    assert resposta.code == "filtro_ausente"
    assert "start_date" in resposta.reason and "end_date" in resposta.reason


def test_valor_que_nao_e_do_tipo_do_parametro_e_recusado_nomeando_o_valor():
    """O nome do parâmetro está certo e o valor não é um identificador.

    Foi o que o modelo real fez na primeira execução do agente: para "quantos
    desvios tivemos este mês?" ele mandou `unit="month"`. As outras quatro
    recusas passam por isso — `unit` é dimensão que a métrica aceita — e a
    string chegaria a uma coluna `uuid`.
    """
    resposta = choose(CATALOGO, "daily_trend", {**PERIODO, "unit": "month"}, domains=TUDO)

    assert isinstance(resposta, Refusal)
    assert resposta.code == "valor_invalido"
    assert "month" in resposta.reason and "unit" in resposta.reason


def test_data_fora_do_formato_e_recusada_como_data():
    resposta = choose(
        CATALOGO, "daily_trend", {**PERIODO, "start_date": "01/08/2026"}, domains=TUDO
    )

    assert isinstance(resposta, Refusal)
    assert resposta.code == "valor_invalido"
    assert "start_date" in resposta.reason


def test_a_escolha_valida_passa_com_os_parametros_no_tipo_do_alvo():
    """A conversão é parte da aprovação: o que sai daqui já é do tipo da coluna."""
    unidade = UUID("33333333-3333-4333-8333-333333333333")

    resposta = choose(CATALOGO, "daily_trend", {**PERIODO, "unit": str(unidade)}, domains=TUDO)

    assert isinstance(resposta, Choice)
    assert resposta.metric is DESVIOS
    assert resposta.parameters == {
        "start_date": date(2026, 8, 1),
        "end_date": date(2026, 8, 24),
        "unit": unidade,
    }


# ---------------------------------------------------------------------------
# O que o modelo vê
# ---------------------------------------------------------------------------
def test_a_metrica_sensivel_nao_e_oferecida_a_quem_nao_alcanca_o_dominio():
    """Oferecer e recusar depois confirma que o dado existe para quem não pode saber."""
    visivel = catalogo.reachable(CATALOGO, frozenset())

    assert FOLHA not in visivel
    assert DESVIOS in visivel


def test_o_prompt_nao_carrega_nome_de_tabela_nem_de_coluna():
    """O modelo não precisa do schema para escolher — e o que ele não sabe não propõe."""
    texto = catalogo.describe(CATALOGO)

    assert "daily_trend" in texto
    for vazamento in (
        "vw_deviation_daily_trend",
        "vw_payroll_summary",
        "unit_id",
        "reference_date",
    ):
        assert vazamento not in texto


# ---------------------------------------------------------------------------
# Da escolha para a consulta
# ---------------------------------------------------------------------------
def test_nenhum_valor_entra_no_texto_da_consulta():
    """Tudo o que veio de fora viaja ligado. É a fronteira inteira da regra 9."""
    query = build(Choice(DESVIOS, {**PERIODO, "unit": "u1'; drop table app.employee--"}))

    assert "drop" not in query.sql
    assert "2026-08-01" not in query.sql
    assert query.parameters["unit"] == "u1'; drop table app.employee--"


def test_a_view_vira_where_e_a_funcao_vira_chamada_nomeada():
    view = build(Choice(DESVIOS, {**PERIODO, "unit": "u1"}))
    funcao = build(Choice(RANKING, {**PERIODO, "unit": "u1"}))

    assert view.sql.startswith("select * from public.vw_deviation_daily_trend where ")
    assert "reference_date >= %(start_date)s" in view.sql
    assert funcao.sql.startswith("select * from public.fn_ranking_by_employee(")
    assert "p_de => %(start_date)s" in funcao.sql


def test_a_dimensao_de_saida_nao_vira_argumento():
    """`employee` no ranking DE colaborador descreve o resultado, não filtra a entrada."""
    query = build(Choice(RANKING, {**PERIODO, "employee": "c1"}))

    assert "employee" not in query.parameters
    assert "p_de" in query.sql and "p_ate" in query.sql


def test_o_teto_de_linhas_e_do_codigo_e_nao_do_prompt():
    assert build(Choice(DESVIOS, PERIODO)).sql.endswith(f"limit {catalogo.MAX_ROWS}")


def test_parametro_sem_binding_e_erro_de_programa_e_nao_do_usuario():
    """Catálogo e código discordando não pode virar uma resposta errada."""
    inventada = Metric("x", "T", "D", "vw_deviation_daily_trend", ("inexistente",), (), None)

    with pytest.raises(catalogo.UnboundParameterError, match="inexistente"):
        build(Choice(inventada, {"inexistente": 1}))


def test_todo_alvo_do_mapa_declara_pelo_menos_o_periodo_ou_diz_por_que_nao():
    """Guarda de leitura: um alvo sem nenhum binding é um alvo esquecido."""
    for alvo, mapa in catalogo.BINDINGS.items():
        assert mapa, f"{alvo} não declara binding nenhum"
