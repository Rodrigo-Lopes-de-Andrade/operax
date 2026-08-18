-- ============================================================================
-- OperaX — 04. CURATED ORG DIMENSION AND EMPLOYEE
-- ----------------------------------------------------------------------------
-- Por que uma dimensão PRÓPRIA em vez de usar Departamento do Secullum direto:
-- na Kastro Park ~26% dos funcionários têm department e company divergentes.
-- Isso significa que Empresa -> Departamento NÃO é uma árvore. Herdar essa
-- ambiguidade quebra o filtro do dashboard e faz o relatório de um gestor
-- incluir gente de outro CNPJ. `app.unit_secullum_map` é onde a bagunça do
-- sistema de source é resolvida uma vez, com curadoria validada pelo cliente.
--
-- Todo cliente futuro do OperaX terá alguma variação desse problema — a camada
-- de mapeamento é feature de produto, não gambiarra deste cliente.
--
-- PII: separada em tabela própria (app.employee_pii). "Quem vê RG" vira uma
-- decisão de policy sobre UMA tabela, não column-level security espalhada.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Empresa (CNPJ)
-- ---------------------------------------------------------------------------
create table if not exists app.company (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references app.tenant(id) on delete cascade,
  cnpj                  text check (cnpj ~ '^\d{14}$'),
  legal_name          text not null,
  trade_name         text,
  secullum_company_id   bigint,
  active                 boolean not null default true,
  created_at             timestamptz not null default now(),
  unique (tenant_id, cnpj),
  unique (tenant_id, secullum_company_id)
);
create index if not exists company_tenant_idx on app.company (tenant_id) where active;

-- ---------------------------------------------------------------------------
-- Unidade = estacionamento físico. Nossa dimensão, não a do Secullum.
-- ---------------------------------------------------------------------------
create table if not exists app.unit (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references app.tenant(id) on delete cascade,
  company_id    uuid not null references app.company(id) on delete restrict,
  code        text not null,
  name          text not null,
  address      text,
  timezone      text not null default 'America/Sao_Paulo',
  active         boolean not null default true,
  created_at     timestamptz not null default now(),
  unique (tenant_id, code)
);
create index if not exists unit_tenant_empresa_idx on app.unit (tenant_id, company_id) where active;

-- Mapeamento curado: Departamento do Secullum -> unit real.
-- N:1 — vários departamentos podem cair na mesma unit.
create table if not exists app.unit_secullum_map (
  tenant_id                 uuid not null references app.tenant(id) on delete cascade,
  secullum_department_id  bigint not null,
  unit_id                uuid not null references app.unit(id) on delete cascade,
  validated_by              uuid references auth.users(id),
  validated_at               timestamptz,
  notes                text,
  primary key (tenant_id, secullum_department_id)
);
create index if not exists unit_mapa_unidade_idx on app.unit_secullum_map (unit_id);
comment on table app.unit_secullum_map is
  'Resolve a divergência Empresa x Departamento do Secullum. Linha sem validated_at = mapeamento provisório, sinalizar na UI.';

create table if not exists app.department (
  id                        uuid primary key default gen_random_uuid(),
  tenant_id                 uuid not null references app.tenant(id) on delete cascade,
  company_id                uuid not null references app.company(id) on delete cascade,
  name                      text not null,
  secullum_department_id  bigint,
  active                     boolean not null default true,
  unique (tenant_id, secullum_department_id)
);
create index if not exists department_empresa_idx on app.department (company_id);

-- ---------------------------------------------------------------------------
-- Colaborador — SEM PII
-- ---------------------------------------------------------------------------
create table if not exists app.employee (
  id                       uuid primary key default gen_random_uuid(),
  tenant_id                uuid not null references app.tenant(id) on delete cascade,
  company_id               uuid not null references app.company(id) on delete restrict,
  unit_id               uuid references app.unit(id) on delete set null,
  department_id          uuid references app.department(id) on delete set null,
  secullum_employee_id  bigint,
  registration_number                text,
  name                     text not null,
  cargo                    text,
  employment_type         text check (employment_type in ('clt','pj','internship','temporary','apprentice','contractor')),
  hired_on            date,
  terminated_on            date,
  manager_employee_id    uuid references app.employee(id) on delete set null,
  status                   text not null default 'active' check (status in ('active','afastado','vacation','desligado')),
  created_at                timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  unique (tenant_id, secullum_employee_id),
  check (terminated_on is null or hired_on is null or terminated_on >= hired_on)
);
create index if not exists employee_tenant_unidade_idx on app.employee (tenant_id, unit_id) where status <> 'desligado';
create index if not exists employee_empresa_idx        on app.employee (company_id);
create index if not exists employee_gestor_idx         on app.employee (manager_employee_id);
create index if not exists employee_departamento_idx   on app.employee (department_id);
comment on column app.employee.company_id is
  'Sempre pelo caminho Funcionario->Empresa. NUNCA derivar de Departamento->Empresa (26% divergem).';

-- ---------------------------------------------------------------------------
-- PII — tabela apartada, policy própria
-- ---------------------------------------------------------------------------
create table if not exists app.employee_pii (
  employee_id   uuid primary key references app.employee(id) on delete cascade,
  tenant_id        uuid not null references app.tenant(id) on delete cascade,
  cpf              text,
  rg               text,
  pis              text,
  ctps             text,
  birth_date  date,
  mother_name         text,
  father_name         text,
  phone         text,
  personal_email    text,
  address         jsonb,
  updated_at    timestamptz not null default now()
);
create index if not exists employee_pii_tenant_idx on app.employee_pii (tenant_id);
comment on table app.employee_pii is
  'Dado pessoal direto. Acesso exige util.can_see_domain(tenant, ''pii''). Nunca entra em view de dashboard.';

-- ---------------------------------------------------------------------------
-- Históricos
-- ---------------------------------------------------------------------------
create table if not exists app.employee_compensation (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references app.tenant(id) on delete cascade,
  employee_id   uuid not null references app.employee(id) on delete cascade,
  effective_from  date not null,
  effective_to     date,
  salary          numeric(14,2) not null check (salary >= 0),
  reason           text,
  recorded_by   uuid references auth.users(id),
  created_at        timestamptz not null default now(),
  check (effective_to is null or effective_to >= effective_from)
);
create index if not exists remuneracao_colab_idx on app.employee_compensation (employee_id, effective_from desc);

create table if not exists app.employee_position (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references app.tenant(id) on delete cascade,
  employee_id   uuid not null references app.employee(id) on delete cascade,
  effective_from  date not null,
  effective_to     date,
  cargo            text not null,
  unit_id       uuid references app.unit(id),
  created_at        timestamptz not null default now()
);
create index if not exists responsibility_colab_idx on app.employee_position (employee_id, effective_from desc);

-- Afastamento com rótulo NEUTRO. O reason real nunca é armazenado nem exibido.
create table if not exists app.leave_period (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references app.tenant(id) on delete cascade,
  employee_id   uuid not null references app.employee(id) on delete cascade,
  category        text not null check (category in ('vacation','leave_period','leave_of_absence','suspension')),
  start_date      date not null,
  end_date         date,
  source           text not null default 'secullum' check (source in ('secullum','manual','spreadsheet')),
  created_at        timestamptz not null default now(),
  check (end_date is null or end_date >= start_date)
);
create index if not exists leave_period_periodo_idx on app.leave_period (employee_id, start_date, end_date);
comment on table app.leave_period is
  'Rótulo neutro por decisão de produto. Motivo de leave_period é dado de saúde e não é capturado.';

-- ---------------------------------------------------------------------------
-- Responsáveis e contatos (destination dos alertas)
-- ---------------------------------------------------------------------------
create table if not exists app.contact (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references app.tenant(id) on delete cascade,
  name             text not null,
  whatsapp         text check (whatsapp ~ '^\+?\d{10,15}$'),
  email            text,
  type             text not null default 'person' check (type in ('person','whatsapp_group','email_list')),
  active            boolean not null default true,
  created_at        timestamptz not null default now()
);
create index if not exists contact_tenant_idx on app.contact (tenant_id) where active;

create table if not exists app.unit_responsible (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references app.tenant(id) on delete cascade,
  unit_id       uuid not null references app.unit(id) on delete cascade,
  contact_id       uuid not null references app.contact(id) on delete cascade,
  responsibility           text not null check (responsibility in ('unit_manager','regional_supervisor','personnel','hr','executive','group')),
  is_primary        boolean not null default false,
  unique (unit_id, contact_id, responsibility)
);
create index if not exists unit_responsible_unidade_idx on app.unit_responsible (unit_id);

-- ---------------------------------------------------------------------------
-- FKs pendentes da migration 02
-- ---------------------------------------------------------------------------
alter table app.user_scope
  drop constraint if exists user_scope_empresa_fk,
  add  constraint user_scope_empresa_fk foreign key (company_id) references app.company(id) on delete cascade;
alter table app.user_scope
  drop constraint if exists user_scope_unidade_fk,
  add  constraint user_scope_unidade_fk foreign key (unit_id) references app.unit(id) on delete cascade;

-- ---------------------------------------------------------------------------
-- Helpers de escopo (dependiam de app.company/app.unit)
-- ---------------------------------------------------------------------------
create or replace function util.can_see_company(p_company_id uuid)
returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1
    from app.company emp
    join app.tenant_member tm
      on tm.tenant_id = emp.tenant_id
     and tm.user_id   = (select auth.uid())
     and tm.active
    where emp.id = p_company_id
      and (
        tm.role in ('owner','executive','hr','personnel')
        or exists (
          select 1 from app.user_scope e
          where e.user_id   = tm.user_id
            and e.tenant_id = emp.tenant_id
            and (e.company_id is null or e.company_id = emp.id)
        )
      )
  );
$$;

create or replace function util.can_see_unit(p_unit_id uuid)
returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1
    from app.unit u
    join app.tenant_member tm
      on tm.tenant_id = u.tenant_id
     and tm.user_id   = (select auth.uid())
     and tm.active
    where u.id = p_unit_id
      and (
        tm.role in ('owner','executive','hr','personnel')
        or exists (
          select 1 from app.user_scope e
          where e.user_id   = tm.user_id
            and e.tenant_id = u.tenant_id
            and (e.company_id is null or e.company_id = u.company_id)
            and (e.unit_id is null or e.unit_id = u.id)
        )
      )
  );
$$;

-- Colaborador sem unit (mapeamento pendente) só aparece para admin.
create or replace function util.can_see_employee(p_employee_id uuid)
returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from app.employee c
    where c.id = p_employee_id
      and (
        util.is_admin(c.tenant_id)
        or (c.unit_id is not null and util.can_see_unit(c.unit_id))
        or (c.unit_id is null    and util.can_see_company(c.company_id))
      )
  );
$$;

grant execute on function util.can_see_company(uuid)     to authenticated, service_role;
grant execute on function util.can_see_unit(uuid)     to authenticated, service_role;
grant execute on function util.can_see_employee(uuid) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array[
    'company','unit','unit_secullum_map','department','employee',
    'employee_pii','employee_compensation','employee_position',
    'leave_period','contact','unit_responsible'
  ] loop
    execute format('alter table app.%I enable row level security', t);
    execute format('revoke all on table app.%I from anon', t);
  end loop;
end $$;

drop policy if exists company_read on app.company;
create policy company_read on app.company
  for select to authenticated using (util.can_see_company(id));

drop policy if exists company_write on app.company;
create policy company_write on app.company
  for all to authenticated using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

drop policy if exists unit_read on app.unit;
create policy unit_read on app.unit
  for select to authenticated using (util.can_see_unit(id));

drop policy if exists unit_write on app.unit;
create policy unit_write on app.unit
  for all to authenticated using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

drop policy if exists mapa_admin on app.unit_secullum_map;
create policy mapa_admin on app.unit_secullum_map
  for all to authenticated using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

drop policy if exists department_read on app.department;
create policy department_read on app.department
  for select to authenticated using (util.can_see_company(company_id));

drop policy if exists employee_read on app.employee;
create policy employee_read on app.employee
  for select to authenticated
  using (
    util.is_admin(tenant_id)
    or (unit_id is not null and util.can_see_unit(unit_id))
    or (unit_id is null     and util.can_see_company(company_id))
  );

drop policy if exists employee_write on app.employee;
create policy employee_write on app.employee
  for all to authenticated using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

-- PII: escopo E domínio. Ver a unit não basta.
drop policy if exists pii_read on app.employee_pii;
create policy pii_read on app.employee_pii
  for select to authenticated
  using (util.can_see_domain(tenant_id, 'pii') and util.can_see_employee(employee_id));

drop policy if exists pii_write on app.employee_pii;
create policy pii_write on app.employee_pii
  for all to authenticated
  using (util.can_see_domain(tenant_id, 'pii') and util.is_admin(tenant_id))
  with check (util.can_see_domain(tenant_id, 'pii') and util.is_admin(tenant_id));

drop policy if exists remuneracao_read on app.employee_compensation;
create policy remuneracao_read on app.employee_compensation
  for select to authenticated
  using (util.can_see_domain(tenant_id, 'compensation') and util.can_see_employee(employee_id));

drop policy if exists remuneracao_write on app.employee_compensation;
create policy remuneracao_write on app.employee_compensation
  for all to authenticated
  using (util.can_see_domain(tenant_id, 'compensation') and util.is_admin(tenant_id))
  with check (util.can_see_domain(tenant_id, 'compensation') and util.is_admin(tenant_id));

drop policy if exists responsibility_read on app.employee_position;
create policy responsibility_read on app.employee_position
  for select to authenticated using (util.can_see_employee(employee_id));

drop policy if exists leave_period_read on app.leave_period;
create policy leave_period_read on app.leave_period
  for select to authenticated using (util.can_see_employee(employee_id));

drop policy if exists contact_admin on app.contact;
create policy contact_admin on app.contact
  for all to authenticated using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

drop policy if exists contact_read on app.contact;
create policy contact_read on app.contact
  for select to authenticated using (util.has_tenant(tenant_id));

drop policy if exists unit_responsible_read on app.unit_responsible;
create policy unit_responsible_read on app.unit_responsible
  for select to authenticated using (util.can_see_unit(unit_id));

drop policy if exists unit_responsible_admin on app.unit_responsible;
create policy unit_responsible_admin on app.unit_responsible
  for all to authenticated using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

grant select on all tables in schema app to authenticated;
grant insert, update, delete on
  app.company, app.unit, app.unit_secullum_map, app.department,
  app.employee, app.employee_pii, app.employee_compensation,
  app.employee_position, app.contact, app.unit_responsible
to authenticated;
