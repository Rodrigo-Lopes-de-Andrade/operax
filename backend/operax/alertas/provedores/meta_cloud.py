"""Meta Cloud API — the official provider. Verification and template listing; `enviar` is C5.

⏳ ENDPOINTS AS PREMISE, NOT AS MEASUREMENT
No request has been made against the Graph API from this repository, by rule:
the first real credential is the owner's stop (SPRINTS-CANAIS, C2). What is
written here is the documented shape of *"read the phone number object"*,
*"read the WABA object"* and *"list the WABA's message templates"*, and a wrong
shape fails to the safe side — the credential is refused and nothing is stored;
the sync is refused and no status changes.

    GET https://graph.facebook.com/v21.0/{phone_number_id}
        ?fields=verified_name,display_phone_number
    GET https://graph.facebook.com/v21.0/{waba_id}?fields=id
    GET https://graph.facebook.com/v21.0/{waba_id}/message_templates
        ?fields=name,status,language,category,rejected_reason&limit=100
    Authorization: Bearer {token}

The Graph API answers an invalid token with **400** (`OAuthException`, code
190), not 401 — so every 4xx here is *"the provider refused this"*, and only a
5xx or a transport failure is *"the provider could not be asked"*.

THE TOKEN NEVER LEAVES A REQUEST HEADER
It is read from the vault into a local, put into `Authorization`, and that is
the whole of its life here. No log line, no exception message, no return value
carries it: every refusal is `InvalidCredentialError(code)` raised `from None`,
and the only acceptable client is `verification_client()`, which mutes the
`httpx` request log at the point of construction.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from operax.alertas.provedores.base import FieldSpec, InvalidCredentialError

NAME = "meta_cloud"

_GRAPH = "https://graph.facebook.com/v21.0"
_GRAPH_HOST = httpx.URL(_GRAPH).host

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
        name="waba_id",
        label_pt="ID da conta do WhatsApp Business (WABA)",
        pattern=r"[0-9]{5,32}",
        autocomplete="off",
        inputmode="numeric",
        secret=False,
        placeholder="102030405060708",
        hint_pt="isto não parece um ID de WABA: a Meta usa só dígitos",
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


async def _get(http: httpx.AsyncClient, url: str, token: str, **params: str) -> httpx.Response:
    """One Graph API read, or the refusal that says the provider could not be asked."""
    try:
        response = await http.get(
            url, params=params or None, headers={"Authorization": f"Bearer {token}"}
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
    return response


async def verify(fields: Mapping[str, str], http: httpx.AsyncClient) -> str:
    """Read the phone number object with the token; its name is the identity.

    Then read the WABA object with the same token: the template sync lists
    `/{waba_id}/message_templates`, and a token that reaches the number but not
    the account would be stored today and refused at the first sync. Validating
    before writing (§5.2) covers the new field too. The identity stays the
    phone number's.
    """
    response = await _get(
        http,
        f"{_GRAPH}/{fields['phone_number_id']}",
        fields["token"],
        fields="verified_name,display_phone_number",
    )
    try:
        body = response.json()
        name = str(body["verified_name"])
        number = str(body["display_phone_number"])
    except (ValueError, KeyError, TypeError):
        raise InvalidCredentialError("malformed") from None

    await _get(http, f"{_GRAPH}/{fields['waba_id']}", fields["token"], fields="id")

    return f"{name} ({number})"


# ---------------------------------------------------------------------------
# The WABA's templates — read only; the customer approves them in the WABA (DECISAO-WHATSAPP §5)
# ---------------------------------------------------------------------------
#: Meta's template status → `app.message_template.meta_status`. Data, so that
#: the route never spells a Meta literal. ⛔ Only `APPROVED` opens delivery: a
#: status this map does not know is *not* an approval, and the route treats it
#: as `rejected` with the literal recorded — a new status nobody foresaw must not
#: turn a message on.
META_STATUS: Mapping[str, str] = {
    "APPROVED": "approved",
    "PENDING": "pending",
    "IN_APPEAL": "pending",
    "REJECTED": "rejected",
    "PAUSED": "paused",
    "LIMIT_EXCEEDED": "paused",
    "DISABLED": "rejected",
    "PENDING_DELETION": "rejected",
    "DELETED": "rejected",
}

#: How many pages of `message_templates` one sync may follow. A WABA has at
#: most a few hundred templates and a page carries 100; a `paging.next` that
#: never ends is a response this code does not understand, not a bigger WABA.
MAX_PAGES = 10

_TEMPLATE_FIELDS = "name,status,language,category,rejected_reason"


@dataclass(frozen=True, slots=True)
class MetaTemplate:
    """One template as the WABA reports it. `status` is Meta's literal, as it came."""

    name: str
    language: str
    status: str
    rejected_reason: str | None


def _parse(item: Any) -> MetaTemplate:
    reason = item.get("rejected_reason")
    return MetaTemplate(
        name=str(item["name"]),
        language=str(item["language"]),
        status=str(item["status"]),
        rejected_reason=None if reason in (None, "NONE") else str(reason),
    )


def _next_page(body: Mapping[str, Any]) -> str | None:
    """The `paging.next` URL, or `None` at the last page.

    Followed only when it stays on the Graph API host, and over https: the URL
    comes from the response body, and the next request carries the Bearer
    token — a body that pointed elsewhere would have us hand the token to
    whoever it named. Anything else is a response this code does not recognise.
    """
    paging = body.get("paging")
    if paging is None:
        return None
    nxt = paging.get("next")
    if nxt is None:
        return None
    url = httpx.URL(str(nxt))
    if url.scheme != "https" or url.host != _GRAPH_HOST:
        raise InvalidCredentialError("malformed") from None
    return str(url)


async def list_templates(
    fields: Mapping[str, str], token: str, http: httpx.AsyncClient
) -> list[MetaTemplate]:
    """Every template of the WABA, following `paging.next` up to `MAX_PAGES`.

    The refusals are the ones `verify` raises, with the same codes and the same
    `from None`; the body of an error response is never read.
    """
    templates: list[MetaTemplate] = []
    url: str | None = f"{_GRAPH}/{fields['waba_id']}/message_templates"
    params: dict[str, str] = {"fields": _TEMPLATE_FIELDS, "limit": "100"}
    pages = 0

    while url is not None:
        if pages >= MAX_PAGES:
            raise InvalidCredentialError("malformed") from None
        response = await _get(http, url, token, **params)
        pages += 1
        params = {}  # `paging.next` already carries them
        try:
            body = response.json()
            templates.extend(_parse(item) for item in body["data"])
            url = _next_page(body)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise InvalidCredentialError("malformed") from None

    return templates
