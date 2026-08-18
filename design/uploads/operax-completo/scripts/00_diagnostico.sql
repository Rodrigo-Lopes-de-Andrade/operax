-- OperaX / Kastro Park — DIAGNÓSTICO DE EXPOSIÇÃO
-- Read-only. Rode ANTES de qualquer migration e cole o resultado no PR.
-- Objetivo: provar o que hoje está alcançável pela anon key (que está no bundle público).

\echo '=== 1. Tabelas em public: RLS ligada? anon/authenticated leem? ==='
select t.tablename,
       t.rowsecurity                                                                      as rls_on,
       has_table_privilege('anon',          format('%I.%I', t.schemaname, t.tablename), 'SELECT') as anon_select,
       has_table_privilege('authenticated', format('%I.%I', t.schemaname, t.tablename), 'SELECT') as auth_select,
       (select count(*) from pg_policies p
         where p.schemaname = t.schemaname and p.tablename = t.tablename)                 as n_policies,
       pg_size_pretty(pg_total_relation_size(format('%I.%I', t.schemaname, t.tablename)::regclass)) as tamanho
from pg_tables t
where t.schemaname = 'public'
order by t.rowsecurity, t.tablename;
-- LEITURA: rls_on = false E anon_select = true  -> ABERTO PARA A INTERNET.
--          rls_on = true  E n_policies = 0      -> fechado (nenhuma linha passa).
--          rls_on = true  com policy using(true)-> parece seguro no relatório e NÃO é.

\echo '=== 2. Policies existentes (procure por qual = true) ==='
select schemaname, tablename, policyname, roles, cmd, qual, with_check
from pg_policies
order by schemaname, tablename, policyname;

\echo '=== 3. Views SECURITY DEFINER (ignoram RLS da tabela base) ==='
select n.nspname as schema, c.relname as view, c.relkind,
       coalesce(array_to_string(c.reloptions, ','), '(sem opcoes -> DEFINER, RLS IGNORADA)') as opcoes
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where c.relkind in ('v','m')
  and n.nspname not in ('pg_catalog','information_schema','extensions')
order by 1,2;
-- Qualquer view sem security_invoker=true roda como o DONO e ignora RLS das tabelas base.

\echo '=== 4. Inventário de colunas (insumo para o mapeamento -> schema app) ==='
select table_schema, table_name, column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema not in ('pg_catalog','information_schema','extensions','auth','storage','realtime','vault','graphql','graphql_public','net','pgsodium','supabase_migrations','supabase_functions','cron')
order by table_schema, table_name, ordinal_position;

\echo '=== 5. Chaves e relacionamentos existentes ==='
select tc.table_schema, tc.table_name, tc.constraint_type, tc.constraint_name,
       kcu.column_name, ccu.table_name as ref_table, ccu.column_name as ref_column
from information_schema.table_constraints tc
left join information_schema.key_column_usage kcu
       on kcu.constraint_name = tc.constraint_name and kcu.constraint_schema = tc.constraint_schema
left join information_schema.constraint_column_usage ccu
       on ccu.constraint_name = tc.constraint_name and ccu.constraint_schema = tc.constraint_schema
where tc.constraint_type in ('PRIMARY KEY','FOREIGN KEY','UNIQUE')
  and tc.table_schema not in ('pg_catalog','information_schema')
order by 1,2,3;

\echo '=== 6. Colunas com cara de PII (confira o resultado item a item) ==='
select table_schema, table_name, column_name
from information_schema.columns
where table_schema not in ('pg_catalog','information_schema','auth','storage','vault')
  and column_name ~* '(cpf|rg$|identidade|endereco|logradouro|cep|telefone|celular|fone|email|mae|pai|filiacao|nascimento|pis|ctps|titulo|salario|remunera|conta|agencia|banco|racial|deficien)'
order by 1,2,3;

\echo '=== 7. Índices existentes ==='
select schemaname, tablename, indexname, indexdef
from pg_indexes
where schemaname not in ('pg_catalog','information_schema')
order by 1,2,3;

\echo '=== 8. Extensões e versão ==='
select current_setting('server_version') as pg_version;
select extname, extversion from pg_extension order by 1;
