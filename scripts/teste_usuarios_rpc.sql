-- ============================================================================
-- OperaX — USER RPC GATE (sprint U2 of docs/SPRINTS-USUARIOS.md)
-- ----------------------------------------------------------------------------
-- The four doors of `usuarios_rpc` — fn_convidar_usuario, fn_definir_papel,
-- fn_definir_escopo, fn_desativar_membro — exercised as `authenticated` with
-- the JWT sub of each caller, never as `anon` and never as `postgres`. What
-- each call left behind is read afterwards as `postgres`, so no policy enters
-- the measurement of the effect.
--
-- Every refusal is asserted by its CODE (`P0001:<code>`), and every refusal
-- that could have written something is followed by "nothing changed".
-- Every refusal has its positive next to it, so "the RPC refuses everything"
-- cannot pass.
--
-- Fixture (own ids, prefix d2):
--   tenant T: companies E1 (unit U1) and E2 (unit U2); owners O1 and O2, hr HR,
--             personnel PE, unit_supervisor SUP (scope E1/U1), viewer V
--             (scope E1), inactive viewer IN; NEW is in auth.users only.
--   tenant X: company XE (unit XU), owner XO — the other tenant.
--   tenant S: company SE, ONE owner SO and an hr SH — for `ultimo_owner` and
--             `owner_so_por_owner`.
--   one customer per user (`conta_em_outro_cliente`, owner decision 05/10):
--             XB active viewer of X; ZA active viewer of tenant Z, which is
--             INACTIVE; XI INACTIVE viewer of X (and nothing else).
--
-- The race between two owners, and the race between two TENANTS inviting the
-- same person, need two sessions and live in
-- `scripts/teste_usuarios_concorrencia.py`.
--
-- Runs in a rolled-back transaction. Leaves nothing behind.
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/teste_usuarios_rpc.sql
-- ============================================================================

begin;

create or replace function pg_temp.assert_eq(rotulo text, obtido anyelement, esperado anyelement)
returns void language plpgsql as $$
begin
  if obtido is distinct from esperado then
    raise exception 'FALHA [%]: esperado %, obtido %', rotulo, esperado, obtido;
  end if;
  raise notice '  ok  % (%)', rotulo, obtido;
end $$;

-- Runs `p_sql` as `authenticated` with sub = p_user. Returns 'ok' or
-- 'sqlstate:message'. The role is set outside the inner block, so a refusal
-- (which rolls the block back) does not undo it; it is reset on the way out.
create or replace function pg_temp.como(p_user uuid, p_sql text)
returns text language plpgsql as $$
declare
  v text;
begin
  perform set_config('request.jwt.claim.sub', p_user::text, true);
  set local role authenticated;
  begin
    execute p_sql;
    v := 'ok';
  exception when others then
    v := sqlstate || ':' || sqlerrm;
  end;
  reset role;
  perform set_config('request.jwt.claim.sub', '', true);
  return v;
end $$;

-- The scope of a user in a tenant, as a stable text: 'E1/-,E2/U2'.
create or replace function pg_temp.escopo(p_tenant uuid, p_user uuid)
returns text language sql as $$
  select coalesce(string_agg(
           right(us.company_id::text, 2) || '/' || coalesce(right(us.unit_id::text, 2), '-'),
           ',' order by us.company_id, us.unit_id nulls first), '')
    from app.user_scope us
   where us.tenant_id = p_tenant and us.user_id = p_user;
$$;

create or replace function pg_temp.n_audit() returns bigint language sql as $$
  select count(*) from app.audit_log
   where tenant_id in ('d2000000-0000-0000-0000-0000000000a1',
                       'd2000000-0000-0000-0000-0000000000a3');
$$;

-- ---------------------------------------------------------------------------
-- Fixture
-- ---------------------------------------------------------------------------
insert into auth.users (id, email) values
  ('d2000000-0000-0000-0000-000000000001', 'o1.u2@teste'),
  ('d2000000-0000-0000-0000-000000000002', 'o2.u2@teste'),
  ('d2000000-0000-0000-0000-000000000003', 'hr.u2@teste'),
  ('d2000000-0000-0000-0000-000000000004', 'pe.u2@teste'),
  ('d2000000-0000-0000-0000-000000000005', 'sup.u2@teste'),
  ('d2000000-0000-0000-0000-000000000006', 'v.u2@teste'),
  ('d2000000-0000-0000-0000-000000000007', 'new.u2@teste'),
  ('d2000000-0000-0000-0000-000000000008', 'xo.u2@teste'),
  ('d2000000-0000-0000-0000-000000000009', 'so.u2@teste'),
  ('d2000000-0000-0000-0000-00000000000a', 'sh.u2@teste'),
  ('d2000000-0000-0000-0000-00000000000b', 'in.u2@teste'),
  ('d2000000-0000-0000-0000-00000000000c', 'xb.u2@teste'),
  ('d2000000-0000-0000-0000-00000000000d', 'za.u2@teste'),
  ('d2000000-0000-0000-0000-00000000000e', 'xi.u2@teste');

insert into app.tenant (id, slug, name) values
  ('d2000000-0000-0000-0000-0000000000a1', 'u2-t', 'U2 T'),
  ('d2000000-0000-0000-0000-0000000000a2', 'u2-x', 'U2 X'),
  ('d2000000-0000-0000-0000-0000000000a3', 'u2-s', 'U2 S');
insert into app.tenant (id, slug, name, active) values
  ('d2000000-0000-0000-0000-0000000000a4', 'u2-z', 'U2 Z (suspenso)', false);

insert into app.company (id, tenant_id, legal_name) values
  ('d2000000-0000-0000-0000-0000000000e1', 'd2000000-0000-0000-0000-0000000000a1', 'U2 E1 LTDA'),
  ('d2000000-0000-0000-0000-0000000000e2', 'd2000000-0000-0000-0000-0000000000a1', 'U2 E2 LTDA'),
  ('d2000000-0000-0000-0000-0000000000e9', 'd2000000-0000-0000-0000-0000000000a2', 'U2 XE LTDA'),
  ('d2000000-0000-0000-0000-0000000000e3', 'd2000000-0000-0000-0000-0000000000a3', 'U2 SE LTDA');

insert into app.unit (id, tenant_id, company_id, code, name) values
  ('d2000000-0000-0000-0000-0000000000b1', 'd2000000-0000-0000-0000-0000000000a1',
   'd2000000-0000-0000-0000-0000000000e1', 'U2-1', 'U2 Unidade 1'),
  ('d2000000-0000-0000-0000-0000000000b2', 'd2000000-0000-0000-0000-0000000000a1',
   'd2000000-0000-0000-0000-0000000000e2', 'U2-2', 'U2 Unidade 2'),
  ('d2000000-0000-0000-0000-0000000000b9', 'd2000000-0000-0000-0000-0000000000a2',
   'd2000000-0000-0000-0000-0000000000e9', 'U2-X', 'U2 Unidade X');

insert into app.tenant_member (tenant_id, user_id, role, active) values
  ('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-000000000001', 'owner', true),
  ('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-000000000002', 'owner', true),
  ('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-000000000003', 'hr', true),
  ('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-000000000004', 'personnel', true),
  ('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-000000000005', 'unit_supervisor', true),
  ('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-000000000006', 'viewer', true),
  ('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-00000000000b', 'viewer', false),
  ('d2000000-0000-0000-0000-0000000000a2', 'd2000000-0000-0000-0000-000000000008', 'owner', true),
  ('d2000000-0000-0000-0000-0000000000a3', 'd2000000-0000-0000-0000-000000000009', 'owner', true),
  ('d2000000-0000-0000-0000-0000000000a3', 'd2000000-0000-0000-0000-00000000000a', 'hr', true),
  ('d2000000-0000-0000-0000-0000000000a2', 'd2000000-0000-0000-0000-00000000000c', 'viewer', true),
  ('d2000000-0000-0000-0000-0000000000a4', 'd2000000-0000-0000-0000-00000000000d', 'viewer', true),
  ('d2000000-0000-0000-0000-0000000000a2', 'd2000000-0000-0000-0000-00000000000e', 'viewer', false);

insert into app.user_scope (tenant_id, user_id, company_id, unit_id) values
  ('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-000000000005',
   'd2000000-0000-0000-0000-0000000000e1', 'd2000000-0000-0000-0000-0000000000b1'),
  ('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-000000000006',
   'd2000000-0000-0000-0000-0000000000e1', null);

\echo '--- negativos: o caminho direto continua fechado, e anon não chega às quatro'
do $$
declare
  v_sig text;
begin
  perform pg_temp.assert_eq('owner inserindo direto em app.tenant_member: permission denied for table (regressão da P1.2b)',
    split_part(pg_temp.como('d2000000-0000-0000-0000-000000000001', $q$
      insert into app.tenant_member (tenant_id, user_id, role)
      values ('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-000000000007', 'owner')
    $q$), ':', 2) like 'permission denied for table%', true);
  perform pg_temp.assert_eq('  e o NEW não virou membro',
    (select count(*) from app.tenant_member where user_id = 'd2000000-0000-0000-0000-000000000007'), 0::bigint);

  foreach v_sig in array array[
    'public.fn_convidar_usuario(uuid,uuid,jsonb)',
    'public.fn_definir_papel(uuid,uuid,app.user_role)',
    'public.fn_definir_escopo(uuid,uuid,jsonb)',
    'public.fn_desativar_membro(uuid,uuid)'] loop
    perform pg_temp.assert_eq('anon NÃO executa ' || v_sig,
      has_function_privilege('anon', v_sig, 'EXECUTE'), false);
    perform pg_temp.assert_eq('  authenticated executa ' || v_sig,
      has_function_privilege('authenticated', v_sig, 'EXECUTE'), true);
  end loop;
end $$;

\echo '--- fn_definir_papel: só owner'
do $$
declare v_a bigint := pg_temp.n_audit();
begin
  perform pg_temp.assert_eq('hr definindo papel: not_owner',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_definir_papel('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000003', 'owner')
    $q$), 'P0001:not_owner');
  perform pg_temp.assert_eq('personnel definindo papel: not_owner',
    pg_temp.como('d2000000-0000-0000-0000-000000000004', $q$
      select public.fn_definir_papel('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000006', 'hr')
    $q$), 'P0001:not_owner');
  perform pg_temp.assert_eq('owner de OUTRO tenant definindo papel em T: not_owner',
    pg_temp.como('d2000000-0000-0000-0000-000000000008', $q$
      select public.fn_definir_papel('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000006', 'hr')
    $q$), 'P0001:not_owner');
  perform pg_temp.assert_eq('  e os papéis ficaram (hr segue hr, V segue viewer)',
    (select string_agg(role::text, ',' order by user_id) from app.tenant_member
      where tenant_id = 'd2000000-0000-0000-0000-0000000000a1'
        and user_id in ('d2000000-0000-0000-0000-000000000003', 'd2000000-0000-0000-0000-000000000006')),
    'hr,viewer');
  perform pg_temp.assert_eq('owner, membro inexistente: member_not_found',
    pg_temp.como('d2000000-0000-0000-0000-000000000001', $q$
      select public.fn_definir_papel('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000007', 'hr')
    $q$), 'P0001:member_not_found');
  perform pg_temp.assert_eq('owner, membro de OUTRO tenant: member_not_found',
    pg_temp.como('d2000000-0000-0000-0000-000000000001', $q$
      select public.fn_definir_papel('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000008', 'hr')
    $q$), 'P0001:member_not_found');
  perform pg_temp.assert_eq('  e nenhuma recusa gravou audit_log', pg_temp.n_audit(), v_a);
end $$;

\echo '--- fn_definir_papel: positivo, com a linha de auditoria'
do $$
declare
  v_a bigint := pg_temp.n_audit();
  r   record;
begin
  perform pg_temp.assert_eq('owner promove V a unit_supervisor',
    pg_temp.como('d2000000-0000-0000-0000-000000000001', $q$
      select public.fn_definir_papel('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000006', 'unit_supervisor')
    $q$), 'ok');
  perform pg_temp.assert_eq('  o papel foi gravado',
    (select role::text from app.tenant_member
      where tenant_id = 'd2000000-0000-0000-0000-0000000000a1'
        and user_id = 'd2000000-0000-0000-0000-000000000006'), 'unit_supervisor');
  perform pg_temp.assert_eq('  uma linha de audit_log', pg_temp.n_audit(), v_a + 1);
  select * into r from app.audit_log
   where tenant_id = 'd2000000-0000-0000-0000-0000000000a1' order by id desc limit 1;
  perform pg_temp.assert_eq('  action dentro do CHECK, e é update', r.action, 'update');
  perform pg_temp.assert_eq('  entity / entity_id', r.entity || '/' || r.entity_id,
    'tenant_member/d2000000-0000-0000-0000-000000000006');
  perform pg_temp.assert_eq('  autor = o owner que chamou', r.user_id,
    'd2000000-0000-0000-0000-000000000001'::uuid);
  perform pg_temp.assert_eq('  antes não nulo e = viewer', r.antes, '{"role": "viewer"}'::jsonb);
  perform pg_temp.assert_eq('  depois não nulo e = unit_supervisor', r.depois,
    '{"role": "unit_supervisor"}'::jsonb);

  perform pg_temp.assert_eq('o mesmo papel de novo: ok, sem auditoria nova',
    pg_temp.como('d2000000-0000-0000-0000-000000000001', $q$
      select public.fn_definir_papel('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000006', 'unit_supervisor')
    $q$) || ' / ' || (pg_temp.n_audit() - v_a), 'ok / 1');
end $$;

\echo '--- ultimo_owner'
do $$
declare v_a bigint;
begin
  -- Tenant S: one owner.
  v_a := pg_temp.n_audit();
  perform pg_temp.assert_eq('o único owner de S se rebaixa: ultimo_owner',
    pg_temp.como('d2000000-0000-0000-0000-000000000009', $q$
      select public.fn_definir_papel('d2000000-0000-0000-0000-0000000000a3',
        'd2000000-0000-0000-0000-000000000009', 'hr')
    $q$), 'P0001:ultimo_owner');
  -- Since 05/10 only an owner deactivates an owner, so the hr is stopped one
  -- step earlier. `ultimo_owner` in fn_desativar_membro is now unreachable by
  -- construction (the caller is itself an active owner, and not the target);
  -- it stays in the function as a guard.
  perform pg_temp.assert_eq('o hr de S desativa o único owner: owner_so_por_owner',
    pg_temp.como('d2000000-0000-0000-0000-00000000000a', $q$
      select public.fn_desativar_membro('d2000000-0000-0000-0000-0000000000a3',
        'd2000000-0000-0000-0000-000000000009')
    $q$), 'P0001:owner_so_por_owner');
  perform pg_temp.assert_eq('  e S segue com um owner ativo, sem auditoria',
    (select count(*) from app.tenant_member
      where tenant_id = 'd2000000-0000-0000-0000-0000000000a3' and role = 'owner' and active)
    || ' / ' || (pg_temp.n_audit() - v_a), '1 / 0');

  -- Tenant T: two owners. O1 demotes O2 (positive), then the last one is held.
  perform pg_temp.assert_eq('com dois owners em T, O1 rebaixa O2 a hr: ok',
    pg_temp.como('d2000000-0000-0000-0000-000000000001', $q$
      select public.fn_definir_papel('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000002', 'hr')
    $q$), 'ok');
  perform pg_temp.assert_eq('agora O1 é o último e se rebaixa: ultimo_owner',
    pg_temp.como('d2000000-0000-0000-0000-000000000001', $q$
      select public.fn_definir_papel('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000001', 'viewer')
    $q$), 'P0001:ultimo_owner');
  perform pg_temp.assert_eq('o hr desativa o último owner de T: owner_so_por_owner',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_desativar_membro('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000001')
    $q$), 'P0001:owner_so_por_owner');
  perform pg_temp.assert_eq('O2 (agora hr) tentando definir papel: not_owner',
    pg_temp.como('d2000000-0000-0000-0000-000000000002', $q$
      select public.fn_definir_papel('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000002', 'owner')
    $q$), 'P0001:not_owner');
  perform pg_temp.assert_eq('O1 devolve O2 a owner: ok (promover não esbarra em ultimo_owner)',
    pg_temp.como('d2000000-0000-0000-0000-000000000001', $q$
      select public.fn_definir_papel('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000002', 'owner')
    $q$), 'ok');
  perform pg_temp.assert_eq('  T volta a ter dois owners ativos',
    (select count(*) from app.tenant_member
      where tenant_id = 'd2000000-0000-0000-0000-0000000000a1' and role = 'owner' and active), 2::bigint);
end $$;

\echo '--- fn_desativar_membro'
do $$
declare
  v_a bigint := pg_temp.n_audit();
  r   record;
begin
  perform pg_temp.assert_eq('supervisor desativando: not_admin',
    pg_temp.como('d2000000-0000-0000-0000-000000000005', $q$
      select public.fn_desativar_membro('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000006')
    $q$), 'P0001:not_admin');
  perform pg_temp.assert_eq('owner de OUTRO tenant desativando em T: not_admin',
    pg_temp.como('d2000000-0000-0000-0000-000000000008', $q$
      select public.fn_desativar_membro('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000006')
    $q$), 'P0001:not_admin');
  perform pg_temp.assert_eq('hr desativa a si mesmo: e_voce_mesmo',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_desativar_membro('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000003')
    $q$), 'P0001:e_voce_mesmo');
  perform pg_temp.assert_eq('owner (com outro owner ativo) desativa a si mesmo: e_voce_mesmo',
    pg_temp.como('d2000000-0000-0000-0000-000000000001', $q$
      select public.fn_desativar_membro('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000001')
    $q$), 'P0001:e_voce_mesmo');
  perform pg_temp.assert_eq('hr, membro inexistente: member_not_found',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_desativar_membro('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000007')
    $q$), 'P0001:member_not_found');
  perform pg_temp.assert_eq('  todos seguem ativos, sem auditoria',
    (select count(*) from app.tenant_member
      where tenant_id = 'd2000000-0000-0000-0000-0000000000a1' and active)
    || ' / ' || (pg_temp.n_audit() - v_a), '6 / 0');

  perform pg_temp.assert_eq('hr desativa V: ok',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_desativar_membro('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000006')
    $q$), 'ok');
  select * into r from app.tenant_member
   where tenant_id = 'd2000000-0000-0000-0000-0000000000a1'
     and user_id = 'd2000000-0000-0000-0000-000000000006';
  perform pg_temp.assert_eq('  a linha foi preservada', r.user_id is not null, true);
  perform pg_temp.assert_eq('  active = false', r.active, false);
  perform pg_temp.assert_eq('  deactivated_at preenchido', r.deactivated_at is not null, true);
  perform pg_temp.assert_eq('  o papel e o escopo não foram tocados',
    r.role::text || ' ' || pg_temp.escopo(r.tenant_id, r.user_id), 'unit_supervisor e1/-');
  perform pg_temp.assert_eq('  uma linha de audit_log', pg_temp.n_audit(), v_a + 1);
  perform pg_temp.assert_eq('  com antes, depois e autor',
    (select a.action || ' ' || a.entity || ' ' || (a.antes ->> 'active') || '->'
            || (a.depois ->> 'active') || ' ' || (a.depois ->> 'deactivated_at' is not null)::text
            || ' ' || a.user_id::text
       from app.audit_log a
      where a.tenant_id = 'd2000000-0000-0000-0000-0000000000a1' order by a.id desc limit 1),
    'update tenant_member true->false true d2000000-0000-0000-0000-000000000003');
  perform pg_temp.assert_eq('desativar de novo: ok, sem auditoria, mesma data',
    pg_temp.como('d2000000-0000-0000-0000-000000000004', $q$
      select public.fn_desativar_membro('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000006')
    $q$) || ' / ' || (pg_temp.n_audit() - v_a) || ' / '
    || ((select deactivated_at from app.tenant_member
          where tenant_id = 'd2000000-0000-0000-0000-0000000000a1'
            and user_id = 'd2000000-0000-0000-0000-000000000006') = r.deactivated_at)::text,
    'ok / 1 / true');
end $$;

\echo '--- escopo_invalido: o parser é estrito, nas duas funções'
do $$
declare
  c   record;
  v_a bigint := pg_temp.n_audit();
begin
  for c in select * from (values
    ('entrada que não é objeto',          '["d2000000-0000-0000-0000-0000000000e1"]'),
    ('chave desconhecida (unitId)',       '[{"company_id": "d2000000-0000-0000-0000-0000000000e1", "unitId": "d2000000-0000-0000-0000-0000000000b1"}]'),
    ('company_id string vazia',           '[{"company_id": ""}]'),
    ('unit_id string vazia',              '[{"company_id": "d2000000-0000-0000-0000-0000000000e1", "unit_id": ""}]'),
    ('company_id não-string (número)',    '[{"company_id": 1}]'),
    ('unit_id não-string (null JSON)',    '[{"company_id": "d2000000-0000-0000-0000-0000000000e1", "unit_id": null}]'),
    ('unit_id não-string (objeto)',       '[{"company_id": "d2000000-0000-0000-0000-0000000000e1", "unit_id": {}}]')
  ) as v(rotulo, escopo) loop
    perform pg_temp.assert_eq('escopo, ' || c.rotulo || ': escopo_invalido',
      pg_temp.como('d2000000-0000-0000-0000-000000000003', format($q$
        select public.fn_definir_escopo('d2000000-0000-0000-0000-0000000000a1',
          'd2000000-0000-0000-0000-000000000005', %L)
      $q$, c.escopo)), 'P0001:escopo_invalido');
    perform pg_temp.assert_eq('convite, ' || c.rotulo || ': escopo_invalido',
      pg_temp.como('d2000000-0000-0000-0000-000000000003', format($q$
        select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
          'd2000000-0000-0000-0000-000000000007', %L)
      $q$, c.escopo)), 'P0001:escopo_invalido');
  end loop;
  perform pg_temp.assert_eq('  nada mudou: escopo do supervisor, NEW fora, sem auditoria',
    pg_temp.escopo('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-000000000005')
    || ' ' || (select count(*) from app.tenant_member where user_id = 'd2000000-0000-0000-0000-000000000007')
    || ' / ' || (pg_temp.n_audit() - v_a), 'e1/b1 0 / 0');
  -- Positive: the valid shape still passes (same scope: ok, nothing written).
  perform pg_temp.assert_eq('a forma válida {company_id, unit_id} continua passando',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_definir_escopo('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000005',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e1", "unit_id": "d2000000-0000-0000-0000-0000000000b1"}]')
    $q$) || ' / ' || (pg_temp.n_audit() - v_a), 'ok / 0');
end $$;

\echo '--- fn_definir_escopo: recusas, e nada mudou depois de cada uma'
do $$
declare
  v_a   bigint := pg_temp.n_audit();
  v_sup text := pg_temp.escopo('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-000000000005');
  v_n   bigint;
begin
  select count(*) into v_n from app.user_scope
   where tenant_id = 'd2000000-0000-0000-0000-0000000000a1'
     and user_id = 'd2000000-0000-0000-0000-000000000005';
  perform pg_temp.assert_eq('escopo do supervisor antes: uma linha, E1/U1', v_n || ' ' || v_sup, '1 e1/b1');

  perform pg_temp.assert_eq('supervisor redefinindo o próprio escopo: not_admin',
    pg_temp.como('d2000000-0000-0000-0000-000000000005', $q$
      select public.fn_definir_escopo('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000005',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e2"}]')
    $q$), 'P0001:not_admin');
  perform pg_temp.assert_eq('owner de OUTRO tenant: not_admin',
    pg_temp.como('d2000000-0000-0000-0000-000000000008', $q$
      select public.fn_definir_escopo('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000005',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e2"}]')
    $q$), 'P0001:not_admin');
  perform pg_temp.assert_eq('hr, usuário que não é membro: member_not_found',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_definir_escopo('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000007',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e1"}]')
    $q$), 'P0001:member_not_found');
  perform pg_temp.assert_eq('hr, lista vazia: escopo_vazio',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_definir_escopo('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000005', '[]')
    $q$), 'P0001:escopo_vazio');
  perform pg_temp.assert_eq('hr, nulo: escopo_vazio',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_definir_escopo('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000005', null)
    $q$), 'P0001:escopo_vazio');
  perform pg_temp.assert_eq('hr, objeto em vez de lista: escopo_vazio',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_definir_escopo('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000005',
        '{"company_id": "d2000000-0000-0000-0000-0000000000e1"}')
    $q$), 'P0001:escopo_vazio');
  perform pg_temp.assert_eq('hr, unidade sem empresa: escopo_sem_empresa',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_definir_escopo('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000005',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e1"},
          {"unit_id": "d2000000-0000-0000-0000-0000000000b1"}]')
    $q$), 'P0001:escopo_sem_empresa');
  perform pg_temp.assert_eq('hr, empresa de outro tenant: empresa_fora_do_tenant',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_definir_escopo('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000005',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e9"}]')
    $q$), 'P0001:empresa_fora_do_tenant');
  perform pg_temp.assert_eq('hr, par trocado (E2 com U1, que é de E1): unidade_fora_da_empresa',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_definir_escopo('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000005',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e2", "unit_id": "d2000000-0000-0000-0000-0000000000b1"}]')
    $q$), 'P0001:unidade_fora_da_empresa');
  perform pg_temp.assert_eq('hr, unidade de OUTRO tenant sob empresa de T: unidade_fora_da_empresa',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_definir_escopo('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000005',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e1", "unit_id": "d2000000-0000-0000-0000-0000000000b9"}]')
    $q$), 'P0001:unidade_fora_da_empresa');

  select count(*) into v_n from app.user_scope
   where tenant_id = 'd2000000-0000-0000-0000-0000000000a1'
     and user_id = 'd2000000-0000-0000-0000-000000000005';
  perform pg_temp.assert_eq('  depois das recusas: as mesmas linhas (contagem e conteúdo), sem auditoria',
    v_n || ' ' || pg_temp.escopo('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-000000000005')
    || ' / ' || (pg_temp.n_audit() - v_a), '1 e1/b1 / 0');
end $$;

\echo '--- fn_definir_escopo: positivos'
do $$
declare
  v_a bigint := pg_temp.n_audit();
  r   record;
begin
  perform pg_temp.assert_eq('personnel troca o escopo do supervisor para U2 de E2 + toda E1 (par certo)',
    pg_temp.como('d2000000-0000-0000-0000-000000000004', $q$
      select public.fn_definir_escopo('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000005',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e2", "unit_id": "d2000000-0000-0000-0000-0000000000b2"},
          {"company_id": "d2000000-0000-0000-0000-0000000000e1"},
          {"company_id": "d2000000-0000-0000-0000-0000000000e1"}]')
    $q$), 'ok');
  perform pg_temp.assert_eq('  o escopo é exatamente o novo (repetição colapsada)',
    pg_temp.escopo('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-000000000005'),
    'e1/-,e2/b2');
  perform pg_temp.assert_eq('  uma linha de audit_log', pg_temp.n_audit(), v_a + 1);
  select * into r from app.audit_log
   where tenant_id = 'd2000000-0000-0000-0000-0000000000a1' order by id desc limit 1;
  perform pg_temp.assert_eq('  update em user_scope, autor = personnel',
    r.action || ' ' || r.entity || ' ' || r.entity_id || ' ' || r.user_id,
    'update user_scope d2000000-0000-0000-0000-000000000005 d2000000-0000-0000-0000-000000000004');
  perform pg_temp.assert_eq('  antes = a lista anterior',
    r.antes, '[{"unit_id": "d2000000-0000-0000-0000-0000000000b1", "company_id": "d2000000-0000-0000-0000-0000000000e1"}]'::jsonb);
  perform pg_temp.assert_eq('  depois = a lista nova',
    jsonb_array_length(r.depois), 2);

  perform pg_temp.assert_eq('o owner define o escopo de um membro INATIVO: ok (escopo não é acesso)',
    pg_temp.como('d2000000-0000-0000-0000-000000000001', $q$
      select public.fn_definir_escopo('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-00000000000b',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e2"}]')
    $q$), 'ok');
  perform pg_temp.assert_eq('o mesmo escopo de novo: ok, sem auditoria nova',
    pg_temp.como('d2000000-0000-0000-0000-000000000001', $q$
      select public.fn_definir_escopo('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-00000000000b',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e2"}]')
    $q$) || ' / ' || (pg_temp.n_audit() - v_a), 'ok / 2');
end $$;

\echo '--- fn_convidar_usuario'
do $$
declare
  v_a bigint := pg_temp.n_audit();
  r   record;
begin
  perform pg_temp.assert_eq('supervisor convidando: not_admin',
    pg_temp.como('d2000000-0000-0000-0000-000000000005', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000007',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e1"}]')
    $q$), 'P0001:not_admin');
  perform pg_temp.assert_eq('owner de OUTRO tenant convidando em T: not_admin',
    pg_temp.como('d2000000-0000-0000-0000-000000000008', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000007',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e1"}]')
    $q$), 'P0001:not_admin');
  perform pg_temp.assert_eq('hr convidando quem já é membro ativo: ja_e_membro',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000005',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e1"}]')
    $q$), 'P0001:ja_e_membro');
  perform pg_temp.assert_eq('hr convidando quem é membro INATIVO: ja_e_membro',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-00000000000b',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e1"}]')
    $q$), 'P0001:ja_e_membro');
  perform pg_temp.assert_eq('hr, escopo vazio: escopo_vazio',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000007', '[]')
    $q$), 'P0001:escopo_vazio');
  perform pg_temp.assert_eq('hr, unidade sem empresa: escopo_sem_empresa',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000007',
        '[{"unit_id": "d2000000-0000-0000-0000-0000000000b1"}]')
    $q$), 'P0001:escopo_sem_empresa');
  perform pg_temp.assert_eq('hr, empresa de outro tenant: empresa_fora_do_tenant',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000007',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e9", "unit_id": "d2000000-0000-0000-0000-0000000000b9"}]')
    $q$), 'P0001:empresa_fora_do_tenant');
  perform pg_temp.assert_eq('hr, par trocado (E1 com U2, que é de E2): unidade_fora_da_empresa',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000007',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e1", "unit_id": "d2000000-0000-0000-0000-0000000000b2"}]')
    $q$), 'P0001:unidade_fora_da_empresa');
  perform pg_temp.assert_eq('  nenhuma recusa criou vínculo, escopo ou auditoria',
    (select count(*) from app.tenant_member where user_id = 'd2000000-0000-0000-0000-000000000007')
    || ' ' || (select count(*) from app.user_scope where user_id = 'd2000000-0000-0000-0000-000000000007')
    || ' / ' || (pg_temp.n_audit() - v_a), '0 0 / 0');

  perform pg_temp.assert_eq('hr convida NEW com toda E1 e U2 de E2 (par certo): ok',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000007',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e1"},
          {"company_id": "d2000000-0000-0000-0000-0000000000e2", "unit_id": "d2000000-0000-0000-0000-0000000000b2"}]')
    $q$), 'ok');
  select * into r from app.tenant_member
   where tenant_id = 'd2000000-0000-0000-0000-0000000000a1'
     and user_id = 'd2000000-0000-0000-0000-000000000007';
  perform pg_temp.assert_eq('  nasce viewer, ativo, convidado pelo hr, sem data de inativação',
    r.role::text || ' ' || r.active || ' ' || r.invited_by || ' ' || (r.deactivated_at is null),
    'viewer true d2000000-0000-0000-0000-000000000003 true');
  perform pg_temp.assert_eq('  com o escopo pedido',
    pg_temp.escopo(r.tenant_id, r.user_id), 'e1/-,e2/b2');
  perform pg_temp.assert_eq('  uma linha de audit_log (insert, dentro do CHECK)',
    (select a.action || ' ' || a.entity || ' ' || a.user_id || ' ' || (a.antes is null)
            || ' ' || (a.depois ->> 'role') || ' ' || jsonb_array_length(a.depois -> 'scope')
       from app.audit_log a
      where a.tenant_id = 'd2000000-0000-0000-0000-0000000000a1' order by a.id desc limit 1)
    || ' / ' || (pg_temp.n_audit() - v_a),
    'insert tenant_member d2000000-0000-0000-0000-000000000003 true viewer 2 / 1');

  perform pg_temp.assert_eq('convidar NEW de novo: ja_e_membro',
    pg_temp.como('d2000000-0000-0000-0000-000000000004', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000007',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e1"}]')
    $q$), 'P0001:ja_e_membro');
  -- Até a revisão da U3 esta linha esperava 'ok' — e o 'ok' era o defeito: NEW
  -- ficava ativo em T E em S, e a resolução do token dele, ambígua (403 em
  -- tudo). Decisão do dono, 05/10/2026: um cliente por usuário.
  perform pg_temp.assert_eq('o owner de S convida o mesmo NEW (ativo em T) em S: conta_em_outro_cliente',
    pg_temp.como('d2000000-0000-0000-0000-000000000009', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a3',
        'd2000000-0000-0000-0000-000000000007',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e3"}]')
    $q$), 'P0001:conta_em_outro_cliente');
end $$;

\echo '--- um cliente por usuário (decisão do dono, 05/10): conta_em_outro_cliente pela RPC direta'
do $$
declare
  v_a bigint := pg_temp.n_audit();
begin
  -- O ataque P1: o uuid é o `sub` de qualquer JWT, e a RPC é chamável pelo
  -- PostgREST. A rota não está no caminho.
  perform pg_temp.assert_eq('hr de T convida XB, ativo em X: conta_em_outro_cliente',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-00000000000c',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e1"}]')
    $q$), 'P0001:conta_em_outro_cliente');
  perform pg_temp.assert_eq('hr de T convida o OWNER de X: conta_em_outro_cliente',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000008',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e1"}]')
    $q$), 'P0001:conta_em_outro_cliente');
  perform pg_temp.assert_eq('  ordem: vem antes do escopo (XB com escopo vazio ainda é conta_em_outro_cliente)',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-00000000000c', '[]')
    $q$), 'P0001:conta_em_outro_cliente');
  perform pg_temp.assert_eq('  ordem: o papel vem antes (supervisor convidando XB: not_admin)',
    pg_temp.como('d2000000-0000-0000-0000-000000000005', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-00000000000c',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e1"}]')
    $q$), 'P0001:not_admin');
  -- P3: o tenant suspenso também conta — reativado, deixaria o token ambíguo.
  perform pg_temp.assert_eq('hr de T convida ZA, ativo em Z (tenant INATIVO): conta_em_outro_cliente',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-00000000000d',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e1"}]')
    $q$), 'P0001:conta_em_outro_cliente');
  perform pg_temp.assert_eq('  nenhum vínculo em T nem em S para XB, XO, ZA ou NEW; nenhum escopo; nenhuma auditoria',
    (select count(*) from app.tenant_member
      where tenant_id in ('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-0000000000a3')
        and user_id in ('d2000000-0000-0000-0000-00000000000c', 'd2000000-0000-0000-0000-000000000008',
                        'd2000000-0000-0000-0000-00000000000d'))
    || ' ' || (select count(*) from app.tenant_member
                where tenant_id = 'd2000000-0000-0000-0000-0000000000a3'
                  and user_id = 'd2000000-0000-0000-0000-000000000007')
    || ' ' || (select count(*) from app.user_scope
                where user_id in ('d2000000-0000-0000-0000-00000000000c', 'd2000000-0000-0000-0000-000000000008',
                                  'd2000000-0000-0000-0000-00000000000d'))
    || ' / ' || (pg_temp.n_audit() - v_a), '0 0 0 / 0');
  perform pg_temp.assert_eq('  os vínculos de origem intactos: XB e XO ativos em X, ZA ativo em Z, NEW ativo só em T',
    (select string_agg(right(tenant_id::text, 2) || ':' || right(user_id::text, 2) || ':' || active,
                       ',' order by tenant_id, user_id)
       from app.tenant_member
      where user_id in ('d2000000-0000-0000-0000-00000000000c', 'd2000000-0000-0000-0000-000000000008',
                        'd2000000-0000-0000-0000-00000000000d', 'd2000000-0000-0000-0000-000000000007')),
    'a1:07:true,a2:08:true,a2:0c:true,a4:0d:true');

  -- O positivo: só vínculo INATIVO em outro tenant não é cliente nenhum.
  perform pg_temp.assert_eq('o owner de S convida XI (só INATIVO em X): ok',
    pg_temp.como('d2000000-0000-0000-0000-000000000009', $q$
      select public.fn_convidar_usuario('d2000000-0000-0000-0000-0000000000a3',
        'd2000000-0000-0000-0000-00000000000e',
        '[{"company_id": "d2000000-0000-0000-0000-0000000000e3"}]')
    $q$), 'ok');
  perform pg_temp.assert_eq('  XI: viewer ativo em S, e o vínculo inativo de X fica como estava',
    (select string_agg(right(tenant_id::text, 2) || ':' || role || ':' || active, ',' order by tenant_id)
       from app.tenant_member where user_id = 'd2000000-0000-0000-0000-00000000000e'),
    'a2:viewer:false,a3:viewer:true');
end $$;

\echo '--- owner_so_por_owner (decisão do dono, 05/10): T com dois owners'
do $$
declare v_a bigint := pg_temp.n_audit();
begin
  perform pg_temp.assert_eq('T tem dois owners ativos',
    (select count(*) from app.tenant_member
      where tenant_id = 'd2000000-0000-0000-0000-0000000000a1' and role = 'owner' and active), 2::bigint);
  perform pg_temp.assert_eq('hr desativa O1: owner_so_por_owner',
    pg_temp.como('d2000000-0000-0000-0000-000000000003', $q$
      select public.fn_desativar_membro('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000001')
    $q$), 'P0001:owner_so_por_owner');
  perform pg_temp.assert_eq('personnel desativa O2: owner_so_por_owner',
    pg_temp.como('d2000000-0000-0000-0000-000000000004', $q$
      select public.fn_desativar_membro('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000002')
    $q$), 'P0001:owner_so_por_owner');
  perform pg_temp.assert_eq('  os dois seguem ativos, sem auditoria',
    (select count(*) from app.tenant_member
      where tenant_id = 'd2000000-0000-0000-0000-0000000000a1' and role = 'owner' and active)
    || ' / ' || (pg_temp.n_audit() - v_a), '2 / 0');
  perform pg_temp.assert_eq('O1 desativa O2: ok',
    pg_temp.como('d2000000-0000-0000-0000-000000000001', $q$
      select public.fn_desativar_membro('d2000000-0000-0000-0000-0000000000a1',
        'd2000000-0000-0000-0000-000000000002')
    $q$), 'ok');
  perform pg_temp.assert_eq('  O2 inativo, com data, linha preservada; um owner ativo; uma auditoria do O1',
    (select (not tm.active)::text || ' ' || (tm.deactivated_at is not null)::text
       from app.tenant_member tm
      where tm.tenant_id = 'd2000000-0000-0000-0000-0000000000a1'
        and tm.user_id = 'd2000000-0000-0000-0000-000000000002')
    || ' ' || (select count(*) from app.tenant_member
                where tenant_id = 'd2000000-0000-0000-0000-0000000000a1' and role = 'owner' and active)
    || ' / ' || (pg_temp.n_audit() - v_a)
    || ' ' || (select a.user_id::text from app.audit_log a
                where a.tenant_id = 'd2000000-0000-0000-0000-0000000000a1' order by a.id desc limit 1),
    'true true 1 / 1 d2000000-0000-0000-0000-000000000001');
end $$;

\echo '--- toda linha de auditoria do teste: action no CHECK, autor preenchido, depois não nulo'
do $$ begin
  perform pg_temp.assert_eq('nenhuma linha fora do contrato',
    (select count(*) from app.audit_log
      where tenant_id in ('d2000000-0000-0000-0000-0000000000a1', 'd2000000-0000-0000-0000-0000000000a3')
        and (action not in ('insert', 'update') or user_id is null or depois is null
             or (action = 'update' and antes is null))), 0::bigint);
  perform pg_temp.assert_eq('e são nove: papel x3, desativar x2, escopo x2, convite x2',
    pg_temp.n_audit(), 9::bigint);
  perform pg_temp.assert_eq('nenhum membro foi apagado (13 vínculos do fixture + 2 convites)',
    (select count(*) from app.tenant_member
      where tenant_id in ('d2000000-0000-0000-0000-0000000000a1',
                          'd2000000-0000-0000-0000-0000000000a2',
                          'd2000000-0000-0000-0000-0000000000a3',
                          'd2000000-0000-0000-0000-0000000000a4')), 15::bigint);
end $$;

rollback;
\echo '=== RPCS DE USUÁRIO OK'
