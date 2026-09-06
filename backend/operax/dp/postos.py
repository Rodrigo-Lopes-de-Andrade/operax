"""Quadro de Postos — o cadastro que a rotina de vale transporte usa para achar a escala.

O QUE ESTE MÓDULO **NÃO** TEM, E A AUSÊNCIA É O DESENHO
Não há `secullum_schedule_id` aqui. O elo posto → escala saiu da `dp_work_post`
de propósito (`docs/SPEC-DP.md` §0-bis e §1c) e entra em migration própria, numa
sprint posterior. Um campo inventado agora fingiria que a pergunta foi
respondida.

⛔ LEITURA NÃO RODA COMO O USUÁRIO, E ISSO NÃO É DESCUIDO
`app.work_post` **não concede nada a `authenticated`** — a etapa DP inteira é
Caminho 2. Então um `select` sob `user_scope` não seria filtrado pela policy: ele
morreria com `permission denied`. A leitura roda sob `tenant_scope`, filtrada por
`tenant_id`, e o recorte por unidade vem de `app.unit`, que **é** legível pelo
usuário e cuja policy `unit_read` chama `util.can_see_unit`. A regra de quem
enxerga qual unidade continua morando na policy; aqui ela é consultada, nunca
reescrita.

É a mesma ordem que `server/routers/employees.py` usa para as batidas: a pergunta
autorizadora acontece primeiro, como o usuário, e a leitura seguinte só alcança
ids que a policy já liberou.

TRÊS EIXOS? DOIS.
Posto é estrutura da unidade, não dado de pessoa: não há domínio sensível a
perguntar, e exigir um seria cerimônia — cerimônia se satisfaz com tautologia. Os
eixos são a unidade (`util.can_see_unit`) para ler e a administração
(`util.is_admin`) mais a unidade para escrever, exatamente o par que as policies
`work_post_read` e `work_post_admin` declaram.

⛔ POSTO NÃO SE APAGA
`grant` da migration é `select, insert, update` — sem `delete`. Sair de operação
é `active = false`, porque o ciclo de VT do mês passado aponta para o posto. A
regra 6 do projeto estendida ao cadastro.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg import errors

from operax.core.tenant import TenantContext, tenant_scope, user_scope
from operax.rh.repository import audit

#: O que a trilha de auditoria grava como origem da escrita vinda da tela.
_ORIGEM = {"form": "dp_quadro_de_postos"}


class WorkPostError(RuntimeError):
    """Base das recusas deste módulo."""


class DuplicateWorkPostError(WorkPostError):
    """`unique (tenant_id, unit_id, code)` — a frase da tela de VT virando recusa.

    Dois postos com o mesmo código na mesma unidade tornam a busca da escala
    ambígua, e ambígua ela devolve a escala de outra pessoa, calada.
    """


@dataclass(frozen=True, slots=True)
class WorkPost:
    """Um posto do quadro, com o nome da unidade já resolvido.

    `unit_name` viaja junto porque `unit_id` é uuid na tabela e "Shopping Norte"
    na tela — devolver o uuid obrigaria a tela a fazer a segunda consulta.
    """

    id: UUID
    unit_id: UUID
    unit_name: str
    code: str
    name: str | None
    active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# As perguntas autorizadoras — feitas ao banco, como quem perguntou
# ---------------------------------------------------------------------------
# Sem `where tenant_id`: a policy `unit_read` já filtra, e sob `user_scope` a RLS
# está em vigor. Pedir o filtro aqui seria ritual — e ritual se satisfaz com
# tautologia. Ver o docstring de `UserScope`.
_VISIBLE_UNITS_SQL = """
    select u.id
    from app.unit u
"""

_CAN_SEE_UNIT_SQL = """
    select util.can_see_unit(%(unit_id)s) as visible
"""


async def visible_units(tenant: TenantContext) -> list[UUID]:
    """As unidades que quem perguntou enxerga, respondidas pela policy `unit_read`."""
    async with user_scope(tenant) as scope:
        await scope.execute(_VISIBLE_UNITS_SQL)
        linhas = await scope.fetchall()
    return [linha["id"] for linha in linhas]


async def can_see_unit(tenant: TenantContext, unit_id: UUID) -> bool:
    """`util.can_see_unit`, a mesma função que a policy chama.

    Reimplementá-la como `role in (...)` seria a regra de escopo escrita duas
    vezes, em duas linguagens, divergindo na primeira mudança de `app.user_scope`.
    """
    async with user_scope(tenant) as scope:
        await scope.execute(_CAN_SEE_UNIT_SQL, {"unit_id": unit_id})
        linha = await scope.fetchone()
    return bool(linha and linha["visible"])


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
# `unit_id = any(...)` recebe os ids que a policy liberou. Lista vazia devolve
# zero linhas sem caso especial, que é a resposta certa para quem não enxerga
# unidade nenhuma.
_LIST_SQL = """
    select p.id, p.unit_id, u.name as unit_name, p.code, p.name, p.active, p.created_at
    from app.work_post p
    join app.unit u on u.id = p.unit_id
    where p.tenant_id = %(tenant_id)s
      and p.unit_id = any(%(units)s::uuid[])
      and (%(unit_id)s::uuid is null or p.unit_id = %(unit_id)s::uuid)
    order by u.name, p.code
"""

_LOAD_SQL = """
    select p.id, p.unit_id, u.name as unit_name, p.code, p.name, p.active, p.created_at
    from app.work_post p
    join app.unit u on u.id = p.unit_id
    where p.id = %(post_id)s and p.tenant_id = %(tenant_id)s
"""

# O nome da unidade sai de subconsulta no `returning` para que a linha gravada
# volte completa numa ida só — e a resposta é o que o banco gravou, não o que o
# cliente enviou.
_INSERT_SQL = """
    insert into app.work_post (tenant_id, unit_id, code, name)
    values (%(tenant_id)s, %(unit_id)s, %(code)s, %(name)s)
    returning id, unit_id, code, name, active, created_at,
              (select u.name from app.unit u where u.id = work_post.unit_id) as unit_name
"""

# `coalesce` e não atribuição direta: `PATCH` manda o que mudou, e um campo
# ausente tem de continuar como está. A consequência declarada é que `name` não
# se apaga por esta porta — rótulo em branco não é caso de uso, e distinguir
# "ausente" de "nulo" custaria um sentinela para nada.
_UPDATE_SQL = """
    update app.work_post
       set name   = coalesce(%(name)s::text, name),
           active = coalesce(%(active)s::boolean, active)
     where id = %(post_id)s and tenant_id = %(tenant_id)s
    returning id, unit_id, code, name, active, created_at,
              (select u.name from app.unit u where u.id = work_post.unit_id) as unit_name
"""


def _row_to_post(row: dict[str, Any]) -> WorkPost:
    return WorkPost(
        id=row["id"],
        unit_id=row["unit_id"],
        unit_name=row["unit_name"],
        code=row["code"],
        name=row["name"],
        active=row["active"],
        created_at=row["created_at"],
    )


def _trail(post: WorkPost) -> dict[str, Any]:
    return {
        "unit_id": str(post.unit_id),
        "code": post.code,
        "name": post.name,
        "active": post.active,
    }


async def list_posts(tenant: TenantContext, *, unit_id: UUID | None = None) -> list[WorkPost]:
    """O quadro das unidades que quem pergunta enxerga, ativos e inativos.

    Inativo vem junto de propósito: o posto desativado ainda aparece no histórico
    de VT, e uma lista que o esconde faz o gestor recriá-lo com outro código.
    """
    units = await visible_units(tenant)
    async with tenant_scope(tenant) as scope:
        await scope.execute(_LIST_SQL, {"units": units, "unit_id": unit_id})
        linhas = await scope.fetchall()
    return [_row_to_post(dict(linha)) for linha in linhas]


async def load_post(tenant: TenantContext, post_id: UUID) -> WorkPost | None:
    """Um posto do tenant, sem recorte de unidade — quem recorta é quem chama."""
    async with tenant_scope(tenant) as scope:
        await scope.execute(_LOAD_SQL, {"post_id": post_id})
        linha = await scope.fetchone()
    return _row_to_post(dict(linha)) if linha else None


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------
async def create_post(
    tenant: TenantContext, *, unit_id: UUID, code: str, name: str | None
) -> WorkPost:
    """Cria o posto e a trilha na mesma transação.

    A unicidade é do banco, e a recusa dela chega aqui traduzida: `unique
    (tenant_id, unit_id, code)` é a regra da tela de VT, e uma mensagem de
    `IntegrityError` crua não diria isso a ninguém.
    """
    async with tenant_scope(tenant) as scope:
        try:
            await scope.execute(_INSERT_SQL, {"unit_id": unit_id, "code": code, "name": name})
        except errors.UniqueViolation as choque:
            raise DuplicateWorkPostError(
                f"já existe um posto com o código {code} nesta unidade"
            ) from choque
        linha = await scope.fetchone()
        if linha is None:
            raise WorkPostError(f"o posto {code} não foi gravado")

        criado = _row_to_post(dict(linha))
        await audit(
            scope,
            tenant,
            action="insert",
            entity="work_post",
            entity_id=criado.id,
            antes=None,
            depois=_trail(criado),
            origem=_ORIGEM,
        )
    return criado


async def update_post(
    tenant: TenantContext,
    post_id: UUID,
    *,
    anterior: WorkPost,
    name: str | None,
    active: bool | None,
) -> WorkPost:
    """Renomeia ou tira de operação. `anterior` vem de quem já leu para autorizar.

    Não há caminho para apagar: `active = false` é como o posto sai, porque o
    ciclo de VT do mês passado aponta para ele.
    """
    async with tenant_scope(tenant) as scope:
        await scope.execute(_UPDATE_SQL, {"post_id": post_id, "name": name, "active": active})
        linha = await scope.fetchone()
        if linha is None:
            raise WorkPostError(f"o posto {post_id} não foi atualizado")

        gravado = _row_to_post(dict(linha))
        await audit(
            scope,
            tenant,
            action="update",
            entity="work_post",
            entity_id=gravado.id,
            antes=_trail(anterior),
            depois=_trail(gravado),
            origem=_ORIGEM,
        )
    return gravado
