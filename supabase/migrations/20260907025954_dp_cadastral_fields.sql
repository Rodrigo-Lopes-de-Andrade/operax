-- ============================================================================
-- OperaX — dp_cadastral_fields. OS CAMPOS DA FICHA QUE O DOMÍNIO NÃO TINHA
-- ----------------------------------------------------------------------------
-- Desenho em `docs/SPEC-DP.md` §1j, inventário em
-- `ANEXO-COBERTURA-LEGADO-FASTPARK.md` §3b. Oito colunas, todas aditivas e
-- anuláveis, em duas tabelas que já existem.
--
-- ⛔ `disability` É BOOLEANO, E ISSO É A REGRA 10 ESCRITA EM DDL
-- O legado tem "PCD". O que a lei exige que o empregador saiba é SE a pessoa é
-- pessoa com deficiência — a cota do art. 93 da Lei 8.213 conta cabeças, não
-- condições. QUAL é a deficiência é dado de saúde, e o projeto não guarda dado de
-- saúde além de aptidão e validade. Um `text` aqui aceitaria "cadeirante" no
-- primeiro import, e ninguém veria: por isso o tipo é `boolean` e o passo 2 da
-- garantia falha alto se ele deixar de ser.
--
-- ⛔ `race_color` E `disability` SÃO SENSÍVEIS E JÁ ESTÃO NO LUGAR CERTO
-- Estão em `app.employee_pii`, cuja policy `pii_read` (migration 04) exige
-- `util.can_see_domain(tenant_id, 'pii')` ALÉM do escopo. Nenhuma policy é
-- alterada aqui — a proteção já existia e é herdada pela coluna nova. O passo 4
-- confere isso em vez de presumir.
--
-- ⛔ `dependents_names` É NOME DE TERCEIRO
-- Não é dado do colaborador: é dado de quem não assinou contrato nenhum com o
-- cliente. `SPEC-DP.md` §5: "mesma proteção de pii, nunca em view pública". O
-- passo 5 varre a superfície pública atrás dele.
--
-- ⚠️ `shift_label` É TEXTO LIVRE DE PROPÓSITO, E TEM PRAZO
-- "10:00 AS 22:00 INT 14:30 AS 15:45" é como o legado guarda jornada hoje.
-- Preservado como texto até o Quadro de Postos cobrir todos os colaboradores, e
-- então descontinuado (SPEC §1j). Nada nesta etapa calcula sobre ele — quem
-- calcular jornada usa `app.expected_workday`, que é derivada e por dia.
--
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

alter table app.employee_pii
  add column if not exists marital_status   text,
  add column if not exists race_color       text,
  add column if not exists education_level  text,
  add column if not exists disability       boolean,
  add column if not exists dependents_count integer,
  add column if not exists dependents_names text[];

-- Quantidade negativa de dependente não é estado possível do mundo — é linha de
-- planilha malformada chegando pelo import. Barrar aqui é mais barato do que
-- descobrir no fechamento.
alter table app.employee_pii
  drop constraint if exists employee_pii_dependents_count_check;
alter table app.employee_pii
  add constraint employee_pii_dependents_count_check
  check (dependents_count is null or dependents_count >= 0);

alter table app.employee_position
  add column if not exists workload_minutes integer,
  add column if not exists shift_label      text;

alter table app.employee_position
  drop constraint if exists employee_position_workload_check;
alter table app.employee_position
  add constraint employee_position_workload_check
  check (workload_minutes is null or workload_minutes > 0);

comment on column app.employee_pii.disability is
  'BOOLEANO, e só. A cota legal conta pessoas; qual é a deficiência é dado de saúde '
  'e o produto não o guarda (regra 10). Nunca virar texto, nunca ganhar uma coluna '
  'irmã com o tipo.';
comment on column app.employee_pii.race_color is
  'Dado sensível. Protegido pelo domínio pii da policy pii_read — a coluna não tem '
  'proteção própria e não precisa de uma: ela herda a da tabela.';
comment on column app.employee_pii.dependents_names is
  'Nome de TERCEIRO. Mesma proteção de pii e nunca em view pública: quem aparece '
  'aqui não assinou contrato com o cliente.';
comment on column app.employee_position.workload_minutes is
  'Carga horária contratada, em minutos. Minuto e não hora pela mesma razão de '
  'app.deviation_event.minutes: 6h20 não cabe em decimal sem arredondar.';
comment on column app.employee_position.shift_label is
  'Jornada como o legado a escreve ("10:00 AS 22:00 INT 14:30 AS 15:45"). Texto livre, '
  'com prazo: sai quando o Quadro de Postos cobrir todos. Não é insumo de cálculo.';

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v_coluna    text;
  v_tipo      text;
  v_nullable  text;
  v_proibida  text;
  v_qual      text;
  v_tenant    uuid;
  v_company   uuid;
  v_employee  uuid;
  v_recusou   boolean := false;
  v_esperado  constant text[][] := array[
    ['employee_pii',      'marital_status',   'text'],
    ['employee_pii',      'race_color',       'text'],
    ['employee_pii',      'education_level',  'text'],
    ['employee_pii',      'disability',       'boolean'],
    ['employee_pii',      'dependents_count', 'integer'],
    ['employee_pii',      'dependents_names', 'ARRAY'],
    ['employee_position', 'workload_minutes', 'integer'],
    ['employee_position', 'shift_label',      'text']
  ];
  i int;
begin
  -- 1. As oito existem, com o tipo declarado e anuláveis.
  for i in 1 .. array_length(v_esperado, 1) loop
    v_coluna := v_esperado[i][2];
    select data_type, is_nullable into v_tipo, v_nullable
      from information_schema.columns
     where table_schema = 'app' and table_name = v_esperado[i][1]
       and column_name = v_coluna;
    if v_tipo is null then
      raise exception 'app.%.% não existe', v_esperado[i][1], v_coluna;
    end if;
    if v_tipo <> v_esperado[i][3] then
      raise exception 'app.%.% é %, esperava %',
        v_esperado[i][1], v_coluna, v_tipo, v_esperado[i][3];
    end if;
    if v_nullable <> 'YES' then
      raise exception
        'app.%.% é NOT NULL — a coluna era aditiva e passou a recusar a ficha que já existe',
        v_esperado[i][1], v_coluna;
    end if;
  end loop;

  -- 2. ⛔ O TIPO DE `disability`, DITO DE NOVO E SOZINHO
  --    O passo 1 já o compara, mas dentro de um laço que roda oito vezes: a
  --    mensagem dele fala de "tipo errado". Esta fala do que o tipo errado
  --    SIGNIFICA, porque quem ler o vermelho precisa saber que a correção não é
  --    trocar o tipo de volta e seguir, é apagar o que foi gravado.
  select data_type into v_tipo from information_schema.columns
   where table_schema = 'app' and table_name = 'employee_pii' and column_name = 'disability';
  if v_tipo <> 'boolean' then
    raise exception
      'app.employee_pii.disability é % — ela guarda o BOOLEANO legal, jamais a condição (regra 10)',
      v_tipo;
  end if;

  -- 3. E nenhuma coluna irmã carregando a condição por outro nome. Mesmo
  --    instrumento do passo 3 de `dp_leave_extension`: a regra 10 vive numa
  --    asserção, não num cabeçalho.
  select string_agg(column_name, ', ') into v_proibida
    from information_schema.columns
   where table_schema = 'app' and table_name = 'employee_pii'
     and column_name ~* '(cid|diagn|deficiencia_tipo|disability_type|disability_kind|restric)';
  if v_proibida is not null then
    raise exception
      'REGRA 10 VIOLADA: app.employee_pii ganhou coluna de condição -> %', v_proibida;
  end if;

  -- 4. O domínio sensível continua sendo o que protege as duas colunas novas.
  --    Nenhuma policy foi tocada — este passo prova que a herança existe, e é o
  --    que impede alguém de "resolver" um 403 removendo a exigência de domínio.
  select pg_get_expr(p.polqual, p.polrelid) into v_qual
    from pg_policy p
   where p.polrelid = 'app.employee_pii'::regclass and p.polname = 'pii_read';
  if v_qual is null then
    raise exception 'a policy pii_read sumiu de app.employee_pii';
  end if;
  if v_qual not like '%can_see_domain%' or v_qual not like '%pii%' then
    raise exception
      'pii_read não exige mais o domínio pii (%) — race_color e disability ficaram sem a proteção que herdavam',
      v_qual;
  end if;

  -- 5. ⛔ NADA DISSO CHEGOU À SUPERFÍCIE PÚBLICA
  --    `dependents_names` é nome de terceiro; `race_color` e `disability` são
  --    sensíveis. A varredura é a mesma ideia do item 8 de
  --    `scripts/99_verificacao_rls.sql`, feita aqui para que a migration falhe
  --    junto com a view que a expusesse, no mesmo PR.
  select string_agg(format('%s.%s', c.relname, a.attname), ', ') into v_proibida
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    join pg_attribute a on a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped
   where n.nspname = 'public' and c.relkind = 'v'
     and a.attname in ('race_color', 'disability', 'dependents_names', 'dependents_count');
  if v_proibida is not null then
    raise exception 'FALHA: dado sensível da ficha exposto em view pública -> %', v_proibida;
  end if;

  -- 6. A prova viva: os valores entram, e a quantidade negativa não.
  select t.id into v_tenant from app.tenant t order by t.created_at limit 1;
  if v_tenant is null then
    raise notice 'sem tenant: prova viva pulada (a estrutura já foi verificada acima)';
    return;
  end if;

  insert into app.company (tenant_id, legal_name, active)
  values (v_tenant, '__dp_cf_prova__', false)
  returning id into v_company;
  insert into app.employee (tenant_id, company_id, name)
  values (v_tenant, v_company, '__dp_cf_prova__')
  returning id into v_employee;

  -- a) a ficha completa entra;
  insert into app.employee_pii
    (employee_id, tenant_id, marital_status, race_color, education_level,
     disability, dependents_count, dependents_names)
  values (v_employee, v_tenant, 'casado', 'parda', 'medio_completo',
          true, 2, array['__dp_cf_dep_1__', '__dp_cf_dep_2__']);

  insert into app.employee_position
    (tenant_id, employee_id, effective_from, cargo, workload_minutes, shift_label)
  values (v_tenant, v_employee, date '2026-01-01', '__dp_cf_prova__',
          220 * 60, '10:00 AS 22:00 INT 14:30 AS 15:45');

  -- b) e a quantidade negativa é barrada.
  begin
    update app.employee_pii set dependents_count = -1 where employee_id = v_employee;
  exception when check_violation then
    v_recusou := true;
  end;
  if not v_recusou then
    raise exception
      'app.employee_pii aceitou dependents_count negativo — a coluna virou texto numérico';
  end if;

  delete from app.employee_position where employee_id = v_employee;
  delete from app.employee_pii      where employee_id = v_employee;
  delete from app.employee          where id = v_employee;
  delete from app.company           where id = v_company;

  raise notice
    'OK: ficha cadastral estendida — disability é booleano, o domínio pii continua de pé e nada disso alcança public.';
end $$;
