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

echo "--- a justificativa sobrevive ao reprocessamento (as quatro linhas da DECISAO-ALCADA §3)"
python3 scripts/teste_justificativa_sobrevive.py || exit 1

echo "--- a justificativa pendente (P1.1: o espelho não pende, e nada vira pending retroativamente)"
python3 scripts/82_teste_justificativa_pendente.py || exit 1

echo "--- o feriado no motor (P0.3: escala semanal folga, revezamento segue, VT e revogação)"
python3 scripts/83_teste_feriado.py || exit 1

echo "--- ponte da marcação (ingestão -> domínio)"
python3 scripts/89_teste_marcacao.py || exit 1

echo "--- ciclo de relatório e fila de alertas"
python3 scripts/93_teste_ciclo.py || exit 1

# O ciclo MUDO (C7). Este não é um roteiro de SQL como os de cima: o que está
# sob teste é a fronteira da transação e o laço que pula a regra doente, os dois
# em Python. Um roteiro que executasse `_RESERVE_SQL` e `_ENQUEUE_SQL` na ordem
# certa passaria com o defeito de pé. Então ele roda o código de verdade, o que
# exige o venv do backend — e, como o ensaio Deno, um DSN alcançável do HOST:
# o psql daqui pode estar atrás de um wrapper, e a porta não se deriva de PGPORT.
echo "--- o ciclo mudo (C7): uma transação só, regra doente pulada, ciclo desfeito"
# ⛔ Este passo é OBRIGATÓRIO, ao contrário do ensaio Deno: o que ele mede é a
# fronteira da transação do C7, e nenhum roteiro de `psql` a alcança — um
# `delete` sem filtro de tenant passa em todo o resto da suíte. Sem o DSN, a
# suíte FALHA em vez de seguir verde dizendo que mediu.
if [ -z "${ENSAIO_DATABASE_URL:-}" ]; then
  echo "!!! ciclo mudo NÃO RODOU — defina ENSAIO_DATABASE_URL, ex.:"
  echo "    ENSAIO_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55322/$DB"
  echo "    (é o mesmo DSN do ensaio Deno, alcançável do HOST)"
  exit 1
elif ! printf '%s' "$ENSAIO_DATABASE_URL" | grep -q "/$DB\$"; then
  # Rodar a prova do C7 no banco errado é pior que não rodar: ela diria OK
  # sobre um schema que não é o que acabou de ser migrado.
  echo "!!! ENSAIO_DATABASE_URL não termina em /$DB — a prova do C7 rodaria em outro banco"
  exit 1
elif [ -x backend/.venv/bin/python ]; then
  PY_ENSAIO="backend/.venv/bin/python"
elif command -v uv >/dev/null 2>&1; then
  PY_ENSAIO="uv run --no-sync --project backend python"
else
  echo "!!! PULADO: sem venv do backend e sem uv, e ENSAIO_DATABASE_URL foi definida"
  exit 1
fi
$PY_ENSAIO scripts/85_teste_ciclo_mudo.py || exit 1
# A curadoria de justificativa (S6). Pelo mesmo motivo do C7: o que está sob
# teste é o acordo entre a porta que grava a chave, o `check` que a canonicaliza
# e o apurador que a procura — e um roteiro de `psql` que inserisse no mapa na
# mão provaria o `check` e mentiria sobre o acordo.
echo "--- a porta da curadoria de justificativa (S6): sem aval, a competência não apura"
$PY_ENSAIO scripts/84_teste_curadoria_justificativa.py || exit 1
# O lock da alçada (P1.2) só existe entre DUAS sessões, e o `98` é uma só.
echo "--- a revisão concorrente (P1.2): quem não alcança não espera, a segunda vê a primeira"
$PY_ENSAIO scripts/81_teste_revisao_concorrente.py || exit 1
# O mesmo lock, na marca de lançamento (P1.4): sem ele a segunda sobrescreve.
echo "--- o lançamento concorrente (P1.4): quem não alcança não espera, a segunda não sobrescreve"
$PY_ENSAIO scripts/78_teste_lancamento_concorrente.py || exit 1
# A lista do lançamento (P1.4) é SQL no router, não objeto do banco: o que a
# prova é a rota de verdade, como o usuário, contra a RLS.
echo "--- a lista do lançamento (P1.4): competência do fato, papel na consulta, supervisor sem nada"
$PY_ENSAIO scripts/77_teste_lista_lancamento.py || exit 1
# A janela 21→20 vive em Python (DP) e em SQL (fila da alçada, P1.3).
echo "--- a janela da competência (P1.3): util.competencia_janela = dp/ciclo.py"
$PY_ENSAIO scripts/80_teste_janela_competencia.py || exit 1
# `detect()` inteiro, não o SQL dele: o `94` roda o statement por `psql` e
# não alcança o run que a função abre em Python — foi por ali que um parâmetro
# sombreado quebrou todo cron do motor com a suíte verde.
echo "--- detect() contra o banco: o run abre, fecha e carrega o escopo certo"
$PY_ENSAIO scripts/79_teste_detect_run.py || exit 1
echo "--- painel de DP (contadores de alerta, janela e escopo)"
psql -q -v ON_ERROR_STOP=1 -f scripts/87_teste_painel_dp.sql 2>&1 | grep -Ev "^(INSERT|UPDATE|DO|SET|BEGIN|ROLLBACK|CREATE)" | sed "s/^psql:[^ ]* //" || exit 1
echo "--- teste de regras de alerta e cadência"
psql -q -v ON_ERROR_STOP=1 -f scripts/97_teste_regras_alerta.sql 2>&1 | grep -Ev "^(INSERT|DO|SET|BEGIN|ROLLBACK|CREATE)" | sed "s/^psql:[^ ]* //" || exit 1
echo "--- exclusividade dos canais (as oito linhas da SPEC-CANAIS §2.2)"
psql -q -v ON_ERROR_STOP=1 -f scripts/86_teste_canais_exclusividade.sql 2>&1 | grep -Ev "^(INSERT|UPDATE|DO|SET|BEGIN|ROLLBACK|CREATE)" | sed "s/^psql:[^ ]* //" || exit 1
echo "--- tela de Conexões (a lista é a decomposição da contagem)"
python3 scripts/97_teste_canais.py || exit 1
echo "--- camadas do assistente (as sete linhas da SPEC-AGENTE §3a, a RPC e a RLS como os papéis)"
psql -q -v ON_ERROR_STOP=1 -f scripts/97_teste_assistente.sql 2>&1 | grep -Ev "^(INSERT|UPDATE|DELETE|DO|SET|BEGIN|ROLLBACK|CREATE|SAVEPOINT|RESET)" | sed "s/^psql:[^ ]* //" || exit 1
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
# ---------------------------------------------------------------------------
# O espelho do Secullum, conferido contra produção.
#
# Vinte das 22 tabelas já chegaram aqui pelo `_baseline.sql`, em `public`, e a
# migration 03 as varreu para `secullum`. As outras duas são snake_case: a 03 só
# varre `^[A-Z]`, então pelo caminho do baseline elas parariam em `app`. Entram
# agora, pela fixture, que é idempotente e só preenche o que falta.
#
# A conferência é o ponto. Em 01/09/2026 o baseline estava três linhas atrás de
# produção, e as três eram `Estrutura.departamento_id` — a coluna que a
# `sync-cadastro` grava e que produção não tem. Nada tocava.
# ---------------------------------------------------------------------------
echo "--- espelho do Secullum (alvo de ensaio)"
psql -q -v ON_ERROR_STOP=1 -f supabase/fixtures/espelho_secullum.sql >/tmp/espelho.log 2>&1 \
  || { echo "FIXTURE DO ESPELHO FALHOU"; tail -20 /tmp/espelho.log; exit 1; }
python3 scripts/verificar_espelho.py "$DB" --psql --somente-tabelas || exit 1
psql -q -v ON_ERROR_STOP=1 -f scripts/88_teste_espelho.sql 2>&1 \
  | grep -Ev '^(DO|SET|BEGIN|ROLLBACK)' | sed "s/^psql:[^ ]* //"
RC=${PIPESTATUS[0]}
[ $RC -ne 0 ] && exit $RC

# Aplicado PARA VALER, e não mais dentro de um rollback: a linha é o que
# destrava `writeSyncRun`, e o ensaio dos ciclos (mais abaixo) precisa dela de
# pé para provar que a `sync-cadastro` grava o diário. Sem ela aquele ensaio
# passaria pelo caminho macio — que é exatamente a falha que este arquivo
# existe para não repetir. As duas passadas seguidas continuam provando a
# idempotência; a guarda continua provando que a prova não deixa rastro.
echo "--- a integração que destrava app.sync_run"
psql -q -v ON_ERROR_STOP=1 <<'SQL' 2>&1 \
  | grep -Ev '^(DO|SET)' | sed "s/^psql:[^ ]* //"
\i scripts/janela_integracao_secullum.sql
\i scripts/janela_integracao_secullum.sql
do $g$ begin
  if (select count(*) from app.integration where provider='secullum' and active) <> 1 then
    raise exception 'esperava exatamente 1 integração secullum ativa';
  end if;
  if exists (select 1 from app.sync_run where entity = '__prova_janela__') then
    raise exception 'a linha de prova ficou em app.sync_run';
  end if;
  raise notice 'OK: 1 integração, idempotente, e a prova não deixou rastro';
end $g$;
SQL
RC=${PIPESTATUS[0]}
[ $RC -ne 0 ] && exit $RC

echo "--- troca de runner da janela (cron simulado, tudo em rollback)"
psql -q -v ON_ERROR_STOP=1 -f scripts/ensaio_janela_cron.sql 2>&1 \
  | grep -Ev '^(DO|SET|BEGIN|ROLLBACK|CREATE|INSERT|UPDATE|SAVEPOINT)' | sed "s/^psql:[^ ]* //"
RC=${PIPESTATUS[0]}
[ $RC -ne 0 ] && exit $RC

# ---------------------------------------------------------------------------
# Os dois ciclos de sincronização contra o espelho — o ensaio que as Edge
# Functions nunca tiveram. Opt-in porque o Deno roda no HOST e o psql daqui
# pode estar atrás de um wrapper: a porta não dá para derivar de PGPORT.
# ---------------------------------------------------------------------------
if [ -n "${ENSAIO_DATABASE_URL:-}" ]; then
  if command -v deno >/dev/null 2>&1; then
    echo "--- ensaio dos ciclos de sincronização contra o espelho"
    ( cd supabase/functions \
      && DATABASE_URL="$ENSAIO_DATABASE_URL" deno test --allow-net --allow-env \
           _shared/sync_espelho_test.ts ) || exit 1
  else
    echo "!!! ENSAIO PULADO: deno não está instalado, e ENSAIO_DATABASE_URL foi definida"
    exit 1
  fi
else
  echo "!!! ensaio dos ciclos de sincronização NÃO RODOU — defina ENSAIO_DATABASE_URL, ex.:"
  echo "    ENSAIO_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55322/$DB"
fi

echo "=== SUÍTE COMPLETA OK"
