"""Curadoria do que a origem não diz — Caminho 2.

Duas filas, cada uma com a sua fila e o seu botão: departamento → unidade, e
horário → rotação. São o mesmo problema em dois eixos — o Secullum não carrega o
conceito de pátio nem consegue escrever um ciclo de 48 h —, e por isso a mesma
forma: uma linha curada por objeto do espelho, validada por gente, com carimbo
de quem e quando.

O que decide quem entra aqui é `util.is_admin`, perguntado ao banco como o
usuário que perguntou — a mesma função que as policies `mapa_admin` e
`rotation_map_admin` chamam, e não uma cópia dela em Python.

UMA DIFERENÇA ENTRE AS DUAS FILAS, E ELA MUDA O ESCOPO DA LEITURA
A de unidade sai de `app.department`, que é domínio nosso e tem policy: ela lê
como o usuário. A de rotação sai de `secullum."Horario"`, e `secullum` não tem
`usage` para `authenticated` desde a migration 01 — não é RLS que a impede, é o
grant. Ela autoriza no `user_scope` e lê no `tenant_scope`, que é a ordem que
`operax/motor/marcacao.py` já documenta.

POR QUE A ESCRITA SAI DO `user_scope`
`app.unit_secullum_map` tem policy de escrita para admin, então a gravação do
mapa **poderia** rodar como o usuário (`app.employee` não pode desde a P1.2b).
`app.audit_log` não tem: ele é escrito por `service_role`, e o motivo é o mesmo
que `operax/rh/repository.py` documenta — a linha e a linha de auditoria que a
descreve precisam commitar juntas, senão existe um estado em que o mapa mudou e
ninguém sabe quem mudou.

Então a autorização acontece antes, no `user_scope`, e a transação de escrita é
`service_role`. É a ordem de sempre neste backend: quem pode, pergunta-se à
policy; o que se grava, grava-se junto da trilha.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from psycopg.types.json import Jsonb

from operax.core.tenant import tenant_scope, user_scope
from operax.motor import mapeamento, rotacao
from server.deps import CurrentTenant
from server.models import (
    ExceptionTrackingApplied,
    ExceptionTrackingRequest,
    RotationApplied,
    RotationRequest,
    RotationRow,
    RotationScreen,
    UnitMappingApplied,
    UnitMappingRequest,
    UnitMappingRow,
    UnitMappingScreen,
    UnitOption,
    UnitSuggestion,
)

router = APIRouter(prefix="/curadoria", tags=["curadoria"])

_SEM_PERMISSAO = "Curar o mapa de unidades é do administrador do cliente."
_SEM_PERMISSAO_ROTACAO = "Declarar a escala de um horário é do administrador do cliente."

#: Quantos dias de batida a fila mostra. Duas semanas e meia cobrem sete voltas de
#: um 12x36, que é quanto basta para alguém reconhecer a escala olhando.
_JANELA_OBSERVADA = 21


@router.get("/unidades")
async def unit_mapping(tenant: CurrentTenant) -> UnitMappingScreen:
    """A fila: o que falta mapear, o que está provisório e o que já foi curado."""
    async with user_scope(tenant) as scope:
        await _require_admin(scope, tenant)

        await scope.execute(mapeamento.UNITS_SQL, {})
        units = await scope.fetchall()

        await scope.execute(mapeamento.ROWS_SQL, {})
        rows = await scope.fetchall()

        await scope.execute(mapeamento.SUMMARY_SQL, {"tenant_id": tenant.tenant_id})
        summary = await scope.fetchone()

    active = summary["active"] if summary else 0
    without_unit = summary["without_unit"] if summary else 0
    provisional = summary["provisional"] if summary else 0

    return UnitMappingScreen(
        rows=[_row(row, units) for row in rows],
        units=[UnitOption(**unit) for unit in units],
        active=active,
        validated=active - without_unit - provisional,
        provisional=provisional,
        without_unit=without_unit,
    )


@router.post("/unidades")
async def validate_unit_mapping(
    tenant: CurrentTenant, request: UnitMappingRequest
) -> UnitMappingApplied:
    """Grava os pares escolhidos como validados, e aloca quem estava sem unidade."""
    async with user_scope(tenant) as scope:
        await _require_admin(scope, tenant)

    validados = 0
    alocados = 0

    async with tenant_scope(tenant) as bound:
        for par in request.mappings:
            params = {
                "user_id": tenant.user_id,
                "secullum_department_id": par.secullum_department_id,
                "unit_id": par.unit_id,
            }
            await bound.execute(mapeamento.VALIDATE_SQL, params)
            gravado = await bound.fetchall()

            # Zero linha é um dos dois ids fora deste cliente. A FK de
            # `unit_secullum_map.unit_id` não confere tenant, então esta é a
            # única coisa entre um id colado à mão e um mapa entre clientes.
            if not gravado:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"Departamento {par.secullum_department_id} ou unidade "
                        "escolhida não pertencem a este cliente."
                    ),
                )

            validados += 1

            await bound.execute(mapeamento.ALLOCATE_SQL, params)
            movidos = await bound.fetchall()
            alocados += len(movidos)

            await bound.execute(
                mapeamento.AUDIT_SQL,
                {
                    "user_id": tenant.user_id,
                    "entity_id": str(par.secullum_department_id),
                    "antes": None,
                    "depois": Jsonb(
                        {
                            "unit_id": str(par.unit_id),
                            "employees_allocated": len(movidos),
                        }
                    ),
                },
            )

    return UnitMappingApplied(validated=validados, employees_allocated=alocados)


@router.get("/rotacoes")
async def rotation_queue(tenant: CurrentTenant) -> RotationScreen:
    """A fila: horários sem expediente declarado, ordenados por quanta gente giram.

    A leitura roda sob `tenant_scope`, e não como o usuário, porque ela sai de
    `secullum."Horario"` — e `secullum` não tem `usage` para `authenticated`
    desde a migration 01. A autorização acontece antes, no `user_scope`, e não
    alarga escopo nenhum: `employee_read` já devolve o tenant inteiro para quem é
    admin, que é exatamente quem esta rota deixa entrar.
    """
    async with user_scope(tenant) as scope:
        await _require_admin(scope, tenant, _SEM_PERMISSAO_ROTACAO)

    async with tenant_scope(tenant) as bound:
        await bound.execute(rotacao.ROWS_SQL, {"dias": _JANELA_OBSERVADA})
        rows = await bound.fetchall()

        await bound.execute(rotacao.SUMMARY_SQL, {})
        summary = await bound.fetchone()

    return RotationScreen(
        rows=[RotationRow(**row) for row in rows],
        on_blank_schedule=summary["on_blank_schedule"] if summary else 0,
        validated=summary["validated"] if summary else 0,
        provisional=summary["provisional"] if summary else 0,
    )


@router.post("/rotacoes")
async def validate_rotation(tenant: CurrentTenant, request: RotationRequest) -> RotationApplied:
    """Carimba a rotação de um horário, e devolve quanta gente ela tira da confiança 0."""
    async with user_scope(tenant) as scope:
        await _require_admin(scope, tenant, _SEM_PERMISSAO_ROTACAO)

    payload = request.model_dump()

    async with tenant_scope(tenant) as bound:
        await bound.execute(rotacao.VALIDATE_SQL, {**payload, "user_id": tenant.user_id})
        gravado = await bound.fetchall()

        # Zero linha é um horário que não é deste cliente. `secullum_schedule_id`
        # é parte da PK e não tem FK, então este join é a única coisa entre um id
        # colado à mão e uma escala gravada sobre o horário de outro tenant.
        if not gravado:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(f"Horário {request.secullum_schedule_id} não pertence a este cliente."),
            )

        await bound.execute(
            rotacao.AFFECTED_SQL,
            {"secullum_schedule_id": request.secullum_schedule_id},
        )
        afetados = await bound.fetchone()
        cobertos = afetados["employees"] if afetados else 0

        await bound.execute(
            rotacao.AUDIT_SQL,
            {
                "user_id": tenant.user_id,
                "entity_id": str(request.secullum_schedule_id),
                "antes": None,
                "depois": Jsonb(
                    {
                        **{
                            chave: str(valor) if valor is not None else None
                            for chave, valor in payload.items()
                        },
                        "employees_covered": cobertos,
                    }
                ),
            },
        )

    return RotationApplied(
        secullum_schedule_id=request.secullum_schedule_id, employees_covered=cobertos
    )


@router.post("/fora-do-motor")
async def set_exception_tracking(
    tenant: CurrentTenant, request: ExceptionTrackingRequest
) -> ExceptionTrackingApplied:
    """Tira do motor — ou devolve a ele — todo mundo de um horário.

    É a outra resposta possível para um horário que não declara expediente: não
    é que falte a rotação, é que não há jornada devida. Quem está aqui deixa de
    materializar `app.expected_workday` e passa a ser contado à parte no monitor,
    separado de `unrostered`, que é falha de cobertura e tem a mesma aparência.
    """
    async with user_scope(tenant) as scope:
        await _require_admin(scope, tenant, _SEM_PERMISSAO_ROTACAO)

    async with tenant_scope(tenant) as bound:
        await bound.execute(
            rotacao.EXCEPTION_SQL,
            {
                "secullum_schedule_id": request.secullum_schedule_id,
                "exception_tracking": request.exception_tracking,
            },
        )
        mudados = await bound.fetchall()

        # Zero linha aqui NÃO é recusa: pode ser um horário de outro cliente e
        # pode ser todo mundo já do lado pedido. A diferença não muda o que o
        # sistema faz — nada foi alterado nos dois casos — e inventar um 422
        # para o segundo transformaria "já estava assim" em erro.
        await bound.execute(
            rotacao.EXCEPTION_AUDIT_SQL,
            {
                "user_id": tenant.user_id,
                "entity_id": str(request.secullum_schedule_id),
                "antes": None,
                "depois": Jsonb(
                    {
                        "exception_tracking": request.exception_tracking,
                        "employees_changed": len(mudados),
                    }
                ),
            },
        )

    return ExceptionTrackingApplied(
        secullum_schedule_id=request.secullum_schedule_id,
        employees_changed=len(mudados),
    )


async def _require_admin(scope: Any, tenant: CurrentTenant, mensagem: str = _SEM_PERMISSAO) -> None:
    await scope.execute(mapeamento.PERMISSION_SQL, {"tenant_id": tenant.tenant_id})
    row = await scope.fetchone()
    if not (row and row["admin"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=mensagem)


def _row(row: dict[str, Any], units: list[dict[str, Any]]) -> UnitMappingRow:
    """A sugestão entra na linha, e nunca no lugar do que foi curado.

    Um departamento já validado não recebe palpite: oferecer uma alternativa a
    uma decisão que uma pessoa tomou é convidar a desfazê-la por engano, e a
    tela tem o seletor de unidade para quem quiser mesmo trocar.
    """
    palpite = None
    if row["validated_at"] is None:
        sugestao = mapeamento.suggest(row["department"], units)
        if sugestao is not None:
            palpite = UnitSuggestion(
                unit_id=UUID(sugestao.unit_id),
                unit_name=sugestao.unit_name,
                confidence=sugestao.confidence,
            )

    return UnitMappingRow(**row, suggestion=palpite)
