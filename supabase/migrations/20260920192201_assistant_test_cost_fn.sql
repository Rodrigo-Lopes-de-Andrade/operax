-- ============================================================================
-- OperaX — assistant_test_cost_fn. THE MONEY THE COST TABLE CANNOT SHOW
-- ----------------------------------------------------------------------------
-- One function, and it exists because `fn_assistant_cost_by_version` answers
-- "cost of the traffic" and the reader hears "what this tenant cost me".
-- `not is_dry_run` is right — a test is not traffic, and a test inside the
-- average moves the only number this stage produces (SPEC-AGENTE §0.3). But
-- the Teste tab bills real money, and in a month of prompt tuning it is most
-- of the bill: measured on 20/09/2026, 1998 tokens of dry run against 175 of
-- real traffic in the same scenario. Whoever reads the cost table as an
-- invoice reads less than they spent.
--
-- ⛔ A LINE OF ITS OWN, NOT A COLUMN IN THE SAME TABLE — OWNER'S DECISION,
--    20/09/2026
-- A `test_input_tokens` column beside `input_tokens` would be summed by the
-- first person to reach for a total, and the sum has no meaning: one is
-- traffic and the other is tuning. So it is a separate function, with a
-- separate return, and NO version and NO model in it: it is a TOTAL, not a
-- breakdown. Nothing here can be joined to the sister by anything but the
-- competência, and that is the point.
--
-- ⛔ `q.is_dry_run` IS AFFIRMATIVE HERE, AND IT IS THE WHOLE FUNCTION
-- The two sisters negate it; this one asserts it. A `not` slipped in front of
-- it turns the "Testes do período" line into a second, unlabelled copy of the
-- traffic — the same numbers twice, one of them called tests. The proof at
-- the bottom, `97` §A4-f and `99` item 20 each check the sign.
--
-- ⛔ SAME WINDOW EXPRESSION AS THE SISTERS, COPIED, NOT REWRITTEN
-- `date_trunc('week', now()) - make_interval(weeks => greatest(p_weeks, 1) - 1)`
-- — literally the same line as `fn_assistant_runs` and
-- `fn_assistant_cost_by_version`. The screen shows the three under one week
-- selector, so a window that drifts by a day makes the total belong to a
-- period the table above it does not cover. The floor (`greatest`) is what
-- keeps `p_weeks = 0` meaning the current week and never "everything".
--
-- ⛔ `security invoker`, LIKE THE SISTERS, AND FOR THE SAME REASON
-- `ai_query_read` is `user_id = auth.uid() or util.is_admin(tenant_id)`: an
-- admin totals the tenant's tests, a common member totals their own. There is
-- NO role filter in the body, on purpose — a second, hand-written copy of the
-- policy drifts at the first change, and a definer here would total every
-- tenant's tests for anyone.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

create or replace function public.fn_assistant_test_cost(p_weeks integer default 8)
returns table (
  month_start   date,
  runs          bigint,
  input_tokens  bigint,
  output_tokens bigint
)
language sql stable security invoker set search_path = ''
as $$
  select date_trunc('month', q.created_at)::date    as month_start,
         count(*)                                   as runs,
         coalesce(sum(q.input_tokens), 0)::bigint   as input_tokens,
         coalesce(sum(q.output_tokens), 0)::bigint  as output_tokens
    from app.ai_query q
   where q.is_dry_run
     and q.created_at >= date_trunc('week', now()) - make_interval(weeks => greatest(p_weeks, 1) - 1)
   group by 1
   order by month_start desc;
$$;

comment on function public.fn_assistant_test_cost(integer) is
  'O gasto da aba Teste por competência, nas últimas p_weeks semanas (a atual '
  'inclusa): turnos de dry run, tokens de entrada e de saída. É o complemento '
  'de fn_assistant_cost_by_version, que conta só o tráfego real — e é um '
  'TOTAL À PARTE, sem versão e sem modelo, para ninguém somar os dois sem '
  'perceber: um é tráfego, o outro é ajuste de prompt. Decisão do dono em '
  '20/09/2026. q.is_dry_run é AFIRMATIVO aqui e negado nas irmãs; a janela é '
  'a mesma expressão das três. Security INVOKER: o recorte é ai_query_read '
  '(próprio turno OU is_admin), como nas irmãs.';

revoke execute on function public.fn_assistant_test_cost(integer) from public, anon;
grant  execute on function public.fn_assistant_test_cost(integer) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
-- ⚠️ What it does NOT do, on purpose: it does not seed `ai_query` to prove the
-- role cut — the migration runs as the owner of the schema, who bypasses RLS,
-- so a functional proof here would prove nothing. The cut, and the fact that
-- this total and the sisters' totals are disjoint, are proved in
-- `scripts/97_teste_assistente.sql` §A4-f, on `make db-test`.
do $$
declare
  v_oid    oid;
  v_secdef boolean;
  v_config text;
  v_src    text;
  v_cols   text[];
  v_window text := 'date_trunc(''week'', now()) - make_interval(weeks => greatest(p_weeks, 1) - 1)';
begin
  if (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
       where n.nspname = 'public' and p.proname = 'fn_assistant_test_cost') <> 1 then
    raise exception 'public.fn_assistant_test_cost must exist with exactly one signature';
  end if;
  select p.oid, p.prosecdef, coalesce(array_to_string(p.proconfig, ','), '')
    into v_oid, v_secdef, v_config
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname = 'fn_assistant_test_cost';

  -- Invoker is the whole role cut, exactly as in the two sisters.
  if v_secdef then
    raise exception 'public.fn_assistant_test_cost is security definer — it would total every tenant''s tests for anyone';
  end if;
  if v_config not like '%search_path=%' then
    raise exception 'public.fn_assistant_test_cost has no search_path pinned';
  end if;
  if has_function_privilege('anon', v_oid, 'EXECUTE')
     or has_function_privilege('public', v_oid, 'EXECUTE') then
    raise exception 'anon/public can execute public.fn_assistant_test_cost';
  end if;
  if not has_function_privilege('authenticated', v_oid, 'EXECUTE') then
    raise exception 'authenticated cannot execute public.fn_assistant_test_cost — the total line of the tab would never load';
  end if;

  v_src := pg_get_functiondef(v_oid);
  if v_src not like '%from app.ai_query%' then
    raise exception 'public.fn_assistant_test_cost does not read app.ai_query';
  end if;
  -- ⛔ The sign. Affirmative, and NEVER negated: a `not` here makes the
  -- "Testes do período" line a second copy of the traffic under another name.
  if v_src !~ 'where q\.is_dry_run' then
    raise exception 'public.fn_assistant_test_cost does not filter on q.is_dry_run affirmatively — it would total the real traffic and call it tests';
  end if;
  if v_src ~ 'not q\.is_dry_run' then
    raise exception 'public.fn_assistant_test_cost negates is_dry_run — it is the sisters that negate it; this one is the test total';
  end if;
  -- ⛔ The window, character for character the sisters'. The tab shows the
  -- three under one selector: a window that drifts makes the total belong to
  -- a period the table above it does not cover.
  if position(v_window in v_src) = 0 then
    raise exception 'public.fn_assistant_test_cost does not use the same window expression as fn_assistant_runs and fn_assistant_cost_by_version';
  end if;
  if position(v_window in pg_get_functiondef(
       (select p.oid from pg_proc p join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public' and p.proname = 'fn_assistant_cost_by_version'))) = 0 then
    raise exception 'fn_assistant_cost_by_version changed its window — the two no longer cover the same period, and the total would be read against the wrong table';
  end if;
  -- No role cut written by hand: the policy is the cut.
  if v_src ~* 'is_admin|user_tenants|has_tenant' then
    raise exception 'public.fn_assistant_test_cost writes a role cut in the body — it is invoker precisely to inherit ai_query_read';
  end if;
  -- ⛔ A TOTAL, NOT A BREAKDOWN: no version and no model, so nobody groups it
  -- beside the sister and sums the two.
  if v_src ~* 'prompt_version_id|version_label|q\.model' then
    raise exception 'public.fn_assistant_test_cost breaks the total down by version or model — the owner asked for a line apart, not a column in the same table';
  end if;

  -- The contract, by exact name.
  select array_agg(a.n order by a.n) into v_cols
    from pg_proc p, unnest(p.proargnames, p.proargmodes) as a(n, m)
   where p.oid = v_oid and a.m = 't';
  if v_cols <> array['input_tokens', 'month_start', 'output_tokens', 'runs'] then
    raise exception 'public.fn_assistant_test_cost changed its contract: %', v_cols;
  end if;

  -- It runs (as the migration runner, who bypasses RLS — so nothing is
  -- asserted about the rows), on the default window and on a degenerate one.
  perform * from public.fn_assistant_test_cost();
  perform * from public.fn_assistant_test_cost(0);

  raise notice 'OK: fn_assistant_test_cost — invoker, anon out, is_dry_run affirmative, same window as the sisters, total without version or model.';
end $$;
