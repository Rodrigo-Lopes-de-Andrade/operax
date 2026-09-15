-- ============================================================================
-- OperaX — ch_channel_health. THE WATCHER THAT ASKS — AND WRITES THE AGE
-- ----------------------------------------------------------------------------
-- Design in `docs/SPEC-CANAIS.md` §7. Owner decision of 15/09/2026
-- (`docs/SPRINTS-CANAIS.md` §C3, item 1): `app.channel_health` is read by
-- `authenticated` under `util.has_tenant(tenant_id)` — it is channel state, not
-- personal data, and the unit supervisor is entitled to know the channel is
-- down — and written only by `service_role` (`select, insert, update`).
--
-- WHY IT EXISTS
-- The webhook goes silent exactly when it matters most: while the transport is
-- alive it reports in seconds; when the transport dies, no event arrives — and
-- "no event" is indistinguishable from "all fine". So the backend ASKS the
-- provider on a schedule (wave 2, the watcher) and records the answer here,
-- with its age. It is `public.fn_data_freshness` (migration 12) applied to the
-- channel: in OperaX, data without an age is not data, and neither is a
-- connection.
--
-- ⛔ `status_changed_at` ONLY MOVES WHEN THE STATUS CHANGES
-- That is the rule of §7 — it measures time IN the state — and it lives here,
-- in `app.fn_record_channel_health`, not in Python. A watcher rewritten in
-- another language, or a manual `select app.fn_record_channel_health(...)`
-- from the console, gets the same rule. `checked_at` moves on every call.
--
-- ⛔ THE WATCHER DOES NOT RECONNECT
-- Nothing here reconnects, and wave 2 must not either: reconnecting a number
-- that dropped because the platform blocked it turns a temporary suspension
-- into a permanent one (`docs/DECISAO-WHATSAPP.md` §1). The function records.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. One row per integration
-- ---------------------------------------------------------------------------
create table if not exists app.channel_health (
  --: One row per integration; the primary key is the uniqueness the design
  --: asks for. Upsert is `on conflict (integration_id)`.
  integration_id    uuid primary key references app.integration(id) on delete cascade,
  tenant_id         uuid not null references app.tenant(id) on delete cascade,
  status            text not null
    check (status in ('connected', 'disconnected', 'unknown')),
  --: When the watcher last asked. Moves on every call.
  checked_at        timestamptz not null default now(),
  --: When the status last CHANGED. Moves only when it does — the age of the
  --: state, which is what "disconnected for 3 hours" needs.
  status_changed_at timestamptz not null default now(),
  --: What the provider said, for the screen. Never a secret, never a body.
  detail            text
);

create index if not exists channel_health_tenant_idx
  on app.channel_health (tenant_id);

comment on table app.channel_health is
  'Saúde do canal, medida pelo vigia que PERGUNTA ao provedor (o webhook emudece '
  'justamente quando cai). Uma linha por integração. status_changed_at só avança '
  'quando o status muda — é a idade do estado, e a regra mora em '
  'app.fn_record_channel_health, não no Python. Leitura por util.has_tenant '
  '(estado do canal, não dado pessoal); escrita só service_role. O vigia nunca '
  'religa: reconectar número bloqueado transforma suspensão em banimento.';
comment on column app.channel_health.status_changed_at is
  'Só avança quando o status muda. Duas medições iguais seguidas mantêm o valor; '
  'é o que permite dizer "desconectado há 3 horas" em vez de "checado há 15 min".';

-- ---------------------------------------------------------------------------
-- 2. The upsert that carries the rule
-- ---------------------------------------------------------------------------
-- `security definer` so the watcher (service_role) writes through one door;
-- the tenant is derived from the integration, never taken from the caller.
-- An integration that does not exist raises — recording health for nothing
-- would be the silent degradation this project refuses.
create or replace function app.fn_record_channel_health(
  p_integration_id uuid,
  p_status         text,
  p_detail         text default null
)
returns void
language plpgsql security definer set search_path = ''
as $$
declare
  v_tenant uuid;
begin
  select i.tenant_id into v_tenant
    from app.integration i
   where i.id = p_integration_id;
  if v_tenant is null then
    raise exception 'app.fn_record_channel_health: integration % does not exist', p_integration_id
      using errcode = 'foreign_key_violation';
  end if;

  insert into app.channel_health
         (integration_id, tenant_id, status, checked_at, status_changed_at, detail)
  values (p_integration_id, v_tenant, p_status, now(), now(), p_detail)
  on conflict (integration_id) do update
     set status            = excluded.status,
         checked_at        = excluded.checked_at,
         detail            = excluded.detail,
         -- The rule of §7, in the only place it can be enforced for every
         -- caller: the state's age is kept unless the state changed.
         status_changed_at = case
           when app.channel_health.status is distinct from excluded.status
             then excluded.checked_at
           else app.channel_health.status_changed_at
         end;
end $$;

comment on function app.fn_record_channel_health(uuid, text, text) is
  'Grava a medição do vigia. Upsert por integration_id; tenant derivado da '
  'integração. status_changed_at só avança quando o status muda; checked_at '
  'avança sempre. Integração inexistente levanta. Só service_role executa.';

-- `trg_lock_down_new_function` already strips public/anon from functions in
-- `app`; written anyway, and `authenticated` with it: the function is definer
-- and writes, so the panel must not reach it by any path.
revoke execute on function app.fn_record_channel_health(uuid, text, text)
  from public, anon, authenticated;
grant  execute on function app.fn_record_channel_health(uuid, text, text)
  to service_role;

-- ---------------------------------------------------------------------------
-- 3. The boundary — owner item 2
-- ---------------------------------------------------------------------------
alter table app.channel_health enable row level security;

revoke all on table app.channel_health from anon, authenticated;
grant select on table app.channel_health to authenticated;
-- ⛔ `select, insert, update` and not `grant all`: a health row is never
--    deleted by anyone; it follows the integration (`on delete cascade`).
grant select, insert, update on table app.channel_health to service_role;

drop policy if exists channel_health_read on app.channel_health;
create policy channel_health_read on app.channel_health
  for select to authenticated
  using (util.has_tenant(tenant_id));

-- No write policy: `authenticated` has no insert/update grant, and the policy
-- is the second lock if a grant ever slips in.

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_privilege text;
  v_n         int;
  v_qual      text;
  v_oid       oid;
  v_secdef    boolean;
  v_config    text;
begin
  if to_regclass('app.channel_health') is null then
    raise exception 'app.channel_health does not exist after being created';
  end if;

  -- 1. Rule 3: tenant_id and RLS.
  if not exists (
    select 1 from information_schema.columns
     where table_schema = 'app' and table_name = 'channel_health' and column_name = 'tenant_id'
  ) then
    raise exception 'app.channel_health without tenant_id — rule 3 of CLAUDE.md';
  end if;
  if not (select relrowsecurity from pg_class where oid = 'app.channel_health'::regclass) then
    raise exception 'app.channel_health without RLS — rule 3 of CLAUDE.md';
  end if;

  -- 2. One row per integration: the primary key IS integration_id.
  if not exists (
    select 1 from pg_constraint
     where conrelid = 'app.channel_health'::regclass and contype = 'p'
       and pg_get_constraintdef(oid) = 'PRIMARY KEY (integration_id)'
  ) then
    raise exception 'app.channel_health is not keyed by integration_id alone';
  end if;

  -- 3. Exactly one policy, read-only, on util.has_tenant. Counting without
  --    reading the text would let a policy on `true` pass.
  select count(*) into v_n from pg_policies
   where schemaname = 'app' and tablename = 'channel_health';
  if v_n <> 1 then
    raise exception 'app.channel_health has % policy(ies), expected 1 (read)', v_n;
  end if;
  select qual into v_qual from pg_policies
   where schemaname = 'app' and tablename = 'channel_health' and policyname = 'channel_health_read';
  if v_qual is null or v_qual not like '%has_tenant%' then
    raise exception 'channel_health_read is not on util.has_tenant: %', coalesce(v_qual, '(missing)');
  end if;
  if exists (
    select 1 from pg_policies
     where schemaname = 'app' and tablename = 'channel_health' and cmd <> 'SELECT'
  ) then
    raise exception 'app.channel_health has a write policy; writing is service_role only';
  end if;

  -- 4. authenticated reads and does nothing else; anon nothing at all.
  if not has_table_privilege('authenticated', 'app.channel_health', 'SELECT') then
    raise exception 'authenticated cannot read app.channel_health — the screen would never show the channel state';
  end if;
  foreach v_privilege in array array['INSERT','UPDATE','DELETE'] loop
    if has_table_privilege('authenticated', 'app.channel_health', v_privilege) then
      raise exception 'authenticated has % on app.channel_health — writing is service_role only', v_privilege;
    end if;
  end loop;
  foreach v_privilege in array array['SELECT','INSERT','UPDATE','DELETE'] loop
    if has_table_privilege('anon', 'app.channel_health', v_privilege) then
      raise exception 'anon has % on app.channel_health', v_privilege;
    end if;
  end loop;

  -- 5. service_role writes, and does not delete.
  foreach v_privilege in array array['SELECT','INSERT','UPDATE'] loop
    if not has_table_privilege('service_role', 'app.channel_health', v_privilege) then
      raise exception 'service_role lacks % on app.channel_health — the watcher could not record', v_privilege;
    end if;
  end loop;
  foreach v_privilege in array array['DELETE','TRUNCATE'] loop
    if has_table_privilege('service_role', 'app.channel_health', v_privilege) then
      raise exception 'service_role has % on app.channel_health; health rows are never deleted', v_privilege;
    end if;
  end loop;

  -- 6. The function: definer with search_path locked, service_role only.
  select p.oid, p.prosecdef, coalesce(array_to_string(p.proconfig, ','), '')
    into v_oid, v_secdef, v_config
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'app' and p.proname = 'fn_record_channel_health';
  if v_oid is null then
    raise exception 'app.fn_record_channel_health does not exist';
  end if;
  if not v_secdef then
    raise exception 'app.fn_record_channel_health is not security definer';
  end if;
  if v_config not like '%search_path=%' then
    raise exception 'app.fn_record_channel_health is definer WITHOUT search_path locked';
  end if;
  if has_function_privilege('anon', v_oid, 'EXECUTE')
     or has_function_privilege('authenticated', v_oid, 'EXECUTE') then
    raise exception 'the panel can execute app.fn_record_channel_health — it writes as definer';
  end if;
  if not has_function_privilege('service_role', v_oid, 'EXECUTE') then
    raise exception 'service_role cannot execute app.fn_record_channel_health — the watcher could not record';
  end if;

  -- 7. The rule of §7 is in the function body: the upsert keys on the
  --    integration and keeps status_changed_at unless the status differs.
  --    The functional proof (two equal calls do not move it, a different one
  --    does) runs with real rows in `scripts/86_teste_canais_exclusividade.sql`;
  --    a migration does not seed integrations in production.
  if pg_get_functiondef(v_oid) not ilike '%on conflict (integration_id)%'
     or pg_get_functiondef(v_oid) not ilike '%is distinct from excluded.status%' then
    raise exception 'app.fn_record_channel_health lost the §7 rule (upsert by integration, status_changed_at only on change)';
  end if;

  raise notice 'OK: app.channel_health readable by the tenant, written only by service_role through fn_record_channel_health, status age kept on equal readings.';
end $$;
