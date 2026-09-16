"""What each channel provider permits — the only place in the backend that knows.

No feature asks *who* we are talking to. It asks *what the channel allows*, and
that answer is data here instead of an `if` somewhere else. Today the difference
between `meta_cloud` and the two unofficial providers is spread across
`util.validate_alert_template` in the database, the comment on
`app.integration.provider`, and whoever read `docs/DECISAO-WHATSAPP.md`. A fourth
channel is on the way; spreading it further is how the contract gets lost.

TWO FAMILIES OF RESTRICTION, AND THEY NEVER COEXIST
* **self-restriction** (`ban_risk`) — *"I speak whenever I want, and WhatsApp
  bans me if I abuse it"*: `z_api` and `uazapi`, which connect over QR as a
  WhatsApp Web client. The ban is of the customer's own number, permanent, and
  has no appeal (`docs/DECISAO-WHATSAPP.md` §1).
* **other-restriction** (`requires_templates`) — *"nobody bans me, but Meta
  forbids me and charges me"*: `meta_cloud`, whose business-initiated message
  outside the 24h window must be a template approved in advance.

A provider carrying both would be a channel that can be banned for saying exactly
what it was authorised to say. That is a modelling mistake, not a new kind of
channel, and `tests/test_capacidades.py` asserts it over the whole matrix rather
than provider by provider — the first candidate to challenge it has *neither*,
and *neither* is not *both*.

THE THIRD FAMILY: RESTRICTION OF RECIPIENT (`requires_recipient_opt_in`)
`telegram` has neither of the two above — no 24h window, no approved template,
no ban for volume, no cost per message — and the naive reading of that is "the
channel without rules", which is false (`docs/SPEC-CANAIS.md` §1.1). Its
restriction is on another axis: it does not send to a phone number, it sends to
a `chat_id` that only exists after the person opened the bot. WhatsApp restricts
WHAT you say and WHEN; Telegram restricts TO WHOM. The consent lives in
`app.messaging_identity`, and a recipient without a current identity is not
reachable on that channel at all — the sender falls back to WhatsApp (SPEC §8).

FAIL-CLOSED, AND THE ASSUMED ANSWER IS THE FEARFUL ONE
`capabilities_for` raises on a provider it does not know instead of answering
something plausible. Where an answer has to be assumed before the provider is
resolved, `CONSERVATIVE_DEFAULT` is what gets assumed: erring towards
`meta_cloud` would disarm the anti-ban guard on a number that can be banned, and
that mistake does not come back. A refused template does.

⚠️ `CONSERVATIVE_DEFAULT` IS NOT "THE DEFAULT PROVIDER", AND THE TWO POINT THE
OPPOSITE WAY
Migration 14 and `docs/DECISAO-WHATSAPP.md` §1 say `meta_cloud` is the default
*choice* — the provider a customer should be put on, because the other two risk
the number. This constant is the default *assumption* — what to believe about a
channel whose identity is not resolved, where believing "official" is what costs.
Collapsing the two is how the anti-ban guard gets switched off by a rename.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


class UnknownProviderError(LookupError):
    """A provider nobody declared here.

    Named so that a caller can catch this and nothing else. It is raised rather
    than defaulted because the two wrong answers are not symmetric: "this channel
    has no restriction" is how a number gets banned, and a channel the catalogue
    does not know is a channel nobody decided about yet.
    """


class UnknownChannelError(LookupError):
    """A channel nobody declared here. Same reasoning as `UnknownProviderError`."""


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """What a channel permits. Data — never behaviour, never a subclass."""

    #: Meta's own API. Costs per conversation, and the business is verified.
    official: bool
    #: Hetero-restriction: the message must name a template approved in advance,
    #: and `util.validate_alert_template` refuses the queue row otherwise.
    requires_templates: bool
    #: Self-restriction: the customer's own number can be banned, permanently and
    #: without appeal, for how much and how it speaks.
    ban_risk: bool
    #: Restriction of recipient: the channel cannot address a phone number; the
    #: person must have opened the bot first, and the resulting identity
    #: (`app.messaging_identity`) is revocable. No current identity, no delivery.
    requires_recipient_opt_in: bool


#: What to assume when the provider is not resolved. See the module docstring:
#: this is the assumption, not the recommendation.
CONSERVATIVE_DEFAULT = ProviderCapabilities(
    official=False,
    requires_templates=False,
    ban_risk=True,
    requires_recipient_opt_in=False,
)

#: The providers that carry WhatsApp, and the same three the partial unique index
#: `integration_whatsapp_unico_ativo` (migration 14) names — one active per
#: tenant.
#:
#: Written out instead of derived from the matrix below on purpose. The matrix is
#: "every channel we know"; this tuple is "the channels that are WhatsApp", and a
#: fourth channel joining the first does not join the second. Deriving it would
#: make a new row silently widen the query that answers *"which WhatsApp provider
#: is this tenant on?"*.
WHATSAPP_PROVIDERS: tuple[str, ...] = ("meta_cloud", "z_api", "uazapi")

#: Every provider that carries a channel — the WhatsApp three and Telegram. This
#: is the list `public.fn_channel_readiness` (migration `ch_readiness_fn`) walks,
#: one row per active integration; `WHATSAPP_PROVIDERS` is deliberately NOT
#: widened to it (see above). `telegram` has its own exclusivity index,
#: `integration_telegram_unico_ativo`, sibling of the WhatsApp one.
CHANNEL_PROVIDERS: tuple[str, ...] = (*WHATSAPP_PROVIDERS, "telegram")

#: The channel a provider carries — the axis the two sibling exclusivity
#: indexes are drawn on. `whatsapp` is three providers behind one index;
#: `telegram` is one provider behind the other. A route that switches a
#: tenant's provider switches it WITHIN its channel: disabling "every active
#: channel provider" when a bot token is saved would be the bug of SPEC-CANAIS
#: §2.1 — *"liguei o Telegram e o WhatsApp desligou"* — through the credential
#: door instead of the index. `channel_of` and `providers_of` are that axis as
#: data, so nobody else needs to know which name is which.
Channel = Literal["whatsapp", "telegram"]

WHATSAPP_CHANNEL: Channel = "whatsapp"
TELEGRAM_CHANNEL: Channel = "telegram"
CHANNELS: tuple[Channel, ...] = (WHATSAPP_CHANNEL, TELEGRAM_CHANNEL)

_PROVIDERS_OF: dict[Channel, tuple[str, ...]] = {
    WHATSAPP_CHANNEL: WHATSAPP_PROVIDERS,
    TELEGRAM_CHANNEL: ("telegram",),
}

#: ⛔ The one place in the backend that spells these names. Everything else asks.
#:
#: The two unofficial ones *are* the conservative assumption rather than a copy of
#: it: the fearful answer and the QR-based answer are the same answer, and writing
#: it twice is how they drift apart.
_CAPABILITIES: dict[str, ProviderCapabilities] = {
    "meta_cloud": ProviderCapabilities(
        official=True,
        requires_templates=True,
        ban_risk=False,
        requires_recipient_opt_in=False,
    ),
    "z_api": CONSERVATIVE_DEFAULT,
    "uazapi": CONSERVATIVE_DEFAULT,
    # The third family: neither template nor ban, and the recipient must have
    # opened the bot. Official — it is the platform's own Bot API.
    "telegram": ProviderCapabilities(
        official=True,
        requires_templates=False,
        ban_risk=False,
        requires_recipient_opt_in=True,
    ),
}


def capabilities_for(provider: str) -> ProviderCapabilities:
    """What this provider permits, or a refusal to guess."""
    try:
        return _CAPABILITIES[provider]
    except KeyError:
        raise UnknownProviderError(
            f"provider {provider!r} is not in the capability matrix; "
            f"the declared ones are {', '.join(sorted(_CAPABILITIES))}"
        ) from None


def channel_of(provider: str) -> Channel:
    """The channel this provider carries, or a refusal to guess."""
    for channel, providers in _PROVIDERS_OF.items():
        if provider in providers:
            return channel
    raise UnknownProviderError(
        f"provider {provider!r} carries no declared channel; "
        f"the declared ones are {', '.join(sorted(CHANNEL_PROVIDERS))}"
    )


def providers_of(channel: str) -> tuple[str, ...]:
    """The providers that carry `channel` — the predicate of its exclusivity index."""
    try:
        return _PROVIDERS_OF[channel]
    except KeyError:
        raise UnknownChannelError(
            f"channel {channel!r} is not declared; the declared ones are {', '.join(CHANNELS)}"
        ) from None
