"""The in-memory limiter, on its own: what it keeps, and what it lets go.

`test_assistente.py` proves the 429 shape the assistant relies on. This file
proves the part a public endpoint relies on — the map does not grow without
bound when every caller is a new key.
"""

from __future__ import annotations

import pytest

from server import ratelimit
from server.ratelimit import RateLimiter


def test_chaves_que_envelheceram_inteiras_sao_despejadas(monkeypatch: pytest.MonkeyPatch) -> None:
    """⛔ Num endpoint público a chave é o IP de quem chamou. Sem despejo, 50 mil
    IPs distintos são 50 mil entradas para sempre; com ele, o mapa encolhe ao
    que ainda está dentro da janela."""
    agora = [1000.0]
    monkeypatch.setattr(ratelimit, "monotonic", lambda: agora[0])
    limiter = RateLimiter(limit=12, window=60.0)

    for i in range(limiter.limit * 64 + 1):
        assert limiter.retry_after(f"ip-{i}") is None
    assert len(limiter._hits) == limiter.limit * 64 + 1

    agora[0] += 61.0
    assert limiter.retry_after("ip-novo") is None

    # Só quem bateu dentro da janela sobrevive: a chave nova.
    assert set(limiter._hits) == {"ip-novo"}


def test_chave_ainda_na_janela_nao_e_despejada(monkeypatch: pytest.MonkeyPatch) -> None:
    agora = [1000.0]
    monkeypatch.setattr(ratelimit, "monotonic", lambda: agora[0])
    limiter = RateLimiter(limit=1, window=60.0)

    for i in range(limiter.limit * 64 + 1):
        limiter.retry_after(f"ip-{i}")
    agora[0] += 30.0  # dentro da janela
    limiter.retry_after("ip-novo")

    assert "ip-0" in limiter._hits and "ip-novo" in limiter._hits
    # E o teto continua valendo para quem está dentro dela.
    assert limiter.retry_after("ip-0") is not None
