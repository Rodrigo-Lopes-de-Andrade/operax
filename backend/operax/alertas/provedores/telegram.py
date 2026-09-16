"""Telegram Bot API — the fourth provider, official, third family. Verification,
webhook registration, and `TelegramProvider.enviar`; the webhook endpoint that
receives `/start` is `server/routers/webhooks.py`.

⏳ ENDPOINTS AS PREMISE, NOT AS MEASUREMENT
Never called from this repository. The documented Bot API surface used here:

    GET  https://api.telegram.org/bot{token}/getMe
    POST https://api.telegram.org/bot{token}/setWebhook
         {url, secret_token, allowed_updates, drop_pending_updates}
    POST https://api.telegram.org/bot{token}/deleteWebhook {drop_pending_updates}
    GET  https://api.telegram.org/bot{token}/getWebhookInfo
    POST https://api.telegram.org/bot{token}/sendMessage {chat_id, text}
         → 403 "Forbidden: bot was blocked by the user" when the person blocked it

Every answer is `{"ok": bool, "result": …}`; an invalid token is a 401 with
`ok: false`. Three refusals, the same three as the WhatsApp providers: `ok`
false or any 4xx → `unauthorized`; transport failure or 5xx → `unreachable`;
a body this code does not recognise → `malformed`. `not_connected` does not
exist here — a bot has no phone to pair.

⛔ THE TOKEN IS IN THE URL PATH — THE `z_api` CASE AGAIN (GATE 3)
`httpx` logs every request at INFO as `HTTP Request: GET <url> "HTTP/1.1 401
…"`, and `httpx.HTTPStatusError` spells the URL in its message. For this
provider both would be the token. The two defences are the ones
`tests/test_canais_telegram.py` mutates: the client comes from
`verification_client()`, which mutes the `httpx` logger, and every failure is
raised `from None` so the chain never reaches a log or Sentry. `pattern` is the
third: the token class (digits, `:`, letters, `_`, `-`) cannot carry a `/` or a
`?` into the path.

⛔ `last_error_message` IS HOSTILE DATA
`getWebhookInfo` echoes what the platform saw, and that can be the webhook URL
— which carries the `path_token`. It is capped and the path token masked before
it leaves this module (`_mask`). Nothing else from a body is returned verbatim.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from operax.alertas.provedores.base import (
    Delivery,
    FieldSpec,
    InvalidCredentialError,
    Message,
    render,
)

NAME = "telegram"

_BASE = "https://api.telegram.org"

#: The path the API serves the webhook on (wave 2b) and the one `setWebhook`
#: registers. One constant, so the route that builds the URL and the route that
#: answers it cannot disagree — and so `_mask` knows what to hide.
WEBHOOK_PATH = "/webhooks/telegram"

#: Cap on `last_error_message` after masking. It is a sentence for a screen.
_ERROR_MESSAGE_MAX_CHARS = 200

_PATH_TOKEN = re.compile(re.escape(WEBHOOK_PATH) + r"/[^\s/?#]+")

FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        name="bot_token",
        label_pt="Token do bot (BotFather)",
        # `\-` escaped for the browser's `v`-flag dialect (test_canais_credencial).
        pattern=r"[0-9]{6,12}:[A-Za-z0-9_\-]{30,64}",
        autocomplete="one-time-code",
        inputmode="text",
        secret=True,
        placeholder="123456789:AAH…",
        hint_pt="isto não parece um token de bot: dígitos, dois-pontos e o segredo do BotFather",
    ),
)


@dataclass(frozen=True, slots=True)
class WebhookInfo:
    """What the platform says about the registered webhook. Never the token."""

    url: str | None
    pending_update_count: int
    last_error_date: datetime | None
    last_error_message: str | None


def _mask(message: str) -> str:
    """Hide the path token of any webhook URL echoed back, then cap the length.

    Mask first: truncating first could leave a partial token in the tail, and a
    partial token is still a token."""
    return _PATH_TOKEN.sub(f"{WEBHOOK_PATH}/…", message)[:_ERROR_MESSAGE_MAX_CHARS]


async def _call(
    http: httpx.AsyncClient, token: str, method: str, payload: Mapping[str, Any] | None = None
) -> Any:
    """One Bot API call; returns `result`, or the refusal that says why not.

    The body of a refusal is never read past `ok`: a platform that echoed the
    token in `description` must not have it echoed by us (SPEC-CANAIS §5.3).
    """
    url = f"{_BASE}/bot{token}/{method}"
    try:
        if payload is None:
            response = await http.get(url)
        else:
            response = await http.post(url, json=payload)
    except httpx.HTTPError:
        # `from None`: the httpx exception names the URL, and the URL is the token.
        raise InvalidCredentialError("unreachable") from None

    if response.status_code >= 500 or response.status_code == 429:
        # 429 is a transient limit, not a verdict on the token: "recusou a
        # credencial" would send the admin to check a token that is fine.
        raise InvalidCredentialError("unreachable") from None
    if response.status_code != 200:
        raise InvalidCredentialError("unauthorized") from None

    try:
        body = response.json()
        ok = bool(body["ok"])
    except (ValueError, KeyError, TypeError):
        raise InvalidCredentialError("malformed") from None
    if not ok:
        raise InvalidCredentialError("unauthorized") from None
    try:
        return body["result"]
    except (KeyError, TypeError):
        raise InvalidCredentialError("malformed") from None


async def verify(fields: Mapping[str, str], http: httpx.AsyncClient) -> str:
    """`getMe` with the token; the bot's `@username` is the identity the screen
    shows (*"conectado como @FastParkAlertasBot"*, SPEC-CANAIS §5.2)."""
    result = await _call(http, fields["bot_token"], "getMe")
    try:
        username = str(result["username"])
    except (KeyError, TypeError):
        raise InvalidCredentialError("malformed") from None
    return f"@{username}"


async def set_webhook(token: str, url: str, secret: str, http: httpx.AsyncClient) -> None:
    """Register `url` as the bot's webhook, with `secret` as the header the
    platform will send back (`X-Telegram-Bot-Api-Secret-Token`, SPEC §6).

    `allowed_updates=["message"]`: the bot handles `/start` and nothing else,
    so nothing else is delivered. `drop_pending_updates`: whatever queued while
    the webhook was down was addressed to a path that no longer exists.
    """
    await _call(
        http,
        token,
        "setWebhook",
        {
            "url": url,
            "secret_token": secret,
            "allowed_updates": ["message"],
            "drop_pending_updates": True,
        },
    )


async def delete_webhook(token: str, http: httpx.AsyncClient) -> None:
    """Unregister the webhook and drop what was queued for it."""
    await _call(http, token, "deleteWebhook", {"drop_pending_updates": True})


async def webhook_info(token: str, http: httpx.AsyncClient) -> WebhookInfo:
    """What the platform has registered, for the watcher (wave 2b).

    An empty `url` is *no webhook* and comes back as `None`. `last_error_message`
    is masked and capped — it can echo the URL, and the URL carries the token.
    """
    result = await _call(http, token, "getWebhookInfo")
    try:
        url = str(result.get("url") or "") or None
        pending = int(result.get("pending_update_count", 0))
        error_date = result.get("last_error_date")
        error_message = result.get("last_error_message")
        last_error_date = (
            datetime.fromtimestamp(int(error_date), tz=UTC) if error_date is not None else None
        )
    except (AttributeError, TypeError, ValueError, OverflowError, OSError):
        raise InvalidCredentialError("malformed") from None
    return WebhookInfo(
        url=url,
        pending_update_count=pending,
        last_error_date=last_error_date,
        last_error_message=_mask(str(error_message)) if error_message is not None else None,
    )


# ---------------------------------------------------------------------------
# Delivery — under the template contract (SPEC-CANAIS §2)
# ---------------------------------------------------------------------------
#: What the Bot API answers when the person blocked the bot. The status code is
#: the signal; the description is not read.
_BLOCKED_STATUS = 403


@dataclass(frozen=True, slots=True)
class TelegramProvider:
    """The bot as an outbound channel: `sendMessage` to a `chat_id`.

    The text is `render(message.body, message)` — the same renderer the
    unofficial WhatsApp providers use over the same `app.message_template.body`,
    which is what makes the two copies of one alert identical by construction
    (§2, item 3). No `parse_mode`: text only, until a template declares
    formatting. `body` absent is refused before any HTTP — this provider has no
    other source of a sentence, on purpose.

    `http` must come from `verification_client()`: the token is in the URL path
    (gate 3), and that client is where the `httpx` log is muted. The sender that
    wires this in (C5) owns the token's journey from the vault to here.

    A `403` is `Delivery("failed", error="blocked")`: the person blocked the
    bot, and the identity is no longer a place alerts reach. Revoking it is the
    caller's decision (C4), not this method's — a provider that writes to the
    database is a provider that can be pointed at one.
    """

    token: str
    http: httpx.AsyncClient
    name: str = NAME

    async def enviar(self, message: Message) -> Delivery:
        if message.body is None:
            return Delivery(status="failed", error="no_body")
        payload = {"chat_id": message.destination, "text": render(message.body, message)}
        try:
            response = await self.http.post(f"{_BASE}/bot{self.token}/sendMessage", json=payload)
        except httpx.HTTPError:
            # No exception leaves here: the httpx message names the URL, and
            # the URL is the token.
            return Delivery(status="failed", error="unreachable")

        if response.status_code == _BLOCKED_STATUS:
            return Delivery(status="failed", error="blocked")
        if response.status_code >= 500 or response.status_code == 429:
            return Delivery(status="failed", error="unreachable")
        if response.status_code != 200:
            # The code and nothing else: `description` is the platform's body.
            return Delivery(status="failed", error=f"http_{response.status_code}")
        try:
            body = response.json()
            if not body["ok"]:
                return Delivery(status="failed", error="malformed")
            message_id = str(int(body["result"]["message_id"]))
        except (ValueError, KeyError, TypeError):
            return Delivery(status="failed", error="malformed")
        return Delivery(status="sent", provider_message_id=message_id)
