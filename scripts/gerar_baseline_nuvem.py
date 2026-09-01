#!/usr/bin/env python3
"""Monta o baseline real que `scripts/testar_migrations.sh` procura e nunca achou.

    python3 scripts/introspeccao_nuvem.py <ref> --json scripts/_producao.json --out /dev/null
    python3 scripts/gerar_baseline_nuvem.py scripts/_producao.json --out scripts/_baseline.sql

`testar_migrations.sh` usa `scripts/_baseline.sql` quando ele existe e cai no
`_test_stub_supabase.sql` quando não — e o próprio comentário de lá chama o stub
de "um palpite, não o schema real". O palpite diverge do real de forma que
importa: `secullum."Funcionario"` do stub tem `Id, Nome, Cpf, DataAdmissao`,
enquanto produção tem `id` uuid, `FuncionarioId`, `horario_id` e `Demissao`.
Sete tabelas do espelho não existem no stub, e o motor de jornada lê justamente
`Horario`, `HorarioDia` e `FuncionarioAfastamento`. Escrever o motor contra o
palpite seria escrever contra um schema que não existe em lugar nenhum.

O baseline reproduz o estado ANTERIOR à migration 00: o espelho ainda em
`public`, PascalCase, e as quatro tabelas da ingestão em `public` minúsculas.
Por isso ele omite, de propósito, o que as migrations 00 e 03 é que aplicam:

  • `tenant_id` e o índice dele — a 03 adiciona (`add column if not exists`).
  • RLS, FORCE e grants — a 00 e a 03 aplicam.
  • FK para `app.tenant` — `app` ainda não existe neste ponto.

Ele também NÃO cria `work_schedule_day`: o stub cria, produção nunca teve, e
nenhuma migration a referencia. A ausência é mais fiel que a presença.

Só catálogo é lido. Nenhuma linha de dado de pessoa entra aqui."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
STUB = RAIZ / "scripts" / "_test_stub_supabase.sql"

# As quatro da ingestão nascem em `public` minúsculas e a migration 03 as varre
# para `app`. Ficam nomeadas aqui porque `app` em produção tem 48 tabelas e só
# estas quatro são anteriores a este repositório.
INGESTAO = frozenset(
    {"batida_marcacao", "cursor_sincronizacao", "empresa_evento_status", "funcionario_evento_status"}
)
TENANT = "tenant_id"


def ident(nome: str) -> str:
    """Cita só o que precisa. `secullum` é PascalCase e sempre precisa."""
    return nome if nome.islower() and nome.replace("_", "").isalnum() else f'"{nome}"'


def plataforma() -> str:
    """A parte do stub que é plataforma: roles, `auth`, extensões.

    Cortada no primeiro `create table public.` — dali em diante o stub começa a
    adivinhar o espelho, e é exatamente isso que este baseline substitui."""
    texto = STUB.read_text()
    corte = texto.index("create table public.")
    return texto[:corte].rstrip() + "\n"


def tipo_da_coluna(col: dict) -> str:
    if col["data_type"] == "ARRAY":
        return col["udt_name"].lstrip("_") + "[]"
    if col["data_type"] == "USER-DEFINED":
        return f"{col['udt_schema']}.{ident(col['udt_name'])}"
    if col["maxlen"]:
        return f"{col['data_type']}({col['maxlen']})"
    if col["data_type"] == "numeric" and col["prec"]:
        return f"numeric({col['prec']},{col['scale']})"
    return col["data_type"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("catalogo", help="JSON de scripts/introspeccao_nuvem.py --json")
    p.add_argument("--out", default=None, help="arquivo .sql de saída")
    args = p.parse_args()
    cat = json.load(open(args.catalogo))

    # (schema, nome) -> nome que a tabela tem em `public` antes da migration 03
    alvo: dict[tuple[str, str], str] = {}
    fora_do_caminho: list[str] = []
    for t in cat["tables"]:
        if t["schema"] == "secullum":
            # A migration 03 varre de `public` para `secullum` só o que casa
            # `^[A-Z]`; o que é minúsculo ela manda para `app`. Uma tabela de
            # espelho em snake_case posta aqui acabaria no schema errado, o que
            # é pior que a ausência. Ela entra depois das migrations, pela
            # fixture — ver supabase/fixtures/espelho_secullum.sql.
            if not t["name"][:1].isupper():
                fora_do_caminho.append(t["name"])
                continue
            alvo[(t["schema"], t["name"])] = t["name"]
        elif t["schema"] == "app" and t["name"] in INGESTAO:
            alvo[(t["schema"], t["name"])] = t["name"]

    if fora_do_caminho:
        print(
            "espelho fora do caminho do baseline (snake_case, entram pela fixture): "
            + ", ".join(sorted(fora_do_caminho)),
            file=sys.stderr,
        )

    faltando = INGESTAO - {n for (s, n) in alvo if s == "app"}
    if faltando:
        print(f"aviso: ingestão ausente do catálogo: {sorted(faltando)}", file=sys.stderr)

    cols: dict[tuple[str, str], list[dict]] = {}
    for c in cat["columns"]:
        cols.setdefault((c["schema"], c["name"]), []).append(c)

    out: list[str] = [
        "-- " + "=" * 74,
        "-- Baseline REAL — o espelho como ele é em produção, antes da migration 00.",
        "-- GERADO por scripts/gerar_baseline_nuvem.py — não editar à mão.",
        "--",
        "-- Substitui scripts/_test_stub_supabase.sql em scripts/testar_migrations.sh.",
        "-- Sem tenant_id, sem RLS, sem grant: quem aplica isso são as migrations 00 e 03.",
        "-- " + "=" * 74,
        "",
        plataforma(),
        "",
        "-- O espelho do Secullum, ainda em `public` e PascalCase.",
    ]

    usuario_definido: list[str] = []
    for (schema, nome), publico in sorted(alvo.items(), key=lambda kv: kv[1]):
        linhas = []
        for col in cols.get((schema, nome), []):
            if col["column"] == TENANT:
                continue  # a migration 03 é quem adiciona
            t = tipo_da_coluna(col)
            if col["data_type"] == "USER-DEFINED":
                usuario_definido.append(f"{publico}.{col['column']} :: {t}")
            peca = f"  {ident(col['column'])} {t}"
            if col["is_identity"] == "YES":
                peca += f" generated {col['identity_generation'].lower()} as identity"
            elif col["column_default"]:
                peca += f" default {col['column_default']}"
            if col["is_nullable"] == "NO":
                peca += " not null"
            linhas.append(peca)
        if not linhas:
            continue
        out.append(f"create table if not exists public.{ident(publico)} (")
        out.append(",\n".join(linhas))
        out.append(");")
    out.append("")

    if usuario_definido:
        print(f"aviso: tipo definido pelo usuário no baseline: {usuario_definido}", file=sys.stderr)

    # PK e unique primeiro; FK depois, e só entre tabelas que este baseline cria.
    # `tenant_id` some junto com as constraints que o citam — inclusive a FK para
    # `app.tenant`, cujo schema ainda não existe aqui.
    out.append("-- constraints (as que a 03 recria ficam de fora)")
    nomes_publicos = set(alvo.values())
    for grupo in ("p", "u", "c", "x", "t", "f"):
        for r in cat["constraints"]:
            chave = (r["schema"], r["name"])
            if chave not in alvo:
                continue
            definicao = r["definition"]
            if TENANT in definicao:
                continue
            if grupo == "f":
                referida = re.search(r"REFERENCES (?:(\w+)\.)?\"?([A-Za-z_][\w]*)\"?", definicao)
                if not referida or referida.group(2) not in nomes_publicos:
                    continue
                definicao = re.sub(r"REFERENCES (?:\w+\.)?", "REFERENCES public.", definicao, count=1)
            if r["type"] != grupo:
                continue
            out.append(
                f"alter table public.{ident(alvo[chave])} "
                f"add constraint {ident(r['constraint'])} {definicao};"
            )
    out.append("")

    # `pg_indexes` lista também o índice que a constraint criou, e o de tenant
    # é da migration 03. Sobra o que o Secullum precisa para ler rápido.
    de_constraint = {(r["schema"], r["constraint"]) for r in cat["constraints"]}
    vistos: set[str] = set()
    out.append("-- índices")
    for r in cat["indexes"]:
        chave = (r["schema"], r["name"])
        if chave not in alvo or (r["schema"], r["index"]) in de_constraint:
            continue
        if TENANT in r["definition"] or r["index"].endswith("_tenant_idx"):
            continue
        if r["index"] in vistos:
            print(f"aviso: índice repetido ao juntar em public: {r['index']}", file=sys.stderr)
            continue
        vistos.add(r["index"])
        out.append(re.sub(r"\bON (?:secullum|app)\.", "ON public.", r["definition"], count=1) + ";")
    out.append("")

    out.append("-- comentários (é onde mora o que se aprendeu do payload do Secullum)")
    for r in cat["tables"]:
        chave = (r["schema"], r["name"])
        if chave in alvo and r["comment"]:
            c = r["comment"].replace("'", "''")
            out.append(f"comment on table public.{ident(alvo[chave])} is '{c}';")
    for r in cat["column_comments"]:
        chave = (r["schema"], r["name"])
        if chave in alvo and r["column"] != TENANT:
            c = r["comment"].replace("'", "''")
            out.append(
                f"comment on column public.{ident(alvo[chave])}.{ident(r['column'])} is '{c}';"
            )

    sql = "\n".join(out) + "\n"
    if args.out:
        pathlib.Path(args.out).write_text(sql)
        print(f"{args.out} gerado — {len(alvo)} tabelas do espelho, sem tenant_id e sem RLS")
    else:
        print(sql)


if __name__ == "__main__":
    main()
