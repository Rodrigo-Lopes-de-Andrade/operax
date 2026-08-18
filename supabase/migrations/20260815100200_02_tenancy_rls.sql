-- ============================================================================
-- OperaX — 02. TENANCY, ROLES, SCOPE AND RLS HELPERS
-- ----------------------------------------------------------------------------
-- Three independent authorization axes. Toda policy de domínio combina os
-- três — nenhuma tabela pode depender de só um:
--
--   1. TENANT        de qual cliente OperaX é o dado.      util.has_tenant()
--   2. ESCOPO        quais empresas/unidades o usuário vê. util.can_see_unit()  [migration 04]
--   3. SENSIBILIDADE pii / remuneracao / saude / disciplinar. util.can_see_domain()
--
-- Doing this now, with only master data synced, is the cheapest window
-- there will ever be. Depois de deviation_event e folha em produção, é reescrita.
--
-- Sobre SECURITY DEFINER: estes helpers bypassam RLS por definição — é o que
-- evita recursão infinita nas policies. Em troca: search_path travado em '',
-- checagem explícita de auth.uid() no corpo, schema não exposto ao PostgREST,
-- e EXECUTE revogado de anon.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Tipos
-- ---------------------------------------------------------------------------
do $$ begin
  create type app.user_role as enum (
    'owner',              -- tenant-wide administrator
    'executive',
    'hr',
    'personnel',                 -- personnel department
    'regional_manager',
    'unit_supervisor',
    'operations_manager',
    'accounting',
    'viewer'            -- read-only, no sensitive data
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type app.sensitive_domain as enum ('pii','compensation','health','disciplinary');
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- Tabelas
-- ---------------------------------------------------------------------------
create table if not exists app.tenant (
  id          uuid primary key default gen_random_uuid(),
  slug        text not null unique check (slug ~ '^[a-z0-9-]{2,40}$'),
  name        text not null,
  active       boolean not null default true,
  created_at   timestamptz not null default now()
);
comment on table app.tenant is 'OperaX customer. Kastro Park is the first.';

create table if not exists app.tenant_member (
  tenant_id   uuid not null references app.tenant(id) on delete cascade,
  user_id     uuid not null references auth.users(id) on delete cascade,
  role       app.user_role not null,
  active       boolean not null default true,
  created_at   timestamptz not null default now(),
  primary key (tenant_id, user_id)
);
create index if not exists tenant_member_user_idx on app.tenant_member (user_id) where active;

-- Additive scope. One row per grant:
--   company_id NULL e unit_id NULL -> entire tenant
--   company_id set             -> the whole company
--   unit_id set             -> that unit only
create table if not exists app.user_scope (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references app.tenant(id) on delete cascade,
  user_id     uuid not null references auth.users(id) on delete cascade,
  company_id  uuid,   -- FK adicionada na migration 04
  unit_id  uuid,   -- FK adicionada na migration 04
  created_at   timestamptz not null default now()
);
create index if not exists user_scope_lookup_idx  on app.user_scope (user_id, tenant_id);
create index if not exists user_scope_empresa_idx on app.user_scope (company_id) where company_id is not null;
create index if not exists user_scope_unidade_idx on app.user_scope (unit_id) where unit_id is not null;

-- Who sees what, by role. Data-driven: changes by UPDATE, not migration.
create table if not exists app.domain_permission (
  tenant_id   uuid not null references app.tenant(id) on delete cascade,
  role       app.user_role not null,
  domain     app.sensitive_domain not null,
  allowed   boolean not null default false,
  primary key (tenant_id, role, domain)
);
comment on table app.domain_permission is
  'Salário, RG, ASO e ocorrência disciplinar são decisão de dado, não de código.';

-- ---------------------------------------------------------------------------
-- Helpers (os que dependem de app.company/app.unit estão na migration 04)
-- ---------------------------------------------------------------------------
create or replace function util.user_tenants()
returns uuid[]
language sql stable security definer set search_path = ''
as $$
  select coalesce(array_agg(tm.tenant_id), '{}'::uuid[])
  from app.tenant_member tm
  where tm.user_id = (select auth.uid())
    and tm.active;
$$;

create or replace function util.has_tenant(p_tenant_id uuid)
returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from app.tenant_member tm
    where tm.tenant_id = p_tenant_id
      and tm.user_id = (select auth.uid())
      and tm.active
  );
$$;

create or replace function util.roles_in_tenant(p_tenant_id uuid)
returns app.user_role[]
language sql stable security definer set search_path = ''
as $$
  select coalesce(array_agg(tm.role), '{}'::app.user_role[])
  from app.tenant_member tm
  where tm.tenant_id = p_tenant_id
    and tm.user_id = (select auth.uid())
    and tm.active;
$$;

-- No row in domain_permission = denied.
create or replace function util.can_see_domain(p_tenant_id uuid, p_domain app.sensitive_domain)
returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1
    from app.tenant_member tm
    join app.domain_permission pd
      on pd.tenant_id = tm.tenant_id
     and pd.role     = tm.role
     and pd.domain   = p_domain
     and pd.allowed
    where tm.tenant_id = p_tenant_id
      and tm.user_id = (select auth.uid())
      and tm.active
  );
$$;

create or replace function util.is_admin(p_tenant_id uuid)
returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from app.tenant_member tm
    where tm.tenant_id = p_tenant_id
      and tm.user_id = (select auth.uid())
      and tm.active
      and tm.role in ('owner','hr','personnel')
  );
$$;

-- Policies evaluate as the querying user, so EXECUTE is required.
revoke execute on all functions in schema util from public, anon;
grant  execute on function util.user_tenants()                                 to authenticated, service_role;
grant  execute on function util.has_tenant(uuid)                                     to authenticated, service_role;
grant  execute on function util.roles_in_tenant(uuid)                               to authenticated, service_role;
grant  execute on function util.can_see_domain(uuid, app.sensitive_domain)         to authenticated, service_role;
grant  execute on function util.is_admin(uuid)                                       to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table app.tenant            enable row level security;
alter table app.tenant_member     enable row level security;
alter table app.user_scope    enable row level security;
alter table app.domain_permission enable row level security;

drop policy if exists tenant_read on app.tenant;
create policy tenant_read on app.tenant
  for select to authenticated
  using (util.has_tenant(id));

drop policy if exists tenant_member_read on app.tenant_member;
create policy tenant_member_read on app.tenant_member
  for select to authenticated
  using (util.has_tenant(tenant_id));

drop policy if exists tenant_member_admin on app.tenant_member;
create policy tenant_member_admin on app.tenant_member
  for all to authenticated
  using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

drop policy if exists escopo_read on app.user_scope;
create policy escopo_read on app.user_scope
  for select to authenticated
  using (user_id = (select auth.uid()) or util.is_admin(tenant_id));

drop policy if exists escopo_admin on app.user_scope;
create policy escopo_admin on app.user_scope
  for all to authenticated
  using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

drop policy if exists domain_permission_read on app.domain_permission;
create policy domain_permission_read on app.domain_permission
  for select to authenticated
  using (util.has_tenant(tenant_id));

grant select on app.tenant, app.tenant_member, app.user_scope, app.domain_permission to authenticated;
grant insert, update, delete on app.tenant_member, app.user_scope to authenticated;

-- ---------------------------------------------------------------------------
-- Seed: Kastro Park + matriz de sensibilidade padrão
-- ---------------------------------------------------------------------------
insert into app.tenant (slug, name)
values ('kastro-park', 'Kastro Park')
on conflict (slug) do nothing;

insert into app.domain_permission (tenant_id, role, domain, allowed)
select t.id, p.role, d.domain,
       case
         when p.role = 'owner'         then true
         when p.role = 'personnel'            then d.domain in ('pii','compensation','disciplinary')
         when p.role = 'hr'            then d.domain in ('pii','health','disciplinary')
         when p.role = 'executive'     then d.domain in ('compensation')
         when p.role = 'accounting' then d.domain in ('compensation')
         else false
       end
from app.tenant t
cross join (select unnest(enum_range(null::app.user_role))            as role)   p
cross join (select unnest(enum_range(null::app.sensitive_domain)) as domain) d
where t.slug = 'kastro-park'
on conflict (tenant_id, role, domain) do nothing;

-- NOTA DELIBERADA: gestor_regional, supervisor_unit, gestor_operacional e
-- consulta ficam sem nenhum domínio sensível. Gestor vê ocorrência de ponto da
-- sua unit; não vê salário, RG nem ASO. Alterar por UPDATE se o cliente pedir.
