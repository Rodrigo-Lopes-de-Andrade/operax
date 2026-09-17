-- ============================================================================
-- OperaX — ch_queue_telegram. THE QUEUE LEARNS THE THIRD CHANNEL; THE RULE DOES NOT
-- ----------------------------------------------------------------------------
-- Design in `docs/SPEC-CANAIS.md` §8: *"Telegram se houver identidade vigente;
-- WhatsApp caso contrário"* — no preference screen, no column of choice. The
-- consequence for the schema is asymmetric, and the asymmetry is the point:
--
--   * `app.alert_queue.channel` GAINS `'telegram'`. A queue row is one routed
--     message, and the sender needs to know which wire it goes on.
--   * `app.alert_rule.channel` DOES NOT. A rule says "messaging" (`whatsapp`)
--     or "e-mail" or `both`; which messaging channel reaches a given person is
--     decided per person by `app.messaging_identity`, in `outbox.route`. A
--     rule that could name `telegram` would be a rule that stops degrading on
--     its own — the person who blocked the bot would get nothing instead of
--     WhatsApp. The proof block asserts the rule check is untouched.
--
-- The check changes by `drop constraint if exists` + `add constraint`, the
-- way migration 14 and `ch_telegram_provider` already did: a check is not
-- editable in place, and the applied migration is never edited.
--
-- THE SECOND THING HERE: THE VALIDATOR LETS A FINISHED ROW BE SCRUBBED
-- `util.validate_alert_template` fires `before insert or update` and refuses a
-- payload that does not cover the template's variables. The C4 invite carries
-- the adhesion link — which IS the credential (SPEC §3.3) — in `payload.link`,
-- and the named debt of C4 is to remove it once the row is `sent` or
-- `discarded`. Measured before writing this: `payload - 'link'` on a
-- `telegram_invite` row is refused by the trigger ("Payload não cobre as
-- variáveis do template telegram_invite: link"). So the validator gains one
-- clause: an UPDATE that lands the row on a terminal status (`sent`,
-- `discarded`) is not validated — there is nothing left to deliver, and the
-- scrub is exactly what happens at that moment. Insert and every other update
-- (`sending`, `failed`, the re-route to WhatsApp after `blocked`) validate as
-- before. Only `service_role` writes the queue, so the clause opens no door.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. `telegram` in the queue channel check
-- ---------------------------------------------------------------------------
alter table app.alert_queue
  drop constraint if exists alert_queue_channel_check;
alter table app.alert_queue
  add  constraint alert_queue_channel_check
    check (channel in ('whatsapp', 'email', 'telegram'));

comment on column app.alert_queue.channel is
  'O canal ROTEADO desta mensagem: whatsapp, email ou telegram. A regra '
  '(app.alert_rule.channel) nunca diz telegram — ela diz mensageria, e quem '
  'decide o canal é a identidade vigente da pessoa (app.messaging_identity), '
  'em outbox.route. Sem identidade, ou sem bot ativo, a mensagem vai por '
  'WhatsApp como sempre foi.';

-- ---------------------------------------------------------------------------
-- 2. The validator: a terminal update is not validated
-- ---------------------------------------------------------------------------
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

  -- Uma linha que chega a `sent` ou `discarded` não tem mais o que entregar,
  -- e é neste update que o sender tira `payload.link` do convite de adesão
  -- (SPEC-CANAIS §3.3: o link é a credencial). Validar aqui recusaria a
  -- limpeza. Insert e todo outro update continuam validando.
  if tg_op = 'UPDATE' and new.status in ('sent', 'discarded') then
    return new;
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

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_queue text;
  v_rule  text;
  v_src   text;
begin
  -- 1. The queue check accepts the three channels. Read from the catalogue.
  select pg_get_constraintdef(oid) into v_queue
    from pg_constraint
   where conrelid = 'app.alert_queue'::regclass and conname = 'alert_queue_channel_check';
  if v_queue is null then
    raise exception 'alert_queue_channel_check is missing';
  end if;
  if v_queue not like '%telegram%' then
    raise exception 'alert_queue_channel_check does not accept telegram: %', v_queue;
  end if;
  if v_queue not like '%whatsapp%' or v_queue not like '%email%' then
    raise exception 'alert_queue_channel_check lost a channel: %', v_queue;
  end if;

  -- 2. ⛔ The RULE check is untouched: whatsapp, email, both — and NOT telegram.
  --    A rule naming telegram is a rule that stops degrading to WhatsApp.
  select pg_get_constraintdef(oid) into v_rule
    from pg_constraint
   where conrelid = 'app.alert_rule'::regclass and conname = 'alert_rule_channel_check';
  if v_rule is null then
    raise exception 'alert_rule_channel_check disappeared';
  end if;
  if v_rule like '%telegram%' then
    raise exception 'alert_rule_channel_check names telegram — the rule would choose the channel instead of the identity: %', v_rule;
  end if;
  if v_rule not like '%whatsapp%' or v_rule not like '%email%' or v_rule not like '%both%' then
    raise exception 'alert_rule_channel_check changed: %', v_rule;
  end if;

  -- 3. The validator has the terminal clause, is still definer with a locked
  --    search_path, and still fires before insert AND update.
  select pg_get_functiondef(p.oid) into v_src
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'util' and p.proname = 'validate_alert_template';
  if v_src is null then
    raise exception 'util.validate_alert_template() does not exist';
  end if;
  if v_src not like '%new.status in (''sent'', ''discarded'')%' then
    raise exception 'util.validate_alert_template() would refuse the scrub of payload.link on a finished row';
  end if;
  if v_src not ilike '%security definer%' or v_src not ilike '%search_path%' then
    raise exception 'util.validate_alert_template() lost definer or search_path';
  end if;
  if not exists (
    select 1 from pg_trigger
     where tgname = 'trg_validate_alert_template'
       and tgrelid = 'app.alert_queue'::regclass
       and tgenabled <> 'D'
  ) then
    raise exception 'trg_validate_alert_template is missing or disabled on app.alert_queue';
  end if;

  raise notice 'OK: alert_queue.channel accepts telegram, alert_rule.channel does not, and a finished row can be scrubbed.';
end $$;
