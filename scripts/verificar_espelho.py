#!/usr/bin/env python3
"""
Confere se o espelho do Secullum que se tem à mão é o que produção tem.

    python3 scripts/verificar_espelho.py nklobmlxyidqxarzisph
        Produção contra `supabase/fixtures/espelho_secullum.sql`. Precisa de rede
        e do token de conta. Rode antes de marcar uma janela.

    python3 scripts/verificar_espelho.py operax_test --psql --somente-tabelas
        O banco do ensaio contra a mesma fixture. Sem rede. É o que a suíte roda.

As 22 tabelas de `secullum` são desenho da outra equipe: nenhuma migration deste
repositório as cria. Vinte delas chegam ao ensaio por `scripts/_baseline.sql`, e
duas — as snake_case — pela fixture, porque a migration 03 só varre para
`secullum` o que casa `^[A-Z]`.

**Por que isto existe:** em 01/09/2026 o baseline do ensaio estava três linhas
atrás de produção, e as três eram `Estrutura.departamento_id` — a coluna que a
`sync-cadastro` deste repositório grava e que produção não tem mais. O ensaio
não deixou de pegar por não existir; deixou de pegar por estar velho, e nada
tocava. Ver docs/RUNBOOK-JANELA-CONVERGENCIA.md §3b.

Só lê catálogo, pela mesma Management API do scripts/sb_sql.sh.
"""

from __future__ import annotations

import argparse
import difflib
import pathlib
import subprocess
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = RAIZ / "supabase" / "fixtures" / "espelho_secullum.sql"
GERADOR = RAIZ / "scripts" / "introspeccao_nuvem.py"


def corpo(sql: str, somente_tabelas: bool) -> list[str]:
    """O DDL comparável, sem o que muda por motivo que não é deriva do espelho.

    Fora sempre: comentário do gerador. O cabeçalho carrega o histórico de
    migrations do projeto, que muda toda vez que produção ganha uma — compará-lo
    faria o verificador acusar deriva quando o que mudou foi outra coisa, e um
    alarme que toca sozinho é um alarme que ninguém lê. `comment on ...` é DDL de
    verdade e continua sendo comparado.

    Com `--somente-tabelas`, fora também: tudo que não é bloco de `create table`,
    e a coluna `tenant_id`. No ensaio quem põe constraint, índice, RLS e grant no
    espelho é a migration 03, com o uuid de tenant local — divergir dali é o
    esperado, não deriva. O que precisa bater é a forma da tabela.
    """
    linhas = [ln.rstrip() for ln in sql.splitlines() if ln.strip() and not ln.startswith("--")]
    if not somente_tabelas:
        return linhas

    blocos: list[str] = []
    dentro = False
    for ln in linhas:
        if ln.startswith("create table if not exists secullum."):
            dentro = True
            blocos.append(ln)
        elif dentro:
            if ln.startswith("  tenant_id "):
                continue
            if ln.startswith(");") and blocos and blocos[-1].endswith(","):
                # `tenant_id` saiu da lista, e se ele era a ÚLTIMA coluna a
                # anterior fica com vírgula pendurada. Isso não é deriva: é onde
                # cada lado pôs a coluna. Em produção ela entrou no meio; no
                # ensaio a migration 03 a acrescenta no fim, depois do que o
                # baseline criou. Sem esta normalização, uma coluna nova em
                # produção **depois** de `tenant_id` acusa deriva para sempre —
                # foi o que aconteceu em 02/09/2026 com as colunas de foto.
                blocos[-1] = blocos[-1][:-1]
            blocos.append(ln)
            if ln.startswith(");"):
                dentro = False
    return blocos


def capturar(alvo: str, psql: bool) -> str:
    with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tmp:
        destino = pathlib.Path(tmp.name)
    try:
        cmd = [sys.executable, str(GERADOR), alvo, "--only", "secullum", "--out", str(destino)]
        if psql:
            cmd.append("--psql")
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        return destino.read_text()
    finally:
        destino.unlink(missing_ok=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("alvo", help="project ref do Supabase, ou dbname com --psql")
    p.add_argument("--psql", action="store_true", help="alvo é um Postgres local")
    p.add_argument(
        "--somente-tabelas",
        action="store_true",
        help="compara só a forma das tabelas (o que a 03 aplica no ensaio fica de fora)",
    )
    args = p.parse_args()

    if not FIXTURE.exists():
        sys.exit(f"fixture ausente: {FIXTURE.relative_to(RAIZ)}")

    atual = corpo(capturar(args.alvo, args.psql), args.somente_tabelas)
    esperado = corpo(FIXTURE.read_text(), args.somente_tabelas)

    escopo = "a forma das tabelas" if args.somente_tabelas else "o DDL"
    if atual == esperado:
        print(f"OK: {escopo} do espelho em {args.alvo} confere ({len(esperado)} linhas).")
        return

    print(
        "\n".join(
            difflib.unified_diff(
                esperado,
                atual,
                fromfile="fixture (produção capturada)",
                tofile=f"espelho em {args.alvo}",
                lineterm="",
            )
        )
    )
    if args.psql:
        rumo = (
            "O espelho do ensaio não é o de produção. Se produção é quem mudou, regenere\n"
            "a captura e o baseline, nesta ordem:\n"
            "  python3 scripts/introspeccao_nuvem.py <ref> --json scripts/_producao.json --out scripts/_producao.sql\n"
            "  python3 scripts/introspeccao_nuvem.py <ref> --only secullum --out supabase/fixtures/espelho_secullum.sql\n"
            "  python3 scripts/gerar_baseline_nuvem.py scripts/_producao.json --out scripts/_baseline.sql"
        )
    else:
        rumo = (
            "O espelho de produção mudou. Leia o diff antes de confiar em qualquer ensaio,\n"
            "e então regenere a fixture:\n"
            f"  python3 scripts/introspeccao_nuvem.py {args.alvo} --only secullum \\\n"
            "      --out supabase/fixtures/espelho_secullum.sql"
        )
    print("\n" + rumo, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
