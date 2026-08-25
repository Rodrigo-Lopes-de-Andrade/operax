"""Individual consultation — Caminho 2 of the contract.

Everything here is about one named person, so none of it belongs on the anon
path. The reads run through `user_scope`: the transaction takes the
`authenticated` role and the `sub` of the validated token, and the policies that
already guard the browser decide what comes back. A colleague outside the
caller's scope does not come back filtered — the header query returns nothing and
the answer is 404, which is also the right answer to "does this person exist".

The three sensitive blocks are gated by `util.can_see_domain`, the same helper
the policies call. The gate is needed on top of RLS for one reason: with RLS
alone, "you may not see salaries" and "this person has no salary on record" are
both an empty list, and the screen has to tell them apart — one renders nothing,
the other renders an empty state.

The punches are the single read here that leaves `user_scope`, and the order is
what makes that safe. `app.batida_marcacao` keys the person by a uuid of the
mirror, and `secullum` is revoked from `authenticated` at the schema level, so
the bridge cannot run as the user. It runs after the header query has already
answered: if the policies did not return this person, the request is a 404 and
the punch query never happens. Authorisation stays in the policy; the second
scope only fetches, by an id already cleared.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from operax.core.tenant import tenant_scope, user_scope
from operax.motor.marcacao import EMPLOYEE_PUNCHES_SQL, PUNCH_READING_SQL
from server.deps import CurrentTenant
from server.models import (
    CompensationBand,
    DeviationIndicators,
    DeviationTypeCount,
    EmployeeDetail,
    EmployeeDocument,
    EmployeeSummary,
    JustificationRow,
    OccupationalExamRow,
    PunchRow,
    WorkdayRow,
)

router = APIRouter(prefix="/colaboradores", tags=["colaboradores"])

_MAX_JUSTIFICATIONS = 20

_EMPLOYEE_SQL = """
    select c.id as employee_id, c.name, c.registration_number, c.cargo, c.status,
           c.hired_on, c.employment_type,
           u.name   as unit_name,
           e.trade_name as company_name,
           dep.name as department_name,
           g.name   as manager_name
    from app.employee c
    left join app.unit u        on u.id = c.unit_id
    left join app.company e     on e.id = c.company_id
    left join app.department dep on dep.id = c.department_id
    left join app.employee g    on g.id = c.manager_employee_id
    where c.id = %(employee_id)s
"""

# Every aggregate joins deviation_type_config the way the public views do, so a
# type the tenant marked as informative stays out of the KPI here too.
_COUNTED = """
    from app.deviation_event d
    join app.deviation_type_config cfg
         on cfg.tenant_id = d.tenant_id and cfg.code = d.type
        and cfg.counts_as_deviation and cfg.active
    where d.employee_id = %(employee_id)s
      and d.status = 'active' and d.mode = 'production'
      and d.reference_date between %(de)s and %(ate)s
"""

_INDICATORS_SQL = f"""
    select count(*)                                        as events,
           coalesce(sum(abs(d.minutes)), 0)                as minutes_abs,
           coalesce(sum(d.minutes), 0)                     as minutes_balance,
           count(distinct d.reference_date)                as days_with_deviation,
           count(*) filter (where d.report_cycle_id is null) as pending_cycle
    {_COUNTED}
"""

_BY_TYPE_SQL = """
    select d.type, t.description,
           count(*)                         as events,
           coalesce(sum(abs(d.minutes)), 0) as minutes_abs
    from app.deviation_event d
    join app.deviation_type t on t.code = d.type
    join app.deviation_type_config cfg
         on cfg.tenant_id = d.tenant_id and cfg.code = d.type
        and cfg.counts_as_deviation and cfg.active
    where d.employee_id = %(employee_id)s
      and d.status = 'active' and d.mode = 'production'
      and d.reference_date between %(de)s and %(ate)s
    group by d.type, t.description
    order by count(*) desc
"""

_WORKDAYS_SQL = """
    select w.reference_date, w.day_type, w.expected_entry, w.expected_exit, w.confidence,
           d.type        as deviation_type,
           t.description as deviation_description,
           t.direction,
           d.minutes, d.expected_time, d.actual_time
    from app.expected_workday w
    left join app.deviation_event d
           on d.employee_id = w.employee_id
          and d.reference_date = w.reference_date
          and d.status = 'active' and d.mode = 'production'
    left join app.deviation_type t on t.code = d.type
    where w.employee_id = %(employee_id)s
      and w.reference_date between %(de)s and %(ate)s
    order by w.reference_date desc
"""

_JUSTIFICATIONS_SQL = """
    select j.reference_date, j.text, j.author_name, j.source
    from app.justification j
    where j.employee_id = %(employee_id)s
    order by j.reference_date desc
    limit %(limit)s
"""

_DOMAINS_SQL = """
    select util.can_see_domain(%(tenant_id)s, 'compensation') as compensation,
           util.can_see_domain(%(tenant_id)s, 'pii')          as pii,
           util.can_see_domain(%(tenant_id)s, 'health')       as health
"""

_COMPENSATION_SQL = """
    select r.effective_from, r.effective_to, r.salary, r.reason
    from app.employee_compensation r
    where r.employee_id = %(employee_id)s
    order by r.effective_from desc
"""

_DOCUMENTS_SQL = """
    select dt.name as type_name, doc.valid_until, doc.status
    from app.document doc
    join app.document_type dt on dt.id = doc.type_id
    where doc.employee_id = %(employee_id)s
      and doc.status = 'active'
    order by doc.valid_until nulls last
"""

_EXAMS_SQL = """
    select x.type, x.performed_on, x.valid_until, x.result
    from app.occupational_exam x
    where x.employee_id = %(employee_id)s
    order by x.performed_on desc
"""


@router.get("/{employee_id}")
async def get_employee(
    employee_id: UUID,
    tenant: CurrentTenant,
    de: Annotated[date, Query(description="Primeiro dia do recorte")],
    ate: Annotated[date, Query(description="Último dia do recorte")],
) -> EmployeeDetail:
    """One person's cut, plus the sensitive blocks the caller's role reaches."""
    if ate < de:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="O fim do período é anterior ao início.",
        )

    window = {"employee_id": employee_id, "de": de, "ate": ate}

    async with user_scope(tenant) as scope:
        await scope.execute(_EMPLOYEE_SQL, {"employee_id": employee_id})
        employee = await scope.fetchone()

        # Out of scope and non-existent answer the same way on purpose: a 403
        # here would confirm that the person exists in another unit.
        if employee is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Colaborador não encontrado.",
            )

        await scope.execute(_INDICATORS_SQL, window)
        indicators = await scope.fetchone()

        await scope.execute(_BY_TYPE_SQL, window)
        by_type = await scope.fetchall()

        await scope.execute(_WORKDAYS_SQL, window)
        workdays = await scope.fetchall()

        await scope.execute(
            _JUSTIFICATIONS_SQL,
            {"employee_id": employee_id, "limit": _MAX_JUSTIFICATIONS},
        )
        justifications = await scope.fetchall()

        await scope.execute(_DOMAINS_SQL, {"tenant_id": tenant.tenant_id})
        domains = await scope.fetchone()

        compensation = None
        if domains and domains["compensation"]:
            await scope.execute(_COMPENSATION_SQL, {"employee_id": employee_id})
            compensation = [CompensationBand(**row) for row in await scope.fetchall()]

        documents = None
        if domains and domains["pii"]:
            await scope.execute(_DOCUMENTS_SQL, {"employee_id": employee_id})
            documents = [EmployeeDocument(**row) for row in await scope.fetchall()]

        exams = None
        if domains and domains["health"]:
            await scope.execute(_EXAMS_SQL, {"employee_id": employee_id})
            exams = [OccupationalExamRow(**row) for row in await scope.fetchall()]

    # Only now, and only for a person the policies just returned.
    async with tenant_scope(tenant) as bound:
        await bound.execute(PUNCH_READING_SQL, {})
        reading = await bound.fetchone()
        readable = bool(reading and reading["mirror_present"])

        punches: list[PunchRow] = []
        if readable:
            await bound.execute(EMPLOYEE_PUNCHES_SQL, window)
            punches = [PunchRow(**row) for row in await bound.fetchall()]

    return EmployeeDetail(
        employee=EmployeeSummary(**employee),
        indicators=DeviationIndicators(**indicators) if indicators else _NO_DEVIATION,
        by_type=[DeviationTypeCount(**row) for row in by_type],
        workdays=[WorkdayRow(**row) for row in workdays],
        punches=punches,
        punches_read_at=reading["read_at"] if readable else None,
        justifications=[JustificationRow(**row) for row in justifications],
        compensation=compensation,
        documents=documents,
        exams=exams,
    )


_NO_DEVIATION = DeviationIndicators(
    events=0, minutes_abs=0, minutes_balance=0, days_with_deviation=0, pending_cycle=0
)
