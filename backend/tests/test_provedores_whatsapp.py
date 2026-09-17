"""Os três `enviar` de WhatsApp e a fábrica dos quatro (SPRINTS-CANAIS, C5, onda 1, metade B).

Cinco portões:

1. **o corpo exato** — para cada provedor, URL, método, cabeçalhos e JSON
   inteiro (`==` no dict), com três variáveis fora de ordem alfabética, para
   provar que a ordem é a de `variables` (`ordered()`) e não a de `facts`;
2. **`meta_cloud` nunca renderiza; `z_api` e `uazapi` só renderizam** — o
   oficial manda nome de template + parâmetros ordenados e não tem `render`
   nem no `ast`; os dois de QR mandam `render(body, message)` byte a byte, a
   mesma função do Telegram (SPEC-CANAIS §2, item 3);
3. **mapa de erro por tabela** — exceção, 401, 403, 429, 500, 4xx e JSON sem
   id, para os três; `error` é só o código, e o corpo do provedor não chega a
   `error`, a `repr(Delivery)` nem ao log;
4. **token e número em lugar nenhum** — sonda no token, no `Client-Token` e no
   destino; ausentes de `error`, de `caplog` em DEBUG com `httpx`/`httpcore`
   **incluídos**, e de `str(exc)` de qualquer exceção forçada. Para o `z_api`,
   cujo token está na URL, o par: o `AsyncClient` cru **falha** (a URL vai ao
   log), o `verification_client` passa;
5. **a fábrica cobre a matriz inteira e só ela** — `build` percorre
   `CHANNEL_PROVIDERS`, a partição secreto/não-secreto é a de `FIELDS`, um
   campo do lado errado é `KeyError` com o nome e nada mais, e o `ast` de
   `fabrica.py` não escreve provedor nenhum.

⚠️ O QUE ESTA SUÍTE NÃO PODE PROVAR
Nenhuma das três APIs foi chamada deste repositório: as formas de resposta são
premissa (docstring de cada módulo), e a primeira credencial real é a parada do
dono. O `MockTransport` prova o que sai, não o que a Meta, a Z-API ou o uazapi
respondem de verdade.
"""

from __future__ import annotations

import ast
import logging
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

from operax.alertas.capacidades import CHANNEL_PROVIDERS, UnknownProviderError
from operax.alertas.provedores import PROVIDERS, base, fabrica, meta_cloud, telegram, uazapi, z_api
from operax.alertas.provedores.base import (
    Delivery,
    Message,
    Provider,
    render,
    verification_client,
)
from tests.test_canais_credencial import (
    BOT_TOKEN,
    CLIENT_TOKEN,
    TOKEN,
    VALID_FIELDS,
    _reset_http_loggers,
)

DESTINATION = "+5521999990000"
DIGITS = "5521999990000"
PHONE_NUMBER_ID = VALID_FIELDS[meta_cloud.NAME]["phone_number_id"]
INSTANCE_ID = VALID_FIELDS[z_api.NAME]["instance_id"]
BASE_URL = VALID_FIELDS[uazapi.NAME]["base_url"]

#: Três variáveis fora de ordem alfabética, e `facts` numa terceira ordem: só
#: `ordered()` devolve `Shopping Norte, Colab Sonda, 2`.
VARIABLES = ("unit", "employee", "total")
FACTS = {"total": "2", "employee": "Colab Sonda", "unit": "Shopping Norte"}
BODY = "FastPark: {{2}} teve {{3}} indício(s) em {{1}}."
RENDERED = "FastPark: Colab Sonda teve 2 indício(s) em Shopping Norte."

#: O que um provedor poderia devolver no corpo de uma recusa. Nada disto chega
#: a `error`, a `repr(Delivery)` nem ao log.
PROBE = "sonda-do-corpo-do-provedor"
WAMID = "wamid.HBgLNTUyMTk5OTk5MDAwMBUCABEYEjNFQjA"
ZAPI_MESSAGE_ID = "3EB0-mensagem-zapi"
ZAPI_ZAAP_ID = "zaap-id-interno"
UAZ_MESSAGE_ID = "3EB0-mensagem-uazapi"


def _message(**overrides: Any) -> Message:
    campos: dict[str, Any] = {
        "destination": DESTINATION,
        "template": "deviation_individual",
        "variables": VARIABLES,
        "facts": FACTS,
        "body": BODY,
    }
    return Message(**(campos | overrides))


def _sent(request: httpx.Request) -> Any:
    """O JSON que o provedor mandou."""
    return httpx.Response(200, content=request.content).json()


def _tree(module: ModuleType) -> ast.Module:
    assert module.__file__ is not None
    return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))


def _meta(http: httpx.AsyncClient) -> Provider:
    return meta_cloud.MetaCloudProvider(PHONE_NUMBER_ID, TOKEN, http)


def _zapi(http: httpx.AsyncClient) -> Provider:
    return z_api.ZApiProvider(INSTANCE_ID, TOKEN, CLIENT_TOKEN, http)


def _uaz(http: httpx.AsyncClient) -> Provider:
    return uazapi.UazapiProvider(BASE_URL, TOKEN, http)


Make = Callable[[httpx.AsyncClient], Provider]
Respond = Callable[[httpx.Request], httpx.Response]


def _meta_ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "messaging_product": "whatsapp",
            "contacts": [{"input": DIGITS, "wa_id": DIGITS}],
            "messages": [{"id": WAMID}],
        },
    )


def _zapi_ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={"zaapId": ZAPI_ZAAP_ID, "messageId": ZAPI_MESSAGE_ID, "id": ZAPI_MESSAGE_ID}
    )


def _uaz_ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={"id": "uuid-interno", "messageid": UAZ_MESSAGE_ID, "chatid": f"{DIGITS}@s"}
    )


#: (fábrica do provedor, resposta que aceita, id esperado, módulo)
PROVIDERS_UNDER_TEST: list[tuple[Make, Respond, str, ModuleType]] = [
    (_meta, _meta_ok, WAMID, meta_cloud),
    (_zapi, _zapi_ok, ZAPI_MESSAGE_ID, z_api),
    (_uaz, _uaz_ok, UAZ_MESSAGE_ID, uazapi),
]
PROVIDER_IDS = [module.NAME for _, _, _, module in PROVIDERS_UNDER_TEST]


async def _enviar(
    make: Make, respond: Respond, message: Message | None = None
) -> tuple[Delivery, list[httpx.Request]]:
    """Um envio pelo `verification_client` — onde a defesa do log vive — que
    guarda a requisição. Nenhuma exceção pode sair; se sair, o token e o
    número não podem estar nela."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return respond(request)

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        try:
            entrega = await make(http).enviar(message or _message())
        except Exception as exc:
            for sonda in (TOKEN, CLIENT_TOKEN, DIGITS):
                assert sonda not in str(exc)
            pytest.fail(f"nenhuma exceção pode sair de enviar: {type(exc).__name__}")
    return entrega, seen


# ---------------------------------------------------------------------------
# Gate 1 — o corpo exato, com `ordered()`
# ---------------------------------------------------------------------------
async def test_meta_cloud_manda_o_template_com_os_parametros_na_ordem_declarada() -> None:
    """`POST /{phone_number_id}/messages` com o Bearer no cabeçalho e o JSON
    inteiro: nome do template, idioma e os parâmetros na ordem de `variables`
    — `Shopping Norte, Colab Sonda, 2`, que não é a ordem de `facts` nem a
    alfabética."""
    entrega, seen = await _enviar(_meta, _meta_ok)

    assert entrega == Delivery(status="sent", provider_message_id=WAMID, cost_cents=None)
    [request] = seen
    assert request.method == "POST"
    assert str(request.url) == f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert _sent(request) == {
        "messaging_product": "whatsapp",
        "to": DIGITS,
        "type": "template",
        "template": {
            "name": "deviation_individual",
            "language": {"code": "pt_BR"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "Shopping Norte"},
                        {"type": "text", "text": "Colab Sonda"},
                        {"type": "text", "text": "2"},
                    ],
                }
            ],
        },
    }
    assert _meta(httpx.AsyncClient()).name == meta_cloud.NAME


async def test_z_api_manda_o_render_do_body_com_o_token_no_caminho() -> None:
    """`send-text` com `Client-Token` no cabeçalho, o token na URL, e o JSON
    inteiro: o número sem `+` e o texto igual a `render(body, message)`."""
    entrega, seen = await _enviar(_zapi, _zapi_ok)

    assert entrega == Delivery(status="sent", provider_message_id=ZAPI_MESSAGE_ID)
    [request] = seen
    assert request.method == "POST"
    assert (
        str(request.url) == f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{TOKEN}/send-text"
    )
    assert request.headers["Client-Token"] == CLIENT_TOKEN
    assert "Authorization" not in request.headers
    assert _sent(request) == {"phone": DIGITS, "message": render(BODY, _message())}
    assert _sent(request)["message"] == RENDERED
    assert _zapi(httpx.AsyncClient()).name == z_api.NAME


async def test_uazapi_manda_o_render_do_body_com_o_token_no_cabecalho() -> None:
    """`{base_url}/send/text` com `token` no cabeçalho e o JSON inteiro."""
    entrega, seen = await _enviar(_uaz, _uaz_ok)

    assert entrega == Delivery(status="sent", provider_message_id=UAZ_MESSAGE_ID)
    [request] = seen
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}/send/text"
    assert request.headers["token"] == TOKEN
    assert TOKEN not in str(request.url)
    assert _sent(request) == {"number": DIGITS, "text": render(BODY, _message())}
    assert _sent(request)["text"] == RENDERED
    assert _uaz(httpx.AsyncClient()).name == uazapi.NAME


@pytest.mark.parametrize(("make", "ok", "_id", "module"), PROVIDERS_UNDER_TEST, ids=PROVIDER_IDS)
async def test_o_destino_vai_so_com_digitos_e_a_delivery_nao_custa(
    make: Make, ok: Respond, _id: str, module: ModuleType
) -> None:
    """O sender manda E.164 com `+`; os três mandam só os dígitos. E nenhum dos
    três devolve custo: a Meta cobra por conversa e informa por webhook, os
    dois de QR cobram por instância — `cost_cents` é `None` até haver fonte."""
    entrega, [request] = await _enviar(make, ok)

    corpo = _sent(request)
    assert DIGITS in corpo.values()
    assert DESTINATION not in corpo.values()
    assert entrega.cost_cents is None


# ---------------------------------------------------------------------------
# Gate 2 — `meta_cloud` nunca renderiza; os dois de QR só renderizam
# ---------------------------------------------------------------------------
def _boom(*_: Any, **__: Any) -> str:
    raise AssertionError("render foi chamado pelo provedor oficial")


async def test_meta_cloud_nunca_renderiza_nem_le_o_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """A frase do oficial vive na WABA. `render` não está no `ast` do módulo;
    mesmo com `base.render` armado para explodir e um `body` cheio de
    placeholders, a requisição sai sem uma letra do texto renderizado."""
    tree = _tree(meta_cloud)
    assert not any(isinstance(n, ast.Name) and n.id == "render" for n in ast.walk(tree))
    assert not any(
        isinstance(n, ast.ImportFrom) and any(a.name == "render" for a in n.names)
        for n in ast.walk(tree)
    )
    assert not hasattr(meta_cloud, "render")

    monkeypatch.setattr(base, "render", _boom)
    entrega, [request] = await _enviar(_meta, _meta_ok)

    assert entrega.status == "sent"
    assert RENDERED not in request.content.decode()
    assert "Colab Sonda teve" not in request.content.decode()
    assert BODY not in request.content.decode()


async def test_meta_cloud_provider_template_vence_o_code_e_language_vai_como_veio() -> None:
    """`meta_template_name` é o nome que a WABA conhece; o `code` é o nosso.
    Quando os dois existem, vai o da WABA; o idioma é o da aprovação, sem
    normalizar."""
    entrega, [request] = await _enviar(
        _meta, _meta_ok, _message(provider_template="fastpark_desvio_v2", language="es_AR")
    )

    assert entrega.status == "sent"
    template = _sent(request)["template"]
    assert template["name"] == "fastpark_desvio_v2"
    assert template["language"] == {"code": "es_AR"}

    _, [request] = await _enviar(_meta, _meta_ok, _message(provider_template=None))
    assert _sent(request)["template"]["name"] == "deviation_individual"
    assert _sent(request)["template"]["language"] == {"code": "pt_BR"}


async def test_meta_cloud_sem_variaveis_nao_manda_components() -> None:
    """`parameters: []` é erro na Graph API, não um no-op: sem variável, a
    chave `components` não existe. É `variables` quem decide, não `facts`: o
    outbox manda sempre os mesmos oito fatos, e um template que declare zero
    variáveis não pode virar `parameters: []` por causa deles."""
    entrega, [request] = await _enviar(_meta, _meta_ok, _message(variables=()))

    assert entrega.status == "sent"
    assert _sent(request) == {
        "messaging_product": "whatsapp",
        "to": DIGITS,
        "type": "template",
        "template": {"name": "deviation_individual", "language": {"code": "pt_BR"}},
    }


async def test_meta_cloud_variavel_declarada_sem_fato_vai_vazia() -> None:
    """O inverso: a variável declarada sem fato correspondente vira `""`, e
    `components` existe — `ordered()` é quem preenche, pela ordem do template."""
    _, [request] = await _enviar(_meta, _meta_ok, _message(variables=("unit",), facts={}))

    assert _sent(request)["template"]["components"] == [
        {"type": "body", "parameters": [{"type": "text", "text": ""}]}
    ]


async def test_meta_cloud_sem_template_e_no_template_sem_requisicao() -> None:
    """O oficial não tem outra fonte de frase — e não cai em `render`."""
    entrega, seen = await _enviar(_meta, _meta_ok, _message(template=None))

    assert entrega == Delivery(status="failed", error="no_template")
    assert seen == []


@pytest.mark.parametrize(
    ("make", "ok", "campo"), [(_zapi, _zapi_ok, "message"), (_uaz, _uaz_ok, "text")]
)
async def test_z_api_e_uazapi_o_texto_e_render_byte_a_byte_e_o_vao_vira_vazio(
    make: Make, ok: Respond, campo: str
) -> None:
    """`{{4}}` com três variáveis declaradas vira vazio, não fica literal — a
    mesma regra do Telegram, pela mesma função."""
    com_vao = _message(body="{{2}}: {{4}} [{{1}}]")
    _, [request] = await _enviar(make, ok, com_vao)

    assert _sent(request)[campo] == render(com_vao.body or "", com_vao)
    assert _sent(request)[campo] == "Colab Sonda:  [Shopping Norte]"
    assert "{{" not in _sent(request)[campo]


@pytest.mark.parametrize(("make", "ok"), [(_zapi, _zapi_ok), (_uaz, _uaz_ok)])
async def test_z_api_e_uazapi_sem_body_e_no_body_sem_requisicao(make: Make, ok: Respond) -> None:
    entrega, seen = await _enviar(make, ok, _message(body=None))

    assert entrega == Delivery(status="failed", error="no_body")
    assert seen == []


async def test_z_api_cai_no_zaap_id_quando_nao_ha_message_id() -> None:
    """Premissa registrada no módulo: `messageId` primeiro, `zaapId` como
    reserva — e vazio conta como ausente."""
    entrega, _ = await _enviar(
        _zapi, lambda _: httpx.Response(200, json={"zaapId": ZAPI_ZAAP_ID, "messageId": ""})
    )

    assert entrega == Delivery(status="sent", provider_message_id=ZAPI_ZAAP_ID)


@pytest.mark.parametrize(
    "corpo",
    [
        {"messageid": UAZ_MESSAGE_ID, "id": "uuid-interno"},
        {"id": UAZ_MESSAGE_ID},
        {"key": {"id": UAZ_MESSAGE_ID, "remoteJid": f"{DIGITS}@s.whatsapp.net"}},
    ],
    ids=["messageid", "id", "key.id"],
)
async def test_uazapi_le_o_id_nas_tres_formas_da_premissa(corpo: dict[str, Any]) -> None:
    """Premissa registrada no módulo: `messageid` (v2), depois `id`, depois
    `key.id` (pré-v2). A primeira que vier."""
    entrega, _ = await _enviar(_uaz, lambda _: httpx.Response(200, json=corpo))

    assert entrega == Delivery(status="sent", provider_message_id=UAZ_MESSAGE_ID)


# ---------------------------------------------------------------------------
# Gate 3 — o mapa de erro por tabela; o corpo do provedor não chega a lugar nenhum
# ---------------------------------------------------------------------------
def _echoing(status: int) -> Respond:
    """A recusa que devolve a sonda, o token e a URL no corpo — o pior caso."""

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"detail": PROBE, "token": TOKEN, "url": str(request.url), "error": PROBE},
        )

    return respond


def _falls(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError(f"refused {request.url} {PROBE}", request=request)


def _timed_out(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout(f"timeout {request.url}", request=request)


def _undecodable(request: httpx.Request) -> httpx.Response:
    # `RequestError` que não é `TransportError`: um `except` estreito demais a
    # deixaria sair de `enviar`.
    raise httpx.DecodingError(f"encoding {PROBE}", request=request)


ERROR_TABLE: list[tuple[str, Respond, str]] = [
    ("connect_error", _falls, "unreachable"),
    ("read_timeout", _timed_out, "unreachable"),
    ("decoding_error", _undecodable, "unreachable"),
    # 2xx/3xx que não é 200 é recusa, como no Telegram: fail-closed.
    ("201", _echoing(201), "http_201"),
    ("302", _echoing(302), "http_302"),
    ("401", _echoing(401), "unauthorized"),
    ("403", _echoing(403), "unauthorized"),
    ("429", _echoing(429), "unreachable"),
    ("500", _echoing(500), "unreachable"),
    ("503", _echoing(503), "unreachable"),
    ("400", _echoing(400), "http_400"),
    ("404", _echoing(404), "http_404"),
    ("422", _echoing(422), "http_422"),
    ("html_200", lambda _: httpx.Response(200, content=b"<html>" + PROBE.encode()), "malformed"),
    ("json_lista", lambda _: httpx.Response(200, json=[PROBE]), "malformed"),
    ("json_sem_id", lambda _: httpx.Response(200, json={"detail": PROBE}), "malformed"),
    ("json_null", lambda _: httpx.Response(200, content=b"null"), "malformed"),
]

#: JSON com 200 que cada provedor não reconhece — sem `messages[0].id`, sem
#: `messageId`/`zaapId`, sem `messageid`/`id`/`key.id`.
MALFORMED_BY_PROVIDER: dict[str, list[dict[str, Any]]] = {
    meta_cloud.NAME: [
        {"messages": []},
        {"messages": [{}]},
        {"messages": [{"id": ""}]},
        {"messages": [{"id": 12345}]},
        {"messages": {"id": WAMID}},
        {"contacts": [{"wa_id": DIGITS}]},
    ],
    z_api.NAME: [{"id": ZAPI_MESSAGE_ID}, {"messageId": 1}, {"messageId": "", "zaapId": ""}],
    uazapi.NAME: [{"key": {}}, {"key": "x"}, {"messageid": 7}, {"id": ""}],
}


@pytest.mark.parametrize(("make", "ok", "_id", "module"), PROVIDERS_UNDER_TEST, ids=PROVIDER_IDS)
@pytest.mark.parametrize(
    ("_rotulo", "respond", "esperado"), ERROR_TABLE, ids=[r for r, _, _ in ERROR_TABLE]
)
async def test_mapa_de_erro_por_tabela_e_o_corpo_nao_chega_a_lugar_nenhum(
    make: Make,
    ok: Respond,
    _id: str,
    module: ModuleType,
    _rotulo: str,
    respond: Respond,
    esperado: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Exceção do httpx → `unreachable`; 429 e ≥ 500 → `unreachable`; 401/403
    → `unauthorized`; outro 4xx → `http_<código>`; JSON sem id → `malformed`.
    `error` é só o código: a sonda que o provedor devolveu não está em `error`,
    em `repr(Delivery)` nem no log."""
    _reset_http_loggers()
    with caplog.at_level(logging.DEBUG):
        entrega, _ = await _enviar(make, respond)

    assert entrega.status == "failed"
    assert entrega.error == esperado
    assert entrega.provider_message_id is None
    assert entrega.cost_cents is None
    for sonda in (PROBE, TOKEN, CLIENT_TOKEN, DIGITS):
        assert sonda not in (entrega.error or "")
        assert sonda not in repr(entrega)
        assert sonda not in caplog.text
    _reset_http_loggers()


@pytest.mark.parametrize(("make", "ok", "_id", "module"), PROVIDERS_UNDER_TEST, ids=PROVIDER_IDS)
async def test_json_que_o_provedor_nao_reconhece_e_malformed(
    make: Make, ok: Respond, _id: str, module: ModuleType
) -> None:
    for corpo in MALFORMED_BY_PROVIDER[module.NAME]:
        entrega, _ = await _enviar(make, lambda _, c=corpo: httpx.Response(200, json=c))
        assert entrega == Delivery(status="failed", error="malformed"), corpo


@pytest.mark.parametrize(("make", "ok", "_id", "module"), PROVIDERS_UNDER_TEST, ids=PROVIDER_IDS)
async def test_enviar_nunca_levanta_e_nunca_recusa_por_excecao(
    make: Make, ok: Respond, _id: str, module: ModuleType
) -> None:
    """`enviar` devolve `Delivery`; o sender grava `error`, não trata exceção.
    E o `ast` do módulo confirma: nenhum `raise` dentro de `enviar`."""
    [enviar] = [
        n
        for n in ast.walk(_tree(module))
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "enviar"
    ]
    assert not any(isinstance(n, ast.Raise) for n in ast.walk(enviar))

    entrega, _ = await _enviar(make, _falls)
    assert entrega == Delivery(status="failed", error="unreachable")


# ---------------------------------------------------------------------------
# Gate 4 — token e número em lugar nenhum; o par do `z_api`
# ---------------------------------------------------------------------------
async def test_gate_3_z_api_o_cliente_cru_vaza_o_token_e_o_verification_client_nao(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """O par. Positivo primeiro: com um `AsyncClient` cru, o `httpx` escreve
    `HTTP Request: POST …/token/<token>/send-text` em INFO — o teste **falharia**
    sem a defesa. Depois, pelo `verification_client`, nada: nem o token, nem o
    `Client-Token`, nem o número, com `httpx` e `httpcore` capturados em DEBUG.
    ⛔ Mutação: tirar o `setLevel` de `verification_client` deixa a segunda
    metade vermelha."""
    _reset_http_loggers()
    with caplog.at_level(logging.DEBUG):
        async with httpx.AsyncClient(transport=httpx.MockTransport(_echoing(401))) as raw:
            entrega = await z_api.ZApiProvider(INSTANCE_ID, TOKEN, CLIENT_TOKEN, raw).enviar(
                _message()
            )
    assert entrega.error == "unauthorized"
    assert any(r.name == "httpx" and TOKEN in r.getMessage() for r in caplog.records)
    assert TOKEN in caplog.text  # o positivo: sem a defesa, a URL vai para o log

    caplog.clear()
    _reset_http_loggers()
    with caplog.at_level(logging.DEBUG):
        entrega, [request] = await _enviar(_zapi, _echoing(401))
    assert entrega.error == "unauthorized"
    assert TOKEN in str(request.url)  # a premissa: o token está mesmo no caminho
    for sonda in (TOKEN, CLIENT_TOKEN, DIGITS, DESTINATION, PROBE):
        assert sonda not in caplog.text
        assert sonda not in (entrega.error or "")
    _reset_http_loggers()


@pytest.mark.parametrize(("make", "ok", "_id", "module"), PROVIDERS_UNDER_TEST, ids=PROVIDER_IDS)
async def test_token_e_numero_ausentes_do_log_em_debug_com_httpx_incluido(
    make: Make, ok: Respond, _id: str, module: ModuleType, caplog: pytest.LogCaptureFixture
) -> None:
    """Para os três, no sucesso e na recusa que ecoa: nenhum registro de
    `caplog` — `httpx` e `httpcore` incluídos — carrega o token, o
    `Client-Token`, o número ou a sonda."""
    for respond in (ok, _echoing(401), _falls):
        _reset_http_loggers()
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            await _enviar(make, respond)
        for sonda in (TOKEN, CLIENT_TOKEN, DIGITS, DESTINATION, PROBE):
            assert sonda not in caplog.text, respond
        for registro in caplog.records:
            for sonda in (TOKEN, CLIENT_TOKEN, DIGITS):
                assert sonda not in registro.getMessage()
    _reset_http_loggers()


# ---------------------------------------------------------------------------
# Gate 5 — a fábrica cobre a matriz inteira e só ela
# ---------------------------------------------------------------------------
EXPECTED_CLASS: dict[str, type] = {
    meta_cloud.NAME: meta_cloud.MetaCloudProvider,
    z_api.NAME: z_api.ZApiProvider,
    uazapi.NAME: uazapi.UazapiProvider,
    telegram.NAME: telegram.TelegramProvider,
}


def _split(provider: str) -> tuple[dict[str, str], dict[str, str]]:
    """`(config, secrets)` de `VALID_FIELDS`, pela partição de `FIELDS`."""
    fields = VALID_FIELDS[provider]
    specs = PROVIDERS[provider].FIELDS
    config = {s.name: fields[s.name] for s in specs if not s.secret}
    secrets = {s.name: fields[s.name] for s in specs if s.secret}
    return config, secrets


def test_build_cobre_todos_os_provedores_da_matriz_e_so_eles() -> None:
    """`_BUILDERS` é a matriz, nos dois sentidos, e `build` devolve a classe
    certa para cada nome com o `http` que recebeu."""
    assert {module.NAME for module in fabrica._BUILDERS} == set(CHANNEL_PROVIDERS)
    assert set(EXPECTED_CLASS) == set(CHANNEL_PROVIDERS)

    http = httpx.AsyncClient()
    for provider in CHANNEL_PROVIDERS:
        config, secrets = _split(provider)
        built = fabrica.build(provider, config=config, secrets=secrets, http=http)
        assert isinstance(built, EXPECTED_CLASS[provider]), provider
        assert built.name == provider
        assert built.http is http  # type: ignore[attr-defined]


def _build(provider: str, http: httpx.AsyncClient) -> Provider:
    config, secrets = _split(provider)
    return fabrica.build(provider, config=config, secrets=secrets, http=http)


def test_build_liga_cada_campo_ao_atributo_certo() -> None:
    http = httpx.AsyncClient()
    meta = _build(meta_cloud.NAME, http)
    assert isinstance(meta, meta_cloud.MetaCloudProvider)
    assert (meta.phone_number_id, meta.token) == (PHONE_NUMBER_ID, TOKEN)

    zapi = _build(z_api.NAME, http)
    assert isinstance(zapi, z_api.ZApiProvider)
    assert (zapi.instance_id, zapi.token, zapi.client_token) == (INSTANCE_ID, TOKEN, CLIENT_TOKEN)

    uaz = _build(uazapi.NAME, http)
    assert isinstance(uaz, uazapi.UazapiProvider)
    assert (uaz.base_url, uaz.token) == (BASE_URL, TOKEN)

    bot = _build(telegram.NAME, http)
    assert isinstance(bot, telegram.TelegramProvider)
    assert bot.token == BOT_TOKEN


def test_build_com_nome_desconhecido_e_unknown_provider_antes_de_ler_campo() -> None:
    """A recusa é a da matriz, e vem antes de qualquer `KeyError`: com os dois
    mapas vazios, o erro ainda é o nome."""
    with pytest.raises(UnknownProviderError):
        fabrica.build("whatsapp_web", config={}, secrets={}, http=httpx.AsyncClient())
    with pytest.raises(UnknownProviderError):
        fabrica.build("", config={}, secrets={}, http=httpx.AsyncClient())


@pytest.mark.parametrize("provider", CHANNEL_PROVIDERS)
def test_build_campo_do_lado_errado_e_key_error_com_o_nome_e_nada_mais(provider: str) -> None:
    """A partição é a de `FIELDS`, percorrida: cada campo secreto oferecido em
    `config` (e ausente do cofre) e cada não-secreto oferecido em `secrets` é
    `KeyError(<nome>)` — e `str(exc)` não carrega valor nenhum."""
    http = httpx.AsyncClient()
    config, secrets = _split(provider)
    valores = set(VALID_FIELDS[provider].values())

    for spec in PROVIDERS[provider].FIELDS:
        if spec.secret:
            errado_config = config | {spec.name: secrets[spec.name]}
            errado_secrets = {k: v for k, v in secrets.items() if k != spec.name}
        else:
            errado_config = {k: v for k, v in config.items() if k != spec.name}
            errado_secrets = secrets | {spec.name: config[spec.name]}

        with pytest.raises(KeyError) as erro:
            fabrica.build(provider, config=errado_config, secrets=errado_secrets, http=http)
        assert erro.value.args == (spec.name,), spec.name
        for valor in valores:
            assert valor not in str(erro.value)
            assert valor not in repr(erro.value)

        # E simplesmente ausente dos dois lados: o mesmo nome.
        with pytest.raises(KeyError) as erro:
            fabrica.build(
                provider,
                config={k: v for k, v in config.items() if k != spec.name},
                secrets={k: v for k, v in secrets.items() if k != spec.name},
                http=http,
            )
        assert erro.value.args == (spec.name,)


def test_build_ignora_o_que_a_rota_guarda_ao_lado_do_formulario() -> None:
    """`app.integration.config` do Telegram carrega `webhook_url` e
    `path_token` além do formulário; a fábrica lê só o que `FIELDS` declara."""
    built = fabrica.build(
        telegram.NAME,
        config={"webhook_url": "https://api.exemplo.test/webhooks/telegram/x", "path_token": "x"},
        secrets={"bot_token": BOT_TOKEN, "webhook_secret": "segredo"},
        http=httpx.AsyncClient(),
    )
    assert isinstance(built, telegram.TelegramProvider)


def test_fabrica_nao_escreve_provedor_como_literal() -> None:
    """O `ast` do C1 continua valendo por dentro de `provedores/`: `fabrica`
    mapeia por módulo, e nenhum nome de provedor aparece como string."""
    literais = {n.value for n in ast.walk(_tree(fabrica)) if isinstance(n, ast.Constant)}
    assert literais.isdisjoint(CHANNEL_PROVIDERS)


# ---------------------------------------------------------------------------
# Critério 5 — provedor não conhece banco
# ---------------------------------------------------------------------------
_DB_NAMES = {"execute", "fetchone", "fetchall", "tenant_scope", "user_scope", "scope"}
_DB_MODULES = ("operax.core", "psycopg", "operax.alertas.sender", "operax.alertas.outbox")


@pytest.mark.parametrize("module", [meta_cloud, z_api, uazapi, fabrica], ids=lambda m: m.__name__)
def test_provedor_nao_conhece_banco(module: ModuleType) -> None:
    """Nenhum identificador de banco e nenhuma importação de `operax.core`,
    `psycopg`, do sender ou do outbox: o provedor recebe strings e um cliente
    HTTP, e quem grava é o sender."""
    identificadores: set[str] = set()
    importados: set[str] = set()
    for n in ast.walk(_tree(module)):
        if isinstance(n, ast.Name):
            identificadores.add(n.id)
        elif isinstance(n, ast.Attribute):
            identificadores.add(n.attr)
        elif isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
            identificadores.add(n.name)
        elif isinstance(n, ast.arg):
            identificadores.add(n.arg)
        elif isinstance(n, ast.Import):
            importados |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            importados.add(n.module)
    assert identificadores.isdisjoint(_DB_NAMES), identificadores & _DB_NAMES
    assert not [m for m in importados if m.startswith(_DB_MODULES)], importados
