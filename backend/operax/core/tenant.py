"""Tenant context — the single chokepoint for every `service_role` access.

`service_role` ignores RLS, so the database will not catch a query that forgot
its tenant filter: this module has to. The tenant id is therefore never a value
the caller carries around. It lives inside a `TenantContext` resolved from the
authenticated token, and only `TenantScope` can bind it to a statement — refusing
any statement that does not carry it. Forgetting the filter is a runtime error,
not an oversight that reaches production data.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from psycopg import AsyncCursor
from psycopg.rows import DictRow, dict_row

from operax.core.db import Schema, get_pools

TENANT_PARAM = "tenant_id"
TENANT_PLACEHOLDER = f"%({TENANT_PARAM})s"
_TENANT_COLUMN = re.compile(rf"\b{TENANT_PARAM}\b")
_EXCERPT_LENGTH = 120


class TenantError(RuntimeError):
    """Base of every failure to establish or honour the tenant boundary."""


class MissingTenantContextError(TenantError):
    """A tenant-bound operation was attempted without a resolved tenant."""


class MissingTenantFilterError(TenantError):
    """A statement did not filter by tenant, or tried to choose its own tenant."""


class NoTenantMembershipError(TenantError):
    """The authenticated user belongs to no active tenant."""


class AmbiguousTenantMembershipError(TenantError):
    """The authenticated user belongs to more than one active tenant."""


class UserRole(StrEnum):
    """Mirrors the `app.user_role` enum (migration 02)."""

    OWNER = "owner"
    EXECUTIVE = "executive"
    HR = "hr"
    PERSONNEL = "personnel"
    REGIONAL_MANAGER = "regional_manager"
    UNIT_SUPERVISOR = "unit_supervisor"
    OPERATIONS_MANAGER = "operations_manager"
    ACCOUNTING = "accounting"
    VIEWER = "viewer"


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Who is asking, for which tenant, wearing which role.

    Validated at construction on purpose: type hints are not enforced at runtime,
    and a `None` sneaking in from an absent token claim is exactly the bug this
    whole module exists to prevent.
    """

    tenant_id: UUID
    user_id: UUID
    role: UserRole

    def __post_init__(self) -> None:
        _require_uuid("tenant_id", self.tenant_id)
        _require_uuid("user_id", self.user_id)
        if not isinstance(self.role, UserRole):
            raise MissingTenantContextError("role must be a UserRole resolved from the membership")


def _require_uuid(field: str, value: object) -> None:
    if not isinstance(value, UUID) or value.int == 0:
        raise MissingTenantContextError(
            f"{field} must be a resolved UUID, got {type(value).__name__}"
        )


def bind_tenant(
    statement: str,
    params: Mapping[str, Any] | None,
    context: TenantContext,
) -> dict[str, Any]:
    """Bind the context tenant to `statement`, or refuse to run it.

    Two conditions, both cheap and both about the same mistake:
    the statement must bind `%(tenant_id)s`, and it must mention a `tenant_id`
    column outside that placeholder — so `select %(tenant_id)s, * from app.employee`
    does not pass as filtered. The value itself never comes from the caller.
    """
    if not isinstance(context, TenantContext):
        raise MissingTenantContextError("a TenantContext is required to run any statement")
    if TENANT_PLACEHOLDER not in statement:
        raise MissingTenantFilterError(
            f"statement does not bind {TENANT_PLACEHOLDER}: {_excerpt(statement)}"
        )
    if not _TENANT_COLUMN.search(statement.replace(TENANT_PLACEHOLDER, "")):
        raise MissingTenantFilterError(
            f"statement binds {TENANT_PLACEHOLDER} but references no {TENANT_PARAM} "
            f"column: {_excerpt(statement)}"
        )
    if params is None:
        params = {}
    if not isinstance(params, Mapping):
        raise MissingTenantFilterError("named parameters are required so the tenant can be bound")
    if TENANT_PARAM in params:
        raise MissingTenantFilterError(
            f"{TENANT_PARAM} comes from the authenticated context, never from the caller"
        )
    return {**params, TENANT_PARAM: context.tenant_id}


def _excerpt(statement: str) -> str:
    flat = " ".join(statement.split())
    return flat if len(flat) <= _EXCERPT_LENGTH else f"{flat[:_EXCERPT_LENGTH]}..."


class TenantScope:
    """A cursor that only runs statements bound to one tenant."""

    def __init__(self, cursor: AsyncCursor[DictRow], context: TenantContext) -> None:
        self._cursor = cursor
        self._context = context

    @property
    def context(self) -> TenantContext:
        return self._context

    async def execute(
        self,
        statement: str,
        params: Mapping[str, Any] | None = None,
    ) -> AsyncCursor[DictRow]:
        return await self._cursor.execute(statement, bind_tenant(statement, params, self._context))

    async def fetchone(self) -> DictRow | None:
        return await self._cursor.fetchone()

    async def fetchall(self) -> list[DictRow]:
        return await self._cursor.fetchall()


@asynccontextmanager
async def tenant_scope(
    context: TenantContext,
    schema: Schema = "app",
) -> AsyncIterator[TenantScope]:
    """Open a tenant-bound cursor. The only sanctioned way to reach the data."""
    if not isinstance(context, TenantContext):
        raise MissingTenantContextError("a TenantContext is required to open a scope")
    async with get_pools().pool(schema).connection() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            yield TenantScope(cursor, context)


_MEMBERSHIP_SQL = """
    select tm.tenant_id, tm.role
    from app.tenant_member tm
    join app.tenant t on t.id = tm.tenant_id and t.active
    where tm.user_id = %(user_id)s
      and tm.active
"""


async def resolve_membership(user_id: UUID) -> TenantContext:
    """Bootstrap of the tenant context, from the `sub` claim of a validated token.

    The one query in the backend that runs without a tenant filter, because it is
    the query that establishes the tenant. It is filtered by the authenticated
    user and returns nothing but their membership. Everything downstream goes
    through `tenant_scope`.
    """
    pool = get_pools().pool("app")
    async with pool.connection() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(_MEMBERSHIP_SQL, {"user_id": user_id})
            memberships = await cursor.fetchall()

    if not memberships:
        raise NoTenantMembershipError(f"user {user_id} has no active tenant membership")
    if len(memberships) > 1:
        raise AmbiguousTenantMembershipError(
            f"user {user_id} is active in {len(memberships)} tenants; the request cannot pick one"
        )
    membership = memberships[0]
    return TenantContext(
        tenant_id=membership["tenant_id"],
        user_id=user_id,
        role=UserRole(membership["role"]),
    )
