"""A aba de templates: o catálogo pelo Caminho 2, e o "Sincronizar" da WABA.

Quatro portões (SPRINTS-CANAIS, C2b), e o quarto é o que costuma escapar:

1. quem não é admin não cria, não edita e não sincroniza — e o admin cria;
2. corpo que não usa uma variável declarada é recusado **pelo gatilho**, e a
   frase dele chega como `detail` — o Python não conhece a sintaxe de placeholder
   (há um teste que lê o fonte da rota e procura por ela: zero);
3. da sincronização, **só `APPROVED` produz `approved`** — parametrizado sobre
   todos os status da Meta e mais um inventado;
4. **o token não aparece no log nem no erro** da sincronização — a mesma
   varredura sob `DEBUG` do gate 3 do C2, e o positivo que prova qual defesa
   segura o quê: `verification_client` para o log, `from None` para a cadeia.

⚠️ O QUE ESTA SUÍTE NÃO PODE PROVAR
Nada aqui toca banco nem rede. O gatilho de verdade (`P0001` com a frase), o
`is distinct from` do upsert que devolve `draft` quando o nome muda, o `unnest`
da sincronização que só grava o que mudou, e a policy que esconde o tenant
vizinho são `scripts/97_teste_canais.py`, no `make db-test`, executando o SQL
real destas rotas. Aqui o banco é um stub que responde pelo assunto da
instrução — e, na sincronização, emula o `is distinct from` a partir do estado
semeado, para que "só o que mudou" seja verificável de ponta a ponta no Python.
"""

from __future__ import annotations

import ast
import logging
import re
import traceback
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from psycopg import errors

from operax.alertas.provedores import meta_cloud
from operax.alertas.provedores.base import InvalidCredentialError, verification_client
from server.main import app
from server.routers import canais
from tests.conftest import TENANT_ID
from tests.test_canais_credencial import (
    TOKEN,
    WABA_ID,
    Recorder,
    StubScope,
    StubScopeContext,
    _all_text,
    _codes_raised,
    _reset_http_loggers,
)

INTEGRATION_ID = UUID("33333333-3333-4333-8333-333333333332")
TEMPLATE_ID = UUID("55555555-5555-4555-8555-555555555551")
OTHER_TEMPLATE_ID = UUID("55555555-5555-4555-8555-555555555552")
THIRD_TEMPLATE_ID = UUID("55555555-5555-4555-8555-555555555553")

#: A frase que o gatilho de verdade produz (o `97` a executa); aqui é o que o
#: stub levanta, e o teste afirma que ela chega **literal** ao operador.
TRIGGER_PHRASE = (
    "Template deviation_summary declara a variável 2 (occurrences) mas o corpo não usa {{2}}."
)

CONTRACT = {
    "code",
    "category",
    "language",
    "variables",
    "body",
    "meta_template_name",
    "meta_status",
    "meta_rejection",
    "active",
    "updated_at",
}

VALID_WRITE: dict[str, Any] = {
    "category": "utility",
    "language": "pt_BR",
    "variables": ["unit", "occurrences"],
    "body": "FastPark: {{1}} com {{2}} ocorrências.",
    "meta_template_name": "deviation_summary_v1",
    "active": True,
}


def template_row(**overrides: Any) -> dict[str, Any]:
    """Uma linha do `returning` do upsert (ou do `select` do catálogo)."""
    return {
        "id": TEMPLATE_ID,
        "code": "deviation_summary",
        "category": "utility",
        "language": "pt_BR",
        "variables": ["unit", "occurrences"],
        "body": "FastPark: {{1}} com {{2}} ocorrências.",
        "meta_template_name": "deviation_summary_v1",
        "meta_status": "draft",
        "meta_rejection": None,
        "active": True,
        "updated_at": "2026-09-15T12:00:00+00:00",
        "before": None,
    } | overrides


def named(
    code: str,
    name: str,
    status: str = "draft",
    rejection: str | None = None,
    *,
    id: UUID = TEMPLATE_ID,
    language: str = "pt_BR",
) -> dict[str, Any]:
    """Uma linha de `_NAMED_TEMPLATES_SQL`. `meta_status`/`meta_rejection` não
    são colunas dessa consulta: existem aqui para o stub emular o `is distinct
    from` do banco — a rota não os lê, e um teste prende isso."""
    return {
        "id": id,
        "code": code,
        "language": language,
        "meta_template_name": name,
        "meta_status": status,
        "meta_rejection": rejection,
    }


# ---------------------------------------------------------------------------
# O transporte: o que a WABA responde
# ---------------------------------------------------------------------------
def meta_template(
    name: str, status: str, language: str = "pt_BR", rejected_reason: str | None = None
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name,
        "status": status,
        "language": language,
        "category": "UTILITY",
        "id": "1",
    }
    if rejected_reason is not None:
        item["rejected_reason"] = rejected_reason
    return item


def page(*items: dict[str, Any], next: str | None = None) -> httpx.Response:
    body: dict[str, Any] = {"data": list(items), "paging": {"cursors": {"after": "x"}}}
    if next is not None:
        body["paging"]["next"] = next
    return httpx.Response(200, json=body)


# As duas fixtures do C2, redeclaradas em vez de importadas: importar uma
# fixture pelo nome e usá-la como parâmetro é o F811 do ruff em todo teste.
@pytest.fixture
def cabecalho(issue_token: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token()}"}


@pytest.fixture
def transport(client: TestClient) -> Iterator[Recorder]:
    """O mesmo `Recorder` do C2, pelo mesmo `verification_client` — onde a
    defesa do log vive."""
    recorder = Recorder()

    async def override() -> Any:
        _reset_http_loggers()
        async with verification_client(transport=httpx.MockTransport(recorder.handler)) as http:
            yield http

    app.dependency_overrides[canais.get_http_client] = override
    yield recorder
    _reset_http_loggers()


# ---------------------------------------------------------------------------
# O banco falso, com resposta que pode depender dos parâmetros
# ---------------------------------------------------------------------------
class AnsweringScope(StubScope):
    """`StubScope` cujo valor pode ser uma função dos parâmetros — é como o
    stub emula o `is distinct from` da sincronização."""

    async def execute(self, statement: str, params: Any = None) -> None:
        self.statements.append(statement)
        self.params.append(params)
        answer = next(
            (value for marker, value in self._answers.items() if marker in statement),
            None,
        )
        if isinstance(answer, Exception):
            raise answer
        if callable(answer):
            answer = answer(params)
        self._current = answer


class TimedScopeContext(StubScopeContext):
    """Registra entrada e saída numa linha do tempo compartilhada com o transporte."""

    def __init__(self, scope: StubScope, timeline: list[str], name: str) -> None:
        super().__init__(scope)
        self._timeline = timeline
        self._name = name

    async def __aenter__(self) -> StubScope:
        self._timeline.append(f"{self._name}:enter")
        return await super().__aenter__()

    async def __aexit__(self, exc_type: type[BaseException] | None, *exc: object) -> None:
        self._timeline.append(f"{self._name}:exit")
        return await super().__aexit__(exc_type, *exc)


class _TriggerRefusal(errors.RaiseException):
    """O `P0001` do gatilho, com o `diag.message_primary` que o psycopg preenche
    a partir do `message` do `raise exception`."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self._message = message

    @property
    def diag(self) -> Any:
        return SimpleNamespace(message_primary=self._message)


def _sync_update(local: list[dict[str, Any]]) -> Callable[[Any], list[dict[str, str]]]:
    """Emula `_SYNC_TEMPLATES_SQL`: devolve o `code` de quem o par
    `(meta_status, meta_rejection)` pedido é distinto do semeado — e só se o
    nome que a rota consultou ainda é o nome da linha."""
    by_id = {row["id"]: row for row in local}

    def answer(params: Any) -> list[dict[str, str]]:
        changed = []
        for id_, name, status, rejection in zip(
            params["ids"], params["names"], params["statuses"], params["rejections"], strict=True
        ):
            row = by_id[id_]
            if row["meta_template_name"] != name:
                continue
            if (row["meta_status"], row["meta_rejection"]) != (status, rejection):
                changed.append({"code": row["code"]})
        return changed

    return answer


@dataclass
class Stubs:
    user: AnsweringScope
    bound: AnsweringScope
    bound_ctx: TimedScopeContext
    timeline: list[str] = field(default_factory=list)


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Stubs]:
    def install(
        *,
        admin: bool = True,
        catalogue: list[dict[str, Any]] | None = None,
        upsert: Any = None,
        integration: dict[str, Any] | None | str = "default",
        token: str | None = TOKEN,
        local: list[dict[str, Any]] | None = None,
        local_at_update: list[dict[str, Any]] | None = None,
    ) -> Stubs:
        timeline: list[str] = []
        user = AnsweringScope(
            {
                "util.is_admin": {"admin": admin},
                "from app.message_template": catalogue if catalogue is not None else [],
            }
        )
        if integration == "default":
            integration = {"id": INTEGRATION_ID, "waba_id": WABA_ID}
        local = local or []
        bound = AnsweringScope(
            {
                "on conflict (tenant_id, code, language)": (
                    upsert if upsert is not None else template_row()
                ),
                "config ->> 'waba_id'": integration,
                "vault.decrypted_secrets": {"decrypted_secret": token} if token else None,
                "meta_template_name is not null": local,
                # O estado que o `update` encontra pode não ser o que o `select`
                # leu: é a corrida com um `PUT` que renomeia enquanto a Meta responde.
                "unnest(": _sync_update(local if local_at_update is None else local_at_update),
                "insert into app.audit_log": None,
            }
        )
        bound_ctx = TimedScopeContext(bound, timeline, "tenant_scope")
        monkeypatch.setattr(
            canais, "user_scope", lambda _t: TimedScopeContext(user, timeline, "user_scope")
        )
        monkeypatch.setattr(canais, "tenant_scope", lambda _t: bound_ctx)
        return Stubs(user=user, bound=bound, bound_ctx=bound_ctx, timeline=timeline)

    return install


def _put(client: TestClient, cabecalho: dict[str, str], code: str, body: dict[str, Any]):
    return client.put(f"/canais/templates/{code}", json=body, headers=cabecalho)


def _sync(client: TestClient, cabecalho: dict[str, str]):
    return client.post("/canais/templates/sincronizar", headers=cabecalho)


def _statements(scope: StubScope, marker: str) -> list[tuple[str, Any]]:
    return [(s, p) for s, p in zip(scope.statements, scope.params, strict=True) if marker in s]


# ---------------------------------------------------------------------------
# GET — como o usuário, qualquer membro, inativos inclusive
# ---------------------------------------------------------------------------
def test_o_catalogo_roda_como_o_usuario_e_nao_no_tenant_scope(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """A policy `message_template_read` é quem recorta; `service_role` não entra.
    ⛔ Mutação: trocar `user_scope` por `tenant_scope` na rota deixa isto vermelho."""
    stubs = db(catalogue=[template_row(), template_row(code="deviation_individual")])

    resposta = client.get("/canais/templates", headers=cabecalho)

    assert resposta.status_code == 200
    assert [t["code"] for t in resposta.json()] == ["deviation_summary", "deviation_individual"]
    assert stubs.bound_ctx.opened == 0
    assert stubs.bound.statements == []
    [(statement, params)] = _statements(stubs.user, "from app.message_template")
    assert statement == canais._TEMPLATES_SQL
    assert params["tenant_id"] == str(TENANT_ID)
    assert "order by code" in canais._TEMPLATES_SQL


def test_o_catalogo_nao_exige_admin_e_inclui_inativos(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """Quem vê Conexões vê o catálogo; `active` é coluna e a tela decide."""
    stubs = db(admin=False, catalogue=[template_row(active=False)])

    resposta = client.get("/canais/templates", headers=cabecalho)

    assert resposta.status_code == 200
    [linha] = resposta.json()
    assert linha["active"] is False
    assert not any("util.is_admin" in s for s in stubs.user.statements)
    assert "active" not in canais._TEMPLATES_SQL.split("where")[1]  # nenhum filtro por active


def test_o_catalogo_devolve_exatamente_o_contrato(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    db(catalogue=[template_row(id="nao-deveria-sair", before={"x": 1})])

    [linha] = client.get("/canais/templates", headers=cabecalho).json()

    assert set(linha) == CONTRACT


# ---------------------------------------------------------------------------
# PUT — gate 1: admin grava, não-admin não; a forma antes do banco
# ---------------------------------------------------------------------------
def test_put_sem_admin_e_403_antes_de_qualquer_escrita(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(admin=False)

    resposta = _put(client, cabecalho, "deviation_summary", VALID_WRITE)

    assert resposta.status_code == 403
    # A frase nomeia o que foi negado — a tela a mostra como veio, e "gravar a
    # credencial" num 403 de template mandaria o operador ao lugar errado.
    assert resposta.json()["detail"] == "Gravar templates do canal é do administrador do cliente."
    assert stubs.bound_ctx.opened == 0
    assert stubs.bound.statements == []


def test_put_admin_grava_uma_vez_e_devolve_o_gravado_relido(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """O positivo do gate 1. ⛔ Mutação: tirar o `_require_admin` do PUT deixa o
    teste do 403 vermelho, não este."""
    stubs = db()

    resposta = _put(client, cabecalho, "deviation_summary", VALID_WRITE)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert set(corpo) == CONTRACT
    assert corpo["code"] == "deviation_summary"
    assert corpo["meta_status"] == "draft"
    assert stubs.bound_ctx.opened == 1
    assert stubs.bound_ctx.exited_with is None
    [(statement, params)] = _statements(stubs.bound, "on conflict")
    assert statement == canais._TEMPLATE_UPSERT_SQL
    assert params["code"] == "deviation_summary"
    assert params["variables"] == ["unit", "occurrences"]
    assert params["meta_template_name"] == "deviation_summary_v1"
    # `meta_status` e `meta_rejection` não são do formulário: o SQL os decide.
    assert "meta_status" not in params and "meta_rejection" not in params
    assert any("util.is_admin" in s for s in stubs.user.statements)


def test_put_audita_insert_com_antes_nulo_e_depois_igual_ao_gravado(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db()

    corpo = _put(client, cabecalho, "deviation_summary", VALID_WRITE).json()

    [(statement, params)] = _statements(stubs.bound, "app.audit_log")
    assert statement == canais._TEMPLATE_AUDIT_SQL
    assert "'message_template'" in statement
    assert params["action"] == "insert"
    assert params["entity_id"] == str(TEMPLATE_ID)
    assert params["antes"] is None
    assert params["depois"].obj == corpo
    assert params["user_id"] is not None


def test_put_audita_update_com_a_linha_anterior_em_antes(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """`before` vem do `returning` — a CTE lê a linha na foto anterior à escrita.
    O `to_jsonb` traz `id`, `tenant_id` e `created_at`; a trilha leva só o contrato."""
    anterior = {k: v for k, v in template_row(meta_status="approved").items() if k != "before"} | {
        "tenant_id": str(TENANT_ID),
        "created_at": "2026-09-01T00:00:00+00:00",
    }
    stubs = db(upsert=template_row(before=anterior, meta_status="approved"))

    resposta = _put(client, cabecalho, "deviation_summary", VALID_WRITE)

    assert resposta.status_code == 200
    [(_, params)] = _statements(stubs.bound, "app.audit_log")
    assert params["action"] == "update"
    antes = params["antes"].obj
    assert set(antes) == CONTRACT
    assert antes["meta_status"] == "approved"
    assert antes["updated_at"].startswith("2026-09-15T12:00:00")
    assert params["depois"].obj["meta_status"] == "approved"


@pytest.mark.parametrize(
    ("code", "override", "field"),
    [
        ("Deviation-Summary", {}, "code"),
        ("ab", {}, "code"),
        ("deviation_summary", {"category": "promo"}, "category"),
        ("deviation_summary", {"language": "portuguese"}, "language"),
        ("deviation_summary", {"language": "PT_br"}, "language"),
        ("deviation_summary", {"variables": []}, "variables"),
        ("deviation_summary", {"variables": ["Unit"]}, "variables"),
        ("deviation_summary", {"variables": ["unit", "unit"]}, "variables"),
        ("deviation_summary", {"meta_template_name": "Nome Com Espaço"}, "meta_template_name"),
        ("deviation_summary", {"meta_template_name": ""}, "meta_template_name"),
    ],
)
def test_forma_invalida_e_422_nomeando_o_campo_sem_tocar_o_banco(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Callable[..., Stubs],
    code: str,
    override: dict[str, Any],
    field: str,
) -> None:
    """Só o que o banco não confere. O corpo fica de fora de propósito — é do gatilho."""
    stubs = db()

    resposta = _put(client, cabecalho, code, VALID_WRITE | override)

    assert resposta.status_code == 422, resposta.text
    corpo = resposta.json()
    assert corpo["code"] == "invalid_format"
    assert corpo["field"] == field
    assert stubs.bound_ctx.opened == 0


def test_meta_template_name_nulo_e_aceito(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """O par do caso `""`: nulo é "ainda sem nome na WABA", e é válido."""
    stubs = db(upsert=template_row(meta_template_name=None))

    corpo = VALID_WRITE | {"meta_template_name": None}
    resposta = _put(client, cabecalho, "deviation_summary", corpo)

    assert resposta.status_code == 200
    [(_, params)] = _statements(stubs.bound, "on conflict")
    assert params["meta_template_name"] is None


# ---------------------------------------------------------------------------
# PUT — gate 2: o corpo é do gatilho, e a frase dele chega literal
# ---------------------------------------------------------------------------
def test_corpo_recusado_pelo_gatilho_e_422_com_a_frase_literal_e_sem_auditoria(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """O `P0001` do gatilho vira 422 com `detail` = `message_primary`, sem cópia
    nem tradução; a transação sai por exceção (rollback) e a auditoria não roda."""
    stubs = db(upsert=_TriggerRefusal(TRIGGER_PHRASE))

    resposta = _put(client, cabecalho, "deviation_summary", VALID_WRITE | {"body": "só {{1}}"})

    assert resposta.status_code == 422
    corpo = resposta.json()
    assert corpo["detail"] == TRIGGER_PHRASE
    assert corpo["code"] == "template_body"
    assert stubs.bound_ctx.opened == 1
    assert stubs.bound_ctx.exited_with is canais.TemplateBodyRefusedError
    assert _statements(stubs.bound, "app.audit_log") == []


def test_a_rota_nao_conhece_a_sintaxe_de_placeholder(
    last_migration_with: Callable[[str], str],
) -> None:
    """A asserção do revisor: zero `{{` no fonte da rota. O positivo é que a
    sintaxe existe — na função do banco que julga o corpo."""
    assert canais.__file__ is not None
    fonte = Path(canais.__file__).read_text(encoding="utf-8")
    assert "{{" not in fonte
    gatilho = last_migration_with("create or replace function util.validate_template_body")
    assert "{{" in gatilho


def test_outro_erro_do_banco_nao_vira_422(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """Só o `P0001` do gatilho é recusa do operador. Um `check` violado ou um
    erro de driver é defeito nosso, e tem de estourar — não virar frase de tela."""
    db(upsert=errors.CheckViolation("injected"))

    with pytest.raises(errors.CheckViolation):
        _put(client, cabecalho, "deviation_summary", VALID_WRITE)


def test_o_select_do_catalogo_nomeia_toda_coluna_do_contrato() -> None:
    """O stub devolve o que lhe dão; um `select` que esquecesse `meta_rejection`
    passaria em todo teste de rota e quebraria em produção com `KeyError`."""
    projecao = canais._TEMPLATES_SQL.split("from app.message_template")[0]
    for column in canais._TEMPLATE_COLUMNS:
        assert re.search(rf"\b{column}\b", projecao), column
    assert set(canais._TEMPLATE_COLUMNS) == CONTRACT
    assert "returning t.*" in canais._TEMPLATE_UPSERT_SQL


# ---------------------------------------------------------------------------
# PUT — trocar o nome na Meta volta o status a draft, no SQL
# ---------------------------------------------------------------------------
def test_trocar_o_meta_template_name_volta_o_status_a_draft_no_proprio_upsert() -> None:
    """Uma viagem, não duas: o `case` compara `excluded` com a linha existente.
    Quem executa (nome igual preserva `approved`; nome novo → `draft`) é o `97`."""
    sql = canais._TEMPLATE_UPSERT_SQL
    assert sql.count("excluded.meta_template_name is distinct from t.meta_template_name") == 2
    assert "then 'draft' else t.meta_status end" in sql
    assert "then null else t.meta_rejection end" in sql
    assert "on conflict (tenant_id, code, language)" in sql
    # O `antes` da auditoria e o `insert`/`update` vêm da mesma foto.
    assert "with before as" in sql and "(select to_jsonb(b) from before b) as before" in sql
    # `meta_status`/`meta_rejection` nunca vêm do formulário.
    assert "%(meta_status)s" not in sql and "%(meta_rejection)s" not in sql


# ---------------------------------------------------------------------------
# Sincronizar — gate 1 e as recusas antes de qualquer HTTP
# ---------------------------------------------------------------------------
def test_sincronizar_sem_admin_e_403_sem_http_e_sem_transacao(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    stubs = db(admin=False)
    transport.respond = lambda _: page(meta_template("deviation_summary_v1", "APPROVED"))

    resposta = _sync(client, cabecalho)

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Gravar templates do canal é do administrador do cliente."
    assert transport.requests == []
    assert stubs.bound_ctx.opened == 0


def test_sincronizar_sem_meta_cloud_ativo_e_422_sem_http_e_sem_ler_o_cofre(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    stubs = db(integration=None)
    transport.respond = lambda _: page(meta_template("deviation_summary_v1", "APPROVED"))

    resposta = _sync(client, cabecalho)

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "no_official_provider"
    assert "Cloud API" in resposta.json()["detail"]
    assert transport.requests == []
    assert _statements(stubs.bound, "vault.decrypted_secrets") == []
    assert _statements(stubs.bound, "unnest(") == []
    [(statement, params)] = _statements(stubs.bound, "config ->> 'waba_id'")
    assert statement == canais._OFFICIAL_INTEGRATION_SQL
    assert params["provider"] == meta_cloud.NAME


def test_sincronizar_sem_ponteiro_no_cofre_e_422_sem_http(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    stubs = db(token=None)
    transport.respond = lambda _: page(meta_template("deviation_summary_v1", "APPROVED"))

    resposta = _sync(client, cabecalho)

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "no_credential"
    assert transport.requests == []
    [(_, params)] = _statements(stubs.bound, "vault.decrypted_secrets")
    assert params["integration_id"] == INTEGRATION_ID
    assert params["key"] == "token"
    assert _statements(stubs.bound, "unnest(") == []


def test_sincronizar_com_credencial_sem_waba_id_e_422_sem_ler_o_cofre(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """Credencial gravada antes do C2b não tem `waba_id` em `config`: não há o
    que listar, e o token nem é lido."""
    stubs = db(integration={"id": INTEGRATION_ID, "waba_id": None})

    resposta = _sync(client, cabecalho)

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "no_credential"
    assert transport.requests == []
    assert _statements(stubs.bound, "vault.decrypted_secrets") == []


def test_a_transacao_da_credencial_fecha_antes_da_primeira_requisicao(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """⛔ Mutação: chamar `list_templates` dentro do primeiro `tenant_scope` deixa
    isto vermelho. O token vive numa local entre o cofre e a Meta — fora de
    transação, como a verificação do C2."""
    stubs = db(local=[named("deviation_summary", "deviation_summary_v1")])

    def respond(_: httpx.Request) -> httpx.Response:
        stubs.timeline.append("http")
        return page(meta_template("deviation_summary_v1", "APPROVED"))

    transport.respond = respond

    assert _sync(client, cabecalho).status_code == 200
    linha = stubs.timeline
    assert linha == [
        "user_scope:enter",
        "user_scope:exit",
        "tenant_scope:enter",
        "tenant_scope:exit",
        "http",
        "tenant_scope:enter",
        "tenant_scope:exit",
    ]


def test_sincronizar_devolve_o_contrato_e_o_provedor_oficial(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    db()
    transport.respond = lambda _: page(
        meta_template("x", "APPROVED"), meta_template("y", "PENDING")
    )

    corpo = _sync(client, cabecalho).json()

    assert set(corpo) == {"provider", "meta_total", "updated", "unmatched", "synced_at"}
    assert corpo["provider"] == meta_cloud.NAME
    assert corpo["meta_total"] == 2
    assert corpo["updated"] == [] and corpo["unmatched"] == []


def test_sincronizar_manda_o_bearer_para_a_waba_certa(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    db()
    transport.respond = lambda _: page()

    _sync(client, cabecalho)

    [pedido] = transport.requests
    assert pedido.headers["Authorization"] == f"Bearer {TOKEN}"
    assert pedido.url.host == "graph.facebook.com"
    assert pedido.url.path.endswith(f"/{WABA_ID}/message_templates")
    assert pedido.url.params["fields"] == "name,status,language,category,rejected_reason"
    assert pedido.url.params["limit"] == "100"


# ---------------------------------------------------------------------------
# Sincronizar — gate 3: só APPROVED produz approved
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("meta_status", [*meta_cloud.META_STATUS, "BANANA", "approved", ""])
def test_so_approved_produz_approved(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Callable[..., Stubs],
    transport: Recorder,
    meta_status: str,
) -> None:
    """Todos os status da premissa, mais um inventado, um em minúsculas e um
    vazio: o único que abre a entrega é o literal `APPROVED`. O desconhecido é
    `rejected` com o literal registrado — um status novo da Meta que ninguém
    previu não liga mensagem nenhuma."""
    stubs = db(local=[named("deviation_summary", "deviation_summary_v1", "pending")])
    transport.respond = lambda _: page(
        meta_template("deviation_summary_v1", meta_status, rejected_reason="NONE")
    )

    corpo = _sync(client, cabecalho).json()

    [(_, params)] = _statements(stubs.bound, "unnest(")
    [status] = params["statuses"]
    [reason] = params["rejections"]
    assert (status == "approved") == (meta_status == "APPROVED")
    if meta_status in meta_cloud.META_STATUS:
        assert status == meta_cloud.META_STATUS[meta_status]
        assert reason is None
    else:
        assert status == "rejected"
        assert reason == f"Status desconhecido na Meta: {meta_status}"
    assert corpo["unmatched"] == []
    # O local estava `pending`/nulo: só o par igual a esse não conta como mudança.
    unchanged = status == "pending" and reason is None
    assert corpo["updated"] == ([] if unchanged else ["deviation_summary"])


def test_o_mapa_e_dado_e_so_uma_chave_aponta_para_approved() -> None:
    """O mapa vive em `meta_cloud.py`, cobre os nove status da premissa e cabe
    no `check` de `meta_status` (nunca produz `draft`, que é o "sem par")."""
    assert set(meta_cloud.META_STATUS) == {
        "APPROVED",
        "PENDING",
        "IN_APPEAL",
        "REJECTED",
        "PAUSED",
        "LIMIT_EXCEEDED",
        "DISABLED",
        "PENDING_DELETION",
        "DELETED",
    }
    assert [k for k, v in meta_cloud.META_STATUS.items() if v == "approved"] == ["APPROVED"]
    assert set(meta_cloud.META_STATUS.values()) == {"approved", "pending", "rejected", "paused"}


def test_rejected_reason_da_meta_chega_em_meta_rejection(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    stubs = db(local=[named("deviation_summary", "deviation_summary_v1", "pending")])
    transport.respond = lambda _: page(
        meta_template("deviation_summary_v1", "REJECTED", rejected_reason="INVALID_FORMAT")
    )

    _sync(client, cabecalho)

    [(_, params)] = _statements(stubs.bound, "unnest(")
    assert params["statuses"] == ["rejected"]
    assert params["rejections"] == ["INVALID_FORMAT"]


def test_sem_par_na_waba_volta_a_draft_com_a_razao_e_entra_em_unmatched(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """O par é `(name, language)`: mesmo nome noutro idioma não casa."""
    stubs = db(local=[named("deviation_summary", "deviation_summary_v1", "approved")])
    transport.respond = lambda _: page(meta_template("deviation_summary_v1", "APPROVED", "en_US"))

    corpo = _sync(client, cabecalho).json()

    [(_, params)] = _statements(stubs.bound, "unnest(")
    assert params["ids"] == [TEMPLATE_ID]
    assert params["statuses"] == ["draft"]
    assert params["rejections"] == ["Não encontrado na WABA na última sincronização"]
    assert corpo["unmatched"] == ["deviation_summary"]
    assert corpo["updated"] == ["deviation_summary"]


def test_updated_traz_so_o_que_mudou_e_a_auditoria_resume(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """Três locais: `a` já aprovado (a Meta confirma — nada muda), `b` pendente
    que a Meta aprovou (muda), `c` com nome e sem par (volta a draft). Um só
    `update`, com o `is distinct from` no texto; o stub o emula do estado semeado."""
    local = [
        named("a", "a_v1", "approved", id=TEMPLATE_ID),
        named("b", "b_v1", "pending", id=OTHER_TEMPLATE_ID),
        named("c", "c_v1", "pending", id=THIRD_TEMPLATE_ID),
    ]
    stubs = db(local=local)
    transport.respond = lambda _: page(
        meta_template("a_v1", "APPROVED"), meta_template("b_v1", "APPROVED")
    )

    corpo = _sync(client, cabecalho).json()

    assert corpo["updated"] == ["b", "c"]
    assert corpo["unmatched"] == ["c"]
    assert corpo["meta_total"] == 2
    [(statement, params)] = _statements(stubs.bound, "unnest(")
    assert statement == canais._SYNC_TEMPLATES_SQL
    assert "is distinct from (v.meta_status, v.meta_rejection)" in statement
    assert "and t.meta_template_name = v.name" in statement
    assert params["ids"] == [TEMPLATE_ID, OTHER_TEMPLATE_ID, THIRD_TEMPLATE_ID]
    assert params["names"] == ["a_v1", "b_v1", "c_v1"]
    assert params["statuses"] == ["approved", "approved", "draft"]
    [(_, audit)] = _statements(stubs.bound, "app.audit_log")
    assert audit["action"] == "update"
    assert audit["entity_id"] is None
    assert audit["antes"] is None
    assert audit["depois"].obj == {"updated": ["b", "c"], "unmatched": ["c"], "meta_total": 2}


def test_renomear_enquanto_a_meta_responde_nao_grava_o_veredito_do_nome_velho(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """A rota consultou `a_v1`; entre a leitura e o `update`, um `PUT` trocou o
    nome para `a_v2` e a linha já está em `draft`. O veredito da WABA é sobre
    `a_v1` — gravá-lo por `id` poria `approved` num nome que ninguém conferiu.
    O nome está na chave do `update`, e a linha fica como o `PUT` a deixou."""
    read = [named("a", "a_v1", "pending", id=TEMPLATE_ID)]
    renamed = [named("a", "a_v2", "draft", id=TEMPLATE_ID)]
    stubs = db(local=read, local_at_update=renamed)
    transport.respond = lambda _: page(meta_template("a_v1", "APPROVED"))

    corpo = _sync(client, cabecalho).json()

    assert corpo["updated"] == []
    assert corpo["unmatched"] == []
    [(_, params)] = _statements(stubs.bound, "unnest(")
    assert params["names"] == ["a_v1"]


def test_sem_template_com_nome_nao_ha_update_mas_ha_auditoria(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    stubs = db(local=[])
    transport.respond = lambda _: page(meta_template("x", "APPROVED"))

    corpo = _sync(client, cabecalho).json()

    assert corpo["updated"] == [] and corpo["unmatched"] == []
    assert _statements(stubs.bound, "unnest(") == []
    [(_, audit)] = _statements(stubs.bound, "app.audit_log")
    assert audit["depois"].obj == {"updated": [], "unmatched": [], "meta_total": 1}


def test_a_rota_le_so_as_colunas_da_consulta_de_nomeados(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """O stub semeia `meta_status` para emular o banco; a rota não pode depender
    disso — a consulta real não o devolve."""
    colunas = ("id", "code", "language", "meta_template_name")
    linhas = [{k: v for k, v in named("a", "a_v1").items() if k in colunas}]
    stubs = db(local=linhas)
    stubs.bound._answers["unnest("] = [{"code": "a"}]
    transport.respond = lambda _: page(meta_template("a_v1", "APPROVED"))

    assert _sync(client, cabecalho).json()["updated"] == ["a"]
    assert "select id, code, language, meta_template_name" in canais._NAMED_TEMPLATES_SQL


def test_recusa_da_meta_e_422_e_a_segunda_transacao_nem_abre(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """Endpoint errado falha para o lado seguro: nenhum status muda."""
    stubs = db(local=[named("deviation_summary", "deviation_summary_v1", "approved")])
    transport.respond = lambda _: httpx.Response(400, json={"error": {"message": "Unsupported"}})

    resposta = _sync(client, cabecalho)

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "unauthorized"
    assert stubs.bound_ctx.opened == 1
    assert _statements(stubs.bound, "unnest(") == []
    assert _statements(stubs.bound, "app.audit_log") == []


# ---------------------------------------------------------------------------
# list_templates — paginação, teto, forma
# ---------------------------------------------------------------------------
_TEMPLATES_URL = f"https://graph.facebook.com/v21.0/{WABA_ID}/message_templates"


def _paged(pages: int) -> Callable[[httpx.Request], httpx.Response]:
    """`pages` páginas com um template cada; todas menos a última têm `next`."""

    def handler(request: httpx.Request) -> httpx.Response:
        n = int(request.url.params.get("after", "0"))
        nxt = f"{_TEMPLATES_URL}?after={n + 1}" if n + 1 < pages else None
        return page(meta_template(f"t{n}", "APPROVED"), next=nxt)

    return handler


async def test_duas_paginas_sao_seguidas_com_o_mesmo_bearer() -> None:
    seen: list[httpx.Request] = []
    handler = _paged(2)

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    async with verification_client(transport=httpx.MockTransport(record)) as http:
        result = await meta_cloud.list_templates({"waba_id": WABA_ID}, TOKEN, http)

    assert [t.name for t in result] == ["t0", "t1"]
    assert len(seen) == 2
    assert str(seen[1].url) == f"{_TEMPLATES_URL}?after=1"
    assert all(r.headers["Authorization"] == f"Bearer {TOKEN}" for r in seen)


async def test_dez_paginas_passam_e_onze_sao_malformed() -> None:
    """Um teto sem teste é decoração: 10 páginas cabem, a 11ª é recusa — e a
    11ª requisição nunca é feita."""
    async with verification_client(transport=httpx.MockTransport(_paged(10))) as http:
        assert len(await meta_cloud.list_templates({"waba_id": WABA_ID}, TOKEN, http)) == 10

    count = {"n": 0}
    handler = _paged(11)

    def record(request: httpx.Request) -> httpx.Response:
        count["n"] += 1
        return handler(request)

    async with verification_client(transport=httpx.MockTransport(record)) as http:
        with pytest.raises(InvalidCredentialError) as erro:
            await meta_cloud.list_templates({"waba_id": WABA_ID}, TOKEN, http)
    assert erro.value.code == "malformed"
    assert count["n"] == meta_cloud.MAX_PAGES == 10


async def test_next_fora_do_host_da_graph_nao_e_seguido() -> None:
    """O `next` vem do corpo da resposta e a requisição seguinte leva o Bearer:
    um corpo que apontasse para outro host receberia o token. Recusa, e a
    segunda requisição não acontece."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return page(meta_template("t", "APPROVED"), next="https://evil.example/collect")

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(InvalidCredentialError) as erro:
            await meta_cloud.list_templates({"waba_id": WABA_ID}, TOKEN, http)

    assert erro.value.code == "malformed"
    assert len(seen) == 1

    def http_next(request: httpx.Request) -> httpx.Response:
        return page(next=f"http://graph.facebook.com/v21.0/{WABA_ID}/message_templates?after=1")

    async with verification_client(transport=httpx.MockTransport(http_next)) as http:
        with pytest.raises(InvalidCredentialError) as erro:
            await meta_cloud.list_templates({"waba_id": WABA_ID}, TOKEN, http)
    assert erro.value.code == "malformed"


async def test_rejected_reason_none_vira_nulo_e_o_resto_fica() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return page(
            meta_template("a", "APPROVED", rejected_reason="NONE"),
            meta_template("b", "REJECTED", rejected_reason="INVALID_FORMAT"),
            meta_template("c", "PENDING"),
        )

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        a, b, c = await meta_cloud.list_templates({"waba_id": WABA_ID}, TOKEN, http)

    assert [t.rejected_reason for t in (a, b, c)] == [None, "INVALID_FORMAT", None]
    assert (a.status, b.status, c.status) == ("APPROVED", "REJECTED", "PENDING")
    assert a.language == "pt_BR"


@pytest.mark.parametrize(
    "body",
    [
        {"something": "else"},
        {"data": "not-a-list"},
        {"data": [{"name": "a"}]},
        {"data": [], "paging": "x"},
        [],
    ],
)
async def test_resposta_fora_da_forma_e_malformed(body: Any) -> None:
    async with verification_client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as http:
        with pytest.raises(InvalidCredentialError) as erro:
            await meta_cloud.list_templates({"waba_id": WABA_ID}, TOKEN, http)
    assert erro.value.code == "malformed"


async def test_5xx_e_unreachable_e_4xx_e_unauthorized() -> None:
    for status, code in ((503, "unreachable"), (400, "unauthorized"), (401, "unauthorized")):
        async with verification_client(
            transport=httpx.MockTransport(lambda _, s=status: httpx.Response(s, json={"t": TOKEN}))
        ) as http:
            with pytest.raises(InvalidCredentialError) as erro:
                await meta_cloud.list_templates({"waba_id": WABA_ID}, TOKEN, http)
        assert erro.value.code == code


# ---------------------------------------------------------------------------
# Gate 4 — nem no log, nem no detail, nem na cadeia
# ---------------------------------------------------------------------------
def test_gate_4_o_token_nao_aparece_no_log_em_debug_nem_no_detail_nem_na_trilha(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Callable[..., Stubs],
    transport: Recorder,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A Meta responde 401 ecoando o token no corpo. Captura em DEBUG no logger
    raiz e varre o log, a resposta e tudo que passou pelas transações."""
    stubs = db(local=[named("deviation_summary", "deviation_summary_v1")])
    transport.refuse_echoing_the_token()

    with caplog.at_level(logging.DEBUG):
        resposta = _sync(client, cabecalho)

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "unauthorized"
    assert TOKEN not in caplog.text
    assert TOKEN not in resposta.text
    for statement, params in zip(stubs.bound.statements, stubs.bound.params, strict=True):
        assert TOKEN not in statement
        assert TOKEN not in _all_text(params)
    [recusa] = [r for r in caplog.records if r.name == canais.logger.name]
    assert "unauthorized" in recusa.getMessage()


def test_gate_4_o_caminho_feliz_tambem_nao_leva_o_token_a_trilha_nem_ao_log(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Callable[..., Stubs],
    transport: Recorder,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stubs = db(local=[named("deviation_summary", "deviation_summary_v1")])
    transport.respond = lambda _: page(meta_template("deviation_summary_v1", "APPROVED"))

    with caplog.at_level(logging.DEBUG):
        resposta = _sync(client, cabecalho)

    assert resposta.status_code == 200
    assert TOKEN not in caplog.text
    assert TOKEN not in resposta.text
    for statement, params in zip(stubs.bound.statements, stubs.bound.params, strict=True):
        assert TOKEN not in statement
        assert TOKEN not in _all_text(params)


#: A premissa do caso real: a Meta pode devolver `paging.next` com o token na
#: query string. Aí a URL da segunda página É o token — e o `httpx` loga a URL.
_NEXT_WITH_TOKEN = f"{_TEMPLATES_URL}?access_token={TOKEN}&after=1"


def _second_page_refuses(request: httpx.Request) -> httpx.Response:
    if "after" in request.url.params:
        return httpx.Response(401, json={"token": TOKEN})
    return page(meta_template("t0", "APPROVED"), next=_NEXT_WITH_TOKEN)


async def test_gate_4_a_defesa_do_log_e_o_verification_client(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """O par que prova a defesa: o mesmo transporte, com um `AsyncClient` cru,
    loga `HTTP Request: GET …access_token=<valor>…` em INFO; com o
    `verification_client`, nada. ⛔ Mutação: tirar o `setLevel` de
    `verification_client` deixa a segunda metade vermelha."""
    _reset_http_loggers()
    with caplog.at_level(logging.DEBUG):
        async with httpx.AsyncClient(transport=httpx.MockTransport(_second_page_refuses)) as raw:
            with pytest.raises(InvalidCredentialError):
                await meta_cloud.list_templates({"waba_id": WABA_ID}, TOKEN, raw)
    assert TOKEN in caplog.text  # o positivo: sem a defesa, a URL vai para o log
    assert any(r.name == "httpx" and TOKEN in r.getMessage() for r in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        async with verification_client(transport=httpx.MockTransport(_second_page_refuses)) as http:
            with pytest.raises(InvalidCredentialError) as erro:
                await meta_cloud.list_templates({"waba_id": WABA_ID}, TOKEN, http)
    assert erro.value.code == "unauthorized"
    assert TOKEN not in caplog.text
    _reset_http_loggers()


async def test_gate_4_a_defesa_da_cadeia_e_o_from_none() -> None:
    """Falha de transporte na segunda página, cuja URL carrega o token: a
    exceção do `httpx` soletra a URL. A nossa nasce `from None` e a cadeia morre
    ali. ⛔ Mutação: `raise … from None` → `raise …` deixa isto vermelho — o
    `format_exception` imprimiria "During handling of the above exception" com
    a mensagem de baixo, que é o token."""
    swallowed: list[BaseException] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "after" in request.url.params:
            erro = httpx.ConnectError(f"connection refused by {request.url}", request=request)
            swallowed.append(erro)
            raise erro
        return page(meta_template("t0", "APPROVED"), next=_NEXT_WITH_TOKEN)

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(InvalidCredentialError) as erro:
            await meta_cloud.list_templates({"waba_id": WABA_ID}, TOKEN, http)

    formatado = "".join(traceback.format_exception(erro.value))
    assert erro.value.code == "unreachable"
    assert erro.value.__suppress_context__ is True
    assert TOKEN not in str(erro.value)
    assert TOKEN not in formatado
    assert "ConnectError" not in formatado
    # O positivo: o que a cadeia carregaria, se existisse, é o token.
    [engolida] = swallowed
    assert TOKEN in str(engolida)


async def test_gate_4_o_401_da_meta_nao_carrega_o_corpo_na_excecao() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"token": TOKEN, "url": str(request.url)})

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(InvalidCredentialError) as erro:
            await meta_cloud.list_templates({"waba_id": WABA_ID}, TOKEN, http)

    formatado = "".join(traceback.format_exception(erro.value))
    assert erro.value.code == "unauthorized"
    assert TOKEN not in formatado


def test_meta_template_nao_carrega_o_token() -> None:
    """A estrutura devolvida tem quatro campos, e nenhum é o token."""
    campos = {f for f in meta_cloud.MetaTemplate.__slots__}  # type: ignore[attr-defined]
    assert campos == {"name", "language", "status", "rejected_reason"}


# ---------------------------------------------------------------------------
# Os códigos de recusa novos têm frase
# ---------------------------------------------------------------------------
def _refusal_codes_in_route() -> set[str]:
    """Todo `_REFUSALS["<code>"]` escrito em `canais.py`, pelo `ast`."""
    assert canais.__file__ is not None
    tree = ast.parse(Path(canais.__file__).read_text(encoding="utf-8"))
    return {
        node.slice.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "_REFUSALS"
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
    }


def test_todo_codigo_de_recusa_da_rota_e_do_provedor_tem_frase() -> None:
    """`_REFUSALS[code]` sem a chave é um 500 na cara do operador."""
    codes = _refusal_codes_in_route()
    assert {"no_official_provider", "no_credential"} <= codes
    assert codes <= set(canais._REFUSALS), codes - set(canais._REFUSALS)
    assert _codes_raised(meta_cloud) <= set(canais._REFUSALS)
    assert {"unauthorized", "unreachable", "malformed"} <= _codes_raised(meta_cloud)


def test_o_token_do_cofre_e_lido_pela_chave_que_o_formulario_declara_secreta() -> None:
    """A chave não é escrita à mão na rota: vem de `FieldSpec.secret`, como no
    `save_credential`. Renomear o campo move os dois lados juntos."""
    assert canais._META_TOKEN_KEY == "token"
    assert [s.name for s in meta_cloud.FIELDS if s.secret] == [canais._META_TOKEN_KEY]


def test_o_waba_id_e_nao_secreto_e_fica_entre_o_numero_e_o_token() -> None:
    nomes = [s.name for s in meta_cloud.FIELDS]
    assert nomes == ["phone_number_id", "waba_id", "token"]
    waba = meta_cloud.FIELDS[1]
    assert waba.secret is False
    assert waba.inputmode == "numeric" and waba.autocomplete == "off"
    assert waba.pattern == r"[0-9]{5,32}"
    assert "WABA" in waba.label_pt
