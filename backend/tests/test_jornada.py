"""What the engine decides in Python, away from the database.

The SQL is where almost all of this module's judgement lives, and it is proved
against a real schema by `scripts/96_teste_jornada.py` — which extracts the very
statement this module runs, so the two cannot drift. What is left here is the
part that has no database in it: the context a scheduled task binds with, and
the coverage report an operator reads.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from operax.core.tenant import (
    MissingTenantContextError,
    MissingTenantFilterError,
    SystemContext,
    TenantContext,
    UserRole,
    bind_tenant,
)
from operax.motor.jornada import CONFIDENCE_GATE, Coverage, ScheduleGap, relatorio

TENANT = UUID("33333333-3333-4333-8333-333333333333")
FILTERED = "select 1 from app.expected_workday where tenant_id = %(tenant_id)s"


def test_a_scheduled_task_binds_a_tenant_without_pretending_to_be_a_user() -> None:
    context = SystemContext(tenant_id=TENANT, task="motor.jornada")
    assert bind_tenant(FILTERED, None, context) == {"tenant_id": TENANT}


def test_the_task_must_name_itself() -> None:
    # It is what identifies the query in `pg_stat_activity`; an empty name would
    # make the log say nothing precisely when someone is reading it.
    with pytest.raises(MissingTenantContextError):
        SystemContext(tenant_id=TENANT, task="   ")


def test_the_task_context_still_refuses_an_unresolved_tenant() -> None:
    with pytest.raises(MissingTenantContextError):
        SystemContext(tenant_id=UUID(int=0), task="motor.jornada")


def test_a_task_cannot_skip_the_tenant_filter_either() -> None:
    # A different failure from an unresolved context, and the distinction is the
    # point: the task IS bound to a tenant, and still wrote a statement that
    # would have read every one of them.
    context = SystemContext(tenant_id=TENANT, task="motor.jornada")
    with pytest.raises(MissingTenantFilterError):
        bind_tenant("select 1 from app.expected_workday", None, context)


def test_a_user_context_is_still_accepted() -> None:
    context = TenantContext(tenant_id=TENANT, user_id=UUID(int=7), role=UserRole.OWNER)
    assert bind_tenant(FILTERED, None, context) == {"tenant_id": TENANT}


def _coverage(employees: int, confident: int, gaps: tuple[ScheduleGap, ...] = ()) -> Coverage:
    return Coverage(
        tenant_id=TENANT,
        start=date(2026, 5, 27),
        end=date(2026, 8, 24),
        rows=employees * 90,
        employees=employees,
        employees_confident=confident,
        gaps=gaps,
    )


def test_coverage_is_the_share_of_people_the_detector_may_be_trusted_on() -> None:
    assert _coverage(79, 66).confident_ratio == pytest.approx(66 / 79)


def test_an_empty_roster_does_not_divide_by_zero() -> None:
    # A tenant that has not been promoted from the mirror yet has no employees at
    # all, and the report is read before that promotion exists.
    assert _coverage(0, 0).confident_ratio == 0.0


def test_the_report_names_each_gap_by_schedule_so_the_two_problems_stay_apart() -> None:
    # Seven people on a 12x36 whose rotation is not mirrored, and six on
    # exception tracking, need different answers. Collapsing them into "13
    # uncovered" is what would hide that.
    texto = relatorio(
        [
            _coverage(
                79,
                66,
                (
                    ScheduleGap(schedule="U-042 - P01 - 19h as 7h - Impar", employees=7, days=630),
                    ScheduleGap(schedule="U-000 - Seg a Sex (Supervisão)", employees=6, days=540),
                ),
            )
        ]
    )
    assert "66 de 79" in texto
    assert f"≥{CONFIDENCE_GATE}" in texto
    assert "7 em «U-042 - P01 - 19h as 7h - Impar»" in texto
    assert "6 em «U-000 - Seg a Sex (Supervisão)»" in texto


def test_a_roster_with_no_gap_says_so_instead_of_staying_silent() -> None:
    assert "nenhuma lacuna" in relatorio([_coverage(40, 40)])


def test_no_active_tenant_is_a_sentence_and_not_an_empty_string() -> None:
    assert relatorio([]) == "nenhum tenant ativo"
