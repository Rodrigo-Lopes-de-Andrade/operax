"""O Telegram como quarto provedor: o bot, a credencial por canal e a tela com dois canais.

Cinco portões (SPRINTS-CANAIS, C3, onda 2a):

1. **o token do bot está na URL da Bot API** — é o caso do `z_api` de novo, e
   as duas defesas são as mesmas: `verification_client` para o log, `from None`
   para a cadeia. O gate 3 aqui captura em DEBUG e varre;
2. **gravar o bot desliga só o bot** — a `_DEACTIVATE_SQL` do canal `telegram`
   não nomeia provedor de WhatsApp, e a do WhatsApp não nomeia o bot. É a linha 1
   da SPEC §2.2 pela porta da credencial;
3. **conectar grava antes de chamar** — o `setWebhook` só acontece com a
   transação fechada, e uma recusa deixa a saúde em `disconnected` com uma frase
   **da rota**, nunca o corpo do provedor;
4. **desconectar chama antes de gravar, e rotaciona** — o `path_token` muda, o
   `webhook_url` zera, e reconectar não devolve o endereço antigo;
5. **o `webhook_secret` não sai por lugar nenhum** — nem resposta, nem log, nem
   auditoria, nem instrução: só `params["value"]` da gravação no cofre;
6. **`enviar` renderiza o template, e só** (onda 2b) — o texto que vai ao
   `sendMessage` é exatamente `render(body, message)`, sem `parse_mode`; `403`
   é `blocked` e ninguém revoga aqui; o token está na URL (gate 3 de novo).

⚠️ O QUE ESTA SUÍTE NÃO PODE PROVAR
Nada aqui toca banco nem rede. `fn_channel_readiness` de verdade com dois canais
ativos, a `_DEACTIVATE_SQL` do bot executada ao lado de um `meta_cloud` ativo que
sobrevive, e `fn_record_channel_health` gravando o `detail` literal são
`scripts/97_teste_canais.py`, no `make db-test`. Aqui o banco é um stub que
responde pelo assunto da instrução — e que **muta** um `config` e uma saúde
falsos a partir dos parâmetros que a rota lhe manda, para que a resposta
relida depois de conectar e desconectar seja verificável de ponta a ponta.
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from operax.alertas import saude
from operax.alertas.capacidades import (
    CHANNEL_PROVIDERS,
    CHANNELS,
    WHATSAPP_PROVIDERS,
    UnknownChannelError,
    UnknownProviderError,
    channel_of,
    providers_of,
)
from operax.alertas.provedores import PROVIDERS, meta_cloud, telegram, z_api
from operax.alertas.provedores.base import (
    Delivery,
    FieldError,
    InvalidCredentialError,
    Message,
    check_fields,
    render,
    verification_client,
)
from operax.core.config import Settings
from operax.core.tenant import SystemContext, bind_tenant
from server.main import app
from server.routers import canais
from tests.conftest import TENANT_ID
from tests.test_canais_credencial import (
    BOT_TOKEN,
    TOKEN,
    VALID_FIELDS,
    Recorder,
    _accepts,
    _all_text,
    _codes_raised,
    _reset_http_loggers,
    _v_flag_violations,
)
from tests.test_canais_templates import AnsweringScope, TimedScopeContext, _statements

INTEGRATION_ID = UUID("33333333-3333-4333-8333-333333333333")
VAULT_ID = UUID("44444444-4444-4444-8444-444444444443")
PUBLIC_URL = "https://api.exemplo.test"
BOT_USERNAME = "@FastParkAlertasBot"
CHECKED_AT = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
CHANGED_AT = datetime(2026, 9, 15, 11, 0, tzinfo=UTC)
#: O que um `setWebhook` recusado poderia devolver — o token e um texto. Nenhum
#: dos dois pode chegar ao `detail` da saúde.
REFUSAL_TEXT = "Unauthorized: bot token is invalid"


# ---------------------------------------------------------------------------
# A Bot API falsa
# ---------------------------------------------------------------------------
def _method(request: httpx.Request) -> str:
    return request.url.path.rsplit("/", 1)[1]


def bot_api(request: httpx.Request) -> httpx.Response:
    """Aceita tudo: `getMe` com o bot de teste, o resto com `result: true`."""
    if _method(request) == "getMe":
        return httpx.Response(200, json=_accepts(telegram))
    return httpx.Response(200, json={"ok": True, "result": True})


def _refuses_echoing(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        401,
        json={
            "ok": False,
            "error_code": 401,
            "description": REFUSAL_TEXT,
            "token": BOT_TOKEN,
            "url": str(request.url),
        },
    )


def _sent(request: httpx.Request) -> dict[str, Any]:
    """O JSON que a rota mandou à plataforma."""
    return httpx.Response(200, content=request.content).json()


@pytest.fixture
def cabecalho(issue_token: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token()}"}


@pytest.fixture
def transport(client: TestClient) -> Iterator[Recorder]:
    """O `Recorder` do C2, pelo mesmo `verification_client` — onde a defesa do
    log vive. Responde como a Bot API que aceita, salvo instrução contrária."""
    recorder = Recorder()
    recorder.respond = bot_api

    async def override() -> Any:
        _reset_http_loggers()
        async with verification_client(transport=httpx.MockTransport(recorder.handler)) as http:
            yield http

    app.dependency_overrides[canais.get_http_client] = override
    yield recorder
    _reset_http_loggers()


# ---------------------------------------------------------------------------
# O banco falso: um bot cujo `config` e saúde as instruções da rota mutam
# ---------------------------------------------------------------------------
@dataclass
class FakeBot:
    """A integração `telegram` ativa, como o banco falso a conhece."""

    config: dict[str, Any] = field(default_factory=lambda: {"public_identity": BOT_USERNAME})
    #: `(status, detail)` da última `fn_record_channel_health`; `None` = nunca medido.
    health: tuple[str, str | None] | None = None
    has_token: bool = True
    #: O que a linha da função diz além da saúde — para prender que a rota não
    #: recalcula `ready`.
    readiness: dict[str, Any] = field(default_factory=dict)

    def state_row(self) -> dict[str, Any]:
        return {
            "id": INTEGRATION_ID,
            "public_identity": self.config.get("public_identity"),
            "webhook_url": self.config.get("webhook_url"),
            "webhook_path_token": self.config.get("webhook_path_token"),
            "health_checked_at": CHECKED_AT if self.health else None,
            "health_detail": self.health[1] if self.health else None,
        }

    def readiness_row(self) -> dict[str, Any]:
        status = self.health[0] if self.health else None
        return {
            "provider": telegram.NAME,
            "official": True,
            "templates_total": 0,
            "templates_approved": 0,
            "rules_blocked": 0,
            "health_status": status,
            "health_changed_at": CHANGED_AT if status else None,
            "ready": status == "connected",
        } | self.readiness


def connected_bot() -> FakeBot:
    return FakeBot(
        config={
            "public_identity": BOT_USERNAME,
            "webhook_path_token": "cauda-antiga",
            "webhook_url": f"{PUBLIC_URL}/webhooks/telegram/cauda-antiga",
        },
        health=("connected", "webhook registrado"),
    )


def whatsapp_row(**overrides: Any) -> dict[str, Any]:
    return {
        "provider": meta_cloud.NAME,
        "official": True,
        "templates_total": 4,
        "templates_approved": 3,
        "rules_blocked": 1,
        "health_status": None,
        "health_changed_at": None,
        "ready": False,
    } | overrides


def blocked_row() -> dict[str, Any]:
    return {
        "rule_name": "Desvio individual — Shopping Norte",
        "template_code": "deviation_individual",
        "meta_status": "pending",
    }


@dataclass
class Stubs:
    user: AnsweringScope
    bound: AnsweringScope
    bound_ctx: TimedScopeContext
    bot: FakeBot | None
    timeline: list[str]


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Stubs]:
    def install(
        *,
        admin: bool = True,
        bot: FakeBot | None | str = "default",
        whatsapp: dict[str, Any] | None = None,
        blocked: list[dict[str, Any]] | None = None,
        public_url: str | None = PUBLIC_URL,
        deactivated: list[dict[str, Any]] | None = None,
    ) -> Stubs:
        if bot == "default":
            bot = FakeBot()
        assert bot is None or isinstance(bot, FakeBot)
        timeline: list[str] = []

        def readiness(_: Any) -> list[dict[str, Any]]:
            rows = [whatsapp] if whatsapp is not None else []
            if bot is not None:
                rows.append(bot.readiness_row())
            return rows

        def state(_: Any) -> dict[str, Any] | None:
            return bot.state_row() if bot is not None else None

        def token(_: Any) -> dict[str, Any] | None:
            return {"decrypted_secret": BOT_TOKEN} if bot is not None and bot.has_token else None

        def patch(params: Any) -> dict[str, Any]:
            assert bot is not None
            bot.config.update(params["patch"].obj)
            return {"id": INTEGRATION_ID}

        def health(params: Any) -> dict[str, Any]:
            assert bot is not None
            bot.health = (params["status"], params["detail"])
            return {"fn_record_channel_health": None}

        user = AnsweringScope(
            {
                "util.is_admin": {"admin": admin},
                "fn_channel_readiness": readiness,
                "from app.alert_rule": blocked or [],
            }
        )
        bound = AnsweringScope(
            {
                "config ->> 'webhook_url'": state,
                "vault.decrypted_secrets": token,
                "config ||": patch,
                "fn_record_channel_health": health,
                "vault.update_secret": None,
                "vault.create_secret": {"vault_id": VAULT_ID},
                "insert into app.audit_log": None,
                # A rota de credencial, para os testes de "desliga só o canal".
                # `deactivated` é o que a linha anterior devolve — inclusive se
                # tinha webhook registrado, que é o que decide a saúde.
                "set active = false": deactivated if deactivated is not None else [],
                "insert into app.integration (": {"id": INTEGRATION_ID},
                "max(s.updated_at)": {
                    "provider": telegram.NAME,
                    "public_identity": BOT_USERNAME,
                    "updated_at": "2026-09-15T12:00:00+00:00",
                },
            }
        )
        bound_ctx = TimedScopeContext(bound, timeline, "tenant_scope")
        monkeypatch.setattr(
            canais, "user_scope", lambda _t: TimedScopeContext(user, timeline, "user_scope")
        )
        monkeypatch.setattr(canais, "tenant_scope", lambda _t: bound_ctx)
        monkeypatch.setattr(
            canais, "get_settings", lambda: SimpleNamespace(api_public_url=public_url)
        )
        return Stubs(user=user, bound=bound, bound_ctx=bound_ctx, bot=bot, timeline=timeline)

    return install


def _connect(client: TestClient, cabecalho: dict[str, str]):
    return client.post("/canais/telegram/conectar", headers=cabecalho)


def _disconnect(client: TestClient, cabecalho: dict[str, str]):
    return client.post("/canais/telegram/desconectar", headers=cabecalho)


def _post_credential(client: TestClient, cabecalho: dict[str, str], provider: str):
    return client.post(
        "/canais/credencial",
        json={"provider": provider, "fields": VALID_FIELDS[provider]},
        headers=cabecalho,
    )


_WRITE_MARKERS = (
    "config ||",
    "fn_record_channel_health",
    "vault.create_secret",
    "vault.update_secret",
    "insert into app.audit_log",
)


def _writes(scope: AnsweringScope) -> list[str]:
    """As instruções que mudam algo: `config`, saúde, cofre e trilha."""
    return [s for s in scope.statements if any(m in s for m in _WRITE_MARKERS)]


# ---------------------------------------------------------------------------
# O formulário: um token, secreto, na forma do BotFather
# ---------------------------------------------------------------------------
def test_o_formulario_do_bot_e_um_token_secreto_no_dialeto_do_navegador() -> None:
    """Um campo só, e é segredo: o token é a credencial inteira, e a identidade
    (`@…`) vem do `getMe`, não de um campo. `one-time-code` para o navegador não
    oferecer salvar; `\\-` escapado para a flag `v` não descartar o `pattern`."""
    [spec] = telegram.FIELDS
    assert spec.name == "bot_token"
    assert spec.secret is True
    assert spec.autocomplete == "one-time-code"
    assert "BotFather" in spec.label_pt
    assert _v_flag_violations(spec.pattern) == set()
    assert check_fields(telegram.FIELDS, VALID_FIELDS[telegram.NAME]) == {"bot_token": BOT_TOKEN}


@pytest.mark.parametrize(
    "bad",
    [
        "gestor@fastpark.com.br",
        "123:abc",
        "abc:AAH-token-de-bot-de-teste-nao-e-real-000",
        "123456789:AAH/../getMe",
        "123456789:AAH token com espaco 000000000000000000",
    ],
)
def test_o_pattern_do_token_recusa_o_que_nao_e_token_sem_carregar_o_valor(bad: str) -> None:
    """A terceira defesa do gate 3: o que não é `<id>:<segredo>` morre antes de
    virar caminho de URL — uma `/` no valor seria outro método da Bot API."""
    with pytest.raises(FieldError) as erro:
        check_fields(telegram.FIELDS, {"bot_token": bad})
    assert erro.value.name == "bot_token"
    assert bad not in str(erro.value)


def test_o_bot_token_e_lido_pela_chave_que_o_formulario_declara_secreta() -> None:
    """Como `_META_TOKEN_KEY`: renomear o campo move os dois lados juntos."""
    assert canais._BOT_TOKEN_KEY == "bot_token"
    assert [s.name for s in telegram.FIELDS if s.secret] == [canais._BOT_TOKEN_KEY]


# ---------------------------------------------------------------------------
# `verify`: os três desfechos, e a premissa de que o token está na URL
# ---------------------------------------------------------------------------
async def test_verify_devolve_o_username_com_arroba_e_manda_o_token_pelo_caminho() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return bot_api(request)

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        identidade = await telegram.verify(VALID_FIELDS[telegram.NAME], http)

    assert identidade == BOT_USERNAME
    [request] = seen
    assert request.method == "GET"
    assert request.url.host == "api.telegram.org"
    assert request.url.path == f"/bot{BOT_TOKEN}/getMe"


@pytest.mark.parametrize(
    "response",
    [
        _refuses_echoing,
        lambda _: httpx.Response(404, json={"ok": False, "error_code": 404}),
        lambda _: httpx.Response(200, json={"ok": False, "description": "x", "token": BOT_TOKEN}),
    ],
)
async def test_ok_false_ou_4xx_e_unauthorized_e_a_excecao_nao_carrega_o_corpo(
    response: Callable[[httpx.Request], httpx.Response],
) -> None:
    async with verification_client(transport=httpx.MockTransport(response)) as http:
        with pytest.raises(InvalidCredentialError) as erro:
            await telegram.verify(VALID_FIELDS[telegram.NAME], http)

    formatado = "".join(traceback.format_exception(erro.value))
    assert erro.value.code == "unauthorized"
    assert BOT_TOKEN not in formatado
    assert REFUSAL_TEXT not in formatado


async def test_429_e_unreachable_nao_unauthorized() -> None:
    """Limite transitório da Bot API não é veredito sobre o token: `unauthorized`
    mandaria o administrador conferir uma credencial que está certa."""

    def limited(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"ok": False, "description": "Too Many Requests"})

    async with verification_client(transport=httpx.MockTransport(limited)) as http:
        with pytest.raises(InvalidCredentialError) as erro:
            await telegram.verify(VALID_FIELDS[telegram.NAME], http)
    assert erro.value.code == "unreachable"


async def test_rede_e_5xx_sao_unreachable_e_a_cadeia_morre_no_from_none() -> None:
    """⛔ Mutação: `raise … from None` → `raise …` deixa isto vermelho — a
    mensagem do `ConnectError` é a URL, e a URL é o token."""
    swallowed: list[BaseException] = []

    def falls(request: httpx.Request) -> httpx.Response:
        erro = httpx.ConnectError(f"connection refused by {request.url}", request=request)
        swallowed.append(erro)
        raise erro

    async with verification_client(transport=httpx.MockTransport(falls)) as http:
        with pytest.raises(InvalidCredentialError) as erro:
            await telegram.verify(VALID_FIELDS[telegram.NAME], http)
    formatado = "".join(traceback.format_exception(erro.value))
    assert erro.value.code == "unreachable"
    assert erro.value.__suppress_context__ is True
    assert BOT_TOKEN not in formatado
    assert "ConnectError" not in formatado
    [engolida] = swallowed
    assert BOT_TOKEN in str(engolida)  # o positivo: a cadeia carregaria o token

    async with verification_client(
        transport=httpx.MockTransport(lambda _: httpx.Response(502, text=BOT_TOKEN))
    ) as http:
        with pytest.raises(InvalidCredentialError) as erro:
            await telegram.verify(VALID_FIELDS[telegram.NAME], http)
    assert erro.value.code == "unreachable"


@pytest.mark.parametrize(
    "body",
    [
        b"<html>not json</html>",
        b'{"ok": true}',
        b'{"ok": true, "result": {}}',
        b'{"ok": true, "result": "FastParkAlertasBot"}',
        b'{"result": {"username": "x"}}',
    ],
)
async def test_corpo_estranho_no_getme_e_malformed(body: bytes) -> None:
    """Endpoint como premissa: forma inesperada recusa em vez de gravar uma
    identidade inventada."""
    async with verification_client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    ) as http:
        with pytest.raises(InvalidCredentialError) as erro:
            await telegram.verify(VALID_FIELDS[telegram.NAME], http)
    assert erro.value.code == "malformed"


def test_todo_codigo_de_recusa_do_telegram_tem_frase_nas_duas_tabelas() -> None:
    """`verify` recusa pela `_REFUSALS`; `setWebhook`/`deleteWebhook` pela
    `_WEBHOOK_REFUSALS`, com outra frase — "nada foi gravado" seria falso depois
    de conectar. Um código sem frase numa das duas é um 500 na cara do operador."""
    codes = _codes_raised(telegram)
    assert codes == {"unauthorized", "unreachable", "malformed"}
    assert codes <= set(canais._REFUSALS)
    assert codes <= set(canais._WEBHOOK_REFUSALS)
    assert "no_public_url" in canais._REFUSALS


# ---------------------------------------------------------------------------
# setWebhook, deleteWebhook, getWebhookInfo — o que vai e o que volta
# ---------------------------------------------------------------------------
async def test_set_webhook_manda_url_segredo_so_message_e_drop_pending() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return bot_api(request)

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        await telegram.set_webhook(BOT_TOKEN, f"{PUBLIC_URL}/webhooks/telegram/abc", "s3cr3t", http)
        await telegram.delete_webhook(BOT_TOKEN, http)

    setw, delw = seen
    assert setw.method == "POST"
    assert setw.url.path == f"/bot{BOT_TOKEN}/setWebhook"
    assert _sent(setw) == {
        "url": f"{PUBLIC_URL}/webhooks/telegram/abc",
        "secret_token": "s3cr3t",
        "allowed_updates": ["message"],
        "drop_pending_updates": True,
    }
    assert delw.method == "POST"
    assert delw.url.path == f"/bot{BOT_TOKEN}/deleteWebhook"
    assert _sent(delw) == {"drop_pending_updates": True}


async def test_set_webhook_recusado_e_o_mesmo_codigo_sem_o_corpo() -> None:
    async with verification_client(transport=httpx.MockTransport(_refuses_echoing)) as http:
        with pytest.raises(InvalidCredentialError) as erro:
            await telegram.set_webhook(BOT_TOKEN, "https://x", "s", http)
    assert erro.value.code == "unauthorized"
    assert BOT_TOKEN not in "".join(traceback.format_exception(erro.value))


async def test_webhook_info_le_os_quatro_campos_e_url_vazia_e_none() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "url": "",
                    "has_custom_certificate": False,
                    "pending_update_count": 3,
                    "last_error_date": 1789560000,
                    "last_error_message": "Connection timed out",
                },
            },
        )

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        info = await telegram.webhook_info(BOT_TOKEN, http)

    assert info == telegram.WebhookInfo(
        url=None,
        pending_update_count=3,
        last_error_date=datetime.fromtimestamp(1789560000, tz=UTC),
        last_error_message="Connection timed out",
    )
    assert set(telegram.WebhookInfo.__slots__) == {  # type: ignore[attr-defined]
        "url",
        "pending_update_count",
        "last_error_date",
        "last_error_message",
    }


async def test_webhook_info_mascara_o_path_token_ecoado_e_corta_em_200() -> None:
    """⛔ `last_error_message` pode ecoar a URL do webhook — que carrega o
    `path_token`. Ela sai mascarada e com teto, e a máscara vem ANTES do corte:
    cortar primeiro deixaria meio token na cauda."""
    path_token = "tok3n-publico-mas-rotativo-XYZ"
    url = f"{PUBLIC_URL}/webhooks/telegram/{path_token}"
    longa = f"Wrong response from the webhook: 502 Bad Gateway at {url} " + "x" * 400

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"ok": True, "result": {"url": url, "last_error_message": longa}},
        )

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        info = await telegram.webhook_info(BOT_TOKEN, http)

    assert info.url == url  # a URL registrada volta inteira: é o que o vigia compara
    assert info.last_error_message is not None
    assert path_token not in info.last_error_message
    assert f"{PUBLIC_URL}/webhooks/telegram/…" in info.last_error_message
    assert len(info.last_error_message) == 200
    assert info.pending_update_count == 0
    assert info.last_error_date is None


async def test_a_mascara_vem_antes_do_corte_mesmo_com_a_url_atravessando_o_teto() -> None:
    """⛔ Mutação: cortar em 200 e mascarar depois deixaria um pedaço do
    `path_token` na cauda quando a URL atravessa a posição 200 — aqui ela
    atravessa de propósito, e nenhum fragmento de 8+ caracteres dele sobra."""
    path_token = "tok3n-publico-mas-rotativo-XYZ-0123456789abcdef"
    url = f"{PUBLIC_URL}/webhooks/telegram/{path_token}"
    prefixo = "Wrong response from the webhook: 502 Bad Gateway at " + "y" * 120 + " "
    assert len(prefixo) < 200 < len(prefixo) + len(url)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"ok": True, "result": {"url": url, "last_error_message": prefixo + url}},
        )

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        info = await telegram.webhook_info(BOT_TOKEN, http)

    assert info.last_error_message is not None
    assert len(info.last_error_message) <= 200
    fragmentos = {path_token[i : i + 8] for i in range(len(path_token) - 7)}
    assert not any(f in info.last_error_message for f in fragmentos)


@pytest.mark.parametrize(
    "body",
    [
        b'{"ok": true, "result": "x"}',
        b'{"ok": true, "result": {"pending_update_count": "muitos"}}',
        b'{"ok": true, "result": {"last_error_date": "ontem"}}',
    ],
)
async def test_webhook_info_corpo_estranho_e_malformed(body: bytes) -> None:
    async with verification_client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    ) as http:
        with pytest.raises(InvalidCredentialError) as erro:
            await telegram.webhook_info(BOT_TOKEN, http)
    assert erro.value.code == "malformed"


# ---------------------------------------------------------------------------
# Gate 3 — o token está na URL; sem `verification_client` a URL vai para o log
# ---------------------------------------------------------------------------
async def test_gate_3_a_defesa_do_log_e_o_verification_client(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """O mesmo transporte, com um `AsyncClient` cru, loga `HTTP Request: GET
    …/bot<token>/getMe` em INFO; com o `verification_client`, nada. ⛔ Mutação:
    tirar o `setLevel` de `verification_client` deixa a segunda metade vermelha."""
    _reset_http_loggers()
    with caplog.at_level(logging.DEBUG):
        async with httpx.AsyncClient(transport=httpx.MockTransport(_refuses_echoing)) as raw:
            with pytest.raises(InvalidCredentialError):
                await telegram.verify(VALID_FIELDS[telegram.NAME], raw)
    assert BOT_TOKEN in caplog.text  # o positivo: sem a defesa, a URL vai para o log
    assert any(r.name == "httpx" and BOT_TOKEN in r.getMessage() for r in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        async with verification_client(transport=httpx.MockTransport(_refuses_echoing)) as http:
            with pytest.raises(InvalidCredentialError) as erro:
                await telegram.verify(VALID_FIELDS[telegram.NAME], http)
    assert erro.value.code == "unauthorized"
    assert BOT_TOKEN not in caplog.text
    _reset_http_loggers()


def test_gate_3_pela_rota_o_token_nao_aparece_no_log_em_debug_nem_na_resposta(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Callable[..., Stubs],
    transport: Recorder,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`POST /canais/credencial` com o bot: 401 ecoando o token, e o token ESTÁ
    na URL da requisição. Captura em DEBUG no logger raiz e varre."""
    stubs = db()
    transport.refuse_echoing_the_token(BOT_TOKEN)

    with caplog.at_level(logging.DEBUG):
        resposta = _post_credential(client, cabecalho, telegram.NAME)

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "unauthorized"
    assert BOT_TOKEN in str(transport.requests[0].url)  # a premissa do caso real
    assert BOT_TOKEN not in caplog.text
    assert BOT_TOKEN not in resposta.text
    assert stubs.bound_ctx.opened == 0
    [recusa] = [r for r in caplog.records if r.name == canais.logger.name]
    assert "unauthorized" in recusa.getMessage()


# ---------------------------------------------------------------------------
# A matriz: o canal de cada provedor, a lista de cada canal
# ---------------------------------------------------------------------------
def test_o_canal_de_cada_provedor_e_a_lista_de_cada_canal_nos_dois_sentidos() -> None:
    assert CHANNELS == ("whatsapp", "telegram")
    assert providers_of("whatsapp") == WHATSAPP_PROVIDERS
    assert providers_of("telegram") == (telegram.NAME,)
    for provider in WHATSAPP_PROVIDERS:
        assert channel_of(provider) == "whatsapp"
    assert channel_of(telegram.NAME) == "telegram"
    # Partição: todo provedor de canal está em exatamente uma lista.
    assert sorted(p for c in CHANNELS for p in providers_of(c)) == sorted(CHANNEL_PROVIDERS)
    with pytest.raises(UnknownProviderError):
        channel_of("evolution_api")
    with pytest.raises(UnknownChannelError):
        providers_of("sms")


def test_as_duas_renderizacoes_sao_a_lista_exata_do_canal_e_ligam_o_tenant() -> None:
    """`_DEACTIVATE_SQL` e `_CREDENTIAL_STATUS_SQL` existem uma vez por canal,
    cada uma com a lista de `providers_of` — e nenhuma nomeia o outro canal."""
    context = SystemContext(tenant_id=TENANT_ID, task="test")
    for by_channel in (canais._DEACTIVATE_BY_CHANNEL, canais._CREDENTIAL_STATUS_BY_CHANNEL):
        assert set(by_channel) == set(CHANNELS)
        for channel, sql in by_channel.items():
            assert "{channel_providers}" not in sql
            esperado = ", ".join(f"'{p}'" for p in providers_of(channel))
            assert f"provider in ({esperado})" in sql
            for other in CHANNELS:
                for provider in providers_of(other) if other != channel else ():
                    assert f"'{provider}'" not in sql
            assert bind_tenant(sql, {}, context)["tenant_id"] == TENANT_ID


# ---------------------------------------------------------------------------
# A credencial por canal — gravar o bot desliga só o bot
# ---------------------------------------------------------------------------
def test_gravar_o_bot_desliga_so_o_telegram_ativo_e_deixa_o_whatsapp(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """⛔ É a linha 1 da SPEC §2.2 pela porta da credencial. A instrução de
    desativação que a rota executou nomeia `'telegram'` e nenhum provedor de
    WhatsApp; a de status idem. Quem a executa ao lado de um `meta_cloud` ativo
    que sobrevive é o `97`."""
    stubs = db()

    resposta = _post_credential(client, cabecalho, telegram.NAME)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["channel"] == "telegram"
    assert corpo["configured"] is True
    assert corpo["provider"] == telegram.NAME
    assert corpo["public_identity"] == BOT_USERNAME
    assert BOT_TOKEN not in resposta.text

    [(deactivate, _)] = _statements(stubs.bound, "set active = false")
    [(status, _)] = _statements(stubs.bound, "max(s.updated_at)")
    for sql in (deactivate, status):
        assert f"'{telegram.NAME}'" in sql
        for provider in WHATSAPP_PROVIDERS:
            assert f"'{provider}'" not in sql
    assert deactivate == canais._DEACTIVATE_BY_CHANNEL["telegram"]

    [(_, upsert)] = _statements(stubs.bound, "on conflict")
    assert upsert["config"].obj == {"public_identity": BOT_USERNAME}
    [(_, store)] = _statements(stubs.bound, "vault.create_secret")
    assert store["key"] == "bot_token" and store["value"] == BOT_TOKEN
    [(_, audit)] = _statements(stubs.bound, "app.audit_log")
    assert audit["depois"].obj["keys"] == ["bot_token"]
    assert BOT_TOKEN not in _all_text(audit)
    # Sem webhook registrado antes, a saúde não é tocada.
    assert _statements(stubs.bound, "fn_record_channel_health") == []


def test_regravar_o_token_do_bot_com_webhook_registrado_derruba_a_saude(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """⛔ O upsert troca `config` inteiro e leva `webhook_url` junto; sem isto a
    saúde ficaria `connected` e a tela diria "pronto" ao lado de "Conectar
    bot", com o Telegram entregando num caminho que o banco não conhece mais."""
    stubs = db(deactivated=[{"provider": telegram.NAME, "had_webhook": True}])

    resposta = _post_credential(client, cabecalho, telegram.NAME)

    assert resposta.status_code == 200, resposta.text
    [(_, health)] = _statements(stubs.bound, "fn_record_channel_health")
    assert health["status"] == "disconnected"
    assert health["detail"] == "token do bot regravado; conecte o bot de novo"
    assert health["integration_id"] == INTEGRATION_ID


def test_regravar_o_whatsapp_com_webhook_no_telegram_nao_toca_a_saude_do_bot(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """A regra é do canal do provedor que entra: o WhatsApp desliga só WhatsApp,
    e o webhook do bot ao lado não é assunto dele."""
    stubs = db(deactivated=[{"provider": meta_cloud.NAME, "had_webhook": False}])
    transport.accept(meta_cloud)

    resposta = _post_credential(client, cabecalho, meta_cloud.NAME)

    assert resposta.status_code == 200, resposta.text
    assert _statements(stubs.bound, "fn_record_channel_health") == []


def test_gravar_o_whatsapp_desliga_so_o_whatsapp_e_deixa_o_bot(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    stubs = db()
    transport.accept(meta_cloud)

    resposta = _post_credential(client, cabecalho, meta_cloud.NAME)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["channel"] == "whatsapp"
    [(deactivate, _)] = _statements(stubs.bound, "set active = false")
    assert deactivate == canais._DEACTIVATE_BY_CHANNEL["whatsapp"]
    assert f"'{telegram.NAME}'" not in deactivate
    for provider in WHATSAPP_PROVIDERS:
        assert f"'{provider}'" in deactivate


def test_get_credencial_por_canal_e_o_default_e_whatsapp(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db()

    bot = client.get("/canais/credencial", params={"canal": "telegram"}, headers=cabecalho)
    assert bot.status_code == 200
    assert bot.json()["channel"] == "telegram"
    assert bot.json()["public_identity"] == BOT_USERNAME
    [(sql, _)] = _statements(stubs.bound, "max(s.updated_at)")
    assert sql == canais._CREDENTIAL_STATUS_BY_CHANNEL["telegram"]

    stubs.bound.statements.clear()
    stubs.bound.params.clear()
    default = client.get("/canais/credencial", headers=cabecalho)
    assert default.json()["channel"] == "whatsapp"
    [(sql, _)] = _statements(stubs.bound, "max(s.updated_at)")
    assert sql == canais._CREDENTIAL_STATUS_BY_CHANNEL["whatsapp"]


def test_get_credencial_com_canal_desconhecido_e_422_sem_tocar_o_banco(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db()
    resposta = client.get("/canais/credencial", params={"canal": "sms"}, headers=cabecalho)
    assert resposta.status_code == 422
    assert stubs.bound.statements == []


def test_get_provedores_devolve_os_quatro_e_o_bot_tem_um_campo_secreto(
    client: TestClient, cabecalho: dict[str, str]
) -> None:
    corpo = client.get("/canais/provedores", headers=cabecalho).json()
    assert [f["provider"] for f in corpo] == list(CHANNEL_PROVIDERS)
    assert [f["channel"] for f in corpo] == ["whatsapp", "whatsapp", "whatsapp", "telegram"]
    [bot] = [f for f in corpo if f["provider"] == telegram.NAME]
    assert bot["capabilities"]["requires_recipient_opt_in"] is True
    assert [(f["name"], f["secret"]) for f in bot["fields"]] == [("bot_token", True)]


# ---------------------------------------------------------------------------
# Conectar — gravar antes de chamar
# ---------------------------------------------------------------------------
def test_conectar_sem_admin_e_403_com_a_frase_do_bot_sem_http_nem_transacao(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    stubs = db(admin=False)

    resposta = _connect(client, cabecalho)

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Conectar o bot é do administrador do cliente."
    assert transport.requests == []
    assert stubs.bound_ctx.opened == 0


def test_conectar_sem_api_public_url_e_422_sem_http_nem_transacao(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """Sem endereço público não há o que registrar — e registrar um endereço
    inventado deixaria o Telegram entregando para ninguém."""
    stubs = db(public_url=None)

    resposta = _connect(client, cabecalho)

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "no_public_url"
    assert "API_PUBLIC_URL" in resposta.json()["detail"]
    assert transport.requests == []
    assert stubs.bound_ctx.opened == 0


@pytest.mark.parametrize("sem", ["integracao", "ponteiro"])
def test_conectar_sem_bot_ativo_com_ponteiro_e_422_no_credential_sem_http(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Callable[..., Stubs],
    transport: Recorder,
    sem: str,
) -> None:
    """Integração ausente e integração sem token no cofre são a mesma recusa, com
    a frase do bot — a do `no_credential` da WABA mandaria o operador ao lugar
    errado. E nada é gravado."""
    stubs = db(bot=None if sem == "integracao" else FakeBot(has_token=False))

    resposta = _connect(client, cabecalho)

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "no_credential"
    assert "bot" in resposta.json()["detail"]
    assert "WABA" not in resposta.json()["detail"]
    assert transport.requests == []
    assert _writes(stubs.bound) == []


def test_conectar_grava_antes_de_chamar_a_plataforma_e_a_transacao_ja_fechou(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """⛔ Mutação: mover o `setWebhook` para dentro do `tenant_scope`, ou para
    antes dele, deixa isto vermelho. Um `setWebhook` que passou e uma gravação
    que falhou deixaria o Telegram apontando para um caminho que o banco não
    conhece — por isso a ordem é gravar, fechar, chamar."""
    stubs = db()
    at_http: list[tuple[list[str], list[str]]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        stubs.timeline.append(f"http:{_method(request)}")
        at_http.append((list(stubs.timeline), _writes(stubs.bound)))
        return bot_api(request)

    transport.respond = respond

    resposta = _connect(client, cabecalho)

    assert resposta.status_code == 200, resposta.text
    [(timeline_at_http, writes_at_http)] = at_http
    assert timeline_at_http[-1] == "http:setWebhook"
    assert timeline_at_http[-2] == "tenant_scope:exit"  # fechada antes de chamar
    assert any("config ||" in s for s in writes_at_http)
    assert any("vault.create_secret" in s for s in writes_at_http)
    assert any("app.audit_log" in s for s in writes_at_http)
    assert not any("fn_record_channel_health" in s for s in writes_at_http)  # a saúde vem depois


def test_conectar_registra_o_endereco_gravado_com_o_segredo_gravado_e_fica_connected(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """O que foi ao Telegram é o que ficou no banco: a `url` do `setWebhook` é
    `API_PUBLIC_URL + /webhooks/telegram/ + path_token` do `config`, e o
    `secret_token` é o valor gravado no cofre sob `webhook_secret`."""
    stubs = db()
    assert stubs.bot is not None

    resposta = _connect(client, cabecalho)

    assert resposta.status_code == 200, resposta.text
    [setw] = [r for r in transport.requests if _method(r) == "setWebhook"]
    enviado = _sent(setw)
    path_token = stubs.bot.config["webhook_path_token"]
    assert path_token and len(path_token) >= 24
    assert enviado["url"] == f"{PUBLIC_URL}/webhooks/telegram/{path_token}"
    assert enviado["url"] == stubs.bot.config["webhook_url"]
    [(_, store)] = _statements(stubs.bound, "vault.create_secret")
    assert store["key"] == "webhook_secret"
    assert store["value"] == enviado["secret_token"]
    assert stubs.bot.health == ("connected", "webhook registrado")

    corpo = resposta.json()
    assert corpo["provider"] == telegram.NAME
    assert corpo["bot_username"] == BOT_USERNAME
    assert corpo["webhook_configured"] is True
    assert corpo["webhook_url"] == enviado["url"]
    assert corpo["webhook_path_token"] == path_token
    assert corpo["health_status"] == "connected"
    assert corpo["health_detail"] == "webhook registrado"
    assert corpo["ready"] is True
    assert corpo["capabilities"]["requires_recipient_opt_in"] is True


def test_conectar_o_webhook_secret_nunca_sai_da_rota(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Callable[..., Stubs],
    transport: Recorder,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Gate 5: o valor só existe em `params["value"]` da gravação no cofre e no
    corpo que foi ao Telegram. Nem resposta, nem log em DEBUG, nem auditoria,
    nem texto de instrução. O `path_token` pode ir à trilha — é a cauda pública."""
    stubs = db()

    with caplog.at_level(logging.DEBUG):
        resposta = _connect(client, cabecalho)

    assert resposta.status_code == 200
    [setw] = [r for r in transport.requests if _method(r) == "setWebhook"]
    secret = _sent(setw)["secret_token"]
    assert secret and len(secret) >= 32
    assert secret not in resposta.text
    assert secret not in caplog.text
    assert BOT_TOKEN not in caplog.text
    assert BOT_TOKEN not in resposta.text
    for statement, params in zip(stubs.bound.statements, stubs.bound.params, strict=True):
        assert secret not in statement and BOT_TOKEN not in statement
        sem_value = {k: v for k, v in (params or {}).items() if k != "value"}
        assert secret not in _all_text(sem_value)
        assert BOT_TOKEN not in _all_text(sem_value)
    [(_, audit)] = _statements(stubs.bound, "app.audit_log")
    assert audit["depois"].obj["keys"] == ["webhook_secret"]
    assert audit["depois"].obj["webhook_path_token"] == resposta.json()["webhook_path_token"]
    assert audit["entity_id"] == str(INTEGRATION_ID)


def test_conectar_recusado_grava_disconnected_com_o_codigo_e_devolve_422(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """⛔ `detail` de `fn_record_channel_health` nunca é corpo do provedor: o
    banco grava o que recebe (achado do guardião da onda 1). O Telegram responde
    401 com o token e um texto; o `detail` gravado é a frase da rota com o
    código, e só. A integração fica com o `webhook_url` gravado — a tela mostra
    o endereço e a saúde `disconnected`, que é o estado real."""
    stubs = db()
    assert stubs.bot is not None

    def respond(request: httpx.Request) -> httpx.Response:
        if _method(request) == "setWebhook":
            return _refuses_echoing(request)
        return bot_api(request)

    transport.respond = respond

    resposta = _connect(client, cabecalho)

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "unauthorized"
    assert resposta.json()["detail"] == canais._WEBHOOK_REFUSALS["unauthorized"]
    assert BOT_TOKEN not in resposta.text
    assert REFUSAL_TEXT not in resposta.text

    assert stubs.bot.health == ("disconnected", "setWebhook recusado: unauthorized")
    [(_, health)] = _statements(stubs.bound, "fn_record_channel_health")
    assert BOT_TOKEN not in _all_text(health)
    assert REFUSAL_TEXT not in _all_text(health)
    # Gravado antes: o endereço está no `config`, numa transação; a saúde veio
    # numa segunda — duas aberturas do `tenant_scope`, nenhuma releitura.
    assert stubs.bot.config["webhook_url"]
    assert stubs.bound_ctx.opened == 2


def test_conectar_recusado_por_rede_e_unreachable_com_a_frase_do_webhook(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    stubs = db()

    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"refused {request.url}", request=request)

    transport.respond = respond

    resposta = _connect(client, cabecalho)

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "unreachable"
    assert resposta.json()["detail"] == canais._WEBHOOK_REFUSALS["unreachable"]
    assert stubs.bot is not None
    assert stubs.bot.health == ("disconnected", "setWebhook recusado: unreachable")


# ---------------------------------------------------------------------------
# Desconectar — chamar antes de gravar, e rotacionar
# ---------------------------------------------------------------------------
def test_desconectar_chama_a_plataforma_antes_da_escrita_e_rotaciona(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """Conecta, depois desconecta. No `deleteWebhook` nenhuma escrita aconteceu
    ainda; depois dele o `path_token` MUDOU, o `webhook_url` zerou, há um
    `webhook_secret` novo no cofre e a saúde é `disconnected` com a frase da
    rota. Reconectar não devolve o endereço antigo (SPEC §6)."""
    stubs = db()
    assert stubs.bot is not None
    assert _connect(client, cabecalho).status_code == 200
    [setw] = [r for r in transport.requests if _method(r) == "setWebhook"]
    first_secret = _sent(setw)["secret_token"]
    first_path = stubs.bot.config["webhook_path_token"]
    stubs.bound.statements.clear()
    stubs.bound.params.clear()
    writes_at_delete: list[list[str]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if _method(request) == "deleteWebhook":
            writes_at_delete.append(_writes(stubs.bound))
        return bot_api(request)

    transport.respond = respond

    resposta = _disconnect(client, cabecalho)

    assert resposta.status_code == 200, resposta.text
    assert writes_at_delete == [[]]  # nada escrito quando a plataforma foi chamada
    corpo = resposta.json()
    assert corpo["webhook_configured"] is False
    assert corpo["webhook_url"] is None
    assert corpo["webhook_path_token"] != first_path
    assert corpo["webhook_path_token"] == stubs.bot.config["webhook_path_token"]
    assert stubs.bot.config["webhook_url"] is None
    assert stubs.bot.health == ("disconnected", "desconectado pelo administrador")
    assert corpo["health_status"] == "disconnected"
    assert corpo["ready"] is False
    [(_, store)] = _statements(stubs.bound, "vault.create_secret")
    assert store["key"] == "webhook_secret"
    assert store["value"] != first_secret
    assert store["value"] not in resposta.text
    [(_, audit)] = _statements(stubs.bound, "app.audit_log")
    assert audit["antes"].obj["webhook_path_token"] == first_path
    assert audit["depois"].obj["webhook_url"] is None
    assert audit["depois"].obj["keys"] == ["webhook_secret"]
    assert first_secret not in _all_text(audit) and store["value"] not in _all_text(audit)


def test_desconectar_recusado_e_422_e_nada_muda(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    """Se a plataforma não confirmou a remoção, rotacionar aqui deixaria o
    Telegram entregando num caminho morto e a tela dizendo "desconectado". A
    rota recusa com o código e não toca o banco — o administrador tenta de novo."""
    stubs = db(bot=connected_bot())
    transport.respond = _refuses_echoing

    resposta = _disconnect(client, cabecalho)

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "unauthorized"
    assert BOT_TOKEN not in resposta.text
    assert _writes(stubs.bound) == []
    assert stubs.bot is not None
    assert stubs.bot.config["webhook_path_token"] == "cauda-antiga"
    assert stubs.bot.health == ("connected", "webhook registrado")


def test_desconectar_sem_admin_e_403_e_sem_bot_e_no_credential(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], transport: Recorder
) -> None:
    stubs = db(admin=False)
    resposta = _disconnect(client, cabecalho)
    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Desconectar o bot é do administrador do cliente."
    assert transport.requests == [] and stubs.bound_ctx.opened == 0

    stubs = db(bot=None)
    resposta = _disconnect(client, cabecalho)
    assert resposta.status_code == 422
    assert resposta.json()["code"] == "no_credential"
    assert transport.requests == [] and _writes(stubs.bound) == []


# ---------------------------------------------------------------------------
# Conexões — os dois canais, um só, nenhum
# ---------------------------------------------------------------------------
def test_conexoes_com_os_dois_canais_lado_a_lado(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """Linha 1 da SPEC §2.2, na tela: WhatsApp oficial com a lista de bloqueio e
    o bot com a saúde, cada um de sua fonte — a função dá `health_status` e
    `health_changed_at`; `channel_health` dá `checked_at` e `detail`; `config`
    dá o `@username` e o webhook."""
    stubs = db(bot=connected_bot(), whatsapp=whatsapp_row(), blocked=[blocked_row()])

    resposta = client.get("/canais/conexoes", headers=cabecalho)

    assert resposta.status_code == 200, resposta.text
    tela = resposta.json()
    assert set(tela) == {"whatsapp", "telegram"}
    assert tela["whatsapp"]["provider"] == meta_cloud.NAME
    assert tela["whatsapp"]["rules_blocked"] == 1
    assert tela["whatsapp"]["blocked"] == [blocked_row()]
    assert tela["telegram"] == {
        "provider": telegram.NAME,
        "capabilities": {
            "official": True,
            "requires_templates": False,
            "ban_risk": False,
            "requires_recipient_opt_in": True,
        },
        "bot_username": BOT_USERNAME,
        "webhook_configured": True,
        "webhook_url": f"{PUBLIC_URL}/webhooks/telegram/cauda-antiga",
        "webhook_path_token": "cauda-antiga",
        "health_status": "connected",
        "health_checked_at": CHECKED_AT.isoformat().replace("+00:00", "Z"),
        "health_changed_at": CHANGED_AT.isoformat().replace("+00:00", "Z"),
        "health_detail": "webhook registrado",
        "ready": True,
    }
    # A linha do bot é lida por `tenant_scope`, com o provedor ligado por parâmetro.
    [(sql, params)] = _statements(stubs.bound, "config ->> 'webhook_url'")
    assert sql == canais._TELEGRAM_STATE_SQL
    assert params == {"provider": telegram.NAME}


def test_conexoes_so_com_o_bot_nao_consulta_a_lista_e_nao_tem_whatsapp(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(bot=FakeBot())

    tela = client.get("/canais/conexoes", headers=cabecalho).json()

    assert tela["whatsapp"] is None
    assert tela["telegram"]["bot_username"] == BOT_USERNAME
    assert tela["telegram"]["webhook_configured"] is False
    assert tela["telegram"]["webhook_url"] is None
    assert tela["telegram"]["webhook_path_token"] is None
    assert tela["telegram"]["health_status"] is None
    assert tela["telegram"]["health_checked_at"] is None
    assert tela["telegram"]["health_detail"] is None
    assert tela["telegram"]["ready"] is False
    assert len(stubs.user.statements) == 1  # só a função; a lista é do WhatsApp oficial


def test_conexoes_blocked_so_quando_o_whatsapp_e_oficial(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """`z_api` + bot: a função não conta regra bloqueada (o bot é `official`, mas
    a CTE só olha a linha de WhatsApp), e a rota não pergunta a lista."""
    stubs = db(
        bot=FakeBot(),
        whatsapp=whatsapp_row(provider=z_api.NAME, official=False, rules_blocked=0, ready=True),
        blocked=[blocked_row()],
    )

    tela = client.get("/canais/conexoes", headers=cabecalho).json()

    assert tela["whatsapp"]["blocked"] == []
    assert tela["whatsapp"]["ready"] is True
    assert tela["telegram"]["provider"] == telegram.NAME
    assert not any("from app.alert_rule" in s for s in stubs.user.statements)


def test_conexoes_sem_canal_nenhum_e_as_duas_linhas_nulas_sem_tenant_scope(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(bot=None)

    resposta = client.get("/canais/conexoes", headers=cabecalho)

    assert resposta.status_code == 200
    assert resposta.json() == {"whatsapp": None, "telegram": None}
    assert stubs.bound_ctx.opened == 0


@pytest.mark.parametrize(
    ("health", "ready"),
    [(("disconnected", "x"), True), (("connected", "x"), False), (None, True)],
)
def test_conexoes_ready_do_bot_e_a_coluna_da_funcao_e_nao_e_recalculado(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Callable[..., Stubs],
    health: tuple[str, str] | None,
    ready: bool,
) -> None:
    """Combinações que a função nunca produz, para provar que a rota não refaz
    a conta: `ready` volta como a coluna veio, seja qual for a saúde."""
    db(bot=FakeBot(health=health, readiness={"ready": ready}))

    tela = client.get("/canais/conexoes", headers=cabecalho).json()

    assert tela["telegram"]["ready"] is ready
    assert tela["telegram"]["health_status"] == (health[0] if health else None)


def test_conexoes_o_bot_tem_exatamente_os_campos_do_contrato_e_nenhum_segredo(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """A linha do stub vem envenenada com o que uma consulta descuidada traria
    junto; a resposta tem só o contrato."""
    bot = FakeBot(
        config={
            "public_identity": BOT_USERNAME,
            "bot_token": BOT_TOKEN,
            "webhook_secret": "segredo-que-nao-pode-sair",
            "vault_id": "0d5f6b2e",
        }
    )
    db(bot=bot)

    resposta = client.get("/canais/conexoes", headers=cabecalho)

    assert set(resposta.json()["telegram"]) == {
        "provider",
        "capabilities",
        "bot_username",
        "webhook_configured",
        "webhook_url",
        "webhook_path_token",
        "health_status",
        "health_checked_at",
        "health_changed_at",
        "health_detail",
        "ready",
    }
    assert BOT_TOKEN not in resposta.text
    assert "segredo-que-nao-pode-sair" not in resposta.text
    assert "vault" not in resposta.text.lower()
    assert "0d5f6b2e" not in resposta.text


def test_as_instrucoes_do_bot_ligam_o_tenant_pela_integracao() -> None:
    """`_TELEGRAM_STATE_SQL`, `_TELEGRAM_WEBHOOK_SQL` e `saude.RECORD_HEALTH_SQL`
    (a porta única, compartilhada com o vigia) passam por `bind_tenant` e
    recortam por `tenant_id` da integração — a função de saúde só é avaliada se
    a integração for do tenant (zero linhas do `from … where` é zero chamadas).
    Só as três chaves públicas de `config` saem."""
    context = SystemContext(tenant_id=TENANT_ID, task="test")
    for sql in (
        canais._TELEGRAM_STATE_SQL,
        canais._TELEGRAM_WEBHOOK_SQL,
        saude.RECORD_HEALTH_SQL,
    ):
        assert bind_tenant(sql, {}, context)["tenant_id"] == TENANT_ID
        assert "tenant_id = %(tenant_id)s" in sql
    assert "from app.integration i" in saude.RECORD_HEALTH_SQL
    assert "app.fn_record_channel_health(i.id" in saude.RECORD_HEALTH_SQL
    assert canais.record_health is saude.record_health  # uma porta, não uma cópia
    state = canais._TELEGRAM_STATE_SQL.lower()
    assert "vault_id" not in state and "select *" not in state
    assert state.count("config ->>") == 3
    # O `config` inteiro nunca sai: só as três chaves públicas, por nome.
    assert "i.config as" not in state and "i.config," not in state and ", i.config" not in state
    assert "public_identity" in state and "webhook_url" in state and "webhook_path_token" in state


def test_o_bot_nao_e_provedor_de_whatsapp_no_sender() -> None:
    """O par de `test_o_sender_conhece_todo_provedor_de_whatsapp_da_matriz`:
    desde o C5 o sender constrói o bot pela fábrica como os outros três, mas
    o bot NÃO é provedor de WhatsApp — `outbox.route` só o escolhe para quem
    tem identidade vigente (SPEC §8), e `outbox._PROVIDER_SQL` (o WhatsApp
    ativo do tenant, também o destino do re-roteamento após `blocked`) nunca o
    devolve. Um bot na lista de WhatsApp entregaria a um `chat_id` que ninguém
    resolveu."""
    from operax.alertas import capacidades, outbox

    assert telegram.NAME in PROVIDERS
    assert telegram.NAME in capacidades.CHANNEL_PROVIDERS
    assert telegram.NAME not in capacidades.WHATSAPP_PROVIDERS
    assert f"'{telegram.NAME}'" not in outbox._PROVIDER_SQL
    assert outbox.TELEGRAM_PROVIDER == telegram.NAME
    assert callable(telegram.TelegramProvider.enviar)


# ---------------------------------------------------------------------------
# `TelegramProvider.enviar` — sob o contrato de template (SPEC-CANAIS §2)
# ---------------------------------------------------------------------------
TEMPLATE_BODY = "FastPark: {{1}} teve {{2}} indício(s) em {{3}}. Detalhe: {{4}}"
CHAT_ID = "987654321012"


def _message(body: str | None = TEMPLATE_BODY) -> Message:
    return Message(
        destination=CHAT_ID,
        template="deviation_individual",
        variables=("employee", "total", "unit", "link"),
        facts={
            "employee": "Colab Sonda",
            "total": "2",
            "unit": "Shopping Norte",
            "link": "https://app.exemplo.test/?u=1",
        },
        body=body,
    )


def _send_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"ok": True, "result": {"message_id": 4242, "chat": {"id": int(CHAT_ID)}}},
    )


async def _enviar(
    respond: Callable[[httpx.Request], httpx.Response], message: Message | None = None
) -> tuple[Delivery, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return respond(request)

    async with verification_client(transport=httpx.MockTransport(handler)) as http:
        provider = telegram.TelegramProvider(BOT_TOKEN, http)
        return await provider.enviar(message or _message()), seen


async def test_enviar_manda_exatamente_o_render_do_template_sem_parse_mode() -> None:
    """O gate "texto idêntico a partir de um template só": o `text` do
    `sendMessage` é `render(body, message)` byte a byte — a mesma função que o
    `z_api`/`uazapi` usarão sobre o mesmo `body`. Sem `parse_mode`, sem botão:
    entram quando o template os declarar (§2)."""
    entrega, seen = await _enviar(_send_ok)

    assert entrega == Delivery(status="sent", provider_message_id="4242")
    [request] = seen
    assert request.method == "POST"
    assert request.url.host == "api.telegram.org"
    assert request.url.path == f"/bot{BOT_TOKEN}/sendMessage"
    enviado = _sent(request)
    assert enviado == {"chat_id": CHAT_ID, "text": render(TEMPLATE_BODY, _message())}
    assert enviado["text"] == (
        "FastPark: Colab Sonda teve 2 indício(s) em Shopping Norte. "
        "Detalhe: https://app.exemplo.test/?u=1"
    )
    assert "{{" not in enviado["text"]
    assert "parse_mode" not in enviado
    assert telegram.TelegramProvider(BOT_TOKEN, httpx.AsyncClient()).name == telegram.NAME


async def test_enviar_sem_body_recusa_antes_de_qualquer_http() -> None:
    """Sem `body` não há de onde tirar a frase — e este provedor não a inventa.
    É a fronteira assistente → sender da §2, item 2: nenhum caminho leva texto
    livre a `sendMessage`."""
    entrega, seen = await _enviar(_send_ok, _message(body=None))

    assert entrega == Delivery(status="failed", error="no_body")
    assert seen == []


async def test_403_e_blocked_e_o_provedor_nao_revoga() -> None:
    """A pessoa bloqueou o bot. `blocked` é o que o C4 usa para revogar a
    identidade — aqui só se informa. O corpo do 403 (com o `description` da
    plataforma) não chega ao `error`."""

    def blocked(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "ok": False,
                "error_code": 403,
                "description": "Forbidden: bot was blocked by the user",
            },
        )

    entrega, _ = await _enviar(blocked)

    assert entrega == Delivery(status="failed", error="blocked")
    assert "Forbidden" not in (entrega.error or "")


@pytest.mark.parametrize(
    ("respond", "error"),
    [
        (
            lambda _: httpx.Response(400, json={"ok": False, "description": "chat not found"}),
            "http_400",
        ),
        (lambda _: httpx.Response(401, json={"ok": False, "token": BOT_TOKEN}), "http_401"),
        (lambda _: httpx.Response(429, json={"ok": False}), "unreachable"),
        (lambda _: httpx.Response(502, text=BOT_TOKEN), "unreachable"),
        (lambda _: httpx.Response(200, content=b"<html>"), "malformed"),
        (lambda _: httpx.Response(200, json={"ok": False}), "malformed"),
        (lambda _: httpx.Response(200, json={"ok": True, "result": {}}), "malformed"),
        (
            lambda _: httpx.Response(200, json={"ok": True, "result": {"message_id": "x"}}),
            "malformed",
        ),
    ],
)
async def test_outras_recusas_sao_failed_com_o_codigo_e_nunca_o_corpo(
    respond: Callable[[httpx.Request], httpx.Response], error: str
) -> None:
    entrega, _ = await _enviar(respond)

    assert entrega.status == "failed"
    assert entrega.error == error
    assert entrega.provider_message_id is None
    assert BOT_TOKEN not in (entrega.error or "")
    assert "chat not found" not in (entrega.error or "")


async def test_enviar_com_a_rede_fora_e_unreachable_e_nenhuma_excecao_sai() -> None:
    """Nenhuma exceção sai de `enviar`: a do `httpx` nomeia a URL, e a URL é o
    token. O sender grava `error`, não um traceback."""

    def falls(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"refused {request.url}", request=request)

    entrega, _ = await _enviar(falls)

    assert entrega == Delivery(status="failed", error="unreachable")


async def test_gate_3_no_enviar_o_token_nao_aparece_no_log_em_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Positivo primeiro (cliente cru loga a URL), depois a defesa."""
    _reset_http_loggers()
    with caplog.at_level(logging.DEBUG):
        async with httpx.AsyncClient(transport=httpx.MockTransport(_refuses_echoing)) as raw:
            await telegram.TelegramProvider(BOT_TOKEN, raw).enviar(_message())
    assert BOT_TOKEN in caplog.text

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        entrega, seen = await _enviar(_refuses_echoing)
    assert entrega.status == "failed" and entrega.error == "http_401"
    assert BOT_TOKEN in str(seen[0].url)  # a premissa
    assert BOT_TOKEN not in caplog.text
    assert CHAT_ID not in caplog.text
    _reset_http_loggers()


def test_enviar_devolve_delivery_e_nunca_levanta_invalid_credential() -> None:
    """`_codes_raised(telegram)` continua nos três de `verify`: `enviar` não
    recusa por exceção, devolve `Delivery` — o sender não trata exceção de
    provedor, grava `error`."""
    assert _codes_raised(telegram) == {"unauthorized", "unreachable", "malformed"}
    assert "blocked" not in _codes_raised(telegram)


def test_message_body_e_opcional_e_o_null_provider_continua_igual() -> None:
    """`Message` ganhou `body` com default: o sender de hoje, que não o passa,
    continua compilando, e o `NullProvider` não olha para ele."""
    sem = Message(destination="+55", template="t", variables=(), facts={})
    assert sem.body is None
    assert _message().body == TEMPLATE_BODY


# ---------------------------------------------------------------------------
# API_PUBLIC_URL — a forma, e vazio é ausente
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["http://api.exemplo.test", "https://api.exemplo.test/", "api.x"])
def test_api_public_url_exige_https_e_sem_barra_final(bad: str) -> None:
    with pytest.raises(ValidationError) as erro:
        Settings(api_public_url=bad)
    assert "https://" in str(erro.value)


def test_api_public_url_vazia_e_ausente_e_valida_e_mantida() -> None:
    """`.env.example` a lista em branco, como as outras opcionais: em branco é
    `None`, e `conectar` responde `no_public_url` em vez de registrar `/webhooks…`
    sem host."""
    assert Settings(api_public_url="").api_public_url is None
    assert Settings().api_public_url is None
    assert Settings(api_public_url=PUBLIC_URL).api_public_url == PUBLIC_URL


def test_o_valor_de_teste_do_token_do_bot_nao_e_um_token_de_whatsapp() -> None:
    """Sentinela das varreduras: os dois valores são distintos e nenhum contém o
    outro — senão "o token não aparece" passaria pelo motivo errado."""
    assert TOKEN not in BOT_TOKEN and BOT_TOKEN not in TOKEN
