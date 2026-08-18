-- ============================================================================
-- OperaX — 09. INTEGRATIONS, IMPORTS, AUDIT AND SEMANTIC LAYER
-- ----------------------------------------------------------------------------
-- Credenciais NUNCA em coluna de text. O segredo vive no Supabase Vault
-- (extensão supabase_vault) e aqui fica só o UUID que o reference. Cada tenant
-- tem sua própria instância de Secullum e seu próprio token — cofre por tenant
-- é requisito de multi-tenant, não refinamento.
--
-- CAMADA SEMÂNTICA (app.metric): o assistente de IA NÃO faz text-to-SQL livre.
-- Com salário e dado de saúde em base multi-tenant, LLM gerando SQL solto é
-- vazamento cruzado e resposta errada apresentada com confiança. O assistente
-- escolhe uma métrica do catálogo e preenche parâmetros; a consulta roda como o
-- usuário que perguntou, herdando exatamente a RLS dele.
-- ============================================================================

-- Vault existe no Supabase gerenciado; em Postgres local (CI) não. Tolerar a
-- ausência permite rodar a suíte inteira em banco descartável.
do $$
begin
  create extension if not exists supabase_vault with schema vault;
exception when others then
  raise notice 'supabase_vault indisponível (%). Em ambiente local isso é esperado; em produção o Vault é obrigatório para app.integration_secret.', sqlerrm;
end $$;

-- ---------------------------------------------------------------------------
-- Integrações
-- ---------------------------------------------------------------------------
create table if not exists app.integration (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references app.tenant(id) on delete cascade,
  provider      text not null check (provider in ('secullum','domain','evolution','whatsapp_cloud','smtp','spreadsheet')),
  alias       text,
  config        jsonb not null default '{}'::jsonb,   -- base_url, company_id, timezone... nunca segredo
  active         boolean not null default false,
  created_at     timestamptz not null default now(),
  unique (tenant_id, provider, alias)
);

create table if not exists app.integration_secret (
  integration_id uuid not null references app.integration(id) on delete cascade,
  key         text not null,          -- 'token', 'client_secret', 'api_key'
  vault_id      uuid not null,          -- referência a vault.secrets
  updated_at timestamptz not null default now(),
  primary key (integration_id, key)
);
comment on table app.integration_secret is
  'Só o ponteiro. O valor está no Vault. Nenhum role do painel lê esta tabela — nem owner.';

create table if not exists app.sync_run (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null references app.tenant(id) on delete cascade,
  integration_id      uuid not null references app.integration(id) on delete cascade,
  entity           text not null,      -- 'Funcionario', 'Batida', 'payroll_entry'...
  started_at        timestamptz not null default now(),
  finished_at       timestamptz,
  status             text not null default 'running' check (status in ('running','completed','failed','partial')),
  cursor_until         timestamptz,        -- incremental: de onde retomar
  records_read    integer not null default 0,
  records_written integer not null default 0,
  error               text
);
create index if not exists sync_run_idx on app.sync_run (integration_id, entity, started_at desc);
create index if not exists sync_run_falha_idx on app.sync_run (tenant_id, started_at desc) where status = 'failed';

-- ---------------------------------------------------------------------------
-- Importação de planilhas (fallback quando não há API — caminho is_primary do Domínio)
-- ---------------------------------------------------------------------------
create table if not exists app.file_import (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references app.tenant(id) on delete cascade,
  type           text not null check (type in ('folha','payroll_charge','employee','cost_center','roster','benefit','other')),
  payroll_period_id uuid references app.payroll_period(id) on delete set null,
  storage_path   text not null,
  file_name   text,
  layout_version  text,
  uploaded_by    uuid references auth.users(id),
  status         text not null default 'received' check (status in ('received','validating','validation_error','processed','discarded')),
  rows_total   integer,
  rows_ok      integer,
  rows_error    integer,
  report      jsonb,       -- erros por linha, para devolver ao usuário
  created_at      timestamptz not null default now()
);
create index if not exists importacao_tenant_idx on app.file_import (tenant_id, created_at desc);

alter table app.payroll_entry
  drop constraint if exists payroll_entry_importacao_fk,
  add  constraint payroll_entry_importacao_fk
       foreign key (import_id) references app.file_import(id) on delete set null;

-- ---------------------------------------------------------------------------
-- Auditoria
-- ---------------------------------------------------------------------------
create table if not exists app.audit_log (
  id           bigint generated always as identity primary key,
  tenant_id    uuid references app.tenant(id) on delete set null,
  user_id      uuid references auth.users(id) on delete set null,
  action         text not null check (action in ('insert','update','delete','login','export','sensitive_query')),
  entity     text not null,
  entity_id  text,
  antes        jsonb,
  depois       jsonb,
  ip           inet,
  user_agent   text,
  created_at    timestamptz not null default now()
);
create index if not exists audit_log_tenant_idx   on app.audit_log (tenant_id, created_at desc);
create index if not exists audit_log_entidade_idx on app.audit_log (entity, entity_id);
comment on table app.audit_log is
  'Cresce rápido. Quando passar de ~50M linhas, particionar por mês (created_at) e mover partição antiga para armazenamento frio.';

create table if not exists app.ai_query (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null references app.tenant(id) on delete cascade,
  user_id            uuid references auth.users(id) on delete set null,
  question           text not null,
  metric_code     text,
  parameters         jsonb,
  rows_returned  integer,
  latency_ms        integer,
  input_tokens     integer,
  output_tokens       integer,
  refused           boolean not null default false,
  refusal_reason      text,
  created_at          timestamptz not null default now()
);
create index if not exists ai_query_tenant_idx on app.ai_query (tenant_id, created_at desc);
comment on column app.ai_query.output_tokens is
  'Custo de LLM é variável e sai da sustentação mensal. Sem medir, não dá para saber se a margem virou negativa.';

-- ---------------------------------------------------------------------------
-- Camada semântica — o catálogo fechado que o assistente pode usar
-- ---------------------------------------------------------------------------
create table if not exists app.metric (
  code         text primary key,
  title         text not null,
  description      text not null,
  target_view      text not null,           -- view em `public`, jamais tabela
  dimensions      text[] not null default '{}',
  filters        text[] not null default '{}',
  domain        app.sensitive_domain,    -- null = não sensível
  active          boolean not null default true
);
comment on table app.metric is
  'Catálogo fechado do assistente de IA. Métrica ausente daqui = question que ele responde "não tenho esse dado", em vez de inventar.';

insert into app.metric (code, title, description, target_view, dimensions, filters, domain) values
  ('deviations_total',        'Total de desvios no período',        'Contagem de ocorrências ativas',                  'vw_deviation_event',           array['unit','company','employee','type'], array['start_date','end_date'], null),
  ('deviations_minutes',      'Minutos de desvio acumulados',       'Soma de minutes, com sinal',                      'vw_deviation_event',           array['unit','company','employee','type'], array['start_date','end_date'], null),
  ('ranking_by_unit',      'Ranking de desvios por unidade',  'Unidades ordenadas por ocorrências',              'vw_deviation_summary_by_unit',   array['unit'],                                array['start_date','end_date'], null),
  ('ranking_by_employee',  'Ranking de desvios por colaborador', 'Colaboradores ordenados por ocorrências',      'fn_ranking_by_employee', array['employee','unit'],               array['start_date','end_date'], null),
  ('daily_trend',     'Tendência diária de desvios',        'Série temporal por dia',                          'vw_deviation_daily_trend', array['unit'],                                array['start_date','end_date'], null),
  ('recurrence',          'Colaboradores recorrentes',          'Desvio em 3 ou mais dias na janela',              'vw_desvio_recorrencia',      array['employee','unit'],                  array['start_date','end_date'], null),
  ('documents_expiring',  'Documentos a vencer',                'Documentos ativos com validade próxima',          'vw_document_expiry',    array['employee','unit','type'],           array['days_ahead'],             'pii'),
  ('payroll_summary',         'Resumo da folha por competência',    'Valor total, por empresa e unidade',           'vw_payroll_summary',            array['company','unit','payroll_period'],        array['year','month'],              'compensation')
on conflict (code) do nothing;

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['integration','integration_secret','sync_run','file_import','audit_log','ai_query','metric'] loop
    execute format('alter table app.%I enable row level security', t);
    execute format('revoke all on table app.%I from anon', t);
  end loop;
end $$;

drop policy if exists integration_admin on app.integration;
create policy integration_admin on app.integration
  for all to authenticated using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

-- integration_secret: sem policy. Nenhuma linha passa para authenticated.
-- Só service_role (que bypassa RLS) enxerga. Intencional.
revoke all on app.integration_secret from authenticated;
grant  all on app.integration_secret to service_role;

drop policy if exists sync_read on app.sync_run;
create policy sync_read on app.sync_run
  for select to authenticated using (util.is_admin(tenant_id));

drop policy if exists importacao_read on app.file_import;
create policy importacao_read on app.file_import
  for select to authenticated using (util.is_admin(tenant_id));

drop policy if exists importacao_write on app.file_import;
create policy importacao_write on app.file_import
  for insert to authenticated with check (util.is_admin(tenant_id));

drop policy if exists audit_read on app.audit_log;
create policy audit_read on app.audit_log
  for select to authenticated using (util.is_admin(tenant_id));
-- Sem policy de insert/update/delete: log é imutável para o painel. Só service_role grava.

drop policy if exists ai_query_read on app.ai_query;
create policy ai_query_read on app.ai_query
  for select to authenticated
  using (user_id = (select auth.uid()) or util.is_admin(tenant_id));

drop policy if exists metric_read on app.metric;
create policy metric_read on app.metric
  for select to authenticated using (active);

grant select on app.integration, app.sync_run, app.file_import,
                app.audit_log, app.ai_query, app.metric to authenticated;
grant insert, update, delete on app.integration to authenticated;
grant insert on app.file_import to authenticated;
