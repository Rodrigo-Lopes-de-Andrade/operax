"""`/assistente/configuracao` — the ten routes, and the order that is the contract.

What these tests pin is not the SQL running (that is `scripts/97_teste_assistente.sql`
§A3 on the real schema): it is what the route does **around** the SQL. Who is
refused before any transaction of `service_role` opens; that the rollback reads
the version before it writes anything, and that a foreign, platform or
non-existent version is a 404 with the pointer untouched; that the draft freezes
its origin on insert and never on update; that the five codes of the publish
RPC become the five statuses with `detail` = code; that the test tab records a
dry run with the hash of the draft it ran, and points at the platform version;
and that the platform layer is read-only in every route and no route takes a
role.

The database is a stub that answers by the subject of the statement, like
`test_canais_*`. For the rollback it emulates the predicate of the version
query on a small table, so "another tenant's version" and "a platform version"
are different rows and not the same `None`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from psycopg.types.json import Jsonb

from operax.agente import agente
from operax.agente.agente import Record
from operax.agente.prompt import PromptLayers
from operax.core.tenant import TenantContext
from server.routers import assistente, assistente_config
from tests.conftest import TENANT_ID, USER_ID
from tests.fixtures.fake_llm import FakeChatModel
from tests.test_assistente import banco  # noqa: F401 — the executor stubs, for the real Turn
from tests.test_canais_credencial import StubScope, StubScopeContext
from tests.test_canais_templates import _TriggerRefusal

OTHER_TENANT = UUID("99999999-9999-4999-8999-999999999999")
PLATFORM_V1 = UUID("44444444-4444-4444-8444-444444444441")
TENANT_V1 = UUID("44444444-4444-4444-8444-444444444442")
TENANT_V2 = UUID("44444444-4444-4444-8444-444444444443")
OTHER_V1 = UUID("44444444-4444-4444-8444-444444444499")
WHEN = "2026-09-17T12:00:00+00:00"
#: The same instant as Pydantic writes it.
WHEN_JSON = "2026-09-17T12:00:00Z"

PLATFORM_ROW = {
    "layer": "platform",
    "version_id": PLATFORM_V1,
    "version_number": 1,
    "content": "Doutrina {{hoje}} {{catalogo}} {{unidades}}",
    "provider": "anthropic",
    "model": "claude-haiku-4-5-20251001",
    "max_steps": None,
    "created_at": WHEN,
    "created_by": None,
}
TENANT_ROW = {
    "layer": "tenant",
    "version_id": TENANT_V2,
    "version_number": 2,
    "content": "Vocabulário v2",
    "provider": None,
    "model": None,
    "max_steps": None,
    "created_at": WHEN,
    "created_by": USER_ID,
}

#: The versions the rollback query may see, with the predicate emulated.
VERSIONS_TABLE = [
    {"id": TENANT_V1, "tenant_id": TENANT_ID, "layer": "tenant", "version_number": 1},
    {"id": TENANT_V2, "tenant_id": TENANT_ID, "layer": "tenant", "version_number": 2},
    {"id": OTHER_V1, "tenant_id": OTHER_TENANT, "layer": "tenant", "version_number": 1},
    {"id": PLATFORM_V1, "tenant_id": None, "layer": "platform", "version_number": 1},
]

CATALOG = [
    {
        "code": "deviations_total",
        "title": "Total de desvios",
        "description": "Contagem",
        "domain": None,
        "enabled": True,
        "visible_to_me": True,
    },
    {
        "code": "payroll_summary",
        "title": "Folha",
        "description": "Valor total",
        "domain": "compensation",
        "enabled": True,
        "visible_to_me": False,
    },
]


def draft_row(**overrides: Any) -> dict[str, Any]:
    return {
        "content": "Rascunho do cliente.",
        "frozen_from_version_id": TENANT_V2,
        "updated_at": WHEN,
        "updated_by": USER_ID,
    } | overrides


def _restorable(statement: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """`_RESTORABLE_VERSION_SQL` applied to `VERSIONS_TABLE` — the predicate AS
    WRITTEN in the statement, so a condition dropped from the SQL is dropped
    here too and the 404 tests see the row the real query would return."""
    for row in VERSIONS_TABLE:
        if row["id"] != params["version_id"]:
            continue
        if "v.tenant_id = %(tenant_id)s" in statement and row["tenant_id"] != params["tenant_id"]:
            if not ("v.tenant_id is null" in statement and row["tenant_id"] is None):
                continue
        if "v.layer = 'tenant'" in statement and row["layer"] != "tenant":
            continue
        return {
            "version_id": row["id"],
            "version_number": row["version_number"],
            "content": f"v{row['version_number']}",
            "created_at": WHEN,
            "created_by": USER_ID,
        }
    return None


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch):
    """Installs the two scopes of the router and returns `(user, bound, bound_ctx)`."""

    def install(
        *,
        admin: bool = True,
        on_air: list[dict[str, Any]] | None = None,
        draft: dict[str, Any] | None = None,
        versions: list[dict[str, Any]] | None = None,
        publish: Any = None,
        catalog: list[dict[str, Any]] | None = None,
        catalog_one: dict[str, Any] | None = None,
        runs: list[dict[str, Any]] | None = None,
        cost: list[dict[str, Any]] | None = None,
        draft_saved: dict[str, Any] | None = None,
        pointer_moved: dict[str, Any] | None = None,
        scope_saved: dict[str, Any] | None = None,
    ) -> tuple[StubScope, StubScope, StubScopeContext]:
        user = StubScope(
            {
                "util.is_admin": {"admin": admin},
                "join app.assistant_prompt_version v on v.id = p.version_id": (
                    on_air if on_air is not None else [PLATFORM_ROW, TENANT_ROW]
                ),
                "from app.assistant_draft": draft,
                ") as on_air": versions or [],
                "fn_publish_assistant_prompt": publish,
                "fn_assistant_runs": runs if runs is not None else [],
                "fn_assistant_cost_by_version": cost if cost is not None else [],
                "where code = %(code)s": catalog_one,
                "order by code": catalog if catalog is not None else CATALOG,
            }
        )
        original = user.execute

        async def execute(statement: str, params: Any = None) -> None:
            await original(statement, params)
            if "where v.id = %(version_id)s" in statement:
                user._current = _restorable(statement, params)

        user.execute = execute  # type: ignore[method-assign]

        bound = StubScope(
            {
                "insert into app.assistant_draft": draft_saved,
                "update app.assistant_prompt_pointer": pointer_moved,
                "insert into app.assistant_metric_scope": scope_saved,
                "insert into app.audit_log": None,
            }
        )
        bound_ctx = StubScopeContext(bound)
        monkeypatch.setattr(assistente_config, "user_scope", lambda _t: StubScopeContext(user))
        monkeypatch.setattr(assistente_config, "tenant_scope", lambda _t: bound_ctx)
        return user, bound, bound_ctx

    return install


@pytest.fixture
def cabecalho(issue_token: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token()}"}


def _audits(bound: StubScope) -> list[dict[str, Any]]:
    return [
        params
        for statement, params in zip(bound.statements, bound.params, strict=True)
        if "insert into app.audit_log" in statement
    ]


def _writes(bound: StubScope) -> list[str]:
    return [s for s in bound.statements if "insert into app.audit_log" not in s]


# ---------------------------------------------------------------------------
# GET /prompt
# ---------------------------------------------------------------------------
def test_a_tela_traz_as_duas_camadas_e_o_rascunho_como_o_usuario(
    client: TestClient, cabecalho: dict[str, str], db
):
    user, _, bound_ctx = db(draft=draft_row())

    resposta = client.get("/assistente/configuracao/prompt", headers=cabecalho)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["platform"] == {
        "version_id": str(PLATFORM_V1),
        "version_number": 1,
        "content": PLATFORM_ROW["content"],
        "provider": "anthropic",
        "model": "claude-haiku-4-5-20251001",
        "max_steps": None,
        "created_at": WHEN_JSON,
    }
    assert corpo["tenant"] == {
        "version_id": str(TENANT_V2),
        "version_number": 2,
        "content": "Vocabulário v2",
        "created_at": WHEN_JSON,
        "created_by": str(USER_ID),
    }
    assert corpo["draft"]["content"] == "Rascunho do cliente."
    assert corpo["draft"]["frozen_from_version_id"] == str(TENANT_V2)
    assert corpo["max_length"] == 12000
    assert corpo["draft_ahead_of_air"] is False
    # Everything as the user; the service_role transaction never opened.
    assert bound_ctx.opened == 0
    assert all(p == {"tenant_id": TENANT_ID} for p in user.params)
    # And the tenant is in the SQL text, not only in the params: without the
    # predicate the RLS still narrows, but the query stops being the contract.
    on_air, draft = user.statements[0], user.statements[1]
    assert "p.tenant_id = %(tenant_id)s and p.layer = 'tenant'" in on_air
    assert "where tenant_id = %(tenant_id)s" in draft


def test_draft_ahead_of_air_e_verdadeiro_quando_o_rascunho_partiu_de_outra_versao(
    client: TestClient, cabecalho: dict[str, str], db
):
    """The rollback case of SPEC §2: pointer on v2, draft descended from a v3
    that is no longer on the air. The screen has to show both."""
    db(draft=draft_row(frozen_from_version_id=uuid4()))

    corpo = client.get("/assistente/configuracao/prompt", headers=cabecalho).json()

    assert corpo["draft_ahead_of_air"] is True


def test_quem_nao_e_admin_recebe_o_rascunho_nulo_e_nao_um_erro(
    client: TestClient, cabecalho: dict[str, str], db
):
    db(admin=False, draft=None)

    resposta = client.get("/assistente/configuracao/prompt", headers=cabecalho)

    assert resposta.status_code == 200
    assert resposta.json()["draft"] is None
    assert resposta.json()["draft_ahead_of_air"] is False


def test_sem_versao_de_tenant_a_camada_e_nula_e_o_rascunho_sem_origem_nao_esta_a_frente(
    client: TestClient, cabecalho: dict[str, str], db
):
    db(on_air=[PLATFORM_ROW], draft=draft_row(frozen_from_version_id=None))

    corpo = client.get("/assistente/configuracao/prompt", headers=cabecalho).json()

    assert corpo["tenant"] is None
    assert corpo["draft_ahead_of_air"] is False


def test_sem_ponteiro_de_plataforma_a_tela_responde_503(
    client: TestClient, cabecalho: dict[str, str], db
):
    db(on_air=[])

    resposta = client.get("/assistente/configuracao/prompt", headers=cabecalho)

    assert resposta.status_code == 503
    assert resposta.json()["detail"] == "O assistente está sem configuração publicada."


# ---------------------------------------------------------------------------
# PUT /rascunho
# ---------------------------------------------------------------------------
def test_quem_nao_e_admin_nao_grava_o_rascunho(client: TestClient, cabecalho: dict[str, str], db):
    _, _, bound_ctx = db(admin=False)

    resposta = client.put(
        "/assistente/configuracao/rascunho", json={"content": "x"}, headers=cabecalho
    )

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Sem permissão para editar o rascunho."
    assert bound_ctx.opened == 0


def test_o_rascunho_nasce_com_a_origem_na_versao_apontada(
    client: TestClient, cabecalho: dict[str, str], db
):
    salvo = draft_row(content="Novo.", frozen_from_version_id=TENANT_V2) | {"before": None}
    _, bound, _ = db(draft_saved=salvo)

    resposta = client.put(
        "/assistente/configuracao/rascunho", json={"content": "Novo."}, headers=cabecalho
    )

    assert resposta.status_code == 200
    assert resposta.json()["frozen_from_version_id"] == str(TENANT_V2)
    [upsert] = _writes(bound)
    # The origin comes from the pointer on the air, in the INSERT values...
    insert_values = upsert[upsert.index("values (") : upsert.index("on conflict")]
    assert "app.assistant_prompt_pointer" in insert_values
    assert "p.layer = 'tenant'" in insert_values
    # ...and the UPDATE branch does not touch it: only publishing moves it.
    update_branch = upsert[upsert.index("do update") : upsert.index("returning")]
    assert "frozen_from_version_id" not in update_branch
    assert "content = excluded.content" in update_branch
    [audit] = _audits(bound)
    assert audit["action"] == "insert"
    assert audit["entity"] == "assistant_draft"
    assert audit["antes"] is None
    assert audit["depois"].obj["content"] == "Novo."


def test_editar_o_rascunho_audita_o_antes_e_o_depois(
    client: TestClient, cabecalho: dict[str, str], db
):
    antes = {"content": "Velho.", "frozen_from_version_id": str(TENANT_V1)}
    salvo = draft_row(content="Novo.", frozen_from_version_id=TENANT_V1) | {"before": antes}
    _, bound, _ = db(draft_saved=salvo)

    resposta = client.put(
        "/assistente/configuracao/rascunho", json={"content": "Novo."}, headers=cabecalho
    )

    assert resposta.status_code == 200
    [audit] = _audits(bound)
    assert audit["action"] == "update"
    assert audit["antes"].obj == antes
    assert isinstance(audit["depois"], Jsonb)
    assert bound.params[0]["user_id"] == USER_ID


@pytest.mark.parametrize("content", ["", "x" * 12001])
def test_o_limite_do_rascunho_e_o_do_banco(
    client: TestClient, cabecalho: dict[str, str], db, content: str
):
    _, _, bound_ctx = db()

    resposta = client.put(
        "/assistente/configuracao/rascunho", json={"content": content}, headers=cabecalho
    )

    assert resposta.status_code == 422
    assert bound_ctx.opened == 0


# ---------------------------------------------------------------------------
# POST /publicar
# ---------------------------------------------------------------------------
def test_publicar_chama_a_rpc_como_o_usuario_e_audita_depois(
    client: TestClient, cabecalho: dict[str, str], db
):
    novo = uuid4()
    user, bound, _ = db(
        publish={"version_id": novo, "version_number": 3, "previous_version_id": TENANT_V2}
    )

    resposta = client.post("/assistente/configuracao/publicar", headers=cabecalho)

    assert resposta.status_code == 200
    assert resposta.json() == {
        "version_id": str(novo),
        "version_number": 3,
        "previous_version_id": str(TENANT_V2),
    }
    [rpc] = user.statements
    assert "public.fn_publish_assistant_prompt(%(tenant_id)s, %(seen_updated_at)s)" in rpc
    assert user.params[0] == {"tenant_id": TENANT_ID, "seen_updated_at": None}
    # No is_admin here: the definer checks it by auth.uid() itself.
    assert "util.is_admin" not in rpc
    [audit] = _audits(bound)
    assert audit["entity"] == "assistant_prompt_version"
    assert audit["entity_id"] == str(novo)
    assert audit["antes"].obj == {"pointer_version_id": str(TENANT_V2)}
    assert audit["depois"].obj == {"version_id": str(novo), "version_number": 3}
    assert _writes(bound) == []


@pytest.mark.parametrize(
    ("code", "status_code"),
    [
        ("not_admin", 403),
        ("draft_not_found", 404),
        ("draft_moved", 409),
        ("draft_empty", 422),
        ("platform_layer_missing", 409),
        ("draft_unchanged", 409),
    ],
)
def test_as_seis_recusas_da_rpc_viram_http_com_o_codigo_no_detail(
    client: TestClient, cabecalho: dict[str, str], db, code: str, status_code: int
):
    _, _, bound_ctx = db(publish=_TriggerRefusal(code))

    resposta = client.post("/assistente/configuracao/publicar", headers=cabecalho)

    assert resposta.status_code == status_code
    assert resposta.json() == {"detail": code}
    assert bound_ctx.opened == 0


def test_publicar_sem_corpo_manda_seen_updated_at_nulo(
    client: TestClient, cabecalho: dict[str, str], db
):
    """O chamador de hoje não manda corpo — e o nulo é o comportamento de
    antes deste parâmetro, não um erro."""
    novo = uuid4()
    user, _, _ = db(publish={"version_id": novo, "version_number": 3, "previous_version_id": None})

    resposta = client.post("/assistente/configuracao/publicar", headers=cabecalho)

    assert resposta.status_code == 200
    assert user.params[0] == {"tenant_id": TENANT_ID, "seen_updated_at": None}


def test_publicar_leva_o_que_a_tela_viu_ate_a_rpc(
    client: TestClient, cabecalho: dict[str, str], db
):
    """`seen_updated_at` chega à RPC como veio: é lá que ele vira `draft_moved`."""
    novo = uuid4()
    user, _, _ = db(publish={"version_id": novo, "version_number": 3, "previous_version_id": None})

    resposta = client.post(
        "/assistente/configuracao/publicar",
        json={"seen_updated_at": WHEN},
        headers=cabecalho,
    )

    assert resposta.status_code == 200
    assert user.params[0]["seen_updated_at"] == datetime.fromisoformat(WHEN)
    assert "%(seen_updated_at)s" in user.statements[0]


def test_o_rascunho_que_mudou_debaixo_da_tela_e_409_draft_moved(
    client: TestClient, cabecalho: dict[str, str], db
):
    """Dois admins no mesmo minuto: quem chegou depois publicaria o texto do
    outro, que nunca viu. A recusa vem do banco e o `detail` é o código."""
    _, _, bound_ctx = db(publish=_TriggerRefusal("draft_moved"))

    resposta = client.post(
        "/assistente/configuracao/publicar",
        json={"seen_updated_at": WHEN},
        headers=cabecalho,
    )

    assert resposta.status_code == 409
    assert resposta.json() == {"detail": "draft_moved"}
    assert bound_ctx.opened == 0


def test_publicar_nao_aceita_campo_desconhecido(client: TestClient, cabecalho: dict[str, str], db):
    db()

    resposta = client.post(
        "/assistente/configuracao/publicar",
        json={"seen_updated_at": WHEN, "content": "texto"},
        headers=cabecalho,
    )

    assert resposta.status_code == 422


def test_um_p0001_que_nao_e_dos_seis_nao_e_engolido(
    client: TestClient, cabecalho: dict[str, str], db
):
    db(publish=_TriggerRefusal("algo_novo"))

    with pytest.raises(_TriggerRefusal):
        client.post("/assistente/configuracao/publicar", headers=cabecalho)


# ---------------------------------------------------------------------------
# GET /versoes
# ---------------------------------------------------------------------------
def test_o_historico_separa_tenant_e_plataforma_e_diz_qual_esta_no_ar(
    client: TestClient, cabecalho: dict[str, str], db
):
    def linha(layer: str, vid: UUID, n: int, on_air: bool) -> dict[str, Any]:
        return {
            "layer": layer,
            "version_id": vid,
            "version_number": n,
            "content": f"{layer} v{n}",
            "created_at": WHEN,
            "created_by": None if layer == "platform" else USER_ID,
            "on_air": on_air,
        }

    user, _, bound_ctx = db(
        versions=[
            linha("platform", PLATFORM_V1, 1, True),
            linha("tenant", TENANT_V2, 2, True),
            linha("tenant", TENANT_V1, 1, False),
        ]
    )

    resposta = client.get("/assistente/configuracao/versoes", headers=cabecalho)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [v["version_number"] for v in corpo["tenant"]] == [2, 1]
    assert [v["on_air"] for v in corpo["tenant"]] == [True, False]
    assert corpo["platform"] == [
        {
            "version_id": str(PLATFORM_V1),
            "version_number": 1,
            "content": "platform v1",
            "created_at": WHEN_JSON,
            "created_by": None,
            "on_air": True,
        }
    ]
    assert bound_ctx.opened == 0
    # The tenant predicate in the SQL text, not only in the params.
    [versions] = user.statements
    assert "v.tenant_id = %(tenant_id)s and v.layer = 'tenant'" in versions


# ---------------------------------------------------------------------------
# POST /versoes/{id}/restaurar
# ---------------------------------------------------------------------------
def test_restaurar_move_o_ponteiro_e_devolve_a_camada_de_tenant_nova(
    client: TestClient, cabecalho: dict[str, str], db
):
    user, bound, _ = db(pointer_moved={"version_id": TENANT_V1, "previous_version_id": TENANT_V2})

    resposta = client.post(
        f"/assistente/configuracao/versoes/{TENANT_V1}/restaurar", headers=cabecalho
    )

    assert resposta.status_code == 200
    assert resposta.json() == {
        "version_id": str(TENANT_V1),
        "version_number": 1,
        "content": "v1",
        "created_at": WHEN_JSON,
        "created_by": str(USER_ID),
    }
    # Read as the user, with the three conditions, BEFORE the write.
    check = next(s for s in user.statements if "where v.id = %(version_id)s" in s)
    assert "v.tenant_id = %(tenant_id)s" in check
    assert "v.layer = 'tenant'" in check
    [update] = _writes(bound)
    assert "update app.assistant_prompt_pointer" in update
    assert "layer = 'tenant'" in update
    assert "updated_by = %(user_id)s" in update
    assert bound.params[0] == {"version_id": TENANT_V1, "user_id": USER_ID}
    [audit] = _audits(bound)
    assert audit["entity"] == "assistant_prompt_pointer"
    assert audit["antes"].obj == {"version_id": str(TENANT_V2)}
    assert audit["depois"].obj == {"version_id": str(TENANT_V1)}


@pytest.mark.parametrize(
    "version_id",
    [OTHER_V1, PLATFORM_V1, UUID("00000000-0000-4000-8000-00000000dead")],
    ids=["outro_tenant", "plataforma", "inexistente"],
)
def test_restaurar_recusa_com_404_antes_de_qualquer_escrita(
    client: TestClient, cabecalho: dict[str, str], db, version_id: UUID
):
    """Another tenant's, the platform's, or none: 404, and the service_role
    transaction never opened. The order is the contract; the trigger is the net."""
    _, bound, bound_ctx = db(pointer_moved={"version_id": version_id, "previous_version_id": None})

    resposta = client.post(
        f"/assistente/configuracao/versoes/{version_id}/restaurar", headers=cabecalho
    )

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Versão não encontrada."
    assert bound_ctx.opened == 0
    assert bound.statements == []


def test_quem_nao_e_admin_nao_restaura(client: TestClient, cabecalho: dict[str, str], db):
    user, _, bound_ctx = db(admin=False)

    resposta = client.post(
        f"/assistente/configuracao/versoes/{TENANT_V1}/restaurar", headers=cabecalho
    )

    assert resposta.status_code == 403
    assert bound_ctx.opened == 0
    # Refused before even looking the version up.
    assert all("where v.id" not in s for s in user.statements)


# ---------------------------------------------------------------------------
# Capacidades
# ---------------------------------------------------------------------------
def test_capacidades_traz_todas_as_linhas_da_regua_unica(
    client: TestClient, cabecalho: dict[str, str], db
):
    user, _, bound_ctx = db()

    resposta = client.get("/assistente/configuracao/capacidades", headers=cabecalho)

    assert resposta.status_code == 200
    assert resposta.json() == CATALOG
    [sql] = user.statements
    assert "public.fn_assistant_catalog(%(tenant_id)s)" in sql
    assert "where visible_to_me" not in sql
    # The runtime columns stay inside.
    assert "target_view" not in sql
    assert bound_ctx.opened == 0


def test_quem_nao_e_admin_nao_liga_nem_desliga(client: TestClient, cabecalho: dict[str, str], db):
    _, _, bound_ctx = db(admin=False)

    resposta = client.put(
        "/assistente/configuracao/capacidades/payroll_summary",
        json={"enabled": False},
        headers=cabecalho,
    )

    assert resposta.status_code == 403
    assert bound_ctx.opened == 0


def test_desligar_uma_metrica_grava_o_escopo_audita_e_rele_pela_regua(
    client: TestClient, cabecalho: dict[str, str], db
):
    user, bound, _ = db(
        catalog_one=CATALOG[1] | {"enabled": False},
        scope_saved={"enabled": False, "before_enabled": None},
    )

    resposta = client.put(
        "/assistente/configuracao/capacidades/payroll_summary",
        json={"enabled": False},
        headers=cabecalho,
    )

    assert resposta.status_code == 200
    assert resposta.json()["enabled"] is False
    assert resposta.json()["visible_to_me"] is False
    [upsert] = _writes(bound)
    assert "insert into app.assistant_metric_scope" in upsert
    assert "on conflict (tenant_id, metric_code) do update" in upsert
    assert "delete" not in upsert.lower()
    assert bound.params[0] == {"code": "payroll_summary", "enabled": False, "user_id": USER_ID}
    [audit] = _audits(bound)
    assert audit["action"] == "insert"
    assert audit["entity"] == "assistant_metric_scope"
    assert audit["entity_id"] == "payroll_summary"
    assert audit["antes"] is None
    assert audit["depois"].obj == {"enabled": False}
    # Existence checked and the row re-read through the same ruler, as the user.
    assert [s for s in user.statements if "where code = %(code)s" in s].__len__() == 2


def test_religar_audita_o_valor_anterior(client: TestClient, cabecalho: dict[str, str], db):
    _, bound, _ = db(catalog_one=CATALOG[1], scope_saved={"enabled": True, "before_enabled": False})

    resposta = client.put(
        "/assistente/configuracao/capacidades/payroll_summary",
        json={"enabled": True},
        headers=cabecalho,
    )

    assert resposta.status_code == 200
    [audit] = _audits(bound)
    assert audit["action"] == "update"
    assert audit["antes"].obj == {"enabled": False}


def test_metrica_que_a_regua_nao_conhece_e_404_antes_de_escrever(
    client: TestClient, cabecalho: dict[str, str], db
):
    _, _, bound_ctx = db(catalog_one=None)

    resposta = client.put(
        "/assistente/configuracao/capacidades/custo_por_hora",
        json={"enabled": False},
        headers=cabecalho,
    )

    assert resposta.status_code == 404
    assert bound_ctx.opened == 0


# ---------------------------------------------------------------------------
# POST /testar
# ---------------------------------------------------------------------------
LAYERS = PromptLayers(
    platform_version_id=PLATFORM_V1,
    platform_content=PLATFORM_ROW["content"],
    provider="anthropic",
    model="claude-haiku-4-5-20251001",
    max_steps=None,
    tenant_version_id=TENANT_V2,
    tenant_content="Vocabulário v2",
)


@pytest.fixture
def turno_real(monkeypatch: pytest.MonkeyPatch, banco: dict[str, Any]) -> dict[str, Any]:  # noqa: F811
    """`answer()` for real — layers, a scripted model and the record captured
    — so what `/testar` writes is what the Turn produced, not a stub's guess."""
    estado: dict[str, Any] = {"gravados": [], "camadas": LAYERS}

    async def load_layers(tenant: TenantContext) -> PromptLayers | None:
        return estado["camadas"]

    def build_model(pedido: str | None, **kw: Any) -> tuple[Any, str]:
        modelo = FakeChatModel(responses=[AIMessage(content="ok")], calls=[])
        estado["modelo"] = modelo
        return modelo, "fake-1"

    async def registrar(tenant: TenantContext, record: Record) -> UUID:
        estado["gravados"].append(record)
        return uuid4()

    monkeypatch.setattr(assistente, "load_layers", load_layers)
    monkeypatch.setattr(assistente, "build_model", build_model)
    monkeypatch.setattr(assistente, "registrar", registrar)
    monkeypatch.setattr(assistente, "_limiter", assistente.RateLimiter())
    return estado


def _eventos(corpo: str) -> list[tuple[str, dict[str, Any]]]:
    lidos = []
    for bloco in corpo.strip().split("\n\n"):
        linhas = dict(linha.split(": ", 1) for linha in bloco.splitlines() if ": " in linha)
        lidos.append((linhas["event"], json.loads(linhas["data"])))
    return lidos


def test_testar_sem_rascunho_grava_dry_run_com_a_versao_de_tenant_no_ar(
    client: TestClient, cabecalho: dict[str, str], db, turno_real: dict[str, Any]
):
    db()

    resposta = client.post(
        "/assistente/configuracao/testar",
        json={"question": "quantos desvios?", "use_draft": False},
        headers=cabecalho,
    )

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/event-stream")
    assert [nome for nome, _ in _eventos(resposta.text)][-1] == "done"
    [gravado] = turno_real["gravados"]
    assert gravado.is_dry_run is True
    assert gravado.prompt_version_id == TENANT_V2
    assert gravado.draft_content_hash is None
    assert "Vocabulário v2" in turno_real["modelo"].calls[0][0].text


def test_testar_com_rascunho_grava_o_hash_e_aponta_para_a_plataforma(
    client: TestClient, cabecalho: dict[str, str], db, turno_real: dict[str, Any]
):
    db(draft=draft_row(content="Rascunho: chame de pátio."))

    resposta = client.post(
        "/assistente/configuracao/testar",
        json={"question": "quantos desvios?", "use_draft": True},
        headers=cabecalho,
    )

    assert resposta.status_code == 200
    [gravado] = turno_real["gravados"]
    assert gravado.is_dry_run is True
    assert gravado.prompt_version_id == PLATFORM_V1
    esperado = hashlib.sha256("Rascunho: chame de pátio.".encode()).hexdigest()
    assert gravado.draft_content_hash == esperado
    prompt = turno_real["modelo"].calls[0][0].text
    assert "pátio" in prompt
    assert "Vocabulário v2" not in prompt


def test_o_done_do_teste_diz_o_que_rodou_e_nao_o_que_a_tela_pediu(
    client: TestClient, cabecalho: dict[str, str], db, turno_real: dict[str, Any]
):
    """O selo "Rascunho" da tela sai do `done`, e o `done` sai do registro.

    Hoje `use_draft` e o que rodou coincidem, porque testar sem rascunho é
    404 antes do stream. No dia em que isso virar fallback, o pedido mentiria
    e o hash não: é ele que a tela tem de ler.
    """
    db(draft=draft_row(content="Rascunho: chame de pátio."))

    resposta = client.post(
        "/assistente/configuracao/testar",
        json={"question": "quantos desvios?", "use_draft": True},
        headers=cabecalho,
    )

    nome, dados = _eventos(resposta.text)[-1]
    assert nome == "done"
    assert (
        dados["draft_content_hash"]
        == hashlib.sha256("Rascunho: chame de pátio.".encode()).hexdigest()
    )
    assert dados["prompt_version_id"] == str(PLATFORM_V1)


def test_o_done_do_teste_sem_rascunho_nao_carrega_hash(
    client: TestClient, cabecalho: dict[str, str], db, turno_real: dict[str, Any]
):
    db()

    resposta = client.post(
        "/assistente/configuracao/testar",
        json={"question": "quantos desvios?", "use_draft": False},
        headers=cabecalho,
    )

    _, dados = _eventos(resposta.text)[-1]
    assert dados["draft_content_hash"] is None
    assert dados["prompt_version_id"] == str(TENANT_V2)


def test_testar_com_rascunho_sem_ser_admin_e_403_e_nao_roda(
    client: TestClient, cabecalho: dict[str, str], db, turno_real: dict[str, Any]
):
    """The RLS would answer "no draft"; the backend says "no permission"."""
    db(admin=False, draft=None)

    resposta = client.post(
        "/assistente/configuracao/testar",
        json={"question": "oi", "use_draft": True},
        headers=cabecalho,
    )

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Sem permissão para testar o rascunho."
    assert turno_real["gravados"] == []


def test_admin_sem_rascunho_recebe_404_e_nao_roda(
    client: TestClient, cabecalho: dict[str, str], db, turno_real: dict[str, Any]
):
    db(admin=True, draft=None)

    resposta = client.post(
        "/assistente/configuracao/testar",
        json={"question": "oi", "use_draft": True},
        headers=cabecalho,
    )

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Não há rascunho para testar."
    assert turno_real["gravados"] == []


def test_testar_sem_rascunho_nao_exige_admin(
    client: TestClient, cabecalho: dict[str, str], db, turno_real: dict[str, Any]
):
    db(admin=False)

    resposta = client.post(
        "/assistente/configuracao/testar",
        json={"question": "oi"},
        headers=cabecalho,
    )

    assert resposta.status_code == 200
    assert turno_real["gravados"][0].is_dry_run is True


def test_testar_sem_ponteiro_de_plataforma_sai_so_o_error(
    client: TestClient, cabecalho: dict[str, str], db, turno_real: dict[str, Any]
):
    db()
    turno_real["camadas"] = None

    resposta = client.post(
        "/assistente/configuracao/testar", json={"question": "oi"}, headers=cabecalho
    )

    assert resposta.status_code == 200
    assert [nome for nome, _ in _eventos(resposta.text)] == ["error"]
    assert turno_real["gravados"] == []


def test_o_teste_nao_aceita_papel_nem_campo_desconhecido(
    client: TestClient, cabecalho: dict[str, str], db
):
    """No role selector (SPEC §5): `extra="forbid"` is what keeps one from
    appearing without a decision."""
    db()

    resposta = client.post(
        "/assistente/configuracao/testar",
        json={"question": "oi", "role": "unit_supervisor"},
        headers=cabecalho,
    )

    assert resposta.status_code == 422


# ---------------------------------------------------------------------------
# What the module must not contain
# ---------------------------------------------------------------------------
def test_nenhuma_rota_escreve_na_camada_de_plataforma():
    """SPEC §1: the platform layer changes by migration only."""
    fonte = open(assistente_config.__file__, encoding="utf-8").read()
    for statement in (
        assistente_config._DRAFT_UPSERT_SQL,
        assistente_config._POINTER_UPDATE_SQL,
        assistente_config._SCOPE_UPSERT_SQL,
    ):
        assert "'platform'" not in statement
    assert "layer = 'platform'" not in assistente_config._POINTER_UPDATE_SQL
    assert "insert into app.assistant_prompt_version" not in fonte


def test_toda_escrita_passa_pelo_admin_antes_da_transacao():
    """Every route with a `tenant_scope` calls `_require_admin` before it —
    the pattern of `canais.py`, read from the source in order."""
    fonte = open(assistente_config.__file__, encoding="utf-8").read()
    corpo = fonte[fonte.index("@router.put") :]
    for rota in corpo.split("@router.")[1:]:
        if "tenant_scope(" not in rota or rota.startswith('post("/publicar")'):
            continue
        assert rota.index("_require_admin(") < rota.index("tenant_scope("), rota[:60]


# ---------------------------------------------------------------------------
# GET /execucoes e GET /custo
# ---------------------------------------------------------------------------
RUN_ROW = {
    "created_at": WHEN,
    "question": "quantos desvios ontem?",
    "metric_code": "deviations_total",
    "rows_returned": 3,
    "latency_ms": 500,
    "input_tokens": 100,
    "output_tokens": 20,
    "model": "fake-1",
    "refused": False,
    "refusal_reason": None,
    "prompt_version_id": TENANT_V2,
    "version_label": "v2",
}

COST_ROW = {
    "month_start": "2026-09-01",
    "version_label": "antes do versionamento",
    "prompt_version_id": None,
    "model": "gpt-5.4-mini",
    "runs": 4,
    "refused_runs": 1,
    "input_tokens": 400,
    "output_tokens": 90,
    "avg_latency_ms": "275.5",
}


def test_execucoes_traz_o_turno_com_a_versao_que_o_produziu(
    client: TestClient, cabecalho: dict[str, str], db
):
    user, _, _ = db(
        runs=[
            RUN_ROW,
            RUN_ROW | {"prompt_version_id": None, "version_label": "antes do versionamento"},
        ]
    )

    resposta = client.get("/assistente/configuracao/execucoes", headers=cabecalho)

    assert resposta.status_code == 200
    primeira, segunda = resposta.json()
    assert primeira["version_label"] == "v2"
    assert primeira["prompt_version_id"] == str(TENANT_V2)
    assert primeira["metric_code"] == "deviations_total"
    assert primeira["input_tokens"] == 100
    # A linha anterior ao versionamento chega rotulada, e nunca como "v1".
    assert segunda["prompt_version_id"] is None
    assert segunda["version_label"] == "antes do versionamento"
    assert "public.fn_assistant_runs(%(weeks)s)" in user.statements[0]
    assert user.params[0] == {"weeks": 8}


def test_execucoes_aceita_a_janela_e_recusa_a_de_fora_da_faixa(
    client: TestClient, cabecalho: dict[str, str], db
):
    user, _, _ = db(runs=[])

    assert (
        client.get("/assistente/configuracao/execucoes?weeks=12", headers=cabecalho).status_code
        == 200
    )
    assert user.params[0] == {"weeks": 12}
    for fora in ("0", "53", "-1"):
        resposta = client.get(f"/assistente/configuracao/execucoes?weeks={fora}", headers=cabecalho)
        assert resposta.status_code == 422, fora


def test_execucoes_nao_pede_admin_porque_a_policy_ja_recorta(
    client: TestClient, cabecalho: dict[str, str], db
):
    """`fn_assistant_runs` é invoker e `ai_query_read` é próprio-ou-admin: um
    membro comum vendo os próprios turnos é o desenho, não um furo."""
    user, _, _ = db(admin=False, runs=[RUN_ROW])

    resposta = client.get("/assistente/configuracao/execucoes", headers=cabecalho)

    assert resposta.status_code == 200
    assert len(resposta.json()) == 1
    assert not any("util.is_admin" in statement for statement in user.statements)


def test_custo_quebra_a_competencia_por_versao(client: TestClient, cabecalho: dict[str, str], db):
    user, _, _ = db(
        cost=[COST_ROW, COST_ROW | {"version_label": "v2", "prompt_version_id": TENANT_V2}]
    )

    resposta = client.get("/assistente/configuracao/custo?weeks=4", headers=cabecalho)

    assert resposta.status_code == 200
    sem_versao, com_versao = resposta.json()
    assert sem_versao["version_label"] == "antes do versionamento"
    assert sem_versao["prompt_version_id"] is None
    assert sem_versao["runs"] == 4
    assert sem_versao["refused_runs"] == 1
    assert sem_versao["avg_latency_ms"] == "275.5"
    assert com_versao["prompt_version_id"] == str(TENANT_V2)
    assert "public.fn_assistant_cost_by_version(%(weeks)s)" in user.statements[0]
    assert user.params[0] == {"weeks": 4}


def test_o_custo_separa_a_mesma_versao_em_dois_modelos(
    client: TestClient, cabecalho: dict[str, str], db
):
    """O modelo está na chave porque é ele que vira preço.

    A versão gravada é a do tenant, mas quem escolhe o modelo é a camada de
    plataforma, que o registro não guarda: republicar a doutrina troca o preço
    sem mover o rótulo. Sem o modelo na linha, "a v2 custou X" soma dois
    preços — medido em 20/09/2026.
    """
    base = COST_ROW | {"version_label": "v2", "prompt_version_id": TENANT_V2}
    db(
        cost=[
            base | {"model": "gpt-5.4-mini", "runs": 4, "input_tokens": 400},
            base | {"model": "gpt-5.4", "runs": 1, "input_tokens": 900},
        ]
    )

    corpo = client.get("/assistente/configuracao/custo", headers=cabecalho).json()

    assert [linha["model"] for linha in corpo] == ["gpt-5.4-mini", "gpt-5.4"]
    assert [linha["version_label"] for linha in corpo] == ["v2", "v2"]
    # Duas linhas, e não uma soma de 5 turnos: o rótulo é o mesmo, o preço não.
    assert [linha["runs"] for linha in corpo] == [4, 1]


def test_custo_recusa_a_janela_fora_da_faixa(client: TestClient, cabecalho: dict[str, str], db):
    db(cost=[])

    assert (
        client.get("/assistente/configuracao/custo?weeks=0", headers=cabecalho).status_code == 422
    )
    assert (
        client.get("/assistente/configuracao/custo?weeks=53", headers=cabecalho).status_code == 422
    )


def test_as_duas_leituras_de_execucoes_nao_abrem_transacao_de_service_role(
    client: TestClient, cabecalho: dict[str, str], db
):
    """Leitura como o usuário, sempre: `tenant_scope` ignora RLS, e aqui é a
    RLS que responde quem vê o quê."""
    _, _, bound_ctx = db(runs=[RUN_ROW], cost=[COST_ROW])

    client.get("/assistente/configuracao/execucoes", headers=cabecalho)
    client.get("/assistente/configuracao/custo", headers=cabecalho)

    assert bound_ctx.opened == 0


def test_e2e_intocado():
    """The fake provider goes through the same boundary; the flag is still the
    only switch, and it lives in `build_model`."""
    assert agente.e2e.FLAG == "E2E_FAKE_LLM"
