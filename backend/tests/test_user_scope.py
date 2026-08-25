"""Acting as the user: the alternative to writing the security rule twice.

`TenantScope` exists because `service_role` has no RLS to catch a missing filter.
`UserScope` exists because some questions — which units may this person see, which
sensitive domain does this role reach — already have an answer in the policies,
and copying it into Python is how the two answers start to disagree.

These tests are about the mechanic that makes the policies apply: the transaction
has to stop being `service_role` before the first statement runs.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest

from operax.core.tenant import (
    MissingTenantContextError,
    MissingTenantFilterError,
    TenantContext,
    UserRole,
    UserScope,
    user_scope,
)

TENANT_ID = UUID("22222222-2222-4222-8222-222222222222")
USER_ID = UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture
def context() -> TenantContext:
    return TenantContext(tenant_id=TENANT_ID, user_id=USER_ID, role=UserRole.UNIT_SUPERVISOR)


class RecordingCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def execute(self, statement: str, params: Any = None) -> RecordingCursor:
        self.calls.append((statement, params))
        return self


class StubCursorContext:
    def __init__(self, cursor: RecordingCursor) -> None:
        self._cursor = cursor

    async def __aenter__(self) -> RecordingCursor:
        return self._cursor

    async def __aexit__(self, *exc: object) -> None:
        return None


class StubConnection:
    def __init__(self, cursor: RecordingCursor) -> None:
        self._cursor = cursor

    def transaction(self) -> StubCursorContext:
        return StubCursorContext(self._cursor)

    def cursor(self, **_: Any) -> StubCursorContext:
        return StubCursorContext(self._cursor)

    async def __aenter__(self) -> StubConnection:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class StubPool:
    def __init__(self, cursor: RecordingCursor) -> None:
        self._cursor = cursor

    def connection(self) -> StubConnection:
        return StubConnection(self._cursor)


class StubPools:
    """Stands in for the registry: no socket, and it records which pool was used."""

    def __init__(self, cursor: RecordingCursor) -> None:
        self._cursor = cursor
        self.asked_for: list[str] = []

    def pool(self, schema: str) -> StubPool:
        self.asked_for.append(schema)
        return StubPool(self._cursor)


async def test_scope_runs_the_statement_without_injecting_a_tenant(
    context: TenantContext,
) -> None:
    # No tenant placeholder is demanded here, and that is the point: with RLS in
    # force a cross-tenant read is impossible, not merely unfiltered. Demanding
    # the filter anyway would be a ritual, and rituals get satisfied by
    # tautologies.
    cursor = RecordingCursor()
    scope = UserScope(cursor, context)  # type: ignore[arg-type]

    await scope.execute("select id from app.employee where id = %(id)s", {"id": 7})

    assert cursor.calls == [("select id from app.employee where id = %(id)s", {"id": 7})]


async def test_scope_never_hands_back_the_cursor(context: TenantContext) -> None:
    cursor = RecordingCursor()
    scope = UserScope(cursor, context)  # type: ignore[arg-type]

    returned = await scope.execute("select 1")

    assert returned is None
    assert not hasattr(returned, "execute")


async def test_positional_parameters_are_refused(context: TenantContext) -> None:
    cursor = RecordingCursor()
    scope = UserScope(cursor, context)  # type: ignore[arg-type]

    with pytest.raises(MissingTenantFilterError):
        await scope.execute("select id from app.employee where id = %s", (7,))  # type: ignore[arg-type]

    assert cursor.calls == []


async def test_opening_a_scope_requires_a_resolved_context() -> None:
    with pytest.raises(MissingTenantContextError):
        async with user_scope(None):  # type: ignore[arg-type]
            pass


async def test_the_transaction_stops_being_service_role_before_anything_is_read(
    context: TenantContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first statement on the connection is the one that drops the privilege.

    If it ever ran second, the read that matters would already have gone through
    as `service_role` — with every policy bypassed and nothing to show for it,
    because the result would look perfectly normal.
    """
    cursor = RecordingCursor()
    monkeypatch.setattr("operax.core.tenant.get_pools", lambda: StubPools(cursor))

    async with user_scope(context) as scope:
        await scope.execute("select id from app.employee")

    first_statement, first_params = cursor.calls[0]
    assert "set_config('role', 'authenticated', true)" in first_statement
    assert json.loads(first_params["claims"]) == {
        "sub": str(USER_ID),
        "role": "authenticated",
    }
    assert first_params["sub"] == str(USER_ID)
    # Local to the transaction, so the pooled connection goes back as it came.
    assert first_statement.count("true)") == 3
    assert cursor.calls[1][0] == "select id from app.employee"


async def test_the_schema_pool_is_the_one_that_was_asked_for(
    context: TenantContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    cursor = RecordingCursor()
    pools = StubPools(cursor)
    monkeypatch.setattr("operax.core.tenant.get_pools", lambda: pools)

    async with user_scope(context, schema="secullum"):
        pass

    assert pools.asked_for == ["secullum"]
