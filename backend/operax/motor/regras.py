"""The rules, as SQL and nothing else — no driver, no connection, no import.

Three statements read the same definition of "what is a deviation on this day",
and they have to agree or the engine contradicts itself: the detector writes it,
and the revoker asks twice whether a stored event still matches it. A second copy
of a three-hundred-line `union all` would drift on the first tolerance change,
and the copy that drifts is never the one somebody is looking at.

It also has no imports on purpose. `scripts/94_teste_deteccao.py` runs on the
system python, outside the backend venv, and imports this module to get exactly
the SQL the engine runs — the same reason `templates.py` holds the HR select.
SQL that cannot be checked against a real schema is SQL that only fails in
production.

`%%` is psycopg's escape for a literal percent; the test script undoes it.

A DAY IS NOT A CLOCK FACE, AND THE SOURCE ALREADY KNEW
A night shift belongs to the day it started: Secullum keeps the whole journey on
one day-record, so grouping by `data` is right. What is wrong is subtracting one
`time` from another across it — 05:00 minus 19:00 is not minus fourteen hours,
it is plus ten.

So every punch becomes an instant before anything compares it, and the offset has
two sources. `secullum."BatidaFonteDados"."Data"` is the date the equipment
recorded and is the rule; the backwards step in positional order is the fallback,
for the punch whose `FonteDados` is missing (1:1 OPTIONAL, ADR-007). Measured
over production on 2026-08-26 the fallback agreed on all 79 real crossings and
invented 4 more, on days whose punches are merely out of order — which is why it
is second and why it is capped at one day. A day wrongly shifted 24 h is not a
small error: it is a full-day `workday_exceeded` against somebody.

`app.deviation_event.expected_time` and `actual_time` stay `time`. The grain does
not move; only the arithmetic that feeds it.
"""

from __future__ import annotations

#: What the day says, before anybody decides what to do with it. Ends on the
#: `evento` CTE, so each statement below appends its own verb.
EVENTS_SQL = """
with dia as (
    -- Leave and vacation leave whole. Precedence belongs to the expected workday
    -- (SPEC §3.1) and a day somebody did not owe has no deviation to compute.
    select w.employee_id, w.reference_date, w.day_type,
           w.expected_entry, w.expected_exit, w.expected_break_minutes,
           -- A shift that ends before it starts ends on the NEXT day, and the
           -- source declares it that way: six schedules in production carry
           -- `Entrada1` 19:00 with the last `Saida` at 05:00, on every weekday
           -- they declare. Compared as `time`, that exit reads as fourteen hours
           -- EARLY instead of ten hours later.
           (w.reference_date + w.expected_entry) as expected_entry_at,
           (w.reference_date + w.expected_exit
            + case when w.expected_exit < w.expected_entry
                   then interval '1 day' else interval '0' end) as expected_exit_at,
           w.workload_minutes, w.tolerance_extra_minutes, w.tolerance_absence_minutes,
           e.company_id, e.unit_id, f.id as mirror_id
    from app.expected_workday w
    join app.employee e on e.id = w.employee_id
    left join secullum."Funcionario" f
           on f.tenant_id = e.tenant_id
          and f."FuncionarioId" = e.secullum_employee_id
    where w.tenant_id = %(tenant_id)s
      and w.reference_date between %(start)s::date and %(end)s::date
      and w.day_type not in ('vacation', 'leave_period')
),
coluna as (
    -- Every mirrored column of the day, punch or not. `desconsiderada` stays
    -- recorded for traceability and never becomes a deviation.
    select m.funcionario_id, m.data, m.tipo_coluna, m.indice_coluna,
           m.hora, m."Memoria" as memoria, m."FonteDadosId" as fonte_id,
           -- The calendar date the equipment recorded, which is NOT the day of
           -- the day-record when the shift crosses midnight: `Batida."Data"`
           -- keeps the whole journey on the day it started. 1:1 and OPTIONAL
           -- (ADR-007), so it is a source, not the only one.
           (fd."Data" - m.data) as offset_real
    from app.batida_marcacao m
    left join secullum."BatidaFonteDados" fd on fd.batida_marcacao_id = m.id
    where m.tenant_id = %(tenant_id)s
      and m.data between %(start)s::date and %(end)s::date
      and not m.desconsiderada
),
recuo as (
    -- A row with no `hora` is not a punch: the dictionary says so, and counting
    -- it would make an unfilled column look like somebody clocking in.
    --
    -- `recuou` is the fallback for a punch whose `FonteDados` is missing: read in
    -- positional order, the clock only goes backwards when the day crossed
    -- midnight. It is a fallback and not the rule because it is the one that
    -- LIES — measured against production it agreed on all 79 real crossings and
    -- invented 4 more, on days whose punches are merely out of order. A day
    -- shifted 24 h that did not cross is a full-day `workday_exceeded`.
    select c.*,
           case when c.hora < lag(c.hora) over (
                       partition by c.funcionario_id, c.data
                       order by c.indice_coluna,
                                case c.tipo_coluna when 'Entrada' then 0 else 1 end)
                then 1 else 0 end as recuou
    from coluna c
    where c.hora is not null
),
batida as (
    select r.funcionario_id, r.data, r.tipo_coluna, r.indice_coluna, r.hora,
           r.memoria, r.fonte_id,
           -- The instant, not the clock face. Everything downstream subtracts.
           r.data + r.hora + (coalesce(
             r.offset_real,
             least(sum(r.recuou) over (
                     partition by r.funcionario_id, r.data
                     order by r.indice_coluna,
                              case r.tipo_coluna when 'Entrada' then 0 else 1 end
                     rows between unbounded preceding and current row), 1)
           ) * interval '1 day') as at
    from recuo r
),
par as (
    -- Entrada and Saída of the SAME index are a pair. The payload is positional,
    -- and pairing by time order would invent a pair where one side is missing.
    select b.funcionario_id, b.data, b.indice_coluna,
           max(b.at) filter (where b.tipo_coluna = 'Entrada') as entrada,
           max(b.at) filter (where b.tipo_coluna = 'Saida')   as saida
    from batida b
    group by 1, 2, 3
),
resumo as (
    select b.funcionario_id, b.data,
           count(*)   as punches,
           min(b.at) as first_punch_at,
           max(b.at) as last_punch_at,
           coalesce(
             array_agg(b.fonte_id order by b.fonte_id) filter (where b.fonte_id is not null),
             '{}'::bigint[]
           ) as punch_ids
    from batida b
    group by 1, 2
),
trabalhado as (
    select p.funcionario_id, p.data,
           sum(extract(epoch from (p.saida - p.entrada)) / 60)::int as worked_minutes
    from par p
    where p.entrada is not null and p.saida is not null
    group by 1, 2
),
intervalo as (
    -- The gap between the first exit and the second entry — the same definition
    -- `jornada.py` uses for `expected_break_minutes`. Both sides of a comparison
    -- have to measure the same thing.
    select s.funcionario_id, s.data,
           (extract(epoch from (e2.at - s.at)) / 60)::int as break_minutes
    from batida s
    join batida e2
      on e2.funcionario_id = s.funcionario_id and e2.data = s.data
     and e2.tipo_coluna = 'Entrada' and e2.indice_coluna = 2
    where s.tipo_coluna = 'Saida' and s.indice_coluna = 1
),
fato as (
    select d.*,
           coalesce(r.punches, 0) as punches,
           r.first_punch_at, r.last_punch_at,
           r.first_punch_at::time as first_punch,
           r.last_punch_at::time  as last_punch,
           coalesce(r.punch_ids, '{}'::bigint[]) as punch_ids,
           coalesce(t.worked_minutes, 0) as worked_minutes,
           i.break_minutes,
           -- Left for the break and never came back: the return column exists on
           -- the day with the schedule's own expectation in `Memoria` and no
           -- time. It is the mirror saying "a punch is missing here".
           exists (
             select 1 from coluna c
             where c.funcionario_id = d.mirror_id and c.data = d.reference_date
               and c.tipo_coluna = 'Entrada' and c.indice_coluna = 2
               and c.hora is null and c.memoria is not null
           ) as no_return
    from dia d
    left join resumo r on r.funcionario_id = d.mirror_id and r.data = d.reference_date
    left join trabalhado t on t.funcionario_id = d.mirror_id and t.data = d.reference_date
    left join intervalo i on i.funcionario_id = d.mirror_id and i.data = d.reference_date
),
cfg as (
    -- A type with no row is active: it is the column default, and a tenant that
    -- was never configured must not silently stop being watched.
    select code, active, tolerance_extra_minutes, tolerance_absence_minutes
    from app.deviation_type_config
    where tenant_id = %(tenant_id)s
),
evento as (
    -- Punched on a day with no shift.
    select f.employee_id, f.reference_date, f.company_id, f.unit_id, f.punch_ids,
           'punch_on_day_off'::text as type,
           f.worked_minutes as minutes,
           null::time as expected_time, f.first_punch as actual_time
    from fato f
    left join cfg c on c.code = 'punch_on_day_off'
    where coalesce(c.active, true) and f.day_type = 'day_off' and f.punches > 0

    union all
    -- A working day with no punch at all. Requires a declared workload: see the
    -- module docstring — you cannot miss a shift nobody could describe.
    select f.employee_id, f.reference_date, f.company_id, f.unit_id, f.punch_ids,
           'no_punches', -f.workload_minutes, f.expected_entry, null::time
    from fato f
    left join cfg c on c.code = 'no_punches'
    where coalesce(c.active, true) and f.day_type = 'work'
      and f.punches = 0 and f.workload_minutes is not null

    union all
    -- Odd number of punches: some column has one side and not the other.
    select f.employee_id, f.reference_date, f.company_id, f.unit_id, f.punch_ids,
           'incomplete_punches', 0, null::time, f.last_punch
    from fato f
    left join cfg c on c.code = 'incomplete_punches'
    where coalesce(c.active, true) and f.punches > 0 and f.punches %% 2 = 1

    union all
    select f.employee_id, f.reference_date, f.company_id, f.unit_id, f.punch_ids,
           'late_entry',
           -(extract(epoch from (f.first_punch_at - f.expected_entry_at)) / 60)::int,
           f.expected_entry, f.first_punch
    from fato f
    left join cfg c on c.code = 'late_entry'
    where coalesce(c.active, true) and f.day_type = 'work'
      and f.punches > 0 and f.expected_entry_at is not null
      and extract(epoch from (f.first_punch_at - f.expected_entry_at)) / 60
          > coalesce(c.tolerance_absence_minutes, f.tolerance_absence_minutes)

    union all
    select f.employee_id, f.reference_date, f.company_id, f.unit_id, f.punch_ids,
           'early_entry',
           -(extract(epoch from (f.first_punch_at - f.expected_entry_at)) / 60)::int,
           f.expected_entry, f.first_punch
    from fato f
    left join cfg c on c.code = 'early_entry'
    where coalesce(c.active, true) and f.day_type = 'work'
      and f.punches > 0 and f.expected_entry_at is not null
      and extract(epoch from (f.first_punch_at - f.expected_entry_at)) / 60
          < -coalesce(c.tolerance_extra_minutes, f.tolerance_extra_minutes)

    union all
    select f.employee_id, f.reference_date, f.company_id, f.unit_id, f.punch_ids,
           'early_exit',
           (extract(epoch from (f.last_punch_at - f.expected_exit_at)) / 60)::int,
           f.expected_exit, f.last_punch
    from fato f
    left join cfg c on c.code = 'early_exit'
    where coalesce(c.active, true) and f.day_type = 'work'
      and f.punches > 1 and f.expected_exit_at is not null
      and extract(epoch from (f.last_punch_at - f.expected_exit_at)) / 60
          < -coalesce(c.tolerance_absence_minutes, f.tolerance_absence_minutes)

    union all
    select f.employee_id, f.reference_date, f.company_id, f.unit_id, f.punch_ids,
           'late_exit',
           (extract(epoch from (f.last_punch_at - f.expected_exit_at)) / 60)::int,
           f.expected_exit, f.last_punch
    from fato f
    left join cfg c on c.code = 'late_exit'
    where coalesce(c.active, true) and f.day_type = 'work'
      and f.punches > 1 and f.expected_exit_at is not null
      and extract(epoch from (f.last_punch_at - f.expected_exit_at)) / 60
          > coalesce(c.tolerance_extra_minutes, f.tolerance_extra_minutes)

    union all
    select f.employee_id, f.reference_date, f.company_id, f.unit_id, f.punch_ids,
           'break_exceeded', -(f.break_minutes - f.expected_break_minutes),
           null::time, null::time
    from fato f
    left join cfg c on c.code = 'break_exceeded'
    where coalesce(c.active, true) and f.break_minutes is not null
      and f.expected_break_minutes is not null
      and f.break_minutes
          > f.expected_break_minutes + coalesce(c.tolerance_extra_minutes,
                                                f.tolerance_extra_minutes)

    union all
    select f.employee_id, f.reference_date, f.company_id, f.unit_id, f.punch_ids,
           'break_too_short', (f.expected_break_minutes - f.break_minutes),
           null::time, null::time
    from fato f
    left join cfg c on c.code = 'break_too_short'
    where coalesce(c.active, true) and f.break_minutes is not null
      and f.expected_break_minutes is not null
      and f.break_minutes
          < f.expected_break_minutes - coalesce(c.tolerance_absence_minutes,
                                                f.tolerance_absence_minutes)

    union all
    -- Left for the break and did not come back. Only where a break was expected:
    -- otherwise the last exit of a plain day would look like a missing return.
    select f.employee_id, f.reference_date, f.company_id, f.unit_id, f.punch_ids,
           'break_no_return', 0, null::time, f.last_punch
    from fato f
    left join cfg c on c.code = 'break_no_return'
    where coalesce(c.active, true) and f.no_return
      and f.expected_break_minutes is not null

    union all
    -- SPEC §3.2 says "limite_jornada_configurado" and no column holds one. The
    -- day's own workload plus the extra tolerance is the only limit the data
    -- offers; making it configurable is a product decision, and inventing a
    -- constant here would have taken it in silence.
    select f.employee_id, f.reference_date, f.company_id, f.unit_id, f.punch_ids,
           'workday_exceeded',
           f.worked_minutes - (f.workload_minutes
                               + coalesce(c.tolerance_extra_minutes,
                                          f.tolerance_extra_minutes)),
           null::time, f.last_punch
    from fato f
    left join cfg c on c.code = 'workday_exceeded'
    where coalesce(c.active, true) and f.day_type = 'work'
      and f.workload_minutes is not null
      and f.worked_minutes > f.workload_minutes
                             + coalesce(c.tolerance_extra_minutes,
                                        f.tolerance_extra_minutes)
)
"""

#: SPEC §3.3 — re-running the same window rewrites the same row instead of adding
#: one. The `where` on the update is the retroactive rule: an event already tied
#: to a report cycle was **sent to somebody**, and silently rewriting it would
#: make the dashboard disagree with the message in the manager's hand. Those go
#: through `revogacao.py`, which revokes and supersedes with a trail.
DETECT_SQL = (
    EVENTS_SQL
    + """insert into app.deviation_event (
    tenant_id, employee_id, company_id, unit_id, reference_date, type,
    minutes, expected_time, actual_time, punch_ids, mode, run_id
)
select %(tenant_id)s::uuid, e.employee_id, e.company_id, e.unit_id, e.reference_date,
       e.type, e.minutes, e.expected_time, e.actual_time, e.punch_ids,
       %(mode)s, %(run_id)s::uuid
from evento e
-- Re-running the same window rewrites the same row instead of adding one. The
-- index behind this covers both modes since migration 18; before it, shadow had
-- no uniqueness and a second run of the same week doubled every event.
on conflict (employee_id, reference_date, type, mode) where status = 'active'
do update set
    minutes       = excluded.minutes,
    expected_time = excluded.expected_time,
    actual_time   = excluded.actual_time,
    punch_ids     = excluded.punch_ids,
    company_id    = app.deviation_event.company_id,
    unit_id       = app.deviation_event.unit_id,
    run_id        = excluded.run_id,
    updated_at    = now()
where app.deviation_event.report_cycle_id is null
"""
)

#: The deviation stopped existing: the punch was corrected at the source. The
#: engine cannot notice this by writing — an insert has nothing to say about a
#: row that should no longer be there — so it is asked as a question.
VANISHED_SQL = (
    EVENTS_SQL
    + """
select d.id, d.type, d.reference_date, d.employee_id, d.minutes
from app.deviation_event d
where d.tenant_id = %(tenant_id)s
  and d.mode = %(mode)s
  and d.status = 'active'
  and d.reference_date between %(start)s::date and %(end)s::date
  and not exists (
    select 1 from evento e
    where e.employee_id = d.employee_id
      and e.reference_date = d.reference_date
      and e.type = d.type
  )
"""
)

#: The deviation still exists and changed size, on an event that already went out
#: in a report. Only those: the detector updates the rest in place.
SUPERSEDED_SQL = (
    EVENTS_SQL
    + """
select d.id, d.type, d.reference_date, d.employee_id,
       d.minutes as minutes_before,
       e.minutes as minutes_now,
       e.company_id, e.unit_id, e.expected_time, e.actual_time, e.punch_ids
from app.deviation_event d
join evento e
  on e.employee_id = d.employee_id
 and e.reference_date = d.reference_date
 and e.type = d.type
where d.tenant_id = %(tenant_id)s
  and d.mode = %(mode)s
  and d.status = 'active'
  and d.report_cycle_id is not null
  and d.reference_date between %(start)s::date and %(end)s::date
  and d.minutes is distinct from e.minutes
"""
)
