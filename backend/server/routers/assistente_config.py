"""The assistant configuration — Caminho 2, and the pattern of `canais.py`.

Five tabs of the panel read here (SPEC-AGENTE §0.3, §1, §2, §4, §5): the two
layers of the prompt and the draft, the history with rollback, the
capabilities, the test, and the runs with what they cost. Reading is done **as
the user** (`user_scope`): the three policies of A1 and the one ruler of A2
(`fn_assistant_catalog`) already say what each person sees, and a non-admin
getting `draft = null` is the screen in read mode, not an error. Writing
follows `canais.py` to the letter: `util.is_admin` asked
to the database as the user (`_require_admin`, 403 before any transaction),
then the write **and** its `app.audit_log` line in one `service_role`
transaction (`tenant_scope`). The scope trigger of A1 and the RLS stay as the
net; this module precedes them, it does not replace them.

WHAT IS NOT HERE, ON PURPOSE
No platform role: the `platform` layer is read-only in every route, and the
only way a platform version changes is a migration (SPEC §1). No role
selector: the test runs as whoever called, always — "how would this look for
a supervisor" is answered by the capabilities tab listing what that role
reaches, never by executing as it (SPEC §5, and it is forbidden, not out of
scope). No new RPC for rollback: the version is checked (exists, is this
tenant's, is `layer = 'tenant'`) **before** anything is written, and the 404
is the contract; the pointer moves by one `update` under `tenant_scope`.

PUBLISHING CALLS THE RPC AS THE USER
`fn_publish_assistant_prompt` is `security definer` and checks `is_admin` by
`auth.uid()` itself, so it is called under `user_scope` and its six `P0001`
codes become HTTP here — always `{"detail": "<code>"}`, so the screen keys on
the code. The audit line comes after, under `tenant_scope`. `seen_updated_at`
is what the screen read: the RPC answers `draft_moved` when the draft changed
under it, and a body that does not send it keeps the behaviour of before.

READING THE RUNS IS THE POLICY, NOT THE ROUTE
`/execucoes`, `/custo` and `/custo-de-teste` have no `_require_admin`: the
three RPCs are `security invoker` and `ai_query_read` is own-or-admin, so a
common member seeing their own turns is the design. Adding a role check here
would be a second copy of that rule, drifting at the first change.

THE DRAFT FREEZES ITS ORIGIN ONLY ON INSERT
`PUT /rascunho` sets `frozen_from_version_id` to the tenant version on the air
when the draft is born, and **never** touches it on update: the only thing
that moves it is publishing (the RPC does). That is what keeps
`draft_ahead_of_air` honest after a rollback — the draft still says which
version it descended from, and the screen shows both (SPEC §2).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from psycopg import errors
from psycopg.types.json import Jsonb

from operax.core.tenant import TenantContext, tenant_scope, user_scope
from server.deps import CurrentTenant
from server.models import (
    AssistantCostByVersion,
    AssistantDraft,
    AssistantRun,
    AssistantTest,
    AssistantTestCost,
    CapabilityRow,
    CapabilityWrite,
    DraftWrite,
    PlatformLayer,
    PromptScreen,
    PublishRequest,
    PublishResult,
    TenantLayer,
    VersionRow,
    VersionsScreen,
)
from server.routers import assistente

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistente/configuracao", tags=["assistente"])

_SEM_PERMISSAO = "Sem permissão para configurar o assistente."
_SEM_PERMISSAO_RASCUNHO = "Sem permissão para editar o rascunho."
_SEM_PERMISSAO_RESTAURAR = "Sem permissão para restaurar uma versão."
_SEM_PERMISSAO_CAPACIDADE = "Sem permissão para ligar ou desligar uma métrica."
_SEM_PERMISSAO_TESTAR_RASCUNHO = "Sem permissão para testar o rascunho."
_SEM_RASCUNHO = "Não há rascunho para testar."
_VERSAO_NAO_ENCONTRADA = "Versão não encontrada."
_METRICA_NAO_ENCONTRADA = "Métrica não encontrada."
_SEM_CONFIGURACAO = "O assistente está sem configuração publicada."

#: The six refusals of `fn_publish_assistant_prompt`, each `P0001` with the
#: code as the message (migrations `assistant_publish_fn` and
#: `assistant_runs_fn`), and the status each one gets. `detail` is the code
#: itself: the screen keys on it. `draft_moved` is a 409 for the same reason
#: `draft_unchanged` is: the request is well formed and the state refuses it.
_PUBLISH_STATUS = {
    "not_admin": status.HTTP_403_FORBIDDEN,
    "draft_not_found": status.HTTP_404_NOT_FOUND,
    "draft_moved": status.HTTP_409_CONFLICT,
    "draft_empty": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "platform_layer_missing": status.HTTP_409_CONFLICT,
    "draft_unchanged": status.HTTP_409_CONFLICT,
}

# ---------------------------------------------------------------------------
# SQL — read as the user
# ---------------------------------------------------------------------------
_PERMISSION_SQL = """
    select util.is_admin(%(tenant_id)s) as admin
"""

#: The two versions on the air, with what the screen shows of each. The
#: policies of version and pointer already restrict to platform + own tenant;
#: the predicate is the same one, written so the query is the contract.
_ON_AIR_SQL = """
    select p.layer, v.id as version_id, v.version_number, v.content,
           v.provider, v.model, v.max_steps, v.created_at, v.created_by
    from app.assistant_prompt_pointer p
    join app.assistant_prompt_version v on v.id = p.version_id
    where (p.tenant_id is null and p.layer = 'platform')
       or (p.tenant_id = %(tenant_id)s and p.layer = 'tenant')
"""

#: The draft, as the user: `assistant_draft_admin` answers nothing to a
#: non-admin, and nothing is the right answer.
_DRAFT_SQL = """
    select content, frozen_from_version_id, updated_at, updated_by
    from app.assistant_draft
    where tenant_id = %(tenant_id)s
"""

_VERSIONS_SQL = """
    select v.layer, v.id as version_id, v.version_number, v.content,
           v.created_at, v.created_by,
           exists (
             select 1 from app.assistant_prompt_pointer p where p.version_id = v.id
           ) as on_air
    from app.assistant_prompt_version v
    where (v.tenant_id is null and v.layer = 'platform')
       or (v.tenant_id = %(tenant_id)s and v.layer = 'tenant')
    order by v.layer, v.version_number desc
"""

#: The version a rollback may point at: exists, is THIS tenant's, is a tenant
#: version. Read before anything is written — the 404 is the contract, the
#: scope trigger is the net.
_RESTORABLE_VERSION_SQL = """
    select v.id as version_id, v.version_number, v.content, v.created_at, v.created_by
    from app.assistant_prompt_version v
    where v.id = %(version_id)s
      and v.tenant_id = %(tenant_id)s
      and v.layer = 'tenant'
"""

_PUBLISH_SQL = """
    select version_id, version_number, previous_version_id
    from public.fn_publish_assistant_prompt(%(tenant_id)s, %(seen_updated_at)s)
"""

#: The real traffic of whoever calls, newest first. `security invoker`: the
#: policy of `app.ai_query` is the cut, and there is no role check around it.
_RUNS_SQL = """
    select created_at, question, metric_code, rows_returned, latency_ms,
           input_tokens, output_tokens, model, refused, refusal_reason,
           prompt_version_id, version_label
    from public.fn_assistant_runs(%(weeks)s)
"""

#: ⚠️ `model` is in the list because it is in the schema: the column entered
#: the key on 20/09 and this select did not follow it. The stub of the tests
#: answers by the subject of the statement, so a missing column is invisible
#: here and is a 500 against the real database — `AssistantCostByVersion.model`
#: is required. `test_o_select_de_cada_leitura_traz_todo_campo_do_schema`
#: reads both sides and is what catches the next one.
_COST_SQL = """
    select month_start, version_label, prompt_version_id, model, runs,
           refused_runs, input_tokens, output_tokens, avg_latency_ms
    from public.fn_assistant_cost_by_version(%(weeks)s)
"""

#: O gasto da aba Teste, por competência — só dry run, sem versão e sem
#: modelo. Total à parte, nunca coluna da tabela de custo.
_TEST_COST_SQL = """
    select month_start, runs, input_tokens, output_tokens
    from public.fn_assistant_test_cost(%(weeks)s)
"""

#: A janela das duas telas de Execuções, em semanas, a atual inclusa. O teto
#: de um ano é o da tela, não o da função: `p_weeks` maior devolveria o log
#: inteiro numa resposta só, e a aba pagina por período, não por linha.
WeeksWindow = Annotated[int, Query(ge=1, le=52, description="Semanas, a atual inclusa")]
_DEFAULT_WEEKS = 8

#: Every row, as the caller sees it: the tab shows the disabled and the
#: out-of-reach ones too. `target_view`, `dimensions`, `filters` stay inside.
_CATALOG_SQL = """
    select code, title, description, domain, enabled, visible_to_me
    from public.fn_assistant_catalog(%(tenant_id)s)
    order by code
"""

_CATALOG_ONE_SQL = """
    select code, title, description, domain, enabled, visible_to_me
    from public.fn_assistant_catalog(%(tenant_id)s)
    where code = %(code)s
"""

# ---------------------------------------------------------------------------
# SQL — written under service_role, tenant bound
# ---------------------------------------------------------------------------
#: On insert, the draft descends from the tenant version on the air (or from
#: nothing). On update the origin is NOT touched: only publishing moves it.
_DRAFT_UPSERT_SQL = """
    with before as (
        select content, frozen_from_version_id
        from app.assistant_draft
        where tenant_id = %(tenant_id)s
    )
    insert into app.assistant_draft as d (tenant_id, content, frozen_from_version_id, updated_by)
    values (
        %(tenant_id)s,
        %(content)s,
        (select p.version_id
           from app.assistant_prompt_pointer p
          where p.tenant_id = %(tenant_id)s and p.layer = 'tenant'),
        %(user_id)s
    )
    on conflict (tenant_id) do update
       set content = excluded.content,
           updated_by = excluded.updated_by
    returning d.content, d.frozen_from_version_id, d.updated_at, d.updated_by,
              (select to_jsonb(b) from before b) as before
"""

_POINTER_UPDATE_SQL = """
    with before as (
        select version_id
        from app.assistant_prompt_pointer
        where tenant_id = %(tenant_id)s and layer = 'tenant'
    )
    update app.assistant_prompt_pointer p
       set version_id = %(version_id)s,
           updated_at = now(),
           updated_by = %(user_id)s
     where p.tenant_id = %(tenant_id)s
       and p.layer = 'tenant'
    returning p.version_id, (select version_id from before) as previous_version_id
"""

_SCOPE_UPSERT_SQL = """
    with before as (
        select enabled
        from app.assistant_metric_scope
        where tenant_id = %(tenant_id)s and metric_code = %(code)s
    )
    insert into app.assistant_metric_scope as s (tenant_id, metric_code, enabled, updated_by)
    values (%(tenant_id)s, %(code)s, %(enabled)s, %(user_id)s)
    on conflict (tenant_id, metric_code) do update
       set enabled = excluded.enabled,
           updated_by = excluded.updated_by
    returning s.enabled, (select enabled from before) as before_enabled
"""

_AUDIT_SQL = """
    insert into app.audit_log
      (tenant_id, user_id, action, entity, entity_id, antes, depois)
    values
      (%(tenant_id)s, %(user_id)s, %(action)s, %(entity)s, %(entity_id)s, %(antes)s, %(depois)s)
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _require_admin(tenant: TenantContext, detail: str = _SEM_PERMISSAO) -> None:
    """`util.is_admin` asked to the database as the user — the same helper the
    draft and scope policies use, and the same eight lines as `canais.py`.
    403 before any transaction of `service_role`."""
    async with user_scope(tenant) as scope:
        await scope.execute(_PERMISSION_SQL, {"tenant_id": tenant.tenant_id})
        row = await scope.fetchone()
        if not (row and row["admin"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _audit_params(
    tenant: TenantContext,
    *,
    action: str,
    entity: str,
    entity_id: str,
    antes: Mapping[str, Any] | None,
    depois: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "user_id": tenant.user_id,
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "antes": Jsonb(dict(antes)) if antes is not None else None,
        "depois": Jsonb(dict(depois)),
    }


def _tenant_layer(row: Mapping[str, Any]) -> TenantLayer:
    return TenantLayer(
        version_id=row["version_id"],
        version_number=row["version_number"],
        content=row["content"],
        created_at=row["created_at"],
        created_by=row["created_by"],
    )


def _draft(row: Mapping[str, Any]) -> AssistantDraft:
    return AssistantDraft(
        content=row["content"],
        frozen_from_version_id=row["frozen_from_version_id"],
        updated_at=row["updated_at"],
        updated_by=row["updated_by"],
    )


def _capability(row: Mapping[str, Any]) -> CapabilityRow:
    return CapabilityRow(
        code=row["code"],
        title=row["title"],
        description=row["description"],
        domain=row["domain"],
        enabled=row["enabled"],
        visible_to_me=row["visible_to_me"],
    )


async def _read_draft(tenant: TenantContext) -> dict[str, Any] | None:
    async with user_scope(tenant) as scope:
        await scope.execute(_DRAFT_SQL, {"tenant_id": tenant.tenant_id})
        row = await scope.fetchone()
    return dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
@router.get("/prompt")
async def prompt_screen(tenant: CurrentTenant) -> PromptScreen:
    """The two layers on the air and the draft, as the user. 503 with no
    platform pointer: the tab has nothing to show and the turn has nothing to
    run — in production that is the order migrations → push."""
    async with user_scope(tenant) as scope:
        await scope.execute(_ON_AIR_SQL, {"tenant_id": tenant.tenant_id})
        on_air = {row["layer"]: row for row in await scope.fetchall()}
        await scope.execute(_DRAFT_SQL, {"tenant_id": tenant.tenant_id})
        draft_row = await scope.fetchone()

    platform = on_air.get("platform")
    if platform is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_SEM_CONFIGURACAO
        )
    tenant_row = on_air.get("tenant")
    tenant_layer = _tenant_layer(tenant_row) if tenant_row is not None else None
    draft = _draft(draft_row) if draft_row is not None else None
    return PromptScreen(
        platform=PlatformLayer(
            version_id=platform["version_id"],
            version_number=platform["version_number"],
            content=platform["content"],
            provider=platform["provider"],
            model=platform["model"],
            max_steps=platform["max_steps"],
            created_at=platform["created_at"],
        ),
        tenant=tenant_layer,
        draft=draft,
        draft_ahead_of_air=(
            draft is not None
            and draft.frozen_from_version_id
            != (tenant_layer.version_id if tenant_layer is not None else None)
        ),
    )


@router.put("/rascunho")
async def save_draft(tenant: CurrentTenant, request: DraftWrite) -> AssistantDraft:
    """Creates or edits the draft; returns what was written.

    (1) `util.is_admin` as the user; (2) one transaction: the upsert — the
    origin frozen on insert only — and the audit line with the row before and
    the row after.
    """
    await _require_admin(tenant, _SEM_PERMISSAO_RASCUNHO)

    async with tenant_scope(tenant) as bound:
        await bound.execute(
            _DRAFT_UPSERT_SQL,
            {"content": request.content, "user_id": tenant.user_id},
        )
        row = await bound.fetchone()
        if row is None:
            raise RuntimeError("o upsert de app.assistant_draft não devolveu a linha gravada")
        saved = _draft(row)
        before = row["before"]
        await bound.execute(
            _AUDIT_SQL,
            _audit_params(
                tenant,
                action="insert" if before is None else "update",
                entity="assistant_draft",
                entity_id=str(tenant.tenant_id),
                antes=before,
                depois={
                    "content": saved.content,
                    "frozen_from_version_id": (
                        str(saved.frozen_from_version_id)
                        if saved.frozen_from_version_id is not None
                        else None
                    ),
                },
            ),
        )
    return saved


@router.post("/publicar")
async def publish(tenant: CurrentTenant, payload: PublishRequest | None = None) -> PublishResult:
    """Freeze the draft into a version and move the pointer — the RPC, called
    as the user (definer; it checks `is_admin` itself). The six `P0001` codes
    become HTTP with `detail` = the code. Audit after, under `tenant_scope`.

    The body is optional, and so is `seen_updated_at` inside it: without it
    the RPC publishes whatever is in the draft, which is what every caller
    written before this parameter does. With it, a draft that moved between
    the read and the click is `draft_moved` (409) instead of one admin
    publishing the other's text.
    """
    seen = payload.seen_updated_at if payload is not None else None
    try:
        async with user_scope(tenant) as scope:
            await scope.execute(
                _PUBLISH_SQL, {"tenant_id": tenant.tenant_id, "seen_updated_at": seen}
            )
            row = await scope.fetchone()
    except errors.RaiseException as recusa:
        code = recusa.diag.message_primary or ""
        if code not in _PUBLISH_STATUS:
            raise
        raise HTTPException(status_code=_PUBLISH_STATUS[code], detail=code) from None
    if row is None:
        raise RuntimeError("fn_publish_assistant_prompt não devolveu a versão publicada")
    result = PublishResult(
        version_id=row["version_id"],
        version_number=row["version_number"],
        previous_version_id=row["previous_version_id"],
    )

    async with tenant_scope(tenant) as bound:
        await bound.execute(
            _AUDIT_SQL,
            _audit_params(
                tenant,
                action="insert",
                entity="assistant_prompt_version",
                entity_id=str(result.version_id),
                antes=(
                    {"pointer_version_id": str(result.previous_version_id)}
                    if result.previous_version_id is not None
                    else None
                ),
                depois={
                    "version_id": str(result.version_id),
                    "version_number": result.version_number,
                },
            ),
        )
    return result


# ---------------------------------------------------------------------------
# Histórico
# ---------------------------------------------------------------------------
@router.get("/versoes")
async def versions(tenant: CurrentTenant) -> VersionsScreen:
    """Every version of the tenant and of the platform, newest first, each
    saying whether it is on the air. Any member: the policy is the cut."""
    async with user_scope(tenant) as scope:
        await scope.execute(_VERSIONS_SQL, {"tenant_id": tenant.tenant_id})
        rows = await scope.fetchall()
    por_camada: dict[str, list[VersionRow]] = {"tenant": [], "platform": []}
    for row in rows:
        por_camada[row["layer"]].append(
            VersionRow(
                version_id=row["version_id"],
                version_number=row["version_number"],
                content=row["content"],
                created_at=row["created_at"],
                created_by=row["created_by"],
                on_air=row["on_air"],
            )
        )
    return VersionsScreen(tenant=por_camada["tenant"], platform=por_camada["platform"])


@router.post("/versoes/{version_id}/restaurar")
async def restore(tenant: CurrentTenant, version_id: UUID) -> TenantLayer:
    """Rollback: move the tenant pointer to `version_id`. Not a new RPC.

    (1) `util.is_admin` as the user; (2) the version exists, is this tenant's
    and is `layer = 'tenant'` — read as the user, 404 otherwise, **before**
    any write; (3) one transaction: the pointer update and the audit line.
    The scope trigger of A1 would refuse a foreign version anyway; the 404 is
    the contract, the trigger is the net.
    """
    await _require_admin(tenant, _SEM_PERMISSAO_RESTAURAR)

    async with user_scope(tenant) as scope:
        await scope.execute(
            _RESTORABLE_VERSION_SQL,
            {"tenant_id": tenant.tenant_id, "version_id": version_id},
        )
        version = await scope.fetchone()
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_VERSAO_NAO_ENCONTRADA)

    async with tenant_scope(tenant) as bound:
        await bound.execute(
            _POINTER_UPDATE_SQL, {"version_id": version_id, "user_id": tenant.user_id}
        )
        moved = await bound.fetchone()
        if moved is None:
            raise RuntimeError("o tenant tem versão publicada mas nenhum ponteiro para mover")
        await bound.execute(
            _AUDIT_SQL,
            _audit_params(
                tenant,
                action="update",
                entity="assistant_prompt_pointer",
                entity_id=str(tenant.tenant_id),
                antes={"version_id": str(moved["previous_version_id"])},
                depois={"version_id": str(moved["version_id"])},
            ),
        )
    return _tenant_layer(version)


# ---------------------------------------------------------------------------
# Capacidades
# ---------------------------------------------------------------------------
@router.get("/capacidades")
async def capabilities(tenant: CurrentTenant) -> list[CapabilityRow]:
    """The single ruler, as the caller: every active metric, with `enabled`
    (the tenant's switch) and `visible_to_me` (the switch AND the domain)."""
    async with user_scope(tenant) as scope:
        await scope.execute(_CATALOG_SQL, {"tenant_id": tenant.tenant_id})
        rows = await scope.fetchall()
    return [_capability(row) for row in rows]


@router.put("/capacidades/{code}")
async def save_capability(
    tenant: CurrentTenant, code: str, request: CapabilityWrite
) -> CapabilityRow:
    """Switch a metric on or off for the tenant. Never deletes the row.

    (1) `util.is_admin` as the user; (2) the metric exists and is active —
    asked to the same ruler the tab reads, 404 otherwise; (3) one transaction:
    the upsert and the audit line; (4) the row re-read through the ruler, so
    what comes back is what the tab will show.
    """
    await _require_admin(tenant, _SEM_PERMISSAO_CAPACIDADE)

    async with user_scope(tenant) as scope:
        await scope.execute(_CATALOG_ONE_SQL, {"tenant_id": tenant.tenant_id, "code": code})
        existing = await scope.fetchone()
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_METRICA_NAO_ENCONTRADA)

    async with tenant_scope(tenant) as bound:
        await bound.execute(
            _SCOPE_UPSERT_SQL,
            {"code": code, "enabled": request.enabled, "user_id": tenant.user_id},
        )
        row = await bound.fetchone()
        if row is None:
            raise RuntimeError("o upsert de app.assistant_metric_scope não devolveu a linha")
        before_enabled = row["before_enabled"]
        await bound.execute(
            _AUDIT_SQL,
            _audit_params(
                tenant,
                action="insert" if before_enabled is None else "update",
                entity="assistant_metric_scope",
                entity_id=code,
                antes={"enabled": before_enabled} if before_enabled is not None else None,
                depois={"enabled": row["enabled"]},
            ),
        )

    async with user_scope(tenant) as scope:
        await scope.execute(_CATALOG_ONE_SQL, {"tenant_id": tenant.tenant_id, "code": code})
        saved = await scope.fetchone()
    if saved is None:
        raise RuntimeError(f"a métrica {code!r} sumiu do catálogo entre a gravação e a releitura")
    return _capability(saved)


# ---------------------------------------------------------------------------
# Teste
# ---------------------------------------------------------------------------
@router.post("/testar")
async def test_prompt(payload: AssistantTest, tenant: CurrentTenant) -> StreamingResponse:
    """The same turn as `/assistente/perguntar`, recorded as a dry run.

    `use_draft` runs the draft in place of the tenant layer: admin only (403
    — the RLS would answer "no draft" to a non-admin, and the backend says
    "no permission" instead), 404 when the admin has no draft. Always as
    whoever called: there is no role selector, and there will not be one.
    """
    override: str | None = None
    if payload.use_draft:
        await _require_admin(tenant, _SEM_PERMISSAO_TESTAR_RASCUNHO)
        draft = await _read_draft(tenant)
        if draft is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_SEM_RASCUNHO)
        override = draft["content"]
    return await assistente.answer(
        tenant, payload.question, payload.model, dry_run=True, tenant_override=override
    )


# ---------------------------------------------------------------------------
# Execuções
# ---------------------------------------------------------------------------
@router.get("/execucoes")
async def runs(tenant: CurrentTenant, weeks: WeeksWindow = _DEFAULT_WEEKS) -> list[AssistantRun]:
    """The real traffic of the window, newest first — never a dry run.

    No `_require_admin`: `fn_assistant_runs` is `security invoker` and
    `ai_query_read` is own-or-admin, so an admin reads the tenant's turns and
    a common member reads their own. That is the cut, and it is the policy's.
    """
    async with user_scope(tenant) as scope:
        await scope.execute(_RUNS_SQL, {"weeks": weeks})
        rows = await scope.fetchall()
    return [AssistantRun.model_validate(dict(row)) for row in rows]


@router.get("/custo")
async def cost(
    tenant: CurrentTenant, weeks: WeeksWindow = _DEFAULT_WEEKS
) -> list[AssistantCostByVersion]:
    """Cost per competência broken down by prompt version, newest month first.

    The same window and the same invoker cut as `/execucoes`. Dry run is out
    of every average: a test is not traffic, and it would move the only
    number this stage produces (SPEC-AGENTE §0.3).
    """
    async with user_scope(tenant) as scope:
        await scope.execute(_COST_SQL, {"weeks": weeks})
        rows = await scope.fetchall()
    return [AssistantCostByVersion.model_validate(dict(row)) for row in rows]


@router.get("/custo-de-teste")
async def test_cost(
    tenant: CurrentTenant, weeks: WeeksWindow = _DEFAULT_WEEKS
) -> list[AssistantTestCost]:
    """O gasto da aba Teste na mesma janela — o que `/custo` deixa de fora.

    `not is_dry_run` lá está certo, e por isso esta rota existe: o dry run é
    dinheiro real, e num mês de ajuste de prompt é a maior parte da conta.
    Uma linha por competência, **sem** versão e **sem** modelo: é um total à
    parte (decisão do dono, 20/09/2026), e o formato é o que impede que
    alguém o some com o tráfego sem perceber.

    O mesmo recorte de invoker das irmãs, e por isso sem `_require_admin`.
    """
    async with user_scope(tenant) as scope:
        await scope.execute(_TEST_COST_SQL, {"weeks": weeks})
        rows = await scope.fetchall()
    return [AssistantTestCost.model_validate(dict(row)) for row in rows]
