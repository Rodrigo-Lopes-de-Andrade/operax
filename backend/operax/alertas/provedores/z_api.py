"""Z-API — unofficial, QR-based. Verification and `enviar`.

⏳ ENDPOINTS AS PREMISE, NOT AS MEASUREMENT
Never called from this repository. The documented calls are:

    GET  https://api.z-api.io/instances/{instance_id}/token/{token}/status
    POST https://api.z-api.io/instances/{instance_id}/token/{token}/send-text
         {phone, message} → {"zaapId": "…", "messageId": "…", "id": "…"}
    Client-Token: {client_token}

and a 200 with `connected: true` is a live session; `connected: false` is a
valid credential whose phone is not paired (`not_connected`). `send-text`
answers with the WhatsApp id in `messageId` and its own in `zaapId`; the first
is preferred and the second is the fallback.

⛔ THE TOKEN IS IN THE URL PATH — THIS IS THE REAL CASE OF GATE 3
`httpx` logs every request at INFO as `HTTP Request: GET <url> "HTTP/1.1 401
…"`, and `httpx.HTTPStatusError` spells the URL in its message. For this
provider both would be the token. Two defences, both tested by mutation in
`tests/test_canais_credencial.py`: the client comes from
`verification_client()`, which mutes the `httpx` logger, and every failure is
raised `from None` so the chain never reaches a log or Sentry. `pattern` is the
third: the token class (letters, digits, `.`, `_`, `-`) cannot smuggle a `/`
or `?` into the path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from operax.alertas.provedores.base import (
    Delivery,
    FieldSpec,
    InvalidCredentialError,
    Message,
    render,
)

NAME = "z_api"

_BASE = "https://api.z-api.io/instances"

FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        name="instance_id",
        label_pt="ID da instância",
        pattern=r"[A-Za-z0-9]{8,64}",
        autocomplete="off",
        inputmode="text",
        secret=False,
        placeholder="3C4E5F…",
        hint_pt="isto não parece um ID de instância da Z-API: só letras e dígitos",
    ),
    FieldSpec(
        name="token",
        label_pt="Token da instância",
        pattern=r"[A-Za-z0-9._\-]+",
        autocomplete="one-time-code",
        inputmode="text",
        secret=True,
        placeholder="token da instância",
        hint_pt="isto não parece um token: só letras, dígitos, ponto, hífen e sublinhado",
    ),
    FieldSpec(
        name="client_token",
        label_pt="Client-Token da conta",
        pattern=r"[A-Za-z0-9._\-]+",
        autocomplete="one-time-code",
        inputmode="text",
        secret=True,
        placeholder="Client-Token de segurança",
        hint_pt="isto não parece um Client-Token: só letras, dígitos, ponto, hífen e sublinhado",
    ),
)


async def verify(fields: Mapping[str, str], http: httpx.AsyncClient) -> str:
    """Ask the instance status; connected is the only acceptable answer."""
    try:
        response = await http.get(
            f"{_BASE}/{fields['instance_id']}/token/{fields['token']}/status",
            headers={"Client-Token": fields["client_token"]},
        )
    except httpx.HTTPError:
        raise InvalidCredentialError("unreachable") from None

    if response.status_code >= 500:
        raise InvalidCredentialError("unreachable") from None
    if response.status_code != 200:
        raise InvalidCredentialError("unauthorized") from None

    try:
        connected = bool(response.json()["connected"])
    except (ValueError, KeyError, TypeError):
        raise InvalidCredentialError("malformed") from None
    if not connected:
        raise InvalidCredentialError("not_connected") from None

    return f"instância {fields['instance_id']} conectada"


# ---------------------------------------------------------------------------
# Delivery — `render(body, message)` locally, the same renderer as Telegram (SPEC-CANAIS §2)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ZApiProvider:
    """The QR-based channel as an outbound: `send-text` to a phone number.

    Z-API has no concept of a template, so the sentence is built here — and
    only here, by `render(message.body, message)` over
    `app.message_template.body`, which is what keeps this copy of an alert
    identical to the Telegram one and to what the WABA renders for
    `meta_cloud` (§2, item 3). `body` absent is refused before any HTTP: this
    provider does not invent a phrase either.

    ⛔ The token is in the URL path, so `http` must come from
    `verification_client()` — where the `httpx` request log is muted — and no
    exception leaves this method: the httpx message names the URL, and the URL
    is the token. A refusal is a code; the response body is never read past
    the id. `cost_cents` is `None`: Z-API charges per instance, not per message.
    """

    instance_id: str
    token: str
    client_token: str
    http: httpx.AsyncClient
    name: str = NAME

    async def enviar(self, message: Message) -> Delivery:
        if message.body is None:
            return Delivery(status="failed", error="no_body")
        payload = {
            "phone": message.destination.removeprefix("+"),
            "message": render(message.body, message),
        }
        try:
            response = await self.http.post(
                f"{_BASE}/{self.instance_id}/token/{self.token}/send-text",
                json=payload,
                headers={"Client-Token": self.client_token},
            )
        except httpx.HTTPError:
            return Delivery(status="failed", error="unreachable")

        if response.status_code >= 500 or response.status_code == 429:
            return Delivery(status="failed", error="unreachable")
        if response.status_code in (401, 403):
            return Delivery(status="failed", error="unauthorized")
        if response.status_code != 200:
            return Delivery(status="failed", error=f"http_{response.status_code}")
        try:
            body = response.json()
            message_id = body.get("messageId") or body.get("zaapId")
        except (ValueError, AttributeError):
            return Delivery(status="failed", error="malformed")
        if not isinstance(message_id, str) or not message_id:
            return Delivery(status="failed", error="malformed")
        return Delivery(status="sent", provider_message_id=message_id)
