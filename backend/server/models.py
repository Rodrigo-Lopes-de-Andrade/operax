"""Pydantic schemas — source of truth of the API contract.

The frontend generates its table types from the database; everything the FastAPI
answers is declared here.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class JustificationVerdict(BaseModel):
    """O veredito de quem explica um desvio.

    `status` é fechado em dois valores porque o banco fecha nos mesmos desde a
    migration 23 — recusar aqui devolve mensagem em vez de 500. Não existe
    "pendente" como valor: pendente é a AUSÊNCIA de linha aceita, e é assim que
    `fn_pending_justification` a calcula. Um terceiro estado gravado faria a
    mesma pergunta ter duas respostas.

    `text` é obrigatório nos dois vereditos, e no rejeitado também: uma rejeição
    sem motivo é a decisão sem a parte que a pessoa afetada precisa ler.
    """

    text: str = Field(min_length=3, max_length=2000)
    status: Literal["accepted", "rejected"]


class JustificationApplied(BaseModel):
    justification_id: UUID
    deviation_event_id: UUID
    employee_name: str
    reference_date: date
    status: str


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


class PunchRow(BaseModel):
    """One column of one day, exactly as the source transposed it.

    The source records a day as a row of up to five `Entrada`/`Saida` pairs, and
    ingestion turns each column into a line here. `column_index` is that
    position, kept because it is what pairs an entry with its exit — pairing by
    time order would invent a pair whenever one side is missing.

    A line with no `punched_at` is not noise. Either `status_label` explains it
    ("Férias", "Atestado") or `expected_time` says a punch was expected there and
    never arrived, which is the line that most often needs a person.

    `disregarded` is a punch somebody discarded at the source. It is shown, and
    it does not count: the engine ignores it, and a screen that counted it would
    contradict the indication beside it.
    """

    reference_date: date
    column_type: str
    column_index: int
    punched_at: time | None = None
    status_label: str | None = None
    expected_time: time | None = None
    disregarded: bool


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
    #: As marcações do período, do jeito que chegaram da origem. Vazia também
    #: quando a leitura nunca aconteceu — a tela distingue as duas pela data da
    #: última leitura, não por esta lista.
    punches: list[PunchRow]
    punches_read_at: datetime | None = None
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

    `active` is the headcount, and the six counts below it partition exactly:
    `scheduled + on_vacation + on_leave + day_off + unrostered +
    exception_tracking = active`. That identity is the reason `unrostered`
    exists — without it the difference between the headcount and the roster is a
    number nobody can see.

    `with_punch + without_punch = scheduled`, over the same rows as
    `with_indication + clear`. Two partitions of one population, answering two
    different questions: what the engine found, and what the last reading of the
    source contains.
    """

    unit_id: UUID | None = None
    unit_name: str | None = None
    active: int
    scheduled: int
    with_indication: int
    clear: int
    #: Escalados com ao menos uma marcação até a última leitura. Nunca "presentes":
    #: ver `DailyMonitor`.
    with_punch: int
    without_punch: int
    on_vacation: int
    on_leave: int
    day_off: int
    #: Ativo e sem jornada prevista para o dia, sem ninguém ter decidido isso —
    #: ou seja, falha de cobertura do motor. Desde a migration 26 o desenho tem
    #: contagem própria: ver `exception_tracking`. Enquanto os dois dividiam um
    #: número, uma falha de cobertura se escondia dentro dele parecendo decisão.
    unrostered: int
    off_roster: int
    #: Fora do motor por decisão — "ponto por exceção", supervisão. Não tem
    #: jornada esperada porque ninguém lhe deve uma.
    exception_tracking: int = 0


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

    What this can and cannot say is worth stating once. `with_indication` and
    `clear` report what the **engine** found, so "sem indício" means "the last
    detection found nothing", never "present"; the age of that reading is on the
    screen beside it, permanently, because a manager reading a 08:40 picture at
    09:05 would otherwise conclude that nobody is late.

    `with_punch` and `without_punch` are the punches of the day, read from
    `app.batida_marcacao` through `operax.motor.marcacao`. They are **not**
    "presentes" and "ausentes", and the difference is not pedantry:

    - the count is true as of `punches_read_at`, never as of now. Somebody who
      clocked in one minute after that reading is in `without_punch`, and the
      screen must carry the instant beside the number or it states a falsehood
      about a named person;
    - a punch proves a record, not a body. Declaring presence from it is
      decision A12 of the audit, open with the owner, and it is a product
      decision rather than a query.

    `punches_read_at` is null when there is no reading to speak of — the tenant
    never completed one, or the mirror is not in this database at all. **The two
    counts are then meaningless and must not be shown.** They are not zeroed:
    zeroing them would break `with_punch + without_punch = scheduled`, and an
    identity that holds only sometimes is worse than one number to check. A
    consumer gates on `punches_read_at`, which is why it is here and not looked
    up separately.
    """

    day: date
    active: int
    scheduled: int
    with_indication: int
    clear: int
    with_punch: int
    without_punch: int
    #: Instante da última leitura de `Batida` concluída. Null = nunca houve
    #: leitura, e aí os dois números acima não afirmam nada.
    punches_read_at: datetime | None = None
    on_vacation: int
    on_leave: int
    day_off: int
    unrostered: int
    off_roster: int
    #: Ver `MonitorUnitRow.exception_tracking`: quem foi tirado do motor por
    #: decisão, separado de quem o motor deixou de cobrir.
    exception_tracking: int = 0
    units: list[MonitorUnitRow]
    rows: list[MonitorRow]
    truncated: bool = False


class UnitOption(BaseModel):
    """Uma unidade que pode receber um departamento do espelho."""

    unit_id: UUID
    code: str
    name: str
    company_id: UUID
    company_name: str


class UnitSuggestion(BaseModel):
    """Um palpite, com o tamanho do palpite ao lado.

    `confidence` é semelhança de nome, e nada mais. Ela não é gravada em lugar
    nenhum: existe para ordenar o trabalho de quem cura e para dar um limiar ao
    lote. O que vira dado é a escolha da pessoa.
    """

    unit_id: UUID
    unit_name: str
    confidence: int


class UnitMappingRow(BaseModel):
    """Um departamento do espelho, o mapa dele e o peso de não ter mapa.

    Três estados, e a diferença entre os dois últimos é o ponto da tela:

    - **não mapeado** — `unit_id` nulo. Quem está nele foi promovido sem unidade
      e some de todo recorte por unidade;
    - **provisório** — mapeado com `validated_at` nulo. Alguém ou alguma carga
      escreveu o mapa e ninguém confirmou;
    - **validado** — uma pessoa apertou o botão, e está registrado quem e quando.
    """

    secullum_department_id: int
    department: str
    company_id: UUID
    company_name: str
    #: Ativos lotados neste departamento.
    employees: int
    #: Ativos daqui que estão sem unidade — é o que a curadoria resolve.
    unmapped: int
    unit_id: UUID | None = None
    unit_name: str | None = None
    validated_at: datetime | None = None
    suggestion: UnitSuggestion | None = None


class UnitMappingScreen(BaseModel):
    """A fila de curadoria inteira, com a conta que ela fecha.

    `validated` **exclui o provisório de propósito**: uma pessoa cuja unidade veio
    de um mapa que ninguém confirmou está alocada e não está curada. Somar as
    duas faria a barra chegar a 100% com metade do trabalho por fazer, que é o
    modo mais eficiente de encerrar uma curadoria pela metade.
    """

    rows: list[UnitMappingRow]
    units: list[UnitOption]
    active: int
    validated: int
    provisional: int
    without_unit: int


class UnitMappingPair(BaseModel):
    secullum_department_id: int
    unit_id: UUID


class UnitMappingRequest(BaseModel):
    """O que a tela manda de volta: pares departamento → unidade.

    Uma lista, e não um par, porque o lote é o caso principal: "aplicar as
    sugestões acima de N%" é uma decisão só, tomada uma vez, e mandá-la como
    quarenta requisições faria metade dela sobreviver a uma queda de rede.
    """

    mappings: list[UnitMappingPair] = Field(min_length=1, max_length=500)


class UnitMappingApplied(BaseModel):
    """Quantos mapas foram validados, e quanta gente andou por causa disso.

    `employees_allocated` conta só quem **estava sem unidade**. Curar o mapa não
    move quem já está alocado: alocação existente é trabalho humano, e a mesma
    regra vale na promoção (`coalesce(excluded.unit_id, app.employee.unit_id)`).
    """

    validated: int
    employees_allocated: int


class RotationRow(BaseModel):
    """Um horário do espelho que não declara expediente nenhum, e o que se sabe dele.

    Três estados, iguais aos do mapa de unidade:

    - **sem rotação** — `cycle_length_days` nulo. Quem está aqui materializa
      jornada com confiança 0: não gera alerta, e também não é medido;
    - **provisória** — rotação escrita com `validated_at` nulo. `jornada.py` não
      a lê, de propósito;
    - **validada** — alguém carimbou, e a jornada passa a sair daqui com
      confiança 100.

    `observed_days` são os dias em que este horário de fato bateu ponto. Ele
    existe para o curador conferir a âncora contra a realidade — e não para o
    sistema deduzi-la: escala derivada das batidas encaixa sempre, e escala que
    encaixa sempre nunca acusa falta.
    """

    secullum_schedule_id: int
    schedule: str
    #: Ativos neste horário — é o peso que ordena a fila.
    employees: int
    #: Quantos desses já estão fora do motor por decisão. Um horário em branco
    #: tem duas respostas possíveis, e esta é a outra: não falta rotação, não há
    #: jornada devida.
    out_of_engine: int = 0
    cycle_length_days: int | None = None
    anchor_date: date | None = None
    expected_entry: time | None = None
    expected_exit: time | None = None
    expected_break_minutes: int | None = None
    workload_minutes: int | None = None
    tolerance_extra_minutes: int | None = None
    tolerance_absence_minutes: int | None = None
    validated_at: datetime | None = None
    observed_days: list[date] = Field(default_factory=list)


class RotationScreen(BaseModel):
    """A fila de rotação inteira, com a conta que ela fecha.

    `validated` exclui o provisório pelo mesmo motivo de `UnitMappingScreen`, e
    aqui a consequência é mais dura: rotação provisória não é lida pelo motor,
    então contá-la como pronta esconderia gente que continua fora da medição.
    """

    rows: list[RotationRow]
    on_blank_schedule: int
    validated: int
    provisional: int


class RotationRequest(BaseModel):
    """A rotação que o curador declara para um horário.

    `expected_exit` pode ser MENOR que `expected_entry`: é assim que um turno
    noturno se escreve, do mesmo jeito que o `HorarioDia` do Secullum o escreve.
    Quem trata a virada é `regras.py`.

    O ciclo começa em 2 porque 1 é "trabalha todo dia", que é semana fixa e não
    rotação — e porque o banco recusa, e recusar aqui devolve mensagem em vez de
    500.
    """

    secullum_schedule_id: int
    cycle_length_days: int = Field(ge=2, le=31)
    #: Um dia em que este ciclo TRABALHOU. É o que o curador confere contra
    #: `observed_days`.
    anchor_date: date
    expected_entry: time
    expected_exit: time
    expected_break_minutes: int | None = Field(default=None, ge=0)
    workload_minutes: int = Field(gt=0)
    tolerance_extra_minutes: int = Field(default=0, ge=0)
    tolerance_absence_minutes: int = Field(default=0, ge=0)


class ExceptionTrackingRequest(BaseModel):
    """Tirar do motor, ou devolver a ele, todo mundo de um horário.

    O alvo é o horário porque é assim que quem cura pensa — "essa turma toda é
    supervisão" —, e o fato é gravado em cada pessoa porque estar fora do motor
    é do papel: mover alguém de horário não pode ligar nem desligar a medição.
    """

    secullum_schedule_id: int
    exception_tracking: bool


class ExceptionTrackingApplied(BaseModel):
    """Quantas pessoas mudaram de lado. Zero é resposta válida: já estavam."""

    secullum_schedule_id: int
    employees_changed: int


class RotationApplied(BaseModel):
    """O horário carimbado, e quanta gente sai da confiança 0 por causa dele."""

    secullum_schedule_id: int
    employees_covered: int


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


class PayrollLineReport(BaseModel):
    """O veredito de uma linha da folha.

    `warnings` existe aqui e não no relatório do RH porque a folha tem pendência
    que **não** barra a linha: código de evento sem categoria entra, conta no
    total, e só não aparece nos indicadores por categoria. Misturar isso com
    `errors` faria a tela oferecer "corrija antes de confirmar" para algo que não
    é do usuário corrigir — é da curadoria com a contabilidade.
    """

    line: int
    errors: list[ImportLineError] = []
    warnings: list[ImportLineError] = []


class PayrollCounts(BaseModel):
    """Sem `unchanged`: a competência é substituída inteira, não comparada linha a linha."""

    total: int
    ok: int
    error: int


class PayrollReplacement(BaseModel):
    """O que já está gravado na competência e que a confirmação substitui."""

    entries: int
    imported_at: datetime | None = None


class PayrollPreview(BaseModel):
    """O que o arquivo faria com a competência. Nada foi gravado."""

    import_id: UUID
    period: str
    layout_version: str
    status: str
    counts: PayrollCounts
    #: Códigos de evento sem categoria, uma vez cada — o insumo da curadoria.
    unmapped_codes: list[str] = []
    lines: list[PayrollLineReport] = []
    #: `None` quando a competência ainda não tem nada gravado.
    replaces: PayrollReplacement | None = None


class PayrollResult(PayrollPreview):
    """Depois de confirmar.

    Não herda `partial` do import de RH de propósito: folha parcial não existe.
    Arquivo com uma linha em erro não é confirmável, porque a soma da competência
    deixaria de bater com o holerite e ninguém veria — a mesma razão pela qual um
    valor ilegível vira erro em vez de zero.
    """

    applied: int
    replaced: int


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


class HrPhotoSuperseded(BaseModel):
    """A foto enviada que a origem substituiu. Metadado, nunca bytes."""

    uploaded_at: datetime
    uploaded_by_name: str | None = None


class HrPhoto(BaseModel):
    """Se há foto, e de quando ela é. Sem bytes, por desenho.

    ⚠️ **Três estados, não dois** (§6 da decisão): um vazio sem explicação numa
    tela de identificação parece defeito. `ausente` é a origem dizendo que não
    há; `pendente` é a fila ainda não ter chegado nesta pessoa.

    `synced_at` viaja porque **idade de rosto é dado de tela**, pela mesma
    disciplina de idade do dado do resto do produto: rosto de dois anos numa
    ficha de identificação é pior que rosto nenhum, e só a data revela.
    """

    state: Literal["ausente", "pendente", "disponivel"]
    #: De onde vem o rosto exibido. A ORIGEM VENCE (§4-ter): o espelho é o
    #: registro de identidade, e a enviada é tapa-buraco de uma lacuna dele.
    origin: Literal["secullum", "manual"] | None = None
    synced_at: datetime | None = None
    uploaded_at: datetime | None = None
    uploaded_by_name: str | None = None
    #: A foto enviada que a origem substituiu — **nunca apagada**. É o que faz a
    #: ficha dizer "substituiu a foto enviada em DD/MM por [autor]", porque troca
    #: silenciosa do rosto que o DP escolheu é o erro que a revisão apontou.
    superseded: HrPhotoSuperseded | None = None
    #: A tela só oferece envio onde a origem declara não ter, para que as duas
    #: fontes não se sobreponham por construção.
    can_upload: bool = False


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
    #: Metadado da foto — **nunca os bytes**. `null` quando o papel não alcança
    #: `pii`, pela mesma regra dos outros blocos sensíveis: a aba não existe no
    #: DOM em vez de aparecer vazia. A imagem sai por
    #: `GET /rh/employees/{id}/foto`, resposta binária, nunca em JSON e nunca em
    #: lista — ver docs/DECISAO-FOTO-DO-COLABORADOR.md §5.
    photo: HrPhoto | None = None
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


class BankAccountPatch(BaseModel):
    """A conta bancária que o formulário grava — inteira, e nunca em pedaços.

    Não há campo opcional aqui de propósito, apesar do verbo ser `PATCH`: meia
    conta gravada é uma remessa que paga a pessoa errada. Ou o formulário manda a
    conta que vale, ou não manda nada.

    `account_type` repete a lista do `check` de `app.employee_bank_account`
    porque um `Literal` não se lê de tabela — e é a única cópia: o banco continua
    sendo quem recusa por último.
    """

    # `str_strip_whitespace` antes do `min_length`: sem ele um campo com um
    # espaço passa na validação e vira um número de conta que é um espaço.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    bank_code: str = Field(min_length=1, max_length=10)
    branch: str = Field(min_length=1, max_length=20)
    account: str = Field(min_length=1, max_length=30)
    account_type: Literal["checking", "savings", "salary", "payment"] = "checking"
    #: CPF/CNPJ do titular quando a conta não é do colaborador.
    holder_document: str | None = Field(default=None, max_length=20)


class BankAccountMasked(BaseModel):
    """A conta como ela sai da API — e não existe forma de ela sair inteira.

    Regra 10 do `PRD-DP.md`: o número completo nunca chega ao navegador, nem para
    exibir. Não há campo `account` neste schema, e é isso que faz a regra valer
    mesmo numa rota escrita por quem nunca leu o PRD. Quem monta a remessa lê o
    número em `operax/dp/banking.py` e escreve em bytes.
    """

    employee_id: UUID
    bank_code: str
    branch: str
    #: `•••• 8723`. A cauda basta para o DP conferir; o resto não é da tela.
    account_masked: str
    account_type: str
    holder_document: str | None = None
    updated_at: datetime


class WorkPostCreate(BaseModel):
    """Um posto novo no Quadro. `active` não está aqui: posto nasce ativo.

    O código é único por `(tenant, unidade)` no banco — a frase da tela de VT
    ("a escala é obtida do Quadro de Postos: código do posto + unidade") virando
    constraint. O 409 que a rota devolve é essa constraint traduzida.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    unit_id: UUID
    #: "7703" no legado. O teto é folga sobre o que a origem usa; a coluna é
    #: `text` e quem recusa por último continua sendo o banco.
    code: str = Field(min_length=1, max_length=40)
    name: str | None = Field(default=None, max_length=120)


class WorkPostPatch(BaseModel):
    """O que muda num posto: o rótulo e a operação. Nunca o código, nunca a unidade.

    ⛔ **Não há como apagar.** Posto sai de operação com `active = false`, porque
    o ciclo de VT do mês passado aponta para ele — regra 6 do projeto estendida
    ao cadastro. Mudar o código quebraria o histórico do mesmo jeito, e por isso
    ele também não está aqui.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    active: bool | None = None

    @model_validator(mode="after")
    def _algo_a_mudar(self) -> WorkPostPatch:
        # Corpo vazio é 422, não 200: um `PATCH` que não pede nada e responde
        # sucesso faz a tela acreditar que gravou.
        if self.name is None and self.active is None:
            raise ValueError("informe `name` ou `active` — não há o que alterar")
        return self


class WorkPostRow(BaseModel):
    """Um posto, com o nome da unidade já resolvido para a tela."""

    id: UUID
    unit_id: UUID
    unit_name: str
    code: str
    name: str | None = None
    active: bool
    created_at: datetime


class WorkPostList(BaseModel):
    """O Quadro das unidades que quem pergunta enxerga — ativos e inativos.

    `can_write` é cortesia para esconder o botão, não segurança: as rotas de
    escrita recusam por conta própria.
    """

    rows: list[WorkPostRow]
    can_write: bool


class BenefitTypeRow(BaseModel):
    """Uma verba do catálogo. `composes_base` é a definição do KPI, não um rótulo."""

    code: str
    name: str
    #: Entra na folha salarial base. Mudar isto muda o número da tela.
    composes_base: bool
    #: `fixed_amount` | `salary_rate`. O segundo é o mecanismo do triênio.
    calculation: str
    domain: str
    active: bool


class BenefitPlanRow(BaseModel):
    """A vigência de plano que valia na data consultada."""

    id: UUID
    benefit_type_code: str
    code: str
    provider: str
    name: str
    amount: Decimal
    effective_from: date
    effective_to: date | None = None
    reason: str | None = None


class TransportFareRow(BaseModel):
    """A vigência de tarifa que valia na data consultada.

    `kind` faz parte da identidade: a unitária e a ida-e-volta sobem separadas,
    porque integração e desconto de linha quebram a conta de "duas vezes".
    """

    id: UUID
    code: str
    name: str
    kind: str
    amount: Decimal
    effective_from: date
    effective_to: date | None = None
    reason: str | None = None


class BenefitCatalog(BaseModel):
    """O catálogo **numa data**, e nunca "o catálogo".

    Preço tem vigência: perguntar sem data é perguntar por hoje e receber a
    resposta certa por acidente no dia seguinte ao reajuste.
    """

    on: date
    types: list[BenefitTypeRow]
    plans: list[BenefitPlanRow]
    fares: list[TransportFareRow]
    can_write: bool


class BenefitAdjustment(BaseModel):
    """Um reajuste: **nova vigência**, nunca edição do valor publicado.

    Não existe campo para o valor antigo, para a data de fim da faixa que sai ou
    para o id da linha a alterar — e a ausência é o desenho. O que se envia é
    "desde, valor, motivo", que é exatamente a tela de Reajuste do legado; o
    resto o backend deriva da faixa aberta.

    `kind` só existe para tarifa, e é obrigatório lá: sem ele o reajuste da
    unitária subiria a ida-e-volta junto.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target: Literal["plan", "fare"]
    code: str = Field(min_length=1, max_length=60)
    kind: Literal["single", "round_trip"] | None = None
    effective_from: date
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _kind_combina_com_o_alvo(self) -> BenefitAdjustment:
        if self.target == "fare" and self.kind is None:
            raise ValueError("tarifa exige `kind`: single ou round_trip")
        if self.target == "plan" and self.kind is not None:
            raise ValueError("plano não tem `kind`")
        return self


class AdjustedBandRow(BaseModel):
    """A vigência que nasceu, e a que ela fechou.

    As duas voltam juntas porque é a frase que o gestor confere na tela:
    "R$ 4,80 até 31/08, R$ 5,10 a partir de 01/09". `previous_amount` sai da
    linha antiga **depois** do fechamento — é a prova de que ela manteve o valor
    que valeu.
    """

    target: Literal["plan", "fare"]
    id: UUID
    code: str
    kind: str | None = None
    name: str
    amount: Decimal
    effective_from: date
    reason: str | None = None
    previous_id: UUID
    previous_amount: Decimal
    previous_effective_to: date


class BenefitPlanCreate(BaseModel):
    """A PRIMEIRA vigência de um plano. Reajuste é outra rota, e de propósito.

    Não há `effective_to` aqui: uma vigência nasce aberta, e a data de fim é
    escrita pelo reajuste que a substitui. Um campo de fim no formulário de
    criação convidaria a cadastrar um preço que já nasce vencido.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    #: `health_plan`, `dental_plan`… a verba do catálogo a que este plano pertence.
    benefit_type_code: str = Field(min_length=1, max_length=60)
    code: str = Field(min_length=1, max_length=60)
    provider: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    effective_from: date
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    reason: str | None = Field(default=None, max_length=200)


class TransportFareCreate(BaseModel):
    """A PRIMEIRA vigência de uma tarifa. `kind` faz parte da identidade.

    A unitária e a ida-e-volta entram em duas chamadas: `round_trip` não é sempre
    duas vezes `single`, e deduzir uma da outra inventaria o preço que o apurador
    de vale transporte multiplica por dias líquidos.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["single", "round_trip"]
    effective_from: date
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    reason: str | None = Field(default=None, max_length=200)


class NewBandRow(BaseModel):
    """A vigência que nasceu. Sem `previous_*`: não havia nada antes dela."""

    target: Literal["plan", "fare"]
    id: UUID
    code: str
    kind: str | None = None
    name: str
    amount: Decimal
    effective_from: date
    reason: str | None = None


class CycleRequest(BaseModel):
    """Que competência apurar. Três campos, e a janela é derivada deles.

    ⛔ Não há `window_start`/`window_end` no pedido, e a ausência é o desenho: a
    janela 21 → 20 é regra do cliente transcrita da tela, não parâmetro. Aceitá-la
    do formulário deixaria alguém apurar setembro com a janela de agosto e o
    número sairia plausível.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["food_basket", "transport_voucher"]
    period_year: int = Field(ge=2000, le=2100)
    period_month: int = Field(ge=1, le=12)


class CycleEntitlementRow(BaseModel):
    """A linha por pessoa, como a tela a mostra.

    ⛔ NÃO HÁ CAMPO DE CONTA BANCÁRIA, e é isso que faz a regra 10 do `PRD-DP.md`
    valer nesta rota. O número existe só dentro do arquivo de remessa, em `bytes`.
    """

    employee_id: UUID
    name: str
    registration_number: str | None = None
    unit_id: UUID | None = None
    unit_name: str | None = None
    entitled: bool
    #: Qual das duas causas tirou o direito. A pessoa vai perguntar.
    reason: str | None = None
    #: As quatro seguintes ficam nulas para cesta: ela não tem janela nem dias.
    days_base: int | None = None
    absences_prior: int | None = None
    net_days: int | None = None
    unit_amount: Decimal | None = None
    round_trip_amount: Decimal | None = None
    total_amount: Decimal | None = None


class CycleView(BaseModel):
    """A competência apurada — em rascunho ou congelada.

    `status` viaja porque a tela precisa dele para decidir se ainda dá para
    reapurar: `draft` reapura, `generated` não, e a diferença é a regra 9 do PRD.
    """

    id: UUID | None = None
    kind: Literal["food_basket", "transport_voucher"]
    period_year: int
    period_month: int
    window_start: date
    window_end: date
    #: Dias com expediente na janela. Cabeçalho; não entra em nenhuma conta.
    business_days: int | None = None
    status: str
    entitled_count: int
    denied_count: int
    total_amount: Decimal
    #: ⛔ O EIXO DA REMESSA, E ELE NÃO É `can_write`.
    #: A SPEC §3 manda o botão de remessa aparecer só para quem tem o domínio
    #: `banking` — regra 5 do projeto: quem não pode, não vê; não vê desabilitado.
    #: Sem este campo a tela não tem como saber, e deduzir de lista de papéis no
    #: frontend seria a matriz de domínios escrita duas vezes — ela muda por
    #: `UPDATE`, e a cópia divergiria sem ninguém notar.
    #:
    #: ⚠️ `banking` E NÃO `is_admin`, e a assimetria é decisão do S3:
    #: `accounting` confere a remessa e não apura competência nenhuma. Um campo
    #: alimentado por `is_admin` esconderia o botão exatamente de quem existe
    #: para conferi-lo.
    can_export_remittance: bool
    rows: list[CycleEntitlementRow]


class CycleSummary(BaseModel):
    """A competência na lista — sem as linhas.

    ⛔ Não há `rows` aqui de propósito: vinte e quatro competências de 176
    pessoas seriam 4.200 linhas numa tela que só precisa saber qual mês está
    pendente. Quem quer a pessoa abre a competência.
    """

    id: UUID
    kind: Literal["food_basket", "transport_voucher"]
    period_year: int
    period_month: int
    window_start: date
    window_end: date
    business_days: int | None = None
    status: str
    entitled_count: int
    denied_count: int
    total_amount: Decimal


class CycleList(BaseModel):
    """As competências que o tenant já apurou, da mais recente para a mais antiga.

    `can_export_remittance` viaja no container e não em cada linha porque ele é
    propriedade de **quem perguntou**, não da competência — do mesmo jeito que
    `can_write` em `WorkPostList` e `BenefitCatalog`.
    """

    rows: list[CycleSummary]
    can_export_remittance: bool


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
