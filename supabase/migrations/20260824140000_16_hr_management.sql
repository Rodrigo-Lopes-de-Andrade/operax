-- ============================================================================
-- OperaX — 16. HR MANAGEMENT: THE ALTERNATE KEY AND ONE IMPORT TYPE PER TABLE
-- ----------------------------------------------------------------------------
-- The customer's HR lives in a 17-tab spreadsheet. This migration is the whole
-- database half of bringing it in, and it adds NO table: every destination was
-- already built by migrations 04–08. Two things were missing.
--
-- 1. THE ALTERNATE KEY
--
-- The mirror knows people by `registration_number` (matrícula). The spreadsheet
-- knows them by an "ID RH" that exists nowhere else. Linking the two is a human
-- act done once, so `hr_code` is nullable — it is empty for everybody until the
-- link template comes back filled.
--
-- It is an ALTERNATE key, never a composite one. Each identifies a person on its
-- own, and requiring both together would break the very phase the column exists
-- for, when `hr_code` is still null everywhere. What the two must never do is
-- disagree: a row whose matrícula and ID RH point at DIFFERENT people is an
-- error on that line, with both names in the message. The database cannot see
-- that — it is a property of an import row, not of a stored row — so it is
-- enforced in `operax/rh/validators.py`. What the database does enforce is that
-- neither key is ever ambiguous inside a tenant.
--
-- The index is PARTIAL. A plain unique index would let exactly one row hold a
-- null and refuse the second, which is the opposite of what "empty until linked"
-- needs.
--
-- 2. ONE IMPORT TYPE PER TEMPLATE
--
-- "One table at a time" was a convention in the decision document. Here it
-- becomes a constraint: seven new values on `app.file_import.type`, one per
-- template. A file that tries to be two tables at once has no type to be.
--
-- WHAT THIS MIGRATION DELIBERATELY DOES NOT DO
--
--   * No RLS change. Writing stays exclusive to Caminho 2 — FastAPI with
--     `service_role` and its own re-check of role and domain. The panel gains
--     no write grant, and the proof block below asserts that it did not.
--   * No field-ownership table. Which fields the sync owns and which HR owns is
--     a backend constant (`operax/rh/ownership.py`), so changing it takes a
--     deploy and a review. A panel-editable ownership matrix is a panel-editable
--     way to overwrite the source of truth.
--   * No column for CID or diagnosis, here or anywhere. Rule 10 is denied in
--     three layers, and this is the first: no column, no template column, no
--     screen field.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. `hr_code` — the HR side's own identifier for a person
-- ---------------------------------------------------------------------------
alter table app.employee add column if not exists hr_code text;

create unique index if not exists employee_hr_code_unique
  on app.employee (tenant_id, hr_code) where hr_code is not null;

comment on column app.employee.hr_code is
  'ID RH do cliente. Chave ALTERNATIVA — nunca composta com a matrícula: cada '
  'uma identifica sozinha, e divergência entre elas é erro de linha no import. '
  'Anulável de propósito: fica vazia até o template de vínculo voltar preenchido.';

-- ---------------------------------------------------------------------------
-- 2. Um tipo de importação por template
--
-- O check é recriado com os sete valores novos somados aos existentes. Ler os
-- valores atuais do catálogo em vez de reescrevê-los à mão evita o modo de
-- falha clássico desta operação: repetir a lista de memória e apagar em
-- silêncio um valor que já está gravado em linha de produção.
-- ---------------------------------------------------------------------------
do $$
declare
  v_def    text;
  v_atuais text[];
  v_novos  text[] := array[
    'hr_link', 'hr_employee', 'hr_document', 'hr_leave',
    'hr_movement', 'hr_compensation', 'hr_agreement'
  ];
  v_final  text[];
begin
  select pg_get_constraintdef(oid) into v_def
  from pg_constraint
  where conrelid = 'app.file_import'::regclass and conname = 'file_import_type_check';

  if v_def is null then
    raise exception 'file_import_type_check não encontrada: o alvo desta migration mudou de nome';
  end if;

  -- Duas formas, porque o Postgres renderiza a mesma restrição de dois jeitos:
  -- `ARRAY['a'::text, ...]` quando ela foi escrita assim, e `'{a,b}'::text[]`
  -- quando veio de um array ligado por parâmetro. Ler só uma delas faz esta
  -- migration explodir na segunda execução.
  select array_agg(distinct valor order by valor) into v_atuais
  from (
    select unnest(regexp_matches(v_def, '''([a-z_]+)''::text', 'g')) as valor
    union all
    select unnest(string_to_array((regexp_matches(v_def, '''\{([a-z_,]+)\}''::text\[\]'))[1], ','))
  ) t;

  if v_atuais is null then
    raise exception 'não consegui ler os valores atuais de file_import_type_check: %', v_def;
  end if;

  v_final := (select array_agg(distinct v order by v) from unnest(v_atuais || v_novos) v);

  alter table app.file_import drop constraint file_import_type_check;
  -- ARRAY[...], que é como o catálogo já guardava esta restrição: manter a forma
  -- deixa o `pg_get_constraintdef` legível e a asserção abaixo direta.
  execute format(
    'alter table app.file_import add constraint file_import_type_check check (type = any (array[%s]))',
    (select string_agg(quote_literal(v), ', ' order by v) from unnest(v_final) v)
  );
  raise notice 'file_import.type aceita % valores', array_length(v_final, 1);
end $$;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_faltando text[];
  v_gravavel text;
begin
  -- 1. A chave alternativa existe e é única por tenant, sem prender os nulos.
  if not exists (
    select 1 from information_schema.columns
    where table_schema = 'app' and table_name = 'employee' and column_name = 'hr_code'
  ) then
    raise exception 'app.employee.hr_code não foi criada';
  end if;
  if not exists (
    select 1 from pg_index i
    join pg_class c on c.oid = i.indexrelid
    where c.relname = 'employee_hr_code_unique' and i.indisunique and i.indpred is not null
  ) then
    raise exception 'employee_hr_code_unique não é um índice único PARCIAL: '
                    'sem o predicado, só um colaborador poderia ficar sem ID RH';
  end if;

  -- 2. Os sete tipos entraram, e nenhum antigo saiu no caminho.
  select array_agg(t order by t) into v_faltando
  from unnest(array['hr_link','hr_employee','hr_document','hr_leave',
                    'hr_movement','hr_compensation','hr_agreement',
                    'folha','payroll_charge','employee','cost_center',
                    'roster','benefit','other']) t
  where pg_get_constraintdef(
          (select oid from pg_constraint
            where conrelid = 'app.file_import'::regclass
              and conname = 'file_import_type_check')
        ) not like '%' || quote_literal(t) || '%';
  if v_faltando is not null then
    raise exception 'file_import.type não aceita: %', array_to_string(v_faltando, ', ');
  end if;

  -- 3. O painel não ganhou escrita em tabela de RH. É a asserção que o R1 pede,
  --    e ela existe porque a etapa inteira é sobre escrita: o caminho continua
  --    sendo o FastAPI, e um grant a mais aqui abriria o outro.
  select string_agg(format('%s (%s)', c.relname, p.priv), ', ' order by c.relname, p.priv)
    into v_gravavel
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  cross join lateral (values ('INSERT'), ('UPDATE'), ('DELETE')) as p(priv)
  where n.nspname = 'app'
    and c.relkind = 'r'
    and c.relname in ('employee_pii', 'employee_compensation', 'employee_position',
                      'document', 'occupational_exam', 'leave_period',
                      'workforce_movement', 'financial_agreement', 'agreement_installment')
    and has_table_privilege('anon', c.oid, p.priv);
  if v_gravavel is not null then
    raise exception 'anon escreve em tabela de RH: %', v_gravavel;
  end if;

  raise notice 'OK: hr_code é chave alternativa única por tenant, e sete templates têm tipo próprio.';
end $$;
