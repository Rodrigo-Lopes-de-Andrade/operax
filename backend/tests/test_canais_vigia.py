"""O vigia que pergunta — e não religa (SPEC-CANAIS §7).

Quatro portões (SPRINTS-CANAIS, C3, onda 2b):

1. **os desfechos** — `connected` só com a URL igual à registrada, sem erro de
   entrega em 24 h e fila abaixo do teto; `disconnected` com a frase do módulo
   para URL ausente, URL diferente, erro recente e fila acumulada; `unknown`
   com o código quando a plataforma recusa ou não responde;
2. **nenhum `setWebhook`** — em cenário nenhum, sobre TODAS as requisições que
   o transporte viu; e o fonte do módulo não conhece a função;
3. **`detail` nunca é corpo do provedor** — a `last_error_message` do Telegram
   não chega ao banco;
4. **o token fora do log sob DEBUG** — o vigia usa o `verification_client`,
   e o token está na URL da Bot API.

⚠️ O QUE ESTA SUÍTE NÃO PODE PROVAR
`fn_record_channel_health` gravando de fato e `status_changed_at` parado numa
medição igual são `scripts/97_teste_canais.py`. Aqui o banco é o stub das
outras suítes de canais.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest

from operax.alertas import saude, vigia
from operax.alertas.provedores import telegram
from operax.alertas.provedores.base import verification_client
from operax.core.tenant import SystemContext, bind_tenant
from tests.conftest import TENANT_ID
from tests.test_canais_credencial import BOT_TOKEN, Recorder, _all_text, _reset_http_loggers
from tests.test_canais_telegram import _method
from tests.test_canais_templates import AnsweringScope, TimedScopeContext, _statements

INTEGRATION_ID = UUID("33333333-3333-4333-8333-333333333335")
WEBHOOK_URL = "https://api.exemplo.test/webhooks/telegram/cauda-publica-vigia-0123456789"
#: O que a plataforma ecoa em `last_error_message` — e o que não pode chegar ao `detail`.
PLATFORM_ERROR = "Wrong response from the webhook: 502 Bad Gateway"
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def info(**overrides: Any) -> telegram.WebhookInfo:
    base: dict[str, Any] = {
        "url": WEBHOOK_URL,
        "pending_update_count": 0,
        "last_error_date": None,
        "last_error_message": None,
    }
    return telegram.WebhookInfo(**(base | overrides))


def webhook_info_response(
    result: dict[str, Any], timeline: list[str] | None = None
) -> Callable[[httpx.Request], httpx.Response]:
    def respond(request: httpx.Request) -> httpx.Response:
        assert _method(request) == "getWebhookInfo"
        if timeline is not None:
            timeline.append("http")
        return httpx.Response(200, json={"ok": True, "result": result})

    return respond


@dataclass
class Stubs:
    bound: AnsweringScope
    bound_ctx: TimedScopeContext
    timeline: list[str]
    health: list[tuple[str, str]]


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Stubs]:
    def install(
        *, bot: bool = True, token: bool = True, webhook_url: str | None = WEBHOOK_URL
    ) -> Stubs:
        timeline: list[str] = []
        health: list[tuple[str, str]] = []

        def record(params: Any) -> dict[str, Any]:
            health.append((params["status"], params["detail"]))
            return {"fn_record_channel_health": None}

        bound = AnsweringScope(
            {
                "config ->> 'webhook_url'": (
                    {"id": INTEGRATION_ID, "webhook_url": webhook_url} if bot else None
                ),
                "vault.decrypted_secrets": {"decrypted_secret": BOT_TOKEN} if token else None,
                "fn_record_channel_health": record,
            }
        )
        bound_ctx = TimedScopeContext(bound, timeline, "tenant_scope")
        monkeypatch.setattr(vigia, "tenant_scope", lambda _c: bound_ctx)
        return Stubs(bound=bound, bound_ctx=bound_ctx, timeline=timeline, health=health)

    return install


@pytest.fixture
def transport() -> Iterator[Recorder]:
    recorder = Recorder()
    recorder.respond = webhook_info_response({"url": WEBHOOK_URL, "pending_update_count": 0})
    _reset_http_loggers()
    yield recorder
    _reset_http_loggers()


async def _check(stubs: Stubs, transport: Recorder) -> vigia.HealthResult | None:
    context = SystemContext(tenant_id=TENANT_ID, task=vigia.TASK)
    async with verification_client(transport=httpx.MockTransport(transport.handler)) as http:
        return await vigia.check_tenant(context, http)


def _no_set_webhook(transport: Recorder) -> None:
    """⛔ Gate 2, em toda requisição vista: nada além de `getWebhookInfo`."""
    assert transport.requests, "o vigia não perguntou nada"
    for request in transport.requests:
        assert _method(request) == "getWebhookInfo", request.url.path
        assert request.method == "GET"


# ---------------------------------------------------------------------------
# Gate 1 — os desfechos, primeiro como função pura, depois pela rota inteira
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("webhook_info", "registered", "expected"),
    [
        (info(), WEBHOOK_URL, ("connected", "webhook registrado, sem erro de entrega")),
        (
            info(pending_update_count=99),
            WEBHOOK_URL,
            ("connected", "webhook registrado, sem erro de entrega"),
        ),
        (
            info(last_error_date=NOW - timedelta(hours=25), last_error_message=PLATFORM_ERROR),
            WEBHOOK_URL,
            ("connected", "webhook registrado, sem erro de entrega"),
        ),
        (info(url=None), WEBHOOK_URL, ("disconnected", "webhook ausente")),
        (info(url=None), None, ("disconnected", "webhook ausente")),
        (
            info(url="https://outro.exemplo.test/webhooks/telegram/x"),
            WEBHOOK_URL,
            ("disconnected", "webhook aponta para outro endereço"),
        ),
        (info(), None, ("disconnected", "webhook aponta para outro endereço")),
        (
            info(last_error_date=NOW - timedelta(hours=23), last_error_message=PLATFORM_ERROR),
            WEBHOOK_URL,
            ("disconnected", "Telegram registrou erro de entrega"),
        ),
        (
            info(last_error_date=NOW - timedelta(minutes=1)),
            WEBHOOK_URL,
            ("disconnected", "Telegram registrou erro de entrega"),
        ),
        (
            info(pending_update_count=100),
            WEBHOOK_URL,
            ("disconnected", "updates acumulados sem entrega no Telegram"),
        ),
        # URL errada E erro recente: a URL manda — é o que o administrador conserta.
        (
            info(url=None, last_error_date=NOW, last_error_message=PLATFORM_ERROR),
            WEBHOOK_URL,
            ("disconnected", "webhook ausente"),
        ),
    ],
)
def test_judge_decide_pelo_que_a_plataforma_disse_e_pelo_que_foi_registrado(
    webhook_info: telegram.WebhookInfo, registered: str | None, expected: tuple[str, str]
) -> None:
    status, detail = vigia.judge(webhook_info, registered, NOW)
    assert (status, detail) == expected
    assert PLATFORM_ERROR not in detail


async def test_connected_grava_pela_porta_unica_com_a_frase_do_vigia(
    db: Callable[..., Stubs], transport: Recorder
) -> None:
    stubs = db()
    transport.respond = webhook_info_response(
        {"url": WEBHOOK_URL, "pending_update_count": 0}, stubs.timeline
    )

    result = await _check(stubs, transport)

    assert result == vigia.HealthResult(
        tenant_id=TENANT_ID,
        status="connected",
        detail="webhook registrado, sem erro de entrega",
    )
    assert stubs.health == [("connected", "webhook registrado, sem erro de entrega")]
    [(sql, params)] = _statements(stubs.bound, "fn_record_channel_health")
    assert sql == saude.RECORD_HEALTH_SQL
    assert params["integration_id"] == INTEGRATION_ID
    _no_set_webhook(transport)
    # O token foi ao Telegram pelo caminho, e o HTTP aconteceu com a transação fechada.
    [request] = transport.requests
    assert request.url.path == f"/bot{BOT_TOKEN}/getWebhookInfo"
    assert stubs.bound_ctx.opened == 2
    # ⛔ O HTTP acontece ENTRE as duas transações, com a primeira fechada: uma
    # chamada dentro do `tenant_scope` segura a conexão do pool pelo tempo de
    # resposta da plataforma — e é isso que a linha do tempo mede.
    assert stubs.timeline == [
        "tenant_scope:enter",
        "tenant_scope:exit",
        "http",
        "tenant_scope:enter",
        "tenant_scope:exit",
    ]


async def test_webhook_ausente_e_disconnected_e_nao_religa(
    db: Callable[..., Stubs], transport: Recorder
) -> None:
    """⛔ O cenário em que religar seria tentador: o Telegram não tem webhook e
    nós sabemos qual seria. O vigia grava e para."""
    stubs = db()
    transport.respond = webhook_info_response({"url": "", "pending_update_count": 0})

    result = await _check(stubs, transport)

    assert result is not None and result.status == "disconnected"
    assert stubs.health == [("disconnected", "webhook ausente")]
    _no_set_webhook(transport)


async def test_webhook_em_outro_endereco_e_disconnected_e_nao_religa(
    db: Callable[..., Stubs], transport: Recorder
) -> None:
    stubs = db()
    transport.respond = webhook_info_response(
        {
            "url": "https://api.exemplo.test/webhooks/telegram/cauda-antiga-rotacionada",
            "pending_update_count": 0,
        }
    )

    await _check(stubs, transport)

    assert stubs.health == [("disconnected", "webhook aponta para outro endereço")]
    _no_set_webhook(transport)


async def test_erro_recente_e_disconnected_sem_a_mensagem_da_plataforma(
    db: Callable[..., Stubs], transport: Recorder
) -> None:
    """Gate 3: `last_error_message` pode ecoar a URL com o `path_token`; o
    `detail` gravado é a frase do vigia, e só."""
    stubs = db()
    recent = int((datetime.now(UTC) - timedelta(hours=1)).timestamp())
    transport.respond = webhook_info_response(
        {
            "url": WEBHOOK_URL,
            "pending_update_count": 2,
            "last_error_date": recent,
            "last_error_message": f"{PLATFORM_ERROR} at {WEBHOOK_URL}",
        }
    )

    await _check(stubs, transport)

    [(status, detail)] = stubs.health
    assert (status, detail) == ("disconnected", "Telegram registrou erro de entrega")
    assert PLATFORM_ERROR not in detail
    assert "cauda-publica-vigia" not in detail
    for params in stubs.bound.params:
        assert PLATFORM_ERROR not in _all_text(params)
    _no_set_webhook(transport)


async def test_fila_acumulada_e_disconnected(db: Callable[..., Stubs], transport: Recorder) -> None:
    stubs = db()
    transport.respond = webhook_info_response({"url": WEBHOOK_URL, "pending_update_count": 100})

    await _check(stubs, transport)

    assert stubs.health == [("disconnected", "updates acumulados sem entrega no Telegram")]
    _no_set_webhook(transport)


@pytest.mark.parametrize(
    ("respond", "code"),
    [
        (
            lambda request: httpx.Response(
                401, json={"ok": False, "description": PLATFORM_ERROR, "token": BOT_TOKEN}
            ),
            "unauthorized",
        ),
        (lambda request: httpx.Response(502, text=BOT_TOKEN), "unreachable"),
        (lambda request: httpx.Response(200, content=b'{"ok": true, "result": "x"}'), "malformed"),
    ],
)
async def test_recusa_da_plataforma_e_unknown_com_o_codigo_e_nao_religa(
    db: Callable[..., Stubs],
    transport: Recorder,
    respond: Callable[[httpx.Request], httpx.Response],
    code: str,
) -> None:
    stubs = db()
    transport.respond = respond

    result = await _check(stubs, transport)

    assert result is not None and result.status == "unknown"
    assert stubs.health == [("unknown", f"getWebhookInfo: {code}")]
    for params in stubs.bound.params:
        assert BOT_TOKEN not in _all_text(params)
        assert PLATFORM_ERROR not in _all_text(params)
    _no_set_webhook(transport)


async def test_rede_fora_e_unknown_unreachable(
    db: Callable[..., Stubs], transport: Recorder
) -> None:
    stubs = db()

    def falls(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"refused {request.url}", request=request)

    transport.respond = falls

    await _check(stubs, transport)

    assert stubs.health == [("unknown", "getWebhookInfo: unreachable")]


async def test_tenant_sem_bot_nao_pergunta_nem_grava(
    db: Callable[..., Stubs], transport: Recorder
) -> None:
    stubs = db(bot=False)

    result = await _check(stubs, transport)

    assert result is None
    assert transport.requests == []
    assert stubs.health == []
    assert stubs.bound_ctx.opened == 1


async def test_bot_sem_token_no_cofre_e_unknown_sem_http(
    db: Callable[..., Stubs], transport: Recorder
) -> None:
    stubs = db(token=False)

    result = await _check(stubs, transport)

    assert result is not None and result.status == "unknown"
    assert stubs.health == [("unknown", "token do bot ausente no cofre")]
    assert transport.requests == []
    assert "http" not in stubs.timeline


# ---------------------------------------------------------------------------
# Gate 2 — o vigia não conhece `set_webhook`
# ---------------------------------------------------------------------------
def test_o_fonte_do_vigia_nao_chama_set_webhook_nem_delete_webhook() -> None:
    """⛔ A regra da §7 no fonte: nenhuma das duas funções que mudam o registro
    da plataforma é sequer nomeada. O par positivo é o `canais.py`, que as chama."""
    source = Path(vigia.__file__).read_text(encoding="utf-8")
    assert "set_webhook" not in source
    assert "delete_webhook" not in source
    assert "webhook_info" in source
    from server.routers import canais

    canais_source = Path(canais.__file__).read_text(encoding="utf-8")
    assert "telegram.set_webhook(" in canais_source


async def test_run_percorre_todos_os_tenants_ativos_e_nenhum_setwebhook_em_nenhum(
    db: Callable[..., Stubs], transport: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Três tenants, três desfechos — e o transporte viu só `getWebhookInfo`.
    O relatório nomeia tenant, status e detail, como o do sender."""
    outro = UUID("22222222-2222-4222-8222-222222222223")
    terceiro = UUID("22222222-2222-4222-8222-222222222224")
    contexts = [SystemContext(tenant_id=t, task=vigia.TASK) for t in (TENANT_ID, outro, terceiro)]

    async def tenants(task: str) -> list[SystemContext]:
        assert task == vigia.TASK
        return contexts

    monkeypatch.setattr(vigia, "active_tenants", tenants)
    stubs = db()
    answers = iter(
        [
            {"url": WEBHOOK_URL, "pending_update_count": 0},
            {"url": "", "pending_update_count": 0},
            {"url": WEBHOOK_URL, "pending_update_count": 500},
        ]
    )
    transport.respond = lambda request: webhook_info_response(next(answers))(request)

    async with verification_client(transport=httpx.MockTransport(transport.handler)) as http:
        results = await vigia.run(http)

    assert [(r.tenant_id, r.status) for r in results] == [
        (TENANT_ID, "connected"),
        (outro, "disconnected"),
        (terceiro, "disconnected"),
    ]
    assert len(transport.requests) == 3
    _no_set_webhook(transport)
    assert len(stubs.health) == 3
    texto = vigia.relatorio(results)
    assert str(TENANT_ID) in texto and str(outro) in texto
    assert "webhook ausente" in texto and "connected" in texto
    assert vigia.relatorio([]) == "nenhum tenant com bot ativo"


# ---------------------------------------------------------------------------
# Gate 4 — o token fora do log
# ---------------------------------------------------------------------------
async def test_o_token_do_bot_nao_aparece_no_log_em_debug(
    db: Callable[..., Stubs], transport: Recorder, caplog: pytest.LogCaptureFixture
) -> None:
    """Positivo primeiro: com um `AsyncClient` cru a URL (o token) vai ao log
    do `httpx`. Com o `verification_client`, que é o que `main` constrói, não."""
    stubs = db()
    transport.refuse_echoing_the_token(BOT_TOKEN)
    context = SystemContext(tenant_id=TENANT_ID, task=vigia.TASK)

    _reset_http_loggers()
    with caplog.at_level(logging.DEBUG):
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport.handler)) as raw:
            await vigia.check_tenant(context, raw)
    assert BOT_TOKEN in caplog.text

    caplog.clear()
    stubs.health.clear()
    with caplog.at_level(logging.DEBUG):
        await _check(stubs, transport)
    assert BOT_TOKEN not in caplog.text
    assert stubs.health == [("unknown", "getWebhookInfo: unauthorized")]
    for statement, params in zip(stubs.bound.statements, stubs.bound.params, strict=True):
        assert BOT_TOKEN not in statement
        assert BOT_TOKEN not in _all_text(params)
    _reset_http_loggers()


def test_main_constroi_o_cliente_pelo_verification_client() -> None:
    source = Path(vigia.__file__).read_text(encoding="utf-8")
    assert "verification_client()" in source
    assert "httpx.AsyncClient(" not in source


# ---------------------------------------------------------------------------
# O SQL liga o tenant; a chave do cofre é a do formulário
# ---------------------------------------------------------------------------
def test_o_sql_do_vigia_liga_o_tenant_e_le_so_id_e_webhook_url() -> None:
    context = SystemContext(tenant_id=TENANT_ID, task="test")
    assert bind_tenant(vigia._BOT_SQL, {}, context)["tenant_id"] == TENANT_ID
    assert "i.tenant_id = %(tenant_id)s" in vigia._BOT_SQL
    assert "i.active" in vigia._BOT_SQL and "i.provider = %(provider)s" in vigia._BOT_SQL
    lowered = vigia._BOT_SQL.lower()
    assert lowered.count("config ->>") == 1 and "select *" not in lowered
    assert bind_tenant(saude.RECORD_HEALTH_SQL, {}, context)["tenant_id"] == TENANT_ID
    assert vigia.BOT_TOKEN_KEY == "bot_token"
    assert [s.name for s in telegram.FIELDS if s.secret] == [vigia.BOT_TOKEN_KEY]


def test_os_tres_status_sao_os_do_check_constraint(
    last_migration_with: Callable[[str], str],
) -> None:
    migration = last_migration_with("create table if not exists app.channel_health")
    for status in (saude.HEALTH_CONNECTED, saude.HEALTH_DISCONNECTED, saude.HEALTH_UNKNOWN):
        assert f"'{status}'" in migration
    assert {saude.HEALTH_CONNECTED, saude.HEALTH_DISCONNECTED, saude.HEALTH_UNKNOWN} == {
        "connected",
        "disconnected",
        "unknown",
    }
