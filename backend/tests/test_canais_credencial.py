"""A credencial do canal: valida antes, grava no cofre, e o valor não sai por lugar nenhum.

Três portões (SPRINTS-CANAIS, C2), e o terceiro é o que costuma escapar:

1. credencial inválida **não grava nada** — a rota nem abre a transação;
2. nenhum `GET` devolve o segredo, em nenhum campo, em nenhum estado;
3. **o token não aparece no log nem na mensagem de erro** — o `httpx` loga a URL
   inteira em INFO, e no `z_api` o token está na URL. O teste captura em DEBUG e
   varre; tirar a defesa do logger em `verification_client` deixa o do `z_api`
   vermelho, e trocar `raise … from None` por `raise …` deixa o da cadeia
   vermelho.

⚠️ O QUE ESTA SUÍTE NÃO PODE PROVAR
Nada aqui toca banco nem rede. O cofre de verdade — ciphertext ≠ valor, ida e
volta, `count` de `vault.secrets` que não cresce ao regravar, isolamento pelo
`join`, atomicidade no Postgres — é `scripts/97_teste_canais.py`, no
`make db-test`, executando o SQL real destes módulos. E `util.is_admin` é
função do banco: aqui o stub responde `admin`, e é o `97` que prova que `owner`
e `hr` recebem `true` e `unit_supervisor` e `executive` recebem `false`.
"""

from __future__ import annotations

import ast
import json
import logging
import re
import traceback
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from operax.alertas import capacidades
from operax.alertas.capacidades import WHATSAPP_PROVIDERS
from operax.alertas.provedores import PROVIDERS, meta_cloud, uazapi, z_api
from operax.alertas.provedores.base import (
    FieldError,
    InvalidCredentialError,
    check_fields,
    verification_client,
)
from operax.core import vault
from operax.core.tenant import (
    MissingTenantFilterError,
    SystemContext,
    TenantScope,
    bind_tenant,
)
from server.main import app
from server.routers import canais

TENANT_ID = "22222222-2222-4222-8222-222222222222"
INTEGRATION_ID = UUID("33333333-3333-4333-8333-333333333331")

#: Valores de teste, óbvios de propósito. Nenhum é real.
TOKEN = "token-de-teste-nao-e-real"
CLIENT_TOKEN = "client-token-de-teste-nao-e-real"

#: Um formulário válido por provedor, com o segredo em cada campo secreto.
WABA_ID = "102030405060708"
VALID_FIELDS: dict[str, dict[str, str]] = {
    meta_cloud.NAME: {"phone_number_id": "123456789012345", "waba_id": WABA_ID, "token": TOKEN},
    z_api.NAME: {"instance_id": "3C4E5F6A7B8C9D0E", "token": TOKEN, "client_token": CLIENT_TOKEN},
    uazapi.NAME: {"base_url": "https://instancia.exemplo.test", "token": TOKEN},
}


# ---------------------------------------------------------------------------
# O transporte falso, e o que cada provedor responde quando aceita
# ---------------------------------------------------------------------------
def _accepts(module: ModuleType) -> dict[str, Any]:
    if module is meta_cloud:
        return {"verified_name": "FastPark", "display_phone_number": "+55 21 99999-0000"}
    if module is z_api:
        return {"connected": True, "smartphoneConnected": True}
    return {"instance": {"status": "connected", "owner": "5521999990000"}}


class Recorder:
    """Um `MockTransport` que guarda cada requisição e responde o que lhe for dito."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.respond: Callable[[httpx.Request], httpx.Response] = lambda _: httpx.Response(200)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.respond(request)

    def accept(self, module: ModuleType) -> None:
        self.respond = lambda _: httpx.Response(200, json=_accepts(module))

    def refuse_echoing_the_token(self) -> None:
        """O caso real do gate 3: o provedor devolve o token no corpo do 401."""
        self.respond = lambda request: httpx.Response(
            401,
            json={"error": "invalid token", "token": TOKEN, "url": str(request.url)},
        )


def _reset_http_loggers() -> None:
    """Sem isto a defesa de um teste anterior mascararia a mutação neste."""
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.NOTSET)


@pytest.fixture
def transport(client: TestClient) -> Iterator[Recorder]:
    """Troca o cliente HTTP da rota por um `MockTransport` — construído pela
    mesma `verification_client`, que é onde a defesa do log vive."""
    recorder = Recorder()

    async def override() -> Any:
        _reset_http_loggers()
        async with verification_client(transport=httpx.MockTransport(recorder.handler)) as http:
            yield http

    app.dependency_overrides[canais.get_http_client] = override
    yield recorder
    _reset_http_loggers()


# ---------------------------------------------------------------------------
# O banco falso: responde pelo assunto da instrução, e guarda o que foi pedido
# ---------------------------------------------------------------------------
class StubScope:
    def __init__(self, answers: dict[str, Any]) -> None:
        self._answers = answers
        self.statements: list[str] = []
        self.params: list[Any] = []
        self._current: Any = None

    async def execute(self, statement: str, params: Any = None) -> None:
        self.statements.append(statement)
        self.params.append(params)
        answer = next(
            (value for marker, value in self._answers.items() if marker in statement),
            None,
        )
        if isinstance(answer, Exception):
            raise answer
        self._current = answer

    async def fetchone(self) -> dict[str, Any] | None:
        return self._current

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._current or []


class StubScopeContext:
    def __init__(self, scope: StubScope) -> None:
        self._scope = scope
        self.opened = 0
        self.exited_with: type[BaseException] | None = None

    async def __aenter__(self) -> StubScope:
        self.opened += 1
        return self._scope

    async def __aexit__(self, exc_type: type[BaseException] | None, *exc: object) -> None:
        self.exited_with = exc_type
        return None


def status_row(**overrides: Any) -> dict[str, Any]:
    return {
        "provider": meta_cloud.NAME,
        "public_identity": "FastPark (+55 21 99999-0000)",
        "updated_at": "2026-09-13T12:00:00+00:00",
    } | overrides


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch):
    """Instala os dois escopos e devolve `(user, bound)` — o segundo com os
    contextos, para saber se a transação abriu e com o que ela fechou."""

    def install(
        *,
        admin: bool = True,
        status: dict[str, Any] | None = None,
        create_failures: int = 0,
    ) -> tuple[StubScope, StubScope, StubScopeContext]:
        user = StubScope({"util.is_admin": {"admin": admin}})
        creates = {"n": 0}

        class InjectedFailureError(Exception):
            pass

        bound = StubScope(
            {
                "set active = false": [],
                "insert into app.integration (": {"id": INTEGRATION_ID},
                "vault.update_secret": None,
                "vault.create_secret": {"vault_id": UUID("44444444-4444-4444-8444-444444444441")},
                "max(s.updated_at)": status if status is not None else status_row(),
                "insert into app.audit_log": None,
            }
        )
        original = bound.execute

        async def execute(statement: str, params: Any = None) -> None:
            if "vault.create_secret" in statement:
                creates["n"] += 1
                if creates["n"] > 1 and create_failures:
                    bound.statements.append(statement)
                    bound.params.append(params)
                    raise InjectedFailureError("injected: second secret failed")
            await original(statement, params)

        bound.execute = execute  # type: ignore[method-assign]
        bound_ctx = StubScopeContext(bound)
        monkeypatch.setattr(canais, "user_scope", lambda _t: StubScopeContext(user))
        monkeypatch.setattr(canais, "tenant_scope", lambda _t: bound_ctx)
        return user, bound, bound_ctx

    return install


@pytest.fixture
def cabecalho(issue_token: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token()}"}


def _post(client: TestClient, cabecalho: dict[str, str], provider: str, fields: dict[str, str]):
    return client.post(
        "/canais/credencial",
        json={"provider": provider, "fields": fields},
        headers=cabecalho,
    )


def _flatten(value: Any) -> Any:
    """`Jsonb` aberto e mapeamentos percorridos — nunca `str()` de um `Jsonb`.

    ⛔ `str(Jsonb(...))` do psycopg trunca em 35 caracteres. Uma varredura que
    fizesse `str(v)` dos parâmetros não veria dentro de `config`, `antes` nem
    `depois` — e gravar o token na auditoria passaria verde. Foi a mutação que
    sobreviveu ao ciclo 1.
    """
    if isinstance(value, Jsonb):
        return _flatten(value.obj)
    if isinstance(value, Mapping):
        return {str(k): _flatten(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_flatten(v) for v in value]
    return str(value)


def _all_text(*values: Any) -> str:
    """Tudo que passou por uma instrução, achatado, para varrer."""
    return json.dumps([_flatten(v) for v in values], ensure_ascii=False)


def test_a_varredura_enxerga_dentro_de_jsonb() -> None:
    """O par do `_flatten`: um valor enterrado num `Jsonb` longo é achado."""
    enterrado = Jsonb({"a": "x" * 60, "b": {"c": [TOKEN]}})
    assert TOKEN not in str(enterrado)  # o `str` trunca — é por isso que existe `_flatten`
    assert TOKEN in _all_text({"depois": enterrado})


# ---------------------------------------------------------------------------
# Critério 6 — o registro e a matriz são o mesmo conjunto; todo formulário tem
# o que guardar e o que mostrar
# ---------------------------------------------------------------------------
def test_o_registro_de_provedores_e_a_matriz_nos_dois_sentidos() -> None:
    """Um módulo que a matriz não conhece é um provedor que a tela pode escolher
    e a API não verifica; um nome da matriz sem módulo, o contrário. A allowlist
    de literais cresceu para `provedores/*.py` em troca desta igualdade."""
    assert set(PROVIDERS) == set(WHATSAPP_PROVIDERS)
    for name, module in PROVIDERS.items():
        assert module.NAME == name


@pytest.mark.parametrize("provider", WHATSAPP_PROVIDERS)
def test_todo_formulario_tem_um_segredo_e_um_nao_segredo(provider: str) -> None:
    """Sem campo secreto não há o que guardar no cofre; sem campo não-secreto
    não há o que mostrar em `config`."""
    specs = PROVIDERS[provider].FIELDS
    assert any(spec.secret for spec in specs)
    assert any(not spec.secret for spec in specs)
    for spec in specs:
        re.compile(spec.pattern)
        assert spec.name and spec.label_pt and spec.hint_pt
        if spec.secret:
            # `new-password` convida o navegador a SALVAR o token; `off` não
            # impede o autofill. Só estes dois não fazem nenhuma das duas coisas.
            assert spec.autocomplete in {"one-time-code", "new-password"}


# O navegador compila o atributo `pattern` como regex JavaScript com a flag `v`
# (HTML, "compiled pattern regular expression"), e nesse dialeto estes caracteres
# só entram numa classe `[...]` escapados — `-` inclusive, fora de um intervalo
# `a-z`. O `re` do Python e o `new RegExp` sem flag do Zod aceitam os dois
# jeitos; só o atributo é descartado, em silêncio, e a tela perde a dica nativa.
_V_CLASS_SYNTAX = frozenset("()[]{}/-|")


def _v_flag_violations(pattern: str) -> set[str]:
    """Os caracteres que a flag `v` recusaria dentro das classes de `pattern`."""
    violations: set[str] = set()
    for body in re.findall(r"(?<!\\)\[((?:\\.|[^\]])*)\]", pattern):
        bare = re.sub(r"\\.", "", body)  # escapes are always fine
        bare = re.sub(r"[^-]-[^-]", "", bare)  # ranges are the one bare `-`
        violations |= set(bare) & _V_CLASS_SYNTAX
    return violations


def test_a_sonda_do_dialeto_v_distingue_o_hifen_solto_do_escapado() -> None:
    """A sentinela do teste abaixo: cega a `-` solto, ele passaria com o padrão
    velho, que o Chrome descartava com um aviso no console."""
    assert _v_flag_violations(r"[A-Za-z0-9._-]+") == {"-"}
    assert _v_flag_violations(r"https://[A-Za-z0-9.-]+(/[a-z-]+)*") == {"-"}
    assert _v_flag_violations(r"[a-z/]") == {"/"}
    assert _v_flag_violations(r"[A-Za-z0-9._\-]+") == set()
    assert _v_flag_violations(r"[0-9]{5,32}") == set()


@pytest.mark.parametrize("provider", WHATSAPP_PROVIDERS)
def test_todo_pattern_compila_no_dialeto_v_do_navegador(provider: str) -> None:
    for spec in PROVIDERS[provider].FIELDS:
        assert _v_flag_violations(spec.pattern) == set(), spec.name


def test_os_valores_validos_passam_pelo_padrao_de_cada_campo() -> None:
    """O positivo do critério 1: um padrão que recusa tudo passaria no negativo."""
    for provider, fields in VALID_FIELDS.items():
        assert check_fields(PROVIDERS[provider].FIELDS, fields) == fields


def test_o_formulario_da_api_descreve_cada_campo_como_o_modulo_declara(
    client: TestClient, cabecalho: dict[str, str]
) -> None:
    corpo = client.get("/canais/provedores", headers=cabecalho).json()

    assert [form["provider"] for form in corpo] == list(WHATSAPP_PROVIDERS)
    for form in corpo:
        specs = PROVIDERS[form["provider"]].FIELDS
        assert [f["name"] for f in form["fields"]] == [s.name for s in specs]
        assert [f["secret"] for f in form["fields"]] == [s.secret for s in specs]
        assert [f["pattern"] for f in form["fields"]] == [s.pattern for s in specs]
        assert set(form["fields"][0]) == {
            "name",
            "label",
            "pattern",
            "autocomplete",
            "inputmode",
            "secret",
            "placeholder",
            "hint",
        }
        assert set(form["capabilities"]) == {
            "official",
            "requires_templates",
            "ban_risk",
            "requires_recipient_opt_in",
        }


# ---------------------------------------------------------------------------
# Critério 1 — formato inválido é recusado ANTES de qualquer HTTP, nomeando o campo
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("provider", "field", "bad"),
    [
        (meta_cloud.NAME, "phone_number_id", "gestor@fastpark.com.br"),
        (meta_cloud.NAME, "phone_number_id", "12345abc"),
        (uazapi.NAME, "base_url", "http://instancia.exemplo.test"),
        (z_api.NAME, "instance_id", "abc/../etc"),
        (z_api.NAME, "token", "token com espaco"),
    ],
)
def test_formato_invalido_e_422_nomeando_o_campo_sem_chamar_o_provedor(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Any,
    transport: Recorder,
    provider: str,
    field: str,
    bad: str,
) -> None:
    """§5.4: o e-mail que o autofill despeja no campo numérico morre aqui, com a
    frase "isto não parece…", e não com um erro da Graph API."""
    _, bound, bound_ctx = db()
    transport.accept(PROVIDERS[provider])

    resposta = _post(client, cabecalho, provider, VALID_FIELDS[provider] | {field: bad})

    assert resposta.status_code == 422
    corpo = resposta.json()
    assert corpo["code"] == "invalid_format"
    assert corpo["field"] == field
    assert "não parece" in corpo["detail"]
    assert bad not in resposta.text
    assert transport.requests == []
    assert bound_ctx.opened == 0


def test_campo_que_o_provedor_nao_declara_e_recusado(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder
) -> None:
    """Ignorar um campo a mais gravaria menos do que o operador acha que gravou."""
    db()
    resposta = _post(client, cabecalho, meta_cloud.NAME, VALID_FIELDS[meta_cloud.NAME] | {"x": "1"})

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "unknown_field"
    assert transport.requests == []


def test_provedor_desconhecido_e_422(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder
) -> None:
    db()
    resposta = _post(client, cabecalho, "evolution_api", {"token": TOKEN})

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "unknown_provider"
    assert transport.requests == []


def test_check_fields_nomeia_o_campo_e_nao_carrega_o_valor() -> None:
    with pytest.raises(FieldError) as erro:
        check_fields(meta_cloud.FIELDS, {"phone_number_id": "abc", "token": TOKEN})

    assert erro.value.name == "phone_number_id"
    assert erro.value.spec is meta_cloud.FIELDS[0]
    assert "abc" not in str(erro.value)
    assert TOKEN not in str(erro.value)


def test_check_fields_tira_o_espaco_em_volta_do_valor_colado() -> None:
    """Token colado vem com espaço e quebra de linha mais vezes do que não. Sem o
    `strip`, o padrão recusa um valor certo — e o operador não entende por quê."""
    colado = {
        "phone_number_id": " 123456789012345 ",
        "waba_id": f"{WABA_ID}\n",
        "token": f" {TOKEN}\n",
    }

    assert check_fields(meta_cloud.FIELDS, colado) == VALID_FIELDS[meta_cloud.NAME]


def _codes_raised(module: ModuleType) -> set[str]:
    """Todo `InvalidCredentialError("<code>")` escrito no módulo, pelo `ast`."""
    assert module.__file__ is not None
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    return {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "InvalidCredentialError"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }


@pytest.mark.parametrize("provider", WHATSAPP_PROVIDERS)
def test_todo_codigo_de_recusa_do_provedor_tem_frase_na_rota(provider: str) -> None:
    """`_REFUSALS[code]` sem a chave é um 500 na cara do operador. Cada código
    que um módulo levanta tem de ter frase; e cada módulo levanta ao menos um
    (senão a leitura por `ast` estaria olhando o arquivo errado)."""
    codes = _codes_raised(PROVIDERS[provider])

    assert codes
    assert codes <= set(canais._REFUSALS), codes - set(canais._REFUSALS)


# ---------------------------------------------------------------------------
# Critério 2 / Gate 1 — verificação falha → nada gravado; passa → gravado
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("provider", WHATSAPP_PROVIDERS)
def test_provedor_que_recusa_e_422_e_a_transacao_nem_abre(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder, provider: str
) -> None:
    """Gate 1. "Nada é gravado se a validação falhar" (§5.2) é literal: a rota
    não abre `tenant_scope` antes de o provedor dizer sim."""
    _, bound, bound_ctx = db()
    transport.refuse_echoing_the_token()

    resposta = _post(client, cabecalho, provider, VALID_FIELDS[provider])

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "unauthorized"
    assert len(transport.requests) == 1
    assert bound_ctx.opened == 0
    assert bound.statements == []


@pytest.mark.parametrize("provider", WHATSAPP_PROVIDERS)
def test_provedor_que_aceita_grava_e_responde_configurado(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder, provider: str
) -> None:
    """O positivo do gate 1: uma linha em `integration`, um segredo no cofre por
    campo secreto, e a resposta diz que existe — com a identidade pública."""
    module = PROVIDERS[provider]
    _, bound, bound_ctx = db(status=status_row(provider=provider))
    transport.accept(module)

    resposta = _post(client, cabecalho, provider, VALID_FIELDS[provider])

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["configured"] is True
    assert corpo["provider"] == provider
    assert corpo["public_identity"]
    assert bound_ctx.opened == 1
    assert bound_ctx.exited_with is None

    secretos = [spec.name for spec in module.FIELDS if spec.secret]
    upserts = [s for s in bound.statements if "insert into app.integration (" in s]
    creates = [s for s in bound.statements if "vault.create_secret" in s]
    assert len(upserts) == 1
    assert len(creates) == len(secretos)


def test_o_config_da_integracao_leva_so_os_campos_nao_secretos(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder
) -> None:
    """`secret: True` virando `False` faria o token parar em `config`, que o
    painel lê. O que o upsert recebe é exatamente o não-secreto mais a
    identidade pública."""
    _, bound, _ = db()
    transport.accept(z_api)

    _post(client, cabecalho, z_api.NAME, VALID_FIELDS[z_api.NAME])

    [params] = [
        p for s, p in zip(bound.statements, bound.params, strict=True) if "on conflict" in s
    ]
    config = params["config"].obj
    assert config == {
        "instance_id": VALID_FIELDS[z_api.NAME]["instance_id"],
        "public_identity": "instância 3C4E5F6A7B8C9D0E conectada",
    }
    assert TOKEN not in json.dumps(config)
    assert CLIENT_TOKEN not in json.dumps(config)


def test_cada_campo_secreto_vai_para_o_cofre_como_parametro_ligado(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder
) -> None:
    """O valor entra em `%(value)s`, nunca no texto da instrução."""
    _, bound, _ = db()
    transport.accept(z_api)

    _post(client, cabecalho, z_api.NAME, VALID_FIELDS[z_api.NAME])

    stores = [
        (s, p)
        for s, p in zip(bound.statements, bound.params, strict=True)
        if "vault.create_secret" in s
    ]
    assert {p["key"] for _, p in stores} == {"token", "client_token"}
    assert {p["value"] for _, p in stores} == {TOKEN, CLIENT_TOKEN}
    for statement, _ in stores:
        assert TOKEN not in statement
        assert CLIENT_TOKEN not in statement


@pytest.mark.parametrize("provider", WHATSAPP_PROVIDERS)
def test_todo_campo_enviado_cai_em_exatamente_um_dos_dois_lugares(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder, provider: str
) -> None:
    """A invariante que `FieldSpec.secret` promete: secreto → cofre, o resto →
    `config`, nenhum campo em nenhum lugar e nenhum nos dois. É a rota que
    decide, de `FIELDS`; `verify` devolve só a identidade. Virar a flag de um
    campo move o campo — a mutação M6 do revisor agora mostra `client_token`
    dentro de `config`, não descartado."""
    module = PROVIDERS[provider]
    _, bound, _ = db()
    transport.accept(module)

    _post(client, cabecalho, provider, VALID_FIELDS[provider])

    no_cofre = {
        p["key"]
        for s, p in zip(bound.statements, bound.params, strict=True)
        if "vault.create_secret" in s
    }
    [upsert] = [
        p for s, p in zip(bound.statements, bound.params, strict=True) if "on conflict" in s
    ]
    em_config = set(upsert["config"].obj) - {"public_identity"}

    esperado_cofre = {spec.name for spec in module.FIELDS if spec.secret}
    esperado_config = {spec.name for spec in module.FIELDS if not spec.secret}
    assert no_cofre == esperado_cofre
    assert em_config == esperado_config
    assert no_cofre.isdisjoint(em_config)
    assert no_cofre | em_config == set(VALID_FIELDS[provider])
    if module is meta_cloud:
        # O C2b acrescentou o `waba_id` como não-secreto: é de `config` que a
        # sincronização de templates o lê, e do cofre que lê o token.
        assert "waba_id" in em_config
        assert upsert["config"].obj["waba_id"] == WABA_ID


def test_a_identidade_publica_e_truncada_ao_montar(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder
) -> None:
    """É string do provedor, sem limite do lado de lá; aqui vira frase de tela,
    e vai para `config` e para a auditoria. 120 é o teto, nos três lugares."""
    _, bound, _ = db(status=status_row(public_identity="x" * 500))
    transport.respond = lambda _: httpx.Response(
        200, json={"verified_name": "N" * 500, "display_phone_number": "+55"}
    )

    _post(client, cabecalho, meta_cloud.NAME, VALID_FIELDS[meta_cloud.NAME])

    [upsert] = [
        p for s, p in zip(bound.statements, bound.params, strict=True) if "on conflict" in s
    ]
    [audit] = [
        p for s, p in zip(bound.statements, bound.params, strict=True) if "app.audit_log" in s
    ]
    assert len(upsert["config"].obj["public_identity"]) == canais._IDENTITY_MAX_CHARS
    assert len(audit["depois"].obj["public_identity"]) == canais._IDENTITY_MAX_CHARS


def test_a_desativacao_so_alcanca_o_que_esta_ativo() -> None:
    """Sem `and active`, o `returning` devolve toda linha de WhatsApp do tenant,
    ativa ou não, e `previous[0]` é ordem de heap: o `antes` da auditoria nomeia
    o provedor errado. Textual aqui; quem executa com `meta_cloud` inativo ao
    lado de `z_api` ativo é o `97`."""
    assert re.search(r"\band active\b", canais._DEACTIVATE_SQL)


# ---------------------------------------------------------------------------
# Critério 3 / Gate 2 — o valor não volta em campo nenhum, em estado nenhum
# ---------------------------------------------------------------------------
def test_get_credencial_nao_devolve_valor_nem_vault_id_mesmo_envenenado(
    client: TestClient, cabecalho: dict[str, str], db: Any
) -> None:
    """Olha o corpo que saiu pelo socket. A linha do stub vem com o que uma
    consulta descuidada traria junto; a resposta tem só o contrato."""
    db(status=status_row(vault_id="0d5f6b2e-0000-0000-0000-000000000000", token=TOKEN))

    resposta = client.get("/canais/credencial", headers=cabecalho)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {"configured", "provider", "updated_at", "public_identity"}
    assert corpo["configured"] is True
    assert TOKEN not in resposta.text
    assert "vault" not in resposta.text.lower()
    assert "0d5f6b2e" not in resposta.text


def test_get_credencial_sem_credencial_diz_que_nao_ha(
    client: TestClient, cabecalho: dict[str, str], db: Any
) -> None:
    """O estado da produção hoje. Não é 404: a tela existe para dizer isto."""
    _, bound, _ = db(status={})
    bound._answers["max(s.updated_at)"] = None

    corpo = client.get("/canais/credencial", headers=cabecalho).json()

    assert corpo == {
        "configured": False,
        "provider": None,
        "updated_at": None,
        "public_identity": None,
    }


def test_post_nao_devolve_o_valor_em_campo_nenhum(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder
) -> None:
    db(status=status_row(provider=z_api.NAME, token=TOKEN))
    transport.accept(z_api)

    resposta = _post(client, cabecalho, z_api.NAME, VALID_FIELDS[z_api.NAME])

    assert resposta.status_code == 200
    assert set(resposta.json()) == {"configured", "provider", "updated_at", "public_identity"}
    assert TOKEN not in resposta.text
    assert CLIENT_TOKEN not in resposta.text
    assert "vault" not in resposta.text.lower()


def test_a_consulta_do_estado_le_so_a_identidade_publica_do_config() -> None:
    """Nem `vault_id`, nem `config` inteiro, nem `select *`."""
    sql = canais._CREDENTIAL_STATUS_SQL.lower()
    assert "vault_id" not in sql
    assert "*" not in sql
    assert "config ->> 'public_identity'" in sql
    assert "app.integration_secret" in sql  # é o join com o ponteiro que define "configurada"


def test_o_422_nativo_nao_ecoa_o_corpo(client: TestClient, cabecalho: dict[str, str]) -> None:
    """Medido antes do handler em `server/main.py`: sem `provider`, o 422 do
    FastAPI devolvia o token dentro de `input`. Agora `type`, `loc` e `msg`
    ficam; o eco, não."""
    resposta = client.post(
        "/canais/credencial", json={"fields": {"token": TOKEN}}, headers=cabecalho
    )

    assert resposta.status_code == 422
    assert TOKEN not in resposta.text
    [erro] = resposta.json()["detail"]
    assert erro["loc"] == ["body", "provider"]
    assert "input" not in erro


# ---------------------------------------------------------------------------
# Critério 4 / Gate 3 — nem no log, nem na exceção, nem na cadeia, nem no detail
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("provider", WHATSAPP_PROVIDERS)
def test_gate_3_o_token_nao_aparece_no_log_em_debug_nem_no_detail(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Any,
    transport: Recorder,
    caplog: pytest.LogCaptureFixture,
    provider: str,
) -> None:
    """O provedor devolve 401 com o token no corpo; no `z_api` ele também está na
    URL, que o `httpx` loga em INFO. Captura em DEBUG no logger raiz e varre.

    ⛔ Mutação obrigatória: tirar o `setLevel` de `verification_client` deixa o
    caso `z_api` vermelho — é a linha `HTTP Request: GET …/token/<valor>/status`.
    """
    db()
    transport.refuse_echoing_the_token()

    with caplog.at_level(logging.DEBUG):
        resposta = _post(client, cabecalho, provider, VALID_FIELDS[provider])

    assert resposta.status_code == 422
    assert TOKEN not in caplog.text
    assert CLIENT_TOKEN not in caplog.text
    assert TOKEN not in resposta.text
    assert CLIENT_TOKEN not in resposta.text
    # O que ficou no log é o código, e só ele.
    [recusa] = [r for r in caplog.records if r.name == canais.logger.name]
    assert "unauthorized" in recusa.getMessage()
    # E a premissa do caso real está de pé: no z_api o token ESTÁ na URL.
    if provider == z_api.NAME:
        assert TOKEN in str(transport.requests[0].url)


@pytest.mark.parametrize("provider", WHATSAPP_PROVIDERS)
async def test_gate_3_a_excecao_do_provedor_nao_carrega_o_valor_nem_a_cadeia(
    provider: str,
) -> None:
    """Direto no `verify`: um 401 com o token no corpo vira `InvalidCredentialError`
    cujo `str`, `code` e `traceback.format_exception` (que segue a cadeia) não
    contêm o valor."""
    module = PROVIDERS[provider]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"token": TOKEN, "url": str(request.url)})

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(InvalidCredentialError) as erro:
            await module.verify(VALID_FIELDS[provider], http)

    formatado = "".join(traceback.format_exception(erro.value))
    assert erro.value.code == "unauthorized"
    assert TOKEN not in str(erro.value)
    assert TOKEN not in formatado
    assert CLIENT_TOKEN not in formatado


@pytest.mark.parametrize("provider", WHATSAPP_PROVIDERS)
async def test_gate_3_a_falha_de_transporte_nao_arrasta_a_url_pela_cadeia(
    provider: str,
) -> None:
    """A exceção do `httpx` soletra a URL; a nossa nasce `from None` e a cadeia
    morre ali. ⛔ Mutação: `raise … from None` → `raise …` deixa isto vermelho,
    porque `format_exception` imprime "During handling of the above exception"
    com a mensagem de baixo — e no z_api a mensagem é o token."""
    module = PROVIDERS[provider]

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connection refused by {request.url}", request=request)

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(InvalidCredentialError) as erro:
            await module.verify(VALID_FIELDS[provider], http)

    formatado = "".join(traceback.format_exception(erro.value))
    assert erro.value.code == "unreachable"
    assert TOKEN not in formatado
    assert "ConnectError" not in formatado
    assert erro.value.__suppress_context__ is True


async def test_um_200_sem_os_campos_esperados_e_recusado_como_malformado() -> None:
    """Endpoint como premissa: se a forma da resposta não for a esperada, a
    credencial é recusada em vez de gravada com identidade inventada."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"something": "else"})

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        for provider in WHATSAPP_PROVIDERS:
            with pytest.raises(InvalidCredentialError) as erro:
                await PROVIDERS[provider].verify(VALID_FIELDS[provider], http)
            assert erro.value.code == "malformed"


async def test_instancia_desconectada_e_recusada_nos_nao_oficiais() -> None:
    """Credencial válida com o telefone despareado é um canal que não entrega."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.z-api.io":
            return httpx.Response(200, json={"connected": False})
        return httpx.Response(200, json={"instance": {"status": "disconnected"}})

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        for module in (z_api, uazapi):
            with pytest.raises(InvalidCredentialError) as erro:
                await module.verify(VALID_FIELDS[module.NAME], http)
            assert erro.value.code == "not_connected"


async def test_cada_provedor_manda_o_segredo_por_onde_a_premissa_diz() -> None:
    """As premissas de endpoint, presas: header Bearer e `fields` na Meta;
    caminho da URL e `Client-Token` na Z-API; header `token` na uazapi."""
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.setdefault(request.url.host, request)  # a primeira por host
        if request.url.host == "graph.facebook.com":
            return httpx.Response(200, json=_accepts(meta_cloud))
        if request.url.host == "api.z-api.io":
            return httpx.Response(200, json=_accepts(z_api))
        return httpx.Response(200, json=_accepts(uazapi))

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        meta = await meta_cloud.verify(VALID_FIELDS[meta_cloud.NAME], http)
        zapi = await z_api.verify(VALID_FIELDS[z_api.NAME], http)
        uaz = await uazapi.verify(VALID_FIELDS[uazapi.NAME], http)

    graph = seen["graph.facebook.com"]
    assert graph.headers["Authorization"] == f"Bearer {TOKEN}"
    assert graph.url.params["fields"] == "verified_name,display_phone_number"
    assert graph.url.path.endswith("/123456789012345")
    assert meta == "FastPark (+55 21 99999-0000)"

    z = seen["api.z-api.io"]
    assert z.url.path == f"/instances/3C4E5F6A7B8C9D0E/token/{TOKEN}/status"
    assert z.headers["Client-Token"] == CLIENT_TOKEN
    assert zapi == "instância 3C4E5F6A7B8C9D0E conectada"

    u = seen["instancia.exemplo.test"]
    assert u.url.path == "/instance/status"
    assert u.headers["token"] == TOKEN
    assert uaz == "5521999990000 conectado"


def test_meta_cloud_token_que_alcanca_o_numero_mas_nao_a_waba_e_recusado_sem_gravar(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder
) -> None:
    """C2b: validar antes de gravar (§5.2) vale para o `waba_id`. O transporte é
    roteado por caminho — o número responde 200, a WABA 400 — e a rota recusa
    com `unauthorized` sem abrir a transação. ⛔ Mutação: tirar a segunda
    requisição de `verify` deixa isto vermelho (o número sozinho aceita)."""
    _, bound, bound_ctx = db()

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(f"/{WABA_ID}"):
            return httpx.Response(400, json={"error": {"code": 100, "token": TOKEN}})
        return httpx.Response(200, json=_accepts(meta_cloud))

    transport.respond = respond

    resposta = _post(client, cabecalho, meta_cloud.NAME, VALID_FIELDS[meta_cloud.NAME])

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "unauthorized"
    assert TOKEN not in resposta.text
    assert len(transport.requests) == 2
    assert bound_ctx.opened == 0
    assert bound.statements == []


async def test_meta_cloud_verify_le_o_numero_e_depois_a_waba_com_o_mesmo_bearer() -> None:
    """O positivo: duas leituras, nesta ordem, as duas com o token no header, e a
    identidade continua sendo a do número."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_accepts(meta_cloud))

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        identidade = await meta_cloud.verify(VALID_FIELDS[meta_cloud.NAME], http)

    assert identidade == "FastPark (+55 21 99999-0000)"
    numero, waba = seen
    assert numero.url.path.endswith("/123456789012345")
    assert waba.url.path.endswith(f"/{WABA_ID}")
    assert waba.url.params["fields"] == "id"
    assert waba.headers["Authorization"] == numero.headers["Authorization"] == f"Bearer {TOKEN}"


async def test_a_defesa_do_log_e_reaplicada_a_cada_cliente() -> None:
    """A defesa é do ponto de construção, não da configuração de logging: um
    processo que zerou os níveis volta a tê-los no próximo cliente."""
    _reset_http_loggers()
    assert logging.getLogger("httpx").level == logging.NOTSET

    async with verification_client(transport=httpx.MockTransport(lambda _: httpx.Response(200))):
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
    _reset_http_loggers()


# ---------------------------------------------------------------------------
# Critério 5 — quem grava é o administrador; quem lê é qualquer membro
# ---------------------------------------------------------------------------
def test_nao_admin_recebe_403_antes_de_qualquer_http(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder
) -> None:
    """`util.is_admin` responde `false` para `unit_supervisor` e `executive` — o
    `97` prova a tabela; aqui, que o `false` vira 403 e que nada é chamado."""
    _, bound, bound_ctx = db(admin=False)
    transport.accept(meta_cloud)

    resposta = _post(client, cabecalho, meta_cloud.NAME, VALID_FIELDS[meta_cloud.NAME])

    assert resposta.status_code == 403
    assert "administrador" in resposta.json()["detail"]
    assert transport.requests == []
    assert bound_ctx.opened == 0


def test_admin_passa(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder
) -> None:
    """O par: `true` (`owner`, `hr`, `personnel`) grava. ⛔ Mutação: tirar a
    checagem do POST deixa o teste do 403 vermelho, não este."""
    db(admin=True)
    transport.accept(meta_cloud)

    resposta = _post(client, cabecalho, meta_cloud.NAME, VALID_FIELDS[meta_cloud.NAME])

    assert resposta.status_code == 200


def test_a_permissao_e_perguntada_ao_banco_como_o_usuario(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder
) -> None:
    user, _, _ = db()
    transport.accept(meta_cloud)

    _post(client, cabecalho, meta_cloud.NAME, VALID_FIELDS[meta_cloud.NAME])

    assert any("util.is_admin" in s for s in user.statements)
    assert user.params[0]["tenant_id"] == UUID(TENANT_ID)


def test_get_credencial_nao_exige_admin(
    client: TestClient, cabecalho: dict[str, str], db: Any
) -> None:
    """Como `/conexoes`: a tela diz que existe, e isso qualquer membro pode saber."""
    user, _, _ = db(admin=False)

    assert client.get("/canais/credencial", headers=cabecalho).status_code == 200
    assert user.statements == []


def test_get_provedores_nao_toca_o_banco(
    client: TestClient, cabecalho: dict[str, str], db: Any
) -> None:
    user, bound, _ = db()

    assert client.get("/canais/provedores", headers=cabecalho).status_code == 200
    assert user.statements == [] and bound.statements == []


# ---------------------------------------------------------------------------
# Critério 7 — a escrita é uma transação: falha no segundo segredo e nada fica
# ---------------------------------------------------------------------------
def test_falha_no_segundo_segredo_sai_pela_transacao_sem_auditar(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder
) -> None:
    """A exceção atravessa `tenant_scope`, que é quem faz o rollback — e a
    auditoria, que viria depois, não roda. Que o rollback desfaz o primeiro
    segredo E a linha de `vault.secrets` é o `97`, no Postgres."""
    _, bound, bound_ctx = db(create_failures=1)
    transport.accept(z_api)  # dois campos secretos

    with pytest.raises(Exception, match="injected"):
        _post(client, cabecalho, z_api.NAME, VALID_FIELDS[z_api.NAME])

    assert bound_ctx.opened == 1
    assert bound_ctx.exited_with is not None
    assert not any("insert into app.audit_log" in s for s in bound.statements)
    assert sum("vault.create_secret" in s for s in bound.statements) == 2


def test_a_verificacao_acontece_fora_da_transacao(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder
) -> None:
    """⛔ Mutação: `verify` chamado dentro do `tenant_scope` deixa isto vermelho.
    Uma verificação lenta segurando uma conexão do pool é o custo; a
    verificação recusada com a transação aberta é o risco."""
    _, bound, bound_ctx = db()
    opened_when_verified: list[int] = []

    def respond(_: httpx.Request) -> httpx.Response:
        opened_when_verified.append(bound_ctx.opened)
        return httpx.Response(200, json=_accepts(meta_cloud))

    transport.respond = respond

    _post(client, cabecalho, meta_cloud.NAME, VALID_FIELDS[meta_cloud.NAME])

    # Duas requisições no meta_cloud (o número e a WABA), as duas antes da transação.
    assert opened_when_verified == [0, 0]
    assert bound_ctx.opened == 1


# ---------------------------------------------------------------------------
# Critério 8 — a auditoria leva as chaves, nunca os valores
# ---------------------------------------------------------------------------
def test_audit_log_recebe_as_chaves_e_nao_os_valores(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder
) -> None:
    _, bound, _ = db()
    transport.accept(z_api)

    _post(client, cabecalho, z_api.NAME, VALID_FIELDS[z_api.NAME])

    [params] = [
        p for s, p in zip(bound.statements, bound.params, strict=True) if "app.audit_log" in s
    ]
    depois = params["depois"].obj
    assert depois["provider"] == z_api.NAME
    assert depois["keys"] == ["token", "client_token"]
    assert depois["public_identity"]
    assert TOKEN not in _all_text(params)
    assert CLIENT_TOKEN not in _all_text(params)
    assert params["user_id"] is not None
    assert params["entity_id"] == str(INTEGRATION_ID)


def test_nada_que_passou_pela_transacao_carrega_o_valor_fora_do_parametro_value(
    client: TestClient, cabecalho: dict[str, str], db: Any, transport: Recorder
) -> None:
    """A varredura inteira: em toda instrução e todo parâmetro da transação, o
    valor só existe em `params["value"]` das duas gravações no cofre."""
    _, bound, _ = db()
    transport.accept(z_api)

    _post(client, cabecalho, z_api.NAME, VALID_FIELDS[z_api.NAME])

    for statement, params in zip(bound.statements, bound.params, strict=True):
        assert TOKEN not in statement and CLIENT_TOKEN not in statement
        sem_value = {k: v for k, v in (params or {}).items() if k != "value"}
        assert TOKEN not in _all_text(sem_value)
        assert CLIENT_TOKEN not in _all_text(sem_value)


# ---------------------------------------------------------------------------
# O cofre, sem banco: o que dá para prender aqui
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "statement",
    [vault._UPDATE_SQL, vault._CREATE_SQL, vault._READ_SQL, canais._CREDENTIAL_STATUS_SQL],
)
def test_toda_instrucao_do_cofre_liga_o_tenant_pelo_join(statement: str) -> None:
    """`integration_secret` não tem `tenant_id`; o recorte é `i.tenant_id` no
    `join` com `app.integration`. ⛔ Mutação: tirar `%(tenant_id)s` do `join`
    do GET deixa isto vermelho — e `bind_tenant` recusaria a instrução em
    produção."""
    context = SystemContext(tenant_id=UUID(TENANT_ID), task="test")
    bound = bind_tenant(statement, {}, context)
    assert bound["tenant_id"] == UUID(TENANT_ID)
    assert "i.tenant_id = %(tenant_id)s" in statement


def test_bind_tenant_recusa_a_instrucao_sem_o_join_do_tenant() -> None:
    """O par: a checagem que o teste acima usa não é decorativa."""
    sem_tenant = vault._READ_SQL.replace("i.tenant_id = %(tenant_id)s", "true")
    assert sem_tenant != vault._READ_SQL
    with pytest.raises(MissingTenantFilterError):
        bind_tenant(sem_tenant, {}, SystemContext(tenant_id=UUID(TENANT_ID), task="test"))


class _Cursor:
    """O cursor mínimo que `TenantScope` embrulha, para provar o caminho do módulo."""

    def __init__(self, rows: list[dict[str, Any] | None]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, statement: str, params: dict[str, Any]) -> None:
        self.calls.append((statement, params))

    async def fetchone(self) -> dict[str, Any] | None:
        return self.rows.pop(0)

    async def fetchall(self) -> list[dict[str, Any]]:
        return []


def _scope(rows: list[dict[str, Any] | None]) -> tuple[TenantScope, _Cursor]:
    cursor = _Cursor(rows)
    return TenantScope(cursor, SystemContext(tenant_id=UUID(TENANT_ID), task="test")), cursor  # type: ignore[arg-type]


async def test_store_secret_atualiza_quando_o_ponteiro_existe() -> None:
    """⛔ Mutação: `update_secret` trocado por `create_secret` sempre duplica a
    linha de `vault.secrets` (o `97` conta); aqui, que a segunda instrução nem
    é emitida quando a primeira encontrou o ponteiro."""
    scope, cursor = _scope([{"vault_id": "x"}])

    await vault.store_secret(scope, INTEGRATION_ID, "token", TOKEN)

    [(statement, params)] = cursor.calls
    assert "vault.update_secret" in statement
    assert params["value"] == TOKEN
    assert params["tenant_id"] == UUID(TENANT_ID)
    assert TOKEN not in statement


async def test_store_secret_cria_quando_nao_existe() -> None:
    scope, cursor = _scope([None, {"vault_id": "x"}])

    await vault.store_secret(scope, INTEGRATION_ID, "token", TOKEN)

    emitidas = [("update" in s, "create" in s) for s, _ in cursor.calls]
    assert emitidas == [(True, False), (False, True)]
    _, params = cursor.calls[1]
    assert params["value"] == TOKEN
    assert params["key"] == "token"
    assert "name" not in params  # o nome nasce no SQL, do próprio ponteiro


async def test_store_secret_falha_alto_quando_a_integracao_nao_e_do_tenant() -> None:
    """Zero linha do `insert … select` é a integração de outro cliente. Gravar
    nada em silêncio seria pior do que vazar: o operador acharia que conectou."""
    scope, _ = _scope([None, None])

    with pytest.raises(vault.SecretNotStoredError) as erro:
        await vault.store_secret(scope, INTEGRATION_ID, "token", TOKEN)

    assert TOKEN not in str(erro.value)


async def test_read_secret_devolve_o_valor_ou_none() -> None:
    scope, _ = _scope([{"decrypted_secret": TOKEN}, None])

    assert await vault.read_secret(scope, INTEGRATION_ID, "token") == TOKEN
    assert await vault.read_secret(scope, INTEGRATION_ID, "token") is None


def test_o_nome_no_cofre_nasce_no_sql_do_proprio_ponteiro() -> None:
    """Determinístico por `(integration_id, key)` e `unique` no cofre: é o que
    faz a segunda gravação ser update e não colisão."""
    assert "'app.integration_secret/' || i.id || '/' || %(key)s" in vault._CREATE_SQL


# ---------------------------------------------------------------------------
# Critério 9 — zero literal de provedor fora da matriz e de `provedores/*.py`
# ---------------------------------------------------------------------------
def test_os_tres_arquivos_novos_da_rota_nao_escrevem_provedor() -> None:
    """`test_capacidades` varre o backend inteiro; este nomeia os três que o
    despacho exige em zero, para que a allowlist não cresça por descuido."""
    import ast
    from pathlib import Path

    for module in (canais, vault):
        assert module.__file__ is not None
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)}
        assert literals.isdisjoint(WHATSAPP_PROVIDERS), module.__name__

    models = Path(canais.__file__).parent.parent / "models.py"
    tree = ast.parse(models.read_text(encoding="utf-8"))
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)}
    assert literals.isdisjoint(WHATSAPP_PROVIDERS)
    assert capacidades.__file__ is not None
