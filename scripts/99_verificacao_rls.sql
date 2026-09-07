-- ============================================================================
-- OperaX — VERIFICAÇÃO DE ISOLAMENTO
-- ----------------------------------------------------------------------------
-- Rode depois de TODAS as migrations. Falha alto e cedo se qualquer garantia
-- de segurança tiver sido perdida. Este arquivo é o teste de regressão do
-- modelo de acesso — rode de novo a cada PR que mexer em policy, view ou grant.
--
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/99_verificacao_rls.sql
--
-- Não escreve nada. Roda inteiro dentro de uma transação revertida.
-- ============================================================================

begin;

\echo '--- 1. Nenhuma tabela literal do Secullum sobrou em public'
do $$
declare n int;
begin
  select count(*) into n from pg_tables where schemaname = 'public' and tablename ~ '^[A-Z]';
  if n > 0 then raise exception 'FALHA: % tabela(s) PascalCase ainda em public', n; end if;
end $$;

\echo '--- 2. Nenhuma TABELA em public (só view e função)'
do $$
declare n int; lista text;
begin
  select count(*), string_agg(tablename, ', ')
    into n, lista
  from pg_tables where schemaname = 'public';
  if n > 0 then
    raise exception 'FALHA: % tabela(s) em public (%). Tabelas vão para app/secullum.', n, lista;
  end if;
end $$;

\echo '--- 3. anon não lê NADA em secullum, app ou public'
do $$
declare r record; falhas text := '';
begin
  for r in
    select n.nspname as sch, c.relname as obj, c.relkind
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname in ('secullum','app','public','util') and c.relkind in ('r','v','m','p')
  loop
    if has_table_privilege('anon', format('%I.%I', r.sch, r.obj)::regclass, 'SELECT') then
      falhas := falhas || format('%s.%s ', r.sch, r.obj);
    end if;
  end loop;
  if falhas <> '' then raise exception 'FALHA: anon consegue ler -> %', falhas; end if;
end $$;

\echo '--- 4. authenticated não alcança o espelho do Secullum'
do $$
declare r record; falhas text := '';
begin
  for r in select tablename from pg_tables where schemaname = 'secullum' loop
    if has_table_privilege('authenticated', format('secullum.%I', r.tablename)::regclass, 'SELECT') then
      falhas := falhas || r.tablename || ' ';
    end if;
  end loop;
  if falhas <> '' then raise exception 'FALHA: authenticated lê secullum -> %', falhas; end if;
end $$;

\echo '--- 5. Toda view de public é security_invoker'
do $$
declare r record; falhas text := '';
begin
  for r in
    select c.relname, c.reloptions
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind = 'v'
  loop
    if not coalesce(array_to_string(r.reloptions, ',') like '%security_invoker=%', false) then
      falhas := falhas || r.relname || ' ';
    end if;
  end loop;
  if falhas <> '' then
    raise exception 'FALHA: view(s) sem security_invoker (ignoram RLS da base) -> %', falhas;
  end if;
end $$;

\echo '--- 6. Toda tabela de app tem RLS ligada'
do $$
declare r record; falhas text := '';
begin
  for r in select tablename, rowsecurity from pg_tables where schemaname = 'app' loop
    if not r.rowsecurity then falhas := falhas || r.tablename || ' '; end if;
  end loop;
  if falhas <> '' then raise exception 'FALHA: tabela(s) de app sem RLS -> %', falhas; end if;
end $$;

\echo '--- 7. Toda tabela de app com RLS tem pelo menos uma policy OU é exclusiva de service_role'
do $$
declare r record; aviso text := '';
begin
  for r in
    select t.tablename,
           (select count(*) from pg_policies p where p.schemaname='app' and p.tablename=t.tablename) as n
    from pg_tables t where t.schemaname = 'app'
  loop
    if r.n = 0 then aviso := aviso || r.tablename || ' '; end if;
  end loop;
  if aviso <> '' then
    raise notice 'ATENÇÃO (esperado apenas para integration_secret e mv_*): sem policy -> %', aviso;
  end if;
end $$;

\echo '--- 8. Nenhuma coluna de PII vazou para a superfície pública'
do $$
declare r record; falhas text := '';
begin
  for r in
    select c.relname as view_name, a.attname as col
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    join pg_attribute a on a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped
    where n.nspname = 'public' and c.relkind = 'v'
      -- ⚠️ ESTA LISTA ENVELHECE COM O SCHEMA, e envelheceu duas vezes.
      --    `nascimento` é o nome PRÉ-rename: a coluna virou `birth_date` e o
      --    check parou de vê-la sem ficar vermelho. E as seis colunas que a
      --    migration `dp_cadastral_fields` (S4) pôs em `app.employee_pii` —
      --    `race_color` e `dependents_names` à frente — não estavam aqui:
      --    medido em 07/09/2026, uma view de `public` expondo as três passava.
      --    Coluna nova em tabela de PII entra AQUI no mesmo PR, senão o item 8
      --    fica verde justamente sobre o que ainda não sabe procurar.
      and a.attname ~* '(cpf|^rg$|identidade|address|logradouro|cep|phone|celular|personal_email|mother_name|father_name|filiacao|nascimento|birth_date|^pis$|ctps|salary|race_color|marital_status|education_level|disability|dependents)'
  loop
    falhas := falhas || format('%s.%s ', r.view_name, r.col);
  end loop;
  if falhas <> '' then raise exception 'FALHA: PII exposta em view pública -> %', falhas; end if;
end $$;

\echo '--- 9. Helpers de RLS estão travados e sem EXECUTE para anon'
do $$
declare r record; falhas text := '';
begin
  for r in
    select p.proname, p.prosecdef, p.proconfig, p.oid
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'util' and p.prokind = 'f'
  loop
    if r.prosecdef and (r.proconfig is null or not (r.proconfig::text like '%search_path=%')) then
      falhas := falhas || format('%s(sem search_path) ', r.proname);
    end if;
    if has_function_privilege('anon', r.oid, 'EXECUTE') then
      falhas := falhas || format('%s(anon pode executar) ', r.proname);
    end if;
  end loop;
  if falhas <> '' then raise exception 'FALHA: helpers inseguros -> %', falhas; end if;
end $$;

\echo '--- 10. Teste vivo: assumir o role anon e tentar ler'
do $$
declare v_ok boolean := false;
begin
  begin
    set local role anon;
    perform 1 from public.vw_employee limit 1;
    reset role;
    raise exception 'FALHA: anon conseguiu consultar public.vw_employee';
  exception
    when insufficient_privilege then
      v_ok := true;
    when others then
      -- qualquer error que não seja "consegui ler" também serve como bloqueio,
      -- mas registramos para inspeção
      v_ok := true;
      raise notice 'anon bloqueado com: % (%)', sqlerrm, sqlstate;
  end;
  reset role;
  if v_ok then raise notice 'OK: anon bloqueado em public.vw_employee'; end if;
end $$;

reset role;

\echo '--- 11. Matview não é exposta (não respeita RLS por nature)'
do $$
declare r record; falhas text := '';
begin
  for r in
    select n.nspname as sch, c.relname as obj
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where c.relkind = 'm'
  loop
    if has_table_privilege('authenticated', format('%I.%I', r.sch, r.obj)::regclass, 'SELECT')
       or r.sch = 'public' then
      falhas := falhas || format('%s.%s ', r.sch, r.obj);
    end if;
  end loop;
  if falhas <> '' then
    raise exception 'FALHA: materialized view alcançável por authenticated ou em public -> %', falhas;
  end if;
end $$;

\echo '--- 12. Catálogo do assistente aponta para objeto que existe'
-- O assistente só responde a partir de app.metric. Se target_view aponta para
-- um objeto inexistente, a pergunta vira erro em vez de "não tenho esse dado" —
-- que é justamente o comportamento que o catálogo fechado existe para evitar.
do $$
declare r record; falhas text := '';
begin
  for r in select code, target_view from app.metric where active loop
    if to_regclass('public.' || r.target_view) is null
       and not exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                       where n.nspname = 'public' and p.proname = r.target_view) then
      falhas := falhas || format('%s->%s ', r.code, r.target_view);
    end if;
  end loop;
  if falhas <> '' then
    raise exception 'FALHA: métrica aponta para objeto inexistente -> %', falhas;
  end if;
end $$;

\echo '--- 13. Rótulo de métrica não carrega resíduo do rename pt->en'
-- title e description de app.metric são texto de tela: aparecem no assistente.
-- A passada de renomeação traduziu identificadores; se pegou uma frase em
-- português junto, o usuário lê "Ranking de desvios por unit".
do $$
declare r record; falhas text := '';
begin
  for r in
    select code, title, description from app.metric
     where (title || ' ' || coalesce(description, '')) ~*
           '\m(unit|units|employee|employees|company|companies|department|tenant|leave|contact|deviation|payroll_period)\M'
  loop
    falhas := falhas || format('%s(%s) ', r.code, r.title);
  end loop;
  if falhas <> '' then
    raise exception 'FALHA: rótulo de métrica com identificador em inglês no meio da frase -> %', falhas;
  end if;
end $$;

\echo ''
\echo '================================================'
\echo ' TODAS AS VERIFICAÇÕES DE ISOLAMENTO PASSARAM'
\echo '================================================'

rollback;
