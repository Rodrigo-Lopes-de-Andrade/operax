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
READ_AT = datetime(2026, 8, 22, 9, 15, tzinfo=UTC)
UNIT_ID = UUID("33333333-3333-4333-8333-333333333333")


def unit_row(**overrides: Any) -> dict[str, Any]:
    return {
        "unit_id": UNIT_ID,
        "unit_name": "Shopping Norte",
        "active": 30,
        "scheduled": 20,
        "with_indication": 3,
        "clear": 17,
        "with_punch": 18,
        "without_punch": 2,
        "on_vacation": 2,
        "on_leave": 1,
        "day_off": 4,
        "unrostered": 3,
        "off_roster": 7,
        "exception_tracking": 0,
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

    def __init__(
        self,
        batches: list[list[dict[str, Any]]],
        singles: list[dict[str, Any] | None] | None = None,
    ) -> None:
        self._batches = list(batches)
        self._singles = list(singles or [])
        self.statements: list[str] = []
        self.params: list[Any] = []

    async def execute(self, statement: str, params: Any = None) -> None:
        self.statements.append(statement)
        self.params.append(params)

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._batches.pop(0)

    async def fetchone(self) -> dict[str, Any] | None:
        return self._singles.pop(0)


class StubScopeContext:
    def __init__(self, scope: StubScope) -> None:
        self._scope = scope

    async def __aenter__(self) -> StubScope:
        return self._scope

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.fixture
def answer(monkeypatch: pytest.MonkeyPatch):
    """Queues what each of the two scopes would return, and exposes both.

    There are two because the punches force it: `secullum` is unreachable to
    `authenticated`, so who punched is resolved as `service_role` and only then
    counted inside the statement the policies filter. The stub keeps them apart
    so a test can assert *which* scope was asked what.
    """

    def install(
        units: list[dict[str, Any]],
        rows: list[dict[str, Any]],
        punched: list[UUID] | None = None,
        read_at: datetime | None = READ_AT,
        mirror_present: bool = True,
    ) -> tuple[StubScope, StubScope]:
        bound = StubScope(
            [[{"employee_id": each} for each in (punched or [])]],
            [{"read_at": read_at, "mirror_present": mirror_present}],
        )
        scope = StubScope([units, rows])
        monkeypatch.setattr(monitor, "tenant_scope", lambda _context: StubScopeContext(bound))
        monkeypatch.setattr(monitor, "user_scope", lambda _context: StubScopeContext(scope))
        return scope, bound

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


def test_o_quadro_do_dia_particiona_o_headcount(client: TestClient, issue_token, answer):
    """Ativos = escalados + férias + afastados + folga + sem jornada prevista.

    A identidade é o que faz o quadro ser um quadro e não cinco números soltos.
    Se ela não fechar, alguém está sendo contado duas vezes ou não está sendo
    contado — e as duas leituras erradas são invisíveis sem esta soma.
    """
    answer(
        [
            unit_row(active=30, scheduled=20, on_vacation=2, on_leave=1, day_off=4, unrostered=3),
            unit_row(
                unit_id=None,
                unit_name=None,
                active=9,
                scheduled=5,
                with_indication=1,
                clear=4,
                on_vacation=1,
                on_leave=0,
                day_off=3,
                unrostered=0,
                off_roster=4,
            ),
        ],
        [],
    )

    body = client.get(
        "/monitor/diario",
        params={"dia": DAY.isoformat()},
        headers={"Authorization": f"Bearer {issue_token()}"},
    ).json()

    assert body["active"] == 39
    assert (
        body["scheduled"]
        + body["on_vacation"]
        + body["on_leave"]
        + body["day_off"]
        + body["unrostered"]
        == body["active"]
    )
    assert (body["on_vacation"], body["on_leave"], body["unrostered"]) == (3, 1, 3)


def test_quem_o_motor_nao_materializou_e_contado_em_vez_de_sumir(
    client: TestClient, issue_token, answer
):
    """Uma unidade inteira sem jornada prevista aparece, com o número na cara.

    Antes o quadro saía de `app.expected_workday`, e quem o motor não
    materializou não era escalado, não era folga e não era nada: sumia. Seis
    pessoas da administração estão nesse estado de propósito, e falha de
    cobertura do motor tem exatamente a mesma aparência. Contar é o que separa
    as duas.
    """
    answer(
        [
            unit_row(
                unit_name="Administração",
                active=6,
                scheduled=0,
                with_indication=0,
                clear=0,
                on_vacation=0,
                on_leave=0,
                day_off=0,
                unrostered=6,
                off_roster=0,
            )
        ],
        [],
    )

    body = client.get(
        "/monitor/diario",
        params={"dia": DAY.isoformat()},
        headers={"Authorization": f"Bearer {issue_token()}"},
    ).json()

    assert body["active"] == 6
    assert body["unrostered"] == 6
    assert len(body["units"]) == 1


def test_o_quadro_sai_de_employee_e_nao_da_jornada_prevista(
    client: TestClient, issue_token, answer
):
    """Dirigir pela jornada prevista faz o headcount ser o que o motor cobriu."""
    assert "from app.employee c" in monitor._UNITS_SQL
    assert "left join app.expected_workday w" in monitor._UNITS_SQL


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
    scope, _ = answer([unit_row()], [])

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


def test_com_marcacao_e_sem_marcacao_particionam_os_escalados(
    client: TestClient, issue_token, answer
):
    """A segunda partição da mesma população — e ela não é a primeira.

    `com indício` e `sem indício` respondem o que o motor achou. `com marcação`
    e `sem marcação` respondem o que a última leitura da origem contém, e as
    duas coisas divergem o tempo todo: alguém pode ter batido e ainda assim ter
    indício de atraso.
    """
    answer(
        [
            unit_row(scheduled=20, with_punch=18, without_punch=2),
            unit_row(
                unit_id=None,
                unit_name=None,
                active=9,
                scheduled=5,
                with_indication=1,
                clear=4,
                with_punch=3,
                without_punch=2,
                on_vacation=1,
                on_leave=0,
                day_off=3,
                unrostered=0,
                off_roster=4,
            ),
        ],
        [],
    )

    body = client.get(
        "/monitor/diario",
        params={"dia": DAY.isoformat()},
        headers={"Authorization": f"Bearer {issue_token()}"},
    ).json()

    assert body["with_punch"] + body["without_punch"] == body["scheduled"] == 25
    assert (body["with_punch"], body["without_punch"]) == (21, 4)


def test_quem_bateu_e_contado_dentro_da_consulta_do_usuario(
    client: TestClient, issue_token, answer
):
    """Os ids resolvidos como `service_role` entram como PARÂMETRO, não como conta.

    É o que mantém o recorte de unidade onde ele já está — na policy. Se a
    contagem fosse feita em Python sobre o conjunto devolvido pelo
    `service_role`, um supervisor de uma unidade passaria a contar gente de
    outra, e `util.can_see_employee` estaria escrito duas vezes.
    """
    bateram = [uuid4(), uuid4()]
    scope, bound = answer([unit_row()], [], punched=bateram)

    client.get(
        "/monitor/diario",
        params={"dia": DAY.isoformat()},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert scope.params[0]["punched"] == bateram
    assert "any (%(punched)s::uuid[])" in monitor._UNITS_SQL
    # E o lado que alcança o espelho nunca é o do usuário.
    assert not any("app.batida_marcacao" in stmt for stmt in scope.statements)
    assert any('join secullum."Funcionario" f' in stmt for stmt in bound.statements)


def test_sem_nenhuma_leitura_concluida_os_numeros_nao_afirmam_nada(
    client: TestClient, issue_token, answer
):
    """Zero e "nunca leram" não podem chegar iguais à tela.

    Sem `punches_read_at`, "sem marcação: 20" significaria que vinte pessoas não
    bateram ponto. O que aconteceu foi que ninguém leu a origem — e é a tela que
    decide o que fazer com isso, mas só se o dado disser qual dos dois é.
    """
    answer([unit_row(with_punch=0, without_punch=20)], [], read_at=None)

    body = client.get(
        "/monitor/diario",
        params={"dia": DAY.isoformat()},
        headers={"Authorization": f"Bearer {issue_token()}"},
    ).json()

    assert body["punches_read_at"] is None
    assert body["without_punch"] == 20


def test_a_leitura_das_marcacoes_viaja_junto_da_contagem(client: TestClient, issue_token, answer):
    answer([unit_row()], [])

    body = client.get(
        "/monitor/diario",
        params={"dia": DAY.isoformat()},
        headers={"Authorization": f"Bearer {issue_token()}"},
    ).json()

    assert body["punches_read_at"] == READ_AT.isoformat().replace("+00:00", "Z")


def test_marcacao_desconsiderada_nao_conta_como_marcacao():
    """O motor a ignora, então a tela não pode contá-la.

    Contar aqui e não lá poria "com marcação" ao lado de `no_punches` sobre a
    mesma pessoa, no mesmo cartão.
    """
    from operax.motor import marcacao

    assert "not m.desconsiderada" in marcacao.PUNCHED_EMPLOYEES_SQL
    assert "m.hora is not null" in marcacao.PUNCHED_EMPLOYEES_SQL


def test_sem_o_espelho_no_banco_a_tela_responde_em_vez_de_quebrar(
    client: TestClient, issue_token, answer
):
    """`secullum."Funcionario"` não é criado por migration nenhuma deste repo.

    Migration 03 endurece o espelho que encontrar, e não encontrar nada é um
    desfecho válido: é o estado do banco de desenvolvimento e o de qualquer
    projeto montado só com estas migrations. Nomear uma relação inexistente
    falha no parse — nenhum `case` dentro do SQL salva —, então a consulta não
    pode nem ser emitida. A tela precisa continuar respondendo o resto do dia.
    """
    _, bound = answer([unit_row(with_punch=0, without_punch=20)], [], mirror_present=False)

    response = client.get(
        "/monitor/diario",
        params={"dia": DAY.isoformat()},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert response.status_code == 200
    # Nem a leitura, porque um instante ao lado de dois zeros afirmaria que
    # ninguém bateu quando o que houve foi não haver o que ler.
    assert response.json()["punches_read_at"] is None
    assert not any("from app.batida_marcacao m" in stmt for stmt in bound.statements)


def test_quem_esta_fora_do_motor_por_decisao_nao_conta_como_falha_de_cobertura(
    client: TestClient, issue_token, answer
):
    """As duas situações têm a mesma aparência e significam o oposto.

    `unrostered` é o motor devendo um dia e não o tendo produzido — bug. Quem
    carrega `exception_tracking` foi tirado da medição por uma pessoa: ninguém
    lhe deve jornada. Enquanto os dois dividiam um número, uma falha de
    cobertura se escondia dentro dele parecendo decisão.
    """
    answer(
        [
            unit_row(
                active=30,
                scheduled=20,
                on_vacation=2,
                on_leave=1,
                day_off=4,
                unrostered=1,
                exception_tracking=2,
            )
        ],
        [],
    )

    body = client.get(
        "/monitor/diario",
        params={"dia": DAY.isoformat()},
        headers={"Authorization": f"Bearer {issue_token()}"},
    ).json()

    assert (body["unrostered"], body["exception_tracking"]) == (1, 2)
    # A conta continua fechando com o efetivo — é ela que torna a diferença
    # visível em vez de virar gente que some da tela.
    unidade = body["units"][0]
    assert (
        unidade["scheduled"]
        + unidade["on_vacation"]
        + unidade["on_leave"]
        + unidade["day_off"]
        + unidade["unrostered"]
        + unidade["exception_tracking"]
    ) == unidade["active"]
