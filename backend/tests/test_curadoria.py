"""A curadoria do mapa origem → unidade.

Três coisas valem teste aqui, e nenhuma delas é o SQL.

A primeira é a conta consolidada: "provisório" tem de ficar **fora** de
`validated`. Somar os dois faz a barra chegar a 100% com metade do trabalho por
fazer, que é o jeito mais eficiente de encerrar uma curadoria pela metade.

A segunda é a ordem da escrita: a permissão é perguntada antes de a transação de
`service_role` abrir, e um id que não é deste cliente não grava linha nenhuma —
a FK de `unit_secullum_map.unit_id` aponta para `app.unit(id)` sem conferir
tenant, então essa recusa é a única coisa entre um id colado à mão e um mapa
entre clientes.

A terceira é a sugestão, que é função pura e por isso é testada como função.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from operax.motor import mapeamento
from server.routers import curadoria

UNIT_A = UUID("55555555-5555-4555-8555-555555555551")
UNIT_B = UUID("55555555-5555-4555-8555-555555555552")
COMPANY = UUID("66666666-6666-4666-8666-666666666661")


def unit(unit_id: UUID, code: str, name: str) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "code": code,
        "name": name,
        "company_id": COMPANY,
        "company_name": "FastPark Norte",
    }


UNITS = [unit(UNIT_A, "AER01", "Aeroporto 01"), unit(UNIT_B, "SHN", "Shopping Norte")]


def row(**overrides: Any) -> dict[str, Any]:
    return {
        "secullum_department_id": 101,
        "department": "Estac. AEROPORTO-01",
        "company_id": COMPANY,
        "company_name": "FastPark Norte",
        "employees": 12,
        "unmapped": 12,
        "unit_id": None,
        "unit_name": None,
        "validated_at": None,
    } | overrides


class StubScope:
    """Answers by what the statement is about, not by call order."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self._answers = answers
        self.statements: list[str] = []
        self.params: list[Any] = []
        self._current: Any = None

    async def execute(self, statement: str, params: Any = None) -> None:
        self.statements.append(statement)
        self.params.append(params)
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
        rows: list[dict[str, Any]] | None = None,
        summary: dict[str, Any] | None = None,
        admin: bool = True,
        gravado: list[dict[str, Any]] | None = None,
        movidos: list[dict[str, Any]] | None = None,
    ) -> tuple[StubScope, StubScope]:
        scope = StubScope(
            {
                "util.is_admin": {"admin": admin},
                "from app.unit u": UNITS,
                "from app.department d": rows if rows is not None else [row()],
                "from app.employee e": summary
                or {"active": 40, "without_unit": 12, "provisional": 6},
            }
        )
        bound = StubScope(
            {
                "insert into app.unit_secullum_map": (
                    gravado if gravado is not None else [{"secullum_department_id": 101}]
                ),
                "update app.employee e": movidos if movidos is not None else [{"id": uuid4()}],
                "insert into app.audit_log": [],
            }
        )
        monkeypatch.setattr(curadoria, "user_scope", lambda _c: StubScopeContext(scope))
        monkeypatch.setattr(curadoria, "tenant_scope", lambda _c: StubScopeContext(bound))
        return scope, bound

    return install


def _get(client: TestClient, token: str):
    return client.get("/curadoria/unidades", headers={"Authorization": f"Bearer {token}"})


def _post(client: TestClient, token: str, mappings: list[dict[str, Any]]):
    return client.post(
        "/curadoria/unidades",
        json={"mappings": mappings},
        headers={"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------------------
# A conta consolidada
# ---------------------------------------------------------------------------
def test_o_provisorio_fica_fora_do_validado(client: TestClient, issue_token, answer):
    """40 ativos, 12 sem unidade e 6 num mapa que ninguém confirmou = 22 curados.

    Se `provisional` entrasse em `validated`, a tela diria 28 de 40 e a barra
    ficaria a seis pessoas do fim com seis mapeamentos por conferir.
    """
    answer(summary={"active": 40, "without_unit": 12, "provisional": 6})

    body = _get(client, issue_token()).json()

    assert (body["active"], body["without_unit"], body["provisional"]) == (40, 12, 6)
    assert body["validated"] == 22
    assert body["validated"] + body["provisional"] + body["without_unit"] == body["active"]


def test_a_sugestao_nao_e_oferecida_para_o_que_ja_foi_curado(
    client: TestClient, issue_token, answer
):
    """Oferecer alternativa a uma decisão humana é convidar a desfazê-la sem querer."""
    answer(
        rows=[
            row(),
            row(
                secullum_department_id=102,
                department="Shopping Norte",
                unit_id=UNIT_B,
                unit_name="Shopping Norte",
                validated_at=datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
            ),
        ]
    )

    linhas = _get(client, issue_token()).json()["rows"]

    assert linhas[0]["suggestion"]["unit_name"] == "Aeroporto 01"
    assert linhas[1]["suggestion"] is None


# ---------------------------------------------------------------------------
# A escrita
# ---------------------------------------------------------------------------
def test_quem_nao_e_admin_nao_chega_na_transacao_de_escrita(
    client: TestClient, issue_token, answer
):
    """403 antes de o `service_role` abrir, e não depois.

    A transação de escrita ignora RLS de propósito, porque a auditoria precisa
    commitar junto. O que a mantém honesta é a permissão ser perguntada antes.
    """
    _, bound = answer(admin=False)

    response = _post(
        client, issue_token(), [{"secullum_department_id": 101, "unit_id": str(UNIT_A)}]
    )

    assert response.status_code == 403
    assert bound.statements == []


def test_um_id_de_outro_cliente_nao_grava_mapa_nenhum(client: TestClient, issue_token, answer):
    """Zero linha do insert é a recusa: a FK do mapa não confere tenant."""
    answer(gravado=[])

    response = _post(
        client, issue_token(), [{"secullum_department_id": 999, "unit_id": str(UNIT_A)}]
    )

    assert response.status_code == 422
    assert "não pertencem a este cliente" in response.json()["detail"]


def test_o_lote_devolve_quantos_mapas_e_quanta_gente_andou(client: TestClient, issue_token, answer):
    answer(movidos=[{"id": uuid4()} for _ in range(12)])

    body = _post(
        client,
        issue_token(),
        [
            {"secullum_department_id": 101, "unit_id": str(UNIT_A)},
            {"secullum_department_id": 102, "unit_id": str(UNIT_B)},
        ],
    ).json()

    assert body == {"validated": 2, "employees_allocated": 24}


def test_cada_validacao_deixa_trilha(client: TestClient, issue_token, answer):
    _, bound = answer()

    _post(client, issue_token(), [{"secullum_department_id": 101, "unit_id": str(UNIT_A)}])

    assert sum("app.audit_log" in stmt for stmt in bound.statements) == 1


def test_a_unidade_alocada_sai_do_mapa_e_nao_do_pedido():
    """Alocar a partir do corpo do pedido puliria a validação que acabou de rodar."""
    assert "set unit_id = m.unit_id" in mapeamento.ALLOCATE_SQL
    assert "%(unit_id)s" not in mapeamento.ALLOCATE_SQL


def test_a_alocacao_nao_move_quem_ja_tem_unidade():
    """Curar o mapa não desfaz alocação que uma pessoa fez — a mesma regra da promoção."""
    assert "e.unit_id is null" in mapeamento.ALLOCATE_SQL


def test_a_curadoria_recusa_um_chamador_anonimo(client: TestClient):
    assert client.get("/curadoria/unidades").status_code == 401


# ---------------------------------------------------------------------------
# A sugestão, como função
# ---------------------------------------------------------------------------
def test_a_semelhanca_atravessa_acento_caixa_e_pontuacao():
    # "Estac. AEROPORTO-01" e "Aeroporto 01" são o mesmo lugar escrito por duas
    # pessoas diferentes, e é esse o caso que a tela existe para resolver.
    assert mapeamento.normalise("Estac. AEROPORTO-01") == "estac aeroporto 01"
    assert mapeamento.normalise("Manutenção — Térreo") == "manutencao terreo"


def test_a_sugestao_e_a_unidade_mais_parecida():
    palpite = mapeamento.suggest("Estac. AEROPORTO-01", UNITS)

    assert palpite is not None
    assert palpite.unit_name == "Aeroporto 01"
    assert palpite.confidence >= mapeamento.MIN_CONFIDENCE


def test_o_codigo_da_unidade_tambem_conta_como_nome():
    """A origem às vezes escreve o código, não o nome."""
    palpite = mapeamento.suggest("AER01", UNITS)

    assert palpite is not None
    assert palpite.unit_id == str(UNIT_A)


def test_um_nome_que_nao_parece_com_nada_nao_recebe_palpite():
    """Sugestão fraca atrapalha mais do que ajuda: ela vira o clique automático."""
    assert mapeamento.suggest("Departamento 4471", UNITS) is None


def test_a_semelhanca_e_por_palavra_e_nao_por_letra():
    """Letra a letra, "Departamento 4471" e "Aeroporto 01" passam de 45%.

    Vogais em comum bastam, e o palpite errado chega à tela com meio termômetro
    do lado. Por palavra, nenhuma delas encontra par e o resultado é zero.
    """
    assert mapeamento.score("Departamento 4471", "Aeroporto 01") == 0
    assert mapeamento.score("Estac. AEROPORTO-01", "Aeroporto 01") == 80


def test_erro_de_digitacao_ainda_encontra_a_unidade():
    """ "aeroport" e "aeroporto" são a mesma palavra; "aeroporto" e "operacao" não."""
    assert mapeamento.score("Aeroport 01", "Aeroporto 01") == 100
    assert mapeamento.score("Operacao", "Aeroporto") == 0


def test_a_sugestao_nao_muda_entre_duas_aberturas_da_tela():
    """Empate resolvido pela ordem de chegada, que é estável."""
    gemeas = [unit(UNIT_A, "X1", "Portaria"), unit(UNIT_B, "X2", "Portaria")]

    primeira = mapeamento.suggest("Portaria", gemeas)
    segunda = mapeamento.suggest("Portaria", gemeas)

    assert primeira is not None and primeira.unit_id == str(UNIT_A)
    assert primeira == segunda


# ---------------------------------------------------------------------------
# A fila de rotação — o mesmo formato, e uma diferença que muda o escopo
# ---------------------------------------------------------------------------
NOTURNO = {
    "secullum_schedule_id": 9042,
    "cycle_length_days": 2,
    "anchor_date": "2026-08-10",
    "expected_entry": "19:00:00",
    "expected_exit": "05:00:00",
    "expected_break_minutes": 72,
    "workload_minutes": 528,
    "tolerance_extra_minutes": 10,
    "tolerance_absence_minutes": 5,
}


def rotation_row(**overrides: Any) -> dict[str, Any]:
    return {
        "secullum_schedule_id": 9042,
        "schedule": "U-042 - P01 - 19h as 7h - Impar",
        "employees": 3,
        "cycle_length_days": None,
        "anchor_date": None,
        "expected_entry": None,
        "expected_exit": None,
        "expected_break_minutes": None,
        "workload_minutes": None,
        "tolerance_extra_minutes": None,
        "tolerance_absence_minutes": None,
        "validated_at": None,
        "observed_days": [],
    } | overrides


@pytest.fixture
def answer_rotacao(monkeypatch: pytest.MonkeyPatch):
    def install(
        rows: list[dict[str, Any]] | None = None,
        summary: dict[str, Any] | None = None,
        admin: bool = True,
        gravado: list[dict[str, Any]] | None = None,
        cobertos: int = 3,
        fora: int = 3,
    ) -> tuple[StubScope, StubScope]:
        scope = StubScope({"util.is_admin": {"admin": admin}})
        bound = StubScope(
            {
                "observed_days": rows if rows is not None else [rotation_row()],
                "on_blank_schedule": summary
                or {"on_blank_schedule": 13, "validated": 4, "provisional": 2},
                "insert into app.schedule_rotation_map": (
                    gravado if gravado is not None else [{"secullum_schedule_id": 9042}]
                ),
                "count(*)::int as employees": {"employees": cobertos},
                "set exception_tracking": [{"id": uuid4()} for _ in range(fora)],
                "insert into app.audit_log": [],
            }
        )
        monkeypatch.setattr(curadoria, "user_scope", lambda _c: StubScopeContext(scope))
        monkeypatch.setattr(curadoria, "tenant_scope", lambda _c: StubScopeContext(bound))
        return scope, bound

    return install


def _get_rot(client: TestClient, token: str):
    return client.get("/curadoria/rotacoes", headers={"Authorization": f"Bearer {token}"})


def _post_rot(client: TestClient, token: str, corpo: dict[str, Any]):
    return client.post(
        "/curadoria/rotacoes", json=corpo, headers={"Authorization": f"Bearer {token}"}
    )


def test_a_fila_de_rotacao_nao_le_o_espelho_como_o_usuario(
    client: TestClient, issue_token, answer_rotacao
):
    """`secullum` não tem `usage` para `authenticated`: a leitura sai do tenant_scope.

    O que a mantém honesta é a ordem — `util.is_admin` é perguntado como o
    usuário, e só então o `service_role` abre. O teste afirma a ordem, que é o
    que se pode afirmar sem banco.
    """
    scope, bound = answer_rotacao()

    body = _get_rot(client, issue_token()).json()

    assert any("util.is_admin" in stmt for stmt in scope.statements)
    assert all("secullum" not in stmt for stmt in scope.statements)
    assert any('secullum."Horario"' in stmt for stmt in bound.statements)
    assert body["on_blank_schedule"] == 13


def test_a_rotacao_provisoria_fica_fora_do_validado(
    client: TestClient, issue_token, answer_rotacao
):
    """Aqui somar os dois é pior que na fila de unidade.

    Rotação provisória o motor **não lê** — `jornada.py` exige `validated_at`.
    Contá-la como pronta esconderia gente que segue em confiança 0, fora da
    medição do G4 e sem ninguém saber.
    """
    answer_rotacao(summary={"on_blank_schedule": 13, "validated": 4, "provisional": 2})

    body = _get_rot(client, issue_token()).json()

    assert (body["validated"], body["provisional"]) == (4, 2)
    assert body["validated"] + body["provisional"] < body["on_blank_schedule"]


def test_a_fila_mostra_os_dias_batidos_e_nao_conclui_a_ancora(
    client: TestClient, issue_token, answer_rotacao
):
    """O dado vai para a tela; a conclusão fica com quem cura.

    Escala derivada das batidas encaixa sempre, e escala que encaixa sempre
    nunca produz `no_punches` nem `punch_on_day_off`. Por isso a resposta tem
    `observed_days` e não tem campo de âncora sugerida.
    """
    answer_rotacao(rows=[rotation_row(observed_days=["2026-08-10", "2026-08-12"])])

    linha = _get_rot(client, issue_token()).json()["rows"][0]

    assert linha["observed_days"] == ["2026-08-10", "2026-08-12"]
    assert linha["anchor_date"] is None
    assert "suggested_anchor" not in linha


def test_quem_nao_e_admin_nao_declara_escala(client: TestClient, issue_token, answer_rotacao):
    """403 antes de o `service_role` abrir, igual à fila de unidade."""
    _, bound = answer_rotacao(admin=False)

    response = _post_rot(client, issue_token(), NOTURNO)

    assert response.status_code == 403
    assert bound.statements == []


def test_horario_de_outro_cliente_nao_grava_rotacao(
    client: TestClient, issue_token, answer_rotacao
):
    """`secullum_schedule_id` é parte da PK e não tem FK: o join é a única guarda."""
    answer_rotacao(gravado=[])

    response = _post_rot(client, issue_token(), NOTURNO | {"secullum_schedule_id": 999})

    assert response.status_code == 422
    assert "não pertence a este cliente" in response.json()["detail"]


def test_o_turno_que_termina_antes_de_comecar_e_aceito(
    client: TestClient, issue_token, answer_rotacao
):
    """05:00 depois de 19:00 é um turno noturno, não um erro de digitação.

    É como o próprio `HorarioDia` do Secullum declara a virada, e recusar aqui
    tornaria impossível cadastrar exatamente a escala que motivou a tela.
    """
    answer_rotacao(cobertos=3)

    body = _post_rot(client, issue_token(), NOTURNO).json()

    assert body == {"secullum_schedule_id": 9042, "employees_covered": 3}


def test_ciclo_de_um_dia_e_recusado_antes_do_banco(client: TestClient, issue_token, answer_rotacao):
    """Ciclo 1 é "trabalha todo dia", que é semana fixa e não rotação.

    O banco recusa por check; recusar no modelo devolve mensagem em vez de 500.
    """
    _, bound = answer_rotacao()

    response = _post_rot(client, issue_token(), NOTURNO | {"cycle_length_days": 1})

    assert response.status_code == 422
    assert bound.statements == []


def test_cada_rotacao_carimbada_deixa_trilha(client: TestClient, issue_token, answer_rotacao):
    _, bound = answer_rotacao()

    _post_rot(client, issue_token(), NOTURNO)

    assert sum("app.audit_log" in stmt for stmt in bound.statements) == 1


# ---------------------------------------------------------------------------
# A outra resposta para um horário em branco
# ---------------------------------------------------------------------------
def test_tirar_do_motor_escreve_na_pessoa_e_alcanca_pelo_horario(
    client: TestClient, issue_token, answer_rotacao
):
    """Estar fora do motor é do papel; o horário é só como se chega ao conjunto.

    Se o fato ficasse no horário, mover um supervisor para um horário declarado
    o devolveria à medição sem ninguém ter decidido isso.
    """
    _, bound = answer_rotacao(fora=6)

    body = client.post(
        "/curadoria/fora-do-motor",
        json={"secullum_schedule_id": 9042, "exception_tracking": True},
        headers={"Authorization": f"Bearer {issue_token()}"},
    ).json()

    assert body == {"secullum_schedule_id": 9042, "employees_changed": 6}
    escrita = next(stmt for stmt in bound.statements if "exception_tracking" in stmt)
    assert "update app.employee" in escrita
    assert 'h."HorarioId" = %(secullum_schedule_id)s' in escrita


def test_nada_a_mudar_nao_e_erro(client: TestClient, issue_token, answer_rotacao):
    """Zero linha aqui é "já estavam", e transformar isso em 422 seria mentira.

    Diferente da gravação da rotação: lá zero linha só acontece com um horário
    de outro cliente, e é recusa. Aqui os dois casos deixam o banco igual.
    """
    answer_rotacao(fora=0)

    response = client.post(
        "/curadoria/fora-do-motor",
        json={"secullum_schedule_id": 9042, "exception_tracking": True},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert response.status_code == 200
    assert response.json()["employees_changed"] == 0


def test_quem_nao_e_admin_nao_tira_ninguem_do_motor(
    client: TestClient, issue_token, answer_rotacao
):
    _, bound = answer_rotacao(admin=False)

    response = client.post(
        "/curadoria/fora-do-motor",
        json={"secullum_schedule_id": 9042, "exception_tracking": True},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert response.status_code == 403
    assert bound.statements == []
