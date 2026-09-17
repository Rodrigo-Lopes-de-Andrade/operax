"""The platform v1 seeded by migration is a transcription of `agente._prompt`, byte for byte.

`docs/SPRINTS-AGENTE.md` §A1: "transcribe, do not rewrite". If a word improves on
the way into the migration, v1 stops being the portrait of what is on the air and
the history starts by lying. The left side here is the text inside the migration
file (parsed, never re-typed); the right side is the function the runtime still
calls today. Comparing the migration with itself would be a tautology — the right
side is `_prompt`, and it is the only thing that knows how to render.

The three tokens, as documented on `app.assistant_prompt_version.content`:
- `{{hoje}}`      -> `DD/MM/AAAA (AAAA-MM-DD)`, the whole date expression;
- `{{catalogo}}`  -> the catalogue text, verbatim;
- `{{unidades}}`  -> the whole block of unit lines, one `- Name (CODE): uuid` per
                     unit — or, with no unit, the fixed line telling the model not
                     to use `unit`. The block, fallback included, belongs to the
                     renderer, not to the seeded text.

`agente.py` does not change in A1: the runtime keeps reading the code, and the
switch to the pointer is a later sprint. This test is what keeps the two equal
until then.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from operax.agente import agente

HOJE = date(2026, 9, 17)
CATALOGO = "- `deviation_daily_trend`: desvios por dia (start_date, end_date, unit)"
UNIDADES: list[dict[str, Any]] = [
    {"name": "Shopping Norte", "code": "NORTE", "unit_id": "dede0000-0000-4000-8000-0000000000a1"},
    {"name": "Centro", "code": "CENTRO", "unit_id": "dede0000-0000-4000-8000-0000000000a2"},
]
SEM_UNIDADE = "- nenhuma unidade cadastrada; não use o parâmetro `unit`."


@pytest.fixture(scope="module")
def v1_da_migration(last_migration_with: Callable[[str], str]) -> str:
    """The seeded `content`, parsed out of the migration's dollar-quoted string."""
    sql = last_migration_with("$platform_v1$")
    achados = re.findall(r"\$platform_v1\$(.*?)\$platform_v1\$", sql, re.S)
    assert len(achados) == 1, "expected exactly one $platform_v1$ literal in the migration"
    return achados[0]


def _render(seed: str, *, unidades: list[dict[str, Any]]) -> str:
    hoje = f"{HOJE.strftime('%d/%m/%Y')} ({HOJE.isoformat()})"
    if unidades:
        bloco = "\n".join(f"- {u['name']} ({u['code']}): {u['unit_id']}" for u in unidades)
    else:
        bloco = SEM_UNIDADE
    return (
        seed.replace("{{hoje}}", hoje)
        .replace("{{catalogo}}", CATALOGO)
        .replace("{{unidades}}", bloco)
    )


def test_a_semente_carrega_os_tres_tokens_uma_vez_cada(v1_da_migration: str):
    for token in ("{{hoje}}", "{{catalogo}}", "{{unidades}}"):
        assert v1_da_migration.count(token) == 1, token
    # Nothing else that looks like a token: a fourth one would render literally.
    assert set(re.findall(r"\{\{\w+\}\}", v1_da_migration)) == {
        "{{hoje}}",
        "{{catalogo}}",
        "{{unidades}}",
    }


def test_v1_renderizada_com_unidades_e_igual_ao_prompt_do_codigo(v1_da_migration: str):
    esperado = agente._prompt(CATALOGO, UNIDADES, HOJE)

    assert _render(v1_da_migration, unidades=UNIDADES) == esperado


def test_v1_renderizada_sem_unidades_e_igual_ao_prompt_do_codigo(v1_da_migration: str):
    esperado = agente._prompt(CATALOGO, [], HOJE)

    assert _render(v1_da_migration, unidades=[]) == esperado


def test_a_semente_registra_o_provider_e_o_modelo_que_o_codigo_escolhe_por_padrao(
    last_migration_with: Callable[[str], str],
):
    """`provider`/`model` of v1 are what `build_model()` picks when nothing is asked."""
    sql = last_migration_with("$platform_v1$")
    provider = agente._PROVIDER_ORDER[0]
    modelo = agente.ALLOWED_MODELS[provider][0]
    insercao = sql[sql.index("insert into app.assistant_prompt_version") :]

    assert re.search(rf"\$platform_v1\$,\s*'{provider}',\s*'{modelo}',\s*null,\s*null", insercao), (
        f"v1 must seed provider={provider!r}, model={modelo!r}, max_steps=null, created_by=null"
    )
