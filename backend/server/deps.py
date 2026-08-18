"""Request dependencies: authentication and tenant resolution.

The access token is issued by Supabase Auth and validated here against the
project JWKS — there is no OperaX JWT and no OperaX user table. Tenant and role
come from `app.tenant_member`, never from a claim the client could shape.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Annotated, Any, Protocol
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWK, PyJWKClient, PyJWTError
from jwt.exceptions import PyJWKClientConnectionError

from operax.core.config import get_settings
from operax.core.tenant import (
    AmbiguousTenantMembershipError,
    NoTenantMembershipError,
    TenantContext,
    resolve_membership,
)
from server.models import AuthenticatedUser

_ALGORITHMS = ["RS256", "ES256"]
_AUDIENCE = "authenticated"
_REQUIRED_CLAIMS = ["exp", "sub", "aud", "iss"]
# The JWKS fetch is blocking I/O on the request path: an unreachable JWKS must
# fail fast, not hold a worker thread for half a minute.
_JWKS_TIMEOUT_SECONDS = 3

bearer_scheme = HTTPBearer(auto_error=False)


class SigningKeyProvider(Protocol):
    """What `JwksTokenVerifier` needs from a JWKS client. `PyJWKClient` satisfies it."""

    def get_signing_key_from_jwt(self, token: str) -> PyJWK: ...


class JwksTokenVerifier:
    """Validates a Supabase access token: signature, expiry, audience and issuer."""

    def __init__(self, signing_keys: SigningKeyProvider, issuer: str) -> None:
        self._signing_keys = signing_keys
        self._issuer = issuer

    @classmethod
    def from_jwks_url(cls, jwks_url: str, issuer: str) -> JwksTokenVerifier:
        # No `cache_keys`: that tier-2 cache is an lru_cache with no expiry, and it
        # would keep a rotated key valid forever in a long lived process. The
        # JWK set cache (5 min) is what saves the fetch per request.
        return cls(PyJWKClient(jwks_url, timeout=_JWKS_TIMEOUT_SECONDS), issuer)

    def verify(self, token: str) -> dict[str, Any]:
        signing_key = self._signing_keys.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=_ALGORITHMS,
            audience=_AUDIENCE,
            issuer=self._issuer,
            options={"require": _REQUIRED_CLAIMS},
        )


@lru_cache(maxsize=1)
def get_token_verifier() -> JwksTokenVerifier:
    settings = get_settings()
    return JwksTokenVerifier.from_jwks_url(settings.supabase_jwt_jwks_url, settings.jwt_issuer)


MembershipResolver = Callable[[UUID], Awaitable[TenantContext]]


def get_membership_resolver() -> MembershipResolver:
    return resolve_membership


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verifier: Annotated[JwksTokenVerifier, Depends(get_token_verifier)],
) -> AuthenticatedUser:
    """Identity behind the bearer token.

    Deliberately synchronous: verifying fetches the JWKS over the network, and the
    `kid` that decides whether a fetch happens comes from an unverified token. In a
    coroutine that call would block the single event loop of the Railway instance
    for every other request. FastAPI runs a sync dependency in the threadpool.
    """
    if credentials is None:
        raise _unauthorized("Credencial de acesso ausente.")
    try:
        claims = verifier.verify(credentials.credentials)
    except PyJWKClientConnectionError as error:
        # The JWKS being down is our outage, not a bad token: answering 401 would
        # send every client into a pointless refresh loop.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível validar a sessão agora. Tente novamente em instantes.",
        ) from error
    except PyJWTError as error:
        # The token itself never goes into the message.
        raise _unauthorized("Token inválido ou expirado.") from error
    try:
        user_id = UUID(claims["sub"])
    except (KeyError, ValueError, TypeError) as error:
        raise _unauthorized("Token sem identificação de usuário válida.") from error
    return AuthenticatedUser(user_id=user_id, email=claims.get("email"))


async def get_tenant_context(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    resolve: Annotated[MembershipResolver, Depends(get_membership_resolver)],
) -> TenantContext:
    try:
        return await resolve(user.user_id)
    except NoTenantMembershipError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário sem vínculo ativo com nenhum cliente.",
        ) from error
    except AmbiguousTenantMembershipError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário com vínculo ativo em mais de um cliente.",
        ) from error


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
CurrentTenant = Annotated[TenantContext, Depends(get_tenant_context)]
