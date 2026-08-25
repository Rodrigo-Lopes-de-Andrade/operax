"""The assistant endpoint — SSE, and the two failures that must not look alike.

A refusal is a **successful** turn: the assistant was asked something outside the
closed catalogue, or something the person's domains do not reach, and it said so.
It arrives as `event: recusa` inside a 200 stream. An error is the other thing —
the provider fell over, the catalogue could not be read — and it arrives as
`event: error`, also inside a 200 stream, because by then the response has
already started and there is no status code left to change.

The only failures that get a status code are the ones decided **before the first
byte**: no token (401), no membership (403), too many questions (429), a model
that is not on the allowlist (400). The frontend checks `res.ok` before it starts
reading, which is why those have to happen up here.

WHY THE RECORD IS WRITTEN IN `finally`
`app.ai_query` is the only place the cost of this feature is visible. The turn
that most deserves to be recorded is the one where somebody asked something
expensive and closed the tab — the tokens were paid either way. So the write does
not hang off the last event of the stream; it hangs off the stream ending, for
any reason.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from time import monotonic
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from psycopg.types.json import Jsonb

from operax.agente.agente import (
    Event,
    ModelNotAllowedError,
    NoProviderConfiguredError,
    Record,
    Turn,
    build_model,
)
from operax.core.tenant import TenantContext, tenant_scope
from server.deps import CurrentTenant
from server.models import AssistantQuestion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistente", tags=["assistente"])

#: Sem ele, proxies e balanceadores derrubam um stream ocioso — e o assistente
#: fica ocioso o tempo inteiro em que o modelo está pensando.
_PING_SECONDS = 15.0

#: Doze perguntas por minuto por pessoa. Não é proteção contra abuso de terceiro
#: (o token é válido): é o teto que impede um laço no frontend, ou uma pessoa
#: impaciente segurando o Enter, de virar uma conta de provider. Uma pergunta
#: leva segundos, então doze por minuto não alcança nenhum uso legítimo.
_LIMIT = 12
_WINDOW_SECONDS = 60.0


@dataclass(slots=True)
class RateLimiter:
    """Janela deslizante por usuário, em memória.

    Em memória porque a topologia é instância única no Railway — está escrito no
    CLAUDE.md, e é a mesma premissa do resto do processo. Quando houver segunda
    instância isto vira um contador no banco, e o lugar de descobrir isso é aqui.
    """

    limit: int = _LIMIT
    window: float = _WINDOW_SECONDS
    _hits: dict[UUID, deque[float]] = field(default_factory=dict)

    def check(self, user_id: UUID) -> None:
        agora = monotonic()
        marcas = self._hits.setdefault(user_id, deque())
        while marcas and agora - marcas[0] > self.window:
            marcas.popleft()
        if len(marcas) >= self.limit:
            espera = int(self.window - (agora - marcas[0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Muitas perguntas em sequência. Tente de novo em {espera}s.",
                headers={"Retry-After": str(espera)},
            )
        marcas.append(agora)


_limiter = RateLimiter()


_INSERT_SQL = """
insert into app.ai_query (
    tenant_id, user_id, question, model, metric_code, parameters,
    rows_returned, latency_ms, input_tokens, output_tokens, refused, refusal_reason
) values (
    %(tenant_id)s, %(user_id)s, %(question)s, %(model)s, %(metric_code)s, %(parameters)s,
    %(rows_returned)s, %(latency_ms)s, %(input_tokens)s, %(output_tokens)s,
    %(refused)s, %(refusal_reason)s
)
returning id
"""


async def registrar(tenant: TenantContext, record: Record) -> UUID:
    """Grava o turno em `app.ai_query` e devolve o id da consulta."""
    async with tenant_scope(tenant) as scope:
        await scope.execute(
            _INSERT_SQL,
            {
                "user_id": tenant.user_id,
                "question": record.question,
                "model": record.model,
                "metric_code": record.metric_code,
                "parameters": Jsonb(record.parameters) if record.parameters else None,
                "rows_returned": record.rows_returned,
                "latency_ms": record.latency_ms,
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "refused": record.refused,
                "refusal_reason": record.refusal_reason,
            },
        )
        linha = await scope.fetchone()
    return linha["id"]


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


_FIM = object()


async def com_ping(eventos: AsyncIterator[Event]) -> AsyncIterator[Event | None]:
    """Os mesmos eventos, com `None` no lugar de cada silêncio longo.

    O turno é uma fila alimentada por uma tarefa, e não um `async for` com
    timeout, por uma razão de leitura: cronometrar o `__anext__` de um gerador
    exige `shield` para o timeout não cancelar o gerador junto, e um `shield`
    dentro de um `wait_for` é o tipo de linha que ninguém revisa duas vezes.
    """
    fila: asyncio.Queue[Any] = asyncio.Queue()

    async def bombear() -> None:
        try:
            async for evento in eventos:
                await fila.put(evento)
        finally:
            await fila.put(_FIM)

    tarefa = asyncio.create_task(bombear())
    try:
        while True:
            try:
                item = await asyncio.wait_for(fila.get(), _PING_SECONDS)
            except TimeoutError:
                yield None
                continue
            if item is _FIM:
                return
            yield item
    finally:
        tarefa.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarefa


async def _stream(tenant: TenantContext, turno: Turn) -> AsyncIterator[str]:
    gravado = False
    try:
        async for evento in com_ping(turno.stream()):
            if evento is None:
                yield sse("ping", {})
                continue
            yield sse(evento.type, evento.data)

        consulta_id = await registrar(tenant, turno.record)
        gravado = True
        yield sse(
            "done",
            {
                "consulta_id": str(consulta_id),
                "modelo": turno.record.model,
                "tokens_entrada": turno.record.input_tokens,
                "tokens_saida": turno.record.output_tokens,
                "latencia_ms": turno.record.latency_ms,
            },
        )
    finally:
        if not gravado:
            # A pessoa fechou a aba, ou o `registrar` de cima falhou. Os tokens
            # foram pagos nos dois casos.
            with contextlib.suppress(Exception):
                await registrar(tenant, turno.record)


@router.post("/perguntar")
async def perguntar(payload: AssistantQuestion, tenant: CurrentTenant) -> StreamingResponse:
    """Uma pergunta, uma resposta em streaming. Recusa é resposta, não erro."""
    _limiter.check(tenant.user_id)
    try:
        modelo, model_id = build_model(payload.model)
    except ModelNotAllowedError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except NoProviderConfiguredError as error:
        logger.error("assistente: nenhum provider configurado nesta instalação")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O assistente não está configurado nesta instalação.",
        ) from error

    turno = Turn(tenant, payload.question, modelo, model_name=model_id)
    return StreamingResponse(
        _stream(tenant, turno),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            # O Nginx da frente bufferiza `text/event-stream` por padrão, e um
            # stream bufferizado chega inteiro no fim: o mesmo que não existir.
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
