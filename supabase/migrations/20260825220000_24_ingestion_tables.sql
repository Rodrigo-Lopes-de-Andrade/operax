-- ============================================================================
-- OperaX — 24. AS QUATRO TABELAS DE INGESTÃO ENTRAM NAS MIGRATIONS
-- ----------------------------------------------------------------------------
-- `app.batida_marcacao`, `app.cursor_sincronizacao`, `app.empresa_evento_status`
-- e `app.funcionario_evento_status` existem em produção desde antes deste
-- repositório e chegam à suíte pelo `scripts/_baseline.sql`, que é um dump de
-- produção. **Nenhuma migration daqui as criava**, e a consequência era concreta:
-- o banco de desenvolvimento não as tem, porque ele foi criado sem o baseline.
-- Qualquer tela que leia marcação do dia responde 500 em dev e derruba o E2E.
--
-- O QUE ESTA MIGRATION NÃO FAZ, E É O PONTO
-- Não renomeia nada. A migration 11b congelou estas quatro justamente porque as
-- Edge Functions escrevem nelas por nome literal em string JS e não existe teste
-- do outro lado — "congelar é reversível; quebrar a sincronização não é". Criar
-- com o mesmo nome não toca nesse risco: onde elas já existem, `if not exists`
-- não faz nada, e é exatamente o caso de produção e do `make db-test`.
--
-- AS POLICIES NÃO SÃO NOVAS
-- `<tabela>_tenant_read` com `util.has_tenant(tenant_id)` é o predicado que já
-- vigora em produção hoje — copiado do catálogo real, não escrito de novo. Onde
-- a tabela já existe, o `drop policy if exists` + `create policy` reafirma o
-- mesmo texto.
--
-- DUAS DIVERGÊNCIAS DELIBERADAS EM RELAÇÃO A PRODUÇÃO
--
-- 1. `tenant_id` NÃO ganha default. Onde a tabela é anterior a este repositório
--    a coluna tem `default '<uuid>'::uuid` — o identificador de um tenant
--    específico, gravado na definição da coluna, e o valor **difere** entre
--    produção e o baseline da suíte (conferido: são dois uuids diferentes).
--    Copiar qualquer um deles poria o identificador de um cliente dentro deste
--    repositório e faria toda instalação nova nascer apontando para ele.
--    As Edge Functions gravam `tenant_id` explicitamente, então o default é
--    rede de segurança de uma migração antiga, não contrato. Onde ele já existe,
--    esta migration não o remove: mexer nisso é decisão à parte.
--
-- 2. As chaves estrangeiras para `secullum."Batida"` e `secullum."Funcionario"`
--    entram **só se o alvo existir**. O banco de desenvolvimento tem `secullum`
--    com zero tabela, e uma FK para relação inexistente aborta a migration. Onde
--    o espelho existe — produção e a suíte — a FK é criada com o mesmo
--    `on delete cascade` de lá.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

create table if not exists app.batida_marcacao (
  id              uuid primary key default gen_random_uuid(),
  batida_id       uuid not null,
  funcionario_id  uuid not null,
  data            date not null,
  tipo_coluna     text not null,
  indice_coluna   smallint not null,
  valor_bruto     text,
  hora            time,
  status_rotulo   text,
  "Memoria"       time,
  "EquipId"       integer,
  "FonteDadosId"  bigint,
  desconsiderada  boolean not null default false,
  sincronizado_em timestamptz not null default now(),
  criado_em       timestamptz not null default now(),
  atualizado_em   timestamptz not null default now(),
  tenant_id       uuid
);

create unique index if not exists batida_marcacao_posicao_key
  on app.batida_marcacao (batida_id, tipo_coluna, indice_coluna);
create index if not exists batida_marcacao_fontedadosid_idx
  on app.batida_marcacao ("FonteDadosId");
create index if not exists batida_marcacao_funcionario_id_data_idx
  on app.batida_marcacao (funcionario_id, data);
create index if not exists batida_marcacao_hora_idx
  on app.batida_marcacao (funcionario_id, data) where hora is not null;
create index if not exists batida_marcacao_tenant_idx
  on app.batida_marcacao (tenant_id);

create table if not exists app.cursor_sincronizacao (
  chave         text primary key,
  valor         text,
  atualizado_em timestamptz not null default now(),
  tenant_id     uuid
);
create index if not exists cursor_sincronizacao_tenant_idx
  on app.cursor_sincronizacao (tenant_id);

create table if not exists app.empresa_evento_status (
  id             uuid primary key default gen_random_uuid(),
  empresa_id     uuid not null,
  tipo_evento    text not null,
  ativo_anterior boolean,
  ativo_novo     boolean not null,
  detectado_em   timestamptz not null default now(),
  origem         text not null default 'secullum_sync',
  criado_em      timestamptz not null default now(),
  tenant_id      uuid
);
create unique index if not exists empresa_evento_status_baseline_uniq
  on app.empresa_evento_status (empresa_id) where tipo_evento = 'baseline';
create index if not exists empresa_evento_status_empresa_detectado_idx
  on app.empresa_evento_status (empresa_id, detectado_em desc);
create index if not exists empresa_evento_status_tenant_idx
  on app.empresa_evento_status (tenant_id);

create table if not exists app.funcionario_evento_status (
  id                 uuid primary key default gen_random_uuid(),
  funcionario_id     uuid not null,
  tipo_evento        text not null,
  ativo_anterior     boolean,
  ativo_novo         boolean not null,
  data_evento        date,
  admissao_anterior  date,
  admissao_nova      date,
  demissao_anterior  date,
  demissao_nova      date,
  detectado_em       timestamptz not null default now(),
  origem             text not null default 'secullum_sync',
  criado_em          timestamptz not null default now(),
  tenant_id          uuid
);
create unique index if not exists funcionario_evento_status_baseline_uniq
  on app.funcionario_evento_status (funcionario_id) where tipo_evento = 'baseline';
create index if not exists funcionario_evento_status_funcionario_data_evento_idx
  on app.funcionario_evento_status (funcionario_id, data_evento);
create index if not exists funcionario_evento_status_funcionario_detectado_idx
  on app.funcionario_evento_status (funcionario_id, detectado_em desc);
create index if not exists funcionario_evento_status_tenant_idx
  on app.funcionario_evento_status (tenant_id);

-- ---------------------------------------------------------------------------
-- FKs para o espelho — só onde o espelho existe
-- ---------------------------------------------------------------------------
do $$
begin
  if to_regclass('secullum."Batida"') is not null
     and not exists (select 1 from pg_constraint where conname = 'batida_marcacao_batida_id_fkey')
  then
    alter table app.batida_marcacao
      add constraint batida_marcacao_batida_id_fkey
      foreign key (batida_id) references secullum."Batida"(id) on delete cascade;
  end if;

  if to_regclass('secullum."Funcionario"') is not null
     and not exists (select 1 from pg_constraint where conname = 'batida_marcacao_funcionario_id_fkey')
  then
    alter table app.batida_marcacao
      add constraint batida_marcacao_funcionario_id_fkey
      foreign key (funcionario_id) references secullum."Funcionario"(id) on delete cascade;
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- RLS — o mesmo predicado que já vigora em produção
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array[
    'batida_marcacao','cursor_sincronizacao','empresa_evento_status','funcionario_evento_status'
  ] loop
    execute format('alter table app.%I enable row level security', t);
    execute format('revoke all on table app.%I from anon', t);
    execute format('drop policy if exists %I on app.%I', t || '_tenant_read', t);
    execute format(
      'create policy %I on app.%I for select to authenticated using (util.has_tenant(tenant_id))',
      t || '_tenant_read', t);
    execute format('grant select on app.%I to authenticated', t);
    execute format('grant all    on app.%I to service_role', t);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  t     text;
  v_pol int;
begin
  foreach t in array array[
    'batida_marcacao','cursor_sincronizacao','empresa_evento_status','funcionario_evento_status'
  ] loop
    -- 1. Existe, em `app` e não em `public`.
    if to_regclass('app.' || t) is null then
      raise exception 'app.% não existe depois desta migration', t;
    end if;
    if to_regclass('public.' || t) is not null then
      raise exception '%: sobrou cópia em public — nenhuma tabela vive lá', t;
    end if;

    -- 2. RLS ligada, com exatamente uma policy de leitura por tenant.
    if not (select relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'app' and c.relname = t) then
      raise exception 'app.% está sem RLS', t;
    end if;
    select count(*) into v_pol from pg_policy p join pg_class c on c.oid = p.polrelid
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'app' and c.relname = t;
    if v_pol <> 1 then
      raise exception 'app.% tem % policies, esperava 1', t, v_pol;
    end if;

    -- 3. `anon` não alcança nenhuma delas.
    if has_table_privilege('anon', 'app.' || t, 'select') then
      raise exception 'anon lê app.%', t;
    end if;
  end loop;

  -- 4. As quatro carregam `tenant_id`, que é o que a policy filtra. Um default
  --    com uuid de cliente pode existir onde a tabela é anterior a este
  --    repositório — e esta migration não o cria nem o remove: o valor varia
  --    entre produção e a suíte, e apagá-lo é decisão à parte, não efeito
  --    colateral de criar a tabela em quem não a tinha.
  foreach t in array array[
    'batida_marcacao','cursor_sincronizacao','empresa_evento_status','funcionario_evento_status'
  ] loop
    if not exists (
      select 1 from information_schema.columns
      where table_schema = 'app' and table_name = t
        and column_name = 'tenant_id' and data_type = 'uuid'
    ) then
      raise exception 'app.% não tem tenant_id uuid — a policy não teria o que filtrar', t;
    end if;
  end loop;

  raise notice 'OK: as quatro tabelas de ingestão existem, com RLS e com tenant_id.';
end $$;
