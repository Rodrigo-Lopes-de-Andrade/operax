"""What each WhatsApp provider permits — the only place in the backend that knows.

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


class UnknownProviderError(LookupError):
    """A provider nobody declared here.

    Named so that a caller can catch this and nothing else. It is raised rather
    than defaulted because the two wrong answers are not symmetric: "this channel
    has no restriction" is how a number gets banned, and a channel the catalogue
    does not know is a channel nobody decided about yet.
    """


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


#: What to assume when the provider is not resolved. See the module docstring:
#: this is the assumption, not the recommendation.
CONSERVATIVE_DEFAULT = ProviderCapabilities(
    official=False,
    requires_templates=False,
    ban_risk=True,
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

#: ⛔ The one place in the backend that spells these names. Everything else asks.
#:
#: The two unofficial ones *are* the conservative assumption rather than a copy of
#: it: the fearful answer and the QR-based answer are the same answer, and writing
#: it twice is how they drift apart.
_CAPABILITIES: dict[str, ProviderCapabilities] = {
    "meta_cloud": ProviderCapabilities(official=True, requires_templates=True, ban_risk=False),
    "z_api": CONSERVATIVE_DEFAULT,
    "uazapi": CONSERVATIVE_DEFAULT,
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
