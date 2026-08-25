"""Individual consultation: the order that keeps the punches honest.

One thing here is worth a test and it is not the SQL. `app.batida_marcacao`
keys the person by a uuid of the mirror, and `secullum` is revoked from
`authenticated` at the schema level, so the punch query cannot run as the user —
it runs as `service_role`, which ignores RLS. What makes that safe is sequence:
the policies answer first, and a person they did not return is a 404 that never
reaches the second scope.

So the test is that the 404 happens *before* the punches are fetched, not merely
that a 404 happens. Both scopes are stubbed; what the policies actually return is
proved by the isolation suite, in SQL, against real policies.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from server.routers import employees

DE = date(2026, 8, 1)
ATE = date(2026, 8, 22)
READ_AT = datetime(2026, 8, 22, 9, 15, tzinfo=UTC)
EMPLOYEE_ID = UUID("44444444-4444-4444-8444-444444444444")

_EMPLOYEE = {
    "employee_id": EMPLOYEE_ID,
    "name": "Alice",
    "registration_number": "1042",
    "cargo": "Operadora",
    "status": "active",
    "hired_on": date(2024, 3, 1),
    "employment_type": "clt",
    "unit_name": "Shopping Norte",
    "company_name": "FastPark Norte",
    "department_name": "Operação",
    "manager_name": "Bruno",
}
_INDICATORS = {
    "events": 2,
    "minutes_abs": 40,
    "minutes_balance": -40,
    "days_with_deviation": 2,
    "pending_cycle": 1,
}
_DOMAINS = {"compensation": False, "pii": False, "health": False}


def punch(**overrides: Any) -> dict[str, Any]:
    return {
        "reference_date": date(2026, 8, 21),
        "column_type": "Entrada",
        "column_index": 1,
        "punched_at": time(8, 12),
        "status_label": None,
        "expected_time": time(8, 0),
        "disregarded": False,
    } | overrides


class StubScope:
    """Answers by what the statement is about, not by call order."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self._answers = answers
        self.statements: list[str] = []
        self._current: Any = None

    async def execute(self, statement: str, params: Any = None) -> None:
        self.statements.append(statement)
        self._current = next(
            (value for marker, value in self._answers.items() if marker in statement),
            None,
        )

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._current or []

    async def fetchone(self) -> dict[str, Any] | None:
        return self._current


class StubScopeContext:
    def __init__(self, scope: StubScope) -> None:
        self._scope = scope

    async def __aenter__(self) -> StubScope:
        return self._scope

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.fixture
def answer(monkeypatch: pytest.MonkeyPatch):
    def install(
        employee: dict[str, Any] | None = _EMPLOYEE,
        punches: list[dict[str, Any]] | None = None,
        read_at: datetime | None = READ_AT,
        mirror_present: bool = True,
    ) -> tuple[StubScope, StubScope]:
        scope = StubScope(
            {
                "from app.employee c": employee,
                "as days_with_deviation": _INDICATORS,
                "group by d.type": [],
                "from app.expected_workday w": [],
                "from app.justification j": [],
                "util.can_see_domain": _DOMAINS,
            }
        )
        bound = StubScope(
            {
                "from app.batida_marcacao m": punches or [],
                "from app.sync_run s": {
                    "read_at": read_at,
                    "mirror_present": mirror_present,
                },
            }
        )
        monkeypatch.setattr(employees, "user_scope", lambda _c: StubScopeContext(scope))
        monkeypatch.setattr(employees, "tenant_scope", lambda _c: StubScopeContext(bound))
        return scope, bound

    return install


def _get(client: TestClient, token: str, employee_id: UUID = EMPLOYEE_ID):
    return client.get(
        f"/colaboradores/{employee_id}",
        params={"de": DE.isoformat(), "ate": ATE.isoformat()},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_quem_a_policy_nao_devolve_nunca_chega_na_consulta_de_marcacao(
    client: TestClient, issue_token, answer
):
    """404 antes do `service_role`, e não depois.

    Esta é a asserção inteira do desenho: a segunda consulta ignora RLS, então
    ela só pode existir depois que a primeira já autorizou. Se um dia alguém
    mover o bloco de marcações para cima, este teste fica vermelho — e é a única
    coisa entre esse refactor e um vazamento entre unidades.
    """
    _, bound = answer(employee=None)

    response = _get(client, issue_token(), uuid4())

    assert response.status_code == 404
    assert bound.statements == []


def test_a_coluna_vazia_com_previsto_e_uma_linha_que_precisa_aparecer(
    client: TestClient, issue_token, answer
):
    """Marcação faltante é `Memoria` presente e `hora` nula — e é o caso do dia.

    Devolver só as colunas preenchidas transformaria a falta em ausência de
    linha, que na tela é indistinguível de "o dia não tinha essa marcação".
    """
    answer(
        punches=[
            punch(),
            punch(column_type="Saida", column_index=1, punched_at=None, expected_time=time(17, 0)),
        ]
    )

    body = _get(client, issue_token()).json()

    assert len(body["punches"]) == 2
    faltante = body["punches"][1]
    assert faltante["punched_at"] is None
    assert faltante["expected_time"] == "17:00:00"
    assert body["punches_read_at"] == READ_AT.isoformat().replace("+00:00", "Z")


def test_sem_leitura_nenhuma_a_lista_vazia_nao_afirma_que_ninguem_bateu(
    client: TestClient, issue_token, answer
):
    answer(punches=[], read_at=None)

    body = _get(client, issue_token()).json()

    assert body["punches"] == []
    assert body["punches_read_at"] is None


def test_a_marcacao_desconsiderada_chega_marcada_em_vez_de_sumir(
    client: TestClient, issue_token, answer
):
    """Ela não conta e não pode desaparecer: sumir esconde a curadoria da origem."""
    answer(punches=[punch(disregarded=True)])

    body = _get(client, issue_token()).json()

    assert body["punches"][0]["disregarded"] is True


def test_sem_o_espelho_no_banco_a_consulta_responde_sem_marcacoes(
    client: TestClient, issue_token, answer
):
    """O mesmo desfecho do monitor, pelo mesmo motivo, na outra tela."""
    _, bound = answer(punches=[punch()], mirror_present=False)

    response = _get(client, issue_token())

    assert response.status_code == 200
    assert response.json()["punches"] == []
    assert response.json()["punches_read_at"] is None
    assert not any("app.batida_marcacao m" in statement for statement in bound.statements)


def test_a_consulta_individual_recusa_um_chamador_anonimo(client: TestClient):
    response = client.get(
        f"/colaboradores/{EMPLOYEE_ID}",
        params={"de": DE.isoformat(), "ate": ATE.isoformat()},
    )
    assert response.status_code == 401
