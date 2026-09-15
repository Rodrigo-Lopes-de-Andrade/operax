"""uazapi — unofficial, QR-based, self-hosted base URL. Verification only; `enviar` is C5.

⏳ ENDPOINT AS PREMISE, NOT AS MEASUREMENT
Never called from this repository. The documented status call is:

    GET {base_url}/instance/status
    token: {token}

with a 200 whose `instance.status` is `connected`; anything else with a 200 is a
valid token whose phone is not paired (`not_connected`). `instance.owner` (the
paired number) or `instance.name` is the public identity when present.

`base_url` is the customer's own host, so it is a field and not a constant, and
it is the one field that must be `https://` — the token travels in a header to
wherever this points. Its `pattern` admits no trailing slash, so the path below
is appended as is.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from operax.alertas.provedores.base import FieldSpec, InvalidCredentialError

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
