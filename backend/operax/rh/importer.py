"""The verdict on each line — and it is only a verdict, never a write.

Pure like `validators`, and for the same reason: the preview and the confirmation
have to reach the same conclusion, and the only way to be sure of that is for both
to call this. `POST /rh/imports` shows what this returns; `POST
/rh/imports/{id}/confirm` re-reads the file, calls this again, and writes exactly
the lines it approves the second time.

WHY CONFIRM RE-VALIDATES INSTEAD OF TRUSTING THE PREVIEW
Between seeing the preview and pressing confirm the world moves: someone else
takes the ID RH, a payroll period closes, a person is terminated. A stored verdict
would be applied against a database that no longer matches it. The report saved on
the import is what the screen shows; it is not what the write trusts.

THE THIRD OUTCOME
A line can be right and still write nothing. The template comes pre-filled, so an
untouched file is a file where every line already says what the database says.
Those lines are `unchanged`: no write, no audit row, no error. Without that,
downloading the compensation template and uploading it back would open a hundred
identical salary bands, and re-importing the three corrected lines would rewrite
the other seventy-seven.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from operax.rh.templates import Strategy, Template, coerce
from operax.rh.validators import (
    LineError,
    check_enums,
    check_keys,
    check_owned_fields,
    check_unique,
    validate_compensation,
    validate_exam,
)
from operax.rh.workbook import SheetRow

LineStatus = Literal["ok", "unchanged", "error"]


@dataclass(frozen=True, slots=True)
class ImportContext:
    """O que o banco sabe, lido uma vez antes da primeira linha.

    Tudo aqui foi lido **como o usuário que está importando**, com a RLS em
    vigor. É o que faz o escopo valer na escrita sem que a escrita precise
    reimplementá-lo: uma linha que nomeia alguém fora do alcance de quem enviou o
    arquivo simplesmente não encontra a chave, e a resposta é "matrícula não
    existe neste cliente".
    """

    by_registration: dict[str, UUID]
    by_hr_code: dict[str, UUID]
    #: employee_id -> valores atuais, achatados como as colunas do template.
    current: dict[UUID, dict[str, Any]]
    today: date
    #: Quantos dias uma vigência pode retroagir sem tocar competência fechada.
    retroactive_limit_days: int


@dataclass(frozen=True, slots=True)
class LineOutcome:
    """O que acontece com uma linha, e por quê."""

    line: int
    status: LineStatus
    employee_id: UUID | None = None
    #: Só o que muda. Vazio quando a linha já estava como o banco.
    values: dict[str, Any] = dataclass_field(default_factory=dict)
    #: O que estava lá antes, nas mesmas colunas. É o `antes` da auditoria, e
    #: viaja com a decisão para que quem escreve não precise reabrir o contexto.
    previous: dict[str, Any] = dataclass_field(default_factory=dict)
    errors: tuple[LineError, ...] = ()


def retroactive_limit(today: date, last_closed_period_end: date | None) -> int:
    """Quantos dias uma vigência pode retroagir, medido em competência fechada.

    A regra que interessa não é um número de dias: é não reescrever competência
    que a folha já fechou. O banco sabe quais fecharam (`app.payroll_period`), e
    é dele que o limite sai — em vez de um valor inventado que viraria a política
    de folha por omissão.

    Sem nenhuma competência fechada não há nada a proteger, e o limite é o
    tamanho do calendário. A vigência ausente, futura ou ilegível continua sendo
    recusada; só o teto de retroatividade é que fica sem efeito.
    """
    if last_closed_period_end is None:
        return (today - date.min).days
    return (today - last_closed_period_end).days - 1


def validate(
    template: Template, rows: tuple[SheetRow, ...], context: ImportContext
) -> list[LineOutcome]:
    """Cada linha da planilha, julgada na ordem da SPEC §3."""
    resultados: list[LineOutcome] = []
    vistos: dict[str, dict[str, int]] = {coluna: {} for coluna in template.unique_columns}

    for row in rows:
        valores, erros = _coerce_row(template, row.values)

        chave = check_keys(
            {c: valores.get(c) for c in template.key_columns},
            by_registration=context.by_registration,
            by_hr_code=context.by_hr_code,
        )
        erros.extend(chave.errors)
        if chave.employee_id is None:
            resultados.append(LineOutcome(row.line, "error", errors=tuple(erros)))
            continue

        atual = context.current.get(chave.employee_id, {})
        for tabela in template.tables():
            erros.extend(check_owned_fields(valores, atual, table=tabela))
            erros.extend(check_enums(valores, table=tabela))

        for coluna in template.unique_columns:
            campo = _column(template, coluna)
            erros.extend(
                check_unique(
                    valores.get(coluna),
                    column=coluna,
                    label=campo.label if campo else coluna,
                    seen=vistos[coluna],
                    taken=context.by_hr_code if coluna == "hr_code" else {},
                    employee_id=chave.employee_id,
                )
            )
            texto = _texto(valores.get(coluna))
            if texto:
                vistos[coluna].setdefault(texto, row.line)

        match template.strategy:
            case Strategy.EMPLOYEE_UPDATE:
                mudancas = _changed(template, valores, atual)
            case Strategy.COMPENSATION_VERSION:
                mudancas, erros_da_linha = _new_band(template, valores, atual, context)
                erros.extend(erros_da_linha)
            case Strategy.EXAM_INSERT:
                mudancas, erros_da_linha = _new_exam(template, valores, atual, context)
                erros.extend(erros_da_linha)

        # Só a linha que escreve responde por coluna obrigatória. Célula vazia
        # numa planilha pré-preenchida é "não tenho o que dizer aqui" — de quem
        # ainda não tem salário registrado, por exemplo — e não "apague".
        if mudancas:
            erros.extend(_check_required(template, valores))

        if erros:
            resultados.append(
                LineOutcome(row.line, "error", chave.employee_id, errors=tuple(erros))
            )
        elif not mudancas:
            resultados.append(LineOutcome(row.line, "unchanged", chave.employee_id))
        else:
            anterior = {coluna: atual.get(coluna) for coluna in mudancas}
            resultados.append(LineOutcome(row.line, "ok", chave.employee_id, mudancas, anterior))

    return resultados


def _coerce_row(
    template: Template, brutos: dict[str, Any]
) -> tuple[dict[str, Any], list[LineError]]:
    valores: dict[str, Any] = {}
    erros: list[LineError] = []
    for column in template.columns:
        valor, erro = coerce(column, brutos.get(column.column))
        valores[column.column] = valor
        if erro:
            erros.append(erro)
    return valores, erros


def _column(template: Template, nome: str):
    return next((c for c in template.columns if c.column == nome), None)


def _check_required(template: Template, valores: dict[str, Any]) -> list[LineError]:
    erros = []
    for nome in template.required_columns:
        if _texto(valores.get(nome)) == "":
            campo = _column(template, nome)
            rotulo = campo.label if campo else nome
            erros.append(LineError("campo_obrigatorio", f"{rotulo} não pode ficar vazio", nome))
    return erros


def _changed(template: Template, valores: dict[str, Any], atual: dict[str, Any]) -> dict[str, Any]:
    """As colunas preenchíveis cujo valor difere do que está gravado.

    Comparação textual porque um dos lados veio de planilha: `None`, `""` e
    `"  "` são a mesma ausência, e `10` e `"10"` o mesmo número.
    """
    return {
        column.column: valores.get(column.column)
        for column in template.editable()
        if not _igual(valores.get(column.column), atual.get(column.column))
    }


def _new_band(
    template: Template,
    valores: dict[str, Any],
    atual: dict[str, Any],
    context: ImportContext,
) -> tuple[dict[str, Any], list[LineError]]:
    """A vigência nova — ou a constatação de que a linha repete a vigente."""
    if not _changed(template, valores, atual):
        return {}, []
    vigente = atual.get("effective_from")
    erros = validate_compensation(
        valores,
        hoje=context.today,
        limite_dias=context.retroactive_limit_days,
        current_from=vigente if isinstance(vigente, date) else None,
    )
    # A faixa vai inteira, não só o que mudou: uma vigência é uma linha nova, e
    # metade de uma linha nova não é nada.
    return {column.column: valores.get(column.column) for column in template.editable()}, erros


def _new_exam(
    template: Template,
    valores: dict[str, Any],
    atual: dict[str, Any],
    context: ImportContext,
) -> tuple[dict[str, Any], list[LineError]]:
    """O exame novo — ou a constatação de que a linha repete o que já está lá.

    Mesma forma da vigência, e pela mesma razão: o exame vai inteiro, porque meia
    linha nova não é nada. O que muda é o que se compara — não há faixa aberta
    para fechar, só o exame mais recente, que é o que o modelo imprimiu.
    """
    if not _changed(template, valores, atual):
        return {}, []
    ultimo = atual.get("performed_on")
    erros = validate_exam(
        valores,
        hoje=context.today,
        last_performed_on=ultimo if isinstance(ultimo, date) else None,
    )
    return {column.column: valores.get(column.column) for column in template.editable()}, erros


def _igual(a: Any, b: Any) -> bool:
    """Mesmo valor, ainda que não seja o mesmo objeto.

    `Decimal("2500.00")` do banco e `Decimal("2500")` da célula são o mesmo
    salário, e comparar como texto diria que a linha mudou — o que abriria uma
    faixa de vigência nova a cada reenvio do arquivo intocado.
    """
    if isinstance(a, Decimal | int | float) and isinstance(b, Decimal | int | float):
        return Decimal(str(a)) == Decimal(str(b))
    return _texto(a) == _texto(b)


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()
