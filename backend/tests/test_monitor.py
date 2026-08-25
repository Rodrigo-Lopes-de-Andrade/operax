"""The daily monitor: what it ranks first, and what it refuses to claim.

Two things are worth a test here and neither is the SQL. The first is the
ordering: a monitor whose first row is not the loudest thing on it is a list,
not a monitor. The second is that the ranking policy lives in exactly one place
— the moment a `case` in the query starts ranking types too, the two copies
begin to drift and the screen silently changes its mind about what matters.

Nothing here touches a database. `user_scope` is the seam, and it is stubbed:
what the policies return is proved by the isolation suite, in SQL, against real
policies. What is proved here is what this module does with the answer.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from server.routers import monitor

DAY = date(2026, 8, 22)
DETECTED_AT = datetime(2026, 8, 22, 9, 12, tzinfo=UTC)
UNIT_ID = UUID("33333333-3333-4333-8333-333333333333")


def unit_row(**overrides: Any) -> dict[str, Any]:
    return {
        "unit_id": UNIT_ID,
        "unit_name": "Shopping Norte",
        "scheduled": 20,
        "with_indication": 3,
        "clear": 17,
        "off_roster": 4,
    } | overrides


def indication(deviation_type: str, minutes: int, name: str, **overrides: Any) -> dict[str, Any]:
    return {
        "employee_id": uuid4(),
        "employee_name": name,
        "unit_id": UNIT_ID,
        "unit_name": "Shopping Norte",
        "day_type": "work",
        "expected_entry": None,
        "expected_exit": None,
        "confidence": 100,
        "type": deviation_type,
        "type_description": deviation_type,
        "direction": "shortfall",
        "minutes": minutes,
        "expected_time": None,
        "actual_time": None,
        "detected_at": DETECTED_AT,
    } | overrides


class StubScope:
    """Hands back a queued batch per `fetchall`, and records what was asked."""

    def __init__(self, batches: list[list[dict[str, Any]]]) -> None:
        self._batches = list(batches)
        self.statements: list[str] = []
        self.params: list[Any] = []

    async def execute(self, statement: str, params: Any = None) -> None:
        self.statements.append(statement)
        self.params.append(params)

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._batches.pop(0)


class StubScopeContext:
    def __init__(self, scope: StubScope) -> None:
        self._scope = scope

    async def __aenter__(self) -> StubScope:
        return self._scope

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.fixture
def answer(monkeypatch: pytest.MonkeyPatch):
    """Queues what the database would return, and exposes the scope it used."""

    def install(units: list[dict[str, Any]], rows: list[dict[str, Any]]) -> StubScope:
        scope = StubScope([units, rows])
        monkeypatch.setattr(monitor, "user_scope", lambda _context: StubScopeContext(scope))
        return scope

    return install


def test_the_loudest_indication_comes_first_however_small_it_is(
    client: TestClient, issue_token, answer
):
    # 8 minutes of "nobody is at the gate" outranks two hours of "left early":
    # severity decides, and minutes only break the tie inside it.
    answer(
        [unit_row()],
        [
            indication("early_exit", -120, "Beatriz"),
            indication("break_exceeded", -95, "Caio"),
            indication("no_punches", -8, "Alice"),
        ],
    )

    response = client.get(
        "/monitor/diario",
        params={"dia": DAY.isoformat()},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [row["employee_name"] for row in body["rows"]] == ["Alice", "Beatriz", "Caio"]
    assert [row["severity"] for row in body["rows"]] == ["critical", "attention", "watch"]


def test_inside_one_severity_the_longer_deviation_comes_first(
    client: TestClient, issue_token, answer
):
    answer(
        [unit_row()],
        [
            indication("late_entry", -9, "Curto"),
            indication("late_entry", -47, "Longo"),
        ],
    )

    response = client.get(
        "/monitor/diario",
        params={"dia": DAY.isoformat()},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert [row["employee_name"] for row in response.json()["rows"]] == ["Longo", "Curto"]


def test_a_type_the_ranking_has_never_heard_of_still_arrives(
    client: TestClient, issue_token, answer
):
    """A new deviation type is an `insert` into a catalogue, not a deploy.

    So one can exist before this module learns how loud it is. It must land at
    the quiet end of the list, never vanish from it: an indication nobody sees
    is worse than one ranked wrongly.
    """
    answer([unit_row()], [indication("marcacao_futura", -30, "Novo")])

    body = client.get(
        "/monitor/diario",
        params={"dia": DAY.isoformat()},
        headers={"Authorization": f"Bearer {issue_token()}"},
    ).json()

    assert body["rows"][0]["severity"] == "watch"
    assert body["rows"][0]["employee_name"] == "Novo"


def test_a_punch_on_a_day_nobody_was_scheduled_survives_the_missing_roster(
    client: TestClient, issue_token, answer
):
    # The roster join is a left join precisely for this row: an inner join would
    # drop the one indication that means somebody was there unexpectedly.
    answer(
        [unit_row(scheduled=0, with_indication=0, clear=0, off_roster=6)],
        [indication("punch_on_day_off", 90, "Domingo", day_type=None, direction="surplus")],
    )

    body = client.get(
        "/monitor/diario",
        params={"dia": DAY.isoformat()},
        headers={"Authorization": f"Bearer {issue_token()}"},
    ).json()

    assert body["scheduled"] == 0
    assert body["off_roster"] == 6
    assert body["rows"][0]["day_type"] is None


def test_the_totals_are_the_units_and_nothing_else(client: TestClient, issue_token, answer):
    answer(
        [
            unit_row(scheduled=20, with_indication=3, clear=17, off_roster=4),
            unit_row(
                unit_id=None, unit_name=None, scheduled=5, with_indication=1, clear=4, off_roster=0
            ),
        ],
        [],
    )

    body = client.get(
        "/monitor/diario",
        params={"dia": DAY.isoformat()},
        headers={"Authorization": f"Bearer {issue_token()}"},
    ).json()

    assert (body["scheduled"], body["with_indication"], body["clear"], body["off_roster"]) == (
        25,
        4,
        21,
        4,
    )
    assert body["truncated"] is False


def test_a_day_past_the_ceiling_says_so(client: TestClient, issue_token, answer):
    answer(
        [unit_row()],
        [indication("late_entry", -10, f"Pessoa {n}") for n in range(monitor._MAX_ROWS + 1)],
    )

    body = client.get(
        "/monitor/diario",
        params={"dia": DAY.isoformat()},
        headers={"Authorization": f"Bearer {issue_token()}"},
    ).json()

    assert len(body["rows"]) == monitor._MAX_ROWS
    assert body["truncated"] is True


def test_the_unit_cut_reaches_both_queries(client: TestClient, issue_token, answer):
    """A cut honoured by one query and forgotten by the other reads as a bug in
    the numbers: the unit table would count one unit and the list would show
    every unit under it."""
    scope = answer([unit_row()], [])

    client.get(
        "/monitor/diario",
        params={"dia": DAY.isoformat(), "unidade": str(UNIT_ID)},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert len(scope.params) == 2
    assert all(params["unit_id"] == UNIT_ID for params in scope.params)
    assert all(params["dia"] == DAY for params in scope.params)


def test_no_ranking_lives_in_the_sql(client: TestClient, issue_token, answer):
    """`_SEVERITY` is the only place that decides how loud a type is.

    A `case` on `d.type` inside the query would be the same policy in a second
    language — and the one that stops being updated is always the one nobody
    tested.
    """
    for statement in (monitor._UNITS_SQL, monitor._ROWS_SQL):
        assert "critical" not in statement
        assert "attention" not in statement


def test_the_monitor_refuses_an_anonymous_caller(client: TestClient):
    assert client.get("/monitor/diario", params={"dia": DAY.isoformat()}).status_code == 401
