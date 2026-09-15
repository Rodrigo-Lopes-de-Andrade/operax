"""Meta Cloud API — the official provider. Verification only; `enviar` is C5.

⏳ ENDPOINT AS PREMISE, NOT AS MEASUREMENT
No request has been made against the Graph API from this repository, by rule:
the first real credential is the owner's stop (SPRINTS-CANAIS, C2). What is
written here is the documented shape of *"read the phone number object"*, and a
wrong shape fails to the safe side — the credential is refused and nothing is
stored.

    GET https://graph.facebook.com/v21.0/{phone_number_id}
        ?fields=verified_name,display_phone_number
    Authorization: Bearer {token}

The Graph API answers an invalid token with **400** (`OAuthException`, code
190), not 401 — so every 4xx here is *"the provider refused this"*, and only a
5xx or a transport failure is *"the provider could not be asked"*.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from operax.alertas.provedores.base import FieldSpec, InvalidCredentialError

NAME = "meta_cloud"

_GRAPH = "https://graph.facebook.com/v21.0"

FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        name="phone_number_id",
        label_pt="ID do número de telefone",
        pattern=r"[0-9]{5,32}",
        autocomplete="off",
        inputmode="numeric",
        secret=False,
        placeholder="123456789012345",
        hint_pt="isto não parece um ID de número: a Meta usa só dígitos",
    ),
    FieldSpec(
        name="token",
        label_pt="Token de acesso permanente",
        pattern=r"[A-Za-z0-9._\-]+",
        autocomplete="one-time-code",
        inputmode="text",
        secret=True,
        placeholder="EAAG…",
        hint_pt="isto não parece um token da Meta: só letras, dígitos, ponto, hífen e sublinhado",
    ),
)


async def verify(fields: Mapping[str, str], http: httpx.AsyncClient) -> str:
    """Read the phone number object with the token; its name is the identity."""
    try:
        response = await http.get(
            f"{_GRAPH}/{fields['phone_number_id']}",
            params={"fields": "verified_name,display_phone_number"},
            headers={"Authorization": f"Bearer {fields['token']}"},
        )
    except httpx.HTTPError:
        # `from None`: the httpx exception names the URL, and the chain would
        # carry it into `exc_info` and Sentry.
        raise InvalidCredentialError("unreachable") from None

    if response.status_code >= 500:
        raise InvalidCredentialError("unreachable") from None
    if response.status_code != 200:
        # The body is discarded here on purpose (SPEC-CANAIS §5.3): a provider
        # that echoes the token in its error must not have it echoed by us.
        raise InvalidCredentialError("unauthorized") from None

    try:
        body = response.json()
        name = str(body["verified_name"])
        number = str(body["display_phone_number"])
    except (ValueError, KeyError, TypeError):
        raise InvalidCredentialError("malformed") from None

    return f"{name} ({number})"
