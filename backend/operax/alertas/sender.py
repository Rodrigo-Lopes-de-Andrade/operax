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
completed a detection run in production mode, and has the release been
recorded?** While the gate is open the sender **does not reserve**: it counts
what is waiting and writes nothing. Until 17/09/2026 it reserved the batch and
marked every row `failed` with backoff — five rounds and the C4 invites were
`discarded` without a single delivery attempt, in about eight hours of a sender
running against a closed door. The gate is a wall, not a tax on attempts.

THREE PHASES, AND THE HTTP IS BETWEEN THEM, OUTSIDE ANY TRANSACTION
(a) `tenant_scope`: gate, claim (`sending`), the templates of the claimed rows,
the active integrations of the channel providers and their secrets from the
vault. Closed. (b) No transaction: one `Provider` per integration through
`fabrica.build`, one `enviar` per row. (c1) `tenant_scope`, one for the whole
batch: the log line and the mark of every row — a Telegram row that is about to
be degraded is only parked (`failed`, attempt counted, `next_attempt_at` left
alone); commit. (c2) one small transaction per row to degrade (below). A
provider call inside an open transaction holds a connection of the pool for as
long as a third party takes to answer — `canais.py` and `vigia.py` already do
it this way.

The token lives in a local between (a) and (b). It goes into the provider and
nowhere else: not the log (`verification_client` mutes `httpx`), not an error
(providers raise `from None`), not a result.

A `sending` ROW OLDER THAN `STUCK_MINUTES` IS CLAIMABLE AGAIN
A process that dies between (a) and (c) leaves its rows `sending` forever, and
a queue nobody can drain is worse than a message delivered twice. The claim
stamps `next_attempt_at = now()`, so for a `sending` row that column is the
claim time; after ten minutes the row is taken again and `relatorio` counts it
as recovered. ⚠️ The price is named: a delivery that went out in (b) and whose
(c) never ran will go out a second time. Ten minutes is far past any provider
timeout, so the window is a crashed process, not a slow one.

`payload.link` IS SCRUBBED WHEN THE ROW IS FINISHED
The C4 invite carries the adhesion link — the credential, SPEC-CANAIS §3.3 —
in `payload.link` until the sender delivers it. `sent` and `discarded` remove
it (`payload - 'link'`, only for `telegram_invite`; an alert keeps its dashboard
link). The validator trigger lets a terminal update through for exactly this
(`ch_queue_telegram`).

A TELEGRAM ROW DEGRADES TO WHATSAPP FOR THREE CAUSES — AND ONLY ONE REVOKES
§8 degrading on its own, at delivery time, for a row that `outbox.route` sent
to Telegram:
* `blocked` — the person blocked the bot. The current identity is revoked with
  the reason and the audit line says so without the `chat_id`; this is the
  ONLY cause that touches the identity, because it is the only one that is
  about the person's consent.
* a credential error (`CREDENTIAL_ERRORS`) — the tenant's bot token is dead.
  That is the bot, not the person: the identity stays, the row goes by the
  number.
* the last backoff — five Telegram failures of any other kind. Instead of
  `discarded`, the row goes by the number: eight hours late by WhatsApp beats
  lost.
In every case the SAME queue row is re-routed — `whatsapp`, the tenant's
active provider, the contact's number from the database, `failed`, due now,
`attempts` back to zero — so the next batch delivers it. The re-route is
`telegram → whatsapp` only and the branch requires the row to be `telegram`:
it happens at most once per row, and a re-routed row that fails on WhatsApp
follows the ordinary backoff. No active WhatsApp, no number, no holder: the
row is `discarded`, and the log line of the attempt says why.

EACH DEGRADATION IS ITS OWN FRONTIER — NEVER THE BATCH'S
The validator trigger can refuse the re-route (`meta_cloud` with the template
not approved). Until 17/09/2026 that refusal rolled back phase (c) for the
whole batch: the rows already delivered stayed `sending`, were recovered ten
minutes later, and were delivered AGAIN — a loop for as long as the template
stayed unapproved. So a degradation runs in three small transactions of its
own, after (c1) has committed everybody's log and mark: the holder (and, for
`blocked`, the revocation and its audit line — committed FIRST, so it survives
whatever the re-route does); then the re-route; then, if the re-route was
refused by the trigger or reached no row, the discard — with a second log
line saying `reroute_refused: <the trigger's sentence>` when it was the
trigger. The trigger's sentence is pt-BR, names the template and the provider,
and never carries the payload; only `diag.message_primary` is read, never the
exception chain.

DESTINATION IN CLEAR IN THE QUEUE, HASHED IN THE LOG
`app.alert_queue.destination` holds the number — or the `chat_id` — because the
sender needs to dial it; `app.alert_sent.destination_hash` holds only a hash,
because a long-term delivery log does not need somebody's phone number to be
useful. Neither is ever written to a log line or a report.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx
from psycopg import errors
from psycopg.types.json import Jsonb

from operax.alertas import outbox
from operax.alertas.capacidades import CHANNEL_PROVIDERS, TELEGRAM_CHANNEL, WHATSAPP_CHANNEL
from operax.alertas.provedores import PROVIDERS, fabrica
from operax.alertas.provedores.base import Delivery, Message, Provider, verification_client
from operax.core.db import run_cli
from operax.core.tenant import SystemContext, TenantScope, active_tenants, tenant_scope
from operax.core.vault import read_secret

# The webhook owns "revoke the current identity of this holder, with a reason";
# the sender reuses the statement instead of writing a second one.
from server.routers.webhooks import _REVOKE_PREVIOUS_SQL

logger = logging.getLogger(__name__)

TASK = "alertas.sender"

BATCH = 50

#: 1 min, 5 min, 15 min, 1 h, 6 h — e na sexta o registro vira `discarded`.
BACKOFF_MINUTES = (1, 5, 15, 60, 360)
MAX_ATTEMPTS = len(BACKOFF_MINUTES)

#: Uma linha `sending` há mais que isto foi de um processo que morreu entre a
#: fase (a) e a (c). Volta a ser elegível — ver o docstring sobre o preço.
STUCK_MINUTES = 10

#: O `Delivery.error` com que o provedor de Telegram diz "a pessoa bloqueou o
#: bot" (`TelegramProvider.enviar`, 403). É o único erro que REVOGA a identidade.
BLOCKED_ERROR = "blocked"
#: A razão gravada em `messaging_identity.revoked_reason` e na auditoria.
BLOCKED_REASON = "bloqueou o bot"
#: Os `Delivery.error` que dizem "o token do bot está morto": `http_401` é o que
#: `TelegramProvider.enviar` devolve a um 401; `unauthorized` é o código que o
#: mesmo módulo dá à credencial recusada na verificação. É do bot do tenant, não
#: do consentimento da pessoa: a linha vai por WhatsApp SEM revogar.
CREDENTIAL_ERRORS = frozenset({"unauthorized", "http_401"})
#: O prefixo do segundo registro em `alert_sent` quando o gatilho recusa a
#: re-rota: o resto é a frase do gatilho (`diag.message_primary`).
REROUTE_REFUSED = "reroute_refused"

#: A pergunta que é o gate G4 — em duas metades, porque a primeira sozinha mentiu.
#:
#: Até 11/09/2026 o gate era só `promovido`: uma execução completa em produção,
#: sob a premissa de que promover o motor é o que "a sombra fechou" quer dizer.
#: Em 09/09 o motor foi promovido para o DP ver o painel, com o censo do G4 em
#: zero adjudicações — e a porta ficou aberta com a taxa de falso positivo não
#: medida. O que segurava a entrega era não existir regra de alerta cadastrada.
#:
#: `liberado` é a medição virando fato: uma linha em `app.alert_release`, gravada
#: por `python -m operax.motor.adjudicacao liberar` só depois de `medir` responder
#: PASSA sobre censo completo, e sem `revoked_at`. O schema recusa taxa acima de
#: 5% e censo parcial (migration 38). As duas metades são exigidas: promovido sem
#: liberação é o estado de 09/09; liberação sem motor promovido não tem o que
#: entregar.
_GATE_SQL = """
select exists (
  select 1 from app.detection_run
  where tenant_id = %(tenant_id)s and mode = 'production' and status = 'completed'
) as promovido,
exists (
  select 1 from app.alert_release
  where tenant_id = %(tenant_id)s and revoked_at is null
) as liberado
"""

#: Com o gate aberto, só isto roda: quantas esperam. Nenhum `update`.
_WAITING_SQL = """
select count(*) as waiting
from app.alert_queue q
where q.tenant_id = %(tenant_id)s
  and q.status in ('pending', 'failed')
  and q.next_attempt_at <= now()
  and q.scheduled_for <= now()
"""

#: A reserva do lote. `skip locked` é o que permite mais de um sender; marcar
#: `sending` dentro da mesma transação é o que impede que dois peguem a mesma
#: linha entre o `select` e o `update`. O `next_attempt_at = now()` carimba a
#: reserva: é o relógio que decide, dez minutos depois, se ela ficou presa.
_CLAIM_SQL = """
with alvo as (
    select q.id, q.status as previous_status
    from app.alert_queue q
    where q.tenant_id = %(tenant_id)s
      and q.scheduled_for <= now()
      and (
            (q.status in ('pending', 'failed') and q.next_attempt_at <= now())
         or (q.status = 'sending'
             and q.next_attempt_at < now() - make_interval(mins => %(stuck_minutes)s))
      )
    order by q.next_attempt_at
    limit %(batch)s
    for update skip locked
)
update app.alert_queue q
   set status = 'sending', next_attempt_at = now()
  from alvo
 where q.id = alvo.id and q.tenant_id = %(tenant_id)s
returning q.id, q.rule_id, q.channel, q.destination, q.payload, q.template_code,
          q.provider, q.attempts, alvo.previous_status
"""

#: Os cinco campos de `Message` que vêm do template: a ordem das variáveis, o
#: corpo para quem renderiza localmente, o idioma e o nome que a WABA conhece.
_TEMPLATE_SQL = """
select variables, body, language, meta_template_name
from app.message_template
where tenant_id = %(tenant_id)s and code = %(code)s and active
"""

#: As integrações ativas dos provedores de canal — `%(providers)s` é
#: `CHANNEL_PROVIDERS`, como array. E-mail não entra: não há provedor de e-mail
#: atrás da fábrica, e a linha dele falha nomeada, como sempre falhou.
_INTEGRATIONS_SQL = """
select id, provider, config
from app.integration
where tenant_id = %(tenant_id)s
  and active
  and provider = any(%(providers)s)
"""

#: Entregue. O convite de adesão perde o link — ele é a credencial.
_MARK_SENT_SQL = """
update app.alert_queue
   set status = 'sent',
       attempts = attempts + 1,
       payload = case when template_code = 'telegram_invite'
                      then payload - 'link' else payload end
 where id = %(queue_id)s and tenant_id = %(tenant_id)s
"""

#: Falhou: volta para a fila com o próximo horário, ou é descartada na última —
#: e na última o convite também perde o link.
_MARK_FAILED_SQL = """
update app.alert_queue
   set status = case when attempts + 1 >= %(max_attempts)s then 'discarded' else 'failed' end,
       attempts = attempts + 1,
       next_attempt_at = now() + make_interval(mins => %(wait_minutes)s),
       payload = case when attempts + 1 >= %(max_attempts)s
                       and template_code = 'telegram_invite'
                      then payload - 'link' else payload end
 where id = %(queue_id)s and tenant_id = %(tenant_id)s
returning status
"""

#: A marca de (c1) para a linha de Telegram que vai ser degradada: a tentativa
#: conta, o status é `failed`, e `next_attempt_at` fica como está — quem decide
#: o próximo horário é a re-rota (agora) ou o descarte (nunca), em (c2).
_PARK_SQL = """
update app.alert_queue
   set status = 'failed',
       attempts = attempts + 1
 where id = %(queue_id)s and tenant_id = %(tenant_id)s
"""

#: Descartada sem mais tentativa — a degradação sem WhatsApp para onde ir. A
#: tentativa já foi contada por `_PARK_SQL`.
_DISCARD_SQL = """
update app.alert_queue
   set status = 'discarded',
       payload = case when template_code = 'telegram_invite'
                      then payload - 'link' else payload end
 where id = %(queue_id)s and tenant_id = %(tenant_id)s
"""

#: O titular por trás de um chat_id — a linha da fila só tem o destino. A
#: vigente primeiro; uma revogada ainda diz quem era, para o re-roteamento.
_IDENTITY_HOLDER_SQL = """
select contact_id, employee_id
from app.messaging_identity
where tenant_id = %(tenant_id)s
  and channel = %(channel)s
  and external_id = %(external_id)s
order by (revoked_at is null) desc, opted_in_at desc
limit 1
"""

#: `user_id` nulo: ninguém autenticado — quem agiu foi a plataforma, pela
#: resposta do bot. ⛔ `depois` leva canal e razão; o `chat_id` não.
_AUDIT_SQL = """
insert into app.audit_log
  (tenant_id, user_id, action, entity, entity_id, antes, depois)
values
  (%(tenant_id)s, null, 'update', 'messaging_identity', %(entity_id)s, null, %(depois)s)
"""

#: A mesma linha, agora por WhatsApp, para o número do contato, devida já, com
#: as tentativas zeradas: as de Telegram foram do outro canal, e uma re-rota na
#: quarta tentativa descartaria na primeira falha de WhatsApp. Só acontece
#: `telegram → whatsapp`, uma vez por linha. Zero linhas quando o contato não
#: tem número (ou não está ativo): o chamador descarta.
_REROUTE_SQL = """
update app.alert_queue q
   set channel = %(channel)s,
       provider = %(provider)s,
       destination = c.whatsapp,
       status = 'failed',
       attempts = 0,
       next_attempt_at = now()
  from app.contact c
 where q.id = %(queue_id)s
   and q.tenant_id = %(tenant_id)s
   and c.id = %(contact_id)s
   and c.tenant_id = %(tenant_id)s
   and c.active
   and c.whatsapp is not null
returning q.id
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
    #: Com o gate aberto: qual metade está aberta. Nada foi reservado.
    gate_reason: str | None = None
    #: Com o gate aberto: quantas esperam (`pending`/`failed` vencidas).
    waiting: int = 0
    claimed: int = 0
    sent: int = 0
    failed: int = 0
    discarded: int = 0
    #: `sending` presas há mais de `STUCK_MINUTES`, retomadas neste lote.
    recovered: int = 0
    #: O nome da exceção quando o lote deste tenant morreu antes de terminar.
    #: Os outros tenants seguiram; as linhas que ficaram `sending` voltam pelo
    #: `STUCK_MINUTES`. Nada foi reservado de novo neste turno.
    error: str | None = None
    sent_by_channel: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _Batch:
    """O que a fase (a) entrega à (b). Os segredos vivem aqui e em lugar nenhum mais."""

    rows: list[dict[str, Any]]
    templates: dict[str, dict[str, Any]]
    #: `id`, `provider`, `config` de cada integração ativa de canal.
    integrations: list[dict[str, Any]]
    #: provedor → `{chave do cofre: valor}`, só as que o cofre tinha. Fora do
    #: `repr`: um traceback ou um `print` de depuração não o mostram.
    secrets: dict[str, dict[str, str]] = field(repr=False)


def destination_hash(destination: str) -> str:
    """O que vai para o log de longo prazo no lugar do telefone."""
    return hashlib.sha256(destination.encode("utf-8")).hexdigest()


def _wait_minutes(attempts: int) -> int:
    indice = min(attempts, len(BACKOFF_MINUTES) - 1)
    return BACKOFF_MINUTES[indice]


def _secret_keys(provider: str) -> list[str]:
    """As chaves do cofre de um provedor: o nome de cada `FieldSpec.secret` —
    o mesmo nome com que `save_credential` gravou."""
    return [spec.name for spec in PROVIDERS[provider].FIELDS if spec.secret]


def _missing_fields(
    provider: str, config: Mapping[str, Any], secrets: Mapping[str, str]
) -> list[str]:
    """Os campos declarados em `FIELDS` que não estão do lado que `FieldSpec.secret`
    nomeia — o que `fabrica.build` recusaria com `KeyError`. Nomes de campo,
    nunca valores."""
    return [
        spec.name
        for spec in PROVIDERS[provider].FIELDS
        if spec.name not in (secrets if spec.secret else config)
    ]


async def _claim(scope: TenantScope, batch: int) -> _Batch:
    """Fase (a), depois do gate: reserva, templates, integrações e segredos."""
    await scope.execute(_CLAIM_SQL, {"batch": batch, "stuck_minutes": STUCK_MINUTES})
    rows = await scope.fetchall()
    if not rows:
        return _Batch(rows=[], templates={}, integrations=[], secrets={})

    templates: dict[str, dict[str, Any]] = {}
    for code in sorted({row["template_code"] for row in rows if row["template_code"]}):
        await scope.execute(_TEMPLATE_SQL, {"code": code})
        template = await scope.fetchone()
        if template is not None:
            templates[code] = template

    await scope.execute(_INTEGRATIONS_SQL, {"providers": list(CHANNEL_PROVIDERS)})
    integrations = await scope.fetchall()
    secrets: dict[str, dict[str, str]] = {}
    for integration in integrations:
        values: dict[str, str] = {}
        for key in _secret_keys(integration["provider"]):
            value = await read_secret(scope, integration["id"], key)
            if value is not None:
                values[key] = value
        secrets[integration["provider"]] = values
    return _Batch(rows=rows, templates=templates, integrations=integrations, secrets=secrets)


def _message(row: dict[str, Any], template: dict[str, Any] | None) -> Message:
    """O `Message` completo: os fatos do payload e os cinco campos do template."""
    facts = {k: str(v) for k, v in (row["payload"] or {}).items()}
    if template is None:
        return Message(
            destination=row["destination"], template=row["template_code"], variables=(), facts=facts
        )
    return Message(
        destination=row["destination"],
        template=row["template_code"],
        variables=tuple(template["variables"]),
        facts=facts,
        body=template["body"],
        language=template["language"],
        provider_template=template["meta_template_name"],
    )


async def _deliver(batch: _Batch, http: httpx.AsyncClient) -> list[Delivery]:
    """Fase (b): um provedor por integração, um `enviar` por linha. Sem transação."""
    providers: dict[str, Provider] = {}
    unusable: dict[str, str] = {}
    for integration in batch.integrations:
        name = integration["provider"]
        config = integration["config"] or {}
        secrets = batch.secrets.get(name, {})
        missing = _missing_fields(name, config, secrets)
        if missing:
            unusable[name] = f"provedor {name!r} sem credencial completa: {', '.join(missing)}"
            continue
        providers[name] = fabrica.build(name, config=config, secrets=secrets, http=http)

    deliveries: list[Delivery] = []
    for row in batch.rows:
        name = row["provider"] or ""
        provider = providers.get(name)
        if provider is None:
            motivo = unusable.get(name, f"provedor {name!r} não configurado")
            deliveries.append(Delivery(status="failed", error=motivo))
            continue
        template = batch.templates.get(row["template_code"] or "")
        deliveries.append(await provider.enviar(_message(row, template)))
    return deliveries


def _degrades(row: dict[str, Any], entrega: Delivery) -> bool:
    """Uma linha de Telegram que não chegou e tem por que ir pelo número.

    As três causas do docstring. Só uma linha `telegram` entra aqui, e é o que
    garante que a re-rota acontece no máximo uma vez: a linha re-roteada é
    `whatsapp`, e o WhatsApp segue o backoff comum.
    """
    if row["channel"] != TELEGRAM_CHANNEL or entrega.status == "sent":
        return False
    return (
        entrega.error == BLOCKED_ERROR
        or entrega.error in CREDENTIAL_ERRORS
        or row["attempts"] + 1 >= MAX_ATTEMPTS
    )


def _log_params(row: dict[str, Any], entrega: Delivery) -> dict[str, Any]:
    return {
        "queue_id": row["id"],
        "rule_id": row["rule_id"],
        "channel": row["channel"],
        "provider": row["provider"] or "smtp",
        "destination_hash": destination_hash(row["destination"]),
        "provider_message_id": entrega.provider_message_id,
        "status": entrega.status,
        "error": entrega.error,
        "cost_cents": entrega.cost_cents,
    }


async def _degrade(context: SystemContext, row: dict[str, Any], entrega: Delivery) -> str:
    """(c2) para uma linha: o titular, a revogação se `blocked`, a re-rota, ou o
    descarte. Três transações pequenas — ver o docstring do módulo.

    Devolve o status final da linha: `failed` (re-roteada, devida já) ou
    `discarded` (sem titular, sem WhatsApp ativo, sem número, ou re-rota
    recusada pelo gatilho).
    """
    # 1. O titular por trás do chat_id — e, se a pessoa bloqueou o bot, a
    #    revogação com a razão. Comitada antes da re-rota: sobrevive a ela.
    async with tenant_scope(context) as scope:
        await scope.execute(
            _IDENTITY_HOLDER_SQL,
            {"channel": TELEGRAM_CHANNEL, "external_id": row["destination"]},
        )
        holder = await scope.fetchone()
        if holder is not None and entrega.error == BLOCKED_ERROR:
            await scope.execute(
                _REVOKE_PREVIOUS_SQL,
                {
                    "channel": TELEGRAM_CHANNEL,
                    "reason": BLOCKED_REASON,
                    "contact_id": holder["contact_id"],
                    "employee_id": holder["employee_id"],
                },
            )
            for revoked in await scope.fetchall():
                await scope.execute(
                    _AUDIT_SQL,
                    {
                        "entity_id": str(revoked["id"]),
                        "depois": Jsonb({"channel": TELEGRAM_CHANNEL, "reason": BLOCKED_REASON}),
                    },
                )

    # 2. A re-rota, na própria transação. Uma recusa do gatilho sai daqui como
    #    `RaiseException`, desfeita pelo pool; só a frase dele é lida.
    contact_id = holder["contact_id"] if holder is not None else None
    whatsapp: str | None = None
    refused: str | None = None
    if contact_id is not None:
        try:
            async with tenant_scope(context) as scope:
                await scope.execute(outbox._PROVIDER_SQL, {})
                active = await scope.fetchone()
                if active is not None:
                    whatsapp = active["provider"]
                    await scope.execute(
                        _REROUTE_SQL,
                        {
                            "queue_id": row["id"],
                            "contact_id": contact_id,
                            "channel": WHATSAPP_CHANNEL,
                            "provider": whatsapp,
                        },
                    )
                    if await scope.fetchone() is not None:
                        return "failed"
        except errors.RaiseException as refusal:
            refused = refusal.diag.message_primary or "o gatilho recusou a re-rota"

    # 3. Sem para onde ir: descartada, e a recusa do gatilho fica no log.
    async with tenant_scope(context) as scope:
        if refused is not None:
            await scope.execute(
                _LOG_SQL,
                _log_params(
                    {**row, "channel": WHATSAPP_CHANNEL, "provider": whatsapp},
                    Delivery(status="failed", error=f"{REROUTE_REFUSED}: {refused}"),
                ),
            )
        await scope.execute(_DISCARD_SQL, {"queue_id": row["id"]})
    return "discarded"


async def _record(context: SystemContext, batch: _Batch, deliveries: list[Delivery]) -> SendResult:
    """(c1) o log e a marca de todas as linhas, numa transação; (c2) a degradação
    de cada linha de Telegram que não chegou, em transações próprias."""
    sent = failed = discarded = 0
    by_channel: Counter[str] = Counter()
    degrading: list[tuple[dict[str, Any], Delivery]] = []

    async with tenant_scope(context) as scope:
        for row, entrega in zip(batch.rows, deliveries, strict=True):
            await scope.execute(_LOG_SQL, _log_params(row, entrega))
            if entrega.status == "sent":
                await scope.execute(_MARK_SENT_SQL, {"queue_id": row["id"]})
                sent += 1
                by_channel[row["channel"]] += 1
            elif _degrades(row, entrega):
                await scope.execute(_PARK_SQL, {"queue_id": row["id"]})
                degrading.append((row, entrega))
            else:
                await scope.execute(
                    _MARK_FAILED_SQL,
                    {
                        "queue_id": row["id"],
                        "max_attempts": MAX_ATTEMPTS,
                        "wait_minutes": _wait_minutes(row["attempts"]),
                    },
                )
                if (await scope.fetchone())["status"] == "discarded":
                    discarded += 1
                else:
                    failed += 1

    for row, entrega in degrading:
        if await _degrade(context, row, entrega) == "discarded":
            discarded += 1
        else:
            failed += 1

    return SendResult(
        tenant_id=context.tenant_id,
        gate_open=False,
        claimed=len(batch.rows),
        sent=sent,
        failed=failed,
        discarded=discarded,
        recovered=sum(1 for row in batch.rows if row["previous_status"] == "sending"),
        sent_by_channel=dict(by_channel),
    )


async def dispatch(
    context: SystemContext, http: httpx.AsyncClient, *, batch: int = BATCH
) -> SendResult:
    """Consome um lote da fila em três fases. Com o gate aberto, não reserva.

    `http` vem de `verification_client()`: o token do Telegram e do z_api vão
    na URL, e é lá que o log do `httpx` está mudo.
    """
    async with tenant_scope(context) as scope:
        await scope.execute(_GATE_SQL, {})
        gate = await scope.fetchone()
        if not gate["promovido"]:
            motivo = "o motor nunca rodou em produção neste cliente"
        elif not gate["liberado"]:
            motivo = (
                "a entrega nunca foi liberada — o censo não fechou com falso positivo ≤5%, "
                "ou ninguém registrou a liberação"
            )
        else:
            motivo = None
        if motivo is not None:
            await scope.execute(_WAITING_SQL, {})
            waiting = (await scope.fetchone())["waiting"]
            return SendResult(
                tenant_id=context.tenant_id, gate_open=True, gate_reason=motivo, waiting=waiting
            )
        lote = await _claim(scope, batch)

    if not lote.rows:
        return SendResult(tenant_id=context.tenant_id, gate_open=False)

    deliveries = await _deliver(lote, http)
    return await _record(context, lote, deliveries)


async def run(*, batch: int = BATCH) -> list[SendResult]:
    """One dispatch per active tenant — and one tenant's failure is its own.

    A vault that does not answer, a provider that raises what nobody mapped, a
    pool that closes under one tenant: none of it may cost the others their
    batch. The cron runs every quarter hour; a tenant that failed shows up in
    the report by name and is tried again next round, with its stuck `sending`
    rows reclaimed by `STUCK_MINUTES`.
    """
    results: list[SendResult] = []
    async with verification_client() as http:
        for ctx in await active_tenants(TASK):
            try:
                results.append(await dispatch(ctx, http, batch=batch))
            except Exception as exc:  # noqa: BLE001 — the boundary between tenants
                logger.exception("sender: tenant %s falhou no lote", ctx.tenant_id)
                results.append(
                    SendResult(tenant_id=ctx.tenant_id, gate_open=False, error=type(exc).__name__)
                )
    return results


def relatorio(resultados: list[SendResult]) -> str:
    linhas: list[str] = []
    for r in resultados:
        if r.error is not None:
            linhas.append(
                f"tenant {r.tenant_id}: ✗ o lote morreu ({r.error}) — nada reservado neste "
                f"turno; os outros tenants seguiram, e as `sending` presas voltam em "
                f"{STUCK_MINUTES} min."
            )
            continue
        if r.gate_open:
            linhas.append(
                f"tenant {r.tenant_id}: ⛔ gate G4 aberto — {r.waiting} mensagem(ns) esperando, "
                f"nenhuma reservada: {r.gate_reason}. Exige motor em produção E liberação "
                f"registrada (`python -m operax.motor.adjudicacao liberar`, depois de "
                f"`medir` PASSAR)."
            )
            continue
        por_canal = " · ".join(f"{canal} {n}" for canal, n in sorted(r.sent_by_channel.items()))
        linhas.append(
            f"tenant {r.tenant_id}: {r.claimed} reservada(s) · {r.sent} enviada(s)"
            + (f" ({por_canal})" if por_canal else "")
            + f" · {r.failed} de volta para a fila · {r.discarded} descartada(s) · "
            f"{r.recovered} recuperada(s)"
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
