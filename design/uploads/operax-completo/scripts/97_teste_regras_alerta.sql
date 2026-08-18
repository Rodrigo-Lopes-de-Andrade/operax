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

\echo ''
\echo '================================================'
\echo ' REGRAS DE ALERTA E CADÊNCIA: TODOS OS TESTES OK'
\echo '================================================'

rollback;
