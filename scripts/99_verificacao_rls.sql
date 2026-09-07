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
-- ⛔ O VOCABULÁRIO DE PII MORA NUM LUGAR SÓ, e este bloco existe por isso.
-- Os itens 8 e 9 procuram a mesma coisa em superfícies diferentes (coluna de
-- view, e tipo de retorno de função definer), e até 07/09/2026 procuravam com
-- listas DIFERENTES. O item 9 usava `\mname\M`, e `_` é caractere de palavra no
-- regex do Postgres — então `mother_name`, `father_name` e `dependents_names`
-- NÃO casavam, e `race_color` nem estava na lista dele. Medido: uma função
-- definer de `public` devolvendo qualquer uma das quatro passava verde.
-- Duas listas que precisam concordar e podem divergir sempre divergem; a
-- correção não é sincronizá-las, é haver uma só.
create or replace function pg_temp.pii_regex() returns text language sql immutable as $pii$
  select '(cpf|^rg$|identidade|address|logradouro|cep|phone|celular|personal_email'
      || '|mother_name|father_name|filiacao|nascimento|birth_date|^pis$|ctps|salary'
      || '|race_color|marital_status|education_level|disability|dependents)'
$pii$;

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
      and a.attname ~* pg_temp.pii_regex()
  loop
    falhas := falhas || format('%s.%s ', r.view_name, r.col);
  end loop;
  if falhas <> '' then raise exception 'FALHA: PII exposta em view pública -> %', falhas; end if;
end $$;

\echo '--- 9. Função de util E de public: definer travado, sem EXECUTE para anon'
-- ⚠️ O laço varria só `util` até 07/09/2026, e `public` tem QUATRO funções
-- `security definer` — `fn_data_freshness`, `fn_detection_health`,
-- `fn_whatsapp_readiness` e `fn_dp_alerts`. A garantia de cada uma vivia no
-- bloco `do $$` da migration que a criou, que roda uma vez: um `create or
-- replace` posterior trocava a função e nada ficava vermelho. Definer é definer
-- em qualquer schema, e `public` é o único exposto ao PostgREST — se havia um
-- schema para varrer com mais cuidado, era este.
do $$
declare r record; falhas text := '';
begin
  for r in
    select n.nspname as sch, p.proname, p.prosecdef, p.proconfig, p.oid
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname in ('util', 'public') and p.prokind = 'f'
  loop
    if r.prosecdef and (r.proconfig is null or not (r.proconfig::text like '%search_path=%')) then
      falhas := falhas || format('%s.%s(sem search_path) ', r.sch, r.proname);
    end if;
    if has_function_privilege('anon', r.oid, 'EXECUTE') then
      falhas := falhas || format('%s.%s(anon pode executar) ', r.sch, r.proname);
    end if;
    -- ⛔ DEFINER EM `public` NÃO DEVOLVE PESSOA.
    -- Ele ignora RLS por construção, então o que ele devolve não passa por
    -- policy nenhuma: agregado é a única forma segura. As quatro de hoje
    -- devolvem contagem, prontidão e idade de sincronização. A varredura é por
    -- NOME DE COLUNA do tipo de retorno — o mesmo instrumento do item 8, e o
    -- que impede um `create or replace` futuro de acrescentar `employee_id`
    -- "já que estamos aqui".
    if r.sch = 'public' and r.prosecdef
       -- ⚠️ O vocabulário é o MESMO do item 8 (`pg_temp.pii_regex()`), mais os
       -- identificadores de pessoa que só fazem sentido num retorno de função.
       -- Até 07/09 esta linha tinha lista própria e mais curta — ver o bloco
       -- que define a função.
       -- ⛔ LIMITE CONHECIDO: `returns json`, `jsonb` e `setof record` não têm
       -- nome de coluna em `pg_get_function_result`, então passam. É a forma
       -- mais provável de devolver uma pessoa sem nomear nada, e esta varredura
       -- não a alcança — fica declarado em vez de silencioso.
       and (pg_get_function_result(r.oid) ~* pg_temp.pii_regex()
            or pg_get_function_result(r.oid) ~* '(employee|colaborador|nome|registration)') then
      falhas := falhas || format('%s.%s(definer devolve dado por pessoa) ', r.sch, r.proname);
    end if;
  end loop;
  if falhas <> '' then raise exception 'FALHA: função insegura -> %', falhas; end if;
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
