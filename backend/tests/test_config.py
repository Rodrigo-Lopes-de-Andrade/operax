"""Startup configuration: it fails loud, it names the variable, it leaks no secret."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from operax.core.config import ConfigurationError, Settings, get_settings

REQUIRED = (
    "DATABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_JWT_JWKS_URL",
)
SECRET = "super-secret-value-nobody-should-see"


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # A developer's own .env must not decide whether this test passes.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_missing_required_variable_fails_loud_and_names_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SUPABASE_JWT_JWKS_URL")

    with pytest.raises(ConfigurationError) as error:
        get_settings()

    assert "SUPABASE_JWT_JWKS_URL" in str(error.value)


def test_every_missing_variable_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in REQUIRED:
        monkeypatch.delenv(variable)

    with pytest.raises(ConfigurationError) as error:
        get_settings()

    message = str(error.value)
    for variable in REQUIRED:
        assert variable in message


def test_failure_never_echoes_a_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SECRET)
    monkeypatch.delenv("DATABASE_URL")

    with pytest.raises(ConfigurationError) as error:
        get_settings()

    assert "DATABASE_URL" in str(error.value)
    assert SECRET not in str(error.value)


def test_settings_never_render_a_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SECRET)

    settings = get_settings()

    assert SECRET not in repr(settings)
    assert SECRET not in str(settings)
    assert settings.supabase_service_role_key.get_secret_value() == SECRET


def test_at_least_one_provider_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(variable, raising=False)

    with pytest.raises(ConfigurationError) as error:
        get_settings()

    message = str(error.value)
    assert "OPENAI_API_KEY" in message
    assert "ANTHROPIC_API_KEY" in message
    assert "GOOGLE_API_KEY" in message


def test_wildcard_origin_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "*")

    with pytest.raises(ConfigurationError) as error:
        get_settings()

    assert "CORS_ORIGINS" in str(error.value)


def test_origins_come_from_a_comma_separated_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://app.operax.com.br, https://staging.operax.com.br")

    settings = get_settings()

    assert settings.cors_origins == ("https://app.operax.com.br", "https://staging.operax.com.br")


def test_issuer_is_derived_from_the_supabase_project() -> None:
    assert get_settings().jwt_issuer == "https://project.supabase.co/auth/v1"
