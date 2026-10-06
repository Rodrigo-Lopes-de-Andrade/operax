"""Supabase Auth Admin API — the one place the backend creates an identity.

`app.tenant_member.user_id` references `auth.users`, and an identity is born in
GoTrue, outside the database: inviting a person is therefore an HTTP call with
the service key, then an RPC (SPEC-USUARIOS §5.4). This module is the HTTP half.

⛔ What comes back from GoTrue never leaves this module except as a `UUID`. The
invite response is the user object, and the admin endpoints of GoTrue can carry
`action_link`, confirmation and recovery tokens: none of it may reach a response,
a log line or an exception message. So the body is read in one expression and
never bound to a name, and every error says the HTTP status and nothing else.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

import httpx

from operax.core.config import get_settings

_TIMEOUT_SECONDS = 15


class AuthAdminError(RuntimeError):
    """GoTrue refused or did not answer. The message carries the status only."""


class AuthAdmin(Protocol):
    """What the user routes need from the Admin API. Small on purpose."""

    async def invite(self, email: str, redirect_to: str, name: str | None = None) -> UUID: ...


class SupabaseAuthAdmin:
    """`POST /auth/v1/invite` with the service key.

    Called for a NEW identity (it creates the user and sends the invitation
    e-mail) and to resend: GoTrue sends the invitation again to a user who has
    not confirmed yet, and refuses one who has.
    """

    def __init__(self, base_url: str, service_key: str) -> None:
        self._url = f"{base_url.rstrip('/')}/auth/v1/invite"
        self._headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    async def invite(self, email: str, redirect_to: str, name: str | None = None) -> UUID:
        """`name`, quando dado, vai em `data.name` — os metadados da conta que o
        convite cria. O reenvio não o manda: não reescreve o que a pessoa tem."""
        body: dict[str, object] = {"email": email}
        if name is not None:
            body["data"] = {"name": name}
        # Network failure and timeout become `AuthAdminError` too (the route
        # answers 502). Raised OUTSIDE the `except`: `from None` only hides the
        # chain from the printout — `__context__` would still hold the httpx
        # error, whose request carries the service key in its headers, and an
        # error tracker walks `__context__`.
        resposta: httpx.Response | None = None
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                resposta = await client.post(
                    self._url,
                    params={"redirect_to": redirect_to},
                    json=body,
                    headers=self._headers,
                )
        except httpx.HTTPError:
            pass
        if resposta is None:
            raise AuthAdminError("o Admin API não respondeu (rede ou tempo esgotado)")
        if resposta.status_code >= 400:
            raise AuthAdminError(f"o Admin API recusou o convite (HTTP {resposta.status_code})")
        user_id: UUID | None = None
        try:
            user_id = UUID(str(resposta.json()["id"]))
        except (ValueError, KeyError, TypeError):
            # Same reason: the decoding error carries the body with it.
            pass
        if user_id is None:
            raise AuthAdminError("o Admin API respondeu sem o id do usuário")
        return user_id


def get_auth_admin() -> AuthAdmin:
    settings = get_settings()
    return SupabaseAuthAdmin(
        settings.supabase_url, settings.supabase_service_role_key.get_secret_value()
    )
