"""The catalogue comes from `public.fn_assistant_catalog`, and from nowhere else.

SPEC-AGENTE §4.3, the lesson the DeskcommCRM paid to learn: a screen and a
runtime with rulers of their own diverge only in the rare case — which is where
nobody looks — and the divergence shows up as "the tab says it is on and the
assistant says it has no such data", indistinguishable from a model bug. So the
"Capacidades" tab and `executor.load_catalog` read the same function, and this
file is the gate that fails if the runtime grows a query of its own again.

Two halves. The first reads every module under `operax/` and `server/` as TEXT
and refuses any SQL over `app.metric` — the gate of §4.3, which no amount of
mocking can satisfy, and which a third module would otherwise slip past. The
second runs `load_catalog` over a fake scope and checks what it asks the
database: the RPC, the tenant of the context, and `where visible_to_me` as the
LAST clause of the statement, with SQL comments stripped first — a review
planted the RPC in a `--` comment and the substring checks went green while the
catalogue came from `app.metric`. The filter is in SQL, so a disabled metric
never reaches the raw list, let alone `from_rows`.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from operax.agente import catalogo, executor
from operax.core.tenant import TenantContext, UserRole

AGENTE = Path(executor.__file__).parent
EXECUTOR = AGENTE / "executor.py"
BACKEND = AGENTE.parent.parent
MODULES = sorted([*(BACKEND / "operax").rglob("*.py"), *(BACKEND / "server").rglob("*.py")])
APP_METRIC = re.compile(r"\bapp\s*\.\s*metric\b")

TENANT = TenantContext(
    tenant_id=UUID("22222222-2222-4222-8222-222222222222"),
    user_id=UUID("11111111-1111-4111-8111-111111111111"),
    role=UserRole.UNIT_SUPERVISOR,
)

# What the RPC hands back: the six columns of SPEC §3e plus the three the
# runtime needs. `payroll_summary` is what the tenant disabled — or what the
# role cannot see; the RPC does not say which, and the runtime does not care.
RPC_ROWS: list[dict[str, Any]] = [
    {
        "code": "deviations_total",
        "title": "Total de desvios no período",
        "description": "Contagem de ocorrências ativas",
        "target_view": "fn_kpi_period",
        "dimensions": ["unit", "company"],
        "filters": ["start_date", "end_date"],
        "domain": None,
        "enabled": True,
        "visible_to_me": True,
    },
    {
        "code": "payroll_summary",
        "title": "Resumo da folha por competência",
        "description": "Valor total",
        "target_view": "vw_payroll_summary",
        "dimensions": ["company", "unit", "payroll_period"],
        "filters": ["year", "month"],
        "domain": "compensation",
        "enabled": False,
        "visible_to_me": False,
    },
    {
        "code": "ranking_by_unit",
        "title": "Ranking de desvios por unidade",
        "description": "Unidades ordenadas por ocorrências",
        "target_view": "fn_ranking_by_unit",
        "dimensions": ["unit"],
        "filters": ["start_date", "end_date"],
        "domain": None,
        "enabled": True,
        "visible_to_me": True,
    },
]


# ---------------------------------------------------------------------------
# Gate 2 — the text of every module
# ---------------------------------------------------------------------------
def _flat(text: str) -> str:
    return " ".join(text.split()).lower()


def _executed(statement: str) -> str:
    """The statement as the database reads it: no `--` or `/* */` comments.

    A comment can spell the RPC and the filter word for word; only what is left
    after stripping it is what runs.
    """
    sem_linha = re.sub(r"--[^\n]*", "", statement)
    sem_bloco = re.sub(r"/\*.*?\*/", "", sem_linha, flags=re.DOTALL)
    return _flat(sem_bloco).rstrip("; ")


def _sql_strings(path: Path) -> list[str]:
    """Every string constant in the module that is NOT a docstring.

    Prose may name `app.metric` — the docstrings of `catalogo.py` describe what a
    `Metric` is a row of. A string that is not a docstring is a string that can
    reach `execute`, and that is the one that may not say it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


@pytest.mark.parametrize("path", MODULES, ids=[str(p.relative_to(BACKEND)) for p in MODULES])
def test_gate_2_no_module_builds_the_catalogue_by_its_own_query(path: Path) -> None:
    """A screen and a runtime with rulers of their own diverge only in the rare case.

    Every module, not just the two of the agent: a third file reading
    `app.metric` for the executor is the same regression with a different name.
    Three spellings of it: `from app.metric` anywhere in the text, `app.metric`
    — with any spacing, split across concatenated literals — in strings that are
    not docstrings (an SQL literal), and the PostgREST spelling `.from("metric")`.
    """
    text = path.read_text(encoding="utf-8")
    assert "from app.metric" not in _flat(text), f"{path} reads app.metric directly"
    assert not re.search(r"\.from\(\s*['\"]metric['\"]\s*\)", text), (
        f"{path} builds the catalogue through PostgREST's .from('metric')"
    )
    # Joined without a separator on purpose: `"from app." + "metric"` is one
    # statement to the database and must be one string to this gate.
    literais = "".join(_sql_strings(path)).lower()
    assert not APP_METRIC.search(literais), f"{path} has app.metric in a string that can reach SQL"


def test_gate_2_the_executor_reads_the_single_ruler() -> None:
    """Not reading `app.metric` is half of it: the RPC has to be what is read."""
    assert "fn_assistant_catalog" in EXECUTOR.read_text(encoding="utf-8")
    assert "fn_assistant_catalog" in executor._CATALOG_SQL


# ---------------------------------------------------------------------------
# `load_catalog` over a fake scope
# ---------------------------------------------------------------------------
class StubScope:
    """Records the statement and the parameters, and answers like the database
    would: the rows of the RPC, with `where visible_to_me` honoured only if the
    statement — comments stripped — ENDS in exactly that clause. `= false`,
    `is not null` or a commented-out filter get every row, as they would."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.statements: list[str] = []
        self.params: list[Any] = []

    async def execute(self, statement: str, params: Any = None) -> None:
        self.statements.append(statement)
        self.params.append(params)

    async def fetchone(self) -> dict[str, Any] | None:
        rows = await self.fetchall()
        return rows[0] if rows else None

    async def fetchall(self) -> list[dict[str, Any]]:
        if _executed(self.statements[-1]).endswith("where visible_to_me"):
            return [dict(r) for r in self._rows if r["visible_to_me"]]
        return [dict(r) for r in self._rows]


class StubScopeContext:
    def __init__(self, scope: StubScope) -> None:
        self._scope = scope

    async def __aenter__(self) -> StubScope:
        return self._scope

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.fixture
def scope(monkeypatch: pytest.MonkeyPatch) -> StubScope:
    stub = StubScope(RPC_ROWS)
    monkeypatch.setattr(executor, "user_scope", lambda tenant: StubScopeContext(stub))
    return stub


async def test_load_catalog_calls_the_rpc_with_the_tenant_of_the_context(scope: StubScope) -> None:
    await executor.load_catalog(TENANT)

    assert len(scope.statements) == 1
    statement = _executed(scope.statements[0])
    assert "from public.fn_assistant_catalog(%(tenant_id)s)" in statement
    assert not APP_METRIC.search(statement), "the executed statement reads app.metric"
    assert scope.params == [{"tenant_id": TENANT.tenant_id}]


async def test_load_catalog_filters_visible_to_me_in_sql(scope: StubScope) -> None:
    """The filter is in the statement, not in Python: a disabled metric — or one
    outside the person's domains — never reaches the raw list."""
    rows = await executor.load_catalog(TENANT)

    # The last clause of what actually runs — not a substring: `= false` or a
    # comment spelling the filter would both contain it and filter nothing.
    assert _executed(scope.statements[0]).endswith("where visible_to_me")
    assert [row["code"] for row in rows] == ["deviations_total", "ranking_by_unit"]
    assert all(row["visible_to_me"] for row in rows)

    # And what reaches `from_rows` is exactly that — `payroll_summary` is gone
    # before the model could be shown it exists.
    metrics = catalogo.from_rows(rows)
    assert [m.code for m in metrics] == ["deviations_total", "ranking_by_unit"]


def test_from_rows_ignores_the_two_columns_the_runtime_does_not_need() -> None:
    """`enabled` and `visible_to_me` are the tab's columns. Everything that
    reaches `from_rows` is already visible, so a `Metric.enabled` that is always
    true would be a field with no reader."""
    metrics = catalogo.from_rows([row for row in RPC_ROWS if row["visible_to_me"]])

    assert {m.code for m in metrics} == {"deviations_total", "ranking_by_unit"}
    assert not hasattr(metrics[0], "enabled")
    assert not hasattr(metrics[0], "visible_to_me")
