"""A tela de Conexões — Caminho 2, e o diagnóstico que já existia sem leitor.

`public.fn_whatsapp_readiness` (migration 14) sabe dizer desde sempre que o
cliente está bloqueado e por quê. Ninguém a chama. Diagnóstico existente e
invisível é diagnóstico que não existe, e é isso — não uma tela nova — que esta
rota conserta. Desde o C3 quem responde é `public.fn_channel_readiness`
(migration `ch_readiness_fn`): uma linha por canal ativo, WhatsApp e Telegram
lado a lado — os dois canais coexistem por desenho (SPEC-CANAIS §2.1, §8).

DOIS CANAIS, UMA CREDENCIAL POR CANAL
`channel_of(provider)` decide de qual canal um provedor é, e é por canal que a
credencial desliga o que estava ativo antes do upsert: gravar o token do bot
desliga o bot anterior, e **só** ele. Desligar "todo provedor de canal ativo"
aqui seria o bug *"liguei o Telegram e o WhatsApp desligou"* (§2.1) pela porta
da credencial, com o índice irmão intacto e a suíte de banco verde.

O BOT — SPEC-CANAIS §6, A PARTE QUE É REGISTRO
Conectar grava primeiro e chama a plataforma depois: `webhook_path_token` e
`webhook_url` em `config`, `webhook_secret` no cofre, e só com a transação
fechada o `setWebhook`. A ordem é deliberada — um `setWebhook` que passou e uma
gravação que falhou deixaria o Telegram apontando para um caminho que o banco
não conhece. Recusa da plataforma vira saúde `disconnected` com uma frase
**desta rota** (nunca o corpo do provedor) e 422 com o código. Desconectar faz o
inverso: `deleteWebhook` fora de transação e, se passou, **rotaciona** o
`path_token` e o segredo — reconectar não devolve o endereço antigo. Nada aqui
religa sozinho (§7). O endpoint que recebe o webhook é a onda 2b.

`bot_username`, o estado do webhook e a idade da saúde saem de
`app.integration.config` e `app.channel_health` por `tenant_scope`, com o
`tenant_id` ligado — o mesmo caminho pelo qual `GET /canais/credencial` já lê
`public_identity` para qualquer membro. `app.integration` só tem a policy
`integration_admin` (`util.is_admin`, migration 09): como o usuário, um
supervisor veria a linha do bot na função e nada do bot ao lado dela.

POR QUE CAMINHO 2, SE A FUNÇÃO JÁ ATENDE O NAVEGADOR
A função sim: é `security definer`, recortada por `util.user_tenants()` e já
concedida a `authenticated`. O detalhe que falta nela, não: *qual* regra e *qual*
template vivem em `app.alert_rule` e `app.message_template`, e `app` está fora
dos exposed schemas. Expor uma view nova em `public` para isso é uma das três
paradas obrigatórias do projeto — e desnecessária, porque este é o backend.

QUEM PODE VER, E POR QUE NÃO HÁ CHECAGEM DE PAPEL AQUI
A audiência é quem já enxerga a área de alertas, e isso já está decidido no
banco em três lugares que concordam: a função é concedida a `authenticated` e
cortada por `util.user_tenants()`; `alert_rule_read` e `message_template_read`
liberam `select` com `util.has_tenant(tenant_id)`. Ou seja: qualquer membro ativo
do cliente. Repetir isso aqui como `if role in (...)` seria uma quarta cópia da
mesma regra, escrita noutra linguagem, livre para divergir das outras três — e
mais estreita que a policy sem que ninguém tivesse decidido estreitar.

Então a leitura inteira sai por `user_scope`, como as rotas irmãs
(`monitor.py`, `justificativas.py`): a transação assume o papel `authenticated`
com o `sub` do token, e quem recorta é a policy. O `tenant_id` do token ainda vai
no `where` das duas consultas — a função devolve os tenants do usuário, e este
produto recusa vínculo em mais de um, mas um filtro explícito custa nada e é o
que a regra 4 pede que esteja escrito.

⛔ NADA AQUI É RECALCULADO
As seis contagens são as colunas da função. Refazer a conta em Python passaria em
todo teste de contagem desta sprint e mentiria no primeiro dia em que o predicado
da função mudasse — que é exatamente o defeito que a tela existe para não ter.

A CREDENCIAL — SPEC-CANAIS §5, E O CAMINHO QUE NÃO PODE SER CONTORNADO
`app.integration_secret` guarda só o ponteiro para o Vault e não tem policy:
*"nenhum role do painel lê esta tabela — nem owner"*. Então gravar credencial é
Caminho 2 por definição, e a ordem é a de `curadoria.py`: quem pode, pergunta-se
à policy (`util.is_admin`, no `user_scope`); o que se grava, grava-se junto da
trilha, numa transação de `service_role` (`tenant_scope`). Entre as duas, e
**fora** de qualquer transação, a verificação no provedor — *"nada é gravado se
a validação falhar"* (§5.2) é literal: a rota não abre a transação antes de o
provedor dizer sim.

Leitura do estado (`GET /canais/credencial`): qualquer membro do tenant, como
`GET /canais/conexoes` — a tela diz que a credencial existe, não qual é (§5.3).
Escrita (`POST`): administrador, pela mesma `util.is_admin` da policy
`integration_admin`.

OS TEMPLATES — SPEC-CANAIS §5.5, E O LAÇO QUE FECHA `ready = false`
`app.message_template` está vazia em produção e não tinha escrita por
superfície nenhuma. O catálogo (`GET`/`PUT /canais/templates`) é a primeira; o
"Sincronizar" (`POST /canais/templates/sincronizar`) é o que traz `meta_status`
da WABA. Dois juízes que a rota não substitui: o gatilho
`util.validate_template_body` decide se o corpo usa as variáveis declaradas, e
a frase dele é o `detail` — este arquivo não conhece a sintaxe de placeholder;
e `meta_cloud.META_STATUS` decide o que cada status da Meta vale — **só
`APPROVED` vira `approved`**, e o que o mapa não conhece é `rejected` com o
literal registrado. O token da Cloud API é o primeiro uso real de
`read_secret`: vive numa variável local entre a leitura e a chamada à Meta,
fora de transação, e não vai para auditoria, log, resposta nem exceção.
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from psycopg import errors
from psycopg.rows import DictRow
from psycopg.types.json import Jsonb

from operax.alertas.capacidades import (
    CHANNEL_PROVIDERS,
    CHANNELS,
    TELEGRAM_CHANNEL,
    WHATSAPP_CHANNEL,
    Channel,
    ProviderCapabilities,
    capabilities_for,
    channel_of,
    providers_of,
)
from operax.alertas.provedores import PROVIDERS, meta_cloud, telegram
from operax.alertas.provedores.base import (
    FieldError,
    InvalidCredentialError,
    check_fields,
    verification_client,
)
from operax.core.config import get_settings
from operax.core.tenant import TenantContext, TenantScope, tenant_scope, user_scope
from operax.core.vault import read_secret, store_secret
from server.deps import CurrentTenant
from server.models import (
    BlockedAlertRule,
    ChannelCapabilities,
    ConnectionsScreen,
    CredentialRequest,
    CredentialStatus,
    FieldForm,
    ProviderForm,
    TelegramChannel,
    TemplateRow,
    TemplateSyncResult,
    TemplateWrite,
    WhatsAppChannel,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/canais", tags=["canais"])

#: Uma linha por integração ativa de canal do tenant — as colunas da função,
#: menos `tenant_id` (é o do token) e `channel` (a rota pergunta à matriz, com
#: `channel_of`, em vez de confiar na coluna: provedor que a matriz não conhece
#: derruba a tela em vez de virar linha de canal nenhum).
_READINESS_SQL = """
    select provider, official, templates_total, templates_approved, rules_blocked,
           health_status, health_changed_at, ready
    from public.fn_channel_readiness()
    where tenant_id = %(tenant_id)s
"""

#: ⚠️ ESTE `where` É O MESMO DA CTE `blocked` DE `fn_channel_readiness`, CLÁUSULA
#: POR CLÁUSULA — menos `p.official` e `p.channel = 'whatsapp'`, que na função
#: estão no `join prov` e aqui são o `if` na rota (a lista só é consultada para
#: a linha de WhatsApp oficial). Regra ligada, canal que alcança WhatsApp, e
#: template que não está aprovado — incluindo a regra que não aponta para
#: template nenhum (`m.id is null`), que a função conta e que é o caso mais fácil
#: de esquecer aqui. Qualquer diferença entre os dois predicados aparece como
#: contagem que a lista não sustenta. `tests/test_canais.py` confere as cláusulas
#: contra a última migration que define a função, e `scripts/97_teste_canais.py`
#: executa as duas contra o banco.
#:
#: Sem `distinct`, de propósito: o mesmo `code` em dois idiomas casa duas vezes no
#: `left join` e a função conta as duas. Deduplicar aqui quebraria o par.
_BLOCKED_SQL = """
    select r.name as rule_name,
           r.template_code,
           m.meta_status
    from app.alert_rule r
    left join app.message_template m
           on m.tenant_id = r.tenant_id
          and m.code = r.template_code
          and m.active
    where r.tenant_id = %(tenant_id)s
      and r.active
      and r.channel in ('whatsapp', 'both')
      and (m.id is null or m.meta_status <> 'approved')
    order by r.name, r.template_code nulls first
"""


#: O que a linha de Telegram precisa além da função: a identidade pública do
#: bot, o estado do webhook e a idade da saúde. `tenant_scope`, pelo motivo do
#: docstring; o recorte é o `%(tenant_id)s`. Só as três chaves de `config` que
#: são públicas saem daqui — nem `vault_id`, nem `config` inteiro.
_TELEGRAM_STATE_SQL = """
    select i.id,
           i.config ->> 'public_identity' as public_identity,
           i.config ->> 'webhook_url' as webhook_url,
           i.config ->> 'webhook_path_token' as webhook_path_token,
           h.checked_at as health_checked_at,
           h.detail as health_detail
    from app.integration i
    left join app.channel_health h on h.integration_id = i.id
    where i.tenant_id = %(tenant_id)s
      and i.active
      and i.provider = %(provider)s
"""


def _capabilities(capabilities: ProviderCapabilities) -> ChannelCapabilities:
    return ChannelCapabilities(
        official=capabilities.official,
        requires_templates=capabilities.requires_templates,
        ban_risk=capabilities.ban_risk,
        requires_recipient_opt_in=capabilities.requires_recipient_opt_in,
    )


def _whatsapp(row: DictRow, blocked: list[DictRow]) -> WhatsAppChannel:
    return WhatsAppChannel(
        provider=row["provider"],
        capabilities=_capabilities(capabilities_for(row["provider"])),
        templates_total=row["templates_total"],
        templates_approved=row["templates_approved"],
        rules_blocked=row["rules_blocked"],
        ready=row["ready"],
        blocked=[BlockedAlertRule(**linha) for linha in blocked],
    )


def _telegram(row: DictRow, state: Mapping[str, Any]) -> TelegramChannel:
    return TelegramChannel(
        provider=row["provider"],
        capabilities=_capabilities(capabilities_for(row["provider"])),
        bot_username=state.get("public_identity"),
        webhook_configured=state.get("webhook_url") is not None,
        webhook_url=state.get("webhook_url"),
        webhook_path_token=state.get("webhook_path_token"),
        health_status=row["health_status"],
        health_checked_at=state.get("health_checked_at"),
        health_changed_at=row["health_changed_at"],
        health_detail=state.get("health_detail"),
        ready=row["ready"],
    )


async def _connections(tenant: TenantContext) -> ConnectionsScreen:
    """A tela inteira, relida — é o que o `GET` devolve e o que conectar e
    desconectar devolvem depois de agir."""
    async with user_scope(tenant) as scope:
        await scope.execute(_READINESS_SQL, {"tenant_id": str(tenant.tenant_id)})
        # Fail-closed: provedor que a matriz não conhece levanta aqui em vez de
        # virar "canal sem restrição" na tela de quem decide ligar uma regra.
        rows: dict[Channel, DictRow] = {
            channel_of(row["provider"]): row for row in await scope.fetchall()
        }
        whatsapp = rows.get(WHATSAPP_CHANNEL)

        blocked: list[DictRow] = []
        if whatsapp is not None and whatsapp["official"]:
            # A CTE da função só conta regra bloqueada quando o provedor de
            # WhatsApp é o oficial — é ele que recusa template não aprovado.
            # Perguntar fora disso devolveria linha que `rules_blocked` não conta.
            await scope.execute(_BLOCKED_SQL, {"tenant_id": str(tenant.tenant_id)})
            blocked = await scope.fetchall()

    if whatsapp is not None and whatsapp["rules_blocked"] != len(blocked):
        # Duas leituras do mesmo fato que discordam. A tela entrega as duas como
        # vieram — a contagem é a que o gate de prontidão usa e a lista é o que
        # há para mostrar — e o sintoma fica no log em vez de mudo. Não levanta:
        # `user_scope` roda em READ COMMITTED, e uma aprovação de template no
        # meio dos dois statements produz exatamente esta diferença por um
        # instante, sem que nada esteja errado.
        logger.warning(
            "canais: fn_channel_readiness conta %d regra(s) bloqueada(s) e a lista "
            "traz %d para o tenant %s",
            whatsapp["rules_blocked"],
            len(blocked),
            tenant.tenant_id,
        )

    bot = rows.get(TELEGRAM_CHANNEL)
    state: Mapping[str, Any] = {}
    if bot is not None:
        async with tenant_scope(tenant) as bound:
            # `or {}`: a função viu o bot ativo uma transação atrás; se outra
            # sessão o desligou no meio, a linha vem sem bot em vez de 500.
            state = (await _bot_state(bound)) or {}

    return ConnectionsScreen(
        whatsapp=_whatsapp(whatsapp, blocked) if whatsapp is not None else None,
        telegram=_telegram(bot, state) if bot is not None else None,
    )


@router.get("/conexoes")
async def connections(tenant: CurrentTenant) -> ConnectionsScreen:
    """Os canais ativos do cliente, a saúde de cada um e o que está travando o envio.

    Cliente sem canal nenhum não é 404: a tela existe para dizer justamente
    isso, e é o estado da produção hoje.
    """
    return await _connections(tenant)


# ---------------------------------------------------------------------------
# A credencial — SPEC-CANAIS §5
# ---------------------------------------------------------------------------
_SEM_PERMISSAO = "Gravar a credencial do canal é do administrador do cliente."
_SEM_PERMISSAO_TEMPLATE = "Gravar templates do canal é do administrador do cliente."

#: A frase de cada recusa do provedor, por código. O código é o que vai para o
#: log e para a resposta; o corpo do provedor não vai para lugar nenhum (§5.3).
_REFUSALS = {
    "unauthorized": "O provedor recusou a credencial. Nada foi gravado.",
    "not_connected": (
        "A credencial é válida, mas a instância não está conectada ao WhatsApp. Nada foi gravado."
    ),
    "unreachable": "Não foi possível falar com o provedor agora. Nada foi gravado.",
    "malformed": (
        "O provedor respondeu de um jeito que este sistema não reconhece. Nada foi gravado."
    ),
    # As duas da sincronização de templates, recusadas antes de qualquer HTTP.
    "no_official_provider": (
        "A sincronização de templates só existe para a Cloud API da Meta, "
        "e este cliente não a tem ativa."
    ),
    "no_credential": (
        "A credencial da Cloud API não está gravada com o ID da WABA. "
        "Grave-a em Conexões antes de sincronizar."
    ),
    # A do bot, recusada antes de qualquer HTTP.
    "no_public_url": (
        "O endereço público da API (API_PUBLIC_URL) não está configurado, e o "
        "Telegram não teria para onde entregar. Nada foi alterado."
    ),
}

#: `no_credential` do bot: mesmo código, frase própria — a de cima fala da WABA.
_SEM_BOT_CREDENCIAL = "O token do bot não está gravado. Grave-o em Conexões antes de conectar."

#: A frase de cada recusa da plataforma ao registrar ou remover o webhook. São
#: os mesmos três códigos de `verify`, com outra frase: aqui não é a credencial
#: que está sendo gravada, e "nada foi gravado" seria falso depois de conectar
#: — a integração fica com o `webhook_url` e a saúde vai a `disconnected`.
_WEBHOOK_REFUSALS = {
    "unauthorized": "O Telegram recusou o token do bot. Confira a credencial em Conexões.",
    "unreachable": "Não foi possível falar com o Telegram agora. Tente de novo em instantes.",
    "malformed": "O Telegram respondeu de um jeito que este sistema não reconhece.",
}

#: Teto da identidade pública gravada em `config` e devolvida pelo `GET`. É
#: string do provedor, sem limite do lado de lá; aqui vira uma frase de tela.
_IDENTITY_MAX_CHARS = 120

_PERMISSION_SQL = """
    select util.is_admin(%(tenant_id)s) as admin
"""

#: O estado da credencial de UM canal: só o provedor ativo desse canal **com**
#: ponteiro. O `join` é interno de propósito — integração ativa sem segredo é
#: canal escolhido e credencial não gravada, e `configured` tem de dizer o
#: segundo. Nem `vault_id` nem `config` inteiro saem daqui: a chave
#: `public_identity` é a única lida. `{channel_providers}` é o único token que
#: não é do psycopg: renderizado uma vez por canal, abaixo, com a lista de
#: `providers_of` — a mesma técnica de `outbox._PROVIDER_SQL`, e a que
#: `scripts/97_teste_canais.py` repete para compilar e executar o texto real.
_CREDENTIAL_STATUS_SQL = """
    select i.provider,
           i.config ->> 'public_identity' as public_identity,
           max(s.updated_at) as updated_at
    from app.integration i
    join app.integration_secret s on s.integration_id = i.id
    where i.tenant_id = %(tenant_id)s
      and i.active
      and i.provider in ({channel_providers})
    group by i.id, i.provider, i.config
"""

#: Desliga TODO provedor ativo DO CANAL, e não só o de outro provedor: o índice
#: parcial do canal (`integration_whatsapp_unico_ativo` ou o irmão
#: `integration_telegram_unico_ativo`) é conferido no `insert` do upsert abaixo,
#: e uma linha ativa do mesmo provedor com outro `alias` (o que um seed à mão
#: produz) o faria estourar. O upsert religa exatamente uma. O `returning` é o
#: que a auditoria grava como `antes`. ⛔ Só o canal: o WhatsApp ativo sobrevive
#: à gravação do bot, e vice-versa (SPEC-CANAIS §2.2, linha 1).
_DEACTIVATE_SQL = """
    update app.integration
       set active = false
     where tenant_id = %(tenant_id)s
       and active
       and provider in ({channel_providers})
    returning provider,
              coalesce(jsonb_typeof(config -> 'webhook_url') = 'string', false) as had_webhook
"""


def _render(sql: str, channel: Channel) -> str:
    return sql.replace(
        "{channel_providers}", ", ".join(f"'{provider}'" for provider in providers_of(channel))
    )


_CREDENTIAL_STATUS_BY_CHANNEL = {c: _render(_CREDENTIAL_STATUS_SQL, c) for c in CHANNELS}
_DEACTIVATE_BY_CHANNEL = {c: _render(_DEACTIVATE_SQL, c) for c in CHANNELS}

#: `alias = provider`, como a integração `secullum` de produção (alias
#: `'secullum'`): a chave única da migration 09 é `(tenant_id, provider, alias)`
#: e `alias` nulo nunca conflita, então é o alias preenchido que faz disto um
#: upsert por `(tenant_id, provider)` sem migration nova.
_UPSERT_INTEGRATION_SQL = """
    insert into app.integration (tenant_id, provider, alias, config, active)
    values (%(tenant_id)s, %(provider)s, %(provider)s, %(config)s, true)
    on conflict (tenant_id, provider, alias)
    do update set config = excluded.config, active = true
    returning id
"""

_AUDIT_SQL = """
    insert into app.audit_log
      (tenant_id, user_id, action, entity, entity_id, antes, depois)
    values
      (%(tenant_id)s, %(user_id)s, 'update', 'integration',
       %(entity_id)s, %(antes)s, %(depois)s)
"""


async def get_http_client() -> AsyncIterator[httpx.AsyncClient]:
    """O cliente da verificação. Os testes o substituem por um `MockTransport`
    construído pela mesma `verification_client`, que é onde vive a defesa do log."""
    async with verification_client() as client:
        yield client


HttpDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]


def _form(provider: str) -> ProviderForm:
    return ProviderForm(
        provider=provider,
        channel=channel_of(provider),
        capabilities=_capabilities(capabilities_for(provider)),
        fields=[
            FieldForm(
                name=spec.name,
                label=spec.label_pt,
                pattern=spec.pattern,
                autocomplete=spec.autocomplete,
                inputmode=spec.inputmode,
                secret=spec.secret,
                placeholder=spec.placeholder,
                hint=spec.hint_pt,
            )
            for spec in PROVIDERS[provider].FIELDS
        ],
    )


def _status(row: DictRow | None, channel: Channel) -> CredentialStatus:
    if row is None:
        return CredentialStatus(channel=channel, configured=False)
    return CredentialStatus(
        channel=channel,
        configured=True,
        provider=row["provider"],
        updated_at=row["updated_at"],
        public_identity=row["public_identity"],
    )


def _refuse(detail: str, code: str, **extra: Any) -> JSONResponse:
    """422 com `detail` em pt-BR e um `code` estável ao lado. Nunca o valor."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": detail, "code": code, **extra},
    )


async def _require_admin(tenant: TenantContext, detail: str = _SEM_PERMISSAO) -> None:
    """`util.is_admin` perguntada ao banco como o usuário — a mesma função das
    policies `integration_admin` e `message_template_admin`. 403 antes de
    qualquer HTTP e de qualquer transação de `service_role`. `detail` é a
    frase que a tela mostra como veio — ela nomeia o que foi negado."""
    async with user_scope(tenant) as scope:
        await scope.execute(_PERMISSION_SQL, {"tenant_id": tenant.tenant_id})
        row = await scope.fetchone()
        if not (row and row["admin"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


@router.get("/provedores")
async def provider_forms(tenant: CurrentTenant) -> list[ProviderForm]:
    """O formulário de cada provedor de canal, na ordem da matriz (os três de
    WhatsApp, o oficial primeiro; depois o bot), cada um dizendo de que canal é.
    Qualquer membro: é a descrição de um formulário, não um dado."""
    return [_form(provider) for provider in CHANNEL_PROVIDERS]


@router.get("/credencial")
async def credential_status(
    tenant: CurrentTenant,
    channel: Annotated[Channel, Query(alias="canal")] = WHATSAPP_CHANNEL,
) -> CredentialStatus:
    """Que a credencial do canal existe, de qual provedor e desde quando — nunca
    qual é. `canal` default WhatsApp, para o painel de hoje não quebrar.

    `tenant_scope`, porque a tabela de ponteiros não tem policy; o recorte é o
    `%(tenant_id)s` do `join`. Qualquer membro do tenant, como `/conexoes`.
    """
    async with tenant_scope(tenant) as bound:
        await bound.execute(_CREDENTIAL_STATUS_BY_CHANNEL[channel], {})
        row = await bound.fetchone()
    return _status(row, channel)


@router.post("/credencial")
async def save_credential(
    tenant: CurrentTenant, request: CredentialRequest, http: HttpDep
) -> CredentialStatus:
    """Valida no provedor e só então grava: valor no Vault, ponteiro na tabela.

    A ordem é o contrato. (1) `util.is_admin` como o usuário; (2) provedor e
    formato de cada campo, antes de qualquer HTTP; (3) o provedor, fora de
    transação, que devolve só a identidade pública; (4) uma transação: desliga o
    que estava ativo **no canal do provedor** — e só nele —, upsert da
    integração com os campos não-secretos em `config` (decidido por
    `FieldSpec.secret`, aqui), um segredo no cofre por campo secreto, e a
    auditoria com as **chaves** — nunca os valores.
    """
    await _require_admin(tenant)

    module = PROVIDERS.get(request.provider)
    if module is None:
        return _refuse("Provedor desconhecido.", "unknown_provider")
    channel = channel_of(request.provider)

    try:
        fields = check_fields(module.FIELDS, request.fields)
    except FieldError as erro:
        if erro.spec is None:
            return _refuse(
                f"O campo «{erro.name}» não existe para este provedor.",
                "unknown_field",
                field=erro.name,
            )
        return _refuse(
            f"O campo «{erro.spec.label_pt}»: {erro.spec.hint_pt}.",
            "invalid_format",
            field=erro.name,
        )

    try:
        public_identity = (await module.verify(fields, http))[:_IDENTITY_MAX_CHARS]
    except InvalidCredentialError as recusa:
        # Só o código: a exceção nasce `from None` no provedor e não carrega
        # corpo nem URL, e é assim que ela chega ao log.
        logger.info(
            "canais: credencial de %s recusada para o tenant %s (%s)",
            request.provider,
            tenant.tenant_id,
            recusa.code,
        )
        return _refuse(_REFUSALS[recusa.code], recusa.code)

    # Onde cada campo cai é `FieldSpec.secret`, lido aqui e em lugar nenhum
    # mais: secreto vai para o cofre, o resto para `config`. Todo campo enviado
    # cai em exatamente um dos dois — virar a flag move o campo, não o some.
    secret_keys = [spec.name for spec in module.FIELDS if spec.secret]
    config = {spec.name: fields[spec.name] for spec in module.FIELDS if not spec.secret}
    config["public_identity"] = public_identity

    async with tenant_scope(tenant) as bound:
        await bound.execute(_DEACTIVATE_BY_CHANNEL[channel], {})
        deactivated = await bound.fetchall()
        previous = [linha["provider"] for linha in deactivated]
        had_webhook = any(linha["had_webhook"] for linha in deactivated)

        await bound.execute(
            _UPSERT_INTEGRATION_SQL,
            {"provider": request.provider, "config": Jsonb(config)},
        )
        integration = await bound.fetchone()
        if integration is None:
            # `insert … on conflict do update … returning id` devolve sempre uma
            # linha. Zero aqui é o driver ou o schema fora do que este código
            # conhece, e a transação tem de morrer com isso dito.
            raise RuntimeError("o upsert de app.integration não devolveu a linha gravada")
        integration_id = integration["id"]

        for key in secret_keys:
            await store_secret(bound, integration_id, key, fields[key])

        if channel == TELEGRAM_CHANNEL and had_webhook:
            # O upsert troca `config` inteiro, e com ele somem `webhook_url` e
            # `webhook_path_token` — mas a saúde ficaria em `connected`, e a
            # tela diria "pronto" ao lado de "Conectar bot". O Telegram segue
            # entregando no caminho antigo, que o banco não conhece mais; até
            # o administrador reconectar, o canal está fora, e a saúde diz.
            await _record_health(
                bound,
                integration_id,
                "disconnected",
                "token do bot regravado; conecte o bot de novo",
            )

        await bound.execute(
            _AUDIT_SQL,
            {
                "user_id": tenant.user_id,
                "entity_id": str(integration_id),
                "antes": Jsonb({"provider": previous[0]}) if previous else None,
                "depois": Jsonb(
                    {
                        "provider": request.provider,
                        "public_identity": public_identity,
                        "keys": secret_keys,
                    }
                ),
            },
        )

        await bound.execute(_CREDENTIAL_STATUS_BY_CHANNEL[channel], {})
        row = await bound.fetchone()

    return _status(row, channel)


# ---------------------------------------------------------------------------
# O bot — SPEC-CANAIS §6, a parte que é registro; §7, o que não religa
# ---------------------------------------------------------------------------
_SEM_PERMISSAO_CONECTAR = "Conectar o bot é do administrador do cliente."
_SEM_PERMISSAO_DESCONECTAR = "Desconectar o bot é do administrador do cliente."

#: A chave do cofre em que `save_credential` guardou o token do bot — derivada
#: de `FieldSpec.secret`, como a da Cloud API, e não escrita à mão aqui.
[_BOT_TOKEN_KEY] = [spec.name for spec in telegram.FIELDS if spec.secret]

#: A chave do cofre do segredo que a plataforma devolve no header
#: `X-Telegram-Bot-Api-Secret-Token`. Não é campo de formulário: nasce aqui, em
#: `secrets.token_urlsafe`, e rotaciona a cada desconexão.
_WEBHOOK_SECRET_KEY = "webhook_secret"

#: `app.channel_health.status`, os dois que esta rota escreve. A terceira
#: (`unknown`) é do vigia.
_HEALTH_CONNECTED = "connected"
_HEALTH_DISCONNECTED = "disconnected"

#: `config` ganha (ou troca) as duas chaves do webhook. `||` com o patch, em vez
#: de reescrever `config`: `public_identity` e o que mais o formulário gravou
#: ficam. `%(patch)s` é `Jsonb`, com `webhook_url` nulo na desconexão.
_TELEGRAM_WEBHOOK_SQL = """
    update app.integration
       set config = config || %(patch)s::jsonb
     where tenant_id = %(tenant_id)s
       and id = %(integration_id)s
    returning id
"""

#: A medição, gravada pela porta única (`app.fn_record_channel_health`, migration
#: `ch_channel_health`), que é quem segura a regra da §7 — `status_changed_at`
#: só avança quando o status muda. O `from app.integration … tenant_id` é o que
#: liga o tenant: integração de outro cliente é zero linhas e função nunca
#: avaliada. ⛔ `%(detail)s` é sempre uma frase DESTA rota — no máximo com o
#: código da recusa —, nunca corpo nem mensagem do provedor: a função grava o
#: que recebe (achado do guardião da onda 1).
_RECORD_HEALTH_SQL = """
    select app.fn_record_channel_health(i.id, %(status)s, %(detail)s)
    from app.integration i
    where i.tenant_id = %(tenant_id)s
      and i.id = %(integration_id)s
"""


async def _bot_state(bound: TenantScope) -> DictRow | None:
    await bound.execute(_TELEGRAM_STATE_SQL, {"provider": telegram.NAME})
    return await bound.fetchone()


async def _record_health(
    bound: TenantScope, integration_id: Any, status_: str, detail: str
) -> None:
    await bound.execute(
        _RECORD_HEALTH_SQL,
        {"integration_id": integration_id, "status": status_, "detail": detail},
    )
    if await bound.fetchone() is None:
        raise RuntimeError("app.fn_record_channel_health não alcançou a integração do tenant")


async def _rotate_webhook(
    bound: TenantScope,
    tenant: TenantContext,
    state: DictRow,
    *,
    webhook_url: str | None,
    path_token: str,
    webhook_secret: str,
) -> None:
    """As três gravações de um webhook — `config`, cofre e trilha — na
    transação do chamador. A auditoria leva `webhook_path_token` (a cauda
    pública da URL) e a **chave** do segredo; o valor, nunca."""
    await bound.execute(
        _TELEGRAM_WEBHOOK_SQL,
        {
            "integration_id": state["id"],
            "patch": Jsonb({"webhook_path_token": path_token, "webhook_url": webhook_url}),
        },
    )
    if await bound.fetchone() is None:
        raise RuntimeError("o update de app.integration não alcançou a integração do tenant")
    await store_secret(bound, state["id"], _WEBHOOK_SECRET_KEY, webhook_secret)
    await bound.execute(
        _AUDIT_SQL,
        {
            "user_id": tenant.user_id,
            "entity_id": str(state["id"]),
            "antes": Jsonb(
                {
                    "webhook_path_token": state["webhook_path_token"],
                    "webhook_url": state["webhook_url"],
                }
            ),
            "depois": Jsonb(
                {
                    "webhook_path_token": path_token,
                    "webhook_url": webhook_url,
                    "keys": [_WEBHOOK_SECRET_KEY],
                }
            ),
        },
    )


async def _telegram_channel(tenant: TenantContext) -> TelegramChannel:
    screen = await _connections(tenant)
    if screen.telegram is None:
        # A integração estava ativa duas transações atrás. Sumir agora é outra
        # sessão desligando o bot no meio do clique, e a tela tem de dizer isso
        # em vez de devolver um bot que não existe.
        raise RuntimeError("a integração do bot deixou de estar ativa durante a operação")
    return screen.telegram


@router.post("/telegram/conectar")
async def connect_bot(tenant: CurrentTenant, http: HttpDep) -> TelegramChannel:
    """Registra o webhook do bot na plataforma — gravando antes de chamar.

    (1) `util.is_admin`; (2) `API_PUBLIC_URL`, sem a qual não há endereço a
    registrar; (3) uma transação: o bot ativo com ponteiro (ou 422), o token do
    cofre para uma variável local, `webhook_path_token` e `webhook_url` em
    `config`, `webhook_secret` novo no cofre, auditoria; (4) fechada a
    transação, `setWebhook` — recusa vira saúde `disconnected` com o código,
    numa segunda transação, e 422; (5) sucesso vira saúde `connected`. A tela
    volta relida.
    """
    await _require_admin(tenant, _SEM_PERMISSAO_CONECTAR)

    public_url = get_settings().api_public_url
    if public_url is None:
        return _refuse(_REFUSALS["no_public_url"], "no_public_url")

    path_token = secrets.token_urlsafe(24)
    webhook_secret = secrets.token_urlsafe(32)
    webhook_url = f"{public_url}{telegram.WEBHOOK_PATH}/{path_token}"

    async with tenant_scope(tenant) as bound:
        state = await _bot_state(bound)
        token = await read_secret(bound, state["id"], _BOT_TOKEN_KEY) if state else None
        if state is None or token is None:
            return _refuse(_SEM_BOT_CREDENCIAL, "no_credential")
        await _rotate_webhook(
            bound,
            tenant,
            state,
            webhook_url=webhook_url,
            path_token=path_token,
            webhook_secret=webhook_secret,
        )

    try:
        await telegram.set_webhook(token, webhook_url, webhook_secret, http)
    except InvalidCredentialError as recusa:
        # Só o código: a exceção nasce `from None` no provedor e não carrega
        # corpo nem URL — e é só o código que vai para o `detail` da saúde.
        logger.info(
            "canais: setWebhook recusado para o tenant %s (%s)", tenant.tenant_id, recusa.code
        )
        async with tenant_scope(tenant) as bound:
            await _record_health(
                bound, state["id"], _HEALTH_DISCONNECTED, f"setWebhook recusado: {recusa.code}"
            )
        return _refuse(_WEBHOOK_REFUSALS[recusa.code], recusa.code)

    async with tenant_scope(tenant) as bound:
        await _record_health(bound, state["id"], _HEALTH_CONNECTED, "webhook registrado")

    return await _telegram_channel(tenant)


@router.post("/telegram/desconectar")
async def disconnect_bot(tenant: CurrentTenant, http: HttpDep) -> TelegramChannel:
    """Remove o webhook na plataforma e **rotaciona** o caminho e o segredo.

    (1) `util.is_admin`; (2) uma transação só de leitura: o bot ativo com
    ponteiro (ou 422) e o token do cofre; (3) fechada, `deleteWebhook` —
    recusa é 422 e nada muda; (4) uma transação: `webhook_path_token` novo,
    `webhook_url` nulo, `webhook_secret` novo, saúde `disconnected`, auditoria.
    Reconectar não devolve o endereço antigo (SPEC-CANAIS §6), e nada aqui
    religa (§7).
    """
    await _require_admin(tenant, _SEM_PERMISSAO_DESCONECTAR)

    async with tenant_scope(tenant) as bound:
        state = await _bot_state(bound)
        token = await read_secret(bound, state["id"], _BOT_TOKEN_KEY) if state else None
        if state is None or token is None:
            return _refuse(_SEM_BOT_CREDENCIAL, "no_credential")

    try:
        await telegram.delete_webhook(token, http)
    except InvalidCredentialError as recusa:
        logger.info(
            "canais: deleteWebhook recusado para o tenant %s (%s)", tenant.tenant_id, recusa.code
        )
        return _refuse(_WEBHOOK_REFUSALS[recusa.code], recusa.code)

    async with tenant_scope(tenant) as bound:
        await _rotate_webhook(
            bound,
            tenant,
            state,
            webhook_url=None,
            path_token=secrets.token_urlsafe(24),
            webhook_secret=secrets.token_urlsafe(32),
        )
        await _record_health(
            bound, state["id"], _HEALTH_DISCONNECTED, "desconectado pelo administrador"
        )

    return await _telegram_channel(tenant)


# ---------------------------------------------------------------------------
# Os templates — SPEC-CANAIS §5.5
# ---------------------------------------------------------------------------
#: A forma que o banco não confere. O corpo fica de fora de propósito: quem sabe
#: o que é placeholder é `util.validate_template_body`, e a asserção do revisor
#: é que este arquivo não conhece a sintaxe dele.
_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]{2,63}")
_LANGUAGE_PATTERN = re.compile(r"[a-z]{2}(_[A-Z]{2})?")
_VARIABLE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")
_META_NAME_PATTERN = re.compile(r"[a-z0-9_]{1,512}")
_CATEGORIES = frozenset({"utility", "authentication", "marketing"})

#: As colunas de `TemplateRow`: o que o catálogo devolve e o que a auditoria
#: copia em `antes`/`depois`. `tests/test_canais_templates.py` confere que o
#: `select` abaixo as nomeia todas — o SQL é literal para que o `97` o execute
#: como está.
_TEMPLATE_COLUMNS = (
    "code",
    "category",
    "language",
    "variables",
    "body",
    "meta_template_name",
    "meta_status",
    "meta_rejection",
    "active",
    "updated_at",
)

#: O catálogo inteiro, inativos inclusive: `active` é coluna e a tela decide.
#: Roda como o usuário — `message_template_read` é `util.has_tenant`.
_TEMPLATES_SQL = """
    select code, category, language, variables, body, meta_template_name,
           meta_status, meta_rejection, active, updated_at
    from app.message_template
    where tenant_id = %(tenant_id)s
    order by code, language
"""

#: Um upsert por `(tenant_id, code, language)`. A CTE `before` lê a linha na
#: mesma foto, antes da escrita: é o `antes` da auditoria, e `before is null` é
#: o que diz se foi `insert` ou `update`. `meta_status` e `meta_rejection` não
#: vêm do formulário: ficam como estão, salvo quando `meta_template_name` muda
#: — aí voltam a `draft`/nulo, porque o nome novo não foi conferido na WABA.
#: `updated_at` é do gatilho.
_TEMPLATE_UPSERT_SQL = """
    with before as (
        select *
        from app.message_template
        where tenant_id = %(tenant_id)s
          and code = %(code)s
          and language = %(language)s
    )
    insert into app.message_template as t
      (tenant_id, code, category, language, variables, body, meta_template_name, active)
    values
      (%(tenant_id)s, %(code)s, %(category)s, %(language)s, %(variables)s, %(body)s,
       %(meta_template_name)s, %(active)s)
    on conflict (tenant_id, code, language) do update
       set category = excluded.category,
           variables = excluded.variables,
           body = excluded.body,
           meta_template_name = excluded.meta_template_name,
           active = excluded.active,
           meta_status = case
               when excluded.meta_template_name is distinct from t.meta_template_name
               then 'draft' else t.meta_status end,
           meta_rejection = case
               when excluded.meta_template_name is distinct from t.meta_template_name
               then null else t.meta_rejection end
    returning t.*, (select to_jsonb(b) from before b) as before
"""

#: A integração oficial ativa e o `waba_id` que o C2b passou a gravar em
#: `config`. Só ela tem templates para sincronizar.
_OFFICIAL_INTEGRATION_SQL = """
    select i.id, i.config ->> 'waba_id' as waba_id
    from app.integration i
    where i.tenant_id = %(tenant_id)s
      and i.active
      and i.provider = %(provider)s
"""

#: O que a sincronização compara: todo template com nome na WABA, ativo ou não.
_NAMED_TEMPLATES_SQL = """
    select id, code, language, meta_template_name
    from app.message_template
    where tenant_id = %(tenant_id)s
      and meta_template_name is not null
    order by code, language
"""

#: Só grava o que mudou: `is distinct from` compara o par inteiro, nulo
#: incluído, e o `returning` é a lista `updated` da resposta. O nome entra na
#: chave: o veredito da WABA é sobre o nome que foi consultado, e um `PUT` que
#: o troque enquanto a Meta responde já pôs a linha em `draft` — gravar por
#: `id` escreveria o status do nome velho sobre o nome novo.
_SYNC_TEMPLATES_SQL = """
    update app.message_template t
       set meta_status = v.meta_status,
           meta_rejection = v.meta_rejection
      from unnest(%(ids)s::uuid[], %(names)s::text[],
                  %(statuses)s::text[], %(rejections)s::text[])
           as v(id, name, meta_status, meta_rejection)
     where t.tenant_id = %(tenant_id)s
       and t.id = v.id
       and t.meta_template_name = v.name
       and (t.meta_status, t.meta_rejection)
           is distinct from (v.meta_status, v.meta_rejection)
    returning t.code
"""

_TEMPLATE_AUDIT_SQL = """
    insert into app.audit_log
      (tenant_id, user_id, action, entity, entity_id, antes, depois)
    values
      (%(tenant_id)s, %(user_id)s, %(action)s, 'message_template',
       %(entity_id)s, %(antes)s, %(depois)s)
"""

#: A chave do cofre em que `save_credential` guardou o token da Cloud API —
#: derivada de `FieldSpec.secret`, como lá, e não escrita à mão aqui.
[_META_TOKEN_KEY] = [spec.name for spec in meta_cloud.FIELDS if spec.secret]

_UNMATCHED_REASON = "Não encontrado na WABA na última sincronização"
_UNKNOWN_STATUS_REASON = "Status desconhecido na Meta: "


class TemplateBodyRefusedError(ValueError):
    """O gatilho recusou o corpo. A mensagem é a dele, já em pt-BR."""


def _template_shape_error(code: str, request: TemplateWrite) -> tuple[str, str] | None:
    """`(campo, frase)` do primeiro campo fora de forma, ou `None`."""
    if not _CODE_PATTERN.fullmatch(code):
        return (
            "code",
            "O código do template: letras minúsculas, dígitos e sublinhado, "
            "começando por letra, de 3 a 64 caracteres.",
        )
    if request.category not in _CATEGORIES:
        return ("category", "A categoria é utility, authentication ou marketing.")
    if not _LANGUAGE_PATTERN.fullmatch(request.language):
        return ("language", "O idioma segue a forma da Meta: pt_BR, en_US ou en.")
    if (
        not request.variables
        or len(set(request.variables)) != len(request.variables)
        or not all(_VARIABLE_PATTERN.fullmatch(v) for v in request.variables)
    ):
        return (
            "variables",
            "As variáveis: ao menos uma, sem repetição, cada uma com letras minúsculas, "
            "dígitos e sublinhado, começando por letra.",
        )
    if request.meta_template_name is not None and not _META_NAME_PATTERN.fullmatch(
        request.meta_template_name
    ):
        return (
            "meta_template_name",
            "O nome do template na Meta: só letras minúsculas, dígitos e sublinhado.",
        )
    return None


def _template_row(row: Mapping[str, Any]) -> TemplateRow:
    """Só as colunas do contrato: `t.*` e `to_jsonb(before)` trazem `id`,
    `tenant_id` e `created_at`, que não saem nem vão para a trilha."""
    return TemplateRow(**{column: row[column] for column in _TEMPLATE_COLUMNS})


@router.get("/templates")
async def templates(tenant: CurrentTenant) -> list[TemplateRow]:
    """O catálogo do cliente, como o usuário: a policy recorta por tenant.
    Qualquer membro — quem vê Conexões vê o catálogo; escrever é que exige admin."""
    async with user_scope(tenant) as scope:
        await scope.execute(_TEMPLATES_SQL, {"tenant_id": str(tenant.tenant_id)})
        rows = await scope.fetchall()
    return [_template_row(row) for row in rows]


@router.put("/templates/{code}")
async def save_template(tenant: CurrentTenant, code: str, request: TemplateWrite) -> TemplateRow:
    """Cria ou edita um template; devolve o gravado, relido do `returning`.

    (1) `util.is_admin` como o usuário; (2) a forma do que o banco não confere,
    sem tocar o banco; (3) uma transação: o upsert — cujo corpo o gatilho
    julga, e a frase dele volta como 422 — e a auditoria com a linha anterior
    e a gravada. Nada aqui é segredo; o JSON inteiro vai para a trilha.
    """
    await _require_admin(tenant, _SEM_PERMISSAO_TEMPLATE)

    shape = _template_shape_error(code, request)
    if shape is not None:
        field, detail = shape
        return _refuse(detail, "invalid_format", field=field)

    try:
        async with tenant_scope(tenant) as bound:
            try:
                await bound.execute(
                    _TEMPLATE_UPSERT_SQL,
                    {
                        "code": code,
                        "category": request.category,
                        "language": request.language,
                        "variables": request.variables,
                        "body": request.body,
                        "meta_template_name": request.meta_template_name,
                        "active": request.active,
                    },
                )
            except errors.RaiseException as recusa:
                # A frase do gatilho, e só ela: já é pt-BR e nomeia a variável
                # e o placeholder. Sai pela transação, que é quem faz o rollback.
                raise TemplateBodyRefusedError(
                    recusa.diag.message_primary or "O corpo do template foi recusado."
                ) from None
            row = await bound.fetchone()
            if row is None:
                raise RuntimeError("o upsert de app.message_template não devolveu a linha gravada")
            saved = _template_row(row)
            await bound.execute(
                _TEMPLATE_AUDIT_SQL,
                {
                    "user_id": tenant.user_id,
                    "action": "insert" if row["before"] is None else "update",
                    "entity_id": str(row["id"]),
                    "antes": (
                        Jsonb(_template_row(row["before"]).model_dump(mode="json"))
                        if row["before"] is not None
                        else None
                    ),
                    "depois": Jsonb(saved.model_dump(mode="json")),
                },
            )
    except TemplateBodyRefusedError as recusa:
        return _refuse(str(recusa), "template_body")

    return saved


@router.post("/templates/sincronizar")
async def sync_templates(tenant: CurrentTenant, http: HttpDep) -> TemplateSyncResult:
    """Traz `status` e `rejected_reason` da WABA para os templates com nome.

    (1) `util.is_admin`; (2) a integração oficial ativa e o token do cofre,
    numa transação que **fecha antes** de qualquer HTTP; (3) a Meta, fora de
    transação; (4) uma transação: o mapa `meta_cloud.META_STATUS` decide o
    status local de cada par — só `APPROVED` vira `approved`, o desconhecido é
    `rejected` com o literal, o sem par é `draft` — e só o que mudou é gravado.
    """
    await _require_admin(tenant, _SEM_PERMISSAO_TEMPLATE)

    async with tenant_scope(tenant) as bound:
        await bound.execute(_OFFICIAL_INTEGRATION_SQL, {"provider": meta_cloud.NAME})
        integration = await bound.fetchone()
        if integration is None:
            return _refuse(_REFUSALS["no_official_provider"], "no_official_provider")
        waba_id = integration["waba_id"]
        token = await read_secret(bound, integration["id"], _META_TOKEN_KEY) if waba_id else None
        if token is None:
            return _refuse(_REFUSALS["no_credential"], "no_credential")

    try:
        remote = await meta_cloud.list_templates({"waba_id": waba_id}, token, http)
    except InvalidCredentialError as recusa:
        logger.info(
            "canais: sincronização de templates recusada para o tenant %s (%s)",
            tenant.tenant_id,
            recusa.code,
        )
        return _refuse(_REFUSALS[recusa.code], recusa.code)

    by_key = {(t.name, t.language): t for t in remote}

    async with tenant_scope(tenant) as bound:
        await bound.execute(_NAMED_TEMPLATES_SQL, {})
        local = await bound.fetchall()

        ids: list[Any] = []
        names: list[str] = []
        statuses: list[str] = []
        rejections: list[str | None] = []
        unmatched: list[str] = []
        for row in local:
            pair = by_key.get((row["meta_template_name"], row["language"]))
            if pair is None:
                unmatched.append(row["code"])
                desired, reason = "draft", _UNMATCHED_REASON
            elif pair.status in meta_cloud.META_STATUS:
                desired, reason = meta_cloud.META_STATUS[pair.status], pair.rejected_reason
            else:
                desired, reason = "rejected", _UNKNOWN_STATUS_REASON + pair.status
            ids.append(row["id"])
            names.append(row["meta_template_name"])
            statuses.append(desired)
            rejections.append(reason)

        updated: list[str] = []
        if ids:
            await bound.execute(
                _SYNC_TEMPLATES_SQL,
                {"ids": ids, "names": names, "statuses": statuses, "rejections": rejections},
            )
            updated = [row["code"] for row in await bound.fetchall()]

        await bound.execute(
            _TEMPLATE_AUDIT_SQL,
            {
                "user_id": tenant.user_id,
                "action": "update",
                "entity_id": None,
                "antes": None,
                "depois": Jsonb(
                    {"updated": updated, "unmatched": unmatched, "meta_total": len(remote)}
                ),
            },
        )

    return TemplateSyncResult(
        provider=meta_cloud.NAME,
        meta_total=len(remote),
        updated=updated,
        unmatched=unmatched,
        synced_at=datetime.now(UTC),
    )
