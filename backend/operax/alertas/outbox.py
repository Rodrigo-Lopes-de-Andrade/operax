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

The refusal is of ONE RULE, and it is never fatal (C7). It used to raise, and
the raise killed the whole tenant's batch: a template deactivated in the
afternoon silenced every other rule of that customer, and — because the cycle
had already committed its reservation in a transaction of its own — took that
day's deviations with it, permanently. Now the rule is skipped, named in
`Outbox.skipped` and logged, and the healthy rules beside it still deliver.

THE TRANSACTION IS THE CALLER'S, AND IT IS THE SAME ONE THAT RESERVED
`enqueue` takes a `TenantScope` instead of opening its own, so `ciclo.assemble`
and this module commit together or not at all. Two transactions is what made
"reserved with no message" reachable, and nothing else in this module could
have repaired it: `_RESERVE_SQL` only ever sees `report_cycle_id is null`.

IDEMPOTENCY IS THE KEY, LITERALLY
`idempotency_key` is unique on the table and composed of rule, period, contact,
the half of the rule (messaging or e-mail) and a hash of the content. Re-running
the assembly after a crash does not send twice, and the same cycle re-enqueued
with the same facts is a no-op. The key names the CONTACT and not the
destination on purpose: the channel a contact is reached on is an attribute of
the row (below), and a person adhering to Telegram between two runs must not
turn one message into two.

THE ROUTE IS DECIDED PER PERSON, HERE (SPEC-CANAIS §8)
*"Telegram se houver identidade vigente; WhatsApp caso contrário."* No
preference screen, no column of choice, and the rule never names a channel
other than "messaging" or "e-mail". `route` is the whole of it, as a pure
function: a current `app.messaging_identity` AND a READY bot in the tenant →
the row is `telegram` and its destination is the `chat_id`; anything less →
`whatsapp`, to the number, exactly as before adhesion. Both conditions are
required: an identity without a bot is a chat nobody can reach, and routing to
it would park the message in `failed` instead of reaching the person.

"Ready" is what `public.fn_channel_readiness` says on the Conexões screen —
integration `active` AND `app.channel_health.status = 'connected'` for it —
so the panel and the outbox never disagree about whether Telegram is on. No
health row (the watcher never measured, nobody connected from the screen) is
not ready: fail-closed, to the number. What the sender does when Telegram
fails at delivery time (blocked, dead token, last backoff) is the sender's —
`sender.py`, "degrading" — and only `blocked` revokes the identity.

⛔ The destination of a Telegram row is a `chat_id`. It never goes to a log, a
report line or a response: `Queued` does not carry it, and `relatorio` counts.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from operax.alertas.capacidades import (
    TELEGRAM_CHANNEL,
    WHATSAPP_CHANNEL,
    WHATSAPP_PROVIDERS,
    capabilities_for,
    providers_of,
)
from operax.alertas.ciclo import Cycle
from operax.alertas.saude import HEALTH_CONNECTED
from operax.core.tenant import TenantScope

logger = logging.getLogger(__name__)

#: The one provider that carries Telegram, asked of the matrix. The unpacking
#: is the assertion: a second bot provider would need its own routing decision.
[TELEGRAM_PROVIDER] = providers_of(TELEGRAM_CHANNEL)

#: The rule's e-mail half. Not a channel of the capability matrix (e-mail has
#: no capability to declare) and not a provider name: it is what
#: `app.alert_rule.channel` spells, and `route` hands it back untouched.
EMAIL_CHANNEL = "email"

#: As regras que cobrem uma unidade, com o destino já resolvido. Um destino sai de
#: um contato nomeado na regra ou da responsabilidade dele na unidade — as duas
#: formas que `app.alert_rule_target` aceita. Por responsabilidade, a escolha
#: (primário primeiro) só olha contato ATIVO: um primário desativado cai para o
#: próximo, em vez de ser escolhido e depois descartado pelo `c.active` de fora —
#: o que deixava a regra entregando a ninguém com um segundo responsável ativo
#: (medido no C6).
#:
#: Mais duas colunas desde o C5, as duas entradas de `route`: a identidade de
#: Telegram VIGENTE do contato (`left join lateral` — o índice parcial
#: `messaging_identity_vigente_contact_uk` garante no máximo uma, e o `limit 1`
#: é a forma) e se o tenant tem bot PRONTO — ativo e com a saúde do vigia em
#: `connected`, o mesmo predicado de `public.fn_channel_readiness`. As três
#: fontes ligam o tenant: `%(telegram_providers)s` é
#: `providers_of(TELEGRAM_CHANNEL)`, renderizado como array pelo driver, e
#: `%(telegram_health)s` é `saude.HEALTH_CONNECTED` — nada disso é escrito aqui.
_TARGETS_SQL = """
select r.id as rule_id, r.name as rule_name, r.channel, r.template_code, r.content,
       c.id as contact_id, c.type as contact_type,
       c.whatsapp, c.email,
       mi.external_id as telegram_external_id,
       exists (select 1 from app.integration i
                 join app.channel_health h on h.integration_id = i.id
                where i.tenant_id = %(tenant_id)s
                  and i.active
                  and i.provider = any(%(telegram_providers)s)
                  and h.status = %(telegram_health)s) as telegram_ready
from app.alert_rule r
join app.alert_rule_target t on t.rule_id = r.id
left join app.contact c
       on c.id = coalesce(
            t.contact_id,
            (select ur.contact_id from app.unit_responsible ur
               join app.contact rc on rc.id = ur.contact_id and rc.active
              where ur.unit_id = %(unit_id)s
                and ur.responsibility = t.responsibility
                and ur.tenant_id = %(tenant_id)s
              order by ur.is_primary desc
              limit 1))
left join lateral (
       select mi.external_id
         from app.messaging_identity mi
        where mi.tenant_id = %(tenant_id)s
          and mi.channel = %(telegram_channel)s
          and mi.contact_id = c.id
          and mi.revoked_at is null
        limit 1) mi on true
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

#: O template como ESTE módulo precisa vê-lo: as variáveis que ele exige e o
#: estado dele na Meta. Separada de `_TEMPLATE_SQL` de propósito — aquela é
#: lida por três rotas, e acrescentar coluna lá mexeria nelas sem motivo.
_TEMPLATE_FOR_CYCLE_SQL = """
select variables, meta_status
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

#: O `in (...)` do provedor, renderizado uma vez, em import time. Os valores são
#: a tupla congelada de `operax.alertas.capacidades` — nunca entrada de usuário —
#: e é por isso que entram no texto e não como parâmetro: a instrução que roda é
#: a forma simples para a qual o índice parcial foi escrito, sem adaptação de
#: driver no meio (tupla vira registro, não array, e o `93` só compila o texto).
#: A lista continua tendo um dono só; isto é uma renderização dela.
_WHATSAPP_PROVIDER_LIST = ", ".join(f"'{provider}'" for provider in WHATSAPP_PROVIDERS)

#: O provedor de WhatsApp ativo do tenant. O índice único da migration 14 garante
#: no máximo um, então `limit 1` é a forma e não um desempate.
#:
#: `{whatsapp_providers}` é o único token que não é do psycopg, e
#: `scripts/93_teste_ciclo.py` o renderiza do mesmo jeito para compilar a
#: instrução real.
_PROVIDER_SQL = """
select provider from app.integration
where tenant_id = %(tenant_id)s and active
  and provider in ({whatsapp_providers})
limit 1
""".replace("{whatsapp_providers}", _WHATSAPP_PROVIDER_LIST)


@dataclass(frozen=True, slots=True)
class Queued:
    """Uma linha enfileirada. Sem destino: o de uma linha `telegram` é o chat_id."""

    queue_id: UUID
    rule_name: str
    #: O canal ROTEADO — `telegram`, `whatsapp` ou `email` —, não o da regra.
    channel: str


@dataclass(frozen=True, slots=True)
class Skipped:
    """Uma regra que não consegue montar a mensagem — nomeada, nunca fatal.

    Uma por REGRA, não por alvo: o template é atributo da regra, então todo
    destino dela adoece junto, e repetir a mesma linha por contato só esconde
    quantas regras ficaram de fora.
    """

    rule_id: UUID
    rule_name: str
    template_code: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class Outbox:
    """O que entrou na fila e o que ficou de fora — as duas metades da verdade.

    Ficar de fora sem aparecer no retorno é o que transformava uma regra doente
    em silêncio: quem lê o log do Railway tem de saber qual regra e por quê sem
    abrir o banco.
    """

    queued: list[Queued]
    skipped: list[Skipped]


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


def _key(rule_id: UUID, cycle: Cycle, contact_id: UUID, half: str, payload: dict[str, Any]) -> str:
    """`regra:período:contato:metade:hash(conteúdo)`.

    A SPEC §5 sugeria o destino no lugar do contato. Desde o C5 o destino é
    atributo da linha (`route`), e a chave nomeia quem recebe e por qual metade
    da regra (`whatsapp` ou `email`) — assim a adesão ao Telegram entre duas
    execuções não transforma uma mensagem em duas.
    """
    conteudo = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:16]
    return f"{rule_id}:{cycle.period_end}:{contact_id}:{half}:{digest}"


def route(
    target: Mapping[str, Any], half: str, *, whatsapp_provider: str | None
) -> tuple[str, str | None, str | None]:
    """`(channel, provider, destination)` de uma metade da regra para um contato.

    SPEC-CANAIS §8, inteira: Telegram se o contato tem identidade vigente E o
    tenant tem bot pronto; WhatsApp caso contrário. `email` volta intocado.
    Puro: `target` é uma linha de `_TARGETS_SQL`, e a resposta não depende de
    mais nada. Destino `None` é "esta metade não alcança este contato".
    """
    if half == EMAIL_CHANNEL:
        return EMAIL_CHANNEL, "smtp", target["email"]
    if target["telegram_external_id"] and target["telegram_ready"]:
        return TELEGRAM_CHANNEL, TELEGRAM_PROVIDER, target["telegram_external_id"]
    return WHATSAPP_CHANNEL, whatsapp_provider, target["whatsapp"]


def _pular(
    pulados: dict[UUID, Skipped], alvo: Mapping[str, Any], cycle: Cycle, motivo: str
) -> None:
    """Registra a regra que ficou de fora — uma vez, por regra.

    O log avisa só na primeira: o motivo é atributo da regra, e repeti-lo por
    destino e por ciclo enche o log de linhas idênticas num cliente com trinta
    unidades, a cada quinze minutos.
    """
    if alvo["rule_id"] in pulados:
        return
    pulados[alvo["rule_id"]] = Skipped(
        rule_id=alvo["rule_id"],
        rule_name=alvo["rule_name"],
        template_code=alvo["template_code"],
        reason=motivo,
    )
    logger.warning(
        "outbox: regra %r ficou de fora do ciclo %s — %s",
        alvo["rule_name"],
        cycle.cycle_id,
        motivo,
    )


async def _template_reason(
    scope: TenantScope, code: str, dados: dict[str, Any], *, exige_aprovado: bool
) -> str | None:
    """Por que este template não serve para este ciclo — ou `None` quando serve.

    Uma frase, não uma exceção. A recusa continua sendo a mesma de sempre — o
    módulo não enfileira mensagem que o provedor oficial recusa nem que os não
    oficiais entregam com `{{2}}` no meio —, mas ela agora cabe numa linha de
    log e num relatório, em vez de derrubar o lote do cliente inteiro.

    ⛔ Os três motivos são os três do gatilho `util.validate_alert_template`,
    na mesma ordem. Perguntar aqui o que o gatilho perguntaria é o que mantém a
    recusa PULÁVEL: o que ele recusa de dentro do `insert` estoura a transação
    inteira, e aí não há o que pular — cai o turno do cliente. Um motivo que
    exista lá e falte aqui é um buraco, não uma folga.
    """
    await scope.execute(_TEMPLATE_FOR_CYCLE_SQL, {"code": code})
    template = await scope.fetchone()
    if template is None:
        return f"o template {code!r} não existe ou está inativo neste cliente"
    faltando = [v for v in template["variables"] if v not in dados]
    if faltando:
        return (
            f"o template {code!r} declara {', '.join(faltando)}, e o ciclo não sabe "
            f"responder. O conhecido é: {', '.join(sorted(dados))}"
        )
    if exige_aprovado and template["meta_status"] != "approved":
        return (
            f"o template {code!r} está {template['meta_status']!r} na Meta, e o "
            f"provedor oficial só entrega o que ela aprovou"
        )
    return None


async def enqueue(scope: TenantScope, cycles: list[Cycle], *, base_url: str) -> Outbox:
    """Uma mensagem por (regra, destino, ciclo) — e nenhuma duas vezes.

    O escopo é de quem chamou: esta é a MESMA transação que reservou os desvios
    em `ciclo.assemble`, e as duas commitam juntas ou nenhuma commita. Com
    transações separadas, a reserva ficava de pé e o enfileiramento voltava —
    desvio preso num ciclo sem mensagem, que a reserva do turno seguinte não
    alcança.

    Uma regra que não consegue montar a mensagem é PULADA e nomeada, nunca
    fatal: ela cala a própria audiência, jamais a das outras regras do mesmo
    cliente. O resíduo está declarado na C7 — a audiência da regra doente perde
    aquela janela, porque o ciclo é da unidade e a regra saudável o consome.
    """
    enfileiradas: list[Queued] = []
    #: Por regra, e por isso um dicionário: o template é atributo dela.
    pulados: dict[UUID, Skipped] = {}
    await scope.execute(_PROVIDER_SQL, {})
    linha = await scope.fetchone()
    provider = linha["provider"] if linha else None

    for cycle in cycles:
        dados = facts(cycle, base_url=base_url)
        await scope.execute(
            _TARGETS_SQL,
            {
                "unit_id": cycle.unit_id,
                "telegram_channel": TELEGRAM_CHANNEL,
                "telegram_providers": list(providers_of(TELEGRAM_CHANNEL)),
                "telegram_health": HEALTH_CONNECTED,
            },
        )
        alvos = await scope.fetchall()

        for alvo in alvos:
            metades = (
                (WHATSAPP_CHANNEL, EMAIL_CHANNEL)
                if alvo["channel"] == "both"
                else (alvo["channel"],)
            )
            for metade in metades:
                canal, provedor, destino = route(alvo, metade, whatsapp_provider=provider)
                if not destino:
                    # Contato sem o endereço deste canal. Era um `continue` mudo:
                    # a regra sumia do turno sem aparecer em lugar nenhum, e o
                    # ciclo era desfeito "sem culpado". O motivo não nomeia o
                    # contato — o relatório e o log não carregam destino.
                    _pular(
                        pulados,
                        alvo,
                        cycle,
                        f"o contato desta regra não tem por onde receber {canal}",
                    )
                    continue

                if alvo["template_code"]:
                    # Quem exige template APROVADO é o provedor oficial, e quem
                    # diz isso é a matriz de capacidades — nunca o nome escrito
                    # aqui (SPEC-CANAIS §1). O `canal` na frente mantém a
                    # pergunta dentro de quem a matriz conhece: `smtp` não é
                    # provedor dela, e `capabilities_for` recusa adivinhar.
                    exige_aprovado = (
                        canal == WHATSAPP_CHANNEL
                        and provedor is not None
                        and capabilities_for(provedor).requires_templates
                    )
                    motivo = await _template_reason(
                        scope, alvo["template_code"], dados, exige_aprovado=exige_aprovado
                    )
                    if motivo is not None:
                        _pular(pulados, alvo, cycle, motivo)
                        continue

                await scope.execute(
                    _ENQUEUE_SQL,
                    {
                        "rule_id": alvo["rule_id"],
                        "cycle_id": cycle.cycle_id,
                        "channel": canal,
                        "destination": destino,
                        "payload": json.dumps(dados, ensure_ascii=False),
                        "idempotency_key": _key(
                            alvo["rule_id"], cycle, alvo["contact_id"], metade, dados
                        ),
                        "template_code": alvo["template_code"],
                        "provider": provedor,
                    },
                )
                criada = await scope.fetchone()
                if criada is not None:
                    enfileiradas.append(
                        Queued(
                            queue_id=criada["id"],
                            rule_name=alvo["rule_name"],
                            channel=canal,
                        )
                    )
    return Outbox(queued=enfileiradas, skipped=list(pulados.values()))


def relatorio(resultado: Outbox) -> str:
    """Quantas entraram, por canal roteado, e quem ficou de fora. Nunca um destino."""
    por_canal = Counter(q.channel for q in resultado.queued)
    detalhe = " · ".join(f"{canal} {n}" for canal, n in sorted(por_canal.items()))
    linhas = [
        f"{len(resultado.queued)} mensagem(ns) na fila" + (f" · {detalhe}" if detalhe else "")
    ]
    # Nome da regra e motivo, nunca o destino: quem lê o log do Railway precisa
    # saber quem ficou de fora sem abrir o banco.
    linhas += [f"regra {s.rule_name!r} ficou de fora: {s.reason}" for s in resultado.skipped]
    return "\n".join(linhas)
