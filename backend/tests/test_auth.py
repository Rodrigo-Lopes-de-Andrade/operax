"""Token validation and tenant resolution, exercised through the real dependency.

The signature, expiry, audience and issuer checks are the production ones — only
the JWKS fetch and the membership query are injected.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jwt import PyJWK

from operax.core.tenant import AmbiguousTenantMembershipError, NoTenantMembershipError
from server.deps import get_membership_resolver
from server.main import app
from tests.conftest import ROLE, TENANT_ID, USER_ID, TokenFactory


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
