-- ============================================================================
-- OperaX — PRÉ-VOO
-- ----------------------------------------------------------------------------
-- Read-only. Simula o que as migrations 00 e 03 VÃO fazer, sem fazer nada.
-- Rode no projeto real ANTES de aplicar qualquer migration.
--
--   psql "$DATABASE_URL" -f scripts/01_preflight.sql > docs/preflight-<data>.txt
--
-- >>> ESTE RELATÓRIO NÃO CONTÉM NENHUM DADO PESSOAL. <<<
-- Só name de objeto, type, contagem e percentual. Nenhuma linha de tabela é
-- selecionada. É seguro anexar numa conversa ou num PR.
--
-- O que NÃO deve ser compartilhado em nenhuma hipótese: dump com --data-only,
-- result de `select *` em qualquer tabela do Secullum, planilha de
-- colaboradores, folha. Se precisar avaliar qualidade de dado, use agregado —
-- é o que a seção 9 deste arquivo faz.
-- ============================================================================

\pset pager off
\timing off

\echo '############################################################'
\echo '# 1. MIGRATIONS JÁ APLICADAS'
\echo '############################################################'
do $$
declare r record; n int := 0; ultima text;
begin
  if to_regclass('supabase_migrations.schema_migrations') is null then
    raise notice 'Nenhum histórico de migration encontrado (projeto sem Supabase CLI ainda).';
    return;
  end if;
  for r in execute 'select version, coalesce(name,'''') as name
                    from supabase_migrations.schema_migrations order by version'
  loop
    raise notice '  %  %', r.version, r.name;
    ultima := r.version; n := n + 1;
  end loop;
  raise notice '% migration(s) aplicada(s). Última: %', n, coalesce(ultima, '—');
  if ultima is not null and ultima >= '20260815100000' then
    raise warning 'A última migration existente é MAIS NOVA que as do OperaX (20260815100000). Renomeie os arquivos do OperaX para timestamps posteriores antes de aplicar.';
  end if;
end $$;
-- As 12 migrations do OperaX precisam ter timestamp MAIOR que a última daqui.
-- Se não tiverem, renomeie os arquivos antes de aplicar — a ordem é o que
-- garante que as tabelas existam antes de serem movidas.

\echo ''
\echo '############################################################'
\echo '# 2. SCHEMAS QUE JÁ EXISTEM'
\echo '############################################################'
select nspname as schema,
       (select count(*) from pg_class c where c.relnamespace = n.oid and c.relkind in ('r','p')) as tabelas,
       (select count(*) from pg_class c where c.relnamespace = n.oid and c.relkind = 'v')        as views
from pg_namespace n
where nspname not like 'pg\_%'
  and nspname not in ('information_schema')
order by 1;
-- Se `app`, `secullum` ou `util` JÁ existirem, pare: a migration 01 assume que
-- não existem e o conteúdo atual precisa ser avaliado antes.

\echo ''
\echo '############################################################'
\echo '# 2b. ESCRITA DUPLA — mesma tabela em `public` e em `secullum`?'
\echo '############################################################'
select p.tablename as name,
       'existe nos DOIS schemas' as situacao,
       (select n_live_tup from pg_stat_user_tables t
         where t.schemaname='public'   and t.relname=p.tablename) as linhas_public,
       (select n_live_tup from pg_stat_user_tables t
         where t.schemaname='secullum' and t.relname=p.tablename) as linhas_secullum
from pg_tables p
where p.schemaname = 'public'
  and exists (select 1 from pg_tables s
              where s.schemaname='secullum' and s.tablename = p.tablename)
order by 1;
-- QUALQUER LINHA AQUI É BLOQUEANTE. Significa migração em andamento com
-- escrita dupla. A migration 03 move `public` por cima do que já está em
-- `secullum` e o ALTER TABLE SET SCHEMA falha, ou pior: as duas cópias
-- divergem em silêncio. Decidir qual lado é a verdade ANTES de aplicar.

\echo ''
\echo '############################################################'
\echo '# 3. O QUE A MIGRATION 00 VAI BLINDAR (PascalCase em public)'
\echo '############################################################'
select tablename as tabela,
       rowsecurity as rls_hoje,
       has_table_privilege('anon', format('%I.%I', schemaname, tablename), 'SELECT') as anon_le_hoje
from pg_tables
where schemaname = 'public' and tablename ~ '^[A-Z]'
order by 1;
-- Vazio aqui = A CONVENÇÃO NÃO É PascalCase. Pare e me avise: o predicado das
-- migrations 00 e 03 precisa ser trocado antes de aplicar.

\echo ''
\echo '############################################################'
\echo '# 4. O QUE A MIGRATION 03 VAI MOVER PARA `secullum`'
\echo '############################################################'
select tablename as tabela,
       (select count(*) from pg_attribute a
         where a.attrelid = format('%I.%I', schemaname, tablename)::regclass
           and a.attnum > 0 and not a.attisdropped) as colunas,
       pg_size_pretty(pg_total_relation_size(format('%I.%I', schemaname, tablename)::regclass)) as tamanho
from pg_tables
where schemaname = 'public' and tablename ~ '^[A-Z]'
order by 1;

\echo ''
\echo '############################################################'
\echo '# 5. O QUE A MIGRATION 03 VAI MOVER PARA `app`  <<< REVISE LINHA A LINHA'
\echo '############################################################'
select tablename as tabela,
       rowsecurity as rls_hoje,
       exists (select 1 from pg_attribute a
                where a.attrelid = format('%I.%I', schemaname, tablename)::regclass
                  and a.attname = 'tenant_id' and a.attnum > 0 and not a.attisdropped) as ja_tem_tenant_id,
       pg_size_pretty(pg_total_relation_size(format('%I.%I', schemaname, tablename)::regclass)) as tamanho
from pg_tables
where schemaname = 'public' and tablename !~ '^[A-Z]'
order by 1;
-- A migration 03 move TUDO que sobrar em `public` para `app`. Se aparecer aqui
-- alguma tabela que não deveria se mover, edite a lista de exclusão da migration
-- ANTES de aplicar.

\echo ''
\echo '############################################################'
\echo '# 6. COLISÕES DE NOME COM O MODELO NOVO'
\echo '############################################################'
select t.tablename as tabela_existente,
       'a migration 04/05 cria app.' || t.tablename || ' — vai colidir' as alerta
from pg_tables t
where t.schemaname = 'public'
  and t.tablename in (
    'tenant','tenant_member','user_scope','domain_permission',
    'company','unit','unit_secullum_map','department','employee',
    'employee_pii','employee_compensation','employee_position','leave_period',
    'contact','unit_responsible','deviation_type','deviation_type_config','expected_workday',
    'detection_run','report_cycle','deviation_event','justification',
    'alert_rule','alert_rule_target','alert_queue','alert_sent',
    'payroll_period','cost_center','payroll_entry','payroll_charge','workforce_movement',
    'financial_threshold','document_type','document','occupational_exam',
    'financial_agreement','agreement_installment','integration','integration_secret',
    'sync_run','file_import','audit_log','ai_query','metric')
order by 1;
-- Qualquer linha aqui é bloqueante: a 03 move a sua para `app` e a 04+ tenta
-- criar uma com o mesmo name. Decidir antes: renomear a existente, ou adaptar
-- a nossa para reaproveitar a de vocês.

\echo ''
\echo '############################################################'
\echo '# 7. DEPENDÊNCIAS EM `public` (views/funções que usam o que vai mover)'
\echo '############################################################'
select distinct
       dependente.relname as objeto_dependente,
       dependente.relkind as type,
       source.relname     as depende_de
from pg_depend d
join pg_rewrite r  on r.oid = d.objid
join pg_class dependente on dependente.oid = r.ev_class
join pg_class source     on source.oid = d.refobjid
join pg_namespace n      on n.oid = source.relnamespace
where n.nspname = 'public'
  and dependente.relname <> source.relname
  and dependente.relkind in ('v','m')
order by 1;
-- View segue a tabela automaticamente no ALTER TABLE SET SCHEMA. O que NÃO
-- segue é código de aplicação com o name cravado — esse é o trabalho do PR.

\echo ''
\echo '############################################################'
\echo '# 8. TABELAS SEM CHAVE PRIMÁRIA (upsert idempotente impossível)'
\echo '############################################################'
select t.tablename
from pg_tables t
where t.schemaname = 'public'
  and not exists (
    select 1 from pg_constraint c
    where c.conrelid = format('%I.%I', t.schemaname, t.tablename)::regclass
      and c.contype = 'p')
order by 1;

\echo ''
\echo '############################################################'
\echo '# 9. QUALIDADE DE DADO — SÓ AGREGADO, NENHUMA LINHA'
\echo '############################################################'
do $$
declare
  v_total          bigint;
  v_diverg         bigint;
  v_sem_dep        bigint;
  v_sem_horario    bigint;
  v_ativos         bigint;
begin
  if to_regclass('public."Funcionario"') is null then
    raise notice 'Tabela public."Funcionario" não encontrada — pulando esta seção.';
    return;
  end if;

  execute 'select count(*) from public."Funcionario"' into v_total;
  raise notice 'Funcionários (todos): %', v_total;

  -- Ativos, se a coluna existir
  if exists (select 1 from information_schema.columns
             where table_schema='public' and table_name='Funcionario' and column_name='Ativo') then
    execute 'select count(*) from public."Funcionario" where "Ativo"' into v_ativos;
    raise notice 'Funcionários ativos: %', v_ativos;
  end if;

  -- A divergência Empresa x Departamento — a premissa dos 26%
  if exists (select 1 from information_schema.columns
             where table_schema='public' and table_name='Funcionario' and column_name='DepartamentoId')
     and to_regclass('public."Departamento"') is not null
     and exists (select 1 from information_schema.columns
                 where table_schema='public' and table_name='Departamento' and column_name='EmpresaId')
  then
    execute '
      select count(*) from public."Funcionario" f
      join public."Departamento" d on d."Id" = f."DepartamentoId"
      where d."EmpresaId" is distinct from f."EmpresaId"' into v_diverg;
    raise notice 'Funcionários com Empresa <> Empresa do Departamento: % (% %%)',
      v_diverg, round(100.0 * v_diverg / nullif(v_total,0), 1);

    execute 'select count(*) from public."Funcionario" where "DepartamentoId" is null' into v_sem_dep;
    raise notice 'Funcionários sem department: %', v_sem_dep;
  else
    raise notice 'Colunas de Empresa/Departamento não encontradas com os nomes esperados — conferir manualmente.';
  end if;

  -- Cobertura de horário: quem não tem jornada não pode ser apurado
  if exists (select 1 from information_schema.columns
             where table_schema='public' and table_name='Funcionario' and column_name='HorarioId')
  then
    execute 'select count(*) from public."Funcionario" where "HorarioId" is null' into v_sem_horario;
    raise notice 'Funcionários sem horário vinculado: %', v_sem_horario;
  end if;
end $$;

\echo ''
\echo '--- Distribuição de horários (mede o risco de escala cíclica / 12x36)'
select case when to_regclass('public."HorarioDia"') is null
            then 'tabela HorarioDia não encontrada' end as aviso
where to_regclass('public."HorarioDia"') is null;

\echo ''
\echo '############################################################'
\echo '# 10. VOLUMETRIA'
\echo '############################################################'
select schemaname, relname as tabela, n_live_tup as linhas_aprox,
       pg_size_pretty(pg_total_relation_size(relid)) as tamanho
from pg_stat_user_tables
where schemaname = 'public'
order by n_live_tup desc
limit 40;

\echo ''
\echo '############################################################'
\echo '# 11. EXPOSIÇÃO ATUAL — resumo'
\echo '############################################################'
select count(*) filter (where not rowsecurity)                    as sem_rls,
       count(*) filter (where has_table_privilege('anon', format('%I.%I', schemaname, tablename), 'SELECT')) as anon_le,
       count(*)                                                    as total_em_public
from pg_tables where schemaname = 'public';

select c.relname as view_sem_security_invoker
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'v'
  and not coalesce(array_to_string(c.reloptions, ',') like '%security_invoker%', false)
order by 1;
-- Toda view listada acima roda com privilégio do DONO e ignora a RLS das
-- tabelas base. Se houver alguma, é o achado mais urgente deste relatório.

\echo ''
\echo '=== FIM DO PRÉ-VOO — nenhum dado pessoal neste relatório ==='
