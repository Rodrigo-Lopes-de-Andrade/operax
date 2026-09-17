-- ============================================================================
-- OperaX — assistant_catalog_fn. THE SINGLE RULER OF THE ASSISTANT'S CATALOGUE
-- ----------------------------------------------------------------------------
-- Design in `docs/SPEC-AGENTE.md` §3e (the RPC), §4.2 (three filters, all
-- narrowing) and §4.3 (one ruler). The effective catalogue of a tenant, for
-- the person asking, in one answer:
--
--   app.metric.active                    (EURECA: the metric exists)
--           ↓
--   app.assistant_metric_scope.enabled   (customer: we use this; absence = on)
--           ↓
--   util.can_see_domain(tenant, domain)  (role: this person may see)
--
-- Never the other way round, in none of the three. The "Capacidades" tab and
-- `backend/operax/agente/executor.py:load_catalog` both read THIS function;
-- a screen and a runtime with rulers of their own diverge exactly in the rare
-- case, which is where nobody looks (§4.3 — the DeskcommCRM lesson).
--
-- NINE COLUMNS — SIX FROM THE SPEC, THREE FROM THE OWNER'S STOP (17/09/2026)
-- `code, title, description, domain, enabled, visible_to_me` are §3e;
-- `target_view, dimensions, filters` were added by the owner's decision
-- because the runtime needs them to build the query and the SPEC did not
-- list them. Nothing else: no column, no person, no destination.
--
-- `security invoker`, ON PURPOSE
-- The three rulers already exist as objects the user reaches: `app.metric`
-- under `metric_read` (`active`), `app.assistant_metric_scope` under
-- `assistant_scope_read` (`has_tenant`), and `util.can_see_domain` (definer,
-- granted to `authenticated`). Definer here would be privilege without need
-- — and it would answer for a tenant the caller is not a member of.
--
-- WHO IS NOT A MEMBER GETS ZERO ROWS, NOT AN ERROR
-- The RPC is Path 1 (browser → PostgREST) and the client chooses
-- `p_tenant_id`. `where util.has_tenant(p_tenant_id)` in the body: the
-- catalogue of another tenant — even the platform-wide, non-sensitive part —
-- is not shown to whoever is not in it.
--
-- ⚠️ `trg_lock_down_new_function` DOES NOT COVER `public`. The revoke and the
-- `grant execute … to authenticated` are written here; without the grant the
-- RPC is born unreachable and the symptom is a 403 with nothing in the log.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

create or replace function public.fn_assistant_catalog(p_tenant_id uuid)
returns table (
  code          text,
  title         text,
  description   text,
  domain        app.sensitive_domain,
  enabled       boolean,
  visible_to_me boolean,
  target_view   text,
  dimensions    text[],
  filters       text[]
)
language sql stable security invoker set search_path = ''
as $$
  select m.code,
         m.title,
         m.description,
         m.domain,
         coalesce(s.enabled, true)                                                  as enabled,
         coalesce(s.enabled, true)
           and (m.domain is null or util.can_see_domain(p_tenant_id, m.domain))     as visible_to_me,
         m.target_view,
         m.dimensions,
         m.filters
    from app.metric m
    left join app.assistant_metric_scope s
      on s.tenant_id = p_tenant_id
     and s.metric_code = m.code
   where m.active
     and util.has_tenant(p_tenant_id)
   order by m.code;
$$;

comment on function public.fn_assistant_catalog(uuid) is
  'O catálogo efetivo do assistente para o tenant, como quem chama. Os três '
  'filtros da SPEC-AGENTE §4.2 numa resposta: só app.metric.active; enabled = '
  'coalesce(escopo do tenant, true) — ausência é habilitada; visible_to_me = '
  'enabled e (sem domínio ou util.can_see_domain). É a régua única (§4.3): a '
  'aba Capacidades e o runtime (executor.load_catalog) leem daqui. Security '
  'INVOKER: metric_read, assistant_scope_read e can_see_domain já são o que o '
  'usuário alcança. Quem não é membro do tenant recebe zero linhas, não erro. '
  'target_view, dimensions e filters entram por decisão do dono (17/09/2026): '
  'o runtime precisa deles para montar a consulta.';

-- The trigger does not cover public: written, both sides.
revoke execute on function public.fn_assistant_catalog(uuid) from public, anon;
grant  execute on function public.fn_assistant_catalog(uuid) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_oid    oid;
  v_secdef boolean;
  v_config text;
  v_result text;
  v_src    text;
  v_body   text;
begin
  select p.oid, p.prosecdef, coalesce(array_to_string(p.proconfig, ','), '')
    into v_oid, v_secdef, v_config
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname = 'fn_assistant_catalog';
  if v_oid is null then
    raise exception 'public.fn_assistant_catalog(uuid) does not exist';
  end if;

  -- 1. NOT definer (it would answer for a tenant the caller is not in), with
  --    search_path locked anyway.
  if v_secdef then
    raise exception 'public.fn_assistant_catalog is security definer — the three rulers are the user''s own objects; definer is privilege without need';
  end if;
  if v_config not like '%search_path=%' then
    raise exception 'public.fn_assistant_catalog has no search_path locked';
  end if;

  -- 2. anon cannot execute; authenticated can. No net under public.
  if has_function_privilege('anon', v_oid, 'EXECUTE') then
    raise exception 'anon can execute public.fn_assistant_catalog';
  end if;
  if has_function_privilege('public', v_oid, 'EXECUTE') then
    raise exception 'public can execute public.fn_assistant_catalog';
  end if;
  if not has_function_privilege('authenticated', v_oid, 'EXECUTE') then
    raise exception 'authenticated cannot execute public.fn_assistant_catalog — the assistant would load no catalogue and the tab would 403 with nothing in the log';
  end if;

  -- 3. The nine columns, in this order — the contract of the tab and the runtime.
  v_result := regexp_replace(pg_get_function_result(v_oid), '\s+', ' ', 'g');
  if v_result <> 'TABLE(code text, title text, description text, domain app.sensitive_domain, enabled boolean, visible_to_me boolean, target_view text, dimensions text[], filters text[])' then
    raise exception 'public.fn_assistant_catalog returns "%" — expected the nine columns of SPEC §3e + the owner''s stop, in order', v_result;
  end if;

  -- 4. The body applies the three rulers, read from the catalogue not from
  --    this file: membership, domain, absence = enabled, the scope table.
  v_src  := pg_get_functiondef(v_oid);
  v_body := substr(v_src, position('$function$' in v_src));
  if v_body not like '%has_tenant%' then
    raise exception 'public.fn_assistant_catalog does not check util.has_tenant — a non-member would read another tenant''s catalogue';
  end if;
  if v_body not like '%can_see_domain%' then
    raise exception 'public.fn_assistant_catalog does not apply util.can_see_domain — enabling would grant a domain the role does not have';
  end if;
  if v_body not like '%coalesce(%' then
    raise exception 'public.fn_assistant_catalog has no coalesce — absence of a scope row must mean enabled';
  end if;
  if v_body not like '%assistant_metric_scope%' then
    raise exception 'public.fn_assistant_catalog does not read app.assistant_metric_scope';
  end if;

  raise notice 'OK: public.fn_assistant_catalog — invoker with search_path, anon out, authenticated in, nine columns in order, has_tenant + can_see_domain + coalesce + scope in the body.';
end $$;
