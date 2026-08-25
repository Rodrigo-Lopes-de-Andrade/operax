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
