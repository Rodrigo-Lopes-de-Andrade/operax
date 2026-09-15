"""A tela de Conexões — Caminho 2, e o diagnóstico que já existia sem leitor.

`public.fn_whatsapp_readiness` (migration 14) sabe dizer desde sempre que o
cliente está bloqueado e por quê. Ninguém a chama. Diagnóstico existente e
invisível é diagnóstico que não existe, e é isso — não uma tela nova — que esta
rota conserta.

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
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from psycopg.rows import DictRow
from psycopg.types.json import Jsonb

from operax.alertas.capacidades import WHATSAPP_PROVIDERS, capabilities_for
from operax.alertas.provedores import PROVIDERS
from operax.alertas.provedores.base import (
    FieldError,
    InvalidCredentialError,
    check_fields,
    verification_client,
)
from operax.core.tenant import tenant_scope, user_scope
from operax.core.vault import store_secret
from server.deps import CurrentTenant
from server.models import (
    BlockedAlertRule,
    ChannelCapabilities,
    ConnectionsScreen,
    CredentialRequest,
    CredentialStatus,
    FieldForm,
    ProviderForm,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/canais", tags=["canais"])

#: As sete colunas da função, menos o `tenant_id` que já é o do token.
_READINESS_SQL = """
    select provider, official, templates_total, templates_approved, rules_blocked, ready
    from public.fn_whatsapp_readiness()
    where tenant_id = %(tenant_id)s
"""

#: ⚠️ ESTE `where` É O MESMO DA CTE `blocked` DE `fn_whatsapp_readiness`, CLÁUSULA
#: POR CLÁUSULA — menos `p.official`, que aqui é o `if` na rota. Regra ligada,
#: canal que alcança WhatsApp, e template que não está aprovado — incluindo a
#: regra que não aponta para template nenhum (`m.id is null`), que a função conta
#: e que é o caso mais fácil de esquecer aqui. Qualquer diferença entre os dois
#: predicados aparece como contagem que a lista não sustenta. `tests/test_canais.py`
#: confere as cláusulas contra a última migration que define a função, e
#: `scripts/97_teste_canais.py` executa as duas contra o banco.
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


@router.get("/conexoes")
async def connections(tenant: CurrentTenant) -> ConnectionsScreen:
    """O provedor ativo do cliente, a saúde do canal e o que está travando o envio."""
    async with user_scope(tenant) as scope:
        await scope.execute(_READINESS_SQL, {"tenant_id": str(tenant.tenant_id)})
        readiness = await scope.fetchone()

        if readiness is None:
            # Cliente sem provedor de WhatsApp ativo. Não é 404: a tela existe
            # para dizer justamente isso, e é o estado da produção hoje.
            return ConnectionsScreen()

        blocked: list[DictRow] = []
        if readiness["official"]:
            # A CTE da função só conta regra bloqueada quando o provedor é o
            # oficial — é ele que recusa template não aprovado. Perguntar fora
            # disso devolveria linha que `rules_blocked` não conta.
            await scope.execute(_BLOCKED_SQL, {"tenant_id": str(tenant.tenant_id)})
            blocked = await scope.fetchall()

    if readiness["rules_blocked"] != len(blocked):
        # Duas leituras do mesmo fato que discordam. A tela entrega as duas como
        # vieram — a contagem é a que o gate de prontidão usa e a lista é o que
        # há para mostrar — e o sintoma fica no log em vez de mudo. Não levanta:
        # `user_scope` roda em READ COMMITTED, e uma aprovação de template no
        # meio dos dois statements produz exatamente esta diferença por um
        # instante, sem que nada esteja errado.
        logger.warning(
            "canais: fn_whatsapp_readiness conta %d regra(s) bloqueada(s) e a lista "
            "traz %d para o tenant %s",
            readiness["rules_blocked"],
            len(blocked),
            tenant.tenant_id,
        )

    # Fail-closed: provedor que a matriz não conhece levanta aqui em vez de
    # virar "canal sem restrição" na tela de quem decide ligar uma regra.
    capabilities = capabilities_for(readiness["provider"])

    return ConnectionsScreen(
        provider=readiness["provider"],
        capabilities=ChannelCapabilities(
            official=capabilities.official,
            requires_templates=capabilities.requires_templates,
            ban_risk=capabilities.ban_risk,
        ),
        templates_total=readiness["templates_total"],
        templates_approved=readiness["templates_approved"],
        rules_blocked=readiness["rules_blocked"],
        ready=readiness["ready"],
        blocked=[BlockedAlertRule(**row) for row in blocked],
    )


# ---------------------------------------------------------------------------
# A credencial — SPEC-CANAIS §5
# ---------------------------------------------------------------------------
_SEM_PERMISSAO = "Gravar a credencial do canal é do administrador do cliente."

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
}

#: Teto da identidade pública gravada em `config` e devolvida pelo `GET`. É
#: string do provedor, sem limite do lado de lá; aqui vira uma frase de tela.
_IDENTITY_MAX_CHARS = 120

#: A mesma lista renderizada de `outbox._PROVIDER_SQL`: o índice parcial da
#: migration 14 é escrito para a forma `in (...)`, e `{whatsapp_providers}` é o
#: único token que não é do psycopg — `scripts/97_teste_canais.py` o renderiza
#: do mesmo jeito para compilar e executar o texto real.
_WHATSAPP_PROVIDER_LIST = ", ".join(f"'{provider}'" for provider in WHATSAPP_PROVIDERS)

_PERMISSION_SQL = """
    select util.is_admin(%(tenant_id)s) as admin
"""

#: O estado da credencial: só o provedor ativo **com** ponteiro. O `join` é
#: interno de propósito — integração ativa sem segredo é canal escolhido e
#: credencial não gravada, e `configured` tem de dizer o segundo. Nem `vault_id`
#: nem `config` inteiro saem daqui: a chave `public_identity` é a única lida.
_CREDENTIAL_STATUS_SQL = """
    select i.provider,
           i.config ->> 'public_identity' as public_identity,
           max(s.updated_at) as updated_at
    from app.integration i
    join app.integration_secret s on s.integration_id = i.id
    where i.tenant_id = %(tenant_id)s
      and i.active
      and i.provider in ({whatsapp_providers})
    group by i.id, i.provider, i.config
""".replace("{whatsapp_providers}", _WHATSAPP_PROVIDER_LIST)

#: Desliga TODO WhatsApp ativo do tenant, e não só o de outro provedor: o
#: índice parcial `integration_whatsapp_unico_ativo` é conferido no `insert` do
#: upsert abaixo, e uma linha ativa do mesmo provedor com outro `alias` (o que
#: um seed à mão produz) o faria estourar. O upsert religa exatamente uma. O
#: `returning` é o que a auditoria grava como `antes`.
_DEACTIVATE_SQL = """
    update app.integration
       set active = false
     where tenant_id = %(tenant_id)s
       and active
       and provider in ({whatsapp_providers})
    returning provider
""".replace("{whatsapp_providers}", _WHATSAPP_PROVIDER_LIST)

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
    capabilities = capabilities_for(provider)
    return ProviderForm(
        provider=provider,
        capabilities=ChannelCapabilities(
            official=capabilities.official,
            requires_templates=capabilities.requires_templates,
            ban_risk=capabilities.ban_risk,
        ),
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


def _status(row: DictRow | None) -> CredentialStatus:
    if row is None:
        return CredentialStatus(configured=False)
    return CredentialStatus(
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


@router.get("/provedores")
async def provider_forms(tenant: CurrentTenant) -> list[ProviderForm]:
    """O formulário de cada provedor de WhatsApp, na ordem da matriz (o oficial
    primeiro). Qualquer membro: é a descrição de um formulário, não um dado."""
    return [_form(provider) for provider in WHATSAPP_PROVIDERS]


@router.get("/credencial")
async def credential_status(tenant: CurrentTenant) -> CredentialStatus:
    """Que a credencial existe, de qual provedor e desde quando — nunca qual é.

    `tenant_scope`, porque a tabela de ponteiros não tem policy; o recorte é o
    `%(tenant_id)s` do `join`. Qualquer membro do tenant, como `/conexoes`.
    """
    async with tenant_scope(tenant) as bound:
        await bound.execute(_CREDENTIAL_STATUS_SQL, {})
        row = await bound.fetchone()
    return _status(row)


@router.post("/credencial")
async def save_credential(
    tenant: CurrentTenant, request: CredentialRequest, http: HttpDep
) -> CredentialStatus:
    """Valida no provedor e só então grava: valor no Vault, ponteiro na tabela.

    A ordem é o contrato. (1) `util.is_admin` como o usuário; (2) provedor e
    formato de cada campo, antes de qualquer HTTP; (3) o provedor, fora de
    transação, que devolve só a identidade pública; (4) uma transação: desliga o
    WhatsApp ativo, upsert da integração com os campos não-secretos em `config`
    (decidido por `FieldSpec.secret`, aqui), um segredo no cofre por campo
    secreto, e a auditoria com as **chaves** — nunca os valores.
    """
    async with user_scope(tenant) as scope:
        await scope.execute(_PERMISSION_SQL, {"tenant_id": tenant.tenant_id})
        row = await scope.fetchone()
        if not (row and row["admin"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_SEM_PERMISSAO)

    module = PROVIDERS.get(request.provider)
    if module is None:
        return _refuse("Provedor desconhecido.", "unknown_provider")

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
        await bound.execute(_DEACTIVATE_SQL, {})
        previous = [linha["provider"] for linha in await bound.fetchall()]

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

        await bound.execute(_CREDENTIAL_STATUS_SQL, {})
        row = await bound.fetchone()

    return _status(row)
