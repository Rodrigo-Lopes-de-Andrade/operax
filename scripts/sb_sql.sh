#!/usr/bin/env bash
# Executa SQL num projeto Supabase pela Management API — sem senha de banco.
#
#   scripts/sb_sql.sh <project-ref> 'select 1'
#   scripts/sb_sql.sh <project-ref> -f consulta.sql
#
# Existe porque a senha do banco dos projetos na nuvem se perdeu e resetá-la num
# projeto de cliente é ação com consequência. A Management API executa SQL com o
# *token de conta* do `supabase login`, que o CLI já guarda em
# ~/.supabase/access-token. Também resolve dois problemas de rede: o host direto
# db.<ref>.supabase.co é IPv6-only, e o pooler exige usuário `postgres.<ref>`.
# Aqui é HTTPS, então nada disso importa.
#
# ⚠️ Isto roda como `postgres`. Não há RLS, não há confirmação e não há desfazer.
# O uso previsto é LEITURA DE CATÁLOGO (ver scripts/introspeccao_nuvem.py, que só
# consulta pg_catalog/information_schema). DDL em projeto de cliente é decisão do
# dono — ver docs/PLANO-RECONCILIACAO-NUVEM.md §5.
#
# Token: $SUPABASE_ACCESS_TOKEN, ou ~/.supabase/access-token. Nunca em arquivo do
# repositório. Gerar em https://supabase.com/dashboard/account/tokens
set -euo pipefail

if [ $# -lt 2 ]; then
  sed -n '2,6p' "$0" >&2
  exit 2
fi

REF="$1"; shift
TOKEN_FILE="${HOME}/.supabase/access-token"
PAT="${SUPABASE_ACCESS_TOKEN:-}"
if [ -z "$PAT" ]; then
  [ -r "$TOKEN_FILE" ] || {
    echo "sem token: defina SUPABASE_ACCESS_TOKEN ou rode \`supabase login\`" >&2
    exit 1
  }
  PAT=$(cat "$TOKEN_FILE")
fi

if [ "${1:-}" = "-f" ]; then SQL=$(cat "$2"); else SQL="$1"; fi

# O SQL vai por stdin e vira JSON em Python: aspas, quebras de linha e cifrões de
# corpo de função passam intactos, o que `-d "{\"query\":\"$SQL\"}"` não garante.
printf '%s' "$SQL" \
  | python3 -c 'import json,sys; print(json.dumps({"query": sys.stdin.read()}))' \
  | curl -sS --fail-with-body \
      -X POST "https://api.supabase.com/v1/projects/${REF}/database/query" \
      -H "Authorization: Bearer ${PAT}" \
      -H "Content-Type: application/json" \
      --data-binary @-
