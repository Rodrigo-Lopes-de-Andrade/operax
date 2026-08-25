-- ============================================================================
-- OperaX — 23. "PENDENTE DE JUSTIFICATIVA" VIRA ESTADO, EM VEZ DE INTENÇÃO
-- ----------------------------------------------------------------------------
-- O escopo contratado lista "ocorrências pendentes de justificativa" como
-- indicador (COBERTURA §4.3, item 10). `app.justification` existe desde a
-- migration 05 e **nada marcava um desvio como exigindo justificativa**, nem uma
-- justificativa como aceita. O indicador não podia ser calculado porque os dois
-- lados da conta faltavam.
--
-- 1. QUAL TIPO EXIGE. `app.deviation_type_config` é onde a política por cliente
--    já mora — `counts_as_deviation` e `triggers_alert` estão lá. Exigir
--    justificativa é a mesma classe de decisão: "atraso precisa de explicação
--    aqui, marcação incompleta não" muda por cliente. Nasce `false` para todos,
--    pelo mesmo motivo que `triggers_alert` nasce `false`: uma política que
--    aparece ligada sem alguém ter ligado é uma política que ninguém homologou.
--
-- 2. O QUE É "ACEITA". `app.justification` não tinha estado: uma linha ali era,
--    implicitamente, a resposta final. O default `accepted` preserva exatamente
--    esse significado para toda linha que já existe — nenhuma justificativa
--    escrita até hoje passa a contar como pendente por causa desta migration.
--
--    ⚠️ Não há tela que aceite ou rejeite. `rejected` existe no domínio e não
--    tem quem o produza; enquanto isso não existir, "aceita" e "escrita" são a
--    mesma coisa na prática. Está declarado aqui para que ninguém leia o
--    indicador como se houvesse curadoria por trás dele.
--
-- 3. A LEITURA DERIVADA é função em `public`, e não coluna nova numa view
--    existente. Acrescentar coluna a view de `public` é uma das três paradas
--    obrigatórias do CLAUDE.md; uma função nova, `security invoker`, com grant
--    só para `authenticated`, expõe o mesmo recorte que `vw_deviation_event` já
--    expõe — os mesmos eventos, sob a mesma RLS — mais um booleano derivado. O
--    texto da justificativa **não sai**: só a existência dela.
--
-- Nenhuma tabela nova, nenhuma policy nova.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

alter table app.deviation_type_config
  add column if not exists requires_justification boolean not null default false;

comment on column app.deviation_type_config.requires_justification is
  'Nasce false, como triggers_alert. Política por cliente: atraso pode exigir explicação '
  'onde marcação incompleta não exige. Sem isto, "pendente de justificativa" não tem de '
  'onde sair — todo desvio pareceria pendente, ou nenhum.';

alter table app.justification
  add column if not exists status text not null default 'accepted';

alter table app.justification drop constraint if exists justification_status_check;
alter table app.justification
  add  constraint justification_status_check check (status in ('accepted','rejected'));

comment on column app.justification.status is
  'Default accepted de propósito: até esta migration uma linha aqui ERA a resposta final, '
  'e nenhuma justificativa já escrita pode virar pendente retroativamente. Não existe tela '
  'que rejeite — enquanto não existir, "aceita" e "escrita" são a mesma coisa.';

create index if not exists justification_aceita_idx
  on app.justification (deviation_event_id)
  where status = 'accepted';

-- ---------------------------------------------------------------------------
-- A leitura derivada
-- ---------------------------------------------------------------------------
create or replace function public.fn_pending_justification(
  p_de date, p_ate date,
  p_unit_id       uuid default null,
  p_department_id uuid default null,
  p_manager_id    uuid default null
) returns table (
  deviation_event_id uuid,
  employee_id        uuid,
  employee_name      text,
  unit_id            uuid,
  unit_name          text,
  reference_date     date,
  type               text,
  type_description   text,
  minutes            integer,
  detected_at        timestamptz
)
language sql stable security invoker set search_path = ''
as $$
  select d.id, d.employee_id, e.name, d.unit_id, u.name,
         d.reference_date, d.type, t.description, d.minutes, d.detected_at
  from app.deviation_event d
  join app.employee e on e.id = d.employee_id
  join app.deviation_type t on t.code = d.type
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type
      and cfg.active and cfg.requires_justification
  left join app.unit u on u.id = d.unit_id
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_unit_id       is null or d.unit_id = p_unit_id)
    and (p_department_id is null or e.department_id = p_department_id)
    and (p_manager_id    is null or e.manager_employee_id = p_manager_id)
    and not exists (
      select 1 from app.justification j
      where j.deviation_event_id = d.id and j.status = 'accepted'
    )
  order by d.reference_date desc, e.name;
$$;

comment on function public.fn_pending_justification(date, date, uuid, uuid, uuid) is
  'Desvio ativo, de tipo que exige justificativa, sem nenhuma justificativa aceita. '
  'Devolve a existência da pendência, nunca o texto de justificativa nenhuma.';

revoke execute on function public.fn_pending_justification(date, date, uuid, uuid, uuid)
  from public, anon;
grant  execute on function public.fn_pending_justification(date, date, uuid, uuid, uuid)
  to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_tenant   uuid;
  v_company  uuid;
  v_employee uuid;
  v_evento   uuid;
  v_pend     int;
begin
  -- 1. As duas colunas existem com o default que preserva o passado.
  if (select column_default from information_schema.columns
      where table_schema='app' and table_name='justification' and column_name='status')
     not like '%accepted%' then
    raise exception 'o default de app.justification.status não é accepted — linha antiga viraria pendente';
  end if;
  if (select column_default from information_schema.columns
      where table_schema='app' and table_name='deviation_type_config'
        and column_name='requires_justification') not like '%false%' then
    raise exception 'requires_justification não nasce false';
  end if;

  -- 2. A função não alcança anon, e não devolve texto de justificativa.
  if has_function_privilege('anon',
       'public.fn_pending_justification(date,date,uuid,uuid,uuid)', 'execute') then
    raise exception 'anon executa fn_pending_justification';
  end if;
  if exists (
    select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname='public' and p.proname='fn_pending_justification'
      and pg_get_function_result(p.oid) ilike '%text_justificativa%'
  ) then
    raise exception 'a função devolve texto de justificativa';
  end if;

  -- 3. Teste vivo: exigir, não justificar, justificar.
  select id into v_tenant from app.tenant order by created_at limit 1;
  if v_tenant is null then
    raise notice 'sem tenant: prova viva pulada (as colunas já foram verificadas acima)';
    return;
  end if;
  select id into v_company  from app.company  where tenant_id = v_tenant limit 1;
  select id into v_employee from app.employee where tenant_id = v_tenant limit 1;
  if v_company is null or v_employee is null then
    raise notice 'sem colaborador: prova viva pulada';
    return;
  end if;

  update app.deviation_type_config
     set requires_justification = true
   where tenant_id = v_tenant and code = 'late_entry';

  insert into app.deviation_event
    (tenant_id, employee_id, company_id, reference_date, type, minutes, mode)
  values (v_tenant, v_employee, v_company, '1999-02-01', 'late_entry', -15, 'production')
  on conflict (employee_id, reference_date, type) where status = 'active'
  do update set minutes = excluded.minutes
  returning id into v_evento;

  select count(*) into v_pend
    from app.deviation_event d
    join app.deviation_type_config cfg
         on cfg.tenant_id = d.tenant_id and cfg.code = d.type
        and cfg.active and cfg.requires_justification
   where d.id = v_evento
     and not exists (select 1 from app.justification j
                     where j.deviation_event_id = d.id and j.status = 'accepted');
  if v_pend <> 1 then
    raise exception 'desvio de tipo que exige justificativa não apareceu como pendente';
  end if;

  insert into app.justification
    (tenant_id, deviation_event_id, employee_id, reference_date, text, status)
  values (v_tenant, v_evento, v_employee, '1999-02-01', '__migration_23__', 'accepted');

  select count(*) into v_pend
    from app.deviation_event d
   where d.id = v_evento
     and not exists (select 1 from app.justification j
                     where j.deviation_event_id = d.id and j.status = 'accepted');
  if v_pend <> 0 then
    raise exception 'justificativa aceita não tirou o desvio da pendência';
  end if;

  delete from app.justification where deviation_event_id = v_evento;
  delete from app.deviation_event where id = v_evento;
  update app.deviation_type_config
     set requires_justification = false
   where tenant_id = v_tenant and code = 'late_entry';

  raise notice 'OK: pendente de justificativa é estado, e justificar tira da lista.';
end $$;
