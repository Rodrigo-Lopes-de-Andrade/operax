-- ============================================================================
-- OperaX — 12. DATA FRESHNESS
-- ----------------------------------------------------------------------------
-- Sync cadence is 30 minutes (customer decision). That makes the daily monitor
-- viable, and it makes staleness a first-class product concern.
--
-- A manager looking at the board at 09:05 must not conclude "nobody is late"
-- when the last successful sync ran at 08:40. The screen has to say how old the
-- data is, so the number it shows can be trusted for what it is.
--
-- Why a function and not a view over app.sync_run: that table is admin-only by
-- policy, and its `error` column can carry provider messages. Everyone in the
-- tenant needs freshness; nobody outside admin needs the error text. So this
-- exposes four safe columns, derives the tenant from the session, and takes no
-- tenant parameter — there is no way to probe another tenant with it.
-- ============================================================================

create index if not exists sync_run_freshness_idx
  on app.sync_run (tenant_id, entity, finished_at desc)
  where status = 'completed';

create or replace function public.fn_data_freshness(p_stale_after_minutes int default 45)
returns table (
  tenant_id      uuid,
  entity         text,
  last_sync_at   timestamptz,
  age_minutes    integer,
  is_stale       boolean
)
language sql stable security definer set search_path = ''
as $$
  select s.tenant_id,
         s.entity,
         max(s.finished_at)                                                as last_sync_at,
         (extract(epoch from (now() - max(s.finished_at))) / 60)::int      as age_minutes,
         now() - max(s.finished_at) > make_interval(mins => greatest(p_stale_after_minutes, 1))
    from app.sync_run s
   where s.status = 'completed'
     and s.finished_at is not null
     and s.tenant_id = any (util.user_tenants())
   group by s.tenant_id, s.entity;
$$;

comment on function public.fn_data_freshness(int) is
  'Data age per synced entity, for the "updated N minutes ago" indicator. '
  'Default threshold is 45 min — 1.5x the 30-minute cadence, so a single '
  'missed run does not raise a false alarm but two in a row do.';

revoke execute on function public.fn_data_freshness(int) from public, anon;
grant  execute on function public.fn_data_freshness(int) to authenticated, service_role;

-- Register it in the AI catalogue: "is today's data up to date?" is a fair
-- question and it should not get "I don't have that".
insert into app.metric (code, title, description, target_view, dimensions, filters, domain)
values ('data_freshness', 'Data freshness',
        'How old the synced data is, per entity',
        'fn_data_freshness', array['entity'], array['stale_after_minutes'], null)
on conflict (code) do nothing;

do $$
declare n int;
begin
  select count(*) into n
  from pg_proc p join pg_namespace ns on ns.oid = p.pronamespace
  where ns.nspname = 'public' and p.proname = 'fn_data_freshness'
    and has_function_privilege('anon', p.oid, 'EXECUTE');
  if n > 0 then
    raise exception 'fn_data_freshness is executable by anon';
  end if;
  raise notice 'OK: freshness exposed to authenticated only.';
end $$;
