"""Pydantic schemas — source of truth of the API contract.

The frontend generates its table types from the database; everything the FastAPI
answers is declared here.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from operax.core.tenant import UserRole


class HealthResponse(BaseModel):
    """Liveness of the process. Public, says nothing about the environment."""

    status: Literal["ok"] = "ok"


class AuthenticatedUser(BaseModel):
    """Identity carried by a validated Supabase access token."""

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    email: str | None = None


class Identity(BaseModel):
    """Who the caller is, plus the tenant and role the backend resolved for them."""

    user_id: UUID
    email: str | None = None
    tenant_id: UUID
    role: UserRole


class EmployeeSummary(BaseModel):
    """Who the person is. No document of identity: that is `app.employee_pii`."""

    employee_id: UUID
    name: str
    registration_number: str | None = None
    cargo: str | None = None
    status: str
    hired_on: date | None = None
    employment_type: str | None = None
    unit_name: str | None = None
    company_name: str | None = None
    department_name: str | None = None
    manager_name: str | None = None


class DeviationIndicators(BaseModel):
    """The cut, for one person. `minutes_balance` is signed; `minutes_abs` is not."""

    events: int
    minutes_abs: int
    minutes_balance: int
    days_with_deviation: int
    pending_cycle: int


class DeviationTypeCount(BaseModel):
    type: str
    description: str
    events: int
    minutes_abs: int


class WorkdayRow(BaseModel):
    """One day of the roster, with the deviation found on it, if any.

    `confidence` comes from `app.expected_workday`: a 12x36 roster inferred from
    the source rarely reaches 100, and a day below the threshold is an
    unconfirmed schedule, not a finding.
    """

    reference_date: date
    day_type: str
    expected_entry: time | None = None
    expected_exit: time | None = None
    confidence: int
    deviation_type: str | None = None
    deviation_description: str | None = None
    direction: str | None = None
    minutes: int | None = None
    expected_time: time | None = None
    actual_time: time | None = None


class JustificationRow(BaseModel):
    reference_date: date
    text: str
    author_name: str | None = None
    source: str


class CompensationBand(BaseModel):
    """Sensitive: `compensation` domain."""

    effective_from: date
    effective_to: date | None = None
    salary: Decimal
    reason: str | None = None


class EmployeeDocument(BaseModel):
    """Sensitive: `pii` domain. The file itself lives in Storage, not here."""

    type_name: str
    issued_on: date | None = None
    valid_until: date | None = None
    status: str


class OccupationalExamRow(BaseModel):
    """Sensitive: `health` domain.

    Fitness and validity only. No diagnosis, no ICD, no description of a
    restriction — the table has no column for any of it (rule 10).
    """

    type: str
    performed_on: date
    valid_until: date | None = None
    result: str | None = None


class EmployeeDetail(BaseModel):
    """Individual consultation.

    The three sensitive blocks are absent — not empty, not masked — when the
    caller's role does not reach that domain. It is the same rule the design
    states for the screen: the role changes what exists, and there is no padlock
    to reason about.
    """

    employee: EmployeeSummary
    indicators: DeviationIndicators
    by_type: list[DeviationTypeCount]
    workdays: list[WorkdayRow]
    justifications: list[JustificationRow]
    compensation: list[CompensationBand] | None = None
    documents: list[EmployeeDocument] | None = None
    exams: list[OccupationalExamRow] | None = None


Severity = Literal["critical", "attention", "watch"]


class MonitorUnitRow(BaseModel):
    """Presence of one unit on the day being watched.

    `scheduled` counts people the roster expected to work, so a unit that is
    entirely off today reports zero and still appears — "nobody was scheduled"
    and "nothing was read" are different answers and the screen shows both.
    """

    unit_id: UUID | None = None
    unit_name: str | None = None
    scheduled: int
    with_indication: int
    clear: int
    off_roster: int


class MonitorRow(BaseModel):
    """One indication of the day, with the reading that produced it.

    `expected_time` and `actual_time` are what the engine compared. The screen
    shows both side by side and never states a conclusion: the official record
    of the workday stays in the time-clock system.
    """

    employee_id: UUID
    employee_name: str
    unit_id: UUID | None = None
    unit_name: str | None = None
    day_type: str | None = None
    expected_entry: time | None = None
    expected_exit: time | None = None
    confidence: int | None = None
    type: str
    type_description: str
    direction: str
    severity: Severity
    minutes: int
    expected_time: time | None = None
    actual_time: time | None = None
    detected_at: datetime


class DailyMonitor(BaseModel):
    """The situation of one day, by unit.

    What this can and cannot say is worth stating once. The product does not
    mirror punches into its own schema — they live in the source mirror, which
    is never exposed — so the monitor reports what the engine found, not who
    walked through the door. "Sem indício" therefore means "the last reading
    found nothing", never "present"; the age of that reading is on the screen
    beside it, permanently, because a manager reading a 08:40 picture at 09:05
    would otherwise conclude that nobody is late.
    """

    day: date
    scheduled: int
    with_indication: int
    clear: int
    off_roster: int
    units: list[MonitorUnitRow]
    rows: list[MonitorRow]
    truncated: bool = False


class ImportLineError(BaseModel):
    """Por que uma linha não entra. Texto em pt-BR, chega ao usuário como está."""

    code: str
    message: str
    column: str | None = None


class ImportLineReport(BaseModel):
    """O veredito de uma linha da planilha, pelo número que o Excel mostra."""

    line: int
    status: Literal["ok", "unchanged", "error"]
    errors: list[ImportLineError] = []


class ImportCounts(BaseModel):
    """`unchanged` é contado à parte de propósito.

    Somado a `ok` ele é `rows_ok` do banco, mas na tela as duas coisas são
    diferentes: "77 linhas já estavam assim" é uma informação, e escondê-la
    dentro de "80 linhas ok" faz o usuário procurar 80 alterações que não
    aconteceram.
    """

    total: int
    ok: int
    unchanged: int
    error: int


class ImportPreview(BaseModel):
    """O que o preview devolve. Nada foi gravado."""

    import_id: UUID
    type: str
    layout_version: str
    status: str
    counts: ImportCounts
    lines: list[ImportLineReport]


class ImportResult(ImportPreview):
    """Depois de confirmar.

    `partial` é derivado, não é estado guardado: `app.file_import.status` aceita
    `received`, `validating`, `validation_error`, `processed` e `discarded`, e o
    import confirmado com linha recusada é `processed` com `rows_error > 0` — a
    mesma semântica da folha. O rótulo "parcial" que a SPEC §3 descreve é leitura
    desses dois campos, e não um sexto valor no check.
    """

    applied: int
    partial: bool


class HrDueDate(BaseModel):
    """O prazo mais urgente de uma pessoa, seja ele qual for.

    Um só, e não uma lista: a coluna da tela mostra o que vence primeiro, e uma
    lista de cinco prazos numa célula deixa de ser lida. O que já venceu entra
    com a data no passado — vencido é justamente o que a lista existe para
    mostrar.
    """

    kind: Literal["aso", "documento", "experiencia"]
    label: str
    due_on: date


class HrEmployeeRow(BaseModel):
    """Uma linha da aba Colaboradores."""

    employee_id: UUID
    name: str
    registration_number: str | None = None
    hr_code: str | None = None
    cargo: str | None = None
    status: str
    hired_on: date | None = None
    unit_id: UUID | None = None
    unit_name: str | None = None
    due: HrDueDate | None = None


class HrEmployeeList(BaseModel):
    """A lista, e o que quem pediu pode fazer com ela.

    `can_write` vem do banco (`util.is_admin`), não do papel que o navegador
    acha que tem: é o que decide se a tela mostra botão de editar. Esconder o
    botão não é a segurança — a segurança é o backend recusar —, é não oferecer
    o que não vai funcionar.
    """

    rows: list[HrEmployeeRow]
    truncated: bool = False
    can_write: bool = False


class HrSyncField(BaseModel):
    """Um campo que o Secullum governa, com a coluna de onde ele vem.

    `mirror` é o que a tela cita ao dizer de onde o valor veio. `pending` marca
    os três campos que ninguém confirmou ainda — tratados como sync porque
    congelar é o lado seguro do erro, e rotulados como pendentes para a tela não
    afirmar uma origem que não foi checada.
    """

    column: str
    value: str | None = None
    mirror: str | None = None
    pending: bool = False


class HrIdentity(BaseModel):
    """O cabeçalho da pessoa na aba de RH."""

    employee_id: UUID
    name: str
    registration_number: str | None = None
    hr_code: str | None = None
    cargo: str | None = None
    status: str
    hired_on: date | None = None
    terminated_on: date | None = None
    employment_type: str | None = None
    unit_id: UUID | None = None
    unit_name: str | None = None
    company_name: str | None = None
    department_name: str | None = None
    manager_name: str | None = None


class PositionBand(BaseModel):
    """Uma vigência de posição. Corrigir é revogar e criar outra."""

    effective_from: date
    effective_to: date | None = None
    cargo: str
    unit_name: str | None = None


class HrPii(BaseModel):
    """Sensível: domínio `pii`. Quase tudo aqui é leitura — vem do espelho."""

    cpf: str | None = None
    rg: str | None = None
    pis: str | None = None
    ctps: str | None = None
    birth_date: date | None = None
    mother_name: str | None = None
    father_name: str | None = None
    phone: str | None = None
    personal_email: str | None = None


class HrLeave(BaseModel):
    """Rótulo neutro por decisão de produto: o motivo é dado de saúde e não é
    capturado em lugar nenhum."""

    category: str
    start_date: date
    end_date: date | None = None
    source: str


class HrMovement(BaseModel):
    type: str
    event_date: date
    notes: str | None = None
    unit_name: str | None = None


class HrAgreement(BaseModel):
    """Sensível: domínio `compensation`."""

    id: UUID
    type: str
    description: str | None = None
    total_amount: Decimal
    installment_count: int
    agreement_date: date
    status: str
    pending_installments: int = 0


class HrEmployeeDetail(BaseModel):
    """Uma pessoa em abas por domínio.

    Os cinco blocos sensíveis chegam `null` — ausentes, não vazios — quando o
    papel de quem pergunta não alcança o domínio. É essa distinção que faz a aba
    **não existir no DOM** em vez de aparecer desabilitada: quem não pode ver
    salário não fica sabendo que existe salário.
    """

    employee: HrIdentity
    sync_fields: list[HrSyncField]
    editable_fields: list[str]
    #: Os valores que cada campo editável aceita, do `check` do próprio banco.
    #: Viajam com a resposta para que a tela não mantenha uma segunda cópia do
    #: catálogo — uma cópia que envelheceria oferecendo o que o banco recusa.
    enums: dict[str, list[str]] = {}
    can_write: bool
    positions: list[PositionBand]
    leaves: list[HrLeave]
    movements: list[HrMovement]
    pii: HrPii | None = None
    documents: list[EmployeeDocument] | None = None
    exams: list[OccupationalExamRow] | None = None
    compensation: list[CompensationBand] | None = None
    agreements: list[HrAgreement] | None = None


class EmployeePatch(BaseModel):
    """O que o formulário de cadastro pode mudar.

    `extra="forbid"` de propósito: um campo que a matriz diz ser do sync chegando
    aqui é um cliente pedindo para sobrescrever a origem, e a resposta certa é
    recusar o pedido inteiro em vez de ignorar a chave em silêncio.
    """

    model_config = ConfigDict(extra="forbid")

    hr_code: str | None = None
    employment_type: str | None = None
    ctps: str | None = None


class NewCompensation(BaseModel):
    """Uma vigência nova de salário. Não existe editar a faixa vigente."""

    model_config = ConfigDict(extra="forbid")

    effective_from: date
    salary: Decimal
    reason: str | None = None


class NewPosition(BaseModel):
    """Uma vigência nova de cargo."""

    model_config = ConfigDict(extra="forbid")

    effective_from: date
    cargo: str
    unit_id: UUID | None = None


class AssistantQuestion(BaseModel):
    """A pergunta que entra no assistente.

    O teto de caracteres não é higiene de formulário: a pergunta viaja para um
    provider pago por token, e um campo de texto sem limite é uma conta sem
    limite. `extra="forbid"` pelo motivo de sempre — um parâmetro que o servidor
    não conhece chegando aqui é o cliente pedindo algo que ninguém desenhou.
    """

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000)
    #: Id do modelo, validado contra a allowlist de `operax.agente.agente`.
    #: `None` = o padrão do provider configurado.
    model: str | None = None
