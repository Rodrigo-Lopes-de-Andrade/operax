"""The WhatsApp providers, by name — built from the modules, never listed twice.

Each module owns its own `NAME`, and `PROVIDERS` is the registry the route reads.
`tests/test_canais_credencial.py` asserts `set(PROVIDERS) == set(WHATSAPP_PROVIDERS)`
in both directions: a module here that the capability matrix does not know, or
a name in the matrix with no module behind it, is a provider the screen can
choose and the API cannot verify.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import ModuleType

from operax.alertas.provedores import meta_cloud, uazapi, z_api

PROVIDERS: Mapping[str, ModuleType] = {
    module.NAME: module for module in (meta_cloud, z_api, uazapi)
}
