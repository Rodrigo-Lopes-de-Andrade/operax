-- ============================================================================
-- OperaX — ch_telegram_provider. THE FOURTH PROVIDER, AND THE THIRD FAMILY
-- ----------------------------------------------------------------------------
-- Design in `docs/SPEC-CANAIS.md` §1.1, §2.1 and §2.2. Owner decisions of
-- 15/09/2026 (`docs/SPRINTS-CANAIS.md` §C3): bot per tenant, token in
-- `app.integration_secret` + Vault exactly like WhatsApp.
--
-- Migration 14 named two families of restriction and said they never coexist:
-- self-restriction (`z_api`, `uazapi` — the number can be banned) and
-- hetero-restriction (`meta_cloud` — a template must be approved first).
-- Telegram has NEITHER, and the naive reading of that is "the channel without
-- rules", which is false. Its restriction is on a third axis: it does not send
-- to a phone number, it sends to a `chat_id` that only exists after the person
-- opened the bot. WhatsApp restricts WHAT and WHEN; Telegram restricts TO WHOM.
-- That axis is what `app.messaging_identity` (next migration) exists for.
--
-- ⛔ `integration_whatsapp_unico_ativo` DOES NOT GAIN `'telegram'`
-- That index exists because two active WhatsApp providers means a duplicated
-- alert on the manager's phone — and that holds between providers OF THE SAME
-- CHANNEL. Telegram and WhatsApp are different channels and MUST coexist
-- (SPEC §8: Telegram when there is a current identity, WhatsApp otherwise).
-- Adding `'telegram'` to that predicate makes the two mutually exclusive, and
-- the symptom arrives as a product bug: "I switched Telegram on and WhatsApp
-- went off". What enters is a SIBLING index, same reason, its own channel.
-- The proof block below asserts the WhatsApp predicate stayed untouched.
--
-- The three `check` constraints change by `drop constraint if exists` +
-- `add constraint`, the way migration 14 already did: a check is not editable
-- in place, and the applied migration is never edited.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. `telegram` in the three provider checks
-- ---------------------------------------------------------------------------
alter table app.integration
  drop constraint if exists integration_provider_check;
alter table app.integration
  add  constraint integration_provider_check check (provider in (
    'secullum', 'domain', 'spreadsheet',              -- origem de dado
    'meta_cloud', 'z_api', 'uazapi',                  -- whatsapp
    'telegram',                                       -- telegram
    'smtp', 'resend'                                  -- e-mail
  ));

alter table app.alert_sent
  drop constraint if exists alert_sent_provider_check;
alter table app.alert_sent
  add  constraint alert_sent_provider_check check (provider in (
    'meta_cloud', 'z_api', 'uazapi', 'telegram', 'smtp', 'resend'
  ));

alter table app.alert_queue
  drop constraint if exists alert_queue_provider_check;
alter table app.alert_queue
  add  constraint alert_queue_provider_check
    check (provider is null or provider in (
      'meta_cloud', 'z_api', 'uazapi', 'telegram', 'smtp', 'resend'
    ));

-- ---------------------------------------------------------------------------
-- 2. The sibling index — one active bot per tenant, in its own channel
-- ---------------------------------------------------------------------------
-- Two active bots at once is the same duplicated alert migration 14 prevents
-- for WhatsApp, now on the Telegram side. The WhatsApp index is NOT touched.
create unique index if not exists integration_telegram_unico_ativo
  on app.integration (tenant_id)
  where active and provider = 'telegram';

-- ---------------------------------------------------------------------------
-- 3. The third family, recorded where the value lives
-- ---------------------------------------------------------------------------
comment on column app.integration.provider is
  'meta_cloud = API oficial da Meta, exige template aprovado e verificação de '
  'negócio (hetero-restrição). z_api e uazapi = não oficiais, baseados em '
  'QR/WhatsApp Web: dispensam template, mas o número do cliente pode ser banido '
  'sem recurso (auto-restrição). telegram = terceira família, restrição de '
  'DESTINATÁRIO: não envia para número de telefone, só para o chat_id que passa '
  'a existir quando a pessoa inicia o bot — o vínculo vive em '
  'app.messaging_identity e é revogável. Um bot por tenant, token no Vault como '
  'o WhatsApp; coexiste com o provedor de WhatsApp ativo (índice irmão, nunca o '
  'mesmo índice).';

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_def       text;
  v_whatsapp  text;
  v_telegram  text;
begin
  -- 1. The three checks accept `telegram`. Read from the catalogue, not from
  --    this file: the applied definition is what production runs.
  select pg_get_constraintdef(oid) into v_def
    from pg_constraint
   where conrelid = 'app.integration'::regclass and conname = 'integration_provider_check';
  if v_def is null or v_def not like '%telegram%' then
    raise exception 'integration_provider_check does not accept telegram: %', v_def;
  end if;

  select pg_get_constraintdef(oid) into v_def
    from pg_constraint
   where conrelid = 'app.alert_sent'::regclass and conname = 'alert_sent_provider_check';
  if v_def is null or v_def not like '%telegram%' then
    raise exception 'alert_sent_provider_check does not accept telegram: %', v_def;
  end if;

  select pg_get_constraintdef(oid) into v_def
    from pg_constraint
   where conrelid = 'app.alert_queue'::regclass and conname = 'alert_queue_provider_check';
  if v_def is null or v_def not like '%telegram%' then
    raise exception 'alert_queue_provider_check does not accept telegram: %', v_def;
  end if;
  -- The queue check keeps accepting null: e-mail and free summaries carry no
  -- provider until the sender resolves one. Losing the `is null` branch would
  -- refuse every row `enqueue` writes today.
  if v_def not ilike '%provider is null%' then
    raise exception 'alert_queue_provider_check lost the null branch: %', v_def;
  end if;

  -- 2. The sibling index exists, is unique, and its predicate is the Telegram
  --    provider alone.
  select pg_get_indexdef(i.indexrelid) into v_telegram
    from pg_index i
    join pg_class c on c.oid = i.indexrelid
   where c.relname = 'integration_telegram_unico_ativo' and i.indisunique;
  if v_telegram is null then
    raise exception 'integration_telegram_unico_ativo missing or not unique';
  end if;
  if v_telegram not ilike '%provider = ''telegram''%' or v_telegram not ilike '%active%' then
    raise exception 'integration_telegram_unico_ativo has the wrong predicate: %', v_telegram;
  end if;

  -- 3. ⛔ The WhatsApp index is intact and does NOT name telegram. This is the
  --    line-1 guarantee of SPEC §2.2 ("WhatsApp active + Telegram active
  --    coexist"), asserted on the catalogue; the functional half lives in
  --    `scripts/86_teste_canais_exclusividade.sql`.
  select pg_get_indexdef(i.indexrelid) into v_whatsapp
    from pg_index i
    join pg_class c on c.oid = i.indexrelid
   where c.relname = 'integration_whatsapp_unico_ativo' and i.indisunique;
  if v_whatsapp is null then
    raise exception 'integration_whatsapp_unico_ativo disappeared — one tenant could run two WhatsApp providers';
  end if;
  if v_whatsapp ilike '%telegram%' then
    raise exception 'integration_whatsapp_unico_ativo names telegram — switching Telegram on would switch WhatsApp off: %', v_whatsapp;
  end if;

  -- 4. The comment records the third family.
  if coalesce(col_description('app.integration'::regclass,
       (select attnum from pg_attribute
         where attrelid = 'app.integration'::regclass and attname = 'provider')), '')
     not ilike '%telegram%' then
    raise exception 'app.integration.provider comment does not describe telegram';
  end if;

  raise notice 'OK: telegram is the fourth provider, in its own exclusivity index; the WhatsApp index is untouched.';
end $$;
