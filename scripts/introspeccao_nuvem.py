#!/usr/bin/env python3
"""
Reconstrói o DDL de um projeto Supabase na nuvem, lendo só o catálogo.

Existe porque a senha do banco dos projetos na nuvem se perdeu e resetá-la num
projeto de cliente é ação com consequência. A Management API do Supabase executa
SQL com o token de conta do `supabase login` — o mesmo que o CLI já guarda em
`~/.supabase/access-token` — e isso basta para introspecção.

    python3 scripts/introspeccao_nuvem.py <project-ref> [--out scripts/_producao.sql]

**Lê apenas catálogo.** Nenhum `select` sai de `pg_catalog`/`information_schema`:
o alvo é um banco de produção com dado de pessoa real, e schema é a única coisa
que a reconciliação precisa. Se alguém adicionar aqui uma consulta que toca
tabela de domínio, é bug de privacidade, não descuido.

O que reconstrói: schemas, enums, tabelas com colunas e defaults, constraints,
índices, RLS e policies, funções, views, triggers e comentários. O que NÃO
reconstrói: grants por role, owners, sequences soltas e extensões — o baseline
não é backup, é o mapa contra o qual a migration de rename é escrita.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

SB_SQL = pathlib.Path(__file__).with_name("sb_sql.sh")
# Schemas do produto. Os do Supabase (auth, storage, realtime...) ficam de fora:
# são geridos pela plataforma e não entram numa migration nossa.
SCHEMAS = ("app", "secullum", "util", "public")


def q(ref: str, sql: str, opcional: bool = False) -> list[dict]:
    out = subprocess.run(
        [str(SB_SQL), ref, sql], capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        # Um projeto que nunca recebeu `db push` não tem
        # `supabase_migrations.schema_migrations`, e o endpoint responde 400.
        # Perder o histórico de migration não pode abortar a leitura do schema,
        # que é o motivo de o script existir — mas some em silêncio nunca:
        # o aviso vai para stderr.
        if opcional:
            print(f"aviso: consulta opcional falhou em {ref}", file=sys.stderr)
            return []
        sys.exit(f"falhou ao consultar {ref}: {out.stderr.strip()}")
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        sys.exit(f"resposta não é JSON: {out.stdout[:300]}")
    if isinstance(data, dict) and data.get("message"):
        sys.exit(f"API recusou: {data['message']}")
    return data


IN_SCHEMAS = "'" + "','".join(SCHEMAS) + "'"

# pg_get_*def faz o trabalho pesado: são as funções que o próprio pg_dump usa
# para reimprimir um objeto, então o texto sai canônico em vez de remontado.
QUERIES: dict[str, str] = {
    "enums": f"""
        select n.nspname as schema, t.typname as name,
               array_agg(e.enumlabel order by e.enumsortorder) as labels
        from pg_type t
        join pg_namespace n on n.oid = t.typnamespace
        join pg_enum e on e.enumtypid = t.oid
        where n.nspname in ({IN_SCHEMAS})
        group by 1, 2 order by 1, 2
    """,
    "tables": f"""
        select n.nspname as schema, c.relname as name, c.relkind as kind,
               c.relrowsecurity as rls, c.relforcerowsecurity as rls_forced,
               obj_description(c.oid) as comment
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname in ({IN_SCHEMAS}) and c.relkind in ('r','p','m')
        order by 1, 2
    """,
    "columns": f"""
        select table_schema as schema, table_name as name, column_name as column,
               ordinal_position as pos, data_type, udt_name,
               character_maximum_length as maxlen, numeric_precision as prec,
               numeric_scale as scale, is_nullable, column_default, is_identity
        from information_schema.columns
        where table_schema in ({IN_SCHEMAS})
        order by table_schema, table_name, ordinal_position
    """,
    "constraints": f"""
        select n.nspname as schema, rel.relname as name, con.conname as constraint,
               con.contype as type, pg_get_constraintdef(con.oid) as definition
        from pg_constraint con
        join pg_class rel on rel.oid = con.conrelid
        join pg_namespace n on n.oid = rel.relnamespace
        where n.nspname in ({IN_SCHEMAS})
        order by 1, 2, 3
    """,
    "indexes": f"""
        select schemaname as schema, tablename as name, indexname as index,
               indexdef as definition
        from pg_indexes where schemaname in ({IN_SCHEMAS})
        order by 1, 2, 3
    """,
    "policies": f"""
        select n.nspname as schema, c.relname as name, p.polname as policy,
               p.polcmd as command,
               (select array_agg(r.rolname) from pg_roles r
                 where r.oid = any(p.polroles)) as roles,
               pg_get_expr(p.polqual, p.polrelid) as using_expr,
               pg_get_expr(p.polwithcheck, p.polrelid) as check_expr
        from pg_policy p
        join pg_class c on c.oid = p.polrelid
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname in ({IN_SCHEMAS})
        order by 1, 2, 3
    """,
    "functions": f"""
        select n.nspname as schema, p.proname as name,
               pg_get_function_identity_arguments(p.oid) as args,
               pg_get_functiondef(p.oid) as definition,
               obj_description(p.oid) as comment
        from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname in ({IN_SCHEMAS}) and p.prokind in ('f','p')
        order by 1, 2, 3
    """,
    "views": f"""
        select n.nspname as schema, c.relname as name,
               pg_get_viewdef(c.oid, true) as definition,
               c.reloptions as options, obj_description(c.oid) as comment
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname in ({IN_SCHEMAS}) and c.relkind in ('v','m')
        order by 1, 2
    """,
    "triggers": f"""
        select n.nspname as schema, c.relname as name, t.tgname as trigger,
               pg_get_triggerdef(t.oid) as definition
        from pg_trigger t
        join pg_class c on c.oid = t.tgrelid
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname in ({IN_SCHEMAS}) and not t.tgisinternal
        order by 1, 2, 3
    """,
    "column_comments": f"""
        select n.nspname as schema, c.relname as name, a.attname as column,
               col_description(c.oid, a.attnum) as comment
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        join pg_attribute a on a.attrelid = c.oid and a.attnum > 0
        where n.nspname in ({IN_SCHEMAS})
          and col_description(c.oid, a.attnum) is not null
        order by 1, 2, 3
    """,
    "migrations": """
        select version, name from supabase_migrations.schema_migrations
        order by version
    """,
}


# O histórico de migration é contexto, não schema: um projeto vazio não o tem.
OPCIONAIS = frozenset({"migrations"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ref", help="project ref do Supabase")
    parser.add_argument("--out", default=None, help="arquivo .sql de saída")
    parser.add_argument("--json", default=None, help="também grava o catálogo cru")
    args = parser.parse_args()

    catalog = {
        name: q(args.ref, sql, opcional=name in OPCIONAIS)
        for name, sql in QUERIES.items()
    }

    if args.json:
        pathlib.Path(args.json).write_text(
            json.dumps(catalog, indent=2, ensure_ascii=False, sort_keys=True)
        )

    sql = render(args.ref, catalog)
    if args.out:
        pathlib.Path(args.out).write_text(sql)
        print(f"{args.out} gerado — " + summary(catalog))
    else:
        print(sql)


def summary(cat: dict) -> str:
    return ", ".join(f"{len(rows)} {name}" for name, rows in cat.items())


def ident(name: str) -> str:
    """Cita só o que precisa. `secullum` é PascalCase e sempre precisa."""
    return name if name.islower() and name.replace("_", "").isalnum() else f'"{name}"'


COMMAND = {"r": "select", "a": "insert", "w": "update", "d": "delete", "*": "all"}


def render(ref: str, cat: dict) -> str:
    out: list[str] = [
        "-- " + "=" * 74,
        f"-- Schema do projeto Supabase {ref}, reconstruído do catálogo.",
        "-- GERADO por scripts/introspeccao_nuvem.py — não editar à mão.",
        "--",
        "-- Só catálogo foi lido: nenhuma linha de dado de cliente entrou aqui.",
        "-- Não é backup. É o mapa contra o qual a migration de rename é escrita.",
        "-- " + "=" * 74,
        "",
        "-- Histórico de migration aplicado neste projeto:",
    ]
    for row in cat["migrations"]:
        out.append(f"--   {row['version']}  {row.get('name') or ''}")
    out.append("")

    schemas = {r["schema"] for r in cat["tables"]} | {r["schema"] for r in cat["views"]}
    for schema in sorted(schemas):
        out.append(f"create schema if not exists {schema};")
    out.append("")

    for row in cat["enums"]:
        labels = ", ".join(f"'{v}'" for v in row["labels"])
        out.append(f"create type {row['schema']}.{ident(row['name'])} as enum ({labels});")
    out.append("")

    cols_by: dict[tuple, list] = {}
    for row in cat["columns"]:
        cols_by.setdefault((row["schema"], row["name"]), []).append(row)

    for tbl in cat["tables"]:
        key = (tbl["schema"], tbl["name"])
        cols = cols_by.get(key, [])
        if not cols:
            continue
        out.append(f"create table if not exists {tbl['schema']}.{ident(tbl['name'])} (")
        lines = []
        for col in cols:
            t = col["udt_name"]
            if col["data_type"] == "ARRAY":
                t = t.lstrip("_") + "[]"
            elif col["data_type"] == "USER-DEFINED":
                t = col["udt_name"]
            elif col["maxlen"]:
                t = f"{col['data_type']}({col['maxlen']})"
            elif col["data_type"] == "numeric" and col["prec"]:
                t = f"numeric({col['prec']},{col['scale']})"
            else:
                t = col["data_type"]
            piece = f"  {ident(col['column'])} {t}"
            if col["column_default"]:
                piece += f" default {col['column_default']}"
            if col["is_nullable"] == "NO":
                piece += " not null"
            lines.append(piece)
        out.append(",\n".join(lines))
        out.append(");")
        if tbl["rls"]:
            alvo = f"{tbl['schema']}.{ident(tbl['name'])}"
            out.append(f"alter table {alvo} enable row level security;")
        if tbl["comment"]:
            c = tbl["comment"].replace("'", "''")
            alvo = f"{tbl['schema']}.{ident(tbl['name'])}"
            out.append(f"comment on table {alvo} is '{c}';")
        out.append("")

    out.append("-- constraints")
    for row in cat["constraints"]:
        if row["type"] == "p" and "PRIMARY KEY" in (row["definition"] or ""):
            pass  # a PK vem junto do create table em pg_dump; aqui vai como alter
        out.append(
            f"alter table {row['schema']}.{ident(row['name'])} "
            f"add constraint {ident(row['constraint'])} {row['definition']};"
        )
    out.append("")

    out.append("-- índices")
    for row in cat["indexes"]:
        out.append(row["definition"] + ";")
    out.append("")

    out.append("-- funções")
    for row in cat["functions"]:
        out.append(row["definition"].rstrip().rstrip(";") + ";")
        if row["comment"]:
            c = row["comment"].replace("'", "''")
            alvo = f"{row['schema']}.{ident(row['name'])}({row['args']})"
            out.append(f"comment on function {alvo} is '{c}';")
    out.append("")

    out.append("-- views")
    for row in cat["views"]:
        opts = ""
        if row["options"]:
            opts = " with (" + ", ".join(row["options"]) + ")"
        out.append(
            f"create or replace view {row['schema']}.{ident(row['name'])}{opts} as\n"
            + row["definition"].rstrip().rstrip(";") + ";"
        )
    out.append("")

    out.append("-- policies")
    for row in cat["policies"]:
        cmd = COMMAND[row["command"]]
        roles = ", ".join(row["roles"] or ["public"])
        piece = (
            f"create policy {ident(row['policy'])} on {row['schema']}.{ident(row['name'])}\n"
            f"  for {cmd} to {roles}"
        )
        if row["using_expr"]:
            piece += f"\n  using ({row['using_expr']})"
        if row["check_expr"]:
            piece += f"\n  with check ({row['check_expr']})"
        out.append(piece + ";")
    out.append("")

    out.append("-- triggers")
    for row in cat["triggers"]:
        out.append(row["definition"] + ";")
    out.append("")

    out.append("-- comentários de coluna")
    for row in cat["column_comments"]:
        c = row["comment"].replace("'", "''")
        alvo = f"{row['schema']}.{ident(row['name'])}.{ident(row['column'])}"
        out.append(f"comment on column {alvo} is '{c}';")

    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
