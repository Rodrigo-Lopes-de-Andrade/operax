"""A alçada no FastAPI — a fila e a revisão (P1.3).

O SQL é provado no `98` (a fila: janela 21→20, filtros, escopo e tenant; a RPC:
as nove recusas) e no `80` (a janela contra `dp/ciclo.py`). Aqui fica o que a
rota decide: quem recebe 403 antes de a fila rodar, que as duas portas rodam
como o usuário, que os filtros chegam à RPC como vieram, que cada recusa vira o
status declarado com o código em `detail`, e que o corpo é fechado.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from operax.core.tenant import TenantContext, UserRole
from operax.motor import relogio
from server.deps import get_membership_resolver
from server.main import app
from server.routers import alcada
from tests.conftest import TENANT_ID
from tests.test_canais_credencial import StubScope, StubScopeContext
from tests.test_canais_templates import _TriggerRefusal

JUSTIFICATION = UUID("a1ca0000-0000-4000-8000-000000000001")
EMPLOYEE = UUID("a1ca0000-0000-4000-8000-000000000002")
UNIT = UUID("a1ca0000-0000-4000-8000-000000000003")
REVIEW = UUID("a1ca0000-0000-4000-8000-000000000004")

QUEUE_ROW = {
    "justification_id": JUSTIFICATION,
    "employee_id": EMPLOYEE,
    "employee_name": "Ana Ribeiro",
    "unit_id": UNIT,
    "unit_name": "Centro",
    "reference_date": date(2026, 11, 21),
    "type": "late_entry",
    "type_description": "Entrada após o previsto",
    "minutes": -17,
    "text": "Consulta médica",
    "author_name": "Supervisor Centro",
    "created_at": datetime(2026, 11, 21, 12, 0),
    "can_review": True,
    "blocked_reason": None,
}

HR_OR_OWNER = {UserRole.HR, UserRole.OWNER}

WINDOW = {"period_start": date(2026, 12, 21), "period_end": date(2027, 1, 20)}


@pytest.fixture
def as_role():
    """Troca o papel da membership — e é ele que o stub de `util.roles_in_tenant`
    responde, como o banco responderia."""

    def install(role: UserRole) -> None:
        async def membership(user_id: UUID) -> TenantContext:
            return TenantContext(tenant_id=TENANT_ID, user_id=user_id, role=role)

        app.dependency_overrides[get_membership_resolver] = lambda: membership

    return install


#: 02:30 UTC de 21/12/2026 é 23:30 de 20/12 em São Paulo: o "hoje" do tenant
#: é 20/12, e o do container seria 21/12 — outra competência.
AGORA_UTC = datetime(2026, 12, 21, 2, 30, tzinfo=UTC)


class _Relogio(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
        return AGORA_UTC.astimezone(tz)


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch):

    def install(
        *, allowed: bool = True, queue: list[dict[str, Any]] | None = None, review: Any = None
    ) -> tuple[StubScope, StubScopeContext]:
        user = StubScope(
            {
                "util.roles_in_tenant": {"allowed": allowed},
                "from app.unit u": {"timezone": "America/Sao_Paulo"},
                "util.competencia_de": {"period_year": 2027, "period_month": 1},
                "util.competencia_janela": WINDOW,
                "fn_fila_aprovacao": queue if queue is not None else [QUEUE_ROW],
                "fn_revisar_justificativa": (
                    review if review is not None else {"review_id": REVIEW}
                ),
            }
        )
        # O `UserScope` de verdade carrega o contexto do token; o relógio lê dele.
        user.context = SimpleNamespace(tenant_id=TENANT_ID)  # type: ignore[attr-defined]
        ctx = StubScopeContext(user)
        monkeypatch.setattr(alcada, "user_scope", lambda _t: ctx)
        monkeypatch.setattr(relogio, "datetime", _Relogio)

        # Uma requisição, uma conexão: um `tenant_scope` aberto por baixo da
        # transação do usuário seria a segunda conexão que esgota o pool.
        def segunda_conexao(*_: Any, **__: Any) -> Any:
            raise AssertionError("tenant_scope aberto dentro de uma rota da alçada")

        monkeypatch.setattr(relogio, "tenant_scope", segunda_conexao)
        return user, ctx

    return install


@pytest.fixture
def cabecalho(issue_token: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token()}"}


def _relogio_lido(user: StubScope) -> bool:
    return any("from app.unit u" in s for s in user.statements)


def _fila_statements(user: StubScope) -> list[str]:
    return [s for s in user.statements if "fn_fila_aprovacao" in s]


def _params(user: StubScope, marker: str) -> Any:
    (params,) = [p for s, p in zip(user.statements, user.params, strict=True) if marker in s]
    return params


# ---------------------------------------------------------------------------
# GET /alcada/fila
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", sorted(set(UserRole) - HR_OR_OWNER))
def test_quem_nao_e_rh_nem_owner_recebe_403_e_a_fila_nao_roda(
    client: TestClient, cabecalho: dict[str, str], db, as_role, role: UserRole
):
    """Supervisor, DP, contabilidade e o resto: 403 — não uma fila vazia, que
    pareceria "nada para aprovar"."""
    as_role(role)
    user, _ = db(allowed=role in HR_OR_OWNER)

    resposta = client.get("/alcada/fila?ano=2026&mes=12", headers=cabecalho)

    assert resposta.status_code == 403
    assert resposta.json() == {"detail": "not_hr"}
    assert _fila_statements(user) == []


def test_o_403_vem_antes_do_relogio_e_da_competencia_corrente(
    client: TestClient, cabecalho: dict[str, str], db, as_role
):
    as_role(UserRole.UNIT_SUPERVISOR)
    user, _ = db(allowed=False)

    resposta = client.get("/alcada/fila", headers=cabecalho)

    assert resposta.status_code == 403
    assert not _relogio_lido(user)
    assert len(user.statements) == 1


@pytest.mark.parametrize("role", sorted(HR_OR_OWNER))
def test_rh_e_owner_recebem_a_fila(
    client: TestClient, cabecalho: dict[str, str], db, as_role, role: UserRole
):
    as_role(role)
    user, ctx = db(allowed=role in HR_OR_OWNER)

    resposta = client.get("/alcada/fila?ano=2026&mes=12", headers=cabecalho)

    assert resposta.status_code == 200
    corpo = resposta.json()["rows"]
    assert [r["justification_id"] for r in corpo] == [str(JUSTIFICATION)]
    assert corpo[0]["employee_name"] == "Ana Ribeiro"
    assert corpo[0]["minutes"] == -17
    # O papel, a janela e a fila numa transação só, como o usuário, papel primeiro.
    assert ctx.opened == 1
    assert "util.roles_in_tenant" in user.statements[0]
    assert user.params[0] == {"tenant_id": TENANT_ID}
    assert "fn_fila_aprovacao" in user.statements[-1]


def test_com_ano_e_mes_a_resposta_traz_a_janela_do_banco(
    client: TestClient, cabecalho: dict[str, str], db
):
    """A janela é a que `util.competencia_janela` devolveu, e o relógio nem é lido."""
    user, _ = db()

    corpo = client.get("/alcada/fila?ano=2027&mes=1", headers=cabecalho).json()

    assert (corpo["ano"], corpo["mes"]) == (2027, 1)
    assert (corpo["period_start"], corpo["period_end"]) == ("2026-12-21", "2027-01-20")
    assert _params(user, "util.competencia_janela") == {"year": 2027, "month": 1}
    assert not [s for s in user.statements if "util.competencia_de" in s]
    assert not _relogio_lido(user)


def test_sem_ano_e_mes_vale_a_competencia_que_contem_hoje_no_relogio_do_tenant(
    client: TestClient, cabecalho: dict[str, str], db
):
    """São 23:30 de 20/12/2026 em São Paulo (02:30 de 21/12 em UTC): o dia vai
    ao banco, e a competência é a que `util.competencia_de` disser — não uma
    conta feita aqui. O fuso é lido NA transação do usuário, filtrado pelo
    tenant do token, e a requisição abre uma conexão só."""
    user, ctx = db()

    corpo = client.get("/alcada/fila", headers=cabecalho).json()

    assert ctx.opened == 1
    assert _params(user, "from app.unit u") == {"tenant_id": TENANT_ID}
    assert _params(user, "util.competencia_de") == {"today": date(2026, 12, 20)}
    assert (corpo["ano"], corpo["mes"]) == (2027, 1)
    assert _params(user, "util.competencia_janela") == {"year": 2027, "month": 1}
    assert _params(user, "fn_fila_aprovacao")["year"] == 2027
    assert _params(user, "fn_fila_aprovacao")["month"] == 1
    assert (corpo["period_start"], corpo["period_end"]) == ("2026-12-21", "2027-01-20")


@pytest.mark.parametrize("query", ["ano=2026", "mes=12"])
def test_ano_sem_mes_ou_mes_sem_ano_e_422_antes_do_banco(
    client: TestClient, cabecalho: dict[str, str], db, query: str
):
    _, ctx = db()

    resposta = client.get(f"/alcada/fila?{query}", headers=cabecalho)

    assert resposta.status_code == 422
    assert ctx.opened == 0


def test_a_linha_bloqueada_continua_na_fila_com_o_motivo(
    client: TestClient, cabecalho: dict[str, str], db
):
    """Decisão do dono (29/09): o RH vê o que não pode revisar, e por quê — o
    código é o mesmo que a revisão devolveria."""
    bloqueada = QUEUE_ROW | {
        "justification_id": uuid4(),
        "can_review": False,
        "blocked_reason": "owner_only",
    }
    db(queue=[QUEUE_ROW, bloqueada])

    corpo = client.get("/alcada/fila?ano=2026&mes=12", headers=cabecalho).json()["rows"]

    assert [(r["can_review"], r["blocked_reason"]) for r in corpo] == [
        (True, None),
        (False, "owner_only"),
    ]


def test_motivo_de_bloqueio_desconhecido_nao_passa_calado(
    client: TestClient, cabecalho: dict[str, str], db
):
    """Um código novo no banco sem par aqui é erro alto, não um bloqueio que a
    tela não sabe nomear."""
    db(queue=[QUEUE_ROW | {"can_review": False, "blocked_reason": "algo_novo"}])

    with pytest.raises(ValidationError):
        client.get("/alcada/fila?ano=2026&mes=12", headers=cabecalho)


def test_os_filtros_chegam_a_rpc_como_vieram(client: TestClient, cabecalho: dict[str, str], db):
    user, _ = db()

    resposta = client.get(
        f"/alcada/fila?ano=2027&mes=1&unidade={UNIT}&colaborador={EMPLOYEE}"
        "&de=2026-12-28&ate=2027-01-05",
        headers=cabecalho,
    )

    assert resposta.status_code == 200
    # A janela da resposta é a do banco, não o recorte do filtro: `de`/`ate` só
    # estreitam as linhas, e a tela limita as datas pela janela inteira.
    assert (resposta.json()["period_start"], resposta.json()["period_end"]) == (
        "2026-12-21",
        "2027-01-20",
    )
    assert _params(user, "fn_fila_aprovacao") == {
        "year": 2027,
        "month": 1,
        "unit_id": UNIT,
        "employee_id": EMPLOYEE,
        "de": date(2026, 12, 28),
        "ate": date(2027, 1, 5),
    }


def test_sem_filtro_opcional_a_rpc_recebe_nulo(client: TestClient, cabecalho: dict[str, str], db):
    user, _ = db()

    client.get("/alcada/fila?ano=2026&mes=12", headers=cabecalho)

    assert _params(user, "fn_fila_aprovacao") == {
        "year": 2026,
        "month": 12,
        "unit_id": None,
        "employee_id": None,
        "de": None,
        "ate": None,
    }


def test_a_rota_nao_manda_tenant_a_fila(client: TestClient, cabecalho: dict[str, str], db):
    """A fila é invoker: o tenant é o da RLS. Um `tenant_id` na chamada seria um
    filtro em que a policy não confia — e a tela acreditaria que ele recorta."""
    user, _ = db()

    client.get("/alcada/fila?ano=2026&mes=12", headers=cabecalho)

    assert "tenant_id" not in _params(user, "fn_fila_aprovacao")
    assert "tenant" not in _fila_statements(user)[0]


@pytest.mark.parametrize(
    "query",
    ["ano=2026&mes=13", "ano=2026&mes=0", "ano=1999&mes=1", "ano=2026&mes=12&de=ontem"],
)
def test_competencia_malformada_e_422_antes_do_banco(
    client: TestClient, cabecalho: dict[str, str], db, query: str
):
    user, ctx = db()

    resposta = client.get(f"/alcada/fila?{query}", headers=cabecalho)

    assert resposta.status_code == 422
    assert ctx.opened == 0


# ---------------------------------------------------------------------------
# POST /alcada/justificativas/{id}/revisao
# ---------------------------------------------------------------------------
def _revisar(client: TestClient, cabecalho: dict[str, str], body: dict[str, Any]):
    return client.post(
        f"/alcada/justificativas/{JUSTIFICATION}/revisao", json=body, headers=cabecalho
    )


def test_aprovar_chama_a_rpc_como_o_usuario(client: TestClient, cabecalho: dict[str, str], db):
    user, ctx = db()

    resposta = _revisar(client, cabecalho, {"decisao": "approved"})

    assert resposta.status_code == 201
    assert resposta.json() == {
        "review_id": str(REVIEW),
        "justification_id": str(JUSTIFICATION),
        "decision": "approved",
    }
    assert ctx.opened == 1
    assert user.params[0] == {
        "justification_id": JUSTIFICATION,
        "decision": "approved",
        "reason": None,
    }


def test_reprovar_leva_o_motivo(client: TestClient, cabecalho: dict[str, str], db):
    user, _ = db()

    resposta = _revisar(client, cabecalho, {"decisao": "rejected", "motivo": "Sem comprovante"})

    assert resposta.status_code == 201
    assert user.params[0]["reason"] == "Sem comprovante"
    assert user.params[0]["decision"] == "rejected"


def test_o_mapeamento_cobre_exatamente_as_nove_recusas():
    """Recusa nova na RPC sem status aqui é 500 — e esta lista é a da migration."""
    assert set(alcada.REVIEW_STATUS) == {
        "not_hr",
        "justification_not_found",
        "own_justification",
        "owner_only",
        "already_reviewed",
        "source_is_mirror",
        "not_pending",
        "no_open_period",
        "rejection_needs_reason",
    }


@pytest.mark.parametrize(
    ("code", "status_code"),
    [
        ("not_hr", 403),
        ("justification_not_found", 404),
        ("own_justification", 403),
        ("owner_only", 403),
        ("already_reviewed", 409),
        ("source_is_mirror", 409),
        ("not_pending", 409),
        ("no_open_period", 409),
        ("rejection_needs_reason", 422),
    ],
)
def test_as_nove_recusas_viram_http_com_o_codigo_no_detail(
    client: TestClient, cabecalho: dict[str, str], db, code: str, status_code: int
):
    db(review=_TriggerRefusal(code))

    resposta = _revisar(client, cabecalho, {"decisao": "rejected", "motivo": "x"})

    assert resposta.status_code == status_code
    assert resposta.json() == {"detail": code}


@pytest.mark.parametrize(
    "role", [UserRole.UNIT_SUPERVISOR, UserRole.PERSONNEL, UserRole.ACCOUNTING]
)
def test_supervisor_dp_e_contabilidade_revisando_recebem_403(
    client: TestClient, cabecalho: dict[str, str], db, as_role, role: UserRole
):
    """Quem decide o papel na revisão é a RPC (definer, `not_hr`); a rota não
    tem uma segunda opinião, e o 403 é o dela."""
    as_role(role)
    db(review=_TriggerRefusal("not_hr"))

    resposta = _revisar(client, cabecalho, {"decisao": "approved"})

    assert resposta.status_code == 403
    assert resposta.json() == {"detail": "not_hr"}


def test_um_p0001_que_nao_e_dos_nove_nao_e_engolido(
    client: TestClient, cabecalho: dict[str, str], db
):
    db(review=_TriggerRefusal("algo_novo"))

    with pytest.raises(_TriggerRefusal):
        _revisar(client, cabecalho, {"decisao": "approved"})


@pytest.mark.parametrize(
    "body",
    [
        {"decisao": "approved", "status": "accepted"},
        {"decisao": "approved", "tenant_id": str(uuid4())},
        {"decisao": "approved", "reviewed_by": str(uuid4())},
        {"decisao": "aprovado"},
        {"decisao": "justified"},
        {"motivo": "sem decisão"},
        {"decisao": "rejected", "motivo": "x" * 2001},
    ],
)
def test_corpo_fora_do_contrato_e_422_e_a_rpc_nao_roda(
    client: TestClient, cabecalho: dict[str, str], db, body: dict[str, Any]
):
    """`extra="forbid"`: um `reviewed_by` ou `tenant_id` no corpo é recusado, não
    ignorado — quem revisa é o `sub` do token, e o tenant é o da linha."""
    _, ctx = db()

    resposta = _revisar(client, cabecalho, body)

    assert resposta.status_code == 422
    assert ctx.opened == 0
