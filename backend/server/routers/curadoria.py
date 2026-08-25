"""Curadoria do mapa origem → unidade — Caminho 2.

Duas rotas: a fila e o botão. O que decide quem entra aqui é `util.is_admin`,
perguntado ao banco como o usuário que perguntou — a mesma função que a policy
`mapa_admin` chama, e não uma cópia dela em Python.

POR QUE A ESCRITA SAI DO `user_scope`
`app.unit_secullum_map` e `app.employee` têm policy de escrita para admin, então
a gravação **poderia** rodar como o usuário. `app.audit_log` não tem: ele é
escrito por `service_role`, e o motivo é o mesmo que `operax/rh/repository.py`
documenta — a linha e a linha de auditoria que a descreve precisam commitar
juntas, senão existe um estado em que o mapa mudou e ninguém sabe quem mudou.

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
from operax.motor import mapeamento
from server.deps import CurrentTenant
from server.models import (
    UnitMappingApplied,
    UnitMappingRequest,
    UnitMappingRow,
    UnitMappingScreen,
    UnitOption,
    UnitSuggestion,
)

router = APIRouter(prefix="/curadoria", tags=["curadoria"])

_SEM_PERMISSAO = "Curar o mapa de unidades é do administrador do cliente."


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


async def _require_admin(scope: Any, tenant: CurrentTenant) -> None:
    await scope.execute(mapeamento.PERMISSION_SQL, {"tenant_id": tenant.tenant_id})
    row = await scope.fetchone()
    if not (row and row["admin"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_SEM_PERMISSAO)


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
