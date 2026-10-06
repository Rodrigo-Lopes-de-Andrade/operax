-- ============================================================================
-- OperaX — usuarios_rpc. THE FOUR DOORS THAT WRITE MEMBERSHIP AND SCOPE
-- ----------------------------------------------------------------------------
-- Sprint U2 of `docs/SPRINTS-USUARIOS.md`, shape in `docs/SPEC-USUARIOS.md`
-- §2, §5.4 and §5.5. `authenticated` has no INSERT/UPDATE/DELETE on
-- `app.tenant_member` or `app.user_scope` since `alcada_revoke_writes` (P1.2b),
-- so these four `security definer` functions are the ONLY way the panel writes
-- membership or scope, and every guard of the stage lives in them:
--
--   fn_convidar_usuario(p_tenant_id, p_user_id, p_scope)   hr/personnel/owner
--   fn_definir_papel   (p_tenant_id, p_user_id, p_role)    owner only
--   fn_definir_escopo  (p_tenant_id, p_user_id, p_scope)   hr/personnel/owner
--   fn_desativar_membro(p_tenant_id, p_user_id)            hr/personnel/owner
--
-- REFUSALS: `raise exception '<code>' using errcode = 'P0001'`, in this order
-- (the authorisation code always first: a caller without the role learns
-- nothing about the member or the scope):
--   convidar : not_admin, ja_e_membro, conta_em_outro_cliente,
--              escopo_vazio, escopo_invalido, escopo_sem_empresa,
--              empresa_fora_do_tenant, unidade_fora_da_empresa
--   papel    : not_owner, member_not_found, ultimo_owner
--   escopo   : not_admin, member_not_found, escopo_vazio, escopo_invalido,
--              escopo_sem_empresa, empresa_fora_do_tenant,
--              unidade_fora_da_empresa
--   desativar: not_admin, e_voce_mesmo, member_not_found,
--              owner_so_por_owner, ultimo_owner
-- `conta_em_outro_cliente` (owner decision of 05/10/2026, U3 review): ONE
-- CUSTOMER PER USER. The invite refuses a user who is `active` in ANY other
-- tenant — active tenant or not. A second active membership makes the token
-- resolution of that user ambiguous (`resolve_membership` raises, the API
-- answers 403 to everything, `/me` included): an hr of A could lock the owner
-- of B out knowing only the uuid, which is the `sub` of every JWT. The tenant
-- of the other membership is deliberately NOT required to be active: a member
-- of a suspended tenant would become ambiguous the day it is reactivated.
-- No unique index: the `98` keeps a user active in two tenants on purpose (a
-- fixture inserted as `postgres`), and production has none (measured 05/10).
-- The tenant lock serialises A against A, never A against B, so the check is
-- preceded by a PER-USER lock:
--   pg_advisory_xact_lock(hashtextextended('tenant_member/user/' || p_user_id, 0))
-- Two tenants inviting the same person at once: the second waits, and its
-- check (a fresh READ COMMITTED snapshot) sees the first one's membership.
-- Tenant lock first, user lock second, in every caller: no deadlock cycle.
-- `owner_so_por_owner`: owner decision of 05/10/2026 — only an owner
-- deactivates an owner; hr and personnel deactivate everyone else.
-- `escopo_invalido` (code review, cycle 1): the parser is strict, because a
-- misspelt key (`unitId`) used to be ignored and silently widen a unit scope
-- to the whole company.
-- `empresa_fora_do_tenant`, `unidade_fora_da_empresa` (condition inherited
-- from the U1 review) and `member_not_found` in `fn_desativar_membro` are not
-- in the SPEC §5.4 table; they are declared here, each replacing what would
-- otherwise be a silent write or a silent no-op.
--
-- THE SHAPE OF `p_scope` (both scope-taking functions, one parser:
-- `util.parse_user_scope`): a NON-EMPTY jsonb array of objects
--   [{"company_id": "<uuid>"}, {"company_id": "<uuid>", "unit_id": "<uuid>"}]
--   * `{company_id}`           -> every unit of that company ("todas as
--                                 unidades" is one such entry per company —
--                                 a snapshot, not a rule: SPEC §3.3);
--   * `{company_id, unit_id}`  -> that unit only; the unit must belong to that
--                                 company, in this tenant.
--   null / not an array / []   -> escopo_vazio
--   an entry that is not an object, a key other than company_id/unit_id,
--   or company_id/unit_id that is not a non-empty string (an empty string,
--   a number, a JSON null)     -> escopo_invalido
--   an entry without company   -> escopo_sem_empresa (also a unit without it)
--   company not of p_tenant_id -> empresa_fora_do_tenant
--   unit not of that company   -> unidade_fora_da_empresa — this is also what a
--                                 unit of ANOTHER tenant gets: with a company of
--                                 this tenant it is "not of that company"; with
--                                 a company of the other tenant the company is
--                                 refused first.
--   a non-empty string that is not a uuid -> 22P02 from the cast, loud.
--   Repeated entries collapse (same meaning, one row).
--
-- THE LOCK. Every function first checks, WITHOUT a lock, that the caller is an
-- active member of p_tenant_id (`util.has_tenant`), and refuses with its role
-- code otherwise: an outsider never waits for, nor holds, the row of another
-- tenant (code review, cycle 1). Then
--   select … from app.tenant where id = p_tenant_id for no key update
-- serialises all four, per tenant, and the ROLE is read again after it.
-- Two owners demoting each other at
-- the same time: the second waits, and — because the role check runs AFTER
-- the lock, on a fresh READ COMMITTED snapshot — it sees that it is no longer
-- owner and gets `not_owner`; `ultimo_owner` then counts committed owners
-- only. `no key update` and not `update`: it does not conflict with the
-- `for key share` that every FK insert referencing app.tenant takes, so the
-- motor and the sync never wait for this lock. Proven with two real sessions
-- in `scripts/teste_usuarios_concorrencia.py`.
--
-- AUDIT. One `app.audit_log` row per action that changes something, written
-- because the functions are definer (owner of the table); no policy is added.
--   convidar  -> action 'insert' (a membership is born; in the CHECK),
--                entity 'tenant_member', antes NULL, depois = member + scope
--   papel     -> 'update', 'tenant_member', antes/depois = {role}
--   escopo    -> 'update', 'user_scope',    antes/depois = scope lists
--   desativar -> 'update', 'tenant_member', antes/depois = {active, deactivated_at}
-- author = auth.uid(), entity_id = the target user. A call that changes
-- nothing (same role, member already inactive) writes nothing and no audit.
--
-- NEVER DELETE A MEMBER. Deactivation is `active = false` + `deactivated_at`.
-- `fn_definir_escopo` does delete `app.user_scope` rows: replacing a scope is
-- removing the old rows, and it happens only after the new list was fully
-- validated, in the same transaction.
--
-- ⚠️ `trg_lock_down_new_function` DOES NOT COVER `public`: the revoke from
-- `public, anon` and the grant to `authenticated, service_role` are written
-- for each of the four (SPEC §5.5). The parser lives in `util`, where the
-- trigger revokes it from `public, anon`; it gets no grant at all — only the
-- four definers (running as its owner) call it.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- The parser of p_scope — invoker, called only from inside the definers.
-- ---------------------------------------------------------------------------
create or replace function util.parse_user_scope(p_tenant_id uuid, p_scope jsonb)
returns table (company_id uuid, unit_id uuid)
language plpgsql
stable
set search_path = ''
as $$
begin
  if p_scope is null or jsonb_typeof(p_scope) <> 'array' or jsonb_array_length(p_scope) = 0 then
    raise exception 'escopo_vazio' using errcode = 'P0001';
  end if;

  -- Strict shape: an object with only company_id/unit_id, each, when present,
  -- a non-empty string. Anything else is refused, never ignored.
  if exists (select 1 from jsonb_array_elements(p_scope) e
              -- `case`, not `or`: SQL does not promise the order of `or`, and
              -- jsonb_object_keys on a non-object raises instead of refusing.
              where case when jsonb_typeof(e) <> 'object' then true
                         else exists (select 1 from jsonb_object_keys(e) k
                                       where k not in ('company_id', 'unit_id'))
                           or (e ? 'company_id' and (jsonb_typeof(e -> 'company_id') <> 'string'
                                                     or e ->> 'company_id' = ''))
                           or (e ? 'unit_id' and (jsonb_typeof(e -> 'unit_id') <> 'string'
                                                  or e ->> 'unit_id' = ''))
                    end) then
    raise exception 'escopo_invalido' using errcode = 'P0001';
  end if;

  if exists (select 1 from jsonb_array_elements(p_scope) e
              where not e ? 'company_id') then
    raise exception 'escopo_sem_empresa' using errcode = 'P0001';
  end if;

  if exists (select 1 from jsonb_array_elements(p_scope) e
              where not exists (select 1 from app.company c
                                 where c.id = (e ->> 'company_id')::uuid
                                   and c.tenant_id = p_tenant_id)) then
    raise exception 'empresa_fora_do_tenant' using errcode = 'P0001';
  end if;

  if exists (select 1 from jsonb_array_elements(p_scope) e
              where e ? 'unit_id'
                and not exists (select 1 from app.unit u
                                 where u.id = (e ->> 'unit_id')::uuid
                                   and u.tenant_id = p_tenant_id
                                   and u.company_id = (e ->> 'company_id')::uuid)) then
    raise exception 'unidade_fora_da_empresa' using errcode = 'P0001';
  end if;

  return query
    select distinct (e ->> 'company_id')::uuid, (e ->> 'unit_id')::uuid
      from jsonb_array_elements(p_scope) e;
end $$;

comment on function util.parse_user_scope(uuid, jsonb) is
  'Valida e normaliza o p_scope das RPCs de usuário: lista não vazia de {company_id, unit_id?}. '
  'Estrito: chave desconhecida, entrada que não é objeto ou id que não é string não vazia é '
  'recusado. Recusas P0001: escopo_vazio, escopo_invalido, escopo_sem_empresa, '
  'empresa_fora_do_tenant, unidade_fora_da_empresa. Sem grant: só as funções definer de usuarios_rpc a chamam.';

revoke execute on function util.parse_user_scope(uuid, jsonb) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 1. Invite: the member is born `viewer`, with the scope, in one call.
-- ---------------------------------------------------------------------------
create or replace function public.fn_convidar_usuario(
  p_tenant_id uuid, p_user_id uuid, p_scope jsonb)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_companies uuid[];
  v_units     uuid[];
  v_scope     jsonb;
begin
  -- Outsiders are refused before the lock: they never wait for, nor hold,
  -- another tenant's row. The role itself is read again after the lock.
  if not util.has_tenant(p_tenant_id) then
    raise exception 'not_admin' using errcode = 'P0001';
  end if;

  -- The tenant lock: serialises every membership change of the tenant.
  perform 1 from app.tenant t where t.id = p_tenant_id for no key update;

  if not util.is_admin(p_tenant_id) then
    raise exception 'not_admin' using errcode = 'P0001';
  end if;

  -- Active or not: the row exists, and reactivation is not an invite.
  if exists (select 1 from app.tenant_member tm
              where tm.tenant_id = p_tenant_id and tm.user_id = p_user_id) then
    raise exception 'ja_e_membro' using errcode = 'P0001';
  end if;

  -- One customer per user. The tenant lock does not order this tenant against
  -- another one, so the person is locked too, and only then counted.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('tenant_member/user/' || p_user_id::text, 0));
  -- Any other tenant, active or not (a suspended one can be reactivated).
  if exists (select 1 from app.tenant_member o
              where o.user_id = p_user_id and o.tenant_id <> p_tenant_id and o.active) then
    raise exception 'conta_em_outro_cliente' using errcode = 'P0001';
  end if;

  -- Everything validated before anything is written.
  select array_agg(s.company_id order by s.company_id, s.unit_id nulls first),
         array_agg(s.unit_id    order by s.company_id, s.unit_id nulls first),
         jsonb_agg(jsonb_build_object('company_id', s.company_id, 'unit_id', s.unit_id)
                   order by s.company_id, s.unit_id nulls first)
    into v_companies, v_units, v_scope
    from util.parse_user_scope(p_tenant_id, p_scope) s;

  insert into app.tenant_member (tenant_id, user_id, role, invited_by)
  values (p_tenant_id, p_user_id, 'viewer', (select auth.uid()));

  insert into app.user_scope (tenant_id, user_id, company_id, unit_id)
  select p_tenant_id, p_user_id, x.company_id, x.unit_id
    from unnest(v_companies, v_units) as x(company_id, unit_id);

  insert into app.audit_log (tenant_id, user_id, action, entity, entity_id, antes, depois)
  values (p_tenant_id, (select auth.uid()), 'insert', 'tenant_member', p_user_id::text, null,
          jsonb_build_object('role', 'viewer', 'active', true,
                             'invited_by', (select auth.uid()), 'scope', v_scope));
end $$;

comment on function public.fn_convidar_usuario(uuid, uuid, jsonb) is
  'Convite: cria o vínculo como viewer (invited_by = auth.uid()) e o escopo, na mesma transação. '
  'Quem: owner, hr, personnel. Recusas P0001, nesta ordem: not_admin, ja_e_membro (ativo ou não), '
  'conta_em_outro_cliente (vínculo ativo em qualquer outro tenant, ativo ou não — um cliente por '
  'usuário; conferido sob pg_advisory_xact_lock por usuário), '
  'escopo_vazio, escopo_invalido, escopo_sem_empresa, empresa_fora_do_tenant, unidade_fora_da_empresa. '
  'p_scope = lista não vazia de {company_id, unit_id?}. Roda DEPOIS do Admin API: ja_e_membro e '
  'conta_em_outro_cliente precisam ser lidos antes de convidar. Grava audit_log (insert).';

revoke execute on function public.fn_convidar_usuario(uuid, uuid, jsonb) from public, anon;
grant  execute on function public.fn_convidar_usuario(uuid, uuid, jsonb) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Role: the only act that grants privilege, and only the owner does it.
-- ---------------------------------------------------------------------------
create or replace function public.fn_definir_papel(
  p_tenant_id uuid, p_user_id uuid, p_role app.user_role)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_old    app.user_role;
  v_active boolean;
begin
  -- Outsiders are refused before the lock: they never wait for, nor hold,
  -- another tenant's row. The role itself is read again after the lock.
  if not util.has_tenant(p_tenant_id) then
    raise exception 'not_owner' using errcode = 'P0001';
  end if;

  perform 1 from app.tenant t where t.id = p_tenant_id for no key update;

  -- After the lock: a concurrent demotion of the caller is already visible.
  if not ('owner' = any(util.roles_in_tenant(p_tenant_id))) then
    raise exception 'not_owner' using errcode = 'P0001';
  end if;

  select tm.role, tm.active into v_old, v_active
    from app.tenant_member tm
   where tm.tenant_id = p_tenant_id and tm.user_id = p_user_id;
  if not found then
    raise exception 'member_not_found' using errcode = 'P0001';
  end if;

  if v_old = 'owner' and v_active and p_role is distinct from 'owner'
     and (select count(*) from app.tenant_member tm
           where tm.tenant_id = p_tenant_id and tm.role = 'owner' and tm.active) <= 1 then
    raise exception 'ultimo_owner' using errcode = 'P0001';
  end if;

  if v_old = p_role then
    return;
  end if;

  update app.tenant_member tm
     set role = p_role
   where tm.tenant_id = p_tenant_id and tm.user_id = p_user_id;

  insert into app.audit_log (tenant_id, user_id, action, entity, entity_id, antes, depois)
  values (p_tenant_id, (select auth.uid()), 'update', 'tenant_member', p_user_id::text,
          jsonb_build_object('role', v_old), jsonb_build_object('role', p_role));
end $$;

comment on function public.fn_definir_papel(uuid, uuid, app.user_role) is
  'Define o papel de um membro. Quem: só owner. Recusas P0001, nesta ordem: not_owner, '
  'member_not_found, ultimo_owner (rebaixar o último owner ativo). Papel igual não grava nada. '
  'Trava a linha do tenant antes de decidir: dois owners rebaixando um ao outro não zeram os '
  'owners. Grava audit_log (update) com o papel antes e depois.';

revoke execute on function public.fn_definir_papel(uuid, uuid, app.user_role) from public, anon;
grant  execute on function public.fn_definir_papel(uuid, uuid, app.user_role) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Scope: validate the whole new list, THEN swap — one transaction.
-- ---------------------------------------------------------------------------
create or replace function public.fn_definir_escopo(
  p_tenant_id uuid, p_user_id uuid, p_scope jsonb)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_companies uuid[];
  v_units     uuid[];
  v_new       jsonb;
  v_old       jsonb;
begin
  -- Outsiders are refused before the lock: they never wait for, nor hold,
  -- another tenant's row. The role itself is read again after the lock.
  if not util.has_tenant(p_tenant_id) then
    raise exception 'not_admin' using errcode = 'P0001';
  end if;

  perform 1 from app.tenant t where t.id = p_tenant_id for no key update;

  if not util.is_admin(p_tenant_id) then
    raise exception 'not_admin' using errcode = 'P0001';
  end if;

  if not exists (select 1 from app.tenant_member tm
                  where tm.tenant_id = p_tenant_id and tm.user_id = p_user_id) then
    raise exception 'member_not_found' using errcode = 'P0001';
  end if;

  -- ⛔ Validation BEFORE the delete: a refusal leaves the old scope intact.
  select array_agg(s.company_id order by s.company_id, s.unit_id nulls first),
         array_agg(s.unit_id    order by s.company_id, s.unit_id nulls first),
         jsonb_agg(jsonb_build_object('company_id', s.company_id, 'unit_id', s.unit_id)
                   order by s.company_id, s.unit_id nulls first)
    into v_companies, v_units, v_new
    from util.parse_user_scope(p_tenant_id, p_scope) s;

  select coalesce(jsonb_agg(jsonb_build_object('company_id', us.company_id, 'unit_id', us.unit_id)
                            order by us.company_id, us.unit_id nulls first), '[]'::jsonb)
    into v_old
    from app.user_scope us
   where us.tenant_id = p_tenant_id and us.user_id = p_user_id;

  if v_old = v_new then
    return;
  end if;

  delete from app.user_scope us
   where us.tenant_id = p_tenant_id and us.user_id = p_user_id;

  insert into app.user_scope (tenant_id, user_id, company_id, unit_id)
  select p_tenant_id, p_user_id, x.company_id, x.unit_id
    from unnest(v_companies, v_units) as x(company_id, unit_id);

  insert into app.audit_log (tenant_id, user_id, action, entity, entity_id, antes, depois)
  values (p_tenant_id, (select auth.uid()), 'update', 'user_scope', p_user_id::text, v_old, v_new);
end $$;

comment on function public.fn_definir_escopo(uuid, uuid, jsonb) is
  'Troca o escopo de um membro inteiro, numa transação: valida a lista nova antes de apagar a '
  'anterior. Quem: owner, hr, personnel. Recusas P0001, nesta ordem: not_admin, member_not_found, '
  'escopo_vazio, escopo_invalido, escopo_sem_empresa, empresa_fora_do_tenant, '
  'unidade_fora_da_empresa. p_scope = lista não vazia de {company_id, unit_id?}. Escopo igual não grava nada. Grava '
  'audit_log (update) com as listas antes e depois.';

revoke execute on function public.fn_definir_escopo(uuid, uuid, jsonb) from public, anon;
grant  execute on function public.fn_definir_escopo(uuid, uuid, jsonb) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. Deactivate: active = false and the date. Never a delete.
-- ---------------------------------------------------------------------------
create or replace function public.fn_desativar_membro(p_tenant_id uuid, p_user_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_role   app.user_role;
  v_active boolean;
  v_at     timestamptz;
begin
  -- Outsiders are refused before the lock: they never wait for, nor hold,
  -- another tenant's row. The role itself is read again after the lock.
  if not util.has_tenant(p_tenant_id) then
    raise exception 'not_admin' using errcode = 'P0001';
  end if;

  perform 1 from app.tenant t where t.id = p_tenant_id for no key update;

  if not util.is_admin(p_tenant_id) then
    raise exception 'not_admin' using errcode = 'P0001';
  end if;

  if p_user_id = (select auth.uid()) then
    raise exception 'e_voce_mesmo' using errcode = 'P0001';
  end if;

  select tm.role, tm.active into v_role, v_active
    from app.tenant_member tm
   where tm.tenant_id = p_tenant_id and tm.user_id = p_user_id;
  if not found then
    raise exception 'member_not_found' using errcode = 'P0001';
  end if;

  -- Already inactive: nothing changes, and the first date is kept.
  if not v_active then
    return;
  end if;

  -- Owner decision (05/10/2026): only an owner deactivates an owner.
  if v_role = 'owner' and not ('owner' = any(util.roles_in_tenant(p_tenant_id))) then
    raise exception 'owner_so_por_owner' using errcode = 'P0001';
  end if;

  if v_role = 'owner'
     and (select count(*) from app.tenant_member tm
           where tm.tenant_id = p_tenant_id and tm.role = 'owner' and tm.active) <= 1 then
    raise exception 'ultimo_owner' using errcode = 'P0001';
  end if;

  update app.tenant_member tm
     set active = false, deactivated_at = now()
   where tm.tenant_id = p_tenant_id and tm.user_id = p_user_id
  returning tm.deactivated_at into v_at;

  insert into app.audit_log (tenant_id, user_id, action, entity, entity_id, antes, depois)
  values (p_tenant_id, (select auth.uid()), 'update', 'tenant_member', p_user_id::text,
          jsonb_build_object('active', true, 'deactivated_at', null),
          jsonb_build_object('active', false, 'deactivated_at', v_at));
end $$;

comment on function public.fn_desativar_membro(uuid, uuid) is
  'Encerra o acesso: active = false e deactivated_at = now(). Nunca apaga o vínculo. Quem: owner, '
  'hr, personnel; owner só por owner (decisão de 05/10/2026). Recusas P0001, nesta ordem: '
  'not_admin, e_voce_mesmo, member_not_found, owner_so_por_owner, ultimo_owner (o último owner '
  'ativo). Membro já inativo não grava nada. Grava audit_log (update).';

revoke execute on function public.fn_desativar_membro(uuid, uuid) from public, anon;
grant  execute on function public.fn_desativar_membro(uuid, uuid) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  r         record;
  v_body    text;
  v_codes   text[];
  v_i       int;
  v_err     text;
  v_tenant  uuid := gen_random_uuid();
begin
  for r in
    select * from (values
      ('public.fn_convidar_usuario(uuid,uuid,jsonb)',
       array['not_admin', 'ja_e_membro', 'pg_advisory_xact_lock', 'conta_em_outro_cliente',
             'parse_user_scope']),
      ('public.fn_definir_papel(uuid,uuid,app.user_role)',
       array['not_owner', 'member_not_found', 'ultimo_owner']),
      ('public.fn_definir_escopo(uuid,uuid,jsonb)',
       array['not_admin', 'member_not_found', 'parse_user_scope', 'delete from app.user_scope']),
      ('public.fn_desativar_membro(uuid,uuid)',
       array['not_admin', 'e_voce_mesmo', 'member_not_found', 'owner_so_por_owner', 'ultimo_owner'])
    ) as f(sig, codes)
  loop
    -- 1. Definer with search_path locked to '' (item 9 of the 99).
    if not exists (select 1 from pg_proc p
                    where p.oid = r.sig::regprocedure and p.prosecdef
                      and p.proconfig @> array['search_path=""']) then
      raise exception '% não é definer com search_path = ''''', r.sig;
    end if;

    -- 2. The pair (SPEC §5.5): anon and PUBLIC out, authenticated and service_role in.
    if has_function_privilege('anon', r.sig, 'EXECUTE') then
      raise exception 'anon pode executar % — falta o revoke', r.sig;
    end if;
    if exists (select 1 from pg_proc p, aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
                where p.oid = r.sig::regprocedure and a.grantee = 0) then
      raise exception 'PUBLIC pode executar % — falta o revoke', r.sig;
    end if;
    if not has_function_privilege('authenticated', r.sig, 'EXECUTE')
       or not has_function_privilege('service_role', r.sig, 'EXECUTE') then
      raise exception 'authenticated/service_role não executam % — a tela daria 403', r.sig;
    end if;

    -- 3. The body, from the catalogue: membership checked BEFORE the lock (an
    --    outsider never holds another tenant's row), then the tenant lock,
    --    then the role read again and the refusals in order; never a delete
    --    of a member. The order is read from the lock onwards.
    v_body := pg_get_functiondef(r.sig::regprocedure);
    v_body := substr(v_body, position('begin' in v_body));
    if position('for no key update' in v_body) = 0
       or position('util.has_tenant(p_tenant_id)' in v_body) = 0
       or position('util.has_tenant(p_tenant_id)' in v_body) > position('for no key update' in v_body) then
      raise exception '% não confere o tenant antes do lock', r.sig;
    end if;
    if v_body !~ 'insert into app\.audit_log' then
      raise exception '% não grava audit_log', r.sig;
    end if;
    if v_body ~* 'delete\s+from\s+app\.tenant_member' then
      raise exception '% apaga membro — desativar é active = false', r.sig;
    end if;
    v_body := substr(v_body, position('for no key update' in v_body));
    v_codes := r.codes;
    for v_i in 1 .. cardinality(v_codes) loop
      if position(v_codes[v_i] in v_body) = 0 then
        raise exception '% não contém %', r.sig, v_codes[v_i];
      end if;
      if v_i > 1 and position(v_codes[v_i - 1] in v_body) > position(v_codes[v_i] in v_body) then
        raise exception '% recusa fora de ordem: % depois de %', r.sig, v_codes[v_i - 1], v_codes[v_i];
      end if;
    end loop;
  end loop;

  -- 3b. One customer per user: the condition is any other tenant, active
  --     membership, and it does NOT look at app.tenant.active.
  v_body := pg_get_functiondef('public.fn_convidar_usuario(uuid,uuid,jsonb)'::regprocedure);
  if position('o.tenant_id <> p_tenant_id and o.active' in v_body) = 0
     or position('hashtextextended(''tenant_member/user/'' || p_user_id::text, 0)' in v_body) = 0 then
    raise exception 'fn_convidar_usuario: conta_em_outro_cliente sem a condição ou sem a trava por usuário';
  end if;
  if substr(v_body, position('conta_em_outro_cliente' in v_body) - 400, 400) ~ 't\.active' then
    raise exception 'fn_convidar_usuario: conta_em_outro_cliente olha tenant.active — o suspenso escapa';
  end if;

  -- 4. The parser: nobody but the owner executes it.
  if has_function_privilege('anon', 'util.parse_user_scope(uuid,jsonb)', 'EXECUTE')
     or has_function_privilege('authenticated', 'util.parse_user_scope(uuid,jsonb)', 'EXECUTE') then
    raise exception 'util.parse_user_scope executável por anon/authenticated';
  end if;
  v_body := pg_get_functiondef('util.parse_user_scope(uuid,jsonb)'::regprocedure);
  if not (position('escopo_vazio' in v_body) < position('escopo_invalido' in v_body)
      and position('escopo_invalido' in v_body) < position('escopo_sem_empresa' in v_body)
      and position('escopo_sem_empresa' in v_body) < position('empresa_fora_do_tenant' in v_body)
      and position('empresa_fora_do_tenant' in v_body) < position('unidade_fora_da_empresa' in v_body)) then
    raise exception 'util.parse_user_scope recusa fora de ordem';
  end if;

  -- 5. Live, without a session: the first refusal of each is the role one.
  begin perform public.fn_convidar_usuario(v_tenant, gen_random_uuid(), '[]'); v_err := null;
  exception when sqlstate 'P0001' then v_err := sqlerrm; end;
  if v_err is distinct from 'not_admin' then
    raise exception 'fn_convidar_usuario sem sessão: %, não not_admin', coalesce(v_err, 'sucesso');
  end if;
  begin perform public.fn_definir_papel(v_tenant, gen_random_uuid(), 'viewer'); v_err := null;
  exception when sqlstate 'P0001' then v_err := sqlerrm; end;
  if v_err is distinct from 'not_owner' then
    raise exception 'fn_definir_papel sem sessão: %, não not_owner', coalesce(v_err, 'sucesso');
  end if;
  begin perform public.fn_definir_escopo(v_tenant, gen_random_uuid(), '[]'); v_err := null;
  exception when sqlstate 'P0001' then v_err := sqlerrm; end;
  if v_err is distinct from 'not_admin' then
    raise exception 'fn_definir_escopo sem sessão: %, não not_admin', coalesce(v_err, 'sucesso');
  end if;
  begin perform public.fn_desativar_membro(v_tenant, gen_random_uuid()); v_err := null;
  exception when sqlstate 'P0001' then v_err := sqlerrm; end;
  if v_err is distinct from 'not_admin' then
    raise exception 'fn_desativar_membro sem sessão: %, não not_admin', coalesce(v_err, 'sucesso');
  end if;

  raise notice 'OK: as quatro RPCs de usuário — definer travado, anon e PUBLIC fora, tenant travado antes de decidir, recusas em ordem, nenhum delete de membro, audit_log em todas; convite com um cliente por usuário, sob trava por usuário.';
end $$;
