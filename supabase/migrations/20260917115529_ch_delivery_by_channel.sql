-- ============================================================================
-- OperaX — ch_delivery_by_channel. DELIVERY BROKEN DOWN BY CHANNEL, BY WEEK
-- ----------------------------------------------------------------------------
-- Design in `docs/SPEC-CANAIS.md` §8, consequence 3: *"`app.alert_sent.provider`
-- passa a ter quatro valores, e o relatório de entrega quebra por canal sem
-- trabalho novo"*. This is that report, as one RPC. It is the metric that
-- justifies the whole Canais stage (`docs/SPRINTS-CANAIS.md` §C5, "Gate"):
-- every responsible who adheres to Telegram leaves the customer's WhatsApp
-- number, and the number that can be banned without appeal
-- (`docs/DECISAO-WHATSAPP.md` §1) carries less. The screen (C5, wave 2) shows
-- the WhatsApp column falling as the Telegram column rises.
--
-- INVOKER, NOT DEFINER — AND WHY THE SUPERVISOR SEES NOTHING
-- `app.alert_sent` already has its policy: `alert_sent_read`, `util.is_admin`
-- (owner, hr, personnel), from migration 06. This function reads the table AS
-- THE CALLER, so that policy is the whole cut: an admin sees their tenant's
-- weeks, a unit supervisor sees zero rows. That is the design, not a gap — a
-- delivery log is an administrator's instrument, and a definer here would be
-- a second, hand-written copy of the same rule, drifting at the first change.
--
-- COUNTS, NEVER A DESTINATION
-- `alert_sent` carries `destination_hash`, never the number or the chat_id,
-- and this function does not return even the hash: week, channel, provider,
-- sent, failed. The proof block asserts that on the return type by exact
-- name, and `scripts/99_verificacao_rls.sql` keeps asserting it.
--
-- THE SECOND THING HERE: `fn_telegram_adhesion` GAINS AN `order by`
-- Named in "C4 fechado no código" as inherited by C5. The screen listed units
-- in whatever order the planner produced; `order by u.name` is what the
-- adhesion screen sorted by hand. `create or replace` keeps grants and
-- comment; they are restated anyway, because a grant that exists only by
-- inheritance is a grant nobody wrote.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Delivery by channel, by week
-- ---------------------------------------------------------------------------
-- `p_weeks` counts back from the current week INCLUDING it: the default of 8
-- is the current week plus the seven before. `date_trunc('week')` is ISO
-- (Monday), in the session time zone — UTC on Supabase — the same week the
-- rest of the panel uses.
create or replace function public.fn_delivery_by_channel(p_weeks integer default 8)
returns table (
  week_start date,
  channel    text,
  provider   text,
  sent       integer,
  failed     integer
)
language sql stable security invoker set search_path = ''
as $$
  select date_trunc('week', s.sent_at)::date                                       as week_start,
         s.channel,
         s.provider,
         (count(*) filter (where s.status in ('sent', 'delivered', 'read')))::int as sent,
         (count(*) filter (where s.status = 'failed'))::int                       as failed
    from app.alert_sent s
   where s.sent_at >= date_trunc('week', now()) - make_interval(weeks => greatest(p_weeks, 1) - 1)
   group by 1, 2, 3
   order by week_start, channel, provider;
$$;

comment on function public.fn_delivery_by_channel(integer) is
  'Entregas por semana, canal e provedor, nas últimas p_weeks semanas (a atual '
  'inclusa): sent conta sent/delivered/read, failed conta failed. É o relatório '
  'da SPEC-CANAIS §8 (consequência 3) — a coluna de WhatsApp cai conforme a '
  'adesão ao Telegram sobe. Security INVOKER: lê app.alert_sent pela policy '
  'alert_sent_read (util.is_admin), então quem não é owner/hr/personnel recebe '
  'zero linhas. Nem nome, nem destino, nem hash: só contagens.';

revoke execute on function public.fn_delivery_by_channel(integer) from public, anon;
grant  execute on function public.fn_delivery_by_channel(integer) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. `fn_telegram_adhesion` ordered by unit name
-- ---------------------------------------------------------------------------
-- The body is `ch_adhesion_fn` verbatim plus the final `order by`. Everything
-- that migration's proof asserts (definer locked, anon out, five columns,
-- tenant + unit cut, active employees only) holds here and is re-asserted.
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
   group by u.id, u.name
   order by u.name;
$$;

revoke execute on function public.fn_telegram_adhesion() from public, anon;
grant  execute on function public.fn_telegram_adhesion() to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
-- ⚠️ What it does NOT do, on purpose: it does not seed `alert_sent` or users
-- to prove the tenant cut — the migration runs as the owner of the schema,
-- who bypasses RLS, so a functional proof here would prove nothing. The cut
-- is proved in `scripts/98_teste_isolamento_tenant.sql` (two tenants, each
-- admin sees their own week, the supervisor sees none), on `make db-test`.
do $$
declare
  v_oid     oid;
  v_secdef  boolean;
  v_colunas text[];
  v_src     text;
begin
  -- 1. The delivery function exists, ONCE, and is invoker.
  if (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
       where n.nspname = 'public' and p.proname = 'fn_delivery_by_channel') <> 1 then
    raise exception 'public.fn_delivery_by_channel must exist with exactly one signature';
  end if;
  select p.oid, p.prosecdef into v_oid, v_secdef
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname = 'fn_delivery_by_channel';
  if v_secdef then
    raise exception 'public.fn_delivery_by_channel is security definer — it would read every tenant''s log for anyone';
  end if;

  -- 2. anon out, authenticated in.
  if has_function_privilege('anon', v_oid, 'EXECUTE') then
    raise exception 'anon can execute public.fn_delivery_by_channel';
  end if;
  if has_function_privilege('public', v_oid, 'EXECUTE') then
    raise exception 'public can execute public.fn_delivery_by_channel';
  end if;
  if not has_function_privilege('authenticated', v_oid, 'EXECUTE') then
    raise exception 'authenticated cannot execute public.fn_delivery_by_channel — the report would never load';
  end if;

  -- 3. ⛔ COUNTS, NEVER A PERSON OR A DESTINATION — on the return type, by
  --    exact name. `destination_hash` is a hash of a phone number; it does
  --    not leave `app` either.
  select array_agg(a.n order by a.n) into v_colunas
    from pg_proc p, unnest(p.proargnames, p.proargmodes) as a(n, m)
   where p.oid = v_oid and a.m = 't';
  if v_colunas is null then
    raise exception 'public.fn_delivery_by_channel does not return a table';
  end if;
  if v_colunas <> array['channel', 'failed', 'provider', 'sent', 'week_start'] then
    raise exception 'public.fn_delivery_by_channel changed its contract: %', v_colunas;
  end if;

  -- 4. It reads the log and nothing else, and reads it under the caller.
  v_src := pg_get_functiondef(v_oid);
  if v_src not like '%from app.alert_sent%' then
    raise exception 'public.fn_delivery_by_channel does not read app.alert_sent';
  end if;
  if v_src ~* 'destination|external_id|chat_id|app\.contact|app\.employee|app\.alert_queue' then
    raise exception 'public.fn_delivery_by_channel reaches a destination or a person';
  end if;

  -- 5. It runs (as the migration runner, who bypasses RLS — so nothing is
  --    asserted about the rows) and the window is never unbounded: a
  --    `p_weeks` of zero or less is the current week, not "everything".
  perform * from public.fn_delivery_by_channel();
  perform * from public.fn_delivery_by_channel(1);
  perform * from public.fn_delivery_by_channel(0);
  if v_src not like '%greatest(p_weeks, 1)%' then
    raise exception 'public.fn_delivery_by_channel lost the floor on p_weeks';
  end if;

  -- 6. `fn_telegram_adhesion` is ordered, still definer locked, still anon-free,
  --    still the same five columns and the same cut.
  select p.oid, p.prosecdef, coalesce(array_to_string(p.proconfig, ','), '')
    into v_oid, v_secdef, v_src
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname = 'fn_telegram_adhesion';
  if v_oid is null then
    raise exception 'public.fn_telegram_adhesion() does not exist';
  end if;
  if not v_secdef or v_src not like '%search_path=%' then
    raise exception 'public.fn_telegram_adhesion() lost definer or search_path';
  end if;
  if has_function_privilege('anon', v_oid, 'EXECUTE') then
    raise exception 'anon can execute public.fn_telegram_adhesion()';
  end if;
  if not has_function_privilege('authenticated', v_oid, 'EXECUTE') then
    raise exception 'authenticated cannot execute public.fn_telegram_adhesion()';
  end if;
  v_src := pg_get_functiondef(v_oid);
  if v_src !~* 'order by\s+u\.name' then
    raise exception 'public.fn_telegram_adhesion() is not ordered by unit name';
  end if;
  if v_src not like '%util.user_tenants()%' or v_src not like '%util.can_see_unit(%'
     or v_src not like '%status <> ''desligado''%' then
    raise exception 'public.fn_telegram_adhesion() lost the tenant, unit or active cut';
  end if;
  select array_agg(a.n order by a.n) into v_colunas
    from pg_proc p, unnest(p.proargnames, p.proargmodes) as a(n, m)
   where p.oid = v_oid and a.m = 't';
  if v_colunas <> array['joined', 'pending', 'revoked', 'unit_id', 'unit_name'] then
    raise exception 'public.fn_telegram_adhesion() changed its contract: %', v_colunas;
  end if;
  if exists (select 1 from public.fn_telegram_adhesion()) then
    raise exception 'public.fn_telegram_adhesion() returned rows with no authenticated user';
  end if;

  raise notice 'OK: public.fn_delivery_by_channel — invoker, counts only, anon out; fn_telegram_adhesion ordered by unit name.';
end $$;
