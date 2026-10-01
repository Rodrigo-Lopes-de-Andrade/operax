#!/usr/bin/env python3
"""A janela 21→20 do banco é a mesma do DP — `util.competencia_janela` contra
`operax.dp.ciclo.cycle_window`.

    ENSAIO_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55322/operax_test \\
      uv run --no-sync --project backend python scripts/80_teste_janela_competencia.py

⛔ POR QUE ESTE TESTE EXISTE
A janela da competência passou a viver em dois lugares: em Python, na tela do
vale transporte (`dp/ciclo.py`), e em SQL, na fila de aprovação da alçada
(`public.fn_fila_aprovacao`, P1.3). O dono decidiu (29/09/2026) que as duas são a
MESMA janela — 21 do mês anterior a 20 do mês. Duas cópias de uma regra de
calendário divergem no primeiro janeiro em que alguém mexe numa delas; este
teste é o que faz a divergência ficar vermelha em vez de virar uma justificativa
que o RH aprova numa competência e o DP paga em outra.

Todos os meses de quatro anos, com um bissexto (2028) e três viradas de ano.

E `util.competencia_de(data)`, que a fila usa para a competência corrente, dia
a dia no mesmo intervalo: uma resposta só, e a janela dela (que acima já se
provou igual à de `ciclo.py`) contém a data. Ela não tem cópia da regra — pergunta à janela —, e
é isto que prova que a pergunta tem uma resposta e é a certa.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import psycopg

from operax.dp.ciclo import TRANSPORT_VOUCHER, cycle_window

DSN = os.environ.get("ENSAIO_DATABASE_URL")
if not DSN:
    print("  ✖ defina ENSAIO_DATABASE_URL com o DSN do banco de ensaio")
    raise SystemExit(1)

ANOS = range(2025, 2029)

with psycopg.connect(DSN) as conn:
    falhas = []
    n = 0
    for ano in ANOS:
        for mes in range(1, 13):
            banco = conn.execute(
                "select period_start, period_end from util.competencia_janela(%s, %s)",
                (ano, mes),
            ).fetchone()
            python = cycle_window(TRANSPORT_VOUCHER, ano, mes)
            n += 1
            if banco != python:
                falhas.append(f"{ano}/{mes:02d}: banco {banco}, ciclo.py {python}")

    dias = 0
    dia = date(ANOS.start, 1, 1)
    while dia.year < ANOS.stop:
        linhas = conn.execute(
            "select period_year, period_month from util.competencia_de(%s)", (dia,)
        ).fetchall()
        dias += 1
        if len(linhas) != 1:
            falhas.append(f"competencia_de({dia}): {len(linhas)} competências")
        else:
            inicio, fim = cycle_window(TRANSPORT_VOUCHER, *linhas[0])
            if not inicio <= dia <= fim:
                falhas.append(f"competencia_de({dia}) = {linhas[0]}, cuja janela é {inicio}..{fim}")
        dia += timedelta(days=1)

if falhas:
    print("  ✖ a janela do banco diverge de dp/ciclo.py:")
    for f in falhas:
        print(f"      {f}")
    sys.exit(1)
print(f"  ✔ {n} competências ({ANOS.start}–{ANOS.stop - 1}): banco e ciclo.py dão a mesma janela")
print(f"  ✔ {dias} dias: util.competencia_de devolve uma competência, e a janela dela contém o dia")
