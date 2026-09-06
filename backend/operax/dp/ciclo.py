"""A rotina mensal: cesta básica e vale transporte, um modelo e dois `kind`.

⛔ AS REGRAS SÃO TRANSCRITAS DAS TELAS DO CLIENTE, NÃO DERIVADAS
`docs/SPEC-DP.md` §1e e `docs/ANEXO-COBERTURA-LEGADO-FASTPARK.md` §4.2 e §4.3.
Janela **21 → 20**; faltas injustificadas contadas no **mês civil anterior ao
início do período**; `net_days = days_base − absences_prior`;
`total_amount = net_days × round_trip_amount`. A cesta perde por **falta
injustificada** ou por **admissão depois do início do período**, e o `reason`
grava qual dos dois — a pessoa vai perguntar.

⚠️ A REGRA DE JANELA DA FALTA É UMA SÓ, E VALE PARA OS DOIS `kind`
A SPEC a escreve só para o VT, porque é lá que ela é contra-intuitiva. Aplicada
literalmente — *"o mês civil anterior ao início do período"* — ela responde
sozinha para a cesta: o período dela começa no dia 1º, e o mês inteiramente
anterior a 1º/09 é agosto; o do VT começa em 21/08, e o mês inteiramente anterior
a 21/08 é julho. Uma regra, duas respostas certas. Escrever uma segunda para a
cesta seria a regra escrita duas vezes, que é a que diverge.

⛔ STRING NÃO CURADA NÃO ENTRA EM CÁLCULO — ELA PARA A APURAÇÃO
A distinção entre falta e atestado existe só como texto livre no
`JustificativaNome` do Secullum, digitado pelo cliente e truncado em 7
caracteres (`Atested` e `ATEST M` são o mesmo conceito). `app.leave_justification_map`
é a curadoria, e uma justificativa que não está lá — ou está e ninguém validou —
levanta `UncuratedJustificationError` com a string no texto. **Silêncio aqui não
é neutro: ele dá vale transporte a quem faltou.**

⚠️ AS FALTAS VÊM DE DUAS FONTES, E A UNIÃO É POR DIA
O espelho (`secullum."FuncionarioAfastamento"`, resolvido pela curadoria) e
`app.leave_period` com `category = 'unjustified_absence'` (o que o RH digita).
As duas são somadas como **conjunto de datas**, não como contagem de linhas:
quando a promoção do espelho para o domínio existir, o mesmo afastamento estará
nos dois lugares, e contar linhas o cobraria duas vezes.

⚠️ `days_base` VEM DE `app.expected_workday`, E A ESCOLHA TEM CONSEQUÊNCIA
A tela do legado diz que *"a escala é obtida do Quadro de Postos"*; o elo posto →
escala não existe neste repositório e é migration de outra sprint
(`SPEC-DP.md` §0-bis). O que existe é a escala **já materializada por pessoa e
por data**, que é o produto da mesma origem. A alternativa — contar segunda a
sexta do calendário — seria errada para este cliente: quem faz 12x36 trabalha
sábado e domingo, e receberia VT de menos todo mês, calado.

⛔ E POR ISSO A COBERTURA É EXIGIDA, NÃO ASSUMIDA
Se `app.expected_workday` não cobre o vínculo inteiro dentro da janela, os dias
que faltam não são "dias sem expediente": são dias que o motor não materializou.
Tratá-los como zero paga menos a alguém sem nenhum sintoma —
`ScheduleCoverageError` para a apuração e diz de quem e quantos dias.

⛔ NÃO HÁ ARREDONDAMENTO AQUI, E A AUSÊNCIA É O DESENHO
`net_days` é inteiro e a tarifa tem duas casas: o produto é exato. Um `quantize`
a mais seria a regra de arredondamento da folha escrita uma segunda vez, longe
de `beneficios._money` — e a segunda cópia é a que diverge.

⛔ LEITURA NÃO RODA COMO O USUÁRIO
Nenhuma das tabelas desta etapa concede algo a `authenticated`: um `select` sob
`user_scope` morreria com `permission denied` em vez de ser filtrado. Tudo roda
sob `tenant_scope`, com `where tenant_id = %(tenant_id)s`, e quem autoriza é a
rota — mesma decisão declarada em `operax/dp/beneficios.py`.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from operax.core.tenant import TenantContext, tenant_scope
from operax.dp import beneficios

FOOD_BASKET = "food_basket"
TRANSPORT_VOUCHER = "transport_voucher"
KINDS = (FOOD_BASKET, TRANSPORT_VOUCHER)

DRAFT = "draft"
GENERATED = "generated"

#: A categoria que a `dp_leave_category` acrescentou. É a única que vale dinheiro.
UNJUSTIFIED_ABSENCE = "unjustified_absence"

#: O `kind` do ciclo É o `code` da verba no catálogo — a §1e usa os dois mesmos
#: literais, e `app.benefit_cycle.kind` e `app.benefit_type.code` os repetem. Não
#: é lista de códigos escrita no backend: é a identidade, e ela viaja como
#: parâmetro ligado, nunca interpolada em SQL.
_BENEFIT_CODE = {FOOD_BASKET: FOOD_BASKET, TRANSPORT_VOUCHER: TRANSPORT_VOUCHER}

#: Quantas pessoas a mensagem de falha de cobertura nomeia antes de resumir. Uma
#: mensagem com 176 nomes não é lida; uma com zero não é acionável.
_NOMES_NA_MENSAGEM = 5

_UM_DIA = timedelta(days=1)


class CycleError(RuntimeError):
    """Base das recusas deste módulo."""


class UnknownCycleKindError(CycleError):
    """`kind` fora de `food_basket` e `transport_voucher`."""


class UncuratedJustificationError(CycleError):
    """Justificativa de afastamento que a curadoria não classificou.

    Falha alto de propósito, e é a recusa mais importante desta etapa. A
    alternativa — tratar o desconhecido como "não é falta" — entrega vale
    transporte e cesta a quem faltou, e ninguém reclama de receber a mais. A
    mensagem carrega a string literal porque é ela que a pessoa vai procurar na
    tela de curadoria.
    """


class ScheduleCoverageError(CycleError):
    """`app.expected_workday` não cobre o vínculo dentro da janela.

    Dia sem linha não é dia sem expediente: é dia que o motor não materializou.
    Somá-lo como zero paga menos a alguém, sem sintoma nenhum.
    """


class MissingFareError(CycleError):
    """Tarifa sem a faixa vigente de ida-e-volta na data do ciclo.

    `total_amount = net_days × round_trip_amount`: sem o valor, o total seria
    zero — e zero calado numa remessa é dinheiro que a pessoa não recebe.
    """


class CycleAlreadyGeneratedError(CycleError):
    """O ciclo já foi congelado. Correção é ciclo novo com `reason`, nunca `update`."""


# ---------------------------------------------------------------------------
# Calendário — as três datas que a tela declara
# ---------------------------------------------------------------------------
def _fim_do_mes(ano: int, mes: int) -> date:
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def cycle_window(kind: str, period_year: int, period_month: int) -> tuple[date, date]:
    """A janela do ciclo. VT: **21 → 20**; cesta: o mês civil.

    O 21 é do mês ANTERIOR e o 20 é do mês de referência — é a frase da tela de
    vale transporte, e é o único lugar deste módulo em que os dois números
    aparecem.
    """
    if kind == TRANSPORT_VOUCHER:
        inicio = date(period_year, period_month, 1) - _UM_DIA
        return date(inicio.year, inicio.month, 21), date(period_year, period_month, 20)
    if kind == FOOD_BASKET:
        return date(period_year, period_month, 1), _fim_do_mes(period_year, period_month)
    raise UnknownCycleKindError(f"kind '{kind}' não existe; use {' ou '.join(KINDS)}")


def absence_month(window_start: date) -> tuple[date, date]:
    """O **mês civil anterior ao início do período** — a frase da tela, literal.

    "Anterior ao início do período" é o mês que termina antes de `window_start`,
    não o mês em que ela cai: a janela do VT começa em 21/08 e agosto ainda está
    correndo, então o mês fechado antes dela é julho. Contar agosto contaria dias
    que estão DENTRO da própria janela.
    """
    ultimo = date(window_start.year, window_start.month, 1) - _UM_DIA
    return date(ultimo.year, ultimo.month, 1), ultimo


def _dias(inicio: date, fim: date) -> set[date]:
    if fim < inicio:
        return set()
    return {inicio + timedelta(days=i) for i in range((fim - inicio).days + 1)}


# ---------------------------------------------------------------------------
# Curadoria da justificativa
# ---------------------------------------------------------------------------
def canonical_justification(raw: str | None) -> str:
    """`upper(btrim(...))` — a mesma canonicalização que o `check` do banco impõe.

    Acento não é normalizado: 'FÉRIAS' e 'FERIAS' são duas strings, e cada uma se
    cura sozinha. Tirar acento seria adivinhar que são a mesma coisa, e adivinhar
    é o que a curadoria existe para não fazer.
    """
    return (raw or "").strip().upper()


def resolve_absence_days(
    leaves: Sequence[Mapping[str, Any]],
    curation: Mapping[str, Mapping[str, Any]],
    month_start: date,
    month_end: date,
) -> dict[UUID, set[date]]:
    """Os dias de falta injustificada por pessoa, dentro do mês contado.

    Levanta em vez de devolver menos: uma justificativa desconhecida, ou conhecida
    e não validada, para a apuração inteira. Um afastamento sem justificativa
    nenhuma no Secullum cai no mesmo lugar — não dá para curar o que não tem nome,
    e chamá-lo de "não é falta" é a mesma entrega de dinheiro no escuro.
    """
    por_pessoa: dict[UUID, set[date]] = defaultdict(set)
    for leave in leaves:
        chave = canonical_justification(leave["justification"])
        if not chave:
            raise UncuratedJustificationError(
                "há afastamento sem justificativa no Secullum entre "
                f"{month_start:%d/%m/%Y} e {month_end:%d/%m/%Y}; "
                "sem o nome dela não há o que classificar, e supor que não é falta "
                "entrega benefício a quem faltou"
            )
        curado = curation.get(chave)
        if curado is None:
            raise UncuratedJustificationError(
                f"a justificativa «{chave}» não está classificada em "
                "app.leave_justification_map; classifique-a antes de apurar — "
                "tratá-la como ausência de falta entrega benefício a quem faltou"
            )
        if curado["validated_at"] is None:
            raise UncuratedJustificationError(
                f"a justificativa «{chave}» está classificada como "
                f"«{curado['category']}» mas ninguém validou; classificação "
                "provisória não entra em cálculo de dinheiro"
            )
        if curado["category"] != UNJUSTIFIED_ABSENCE:
            continue
        por_pessoa[leave["employee_id"]] |= _dias(
            max(leave["starts_on"], month_start), min(leave["ends_on"], month_end)
        )
    return por_pessoa


def merge_absence_days(
    *fontes: Mapping[UUID, set[date]],
) -> dict[UUID, set[date]]:
    """A união por DIA das fontes de falta.

    Por dia e não por linha: quando a promoção do espelho para `app.leave_period`
    existir, o mesmo afastamento estará nos dois lugares, e somar contagens o
    cobraria duas vezes do colaborador.
    """
    junto: dict[UUID, set[date]] = defaultdict(set)
    for fonte in fontes:
        for employee_id, dias in fonte.items():
            junto[employee_id] |= dias
    return junto


# ---------------------------------------------------------------------------
# A apuração
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class EntitlementLine:
    """A linha por pessoa. As colunas de dias ficam nulas para cesta."""

    employee_id: UUID
    name: str
    registration_number: str | None
    unit_id: UUID | None
    unit_name: str | None
    entitled: bool
    reason: str | None
    days_base: int | None = None
    absences_prior: int | None = None
    net_days: int | None = None
    unit_amount: Decimal | None = None
    round_trip_amount: Decimal | None = None
    total_amount: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Cycle:
    """A competência apurada, com o que a tela mostra no cabeçalho."""

    id: UUID | None
    kind: str
    period_year: int
    period_month: int
    window_start: date
    window_end: date
    business_days: int | None
    status: str
    lines: tuple[EntitlementLine, ...]

    @property
    def entitled_count(self) -> int:
        return sum(1 for linha in self.lines if linha.entitled)

    @property
    def denied_count(self) -> int:
        return sum(1 for linha in self.lines if not linha.entitled)

    @property
    def total_amount(self) -> Decimal:
        return sum(
            (linha.total_amount for linha in self.lines if linha.total_amount is not None),
            start=Decimal("0"),
        )


def _vinculo_na_janela(
    employee: Mapping[str, Any], window_start: date, window_end: date
) -> tuple[date, date]:
    """O recorte do vínculo dentro da janela. Data nula não recorta nada."""
    inicio = window_start
    if employee["hired_on"] is not None and employee["hired_on"] > inicio:
        inicio = employee["hired_on"]
    fim = window_end
    if employee["terminated_on"] is not None and employee["terminated_on"] < fim:
        fim = employee["terminated_on"]
    return inicio, fim


def _cobertura(
    employees: Sequence[Mapping[str, Any]],
    schedule: Mapping[UUID, Mapping[date, str]],
    window_start: date,
    window_end: date,
) -> None:
    """Recusa quando a jornada esperada não cobre o vínculo dentro da janela."""
    faltando: list[tuple[str, int]] = []
    for employee in employees:
        inicio, fim = _vinculo_na_janela(employee, window_start, window_end)
        esperados = _dias(inicio, fim)
        if not esperados:
            continue
        cobertos = esperados & set(schedule.get(employee["employee_id"], {}))
        if len(cobertos) < len(esperados):
            faltando.append((employee["name"], len(esperados) - len(cobertos)))
    if not faltando:
        return
    faltando.sort(key=lambda par: (-par[1], par[0]))
    amostra = "; ".join(f"{nome} ({dias} dia(s))" for nome, dias in faltando[:_NOMES_NA_MENSAGEM])
    sobra = len(faltando) - _NOMES_NA_MENSAGEM
    resto = f" e mais {sobra}" if sobra > 0 else ""
    raise ScheduleCoverageError(
        f"app.expected_workday não cobre o período de {len(faltando)} colaborador(es): "
        f"{amostra}{resto}. Rode o motor de jornada sobre a janela antes de apurar — "
        "dia sem linha não é dia sem expediente, e contá-lo como zero paga a menos"
    )


def _fares_by_code(catalog: beneficios.Catalog) -> dict[str, dict[str, Decimal]]:
    por_code: dict[str, dict[str, Decimal]] = defaultdict(dict)
    for fare in catalog.fares:
        por_code[fare.code][fare.kind] = fare.amount
    return por_code


def compute_basket_cycle(
    window_start: date,
    window_end: date,
    employees: Sequence[Mapping[str, Any]],
    absence_days: Mapping[UUID, set[date]],
    absence_month_start: date,
) -> tuple[EntitlementLine, ...]:
    """Cesta: perde por falta injustificada ou por admissão depois do início.

    A ordem das duas causas não é arbitrária: quem foi admitido depois do início
    do período não estava na casa no mês contado, então não podia ter faltado —
    perguntar pela admissão primeiro dá o motivo que explica o outro.
    """
    linhas: list[EntitlementLine] = []
    for employee in employees:
        hired_on = employee["hired_on"]
        faltas = len(absence_days.get(employee["employee_id"], set()))
        if hired_on is not None and hired_on > window_start:
            entitled, reason = (
                False,
                (
                    f"Admitido em {hired_on:%d/%m/%Y}, depois do início do período "
                    f"({window_start:%d/%m/%Y})."
                ),
            )
        elif faltas:
            entitled, reason = (
                False,
                (f"{faltas} falta(s) injustificada(s) em {absence_month_start:%m/%Y}."),
            )
        else:
            entitled, reason = True, None
        linhas.append(
            EntitlementLine(
                employee_id=employee["employee_id"],
                name=employee["name"],
                registration_number=employee["registration_number"],
                unit_id=employee["unit_id"],
                unit_name=employee["unit_name"],
                entitled=entitled,
                reason=reason,
            )
        )
    return tuple(linhas)


def compute_transport_cycle(
    window_start: date,
    window_end: date,
    employees: Sequence[Mapping[str, Any]],
    schedule: Mapping[UUID, Mapping[date, str]],
    absence_days: Mapping[UUID, set[date]],
    absence_month_start: date,
    fares: Mapping[str, Mapping[str, Decimal]],
    assignments: Mapping[UUID, Sequence[str]],
) -> tuple[EntitlementLine, ...]:
    """VT: `net_days = days_base − absences_prior`, `total = net_days × ida-e-volta`.

    ⛔ Admissão e desligamento no meio do período NÃO têm regra própria: eles
    saem pelo mesmo recorte de vínculo que a cobertura usa, e o `days_base` já
    nasce menor. Uma exceção escrita aqui seria a regra do vínculo escrita duas
    vezes — e a segunda cópia é a que diverge (lição do S1).

    ⚠️ Duas linhas de ônibus são legítimas — a `dp_benefit_catalog` recusa
    travá-las de propósito —, então as tarifas da pessoa SOMAM. Escolher uma
    delas pagaria só metade do trajeto de quem faz integração.
    """
    linhas: list[EntitlementLine] = []
    for employee in employees:
        employee_id = employee["employee_id"]
        codes = assignments.get(employee_id)
        if not codes:
            continue

        inicio, fim = _vinculo_na_janela(employee, window_start, window_end)
        dias = schedule.get(employee_id, {})
        days_base = sum(1 for dia, tipo in dias.items() if tipo == "work" and inicio <= dia <= fim)
        absences_prior = len(absence_days.get(employee_id, set()))
        # ⛔ A subtração é literal. O piso em zero é o único acréscimo, e ele
        #    existe porque as faltas são contadas num mês DIFERENTE do dos dias
        #    base: quem faltou 20 dias em julho e tem 8 dias de escala na janela
        #    daria dias líquidos negativos, e um total negativo seria o produto
        #    cobrando vale transporte do colaborador.
        net_days = max(days_base - absences_prior, 0)

        unit_amount = Decimal("0")
        round_trip_amount = Decimal("0")
        for code in codes:
            faixa = fares.get(code, {})
            if "round_trip" not in faixa:
                raise MissingFareError(
                    f"a tarifa «{code}» de {employee['name']} não tem faixa vigente de "
                    f"ida-e-volta em {window_start:%d/%m/%Y}; sem ela o total sairia zero"
                )
            round_trip_amount += faixa["round_trip"]
            unit_amount += faixa.get("single", Decimal("0"))

        total_amount = round_trip_amount * net_days
        entitled = net_days > 0
        reason = None
        if not entitled:
            reason = (
                f"Sem dias líquidos: {days_base} dia(s) base menos {absences_prior} "
                f"falta(s) injustificada(s) em {absence_month_start:%m/%Y}."
            )
        linhas.append(
            EntitlementLine(
                employee_id=employee_id,
                name=employee["name"],
                registration_number=employee["registration_number"],
                unit_id=employee["unit_id"],
                unit_name=employee["unit_name"],
                entitled=entitled,
                reason=reason,
                days_base=days_base,
                absences_prior=absences_prior,
                net_days=net_days,
                unit_amount=unit_amount,
                round_trip_amount=round_trip_amount,
                total_amount=total_amount,
            )
        )
    return tuple(linhas)


def business_days_in(schedule: Mapping[UUID, Mapping[date, str]]) -> int:
    """Dias com expediente na janela — cabeçalho da tela, nunca dinheiro.

    Derivado da MESMA fonte de `days_base`, e não de uma segunda definição de
    "dia útil": duas definições divergem, e a que aparece no cabeçalho seria a
    que ninguém confere.
    """
    return len({dia for dias in schedule.values() for dia, tipo in dias.items() if tipo == "work"})


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
# ⛔ O TENANT PROPAGA NO `join`, E NÃO SÓ NO `where`
# `on u.id = e.unit_id` casa por id e mais nada: a unidade de outro cliente com
# o mesmo uuid entraria pelo lado de fora do filtro. É a forma que o docstring
# do `FakeCursor` declara NÃO pegar — nenhuma inspeção de string alcança o lado
# não filtrado de um join —, então ela se resolve escrevendo o predicado, não
# confiando na guarda. Vale para os quatro joins deste módulo.
_EMPLOYEES_SQL = """
    select e.id as employee_id, e.name, e.registration_number,
           e.unit_id, u.name as unit_name, e.hired_on, e.terminated_on
    from app.employee e
    left join app.unit u on u.id = e.unit_id and u.tenant_id = e.tenant_id
    where e.tenant_id = %(tenant_id)s
      and (e.hired_on is null       or e.hired_on <= %(window_end)s::date)
      and (e.terminated_on is null  or e.terminated_on >= %(window_start)s::date)
    order by e.name
"""

_SCHEDULE_SQL = """
    select w.employee_id, w.reference_date, w.day_type
    from app.expected_workday w
    where w.tenant_id = %(tenant_id)s
      and w.reference_date between %(window_start)s::date and %(window_end)s::date
"""

# `bt.code` chega ligado, nunca interpolado: o `kind` do ciclo É o `code` da
# verba, e os dois literais vêm da SPEC.
_ASSIGNMENT_SQL = """
    select eb.employee_id, eb.effective_from, eb.effective_to, f.code as fare_code
    from app.employee_benefit eb
    join app.benefit_type bt
      on bt.id = eb.benefit_type_id and bt.tenant_id = eb.tenant_id
    join app.transport_fare f
      on f.id = eb.transport_fare_id and f.tenant_id = eb.tenant_id
    where eb.tenant_id = %(tenant_id)s
      and bt.code = %(benefit_code)s
      and bt.active
"""

# ⛔ O espelho é lido CRU: a classificação acontece em Python, sob a curadoria.
#    Filtrar a falta aqui esconderia a justificativa desconhecida — e é
#    justamente ela que precisa parar a apuração.
_MIRROR_LEAVE_SQL = """
    select e.id as employee_id,
           a."Inicio"::date as starts_on,
           coalesce(a."Fim"::date, 'infinity'::date) as ends_on,
           a."JustificativaNome" as justification
    from secullum."FuncionarioAfastamento" a
    join secullum."Funcionario" f
      on f.id = a.funcionario_id and f.tenant_id = a.tenant_id
    join app.employee e
      on e.secullum_employee_id = f."FuncionarioId" and e.tenant_id = a.tenant_id
    where a.tenant_id = %(tenant_id)s
      and a."Inicio"::date <= %(month_end)s::date
      and coalesce(a."Fim"::date, 'infinity'::date) >= %(month_start)s::date
"""

# A outra fonte: o que o RH digitou. Já vem com categoria curada — não passa
# pela curadoria de string, e é por isso que o filtro pode ficar no `where`.
_DOMAIN_LEAVE_SQL = """
    select l.employee_id,
           l.start_date as starts_on,
           coalesce(l.end_date, 'infinity'::date) as ends_on
    from app.leave_period l
    where l.tenant_id = %(tenant_id)s
      and l.category = %(category)s
      and l.start_date <= %(month_end)s::date
      and coalesce(l.end_date, 'infinity'::date) >= %(month_start)s::date
"""

_CURATION_SQL = """
    select m.justification, m.category, m.validated_at
    from app.leave_justification_map m
    where m.tenant_id = %(tenant_id)s
"""


def _schedule_by_employee(rows: Iterable[Mapping[str, Any]]) -> dict[UUID, dict[date, str]]:
    por_pessoa: dict[UUID, dict[date, str]] = defaultdict(dict)
    for row in rows:
        por_pessoa[row["employee_id"]][row["reference_date"]] = row["day_type"]
    return por_pessoa


def _assignments_on(rows: Iterable[Mapping[str, Any]], on: date) -> dict[UUID, list[str]]:
    """As tarifas vigentes da pessoa na data — `in_effect` do S1, não uma segunda cópia."""
    por_pessoa: dict[UUID, list[str]] = defaultdict(list)
    for row in rows:
        if beneficios.in_effect(on, row["effective_from"], row["effective_to"]):
            por_pessoa[row["employee_id"]].append(row["fare_code"])
    return por_pessoa


def _domain_absence_days(
    rows: Iterable[Mapping[str, Any]], month_start: date, month_end: date
) -> dict[UUID, set[date]]:
    por_pessoa: dict[UUID, set[date]] = defaultdict(set)
    for row in rows:
        por_pessoa[row["employee_id"]] |= _dias(
            max(row["starts_on"], month_start), min(row["ends_on"], month_end)
        )
    return por_pessoa


async def compute_cycle(
    tenant: TenantContext, *, kind: str, period_year: int, period_month: int
) -> Cycle:
    """Apura a competência sem gravar nada. O `id` volta nulo: ainda não é ciclo."""
    window_start, window_end = cycle_window(kind, period_year, period_month)
    month_start, month_end = absence_month(window_start)
    janela = {"window_start": window_start, "window_end": window_end}
    mes = {"month_start": month_start, "month_end": month_end}

    async with tenant_scope(tenant) as scope:
        await scope.execute(_EMPLOYEES_SQL, janela)
        employees = [dict(linha) for linha in await scope.fetchall()]

        await scope.execute(_CURATION_SQL)
        curation = {linha["justification"]: dict(linha) for linha in await scope.fetchall()}

        await scope.execute(_MIRROR_LEAVE_SQL, mes)
        mirror_leaves = [dict(linha) for linha in await scope.fetchall()]

        await scope.execute(_DOMAIN_LEAVE_SQL, {**mes, "category": UNJUSTIFIED_ABSENCE})
        domain_leaves = [dict(linha) for linha in await scope.fetchall()]

        schedule_rows: list[dict[str, Any]] = []
        assignment_rows: list[dict[str, Any]] = []
        if kind == TRANSPORT_VOUCHER:
            await scope.execute(_SCHEDULE_SQL, janela)
            schedule_rows = [dict(linha) for linha in await scope.fetchall()]
            await scope.execute(_ASSIGNMENT_SQL, {"benefit_code": _BENEFIT_CODE[TRANSPORT_VOUCHER]})
            assignment_rows = [dict(linha) for linha in await scope.fetchall()]

    absence_days = merge_absence_days(
        resolve_absence_days(mirror_leaves, curation, month_start, month_end),
        _domain_absence_days(domain_leaves, month_start, month_end),
    )

    if kind == FOOD_BASKET:
        return Cycle(
            id=None,
            kind=kind,
            period_year=period_year,
            period_month=period_month,
            window_start=window_start,
            window_end=window_end,
            business_days=None,
            status=DRAFT,
            lines=compute_basket_cycle(
                window_start, window_end, employees, absence_days, month_start
            ),
        )

    schedule = _schedule_by_employee(schedule_rows)
    assignments = _assignments_on(assignment_rows, window_start)
    # A cobertura é exigida só de quem entra no ciclo: quem não tem vale
    # transporte atribuído não tem days_base a errar, e recusar por ele travaria
    # a rotina por causa de quem ela nem paga.
    com_vt = [e for e in employees if assignments.get(e["employee_id"])]
    _cobertura(com_vt, schedule, window_start, window_end)

    catalog = await beneficios.read_catalog(tenant, on=window_start)
    return Cycle(
        id=None,
        kind=kind,
        period_year=period_year,
        period_month=period_month,
        window_start=window_start,
        window_end=window_end,
        business_days=business_days_in(schedule),
        status=DRAFT,
        lines=compute_transport_cycle(
            window_start,
            window_end,
            employees,
            schedule,
            absence_days,
            month_start,
            _fares_by_code(catalog),
            assignments,
        ),
    )


# ---------------------------------------------------------------------------
# Gravação — o rascunho é reconstruível, o congelado não se toca
# ---------------------------------------------------------------------------
# ⚠️ NÃO HÁ `on conflict` AQUI, E O MOTIVO É DO POSTGRES
# `benefit_cycle_period_key` é `deferrable initially deferred`, como a SPEC §1e
# manda, e o Postgres não aceita índice adiável como árbitro de `on conflict`.
# Então a reserva é `select ... for update` e depois `insert` — e a corrida de
# dois pedidos simultâneos da mesma competência estoura no commit, com a mesma
# violação de unicidade, que a rota traduz em 409. Ciclo mensal é ação humana:
# a corrida é possível e rara, e ela falha alto em vez de duplicar.
_OPEN_DRAFT_SQL = """
    select c.id
    from app.benefit_cycle c
    where c.tenant_id = %(tenant_id)s
      and c.kind = %(kind)s
      and c.period_year = %(period_year)s
      and c.period_month = %(period_month)s
      and c.status = %(draft)s
    for update
"""

_INSERT_CYCLE_SQL = """
    insert into app.benefit_cycle
      (tenant_id, kind, period_year, period_month, window_start, window_end, business_days)
    values
      (%(tenant_id)s, %(kind)s, %(period_year)s, %(period_month)s,
       %(window_start)s, %(window_end)s, %(business_days)s)
    returning id
"""

_REFRESH_CYCLE_SQL = """
    update app.benefit_cycle
       set window_start = %(window_start)s,
           window_end   = %(window_end)s,
           business_days = %(business_days)s
     where id = %(cycle_id)s and tenant_id = %(tenant_id)s
"""

_CLEAR_LINES_SQL = """
    delete from app.benefit_entitlement
     where cycle_id = %(cycle_id)s and tenant_id = %(tenant_id)s
"""

_INSERT_LINE_SQL = """
    insert into app.benefit_entitlement
      (tenant_id, cycle_id, employee_id, unit_id, entitled, reason,
       days_base, absences_prior, net_days, unit_amount, round_trip_amount, total_amount)
    values
      (%(tenant_id)s, %(cycle_id)s, %(employee_id)s, %(unit_id)s, %(entitled)s, %(reason)s,
       %(days_base)s, %(absences_prior)s, %(net_days)s, %(unit_amount)s,
       %(round_trip_amount)s, %(total_amount)s)
"""

# ⛔ `and status = draft` NÃO É REDUNDANTE COM O GATILHO
# O gatilho recusa com erro; esta cláusula devolve zero linhas, e é o que permite
# a rota dizer "já foi gerado" em vez de estourar. As duas defesas dizem a mesma
# coisa, e a de baixo é a que vale quando alguém escreve pelo psql.
_FREEZE_SQL = """
    update app.benefit_cycle
       set status = %(generated)s, generated_at = now(), generated_by = %(user_id)s
     where id = %(cycle_id)s and tenant_id = %(tenant_id)s and status = %(draft)s
    returning id
"""

_LOAD_CYCLE_SQL = """
    select c.id, c.kind, c.period_year, c.period_month, c.window_start, c.window_end,
           c.business_days, c.status
    from app.benefit_cycle c
    where c.id = %(cycle_id)s and c.tenant_id = %(tenant_id)s
"""

_LOAD_LINES_SQL = """
    select b.employee_id, e.name, e.registration_number, b.unit_id, u.name as unit_name,
           b.entitled, b.reason, b.days_base, b.absences_prior, b.net_days,
           b.unit_amount, b.round_trip_amount, b.total_amount
    from app.benefit_entitlement b
    join app.employee e on e.id = b.employee_id and e.tenant_id = b.tenant_id
    left join app.unit u on u.id = b.unit_id and u.tenant_id = b.tenant_id
    where b.cycle_id = %(cycle_id)s and b.tenant_id = %(tenant_id)s
    order by u.name nulls last, e.name
"""


def _line_params(cycle_id: UUID, linha: EntitlementLine) -> dict[str, Any]:
    return {
        "cycle_id": cycle_id,
        "employee_id": linha.employee_id,
        "unit_id": linha.unit_id,
        "entitled": linha.entitled,
        "reason": linha.reason,
        "days_base": linha.days_base,
        "absences_prior": linha.absences_prior,
        "net_days": linha.net_days,
        "unit_amount": linha.unit_amount,
        "round_trip_amount": linha.round_trip_amount,
        "total_amount": linha.total_amount,
    }


def _row_to_line(row: Mapping[str, Any]) -> EntitlementLine:
    return EntitlementLine(
        employee_id=row["employee_id"],
        name=row["name"],
        registration_number=row["registration_number"],
        unit_id=row["unit_id"],
        unit_name=row["unit_name"],
        entitled=row["entitled"],
        reason=row["reason"],
        days_base=row["days_base"],
        absences_prior=row["absences_prior"],
        net_days=row["net_days"],
        unit_amount=row["unit_amount"],
        round_trip_amount=row["round_trip_amount"],
        total_amount=row["total_amount"],
    )


async def save_draft(tenant: TenantContext, cycle: Cycle) -> Cycle:
    """Grava o rascunho e devolve o ciclo com `id`.

    ⛔ Rascunho NÃO é linha definitiva, e é por isso que ele pode ser gravado
    antes de o gestor confirmar. Reapurar a mesma competência refaz as linhas do
    MESMO rascunho: apagar e reinserir sob o `unique (cycle_id, employee_id)` é o
    que faz o reprocessamento não duplicar ninguém. O que `POST /dp/ciclos/{id}/gerar`
    congela é exatamente o que o gestor viu — ele não reapura, e por isso o número
    da tela e o número da remessa não podem divergir.
    """
    chave = {
        "kind": cycle.kind,
        "period_year": cycle.period_year,
        "period_month": cycle.period_month,
    }
    async with tenant_scope(tenant) as scope:
        await scope.execute(_OPEN_DRAFT_SQL, {**chave, "draft": DRAFT})
        aberto = await scope.fetchone()

        cabecalho = {
            "window_start": cycle.window_start,
            "window_end": cycle.window_end,
            "business_days": cycle.business_days,
        }
        if aberto is None:
            await scope.execute(_INSERT_CYCLE_SQL, {**chave, **cabecalho})
            criado = await scope.fetchone()
            if criado is None:
                raise CycleError("o ciclo não foi gravado")
            cycle_id = criado["id"]
        else:
            cycle_id = aberto["id"]
            await scope.execute(_REFRESH_CYCLE_SQL, {**cabecalho, "cycle_id": cycle_id})
            await scope.execute(_CLEAR_LINES_SQL, {"cycle_id": cycle_id})

        for linha in cycle.lines:
            await scope.execute(_INSERT_LINE_SQL, _line_params(cycle_id, linha))

    return Cycle(
        id=cycle_id,
        kind=cycle.kind,
        period_year=cycle.period_year,
        period_month=cycle.period_month,
        window_start=cycle.window_start,
        window_end=cycle.window_end,
        business_days=cycle.business_days,
        status=DRAFT,
        lines=cycle.lines,
    )


async def load_cycle(tenant: TenantContext, cycle_id: UUID) -> Cycle | None:
    """O ciclo gravado, com as linhas dele. `None` quando não é deste tenant."""
    async with tenant_scope(tenant) as scope:
        await scope.execute(_LOAD_CYCLE_SQL, {"cycle_id": cycle_id})
        cabecalho = await scope.fetchone()
        if cabecalho is None:
            return None
        await scope.execute(_LOAD_LINES_SQL, {"cycle_id": cycle_id})
        linhas = [_row_to_line(dict(linha)) for linha in await scope.fetchall()]

    return Cycle(
        id=cabecalho["id"],
        kind=cabecalho["kind"],
        period_year=cabecalho["period_year"],
        period_month=cabecalho["period_month"],
        window_start=cabecalho["window_start"],
        window_end=cabecalho["window_end"],
        business_days=cabecalho["business_days"],
        status=cabecalho["status"],
        lines=tuple(linhas),
    )


async def freeze(tenant: TenantContext, cycle_id: UUID) -> Cycle:
    """Congela o rascunho. Não reapura: o que foi visto é o que fica.

    Reapurar aqui deixaria o número da tela e o número da remessa dependerem de
    o dado não ter mudado no meio — e "mudou entre a conferência e o envio" é
    exatamente a divergência de uma pessoa que o gate chama de falha.
    """
    async with tenant_scope(tenant) as scope:
        await scope.execute(
            _FREEZE_SQL,
            {
                "cycle_id": cycle_id,
                "user_id": tenant.user_id,
                "generated": GENERATED,
                "draft": DRAFT,
            },
        )
        congelado = await scope.fetchone()
    if congelado is None:
        raise CycleAlreadyGeneratedError(
            "este ciclo não está mais em rascunho; correção é ciclo novo com motivo, nunca update"
        )
    frozen = await load_cycle(tenant, cycle_id)
    if frozen is None:
        raise CycleError(f"o ciclo {cycle_id} sumiu logo depois de ser congelado")
    return frozen
