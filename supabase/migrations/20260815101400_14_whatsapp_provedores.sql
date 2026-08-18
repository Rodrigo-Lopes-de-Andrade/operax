-- ============================================================================
-- OperaX — 14. WHATSAPP PROVIDERS AND MESSAGE TEMPLATES
-- ----------------------------------------------------------------------------
-- Three providers, by customer decision: Meta Cloud API (official), Z-API and
-- uazapi (both unofficial, QR/WhatsApp-Web based).
--
-- They are NOT interchangeable behind a "send(text)" interface, and this is the
-- whole reason this migration exists.
--
--   * Meta Cloud API: a business-initiated message outside the 24h service
--     window MUST be a template approved in advance, sent as
--     (template_name, language, ordered variables). Free text is refused.
--   * Z-API / uazapi: take free text and have no template concept.
--
-- An interface built around free text cannot serve the official provider, ever.
-- An interface built around (template_code, variables) serves all three: the
-- unofficial ones render the template locally into text before sending. So the
-- contract is TEMPLATE-FIRST, and the renderer is the provider's problem.
--
-- This also explains why migration 13 was right to force alert_queue.payload to
-- be a structured object instead of a prebuilt string. That decision was made
-- to keep the observed time in the message; it turns out to be exactly the
-- shape a Meta template needs. The payload keys ARE the template variables.
--
-- Risk note recorded in the schema, not only in the proposal: through 2026 Meta
-- escalated enforcement against reverse-engineered clients, using connection
-- fingerprinting rather than volume. Z-API and uazapi are named in that class.
-- A ban is permanent and has no appeal, and it takes the customer's own number
-- with it. Hence meta_cloud is the default here, and the other two require a
-- deliberate choice.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Provider becomes a first-class value
-- ---------------------------------------------------------------------------
alter table app.integration
  drop constraint if exists integration_provider_check;
alter table app.integration
  add  constraint integration_provider_check check (provider in (
    'secullum', 'domain', 'spreadsheet',              -- origem de dado
    'meta_cloud', 'z_api', 'uazapi',                  -- whatsapp
    'smtp', 'resend'                                  -- e-mail
  ));

alter table app.alert_sent
  drop constraint if exists alert_sent_provider_check;
alter table app.alert_sent
  add  constraint alert_sent_provider_check check (provider in (
    'meta_cloud', 'z_api', 'uazapi', 'smtp', 'resend'
  ));

comment on column app.integration.provider is
  'meta_cloud = API oficial da Meta, exige template aprovado e verificação de '
  'negócio. z_api e uazapi = não oficiais, baseados em QR/WhatsApp Web: '
  'dispensam template, mas o número do cliente pode ser banido sem recurso.';

-- Um tenant tem no máximo um provedor de WhatsApp ativo. Dois ativos ao mesmo
-- tempo significa alerta duplicado no telefone do gestor.
create unique index if not exists integration_whatsapp_unico_ativo
  on app.integration (tenant_id)
  where active and provider in ('meta_cloud', 'z_api', 'uazapi');

-- ---------------------------------------------------------------------------
-- 2. Template catalogue
-- ---------------------------------------------------------------------------
-- Por tenant, porque cada cliente aprova os próprios templates na sua WABA.
create table if not exists app.message_template (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null references app.tenant(id) on delete cascade,
  code               text not null,        -- código interno, estável: 'deviation_individual'
  category           text not null default 'utility'
                       check (category in ('utility', 'authentication', 'marketing')),
  language           text not null default 'pt_BR',
  variables          text[] not null,      -- ordem define {{1}}, {{2}}, ... e são chaves do payload
  body               text not null,        -- render local (z_api/uazapi) com {{1}}, {{2}}, ...
  meta_template_name text,                 -- nome aprovado na WABA do tenant
  meta_status        text not null default 'draft'
                       check (meta_status in ('draft','pending','approved','rejected','paused')),
  meta_rejection     text,
  active             boolean not null default true,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (tenant_id, code, language)
);

comment on table app.message_template is
  'Contrato único das três integrações de WhatsApp. `variables` é a ordem dos '
  'placeholders do template da Meta E o conjunto de chaves exigido no payload '
  'da fila. `body` é o mesmo texto renderizado localmente para os provedores '
  'não oficiais, que não têm template.';

comment on column app.message_template.category is
  'utility para alerta operacional. Categoria errada faz a Meta reprovar o '
  'template ou cobrar como marketing — cerca de 9x mais caro no Brasil.';

-- O corpo tem que usar exatamente os placeholders declarados: nem a mais (o
-- render deixaria {{4}} literal na mensagem), nem a menos (variável coletada e
-- nunca mostrada). Falhar aqui é barato; falhar na revisão da Meta custa dias.
create or replace function util.validate_template_body()
returns trigger
language plpgsql security definer set search_path = ''
as $$
declare
  n int := array_length(new.variables, 1);
  i int;
  maior int := 0;
  achado text;
begin
  if n is null or n = 0 then
    raise exception using errcode = 'raise_exception',
      message = 'Template sem variáveis declaradas.',
      hint    = 'Alerta de ocorrência precisa carregar data e horário observado; '
             || 'um template sem variável só consegue dizer "algo aconteceu".';
  end if;

  for i in 1..n loop
    if position('{{' || i || '}}' in new.body) = 0 then
      raise exception using errcode = 'raise_exception',
        message = format('Template %s declara a variável %s (%s) mas o corpo não usa {{%s}}.',
                         new.code, i, new.variables[i], i);
    end if;
  end loop;

  -- Placeholder além do declarado sairia literal na mensagem enviada.
  for achado in select (regexp_matches(new.body, '\{\{(\d+)\}\}', 'g'))[1] loop
    maior := greatest(maior, achado::int);
  end loop;
  if maior > n then
    raise exception using errcode = 'raise_exception',
      message = format('Template %s usa {{%s}} mas declara só %s variáveis.',
                       new.code, maior, n);
  end if;

  new.updated_at := now();
  return new;
end $$;

drop trigger if exists trg_validate_template_body on app.message_template;
create trigger trg_validate_template_body
  before insert or update on app.message_template
  for each row execute function util.validate_template_body();

-- ---------------------------------------------------------------------------
-- 3. A regra aponta para um template
-- ---------------------------------------------------------------------------
alter table app.alert_rule
  add column if not exists template_code text;

comment on column app.alert_rule.template_code is
  'Null = alerta de e-mail ou resumo livre. Para WhatsApp com provedor oficial '
  'é obrigatório: sem template aprovado a Meta recusa a mensagem.';

alter table app.alert_queue
  add column if not exists template_code text;
alter table app.alert_queue
  add column if not exists provider text;

alter table app.alert_queue
  drop constraint if exists alert_queue_provider_check;
alter table app.alert_queue
  add  constraint alert_queue_provider_check
    check (provider is null or provider in ('meta_cloud','z_api','uazapi','smtp','resend'));

-- ---------------------------------------------------------------------------
-- 4. O contrato: payload cobre as variáveis do template
-- ---------------------------------------------------------------------------
-- Estende a validação da migration 13. Lá o payload tinha que carregar o
-- horário observado; aqui ele tem que carregar tudo que o template promete —
-- senão o provedor oficial recusa a mensagem e o não oficial envia um texto com
-- "{{2}}" no meio.
create or replace function util.validate_alert_template()
returns trigger
language plpgsql security definer set search_path = ''
as $$
declare
  t record;
  v text;
  faltando text := '';
begin
  if new.template_code is null then
    return new;                       -- e-mail e resumo livre não usam template
  end if;

  select * into t
    from app.message_template
   where tenant_id = new.tenant_id
     and code      = new.template_code
     and active
   limit 1;

  if not found then
    raise exception using errcode = 'raise_exception',
      message = format('Template %s não existe para este tenant.', new.template_code),
      hint    = 'Template é por tenant: cada cliente aprova os seus na própria WABA.';
  end if;

  foreach v in array t.variables loop
    if new.payload ->> v is null then
      faltando := faltando || v || ' ';
    end if;
  end loop;

  if faltando <> '' then
    raise exception using errcode = 'raise_exception',
      message = format('Payload não cobre as variáveis do template %s: %s',
                       new.template_code, trim(faltando)),
      hint    = 'As chaves do payload são os placeholders da mensagem. Faltando '
             || 'uma, o provedor oficial recusa e o não oficial envia "{{n}}" '
             || 'literal para o gestor.';
  end if;

  -- Provedor oficial só aceita template aprovado. Descobrir isso em produção
  -- significa alerta silenciosamente não entregue no dia que mais importa.
  if new.provider = 'meta_cloud' and t.meta_status <> 'approved' then
    raise exception using errcode = 'raise_exception',
      message = format('Template %s está %s e o provedor é meta_cloud.',
                       new.template_code, t.meta_status),
      hint    = 'A Meta leva de horas a dias para aprovar. Aprove antes de ligar '
             || 'a regra, ou o alerta falha calado.';
  end if;

  return new;
end $$;

drop trigger if exists trg_validate_alert_template on app.alert_queue;
create trigger trg_validate_alert_template
  before insert or update on app.alert_queue
  for each row execute function util.validate_alert_template();

-- ---------------------------------------------------------------------------
-- 5. Prontidão do canal, para o painel e para a implantação
-- ---------------------------------------------------------------------------
-- Mesma ideia de fn_data_freshness e fn_detection_health: a ausência precisa
-- ser detectável antes de doer.
create or replace function public.fn_whatsapp_readiness()
returns table (
  tenant_id           uuid,
  provider            text,
  official            boolean,
  templates_total     integer,
  templates_approved  integer,
  rules_blocked       integer,
  ready               boolean
)
language sql stable security definer set search_path = ''
as $$
  with prov as (
    select i.tenant_id,
           i.provider,
           i.provider = 'meta_cloud' as official
      from app.integration i
     where i.active
       and i.provider in ('meta_cloud','z_api','uazapi')
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
    select r.tenant_id, count(*)::int as n
      from app.alert_rule r
      join prov p on p.tenant_id = r.tenant_id
      left join app.message_template m
             on m.tenant_id = r.tenant_id and m.code = r.template_code and m.active
     where r.active
       and r.channel in ('whatsapp','both')
       and p.official
       and (m.id is null or m.meta_status <> 'approved')
     group by r.tenant_id
  )
  select p.tenant_id,
         p.provider,
         p.official,
         coalesce(t.total, 0),
         coalesce(t.approved, 0),
         coalesce(b.n, 0),
         case when p.official then coalesce(b.n, 0) = 0 and coalesce(t.approved, 0) > 0
              else true end
    from prov p
    left join tpl     t on t.tenant_id = p.tenant_id
    left join blocked b on b.tenant_id = p.tenant_id;
$$;

comment on function public.fn_whatsapp_readiness() is
  'ready = false quando o tenant está no provedor oficial e existe regra ligada '
  'apontando para template não aprovado. Nesse estado o alerta falha calado.';

revoke execute on function public.fn_whatsapp_readiness() from public, anon;
grant  execute on function public.fn_whatsapp_readiness() to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 6. RLS
-- ---------------------------------------------------------------------------
alter table app.message_template enable row level security;
revoke all on table app.message_template from anon;

drop policy if exists message_template_admin on app.message_template;
create policy message_template_admin on app.message_template
  for all to authenticated
  using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

drop policy if exists message_template_read on app.message_template;
create policy message_template_read on app.message_template
  for select to authenticated using (util.has_tenant(tenant_id));

grant select on app.message_template to authenticated;
grant insert, update, delete on app.message_template to authenticated;

create index if not exists message_template_tenant_idx
  on app.message_template (tenant_id, code) where active;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_trigger where tgname = 'trg_validate_alert_template') then
    raise exception 'alert template contract trigger not installed';
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'trg_validate_template_body') then
    raise exception 'template body validation trigger not installed';
  end if;
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'public' and p.proname = 'fn_whatsapp_readiness'
               and has_function_privilege('anon', p.oid, 'EXECUTE')) then
    raise exception 'fn_whatsapp_readiness is executable by anon';
  end if;
  raise notice 'OK: three whatsapp providers behind one template-first contract.';
end $$;
