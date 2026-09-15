"""The provider contract — `(template, variables, destination)` and nothing else.

Rule 11 of the project, and it is a one-way door. The official Meta Cloud API
accepts an approved template name plus ordered parameters; it does not accept a
sentence. Z-API and uazapi accept free text and have no concept of a template. An
interface shaped around free text can serve the two unofficial ones and can
**never** serve the official one — so the contract is template-first, and turning
a template into text is the provider's problem, not the caller's.

That is why `Message` carries a dict of facts. The renderer below exists for the
unofficial providers, which need the sentence built locally; `meta_cloud` never
calls it, because the sentence lives in the WABA.

`NullProvider` is not a test double. It is what the sender uses while the shadow
gate is open (rule 8): it records what would have gone out and delivers nothing.
A product that can send before its false-positive rate is known is a product that
will send a wrong accusation to a manager, once, and never be trusted again.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol

import httpx

#: `{{1}}`, `{{2}}` — a ordem declarada em `app.message_template.variables`.
_PLACEHOLDER = re.compile(r"\{\{(\d+)\}\}")


@dataclass(frozen=True, slots=True)
class Message:
    """O que se entrega a um provedor. Nunca uma frase pronta."""

    destination: str
    #: `None` para e-mail e resumo livre; obrigatório no provedor oficial.
    template: str | None
    #: A ordem declarada no template, que é o que vira `{{1}}`, `{{2}}`...
    variables: tuple[str, ...]
    #: Os fatos, por nome. O provedor escolhe o que fazer com eles.
    facts: dict[str, str]

    def ordered(self) -> list[str]:
        """Os valores na ordem em que o template os declarou."""
        return [self.facts.get(nome, "") for nome in self.variables]


@dataclass(frozen=True, slots=True)
class Delivery:
    """O que o provedor respondeu. `cost_cents` desde o primeiro envio."""

    status: Literal["sent", "failed"]
    provider_message_id: str | None = None
    error: str | None = None
    cost_cents: int | None = None


class Provider(Protocol):
    """Um canal de saída. O motor conhece esta forma e mais nada."""

    name: str

    async def enviar(self, message: Message) -> Delivery: ...


def render(body: str, message: Message) -> str:
    """`{{n}}` trocado pelo n-ésimo valor declarado — para quem não tem template.

    Placeholder sem valor vira string vazia em vez de ficar literal na mensagem:
    o banco já recusa um corpo que use `{{4}}` declarando três variáveis
    (`util.validate_template_body`), então chegar aqui com um vão é sinal de
    template alterado por fora — e "texto faltando" é menos ruim do que "{{4}}"
    na tela de um gestor.
    """
    valores = message.ordered()

    def trocar(achado: re.Match[str]) -> str:
        indice = int(achado.group(1))
        return valores[indice - 1] if 1 <= indice <= len(valores) else ""

    return _PLACEHOLDER.sub(trocar, body)


@dataclass
class NullProvider:
    """Registra e não entrega. É o que roda enquanto o gate G4 está aberto."""

    name: str = "null"
    sent: list[Message] = field(default_factory=list)

    async def enviar(self, message: Message) -> Delivery:
        self.sent.append(message)
        return Delivery(status="failed", error="gate G4 aberto: nada é entregue em sombra")


# ---------------------------------------------------------------------------
# Credential verification — the other half of the contract (SPEC-CANAIS §5)
# ---------------------------------------------------------------------------
# A provider module declares its form as data (`FIELDS`) and proves a credential
# with `verify` before anything is written. The form is data so that §5.4 lives
# in one place: the pattern that refuses an e-mail in a numeric field and the
# `autocomplete` that stops the browser from offering it are read by the API,
# rendered by the screen and enforced by the route from the same tuple.
#
# `verify(fields, http) -> str` answers one thing: the human-readable identity
# the credential resolves to (*"conectado como …"*). Where each field is stored
# is not the provider's call — `FieldSpec.secret` is, and the route reads it.


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One field of a provider's credential form.

    `secret` decides where the value goes, and it is the route that reads it:
    `True` → Supabase Vault, behind a pointer in `app.integration_secret`;
    `False` → `app.integration.config`, which the panel can read. Every field the
    operator sent lands in exactly one of the two — `verify` never chooses, it
    only answers who the credential belongs to. Flipping the flag *moves* the
    field between the two places; it cannot drop it, and `tests/test_canais_credencial.py`
    asserts that partition per provider.

    `autocomplete` for a secret is `one-time-code` rather than `new-password`:
    both keep the browser from pasting an e-mail into the field, but
    `new-password` also invites it to *save* the value — a copy of the token in
    the browser's password store, outside the vault. `one-time-code` never offers
    to save. Non-secret identifiers use `off` plus a strict `pattern` and an
    `inputmode`, which is what actually stops the autofill seen in the
    DeskcommCRM captures (§5.4): an e-mail does not match `[0-9]+`.
    """

    name: str
    label_pt: str
    #: Anchored by `fullmatch`. Besides catching the wrong value early, it keeps
    #: the value URL- and header-safe: a token goes into a path or a header, and
    #: `[A-Za-z0-9._\-]+` cannot carry a `/`, a `?` or a line break there.
    pattern: str
    autocomplete: str
    inputmode: str
    secret: bool
    placeholder: str
    #: The §5.4 sentence — *"isto não parece um ID de número"* — shown when the
    #: value fails `pattern`. Never the value.
    hint_pt: str


class InvalidCredentialError(Exception):
    """The provider did not accept the credential, or could not be asked.

    Carries a short, stable `code` and nothing else — never the response body,
    never the URL, never a value. Providers raise it `from None` on purpose: the
    exception it replaces (`httpx.HTTPStatusError` and friends) spells the full
    URL in its message, and `exc_info=True`, Sentry and `traceback.format_exception`
    all walk `__cause__`/`__context__`.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


#: How long a verification may take. It is one request, and the operator is
#: waiting behind a button.
VERIFY_TIMEOUT_SECONDS = 10

#: The loggers httpx writes to. `httpx` logs every request at INFO with the
#: **full URL** — `HTTP Request: GET https://… "HTTP/1.1 401 Unauthorized"` —
#: and at least one provider carries the token in the URL path. `httpcore` logs
#: at DEBUG. Neither line may exist for a verification call.
_HTTP_LOGGERS = ("httpx", "httpcore")


def verification_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    """The one place a provider's HTTP client is built — and where its log is muted.

    ⛔ The `setLevel` below is the defence of gate 3 (SPEC-CANAIS §5.3) for the
    log: without it, `httpx` writes the request URL at INFO, and for a provider
    that puts the token in the path that line *is* the token. Raising the level
    at the point of construction, instead of in logging config, means the
    defence travels with the client — a test that injects a `MockTransport`
    through this function exercises it, and a deployment that never configured
    logging still has it.

    `transport` exists for tests only: `httpx.MockTransport`, never a real host.
    """
    for name in _HTTP_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    return httpx.AsyncClient(timeout=VERIFY_TIMEOUT_SECONDS, transport=transport)


class FieldError(ValueError):
    """A submitted value that does not match the field's `pattern`, or a field
    missing or unexpected. Names the field; never carries the value."""

    def __init__(self, spec: FieldSpec | None, name: str) -> None:
        super().__init__(name)
        self.spec = spec
        self.name = name


def check_fields(specs: tuple[FieldSpec, ...], values: Mapping[str, str]) -> dict[str, str]:
    """Every declared field present and matching its `pattern`, and nothing else.

    Runs **before** any HTTP: the wrong shape is refused here with the §5.4
    sentence instead of with a provider error. Whitespace around a value is
    stripped, because a pasted token comes with it more often than not.
    """
    declared = {spec.name: spec for spec in specs}
    for name in values:
        if name not in declared:
            raise FieldError(None, name)
    checked: dict[str, str] = {}
    for spec in specs:
        value = values.get(spec.name, "").strip()
        if not re.fullmatch(spec.pattern, value):
            raise FieldError(spec, spec.name)
        checked[spec.name] = value
    return checked
