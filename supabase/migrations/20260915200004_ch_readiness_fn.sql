-- ============================================================================
-- OperaX — ch_readiness_fn. READINESS FOR FOUR PROVIDERS, TWO CHANNELS
-- ----------------------------------------------------------------------------
-- Design in `docs/SPEC-CANAIS.md` §4 and §7. `public.fn_whatsapp_readiness`
-- (migration 14) answers one question — "is the tenant's WhatsApp ready?" — and
-- assumes one active provider per tenant, which the WhatsApp index guarantees.
-- With Telegram alongside (previous migrations), a tenant has up to TWO active
-- channel integrations, and the screen needs a line for each.
--
-- `public.fn_channel_readiness()` generalises it: one row per active channel
-- integration (`meta_cloud`, `z_api`, `uazapi`, `telegram`) of the caller's
-- tenants, with the channel it carries and the health the watcher recorded.
--
-- READY MEANS SOMETHING DIFFERENT PER CHANNEL, AND THAT IS THE POINT
-- * WhatsApp: the same count as today — official needs approved templates and
--   no rule pointing at an unapproved one; unofficial is ready by existing.
-- * Telegram: there is no template to approve (the local `body` is what goes
--   out, SPEC §2), so `templates_*` and `rules_blocked` are 0 by definition —
--   and `ready` is "the bot is connected", which only the watcher knows. No
--   health row, or any status but `connected`, is NOT ready: an untested bot is
--   a bot whose alerts fail quietly.
--
-- ⚠️ `fn_whatsapp_readiness` IS NOT DROPPED HERE
-- `server/routers/canais.py` and `scripts/97_teste_canais.py` still call it.
-- It is deprecated by `comment on` and removed in a later migration, after
-- measuring that nobody calls it — "measure that they stopped" is a step, not
-- a formality (the `sync-fotos` lesson).
--
-- ⚠️ `trg_lock_down_new_function` DOES NOT COVER `public`. The grant and the
-- revoke are written here.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

create or replace function public.fn_channel_readiness()
returns table (
  tenant_id           uuid,
  provider            text,
  channel             text,
  official            boolean,
  templates_total     integer,
  templates_approved  integer,
  rules_blocked       integer,
  health_status       text,
  health_changed_at   timestamptz,
  ready               boolean
)
language sql stable security definer set search_path = ''
as $$
  with prov as (
    select i.id,
           i.tenant_id,
           i.provider,
           case when i.provider = 'telegram' then 'telegram' else 'whatsapp' end as channel,
           -- Meta's own API and Telegram's Bot API are the platform's official
           -- surfaces; z_api and uazapi are reverse-engineered clients.
           i.provider in ('meta_cloud', 'telegram') as official
      from app.integration i
     where i.active
       and i.provider in ('meta_cloud', 'z_api', 'uazapi', 'telegram')
       and i.tenant_id = any (util.user_tenants())
  ),
  tpl as (
    select m.tenant_id,
           (count(*) filter (where m.active))::int                                as total,
           (count(*) filter (where m.active and m.meta_status = 'approved'))::int as approved
      from app.message_template m
     group by m.tenant_id
  ),
  blocked as (
    -- Only the official WHATSAPP provider blocks on template approval. The
    -- join is on the WhatsApp row of the tenant, never on the Telegram row:
    -- Telegram is `official` too, and without `channel = 'whatsapp'` a tenant
    -- on z_api + Telegram would see its rules counted as blocked.
    select r.tenant_id, count(*)::int as n
      from app.alert_rule r
      join prov p on p.tenant_id = r.tenant_id
                 and p.channel = 'whatsapp'
                 and p.official
      left join app.message_template m
             on m.tenant_id = r.tenant_id and m.code = r.template_code and m.active
     where r.active
       and r.channel in ('whatsapp', 'both')
       and (m.id is null or m.meta_status <> 'approved')
     group by r.tenant_id
  )
  select p.tenant_id,
         p.provider,
         p.channel,
         p.official,
         case when p.channel = 'whatsapp' then coalesce(t.total, 0)    else 0 end,
         case when p.channel = 'whatsapp' then coalesce(t.approved, 0) else 0 end,
         case when p.channel = 'whatsapp' then coalesce(b.n, 0)        else 0 end,
         h.status,
         h.status_changed_at,
         case
           when p.channel = 'telegram' then coalesce(h.status = 'connected', false)
           when p.official then coalesce(b.n, 0) = 0 and coalesce(t.approved, 0) > 0
           else true
         end
    from prov p
    left join tpl                t on t.tenant_id      = p.tenant_id
    left join blocked            b on b.tenant_id      = p.tenant_id
    left join app.channel_health h on h.integration_id = p.id;
$$;

comment on function public.fn_channel_readiness() is
  'Uma linha por integração ativa de canal (meta_cloud, z_api, uazapi, telegram) '
  'dos tenants do chamador, com o canal (whatsapp|telegram) e a saúde medida pelo '
  'vigia. ready: WhatsApp = a conta de fn_whatsapp_readiness (oficial exige template '
  'aprovado e nenhuma regra apontando para template não aprovado); Telegram = '
  'existe bot ativo E channel_health.status = connected — sem medição não está '
  'pronto. Para telegram templates_* e rules_blocked valem 0: não há template a '
  'aprovar, o body local é o que sai. Substitui fn_whatsapp_readiness.';

revoke execute on function public.fn_channel_readiness() from public, anon;
grant  execute on function public.fn_channel_readiness() to authenticated, service_role;

-- The predecessor stays callable; it is marked, not removed.
comment on function public.fn_whatsapp_readiness() is
  'DEPRECIADA em 15/09/2026 em favor de public.fn_channel_readiness(), que devolve '
  'uma linha por canal (WhatsApp e Telegram) com a saúde do vigia. Esta só conhece '
  'WhatsApp e assume um provedor ativo por tenant. Remoção em migration posterior, '
  'depois de medir que ninguém a chama. ready = false quando o tenant está no '
  'provedor oficial e existe regra ligada apontando para template não aprovado.';

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_oid       oid;
  v_secdef    boolean;
  v_config    text;
  v_resultado text;
  v_src       text;
begin
  select p.oid, p.prosecdef, coalesce(array_to_string(p.proconfig, ','), '')
    into v_oid, v_secdef, v_config
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname = 'fn_channel_readiness';
  if v_oid is null then
    raise exception 'public.fn_channel_readiness() does not exist';
  end if;

  -- 1. Definer with search_path locked — the requirement item 9 of
  --    scripts/99_verificacao_rls.sql makes of every definer in public.
  if not v_secdef then
    raise exception 'public.fn_channel_readiness() is not security definer';
  end if;
  if v_config not like '%search_path=%' then
    raise exception 'public.fn_channel_readiness() is definer WITHOUT search_path locked';
  end if;

  -- 2. anon cannot execute; authenticated can. The trigger does not cover
  --    public, so a missing grant here would be a screen nobody can open.
  if has_function_privilege('anon', v_oid, 'EXECUTE') then
    raise exception 'anon can execute public.fn_channel_readiness()';
  end if;
  if not has_function_privilege('authenticated', v_oid, 'EXECUTE') then
    raise exception 'authenticated cannot execute public.fn_channel_readiness() — the Conexões screen would never load';
  end if;

  -- 3. Aggregate only: a definer in public never returns a person.
  v_resultado := pg_get_function_result(v_oid);
  if v_resultado ~* '(employee|colaborador|name|nome|cpf|contact|external_id|chat_id|phone)' then
    raise exception 'public.fn_channel_readiness() returns per-person data (%)', v_resultado;
  end if;

  -- 4. The body knows the four providers and the two channels, and blocks
  --    only on the WhatsApp side. Read from the catalogue, not this file.
  v_src := pg_get_functiondef(v_oid);
  if v_src not like '%''telegram''%' or v_src not like '%''meta_cloud''%'
     or v_src not like '%''z_api''%' or v_src not like '%''uazapi''%' then
    raise exception 'public.fn_channel_readiness() does not name the four channel providers';
  end if;
  if v_src not ilike '%p.channel = ''whatsapp''%and p.official%' then
    raise exception 'public.fn_channel_readiness() blocks on templates without restricting to the WhatsApp row — a z_api + telegram tenant would count blocked rules';
  end if;

  -- 5. No caller, no rows: auth.uid() is null, util.user_tenants() is empty.
  if exists (select 1 from public.fn_channel_readiness()) then
    raise exception 'public.fn_channel_readiness() returned rows with no authenticated user';
  end if;

  -- 6. The predecessor is still there, deprecated and not dropped.
  select p.oid into v_oid
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname = 'fn_whatsapp_readiness';
  if v_oid is null then
    raise exception 'public.fn_whatsapp_readiness() was dropped — the router still calls it; deprecate, measure, then remove';
  end if;
  if coalesce(obj_description(v_oid, 'pg_proc'), '') not ilike '%fn_channel_readiness%' then
    raise exception 'public.fn_whatsapp_readiness() is not marked deprecated in favour of fn_channel_readiness';
  end if;

  raise notice 'OK: public.fn_channel_readiness() — one row per channel integration, definer locked, anon out, aggregate only; fn_whatsapp_readiness deprecated, not dropped.';
end $$;
