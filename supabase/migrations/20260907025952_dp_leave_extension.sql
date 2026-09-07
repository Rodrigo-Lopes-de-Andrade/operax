-- ============================================================================
-- OperaX — dp_leave_extension. FÉRIAS E ATESTADO GANHAM O QUE FALTAVA
-- ----------------------------------------------------------------------------
-- Desenho em `docs/SPEC-DP.md` §1h. `app.leave_period` guarda hoje categoria,
-- início, fim e origem. O legado precisa de três coisas a mais para fechar
-- férias: o anexo, o período aquisitivo e a data limite.
--
-- ⛔ NENHUMA DELAS É MOTIVO, E ISSO É A REGRA 10 DO PROJETO
-- "Dado de saúde guarda só aptidão e validade — nunca diagnóstico, CID ou
-- restrição." O comentário da tabela (migration 04) já dizia por que a categoria
-- é rótulo neutro, e nada aqui desfaz isso: `document_id` aponta para o ARQUIVO
-- do atestado, cujo acesso continua sendo decidido pelo domínio do tipo de
-- documento (`document_read`, migration 08); `accrual_period` é um par de anos; e
-- `limit_date` é uma data. Nenhuma coluna nova aceita texto de motivo — e o passo
-- 3 da garantia abaixo é o que impede que uma apareça amanhã com outro nome.
--
-- ⚠️ A CATEGORIA DE FALTA CHEGOU EM `dp_leave_category` (06/09), NÃO AQUI
-- Aquela migration abriu o check para `unjustified_absence`, que é o que as duas
-- rotinas financeiras leem. Esta não toca no check: as três colunas são
-- ortogonais à categoria, e mexer nele de novo faria duas migrations disputarem
-- a mesma constraint.
--
-- ⛔ AS TRÊS SÃO ADITIVAS E ANULÁVEIS
-- Toda linha já gravada — inclusive as que a sincronização escreve — nasce sem
-- as três. `not null` aqui quebraria a próxima escrita da origem.
--
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

alter table app.leave_period
  add column if not exists document_id     uuid references app.document(id) on delete set null,
  add column if not exists accrual_period  text,
  add column if not exists limit_date      date;

create index if not exists leave_period_limite_idx
  on app.leave_period (tenant_id, limit_date)
  where limit_date is not null;

comment on column app.leave_period.document_id is
  'Anexo do afastamento (o atestado). Aponta para o ARQUIVO, nunca para o motivo: '
  'quem lê o documento continua passando por document_read, que exige o domínio do '
  'tipo. Regra 10 — sem diagnóstico, sem CID, sem restrição.';
comment on column app.leave_period.accrual_period is
  'Período aquisitivo no formato do legado ("2025/2026"). Texto porque é rótulo de '
  'competência, não data: nada nesta etapa calcula sobre ele.';
comment on column app.leave_period.limit_date is
  'Data limite para gozo das férias (admissão + 12 meses, no legado). É a fonte do '
  'contador "data limite de férias" de public.fn_dp_alerts.';

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v_coluna    text;
  v_tipo      text;
  v_nullable  text;
  v_alvo      text;
  v_proibida  text;
  v_tenant    uuid;
  v_company   uuid;
  v_employee  uuid;
  v_recusou   boolean := false;
  v_esperado  constant text[][] := array[
    ['document_id',    'uuid'],
    ['accrual_period', 'text'],
    ['limit_date',     'date']
  ];
  i int;
begin
  -- 1. As três existem, com o tipo declarado e anuláveis.
  for i in 1 .. array_length(v_esperado, 1) loop
    v_coluna := v_esperado[i][1];
    select data_type, is_nullable into v_tipo, v_nullable
      from information_schema.columns
     where table_schema = 'app' and table_name = 'leave_period'
       and column_name = v_coluna;
    if v_tipo is null then
      raise exception 'app.leave_period.% não existe', v_coluna;
    end if;
    if v_tipo <> v_esperado[i][2] then
      raise exception 'app.leave_period.% é %, esperava %', v_coluna, v_tipo, v_esperado[i][2];
    end if;
    if v_nullable <> 'YES' then
      raise exception
        'app.leave_period.% é NOT NULL — a coluna era aditiva e passou a recusar a linha que a sincronização grava',
        v_coluna;
    end if;
  end loop;

  -- 2. `document_id` aponta para `app.document`. Um uuid solto aceitaria
  --    qualquer id, inclusive o de outro tenant.
  select cl.relname into v_alvo
    from pg_constraint c
    join pg_class cl on cl.oid = c.confrelid
    join pg_attribute a on a.attrelid = c.conrelid and a.attnum = c.conkey[1]
   where c.conrelid = 'app.leave_period'::regclass
     and c.contype = 'f'
     and array_length(c.conkey, 1) = 1
     and a.attname = 'document_id';
  if v_alvo is distinct from 'document' then
    raise exception 'app.leave_period.document_id referencia % — esperava app.document',
      coalesce(v_alvo, 'NADA');
  end if;

  -- 3. ⛔ REGRA 10, NA CAMADA DO BANCO
  --    A varredura é por NOME de coluna e não por valor de propósito: o dia em
  --    que alguém acrescentar `cid`, `diagnostico` ou `restricao` a esta tabela,
  --    a migration que o fizer não roda. Sem esta asserção, a regra viveria só
  --    no cabeçalho — e cabeçalho não reprova PR.
  select string_agg(column_name, ', ') into v_proibida
    from information_schema.columns
   where table_schema = 'app'
     and table_name in ('leave_period', 'occupational_exam')
     and column_name ~* '(cid|diagn|restric|restrict|doenca|patolog|laudo_medico|motivo_medico)';
  if v_proibida is not null then
    raise exception
      'REGRA 10 VIOLADA: coluna de diagnóstico/restrição em afastamento ou exame -> %',
      v_proibida;
  end if;

  -- 4. A prova viva: as três aceitam valor, e a FK do anexo é FK de verdade.
  select t.id into v_tenant from app.tenant t order by t.created_at limit 1;
  if v_tenant is null then
    raise notice 'sem tenant: prova viva pulada (a estrutura já foi verificada acima)';
    return;
  end if;

  insert into app.company (tenant_id, legal_name, active)
  values (v_tenant, '__dp_le_prova__', false)
  returning id into v_company;
  insert into app.employee (tenant_id, company_id, name)
  values (v_tenant, v_company, '__dp_le_prova__')
  returning id into v_employee;

  -- a) férias com período aquisitivo e data limite, sem anexo;
  insert into app.leave_period
    (tenant_id, employee_id, category, start_date, end_date, source,
     accrual_period, limit_date)
  values (v_tenant, v_employee, 'vacation', date '2026-07-01', date '2026-07-30',
          'manual', '2025/2026', date '2026-12-31');

  -- b) e o anexo inventado é barrado — a coluna aponta para documento que existe.
  begin
    insert into app.leave_period
      (tenant_id, employee_id, category, start_date, end_date, source, document_id)
    values (v_tenant, v_employee, 'leave_period', date '2026-08-01', date '2026-08-02',
            'manual', '00000000-0000-4000-8000-000000000000');
  exception when foreign_key_violation then
    v_recusou := true;
  end;
  if not v_recusou then
    raise exception
      'app.leave_period aceitou document_id que não existe — o anexo virou texto livre com cara de referência';
  end if;

  delete from app.leave_period where employee_id = v_employee;
  delete from app.employee where id = v_employee;
  delete from app.company  where id = v_company;

  raise notice
    'OK: app.leave_period ganhou anexo, período aquisitivo e data limite — e nenhuma coluna de diagnóstico entrou junto.';
end $$;
