#!/usr/bin/env bash
# Ensaia a migration de rename contra uma cópia fiel do schema da nuvem.
#
#   scripts/ensaiar_rename_nuvem.sh <ref-da-nuvem>
#
# Monta dois bancos descartáveis no Postgres apontado por PG* e confronta um com
# o outro:
#
#   alvo_en   — o que as 16 migrations deste repositório produzem.
#   ensaio_pt — o schema real da nuvem, em português, com as linhas de
#               configuração; depois a migration de rename e as migrations 12 a 15.
#
# O ensaio passa quando os dois catálogos ficam idênticos E as três suítes de
# comportamento (97, 98, 99) passam no banco renomeado. Igualdade de catálogo
# prova que o rename alcançou tudo; as suítes provam que a fronteira de
# segurança continua de pé depois dele.
#
# Requer psql, python3 e o token do `supabase login` (SUPABASE_ACCESS_TOKEN ou
# ~/.supabase/access-token). Lê apenas catálogo e tabelas de configuração da
# nuvem — nenhuma tabela de pessoa.
set -uo pipefail
REF="${1:?uso: $0 <project-ref>}"
cd "$(dirname "$0")/.."

falhou=0
passo() { printf '\n=== %s\n' "$1"; }

passo "1. lendo o schema da nuvem"
python3 scripts/introspeccao_nuvem.py "$REF" \
  --out scripts/_producao.sql --json scripts/_producao.json || exit 1

passo "2. montando o alvo (as 16 migrations deste repositório)"
psql -q -d postgres -c "drop database if exists alvo_en;" -c "create database alvo_en;" >/dev/null
PGDATABASE=alvo_en psql -q -v ON_ERROR_STOP=1 -f scripts/_test_stub_supabase.sql >/dev/null 2>&1
for f in supabase/migrations/*.sql; do
  PGDATABASE=alvo_en psql -q -v ON_ERROR_STOP=1 -f "$f" >/dev/null 2>&1
done
python3 scripts/introspeccao_nuvem.py alvo_en --psql \
  --out scripts/_alvo_en.sql --json scripts/_alvo_en.json || exit 1

passo "3. montando o ensaio (o schema da nuvem, em português)"
# Só a parte de PLATAFORMA do stub: roles, auth e extensões. As tabelas que ele
# simula em `public` são um palpite sobre o passado, e aqui o schema real vem
# logo em seguida.
sed -n "1,$(($(grep -n 'create table public\.' scripts/_test_stub_supabase.sql | head -1 | cut -d: -f1) - 1))p" \
  scripts/_test_stub_supabase.sql > scripts/_plataforma.sql
psql -q -d postgres -c "drop database if exists ensaio_pt;" -c "create database ensaio_pt;" >/dev/null
export PGDATABASE=ensaio_pt
psql -q -v ON_ERROR_STOP=1 -f scripts/_plataforma.sql >/dev/null 2>&1
erros=$(psql -q -f scripts/_producao.sql 2>&1 | grep -cE '^psql.*ERROR')
echo "  schema aplicado com $erros erro(s)"
[ "$erros" -ne 0 ] && falhou=1
python3 scripts/extrair_config_nuvem.py "$REF" > scripts/_config_nuvem.sql
psql -q -f scripts/_config_nuvem.sql >/dev/null 2>&1

passo "4. aplicando o rename e as migrations 12 a 15"
for f in supabase/migrations/20260815101150_*.sql \
         supabase/migrations/2026081510120*.sql supabase/migrations/2026081510130*.sql \
         supabase/migrations/2026081510140*.sql supabase/migrations/20260822160000*.sql; do
  saida=$(psql -q -v ON_ERROR_STOP=1 -f "$f" 2>&1 | grep -E '^psql.*(ERROR|FATAL)')
  if [ -n "$saida" ]; then echo "  FALHOU $(basename "$f"): $saida"; falhou=1
  else echo "  ok $(basename "$f")"; fi
done

passo "5. comportamento no banco renomeado"
for t in 97_teste_regras_alerta 98_teste_isolamento_tenant 99_verificacao_rls; do
  linha=$(psql -q -v ON_ERROR_STOP=1 -f "scripts/$t.sql" 2>&1 | grep -E 'FALHA|TODOS OS TESTES OK|PASSARAM' | tail -1)
  echo "  $t: ${linha:-<sem saída>}"
  case "$linha" in *OK|*PASSARAM) ;; *) falhou=1;; esac
done

passo "6. o catálogo do ensaio é o do alvo?"
python3 scripts/introspeccao_nuvem.py ensaio_pt --psql --json scripts/_ensaio.json --out /dev/null >/dev/null
python3 scripts/comparar_catalogos.py scripts/_ensaio.json scripts/_alvo_en.json || falhou=1

[ "$falhou" -eq 0 ] && echo -e "\n=== ENSAIO OK ===" || { echo -e "\n=== ENSAIO FALHOU ==="; exit 1; }
