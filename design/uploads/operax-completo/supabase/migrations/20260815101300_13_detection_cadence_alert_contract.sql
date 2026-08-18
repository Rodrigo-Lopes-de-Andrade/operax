-- ============================================================================
-- OperaX — 13. DETECTION CADENCE AND ALERT CONTENT CONTRACT
-- ----------------------------------------------------------------------------
-- Two decisions from the customer, encoded here instead of left to discipline.
--
-- 1. TWO CADENCES. Incremental detection runs after every 30-minute sync and
--    covers the current day only. A retroactive pass runs once a day over a
--    7-day window, because punches get corrected after the fact — without it,
--    yesterday's fix to a two-day-old punch never becomes a revocation.
--
--    "Not optional" has to mean "its absence is detectable". So the run records
--    its scope and fn_detection_health() reports when the backfill is overdue.
--
-- 2. THE ALERT CARRIES THE OBSERVED TIME, NEVER "NOW". At a 30-minute cadence a
--    10-minute delay reaches the manager up to 40 minutes after the fact. The
--    message has to read "entry recorded 08:12, expected 08:00" — not "so-and-so
--    is late". A trigger rejects any occurrence alert whose payload does not
--    carry the times the event actually has, so no template can drift into
--    relative phrasing.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Run scope
-- ---------------------------------------------------------------------------
alter table app.detection_run
  add column if not exists scope text not null default 'incremental';

alter table app.detection_run
  drop constraint if exists detection_run_scope_check;
alter table app.detection_run
  add  constraint detection_run_scope_check check (scope in ('incremental','backfill'));

comment on column app.detection_run.scope is
  'incremental = current day, after each sync (48x/day). '
  'backfill = 7-day retroactive window, once a day, off-peak.';

create index if not exists detection_run_backfill_idx
  on app.detection_run (tenant_id, started_at desc)
  where scope = 'backfill' and status = 'completed';

create index if not exists detection_run_incremental_idx
  on app.detection_run (tenant_id, started_at desc)
  where scope = 'incremental' and status = 'completed';

-- Health of the engine, mirroring fn_data_freshness for the sync side.
create or replace function public.fn_detection_health(
  p_backfill_max_age_hours int default 26   -- daily + 2h grace
) returns table (
  tenant_id                uuid,
  last_incremental_at      timestamptz,
  incremental_age_minutes  integer,
  last_backfill_at         timestamptz,
  backfill_age_hours       integer,
  backfill_overdue         boolean
)
language sql stable security definer set search_path = ''
as $$
  select r.tenant_id,
         max(r.started_at) filter (where r.scope = 'incremental'),
         (extract(epoch from (now() - max(r.started_at) filter (where r.scope = 'incremental'))) / 60)::int,
         max(r.started_at) filter (where r.scope = 'backfill'),
         (extract(epoch from (now() - max(r.started_at) filter (where r.scope = 'backfill'))) / 3600)::int,
         coalesce(
           now() - max(r.started_at) filter (where r.scope = 'backfill')
             > make_interval(hours => greatest(p_backfill_max_age_hours, 1)),
           true)          -- never ran = overdue
    from app.detection_run r
   where r.status = 'completed'
     and r.mode   = 'production'
     and r.tenant_id = any (util.user_tenants())
   group by r.tenant_id;
$$;

comment on function public.fn_detection_health(int) is
  'Backfill overdue is true when it has not completed in p_backfill_max_age_hours '
  'OR has never run. Never-ran must read as overdue, not as null.';

revoke execute on function public.fn_detection_health(int) from public, anon;
grant  execute on function public.fn_detection_health(int) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. Alert content contract
-- ---------------------------------------------------------------------------
create or replace function util.validate_alert_payload()
returns trigger
language plpgsql security definer set search_path = ''
as $$
declare
  ev record;
  faltando text := '';
begin
  if new.deviation_event_id is null then
    return new;                      -- aggregate/cycle alerts carry no occurrence
  end if;

  if jsonb_typeof(new.payload) is distinct from 'object' then
    raise exception using
      errcode = 'raise_exception',
      message = 'Alert payload must be a JSON object.',
      hint    = 'The occurrence alert needs structured fields, not a prebuilt string.';
  end if;

  select expected_time, actual_time, reference_date
    into ev
    from app.deviation_event
   where id = new.deviation_event_id;

  -- The date is always required: the message states the day, never "today".
  if new.payload ->> 'reference_date' is null then
    faltando := faltando || 'reference_date ';
  end if;

  -- Times are required only when the event actually has them. `no_punches`
  -- legitimately has no actual_time; demanding it would be a false constraint.
  if ev.expected_time is not null and new.payload ->> 'expected_time' is null then
    faltando := faltando || 'expected_time ';
  end if;
  if ev.actual_time is not null and new.payload ->> 'actual_time' is null then
    faltando := faltando || 'actual_time ';
  end if;

  if faltando <> '' then
    raise exception using
      errcode = 'raise_exception',
      message = format('Occurrence alert payload is missing: %s', trim(faltando)),
      hint    = 'Sync runs every 30 minutes, so an alert can arrive up to 40 minutes '
             || 'after the fact. It must state the observed time ("entry recorded '
             || '08:12, expected 08:00"), never a relative "now".';
  end if;

  return new;
end $$;

drop trigger if exists trg_validate_alert_payload on app.alert_queue;
create trigger trg_validate_alert_payload
  before insert or update on app.alert_queue
  for each row execute function util.validate_alert_payload();

-- ---------------------------------------------------------------------------
-- 3. The EXECUTE lockdown has to be permanent, not a one-off
-- ---------------------------------------------------------------------------
-- Migration 11 swept util/app and revoked EXECUTE from PUBLIC and anon. That
-- sweep ran once. This migration then created util.validate_alert_payload(),
-- which was born with the Postgres default of EXECUTE to PUBLIC — and the
-- isolation suite caught it immediately.
--
-- Fixing this one function would leave the same hole open for migration 14. So
-- the lockdown becomes an event trigger: every function created in util or app
-- from now on loses PUBLIC and anon the moment it exists. Same reasoning as the
-- trigger that blocks tables in `public` — enforce the invariant, do not rely on
-- whoever writes the next migration remembering it.
create or replace function util.lock_down_new_function()
returns event_trigger
language plpgsql
as $$
declare obj record;
begin
  for obj in select * from pg_event_trigger_ddl_commands()
  loop
    if obj.object_type = 'function' and obj.schema_name in ('util','app') then
      execute format('revoke execute on function %s from public, anon', obj.object_identity);
    end if;
  end loop;
end $$;

drop event trigger if exists trg_lock_down_new_function;
create event trigger trg_lock_down_new_function
  on ddl_command_end
  when tag in ('CREATE FUNCTION')
  execute function util.lock_down_new_function();

comment on function util.lock_down_new_function() is
  'Keeps the migration-11 sweep permanent. Grant EXECUTE explicitly to '
  'authenticated/service_role after creating a helper — never to PUBLIC.';

-- Close the one this migration opened, and the guard itself: the event trigger
-- does not exist yet while its own function is being created, so it cannot
-- guard its own birth. Every later function is covered automatically.
revoke execute on function util.validate_alert_payload()  from public, anon;
revoke execute on function util.lock_down_new_function()  from public, anon;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_trigger where tgname = 'trg_validate_alert_payload') then
    raise exception 'alert payload contract trigger not installed';
  end if;
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'public' and p.proname = 'fn_detection_health'
               and has_function_privilege('anon', p.oid, 'EXECUTE')) then
    raise exception 'fn_detection_health is executable by anon';
  end if;
  raise notice 'OK: cadence recorded and alert content contract enforced.';
end $$;
