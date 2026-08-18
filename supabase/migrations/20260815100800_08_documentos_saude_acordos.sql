-- ============================================================================
-- OperaX — 08. DOCUMENTS, OCCUPATIONAL EXAMS AND FINANCIAL AGREEMENTS
--              (Fases 3 e 4 da proposta — seções 8 e 9)
-- ----------------------------------------------------------------------------
-- ATENÇÃO — MODELO NÃO VALIDADO CONTRA PROCESSO REAL. Isolado nesta migration
-- para poder ser revisto sem tocar no núcleo.
--
-- ASO e exame ocupacional são DADO DE SAÚDE — dado pessoal sensível sob a LGPD
-- (art. 5º, II), com base legal e tratamento mais restritos que o resto. Por isso:
--   - tabela própria, domínio 'health', separada de document genérico;
--   - guarda apenas APTO / INAPTO / APTO COM RESTRIÇÃO e validade;
--   - NUNCA guarda diagnóstico, CID, restrição clínica ou reason;
--   - nenhuma coluna desta tabela entra em view de dashboard.
--
-- Desconto em folha exige autorização documentada. `authorized_by` e
-- `document_id` são NOT NULL de propósito: sem prova de autorização não se
-- registra acordo. A efetivação do desconto continua sendo do DP no sistema
-- oficial — o OperaX acompanha, não executa (item 20 do escopo).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Documentos
-- ---------------------------------------------------------------------------
create table if not exists app.document_type (
  id                      uuid primary key default gen_random_uuid(),
  tenant_id               uuid not null references app.tenant(id) on delete cascade,
  name                    text not null,
  requires_expiry          boolean not null default false,
  expiry_alert_days  integer not null default 30,
  required             boolean not null default false,
  domain                 app.sensitive_domain not null default 'pii',
  unique (tenant_id, name)
);

create table if not exists app.document (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references app.tenant(id) on delete cascade,
  employee_id  uuid not null references app.employee(id) on delete cascade,
  type_id         uuid not null references app.document_type(id) on delete restrict,
  storage_bucket  text not null default 'documentos',
  storage_path    text not null,
  file_name    text,
  issued_on      date,
  valid_until      date,
  status          text not null default 'active' check (status in ('active','vencido','substituido','removido')),
  replaces_id    uuid references app.document(id) on delete set null,
  created_by      uuid references auth.users(id),
  created_at       timestamptz not null default now(),
  unique (storage_bucket, storage_path)
);
create index if not exists document_colab_idx      on app.document (employee_id, type_id);
create index if not exists document_vencimento_idx on app.document (tenant_id, valid_until)
  where status = 'active' and valid_until is not null;
comment on table app.document is
  'O arquivo vive no Supabase Storage. A policy do bucket precisa espelhar util.can_see_employee — RLS de tabela não protege o objeto.';

-- ---------------------------------------------------------------------------
-- Exames ocupacionais — dado de saúde
-- ---------------------------------------------------------------------------
create table if not exists app.occupational_exam (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references app.tenant(id) on delete cascade,
  employee_id  uuid not null references app.employee(id) on delete cascade,
  type            text not null check (type in ('pre_employment','periodic','exit','return_to_work_exam','job_change')),
  performed_on    date not null,
  valid_until      date,
  result       text check (result in ('fit','unfit','fit_with_restriction')),
  document_id    uuid references app.document(id) on delete set null,
  created_by      uuid references auth.users(id),
  created_at       timestamptz not null default now()
);
create index if not exists exame_colab_idx      on app.occupational_exam (employee_id, performed_on desc);
create index if not exists exame_vencimento_idx on app.occupational_exam (tenant_id, valid_until) where valid_until is not null;
comment on table app.occupational_exam is
  'DADO DE SAÚDE (LGPD art. 5º II). Sem diagnóstico, sem CID, sem descrição de restrição. Só aptidão e validade.';

-- ---------------------------------------------------------------------------
-- Acordos financeiros com employee (seção 9)
-- ---------------------------------------------------------------------------
create table if not exists app.financial_agreement (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references app.tenant(id) on delete cascade,
  employee_id  uuid not null references app.employee(id) on delete cascade,
  type            text not null check (type in ('installment_plan','vehicle_damage','equipment_damage','advance','loan','benefit','other')),
  description       text,
  total_amount     numeric(14,2) not null check (total_amount > 0),
  installment_count    integer not null default 1 check (installment_count >= 1),
  agreement_date     date not null,
  document_id    uuid not null references app.document(id) on delete restrict,
  authorized_by  uuid not null references auth.users(id),
  authorized_at   timestamptz not null default now(),
  status          text not null default 'active' check (status in ('active','settled','cancelled','suspended')),
  created_at       timestamptz not null default now()
);
create index if not exists acordo_colab_idx on app.financial_agreement (employee_id, status);
comment on column app.financial_agreement.document_id is
  'NOT NULL de propósito: desconto sem autorização documentada não se registra.';

create table if not exists app.agreement_installment (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references app.tenant(id) on delete cascade,
  agreement_id        uuid not null references app.financial_agreement(id) on delete cascade,
  number           integer not null check (number >= 1),
  period_year  smallint not null,
  period_month  smallint not null check (period_month between 1 and 13),
  amount            numeric(14,2) not null check (amount > 0),
  status           text not null default 'pending' check (status in ('pending','processed','cancelled','renegotiated')),
  payroll_entry_id  uuid references app.payroll_entry(id) on delete set null,
  processed_at    timestamptz,
  unique (agreement_id, number)
);
create index if not exists parcela_competencia_idx on app.agreement_installment (tenant_id, period_year, period_month)
  where status = 'pending';
comment on table app.agreement_installment is
  'Parcela pendente cuja competência já passou = alerta de "parcela não processada" (item 9 da proposta).';

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['document_type','document','occupational_exam','financial_agreement','agreement_installment'] loop
    execute format('alter table app.%I enable row level security', t);
    execute format('revoke all on table app.%I from anon', t);
  end loop;
end $$;

drop policy if exists document_type_read on app.document_type;
create policy document_type_read on app.document_type
  for select to authenticated using (util.has_tenant(tenant_id));

drop policy if exists document_type_admin on app.document_type;
create policy document_type_admin on app.document_type
  for all to authenticated using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

-- Documento herda o domínio do seu type.
drop policy if exists document_read on app.document;
create policy document_read on app.document
  for select to authenticated
  using (
    util.can_see_employee(employee_id)
    and exists (
      select 1 from app.document_type dt
      where dt.id = type_id and util.can_see_domain(tenant_id, dt.domain)
    )
  );

drop policy if exists document_write on app.document;
create policy document_write on app.document
  for all to authenticated using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

-- Saúde: só quem tem o domínio 'health'. Ver a unit não basta, ser admin não basta.
drop policy if exists exame_read on app.occupational_exam;
create policy exame_read on app.occupational_exam
  for select to authenticated
  using (util.can_see_domain(tenant_id, 'health') and util.can_see_employee(employee_id));

drop policy if exists exame_write on app.occupational_exam;
create policy exame_write on app.occupational_exam
  for all to authenticated
  using (util.can_see_domain(tenant_id, 'health'))
  with check (util.can_see_domain(tenant_id, 'health'));

drop policy if exists acordo_read on app.financial_agreement;
create policy acordo_read on app.financial_agreement
  for select to authenticated
  using (util.can_see_domain(tenant_id, 'compensation') and util.can_see_employee(employee_id));

drop policy if exists acordo_write on app.financial_agreement;
create policy acordo_write on app.financial_agreement
  for all to authenticated
  using (util.can_see_domain(tenant_id, 'compensation') and util.is_admin(tenant_id))
  with check (util.can_see_domain(tenant_id, 'compensation') and util.is_admin(tenant_id));

drop policy if exists parcela_read on app.agreement_installment;
create policy parcela_read on app.agreement_installment
  for select to authenticated
  using (util.can_see_domain(tenant_id, 'compensation')
         and exists (select 1 from app.financial_agreement a
                     where a.id = agreement_id and util.can_see_employee(a.employee_id)));

drop policy if exists parcela_write on app.agreement_installment;
create policy parcela_write on app.agreement_installment
  for all to authenticated
  using (util.can_see_domain(tenant_id, 'compensation') and util.is_admin(tenant_id))
  with check (util.can_see_domain(tenant_id, 'compensation') and util.is_admin(tenant_id));

grant select on app.document_type, app.document, app.occupational_exam,
                app.financial_agreement, app.agreement_installment to authenticated;
grant insert, update, delete on app.document_type, app.document, app.occupational_exam,
                app.financial_agreement, app.agreement_installment to authenticated;
