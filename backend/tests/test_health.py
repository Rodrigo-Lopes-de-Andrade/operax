"""The health check Railway calls: public, and it says nothing about the environment."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_answers_without_authentication(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ignores_a_broken_token(client: TestClient) -> None:
    response = client.get("/health", headers={"Authorization": "Bearer not-a-token"})

    assert response.status_code == 200
