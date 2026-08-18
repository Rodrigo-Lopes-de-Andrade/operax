-- ============================================================================
-- OperaX — 10. PUBLIC SURFACE: VIEWS AND RPCs
-- ----------------------------------------------------------------------------
-- Este é o ÚNICO schema que o PostgREST expõe. No tables mora aqui
-- (a event trigger da migration 01 impede). Só view e função.
--
-- Toda view usa security_invoker = on. Sem isso a view rodaria com privilégio
-- do DONO e IGNORARIA a RLS das tabelas base — que é exatamente o alerta
-- `security_definer_view` do linter do Supabase e a forma mais comum de
-- vazamento em projeto que "tem RLS".
--
-- anon não recebe nada. Nem uma view. O painel autentica antes de ler.
--
-- Regra de agregação: SEMPRE pelo caminho employee -> company. NUNCA
-- department -> company (26% divergem na Kastro Park).
-- ============================================================================

do $$
begin
  if current_setting('server_version_num')::int < 150000 then
    raise exception 'security_invoker em views exige Postgres 15+. Versão atual: %', current_setting('server_version');
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- Dimensões
-- ---------------------------------------------------------------------------
create or replace view public.vw_unit
with (security_invoker = on) as
select u.id            as unit_id,
       u.tenant_id,
       u.company_id,
       e.trade_name as company_name,
       u.code,
       u.name,
       u.timezone,
       u.active
from app.unit u
join app.company e on e.id = u.company_id;

-- Sem uma única coluna de app.employee_pii. Por construção, não por disciplina.
create or replace view public.vw_employee
with (security_invoker = on) as
select c.id          as employee_id,
       c.tenant_id,
       c.company_id,
       c.unit_id,
       c.name,
       c.registration_number,
       c.cargo,
       c.hired_on,
       c.status,
       u.name         as unit_name,
       e.trade_name as company_name,
       g.name         as gestor_name
from app.employee c
left join app.unit  u on u.id = c.unit_id
left join app.company  e on e.id = c.company_id
left join app.employee g on g.id = c.manager_employee_id;

-- ---------------------------------------------------------------------------
-- Desvios — grão evento (drill-down e filtro por query string no cliente)
-- ---------------------------------------------------------------------------
create or replace view public.vw_deviation_event
with (security_invoker = on) as
select d.id            as evento_id,
       d.tenant_id,
       d.reference_date,
       d.company_id,
       d.unit_id,
       u.name          as unit_name,
       d.employee_id,
       c.name          as employee_name,
       d.type,
       t.description     as type_description,
       t.direction,
       t.category,
       d.minutes,
       abs(d.minutes)  as minutes_abs,
       d.expected_time,
       d.actual_time,
       d.status,
       d.report_cycle_id,
       (d.report_cycle_id is null) as pendente_de_ciclo,
       d.detected_at,
       cfg.counts_as_deviation
from app.deviation_event d
join app.deviation_type t          on t.code = d.type
join app.employee c          on c.id = d.employee_id
left join app.unit u         on u.id = d.unit_id
left join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type
where d.status = 'active'
  and d.mode   = 'production';

-- ---------------------------------------------------------------------------
-- Agregados em grão de DIA. O cliente filtra o período e soma — mantém o
-- cálculo pesado no Postgres sem precisar de view parametrizada.
-- ---------------------------------------------------------------------------
create or replace view public.vw_deviation_summary_by_unit
with (security_invoker = on) as
select d.tenant_id,
       d.reference_date,
       d.unit_id,
       u.name                                   as unit_name,
       d.company_id,
       count(*)                                 as eventos,
       count(distinct d.employee_id)         as colaboradores,
       sum(d.minutes) filter (where d.minutes > 0) as minutes_excedente,
       -sum(d.minutes) filter (where d.minutes < 0) as minutes_faltante,
       sum(abs(d.minutes))                      as minutes_abs
from app.deviation_event d
join app.deviation_type_config cfg
     on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
left join app.unit u on u.id = d.unit_id
where d.status = 'active' and d.mode = 'production'
group by d.tenant_id, d.reference_date, d.unit_id, u.name, d.company_id;

create or replace view public.vw_deviation_daily_trend
with (security_invoker = on) as
select d.tenant_id,
       d.reference_date,
       d.unit_id,
       t.direction,
       count(*)            as eventos,
       sum(abs(d.minutes)) as minutes_abs
from app.deviation_event d
join app.deviation_type t on t.code = d.type
join app.deviation_type_config cfg
     on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
where d.status = 'active' and d.mode = 'production'
group by d.tenant_id, d.reference_date, d.unit_id, t.direction;

create or replace view public.vw_deviation_by_employee_day
with (security_invoker = on) as
select d.tenant_id,
       d.reference_date,
       d.employee_id,
       c.name              as employee_name,
       d.unit_id,
       u.name              as unit_name,
       count(*)            as eventos,
       sum(abs(d.minutes)) as minutes_abs
from app.deviation_event d
join app.employee c on c.id = d.employee_id
join app.deviation_type_config cfg
     on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
left join app.unit u on u.id = d.unit_id
where d.status = 'active' and d.mode = 'production'
group by d.tenant_id, d.reference_date, d.employee_id, c.name, d.unit_id, u.name;

-- ---------------------------------------------------------------------------
-- Documentos e folha
-- ---------------------------------------------------------------------------
create or replace view public.vw_document_expiry
with (security_invoker = on) as
select doc.id           as document_id,
       doc.tenant_id,
       doc.employee_id,
       c.name           as employee_name,
       c.unit_id,
       dt.name          as type_name,
       doc.valid_until,
       (doc.valid_until - current_date) as dias_para_vencer,
       dt.expiry_alert_days,
       (doc.valid_until - current_date) <= dt.expiry_alert_days as em_alerta
from app.document doc
join app.document_type dt on dt.id = doc.type_id
join app.employee c     on c.id = doc.employee_id
where doc.status = 'active' and doc.valid_until is not null;

create or replace view public.vw_payroll_summary
with (security_invoker = on) as
select f.tenant_id,
       comp.year,
       comp.month,
       f.company_id,
       f.unit_id,
       sum(f.amount) filter (where f.nature = 'earning')  as total_proventos,
       sum(f.amount) filter (where f.nature = 'deduction')  as total_descontos,
       sum(f.amount) filter (where f.nature = 'payroll_charge')   as total_encargos,
       count(distinct f.employee_id)                     as colaboradores
from app.payroll_entry f
join app.payroll_period comp on comp.id = f.payroll_period_id
group by f.tenant_id, comp.year, comp.month, f.company_id, f.unit_id;

-- ---------------------------------------------------------------------------
-- RPCs com período parametrizado
-- security invoker (padrão): a RLS do usuário que chamou continua valendo.
-- ---------------------------------------------------------------------------
create or replace function public.fn_kpi_period(
  p_de date, p_ate date,
  p_company_id uuid default null,
  p_unit_id uuid default null
) returns table (
  eventos bigint, colaboradores_afetados bigint,
  minutes_excedente bigint, minutes_faltante bigint, minutes_abs bigint,
  unidades_afetadas bigint, eventos_pendentes_ciclo bigint
)
language sql stable security invoker set search_path = ''
as $$
  select count(*),
         count(distinct d.employee_id),
         coalesce(sum(d.minutes) filter (where d.minutes > 0), 0),
         coalesce(-sum(d.minutes) filter (where d.minutes < 0), 0),
         coalesce(sum(abs(d.minutes)), 0),
         count(distinct d.unit_id),
         count(*) filter (where d.report_cycle_id is null)
  from app.deviation_event d
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_company_id is null or d.company_id = p_company_id)
    and (p_unit_id is null or d.unit_id = p_unit_id);
$$;

create or replace function public.fn_ranking_by_unit(
  p_de date, p_ate date, p_company_id uuid default null, p_limite int default 20
) returns table (unit_id uuid, unit_name text, eventos bigint, minutes_abs bigint, colaboradores bigint)
language sql stable security invoker set search_path = ''
as $$
  select d.unit_id, u.name, count(*), coalesce(sum(abs(d.minutes)),0), count(distinct d.employee_id)
  from app.deviation_event d
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  left join app.unit u on u.id = d.unit_id
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_company_id is null or d.company_id = p_company_id)
  group by d.unit_id, u.name
  order by count(*) desc
  limit greatest(p_limite, 1);
$$;

create or replace function public.fn_ranking_by_employee(
  p_de date, p_ate date, p_company_id uuid default null,
  p_unit_id uuid default null, p_limite int default 20
) returns table (employee_id uuid, employee_name text, unit_name text, eventos bigint, minutes_abs bigint)
language sql stable security invoker set search_path = ''
as $$
  select d.employee_id, c.name, u.name, count(*), coalesce(sum(abs(d.minutes)),0)
  from app.deviation_event d
  join app.employee c on c.id = d.employee_id
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  left join app.unit u on u.id = d.unit_id
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_company_id is null or d.company_id = p_company_id)
    and (p_unit_id is null or d.unit_id = p_unit_id)
  group by d.employee_id, c.name, u.name
  order by count(*) desc
  limit greatest(p_limite, 1);
$$;

-- KPI 8 da proposta: desvio em 3+ dias distintos na janela.
create or replace function public.fn_recurrence(
  p_de date, p_ate date, p_min_dias int default 3, p_unit_id uuid default null
) returns table (employee_id uuid, employee_name text, unit_name text, dias_com_desvio bigint, eventos bigint)
language sql stable security invoker set search_path = ''
as $$
  select d.employee_id, c.name, u.name,
         count(distinct d.reference_date), count(*)
  from app.deviation_event d
  join app.employee c on c.id = d.employee_id
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  left join app.unit u on u.id = d.unit_id
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_unit_id is null or d.unit_id = p_unit_id)
  group by d.employee_id, c.name, u.name
  having count(distinct d.reference_date) >= greatest(p_min_dias, 1)
  order by count(distinct d.reference_date) desc;
$$;

-- ---------------------------------------------------------------------------
-- Grants: authenticated lê, anon não existe
-- ---------------------------------------------------------------------------
do $$
declare r record;
begin
  for r in select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
           where n.nspname = 'public' and c.relkind = 'v'
  loop
    execute format('revoke all on public.%I from anon, public', r.relname);
    execute format('grant select on public.%I to authenticated, service_role', r.relname);
  end loop;
end $$;

revoke execute on all functions in schema public from anon, public;
grant  execute on function public.fn_kpi_period(date, date, uuid, uuid)              to authenticated, service_role;
grant  execute on function public.fn_ranking_by_unit(date, date, uuid, int)           to authenticated, service_role;
grant  execute on function public.fn_ranking_by_employee(date, date, uuid, uuid, int) to authenticated, service_role;
grant  execute on function public.fn_recurrence(date, date, int, uuid)               to authenticated, service_role;

-- Catálogo semântico aponta para os alvos reais criados aqui.
update app.metric set target_view = 'fn_ranking_by_unit'     where code = 'ranking_by_unit';
update app.metric set target_view = 'fn_ranking_by_employee' where code = 'ranking_by_employee';
update app.metric set target_view = 'fn_recurrence'         where code = 'recurrence';
update app.metric set target_view = 'vw_deviation_by_employee_day' where code = 'deviations_minutes';

-- ---------------------------------------------------------------------------
-- Proof: nenhuma view SECURITY DEFINER, nenhum objeto legível por anon
-- ---------------------------------------------------------------------------
do $$
declare n int;
begin
  select count(*) into n
  from pg_class c join pg_namespace n2 on n2.oid = c.relnamespace
  where n2.nspname = 'public' and c.relkind = 'v'
    and not coalesce(array_to_string(c.reloptions, ',') like '%security_invoker=%', false);
  if n > 0 then
    raise exception 'HÁ % view(s) em public sem security_invoker — elas IGNORAM a RLS das tabelas base', n;
  end if;

  select count(*) into n
  from pg_class c join pg_namespace n2 on n2.oid = c.relnamespace
  where n2.nspname = 'public' and c.relkind = 'v'
    and has_table_privilege('anon', c.oid, 'SELECT');
  if n > 0 then
    raise exception 'HÁ % view(s) em public legíveis por anon', n;
  end if;

  raise notice 'OK: superfície pública com security_invoker e sem acesso anônimo.';
end $$;
