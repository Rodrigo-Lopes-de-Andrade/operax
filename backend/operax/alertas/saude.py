"""The one door to `app.channel_health` — shared by the screen and the watcher.

`app.fn_record_channel_health` (migration `ch_channel_health`) holds the rule of
SPEC-CANAIS §7: `status_changed_at` only moves when the status changes. This
module holds the other half of the contract, the one the function cannot
enforce: the integration is reached **through the tenant** (an integration of
another customer is zero rows, function never evaluated), and `detail` is
always a sentence of the caller — a code at most — never the body or the error
message of a provider. The function writes whatever it is handed (finding of
the wave-1 guardian), so the discipline lives here and in the two callers:
`server/routers/canais.py` (connect, disconnect, re-saving the token) and
`operax/alertas/vigia.py` (the watcher).
"""

from __future__ import annotations

from typing import Any

from operax.core.tenant import TenantScope

#: `app.channel_health.status`, the three values the check constraint admits.
HEALTH_CONNECTED = "connected"
HEALTH_DISCONNECTED = "disconnected"
HEALTH_UNKNOWN = "unknown"

#: The measurement, through the single door. The `from app.integration …
#: tenant_id` is what binds the tenant. ⛔ `%(detail)s` is always a sentence of
#: the caller, never a provider's body or message.
RECORD_HEALTH_SQL = """
    select app.fn_record_channel_health(i.id, %(status)s, %(detail)s)
    from app.integration i
    where i.tenant_id = %(tenant_id)s
      and i.id = %(integration_id)s
"""


async def record_health(bound: TenantScope, integration_id: Any, status: str, detail: str) -> None:
    """Record one measurement for one integration of the scope's tenant, or raise."""
    await bound.execute(
        RECORD_HEALTH_SQL,
        {"integration_id": integration_id, "status": status, "detail": detail},
    )
    if await bound.fetchone() is None:
        raise RuntimeError("app.fn_record_channel_health não alcançou a integração do tenant")
