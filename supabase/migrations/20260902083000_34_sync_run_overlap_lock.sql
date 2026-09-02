-- ============================================================================
-- OperaX — 34. O DIÁRIO DA SINCRONIZAÇÃO VIRA LOCK
-- ----------------------------------------------------------------------------
-- `app.job_execucao`, o diário do runner que sai, é duas coisas ao mesmo tempo:
-- o registro do que aconteceu e o **lock de sobreposição** dos jobs agendados.
-- Quem o torna lock é um índice único parcial, medido no catálogo de produção:
--
--     CREATE UNIQUE INDEX job_execucao_em_andamento_key
--       ON app.job_execucao USING btree (job) WHERE (status = 'running')
--
-- `app.sync_run` — o diário para onde a sincronização vai — não tem equivalente.
-- Trocar de diário sem trocar de lock entregaria sobreposição silenciosa, e a
-- porta para ela não é hipotética: depois da troca de runner, quem barra as Edge
-- Functions é o `verify_jwt` do gateway, que aceita a anon key, que é pública.
--
-- ⛔ E O ÍNDICE SOZINHO NÃO RESOLVE — foi por isso que este conserto ficou
-- parado. `app.sync_run.status` tem default `'running'` e o check aceita os
-- quatro estados: o schema foi desenhado para **reivindicar antes e fechar
-- depois**. Só que ninguém reivindicava — a Edge Function gravava uma linha só,
-- no fim, já com status terminal. Um índice parcial em cima disso é um lock que
-- nunca tranca. A outra metade do conserto está em
-- `supabase/functions/_shared/sync-run.ts`, e é ela que dá sentido a este
-- índice: `claimSyncRun` grava `running` ao começar, `closeSyncRun` fecha a
-- mesma linha ao terminar.
--
-- POR QUE (tenant_id, entity) E NÃO (tenant_id, entity, scope)
-- `sync-batidas` roda em dois escopos — `incremental` a cada 15 min e
-- `backfill` 1x/dia — e os dois escrevem as MESMAS tabelas. Deixá-los correr
-- juntos é a sobreposição que se quer evitar, não uma exceção a ela. É também o
-- que aposenta a heurística do minuto 7 em `scripts/janela_cron_runner.sql`: o
-- backfill saía da grade de 15 porque não havia lock.
--
-- O LEASE MORA NO CÓDIGO, E O NÚMERO É MEDIDO
-- Um lock que não expira transforma um crash em parada permanente: a linha
-- `running` fica, e toda execução seguinte é recusada. Por isso `claimSyncRun`
-- reivindica **depois** de encerrar como `failed` qualquer `running` mais velho
-- que o lease. O número saiu do diário de produção em 02/09/2026, sobre 954
-- execuções: `sync_batidas` leva 3,5 s em média (máx 27 s) e `sync_cadastro`
-- 7,4 s (máx 31 s). O lease de 10 min é 20x o pior caso medido e ainda menor
-- que a menor cadência (15 min) — então um `running` abandonado nunca sobrevive
-- para bloquear o ciclo seguinte. Ele fica no código porque é o código que o
-- aplica; aqui ficaria como constante que ninguém lê.
--
-- Nenhuma tabela nova, nenhuma coluna nova, nenhuma policy nova. `app.sync_run`
-- tem RLS e policy desde a migration 09.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

create unique index if not exists sync_run_em_andamento_key
  on app.sync_run (tenant_id, entity)
  where status = 'running';

comment on index app.sync_run_em_andamento_key is
  'Lock de sobreposição da sincronização — o equivalente de '
  'job_execucao_em_andamento_key no diário do runner antigo. Uma execução em '
  'andamento por (tenant, entidade); os dois escopos (incremental e backfill) '
  'disputam o mesmo lock de propósito, porque escrevem as mesmas tabelas. '
  'Só tranca porque a Edge Function reivindica antes e fecha depois — ver '
  'supabase/functions/_shared/sync-run.ts.';

-- ---------------------------------------------------------------------------
-- Prova
-- ---------------------------------------------------------------------------
do $$
declare
  v_tenant      uuid;
  v_integration uuid;
  v_primeira    uuid;
  v_segunda     uuid;
  v_barrou      boolean := false;
begin
  -- 1. O índice existe, é único e é parcial pelo estado certo. Um índice total
  --    aqui recusaria a segunda execução de sempre, não a simultânea.
  if not exists (
    select 1
      from pg_index i
      join pg_class c  on c.oid = i.indexrelid
      join pg_class t  on t.oid = i.indrelid
      join pg_namespace n on n.oid = t.relnamespace
     where n.nspname = 'app' and t.relname = 'sync_run'
       and c.relname = 'sync_run_em_andamento_key'
       and i.indisunique
       and pg_get_expr(i.indpred, i.indrelid) ilike '%running%'
  ) then
    raise exception 'sync_run_em_andamento_key não existe, não é único, ou não é parcial em running';
  end if;

  select id into v_tenant from app.tenant order by created_at limit 1;
  if v_tenant is null then
    raise notice 'sem tenant: prova viva pulada (o índice já foi verificado acima)';
    return;
  end if;

  insert into app.integration (tenant_id, provider, alias, active)
  values (v_tenant, 'secullum', '__migration_34__', true)
  on conflict (tenant_id, provider, alias) do update set active = true
  returning id into v_integration;

  -- 2. A primeira reivindicação passa.
  insert into app.sync_run (tenant_id, integration_id, entity, scope, status)
  values (v_tenant, v_integration, '__lock_t34__', 'incremental', 'running')
  returning id into v_primeira;

  -- 3. A segunda, do MESMO par (tenant, entidade), é barrada — inclusive com
  --    escopo diferente, que é o ponto de a chave não incluir `scope`.
  begin
    insert into app.sync_run (tenant_id, integration_id, entity, scope, status)
    values (v_tenant, v_integration, '__lock_t34__', 'backfill', 'running');
  exception when unique_violation then
    v_barrou := true;
  end;
  if not v_barrou then
    raise exception 'duas execuções simultâneas da mesma entidade foram aceitas — o lock não tranca';
  end if;

  -- 4. Outra entidade não é barrada: o lock é por entidade, não global. Sem
  --    isto, cadastro e batidas passariam a se excluir.
  insert into app.sync_run (tenant_id, integration_id, entity, scope, status)
  values (v_tenant, v_integration, '__lock_t34_outra__', 'incremental', 'running')
  returning id into v_segunda;

  -- 5. Fechada a primeira, o par volta a aceitar reivindicação. É o que
  --    permite o ciclo seguinte rodar — e o que um índice total quebraria.
  update app.sync_run set status = 'completed', finished_at = now()
   where id = v_primeira;

  insert into app.sync_run (tenant_id, integration_id, entity, scope, status)
  values (v_tenant, v_integration, '__lock_t34__', 'incremental', 'running');

  delete from app.sync_run where entity in ('__lock_t34__', '__lock_t34_outra__');
  delete from app.integration where id = v_integration;

  raise notice 'OK: uma execução em andamento por (tenant, entidade), e o par libera ao fechar.';
end $$;
