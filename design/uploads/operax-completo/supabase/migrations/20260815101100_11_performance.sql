-- ============================================================================
-- OperaX — 11. PERFORMANCE
-- ----------------------------------------------------------------------------
-- Meta de carregamento do dashboard: < 3s (decisão do Owner, item 8 do resumo).
-- Três frentes:
--   1. Índice em toda FK — Postgres não cria automaticamente e o dashboard é
--      JOIN em cima de JOIN.
--   2. Índice nas colunas usadas por RLS — a policy roda por linha; sem índice,
--      cada consulta filtrada vira varredura.
--   3. Materialized view do resumo diário — os dados só mudam quando o worker
--      roda, então cache materializado é obviamente correto aqui.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Varredura de FK sem índice
-- ---------------------------------------------------------------------------
do $$
declare r record; idx_name text; criados int := 0;
begin
  for r in
    select n.nspname as schema_name,
           t.relname as table_name,
           a.attname as col_name
    from pg_constraint c
    join pg_class     t on t.oid = c.conrelid
    join pg_namespace n on n.oid = t.relnamespace
    join pg_attribute a on a.attrelid = c.conrelid and a.attnum = c.conkey[1]
    where c.contype = 'f'
      and n.nspname in ('app','secullum')
      and array_length(c.conkey, 1) = 1
      and not exists (
        select 1 from pg_index i
        where i.indrelid = c.conrelid and i.indkey[0] = c.conkey[1]
      )
  loop
    idx_name := left(format('%s_%s_fkidx', r.table_name, r.col_name), 63);
    execute format('create index if not exists %I on %I.%I (%I)',
                   idx_name, r.schema_name, r.table_name, r.col_name);
    criados := criados + 1;
    raise notice 'índice de FK criado: %.%(%)', r.schema_name, r.table_name, r.col_name;
  end loop;
  raise notice '% índice(s) de FK criados.', criados;
end $$;

-- ---------------------------------------------------------------------------
-- 2. Índices que sustentam as policies de RLS
-- ---------------------------------------------------------------------------
create index if not exists tenant_member_rls_idx
  on app.tenant_member (user_id, tenant_id, role) where active;
create index if not exists escopo_rls_idx
  on app.user_scope (user_id, tenant_id, company_id, unit_id);
create index if not exists domain_permission_rls_idx
  on app.domain_permission (tenant_id, role, domain) where allowed;

-- Composto para o padrão de consulta do dashboard: igualdade primeiro, range depois.
create index if not exists deviation_periodo_idx
  on app.deviation_event (tenant_id, unit_id, reference_date)
  where status = 'active' and mode = 'production';
create index if not exists deviation_tipo_periodo_idx
  on app.deviation_event (tenant_id, type, reference_date)
  where status = 'active' and mode = 'production';

-- ---------------------------------------------------------------------------
-- 3. updated_at automático
-- ---------------------------------------------------------------------------
create or replace function util.touch_updated_at()
returns trigger language plpgsql set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end $$;

do $$
declare r record;
begin
  for r in
    select c.relname as tabela
    from pg_attribute a
    join pg_class c     on c.oid = a.attrelid
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'app' and a.attname = 'updated_at' and c.relkind = 'r'
  loop
    execute format('drop trigger if exists trg_updated_at on app.%I', r.tabela);
    execute format(
      'create trigger trg_updated_at before update on app.%I
       for each row execute function util.touch_updated_at()', r.tabela);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 4. Materialized view do resumo diário
--    REFRESH CONCURRENTLY exige índice único — daí a PK sintética abaixo.
--    O worker chama app.refresh_dashboard() ao final de cada execução do motor.
-- ---------------------------------------------------------------------------
drop materialized view if exists app.mv_deviation_day;
create materialized view app.mv_deviation_day as
select d.tenant_id,
       d.reference_date,
       d.company_id,
       d.unit_id,
       d.type,
       count(*)::bigint                                        as eventos,
       count(distinct d.employee_id)::bigint                as colaboradores,
       coalesce(sum(d.minutes) filter (where d.minutes > 0),0)::bigint  as minutes_excedente,
       coalesce(-sum(d.minutes) filter (where d.minutes < 0),0)::bigint as minutes_faltante
from app.deviation_event d
join app.deviation_type_config cfg
     on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
where d.status = 'active' and d.mode = 'production'
group by d.tenant_id, d.reference_date, d.company_id, d.unit_id, d.type;

create unique index if not exists mv_deviation_day_pk
  on app.mv_deviation_day (tenant_id, reference_date, company_id, coalesce(unit_id, '00000000-0000-0000-0000-000000000000'::uuid), type);
create index if not exists mv_deviation_day_periodo_idx on app.mv_deviation_day (tenant_id, reference_date);

create or replace function app.refresh_dashboard()
returns void language plpgsql security definer set search_path = ''
as $$
begin
  refresh materialized view concurrently app.mv_deviation_day;
end $$;

revoke execute on function app.refresh_dashboard() from public, anon, authenticated;
grant  execute on function app.refresh_dashboard() to service_role;

-- ATENÇÃO: matview NÃO respeita RLS. app.mv_deviation_day contém todos os tenants
-- e por isso nunca é exposta em `public`. Quem serve o dashboard a partir dela é
-- a rota server-side no Vercel (service_role + filtro explícito de tenant/escopo).
revoke all on app.mv_deviation_day from anon, authenticated;
grant  select on app.mv_deviation_day to service_role;

-- ---------------------------------------------------------------------------
-- 5. Final lockdown de EXECUTE
--    Função em Postgres nasce com EXECUTE para PUBLIC, e ALTER DEFAULT
--    PRIVILEGES não cobre todos os casos de forma confiável. Esta varredura
--    revoga PUBLIC e anon em util/app; os grants explícitos para authenticated
--    e service_role feitos nas migrations anteriores permanecem intactos.
-- ---------------------------------------------------------------------------
do $$
declare r record; n int := 0;
begin
  for r in
    select p.oid::regprocedure as assinatura
    from pg_proc p
    join pg_namespace ns on ns.oid = p.pronamespace
    where ns.nspname in ('util','app')
      and p.prokind = 'f'
  loop
    execute format('revoke execute on function %s from public, anon', r.assinatura);
    n := n + 1;
  end loop;
  raise notice 'EXECUTE revogado de PUBLIC/anon em % função(ões).', n;
end $$;

-- Proof
do $$
declare r record; falhas text := '';
begin
  for r in
    select p.oid, p.proname
    from pg_proc p join pg_namespace ns on ns.oid = p.pronamespace
    where ns.nspname in ('util','app','public') and p.prokind = 'f'
  loop
    if has_function_privilege('anon', r.oid, 'EXECUTE') then
      falhas := falhas || r.proname || ' ';
    end if;
  end loop;
  if falhas <> '' then
    raise exception 'FALHA: anon ainda executa -> %', falhas;
  end if;
  raise notice 'OK: nenhuma função executável por anon.';
end $$;

-- ---------------------------------------------------------------------------
-- 6. Estatísticas
-- ---------------------------------------------------------------------------
alter table app.deviation_event set (autovacuum_analyze_scale_factor = 0.02);
alter table app.expected_workday     set (autovacuum_analyze_scale_factor = 0.02);
analyze app.deviation_event;
analyze app.employee;
analyze app.unit;
