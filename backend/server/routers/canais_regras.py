"""Destinatários e regras de alerta — a linha do S6 que nunca foi construída (C6).

Medido em produção em 21/09/2026: 27 unidades, 0 contatos, 0 responsáveis por
unidade, 0 regras, 0 destinos. A esteira inteira — ciclo, outbox, sender, gate
G4 — existe e não tem por onde receber uma regra. Este arquivo é a superfície
que faltava: `/canais/destinatarios` (contatos e a matriz unidade ×
responsabilidade) e `/canais/regras` (regra, destinos, ligar, desligar,
silenciar e o modo de teste do S6).

É UM ARQUIVO À PARTE, E POR QUÊ
`canais.py` tem 1.500 linhas e o `scripts/97_teste_canais.py` pina o conjunto
exato das instruções `_SQL` dele. Acrescentar vinte instruções lá seria mexer
num módulo que não quebrou e reescrever o pino do `97`; um módulo irmão ganha o
próprio pino. O padrão é o mesmo — `_require_admin` (importado, não copiado)
antes de qualquer transação; leitura como o usuário (`user_scope`); escrita e
`app.audit_log` na mesma transação de `tenant_scope`, com o `tenant_id` do token
em cada instrução — e o prefixo é o de `canais.py`, então a tela vê uma API só.

NADA DE DELETE EM CONTATO NEM EM REGRA
Os dois desligam com `active = false`. `app.unit_responsible` e
`app.alert_rule_target` são linhas de ligação: um `PUT` que substitui a matriz
ou os destinos apaga e reinsere na mesma transação, e a trilha leva o antes e o
depois — é o que "substituir" significa, e é o que o outbox lê.

A REGRA 7 É DO GATILHO, E O GATILHO SÓ VÊ O DESTINO
`util.validate_alert_target` dispara em `insert`/`update` de
`app.alert_rule_target` e recusa grupo em regra `individual`. Ele NÃO dispara
quando `app.alert_rule.content` vira `individual` com um grupo já cadastrado,
nem quando `app.contact.type` vira `whatsapp_group` num contato que já é
destino de regra individual — medido no banco de ensaio: os dois `update`
passam. Sem migration, quem fecha as duas portas é esta rota, e fecha SEM
reescrever o predicado: depois de gravar, `_REVALIDATE_*_TARGETS_SQL` re-toca
cada destino afetado (`set rule_id = rule_id`), o gatilho julga de novo com o
conteúdo novo, e a frase dele é o 409. O predicado continua tendo um dono só.

LIGAR É A ÚNICA PORTA, E ELA EXIGE O QUE A ENTREGA EXIGE
Uma regra nasce desligada (migration 06) e `AlertRuleWrite` não tem `active`.
`POST /{id}/ligar` exige ao menos um destino ATIVO (o outbox filtra
`c.active`), e, se o canal inclui mensageria, `template_code` presente, com
template ativo no catálogo e — no provedor oficial — aprovado, porque o gatilho
da fila recusa `meta_cloud` com template fora de `approved` e o `enqueue`
inteiro do tenant morre com ele. Os mesmos juízes valem para um `PUT` numa regra
ligada: o que a deixaria sem condição de entregar é 409, e nada muda.

`blocked_reason` NÃO É UM PREDICADO NOVO
É a leitura de duas fontes que já existem — `public.fn_channel_readiness` (o
canal está pronto?) e `canais._BLOCKED_SQL` (a lista de `BlockedAlertRule` da
tela de Conexões: template ausente, inativo ou não aprovado) — mais o que só a
regra sabe: nenhum destino ativo. Nulo é "nada a apontar", nunca "vai entregar".

O MODO DE TESTE DO S6 — *"rodar primeiro com destino no próprio owner"*
`POST /{id}/testar` enfileira a regra para quem clicou, e só para ele. Quem é
quem clicou: o contato ATIVO, do tipo pessoa, cujo `email` é o e-mail do token
validado — o schema não liga `auth.users` a `app.contact`, e o e-mail assinado
pelo Supabase é o único fato de identidade que os dois lados carregam. O canal
é decidido por `outbox.route`, como na entrega real (Telegram se aderiu e o bot
está pronto; WhatsApp caso contrário; e-mail na metade de e-mail); os fatos são
`outbox.facts` sobre os desvios REAIS da unidade nos últimos sete dias, lidos e
NÃO reservados (reservar seria tirá-los do relatório de verdade — `ciclo.py`);
`declaration` diz que é teste. A chave de idempotência é `outbox._key` com o
sufixo `:test:<test_id>` — cada clique é um teste, e o `test_id` vai para a
trilha. Quem entrega é o sender: com o G4 fechado a linha conta "1 esperando".
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from psycopg import errors
from psycopg.rows import DictRow
from psycopg.types.json import Jsonb

from operax.alertas import outbox
from operax.alertas.capacidades import (
    TELEGRAM_CHANNEL,
    WHATSAPP_CHANNEL,
    Channel,
    channel_of,
    providers_of,
)
from operax.alertas.ciclo import Cycle
from operax.alertas.saude import HEALTH_CONNECTED
from operax.core.config import get_settings
from operax.core.tenant import TenantContext, TenantScope, UserScope, tenant_scope, user_scope
from server.deps import CurrentTenant, CurrentUser
from server.models import (
    AlertRuleRow,
    AlertRuleTargets,
    AlertRuleWrite,
    ContactRow,
    ContactUnits,
    ContactWrite,
    MuteRequest,
    QueuedTestMessage,
    RuleTestResult,
)
from server.routers import canais
from server.routers.canais import _refuse, _require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/canais", tags=["canais"])

_SEM_PERMISSAO_CONTATO = "Gravar destinatários é do administrador do cliente."
_SEM_PERMISSAO_REGRA = "Gravar regras de alerta é do administrador do cliente."
_SEM_PERMISSAO_LER_REGRAS = "Ler regras e destinos é do administrador do cliente."
_SEM_PERMISSAO_TESTAR = "Testar uma regra é do administrador do cliente."

_CONTATO_NAO_ENCONTRADO = "Contato não encontrado."
_UNIDADE_NAO_ENCONTRADA = "Unidade não encontrada."
_REGRA_NAO_ENCONTRADA = "Regra não encontrada."
_TIPO_NAO_ENCONTRADO = "Tipo de desvio não encontrado."

#: As recusas nomeadas, por código. O código é o contrato com a tela.
_REFUSALS = {
    "contact_in_active_rule": (
        "Este contato é destino de regra ligada. Troque o destino nas regras "
        "listadas — ou desligue-as — antes de desativá-lo."
    ),
    "contact_inactive": "Um contato desativado não pode ser destino de regra.",
    "rule_has_no_target": (
        "A regra não tem destino ativo. Cadastre ao menos um destino em Destinos antes de ligar."
    ),
    "template_required": (
        "A mensageria exige um template do catálogo. Escolha um em Templates antes de ligar."
    ),
    "template_not_found": (
        "O template «{template}» não existe ou está inativo no catálogo deste cliente."
    ),
    "template_not_approved": (
        "O template «{template}» está «{meta_status}» na Meta, e o provedor é o oficial: só "
        "«approved» entrega. Aprove antes de ligar."
    ),
    "mute_in_past": "O silêncio termina no passado. Informe uma data futura, com fuso.",
    "caller_has_no_contact": (
        "Para testar, cadastre em Destinatários um contato do tipo pessoa com o seu "
        "e-mail ({email}) e um número de WhatsApp — o teste vai para você."
    ),
    "caller_unreachable": (
        "O seu contato ({name}) não tem por onde receber esta regra: cadastre um "
        "número de WhatsApp (ou adira ao Telegram) para a mensageria, e um e-mail "
        "para a metade de e-mail."
    ),
    "no_channel": (
        "Nenhum canal de mensageria ativo: conecte um WhatsApp (ou o bot do Telegram) "
        "em Conexões antes de testar."
    ),
    "no_unit": "Cadastre uma unidade ativa antes de testar: a mensagem fala de uma unidade.",
    "group_responsibility": (
        "Um grupo de WhatsApp só pode ter a responsabilidade «group» na unidade — é por "
        "ela que a regra 7 o reconhece num destino por responsabilidade."
    ),
    "contact_last_responsible": (
        "Este contato é o único responsável ativo que resolve o destino por "
        "responsabilidade de regra ligada. Cadastre outro responsável na unidade — ou "
        "desligue as regras listadas — antes."
    ),
}

#: O que `blocked_reason` diz em cada estado. As frases dos dois casos de
#: template são as mesmas de `ligar`, porque a causa é a mesma.
_BLOCKED = {
    "no_target": "Nenhum destino ativo: a regra está ligada e não alcança ninguém.",
    "template_required": "Sem template: a mensageria exige um template do catálogo.",
    "template_not_found": _REFUSALS["template_not_found"],
    "template_not_approved": _REFUSALS["template_not_approved"],
    "no_channel": "Nenhum canal de mensageria ativo em Conexões.",
    "email_no_provider": "O e-mail ainda não tem provedor de entrega neste produto.",
}

#: A janela dos fatos do teste: os desvios reais da unidade nos últimos sete
#: dias, até hoje — lidos, nunca reservados.
_TEST_WINDOW_DAYS = 7

# ---------------------------------------------------------------------------
# Destinatários — o SQL
# ---------------------------------------------------------------------------
#: A lista, ou um contato só (`%(contact_id)s` nulo é "todos"). Como o usuário:
#: `contact_read` é `util.has_tenant`, `unit_responsible_read` e `unit_read`
#: são `util.can_see_unit` — a matriz que cada um vê é a das unidades dele.
#: Inativos inclusive: `active` é coluna e a tela decide.
_CONTACTS_SQL = """
select c.id, c.name, c.whatsapp, c.email, c.type, c.active,
       coalesce((
         select json_agg(json_build_object(
                  'unit_id', ur.unit_id, 'unit_name', u.name,
                  'responsibility', ur.responsibility, 'is_primary', ur.is_primary)
                order by u.name, ur.responsibility)
           from app.unit_responsible ur
           join app.unit u on u.id = ur.unit_id
          where ur.tenant_id = c.tenant_id
            and ur.contact_id = c.id), '[]'::json) as units
  from app.contact c
 where c.tenant_id = %(tenant_id)s
   and (%(contact_id)s::uuid is null or c.id = %(contact_id)s)
 order by c.active desc, c.name, c.id
"""

_INSERT_CONTACT_SQL = """
insert into app.contact (tenant_id, name, whatsapp, email, type)
values (%(tenant_id)s, %(name)s, %(whatsapp)s, %(email)s, %(type)s)
returning id, name, whatsapp, email, type, active
"""

#: A CTE `before` é o `antes` da auditoria, lido na mesma foto.
_UPDATE_CONTACT_SQL = """
with before as (
    select id, name, whatsapp, email, type, active
      from app.contact
     where tenant_id = %(tenant_id)s and id = %(contact_id)s
)
update app.contact c
   set name = %(name)s, whatsapp = %(whatsapp)s, email = %(email)s, type = %(type)s
  from before b
 where c.id = b.id and c.tenant_id = %(tenant_id)s
returning c.id, c.name, c.whatsapp, c.email, c.type, c.active,
          (select to_jsonb(b) from before b) as before
"""

#: Desligar, nunca apagar. Já inativo é zero linhas — e nada a auditar.
_DEACTIVATE_CONTACT_SQL = """
update app.contact
   set active = false
 where tenant_id = %(tenant_id)s and id = %(contact_id)s and active
returning id
"""

#: As regras LIGADAS que nomeiam o contato como destino direto. É o 409 de
#: `desativar`: um contato que some de baixo de uma regra ligada deixaria a
#: regra entregando a ninguém, em silêncio. O destino por responsabilidade
#: não entra: ele é da unidade, não do contato, e o outbox resolve por unidade.
_CONTACT_ACTIVE_RULES_SQL = """
select distinct r.id, r.name
  from app.alert_rule r
  join app.alert_rule_target t on t.rule_id = r.id
 where r.tenant_id = %(tenant_id)s
   and r.active
   and t.contact_id = %(contact_id)s
 order by r.name, r.id
"""

#: O contato, como o usuário — inativo inclusive (editar um inativo é permitido).
# As responsabilidades que não são `group` deste contato: um grupo não pode
# tê-las (o outbox o resolveria para uma regra individual sem o gatilho ver).
# É a mesma cerca de `PUT /unidades`, olhando do outro lado — mudar o `type`.
_NON_GROUP_RESPONSIBILITY_SQL = """
select ur.unit_id, ur.responsibility
  from app.unit_responsible ur
 where ur.tenant_id = %(tenant_id)s
   and ur.contact_id = %(contact_id)s
   and ur.responsibility <> 'group'
"""
# As regras LIGADAS cujo destino por responsabilidade deixa de resolver em
# alguma unidade se este contato perder as responsabilidades que não estão em
# `kept` (desativar: nenhuma fica; `PUT /unidades`: fica o que a matriz nova
# repete). Resolve = há outro contato ATIVO com a mesma responsabilidade na
# unidade — o predicado do outbox, que já filtra `c.active` antes de escolher.
_LAST_RESPONSIBLE_RULES_SQL = """
select distinct r.id, r.name
  from app.unit_responsible ur
  join app.contact me on me.id = ur.contact_id and me.active
  join app.alert_rule r
    on r.tenant_id = ur.tenant_id
   and r.active
   and (r.scope_unit_id is null or r.scope_unit_id = ur.unit_id)
  join app.alert_rule_target t
    on t.rule_id = r.id
   and t.responsibility = ur.responsibility
 where ur.tenant_id = %(tenant_id)s
   and ur.contact_id = %(contact_id)s
   and not exists (
         select 1
           from unnest(%(kept_unit_ids)s::uuid[], %(kept_responsibilities)s::text[])
                as k(unit_id, responsibility)
          where k.unit_id = ur.unit_id and k.responsibility = ur.responsibility)
   and not exists (
         select 1
           from app.unit_responsible o
           join app.contact c on c.id = o.contact_id and c.active
          where o.tenant_id = ur.tenant_id
            and o.unit_id = ur.unit_id
            and o.responsibility = ur.responsibility
            and o.contact_id <> ur.contact_id)
 order by r.name, r.id
"""
_VISIBLE_CONTACT_SQL = """
select c.id, c.name, c.type, c.active
  from app.contact c
 where c.tenant_id = %(tenant_id)s and c.id = %(contact_id)s
"""

#: Os contatos de uma lista, como o usuário: o que faltar não é do tenant.
_VISIBLE_CONTACTS_SQL = """
select c.id, c.name, c.type, c.active
  from app.contact c
 where c.tenant_id = %(tenant_id)s
   and c.id = any(%(contact_ids)s::uuid[])
"""

#: As unidades de uma lista, como o usuário (`unit_read` = `can_see_unit`).
_VISIBLE_UNITS_SQL = """
select u.id, u.name
  from app.unit u
 where u.tenant_id = %(tenant_id)s
   and u.id = any(%(unit_ids)s::uuid[])
"""

#: A matriz é linha de ligação: apagar e reinserir é o `PUT`. O `returning` do
#: `delete` é o `antes` da trilha.
_DELETE_UNIT_RESPONSIBLE_SQL = """
delete from app.unit_responsible ur
 where ur.tenant_id = %(tenant_id)s and ur.contact_id = %(contact_id)s
returning ur.unit_id, ur.responsibility, ur.is_primary
"""

#: O `join` em `app.unit` pelo tenant é a segunda cerca: uma unidade de outro
#: tenant já foi 404 como o usuário; aqui ela simplesmente não entra, e a rota
#: confere que entraram todas.
_INSERT_UNIT_RESPONSIBLE_SQL = """
insert into app.unit_responsible (tenant_id, unit_id, contact_id, responsibility, is_primary)
select c.tenant_id, u.id, c.id, v.responsibility, v.is_primary
  from app.contact c
  cross join unnest(%(unit_ids)s::uuid[], %(responsibilities)s::text[], %(primaries)s::boolean[])
       as v(unit_id, responsibility, is_primary)
  join app.unit u on u.id = v.unit_id and u.tenant_id = c.tenant_id
 where c.tenant_id = %(tenant_id)s and c.id = %(contact_id)s
returning unit_id, responsibility, is_primary
"""

#: Depois de mudar `type`, o gatilho julga de novo cada destino que nomeia o
#: contato — é a regra 7 pela porta do contato (ver o docstring do módulo).
_REVALIDATE_CONTACT_TARGETS_SQL = """
update app.alert_rule_target t
   set rule_id = t.rule_id
  from app.alert_rule r
 where r.id = t.rule_id
   and r.tenant_id = %(tenant_id)s
   and t.contact_id = %(contact_id)s
returning t.id
"""

# ---------------------------------------------------------------------------
# Regras — o SQL
# ---------------------------------------------------------------------------
#: A lista, ou uma regra só. Como o usuário, e só o administrador chega aqui:
#: `regra_destino_admin` é a única policy de `app.alert_rule_target`, então um
#: membro que não é admin veria toda regra com `targets: []` — e um
#: `blocked_reason` "nenhum destino" falso. `contact_active` é o que `ligar`
#: e `blocked_reason` contam; `contact_name` é nulo no destino por
#: responsabilidade.
_RULES_SQL = """
select r.id, r.name, r.deviation_type, r.scope_unit_id, u.name as scope_unit_name,
       r.content, r.channel, r.cron_window, r.threshold_minutes, r.threshold_occurrences,
       r.muted_until, r.template_code, r.active,
       coalesce((
         select json_agg(json_build_object(
                  'id', t.id, 'contact_id', t.contact_id, 'contact_name', c.name,
                  'contact_active', c.active, 'responsibility', t.responsibility)
                order by c.name, t.responsibility, t.id)
           from app.alert_rule_target t
           left join app.contact c on c.id = t.contact_id and c.tenant_id = r.tenant_id
          where t.rule_id = r.id), '[]'::json) as targets
  from app.alert_rule r
  left join app.unit u on u.id = r.scope_unit_id and u.tenant_id = r.tenant_id
 where r.tenant_id = %(tenant_id)s
   and (%(rule_id)s::uuid is null or r.id = %(rule_id)s)
 order by r.active desc, r.name, r.id
"""

#: A regra, como o usuário — o 404 antes de qualquer escrita.
_VISIBLE_RULE_SQL = """
select r.id, r.name, r.content, r.channel, r.template_code, r.active, r.scope_unit_id
  from app.alert_rule r
 where r.tenant_id = %(tenant_id)s and r.id = %(rule_id)s
"""

#: O catálogo é global (sem `tenant_id`, policy `using (true)`): roda como o
#: usuário, porque `tenant_scope` recusaria a instrução — e deve.
_DEVIATION_TYPE_SQL = """
select code from app.deviation_type where code = %(code)s
"""

#: `active` é o literal `false`: a regra nasce desligada, e não há parâmetro
#: que mude isso. `tests/test_canais_regras.py` prende o literal.
_INSERT_RULE_SQL = """
insert into app.alert_rule
  (tenant_id, name, deviation_type, scope_unit_id, content, channel, cron_window,
   threshold_minutes, threshold_occurrences, template_code, active)
values
  (%(tenant_id)s, %(name)s, %(deviation_type)s, %(scope_unit_id)s, %(content)s, %(channel)s,
   %(cron_window)s, %(threshold_minutes)s, %(threshold_occurrences)s, %(template_code)s, false)
returning id
"""

#: Nem `active` nem `muted_until` entram aqui: são de `ligar`/`desligar` e de
#: `silenciar`, cada um com a própria trilha.
_UPDATE_RULE_SQL = """
with before as (
    select id, name, deviation_type, scope_unit_id, content, channel, cron_window,
           threshold_minutes, threshold_occurrences, template_code, active, muted_until
      from app.alert_rule
     where tenant_id = %(tenant_id)s and id = %(rule_id)s
)
update app.alert_rule r
   set name = %(name)s, deviation_type = %(deviation_type)s,
       scope_unit_id = %(scope_unit_id)s, content = %(content)s, channel = %(channel)s,
       cron_window = %(cron_window)s, threshold_minutes = %(threshold_minutes)s,
       threshold_occurrences = %(threshold_occurrences)s, template_code = %(template_code)s
  from before b
 where r.id = b.id and r.tenant_id = %(tenant_id)s
returning r.id, r.name, r.channel, r.template_code, r.active,
          (select to_jsonb(b) from before b) as before
"""

#: Depois de mudar `content`, o gatilho julga de novo cada destino da regra —
#: é a regra 7 pela porta da regra (ver o docstring do módulo).
_REVALIDATE_RULE_TARGETS_SQL = """
update app.alert_rule_target t
   set rule_id = t.rule_id
  from app.alert_rule r
 where r.id = t.rule_id
   and r.tenant_id = %(tenant_id)s
   and r.id = %(rule_id)s
returning t.id
"""

_SET_RULE_ACTIVE_SQL = """
update app.alert_rule
   set active = %(active)s
 where tenant_id = %(tenant_id)s and id = %(rule_id)s
returning id, active
"""

_MUTE_RULE_SQL = """
update app.alert_rule
   set muted_until = %(until)s
 where tenant_id = %(tenant_id)s and id = %(rule_id)s
returning id, muted_until
"""

#: Os destinos que contam: por responsabilidade, ou contato ATIVO — o mesmo
#: `c.active` que `outbox._TARGETS_SQL` filtra. Um contato de outro tenant
#: ligado por engano cai no `null` do `left join` e não conta.
_ACTIVE_TARGETS_SQL = """
select count(*)::int as n
  from app.alert_rule_target t
  join app.alert_rule r on r.id = t.rule_id
  left join app.contact c on c.id = t.contact_id and c.tenant_id = r.tenant_id
 where r.tenant_id = %(tenant_id)s
   and r.id = %(rule_id)s
   and (t.contact_id is null or c.active)
"""

_DELETE_TARGETS_SQL = """
delete from app.alert_rule_target t
 using app.alert_rule r
 where r.id = t.rule_id
   and r.tenant_id = %(tenant_id)s
   and r.id = %(rule_id)s
returning t.contact_id, t.responsibility
"""

#: O `left join` pelo tenant é a segunda cerca do contato (a primeira é o 404
#: como o usuário): um contato de outro tenant não entra, e a rota confere que
#: entraram todos. Cada linha passa por `util.validate_alert_target`.
_INSERT_TARGETS_SQL = """
insert into app.alert_rule_target (rule_id, contact_id, responsibility)
select r.id, c.id, v.responsibility
  from app.alert_rule r
  cross join unnest(%(contact_ids)s::uuid[], %(responsibilities)s::text[])
       as v(contact_id, responsibility)
  left join app.contact c on c.id = v.contact_id and c.tenant_id = r.tenant_id
 where r.tenant_id = %(tenant_id)s
   and r.id = %(rule_id)s
   and (v.contact_id is null or c.id is not null)
returning id, contact_id, responsibility
"""

_AUDIT_SQL = """
insert into app.audit_log
  (tenant_id, user_id, action, entity, entity_id, antes, depois)
values
  (%(tenant_id)s, %(user_id)s, %(action)s, %(entity)s, %(entity_id)s, %(antes)s, %(depois)s)
"""

# ---------------------------------------------------------------------------
# O teste — o SQL
# ---------------------------------------------------------------------------
#: Quem clicou, como o usuário: o contato ativo, pessoa, com o e-mail do token.
#: Só pessoa — o teste é conteúdo para uma pessoa, e um grupo com o e-mail do
#: administrador seria a regra 7 pela porta do teste.
_CALLER_CONTACT_SQL = """
select c.id, c.name
  from app.contact c
 where c.tenant_id = %(tenant_id)s
   and c.active
   and c.type = 'person'
   and lower(c.email) = lower(%(email)s)
 order by c.created_at, c.id
 limit 1
"""

#: As duas entradas de `outbox.route` para o chamador — a identidade de
#: Telegram vigente e o bot pronto — escritas EXATAMENTE como em
#: `outbox._TARGETS_SQL`: `tests/test_canais_regras.py` compara os dois blocos
#: por texto, e o `97` executa os dois. `%(telegram_providers)s` é
#: `providers_of(TELEGRAM_CHANNEL)`, `%(telegram_health)s` é `HEALTH_CONNECTED`.
_CALLER_ROUTE_SQL = """
select c.id as contact_id, c.type as contact_type,
       c.whatsapp, c.email,
       mi.external_id as telegram_external_id,
       exists (select 1 from app.integration i
                 join app.channel_health h on h.integration_id = i.id
                where i.tenant_id = %(tenant_id)s
                  and i.active
                  and i.provider = any(%(telegram_providers)s)
                  and h.status = %(telegram_health)s) as telegram_ready
from app.contact c
left join lateral (
       select mi.external_id
         from app.messaging_identity mi
        where mi.tenant_id = %(tenant_id)s
          and mi.channel = %(telegram_channel)s
          and mi.contact_id = c.id
          and mi.revoked_at is null
        limit 1) mi on true
where c.tenant_id = %(tenant_id)s
  and c.id = %(contact_id)s
  and c.active
"""

#: A unidade de que a mensagem fala: a do recorte da regra, ou a primeira ativa
#: por nome quando a regra cobre todas. Como o usuário.
_TEST_UNIT_SQL = """
select u.id, u.name
  from app.unit u
 where u.tenant_id = %(tenant_id)s
   and u.active
   and (%(unit_id)s::uuid is null or u.id = %(unit_id)s)
 order by u.name, u.id
 limit 1
"""

#: Os fatos reais da janela: os desvios ATIVOS de produção da unidade no
#: período, reservados ou não — um teste não move nada, então não filtra
#: `report_cycle_id is null` como `ciclo._RESERVE_SQL` faz. Só contagem: nada
#: individual sai daqui.
_TEST_FACTS_SQL = """
select count(*)::int as total_events,
       coalesce(sum(abs(d.minutes)), 0)::int as deviation_minutes
  from app.deviation_event d
 where d.tenant_id = %(tenant_id)s
   and d.unit_id = %(unit_id)s
   and d.status = 'active'
   and d.mode = 'production'
   and d.reference_date between %(de)s::date and %(ate)s::date
"""


class _RefusedError(ValueError):
    """Uma recusa nomeada levantada de dentro da transação — a saída por
    exceção é o rollback do `tenant_scope`; a rota a traduz em resposta."""

    def __init__(self, code: str, detail: str, status_code: int, **extra: Any) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code
        self.extra = extra


def _conflict(refusal: str, **values: Any) -> _RefusedError:
    """409 nomeado; `values` preenche a frase e volta no corpo ao lado dela."""
    return _RefusedError(
        refusal, _REFUSALS[refusal].format(**values), status.HTTP_409_CONFLICT, **values
    )


def _holding_rules(refusal: str, rows: list[DictRow]) -> _RefusedError:
    """409 com as regras ligadas que seguram o contato — a tela as lista."""
    return _conflict(refusal, rules=[{"id": str(r["id"]), "name": r["name"]} for r in rows])


def _refusal(recusa: _RefusedError) -> JSONResponse:
    return _refuse(recusa.detail, recusa.code, status_code=recusa.status_code, **recusa.extra)


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _trigger_phrase(recusa: errors.RaiseException, fallback: str) -> str:
    """A frase do gatilho, e só ela: já é pt-BR e nomeia o que foi recusado."""
    return recusa.diag.message_primary or fallback


async def _audit(
    bound: TenantScope,
    tenant: TenantContext,
    *,
    action: str,
    entity: str,
    entity_id: str | None,
    antes: Any,
    depois: Any,
) -> None:
    await bound.execute(
        _AUDIT_SQL,
        {
            "user_id": tenant.user_id,
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "antes": Jsonb(antes) if antes is not None else None,
            "depois": Jsonb(depois) if depois is not None else None,
        },
    )


# ---------------------------------------------------------------------------
# Destinatários
# ---------------------------------------------------------------------------
def _contact_row(row: Mapping[str, Any]) -> ContactRow:
    return ContactRow(
        id=row["id"],
        name=row["name"],
        whatsapp=row["whatsapp"],
        email=row["email"],
        type=row["type"],
        active=row["active"],
        units=row["units"],
    )


async def _contacts(tenant: TenantContext, contact_id: UUID | None = None) -> list[ContactRow]:
    async with user_scope(tenant) as scope:
        await scope.execute(
            _CONTACTS_SQL,
            {
                "tenant_id": str(tenant.tenant_id),
                "contact_id": str(contact_id) if contact_id is not None else None,
            },
        )
        rows = await scope.fetchall()
    return [_contact_row(row) for row in rows]


async def _contact(tenant: TenantContext, contact_id: UUID) -> ContactRow:
    rows = await _contacts(tenant, contact_id)
    if not rows:
        raise RuntimeError("o contato recém-gravado não voltou na releitura")
    [row] = rows
    return row


async def _visible_contact(tenant: TenantContext, contact_id: UUID) -> DictRow:
    """O contato, como o usuário — ou 404 antes de qualquer escrita."""
    async with user_scope(tenant) as scope:
        await scope.execute(
            _VISIBLE_CONTACT_SQL,
            {"tenant_id": str(tenant.tenant_id), "contact_id": str(contact_id)},
        )
        row = await scope.fetchone()
    if row is None:
        raise _not_found(_CONTATO_NAO_ENCONTRADO)
    return row


def _contact_fields(request: ContactWrite) -> dict[str, Any]:
    return {
        "name": request.name,
        "whatsapp": request.whatsapp,
        "email": request.email,
        "type": request.type,
    }


def _for_audit(contact: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """A linha do contato como vai para a trilha: o número só pelos quatro
    últimos dígitos. SPEC §5, "destino em claro": o log de longo prazo não
    precisa do telefone — a fila o tem enquanto entrega, e só ela."""
    if contact is None:
        return None
    whatsapp = contact.get("whatsapp")
    return {
        **{k: v for k, v in contact.items() if k != "id"},
        "whatsapp": f"•••{whatsapp[-4:]}" if whatsapp else None,
    }


@router.get("/destinatarios/contatos")
async def contacts(tenant: CurrentTenant) -> list[ContactRow]:
    """Os contatos do cliente, com a matriz de unidades que quem pede enxerga.

    Qualquer membro: `contact_read` é `util.has_tenant`. A matriz vem recortada
    por `util.can_see_unit` — um supervisor vê as responsabilidades das unidades
    dele. É o desenho, e a rota não filtra por papel.
    """
    return await _contacts(tenant)


@router.post("/destinatarios/contatos", status_code=status.HTTP_201_CREATED)
async def create_contact(tenant: CurrentTenant, request: ContactWrite) -> ContactRow:
    """Cria o contato e devolve a linha relida como o usuário."""
    await _require_admin(tenant, _SEM_PERMISSAO_CONTATO)
    async with tenant_scope(tenant) as bound:
        await bound.execute(_INSERT_CONTACT_SQL, _contact_fields(request))
        row = await bound.fetchone()
        if row is None:
            raise RuntimeError("o insert de app.contact não devolveu a linha gravada")
        await _audit(
            bound,
            tenant,
            action="insert",
            entity="contact",
            entity_id=str(row["id"]),
            antes=None,
            depois=_for_audit(_contact_fields(request) | {"active": row["active"]}),
        )
        contact_id = row["id"]
    return await _contact(tenant, contact_id)


@router.put("/destinatarios/contatos/{contact_id}")
async def update_contact(
    tenant: CurrentTenant, contact_id: UUID, request: ContactWrite
) -> ContactRow:
    """Edita o contato. 404 como o usuário antes de escrever.

    Mudar `type` para grupo num contato que é destino de regra `individual` é
    recusado pelo gatilho, re-tocado sobre cada destino do contato — 409 com a
    frase dele. E um contato que já tem responsabilidade que não é `group` na
    matriz não vira grupo: 422, a cerca de `PUT /unidades` pelo outro lado.
    """
    await _require_admin(tenant, _SEM_PERMISSAO_CONTATO)
    await _visible_contact(tenant, contact_id)
    try:
        async with tenant_scope(tenant) as bound:
            if request.type == "whatsapp_group":
                await bound.execute(_NON_GROUP_RESPONSIBILITY_SQL, {"contact_id": str(contact_id)})
                if await bound.fetchall():
                    raise _RefusedError(
                        "group_responsibility",
                        _REFUSALS["group_responsibility"],
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                    )
            await bound.execute(
                _UPDATE_CONTACT_SQL, {"contact_id": str(contact_id), **_contact_fields(request)}
            )
            row = await bound.fetchone()
            if row is None:
                raise RuntimeError("o update de app.contact não alcançou o contato do tenant")
            try:
                await bound.execute(
                    _REVALIDATE_CONTACT_TARGETS_SQL, {"contact_id": str(contact_id)}
                )
                await bound.fetchall()
            except errors.RaiseException as recusa:
                raise _RefusedError(
                    "individual_to_group",
                    _trigger_phrase(recusa, "O gatilho recusou o destino."),
                    status.HTTP_409_CONFLICT,
                ) from None
            await _audit(
                bound,
                tenant,
                action="update",
                entity="contact",
                entity_id=str(contact_id),
                antes=_for_audit(row["before"]),
                depois=_for_audit(_contact_fields(request) | {"active": row["active"]}),
            )
    except _RefusedError as recusa:
        return _refusal(recusa)
    return await _contact(tenant, contact_id)


@router.post("/destinatarios/contatos/{contact_id}/desativar")
async def deactivate_contact(tenant: CurrentTenant, contact_id: UUID) -> ContactRow:
    """`active = false`, nunca `delete`.

    Se o contato é destino direto de regra LIGADA, 409 `contact_in_active_rule`
    com as regras — desativar por baixo delas as deixaria entregando a ninguém.
    Se é o último responsável ativo que resolve o destino por responsabilidade
    de uma regra ligada em alguma unidade, 409 `contact_last_responsible`, pelo
    mesmo motivo. Já inativo é idempotente: nada muda, nada é auditado.
    """
    await _require_admin(tenant, _SEM_PERMISSAO_CONTATO)
    await _visible_contact(tenant, contact_id)
    try:
        async with tenant_scope(tenant) as bound:
            await bound.execute(_CONTACT_ACTIVE_RULES_SQL, {"contact_id": str(contact_id)})
            rules = await bound.fetchall()
            if rules:
                raise _holding_rules("contact_in_active_rule", rules)
            await bound.execute(
                _LAST_RESPONSIBLE_RULES_SQL,
                {"contact_id": str(contact_id), "kept_unit_ids": [], "kept_responsibilities": []},
            )
            rules = await bound.fetchall()
            if rules:
                raise _holding_rules("contact_last_responsible", rules)
            await bound.execute(_DEACTIVATE_CONTACT_SQL, {"contact_id": str(contact_id)})
            if await bound.fetchone() is not None:
                await _audit(
                    bound,
                    tenant,
                    action="update",
                    entity="contact",
                    entity_id=str(contact_id),
                    antes={"active": True},
                    depois={"active": False},
                )
    except _RefusedError as recusa:
        return _refusal(recusa)
    return await _contact(tenant, contact_id)


@router.put("/destinatarios/contatos/{contact_id}/unidades")
async def replace_contact_units(
    tenant: CurrentTenant, contact_id: UUID, request: ContactUnits
) -> ContactRow:
    """Substitui a matriz unidade × responsabilidade do contato.

    Contato e unidades são conferidos como o usuário (404) antes da transação;
    dentro dela, apagar e reinserir, e a trilha com o antes e o depois.

    Um `whatsapp_group` só entra como `group`: `util.validate_alert_target` só
    vê `responsibility = 'group'` no destino por responsabilidade, e um grupo
    como `unit_manager` seria resolvido pelo outbox para uma regra individual
    sem que o gatilho tivesse o que recusar.

    Tirar da matriz a responsabilidade que uma regra LIGADA resolve por ela,
    sem outro responsável ativo na unidade, é 409 `contact_last_responsible`
    listando as regras — a mesma cerca de `desativar`, na mesma transação.
    """
    await _require_admin(tenant, _SEM_PERMISSAO_CONTATO)
    contact = await _visible_contact(tenant, contact_id)
    if contact["type"] == "whatsapp_group" and any(
        u.responsibility != "group" for u in request.units
    ):
        return _refuse(_REFUSALS["group_responsibility"], "group_responsibility")
    unit_ids = sorted({str(u.unit_id) for u in request.units})
    if unit_ids:
        async with user_scope(tenant) as scope:
            await scope.execute(
                _VISIBLE_UNITS_SQL, {"tenant_id": str(tenant.tenant_id), "unit_ids": unit_ids}
            )
            visible = {str(row["id"]) for row in await scope.fetchall()}
        if visible != set(unit_ids):
            raise _not_found(_UNIDADE_NAO_ENCONTRADA)

    depois = [
        {"unit_id": str(u.unit_id), "responsibility": u.responsibility, "is_primary": u.is_primary}
        for u in request.units
    ]
    try:
        async with tenant_scope(tenant) as bound:
            await bound.execute(
                _LAST_RESPONSIBLE_RULES_SQL,
                {
                    "contact_id": str(contact_id),
                    "kept_unit_ids": [u["unit_id"] for u in depois],
                    "kept_responsibilities": [u["responsibility"] for u in depois],
                },
            )
            rules = await bound.fetchall()
            if rules:
                raise _holding_rules("contact_last_responsible", rules)
            await bound.execute(_DELETE_UNIT_RESPONSIBLE_SQL, {"contact_id": str(contact_id)})
            antes = [
                {
                    "unit_id": str(r["unit_id"]),
                    "responsibility": r["responsibility"],
                    "is_primary": r["is_primary"],
                }
                for r in await bound.fetchall()
            ]
            if request.units:
                await bound.execute(
                    _INSERT_UNIT_RESPONSIBLE_SQL,
                    {
                        "contact_id": str(contact_id),
                        "unit_ids": [str(u.unit_id) for u in request.units],
                        "responsibilities": [u.responsibility for u in request.units],
                        "primaries": [u.is_primary for u in request.units],
                    },
                )
                inserted = await bound.fetchall()
                if len(inserted) != len(request.units):
                    raise RuntimeError("a matriz gravada não tem todas as linhas pedidas")
            await _audit(
                bound,
                tenant,
                action="update",
                entity="unit_responsible",
                entity_id=str(contact_id),
                antes=antes,
                depois=depois,
            )
    except _RefusedError as recusa:
        return _refusal(recusa)
    return await _contact(tenant, contact_id)


# ---------------------------------------------------------------------------
# Regras — leitura e `blocked_reason`
# ---------------------------------------------------------------------------
def blocked_reason(
    rule: Mapping[str, Any],
    readiness: Mapping[Channel, Mapping[str, Any]],
    blocked: list[Mapping[str, Any]],
) -> str | None:
    """O que impede a regra LIGADA de entregar hoje, ou nada.

    Puro. `readiness` é `fn_channel_readiness` por canal; `blocked` é a lista
    de `canais._BLOCKED_SQL` (o predicado da CTE da função). A ordem é a ordem
    em que o administrador resolve: destino, template, canal.
    """
    if not rule["active"]:
        return None
    if not any(t["contact_id"] is None or t["contact_active"] for t in rule["targets"]):
        return _BLOCKED["no_target"]
    if rule["channel"] not in (WHATSAPP_CHANNEL, "both"):
        return _BLOCKED["email_no_provider"]
    if rule["template_code"] is None:
        return _BLOCKED["template_required"]
    rows = [
        b
        for b in blocked
        if b["rule_name"] == rule["name"] and b["template_code"] == rule["template_code"]
    ]
    whatsapp = readiness.get(WHATSAPP_CHANNEL)
    if any(b["meta_status"] is None for b in rows):
        return _BLOCKED["template_not_found"].format(template=rule["template_code"])
    if whatsapp is not None and whatsapp["official"] and rows:
        return _BLOCKED["template_not_approved"].format(
            template=rule["template_code"], meta_status=rows[0]["meta_status"]
        )
    bot = readiness.get(TELEGRAM_CHANNEL)
    if whatsapp is None and not (bot is not None and bot["ready"]):
        return _BLOCKED["no_channel"]
    return None


def _rule_row(row: Mapping[str, Any], reason: str | None) -> AlertRuleRow:
    return AlertRuleRow(
        id=row["id"],
        name=row["name"],
        deviation_type=row["deviation_type"],
        scope_unit_id=row["scope_unit_id"],
        scope_unit_name=row["scope_unit_name"],
        content=row["content"],
        channel=row["channel"],
        cron_window=row["cron_window"],
        threshold_minutes=row["threshold_minutes"],
        threshold_occurrences=row["threshold_occurrences"],
        muted_until=row["muted_until"],
        template_code=row["template_code"],
        active=row["active"],
        targets=row["targets"],
        blocked_reason=reason,
    )


async def _readiness(scope: UserScope, tenant: TenantContext) -> dict[Channel, DictRow]:
    """`fn_channel_readiness` por canal, como `canais._connections` a lê."""
    await scope.execute(canais._READINESS_SQL, {"tenant_id": str(tenant.tenant_id)})
    return {channel_of(row["provider"]): row for row in await scope.fetchall()}


async def _rules(tenant: TenantContext, rule_id: UUID | None = None) -> list[AlertRuleRow]:
    async with user_scope(tenant) as scope:
        await scope.execute(
            _RULES_SQL,
            {
                "tenant_id": str(tenant.tenant_id),
                "rule_id": str(rule_id) if rule_id is not None else None,
            },
        )
        rows = await scope.fetchall()
        readiness = await _readiness(scope, tenant)
        await scope.execute(canais._BLOCKED_SQL, {"tenant_id": str(tenant.tenant_id)})
        blocked = await scope.fetchall()
    return [_rule_row(row, blocked_reason(row, readiness, blocked)) for row in rows]


async def _rule(tenant: TenantContext, rule_id: UUID) -> AlertRuleRow:
    rows = await _rules(tenant, rule_id)
    if not rows:
        raise RuntimeError("a regra recém-gravada não voltou na releitura")
    [row] = rows
    return row


async def _visible_rule(tenant: TenantContext, rule_id: UUID) -> DictRow:
    """A regra, como o usuário — ou 404 antes de qualquer escrita."""
    async with user_scope(tenant) as scope:
        await scope.execute(
            _VISIBLE_RULE_SQL, {"tenant_id": str(tenant.tenant_id), "rule_id": str(rule_id)}
        )
        row = await scope.fetchone()
    if row is None:
        raise _not_found(_REGRA_NAO_ENCONTRADA)
    return row


@router.get("/regras")
async def rules(tenant: CurrentTenant) -> list[AlertRuleRow]:
    """As regras do cliente, com destinos e `blocked_reason`. Administrador:
    ver o docstring de `_RULES_SQL`."""
    await _require_admin(tenant, _SEM_PERMISSAO_LER_REGRAS)
    return await _rules(tenant)


# ---------------------------------------------------------------------------
# Regras — escrita
# ---------------------------------------------------------------------------
async def _check_rule_references(tenant: TenantContext, request: AlertRuleWrite) -> None:
    """Tipo de desvio, unidade do recorte e template, como o usuário, antes de
    escrever. 404 para os dois primeiros; 422 `template_not_found` para o
    terceiro — a pessoa descobre agora, não ao ligar."""
    async with user_scope(tenant) as scope:
        if request.deviation_type is not None:
            await scope.execute(_DEVIATION_TYPE_SQL, {"code": request.deviation_type})
            if await scope.fetchone() is None:
                raise _not_found(_TIPO_NAO_ENCONTRADO)
        if request.scope_unit_id is not None:
            await scope.execute(
                _VISIBLE_UNITS_SQL,
                {"tenant_id": str(tenant.tenant_id), "unit_ids": [str(request.scope_unit_id)]},
            )
            if not await scope.fetchall():
                raise _not_found(_UNIDADE_NAO_ENCONTRADA)
        if request.template_code is not None:
            await scope.execute(
                outbox._TEMPLATE_SQL,
                {"tenant_id": str(tenant.tenant_id), "code": request.template_code},
            )
            if await scope.fetchone() is None:
                raise _RefusedError(
                    "template_not_found",
                    _REFUSALS["template_not_found"].format(template=request.template_code),
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    template=request.template_code,
                )


def _rule_fields(request: AlertRuleWrite) -> dict[str, Any]:
    return {
        "name": request.name,
        "deviation_type": request.deviation_type,
        "scope_unit_id": str(request.scope_unit_id) if request.scope_unit_id else None,
        "content": request.content,
        "channel": request.channel,
        "cron_window": request.cron_window,
        "threshold_minutes": request.threshold_minutes,
        "threshold_occurrences": request.threshold_occurrences,
        "template_code": request.template_code,
    }


async def _require_deliverable(
    bound: TenantScope,
    rule: Mapping[str, Any],
    readiness: Mapping[Channel, Mapping[str, Any]],
) -> None:
    """O que `ligar` exige, dentro da transação — e o `PUT` numa regra ligada.

    Ao menos um destino ativo; e, na mensageria, template presente, ativo no
    catálogo e — no provedor oficial — aprovado. A lista de `canais._BLOCKED_SQL`
    é o juiz do template: ela só vê regra LIGADA, por isso roda depois da
    escrita e antes do commit; a exceção é o rollback.
    """
    await bound.execute(_ACTIVE_TARGETS_SQL, {"rule_id": str(rule["id"])})
    if (await bound.fetchone())["n"] == 0:
        raise _conflict("rule_has_no_target")
    if rule["channel"] not in (WHATSAPP_CHANNEL, "both"):
        return
    if rule["template_code"] is None:
        raise _conflict("template_required")
    await bound.execute(canais._BLOCKED_SQL, {})
    rows = [
        b
        for b in await bound.fetchall()
        if b["rule_name"] == rule["name"] and b["template_code"] == rule["template_code"]
    ]
    if any(b["meta_status"] is None for b in rows):
        raise _conflict("template_not_found", template=rule["template_code"])
    whatsapp = readiness.get(WHATSAPP_CHANNEL)
    if whatsapp is not None and whatsapp["official"] and rows:
        raise _conflict(
            "template_not_approved",
            template=rule["template_code"],
            meta_status=rows[0]["meta_status"],
        )


@router.post("/regras", status_code=status.HTTP_201_CREATED)
async def create_rule(tenant: CurrentTenant, request: AlertRuleWrite) -> AlertRuleRow:
    """Cria a regra — desligada, sempre. `active` no corpo é 422 pelo schema."""
    await _require_admin(tenant, _SEM_PERMISSAO_REGRA)
    try:
        await _check_rule_references(tenant, request)
        async with tenant_scope(tenant) as bound:
            await bound.execute(_INSERT_RULE_SQL, _rule_fields(request))
            row = await bound.fetchone()
            if row is None:
                raise RuntimeError("o insert de app.alert_rule não devolveu a linha gravada")
            await _audit(
                bound,
                tenant,
                action="insert",
                entity="alert_rule",
                entity_id=str(row["id"]),
                antes=None,
                depois=_rule_fields(request) | {"active": False},
            )
            rule_id = row["id"]
    except _RefusedError as recusa:
        return _refusal(recusa)
    return await _rule(tenant, rule_id)


@router.put("/regras/{rule_id}")
async def update_rule(
    tenant: CurrentTenant, rule_id: UUID, request: AlertRuleWrite
) -> AlertRuleRow:
    """Edita a regra. 404 como o usuário antes de escrever.

    Numa regra LIGADA, o que a deixaria sem condição de entregar é 409 e nada
    muda — os mesmos juízes de `ligar`. Mudar `content` para `individual` com
    grupo entre os destinos é recusado pelo gatilho, re-tocado sobre cada
    destino — 409 com a frase dele.
    """
    await _require_admin(tenant, _SEM_PERMISSAO_REGRA)
    await _visible_rule(tenant, rule_id)
    try:
        await _check_rule_references(tenant, request)
        async with user_scope(tenant) as scope:
            readiness = await _readiness(scope, tenant)
        async with tenant_scope(tenant) as bound:
            await bound.execute(
                _UPDATE_RULE_SQL, {"rule_id": str(rule_id), **_rule_fields(request)}
            )
            row = await bound.fetchone()
            if row is None:
                raise RuntimeError("o update de app.alert_rule não alcançou a regra do tenant")
            try:
                await bound.execute(_REVALIDATE_RULE_TARGETS_SQL, {"rule_id": str(rule_id)})
                await bound.fetchall()
            except errors.RaiseException as recusa:
                raise _RefusedError(
                    "individual_to_group",
                    _trigger_phrase(recusa, "O gatilho recusou o destino."),
                    status.HTTP_409_CONFLICT,
                ) from None
            if row["active"]:
                await _require_deliverable(bound, row, readiness)
            await _audit(
                bound,
                tenant,
                action="update",
                entity="alert_rule",
                entity_id=str(rule_id),
                antes=row["before"],
                depois=_rule_fields(request) | {"active": row["active"]},
            )
    except _RefusedError as recusa:
        return _refusal(recusa)
    return await _rule(tenant, rule_id)


@router.put("/regras/{rule_id}/destinos")
async def replace_rule_targets(
    tenant: CurrentTenant, rule_id: UUID, request: AlertRuleTargets
) -> AlertRuleRow:
    """Substitui os destinos da regra.

    Regra e contatos conferidos como o usuário (404) antes da transação; um
    contato desativado não entra (422). Dentro dela, apagar e reinserir — cada
    linha passa por `util.validate_alert_target`, e a frase dele é o 409
    `individual_to_group`. Regra ligada que ficaria sem destino ativo: 409.
    """
    await _require_admin(tenant, _SEM_PERMISSAO_REGRA)
    rule = await _visible_rule(tenant, rule_id)
    contact_ids = sorted({str(t.contact_id) for t in request.targets if t.contact_id is not None})
    if contact_ids:
        async with user_scope(tenant) as scope:
            await scope.execute(
                _VISIBLE_CONTACTS_SQL,
                {"tenant_id": str(tenant.tenant_id), "contact_ids": contact_ids},
            )
            visible = {str(row["id"]): row for row in await scope.fetchall()}
        if set(visible) != set(contact_ids):
            raise _not_found(_CONTATO_NAO_ENCONTRADO)
        if not all(visible[c]["active"] for c in contact_ids):
            return _refuse(_REFUSALS["contact_inactive"], "contact_inactive")

    depois = [
        {
            "contact_id": str(t.contact_id) if t.contact_id is not None else None,
            "responsibility": t.responsibility,
        }
        for t in request.targets
    ]
    try:
        async with tenant_scope(tenant) as bound:
            await bound.execute(_DELETE_TARGETS_SQL, {"rule_id": str(rule_id)})
            antes = [
                {
                    "contact_id": str(r["contact_id"]) if r["contact_id"] is not None else None,
                    "responsibility": r["responsibility"],
                }
                for r in await bound.fetchall()
            ]
            if request.targets:
                try:
                    await bound.execute(
                        _INSERT_TARGETS_SQL,
                        {
                            "rule_id": str(rule_id),
                            "contact_ids": [
                                str(t.contact_id) if t.contact_id is not None else None
                                for t in request.targets
                            ],
                            "responsibilities": [t.responsibility for t in request.targets],
                        },
                    )
                except errors.RaiseException as recusa:
                    raise _RefusedError(
                        "individual_to_group",
                        _trigger_phrase(recusa, "O gatilho recusou o destino."),
                        status.HTTP_409_CONFLICT,
                    ) from None
                inserted = await bound.fetchall()
                if len(inserted) != len(request.targets):
                    raise RuntimeError("os destinos gravados não são todos os pedidos")
            if rule["active"]:
                await bound.execute(_ACTIVE_TARGETS_SQL, {"rule_id": str(rule_id)})
                if (await bound.fetchone())["n"] == 0:
                    raise _conflict("rule_has_no_target")
            await _audit(
                bound,
                tenant,
                action="update",
                entity="alert_rule_target",
                entity_id=str(rule_id),
                antes=antes,
                depois=depois,
            )
    except _RefusedError as recusa:
        return _refusal(recusa)
    return await _rule(tenant, rule_id)


async def _set_active(
    tenant: TenantContext, rule_id: UUID, *, active: bool, detail: str
) -> AlertRuleRow:
    await _require_admin(tenant, detail)
    rule = await _visible_rule(tenant, rule_id)
    readiness: dict[Channel, DictRow] = {}
    if active:
        async with user_scope(tenant) as scope:
            readiness = await _readiness(scope, tenant)
    try:
        async with tenant_scope(tenant) as bound:
            await bound.execute(_SET_RULE_ACTIVE_SQL, {"rule_id": str(rule_id), "active": active})
            if await bound.fetchone() is None:
                raise RuntimeError("o update de app.alert_rule não alcançou a regra do tenant")
            if active:
                await _require_deliverable(bound, rule, readiness)
            await _audit(
                bound,
                tenant,
                action="update",
                entity="alert_rule",
                entity_id=str(rule_id),
                antes={"active": rule["active"]},
                depois={"active": active},
            )
    except _RefusedError as recusa:
        return _refusal(recusa)
    return await _rule(tenant, rule_id)


@router.post("/regras/{rule_id}/ligar")
async def activate_rule(tenant: CurrentTenant, rule_id: UUID) -> AlertRuleRow:
    """A única rota que liga. Exige destino ativo e, na mensageria, template
    presente, ativo e — no provedor oficial — aprovado: 409 nomeado, e nada muda."""
    return await _set_active(tenant, rule_id, active=True, detail=_SEM_PERMISSAO_REGRA)


@router.post("/regras/{rule_id}/desligar")
async def deactivate_rule(tenant: CurrentTenant, rule_id: UUID) -> AlertRuleRow:
    """`active = false`. Sempre aceita."""
    return await _set_active(tenant, rule_id, active=False, detail=_SEM_PERMISSAO_REGRA)


@router.post("/regras/{rule_id}/silenciar")
async def mute_rule(tenant: CurrentTenant, rule_id: UUID, request: MuteRequest) -> AlertRuleRow:
    """`muted_until`. No passado é 422; nulo tira o silêncio."""
    await _require_admin(tenant, _SEM_PERMISSAO_REGRA)
    if request.until is not None and request.until <= datetime.now(UTC):
        return _refuse(_REFUSALS["mute_in_past"], "mute_in_past")
    await _visible_rule(tenant, rule_id)
    async with tenant_scope(tenant) as bound:
        await bound.execute(_MUTE_RULE_SQL, {"rule_id": str(rule_id), "until": request.until})
        row = await bound.fetchone()
        if row is None:
            raise RuntimeError("o update de app.alert_rule não alcançou a regra do tenant")
        await _audit(
            bound,
            tenant,
            action="update",
            entity="alert_rule",
            entity_id=str(rule_id),
            antes=None,
            depois={"muted_until": request.until.isoformat() if request.until else None},
        )
    return await _rule(tenant, rule_id)


# ---------------------------------------------------------------------------
# O modo de teste do S6
# ---------------------------------------------------------------------------
def key_for_test(
    rule_id: UUID,
    cycle: Cycle,
    contact_id: UUID,
    half: str,
    payload: dict[str, Any],
    test_id: UUID,
) -> str:
    """A chave da casa (`outbox._key`) com o sufixo do clique. O prefixo
    continua dizendo regra, período, contato, metade e conteúdo; o sufixo diz
    que é teste e qual — dois cliques são duas mensagens, de propósito."""
    return f"{outbox._key(rule_id, cycle, contact_id, half, payload)}:test:{test_id}"


def declaration_for_test(rule_name: str) -> str:
    return f"Mensagem de teste da regra «{rule_name}» — nenhum alerta real foi enviado."


@router.post("/regras/{rule_id}/testar")
async def test_rule(tenant: CurrentTenant, user: CurrentUser, rule_id: UUID) -> RuleTestResult:
    """Enfileira a regra para quem clicou — o modo de teste do S6.

    (1) `util.is_admin`; (2) como o usuário: a regra (404), o contato do
    chamador pelo e-mail do token (409 `caller_has_no_contact`) e a unidade de
    que a mensagem fala (409 `no_unit`); (3) uma transação: o provedor de
    WhatsApp e as duas entradas de `route` para o chamador, os fatos reais da
    janela, e — por metade da regra, como `outbox.enqueue` — a rota, o template
    (a variável que o ciclo não sabe responder é 422 `template_mismatch`, a
    frase do outbox) e a linha na fila pelo gatilho; a trilha com o `test_id`.
    A regra não precisa estar ligada: o teste vem antes de ligar.
    """
    await _require_admin(tenant, _SEM_PERMISSAO_TESTAR)
    rule = await _visible_rule(tenant, rule_id)
    if user.email is None:
        return _refuse(
            _REFUSALS["caller_has_no_contact"].format(email="sem e-mail no token"),
            "caller_has_no_contact",
            status_code=status.HTTP_409_CONFLICT,
        )

    async with user_scope(tenant) as scope:
        await scope.execute(
            _CALLER_CONTACT_SQL, {"tenant_id": str(tenant.tenant_id), "email": user.email}
        )
        caller = await scope.fetchone()
        if caller is None:
            return _refuse(
                _REFUSALS["caller_has_no_contact"].format(email=user.email),
                "caller_has_no_contact",
                status_code=status.HTTP_409_CONFLICT,
            )
        await scope.execute(
            _TEST_UNIT_SQL,
            {
                "tenant_id": str(tenant.tenant_id),
                "unit_id": str(rule["scope_unit_id"]) if rule["scope_unit_id"] else None,
            },
        )
        unit = await scope.fetchone()
        if unit is None:
            return _refuse(_REFUSALS["no_unit"], "no_unit", status_code=status.HTTP_409_CONFLICT)

    test_id = uuid4()
    ate = date.today()
    de = ate - timedelta(days=_TEST_WINDOW_DAYS - 1)
    queued: list[QueuedTestMessage] = []
    try:
        async with tenant_scope(tenant) as bound:
            await bound.execute(outbox._PROVIDER_SQL, {})
            provider_row = await bound.fetchone()
            whatsapp_provider = provider_row["provider"] if provider_row else None

            await bound.execute(
                _CALLER_ROUTE_SQL,
                {
                    "contact_id": str(caller["id"]),
                    "telegram_channel": TELEGRAM_CHANNEL,
                    "telegram_providers": list(providers_of(TELEGRAM_CHANNEL)),
                    "telegram_health": HEALTH_CONNECTED,
                },
            )
            target = await bound.fetchone()
            if target is None:
                raise RuntimeError("o contato do chamador deixou de estar ativo durante o teste")

            await bound.execute(_TEST_FACTS_SQL, {"unit_id": str(unit["id"]), "de": de, "ate": ate})
            counts = await bound.fetchone()
            cycle = Cycle(
                cycle_id=test_id,
                unit_id=unit["id"],
                unit_name=unit["name"],
                period_start=de,
                period_end=ate,
                total_events=counts["total_events"],
                deviation_minutes=counts["deviation_minutes"],
                from_previous_days=0,
            )
            dados = outbox.facts(cycle, base_url=get_settings().dashboard_url)
            dados["declaration"] = declaration_for_test(rule["name"])

            halves = (
                (WHATSAPP_CHANNEL, outbox.EMAIL_CHANNEL)
                if rule["channel"] == "both"
                else (rule["channel"],)
            )
            for half in halves:
                canal, provedor, destino = outbox.route(
                    target, half, whatsapp_provider=whatsapp_provider
                )
                if not destino:
                    continue
                if canal == WHATSAPP_CHANNEL and provedor is None:
                    raise _conflict("no_channel")
                if rule["template_code"]:
                    await bound.execute(outbox._TEMPLATE_SQL, {"code": rule["template_code"]})
                    template = await bound.fetchone()
                    if template is None:
                        raise _conflict("template_not_found", template=rule["template_code"])
                    faltando = [v for v in template["variables"] if v not in dados]
                    if faltando:
                        raise _RefusedError(
                            "template_mismatch",
                            f"O template «{rule['template_code']}» declara "
                            f"{', '.join(faltando)}, e o ciclo não sabe responder. "
                            f"O conhecido é: {', '.join(sorted(dados))}.",
                            status.HTTP_422_UNPROCESSABLE_CONTENT,
                        )
                try:
                    await bound.execute(
                        outbox._ENQUEUE_SQL,
                        {
                            "rule_id": str(rule_id),
                            "cycle_id": None,
                            "channel": canal,
                            "destination": destino,
                            "payload": json.dumps(dados, ensure_ascii=False),
                            "idempotency_key": key_for_test(
                                rule_id, cycle, caller["id"], half, dados, test_id
                            ),
                            "template_code": rule["template_code"],
                            "provider": provedor,
                        },
                    )
                except errors.RaiseException as recusa:
                    # A frase do gatilho, sem o payload e sem a cadeia (o
                    # DETAIL do Postgres traria a linha, e a linha tem o destino).
                    raise _RefusedError(
                        "queue_refused",
                        _trigger_phrase(recusa, "A fila recusou a mensagem de teste."),
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                    ) from None
                criada = await bound.fetchone()
                if criada is None:
                    raise RuntimeError("a fila não aceitou a mensagem de teste recém-criada")
                queued.append(QueuedTestMessage(channel=canal, provider=provedor))
                await _audit(
                    bound,
                    tenant,
                    action="insert",
                    entity="alert_queue",
                    entity_id=str(criada["id"]),
                    antes=None,
                    depois={
                        "test_id": str(test_id),
                        "rule_id": str(rule_id),
                        "contact_id": str(caller["id"]),
                        "channel": canal,
                        "provider": provedor,
                    },
                )
            if not queued:
                raise _conflict("caller_unreachable", name=caller["name"])
    except _RefusedError as recusa:
        return _refusal(recusa)

    logger.info(
        "canais: teste da regra %s enfileirado para o tenant %s (%d linha(s))",
        rule_id,
        tenant.tenant_id,
        len(queued),
    )
    return RuleTestResult(
        rule_id=rule_id,
        test_id=test_id,
        contact_id=caller["id"],
        contact_name=caller["name"],
        queued=queued,
    )
