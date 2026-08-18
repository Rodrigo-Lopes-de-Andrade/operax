"""Token validation and tenant resolution, exercised through the real dependency.

The signature, expiry, audience and issuer checks are the production ones — only
the JWKS fetch and the membership query are injected.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import inspect
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient
from jwt import PyJWK
from jwt.exceptions import PyJWKClientConnectionError

from operax.core.tenant import AmbiguousTenantMembershipError, NoTenantMembershipError
from server.deps import (
    JwksTokenVerifier,
    get_current_user,
    get_membership_resolver,
    get_token_verifier,
)
from server.main import app
from tests.conftest import ISSUER, ROLE, TENANT_ID, USER_ID, TokenFactory


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _signing_input(header: dict[str, Any], payload: dict[str, Any]) -> str:
    """Header and payload of a token, assembled by hand.

    PyJWT refuses to *encode* HS256 with a public PEM, which is exactly the forgery
    these tests need to attempt.
    """
    return f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}"


def _claims() -> dict[str, Any]:
    return {
        "sub": str(USER_ID),
        "aud": "authenticated",
        "iss": ISSUER,
        "email": "gestor@kastropark.com.br",
        "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
    }


class UnreachableSigningKeys:
    """A JWKS endpoint that is down."""

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        raise PyJWKClientConnectionError("jwks unreachable")


def test_request_without_token_is_rejected(client: TestClient) -> None:
    response = client.get("/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_garbage_token_is_rejected(client: TestClient) -> None:
    response = client.get("/me", headers={"Authorization": "Bearer not.a.jwt"})

    assert response.status_code == 401


def test_expired_token_is_rejected(client: TestClient, issue_token: TokenFactory) -> None:
    token = issue_token(exp=datetime.now(UTC) - timedelta(seconds=1))

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_token_signed_by_another_key_is_rejected(
    client: TestClient,
    issue_token: TokenFactory,
    other_signing_key: tuple[bytes, PyJWK],
) -> None:
    forged_key, _ = other_signing_key
    token = issue_token(private_key=forged_key)

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_token_from_another_project_is_rejected(
    client: TestClient, issue_token: TokenFactory
) -> None:
    token = issue_token(iss="https://another-project.supabase.co/auth/v1")

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_anon_token_is_rejected(client: TestClient, issue_token: TokenFactory) -> None:
    token = issue_token(aud="anon")

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_token_without_subject_is_rejected(client: TestClient, issue_token: TokenFactory) -> None:
    token = issue_token(sub="not-a-uuid")

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_valid_token_resolves_tenant_and_role(
    client: TestClient, issue_token: TokenFactory
) -> None:
    token = issue_token()

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(USER_ID),
        "email": "gestor@kastropark.com.br",
        "tenant_id": str(TENANT_ID),
        "role": ROLE.value,
    }


@pytest.mark.parametrize(
    "failure",
    [NoTenantMembershipError("no membership"), AmbiguousTenantMembershipError("two tenants")],
)
def test_user_without_a_single_tenant_is_forbidden(
    client: TestClient,
    issue_token: TokenFactory,
    failure: Exception,
) -> None:
    async def resolver(user_id: object) -> None:
        raise failure

    app.dependency_overrides[get_membership_resolver] = lambda: resolver
    token = issue_token()

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


def test_token_forged_with_the_public_key_as_hmac_secret_is_rejected(
    client: TestClient, signing_key: tuple[bytes, PyJWK]
) -> None:
    # The JWKS is public. If HS256 ever joins the allowlist, the verification key
    # becomes the forging key and anyone mints a valid token.
    _, public_key = signing_key
    public_pem = public_key.key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    signing_input = _signing_input({"alg": "HS256", "typ": "JWT", "kid": "operax-test"}, _claims())
    signature = hmac.new(public_pem, signing_input.encode(), hashlib.sha256).digest()
    token = f"{signing_input}.{_b64url(signature)}"

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_unsigned_token_is_rejected(client: TestClient) -> None:
    token = f"{_signing_input({'alg': 'none', 'typ': 'JWT'}, _claims())}."

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_jwks_outage_is_not_reported_as_a_bad_token(
    client: TestClient, issue_token: TokenFactory
) -> None:
    # 401 here would send every signed-in client into a refresh loop against an
    # outage of ours.
    app.dependency_overrides[get_token_verifier] = lambda: JwksTokenVerifier(
        UnreachableSigningKeys(), ISSUER
    )
    token = issue_token()

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 503


def test_token_verification_stays_off_the_event_loop() -> None:
    # Verifying fetches the JWKS with blocking I/O, and an unverified `kid` decides
    # whether that fetch happens. As a coroutine it would stall the single event
    # loop of the Railway instance for everyone; FastAPI runs a sync dependency in
    # the threadpool.
    assert not inspect.iscoroutinefunction(get_current_user)
