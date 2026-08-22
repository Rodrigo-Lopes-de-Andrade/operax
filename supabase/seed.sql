-- ============================================================================
-- OperaX — SEED DE DESENVOLVIMENTO LOCAL
-- ----------------------------------------------------------------------------
-- Carregado por `supabase db reset` (config.toml, [db.seed]). NUNCA roda em
-- `db push`, portanto nunca chega a produção.
--
-- Existe porque o dashboard lê `app.deviation_event` em mode='production' e o
-- motor de detecção ainda não foi escrito: sem este arquivo, todas as views e
-- RPCs devolvem zero linhas e a tela só exercita o estado vazio.
--
-- Três decisões que valem a leitura:
--
--  (a) TENANT PRÓPRIO. Tudo nasce sob o tenant 'operax-dev', não sob
--      'kastro-park'. Dado sintético e dado de cliente nunca compartilham
--      chave — nem localmente, onde a confusão custa barato e ensina errado.
--
--  (b) SEM DOCUMENTO DE IDENTIDADE. Nenhum cpf, rg ou pis, nem em fixture
--      (handoff de design). `app.employee_pii` não recebe uma linha sequer.
--
--  (c) DETERMINÍSTICO. Todo id vem de md5(semente), todo sorteio vem do mesmo
--      hash. Rodar duas vezes não duplica nada e o print de ontem continua
--      batendo com a tela de hoje.
--
-- Reproduz de propósito duas patologias do cliente real, porque tela que só
-- conhece o caso feliz mente: ~26% dos colaboradores com departamento de outra
-- empresa (por isso a agregação é employee -> company) e escala 12x36 com
-- confidence abaixo de 80 (por isso `expected_workday.confidence` existe).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Trava: banco com desvio de outro tenant não é banco de desenvolvimento.
-- ---------------------------------------------------------------------------
do $$
declare n bigint;
begin
  select count(*) into n
  from app.deviation_event d
  join app.tenant t on t.id = d.tenant_id
  where t.slug <> 'operax-dev';

  if n > 0 then
    raise exception
      'seed de desenvolvimento recusado: % desvio(s) de outro tenant neste banco', n;
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- Tenant, matriz de sensibilidade e usuários
-- ---------------------------------------------------------------------------
insert into app.tenant (id, slug, name) values
  ('dede0000-0000-0000-0000-000000000001', 'operax-dev', 'OperaX · Desenvolvimento')
on conflict (id) do nothing;

insert into app.domain_permission (tenant_id, role, domain, allowed)
select t.id, p.role, d.domain,
       case
         when p.role = 'owner'      then true
         when p.role = 'personnel'  then d.domain in ('pii','compensation','disciplinary')
         when p.role = 'hr'         then d.domain in ('pii','health','disciplinary')
         when p.role = 'executive'  then d.domain in ('compensation')
         when p.role = 'accounting' then d.domain in ('compensation')
         else false
       end
from app.tenant t
cross join (select unnest(enum_range(null::app.user_role))        as role)   p
cross join (select unnest(enum_range(null::app.sensitive_domain)) as domain) d
where t.slug = 'operax-dev'
on conflict (tenant_id, role, domain) do nothing;

-- Senha única para todos: operax-dev. Vale só no stack local.
insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
  raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
  confirmation_token, email_change, email_change_token_new, recovery_token
)
select '00000000-0000-0000-0000-000000000000',
       u.id, 'authenticated', 'authenticated', u.email,
       extensions.crypt('operax-dev', extensions.gen_salt('bf')), now(),
       '{"provider":"email","providers":["email"]}'::jsonb,
       jsonb_build_object('name', u.nome),
       now(), now(), '', '', '', ''
from (values
  ('dede0000-0000-0000-0000-0000000000f1'::uuid, 'owner@operax.dev',      'Dev Owner'),
  ('dede0000-0000-0000-0000-0000000000f2'::uuid, 'dp@operax.dev',         'Dev Departamento Pessoal'),
  ('dede0000-0000-0000-0000-0000000000f3'::uuid, 'supervisor@operax.dev', 'Dev Supervisor Norte'),
  ('dede0000-0000-0000-0000-0000000000f4'::uuid, 'consulta@operax.dev',   'Dev Consulta')
) as u(id, email, nome)
on conflict (id) do nothing;

insert into auth.identities (
  id, user_id, provider_id, identity_data, provider,
  last_sign_in_at, created_at, updated_at
)
select gen_random_uuid(), u.id, u.id::text,
       jsonb_build_object('sub', u.id::text, 'email', u.email, 'email_verified', true),
       'email', now(), now(), now()
from auth.users u
where u.email like '%@operax.dev'
on conflict do nothing;

insert into app.tenant_member (tenant_id, user_id, role) values
  ('dede0000-0000-0000-0000-000000000001', 'dede0000-0000-0000-0000-0000000000f1', 'owner'),
  ('dede0000-0000-0000-0000-000000000001', 'dede0000-0000-0000-0000-0000000000f2', 'personnel'),
  ('dede0000-0000-0000-0000-000000000001', 'dede0000-0000-0000-0000-0000000000f3', 'unit_supervisor'),
  ('dede0000-0000-0000-0000-000000000001', 'dede0000-0000-0000-0000-0000000000f4', 'viewer')
on conflict (tenant_id, user_id) do nothing;

-- ---------------------------------------------------------------------------
-- Empresas e unidades
-- ---------------------------------------------------------------------------
insert into app.company (id, tenant_id, cnpj, legal_name, trade_name, secullum_company_id) values
  ('dede0000-0000-0000-0000-0000000000e1', 'dede0000-0000-0000-0000-000000000001', '11222333000181', 'Estacionamentos Dev Um LTDA',  'Dev Um',  1),
  ('dede0000-0000-0000-0000-0000000000e2', 'dede0000-0000-0000-0000-000000000001', '11222333000262', 'Estacionamentos Dev Dois LTDA', 'Dev Dois', 2)
on conflict (id) do nothing;

insert into app.unit (id, tenant_id, company_id, code, name, address) values
  ('dede0000-0000-0000-0000-0000000000a1', 'dede0000-0000-0000-0000-000000000001', 'dede0000-0000-0000-0000-0000000000e1', 'DEV-NORTE',   'Shopping Norte',  'Av. Dev, 100'),
  ('dede0000-0000-0000-0000-0000000000a2', 'dede0000-0000-0000-0000-000000000001', 'dede0000-0000-0000-0000-0000000000e1', 'DEV-AERO',    'Aeroporto',       'Av. Dev, 200'),
  ('dede0000-0000-0000-0000-0000000000a3', 'dede0000-0000-0000-0000-000000000001', 'dede0000-0000-0000-0000-0000000000e1', 'DEV-CENTRO',  'Centro',          'Av. Dev, 300'),
  ('dede0000-0000-0000-0000-0000000000a4', 'dede0000-0000-0000-0000-000000000001', 'dede0000-0000-0000-0000-0000000000e1', 'DEV-SUL',     'Shopping Sul',    'Av. Dev, 400'),
  ('dede0000-0000-0000-0000-0000000000a5', 'dede0000-0000-0000-0000-000000000001', 'dede0000-0000-0000-0000-0000000000e2', 'DEV-HOSP',    'Hospital',        'Av. Dev, 500'),
  ('dede0000-0000-0000-0000-0000000000a6', 'dede0000-0000-0000-0000-000000000001', 'dede0000-0000-0000-0000-0000000000e2', 'DEV-RODO',    'Rodoviária',      'Av. Dev, 600')
on conflict (id) do nothing;

-- O supervisor enxerga uma unidade só. É o escopo que a tela precisa provar.
insert into app.user_scope (id, tenant_id, user_id, unit_id) values
  ('dede0000-0000-0000-0000-0000000000b1', 'dede0000-0000-0000-0000-000000000001',
   'dede0000-0000-0000-0000-0000000000f3', 'dede0000-0000-0000-0000-0000000000a1')
on conflict (id) do nothing;

insert into app.department (id, tenant_id, company_id, name, secullum_department_id)
select md5('operax-dev-department-' || n)::uuid,
       'dede0000-0000-0000-0000-000000000001',
       case when n <= 4 then 'dede0000-0000-0000-0000-0000000000e1'
                        else 'dede0000-0000-0000-0000-0000000000e2' end::uuid,
       (array['Operação Norte','Operação Aeroporto','Operação Centro',
              'Operação Sul','Operação Hospital','Administrativo'])[n],
       100 + n
from generate_series(1, 6) n
on conflict (id) do nothing;

insert into app.unit_secullum_map (tenant_id, secullum_department_id, unit_id, validated_at)
select 'dede0000-0000-0000-0000-000000000001', 100 + n,
       (array['dede0000-0000-0000-0000-0000000000a1','dede0000-0000-0000-0000-0000000000a2',
              'dede0000-0000-0000-0000-0000000000a3','dede0000-0000-0000-0000-0000000000a4',
              'dede0000-0000-0000-0000-0000000000a5','dede0000-0000-0000-0000-0000000000a6'])[n]::uuid,
       case when n <= 4 then now() else null end
from generate_series(1, 6) n
on conflict (tenant_id, secullum_department_id) do nothing;

-- ---------------------------------------------------------------------------
-- Colaboradores — 42, seis unidades, sem uma linha de employee_pii
-- ---------------------------------------------------------------------------
insert into app.employee (
  id, tenant_id, company_id, unit_id, department_id, secullum_employee_id,
  registration_number, name, cargo, employment_type, hired_on, status
)
select md5('operax-dev-employee-' || n)::uuid,
       'dede0000-0000-0000-0000-000000000001',
       case when un <= 4 then 'dede0000-0000-0000-0000-0000000000e1'
                         else 'dede0000-0000-0000-0000-0000000000e2' end::uuid,
       (array['dede0000-0000-0000-0000-0000000000a1','dede0000-0000-0000-0000-0000000000a2',
              'dede0000-0000-0000-0000-0000000000a3','dede0000-0000-0000-0000-0000000000a4',
              'dede0000-0000-0000-0000-0000000000a5','dede0000-0000-0000-0000-0000000000a6'])[un]::uuid,
       -- A cada quatro colaboradores, o departamento é de OUTRA empresa. É a
       -- divergência de 26% da Kastro Park, e a razão de a agregação nunca
       -- passar por departamento -> empresa.
       md5('operax-dev-department-' ||
           case when n % 4 = 0 then (case when un <= 4 then 6 else 1 end) else un end)::uuid,
       1000 + n,
       lpad(n::text, 5, '0'),
       (array['Ana','Bruno','Carla','Diego','Eliane','Fábio','Gisele','Heitor','Ivone','João',
              'Karina','Lucas','Marta','Nelson','Olívia','Paulo','Queila','Rafael','Sônia','Tiago',
              'Úrsula','Vitor','Wanda','Xavier','Yara','Zeca','Adriana','Bento','Célia','Danilo',
              'Elisa','Fernando','Gabriela','Hugo','Isabel','Jorge','Luana','Marcelo','Nádia','Otávio',
              'Priscila','Renato'])[n]
       || ' ' ||
       (array['Almeida','Barbosa','Cardoso','Duarte','Esteves','Ferreira','Gomes','Henriques',
              'Ibrahim','Jardim','Klein','Lopes','Machado','Nogueira','Oliveira','Pacheco',
              'Quintela','Ramos','Siqueira','Tavares','Uchôa','Vieira'])[1 + (n * 7) % 22],
       case when n <= 6 then 'Supervisor de pátio'
            else (array['Operador de estacionamento','Manobrista','Controlador de acesso',
                        'Auxiliar administrativo','Zelador'])[1 + (n % 5)] end,
       'clt',
       current_date - (200 + n * 13),
       case n when 41 then 'vacation' when 42 then 'afastado' else 'active' end
from generate_series(1, 42) n
cross join lateral (select ((n - 1) % 6) + 1 as un) u
on conflict (id) do nothing;

-- Gestor = o supervisor da própria unidade (colaboradores 1..6).
update app.employee c
   set manager_employee_id = md5('operax-dev-employee-' || g.n)::uuid
  from generate_series(1, 6) g(n)
 where c.tenant_id = 'dede0000-0000-0000-0000-000000000001'
   and c.unit_id = (array['dede0000-0000-0000-0000-0000000000a1','dede0000-0000-0000-0000-0000000000a2',
                          'dede0000-0000-0000-0000-0000000000a3','dede0000-0000-0000-0000-0000000000a4',
                          'dede0000-0000-0000-0000-0000000000a5','dede0000-0000-0000-0000-0000000000a6'])[g.n]::uuid
   and c.id <> md5('operax-dev-employee-' || g.n)::uuid
   and c.manager_employee_id is distinct from md5('operax-dev-employee-' || g.n)::uuid;

-- ---------------------------------------------------------------------------
-- Política de tipos de desvio do tenant
-- ---------------------------------------------------------------------------
insert into app.deviation_type_config (tenant_id, code, active, counts_as_deviation, triggers_alert)
select 'dede0000-0000-0000-0000-000000000001', dt.code, true,
       -- Marcação fora do perímetro é informativa neste tenant: aparece na
       -- consulta individual, não infla KPI nem ranking.
       dt.code <> 'outside_perimeter',
       false
from app.deviation_type dt
on conflict (tenant_id, code) do nothing;

-- ---------------------------------------------------------------------------
-- Jornada esperada — 45 dias. Um terço em 12x36, com confidence abaixo de 80,
-- porque a escala inferida do Horario do Secullum não chega a 100 e a tela
-- precisa saber diferenciar "desvio" de "escala não confirmada".
-- ---------------------------------------------------------------------------
insert into app.expected_workday (
  tenant_id, employee_id, reference_date, day_type,
  expected_entry, expected_exit, expected_break_minutes, workload_minutes,
  tolerance_extra_minutes, tolerance_absence_minutes, source, confidence
)
select c.tenant_id, c.id, d.reference_date,
       case when p.plantao then (case when (d.reference_date - date '2026-01-01') % 2 = 0 then 'work' else 'day_off' end)
            when extract(dow from d.reference_date) = 0 then 'day_off'
            else 'work' end,
       case when p.plantao then time '07:00' else time '08:00' end,
       case when p.plantao then time '19:00' else time '17:00' end,
       case when p.plantao then 60 else 60 end,
       case when p.plantao then 720 else 480 end,
       10, 10,
       case when p.plantao then 'inferred' else 'secullum_schedule' end,
       case when p.plantao then 65 else 100 end
from app.employee c
cross join lateral (select (get_byte(decode(md5(c.id::text), 'hex'), 0) % 3 = 0) as plantao) p
cross join lateral (select generate_series(current_date - 44, current_date, interval '1 day')::date as reference_date) d
where c.tenant_id = 'dede0000-0000-0000-0000-000000000001'
on conflict (employee_id, reference_date) do nothing;

-- ---------------------------------------------------------------------------
-- Integração e execuções de sincronização — é daqui que sai a idade do dado
-- ---------------------------------------------------------------------------
insert into app.integration (id, tenant_id, provider, alias, config, active) values
  ('dede0000-0000-0000-0000-0000000000c1', 'dede0000-0000-0000-0000-000000000001',
   'secullum', 'principal',
   '{"base_url":"https://exemplo.invalid/secullum","timezone":"America/Sao_Paulo"}'::jsonb, true)
on conflict (id) do nothing;

-- Cadência de 30 min. A última leitura completa fica 25 min atrás, dentro do
-- limiar de 45 — o indicador do cabeçalho nasce "atualizado", não "atrasado".
insert into app.sync_run (
  id, tenant_id, integration_id, entity, started_at, finished_at, status,
  records_read, records_written
)
select md5('operax-dev-sync-' || e.entity || '-' || k)::uuid,
       'dede0000-0000-0000-0000-000000000001',
       'dede0000-0000-0000-0000-0000000000c1',
       e.entity,
       now() - make_interval(mins => 25 + k * 30 + 3),
       now() - make_interval(mins => 25 + k * 30),
       case when k = 3 and e.entity = 'Batida' then 'failed' else 'completed' end,
       e.lidos, e.lidos
from (values ('Funcionario', 42), ('Batida', 1890)) as e(entity, lidos)
cross join generate_series(0, 5) k
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- Execuções do motor e ciclos de relatório
-- ---------------------------------------------------------------------------
insert into app.detection_run (
  id, tenant_id, mode, period_start, period_end, started_at, finished_at,
  status, engine_version
) values
  (md5('operax-dev-run-production')::uuid, 'dede0000-0000-0000-0000-000000000001',
   'production', current_date - 44, current_date, now() - interval '25 minutes',
   now() - interval '23 minutes', 'completed', 'seed-dev'),
  (md5('operax-dev-run-shadow')::uuid, 'dede0000-0000-0000-0000-000000000001',
   'shadow', current_date - 1, current_date, now() - interval '20 minutes',
   now() - interval '19 minutes', 'completed', 'seed-dev')
on conflict (id) do nothing;

-- Um ciclo fechado por unidade cobrindo tudo que tem mais de sete dias. O que
-- é mais recente fica sem ciclo — é o número de "pendentes" do painel.
insert into app.report_cycle (
  id, tenant_id, unit_id, period_start, period_end, generated_at, sent_at,
  channel, status
)
select md5('operax-dev-cycle-' || u.id::text)::uuid, u.tenant_id, u.id,
       current_date - 44, current_date - 8,
       (current_date - 7 + time '07:30')::timestamptz,
       (current_date - 7 + time '07:35')::timestamptz,
       'whatsapp', 'sent'
from app.unit u
where u.tenant_id = 'dede0000-0000-0000-0000-000000000001'
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- Desvios. Um por colaborador/dia no máximo, sorteado do hash do par — mesmo
-- banco, mesma tela, todo dia.
-- ---------------------------------------------------------------------------
insert into app.deviation_event (
  id, tenant_id, employee_id, company_id, unit_id, reference_date, type, minutes,
  expected_time, actual_time, status, mode, run_id, report_cycle_id, detected_at
)
select md5('operax-dev-event-' || c.id::text || '|' || d.reference_date::text)::uuid,
       c.tenant_id, c.id, c.company_id, c.unit_id, d.reference_date,
       s.type, s.minutes,
       s.expected_time,
       s.actual_time,
       -- Uma fatia pequena já foi tratada: comprova que revogado e justificado
       -- somem da view sem que ninguém tenha apagado linha (regra 6).
       case when h.b2 % 25 = 0 then 'revoked'
            when h.b2 % 25 = 1 then 'justified'
            else 'active' end,
       'production',
       md5('operax-dev-run-production')::uuid,
       case when d.reference_date <= current_date - 8
            then md5('operax-dev-cycle-' || c.unit_id::text)::uuid end,
       (d.reference_date + time '09:00' + make_interval(mins => h.b3 % 400))::timestamptz
from app.employee c
cross join lateral (select generate_series(current_date - 44, current_date, interval '1 day')::date as reference_date) d
cross join lateral (select decode(md5('operax-dev-event-' || c.id::text || '|' || d.reference_date::text), 'hex') as bytes) k
cross join lateral (
  select get_byte(k.bytes, 0) as b0, get_byte(k.bytes, 1) as b1,
         get_byte(k.bytes, 2) as b2, get_byte(k.bytes, 3) as b3
) h
cross join lateral (
  select case
           when h.b0 % 100 between  0 and  8 then 'late_entry'
           when h.b0 % 100 between  9 and 14 then 'early_exit'
           when h.b0 % 100 between 15 and 20 then 'late_exit'
           when h.b0 % 100 between 21 and 23 then 'break_exceeded'
           when h.b0 % 100 = 24              then 'no_punches'
           when h.b0 % 100 = 25              then 'incomplete_punches'
           when h.b0 % 100 = 26              then 'punch_on_day_off'
         end as type
) t
cross join lateral (
  select t.type,
         -- Assinado: + excedente, - faltante. Nunca chamar de hora extra.
         case t.type
           when 'late_entry'         then -(6  + h.b1 % 25)
           when 'early_exit'         then -(5  + h.b1 % 40)
           when 'late_exit'          then  (8  + h.b1 % 52)
           when 'break_exceeded'     then -(10 + h.b1 % 26)
           when 'no_punches'         then -480
           when 'incomplete_punches' then 0
           when 'punch_on_day_off'   then  (60 + h.b1 % 180)
         end as minutes,
         case t.type
           when 'late_entry'         then time '08:00'
           when 'early_exit'         then time '17:00'
           when 'late_exit'          then time '17:00'
           when 'break_exceeded'     then time '13:00'
           when 'no_punches'         then time '08:00'
           when 'incomplete_punches' then time '17:00'
         end as expected_time,
         case t.type
           when 'late_entry'         then time '08:00' + make_interval(mins => 6  + h.b1 % 25)
           when 'early_exit'         then time '17:00' - make_interval(mins => 5  + h.b1 % 40)
           when 'late_exit'          then time '17:00' + make_interval(mins => 8  + h.b1 % 52)
           when 'break_exceeded'     then time '13:00' + make_interval(mins => 10 + h.b1 % 26)
           when 'punch_on_day_off'   then time '09:00'
         end as actual_time
) s
where c.tenant_id = 'dede0000-0000-0000-0000-000000000001'
  and c.status = 'active'
  and t.type is not null
on conflict (id) do nothing;

-- Mode sombra: existe no banco, não existe em nenhuma view. É o que a onda de
-- calibragem do motor vai comparar contra a apuração do Secullum.
insert into app.deviation_event (
  id, tenant_id, employee_id, company_id, unit_id, reference_date, type, minutes,
  expected_time, actual_time, status, mode, run_id, detected_at
)
select md5('operax-dev-shadow-' || c.id::text)::uuid,
       c.tenant_id, c.id, c.company_id, c.unit_id, current_date,
       'late_entry', -(11 + get_byte(decode(md5(c.id::text), 'hex'), 4) % 20),
       time '08:00', time '08:15', 'active', 'shadow',
       md5('operax-dev-run-shadow')::uuid, now() - interval '19 minutes'
from app.employee c
where c.tenant_id = 'dede0000-0000-0000-0000-000000000001'
  and c.status = 'active'
  and get_byte(decode(md5(c.id::text), 'hex'), 5) % 4 = 0
on conflict (id) do nothing;

update app.report_cycle rc
   set total_events = x.n
  from (select report_cycle_id, count(*) as n
          from app.deviation_event
         where report_cycle_id is not null
         group by report_cycle_id) x
 where rc.id = x.report_cycle_id
   and rc.total_events is distinct from x.n;

update app.detection_run dr
   set events_detected  = x.n,
       events_published = x.publicados
  from (select run_id, count(*) as n,
               count(*) filter (where mode = 'production') as publicados
          from app.deviation_event
         where run_id is not null
         group by run_id) x
 where dr.id = x.run_id
   and dr.events_detected is distinct from x.n;

-- ---------------------------------------------------------------------------
-- Prova: o seed sustenta o que promete, ou falha alto.
-- ---------------------------------------------------------------------------
do $$
declare
  v_tenant   constant uuid := 'dede0000-0000-0000-0000-000000000001';
  v_eventos  bigint;
  v_sombra   bigint;
  v_pendentes bigint;
  v_divergentes bigint;
  v_pii      bigint;
begin
  select count(*) into v_eventos
    from app.deviation_event
   where tenant_id = v_tenant and mode = 'production' and status = 'active';
  if v_eventos < 200 then
    raise exception 'seed gerou só % desvio(s) em produção — a tela não exercita ranking nem tendência', v_eventos;
  end if;

  select count(*) into v_sombra
    from app.deviation_event where tenant_id = v_tenant and mode = 'shadow';
  if v_sombra = 0 then
    raise exception 'seed sem evento em sombra — o estado que o dashboard precisa ignorar não existe';
  end if;

  select count(*) into v_pendentes
    from app.deviation_event
   where tenant_id = v_tenant and mode = 'production' and status = 'active'
     and report_cycle_id is null;
  if v_pendentes = 0 then
    raise exception 'seed sem pendente de ciclo — o terceiro KPI do painel nasce zerado';
  end if;

  -- A patologia do cliente: departamento apontando para outra empresa.
  select count(*) into v_divergentes
    from app.employee c
    join app.department dep on dep.id = c.department_id
   where c.tenant_id = v_tenant and dep.company_id <> c.company_id;
  if v_divergentes = 0 then
    raise exception 'seed sem divergência empresa x departamento — a regra 5 fica sem caso de teste';
  end if;

  select count(*) into v_pii from app.employee_pii where tenant_id = v_tenant;
  if v_pii > 0 then
    raise exception 'seed de desenvolvimento gravou % linha(s) de PII', v_pii;
  end if;

  raise notice 'seed operax-dev: % desvios em produção, % pendentes de ciclo, % em sombra, % vínculos divergentes',
    v_eventos, v_pendentes, v_sombra, v_divergentes;
end $$;
