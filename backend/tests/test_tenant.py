"""The chokepoint: with `service_role` there is no RLS to catch a missing filter.

Every test here is about the same failure mode — reaching data without a resolved
tenant — and about it being loud instead of silent.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from operax.core.tenant import (
    MissingTenantContextError,
    MissingTenantFilterError,
    TenantContext,
    TenantScope,
    UserRole,
    bind_tenant,
    tenant_scope,
)

TENANT_ID = UUID("22222222-2222-4222-8222-222222222222")
USER_ID = UUID("11111111-1111-4111-8111-111111111111")

SELECT = "select id from app.employee where tenant_id = %(tenant_id)s and unit_id = %(unit_id)s"
INSERT = "insert into app.employee (tenant_id, name) values (%(tenant_id)s, %(name)s)"


@pytest.fixture
def context() -> TenantContext:
    return TenantContext(tenant_id=TENANT_ID, user_id=USER_ID, role=UserRole.UNIT_SUPERVISOR)


class RecordingCursor:
    """Stands in for the database. Records what would have been executed."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def execute(self, statement: str, params: Any = None) -> RecordingCursor:
        self.calls.append((statement, params))
        return self


def test_context_refuses_an_unresolved_tenant() -> None:
    with pytest.raises(MissingTenantContextError, match="tenant_id"):
        TenantContext(tenant_id=None, user_id=USER_ID, role=UserRole.OWNER)  # type: ignore[arg-type]


def test_context_refuses_a_tenant_that_is_not_a_uuid() -> None:
    with pytest.raises(MissingTenantContextError):
        TenantContext(tenant_id=str(TENANT_ID), user_id=USER_ID, role=UserRole.OWNER)  # type: ignore[arg-type]


def test_context_refuses_a_role_outside_the_enum() -> None:
    with pytest.raises(MissingTenantContextError, match="role"):
        TenantContext(tenant_id=TENANT_ID, user_id=USER_ID, role="owner")  # type: ignore[arg-type]


def test_tenant_is_bound_from_the_context(context: TenantContext) -> None:
    params = bind_tenant(SELECT, {"unit_id": 7}, context)

    assert params == {"unit_id": 7, "tenant_id": TENANT_ID}


def test_insert_carrying_the_tenant_column_is_accepted(context: TenantContext) -> None:
    params = bind_tenant(INSERT, {"name": "Maria"}, context)

    assert params["tenant_id"] == TENANT_ID


def test_statement_without_the_tenant_placeholder_is_refused(context: TenantContext) -> None:
    with pytest.raises(MissingTenantFilterError, match="does not bind"):
        bind_tenant("select id from app.employee", None, context)


def test_placeholder_alone_does_not_count_as_a_filter(context: TenantContext) -> None:
    with pytest.raises(MissingTenantFilterError, match="references no tenant_id"):
        bind_tenant("select %(tenant_id)s, id from app.employee", None, context)


def test_caller_cannot_choose_the_tenant(context: TenantContext) -> None:
    other_tenant = UUID("33333333-3333-4333-8333-333333333333")

    with pytest.raises(MissingTenantFilterError, match="never from the caller"):
        bind_tenant(SELECT, {"unit_id": 7, "tenant_id": other_tenant}, context)


def test_positional_parameters_are_refused(context: TenantContext) -> None:
    with pytest.raises(MissingTenantFilterError, match="named parameters"):
        bind_tenant(SELECT, (7,), context)  # type: ignore[arg-type]


def test_binding_requires_a_context() -> None:
    with pytest.raises(MissingTenantContextError):
        bind_tenant(SELECT, {"unit_id": 7}, None)  # type: ignore[arg-type]


async def test_scope_never_reaches_the_database_without_a_filter(context: TenantContext) -> None:
    cursor = RecordingCursor()
    scope = TenantScope(cursor, context)  # type: ignore[arg-type]

    with pytest.raises(MissingTenantFilterError):
        await scope.execute("select id from app.employee")

    assert cursor.calls == []


async def test_scope_executes_with_the_tenant_injected(context: TenantContext) -> None:
    cursor = RecordingCursor()
    scope = TenantScope(cursor, context)  # type: ignore[arg-type]

    await scope.execute(SELECT, {"unit_id": 7})

    assert cursor.calls == [(SELECT, {"unit_id": 7, "tenant_id": TENANT_ID})]


async def test_scope_never_hands_back_the_cursor(context: TenantContext) -> None:
    # `psycopg` returns the cursor from execute. Handing it back would let
    # `cur = await cur.execute(...)` — the idiomatic form — walk around the wrapper
    # and reach every tenant with the next statement.
    cursor = RecordingCursor()
    scope = TenantScope(cursor, context)  # type: ignore[arg-type]

    returned = await scope.execute(SELECT, {"unit_id": 7})

    assert returned is None
    assert returned is not cursor
    assert not hasattr(returned, "execute")


async def test_opening_a_scope_requires_a_resolved_context() -> None:
    with pytest.raises(MissingTenantContextError):
        async with tenant_scope(None):  # type: ignore[arg-type]
            pass
