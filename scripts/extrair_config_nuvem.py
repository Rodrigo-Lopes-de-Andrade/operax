#!/usr/bin/env python3
"""
Extrai as linhas de CONFIGURAÇÃO de um projeto Supabase, como `insert`.

    python3 scripts/extrair_config_nuvem.py <ref> > scripts/_config_nuvem.sql

Serve ao ensaio do rename: sem essas linhas o banco de ensaio tem o schema mas
não tem o catálogo de tipo de desvio nem a matriz de domínio, e a migração de
dado do bloco 11 não teria o que traduzir.

**Só tabelas de configuração são lidas.** Nenhuma tabela de pessoa entra aqui —
o alvo é o banco de um cliente, e o ensaio precisa do catálogo, não do cadastro.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

SB_SQL = pathlib.Path(__file__).with_name("sb_sql.sh")

TABELAS = {
    "tenant": "select * from app.tenant",
    "desvio_tipo": "select * from app.desvio_tipo order by codigo",
    "desvio_tipo_config": "select * from app.desvio_tipo_config order by codigo",
    "metrica": "select * from app.metrica order by codigo",
    "permissao_dominio": (
        "select tenant_id, papel::text, dominio::text, permitido "
        "from app.permissao_dominio order by 1, 2, 3"
    ),
}
# Colunas de tipo enum precisam do cast explícito: o valor vem como texto.
ENUM = {"permissao_dominio": {"papel": "app.papel", "dominio": "app.dominio_sensivel"}}


def literal(valor, cast: str | None = None) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)):
        return str(valor)
    if isinstance(valor, list):
        # text[] volta do JSON como lista; str(lista) vira literal malformado
        return "array[" + ", ".join(literal(x) for x in valor) + "]::text[]"
    if isinstance(valor, dict):
        return "'" + json.dumps(valor).replace("'", "''") + "'::jsonb"
    texto = "'" + str(valor).replace("'", "''") + "'"
    return f"{texto}::{cast}" if cast else texto


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(f"uso: {sys.argv[0]} <project-ref>")
    ref = sys.argv[1]

    print("-- Linhas de configuração da nuvem, para o ensaio do rename ser fiel.")
    print("-- Gerado por scripts/extrair_config_nuvem.py — nenhuma tabela de pessoa foi lida.")
    for tabela, sql in TABELAS.items():
        saida = subprocess.run([str(SB_SQL), ref, sql], capture_output=True, text=True)
        if saida.returncode != 0:
            sys.exit(f"falhou ao ler app.{tabela}: {saida.stderr.strip()}")
        linhas = json.loads(saida.stdout)
        if not linhas:
            continue
        colunas = list(linhas[0].keys())
        print(f"\n-- app.{tabela}: {len(linhas)} linha(s)")
        for linha in linhas:
            valores = ", ".join(literal(linha[c], ENUM.get(tabela, {}).get(c)) for c in colunas)
            print(
                f"insert into app.{tabela} ({', '.join(colunas)}) "
                f"values ({valores}) on conflict do nothing;"
            )


if __name__ == "__main__":
    main()
