"""Direct Postgres access, one connection pool per schema.

The backend talks to Postgres with `psycopg` and a `search_path` fixed per schema
(PostgREST is only for what comes from the browser). Building the pools does not
open a connection: the process must import without a live database.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from psycopg_pool import AsyncConnectionPool

from operax.core.config import get_settings

Schema = Literal["app", "secullum"]
SCHEMAS: tuple[Schema, ...] = ("app", "secullum")

_MAX_CONNECTIONS = 10


class SchemaPools:
    """Registry of pools keyed by schema."""

    def __init__(self, dsn: str) -> None:
        # min_size=0 so that opening the registry never depends on the database
        # being reachable; connections are created on demand.
        self._pools: dict[Schema, AsyncConnectionPool] = {
            schema: AsyncConnectionPool(
                dsn,
                open=False,
                min_size=0,
                max_size=_MAX_CONNECTIONS,
                kwargs={"options": f"-c search_path={schema}"},
                name=f"operax-{schema}",
            )
            for schema in SCHEMAS
        }

    def pool(self, schema: Schema) -> AsyncConnectionPool:
        return self._pools[schema]

    async def open(self) -> None:
        for pool in self._pools.values():
            await pool.open(wait=False)

    async def close(self) -> None:
        for pool in self._pools.values():
            await pool.close()


@lru_cache(maxsize=1)
def get_pools() -> SchemaPools:
    return SchemaPools(get_settings().database_url.get_secret_value())
