"""The vault, per tenant — where a credential's value lives, and the only way in.

`app.integration_secret` holds a pointer (`vault_id`) and nothing else; the value
sits in `vault.secrets`, encrypted by the `supabase_vault` extension (0.3.1 in
the rehearsal database and in production alike). *"Nenhum role do painel lê esta
tabela — nem owner"*: the pointer table has no policy, so every access is
`service_role`, and every access therefore goes through `TenantScope` — the
statements below all bind `%(tenant_id)s`, cut through the `join` with
`app.integration`, because the pointer table has no `tenant_id` of its own.

ONE TRANSACTION, THE CALLER'S
`store_secret` takes the caller's scope instead of opening one. `vault.create_secret`
is an ordinary row in `vault.secrets`: if the pointer insert, the audit line or
anything after it fails, the row must go with them, and that only happens when
all of it shares a transaction. The `insert … select vault.create_secret(…)`
shape also means a wrong tenant creates nothing — zero rows selected, the
function never evaluated.

⛔ THE VALUE NEVER LEAVES THIS MODULE EXCEPT THROUGH `read_secret`
It goes into the statement as a bound parameter, never interpolated; it is not
logged, not part of any exception, and not returned by `store_secret`. The
secret's `name` in the vault is deterministic per `(integration_id, key)` and
`unique`, so saving twice updates the same row — proved by the row count of
`vault.secrets` in `scripts/97_teste_canais.py`.
"""

from __future__ import annotations

from uuid import UUID

from operax.core.tenant import TenantScope


class SecretNotStoredError(RuntimeError):
    """The integration is not this tenant's, so no secret was written."""


#: Update in place when the pointer exists. The data-modifying CTE touches the
#: pointer's `updated_at` and hands the `vault_id` to `vault.update_secret` in
#: the same statement; zero rows out of the CTE means zero calls to the vault.
_UPDATE_SQL = """
    with pointer as (
        update app.integration_secret s
           set updated_at = now()
          from app.integration i
         where i.id = s.integration_id
           and i.tenant_id = %(tenant_id)s
           and s.integration_id = %(integration_id)s
           and s.key = %(key)s
        returning s.vault_id
    )
    select vault.update_secret(p.vault_id, %(value)s), p.vault_id
    from pointer p
"""

#: Create when it does not: the `select` only yields a row when the integration
#: belongs to the tenant, and `vault.create_secret` is evaluated per row yielded.
#: The vault `name` is `unique`, and it is built here, from the pointer's own
#: key, so that a second save finds the row above instead of colliding here.
_CREATE_SQL = """
    insert into app.integration_secret (integration_id, key, vault_id)
    select i.id,
           %(key)s,
           vault.create_secret(
               %(value)s,
               'app.integration_secret/' || i.id || '/' || %(key)s,
               %(description)s
           )
    from app.integration i
    where i.id = %(integration_id)s
      and i.tenant_id = %(tenant_id)s
    returning vault_id
"""

#: The one read. Same `join`, same tenant cut, through `vault.decrypted_secrets`.
_READ_SQL = """
    select d.decrypted_secret
    from app.integration_secret s
    join app.integration i on i.id = s.integration_id
    join vault.decrypted_secrets d on d.id = s.vault_id
    where i.tenant_id = %(tenant_id)s
      and s.integration_id = %(integration_id)s
      and s.key = %(key)s
"""

_DESCRIPTION = "OperaX: credencial de integração por tenant; o ponteiro é app.integration_secret"


async def store_secret(scope: TenantScope, integration_id: UUID, key: str, value: str) -> None:
    """Put `value` in the vault behind the pointer `(integration_id, key)`.

    Updates the existing secret when the pointer exists; creates secret and
    pointer otherwise. Runs in the caller's transaction. Raises
    `SecretNotStoredError` when the integration is not the scope's tenant's —
    silently storing nothing would be the one failure mode worse than a leak.
    """
    params = {"integration_id": integration_id, "key": key, "value": value}
    await scope.execute(_UPDATE_SQL, params)
    if await scope.fetchone() is not None:
        return
    await scope.execute(_CREATE_SQL, {**params, "description": _DESCRIPTION})
    if await scope.fetchone() is None:
        raise SecretNotStoredError(
            f"integration {integration_id} is not the scope's tenant's; nothing was stored"
        )


async def read_secret(scope: TenantScope, integration_id: UUID, key: str) -> str | None:
    """The value behind the pointer, or `None` when there is no pointer.

    Two consumers, and both use the value in one place and drop it: the
    template sync (`POST /canais/templates/sincronizar`, C2b), which reads the
    Cloud API token into a local, closes the scope, hands the token to the
    Graph API call and never writes it — not to the audit line, not to the log,
    not to the response; and, from C5 on, the sender, which needs the token to
    deliver. The panel never reads it: `GET /canais/credencial` says that a
    credential exists, not what it is. `scripts/97_teste_canais.py` proves the
    round trip and the tenant cut against the real vault.
    """
    await scope.execute(_READ_SQL, {"integration_id": integration_id, "key": key})
    row = await scope.fetchone()
    return None if row is None else row["decrypted_secret"]
