-- ============================================================================
-- OperaX — 05. EXPECTED WORKDAY, DEVIATION ENGINE AND REPORT CYCLE
-- ----------------------------------------------------------------------------
-- A API do Secullum entrega BATIDA BRUTA. Isso significa que o OperaX é um
-- motor de apuração, não uma camada de leitura. Três consequências desenhadas
-- aqui dentro:
--
--  (a) 12x36. Estacionamento opera em plantão e revezamento. "Batida em dia de
--      folga = desvio automático" gera falso positivo em massa se a escala
--      esperada não estiver materializada. Daí app.expected_workday, com `source` e
--      `confidence` — sem isso não há como medir a qualidade da inferência.
--
--  (b) Modo sombra. detection_run.mode = 'shadow' roda o motor sem publicar.
--      As views do dashboard só leem mode='production'. Rodar em sombra por 1-2
--      semanas contra a apuração do Secullum ANTES de enviar qualquer alerta.
--
--  (c) Edição retroativa. Alguém justifica ou corrige uma batida depois do
--      relatório enviado. Insert-only faria dashboard e relatório divergirem
--      exatamente no caso que mais destrói confiança. Daí status + supersede_id.
--
-- VOCABULÁRIO: no banco e na UI é sempre DESVIO / INDÍCIO. Nunca "hora extra"
-- como figura legal — o registro oficial é o Secullum, e divergência entre o
-- número do OperaX e o dele, se um gestor agir em cima, é exposição do fornecedor.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Catálogo de tipos + configuração por tenant
-- A decisão pendente do Owner ("conta só hora extra ou também atraso/falta?")
-- vira UPDATE nesta tabela, não migration.
-- ---------------------------------------------------------------------------
create table if not exists app.deviation_type (
  code     text primary key,
  description  text not null,
  direction    text not null check (direction in ('surplus','shortfall','neutral')),
  category  text not null check (category in ('entry','exit','break','integrity','roster','perimeter'))
);

insert into app.deviation_type (code, description, direction, category) values
  ('late_entry',     'Entrada após o previsto além da tolerância',   'shortfall',  'entry'),
  ('early_entry',    'Entrada antes do previsto além da tolerância', 'surplus', 'entry'),
  ('early_exit',     'Saída antes do previsto além da tolerância',   'shortfall',  'exit'),
  ('late_exit',     'Saída após o previsto além da tolerância',     'surplus', 'exit'),
  ('break_exceeded',   'Intervalo acima do previsto',                  'shortfall',  'break'),
  ('break_too_short','Intervalo abaixo do mínimo previsto',         'surplus', 'break'),
  ('break_no_return','Não registrou retorno do intervalo',           'neutral',    'break'),
  ('incomplete_punches',  'Par de marcações incompleto no dia',           'neutral',    'integrity'),
  ('no_punches',         'Dia de trabalho sem nenhuma marcação',         'shortfall',  'integrity'),
  ('punch_on_day_off',      'Marcação em dia sem jornada prevista',         'surplus', 'roster'),
  ('workday_exceeded',     'Jornada acima do limite configurado',          'surplus', 'roster'),
  ('outside_perimeter',       'Marcação fora do local autorizado',            'neutral',    'perimeter')
on conflict (code) do nothing;

create table if not exists app.deviation_type_config (
  tenant_id          uuid not null references app.tenant(id) on delete cascade,
  code             text not null references app.deviation_type(code),
  active              boolean not null default true,
  counts_as_deviation  boolean not null default true,  -- entra nos KPIs e rankings
  triggers_alert        boolean not null default false,
  tolerance_extra_minutes  integer,   -- sobrepõe a tolerância do Horario do Secullum
  tolerance_absence_minutes  integer,
  primary key (tenant_id, code)
);
comment on table app.deviation_type_config is
  'Onde a decisão "direção do desvio contabilizada" vive. Cliente diferente, política diferente, mesmo schema.';

insert into app.deviation_type_config (tenant_id, code, active, counts_as_deviation, triggers_alert)
select t.id, dt.code, true, true, false
from app.tenant t cross join app.deviation_type dt
where t.slug = 'kastro-park'
on conflict (tenant_id, code) do nothing;

-- ---------------------------------------------------------------------------
-- Jornada esperada por dia — materializada, não inferida em tempo de consulta
-- ---------------------------------------------------------------------------
create table if not exists app.expected_workday (
  tenant_id             uuid not null references app.tenant(id) on delete cascade,
  employee_id        uuid not null references app.employee(id) on delete cascade,
  reference_date              date not null,
  day_type              text not null check (day_type in ('work','day_off','vacation','leave_period','holiday','compensated')),
  expected_entry      time,
  expected_exit        time,
  expected_break_minutes integer,
  workload_minutes    integer,
  tolerance_extra_minutes  integer not null default 0,
  tolerance_absence_minutes  integer not null default 0,
  secullum_schedule_id   bigint,
  source                text not null check (source in ('secullum_schedule','manual_roster','inferred')),
  confidence             smallint not null default 100 check (confidence between 0 and 100),
  primary key (employee_id, reference_date)
);
create index if not exists expected_workday_tenant_data_idx on app.expected_workday (tenant_id, reference_date);
create index if not exists expected_workday_baixa_confianca_idx on app.expected_workday (tenant_id, reference_date) where confidence < 80;
comment on column app.expected_workday.confidence is
  'Escala 12x36 inferida a partir do Horario do Secullum costuma ficar abaixo de 100. Linha com confidence baixa NÃO deve gerar alerta automático.';

-- ---------------------------------------------------------------------------
-- Execução do motor — sombra x produção
-- ---------------------------------------------------------------------------
create table if not exists app.detection_run (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid not null references app.tenant(id) on delete cascade,
  mode                text not null check (mode in ('shadow','production')),
  period_start      date not null,
  period_end         date not null,
  started_at         timestamptz not null default now(),
  finished_at        timestamptz,
  status              text not null default 'running' check (status in ('running','completed','failed')),
  events_detected  integer not null default 0,
  events_published  integer not null default 0,
  engine_version        text,
  error                text
);
create index if not exists detection_run_tenant_idx on app.detection_run (tenant_id, started_at desc);

-- ---------------------------------------------------------------------------
-- Ciclo de relatório
-- ---------------------------------------------------------------------------
create table if not exists app.report_cycle (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references app.tenant(id) on delete cascade,
  unit_id      uuid references app.unit(id) on delete cascade,
  period_start  date not null,
  period_end     date not null,
  generated_at       timestamptz not null default now(),
  sent_at      timestamptz,
  channel           text check (channel in ('whatsapp','email','both')),
  status          text not null default 'open' check (status in ('open','sent','failed','cancelled')),
  total_events   integer not null default 0,
  check (period_end >= period_start)
);
create index if not exists report_cycle_unidade_idx on app.report_cycle (unit_id, period_start desc);

-- ---------------------------------------------------------------------------
-- deviation_event — fonte única de verdade
-- Grão: uma linha por (employee, reference_date, type). Dashboard e relatório
-- leem daqui e só daqui. É o que sustenta a garantia de que os números batem.
-- ---------------------------------------------------------------------------
create table if not exists app.deviation_event (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid not null references app.tenant(id) on delete cascade,
  employee_id      uuid not null references app.employee(id) on delete cascade,

  -- Denormalizado NO MOMENTO DO FATO. Se o employee trocar de unit depois,
  -- o histórico não pode se reescrever retroativamente.
  company_id          uuid not null references app.company(id),
  unit_id          uuid references app.unit(id),

  reference_date            date not null,      -- data do FATO; é por ela que o dashboard filtra
  type                text not null references app.deviation_type(code),
  minutes             integer not null default 0,  -- ASSINADO: + excedente, - faltante
  expected_time    time,
  actual_time   time,
  punch_ids          bigint[] not null default '{}',

  status              text not null default 'active'
                        check (status in ('active','revoked','justified','ignored')),
  supersede_id        uuid references app.deviation_event(id) on delete set null,
  status_reason       text,

  mode                text not null default 'production' check (mode in ('shadow','production')),
  run_id         uuid references app.detection_run(id) on delete set null,
  report_cycle_id  uuid references app.report_cycle(id) on delete set null,

  detected_at        timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

-- Regra 5 (cada desvio em exatamente um ciclo) começa aqui: no máximo um evento
-- active por employee/dia/type em produção. Reprocessar não duplica.
create unique index if not exists deviation_event_unico_active
  on app.deviation_event (employee_id, reference_date, type)
  where status = 'active' and mode = 'production';

create index if not exists deviation_event_dash_idx
  on app.deviation_event (tenant_id, reference_date, unit_id)
  where status = 'active' and mode = 'production';
create index if not exists deviation_event_colab_idx
  on app.deviation_event (employee_id, reference_date desc)
  where status = 'active' and mode = 'production';
create index if not exists deviation_event_ciclo_idx  on app.deviation_event (report_cycle_id) where report_cycle_id is not null;
create index if not exists deviation_event_pendente_idx on app.deviation_event (tenant_id, unit_id)
  where report_cycle_id is null and status = 'active' and mode = 'production';
create index if not exists deviation_event_execucao_idx on app.deviation_event (run_id);
create index if not exists deviation_event_supersede_idx on app.deviation_event (supersede_id);

comment on column app.deviation_event.reference_date is
  'Data do fato. Dashboard SEMPRE filtra por ela. Relatório agrupa por ciclo — quando um desvio é detectado tarde, o relatório declara "inclui N ocorrências de dias anteriores".';
comment on column app.deviation_event.minutes is
  'Assinado. Soma direta responde "minutos líquidos"; abs() responde "minutos de desvio". Nunca chamar de hora extra.';

-- Never delete: revoke.
create or replace function app.revoke_deviation(p_id uuid, p_reason text, p_novo_status text default 'revoked')
returns void
language plpgsql security invoker set search_path = ''
as $$
begin
  if p_novo_status not in ('revoked','justified','ignored') then
    raise exception 'status inválido: %', p_novo_status;
  end if;
  update app.deviation_event
     set status = p_novo_status, status_reason = p_reason, updated_at = now()
   where id = p_id and status = 'active';
end $$;

-- ---------------------------------------------------------------------------
-- Justificativas
-- ---------------------------------------------------------------------------
create table if not exists app.justification (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid not null references app.tenant(id) on delete cascade,
  deviation_event_id  uuid references app.deviation_event(id) on delete cascade,
  employee_id      uuid not null references app.employee(id) on delete cascade,
  reference_date            date not null,
  text               text not null,
  source              text not null default 'operax' check (source in ('secullum','operax','whatsapp')),
  author_user_id       uuid references auth.users(id),
  author_name          text,
  created_at           timestamptz not null default now()
);
create index if not exists justification_evento_idx on app.justification (deviation_event_id);
create index if not exists justification_colab_idx  on app.justification (employee_id, reference_date desc);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array[
    'deviation_type','deviation_type_config','expected_workday','detection_run',
    'report_cycle','deviation_event','justification'
  ] loop
    execute format('alter table app.%I enable row level security', t);
    execute format('revoke all on table app.%I from anon', t);
  end loop;
end $$;

drop policy if exists deviation_type_read on app.deviation_type;
create policy deviation_type_read on app.deviation_type
  for select to authenticated using (true);   -- catálogo global, sem dado de cliente

drop policy if exists desvio_config_read on app.deviation_type_config;
create policy desvio_config_read on app.deviation_type_config
  for select to authenticated using (util.has_tenant(tenant_id));

drop policy if exists desvio_config_admin on app.deviation_type_config;
create policy desvio_config_admin on app.deviation_type_config
  for all to authenticated using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

drop policy if exists expected_workday_read on app.expected_workday;
create policy expected_workday_read on app.expected_workday
  for select to authenticated using (util.can_see_employee(employee_id));

drop policy if exists detection_run_read on app.detection_run;
create policy detection_run_read on app.detection_run
  for select to authenticated using (util.is_admin(tenant_id));

drop policy if exists ciclo_read on app.report_cycle;
create policy ciclo_read on app.report_cycle
  for select to authenticated
  using (unit_id is null and util.is_admin(tenant_id) or util.can_see_unit(unit_id));

-- Sombra só para admin: número não homologado não circula.
drop policy if exists deviation_read on app.deviation_event;
create policy deviation_read on app.deviation_event
  for select to authenticated
  using (
    (mode = 'production' or util.is_admin(tenant_id))
    and (
      util.is_admin(tenant_id)
      or (unit_id is not null and util.can_see_unit(unit_id))
      or (unit_id is null     and util.can_see_company(company_id))
    )
  );

drop policy if exists deviation_write on app.deviation_event;
create policy deviation_write on app.deviation_event
  for update to authenticated
  using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

drop policy if exists justification_read on app.justification;
create policy justification_read on app.justification
  for select to authenticated using (util.can_see_employee(employee_id));

drop policy if exists justification_write on app.justification;
create policy justification_write on app.justification
  for insert to authenticated with check (util.can_see_employee(employee_id));

grant select on app.deviation_type, app.deviation_type_config, app.expected_workday,
                app.detection_run, app.report_cycle, app.deviation_event,
                app.justification to authenticated;
grant update on app.deviation_event to authenticated;
grant insert on app.justification to authenticated;
grant insert, update, delete on app.deviation_type_config to authenticated;
grant execute on function app.revoke_deviation(uuid, text, text) to authenticated, service_role;
