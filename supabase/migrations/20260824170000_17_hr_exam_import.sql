-- ============================================================================
-- OperaX — 17. THE IMPORT TYPE THAT ASO SHOULD ALWAYS HAVE HAD
-- ----------------------------------------------------------------------------
-- Migration 16 created seven import types, one per template, and folded the
-- occupational exam into `hr_document` because the product groups them as one
-- domain ("Documentos + ASO"). The grouping is right on screen and wrong in the
-- database: they are two tables with two different reasons to exist.
--
--   `app.document`          — `storage_path` is NOT NULL. A document arrives
--                             with its file; a spreadsheet row cannot carry one.
--                             It has no round trip, and that is correct.
--   `app.occupational_exam` — no file requirement at all (`document_id` is
--                             nullable), and migration 08 already grants insert,
--                             update and delete to `authenticated` behind a
--                             policy that asks for the `health` domain. It has
--                             every condition for a round trip except a name.
--
-- So the health domain was locked out of the initial load by a constraint that
-- belongs to a different table. The carga inicial of 24/08/2026 found it: the
-- converter had the ASO tab translated — `APTO` to `fit`, `PERIÓDICO` to
-- `periodic` — with nowhere to send it, and the expiry column that is the whole
-- reason the Colaboradores list exists had to be answered with seeded data.
--
-- This migration adds `hr_exam` to `app.file_import.type` and nothing else.
--
-- WHAT IT DELIBERATELY DOES NOT DO
--
--   * No policy change. `exame_read` and `exame_write` already say what they
--     have to say: only whoever holds the `health` domain, and reading also
--     needs to reach the person. Writing keeps going through Caminho 2, which
--     re-checks the domain before opening the transaction.
--   * No new column. Aptitude and validity are what the table holds, and that is
--     all rule 10 allows it to hold: no diagnosis, no CID, no description of a
--     restriction — the `check` on `result` is the whole vocabulary.
--   * No grant. The proof block asserts `anon` still cannot write.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. `hr_exam` joins the catalogue
--
-- Same shape as migration 16: read the values the constraint holds today and add
-- to them, instead of rewriting the list from memory. Repeating the list by hand
-- is how a value already stored on a production row disappears in silence.
-- ---------------------------------------------------------------------------
do $$
declare
  v_def    text;
  v_atuais text[];
  v_final  text[];
begin
  select pg_get_constraintdef(oid) into v_def
  from pg_constraint
  where conrelid = 'app.file_import'::regclass and conname = 'file_import_type_check';

  if v_def is null then
    raise exception 'file_import_type_check não encontrada: o alvo desta migration mudou de nome';
  end if;

  select array_agg(distinct valor order by valor) into v_atuais
  from (
    select unnest(regexp_matches(v_def, '''([a-z_]+)''::text', 'g')) as valor
    union all
    select unnest(string_to_array((regexp_matches(v_def, '''\{([a-z_,]+)\}''::text\[\]'))[1], ','))
  ) t;

  if v_atuais is null then
    raise exception 'não consegui ler os valores atuais de file_import_type_check: %', v_def;
  end if;

  if 'hr_exam' = any(v_atuais) then
    raise notice 'file_import.type já aceita hr_exam';
    return;
  end if;

  v_final := (select array_agg(distinct v order by v) from unnest(v_atuais || array['hr_exam']) v);

  alter table app.file_import drop constraint file_import_type_check;
  execute format(
    'alter table app.file_import add constraint file_import_type_check check (type = any (array[%s]))',
    (select string_agg(quote_literal(v), ', ' order by v) from unnest(v_final) v)
  );
  raise notice 'file_import.type aceita % valores', array_length(v_final, 1);
end $$;

comment on table app.occupational_exam is
  'DADO DE SAÚDE (LGPD art. 5º II). Sem diagnóstico, sem CID, sem descrição de restrição. '
  'Só aptidão e validade. Importável pelo template `hr_exam` desde a migration 17, por quem '
  'tem o domínio `health`.';

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_faltando text[];
  v_gravavel text;
begin
  -- 1. Os oito tipos de RH estão no catálogo.
  select array_agg(t) into v_faltando
  from unnest(array['hr_link','hr_employee','hr_document','hr_leave','hr_movement',
                    'hr_compensation','hr_agreement','hr_exam']) t
  where not exists (
    select 1 from pg_constraint
    where conrelid = 'app.file_import'::regclass
      and conname = 'file_import_type_check'
      and pg_get_constraintdef(oid) like '%' || quote_literal(t) || '%'
  );
  if v_faltando is not null then
    raise exception 'file_import.type não aceita: %', v_faltando;
  end if;

  -- 2. A política de saúde continua exigindo o domínio, e não só o papel.
  if not exists (
    select 1 from pg_policies
    where schemaname = 'app' and tablename = 'occupational_exam' and policyname = 'exame_write'
      and qual like '%can_see_domain%health%'
  ) then
    raise exception 'exame_write não exige mais o domínio health';
  end if;

  -- 3. `anon` continua sem escrever no exame.
  select 'occupational_exam' into v_gravavel
  where has_table_privilege('anon', 'app.occupational_exam', 'INSERT')
     or has_table_privilege('anon', 'app.occupational_exam', 'UPDATE')
     or has_table_privilege('anon', 'app.occupational_exam', 'DELETE');
  if v_gravavel is not null then
    raise exception 'anon escreve em app.occupational_exam';
  end if;

  -- 4. Diagnóstico continua sem coluna. A regra 10 é negada aqui antes de ser
  --    negada no template.
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'app' and table_name = 'occupational_exam'
      and column_name in ('cid', 'diagnostico', 'diagnosis', 'restricao', 'restriction')
  ) then
    raise exception 'app.occupational_exam ganhou coluna de diagnóstico ou restrição';
  end if;

  raise notice 'OK: ASO tem tipo de importação próprio, e nada mais mudou.';
end $$;
