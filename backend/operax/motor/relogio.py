"""The tenant's clock — which day is "today", and what time it is there.

WHY THIS EXISTS
The engine ran with `date.today()` and `now()`, and both answer in the
container's zone, which on Railway is UTC. Measured on 2026-09-11, the first
night of the scheduled engine: at 21:00 in São Paulo the incremental run
started detecting the NEXT day — a day nobody had started — and flagged 56
people as `no_punches` for it. They were "corrected at the source" one by one
as they arrived at work the next morning. Nothing was corrected; the clock was
three hours ahead of the people.

The data was never in UTC. `app.expected_workday` holds local calendar dates
and local times, because the source declares them that way. Only the window and
the "is the shift over yet" comparison read the wrong clock. Both come from
here now, in the same zone the rows are written in.

WHY THE ZONE COMES FROM THE UNITS
`app.unit.timezone` already exists and is the only place the product records
where people actually work. A tenant with units in two zones would need the
engine to run per unit; today every unit of every tenant declares
`America/Sao_Paulo`, and the most common zone is the tenant's clock. Hardcoding
the zone would be right for exactly one customer.

`now` is naive on purpose: it is compared against `reference_date +
expected_exit`, which is a naive local timestamp, and a tz-aware value on one
side of that comparison would be an error the database catches late.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from operax.core.tenant import SystemContext, tenant_scope

#: When a tenant has no unit at all there is no better answer than the
#: container's own — which is what the engine did before this module existed.
FALLBACK_TIMEZONE = "UTC"

_TIMEZONE_SQL = """
select u.timezone
  from app.unit u
 where u.tenant_id = %(tenant_id)s and u.active
 group by u.timezone
 order by count(*) desc, u.timezone
 limit 1
"""


@dataclass(frozen=True)
class Clock:
    timezone: str
    #: Naive local wall time — the same shape as the expected times it is
    #: compared against.
    now: datetime

    @property
    def today(self) -> date:
        return self.now.date()

    @classmethod
    def at(cls, timezone: str, instant: datetime) -> Clock:
        """The clock of `timezone` at an absolute `instant` (tz-aware).

        Pure, so a test can pin 22:00 in São Paulo and prove the day did not
        flip to tomorrow with UTC.
        """
        local = instant.astimezone(ZoneInfo(timezone)).replace(tzinfo=None)
        return cls(timezone=timezone, now=local)


async def tenant_clock(context: SystemContext) -> Clock:
    async with tenant_scope(context) as scope:
        await scope.execute(_TIMEZONE_SQL, {})
        row = await scope.fetchone()
    timezone = row["timezone"] if row else FALLBACK_TIMEZONE
    return Clock.at(timezone, datetime.now(UTC))
