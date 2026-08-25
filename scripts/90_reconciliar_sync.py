#!/usr/bin/env python3
"""Prova que a ingestão de batidas **voltou** — não que a função respondeu 200.

    python3 scripts/90_reconciliar_sync.py [--dias 2]

É o critério de "religou" da fase 3 da reconciliação. O §4b do
`docs/PLANO-RECONCILIACAO-NUVEM.md` explica por que ele precisa existir: a
invocação vem do pg_cron por `net.http_post`, e **o job registra sucesso por ter
entregado o POST**. Do lado do agendador, um 500 e um 200 são indistinguíveis.
Depois de uma janela de manutenção, "a função respondeu" não é resposta.

TRÊS AFIRMAÇÕES, E A TERCEIRA É A QUE IMPORTA

1. A última execução de `Batida` em `app.sync_run` terminou como `completed`.
2. Ela gravou linha: `records_written > 0`. Uma execução que lê e não grava é o
   modo de falha do risco 3 — correlação quebrada respondendo sucesso.
3. **Nenhuma `Batida` na janela está sem marcação.** Esta é a que não se deduz do
   relatório: é o estado que o risco 1 produzia quando `upsertBatidas` commitava
   e a leitura seguinte falhava. Ele não se lê como "faltando dado" — o motor de
   detecção o lê como `no_punches`, "o colaborador não bateu ponto naquele dia",
   e emite indício contra uma pessoa que bateu.

O item 3 é verificado **contra o dado**, e não contra o summary, de propósito: um
resumo é o que o código achou que fez. A tabela é o que ficou.

Sai com código 1 em qualquer falha, para servir de portão num roteiro de
manutenção.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

ENV = {
    **os.environ,
    "PGHOST": os.environ.get("PGHOST", "/tmp"),
    "PGPORT": os.environ.get("PGPORT", "5433"),
    "PGUSER": os.environ.get("PGUSER", "postgres"),
    "PGDATABASE": os.environ.get("PGDATABASE", "operax_test"),
}


def consultar(sql: str) -> list[list[str]]:
    r = subprocess.run(
        ["psql", "-tAF\t", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True,
        text=True,
        env=ENV,
    )
    if r.returncode != 0:
        sys.exit(f"psql falhou:\n{r.stderr}")
    return [linha.split("\t") for linha in r.stdout.split("\n") if linha.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dias",
        type=int,
        default=2,
        help="Janela conferida, em dias antes de hoje (padrão 2 — a janela incremental).",
    )
    dias = parser.parse_args().dias
    problemas: list[str] = []

    # 1 e 2 — a última execução de Batida.
    execucao = consultar(
        "select status, scope, records_read, records_written, records_skipped, "
        "coalesce(error, ''), coalesce(finished_at::text, '') "
        "from app.sync_run where entity = 'Batida' "
        "order by started_at desc limit 1"
    )
    if not execucao:
        problemas.append(
            "app.sync_run não tem nenhuma execução de 'Batida' — a ingestão nunca "
            "deixou rastro, ou a função ainda não roda com o registro de execução."
        )
    else:
        status, scope, lidos, gravados, pulados, erro, fim = execucao[0]
        print(
            f"  última execução: {scope} · {status} · lidos={lidos} gravados={gravados} "
            f"pulados={pulados} · fim={fim or '—'}"
        )
        if status != "completed":
            problemas.append(f"a última execução terminou como {status!r}: {erro or 'sem detalhe'}")
        if int(gravados or 0) <= 0:
            problemas.append(
                f"a última execução gravou {gravados} linha(s) de Batida — "
                f"leu {lidos} e pulou {pulados}. Ler sem gravar é correlação quebrada."
            )

    # 3 — o estado que o risco 1 produzia.
    orfas = consultar(
        "select count(*) from secullum.\"Batida\" b "
        "where b.\"Data\" >= current_date - interval '%d days' "
        "and not exists (select 1 from app.batida_marcacao m where m.batida_id = b.id)" % dias
    )
    quantas = int(orfas[0][0]) if orfas else 0
    print(f"  Batida sem nenhuma marcação nos últimos {dias} dia(s): {quantas}")
    if quantas:
        problemas.append(
            f"{quantas} 'Batida' sem nenhuma marcação na janela — é o estado que o motor "
            f"lê como 'não bateu ponto'. Confira se a escrita foi interrompida no meio."
        )

    if problemas:
        for p in problemas:
            print(f"  ✖ {p}")
        print("\n================================================")
        print(" A INGESTÃO NÃO PODE SER DADA COMO RELIGADA")
        print("================================================")
        sys.exit(1)

    print("\n================================================")
    print(" INGESTÃO RELIGADA: GRAVOU, E NADA FICOU PELA METADE")
    print("================================================")


if __name__ == "__main__":
    main()
