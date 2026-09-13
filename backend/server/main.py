"""FastAPI entrypoint.

Serves the panel API for individual and sensitive data, the AI assistant and the
administrative endpoints. It is the only place in the product holding
`service_role`, so every route that touches data goes through the tenant context.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from operax.core.config import get_settings
from operax.core.db import get_pools
from server.deps import CurrentTenant, CurrentUser
from server.models import HealthResponse, Identity
from server.routers import (
    assistente,
    canais,
    curadoria,
    dp,
    employees,
    folha,
    justificativas,
    monitor,
    rh,
    rh_employees,
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


app.include_router(assistente.router)
app.include_router(canais.router)
app.include_router(curadoria.router)
app.include_router(dp.router)
app.include_router(employees.router)
app.include_router(folha.router)
app.include_router(justificativas.router)
app.include_router(monitor.router)
app.include_router(rh.router)
app.include_router(rh_employees.router)


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
