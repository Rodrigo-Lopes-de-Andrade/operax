"""A justificativa de uma ocorrência — sempre `pending` desde a P1.2.

A migration 23 abriu `app.justification.status`; a P1.1 acrescentou `pending`;
a P1.2 tirou `status` do corpo da rota: quem explica não decide, e a decisão é
da alçada (`public.fn_revisar_justificativa`, provada no `98`). Estes testes
cobrem a porta, e o que vale testar aqui não é o SQL.

A primeira coisa é a ORDEM: a autorização é a RLS lendo o evento como o usuário,
e ela acontece ANTES de a transação de `service_role` abrir. Um evento que a
policy não devolve não pode gravar linha nenhuma — `justification.employee_id`
tem FK para `app.employee(id)` sem conferir tenant, então essa recusa é a única
coisa entre um id colado à mão e uma justificativa escrita sobre a pessoa de
outro cliente.

A segunda é que a justificativa é escrita com o `employee_id` e a data que vieram
do EVENTO, nunca do corpo do pedido. O cliente manda texto; quem a ocorrência é,
quem responde é o banco.

A terceira é que o estado não é do cliente: nasce `pending`, e um corpo que ainda
traga `status` é recusado (422), nunca ignorado em silêncio.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from server.routers import justificativas

EVENT = UUID("77777777-7777-4777-8777-777777777771")
EMPLOYEE = UUID("88888888-8888-4888-8888-888888888881")
JUSTIFICATION = UUID("99999999-9999-4999-8999-999999999991")


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
    # `...` é o sentinela de "não me passaram nada"; `None` é a resposta que
    # importa testar — a RLS devolvendo zero linha.
    def install(
        evento: dict[str, Any] | None = ...,  # type: ignore[assignment]
        gravado: dict[str, Any] | None = ...,  # type: ignore[assignment]
    ) -> tuple[StubScope, StubScope]:
        scope = StubScope(
            {
                "from app.deviation_event d": (
                    evento
                    if evento is not ...
                    else {
                        "id": EVENT,
                        "employee_id": EMPLOYEE,
                        "reference_date": date(2026, 8, 20),
                        "type": "late_entry",
                        "employee_name": "Ana Ribeiro",
                    }
                )
            }
        )
        bound = StubScope(
            {
                "insert into app.justification": (
                    {"id": JUSTIFICATION, "created_at": None} if gravado is ... else gravado
                ),
                "insert into app.audit_log": [],
            }
        )
        monkeypatch.setattr(justificativas, "user_scope", lambda _c: StubScopeContext(scope))
        monkeypatch.setattr(justificativas, "tenant_scope", lambda _c: StubScopeContext(bound))
        return scope, bound

    return install


def _post(client: TestClient, token: str, event: UUID = EVENT, **body: Any):
    return client.post(
        f"/ocorrencias/{event}/justificativa",
        json={"text": "Atendimento externo autorizado pelo gestor."} | body,
        headers={"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------------------
# A ordem: a policy responde antes de `service_role` abrir transação
# ---------------------------------------------------------------------------
def test_evento_que_a_rls_nao_devolve_nao_grava_nada(client: TestClient, issue_token, answer):
    """404, e nenhuma linha — nem justificativa, nem auditoria.

    A FK de `justification.employee_id` aponta para `app.employee(id)` sem
    conferir tenant. Se a gravação abrisse antes desta pergunta, um id de outro
    cliente colado na URL escreveria um veredito sobre a pessoa dele.
    """
    _, bound = answer(evento=None)

    resposta = _post(client, issue_token())

    assert resposta.status_code == 404
    assert bound.statements == []


def test_a_recusa_nao_distingue_inexistente_de_alheio(client: TestClient, issue_token, answer):
    """Duas frases diferentes contariam ao supervisor o que há fora da unidade dele."""
    answer(evento=None)

    detalhe = _post(client, issue_token(), event=uuid4()).json()["detail"]

    assert detalhe == justificativas._FORA_DE_ALCANCE


# ---------------------------------------------------------------------------
# Quem a ocorrência é, quem responde é o banco
# ---------------------------------------------------------------------------
def test_a_pessoa_e_a_data_saem_do_evento(client: TestClient, issue_token, answer):
    """O corpo manda só texto. Quem é a pessoa e qual é o dia, o evento diz."""
    _, bound = answer()

    resposta = _post(client, issue_token())

    assert resposta.status_code == 201
    gravado = bound.params[0]
    assert gravado["employee_id"] == str(EMPLOYEE)
    assert gravado["reference_date"] == date(2026, 8, 20)
    assert resposta.json()["employee_name"] == "Ana Ribeiro"


def test_o_pedido_nao_escolhe_a_pessoa(client: TestClient, issue_token, answer):
    """Aceitar `employee_id` do cliente seria aceitar que ele escolha sobre quem a
    justificativa recai. Desde a P1.2 o campo nem é ignorado: é recusado."""
    _, bound = answer()

    resposta = _post(
        client,
        issue_token(),
        employee_id=str(uuid4()),
        reference_date="1999-01-01",
    )

    assert resposta.status_code == 422
    assert bound.statements == []


def test_a_justificativa_vira_linha_de_auditoria(client: TestClient, issue_token, answer):
    """Sem a trilha, "quem explicou o atraso da Ana" não tem resposta."""
    _, bound = answer()

    _post(client, issue_token(), text="Sem autorização registrada.")

    assert "insert into app.audit_log" in bound.statements[1]
    depois = bound.params[1]["depois"].obj
    assert depois["status"] == "pending"
    assert depois["deviation_event_id"] == str(EVENT)


# ---------------------------------------------------------------------------
# O estado não é do cliente
# ---------------------------------------------------------------------------
def test_a_justificativa_nasce_pending(client: TestClient, issue_token, answer):
    """Quem explica não decide: o SQL grava `pending`, e a resposta diz isso."""
    _, bound = answer()

    resposta = _post(client, issue_token())

    assert resposta.status_code == 201
    assert resposta.json()["status"] == "pending"
    assert "'pending'" in bound.statements[0]
    assert "status" not in bound.params[0]


@pytest.mark.parametrize("valor", ["accepted", "rejected", "pending"])
def test_corpo_com_status_e_recusado(client: TestClient, issue_token, answer, valor: str):
    """Cliente antigo mandando `status` recebe 422 — ignorar calado deixaria o
    supervisor achando que aprovou. E nada é gravado."""
    _, bound = answer()

    assert _post(client, issue_token(), status=valor).status_code == 422
    assert bound.statements == []


def test_texto_vazio_e_recusado(client: TestClient, issue_token, answer):
    """Justificativa sem texto é a explicação sem a explicação."""
    answer()

    assert _post(client, issue_token(), text="").status_code == 422


def test_token_de_usuario_apagado_nao_grava_veredito_sem_autor(
    client: TestClient, issue_token, answer
):
    """O `insert ... select` não escreve linha se o id não estiver em `auth.users`.

    Não é caso impossível: um usuário apagado no painel mantém o JWT válido até
    expirar. Gravar mesmo assim deixaria um veredito sem autor, que é pior do que
    não gravar.
    """
    _, bound = answer(gravado=None)

    resposta = _post(client, issue_token())

    assert resposta.status_code == 401
    assert not any("audit_log" in s for s in bound.statements)
