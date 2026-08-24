#!/usr/bin/env python3
"""Confere se uma cópia do schema é fiel à origem, campo a campo.

    python3 scripts/conferir_copia.py scripts/_producao.json scripts/_stg_antes.json

Diferente de `comparar_catalogos.py`, que pergunta "o rename alcançou tudo?" e
compara nomes dentro de `app`/`util`/`public`, este pergunta "a cópia é a origem?"
e compara **todo campo de todo registro em todo schema**, `secullum` incluído.

Existe porque a comparação por nome deixou passar três coisas de uma vez:
FORCE ROW LEVEL SECURITY em 20 tabelas, o privilégio MAINTAIN do PG17, e lacunas
de attnum. As duas primeiras eram fronteira de segurança.

Diferença de `migrations` é esperada: uma cópia montada por DDL não herda o
histórico da origem. Sai com código 1 no resto."""

import json
import sys

if len(sys.argv) != 3:
    sys.exit(f"uso: {sys.argv[0]} <origem.json> <copia.json>")
ORIG, COPIA = sys.argv[1], sys.argv[2]
a, b = json.load(open(ORIG)), json.load(open(COPIA))

# `pos` é o attnum, e ele guarda a lacuna deixada por uma coluna derrubada na
# origem. Uma cópia recriada do zero renumera; isso não muda nada que o produto
# leia, então a coluna entra na comparação sem a posição.
IGNORA_CAMPO = {"columns": {"pos"}}

ok = True
print(f"{'espécie':<18} {'origem':>7} {'cópia':>7}")
for especie in sorted(set(a) | set(b)):
    if especie == "migrations":
        continue
    fora = IGNORA_CAMPO.get(especie, set())

    def chave(r, fora=fora):
        return json.dumps(
            {k: v for k, v in r.items() if k not in fora}, sort_keys=True, ensure_ascii=False
        )

    sa = {chave(r) for r in a.get(especie, [])}
    sb = {chave(r) for r in b.get(especie, [])}
    so_a, so_b = sorted(sa - sb), sorted(sb - sa)
    if so_a or so_b:
        ok = False
    print(f"{especie:<18} {len(sa):>7} {len(sb):>7}  {'✓' if not so_a and not so_b else '✗'}")
    for x in so_a[:8]:
        print(f"     só origem: {x[:220]}")
    for x in so_b[:8]:
        print(f"     só cópia : {x[:220]}")

ma, mb = len(a.get("migrations", [])), len(b.get("migrations", []))
print(f"\nhistórico de migration: origem {ma}, cópia {mb} (divergir aqui é esperado)")
print("\n" + ("=== A CÓPIA É FIEL ===" if ok else "=== A CÓPIA DIVERGE ==="))
sys.exit(0 if ok else 1)
