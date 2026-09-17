-- ============================================================================
-- OperaX — assistant_metric_scope. THE TENANT'S EXCEPTIONS TO THE CATALOGUE
-- ----------------------------------------------------------------------------
-- Design in `docs/SPEC-AGENTE.md` §3b (this DDL) and §4 (capabilities =
-- metrics). Owner decisions of 17/09/2026 (`docs/SPRINTS-AGENTE.md`, "Parada
-- da A2"): read by `util.has_tenant` — the runtime reads the catalogue AS THE
-- USER, so every member has to see the scope of their own tenant; insert and
-- update by `util.is_admin`; and NO delete for any role — re-enabling is
-- `enabled = true`, the row stays.
--
-- ABSENCE = ENABLED. THE TABLE HOLDS ONLY EXCEPTIONS.
-- The reason is not row economy: if absence meant disabled, a metric newly
-- seeded by EURECA would be born invisible to every existing customer, and the
-- symptom would be "the assistant stopped answering about X" with nothing in
-- the logs. The silent failure is the criterion (SPEC §3b).
--
-- THE INVARIANT THIS TABLE MUST NEVER BREAK (SPEC §4.1)
-- Enabling a metric grants no access to data. The executor runs the view as
-- the user and RLS decides what comes back; this table only NARROWS the
-- catalogue the model sees. `public.fn_assistant_catalog` (next migration)
-- is the single ruler that applies it — after `app.metric.active` and before
-- `util.can_see_domain`, never the other way round (§4.2).
--
-- EXACTLY THREE POLICIES, BY NAME, AND NO `for all`
-- `for all` would cover delete, and the stop said no delete. The proof below
-- compares the set by name and by `cmd`.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

create table if not exists app.assistant_metric_scope (
  tenant_id   uuid not null references app.tenant(id) on delete cascade,
  metric_code text not null references app.metric(code) on delete cascade,
  enabled     boolean not null,
  updated_at  timestamptz not null default now(),
  updated_by  uuid references auth.users(id),
  primary key (tenant_id, metric_code)
);

-- The house helper (migration 11): `updated_at` moves on every update, so a
-- re-enable that only touches `enabled` cannot leave a stale date.
drop trigger if exists trg_updated_at on app.assistant_metric_scope;
create trigger trg_updated_at
  before update on app.assistant_metric_scope
  for each row execute function util.touch_updated_at();

-- ---------------------------------------------------------------------------
-- Comments — the data dictionary is generated from these
-- ---------------------------------------------------------------------------
comment on table app.assistant_metric_scope is
  'Exceções do tenant ao catálogo do assistente: uma linha por métrica que o '
  'cliente desligou (ou religou). Ausência = habilitada, de propósito: se '
  'ausência fosse "desabilitada", uma métrica nova semeada pela EURECA nasceria '
  'invisível para todo cliente existente, e o sintoma seria "o assistente parou '
  'de responder sobre X" sem nada nos logs — a falha silenciosa é o critério. '
  'Só estreita: habilitar nunca concede domínio que o papel não tem (SPEC '
  'AGENTE §4.1). Leitura por todo membro do tenant (o runtime lê como o '
  'usuário); insert e update pelo admin (owner, hr, personnel); ninguém apaga '
  '— reabilitar é enabled = true.';
comment on column app.assistant_metric_scope.tenant_id is
  'O tenant dono da exceção. Cascade: some com o tenant.';
comment on column app.assistant_metric_scope.metric_code is
  'A métrica de app.metric. Cascade: some com a métrica.';
comment on column app.assistant_metric_scope.enabled is
  'false = o tenant desligou a métrica; true = religou (a linha fica). Sem '
  'linha = habilitada.';
comment on column app.assistant_metric_scope.updated_at is
  'Mantido por trigger (util.touch_updated_at) a cada update.';
comment on column app.assistant_metric_scope.updated_by is
  'Quem ligou ou desligou por último. Nulo quando veio por migration ou pelo '
  'backend.';

-- ---------------------------------------------------------------------------
-- The boundary — RLS and grants (the stop opened by the owner, 17/09/2026)
-- ---------------------------------------------------------------------------
alter table app.assistant_metric_scope enable row level security;

revoke all on table app.assistant_metric_scope from public, anon, authenticated, service_role;

-- No delete and no truncate for anyone: re-enabling is `enabled = true`.
grant select, insert, update on table app.assistant_metric_scope to authenticated;
grant select, insert, update on table app.assistant_metric_scope to service_role;

-- read: every member of the tenant. The catalogue RPC is `security invoker`
-- and runs as the person asking; a supervisor who could not read the scope
-- would get a catalogue that ignores what the tenant disabled.
drop policy if exists assistant_scope_read on app.assistant_metric_scope;
create policy assistant_scope_read on app.assistant_metric_scope
  for select to authenticated
  using (util.has_tenant(tenant_id));

-- insert / update: the tenant admin. Two policies, not `for all`, because
-- `for all` covers delete and the stop said no delete.
drop policy if exists assistant_scope_insert on app.assistant_metric_scope;
create policy assistant_scope_insert on app.assistant_metric_scope
  for insert to authenticated
  with check (util.is_admin(tenant_id));

drop policy if exists assistant_scope_update on app.assistant_metric_scope;
create policy assistant_scope_update on app.assistant_metric_scope
  for update to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_privilege text;
  v_role      text;
  v_policies  text[];
  v_tgtype    smallint;
  v_n         int;
begin
  if to_regclass('app.assistant_metric_scope') is null then
    raise exception 'app.assistant_metric_scope does not exist after being created';
  end if;

  -- 1. Rule 3: tenant_id and RLS.
  if not exists (
    select 1 from information_schema.columns
     where table_schema = 'app' and table_name = 'assistant_metric_scope' and column_name = 'tenant_id'
  ) then
    raise exception 'app.assistant_metric_scope without tenant_id — rule 3 of CLAUDE.md';
  end if;
  if not (select relrowsecurity from pg_class where oid = 'app.assistant_metric_scope'::regclass) then
    raise exception 'app.assistant_metric_scope without RLS — rule 3 of CLAUDE.md';
  end if;

  -- 2. Nobody deletes or truncates; anon has nothing at all.
  foreach v_role in array array['anon', 'authenticated', 'service_role'] loop
    foreach v_privilege in array array['DELETE', 'TRUNCATE'] loop
      if has_table_privilege(v_role, 'app.assistant_metric_scope', v_privilege) then
        raise exception '% has % on app.assistant_metric_scope — re-enabling is enabled = true, never a delete', v_role, v_privilege;
      end if;
    end loop;
  end loop;
  foreach v_privilege in array array['SELECT', 'INSERT', 'UPDATE', 'DELETE'] loop
    if has_table_privilege('anon', 'app.assistant_metric_scope', v_privilege) then
      raise exception 'anon has % on app.assistant_metric_scope', v_privilege;
    end if;
  end loop;

  -- 3. authenticated and service_role: select, insert, update.
  foreach v_role in array array['authenticated', 'service_role'] loop
    foreach v_privilege in array array['SELECT', 'INSERT', 'UPDATE'] loop
      if not has_table_privilege(v_role, 'app.assistant_metric_scope', v_privilege) then
        raise exception '% lacks % on app.assistant_metric_scope', v_role, v_privilege;
      end if;
    end loop;
  end loop;

  -- 4. Exactly the three policies, by name and by cmd — the set the stop was
  --    opened for. `has_tenant` on the read, `is_admin` on both writes.
  select array_agg(policyname::text order by policyname) into v_policies
    from pg_policies
   where schemaname = 'app' and tablename = 'assistant_metric_scope';
  if v_policies is distinct from array['assistant_scope_insert', 'assistant_scope_read', 'assistant_scope_update'] then
    raise exception 'app.assistant_metric_scope carries policies % — expected exactly assistant_scope_insert, assistant_scope_read, assistant_scope_update', v_policies;
  end if;
  if not exists (
    select 1 from pg_policies
     where schemaname = 'app' and tablename = 'assistant_metric_scope'
       and policyname = 'assistant_scope_read' and cmd = 'SELECT'
       and qual like '%has_tenant%' and qual not like '%is_admin%'
  ) then
    raise exception 'assistant_scope_read is not "select by util.has_tenant" — the runtime reads as the user, every member must see the scope';
  end if;
  if not exists (
    select 1 from pg_policies
     where schemaname = 'app' and tablename = 'assistant_metric_scope'
       and policyname = 'assistant_scope_insert' and cmd = 'INSERT'
       and with_check like '%is_admin%'
  ) then
    raise exception 'assistant_scope_insert is not "insert with check util.is_admin"';
  end if;
  if not exists (
    select 1 from pg_policies
     where schemaname = 'app' and tablename = 'assistant_metric_scope'
       and policyname = 'assistant_scope_update' and cmd = 'UPDATE'
       and qual like '%is_admin%' and with_check like '%is_admin%'
  ) then
    raise exception 'assistant_scope_update is not "update using and with check util.is_admin"';
  end if;
  if exists (
    select 1 from pg_policies
     where schemaname = 'app' and tablename = 'assistant_metric_scope' and cmd in ('ALL', 'DELETE')
  ) then
    raise exception 'app.assistant_metric_scope has a policy covering delete (for all / for delete) — the stop said no delete';
  end if;

  -- 5. Both FKs cascade: the row follows the tenant and the metric.
  select count(*) into v_n
    from pg_constraint c
   where c.conrelid = 'app.assistant_metric_scope'::regclass
     and c.contype = 'f' and c.confdeltype = 'c'
     and c.confrelid in ('app.tenant'::regclass, 'app.metric'::regclass);
  if v_n <> 2 then
    raise exception 'app.assistant_metric_scope: expected 2 FKs with on delete cascade (tenant, metric), found %', v_n;
  end if;

  -- 6. trg_updated_at: before update, row level, enabled, on the house helper.
  select t.tgtype into v_tgtype
    from pg_trigger t
   where t.tgrelid = 'app.assistant_metric_scope'::regclass
     and t.tgname = 'trg_updated_at' and not t.tgisinternal and t.tgenabled = 'O'
     and t.tgfoid = 'util.touch_updated_at'::regproc;
  if v_tgtype is null then
    raise exception 'trg_updated_at on app.assistant_metric_scope is missing, disabled, or not on util.touch_updated_at';
  end if;
  -- tgtype bits: 1 = row, 2 = before, 16 = update.
  if (v_tgtype & 1) = 0 or (v_tgtype & 2) = 0 or (v_tgtype & 16) = 0 then
    raise exception 'trg_updated_at on app.assistant_metric_scope is not BEFORE UPDATE FOR EACH ROW (tgtype=%)', v_tgtype;
  end if;

  raise notice 'OK: app.assistant_metric_scope — RLS on, three policies (read has_tenant, insert/update is_admin), nobody deletes, anon out, both FKs cascade, trg_updated_at on.';
end $$;
