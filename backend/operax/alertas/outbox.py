"""The outbox — the engine writes here and never sends.

Two things separate a queue from a function call, and both matter here. A failed
delivery is retried without recomputing the cycle, and there is exactly one place
that can put a message on the wire — which is what makes the G4 gate in
`sender.py` enforceable instead of hopeful.

THE PAYLOAD IS STRUCTURED, NEVER A READY-MADE STRING
Rule 11 of the project: a provider receives `(template, variables, destination)`.
The official Meta API accepts nothing else, and an interface built around free
text excludes it irreversibly. So this module assembles **facts** — unit, period,
totals, the link — and the provider renders. `util.validate_alert_template` in
the database checks the same thing from the other side: a payload that does not
cover the template's declared variables is refused there too.

WHAT HAPPENS WHEN A TEMPLATE ASKS FOR SOMETHING THIS MODULE DOES NOT KNOW
It refuses to enqueue, naming the variable. The alternative — sending the message
with the value missing — means the official provider rejects it and the unofficial
ones deliver a text with `{{2}}` in the middle of it. Adding a variable to a
template is a visible action, and this is where it becomes visible.

IDEMPOTENCY IS THE KEY, LITERALLY
`idempotency_key` is unique on the table and composed of rule, period, destination
and a hash of the content. Re-running the assembly after a crash does not send
twice, and the same cycle re-enqueued with the same facts is a no-op.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from operax.alertas.ciclo import Cycle
from operax.core.tenant import SystemContext, tenant_scope

#: As regras que cobrem uma unidade, com o destino já resolvido. Um destino sai de
#: um contato nomeado na regra ou da responsabilidade dele na unidade — as duas
#: formas que `app.alert_rule_target` aceita.
_TARGETS_SQL = """
select r.id as rule_id, r.name as rule_name, r.channel, r.template_code, r.content,
       c.id as contact_id, c.type as contact_type,
       c.whatsapp, c.email
from app.alert_rule r
join app.alert_rule_target t on t.rule_id = r.id
left join app.contact c
       on c.id = coalesce(
            t.contact_id,
            (select ur.contact_id from app.unit_responsible ur
              where ur.unit_id = %(unit_id)s
                and ur.responsibility = t.responsibility
                and ur.tenant_id = %(tenant_id)s
              order by ur.is_primary desc
              limit 1))
where r.tenant_id = %(tenant_id)s
  and r.active
  and r.content = 'aggregate'
  and (r.scope_unit_id is null or r.scope_unit_id = %(unit_id)s)
  and (r.muted_until is null or r.muted_until <= now())
  and c.id is not null
  and c.active
"""

_TEMPLATE_SQL = """
select code, variables
from app.message_template
where tenant_id = %(tenant_id)s and code = %(code)s and active
"""

_ENQUEUE_SQL = """
insert into app.alert_queue
  (tenant_id, rule_id, report_cycle_id, channel, destination, payload,
   idempotency_key, template_code, provider)
values
  (%(tenant_id)s, %(rule_id)s, %(cycle_id)s, %(channel)s, %(destination)s, %(payload)s,
   %(idempotency_key)s, %(template_code)s, %(provider)s)
on conflict (idempotency_key) do nothing
returning id
"""

#: O provedor de WhatsApp ativo do tenant. O índice único da migration 14 garante
#: no máximo um, então `limit 1` é a forma e não um desempate.
_PROVIDER_SQL = """
select provider from app.integration
where tenant_id = %(tenant_id)s and active
  and provider in ('meta_cloud', 'z_api', 'uazapi')
limit 1
"""


class TemplateMismatchError(RuntimeError):
    """O template pede uma variável que o ciclo não sabe responder."""


@dataclass(frozen=True, slots=True)
class Queued:
    queue_id: UUID
    rule_name: str
    channel: str
    destination: str


def facts(cycle: Cycle, *, base_url: str) -> dict[str, Any]:
    """Os fatos do ciclo, com os nomes que um template pode declarar.

    O link é profundo e recortado: abre o dashboard já filtrado na unidade e no
    período do relatório, para que "o número da mensagem" e "o número da tela"
    sejam a mesma consulta. É o que a SPEC §4 pede e o que o dashboard do S5 já
    sabe ler.
    """
    link = (
        f"{base_url.rstrip('/')}/dashboard"
        f"?un={cycle.unit_id}&de={cycle.period_start}&ate={cycle.period_end}"
    )
    return {
        "unit": cycle.unit_name,
        "period_start": cycle.period_start.strftime("%d/%m/%Y"),
        "period_end": cycle.period_end.strftime("%d/%m/%Y"),
        "total_events": str(cycle.total_events),
        "deviation_minutes": str(cycle.deviation_minutes),
        "from_previous_days": str(cycle.from_previous_days),
        "declaration": cycle.declaration or "",
        "link": link,
    }


def _key(rule_id: UUID, cycle: Cycle, destination: str, payload: dict[str, Any]) -> str:
    """`regra:período:destino:hash(conteúdo)`, como a SPEC §5 sugere."""
    conteudo = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:16]
    return f"{rule_id}:{cycle.period_end}:{destination}:{digest}"


def _destination(row: dict[str, Any], channel: str) -> str | None:
    return row["whatsapp"] if channel == "whatsapp" else row["email"]


async def enqueue(context: SystemContext, cycles: list[Cycle], *, base_url: str) -> list[Queued]:
    """Uma mensagem por (regra, destino, ciclo) — e nenhuma duas vezes."""
    enfileiradas: list[Queued] = []
    async with tenant_scope(context) as scope:
        await scope.execute(_PROVIDER_SQL, {})
        linha = await scope.fetchone()
        provider = linha["provider"] if linha else None

        for cycle in cycles:
            dados = facts(cycle, base_url=base_url)
            await scope.execute(_TARGETS_SQL, {"unit_id": cycle.unit_id})
            alvos = await scope.fetchall()

            for alvo in alvos:
                canais = ("whatsapp", "email") if alvo["channel"] == "both" else (alvo["channel"],)
                for canal in canais:
                    destino = _destination(alvo, canal)
                    if not destino:
                        continue

                    if alvo["template_code"]:
                        await scope.execute(_TEMPLATE_SQL, {"code": alvo["template_code"]})
                        template = await scope.fetchone()
                        if template is None:
                            raise TemplateMismatchError(
                                f"regra {alvo['rule_name']!r} aponta para o template "
                                f"{alvo['template_code']!r}, que não existe ou está inativo "
                                f"neste cliente"
                            )
                        faltando = [v for v in template["variables"] if v not in dados]
                        if faltando:
                            raise TemplateMismatchError(
                                f"o template {alvo['template_code']!r} declara "
                                f"{', '.join(faltando)}, e o ciclo não sabe responder. "
                                f"O conhecido é: {', '.join(sorted(dados))}"
                            )

                    await scope.execute(
                        _ENQUEUE_SQL,
                        {
                            "rule_id": alvo["rule_id"],
                            "cycle_id": cycle.cycle_id,
                            "channel": canal,
                            "destination": destino,
                            "payload": json.dumps(dados, ensure_ascii=False),
                            "idempotency_key": _key(alvo["rule_id"], cycle, destino, dados),
                            "template_code": alvo["template_code"],
                            "provider": provider if canal == "whatsapp" else "smtp",
                        },
                    )
                    criada = await scope.fetchone()
                    if criada is not None:
                        enfileiradas.append(
                            Queued(
                                queue_id=criada["id"],
                                rule_name=alvo["rule_name"],
                                channel=canal,
                                destination=destino,
                            )
                        )
    return enfileiradas
