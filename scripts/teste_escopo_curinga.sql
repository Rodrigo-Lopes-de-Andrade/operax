-- ============================================================================
-- OperaX — SCOPE WILDCARD GATE (the six lines of SPEC-USUARIOS §3, sprint U1)
-- ----------------------------------------------------------------------------
-- `util.can_see_unit` and `util.can_see_company` read a NULL column of
-- `app.user_scope` as "any". Migration `usuarios_escopo_constraint` closes both
-- wildcards with two checks and a unique index, without touching the functions.
-- This file exercises them against the migrated database:
--   1. both NULL                     -> refused (23514, escopo_nao_vazio)
--   2. unit_id with company_id NULL  -> refused (23514, escopo_unidade_tem_empresa)
--   3. duplicate                     -> refused (23505, user_scope_sem_duplicata),
--                                       including the company-only duplicate,
--                                       which only `coalesce` catches
--   4. no row                        -> 0 units AND 0 companies
--   5. unit_id + company_id          -> 1 unit and 1 company
--   6. company only (POSITIVE)       -> the units of that company, not the other's
--
-- ⛔ ROLE PINNED TO `unit_supervisor`. `owner`, `executive`, `hr` and
-- `personnel` hit a role shortcut in both functions before `user_scope` is
-- read, so with them lines 4–6 would measure the shortcut, not the scope.
-- The fixture asserts the pin before anything else.
--
-- Refusals assert WHICH constraint refused, not just that something did: with
-- line 2's check missing, line 2 must not stay green on another error.
--
-- Visibility is read as the user (`authenticated` + the JWT sub), calling the
-- functions over a fixed id list, so no table grant enters the measurement.
--
-- Runs in a rolled-back transaction. Leaves nothing behind.
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/teste_escopo_curinga.sql
-- ============================================================================

begin;

create or replace function pg_temp.assert_eq(rotulo text, obtido text, esperado text)
returns void language plpgsql as $$
begin
  if obtido is distinct from esperado then
    raise exception 'FALHA [%]: esperado %, obtido %', rotulo, esperado, obtido;
  end if;
  raise notice '  ok  % (%)', rotulo, obtido;
end $$;

-- Returns 'sqlstate:constraint' of the refusal; raises if the statement passed.
create or replace function pg_temp.recusado_por(rotulo text, sql_text text)
returns text language plpgsql as $$
declare
  v_state text;
  v_constraint text;
begin
  begin
    execute sql_text;
  exception when others then
    get stacked diagnostics v_state = returned_sqlstate, v_constraint = constraint_name;
    return v_state || ':' || coalesce(nullif(v_constraint, ''), sqlerrm);
  end;
  raise exception 'FALHA [%]: deveria ter sido recusado e passou', rotulo;
end $$;

-- ---------------------------------------------------------------------------
-- Fixture: 1 tenant, 3 companies, 2 units (U1 in E1, U2 in E2; E3 has none),
-- one user pinned to `unit_supervisor`.
-- ---------------------------------------------------------------------------
insert into auth.users (id, email) values
  ('c0000000-0000-0000-0000-00000000005a', 'supervisor.curinga@teste');

insert into app.tenant (id, slug, name) values
  ('c0000000-0000-0000-0000-0000000000a1', 'tenant-curinga', 'Cliente Curinga');

insert into app.tenant_member (tenant_id, user_id, role) values
  ('c0000000-0000-0000-0000-0000000000a1', 'c0000000-0000-0000-0000-00000000005a', 'unit_supervisor');

insert into app.company (id, tenant_id, legal_name) values
  ('c0000000-0000-0000-0000-0000000000e1', 'c0000000-0000-0000-0000-0000000000a1', 'Empresa Curinga 1 LTDA'),
  ('c0000000-0000-0000-0000-0000000000e2', 'c0000000-0000-0000-0000-0000000000a1', 'Empresa Curinga 2 LTDA'),
  ('c0000000-0000-0000-0000-0000000000e3', 'c0000000-0000-0000-0000-0000000000a1', 'Empresa Curinga 3 LTDA');

insert into app.unit (id, tenant_id, company_id, code, name) values
  ('c0000000-0000-0000-0000-0000000000b1', 'c0000000-0000-0000-0000-0000000000a1',
   'c0000000-0000-0000-0000-0000000000e1', 'CUR-1', 'Unidade Curinga 1'),
  ('c0000000-0000-0000-0000-0000000000b2', 'c0000000-0000-0000-0000-0000000000a1',
   'c0000000-0000-0000-0000-0000000000e2', 'CUR-2', 'Unidade Curinga 2');

-- What the user sees, as the user: 'units=<n> companies=<n> [<codes>]'.
create or replace function pg_temp.visivel() returns text language sql as $$
  select format('units=%s companies=%s [%s]',
    (select count(*) from (values ('c0000000-0000-0000-0000-0000000000b1'::uuid),
                                  ('c0000000-0000-0000-0000-0000000000b2'::uuid)) v(id)
      where util.can_see_unit(v.id)),
    (select count(*) from (values ('c0000000-0000-0000-0000-0000000000e1'::uuid),
                                  ('c0000000-0000-0000-0000-0000000000e2'::uuid),
                                  ('c0000000-0000-0000-0000-0000000000e3'::uuid)) v(id)
      where util.can_see_company(v.id)),
    (select coalesce(string_agg(v.label, ',' order by v.label), '')
       from (values ('b1', 'c0000000-0000-0000-0000-0000000000b1'::uuid, true),
                    ('b2', 'c0000000-0000-0000-0000-0000000000b2'::uuid, true),
                    ('e1', 'c0000000-0000-0000-0000-0000000000e1'::uuid, false),
                    ('e2', 'c0000000-0000-0000-0000-0000000000e2'::uuid, false),
                    ('e3', 'c0000000-0000-0000-0000-0000000000e3'::uuid, false)) v(label, id, is_unit)
      where case when v.is_unit then util.can_see_unit(v.id) else util.can_see_company(v.id) end));
$$;

do $$ begin
  perform pg_temp.assert_eq('papel fixado em unit_supervisor (sem atalho por papel)',
    (select string_agg(role::text, ',') from app.tenant_member
      where user_id = 'c0000000-0000-0000-0000-00000000005a'), 'unit_supervisor');
end $$;

\echo '--- 1. dois nulos'
do $$ begin
  perform pg_temp.assert_eq('1. company_id e unit_id nulos: recusada',
    pg_temp.recusado_por('1', $q$
      insert into app.user_scope (tenant_id, user_id, company_id, unit_id) values
        ('c0000000-0000-0000-0000-0000000000a1', 'c0000000-0000-0000-0000-00000000005a', null, null)
    $q$), '23514:escopo_nao_vazio');
end $$;

\echo '--- 2. unidade sem empresa'
do $$ begin
  perform pg_temp.assert_eq('2. unit_id com company_id nulo: recusada',
    pg_temp.recusado_por('2', $q$
      insert into app.user_scope (tenant_id, user_id, company_id, unit_id) values
        ('c0000000-0000-0000-0000-0000000000a1', 'c0000000-0000-0000-0000-00000000005a',
         null, 'c0000000-0000-0000-0000-0000000000b1')
    $q$), '23514:escopo_unidade_tem_empresa');
end $$;

\echo '--- 3. duplicata'
savepoint linha_3;
insert into app.user_scope (tenant_id, user_id, company_id, unit_id) values
  ('c0000000-0000-0000-0000-0000000000a1', 'c0000000-0000-0000-0000-00000000005a',
   'c0000000-0000-0000-0000-0000000000e1', 'c0000000-0000-0000-0000-0000000000b1'),
  ('c0000000-0000-0000-0000-0000000000a1', 'c0000000-0000-0000-0000-00000000005a',
   'c0000000-0000-0000-0000-0000000000e3', null);
do $$ begin
  perform pg_temp.assert_eq('3a. empresa + unidade repetidas: recusada pelo índice',
    pg_temp.recusado_por('3a', $q$
      insert into app.user_scope (tenant_id, user_id, company_id, unit_id) values
        ('c0000000-0000-0000-0000-0000000000a1', 'c0000000-0000-0000-0000-00000000005a',
         'c0000000-0000-0000-0000-0000000000e1', 'c0000000-0000-0000-0000-0000000000b1')
    $q$), '23505:user_scope_sem_duplicata');
  -- Only `coalesce` catches this one: in a plain unique index NULLs are distinct.
  perform pg_temp.assert_eq('3b. só empresa repetida (unit_id nulo): recusada pelo índice',
    pg_temp.recusado_por('3b', $q$
      insert into app.user_scope (tenant_id, user_id, company_id, unit_id) values
        ('c0000000-0000-0000-0000-0000000000a1', 'c0000000-0000-0000-0000-00000000005a',
         'c0000000-0000-0000-0000-0000000000e3', null)
    $q$), '23505:user_scope_sem_duplicata');
end $$;
rollback to savepoint linha_3;

\echo '--- 4. supervisor sem linha'
set local role authenticated;
set local request.jwt.claim.sub = 'c0000000-0000-0000-0000-00000000005a';
do $$ begin
  perform pg_temp.assert_eq('4. sem linha de escopo: 0 unidades e 0 empresas',
    pg_temp.visivel(), 'units=0 companies=0 []');
end $$;
reset request.jwt.claim.sub;
reset role;

\echo '--- 5. unidade + empresa'
savepoint linha_5;
insert into app.user_scope (tenant_id, user_id, company_id, unit_id) values
  ('c0000000-0000-0000-0000-0000000000a1', 'c0000000-0000-0000-0000-00000000005a',
   'c0000000-0000-0000-0000-0000000000e1', 'c0000000-0000-0000-0000-0000000000b1');
set local role authenticated;
set local request.jwt.claim.sub = 'c0000000-0000-0000-0000-00000000005a';
do $$ begin
  perform pg_temp.assert_eq('5. unit_id + company_id: 1 unidade e 1 empresa',
    pg_temp.visivel(), 'units=1 companies=1 [b1,e1]');
end $$;
reset request.jwt.claim.sub;
reset role;
rollback to savepoint linha_5;

\echo '--- 6. só empresa (positivo)'
savepoint linha_6;
insert into app.user_scope (tenant_id, user_id, company_id, unit_id) values
  ('c0000000-0000-0000-0000-0000000000a1', 'c0000000-0000-0000-0000-00000000005a',
   'c0000000-0000-0000-0000-0000000000e2', null);
set local role authenticated;
set local request.jwt.claim.sub = 'c0000000-0000-0000-0000-00000000005a';
do $$ begin
  perform pg_temp.assert_eq('6. escopo só por empresa: vê a unidade dela, não a da outra',
    pg_temp.visivel(), 'units=1 companies=1 [b2,e2]');
end $$;
reset request.jwt.claim.sub;
reset role;
rollback to savepoint linha_6;

rollback;
\echo '=== ESCOPO CURINGA OK (seis linhas)'
