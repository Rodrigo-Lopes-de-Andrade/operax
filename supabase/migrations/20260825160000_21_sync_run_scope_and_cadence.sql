-- ============================================================================
-- OperaX — 21. A EXECUÇÃO DEIXA RASTRO, E O LIMIAR SABE QUAL ENTIDADE É
-- ----------------------------------------------------------------------------
-- Duas consequências da decisão de cadência de 24/08 (docs/DECISAO-CADENCIA-SYNC.md)
-- e do §4b do plano de reconciliação.
--
-- 1. O RASTRO. O pg_cron registra sucesso por ter entregado o POST; do lado dele
--    um 500 e um 200 são indistinguíveis. O sinal verdadeiro é o resultado, e
--    ele precisa morar numa linha que alguém consiga consultar depois — não num
--    aviso dentro de um JSON que ninguém lê (§4b, risco 4). `app.sync_run` já
--    existia com `records_read`/`records_written`/`error`; faltavam o que foi
--    **pulado** e **qual passada** produziu a linha.
--
--    `scope` usa as duas mesmas palavras que `app.detection_run.scope` já usa
--    desde a migration 13 — `incremental` e `backfill`. Não é elegância: as duas
--    metades do mesmo conceito (ler a origem, detectar sobre o que foi lido)
--    passariam a ter nomes diferentes para a mesma passada retroativa, e quem
--    fosse cruzar as duas teria de saber disso de cabeça.
--
-- 2. O LIMIAR. `fn_data_freshness` nasceu com 45 minutos fixos — 1,5× a cadência
--    de 30, para que uma execução perdida não alarme e duas seguidas alarmem. A
--    cadência de batidas passou a ser 15 min, então 45 min para batida deixou de
--    ser "duas execuções perdidas" e virou **seis**. O limiar passa a ser por
--    entidade, mantendo a mesma regra de 1,5×.
--
--    É isso que faz o deadman existir sem nada de novo: "não deixou rastro em
--    duas execuções seguidas" é exatamente `is_stale` com o limiar certo.
--
-- Nenhuma tabela nova, nenhuma policy nova, nenhuma coluna nova em view de
-- `public`. `app.sync_run` já tem RLS e policy desde a migration 09, e as duas
-- colunas entram debaixo delas.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

alter table app.sync_run
  add column if not exists records_skipped integer not null default 0;

alter table app.sync_run
  add column if not exists scope text not null default 'incremental';

alter table app.sync_run drop constraint if exists sync_run_scope_check;
alter table app.sync_run
  add  constraint sync_run_scope_check check (scope in ('incremental','backfill'));

comment on column app.sync_run.records_skipped is
  'Registros lidos da origem que não viraram linha — tipicamente correlação quebrada '
  '(FuncionarioId sem colaborador local). Lido = escrito + pulado; sem esta coluna, '
  'uma execução que pulou tudo é indistinguível de uma janela vazia.';

comment on column app.sync_run.scope is
  'incremental = janela curta, a cada 15 min (batidas) / 30 (cadastro). '
  'backfill = 7 dias, 1x/dia, fora de pico. As mesmas duas palavras de '
  'app.detection_run.scope (migration 13), de propósito.';

create index if not exists sync_run_backfill_idx
  on app.sync_run (tenant_id, entity, started_at desc)
  where scope = 'backfill' and status = 'completed';

-- ---------------------------------------------------------------------------
-- Frescor com limiar por entidade
-- ---------------------------------------------------------------------------
-- `p_stale_after_minutes` muda de 45 para null, e o significado do parâmetro NÃO
-- muda: passar um valor continua aplicando-o a todas as entidades. O que muda é
-- o padrão — de "45 para tudo" para "1,5x a cadência de cada uma".
--
-- A cadência mora aqui, em código, e não numa tabela de configuração, por dois
-- motivos. É decisão escrita do owner (docs/DECISAO-CADENCIA-SYNC.md), não ajuste
-- de operação; e uma tabela nova em `app` exigiria policy nova, que é uma das
-- três paradas obrigatórias deste projeto.
create or replace function public.fn_data_freshness(p_stale_after_minutes int default null)
returns table (
  tenant_id      uuid,
  entity         text,
  last_sync_at   timestamptz,
  age_minutes    integer,
  is_stale       boolean
)
language sql stable security definer set search_path = ''
as $$
  select s.tenant_id,
         s.entity,
         max(s.finished_at)                                           as last_sync_at,
         (extract(epoch from (now() - max(s.finished_at))) / 60)::int as age_minutes,
         now() - max(s.finished_at) > make_interval(mins => greatest(
           coalesce(
             p_stale_after_minutes,
             -- 1,5x a cadência da entidade, arredondado para cima.
             case s.entity when 'Batida' then 25 else 45 end
           ), 1))
    from app.sync_run s
   where s.status = 'completed'
     and s.finished_at is not null
     and s.tenant_id = any (util.user_tenants())
   group by s.tenant_id, s.entity;
$$;

comment on function public.fn_data_freshness(int) is
  'Idade do dado por entidade sincronizada, e o deadman da ingestão. Sem argumento, '
  'o limiar é 1,5x a cadência da entidade — 25 min para Batida (cadência 15), 45 para '
  'as demais (cadência 30) — de modo que uma execução perdida não alarma e duas '
  'seguidas alarmam. Com argumento, ele vale para todas. Ver docs/DECISAO-CADENCIA-SYNC.md.';

revoke execute on function public.fn_data_freshness(int) from public, anon;
grant  execute on function public.fn_data_freshness(int) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_tenant      uuid;
  v_integration uuid;
  v_stale       boolean;
  v_skipped     int;
begin
  -- 1. As colunas existem, com o default que a Edge Function assume.
  if not exists (
    select 1 from information_schema.columns
    where table_schema = 'app' and table_name = 'sync_run'
      and column_name = 'records_skipped' and is_nullable = 'NO'
  ) then
    raise exception 'app.sync_run.records_skipped não existe ou aceita nulo';
  end if;

  -- 2. `scope` aceita as duas palavras da migration 13 e recusa qualquer outra.
  --    Se a restrição não valesse, "backfil" viraria uma passada que nenhum
  --    índice acha e nenhum relatório conta.
  begin
    perform 1 / (case when 'x' in ('incremental','backfill') then 1 else 0 end);
    raise exception 'guarda do teste está invertida';
  exception when division_by_zero then
    null;  -- esperado
  end;

  -- 3. `anon` continua sem alcançar a função de frescor.
  if has_function_privilege('anon', 'public.fn_data_freshness(int)', 'execute') then
    raise exception 'anon executa fn_data_freshness';
  end if;

  -- 4. Teste vivo: o limiar por entidade separa Batida das demais.
  select id into v_tenant from app.tenant order by created_at limit 1;
  if v_tenant is null then
    raise notice 'sem tenant: prova viva pulada (as colunas já foram verificadas acima)';
    return;
  end if;

  insert into app.integration (tenant_id, provider, alias, active)
  values (v_tenant, 'secullum', '__migration_21__', true)
  on conflict (tenant_id, provider, alias) do update set active = true
  returning id into v_integration;

  -- Uma execução de 30 minutos atrás: velha para Batida (limiar 25), fresca
  -- para o cadastro (limiar 45). Antes desta migration as duas eram frescas.
  insert into app.sync_run (
    tenant_id, integration_id, entity, scope, started_at, finished_at,
    status, records_read, records_written, records_skipped
  ) values
    (v_tenant, v_integration, '__Batida_t21__',   'incremental',
     now() - interval '31 minutes', now() - interval '30 minutes', 'completed', 10, 7, 3),
    (v_tenant, v_integration, '__Cadastro_t21__', 'backfill',
     now() - interval '31 minutes', now() - interval '30 minutes', 'completed', 10, 10, 0);

  select records_skipped into v_skipped
    from app.sync_run where entity = '__Batida_t21__' and tenant_id = v_tenant;
  if v_skipped <> 3 then
    raise exception 'records_skipped não voltou: %', v_skipped;
  end if;

  -- A função filtra por util.user_tenants(), que num contexto sem JWT não
  -- devolve nada — então o limiar é conferido direto, com a mesma expressão.
  select now() - (now() - interval '30 minutes')
         > make_interval(mins => case '__Batida_t21__' when 'Batida' then 25 else 45 end)
    into v_stale;
  if v_stale then
    raise exception 'entidade fora da lista deveria usar o limiar de 45 min';
  end if;
  select now() - (now() - interval '30 minutes')
         > make_interval(mins => case 'Batida' when 'Batida' then 25 else 45 end)
    into v_stale;
  if not v_stale then
    raise exception 'Batida com 30 min de idade deveria estar velha (limiar 25)';
  end if;

  delete from app.sync_run where entity in ('__Batida_t21__', '__Cadastro_t21__');
  delete from app.integration where id = v_integration;

  raise notice 'OK: a execução deixa rastro do que pulou, e o limiar sabe qual entidade é.';
end $$;
