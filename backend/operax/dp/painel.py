"""O painel de DP: a unidade de atuação derivada e os nove KPIs de topo.

⛔ OS NOVE KPIs VÊM PELO CAMINHO 2, E ISSO FOI DECISÃO, NÃO OMISSÃO
Decisão do dono, 06/09/2026 (`SPRINTS-DP.md`, "Despacho do S4"). A RPC
`public.fn_dp_panel` **não existe** e não deve nascer: a folha base já é
`beneficios.compute_base_payroll`, e o S1 declarou de propósito que a regra de
vigência mora em Python porque *"escrita nos dois lugares ela divergiria, e a
metade SQL é a que o pytest não alcança"*. O `ANEXO` §2a exige que essa soma bata
com a do cliente **na vírgula** — duas implementações de uma conta que precisa
bater na vírgula é o defeito, não a otimização. E é coerente com o Contrato:
folha base é `compensation`, e o Caminho 1 carrega só agregado não sensível.

⛔ NENHUM NOME DE PESSOA SAI DAQUI
Os nove KPIs são números, e o cartão "unidades com sinistro ativo" devolve
**contagem** (`ANEXO` §2b). O painel do legado nomeia quem tem parcela em aberto
na home; no modelo do OperaX isso é conteúdo individual de domínio sensível
exposto num agregado — a mesma classe de problema da regra 7. Quem quer o nome
abre a ficha, com `compensation` revalidado.

⚠️ A UNIDADE DE ATUAÇÃO É LEITURA, NUNCA CAMPO
`resolve_acting_placement` transcreve a regra que a tela do legado declara
(`ANEXO` §4.1, `SPEC-DP.md` §1g). Não há coluna `acting_unit_id` em
`app.employee` e não deve haver: a mesma informação em dois lugares envelhece no
segundo, e bastaria uma movimentação encerrada fora da tela para a ficha apontar
para a unidade errada.

⚠️ O FILTRO É APLICADO SOBRE A POPULAÇÃO JÁ LIDA, E NÃO NUM `where`
Porque a unidade de atuação é derivada: não existe coluna para pôr no `where`.
A empresa acompanha para que o recorte seja **um lugar só** — um filtro metade
em SQL e metade em Python é como se perde um deles em silêncio. O custo é ler o
tenant inteiro; a FastPark tem ~176 colaboradores, e `operax/rh/employees.py` já
opera com esse teto.

⛔ QUEM RECORTA POR ESCOPO É A RLS, NÃO ESTE MÓDULO
A população vem por `user_scope`: quem não enxerga a unidade não recebe a linha,
pela policy `employee_read`. As tabelas de dinheiro (`app.employee_compensation`,
`app.employee_benefit`) vêm por `tenant_scope`, como no S1 — a de verbas não
concede nada a `authenticated` —, e só são usadas para gente que a leitura sob
RLS já devolveu. O agregado nunca soma alguém que quem perguntou não enxerga.

⚠️ E OS DOIS EIXOS DE UNIDADE NÃO SÃO O MESMO — CONSEQUÊNCIA DECLARADA
Autorização é por **lotação**: `util.can_see_employee` decide por
`app.employee.unit_id`, e é ela que a policy consulta. Filtro é por **atuação**:
`_no_filtro` compara `placement.unit_id`. Quem foi remanejado PARA a unidade do
supervisor e continua lotado em outra **não aparece para ele**, nem quando ele
filtra pela própria unidade — o recorte de autorização vem antes e é mais
restritivo. Não é vazamento (nunca mostra a mais); é um número parcial que quem
o lê não tem como saber que é parcial. Fechar isso é mudar `util.can_see_employee`
para enxergar a movimentação, e mudança de policy de RLS é parada obrigatória
(`CLAUDE.md`) — decisão do dono, não daqui. A `dp_movement_period` registra a
consequência gêmea do lado da policy de `app.workforce_movement`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from operax.core.tenant import TenantContext, tenant_scope, user_scope
from operax.dp import beneficios

#: O status que tira a pessoa do efetivo. Os outros três (`active`, `afastado`,
#: `vacation`) continuam sendo vínculo ativo — quem está de férias custa folha.
TERMINATED = "desligado"

#: ⛔ OS CÓDIGOS DOS TRÊS CARTÕES QUE A TELA NOMEIA — E NADA ALÉM DISSO.
#: A folha base **não** sai desta lista: ela sai de `benefit_type.composes_base`,
#: que é coluna e o cliente edita. Uma tupla de códigos decidindo o que compõe a
#: base passaria no teste "VR fica fora" e quebraria no dia em que o cliente
#: criasse a nona verba (ver o cabeçalho de `beneficios.py`). O que estes nomes
#: fazem é só uma coisa: dizer qual verba aparece em qual cartão.
#: Tenant que renomear um código perde o cartão, nunca o total.
MEAL_VOUCHER = "meal_voucher"
COST_ALLOWANCE = "cost_allowance"
TRUST_AND_HAZARD = ("trust_position", "hazard_pay")

#: O par que define "parcela em aberto": parcela pendente de acordo em vigor.
#: `app.agreement_installment.status` aceita
#: ('pending','processed','cancelled','renegotiated') e
#: `app.financial_agreement.status` aceita ('active','settled','cancelled','suspended')
#: — migration 08. Uma parcela processada já foi descontada, e um acordo quitado
#: não deve nada: contar qualquer um dos dois acende o cartão de sinistro de uma
#: unidade que está em dia.
PENDING_INSTALLMENT = "pending"
ACTIVE_AGREEMENT = "active"

_CENTAVOS = Decimal("0.01")
_QUATRO_CASAS = Decimal("0.0001")
_ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# A unidade de atuação — SPEC §1g
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Placement:
    """Onde a pessoa atua hoje: unidade e posto, juntos.

    ⛔ OS DOIS SAEM DA MESMA MOVIMENTAÇÃO, e é por isso que são um objeto e não
    duas funções. A tela do legado atualiza "unidade destino e cód. posto
    destino" no mesmo ato; derivá-los em separado permitiria a uma leitura futura
    pegar o posto de um remanejamento e a unidade de outro — um posto que não
    existe na unidade em que a pessoa aparece.
    """

    unit_id: UUID | None
    work_post_id: UUID | None


def resolve_acting_placement(
    employees: Sequence[Mapping[str, Any]],
    movements: Sequence[Mapping[str, Any]],
    on: date,
) -> dict[UUID, Placement]:
    """A regra da tela, transcrita:

    > unidade de atuação = destino da movimentação vigente (sem `effective_to`,
    > ou com `effective_to` no futuro); na ausência de movimentação, a lotação de
    > `app.employee.unit_id`.

    "Vigente" é `beneficios.in_effect`, a única implementação de "vale nesta
    data" desta etapa: começou e não terminou, com `effective_to` inclusivo. O
    parêntese da regra só detalha o lado do fim — movimentação que **ainda não
    começou** não é vigente, e projetá-la mudaria a ficha antes da hora.

    ⚠️ SÓ MOVIMENTAÇÃO COM DESTINO ENTRA. `app.workforce_movement` guarda também
    admissão, desligamento e promoção, que não têm destino: elas não dizem nada
    sobre onde a pessoa trabalha. Tomar a mais recente sem olhar o destino faria
    uma promoção posterior a um remanejamento devolver a pessoa à lotação antiga.

    Empate em `effective_from` é dado ruim — duas vigências abertas para a mesma
    pessoa. Ganha a primeira lida, e a consulta ordena, para que a resposta ao
    menos seja a mesma em toda leitura.
    """
    por_pessoa: dict[UUID, list[Mapping[str, Any]]] = defaultdict(list)
    for movimento in movements:
        if movimento["destination_unit_id"] is None or movimento["effective_from"] is None:
            continue
        if not beneficios.in_effect(on, movimento["effective_from"], movimento["effective_to"]):
            continue
        por_pessoa[movimento["employee_id"]].append(movimento)

    lotacao: dict[UUID, Placement] = {}
    for employee in employees:
        employee_id = employee["employee_id"]
        vigentes = por_pessoa.get(employee_id)
        if vigentes:
            atual = max(vigentes, key=lambda m: m["effective_from"])
            lotacao[employee_id] = Placement(
                unit_id=atual["destination_unit_id"],
                work_post_id=atual["destination_work_post_id"],
            )
        else:
            lotacao[employee_id] = Placement(unit_id=employee["unit_id"], work_post_id=None)
    return lotacao


# ---------------------------------------------------------------------------
# Os nove KPIs — ANEXO §2a
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PanelKpis:
    """Os nove números do topo do painel, mais dois que a honestidade exige.

    ⚠️ `retention` NÃO É RETENÇÃO, E ISSO ESTÁ REGISTRADO
    O `ANEXO` §2a transcreve a fórmula que a tela do legado declara — `ativos /
    total no filtro` — e registra, na mesma linha, que ela **não é retenção**: é
    a proporção de ativos na base carregada, que muda de significado conforme o
    filtro e some se a base virar histórico completo. Está aqui com a fórmula do
    legado porque é contra ele que o gate compara, e **não foi consertada**: ou
    ela ganha janela declarada ("desligamentos nos últimos 12 meses ÷ efetivo
    médio") ou muda de rótulo, e as duas coisas são canetada de produto,
    pendentes do dono. Quem "arrumar" isto sem decisão quebra o gate.

    `without_salary` não é décimo KPI: é o que explica um total baixo. Uma folha
    base que exclui em silêncio doze cadastros incompletos é degradação
    silenciosa, e o painel diria um número menor com cara de número certo.
    """

    on: date
    #: "registros no filtro corrente" — inclui desligado, que é o que faz a
    #: fórmula de retenção do legado ter denominador.
    total_analyzed: int
    active_headcount: int
    terminations: int
    retention: Decimal | None
    base_payroll: Decimal
    base_payroll_average: Decimal | None
    meal_voucher: Decimal
    cost_allowance: Decimal
    trust_and_hazard: Decimal
    without_salary: int
    #: ⛔ CONTAGEM. O nome de quem tem parcela em aberto não sai do agregado.
    units_with_open_installment: int


def _no_filtro(
    employee: Mapping[str, Any],
    placement: Placement,
    unit_id: UUID | None,
    company_id: UUID | None,
) -> bool:
    """O recorte do painel, num lugar só.

    ⛔ A UNIDADE COMPARADA É A DE ATUAÇÃO, não a lotação: filtrar por unidade e
    receber quem foi remanejado para fora dela é a divergência que a `SPEC-DP.md`
    §1g existe para fechar.

    ⛔ E A EMPRESA VEM DO COLABORADOR — regra 5 do projeto. Nunca por
    departamento: ~26% divergem na FastPark.
    """
    if unit_id is not None and placement.unit_id != unit_id:
        return False
    return not (company_id is not None and employee["company_id"] != company_id)


def _sum_benefit(
    codes: Collection[str],
    benefits: Sequence[Mapping[str, Any]],
    active_ids: Collection[UUID],
    salaries: Mapping[UUID, Decimal],
    on: date,
) -> Decimal:
    """Soma mensal de uma verba sobre os ATIVOS — `ANEXO` §2a, "soma mensal, ativos".

    ⛔ VALORIZADA POR `beneficios.value_component`, a mesma função que a folha
    base usa. Um `sum(amount)` aqui daria **zero** para verba de taxa
    (periculosidade é `salary_rate`, e o valor dela mora em `rate × quantity ×
    salário`) e o cartão mostraria um número menor com cara de número.

    ⛔ A POPULAÇÃO É "ATIVO", E NÃO "ATIVO COM FAIXA SALARIAL VIGENTE"
    Corrigido em 07/09/2026, medido pelo revisor. A versão anterior exigia
    salário para toda verba, com a justificativa "sem salário não há como
    valorizar taxa" — que é verdadeira para `salary_rate` e **falsa para
    `fixed_amount`**: `value_component` nem olha o salário nesse caso. O efeito
    era o VR de quem está sem faixa cadastrada sumir do cartão em silêncio, e
    `without_salary` explica o total da FOLHA, não o dos três cartões.

    ⚠️ VERBA DE TAXA DE QUEM NÃO TEM FAIXA VIGENTE CONTINUA FORA, e o que isso
    muda é MENOS do que parece: 30% de um salário ausente somaria zero de
    qualquer jeito, então o total é o mesmo com ou sem a guarda. O que ela evita
    é outra coisa, e é a razão de ela existir: `value_component` **falha alto**
    quando uma verba de taxa não tem `rate` ou `quantity`, e sem a guarda esse
    cadastro incompleto — de alguém que nem está na folha — derrubaria o painel
    inteiro. Exercitado por `test_taxa_malformada_de_quem_nao_tem_faixa_nao_derruba_o_painel`.
    """
    total = _ZERO
    for verba in benefits:
        if verba["code"] not in codes:
            continue
        if verba["employee_id"] not in active_ids:
            continue
        if not beneficios.in_effect(on, verba["effective_from"], verba["effective_to"]):
            continue
        salary = salaries.get(verba["employee_id"])
        if salary is None:
            if verba["calculation"] == beneficios.SALARY_RATE:
                continue
            # `fixed_amount` ignora o salário — ver `value_component`. O zero
            # aqui não entra em conta nenhuma; ele só satisfaz a assinatura.
            salary = _ZERO
        total += beneficios.value_component(verba, salary).amount
    return total


def compute_panel(
    on: date,
    employees: Sequence[Mapping[str, Any]],
    movements: Sequence[Mapping[str, Any]],
    salary_bands: Sequence[Mapping[str, Any]],
    benefits: Sequence[Mapping[str, Any]],
    installments: Sequence[Mapping[str, Any]],
    *,
    unit_id: UUID | None = None,
    company_id: UUID | None = None,
) -> PanelKpis:
    """Os nove KPIs sobre a população filtrada. Pura de propósito.

    A folha base **não é recalculada aqui**: ela é `compute_base_payroll`, do S1,
    recebendo a população de ativos. O que este módulo acrescenta é o recorte, a
    partição por status e os três cartões que dividem a base em verbas.
    """
    placements = resolve_acting_placement(employees, movements, on)
    selecionados = [
        employee
        for employee in employees
        if _no_filtro(employee, placements[employee["employee_id"]], unit_id, company_id)
    ]

    # ⚠️ ATIVO POR `status`, E NÃO PELA JANELA DE VÍNCULO
    # `compute_base_payroll` decide quem estava na casa em `on` por
    # `hired_on`/`terminated_on`, porque ele lê competência fechada e precisa ser
    # datado. Aqui o eixo é outro: o `ANEXO` §2a declara "vínculos ativos" e
    # aponta a coluna `status`, e é ela que o cliente vê no filtro da tela. As
    # duas leituras coincidem num painel de hoje e divergem numa base com
    # sincronização atrasada — e nesse caso a que o cliente reconhece é esta.
    ativos = [e for e in selecionados if e["status"] != TERMINATED]
    desligados = [e for e in selecionados if e["status"] == TERMINATED]

    payroll = beneficios.compute_base_payroll(on, ativos, salary_bands, benefits)
    salarios = {linha.employee_id: linha.salary for linha in payroll.lines}
    ativos_ids = {e["employee_id"] for e in ativos}

    total = len(selecionados)
    em_aberto = {
        linha["employee_id"]
        for linha in installments
        if linha["installment_status"] == PENDING_INSTALLMENT
        and linha["agreement_status"] == ACTIVE_AGREEMENT
    }
    unidades_com_parcela = {
        placements[e["employee_id"]].unit_id
        for e in selecionados
        if e["employee_id"] in em_aberto and placements[e["employee_id"]].unit_id is not None
    }

    return PanelKpis(
        on=on,
        total_analyzed=total,
        active_headcount=len(ativos),
        terminations=len(desligados),
        retention=(
            None if total == 0 else (Decimal(len(ativos)) / Decimal(total)).quantize(_QUATRO_CASAS)
        ),
        base_payroll=payroll.total,
        # ⚠️ O denominador é "ativos", como a tela declara — e não "ativos com
        # salário". Quem não tem faixa não entra no numerador, então a média cai
        # quando o cadastro está incompleto. É a aritmética do legado, e
        # `without_salary` é o que a explica.
        base_payroll_average=(
            None
            if not ativos
            else (payroll.total / Decimal(len(ativos))).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)
        ),
        meal_voucher=_sum_benefit({MEAL_VOUCHER}, benefits, ativos_ids, salarios, on),
        cost_allowance=_sum_benefit({COST_ALLOWANCE}, benefits, ativos_ids, salarios, on),
        trust_and_hazard=_sum_benefit(set(TRUST_AND_HAZARD), benefits, ativos_ids, salarios, on),
        without_salary=payroll.without_salary,
        units_with_open_installment=len(unidades_com_parcela),
    )


# ---------------------------------------------------------------------------
# As leituras
# ---------------------------------------------------------------------------
# ⛔ SEM `tenant_id` AQUI, E ISSO É O DESENHO
# A população roda sob `user_scope`: com a RLS de pé, leitura de outro tenant não
# é filtro esquecido, é impossível — e o recorte de unidade sai da policy
# `employee_read` em vez de ser reimplementado neste arquivo.
_POPULATION_SQL = """
    select e.id as employee_id, e.name, e.status, e.company_id, e.unit_id
    from app.employee e
    order by e.name
"""

# As três abaixo rodam sob `tenant_scope` e por isso carregam o filtro explícito.
# Movimentação sem destino não entra: ela não diz nada sobre onde a pessoa
# trabalha, e trazê-la só para descartá-la em Python é leitura à toa.
_MOVEMENTS_SQL = """
    select m.employee_id, m.destination_unit_id, m.destination_work_post_id,
           m.effective_from, m.effective_to
    from app.workforce_movement m
    where m.tenant_id = %(tenant_id)s
      and m.destination_unit_id is not null
    order by m.employee_id, m.effective_from
"""

# ⛔ SÓ `employee_id` E OS DOIS `status` — nunca o nome, nunca o valor devido. O
# cartão é contagem de unidade, e o que não é lido não vaza.
#
# ⚠️ O QUE É "PARCELA EM ABERTO" NÃO ESTÁ NESTE SQL, E ISSO É ESCOLHA
# Corrigido em 07/09/2026. A versão anterior filtrava por `i.status = 'pending'`
# e `a.status = 'active'` aqui — dois literais que decidem um cartão da home e
# que **nenhum teste alcançava**: a suíte de pytest não abre banco, e
# `scripts/87_teste_painel_dp.sql`, que abre, só enxerga `public.fn_dp_alerts`.
# Mutar qualquer um dos dois deixava as 182 asserções verdes. Com a regra em
# Python ela é exercitada pela mesma fixture que o resto do painel — é a escolha
# que `beneficios.in_effect` já fez no S1, pelo mesmo motivo.
_OPEN_INSTALLMENTS_SQL = """
    select a.employee_id,
           i.status as installment_status,
           a.status as agreement_status
    from app.agreement_installment i
    join app.financial_agreement a
      on a.id = i.agreement_id and a.tenant_id = i.tenant_id
    where i.tenant_id = %(tenant_id)s
"""


async def read_panel(
    tenant: TenantContext,
    *,
    on: date,
    unit_id: UUID | None = None,
    company_id: UUID | None = None,
) -> PanelKpis:
    """Os nove KPIs do tenant em `on`, recortados pelo filtro da tela.

    ⛔ Domínio `compensation` — a rota revalida antes de chamar, como
    `GET /dp/beneficios/catalogo` faz.
    """
    async with user_scope(tenant) as escopo:
        await escopo.execute(_POPULATION_SQL)
        employees = [dict(linha) for linha in await escopo.fetchall()]

    async with tenant_scope(tenant) as scope:
        await scope.execute(_MOVEMENTS_SQL)
        movements = [dict(linha) for linha in await scope.fetchall()]

        await scope.execute(_OPEN_INSTALLMENTS_SQL)
        installments = [dict(linha) for linha in await scope.fetchall()]

    entradas = await beneficios.read_payroll_inputs(tenant)
    return compute_panel(
        on,
        employees,
        movements,
        entradas.salary_bands,
        entradas.benefits,
        installments,
        unit_id=unit_id,
        company_id=company_id,
    )
