"""The customer's payroll arriving as a spreadsheet — the file becomes a verdict.

The v1 of the Domínio integration is a file, not an API: the accounting firm
sends a report, somebody uploads it. That decision is recorded in
`docs/COBERTURA-ESCOPO.md` §5, and it is what removed "Domínio libera a API" from
the risk table.

WHY OUR TEMPLATE, AND NOT THE DOMÍNIO EXPORT AS IT COMES
§6 of the contracted scope obliges *us* to publish a standard template, so that
is what this module generates and reads back. A file we generated carries a
control sheet — layout version, tenant, column keys and a header fingerprint —
and each of those turns a class of silent wrong import into a refusal before the
first line is read. A native Domínio export carries none of it, and matching it
means guessing columns by their labels.

⚠️ **Premissa declarada:** se o cliente disser que vai mandar o export do Domínio
cru, o que muda é só a porta de entrada — `parse_upload`. O veredito, o mapa de
eventos, a duplicidade e o relatório por linha continuam valendo, porque nada
aqui embaixo depende de como o arquivo chegou.

WHAT THIS MODULE DOES NOT DO
It does not write. `verdict` is pure: rows in, outcomes out. The same split the
HR import uses (`rh/importer.py` decides, `rh/repository.py` writes), and for the
same reason — the preview screen has to show what *would* happen before anyone
confirms, and a decider that writes cannot be asked twice.

AN UNMAPPED EVENT CODE IS NOT AN ERROR
`app.payroll_event_map` (migration 30) says which category each of the customer's
event codes belongs to, and it is curated with the accountant — it will never be
complete on the first upload. A line whose code is unmapped **imports normally**:
the value is real and the total is right. What it does not do is land in a
category, so the eight indicators that depend on categories skip it. That is a
pendency reported next to the line, not a refusal — blocking a whole payroll on
an unmapped code would make the first import impossible, which is the month the
customer most needs it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Literal
from uuid import UUID

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from operax.rh.validators import LineError

# O contrato da aba de controle é um só, e vem de onde ele já existe. Reescrever
# `header_hash` aqui seria manter dois formatos que divergem na primeira mudança
# — e o arquivo de folha e o de RH são lidos pela mesma tela.
from operax.rh.workbook import META_SHEET, SheetRow, WorkbookError, header_hash

#: O tipo em `app.file_import.type`. Já existe no check da migration 09 — este
#: módulo não precisou de migration nenhuma para nascer.
IMPORT_TYPE = "folha"
LAYOUT_VERSION = "folha-1"
SHEET_TITLE = "Folha"

CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_BAIXE_O_MODELO = "Baixe o modelo da competência e refaça o preenchimento."

Kind = Literal["text", "decimal"]


@dataclass(frozen=True, slots=True)
class Column:
    """Uma coluna do modelo, com o nome que o usuário lê e a chave que grava."""

    key: str
    label: str
    kind: Kind = "text"
    required: bool = False
    #: O que a coluna quer dizer, no comentário da célula do cabeçalho. É onde
    #: quem preenche procura antes de perguntar.
    note: str | None = None


#: A natureza como a contabilidade a escreve, e como o banco a guarda. O check de
#: `app.payroll_entry.nature` está em inglês; a planilha do cliente, não.
NATURES: dict[str, str] = {
    "Provento": "earning",
    "Desconto": "deduction",
    "Base": "base",
    "Encargo": "payroll_charge",
    "Informativo": "informational",
}

COLUMNS: tuple[Column, ...] = (
    Column(
        "employee_code",
        "Matrícula",
        required=True,
        note="A matrícula como ela está no sistema de ponto. É por ela que a linha "
        "encontra a pessoa — nome não identifica ninguém.",
    ),
    Column(
        "employee_name",
        "Colaborador",
        note="Só para conferência humana. O sistema ignora este campo e usa a matrícula.",
    ),
    Column("code", "Código do evento", required=True, note="O código do seu plano de contas."),
    Column("description", "Descrição do evento"),
    Column(
        "nature",
        "Natureza",
        required=True,
        note="Um de: " + ", ".join(NATURES),
    ),
    Column("reference", "Referência", kind="decimal", note="Horas, dias ou percentual, se houver."),
    Column("amount", "Valor", kind="decimal", required=True),
)

_FONT_HEADER = Font(bold=True, color="FFFFFF")
_FILL_HEADER = PatternFill("solid", fgColor="1F2937")
_MIN_WIDTH = 14
_MAX_WIDTH = 42


def labels() -> tuple[str, ...]:
    return tuple(c.label for c in COLUMNS)


def accepted_versions() -> frozenset[str]:
    """As versões que o parser ainda entende. Só a corrente, enquanto só houver uma."""
    return frozenset({LAYOUT_VERSION})


# ---------------------------------------------------------------------------
# Geração
# ---------------------------------------------------------------------------
def build_template(
    *,
    tenant_id: UUID,
    year: int,
    month: int,
    generated_at: datetime,
    rows: tuple[dict[str, Any], ...] = (),
) -> bytes:
    """O modelo da competência, vazio ou com o que já foi importado antes.

    A competência vai na aba de controle, e não numa coluna repetida em cada
    linha: uma planilha com duas competências dentro é um arquivo que ninguém
    consegue conferir, e a soma dele não bate com nenhum holerite.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_TITLE

    for indice, column in enumerate(COLUMNS, start=1):
        celula = ws.cell(row=1, column=indice, value=column.label)
        celula.font = _FONT_HEADER
        celula.fill = _FILL_HEADER
        celula.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if column.note:
            celula.comment = _comentario(column.note)
        largura = max(len(column.label) + 4, _MIN_WIDTH)
        ws.column_dimensions[get_column_letter(indice)].width = min(largura, _MAX_WIDTH)

    for deslocamento, registro in enumerate(rows):
        linha = 2 + deslocamento
        for indice, column in enumerate(COLUMNS, start=1):
            celula = ws.cell(row=linha, column=indice, value=registro.get(column.key))
            if column.kind == "decimal":
                celula.number_format = "#,##0.00"

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{max(2, 1 + len(rows))}"

    meta = wb.create_sheet(META_SHEET)
    pares = (
        ("layout_version", LAYOUT_VERSION),
        ("type", IMPORT_TYPE),
        ("tenant", str(tenant_id)),
        ("sheet", SHEET_TITLE),
        ("period", f"{year:04d}-{month:02d}"),
        ("generated_at", generated_at.isoformat()),
        ("columns", ",".join(c.key for c in COLUMNS)),
        ("header_hash", header_hash(labels())),
    )
    for linha, (chave, valor) in enumerate(pares, start=1):
        meta.cell(row=linha, column=1, value=chave)
        meta.cell(row=linha, column=2, value=valor)
    meta.protection.sheet = True
    meta.sheet_state = "hidden"

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _comentario(texto: str):
    from openpyxl.comments import Comment

    comentario = Comment(texto, "OperaX")
    comentario.width = 300
    comentario.height = 90
    return comentario


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ParsedPayroll:
    """O arquivo aceito: a competência que ele declara e as linhas dele."""

    layout_version: str
    year: int
    month: int
    rows: tuple[SheetRow, ...]


def parse_upload(data: bytes, *, tenant_id: UUID) -> ParsedPayroll:
    """O arquivo de volta, ou a recusa do arquivo inteiro com o motivo.

    O arquivo é julgado antes da primeira linha, porque arquivo errado não tem
    linha certa — e a recusa que nomeia o motivo é a diferença entre "deu erro"
    e "você mandou a competência passada".
    """
    try:
        wb = load_workbook(BytesIO(data), data_only=True, read_only=False)
    except Exception as erro:  # noqa: BLE001 — qualquer falha aqui é "não é xlsx"
        raise WorkbookError(
            "arquivo_ilegivel", f"Não consegui abrir o arquivo como .xlsx. {_BAIXE_O_MODELO}"
        ) from erro

    if META_SHEET not in wb.sheetnames:
        raise WorkbookError(
            "sem_meta",
            f"Arquivo sem a aba de controle `{META_SHEET}` — ele não foi gerado aqui. "
            f"{_BAIXE_O_MODELO}",
        )

    meta = _ler_meta(wb[META_SHEET])

    if meta.get("type") != IMPORT_TYPE:
        raise WorkbookError(
            "tipo_divergente",
            f"O arquivo é do tipo {meta.get('type')!r} e foi enviado como folha. "
            "Escolha o tipo correto ou baixe o modelo de folha.",
        )
    if meta.get("tenant") != str(tenant_id):
        raise WorkbookError(
            "tenant_divergente",
            "Este arquivo foi gerado para outro cliente e não pode ser importado aqui.",
        )
    if meta.get("layout_version") not in accepted_versions():
        raise WorkbookError(
            "layout_antigo",
            f"O modelo é da versão {meta.get('layout_version')!r}, que não é mais aceita. "
            f"{_BAIXE_O_MODELO}",
        )

    year, month = _competencia(meta.get("period", ""))

    ws = wb[meta["sheet"]] if meta.get("sheet") in wb.sheetnames else wb.worksheets[0]
    cabecalho = tuple(_texto(c.value) for c in next(ws.iter_rows(min_row=1, max_row=1)))
    if header_hash(cabecalho) != meta.get("header_hash"):
        raise WorkbookError(
            "cabecalho_alterado",
            "O cabeçalho da planilha foi alterado — coluna inserida, removida ou renomeada. "
            f"{_BAIXE_O_MODELO}",
        )

    chaves = meta.get("columns", "").split(",")
    if len(chaves) != len(cabecalho):
        raise WorkbookError(
            "cabecalho_alterado",
            f"O cabeçalho tem {len(cabecalho)} coluna(s) e o modelo declara {len(chaves)}. "
            f"{_BAIXE_O_MODELO}",
        )

    linhas: list[SheetRow] = []
    for numero, celulas in enumerate(ws.iter_rows(min_row=2), start=2):
        valores = {chave: celula.value for chave, celula in zip(chaves, celulas, strict=False)}
        if all(_texto(v) == "" for v in valores.values()):
            # Linha em branco no fim é rastro de quem apagou o conteúdo em vez de
            # excluir a linha. Não é erro; não é linha.
            continue
        linhas.append(SheetRow(line=numero, values=valores))

    return ParsedPayroll(
        layout_version=meta["layout_version"], year=year, month=month, rows=tuple(linhas)
    )


def _competencia(valor: str) -> tuple[int, int]:
    try:
        ano, mes = valor.split("-")
        year, month = int(ano), int(mes)
        if not 1 <= month <= 12:
            raise ValueError(month)
    except (ValueError, AttributeError) as erro:
        raise WorkbookError(
            "competencia_invalida",
            f"A aba de controle não declara uma competência válida ({valor!r}). {_BAIXE_O_MODELO}",
        ) from erro
    return year, month


def _ler_meta(ws) -> dict[str, str]:
    return {
        _texto(linha[0].value): _texto(linha[1].value)
        for linha in ws.iter_rows(min_row=1, max_col=2)
        if linha and _texto(linha[0].value)
    }


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _decimal(valor: Any) -> Decimal | None:
    """O número como a planilha o entrega, ou `None` se não for número.

    Aceita o formato brasileiro (`1.234,56`) porque é o que sai do sistema da
    contabilidade — recusar isso faria o usuário reformatar mil linhas à mão
    para descobrir, no fim, que o total continua o mesmo.
    """
    if valor is None or _texto(valor) == "":
        return None
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))
    texto = _texto(valor).replace("R$", "").strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


# ---------------------------------------------------------------------------
# Veredito
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class LineOutcome:
    """O que aconteceria com esta linha, sem que nada tenha acontecido."""

    line: int
    employee_id: UUID | None
    values: dict[str, Any]
    errors: tuple[LineError, ...] = ()
    #: Pendências que **não** impedem a linha de entrar, e que a tela mostra ao
    #: lado dela. Hoje só uma: código de evento fora do mapa de categorias.
    warnings: tuple[LineError, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class Report:
    """O veredito do arquivo inteiro, no formato que `app.file_import` guarda."""

    rows_total: int
    rows_ok: int
    rows_error: int
    outcomes: tuple[LineOutcome, ...]

    #: Códigos de evento sem categoria, uma vez cada. É a lista que a curadoria
    #: com a contabilidade recebe — e ela vale mais que a contagem de linhas.
    unmapped_codes: tuple[str, ...] = ()

    def as_json(self) -> dict[str, Any]:
        """O `report` de `app.file_import`, com o que a tela precisa mostrar."""
        return {
            "rows_total": self.rows_total,
            "rows_ok": self.rows_ok,
            "rows_error": self.rows_error,
            "unmapped_codes": list(self.unmapped_codes),
            "lines": [
                {
                    "line": o.line,
                    "errors": [
                        {"code": e.code, "message": e.message, "column": e.column} for e in o.errors
                    ],
                    "warnings": [
                        {"code": w.code, "message": w.message, "column": w.column}
                        for w in o.warnings
                    ],
                }
                for o in self.outcomes
                if o.errors or o.warnings
            ],
        }


def verdict(
    rows: tuple[SheetRow, ...],
    *,
    employees: dict[str, UUID],
    mapped_codes: frozenset[str],
) -> Report:
    """O que cada linha faria, sem fazer nada.

    `employees` é matrícula -> id, resolvida por quem chamou sob a RLS do
    usuário: uma linha só encontra quem o usuário já podia enxergar, e um
    colaborador fora do alcance dele é indistinguível de um que não existe.
    """
    outcomes: list[LineOutcome] = []
    vistos: Counter[tuple[str, str, str, str]] = Counter()
    sem_categoria: list[str] = []

    for row in rows:
        erros: list[LineError] = []
        avisos: list[LineError] = []
        valores: dict[str, Any] = {}

        for column in COLUMNS:
            bruto = row.values.get(column.key)
            if column.kind == "decimal":
                numero = _decimal(bruto)
                if numero is None and _texto(bruto) != "":
                    erros.append(
                        LineError(
                            "valor_invalido",
                            f"{column.label}: {_texto(bruto)!r} não é um número.",
                            column.key,
                        )
                    )
                valores[column.key] = numero
            else:
                valores[column.key] = _texto(bruto)

            if column.required and (
                valores[column.key] is None or _texto(valores[column.key]) == ""
            ):
                erros.append(
                    LineError("campo_obrigatorio", f"{column.label} é obrigatório.", column.key)
                )

        matricula = _texto(valores.get("employee_code"))
        employee_id = employees.get(matricula) if matricula else None
        if matricula and employee_id is None:
            erros.append(
                LineError(
                    "colaborador_desconhecido",
                    f"Não encontrei a matrícula {matricula!r} entre os colaboradores que você "
                    f"enxerga. Confira a matrícula ou o cadastro.",
                    "employee_code",
                )
            )

        natureza = _texto(valores.get("nature"))
        if natureza and natureza not in NATURES:
            erros.append(
                LineError(
                    "natureza_invalida",
                    f"Natureza {natureza!r} não existe. Use uma de: {', '.join(NATURES)}.",
                    "nature",
                )
            )
        else:
            valores["nature"] = NATURES.get(natureza, natureza)

        codigo = _texto(valores.get("code"))
        if codigo and codigo not in mapped_codes:
            avisos.append(
                LineError(
                    "codigo_sem_categoria",
                    f"O código {codigo!r} ainda não tem categoria mapeada. A linha entra e o "
                    f"valor conta no total; ela só não aparece nos indicadores por categoria.",
                    "code",
                )
            )
            if codigo not in sem_categoria:
                sem_categoria.append(codigo)

        assinatura = (
            matricula,
            codigo,
            _texto(valores.get("reference")),
            _texto(valores.get("amount")),
        )
        vistos[assinatura] += 1
        if vistos[assinatura] > 1:
            avisos.append(
                LineError(
                    "linha_repetida",
                    "Esta linha é idêntica a outra do mesmo arquivo — mesma matrícula, mesmo "
                    "código, mesmo valor. Confira se não foi colada duas vezes.",
                    None,
                )
            )

        outcomes.append(
            LineOutcome(
                line=row.line,
                employee_id=employee_id,
                values=valores,
                errors=tuple(erros),
                warnings=tuple(avisos),
            )
        )

    com_erro = sum(1 for o in outcomes if o.errors)
    return Report(
        rows_total=len(outcomes),
        rows_ok=len(outcomes) - com_erro,
        rows_error=com_erro,
        outcomes=tuple(outcomes),
        unmapped_codes=tuple(sem_categoria),
    )
