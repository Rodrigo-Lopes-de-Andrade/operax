#!/usr/bin/env python3
"""`deteccao.detect()` de verdade contra o banco: o run abre, fecha, e com o escopo certo.

    ENSAIO_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55322/operax_test \\
      uv run --no-sync --project backend python scripts/79_teste_detect_run.py

⛔ POR QUE ESTE TESTE EXISTE
O `94` extrai o SQL do motor e o roda por `psql`; nenhum teste chamava a função
`detect()` inteira. Foi assim que um defeito de Python passou pela suíte verde:
o parâmetro `scope` de `detect()` era sombreado pelo `async with tenant_scope(...)
as scope`, e o objeto `TenantScope` ia como parâmetro SQL do `insert` do run.

    psycopg.ProgrammingError: cannot adapt type 'TenantScope'

Todo `detect()` quebrava ao abrir o run: os dois crons, o retro e o
reprocessamento de feriado. Este teste roda o código, não uma cópia dele, e olha
para `app.detection_run` depois:

1. janela de um dia, sem escopo pedido  -> `incremental`, `completed`
2. janela de sete dias, sem escopo pedido -> `backfill`, `completed`
3. janela de um dia com `run_scope="backfill"` -> `backfill` (o pedido vence a janela)
4. `feriados.reprocess`, o chamador real do item 3 -> `backfill`, `completed`
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

DSN = os.environ.get("ENSAIO_DATABASE_URL")
if not DSN:
    print("  ✖ defina ENSAIO_DATABASE_URL com o DSN do banco de ensaio")
    raise SystemExit(1)

os.environ["DATABASE_URL"] = DSN
os.environ.setdefault("SUPABASE_URL", "https://project.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key-for-tests")
os.environ.setdefault(
    "SUPABASE_JWT_JWKS_URL", "https://project.supabase.co/auth/v1/.well-known/jwks.json"
)
os.environ.setdefault("ANTHROPIC_API_KEY", "anthropic-key-for-tests")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from operax.core.db import get_pools  # noqa: E402
from operax.core.tenant import SystemContext  # noqa: E402
from operax.motor import deteccao, feriados  # noqa: E402

TENANT = "79000000-0000-0000-0000-000000000001"
CONTEXT = SystemContext(tenant_id=uuid.UUID(TENANT), task="79-teste-detect-run")
DIA = date(2026, 9, 1)
NOW = datetime(2026, 9, 30, 12, tzinfo=UTC)

_LIMPAR = f"""
delete from app.detection_run where tenant_id = '{TENANT}';
delete from app.tenant where id = '{TENANT}';
"""

falhas: list[str] = []


def sql(texto: str) -> list[dict]:
    with psycopg.connect(DSN, row_factory=dict_row, autocommit=True) as conexao:
        with conexao.cursor() as cur:
            cur.execute(texto)
            return cur.fetchall() if cur.description else []


def run(run_id: uuid.UUID) -> dict:
    return sql(
        f"select scope, status, period_start, period_end, error "
        f"from app.detection_run where id = '{run_id}' and tenant_id = '{TENANT}'"
    )[0]


def igual(rotulo: str, obtido: object, esperado: object) -> None:
    if obtido != esperado:
        falhas.append(f"{rotulo}: esperado {esperado!r}, obtido {obtido!r}")
        print(f"  ✖ {rotulo}: esperado {esperado!r}, obtido {obtido!r}")
    else:
        print(f"  ok  {rotulo} ({obtido!r})")


async def chamar[T](rotulo: str, chamada: Callable[[], Awaitable[T]]) -> T | None:
    try:
        return await chamada()
    except Exception as exc:  # noqa: BLE001 — é o que está sob teste
        falhas.append(f"{rotulo}: levantou {type(exc).__name__}: {exc}")
        print(f"  ✖ {rotulo}: levantou {type(exc).__name__}: {exc}")
        return None


def conferir(rotulo: str, resultado: deteccao.RunResult | None, scope: str) -> None:
    if resultado is None:
        return
    linha = run(resultado.run_id)
    igual(f"{rotulo}: status", linha["status"], "completed")
    igual(f"{rotulo}: scope", linha["scope"], scope)
    igual(
        f"{rotulo}: janela",
        (linha["period_start"], linha["period_end"]),
        (resultado.start, resultado.end),
    )


async def main() -> None:
    await get_pools().open()
    try:
        print("--- 1. um dia, sem escopo pedido: incremental")
        r = await chamar("incremental", lambda: deteccao.detect(CONTEXT, DIA, DIA))
        conferir("incremental", r, "incremental")

        print("--- 2. sete dias, sem escopo pedido: backfill")
        r = await chamar(
            "backfill", lambda: deteccao.detect(CONTEXT, DIA, date(2026, 9, 7), now=NOW)
        )
        conferir("backfill", r, "backfill")

        print("--- 3. um dia com run_scope='backfill': o pedido vence a janela")
        r = await chamar(
            "explícito",
            lambda: deteccao.detect(CONTEXT, DIA, DIA, now=NOW, run_scope="backfill"),
        )
        conferir("explícito", r, "backfill")

        print("--- 4. feriados.reprocess, o chamador real do escopo explícito")
        rep = await chamar(
            "feriados.reprocess",
            lambda: feriados.reprocess(CONTEXT, DIA, mode="shadow", now=NOW),
        )
        conferir("feriados.reprocess", rep.detection if rep else None, "backfill")
    finally:
        await get_pools().close()


sql(_LIMPAR)
sql(f"insert into app.tenant (id, slug, name) values ('{TENANT}', 't79-detect-run', 'T79')")
asyncio.run(main())
sql(_LIMPAR)

print()
if falhas:
    print(f"  ✖ {len(falhas)} FALHA(S)")
    sys.exit(1)
print(" DETECT(): O RUN ABRE, FECHA E CARREGA O ESCOPO CERTO")
