"""Process settings.

Fails loud at startup when a required variable is missing: a backend that boots
half-configured is worse than one that refuses to boot. Secret values are held in
`SecretStr` and never rendered — not in logs, not in error messages.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROVIDER_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY")


class ConfigurationError(RuntimeError):
    """The process is not configured well enough to start."""


class Settings(BaseSettings):
    """Environment of the backend. Field names map to upper case variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: SecretStr
    supabase_url: str
    supabase_service_role_key: SecretStr
    supabase_jwt_jwks_url: str

    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None

    # Exact origins of the dashboard. With allow_credentials, "*" is forbidden.
    cors_origins: Annotated[tuple[str, ...], NoDecode] = ("http://localhost:3000",)

    # The public https address of THIS API, no trailing slash — what the Telegram
    # platform calls back on (`{API_PUBLIC_URL}/webhooks/telegram/{path_token}`).
    # Optional on purpose: without it the process runs and "Conectar o bot"
    # answers 422 `no_public_url`, instead of registering a webhook nobody
    # reaches. Empty is absent — the `.env.example` lists it blank.
    api_public_url: str | None = None

    # Bucket privado do Storage onde o arquivo importado fica guardado. Privado
    # não é opinião: o arquivo carrega nome, matrícula e, conforme o template,
    # salário.
    import_bucket: str = "imports"

    sentry_dsn: SecretStr | None = None
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str | None = None

    @property
    def dashboard_url(self) -> str:
        """De onde sai o link profundo do relatório.

        É a primeira origem de `CORS_ORIGINS` — que é, por definição, a origem
        exata do painel. Uma variável nova para a mesma coisa seria uma variável
        a mais para esquecer num dos dois painéis de deploy, e um link quebrado
        numa mensagem de WhatsApp não tem como ser corrigido depois de enviado.
        """
        return self.cors_origins[0]

    @property
    def jwt_issuer(self) -> str:
        """Issuer Supabase Auth stamps on the access token of this project."""
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(origin.strip() for origin in value.split(",") if origin.strip())
        return value

    @field_validator("cors_origins", mode="after")
    @classmethod
    def _reject_wildcard(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if "*" in value:
            raise ValueError("CORS_ORIGINS cannot contain '*': the API answers with credentials")
        return value

    @field_validator("api_public_url", mode="before")
    @classmethod
    def _public_url_shape(cls, value: object) -> object:
        if value is None or value == "":
            return None
        if not isinstance(value, str) or not value.startswith("https://") or value.endswith("/"):
            raise ValueError("API_PUBLIC_URL must start with https:// and carry no trailing slash")
        return value

    @model_validator(mode="after")
    def _require_one_provider_key(self) -> Settings:
        if not any((self.openai_api_key, self.anthropic_api_key, self.google_api_key)):
            raise ValueError(f"at least one of {', '.join(PROVIDER_KEYS)} is required")
        return self


def _describe(error: ValidationError) -> str:
    """Render a startup failure naming the variables — never their values."""
    missing = sorted(
        str(item["loc"][0]).upper() for item in error.errors() if item["type"] == "missing"
    )
    invalid = sorted(
        f"{'.'.join(str(part) for part in item['loc']).upper() or 'settings'}: {item['msg']}"
        for item in error.errors()
        if item["type"] != "missing"
    )
    parts = []
    if missing:
        parts.append(f"missing required environment variables: {', '.join(missing)}")
    if invalid:
        parts.append(f"invalid environment: {'; '.join(invalid)}")
    return " | ".join(parts)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as error:
        # `from None`: the pydantic error carries the offending input, and some of
        # those inputs are secrets.
        raise ConfigurationError(_describe(error)) from None
