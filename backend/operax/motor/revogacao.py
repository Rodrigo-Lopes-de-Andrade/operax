"""Retroactive correction — the punch changed after the fact, and the trail keeps.

The detector answers "what is true today". This module answers the harder
question: what happens to what was true yesterday, once the source disagrees.

Two things can happen to a stored event, and they are not the same thing:

  the deviation stopped existing — somebody fixed the punch at the clock, or a
      justification was accepted there. `app.revoke_deviation` marks it revoked
      with a reason. **Never a delete** (rule 6): the dashboard shows the current
      state and the audit shows how it got there, and a row that vanishes cannot
      explain a report that already went out.

  the deviation changed size on an event that was already **sent to somebody**.
      The detector deliberately does not touch those — `DETECT_SQL` skips any row
      with a `report_cycle_id`, because silently rewriting a number a manager is
      holding on WhatsApp is how a product loses the argument it is supposed to
      win. So here the old one is revoked and a new one is inserted pointing back
      at it through `supersede_id`.

WHY IT RUNS AFTER THE DETECTOR AND NOT INSTEAD OF IT
`DETECT_SQL` updates in place the events nobody has seen yet, which is cheap and
leaves no noise. What it cannot do is remove a row — an insert has nothing to say
about something that should no longer be there — so the vanished ones are asked
as a question, against the same `evento` definition the detector writes from.

SPEC §3.5b: the incremental pass looks at today; this one looks at the last week,
1×/day, because a punch corrected today belongs to a day before it.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from operax.core.db import run_cli
from operax.core.tenant import SystemContext, active_tenants, tenant_scope
from operax.motor.deteccao import BACKFILL_DAYS, ENGINE_VERSION, MODES
from operax.motor.regras import SUPERSEDED_SQL, VANISHED_SQL
from operax.motor.relogio import tenant_clock

TASK = "motor.revogacao"

REASON_VANISHED = "batida corrigida na origem: o indício não existe mais"
REASON_SUPERSEDED = "batida corrigida na origem: o indício mudou de tamanho depois do relatório"

_OPEN_RUN_SQL = """
insert into app.detection_run
  (tenant_id, mode, period_start, period_end, engine_version, scope)
values (%(tenant_id)s, %(mode)s, %(start)s, %(end)s, %(engine_version)s, %(scope)s)
returning id
"""

_CLOSE_RUN_SQL = """
update app.detection_run
   set status = 'completed', finished_at = now(), events_detected = %(events_detected)s
 where id = %(run_id)s and tenant_id = %(tenant_id)s
"""

#: A revogação passa pela função do banco, e não por um `update` daqui: é a única
#: porta sancionada (regra 6), e o filtro de tenant ao lado dela é o que faz a
#: guarda sintática do `bind_tenant` valer alguma coisa.
_REVOKE_SQL = """
select app.revoke_deviation(d.id, %(reason)s, 'revoked')
from app.deviation_event d
where d.id = %(event_id)s and d.tenant_id = %(tenant_id)s and d.status = 'active'
"""

#: A empresa e a unidade vêm do evento ANTIGO, não do colaborador de hoje: o fato
#: aconteceu onde aconteceu (SPEC §3.3), e supersessão não é uma chance de
#: reescrever o passado.
_SUPERSEDE_SQL = """
insert into app.deviation_event
  (tenant_id, employee_id, company_id, unit_id, reference_date, type, minutes,
   expected_time, actual_time, punch_ids, mode, run_id, supersede_id)
select %(tenant_id)s::uuid, d.employee_id, d.company_id, d.unit_id, d.reference_date,
       d.type, %(minutes)s, %(expected_time)s, %(actual_time)s, %(punch_ids)s,
       d.mode, %(run_id)s::uuid, d.id
from app.deviation_event d
where d.id = %(event_id)s and d.tenant_id = %(tenant_id)s
returning id
"""


@dataclass(frozen=True, slots=True)
class Change:
    """Um indício que deixou de valer, e o que aconteceu com ele."""

    event_id: UUID
    employee_id: UUID
    reference_date: date
    type: str
    minutes_before: int
    minutes_now: int | None


@dataclass(frozen=True, slots=True)
class RevocationResult:
    tenant_id: UUID
    run_id: UUID
    mode: str
    start: date
    end: date
    revoked: tuple[Change, ...]
    superseded: tuple[Change, ...]


async def reconcile(
    context: SystemContext,
    start: date,
    end: date,
    *,
    mode: str = "production",
    now: datetime | None = None,
) -> RevocationResult:
    """Compara o que está gravado com o que as batidas dizem hoje."""
    # The same clock the detector used: the reconciliation re-asks the rules,
    # and a rule gated on "is the shift over" must hear the same answer.
    if now is None:
        now = (await tenant_clock(context)).now
    window = {"start": start, "end": end, "mode": mode}
    rules = {**window, "now": now}
    revoked: list[Change] = []
    superseded: list[Change] = []

    async with tenant_scope(context) as scope:
        await scope.execute(
            _OPEN_RUN_SQL,
            {
                **window,
                "engine_version": f"{ENGINE_VERSION}+revogacao",
                # Sempre retroativa: reconciliar o dia corrente com ele mesmo não
                # tem o que achar, porque a correção de batida chega depois.
                "scope": "backfill",
            },
        )
        run_id = (await scope.fetchone())["id"]

        await scope.execute(VANISHED_SQL, rules)
        for row in await scope.fetchall():
            await scope.execute(_REVOKE_SQL, {"event_id": row["id"], "reason": REASON_VANISHED})
            revoked.append(
                Change(
                    event_id=row["id"],
                    employee_id=row["employee_id"],
                    reference_date=row["reference_date"],
                    type=row["type"],
                    minutes_before=row["minutes"],
                    minutes_now=None,
                )
            )

        await scope.execute(SUPERSEDED_SQL, rules)
        for row in await scope.fetchall():
            # Revogar ANTES de inserir: o índice único cobre um ativo por
            # (colaborador, dia, tipo, modo), e os dois não podem coexistir.
            await scope.execute(_REVOKE_SQL, {"event_id": row["id"], "reason": REASON_SUPERSEDED})
            await scope.execute(
                _SUPERSEDE_SQL,
                {
                    "event_id": row["id"],
                    "minutes": row["minutes_now"],
                    "expected_time": row["expected_time"],
                    "actual_time": row["actual_time"],
                    "punch_ids": row["punch_ids"],
                    "run_id": run_id,
                },
            )
            superseded.append(
                Change(
                    event_id=row["id"],
                    employee_id=row["employee_id"],
                    reference_date=row["reference_date"],
                    type=row["type"],
                    minutes_before=row["minutes_before"],
                    minutes_now=row["minutes_now"],
                )
            )

        await scope.execute(
            _CLOSE_RUN_SQL,
            {"run_id": run_id, "events_detected": len(revoked) + len(superseded)},
        )

    return RevocationResult(
        tenant_id=context.tenant_id,
        run_id=run_id,
        mode=mode,
        start=start,
        end=end,
        revoked=tuple(revoked),
        superseded=tuple(superseded),
    )


async def run(
    *, days: int = BACKFILL_DAYS, mode: str = "production", today: date | None = None
) -> list[RevocationResult]:
    results: list[RevocationResult] = []
    for ctx in await active_tenants(TASK):
        clock = await tenant_clock(ctx)
        end = today or clock.today
        start = end - timedelta(days=days - 1)
        results.append(await reconcile(ctx, start, end, mode=mode, now=clock.now))
    return results


def relatorio(resultados: list[RevocationResult]) -> str:
    """O que mudou de ontem para hoje, em pt-BR."""
    linhas: list[str] = []
    for r in resultados:
        if not r.revoked and not r.superseded:
            linhas.append(
                f"tenant {r.tenant_id} · {r.start} a {r.end} · modo {r.mode}: nada mudou na origem"
            )
            continue
        linhas.append(
            f"tenant {r.tenant_id} · {r.start} a {r.end} · modo {r.mode}\n"
            f"  {len(r.revoked)} revogado(s) · {len(r.superseded)} substituído(s)"
        )
        for c in r.revoked:
            linhas.append(f"    revogado   {c.reference_date} {c.type} ({c.minutes_before} min)")
        for c in r.superseded:
            linhas.append(
                f"    substituído {c.reference_date} {c.type} "
                f"({c.minutes_before} -> {c.minutes_now} min)"
            )
    return "\n".join(linhas) or "nenhum tenant ativo"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcilia os indícios gravados com as batidas corrigidas na origem."
    )
    parser.add_argument("--modo", default="producao", help="producao (padrão) ou sombra")
    parser.add_argument("--dias", type=int, default=BACKFILL_DAYS, help="janela retroativa")
    args = parser.parse_args(argv)

    mode = MODES.get(args.modo)
    if mode is None:
        print(f"erro: modo {args.modo!r} — use sombra ou producao")
        return 2

    print(relatorio(run_cli(run(days=args.dias, mode=mode))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
