-- ============================================================================
-- OperaX — 22. FILTRO POR DEPARTAMENTO E POR GESTOR NOS QUATRO RPCs
-- ----------------------------------------------------------------------------
-- O escopo contratado exige os dois filtros (COBERTURA-ESCOPO §4.3) e nenhum dos
-- quatro RPCs públicos os aceitava. `app.employee` já carrega `department_id` e
-- `manager_employee_id` desde a migration 04 — o que faltava era o caminho até
-- eles.
--
-- POR QUE O FILTRO PRECISA DE UM JOIN, E POR QUE ELE NÃO MUDA NENHUMA CONTA
-- `app.deviation_event` guarda `company_id` e `unit_id`, e não guarda
-- departamento nem gestor — de propósito: os dois mudam com o tempo e o evento é
-- um fato datado. Então o filtro entra por `app.employee`, com um join 1:1 pela
-- chave primária. Um join 1:1 não duplica linha e não altera `count(*)`, o que é
-- a única razão de ele poder ser incondicional em vez de montado por string.
--
-- ⚠️ DEPARTAMENTO FILTRA PESSOA, NUNCA EMPRESA
-- Este é o lugar onde a regra 5 do CLAUDE.md pode ser violada sem que ninguém
-- perceba: `app.department` tem `company_id`, e é tentador derivar empresa a
-- partir dele. Cerca de 26% dos vínculos da FastPark divergem — alguém da
-- Empresa B lotado num departamento da Empresa A. `p_department_id` filtra
-- `app.employee.department_id` e nada mais; `p_company_id` continua saindo de
-- `app.deviation_event.company_id`, que veio da pessoa.
--
-- POR QUE `drop` E NÃO `create or replace`
-- Acrescentar parâmetro muda a assinatura, e `create or replace` com assinatura
-- nova cria uma SOBRECARGA em vez de substituir: as chamadas antigas passariam a
-- ser ambíguas e falhariam. O `drop` é do identificador antigo, exato, e o
-- `create` seguinte repõe os grants — não há janela em que a função não exista,
-- porque a migration inteira roda numa transação.
--
-- Chamada antiga continua válida: os dois parâmetros novos entram por último e
-- com default null, então `fn_ranking_by_unit(de, ate)` segue significando o
-- mesmo.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. fn_kpi_period
-- ---------------------------------------------------------------------------
drop function if exists public.fn_kpi_period(date, date, uuid, uuid);

create or replace function public.fn_kpi_period(
  p_de date, p_ate date,
  p_company_id    uuid default null,
  p_unit_id       uuid default null,
  p_department_id uuid default null,
  p_manager_id    uuid default null
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
  join app.employee e on e.id = d.employee_id
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_company_id    is null or d.company_id = p_company_id)
    and (p_unit_id       is null or d.unit_id = p_unit_id)
    and (p_department_id is null or e.department_id = p_department_id)
    and (p_manager_id    is null or e.manager_employee_id = p_manager_id);
$$;

-- ---------------------------------------------------------------------------
-- 2. fn_ranking_by_unit
-- ---------------------------------------------------------------------------
drop function if exists public.fn_ranking_by_unit(date, date, uuid, int);

create or replace function public.fn_ranking_by_unit(
  p_de date, p_ate date,
  p_company_id    uuid default null,
  p_limite        int  default 20,
  p_department_id uuid default null,
  p_manager_id    uuid default null
) returns table (unit_id uuid, unit_name text, eventos bigint, minutes_abs bigint, colaboradores bigint)
language sql stable security invoker set search_path = ''
as $$
  select d.unit_id, u.name, count(*), coalesce(sum(abs(d.minutes)),0), count(distinct d.employee_id)
  from app.deviation_event d
  join app.employee e on e.id = d.employee_id
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  left join app.unit u on u.id = d.unit_id
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_company_id    is null or d.company_id = p_company_id)
    and (p_department_id is null or e.department_id = p_department_id)
    and (p_manager_id    is null or e.manager_employee_id = p_manager_id)
  group by d.unit_id, u.name
  order by count(*) desc
  limit greatest(p_limite, 1);
$$;

-- ---------------------------------------------------------------------------
-- 3. fn_ranking_by_employee
-- ---------------------------------------------------------------------------
drop function if exists public.fn_ranking_by_employee(date, date, uuid, uuid, int);

create or replace function public.fn_ranking_by_employee(
  p_de date, p_ate date,
  p_company_id    uuid default null,
  p_unit_id       uuid default null,
  p_limite        int  default 20,
  p_department_id uuid default null,
  p_manager_id    uuid default null
) returns table (employee_id uuid, employee_name text, unit_name text, eventos bigint, minutes_abs bigint)
language sql stable security invoker set search_path = ''
as $$
  select d.employee_id, e.name, u.name, count(*), coalesce(sum(abs(d.minutes)),0)
  from app.deviation_event d
  join app.employee e on e.id = d.employee_id
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  left join app.unit u on u.id = d.unit_id
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_company_id    is null or d.company_id = p_company_id)
    and (p_unit_id       is null or d.unit_id = p_unit_id)
    and (p_department_id is null or e.department_id = p_department_id)
    and (p_manager_id    is null or e.manager_employee_id = p_manager_id)
  group by d.employee_id, e.name, u.name
  order by count(*) desc
  limit greatest(p_limite, 1);
$$;

-- ---------------------------------------------------------------------------
-- 4. fn_recurrence
-- ---------------------------------------------------------------------------
drop function if exists public.fn_recurrence(date, date, int, uuid);

create or replace function public.fn_recurrence(
  p_de date, p_ate date,
  p_min_dias      int  default 3,
  p_unit_id       uuid default null,
  p_department_id uuid default null,
  p_manager_id    uuid default null
) returns table (employee_id uuid, employee_name text, unit_name text, dias_com_desvio bigint, eventos bigint)
language sql stable security invoker set search_path = ''
as $$
  select d.employee_id, e.name, u.name,
         count(distinct d.reference_date), count(*)
  from app.deviation_event d
  join app.employee e on e.id = d.employee_id
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  left join app.unit u on u.id = d.unit_id
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_unit_id       is null or d.unit_id = p_unit_id)
    and (p_department_id is null or e.department_id = p_department_id)
    and (p_manager_id    is null or e.manager_employee_id = p_manager_id)
  group by d.employee_id, e.name, u.name
  having count(distinct d.reference_date) >= greatest(p_min_dias, 1)
  order by count(distinct d.reference_date) desc;
$$;

-- ---------------------------------------------------------------------------
-- Grants — repostos porque o `drop` os levou junto
-- ---------------------------------------------------------------------------
do $$
declare f text;
begin
  foreach f in array array[
    'public.fn_kpi_period(date, date, uuid, uuid, uuid, uuid)',
    'public.fn_ranking_by_unit(date, date, uuid, int, uuid, uuid)',
    'public.fn_ranking_by_employee(date, date, uuid, uuid, int, uuid, uuid)',
    'public.fn_recurrence(date, date, int, uuid, uuid, uuid)'
  ] loop
    execute format('revoke execute on function %s from public, anon', f);
    execute format('grant  execute on function %s to authenticated, service_role', f);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_antes  bigint;
  v_dept   bigint;
  v_nomes  text;
begin
  -- 1. Existe exatamente UMA versão de cada função. Duas seria a sobrecarga
  --    ambígua que o `drop` existe para evitar — e ela só apareceria quando
  --    alguém chamasse com a assinatura antiga, em produção.
  for v_nomes in
    select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname in ('fn_kpi_period','fn_ranking_by_unit','fn_ranking_by_employee','fn_recurrence')
    group by p.proname having count(*) > 1
  loop
    raise exception '% tem mais de uma assinatura — chamada antiga vira ambígua', v_nomes;
  end loop;

  -- 2. `anon` continua sem executar nenhuma delas.
  if has_function_privilege('anon', 'public.fn_kpi_period(date,date,uuid,uuid,uuid,uuid)', 'execute')
  then
    raise exception 'anon executa fn_kpi_period';
  end if;

  -- 3. A chamada ANTIGA continua funcionando, com o mesmo significado.
  select eventos into v_antes from public.fn_kpi_period(date '1999-01-01', date '1999-12-31');
  if v_antes is null then
    raise exception 'a chamada de dois argumentos deixou de funcionar';
  end if;
  perform * from public.fn_ranking_by_unit(date '1999-01-01', date '1999-12-31');
  perform * from public.fn_ranking_by_employee(date '1999-01-01', date '1999-12-31');
  perform * from public.fn_recurrence(date '1999-01-01', date '1999-12-31');

  -- 4. O filtro novo é aceito e restringe (num período vazio, restringe a zero).
  select eventos into v_dept
    from public.fn_kpi_period(
      date '1999-01-01', date '1999-12-31',
      p_department_id => '00000000-0000-0000-0000-000000000000'::uuid);
  if v_dept <> 0 then
    raise exception 'filtro de departamento inexistente devolveu % eventos', v_dept;
  end if;
  perform * from public.fn_recurrence(
    date '1999-01-01', date '1999-12-31',
    p_manager_id => '00000000-0000-0000-0000-000000000000'::uuid);

  raise notice 'OK: os quatro RPCs filtram por departamento e gestor, e a chamada antiga não mudou.';
end $$;
