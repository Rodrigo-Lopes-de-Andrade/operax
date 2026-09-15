-- ============================================================================
-- OperaX — ch_adhesion_fn. ADHESION BY UNIT: COUNTS, NEVER A chat_id
-- ----------------------------------------------------------------------------
-- Design in `docs/SPEC-CANAIS.md` §3.2. Owner decision of 15/09/2026
-- (`docs/SPRINTS-CANAIS.md` §C3, item 1): no panel role reads
-- `app.messaging_identity`, not even owner; what the screen needs comes from
-- this function — `security definer`, cut by `util.user_tenants()`, counts per
-- unit, `grant execute` written.
--
-- The screen does not need the chat_id. It needs "how many joined", by unit,
-- so the person driving adhesion (C4) knows where to go next. So the function
-- returns three counts per unit and nothing that names a person: no name, no
-- `employee_id`, no `contact_id`, no `external_id`. The proof block asserts
-- that on the return type, and `scripts/99_verificacao_rls.sql` item 9 keeps
-- asserting it for every definer in `public`.
--
-- WHAT EACH COUNT COUNTS — active employees of the unit (`status <>
-- 'desligado'`, the same "active" `operax/motor/cadastro.py` reports), and
-- the three are a PARTITION of them:
--   joined  — has a current identity (`revoked_at is null`);
--   revoked — no current identity, and at least one revoked one (blocked the
--             bot, or was unlinked, and did not come back);
--   pending — never had an identity. An open invite does not move the person
--             out of pending: invited-and-waiting is still "has not joined",
--             which is what the C4 field work needs to see.
-- joined + pending + revoked = active employees of the unit. A fourth silent
-- state would make the screen's numbers not add up, and that is the kind of
-- quiet wrong this project refuses.
--
-- ⚠️ RESPONSIBLES (`app.contact`) ARE OUT OF THIS COUNT
-- A contact answers for zero, one or many units (`app.unit_responsible`), so
-- "per unit" has no single answer for them. Their adhesion is a per-tenant
-- number, not a per-unit one, and it is not this function's.
--
-- ⚠️ `trg_lock_down_new_function` DOES NOT COVER `public`. The grant is here.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

create or replace function public.fn_telegram_adhesion()
returns table (
  unit_id    uuid,
  unit_name  text,
  joined     integer,
  pending    integer,
  revoked    integer
)
language sql stable security definer set search_path = ''
as $$
  with visible_unit as (
    -- The whole cut lives here: tenant + scope, by the same helpers the
    -- policies use. A unit supervisor gets the units in `app.user_scope`;
    -- owner, executive, hr and personnel get the tenant.
    select u.id, u.name
      from app.unit u
     where u.tenant_id = any (util.user_tenants())
       and util.can_see_unit(u.id)
  ),
  person as (
    select e.id, e.unit_id,
           exists (select 1 from app.messaging_identity mi
                    where mi.employee_id = e.id
                      and mi.channel = 'telegram'
                      and mi.revoked_at is null)     as has_current,
           exists (select 1 from app.messaging_identity mi
                    where mi.employee_id = e.id
                      and mi.channel = 'telegram'
                      and mi.revoked_at is not null) as has_revoked
      from app.employee e
      join visible_unit u on u.id = e.unit_id
     where e.status <> 'desligado'
  )
  select u.id,
         u.name,
         (count(p.id) filter (where p.has_current))::int                        as joined,
         (count(p.id) filter (where not p.has_current and not p.has_revoked))::int as pending,
         (count(p.id) filter (where not p.has_current and p.has_revoked))::int  as revoked
    from visible_unit u
    left join person p on p.unit_id = u.id
   group by u.id, u.name;
$$;

comment on function public.fn_telegram_adhesion() is
  'Adesão ao Telegram por unidade: colaboradores ATIVOS da unidade com identidade '
  'vigente (joined), sem identidade alguma (pending — convite em aberto não tira '
  'ninguém daqui) e com identidade revogada e nenhuma vigente (revoked). Os três '
  'somam os ativos da unidade. Nome nenhum, chat_id nenhum, contact_id nenhum: é '
  'a única superfície do painel sobre app.messaging_identity, que nenhum papel lê. '
  'Recorte por util.user_tenants() + util.can_see_unit: o supervisor vê só as '
  'unidades dele. Responsáveis (app.contact) ficam FORA desta contagem: não têm '
  'unidade única.';

revoke execute on function public.fn_telegram_adhesion() from public, anon;
grant  execute on function public.fn_telegram_adhesion() to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
-- ⚠️ What it does NOT do, on purpose: it does not seed users to prove the cut
-- or the counts. That would write `auth.users` in production. The functional
-- proof — owner sees both units with the right numbers, supervisor sees only
-- his — lives in `scripts/98_teste_isolamento_tenant.sql`, in a rolled-back
-- transaction, and runs on `make db-test`.
do $$
declare
  v_oid       oid;
  v_secdef    boolean;
  v_config    text;
  v_colunas   text[];
  v_src       text;
begin
  select p.oid, p.prosecdef, coalesce(array_to_string(p.proconfig, ','), '')
    into v_oid, v_secdef, v_config
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname = 'fn_telegram_adhesion';
  if v_oid is null then
    raise exception 'public.fn_telegram_adhesion() does not exist';
  end if;

  -- 1. Definer with search_path locked. It reads a table no panel role can
  --    read; definer is the whole reason it exists, and an unlocked
  --    search_path is privilege escalation waiting for a temp schema.
  if not v_secdef then
    raise exception 'public.fn_telegram_adhesion() is not security definer — it could not read messaging_identity for anyone';
  end if;
  if v_config not like '%search_path=%' then
    raise exception 'public.fn_telegram_adhesion() is definer WITHOUT search_path locked';
  end if;

  -- 2. anon out, authenticated in.
  if has_function_privilege('anon', v_oid, 'EXECUTE') then
    raise exception 'anon can execute public.fn_telegram_adhesion()';
  end if;
  if not has_function_privilege('authenticated', v_oid, 'EXECUTE') then
    raise exception 'authenticated cannot execute public.fn_telegram_adhesion() — the adhesion screen would never load';
  end if;

  -- 3. ⛔ COUNTS, NEVER A PERSON — asserted on the RETURN TYPE. A future
  --    `create or replace` that adds `employee_id` or `external_id` "since we
  --    are here" does not run.
  --    The columns are read from `pg_proc` (the OUT arguments of `returns
  --    table`), by exact name: `unit_name` is the unit's, and allowed; a column
  --    called `name` is a person's, and is not.
  select array_agg(a.n order by a.n) into v_colunas
    from pg_proc p,
         unnest(p.proargnames, p.proargmodes) as a(n, m)
   where p.oid = v_oid and a.m = 't';
  if v_colunas is null then
    raise exception 'public.fn_telegram_adhesion() does not return a table';
  end if;
  if v_colunas && array['external_id','chat_id','contact_id','employee_id','name'] then
    raise exception 'public.fn_telegram_adhesion() returns per-person data (%) — it is counts per unit, and the chat_id never leaves the backend',
      v_colunas;
  end if;
  if exists (select 1 from unnest(v_colunas) c
              where c ~* '(employee|colaborador|contact|external|chat|cpf|phone)') then
    raise exception 'public.fn_telegram_adhesion() returns a column that names a person: %', v_colunas;
  end if;
  if v_colunas <> array['joined','pending','revoked','unit_id','unit_name'] then
    raise exception 'public.fn_telegram_adhesion() changed its contract: %', v_colunas;
  end if;

  -- 4. The cut is by tenant AND by unit scope, by the same helpers the
  --    policies use. Read from the catalogue.
  v_src := pg_get_functiondef(v_oid);
  if v_src not like '%util.user_tenants()%' or v_src not like '%util.can_see_unit(%' then
    raise exception 'public.fn_telegram_adhesion() lost the tenant or the unit cut';
  end if;
  -- And it counts ACTIVE employees only: unlinking a dismissed employee is not
  -- field work anyone should be sent to do.
  if v_src not like '%status <> ''desligado''%' then
    raise exception 'public.fn_telegram_adhesion() counts dismissed employees';
  end if;

  -- 5. No caller, no rows.
  if exists (select 1 from public.fn_telegram_adhesion()) then
    raise exception 'public.fn_telegram_adhesion() returned rows with no authenticated user';
  end if;

  raise notice 'OK: public.fn_telegram_adhesion() — counts per unit, definer locked, anon out, nothing per person in the return type.';
end $$;
