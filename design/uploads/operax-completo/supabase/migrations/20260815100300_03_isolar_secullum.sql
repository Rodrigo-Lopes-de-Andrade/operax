-- ============================================================================
-- OperaX — 03. ISOLATE THE SECULLUM MIRROR
-- ----------------------------------------------------------------------------
-- Move toda tabela literal do Secullum (PascalCase) de `public` para `secullum`.
-- Depois disso o PostgREST não alcança mais essas tabelas por nenhum caminho:
-- não é policy que protege, é topologia. Erro de policy deixa de ser vazamento
-- de RG, endereço e filiação.
--
-- >>> QUEBRA O WORKER — aplicar junto com o ajuste de código no mesmo PR <<<
-- O worker passa a apontar para o schema `secullum`:
--   backend/operax/core/db.py: pool com `options='-c search_path=secullum'`
--   (conexão direta com psycopg — upsert em lote é bem mais rápido que PostgREST)
--
-- O painel NÃO lê `secullum`. Nunca. O motor de detecção lê com service_role e
-- grava em `app`. O dashboard só enxerga `app` através das views de `public`.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Move as tabelas e adiciona tenant_id
-- ---------------------------------------------------------------------------
do $$
declare
  r           record;
  v_tenant_id uuid;
  movidas     int := 0;
begin
  select id into v_tenant_id from app.tenant where slug = 'kastro-park';
  if v_tenant_id is null then
    raise exception 'Tenant kastro-park não encontrado. Rode a migration 02 antes desta.';
  end if;

  for r in
    select tablename from pg_tables
    where schemaname = 'public' and tablename ~ '^[A-Z]'
    order by tablename
  loop
    execute format('alter table public.%I set schema secullum', r.tablename);

    -- Multi-tenant: cada cliente OperaX tem sua própria instância de Secullum.
    execute format(
      'alter table secullum.%I add column if not exists tenant_id uuid references app.tenant(id) on delete cascade',
      r.tablename);
    execute format('update secullum.%I set tenant_id = %L where tenant_id is null', r.tablename, v_tenant_id);
    execute format('alter table secullum.%I alter column tenant_id set not null', r.tablename);
    execute format('alter table secullum.%I alter column tenant_id set default %L', r.tablename, v_tenant_id);
    execute format('create index if not exists %I on secullum.%I (tenant_id)',
                   lower(r.tablename) || '_tenant_idx', r.tablename);

    -- Belt and airbag: mesmo inalcançável pelo PostgREST, RLS fica ligada.
    execute format('alter table secullum.%I enable row level security', r.tablename);
    execute format('revoke all on table secullum.%I from anon, authenticated', r.tablename);
    execute format('grant all on table secullum.%I to service_role', r.tablename);

    movidas := movidas + 1;
    raise notice 'movida para secullum: % (tenant_id adicionado)', r.tablename;
  end loop;

  if movidas = 0 then
    raise warning 'No tables PascalCase encontrada em public. Confirme a convenção de nomes com o diagnóstico (scripts/00_diagnostico.sql).';
  else
    raise notice '% tabela(s) isolada(s). ATUALIZE O WORKER para o schema secullum.', movidas;
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 1b. Tabelas NOSSAS que sobraram em public (company_evento_status,
--     funcionario_evento_status e afins) vão para `app`. Depois disto, `public`
--     fica só com view e função — o que a event trigger da migration 01 mantém.
-- ---------------------------------------------------------------------------
do $$
declare
  r           record;
  v_tenant_id uuid;
begin
  select id into v_tenant_id from app.tenant where slug = 'kastro-park';

  for r in
    select tablename from pg_tables
    where schemaname = 'public'
      and tablename not in ('schema_migrations')
    order by tablename
  loop
    execute format('alter table public.%I set schema app', r.tablename);

    if not exists (
      select 1 from information_schema.columns
      where table_schema = 'app' and table_name = r.tablename and column_name = 'tenant_id'
    ) then
      execute format('alter table app.%I add column tenant_id uuid references app.tenant(id) on delete cascade', r.tablename);
      execute format('update app.%I set tenant_id = %L where tenant_id is null', r.tablename, v_tenant_id);
      execute format('alter table app.%I alter column tenant_id set default %L', r.tablename, v_tenant_id);
      execute format('create index if not exists %I on app.%I (tenant_id)', r.tablename || '_tenant_idx', r.tablename);
    end if;

    execute format('alter table app.%I enable row level security', r.tablename);
    execute format('revoke all on table app.%I from anon', r.tablename);
    execute format('grant select on table app.%I to authenticated', r.tablename);

    -- Policy padrão de tenant. Refine por tabela se a regra for mais estreita.
    execute format($p$
      drop policy if exists %I on app.%I;
      create policy %I on app.%I for select to authenticated
        using (util.has_tenant(tenant_id));
    $p$, r.tablename || '_tenant_read', r.tablename,
         r.tablename || '_tenant_read', r.tablename);

    raise notice 'movida para app: % (tenant_id + RLS)', r.tablename;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 2. Sequences acompanham as tabelas
-- ---------------------------------------------------------------------------
do $$
declare r record;
begin
  for r in
    select sequence_name from information_schema.sequences
    where sequence_schema = 'public' and sequence_name ~ '^[A-Z]'
  loop
    execute format('alter sequence public.%I set schema secullum', r.sequence_name);
    execute format('revoke all on sequence secullum.%I from anon, authenticated', r.sequence_name);
    execute format('grant  all on sequence secullum.%I to service_role', r.sequence_name);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 3. Isolation proof — fails the migration if anything escaped
-- ---------------------------------------------------------------------------
do $$
declare n int;
begin
  select count(*) into n
  from pg_tables where schemaname = 'public' and tablename ~ '^[A-Z]';
  if n > 0 then
    raise exception 'ISOLAMENTO INCOMPLETO: % tabela(s) PascalCase ainda em public', n;
  end if;

  -- Pelo OID, não pelo name montado: o planner pode reordenar predicados e
  -- avaliar has_table_privilege() em linhas de outros schemas, o que quebraria
  -- com "relation não existe" em vez de responder a question.
  select count(*) into n
  from pg_class c
  join pg_namespace ns on ns.oid = c.relnamespace
  where ns.nspname = 'secullum'
    and c.relkind in ('r','p')
    and (has_table_privilege('anon', c.oid, 'SELECT')
      or has_table_privilege('authenticated', c.oid, 'SELECT'));
  if n > 0 then
    raise exception 'ISOLAMENTO FALHOU: % tabela(s) em secullum legíveis por anon/authenticated', n;
  end if;

  raise notice 'OK: espelho do Secullum isolado e inalcançável pelo PostgREST.';
end $$;
