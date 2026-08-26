-- ============================================================================
-- OperaX — TESTE FUNCIONAL DE ISOLAMENTO MULTI-TENANT
-- ----------------------------------------------------------------------------
-- Não basta "a RLS está ligada". Este teste monta dois clientes com dados
-- reais e prova, consultando como cada usuário, que:
--
--   1. Tenant A não enxerga uma linha sequer do tenant B.
--   2. Supervisor de unit só vê a unit dele, mesmo dentro do seu tenant.
--   3. Supervisor não lê PII nem remuneração — ver a unit não basta.
--   4. DP lê PII mas não lê ASO (dado de saúde).
--   5. Evento em mode sombra não aparece para ninguém que não seja admin.
--
-- Roda em transação revertida. Não deixa resíduo.
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/98_teste_isolamento_tenant.sql
-- ============================================================================

begin;

-- ---------------------------------------------------------------------------
-- Cenário
-- ---------------------------------------------------------------------------
insert into auth.users (id, email) values
  ('11111111-1111-1111-1111-111111111111', 'owner.a@teste'),
  ('22222222-2222-2222-2222-222222222222', 'supervisor.a@teste'),
  ('33333333-3333-3333-3333-333333333333', 'dp.a@teste'),
  ('44444444-4444-4444-4444-444444444444', 'owner.b@teste');

insert into app.tenant (id, slug, name) values
  ('aaaaaaaa-0000-0000-0000-000000000001', 'tenant-a', 'Cliente A'),
  ('bbbbbbbb-0000-0000-0000-000000000002', 'tenant-b', 'Cliente B');

insert into app.domain_permission (tenant_id, role, domain, allowed)
select t.id, p.role, d.domain,
       case when p.role = 'owner' then true
            when p.role = 'personnel'    then d.domain in ('pii','compensation','disciplinary')
            else false end
from app.tenant t
cross join (select unnest(enum_range(null::app.user_role)) role) p
cross join (select unnest(enum_range(null::app.sensitive_domain)) domain) d
where t.slug in ('tenant-a','tenant-b')
on conflict do nothing;

insert into app.tenant_member (tenant_id, user_id, role) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'owner'),
  ('aaaaaaaa-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'unit_supervisor'),
  ('aaaaaaaa-0000-0000-0000-000000000001', '33333333-3333-3333-3333-333333333333', 'personnel'),
  ('bbbbbbbb-0000-0000-0000-000000000002', '44444444-4444-4444-4444-444444444444', 'owner');

insert into app.company (id, tenant_id, legal_name, trade_name) values
  ('a0000000-0000-0000-0000-0000000000e1', 'aaaaaaaa-0000-0000-0000-000000000001', 'Empresa A1 LTDA', 'A1'),
  ('b0000000-0000-0000-0000-0000000000e1', 'bbbbbbbb-0000-0000-0000-000000000002', 'Empresa B1 LTDA', 'B1');

insert into app.unit (id, tenant_id, company_id, code, name) values
  ('a0000000-0000-0000-0000-0000000000a1', 'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000e1', 'A-CENTRO', 'A Centro'),
  ('a0000000-0000-0000-0000-0000000000a2', 'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000e1', 'A-NORTE',  'A Norte'),
  ('b0000000-0000-0000-0000-0000000000a1', 'bbbbbbbb-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-0000000000e1', 'B-SUL',    'B Sul');

-- Supervisor A só tem escopo na unit A Centro.
insert into app.user_scope (tenant_id, user_id, unit_id) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'a0000000-0000-0000-0000-0000000000a1');

insert into app.employee (id, tenant_id, company_id, unit_id, name) values
  ('a0000000-0000-0000-0000-0000000000c1', 'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000e1', 'a0000000-0000-0000-0000-0000000000a1', 'Colab A Centro'),
  ('a0000000-0000-0000-0000-0000000000c2', 'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000e1', 'a0000000-0000-0000-0000-0000000000a2', 'Colab A Norte'),
  ('b0000000-0000-0000-0000-0000000000c1', 'bbbbbbbb-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-0000000000e1', 'b0000000-0000-0000-0000-0000000000a1', 'Colab B Sul');

-- O gestor como dimensão (migration 27). Um por unidade em A, para o ranking
-- ter o que separar; um em B, para provar que ele não atravessa.
insert into app.manager (id, tenant_id, secullum_structure_id, name) values
  ('a0000000-0000-0000-0000-0000000000f1', 'aaaaaaaa-0000-0000-0000-000000000001', 8001, 'Gestor A Centro'),
  ('a0000000-0000-0000-0000-0000000000f2', 'aaaaaaaa-0000-0000-0000-000000000001', 8002, 'Gestor A Norte'),
  ('b0000000-0000-0000-0000-0000000000f1', 'bbbbbbbb-0000-0000-0000-000000000002', 8003, 'Gestor B Sul');

update app.employee set manager_id = 'a0000000-0000-0000-0000-0000000000f1'
 where id = 'a0000000-0000-0000-0000-0000000000c1';
update app.employee set manager_id = 'a0000000-0000-0000-0000-0000000000f2'
 where id = 'a0000000-0000-0000-0000-0000000000c2';
update app.employee set manager_id = 'b0000000-0000-0000-0000-0000000000f1'
 where id = 'b0000000-0000-0000-0000-0000000000c1';

insert into app.employee_pii (employee_id, tenant_id, cpf, rg) values
  ('a0000000-0000-0000-0000-0000000000c1', 'aaaaaaaa-0000-0000-0000-000000000001', '00000000191', 'MG-1'),
  ('b0000000-0000-0000-0000-0000000000c1', 'bbbbbbbb-0000-0000-0000-000000000002', '00000000272', 'SP-2');

insert into app.deviation_type_config (tenant_id, code, active, counts_as_deviation)
select t.id, dt.code, true, true
from app.tenant t cross join app.deviation_type dt
where t.slug in ('tenant-a','tenant-b')
on conflict do nothing;

insert into app.deviation_event (tenant_id, employee_id, company_id, unit_id, reference_date, type, minutes, mode) values
  ('aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c1','a0000000-0000-0000-0000-0000000000e1','a0000000-0000-0000-0000-0000000000a1','2026-08-10','late_entry',-15,'production'),
  ('aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c2','a0000000-0000-0000-0000-0000000000e1','a0000000-0000-0000-0000-0000000000a2','2026-08-10','late_entry',-22,'production'),
  ('aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c1','a0000000-0000-0000-0000-0000000000e1','a0000000-0000-0000-0000-0000000000a1','2026-08-11','late_exit', 40,'shadow'),
  ('bbbbbbbb-0000-0000-0000-000000000002','b0000000-0000-0000-0000-0000000000c1','b0000000-0000-0000-0000-0000000000e1','b0000000-0000-0000-0000-0000000000a1','2026-08-10','late_entry',-99,'production');

-- ---------------------------------------------------------------------------
-- Utilitário de asserção
-- ---------------------------------------------------------------------------
create or replace function pg_temp.assert_eq(rotulo text, obtido bigint, esperado bigint)
returns void language plpgsql as $$
begin
  if obtido is distinct from esperado then
    raise exception 'FALHA [%]: esperado %, obtido %', rotulo, esperado, obtido;
  end if;
  raise notice '  ok  % (%)', rotulo, obtido;
end $$;

-- ---------------------------------------------------------------------------
\echo '--- Owner do tenant A'
-- ---------------------------------------------------------------------------
set local role authenticated;
set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';

do $$ begin
  perform pg_temp.assert_eq('owner A vê 2 colaboradores (só do tenant A)',
    (select count(*) from public.vw_employee), 2);
  perform pg_temp.assert_eq('owner A vê 2 unidades',
    (select count(*) from public.vw_unit), 2);
  perform pg_temp.assert_eq('owner A vê 2 desvios em produção (sombra fora da view)',
    (select count(*) from public.vw_deviation_event), 2);
  perform pg_temp.assert_eq('owner A lê PII do seu tenant',
    (select count(*) from app.employee_pii), 1);
  perform pg_temp.assert_eq('KPI do período confere',
    (select eventos from public.fn_kpi_period('2026-08-01','2026-08-31')), 2);
  perform pg_temp.assert_eq('owner A vê os 2 gestores dele',
    (select count(*) from app.manager), 2);
  perform pg_temp.assert_eq('e o ranking por gestor separa os dois',
    (select count(*) from public.fn_ranking_by_manager('2026-08-01','2026-08-31')), 2);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- Owner do tenant B (não pode ver NADA de A)'
-- ---------------------------------------------------------------------------
set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';

do $$ begin
  perform pg_temp.assert_eq('owner B vê só o próprio employee',
    (select count(*) from public.vw_employee), 1);
  perform pg_temp.assert_eq('owner B não vê employee de A',
    (select count(*) from public.vw_employee where name like 'Colab A%'), 0);
  perform pg_temp.assert_eq('owner B não vê desvio de A',
    (select count(*) from public.vw_deviation_event where minutes <> -99), 0);
  perform pg_temp.assert_eq('owner B não vê gestor de A',
    (select count(*) from app.manager where tenant_id <> 'bbbbbbbb-0000-0000-0000-000000000002'), 0);
  perform pg_temp.assert_eq('owner B não lê PII de A',
    (select count(*) from app.employee_pii where rg = 'MG-1'), 0);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- Supervisor de unit (tenant A, escopo só em A Centro)'
-- ---------------------------------------------------------------------------
set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';

do $$ begin
  perform pg_temp.assert_eq('supervisor vê só a unit dele',
    (select count(*) from public.vw_unit), 1);
  perform pg_temp.assert_eq('supervisor vê só o employee da unit dele',
    (select count(*) from public.vw_employee), 1);
  perform pg_temp.assert_eq('supervisor não vê desvio da unit A Norte',
    (select count(*) from public.vw_deviation_event where unit_name = 'A Norte'), 0);
  perform pg_temp.assert_eq('supervisor NÃO lê PII (ver unit não basta)',
    (select count(*) from app.employee_pii), 0);
  perform pg_temp.assert_eq('supervisor NÃO lê remuneração',
    (select count(*) from app.employee_compensation), 0);
  perform pg_temp.assert_eq('supervisor não vê evento em mode sombra',
    (select count(*) from app.deviation_event where mode = 'shadow'), 0);
  -- A policy do gestor tem o mesmo recorte da de unidade: ver o gestor é ver
  -- quem responde a ele. Sem isso, a chefia das outras unidades vazaria por uma
  -- tabela de dimensão, que é onde ninguém procura vazamento.
  perform pg_temp.assert_eq('supervisor vê só o gestor de quem ele enxerga',
    (select count(*) from app.manager), 1);
  perform pg_temp.assert_eq('e o ranking por gestor devolve só a linha dele',
    (select count(*) from public.fn_ranking_by_manager('2026-08-01','2026-08-31')), 1);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- DP (tenant A): lê PII, não lê saúde'
-- ---------------------------------------------------------------------------
set local request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';

do $$ begin
  perform pg_temp.assert_eq('DP lê PII',
    (select count(*) from app.employee_pii), 1);
  perform pg_temp.assert_eq('DP NÃO lê exame ocupacional (domínio saúde)',
    (select count(*) from app.occupational_exam), 0);
  perform pg_temp.assert_eq('DP vê os 2 colaboradores do tenant',
    (select count(*) from public.vw_employee), 2);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- Usuário autenticado sem vínculo com nenhum tenant'
-- ---------------------------------------------------------------------------
set local request.jwt.claim.sub = '99999999-9999-9999-9999-999999999999';

do $$ begin
  perform pg_temp.assert_eq('usuário sem tenant não vê employee',
    (select count(*) from public.vw_employee), 0);
  perform pg_temp.assert_eq('usuário sem tenant não vê desvio',
    (select count(*) from public.vw_deviation_event), 0);
  perform pg_temp.assert_eq('usuário sem tenant não vê unit',
    (select count(*) from public.vw_unit), 0);
end $$;

reset role;

\echo ''
\echo '================================================'
\echo ' ISOLAMENTO MULTI-TENANT: TODOS OS TESTES OK'
\echo '================================================'

rollback;
