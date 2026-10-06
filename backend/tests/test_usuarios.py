"""Usuários do painel no FastAPI — convite, reenvio e lista (U3); detalhe, papel,
escopo, desativar e a matriz de domínios (U4).

O SQL contra o banco de verdade (a RPC como o usuário grava `viewer` com
`invited_by`; a lista não vê outro tenant) está em
`scripts/teste_usuarios_rota.py`. Aqui fica o que a rota decide: quem recebe
403 antes de qualquer leitura, que `ja_e_membro` e o escopo são checados ANTES
do Admin API, que a recusa tardia da RPC não apaga a identidade, que o escopo
da lista respeita o atalho de papel, que os corpos são fechados — e que nada do
que o Admin API devolve chega a uma resposta.

O Admin API é falso no nível do HTTP (`httpx.MockTransport`): o
`SupabaseAuthAdmin` de verdade lê a resposta, e a resposta falsa carrega senha,
link e tokens, como o GoTrue pode carregar. A varredura procura as chaves E os
valores.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from operax.core.tenant import TenantContext, TenantScope, UserRole
from server.deps import get_membership_resolver
from server.main import app
from server.models import SensitiveDomain
from server.routers import usuarios
from tests.conftest import TENANT_ID, USER_ID
from tests.test_canais_credencial import StubScope, StubScopeContext
from tests.test_canais_templates import _TriggerRefusal

NEW_USER = UUID("0c3a0000-0000-4000-8000-000000000001")
EXISTING = UUID("0c3a0000-0000-4000-8000-000000000002")
MEMBER = UUID("0c3a0000-0000-4000-8000-000000000003")
COMPANY = UUID("0c3a0000-0000-4000-8000-0000000000c1")
UNIT = UUID("0c3a0000-0000-4000-8000-0000000000a1")
EMAIL = "nova.pessoa@cliente.com.br"
NAME = "Nova Pessoa"

ADMIN = sorted(usuarios.ADMIN_ROLES)
NOT_ADMIN = sorted(set(UserRole) - usuarios.ADMIN_ROLES)

#: O que o GoTrue pode devolver e não pode sair daqui. Os valores são únicos
#: para que a varredura os ache em qualquer lugar do texto da resposta.
SECRETS = {
    "password": "pw-SEGREDO-0001",
    "token": "tk-SEGREDO-0002",
    "confirmation_token": "ct-SEGREDO-0003",
    "recovery_token": "rt-SEGREDO-0004",
    "action_link": "https://project.supabase.co/auth/v1/verify?token=al-SEGREDO-0005&type=invite",
    "access_token": "at-SEGREDO-0006",
    "refresh_token": "rf-SEGREDO-0007",
}
FORBIDDEN_KEYS = set(SECRETS)


def gotrue_user(
    user_id: UUID = NEW_USER, email: str = EMAIL, metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "id": str(user_id),
        "aud": "authenticated",
        "role": "authenticated",
        "email": email,
        "invited_at": "2026-10-05T12:00:00Z",
        "user_metadata": metadata or {},
        "properties": {"action_link": SECRETS["action_link"]},
        **SECRETS,
    }


class FakeGoTrue:
    """O GoTrue atrás de `httpx`: grava cada requisição e responde como mandado."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.user_id = NEW_USER
        self.metadata: dict[str, dict[str, Any]] = {}
        #: Erro de rede a levantar no lugar da resposta (`ConnectError`, timeout).
        self.failure: Exception | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        pedido = json.loads(request.content)
        # Como o GoTrue: `data` vira os metadados da conta que o convite cria.
        self.metadata[pedido["email"]] = pedido.get("data", {})
        body = gotrue_user(self.user_id, pedido["email"], self.metadata[pedido["email"]])
        if self.status >= 400:
            body = {"code": self.status, "msg": "falhou", **SECRETS}
        return httpx.Response(self.status, json=body)


@pytest.fixture
def gotrue(monkeypatch: pytest.MonkeyPatch) -> FakeGoTrue:
    fake = FakeGoTrue()
    real = httpx.AsyncClient
    transport = httpx.MockTransport(fake.handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    return fake


@pytest.fixture
def as_role() -> Any:
    def install(role: UserRole) -> None:
        async def membership(user_id: UUID) -> TenantContext:
            return TenantContext(tenant_id=TENANT_ID, user_id=user_id, role=role)

        app.dependency_overrides[get_membership_resolver] = lambda: membership

    return install


@pytest.fixture
def cabecalho(issue_token: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token()}"}


def ident(
    user_id: UUID = EXISTING,
    *,
    confirmed: bool = True,
    is_member: bool = False,
    active_elsewhere: bool = False,
) -> dict[str, Any]:
    """Uma linha de `IDENTITY_SQL`: a conta do e-mail no Auth."""
    return {
        "user_id": user_id,
        "confirmed": confirmed,
        "is_member": is_member,
        "active_elsewhere": active_elsewhere,
    }


def member_row(role: str, user_id: UUID = MEMBER, **overrides: Any) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "email": f"{role}@cliente.com.br",
        "name": f"Pessoa {role}",
        "role": role,
        "active": True,
        "deactivated_at": None,
        "invitation_accepted": True,
        "invited_by": None,
        "invited_by_email": None,
        "invited_by_name": None,
    } | overrides


class Db:
    """Os dois cursores: o `tenant_scope` (embrulhado no `TenantScope` de
    verdade, para que `bind_tenant` continue valendo) e o `user_scope`."""

    def __init__(self, bound: StubScope, user: StubScope) -> None:
        self.bound = bound
        self.user = user
        self.user_ctx = StubScopeContext(user)

    def ran(self, scope: StubScope, marker: str) -> list[Any]:
        return [p for s, p in zip(scope.statements, scope.params, strict=True) if marker in s]


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(
        *,
        identity: list[dict[str, Any]] | None = None,
        scope_check: Any = None,
        rpc: Any = None,
        target: Any = None,
        members: list[dict[str, Any]] | None = None,
        scope_rows: list[dict[str, Any]] | None = None,
        matrix: list[dict[str, Any]] | None = None,
    ) -> Db:
        bound = StubScope(
            {
                "from auth.users u\n     where lower(u.email)": identity or [],
                "util.parse_user_scope": (
                    scope_check if scope_check is not None else {"entries": 1}
                ),
                "u.email_confirmed_at is not null as accepted": target,
                "u.email_confirmed_at is not null as invitation_accepted": members or [],
                "from app.user_scope s": scope_rows or [],
                "enum_range(null::app.user_role)": matrix or [],
            }
        )
        # As quatro RPCs da etapa respondem o mesmo `rpc`.
        user = StubScope({"select public.fn_": rpc})
        handle = Db(bound, user)

        @asynccontextmanager
        async def fake_tenant_scope(context: Any, schema: str = "app") -> Any:
            yield TenantScope(bound, context)  # type: ignore[arg-type]

        monkeypatch.setattr(usuarios, "tenant_scope", fake_tenant_scope)
        monkeypatch.setattr(usuarios, "user_scope", lambda _t: handle.user_ctx)
        return handle

    return install


def invite_body(**overrides: Any) -> dict[str, Any]:
    return {
        "name": NAME,
        "email": EMAIL,
        "scope": [{"company_id": str(COMPANY), "unit_id": str(UNIT)}],
    } | overrides


# ---------------------------------------------------------------------------
# 403 por papel, nas três rotas — antes de qualquer leitura e do Admin API
# ---------------------------------------------------------------------------
ROUTES = [
    ("post", "/usuarios/convites", invite_body()),
    ("post", f"/usuarios/{MEMBER}/reenviar-convite", {}),
    ("get", "/usuarios", None),
    ("get", "/usuarios/matriz", None),
    ("get", f"/usuarios/{MEMBER}", None),
    ("put", f"/usuarios/{MEMBER}/escopo", {"scope": [{"company_id": str(COMPANY)}]}),
    ("post", f"/usuarios/{MEMBER}/desativar", {}),
]


@pytest.mark.parametrize("role", NOT_ADMIN)
@pytest.mark.parametrize(("method", "url", "body"), ROUTES)
def test_quem_nao_administra_recebe_403_sem_ler_nada(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Any,
    gotrue: FakeGoTrue,
    as_role: Any,
    role: UserRole,
    method: str,
    url: str,
    body: Any,
) -> None:
    as_role(role)
    handle = db(identity=[], target=None)

    kwargs: dict[str, Any] = {"headers": cabecalho}
    if body is not None:
        kwargs["json"] = body
    resposta = getattr(client, method)(url, **kwargs)

    assert resposta.status_code == 403
    assert resposta.json() == {"detail": "not_admin"}
    assert handle.bound.statements == []
    assert handle.user_ctx.opened == 0
    assert gotrue.requests == []


def test_os_papeis_da_rota_sao_os_do_util_is_admin(last_migration_with: Any) -> None:
    sql = last_migration_with("create or replace function util.is_admin(")
    body = sql.split("create or replace function util.is_admin(", 1)[1].split("$$;", 1)[0]
    (roles,) = re.findall(r"tm\.role in \(([^)]*)\)", body)
    assert {r.strip(" '") for r in roles.split(",")} == {r.value for r in usuarios.ADMIN_ROLES}


@pytest.mark.parametrize("function", ["util.can_see_unit", "util.can_see_company"])
def test_o_atalho_de_papel_da_lista_e_o_das_funcoes_de_escopo(
    last_migration_with: Any, function: str
) -> None:
    """`by_role` é exatamente quem o atalho de papel deixa ver tudo (§3.2)."""
    marker = f"create or replace function {function}("
    body = last_migration_with(marker).split(marker, 1)[1].split("$$;", 1)[0]
    (roles,) = re.findall(r"tm\.role in \(([^)]*)\)", body)
    assert {r.strip(" '") for r in roles.split(",")} == {r.value for r in usuarios.BY_ROLE_ROLES}


# ---------------------------------------------------------------------------
# POST /usuarios/convites
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", ADMIN)
def test_convite_novo_chama_o_admin_api_e_depois_a_rpc_como_o_usuario(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Any,
    gotrue: FakeGoTrue,
    as_role: Any,
    role: UserRole,
) -> None:
    as_role(role)
    handle = db(identity=[])

    resposta = client.post("/usuarios/convites", json=invite_body(), headers=cabecalho)

    assert resposta.status_code == 201
    assert resposta.json() == {
        "user_id": str(NEW_USER),
        "email": EMAIL,
        "role": "viewer",
        "invitation_sent": True,
    }
    # O Admin API: um convite, só o e-mail no corpo, e o retorno vindo da config.
    (pedido,) = gotrue.requests
    assert (pedido.method, pedido.url.path) == ("POST", "/auth/v1/invite")
    assert json.loads(pedido.content) == {"email": EMAIL, "data": {"name": NAME}}
    assert pedido.url.params["redirect_to"] == "http://localhost:3000/convite"
    assert pedido.headers["apikey"] == "service-role-key-for-tests"
    # A RPC, como o usuário, com o id que o GoTrue devolveu e o escopo pedido.
    (params,) = handle.ran(handle.user, "fn_convidar_usuario")
    assert params["tenant_id"] == TENANT_ID
    assert params["user_id"] == NEW_USER
    assert params["scope"].obj == [{"company_id": str(COMPANY), "unit_id": str(UNIT)}]
    # Nenhum papel sai daqui: quem grava `viewer` é a RPC.
    assert "role" not in params
    assert handle.user_ctx.opened == 1


def test_o_e_mail_e_normalizado_antes_de_procurar_a_identidade(
    client: TestClient, cabecalho: dict[str, str], db: Any, gotrue: FakeGoTrue, as_role: Any
) -> None:
    as_role(UserRole.HR)
    handle = db(identity=[])

    client.post(
        "/usuarios/convites",
        json=invite_body(email="  Nova.Pessoa@Cliente.com.BR ", name="  Nova Pessoa "),
        headers=cabecalho,
    )

    (params,) = handle.ran(handle.bound, "lower(u.email)")
    assert params == {"email": EMAIL, "tenant_id": TENANT_ID}
    assert json.loads(gotrue.requests[0].content) == {"email": EMAIL, "data": {"name": NAME}}


@pytest.mark.parametrize("ativo", [True, False])
def test_ja_e_membro_e_checado_antes_do_admin_api(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Any,
    gotrue: FakeGoTrue,
    as_role: Any,
    ativo: bool,
) -> None:
    """Vínculo ativo ou inativo: o e-mail não sai, e nem o escopo é lido."""
    as_role(UserRole.PERSONNEL)
    handle = db(identity=[ident(is_member=True, active_elsewhere=True)])

    resposta = client.post("/usuarios/convites", json=invite_body(), headers=cabecalho)

    assert resposta.status_code == 409
    assert resposta.json() == {"detail": "ja_e_membro"}
    assert gotrue.requests == []
    # O vínculo que recusa é o DESTE tenant, e vem antes de `conta_em_outro_cliente`.
    assert "where tm.tenant_id = %(tenant_id)s and tm.user_id = u.id" in usuarios.IDENTITY_SQL
    assert handle.ran(handle.bound, "util.parse_user_scope") == []
    assert handle.user_ctx.opened == 0


def test_conta_ativa_em_outro_cliente_recusa_antes_do_admin_api(
    client: TestClient, cabecalho: dict[str, str], db: Any, gotrue: FakeGoTrue, as_role: Any
) -> None:
    """Um segundo vínculo ativo deixaria a resolução do token ambígua, e a pessoa
    sem acesso nenhum ao cliente dela (decisão do dono, 05/10/2026). Confirmada
    ou não, a conta ativa em outro cliente é recusada — sem dizer qual."""
    as_role(UserRole.HR)
    for confirmed in (True, False):
        handle = db(identity=[ident(confirmed=confirmed, active_elsewhere=True)])

        resposta = client.post("/usuarios/convites", json=invite_body(), headers=cabecalho)

        assert resposta.status_code == 409
        assert resposta.json() == {"detail": "conta_em_outro_cliente"}
        assert gotrue.requests == []
        assert handle.ran(handle.bound, "util.parse_user_scope") == []
        assert handle.user_ctx.opened == 0


def test_conta_em_outro_cliente_e_a_condicao_da_rpc(last_migration_with: Any) -> None:
    """`active_elsewhere` é a condição de `fn_convidar_usuario`: vínculo ativo em
    QUALQUER outro tenant, sem olhar `app.tenant.active` (o suspenso, reativado,
    ficaria ambíguo)."""
    sql = " ".join(usuarios.IDENTITY_SQL.split())
    assert (
        "exists (select 1 from app.tenant_member o where o.tenant_id <> %(tenant_id)s "
        "and o.user_id = u.id and o.active) as active_elsewhere"
    ) in sql
    assert "app.tenant t" not in sql
    rpc = last_migration_with("create or replace function public.fn_convidar_usuario(")
    assert "where o.user_id = p_user_id and o.tenant_id <> p_tenant_id and o.active" in rpc


@pytest.mark.parametrize(
    "code", ["empresa_fora_do_tenant", "unidade_fora_da_empresa", "escopo_sem_empresa"]
)
def test_escopo_que_nao_vale_no_tenant_recusa_antes_do_admin_api(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Any,
    gotrue: FakeGoTrue,
    as_role: Any,
    code: str,
) -> None:
    as_role(UserRole.OWNER)
    handle = db(identity=[], scope_check=_TriggerRefusal(code))

    resposta = client.post("/usuarios/convites", json=invite_body(), headers=cabecalho)

    assert resposta.status_code == 422
    assert resposta.json() == {"detail": code}
    assert gotrue.requests == []
    assert handle.user_ctx.opened == 0
    (params,) = handle.ran(handle.bound, "util.parse_user_scope")
    assert params["caller"] == USER_ID
    assert params["tenant_id"] == TENANT_ID


def test_parser_que_nao_roda_nao_libera_o_admin_api(
    client: TestClient, cabecalho: dict[str, str], db: Any, gotrue: FakeGoTrue, as_role: Any
) -> None:
    """Zero linha na checagem do escopo é o parser que não rodou: falha alto."""
    as_role(UserRole.OWNER)
    db(identity=[], scope_check={"entries": 0})

    with pytest.raises(RuntimeError, match="não foi validado"):
        client.post("/usuarios/convites", json=invite_body(), headers=cabecalho)
    assert gotrue.requests == []


def test_conta_confirmada_sem_vinculo_ativo_e_reusada_sem_novo_convite(
    client: TestClient, cabecalho: dict[str, str], db: Any, gotrue: FakeGoTrue, as_role: Any
) -> None:
    """Tem senha e não está ativa em cliente nenhum: entra com a senha que já tem."""
    as_role(UserRole.HR)
    handle = db(identity=[ident(confirmed=True)])

    resposta = client.post("/usuarios/convites", json=invite_body(), headers=cabecalho)

    assert resposta.status_code == 201
    assert resposta.json()["user_id"] == str(EXISTING)
    assert resposta.json()["invitation_sent"] is False
    assert gotrue.requests == []
    (params,) = handle.ran(handle.user, "fn_convidar_usuario")
    assert params["user_id"] == EXISTING
    # O `name` pedido é descartado: os metadados da conta existente não são
    # reescritos — nem pelo Admin API (não chamado) nem pelo banco.
    assert NAME not in json.dumps([str(p) for p in handle.bound.params + handle.user.params])


def test_conta_sem_senha_recebe_o_convite_de_novo_sem_reescrever_o_nome(
    client: TestClient, cabecalho: dict[str, str], db: Any, gotrue: FakeGoTrue, as_role: Any
) -> None:
    """Sem senha e sem vínculo ativo: reusar em silêncio deixaria a pessoa sem
    como entrar. O Admin API reenvia (sem `data`), e a resposta diz que saiu."""
    as_role(UserRole.HR)
    gotrue.user_id = EXISTING
    handle = db(identity=[ident(confirmed=False)])

    resposta = client.post("/usuarios/convites", json=invite_body(), headers=cabecalho)

    assert resposta.status_code == 201
    assert resposta.json()["user_id"] == str(EXISTING)
    assert resposta.json()["invitation_sent"] is True
    (pedido,) = gotrue.requests
    assert json.loads(pedido.content) == {"email": EMAIL}
    assert pedido.url.params["redirect_to"] == "http://localhost:3000/convite"
    (params,) = handle.ran(handle.user, "fn_convidar_usuario")
    assert params["user_id"] == EXISTING


def test_reenvio_que_volta_com_outra_identidade_nao_vincula(
    client: TestClient, cabecalho: dict[str, str], db: Any, gotrue: FakeGoTrue, as_role: Any
) -> None:
    as_role(UserRole.HR)
    gotrue.user_id = NEW_USER
    handle = db(identity=[ident(confirmed=False)])

    with pytest.raises(RuntimeError, match="outra identidade"):
        client.post("/usuarios/convites", json=invite_body(), headers=cabecalho)
    assert handle.user_ctx.opened == 0


@pytest.mark.parametrize(
    ("code", "http"),
    [
        ("not_admin", 403),
        ("ja_e_membro", 409),
        ("conta_em_outro_cliente", 409),
        ("empresa_fora_do_tenant", 422),
        ("unidade_fora_da_empresa", 422),
        ("escopo_vazio", 422),
        ("escopo_invalido", 422),
        ("escopo_sem_empresa", 422),
    ],
)
def test_recusa_da_rpc_depois_do_admin_api_vira_http_e_a_identidade_fica(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Any,
    gotrue: FakeGoTrue,
    as_role: Any,
    code: str,
    http: int,
) -> None:
    """Só uma corrida chega aqui (o pré-teste passou). A identidade criada FICA
    no Auth — nenhum DELETE ao Admin API — e o próximo convite a acha sem senha
    e reenvia o e-mail para ela, com o mesmo id."""
    as_role(UserRole.OWNER)
    db(identity=[], rpc=_TriggerRefusal(code))

    resposta = client.post("/usuarios/convites", json=invite_body(), headers=cabecalho)

    assert resposta.status_code == http
    assert resposta.json() == {"detail": code}
    assert [(r.method, r.url.path) for r in gotrue.requests] == [("POST", "/auth/v1/invite")]

    # O segundo convite do mesmo e-mail acha a identidade órfã, sem senha.
    gotrue.requests.clear()
    handle = db(identity=[ident(NEW_USER, confirmed=False)])
    segunda = client.post("/usuarios/convites", json=invite_body(), headers=cabecalho)
    assert segunda.status_code == 201
    assert segunda.json()["invitation_sent"] is True
    (reenvio,) = gotrue.requests
    assert json.loads(reenvio.content) == {"email": EMAIL}
    assert handle.ran(handle.user, "fn_convidar_usuario")[0]["user_id"] == NEW_USER


def test_recusa_desconhecida_da_rpc_nao_vira_resposta_bonita(
    client: TestClient, cabecalho: dict[str, str], db: Any, gotrue: FakeGoTrue, as_role: Any
) -> None:
    as_role(UserRole.OWNER)
    db(identity=[], rpc=_TriggerRefusal("algo_novo"))

    with pytest.raises(_TriggerRefusal):
        client.post("/usuarios/convites", json=invite_body(), headers=cabecalho)


@pytest.mark.parametrize("status", [400, 422, 429, 500])
def test_admin_api_que_falha_vira_502_sem_o_corpo_dele(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Any,
    gotrue: FakeGoTrue,
    as_role: Any,
    status: int,
) -> None:
    as_role(UserRole.OWNER)
    handle = db(identity=[])
    gotrue.status = status

    resposta = client.post("/usuarios/convites", json=invite_body(), headers=cabecalho)

    assert resposta.status_code == 502
    assert resposta.json() == {"detail": "convite_nao_enviado"}
    assert handle.user_ctx.opened == 0
    _sem_segredo(resposta)


@pytest.mark.parametrize(
    "body",
    [
        invite_body(role="owner"),
        invite_body(password="x"),
        invite_body(tenant_id=str(TENANT_ID)),
        invite_body(scope=[]),
        invite_body(scope=[{"company_id": str(COMPANY), "unitId": str(UNIT)}]),
        invite_body(scope=[{"company_id": str(COMPANY), "unit_id": None}]),
        invite_body(scope=[{"company_id": str(COMPANY), "unit_id": ""}]),
        invite_body(scope=[{"unit_id": str(UNIT)}]),
        invite_body(email="sem-arroba"),
        {"scope": invite_body()["scope"]},
        {"email": EMAIL, "scope": invite_body()["scope"]},
        invite_body(name=""),
        invite_body(name="   "),
        invite_body(name=None),
        invite_body(name="x" * 121),
    ],
    ids=[
        "role",
        "password",
        "tenant_id",
        "escopo-vazio",
        "chave-trocada",
        "unidade-nula",
        "unidade-vazia",
        "sem-empresa",
        "email-invalido",
        "sem-email",
        "sem-nome",
        "nome-vazio",
        "nome-so-espacos",
        "nome-nulo",
        "nome-longo",
    ],
)
def test_corpo_do_convite_e_fechado(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Any,
    gotrue: FakeGoTrue,
    as_role: Any,
    body: dict[str, Any],
) -> None:
    as_role(UserRole.OWNER)
    handle = db(identity=[])

    resposta = client.post("/usuarios/convites", json=body, headers=cabecalho)

    assert resposta.status_code == 422
    assert gotrue.requests == []
    assert handle.bound.statements == []


# ---------------------------------------------------------------------------
# POST /usuarios/{user_id}/reenviar-convite
# ---------------------------------------------------------------------------
def test_reenviar_convite_manda_de_novo_ao_e_mail_do_membro(
    client: TestClient, cabecalho: dict[str, str], db: Any, gotrue: FakeGoTrue, as_role: Any
) -> None:
    as_role(UserRole.PERSONNEL)
    gotrue.user_id = MEMBER
    handle = db(target={"email": EMAIL, "active": True, "accepted": False})

    resposta = client.post(f"/usuarios/{MEMBER}/reenviar-convite", json={}, headers=cabecalho)

    assert resposta.status_code == 200
    assert resposta.json() == {"user_id": str(MEMBER), "email": EMAIL}
    (pedido,) = gotrue.requests
    # O reenvio não manda `data`: não reescreve o nome que a pessoa tem.
    assert json.loads(pedido.content) == {"email": EMAIL}
    assert pedido.url.params["redirect_to"] == "http://localhost:3000/convite"
    (params,) = handle.ran(handle.bound, "as accepted")
    assert params == {"user_id": MEMBER, "tenant_id": TENANT_ID}


@pytest.mark.parametrize(
    ("target", "http", "code"),
    [
        (None, 404, "member_not_found"),
        ({"email": EMAIL, "active": False, "accepted": False}, 409, "membro_inativo"),
        ({"email": EMAIL, "active": True, "accepted": True}, 409, "convite_ja_aceito"),
    ],
)
def test_reenviar_convite_recusa_sem_chamar_o_admin_api(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Any,
    gotrue: FakeGoTrue,
    as_role: Any,
    target: Any,
    http: int,
    code: str,
) -> None:
    as_role(UserRole.OWNER)
    db(target=target)

    resposta = client.post(f"/usuarios/{MEMBER}/reenviar-convite", json={}, headers=cabecalho)

    assert (resposta.status_code, resposta.json()) == (http, {"detail": code})
    assert gotrue.requests == []


@pytest.mark.parametrize("body", [{"password": "x"}, {"email": EMAIL}, None])
def test_corpo_do_reenvio_e_fechado_e_obrigatorio(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Any,
    gotrue: FakeGoTrue,
    as_role: Any,
    body: Any,
) -> None:
    as_role(UserRole.OWNER)
    handle = db(target={"email": EMAIL, "active": True, "accepted": False})

    kwargs: dict[str, Any] = {"headers": cabecalho}
    if body is not None:
        kwargs["json"] = body
    resposta = client.post(f"/usuarios/{MEMBER}/reenviar-convite", **kwargs)

    assert resposta.status_code == 422
    assert gotrue.requests == []
    assert handle.bound.statements == []


# ---------------------------------------------------------------------------
# GET /usuarios
# ---------------------------------------------------------------------------
INVITER = UUID("0c3a0000-0000-4000-8000-0000000000f1")


def test_a_lista_traz_nome_e_mail_e_quem_convidou_do_recem_convidado(
    client: TestClient, cabecalho: dict[str, str], db: Any, as_role: Any
) -> None:
    as_role(UserRole.HR)
    novo = member_row(
        "viewer",
        user_id=NEW_USER,
        email=EMAIL,
        name="Nova Pessoa",
        invitation_accepted=False,
        invited_by=INVITER,
        invited_by_email="rh@cliente.com.br",
        invited_by_name="Pessoa do RH",
    )
    handle = db(
        members=[novo],
        scope_rows=[
            {
                "user_id": NEW_USER,
                "company_id": COMPANY,
                "company_name": "Alfa",
                "unit_id": UNIT,
                "unit_name": "Centro",
            }
        ],
    )

    resposta = client.get("/usuarios", headers=cabecalho)

    assert resposta.status_code == 200
    assert resposta.json() == {
        "users": [
            {
                "user_id": str(NEW_USER),
                "email": EMAIL,
                "name": "Nova Pessoa",
                "role": "viewer",
                "active": True,
                "deactivated_at": None,
                "invitation_accepted": False,
                "invited_by": {
                    "user_id": str(INVITER),
                    "email": "rh@cliente.com.br",
                    "name": "Pessoa do RH",
                },
                "scope_mode": "by_scope",
                "scope": [
                    {
                        "company_id": str(COMPANY),
                        "company_name": "Alfa",
                        "unit_id": str(UNIT),
                        "unit_name": "Centro",
                    }
                ],
            }
        ]
    }
    # As duas leituras passaram pelo `bind_tenant`: o tenant do token, nunca outro.
    assert handle.bound.params == [{"tenant_id": TENANT_ID}, {"tenant_id": TENANT_ID}]
    assert "where tm.tenant_id = %(tenant_id)s" in usuarios.LIST_SQL
    assert "where s.tenant_id = %(tenant_id)s" in usuarios.SCOPE_LIST_SQL


def test_o_nome_do_convite_chega_a_lista_pelo_que_o_gotrue_gravou(
    client: TestClient, cabecalho: dict[str, str], db: Any, gotrue: FakeGoTrue, as_role: Any
) -> None:
    """O nome não é simulado: a linha da lista é montada com os metadados que o
    GoTrue falso gravou a partir do `data` que o convite mandou."""
    as_role(UserRole.HR)
    db(identity=[])
    feito = client.post("/usuarios/convites", json=invite_body(), headers=cabecalho).json()

    gravado = gotrue.metadata[EMAIL]
    assert gravado == {"name": NAME}
    db(
        members=[
            member_row(
                "viewer",
                user_id=UUID(feito["user_id"]),
                email=EMAIL,
                name=gravado.get("name"),
                invitation_accepted=False,
                invited_by=USER_ID,
            )
        ]
    )
    (linha,) = client.get("/usuarios", headers=cabecalho).json()["users"]

    assert (linha["user_id"], linha["name"], linha["email"]) == (str(NEW_USER), NAME, EMAIL)
    assert linha["invited_by"]["user_id"] == str(USER_ID)


def test_inativo_vem_marcado_com_a_data(
    client: TestClient, cabecalho: dict[str, str], db: Any, as_role: Any
) -> None:
    as_role(UserRole.OWNER)
    quando = datetime(2026, 10, 5, 13, 0, tzinfo=UTC)
    db(members=[member_row("viewer", active=False, deactivated_at=quando)])

    (linha,) = client.get("/usuarios", headers=cabecalho).json()["users"]

    assert linha["active"] is False
    assert linha["deactivated_at"] == "2026-10-05T13:00:00Z"
    assert linha["invited_by"] is None


@pytest.mark.parametrize("role", list(UserRole))
def test_scope_mode_por_papel_e_o_escopo_nunca_aparece_para_quem_e_por_papel(
    client: TestClient, cabecalho: dict[str, str], db: Any, as_role: Any, role: UserRole
) -> None:
    """Todo papel tem uma linha em `user_scope` aqui — e para os quatro do
    atalho ela NÃO aparece: mostrar "Empresa Alfa" a quem vê três mentiria."""
    as_role(UserRole.OWNER)
    db(
        members=[member_row(role.value)],
        scope_rows=[
            {
                "user_id": MEMBER,
                "company_id": COMPANY,
                "company_name": "Alfa",
                "unit_id": None,
                "unit_name": None,
            }
        ],
    )

    (linha,) = client.get("/usuarios", headers=cabecalho).json()["users"]

    by_role = {UserRole.OWNER, UserRole.EXECUTIVE, UserRole.HR, UserRole.PERSONNEL}
    if role in by_role:
        assert (linha["scope_mode"], linha["scope"]) == ("by_role", [])
    else:
        assert linha["scope_mode"] == "by_scope"
        assert [s["company_name"] for s in linha["scope"]] == ["Alfa"]


# ---------------------------------------------------------------------------
# U4 — detalhe, papel, escopo, desativar e a matriz
# ---------------------------------------------------------------------------
def _send(client: TestClient, method: str, url: str, body: Any, cabecalho: dict[str, str]) -> Any:
    kwargs: dict[str, Any] = {"headers": cabecalho}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(url, **kwargs)


@pytest.mark.parametrize("role", sorted(set(UserRole) - {UserRole.OWNER}))
def test_papel_por_quem_nao_e_owner_recusa_na_rota_sem_chamar_a_rpc(
    client: TestClient, cabecalho: dict[str, str], db: Any, as_role: Any, role: UserRole
) -> None:
    """O gate da U4: para `hr` (e todo papel que não é `owner`) a ROTA recusa —
    a RPC nem abre, nem nada é lido."""
    as_role(role)
    handle = db(members=[member_row("viewer")])

    resposta = client.put(f"/usuarios/{MEMBER}/papel", json={"role": "hr"}, headers=cabecalho)

    assert resposta.status_code == 403
    assert resposta.json() == {"detail": "not_owner"}
    assert handle.user_ctx.opened == 0
    assert handle.user.statements == []
    assert handle.bound.statements == []


def test_papel_pelo_owner_chama_a_rpc_como_o_usuario_e_devolve_o_membro(
    client: TestClient, cabecalho: dict[str, str], db: Any, as_role: Any
) -> None:
    as_role(UserRole.OWNER)
    handle = db(members=[member_row("unit_supervisor")])

    resposta = client.put(
        f"/usuarios/{MEMBER}/papel", json={"role": "unit_supervisor"}, headers=cabecalho
    )

    assert resposta.status_code == 200
    assert resposta.json()["role"] == "unit_supervisor"
    assert handle.user_ctx.opened == 1
    assert handle.ran(handle.user, "fn_definir_papel") == [
        {"tenant_id": TENANT_ID, "user_id": MEMBER, "role": "unit_supervisor"}
    ]
    # A releitura passou pelo `bind_tenant`: o tenant do token, nunca outro.
    assert handle.bound.params == [
        {"user_id": MEMBER, "tenant_id": TENANT_ID},
        {"user_id": MEMBER, "tenant_id": TENANT_ID},
    ]


@pytest.mark.parametrize("role", ADMIN)
def test_escopo_chama_a_rpc_com_a_lista_do_convite(
    client: TestClient, cabecalho: dict[str, str], db: Any, as_role: Any, role: UserRole
) -> None:
    as_role(role)
    handle = db(members=[member_row("viewer")])
    body = {
        "scope": [{"company_id": str(COMPANY)}, {"company_id": str(COMPANY), "unit_id": str(UNIT)}]
    }

    resposta = client.put(f"/usuarios/{MEMBER}/escopo", json=body, headers=cabecalho)

    assert resposta.status_code == 200
    (params,) = handle.ran(handle.user, "fn_definir_escopo")
    assert (params["tenant_id"], params["user_id"]) == (TENANT_ID, MEMBER)
    assert params["scope"].obj == [
        {"company_id": str(COMPANY)},
        {"company_id": str(COMPANY), "unit_id": str(UNIT)},
    ]


@pytest.mark.parametrize("role", ADMIN)
def test_desativar_chama_a_rpc_e_devolve_o_membro_inativo(
    client: TestClient, cabecalho: dict[str, str], db: Any, as_role: Any, role: UserRole
) -> None:
    as_role(role)
    quando = datetime(2026, 10, 5, 13, 0, tzinfo=UTC)
    handle = db(members=[member_row("viewer", active=False, deactivated_at=quando)])

    resposta = client.post(f"/usuarios/{MEMBER}/desativar", json={}, headers=cabecalho)

    assert resposta.status_code == 200
    assert (resposta.json()["active"], resposta.json()["deactivated_at"]) == (
        False,
        "2026-10-05T13:00:00Z",
    )
    assert handle.ran(handle.user, "fn_desativar_membro") == [
        {"tenant_id": TENANT_ID, "user_id": MEMBER}
    ]


WRITES = {
    "papel": ("put", f"/usuarios/{MEMBER}/papel", {"role": "viewer"}),
    "escopo": ("put", f"/usuarios/{MEMBER}/escopo", {"scope": [{"company_id": str(COMPANY)}]}),
    "desativar": ("post", f"/usuarios/{MEMBER}/desativar", {}),
}
REFUSALS = [
    ("papel", "not_owner", 403),
    ("papel", "member_not_found", 404),
    ("papel", "ultimo_owner", 409),
    ("escopo", "not_admin", 403),
    ("escopo", "member_not_found", 404),
    ("escopo", "escopo_vazio", 422),
    ("escopo", "escopo_invalido", 422),
    ("escopo", "escopo_sem_empresa", 422),
    ("escopo", "empresa_fora_do_tenant", 422),
    ("escopo", "unidade_fora_da_empresa", 422),
    ("desativar", "not_admin", 403),
    ("desativar", "e_voce_mesmo", 409),
    ("desativar", "member_not_found", 404),
    ("desativar", "owner_so_por_owner", 403),
    ("desativar", "ultimo_owner", 409),
]


@pytest.mark.parametrize(("rota", "code", "esperado"), REFUSALS)
def test_cada_recusa_da_rpc_vira_o_status_dela_sem_reler(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Any,
    as_role: Any,
    rota: str,
    code: str,
    esperado: int,
) -> None:
    as_role(UserRole.OWNER)
    handle = db(members=[member_row("viewer")], rpc=_TriggerRefusal(code))

    resposta = _send(client, *WRITES[rota], cabecalho)

    assert (resposta.status_code, resposta.json()) == (esperado, {"detail": code})
    assert handle.bound.statements == []


def test_as_tabelas_de_recusa_sao_as_das_rpcs(last_migration_with: Any) -> None:
    """Toda recusa que a RPC levanta tem status na rota, e nenhuma a mais."""
    sql = last_migration_with("create or replace function public.fn_desativar_membro(")
    for function, statuses in (
        ("fn_definir_papel", usuarios.ROLE_STATUS),
        ("fn_definir_escopo", usuarios.SCOPE_STATUS),
        ("fn_desativar_membro", usuarios.DEACTIVATE_STATUS),
    ):
        body = sql.split(f"create or replace function public.{function}(", 1)[1]
        body = body.split("$$;", 1)[0]
        codes = set(re.findall(r"raise exception '(\w+)'", body))
        if function == "fn_definir_escopo":
            parser = sql.split("create or replace function util.parse_user_scope(", 1)[1]
            codes |= set(re.findall(r"raise exception '(\w+)'", parser.split("$$;", 1)[0]))
        assert codes == set(statuses), function
    assert {c for _, c, _ in REFUSALS} == (
        set(usuarios.ROLE_STATUS) | set(usuarios.SCOPE_STATUS) | set(usuarios.DEACTIVATE_STATUS)
    )


@pytest.mark.parametrize("rota", sorted(WRITES))
def test_recusa_desconhecida_das_escritas_nao_vira_200(
    client: TestClient, cabecalho: dict[str, str], db: Any, as_role: Any, rota: str
) -> None:
    as_role(UserRole.OWNER)
    db(members=[member_row("viewer")], rpc=_TriggerRefusal("algo_novo"))

    with pytest.raises(_TriggerRefusal):
        _send(client, *WRITES[rota], cabecalho)


@pytest.mark.parametrize(
    ("rota", "body"),
    [
        ("papel", {"role": "viewer", "active": False}),
        ("papel", {"role": "superuser"}),
        ("papel", {}),
        ("escopo", {"scope": []}),
        ("escopo", {"scope": [{"company_id": str(COMPANY)}], "role": "owner"}),
        ("escopo", {"scope": [{"company_id": str(COMPANY), "unit_id": None}]}),
        ("escopo", {"scope": [{"company_id": str(COMPANY), "unitId": str(UNIT)}]}),
        ("desativar", {"password": "x"}),
        ("desativar", None),
    ],
)
def test_corpos_das_escritas_sao_fechados(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Any,
    as_role: Any,
    rota: str,
    body: Any,
) -> None:
    as_role(UserRole.OWNER)
    handle = db(members=[member_row("viewer")])
    method, url, _ = WRITES[rota]

    resposta = _send(client, method, url, body, cabecalho)

    assert resposta.status_code == 422
    assert handle.user_ctx.opened == 0


def test_detalhe_de_quem_nao_e_deste_tenant_e_404(
    client: TestClient, cabecalho: dict[str, str], db: Any, as_role: Any
) -> None:
    as_role(UserRole.HR)
    handle = db(members=[])

    resposta = client.get(f"/usuarios/{MEMBER}", headers=cabecalho)

    assert (resposta.status_code, resposta.json()) == (404, {"detail": "member_not_found"})
    assert handle.bound.params[0] == {"user_id": MEMBER, "tenant_id": TENANT_ID}
    assert "and tm.user_id = %(user_id)s" in usuarios.DETAIL_SQL
    assert "and s.user_id = %(user_id)s" in usuarios.SCOPE_DETAIL_SQL


@pytest.mark.parametrize("role", list(UserRole))
def test_detalhe_scope_mode_por_papel(
    client: TestClient, cabecalho: dict[str, str], db: Any, as_role: Any, role: UserRole
) -> None:
    """Os quatro do atalho saem `by_role`, sem a linha de `user_scope` que têm."""
    as_role(UserRole.PERSONNEL)
    db(
        members=[member_row(role.value)],
        scope_rows=[
            {
                "user_id": MEMBER,
                "company_id": COMPANY,
                "company_name": "Alfa",
                "unit_id": UNIT,
                "unit_name": "Centro",
            }
        ],
    )

    linha = client.get(f"/usuarios/{MEMBER}", headers=cabecalho).json()

    if role in {UserRole.OWNER, UserRole.EXECUTIVE, UserRole.HR, UserRole.PERSONNEL}:
        assert (linha["scope_mode"], linha["scope"]) == ("by_role", [])
    else:
        assert linha["scope_mode"] == "by_scope"
        assert [(s["company_name"], s["unit_name"]) for s in linha["scope"]] == [("Alfa", "Centro")]


@pytest.mark.parametrize("role", ADMIN)
def test_a_matriz_e_o_que_o_banco_devolve_com_papel_vazio_presente(
    client: TestClient, cabecalho: dict[str, str], db: Any, as_role: Any, role: UserRole
) -> None:
    """`/matriz` não é lido como um `user_id` (rota declarada antes), e papel
    sem domínio vem com lista vazia, não omitido."""
    as_role(role)
    handle = db(
        matrix=[
            {"role": "owner", "domains": ["pii", "compensation", "banking"]},
            {"role": "hr", "domains": ["pii", "health"]},
            {"role": "viewer", "domains": []},
        ]
    )

    resposta = client.get("/usuarios/matriz", headers=cabecalho)

    assert resposta.status_code == 200
    assert resposta.json() == {
        "roles": [
            {"role": "owner", "domains": ["pii", "compensation", "banking"]},
            {"role": "hr", "domains": ["pii", "health"]},
            {"role": "viewer", "domains": []},
        ]
    }
    assert handle.bound.params == [{"tenant_id": TENANT_ID}]
    assert "dp.tenant_id = %(tenant_id)s" in usuarios.MATRIX_SQL


def test_dominio_que_o_python_nao_conhece_nao_some_da_matriz(
    client: TestClient, cabecalho: dict[str, str], db: Any, as_role: Any
) -> None:
    """Um valor novo no enum do banco quebra alto, em vez de sumir da tela."""
    as_role(UserRole.OWNER)
    db(matrix=[{"role": "hr", "domains": ["genetic"]}])

    with pytest.raises(ValueError, match="genetic"):
        client.get("/usuarios/matriz", headers=cabecalho)


def test_sensitive_domain_espelha_o_enum_do_banco() -> None:
    from tests.conftest import MIGRATIONS

    values: list[str] = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        for created in re.findall(r"create type app\.sensitive_domain as enum \(([^)]*)\)", text):
            values += [v.strip(" '") for v in created.split(",")]
        values += re.findall(
            r"alter type app\.sensitive_domain add value if not exists '(\w+)'", text
        )
    assert values == [d.value for d in SensitiveDomain]


# ---------------------------------------------------------------------------
# A varredura: nenhuma resposta carrega senha, link ou token
# ---------------------------------------------------------------------------
def _keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _keys(v)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def _sem_segredo(resposta: httpx.Response) -> None:
    corpo = resposta.json()
    assert FORBIDDEN_KEYS.isdisjoint(_keys(corpo)), set(_keys(corpo)) & FORBIDDEN_KEYS
    texto = resposta.text
    for chave, valor in SECRETS.items():
        assert valor not in texto, chave
    assert "SEGREDO" not in texto
    assert "verify?token" not in texto


def test_nenhuma_resposta_das_rotas_carrega_senha_link_ou_token(
    client: TestClient, cabecalho: dict[str, str], db: Any, gotrue: FakeGoTrue, as_role: Any
) -> None:
    respostas = []
    as_role(UserRole.OWNER)

    db(identity=[])
    respostas.append(client.post("/usuarios/convites", json=invite_body(), headers=cabecalho))
    db(identity=[ident(confirmed=True)])
    respostas.append(client.post("/usuarios/convites", json=invite_body(), headers=cabecalho))
    db(identity=[ident(is_member=True)])
    respostas.append(client.post("/usuarios/convites", json=invite_body(), headers=cabecalho))
    db(identity=[ident(active_elsewhere=True)])
    respostas.append(client.post("/usuarios/convites", json=invite_body(), headers=cabecalho))
    gotrue.user_id = EXISTING
    db(identity=[ident(confirmed=False)])
    respostas.append(client.post("/usuarios/convites", json=invite_body(), headers=cabecalho))
    gotrue.user_id = NEW_USER
    db(identity=[], rpc=_TriggerRefusal("empresa_fora_do_tenant"))
    respostas.append(client.post("/usuarios/convites", json=invite_body(), headers=cabecalho))
    respostas.append(
        client.post("/usuarios/convites", json=invite_body(password="x"), headers=cabecalho)
    )

    gotrue.user_id = MEMBER
    db(target={"email": EMAIL, "active": True, "accepted": False})
    respostas.append(
        client.post(f"/usuarios/{MEMBER}/reenviar-convite", json={}, headers=cabecalho)
    )
    respostas.append(
        client.post(
            f"/usuarios/{MEMBER}/reenviar-convite", json={"password": "x"}, headers=cabecalho
        )
    )

    db(members=[member_row("viewer", invited_by=INVITER, invited_by_email="a@b.c")])
    respostas.append(client.get("/usuarios", headers=cabecalho))

    db(members=[member_row("viewer", invited_by=INVITER, invited_by_email="a@b.c")])
    respostas.append(client.get(f"/usuarios/{MEMBER}", headers=cabecalho))
    respostas.append(
        client.put(f"/usuarios/{MEMBER}/papel", json={"role": "hr"}, headers=cabecalho)
    )
    respostas.append(
        client.put(
            f"/usuarios/{MEMBER}/escopo",
            json={"scope": [{"company_id": str(COMPANY)}]},
            headers=cabecalho,
        )
    )
    respostas.append(client.post(f"/usuarios/{MEMBER}/desativar", json={}, headers=cabecalho))
    respostas.append(
        client.post(f"/usuarios/{MEMBER}/desativar", json={"token": "x"}, headers=cabecalho)
    )
    db(matrix=[{"role": "hr", "domains": ["pii"]}])
    respostas.append(client.get("/usuarios/matriz", headers=cabecalho))

    gotrue.status = 500
    db(identity=[])
    respostas.append(client.post("/usuarios/convites", json=invite_body(), headers=cabecalho))
    db(target={"email": EMAIL, "active": True, "accepted": False})
    respostas.append(
        client.post(f"/usuarios/{MEMBER}/reenviar-convite", json={}, headers=cabecalho)
    )

    gotrue.status = 200
    gotrue.failure = httpx.ConnectError("sem rede")
    db(identity=[])
    respostas.append(client.post("/usuarios/convites", json=invite_body(), headers=cabecalho))

    assert [r.status_code for r in respostas] == [
        201, 201, 409, 409, 201, 422, 422, 200, 422, 200,
        200, 200, 200, 200, 422, 200,
        502, 502, 502,
    ]  # fmt: skip
    # O Admin API falso respondeu com os segredos — a varredura tem o que achar.
    assert len(gotrue.requests) == 7
    for resposta in respostas:
        _sem_segredo(resposta)


def test_a_falha_do_admin_api_nao_carrega_o_corpo_na_mensagem(gotrue: FakeGoTrue) -> None:
    """A exceção que fica no servidor (e no Sentry) diz só o status."""
    import asyncio

    from operax.core.auth_admin import AuthAdminError, SupabaseAuthAdmin

    gotrue.status = 422
    admin = SupabaseAuthAdmin("https://project.supabase.co", "chave")
    with pytest.raises(AuthAdminError) as erro:
        asyncio.run(admin.invite(EMAIL, "http://localhost:3000/convite"))
    assert str(erro.value) == "o Admin API recusou o convite (HTTP 422)"
    assert erro.value.__cause__ is None and erro.value.__context__ is None


NETWORK_FAILURES = [
    httpx.ConnectError("sem rede"),
    httpx.ConnectTimeout("tempo esgotado"),
    httpx.ReadTimeout("tempo esgotado"),
    httpx.RemoteProtocolError("conexão caiu"),
]
SERVICE_KEY = "service-role-key-for-tests"


@pytest.mark.parametrize("failure", NETWORK_FAILURES, ids=lambda e: type(e).__name__)
@pytest.mark.parametrize("caminho", ["convite", "reenvio"])
def test_rede_ou_timeout_do_admin_api_vira_502_sem_a_chave(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Any,
    gotrue: FakeGoTrue,
    as_role: Any,
    failure: Exception,
    caminho: str,
) -> None:
    as_role(UserRole.OWNER)
    gotrue.failure = failure
    handle = db(identity=[], target={"email": EMAIL, "active": True, "accepted": False})

    if caminho == "convite":
        resposta = client.post("/usuarios/convites", json=invite_body(), headers=cabecalho)
    else:
        resposta = client.post(f"/usuarios/{MEMBER}/reenviar-convite", json={}, headers=cabecalho)

    assert resposta.status_code == 502
    assert resposta.json() == {"detail": "convite_nao_enviado"}
    assert len(gotrue.requests) == 1
    assert handle.user_ctx.opened == 0
    assert SERVICE_KEY not in resposta.text and "Bearer" not in resposta.text
    assert "apikey" not in resposta.text.lower()
    _sem_segredo(resposta)


@pytest.mark.parametrize("failure", NETWORK_FAILURES, ids=lambda e: type(e).__name__)
def test_a_excecao_de_rede_nao_carrega_a_chave_nem_os_headers(
    gotrue: FakeGoTrue, failure: Exception
) -> None:
    """Nem no texto nem na cadeia: `__cause__` e `__context__` vazios — o erro do
    httpx carrega a requisição, e a requisição carrega a chave nos headers."""
    import asyncio

    from operax.core.auth_admin import AuthAdminError, SupabaseAuthAdmin

    gotrue.failure = failure
    admin = SupabaseAuthAdmin("https://project.supabase.co", SERVICE_KEY)
    with pytest.raises(AuthAdminError) as erro:
        asyncio.run(admin.invite(EMAIL, "http://localhost:3000/convite"))

    assert str(erro.value) == "o Admin API não respondeu (rede ou tempo esgotado)"
    assert erro.value.__cause__ is None and erro.value.__context__ is None
    for texto in (str(erro.value), repr(erro.value)):
        assert SERVICE_KEY not in texto
        assert "Bearer" not in texto and "apikey" not in texto.lower()
