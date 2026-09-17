-- ============================================================================
-- OperaX — assistant_publish_fn. FREEZE THE DRAFT, MOVE THE POINTER — ATOMIC
-- ----------------------------------------------------------------------------
-- Design in `docs/SPEC-AGENTE.md` §3d. Publishing = freeze the draft into a
-- new immutable version AND move the tenant pointer to it, in one function:
-- two statements from the application would leave the database inconsistent
-- on a partial failure.
--
-- FIVE REFUSALS, IN THIS ORDER, EACH `P0001` WITH THE CODE AS THE MESSAGE
--   1. not_admin               — util.is_admin(p_tenant_id) is false
--   2. draft_not_found         — no draft for the tenant
--   3. draft_empty             — blank content
--   4. platform_layer_missing  — no platform pointer: a tenant layer without
--                                the doctrine under it is an assistant with
--                                no refusal contract
--   5. draft_unchanged         — identical to the version the tenant pointer
--                                points at (the POINTED one, not the latest:
--                                after a rollback the draft may equal v2
--                                while v1 is on the air, and that publishes)
--
-- `not_admin` COMES FIRST — BEFORE THE CALLER LEARNS ANYTHING (cycle 2)
-- With `draft_not_found` first, the owner of another tenant calling with this
-- tenant's id learned whether it has a draft (and whether the tenant exists at
-- all): the two codes differ. The lock still happens first — `found` is kept
-- in a variable and judged only after the role check.
--
-- ⛔ THE FUNCTION IS `security definer` AND CHECKS THE ROLE ITSELF
-- It does not inherit the caller's RLS, so `util.is_admin` is called here, on
-- purpose. The test that separates `is_admin` from `has_tenant` is the UNIT
-- SUPERVISOR of the same tenant (member, not admin): the owner of another
-- tenant is refused by either helper.
--
-- ⛔ THE FIRST STATEMENT LOCKS THE DRAFT — `for update`
-- `version_number` is `max + 1` (never `count + 1`: a version deleted by the
-- database owner would make the count collide with a number still taken);
-- two concurrent publications of the same tenant would read the same max and
-- the second would die on the unique index. The draft is the only object that
-- always exists at publish time (the pointer does not, on the first
-- publication), so it is the lock.
--
-- ⚠️ `trg_lock_down_new_function` DOES NOT COVER `public`. The revoke and the
-- `grant execute … to authenticated` are written here; without the grant the
-- RPC is born unreachable and the symptom is a 403 with nothing in the log.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

create or replace function public.fn_publish_assistant_prompt(p_tenant_id uuid)
returns table (version_id uuid, version_number integer, previous_version_id uuid)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_draft_content text;
  v_found         boolean;
  v_pointed       uuid;
  v_number        integer;
  v_new_id        uuid;
begin
  -- Lock the draft. First of everything: serialises every publication of
  -- this tenant from here on. Whether it exists is judged only after the role.
  select d.content
    into v_draft_content
    from app.assistant_draft d
   where d.tenant_id = p_tenant_id
     for update;
  v_found := found;

  -- 1. Definer does not inherit RLS: the role is checked here, by the same
  --    helper the draft policy uses. `auth.uid()` is a session setting, so it
  --    answers the same under definer with an empty search_path.
  if not util.is_admin(p_tenant_id) then
    raise exception 'not_admin' using errcode = 'P0001';
  end if;

  -- 2. Nothing to publish.
  if not v_found then
    raise exception 'draft_not_found' using errcode = 'P0001';
  end if;

  -- 3. Blank text is not a version.
  if btrim(v_draft_content) = '' then
    raise exception 'draft_empty' using errcode = 'P0001';
  end if;

  -- 4. No doctrine under it, no tenant layer on top of it.
  if not exists (
    select 1 from app.assistant_prompt_pointer p
     where p.layer = 'platform' and p.tenant_id is null
  ) then
    raise exception 'platform_layer_missing' using errcode = 'P0001';
  end if;

  -- 5. Compared with the version ON THE AIR (the pointer), never with the
  --    latest one: a rollback leaves the pointer behind the newest version.
  select p.version_id
    into v_pointed
    from app.assistant_prompt_pointer p
   where p.tenant_id = p_tenant_id and p.layer = 'tenant';
  if v_pointed is not null and exists (
    select 1 from app.assistant_prompt_version v
     where v.id = v_pointed and v.content = v_draft_content
  ) then
    raise exception 'draft_unchanged' using errcode = 'P0001';
  end if;

  -- Freeze: the next number in the tenant's scope, safe under the lock above.
  select coalesce(max(v.version_number), 0) + 1
    into v_number
    from app.assistant_prompt_version v
   where v.tenant_id = p_tenant_id and v.layer = 'tenant';

  insert into app.assistant_prompt_version
         (tenant_id, layer, version_number, content, created_by)
  values (p_tenant_id, 'tenant', v_number, v_draft_content, auth.uid())
  returning id into v_new_id;

  -- Move the pointer (first publication inserts it; the partial index is the
  -- conflict target — its predicate has to be named for the inference).
  insert into app.assistant_prompt_pointer (tenant_id, layer, version_id, updated_at, updated_by)
  values (p_tenant_id, 'tenant', v_new_id, now(), auth.uid())
  on conflict (tenant_id, layer) where tenant_id is not null
  do update set version_id = excluded.version_id,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by;

  -- The draft now descends from the version it just became.
  update app.assistant_draft d
     set frozen_from_version_id = v_new_id,
         updated_at             = now(),
         updated_by             = auth.uid()
   where d.tenant_id = p_tenant_id;

  return query select v_new_id, v_number, v_pointed;
end $$;

comment on function public.fn_publish_assistant_prompt(uuid) is
  'Publica o rascunho do tenant: congela em versão nova (imutável) e move o '
  'ponteiro, na mesma transação. Cinco recusas, nesta ordem, cada uma P0001 com '
  'a mensagem = código: not_admin, draft_not_found, draft_empty, '
  'platform_layer_missing, draft_unchanged (idêntico à versão APONTADA, não à '
  'última). not_admin vem antes de tudo: o owner de outro tenant não aprende se '
  'este tem rascunho. A primeira instrução trava o rascunho (for update) e '
  'serializa publicações concorrentes do mesmo tenant. Definer: checa '
  'util.is_admin ela mesma. Devolve (version_id, version_number, '
  'previous_version_id).';

-- The trigger does not cover public: written, both sides.
revoke execute on function public.fn_publish_assistant_prompt(uuid) from public, anon;
grant  execute on function public.fn_publish_assistant_prompt(uuid) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_oid    oid;
  v_secdef boolean;
  v_config text;
  v_src    text;
  v_body   text;
begin
  select p.oid, p.prosecdef, coalesce(array_to_string(p.proconfig, ','), '')
    into v_oid, v_secdef, v_config
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname = 'fn_publish_assistant_prompt';
  if v_oid is null then
    raise exception 'public.fn_publish_assistant_prompt(uuid) does not exist';
  end if;

  -- 1. Definer with search_path locked — item 9 of scripts/99_verificacao_rls.sql.
  if not v_secdef then
    raise exception 'public.fn_publish_assistant_prompt is not security definer';
  end if;
  if v_config not like '%search_path=%' then
    raise exception 'public.fn_publish_assistant_prompt is definer WITHOUT search_path locked';
  end if;

  -- 2. anon cannot execute; authenticated can. No net under public.
  if has_function_privilege('anon', v_oid, 'EXECUTE') then
    raise exception 'anon can execute public.fn_publish_assistant_prompt';
  end if;
  if not has_function_privilege('authenticated', v_oid, 'EXECUTE') then
    raise exception 'authenticated cannot execute public.fn_publish_assistant_prompt — the Publicar button would 403 with nothing in the log';
  end if;

  -- 3. The body: the lock is the first statement, and the five codes are there
  --    in order. Read from the catalogue, not from this file.
  v_src  := pg_get_functiondef(v_oid);
  v_body := substr(v_src, position('begin' in lower(v_src)));
  if position('for update' in lower(v_body)) = 0 then
    raise exception 'public.fn_publish_assistant_prompt has no "for update" on the draft — concurrent publications would collide on the unique index';
  end if;
  if position('for update' in lower(v_body)) > position('not_admin' in v_body) then
    raise exception 'public.fn_publish_assistant_prompt decides before it locks — the lock must be the first statement';
  end if;
  if not (position('not_admin' in v_body) < position('draft_not_found' in v_body)
      and position('draft_not_found' in v_body) < position('draft_empty' in v_body)
      and position('draft_empty' in v_body) < position('platform_layer_missing' in v_body)
      and position('platform_layer_missing' in v_body) < position('draft_unchanged' in v_body)) then
    raise exception 'public.fn_publish_assistant_prompt refuses in the wrong order (SPEC §3d): not_admin, draft_not_found, draft_empty, platform_layer_missing, draft_unchanged';
  end if;
  if v_body not like '%util.is_admin(p_tenant_id)%' then
    raise exception 'public.fn_publish_assistant_prompt does not check util.is_admin itself — definer inherits no RLS';
  end if;
  if v_body not like '%max(v.version_number)%' then
    raise exception 'public.fn_publish_assistant_prompt does not number by max + 1 — a count would collide after any delete by the database owner';
  end if;

  raise notice 'OK: public.fn_publish_assistant_prompt — definer locked, anon out, authenticated in, draft locked first, not_admin before anything is learned, five refusals in order, max + 1.';
end $$;
