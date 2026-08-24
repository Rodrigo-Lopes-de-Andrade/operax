"""The executor — runs the chosen metric **as the person who asked**.

This is the second half of rule 9. The catalogue keeps the model from inventing a
query; this keeps a correct query from returning rows the asker cannot see. It
runs under `user_scope`, so the same policies that guard the browser decide what
comes back — the assistant has no privilege of its own, and a metric asked by a
supervisor answers with the supervisor's units without a single line here saying
so.

WHAT REACHES THE SQL TEXT, AND WHAT DOES NOT
The target name and the column names come from `catalogo.BINDINGS`, a frozen map
in code, reached through a metric loaded from `app.metric`. Nothing the model
said and nothing the user typed is ever interpolated: every value travels as a
bound parameter. The db-test compiles the statement each metric generates against
the real schema, which is what catches a column that stopped existing.

WHERE THE STATEMENT IS BUILT
In `catalogo.py`, not here, and for a reason that is not tidiness: `build` is
pure, and `scripts/91_teste_catalogo.py` compiles what it produces against the
real schema on every `make db-test`. A builder that imports the driver is a
builder no test outside the venv can reach.
"""

from __future__ import annotations

from typing import Any

from operax.agente.catalogo import MAX_ROWS, Choice, build
from operax.core.tenant import TenantContext, user_scope

_CATALOG_SQL = """
select code, title, description, target_view, dimensions, filters, domain
from app.metric
where active
order by code
"""

_PERMISSIONS_SQL = """
select util.can_see_domain(%(tenant_id)s, 'pii')          as pii,
       util.can_see_domain(%(tenant_id)s, 'compensation') as compensation,
       util.can_see_domain(%(tenant_id)s, 'health')       as health,
       util.can_see_domain(%(tenant_id)s, 'disciplinary') as disciplinary
"""


async def load_catalog(tenant: TenantContext) -> list[dict[str, Any]]:
    """O catálogo cru, lido como o usuário. `metric_read` só mostra o que está ativo."""
    async with user_scope(tenant) as scope:
        await scope.execute(_CATALOG_SQL)
        return [dict(row) for row in await scope.fetchall()]


async def domains(tenant: TenantContext) -> frozenset[str]:
    """Os domínios sensíveis que esta pessoa alcança, perguntados ao banco.

    Ao banco, e não ao papel: a autorização tem três eixos independentes, e
    `if role == 'hr'` não é um deles.
    """
    async with user_scope(tenant) as scope:
        await scope.execute(_PERMISSIONS_SQL, {"tenant_id": tenant.tenant_id})
        row = await scope.fetchone()
    sensiveis = ("pii", "compensation", "health", "disciplinary")
    return frozenset(nome for nome in sensiveis if row[nome])


async def execute(tenant: TenantContext, choice: Choice, *, limit: int = MAX_ROWS) -> list[dict]:
    """Roda a métrica como o usuário. A RLS decide o que volta."""
    query = build(choice, limit=limit)
    async with user_scope(tenant) as scope:
        await scope.execute(query.sql, query.parameters)
        return [dict(row) for row in await scope.fetchall()]
