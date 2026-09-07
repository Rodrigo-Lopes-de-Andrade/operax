-- ============================================================================
-- OperaX — dp_movement_period. A MOVIMENTAÇÃO DEIXA DE SER EVENTO E VIRA PERÍODO
-- ----------------------------------------------------------------------------
-- Desenho em `docs/SPEC-DP.md` §1g. Hoje `app.workforce_movement` guarda
-- `unit_id`, `type` e `event_date`: um carimbo de que algo aconteceu num dia. O
-- legado trabalha com PERÍODO — origem, destino e vigência — e projeta a
-- "unidade de atuação" da ficha a partir dele
-- (`ANEXO-COBERTURA-LEGADO-FASTPARK.md` §4.1).
--
-- ⛔ AS SEIS COLUNAS SÃO ADITIVAS E ANULÁVEIS, E ISSO NÃO É FROUXIDÃO
-- A tabela já tem linhas (`hire`, `termination`, `promotion`) que não são
-- remanejamento e não têm origem nem destino. Exigir `not null` aqui tornaria
-- ilegal a linha que o produto já grava, e a migration não rodaria sem janela.
--
-- ⛔ A UNIDADE DE ATUAÇÃO NÃO GANHA COLUNA — ELA É LEITURA DERIVADA
-- A regra que a tela do legado declara, transcrita:
--
--   unidade de atuação = destino da movimentação vigente (sem `effective_to`,
--   ou com `effective_to` no futuro); na ausência de movimentação, a lotação de
--   `app.employee.unit_id`.
--
-- Uma coluna `acting_unit_id` em `app.employee` seria a mesma informação em dois
-- lugares, e o segundo é o que fica velho: bastaria uma movimentação encerrada
-- fora da tela para a ficha continuar apontando para a unidade antiga. A
-- derivação mora em `backend/operax/dp/painel.py::resolve_acting_placement`, uma
-- função pura, exercitada por fixture — mesma escolha, e pelo mesmo motivo, que
-- `beneficios.in_effect` (S1): escrita nos dois lugares ela divergiria, e a
-- metade SQL é a que o pytest não alcança.
--
-- ⛔ A POLICY DE LEITURA NÃO É TOCADA AQUI
-- `movimentacao_read` recorta por `unit_id`, a coluna do evento. Ela continua
-- exatamente como estava: mudança de policy de RLS é parada obrigatória
-- (`CLAUDE.md`), e nenhuma rota desta sprint escreve movimentação. Consequência
-- registrada para quem for escrever a tela de movimentações: uma linha cujo
-- `destination_unit_id` é a unidade do supervisor e cujo `unit_id` é outra NÃO
-- aparece para ele. Isso é decisão de policy, e é de quem despacha, não daqui.
--
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

alter table app.workforce_movement
  add column if not exists origin_unit_id           uuid references app.unit(id),
  add column if not exists destination_unit_id      uuid references app.unit(id),
  add column if not exists origin_work_post_id      uuid references app.work_post(id),
  add column if not exists destination_work_post_id uuid references app.work_post(id),
  add column if not exists effective_from           date,
  add column if not exists effective_to             date;

-- Período que termina antes de começar não é período. `not valid` seria mais
-- barato e mentiria sobre as linhas antigas — mas elas têm as duas colunas
-- nulas, então nenhuma fica ilegal e a validação roda na hora.
alter table app.workforce_movement
  drop constraint if exists workforce_movement_period_check;
alter table app.workforce_movement
  add constraint workforce_movement_period_check
  check (effective_to is null or effective_from is null or effective_to >= effective_from);

-- A derivação lê por pessoa e escolhe a mais recente entre as vigentes. Sem este
-- índice ela varre a tabela inteira por colaborador.
create index if not exists workforce_movement_periodo_idx
  on app.workforce_movement (tenant_id, employee_id, effective_from desc)
  where destination_unit_id is not null;

comment on column app.workforce_movement.destination_unit_id is
  'Destino do remanejamento. É daqui que sai a UNIDADE DE ATUAÇÃO: destino da '
  'movimentação vigente (sem effective_to, ou com effective_to no futuro); sem '
  'movimentação, vale a lotação de app.employee.unit_id. Derivada em leitura — '
  'nunca gravada de volta na ficha.';
comment on column app.workforce_movement.destination_work_post_id is
  'Posto de destino. Acompanha destination_unit_id na mesma projeção: a tela do '
  'legado atualiza os dois juntos, e separá-los deixaria a ficha com posto de '
  'uma unidade e unidade de outra.';
comment on column app.workforce_movement.effective_to is
  'Fim da vigência, inclusivo. Nulo = em aberto. Encerrar é escrever esta data — '
  'movimentação NUNCA é apagada (regra 6 estendida): apagar altera '
  'retroativamente onde a pessoa estava.';

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v_coluna    text;
  v_tipo      text;
  v_nullable  text;
  v_alvo      text;
  v_tenant    uuid;
  v_company   uuid;
  v_employee  uuid;
  v_unidade   uuid;
  v_posto     uuid;
  v_recusou   boolean := false;
  v_esperado  constant text[][] := array[
    ['origin_unit_id',           'uuid', 'unit'],
    ['destination_unit_id',      'uuid', 'unit'],
    ['origin_work_post_id',      'uuid', 'work_post'],
    ['destination_work_post_id', 'uuid', 'work_post'],
    ['effective_from',           'date', ''],
    ['effective_to',             'date', '']
  ];
  i int;
begin
  -- 1. As seis existem, com o tipo declarado e ANULÁVEIS. O `is_nullable` é
  --    asserção e não zelo: um `not null` aqui torna ilegal a linha de admissão
  --    que a tabela já grava, e o sintoma seria a próxima sincronização falhando
  --    longe daqui.
  for i in 1 .. array_length(v_esperado, 1) loop
    v_coluna := v_esperado[i][1];
    select data_type, is_nullable into v_tipo, v_nullable
      from information_schema.columns
     where table_schema = 'app' and table_name = 'workforce_movement'
       and column_name = v_coluna;
    if v_tipo is null then
      raise exception 'app.workforce_movement.% não existe', v_coluna;
    end if;
    if v_tipo <> v_esperado[i][2] then
      raise exception 'app.workforce_movement.% é %, esperava %',
        v_coluna, v_tipo, v_esperado[i][2];
    end if;
    if v_nullable <> 'YES' then
      raise exception
        'app.workforce_movement.% é NOT NULL — a coluna era aditiva e passou a recusar a linha antiga',
        v_coluna;
    end if;

    -- 2. E as quatro de referência apontam para a TABELA certa — um `uuid` sem
    --    FK aceitaria o id de um posto no lugar do de uma unidade.
    --    ⚠️ O que ela NÃO garante: a FK é simples, então ela aceita a unidade de
    --    OUTRO tenant. Nenhuma FK de `app` é composta com `tenant_id` — a
    --    fronteira de tenant é da RLS e do `tenant_scope`, não do catálogo — e
    --    dizer aqui que ela era da FK seria uma promessa que o schema inteiro
    --    não cumpre.
    if v_esperado[i][3] <> '' then
      select cl.relname into v_alvo
        from pg_constraint c
        join pg_class cl on cl.oid = c.confrelid
        join pg_attribute a on a.attrelid = c.conrelid and a.attnum = c.conkey[1]
       where c.conrelid = 'app.workforce_movement'::regclass
         and c.contype = 'f'
         and array_length(c.conkey, 1) = 1
         and a.attname = v_coluna;
      if v_alvo is distinct from v_esperado[i][3] then
        raise exception 'app.workforce_movement.% referencia % — esperava app.%',
          v_coluna, coalesce(v_alvo, 'NADA'), v_esperado[i][3];
      end if;
    end if;
  end loop;

  -- 3. A prova viva. Os itens acima conferem a ESTRUTURA; esta confere que o
  --    período se comporta — aceita vigência aberta e recusa fim antes do
  --    início. Uma constraint escrita ao contrário passaria nos dois primeiros.
  --    ⛔ Fixture inteiramente própria: o banco de ensaio tem ZERO empresas e
  --    `app.employee.company_id` é NOT NULL. A lição é da `dp_benefit_catalog`.
  select t.id into v_tenant from app.tenant t order by t.created_at limit 1;
  if v_tenant is null then
    raise notice 'sem tenant: prova viva pulada (a estrutura já foi verificada acima)';
    return;
  end if;

  insert into app.company (tenant_id, legal_name, active)
  values (v_tenant, '__dp_mp_prova__', false)
  returning id into v_company;
  insert into app.unit (tenant_id, company_id, code, name, active)
  values (v_tenant, v_company, '__dp_mp_prova__', '__dp_mp_prova__', false)
  returning id into v_unidade;
  insert into app.work_post (tenant_id, unit_id, code, name, active)
  values (v_tenant, v_unidade, '__dp_mp_prova__', '__dp_mp_prova__', false)
  returning id into v_posto;
  insert into app.employee (tenant_id, company_id, name)
  values (v_tenant, v_company, '__dp_mp_prova__')
  returning id into v_employee;

  -- a) o período em aberto entra, com destino e posto de destino;
  insert into app.workforce_movement
    (tenant_id, employee_id, company_id, type, event_date,
     destination_unit_id, destination_work_post_id, effective_from, effective_to)
  values (v_tenant, v_employee, v_company, 'transfer', date '2026-03-01',
          v_unidade, v_posto, date '2026-03-01', null);

  -- b) a linha SEM as colunas novas continua entrando — é a que já existia;
  insert into app.workforce_movement
    (tenant_id, employee_id, company_id, type, event_date)
  values (v_tenant, v_employee, v_company, 'hire', date '2020-01-01');

  -- c) e o período invertido é barrado.
  begin
    insert into app.workforce_movement
      (tenant_id, employee_id, company_id, type, event_date, effective_from, effective_to)
    values (v_tenant, v_employee, v_company, 'transfer', date '2026-03-01',
            date '2026-03-10', date '2026-03-01');
  exception when check_violation then
    v_recusou := true;
  end;
  if not v_recusou then
    raise exception
      'app.workforce_movement aceitou período que termina antes de começar — a vigência virou decoração, e a unidade de atuação passa a depender de uma janela impossível';
  end if;

  delete from app.workforce_movement where employee_id = v_employee;
  delete from app.employee  where id = v_employee;
  delete from app.work_post where id = v_posto;
  delete from app.unit      where id = v_unidade;
  delete from app.company   where id = v_company;

  raise notice
    'OK: app.workforce_movement virou período — origem, destino, posto e vigência, todos aditivos, e a linha antiga continua legal.';
end $$;
