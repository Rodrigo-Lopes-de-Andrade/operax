"""Z-API — unofficial, QR-based. Verification only; `enviar` is C5.

⏳ ENDPOINT AS PREMISE, NOT AS MEASUREMENT
Never called from this repository. The documented status call is:

    GET https://api.z-api.io/instances/{instance_id}/token/{token}/status
    Client-Token: {client_token}

and a 200 with `connected: true` is a live session; `connected: false` is a
valid credential whose phone is not paired (`not_connected`).

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

import httpx

from operax.alertas.provedores.base import FieldSpec, InvalidCredentialError

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
