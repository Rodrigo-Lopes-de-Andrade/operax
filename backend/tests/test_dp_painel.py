"""O gate do S4 do lado do Python: a unidade de atuação e os nove KPIs.

⛔ POR QUE OS NOVE KPIs SÃO PROVADOS POR FIXTURE SINTÉTICA
O gate do plano diz "os 9 KPIs batem com o legado sobre a mesma base" — e **não
há export do legado no repositório**. Medido no despacho do S4, em 06/09/2026. O
`ANEXO` §2a traz as fórmulas declaradas na própria tela, então elas são
transcritas e exercitadas aqui; a **conferência contra o legado fica ABERTA**,
como ficou no S3. Inventar um "legado" sintético para comparar seria
auto-consistência disfarçada de reconciliação.

⛔ O DEFEITO QUE ESTE ARQUIVO EXISTE PARA NÃO REPETIR
`GET /dp/ciclos` recebia um filtro de mês, passava o parâmetro e o SQL não tinha
a cláusula: `psycopg` não reclama de chave que o SQL não usa, e o filtro era
ignorado em silêncio. Aqui o recorte é em Python, o que muda a forma do defeito e
não a existência dele — um `_no_filtro` que devolvesse `True` sempre teria a
mesma cara. Por isso todo filtro é testado com um par: **o que entra** e **o que
some**, e nunca só a contagem total.

A PERGUNTA DO FALSO VERDE, APLICADA AQUI
"O desligado não entra na folha" é satisfeito por um cálculo que não soma
ninguém. Então cada exclusão vem com o valor positivo ao lado: a folha de quem
ficou é conferida na vírgula, e o desligado aparece em `total_analyzed` e em
`terminations` — some de um número e continua existindo nos outros dois.

O QUE ESTA SUÍTE **NÃO** PROVA, E ONDE ISSO É PROVADO
O dublê responde por trecho de statement e devolve linhas plausíveis: ele modela
o filtro de tenant, e falha alto quando falta. Ele **não** decide nada de
negócio — devolve as parcelas com os dois `status` e deixa `compute_panel`
filtrar. Foi assim que os literais de "parcela em aberto" saíram do SQL, onde
nenhum teste os alcançava, e passaram a morrer sob mutação.
Os oito contadores de alerta são de SQL e vivem em `scripts/87_teste_painel_dp.sql`,
contra Postgres de verdade, com dois usuários — esta suíte não abre banco.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from operax.dp import banking, beneficios, painel
from operax.rh import repository as rh_repository
from tests.conftest import TENANT_ID
from tests.test_dp_ciclo import FakeCursor, FakeScope, cabecalho

OUTRO_TENANT = UUID("33333333-3333-4333-8333-000000000003")

ANA = UUID("aaaa0000-0000-4000-8000-000000000001")
BRUNO = UUID("aaaa0000-0000-4000-8000-000000000002")
CARLA = UUID("aaaa0000-0000-4000-8000-000000000003")

LOTACAO = UUID("bbbb0000-0000-4000-8000-000000000001")
DESTINO = UUID("bbbb0000-0000-4000-8000-000000000002")
TERCEIRA = UUID("bbbb0000-0000-4000-8000-000000000003")

POSTO = UUID("cccc0000-0000-4000-8000-000000000001")
OUTRO_POSTO = UUID("cccc0000-0000-4000-8000-000000000002")

EMPRESA = UUID("eeee0000-0000-4000-8000-000000000001")
OUTRA_EMPRESA = UUID("eeee0000-0000-4000-8000-000000000002")

HOJE = date(2026, 9, 7)


# ---------------------------------------------------------------------------
# Fixtures sintéticas — as linhas como o `select` as devolve
# ---------------------------------------------------------------------------
def pessoa(
    employee_id: UUID = ANA,
    nome: str = "Ana Ribeiro",
    *,
    status: str = "active",
    unit_id: UUID | None = LOTACAO,
    company_id: UUID = EMPRESA,
) -> dict[str, Any]:
    return {
        "employee_id": employee_id,
        "name": nome,
        "status": status,
        "company_id": company_id,
        "unit_id": unit_id,
    }


def movimentacao(
    *,
    employee_id: UUID = ANA,
    destino: UUID | None = DESTINO,
    posto: UUID | None = POSTO,
    desde: date | None = date(2026, 1, 1),
    ate: date | None = None,
) -> dict[str, Any]:
    return {
        "employee_id": employee_id,
        "destination_unit_id": destino,
        "destination_work_post_id": posto,
        "effective_from": desde,
        "effective_to": ate,
    }


def faixa(
    salario: str,
    *,
    employee_id: UUID = ANA,
    desde: date = date(2020, 1, 1),
    ate: date | None = None,
) -> dict[str, Any]:
    return {
        "employee_id": employee_id,
        "effective_from": desde,
        "effective_to": ate,
        "salary": Decimal(salario),
    }


def verba(
    code: str,
    *,
    employee_id: UUID = ANA,
    composes_base: bool = True,
    amount: str | None = None,
    rate: str | None = None,
    quantity: int | None = None,
    desde: date = date(2020, 1, 1),
    ate: date | None = None,
) -> dict[str, Any]:
    return {
        "employee_id": employee_id,
        "effective_from": desde,
        "effective_to": ate,
        "amount": Decimal(amount) if amount is not None else None,
        "rate": Decimal(rate) if rate is not None else None,
        "quantity": quantity,
        "code": code,
        "name": code,
        "composes_base": composes_base,
        "calculation": beneficios.SALARY_RATE if rate is not None else beneficios.FIXED_AMOUNT,
    }


#: A folha da Ana, como o `ANEXO` §2a a declara: salário + ajuda de custo +
#: cargo de confiança + periculosidade, com o VR **fora**.
#:   3000 + 500 + 200 + (30% de 3000 = 900) = 4600 · VR = 600
def verbas_da_ana() -> list[dict[str, Any]]:
    return [
        verba(painel.COST_ALLOWANCE, amount="500.00"),
        verba("trust_position", amount="200.00"),
        verba("hazard_pay", rate="0.30", quantity=1),
        verba(painel.MEAL_VOUCHER, composes_base=False, amount="600.00"),
    ]


def parcela(
    *,
    employee_id: UUID = ANA,
    installment_status: str = "pending",
    agreement_status: str = "active",
) -> dict[str, Any]:
    """Uma parcela de acordo, com os DOIS status que a consulta filtra."""
    return {
        "employee_id": employee_id,
        "installment_status": installment_status,
        "agreement_status": agreement_status,
    }


# ---------------------------------------------------------------------------
# 1. A unidade de atuação — SPEC §1g, transcrita
# ---------------------------------------------------------------------------
def um(employees: list[dict[str, Any]], movements: list[dict[str, Any]]) -> painel.Placement:
    return painel.resolve_acting_placement(employees, movements, HOJE)[ANA]


def test_sem_movimentacao_a_atuacao_e_a_lotacao() -> None:
    assert um([pessoa()], []) == painel.Placement(unit_id=LOTACAO, work_post_id=None)


def test_movimentacao_vigente_em_aberto_projeta_destino_e_posto() -> None:
    """⛔ Os dois juntos: a tela do legado atualiza unidade e posto no mesmo ato."""
    assert um([pessoa()], [movimentacao()]) == painel.Placement(unit_id=DESTINO, work_post_id=POSTO)


def test_movimentacao_com_fim_no_futuro_ainda_projeta() -> None:
    """ "sem `effective_to`, ou com `effective_to` no futuro" — a segunda metade."""
    fim_futuro = movimentacao(ate=date(2026, 12, 31))
    assert um([pessoa()], [fim_futuro]).unit_id == DESTINO


def test_movimentacao_que_termina_hoje_ainda_projeta() -> None:
    """`effective_to` é inclusivo, como toda vigência desta etapa (`in_effect`).

    O último dia do remanejamento é dia de trabalho na unidade de destino: quem
    tratar a data como exclusiva devolve a pessoa à lotação um dia cedo demais.
    """
    assert um([pessoa()], [movimentacao(ate=HOJE)]).unit_id == DESTINO


def test_movimentacao_encerrada_no_passado_devolve_a_lotacao() -> None:
    encerrada = movimentacao(ate=date(2026, 8, 31))
    assert um([pessoa()], [encerrada]) == painel.Placement(unit_id=LOTACAO, work_post_id=None)


def test_movimentacao_que_ainda_nao_comecou_nao_projeta() -> None:
    """⛔ O CASO QUE A LEITURA LITERAL DO PARÊNTESE ERRA.

    A regra escrita diz "sem `effective_to`, ou com `effective_to` no futuro" e
    não menciona o começo — quem a ler ao pé da letra projeta um remanejamento
    agendado para o mês que vem, e a ficha muda antes de a pessoa se mudar.
    """
    agendada = movimentacao(desde=date(2026, 10, 1))
    assert um([pessoa()], [agendada]).unit_id == LOTACAO


def test_entre_duas_vigentes_vale_a_mais_recente() -> None:
    antiga = movimentacao(destino=TERCEIRA, posto=OUTRO_POSTO, desde=date(2026, 1, 1))
    nova = movimentacao(destino=DESTINO, posto=POSTO, desde=date(2026, 6, 1))
    assert um([pessoa()], [antiga, nova]) == painel.Placement(unit_id=DESTINO, work_post_id=POSTO)


def test_movimentacao_sem_destino_nao_desfaz_o_remanejamento() -> None:
    """⛔ PROMOÇÃO NÃO É MUDANÇA DE LUGAR.

    `app.workforce_movement` guarda admissão, promoção e desligamento, que não
    têm destino. Quem tomar "a movimentação vigente mais recente" sem olhar o
    destino devolve a pessoa à lotação no dia em que ela é promovida.
    """
    remanejamento = movimentacao(desde=date(2026, 1, 1))
    promocao = movimentacao(destino=None, posto=None, desde=date(2026, 6, 1))
    assert um([pessoa()], [remanejamento, promocao]).unit_id == DESTINO


def test_movimentacao_sem_vigencia_declarada_e_ignorada() -> None:
    """A linha antiga — evento, não período — não tem `effective_from`."""
    evento = movimentacao(desde=None)
    assert um([pessoa()], [evento]).unit_id == LOTACAO


def test_movimentacao_de_outra_pessoa_nao_muda_a_minha() -> None:
    """O par positivo do agrupamento: Bruno se move, Ana fica."""
    lugares = painel.resolve_acting_placement(
        [pessoa(), pessoa(BRUNO, "Bruno Alves")],
        [movimentacao(employee_id=BRUNO)],
        HOJE,
    )
    assert lugares[BRUNO].unit_id == DESTINO
    assert lugares[ANA].unit_id == LOTACAO


def test_pessoa_sem_lotacao_e_sem_movimentacao_fica_sem_unidade() -> None:
    """Mapeamento pendente é `unit_id` nulo. Ele não vira unidade nenhuma."""
    assert um([pessoa(unit_id=None)], []) == painel.Placement(unit_id=None, work_post_id=None)


# ---------------------------------------------------------------------------
# 2. Os nove KPIs — ANEXO §2a, transcritos
# ---------------------------------------------------------------------------
def kpis(**overrides: Any) -> painel.PanelKpis:
    argumentos: dict[str, Any] = {
        "employees": [pessoa()],
        "movements": [],
        "salary_bands": [faixa("3000.00")],
        "benefits": verbas_da_ana(),
        "installments": [],
    }
    argumentos |= overrides
    return painel.compute_panel(
        HOJE,
        argumentos["employees"],
        argumentos["movements"],
        argumentos["salary_bands"],
        argumentos["benefits"],
        argumentos["installments"],
        unit_id=argumentos.get("unit_id"),
        company_id=argumentos.get("company_id"),
    )


def test_folha_base_e_salario_mais_ajuda_cargo_e_periculosidade() -> None:
    """⛔ A FÓRMULA DECLARADA NA TELA, NA VÍRGULA (`ANEXO` §2a).

    3000 (salário) + 500 (ajuda de custo) + 200 (cargo de confiança)
    + 900 (periculosidade, 30% do salário) = 4600. O VR de 600 fica **fora**.
    """
    assert kpis().base_payroll == Decimal("4600.00")


def test_o_vr_sai_da_base_e_aparece_no_cartao_dele() -> None:
    """O par positivo de "o VR fica fora": ele não some do painel, muda de cartão."""
    resultado = kpis()
    assert resultado.meal_voucher == Decimal("600.00")
    assert resultado.base_payroll == Decimal("4600.00")


def test_quem_decide_a_base_e_a_coluna_composes_base_e_nao_o_codigo() -> None:
    """⛔ A MUTAÇÃO QUE O S1 DEIXOU ESCRITA, EXERCIDA AQUI.

    Virar `composes_base` do VR muda o total — porque quem decide é a coluna, que
    o cliente edita, e não uma lista de códigos em Python. Se algum dia a base
    passar a sair de `painel.MEAL_VOUCHER` e amigos, este teste fica verde com o
    produto errado, então ele compara os DOIS totais.
    """
    com_vr_na_base = [
        {**v, "composes_base": True} if v["code"] == painel.MEAL_VOUCHER else v
        for v in verbas_da_ana()
    ]
    assert kpis(benefits=com_vr_na_base).base_payroll == Decimal("5200.00")
    # E o cartão do VR continua mostrando o VR: ele mudou de lado, não sumiu.
    assert kpis(benefits=com_vr_na_base).meal_voucher == Decimal("600.00")


def test_periculosidade_e_valorizada_pela_taxa_e_nao_pelo_amount() -> None:
    """⛔ `hazard_pay` é `salary_rate`: `amount` é nulo.

    Um cartão que somasse `amount` daria ZERO aqui e ninguém veria — o número
    menor tem cara de número. Os dois cartões usam `beneficios.value_component`,
    a mesma função da folha base.
    """
    assert kpis().trust_and_hazard == Decimal("1100.00")  # 200 de cargo + 900 de periculosidade


def test_ajuda_de_custo_tem_cartao_proprio_dentro_da_base() -> None:
    assert kpis().cost_allowance == Decimal("500.00")


def test_verba_fora_de_vigencia_nao_entra_em_cartao_nenhum() -> None:
    """O negativo com o positivo ao lado: a mesma verba, encerrada, sai de tudo."""
    encerradas = [{**v, "effective_to": date(2026, 8, 31)} for v in verbas_da_ana()]
    resultado = kpis(benefits=encerradas)
    assert resultado.base_payroll == Decimal("3000.00")
    assert resultado.meal_voucher == Decimal("0")
    assert resultado.trust_and_hazard == Decimal("0")
    assert resultado.cost_allowance == Decimal("0")


def test_desligado_sai_da_folha_e_continua_no_total_e_nos_desligamentos() -> None:
    """⛔ "só ativos" é uma exclusão, e exclusão sem par fica verde num cálculo vazio.

    Carla tem salário maior que a folha inteira: se ela entrasse, o total mudaria.
    Ela não entra — e ainda assim aparece em `total_analyzed` e em `terminations`.
    """
    resultado = kpis(
        employees=[pessoa(), pessoa(CARLA, "Carla Dias", status="desligado")],
        salary_bands=[faixa("3000.00"), faixa("9000.00", employee_id=CARLA)],
    )
    assert resultado.base_payroll == Decimal("4600.00")
    assert resultado.total_analyzed == 2
    assert resultado.active_headcount == 1
    assert resultado.terminations == 1


def test_afastado_e_em_ferias_continuam_no_efetivo() -> None:
    """`status` tem quatro valores, e só um deles tira do efetivo.

    Quem está de férias custa folha. Um `status = 'active'` no lugar de
    `status <> 'desligado'` encolheria o efetivo e a folha na mesma leitura.
    """
    resultado = kpis(
        employees=[
            pessoa(status="afastado"),
            pessoa(BRUNO, "Bruno Alves", status="vacation"),
        ],
        salary_bands=[faixa("3000.00"), faixa("2000.00", employee_id=BRUNO)],
        benefits=verbas_da_ana(),
    )
    assert resultado.active_headcount == 2
    assert resultado.base_payroll == Decimal("6600.00")


def test_retencao_e_ativos_sobre_o_total_do_filtro() -> None:
    """⚠️ TRANSCRITA DO LEGADO, E NÃO CONSERTADA.

    O `ANEXO` §2a registra que `ativos / total` **não é retenção**. A fórmula
    está aqui porque é contra ela que o gate compara; o rótulo é canetada de
    produto, pendente do dono. Quem "arrumar" isto sem decisão quebra o gate.
    """
    resultado = kpis(
        employees=[
            pessoa(),
            pessoa(BRUNO, "Bruno Alves"),
            pessoa(CARLA, "Carla Dias", status="desligado"),
        ],
        salary_bands=[faixa("3000.00")],
    )
    assert resultado.retention == Decimal("0.6667")


def test_retencao_de_base_vazia_e_nula_e_nao_zero() -> None:
    """Zero diria "nenhuma retenção" sobre uma base em que não há ninguém."""
    vazio = kpis(employees=[], salary_bands=[], benefits=[])
    assert vazio.retention is None
    assert vazio.base_payroll_average is None
    assert vazio.base_payroll == Decimal("0")


def test_media_divide_a_folha_pelos_ativos_e_o_cadastro_incompleto_e_nomeado() -> None:
    """⚠️ O DENOMINADOR É "ATIVOS", NÃO "ATIVOS COM SALÁRIO".

    É a aritmética do legado. Bruno não tem faixa salarial: ele derruba a média e
    aparece em `without_salary`, que é o que impede o número menor de passar por
    número certo.
    """
    resultado = kpis(employees=[pessoa(), pessoa(BRUNO, "Bruno Alves")])
    assert resultado.base_payroll == Decimal("4600.00")
    assert resultado.base_payroll_average == Decimal("2300.00")
    assert resultado.without_salary == 1


def test_o_cartao_de_sinistro_conta_unidades_e_nao_pessoas() -> None:
    """⛔ CONTAGEM (`ANEXO` §2b). Duas pessoas na mesma unidade são UMA unidade."""
    resultado = kpis(
        employees=[pessoa(), pessoa(BRUNO, "Bruno Alves")],
        installments=[parcela(), parcela(employee_id=BRUNO)],
    )
    assert resultado.units_with_open_installment == 1


def test_o_cartao_de_sinistro_separa_unidades_distintas() -> None:
    """E o par positivo: unidades diferentes contam duas — senão bastaria `1`."""
    resultado = kpis(
        employees=[pessoa(), pessoa(BRUNO, "Bruno Alves", unit_id=DESTINO)],
        installments=[parcela(), parcela(employee_id=BRUNO)],
    )
    assert resultado.units_with_open_installment == 2


def test_o_sinistro_segue_a_unidade_de_atuacao_e_nao_a_lotacao() -> None:
    """As duas pessoas são da mesma lotação; uma foi remanejada. São duas unidades."""
    resultado = kpis(
        employees=[pessoa(), pessoa(BRUNO, "Bruno Alves")],
        movements=[movimentacao(employee_id=BRUNO)],
        installments=[parcela(), parcela(employee_id=BRUNO)],
    )
    assert resultado.units_with_open_installment == 2


def test_quem_nao_tem_parcela_em_aberto_nao_conta_unidade() -> None:
    assert kpis(installments=[]).units_with_open_installment == 0


def test_parcela_processada_nao_acende_o_cartao_e_a_pendente_acende() -> None:
    """⛔ OS DOIS `status` DE "PARCELA EM ABERTO", EXERCIDOS EM PAR.

    Eram dois literais dentro do SQL até 07/09/2026, e nenhum teste os alcançava
    — mutar qualquer um deixava a suíte inteira verde. A regra mudou de lugar
    (para `compute_panel`) exatamente para caber aqui: parcela já processada foi
    descontada, e acordo quitado não deve nada. Contar qualquer um dos dois
    acende o cartão de sinistro de uma unidade que está em dia.
    """
    assert (
        kpis(installments=[parcela(installment_status="processed")]).units_with_open_installment
        == 0
    )
    assert kpis(installments=[parcela(agreement_status="settled")]).units_with_open_installment == 0
    # O positivo ao lado, senão os dois acima ficariam verdes num cartão que
    # nunca acende.
    assert kpis(installments=[parcela()]).units_with_open_installment == 1


def test_taxa_malformada_de_quem_nao_tem_faixa_nao_derruba_o_painel() -> None:
    """⚠️ A GUARDA DE `salary_rate` SEM FAIXA, E O QUE ELA DE FATO COMPRA.

    Não é o número: 30% de um salário ausente somaria zero de qualquer jeito. É a
    exceção — `value_component` falha alto quando uma verba de taxa não declara
    `rate` ou `quantity`, e sem a guarda o cadastro incompleto de alguém que nem
    está na folha derrubaria o painel inteiro, com um 500 em vez de um cartão.

    Bruno é ativo, não tem faixa salarial e tem uma periculosidade sem
    `quantity`. O painel responde, e o número de Ana continua certo.
    """
    resultado = kpis(
        employees=[pessoa(), pessoa(BRUNO, "Bruno Alves")],
        benefits=[
            *verbas_da_ana(),
            {**verba("hazard_pay", employee_id=BRUNO, rate="0.30"), "quantity": None},
        ],
    )
    assert resultado.trust_and_hazard == Decimal("1100.00")


# ---------------------------------------------------------------------------
# 2-bis. Os três cartões de verba — a população é "ativo", não "ativo com faixa"
# ---------------------------------------------------------------------------
def test_vr_de_quem_nao_tem_faixa_salarial_continua_no_cartao() -> None:
    """⛔ O DEFEITO QUE O REVISOR MEDIU EM 07/09/2026.

    A versão anterior exigia salário para somar QUALQUER verba, com a razão
    "sem salário não há como valorizar taxa" — verdadeira para `salary_rate` e
    **falsa para `fixed_amount`**, que nem olha o salário. O VR de quem está sem
    faixa cadastrada sumia do cartão em silêncio, e `without_salary` explica o
    total da folha, não o dos cartões.

    Bruno é ativo, não tem faixa salarial e tem VR de 250: o cartão soma 850.
    """
    resultado = kpis(
        employees=[pessoa(), pessoa(BRUNO, "Bruno Alves")],
        benefits=[
            *verbas_da_ana(),
            verba(painel.MEAL_VOUCHER, employee_id=BRUNO, composes_base=False, amount="250.00"),
        ],
    )
    assert resultado.meal_voucher == Decimal("850.00")
    # E ele continua fora da folha base, que é datada e exige faixa vigente — as
    # duas exclusões são de perguntas diferentes.
    assert resultado.base_payroll == Decimal("4600.00")
    assert resultado.without_salary == 1


def test_verba_de_taxa_sem_faixa_salarial_fica_de_fora_e_e_a_unica_exclusao() -> None:
    """⚠️ 30% DE UM SALÁRIO DESCONHECIDO NÃO TEM VALOR.

    O par negativo do teste acima, e a divergência que sobra declarada: a
    periculosidade de Bruno não entra porque não há de que tirar percentual —
    chutar zero seria inventar um número. `without_salary` é a explicação, e
    aqui ela é de fato a explicação certa.
    """
    resultado = kpis(
        employees=[pessoa(), pessoa(BRUNO, "Bruno Alves")],
        benefits=[
            *verbas_da_ana(),
            verba("hazard_pay", employee_id=BRUNO, rate="0.30", quantity=1),
        ],
    )
    assert resultado.trust_and_hazard == Decimal("1100.00")
    assert resultado.without_salary == 1


def test_verba_de_desligado_nao_entra_em_cartao_nenhum() -> None:
    """ "soma mensal, ativos" (`ANEXO` §2a) — e o positivo de Ana ao lado.

    Sem esta linha, trocar a população dos cartões por "todo mundo do filtro"
    passaria verde: o desligado não tem faixa vigente na fixture, e a exclusão
    antiga o pegava por acidente.
    """
    resultado = kpis(
        employees=[pessoa(), pessoa(CARLA, "Carla Dias", status="desligado")],
        salary_bands=[faixa("3000.00"), faixa("9000.00", employee_id=CARLA)],
        benefits=[
            *verbas_da_ana(),
            verba(painel.MEAL_VOUCHER, employee_id=CARLA, composes_base=False, amount="999.00"),
        ],
    )
    assert resultado.meal_voucher == Decimal("600.00")


# ---------------------------------------------------------------------------
# 3. O filtro — o defeito mais barato desta etapa
# ---------------------------------------------------------------------------
def test_filtro_por_unidade_usa_a_atuacao_e_nao_a_lotacao() -> None:
    """⛔ É PARA ISTO QUE A SPEC §1g EXISTE.

    Ana está lotada em LOTACAO e atuando em DESTINO. Filtrar por DESTINO tem de
    trazê-la; filtrar por LOTACAO tem de deixá-la de fora. Um filtro que lesse
    `employee.unit_id` daria exatamente o contrário, e as duas asserções abaixo
    são o par que impede um `return True` de passar.
    """
    remanejada = {"employees": [pessoa()], "movements": [movimentacao()]}
    assert kpis(**remanejada, unit_id=DESTINO).total_analyzed == 1
    assert kpis(**remanejada, unit_id=LOTACAO).total_analyzed == 0


def test_filtro_por_unidade_recorta_a_folha_junto() -> None:
    """O filtro não é só contagem: ele muda o dinheiro na mesma leitura."""
    dois = {
        "employees": [pessoa(), pessoa(BRUNO, "Bruno Alves", unit_id=DESTINO)],
        "salary_bands": [faixa("3000.00"), faixa("2000.00", employee_id=BRUNO)],
    }
    assert kpis(**dois).base_payroll == Decimal("6600.00")
    assert kpis(**dois, unit_id=LOTACAO).base_payroll == Decimal("4600.00")
    assert kpis(**dois, unit_id=DESTINO).base_payroll == Decimal("2000.00")


def test_filtro_por_empresa_vem_do_colaborador() -> None:
    """⛔ REGRA 5: a empresa é a do colaborador, nunca a do departamento."""
    duas = {
        "employees": [pessoa(), pessoa(BRUNO, "Bruno Alves", company_id=OUTRA_EMPRESA)],
        "salary_bands": [faixa("3000.00"), faixa("2000.00", employee_id=BRUNO)],
    }
    assert kpis(**duas, company_id=EMPRESA).total_analyzed == 1
    assert kpis(**duas, company_id=OUTRA_EMPRESA).total_analyzed == 1
    assert kpis(**duas).total_analyzed == 2


def test_os_dois_filtros_se_somam() -> None:
    """Empresa certa e unidade errada não devolve ninguém — `and`, não `or`."""
    dois = {"employees": [pessoa()], "movements": []}
    assert kpis(**dois, company_id=EMPRESA, unit_id=LOTACAO).total_analyzed == 1
    assert kpis(**dois, company_id=EMPRESA, unit_id=DESTINO).total_analyzed == 0
    assert kpis(**dois, company_id=OUTRA_EMPRESA, unit_id=LOTACAO).total_analyzed == 0


# ---------------------------------------------------------------------------
# 4. A rota
# ---------------------------------------------------------------------------
class PainelDB:
    """Dublê endereçado por trecho de statement, como o do S3.

    Ele **não** modela `i.status = 'pending'` nem `a.status = 'active'` — ver o
    cabeçalho do arquivo. O que ele modela e o que importa aqui é o filtro de
    tenant, que `FakeCursor` exige e cuja ausência falha alto.
    """

    def __init__(self) -> None:
        self.compensation = True
        self.admin = True
        self.banking = True
        self.colaboradores: list[dict[str, Any]] = []
        self.movimentacoes: list[dict[str, Any]] = []
        self.faixas: list[dict[str, Any]] = []
        self.verbas: list[dict[str, Any]] = []
        self.parcelas: list[dict[str, Any]] = []
        self.statements: list[tuple[str, dict[str, Any]]] = []

    def semear(self, linha: dict[str, Any], onde: str, tenant_id: UUID = TENANT_ID) -> None:
        getattr(self, onde).append({**linha, "tenant_id": tenant_id})

    def _do_tenant(
        self, linhas: list[dict[str, Any]], params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return [dict(linha) for linha in linhas if linha["tenant_id"] == params["tenant_id"]]

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
        # ⚠️ A população roda sob `user_scope` e por isso NÃO carrega tenant: quem
        # recorta é a RLS. O dublê devolve só o tenant do contexto porque é isso
        # que a policy faria — e o teste de vazamento de tenant é o de baixo, que
        # semeia uma linha alheia e confere que ela não chega.
        if "from app.employee e" in sql:
            return [dict(linha) for linha in self.colaboradores if linha["tenant_id"] == TENANT_ID]
        if "from app.workforce_movement m" in sql:
            return self._do_tenant(self.movimentacoes, params)
        if "from app.agreement_installment i" in sql:
            # ⛔ O DUBLÊ DEVOLVE AS LINHAS CRUAS, com os dois `status`, e NÃO
            # filtra: quem decide o que é "parcela em aberto" é
            # `painel.compute_panel`. Um dublê que filtrasse seria a regra
            # escrita no teste, concordando consigo mesma — e foi por isso que os
            # dois literais viveram no SQL sem teste até 07/09/2026.
            return self._do_tenant(self.parcelas, params)
        if "from app.employee_compensation c" in sql:
            return self._do_tenant(self.faixas, params)
        if "from app.employee_benefit eb" in sql:
            return self._do_tenant(self.verbas, params)
        raise AssertionError(f"consulta sem dublê: {sql}")


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> PainelDB:
    estado = PainelDB()

    def tenant_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursor(estado, context, checar_tenant=True))

    def user_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursor(estado, context, checar_tenant=False))

    monkeypatch.setattr(painel, "tenant_scope", tenant_scope)
    monkeypatch.setattr(painel, "user_scope", user_scope)
    monkeypatch.setattr(beneficios, "tenant_scope", tenant_scope)
    monkeypatch.setattr(banking, "tenant_scope", tenant_scope)
    monkeypatch.setattr(banking, "user_scope", user_scope)
    monkeypatch.setattr(rh_repository, "user_scope", user_scope)
    return estado


def cenario(fake_db: PainelDB) -> None:
    """Ana lotada em LOTACAO, atuando em DESTINO, com a folha do `ANEXO` §2a."""
    fake_db.semear(pessoa(), "colaboradores")
    fake_db.semear(movimentacao(), "movimentacoes")
    fake_db.semear(faixa("3000.00"), "faixas")
    for v in verbas_da_ana():
        fake_db.semear(v, "verbas")


def pedir(client: TestClient, issue_token: Any, **query: Any) -> Any:
    return client.get(
        "/dp/painel", params={"em": HOJE.isoformat(), **query}, headers=cabecalho(issue_token)
    )


def test_painel_devolve_os_nove_kpis(
    client: TestClient, issue_token: Any, fake_db: PainelDB
) -> None:
    cenario(fake_db)
    resposta = pedir(client, issue_token)
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["total_analyzed"] == 1
    assert corpo["active_headcount"] == 1
    assert corpo["terminations"] == 0
    assert corpo["retention"] == "1.0000"
    assert corpo["base_payroll"] == "4600.00"
    assert corpo["base_payroll_average"] == "4600.00"
    assert corpo["meal_voucher"] == "600.00"
    assert corpo["cost_allowance"] == "500.00"
    assert corpo["trust_and_hazard"] == "1100.00"
    assert corpo["units_with_open_installment"] == 0


def test_o_filtro_de_unidade_chega_ao_resultado(
    client: TestClient, issue_token: Any, fake_db: PainelDB
) -> None:
    """⛔ O DEFEITO DA SEMANA: parâmetro na assinatura que a consulta ignora.

    Ana atua em DESTINO. Pedir LOTACAO tem de devolver zero — e pedir DESTINO tem
    de devolver Ana. Sem o par, um filtro ignorado passa: os dois pedidos
    devolveriam 1 e o teste ficaria verde.
    """
    cenario(fake_db)
    assert pedir(client, issue_token, unidade=str(DESTINO)).json()["total_analyzed"] == 1
    assert pedir(client, issue_token, unidade=str(LOTACAO)).json()["total_analyzed"] == 0


def test_o_filtro_de_empresa_chega_ao_resultado(
    client: TestClient, issue_token: Any, fake_db: PainelDB
) -> None:
    cenario(fake_db)
    assert pedir(client, issue_token, empresa=str(EMPRESA)).json()["total_analyzed"] == 1
    assert pedir(client, issue_token, empresa=str(OUTRA_EMPRESA)).json()["total_analyzed"] == 0


def test_a_data_pedida_chega_a_vigencia(
    client: TestClient, issue_token: Any, fake_db: PainelDB
) -> None:
    """`em` não é decoração: a folha de uma data anterior à faixa é outra folha."""
    cenario(fake_db)
    antes = client.get(
        "/dp/painel", params={"em": "2019-12-31"}, headers=cabecalho(issue_token)
    ).json()
    # "0" e não "0.00": a folha vazia é o `start=Decimal("0")` de
    # `compute_base_payroll`, que não passa por quantize. Comportamento do S1.
    assert antes["base_payroll"] == "0"
    assert antes["without_salary"] == 1


def test_movimentacao_de_outro_tenant_nao_remaneja_ninguem(
    client: TestClient, issue_token: Any, fake_db: PainelDB
) -> None:
    """O eixo de tenant, exercido no caminho que o `FakeCursor` não cobre sozinho.

    A guarda do dublê prova que a consulta CARREGA o filtro; esta prova que o
    filtro RECORTA — a movimentação alheia existe, e Ana continua na lotação dela.
    """
    cenario(fake_db)
    fake_db.movimentacoes.clear()
    fake_db.semear(movimentacao(), "movimentacoes", tenant_id=OUTRO_TENANT)
    assert pedir(client, issue_token, unidade=str(LOTACAO)).json()["total_analyzed"] == 1
    assert pedir(client, issue_token, unidade=str(DESTINO)).json()["total_analyzed"] == 0


def test_a_parcela_lida_do_banco_chega_ao_cartao(
    client: TestClient, issue_token: Any, fake_db: PainelDB
) -> None:
    """O par acima é puro; este é o encanamento — a linha do banco vira cartão.

    Sem ele, `_OPEN_INSTALLMENTS_SQL` poderia devolver a coluna com outro nome e
    só a rota saberia. Com ele, o `KeyError` aparece aqui.
    """
    cenario(fake_db)
    fake_db.semear(parcela(installment_status="processed"), "parcelas")
    assert pedir(client, issue_token).json()["units_with_open_installment"] == 0

    fake_db.semear(parcela(), "parcelas")
    assert pedir(client, issue_token).json()["units_with_open_installment"] == 1


def test_sem_o_dominio_de_remuneracao_o_painel_nao_abre(
    client: TestClient, issue_token: Any, fake_db: PainelDB
) -> None:
    cenario(fake_db)
    fake_db.compensation = False
    resposta = pedir(client, issue_token)
    assert resposta.status_code == 403
    assert "remuneração" in resposta.json()["detail"]


def test_o_painel_abre_sem_papel_administrativo(
    client: TestClient, issue_token: Any, fake_db: PainelDB
) -> None:
    """O par positivo do 403 acima: `executive` e `accounting` existem para olhá-lo.

    Sem esta linha, "o painel exige compensation" ficaria verde num endpoint que
    exigisse admin também — e trancaria fora exatamente quem ele serve.
    """
    cenario(fake_db)
    fake_db.admin = False
    assert pedir(client, issue_token).status_code == 200


def test_nenhuma_resposta_do_painel_carrega_pessoa(
    client: TestClient, issue_token: Any, fake_db: PainelDB
) -> None:
    """⛔ AGREGADO É AGREGADO (`ANEXO` §2b e regra 7).

    O JSON literal é varrido atrás do nome semeado e do id de todo mundo: o
    cartão de sinistro devolve contagem, e o nome exige abrir a ficha.
    """
    cenario(fake_db)
    fake_db.semear(parcela(), "parcelas")
    corpo = json.dumps(pedir(client, issue_token).json())
    assert "Ana Ribeiro" not in corpo
    assert str(ANA) not in corpo
    assert str(LOTACAO) not in corpo
    # E o cartão continua contando — senão a varredura acima ficaria verde por
    # uma resposta vazia.
    assert pedir(client, issue_token).json()["units_with_open_installment"] == 1
