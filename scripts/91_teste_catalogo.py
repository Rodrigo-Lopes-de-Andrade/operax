#!/usr/bin/env python3
"""Prova o catálogo do assistente contra o schema — e o mapa contra o catálogo.

    python3 scripts/91_teste_catalogo.py

Duas listas precisam concordar e vivem em lugares diferentes de propósito:
`app.metric` diz **o que** cada métrica aceita (dado, editável com uma migration)
e `catalogo.BINDINGS` diz **como** cada parâmetro alcança o alvo (código, porque
é o único ponto em que um nome de coluna encosta em SQL). Este teste é o contrato
entre as duas.

Três coisas conferidas:
  1. todo alvo de `app.metric` existe em `public` — view ou função;
  2. todo parâmetro declarado no catálogo tem binding e tipo, e toda coluna
     citada pelo binding existe no alvo;
  3. a consulta que cada métrica gera **compila** contra o schema real.

`operax/agente/catalogo.py` não importa driver nenhum, então este script o importa
direto em vez de ler o arquivo como texto.
"""

import os
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))
from operax.agente import catalogo  # noqa: E402

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


def posicionar(sql: str) -> str:
    ordem: list[str] = []

    def trocar(m: re.Match) -> str:
        if m.group(1) not in ordem:
            ordem.append(m.group(1))
        return f"${ordem.index(m.group(1)) + 1}"

    return re.sub(r"%\((\w+)\)s", trocar, sql)


#: O tipo de cada parâmetro, para o `prepare` inferir (um `$1` sozinho num `where`
#: de uuid é ambíguo). Vive em `catalogo.TYPES` e não aqui porque o runtime passou
#: a precisar do mesmo mapa para recusar valor inventado pelo modelo — duas
#: cópias divergiriam na primeira métrica nova, e é esse tipo de divergência que
#: este script existe para achar.
TIPOS = catalogo.TYPES


def main() -> None:
    problemas: list[str] = []

    linhas = consultar(
        "select code, title, description, target_view, "
        "coalesce(array_to_string(dimensions, ','), ''), "
        "coalesce(array_to_string(filters, ','), ''), coalesce(domain::text, '') "
        "from app.metric where active order by code"
    )
    metrics = tuple(
        catalogo.Metric(
            code=c,
            title=t,
            description=d,
            target=alvo,
            dimensions=tuple(x for x in dims.split(",") if x),
            filters=tuple(x for x in filt.split(",") if x),
            domain=dom or None,
        )
        for c, t, d, alvo, dims, filt, dom in linhas
    )
    if not metrics:
        sys.exit("app.metric está vazia: o assistente não teria o que responder")

    colunas = {
        nome: set(cols.split(","))
        for nome, cols in consultar(
            "select c.relname, string_agg(a.attname, ',') from pg_class c "
            "join pg_namespace n on n.oid = c.relnamespace "
            "join pg_attribute a on a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped "
            "where n.nspname = 'public' and c.relkind in ('v','m','r') group by 1"
        )
    }
    funcoes = {nome for (nome,) in consultar(
        "select distinct p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'public'"
    )}

    for m in metrics:
        # 1. o alvo existe
        if m.kind == "function":
            if m.target not in funcoes:
                problemas.append(f"{m.code}: a função public.{m.target} não existe")
                continue
        elif m.target not in colunas:
            problemas.append(f"{m.code}: a view public.{m.target} não existe")
            continue

        # 2. todo parâmetro tem binding, e toda coluna citada existe
        mapa = catalogo.BINDINGS.get(m.target)
        if mapa is None:
            problemas.append(f"{m.code}: o alvo {m.target} não tem binding declarado")
            continue
        for parametro in sorted(m.accepted):
            binding = mapa.get(parametro)
            if binding is None:
                problemas.append(
                    f"{m.code}: o catálogo aceita {parametro!r} e BINDINGS não sabe onde ligá-lo"
                )
                continue
            if binding.column and binding.column not in colunas.get(m.target, set()):
                problemas.append(
                    f"{m.code}: binding de {parametro!r} aponta para {m.target}.{binding.column}, "
                    f"que não existe"
                )
            if parametro not in TIPOS:
                problemas.append(
                    f"{m.code}: o catálogo aceita {parametro!r} e TYPES não diz de que tipo ele é"
                )

        # 3. a consulta compila
        parametros = {p: None for p in sorted(m.accepted)}
        query = catalogo.build(catalogo.Choice(metric=m, parameters=parametros))
        sql = posicionar(query.sql)
        for indice, nome in enumerate(sorted(query.parameters), start=1):
            sql = sql.replace(f"${indice}", f"${indice}::{TIPOS.get(nome, 'text')}")
        r = subprocess.run(
            ["psql", "-q", "-v", "ON_ERROR_STOP=1", "-c", f"prepare p as {sql}"],
            capture_output=True,
            text=True,
            env=ENV,
        )
        if r.returncode != 0:
            problemas.append(f"{m.code}: a consulta não compila: {r.stderr.strip().splitlines()[0]}")

    # 4. nenhum binding sobra apontando para alvo que ninguém usa
    alvos = {m.target for m in metrics}
    for alvo in sorted(set(catalogo.BINDINGS) - alvos):
        problemas.append(f"BINDINGS declara {alvo!r} e nenhuma métrica ativa aponta para ele")

    if problemas:
        for p in problemas:
            print(f"  ✖ {p}")
        sys.exit(1)

    sensiveis = [m.code for m in metrics if m.domain]
    print(f"  métricas ativas: {len(metrics)} ({len(sensiveis)} em domínio sensível)")
    print("\n================================================")
    print(" CATÁLOGO DO ASSISTENTE: TODOS OS TESTES OK")
    print("================================================")


if __name__ == "__main__":
    main()
