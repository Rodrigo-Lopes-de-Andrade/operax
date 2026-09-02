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
4. **A janela não perdeu marcação em massa.** Esta é a que não se deduz do
   relatório: é o estado que o risco 1 produzia quando `upsertBatidas` commitava
   e a leitura seguinte falhava. Ele não se lê como "faltando dado" — o motor de
   detecção o lê como `no_punches`, "o colaborador não bateu ponto naquele dia",
   e emite indício contra uma pessoa que bateu.

O item 4 é verificado **contra o dado**, e não contra o summary, de propósito: um
resumo é o que o código achou que fez. A tabela é o que ficou.

⛔ **A primeira versão dele afirmava "NENHUMA `Batida` sem marcação", e isso é
falso em produção saudável.** Medido em 02/09/2026, na primeira vez que este
script correu contra produção: 18 órfãs em 2 dias, todas de **seis supervisores**
no horário 4401 ("U-000 - Seg a Sex - 08:00h ás 18:00h (Supervisão)"), ativos e
sem demissão — cinco deles nunca tiveram marcação nenhuma. O Secullum emite a
linha-dia para quem não bate ponto. Em 14 dias a taxa de órfãs é **26,7%**, contra
7,8% na janela: "batida sem marcação" é o normal, não a exceção.

Então a afirmação passou a ser **comparativa e auto-calibrada**: reprova quando a
taxa da janela é ao menos o dobro da taxa dos 14 dias anteriores E passa de
metade. Fim de semana, folga e supervisor entram nos dois lados da conta e se
cancelam; uma escrita interrompida não — ela empurra a janela para perto de 100%
sem tocar na referência.

⚠️ **O que ele deixa de pegar, dito de frente:** um punhado de marcações perdidas
não muda taxa e passa. Quem impede esse caso é a transação em
`SupabaseBatidaRepository.transaction`, não este script. Um portão que reprova
produção saudável às 2h da manhã não é mais rigoroso — é ignorado.

⚠️ **`running` não é falha, e nem sempre é sucesso.** Desde a migration 34 a
Edge Function reivindica a linha antes de ler a origem, então a mais recente
pode estar legitimamente em andamento — rodar este script no segundo errado não
pode reprovar a janela. O que reprova é uma reivindicação **passada do lease**:
ela quer dizer que a função morreu no meio, e o reaper só a encerra quando a
próxima execução chegar. Ou seja, um lock preso é exatamente o sintoma de que a
próxima execução não chegou.

ONDE ELE OLHA — E POR QUE ISSO PRECISOU DE UM ARGUMENTO

    python3 scripts/90_reconciliar_sync.py --ref nklobmlxyidqxarzisph   # produção
    python3 scripts/90_reconciliar_sync.py                             # banco local

⛔ Até 02/09/2026 só existia o caminho local, por `psql`, com o padrão apontando
para `operax_test` — o banco descartável da suíte. Mas **não há caminho psql para
produção neste repositório**: todo o resto do runbook chega lá pelo
`scripts/sb_sql.sh`, que usa a Management API. Rodado no passo 7 numa máquina de
desenvolvimento, este script conferiria o banco de teste e imprimiria
"INGESTÃO RELIGADA" — um verde sobre a base errada, que é a mesma patologia que
ele existe para pegar.

Por isso o alvo é impresso como primeira linha, sempre. Um portão que não diz o
que olhou não é portão.

Sai com código 1 em qualquer falha, para servir de portão num roteiro de
manutenção.
"""

from __future__ import annotations

import argparse
import json
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


# Preenchido por `main()`. `None` = banco local por psql.
REF: str | None = None


def consultar(sql: str) -> list[list[str]]:
    return _pela_api(sql) if REF else _pelo_psql(sql)


def _pelo_psql(sql: str) -> list[list[str]]:
    r = subprocess.run(
        ["psql", "-tAF\t", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True,
        text=True,
        env=ENV,
    )
    if r.returncode != 0:
        sys.exit(f"psql falhou:\n{r.stderr}")
    return [linha.split("\t") for linha in r.stdout.split("\n") if linha.strip()]


def _pela_api(sql: str) -> list[list[str]]:
    """A mesma porta que o resto do runbook usa para produção.

    `sb_sql.sh` devolve um array de objetos JSON. As chaves vêm na ordem do
    `select`, e é essa ordem que os chamadores desempacotam — igual ao `-tA` do
    psql. Nulo vira string vazia pelo mesmo motivo: as consultas daqui já
    aplicam `coalesce` onde o vazio tem significado.
    """
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run(
        [os.path.join(raiz, "scripts", "sb_sql.sh"), str(REF), sql],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        sys.exit(f"sb_sql.sh falhou:\n{r.stderr or r.stdout}")
    try:
        linhas = json.loads(r.stdout)
    except json.JSONDecodeError:
        sys.exit(f"resposta da Management API não é JSON:\n{r.stdout[:400]}")
    return [["" if v is None else str(v) for v in linha.values()] for linha in linhas]


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


# Referência com que a janela é comparada. Catorze dias cobrem dois fins de
# semana, que é o que faz a taxa de órfãs oscilar — abaixo disso a referência
# vira ruído em vez de linha de base.
REFERENCIA_DIAS = 14


def conferir_marcacoes_perdidas(dias: int) -> list[str]:
    """A afirmação 4: a janela não perdeu marcação em massa."""
    linhas = consultar(
        "with d as ("
        '  select b.id, b."Data"::date as dia,'
        "         exists (select 1 from app.batida_marcacao m where m.batida_id = b.id) as tem"
        '    from secullum."Batida" b'
        f"   where b.\"Data\" >= current_date - interval '{dias + REFERENCIA_DIAS} days'"
        ") select"
        f"   count(*) filter (where dia >= current_date - interval '{dias} days') as janela,"
        f"   count(*) filter (where dia >= current_date - interval '{dias} days' and not tem) as janela_sem,"
        f"   count(*) filter (where dia <  current_date - interval '{dias} days') as ref,"
        f"   count(*) filter (where dia <  current_date - interval '{dias} days' and not tem) as ref_sem"
        "  from d"
    )
    janela, janela_sem, ref, ref_sem = (int(v or 0) for v in linhas[0])

    if not janela:
        print(f"  Batida na janela de {dias} dia(s): nenhuma")
        return [
            f"nenhuma 'Batida' nos últimos {dias} dia(s) — a ingestão não trouxe nada, "
            f"e as afirmações acima podem estar olhando uma execução antiga."
        ]

    taxa = 100.0 * janela_sem / janela
    taxa_ref = (100.0 * ref_sem / ref) if ref else 0.0
    print(
        f"  Batida sem marcação: {janela_sem}/{janela} na janela ({taxa:.1f}%) "
        f"· {ref_sem}/{ref} nos {REFERENCIA_DIAS} dias anteriores ({taxa_ref:.1f}%)"
    )

    # Metade é o piso: abaixo disso o número não se distingue de gente que não
    # bateu ponto — em produção a referência mede 26,7%. O dobro é o detector de
    # degrau: folga, fim de semana e supervisor entram nos dois lados da conta.
    if taxa > 50.0 and taxa >= 2 * taxa_ref:
        return [
            f"{janela_sem} de {janela} 'Batida' na janela estão sem marcação "
            f"({taxa:.1f}%), contra {taxa_ref:.1f}% nos {REFERENCIA_DIAS} dias anteriores. "
            f"Um degrau desse tamanho não é gente que não bateu ponto — é escrita "
            f"interrompida no meio, o estado que o motor lê como 'não bateu'."
        ]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dias",
        type=int,
        default=2,
        help="Janela conferida, em dias antes de hoje (padrão 2 — a janela incremental).",
    )
    parser.add_argument(
        "--ref",
        default=None,
        help=(
            "Project ref do Supabase. Com ele, a leitura vai pela Management API "
            "(scripts/sb_sql.sh) — o único caminho deste repositório até produção. "
            "Sem ele, psql no banco apontado por PGHOST/PGPORT/PGDATABASE."
        ),
    )
    args = parser.parse_args()
    dias = args.dias

    global REF
    REF = args.ref
    # Primeira linha, sempre: um portão que não diz o que olhou não é portão. Foi
    # o padrão silencioso apontando para `operax_test` que tornou isto necessário.
    if REF:
        print(f"  alvo: Management API · projeto {REF}")
    else:
        print(f"  alvo: psql · {ENV['PGHOST']}:{ENV['PGPORT']}/{ENV['PGDATABASE']}")

    problemas: list[str] = []

    # 1 a 3 — as duas entidades, cada uma com o seu diário.
    for entidade in ENTIDADES:
        problemas.extend(conferir_entidade(entidade))

    # 4 — o estado que o risco 1 produzia, medido contra a própria base.
    problemas.extend(conferir_marcacoes_perdidas(dias))

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
