"""Test bootstrap.

Nothing here touches the network or a database: the JWKS client and the
membership lookup are the two seams, and both are injected.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

os.environ["DATABASE_URL"] = "postgresql://operax:secret@localhost:5432/operax"
os.environ["SUPABASE_URL"] = "https://project.supabase.co"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "service-role-key-for-tests"
os.environ["SUPABASE_JWT_JWKS_URL"] = "https://project.supabase.co/auth/v1/.well-known/jwks.json"
os.environ["ANTHROPIC_API_KEY"] = "anthropic-key-for-tests"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"

import jwt  # noqa: E402
import pytest  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.hazmat.primitives.serialization import (  # noqa: E402
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from fastapi.testclient import TestClient  # noqa: E402
from jwt import PyJWK  # noqa: E402
from jwt.algorithms import RSAAlgorithm  # noqa: E402

from operax.core.tenant import TenantContext, UserRole  # noqa: E402
from server.deps import (  # noqa: E402
    JwksTokenVerifier,
    get_membership_resolver,
    get_token_verifier,
)
from server.main import app  # noqa: E402

ISSUER = "https://project.supabase.co/auth/v1"
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
TENANT_ID = UUID("22222222-2222-4222-8222-222222222222")
ROLE = UserRole.UNIT_SUPERVISOR


class StubSigningKeys:
    """Stands in for `PyJWKClient`: same method, no HTTP."""

    def __init__(self, key: PyJWK) -> None:
        self._key = key

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        return self._key


def _generate_key(kid: str) -> tuple[bytes, PyJWK]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    public_jwk: dict[str, Any] = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk |= {"alg": "RS256", "use": "sig", "kid": kid}
    return private_pem, PyJWK.from_dict(public_jwk)


@pytest.fixture(scope="session")
def signing_key() -> tuple[bytes, PyJWK]:
    return _generate_key("operax-test")


@pytest.fixture(scope="session")
def other_signing_key() -> tuple[bytes, PyJWK]:
    return _generate_key("someone-else")


TokenFactory = Callable[..., str]


@pytest.fixture
def issue_token(signing_key: tuple[bytes, PyJWK]) -> TokenFactory:
    private_pem, _ = signing_key

    def factory(*, private_key: bytes | None = None, **claims: Any) -> str:
        payload: dict[str, Any] = {
            "sub": str(USER_ID),
            "aud": "authenticated",
            "iss": ISSUER,
            "email": "gestor@kastropark.com.br",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        }
        payload |= claims
        return jwt.encode(payload, private_key or private_pem, algorithm="RS256")

    return factory


@pytest.fixture
def verifier(signing_key: tuple[bytes, PyJWK]) -> JwksTokenVerifier:
    _, public_key = signing_key
    return JwksTokenVerifier(StubSigningKeys(public_key), ISSUER)


async def _membership(user_id: UUID) -> TenantContext:
    return TenantContext(tenant_id=TENANT_ID, user_id=user_id, role=ROLE)


@pytest.fixture
def client(verifier: JwksTokenVerifier) -> Iterator[TestClient]:
    app.dependency_overrides[get_token_verifier] = lambda: verifier
    app.dependency_overrides[get_membership_resolver] = lambda: _membership
    # No context manager: the lifespan opens connection pools, and these tests
    # must not reach for a database.
    yield TestClient(app)
    app.dependency_overrides.clear()
