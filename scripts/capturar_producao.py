#!/usr/bin/env python3
"""
Captura datada do catálogo de produção, para que deriva vire diff no git.

    python3 scripts/capturar_producao.py nklobmlxyidqxarzisph --rotulo antes-das-onze
    python3 scripts/capturar_producao.py nklobmlxyidqxarzisph --rotulo depois-das-onze

**Por que este arquivo existe, e por que ele não é higiene.**

A verificação anterior comparava produção contra `scripts/_baseline.sql` e
`supabase/fixtures/espelho_secullum.sql`. Esses dois são *expectativa que se
atualiza para acompanhar produção*: quando a origem muda, alguém regenera a
captura e o teste volta a passar. Um teste cuja expectativa persegue a realidade
**não pode reprovar por divergência** — ele só reprova enquanto ninguém
regenerou. As seis colunas de foto que a outra equipe criou em 02/09/2026 não
aparecem em diff nenhum por exatamente esse motivo.

Aqui a expectativa é uma **captura anterior, datada e commitada**. A comparação é
captura contra captura, então a deriva deixa de ser um teste que passa e vira um
diff no git — **com data e autor**, que é o que responde "quando mudou e quem
mudou". Nenhum teste verde responde isso.

**E há um uso que não é rotina: cercar um `db push`.** Existem três event
triggers em `ddl_command_end` neste banco, e o primeiro na ordem alfabética
(`ensure_rls`, da outra equipe) não é nosso. Com ator não lido disparando durante
o push, o estado anterior é a **única** forma de atribuir o que aparecer depois:
sem ele não se separa o que a migration fez do que o gatilho deles fez. Depois do
push o "antes" só existe por reconstrução — que é justamente o que não vale
quando há terceiro no meio. Daí a ordem: capturar → push → capturar → diffar.

⛔ **Só lê catálogo.** Nenhuma consulta sai de `pg_catalog`/`information_schema`:
o alvo é um banco com dado de pessoa real. Quem acrescentar aqui uma leitura de
tabela de domínio está criando um bug de privacidade, não sendo prático.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CAPTURAS = RAIZ / "supabase" / "capturas"
GERADOR = RAIZ / "scripts" / "introspeccao_nuvem.py"

#: O cabeçalho do introspector carimba a hora da geração, o que faria toda
#: captura diferir da anterior por uma linha de ruído — e uma deriva falsa por
#: dia treina quem lê a ignorar. Fora da comparação, não do arquivo.
RUIDO = re.compile(r"^--\s*(gerado em|Gerado em|generated at)\b", re.I)


def corpo(texto: str) -> list[str]:
    return [linha for linha in texto.splitlines() if not RUIDO.match(linha)]


def capturas_de(ref: str) -> list[pathlib.Path]:
    destino = CAPTURAS / ref
    if not destino.is_dir():
        return []
    return sorted(destino.glob("*.sql"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ref", help="project ref do Supabase (ex.: nklobmlxyidqxarzisph)")
    p.add_argument("--rotulo", required=True, help="por que esta captura existe (ex.: antes-das-onze)")
    p.add_argument(
        "--gate",
        action="store_true",
        help="sai com código 1 se houver deriva contra a captura anterior — para cercar um db push",
    )
    args = p.parse_args(argv)

    anteriores = capturas_de(args.ref)
    destino = CAPTURAS / args.ref
    destino.mkdir(parents=True, exist_ok=True)

    carimbo = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H%M")
    rotulo = re.sub(r"[^a-z0-9-]+", "-", args.rotulo.lower()).strip("-")
    arquivo = destino / f"{carimbo}-{rotulo}.sql"

    print(f"capturando {args.ref} -> {arquivo.relative_to(RAIZ)}")
    r = subprocess.run(
        [sys.executable, str(GERADOR), args.ref, "--out", str(arquivo)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(r.stdout or "", file=sys.stderr)
        print(r.stderr or "", file=sys.stderr)
        return r.returncode
    print("  " + (r.stdout.strip().splitlines() or [""])[-1])

    if not anteriores:
        print("\nprimeira captura deste projeto — não há contra o que comparar.")
        print("commite este arquivo: é ele que vira a linha de base da próxima.")
        return 0

    anterior = anteriores[-1]
    a, b = corpo(anterior.read_text()), corpo(arquivo.read_text())
    delta = list(
        difflib.unified_diff(a, b, fromfile=anterior.name, tofile=arquivo.name, lineterm="", n=2)
    )

    if not delta:
        print(f"\nsem deriva contra {anterior.name} — o catálogo é o mesmo.")
        return 0

    add = sum(1 for x in delta if x.startswith("+") and not x.startswith("+++"))
    rem = sum(1 for x in delta if x.startswith("-") and not x.startswith("---"))
    print(f"\n⚠️  DERIVA contra {anterior.name}: +{add} / -{rem} linha(s)\n")
    print("\n".join(delta[:400]))
    if len(delta) > 400:
        print(f"\n… mais {len(delta) - 400} linha(s). Diff inteiro: git diff, depois de commitar.")

    print(
        "\nO que fazer com isto: o que estiver nas migrations deste repositório é obra nossa. "
        "O resto é de terceiro — e pelo docs/PLANO-RECONCILIACAO-NUVEM.md §3d é evento a "
        "escalar, não trabalho a absorver."
    )
    return 1 if args.gate else 0


if __name__ == "__main__":
    raise SystemExit(main())
