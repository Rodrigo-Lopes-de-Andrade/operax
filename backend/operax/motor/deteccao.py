"""The detector — punches against expectation, one row per fact.

`app.expected_workday` says what was supposed to happen; `app.batida_marcacao`
says what the clock recorded. This module is the subtraction, and every choice in
it exists because the source hands over **raw punches**: the OperaX computes, and
a computation that looks precise and is wrong is worse than no number at all.

WHY THE WHOLE ALGORITHM IS ONE STATEMENT
The same reason as `jornada.py`: a Python loop over a hundred thousand
person-days would pull the punches across the wire to do arithmetic the database
already does, and — more importantly — it could not be proved against a real
schema by `scripts/94_teste_deteccao.py`, which extracts this SQL from here and
runs it. SQL that cannot be checked against the database is SQL that only fails
in production.

THE SIGN CONVENTION IS THE PRODUCT
Positive is surplus (worked beyond), negative is shortfall (worked short).
`sum(minutes)` answers "net balance" and `sum(abs(minutes))` answers "minutes of
deviation". Without one convention the two numbers would need different queries
and would drift apart — and they are the two numbers on the dashboard.

WHAT IS **NOT** DECIDED HERE
Whether a type counts towards the KPIs. Every active type is always emitted, and
`app.deviation_type_config.counts_as_deviation` is applied by the views. That is
what makes "the customer only wants overtime counted" an `UPDATE` instead of a
reprocessing of history.

THREE THINGS THE MIRROR SAYS THAT THIS ENGINE DELIBERATELY IGNORES
Naming them is the point: shadow mode exists to classify divergences, and these
are the first three to look at when a false positive shows up.

  `secullum."Batida"."Folga"`, `."Neutro"`, `."Compensado"` — the source's own
      day-level flags. The expectation here comes from `app.expected_workday` and
      only from it; two sources for "was this a working day" is one too many, and
      choosing between them is a product decision, not a detector's.
  `."Abono2".."Abono4"` — free text excusing the day. Reading it would make the
      engine parse prose written by whoever typed it.
  `outside_perimeter` — no coordinate is mirrored. The type exists in the
      catalogue and this engine never emits it.

CONFIDENCE GATES THE ALERT, NOT THE DETECTION
SPEC §3.1: a line below 80 enters the dashboard marked "escala não confirmada"
and never raises an automatic alert. So detection still runs on it. The one place
it is load-bearing here is `no_punches`, which requires a declared
`workload_minutes`: you cannot say somebody missed a shift you were unable to
describe, and a 12x36 whose rotation is not mirrored has no describable shift.
Without that guard every rest day of every rotation worker would be a missed
shift, which is the false-positive flood the whole shadow stage exists to avoid.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from operax.core.db import run_cli
from operax.core.tenant import SystemContext, active_tenants, tenant_scope
from operax.motor.regras import DETECT_SQL
from operax.motor.relogio import tenant_clock

TASK = "motor.deteccao"

#: SPEC §3.5b: the incremental pass looks at the current day only; the retroactive
#: pass at the last week, because a punch corrected yesterday belongs to a day
#: before it.
INCREMENTAL_DAYS = 1
BACKFILL_DAYS = 7

#: Stamped on every `app.detection_run`. It is what makes "this event came from a
#: version of the engine that had the tolerance bug" answerable.
#:
#: v2 (2026-09-11): the four absence types wait for the shift to close, and the
#: window is the tenant's day. Every `no_punches` stamped v1 on a day that was
#: still in progress is a transient of the old engine, not a fact about anyone.
ENGINE_VERSION = "deteccao.v2"

#: The CLI speaks pt-BR because the operator does; the column speaks the schema.
MODES = {
    "sombra": "shadow",
    "producao": "production",
    "shadow": "shadow",
    "production": "production",
}


# ---------------------------------------------------------------------------
# The engine, as one statement
# ---------------------------------------------------------------------------


_OPEN_RUN_SQL = """
insert into app.detection_run
  (tenant_id, mode, period_start, period_end, engine_version, scope)
values (%(tenant_id)s, %(mode)s, %(start)s, %(end)s, %(engine_version)s, %(scope)s)
returning id
"""

_CLOSE_RUN_SQL = """
update app.detection_run
   set status = %(status)s,
       finished_at = now(),
       events_detected = %(events_detected)s,
       error = %(error)s
 where id = %(run_id)s and tenant_id = %(tenant_id)s
"""

#: What the run produced, read back from the events it stamped. Counting the rows
#: the statement touched would count an updated row as a new one, and the number
#: that matters is how many active deviations the window holds.
_TOTALS_SQL = """
select count(*)::int                                            as events,
       count(*) filter (where d.minutes > 0)::int               as surplus,
       count(*) filter (where d.minutes < 0)::int               as shortfall,
       coalesce(sum(abs(d.minutes)), 0)::int                    as deviation_minutes,
       count(distinct d.employee_id)::int                       as employees
from app.deviation_event d
where d.tenant_id = %(tenant_id)s
  and d.mode = %(mode)s
  and d.status = 'active'
  and d.reference_date between %(start)s::date and %(end)s::date
"""

#: Per type, for the shadow comparison: it is the breakdown a person reads to
#: decide whether a divergence is a wrong roster, a wrong tolerance or a bug.
_BY_TYPE_SQL = """
select d.type, count(*)::int as events, coalesce(sum(abs(d.minutes)), 0)::int as minutes
from app.deviation_event d
where d.tenant_id = %(tenant_id)s
  and d.mode = %(mode)s
  and d.status = 'active'
  and d.reference_date between %(start)s::date and %(end)s::date
group by 1
order by 2 desc, 1
"""

#: How much of the window the engine had no describable shift for. It is the
#: denominator of "is this false-positive rate believable" — a run over a roster
#: it cannot describe is not a measurement.
_BLIND_SQL = """
select count(*)::int as days,
       count(distinct w.employee_id)::int as employees
from app.expected_workday w
where w.tenant_id = %(tenant_id)s
  and w.reference_date between %(start)s::date and %(end)s::date
  and w.confidence < 80
"""


@dataclass(frozen=True, slots=True)
class TypeTotal:
    type: str
    events: int
    minutes: int


@dataclass(frozen=True, slots=True)
class RunResult:
    """One tenant, one window, one mode — and what it found."""

    tenant_id: UUID
    run_id: UUID
    mode: str
    start: date
    end: date
    events: int
    employees: int
    surplus: int
    shortfall: int
    deviation_minutes: int
    blind_days: int
    blind_employees: int
    by_type: tuple[TypeTotal, ...]


async def detect(
    context: SystemContext,
    start: date,
    end: date,
    *,
    mode: str = "shadow",
    now: datetime | None = None,
) -> RunResult:
    """Run the engine for one tenant over one window, idempotently.

    Opening the run before the statement and closing it after is not bookkeeping
    for its own sake: `app.detection_run` is what makes an event traceable to the
    engine version that produced it, and a run left `running` is how a crash
    announces itself instead of looking like a quiet day.
    """
    # The rules ask "is this shift over yet" against the tenant's wall clock —
    # never the container's, which on Railway is three hours into tomorrow.
    if now is None:
        now = (await tenant_clock(context)).now
    window = {"start": start, "end": end}
    async with tenant_scope(context) as scope:
        await scope.execute(
            _OPEN_RUN_SQL,
            {
                **window,
                "mode": mode,
                "engine_version": ENGINE_VERSION,
                # Derivado da janela, e não de uma flag ao lado dela: um `--dias 1`
                # rotulado `backfill` faria `fn_detection_health` medir a cadência
                # errada, e o rótulo é a única coisa que ela tem para olhar.
                "scope": "incremental" if start == end else "backfill",
            },
        )
        run = await scope.fetchone()
        run_id = run["id"]

        try:
            await scope.execute(DETECT_SQL, {**window, "mode": mode, "run_id": run_id, "now": now})
        except Exception as erro:
            await scope.execute(
                _CLOSE_RUN_SQL,
                {
                    "run_id": run_id,
                    "status": "failed",
                    "events_detected": 0,
                    "error": str(erro)[:2000],
                },
            )
            raise

        await scope.execute(_TOTALS_SQL, {**window, "mode": mode})
        totals = await scope.fetchone()
        await scope.execute(_BY_TYPE_SQL, {**window, "mode": mode})
        by_type = await scope.fetchall()
        await scope.execute(_BLIND_SQL, window)
        blind = await scope.fetchone()
        await scope.execute(
            _CLOSE_RUN_SQL,
            {
                "run_id": run_id,
                "status": "completed",
                "events_detected": totals["events"],
                "error": None,
            },
        )

    return RunResult(
        tenant_id=context.tenant_id,
        run_id=run_id,
        mode=mode,
        start=start,
        end=end,
        events=totals["events"],
        employees=totals["employees"],
        surplus=totals["surplus"],
        shortfall=totals["shortfall"],
        deviation_minutes=totals["deviation_minutes"],
        blind_days=blind["days"],
        blind_employees=blind["employees"],
        by_type=tuple(
            TypeTotal(type=t["type"], events=t["events"], minutes=t["minutes"]) for t in by_type
        ),
    )


async def run(
    *, days: int = BACKFILL_DAYS, mode: str = "shadow", today: date | None = None
) -> list[RunResult]:
    """Every active tenant, one at a time, each bound to its own context.

    "Today" is the tenant's, not the container's: with `date.today()` in UTC the
    window flipped to tomorrow at 21:00 in São Paulo, and the incremental run
    spent three hours detecting a day nobody had started.
    """
    results: list[RunResult] = []
    for ctx in await active_tenants(TASK):
        clock = await tenant_clock(ctx)
        end = today or clock.today
        start = end - timedelta(days=days - 1)
        results.append(await detect(ctx, start, end, mode=mode, now=clock.now))
    return results


def relatorio(resultados: list[RunResult]) -> str:
    """O relatório do S4, em pt-BR porque quem lê é o operador.

    Traz os minutos cegos junto do total de propósito: um motor que não sabe
    descrever a escala de 13 pessoas não mediu 13 pessoas, e uma taxa de falso
    positivo calculada sem esse denominador parece melhor do que é.
    """
    linhas: list[str] = []
    for r in resultados:
        linhas.append(
            f"tenant {r.tenant_id} · {r.start} a {r.end} · modo {r.mode} · execução {r.run_id}\n"
            f"  {r.events} indício(s) em {r.employees} colaborador(es) · "
            f"{r.deviation_minutes} min de desvio "
            f"({r.surplus} excedente / {r.shortfall} faltante)"
        )
        for t in r.by_type:
            linhas.append(f"    {t.type:<20} {t.events:>5} · {t.minutes:>6} min")
        if r.blind_days:
            linhas.append(
                f"    ⚠️  {r.blind_employees} colaborador(es) sem escala derivável "
                f"({r.blind_days} dia-pessoa abaixo da confiança 80): esses dias não "
                f"produzem falta, e não entram na conta de falso positivo"
            )
    return "\n".join(linhas) or "nenhum tenant ativo"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detecta desvio de jornada a partir de app.expected_workday e das batidas."
    )
    parser.add_argument(
        "--modo",
        default="sombra",
        help="sombra (padrão) ou producao. Nenhum alerta sai antes do gate G4.",
    )
    parser.add_argument(
        "--dias",
        type=int,
        default=BACKFILL_DAYS,
        help=(
            f"tamanho da janela (padrão {BACKFILL_DAYS}; use {INCREMENTAL_DAYS} para o incremental)"
        ),
    )
    args = parser.parse_args(argv)

    mode = MODES.get(args.modo)
    if mode is None:
        print(f"erro: modo {args.modo!r} — use sombra ou producao")
        return 2

    print(relatorio(run_cli(run(days=args.dias, mode=mode))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
