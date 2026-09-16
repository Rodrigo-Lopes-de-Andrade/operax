"""The watcher that asks — and never reconnects (SPEC-CANAIS §7).

The webhook goes silent exactly when it matters most: while the transport is
alive the platform reports in seconds; when it dies, no event arrives — and "no
event" is indistinguishable from "all fine". So this task ASKS the platform, on
a schedule, what it has registered for each tenant's bot, and records the answer
in `app.channel_health` with its age. `python -m operax.alertas.vigia`.

WHAT IT DECIDES, FROM `getWebhookInfo`
* `url` equal to the `webhook_url` this backend registered, no delivery error in
  the last 24 h, fewer than 100 updates waiting → `connected`;
* `url` empty → `disconnected`, "webhook ausente"; `url` different →
  `disconnected`, "webhook aponta para outro endereço" — the platform is
  delivering to a path this database does not know;
* `last_error_date` in the last 24 h → `disconnected`, "Telegram registrou erro
  de entrega" — **without** their message: it can echo the URL, and the URL
  carries the path token (`telegram._mask` already hides it, and it still does
  not go to the screen);
* the platform refused or could not be asked → `unknown`, with the refusal
  code, never a body.

Every `detail` is a sentence of this module. `app.fn_record_channel_health`
writes what it is handed, so this is where "never the provider's body" is kept
(`operax/alertas/saude.py`).

⛔ THE WATCHER DOES NOT RECONNECT
No `setWebhook` here, in any branch, ever — `tests/test_canais_vigia.py`
asserts it over every request the transport saw, in every scenario. "Religar
sozinho uma conexão que caiu por bloqueio da plataforma é a receita para
transformar uma suspensão temporária em definitiva" (§7). What this task
produces is a status and an age; what to do about it is the administrator's,
from the Conexões screen, with the reason in front of them.

Scheduling this on Railway is the owner's action, like the two engine crons.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx

from operax.alertas.provedores import telegram
from operax.alertas.provedores.base import InvalidCredentialError, verification_client
from operax.alertas.saude import (
    HEALTH_CONNECTED,
    HEALTH_DISCONNECTED,
    HEALTH_UNKNOWN,
    record_health,
)
from operax.core.db import run_cli
from operax.core.tenant import SystemContext, active_tenants, tenant_scope
from operax.core.vault import read_secret

TASK = "channel-health"

#: The vault key `save_credential` used for the bot token — derived from
#: `FieldSpec.secret`, the same way `canais._BOT_TOKEN_KEY` is.
[BOT_TOKEN_KEY] = [spec.name for spec in telegram.FIELDS if spec.secret]

#: A delivery error younger than this is a channel that is not delivering.
ERROR_WINDOW = timedelta(hours=24)
#: Updates the platform is holding because we did not take them. Below this the
#: queue is noise; at it, something is not being answered.
PENDING_CEILING = 100

#: The active bot of the tenant and the address this backend registered for it.
#: `tenant_scope`; the cut is `%(tenant_id)s`.
_BOT_SQL = """
    select i.id, i.config ->> 'webhook_url' as webhook_url
    from app.integration i
    where i.tenant_id = %(tenant_id)s
      and i.active
      and i.provider = %(provider)s
"""


@dataclass(frozen=True, slots=True)
class HealthResult:
    tenant_id: UUID
    status: str
    detail: str


def judge(info: telegram.WebhookInfo, webhook_url: str | None, now: datetime) -> tuple[str, str]:
    """`(status, detail)` from what the platform said and what we registered."""
    if info.url is None:
        return HEALTH_DISCONNECTED, "webhook ausente"
    if info.url != webhook_url:
        return HEALTH_DISCONNECTED, "webhook aponta para outro endereço"
    if info.last_error_date is not None and now - info.last_error_date < ERROR_WINDOW:
        return HEALTH_DISCONNECTED, "Telegram registrou erro de entrega"
    if info.pending_update_count >= PENDING_CEILING:
        return HEALTH_DISCONNECTED, "updates acumulados sem entrega no Telegram"
    return HEALTH_CONNECTED, "webhook registrado, sem erro de entrega"


async def check_tenant(context: SystemContext, http: httpx.AsyncClient) -> HealthResult | None:
    """Measure one tenant's bot and record it. `None` when the tenant has no bot.

    The token lives in a local between the vault and the call, and the HTTP
    happens with no transaction open — the same shape as `canais.py`.
    """
    async with tenant_scope(context) as bound:
        await bound.execute(_BOT_SQL, {"provider": telegram.NAME})
        bot = await bound.fetchone()
        if bot is None:
            return None
        token = await read_secret(bound, bot["id"], BOT_TOKEN_KEY)

    if token is None:
        status, detail = HEALTH_UNKNOWN, "token do bot ausente no cofre"
    else:
        try:
            info = await telegram.webhook_info(token, http)
        except InvalidCredentialError as refusal:
            # Only the code: the exception is born `from None` in the provider.
            status, detail = HEALTH_UNKNOWN, f"getWebhookInfo: {refusal.code}"
        else:
            status, detail = judge(info, bot["webhook_url"], datetime.now(UTC))

    async with tenant_scope(context) as bound:
        await record_health(bound, bot["id"], status, detail)
    return HealthResult(tenant_id=context.tenant_id, status=status, detail=detail)


async def run(http: httpx.AsyncClient) -> list[HealthResult]:
    results: list[HealthResult] = []
    for context in await active_tenants(TASK):
        result = await check_tenant(context, http)
        if result is not None:
            results.append(result)
    return results


def relatorio(resultados: list[HealthResult]) -> str:
    return (
        "\n".join(f"tenant {r.tenant_id}: {r.status} — {r.detail}" for r in resultados)
        or "nenhum tenant com bot ativo"
    )


async def _run_with_client() -> list[HealthResult]:
    # `verification_client`: the token is in the URL, and that is where the
    # `httpx` log is muted (gate 3).
    async with verification_client() as http:
        return await run(http)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pergunta ao Telegram a saúde do webhook de cada bot e grava. Não religa."
    )
    parser.parse_args(argv)
    print(relatorio(run_cli(_run_with_client())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
