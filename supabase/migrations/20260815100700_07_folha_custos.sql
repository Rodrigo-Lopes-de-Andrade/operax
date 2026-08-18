-- ============================================================================
-- OperaX — 07. PAYROLL, CHARGES AND LABOR COST  (Fase 3 da proposta)
-- ----------------------------------------------------------------------------
-- ATENÇÃO — MODELO NÃO VALIDADO CONTRA DADO REAL.
-- Integração com Domínio depende do escritório contábil e da Thomson Reuters;
-- API pode simplesmente não ser liberada. Este modelo é FILE-FIRST de propósito:
-- `source` aceita planilha e arquivo desde o começo, e a API é só mais uma
-- source. Se o Domínio abrir, nada muda de estrutura. Se não abrir, o produto
-- funciona igual com importação — e generaliza para clientes que não usam Domínio.
--
-- Revisar este arquivo inteiro quando o primeiro layout real chegar.
-- Ele está isolado nesta migration justamente para poder ser reescrito sem
-- tocar no núcleo (tenancy, employee, desvio).
--
-- Tudo aqui é domínio 'compensation'. Nenhuma coluna de amount entra em view de
-- dashboard operacional.
-- ============================================================================

create table if not exists app.payroll_period (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references app.tenant(id) on delete cascade,
  year         smallint not null check (year between 2000 and 2100),
  month         smallint not null check (month between 1 and 13),  -- 13 = décimo terceiro
  status      text not null default 'aberta' check (status in ('aberta','importada','conferida','fechada')),
  closed_at  timestamptz,
  unique (tenant_id, year, month)
);

create table if not exists app.cost_center (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references app.tenant(id) on delete cascade,
  company_id  uuid references app.company(id) on delete cascade,
  unit_id  uuid references app.unit(id) on delete set null,
  code      text not null,
  name        text not null,
  unique (tenant_id, code)
);
create index if not exists cost_center_unidade_idx on app.cost_center (unit_id);

-- Grão: um evento de folha por employee/competência/código.
create table if not exists app.payroll_entry (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references app.tenant(id) on delete cascade,
  payroll_period_id  uuid not null references app.payroll_period(id) on delete cascade,
  employee_id  uuid references app.employee(id) on delete set null,
  company_id      uuid not null references app.company(id),
  unit_id      uuid references app.unit(id),
  cost_center_id uuid references app.cost_center(id),
  code          text not null,
  description       text,
  nature        text not null check (nature in ('earning','deduction','base','payroll_charge','informational')),
  reference      numeric(14,4),
  amount           numeric(14,2) not null,
  source          text not null check (source in ('domain_api','spreadsheet','file','manual')),
  import_id   uuid,          -- FK adicionada na migration 09
  created_at       timestamptz not null default now()
);
create index if not exists payroll_entry_comp_idx    on app.payroll_entry (payroll_period_id, company_id);
create index if not exists payroll_entry_colab_idx   on app.payroll_entry (employee_id, payroll_period_id);
create index if not exists payroll_entry_unidade_idx on app.payroll_entry (unit_id, payroll_period_id);
create index if not exists payroll_entry_cc_idx      on app.payroll_entry (cost_center_id);
create index if not exists payroll_entry_import_idx  on app.payroll_entry (import_id);
comment on table app.payroll_entry is
  'Espelho do que a folha oficial calculou. O OperaX NÃO calcula obrigação trabalhista — item 20 do escopo.';

create table if not exists app.payroll_charge (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references app.tenant(id) on delete cascade,
  payroll_period_id  uuid not null references app.payroll_period(id) on delete cascade,
  company_id      uuid not null references app.company(id),
  unit_id      uuid references app.unit(id),
  type            text not null check (type in ('fgts','inss_employer','inss_withheld','irrf','rat','third_parties','vacation_accrual','thirteenth_accrual','other')),
  calculation_base    numeric(14,2),
  amount           numeric(14,2) not null,
  source          text not null check (source in ('domain_api','spreadsheet','file','manual')),
  created_at       timestamptz not null default now()
);
create index if not exists payroll_charge_comp_idx on app.payroll_charge (payroll_period_id, company_id);

create table if not exists app.workforce_movement (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references app.tenant(id) on delete cascade,
  employee_id  uuid not null references app.employee(id) on delete cascade,
  company_id      uuid not null references app.company(id),
  unit_id      uuid references app.unit(id),
  type            text not null check (type in ('hire','termination','transfer','promotion','leave_period','return_to_work')),
  event_date     date not null,
  payroll_period_id  uuid references app.payroll_period(id),
  estimated_cost  numeric(14,2),
  notes      text,
  created_at       timestamptz not null default now()
);
create index if not exists movimentacao_data_idx on app.workforce_movement (tenant_id, event_date desc);
create index if not exists movimentacao_colab_idx on app.workforce_movement (employee_id);

-- Limiares dos alertas financeiros (item 5.4 da proposta)
create table if not exists app.financial_threshold (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references app.tenant(id) on delete cascade,
  company_id    uuid references app.company(id) on delete cascade,
  unit_id    uuid references app.unit(id) on delete cascade,
  indicator     text not null check (indicator in ('total_payroll','unit_cost','cost_per_employee','overtime','payroll_charge','terminations')),
  operator      text not null check (operator in ('greater_than','less_than','percent_change')),
  amount         numeric(14,2) not null,
  active         boolean not null default true
);
create index if not exists financial_threshold_tenant_idx on app.financial_threshold (tenant_id) where active;

-- ---------------------------------------------------------------------------
-- RLS — tudo exige domínio 'compensation'
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['payroll_period','cost_center','payroll_entry','payroll_charge','workforce_movement','financial_threshold'] loop
    execute format('alter table app.%I enable row level security', t);
    execute format('revoke all on table app.%I from anon', t);
  end loop;
end $$;

drop policy if exists payroll_period_read on app.payroll_period;
create policy payroll_period_read on app.payroll_period
  for select to authenticated using (util.can_see_domain(tenant_id, 'compensation'));

drop policy if exists cost_center_read on app.cost_center;
create policy cost_center_read on app.cost_center
  for select to authenticated using (util.has_tenant(tenant_id));

drop policy if exists payroll_entry_read on app.payroll_entry;
create policy payroll_entry_read on app.payroll_entry
  for select to authenticated
  using (
    util.can_see_domain(tenant_id, 'compensation')
    and (util.is_admin(tenant_id)
         or (unit_id is not null and util.can_see_unit(unit_id))
         or (unit_id is null     and util.can_see_company(company_id)))
  );

drop policy if exists payroll_charge_read on app.payroll_charge;
create policy payroll_charge_read on app.payroll_charge
  for select to authenticated
  using (util.can_see_domain(tenant_id, 'compensation') and util.can_see_company(company_id));

drop policy if exists movimentacao_read on app.workforce_movement;
create policy movimentacao_read on app.workforce_movement
  for select to authenticated
  using (util.is_admin(tenant_id)
         or (unit_id is not null and util.can_see_unit(unit_id)));

drop policy if exists limiar_admin on app.financial_threshold;
create policy limiar_admin on app.financial_threshold
  for all to authenticated
  using (util.can_see_domain(tenant_id, 'compensation') and util.is_admin(tenant_id))
  with check (util.can_see_domain(tenant_id, 'compensation') and util.is_admin(tenant_id));

grant select on app.payroll_period, app.cost_center, app.payroll_entry, app.payroll_charge,
                app.workforce_movement, app.financial_threshold to authenticated;
grant insert, update, delete on app.financial_threshold, app.cost_center to authenticated;
