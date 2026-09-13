"""Who owns each field — the sync, or the customer's HR.

Without this, someone edits a field the mirror governs and the next read undoes
it. Silently: no error, no conflict, the value simply reverts hours later and the
person who typed it concludes the system loses data.

So ownership is declared once, here, and three things read it: the template
generator locks the sync columns, the screen renders them read-only with
"Secullum · leitura de HH:MM", and the import fails a line that tries to change
one. Three refusals, one source.

WHY A CONSTANT AND NOT A TABLE
A panel-editable ownership matrix is a panel-editable way to overwrite the source
of truth. Changing who owns a field is a decision with a review and a deploy
behind it, not a toggle.

WHAT DECIDED EACH ROW
The mirror itself, read from production on 24/08/2026, not the field's name.
`secullum."Funcionario"` carries `Cpf`, `Rg`, `NumeroPis`, `Nascimento`, `Mae`,
`Pai`, `Telefone`, `Email` and `Endereco` — so almost the whole PII block is
read-only, which is worth knowing before someone builds a form for it. `ctps` is
the exception: nothing in the mirror feeds it.

THE PENDING ONES
Acting unit and an early termination date are marked `pending`: the customer has
not said yet whether the Secullum knows them. Until then they are treated as
sync — the safe direction, because a field wrongly frozen is an annoyance and a
field wrongly editable is data that disappears on the next sync. They keep the
flag so the screen can say "pendente de confirmação" instead of claiming the
Secullum owns something nobody checked.

`manager_employee_id` WAS the third, and measuring it settled half the question
and moved the other half. The Secullum does know the manager — as
`Funcionario.EstruturaId` → `Estrutura`, promoted since migration 27 into
`app.manager` and reachable as `employee.manager_id`. What it does not know is
which of our employees that manager IS, and no name match resolves it (zero of
four in production, 26/08/2026). So `manager_employee_id` is no longer pending
on the customer: it is pending on a curation nobody has needed yet, and it stays
`SYNC` because HR filling it by hand would put a guessed hierarchy next to a read
one with no way to tell them apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Owner(StrEnum):
    """Who may change the value."""

    SYNC = "sync"
    HR = "hr"


class Domain(StrEnum):
    """Mirrors `app.sensitive_domain` (migration 02)."""

    PII = "pii"
    COMPENSATION = "compensation"
    HEALTH = "health"
    DISCIPLINARY = "disciplinary"


@dataclass(frozen=True, slots=True)
class Field:
    table: str
    column: str
    owner: Owner
    domain: Domain | None = None
    # Corrigir não é editar: a linha vigente é revogada e outra é criada.
    versioned: bool = False
    # Tratado como sync até o cliente confirmar de onde o dado vem.
    pending: bool = False
    # A coluna do espelho que governa esta, quando o dono é o sync. É o que a
    # tela cita ao dizer de onde veio o valor.
    mirror: str | None = None


MATRIX: tuple[Field, ...] = (
    # --- app.employee: o esqueleto vem do espelho ---------------------------
    Field("employee", "registration_number", Owner.SYNC, mirror="Funcionario.NumeroFolha"),
    Field("employee", "name", Owner.SYNC, mirror="Funcionario.Nome"),
    Field("employee", "hired_on", Owner.SYNC, mirror="Funcionario.Admissao"),
    # A unidade sai do departamento do espelho pelo mapa de curadoria
    # (`app.unit_secullum_map`), nunca por empresa — 26% divergem.
    Field("employee", "unit_id", Owner.SYNC, mirror="Funcionario.departamento_id"),
    Field("employee", "company_id", Owner.SYNC, mirror="Funcionario.empresa_id"),
    Field("employee", "department_id", Owner.SYNC, mirror="Funcionario.departamento_id"),
    Field("employee", "secullum_employee_id", Owner.SYNC, mirror="Funcionario.FuncionarioId"),
    # Sem origem no espelho: nenhuma coluna de `Funcionario` diz o regime. Como
    # `ctps`, quem sabe é o RH.
    Field("employee", "employment_type", Owner.HR),
    Field("employee", "status", Owner.SYNC, mirror="Funcionario.Demissao"),
    # A planilha DESLIGADOS serve de conferência na carga, não de fonte: o
    # desligamento é fato do ponto, e duas fontes para um fato é uma a mais.
    Field("employee", "terminated_on", Owner.SYNC, pending=True, mirror="Funcionario.Demissao"),
    Field("employee", "manager_employee_id", Owner.SYNC, pending=True),
    Field("employee", "hr_code", Owner.HR),
    # `employee.cargo` é o valor corrente; a linha que manda é a vigência em
    # `employee_position`. O espelho também traz `Funcao`, então este é
    # candidato natural a virar sync junto com os três pendentes — a SPEC §4
    # decidiu RH, e é o que está escrito aqui.
    Field("employee", "cargo", Owner.HR, versioned=True),
    # --- app.employee_pii: quase tudo é leitura ------------------------------
    Field("employee_pii", "cpf", Owner.SYNC, Domain.PII, mirror="Funcionario.Cpf"),
    Field("employee_pii", "rg", Owner.SYNC, Domain.PII, mirror="Funcionario.Rg"),
    Field("employee_pii", "pis", Owner.SYNC, Domain.PII, mirror="Funcionario.NumeroPis"),
    Field("employee_pii", "birth_date", Owner.SYNC, Domain.PII, mirror="Funcionario.Nascimento"),
    Field("employee_pii", "mother_name", Owner.SYNC, Domain.PII, mirror="Funcionario.Mae"),
    Field("employee_pii", "father_name", Owner.SYNC, Domain.PII, mirror="Funcionario.Pai"),
    Field("employee_pii", "phone", Owner.SYNC, Domain.PII, mirror="Funcionario.Telefone"),
    Field("employee_pii", "personal_email", Owner.SYNC, Domain.PII, mirror="Funcionario.Email"),
    Field("employee_pii", "address", Owner.SYNC, Domain.PII, mirror="Funcionario.Endereco"),
    # A única do bloco sem origem no espelho.
    Field("employee_pii", "ctps", Owner.HR, Domain.PII),
    # --- posição e remuneração: vigência, nunca edição -----------------------
    Field("employee_position", "cargo", Owner.HR, versioned=True),
    Field("employee_position", "unit_id", Owner.HR, versioned=True),
    Field("employee_position", "effective_from", Owner.HR, versioned=True),
    Field("employee_compensation", "salary", Owner.HR, Domain.COMPENSATION, versioned=True),
    Field("employee_compensation", "reason", Owner.HR, Domain.COMPENSATION, versioned=True),
    Field("employee_compensation", "effective_from", Owner.HR, Domain.COMPENSATION, versioned=True),
    # --- documentos e ASO ----------------------------------------------------
    Field("document", "type_id", Owner.HR),
    Field("document", "issued_on", Owner.HR),
    Field("document", "valid_until", Owner.HR),
    Field("document", "status", Owner.HR),
    # ASO guarda aptidão e validade. Diagnóstico e CID não têm coluna aqui, nem
    # em nenhum outro lugar — regra 10, negada nas três camadas.
    Field("occupational_exam", "type", Owner.HR, Domain.HEALTH),
    Field("occupational_exam", "performed_on", Owner.HR, Domain.HEALTH),
    Field("occupational_exam", "valid_until", Owner.HR, Domain.HEALTH),
    Field("occupational_exam", "result", Owner.HR, Domain.HEALTH),
    # --- afastamentos e movimentações ---------------------------------------
    Field("leave_period", "category", Owner.HR),
    Field("leave_period", "start_date", Owner.HR),
    Field("leave_period", "end_date", Owner.HR),
    Field("workforce_movement", "type", Owner.HR),
    Field("workforce_movement", "event_date", Owner.HR),
    Field("workforce_movement", "unit_id", Owner.HR),
    Field("workforce_movement", "notes", Owner.HR),
    # --- acordos e parcelas --------------------------------------------------
    Field("financial_agreement", "type", Owner.HR, Domain.COMPENSATION),
    Field("financial_agreement", "description", Owner.HR, Domain.COMPENSATION),
    Field("financial_agreement", "total_amount", Owner.HR, Domain.COMPENSATION),
    Field("financial_agreement", "installment_count", Owner.HR, Domain.COMPENSATION),
    Field("financial_agreement", "agreement_date", Owner.HR, Domain.COMPENSATION),
    Field("financial_agreement", "status", Owner.HR, Domain.COMPENSATION),
    Field("agreement_installment", "number", Owner.HR, Domain.COMPENSATION),
    Field("agreement_installment", "period_year", Owner.HR, Domain.COMPENSATION),
    Field("agreement_installment", "period_month", Owner.HR, Domain.COMPENSATION),
    Field("agreement_installment", "amount", Owner.HR, Domain.COMPENSATION),
    Field("agreement_installment", "status", Owner.HR, Domain.COMPENSATION),
)


#: Os seis campos de benefício apontam para a MESMA casa, criada pela migration
#: `dp_benefit_catalog` (06/09/2026): `app.employee_benefit` guarda o valor por
#: pessoa e `app.benefit_type` o catálogo, com os oito códigos semeados que
#: cobrem VR, VT, cesta, planos, periculosidade e cargo de confiança.
_BENEFICIO: tuple[str, str] = ("employee_benefit", "benefit_type_id")
_BENEFICIO_TEM_CASA = (
    "app.employee_benefit existe desde 06/09/2026, com os oito tipos semeados em "
    "app.benefit_type, e a carga inicial ainda não escreve neles"
)


@dataclass(frozen=True)
class Lacuna:
    """Um campo que a SPEC §4 nomeia e a carga inicial recusa — com a razão AFERÍVEL.

    O `motivo` é o que o cliente lê na ata da implantação. As outras duas são a
    razão em forma de **afirmação sobre o schema**, e existem porque a razão em
    prosa envelhece calada: `scripts/95_teste_matriz_rh.py` confere cada uma
    contra o banco a cada `make db-test`.

    São dois tipos de lacuna, e confundi-los foi o que fez o texto mentir:

    - `ausente` — não há onde gravar. A afirmação é "esta coluna NÃO existe", e o
      guarda reprova no dia em que alguém a criar sem reescrever o texto.
    - `destino` — há onde gravar, e a carga inicial é que ainda não escreve.
      A afirmação é "esta tabela EXISTE", e o guarda reprova se ela sumir.

    ⚠️ Os dois recusam o campo do mesmo jeito: **o escopo da v1 não mudou aqui**.
    O que mudou é o texto parar de dizer que não há lugar quando há.
    """

    motivo: str
    ausente: tuple[str, str] | None = None
    destino: tuple[str, str] | None = None

    def __post_init__(self) -> None:
        if (self.ausente is None) == (self.destino is None):
            raise ValueError(f"{self.motivo}: declare exatamente um de `ausente` ou `destino`")


# ⛔ ESTES TEXTOS CHEGAM AO CLIENTE, e sete deles mentiram entre 06/09 e 12/09.
# As migrations do S1 do DP criaram casa para o que aqui se declarava sem casa —
# `level`, e os oito códigos de `app.benefit_type` — e o `carga_inicial.py`
# seguiu imprimindo "não há coluna" na ata da implantação. A causa foi o guarda:
# ele só recusava nome que estivesse em SEM_COLUNA *e* na matriz, e nunca
# perguntava se a lacuna ainda era verdade. Agora pergunta.
SEM_COLUNA: dict[str, Lacuna] = {
    "cbo": Lacuna("sem coluna em app.employee", ausente=("employee", "cbo")),
    "uniforme": Lacuna("sem coluna em app.employee", ausente=("employee", "uniforme")),
    "nivel": Lacuna(
        "app.employee_position.level existe desde 06/09/2026, e a carga inicial ainda "
        "não escreve nele",
        destino=("employee_position", "level"),
    ),
    "beneficios_vr": Lacuna(_BENEFICIO_TEM_CASA, destino=_BENEFICIO),
    "beneficios_planos": Lacuna(_BENEFICIO_TEM_CASA, destino=_BENEFICIO),
    "beneficios_cesta": Lacuna(_BENEFICIO_TEM_CASA, destino=_BENEFICIO),
    "beneficios_vt": Lacuna(_BENEFICIO_TEM_CASA, destino=_BENEFICIO),
    "periculosidade": Lacuna(_BENEFICIO_TEM_CASA, destino=_BENEFICIO),
    "cargo_de_confianca": Lacuna(_BENEFICIO_TEM_CASA, destino=_BENEFICIO),
    "unidade_de_atuacao": Lacuna(
        "app.workforce_movement passou a ter unidade de origem e destino em 07/09/2026; "
        "`unit_id` continua sendo a lotação, e a carga inicial não escreve o período",
        destino=("workforce_movement", "destination_unit_id"),
    ),
}

# Os valores que cada coluna aceita. Estão aqui, e não só no banco, porque o
# preview do import recusa a linha ANTES de gravar e o template alimenta o
# dropdown do Excel com eles — nenhum dos dois pode perguntar ao Postgres a cada
# linha. A cópia é conferida contra o `check` real em
# `scripts/95_teste_matriz_rh.py`, que roda no `make db-test`: duas listas só são
# uma lista enquanto alguém prova que são.
ENUMS: dict[tuple[str, str], frozenset[str]] = {
    ("employee", "status"): frozenset({"active", "afastado", "vacation", "desligado"}),
    ("employee", "employment_type"): frozenset(
        {"clt", "pj", "internship", "temporary", "apprentice", "contractor"}
    ),
    ("document", "status"): frozenset({"active", "vencido", "substituido", "removido"}),
    ("occupational_exam", "type"): frozenset(
        {"pre_employment", "periodic", "exit", "return_to_work_exam", "job_change"}
    ),
    ("occupational_exam", "result"): frozenset({"fit", "unfit", "fit_with_restriction"}),
    # ⛔ A quinta chegou com a migration `dp_leave_category` (06/09/2026), e ela
    #    é a única categoria que vale dinheiro: cesta e vale transporte a leem.
    #    `scripts/95_teste_matriz_rh.py` reprova se esta lista e o `check` do
    #    banco divergirem — foi ele que exigiu esta linha no mesmo PR.
    ("leave_period", "category"): frozenset(
        {"vacation", "leave_period", "leave_of_absence", "suspension", "unjustified_absence"}
    ),
    ("workforce_movement", "type"): frozenset(
        {"hire", "termination", "transfer", "promotion", "leave_period", "return_to_work"}
    ),
    ("financial_agreement", "type"): frozenset(
        {
            "installment_plan",
            "vehicle_damage",
            "equipment_damage",
            "advance",
            "loan",
            "benefit",
            "other",
        }
    ),
    ("financial_agreement", "status"): frozenset({"active", "settled", "cancelled", "suspended"}),
    ("agreement_installment", "status"): frozenset(
        {"pending", "processed", "cancelled", "renegotiated"}
    ),
}


_POR_CAMPO: dict[tuple[str, str], Field] = {(f.table, f.column): f for f in MATRIX}


def field(table: str, column: str) -> Field | None:
    """A linha da matriz, ou `None` para coluna que ela não governa."""
    return _POR_CAMPO.get((table, column))


def sync_columns(table: str) -> frozenset[str]:
    """As colunas que o RH não pode mudar — travadas no template, cinza na tela.

    Inclui as pendentes: enquanto ninguém confirmou de onde o dado vem, congelar
    é o lado seguro do erro.
    """
    return frozenset(f.column for f in MATRIX if f.table == table and f.owner is Owner.SYNC)


def editable_columns(table: str, *, domains: frozenset[Domain] = frozenset()) -> frozenset[str]:
    """O que este usuário pode escrever nesta tabela, dado o que ele enxerga.

    Coluna de domínio sensível só entra se o domínio estiver na mão — é a mesma
    decisão que a tela toma para mostrar ou esconder a aba, tomada uma vez só.
    """
    return frozenset(
        f.column
        for f in MATRIX
        if f.table == table and f.owner is Owner.HR and (f.domain is None or f.domain in domains)
    )


def versioned_columns(table: str) -> frozenset[str]:
    """O que se corrige revogando e criando outra vigência, nunca com um lápis."""
    return frozenset(f.column for f in MATRIX if f.table == table and f.versioned)


def tables() -> frozenset[str]:
    return frozenset(f.table for f in MATRIX)
