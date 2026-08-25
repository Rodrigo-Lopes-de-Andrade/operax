#!/usr/bin/env bash
# Roda o stub Supabase + todas as migrations + a verificação de isolamento
# num banco descartável. Use em CI e antes de cada `supabase db push`.
set -uo pipefail
export PGHOST=${PGHOST:-/tmp} PGPORT=${PGPORT:-5433} PGUSER=${PGUSER:-postgres}
DB=${DB:-operax_test}
psql -q -d postgres -c "drop database if exists $DB;" -c "create database $DB;" >/dev/null 2>&1
export PGDATABASE=$DB
# Baseline: se existir um dump do schema REAL de vocês, testa a fusão de
# verdade. Sem ele, cai no stub simulado — que é um palpite, não o schema real.
if [ -f scripts/_baseline.sql ]; then
  BASE=scripts/_baseline.sql; ORIGEM="baseline real"
else
  BASE=scripts/_test_stub_supabase.sql; ORIGEM="stub simulado (sem _baseline.sql)"
fi
psql -q -v ON_ERROR_STOP=1 -f "$BASE" >/tmp/stub.log 2>&1 \
  || { echo "BASELINE FALHOU ($BASE)"; tail -20 /tmp/stub.log; exit 1; }
echo "baseline ok — $ORIGEM"
FAIL=0
for f in supabase/migrations/*.sql; do
  out=$(psql -q -v ON_ERROR_STOP=1 -f "$f" 2>&1 | grep -E '^psql.*(ERROR|FATAL)')
  if [ -n "$out" ]; then echo "FALHOU  $(basename "$f")"; echo "$out" | head -5; FAIL=1
  else echo "ok      $(basename "$f")"; fi
done
[ $FAIL -ne 0 ] && { echo "=== MIGRATIONS FALHARAM"; exit 1; }
echo "--- matriz dono-do-campo do RH"
python3 scripts/95_teste_matriz_rh.py || exit 1
echo "--- catálogo do assistente"
python3 scripts/91_teste_catalogo.py || exit 1

echo "--- promoção do espelho para o domínio"
python3 scripts/92_teste_cadastro.py || exit 1

echo "--- motor de jornada esperada"
python3 scripts/96_teste_jornada.py || exit 1

echo "--- motor de detecção"
python3 scripts/94_teste_deteccao.py || exit 1

echo "--- ciclo de relatório e fila de alertas"
python3 scripts/93_teste_ciclo.py || exit 1
echo "--- teste de regras de alerta e cadência"
psql -q -v ON_ERROR_STOP=1 -f scripts/97_teste_regras_alerta.sql 2>&1 | grep -Ev "^(INSERT|DO|SET|BEGIN|ROLLBACK|CREATE)" | sed "s/^psql:[^ ]* //" || exit 1
echo "--- teste funcional multi-tenant"
psql -q -v ON_ERROR_STOP=1 -f scripts/98_teste_isolamento_tenant.sql 2>&1 | grep -Ev "^(INSERT|DO|SET|BEGIN|ROLLBACK|CREATE)" | sed "s/^psql:[^ ]* //" || exit 1
echo "--- verificação de isolamento"
psql -q -v ON_ERROR_STOP=1 -f scripts/99_verificacao_rls.sql 2>&1 | grep -Ev '^(NOTICE|DO|BEGIN|ROLLBACK|SET|RESET)' 
RC=${PIPESTATUS[0]}
[ $RC -ne 0 ] && exit $RC

echo "--- regenerando dicionário de dados"
python3 scripts/gerar_dicionario.py || exit 1
echo "--- verificando referências da documentação"
python3 scripts/verificar_docs.py || exit 1
echo "=== SUÍTE COMPLETA OK"
