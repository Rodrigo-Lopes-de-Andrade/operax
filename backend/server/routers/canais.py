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
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from psycopg.rows import DictRow

from operax.alertas.capacidades import capabilities_for
from operax.core.tenant import user_scope
from server.deps import CurrentTenant
from server.models import BlockedAlertRule, ChannelCapabilities, ConnectionsScreen

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
