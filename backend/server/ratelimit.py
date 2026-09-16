"""A sliding window in memory, keyed by whatever identifies the caller.

Born in the assistant (`routers/assistente.py`), where the key is the user and
the refusal is a 429 with a sentence; generalised for the Telegram webhook
(`routers/webhooks.py`), where the keys are an IP and a path token and the 429
must carry **no body** — a public endpoint does not explain itself to whoever
is knocking. `retry_after` is the primitive both use; `check` is the assistant's
wrapper around it, unchanged in behaviour.

In memory because the topology is a single instance on Railway — it is written
in `CLAUDE.md`, and it is the same premise as the rest of the process. When a
second instance exists this becomes a counter in the database, and the place to
find that out is here.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Hashable
from dataclasses import dataclass, field
from time import monotonic

from fastapi import HTTPException, status

#: Doze perguntas por minuto por pessoa. Não é proteção contra abuso de terceiro
#: (o token é válido): é o teto que impede um laço no frontend, ou uma pessoa
#: impaciente segurando o Enter, de virar uma conta de provider. Uma pergunta
#: leva segundos, então doze por minuto não alcança nenhum uso legítimo.
_LIMIT = 12
_WINDOW_SECONDS = 60.0


@dataclass(slots=True)
class RateLimiter:
    """Janela deslizante por chave, em memória."""

    limit: int = _LIMIT
    window: float = _WINDOW_SECONDS
    _hits: dict[Hashable, deque[float]] = field(default_factory=dict)

    def retry_after(self, key: Hashable) -> int | None:
        """Registra a batida e devolve `None`; ou, no teto, os segundos de espera
        — e não registra, para que insistir não empurre a janela para a frente."""
        agora = monotonic()
        marcas = self._hits.setdefault(key, deque())
        while marcas and agora - marcas[0] > self.window:
            marcas.popleft()
        if len(marcas) >= self.limit:
            return int(self.window - (agora - marcas[0])) + 1
        marcas.append(agora)
        # Chave que envelheceu inteira sai do dicionário: num endpoint público
        # a chave é o IP de quem chamou, e sem despejo o mapa só cresce.
        if len(self._hits) > self.limit * 64:
            self._evict(agora)
        return None

    def _evict(self, agora: float) -> None:
        for chave, marcas in list(self._hits.items()):
            while marcas and agora - marcas[0] > self.window:
                marcas.popleft()
            if not marcas:
                del self._hits[chave]

    def check(self, key: Hashable) -> None:
        """A forma do assistente: 429 com a frase e `Retry-After`."""
        espera = self.retry_after(key)
        if espera is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Muitas perguntas em sequência. Tente de novo em {espera}s.",
                headers={"Retry-After": str(espera)},
            )
