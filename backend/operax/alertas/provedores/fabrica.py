"""From a stored credential to a `Provider` — the one place the four are constructed.

The sender reads `app.integration.config` (the non-secret fields) and the
vault (the secret ones) and hands both here with the provider's name. Which
field lives where is not this module's call: it is `FieldSpec.secret`, the
same flag the credential route used to split the form on the way in
(`base.FieldSpec`). Reading the partition from `FIELDS` instead of restating
it means flipping the flag on a field moves it on both sides at once, and a
field asked from the wrong side is a `KeyError` naming the field — and
nothing else, because the value it did not find is the only thing worth
leaking.

The names come from the capability matrix (`capacidades.CHANNEL_PROVIDERS`)
and the modules from `PROVIDERS`; the adapters below are keyed by module, so
this file spells no provider name and the `ast` check of C1 stays true. An
adapter per module exists because the constructors are not the forms:
`telegram`'s field is `bot_token` and its attribute is `token`, and
`meta_cloud`'s `waba_id` is needed to list templates, not to send one.

`http` is the caller's: it must come from `verification_client()`, where the
`httpx` request log is muted, because two of the four carry the token in the
URL path. The provider built here knows nothing of the database, the vault or
the tenant — it receives strings and a client, and
`tests/test_provedores_whatsapp.py` walks the `ast` of the four modules to
keep it that way.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import ModuleType

import httpx

from operax.alertas import capacidades
from operax.alertas.provedores import PROVIDERS, meta_cloud, telegram, uazapi, z_api
from operax.alertas.provedores.base import Provider


def _fields(
    module: ModuleType, config: Mapping[str, str], secrets: Mapping[str, str]
) -> dict[str, str]:
    """Every field the module declares, from the side `FieldSpec.secret` names.

    Extra keys on either side are ignored (`config` also carries what the
    channel route stores next to the form, e.g. a webhook URL); a declared
    field absent from its side is a `KeyError` with the field name only.
    """
    values: dict[str, str] = {}
    for spec in module.FIELDS:
        source = secrets if spec.secret else config
        if spec.name not in source:
            raise KeyError(spec.name)
        values[spec.name] = source[spec.name]
    return values


def _meta_cloud(fields: Mapping[str, str], http: httpx.AsyncClient) -> Provider:
    return meta_cloud.MetaCloudProvider(
        phone_number_id=fields["phone_number_id"], token=fields["token"], http=http
    )


def _z_api(fields: Mapping[str, str], http: httpx.AsyncClient) -> Provider:
    return z_api.ZApiProvider(
        instance_id=fields["instance_id"],
        token=fields["token"],
        client_token=fields["client_token"],
        http=http,
    )


def _uazapi(fields: Mapping[str, str], http: httpx.AsyncClient) -> Provider:
    return uazapi.UazapiProvider(base_url=fields["base_url"], token=fields["token"], http=http)


def _telegram(fields: Mapping[str, str], http: httpx.AsyncClient) -> Provider:
    return telegram.TelegramProvider(token=fields["bot_token"], http=http)


#: Keyed by module, not by name: the name is the matrix's to spell.
_BUILDERS: dict[ModuleType, Callable[[Mapping[str, str], httpx.AsyncClient], Provider]] = {
    meta_cloud: _meta_cloud,
    z_api: _z_api,
    uazapi: _uazapi,
    telegram: _telegram,
}


def build(
    provider: str,
    *,
    config: Mapping[str, str],
    secrets: Mapping[str, str],
    http: httpx.AsyncClient,
) -> Provider:
    """The provider `provider` names, holding its credential and `http`.

    Unknown name → `capacidades.UnknownProviderError`, from the matrix itself,
    before any field is read. Field missing from the side its `FieldSpec`
    declares → `KeyError(<field name>)`.
    """
    capacidades.capabilities_for(provider)
    module = PROVIDERS[provider]
    return _BUILDERS[module](_fields(module, config, secrets), http)
