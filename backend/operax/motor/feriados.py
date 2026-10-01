"""The holiday calendar — the national load, and re-running a day that changed.

`app.holiday` is read by `jornada.py`, which turns a holiday into `holiday` for
a fixed Secullum week and leaves every rotation on its roster (owner's decision,
2026-09-28). This module does the two things around it that are not the rule:

LOADING THE NATIONAL DAYS
Nine fixed dates plus Good Friday (Easter − 2, owner's decision), for every
active tenant. `on conflict do nothing` on the partial unique index makes it
idempotent AND respects a national day somebody deactivated: the row is still
there, so the load does not bring it back. Carnival and Corpus Christi are
federal "ponto facultativo", not holidays — the owner registers them if the
customer observes them.

RE-RUNNING A DAY
The daily run rematerialises 90 days of expectation but detects and revokes
only the last 7. A holiday registered later than that fixes the expectation and
leaves the `no_punches` it explains active forever — 07/09/2026 is exactly that.
So a holiday date is re-run by itself: expectation, detection, revocation, in
that order, over a one-day window. Detection is part of it because it is what
writes the `punch_on_holiday` of whoever worked.

`python -m operax.motor` does it on its own for every holiday written in the
last two days (created, deactivated or reactivated — `updated_at`) whose date
its expectation window covers and its detection window does not. The first
national load writes every row now, so the next retroactive run corrects
07/09/2026 by itself. The command below is the manual form.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from operax.core.db import run_cli
from operax.core.tenant import SystemContext, active_tenants, tenant_scope
from operax.motor import deteccao, jornada, revogacao
from operax.motor.relogio import tenant_clock

TASK = "motor.feriados"

_FIXED: tuple[tuple[int, int, str], ...] = (
    (1, 1, "Confraternização Universal"),
    (4, 21, "Tiradentes"),
    (5, 1, "Dia do Trabalho"),
    (9, 7, "Independência do Brasil"),
    (10, 12, "Nossa Senhora Aparecida"),
    (11, 2, "Finados"),
    (11, 15, "Proclamação da República"),
    (11, 20, "Dia Nacional de Zumbi e da Consciência Negra"),
    (12, 25, "Natal"),
)

_LOAD_SQL = """
insert into app.holiday (tenant_id, reference_date, jurisdiction, name)
select %(tenant_id)s, d.reference_date, 'national', d.name
from unnest(%(dates)s::date[], %(names)s::text[]) as d(reference_date, name)
on conflict (tenant_id, reference_date) where unit_id is null do nothing
returning reference_date
"""

_LOAD_AUDIT_SQL = """
insert into app.audit_log (tenant_id, user_id, action, entity, entity_id, antes, depois)
values (%(tenant_id)s, null, 'insert', 'holiday', null, null, %(depois)s)
"""

#: Active or not: deactivating a holiday has to correct the day as well. And
#: only what was WRITTEN recently — created, deactivated or reactivated since
#: `since`. A holiday nobody touched was already reprocessed the day it was
#: written; re-detecting it every morning for 90 days would only rewrite old
#: days with whatever the engine is today. `updated_at` is kept by a trigger.
_DATES_SQL = """
select distinct h.reference_date
from app.holiday h
where h.tenant_id = %(tenant_id)s
  and h.reference_date between %(start)s::date and %(end)s::date
  and h.updated_at >= %(since)s
order by 1
"""

#: How far back "recently written" reaches. Two days, not one: a retroactive
#: run that did not happen (a failed deploy, a cron that died) would otherwise
#: lose the holiday written the day before it for good.
RECENT_WRITE = timedelta(days=2)


def easter(year: int) -> date:
    """Gregorian Easter Sunday (Meeus/Jones/Butcher). Pure arithmetic, no table."""
    golden = year % 19
    century, year_of_century = divmod(year, 100)
    leap_centuries, century_rest = divmod(century, 4)
    correction = (century + 8) // 25
    moon = (century - correction + 1) // 3
    epact = (19 * golden + century - leap_centuries - moon + 15) % 30
    leap_years, year_rest = divmod(year_of_century, 4)
    weekday = (32 + 2 * century_rest + 2 * leap_years - epact - year_rest) % 7
    shift = (golden + 11 * epact + 22 * weekday) // 451
    month, day = divmod(epact + weekday - 7 * shift + 114, 31)
    return date(year, month, day + 1)


def national_holidays(year: int) -> list[tuple[date, str]]:
    """The national days of one year, in date order."""
    days = [(date(year, month, day), name) for month, day, name in _FIXED]
    days.append((easter(year) - timedelta(days=2), "Sexta-feira da Paixão"))
    return sorted(days)


@dataclass(frozen=True, slots=True)
class Loaded:
    tenant_id: UUID
    inserted: tuple[date, ...]
    already: int


async def load(years: list[int]) -> list[Loaded]:
    """Write the national days of `years` for every active tenant, idempotently."""
    days = sorted(d for year in years for d in national_holidays(year))
    params = {"dates": [d for d, _ in days], "names": [n for _, n in days]}
    results: list[Loaded] = []
    for ctx in await active_tenants(TASK):
        async with tenant_scope(ctx) as scope:
            await scope.execute(_LOAD_SQL, params)
            inserted = tuple(sorted(row["reference_date"] for row in await scope.fetchall()))
            if inserted:
                await scope.execute(
                    _LOAD_AUDIT_SQL,
                    {
                        "depois": Jsonb(
                            {
                                "source": TASK,
                                "years": years,
                                "inserted": [d.isoformat() for d in inserted],
                            }
                        )
                    },
                )
        results.append(
            Loaded(tenant_id=ctx.tenant_id, inserted=inserted, already=len(days) - len(inserted))
        )
    return results


@dataclass(frozen=True, slots=True)
class Reprocessed:
    tenant_id: UUID
    day: date
    detection: deteccao.RunResult
    revocation: revogacao.RevocationResult


async def reprocess(context: SystemContext, day: date, *, mode: str, now: datetime) -> Reprocessed:
    """Expectation, detection and revocation of ONE day, in that order."""
    await jornada.materialize(context, day, day)
    # `backfill`: a one-day window over an old day is retroactive, whatever its
    # length says (see `deteccao.detect`).
    detected = await deteccao.detect(context, day, day, mode=mode, now=now, run_scope="backfill")
    revoked = await revogacao.reconcile(context, day, day, mode=mode, now=now)
    return Reprocessed(tenant_id=context.tenant_id, day=day, detection=detected, revocation=revoked)


async def run_dates(days: list[date], *, mode: str) -> list[Reprocessed]:
    """The manual form: the given dates, for every active tenant."""
    results: list[Reprocessed] = []
    for ctx in await active_tenants(TASK):
        clock = await tenant_clock(ctx)
        for day in sorted(set(days)):
            results.append(await reprocess(ctx, day, mode=mode, now=clock.now))
    return results


async def run_late(*, jornada_days: int, detection_days: int, mode: str) -> list[Reprocessed]:
    """Recently written holiday dates the expectation window covers and the
    detection window does not.

    The lower bound of detection is the retroactive week even when this run is
    the incremental one: a day inside that week is re-detected by the daily run
    anyway, and re-running it every 15 minutes would only add noise.
    """
    results: list[Reprocessed] = []
    for ctx in await active_tenants(TASK):
        clock = await tenant_clock(ctx)
        start = clock.today - timedelta(days=jornada_days - 1)
        end = clock.today - timedelta(days=max(detection_days, deteccao.BACKFILL_DAYS))
        if start > end:
            continue
        async with tenant_scope(ctx) as scope:
            # The tenant's wall clock, made an instant: `updated_at` is timestamptz.
            since = clock.now.replace(tzinfo=ZoneInfo(clock.timezone)) - RECENT_WRITE
            await scope.execute(_DATES_SQL, {"start": start, "end": end, "since": since})
            days = [row["reference_date"] for row in await scope.fetchall()]
        for day in days:
            results.append(await reprocess(ctx, day, mode=mode, now=clock.now))
    return results


def relatorio_carga(resultados: list[Loaded]) -> str:
    linhas = [
        f"tenant {r.tenant_id} · {len(r.inserted)} feriado(s) nacional(is) gravado(s), "
        f"{r.already} já existia(m)"
        for r in resultados
    ]
    return "\n".join(linhas) or "nenhum tenant ativo"


def relatorio(resultados: list[Reprocessed]) -> str:
    """Um dia por linha, em pt-BR porque quem lê é o operador."""
    linhas = [
        f"tenant {r.tenant_id} · {r.day} · modo {r.detection.mode}: "
        f"{r.detection.events} indício(s) ativo(s) · "
        f"{len(r.revocation.revoked)} revogado(s) · "
        f"{len(r.revocation.superseded)} substituído(s)"
        for r in resultados
    ]
    return "\n".join(linhas) or "nenhum feriado a reprocessar"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calendário de feriados do motor.")
    sub = parser.add_subparsers(dest="comando", required=True)

    carga = sub.add_parser("carga", help="grava os feriados nacionais em todo tenant ativo")
    carga.add_argument("--ano", type=int, action="append", required=True)

    repro = sub.add_parser(
        "reprocessar", help="refaz jornada, detecção e revogação de uma data, em todo tenant"
    )
    repro.add_argument("--data", type=date.fromisoformat, action="append", required=True)
    repro.add_argument("--modo", default="sombra", help="sombra (padrão) ou producao")
    args = parser.parse_args(argv)

    if args.comando == "carga":
        print(relatorio_carga(run_cli(load(args.ano))))
        return 0

    mode = deteccao.MODES.get(args.modo)
    if mode is None:
        print(f"erro: modo {args.modo!r} — use sombra ou producao")
        return 2
    print(relatorio(run_cli(run_dates(args.data, mode=mode))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
