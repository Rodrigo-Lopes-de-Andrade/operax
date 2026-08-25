"""Line validation for HR — one funnel for the form and for the upload.

The form that edits one person and the template that uploads eighty run through
these same functions. That is rule 1 of the step, and it is guaranteed here by
construction rather than by discipline: there is no second place where a rule
could be written differently. Upload is the form in bulk.

Pure on purpose. Nothing here opens a connection or knows a tenant — every check
takes what it needs as an argument, and the caller is the one that fetched it.
That is what lets the same function answer for a spreadsheet row it has never
stored and for a form payload it is about to.

Messages are pt-BR: they reach the person fixing the line, and a line that fails
without saying which column and which value is a line that gets fixed by
guessing.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from operax.rh.ownership import ENUMS, Field, field, sync_columns

# Dois centavos, e não zero: a planilha do cliente carrega valores digitados e
# arredondados à mão, e recusar um acordo cujas parcelas somam um centavo a menos
# faria o DP procurar o erro na linha errada.
TOLERANCIA_SOMA = Decimal("0.02")


@dataclass(frozen=True, slots=True)
class LineError:
    """Por que esta linha não entra. Chega ao usuário como está."""

    code: str
    message: str
    column: str | None = None


@dataclass(frozen=True, slots=True)
class KeyResolution:
    """A quem a linha se refere — ou por que não dá para saber."""

    employee_id: UUID | None
    errors: tuple[LineError, ...]


def _texto(valor: Any) -> str:
    """Nulo, vazio e espaço em branco são a mesma coisa vindos de planilha."""
    return "" if valor is None else str(valor).strip()


# ---------------------------------------------------------------------------
# 1. Chaves divergentes
# ---------------------------------------------------------------------------
def check_keys(
    row: Mapping[str, Any],
    *,
    by_registration: Mapping[str, UUID],
    by_hr_code: Mapping[str, UUID],
) -> KeyResolution:
    """Resolve a linha para uma pessoa, ou recusa dizendo qual chave briga.

    As duas chaves são ALTERNATIVAS: cada uma identifica sozinha, e a fase
    inicial do vínculo existe justamente com `hr_code` vazio. O que elas não
    podem é discordar. Quando discordam, a linha falha **com os dois nomes na
    mensagem** — escolher em silêncio entre matrícula e ID RH é como se grava a
    alteração de uma pessoa no cadastro de outra.
    """
    matricula = _texto(row.get("registration_number"))
    hr_code = _texto(row.get("hr_code"))
    erros: list[LineError] = []

    por_matricula = by_registration.get(matricula) if matricula else None
    por_hr = by_hr_code.get(hr_code) if hr_code else None

    if not matricula and not hr_code:
        erros.append(
            LineError("sem_chave", "linha sem matrícula e sem ID RH: não dá para saber de quem é")
        )
        return KeyResolution(None, tuple(erros))

    if matricula and por_matricula is None:
        erros.append(
            LineError(
                "chave_desconhecida",
                f"matrícula {matricula!r} não existe neste cliente",
                "registration_number",
            )
        )
    if hr_code and por_hr is None:
        erros.append(
            LineError(
                "chave_desconhecida", f"ID RH {hr_code!r} não existe neste cliente", "hr_code"
            )
        )
    if por_matricula and por_hr and por_matricula != por_hr:
        erros.append(
            LineError(
                "chaves_divergem",
                f"matrícula {matricula!r} e ID RH {hr_code!r} apontam para pessoas diferentes",
                "registration_number",
            )
        )
        return KeyResolution(None, tuple(erros))

    return KeyResolution(por_matricula or por_hr, tuple(erros))


# ---------------------------------------------------------------------------
# 2. Campo do sync alterado
# ---------------------------------------------------------------------------
def check_owned_fields(
    row: Mapping[str, Any], current: Mapping[str, Any], *, table: str
) -> list[LineError]:
    """Recusa a linha que muda o que o Secullum governa.

    Não é preciosismo: sem esta recusa a alteração é aceita, gravada, e desfeita
    na leitura seguinte. O usuário vê o valor voltar sozinho e conclui que o
    sistema perde dado — que é pior do que ter sido recusado na hora.

    A comparação é textual dos dois lados porque um lado veio de planilha: `10`,
    `"10"` e `" 10 "` são o mesmo valor, e nulo e vazio também.
    """
    erros: list[LineError] = []
    for coluna in sorted(sync_columns(table)):
        if coluna not in row:
            continue
        if _texto(row[coluna]) != _texto(current.get(coluna)):
            f = field(table, coluna)
            origem = f" (origem: {f.mirror})" if f and f.mirror else ""
            pendente = " — pendente de confirmação com o cliente" if f and f.pending else ""
            erros.append(
                LineError(
                    "campo_do_sync",
                    f"{coluna} pertence ao Secullum{origem}; a alteração não teria "
                    f"efeito{pendente}",
                    coluna,
                )
            )
    return erros


# ---------------------------------------------------------------------------
# 3. Enum fora do catálogo
# ---------------------------------------------------------------------------
def check_enums(row: Mapping[str, Any], *, table: str) -> list[LineError]:
    """O que o banco recusaria depois, recusado agora e com a lista junto."""
    erros: list[LineError] = []
    for (tabela, coluna), aceitos in ENUMS.items():
        if tabela != table or coluna not in row:
            continue
        valor = _texto(row[coluna])
        if valor and valor not in aceitos:
            erros.append(
                LineError(
                    "enum_invalido",
                    f"{coluna}={valor!r} não é um valor aceito. Aceitos: "
                    f"{', '.join(sorted(aceitos))}",
                    coluna,
                )
            )
    return erros


# ---------------------------------------------------------------------------
# 4. Vigência retroativa
# ---------------------------------------------------------------------------
def check_effective_from(
    valor: Any, *, hoje: date, limite_dias: int, column: str = "effective_from"
) -> list[LineError]:
    """Uma vigência velha demais reescreve competência já fechada.

    `limite_dias` não tem valor padrão de propósito: quanto retroagir é política
    de folha, não do validador, e um padrão inventado aqui viraria a política por
    omissão.
    """
    if valor in (None, ""):
        return [LineError("vigencia_ausente", f"{column} é obrigatória numa vigência", column)]
    if not isinstance(valor, date):
        return [LineError("data_invalida", f"{column}={valor!r} não é uma data", column)]
    if valor > hoje:
        return [LineError("vigencia_futura", f"{column} está no futuro: {valor}", column)]
    if (hoje - valor).days > limite_dias:
        return [
            LineError(
                "vigencia_retroativa",
                f"{column}={valor} retroage {(hoje - valor).days} dias, além do limite de "
                f"{limite_dias}. Correção de período fechado é revogação, não vigência nova",
                column,
            )
        ]
    return []


def check_new_band(
    valor: Any, *, current_from: date | None, column: str = "effective_from"
) -> list[LineError]:
    """Vigência nova começa depois da vigente. Sobrepor não é corrigir.

    A faixa aberta é fechada em `desde - 1` quando a próxima entra. Com a mesma
    data nas duas, esse fechamento produziria um período que termina antes de
    começar — o banco recusaria, e a mensagem seria sobre `check` de data em vez
    de sobre o que a pessoa fez. Corrigir a faixa vigente é revogá-la, e revogar
    é outro caminho.
    """
    if not isinstance(valor, date) or current_from is None:
        return []
    if valor <= current_from:
        return [
            LineError(
                "vigencia_sobreposta",
                f"já existe vigência a partir de {current_from}; para mudar aquela faixa, "
                f"revogue-a — vigência nova começa depois dela",
                column,
            )
        ]
    return []


# ---------------------------------------------------------------------------
# 5. Parcelas que não fecham com o acordo
# ---------------------------------------------------------------------------
def _decimal(valor: Any) -> Decimal | None:
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None


def check_installments(
    total_amount: Any, installment_count: Any, parcelas: Sequence[Mapping[str, Any]]
) -> list[LineError]:
    """O acordo e suas parcelas têm de contar a mesma história.

    Três formas de mentir, e as três aparecem em planilha: a soma não bate, a
    quantidade não bate, e a numeração pula ou repete.
    """
    erros: list[LineError] = []
    total = _decimal(total_amount)
    if total is None:
        return [
            LineError(
                "valor_invalido", f"total_amount={total_amount!r} não é um valor", "total_amount"
            )
        ]

    valores = [_decimal(p.get("amount")) for p in parcelas]
    if any(v is None for v in valores):
        erros.append(LineError("valor_invalido", "há parcela com valor ilegível", "amount"))
        valores = [v for v in valores if v is not None]

    soma = sum(valores, Decimal("0"))
    if abs(soma - total) > TOLERANCIA_SOMA:
        erros.append(
            LineError(
                "parcelas_nao_somam",
                f"as parcelas somam {soma} e o acordo é de {total}",
                "total_amount",
            )
        )

    try:
        esperadas = int(installment_count)
    except (TypeError, ValueError):
        esperadas = -1
    if esperadas != len(parcelas):
        erros.append(
            LineError(
                "quantidade_de_parcelas",
                f"o acordo declara {installment_count} parcela(s) e vieram {len(parcelas)}",
                "installment_count",
            )
        )

    numeros = [p.get("number") for p in parcelas]
    if sorted(str(n) for n in numeros) != sorted(str(n) for n in range(1, len(parcelas) + 1)):
        erros.append(
            LineError(
                "numeracao_de_parcelas",
                f"a numeração das parcelas não vai de 1 a {len(parcelas)}: {numeros}",
                "number",
            )
        )
    return erros


# ---------------------------------------------------------------------------
# 6. Afastamento sobreposto
# ---------------------------------------------------------------------------
def check_leave_overlap(
    start_date: Any,
    end_date: Any,
    *,
    existentes: Iterable[tuple[date, date | None]],
) -> list[LineError]:
    """Duas ausências no mesmo dia é uma delas errada.

    Afastamento em aberto (`end_date` nulo) é normal e cobre daqui em diante, por
    isso o fim ausente vira `date.max` na comparação em vez de encerrar o
    intervalo no início.
    """
    if not isinstance(start_date, date):
        return [
            LineError("data_invalida", f"start_date={start_date!r} não é uma data", "start_date")
        ]
    if end_date not in (None, "") and not isinstance(end_date, date):
        return [LineError("data_invalida", f"end_date={end_date!r} não é uma data", "end_date")]

    fim = end_date if isinstance(end_date, date) else date.max
    if fim < start_date:
        return [
            LineError("periodo_invertido", f"end_date {fim} é anterior a {start_date}", "end_date")
        ]

    for outro_inicio, outro_fim in existentes:
        outro_fim = outro_fim or date.max
        if start_date <= outro_fim and outro_inicio <= fim:
            return [
                LineError(
                    "afastamento_sobreposto",
                    f"o período {start_date} a {fim} se sobrepõe ao afastamento já registrado "
                    f"de {outro_inicio} a {outro_fim}",
                    "start_date",
                )
            ]
    return []


# ---------------------------------------------------------------------------
# 7. Duplicidade — dentro do arquivo e contra o banco
# ---------------------------------------------------------------------------
def check_unique(
    valor: Any,
    *,
    column: str,
    label: str,
    seen: Mapping[str, int],
    taken: Mapping[str, UUID],
    employee_id: UUID | None,
) -> list[LineError]:
    """Um valor que identifica sozinho não pode aparecer duas vezes.

    As duas metades da checagem existem porque as duas acontecem: a planilha
    volta com a mesma linha copiada, e o ID RH que o cliente digitou já está no
    cadastro de outra pessoa. A segunda é a que importa — sem ela o `unique`
    parcial de `hr_code` recusaria o lote inteiro no `insert`, sem dizer qual
    linha causou.

    `taken` apontando para a própria pessoa não é duplicidade: é a linha que já
    estava certa e foi reenviada.
    """
    texto = _texto(valor)
    if not texto:
        return []
    erros: list[LineError] = []
    anterior = seen.get(texto)
    if anterior is not None:
        erros.append(
            LineError(
                "duplicado_no_arquivo",
                f"{label} {texto!r} já aparece na linha {anterior} deste mesmo arquivo",
                column,
            )
        )
    dono = taken.get(texto)
    if dono is not None and dono != employee_id:
        erros.append(
            LineError(
                "duplicado_no_cadastro",
                f"{label} {texto!r} já pertence a outro colaborador",
                column,
            )
        )
    return erros


# ---------------------------------------------------------------------------
# Os quatro domínios — é o que import e formulário chamam
# ---------------------------------------------------------------------------
def validate_registration(
    row: Mapping[str, Any], current: Mapping[str, Any], *, table: str = "employee"
) -> list[LineError]:
    """Domínio 1 — cadastro e posição."""
    return check_owned_fields(row, current, table=table) + check_enums(row, table=table)


def validate_documents(row: Mapping[str, Any], *, table: str = "document") -> list[LineError]:
    """Domínio 2 — documentos e ASO. Validade no passado é aviso, não erro:
    documento vencido é um fato do cadastro, e recusá-lo esconderia justamente o
    que a lista de vencimentos existe para mostrar."""
    return check_enums(row, table=table)


def validate_exam(
    row: Mapping[str, Any], *, hoje: date, last_performed_on: date | None = None
) -> list[LineError]:
    """Domínio 2b — exame ocupacional: aptidão, realização e validade.

    Três recusas, e a terceira é a que não é óbvia. O modelo imprime **um exame
    por pessoa**, o mais recente, e o upload é a diferença contra ele. Uma data
    anterior à que veio impressa não é uma correção: é um exame do passado, que
    seria inserido de novo a cada reenvio do mesmo arquivo — o modelo continuaria
    imprimindo o recente, a linha continuaria diferindo, e a pessoa juntaria uma
    cópia por rodada. Backfill de histórico não passa por aqui.

    O que não se recusa: validade no passado. ASO vencido é um fato do cadastro e
    é exatamente o que a coluna de vencimentos existe para mostrar — a mesma
    decisão de `validate_documents`.
    """
    erros: list[LineError] = []
    realizado = row.get("performed_on")
    validade = row.get("valid_until")

    if isinstance(realizado, date):
        if realizado > hoje:
            erros.append(
                LineError(
                    "data_no_futuro",
                    f"exame realizado em {realizado:%d/%m/%Y} é uma data futura: "
                    "exame que ainda não aconteceu não se registra",
                    "performed_on",
                )
            )
        if isinstance(validade, date) and validade <= realizado:
            erros.append(
                LineError(
                    "validade_invalida",
                    f"a validade ({validade:%d/%m/%Y}) precisa ser depois da realização "
                    f"({realizado:%d/%m/%Y})",
                    "valid_until",
                )
            )
        if last_performed_on is not None and realizado < last_performed_on:
            erros.append(
                LineError(
                    "exame_anterior",
                    f"já há exame registrado em {last_performed_on:%d/%m/%Y}; o modelo carrega o "
                    "mais recente, e um exame anterior entraria de novo a cada reenvio",
                    "performed_on",
                )
            )
    return erros


def validate_leave(
    row: Mapping[str, Any], *, existentes: Iterable[tuple[date, date | None]]
) -> list[LineError]:
    """Domínio 3 — afastamentos e movimentações."""
    return check_enums(row, table="leave_period") + check_leave_overlap(
        row.get("start_date"), row.get("end_date"), existentes=existentes
    )


def validate_compensation(
    row: Mapping[str, Any], *, hoje: date, limite_dias: int, current_from: date | None = None
) -> list[LineError]:
    """Domínio 4a — remuneração, sempre por vigência.

    `current_from` é o início da faixa aberta hoje, quando existe. O padrão
    `None` é o caso real de quem ainda não tem salário registrado, não uma
    conveniência: sem faixa vigente não há o que sobrepor.
    """
    return check_effective_from(
        row.get("effective_from"), hoje=hoje, limite_dias=limite_dias
    ) + check_new_band(row.get("effective_from"), current_from=current_from)


def validate_agreement(
    agreement: Mapping[str, Any], parcelas: Sequence[Mapping[str, Any]]
) -> list[LineError]:
    """Domínio 4b — acordos e parcelas."""
    return check_enums(agreement, table="financial_agreement") + check_installments(
        agreement.get("total_amount"), agreement.get("installment_count"), parcelas
    )


__all__ = [
    "Field",
    "KeyResolution",
    "LineError",
    "check_effective_from",
    "check_enums",
    "check_installments",
    "check_keys",
    "check_new_band",
    "check_leave_overlap",
    "check_owned_fields",
    "check_unique",
    "validate_agreement",
    "validate_compensation",
    "validate_documents",
    "validate_exam",
    "validate_leave",
    "validate_registration",
]
