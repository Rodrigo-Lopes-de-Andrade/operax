"""The sender — the only place in the product that puts a message on the wire.

`for update skip locked` is what lets more than one sender run without delivering
twice: each takes a disjoint batch and neither waits on the other. It is also why
the batch is claimed inside the transaction that marks it `sending` — a row read
and released before being marked is a row two senders can both take.

BACKOFF, AND WHY IT ENDS
1, 5, 15, 60, 360 minutes, then `discarded` with the error recorded. A queue that
retries forever turns a wrong number into an infinite loop nobody notices; a
discarded row is a thing somebody can look at.

THE G4 GATE IS ENFORCED HERE, NOT REMEMBERED
Rule 8: nothing is sent before shadow mode closes with a false-positive rate at or
under 5%. That is not a checkbox — it is asked of the data: **has this tenant ever
completed a detection run in production mode?** While the engine has only ever run
in shadow, the gate is open and the sender delivers nothing, marks nothing sent,
and says so out loud. Promoting the engine is what opens the door, and promoting
the engine is exactly what "shadow closed" means.

DESTINATION IN CLEAR IN THE QUEUE, HASHED IN THE LOG
`app.alert_queue.destination` holds the number because the sender needs to dial
it; `app.alert_sent.destination_hash` holds only a hash, because a long-term
delivery log does not need somebody's phone number to be useful.
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from uuid import UUID

from operax.alertas.provedores.base import Delivery, Message, NullProvider, Provider
from operax.core.db import run_cli
from operax.core.tenant import SystemContext, active_tenants, tenant_scope

TASK = "alertas.sender"

BATCH = 50

#: 1 min, 5 min, 15 min, 1 h, 6 h — e na sexta o registro vira `discarded`.
BACKOFF_MINUTES = (1, 5, 15, 60, 360)
MAX_ATTEMPTS = len(BACKOFF_MINUTES)

#: A pergunta que é o gate G4. Uma execução completa em produção só existe depois
#: de alguém promover o motor, e promover o motor é o que "a sombra fechou"
#: quer dizer.
_GATE_SQL = """
select exists (
  select 1 from app.detection_run
  where tenant_id = %(tenant_id)s and mode = 'production' and status = 'completed'
) as promovido
"""

#: A reserva do lote. `skip locked` é o que permite mais de um sender; marcar
#: `sending` dentro da mesma transação é o que impede que dois peguem a mesma
#: linha entre o `select` e o `update`.
_CLAIM_SQL = """
with alvo as (
    select q.id
    from app.alert_queue q
    where q.tenant_id = %(tenant_id)s
      and q.status in ('pending', 'failed')
      and q.next_attempt_at <= now()
      and q.scheduled_for <= now()
    order by q.next_attempt_at
    limit %(batch)s
    for update skip locked
)
update app.alert_queue q
   set status = 'sending'
  from alvo
 where q.id = alvo.id and q.tenant_id = %(tenant_id)s
returning q.id, q.rule_id, q.channel, q.destination, q.payload, q.template_code,
          q.provider, q.attempts
"""

_TEMPLATE_SQL = """
select variables, body from app.message_template
where tenant_id = %(tenant_id)s and code = %(code)s and active
"""

_MARK_SENT_SQL = """
update app.alert_queue
   set status = 'sent', attempts = attempts + 1
 where id = %(queue_id)s and tenant_id = %(tenant_id)s
"""

#: Falhou: volta para a fila com o próximo horário, ou é descartada na última.
_MARK_FAILED_SQL = """
update app.alert_queue
   set status = case when attempts + 1 >= %(max_attempts)s then 'discarded' else 'failed' end,
       attempts = attempts + 1,
       next_attempt_at = now() + make_interval(mins => %(wait_minutes)s)
 where id = %(queue_id)s and tenant_id = %(tenant_id)s
returning status
"""

_LOG_SQL = """
insert into app.alert_sent
  (tenant_id, queue_id, rule_id, channel, provider, destination_hash,
   provider_message_id, status, error, cost_cents)
values
  (%(tenant_id)s, %(queue_id)s, %(rule_id)s, %(channel)s, %(provider)s,
   %(destination_hash)s, %(provider_message_id)s, %(status)s, %(error)s, %(cost_cents)s)
"""


@dataclass(frozen=True, slots=True)
class SendResult:
    tenant_id: UUID
    gate_open: bool
    claimed: int
    sent: int
    failed: int
    discarded: int


def destination_hash(destination: str) -> str:
    """O que vai para o log de longo prazo no lugar do telefone."""
    return hashlib.sha256(destination.encode("utf-8")).hexdigest()


def _wait_minutes(attempts: int) -> int:
    indice = min(attempts, len(BACKOFF_MINUTES) - 1)
    return BACKOFF_MINUTES[indice]


async def dispatch(
    context: SystemContext, providers: dict[str, Provider], *, batch: int = BATCH
) -> SendResult:
    """Consome um lote da fila. Entrega o que der, devolve o resto para a fila."""
    sent = failed = discarded = 0

    async with tenant_scope(context) as scope:
        await scope.execute(_GATE_SQL, {})
        promovido = bool((await scope.fetchone())["promovido"])

        await scope.execute(_CLAIM_SQL, {"batch": batch})
        lote = await scope.fetchall()

        for linha in lote:
            provider = providers.get(linha["provider"] or "")
            if not promovido or provider is None:
                motivo = (
                    "gate G4 aberto: o motor nunca rodou em produção neste cliente"
                    if not promovido
                    else f"provedor {linha['provider']!r} não configurado"
                )
                entrega = Delivery(status="failed", error=motivo)
            else:
                variables: tuple[str, ...] = ()
                if linha["template_code"]:
                    await scope.execute(_TEMPLATE_SQL, {"code": linha["template_code"]})
                    template = await scope.fetchone()
                    variables = tuple(template["variables"]) if template else ()
                entrega = await provider.enviar(
                    Message(
                        destination=linha["destination"],
                        template=linha["template_code"],
                        variables=variables,
                        facts={k: str(v) for k, v in (linha["payload"] or {}).items()},
                    )
                )

            await scope.execute(
                _LOG_SQL,
                {
                    "queue_id": linha["id"],
                    "rule_id": linha["rule_id"],
                    "channel": linha["channel"],
                    "provider": linha["provider"] or "smtp",
                    "destination_hash": destination_hash(linha["destination"]),
                    "provider_message_id": entrega.provider_message_id,
                    "status": entrega.status,
                    "error": entrega.error,
                    "cost_cents": entrega.cost_cents,
                },
            )

            if entrega.status == "sent":
                await scope.execute(_MARK_SENT_SQL, {"queue_id": linha["id"]})
                sent += 1
                continue

            await scope.execute(
                _MARK_FAILED_SQL,
                {
                    "queue_id": linha["id"],
                    "max_attempts": MAX_ATTEMPTS,
                    "wait_minutes": _wait_minutes(linha["attempts"]),
                },
            )
            if (await scope.fetchone())["status"] == "discarded":
                discarded += 1
            else:
                failed += 1

    return SendResult(
        tenant_id=context.tenant_id,
        gate_open=not promovido,
        claimed=len(lote),
        sent=sent,
        failed=failed,
        discarded=discarded,
    )


def default_providers() -> dict[str, Provider]:
    """Enquanto o gate está aberto, ninguém entrega — e é explícito.

    As três integrações de WhatsApp recebem credencial por tenant, do Supabase
    Vault (`app.integration_secret`), e nenhum tenant tem uma configurada. Montar
    um cliente HTTP contra uma API que não se consegue exercitar seria código que
    só falha na primeira mensagem real; enquanto isso, o `NullProvider` registra
    o que teria saído.
    """
    nulo = NullProvider()
    return {nome: nulo for nome in ("meta_cloud", "z_api", "uazapi", "smtp", "resend")}


async def run(*, batch: int = BATCH) -> list[SendResult]:
    providers = default_providers()
    return [await dispatch(ctx, providers, batch=batch) for ctx in await active_tenants(TASK)]


def relatorio(resultados: list[SendResult]) -> str:
    linhas: list[str] = []
    for r in resultados:
        if r.gate_open:
            linhas.append(
                f"tenant {r.tenant_id}: ⛔ gate G4 aberto — {r.claimed} mensagem(ns) na fila e "
                f"nenhuma entregue. O motor precisa rodar em produção antes."
            )
            continue
        linhas.append(
            f"tenant {r.tenant_id}: {r.claimed} reservada(s) · {r.sent} enviada(s) · "
            f"{r.failed} de volta para a fila · {r.discarded} descartada(s)"
        )
    return "\n".join(linhas) or "nenhum tenant ativo"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consome app.alert_queue.")
    parser.add_argument("--lote", type=int, default=BATCH, help=f"tamanho do lote (padrão {BATCH})")
    args = parser.parse_args(argv)
    print(relatorio(run_cli(run(batch=args.lote))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
