-- ============================================================================
-- OperaX — 01. FOUNDATION: SCHEMAS AND PRIVILEGE POLICY
-- ----------------------------------------------------------------------------
-- Arquitetura de fronteira (a decisão central deste projeto):
--
--   secullum  literal Secullum mirror (PascalCase). Full PII.
--             NUNCA exposto ao PostgREST. Só service_role / conexão direta.
--
--   app       modelo de domínio OperaX (snake_case). Tabelas com RLS.
--             NUNCA exposto ao PostgREST. Alcançado apenas via views/RPC.
--
--   util      helpers SECURITY DEFINER usados pelas policies. Sem EXECUTE público.
--
--   public    ONLY exposed schema. Contém apenas VIEWS (security_invoker = on)
--             e FUNÇÕES RPC. No tables.
--
-- Golden rule: a table in `public` is a mistake.
--
-- >>> AÇÃO MANUAL OBRIGATÓRIA APÓS ESTA MIGRATION <<<
-- Supabase Dashboard -> Settings -> API -> Exposed schemas
-- deve conter APENAS: public, graphql_public
-- (não adicione `app` nem `secullum`)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- GUARDA: o schema `secullum` pode JÁ EXISTIR e já ter conteúdo.
-- O pg_stat_statements do projeto real mostra escrita direta em
-- secullum."HorarioDia", secullum."HorarioFaixasExtras" e
-- secullum."HorarioFaixasExtrasItem" — ao mesmo tempo que o PostgREST ainda
-- escreve nas homônimas em `public`. Isso é uma migração em andamento, não um
-- ponto de partida limpo, e aplicar a 03 por cima destruiria a transição.
-- ---------------------------------------------------------------------------
do $$
declare n int;
begin
  select count(*) into n
  from pg_class c join pg_namespace ns on ns.oid = c.relnamespace
  where ns.nspname in ('secullum','app') and c.relkind in ('r','p');

  if n > 0 then
    raise exception using
      errcode = 'raise_exception',
      message = format('Os schemas secullum/app já contêm %s tabela(s).', n),
      hint    = 'Rode scripts/01_preflight.sql e resolva a convivência antes. '
             || 'A migration 03 assume que `public` é a única source — com '
             || 'escrita dupla em andamento ela move o lado errado.';
  end if;
end $$;

create schema if not exists secullum;
create schema if not exists app;
create schema if not exists util;

comment on schema secullum is 'Espelho literal do Secullum. PII completa. Não exposto ao PostgREST.';
comment on schema app      is 'Modelo de domínio OperaX. RLS obrigatória. Não exposto ao PostgREST.';
comment on schema util     is 'Helpers SECURITY DEFINER para policies. EXECUTE revogado de anon/authenticated.';

-- ---------------------------------------------------------------------------
-- Privilégios de schema
-- ---------------------------------------------------------------------------

-- secullum: ninguém além do service_role encosta.
revoke all on schema secullum from public, anon, authenticated;
grant  usage on schema secullum to service_role;

-- app: authenticated recebe USAGE porque as views de `public` rodam com
-- security_invoker = on — o privilégio real é filtrado pela RLS de cada tabela.
-- Como `app` não está exposto ao PostgREST, o GRANT não cria superfície de API.
revoke all   on schema app from public, anon;
grant  usage on schema app to authenticated, service_role;

-- util: só o motor de policies usa.
revoke all   on schema util from public, anon;
grant  usage on schema util to authenticated, service_role;

-- public: authenticated lê views. anon não lê nada.
revoke all   on schema public from public;
grant  usage on schema public to anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Defaults: objeto novo nasce fechado
-- ---------------------------------------------------------------------------
alter default privileges in schema secullum revoke all on tables    from anon, authenticated;
alter default privileges in schema secullum revoke all on sequences from anon, authenticated;
alter default privileges in schema app      revoke all on tables    from anon;
alter default privileges in schema app      revoke all on sequences from anon;
alter default privileges in schema public   revoke all on tables    from anon;

-- Função em Postgres nasce com EXECUTE para PUBLIC. Nos schemas internos isso
-- é revogado no default e cada função recebe grant explícito.
alter default privileges in schema util     revoke all on functions from public;
alter default privileges in schema app      revoke all on functions from public;
alter default privileges in schema secullum revoke all on functions from public;

-- ---------------------------------------------------------------------------
-- Extensões necessárias
-- ---------------------------------------------------------------------------
create extension if not exists pgcrypto  with schema extensions;  -- gen_random_uuid()
create extension if not exists btree_gist with schema extensions; -- exclusão por período

-- ---------------------------------------------------------------------------
-- Guarda de arquitetura: impede que alguém crie tabela em `public` por engano
-- ---------------------------------------------------------------------------
create or replace function util.block_table_in_public()
returns event_trigger
language plpgsql
as $$
declare obj record;
begin
  for obj in select * from pg_event_trigger_ddl_commands()
  loop
    if obj.object_type = 'table' and obj.schema_name = 'public' then
      raise exception using
        errcode = 'raise_exception',
        message = format('Tabela %s criada em public.', obj.object_identity),
        hint    = 'Tabelas vão para `app` (domínio) ou `secullum` (espelho). `public` só recebe views e RPCs.';
    end if;
  end loop;
end $$;

drop event trigger if exists trg_block_table_in_public;
create event trigger trg_block_table_in_public
  on ddl_command_end
  when tag in ('CREATE TABLE', 'CREATE TABLE AS')
  execute function util.block_table_in_public();

comment on function util.block_table_in_public() is
  'Guarda de arquitetura. Para desativar temporariamente: ALTER EVENT TRIGGER trg_block_table_in_public DISABLE;';
