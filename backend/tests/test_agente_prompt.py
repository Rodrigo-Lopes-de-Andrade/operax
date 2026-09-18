"""`operax.agente.prompt` — the renderer of the three tokens and the reader of the pointers.

Pure on one side (`render`, `PromptLayers.text`), one query on the other
(`load_layers`, under `user_scope`, with a stub cursor). What matters here:
the three tokens and nothing else; the fallback line of the units belonging to
the renderer; the tenant layer concatenated **before** rendering; a fourth
token raising, because a turn that ran with `{{x}}` in it would be a turn
nobody configured; and `None` without a platform pointer — never a text made
up here.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import pytest

from operax.agente import prompt
from operax.agente.prompt import PromptLayers
from operax.core.tenant import TenantContext, UserRole

TENANT = TenantContext(
    tenant_id=UUID("22222222-2222-4222-8222-222222222222"),
    user_id=UUID("11111111-1111-4111-8111-111111111111"),
    role=UserRole.OWNER,
)
PLATFORM_ID = UUID("44444444-4444-4444-8444-444444444441")
TENANT_ID = UUID("44444444-4444-4444-8444-444444444442")
HOJE = date(2026, 9, 17)
UNIDADES: list[dict[str, Any]] = [
    {"name": "Shopping Norte", "code": "NORTE", "unit_id": "dede0000-0000-4000-8000-0000000000a1"},
    {"name": "Centro", "code": "CENTRO", "unit_id": "dede0000-0000-4000-8000-0000000000a2"},
]
TEMPLATE = "Hoje: {{hoje}}\nMétricas:\n{{catalogo}}\nUnidades:\n{{unidades}}\nFim."


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------
def test_render_substitui_os_tres_tokens():
    saida = prompt.render(TEMPLATE, catalogo="- a: b.", unidades=UNIDADES, hoje=HOJE)

    assert saida == (
        "Hoje: 17/09/2026 (2026-09-17)\n"
        "Métricas:\n- a: b.\n"
        "Unidades:\n"
        "- Shopping Norte (NORTE): dede0000-0000-4000-8000-0000000000a1\n"
        "- Centro (CENTRO): dede0000-0000-4000-8000-0000000000a2\n"
        "Fim."
    )


def test_render_sem_unidades_poe_a_linha_fixa_do_renderizador():
    saida = prompt.render(TEMPLATE, catalogo="- a: b.", unidades=[], hoje=HOJE)

    assert "Unidades:\n- nenhuma unidade cadastrada; não use o parâmetro `unit`.\nFim." in saida
    assert "{{" not in saida


def test_render_recusa_token_desconhecido():
    with pytest.raises(ValueError, match="papel"):
        prompt.render(TEMPLATE + " {{papel}}", catalogo="", unidades=[], hoje=HOJE)


def test_render_nao_procura_token_dentro_do_que_substituiu():
    """Uma passada só: `{{x}}` no nome de uma unidade é dado, não marcador."""
    unidades = [{"name": "Loja {{x}}", "code": "X", "unit_id": "u"}]

    saida = prompt.render(TEMPLATE, catalogo="- {{catalogo}}", unidades=unidades, hoje=HOJE)

    assert "- Loja {{x}} (X): u" in saida
    assert "Métricas:\n- {{catalogo}}\n" in saida


def test_render_nao_toca_no_que_nao_e_token():
    assert prompt.render("sem marcador", catalogo="x", unidades=[], hoje=HOJE) == "sem marcador"


# ---------------------------------------------------------------------------
# PromptLayers
# ---------------------------------------------------------------------------
def _layers(tenant_content: str | None, tenant_version_id: UUID | None = None) -> PromptLayers:
    return PromptLayers(
        platform_version_id=PLATFORM_ID,
        platform_content="plataforma {{hoje}}",
        provider="openai",
        model="gpt-5.4-mini",
        max_steps=None,
        tenant_version_id=tenant_version_id,
        tenant_content=tenant_content,
    )


def test_texto_efetivo_e_plataforma_seguida_de_tenant_com_linha_em_branco():
    assert _layers("tenant {{hoje}}").text() == "plataforma {{hoje}}\n\ntenant {{hoje}}"


def test_sem_camada_de_tenant_o_texto_e_so_a_plataforma():
    assert _layers(None).text() == "plataforma {{hoje}}"


def test_o_rascunho_entra_no_lugar_da_camada_de_tenant():
    assert _layers("tenant").text("rascunho") == "plataforma {{hoje}}\n\nrascunho"
    assert _layers(None).text("rascunho") == "plataforma {{hoje}}\n\nrascunho"


def test_a_versao_registrada_e_a_de_tenant_ou_senao_a_de_plataforma():
    assert _layers("t", TENANT_ID).version_id == TENANT_ID
    assert _layers(None).version_id == PLATFORM_ID


def test_a_concatenacao_renderiza_depois_e_o_tenant_tambem_usa_os_tokens():
    saida = prompt.render(_layers("tenant {{hoje}}").text(), catalogo="", unidades=[], hoje=HOJE)

    assert saida == "plataforma 17/09/2026 (2026-09-17)\n\ntenant 17/09/2026 (2026-09-17)"


# ---------------------------------------------------------------------------
# load_layers
# ---------------------------------------------------------------------------
class StubScope:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.statements: list[str] = []
        self.params: list[Any] = []

    async def execute(self, statement: str, params: Any = None) -> None:
        self.statements.append(statement)
        self.params.append(params)

    async def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class StubScopeContext:
    def __init__(self, scope: StubScope) -> None:
        self._scope = scope

    async def __aenter__(self) -> StubScope:
        return self._scope

    async def __aexit__(self, *exc: object) -> None:
        return None


def _row(layer: str, version_id: UUID, content: str, **extra: Any) -> dict[str, Any]:
    return {
        "layer": layer,
        "version_id": version_id,
        "content": content,
        "provider": None,
        "model": None,
        "max_steps": None,
    } | extra


@pytest.fixture
def banco(monkeypatch: pytest.MonkeyPatch):
    def install(rows: list[dict[str, Any]]) -> StubScope:
        scope = StubScope(rows)
        monkeypatch.setattr(prompt, "user_scope", lambda _t: StubScopeContext(scope))
        return scope

    return install


async def test_load_layers_le_os_dois_ponteiros_como_o_usuario(banco):
    scope = banco(
        [
            _row(
                "platform", PLATFORM_ID, "p", provider="openai", model="gpt-5.4-mini", max_steps=3
            ),
            _row("tenant", TENANT_ID, "t"),
        ]
    )

    camadas = await prompt.load_layers(TENANT)

    assert camadas == PromptLayers(
        platform_version_id=PLATFORM_ID,
        platform_content="p",
        provider="openai",
        model="gpt-5.4-mini",
        max_steps=3,
        tenant_version_id=TENANT_ID,
        tenant_content="t",
    )
    # Pelo ponteiro, nunca pelo rascunho; e com o tenant do contexto — no
    # texto do SQL, não só nos parâmetros: sem o predicado, a RLS ainda
    # segura, mas a consulta deixa de ser o contrato (regra 4).
    assert "app.assistant_prompt_pointer" in scope.statements[0]
    assert "assistant_draft" not in scope.statements[0]
    assert "p.tenant_id = %(tenant_id)s and p.layer = 'tenant'" in scope.statements[0]
    assert scope.params[0] == {"tenant_id": TENANT.tenant_id}


async def test_load_layers_sem_tenant_deixa_a_camada_de_tenant_nula(banco):
    banco([_row("platform", PLATFORM_ID, "p")])

    camadas = await prompt.load_layers(TENANT)

    assert camadas is not None
    assert camadas.tenant_version_id is None
    assert camadas.tenant_content is None
    assert camadas.version_id == PLATFORM_ID


async def test_load_layers_sem_plataforma_devolve_none_e_nao_inventa_texto(banco):
    """Um ponteiro de tenant sozinho não é prompt: a RPC não o cria sem plataforma,
    e se ele existisse por outro caminho, rodar só com ele seria rodar sem doutrina."""
    banco([_row("tenant", TENANT_ID, "t")])

    assert await prompt.load_layers(TENANT) is None

    banco([])
    assert await prompt.load_layers(TENANT) is None
