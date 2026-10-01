"""A alçada de aprovação de justificativas — Caminho 2, como o usuário.

Duas portas, e as duas rodam sob `user_scope`: quem responde é o banco, com a RLS
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
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from psycopg import errors

from operax.core.tenant import user_scope
from operax.motor.relogio import user_clock
from server.deps import CurrentTenant
from server.models import (
    ApprovalQueue,
    ApprovalQueueRow,
    JustificationReviewApplied,
    JustificationReviewRequest,
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
    if (ano is None) != (mes is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="ano e mes vão juntos: informe os dois, ou nenhum.",
        )
    async with user_scope(tenant) as scope:
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
