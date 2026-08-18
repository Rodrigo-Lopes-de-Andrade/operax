-- ============================================================================
-- OperaX — 06. ALERT RULES, OUTBOX AND LOG
-- ----------------------------------------------------------------------------
-- Duas decisões de produto materializadas no schema:
--
--  (a) OUTBOX. The detection engine NEVER sends. It enqueues into alert_queue.
--      Um sender processa com retry, backoff e idempotência. Sem isso, uma
--      falha de rede no meio do lote vira alerta duplicado no WhatsApp do
--      gestor — que é a forma mais rápida de perder a confiança do cliente.
--
--  (b) CONTEÚDO INDIVIDUAL NUNCA VAI PARA GRUPO. Alerta nominal de atraso em
--      grupo de WhatsApp é exposição do employee e abre espaço para dano
--      moral. Grupo recebe agregado ("3 ocorrências na unit Centro hoje");
--      o nominal vai para o responsável direto. Isso é imposto por trigger,
--      não por disciplina de quem configura.
--
-- Evolution API (não oficial) é o provider inicial. `provider` existe desde já
-- para a migração para a Cloud API oficial não virar refatoração.
-- ============================================================================

create table if not exists app.alert_rule (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references app.tenant(id) on delete cascade,
  name              text not null,
  deviation_type       text references app.deviation_type(code),
  scope_unit_id uuid references app.unit(id) on delete cascade,  -- null = todas
  content          text not null default 'aggregate' check (content in ('individual','aggregate')),
  channel             text not null check (channel in ('whatsapp','email','both')),
  cron_window       text,           -- null = dispara na detecção
  threshold_minutes    integer,
  threshold_occurrences integer,
  muted_until     timestamptz,
  active             boolean not null default false,   -- nasce DESLIGADA. Homologar antes.
  created_at         timestamptz not null default now()
);
create index if not exists alert_rule_tenant_idx on app.alert_rule (tenant_id) where active;
comment on column app.alert_rule.active is
  'Nasce false de propósito. Regra só liga depois de homologada com o cliente e validada pelo jurídico/RH.';

create table if not exists app.alert_rule_target (
  id          uuid primary key default gen_random_uuid(),
  rule_id    uuid not null references app.alert_rule(id) on delete cascade,
  contact_id  uuid references app.contact(id) on delete cascade,
  responsibility      text check (responsibility in ('unit_manager','regional_supervisor','personnel','hr','executive','group')),
  check (contact_id is not null or responsibility is not null)
);
create index if not exists regra_destino_regra_idx on app.alert_rule_target (rule_id);

-- Guardrail: individual nunca para grupo.
create or replace function util.validate_alert_target()
returns trigger
language plpgsql security definer set search_path = ''
as $$
declare v_content text; v_tipo_contact text;
begin
  select content into v_content from app.alert_rule where id = new.rule_id;

  if new.contact_id is not null then
    select type into v_tipo_contact from app.contact where id = new.contact_id;
  end if;

  if v_content = 'individual'
     and (new.responsibility = 'group' or v_tipo_contact = 'whatsapp_group') then
    raise exception using
      errcode = 'raise_exception',
      message = 'Alerta de conteúdo individual não pode ter grupo como destinatário.',
      hint    = 'Exposição nominal de colaborador em grupo é risco trabalhista. Use content = ''aggregate'' para grupos.';
  end if;
  return new;
end $$;

drop trigger if exists trg_validate_alert_target on app.alert_rule_target;
create trigger trg_validate_alert_target
  before insert or update on app.alert_rule_target
  for each row execute function util.validate_alert_target();

-- ---------------------------------------------------------------------------
-- Outbox
-- ---------------------------------------------------------------------------
create table if not exists app.alert_queue (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid not null references app.tenant(id) on delete cascade,
  rule_id            uuid references app.alert_rule(id) on delete set null,
  deviation_event_id  uuid references app.deviation_event(id) on delete cascade,
  report_cycle_id  uuid references app.report_cycle(id) on delete cascade,
  channel               text not null check (channel in ('whatsapp','email')),
  destination             text not null,             -- número E.164 ou e-mail
  payload             jsonb not null,
  idempotency_key  text not null unique,      -- ex: regra:data:destination:hash(content)
  status              text not null default 'pending'
                        check (status in ('pending','sending','sent','failed','discarded')),
  attempts          integer not null default 0,
  next_attempt_at   timestamptz not null default now(),
  scheduled_for       timestamptz not null default now(),
  created_at           timestamptz not null default now()
);
create index if not exists alert_queue_proxima_idx on app.alert_queue (next_attempt_at)
  where status in ('pending','failed');
create index if not exists alert_queue_evento_idx on app.alert_queue (deviation_event_id);
comment on column app.alert_queue.idempotency_key is
  'Reprocessar o mesmo período não reenvia. Consuma a fila com SELECT ... FOR UPDATE SKIP LOCKED.';

create table if not exists app.alert_sent (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid not null references app.tenant(id) on delete cascade,
  queue_id             uuid references app.alert_queue(id) on delete set null,
  rule_id            uuid references app.alert_rule(id) on delete set null,
  channel               text not null,
  provider            text not null check (provider in ('evolution','whatsapp_cloud','smtp','resend')),
  destination_hash        text not null,             -- destination não é guardado em claro no log
  provider_message_id text,
  status              text not null check (status in ('sent','delivered','read','failed')),
  error                text,
  cost_cents      integer,
  sent_at          timestamptz not null default now()
);
create index if not exists alert_sent_tenant_idx on app.alert_sent (tenant_id, sent_at desc);
comment on column app.alert_sent.cost_cents is
  'Cloud API cobra por mensagem. Sem esse campo não dá para saber se a sustentação mensal está com margem negativa.';

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['alert_rule','alert_rule_target','alert_queue','alert_sent'] loop
    execute format('alter table app.%I enable row level security', t);
    execute format('revoke all on table app.%I from anon', t);
  end loop;
end $$;

drop policy if exists alert_rule_admin on app.alert_rule;
create policy alert_rule_admin on app.alert_rule
  for all to authenticated using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

drop policy if exists alert_rule_read on app.alert_rule;
create policy alert_rule_read on app.alert_rule
  for select to authenticated using (util.has_tenant(tenant_id));

drop policy if exists regra_destino_admin on app.alert_rule_target;
create policy regra_destino_admin on app.alert_rule_target
  for all to authenticated
  using (exists (select 1 from app.alert_rule r where r.id = rule_id and util.is_admin(r.tenant_id)))
  with check (exists (select 1 from app.alert_rule r where r.id = rule_id and util.is_admin(r.tenant_id)));

-- Fila é do worker. Ninguém no painel lê destination em claro.
drop policy if exists alert_queue_admin on app.alert_queue;
create policy alert_queue_admin on app.alert_queue
  for select to authenticated using (util.is_admin(tenant_id));

drop policy if exists alert_sent_read on app.alert_sent;
create policy alert_sent_read on app.alert_sent
  for select to authenticated using (util.is_admin(tenant_id));

grant select on app.alert_rule, app.alert_rule_target, app.alert_queue, app.alert_sent to authenticated;
grant insert, update, delete on app.alert_rule, app.alert_rule_target to authenticated;
