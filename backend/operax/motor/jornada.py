"""Expected workday — what each person was supposed to do on each day.

The detector compares punches against an expectation. This is where the
expectation comes from, and its whole job is to be honest about how much it
knows: `app.expected_workday.confidence` gates the detector, and a line below 80
must never raise an alert.

WHAT THE SOURCE CAN AND CANNOT SAY, MEASURED
`secullum."HorarioDia"` is keyed by `(horario_id, "DiaSemana")` with `DiaSemana`
in 0..6. It is a fixed seven-day week: no cycle index, no start date. A 12x36 is
a 48-hour cycle, and seven days is not a multiple of two, so the pattern never
repeats weekly and cannot be written down there.

Secullum's own workaround is visible in the mirrored data: rotations arrive as
pairs of schedules named "Par"/"Ímpar" whose `HorarioDia` is **entirely empty** —
seven rows, all `sem_expediente`. The rotation lives outside the payload, and
nothing mirrored carries it: the three alternate schedule columns on
`Funcionario` are null for every employee, in both classes.

Measured against production on 2026-08-24, over 11–24/08:

  • 66 of 79 active employees are on a fixed week, and it is trustworthy — 4 of
    546 worked days (0.7%) fell on a day the schedule called off.
  • 13 are on a schedule with no expediente at all. They split in two: 7 people
    across two units on real 12x36 shifts, and 6 in administration whose schedule
    is blank by design (the sibling schedules are literally named "Ponto por
    exceção" and "Marcação Supervisor").

⚠️ THAT MEASUREMENT ASKED THE WRONG QUESTION, AND 2026-08-26 FOUND OUT
"Trustworthy" above means the schedule DECLARES the weekday, which is coverage.
It says nothing about whether what it declares describes the shift. Six schedules
in production declare `Entrada1` after their own last `Saida` — 19:00 to 05:00 —
and four active people are on them, on a fixed week, scoring 100 here. They were
inside the 66.

Read as `time`, that exit lands fourteen hours before the entry, and the detector
was handed a whole night backwards. Over 11–26/08, 61 of 682 worked days (8.9%)
cross midnight and 39 of them belong to those four. The 12x36 people are the
OTHER half, and they were never the ones raising alerts: confidence 0 already
stops them at the gate.

The fix is arithmetic, not data — `regras.py` normalises both sides onto a
continuous timeline, and the source already carries everything it needs. This
module's part is only the break: see `break_minutes` below.

WHERE THE ROTATION COMES FROM, SINCE THE MIRROR CANNOT HOLD IT
`app.schedule_rotation_map` (migration 25) is the curated bridge for the shifts
`HorarioDia` cannot express: an anchor date plus a cycle length, keyed by the
mirror's schedule, because the rotation belongs to the SCHEDULE and
`Funcionario.horario_id` already says who is on it. A day is worked when
`(reference_date - anchor_date) mod cycle` is zero.

Two rules live in the join above and not in a comment somewhere:

  • it is read only where the schedule declares NO expediente. Where the mirror
    speaks, the mirror is the record, and curation fills silence rather than
    contradicting it;
  • it is read only when `validated_at` is filled. A provisional rotation would
    arrive at confidence 100 and become an alert against somebody — the same
    reason the unit curation keeps "provisório" in its own band.

A curated rotation is the first thing that lets this module say `day_off` about
a 12x36. Without it a blank schedule produces `work` with no hours, because a
day off and not knowing look identical and only one of them may be claimed.

So this module does not guess. A schedule that declares no expediente produces
`confidence = 0`, and the coverage report groups those rows **by schedule
description** so a person can see which of the two problems they are looking at.
Deciding that supervisors leave the engine's scope was a product call, taken on
2026-08-26 and written down as `app.employee.exception_tracking` (migration 26).
Nobody here reads a schedule name to guess it: the column is set by a person,
and this module only refuses to materialise a day for whoever carries it. A
regex over schedule names would have taken the same decision in silence.

CONFIDENCE IS A LADDER OF THREE, NOT A CURVE
Inventing intermediate values would be false precision over a source that is
either right or absent.

  100  the weekday is declared, either as a shift or as a weekly day off; or the
       source declares a leave, which is a fact and not an inference.
   50  a shift is declared but carries no entry time — we know the day is worked,
       not when. Below the gate, so it cannot raise an alert.
    0  the schedule says nothing about this weekday.

PRECEDENCE: leave > day off > shift. A person on holiday does not owe a shift,
even on a weekday the schedule fills in.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from operax.core.tenant import Bound, active_tenants, tenant_scope

TASK = "motor.jornada"

# S3 acceptance: the table is filled for the last 90 days.
DEFAULT_WINDOW_DAYS = 90

# The gate the detector reads, and the same 80 the partial index in migration 11
# is built on (`expected_workday_baixa_confianca_idx`).
CONFIDENCE_GATE = 80

# `%%` because psycopg reads `%` as the start of a placeholder.
#
# Every schema is spelled out. The pool fixes `search_path` to one schema and
# this statement spans two, so relying on it would be relying on the wrong thing.
_MATERIALIZE_SQL = """
with dia as (
    select generate_series(%(start)s::date, %(end)s::date, interval '1 day')::date
           as reference_date
),
escala as (
    -- How many weekdays the schedule declares as worked. Zero is the signal that
    -- the schedule carries no information — a rotation, or exception tracking.
    select hd.horario_id,
           count(*) filter (where not hd.sem_expediente) as work_days
    from secullum."HorarioDia" hd
    where hd.tenant_id = %(tenant_id)s
    group by hd.horario_id
),
pessoa as (
    select e.id                as employee_id,
           e.hired_on,
           e.terminated_on,
           f.id                as mirror_id,
           f.horario_id,
           h."HorarioId"       as secullum_schedule_id,
           coalesce(esc.work_days, 0) as work_days,
           rot.cycle_length_days,
           rot.anchor_date,
           rot.expected_entry            as rot_entry,
           rot.expected_exit             as rot_exit,
           rot.expected_break_minutes    as rot_break,
           rot.workload_minutes          as rot_workload,
           rot.tolerance_extra_minutes   as rot_tol_extra,
           rot.tolerance_absence_minutes as rot_tol_absence
    from app.employee e
    left join secullum."Funcionario" f
           on f.tenant_id = e.tenant_id
          and f."FuncionarioId" = e.secullum_employee_id
    left join secullum."Horario" h on h.id = f.horario_id
    left join escala esc on esc.horario_id = f.horario_id
    -- ⛔ `validated_at is not null` faz parte do JOIN, não do filtro depois: uma
    --    rotação provisória entraria como confiança 100 e viraria alerta contra
    --    alguém. Mapa que ninguém confirmou não é mapa.
    left join app.schedule_rotation_map rot
           on rot.tenant_id = e.tenant_id
          and rot.secullum_schedule_id = h."HorarioId"
          and rot.validated_at is not null
    where e.tenant_id = %(tenant_id)s
      -- Fora do motor por decisão (migration 26). Materializar um dia para quem
      -- não tem jornada a cumprir escreveria `work` sem hora com confiança 0 —
      -- indistinguível de falha de cobertura, que é o que a coluna existe para
      -- separar. Não escrever é a única forma de a ausência querer dizer algo.
      and not e.exception_tracking
),
afastamento as (
    -- The label is read to choose between two day types and is never stored:
    -- some of these say "Atest" and health data is not this table's business.
    -- An open-ended leave has no `Fim`, so it runs to infinity.
    select a.funcionario_id,
           a."Inicio"::date as starts_on,
           coalesce(a."Fim"::date, 'infinity'::date) as ends_on,
           case
             -- ⛔ upper ANTES do translate: a lista só tem maiúsculas, e o "é"
             --    minúsculo de "Férias" passava inteiro por ela.
             when translate(upper(coalesce(a."JustificativaNome", '')),
                            'ÁÀÂÃÉÊÍÓÔÕÚÜÇ', 'AAAAEEIOOOUUC') like 'FERIAS%%'
             then 'vacation' else 'leave_period'
           end as day_type
    from secullum."FuncionarioAfastamento" a
    where a.tenant_id = %(tenant_id)s
),
bruto as (
    select p.employee_id,
           p.secullum_schedule_id,
           p.work_days,
           p.rot_entry, p.rot_exit, p.rot_break, p.rot_workload,
           p.rot_tol_extra, p.rot_tol_absence,
           -- A rotação vale só onde o espelho não fala. Onde `HorarioDia`
           -- declara expediente, ele é o registro oficial, e curadoria não
           -- sobrescreve registro oficial — ela preenche silêncio.
           (p.cycle_length_days is not null and p.work_days = 0) as rot_applies,
           (p.cycle_length_days is not null and p.work_days = 0
            and (d.reference_date - p.anchor_date) %% p.cycle_length_days = 0) as rot_work,
           d.reference_date,
           af.day_type       as leave_type,
           hd."DiaSemana"    as dow,
           hd.sem_expediente as no_shift,
           hd."Entrada1"     as entry_at,
           coalesce(hd."Saida5", hd."Saida4", hd."Saida3",
                    hd."Saida2", hd."Saida1") as exit_at,
           -- ⛔ The break crosses midnight too, and one schedule in production
           --    does it: `U-075 - P05` leaves at 22:48 and returns at 00:00.
           --    Plain subtraction calls that minus twenty-two hours, and the
           --    detector would read every one of those nights as a break the
           --    person never took.
           case when hd."Saida1" is not null and hd."Entrada2" is not null
                then (extract(epoch from (hd."Entrada2" - hd."Saida1"
                       + case when hd."Entrada2" < hd."Saida1"
                              then interval '1 day' else interval '0' end)) / 60)::int
           end as break_minutes,
           hd."Carga"           as workload_minutes,
           hd."ToleranciaExtra" as tolerance_extra,
           hd."ToleranciaFalta" as tolerance_absence
    from pessoa p
    cross join dia d
    -- ⛔ ISODOW-1, never DOW: `DiaSemana` is 0=Monday and `extract(dow)` is
    --    0=Sunday. Getting this wrong shifts every expectation by one day.
    left join secullum."HorarioDia" hd
           on hd.horario_id = p.horario_id
          and hd."DiaSemana" = extract(isodow from d.reference_date)::int - 1
    left join lateral (
        select a.day_type
        from afastamento a
        where a.funcionario_id = p.mirror_id
          and d.reference_date between a.starts_on and a.ends_on
        -- 'leave_period' sorts before 'vacation'; overlapping leaves are rare and
        -- either answer is non-work, so the tie is broken deterministically
        -- rather than left to the plan.
        order by a.day_type
        limit 1
    ) af on true
    where (p.hired_on is null or d.reference_date >= p.hired_on)
      and (p.terminated_on is null or d.reference_date <= p.terminated_on)
),
classificado as (
    select b.*,
           (b.leave_type is null
            and b.work_days > 0
            and b.dow is not null
            and not b.no_shift) as scheduled_work,
           (b.leave_type is null and b.rot_work) as rot_scheduled
    from bruto b
)
insert into app.expected_workday (
    tenant_id, employee_id, reference_date, day_type,
    expected_entry, expected_exit, expected_break_minutes, workload_minutes,
    tolerance_extra_minutes, tolerance_absence_minutes,
    secullum_schedule_id, source, confidence
)
select
    %(tenant_id)s::uuid,
    c.employee_id,
    c.reference_date,
    case
      when c.leave_type is not null then c.leave_type
      -- A rotação decide os dois lados: o dia que ela trabalha e o que ela
      -- folga. É a diferença entre 12x36 e o `work` sem hora que o motor
      -- escrevia quando não sabia — aquele nunca virava folga porque não havia
      -- como distinguir folga de ignorância.
      when c.rot_applies            then case when c.rot_work then 'work' else 'day_off' end
      when c.work_days = 0          then 'work'
      when c.dow is null            then 'day_off'
      when c.no_shift               then 'day_off'
      else 'work'
    end,
    case when c.rot_scheduled then c.rot_entry
         when c.scheduled_work then c.entry_at end,
    case when c.rot_scheduled then c.rot_exit
         when c.scheduled_work then c.exit_at end,
    case when c.rot_scheduled then c.rot_break
         when c.scheduled_work then c.break_minutes end,
    case when c.rot_scheduled then c.rot_workload
         when c.scheduled_work then c.workload_minutes end,
    -- ⚠️ A day off arrives with both tolerances filled. Carrying them onto a day
    --    with no shift would hand the detector a window around nothing.
    case when c.rot_scheduled then c.rot_tol_extra
         when c.scheduled_work then coalesce(c.tolerance_extra, 0) else 0 end,
    case when c.rot_scheduled then c.rot_tol_absence
         when c.scheduled_work then coalesce(c.tolerance_absence, 0) else 0 end,
    c.secullum_schedule_id,
    case
      when c.leave_type is not null then 'secullum_schedule'
      when c.rot_applies            then 'manual_roster'
      when c.work_days = 0 or c.dow is null then 'inferred'
      else 'secullum_schedule'
    end,
    case
      when c.leave_type is not null then 100
      -- Declarada por um humano que carimbou o dia: é fato lido, do mesmo jeito
      -- que a semana do espelho é. O que não pode pontuar 100 é palpite, e
      -- palpite não chega aqui — o join exige `validated_at`.
      when c.rot_applies            then 100
      when c.work_days = 0          then 0
      when c.dow is null            then 0
      when c.no_shift               then 100
      when c.entry_at is null       then 50
      else 100
    end
from classificado c
on conflict (employee_id, reference_date) do update set
    day_type                  = excluded.day_type,
    expected_entry            = excluded.expected_entry,
    expected_exit             = excluded.expected_exit,
    expected_break_minutes    = excluded.expected_break_minutes,
    workload_minutes          = excluded.workload_minutes,
    tolerance_extra_minutes   = excluded.tolerance_extra_minutes,
    tolerance_absence_minutes = excluded.tolerance_absence_minutes,
    secullum_schedule_id      = excluded.secullum_schedule_id,
    source                    = excluded.source,
    confidence                = excluded.confidence
"""

# An employee counts as covered when EVERY materialised day of theirs clears the
# gate, not when the average does. A rotation scores 0 on all of them and a fixed
# week scores 100 on all of them, so the worst day is the honest summary.
_COVERAGE_SQL = """
with por_pessoa as (
    select w.employee_id, min(w.confidence) as worst, count(*) as days
    from app.expected_workday w
    where w.tenant_id = %(tenant_id)s
      and w.reference_date between %(start)s and %(end)s
    group by w.employee_id
)
select coalesce(sum(days), 0)::int                              as rows,
       count(*)::int                                            as employees,
       count(*) filter (where worst >= %(gate)s)::int            as employees_confident
from por_pessoa
"""

# Grouped by schedule description on purpose: it is what separates "seven people
# on a 12x36 whose rotation is not mirrored" from "six supervisors on exception
# tracking". Those need different answers, and the engine does not pick.
_GAPS_SQL = """
select coalesce(h."Descricao", '(sem horário no Secullum)') as schedule,
       count(distinct w.employee_id)::int as employees,
       count(*)::int                      as days
from app.expected_workday w
left join secullum."Horario" h
       on h."HorarioId" = w.secullum_schedule_id
      and h.tenant_id = w.tenant_id
where w.tenant_id = %(tenant_id)s
  and w.reference_date between %(start)s and %(end)s
  and w.confidence < %(gate)s
group by 1
order by 2 desc, 1
"""


@dataclass(frozen=True, slots=True)
class ScheduleGap:
    """One schedule that cannot answer "what was expected", and its weight."""

    schedule: str
    employees: int
    days: int


@dataclass(frozen=True, slots=True)
class Coverage:
    """The S3 report: how much of the roster the engine may be trusted on."""

    tenant_id: UUID
    start: date
    end: date
    rows: int
    employees: int
    employees_confident: int
    gaps: tuple[ScheduleGap, ...]

    @property
    def confident_ratio(self) -> float:
        return self.employees_confident / self.employees if self.employees else 0.0


async def materialize(context: Bound, start: date, end: date) -> Coverage:
    """Fill `app.expected_workday` for one tenant over a window, idempotently.

    Re-running over the same window rewrites the same rows: the primary key is
    `(employee_id, reference_date)` and every column is refreshed from the source,
    so a schedule corrected in Secullum lands on the next run instead of leaving
    a stale expectation behind.
    """
    window = {"start": start, "end": end}
    async with tenant_scope(context) as scope:
        await scope.execute(_MATERIALIZE_SQL, window)
        await scope.execute(_COVERAGE_SQL, {**window, "gate": CONFIDENCE_GATE})
        totals = await scope.fetchone()
        await scope.execute(_GAPS_SQL, {**window, "gate": CONFIDENCE_GATE})
        gaps = await scope.fetchall()

    return Coverage(
        tenant_id=context.tenant_id,
        start=start,
        end=end,
        rows=totals["rows"],
        employees=totals["employees"],
        employees_confident=totals["employees_confident"],
        gaps=tuple(
            ScheduleGap(schedule=g["schedule"], employees=g["employees"], days=g["days"])
            for g in gaps
        ),
    )


async def run(days: int = DEFAULT_WINDOW_DAYS, today: date | None = None) -> list[Coverage]:
    """Every active tenant, one at a time, each bound to its own context."""
    end = today or date.today()
    start = end - timedelta(days=days - 1)
    return [await materialize(ctx, start, end) for ctx in await active_tenants(TASK)]


def relatorio(coberturas: list[Coverage]) -> str:
    """O relatório de cobertura do S3, em pt-BR porque quem lê é o operador."""
    linhas: list[str] = []
    for c in coberturas:
        pct = 100 * c.confident_ratio
        linhas.append(
            f"tenant {c.tenant_id} · {c.start} a {c.end} · {c.rows} linha(s)\n"
            f"  {c.employees_confident} de {c.employees} colaboradores com confiança "
            f"≥{CONFIDENCE_GATE} = {pct:.1f}%"
        )
        for g in c.gaps:
            linhas.append(
                f"    sem jornada derivável: {g.employees} em «{g.schedule}» ({g.days} dias)"
            )
        if not c.gaps and c.employees:
            linhas.append("    nenhuma lacuna: toda a base tem jornada derivável")
    return "\n".join(linhas) or "nenhum tenant ativo"


def main() -> None:
    parser = argparse.ArgumentParser(description="Materializa app.expected_workday.")
    parser.add_argument(
        "--dias", type=int, default=DEFAULT_WINDOW_DAYS, help="tamanho da janela (padrão 90)"
    )
    args = parser.parse_args()
    print(relatorio(asyncio.run(run(days=args.dias))))


if __name__ == "__main__":
    main()
