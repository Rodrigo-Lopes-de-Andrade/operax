"""The closed catalogue — what the assistant may ask, and what it may never invent.

Rule 9 of the project: no text-to-SQL. The model does not write a query; it picks
a `code` from `app.metric` and hands back parameters. Everything that turns that
choice into data lives on this side of the line, and this module is the gate.

WHY A CATALOGUE AND NOT A CLEVER PROMPT
A model asked to write SQL against a schema it was shown will, eventually, write
a query that is syntactically fine and semantically wrong — joining department to
company, say, which is the 26% mistake the whole data model is shaped around. A
model asked to pick from nine named metrics can only be wrong in one way: picking
the wrong one of nine, which a person reads on screen and corrects. That is the
trade, and it is why the refusal is a first-class answer.

FOUR REASONS TO REFUSE, AND ALL OF THEM NAME THE PROBLEM
Out of catalogue, domain out of reach, unknown parameter, missing filter. A
refusal that says "não consigo responder isso" teaches nobody anything; one that
says *which* parameter it did not recognise gets the next question right.

THE DOMAIN IS FILTERED BEFORE THE MODEL SEES IT
A metric the person cannot reach is not offered at all. Offering it and refusing
afterwards would let the assistant confirm that payroll data exists to somebody
who is not allowed to know that it exists — the same reasoning that removes a tab
from the screen instead of disabling it.

BINDINGS ARE CODE, NOT DATA
`app.metric.dimensions` and `.filters` say *what* a metric accepts; `BINDINGS`
says how each one reaches its target — a column and an operator for a view, an
argument name for an RPC. It is code because it is the only place a caller value
gets near SQL structure, and a panel-editable column name is a panel-editable way
to read another tenant's rows. The db-test asserts the two agree: every dimension
and filter of every metric has a binding, and none points at a column the target
does not have.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Kind = Literal["view", "function"]


@dataclass(frozen=True, slots=True)
class Binding:
    """Como um parâmetro do catálogo alcança o alvo."""

    #: Coluna da view, quando o alvo é view.
    column: str | None = None
    operator: str = "="
    #: Nome do argumento, quando o alvo é função.
    argument: str | None = None


@dataclass(frozen=True, slots=True)
class Metric:
    """Uma linha de `app.metric`, do jeito que o executor precisa dela."""

    code: str
    title: str
    description: str
    target: str
    dimensions: tuple[str, ...]
    filters: tuple[str, ...]
    domain: str | None

    @property
    def kind(self) -> Kind:
        return "function" if self.target.startswith("fn_") else "view"

    @property
    def accepted(self) -> frozenset[str]:
        return frozenset(self.dimensions) | frozenset(self.filters)


@dataclass(frozen=True, slots=True)
class Choice:
    """A escolha aprovada, pronta para virar consulta."""

    metric: Metric
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Refusal:
    """Recusa é resposta válida, e ela diz o que houve.

    O `code` viaja para a UI, que mostra a mensagem; o `reason` é o texto em
    pt-BR que chega à pessoa.
    """

    code: Literal["fora_do_catalogo", "sem_dominio", "parametro_desconhecido", "filtro_ausente"]
    reason: str


# ---------------------------------------------------------------------------
# Como cada parâmetro alcança cada alvo
# ---------------------------------------------------------------------------
_PERIODO_VIEW = {
    "start_date": Binding(column="reference_date", operator=">="),
    "end_date": Binding(column="reference_date", operator="<="),
}
_PERIODO_FN = {"start_date": Binding(argument="p_de"), "end_date": Binding(argument="p_ate")}

BINDINGS: dict[str, dict[str, Binding]] = {
    "vw_deviation_event": {
        **_PERIODO_VIEW,
        "unit": Binding(column="unit_id"),
        "company": Binding(column="company_id"),
        "employee": Binding(column="employee_id"),
        "type": Binding(column="type"),
    },
    "vw_deviation_by_employee_day": {
        **_PERIODO_VIEW,
        "unit": Binding(column="unit_id"),
        "employee": Binding(column="employee_id"),
        # A view é por colaborador e dia: não tem empresa nem tipo, e o catálogo
        # não pode prometer o que ela não entrega.
        "company": Binding(column=None),
        "type": Binding(column=None),
    },
    "vw_deviation_daily_trend": {
        **_PERIODO_VIEW,
        "unit": Binding(column="unit_id"),
    },
    "vw_document_expiry": {
        "days_ahead": Binding(column="dias_para_vencer", operator="<="),
        "unit": Binding(column="unit_id"),
        "employee": Binding(column="employee_id"),
        "type": Binding(column="type_name"),
    },
    "vw_payroll_summary": {
        "year": Binding(column="year"),
        "month": Binding(column="month"),
        "company": Binding(column="company_id"),
        "unit": Binding(column="unit_id"),
        # A folha é por competência; a unidade de tempo dela é ano e mês, e não
        # um intervalo de dias.
        "payroll_period": Binding(column=None),
    },
    "fn_ranking_by_employee": {
        **_PERIODO_FN,
        # Como acima: o ranking é DE colaborador, então `employee` descreve a
        # saída e não é argumento.
        "employee": Binding(argument=None),
        "unit": Binding(argument="p_unit_id"),
        "company": Binding(argument="p_company_id"),
    },
    "fn_ranking_by_unit": {
        **_PERIODO_FN,
        # A função ordena unidades: `unit` é a dimensão da SAÍDA, e ela não tem
        # `p_unit_id` — filtrar um ranking de unidades por uma unidade seria
        # pedir o ranking de um item só.
        "unit": Binding(argument=None),
        "company": Binding(argument="p_company_id"),
    },
    "fn_recurrence": {
        **_PERIODO_FN,
        "unit": Binding(argument="p_unit_id"),
        "employee": Binding(argument=None),
    },
    "fn_data_freshness": {
        # `entity` descreve a saída (uma linha por origem de dado), não a
        # entrada: é dimensão de leitura, e ligá-la a um argumento inventaria um
        # parâmetro que a função não tem.
        "entity": Binding(argument=None),
        "stale_after_minutes": Binding(argument="p_stale_after_minutes"),
    },
}

#: Toda métrica de período precisa das duas pontas. Sem elas a consulta varre o
#: histórico inteiro — e "quantos desvios tivemos?" sem recorte é uma pergunta
#: que parece respondida e não está.
REQUIRED = ("start_date", "end_date")


def from_rows(rows: list[dict[str, Any]]) -> tuple[Metric, ...]:
    """As linhas de `app.metric` como o resto do módulo as entende."""
    return tuple(
        Metric(
            code=row["code"],
            title=row["title"],
            description=row["description"],
            target=row["target_view"],
            dimensions=tuple(row["dimensions"] or ()),
            filters=tuple(row["filters"] or ()),
            domain=row["domain"],
        )
        for row in rows
    )


def reachable(metrics: tuple[Metric, ...], domains: frozenset[str]) -> tuple[Metric, ...]:
    """O catálogo que esta pessoa pode ver — antes de o modelo ver qualquer coisa."""
    return tuple(m for m in metrics if m.domain is None or m.domain in domains)


def describe(metrics: tuple[Metric, ...]) -> str:
    """O catálogo em texto, do jeito que entra no prompt.

    Código, título e o que ele aceita. Nenhum nome de tabela e nenhuma coluna: o
    modelo não precisa deles para escolher, e o que ele não sabe ele não pode
    propor.
    """
    linhas = []
    for m in metrics:
        aceita = ", ".join(sorted(m.accepted)) or "nenhum"
        linhas.append(f"- {m.code}: {m.title}. {m.description}. Parâmetros: {aceita}.")
    return "\n".join(linhas)


def choose(
    metrics: tuple[Metric, ...], code: str, parameters: dict[str, Any], *, domains: frozenset[str]
) -> Choice | Refusal:
    """A escolha do modelo, aprovada ou recusada com o motivo."""
    por_codigo = {m.code: m for m in metrics}
    metric = por_codigo.get(code)
    if metric is None:
        return Refusal(
            "fora_do_catalogo",
            f"Não tenho a métrica {code!r}. O que eu sei responder é: "
            f"{', '.join(sorted(por_codigo)) or 'nada, neste momento'}.",
        )

    if metric.domain is not None and metric.domain not in domains:
        return Refusal(
            "sem_dominio",
            f"Esta pergunta depende de dado de {metric.domain}, e o seu acesso não alcança "
            f"esse domínio.",
        )

    desconhecidos = sorted(set(parameters) - metric.accepted)
    if desconhecidos:
        return Refusal(
            "parametro_desconhecido",
            f"A métrica {metric.code} não aceita {', '.join(desconhecidos)}. Ela aceita: "
            f"{', '.join(sorted(metric.accepted))}.",
        )

    faltando = [f for f in REQUIRED if f in metric.filters and parameters.get(f) in (None, "")]
    if faltando:
        return Refusal(
            "filtro_ausente",
            f"Falta o período: {', '.join(faltando)}. Sem recorte a resposta varreria o "
            f"histórico inteiro, e um número sem período não responde nada.",
        )

    return Choice(metric=metric, parameters=dict(parameters))


# ---------------------------------------------------------------------------
# Da escolha para a consulta
# ---------------------------------------------------------------------------
#: Um assistente que devolve quatro mil linhas não respondeu — e um resumo é o
#: que a pergunta pedia de qualquer forma. O teto fica aqui, e não no prompt,
#: porque um prompt é uma sugestão.
MAX_ROWS = 200


class UnboundParameterError(RuntimeError):
    """O catálogo aceita o parâmetro e o mapa não sabe onde ele encosta.

    Não é erro de usuário: é catálogo e código discordando, e o `make db-test`
    existe para que isso nunca chegue aqui em produção.
    """


@dataclass(frozen=True, slots=True)
class Query:
    """A consulta montada — texto e valores separados, sempre."""

    sql: str
    parameters: dict[str, Any]


def build(choice: Choice, *, limit: int = MAX_ROWS) -> Query:
    """A consulta da métrica escolhida, com cada valor ligado.

    Duas formas, porque o catálogo tem dois tipos de alvo: uma view vira `where`
    e uma função vira chamada com argumentos nomeados. Um parâmetro cujo binding
    não tem destino é **ignorado em silêncio de propósito** — é o caso declarado
    no mapa, como "esta view não tem empresa": o catálogo promete a dimensão para
    outra métrica do mesmo nome, e recusar aqui transformaria uma limitação
    conhecida em erro na cara da pessoa.
    """
    metric = choice.metric
    mapa = BINDINGS.get(metric.target)
    if mapa is None:
        raise UnboundParameterError(f"alvo {metric.target!r} não tem binding declarado")

    valores: dict[str, Any] = {}

    if metric.kind == "function":
        argumentos: list[str] = []
        for nome, valor in sorted(choice.parameters.items()):
            binding = mapa.get(nome)
            if binding is None:
                raise UnboundParameterError(
                    f"{metric.code}: {nome!r} sem binding em {metric.target}"
                )
            if binding.argument is None:
                continue
            argumentos.append(f"{binding.argument} => %({nome})s")
            valores[nome] = valor
        chamada = f"public.{metric.target}({', '.join(argumentos)})"
        return Query(sql=f"select * from {chamada} limit {int(limit)}", parameters=valores)

    condicoes: list[str] = []
    for nome, valor in sorted(choice.parameters.items()):
        binding = mapa.get(nome)
        if binding is None:
            raise UnboundParameterError(f"{metric.code}: {nome!r} sem binding em {metric.target}")
        if binding.column is None:
            continue
        condicoes.append(f"{binding.column} {binding.operator} %({nome})s")
        valores[nome] = valor

    onde = f" where {' and '.join(condicoes)}" if condicoes else ""
    return Query(
        sql=f"select * from public.{metric.target}{onde} limit {int(limit)}", parameters=valores
    )
