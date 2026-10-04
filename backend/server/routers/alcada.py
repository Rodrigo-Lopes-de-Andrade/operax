"""A alçada de aprovação de justificativas — Caminho 2, como o usuário.

Todas as portas rodam sob `user_scope`: quem responde é o banco, com a RLS
e o papel de quem perguntou. Nenhuma abre `tenant_scope`, e cada requisição usa
UMA conexão do pool: até o relógio do tenant é lido dentro da transação do
usuário (`user_clock`), porque segurar uma conexão esperando outra esgota o pool
com dez leituras simultâneas.

A FILA (`GET /alcada/fila`)
`public.fn_fila_aprovacao` (P1.3) é `security invoker`: a RLS recorta tenant e
escopo, e a própria função só devolve linha a quem é `hr` ou `owner`. A rota
pergunta o papel ANTES, na mesma transação, para que o supervisor receba 403 em
vez de uma fila vazia que pareceria "não há nada para aprovar". O filtro por
colaborador é dado individual: é por isso que esta leitura é Caminho 2.
A competência e a janela vêm do banco (`util.competencia_de`,
`util.competencia_janela`) e voltam na resposta: a regra 21→20 não tem cópia
aqui nem na tela. O "hoje" da competência corrente é o do relógio do tenant,
lido depois da checagem de papel: para `hr`/`owner` a RLS de `app.unit` mostra o
tenant inteiro, e o fuso sai o mesmo que o motor usa.
A linha que o chamador não pode revisar (`own_justification`, `owner_only`)
continua na fila, com `can_review = false` e o código em `blocked_reason` —
calculados pelo banco com a regra da RPC, não aqui.

A REVISÃO (`POST /alcada/justificativas/{id}/revisao`)
`public.fn_revisar_justificativa` (P1.2) é `security definer` e checa o papel
ela mesma — a rota não repete a checagem, só traduz as nove recusas `P0001`
para HTTP, com o código em `detail` (a tela decide a frase pelo código). A
revisão é a própria trilha: `app.justification_review` guarda quem, quando e o
quê, e não há `audit_log` aqui (a RPC não grava; ver a P1.2).

A LISTA DO LANÇAMENTO (`GET /alcada/lancamento`)
As revisões aprovadas da competência — do FATO, pela mesma janela 21→20 da
fila (decisão do dono, 04/10/2026) —, pendentes e lançadas juntas. É consulta
direta sob `user_scope`, sem objeto em `public`: a RLS recorta, o pré-teste de
papel é o da fila (403), e a própria consulta repete o papel no tenant da linha.
Nome de quem aprovou e de quem lançou NÃO vem: está em `auth.users`, que
`authenticated` não lê; vão os uuids (`reviewed_by`, `posted_by`).

O LANÇAMENTO (`POST /alcada/revisoes/{id}/lancamento`)
`public.fn_marcar_lancado` (P1.4) é `security definer`, checa o papel ela mesma
e grava `posted_to_source_at`/`posted_by` uma vez só. Como na revisão, a rota só
traduz as quatro recusas `P0001`, com o código em `detail`. Quando e quem são do
banco (`now()` e o `sub` do token): o corpo é fechado e não os aceita.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from psycopg import errors

from operax.core.tenant import TenantContext, UserScope, user_scope
from operax.motor.relogio import user_clock
from server.deps import CurrentTenant
from server.models import (
    ApprovalQueue,
    ApprovalQueueRow,
    JustificationReviewApplied,
    JustificationReviewRequest,
    PostingList,
    PostingListRow,
    ReviewPostingApplied,
    ReviewPostingRequest,
)

router = APIRouter(prefix="/alcada", tags=["alcada"])

#: O mesmo código que a RPC de revisão devolve a quem não é do RH: a tela trata
#: as duas portas por uma chave só.
NOT_HR = "not_hr"

#: As nove recusas de `fn_revisar_justificativa`, na ordem da migration
#: `alcada_justification_review`, e o status de cada uma. 403: quem pede não
#: tem a alçada para ESTA linha; 404: a linha não existe para quem pede (a de
#: outro tenant responde igual, de propósito); 409: o pedido é bem formado e o
#: estado recusa; 422: o pedido está incompleto.
REVIEW_STATUS = {
    "not_hr": status.HTTP_403_FORBIDDEN,
    "justification_not_found": status.HTTP_404_NOT_FOUND,
    "own_justification": status.HTTP_403_FORBIDDEN,
    "owner_only": status.HTTP_403_FORBIDDEN,
    "already_reviewed": status.HTTP_409_CONFLICT,
    "source_is_mirror": status.HTTP_409_CONFLICT,
    "not_pending": status.HTTP_409_CONFLICT,
    "no_open_period": status.HTTP_409_CONFLICT,
    "rejection_needs_reason": status.HTTP_422_UNPROCESSABLE_CONTENT,
}

HR_OR_OWNER_SQL = """
    select util.roles_in_tenant(%(tenant_id)s) && array['hr','owner']::app.user_role[] as allowed
"""

#: A competência que contém "hoje" — derivada da janela no banco, sem cópia da
#: regra 21→20 aqui.
CURRENT_SQL = """
    select period_year, period_month from util.competencia_de(%(today)s)
"""

WINDOW_SQL = """
    select period_start, period_end from util.competencia_janela(%(year)s, %(month)s)
"""

QUEUE_SQL = """
    select justification_id, employee_id, employee_name, unit_id, unit_name,
           reference_date, type, type_description, minutes, text, author_name, created_at,
           can_review, blocked_reason
    from public.fn_fila_aprovacao(%(year)s, %(month)s, %(unit_id)s, %(employee_id)s,
                                  %(de)s, %(ate)s)
"""

REVIEW_SQL = """
    select public.fn_revisar_justificativa(%(justification_id)s, %(decision)s, %(reason)s)
           as review_id
"""

#: As quatro recusas de `fn_marcar_lancado`, na ordem da migration
#: `alcada_mark_posted`. 403: não é do RH; 404: a revisão não existe para quem
#: pede (a de outro tenant responde igual); 409: o estado recusa — reprovada não
#: se lança, e lançada não se relança.
POSTING_STATUS = {
    "not_hr": status.HTTP_403_FORBIDDEN,
    "review_not_found": status.HTTP_404_NOT_FOUND,
    "not_approved": status.HTTP_409_CONFLICT,
    "already_posted": status.HTTP_409_CONFLICT,
}

#: A lista do lançamento: as revisões APROVADAS cujo FATO (`reference_date` da
#: justificativa) cai na janela 21→20 da competência — decisão do dono de
#: 04/10/2026, a mesma competência da fila, sem cópia da regra. Pendente é
#: `posted_to_source_at` nulo; vêm primeiro.
#: Roda como o usuário: `review_read`, `justification_read`, `employee_read` e a
#: RLS de `unit`/`deviation_event` recortam. O papel `hr`/`owner` é checado de
#: novo AQUI, no tenant da linha, para o caso de o pré-teste da rota sumir: a
#: RLS deixa o supervisor ler a revisão da unidade dele. O tenant do token
#: também filtra (`tenant.py`): um usuário em dois tenants não mistura os dois.
POSTING_LIST_SQL = """
    select r.id as review_id, r.justification_id, j.employee_id, e.name as employee_name,
           coalesce(d.unit_id, e.unit_id) as unit_id, u.name as unit_name,
           j.reference_date, d.type, t.description as type_description, d.minutes,
           j.text, j.author_name, r.reviewed_by, r.reviewed_at,
           r.posted_to_source_at, r.posted_by
    from util.competencia_janela(%(year)s, %(month)s) w
    join app.justification j
         on j.reference_date between w.period_start and w.period_end
    join app.justification_review r on r.justification_id = j.id
    join app.employee e on e.id = j.employee_id
    left join app.deviation_event d on d.id = j.deviation_event_id
    left join app.deviation_type t on t.code = d.type
    left join app.unit u on u.id = coalesce(d.unit_id, e.unit_id)
    where r.decision = 'approved'
      and r.tenant_id = %(tenant_id)s
      and util.roles_in_tenant(r.tenant_id) && array['hr','owner']::app.user_role[]
      and (%(unit_id)s::uuid     is null or coalesce(d.unit_id, e.unit_id) = %(unit_id)s::uuid)
      and (%(employee_id)s::uuid is null or j.employee_id = %(employee_id)s::uuid)
      and (%(de)s::date          is null or j.reference_date >= %(de)s::date)
      and (%(ate)s::date         is null or j.reference_date <= %(ate)s::date)
    order by r.posted_to_source_at is not null, j.reference_date, e.name, r.reviewed_at
"""

POSTING_SQL = """
    select public.fn_marcar_lancado(%(review_id)s) as posted_to_source_at
"""


def _ano_e_mes_juntos(ano: int | None, mes: int | None) -> None:
    if (ano is None) != (mes is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="ano e mes vão juntos: informe os dois, ou nenhum.",
        )


async def _competencia(
    scope: UserScope, tenant: TenantContext, ano: int | None, mes: int | None
) -> tuple[int, int, dict[str, Any]]:
    """O papel primeiro (403 `not_hr`), depois a competência e a janela — tudo
    na transação do usuário. Comum à fila e à lista de lançamento."""
    await scope.execute(HR_OR_OWNER_SQL, {"tenant_id": tenant.tenant_id})
    row = await scope.fetchone()
    if not (row and row["allowed"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=NOT_HR)
    if ano is None or mes is None:
        # Na mesma transação, depois do papel: é `hr`/`owner`, a RLS de
        # `app.unit` lhe mostra o tenant inteiro, e a requisição segura uma
        # conexão só do pool.
        today = (await user_clock(scope)).today
        await scope.execute(CURRENT_SQL, {"today": today})
        current = await scope.fetchone()
        ano, mes = current["period_year"], current["period_month"]
    await scope.execute(WINDOW_SQL, {"year": ano, "month": mes})
    window = await scope.fetchone()
    return ano, mes, window


@router.get("/fila")
async def approval_queue(
    tenant: CurrentTenant,
    ano: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    mes: Annotated[int | None, Query(ge=1, le=12)] = None,
    unidade: UUID | None = None,
    colaborador: UUID | None = None,
    de: date | None = None,
    ate: date | None = None,
) -> ApprovalQueue:
    """As justificativas `pending` sem revisão da competência (janela 21→20).

    `ano` e `mes` vão juntos; sem os dois, vale a competência que contém hoje no
    relógio do tenant. A resposta traz a competência e a janela usadas — a tela
    as mostra e limita as datas por elas.

    `de`/`ate` são opcionais e inclusivos (um dia: `de = ate`) e só estreitam a
    janela — uma data fora dela devolve lista vazia, nunca alarga a competência.
    """
    _ano_e_mes_juntos(ano, mes)
    async with user_scope(tenant) as scope:
        ano, mes, window = await _competencia(scope, tenant, ano, mes)
        await scope.execute(
            QUEUE_SQL,
            {
                "year": ano,
                "month": mes,
                "unit_id": unidade,
                "employee_id": colaborador,
                "de": de,
                "ate": ate,
            },
        )
        rows = await scope.fetchall()
    return ApprovalQueue(
        ano=ano,
        mes=mes,
        period_start=window["period_start"],
        period_end=window["period_end"],
        rows=[ApprovalQueueRow(**r) for r in rows],
    )


@router.post("/justificativas/{justification_id}/revisao", status_code=status.HTTP_201_CREATED)
async def review_justification(
    tenant: CurrentTenant,
    justification_id: UUID,
    request: JustificationReviewRequest,
) -> JustificationReviewApplied:
    """Aprova ou reprova. Aprovar move o desvio para `justified` na mesma
    transação; reprovar o devolve à fila do supervisor."""
    try:
        async with user_scope(tenant) as scope:
            await scope.execute(
                REVIEW_SQL,
                {
                    "justification_id": justification_id,
                    "decision": request.decisao,
                    "reason": request.motivo,
                },
            )
            row = await scope.fetchone()
    except errors.RaiseException as recusa:
        code = recusa.diag.message_primary or ""
        if code not in REVIEW_STATUS:
            raise
        raise HTTPException(status_code=REVIEW_STATUS[code], detail=code) from None
    if row is None:
        raise RuntimeError("fn_revisar_justificativa não devolveu o id da revisão")
    return JustificationReviewApplied(
        review_id=row["review_id"],
        justification_id=justification_id,
        decision=request.decisao,
    )


@router.get("/lancamento")
async def posting_list(
    tenant: CurrentTenant,
    ano: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    mes: Annotated[int | None, Query(ge=1, le=12)] = None,
    unidade: UUID | None = None,
    colaborador: UUID | None = None,
    de: date | None = None,
    ate: date | None = None,
) -> PostingList:
    """O que falta lançar no Secullum, e o que já foi — da competência do fato.

    Mesmos parâmetros e mesma competência da fila: `ano`/`mes` juntos ou
    nenhum (então vale a que contém hoje no relógio do tenant), e `de`/`ate`
    só estreitam a janela. Devolve pendentes e lançadas juntas, pendentes
    primeiro; `posted_to_source_at` nulo é pendente, e a tela separa.
    """
    _ano_e_mes_juntos(ano, mes)
    async with user_scope(tenant) as scope:
        ano, mes, window = await _competencia(scope, tenant, ano, mes)
        await scope.execute(
            POSTING_LIST_SQL,
            {
                "year": ano,
                "month": mes,
                "tenant_id": tenant.tenant_id,
                "unit_id": unidade,
                "employee_id": colaborador,
                "de": de,
                "ate": ate,
            },
        )
        rows = await scope.fetchall()
    return PostingList(
        ano=ano,
        mes=mes,
        period_start=window["period_start"],
        period_end=window["period_end"],
        rows=[PostingListRow(**r) for r in rows],
    )


@router.post("/revisoes/{review_id}/lancamento")
async def mark_posted(
    tenant: CurrentTenant,
    review_id: UUID,
    request: ReviewPostingRequest,
) -> ReviewPostingApplied:
    """O RH declara que digitou no Secullum a decisão desta revisão aprovada.

    Definitivo: não existe desfazer, e a segunda marcação é 409 `already_posted`.
    O corpo é `{}`, obrigatório e fechado: sem ele não há onde recusar um
    `posted_by` que o cliente mande.
    """
    try:
        async with user_scope(tenant) as scope:
            await scope.execute(POSTING_SQL, {"review_id": review_id})
            row = await scope.fetchone()
    except errors.RaiseException as recusa:
        code = recusa.diag.message_primary or ""
        if code not in POSTING_STATUS:
            raise
        raise HTTPException(status_code=POSTING_STATUS[code], detail=code) from None
    if row is None or row["posted_to_source_at"] is None:
        raise RuntimeError("fn_marcar_lancado não devolveu a marca")
    return ReviewPostingApplied(
        review_id=review_id,
        posted_to_source_at=row["posted_to_source_at"],
        posted_by=tenant.user_id,
    )
