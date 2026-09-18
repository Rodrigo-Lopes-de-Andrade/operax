-- ============================================================================
-- OperaX — assistant_run_link. THE TURN SAYS WHICH VERSION PRODUCED IT
-- ----------------------------------------------------------------------------
-- Design in `docs/SPEC-AGENTE.md` §3c, plus the owner decision of 17/09/2026
-- on §7.1 (third way: `draft_content_hash`). Three columns on `app.ai_query`,
-- the log of executions that until now had no anchor (SPEC §0.3):
--
--   prompt_version_id   the version on the air when the turn ran — the TENANT
--                       version if the tenant has published, otherwise the
--                       PLATFORM version (dispatch decision 2). NULL means
--                       "before versioning": the rows that already exist have
--                       no version, and inventing one for them would be a lie
--                       written down. The FK has NO cascade — a version is
--                       never deleted, and the FK is what makes that so.
--   is_dry_run          the "Teste" tab. Out of every average and out of the
--                       executions screen: a test in the cost-per-question
--                       figure is noise, not traffic.
--   draft_content_hash  §7.1 decided: testing the draft does not freeze a
--                       version. The sha256 (hex, lower case) of the text
--                       that was tested identifies it without versioning.
--                       Only ever set on a dry run — the check says so.
--
-- NOTHING ELSE MOVES. No policy, no grant, no view: `ai_query_read` (own rows
-- or admin, migration 09) stays exactly as it is, and the proof pins the set
-- of policies so that a fourth one is scope without a decision. There is no
-- scope trigger on `prompt_version_id` and it is not meant to have one: this
-- is a log, and the backend writes it with the id it just read through the
-- pointer as the user. The FK guarantees the version exists, not whose it is —
-- measured, not asserted, in `scripts/97_teste_assistente.sql` §A3.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. The three columns
-- ---------------------------------------------------------------------------
alter table app.ai_query
  add column if not exists prompt_version_id uuid references app.assistant_prompt_version(id);
alter table app.ai_query
  add column if not exists is_dry_run boolean not null default false;
alter table app.ai_query
  add column if not exists draft_content_hash text;

-- The hash only exists on a dry run, and only in one shape. Two named checks
-- rather than one so the refusal names what was wrong.
alter table app.ai_query
  drop constraint if exists ai_query_draft_hash_only_in_dry_run;
alter table app.ai_query
  add  constraint ai_query_draft_hash_only_in_dry_run
    check (draft_content_hash is null or is_dry_run);
alter table app.ai_query
  drop constraint if exists ai_query_draft_hash_format;
alter table app.ai_query
  add  constraint ai_query_draft_hash_format
    check (draft_content_hash is null or draft_content_hash ~ '^[0-9a-f]{64}$');

-- ---------------------------------------------------------------------------
-- 2. The index the executions screen and the cost figure read: real traffic only
-- ---------------------------------------------------------------------------
create index if not exists ai_query_dry_run_idx
  on app.ai_query (tenant_id, created_at desc) where not is_dry_run;

-- ---------------------------------------------------------------------------
-- 3. Comments — the data dictionary is generated from these
-- ---------------------------------------------------------------------------
comment on column app.ai_query.prompt_version_id is
  'A versão do prompt no ar quando o turno rodou: a versão de tenant apontada, '
  'ou, se o tenant nunca publicou, a versão de plataforma apontada. Nulo = '
  'antes do versionamento — nunca inventar uma versão para linha antiga. FK '
  'sem cascade: versão nunca é apagada. No teste de rascunho aponta para a '
  'plataforma (a única camada que de fato é versão) e draft_content_hash '
  'identifica o texto testado.';
comment on column app.ai_query.is_dry_run is
  'true = a aba Teste. Fora de toda média de custo e fora da tela de '
  'execuções: o índice parcial ai_query_dry_run_idx só cobre o tráfego real.';
comment on column app.ai_query.draft_content_hash is
  'SPEC-AGENTE §7.1, decidida pelo dono em 17/09/2026 (terceira via): o sha256 '
  'em hex minúsculo do texto do rascunho testado, que o identifica sem virar '
  'versão. Só num dry run (check); nulo quando o teste rodou com as camadas '
  'publicadas ou quando o turno é real.';

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_type     text;
  v_nullable text;
  v_default  text;
  v_deltype  "char";
  v_indexdef text;
  v_policies text[];
begin
  -- 1. The three columns, with their types.
  select data_type, is_nullable into v_type, v_nullable
    from information_schema.columns
   where table_schema = 'app' and table_name = 'ai_query' and column_name = 'prompt_version_id';
  if v_type is distinct from 'uuid' or v_nullable is distinct from 'YES' then
    raise exception 'app.ai_query.prompt_version_id is not a nullable uuid (type %, nullable %)', v_type, v_nullable;
  end if;

  select data_type, is_nullable, column_default into v_type, v_nullable, v_default
    from information_schema.columns
   where table_schema = 'app' and table_name = 'ai_query' and column_name = 'is_dry_run';
  if v_type is distinct from 'boolean' or v_nullable is distinct from 'NO' or v_default is distinct from 'false' then
    raise exception 'app.ai_query.is_dry_run is not boolean not null default false (type %, nullable %, default %)', v_type, v_nullable, v_default;
  end if;

  select data_type, is_nullable into v_type, v_nullable
    from information_schema.columns
   where table_schema = 'app' and table_name = 'ai_query' and column_name = 'draft_content_hash';
  if v_type is distinct from 'text' or v_nullable is distinct from 'YES' then
    raise exception 'app.ai_query.draft_content_hash is not a nullable text (type %, nullable %)', v_type, v_nullable;
  end if;

  -- 2. The FK to the version, with NO cascade: `a` = no action.
  select c.confdeltype into v_deltype
    from pg_constraint c
   where c.conrelid = 'app.ai_query'::regclass
     and c.contype = 'f'
     and c.confrelid = 'app.assistant_prompt_version'::regclass;
  if v_deltype is null then
    raise exception 'app.ai_query.prompt_version_id has no FK to app.assistant_prompt_version';
  end if;
  if v_deltype <> 'a' then
    raise exception 'app.ai_query.prompt_version_id FK cascades (confdeltype %) — a version pointed by a turn must be undeletable', v_deltype;
  end if;

  -- 3. The two checks, by name.
  if not exists (select 1 from pg_constraint where conrelid = 'app.ai_query'::regclass
                    and conname = 'ai_query_draft_hash_only_in_dry_run' and contype = 'c') then
    raise exception 'check ai_query_draft_hash_only_in_dry_run is missing';
  end if;
  if not exists (select 1 from pg_constraint where conrelid = 'app.ai_query'::regclass
                    and conname = 'ai_query_draft_hash_format' and contype = 'c') then
    raise exception 'check ai_query_draft_hash_format is missing';
  end if;

  -- 4. The partial index, with its predicate.
  select indexdef into v_indexdef
    from pg_indexes
   where schemaname = 'app' and tablename = 'ai_query' and indexname = 'ai_query_dry_run_idx';
  if v_indexdef is null then
    raise exception 'index ai_query_dry_run_idx is missing';
  end if;
  if v_indexdef not like '%WHERE (NOT is_dry_run)%' then
    raise exception 'ai_query_dry_run_idx is not partial on NOT is_dry_run: %', v_indexdef;
  end if;

  -- 5. The policy set of app.ai_query did not move: exactly `ai_query_read`.
  --    Measured on the ensaio before this migration was written.
  select coalesce(array_agg(policyname order by policyname), '{}') into v_policies
    from pg_policies where schemaname = 'app' and tablename = 'ai_query';
  if v_policies <> array['ai_query_read'] then
    raise exception 'app.ai_query policies changed: % (expected only ai_query_read)', v_policies;
  end if;
  if not (select relrowsecurity from pg_class where oid = 'app.ai_query'::regclass) then
    raise exception 'app.ai_query without RLS — rule 3 of CLAUDE.md';
  end if;

  raise notice 'OK: assistant run link — prompt_version_id (FK, no cascade), is_dry_run, draft_content_hash (two checks), partial index on real traffic, and ai_query_read untouched.';
end $$;
