"""The system prompt, read through the pointer — and the three tokens it carries.

Since A1 the prompt is not code: it is the `platform` version on the air plus,
when the tenant has published, the `tenant` version on the air (SPEC-AGENTE §1,
§2). The runtime reads **only the pointers**, never the draft, and there is no
text left in this package to fall back to: with no platform pointer the turn
has nothing to run with, and it says so instead of running with something else.

WHAT THE RENDERER OWNS
The seeded text carries three tokens, documented on
`app.assistant_prompt_version.content`: `{{hoje}}`, `{{catalogo}}` and
`{{unidades}}`. The date expression, the catalogue text and the whole block of
unit lines — the fallback line included — belong to this module, not to the
text. The two layers are concatenated **before** rendering, so the tenant layer
may use the tokens too. A token the renderer does not know is a configuration
error, not a turn: `render` raises, and the turn turns that into `event: error`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from operax.core.tenant import TenantContext, user_scope

_TOKEN = re.compile(r"\{\{(\w+)\}\}")
_KNOWN_TOKENS = frozenset({"hoje", "catalogo", "unidades"})

#: What `{{unidades}}` renders to when the tenant has no unit: the line that
#: tells the model not to use the parameter. The renderer's, not the text's.
NO_UNITS_LINE = "- nenhuma unidade cadastrada; não use o parâmetro `unit`."


@dataclass(frozen=True, slots=True)
class PromptLayers:
    """The two versions on the air, as the pointers say. Never a draft."""

    platform_version_id: UUID
    platform_content: str
    #: The platform layer chooses the model (SPEC-AGENTE §6.2). Nullable in the
    #: schema; `None` means the installation default, as before versioning.
    provider: str | None
    model: str | None
    #: Tool round-trips the model may make in one turn. `None` = no ceiling.
    max_steps: int | None
    tenant_version_id: UUID | None
    tenant_content: str | None

    @property
    def version_id(self) -> UUID:
        """What `app.ai_query.prompt_version_id` records: the tenant version on
        the air, or the platform one if the tenant never published."""
        return self.tenant_version_id or self.platform_version_id

    def text(self, tenant_override: str | None = None) -> str:
        """Platform followed by tenant — or by `tenant_override`, the draft
        under test, which stands in for the tenant layer without being one."""
        tenant = self.tenant_content if tenant_override is None else tenant_override
        if tenant is None:
            return self.platform_content
        return f"{self.platform_content}\n\n{tenant}"


_LAYERS_SQL = """
select p.layer, v.id as version_id, v.content, v.provider, v.model, v.max_steps
from app.assistant_prompt_pointer p
join app.assistant_prompt_version v on v.id = p.version_id
where (p.tenant_id is null and p.layer = 'platform')
   or (p.tenant_id = %(tenant_id)s and p.layer = 'tenant')
"""


async def load_layers(tenant: TenantContext) -> PromptLayers | None:
    """The versions on the air for this tenant, read as the user.

    `None` when there is no platform pointer — the assistant has no doctrine
    to run with, and the caller must not invent one. A tenant pointer without
    a platform pointer is the same case: the RPC refuses to create it, and a
    layer on its own is not a prompt.
    """
    async with user_scope(tenant) as scope:
        await scope.execute(_LAYERS_SQL, {"tenant_id": tenant.tenant_id})
        rows = {row["layer"]: row for row in await scope.fetchall()}
    platform = rows.get("platform")
    if platform is None:
        return None
    tenant_row = rows.get("tenant")
    return PromptLayers(
        platform_version_id=platform["version_id"],
        platform_content=platform["content"],
        provider=platform["provider"],
        model=platform["model"],
        max_steps=platform["max_steps"],
        tenant_version_id=tenant_row["version_id"] if tenant_row else None,
        tenant_content=tenant_row["content"] if tenant_row else None,
    )


def render(layers_text: str, *, catalogo: str, unidades: list[dict[str, Any]], hoje: date) -> str:
    """The effective system prompt: the three tokens replaced, nothing else.

    Pure. Raises `ValueError` on a token the renderer does not know — it is the
    published text that is wrong, and a turn that ran with `{{x}}` in it would
    be a turn nobody configured.
    """
    unknown = sorted(set(_TOKEN.findall(layers_text)) - _KNOWN_TOKENS)
    if unknown:
        raise ValueError(f"unknown prompt token(s): {', '.join(unknown)}")
    if unidades:
        bloco = "\n".join(f"- {u['name']} ({u['code']}): {u['unit_id']}" for u in unidades)
    else:
        bloco = NO_UNITS_LINE
    values = {
        "hoje": f"{hoje.strftime('%d/%m/%Y')} ({hoje.isoformat()})",
        "catalogo": catalogo,
        "unidades": bloco,
    }
    # One pass over the text, so a value is never scanned for tokens itself.
    return _TOKEN.sub(lambda match: values[match.group(1)], layers_text)
