-- ============================================================================
-- OperaX — 00. IMMEDIATE LOCKDOWN
-- ----------------------------------------------------------------------------
-- CONTEXTO: the Supabase anon key is (or will be) in the dashboard's public bundle.
-- Anyone can call PostgREST directly, bypassing the frontend.
-- Project convention: PascalCase = literal Secullum table (carries PII).
--
-- This migration moves nothing and does not break the worker:
--   - service_role has its own grants and the BYPASSRLS attribute;
--   - the frontend does not exist yet (Sprint 4 not started).
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

-- 1. Revoga anon/authenticated e liga RLS em toda tabela literal do Secullum.
do $$
declare r record;
begin
  for r in
    select schemaname, tablename
    from pg_tables
    where schemaname = 'public'
      and tablename ~ '^[A-Z]'
  loop
    execute format('revoke all on table %I.%I from anon, authenticated', r.schemaname, r.tablename);
    execute format('alter table %I.%I enable row level security', r.schemaname, r.tablename);
    execute format('alter table %I.%I force row level security', r.schemaname, r.tablename);
    raise notice 'blindada: %.%', r.schemaname, r.tablename;
  end loop;
end $$;

-- 2. Revoga também as sequences associadas (evita enumeração de volume).
do $$
declare r record;
begin
  for r in
    select sequence_schema, sequence_name
    from information_schema.sequences
    where sequence_schema = 'public' and sequence_name ~ '^[A-Z]'
  loop
    execute format('revoke all on sequence %I.%I from anon, authenticated', r.sequence_schema, r.sequence_name);
  end loop;
end $$;

-- 3. Tabela nova em public não nasce mais aberta para anon.
--    (afeta apenas objetos criados pelos roles abaixo, a partir de agora)
alter default privileges in schema public revoke all on tables    from anon;
alter default privileges in schema public revoke all on sequences from anon;
alter default privileges in schema public revoke all on functions from anon;

alter default privileges for role postgres in schema public revoke all on tables    from anon;
alter default privileges for role postgres in schema public revoke all on sequences from anon;

-- 4. Proof imediata: se sobrou qualquer tabela PascalCase legível por anon, falha.
do $$
declare n int;
begin
  select count(*) into n
  from pg_tables t
  where t.schemaname = 'public'
    and t.tablename ~ '^[A-Z]'
    and has_table_privilege('anon', format('%I.%I', t.schemaname, t.tablename), 'SELECT');

  if n > 0 then
    raise exception 'BLINDAGEM FALHOU: % tabela(s) do Secullum ainda legíveis por anon', n;
  end if;
  raise notice 'OK: nenhuma tabela literal do Secullum é legível por anon.';
end $$;
