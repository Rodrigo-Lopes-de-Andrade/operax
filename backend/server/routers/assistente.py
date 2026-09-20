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

THE ONE STREAM THAT WRITES NOTHING
With no platform pointer there is no prompt to run and no turn to record: the
response is a lone `event: error`, no `done`, no row. `answer()` is that whole
sequence, and it is shared with the Teste tab (`assistente_config.py`) so the
dry run goes through the same limiter, the same stream and the same write.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
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
from operax.agente.prompt import load_layers
from operax.core.tenant import TenantContext, tenant_scope
from server.deps import CurrentTenant
from server.models import AssistantQuestion
from server.ratelimit import RateLimiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistente", tags=["assistente"])

#: Sem ele, proxies e balanceadores derrubam um stream ocioso — e o assistente
#: fica ocioso o tempo inteiro em que o modelo está pensando.
_PING_SECONDS = 15.0

#: Doze perguntas por minuto por pessoa — o default de `RateLimiter`, que nasceu
#: aqui e mora em `server/ratelimit.py` desde que o webhook do Telegram passou a
#: precisar dele com outra chave e sem corpo no 429.
_limiter = RateLimiter()


_INSERT_SQL = """
insert into app.ai_query (
    tenant_id, user_id, question, model, metric_code, parameters,
    rows_returned, latency_ms, input_tokens, output_tokens, refused, refusal_reason,
    prompt_version_id, is_dry_run, draft_content_hash
) values (
    %(tenant_id)s, %(user_id)s, %(question)s, %(model)s, %(metric_code)s, %(parameters)s,
    %(rows_returned)s, %(latency_ms)s, %(input_tokens)s, %(output_tokens)s,
    %(refused)s, %(refusal_reason)s,
    %(prompt_version_id)s, %(is_dry_run)s, %(draft_content_hash)s
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
                "prompt_version_id": record.prompt_version_id,
                "is_dry_run": record.is_dry_run,
                "draft_content_hash": record.draft_content_hash,
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
        record = turno.record
        yield sse(
            "done",
            {
                "consulta_id": str(consulta_id),
                "modelo": record.model,
                "tokens_entrada": record.input_tokens,
                "tokens_saida": record.output_tokens,
                "latencia_ms": record.latency_ms,
                # O que RODOU, lido do registro que acabou de ser gravado — e
                # não o `use_draft` que o cliente pediu. Hoje os dois coincidem
                # porque `/testar?use_draft` sem rascunho é 404 antes do
                # stream; no dia em que isso virar fallback, o selo "Rascunho"
                # da tela mentiria, e é esta coluna que existe para não deixar.
                "prompt_version_id": (
                    str(record.prompt_version_id) if record.prompt_version_id is not None else None
                ),
                "draft_content_hash": record.draft_content_hash,
            },
        )
    finally:
        if not gravado:
            # A pessoa fechou a aba, ou o `registrar` de cima falhou. Os tokens
            # foram pagos nos dois casos.
            with contextlib.suppress(Exception):
                await registrar(tenant, turno.record)


_SEM_CONFIGURACAO = "O assistente está sem configuração publicada."

_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    # O Nginx da frente bufferiza `text/event-stream` por padrão, e um
    # stream bufferizado chega inteiro no fim: o mesmo que não existir.
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


async def _only(evento: Event) -> AsyncIterator[str]:
    yield sse(evento.type, evento.data)


async def answer(
    tenant: TenantContext,
    question: str,
    requested_model: str | None,
    *,
    dry_run: bool = False,
    tenant_override: str | None = None,
) -> StreamingResponse:
    """Um turno como resposta SSE — o de `/perguntar` e o da aba Teste.

    A ordem é a do primeiro byte: o limite por pessoa, as camadas no ar (o
    modelo padrão sai delas), o modelo (400 se o cliente pediu um fora da
    allowlist, 503 se a instalação não roda o que a plataforma diz) e só então
    o stream. Sem ponteiro de plataforma não há turno: sai um `event: error`
    sozinho, sem `done` e sem linha em `app.ai_query` — não houve o que
    registrar, e em produção isso é a ordem migrations → push.
    """
    _limiter.check(tenant.user_id)
    layers = await load_layers(tenant)
    if layers is None:
        logger.error("assistente: nenhuma versão de plataforma publicada — sem ponteiro")
        return StreamingResponse(
            _only(Event("error", {"message": _SEM_CONFIGURACAO})),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )
    try:
        modelo, model_id = build_model(requested_model, layers=layers)
    except ModelNotAllowedError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except NoProviderConfiguredError as error:
        logger.error("assistente: o modelo configurado não roda nesta instalação: %s", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O assistente não está configurado nesta instalação.",
        ) from error

    turno = Turn(
        tenant,
        question,
        modelo,
        layers,
        model_name=model_id,
        dry_run=dry_run,
        tenant_override=tenant_override,
    )
    return StreamingResponse(
        _stream(tenant, turno),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/perguntar")
async def perguntar(payload: AssistantQuestion, tenant: CurrentTenant) -> StreamingResponse:
    """Uma pergunta, uma resposta em streaming. Recusa é resposta, não erro."""
    return await answer(tenant, payload.question, payload.model)
