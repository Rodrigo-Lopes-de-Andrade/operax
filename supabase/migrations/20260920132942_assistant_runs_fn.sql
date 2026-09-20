-- ============================================================================
-- OperaX — assistant_runs_fn. THE RUNS TAB, AND THE DRAFT THE SCREEN SAW
-- ----------------------------------------------------------------------------
-- Three objects, one file, because the first one is a signature change and the
-- other two are what reads what it writes. Design in `docs/SPEC-AGENTE.md`
-- §0.3 (the token columns existed and did not answer), §3c and §3d.
--
-- 1. `fn_publish_assistant_prompt` GAINS `p_seen_updated_at` AND A SIXTH
--    REFUSAL
-- Publishing froze whatever was in `app.assistant_draft` AT THE INSTANT OF THE
-- CALL, with nothing identifying the draft the person had read. Two admins in
-- the same minute: one publishes the other's text, which they never saw, and
-- the database has no way to refuse — `draft_unchanged` compares the draft
-- with the version ON THE AIR, never with what the screen was showing.
--
-- `draft_moved` is the SIXTH refusal and its POSITION IS THE CONTRACT: after
-- `draft_not_found` (with no draft there is nothing to compare) and BEFORE
-- `draft_empty` (a blank draft that MOVED is still a draft that moved: the
-- person would be told to write something when what they must be told is that
-- somebody else wrote). Null `p_seen_updated_at` = the screen did not send it,
-- which is today's behaviour, compatible with every existing caller.
--
-- ⚠️ THE SIGNATURE CHANGES, SO THE OLD FUNCTION IS DROPPED BY NAME AND ARITY
-- `create or replace` cannot add a parameter: it would leave TWO functions in
-- `public`, and the one-argument call would keep hitting the old body. The
-- `drop` is the only way, and it takes the GRANT with it — an unreplaced
-- `grant execute` is a Publicar button that 403s with nothing in the log, the
-- same trap this file's ancestor documented and that `trg_lock_down_new_
-- function` does not cover, because it does not fire for `public`.
--
-- 2. `fn_assistant_runs` — the real traffic of whoever calls
-- 3. `fn_assistant_cost_by_version` — cost per competência, BROKEN DOWN BY
--    VERSION. That is the gate of this stage: token without a version is a
--    number that cannot be turned into margin, because price follows the
--    model and the model may change between versions (SPEC §0.3).
--
-- ⛔ BOTH ARE `security invoker`, AND THAT IS THE WHOLE ROLE CUT
-- `ai_query_read` is `user_id = auth.uid() or util.is_admin(tenant_id)`: a
-- non-admin sees only their own turns. Inheriting that is the design — a
-- definer here would be a second, hand-written copy of the same rule, drifting
-- at the first change, and would answer for every tenant's log. There is NO
-- role filter in the body, on purpose.
--
-- ⛔ `not is_dry_run` IN BOTH, AND IT IS AN ASSERTION, NOT A COMMENT
-- The Teste tab runs real queries over real data, and it runs many. A test in
-- the average cost per turn is noise that moves the only number the stage
-- produces. The partial index `ai_query_dry_run_idx` was created with this
-- predicate (`assistant_run_link`), so the filter is also what makes the
-- window use it.
--
-- `version_label` IS FINISHED TEXT, AND `'antes do versionamento'` IS NOT `v1`
-- Rows written before `assistant_run_link` have a null `prompt_version_id`.
-- Labelling them `v1` would invent provenance, which is the exact error this
-- whole stage exists not to commit. The third branch is the one the `97`
-- MEASURES and does not assert: the FK accepts a version of another tenant
-- (it is a log; there is no scope trigger on it, on purpose), and under
-- invoker that row does not come back from the join — the label says so
-- instead of coming back empty.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Publishing knows which draft the screen saw
-- ---------------------------------------------------------------------------
-- The body is `assistant_publish_fn` verbatim plus the third refusal and the
-- `updated_at` read by the same locking select. Everything that migration
-- asserts (definer locked, anon out, lock first, max + 1, the tenant-bound
-- final update) holds here and is re-asserted at the bottom.
drop function if exists public.fn_publish_assistant_prompt(uuid);

create or replace function public.fn_publish_assistant_prompt(
  p_tenant_id       uuid,
  p_seen_updated_at timestamptz default null
)
returns table (version_id uuid, version_number integer, previous_version_id uuid)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_draft_content text;
  v_draft_seen    timestamptz;
  v_found         boolean;
  v_pointed       uuid;
  v_number        integer;
  v_new_id        uuid;
begin
  -- Lock the draft. First of everything: serialises every publication of
  -- this tenant from here on. Whether it exists is judged only after the role.
  select d.content, d.updated_at
    into v_draft_content, v_draft_seen
    from app.assistant_draft d
   where d.tenant_id = p_tenant_id
     for update;
  v_found := found;

  -- 1. Definer does not inherit RLS: the role is checked here, by the same
  --    helper the draft policy uses. `auth.uid()` is a session setting, so it
  --    answers the same under definer with an empty search_path.
  if not util.is_admin(p_tenant_id) then
    raise exception 'not_admin' using errcode = 'P0001';
  end if;

  -- 2. Nothing to publish.
  if not v_found then
    raise exception 'draft_not_found' using errcode = 'P0001';
  end if;

  -- 3. The draft moved under the screen: somebody else saved between the read
  --    and this call. Null = the caller did not say what it saw, which is the
  --    behaviour of every caller written before this parameter existed.
  if p_seen_updated_at is not null and v_draft_seen is distinct from p_seen_updated_at then
    raise exception 'draft_moved' using errcode = 'P0001';
  end if;

  -- 4. Blank text is not a version.
  if btrim(v_draft_content) = '' then
    raise exception 'draft_empty' using errcode = 'P0001';
  end if;

  -- 5. No doctrine under it, no tenant layer on top of it.
  if not exists (
    select 1 from app.assistant_prompt_pointer p
     where p.layer = 'platform' and p.tenant_id is null
  ) then
    raise exception 'platform_layer_missing' using errcode = 'P0001';
  end if;

  -- 6. Compared with the version ON THE AIR (the pointer), never with the
  --    latest one: a rollback leaves the pointer behind the newest version.
  select p.version_id
    into v_pointed
    from app.assistant_prompt_pointer p
   where p.tenant_id = p_tenant_id and p.layer = 'tenant';
  if v_pointed is not null and exists (
    select 1 from app.assistant_prompt_version v
     where v.id = v_pointed and v.content = v_draft_content
  ) then
    raise exception 'draft_unchanged' using errcode = 'P0001';
  end if;

  -- Freeze: the next number in the tenant's scope, safe under the lock above.
  select coalesce(max(v.version_number), 0) + 1
    into v_number
    from app.assistant_prompt_version v
   where v.tenant_id = p_tenant_id and v.layer = 'tenant';

  insert into app.assistant_prompt_version
         (tenant_id, layer, version_number, content, created_by)
  values (p_tenant_id, 'tenant', v_number, v_draft_content, auth.uid())
  returning id into v_new_id;

  -- Move the pointer (first publication inserts it; the partial index is the
  -- conflict target — its predicate has to be named for the inference).
  insert into app.assistant_prompt_pointer (tenant_id, layer, version_id, updated_at, updated_by)
  values (p_tenant_id, 'tenant', v_new_id, now(), auth.uid())
  on conflict (tenant_id, layer) where tenant_id is not null
  do update set version_id = excluded.version_id,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by;

  -- The draft now descends from the version it just became.
  update app.assistant_draft d
     set frozen_from_version_id = v_new_id,
         updated_at             = now(),
         updated_by             = auth.uid()
   where d.tenant_id = p_tenant_id;

  return query select v_new_id, v_number, v_pointed;
end $$;

comment on function public.fn_publish_assistant_prompt(uuid, timestamptz) is
  'Publica o rascunho do tenant: congela em versão nova (imutável) e move o '
  'ponteiro, na mesma transação. Seis recusas, nesta ordem, cada uma P0001 com '
  'a mensagem = código: not_admin, draft_not_found, draft_moved, draft_empty, '
  'platform_layer_missing, draft_unchanged (idêntico à versão APONTADA, não à '
  'última). not_admin vem antes de tudo: o owner de outro tenant não aprende se '
  'este tem rascunho. draft_moved compara o updated_at do rascunho com o que a '
  'tela leu (p_seen_updated_at); nulo = a tela não mandou, e o comportamento é '
  'o de antes deste parâmetro. A primeira instrução trava o rascunho (for '
  'update) e serializa publicações concorrentes do mesmo tenant. Definer: '
  'checa util.is_admin ela mesma. Devolve (version_id, version_number, '
  'previous_version_id).';

-- The drop above took the grants with it. Written again, both sides.
revoke execute on function public.fn_publish_assistant_prompt(uuid, timestamptz) from public, anon;
grant  execute on function public.fn_publish_assistant_prompt(uuid, timestamptz) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. The runs of whoever calls, newest first
-- ---------------------------------------------------------------------------
-- `p_weeks` counts back from the current week INCLUDING it, the same window
-- `fn_delivery_by_channel` uses: the default of 8 is the current week plus the
-- seven before. `date_trunc('week')` is ISO (Monday), in the session time zone
-- — UTC on Supabase — the same week the rest of the panel uses.
create or replace function public.fn_assistant_runs(p_weeks integer default 8)
returns table (
  created_at        timestamptz,
  question          text,
  metric_code       text,
  rows_returned     integer,
  latency_ms        integer,
  input_tokens      integer,
  output_tokens     integer,
  model             text,
  refused           boolean,
  refusal_reason    text,
  prompt_version_id uuid,
  version_label     text
)
language sql stable security invoker set search_path = ''
as $$
  select q.created_at,
         q.question,
         q.metric_code,
         q.rows_returned,
         q.latency_ms,
         q.input_tokens,
         q.output_tokens,
         q.model,
         q.refused,
         q.refusal_reason,
         q.prompt_version_id,
         case
           when q.prompt_version_id is null then 'antes do versionamento'
           when v.id is null                then 'versão fora do alcance'
           when v.layer = 'platform'        then 'plataforma v' || v.version_number
           else                                  'v' || v.version_number
         end as version_label
    from app.ai_query q
    left join app.assistant_prompt_version v on v.id = q.prompt_version_id
   where not q.is_dry_run
     and q.created_at >= date_trunc('week', now()) - make_interval(weeks => greatest(p_weeks, 1) - 1)
   order by q.created_at desc;
$$;

comment on function public.fn_assistant_runs(integer) is
  'Os turnos REAIS (nunca dry run) das últimas p_weeks semanas, a atual '
  'inclusa, mais novo primeiro, com a versão de prompt que os produziu. '
  'version_label é texto pronto: "v3" para camada de tenant, "plataforma v1" '
  'para a doutrina, e "antes do versionamento" quando prompt_version_id é nulo '
  '— nunca "v1", que seria inventar procedência. Security INVOKER: lê '
  'app.ai_query pela policy ai_query_read (próprio turno OU is_admin), então '
  'quem não é admin vê só os próprios turnos, e isso é o recorte inteiro.';

revoke execute on function public.fn_assistant_runs(integer) from public, anon;
grant  execute on function public.fn_assistant_runs(integer) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Cost per competência, broken down by version — the gate
-- ---------------------------------------------------------------------------
-- Same window, same invoker cut, same `not is_dry_run`. Grouped by
-- (competência, version, MODEL), and the model is in the key on purpose.
-- ⛔ Measured on 20/09/2026: the text that runs is TWO layers, and
-- `ai_query.prompt_version_id` records one — the tenant's, whenever the tenant
-- has a layer of its own. But the model is chosen by the PLATFORM layer (a
-- constraint forbids a model on the tenant layer), so republishing the
-- doctrine changes the price and does not move the label: two turns of the
-- same tenant, one on gpt-4o-mini and one on gpt-4o, landed in a single group.
-- Price is what this table exists to answer, and `model` is the column that
-- decides it — so it is part of the key. Owner's decision, 20/09/2026.
-- O tipo de retorno mudou quando `model` entrou na chave, e `create or replace`
-- não troca tipo de retorno: derruba-se pelo nome e aridade, e o grant é
-- reescrito abaixo porque o drop o leva junto.
drop function if exists public.fn_assistant_cost_by_version(integer);
create or replace function public.fn_assistant_cost_by_version(p_weeks integer default 8)
returns table (
  month_start       date,
  version_label     text,
  prompt_version_id uuid,
  model             text,
  runs              bigint,
  refused_runs      bigint,
  input_tokens      bigint,
  output_tokens     bigint,
  avg_latency_ms    numeric
)
language sql stable security invoker set search_path = ''
as $$
  select date_trunc('month', q.created_at)::date as month_start,
         case
           when q.prompt_version_id is null then 'antes do versionamento'
           when v.id is null                then 'versão fora do alcance'
           when v.layer = 'platform'        then 'plataforma v' || v.version_number
           else                                  'v' || v.version_number
         end                                     as version_label,
         q.prompt_version_id,
         q.model,
         count(*)                                as runs,
         count(*) filter (where q.refused)       as refused_runs,
         coalesce(sum(q.input_tokens), 0)::bigint  as input_tokens,
         coalesce(sum(q.output_tokens), 0)::bigint as output_tokens,
         avg(q.latency_ms)                       as avg_latency_ms
    from app.ai_query q
    left join app.assistant_prompt_version v on v.id = q.prompt_version_id
   where not q.is_dry_run
     and q.created_at >= date_trunc('week', now()) - make_interval(weeks => greatest(p_weeks, 1) - 1)
   group by 1, 2, 3, 4
   order by month_start desc, version_label, q.model nulls last;
$$;

comment on function public.fn_assistant_cost_by_version(integer) is
  'Custo por competência QUEBRADO POR VERSÃO de prompt E POR MODELO, nas '
  'últimas p_weeks semanas (a atual inclusa): turnos, recusas, tokens de '
  'entrada e de saída e latência média. É o que as colunas de token existiam '
  'para responder e não respondiam (SPEC-AGENTE §0.3). O modelo entra na '
  'chave porque é ele que vira preço, e a versão gravada é a do tenant: quem '
  'escolhe o modelo é a camada de plataforma, que o registro não guarda. Sem '
  'o modelo na chave, republicar a doutrina troca o preço sem mover o rótulo '
  'e a linha soma dois preços — medido em 20/09/2026, decisão do dono. Dry '
  'run fica FORA de toda média. Security INVOKER: o recorte é ai_query_read.';

revoke execute on function public.fn_assistant_cost_by_version(integer) from public, anon;
grant  execute on function public.fn_assistant_cost_by_version(integer) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
-- ⚠️ What it does NOT do, on purpose: it does not seed `ai_query` or users to
-- prove the role cut — the migration runs as the owner of the schema, who
-- bypasses RLS, so a functional proof here would prove nothing. The cut is
-- proved in `scripts/97_teste_assistente.sql` §A4, on `make db-test`.
do $$
declare
  v_oid    oid;
  v_secdef boolean;
  v_config text;
  v_src    text;
  v_body   text;
  v_cols   text[];
  v_name   text;
begin
  -- ------------------------------------------------------------------
  -- 1. The publish RPC: ONE signature, and it is the two-argument one.
  -- ------------------------------------------------------------------
  if (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
       where n.nspname = 'public' and p.proname = 'fn_publish_assistant_prompt') <> 1 then
    raise exception 'public.fn_publish_assistant_prompt must exist with exactly one signature — the one-argument call would keep hitting the old body';
  end if;
  select p.oid, p.prosecdef, coalesce(array_to_string(p.proconfig, ','), '')
    into v_oid, v_secdef, v_config
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname = 'fn_publish_assistant_prompt';
  -- Arity AND parameter names: the router calls by name, so a rename is a
  -- contract break the same way a missing argument is.
  if pg_get_function_identity_arguments(v_oid)
     <> 'p_tenant_id uuid, p_seen_updated_at timestamp with time zone' then
    raise exception 'public.fn_publish_assistant_prompt has the wrong signature: %',
      pg_get_function_identity_arguments(v_oid);
  end if;
  if not v_secdef or v_config not like '%search_path=%' then
    raise exception 'public.fn_publish_assistant_prompt lost definer or search_path';
  end if;

  -- The grant did NOT survive the drop and had to be written again.
  if has_function_privilege('anon', v_oid, 'EXECUTE') then
    raise exception 'anon can execute public.fn_publish_assistant_prompt';
  end if;
  if not has_function_privilege('authenticated', v_oid, 'EXECUTE') then
    raise exception 'authenticated cannot execute public.fn_publish_assistant_prompt — the drop took the grant and nobody wrote it back; the Publicar button would 403 with nothing in the log';
  end if;

  -- The SIX codes, in order, read from the catalogue.
  v_src  := pg_get_functiondef(v_oid);
  v_body := substr(v_src, position('begin' in lower(v_src)));
  if position('for update' in lower(v_body)) = 0
     or position('for update' in lower(v_body)) > position('not_admin' in v_body) then
    raise exception 'public.fn_publish_assistant_prompt decides before it locks — the lock must be the first statement';
  end if;
  -- And `updated_at` comes from the SAME statement that locks. Reading it in a
  -- select of its own, before the locking one, satisfies every assertion above
  -- and reopens the exact race `draft_moved` exists to close: measured with two
  -- sessions on 20/09/2026, the second admin's text got published under the
  -- first admin's eyes.
  if v_body !~ 'd\.content,\s*d\.updated_at[\s\S]{0,255}for update' then
    raise exception 'public.fn_publish_assistant_prompt reads updated_at outside the lock — draft_moved would compare against a value that can change before the write';
  end if;
  if not (position('not_admin' in v_body) < position('draft_not_found' in v_body)
      and position('draft_not_found' in v_body) < position('draft_moved' in v_body)
      and position('draft_moved' in v_body) < position('draft_empty' in v_body)
      and position('draft_empty' in v_body) < position('platform_layer_missing' in v_body)
      and position('platform_layer_missing' in v_body) < position('draft_unchanged' in v_body)) then
    raise exception 'public.fn_publish_assistant_prompt refuses in the wrong order: not_admin, draft_not_found, draft_moved, draft_empty, platform_layer_missing, draft_unchanged';
  end if;
  if v_body not like '%util.is_admin(p_tenant_id)%' then
    raise exception 'public.fn_publish_assistant_prompt does not check util.is_admin itself — definer inherits no RLS';
  end if;
  if v_body not like '%max(v.version_number)%' then
    raise exception 'public.fn_publish_assistant_prompt does not number by max + 1';
  end if;
  -- `draft_moved` is guarded by the null: a caller that says nothing keeps the
  -- old behaviour, and without this guard every old caller would be refused.
  if v_body !~ 'p_seen_updated_at is not null' then
    raise exception 'public.fn_publish_assistant_prompt raises draft_moved without guarding on a null p_seen_updated_at — every caller written before this parameter would be refused';
  end if;

  -- ------------------------------------------------------------------
  -- 2 and 3. The two reading functions: invoker, locked, anon out, and
  --          the dry run outside both of them.
  -- ------------------------------------------------------------------
  foreach v_name in array array['fn_assistant_runs', 'fn_assistant_cost_by_version'] loop
    if (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public' and p.proname = v_name) <> 1 then
      raise exception 'public.% must exist with exactly one signature', v_name;
    end if;
    select p.oid, p.prosecdef, coalesce(array_to_string(p.proconfig, ','), '')
      into v_oid, v_secdef, v_config
      from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public' and p.proname = v_name;

    -- Invoker is the whole role cut: `ai_query_read` is own-or-admin.
    if v_secdef then
      raise exception 'public.% is security definer — it would read every tenant''s log for anyone, and a non-admin would read turns that are not theirs', v_name;
    end if;
    if v_config not like '%search_path=%' then
      raise exception 'public.% has no search_path pinned', v_name;
    end if;
    if has_function_privilege('anon', v_oid, 'EXECUTE')
       or has_function_privilege('public', v_oid, 'EXECUTE') then
      raise exception 'anon/public can execute public.%', v_name;
    end if;
    if not has_function_privilege('authenticated', v_oid, 'EXECUTE') then
      raise exception 'authenticated cannot execute public.% — the tab would never load', v_name;
    end if;

    v_src := pg_get_functiondef(v_oid);
    if v_src not like '%from app.ai_query%' then
      raise exception 'public.% does not read app.ai_query', v_name;
    end if;
    -- ⛔ The dry run is out of both, and this is the assertion that says so.
    if v_src !~ 'not q\.is_dry_run' then
      raise exception 'public.% counts the dry run — the Teste tab would move the only number this stage produces', v_name;
    end if;
    -- `'antes do versionamento'` and never `v1` for a null version.
    if v_src not like '%antes do versionamento%' then
      raise exception 'public.% lost the label of the rows written before the versioning', v_name;
    end if;
    if v_src !~ 'q\.prompt_version_id is null' then
      raise exception 'public.% decides the label without testing prompt_version_id for null — a row from before the versioning would be attributed to a version nobody published', v_name;
    end if;
    -- The window has a floor: `p_weeks` of zero or less is the current week,
    -- never "everything".
    if v_src not like '%greatest(p_weeks, 1)%' then
      raise exception 'public.% has no floor on p_weeks', v_name;
    end if;
    -- No hand-written role filter: the policy is the cut, and a second copy
    -- of it here would drift at the first change.
    if v_src ~* 'is_admin|user_tenants|has_tenant' then
      raise exception 'public.% writes a role cut in the body — it is invoker precisely to inherit ai_query_read', v_name;
    end if;
  end loop;

  -- The contracts, by exact name.
  select p.oid into v_oid from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname = 'fn_assistant_runs';
  select array_agg(a.n order by a.n) into v_cols
    from pg_proc p, unnest(p.proargnames, p.proargmodes) as a(n, m)
   where p.oid = v_oid and a.m = 't';
  if v_cols <> array['created_at', 'input_tokens', 'latency_ms', 'metric_code', 'model',
                     'output_tokens', 'prompt_version_id', 'question', 'refusal_reason',
                     'refused', 'rows_returned', 'version_label'] then
    raise exception 'public.fn_assistant_runs changed its contract: %', v_cols;
  end if;

  select p.oid into v_oid from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname = 'fn_assistant_cost_by_version';
  select array_agg(a.n order by a.n) into v_cols
    from pg_proc p, unnest(p.proargnames, p.proargmodes) as a(n, m)
   where p.oid = v_oid and a.m = 't';
  if v_cols <> array['avg_latency_ms', 'input_tokens', 'model', 'month_start', 'output_tokens',
                     'prompt_version_id', 'refused_runs', 'runs', 'version_label'] then
    raise exception 'public.fn_assistant_cost_by_version changed its contract: %', v_cols;
  end if;

  -- They run (as the migration runner, who bypasses RLS — so nothing is
  -- asserted about the rows), on the default window and on a degenerate one.
  perform * from public.fn_assistant_runs();
  perform * from public.fn_assistant_runs(0);
  perform * from public.fn_assistant_cost_by_version();
  perform * from public.fn_assistant_cost_by_version(0);

  raise notice 'OK: fn_publish_assistant_prompt(uuid, timestamptz) — six refusals in order, grant rewritten after the drop; fn_assistant_runs and fn_assistant_cost_by_version — invoker, anon out, dry run outside both.';
end $$;
