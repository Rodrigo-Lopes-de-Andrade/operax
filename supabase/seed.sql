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
--  (a) TENANT PRÓPRIO. Tudo nasce sob o tenant 'fastpark-dev', não sob
--      'fastpark'. Dado sintético e dado de cliente nunca compartilham
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
  where t.slug <> 'fastpark-dev';

  if n > 0 then
    raise exception
      'seed de desenvolvimento recusado: % desvio(s) de outro tenant neste banco', n;
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- Tenant, matriz de sensibilidade e usuários
-- ---------------------------------------------------------------------------
insert into app.tenant (id, slug, name) values
  ('dede0000-0000-0000-0000-000000000001', 'fastpark-dev', 'FastPark · Desenvolvimento')
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
where t.slug = 'fastpark-dev'
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
  ('dede0000-0000-0000-0000-0000000000f1'::uuid, 'owner@fastpark.dev',      'Dev Owner'),
  ('dede0000-0000-0000-0000-0000000000f2'::uuid, 'dp@fastpark.dev',         'Dev Departamento Pessoal'),
  ('dede0000-0000-0000-0000-0000000000f3'::uuid, 'supervisor@fastpark.dev', 'Dev Supervisor Norte'),
  ('dede0000-0000-0000-0000-0000000000f4'::uuid, 'consulta@fastpark.dev',   'Dev Consulta'),
  -- Le a area de RH e nao escreve nela. Existe porque "leitura sem escrita" e um
  -- estado real do produto (executive alcanca remuneracao e nao e is_admin) e,
  -- sem um usuario assim, o gate do R3 nao teria como provar que o botao de
  -- editar some.
  ('dede0000-0000-0000-0000-0000000000f5'::uuid, 'diretoria@fastpark.dev',  'Dev Diretoria')
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
where u.email like '%@fastpark.dev'
on conflict do nothing;

insert into app.tenant_member (tenant_id, user_id, role) values
  ('dede0000-0000-0000-0000-000000000001', 'dede0000-0000-0000-0000-0000000000f1', 'owner'),
  ('dede0000-0000-0000-0000-000000000001', 'dede0000-0000-0000-0000-0000000000f2', 'personnel'),
  ('dede0000-0000-0000-0000-000000000001', 'dede0000-0000-0000-0000-0000000000f3', 'unit_supervisor'),
  ('dede0000-0000-0000-0000-000000000001', 'dede0000-0000-0000-0000-0000000000f4', 'viewer'),
  ('dede0000-0000-0000-0000-000000000001', 'dede0000-0000-0000-0000-0000000000f5', 'executive')
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
select md5('operax-dev-event-' || c.id::text || '|' || w.reference_date::text)::uuid,
       c.tenant_id, c.id, c.company_id, c.unit_id, w.reference_date,
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
       case when w.reference_date <= current_date - 8
            then md5('operax-dev-cycle-' || c.unit_id::text)::uuid end,
       -- A detecção vem DEPOIS do fato, nunca antes. A leitura roda a cada 30
       -- minutos, então o indício nasce entre 5 e 39 minutos do horário
       -- observado — que é a mesma promessa que a tela faz ao gestor.
       -- `at time zone` porque o painel lê no fuso do cliente: uma âncora naive
       -- gravada em UTC apareceria três horas antes do que aconteceu, e o
       -- monitor mostraria "detectado 06:02" para um intervalo das 13:00.
       ((w.reference_date + coalesce(s.actual_time, s.expected_time, time '09:00'))
          at time zone 'America/Sao_Paulo')
         + make_interval(mins => 5 + h.b3 % 35)
from app.employee c
-- O sorteio sai da jornada esperada, não de um calendário paralelo: atraso de
-- entrada em dia de folga é contradição na tela, e tela que se contradiz não
-- ensina ninguém a confiar no número.
join app.expected_workday w
  on w.employee_id = c.id
 and w.reference_date between current_date - 44 and current_date
cross join lateral (select decode(md5('operax-dev-event-' || c.id::text || '|' || w.reference_date::text), 'hex') as bytes) k
cross join lateral (
  select get_byte(k.bytes, 0) as b0, get_byte(k.bytes, 1) as b1,
         get_byte(k.bytes, 2) as b2, get_byte(k.bytes, 3) as b3
) h
cross join lateral (
  select case
           when w.day_type = 'work' then
             case
               when h.b0 % 100 between  0 and  8 then 'late_entry'
               when h.b0 % 100 between  9 and 14 then 'early_exit'
               when h.b0 % 100 between 15 and 20 then 'late_exit'
               when h.b0 % 100 between 21 and 23 then 'break_exceeded'
               when h.b0 % 100 = 24              then 'no_punches'
               when h.b0 % 100 = 25              then 'incomplete_punches'
             end
           -- Em dia sem jornada prevista o único desvio possível é ter batido.
           when w.day_type = 'day_off' and h.b0 % 100 < 5 then 'punch_on_day_off'
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
           when 'no_punches'         then -coalesce(w.workload_minutes, 480)
           when 'incomplete_punches' then 0
           when 'punch_on_day_off'   then  (60 + h.b1 % 180)
         end as minutes,
         case t.type
           when 'late_entry'         then w.expected_entry
           when 'early_exit'         then w.expected_exit
           when 'late_exit'          then w.expected_exit
           when 'break_exceeded'     then time '13:00'
           when 'no_punches'         then w.expected_entry
           when 'incomplete_punches' then w.expected_exit
         end as expected_time,
         case t.type
           when 'late_entry'         then w.expected_entry + make_interval(mins => 6  + h.b1 % 25)
           when 'early_exit'         then w.expected_exit  - make_interval(mins => 5  + h.b1 % 40)
           when 'late_exit'          then w.expected_exit  + make_interval(mins => 8  + h.b1 % 52)
           when 'break_exceeded'     then time '13:00' + make_interval(mins => 10 + h.b1 % 26)
           when 'punch_on_day_off'   then time '09:00' + make_interval(mins => h.b1 % 120)
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
join app.expected_workday w
  on w.employee_id = c.id and w.reference_date = current_date and w.day_type = 'work'
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
-- Domínio sensível — existe para que a tela possa provar que NÃO aparece
-- ----------------------------------------------------------------------------
-- Um teste que diz "o supervisor não vê remuneração" contra um bloco vazio não
-- prova nada: ele passaria com a feature quebrada. Por isso remuneração,
-- documento e exame nascem povoados.
--
-- Exame ocupacional guarda só aptidão e validade. Não existe diagnóstico, CID
-- nem descrição de restrição — nem coluna para isso (regra 10).
-- ---------------------------------------------------------------------------
insert into app.document_type (id, tenant_id, name, requires_expiry, expiry_alert_days, required, domain)
select md5('operax-dev-doctype-' || n)::uuid,
       'dede0000-0000-0000-0000-000000000001',
       (array['ASO','CNH','Certificado NR-35','Contrato de trabalho'])[n],
       n <= 3,
       (array[30, 45, 60, 30])[n],
       n in (1, 4),
       (array['health','pii','pii','pii'])[n]::app.sensitive_domain
from generate_series(1, 4) n
on conflict (tenant_id, name) do nothing;

insert into app.document (
  id, tenant_id, employee_id, type_id, storage_path, file_name,
  issued_on, valid_until, status
)
select md5('operax-dev-document-' || c.id::text || '-' || d.n)::uuid,
       c.tenant_id, c.id,
       md5('operax-dev-doctype-' || d.n)::uuid,
       c.id::text || '/' || d.n::text || '.pdf',
       (array['aso','cnh','nr35','contrato'])[d.n] || '-' || c.registration_number || '.pdf',
       current_date - (300 + h.b0 % 60),
       -- Vencimento espalhado de 20 dias atrás a 200 à frente: a view de
       -- vencimento precisa de caso em alerta, não só de caso tranquilo.
       case when d.n = 4 then null else current_date - 20 + (h.b1 % 220) end,
       'active'
from app.employee c
cross join generate_series(1, 4) d(n)
cross join lateral (
  select get_byte(decode(md5('operax-dev-document-' || c.id::text || '-' || d.n), 'hex'), 0) as b0,
         get_byte(decode(md5('operax-dev-document-' || c.id::text || '-' || d.n), 'hex'), 1) as b1,
         get_byte(decode(md5('operax-dev-document-' || c.id::text || '-' || d.n), 'hex'), 2) as b2
) h
where c.tenant_id = 'dede0000-0000-0000-0000-000000000001'
  and (d.n = 1 or h.b2 % 3 <> 0)
on conflict (id) do nothing;

insert into app.occupational_exam (
  id, tenant_id, employee_id, type, performed_on, valid_until, result, document_id
)
select md5('operax-dev-exam-' || c.id::text)::uuid,
       c.tenant_id, c.id,
       case when h.b0 % 7 = 0 then 'pre_employment' else 'periodic' end,
       current_date - (330 + h.b0 % 30),
       current_date + (h.b1 % 120) - 15,
       case when h.b2 % 11 = 0 then 'fit_with_restriction' else 'fit' end,
       md5('operax-dev-document-' || c.id::text || '-1')::uuid
from app.employee c
cross join lateral (
  select get_byte(decode(md5('operax-dev-exam-' || c.id::text), 'hex'), 0) as b0,
         get_byte(decode(md5('operax-dev-exam-' || c.id::text), 'hex'), 1) as b1,
         get_byte(decode(md5('operax-dev-exam-' || c.id::text), 'hex'), 2) as b2
) h
where c.tenant_id = 'dede0000-0000-0000-0000-000000000001'
on conflict (id) do nothing;

-- Admissão e um reajuste. `effective_to` da primeira faixa fecha na véspera da
-- segunda, que é o que faz "salário vigente" ser uma consulta e não um palpite.
--
-- O reajuste só existe se a data dele já chegou. Sem essa condição, quem foi
-- admitido há menos de um ano ficava com a faixa "em vigor" começando no mês que
-- vem — um salário vigente que ainda não vigora, e um beco sem saída: a tela
-- recusa vigência nova anterior à vigente e recusa vigência no futuro, então
-- essas pessoas nunca poderiam receber um reajuste.
insert into app.employee_compensation (
  id, tenant_id, employee_id, effective_from, effective_to, salary, reason, recorded_by
)
select md5('operax-dev-compensation-' || c.id::text || '-' || f.n)::uuid,
       c.tenant_id, c.id,
       case f.n when 1 then c.hired_on else c.hired_on + 365 end,
       case when f.n = 1 and c.hired_on + 365 <= current_date then c.hired_on + 364 end,
       case f.n when 1 then base else round(base * 1.08, 2) end,
       case f.n when 1 then 'Admissão' else 'Reajuste anual' end,
       'dede0000-0000-0000-0000-0000000000f2'
from app.employee c
cross join lateral (
  select 1600 + (get_byte(decode(md5('operax-dev-compensation-' || c.id::text), 'hex'), 0) % 18) * 100 as base
) b
cross join generate_series(1, 2) f(n)
where c.tenant_id = 'dede0000-0000-0000-0000-000000000001'
  and c.hired_on is not null
  and (f.n = 1 or c.hired_on + 365 <= current_date)
on conflict (id) do nothing;

-- Justificativa só onde o evento já foi tratado como justificado. Justificativa
-- solta, sem evento, seria um estado que o produto não produz.
insert into app.justification (
  id, tenant_id, deviation_event_id, employee_id, reference_date, text, source,
  author_user_id, author_name
)
select md5('operax-dev-justification-' || d.id::text)::uuid,
       d.tenant_id, d.id, d.employee_id, d.reference_date,
       (array['Trânsito parado na avenida de acesso.',
              'Atestado entregue ao departamento pessoal.',
              'Autorizado pelo gestor da unidade.',
              'Falha do relógio de ponto na entrada.'])[1 + get_byte(decode(md5(d.id::text), 'hex'), 0) % 4],
       'operax',
       'dede0000-0000-0000-0000-0000000000f3',
       'Dev Supervisor Norte'
from app.deviation_event d
where d.tenant_id = 'dede0000-0000-0000-0000-000000000001'
  and d.status = 'justified'
on conflict (id) do nothing;

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
  v_sensivel bigint;
  v_alerta   bigint;
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

  -- Sem bloco sensível povoado, o teste "o supervisor não vê remuneração"
  -- passaria com a funcionalidade quebrada.
  select count(*) into v_sensivel
    from app.employee_compensation where tenant_id = v_tenant;
  if v_sensivel = 0 then
    raise exception 'seed sem remuneração — o bloco que o supervisor não pode ver não existe';
  end if;

  select count(*) into v_alerta
    from app.document
   where tenant_id = v_tenant and status = 'active'
     and valid_until is not null and valid_until <= current_date + 30;
  if v_alerta = 0 then
    raise exception 'seed sem documento perto do vencimento — a view de vencimento nasce sem caso em alerta';
  end if;

  raise notice 'seed fastpark-dev: % desvios em produção, % pendentes de ciclo, % em sombra, % vínculos divergentes, % faixas de remuneração',
    v_eventos, v_pendentes, v_sombra, v_divergentes, v_sensivel;
end $$;
