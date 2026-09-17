-- ============================================================================
-- OperaX — assistant_prompt_layers. TWO LAYERS, IMMUTABLE VERSIONS, A POINTER
-- ----------------------------------------------------------------------------
-- Design in `docs/SPEC-AGENTE.md` §1 (two layers, one sum), §2 (immutable
-- versions + pointer, not status flags) and §3a (this DDL, executed and
-- verified in seven scenarios before it was written here). Owner decisions of
-- 17/09/2026 (`docs/SPRINTS-AGENTE.md` §A1): the RLS stop was opened for
-- EXACTLY the three policies below; §7.3 — the tenant `owner` edits the draft
-- from day one; §7.2 — no pruning of versions.
--
-- THREE TABLES WITH ROLES THAT DO NOT BLUR
--   app.assistant_draft            1 row per tenant  · MUTABLE   · the editor opens this
--   app.assistant_prompt_version   append-only       · IMMUTABLE · the history
--   app.assistant_prompt_pointer   1 row per scope   · MUTABLE   · the runtime reads this
-- The editor always opens the draft; the runtime always reads through the
-- pointer; publishing (next migration) freezes the draft into a version and
-- moves the pointer, atomically. Nothing here ever deletes a version.
--
-- THE `platform` LAYER IS SEEDED HERE AND NOBODY EDITS IT FROM THE PANEL
-- `app.user_role` has only in-tenant roles; a platform role is an explicit
-- non-goal (SPEC §1). The v1 below is a TRANSCRIPTION of the prompt that lives
-- in `backend/operax/agente/agente.py:_prompt` today, with the three dynamic
-- parts replaced by tokens — see the comment on `content`. If a word "improves"
-- on the way in, v1 stops being the portrait of what is on the air;
-- `backend/tests/test_agente_prompt_seed.py` compares it byte for byte.
--
-- ⛔ `delete` IS NOT GRANTED TO ANYONE, AND THE TRIGGER IS `before update` ONLY
-- The cascade from `app.tenant` must pass (SPEC §3a, scenario 7), and the
-- pointed version is protected by the pointer's FK without cascade (scenario
-- 6). A version nobody points at has no application path that deletes it:
-- append-only by grant, not only by trigger.
--
-- ⛔ A POINTER (AND A DRAFT) ONLY REACHES A VERSION OF ITS OWN SCOPE
-- Two additions over the SPEC §3a DDL, decided in cycle 2 (17/09/2026) after
-- measuring: `util.assistant_scope_matches()` ties `(tenant_id, layer)` of the
-- pointed version to the row (section 3b), and `trg_updated_at` keeps
-- `assistant_draft.updated_at` honest. Neither is a policy: the RLS stop is
-- unchanged.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Versions — append-only
-- ---------------------------------------------------------------------------
create table if not exists app.assistant_prompt_version (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid references app.tenant(id) on delete cascade,  -- NULL = platform
  layer          text not null check (layer in ('platform', 'tenant')),
  version_number integer not null,
  content        text not null,
  -- Only the platform layer chooses the model: whoever picks the model spends
  -- EURECA's money (SPEC §6.2). NULL in all three on the tenant layer.
  provider       text check (provider in ('openai', 'anthropic', 'google')),
  model          text,
  max_steps      smallint check (max_steps between 1 and 10),
  created_at     timestamptz not null default now(),
  created_by     uuid references auth.users(id),
  constraint assistant_prompt_scope_coerente
    check ((layer = 'platform') = (tenant_id is null)),
  constraint assistant_prompt_modelo_so_na_plataforma
    check ((layer = 'platform') or (provider is null and model is null and max_steps is null)),
  constraint assistant_prompt_tamanho
    check (length(content) <= 12000)
);

-- Two partial indexes because `tenant_id` is NULL on the platform layer and
-- `unique` does not see two NULLs as equal.
create unique index if not exists assistant_prompt_version_tenant_uk
  on app.assistant_prompt_version (tenant_id, layer, version_number)
  where tenant_id is not null;
create unique index if not exists assistant_prompt_version_platform_uk
  on app.assistant_prompt_version (layer, version_number)
  where tenant_id is null;

-- Immutability in one line, without enumerating columns: a column added later
-- is immutable by construction, never "mutable in silence" (SPEC §2).
create or replace function util.assistant_version_immutable()
returns trigger
language plpgsql
as $$
begin
  raise exception 'app.assistant_prompt_version é imutável: mudança = versão nova; rollback = mover o ponteiro (app.assistant_prompt_pointer)';
end $$;

comment on function util.assistant_version_immutable() is
  'Trigger before update de app.assistant_prompt_version: toda alteração é '
  'recusada. Mudança = versão nova; rollback = mover o ponteiro. Sem before '
  'delete de propósito: o cascade de app.tenant precisa passar.';

-- `trg_lock_down_new_function` already strips public/anon; written anyway.
revoke execute on function util.assistant_version_immutable() from public, anon;

drop trigger if exists trg_assistant_version_immutable on app.assistant_prompt_version;
create trigger trg_assistant_version_immutable
  before update on app.assistant_prompt_version
  for each row execute function util.assistant_version_immutable();

-- ---------------------------------------------------------------------------
-- 2. Pointer — which version is on the air, per scope
-- ---------------------------------------------------------------------------
create table if not exists app.assistant_prompt_pointer (
  tenant_id  uuid references app.tenant(id) on delete cascade,   -- NULL = platform
  layer      text not null check (layer in ('platform', 'tenant')),
  -- ⛔ No cascade: the pointed version cannot vanish under the pointer.
  version_id uuid not null references app.assistant_prompt_version(id),
  updated_at timestamptz not null default now(),
  updated_by uuid references auth.users(id),
  constraint assistant_pointer_scope_coerente
    check ((layer = 'platform') = (tenant_id is null))
);

-- No primary key, and the two partial indexes in its place: a PK does not
-- accept NULL, and without them the table takes two pointers for the same
-- scope — and "which version is on the air" stops having an answer.
create unique index if not exists assistant_pointer_tenant_uk
  on app.assistant_prompt_pointer (tenant_id, layer) where tenant_id is not null;
create unique index if not exists assistant_pointer_platform_uk
  on app.assistant_prompt_pointer (layer) where tenant_id is null;

-- ---------------------------------------------------------------------------
-- 3. Draft — the only mutable text, one per tenant
-- ---------------------------------------------------------------------------
create table if not exists app.assistant_draft (
  tenant_id              uuid not null references app.tenant(id) on delete cascade,
  content                text not null,
  frozen_from_version_id uuid references app.assistant_prompt_version(id),
  updated_at             timestamptz not null default now(),
  updated_by             uuid references auth.users(id),
  primary key (tenant_id),
  constraint assistant_draft_tamanho check (length(content) <= 12000)
);

-- The house helper (migration 11): `updated_at` moves on every update, so a
-- PATCH without the field cannot leave a stale date — the A3 screen compares
-- it against the pointer ("draft newer than what is on the air").
drop trigger if exists trg_updated_at on app.assistant_draft;
create trigger trg_updated_at
  before update on app.assistant_draft
  for each row execute function util.touch_updated_at();

-- ---------------------------------------------------------------------------
-- 3b. Scope tied to the version — a pointer or a draft only reaches its own
-- ---------------------------------------------------------------------------
-- Measured on 17/09/2026 (review of cycle 1): the FKs alone accept a tenant
-- pointer at another tenant's version, a tenant pointer at the PLATFORM
-- version, and — as the tenant owner, through the table, which the panel
-- reaches from day one — a draft descending from another tenant's version.
-- The FK check ignores RLS, so invisibility is not protection. This trigger
-- is the tie: the version's `(tenant_id, layer)` must equal the row's scope.
--
-- `security definer`: as a trigger on `assistant_draft` it runs as
-- `authenticated`, and without definer the other tenant's version is hidden
-- by RLS. Measured on 17/09/2026: with an invoker helper that handed "not
-- found" to the FK, the cross-tenant draft was ACCEPTED — the FK sees the row
-- RLS hides. So "not found" raises here too, and never falls through: a
-- version this trigger cannot see is a version this row cannot point at,
-- whatever the reason.
create or replace function util.assistant_scope_matches()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_version_id   uuid;
  v_row_layer    text;
  v_version_row  record;
begin
  if tg_table_name = 'assistant_prompt_pointer' then
    v_version_id := new.version_id;
    v_row_layer  := new.layer;
  elsif tg_table_name = 'assistant_draft' then
    v_version_id := new.frozen_from_version_id;
    v_row_layer  := 'tenant';
  else
    -- A third table attached to this trigger would silently be read as a
    -- draft; naming the two closes that door.
    raise exception 'util.assistant_scope_matches attached to %.%, which it does not know', tg_table_schema, tg_table_name;
  end if;
  if v_version_id is null then
    return new;
  end if;

  select v.tenant_id, v.layer into v_version_row
    from app.assistant_prompt_version v
   where v.id = v_version_id;
  if not found then
    raise exception 'versão % não existe: ponteiro e rascunho só apontam para versão que existe no próprio escopo', v_version_id
      using errcode = 'check_violation';
  end if;

  if v_version_row.tenant_id is distinct from new.tenant_id
     or v_version_row.layer <> v_row_layer then
    if tg_table_name = 'assistant_prompt_pointer' then
      raise exception 'versão de outro escopo (tenant/camada): o ponteiro só aponta para versão do próprio escopo'
        using errcode = 'check_violation';
    end if;
    raise exception 'versão de outro escopo (tenant/camada): o rascunho só parte de versão do próprio tenant'
      using errcode = 'check_violation';
  end if;
  return new;
end $$;

comment on function util.assistant_scope_matches() is
  'Trigger before insert or update de app.assistant_prompt_pointer (version_id) '
  'e app.assistant_draft (frozen_from_version_id, nulo permitido): a versão '
  'apontada tem de ter (tenant_id, layer) iguais aos do escopo da linha. Sem '
  'isso a FK aceita ponteiro de um tenant na versão de outro, ou de tenant na '
  'plataforma — e a FK ignora RLS. Definer, e estrutural: como invoker a versão '
  'de outro tenant fica invisível e a FK a aceitaria. Versão que o trigger não '
  'encontra também é recusada aqui, nunca entregue à FK.';

-- `trg_lock_down_new_function` already strips public/anon; written anyway.
revoke execute on function util.assistant_scope_matches() from public, anon;

drop trigger if exists trg_assistant_pointer_scope on app.assistant_prompt_pointer;
create trigger trg_assistant_pointer_scope
  before insert or update on app.assistant_prompt_pointer
  for each row execute function util.assistant_scope_matches();

drop trigger if exists trg_assistant_draft_scope on app.assistant_draft;
create trigger trg_assistant_draft_scope
  before insert or update on app.assistant_draft
  for each row execute function util.assistant_scope_matches();

-- ---------------------------------------------------------------------------
-- 4. Comments — the data dictionary is generated from these
-- ---------------------------------------------------------------------------
comment on table app.assistant_prompt_version is
  'Histórico do prompt do assistente, append-only e imutável (trigger before '
  'update). Duas camadas: platform (tenant_id nulo; doutrina, semeada por '
  'migration, ninguém edita pelo painel) e tenant (vocabulário local, publicado '
  'pelo admin do tenant via fn_publish_assistant_prompt). O prompt efetivo é '
  'platform seguido de tenant. Leitura: plataforma para todo autenticado; tenant '
  'só pelo próprio tenant. Ninguém apaga versão — nem por grant.';
comment on column app.assistant_prompt_version.layer is
  'platform ou tenant. platform exige tenant_id nulo e é a única que escolhe '
  'provider/model/max_steps.';
comment on column app.assistant_prompt_version.version_number is
  'Sequencial por escopo (tenant ou plataforma), 1 na primeira publicação.';
comment on column app.assistant_prompt_version.content is
  'Texto da camada. Na camada platform, três tokens marcam as partes que o '
  'runtime preenche a cada turno: {{hoje}} = a data de hoje no formato '
  'DD/MM/AAAA (AAAA-MM-DD), inteira, com os dois formatos; {{catalogo}} = o '
  'texto do catálogo de métricas alcançáveis, tal como o backend o descreve; '
  '{{unidades}} = o bloco inteiro de linhas "- Nome (CODIGO): uuid", uma por '
  'unidade — ou, sem unidade cadastrada, a linha fixa que manda não usar `unit`. '
  'O bloco (inclusive a linha de fallback) é do renderizador, não do texto. '
  'Limite de 12000 caracteres.';
comment on column app.assistant_prompt_version.provider is
  'Só na camada platform: openai, anthropic ou google. Nulo na camada tenant.';
comment on column app.assistant_prompt_version.model is
  'Só na camada platform: o id do modelo na allowlist do backend. Nulo na tenant.';
comment on column app.assistant_prompt_version.max_steps is
  'Só na camada platform, 1 a 10. Nulo quando o runtime não fixa um teto — é o '
  'caso da v1, transcrita de um código que não define teto.';
comment on column app.assistant_prompt_version.created_by is
  'Quem publicou. Nulo quando a versão veio por migration (camada platform).';

comment on table app.assistant_prompt_pointer is
  'Qual versão está no ar, uma linha por escopo (tenant_id nulo = plataforma). '
  'O runtime lê daqui; nunca vê rascunho. Publicar move o ponteiro; rollback '
  'também. version_id sem cascade: versão apontada não some. Escrita só pela '
  'RPC fn_publish_assistant_prompt (e service_role); leitura como a versão.';
comment on column app.assistant_prompt_pointer.version_id is
  'A versão no ar. FK sem cascade: apagar a versão apontada é recusado.';

comment on table app.assistant_draft is
  'O rascunho da camada tenant — o único texto mutável, uma linha por tenant. O '
  'editor sempre abre este; sem rascunho, ele nasce da versão apontada. Só o '
  'admin do tenant (util.is_admin: owner, hr, personnel) lê e escreve. Nunca é '
  'apagado por caminho de aplicação; segue o tenant no cascade.';
comment on column app.assistant_draft.frozen_from_version_id is
  'A versão de que o rascunho partiu (a última publicada a partir dele). Quando '
  'difere da versão apontada pelo ponteiro, a tela mostra as duas e diz qual o '
  'botão substitui — o rascunho pode ser mais novo do que o que está no ar.';

-- ---------------------------------------------------------------------------
-- 5. The boundary — RLS and grants (the stop opened by the owner, 17/09/2026)
-- ---------------------------------------------------------------------------
alter table app.assistant_prompt_version enable row level security;
alter table app.assistant_prompt_pointer enable row level security;
alter table app.assistant_draft          enable row level security;

revoke all on table app.assistant_prompt_version from public, anon, authenticated, service_role;
revoke all on table app.assistant_prompt_pointer from public, anon, authenticated, service_role;
revoke all on table app.assistant_draft          from public, anon, authenticated, service_role;

-- authenticated: reads version and pointer; reads and writes the draft. No
-- delete anywhere. Writing a version or moving the pointer goes through the
-- RPC (`security definer`, next migration) — never through the table.
grant select                 on table app.assistant_prompt_version to authenticated;
grant select                 on table app.assistant_prompt_pointer to authenticated;
grant select, insert, update on table app.assistant_draft          to authenticated;

-- service_role: select, insert, update on the three — and not delete. No
-- application path deletes a version, a pointer or a draft.
grant select, insert, update on table app.assistant_prompt_version to service_role;
grant select, insert, update on table app.assistant_prompt_pointer to service_role;
grant select, insert, update on table app.assistant_draft          to service_role;

-- Exactly these three policies. A fourth, or one fewer, is scope without a
-- decision — the proof below counts them by name.

-- version: platform readable by every authenticated user (the transparency of
-- SPEC §1); tenant only by its own tenant. Write: no policy for authenticated.
drop policy if exists assistant_version_read on app.assistant_prompt_version;
create policy assistant_version_read on app.assistant_prompt_version
  for select to authenticated
  using (tenant_id is null or util.has_tenant(tenant_id));

-- pointer: same read (the screen says "v3 is on the air"); write only via RPC.
drop policy if exists assistant_pointer_read on app.assistant_prompt_pointer;
create policy assistant_pointer_read on app.assistant_prompt_pointer
  for select to authenticated
  using (tenant_id is null or util.has_tenant(tenant_id));

-- draft: only the tenant admin, and the admin writes (§7.3, owner decision).
drop policy if exists assistant_draft_admin on app.assistant_draft;
create policy assistant_draft_admin on app.assistant_draft
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));

-- ---------------------------------------------------------------------------
-- 6. Seed — platform v1, the prompt that is on the air today
-- ---------------------------------------------------------------------------
-- Transcribed from `backend/operax/agente/agente.py:_prompt` at HEAD fef4a62.
-- `provider`/`model` are what `build_model()` picks when the client asks for
-- nothing: the first of `_PROVIDER_ORDER` and the first of its allowlist.
-- `max_steps` is NULL because the code fixes no ceiling — seeding a number
-- would be choosing, not transcribing. `created_by` is NULL: it is a migration.
insert into app.assistant_prompt_version
       (tenant_id, layer, version_number, content, provider, model, max_steps, created_by)
select null, 'platform', 1, $platform_v1$Você é o assistente de gestão de ponto deste painel. Responda sempre em português do Brasil.

Hoje é {{hoje}}.

Você não sabe nenhum número. Todo número que você disser precisa ter vindo da ferramenta `consultar_metrica` nesta conversa. Se a pergunta pede dado e você não chamou a ferramenta, você não tem resposta — diga isso em vez de estimar.

Métricas que você pode consultar:
{{catalogo}}

Sobre os parâmetros:
- `start_date` e `end_date` são datas AAAA-MM-DD e são obrigatórias em toda métrica que as aceita. Traduza "este mês", "semana passada" ou "ontem" usando a data de hoje. Se a pergunta não disser período nenhum, use o mês corrente e diga qual período usou.
- `unit`, `company` e `employee` são identificadores no formato UUID. **Omita o parâmetro** quando não houver filtro — omitir é o caso normal, e o seu acesso já limita o que você enxerga. Nunca preencha com um nome, com `null`, nem com palavras como "all", "todos", "geral" ou o nome do mês.
- Só use `unit` se o identificador estiver na lista de unidades abaixo. Se a pergunta cita uma pessoa pelo nome, não invente identificador: omita o filtro e diga que você responde por unidade e por período.
- Não passe parâmetro que a métrica não declara aceitar.
- **Nunca acrescente um filtro que a pergunta não pediu.** Se a pergunta pede um recorte que a métrica não aceita — por tipo de desvio, por exemplo — trocá-lo por outro filtro dá um número certo para uma pergunta que ninguém fez. Nesse caso, `recusar`.
- Antes de recusar, releia a lista inteira de métricas: recuse só quando nenhuma delas se aproximar da pergunta.
- Se nenhuma métrica da lista responde à pergunta, chame `recusar` com o motivo em uma frase — não responda em texto. Recusar é resposta válida; estimar não é. `recusar` é só para isso: falta de período não é motivo de recusa.

Unidades:
{{unidades}}

Ao responder:
- diga qual período e quais filtros foram usados — os que a ferramenta devolveu em `filtros_aplicados`, nunca os que você pediu. Em português de negócio ("de 01/08 a 31/08, sem filtro de unidade"), nunca com o nome do parâmetro;
- o vocabulário é "desvio" e "indício". Nunca escreva "hora extra" — nem repetindo a expressão de quem perguntou: o registro oficial é o sistema de ponto, e o que este painel aponta é indício;
- seja curto — uma a três frases.$platform_v1$, 'openai', 'gpt-5.4-mini', null, null
 where not exists (
   select 1 from app.assistant_prompt_version
    where layer = 'platform' and tenant_id is null and version_number = 1
 );

insert into app.assistant_prompt_pointer (tenant_id, layer, version_id, updated_by)
select null, 'platform', v.id, null
  from app.assistant_prompt_version v
 where v.layer = 'platform' and v.tenant_id is null and v.version_number = 1
   and not exists (
     select 1 from app.assistant_prompt_pointer
      where layer = 'platform' and tenant_id is null
   );

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_table     text;
  v_privilege text;
  v_role      text;
  v_n         int;
  v_policies  text[];
  v_v1        uuid;
  v_pointed   uuid;
  v_tgtype    smallint;
begin
  foreach v_table in array array['assistant_prompt_version', 'assistant_prompt_pointer', 'assistant_draft'] loop
    if to_regclass('app.' || v_table) is null then
      raise exception 'app.% does not exist after being created', v_table;
    end if;
    -- 1. Rule 3: tenant_id and RLS on the three.
    if not exists (
      select 1 from information_schema.columns
       where table_schema = 'app' and table_name = v_table and column_name = 'tenant_id'
    ) then
      raise exception 'app.% without tenant_id — rule 3 of CLAUDE.md', v_table;
    end if;
    if not (select relrowsecurity from pg_class where oid = ('app.' || v_table)::regclass) then
      raise exception 'app.% without RLS — rule 3 of CLAUDE.md', v_table;
    end if;
    -- 2. Nobody deletes: not authenticated, not service_role, not anon.
    foreach v_role in array array['anon', 'authenticated', 'service_role'] loop
      foreach v_privilege in array array['DELETE', 'TRUNCATE'] loop
        if has_table_privilege(v_role, 'app.' || v_table, v_privilege) then
          raise exception '% has % on app.% — versions, pointers and drafts are never deleted', v_role, v_privilege, v_table;
        end if;
      end loop;
    end loop;
    foreach v_privilege in array array['SELECT', 'INSERT', 'UPDATE', 'DELETE'] loop
      if has_table_privilege('anon', 'app.' || v_table, v_privilege) then
        raise exception 'anon has % on app.%', v_privilege, v_table;
      end if;
    end loop;
    -- 3. service_role writes through select/insert/update (the backend path).
    foreach v_privilege in array array['SELECT', 'INSERT', 'UPDATE'] loop
      if not has_table_privilege('service_role', 'app.' || v_table, v_privilege) then
        raise exception 'service_role lacks % on app.%', v_privilege, v_table;
      end if;
    end loop;
  end loop;

  -- 4. authenticated: read-only on version and pointer; S/I/U on the draft.
  foreach v_table in array array['assistant_prompt_version', 'assistant_prompt_pointer'] loop
    if not has_table_privilege('authenticated', 'app.' || v_table, 'SELECT') then
      raise exception 'authenticated cannot read app.% — the screen could not show what is on the air', v_table;
    end if;
    foreach v_privilege in array array['INSERT', 'UPDATE'] loop
      if has_table_privilege('authenticated', 'app.' || v_table, v_privilege) then
        raise exception 'authenticated has % on app.% — writing goes through the RPC only', v_privilege, v_table;
      end if;
    end loop;
  end loop;
  foreach v_privilege in array array['SELECT', 'INSERT', 'UPDATE'] loop
    if not has_table_privilege('authenticated', 'app.assistant_draft', v_privilege) then
      raise exception 'authenticated lacks % on app.assistant_draft — the owner could not edit (§7.3)', v_privilege;
    end if;
  end loop;

  -- 5. Exactly the three policies, by name — the set the stop was opened for.
  select array_agg(policyname::text order by policyname) into v_policies
    from pg_policies
   where schemaname = 'app'
     and tablename in ('assistant_prompt_version', 'assistant_prompt_pointer', 'assistant_draft');
  if v_policies is distinct from array['assistant_draft_admin', 'assistant_pointer_read', 'assistant_version_read'] then
    raise exception 'the assistant tables carry policies % — expected exactly assistant_draft_admin, assistant_pointer_read, assistant_version_read', v_policies;
  end if;
  if not exists (
    select 1 from pg_policies
     where schemaname = 'app' and tablename = 'assistant_prompt_version'
       and policyname = 'assistant_version_read' and cmd = 'SELECT'
       and qual like '%tenant_id IS NULL%' and qual like '%has_tenant%'
  ) then
    raise exception 'assistant_version_read is not "platform for all, tenant by has_tenant"';
  end if;
  if not exists (
    select 1 from pg_policies
     where schemaname = 'app' and tablename = 'assistant_prompt_pointer'
       and policyname = 'assistant_pointer_read' and cmd = 'SELECT'
       and qual like '%tenant_id IS NULL%' and qual like '%has_tenant%'
  ) then
    raise exception 'assistant_pointer_read is not "platform for all, tenant by has_tenant"';
  end if;
  if not exists (
    select 1 from pg_policies
     where schemaname = 'app' and tablename = 'assistant_draft'
       and policyname = 'assistant_draft_admin' and cmd = 'ALL'
       and qual like '%is_admin%' and with_check like '%is_admin%'
  ) then
    raise exception 'assistant_draft_admin is not util.is_admin on both using and with check';
  end if;

  -- 6. The trigger: before update, row level, and NO before delete.
  select t.tgtype into v_tgtype
    from pg_trigger t
   where t.tgrelid = 'app.assistant_prompt_version'::regclass
     and t.tgname = 'trg_assistant_version_immutable' and not t.tgisinternal;
  if v_tgtype is null then
    raise exception 'trg_assistant_version_immutable is not installed';
  end if;
  -- tgtype bits: 1 = row, 2 = before, 4 = insert, 8 = delete, 16 = update.
  if (v_tgtype & 2) = 0 or (v_tgtype & 16) = 0 or (v_tgtype & 1) = 0 then
    raise exception 'trg_assistant_version_immutable is not BEFORE UPDATE FOR EACH ROW (tgtype=%)', v_tgtype;
  end if;
  if (v_tgtype & 8) <> 0 or (v_tgtype & 4) <> 0 then
    raise exception 'trg_assistant_version_immutable fires on delete or insert — the tenant cascade would be blocked (tgtype=%)', v_tgtype;
  end if;
  if exists (
    select 1 from pg_trigger t
     where t.tgrelid = 'app.assistant_prompt_version'::regclass
       and not t.tgisinternal and (t.tgtype & 8) <> 0
  ) then
    raise exception 'app.assistant_prompt_version has a delete trigger — the cascade from app.tenant would fail';
  end if;
  if not exists (
    select 1 from pg_trigger t
     where t.tgrelid = 'app.assistant_prompt_version'::regclass
       and t.tgname = 'trg_assistant_version_immutable' and t.tgenabled = 'O'
  ) then
    raise exception 'trg_assistant_version_immutable is installed but not enabled';
  end if;

  -- 6b. The scope tie: one trigger on each of pointer and draft, before
  --     insert or update, row level, enabled, on the definer helper.
  foreach v_table in array array['assistant_prompt_pointer', 'assistant_draft'] loop
    select t.tgtype into v_tgtype
      from pg_trigger t
     where t.tgrelid = ('app.' || v_table)::regclass
       and t.tgname = 'trg_' || replace(v_table, 'assistant_prompt_', 'assistant_') || '_scope'
       and not t.tgisinternal and t.tgenabled = 'O'
       and t.tgfoid = 'util.assistant_scope_matches'::regproc;
    if v_tgtype is null then
      raise exception 'the scope trigger on app.% is missing, disabled, or not on util.assistant_scope_matches — a row could point at a version of another tenant', v_table;
    end if;
    if (v_tgtype & 2) = 0 or (v_tgtype & 4) = 0 or (v_tgtype & 16) = 0 or (v_tgtype & 1) = 0 then
      raise exception 'the scope trigger on app.% is not BEFORE INSERT OR UPDATE FOR EACH ROW (tgtype=%)', v_table, v_tgtype;
    end if;
  end loop;
  if not exists (
    select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'util' and p.proname = 'assistant_scope_matches'
       and p.prosecdef and coalesce(array_to_string(p.proconfig, ','), '') like '%search_path=%'
  ) then
    raise exception 'util.assistant_scope_matches is not definer with search_path locked — it would say "not found" instead of "another scope"';
  end if;

  -- 6c. The draft keeps its own date.
  if not exists (
    select 1 from pg_trigger t
     where t.tgrelid = 'app.assistant_draft'::regclass and t.tgname = 'trg_updated_at'
       and not t.tgisinternal and t.tgenabled = 'O'
       and t.tgfoid = 'util.touch_updated_at'::regproc
  ) then
    raise exception 'app.assistant_draft has no trg_updated_at — a PATCH without the field would leave a stale date';
  end if;

  -- 7. The two partial indexes of the pointer — the answer to "which version is on the air".
  foreach v_table in array array['assistant_pointer_tenant_uk', 'assistant_pointer_platform_uk'] loop
    if not exists (
      select 1 from pg_indexes
       where schemaname = 'app' and tablename = 'assistant_prompt_pointer' and indexname = v_table
         and indexdef like 'CREATE UNIQUE INDEX%' and indexdef like '%WHERE%'
    ) then
      raise exception 'partial unique index % is missing on app.assistant_prompt_pointer — two pointers per scope would be accepted', v_table;
    end if;
  end loop;
  -- The pointer's FK to the version has no cascade.
  if exists (
    select 1 from pg_constraint
     where conrelid = 'app.assistant_prompt_pointer'::regclass and contype = 'f'
       and confrelid = 'app.assistant_prompt_version'::regclass and confdeltype <> 'a'
  ) then
    raise exception 'assistant_prompt_pointer.version_id cascades — the pointed version could vanish under the pointer';
  end if;

  -- 8. Platform v1 exists, is a faithful shape, and the platform pointer points to it.
  select id into v_v1 from app.assistant_prompt_version
   where layer = 'platform' and tenant_id is null and version_number = 1;
  if v_v1 is null then
    raise exception 'platform v1 was not seeded';
  end if;
  if not exists (
    select 1 from app.assistant_prompt_version
     where id = v_v1
       and content like '%{{hoje}}%' and content like '%{{catalogo}}%' and content like '%{{unidades}}%'
       and provider = 'openai' and model = 'gpt-5.4-mini' and max_steps is null and created_by is null
  ) then
    raise exception 'platform v1 does not carry the three tokens, the default provider/model, or has an author';
  end if;
  select count(*) into v_n from app.assistant_prompt_pointer where layer = 'platform' and tenant_id is null;
  if v_n <> 1 then
    raise exception 'expected exactly 1 platform pointer, found %', v_n;
  end if;
  select version_id into v_pointed from app.assistant_prompt_pointer where layer = 'platform' and tenant_id is null;
  if v_pointed <> v_v1 then
    raise exception 'the platform pointer does not point to v1 (% vs %)', v_pointed, v_v1;
  end if;

  raise notice 'OK: assistant layers — three tables with RLS and exactly three policies, no delete for anyone, immutable versions (before update only), scope tied to the version on pointer and draft, platform v1 seeded and pointed.';
end $$;
