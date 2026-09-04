"""The report cycle — and the reservation that makes "exactly one" true.

A deviation belongs to exactly one cycle. That is not a convention anybody can
keep by being careful: it is an `update ... where report_cycle_id is null` inside
a transaction, and everything else in this module exists to make that statement
correct.

WHY THE RESERVATION HAS NO LOWER BOUND ON THE DATE
Because a deviation can be detected late — the punch arrived in a sync after the
last report went out. `reference_date <= period_end` and nothing else, so a fact
from last Tuesday that nobody had seen yet still gets carried. The alternative,
bounding by `period_start`, would silently drop exactly the occurrences the
manager most needs to hear about.

THE DIVERGENCE THAT HAS TO BE DECLARED
The dashboard filters by `reference_date`; the report groups by cycle. A
deviation detected late belongs to day D and to cycle C+1, and **both numbers are
right and different**. So the cycle counts how many of its events are older than
its own `period_start` and the message says so — "inclui 3 ocorrências de dias
anteriores". Without that line the manager opens the dashboard, sees another
number and concludes the system is wrong, which is the kind of product error that
an explanation afterwards does not fix.

WHAT THIS MODULE DOES NOT DO
Send. It assembles and reserves; `outbox.py` enqueues and `sender.py` delivers.
The engine never sends — that separation is what lets a failed delivery be
retried without recomputing anything, and what keeps the G4 gate enforceable in
one place.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from operax.core.db import run_cli
from operax.core.tenant import SystemContext, active_tenants, tenant_scope

TASK = "alertas.ciclo"

#: As unidades que têm regra ligada, com o período que o ciclo deve cobrir.
#: `period_start` sai do fim do último ciclo daquela unidade — e, na primeira vez,
#: da ocorrência mais antiga que ainda não entrou em ciclo nenhum.
_UNITS_SQL = """
select u.id as unit_id,
       u.name as unit_name,
       coalesce(
         (select max(rc.period_end) + 1
            from app.report_cycle rc
           where rc.tenant_id = %(tenant_id)s and rc.unit_id = u.id
             and rc.status in ('open', 'sent')),
         (select min(d.reference_date)
            from app.deviation_event d
           where d.tenant_id = %(tenant_id)s and d.unit_id = u.id
             and d.report_cycle_id is null and d.status = 'active'
             and d.mode = 'production'),
         %(ate)s::date
       ) as period_start
from app.unit u
where u.tenant_id = %(tenant_id)s
  and u.active
  and exists (
    select 1 from app.alert_rule r
    where r.tenant_id = %(tenant_id)s
      and r.active
      and r.content = 'aggregate'
      and (r.scope_unit_id is null or r.scope_unit_id = u.id)
      and (r.muted_until is null or r.muted_until <= now())
  )
"""

_CREATE_CYCLE_SQL = """
insert into app.report_cycle (tenant_id, unit_id, period_start, period_end, status)
values (%(tenant_id)s, %(unit_id)s, %(de)s, %(ate)s, 'open')
returning id
"""

#: A reserva. `report_cycle_id is null` é a cláusula inteira do "exatamente um":
#: quem já está num ciclo não entra em outro, e o índice parcial da migration 05
#: (`deviation_event_pendente_idx`) existe para esta consulta.
_RESERVE_SQL = """
update app.deviation_event d
   set report_cycle_id = %(cycle_id)s, updated_at = now()
 where d.tenant_id = %(tenant_id)s
   and d.unit_id = %(unit_id)s
   and d.report_cycle_id is null
   and d.status = 'active'
   and d.mode = 'production'
   and d.reference_date <= %(ate)s::date
returning d.reference_date, d.minutes
"""

_CLOSE_CYCLE_SQL = """
update app.report_cycle
   set total_events = %(total_events)s
 where id = %(cycle_id)s and tenant_id = %(tenant_id)s
"""

#: Um ciclo sem ocorrência não vira mensagem. "Nada a relatar" enviado toda noite
#: treina o gestor a ignorar o canal, e o canal é o produto.
_DROP_EMPTY_SQL = """
delete from app.report_cycle
 where id = %(cycle_id)s and tenant_id = %(tenant_id)s and total_events = 0
"""


@dataclass(frozen=True, slots=True)
class Cycle:
    """Um ciclo montado, com o que ele precisa declarar."""

    cycle_id: UUID
    unit_id: UUID
    unit_name: str
    period_start: date
    period_end: date
    total_events: int
    deviation_minutes: int
    #: Ocorrências anteriores ao próprio `period_start`: detectadas depois do
    #: último envio. É o número que a mensagem tem de declarar em texto.
    from_previous_days: int

    @property
    def declaration(self) -> str | None:
        """A frase obrigatória da SPEC §4, ou nada quando não se aplica."""
        if not self.from_previous_days:
            return None
        plural = "s" if self.from_previous_days > 1 else ""
        return (
            f"Inclui {self.from_previous_days} ocorrência{plural} de dias anteriores "
            f"detectada{plural} após o último envio."
        )


async def assemble(context: SystemContext, ate: date) -> list[Cycle]:
    """Monta um ciclo por unidade com regra ligada, numa transação só.

    Numa transação só porque a reserva é destrutiva no sentido que importa: um
    evento marcado para um ciclo que nunca foi criado some do próximo, e some em
    silêncio. Falhar no meio tem de desfazer os dois lados.
    """
    ciclos: list[Cycle] = []
    async with tenant_scope(context) as scope:
        await scope.execute(_UNITS_SQL, {"ate": ate})
        unidades = await scope.fetchall()

        for unidade in unidades:
            de = min(unidade["period_start"], ate)
            await scope.execute(
                _CREATE_CYCLE_SQL, {"unit_id": unidade["unit_id"], "de": de, "ate": ate}
            )
            cycle_id = (await scope.fetchone())["id"]

            await scope.execute(
                _RESERVE_SQL, {"cycle_id": cycle_id, "unit_id": unidade["unit_id"], "ate": ate}
            )
            reservados = await scope.fetchall()

            total = len(reservados)
            await scope.execute(_CLOSE_CYCLE_SQL, {"cycle_id": cycle_id, "total_events": total})
            if total == 0:
                await scope.execute(_DROP_EMPTY_SQL, {"cycle_id": cycle_id})
                continue

            ciclos.append(
                Cycle(
                    cycle_id=cycle_id,
                    unit_id=unidade["unit_id"],
                    unit_name=unidade["unit_name"],
                    period_start=de,
                    period_end=ate,
                    total_events=total,
                    deviation_minutes=sum(abs(r["minutes"]) for r in reservados),
                    from_previous_days=sum(1 for r in reservados if r["reference_date"] < de),
                )
            )
    return ciclos


async def run(*, today: date | None = None) -> list[tuple[SystemContext, list[Cycle]]]:
    ate = today or date.today()
    return [(ctx, await assemble(ctx, ate)) for ctx in await active_tenants(TASK)]


def relatorio(saida: list[tuple[SystemContext, list[Cycle]]]) -> str:
    linhas: list[str] = []
    for context, ciclos in saida:
        if not ciclos:
            linhas.append(f"tenant {context.tenant_id}: nenhuma unidade com ocorrência a relatar")
            continue
        linhas.append(f"tenant {context.tenant_id} · {len(ciclos)} ciclo(s)")
        for c in ciclos:
            linhas.append(
                f"  {c.unit_name}: {c.total_events} ocorrência(s) · "
                f"{c.deviation_minutes} min · {c.period_start} a {c.period_end}"
            )
            if c.declaration:
                linhas.append(f"    {c.declaration}")
    return "\n".join(linhas) or "nenhum tenant ativo"


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Monta o ciclo de relatório por unidade.").parse_args(argv)
    print(relatorio(run_cli(run())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
