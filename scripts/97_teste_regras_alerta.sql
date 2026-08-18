-- ============================================================================
-- OperaX — TESTE DAS REGRAS DE ALERTA E DE CADÊNCIA
-- ----------------------------------------------------------------------------
-- Duas garantias de produto que só valem se o banco recusar a violação:
--
--   A) Alerta de conteúdo individual não vai para grupo (risco trabalhista).
--   B) Alerta de ocorrência carrega o horário observado, nunca "agora"
--      (a cadência é de 30 min: a mensagem chega até 40 min depois do fato).
--
-- A regra (A) existia desde a migration 06 e nunca tinha sido testada.
--
-- Roda em transação revertida.
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/97_teste_regras_alerta.sql
-- ============================================================================

begin;

insert into auth.users (id, email) values
  ('7e000000-0000-0000-0000-000000000001', 'admin.alerta@teste');

insert into app.tenant (id, slug, name) values
  ('7ea70000-0000-0000-0000-0000000000a1', 'tenant-alerta', 'Cliente Alerta');

insert into app.tenant_member (tenant_id, user_id, role) values
  ('7ea70000-0000-0000-0000-0000000000a1', '7e000000-0000-0000-0000-000000000001', 'owner');

insert into app.company (id, tenant_id, legal_name) values
  ('7ea70000-0000-0000-0000-0000000000e1', '7ea70000-0000-0000-0000-0000000000a1', 'Empresa Alerta LTDA');

insert into app.unit (id, tenant_id, company_id, code, name) values
  ('7ea70000-0000-0000-0000-0000000000c1', '7ea70000-0000-0000-0000-0000000000a1',
   '7ea70000-0000-0000-0000-0000000000e1', 'ALERTA-1', 'Unidade Alerta');

insert into app.employee (id, tenant_id, company_id, unit_id, name) values
  ('7ea70000-0000-0000-0000-0000000000b1', '7ea70000-0000-0000-0000-0000000000a1',
   '7ea70000-0000-0000-0000-0000000000e1', '7ea70000-0000-0000-0000-0000000000c1', 'Colab Alerta');

-- Evento COM horário previsto e realizado: o contrato exige os dois no payload.
insert into app.deviation_event
  (id, tenant_id, employee_id, company_id, unit_id, reference_date, type,
   minutes, expected_time, actual_time)
values
  ('7ea70000-0000-0000-0000-0000000000d1', '7ea70000-0000-0000-0000-0000000000a1',
   '7ea70000-0000-0000-0000-0000000000b1', '7ea70000-0000-0000-0000-0000000000e1',
   '7ea70000-0000-0000-0000-0000000000c1', '2026-08-18', 'late_entry',
   -12, '08:00', '08:12');

-- Evento SEM horário realizado: exigir actual_time seria restrição falsa.
insert into app.deviation_event
  (id, tenant_id, employee_id, company_id, unit_id, reference_date, type, minutes)
values
  ('7ea70000-0000-0000-0000-0000000000d2', '7ea70000-0000-0000-0000-0000000000a1',
   '7ea70000-0000-0000-0000-0000000000b1', '7ea70000-0000-0000-0000-0000000000e1',
   '7ea70000-0000-0000-0000-0000000000c1', '2026-08-18', 'no_punches', -480);

insert into app.contact (id, tenant_id, name, type, whatsapp) values
  ('7ea70000-0000-0000-0000-00000000f001', '7ea70000-0000-0000-0000-0000000000a1',
   'Grupo Operação', 'whatsapp_group', '+5511999990000'),
  ('7ea70000-0000-0000-0000-00000000f002', '7ea70000-0000-0000-0000-0000000000a1',
   'Gestor da Unidade', 'person', '+5511999990001');

insert into app.alert_rule (id, tenant_id, name, content, channel) values
  ('7ea70000-0000-0000-0000-00000000e001', '7ea70000-0000-0000-0000-0000000000a1',
   'Atraso — nominal', 'individual', 'whatsapp'),
  ('7ea70000-0000-0000-0000-00000000e002', '7ea70000-0000-0000-0000-0000000000a1',
   'Resumo da unidade', 'aggregate', 'whatsapp');

-- ---------------------------------------------------------------------------
create or replace function pg_temp.deve_falhar(rotulo text, sql_text text)
returns void language plpgsql as $$
begin
  begin
    execute sql_text;
  exception when others then
    raise notice '  ok  % — recusado: %', rotulo, left(sqlerrm, 70);
    return;
  end;
  raise exception 'FALHA [%]: deveria ter sido recusado e passou', rotulo;
end $$;

create or replace function pg_temp.deve_passar(rotulo text, sql_text text)
returns void language plpgsql as $$
begin
  execute sql_text;
  raise notice '  ok  % — aceito', rotulo;
exception when others then
  if sqlerrm like 'FALHA%' then raise; end if;
  raise exception 'FALHA [%]: deveria ter passado e foi recusado: %', rotulo, sqlerrm;
end $$;

\echo '--- A) conteúdo individual nunca vai para grupo'
do $$ begin
  perform pg_temp.deve_falhar('regra individual com contato de grupo', $q$
    insert into app.alert_rule_target (rule_id, contact_id)
    values ('7ea70000-0000-0000-0000-00000000e001', '7ea70000-0000-0000-0000-00000000f001')
  $q$);
  perform pg_temp.deve_falhar('regra individual com destino função=grupo', $q$
    insert into app.alert_rule_target (rule_id, responsibility)
    values ('7ea70000-0000-0000-0000-00000000e001', 'group')
  $q$);
  perform pg_temp.deve_passar('regra individual com contato pessoa', $q$
    insert into app.alert_rule_target (rule_id, contact_id)
    values ('7ea70000-0000-0000-0000-00000000e001', '7ea70000-0000-0000-0000-00000000f002')
  $q$);
  perform pg_temp.deve_passar('regra agregada com grupo', $q$
    insert into app.alert_rule_target (rule_id, contact_id)
    values ('7ea70000-0000-0000-0000-00000000e002', '7ea70000-0000-0000-0000-00000000f001')
  $q$);
end $$;

\echo '--- B) alerta de ocorrência carrega o horário observado'
do $$ begin
  perform pg_temp.deve_falhar('payload sem reference_date', $q$
    insert into app.alert_queue (tenant_id, deviation_event_id, channel, destination,
                                 payload, idempotency_key)
    values ('7ea70000-0000-0000-0000-0000000000a1','7ea70000-0000-0000-0000-0000000000d1',
            'whatsapp','+5511999990001',
            '{"expected_time":"08:00","actual_time":"08:12"}'::jsonb,'k1')
  $q$);

  perform pg_temp.deve_falhar('payload sem actual_time num evento que tem', $q$
    insert into app.alert_queue (tenant_id, deviation_event_id, channel, destination,
                                 payload, idempotency_key)
    values ('7ea70000-0000-0000-0000-0000000000a1','7ea70000-0000-0000-0000-0000000000d1',
            'whatsapp','+5511999990001',
            '{"reference_date":"2026-08-18","expected_time":"08:00"}'::jsonb,'k2')
  $q$);

  perform pg_temp.deve_falhar('payload como string em vez de objeto', $q$
    insert into app.alert_queue (tenant_id, deviation_event_id, channel, destination,
                                 payload, idempotency_key)
    values ('7ea70000-0000-0000-0000-0000000000a1','7ea70000-0000-0000-0000-0000000000d1',
            'whatsapp','+5511999990001',
            '"Fulano esta atrasado agora"'::jsonb,'k3')
  $q$);

  perform pg_temp.deve_passar('payload completo', $q$
    insert into app.alert_queue (tenant_id, deviation_event_id, channel, destination,
                                 payload, idempotency_key)
    values ('7ea70000-0000-0000-0000-0000000000a1','7ea70000-0000-0000-0000-0000000000d1',
            'whatsapp','+5511999990001',
            '{"reference_date":"2026-08-18","expected_time":"08:00","actual_time":"08:12"}'::jsonb,'k4')
  $q$);

  perform pg_temp.deve_passar('evento sem horário realizado não exige actual_time', $q$
    insert into app.alert_queue (tenant_id, deviation_event_id, channel, destination,
                                 payload, idempotency_key)
    values ('7ea70000-0000-0000-0000-0000000000a1','7ea70000-0000-0000-0000-0000000000d2',
            'whatsapp','+5511999990001',
            '{"reference_date":"2026-08-18"}'::jsonb,'k5')
  $q$);

  perform pg_temp.deve_passar('alerta agregado não exige horário', $q$
    insert into app.alert_queue (tenant_id, channel, destination, payload, idempotency_key)
    values ('7ea70000-0000-0000-0000-0000000000a1','whatsapp','+5511999990000',
            '{"unit":"Unidade Alerta","occurrences":3}'::jsonb,'k6')
  $q$);
end $$;

\echo '--- C) cadência do motor'
do $$
declare r record;
begin
  perform pg_temp.deve_falhar('scope inválido em detection_run', $q$
    insert into app.detection_run (tenant_id, mode, scope, period_start, period_end)
    values ('7ea70000-0000-0000-0000-0000000000a1','production','diario','2026-08-18','2026-08-18')
  $q$);

  insert into app.detection_run (tenant_id, mode, scope, period_start, period_end, status, finished_at)
  values ('7ea70000-0000-0000-0000-0000000000a1','production','incremental',
          '2026-08-18','2026-08-18','completed', now());

  set local role authenticated;
  set local request.jwt.claim.sub = '7e000000-0000-0000-0000-000000000001';

  select * into r from public.fn_detection_health() limit 1;
  if r.tenant_id is null then
    raise exception 'FALHA: fn_detection_health não devolveu o tenant do usuário';
  end if;
  if not r.backfill_overdue then
    raise exception 'FALHA: backfill nunca executado deveria constar como atrasado';
  end if;
  raise notice '  ok  backfill que nunca rodou é reportado como atrasado';
  reset role;
end $$;

reset role;

\echo '--- D) três provedores de WhatsApp atrás de um contrato só'
do $$ begin
  -- O corpo do template tem que casar com as variáveis declaradas.
  perform pg_temp.deve_falhar('template sem variável', $q$
    insert into app.message_template (tenant_id, code, variables, body)
    values ('7ea70000-0000-0000-0000-0000000000a1', 'vazio', '{}', 'Algo aconteceu.')
  $q$);

  perform pg_temp.deve_falhar('variável declarada e não usada no corpo', $q$
    insert into app.message_template (tenant_id, code, variables, body)
    values ('7ea70000-0000-0000-0000-0000000000a1', 'incompleto',
            array['reference_date','actual_time'], 'Ocorrência em {{1}}.')
  $q$);

  perform pg_temp.deve_falhar('placeholder além do declarado sairia literal', $q$
    insert into app.message_template (tenant_id, code, variables, body)
    values ('7ea70000-0000-0000-0000-0000000000a1', 'sobrando',
            array['reference_date'], 'Em {{1}} às {{2}}.')
  $q$);

  -- Declara quatro variáveis de propósito: a quarta não vem no payload do teste
  -- seguinte, que é justamente o que deve ser recusado.
  perform pg_temp.deve_passar('template coerente', $q$
    insert into app.message_template
      (tenant_id, code, variables, body, meta_template_name, meta_status)
    values ('7ea70000-0000-0000-0000-0000000000a1', 'deviation_individual',
            array['reference_date','expected_time','actual_time','unit'],
            'OperaX {{4}}: em {{1}}, entrada registrada às {{3}}, prevista {{2}}.',
            'operax_desvio_individual', 'draft')
  $q$);
end $$;

do $$ begin
  -- O payload precisa cobrir todas as variáveis do template.
  perform pg_temp.deve_falhar('payload não cobre variável do template', $q$
    insert into app.alert_queue (tenant_id, deviation_event_id, channel, destination,
                                 payload, idempotency_key, template_code, provider)
    values ('7ea70000-0000-0000-0000-0000000000a1','7ea70000-0000-0000-0000-0000000000d1',
            'whatsapp','+5511999990001',
            '{"reference_date":"2026-08-18","expected_time":"08:00","actual_time":"08:12"}'::jsonb,
            'k10','deviation_individual','z_api')
  $q$);
end $$;

-- Ajusta o template para o que o payload realmente carrega e segue.
update app.message_template
   set variables = array['reference_date','expected_time','actual_time'],
       body = 'OperaX: em {{1}}, entrada registrada às {{3}}, prevista {{2}}.'
 where code = 'deviation_individual';

do $$ begin
  perform pg_temp.deve_passar('provedor não oficial não exige aprovação da Meta', $q$
    insert into app.alert_queue (tenant_id, deviation_event_id, channel, destination,
                                 payload, idempotency_key, template_code, provider)
    values ('7ea70000-0000-0000-0000-0000000000a1','7ea70000-0000-0000-0000-0000000000d1',
            'whatsapp','+5511999990001',
            '{"reference_date":"2026-08-18","expected_time":"08:00","actual_time":"08:12"}'::jsonb,
            'k11','deviation_individual','uazapi')
  $q$);

  perform pg_temp.deve_falhar('meta_cloud com template não aprovado', $q$
    insert into app.alert_queue (tenant_id, deviation_event_id, channel, destination,
                                 payload, idempotency_key, template_code, provider)
    values ('7ea70000-0000-0000-0000-0000000000a1','7ea70000-0000-0000-0000-0000000000d1',
            'whatsapp','+5511999990001',
            '{"reference_date":"2026-08-18","expected_time":"08:00","actual_time":"08:12"}'::jsonb,
            'k12','deviation_individual','meta_cloud')
  $q$);

  -- Payload completo de propósito: assim quem recusa é o contrato de template,
  -- não o da migration 13. Um teste que passa pelo motivo errado não testa nada.
  perform pg_temp.deve_falhar('template inexistente no tenant', $q$
    insert into app.alert_queue (tenant_id, deviation_event_id, channel, destination,
                                 payload, idempotency_key, template_code, provider)
    values ('7ea70000-0000-0000-0000-0000000000a1','7ea70000-0000-0000-0000-0000000000d1',
            'whatsapp','+5511999990001',
            '{"reference_date":"2026-08-18","expected_time":"08:00","actual_time":"08:12"}'::jsonb,
            'k13','nao_existe','z_api')
  $q$);
end $$;

update app.message_template set meta_status = 'approved' where code = 'deviation_individual';

do $$ begin
  perform pg_temp.deve_passar('meta_cloud com template aprovado', $q$
    insert into app.alert_queue (tenant_id, deviation_event_id, channel, destination,
                                 payload, idempotency_key, template_code, provider)
    values ('7ea70000-0000-0000-0000-0000000000a1','7ea70000-0000-0000-0000-0000000000d1',
            'whatsapp','+5511999990001',
            '{"reference_date":"2026-08-18","expected_time":"08:00","actual_time":"08:12"}'::jsonb,
            'k14','deviation_individual','meta_cloud')
  $q$);
end $$;

do $$ begin
  -- Dois provedores ativos = alerta duplicado no telefone do gestor.
  insert into app.integration (tenant_id, provider, active)
  values ('7ea70000-0000-0000-0000-0000000000a1', 'meta_cloud', true);

  perform pg_temp.deve_falhar('segundo provedor de whatsapp ativo no mesmo tenant', $q$
    insert into app.integration (tenant_id, provider, active)
    values ('7ea70000-0000-0000-0000-0000000000a1', 'z_api', true)
  $q$);

  perform pg_temp.deve_passar('segundo provedor inativo pode coexistir', $q$
    insert into app.integration (tenant_id, provider, active)
    values ('7ea70000-0000-0000-0000-0000000000a1', 'uazapi', false)
  $q$);
end $$;

\echo '--- E) prontidão do canal é observável antes de doer'
do $$
declare r record;
begin
  -- Regra ligada, canal whatsapp, apontando para template ainda não aprovado.
  insert into app.message_template (tenant_id, code, variables, body, meta_status)
  values ('7ea70000-0000-0000-0000-0000000000a1', 'deviation_summary',
          array['unit','occurrences'], 'OperaX: {{1}} com {{2}} ocorrências.', 'pending');

  update app.alert_rule
     set template_code = 'deviation_summary', active = true, channel = 'whatsapp'
   where id = '7ea70000-0000-0000-0000-00000000e002';

  set local role authenticated;
  set local request.jwt.claim.sub = '7e000000-0000-0000-0000-000000000001';

  select * into r from public.fn_whatsapp_readiness() limit 1;
  if r.tenant_id is null then
    raise exception 'FALHA: fn_whatsapp_readiness não devolveu o tenant do usuário';
  end if;
  if r.provider <> 'meta_cloud' or not r.official then
    raise exception 'FALHA: provedor ativo deveria ser meta_cloud e oficial (veio %)', r.provider;
  end if;
  if r.rules_blocked < 1 or r.ready then
    raise exception 'FALHA: regra ligada com template pendente deveria travar a prontidão (bloqueadas=%, pronta=%)',
      r.rules_blocked, r.ready;
  end if;
  raise notice '  ok  regra ligada com template não aprovado aparece como não pronta';
  reset role;
end $$;

reset role;

\echo ''
\echo '================================================'
\echo ' REGRAS DE ALERTA E CADÊNCIA: TODOS OS TESTES OK'
\echo '================================================'

rollback;
