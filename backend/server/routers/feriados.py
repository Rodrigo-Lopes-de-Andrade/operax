"""Calendário de feriados — Caminho 2, escrita só do owner.

O que um feriado muda não é pouco: para quem é de escala semanal, o dia deixa de
ter jornada — some a falta, aparece a "batida em feriado", e o VT do dia só é
pago a quem bateu. Por isso o dono decidiu em 28/09/2026 que **só `owner`**
escreve o calendário, e não `util.is_admin` (que inclui `hr` e `personnel`).

A pergunta é feita ao banco, como o usuário, à mesma função que a policy
`holiday_owner` chama — e não a `tenant.role` em Python, que o docstring de
`TenantContext` diz não ser autorização sozinho. `app.holiday` não tem grant
para `authenticated`; a gravação sai no `tenant_scope`, junto da linha de
`app.audit_log`, na ordem que `curadoria.py` documenta.

Não existe apagar: feriado errado sai com `active = false`. O motor refaz os dias
de feriado da janela de 90 dias na passada diária (`operax/motor/feriados.py`).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from psycopg.types.json import Jsonb

from operax.core.tenant import tenant_scope, user_scope
from server.deps import CurrentTenant
from server.models import HolidayCreate, HolidayRow, HolidayUpdate

router = APIRouter(prefix="/feriados", tags=["feriados"])

_SEM_PERMISSAO = "O calendário de feriados é do proprietário da conta."

OWNER_SQL = """
    select 'owner' = any(util.roles_in_tenant(%(tenant_id)s)) as owner
"""

_LIST_SQL = """
    select h.id, h.reference_date, h.jurisdiction, h.unit_id, u.name as unit_name,
           h.name, h.active
    from app.holiday h
    left join app.unit u on u.id = h.unit_id and u.tenant_id = h.tenant_id
    where h.tenant_id = %(tenant_id)s
      and h.reference_date between %(start)s::date and %(end)s::date
    order by h.reference_date, u.name nulls first
"""

#: A FK de `holiday.unit_id` não confere tenant: esta leitura é a única coisa
#: entre um id colado à mão e um feriado apontando para a unidade de outro cliente.
_UNIT_SQL = """
    select u.name from app.unit u where u.id = %(unit_id)s and u.tenant_id = %(tenant_id)s
"""

_CREATE_SQL = """
    insert into app.holiday (tenant_id, reference_date, jurisdiction, unit_id, name, created_by)
    values (%(tenant_id)s, %(reference_date)s, %(jurisdiction)s, %(unit_id)s, %(name)s,
            %(user_id)s)
    on conflict do nothing
    returning id, reference_date, jurisdiction, unit_id, name, active
"""

#: O `antes` sai do CTE, que lê a linha como estava antes do `update` — é o que
#: a auditoria guarda, para "quem desativou" ter "o que estava ativo" ao lado.
_UPDATE_SQL = """
    with antes as (
        select a.id, a.active
        from app.holiday a
        where a.id = %(holiday_id)s and a.tenant_id = %(tenant_id)s
        for update
    )
    update app.holiday h set active = %(active)s
    from antes
    where h.id = antes.id and h.tenant_id = %(tenant_id)s
    returning h.id, h.reference_date, h.jurisdiction, h.unit_id, h.name, h.active,
              antes.active as active_before,
              (select u.name from app.unit u
                where u.id = h.unit_id and u.tenant_id = h.tenant_id) as unit_name
"""

_AUDIT_SQL = """
    insert into app.audit_log (tenant_id, user_id, action, entity, entity_id, antes, depois)
    values (%(tenant_id)s, %(user_id)s, %(action)s, 'holiday', %(entity_id)s, %(antes)s,
            %(depois)s)
"""


@router.get("")
async def list_holidays(
    tenant: CurrentTenant, ano: Annotated[int, Query(ge=2000, le=2100)]
) -> list[HolidayRow]:
    """Os feriados do ano, ativos e desativados — a tela mostra os dois."""
    await _require_owner(tenant)
    async with tenant_scope(tenant) as bound:
        await bound.execute(_LIST_SQL, {"start": date(ano, 1, 1), "end": date(ano, 12, 31)})
        rows = await bound.fetchall()
    return [HolidayRow(**row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_holiday(tenant: CurrentTenant, request: HolidayCreate) -> HolidayRow:
    await _require_owner(tenant)
    unit_name = None
    async with tenant_scope(tenant) as bound:
        if request.unit_id is not None:
            await bound.execute(_UNIT_SQL, {"unit_id": request.unit_id})
            unit = await bound.fetchone()
            if unit is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Unidade não pertence a este cliente.",
                )
            unit_name = unit["name"]

        await bound.execute(_CREATE_SQL, {**request.model_dump(), "user_id": tenant.user_id})
        row = await bound.fetchone()
        # Os dois uniques são parciais (nacional por dia; local por dia e
        # unidade), e desativar não abre vaga: reativa-se a linha existente.
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um feriado nesta data para esta abrangência.",
            )

        await bound.execute(
            _AUDIT_SQL,
            {
                "user_id": tenant.user_id,
                "action": "insert",
                "entity_id": str(row["id"]),
                "antes": None,
                "depois": Jsonb(_as_json(row)),
            },
        )
    return HolidayRow(**row, unit_name=unit_name)


@router.patch("/{holiday_id}")
async def update_holiday(
    tenant: CurrentTenant, holiday_id: UUID, request: HolidayUpdate
) -> HolidayRow:
    """Ativa ou desativa. Não existe apagar."""
    await _require_owner(tenant)
    async with tenant_scope(tenant) as bound:
        await bound.execute(_UPDATE_SQL, {"holiday_id": holiday_id, "active": request.active})
        row = await bound.fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Feriado não encontrado."
            )
        await bound.execute(
            _AUDIT_SQL,
            {
                "user_id": tenant.user_id,
                "action": "update",
                "entity_id": str(holiday_id),
                "antes": Jsonb({"active": row["active_before"]}),
                "depois": Jsonb({"active": request.active}),
            },
        )
    return HolidayRow(**{k: v for k, v in row.items() if k != "active_before"})


async def _require_owner(tenant: CurrentTenant) -> None:
    """403 antes de a transação de `service_role` abrir, e não depois."""
    async with user_scope(tenant) as scope:
        await scope.execute(OWNER_SQL, {"tenant_id": tenant.tenant_id})
        row = await scope.fetchone()
    if not (row and row["owner"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_SEM_PERMISSAO)


def _as_json(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value if value is None or isinstance(value, bool | str) else str(value)
        for key, value in row.items()
    }
