"""Tenant context — the chokepoint every `service_role` access goes through.

`service_role` ignores RLS, so the database will not catch a query that forgot
its tenant filter. The tenant id is therefore never a value the caller carries
around: it lives inside a `TenantContext` resolved from the authenticated token,
and only `TenantScope` binds it to a statement.

What this module does *not* prove. The check in `bind_tenant` is syntactic: it
proves the statement binds the context tenant and names a `tenant_id` column
somewhere, never that the predicate actually restricts rows. Three shapes pass
the check and still read every tenant — placeholder and column living inside an
SQL comment, a tautological predicate (`where %(tenant_id)s is not null`), and
the unfiltered side of a join or union. Read it as cheap lint on the way out, not
as the security boundary. The boundary is a non-superuser role with RLS enabled
and the tenant set per transaction; that is a policy and grant decision, pending
outside this module.
"""

from __future__ import annotations

import json
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

    `role` is not authorization on its own. Authorization has three independent
    axes (migration 02): tenant, scope of companies and units (`app.user_scope`)
    and sensitive domain (`app.domain_permission`). `if role == "hr"` is not a
    gate for PII — the scope and domain checks land in S2.
    """

    tenant_id: UUID
    user_id: UUID
    role: UserRole

    def __post_init__(self) -> None:
        _require_uuid("tenant_id", self.tenant_id)
        _require_uuid("user_id", self.user_id)
        if not isinstance(self.role, UserRole):
            raise MissingTenantContextError("role must be a UserRole resolved from the membership")


@dataclass(frozen=True, slots=True)
class SystemContext:
    """The tenant binding of a scheduled task. There is no person behind it.

    Every other access to the data carries a `TenantContext` resolved from a
    validated token. The engine has no token: it runs on a timer, for one tenant
    at a time, and still must not be allowed to write a statement that forgot its
    tenant. So it binds through the same chokepoint with a context that says out
    loud what it is, instead of borrowing a user identity it does not have.

    `task` is not decoration. It is what a query in `pg_stat_activity` and a line
    in a log have to identify, and inventing a fake `user_id` would have made
    both lie.
    """

    tenant_id: UUID
    task: str

    def __post_init__(self) -> None:
        _require_uuid("tenant_id", self.tenant_id)
        if not isinstance(self.task, str) or not self.task.strip():
            raise MissingTenantContextError("task must name the scheduled task that is running")


# What `bind_tenant` and `tenant_scope` accept. `UserScope` deliberately does
# not: it sets a JWT claim, and a scheduled task has no `sub` to set.
Bound = TenantContext | SystemContext


def _require_uuid(field: str, value: object) -> None:
    if not isinstance(value, UUID) or value.int == 0:
        raise MissingTenantContextError(
            f"{field} must be a resolved UUID, got {type(value).__name__}"
        )


def bind_tenant(
    statement: str,
    params: Mapping[str, Any] | None,
    context: Bound,
) -> dict[str, Any]:
    """Bind the context tenant to `statement`, or refuse to run it.

    Two syntactic conditions, both cheap and both about the same mistake: the
    statement must bind `%(tenant_id)s`, and it must name a `tenant_id` column
    outside that placeholder — so `select %(tenant_id)s, * from app.employee` does
    not pass. The value itself never comes from the caller.

    This catches the forgotten filter, not a wrong one. It cannot see that the
    binding sits inside an SQL comment, that the predicate is a tautology, or that
    one side of a join or union is unfiltered: all three pass here and read every
    tenant. Reviewing the predicate is still the author's job.
    """
    if not isinstance(context, TenantContext | SystemContext):
        raise MissingTenantContextError("a resolved context is required to run any statement")
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
    """A cursor wrapper that only runs statements binding one tenant.

    The wrapped cursor never leaves this object: `psycopg` returns the cursor from
    `execute`, and handing it back would let the idiomatic
    `cur = await cur.execute(...)` walk straight around the wrapper. Read results
    through `fetchone` and `fetchall`.
    """

    def __init__(self, cursor: AsyncCursor[DictRow], context: Bound) -> None:
        self._cursor = cursor
        self._context = context

    @property
    def context(self) -> Bound:
        return self._context

    async def execute(
        self,
        statement: str,
        params: Mapping[str, Any] | None = None,
    ) -> None:
        await self._cursor.execute(statement, bind_tenant(statement, params, self._context))

    async def fetchone(self) -> DictRow | None:
        return await self._cursor.fetchone()

    async def fetchall(self) -> list[DictRow]:
        return await self._cursor.fetchall()


@asynccontextmanager
async def tenant_scope(
    context: Bound,
    schema: Schema = "app",
) -> AsyncIterator[TenantScope]:
    """Open a tenant-bound cursor. The only sanctioned way to reach the data."""
    if not isinstance(context, TenantContext | SystemContext):
        raise MissingTenantContextError("a resolved context is required to open a scope")
    async with get_pools().pool(schema).connection() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            yield TenantScope(cursor, context)


# `SET` takes no placeholder, `set_config` does — and the third argument makes
# it local, so the transaction end puts the connection back the way the pool
# handed it over. Both spellings of the claim are written because `auth.uid()`
# has read both over the life of the Supabase project, and a helper that
# silently returns null would not fail: it would answer "no rows".
_ACT_AS_USER_SQL = """
    select set_config('role', 'authenticated', true),
           set_config('request.jwt.claims', %(claims)s, true),
           set_config('request.jwt.claim.sub', %(sub)s, true)
"""


class UserScope:
    """A cursor that runs as the authenticated user, with RLS in force.

    The counterpart of `TenantScope`, and the answer to a question it cannot
    answer. `service_role` ignores RLS, so a statement that must respect the
    user's scope of companies and units, or the sensitive-domain matrix, would
    have to re-implement `util.can_see_unit` and `util.can_see_domain` here — the
    same security rule written twice, in two languages, drifting apart at the
    first policy change.

    So the transaction stops being `service_role` instead: it takes the
    `authenticated` role and the `sub` of the validated token, and the policies
    that already guard the browser guard this connection too. `util.can_see_*`
    become callable, because `auth.uid()` now answers.

    No tenant placeholder is required here, and that is deliberate rather than an
    omission: with RLS in force a cross-tenant read is not a forgotten filter, it
    is impossible. Demanding the filter anyway would be a ritual, and rituals get
    satisfied by tautologies.

    What this does not do: it does not downgrade the connection permanently. The
    role is set `local`, so it lives exactly as long as the transaction. Anything
    that genuinely needs to bypass RLS — the membership bootstrap, an
    administrative write — stays on `tenant_scope`.
    """

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
    ) -> None:
        if params is not None and not isinstance(params, Mapping):
            raise MissingTenantFilterError("named parameters are required")
        await self._cursor.execute(statement, params or {})

    async def fetchone(self) -> DictRow | None:
        return await self._cursor.fetchone()

    async def fetchall(self) -> list[DictRow]:
        return await self._cursor.fetchall()


@asynccontextmanager
async def user_scope(
    context: TenantContext,
    schema: Schema = "app",
) -> AsyncIterator[UserScope]:
    """Open a cursor that the database sees as the user who asked."""
    if not isinstance(context, TenantContext):
        raise MissingTenantContextError("a TenantContext is required to open a scope")
    claims = json.dumps({"sub": str(context.user_id), "role": "authenticated"})
    async with get_pools().pool(schema).connection() as connection:
        # `set_config(..., local)` needs a transaction to be local to.
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    _ACT_AS_USER_SQL,
                    {"claims": claims, "sub": str(context.user_id)},
                )
                yield UserScope(cursor, context)


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


# The second — and last — statement in the backend that runs without a tenant
# filter. It is what a scheduled task uses to learn which tenants exist before
# binding itself to one of them, and it reads nothing but ids of active tenants.
# Keeping it in this file, beside `resolve_membership`, is deliberate: an auditor
# looking for "what runs unfiltered?" should find every answer in one place.
_ACTIVE_TENANTS_SQL = """
    select t.id
    from app.tenant t
    where t.active
    order by t.slug
"""


async def active_tenants(task: str) -> list[SystemContext]:
    """One `SystemContext` per active tenant, for a task that runs on a timer."""
    pool = get_pools().pool("app")
    async with pool.connection() as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(_ACTIVE_TENANTS_SQL)
            rows = await cursor.fetchall()
    return [SystemContext(tenant_id=row["id"], task=task) for row in rows]
