-- ============================================================================
-- OperaX — ch_messaging_identity. THE chat_id IS CONSENT, NOT A COLUMN
-- ----------------------------------------------------------------------------
-- Design in `docs/SPEC-CANAIS.md` §3 (3.1, 3.2, 3.3, 3.4). Owner decisions of
-- 15/09/2026 (`docs/SPRINTS-CANAIS.md` §C3, "As duas paradas foram abertas"):
--
--   1. `app.messaging_identity` and `app.messaging_invite` carry RLS switched
--      on and NO policy: `revoke all` from `anon`/`authenticated`,
--      `grant select, insert, update` to `service_role` (no `delete`: revoking
--      is `revoked_at`). Nobody in the panel reads the `chat_id`, not even
--      owner. What the screen needs comes from `public.fn_telegram_adhesion`
--      (counts per unit), in a later migration. This is the rule of
--      `app.integration_secret` (migration 09).
--   4. An invite is valid for 7 days: `expires_at` defaults to `now() + 7d`.
--
-- WHY A TABLE AND NOT `telegram_chat_id` ON THE PERSON
-- A `chat_id` is not an attribute like the CPF. It is a record of consent: it
-- has a date, an origin (the person opened the bot) and it is revocable (the
-- person blocked the bot). A column keeps none of that. And one identity table
-- serves both holders — responsible (`app.contact`) and employee — with one
-- path in the sender instead of two.
--
-- ⛔ THE INVITE LINK IS THE CREDENTIAL (SPEC §3.3)
-- Whoever opens `https://t.me/<bot>?start=<token>` becomes that person's
-- recipient of individual alerts. The token is the whole authentication, so
-- the schema enforces what it can of the five rules: single use (`used_at`),
-- short validity (`expires_at`, 7 days), and `token_hash` — never the token —
-- so a leaked database hands out no links. Rules 4 and 5 (the link travels by
-- the already-verified WhatsApp number; the link is visible and revocable on
-- the person's record) are the sender's and the screen's, in wave 2.
--
-- WITHOUT PHYSICAL DELETE (rule 6, extended)
-- Revoking fills `revoked_at`. Someone who blocked the bot and came back has
-- two rows, and the history stays readable. Hence `select, insert, update` to
-- `service_role` and NOT `grant all` — the precedent is `dp_banking_account`
-- and `36_employee_photo`: granting the verb and then promising nobody deletes
-- is the promise without the lock.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. The identity — SPEC §3.1, verbatim
-- ---------------------------------------------------------------------------
create table if not exists app.messaging_identity (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references app.tenant(id) on delete cascade,
  channel        text not null check (channel in ('telegram')),
  contact_id     uuid references app.contact(id)  on delete cascade,
  employee_id    uuid references app.employee(id) on delete cascade,
  external_id    text not null,                 -- chat_id do Telegram
  opted_in_at    timestamptz not null default now(),
  revoked_at     timestamptz,
  revoked_reason text,
  constraint messaging_identity_um_titular
    check ((contact_id is null) <> (employee_id is null))
);

comment on table app.messaging_identity is
  'Identidade de mensageria: o chat_id do Telegram como REGISTRO DE CONSENTIMENTO '
  '(tem data, origem e revogação), nunca coluna de cadastro. Exatamente um titular '
  'por linha — responsável (contact_id) ou colaborador (employee_id). Revogar é '
  'preencher revoked_at; nada aqui é apagado. ⛔ NENHUM papel do painel lê esta '
  'tabela, nem owner: RLS ligada, zero policy, sem grant a authenticated. Só '
  'service_role, pelo Caminho 2 — na prática só o sender e o webhook do /start. '
  'O chat_id nunca sai em tela, log, export ou resposta de API; a tela vê '
  'contagem por unidade em public.fn_telegram_adhesion.';
comment on column app.messaging_identity.external_id is
  'O chat_id do Telegram. Dado pessoal (domínio pii): identifica a pessoa e a liga '
  'a uma conta. Nunca em view de public, nunca em log, nunca em JSON de resposta.';
comment on column app.messaging_identity.revoked_at is
  'Quando o vínculo deixou de valer (a pessoa bloqueou o bot, ou o DP desvinculou). '
  'A linha fica: quem saiu e voltou tem duas, e a história é legível.';

-- No máximo UMA identidade vigente por titular, e por canal. Dois índices
-- parciais, um por tipo de titular: `contact_id` e `employee_id` são
-- mutuamente exclusivos pelo check acima, e um índice único sobre uma coluna
-- nula não conflita — por isso cada um filtra o próprio titular.
create unique index if not exists messaging_identity_vigente_contact_uk
  on app.messaging_identity (tenant_id, channel, contact_id)
  where revoked_at is null and contact_id is not null;

create unique index if not exists messaging_identity_vigente_employee_uk
  on app.messaging_identity (tenant_id, channel, employee_id)
  where revoked_at is null and employee_id is not null;

-- Um chat_id vigente não pode ser de duas pessoas do mesmo tenant. É o irmão da
-- regra 7 (SPEC §3.4): conteúdo individual na tela de quem não é o titular.
create unique index if not exists messaging_identity_vigente_external_uk
  on app.messaging_identity (tenant_id, channel, external_id)
  where revoked_at is null;

-- ---------------------------------------------------------------------------
-- 2. The invite — SPEC §3.3, verbatim, plus the 7-day default (owner, item 4)
-- ---------------------------------------------------------------------------
create table if not exists app.messaging_invite (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references app.tenant(id) on delete cascade,
  channel      text not null check (channel in ('telegram')),
  contact_id   uuid references app.contact(id)  on delete cascade,
  employee_id  uuid references app.employee(id) on delete cascade,
  token_hash   text not null,               -- hash, nunca o token
  expires_at   timestamptz not null default (now() + interval '7 days'),
  used_at      timestamptz,
  created_at   timestamptz not null default now(),
  constraint messaging_invite_um_titular
    check ((contact_id is null) <> (employee_id is null))
);

create unique index if not exists messaging_invite_token_uk
  on app.messaging_invite (token_hash);

comment on table app.messaging_invite is
  'Convite de adesão ao canal. O link https://t.me/<bot>?start=<token> É a '
  'credencial: quem o abrir vira o destinatário dos alertas individuais daquela '
  'pessoa. Por isso: uso único (used_at), validade de 7 dias (decisão do dono, '
  '15/09/2026), token_hash e nunca o token. ⛔ NENHUM papel do painel lê esta '
  'tabela, nem owner: RLS ligada, zero policy, sem grant a authenticated. Só '
  'service_role, pelo Caminho 2.';
comment on column app.messaging_invite.token_hash is
  'Hash do token do deep link, nunca o token. Vazamento do banco não entrega vínculo.';
comment on column app.messaging_invite.expires_at is
  'Validade curta — 7 dias por default. Convite velho circulando é o vetor.';
comment on column app.messaging_invite.used_at is
  'Preenchido no primeiro /start válido. Segundo clique não vincula.';

-- ---------------------------------------------------------------------------
-- 3. The boundary — owner item 1: the `app.integration_secret` rule
-- ---------------------------------------------------------------------------
alter table app.messaging_identity enable row level security;
alter table app.messaging_invite   enable row level security;

revoke all on table app.messaging_identity from anon, authenticated;
revoke all on table app.messaging_invite   from anon, authenticated;

-- ⛔ `select, insert, update` — and NOT `grant all`. `all` includes `delete`
--    and `truncate`, and this design revokes by `revoked_at` (identity) and
--    expires by `expires_at` / `used_at` (invite). Nobody deletes.
grant select, insert, update on table app.messaging_identity to service_role;
grant select, insert, update on table app.messaging_invite   to service_role;

-- No policy, on purpose. With RLS on and no policy, `authenticated` sees
-- nothing even if a future grant slips in — the same double lock as
-- `app.integration_secret`. Writing a policy here would be the mistake.

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_table     text;
  v_privilege text;
  v_n         int;
  v_def       text;
begin
  foreach v_table in array array['messaging_identity', 'messaging_invite'] loop
    if to_regclass('app.' || v_table) is null then
      raise exception 'app.% does not exist after being created', v_table;
    end if;

    -- 1. Rule 3 of CLAUDE.md: tenant_id and RLS, both.
    if not exists (
      select 1 from information_schema.columns
       where table_schema = 'app' and table_name = v_table and column_name = 'tenant_id'
    ) then
      raise exception 'app.% without tenant_id — rule 3 of CLAUDE.md', v_table;
    end if;
    if not (select relrowsecurity from pg_class where oid = ('app.' || v_table)::regclass) then
      raise exception 'app.% without RLS — rule 3 of CLAUDE.md', v_table;
    end if;

    -- 2. ⛔ ZERO policies. Here the absence IS the guarantee (owner item 1):
    --    a policy would be a door for `authenticated`, and nobody in the
    --    panel reads a chat_id.
    select count(*) into v_n from pg_policies
     where schemaname = 'app' and tablename = v_table;
    if v_n <> 0 then
      raise exception 'app.% has % policy(ies); the owner authorised none — no panel role reads the chat_id',
        v_table, v_n;
    end if;

    -- 3. Out of PostgREST in every verb. Asking only for `select` would let a
    --    `grant insert` through, and forging a link is worse than reading one.
    foreach v_privilege in array array['SELECT','INSERT','UPDATE','DELETE'] loop
      if has_table_privilege('authenticated', 'app.' || v_table, v_privilege) then
        raise exception 'authenticated has % on app.% — the design is Caminho 2 only', v_privilege, v_table;
      end if;
      if has_table_privilege('anon', 'app.' || v_table, v_privilege) then
        raise exception 'anon has % on app.%', v_privilege, v_table;
      end if;
    end loop;

    -- 4. The positive. Without it, item 3 is green on a table nobody reaches.
    foreach v_privilege in array array['SELECT','INSERT','UPDATE'] loop
      if not has_table_privilege('service_role', 'app.' || v_table, v_privilege) then
        raise exception 'service_role lacks % on app.% — the webhook and the sender could not work', v_privilege, v_table;
      end if;
    end loop;

    -- 5. And no delete, asked of the role that COULD delete.
    foreach v_privilege in array array['DELETE','TRUNCATE'] loop
      if has_table_privilege('service_role', 'app.' || v_table, v_privilege) then
        raise exception 'service_role has % on app.%; revoking is revoked_at, nothing is deleted', v_privilege, v_table;
      end if;
    end loop;
  end loop;

  -- 6. Exactly one holder, on both tables. Read from the catalogue: a check
  --    that lost the `<>` would accept a row with both holders or with none.
  foreach v_table in array array['messaging_identity', 'messaging_invite'] loop
    select pg_get_constraintdef(oid) into v_def
      from pg_constraint
     where conrelid = ('app.' || v_table)::regclass
       and conname = v_table || '_um_titular';
    if v_def is null or v_def not like '%<>%' then
      raise exception 'app.% lost the one-holder check: %', v_table, v_def;
    end if;
  end loop;

  -- 7. The three partial unique indexes of the identity, all over
  --    `revoked_at is null`: one current per contact, one per employee, and
  --    one person per chat_id. A history row (revoked) must not collide.
  foreach v_table in array array['messaging_identity_vigente_contact_uk',
                                 'messaging_identity_vigente_employee_uk',
                                 'messaging_identity_vigente_external_uk'] loop
    select pg_get_indexdef(i.indexrelid) into v_def
      from pg_index i join pg_class c on c.oid = i.indexrelid
     where c.relname = v_table and i.indisunique;
    if v_def is null then
      raise exception '% missing or not unique', v_table;
    end if;
    if v_def not ilike '%revoked_at is null%' then
      raise exception '% is not partial on revoked_at — a revoked row would block the person from coming back: %', v_table, v_def;
    end if;
  end loop;

  -- 8. The token hash is unique across the whole table, not per tenant: a
  --    token that resolves to two people is a link that binds the wrong one.
  if not exists (
    select 1 from pg_index i join pg_class c on c.oid = i.indexrelid
     where c.relname = 'messaging_invite_token_uk' and i.indisunique
       and pg_get_indexdef(i.indexrelid) not ilike '%where%'
  ) then
    raise exception 'messaging_invite_token_uk missing, not unique, or partial';
  end if;

  -- 9. Owner item 4: the invite expires in 7 days by default.
  select pg_get_expr(d.adbin, d.adrelid) into v_def
    from pg_attrdef d
    join pg_attribute a on a.attrelid = d.adrelid and a.attnum = d.adnum
   where d.adrelid = 'app.messaging_invite'::regclass and a.attname = 'expires_at';
  if v_def is null or v_def not ilike '%7 days%' then
    raise exception 'app.messaging_invite.expires_at does not default to 7 days: %', coalesce(v_def, '(no default)');
  end if;

  raise notice 'OK: messaging_identity and messaging_invite out of PostgREST, zero policies, one holder each, no delete, invite expires in 7 days.';
end $$;
