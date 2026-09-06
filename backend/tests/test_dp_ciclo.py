"""O gate do S3: a falta é exercitada por fixture, e a conta nunca sai em JSON.

⛔ POR QUE A FALTA É SINTÉTICA, E ISSO NÃO É PREGUIÇA
Medido em 06/09/2026 antes do despacho: staging está vazio, produção tem 176
colaboradores e **zero** `app.leave_period`, e o espelho tem **UMA** falta em 26
meses de história. O gate original — "apuração de um mês real confere com o
legado linha a linha" — compararia zero faltas contra zero faltas e passaria sem
provar a única regra que a `SPEC-DP.md` §1e chama de mais perigosa. Então a regra
de falta é construída aqui, caso a caso.

⛔ E A RECONCILIAÇÃO CONTRA O LEGADO CONTINUA ABERTA
Não há export do mês fechado do cliente no repositório. Este arquivo prova o
mecanismo; ele **não** fecha o "linha a linha", e inventar um "legado" sintético
para comparar seria auto-consistência disfarçada de reconciliação.

A PERGUNTA DO FALSO VERDE, APLICADA AQUI
"A justificativa não curada falha alto" é satisfeito por um código que falha alto
em TUDO. Por isso cada recusa vem com o par positivo ao lado: `FÉRIAS` curada
passa e não conta, `ATESTED` curada passa e não conta, e a apuração inteira roda
verde quando a curadoria está completa. Uma trava que barra o legítimo é pior que
a ausência dela.

O QUE O FAKE **NÃO** PROVA, E ONDE ISSO É PROVADO
`FakeDB` modela o filtro por tenant e o `unique (cycle_id, employee_id)`, e falha
alto quando o código os viola. Quem prova que o ciclo gerado recusa `update` é a
prova viva de `20260906131252_dp_benefit_cycle.sql`, contra Postgres de verdade —
esta suíte não abre banco e não tenta substituí-la.
"""

from __future__ import annotations

import inspect
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from psycopg import errors

from operax.core.tenant import bind_tenant
from operax.dp import banking, beneficios, ciclo, export
from operax.rh import repository as rh_repository
from tests.conftest import TENANT_ID

OUTRO_TENANT = UUID("33333333-3333-4333-8333-000000000003")

ANA = UUID("aaaa0000-0000-4000-8000-000000000001")
BRUNO = UUID("aaaa0000-0000-4000-8000-000000000002")

UNIDADE = UUID("bbbb0000-0000-4000-8000-000000000001")

#: A competência de referência de todo este arquivo: setembro de 2026.
#: VT   -> janela 21/08 a 20/09, faltas contadas em JULHO.
#: Cesta -> janela 01/09 a 30/09, faltas contadas em AGOSTO.
ANO, MES = 2026, 9
VT_INICIO, VT_FIM = date(2026, 8, 21), date(2026, 9, 20)
CESTA_INICIO, CESTA_FIM = date(2026, 9, 1), date(2026, 9, 30)
JULHO = (date(2026, 7, 1), date(2026, 7, 31))
AGOSTO = (date(2026, 8, 1), date(2026, 8, 31))


# ---------------------------------------------------------------------------
# Fixtures sintéticas — as linhas como o `select` as devolve
# ---------------------------------------------------------------------------
def pessoa(
    employee_id: UUID = ANA,
    nome: str = "Ana Ribeiro",
    *,
    hired_on: date | None = None,
    terminated_on: date | None = None,
    registro: str | None = "1001",
) -> dict[str, Any]:
    return {
        "employee_id": employee_id,
        "name": nome,
        "registration_number": registro,
        "unit_id": UNIDADE,
        "unit_name": "Shopping Norte",
        "hired_on": hired_on,
        "terminated_on": terminated_on,
    }


def afastamento(
    justificativa: str | None,
    inicio: date,
    fim: date,
    *,
    employee_id: UUID = ANA,
) -> dict[str, Any]:
    """Uma linha crua de `secullum."FuncionarioAfastamento"` — texto livre inclusive."""
    return {
        "employee_id": employee_id,
        "starts_on": inicio,
        "ends_on": fim,
        "justification": justificativa,
    }


def curadoria(**pares: str) -> dict[str, dict[str, Any]]:
    """`{'FALTA': 'unjustified_absence'}` -> o mapa como o `select` o devolve, validado."""
    return {
        chave: {
            "justification": chave,
            "category": categoria,
            "validated_at": datetime(2026, 9, 1, 12, 0),
        }
        for chave, categoria in pares.items()
    }


def escala(
    inicio: date, fim: date, *, employee_id: UUID = ANA, folgas: frozenset[int] = frozenset({5, 6})
) -> list[dict[str, Any]]:
    """`app.expected_workday` de um vínculo, com folga por dia da semana.

    O padrão é sábado e domingo — não porque o produto conheça "dia útil", mas
    porque é a fixture mais legível. O 12x36 é exercitado por
    `test_escala_de_fim_de_semana_conta_como_dia_base`, que é justamente o caso
    que um calendário de segunda a sexta erraria.
    """
    dias = (fim - inicio).days + 1
    linhas = []
    for i in range(dias):
        dia = inicio + timedelta(days=i)
        linhas.append(
            {
                "employee_id": employee_id,
                "reference_date": dia,
                "day_type": "day_off" if dia.weekday() in folgas else "work",
            }
        )
    return linhas


def atribuicao(
    fare_code: str = "302",
    *,
    employee_id: UUID = ANA,
    desde: date = date(2026, 1, 1),
    ate: date | None = None,
) -> dict[str, Any]:
    return {
        "employee_id": employee_id,
        "effective_from": desde,
        "effective_to": ate,
        "fare_code": fare_code,
    }


def tarifas(*pares: tuple[str, str, str]) -> dict[str, dict[str, Decimal]]:
    """`("302", "single", "4.25")` -> o mapa que `compute_transport_cycle` recebe."""
    saida: dict[str, dict[str, Decimal]] = {}
    for code, kind, valor in pares:
        saida.setdefault(code, {})[kind] = Decimal(valor)
    return saida


def uma(linhas: tuple[ciclo.EntitlementLine, ...]) -> ciclo.EntitlementLine:
    assert len(linhas) == 1, f"esperava uma linha, vieram {len(linhas)}"
    return linhas[0]


# ---------------------------------------------------------------------------
# 1. O calendário — os três números que a tela declara
# ---------------------------------------------------------------------------
def test_janela_do_vt_e_21_do_mes_anterior_ate_20_do_mes_de_referencia() -> None:
    assert ciclo.cycle_window(ciclo.TRANSPORT_VOUCHER, 2026, 9) == (VT_INICIO, VT_FIM)


def test_janela_do_vt_atravessa_o_ano() -> None:
    """Janeiro puxa 21 de dezembro do ano anterior — o caso que um `month - 1` erra."""
    assert ciclo.cycle_window(ciclo.TRANSPORT_VOUCHER, 2026, 1) == (
        date(2025, 12, 21),
        date(2026, 1, 20),
    )


def test_janela_da_cesta_e_o_mes_civil_inteiro() -> None:
    assert ciclo.cycle_window(ciclo.FOOD_BASKET, 2026, 2) == (date(2026, 2, 1), date(2026, 2, 28))
    assert ciclo.cycle_window(ciclo.FOOD_BASKET, 2024, 2) == (date(2024, 2, 1), date(2024, 2, 29))


def test_mes_da_falta_e_o_mes_civil_anterior_ao_inicio_do_periodo() -> None:
    """⛔ O CORAÇÃO DA JANELA, E ONDE A LEITURA ERRADA É PLAUSÍVEL.

    A janela do VT começa em 21/08. O mês civil *anterior ao início do período* é
    **julho**, não agosto: agosto ainda está correndo em 21/08, e contá-lo
    contaria dias que estão DENTRO da própria janela — a mesma falta reduzindo
    dias líquidos duas vezes.

    A cesta cai na mesma regra e dá outra resposta certa: o período dela começa
    em 01/09, e o mês inteiramente anterior é agosto.
    """
    assert ciclo.absence_month(VT_INICIO) == JULHO
    assert ciclo.absence_month(CESTA_INICIO) == AGOSTO


def test_kind_desconhecido_nao_inventa_janela() -> None:
    with pytest.raises(ciclo.UnknownCycleKindError):
        ciclo.cycle_window("vale_alimentacao", 2026, 9)


# ---------------------------------------------------------------------------
# 2. A curadoria — string não curada NÃO entra em cálculo
# ---------------------------------------------------------------------------
def test_justificativa_fora_do_mapa_para_a_apuracao_e_diz_qual() -> None:
    """⛔ A RECUSA MAIS IMPORTANTE DESTA ETAPA.

    A alternativa — tratar o desconhecido como "não é falta" — dá vale transporte
    e cesta a quem faltou. A mensagem carrega a string literal porque é ela que a
    pessoa vai procurar na tela de curadoria.
    """
    with pytest.raises(ciclo.UncuratedJustificationError) as recusa:
        ciclo.resolve_absence_days(
            [afastamento("ATEST M", date(2026, 7, 6), date(2026, 7, 7))],
            curadoria(FALTA="unjustified_absence"),
            *JULHO,
        )
    assert "ATEST M" in str(recusa.value)


def test_justificativa_mapeada_e_nao_validada_para_a_apuracao() -> None:
    """Classificação provisória não entra em cálculo de dinheiro.

    É mais estreito que `app.payroll_event_map`, e de propósito: lá o indicador
    sai com aviso, aqui alguém recebe a mais e não reclama.
    """
    provisoria = {
        "ATESTED": {"justification": "ATESTED", "category": "leave_period", "validated_at": None}
    }
    with pytest.raises(ciclo.UncuratedJustificationError) as recusa:
        ciclo.resolve_absence_days(
            [afastamento("Atested", date(2026, 7, 6), date(2026, 7, 7))], provisoria, *JULHO
        )
    assert "ATESTED" in str(recusa.value)
    assert "validou" in str(recusa.value)


@pytest.mark.parametrize("vazia", [None, "", "   "])
def test_afastamento_sem_justificativa_para_a_apuracao(vazia: str | None) -> None:
    """Não dá para curar o que não tem nome — e chamá-lo de "não é falta" paga a mais."""
    with pytest.raises(ciclo.UncuratedJustificationError):
        ciclo.resolve_absence_days(
            [afastamento(vazia, date(2026, 7, 6), date(2026, 7, 7))], curadoria(), *JULHO
        )


def test_duas_grafias_do_mesmo_conceito_sao_duas_curadorias() -> None:
    """⛔ `Atested` e `ATEST M` são o mesmo conceito truncado em 7 caracteres.

    A curadoria TOLERA isso sem ADIVINHAR: as duas entram como duas linhas. Com as
    duas classificadas ninguém perde nada; com só uma, a outra para a apuração
    pelo nome dela — que é o oposto de o produto deduzir semelhança de texto.
    """
    leaves = [
        afastamento("Atested", date(2026, 7, 6), date(2026, 7, 7)),
        afastamento("ATEST M", date(2026, 7, 8), date(2026, 7, 9)),
    ]
    completa = curadoria(ATESTED="leave_period", **{"ATEST M": "leave_period"})
    assert ciclo.resolve_absence_days(leaves, completa, *JULHO) == {}

    with pytest.raises(ciclo.UncuratedJustificationError) as recusa:
        ciclo.resolve_absence_days(leaves, curadoria(ATESTED="leave_period"), *JULHO)
    assert "ATEST M" in str(recusa.value)


def test_a_busca_ignora_caixa_e_espaco_e_nao_ignora_acento() -> None:
    """Canonicalização é `upper(btrim)`, a mesma do `check` do banco.

    Acento não é normalizado: 'FÉRIAS' e 'FERIAS' são strings diferentes e cada
    uma se cura sozinha. Normalizar acento seria adivinhar que são a mesma coisa
    — e adivinhar é o que a curadoria existe para não fazer.
    """
    assert ciclo.canonical_justification("  Férias ") == "FÉRIAS"
    with pytest.raises(ciclo.UncuratedJustificationError) as recusa:
        ciclo.resolve_absence_days(
            [afastamento("Ferias", date(2026, 7, 6), date(2026, 7, 7))],
            curadoria(**{"FÉRIAS": "vacation"}),
            *JULHO,
        )
    assert "FERIAS" in str(recusa.value)


def test_categoria_que_nao_e_falta_nao_conta() -> None:
    """O par positivo: um código que recusasse tudo passaria nas recusas acima."""
    leaves = [
        afastamento("Férias", date(2026, 7, 1), date(2026, 7, 20)),
        afastamento("AFASTAD", date(2026, 7, 21), date(2026, 7, 25)),
    ]
    mapa = curadoria(**{"FÉRIAS": "vacation", "AFASTAD": "leave_of_absence"})
    assert ciclo.resolve_absence_days(leaves, mapa, *JULHO) == {}


def test_falta_conta_so_os_dias_dentro_do_mes_apurado() -> None:
    """O afastamento atravessa a virada do mês; só a parte dele em julho conta."""
    dias = ciclo.resolve_absence_days(
        [afastamento("FALTA", date(2026, 6, 28), date(2026, 7, 3))],
        curadoria(FALTA="unjustified_absence"),
        *JULHO,
    )
    assert dias[ANA] == {date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)}


def test_a_mesma_falta_nas_duas_fontes_conta_uma_vez() -> None:
    """⛔ A UNIÃO É POR DIA, E É POR ISSO QUE ELA É UM `set`.

    Quando a promoção do espelho para `app.leave_period` existir, o mesmo
    afastamento estará nos dois lugares. Somar contagens cobraria dois dias do
    colaborador por um dia que ele faltou.
    """
    do_espelho = ciclo.resolve_absence_days(
        [afastamento("FALTA", date(2026, 7, 6), date(2026, 7, 7))],
        curadoria(FALTA="unjustified_absence"),
        *JULHO,
    )
    do_dominio = {ANA: {date(2026, 7, 6), date(2026, 7, 7)}}
    assert len(ciclo.merge_absence_days(do_espelho, do_dominio)[ANA]) == 2


def test_fontes_diferentes_somam_dias_diferentes() -> None:
    """O par positivo da união: dias distintos continuam somando."""
    junto = ciclo.merge_absence_days(
        {ANA: {date(2026, 7, 6)}}, {ANA: {date(2026, 7, 7)}}, {BRUNO: {date(2026, 7, 8)}}
    )
    assert len(junto[ANA]) == 2
    assert len(junto[BRUNO]) == 1


# ---------------------------------------------------------------------------
# 3. Cesta — as duas causas, e o `reason` diz qual
# ---------------------------------------------------------------------------
def cesta(pessoas: list[dict[str, Any]], faltas: dict[UUID, set[date]] | None = None):
    return ciclo.compute_basket_cycle(CESTA_INICIO, CESTA_FIM, pessoas, faltas or {}, AGOSTO[0])


def test_cesta_com_direito_nao_tem_motivo() -> None:
    linha = uma(cesta([pessoa(hired_on=date(2020, 1, 1))]))
    assert linha.entitled
    assert linha.reason is None
    # ⛔ As colunas de dias ficam NULAS para cesta: ela não tem janela nem dias.
    assert (linha.days_base, linha.absences_prior, linha.net_days) == (None, None, None)
    assert linha.total_amount is None


def test_cesta_perde_por_falta_injustificada_e_o_motivo_diz_quantas() -> None:
    linha = uma(
        cesta(
            [pessoa(hired_on=date(2020, 1, 1))],
            {ANA: {date(2026, 8, 12), date(2026, 8, 13)}},
        )
    )
    assert not linha.entitled
    assert "2 falta" in linha.reason
    assert "08/2026" in linha.reason


def test_cesta_perde_por_admissao_depois_do_inicio_do_periodo() -> None:
    linha = uma(cesta([pessoa(hired_on=date(2026, 9, 10))]))
    assert not linha.entitled
    assert "10/09/2026" in linha.reason
    assert "admitido" in linha.reason.lower()


def test_admitido_no_primeiro_dia_do_periodo_mantem_a_cesta() -> None:
    """A regra é "DEPOIS do início", e o limite é onde ela erra sem sintoma."""
    assert uma(cesta([pessoa(hired_on=CESTA_INICIO)])).entitled


def test_cesta_com_as_duas_causas_nomeia_a_admissao() -> None:
    """Quem entrou depois do início não estava na casa no mês contado.

    A admissão explica a outra causa, então é ela que o `reason` grava — e a
    pessoa que perguntar recebe o motivo que resolve, não o que confunde.
    """
    linha = uma(cesta([pessoa(hired_on=date(2026, 9, 10))], {ANA: {date(2026, 8, 12)}}))
    assert "10/09/2026" in linha.reason
    assert "falta" not in linha.reason.lower()


# ---------------------------------------------------------------------------
# 4. Vale transporte — dias líquidos e total
# ---------------------------------------------------------------------------
def vt(
    pessoas: list[dict[str, Any]],
    escalas: list[dict[str, Any]],
    *,
    faltas: dict[UUID, set[date]] | None = None,
    fares: dict[str, dict[str, Decimal]] | None = None,
    atribuicoes: dict[UUID, list[str]] | None = None,
):
    por_pessoa: dict[UUID, dict[date, str]] = {}
    for linha in escalas:
        por_pessoa.setdefault(linha["employee_id"], {})[linha["reference_date"]] = linha["day_type"]
    return ciclo.compute_transport_cycle(
        VT_INICIO,
        VT_FIM,
        pessoas,
        por_pessoa,
        faltas or {},
        JULHO[0],
        fares or tarifas(("302", "single", "4.25"), ("302", "round_trip", "8.50")),
        atribuicoes or {ANA: ["302"]},
    )


def test_vt_dias_liquidos_e_total() -> None:
    """`net_days = days_base − absences_prior` e `total = net_days × ida-e-volta`."""
    linha = uma(
        vt(
            [pessoa(hired_on=date(2020, 1, 1))],
            escala(VT_INICIO, VT_FIM),
            faltas={ANA: {date(2026, 7, 6), date(2026, 7, 7)}},
        )
    )
    # 21/08 a 20/09 de 2026 tem 21 dias de segunda a sexta.
    assert linha.days_base == 21
    assert linha.absences_prior == 2
    assert linha.net_days == 19
    assert linha.unit_amount == Decimal("4.25")
    assert linha.round_trip_amount == Decimal("8.50")
    assert linha.total_amount == Decimal("161.50")
    assert linha.entitled


def test_o_total_nao_e_arredondado_porque_e_exato() -> None:
    """⛔ Inteiro × duas casas é exato. Um `quantize` aqui seria a regra de
    arredondamento da folha escrita uma segunda vez, longe de `beneficios._money`.
    """
    linha = uma(
        vt(
            [pessoa(hired_on=date(2020, 1, 1))],
            escala(VT_INICIO, VT_FIM),
            fares=tarifas(("302", "single", "0.01"), ("302", "round_trip", "0.03")),
        )
    )
    assert linha.total_amount == Decimal("0.63")
    assert linha.total_amount == linha.round_trip_amount * linha.net_days


def test_escala_de_fim_de_semana_conta_como_dia_base() -> None:
    """⛔ O CASO QUE UM CALENDÁRIO DE SEGUNDA A SEXTA ERRARIA.

    Quem faz 12x36 trabalha sábado e domingo. `days_base` vem de
    `app.expected_workday`, que é a escala materializada da pessoa — contar dias
    úteis do calendário pagaria VT de menos a quem cobre o fim de semana, todo
    mês, calado.
    """
    so_fim_de_semana = escala(VT_INICIO, VT_FIM, folgas=frozenset({0, 1, 2, 3, 4}))
    linha = uma(vt([pessoa(hired_on=date(2020, 1, 1))], so_fim_de_semana))
    assert linha.days_base == 10
    assert linha.net_days == 10


def test_admissao_no_meio_do_periodo_reduz_os_dias_base() -> None:
    """E reduz **sem regra própria**: o recorte do vínculo já faz isso.

    Uma exceção escrita dentro da soma seria a regra do vínculo escrita duas
    vezes — e a segunda cópia é a que diverge.
    """
    admitida = pessoa(hired_on=date(2026, 9, 1))
    inteira = uma(vt([pessoa(hired_on=date(2020, 1, 1))], escala(VT_INICIO, VT_FIM)))
    parcial = uma(vt([admitida], escala(date(2026, 9, 1), VT_FIM)))
    assert parcial.days_base == 14
    assert parcial.days_base < inteira.days_base
    assert parcial.total_amount == Decimal("8.50") * 14


def test_desligamento_no_meio_do_periodo_reduz_os_dias_base() -> None:
    desligada = pessoa(terminated_on=date(2026, 8, 31), hired_on=date(2020, 1, 1))
    linha = uma(vt([desligada], escala(VT_INICIO, date(2026, 8, 31))))
    assert linha.days_base == 7
    assert linha.total_amount == Decimal("8.50") * 7


def test_dia_fora_do_vinculo_nao_entra_mesmo_com_linha_de_escala() -> None:
    """⛔ AUSÊNCIA DO RECORTE: a escala existe para o mês inteiro e a pessoa não.

    Sem `_vinculo_na_janela` dentro da contagem, `days_base` sairia 22 para quem
    foi admitida em 01/09 — e o produto pagaria VT do período em que ela não
    estava na empresa.
    """
    admitida = pessoa(hired_on=date(2026, 9, 1))
    linha = uma(vt([admitida], escala(VT_INICIO, VT_FIM)))
    assert linha.days_base == 14


def test_dia_depois_do_desligamento_nao_entra_mesmo_com_linha_de_escala() -> None:
    """⛔ O ESPELHO DO TESTE DE ADMISSÃO, E ELE FALTAVA.

    `test_desligamento_no_meio_do_periodo_reduz_os_dias_base` não prova o
    recorte: a fixture dele já entrega a escala terminando em 31/08, então a
    redução vem da escala e não de `_vinculo_na_janela`. Medido: apagar a metade
    `terminated_on` do recorte deixava os 62 testes verdes.

    Aqui a escala cobre a janela inteira e o vínculo não — que é o que acontece
    de verdade, porque `app.expected_workday` é materializada por janela e não
    some quando alguém é desligado. Sem o recorte, o produto pagaria vale
    transporte de depois do desligamento.
    """
    desligada = pessoa(terminated_on=date(2026, 8, 31), hired_on=date(2020, 1, 1))
    linha = uma(vt([desligada], escala(VT_INICIO, VT_FIM)))
    assert linha.days_base == 7


def test_a_cobertura_nao_exige_escala_depois_do_desligamento() -> None:
    """A mesma assimetria em `_cobertura`, e no sentido oposto.

    Sem a metade `terminated_on`, quem saiu no meio do mês seria cobrado por
    escala de dias em que já não era da casa — e a apuração de todo mundo travaria
    por causa de quem foi desligado.
    """
    desligada = pessoa(terminated_on=date(2026, 8, 31), hired_on=date(2020, 1, 1))
    ate_o_desligamento = {
        ANA: {
            linha["reference_date"]: linha["day_type"]
            for linha in escala(VT_INICIO, date(2026, 8, 31))
        }
    }
    ciclo._cobertura([desligada], ate_o_desligamento, VT_INICIO, VT_FIM)


def test_duas_linhas_de_onibus_somam() -> None:
    """A `dp_benefit_catalog` recusa travar duas faixas de VT de propósito.

    Escolher uma delas pagaria metade do trajeto de quem faz integração.
    """
    linha = uma(
        vt(
            [pessoa(hired_on=date(2020, 1, 1))],
            escala(VT_INICIO, VT_FIM),
            fares=tarifas(
                ("302", "single", "4.25"),
                ("302", "round_trip", "8.50"),
                ("METRO", "single", "5.00"),
                ("METRO", "round_trip", "10.00"),
            ),
            atribuicoes={ANA: ["302", "METRO"]},
        )
    )
    assert linha.round_trip_amount == Decimal("18.50")
    assert linha.unit_amount == Decimal("9.25")
    assert linha.total_amount == Decimal("18.50") * 21


def test_tarifa_sem_faixa_de_ida_e_volta_falha_alto() -> None:
    """Sem o valor, o total sairia zero — e zero calado numa remessa é dinheiro
    que a pessoa não recebe."""
    with pytest.raises(ciclo.MissingFareError) as recusa:
        vt(
            [pessoa(hired_on=date(2020, 1, 1))],
            escala(VT_INICIO, VT_FIM),
            fares=tarifas(("302", "single", "4.25")),
        )
    assert "302" in str(recusa.value)


def test_dias_liquidos_nao_ficam_negativos() -> None:
    """As faltas são contadas num mês DIFERENTE do dos dias base.

    Sem o piso, quem faltou 25 dias em julho e tem 9 de escala na janela teria
    total negativo — o produto cobrando vale transporte do colaborador.
    """
    muitas = {ANA: {date(2026, 7, d) for d in range(1, 26)}}
    linha = uma(
        vt(
            [pessoa(hired_on=date(2020, 1, 1))],
            escala(VT_INICIO, VT_FIM, folgas=frozenset({0, 1, 2, 3, 4})),
            faltas=muitas,
        )
    )
    assert linha.net_days == 0
    assert linha.total_amount == Decimal("0.00")
    assert not linha.entitled
    assert "10 dia(s) base menos 25 falta" in linha.reason


def test_quem_nao_tem_vale_transporte_fica_fora_do_ciclo() -> None:
    linhas = vt(
        [pessoa(hired_on=date(2020, 1, 1)), pessoa(BRUNO, "Bruno Alves")],
        escala(VT_INICIO, VT_FIM) + escala(VT_INICIO, VT_FIM, employee_id=BRUNO),
    )
    assert [linha.employee_id for linha in linhas] == [ANA]


def test_atribuicao_vencida_nao_entra_no_ciclo() -> None:
    """`in_effect` do S1 é quem decide — não uma segunda cópia da vigência aqui."""
    vencida = [atribuicao(desde=date(2020, 1, 1), ate=date(2026, 8, 20))]
    vigente = [atribuicao(desde=date(2020, 1, 1))]
    assert ciclo._assignments_on(vencida, VT_INICIO) == {}
    assert ciclo._assignments_on(vigente, VT_INICIO) == {ANA: ["302"]}


def test_dias_com_expediente_saem_da_mesma_fonte_dos_dias_base() -> None:
    por_pessoa = {
        ANA: {linha["reference_date"]: linha["day_type"] for linha in escala(VT_INICIO, VT_FIM)}
    }
    assert ciclo.business_days_in(por_pessoa) == 21


# ---------------------------------------------------------------------------
# 5. Cobertura da jornada — dia sem linha não é dia sem expediente
# ---------------------------------------------------------------------------
def test_jornada_incompleta_para_a_apuracao_e_nomeia_quem() -> None:
    """⛔ O SILÊNCIO QUE PAGA A MENOS.

    Em produção `app.expected_workday` cobre poucos dias: uma janela de 31 dias
    com 5 materializados daria `days_base = 4` para todo mundo, e o total sairia
    plausível. Recusar é a única resposta que não tira dinheiro de alguém.
    """
    parcial = {ANA: {date(2026, 8, 21): "work", date(2026, 8, 22): "day_off"}}
    with pytest.raises(ciclo.ScheduleCoverageError) as recusa:
        ciclo._cobertura([pessoa(hired_on=date(2020, 1, 1))], parcial, VT_INICIO, VT_FIM)
    assert "Ana Ribeiro" in str(recusa.value)
    assert "29 dia(s)" in str(recusa.value)


def test_cobertura_completa_passa() -> None:
    """O par positivo: uma trava que recusa tudo passaria no teste acima."""
    completa = {
        ANA: {linha["reference_date"]: linha["day_type"] for linha in escala(VT_INICIO, VT_FIM)}
    }
    ciclo._cobertura([pessoa(hired_on=date(2020, 1, 1))], completa, VT_INICIO, VT_FIM)


def test_cobertura_e_exigida_so_do_vinculo_dentro_da_janela() -> None:
    """Quem foi admitido no meio não precisa de escala antes de existir."""
    admitida = pessoa(hired_on=date(2026, 9, 1))
    so_o_vinculo = {
        ANA: {
            linha["reference_date"]: linha["day_type"] for linha in escala(date(2026, 9, 1), VT_FIM)
        }
    }
    ciclo._cobertura([admitida], so_o_vinculo, VT_INICIO, VT_FIM)


# ---------------------------------------------------------------------------
# O banco de mentira
# ---------------------------------------------------------------------------
_PREDICADO_TENANT = "tenant_id = %(tenant_id)s"


def _no_mesmo_nivel(trecho: str) -> str:
    saida: list[str] = []
    profundidade = 0
    for caractere in trecho:
        if caractere == "(":
            profundidade += 1
            saida.append(" ")
        elif caractere == ")":
            profundidade -= 1
            saida.append(" ")
        else:
            saida.append(caractere if profundidade == 0 else " ")
    return "".join(saida)


def _grupo_do_predicado_de_tenant(sql: str) -> str:
    alvo = sql.index(_PREDICADO_TENANT)
    relativa, inicio = 0, 0
    for i in range(alvo - 1, -1, -1):
        if sql[i] == ")":
            relativa += 1
        elif sql[i] == "(":
            if relativa == 0:
                inicio = i + 1
                break
            relativa -= 1
    relativa, fim = 0, len(sql)
    for i in range(alvo + len(_PREDICADO_TENANT), len(sql)):
        if sql[i] == "(":
            relativa += 1
        elif sql[i] == ")":
            if relativa == 0:
                fim = i
                break
            relativa -= 1
    return sql[inicio:fim]


class FakeCursor:
    """Cursor endereçado por trecho de statement.

    ⚠️ O `delete` ENTROU NA GUARDA, E ESSA É A DIFERENÇA PARA O DUBLÊ DO S1
    O S3 apaga linha (`_CLEAR_LINES_SQL`, ao refazer um rascunho), e um `delete`
    sem filtro de tenant apagaria o rascunho de outro cliente. O dublê do S1
    checava só `select` e `update` porque o S1 não apagava nada — e a guarda que
    não acompanha o verbo novo é uma guarda que passou a não guardar.

    O que continua passando aqui está declarado em `tests/test_dp_beneficios.py`
    e não muda: o lado não filtrado de um `join`, o predicado frouxo sem `or`, e
    o `or` fora do parêntese do predicado. Quem os pega é
    `scripts/98_teste_isolamento_tenant.sql`, contra Postgres.

    ⛔ E O `FakeDB` FILTRAR POR `params["tenant_id"]` NÃO É EVIDÊNCIA DE NADA —
    é conveniência do dublê, que devolve linhas plausíveis. Quem contradiz uma
    consulta mal escrita é a asserção acima, não o filtro do fake. Medido: com o
    predicado trocado por `%(tenant_id)s is not null` ou por `... or true`, são
    16 testes vermelhos; sem a asserção, seriam zero.
    """

    def __init__(self, estado: FakeDB, context: Any, checar_tenant: bool) -> None:
        self._estado = estado
        self._context = context
        self._checar = checar_tenant
        self._resultado: list[dict[str, Any]] = []

    async def execute(self, statement: str, params: Any = None) -> None:
        if self._checar:
            params = bind_tenant(statement, params, self._context)
        sql = " ".join(statement.split())
        if self._checar and sql.startswith(("select", "update", "delete")):
            assert _PREDICADO_TENANT in sql, f"consulta sem filtro de tenant: {sql}"
            grupo = _no_mesmo_nivel(_grupo_do_predicado_de_tenant(sql))
            assert " or " not in grupo, (
                f"o filtro de tenant é uma alternativa, não uma condição — "
                f"`or` no mesmo nível do predicado: {sql}"
            )
        self._estado.statements.append((sql, dict(params or {})))
        self._resultado = self._estado.responder(sql, dict(params or {}))

    async def fetchone(self) -> dict[str, Any] | None:
        return self._resultado[0] if self._resultado else None

    async def fetchall(self) -> list[dict[str, Any]]:
        return list(self._resultado)


class FakeScope:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    async def __aenter__(self) -> FakeCursor:
        return self._cursor

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeDB:
    """As tabelas do S3, com o invariante que o banco garante: uma linha por pessoa."""

    def __init__(self) -> None:
        self.admin = True
        self.compensation = True
        self.banking = True

        self.colaboradores: list[dict[str, Any]] = []
        self.mapa: list[dict[str, Any]] = []
        self.afastamentos_espelho: list[dict[str, Any]] = []
        self.afastamentos_dominio: list[dict[str, Any]] = []
        self.escalas: list[dict[str, Any]] = []
        self.atribuicoes: list[dict[str, Any]] = []
        self.tarifas: list[dict[str, Any]] = []
        self.tipos: list[dict[str, Any]] = []
        self.planos: list[dict[str, Any]] = []
        self.contas: list[dict[str, Any]] = []
        self.ciclos: list[dict[str, Any]] = []
        self.linhas: list[dict[str, Any]] = []

        self.audit: list[dict[str, Any]] = []
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self._proximo_id = 0

    # -- utilidades ---------------------------------------------------------
    def novo_id(self) -> UUID:
        self._proximo_id += 1
        return UUID(f"dddd0000-0000-4000-8000-{self._proximo_id:012d}")

    def _do_tenant(self, linhas: list[dict[str, Any]], params: dict[str, Any]):
        return [linha for linha in linhas if linha["tenant_id"] == params["tenant_id"]]

    # -- semeadura ----------------------------------------------------------
    def semear_pessoa(self, linha: dict[str, Any], tenant_id: UUID = TENANT_ID) -> None:
        self.colaboradores.append({**linha, "tenant_id": tenant_id})

    def semear_curadoria(self, chave: str, categoria: str, *, validada: bool = True) -> None:
        self.mapa.append(
            {
                "tenant_id": TENANT_ID,
                "justification": chave,
                "category": categoria,
                "validated_at": datetime(2026, 9, 1, 12, 0) if validada else None,
            }
        )

    def semear_afastamento(self, linha: dict[str, Any], tenant_id: UUID = TENANT_ID) -> None:
        self.afastamentos_espelho.append({**linha, "tenant_id": tenant_id})

    def semear_escala(self, linhas: list[dict[str, Any]], tenant_id: UUID = TENANT_ID) -> None:
        self.escalas.extend({**linha, "tenant_id": tenant_id} for linha in linhas)

    def semear_atribuicao(self, linha: dict[str, Any], tenant_id: UUID = TENANT_ID) -> None:
        self.atribuicoes.append({**linha, "tenant_id": tenant_id})

    def semear_tarifa(
        self, code: str, kind: str, amount: str, *, tenant_id: UUID = TENANT_ID
    ) -> None:
        self.tarifas.append(
            {
                "id": self.novo_id(),
                "tenant_id": tenant_id,
                "code": code,
                "name": f"Linha {code}",
                "kind": kind,
                "amount": Decimal(amount),
                "effective_from": date(2026, 1, 1),
                "effective_to": None,
                "reason": None,
            }
        )

    def semear_conta(self, employee_id: UUID, account: str, tenant_id: UUID = TENANT_ID) -> None:
        self.contas.append(
            {
                "employee_id": employee_id,
                "tenant_id": tenant_id,
                "bank_code": "341",
                "branch": "0001",
                "account": account,
                "account_type": "checking",
                "holder_document": None,
                "updated_at": datetime(2026, 9, 1, 12, 0),
            }
        )

    # -- o despacho ---------------------------------------------------------
    def responder(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if "util.can_see_domain" in sql and "util.is_admin" in sql:
            if "'banking'" in sql:
                return [{"banking": self.banking, "admin": self.admin}]
            return [
                {
                    "admin": self.admin,
                    "pii": True,
                    "compensation": self.compensation,
                    "health": True,
                }
            ]

        if "from app.leave_justification_map m" in sql:
            return [dict(linha) for linha in self._do_tenant(self.mapa, params)]
        if 'from secullum."FuncionarioAfastamento"' in sql:
            return self._afastamentos_espelho(params)
        if "from app.leave_period l" in sql:
            return self._afastamentos_dominio(params)
        if "from app.expected_workday w" in sql:
            return self._escalas(params)
        if "from app.employee_benefit eb" in sql:
            return [dict(linha) for linha in self._do_tenant(self.atribuicoes, params)]
        if "from app.employee_bank_account a" in sql:
            return [
                dict(linha)
                for linha in self._do_tenant(self.contas, params)
                if linha["employee_id"] in set(params["employee_ids"])
            ]

        if "from app.benefit_type bt" in sql:
            return [dict(linha) for linha in self._do_tenant(self.tipos, params)]
        if "from app.benefit_plan p" in sql:
            return [
                {**linha, "benefit_type_code": "health_plan"}
                for linha in self._do_tenant(self.planos, params)
            ]
        if "from app.transport_fare f" in sql:
            return [dict(linha) for linha in self._do_tenant(self.tarifas, params)]

        # ⛔ ANTES das duas abaixo, e por dois motivos: a listagem lê
        #    `from app.benefit_cycle c` (que `_ciclo` despacha esperando outros
        #    parâmetros) E cita `from app.benefit_entitlement b` DENTRO do
        #    lateral dos agregados. Testar o trecho mais específico primeiro é o
        #    que impede o dublê de responder a consulta errada — e a resposta
        #    errada aqui é um KeyError, que ao menos é barulhento.
        if "left join lateral" in sql:
            return self._listar_ciclos(sql, params)
        if "from app.benefit_entitlement b" in sql:
            return self._linhas_do_ciclo(params)
        if "from app.benefit_cycle c" in sql:
            return self._ciclo(sql, params)
        if "from app.employee e" in sql:
            return self._populacao(params)

        if "insert into app.transport_fare" in sql:
            return self._criar_tarifa(params)
        if "insert into app.benefit_plan" in sql:
            return self._criar_plano(params)

        if "insert into app.benefit_cycle" in sql:
            return self._criar_ciclo(params)
        if "update app.benefit_cycle" in sql:
            return self._alterar_ciclo(sql, params)
        if "delete from app.benefit_entitlement" in sql:
            self.linhas = [
                linha
                for linha in self.linhas
                if not (
                    linha["cycle_id"] == params["cycle_id"]
                    and linha["tenant_id"] == params["tenant_id"]
                )
            ]
            return []
        if "insert into app.benefit_entitlement" in sql:
            return self._criar_linha(params)

        if "insert into app.audit_log" in sql:
            self.audit.append(dict(params))
            return []
        raise AssertionError(f"statement inesperado: {sql}")

    def _criar_tarifa(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        # O índice único parcial da migration, modelado: uma faixa aberta por
        # (tenant, code, kind). Sem ele, `create_fare` abriria a segunda e o
        # preço do mês passaria a depender da ordem da leitura.
        aberta = any(
            linha["tenant_id"] == params["tenant_id"]
            and linha["code"] == params["code"]
            and linha["kind"] == params["kind"]
            and linha["effective_to"] is None
            for linha in self.tarifas
        )
        if aberta:
            raise errors.UniqueViolation(
                'duplicate key value violates unique index "transport_fare_open_band_idx"'
            )
        linha = {
            "id": self.novo_id(),
            "tenant_id": params["tenant_id"],
            "code": params["code"],
            "name": params["name"],
            "kind": params["kind"],
            "amount": Decimal(str(params["amount"])),
            "effective_from": params["effective_from"],
            "effective_to": None,
            "reason": params["reason"],
        }
        self.tarifas.append(linha)
        return [dict(linha)]

    def _criar_plano(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        linha = {
            "id": self.novo_id(),
            "tenant_id": params["tenant_id"],
            "benefit_type_id": params["benefit_type_id"],
            "code": params["code"],
            "provider": params["provider"],
            "name": params["name"],
            "amount": Decimal(str(params["amount"])),
            "effective_from": params["effective_from"],
            "effective_to": None,
            "reason": params["reason"],
        }
        self.planos.append(linha)
        return [dict(linha)]

    def _no_mes(self, linhas, params, chave_inicio="starts_on", chave_fim="ends_on"):
        return [
            linha
            for linha in linhas
            if linha[chave_inicio] <= params["month_end"]
            and linha[chave_fim] >= params["month_start"]
        ]

    def _afastamentos_espelho(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        do_tenant = self._do_tenant(self.afastamentos_espelho, params)
        return [
            {
                "employee_id": linha["employee_id"],
                "starts_on": linha["starts_on"],
                "ends_on": linha["ends_on"],
                "justification": linha["justification"],
            }
            for linha in self._no_mes(do_tenant, params)
        ]

    def _afastamentos_dominio(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        do_tenant = self._do_tenant(self.afastamentos_dominio, params)
        return [
            {
                "employee_id": linha["employee_id"],
                "starts_on": linha["starts_on"],
                "ends_on": linha["ends_on"],
            }
            for linha in self._no_mes(do_tenant, params)
            if linha["category"] == params["category"]
        ]

    def _escalas(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "employee_id": linha["employee_id"],
                "reference_date": linha["reference_date"],
                "day_type": linha["day_type"],
            }
            for linha in self._do_tenant(self.escalas, params)
            if params["window_start"] <= linha["reference_date"] <= params["window_end"]
        ]

    def _populacao(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        saida = []
        for linha in self._do_tenant(self.colaboradores, params):
            if linha["hired_on"] is not None and linha["hired_on"] > params["window_end"]:
                continue
            if (
                linha["terminated_on"] is not None
                and linha["terminated_on"] < params["window_start"]
            ):
                continue
            saida.append({chave: linha[chave] for chave in linha if chave != "tenant_id"})
        return sorted(saida, key=lambda linha: linha["name"])

    def _ciclo(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        do_tenant = self._do_tenant(self.ciclos, params)
        if "c.id = %(cycle_id)s" in sql:
            return [dict(c) for c in do_tenant if c["id"] == params["cycle_id"]]
        return [
            dict(c)
            for c in do_tenant
            if c["kind"] == params["kind"]
            and c["period_year"] == params["period_year"]
            and c["period_month"] == params["period_month"]
            and c["status"] == params["draft"]
        ]

    def _listar_ciclos(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """A lista com os agregados.

        ⛔ RAMIFICA NO TEXTO DO STATEMENT, E NÃO POR CONTA PRÓPRIA
        A primeira versão aplicava os quatro filtros e contava `entitled`
        sempre — e aí três mutações passaram VERDES: tornar os filtros uma
        tautologia, tirar o `filter (where b.entitled)` dos agregados e soltar o
        tenant do lateral. Um fake que decide sozinho nunca contradiz a consulta;
        é a mesma objeção que o ciclo 1 do S1 fez ao dublê do vínculo.
        """
        saida = []
        for c in self._do_tenant(self.ciclos, params):
            for campo, coluna in (
                ("kind", "kind"),
                ("status", "status"),
                ("period_year", "period_year"),
                ("period_month", "period_month"),
            ):
                # Só filtra pelo que a consulta de fato compara.
                if f"c.{coluna} = %({campo})s" not in sql:
                    continue
                if params[campo] is not None and c[coluna] != params[campo]:
                    break
            else:
                linhas = [
                    linha
                    for linha in self.linhas
                    if linha["cycle_id"] == c["id"]
                    # O lateral só recorta por tenant se o SQL disser.
                    and (
                        "b.tenant_id = c.tenant_id" not in sql
                        or linha["tenant_id"] == c["tenant_id"]
                    )
                ]
                com_direito = (
                    [linha for linha in linhas if linha["entitled"]]
                    if "count(*) filter (where b.entitled)" in sql
                    else linhas
                )
                saida.append(
                    {
                        **c,
                        "entitled_count": len(com_direito),
                        "denied_count": sum(1 for linha in linhas if not linha["entitled"]),
                        "total_amount": sum(
                            (
                                linha["total_amount"]
                                for linha in linhas
                                if linha["total_amount"] is not None
                            ),
                            start=Decimal("0"),
                        ),
                    }
                )
        return sorted(saida, key=lambda c: (-c["period_year"], -c["period_month"], c["kind"]))

    def _criar_ciclo(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        linha = {
            "id": self.novo_id(),
            "tenant_id": params["tenant_id"],
            "kind": params["kind"],
            "period_year": params["period_year"],
            "period_month": params["period_month"],
            "window_start": params["window_start"],
            "window_end": params["window_end"],
            "business_days": params["business_days"],
            "status": "draft",
        }
        self.ciclos.append(linha)
        return [{"id": linha["id"]}]

    def _alterar_ciclo(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        for linha in self.ciclos:
            if linha["id"] != params["cycle_id"] or linha["tenant_id"] != params["tenant_id"]:
                continue
            if "set status" in sql:
                # ⛔ O DUBLÊ RAMIFICA NO TEXTO DO STATEMENT, E NÃO POR CONTA PRÓPRIA
                #    A primeira versão desta linha aplicava o recorte de rascunho
                #    sempre — e aí apagar `and status = %(draft)s` do
                #    `_FREEZE_SQL` passava VERDE: um fake que filtra sozinho nunca
                #    contradiz a consulta. É a objeção que o ciclo 1 do S1 fez ao
                #    dublê do vínculo, e ela vale igual aqui.
                if "status = %(draft)s" in sql and linha["status"] != params["draft"]:
                    return []
                linha["status"] = params["generated"]
                return [{"id": linha["id"]}]
            linha["window_start"] = params["window_start"]
            linha["window_end"] = params["window_end"]
            linha["business_days"] = params["business_days"]
            return []
        return []

    def _criar_linha(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        # O `unique (cycle_id, employee_id)` da migration, modelado: sem ele,
        # reapurar um rascunho duplicaria a pessoa e a remessa pagaria duas vezes.
        duplicada = any(
            linha["cycle_id"] == params["cycle_id"]
            and linha["employee_id"] == params["employee_id"]
            for linha in self.linhas
        )
        assert not duplicada, (
            "duplicate key value violates unique constraint on (cycle_id, employee_id)"
        )
        self.linhas.append(dict(params))
        return []

    def _linhas_do_ciclo(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        por_id = {linha["employee_id"]: linha for linha in self.colaboradores}
        saida = []
        for linha in self.linhas:
            if linha["cycle_id"] != params["cycle_id"] or linha["tenant_id"] != params["tenant_id"]:
                continue
            pessoa_ = por_id[linha["employee_id"]]
            saida.append(
                {
                    **linha,
                    "name": pessoa_["name"],
                    "registration_number": pessoa_["registration_number"],
                    "unit_name": pessoa_["unit_name"],
                }
            )
        return sorted(saida, key=lambda linha: linha["name"])


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    estado = FakeDB()

    def tenant_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursor(estado, context, checar_tenant=True))

    def user_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursor(estado, context, checar_tenant=False))

    monkeypatch.setattr(ciclo, "tenant_scope", tenant_scope)
    monkeypatch.setattr(beneficios, "tenant_scope", tenant_scope)
    monkeypatch.setattr(banking, "tenant_scope", tenant_scope)
    monkeypatch.setattr(banking, "user_scope", user_scope)
    monkeypatch.setattr(rh_repository, "user_scope", user_scope)
    monkeypatch.setattr("server.routers.dp.tenant_scope", tenant_scope)
    return estado


def cabecalho(issue_token: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token()}"}


def cenario_vt(fake_db: FakeDB) -> None:
    """Uma pessoa com VT, escala cheia e uma falta em julho — o caso de referência."""
    fake_db.semear_pessoa(pessoa(hired_on=date(2020, 1, 1)))
    fake_db.semear_escala(escala(VT_INICIO, VT_FIM))
    fake_db.semear_atribuicao(atribuicao())
    fake_db.semear_tarifa("302", "single", "4.25")
    fake_db.semear_tarifa("302", "round_trip", "8.50")
    fake_db.semear_curadoria("FALTA", "unjustified_absence")
    fake_db.semear_afastamento(afastamento("FALTA", date(2026, 7, 6), date(2026, 7, 7)))


def apurar(client: TestClient, issue_token: Any, **overrides: Any):
    corpo = {"kind": "transport_voucher", "period_year": ANO, "period_month": MES} | overrides
    return client.post("/dp/ciclos", json=corpo, headers=cabecalho(issue_token))


def apurar_e_gerar(client: TestClient, issue_token: Any) -> str:
    """Apura e congela — o estado em que um ciclo pode virar dinheiro.

    ⛔ As provas de remessa passam por aqui, e não por `apurar` sozinho. A versão
    anterior deste arquivo exportava do RASCUNHO, e o caminho feliz testado ERA o
    defeito: rascunho é reapurado a cada conferência, e o mesmo ciclo produziu
    dois arquivos de banco com valores diferentes.
    """
    ciclo_id = apurar(client, issue_token).json()["id"]
    resposta = client.post(f"/dp/ciclos/{ciclo_id}/gerar", headers=cabecalho(issue_token))
    assert resposta.status_code == 200, resposta.text
    return ciclo_id


# ---------------------------------------------------------------------------
# 6. As rotas — preview, congelamento e recusas
# ---------------------------------------------------------------------------
def test_apurar_devolve_o_preview_com_a_janela_derivada(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    cenario_vt(fake_db)
    resposta = apurar(client, issue_token)

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["window_start"] == "2026-08-21"
    assert corpo["window_end"] == "2026-09-20"
    assert corpo["status"] == "draft"
    assert corpo["entitled_count"] == 1
    assert Decimal(str(corpo["total_amount"])) == Decimal("161.50")
    assert corpo["rows"][0]["net_days"] == 19


def test_reapurar_a_mesma_competencia_nao_duplica_ninguem(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ IDEMPOTÊNCIA: reprocessar um período não pode duplicar linha.

    O dublê levanta na segunda inserção do mesmo `(cycle_id, employee_id)`, que é
    o `unique` da migration — então um rascunho que acrescentasse em vez de
    refazer quebra aqui, e não em produção com a remessa pagando duas vezes.
    """
    cenario_vt(fake_db)
    primeiro = apurar(client, issue_token).json()
    segundo = apurar(client, issue_token).json()

    assert primeiro["id"] == segundo["id"]
    assert len(fake_db.ciclos) == 1
    assert len(fake_db.linhas) == 1


def test_gerar_congela_e_nao_reapura(client: TestClient, issue_token: Any, fake_db: FakeDB) -> None:
    """O número conferido é o número congelado, mesmo que o dado mude no meio."""
    cenario_vt(fake_db)
    ciclo_id = apurar(client, issue_token).json()["id"]

    # Entre a conferência e o congelamento, alguém acrescenta uma falta.
    fake_db.semear_afastamento(afastamento("FALTA", date(2026, 7, 20), date(2026, 7, 24)))

    resposta = client.post(f"/dp/ciclos/{ciclo_id}/gerar", headers=cabecalho(issue_token))
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "generated"
    assert corpo["rows"][0]["net_days"] == 19
    assert Decimal(str(corpo["total_amount"])) == Decimal("161.50")


def test_gerar_duas_vezes_devolve_409(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    cenario_vt(fake_db)
    ciclo_id = apurar(client, issue_token).json()["id"]
    client.post(f"/dp/ciclos/{ciclo_id}/gerar", headers=cabecalho(issue_token))

    segunda = client.post(f"/dp/ciclos/{ciclo_id}/gerar", headers=cabecalho(issue_token))
    assert segunda.status_code == 409
    assert "rascunho" in segunda.json()["detail"]


def test_ciclo_de_outro_tenant_responde_404(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    cenario_vt(fake_db)
    ciclo_id = apurar(client, issue_token).json()["id"]
    for linha in fake_db.ciclos:
        linha["tenant_id"] = OUTRO_TENANT

    resposta = client.post(f"/dp/ciclos/{ciclo_id}/gerar", headers=cabecalho(issue_token))
    assert resposta.status_code == 404


def test_justificativa_nao_curada_vira_422_com_a_string_na_mensagem(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ O TEXTO CHEGA À TELA. Um 500 mandaria isto para o Sentry e a pessoa que
    opera nunca saberia qual justificativa classificar."""
    cenario_vt(fake_db)
    fake_db.semear_afastamento(afastamento("ATEST M", date(2026, 7, 10), date(2026, 7, 11)))

    resposta = apurar(client, issue_token)
    assert resposta.status_code == 422
    assert "ATEST M" in resposta.json()["detail"]
    # E nada ficou gravado: a competência não nasce pela metade.
    assert fake_db.ciclos == []


def test_jornada_incompleta_vira_422(client: TestClient, issue_token: Any, fake_db: FakeDB) -> None:
    cenario_vt(fake_db)
    fake_db.escalas = fake_db.escalas[:3]

    resposta = apurar(client, issue_token)
    assert resposta.status_code == 422
    assert "expected_workday" in resposta.json()["detail"]


def test_quem_nao_tem_vt_com_jornada_incompleta_nao_trava_a_apuracao(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ RECUSA-DEMAIS, E ELA NÃO TEM SINTOMA ATÉ TRAVAR A ROTINA INTEIRA.

    Quem não tem vale transporte atribuído não tem `days_base` a errar. Exigir
    cobertura dele faria um supervisor sem escala materializada — e há seis
    assim em produção, fora do motor por decisão da migration 26 — impedir a
    apuração de todo mundo, todo mês. Uma trava que barra o legítimo é pior que
    a ausência dela.
    """
    cenario_vt(fake_db)
    fake_db.semear_pessoa(pessoa(BRUNO, "Bruno Alves"))  # sem escala e sem VT

    resposta = apurar(client, issue_token)
    assert resposta.status_code == 201
    assert [linha["name"] for linha in resposta.json()["rows"]] == ["Ana Ribeiro"]


def test_apurar_sem_compensation_e_403(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    cenario_vt(fake_db)
    fake_db.compensation = False
    assert apurar(client, issue_token).status_code == 403


def test_apurar_sem_admin_e_403(client: TestClient, issue_token: Any, fake_db: FakeDB) -> None:
    cenario_vt(fake_db)
    fake_db.admin = False
    assert apurar(client, issue_token).status_code == 403


def test_a_janela_nao_vem_do_cliente(client: TestClient, issue_token: Any, fake_db: FakeDB) -> None:
    """⛔ 21 → 20 é regra do cliente transcrita da tela, não parâmetro.

    Aceitar `window_start` do formulário deixaria alguém apurar setembro com a
    janela de agosto, e o número sairia plausível.
    """
    cenario_vt(fake_db)
    resposta = apurar(client, issue_token, window_start="2026-09-01")
    assert resposta.status_code == 422


# ---------------------------------------------------------------------------
# 7. A porta da primeira vigência
# ---------------------------------------------------------------------------
def test_criar_tarifa_abre_a_primeira_vigencia(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    corpo = {
        "code": "302",
        "name": "Linha 302 — Centro",
        "kind": "round_trip",
        "effective_from": "2026-01-01",
        "amount": "8.50",
    }
    resposta = client.post("/dp/beneficios/tarifas", json=corpo, headers=cabecalho(issue_token))

    assert resposta.status_code == 201
    assert Decimal(str(resposta.json()["amount"])) == Decimal("8.50")
    # ⛔ Não há `previous_*`: não havia nada antes dela, e inventar um "anterior"
    #    faria a tela confirmar um reajuste que não aconteceu.
    assert "previous_amount" not in resposta.json()


def test_criar_tarifa_que_ja_existe_devolve_409_e_aponta_o_reajuste(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_tarifa("302", "round_trip", "8.50")
    corpo = {
        "code": "302",
        "name": "Linha 302",
        "kind": "round_trip",
        "effective_from": "2026-02-01",
        "amount": "9.00",
    }
    resposta = client.post("/dp/beneficios/tarifas", json=corpo, headers=cabecalho(issue_token))
    assert resposta.status_code == 409
    assert "reajuste" in resposta.json()["detail"]


def test_criar_plano_de_verba_inexistente_e_404(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    corpo = {
        "benefit_type_code": "plano_de_saude",
        "code": "UNI-100",
        "provider": "Unimed",
        "name": "Unimed 100",
        "effective_from": "2026-01-01",
        "amount": "320.00",
    }
    resposta = client.post("/dp/beneficios/planos", json=corpo, headers=cabecalho(issue_token))
    assert resposta.status_code == 404


def test_criar_tarifa_sem_admin_e_403(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.admin = False
    corpo = {
        "code": "302",
        "name": "Linha 302",
        "kind": "single",
        "effective_from": "2026-01-01",
        "amount": "4.25",
    }
    resposta = client.post("/dp/beneficios/tarifas", json=corpo, headers=cabecalho(issue_token))
    assert resposta.status_code == 403


# ---------------------------------------------------------------------------
# 8. A conta bancária — dentro de `bytes`, e em lugar nenhum mais
# ---------------------------------------------------------------------------
CONTA = "987654321"


def cenario_remessa(fake_db: FakeDB) -> None:
    cenario_vt(fake_db)
    fake_db.semear_conta(ANA, CONTA)


def test_a_remessa_carrega_a_conta_inteira(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """O par positivo da varredura: um produto que nunca escrevesse a conta em
    lugar nenhum passaria em todas as asserções negativas abaixo — e a remessa
    não pagaria ninguém."""
    cenario_remessa(fake_db)
    ciclo_id = apurar_e_gerar(client, issue_token)

    resposta = client.get(
        f"/dp/ciclos/{ciclo_id}/export?formato=banco", headers=cabecalho(issue_token)
    )
    assert resposta.status_code == 200
    assert CONTA.encode() in resposta.content
    assert b"161.50" in resposta.content


def test_nenhuma_resposta_json_de_dp_contem_a_conta(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ VARREDURA, NÃO REVISÃO DE CÓDIGO.

    O número completo e qualquer chave chamada `account` são procurados no JSON
    literal de todas as rotas do ciclo — inclusive a que acabou de montar a
    remessa com o número na mão.
    """
    cenario_remessa(fake_db)
    ciclo_id = apurar_e_gerar(client, issue_token)
    remessa = client.get(
        f"/dp/ciclos/{ciclo_id}/export?formato=banco", headers=cabecalho(issue_token)
    )
    assert remessa.status_code == 200

    respostas = [
        apurar(client, issue_token),
        client.post(f"/dp/ciclos/{ciclo_id}/gerar", headers=cabecalho(issue_token)),
        client.get("/dp/beneficios/catalogo", headers=cabecalho(issue_token)),
    ]
    for resposta in respostas:
        texto = resposta.text
        assert CONTA not in texto, f"a conta vazou em {resposta.request.url}"
        corpo = resposta.json()
        assert "account" not in json.dumps(corpo), f"chave `account` em {resposta.request.url}"


def test_o_excel_e_o_pdf_nao_carregam_a_conta(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Eles não recebem o dado — e a ausência é o desenho, não uma máscara."""
    cenario_remessa(fake_db)
    ciclo_id = apurar(client, issue_token).json()["id"]

    for formato in ("xlsx", "pdf"):
        resposta = client.get(
            f"/dp/ciclos/{ciclo_id}/export?formato={formato}", headers=cabecalho(issue_token)
        )
        assert resposta.status_code == 200
        assert CONTA.encode() not in resposta.content


def test_a_leitura_de_conta_traz_so_o_que_a_remessa_usa(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ COLUNA SENSÍVEL SEM CONSUMIDOR ENFRAQUECE O ARGUMENTO ESTRUTURAL.

    `banking.py` se sustenta em "a garantia é o tipo, não alguém lembrando de
    mascarar". O `dict` cru de `load_accounts` é a exceção a isso — ele atravessa
    dois módulos com o número inteiro — e por isso ele carrega o mínimo.
    `holder_document` é CPF/CNPJ de TERCEIRO e nem o arquivo nem a trilha o usam;
    trazê-lo faria a próxima pessoa lê-lo como se fosse o que a remessa precisa.
    Esta asserção é o que impede um `select *` de voltar por conveniência.
    """
    cenario_remessa(fake_db)
    ciclo_id = apurar_e_gerar(client, issue_token)
    client.get(f"/dp/ciclos/{ciclo_id}/export?formato=banco", headers=cabecalho(issue_token))

    sql = next(sql for sql, _ in fake_db.statements if "employee_bank_account" in sql)
    assert "holder_document" not in sql
    assert "*" not in sql
    # O positivo: as cinco que a remessa de fato usa continuam vindo.
    for coluna in ("employee_id", "bank_code", "branch", "account", "account_type"):
        assert coluna in sql, coluna


def test_a_remessa_de_rascunho_e_recusada_e_a_mensagem_aponta_o_gerar(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ A PORTA QUE PAGA PASSA A EXIGIR O CICLO CONGELADO.

    Toda a maquinaria de imutabilidade protegia o ciclo gerado, e a única rota
    que vira dinheiro não exigia que ele estivesse gerado. Medido antes do
    conserto: o MESMO ciclo em rascunho produziu dois arquivos de banco, um com
    161,50 e outro com 1.881,00, porque reapurar apaga e reinsere as linhas
    depois de a primeira remessa já ter saído.
    """
    cenario_remessa(fake_db)
    ciclo_id = apurar(client, issue_token).json()["id"]

    resposta = client.get(
        f"/dp/ciclos/{ciclo_id}/export?formato=banco", headers=cabecalho(issue_token)
    )
    assert resposta.status_code == 409
    assert "gere o ciclo" in resposta.json()["detail"]
    assert CONTA not in resposta.text
    # ⛔ E a conta nem chegou a ser lida: o estado é conferido antes do `select`.
    assert not [sql for sql, _ in fake_db.statements if "employee_bank_account" in sql]


def test_o_preview_de_rascunho_continua_saindo_em_excel_e_pdf(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """O par positivo do 409 acima. Rascunho EXISTE para ser conferido.

    Uma guarda que barrasse os três formatos tiraria o preview — e uma trava que
    barra o legítimo é pior que a ausência dela.
    """
    cenario_remessa(fake_db)
    ciclo_id = apurar(client, issue_token).json()["id"]

    for formato in ("xlsx", "pdf"):
        resposta = client.get(
            f"/dp/ciclos/{ciclo_id}/export?formato={formato}", headers=cabecalho(issue_token)
        )
        assert resposta.status_code == 200, formato


def test_a_remessa_do_ciclo_congelado_nao_muda_quando_o_dado_muda(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Duas remessas do mesmo ciclo são o mesmo arquivo, byte a byte.

    É a asserção que o defeito reprovava: com a apuração podendo ser refeita por
    baixo, o segundo download pagava outro valor. O ciclo congelado é o documento
    que diz quanto cada pessoa recebeu, e ele não se reescreve.
    """
    cenario_remessa(fake_db)
    ciclo_id = apurar_e_gerar(client, issue_token)

    def baixar() -> bytes:
        return client.get(
            f"/dp/ciclos/{ciclo_id}/export?formato=banco", headers=cabecalho(issue_token)
        ).content

    primeiro = baixar()
    # O mundo muda entre um download e o outro: mais faltas, e a rotina do mês
    # seguinte reapurando a competência.
    fake_db.semear_afastamento(afastamento("FALTA", date(2026, 7, 13), date(2026, 7, 17)))
    apurar(client, issue_token)

    assert baixar() == primeiro
    assert b"161.50" in primeiro


@pytest.mark.parametrize("nome", ["João Gonçalves", "Ana — Silva", "Łukasz Nowak", "中村 太郎"])
def test_o_pdf_sai_com_nome_que_a_fonte_base_nao_desenha(nome: str) -> None:
    """⛔ NOME ESTRANGEIRO NO QUADRO NÃO PODE SER UM 500 NA ROTA DE EXPORT.

    Medido: pt-BR e o travessão passam em cp1252; `Łukasz Nowak` levantava
    `FPDFUnicodeEncodingException`, e um nome no quadro travava o PDF do mês
    inteiro. O `?` que entra no lugar aparece no papel — o Excel e a remessa
    continuam carregando o nome exato.
    """
    linhas = vt([pessoa(nome=nome, hired_on=date(2020, 1, 1))], escala(VT_INICIO, VT_FIM))
    cycle = ciclo.Cycle(
        id=UUID("dddd0000-0000-4000-8000-000000000001"),
        kind=ciclo.TRANSPORT_VOUCHER,
        period_year=ANO,
        period_month=MES,
        window_start=VT_INICIO,
        window_end=VT_FIM,
        business_days=21,
        status="generated",
        lines=linhas,
    )
    assert export.build_pdf(cycle).startswith(b"%PDF-")

    # E o Excel guarda o nome como ele é: a troca vale só onde a fonte não
    # desenha. Sem esta metade, trocar todo mundo por `?` em todo lugar passaria.
    planilha = load_workbook(BytesIO(export.build_xlsx(cycle)))
    celulas = {celula.value for linha in planilha.active.iter_rows() for celula in linha}
    assert nome in celulas


def test_a_remessa_exige_o_dominio_bancario(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    cenario_remessa(fake_db)
    # ⛔ De rascunho mesmo: o papel é conferido ANTES do estado, então quem não
    #    tem `banking` não descobre por aqui se o ciclo já foi gerado.
    ciclo_id = apurar(client, issue_token).json()["id"]
    fake_db.banking = False

    resposta = client.get(
        f"/dp/ciclos/{ciclo_id}/export?formato=banco", headers=cabecalho(issue_token)
    )
    assert resposta.status_code == 403
    # E o Excel continua saindo: quem confere a lista não precisa de conta.
    assert (
        client.get(
            f"/dp/ciclos/{ciclo_id}/export?formato=xlsx", headers=cabecalho(issue_token)
        ).status_code
        == 200
    )


def test_a_remessa_conferida_por_quem_nao_e_admin(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ `accounting` concilia a remessa e não apura ciclo nenhum.

    Exigir admin no download trancaria fora exatamente o papel que existe para
    conferi-la — uma trava que barra o legítimo é pior que a ausência dela.
    """
    cenario_remessa(fake_db)
    ciclo_id = apurar_e_gerar(client, issue_token)
    fake_db.admin = False

    resposta = client.get(
        f"/dp/ciclos/{ciclo_id}/export?formato=banco", headers=cabecalho(issue_token)
    )
    assert resposta.status_code == 200


def test_quem_nao_tem_conta_fica_de_fora_do_arquivo() -> None:
    """Uma linha com conta em branco é uma remessa que o banco recusa inteira."""
    linhas = vt([pessoa(hired_on=date(2020, 1, 1))], escala(VT_INICIO, VT_FIM))
    cycle = ciclo.Cycle(
        id=UUID("dddd0000-0000-4000-8000-000000000001"),
        kind=ciclo.TRANSPORT_VOUCHER,
        period_year=ANO,
        period_month=MES,
        window_start=VT_INICIO,
        window_end=VT_FIM,
        business_days=21,
        status="generated",
        lines=linhas,
    )
    arquivo, sem_conta = export.build_remittance(cycle, [])
    assert sem_conta == ["Ana Ribeiro"]
    assert arquivo.decode().strip() == ";".join(export._REMITTANCE_HEADER)


def test_a_remessa_de_cesta_e_recusada() -> None:
    """Cesta é pedido ao fornecedor, não pagamento em conta."""
    cycle = ciclo.Cycle(
        id=UUID("dddd0000-0000-4000-8000-000000000001"),
        kind=ciclo.FOOD_BASKET,
        period_year=ANO,
        period_month=MES,
        window_start=CESTA_INICIO,
        window_end=CESTA_FIM,
        business_days=None,
        status="generated",
        lines=cesta([pessoa(hired_on=date(2020, 1, 1))]),
    )
    with pytest.raises(export.RemittanceError):
        export.build_remittance(cycle, [])


def test_a_trilha_da_remessa_guarda_a_mascara_e_nunca_o_numero(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """`SPEC-DP.md` §5: quem gerou, quando, para qual ciclo. Sem o número."""
    cenario_remessa(fake_db)
    ciclo_id = apurar_e_gerar(client, issue_token)
    client.get(f"/dp/ciclos/{ciclo_id}/export?formato=banco", headers=cabecalho(issue_token))

    trilhas = [linha for linha in fake_db.audit if linha["action"] == "export"]
    assert len(trilhas) == 1
    texto = str(trilhas[0]["depois"].obj)
    assert CONTA not in texto
    assert "•••• 4321" in texto
    assert ciclo_id in texto


# ---------------------------------------------------------------------------
# 8-bis. A lista de competências, e o eixo que a tela precisa
# ---------------------------------------------------------------------------
def listar(client: TestClient, issue_token: Any, **filtros: Any):
    return client.get("/dp/ciclos", params=filtros, headers=cabecalho(issue_token))


def test_a_lista_reencontra_o_ciclo_congelado_sem_apurar_de_novo(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ SEM ESTA ROTA, O `id` SÓ NASCIA NA RESPOSTA DO `POST`.

    Recarregar a página perdia o ciclo congelado, e reencontrá-lo obrigava a
    apurar de novo — o que cria um SEGUNDO rascunho ao lado do gerado, porque o
    `unique` da competência inclui o `status`. Duas competências do mesmo mês na
    tela é a confusão que faz alguém exportar a errada.
    """
    cenario_vt(fake_db)
    ciclo_id = apurar_e_gerar(client, issue_token)

    resposta = listar(client, issue_token, ano=ANO, mes=MES, kind="transport_voucher")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [linha["id"] for linha in corpo["rows"]] == [ciclo_id]
    assert corpo["rows"][0]["status"] == "generated"
    # E nenhum rascunho novo nasceu: a lista não apura.
    assert len(fake_db.ciclos) == 1


def test_o_resumo_da_lista_bate_com_o_detalhe_do_ciclo(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ OS AGREGADOS SÃO CONTADOS DUAS VEZES — pelo SQL e por `Cycle`, em Python.

    Duas contas para o mesmo número é a forma que diverge. Esta asserção é o que
    as prende juntas: qualquer uma que mude sozinha faz o resumo e o detalhe da
    MESMA competência deixarem de bater.
    """
    cenario_vt(fake_db)
    fake_db.semear_pessoa(pessoa(BRUNO, "Bruno Alves", hired_on=date(2026, 9, 15)))
    fake_db.semear_escala(escala(date(2026, 9, 15), VT_FIM, employee_id=BRUNO))
    fake_db.semear_atribuicao(atribuicao(employee_id=BRUNO))

    detalhe = apurar(client, issue_token).json()
    resumo = listar(client, issue_token).json()["rows"][0]

    for campo in (
        "id",
        "kind",
        "period_year",
        "period_month",
        "window_start",
        "window_end",
        "business_days",
        "status",
        "entitled_count",
        "denied_count",
    ):
        assert resumo[campo] == detalhe[campo], campo
    assert Decimal(str(resumo["total_amount"])) == Decimal(str(detalhe["total_amount"]))
    # O positivo: os agregados não são todos zero — uma comparação de zeros
    # bateria sem provar conta nenhuma.
    assert resumo["entitled_count"] == 2
    assert Decimal(str(resumo["total_amount"])) > 0


def test_a_lista_nao_carrega_a_linha_por_pessoa(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Vinte e quatro competências de 176 pessoas seriam 4.200 linhas na tela."""
    cenario_remessa(fake_db)
    apurar_e_gerar(client, issue_token)

    resposta = listar(client, issue_token)
    assert "rows" not in resposta.json()["rows"][0]
    assert "name" not in resposta.json()["rows"][0]
    assert CONTA not in resposta.text


@pytest.mark.parametrize(
    ("filtro", "acha"),
    [
        ({"ano": ANO, "mes": MES}, True),
        ({"ano": ANO, "mes": 8}, False),
        ({"ano": 2025}, False),
        ({"kind": "transport_voucher"}, True),
        ({"kind": "food_basket"}, False),
        ({"situacao": "generated"}, True),
        ({"situacao": "draft"}, False),
        ({}, True),
    ],
)
def test_a_lista_filtra_por_competencia_e_situacao(
    client: TestClient, issue_token: Any, fake_db: FakeDB, filtro: dict[str, Any], acha: bool
) -> None:
    cenario_vt(fake_db)
    apurar_e_gerar(client, issue_token)

    encontrados = listar(client, issue_token, **filtro).json()["rows"]
    assert bool(encontrados) is acha


def test_o_resumo_separa_quem_tem_direito_de_quem_perdeu(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ O `filter (where b.entitled)` do agregado, exercitado.

    Sem ele os dois contadores viram o mesmo número e a lista diz "142 com
    direito" sobre uma competência em que 30 perderam. `test_o_resumo_da_lista_bate_com_o_detalhe`
    não pega sozinho: numa competência em que ninguém perde, contar todos e
    contar os com direito dá o mesmo.
    """
    cenario_vt(fake_db)
    # Bruno perde: admitido depois, sem dias líquidos suficientes na janela.
    fake_db.semear_pessoa(pessoa(BRUNO, "Bruno Alves", hired_on=date(2026, 9, 18)))
    fake_db.semear_escala(escala(date(2026, 9, 18), VT_FIM, employee_id=BRUNO))
    fake_db.semear_atribuicao(atribuicao(employee_id=BRUNO))
    fake_db.afastamentos_dominio.append(
        {
            "tenant_id": TENANT_ID,
            "employee_id": BRUNO,
            "starts_on": date(2026, 7, 1),
            "ends_on": date(2026, 7, 31),
            "category": ciclo.UNJUSTIFIED_ABSENCE,
        }
    )
    apurar(client, issue_token)

    resumo = listar(client, issue_token).json()["rows"][0]
    assert resumo["entitled_count"] == 1
    assert resumo["denied_count"] == 1


def test_o_agregado_nao_soma_linha_de_outro_tenant(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """O `and b.tenant_id = c.tenant_id` do lateral, exercitado.

    ⚠️ Pelo produto isto é inalcançável — o lateral casa por `c.id`, que é chave
    primária. Alcançável por dado ruim: `app.benefit_entitlement` tem `tenant_id`
    próprio e nada obriga que ele seja o do ciclo. Uma linha com o tenant errado
    inflaria a contagem e o total da competência de outro cliente, calada.
    """
    cenario_vt(fake_db)
    ciclo_id = apurar(client, issue_token).json()["id"]
    intrusa = dict(fake_db.linhas[0])
    intrusa["tenant_id"] = OUTRO_TENANT
    intrusa["employee_id"] = BRUNO
    fake_db.linhas.append(intrusa)
    fake_db.semear_pessoa(pessoa(BRUNO, "Bruno Alves"), tenant_id=OUTRO_TENANT)

    resumo = next(
        linha for linha in listar(client, issue_token).json()["rows"] if linha["id"] == ciclo_id
    )
    assert resumo["entitled_count"] == 1
    assert Decimal(str(resumo["total_amount"])) == Decimal("161.50")


def test_a_lista_nao_devolve_competencia_de_outro_tenant(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    cenario_vt(fake_db)
    apurar_e_gerar(client, issue_token)
    for linha in fake_db.ciclos:
        linha["tenant_id"] = OUTRO_TENANT

    assert listar(client, issue_token).json()["rows"] == []


def test_a_lista_exige_compensation(client: TestClient, issue_token: Any, fake_db: FakeDB) -> None:
    cenario_vt(fake_db)
    fake_db.compensation = False
    assert listar(client, issue_token).status_code == 403


def test_a_lista_nao_exige_admin(client: TestClient, issue_token: Any, fake_db: FakeDB) -> None:
    """⛔ É METADE DO MOTIVO DE ESTA ROTA EXISTIR.

    `accounting` baixa a remessa sem ser admin — decisão do S3 — e não tinha por
    onde chegar a um ciclo: o `id` só nascia no `POST`, que exige admin. Exigir
    admin aqui devolveria a mesma parede uma porta adiante.
    """
    cenario_vt(fake_db)
    apurar_e_gerar(client, issue_token)
    fake_db.admin = False

    resposta = listar(client, issue_token)
    assert resposta.status_code == 200
    assert len(resposta.json()["rows"]) == 1


@pytest.mark.parametrize(
    ("banking", "admin"),
    [(True, True), (True, False), (False, True), (False, False)],
)
def test_o_botao_e_a_guarda_concordam(
    client: TestClient, issue_token: Any, fake_db: FakeDB, banking: bool, admin: bool
) -> None:
    """⛔ A ARMADILHA DESTA MUDANÇA, PERCORRIDA NA MATRIZ INTEIRA.

    Um `can_export_remittance` que a rota calcula e que a guarda real não usa
    seria pior que campo nenhum: a tela esconde o botão e o endpoint continua
    aceitando — trava de mentira, do tipo que só se descobre quando alguém digita
    a URL. Aqui as duas respostas saem de `pode_exportar_remessa`, e esta
    asserção exige que **concordem nos quatro cantos**.

    O par `(banking=True, admin=False)` é o que reprova a troca do eixo por
    `is_admin`: é o `accounting`, que confere a remessa e não apura nada.
    """
    cenario_remessa(fake_db)
    ciclo_id = apurar_e_gerar(client, issue_token)
    fake_db.banking, fake_db.admin = banking, admin

    campo = listar(client, issue_token).json()["can_export_remittance"]
    resposta = client.get(
        f"/dp/ciclos/{ciclo_id}/export?formato=banco", headers=cabecalho(issue_token)
    )

    assert campo is banking, "o campo não reflete o domínio bancário"
    # Quem vê o botão baixa; quem não vê leva 403 se chamar a rota direto.
    assert (resposta.status_code == 200) is campo
    if not campo:
        assert resposta.status_code == 403
        assert CONTA not in resposta.text


def test_o_detalhe_do_ciclo_tambem_carrega_o_eixo_da_remessa(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """As três respostas de ciclo trazem o campo — a tela de detalhe também tem botão."""
    cenario_vt(fake_db)
    apurado = apurar(client, issue_token)
    ciclo_id = apurado.json()["id"]
    gerado = client.post(f"/dp/ciclos/{ciclo_id}/gerar", headers=cabecalho(issue_token))

    assert apurado.json()["can_export_remittance"] is True
    assert gerado.json()["can_export_remittance"] is True


# ---------------------------------------------------------------------------
# 9. O contrato do schema — a ausência do campo é a garantia
# ---------------------------------------------------------------------------
def test_a_linha_do_ciclo_nao_tem_campo_de_conta() -> None:
    """⛔ Nenhuma rota poderia devolver a conta nem querendo: não há onde pô-la."""
    from server.models import CycleEntitlementRow

    campos = set(CycleEntitlementRow.model_fields)
    assert not [nome for nome in campos if "account" in nome or "conta" in nome]
    assert not [nome for nome in campos if "branch" in nome or "bank" in nome]


# ---------------------------------------------------------------------------
# 10. Multi-tenant
# ---------------------------------------------------------------------------
_JOIN = re.compile(
    r"\b(?:left\s+|inner\s+)?join\s+(?:app|secullum)\.[\w\".]+\s+(\w+)\s+on\b"
    r"(?P<on>.*?)(?=\n\s*(?:left\s+join|inner\s+join|join|where|order|group|limit)\b|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def test_todo_join_do_apurador_propaga_o_tenant() -> None:
    """⛔ O LADO NÃO FILTRADO DO `join` — a fuga que o dublê declara NÃO pegar.

    `where eb.tenant_id = %(tenant_id)s` recorta o lado de dentro e diz nada
    sobre o de fora: `on bt.id = eb.benefit_type_id` casa por uuid e mais nada.
    Hoje é inalcançável (uuid não colide), e o efeito não seria silencioso — o
    `code` de tarifa alheia chegaria à mensagem de `MissingFareError`, que vai
    para a resposta. Nenhuma inspeção de string alcança isso, então a garantia é
    esta: **toda** tabela que entra por `join` traz o `tenant_id` do alias dela
    no `on`. Uma linha por join, e a asserção fica vermelha quando alguém a
    esquece — inclusive num `join` que ainda não existe.
    """
    fonte = inspect.getsource(ciclo)
    joins = list(_JOIN.finditer(fonte))
    # ⛔ CONTAGEM EXATA, E ELA É O PREÇO DE UMA GUARDA POR TEXTO
    # Medido: trocar dois `join` por vírgula no `from` sai do alcance do parser e
    # a varredura fica verde — a fuga é implausível como descuido, mas existe.
    # Com o número exato, QUALQUER mudança no conjunto de joins passa por aqui de
    # propósito: acrescentou um, acrescente o `tenant_id` nele e ajuste este
    # número. `>=` deixaria a remoção por vírgula passar, que foi como esta linha
    # nasceu verde na primeira versão.
    assert len(joins) == 7, (
        f"o apurador tem {len(joins)} joins e esta guarda conhece 7; "
        f"se você acrescentou um, propague o tenant nele e ajuste o número — "
        f"se removeu, confira se não virou vírgula no `from`, que foge desta varredura"
    )
    for join in joins:
        alias = join.group(1)
        assert f"{alias}.tenant_id" in join.group("on"), (
            f"o join de `{alias}` casa só por id: uma linha de outro tenant entraria "
            f"pelo lado de fora do `where`. ON: {' '.join(join.group('on').split())}"
        )


def test_afastamento_de_outro_tenant_nao_para_a_apuracao(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ A justificativa não curada de OUTRO cliente não pode travar este.

    Sem o filtro de tenant na leitura do espelho, a curadoria de um cliente
    passaria a depender do texto livre digitado por outro.
    """
    cenario_vt(fake_db)
    fake_db.semear_afastamento(
        afastamento("ATEST M", date(2026, 7, 10), date(2026, 7, 11)), tenant_id=OUTRO_TENANT
    )
    assert apurar(client, issue_token).status_code == 201


def test_colaborador_de_outro_tenant_nao_entra_no_ciclo(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    cenario_vt(fake_db)
    fake_db.semear_pessoa(pessoa(BRUNO, "Bruno Alves"), tenant_id=OUTRO_TENANT)
    fake_db.semear_escala(escala(VT_INICIO, VT_FIM, employee_id=BRUNO), tenant_id=OUTRO_TENANT)
    fake_db.semear_atribuicao(atribuicao(employee_id=BRUNO), tenant_id=OUTRO_TENANT)

    corpo = apurar(client, issue_token).json()
    assert [linha["name"] for linha in corpo["rows"]] == ["Ana Ribeiro"]
