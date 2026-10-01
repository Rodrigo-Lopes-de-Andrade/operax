"""A justificativa de uma ocorrência — Caminho 2.

A LISTA DE PENDENTES **NÃO** ESTÁ AQUI, E É DE PROPÓSITO
`public.fn_pending_justification` (migration 23) é `security invoker`, com grant
só para `authenticated`, e devolve o mesmo recorte que `vw_deviation_event` já
devolve ao navegador. Então ela é Caminho 1: a tela lê direto do Supabase, sob a
RLS do usuário. Passá-la por aqui seria trocar uma policy que o banco aplica por
uma verificação que este arquivo teria de lembrar de fazer.

O que precisa do backend é a escrita, e só ela.

QUEM PODE NÃO É `is_admin`
Quem enxerga o evento pela RLS pode explicá-lo (a policy `justification_write`
saiu na P1.2b, com a escrita de `authenticated`). É recorte diferente do da curadoria de
propósito — ver `operax/motor/justificativa.py`. A autorização é ler o evento
como o usuário: se a RLS o devolve, a justificativa pode ser escrita.

QUEM EXPLICA NÃO DECIDE (P1.2)
A justificativa nasce sempre `pending`. Aprovar ou reprovar é da alçada, por
`public.fn_revisar_justificativa` — não por esta rota.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from psycopg.types.json import Jsonb

from operax.core.tenant import tenant_scope, user_scope
from operax.motor import justificativa
from server.deps import CurrentTenant
from server.models import JustificationApplied, JustificationVerdict

router = APIRouter(prefix="/ocorrencias", tags=["justificativas"])

#: A mesma frase para "não existe" e para "não é do seu escopo". Distinguir as
#: duas contaria a um cliente que um id do outro existe, e contaria a um
#: supervisor quais ocorrências há fora da unidade dele.
_FORA_DE_ALCANCE = "Ocorrência não encontrada ou fora do seu escopo."


@router.post("/{deviation_event_id}/justificativa", status_code=status.HTTP_201_CREATED)
async def record_verdict(
    tenant: CurrentTenant,
    deviation_event_id: UUID,
    request: JustificationVerdict,
) -> JustificationApplied:
    """Registra a explicação de um desvio, que nasce `pending`.

    Escreve uma linha nova a cada explicação — nunca atualiza a anterior —,
    porque a pergunta que `app.justification` responde é quem disse o quê, e
    quando. A decisão é da alçada (`public.fn_revisar_justificativa`).
    """
    async with user_scope(tenant) as scope:
        await scope.execute(
            justificativa.EVENT_SQL,
            {"deviation_event_id": str(deviation_event_id)},
        )
        evento = await scope.fetchone()

    if evento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_FORA_DE_ALCANCE)

    async with tenant_scope(tenant) as bound:
        await bound.execute(
            justificativa.INSERT_SQL,
            {
                "deviation_event_id": str(deviation_event_id),
                "employee_id": str(evento["employee_id"]),
                "reference_date": evento["reference_date"],
                "text": request.text,
                "user_id": str(tenant.user_id),
            },
        )
        gravado = await bound.fetchone()

        # `auth.users` é gerenciado pelo Supabase e o `insert ... select` acima
        # não escreve linha nenhuma se o id do token não estiver lá. Não é caso
        # impossível: um usuário apagado no painel mantém o JWT válido até
        # expirar, e gravar sem autor destruiria a trilha em silêncio.
        if gravado is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário do token não existe mais.",
            )

        await bound.execute(
            justificativa.AUDIT_SQL,
            {
                "user_id": str(tenant.user_id),
                "entity_id": str(gravado["id"]),
                "depois": Jsonb(
                    {
                        "deviation_event_id": str(deviation_event_id),
                        "employee_id": str(evento["employee_id"]),
                        "reference_date": str(evento["reference_date"]),
                        "type": evento["type"],
                        "status": justificativa.STATUS_ON_WRITE,
                    }
                ),
            },
        )

    return JustificationApplied(
        justification_id=gravado["id"],
        deviation_event_id=deviation_event_id,
        employee_name=evento["employee_name"],
        reference_date=evento["reference_date"],
        status=justificativa.STATUS_ON_WRITE,
    )
