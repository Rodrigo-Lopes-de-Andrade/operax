"""uazapi — unofficial, QR-based, self-hosted base URL. Verification and `enviar`.

⏳ ENDPOINTS AS PREMISE, NOT AS MEASUREMENT
Never called from this repository. The documented calls are:

    GET  {base_url}/instance/status
    POST {base_url}/send/text  {number, text}
         → {"id": "…", "messageid": "…", …}  (v2; older builds: {"key": {"id": "…"}})
    token: {token}

with a 200 whose `instance.status` is `connected`; anything else with a 200 is a
valid token whose phone is not paired (`not_connected`). `instance.owner` (the
paired number) or `instance.name` is the public identity when present.

The send response follows the same premise as `verify`: a flat JSON object
whose fields are lowercase. `messageid` (the WhatsApp id) is read first, then
`id` (uazapi's own), then `key.id` (the pre-v2 shape); none of the three is a
response this code does not recognise, and the delivery is `malformed`.

`base_url` is the customer's own host, so it is a field and not a constant, and
it is the one field that must be `https://` — the token travels in a header to
wherever this points. Its `pattern` admits no trailing slash, so the path below
is appended as is.
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

NAME = "uazapi"

FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        name="base_url",
        label_pt="Endereço do servidor",
        pattern=r"https://[A-Za-z0-9.\-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~\-]+)*",
        autocomplete="url",
        inputmode="url",
        secret=False,
        placeholder="https://sua-instancia.uazapi.com",
        hint_pt="isto não parece o endereço do servidor: tem de começar com https://",
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
)


async def verify(fields: Mapping[str, str], http: httpx.AsyncClient) -> str:
    """Ask the instance status at the customer's own host."""
    try:
        response = await http.get(
            f"{fields['base_url']}/instance/status", headers={"token": fields["token"]}
        )
    except httpx.HTTPError:
        raise InvalidCredentialError("unreachable") from None

    if response.status_code >= 500:
        raise InvalidCredentialError("unreachable") from None
    if response.status_code != 200:
        raise InvalidCredentialError("unauthorized") from None

    try:
        instance = response.json()["instance"]
        status = str(instance["status"])
    except (ValueError, KeyError, TypeError):
        raise InvalidCredentialError("malformed") from None
    if status != "connected":
        raise InvalidCredentialError("not_connected") from None

    who = instance.get("owner") or instance.get("name") or "instância"
    return f"{who} conectado"


# ---------------------------------------------------------------------------
# Delivery — `render(body, message)` locally, the same renderer as Telegram (SPEC-CANAIS §2)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class UazapiProvider:
    """The self-hosted QR-based channel as an outbound: `send/text` to a number.

    Same shape as `ZApiProvider`: no template on the provider's side, so the
    sentence is `render(message.body, message)` and nothing else, and `body`
    absent is refused before any HTTP. The token travels in a header to the
    customer's own host — `base_url` is the field whose `pattern` forces
    `https://`. No exception leaves this method and no response body reaches
    `Delivery.error`. `cost_cents` is `None`: uazapi charges per instance.
    """

    base_url: str
    token: str
    http: httpx.AsyncClient
    name: str = NAME

    async def enviar(self, message: Message) -> Delivery:
        if message.body is None:
            return Delivery(status="failed", error="no_body")
        payload = {
            "number": message.destination.removeprefix("+"),
            "text": render(message.body, message),
        }
        try:
            response = await self.http.post(
                f"{self.base_url}/send/text", json=payload, headers={"token": self.token}
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
            message_id = body.get("messageid") or body.get("id") or body.get("key", {}).get("id")
        except (ValueError, AttributeError):
            return Delivery(status="failed", error="malformed")
        if not isinstance(message_id, str) or not message_id:
            return Delivery(status="failed", error="malformed")
        return Delivery(status="sent", provider_message_id=message_id)
