#!/usr/bin/env python3
"""
Verifica se todo objeto de banco citado na documentação existe de fato.

Documento que cita `app.colaborador_pi` (sem o segundo i) parece certo na
revisão e manda o desenvolvedor para uma tabela que não existe. Este script
transforma isso em erro de build.

    python3 scripts/verificar_docs.py
"""
import re, subprocess, os, sys, glob

ENV = {**os.environ,
       "PGHOST": os.environ.get("PGHOST", "/tmp"),
       "PGPORT": os.environ.get("PGPORT", "5433"),
       "PGUSER": os.environ.get("PGUSER", "postgres"),
       "PGDATABASE": os.environ.get("PGDATABASE", "operax_test")}


def q(sql):
    r = subprocess.run(["psql", "-tA", "-c", sql], capture_output=True, text=True, env=ENV)
    if r.returncode != 0:
        sys.exit(f"psql falhou:\n{r.stderr}")
    return {l.strip() for l in r.stdout.split("\n") if l.strip()}


relacoes = q("""
select n.nspname || '.' || c.relname
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname in ('app','secullum','util','public') and c.relkind in ('r','v','m','p');
""")
funcoes = q("""
select n.nspname || '.' || p.proname
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname in ('app','secullum','util','public');
""")
colunas = q("""
select c.relname || '.' || a.attname
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
join pg_attribute a on a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped
where n.nspname in ('app','secullum','util','public');
""")
tipos = q("""
select n.nspname || '.' || t.typname
from pg_type t join pg_namespace n on n.oid = t.typnamespace
where n.nspname in ('app','util');
""")

existentes = relacoes | funcoes | tipos
nomes_curtos = {r.split(".", 1)[1] for r in relacoes} | {f.split(".", 1)[1] for f in funcoes}

# Termos que aparecem em prosa e não são objeto de banco
IGNORAR = {
    "app.metrica.view_alvo",     # referência a coluna, coberta por `colunas`
    "public.vw_desvio_evento",   # checado como relação
}
PREFIXOS = ("app.", "secullum.", "util.", "public.")

DOCS = sorted(glob.glob("docs/*.md")) + ["CLAUDE.md"]

problemas = []
citados = set()

for doc in DOCS:
    if not os.path.exists(doc):
        continue
    if doc.endswith("DICIONARIO-DE-DADOS.md"):
        continue  # gerado do banco, não pode divergir
    texto = open(doc, encoding="utf-8").read()

    # Blocos de código cercados: é de onde alguém copia e cola, então valem
    # tanto quanto o que está em crase — ou mais.
    blocos = re.findall(r"```[a-z]*\n(.*?)```", texto, re.S)
    sem_blocos = re.sub(r"```[a-z]*\n.*?```", "", texto, flags=re.S)

    trechos = re.findall(r"`([^`\n]+)`", sem_blocos)
    for bloco in blocos:
        # nomes qualificados por schema dentro do código
        trechos += re.findall(r"\b((?:app|secullum|util|public)\.\w+(?:\.\w+)?)", bloco)
        # chamadas rpc('fn_x') e from('vw_x') do supabase-js
        trechos += re.findall(r"['\"]((?:vw|fn|mv)_\w+)['\"]", bloco)

    for trecho in trechos:
        t = trecho.strip().rstrip("()").rstrip(".,;:")

        # objeto qualificado por schema
        m = re.fullmatch(r"(app|secullum|util|public)\.([a-zA-Z_][a-zA-Z0-9_]*)", t)
        if m:
            citados.add(t)
            base = f"{m.group(1)}.{m.group(2)}"
            if base in existentes or base in IGNORAR:
                continue
            # pode ser coluna citada como schema.tabela.coluna? não neste padrão
            problemas.append((doc, t, "relação/função/tipo não existe"))
            continue

        # schema.tabela.coluna
        m = re.fullmatch(r"(app|secullum|util|public)\.([a-zA-Z_]\w*)\.([a-zA-Z_]\w*)", t)
        if m:
            citados.add(t)
            rel = f"{m.group(1)}.{m.group(2)}"
            col = f"{m.group(2)}.{m.group(3)}"
            if rel not in existentes:
                problemas.append((doc, t, "relação não existe"))
            elif col not in colunas:
                problemas.append((doc, t, f"coluna não existe em {rel}"))
            continue

        # view/rpc citada sem schema (vw_*, fn_*)
        if re.fullmatch(r"(vw|fn|mv)_\w+", t):
            citados.add(t)
            if t not in nomes_curtos:
                problemas.append((doc, t, "view/função não existe"))

print(f"Documentos verificados: {len([d for d in DOCS if os.path.exists(d) and not d.endswith('DICIONARIO-DE-DADOS.md')])}")
print(f"Identificadores de banco citados: {len(citados)}")

if problemas:
    print(f"\n❌ {len(problemas)} referência(s) quebrada(s):\n")
    for doc, termo, motivo in problemas:
        print(f"  {doc}: `{termo}` — {motivo}")
    sys.exit(1)

print("✅ Toda referência a objeto de banco na documentação existe no schema.")

# Aviso: objetos do schema que nenhum documento menciona
nao_citados = sorted(
    r for r in relacoes
    if r.split(".", 1)[0] == "app"
    and r not in citados
    and r.split(".", 1)[1] not in {c.split(".")[-1] for c in citados}
)
if nao_citados:
    print(f"\nℹ️  {len(nao_citados)} tabela(s) de `app` não citadas em nenhum documento "
          f"(esperado para tabelas de apoio):")
    print("   " + ", ".join(n.split(".", 1)[1] for n in nao_citados))
