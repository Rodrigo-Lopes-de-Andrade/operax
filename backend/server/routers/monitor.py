"""Daily monitor — Caminho 2 of the contract.

The roster of who was expected to work today lives in `app.expected_workday`,
and that table is not on the public surface. Putting it there would mean a new
view in `public` exposing new columns, which is one of the three decisions this
project always stops and asks about. It does not need to be taken: the screen is
about named people on a specific day, which is Caminho 2 anyway.

So the reads run through `user_scope`, as `authenticated`, and
`expected_workday_read` — `util.can_see_employee` — is what makes a unit
supervisor see one unit. The filter is not written here; there is nothing here
to forget.

What the monitor can honestly claim is narrower than it looks, and the shape of
the answer says so. Punches are not mirrored into `app`: they stay in the source
schema, which is never exposed. So a person with no indication is a person the
last reading found nothing about — not a person who is present. The screen
carries the age of that reading beside every count.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from operax.core.tenant import user_scope
from server.deps import CurrentTenant
from server.models import DailyMonitor, MonitorRow, MonitorUnitRow, Severity

router = APIRouter(prefix="/monitor", tags=["monitor"])

# A day of one tenant is bounded by its headcount, so this is a ceiling and not
# a page. It exists so a bad day at a large tenant cannot turn the wall screen
# into a megabyte of JSON — and when it bites, the answer says so instead of
# quietly stopping at 500.
_MAX_ROWS = 500

# How loud each indication is. This is presentation policy, not data: the same
# `no_punches` is an emergency at 10:00 and a fact at 23:00, and no tenant has
# asked to configure it yet. Keeping it here means one place decides, and the
# database keeps storing what happened rather than how it should feel.
#
# `critical` is "somebody is missing right now". `attention` is "the day is
# already wrong and can still be fixed". `watch` is "worth knowing at closing".
_SEVERITY: dict[str, Severity] = {
    "no_punches": "critical",
    "break_no_return": "critical",
    "incomplete_punches": "attention",
    "late_entry": "attention",
    "early_exit": "attention",
    "outside_perimeter": "attention",
    "break_exceeded": "watch",
    "break_too_short": "watch",
    "workday_exceeded": "watch",
    "punch_on_day_off": "watch",
    "late_exit": "watch",
    "early_entry": "watch",
}
_DEFAULT_SEVERITY: Severity = "watch"
_SEVERITY_ORDER: dict[Severity, int] = {"critical": 0, "attention": 1, "watch": 2}

# The roster of the day, joined to whether the engine found anything. Kept as
# one statement so "escalado" and "com indício" are counted over the same rows —
# two queries would disagree the moment a colleague is admitted mid-morning.
#
# IT IS DRIVEN BY `app.employee`, NOT BY `app.expected_workday`, AND THAT IS THE
# WHOLE POINT OF THE HEADCOUNT
# The roster used to start from the expected workday, which meant a person the
# engine never materialised simply did not exist on this screen: not scheduled,
# not off, not counted. Six people at the anchor client are in exactly that
# state on purpose — their schedules are "Ponto por exceção" and they belong
# outside the engine — and there is no way to tell them apart from a coverage
# failure by looking. Starting from the active headcount makes the difference a
# number (`unrostered`) instead of an absence, and a unit whose whole team is off
# stops disappearing from the list.
_UNITS_SQL = """
    with roster as (
        select c.id as employee_id, w.day_type, c.unit_id, u.name as unit_name
        from app.employee c
        left join app.unit u on u.id = c.unit_id
        left join app.expected_workday w
               on w.employee_id = c.id
              and w.reference_date = %(dia)s
        where c.status = 'active'
          and (%(unit_id)s::uuid is null or c.unit_id = %(unit_id)s::uuid)
    ),
    indication as (
        select distinct d.employee_id
        from app.deviation_event d
        where d.reference_date = %(dia)s
          and d.status = 'active'
          and d.mode = 'production'
    )
    select r.unit_id,
           r.unit_name,
           count(*) as active,
           count(*) filter (where r.day_type = 'work') as scheduled,
           count(*) filter (
               where r.day_type = 'work' and i.employee_id is not null
           ) as with_indication,
           count(*) filter (
               where r.day_type = 'work' and i.employee_id is null
           ) as clear,
           count(*) filter (where r.day_type = 'vacation')     as on_vacation,
           count(*) filter (where r.day_type = 'leave_period') as on_leave,
           count(*) filter (
               where r.day_type in ('day_off', 'holiday', 'compensated')
           ) as day_off,
           count(*) filter (where r.day_type is null) as unrostered,
           count(*) filter (
               where r.day_type is not null and r.day_type <> 'work'
           ) as off_roster
    from roster r
    left join indication i on i.employee_id = r.employee_id
    group by r.unit_id, r.unit_name
    order by r.unit_name nulls last
"""

# One row per indication, not per person: "atrasou" and "não voltou do
# intervalo" are two things the manager has to act on, and folding them into one
# row would hide the second.
#
# The roster is a left join on purpose. `punch_on_day_off` exists precisely
# because somebody punched on a day the roster did not expect, and an inner join
# would drop exactly the row that needs a human.
_ROWS_SQL = """
    select d.employee_id,
           c.name        as employee_name,
           c.unit_id,
           u.name        as unit_name,
           w.day_type,
           w.expected_entry,
           w.expected_exit,
           w.confidence,
           d.type,
           t.description as type_description,
           t.direction,
           d.minutes,
           d.expected_time,
           d.actual_time,
           d.detected_at
    from app.deviation_event d
    join app.employee c        on c.id = d.employee_id
    join app.deviation_type t  on t.code = d.type
    left join app.unit u       on u.id = c.unit_id
    left join app.expected_workday w
           on w.employee_id = d.employee_id
          and w.reference_date = d.reference_date
    where d.reference_date = %(dia)s
      and d.status = 'active'
      and d.mode = 'production'
      and (%(unit_id)s::uuid is null or c.unit_id = %(unit_id)s::uuid)
"""


@router.get("/diario")
async def daily_monitor(
    tenant: CurrentTenant,
    dia: Annotated[date, Query(description="Dia observado, no fuso do cliente")],
    unidade: Annotated[UUID | None, Query(description="Recorte de unidade")] = None,
) -> DailyMonitor:
    """The situation of one day, by unit and by person."""
    params = {"dia": dia, "unit_id": unidade}

    async with user_scope(tenant) as scope:
        await scope.execute(_UNITS_SQL, params)
        unit_rows = await scope.fetchall()

        await scope.execute(_ROWS_SQL, params)
        indication_rows = await scope.fetchall()

    units = [MonitorUnitRow(**row) for row in unit_rows]
    rows = sorted(
        (MonitorRow(severity=_severity_of(row["type"]), **row) for row in indication_rows),
        key=_worst_first,
    )

    return DailyMonitor(
        day=dia,
        active=sum(unit.active for unit in units),
        scheduled=sum(unit.scheduled for unit in units),
        with_indication=sum(unit.with_indication for unit in units),
        clear=sum(unit.clear for unit in units),
        on_vacation=sum(unit.on_vacation for unit in units),
        on_leave=sum(unit.on_leave for unit in units),
        day_off=sum(unit.day_off for unit in units),
        unrostered=sum(unit.unrostered for unit in units),
        off_roster=sum(unit.off_roster for unit in units),
        units=units,
        rows=rows[:_MAX_ROWS],
        truncated=len(rows) > _MAX_ROWS,
    )


def _severity_of(deviation_type: str) -> Severity:
    return _SEVERITY.get(deviation_type, _DEFAULT_SEVERITY)


def _worst_first(row: MonitorRow) -> tuple[int, int, str, str]:
    """Loudest first, then the longest deviation, then a stable name order.

    Sorting here rather than in SQL keeps `_SEVERITY` as the only place that
    ranks a type: a `case` in the query would be the same policy written twice,
    and the two would drift at the first new deviation type.
    """
    return (
        _SEVERITY_ORDER[row.severity],
        -abs(row.minutes),
        row.unit_name or "",
        row.employee_name,
    )
