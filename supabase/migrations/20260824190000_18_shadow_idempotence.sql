-- ============================================================================
-- OperaX — 18. RE-RUNNING SHADOW MODE MUST NOT DOUBLE THE COUNT
-- ----------------------------------------------------------------------------
-- Migration 05 declared the grain of `app.deviation_event` — one active row per
-- (employee, day, type) — and enforced it with a partial unique index restricted
-- to `mode = 'production'`. Shadow rows were left without any uniqueness.
--
-- That is exactly backwards for the stage the product is in. S4 runs the engine
-- in shadow for one to two weeks, re-processing the same week after every
-- tolerance correction, and its acceptance criterion is literally "reprocessar o
-- mesmo período duas vezes não altera contagem". Without an index to conflict
-- on, the second run inserted a second copy of every event, and the false
-- positive rate the whole gate depends on would have been measured against a
-- table that doubled every time somebody fixed a tolerance.
--
-- WHAT THIS DOES AND DOES NOT CHANGE
-- The grain does not move: it is the same (employee, day, type) migration 05
-- declared, now carrying `mode` so the two runs of a day do not collide with
-- each other. A shadow event and a production event for the same fact are
-- different rows on purpose — the views read production only, and shadow has to
-- be able to run beside it without touching what the dashboard shows.
--
-- The production index stays. It is stricter than this one for the rows that
-- reach a person, it costs almost nothing, and removing a guarantee to add a
-- broader one is how a guarantee gets lost in a diff.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

create unique index if not exists deviation_event_unico_active_modo
  on app.deviation_event (employee_id, reference_date, type, mode)
  where status = 'active';

comment on index app.deviation_event_unico_active_modo is
  'Grão de migration 05 estendido à sombra: o motor faz `on conflict` neste índice, '
  'e é ele que faz reprocessar a mesma semana reescrever a linha em vez de duplicá-la.';

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_tenant   uuid;
  v_company  uuid;
  v_employee uuid;
  v_antes    int;
  v_depois   int;
begin
  -- 1. Os dois índices existem, e os dois são parciais e únicos.
  if not exists (
    select 1 from pg_class c join pg_index i on i.indexrelid = c.oid
    where c.relname = 'deviation_event_unico_active_modo'
      and i.indisunique and i.indpred is not null
  ) then
    raise exception 'deviation_event_unico_active_modo não é índice único PARCIAL';
  end if;
  if not exists (
    select 1 from pg_class c join pg_index i on i.indexrelid = c.oid
    where c.relname = 'deviation_event_unico_active' and i.indisunique
  ) then
    raise exception 'o índice de produção da migration 05 desapareceu';
  end if;

  -- 2. Teste vivo: dois inserts do mesmo fato em sombra têm de virar uma linha.
  --    É a asserção do S4 escrita onde ela não pode ser esquecida.
  select id into v_tenant from app.tenant order by created_at limit 1;
  if v_tenant is null then
    raise notice 'sem tenant: prova viva pulada (o índice já foi verificado acima)';
    return;
  end if;

  select id into v_company from app.company where tenant_id = v_tenant limit 1;
  select id into v_employee from app.employee where tenant_id = v_tenant limit 1;
  if v_company is null or v_employee is null then
    raise notice 'sem colaborador: prova viva pulada';
    return;
  end if;

  select count(*) into v_antes from app.deviation_event
   where employee_id = v_employee and reference_date = date '1999-01-01';

  insert into app.deviation_event
    (tenant_id, employee_id, company_id, reference_date, type, minutes, mode)
  values (v_tenant, v_employee, v_company, '1999-01-01', 'late_entry', -10, 'shadow')
  on conflict (employee_id, reference_date, type, mode) where status = 'active'
  do update set minutes = excluded.minutes;

  insert into app.deviation_event
    (tenant_id, employee_id, company_id, reference_date, type, minutes, mode)
  values (v_tenant, v_employee, v_company, '1999-01-01', 'late_entry', -25, 'shadow')
  on conflict (employee_id, reference_date, type, mode) where status = 'active'
  do update set minutes = excluded.minutes;

  select count(*) into v_depois from app.deviation_event
   where employee_id = v_employee and reference_date = date '1999-01-01';

  if v_depois - v_antes <> 1 then
    raise exception 'reprocessar em sombra duplicou: % linha(s) para o mesmo fato', v_depois - v_antes;
  end if;
  if (select minutes from app.deviation_event
       where employee_id = v_employee and reference_date = date '1999-01-01'
         and type = 'late_entry' and mode = 'shadow' and status = 'active') <> -25 then
    raise exception 'o segundo processamento não atualizou os minutos';
  end if;

  delete from app.deviation_event
   where employee_id = v_employee and reference_date = date '1999-01-01';

  raise notice 'OK: reprocessar a mesma janela em sombra reescreve a linha, não duplica.';
end $$;
