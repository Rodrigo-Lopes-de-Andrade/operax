#!/usr/bin/env python3
"""Confere a matriz dono-do-campo contra o schema de verdade.

    python3 scripts/95_teste_matriz_rh.py

A matriz de `operax/rh/ownership.py` nomeia colunas de `app` e colunas do espelho
`secullum."Funcionario"`. Nome errado ali não quebra nada na hora: o template
simplesmente não trava a coluna que devia travar, e a tela mostra "Secullum ·
leitura de HH:MM" apontando para um campo que não existe. Falha silenciosa, do
tipo que só aparece quando alguém edita e o dado some.

Este teste existe porque foi exatamente o que aconteceu ao escrever a matriz:
quatro dos dezessete nomes de coluna do espelho estavam errados — `Cadastro` em
vez de `NumeroFolha`, `Departamento`/`Empresa` em vez das FKs uuid, e um
`TipoContrato` que não existe em lugar nenhum.
"""

import os
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from operax.rh.ownership import ENUMS, MATRIX, SEM_COLUNA, Owner  # noqa: E402

ENV = {
    **os.environ,
    "PGHOST": os.environ.get("PGHOST", "/tmp"),
    "PGPORT": os.environ.get("PGPORT", "5433"),
    "PGUSER": os.environ.get("PGUSER", "postgres"),
    "PGDATABASE": os.environ.get("PGDATABASE", "operax_test"),
}


def q(sql: str) -> set[str]:
    r = subprocess.run(["psql", "-tA", "-c", sql], capture_output=True, text=True, env=ENV)
    if r.returncode != 0:
        sys.exit(f"psql falhou:\n{r.stderr}")
    return {linha.strip() for linha in r.stdout.splitlines() if linha.strip()}


colunas_app = q("""
    select table_name || '.' || column_name
    from information_schema.columns where table_schema = 'app'
""")
colunas_espelho = q("""
    select 'Funcionario.' || a.attname
    from pg_attribute a
    where a.attrelid = 'secullum."Funcionario"'::regclass
      and a.attnum > 0 and not a.attisdropped
""")

problemas: list[str] = []

for f in MATRIX:
    if f"{f.table}.{f.column}" not in colunas_app:
        problemas.append(f"app.{f.table}.{f.column} não existe")
    if f.mirror and f.mirror not in colunas_espelho:
        problemas.append(f"{f.table}.{f.column} aponta para {f.mirror}, que não existe no espelho")
    # Campo pendente pode não ter espelho — é literalmente o que "pendente"
    # significa: ninguém confirmou se o Secullum sabe. Campo declarado sync sem
    # pendência, não: se ele é do sync, existe uma coluna de onde ele vem, e a
    # tela precisa citá-la.
    if f.owner is Owner.SYNC and not f.pending and f.mirror is None:
        problemas.append(f"{f.table}.{f.column} é sync sem origem declarada")

# Um campo não pode ser "sem coluna" e estar na matriz ao mesmo tempo: seria a
# lacuna escondida atrás da própria declaração dela.
for nome in SEM_COLUNA:
    if any(f.column == nome for f in MATRIX):
        problemas.append(f"{nome} está em SEM_COLUNA e na matriz ao mesmo tempo")


# Os enums copiados para o Python têm de ser exatamente o `check` do banco. Um
# valor a menos recusa linha boa no preview; um a mais deixa passar a linha que o
# banco vai rejeitar depois — e aí a recusa chega sem "erro na linha 43".
def valores_do_check(tabela: str, coluna: str) -> set[str] | None:
    defs = q(f"""
        select pg_get_constraintdef(oid) from pg_constraint
        where conrelid = 'app.{tabela}'::regclass and contype = 'c'
          and pg_get_constraintdef(oid) like '%({coluna} = ANY%'
    """)
    if not defs:
        return None
    return set(re.findall(r"'([a-z_]+)'::text", next(iter(defs))))


for (tabela, coluna), esperados in sorted(ENUMS.items()):
    reais = valores_do_check(tabela, coluna)
    if reais is None:
        problemas.append(f"app.{tabela}.{coluna} não tem check de enum no banco")
    elif reais != esperados:
        faltam = sorted(reais - esperados)
        sobram = sorted(esperados - reais)
        problemas.append(
            f"app.{tabela}.{coluna}: o banco aceita {faltam or '—'} que o código não, "
            f"e o código aceita {sobram or '—'} que o banco não"
        )

sync = sum(1 for f in MATRIX if f.owner is Owner.SYNC)
print(f"  matriz: {len(MATRIX)} campos ({sync} do sync, {len(MATRIX) - sync} do RH)")
print(f"  enums conferidos: {len(ENUMS)}")
print(f"  lacunas declaradas: {len(SEM_COLUNA)}")

if problemas:
    print("\n❌ " + f"{len(problemas)} problema(s):")
    for p in problemas:
        print(f"  {p}")
    sys.exit(1)

print("\n================================================")
print(" MATRIZ DONO-DO-CAMPO: TODOS OS NOMES EXISTEM")
print("================================================")
