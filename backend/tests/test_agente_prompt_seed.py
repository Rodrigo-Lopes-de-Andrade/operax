"""The platform v1 seeded by migration, rendered, is the prompt the code produced — byte for byte.

`docs/SPRINTS-AGENTE.md` §A1: "transcribe, do not rewrite". Until A3 the right
side of this comparison was `agente._prompt`, the literal in code. A3 removed
the literal (the runtime reads the pointer, and there is nothing to fall back
to), so the pin moved to the renderer's side: `tests/fixtures/prompt_v1_rendered.txt`
is the text `_prompt` produced for fixed inputs (`catalogo="- x: y."`, two
units, `date(2026, 9, 17)`), generated **before** the literal was deleted, and
`prompt.render(<the $platform_v1$ literal of the migration>, same inputs)` has
to reproduce it exactly. If a word "improves" in the migration or in the
renderer, the history starts by lying and this test says so.

The three tokens, as documented on `app.assistant_prompt_version.content`:
- `{{hoje}}`      -> `DD/MM/AAAA (AAAA-MM-DD)`, the whole date expression;
- `{{catalogo}}`  -> the catalogue text, verbatim;
- `{{unidades}}`  -> the whole block of unit lines, one `- Name (CODE): uuid` per
                     unit — or, with no unit, the fixed line telling the model not
                     to use `unit`. The block, fallback included, belongs to the
                     renderer, not to the seeded text.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from operax.agente import agente, prompt

HOJE = date(2026, 9, 17)
CATALOGO = "- x: y."
UNIDADES: list[dict[str, Any]] = [
    {"name": "Shopping Norte", "code": "NORTE", "unit_id": "dede0000-0000-4000-8000-0000000000a1"},
    {"name": "Centro", "code": "CENTRO", "unit_id": "dede0000-0000-4000-8000-0000000000a2"},
]
FIXTURE = Path(__file__).parent / "fixtures" / "prompt_v1_rendered.txt"


@pytest.fixture(scope="module")
def v1_da_migration(last_migration_with: Callable[[str], str]) -> str:
    """The seeded `content`, parsed out of the migration's dollar-quoted string."""
    sql = last_migration_with("$platform_v1$")
    achados = re.findall(r"\$platform_v1\$(.*?)\$platform_v1\$", sql, re.S)
    assert len(achados) == 1, "expected exactly one $platform_v1$ literal in the migration"
    return achados[0]


@pytest.fixture(scope="module")
def v1_renderizada() -> str:
    """What `agente._prompt` produced for these inputs, captured before it was removed."""
    return FIXTURE.read_text(encoding="utf-8")


def test_a_semente_carrega_os_tres_tokens_uma_vez_cada(v1_da_migration: str):
    for token in ("{{hoje}}", "{{catalogo}}", "{{unidades}}"):
        assert v1_da_migration.count(token) == 1, token
    # Nothing else that looks like a token: a fourth one would make `render` raise.
    assert set(re.findall(r"\{\{\w+\}\}", v1_da_migration)) == {
        "{{hoje}}",
        "{{catalogo}}",
        "{{unidades}}",
    }


def test_v1_renderizada_e_igual_ao_prompt_que_o_codigo_produzia(
    v1_da_migration: str, v1_renderizada: str
):
    """The pin, byte for byte, now on the renderer's side."""
    assert (
        prompt.render(v1_da_migration, catalogo=CATALOGO, unidades=UNIDADES, hoje=HOJE)
        == v1_renderizada
    )


def test_a_fixture_e_um_prompt_pronto_sem_marcador(v1_renderizada: str):
    assert "{{" not in v1_renderizada
    assert "17/09/2026 (2026-09-17)" in v1_renderizada
    assert "- Shopping Norte (NORTE): dede0000-0000-4000-8000-0000000000a1" in v1_renderizada
    assert CATALOGO in v1_renderizada


def test_sem_unidades_a_linha_fixa_e_do_renderizador(v1_da_migration: str):
    """The fallback line is not in the seed: it is rendered, and only then."""
    assert prompt.NO_UNITS_LINE not in v1_da_migration
    renderizado = prompt.render(v1_da_migration, catalogo=CATALOGO, unidades=[], hoje=HOJE)
    assert prompt.NO_UNITS_LINE in renderizado
    assert "{{" not in renderizado


def test_o_literal_em_codigo_nao_existe_mais():
    """No fallback text: the runtime reads the pointer or refuses to run."""
    assert not hasattr(agente, "_prompt")


def test_a_semente_registra_o_provider_e_o_modelo_que_o_codigo_escolhe_por_padrao(
    last_migration_with: Callable[[str], str],
):
    """`provider`/`model` of v1 are what `build_model()` picked before versioning."""
    sql = last_migration_with("$platform_v1$")
    provider = agente._PROVIDER_ORDER[0]
    modelo = agente.ALLOWED_MODELS[provider][0]
    insercao = sql[sql.index("insert into app.assistant_prompt_version") :]

    assert re.search(rf"\$platform_v1\$,\s*'{provider}',\s*'{modelo}',\s*null,\s*null", insercao), (
        f"v1 must seed provider={provider!r}, model={modelo!r}, max_steps=null, created_by=null"
    )
