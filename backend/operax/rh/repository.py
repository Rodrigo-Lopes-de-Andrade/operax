"""Every statement the HR import runs, and which identity runs it.

TWO IDENTITIES, ON PURPOSE
Reads go through `user_scope`: the transaction becomes the authenticated user and
the policies that already guard the browser decide what comes back. That is what
makes the scope hold on the *write* without the write re-implementing it — a line
naming somebody the importer cannot see never resolves to an id, and the answer is
"matrícula não existe neste cliente".

Writes go through `tenant_scope` (`service_role`), for one reason: `app.audit_log`
grants insert to nobody but `service_role` — the log is deliberately out of the
panel's reach — and SPEC §8 requires every write to reference its author and its
origin. The row and the audit row that describes it therefore have to commit
together, and they can only do that in a transaction that may write both.

What is *not* re-implemented in Python is the authorisation: `check_permissions`
asks `util.is_admin` and `util.can_see_domain` — the same functions the policies
call — as the user who is asking, and the endpoint refuses before opening the
write transaction.

WHY THE COLUMN NAMES ARE INTERPOLATED
The select list and the set list are built from `templates.TEMPLATES`, a frozen
registry that fails at import time for a column outside `ownership.MATRIX`, and
the matrix itself is checked against the live schema by
`scripts/95_teste_matriz_rh.py` on every `make db-test`. No caller value ever
reaches SQL text; every value travels as a bound parameter.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from operax.core.tenant import TenantContext, tenant_scope, user_scope
from operax.rh.importer import LineOutcome
from operax.rh.templates import Strategy, Template, select_sql

_PERMISSIONS_SQL = """
    select util.is_admin(%(tenant_id)s)                          as admin,
           util.can_see_domain(%(tenant_id)s, 'pii')             as pii,
           util.can_see_domain(%(tenant_id)s, 'compensation')    as compensation,
           util.can_see_domain(%(tenant_id)s, 'health')          as health
"""

# Competência de mês 13 é décimo terceiro, não um mês do calendário: o fim dela é
# 31/12 do próprio ano.
_LAST_CLOSED_SQL = """
    select max(
             case when month = 13 then make_date(year::int, 12, 31)
                  else (make_date(year::int, month::int, 1) + interval '1 month - 1 day')::date
             end
           ) as ends_on
    from app.payroll_period
    where tenant_id = %(tenant_id)s and status = 'fechada'
"""

_CREATE_IMPORT_SQL = """
    insert into app.file_import
      (id, tenant_id, type, storage_path, file_name, layout_version, uploaded_by, status)
    values
      (%(import_id)s, %(tenant_id)s, %(type)s, %(storage_path)s, %(file_name)s,
       %(layout_version)s, %(uploaded_by)s, 'received')
"""

_SAVE_REPORT_SQL = """
    update app.file_import
       set status = %(status)s,
           rows_total = %(rows_total)s,
           rows_ok = %(rows_ok)s,
           rows_error = %(rows_error)s,
           report = %(report)s
     where id = %(import_id)s and tenant_id = %(tenant_id)s
    returning id
"""

_LOAD_IMPORT_SQL = """
    select id, type, storage_path, file_name, layout_version, status,
           rows_total, rows_ok, rows_error
    from app.file_import
    where id = %(import_id)s and tenant_id = %(tenant_id)s
"""

_AUDIT_SQL = """
    insert into app.audit_log
      (tenant_id, user_id, action, entity, entity_id, antes, depois)
    values
      (%(tenant_id)s, %(user_id)s, %(action)s, %(entity)s, %(entity_id)s,
       %(antes)s, %(depois)s)
"""

_CLOSE_BAND_SQL = """
    update app.employee_compensation
       set effective_to = (%(effective_from)s::date - 1)
     where employee_id = %(employee_id)s
       and tenant_id = %(tenant_id)s
       and effective_to is null
"""

_NEW_BAND_SQL = """
    insert into app.employee_compensation
      (tenant_id, employee_id, effective_from, salary, reason, recorded_by)
    values
      (%(tenant_id)s, %(employee_id)s, %(effective_from)s, %(salary)s, %(reason)s, %(user_id)s)
    returning id
"""


@dataclass(frozen=True, slots=True)
class Permissions:
    """O que o banco responde sobre quem está pedindo."""

    admin: bool
    pii: bool
    compensation: bool
    health: bool

    def has_domain(self, domain: str | None) -> bool:
        if domain is None:
            return True
        return bool(getattr(self, domain, False))


def _dumps(valor: Any) -> str:
    # `default=str` porque `date` e `Decimal` não são JSON e são exatamente o que
    # esta auditoria carrega. Vira "2026-08-24" e "2500.00", que é como se lê.
    return json.dumps(valor, default=str, ensure_ascii=False)


def _jsonb(valor: Any) -> Jsonb:
    return Jsonb(valor, dumps=_dumps)


# ---------------------------------------------------------------------------
# Leitura — como o usuário
# ---------------------------------------------------------------------------
async def check_permissions(tenant: TenantContext) -> Permissions:
    """Papel e domínios, perguntados ao banco em vez de deduzidos aqui."""
    async with user_scope(tenant) as scope:
        await scope.execute(_PERMISSIONS_SQL, {"tenant_id": tenant.tenant_id})
        row = await scope.fetchone()
    return Permissions(
        admin=bool(row and row["admin"]),
        pii=bool(row and row["pii"]),
        compensation=bool(row and row["compensation"]),
        health=bool(row and row["health"]),
    )


async def fetch_current(tenant: TenantContext, template: Template) -> list[dict[str, Any]]:
    """O que está gravado hoje — o pré-preenchimento e a base da comparação.

    Uma leitura só serve às duas coisas de propósito: o valor que o template
    imprime e o valor contra o qual a linha de volta é comparada têm de ser o
    mesmo, ou "o campo não mudou" vira uma opinião.
    """
    async with user_scope(tenant) as scope:
        await scope.execute(select_sql(template))
        return [dict(row) for row in await scope.fetchall()]


async def last_closed_period_end(tenant: TenantContext) -> date | None:
    """O último dia de competência fechada, que é o piso da retroatividade."""
    async with tenant_scope(tenant) as scope:
        await scope.execute(_LAST_CLOSED_SQL)
        row = await scope.fetchone()
    return row["ends_on"] if row else None


# ---------------------------------------------------------------------------
# Escrita — como o backend, com a auditoria na mesma transação
# ---------------------------------------------------------------------------
async def create_import(
    tenant: TenantContext,
    *,
    import_id: UUID,
    template: Template,
    storage_path: str,
    file_name: str | None,
) -> None:
    async with tenant_scope(tenant) as scope:
        await scope.execute(
            _CREATE_IMPORT_SQL,
            {
                "import_id": import_id,
                "type": template.type,
                "storage_path": storage_path,
                "file_name": file_name,
                "layout_version": template.layout_version,
                "uploaded_by": tenant.user_id,
            },
        )


async def save_report(
    tenant: TenantContext,
    *,
    import_id: UUID,
    status: str,
    rows_total: int,
    rows_ok: int,
    rows_error: int,
    report: dict[str, Any],
) -> None:
    async with tenant_scope(tenant) as scope:
        await scope.execute(
            _SAVE_REPORT_SQL,
            {
                "import_id": import_id,
                "status": status,
                "rows_total": rows_total,
                "rows_ok": rows_ok,
                "rows_error": rows_error,
                "report": _jsonb(report),
            },
        )


async def load_import(tenant: TenantContext, import_id: UUID) -> dict[str, Any] | None:
    async with tenant_scope(tenant) as scope:
        await scope.execute(_LOAD_IMPORT_SQL, {"import_id": import_id})
        row = await scope.fetchone()
    return dict(row) if row else None


async def apply_lines(
    tenant: TenantContext,
    *,
    template: Template,
    outcomes: list[LineOutcome],
    import_id: UUID,
    status: str,
    rows_total: int,
    rows_ok: int,
    rows_error: int,
    report: dict[str, Any],
) -> int:
    """Grava as linhas aprovadas, audita cada uma e fecha o import — de uma vez.

    Uma transação só: o log que diz "esta linha veio deste arquivo" não pode
    existir sem a linha, nem a linha sem ele.
    """
    aplicadas = 0
    async with tenant_scope(tenant) as scope:
        for outcome in outcomes:
            if outcome.status != "ok" or outcome.employee_id is None:
                continue
            if template.strategy is Strategy.EMPLOYEE_UPDATE:
                await _apply_employee_update(scope, tenant, template, outcome, import_id)
            else:
                await _apply_new_band(scope, tenant, outcome, import_id)
            aplicadas += 1

        await scope.execute(
            _SAVE_REPORT_SQL,
            {
                "import_id": import_id,
                "status": status,
                "rows_total": rows_total,
                "rows_ok": rows_ok,
                "rows_error": rows_error,
                "report": _jsonb(report),
            },
        )
    return aplicadas


async def _apply_employee_update(
    scope: Any,
    tenant: TenantContext,
    template: Template,
    outcome: LineOutcome,
    import_id: UUID,
) -> None:
    por_tabela: dict[str, list[str]] = {}
    for column in template.columns:
        if column.column in outcome.values:
            por_tabela.setdefault(column.table, []).append(column.column)

    for tabela, colunas in por_tabela.items():
        valores = {coluna: outcome.values[coluna] for coluna in colunas}
        if tabela == "employee":
            sets = ", ".join(f"{coluna} = %({coluna})s" for coluna in colunas)
            await scope.execute(
                f"update app.employee set {sets}, updated_at = now() "
                f"where id = %(employee_id)s and tenant_id = %(tenant_id)s returning id",
                {**valores, "employee_id": outcome.employee_id},
            )
        else:
            campos = ", ".join(colunas)
            marcadores = ", ".join(f"%({coluna})s" for coluna in colunas)
            atualiza = ", ".join(f"{coluna} = excluded.{coluna}" for coluna in colunas)
            await scope.execute(
                f"insert into app.{tabela} (employee_id, tenant_id, {campos}, updated_at) "
                f"values (%(employee_id)s, %(tenant_id)s, {marcadores}, now()) "
                f"on conflict (employee_id) do update set {atualiza}, updated_at = now() "
                f"where {tabela}.tenant_id = %(tenant_id)s "
                f"returning employee_id",
                {**valores, "employee_id": outcome.employee_id},
            )
        await _audit(
            scope,
            tenant,
            action="update",
            entity=tabela,
            entity_id=outcome.employee_id,
            antes={coluna: outcome.previous.get(coluna) for coluna in colunas},
            depois=valores,
            import_id=import_id,
            line=outcome.line,
        )


async def _apply_new_band(
    scope: Any, tenant: TenantContext, outcome: LineOutcome, import_id: UUID
) -> None:
    valores = {
        "employee_id": outcome.employee_id,
        "effective_from": outcome.values.get("effective_from"),
        "salary": outcome.values.get("salary"),
        "reason": outcome.values.get("reason"),
        "user_id": tenant.user_id,
    }
    await scope.execute(_CLOSE_BAND_SQL, valores)
    await scope.execute(_NEW_BAND_SQL, valores)
    criada = await scope.fetchone()
    await _audit(
        scope,
        tenant,
        action="insert",
        entity="employee_compensation",
        entity_id=criada["id"] if criada else outcome.employee_id,
        antes=outcome.previous,
        depois={k: v for k, v in valores.items() if k != "user_id"},
        import_id=import_id,
        line=outcome.line,
    )


async def _audit(
    scope: Any,
    tenant: TenantContext,
    *,
    action: str,
    entity: str,
    entity_id: UUID,
    antes: dict[str, Any],
    depois: dict[str, Any],
    import_id: UUID,
    line: int,
) -> None:
    """A origem viaja em `_origem`, dentro de `depois`.

    `app.audit_log` não tem coluna de origem, e inventar uma seria mexer numa
    tabela que já cresce rápido. A chave começa com sublinhado para não colidir
    com nome de coluna do domínio, e responde a consulta direta:
    `depois->'_origem'->>'file_import_id'`.
    """
    await scope.execute(
        _AUDIT_SQL,
        {
            "user_id": tenant.user_id,
            "action": action,
            "entity": entity,
            "entity_id": str(entity_id),
            "antes": _jsonb(antes),
            "depois": _jsonb(
                {**depois, "_origem": {"file_import_id": str(import_id), "line": line}}
            ),
        },
    )


async def record_export(tenant: TenantContext, *, template: Template, rows: int) -> None:
    """O download de template é registrado — o arquivo leva o dado embora (SPEC §2)."""
    async with tenant_scope(tenant) as scope:
        await scope.execute(
            _AUDIT_SQL,
            {
                "user_id": tenant.user_id,
                "action": "export",
                "entity": "rh_template",
                "entity_id": template.type,
                "antes": _jsonb(None),
                "depois": _jsonb(
                    {
                        "layout_version": template.layout_version,
                        "domain": str(template.domain) if template.domain else None,
                        "rows": rows,
                    }
                ),
            },
        )


def to_current_map(rows: list[dict[str, Any]]) -> dict[UUID, dict[str, Any]]:
    return {row["employee_id"]: row for row in rows}


def index_by(rows: list[dict[str, Any]], column: str) -> dict[str, UUID]:
    """Chave textual -> pessoa. Vazio e nulo não são chave."""
    indice: dict[str, UUID] = {}
    for row in rows:
        valor = row.get(column)
        texto = "" if valor is None else str(valor).strip()
        if texto:
            indice[texto] = row["employee_id"]
    return indice
