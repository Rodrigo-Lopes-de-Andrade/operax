#!/usr/bin/env python3
"""Prova que a ingestão de batidas **voltou** — não que a função respondeu 200.

    python3 scripts/90_reconciliar_sync.py [--dias 2]

É o critério de "religou" da fase 3 da reconciliação. O §4b do
`docs/PLANO-RECONCILIACAO-NUVEM.md` explica por que ele precisa existir: a
invocação vem do pg_cron por `net.http_post`, e **o job registra sucesso por ter
entregado o POST**. Do lado do agendador, um 500 e um 200 são indistinguíveis.
Depois de uma janela de manutenção, "a função respondeu" não é resposta.

QUATRO AFIRMAÇÕES, E A ÚLTIMA É A QUE IMPORTA

1. **As duas entidades deixaram rastro.** `Batida` (a cada 15 min) e
   `Funcionario` (a cada 30). Conferir só uma delas deixa passar o modo de falha
   que o diário existe para pegar: entidade que nunca escreve não vira linha
   velha — **vira ausência**, e ausência não dispara alarme em lugar nenhum.
2. A última execução **terminada** de cada uma acabou como `completed`.
3. Ela gravou linha: `records_written > 0`. Uma execução que lê e não grava é o
   modo de falha do risco 3 — correlação quebrada respondendo sucesso.
4. **Nenhuma `Batida` na janela está sem marcação.** Esta é a que não se deduz do
   relatório: é o estado que o risco 1 produzia quando `upsertBatidas` commitava
   e a leitura seguinte falhava. Ele não se lê como "faltando dado" — o motor de
   detecção o lê como `no_punches`, "o colaborador não bateu ponto naquele dia",
   e emite indício contra uma pessoa que bateu.

O item 4 é verificado **contra o dado**, e não contra o summary, de propósito: um
resumo é o que o código achou que fez. A tabela é o que ficou.

⚠️ **`running` não é falha, e nem sempre é sucesso.** Desde a migration 34 a
Edge Function reivindica a linha antes de ler a origem, então a mais recente
pode estar legitimamente em andamento — rodar este script no segundo errado não
pode reprovar a janela. O que reprova é uma reivindicação **passada do lease**:
ela quer dizer que a função morreu no meio, e o reaper só a encerra quando a
próxima execução chegar. Ou seja, um lock preso é exatamente o sintoma de que a
próxima execução não chegou.

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


# As duas entidades que a sincronização escreve depois da troca de runner:
# `sync-batidas` grava 'Batida', `sync-cadastro' grava 'Funcionario' (uma linha
# por passada — ver docs/RUNBOOK-JANELA-CONVERGENCIA.md, passo 7, item 6).
ENTIDADES = ("Batida", "Funcionario")

# O lease da reivindicação, em minutos. A cópia que vale é a de
# `supabase/functions/_shared/sync-run.ts`; aqui ele só distingue "em andamento"
# de "morreu segurando o lock", e por isso uma divergência entre os dois erra
# para o lado barulhento, não para o silencioso.
LEASE_MIN = 10


def conferir_entidade(entidade: str) -> list[str]:
    """As afirmações 1 a 3, para uma entidade."""
    problemas: list[str] = []

    # A reivindicação viva ou presa vem primeiro: ela é o estado que não existia
    # antes do lock, e é o único que muda a leitura das linhas terminais.
    emandamento = consultar(
        "select coalesce(scope, ''), "
        "(extract(epoch from (now() - started_at)) / 60)::int "
        f"from app.sync_run where entity = '{entidade}' and status = 'running' "
        "order by started_at desc limit 1"
    )
    if emandamento:
        scope, idade = emandamento[0]
        if int(idade) > LEASE_MIN:
            problemas.append(
                f"{entidade}: uma execução ({scope}) está 'running' há {idade} min, "
                f"acima do lease de {LEASE_MIN}. Ela morreu segurando o lock — e o "
                f"reaper só a encerra quando a PRÓXIMA execução chegar, então isto "
                f"também diz que ela não chegou."
            )
        else:
            print(f"  {entidade}: execução {scope} em andamento há {idade} min (normal)")

    # As afirmações 2 e 3 olham a última execução TERMINADA: uma execução viva
    # ainda não tem veredito, e tratá-la como falha reprovaria a janela pelo
    # instante em que alguém rodou o script.
    execucao = consultar(
        "select status, scope, records_read, records_written, records_skipped, "
        "coalesce(error, ''), coalesce(finished_at::text, '') "
        f"from app.sync_run where entity = '{entidade}' and finished_at is not null "
        "order by finished_at desc limit 1"
    )
    if not execucao:
        problemas.append(
            f"app.sync_run não tem nenhuma execução terminada de {entidade!r} — a "
            f"sincronização nunca deixou rastro, ou a função ainda não roda com o "
            f"registro de execução. Ausência não vira linha velha: nenhum painel a lê."
        )
        return problemas

    status, scope, lidos, gravados, pulados, erro, fim = execucao[0]
    print(
        f"  {entidade}: última terminada {scope} · {status} · lidos={lidos} "
        f"gravados={gravados} pulados={pulados} · fim={fim or '—'}"
    )
    if status != "completed":
        problemas.append(
            f"{entidade}: a última execução terminou como {status!r}: {erro or 'sem detalhe'}"
        )
    if int(gravados or 0) <= 0:
        problemas.append(
            f"{entidade}: a última execução gravou {gravados} linha(s) — "
            f"leu {lidos} e pulou {pulados}. Ler sem gravar é correlação quebrada."
        )
    return problemas


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

    # 1 a 3 — as duas entidades, cada uma com o seu diário.
    for entidade in ENTIDADES:
        problemas.extend(conferir_entidade(entidade))

    # 4 — o estado que o risco 1 produzia.
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
