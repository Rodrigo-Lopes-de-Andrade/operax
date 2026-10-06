"""FastAPI entrypoint.

Serves the panel API for individual and sensitive data, the AI assistant and the
administrative endpoints. It is the only place in the product holding
`service_role`, so every route that touches data goes through the tenant context.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from operax.core.config import get_settings
from operax.core.db import get_pools
from server.deps import CurrentTenant, CurrentUser
from server.models import HealthResponse, Identity
from server.routers import (
    alcada,
    assistente,
    assistente_config,
    canais,
    canais_regras,
    curadoria,
    dp,
    employees,
    feriados,
    folha,
    justificativas,
    monitor,
    rh,
    rh_employees,
    usuarios,
    webhooks,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pools = get_pools()
    await pools.open()
    try:
        yield
    finally:
        await pools.close()


app = FastAPI(title="OperaX API", version="0.1.0", lifespan=lifespan)

# Exact origins, never "*": the dashboard calls this API with credentials.
# `PUT` is listed because the panel calls the API cross-origin and the browser
# preflights every `PUT`: without it Starlette answers 400 "Disallowed CORS
# method" and the templates, assistant-config and rules `PUT` routes are
# unreachable from the panel while every test stays green (measured, C6).
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def validation_error_without_echo(_: Request, exc: RequestValidationError) -> JSONResponse:
    """The standard 422, minus the `input` echo.

    FastAPI's default handler copies the offending value into each error — and
    for a missing field, the *parent object*. Measured on `POST /canais/credencial`
    without `provider`: the 422 carried the token back in `input`. A value that
    is a secret, a CPF or a salary does not belong in a response because the
    request around it was malformed, so `input` is dropped for every route;
    `type`, `loc` and `msg` — what a client acts on — stay as they were.
    """
    errors = [{k: v for k, v in error.items() if k != "input"} for error in exc.errors()]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": jsonable_encoder(errors)},
    )


app.include_router(alcada.router)
app.include_router(assistente.router)
app.include_router(assistente_config.router)
app.include_router(canais.router)
app.include_router(canais_regras.router)
app.include_router(curadoria.router)
app.include_router(dp.router)
app.include_router(employees.router)
app.include_router(feriados.router)
app.include_router(folha.router)
app.include_router(justificativas.router)
app.include_router(monitor.router)
app.include_router(rh.router)
app.include_router(rh_employees.router)
app.include_router(usuarios.router)
# The Telegram webhook: no JWT dependency, out of the OpenAPI schema, and a
# server-to-server POST that never carries an `Origin` — so the CORS middleware
# above has nothing to say about it (SPEC-CANAIS §6).
app.include_router(webhooks.router)


@app.get("/health")
async def health() -> HealthResponse:
    """Health check of the Railway deploy. Public by design."""
    return HealthResponse()


@app.get("/me")
async def me(user: CurrentUser, tenant: CurrentTenant) -> Identity:
    """Identity behind the access token, as the backend resolved it."""
    return Identity(
        user_id=user.user_id,
        email=user.email,
        tenant_id=tenant.tenant_id,
        role=tenant.role,
    )
