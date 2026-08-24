"""What each HR template is made of — the one description the whole round trip reads.

The generator builds the spreadsheet from here, the parser maps the columns back
from here, and the importer decides what to write from here. One declaration, so
a column cannot be present in the file and absent from the write, or locked on
screen and writable on upload.

WHAT IS *NOT* DECLARED HERE
Who owns a column. That is `ownership.MATRIX`, and this module reads it instead
of restating it — a template that could disagree with the matrix would be a
second answer to "may the customer change this?", and the two would drift on the
first change. Locking, the "origem: Secullum" note and the enum dropdown are all
derived, never typed twice.

WHY ONLY FOUR TEMPLATES
`app.file_import` accepts eight HR types since migration 17, and four of them
have no complete round trip yet:

  hr_document  — `app.document.storage_path` is NOT NULL, and a spreadsheet
                 carries no file. The document arrives with its upload, not with
                 a row. It answered for the occupational exam until migration 17,
                 which is how the health domain ended up locked out by a
                 constraint on a table it does not use.
  hr_agreement — `app.financial_agreement.document_id` is NOT NULL by explicit
                 decision ("desconto sem autorização documentada não se
                 registra"), and again the authorisation is a file.
  hr_leave,    — `app.leave_period` and `app.workforce_movement` grant no write
  hr_movement    to `authenticated` and carry no write policy: today only the
                 sync writes them. Opening that is a policy decision, and policy
                 decisions stop and ask.

They are named here rather than silently missing, and `GET /rh/template/{type}`
answers 501 with the reason above instead of 404 — "not yet" and "never" are
different answers to the person waiting for the file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Literal

from operax.rh.ownership import ENUMS, Domain, Owner, field
from operax.rh.validators import LineError

Kind = Literal["text", "date", "decimal"]


class Strategy(StrEnum):
    """How a valid line becomes a row.

    Not a free-form callback: an import strategy is a write against the domain,
    and the set of writes this step opens is small, closed and reviewable.
    """

    #: Update the person that already exists — `app.employee` plus, for the PII
    #: columns, an upsert on `app.employee_pii`.
    EMPLOYEE_UPDATE = "employee_update"
    #: Close the open compensation band and open the next one. Correcting is
    #: revoking and creating, never editing in place.
    COMPENSATION_VERSION = "compensation_version"
    #: Record one more occupational exam. Nothing is closed — an exam has no
    #: `effective_to`; it has a date it was taken and a date it stops covering
    #: the person, and both belong to the row that carries them.
    EXAM_INSERT = "exam_insert"


@dataclass(frozen=True, slots=True)
class Column:
    """A column of the data sheet, bound to the column it writes."""

    table: str
    column: str
    label: str
    kind: Kind = "text"

    @property
    def owner(self) -> Owner:
        matched = field(self.table, self.column)
        # Unreachable through the registry: `_check_registry` refuses at import
        # time a column the matrix does not govern.
        assert matched is not None, f"{self.table}.{self.column} não está na matriz"
        return matched.owner

    @property
    def mirror(self) -> str | None:
        matched = field(self.table, self.column)
        return matched.mirror if matched else None

    @property
    def enum(self) -> frozenset[str] | None:
        return ENUMS.get((self.table, self.column))


@dataclass(frozen=True, slots=True)
class Template:
    """One type of import, end to end."""

    type: str
    layout_version: str
    sheet_title: str
    strategy: Strategy
    columns: tuple[Column, ...]
    #: The columns that say *who* the line is about. Printed, locked, and never
    #: written: a key the person can retype is a key that files one employee's
    #: change under another employee.
    key_columns: tuple[str, ...]
    #: Values that may not repeat — inside the file or against the tenant.
    unique_columns: tuple[str, ...] = ()
    #: Columns the database declares NOT NULL. Checked only on a line that
    #: actually writes: a blank line in a pre-filled file means "nothing to say
    #: here", not "erase it".
    required_columns: tuple[str, ...] = ()
    #: The sensitive domain the whole template belongs to. Whoever lacks it does
    #: not download the file, because the file carries the data (SPEC §8).
    domain: Domain | None = None

    @property
    def writes_whole_row(self) -> bool:
        """A linha vai inteira, ou não vai.

        `EMPLOYEE_UPDATE` grava só o que mudou, e célula em branco quer dizer
        "não tenho o que dizer aqui" — de quem ainda não tem CTPS, por exemplo.
        As outras duas criam um **registro novo**, e ali uma célula em branco é
        um valor: metade vinda da planilha e metade herdada do pré-preenchimento
        é um exame que nunca aconteceu, com a validade de outro.
        """
        return self.strategy is not Strategy.EMPLOYEE_UPDATE

    def is_locked(self, column: Column) -> bool:
        """Printed and protected: the sync owns it, or it identifies the line."""
        return column.owner is Owner.SYNC or column.column in self.key_columns

    def editable(self) -> tuple[Column, ...]:
        return tuple(c for c in self.columns if not self.is_locked(c))

    def labels(self) -> tuple[str, ...]:
        return tuple(c.label for c in self.columns)

    def tables(self) -> tuple[str, ...]:
        seen: list[str] = []
        for column in self.columns:
            if column.table not in seen:
                seen.append(column.table)
        return tuple(seen)


_EMPLOYEE_IDENTITY = (
    Column("employee", "registration_number", "Matrícula"),
    Column("employee", "name", "Nome"),
)


TEMPLATES: dict[str, Template] = {
    # O primeiro de todos: sem ID RH gravado, nenhum outro template consegue
    # casar a planilha do cliente com o cadastro. Por isso é o único em que
    # `hr_code` é campo a preencher, e não chave.
    "hr_link": Template(
        type="hr_link",
        layout_version="hr_link.v1",
        sheet_title="Vínculo",
        strategy=Strategy.EMPLOYEE_UPDATE,
        columns=(*_EMPLOYEE_IDENTITY, Column("employee", "hr_code", "ID RH")),
        key_columns=("registration_number",),
        unique_columns=("hr_code",),
    ),
    "hr_employee": Template(
        type="hr_employee",
        layout_version="hr_employee.v1",
        sheet_title="Cadastro",
        strategy=Strategy.EMPLOYEE_UPDATE,
        columns=(
            *_EMPLOYEE_IDENTITY,
            Column("employee", "hr_code", "ID RH"),
            Column("employee", "employment_type", "Regime"),
            Column("employee_pii", "ctps", "CTPS"),
        ),
        key_columns=("registration_number", "hr_code"),
        # Carrega CTPS, que é PII. O domínio é do template inteiro e não da
        # coluna porque o arquivo é uma coisa só: quem baixa, baixa tudo.
        domain=Domain.PII,
    ),
    "hr_compensation": Template(
        type="hr_compensation",
        layout_version="hr_compensation.v1",
        sheet_title="Remuneração",
        strategy=Strategy.COMPENSATION_VERSION,
        columns=(
            *_EMPLOYEE_IDENTITY,
            Column("employee", "hr_code", "ID RH"),
            Column("employee_compensation", "effective_from", "Desde", "date"),
            Column("employee_compensation", "salary", "Salário", "decimal"),
            Column("employee_compensation", "reason", "Motivo"),
        ),
        key_columns=("registration_number", "hr_code"),
        # `effective_from` fica de fora: `check_effective_from` já recusa a
        # vigência ausente, e dizer a mesma coisa duas vezes na mesma linha faz
        # o usuário procurar dois problemas.
        required_columns=("salary",),
        domain=Domain.COMPENSATION,
    ),
    "hr_exam": Template(
        type="hr_exam",
        layout_version="hr_exam.v1",
        sheet_title="ASO",
        strategy=Strategy.EXAM_INSERT,
        columns=(
            *_EMPLOYEE_IDENTITY,
            Column("employee", "hr_code", "ID RH"),
            Column("occupational_exam", "type", "Tipo"),
            Column("occupational_exam", "performed_on", "Realizado em", "date"),
            Column("occupational_exam", "valid_until", "Vence em", "date"),
            Column("occupational_exam", "result", "Resultado"),
        ),
        key_columns=("registration_number", "hr_code"),
        # As duas colunas NOT NULL da tabela. `valid_until` fica de fora porque
        # exame demissional não vence, e `result` porque um exame recém-realizado
        # espera laudo — as duas ausências são estados reais, não esquecimento.
        required_columns=("type", "performed_on"),
        # Aptidão e validade são dado de saúde inteiro: quem não tem o domínio
        # não baixa o arquivo. Diagnóstico, CID e descrição de restrição não têm
        # coluna aqui porque não têm coluna em lugar nenhum (regra 10).
        domain=Domain.HEALTH,
    ),
}


# Os tipos que a migration 16 aceita e que ainda não têm caminho de volta. O
# motivo viaja junto porque é ele que o usuário precisa ler.
SEM_TEMPLATE: dict[str, str] = {
    "hr_document": "documento chega com o arquivo: app.document.storage_path é NOT NULL",
    "hr_agreement": (
        "acordo exige autorização documentada: app.financial_agreement.document_id é NOT NULL"
    ),
    "hr_leave": "app.leave_period não concede escrita ao painel; abrir isso é decisão de policy",
    "hr_movement": (
        "app.workforce_movement não concede escrita ao painel; abrir isso é decisão de policy"
    ),
}


# ---------------------------------------------------------------------------
# A leitura de pré-preenchimento
# ---------------------------------------------------------------------------
# Mora aqui, e não junto do resto do SQL, por uma razão prática: `repository`
# importa o driver, e o teste que confere estas colunas contra o schema real roda
# no `make db-test`, fora do venv do backend. SQL que não pode ser conferido
# contra o banco é SQL que só falha em produção.
_ALIAS = {
    "employee": "e",
    "employee_pii": "p",
    "employee_compensation": "c",
    "occupational_exam": "x",
}

_FROM = {
    Strategy.EMPLOYEE_UPDATE: """
    from app.employee e
    left join app.employee_pii p on p.employee_id = e.id
    where e.status <> 'desligado'
    order by e.name
""",
    # Só a faixa aberta: o template mostra o que vale hoje, e o histórico é
    # assunto da linha do tempo na tela, não de uma planilha de edição.
    Strategy.COMPENSATION_VERSION: """
    from app.employee e
    left join app.employee_compensation c
           on c.employee_id = e.id and c.effective_to is null
    where e.status <> 'desligado'
    order by e.name
""",
    # Um exame por pessoa: o mais recente. A planilha do cliente traz histórico e
    # o template não é o lugar dele — aqui se responde "como está a saúde
    # ocupacional desta pessoa hoje", que é a pergunta que a lista de vencimentos
    # faz. `distinct on` porque o `order by` já ordena por pessoa e data.
    Strategy.EXAM_INSERT: """
    from app.employee e
    left join lateral (
      select o.type, o.performed_on, o.valid_until, o.result
      from app.occupational_exam o
      where o.employee_id = e.id
      order by o.performed_on desc, o.created_at desc
      limit 1
    ) x on true
    where e.status <> 'desligado'
    order by e.name
""",
}


def select_sql(template: Template) -> str:
    """O que já está gravado, nas colunas que este template imprime."""
    colunas = ", ".join(
        f"{_ALIAS[column.table]}.{column.column} as {column.column}" for column in template.columns
    )
    return f"select e.id as employee_id, {colunas}{_FROM[template.strategy]}"


def get_template(tipo: str) -> Template | None:
    return TEMPLATES.get(tipo)


def accepted_versions(template: Template) -> frozenset[str]:
    """As versões de layout que o parser ainda entende.

    Hoje só existe a corrente. A janela do §2 da SPEC — manter o parser da versão
    anterior — abre quando existir uma v2; até lá, declarar uma janela vazia é
    mais honesto do que aceitar qualquer string.
    """
    return frozenset({template.layout_version})


# ---------------------------------------------------------------------------
# Leitura de célula
# ---------------------------------------------------------------------------
_DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d")


def coerce(column: Column, valor: Any) -> tuple[Any, LineError | None]:
    """O que veio da célula, no tipo que o banco espera — ou a recusa.

    Excel devolve `datetime` para célula formatada como data e `str` para quem
    digitou por cima; devolve `float` para número e `str` para quem colou com
    símbolo de moeda. As duas formas chegam, e as duas são o mesmo valor.
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None, None

    if column.kind == "date":
        if isinstance(valor, datetime):
            return valor.date(), None
        if isinstance(valor, date):
            return valor, None
        for formato in _DATE_FORMATS:
            try:
                return datetime.strptime(str(valor).strip(), formato).date(), None
            except ValueError:
                continue
        return None, LineError(
            "data_invalida",
            f"{column.label}={valor!r} não é uma data (use dd/mm/aaaa)",
            column.column,
        )

    if column.kind == "decimal":
        bruto = str(valor).strip().replace("R$", "").replace(" ", "")
        # "1.234,56" é o que sai da planilha em pt-BR; "1234.56" é o que sai de
        # uma célula numérica. Só a primeira tem vírgula.
        if "," in bruto:
            bruto = bruto.replace(".", "").replace(",", ".")
        try:
            return Decimal(bruto), None
        except (InvalidOperation, ValueError):
            return None, LineError(
                "valor_invalido", f"{column.label}={valor!r} não é um valor", column.column
            )

    return str(valor).strip(), None


def _check_registry() -> None:
    """Falha alto no import se um template citar coluna que a matriz não governa.

    É o mesmo princípio do bloco `do $$` que fecha toda migration: a garantia é
    verificada onde ela é declarada, não numa suíte que alguém pode não rodar.
    """
    for template in TEMPLATES.values():
        for column in template.columns:
            if field(column.table, column.column) is None:
                raise RuntimeError(
                    f"template {template.type}: {column.table}.{column.column} não está em "
                    f"ownership.MATRIX — declare o dono antes de pôr a coluna no template"
                )
        declaradas = {c.column for c in template.columns}
        if len(declaradas) != len(template.columns):
            # A linha lida vira um dict por nome de coluna. Duas colunas com o
            # mesmo nome fariam uma sobrescrever a outra em silêncio.
            raise RuntimeError(f"template {template.type}: duas colunas com o mesmo nome")
        faltando = set(template.key_columns) - declaradas
        if faltando:
            raise RuntimeError(
                f"template {template.type}: chave {sorted(faltando)} fora das colunas do arquivo"
            )
        if not template.editable():
            raise RuntimeError(f"template {template.type}: nenhuma coluna preenchível")
        if set(TEMPLATES) & set(SEM_TEMPLATE):
            raise RuntimeError("um tipo não pode estar em TEMPLATES e em SEM_TEMPLATE")


_check_registry()
