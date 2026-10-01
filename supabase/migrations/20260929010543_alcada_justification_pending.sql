-- ============================================================================
-- OperaX — alcada_justification_pending. O ESTADO QUE A ALÇADA PRECISA
-- ----------------------------------------------------------------------------
-- Desenho: `docs/DECISAO-ALCADA-APROVACAO.md` §4.1; sprint P1.1 de
-- `docs/SPRINTS-ALCADA.md`.
--
-- 1. `pending` ENTRA NO DOMÍNIO, E VIRA O DEFAULT. A alçada existe para que uma
--    justificativa escrita espere a decisão de quem tem alçada. Até aqui uma
--    linha em `app.justification` ERA a resposta final (migration 23).
--
-- 2. ⛔ NENHUMA LINHA JÁ ESCRITA VIRA PENDENTE. Trocar o default de uma coluna
--    não toca linha existente — e é exatamente o que se quer. Por isso esta
--    migration NÃO tem `update` retroativo, e não pode ter: o comentário da
--    coluna já exigia isso desde a 23. São dois os escritores de hoje, e os
--    dois passam `status` explícito, então a troca de default não muda o que
--    gravam: `backend/operax/motor/justificativa.py` (a rota) e
--    `supabase/seed.sql` (o seed de desenvolvimento, que grava `accepted` sobre
--    evento `justified` — omitido, o default faria o motor reabrir o evento).
--
-- 3. O ESPELHO NÃO PENDE. Justificativa com `source = 'secullum'` já foi
--    decidida no registro oficial: pender ou ser reprovada no OperaX seria
--    reaprovar o que a fonte da verdade resolveu. Vira `check`, não parágrafo.
--    Consequência deliberada: com o default agora `pending`, um escritor do
--    espelho que omita o status é RECUSADO em vez de gravar em silêncio — ele
--    tem de dizer `accepted`.
--    ⚠️ Se alguma linha `secullum` já estiver `rejected`, o `add constraint`
--    falha e a migration inteira para. É o comportamento certo: consertar essa
--    linha é decisão, não efeito colateral de migration. (Produção tinha zero
--    linhas em 28/09/2026.)
--
-- Nenhuma tabela nova, nenhuma policy nova ou alterada, nenhuma view tocada.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

alter table app.justification drop constraint if exists justification_status_check;
alter table app.justification
  add constraint justification_status_check
      check (status in ('pending','accepted','rejected'));

alter table app.justification alter column status set default 'pending';

alter table app.justification drop constraint if exists justification_espelho_nao_pende;
alter table app.justification
  add constraint justification_espelho_nao_pende
      check (source <> 'secullum' or status = 'accepted');

comment on column app.justification.status is
  'Default pending desde a alcada_justification_pending: justificativa nova espera a '
  'decisão de quem tem alçada. Nenhuma justificativa já escrita pode virar pendente '
  'retroativamente — a troca de default não tocou linha existente, e nenhuma migration '
  'pode fazê-lo. source = secullum nasce e fica accepted (justification_espelho_nao_pende): '
  'a origem já decidiu.';

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_tenant   uuid := gen_random_uuid();
  v_company  uuid := gen_random_uuid();
  v_employee uuid := gen_random_uuid();
  v_status   text;
begin
  -- 1. Catálogo: default, domínio e a trava existem como declarados.
  if (select column_default from information_schema.columns
      where table_schema = 'app' and table_name = 'justification'
        and column_name = 'status') not like '''pending''%' then
    raise exception 'o default de app.justification.status não é pending';
  end if;
  if not exists (select 1 from pg_constraint
                 where conrelid = 'app.justification'::regclass
                   and conname = 'justification_espelho_nao_pende' and convalidated) then
    raise exception 'justification_espelho_nao_pende não existe ou não foi validada';
  end if;

  -- 2. Prova viva, com linhas sintéticas desfeitas no fim do bloco: a exceção
  --    'OXP11' reverte tudo que foi inserido aqui, e só ela é engolida.
  begin
    insert into app.tenant (id, slug, name)
    values (v_tenant, 'p11-proof-' || left(replace(v_tenant::text, '-', ''), 12), 'proof');
    insert into app.company (id, tenant_id, legal_name, trade_name)
    values (v_company, v_tenant, 'proof', 'proof');
    insert into app.employee (id, tenant_id, company_id, name)
    values (v_employee, v_tenant, v_company, 'proof');

    -- O check aceita pending, e o default o produz.
    insert into app.justification (tenant_id, employee_id, reference_date, text, source)
    values (v_tenant, v_employee, '1999-01-01', 'proof', 'operax')
    returning status into v_status;
    if v_status <> 'pending' then
      raise exception 'justificativa nova do OperaX nasceu %, não pending', v_status;
    end if;

    -- O espelho não pende: nem pedindo, nem pelo default.
    begin
      insert into app.justification (tenant_id, employee_id, reference_date, text, source, status)
      values (v_tenant, v_employee, '1999-01-01', 'proof', 'secullum', 'pending');
      raise exception 'o banco aceitou justificativa do Secullum pendente';
    exception when check_violation then null;
    end;
    begin
      insert into app.justification (tenant_id, employee_id, reference_date, text, source)
      values (v_tenant, v_employee, '1999-01-01', 'proof', 'secullum');
      raise exception 'o banco aceitou justificativa do Secullum pelo default pending';
    exception when check_violation then null;
    end;

    -- E o espelho aceito continua entrando.
    insert into app.justification (tenant_id, employee_id, reference_date, text, source, status)
    values (v_tenant, v_employee, '1999-01-01', 'proof', 'secullum', 'accepted');

    raise exception using errcode = 'OXP11', message = 'undo proof rows';
  exception when sqlstate 'OXP11' then null;
  end;

  if exists (select 1 from app.tenant where id = v_tenant) then
    raise exception 'a prova deixou rastro em app.tenant';
  end if;

  raise notice 'OK: pending é o default, o espelho não pende, e nada já escrito foi tocado.';
end $$;
