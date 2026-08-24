#!/usr/bin/env python3
"""Confronta dois catálogos lidos por scripts/introspeccao_nuvem.py.

    python3 scripts/comparar_catalogos.py scripts/_ensaio.json scripts/_alvo_en.json

Igualdade aqui é a prova de que a migration de rename alcançou tudo: cada
espécie de objeto é comparada por nome, e o que sobra de um lado aparece
nomeado. Sai com código 1 quando diverge, para servir de gate."""

import json
import sys

if len(sys.argv) != 3:
    sys.exit(f"uso: {sys.argv[0]} <catalogo-a.json> <catalogo-b.json>")
ens = json.load(open(sys.argv[1]))
alv = json.load(open(sys.argv[2]))
DOM = ("app", "util", "public")
SYNC = {
    "batida_marcacao",
    "cursor_sincronizacao",
    "empresa_evento_status",
    "funcionario_evento_status",
}
# work_schedule_day so existe no alvo porque o stub simulado o cria em `public` e
# a migration 03 o move; producao nunca o teve. rls_auto_enable so existe na
# nuvem e a migration nao o toca, de proposito.
IGN_TAB = SYNC | {"work_schedule_day"}
IGN_FN = {("public", "rls_auto_enable")}


def conj(cat, chave, campos):
    return {
        tuple(r[c] for c in campos)
        for r in cat[chave]
        if r["schema"] in DOM
        and r.get("name") not in IGN_TAB
        and (r["schema"], r.get("name")) not in IGN_FN
    }


ok = True
print(f"{'espécie':<14} {'ensaio':>7} {'alvo':>7}")
for nome, chave, campos in (
    ("tabelas", "tables", ("schema", "name")),
    ("colunas", "columns", ("schema", "name", "column")),
    ("funcoes", "functions", ("schema", "name")),
    ("views", "views", ("schema", "name")),
    ("policies", "policies", ("schema", "name", "policy")),
    ("indices", "indexes", ("schema", "name", "index")),
    ("constraints", "constraints", ("schema", "name", "constraint")),
    ("triggers", "triggers", ("schema", "name", "trigger")),
    ("enums", "enums", ("schema", "name")),
):
    e, a = conj(ens, chave, campos), conj(alv, chave, campos)
    so_e, so_a = sorted(e - a), sorted(a - e)
    if so_e or so_a:
        ok = False
    print(f"{nome:<14} {len(e):>7} {len(a):>7}  {'✓' if not so_e and not so_a else '✗'}")
    for x in so_e[:10]:
        print(f"     só ensaio: {'.'.join(map(str, x))}")
    for x in so_a[:10]:
        print(f"     só alvo:   {'.'.join(map(str, x))}")

pe = {(r["schema"], r["name"]): r["labels"] for r in ens["enums"] if r["schema"] in DOM}
pa = {(r["schema"], r["name"]): r["labels"] for r in alv["enums"] if r["schema"] in DOM}
print("\nrótulos de enum:")
for k in sorted(set(pe) | set(pa)):
    igual = pe.get(k) == pa.get(k)
    ok = ok and igual
    print(f"  {'✓' if igual else '✗'} {'.'.join(k)}: {pe.get(k)}")

print("\n" + ("=== O ENSAIO FICOU IDÊNTICO AO ALVO ===" if ok else "=== ainda diverge ==="))
sys.exit(0 if ok else 1)
