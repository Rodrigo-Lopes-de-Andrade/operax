-- ==========================================================================
-- Schema do projeto Supabase nklobmlxyidqxarzisph, reconstruído do catálogo.
-- GERADO por scripts/introspeccao_nuvem.py — não editar à mão.
--
-- Só catálogo foi lido: nenhuma linha de dado de cliente entrou aqui.
-- Não é backup. É o mapa contra o qual o schema deste repositório é conferido.
-- ==========================================================================

-- Histórico de migration aplicado neste projeto:
--   20260811120000  init_sync_cursor
--   20260812130000  cadastro_sync_schema
--   20260812131000  sync_cadastro_cron
--   20260812140000  fix_work_schedule_day_horario_dia_id_uniqueness
--   20260813120000  status_history_company_employee
--   20260813150000  employee_absence
--   20260813160000  rename_schema_secullum
--   20260813161000  cadastro_captura_completa
--   20260813162000  horario_arvore_completa
--   20260813163000  batidas
--   20260813164000  sync_batidas_cron
--   20260815100000  00_blindagem_imediata
--   20260815100100  01_fundacao_schemas
--   20260815100200  02_tenancy_rls
--   20260815100300  03_isolar_secullum
--   20260815100400  04_organizacao_colaborador
--   20260815100500  05_ponto_desvio
--   20260815100600  06_alertas
--   20260815100700  07_folha_custos
--   20260815100800  08_documentos_saude_acordos
--   20260815100900  09_integracoes_auditoria
--   20260815101000  10_views_publicas
--   20260815101100  11_performance
--   20260815101150  
--   20260815101200  
--   20260815101300  
--   20260815101400  
--   20260822160000  
--   20260824140000  
--   20260824170000  
--   20260824190000  
--   20260825120000  
--   20260825140000  
--   20260825160000  
--   20260825180000  
--   20260825200000  
--   20260825220000  
--   20260826120000  
--   20260826140000  
--   20260826160000  
--   20260827180000  
--   20260828120000  
--   20260828160000  
--   20260828180000  
--   20260828200000  
--   20260831230000  33_ingestion_touch_trigger
--   20260902083000  34_sync_run_overlap_lock
--   20260902200000  35_freshness_foto

create schema if not exists app;
create schema if not exists secullum;
create schema if not exists util;
create schema if not exists public;

create type app.sensitive_domain as enum ('pii', 'compensation', 'health', 'disciplinary');
create type app.user_role as enum ('owner', 'executive', 'hr', 'personnel', 'regional_manager', 'unit_supervisor', 'operations_manager', 'accounting', 'viewer');

create table if not exists app.agreement_installment (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  agreement_id uuid not null,
  number integer not null,
  period_year smallint not null,
  period_month smallint not null,
  amount numeric(14,2) not null,
  status text default 'pending'::text not null,
  payroll_entry_id uuid,
  processed_at timestamp with time zone
);
alter table app.agreement_installment enable row level security;
comment on table app.agreement_installment is 'Parcela pendente cuja competência já passou = alerta de "parcela não processada" (item 9 da proposta).';

create table if not exists app.ai_query (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  user_id uuid,
  question text not null,
  metric_code text,
  parameters jsonb,
  rows_returned integer,
  latency_ms integer,
  input_tokens integer,
  output_tokens integer,
  refused boolean default false not null,
  refusal_reason text,
  created_at timestamp with time zone default now() not null,
  model text
);
alter table app.ai_query enable row level security;

create table if not exists app.alert_queue (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  rule_id uuid,
  deviation_event_id uuid,
  report_cycle_id uuid,
  channel text not null,
  destination text not null,
  payload jsonb not null,
  idempotency_key text not null,
  status text default 'pending'::text not null,
  attempts integer default 0 not null,
  next_attempt_at timestamp with time zone default now() not null,
  scheduled_for timestamp with time zone default now() not null,
  created_at timestamp with time zone default now() not null,
  template_code text,
  provider text
);
alter table app.alert_queue enable row level security;

create table if not exists app.alert_rule (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  name text not null,
  deviation_type text,
  scope_unit_id uuid,
  content text default 'aggregate'::text not null,
  channel text not null,
  cron_window text,
  threshold_minutes integer,
  threshold_occurrences integer,
  muted_until timestamp with time zone,
  active boolean default false not null,
  created_at timestamp with time zone default now() not null,
  template_code text
);
alter table app.alert_rule enable row level security;

create table if not exists app.alert_rule_target (
  id uuid default gen_random_uuid() not null,
  rule_id uuid not null,
  contact_id uuid,
  responsibility text
);
alter table app.alert_rule_target enable row level security;

create table if not exists app.alert_sent (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  queue_id uuid,
  rule_id uuid,
  channel text not null,
  provider text not null,
  destination_hash text not null,
  provider_message_id text,
  status text not null,
  error text,
  cost_cents integer,
  sent_at timestamp with time zone default now() not null
);
alter table app.alert_sent enable row level security;

create table if not exists app.audit_log (
  id bigint generated always as identity not null,
  tenant_id uuid,
  user_id uuid,
  action text not null,
  entity text not null,
  entity_id text,
  antes jsonb,
  depois jsonb,
  ip inet,
  user_agent text,
  created_at timestamp with time zone default now() not null
);
alter table app.audit_log enable row level security;
comment on table app.audit_log is 'Cresce rápido. Quando passar de ~50M linhas, particionar por mês (criado_em) e mover partição antiga para armazenamento frio.';

create table if not exists app.batida_marcacao (
  id uuid default gen_random_uuid() not null,
  batida_id uuid not null,
  funcionario_id uuid not null,
  data date not null,
  tipo_coluna text not null,
  indice_coluna smallint not null,
  valor_bruto text,
  hora time without time zone,
  status_rotulo text,
  "Memoria" time without time zone,
  "EquipId" integer,
  "FonteDadosId" bigint,
  desconsiderada boolean default false not null,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid
);
alter table app.batida_marcacao enable row level security;
comment on table app.batida_marcacao is 'TABELA NOSSA (minusculo, ADR-012): e a TRANSPOSICAO de uma coluna do registro-dia (Entrada1..Entrada5 / Saida1..Saida5) em linha. ⛔ NAO procure "Marcacao" no payload do Secullum — nao existe. Identidade POSICIONAL: (batida_id, tipo_coluna, indice_coluna) — nunca por FonteDadosId, que e nullable e portanto nao e chave (ADR-007). ⚠️ Escrita OBRIGATORIA por substituicao do dia inteiro em transacao: upsert das colunas presentes + DELETE das que deixaram de existir. Sem o DELETE, uma batida removida no Secullum sobrevive para sempre no cache e continua gerando desvio.';

create table if not exists app.company (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  cnpj text,
  legal_name text not null,
  trade_name text,
  secullum_company_id bigint,
  active boolean default true not null,
  created_at timestamp with time zone default now() not null
);
alter table app.company enable row level security;

create table if not exists app.contact (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  name text not null,
  whatsapp text,
  email text,
  type text default 'person'::text not null,
  active boolean default true not null,
  created_at timestamp with time zone default now() not null
);
alter table app.contact enable row level security;

create table if not exists app.cost_center (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  company_id uuid,
  unit_id uuid,
  code text not null,
  name text not null
);
alter table app.cost_center enable row level security;

create table if not exists app.cursor_sincronizacao (
  chave text not null,
  valor text,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid
);
alter table app.cursor_sincronizacao enable row level security;
comment on table app.cursor_sincronizacao is 'Controle de sincronizacao com o Secullum. TABELA 100% NOSSA — nao tem equivalente no Secullum, por isso nome e colunas em minusculo (regra do caso, ADR-012). Ver docs/04-modelo-dados.md.';

create table if not exists app.department (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  company_id uuid not null,
  name text not null,
  secullum_department_id bigint,
  active boolean default true not null
);
alter table app.department enable row level security;

create table if not exists app.detection_run (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  mode text not null,
  period_start date not null,
  period_end date not null,
  started_at timestamp with time zone default now() not null,
  finished_at timestamp with time zone,
  status text default 'running'::text not null,
  events_detected integer default 0 not null,
  events_published integer default 0 not null,
  engine_version text,
  error text,
  scope text default 'incremental'::text not null
);
alter table app.detection_run enable row level security;

create table if not exists app.deviation_event (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  employee_id uuid not null,
  company_id uuid not null,
  unit_id uuid,
  reference_date date not null,
  type text not null,
  minutes integer default 0 not null,
  expected_time time without time zone,
  actual_time time without time zone,
  punch_ids int8[] default '{}'::bigint[] not null,
  status text default 'active'::text not null,
  supersede_id uuid,
  status_reason text,
  mode text default 'production'::text not null,
  run_id uuid,
  report_cycle_id uuid,
  detected_at timestamp with time zone default now() not null,
  updated_at timestamp with time zone default now() not null
);
alter table app.deviation_event enable row level security;

create table if not exists app.deviation_type (
  code text not null,
  description text not null,
  direction text not null,
  category text not null
);
alter table app.deviation_type enable row level security;

create table if not exists app.deviation_type_config (
  tenant_id uuid not null,
  code text not null,
  active boolean default true not null,
  counts_as_deviation boolean default true not null,
  triggers_alert boolean default false not null,
  tolerance_extra_minutes integer,
  tolerance_absence_minutes integer,
  requires_justification boolean default false not null
);
alter table app.deviation_type_config enable row level security;
comment on table app.deviation_type_config is 'Onde a decisão "direção do desvio contabilizada" vive. Cliente diferente, política diferente, mesmo schema.';

create table if not exists app.disciplinary_event (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  employee_id uuid not null,
  type text not null,
  occurred_on date not null,
  days integer,
  summary text,
  document_id uuid,
  acknowledged_on date,
  created_by uuid,
  created_at timestamp with time zone default now() not null
);
alter table app.disciplinary_event enable row level security;
comment on table app.disciplinary_event is 'Advertência, suspensão e anotação administrativa. Domínio sensível `disciplinary`: ver a unidade não basta e ser gestor dela não basta. Sem delete para o painel — registro aplicado por engano se corrige por update, com trilha, nunca por apagamento.';

create table if not exists app.document (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  employee_id uuid not null,
  type_id uuid not null,
  storage_bucket text default 'documentos'::text not null,
  storage_path text not null,
  file_name text,
  issued_on date,
  valid_until date,
  status text default 'active'::text not null,
  replaces_id uuid,
  created_by uuid,
  created_at timestamp with time zone default now() not null
);
alter table app.document enable row level security;
comment on table app.document is 'O arquivo vive no Supabase Storage. A policy do bucket precisa espelhar util.pode_ver_colaborador — RLS de tabela não protege o objeto.';

create table if not exists app.document_type (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  name text not null,
  requires_expiry boolean default false not null,
  expiry_alert_days integer default 30 not null,
  required boolean default false not null,
  domain app.sensitive_domain default 'pii'::app.sensitive_domain not null
);
alter table app.document_type enable row level security;

create table if not exists app.domain_permission (
  tenant_id uuid not null,
  role app.user_role not null,
  domain app.sensitive_domain not null,
  allowed boolean default false not null
);
alter table app.domain_permission enable row level security;
comment on table app.domain_permission is 'Salário, RG, ASO e ocorrência disciplinar são decisão de dado, não de código.';

create table if not exists app.employee (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  company_id uuid not null,
  unit_id uuid,
  department_id uuid,
  secullum_employee_id bigint,
  registration_number text,
  name text not null,
  cargo text,
  employment_type text,
  hired_on date,
  terminated_on date,
  manager_employee_id uuid,
  status text default 'active'::text not null,
  created_at timestamp with time zone default now() not null,
  updated_at timestamp with time zone default now() not null,
  hr_code text,
  exception_tracking boolean default false not null,
  manager_id uuid
);
alter table app.employee enable row level security;

create table if not exists app.employee_compensation (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  employee_id uuid not null,
  effective_from date not null,
  effective_to date,
  salary numeric(14,2) not null,
  reason text,
  recorded_by uuid,
  created_at timestamp with time zone default now() not null
);
alter table app.employee_compensation enable row level security;

create table if not exists app.employee_pii (
  employee_id uuid not null,
  tenant_id uuid not null,
  cpf text,
  rg text,
  pis text,
  ctps text,
  birth_date date,
  mother_name text,
  father_name text,
  phone text,
  personal_email text,
  address jsonb,
  updated_at timestamp with time zone default now() not null
);
alter table app.employee_pii enable row level security;
comment on table app.employee_pii is 'Dado pessoal direto. Acesso exige util.pode_ver_dominio(tenant, ''pii''). Nunca entra em view de dashboard.';

create table if not exists app.employee_position (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  employee_id uuid not null,
  effective_from date not null,
  effective_to date,
  cargo text not null,
  unit_id uuid,
  created_at timestamp with time zone default now() not null
);
alter table app.employee_position enable row level security;

create table if not exists app.empresa_evento_status (
  id uuid default gen_random_uuid() not null,
  empresa_id uuid not null,
  tipo_evento text not null,
  ativo_anterior boolean,
  ativo_novo boolean not null,
  detectado_em timestamp with time zone default now() not null,
  origem text default 'secullum_sync'::text not null,
  criado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid
);
alter table app.empresa_evento_status enable row level security;
comment on table app.empresa_evento_status is 'TABELA 100% NOSSA (por isso tudo em minusculo) — historico APPEND-ONLY de mudancas de "Empresa".ativo. ⚠️⚠️ NAO EXISTE DATA REAL DE EVENTO AQUI: o Secullum entrega apenas `Empresa.Desativada` (boolean de estado atual). A unica data e detectado_em (quando a sincronizacao percebeu) e a ausencia de uma coluna de data de evento e PROPOSITAL. Contraste obrigatorio com funcionario_evento_status, que TEM data real. Ver ADR-009.';

create table if not exists app.expected_workday (
  tenant_id uuid not null,
  employee_id uuid not null,
  reference_date date not null,
  day_type text not null,
  expected_entry time without time zone,
  expected_exit time without time zone,
  expected_break_minutes integer,
  workload_minutes integer,
  tolerance_extra_minutes integer default 0 not null,
  tolerance_absence_minutes integer default 0 not null,
  secullum_schedule_id bigint,
  source text not null,
  confidence smallint default 100 not null
);
alter table app.expected_workday enable row level security;

create table if not exists app.file_import (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  type text not null,
  payroll_period_id uuid,
  storage_path text not null,
  file_name text,
  layout_version text,
  uploaded_by uuid,
  status text default 'received'::text not null,
  rows_total integer,
  rows_ok integer,
  rows_error integer,
  report jsonb,
  created_at timestamp with time zone default now() not null
);
alter table app.file_import enable row level security;

create table if not exists app.financial_agreement (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  employee_id uuid not null,
  type text not null,
  description text,
  total_amount numeric(14,2) not null,
  installment_count integer default 1 not null,
  agreement_date date not null,
  document_id uuid not null,
  authorized_by uuid not null,
  authorized_at timestamp with time zone default now() not null,
  status text default 'active'::text not null,
  created_at timestamp with time zone default now() not null
);
alter table app.financial_agreement enable row level security;

create table if not exists app.financial_threshold (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  company_id uuid,
  unit_id uuid,
  indicator text not null,
  operator text not null,
  amount numeric(14,2) not null,
  active boolean default true not null
);
alter table app.financial_threshold enable row level security;

create table if not exists app.funcionario_evento_status (
  id uuid default gen_random_uuid() not null,
  funcionario_id uuid not null,
  tipo_evento text not null,
  ativo_anterior boolean,
  ativo_novo boolean not null,
  data_evento date,
  admissao_anterior date,
  admissao_nova date,
  demissao_anterior date,
  demissao_nova date,
  detectado_em timestamp with time zone default now() not null,
  origem text default 'secullum_sync'::text not null,
  criado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid
);
alter table app.funcionario_evento_status enable row level security;
comment on table app.funcionario_evento_status is 'TABELA 100% NOSSA (minusculo) — historico APPEND-ONLY de mudancas de vinculo ("Funcionario".ativo). ✅ AQUI EXISTE data real de evento (data_evento, de `Admissao`/`Demissao`). data_evento e detectado_em divergem legitimamente. Ver ADR-009 e docs/04-modelo-dados.md.';

create table if not exists app.integration (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  provider text not null,
  alias text,
  config jsonb default '{}'::jsonb not null,
  active boolean default false not null,
  created_at timestamp with time zone default now() not null
);
alter table app.integration enable row level security;

create table if not exists app.integration_secret (
  integration_id uuid not null,
  key text not null,
  vault_id uuid not null,
  updated_at timestamp with time zone default now() not null
);
alter table app.integration_secret enable row level security;
comment on table app.integration_secret is 'Só o ponteiro. O valor está no Vault. Nenhum papel do painel lê esta tabela — nem owner.';

create table if not exists app.job_execucao (
  id uuid default gen_random_uuid() not null,
  job text not null,
  iniciado_em timestamp with time zone default now() not null,
  finalizado_em timestamp with time zone,
  status text not null,
  resumo jsonb,
  erro text,
  host text
);
alter table app.job_execucao enable row level security;
comment on table app.job_execucao is 'Observabilidade durável + lock de sobreposição dos jobs agendados (ADR-016 §3.3/§3.7). Único índice único parcial (job_execucao_em_andamento_key) é o lock.';

create table if not exists app.justification (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  deviation_event_id uuid,
  employee_id uuid not null,
  reference_date date not null,
  text text not null,
  source text default 'operax'::text not null,
  author_user_id uuid,
  author_name text,
  created_at timestamp with time zone default now() not null,
  status text default 'accepted'::text not null
);
alter table app.justification enable row level security;

create table if not exists app.leave_period (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  employee_id uuid not null,
  category text not null,
  start_date date not null,
  end_date date,
  source text default 'secullum'::text not null,
  created_at timestamp with time zone default now() not null
);
alter table app.leave_period enable row level security;
comment on table app.leave_period is 'Rótulo neutro por decisão de produto. Motivo de afastamento é dado de saúde e não é capturado.';

create table if not exists app.manager (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  secullum_structure_id bigint not null,
  name text not null,
  active boolean default true not null,
  created_at timestamp with time zone default now() not null,
  updated_at timestamp with time zone default now() not null
);
alter table app.manager enable row level security;
comment on table app.manager is 'O gestor como o espelho o declara: `secullum."Estrutura"`, alcançada por `Funcionario.EstruturaId`. É dimensão de agregação, NÃO vínculo com um registro de colaborador — resolver qual colaborador é este gestor exigiria casar nome, e a medição de 26/08 mostrou que o casamento falha nas quatro estruturas de produção.';

create table if not exists app.message_template (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  code text not null,
  category text default 'utility'::text not null,
  language text default 'pt_BR'::text not null,
  variables text[] not null,
  body text not null,
  meta_template_name text,
  meta_status text default 'draft'::text not null,
  meta_rejection text,
  active boolean default true not null,
  created_at timestamp with time zone default now() not null,
  updated_at timestamp with time zone default now() not null
);
alter table app.message_template enable row level security;
comment on table app.message_template is 'Contrato único das três integrações de WhatsApp. `variables` é a ordem dos placeholders do template da Meta E o conjunto de chaves exigido no payload da fila. `body` é o mesmo texto renderizado localmente para os provedores não oficiais, que não têm template.';

create table if not exists app.metric (
  code text not null,
  title text not null,
  description text not null,
  target_view text not null,
  dimensions text[] default '{}'::text[] not null,
  filters text[] default '{}'::text[] not null,
  domain app.sensitive_domain,
  active boolean default true not null
);
alter table app.metric enable row level security;
comment on table app.metric is 'Catálogo fechado do assistente de IA. Métrica ausente daqui = pergunta que ele responde "não tenho esse dado", em vez de inventar. O alvo tem de responder o que o título promete: uma métrica de contagem apontada para uma view de linhas devolve o teto de linhas como se fosse a contagem.';

create table if not exists app.occupational_exam (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  employee_id uuid not null,
  type text not null,
  performed_on date not null,
  valid_until date,
  result text,
  document_id uuid,
  created_by uuid,
  created_at timestamp with time zone default now() not null
);
alter table app.occupational_exam enable row level security;
comment on table app.occupational_exam is 'DADO DE SAÚDE (LGPD art. 5º II). Sem diagnóstico, sem CID, sem descrição de restrição. Só aptidão e validade. Importável pelo template `hr_exam` desde a migration 17, por quem tem o domínio `health`.';

create table if not exists app.payroll_charge (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  payroll_period_id uuid not null,
  company_id uuid not null,
  unit_id uuid,
  type text not null,
  calculation_base numeric(14,2),
  amount numeric(14,2) not null,
  source text not null,
  created_at timestamp with time zone default now() not null
);
alter table app.payroll_charge enable row level security;

create table if not exists app.payroll_entry (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  payroll_period_id uuid not null,
  employee_id uuid,
  company_id uuid not null,
  unit_id uuid,
  cost_center_id uuid,
  code text not null,
  description text,
  nature text not null,
  reference numeric(14,4),
  amount numeric(14,2) not null,
  source text not null,
  import_id uuid,
  created_at timestamp with time zone default now() not null
);
alter table app.payroll_entry enable row level security;
comment on table app.payroll_entry is 'Espelho do que a folha oficial calculou. O OperaX NÃO calcula obrigação trabalhista — item 20 do escopo.';

create table if not exists app.payroll_event_map (
  tenant_id uuid not null,
  code text not null,
  category text not null,
  label text,
  validated_by uuid,
  validated_at timestamp with time zone,
  notes text
);
alter table app.payroll_event_map enable row level security;
comment on table app.payroll_event_map is 'Código de evento da folha do cliente -> categoria do produto. Linha sem validated_at = mapeamento provisório, sinalizar na UI. Sem este mapa, metade do dashboard financeiro não existe — e com ele adivinhado, existe errado.';

create table if not exists app.payroll_period (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  year smallint not null,
  month smallint not null,
  status text default 'aberta'::text not null,
  closed_at timestamp with time zone
);
alter table app.payroll_period enable row level security;

create table if not exists app.report_cycle (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  unit_id uuid,
  period_start date not null,
  period_end date not null,
  generated_at timestamp with time zone default now() not null,
  sent_at timestamp with time zone,
  channel text,
  status text default 'open'::text not null,
  total_events integer default 0 not null
);
alter table app.report_cycle enable row level security;

create table if not exists app.schedule_rotation_map (
  tenant_id uuid not null,
  secullum_schedule_id bigint not null,
  cycle_length_days smallint not null,
  anchor_date date not null,
  expected_entry time without time zone not null,
  expected_exit time without time zone not null,
  expected_break_minutes integer,
  workload_minutes integer not null,
  tolerance_extra_minutes integer default 0 not null,
  tolerance_absence_minutes integer default 0 not null,
  validated_by uuid,
  validated_at timestamp with time zone,
  notes text,
  created_at timestamp with time zone default now() not null
);
alter table app.schedule_rotation_map enable row level security;
comment on table app.schedule_rotation_map is 'Rotação que o "HorarioDia" do Secullum não consegue escrever — 12x36 e afins. Uma linha por horário do espelho, curada com o cliente. Linha SEM validated_at é provisória e o motor de jornada NÃO a lê: rotação errada vira confiança 100 e alerta contra alguém. Vale apenas onde o horário não declara expediente nenhum.';

create table if not exists app.sync_run (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  integration_id uuid not null,
  entity text not null,
  started_at timestamp with time zone default now() not null,
  finished_at timestamp with time zone,
  status text default 'running'::text not null,
  cursor_until timestamp with time zone,
  records_read integer default 0 not null,
  records_written integer default 0 not null,
  error text,
  records_skipped integer default 0 not null,
  scope text default 'incremental'::text not null
);
alter table app.sync_run enable row level security;

create table if not exists app.tenant (
  id uuid default gen_random_uuid() not null,
  slug text not null,
  name text not null,
  active boolean default true not null,
  created_at timestamp with time zone default now() not null
);
alter table app.tenant enable row level security;
comment on table app.tenant is 'Cliente do OperaX. Kastro Park é o primeiro.';

create table if not exists app.tenant_member (
  tenant_id uuid not null,
  user_id uuid not null,
  role app.user_role not null,
  active boolean default true not null,
  created_at timestamp with time zone default now() not null
);
alter table app.tenant_member enable row level security;

create table if not exists app.unit (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  company_id uuid not null,
  code text not null,
  name text not null,
  address text,
  timezone text default 'America/Sao_Paulo'::text not null,
  active boolean default true not null,
  created_at timestamp with time zone default now() not null
);
alter table app.unit enable row level security;

create table if not exists app.unit_responsible (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  unit_id uuid not null,
  contact_id uuid not null,
  responsibility text not null,
  is_primary boolean default false not null
);
alter table app.unit_responsible enable row level security;

create table if not exists app.unit_secullum_map (
  tenant_id uuid not null,
  secullum_department_id bigint not null,
  unit_id uuid not null,
  validated_by uuid,
  validated_at timestamp with time zone,
  notes text
);
alter table app.unit_secullum_map enable row level security;
comment on table app.unit_secullum_map is 'Resolve a divergência Empresa x Departamento do Secullum. Linha sem validado_em = mapeamento provisório, sinalizar na UI.';

create table if not exists app.user_scope (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  user_id uuid not null,
  company_id uuid,
  unit_id uuid,
  created_at timestamp with time zone default now() not null
);
alter table app.user_scope enable row level security;

create table if not exists app.workforce_movement (
  id uuid default gen_random_uuid() not null,
  tenant_id uuid not null,
  employee_id uuid not null,
  company_id uuid not null,
  unit_id uuid,
  type text not null,
  event_date date not null,
  payroll_period_id uuid,
  estimated_cost numeric(14,2),
  notes text,
  created_at timestamp with time zone default now() not null
);
alter table app.workforce_movement enable row level security;

create table if not exists secullum."Batida" (
  id uuid default gen_random_uuid() not null,
  "BatidaId" integer,
  funcionario_id uuid not null,
  "FuncionarioId" integer,
  "Data" date not null,
  "Observacoes" text,
  "Ajuste" text,
  "Abono2" text,
  "Abono3" text,
  "Abono4" text,
  "Compensado" boolean default false not null,
  "AlmocoLivre" boolean default false not null,
  "Neutro" boolean default false not null,
  "NBanco" boolean default false not null,
  "Folga" boolean default false not null,
  "Refeicao" boolean default false not null,
  status_dia_rotulo text,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."Batida" enable row level security;
alter table secullum."Batida" force row level security;
comment on table secullum."Batida" is 'Registro-dia de ponto: UM item de GET /Batidas = um par (funcionario x data) com ate 5 pares Entrada/Saida em COLUNAS. NAO e uma batida individual — essa e batida_marcacao. Ver ADR-007 e ADR-011.';

create table if not exists secullum."BatidaFonteDados" (
  id uuid default gen_random_uuid() not null,
  batida_marcacao_id uuid not null,
  batida_id uuid not null,
  "FonteDadosId" bigint,
  "Nsr" text,
  "Hora" time without time zone,
  "Data" date,
  "DataInclusao" timestamp with time zone,
  "Tipo" smallint,
  "Origem" smallint,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."BatidaFonteDados" enable row level security;
alter table secullum."BatidaFonteDados" force row level security;
comment on table secullum."BatidaFonteDados" is 'Objeto `FonteDados` aninhado em cada coluna de /Batidas — ate 10 por registro-dia (FonteDadosEntrada1..5 / FonteDadosSaida1..5). Nome composto: o prefixo "Batida" e NOSSO (agrupamento na listagem de tabelas); "FonteDados" e o tipo literal do Secullum, e cada linha E um desses objetos. 1:1 OPCIONAL com batida_marcacao: existe coluna preenchida SEM FonteDados (buraco conhecido, ADR-007).';

create table if not exists secullum."Cidade" (
  id uuid default gen_random_uuid() not null,
  "CidadeId" integer,
  "Descricao" text not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."Cidade" enable row level security;
alter table secullum."Cidade" force row level security;
comment on table secullum."Cidade" is 'Cidade — no aninhado { Id, Descricao } em Funcionario e em Empresa. Forma confirmada em 2026-08-13. Ver ADR-011.';

create table if not exists secullum."Departamento" (
  id uuid default gen_random_uuid() not null,
  empresa_id uuid not null,
  "DepartamentoId" integer not null,
  "Descricao" text not null,
  ativo boolean default true not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  "Nfolha" text,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."Departamento" enable row level security;
alter table secullum."Departamento" force row level security;
comment on table secullum."Departamento" is 'Departamento = unidade de estacionamento. Espelha o no `Funcionario.Departamento { Id, Descricao, Nfolha }`; a rota standalone GET /Departamentos NAO e chamada. Ver ADR-006 e ADR-008.';

create table if not exists secullum."Empresa" (
  id uuid default gen_random_uuid() not null,
  "Documento" text not null,
  "Nome" text not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  "EmpresaId" integer,
  "Desativada" boolean,
  "Inscricao" text,
  "Endereco" text,
  "Bairro" text,
  cidade_id uuid,
  "CidadeId" integer,
  "Cep" text,
  "Uf" text,
  "Pais" text,
  "Telefone" text,
  "Fax" text,
  "Cei" text,
  "NfolhaEmpresa" text,
  "Logotipo" text,
  "PossuiLogo" boolean,
  "ResponsavelNome" text,
  "ResponsavelCargo" text,
  "ResponsavelEmail" text,
  "TipoDocumento" smallint,
  "UtilizaRepC" boolean,
  "UtilizaRepA" boolean,
  "UtilizaRepP" boolean,
  "UsaFechamentoDoPontoEspecifico" boolean,
  "FechamentoPonto" smallint,
  "DiaFechamentoPonto" smallint,
  "EmitiuAtestadoTecnico" boolean,
  ativo boolean generated always as (COALESCE((NOT "Desativada"), true)) stored not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."Empresa" enable row level security;
alter table secullum."Empresa" force row level security;
comment on table secullum."Empresa" is 'Empresa (agrupador) — espelha o no `Funcionario.Empresa` aninhado em /Funcionarios. ⚠️ ATENCAO AO ALCANCE REAL DOS CAMPOS: o no aninhado confirmado traz { Id, Nome, Documento, Desativada, ... }. As demais colunas vem do CADASTRO DE EMPRESAS do manual (rota GET /Empresas, que este projeto NAO chama) e podem permanecer NULAS para sempre. Elas existem porque o Owner pediu captura completa (ADR-011); nenhuma delas tem consumidor de produto hoje. Ver ADR-006, ADR-011 e ADR-012.';

create table if not exists secullum."Estrutura" (
  id uuid default gen_random_uuid() not null,
  "EstruturaId" integer not null,
  "EstruturaPaiId" integer,
  "Descricao" text not null,
  email text,
  email_origem text default 'manual'::text not null,
  whatsapp text,
  canais_notificacao text[] default '{}'::text[] not null,
  ativo boolean default true not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."Estrutura" enable row level security;
alter table secullum."Estrutura" force row level security;
comment on table secullum."Estrutura" is '⚠️ LEIA O CABECALHO DA SECAO 6 DE 20260813160000_rename_schema_secullum.sql ANTES DE MEXER AQUI. Esta tabela espelha o OBJETO ANINHADO `Funcionario.Estrutura` de /Funcionarios — NAO a rota standalone GET /Estruturas, que foi DESCARTADA pelo ADR-006 e nao e chamada em nenhum fluxo. Papel de negocio: e o GESTOR responsavel pelo(s) departamento(s); "Descricao" e o NOME dele. Origem hibrida: "Descricao"/"EstruturaPaiId" vem do Secullum; email vem por match de nome dentro do proprio /Funcionarios (com protecao via email_origem); whatsapp e canais_notificacao sao SEMPRE cadastro manual do Owner. ⚠️ NAO confundir com "Empresa"."ResponsavelNome" (responsavel LEGAL da empresa, outra pessoa). Ver docs/03-integracao-secullum.md ("Resolucao do gestor").';

create table if not exists secullum."Funcao" (
  id uuid default gen_random_uuid() not null,
  "FuncaoId" integer,
  "Descricao" text not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."Funcao" enable row level security;
alter table secullum."Funcao" force row level security;
comment on table secullum."Funcao" is 'Funcao/cargo do funcionario. Populada a partir do no aninhado em /Funcionarios — a rota standalone GET /Funcoes NAO e chamada (escopo de 5 endpoints, docs/03-integracao-secullum.md).';

create table if not exists secullum."Funcionario" (
  id uuid default gen_random_uuid() not null,
  departamento_id uuid not null,
  empresa_id uuid not null,
  "FuncionarioId" integer not null,
  "Cpf" text,
  "NumeroPis" text,
  "Nome" text not null,
  horario_id uuid,
  ativo boolean default true not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  "Admissao" date,
  "Demissao" date,
  afastado_hoje boolean default false not null,
  afastamento_atual_id uuid,
  "NumeroFolha" text,
  "NumeroIdentificador" text,
  "NumeroProvisorio" text,
  "Carteira" text,
  "CodigoHolerite" text,
  "Observacao" text,
  "Endereco" text,
  "Bairro" text,
  cidade_id uuid,
  "CidadeId" integer,
  "Uf" text,
  "Cep" text,
  "Telefone" text,
  "Celular" text,
  "Email" text,
  "Rg" text,
  "ExpedicaoRg" date,
  "Ssp" text,
  "Mae" text,
  "Pai" text,
  "Nascimento" date,
  "Masculino" boolean,
  "Nacionalidade" text,
  "Naturalidade" text,
  funcao_id uuid,
  "FuncaoId" integer,
  "EmpresaId" integer,
  "DepartamentoId" integer,
  "HorarioId" integer,
  "EstruturaId" integer,
  "NaoVerificarDigital" boolean,
  "Master" boolean,
  "PossuiFoto" boolean,
  "Invisivel" boolean,
  "PeriodoEncerrado" text,
  "DesconsiderarPerimetrosGlobais" boolean,
  "AceitouTermosLgpdApp" boolean,
  "DataUltimoEnvio" timestamp with time zone,
  "DataUltimoLogin" timestamp with time zone,
  "DataAlteracao" timestamp with time zone,
  "EscolaridadeId" integer,
  "Filtro1Id" integer,
  "Filtro2Id" integer,
  "MotivoDemissaoId" integer,
  "NivelPermissaoId" integer,
  "PerfilId" integer,
  "PerfilFuncionarioId" integer,
  "BancoHorasId" integer,
  "HorarioAlternativo2Id" integer,
  "HorarioAlternativo3Id" integer,
  "HorarioAlternativo4Id" integer,
  "ConfigEspecificaInclusaoManualPonto" boolean,
  "ConfigEspecificaInclusaoManualPontoFusoHorarioId" integer,
  "ConfigEspecificaDesativarVerificacaoLocalFicticio" boolean,
  "ConfigEspecificaInclusaoPontoSemLocalizacao" boolean,
  "ConfigEspecificaInclusaoPontoOffline" boolean,
  "ConfigEspecificaCapturaDeFotoNoMomentoDaInclusao" boolean,
  "BloquearRegistroPontoTeclado" boolean,
  "PermiteInclusaoPontoManual" boolean,
  "PermiteInclusaoDispositivosAutorizados" boolean,
  "DesabilitarAssinaturaEletronica" boolean,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null,
  "Foto" bytea,
  foto_sincronizada_em timestamp with time zone,
  foto_tentativa_em timestamp with time zone,
  foto_hash text,
  foto_bytes integer,
  foto_mime text
);
alter table secullum."Funcionario" enable row level security;
alter table secullum."Funcionario" force row level security;
comment on table secullum."Funcionario" is 'Funcionario. ⚠️ A partir de 2026-08-13 (ADR-011) esta tabela deixou de ser um "cache minimo" e passa a guardar TODO o cadastro devolvido por /Funcionarios, incluindo PII sensivel (RG, endereco, telefone, celular, e-mail, filiacao, nascimento). A minimizacao anterior foi REVERTIDA por decisao expressa do Owner. A base legal formal para essa retencao continua PENDENTE — ver docs/06-seguranca-lgpd.md.';

create table if not exists secullum."FuncionarioAfastamento" (
  id uuid default gen_random_uuid() not null,
  funcionario_id uuid not null,
  "AfastamentoId" integer not null,
  "Inicio" date not null,
  "Fim" date not null,
  "JustificativaNome" text,
  "DataInclusao" timestamp with time zone,
  correlacionado_por text default 'pis'::text not null,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."FuncionarioAfastamento" enable row level security;
alter table secullum."FuncionarioAfastamento" force row level security;
comment on table secullum."FuncionarioAfastamento" is 'Periodos (JANELAS) de afastamento/ferias — fonte: GET /IntegracaoExterna/FuncionariosAfastamentos. Nome escolhido a partir do nome da rota (o manual nao nomeia um tipo para o item) — ver secao 10 da migration 20260813160000. NAO confundir com funcionario_evento_status (transicoes de vinculo): o funcionario continua ativo = true durante ferias. Tabela MUTAVEL (upsert + DELETE de convergencia), ao contrario das tabelas *_evento_status, que sao append-only. Ver ADR-010.';

create table if not exists secullum."FuncionarioCentroCusto" (
  id uuid default gen_random_uuid() not null,
  funcionario_id uuid not null,
  "Descricao" text not null,
  criado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."FuncionarioCentroCusto" enable row level security;
alter table secullum."FuncionarioCentroCusto" force row level security;
comment on table secullum."FuncionarioCentroCusto" is 'Centros de custo do funcionario (`ListaCentroDeCustos`, array de { Descricao } em /Funcionarios). ON DELETE CASCADE sustenta o expurgo por titular (docs/06-seguranca-lgpd.md). Escrita por substituicao integral por funcionario.';

create table if not exists secullum."Horario" (
  id uuid default gen_random_uuid() not null,
  "HorarioId" integer not null,
  "Numero" integer,
  "Descricao" text,
  ativo boolean default true not null,
  sincronizado_em timestamp with time zone,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."Horario" enable row level security;
alter table secullum."Horario" force row level security;
comment on table secullum."Horario" is 'Horario (grade prevista) — espelha `Horario` de GET /Horarios (chamada sem parametro). Ver docs/04-modelo-dados.md.';

create table if not exists secullum."HorarioDescanso" (
  id uuid default gen_random_uuid() not null,
  horario_id uuid not null,
  "HorarioId" integer,
  "Tipo" smallint,
  "ValorDescanso" text,
  "LimiteHorasFaltas" text,
  "IncluirFeriado" smallint,
  "FeriadoDomingoApenasUmDescanso" boolean,
  "DescontarFeriadosCasoFaltas" boolean,
  "NaoDescontarAntesAdmissao" boolean,
  "NaoDescontarDuranteAfastamento" boolean,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioDescanso" enable row level security;
alter table secullum."HorarioDescanso" force row level security;
comment on table secullum."HorarioDescanso" is 'No `Horario.Descanso` (tipo `HorarioDescanso`, regras de DSR) — 1:1 com "Horario". Estrutura bate com o manual (confirmado em 2026-08-13). Regras de folha: capturadas, ⛔ NAO consumidas pelo motor.';

create table if not exists secullum."HorarioDescansoFaixaItem" (
  id uuid default gen_random_uuid() not null,
  horario_descanso_id uuid not null,
  "Ordem" integer,
  "Limite" text,
  "Desconto" text,
  criado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioDescansoFaixaItem" enable row level security;
alter table secullum."HorarioDescansoFaixaItem" force row level security;
comment on table secullum."HorarioDescansoFaixaItem" is 'Itens de `Descanso.Faixas` (tipo `HorarioDescansoFaixaItem`: { Ordem, Limite, Desconto }). SEM chave unica de negocio de proposito: escrita por SUBSTITUICAO INTEGRAL do conjunto por "HorarioDescanso", dentro da transacao do ciclo. Nenhum item tem id estavel na origem.';

create table if not exists secullum."HorarioDia" (
  id uuid default gen_random_uuid() not null,
  horario_id uuid not null,
  "HorarioDiaId" integer not null,
  "DiaSemana" smallint not null,
  "Entrada1" time without time zone,
  "Entrada2" time without time zone,
  "Entrada3" time without time zone,
  "Entrada4" time without time zone,
  "Entrada5" time without time zone,
  "Saida1" time without time zone,
  "Saida2" time without time zone,
  "Saida3" time without time zone,
  "Saida4" time without time zone,
  "Saida5" time without time zone,
  "TipoEntrada1" smallint,
  "TipoEntrada2" smallint,
  "TipoEntrada3" smallint,
  "TipoEntrada4" smallint,
  "TipoEntrada5" smallint,
  "TipoSaida1" smallint,
  "TipoSaida2" smallint,
  "TipoSaida3" smallint,
  "TipoSaida4" smallint,
  "TipoSaida5" smallint,
  "ToleranciaExtra" integer,
  "ToleranciaFalta" integer,
  "Carga" integer,
  "TipoDia" smallint,
  "Neutro" boolean default false not null,
  "Compensado" boolean default false not null,
  "AlmocoLivre" boolean default false not null,
  "Alocar24Horas" boolean default false not null,
  sem_expediente boolean default false not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioDia" enable row level security;
alter table secullum."HorarioDia" force row level security;
comment on table secullum."HorarioDia" is 'Grade por dia da semana. Um registro por item de `Horario.Dias[]`. Nome COMPOSTO por nos (`Horario` + `Dia`): o manual do Secullum nao nomeia um tipo para o item do array.';

create table if not exists secullum."HorarioExtras" (
  id uuid default gen_random_uuid() not null,
  horario_id uuid not null,
  "HorarioId" integer,
  "AgruparExtras" boolean,
  "SomenteGrupoExtras" boolean,
  "DescontarFaltasExtras" smallint,
  "DescontarFaltasExtrasNoturnas" boolean,
  "DescontarIgnorarUteis" boolean,
  "DescontarIgnorarSabados" boolean,
  "DescontarIgnorarDomingos" boolean,
  "DescontarIgnorarFeriados" boolean,
  "DescontarIgnorarFolgas" boolean,
  "DescontarIgnorarDiaEspecial" boolean,
  "UsarInterjornada" boolean,
  "Interjornada" text,
  "InterjornadaSeparada" boolean,
  "InterjornadaSeparadaBancoHoras" boolean,
  "SepararExtrasNoturnasDeExtrasNormais" boolean,
  "SepararExtrasIntervalosDeExtrasNormais" boolean,
  "SepararSomatoriaAposMeiaNoite" boolean,
  "MultiplicarExtrasPeloPercentual" boolean,
  "HabilitarMultiplicadorFaixaBancoHoras" boolean,
  "MultiplicarSomenteSaldoPositivo" boolean,
  "NaoDividirExtrasEmFeriados" boolean,
  "NaoDividirExtrasEmDomingos" boolean,
  "DividirJornadaQuandoHouverFolga" boolean,
  "NaoDividirJornadaEmFeriados" boolean,
  "NaoDividirJornadaEmFolgas" boolean,
  "ApenasDividirJornadaFeriadoFolgaDiaSeguinte" boolean,
  "NaoReiniciarDivisoesExtrasDiurnasNoturnas" boolean,
  "ControleHorasExtrasAutorizadas" boolean,
  "QuantidadeExtrasAutorizadas" text,
  "Acumulo" smallint,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioExtras" enable row level security;
alter table secullum."HorarioExtras" force row level security;
comment on table secullum."HorarioExtras" is 'No `Horario.Extras` (tipo `HorarioExtras`). 1:1 com "Horario". ✅ ESTRUTURA FECHADA em 2026-08-13 contra a conta real: 31 campos incluindo "HorarioId" — nao 7 (manual) nem ~15 (estimativa). Regras de folha, capturadas mas ⛔ NAO usadas pelo motor de deteccao. Ver ADR-011.';

create table if not exists secullum."HorarioFaixasExtras" (
  id uuid default gen_random_uuid() not null,
  horario_id uuid not null,
  "HorarioId" integer,
  "DiaSemana" smallint,
  "Controle" smallint,
  "DiaEspecial" smallint,
  criado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioFaixasExtras" enable row level security;
alter table secullum."HorarioFaixasExtras" force row level security;
comment on table secullum."HorarioFaixasExtras" is 'No `Horario.FaixasExtras` (tipo `HorarioFaixasExtras`) — 1:N por horario, uma linha por "Dia Semana" do enum. Escrita por substituicao integral. Regras de folha: capturadas, ⛔ NAO consumidas pelo motor.';

create table if not exists secullum."HorarioFaixasExtrasItem" (
  id uuid default gen_random_uuid() not null,
  horario_faixas_extras_id uuid not null,
  "Ordem" integer,
  "Horas" double precision,
  "Coluna" double precision,
  criado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioFaixasExtrasItem" enable row level security;
alter table secullum."HorarioFaixasExtrasItem" force row level security;
comment on table secullum."HorarioFaixasExtrasItem" is 'Itens de `FaixasExtras.Faixas` (tipo `HorarioFaixasExtrasItem`). Escrita por substituicao integral junto com o pai. Sem chave unica de negocio — nenhum id estavel na origem.';

create table if not exists secullum."HorarioToleranciaEspecifica" (
  id uuid default gen_random_uuid() not null,
  horario_id uuid not null,
  "UsaToleranciaEspecifica" boolean default false not null,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioToleranciaEspecifica" enable row level security;
alter table secullum."HorarioToleranciaEspecifica" force row level security;
comment on table secullum."HorarioToleranciaEspecifica" is 'No `Horario.ToleranciaEspecifica` (SINGULAR, confirmado no payload real; tipo `HorarioToleranciaEspecifica` no manual) — 1:1 com "Horario". Em todos os registros ja inspecionados veio false / lista vazia: nao ha nenhum caso real ativo neste cliente.';

create table if not exists secullum."HorarioToleranciaEspecificaItem" (
  id uuid default gen_random_uuid() not null,
  horario_tolerancia_especifica_id uuid not null,
  "HorarioId" integer,
  "DiaSemana" smallint,
  "Entrada1De" time without time zone,
  "Entrada1Ate" time without time zone,
  "Saida1De" time without time zone,
  "Saida1Ate" time without time zone,
  "Entrada2De" time without time zone,
  "Entrada2Ate" time without time zone,
  "Saida2De" time without time zone,
  "Saida2Ate" time without time zone,
  "Entrada3De" time without time zone,
  "Entrada3Ate" time without time zone,
  "Saida3De" time without time zone,
  "Saida3Ate" time without time zone,
  "Entrada4De" time without time zone,
  "Entrada4Ate" time without time zone,
  "Saida4De" time without time zone,
  "Saida4Ate" time without time zone,
  "Entrada5De" time without time zone,
  "Entrada5Ate" time without time zone,
  "Saida5De" time without time zone,
  "Saida5Ate" time without time zone,
  criado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioToleranciaEspecificaItem" enable row level security;
alter table secullum."HorarioToleranciaEspecificaItem" force row level security;
comment on table secullum."HorarioToleranciaEspecificaItem" is 'Itens de `ToleranciaEspecifica.Tolerancias` (tipo `HorarioToleranciaEspecificaItem`). Escrita por substituicao integral junto com o pai.';

create table if not exists secullum."HorariosOpcoes" (
  id uuid default gen_random_uuid() not null,
  horario_id uuid not null,
  "HorarioId" integer,
  "ToleranciaArtigo58" boolean,
  "IgnorarLimiteMinimoCasoBatidaGerarExtrasSuperiorATolerancia" boolean,
  "IgnorarLimiteMinimoCasoBatidaGerarFaltasSuperiorATolerancia" boolean,
  "QualquerMinutoAdiantadoComoExtra" boolean,
  "QualquerMinutoAtrasadoComoFalta" boolean,
  "DescontarToleranciaDasHorasExtras" boolean,
  "DescontarToleranciaDasHorasFaltas" boolean,
  "UsarToleranciaRefeicoes" boolean,
  "ToleranciaRefeicoesMinutos" integer,
  "LimiteMinimoDeFaltasNoDiaMinutos" integer,
  "LimiteMinimoDeExtrasNoDiaMinutos" integer,
  "SubstituirBatidasAbaixoDasTolerancias" boolean,
  "AlocarHorario24Horas" boolean,
  "AlocarBatidas" integer,
  "NaoDescontarFaltasDeNormais" boolean,
  "PreencherFaltasQuandoDiaEstiverEmBranco" boolean,
  "TipoPreencherQuandoDiaEstiverEmBranco" integer,
  "CalcularFaltasSomenteParaDiaInteiro" boolean,
  "ExibirColunaHorasRepousoFaltantesTrabalhoContinuo" boolean,
  "HorasRepousoConfiguracaoPadrao" boolean,
  "HorasRepousoFaixas" jsonb,
  "CompletarBatidasFaltantes" boolean,
  "PermitirFolgasAutomaticas" boolean,
  "QuantidadeFolgasAutomaticas" integer,
  "ColunasRefeicao" integer,
  "SinalizarEmVermelhoAlmocosCurtos" boolean,
  "NaoCalcularNenhumaHoraNoturna" boolean,
  "SepararHorasNoturnasDeHorasNormais" boolean,
  "IncluirIntervaloNoAdicionalNoturno" boolean,
  "PeriodoEspecialAdicionalNoturnoInicio" text,
  "PeriodoEspecialAdicionalNoturnoFim" text,
  "ConsiderarFeriadosComoHoraExtra" boolean,
  "UsarTempoMaisMenosCargaSuperior" boolean,
  "PercentualCargaUsarTempoMaisMenosMinutos" double precision,
  "DefinirCargaAutomaticamente" boolean,
  "Carga" double precision,
  "DesconsiderarNeutroQuandoHouverBatidasNoDia" boolean,
  "UsarDataFechamentoEncerrarSemana" boolean,
  "Compensacao" smallint,
  "CompensacaoIgnorarSabados" boolean,
  "CompensacaoIgnorarDomingos" boolean,
  "CompensacaoIgnorarFeriados" boolean,
  "CompensacaoIgnorarFolgas" boolean,
  "CompensacaoMensalFechamento" jsonb,
  "CompensacaoCalcularHorasComoNormaisCompatibilidadePontoOff" boolean,
  "CalcularNoturnasIndependenteCompensado" boolean,
  "CalcularBatidasIntermediarias" boolean,
  "NaoCalcularHorasFaltaBatidasIntermediarias" boolean,
  "ListaHorasSobreAviso" jsonb,
  "CalcularHorasInItinere" boolean,
  "ListaHorasInItinere" jsonb,
  "SomarHorasInItinereNormais" boolean,
  "CalcularHorasInItinereIninterruptas" boolean,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorariosOpcoes" enable row level security;
alter table secullum."HorariosOpcoes" force row level security;
comment on table secullum."HorariosOpcoes" is 'No `Horario.Opcoes` (tipo `HorariosOpcoes` no manual — plural no `Horarios` e literal, nao erro). 1:1 com "Horario". ✅ ESTRUTURA FECHADA em 2026-08-13 contra a conta real (inspecao GET-only, so nomes de campo e tipo, zero valores): 54 campos incluindo "HorarioId" — nao 21 (manual) nem ~35 (estimativa). REGRAS DE CALCULO DE FOLHA: capturadas para consulta/auditoria, ⛔ NAO consumidas pelo motor de deteccao. Ver ADR-011.';

create table if not exists secullum.departamento_gestor (
  id uuid default gen_random_uuid() not null,
  departamento_id uuid not null,
  estrutura_id uuid not null,
  "DepartamentoId" integer not null,
  "EstruturaId" integer not null,
  observado_desde timestamp with time zone default now() not null,
  observado_ate timestamp with time zone,
  funcionarios_observados integer default 0 not null,
  origem text default 'secullum_sync'::text not null,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null
);
alter table secullum.departamento_gestor enable row level security;
comment on table secullum.departamento_gestor is 'Atribuição de gestor ("Estrutura") a unidade ("Departamento") COM VIGÊNCIA (ADR-013). "Estrutura" 1:N "Departamento" (um gestor cobre vários departamentos); cada "Departamento" tem NO MÁXIMO UM gestor vigente a cada instante (índice único parcial abaixo). NÃO é uma junção N:N: o Owner confirmou (2026-08-21) que não existe "unidade com dois gestores simultâneos" — o que existe é substituição temporal (titular afastado -> substituto), registrada como uma nova linha vigente após fechar a anterior.';

create table if not exists secullum.estrutura_evento_titular (
  id uuid default gen_random_uuid() not null,
  estrutura_id uuid not null,
  "EstruturaId" integer not null,
  tipo_evento text not null,
  descricao_anterior text,
  descricao_nova text not null,
  email_anterior text,
  email_novo text,
  funcionario_id_anterior uuid,
  funcionario_id_novo uuid,
  detectado_em timestamp with time zone default now() not null,
  origem text default 'secullum_sync'::text not null,
  criado_em timestamp with time zone default now() not null
);
alter table secullum.estrutura_evento_titular enable row level security;
comment on table secullum.estrutura_evento_titular is 'Histórico APPEND-ONLY de identidade de um nó "Estrutura" (ADR-013, 3º adendo, 2026-08-24). "Estrutura" é a POSIÇÃO (nó do organograma, EstruturaId estável), não a PESSOA: "Descricao"/email contêm o nome/contato de quem ocupa o nó AGORA, e a troca de titular (permanente OU temporária por afastamento — o Secullum não distingue) é sempre uma edição desses campos no MESMO EstruturaId. `departamento_gestor` responde "qual NÓ cobre esta unidade"; esta tabela responde "quem ocupava este nó" — as duas precisam ser compostas para responder "quem respondia pela unidade U em T" (ver ADR-013 §6 do 3º adendo). ⚠️ LIMITAÇÃO NOMEADA (não contornável): uma edição de Descricao NÃO distingue, no payload, "o supervisor mudou de A para B" de "o nó estava rotulado com a pessoa ERRADA e o RH corrigiu" — os dois casos chegam byte a byte idênticos. Esta tabela registra a IDENTIDADE OBSERVADA do nó e quando a sincronização a percebeu, NUNCA "a pessoa mudou nesta data" como fato de negócio certo. `tipo_evento` expõe essa incerteza explicitamente em vez de escondê-la (ver comentário da coluna).';

-- constraints (pk e unique primeiro, depois check, fk por último)
do $$ begin
  alter table app.agreement_installment add constraint agreement_installment_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.ai_query add constraint ai_query_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_queue add constraint alert_queue_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_rule add constraint alert_rule_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_rule_target add constraint alert_rule_target_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_sent add constraint alert_sent_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.audit_log add constraint audit_log_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.batida_marcacao add constraint batida_marcacao_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.company add constraint company_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.contact add constraint contact_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.cost_center add constraint cost_center_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.cursor_sincronizacao add constraint cursor_sincronizacao_pkey PRIMARY KEY (chave);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.department add constraint department_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.detection_run add constraint detection_run_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_event add constraint deviation_event_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_type add constraint deviation_type_pkey PRIMARY KEY (code);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_type_config add constraint deviation_type_config_pkey PRIMARY KEY (tenant_id, code);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.disciplinary_event add constraint disciplinary_event_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.document add constraint document_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.document_type add constraint document_type_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.domain_permission add constraint domain_permission_pkey PRIMARY KEY (tenant_id, role, domain);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee add constraint employee_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee_compensation add constraint employee_compensation_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee_pii add constraint employee_pii_pkey PRIMARY KEY (employee_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee_position add constraint employee_position_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.empresa_evento_status add constraint empresa_evento_status_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.expected_workday add constraint expected_workday_pkey PRIMARY KEY (employee_id, reference_date);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.file_import add constraint file_import_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.financial_agreement add constraint financial_agreement_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.financial_threshold add constraint financial_threshold_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.funcionario_evento_status add constraint funcionario_evento_status_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.integration add constraint integration_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.integration_secret add constraint integration_secret_pkey PRIMARY KEY (integration_id, key);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.job_execucao add constraint job_execucao_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.justification add constraint justification_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.leave_period add constraint leave_period_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.manager add constraint manager_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.message_template add constraint message_template_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.metric add constraint metric_pkey PRIMARY KEY (code);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.occupational_exam add constraint occupational_exam_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_charge add constraint payroll_charge_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_entry add constraint payroll_entry_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_event_map add constraint payroll_event_map_pkey PRIMARY KEY (tenant_id, code);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_period add constraint payroll_period_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.report_cycle add constraint report_cycle_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.schedule_rotation_map add constraint schedule_rotation_map_pkey PRIMARY KEY (tenant_id, secullum_schedule_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.sync_run add constraint sync_run_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.tenant add constraint tenant_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.tenant_member add constraint tenant_member_pkey PRIMARY KEY (tenant_id, user_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.unit add constraint unit_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.unit_responsible add constraint unit_responsible_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.unit_secullum_map add constraint unit_secullum_map_pkey PRIMARY KEY (tenant_id, secullum_department_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.user_scope add constraint user_scope_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.workforce_movement add constraint workforce_movement_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Batida" add constraint "Batida_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."BatidaFonteDados" add constraint "BatidaFonteDados_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Cidade" add constraint "Cidade_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Departamento" add constraint departamento_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Empresa" add constraint empresa_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Estrutura" add constraint estrutura_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcao" add constraint "Funcao_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint funcionario_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioAfastamento" add constraint funcionario_afastamento_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioCentroCusto" add constraint "FuncionarioCentroCusto_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Horario" add constraint horario_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDescanso" add constraint "HorarioDescanso_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDescansoFaixaItem" add constraint "HorarioDescansoFaixaItem_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDia" add constraint horario_dia_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioExtras" add constraint "HorarioExtras_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioFaixasExtras" add constraint "HorarioFaixasExtras_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioFaixasExtrasItem" add constraint "HorarioFaixasExtrasItem_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioToleranciaEspecifica" add constraint "HorarioToleranciaEspecifica_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioToleranciaEspecificaItem" add constraint "HorarioToleranciaEspecificaItem_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorariosOpcoes" add constraint "HorariosOpcoes_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.departamento_gestor add constraint departamento_gestor_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.agreement_installment add constraint agreement_installment_agreement_id_number_key UNIQUE (agreement_id, number);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_queue add constraint alert_queue_idempotency_key_key UNIQUE (idempotency_key);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.batida_marcacao add constraint batida_marcacao_posicao_key UNIQUE (batida_id, tipo_coluna, indice_coluna);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.company add constraint company_tenant_id_cnpj_key UNIQUE (tenant_id, cnpj);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.company add constraint company_tenant_id_secullum_company_id_key UNIQUE (tenant_id, secullum_company_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.cost_center add constraint cost_center_tenant_id_code_key UNIQUE (tenant_id, code);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.department add constraint department_tenant_id_secullum_department_id_key UNIQUE (tenant_id, secullum_department_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.document add constraint document_storage_bucket_storage_path_key UNIQUE (storage_bucket, storage_path);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.document_type add constraint document_type_tenant_id_name_key UNIQUE (tenant_id, name);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee add constraint employee_tenant_id_secullum_employee_id_key UNIQUE (tenant_id, secullum_employee_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.integration add constraint integration_tenant_id_provider_alias_key UNIQUE (tenant_id, provider, alias);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.manager add constraint manager_tenant_id_secullum_structure_id_key UNIQUE (tenant_id, secullum_structure_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.message_template add constraint message_template_tenant_id_code_language_key UNIQUE (tenant_id, code, language);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_period add constraint payroll_period_tenant_id_year_month_key UNIQUE (tenant_id, year, month);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.tenant add constraint tenant_slug_key UNIQUE (slug);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.unit add constraint unit_tenant_id_code_key UNIQUE (tenant_id, code);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.unit_responsible add constraint unit_responsible_unit_id_contact_id_responsibility_key UNIQUE (unit_id, contact_id, responsibility);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Batida" add constraint batida_funcionario_id_data_key UNIQUE (funcionario_id, "Data");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."BatidaFonteDados" add constraint batida_fonte_dados_marcacao_key UNIQUE (batida_marcacao_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Cidade" add constraint cidade_descricao_key UNIQUE ("Descricao");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Departamento" add constraint departamento_departamentoid_key UNIQUE ("DepartamentoId");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Empresa" add constraint empresa_documento_key UNIQUE ("Documento");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Estrutura" add constraint estrutura_estruturaid_key UNIQUE ("EstruturaId");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcao" add constraint funcao_descricao_key UNIQUE ("Descricao");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint funcionario_funcionarioid_key UNIQUE ("FuncionarioId");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioAfastamento" add constraint funcionario_afastamento_funcionario_afastamentoid_key UNIQUE (funcionario_id, "AfastamentoId");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioCentroCusto" add constraint funcionario_centro_custo_key UNIQUE (funcionario_id, "Descricao");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Horario" add constraint horario_horarioid_key UNIQUE ("HorarioId");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDescanso" add constraint horario_descanso_horario_id_key UNIQUE (horario_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDia" add constraint horario_dia_horario_id_diasemana_key UNIQUE (horario_id, "DiaSemana");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioExtras" add constraint horario_extras_horario_id_key UNIQUE (horario_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioToleranciaEspecifica" add constraint horario_tolerancia_especifica_horario_id_key UNIQUE (horario_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorariosOpcoes" add constraint horarios_opcoes_horario_id_key UNIQUE (horario_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.agreement_installment add constraint agreement_installment_amount_check CHECK ((amount > (0)::numeric));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.agreement_installment add constraint agreement_installment_number_check CHECK ((number >= 1));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.agreement_installment add constraint agreement_installment_period_month_check CHECK (((period_month >= 1) AND (period_month <= 13)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.agreement_installment add constraint agreement_installment_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'processed'::text, 'cancelled'::text, 'renegotiated'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_queue add constraint alert_queue_channel_check CHECK ((channel = ANY (ARRAY['whatsapp'::text, 'email'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_queue add constraint alert_queue_provider_check CHECK (((provider IS NULL) OR (provider = ANY (ARRAY['meta_cloud'::text, 'z_api'::text, 'uazapi'::text, 'smtp'::text, 'resend'::text]))));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_queue add constraint alert_queue_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'sending'::text, 'sent'::text, 'failed'::text, 'discarded'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_rule add constraint alert_rule_channel_check CHECK ((channel = ANY (ARRAY['whatsapp'::text, 'email'::text, 'both'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_rule add constraint alert_rule_content_check CHECK ((content = ANY (ARRAY['individual'::text, 'aggregate'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_rule_target add constraint alert_rule_target_check CHECK (((contact_id IS NOT NULL) OR (responsibility IS NOT NULL)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_rule_target add constraint alert_rule_target_responsibility_check CHECK ((responsibility = ANY (ARRAY['unit_manager'::text, 'regional_supervisor'::text, 'personnel'::text, 'hr'::text, 'executive'::text, 'group'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_sent add constraint alert_sent_provider_check CHECK ((provider = ANY (ARRAY['meta_cloud'::text, 'z_api'::text, 'uazapi'::text, 'smtp'::text, 'resend'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_sent add constraint alert_sent_status_check CHECK ((status = ANY (ARRAY['sent'::text, 'delivered'::text, 'read'::text, 'failed'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.audit_log add constraint audit_log_action_check CHECK ((action = ANY (ARRAY['insert'::text, 'update'::text, 'delete'::text, 'login'::text, 'export'::text, 'sensitive_query'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.batida_marcacao add constraint batida_marcacao_indice_coluna_check CHECK (((indice_coluna >= 1) AND (indice_coluna <= 5)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.batida_marcacao add constraint batida_marcacao_tipo_coluna_check CHECK ((tipo_coluna = ANY (ARRAY['Entrada'::text, 'Saida'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.company add constraint company_cnpj_check CHECK ((cnpj ~ '^\d{14}$'::text));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.contact add constraint contact_type_check CHECK ((type = ANY (ARRAY['person'::text, 'whatsapp_group'::text, 'email_list'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.contact add constraint contact_whatsapp_check CHECK ((whatsapp ~ '^\+?\d{10,15}$'::text));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.detection_run add constraint detection_run_mode_check CHECK ((mode = ANY (ARRAY['shadow'::text, 'production'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.detection_run add constraint detection_run_scope_check CHECK ((scope = ANY (ARRAY['incremental'::text, 'backfill'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.detection_run add constraint detection_run_status_check CHECK ((status = ANY (ARRAY['running'::text, 'completed'::text, 'failed'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_event add constraint deviation_event_mode_check CHECK ((mode = ANY (ARRAY['shadow'::text, 'production'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_event add constraint deviation_event_status_check CHECK ((status = ANY (ARRAY['active'::text, 'revoked'::text, 'justified'::text, 'ignored'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_type add constraint deviation_type_category_check CHECK ((category = ANY (ARRAY['entry'::text, 'exit'::text, 'break'::text, 'integrity'::text, 'roster'::text, 'perimeter'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_type add constraint deviation_type_direction_check CHECK ((direction = ANY (ARRAY['surplus'::text, 'shortfall'::text, 'neutral'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.disciplinary_event add constraint disciplinary_days_only_suspension CHECK (((days IS NULL) OR (type = 'suspension'::text)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.disciplinary_event add constraint disciplinary_days_positive CHECK (((days IS NULL) OR (days > 0)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.disciplinary_event add constraint disciplinary_event_type_check CHECK ((type = ANY (ARRAY['verbal_warning'::text, 'written_warning'::text, 'suspension'::text, 'administrative_note'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.document add constraint document_status_check CHECK ((status = ANY (ARRAY['active'::text, 'vencido'::text, 'substituido'::text, 'removido'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee add constraint employee_check CHECK (((terminated_on IS NULL) OR (hired_on IS NULL) OR (terminated_on >= hired_on)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee add constraint employee_employment_type_check CHECK ((employment_type = ANY (ARRAY['clt'::text, 'pj'::text, 'internship'::text, 'temporary'::text, 'apprentice'::text, 'contractor'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee add constraint employee_status_check CHECK ((status = ANY (ARRAY['active'::text, 'afastado'::text, 'vacation'::text, 'desligado'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee_compensation add constraint employee_compensation_check CHECK (((effective_to IS NULL) OR (effective_to >= effective_from)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee_compensation add constraint employee_compensation_salary_check CHECK ((salary >= (0)::numeric));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.empresa_evento_status add constraint empresa_evento_status_baseline_check CHECK (((tipo_evento = 'baseline'::text) = (ativo_anterior IS NULL)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.empresa_evento_status add constraint empresa_evento_status_direcao_check CHECK ((((tipo_evento = 'deactivated'::text) AND (ativo_novo = false)) OR ((tipo_evento = 'reactivated'::text) AND (ativo_novo = true)) OR (tipo_evento = 'baseline'::text)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.empresa_evento_status add constraint empresa_evento_status_mudanca_check CHECK (((tipo_evento = 'baseline'::text) OR (ativo_anterior IS DISTINCT FROM ativo_novo)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.empresa_evento_status add constraint empresa_evento_status_origem_check CHECK ((origem = ANY (ARRAY['secullum_sync'::text, 'backfill'::text, 'manual'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.empresa_evento_status add constraint empresa_evento_status_tipo_evento_check CHECK ((tipo_evento = ANY (ARRAY['baseline'::text, 'deactivated'::text, 'reactivated'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.expected_workday add constraint expected_workday_confidence_check CHECK (((confidence >= 0) AND (confidence <= 100)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.expected_workday add constraint expected_workday_day_type_check CHECK ((day_type = ANY (ARRAY['work'::text, 'day_off'::text, 'vacation'::text, 'leave_period'::text, 'holiday'::text, 'compensated'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.expected_workday add constraint expected_workday_source_check CHECK ((source = ANY (ARRAY['secullum_schedule'::text, 'manual_roster'::text, 'inferred'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.file_import add constraint file_import_status_check CHECK ((status = ANY (ARRAY['received'::text, 'validating'::text, 'validation_error'::text, 'processed'::text, 'discarded'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.file_import add constraint file_import_type_check CHECK ((type = ANY (ARRAY['benefit'::text, 'cost_center'::text, 'employee'::text, 'folha'::text, 'hr_agreement'::text, 'hr_compensation'::text, 'hr_document'::text, 'hr_employee'::text, 'hr_exam'::text, 'hr_leave'::text, 'hr_link'::text, 'hr_movement'::text, 'other'::text, 'payroll_charge'::text, 'roster'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.financial_agreement add constraint financial_agreement_installment_count_check CHECK ((installment_count >= 1));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.financial_agreement add constraint financial_agreement_status_check CHECK ((status = ANY (ARRAY['active'::text, 'settled'::text, 'cancelled'::text, 'suspended'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.financial_agreement add constraint financial_agreement_total_amount_check CHECK ((total_amount > (0)::numeric));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.financial_agreement add constraint financial_agreement_type_check CHECK ((type = ANY (ARRAY['installment_plan'::text, 'vehicle_damage'::text, 'equipment_damage'::text, 'advance'::text, 'loan'::text, 'benefit'::text, 'other'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.financial_threshold add constraint financial_threshold_indicator_check CHECK ((indicator = ANY (ARRAY['total_payroll'::text, 'unit_cost'::text, 'cost_per_employee'::text, 'overtime'::text, 'payroll_charge'::text, 'terminations'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.financial_threshold add constraint financial_threshold_operator_check CHECK ((operator = ANY (ARRAY['greater_than'::text, 'less_than'::text, 'percent_change'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.funcionario_evento_status add constraint funcionario_evento_status_admissao_data_check CHECK (((tipo_evento <> 'admission'::text) OR (NOT (data_evento IS DISTINCT FROM admissao_nova))));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.funcionario_evento_status add constraint funcionario_evento_status_baseline_check CHECK (((tipo_evento = 'baseline'::text) = (ativo_anterior IS NULL)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.funcionario_evento_status add constraint funcionario_evento_status_correcao_check CHECK (((tipo_evento <> 'date_correction'::text) OR (ativo_anterior = ativo_novo)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.funcionario_evento_status add constraint funcionario_evento_status_demissao_data_check CHECK (((tipo_evento <> 'termination'::text) OR (NOT (data_evento IS DISTINCT FROM demissao_nova))));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.funcionario_evento_status add constraint funcionario_evento_status_direcao_check CHECK (((tipo_evento = ANY (ARRAY['baseline'::text, 'date_correction'::text])) OR ((tipo_evento = 'admission'::text) AND (ativo_novo = true)) OR ((tipo_evento = 'termination'::text) AND (ativo_novo = false)) OR ((tipo_evento = 'reactivation'::text) AND (ativo_novo = true))));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.funcionario_evento_status add constraint funcionario_evento_status_mudanca_check CHECK (((tipo_evento = 'baseline'::text) OR (ativo_anterior IS DISTINCT FROM ativo_novo) OR ((tipo_evento = 'date_correction'::text) AND ((admissao_anterior IS DISTINCT FROM admissao_nova) OR (demissao_anterior IS DISTINCT FROM demissao_nova)))));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.funcionario_evento_status add constraint funcionario_evento_status_origem_check CHECK ((origem = ANY (ARRAY['secullum_sync'::text, 'backfill'::text, 'manual'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.funcionario_evento_status add constraint funcionario_evento_status_tipo_evento_check CHECK ((tipo_evento = ANY (ARRAY['baseline'::text, 'admission'::text, 'termination'::text, 'reactivation'::text, 'date_correction'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.integration add constraint integration_provider_check CHECK ((provider = ANY (ARRAY['secullum'::text, 'domain'::text, 'spreadsheet'::text, 'meta_cloud'::text, 'z_api'::text, 'uazapi'::text, 'smtp'::text, 'resend'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.job_execucao add constraint job_execucao_status_check CHECK ((status = ANY (ARRAY['running'::text, 'success'::text, 'error'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.justification add constraint justification_source_check CHECK ((source = ANY (ARRAY['secullum'::text, 'operax'::text, 'whatsapp'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.justification add constraint justification_status_check CHECK ((status = ANY (ARRAY['accepted'::text, 'rejected'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.leave_period add constraint leave_period_category_check CHECK ((category = ANY (ARRAY['vacation'::text, 'leave_period'::text, 'leave_of_absence'::text, 'suspension'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.leave_period add constraint leave_period_check CHECK (((end_date IS NULL) OR (end_date >= start_date)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.leave_period add constraint leave_period_source_check CHECK ((source = ANY (ARRAY['secullum'::text, 'manual'::text, 'spreadsheet'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.message_template add constraint message_template_category_check CHECK ((category = ANY (ARRAY['utility'::text, 'authentication'::text, 'marketing'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.message_template add constraint message_template_meta_status_check CHECK ((meta_status = ANY (ARRAY['draft'::text, 'pending'::text, 'approved'::text, 'rejected'::text, 'paused'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.occupational_exam add constraint occupational_exam_result_check CHECK ((result = ANY (ARRAY['fit'::text, 'unfit'::text, 'fit_with_restriction'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.occupational_exam add constraint occupational_exam_type_check CHECK ((type = ANY (ARRAY['pre_employment'::text, 'periodic'::text, 'exit'::text, 'return_to_work_exam'::text, 'job_change'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_charge add constraint payroll_charge_source_check CHECK ((source = ANY (ARRAY['domain_api'::text, 'spreadsheet'::text, 'file'::text, 'manual'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_charge add constraint payroll_charge_type_check CHECK ((type = ANY (ARRAY['fgts'::text, 'inss_employer'::text, 'inss_withheld'::text, 'irrf'::text, 'rat'::text, 'third_parties'::text, 'vacation_accrual'::text, 'thirteenth_accrual'::text, 'other'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_entry add constraint payroll_entry_nature_check CHECK ((nature = ANY (ARRAY['earning'::text, 'deduction'::text, 'base'::text, 'payroll_charge'::text, 'informational'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_entry add constraint payroll_entry_source_check CHECK ((source = ANY (ARRAY['domain_api'::text, 'spreadsheet'::text, 'file'::text, 'manual'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_event_map add constraint payroll_event_map_category_check CHECK ((category = ANY (ARRAY['base_salary'::text, 'overtime'::text, 'vacation'::text, 'thirteenth'::text, 'termination'::text, 'benefit'::text, 'charge'::text, 'deduction'::text, 'other'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_period add constraint payroll_period_month_check CHECK (((month >= 1) AND (month <= 13)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_period add constraint payroll_period_status_check CHECK ((status = ANY (ARRAY['aberta'::text, 'importada'::text, 'conferida'::text, 'fechada'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_period add constraint payroll_period_year_check CHECK (((year >= 2000) AND (year <= 2100)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.report_cycle add constraint report_cycle_channel_check CHECK ((channel = ANY (ARRAY['whatsapp'::text, 'email'::text, 'both'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.report_cycle add constraint report_cycle_check CHECK ((period_end >= period_start));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.report_cycle add constraint report_cycle_status_check CHECK ((status = ANY (ARRAY['open'::text, 'sent'::text, 'failed'::text, 'cancelled'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.schedule_rotation_map add constraint schedule_rotation_map_cycle_length_days_check CHECK (((cycle_length_days >= 2) AND (cycle_length_days <= 31)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.schedule_rotation_map add constraint schedule_rotation_map_expected_break_minutes_check CHECK ((expected_break_minutes >= 0));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.schedule_rotation_map add constraint schedule_rotation_map_tolerance_absence_minutes_check CHECK ((tolerance_absence_minutes >= 0));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.schedule_rotation_map add constraint schedule_rotation_map_tolerance_extra_minutes_check CHECK ((tolerance_extra_minutes >= 0));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.schedule_rotation_map add constraint schedule_rotation_map_workload_minutes_check CHECK ((workload_minutes > 0));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.sync_run add constraint sync_run_scope_check CHECK ((scope = ANY (ARRAY['incremental'::text, 'backfill'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.sync_run add constraint sync_run_status_check CHECK ((status = ANY (ARRAY['running'::text, 'completed'::text, 'failed'::text, 'partial'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.tenant add constraint tenant_slug_check CHECK ((slug ~ '^[a-z0-9-]{2,40}$'::text));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.unit_responsible add constraint unit_responsible_responsibility_check CHECK ((responsibility = ANY (ARRAY['unit_manager'::text, 'regional_supervisor'::text, 'personnel'::text, 'hr'::text, 'executive'::text, 'group'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.workforce_movement add constraint workforce_movement_type_check CHECK ((type = ANY (ARRAY['hire'::text, 'termination'::text, 'transfer'::text, 'promotion'::text, 'leave_period'::text, 'return_to_work'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Estrutura" add constraint estrutura_canais_notificacao_check CHECK ((canais_notificacao <@ ARRAY['whatsapp'::text, 'email'::text]));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Estrutura" add constraint estrutura_email_origem_check CHECK ((email_origem = ANY (ARRAY['manual'::text, 'secullum'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioAfastamento" add constraint funcionario_afastamento_correlacionado_por_check CHECK ((correlacionado_por = ANY (ARRAY['pis'::text, 'cpf'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDia" add constraint horario_dia_diasemana_check CHECK ((("DiaSemana" >= 0) AND ("DiaSemana" <= 6)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.departamento_gestor add constraint departamento_gestor_intervalo_check CHECK (((observado_ate IS NULL) OR (observado_ate >= observado_desde)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.departamento_gestor add constraint departamento_gestor_origem_check CHECK ((origem = ANY (ARRAY['secullum_sync'::text, 'backfill'::text, 'manual'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_baseline_check CHECK (((tipo_evento <> 'baseline'::text) OR ((descricao_anterior IS NULL) AND (email_anterior IS NULL) AND (funcionario_id_anterior IS NULL))));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_coerencia_check CHECK (
CASE
    WHEN (tipo_evento ~~ 'descricao_alterada%'::text) THEN (descricao_anterior IS DISTINCT FROM descricao_nova)
    WHEN (tipo_evento = 'email_alterado'::text) THEN ((NOT (descricao_anterior IS DISTINCT FROM descricao_nova)) AND (email_anterior IS DISTINCT FROM email_novo))
    ELSE true
END);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_mudanca_check CHECK (((tipo_evento = 'baseline'::text) OR (descricao_anterior IS DISTINCT FROM descricao_nova) OR (email_anterior IS DISTINCT FROM email_novo)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_origem_check CHECK ((origem = ANY (ARRAY['secullum_sync'::text, 'backfill'::text, 'manual'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_outro_funcionario_check CHECK (((tipo_evento <> 'descricao_alterada_outro_funcionario'::text) OR ((funcionario_id_anterior IS NOT NULL) AND (funcionario_id_novo IS NOT NULL) AND (funcionario_id_anterior <> funcionario_id_novo))));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_tipo_evento_check CHECK ((tipo_evento = ANY (ARRAY['baseline'::text, 'descricao_alterada_outro_funcionario'::text, 'descricao_alterada_mesmo_funcionario'::text, 'descricao_alterada_indeterminada'::text, 'email_alterado'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.agreement_installment add constraint agreement_installment_agreement_id_fkey FOREIGN KEY (agreement_id) REFERENCES app.financial_agreement(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.agreement_installment add constraint agreement_installment_payroll_entry_id_fkey FOREIGN KEY (payroll_entry_id) REFERENCES app.payroll_entry(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.agreement_installment add constraint agreement_installment_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.ai_query add constraint ai_query_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.ai_query add constraint ai_query_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_queue add constraint alert_queue_deviation_event_id_fkey FOREIGN KEY (deviation_event_id) REFERENCES app.deviation_event(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_queue add constraint alert_queue_report_cycle_id_fkey FOREIGN KEY (report_cycle_id) REFERENCES app.report_cycle(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_queue add constraint alert_queue_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES app.alert_rule(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_queue add constraint alert_queue_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_rule add constraint alert_rule_deviation_type_fkey FOREIGN KEY (deviation_type) REFERENCES app.deviation_type(code);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_rule add constraint alert_rule_scope_unit_id_fkey FOREIGN KEY (scope_unit_id) REFERENCES app.unit(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_rule add constraint alert_rule_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_rule_target add constraint alert_rule_target_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES app.contact(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_rule_target add constraint alert_rule_target_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES app.alert_rule(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_sent add constraint alert_sent_queue_id_fkey FOREIGN KEY (queue_id) REFERENCES app.alert_queue(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_sent add constraint alert_sent_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES app.alert_rule(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.alert_sent add constraint alert_sent_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.audit_log add constraint audit_log_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.audit_log add constraint audit_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.batida_marcacao add constraint batida_marcacao_batida_id_fkey FOREIGN KEY (batida_id) REFERENCES secullum."Batida"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.batida_marcacao add constraint batida_marcacao_funcionario_id_fkey FOREIGN KEY (funcionario_id) REFERENCES secullum."Funcionario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.batida_marcacao add constraint batida_marcacao_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.company add constraint company_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.contact add constraint contact_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.cost_center add constraint cost_center_company_id_fkey FOREIGN KEY (company_id) REFERENCES app.company(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.cost_center add constraint cost_center_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.cost_center add constraint cost_center_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES app.unit(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.cursor_sincronizacao add constraint cursor_sincronizacao_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.department add constraint department_company_id_fkey FOREIGN KEY (company_id) REFERENCES app.company(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.department add constraint department_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.detection_run add constraint detection_run_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_event add constraint deviation_event_company_id_fkey FOREIGN KEY (company_id) REFERENCES app.company(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_event add constraint deviation_event_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES app.employee(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_event add constraint deviation_event_report_cycle_id_fkey FOREIGN KEY (report_cycle_id) REFERENCES app.report_cycle(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_event add constraint deviation_event_run_id_fkey FOREIGN KEY (run_id) REFERENCES app.detection_run(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_event add constraint deviation_event_supersede_id_fkey FOREIGN KEY (supersede_id) REFERENCES app.deviation_event(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_event add constraint deviation_event_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_event add constraint deviation_event_type_fkey FOREIGN KEY (type) REFERENCES app.deviation_type(code);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_event add constraint deviation_event_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES app.unit(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_type_config add constraint deviation_type_config_code_fkey FOREIGN KEY (code) REFERENCES app.deviation_type(code);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.deviation_type_config add constraint deviation_type_config_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.disciplinary_event add constraint disciplinary_event_created_by_fkey FOREIGN KEY (created_by) REFERENCES auth.users(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.disciplinary_event add constraint disciplinary_event_document_id_fkey FOREIGN KEY (document_id) REFERENCES app.document(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.disciplinary_event add constraint disciplinary_event_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES app.employee(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.disciplinary_event add constraint disciplinary_event_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.document add constraint document_created_by_fkey FOREIGN KEY (created_by) REFERENCES auth.users(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.document add constraint document_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES app.employee(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.document add constraint document_replaces_id_fkey FOREIGN KEY (replaces_id) REFERENCES app.document(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.document add constraint document_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.document add constraint document_type_id_fkey FOREIGN KEY (type_id) REFERENCES app.document_type(id) ON DELETE RESTRICT;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.document_type add constraint document_type_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.domain_permission add constraint domain_permission_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee add constraint employee_company_id_fkey FOREIGN KEY (company_id) REFERENCES app.company(id) ON DELETE RESTRICT;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee add constraint employee_department_id_fkey FOREIGN KEY (department_id) REFERENCES app.department(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee add constraint employee_manager_employee_id_fkey FOREIGN KEY (manager_employee_id) REFERENCES app.employee(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee add constraint employee_manager_id_fkey FOREIGN KEY (manager_id) REFERENCES app.manager(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee add constraint employee_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee add constraint employee_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES app.unit(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee_compensation add constraint employee_compensation_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES app.employee(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee_compensation add constraint employee_compensation_recorded_by_fkey FOREIGN KEY (recorded_by) REFERENCES auth.users(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee_compensation add constraint employee_compensation_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee_pii add constraint employee_pii_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES app.employee(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee_pii add constraint employee_pii_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee_position add constraint employee_position_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES app.employee(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee_position add constraint employee_position_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.employee_position add constraint employee_position_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES app.unit(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.empresa_evento_status add constraint empresa_evento_status_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES secullum."Empresa"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.empresa_evento_status add constraint empresa_evento_status_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.expected_workday add constraint expected_workday_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES app.employee(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.expected_workday add constraint expected_workday_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.file_import add constraint file_import_payroll_period_id_fkey FOREIGN KEY (payroll_period_id) REFERENCES app.payroll_period(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.file_import add constraint file_import_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.file_import add constraint file_import_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES auth.users(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.financial_agreement add constraint financial_agreement_authorized_by_fkey FOREIGN KEY (authorized_by) REFERENCES auth.users(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.financial_agreement add constraint financial_agreement_document_id_fkey FOREIGN KEY (document_id) REFERENCES app.document(id) ON DELETE RESTRICT;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.financial_agreement add constraint financial_agreement_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES app.employee(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.financial_agreement add constraint financial_agreement_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.financial_threshold add constraint financial_threshold_company_id_fkey FOREIGN KEY (company_id) REFERENCES app.company(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.financial_threshold add constraint financial_threshold_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.financial_threshold add constraint financial_threshold_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES app.unit(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.funcionario_evento_status add constraint funcionario_evento_status_funcionario_id_fkey FOREIGN KEY (funcionario_id) REFERENCES secullum."Funcionario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.funcionario_evento_status add constraint funcionario_evento_status_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.integration add constraint integration_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.integration_secret add constraint integration_secret_integration_id_fkey FOREIGN KEY (integration_id) REFERENCES app.integration(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.justification add constraint justification_author_user_id_fkey FOREIGN KEY (author_user_id) REFERENCES auth.users(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.justification add constraint justification_deviation_event_id_fkey FOREIGN KEY (deviation_event_id) REFERENCES app.deviation_event(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.justification add constraint justification_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES app.employee(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.justification add constraint justification_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.leave_period add constraint leave_period_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES app.employee(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.leave_period add constraint leave_period_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.manager add constraint manager_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.message_template add constraint message_template_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.occupational_exam add constraint occupational_exam_created_by_fkey FOREIGN KEY (created_by) REFERENCES auth.users(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.occupational_exam add constraint occupational_exam_document_id_fkey FOREIGN KEY (document_id) REFERENCES app.document(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.occupational_exam add constraint occupational_exam_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES app.employee(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.occupational_exam add constraint occupational_exam_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_charge add constraint payroll_charge_company_id_fkey FOREIGN KEY (company_id) REFERENCES app.company(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_charge add constraint payroll_charge_payroll_period_id_fkey FOREIGN KEY (payroll_period_id) REFERENCES app.payroll_period(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_charge add constraint payroll_charge_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_charge add constraint payroll_charge_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES app.unit(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_entry add constraint payroll_entry_company_id_fkey FOREIGN KEY (company_id) REFERENCES app.company(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_entry add constraint payroll_entry_cost_center_id_fkey FOREIGN KEY (cost_center_id) REFERENCES app.cost_center(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_entry add constraint payroll_entry_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES app.employee(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_entry add constraint payroll_entry_importacao_fk FOREIGN KEY (import_id) REFERENCES app.file_import(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_entry add constraint payroll_entry_payroll_period_id_fkey FOREIGN KEY (payroll_period_id) REFERENCES app.payroll_period(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_entry add constraint payroll_entry_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_entry add constraint payroll_entry_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES app.unit(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_event_map add constraint payroll_event_map_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_event_map add constraint payroll_event_map_validated_by_fkey FOREIGN KEY (validated_by) REFERENCES auth.users(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.payroll_period add constraint payroll_period_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.report_cycle add constraint report_cycle_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.report_cycle add constraint report_cycle_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES app.unit(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.schedule_rotation_map add constraint schedule_rotation_map_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.schedule_rotation_map add constraint schedule_rotation_map_validated_by_fkey FOREIGN KEY (validated_by) REFERENCES auth.users(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.sync_run add constraint sync_run_integration_id_fkey FOREIGN KEY (integration_id) REFERENCES app.integration(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.sync_run add constraint sync_run_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.tenant_member add constraint tenant_member_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.tenant_member add constraint tenant_member_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.unit add constraint unit_company_id_fkey FOREIGN KEY (company_id) REFERENCES app.company(id) ON DELETE RESTRICT;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.unit add constraint unit_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.unit_responsible add constraint unit_responsible_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES app.contact(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.unit_responsible add constraint unit_responsible_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.unit_responsible add constraint unit_responsible_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES app.unit(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.unit_secullum_map add constraint unit_secullum_map_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.unit_secullum_map add constraint unit_secullum_map_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES app.unit(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.unit_secullum_map add constraint unit_secullum_map_validated_by_fkey FOREIGN KEY (validated_by) REFERENCES auth.users(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.user_scope add constraint user_scope_empresa_fk FOREIGN KEY (company_id) REFERENCES app.company(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.user_scope add constraint user_scope_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.user_scope add constraint user_scope_unidade_fk FOREIGN KEY (unit_id) REFERENCES app.unit(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.user_scope add constraint user_scope_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.workforce_movement add constraint workforce_movement_company_id_fkey FOREIGN KEY (company_id) REFERENCES app.company(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.workforce_movement add constraint workforce_movement_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES app.employee(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.workforce_movement add constraint workforce_movement_payroll_period_id_fkey FOREIGN KEY (payroll_period_id) REFERENCES app.payroll_period(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.workforce_movement add constraint workforce_movement_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table app.workforce_movement add constraint workforce_movement_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES app.unit(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Batida" add constraint "Batida_funcionario_id_fkey" FOREIGN KEY (funcionario_id) REFERENCES secullum."Funcionario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Batida" add constraint "Batida_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."BatidaFonteDados" add constraint "BatidaFonteDados_batida_id_fkey" FOREIGN KEY (batida_id) REFERENCES secullum."Batida"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."BatidaFonteDados" add constraint "BatidaFonteDados_batida_marcacao_id_fkey" FOREIGN KEY (batida_marcacao_id) REFERENCES app.batida_marcacao(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."BatidaFonteDados" add constraint "BatidaFonteDados_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Cidade" add constraint "Cidade_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Departamento" add constraint "Departamento_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Departamento" add constraint departamento_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES secullum."Empresa"(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Empresa" add constraint "Empresa_cidade_id_fkey" FOREIGN KEY (cidade_id) REFERENCES secullum."Cidade"(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Empresa" add constraint "Empresa_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Estrutura" add constraint "Estrutura_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcao" add constraint "Funcao_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint "Funcionario_cidade_id_fkey" FOREIGN KEY (cidade_id) REFERENCES secullum."Cidade"(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint "Funcionario_funcao_id_fkey" FOREIGN KEY (funcao_id) REFERENCES secullum."Funcao"(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint "Funcionario_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint funcionario_afastamento_atual_id_fkey FOREIGN KEY (afastamento_atual_id) REFERENCES secullum."FuncionarioAfastamento"(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint funcionario_departamento_id_fkey FOREIGN KEY (departamento_id) REFERENCES secullum."Departamento"(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint funcionario_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES secullum."Empresa"(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint funcionario_horario_id_fkey FOREIGN KEY (horario_id) REFERENCES secullum."Horario"(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioAfastamento" add constraint "FuncionarioAfastamento_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioAfastamento" add constraint funcionario_afastamento_funcionario_id_fkey FOREIGN KEY (funcionario_id) REFERENCES secullum."Funcionario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioCentroCusto" add constraint "FuncionarioCentroCusto_funcionario_id_fkey" FOREIGN KEY (funcionario_id) REFERENCES secullum."Funcionario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioCentroCusto" add constraint "FuncionarioCentroCusto_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Horario" add constraint "Horario_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDescanso" add constraint "HorarioDescanso_horario_id_fkey" FOREIGN KEY (horario_id) REFERENCES secullum."Horario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDescanso" add constraint "HorarioDescanso_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDescansoFaixaItem" add constraint "HorarioDescansoFaixaItem_horario_descanso_id_fkey" FOREIGN KEY (horario_descanso_id) REFERENCES secullum."HorarioDescanso"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDescansoFaixaItem" add constraint "HorarioDescansoFaixaItem_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDia" add constraint "HorarioDia_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDia" add constraint horario_dia_horario_id_fkey FOREIGN KEY (horario_id) REFERENCES secullum."Horario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioExtras" add constraint "HorarioExtras_horario_id_fkey" FOREIGN KEY (horario_id) REFERENCES secullum."Horario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioExtras" add constraint "HorarioExtras_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioFaixasExtras" add constraint "HorarioFaixasExtras_horario_id_fkey" FOREIGN KEY (horario_id) REFERENCES secullum."Horario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioFaixasExtras" add constraint "HorarioFaixasExtras_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioFaixasExtrasItem" add constraint "HorarioFaixasExtrasItem_horario_faixas_extras_id_fkey" FOREIGN KEY (horario_faixas_extras_id) REFERENCES secullum."HorarioFaixasExtras"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioFaixasExtrasItem" add constraint "HorarioFaixasExtrasItem_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioToleranciaEspecifica" add constraint "HorarioToleranciaEspecifica_horario_id_fkey" FOREIGN KEY (horario_id) REFERENCES secullum."Horario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioToleranciaEspecifica" add constraint "HorarioToleranciaEspecifica_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioToleranciaEspecificaItem" add constraint "HorarioToleranciaEspecificaIt_horario_tolerancia_especific_fkey" FOREIGN KEY (horario_tolerancia_especifica_id) REFERENCES secullum."HorarioToleranciaEspecifica"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioToleranciaEspecificaItem" add constraint "HorarioToleranciaEspecificaItem_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorariosOpcoes" add constraint "HorariosOpcoes_horario_id_fkey" FOREIGN KEY (horario_id) REFERENCES secullum."Horario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorariosOpcoes" add constraint "HorariosOpcoes_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.departamento_gestor add constraint departamento_gestor_departamento_id_fkey FOREIGN KEY (departamento_id) REFERENCES secullum."Departamento"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.departamento_gestor add constraint departamento_gestor_estrutura_id_fkey FOREIGN KEY (estrutura_id) REFERENCES secullum."Estrutura"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_estrutura_id_fkey FOREIGN KEY (estrutura_id) REFERENCES secullum."Estrutura"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_funcionario_id_anterior_fkey FOREIGN KEY (funcionario_id_anterior) REFERENCES secullum."Funcionario"(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_funcionario_id_novo_fkey FOREIGN KEY (funcionario_id_novo) REFERENCES secullum."Funcionario"(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;

set check_function_bodies = off;
-- funções
CREATE OR REPLACE FUNCTION app.refresh_dashboard()
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
  refresh materialized view concurrently app.mv_deviation_day;
end $function$;
CREATE OR REPLACE FUNCTION app.revoke_deviation(p_id uuid, p_reason text, p_novo_status text DEFAULT 'revoked'::text)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  if p_novo_status not in ('revoked','justified','ignored') then
raise exception 'status inválido: %', p_novo_status;
  end if;
  update app.deviation_event
 set status = p_novo_status, status_reason = p_reason, updated_at = now()
   where id = p_id and status = 'active';
end $function$;
CREATE OR REPLACE FUNCTION public.fn_data_freshness(p_stale_after_minutes integer DEFAULT NULL::integer)
 RETURNS TABLE(tenant_id uuid, entity text, last_sync_at timestamp with time zone, age_minutes integer, is_stale boolean)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select s.tenant_id,
         s.entity,
         max(s.finished_at)                                           as last_sync_at,
         (extract(epoch from (now() - max(s.finished_at))) / 60)::int as age_minutes,
         now() - max(s.finished_at) > make_interval(mins => greatest(
           coalesce(
             p_stale_after_minutes,
             -- 1,5x a cadência da entidade, arredondado para cima.
             case s.entity
               when 'Batida' then 25      -- cadência 15 min
               when 'Foto'   then 2160    -- cadência diária: 1,5 x 24 h
               else 45                    -- cadência 30 min
             end
           ), 1))
    from app.sync_run s
   where s.status = 'completed'
     and s.finished_at is not null
     and s.tenant_id = any (util.user_tenants())
   group by s.tenant_id, s.entity;
$function$;
comment on function public.fn_data_freshness(p_stale_after_minutes integer) is 'Idade do dado por entidade sincronizada, e o deadman da ingestão. Sem argumento, o limiar é 1,5x a cadência da entidade — 25 min para Batida (cadência 15), 2160 para Foto (cadência diária) e 45 para as demais (cadência 30) — de modo que uma execução perdida não alarma e duas seguidas alarmam. Com argumento, ele vale para todas. Ver docs/DECISAO-CADENCIA-SYNC.md.';
CREATE OR REPLACE FUNCTION public.fn_detection_health(p_backfill_max_age_hours integer DEFAULT 26)
 RETURNS TABLE(tenant_id uuid, last_incremental_at timestamp with time zone, incremental_age_minutes integer, last_backfill_at timestamp with time zone, backfill_age_hours integer, backfill_overdue boolean)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select r.tenant_id,
         max(r.started_at) filter (where r.scope = 'incremental'),
         (extract(epoch from (now() - max(r.started_at) filter (where r.scope = 'incremental'))) / 60)::int,
         max(r.started_at) filter (where r.scope = 'backfill'),
         (extract(epoch from (now() - max(r.started_at) filter (where r.scope = 'backfill'))) / 3600)::int,
         coalesce(
           now() - max(r.started_at) filter (where r.scope = 'backfill')
             > make_interval(hours => greatest(p_backfill_max_age_hours, 1)),
           true)          -- never ran = overdue
    from app.detection_run r
   where r.status = 'completed'
     and r.mode   = 'production'
     and r.tenant_id = any (util.user_tenants())
   group by r.tenant_id;
$function$;
comment on function public.fn_detection_health(p_backfill_max_age_hours integer) is 'Backfill overdue is true when it has not completed in p_backfill_max_age_hours OR has never run. Never-ran must read as overdue, not as null.';
CREATE OR REPLACE FUNCTION public.fn_kpi_period(p_de date, p_ate date, p_company_id uuid DEFAULT NULL::uuid, p_unit_id uuid DEFAULT NULL::uuid, p_department_id uuid DEFAULT NULL::uuid, p_manager_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(eventos bigint, colaboradores_afetados bigint, minutes_excedente bigint, minutes_faltante bigint, minutes_abs bigint, unidades_afetadas bigint, eventos_pendentes_ciclo bigint)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  select count(*),
         count(distinct d.employee_id),
         coalesce(sum(d.minutes) filter (where d.minutes > 0), 0),
         coalesce(-sum(d.minutes) filter (where d.minutes < 0), 0),
         coalesce(sum(abs(d.minutes)), 0),
         count(distinct d.unit_id),
         count(*) filter (where d.report_cycle_id is null)
  from app.deviation_event d
  join app.employee e on e.id = d.employee_id
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_company_id    is null or d.company_id = p_company_id)
    and (p_unit_id       is null or d.unit_id = p_unit_id)
    and (p_department_id is null or e.department_id = p_department_id)
    and (p_manager_id    is null or e.manager_employee_id = p_manager_id);
$function$;
CREATE OR REPLACE FUNCTION public.fn_pending_justification(p_de date, p_ate date, p_unit_id uuid DEFAULT NULL::uuid, p_department_id uuid DEFAULT NULL::uuid, p_manager_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(deviation_event_id uuid, employee_id uuid, employee_name text, unit_id uuid, unit_name text, reference_date date, type text, type_description text, minutes integer, detected_at timestamp with time zone)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  select d.id, d.employee_id, e.name, d.unit_id, u.name,
         d.reference_date, d.type, t.description, d.minutes, d.detected_at
  from app.deviation_event d
  join app.employee e on e.id = d.employee_id
  join app.deviation_type t on t.code = d.type
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type
      and cfg.active and cfg.requires_justification
  left join app.unit u on u.id = d.unit_id
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_unit_id       is null or d.unit_id = p_unit_id)
    and (p_department_id is null or e.department_id = p_department_id)
    and (p_manager_id    is null or e.manager_employee_id = p_manager_id)
    and not exists (
      select 1 from app.justification j
      where j.deviation_event_id = d.id and j.status = 'accepted'
    )
  order by d.reference_date desc, e.name;
$function$;
comment on function public.fn_pending_justification(p_de date, p_ate date, p_unit_id uuid, p_department_id uuid, p_manager_id uuid) is 'Desvio ativo, de tipo que exige justificativa, sem nenhuma justificativa aceita. Devolve a existência da pendência, nunca o texto de justificativa nenhuma.';
CREATE OR REPLACE FUNCTION public.fn_ranking_by_employee(p_de date, p_ate date, p_company_id uuid DEFAULT NULL::uuid, p_unit_id uuid DEFAULT NULL::uuid, p_limite integer DEFAULT 20, p_department_id uuid DEFAULT NULL::uuid, p_manager_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(employee_id uuid, employee_name text, unit_name text, eventos bigint, minutes_abs bigint)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  select d.employee_id, e.name, u.name, count(*), coalesce(sum(abs(d.minutes)),0)
  from app.deviation_event d
  join app.employee e on e.id = d.employee_id
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  left join app.unit u on u.id = d.unit_id
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_company_id    is null or d.company_id = p_company_id)
    and (p_unit_id       is null or d.unit_id = p_unit_id)
    and (p_department_id is null or e.department_id = p_department_id)
    and (p_manager_id    is null or e.manager_employee_id = p_manager_id)
  group by d.employee_id, e.name, u.name
  order by count(*) desc
  limit greatest(p_limite, 1);
$function$;
CREATE OR REPLACE FUNCTION public.fn_ranking_by_manager(p_de date, p_ate date, p_company_id uuid DEFAULT NULL::uuid, p_unit_id uuid DEFAULT NULL::uuid, p_limite integer DEFAULT 20, p_department_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(manager_id uuid, manager_name text, eventos bigint, minutes_abs bigint, colaboradores bigint, unidades bigint)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  -- ⚠️ `left join` e sem `where m.id is not null`: quem não tem gestor vira uma
  --    linha com `manager_id` nulo em vez de sumir do ranking. Um desvio que não
  --    aparece em recorte nenhum é a patologia que a fila de unidade existe para
  --    resolver, e ela não pode voltar por aqui.
  select e.manager_id, m.name, count(*), coalesce(sum(abs(d.minutes)),0),
         count(distinct d.employee_id), count(distinct d.unit_id)
  from app.deviation_event d
  join app.employee e on e.id = d.employee_id
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  left join app.manager m on m.id = e.manager_id
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_company_id    is null or d.company_id = p_company_id)
    and (p_unit_id       is null or d.unit_id = p_unit_id)
    and (p_department_id is null or e.department_id = p_department_id)
  group by e.manager_id, m.name
  order by count(*) desc
  limit greatest(p_limite, 1);
$function$;
CREATE OR REPLACE FUNCTION public.fn_ranking_by_unit(p_de date, p_ate date, p_company_id uuid DEFAULT NULL::uuid, p_limite integer DEFAULT 20, p_department_id uuid DEFAULT NULL::uuid, p_manager_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(unit_id uuid, unit_name text, eventos bigint, minutes_abs bigint, colaboradores bigint)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  select d.unit_id, u.name, count(*), coalesce(sum(abs(d.minutes)),0), count(distinct d.employee_id)
  from app.deviation_event d
  join app.employee e on e.id = d.employee_id
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  left join app.unit u on u.id = d.unit_id
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_company_id    is null or d.company_id = p_company_id)
    and (p_department_id is null or e.department_id = p_department_id)
    and (p_manager_id    is null or e.manager_employee_id = p_manager_id)
  group by d.unit_id, u.name
  order by count(*) desc
  limit greatest(p_limite, 1);
$function$;
CREATE OR REPLACE FUNCTION public.fn_recurrence(p_de date, p_ate date, p_min_dias integer DEFAULT 3, p_unit_id uuid DEFAULT NULL::uuid, p_department_id uuid DEFAULT NULL::uuid, p_manager_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(employee_id uuid, employee_name text, unit_name text, dias_com_desvio bigint, eventos bigint)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  select d.employee_id, e.name, u.name,
         count(distinct d.reference_date), count(*)
  from app.deviation_event d
  join app.employee e on e.id = d.employee_id
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  left join app.unit u on u.id = d.unit_id
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_unit_id       is null or d.unit_id = p_unit_id)
    and (p_department_id is null or e.department_id = p_department_id)
    and (p_manager_id    is null or e.manager_employee_id = p_manager_id)
  group by d.employee_id, e.name, u.name
  having count(distinct d.reference_date) >= greatest(p_min_dias, 1)
  order by count(distinct d.reference_date) desc;
$function$;
CREATE OR REPLACE FUNCTION public.fn_whatsapp_readiness()
 RETURNS TABLE(tenant_id uuid, provider text, official boolean, templates_total integer, templates_approved integer, rules_blocked integer, ready boolean)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
$function$;
comment on function public.fn_whatsapp_readiness() is 'ready = false quando o tenant está no provedor oficial e existe regra ligada apontando para template não aprovado. Nesse estado o alerta falha calado.';
CREATE OR REPLACE FUNCTION public.rls_auto_enable()
 RETURNS event_trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE
  cmd record;
BEGIN
  FOR cmd IN
    SELECT *
    FROM pg_event_trigger_ddl_commands()
    WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
      AND object_type IN ('table','partitioned table')
  LOOP
     IF cmd.schema_name IS NOT NULL AND cmd.schema_name IN ('public') AND cmd.schema_name NOT IN ('pg_catalog','information_schema') AND cmd.schema_name NOT LIKE 'pg_toast%' AND cmd.schema_name NOT LIKE 'pg_temp%' THEN
      BEGIN
        EXECUTE format('alter table if exists %s enable row level security', cmd.object_identity);
        RAISE LOG 'rls_auto_enable: enabled RLS on %', cmd.object_identity;
      EXCEPTION
        WHEN OTHERS THEN
          RAISE LOG 'rls_auto_enable: failed to enable RLS on %', cmd.object_identity;
      END;
     ELSE
        RAISE LOG 'rls_auto_enable: skip % (either system schema or not in enforced list: %.)', cmd.object_identity, cmd.schema_name;
     END IF;
  END LOOP;
END;
$function$;
CREATE OR REPLACE FUNCTION secullum.departamento_gestor_transition(p_close_id uuid, p_departamento_id uuid, p_estrutura_id uuid, p_departamento_id_secullum integer, p_estrutura_id_secullum integer, p_funcionarios_observados integer)
 RETURNS secullum.departamento_gestor
 LANGUAGE plpgsql
AS $function$
declare
    v_row secullum.departamento_gestor;
begin
    if p_close_id is not null then
        update secullum.departamento_gestor
           set observado_ate = now(),
               atualizado_em = now()
         where id = p_close_id
           and observado_ate is null;
    end if;

    insert into secullum.departamento_gestor (
        departamento_id, estrutura_id, "DepartamentoId", "EstruturaId",
        funcionarios_observados, origem
    ) values (
        p_departamento_id, p_estrutura_id, p_departamento_id_secullum, p_estrutura_id_secullum,
        p_funcionarios_observados, 'secullum_sync'
    )
    returning * into v_row;

    return v_row;
end;
$function$;
comment on function secullum.departamento_gestor_transition(p_close_id uuid, p_departamento_id uuid, p_estrutura_id uuid, p_departamento_id_secullum integer, p_estrutura_id_secullum integer, p_funcionarios_observados integer) is 'Único caminho de escrita para abrir uma nova linha VIGENTE de departamento_gestor (fechando a anterior, se p_close_id não for null) em uma única transação (ADR-013 §4). p_close_id = null => primeira linha vigente do departamento (sem titular anterior). Chamado exclusivamente pelo worker de sincronização cadastral (service_role) — nunca por UPDATE + INSERT como duas chamadas HTTP separadas.';
CREATE OR REPLACE FUNCTION util.block_table_in_public()
 RETURNS event_trigger
 LANGUAGE plpgsql
AS $function$
declare obj record;
begin
  for obj in select * from pg_event_trigger_ddl_commands()
  loop
if obj.object_type = 'table' and obj.schema_name = 'public' then
  raise exception using
    errcode = 'raise_exception',
    message = format('Tabela %s criada em public.', obj.object_identity),
    hint    = 'Tabelas vão para `app` (domínio) ou `secullum` (espelho). `public` só recebe views e RPCs.';
end if;
  end loop;
end $function$;
comment on function util.block_table_in_public() is 'Guarda de arquitetura. Para desativar temporariamente: ALTER EVENT TRIGGER trg_bloqueia_tabela_em_public DISABLE;';
CREATE OR REPLACE FUNCTION util.can_see_company(p_empresa_id uuid)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select exists (
select 1
from app.company emp
join app.tenant_member tm
  on tm.tenant_id = emp.tenant_id
 and tm.user_id   = (select auth.uid())
 and tm.active
where emp.id = p_empresa_id
  and (
    tm.role in ('owner','executive','hr','personnel')
    or exists (
      select 1 from app.user_scope e
      where e.user_id   = tm.user_id
        and e.tenant_id = emp.tenant_id
        and (e.company_id is null or e.company_id = emp.id)
    )
  )
  );
$function$;
CREATE OR REPLACE FUNCTION util.can_see_domain(p_tenant_id uuid, p_dominio app.sensitive_domain)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select exists (
select 1
from app.tenant_member tm
join app.domain_permission pd
  on pd.tenant_id = tm.tenant_id
 and pd.role     = tm.role
 and pd.domain   = p_dominio
 and pd.allowed
where tm.tenant_id = p_tenant_id
  and tm.user_id = (select auth.uid())
  and tm.active
  );
$function$;
CREATE OR REPLACE FUNCTION util.can_see_employee(p_colaborador_id uuid)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select exists (
select 1 from app.employee c
where c.id = p_colaborador_id
  and (
    util.is_admin(c.tenant_id)
    or (c.unit_id is not null and util.can_see_unit(c.unit_id))
    or (c.unit_id is null    and util.can_see_company(c.company_id))
  )
  );
$function$;
CREATE OR REPLACE FUNCTION util.can_see_unit(p_unidade_id uuid)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select exists (
select 1
from app.unit u
join app.tenant_member tm
  on tm.tenant_id = u.tenant_id
 and tm.user_id   = (select auth.uid())
 and tm.active
where u.id = p_unidade_id
  and (
    tm.role in ('owner','executive','hr','personnel')
    or exists (
      select 1 from app.user_scope e
      where e.user_id   = tm.user_id
        and e.tenant_id = u.tenant_id
        and (e.company_id is null or e.company_id = u.company_id)
        and (e.unit_id is null or e.unit_id = u.id)
    )
  )
  );
$function$;
CREATE OR REPLACE FUNCTION util.has_tenant(p_tenant_id uuid)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select exists (
select 1 from app.tenant_member tm
where tm.tenant_id = p_tenant_id
  and tm.user_id = (select auth.uid())
  and tm.active
  );
$function$;
CREATE OR REPLACE FUNCTION util.is_admin(p_tenant_id uuid)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select exists (
select 1 from app.tenant_member tm
where tm.tenant_id = p_tenant_id
  and tm.user_id = (select auth.uid())
  and tm.active
  and tm.role in ('owner','hr','personnel')
  );
$function$;
CREATE OR REPLACE FUNCTION util.lock_down_new_function()
 RETURNS event_trigger
 LANGUAGE plpgsql
AS $function$
declare obj record;
begin
  for obj in select * from pg_event_trigger_ddl_commands()
  loop
    if obj.object_type = 'function' and obj.schema_name in ('util','app') then
      execute format('revoke execute on function %s from public, anon', obj.object_identity);
    end if;
  end loop;
end $function$;
comment on function util.lock_down_new_function() is 'Keeps the migration-11 sweep permanent. Grant EXECUTE explicitly to authenticated/service_role after creating a helper — never to PUBLIC.';
CREATE OR REPLACE FUNCTION util.roles_in_tenant(p_tenant_id uuid)
 RETURNS app.user_role[]
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select coalesce(array_agg(tm.role), '{}'::app.user_role[])
  from app.tenant_member tm
  where tm.tenant_id = p_tenant_id
and tm.user_id = (select auth.uid())
and tm.active;
$function$;
CREATE OR REPLACE FUNCTION util.touch_atualizado_em()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  new.atualizado_em := now();
  return new;
end $function$;
comment on function util.touch_atualizado_em() is 'Toque de `atualizado_em` nas tabelas de ingestão, que ficaram fora da renomeação da 11b porque o runner da sincronização escreve nelas. A irmã em inglês é util.touch_updated_at().';
CREATE OR REPLACE FUNCTION util.touch_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  new.updated_at := now();
  return new;
end $function$;
CREATE OR REPLACE FUNCTION util.user_tenants()
 RETURNS uuid[]
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select coalesce(array_agg(tm.tenant_id), '{}'::uuid[])
  from app.tenant_member tm
  where tm.user_id = (select auth.uid())
and tm.active;
$function$;
CREATE OR REPLACE FUNCTION util.validate_alert_payload()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  ev record;
  faltando text := '';
begin
  if new.deviation_event_id is null then
    return new;                      -- aggregate/cycle alerts carry no occurrence
  end if;

  if jsonb_typeof(new.payload) is distinct from 'object' then
    raise exception using
      errcode = 'raise_exception',
      message = 'Alert payload must be a JSON object.',
      hint    = 'The occurrence alert needs structured fields, not a prebuilt string.';
  end if;

  select expected_time, actual_time, reference_date
    into ev
    from app.deviation_event
   where id = new.deviation_event_id;

  -- The date is always required: the message states the day, never "today".
  if new.payload ->> 'reference_date' is null then
    faltando := faltando || 'reference_date ';
  end if;

  -- Times are required only when the event actually has them. `no_punches`
  -- legitimately has no actual_time; demanding it would be a false constraint.
  if ev.expected_time is not null and new.payload ->> 'expected_time' is null then
    faltando := faltando || 'expected_time ';
  end if;
  if ev.actual_time is not null and new.payload ->> 'actual_time' is null then
    faltando := faltando || 'actual_time ';
  end if;

  if faltando <> '' then
    raise exception using
      errcode = 'raise_exception',
      message = format('Occurrence alert payload is missing: %s', trim(faltando)),
      hint    = 'Sync runs every 30 minutes, so an alert can arrive up to 40 minutes '
             || 'after the fact. It must state the observed time ("entry recorded '
             || '08:12, expected 08:00"), never a relative "now".';
  end if;

  return new;
end $function$;
CREATE OR REPLACE FUNCTION util.validate_alert_target()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare v_content text; v_tipo_contact text;
begin
  select content into v_content from app.alert_rule where id = new.rule_id;

  if new.contact_id is not null then
select type into v_tipo_contact from app.contact where id = new.contact_id;
  end if;

  if v_content = 'individual'
 and (new.responsibility = 'group' or v_tipo_contact = 'whatsapp_group') then
raise exception using
  errcode = 'raise_exception',
  message = 'Alerta de conteúdo individual não pode ter grupo como destinatário.',
  hint    = 'Exposição nominal de colaborador em grupo é risco trabalhista. Use content = ''aggregate'' para grupos.';
  end if;
  return new;
end $function$;
CREATE OR REPLACE FUNCTION util.validate_alert_template()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
end $function$;
CREATE OR REPLACE FUNCTION util.validate_template_body()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
end $function$;

reset check_function_bodies;

-- views
create materialized view if not exists app.mv_deviation_day as
 SELECT d.tenant_id,
    d.reference_date,
    d.company_id,
    d.unit_id,
    d.type,
    count(*) AS eventos,
    count(DISTINCT d.employee_id) AS colaboradores,
    COALESCE(sum(d.minutes) FILTER (WHERE d.minutes > 0), 0::bigint) AS minutes_excedente,
    COALESCE(- sum(d.minutes) FILTER (WHERE d.minutes < 0), 0::bigint) AS minutes_faltante
   FROM app.deviation_event d
     JOIN app.deviation_type_config cfg ON cfg.tenant_id = d.tenant_id AND cfg.code = d.type AND cfg.counts_as_deviation AND cfg.active
  WHERE d.status = 'active'::text AND d.mode = 'production'::text
  GROUP BY d.tenant_id, d.reference_date, d.company_id, d.unit_id, d.type;
create or replace view public.vw_deviation_by_employee_day with (security_invoker=on) as
 SELECT d.tenant_id,
    d.reference_date,
    d.employee_id,
    c.name AS employee_name,
    d.unit_id,
    u.name AS unit_name,
    count(*) AS eventos,
    sum(abs(d.minutes)) AS minutes_abs
   FROM app.deviation_event d
     JOIN app.employee c ON c.id = d.employee_id
     JOIN app.deviation_type_config cfg ON cfg.tenant_id = d.tenant_id AND cfg.code = d.type AND cfg.counts_as_deviation AND cfg.active
     LEFT JOIN app.unit u ON u.id = d.unit_id
  WHERE d.status = 'active'::text AND d.mode = 'production'::text
  GROUP BY d.tenant_id, d.reference_date, d.employee_id, c.name, d.unit_id, u.name;
create or replace view public.vw_deviation_daily_trend with (security_invoker=on) as
 SELECT d.tenant_id,
    d.reference_date,
    d.unit_id,
    t.direction,
    count(*) AS eventos,
    sum(abs(d.minutes)) AS minutes_abs
   FROM app.deviation_event d
     JOIN app.deviation_type t ON t.code = d.type
     JOIN app.deviation_type_config cfg ON cfg.tenant_id = d.tenant_id AND cfg.code = d.type AND cfg.counts_as_deviation AND cfg.active
  WHERE d.status = 'active'::text AND d.mode = 'production'::text
  GROUP BY d.tenant_id, d.reference_date, d.unit_id, t.direction;
create or replace view public.vw_deviation_event with (security_invoker=on) as
 SELECT d.id AS evento_id,
    d.tenant_id,
    d.reference_date,
    d.company_id,
    d.unit_id,
    u.name AS unit_name,
    d.employee_id,
    c.name AS employee_name,
    d.type,
    t.description AS type_description,
    t.direction,
    t.category,
    d.minutes,
    abs(d.minutes) AS minutes_abs,
    d.expected_time,
    d.actual_time,
    d.status,
    d.report_cycle_id,
    d.report_cycle_id IS NULL AS pendente_de_ciclo,
    d.detected_at,
    cfg.counts_as_deviation
   FROM app.deviation_event d
     JOIN app.deviation_type t ON t.code = d.type
     JOIN app.employee c ON c.id = d.employee_id
     LEFT JOIN app.unit u ON u.id = d.unit_id
     LEFT JOIN app.deviation_type_config cfg ON cfg.tenant_id = d.tenant_id AND cfg.code = d.type
  WHERE d.status = 'active'::text AND d.mode = 'production'::text;
create or replace view public.vw_deviation_summary_by_unit with (security_invoker=on) as
 SELECT d.tenant_id,
    d.reference_date,
    d.unit_id,
    u.name AS unit_name,
    d.company_id,
    count(*) AS eventos,
    count(DISTINCT d.employee_id) AS colaboradores,
    sum(d.minutes) FILTER (WHERE d.minutes > 0) AS minutes_excedente,
    - sum(d.minutes) FILTER (WHERE d.minutes < 0) AS minutes_faltante,
    sum(abs(d.minutes)) AS minutes_abs
   FROM app.deviation_event d
     JOIN app.deviation_type_config cfg ON cfg.tenant_id = d.tenant_id AND cfg.code = d.type AND cfg.counts_as_deviation AND cfg.active
     LEFT JOIN app.unit u ON u.id = d.unit_id
  WHERE d.status = 'active'::text AND d.mode = 'production'::text
  GROUP BY d.tenant_id, d.reference_date, d.unit_id, u.name, d.company_id;
create or replace view public.vw_document_expiry with (security_invoker=on) as
 SELECT doc.id AS document_id,
    doc.tenant_id,
    doc.employee_id,
    c.name AS employee_name,
    c.unit_id,
    dt.name AS type_name,
    doc.valid_until,
    doc.valid_until - CURRENT_DATE AS dias_para_vencer,
    dt.expiry_alert_days,
    (doc.valid_until - CURRENT_DATE) <= dt.expiry_alert_days AS em_alerta
   FROM app.document doc
     JOIN app.document_type dt ON dt.id = doc.type_id
     JOIN app.employee c ON c.id = doc.employee_id
  WHERE doc.status = 'active'::text AND doc.valid_until IS NOT NULL;
create or replace view public.vw_employee with (security_invoker=on) as
 SELECT c.id AS employee_id,
    c.tenant_id,
    c.company_id,
    c.unit_id,
    c.name,
    c.registration_number,
    c.cargo,
    c.hired_on,
    c.status,
    u.name AS unit_name,
    e.trade_name AS company_name,
    g.name AS gestor_name
   FROM app.employee c
     LEFT JOIN app.unit u ON u.id = c.unit_id
     LEFT JOIN app.company e ON e.id = c.company_id
     LEFT JOIN app.employee g ON g.id = c.manager_employee_id;
create or replace view public.vw_payroll_summary with (security_invoker=on) as
 SELECT f.tenant_id,
    comp.year,
    comp.month,
    f.company_id,
    f.unit_id,
    sum(f.amount) FILTER (WHERE f.nature = 'earning'::text) AS total_proventos,
    sum(f.amount) FILTER (WHERE f.nature = 'deduction'::text) AS total_descontos,
    sum(f.amount) FILTER (WHERE f.nature = 'payroll_charge'::text) AS total_encargos,
    count(DISTINCT f.employee_id) AS colaboradores
   FROM app.payroll_entry f
     JOIN app.payroll_period comp ON comp.id = f.payroll_period_id
  GROUP BY f.tenant_id, comp.year, comp.month, f.company_id, f.unit_id;
create or replace view public.vw_unit with (security_invoker=on) as
 SELECT u.id AS unit_id,
    u.tenant_id,
    u.company_id,
    e.trade_name AS company_name,
    u.code,
    u.name,
    u.timezone,
    u.active
   FROM app.unit u
     JOIN app.company e ON e.id = u.company_id;

-- índices (os que sustentam constraint já vieram acima)
CREATE INDEX IF NOT EXISTS agreement_installment_payroll_entry_id_fkidx ON app.agreement_installment USING btree (payroll_entry_id);
CREATE INDEX IF NOT EXISTS parcela_competencia_idx ON app.agreement_installment USING btree (tenant_id, period_year, period_month) WHERE (status = 'pendente'::text);
CREATE INDEX IF NOT EXISTS ai_query_tenant_idx ON app.ai_query USING btree (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ai_query_user_id_fkidx ON app.ai_query USING btree (user_id);
CREATE INDEX IF NOT EXISTS alert_queue_evento_idx ON app.alert_queue USING btree (deviation_event_id);
CREATE INDEX IF NOT EXISTS alert_queue_proxima_idx ON app.alert_queue USING btree (next_attempt_at) WHERE (status = ANY (ARRAY['pendente'::text, 'falhou'::text]));
CREATE INDEX IF NOT EXISTS alert_queue_report_cycle_id_fkidx ON app.alert_queue USING btree (report_cycle_id);
CREATE INDEX IF NOT EXISTS alert_queue_rule_id_fkidx ON app.alert_queue USING btree (rule_id);
CREATE INDEX IF NOT EXISTS alert_queue_tenant_id_fkidx ON app.alert_queue USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS alert_rule_deviation_type_fkidx ON app.alert_rule USING btree (deviation_type);
CREATE INDEX IF NOT EXISTS alert_rule_scope_unit_id_fkidx ON app.alert_rule USING btree (scope_unit_id);
CREATE INDEX IF NOT EXISTS alert_rule_tenant_idx ON app.alert_rule USING btree (tenant_id) WHERE active;
CREATE INDEX IF NOT EXISTS alert_rule_target_contact_id_fkidx ON app.alert_rule_target USING btree (contact_id);
CREATE INDEX IF NOT EXISTS regra_destino_regra_idx ON app.alert_rule_target USING btree (rule_id);
CREATE INDEX IF NOT EXISTS alert_sent_queue_id_fkidx ON app.alert_sent USING btree (queue_id);
CREATE INDEX IF NOT EXISTS alert_sent_rule_id_fkidx ON app.alert_sent USING btree (rule_id);
CREATE INDEX IF NOT EXISTS alert_sent_tenant_idx ON app.alert_sent USING btree (tenant_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS audit_log_entidade_idx ON app.audit_log USING btree (entity, entity_id);
CREATE INDEX IF NOT EXISTS audit_log_tenant_idx ON app.audit_log USING btree (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_log_user_id_fkidx ON app.audit_log USING btree (user_id);
CREATE INDEX IF NOT EXISTS batida_marcacao_fontedadosid_idx ON app.batida_marcacao USING btree ("FonteDadosId");
CREATE INDEX IF NOT EXISTS batida_marcacao_funcionario_id_data_idx ON app.batida_marcacao USING btree (funcionario_id, data);
CREATE INDEX IF NOT EXISTS batida_marcacao_hora_idx ON app.batida_marcacao USING btree (funcionario_id, data) WHERE (hora IS NOT NULL);
CREATE INDEX IF NOT EXISTS batida_marcacao_tenant_idx ON app.batida_marcacao USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS company_tenant_idx ON app.company USING btree (tenant_id) WHERE active;
CREATE INDEX IF NOT EXISTS contact_tenant_idx ON app.contact USING btree (tenant_id) WHERE active;
CREATE INDEX IF NOT EXISTS cost_center_company_id_fkidx ON app.cost_center USING btree (company_id);
CREATE INDEX IF NOT EXISTS cost_center_unidade_idx ON app.cost_center USING btree (unit_id);
CREATE INDEX IF NOT EXISTS cursor_sincronizacao_tenant_idx ON app.cursor_sincronizacao USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS department_empresa_idx ON app.department USING btree (company_id);
CREATE INDEX IF NOT EXISTS detection_run_backfill_idx ON app.detection_run USING btree (tenant_id, started_at DESC) WHERE ((scope = 'backfill'::text) AND (status = 'completed'::text));
CREATE INDEX IF NOT EXISTS detection_run_incremental_idx ON app.detection_run USING btree (tenant_id, started_at DESC) WHERE ((scope = 'incremental'::text) AND (status = 'completed'::text));
CREATE INDEX IF NOT EXISTS detection_run_tenant_idx ON app.detection_run USING btree (tenant_id, started_at DESC);
CREATE INDEX IF NOT EXISTS deviation_event_ciclo_idx ON app.deviation_event USING btree (report_cycle_id) WHERE (report_cycle_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS deviation_event_colab_idx ON app.deviation_event USING btree (employee_id, reference_date DESC) WHERE ((status = 'ativo'::text) AND (mode = 'producao'::text));
CREATE INDEX IF NOT EXISTS deviation_event_company_id_fkidx ON app.deviation_event USING btree (company_id);
CREATE INDEX IF NOT EXISTS deviation_event_dash_idx ON app.deviation_event USING btree (tenant_id, reference_date, unit_id) WHERE ((status = 'ativo'::text) AND (mode = 'producao'::text));
CREATE INDEX IF NOT EXISTS deviation_event_execucao_idx ON app.deviation_event USING btree (run_id);
CREATE INDEX IF NOT EXISTS deviation_event_pendente_idx ON app.deviation_event USING btree (tenant_id, unit_id) WHERE ((report_cycle_id IS NULL) AND (status = 'ativo'::text) AND (mode = 'producao'::text));
CREATE INDEX IF NOT EXISTS deviation_event_supersede_idx ON app.deviation_event USING btree (supersede_id);
CREATE INDEX IF NOT EXISTS deviation_event_type_fkidx ON app.deviation_event USING btree (type);
CREATE UNIQUE INDEX IF NOT EXISTS deviation_event_unico_active ON app.deviation_event USING btree (employee_id, reference_date, type) WHERE ((status = 'ativo'::text) AND (mode = 'producao'::text));
CREATE UNIQUE INDEX IF NOT EXISTS deviation_event_unico_active_modo ON app.deviation_event USING btree (employee_id, reference_date, type, mode) WHERE (status = 'active'::text);
CREATE INDEX IF NOT EXISTS deviation_event_unit_id_fkidx ON app.deviation_event USING btree (unit_id);
CREATE INDEX IF NOT EXISTS deviation_periodo_idx ON app.deviation_event USING btree (tenant_id, unit_id, reference_date) WHERE ((status = 'ativo'::text) AND (mode = 'producao'::text));
CREATE INDEX IF NOT EXISTS deviation_tipo_periodo_idx ON app.deviation_event USING btree (tenant_id, type, reference_date) WHERE ((status = 'ativo'::text) AND (mode = 'producao'::text));
CREATE INDEX IF NOT EXISTS deviation_type_config_code_fkidx ON app.deviation_type_config USING btree (code);
CREATE INDEX IF NOT EXISTS disciplinary_colab_idx ON app.disciplinary_event USING btree (employee_id, occurred_on DESC);
CREATE INDEX IF NOT EXISTS disciplinary_tenant_idx ON app.disciplinary_event USING btree (tenant_id, occurred_on DESC);
CREATE INDEX IF NOT EXISTS document_colab_idx ON app.document USING btree (employee_id, type_id);
CREATE INDEX IF NOT EXISTS document_created_by_fkidx ON app.document USING btree (created_by);
CREATE INDEX IF NOT EXISTS document_replaces_id_fkidx ON app.document USING btree (replaces_id);
CREATE INDEX IF NOT EXISTS document_type_id_fkidx ON app.document USING btree (type_id);
CREATE INDEX IF NOT EXISTS document_vencimento_idx ON app.document USING btree (tenant_id, valid_until) WHERE ((status = 'ativo'::text) AND (valid_until IS NOT NULL));
CREATE INDEX IF NOT EXISTS domain_permission_rls_idx ON app.domain_permission USING btree (tenant_id, role, domain) WHERE allowed;
CREATE INDEX IF NOT EXISTS employee_departamento_idx ON app.employee USING btree (department_id);
CREATE INDEX IF NOT EXISTS employee_empresa_idx ON app.employee USING btree (company_id);
CREATE INDEX IF NOT EXISTS employee_gestor_idx ON app.employee USING btree (manager_employee_id);
CREATE UNIQUE INDEX IF NOT EXISTS employee_hr_code_unique ON app.employee USING btree (tenant_id, hr_code) WHERE (hr_code IS NOT NULL);
CREATE INDEX IF NOT EXISTS employee_manager_idx ON app.employee USING btree (manager_id);
CREATE INDEX IF NOT EXISTS employee_tenant_unidade_idx ON app.employee USING btree (tenant_id, unit_id) WHERE (status <> 'desligado'::text);
CREATE INDEX IF NOT EXISTS employee_unit_id_fkidx ON app.employee USING btree (unit_id);
CREATE INDEX IF NOT EXISTS employee_compensation_recorded_by_fkidx ON app.employee_compensation USING btree (recorded_by);
CREATE INDEX IF NOT EXISTS employee_compensation_tenant_id_fkidx ON app.employee_compensation USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS remuneracao_colab_idx ON app.employee_compensation USING btree (employee_id, effective_from DESC);
CREATE INDEX IF NOT EXISTS employee_pii_tenant_idx ON app.employee_pii USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS employee_position_tenant_id_fkidx ON app.employee_position USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS employee_position_unit_id_fkidx ON app.employee_position USING btree (unit_id);
CREATE INDEX IF NOT EXISTS responsibility_colab_idx ON app.employee_position USING btree (employee_id, effective_from DESC);
CREATE UNIQUE INDEX IF NOT EXISTS empresa_evento_status_baseline_uniq ON app.empresa_evento_status USING btree (empresa_id) WHERE (tipo_evento = 'baseline'::text);
CREATE INDEX IF NOT EXISTS empresa_evento_status_empresa_detectado_idx ON app.empresa_evento_status USING btree (empresa_id, detectado_em DESC);
CREATE INDEX IF NOT EXISTS empresa_evento_status_tenant_idx ON app.empresa_evento_status USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS expected_workday_baixa_confianca_idx ON app.expected_workday USING btree (tenant_id, reference_date) WHERE (confidence < 80);
CREATE INDEX IF NOT EXISTS expected_workday_tenant_data_idx ON app.expected_workday USING btree (tenant_id, reference_date);
CREATE INDEX IF NOT EXISTS file_import_payroll_period_id_fkidx ON app.file_import USING btree (payroll_period_id);
CREATE INDEX IF NOT EXISTS file_import_uploaded_by_fkidx ON app.file_import USING btree (uploaded_by);
CREATE INDEX IF NOT EXISTS importacao_tenant_idx ON app.file_import USING btree (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS acordo_colab_idx ON app.financial_agreement USING btree (employee_id, status);
CREATE INDEX IF NOT EXISTS financial_agreement_authorized_by_fkidx ON app.financial_agreement USING btree (authorized_by);
CREATE INDEX IF NOT EXISTS financial_agreement_document_id_fkidx ON app.financial_agreement USING btree (document_id);
CREATE INDEX IF NOT EXISTS financial_agreement_tenant_id_fkidx ON app.financial_agreement USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS financial_threshold_company_id_fkidx ON app.financial_threshold USING btree (company_id);
CREATE INDEX IF NOT EXISTS financial_threshold_tenant_idx ON app.financial_threshold USING btree (tenant_id) WHERE active;
CREATE INDEX IF NOT EXISTS financial_threshold_unit_id_fkidx ON app.financial_threshold USING btree (unit_id);
CREATE UNIQUE INDEX IF NOT EXISTS funcionario_evento_status_baseline_uniq ON app.funcionario_evento_status USING btree (funcionario_id) WHERE (tipo_evento = 'baseline'::text);
CREATE INDEX IF NOT EXISTS funcionario_evento_status_funcionario_data_evento_idx ON app.funcionario_evento_status USING btree (funcionario_id, data_evento);
CREATE INDEX IF NOT EXISTS funcionario_evento_status_funcionario_detectado_idx ON app.funcionario_evento_status USING btree (funcionario_id, detectado_em DESC);
CREATE INDEX IF NOT EXISTS funcionario_evento_status_tenant_idx ON app.funcionario_evento_status USING btree (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS integration_whatsapp_unico_ativo ON app.integration USING btree (tenant_id) WHERE (active AND (provider = ANY (ARRAY['meta_cloud'::text, 'z_api'::text, 'uazapi'::text])));
CREATE UNIQUE INDEX IF NOT EXISTS job_execucao_em_andamento_key ON app.job_execucao USING btree (job) WHERE (status = 'running'::text);
CREATE INDEX IF NOT EXISTS job_execucao_job_iniciado_em_idx ON app.job_execucao USING btree (job, iniciado_em DESC);
CREATE INDEX IF NOT EXISTS justification_aceita_idx ON app.justification USING btree (deviation_event_id) WHERE (status = 'accepted'::text);
CREATE INDEX IF NOT EXISTS justification_author_user_id_fkidx ON app.justification USING btree (author_user_id);
CREATE INDEX IF NOT EXISTS justification_colab_idx ON app.justification USING btree (employee_id, reference_date DESC);
CREATE INDEX IF NOT EXISTS justification_evento_idx ON app.justification USING btree (deviation_event_id);
CREATE INDEX IF NOT EXISTS justification_tenant_id_fkidx ON app.justification USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS leave_period_periodo_idx ON app.leave_period USING btree (employee_id, start_date, end_date);
CREATE INDEX IF NOT EXISTS leave_period_tenant_id_fkidx ON app.leave_period USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS manager_tenant_idx ON app.manager USING btree (tenant_id) WHERE active;
CREATE INDEX IF NOT EXISTS message_template_tenant_idx ON app.message_template USING btree (tenant_id, code) WHERE active;
CREATE INDEX IF NOT EXISTS mv_deviation_day_periodo_idx ON app.mv_deviation_day USING btree (tenant_id, reference_date);
CREATE UNIQUE INDEX IF NOT EXISTS mv_deviation_day_pk ON app.mv_deviation_day USING btree (tenant_id, reference_date, company_id, COALESCE(unit_id, '00000000-0000-0000-0000-000000000000'::uuid), type);
CREATE INDEX IF NOT EXISTS exame_colab_idx ON app.occupational_exam USING btree (employee_id, performed_on DESC);
CREATE INDEX IF NOT EXISTS exame_vencimento_idx ON app.occupational_exam USING btree (tenant_id, valid_until) WHERE (valid_until IS NOT NULL);
CREATE INDEX IF NOT EXISTS occupational_exam_created_by_fkidx ON app.occupational_exam USING btree (created_by);
CREATE INDEX IF NOT EXISTS occupational_exam_document_id_fkidx ON app.occupational_exam USING btree (document_id);
CREATE INDEX IF NOT EXISTS payroll_charge_comp_idx ON app.payroll_charge USING btree (payroll_period_id, company_id);
CREATE INDEX IF NOT EXISTS payroll_charge_company_id_fkidx ON app.payroll_charge USING btree (company_id);
CREATE INDEX IF NOT EXISTS payroll_charge_tenant_id_fkidx ON app.payroll_charge USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS payroll_charge_unit_id_fkidx ON app.payroll_charge USING btree (unit_id);
CREATE INDEX IF NOT EXISTS payroll_entry_cc_idx ON app.payroll_entry USING btree (cost_center_id);
CREATE INDEX IF NOT EXISTS payroll_entry_colab_idx ON app.payroll_entry USING btree (employee_id, payroll_period_id);
CREATE INDEX IF NOT EXISTS payroll_entry_comp_idx ON app.payroll_entry USING btree (payroll_period_id, company_id);
CREATE INDEX IF NOT EXISTS payroll_entry_company_id_fkidx ON app.payroll_entry USING btree (company_id);
CREATE INDEX IF NOT EXISTS payroll_entry_import_idx ON app.payroll_entry USING btree (import_id);
CREATE INDEX IF NOT EXISTS payroll_entry_tenant_id_fkidx ON app.payroll_entry USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS payroll_entry_unidade_idx ON app.payroll_entry USING btree (unit_id, payroll_period_id);
CREATE INDEX IF NOT EXISTS payroll_event_map_categoria_idx ON app.payroll_event_map USING btree (tenant_id, category);
CREATE INDEX IF NOT EXISTS report_cycle_tenant_id_fkidx ON app.report_cycle USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS report_cycle_unidade_idx ON app.report_cycle USING btree (unit_id, period_start DESC);
CREATE INDEX IF NOT EXISTS sync_run_backfill_idx ON app.sync_run USING btree (tenant_id, entity, started_at DESC) WHERE ((scope = 'backfill'::text) AND (status = 'completed'::text));
CREATE UNIQUE INDEX IF NOT EXISTS sync_run_em_andamento_key ON app.sync_run USING btree (tenant_id, entity) WHERE (status = 'running'::text);
CREATE INDEX IF NOT EXISTS sync_run_falha_idx ON app.sync_run USING btree (tenant_id, started_at DESC) WHERE (status = 'falhou'::text);
CREATE INDEX IF NOT EXISTS sync_run_freshness_idx ON app.sync_run USING btree (tenant_id, entity, finished_at DESC) WHERE (status = 'completed'::text);
CREATE INDEX IF NOT EXISTS sync_run_idx ON app.sync_run USING btree (integration_id, entity, started_at DESC);
CREATE INDEX IF NOT EXISTS tenant_member_rls_idx ON app.tenant_member USING btree (user_id, tenant_id, role) WHERE active;
CREATE INDEX IF NOT EXISTS tenant_member_user_idx ON app.tenant_member USING btree (user_id) WHERE active;
CREATE INDEX IF NOT EXISTS unit_company_id_fkidx ON app.unit USING btree (company_id);
CREATE INDEX IF NOT EXISTS unit_tenant_empresa_idx ON app.unit USING btree (tenant_id, company_id) WHERE active;
CREATE INDEX IF NOT EXISTS unit_responsible_contact_id_fkidx ON app.unit_responsible USING btree (contact_id);
CREATE INDEX IF NOT EXISTS unit_responsible_tenant_id_fkidx ON app.unit_responsible USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS unit_responsible_unidade_idx ON app.unit_responsible USING btree (unit_id);
CREATE INDEX IF NOT EXISTS unit_mapa_unidade_idx ON app.unit_secullum_map USING btree (unit_id);
CREATE INDEX IF NOT EXISTS unit_secullum_map_validated_by_fkidx ON app.unit_secullum_map USING btree (validated_by);
CREATE INDEX IF NOT EXISTS escopo_rls_idx ON app.user_scope USING btree (user_id, tenant_id, company_id, unit_id);
CREATE INDEX IF NOT EXISTS user_scope_empresa_idx ON app.user_scope USING btree (company_id) WHERE (company_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS user_scope_lookup_idx ON app.user_scope USING btree (user_id, tenant_id);
CREATE INDEX IF NOT EXISTS user_scope_tenant_id_fkidx ON app.user_scope USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS user_scope_unidade_idx ON app.user_scope USING btree (unit_id) WHERE (unit_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS movimentacao_colab_idx ON app.workforce_movement USING btree (employee_id);
CREATE INDEX IF NOT EXISTS movimentacao_data_idx ON app.workforce_movement USING btree (tenant_id, event_date DESC);
CREATE INDEX IF NOT EXISTS workforce_movement_company_id_fkidx ON app.workforce_movement USING btree (company_id);
CREATE INDEX IF NOT EXISTS workforce_movement_payroll_period_id_fkidx ON app.workforce_movement USING btree (payroll_period_id);
CREATE INDEX IF NOT EXISTS workforce_movement_unit_id_fkidx ON app.workforce_movement USING btree (unit_id);
CREATE INDEX IF NOT EXISTS batida_batidaid_idx ON secullum."Batida" USING btree ("BatidaId");
CREATE INDEX IF NOT EXISTS batida_data_idx ON secullum."Batida" USING btree ("Data");
CREATE INDEX IF NOT EXISTS batida_tenant_idx ON secullum."Batida" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS batida_fonte_dados_batida_id_idx ON secullum."BatidaFonteDados" USING btree (batida_id);
CREATE INDEX IF NOT EXISTS batida_fonte_dados_fontedadosid_idx ON secullum."BatidaFonteDados" USING btree ("FonteDadosId");
CREATE INDEX IF NOT EXISTS batidafontedados_tenant_idx ON secullum."BatidaFonteDados" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS cidade_tenant_idx ON secullum."Cidade" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS "Departamento_empresa_id_fkidx" ON secullum."Departamento" USING btree (empresa_id);
CREATE INDEX IF NOT EXISTS departamento_tenant_idx ON secullum."Departamento" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS empresa_cidade_id_idx ON secullum."Empresa" USING btree (cidade_id);
CREATE INDEX IF NOT EXISTS empresa_empresaid_idx ON secullum."Empresa" USING btree ("EmpresaId");
CREATE INDEX IF NOT EXISTS empresa_tenant_idx ON secullum."Empresa" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS estrutura_tenant_idx ON secullum."Estrutura" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS funcao_tenant_idx ON secullum."Funcao" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS "Funcionario_afastamento_atual_id_fkidx" ON secullum."Funcionario" USING btree (afastamento_atual_id);
CREATE INDEX IF NOT EXISTS "Funcionario_departamento_id_fkidx" ON secullum."Funcionario" USING btree (departamento_id);
CREATE INDEX IF NOT EXISTS "Funcionario_empresa_id_fkidx" ON secullum."Funcionario" USING btree (empresa_id);
CREATE INDEX IF NOT EXISTS "Funcionario_horario_id_fkidx" ON secullum."Funcionario" USING btree (horario_id);
CREATE INDEX IF NOT EXISTS funcionario_afastado_hoje_idx ON secullum."Funcionario" USING btree (afastado_hoje) WHERE (afastado_hoje = true);
CREATE INDEX IF NOT EXISTS funcionario_cidade_id_idx ON secullum."Funcionario" USING btree (cidade_id);
CREATE INDEX IF NOT EXISTS funcionario_foto_fila_idx ON secullum."Funcionario" USING btree (foto_tentativa_em NULLS FIRST) WHERE "PossuiFoto";
CREATE INDEX IF NOT EXISTS funcionario_funcao_id_idx ON secullum."Funcionario" USING btree (funcao_id);
CREATE INDEX IF NOT EXISTS funcionario_tenant_idx ON secullum."Funcionario" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS funcionario_afastamento_funcionario_janela_idx ON secullum."FuncionarioAfastamento" USING btree (funcionario_id, "Inicio", "Fim");
CREATE INDEX IF NOT EXISTS funcionario_afastamento_janela_idx ON secullum."FuncionarioAfastamento" USING btree ("Fim", "Inicio");
CREATE INDEX IF NOT EXISTS funcionarioafastamento_tenant_idx ON secullum."FuncionarioAfastamento" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS funcionario_centro_custo_funcionario_id_idx ON secullum."FuncionarioCentroCusto" USING btree (funcionario_id);
CREATE INDEX IF NOT EXISTS funcionariocentrocusto_tenant_idx ON secullum."FuncionarioCentroCusto" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horario_tenant_idx ON secullum."Horario" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horariodescanso_tenant_idx ON secullum."HorarioDescanso" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horario_descanso_faixa_item_pai_idx ON secullum."HorarioDescansoFaixaItem" USING btree (horario_descanso_id);
CREATE INDEX IF NOT EXISTS horariodescansofaixaitem_tenant_idx ON secullum."HorarioDescansoFaixaItem" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horario_dia_horariodiaid_idx ON secullum."HorarioDia" USING btree ("HorarioDiaId");
CREATE INDEX IF NOT EXISTS horariodia_tenant_idx ON secullum."HorarioDia" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horarioextras_tenant_idx ON secullum."HorarioExtras" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horario_faixas_extras_horario_id_idx ON secullum."HorarioFaixasExtras" USING btree (horario_id);
CREATE INDEX IF NOT EXISTS horariofaixasextras_tenant_idx ON secullum."HorarioFaixasExtras" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horario_faixas_extras_item_pai_idx ON secullum."HorarioFaixasExtrasItem" USING btree (horario_faixas_extras_id);
CREATE INDEX IF NOT EXISTS horariofaixasextrasitem_tenant_idx ON secullum."HorarioFaixasExtrasItem" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horariotoleranciaespecifica_tenant_idx ON secullum."HorarioToleranciaEspecifica" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horario_tolerancia_especifica_item_pai_idx ON secullum."HorarioToleranciaEspecificaItem" USING btree (horario_tolerancia_especifica_id);
CREATE INDEX IF NOT EXISTS horariotoleranciaespecificaitem_tenant_idx ON secullum."HorarioToleranciaEspecificaItem" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horariosopcoes_tenant_idx ON secullum."HorariosOpcoes" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS departamento_gestor_estrutura_vigente_idx ON secullum.departamento_gestor USING btree (estrutura_id) WHERE (observado_ate IS NULL);
CREATE INDEX IF NOT EXISTS departamento_gestor_historico_idx ON secullum.departamento_gestor USING btree (departamento_id, observado_desde DESC);
CREATE UNIQUE INDEX IF NOT EXISTS departamento_gestor_vigente_key ON secullum.departamento_gestor USING btree (departamento_id) WHERE (observado_ate IS NULL);
CREATE UNIQUE INDEX IF NOT EXISTS estrutura_evento_titular_baseline_uniq ON secullum.estrutura_evento_titular USING btree (estrutura_id) WHERE (tipo_evento = 'baseline'::text);
CREATE INDEX IF NOT EXISTS estrutura_evento_titular_estrutura_detectado_idx ON secullum.estrutura_evento_titular USING btree (estrutura_id, detectado_em DESC);

-- policies
create policy parcela_read on app.agreement_installment
  for select to authenticated
  using ((util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND (EXISTS ( SELECT 1
   FROM app.financial_agreement a
  WHERE ((a.id = agreement_installment.agreement_id) AND util.can_see_employee(a.employee_id))))));
create policy parcela_write on app.agreement_installment
  for all to authenticated
  using ((util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.is_admin(tenant_id)))
  with check ((util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.is_admin(tenant_id)));
create policy ai_query_read on app.ai_query
  for select to authenticated
  using (((user_id = ( SELECT auth.uid() AS uid)) OR util.is_admin(tenant_id)));
create policy alert_queue_admin on app.alert_queue
  for select to authenticated
  using (util.is_admin(tenant_id));
create policy alert_rule_admin on app.alert_rule
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy alert_rule_read on app.alert_rule
  for select to authenticated
  using (util.has_tenant(tenant_id));
create policy regra_destino_admin on app.alert_rule_target
  for all to authenticated
  using ((EXISTS ( SELECT 1
   FROM app.alert_rule r
  WHERE ((r.id = alert_rule_target.rule_id) AND util.is_admin(r.tenant_id)))))
  with check ((EXISTS ( SELECT 1
   FROM app.alert_rule r
  WHERE ((r.id = alert_rule_target.rule_id) AND util.is_admin(r.tenant_id)))));
create policy alert_sent_read on app.alert_sent
  for select to authenticated
  using (util.is_admin(tenant_id));
create policy audit_read on app.audit_log
  for select to authenticated
  using (util.is_admin(tenant_id));
create policy batida_marcacao_tenant_read on app.batida_marcacao
  for select to authenticated
  using (util.has_tenant(tenant_id));
create policy company_read on app.company
  for select to authenticated
  using (util.can_see_company(id));
create policy company_write on app.company
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy contact_admin on app.contact
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy contact_read on app.contact
  for select to authenticated
  using (util.has_tenant(tenant_id));
create policy cost_center_read on app.cost_center
  for select to authenticated
  using (util.has_tenant(tenant_id));
create policy cursor_sincronizacao_tenant_read on app.cursor_sincronizacao
  for select to authenticated
  using (util.has_tenant(tenant_id));
create policy department_read on app.department
  for select to authenticated
  using (util.can_see_company(company_id));
create policy detection_run_read on app.detection_run
  for select to authenticated
  using (util.is_admin(tenant_id));
create policy deviation_read on app.deviation_event
  for select to authenticated
  using ((((mode = 'production'::text) OR util.is_admin(tenant_id)) AND (util.is_admin(tenant_id) OR ((unit_id IS NOT NULL) AND util.can_see_unit(unit_id)) OR ((unit_id IS NULL) AND util.can_see_company(company_id)))));
create policy deviation_write on app.deviation_event
  for update to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy deviation_type_read on app.deviation_type
  for select to authenticated
  using (true);
create policy desvio_config_admin on app.deviation_type_config
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy desvio_config_read on app.deviation_type_config
  for select to authenticated
  using (util.has_tenant(tenant_id));
create policy disciplinary_read on app.disciplinary_event
  for select to authenticated
  using ((util.can_see_domain(tenant_id, 'disciplinary'::app.sensitive_domain) AND util.can_see_employee(employee_id)));
create policy disciplinary_write on app.disciplinary_event
  for all to authenticated
  using (util.can_see_domain(tenant_id, 'disciplinary'::app.sensitive_domain))
  with check (util.can_see_domain(tenant_id, 'disciplinary'::app.sensitive_domain));
create policy document_read on app.document
  for select to authenticated
  using ((util.can_see_employee(employee_id) AND (EXISTS ( SELECT 1
   FROM app.document_type dt
  WHERE ((dt.id = document.type_id) AND util.can_see_domain(dt.tenant_id, dt.domain))))));
create policy document_write on app.document
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy document_type_admin on app.document_type
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy document_type_read on app.document_type
  for select to authenticated
  using (util.has_tenant(tenant_id));
create policy domain_permission_read on app.domain_permission
  for select to authenticated
  using (util.has_tenant(tenant_id));
create policy employee_read on app.employee
  for select to authenticated
  using ((util.is_admin(tenant_id) OR ((unit_id IS NOT NULL) AND util.can_see_unit(unit_id)) OR ((unit_id IS NULL) AND util.can_see_company(company_id))));
create policy employee_write on app.employee
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy remuneracao_read on app.employee_compensation
  for select to authenticated
  using ((util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.can_see_employee(employee_id)));
create policy remuneracao_write on app.employee_compensation
  for all to authenticated
  using ((util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.is_admin(tenant_id)))
  with check ((util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.is_admin(tenant_id)));
create policy pii_read on app.employee_pii
  for select to authenticated
  using ((util.can_see_domain(tenant_id, 'pii'::app.sensitive_domain) AND util.can_see_employee(employee_id)));
create policy pii_write on app.employee_pii
  for all to authenticated
  using ((util.can_see_domain(tenant_id, 'pii'::app.sensitive_domain) AND util.is_admin(tenant_id)))
  with check ((util.can_see_domain(tenant_id, 'pii'::app.sensitive_domain) AND util.is_admin(tenant_id)));
create policy responsibility_read on app.employee_position
  for select to authenticated
  using (util.can_see_employee(employee_id));
create policy empresa_evento_status_tenant_read on app.empresa_evento_status
  for select to authenticated
  using (util.has_tenant(tenant_id));
create policy expected_workday_read on app.expected_workday
  for select to authenticated
  using (util.can_see_employee(employee_id));
create policy importacao_read on app.file_import
  for select to authenticated
  using (util.is_admin(tenant_id));
create policy importacao_write on app.file_import
  for insert to authenticated
  with check (util.is_admin(tenant_id));
create policy acordo_read on app.financial_agreement
  for select to authenticated
  using ((util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.can_see_employee(employee_id)));
create policy acordo_write on app.financial_agreement
  for all to authenticated
  using ((util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.is_admin(tenant_id)))
  with check ((util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.is_admin(tenant_id)));
create policy limiar_admin on app.financial_threshold
  for all to authenticated
  using ((util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.is_admin(tenant_id)))
  with check ((util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.is_admin(tenant_id)));
create policy funcionario_evento_status_tenant_read on app.funcionario_evento_status
  for select to authenticated
  using (util.has_tenant(tenant_id));
create policy integration_admin on app.integration
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy justification_read on app.justification
  for select to authenticated
  using (util.can_see_employee(employee_id));
create policy justification_write on app.justification
  for insert to authenticated
  with check (util.can_see_employee(employee_id));
create policy leave_period_read on app.leave_period
  for select to authenticated
  using (util.can_see_employee(employee_id));
create policy manager_read on app.manager
  for select to authenticated
  using ((util.is_admin(tenant_id) OR (EXISTS ( SELECT 1
   FROM app.employee e
  WHERE ((e.manager_id = manager.id) AND util.can_see_employee(e.id))))));
create policy manager_write on app.manager
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy message_template_admin on app.message_template
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy message_template_read on app.message_template
  for select to authenticated
  using (util.has_tenant(tenant_id));
create policy metric_read on app.metric
  for select to authenticated
  using (active);
create policy exame_read on app.occupational_exam
  for select to authenticated
  using ((util.can_see_domain(tenant_id, 'health'::app.sensitive_domain) AND util.can_see_employee(employee_id)));
create policy exame_write on app.occupational_exam
  for all to authenticated
  using (util.can_see_domain(tenant_id, 'health'::app.sensitive_domain))
  with check (util.can_see_domain(tenant_id, 'health'::app.sensitive_domain));
create policy payroll_charge_read on app.payroll_charge
  for select to authenticated
  using ((util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.can_see_company(company_id)));
create policy payroll_entry_read on app.payroll_entry
  for select to authenticated
  using ((util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND (util.is_admin(tenant_id) OR ((unit_id IS NOT NULL) AND util.can_see_unit(unit_id)) OR ((unit_id IS NULL) AND util.can_see_company(company_id)))));
create policy payroll_event_map_admin on app.payroll_event_map
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy payroll_period_read on app.payroll_period
  for select to authenticated
  using (util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain));
create policy ciclo_read on app.report_cycle
  for select to authenticated
  using ((((unit_id IS NULL) AND util.is_admin(tenant_id)) OR util.can_see_unit(unit_id)));
create policy rotation_map_admin on app.schedule_rotation_map
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy sync_read on app.sync_run
  for select to authenticated
  using (util.is_admin(tenant_id));
create policy tenant_read on app.tenant
  for select to authenticated
  using (util.has_tenant(id));
create policy tenant_member_admin on app.tenant_member
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy tenant_member_read on app.tenant_member
  for select to authenticated
  using (util.has_tenant(tenant_id));
create policy unit_read on app.unit
  for select to authenticated
  using (util.can_see_unit(id));
create policy unit_write on app.unit
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy unit_responsible_admin on app.unit_responsible
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy unit_responsible_read on app.unit_responsible
  for select to authenticated
  using (util.can_see_unit(unit_id));
create policy mapa_admin on app.unit_secullum_map
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy escopo_admin on app.user_scope
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));
create policy escopo_read on app.user_scope
  for select to authenticated
  using (((user_id = ( SELECT auth.uid() AS uid)) OR util.is_admin(tenant_id)));
create policy movimentacao_read on app.workforce_movement
  for select to authenticated
  using ((util.is_admin(tenant_id) OR ((unit_id IS NOT NULL) AND util.can_see_unit(unit_id))));

-- triggers
CREATE TRIGGER trg_validate_alert_payload BEFORE INSERT OR UPDATE ON app.alert_queue FOR EACH ROW EXECUTE FUNCTION util.validate_alert_payload();
CREATE TRIGGER trg_validate_alert_template BEFORE INSERT OR UPDATE ON app.alert_queue FOR EACH ROW EXECUTE FUNCTION util.validate_alert_template();
CREATE TRIGGER trg_validate_alert_target BEFORE INSERT OR UPDATE ON app.alert_rule_target FOR EACH ROW EXECUTE FUNCTION util.validate_alert_target();
CREATE TRIGGER trg_atualizado_em BEFORE UPDATE ON app.batida_marcacao FOR EACH ROW EXECUTE FUNCTION util.touch_atualizado_em();
CREATE TRIGGER trg_atualizado_em BEFORE UPDATE ON app.cursor_sincronizacao FOR EACH ROW EXECUTE FUNCTION util.touch_atualizado_em();
CREATE TRIGGER trg_updated_at BEFORE UPDATE ON app.deviation_event FOR EACH ROW EXECUTE FUNCTION util.touch_updated_at();
CREATE TRIGGER trg_updated_at BEFORE UPDATE ON app.employee FOR EACH ROW EXECUTE FUNCTION util.touch_updated_at();
CREATE TRIGGER trg_updated_at BEFORE UPDATE ON app.employee_pii FOR EACH ROW EXECUTE FUNCTION util.touch_updated_at();
CREATE TRIGGER trg_updated_at BEFORE UPDATE ON app.integration_secret FOR EACH ROW EXECUTE FUNCTION util.touch_updated_at();
CREATE TRIGGER trg_validate_template_body BEFORE INSERT OR UPDATE ON app.message_template FOR EACH ROW EXECUTE FUNCTION util.validate_template_body();

-- grants de schema
revoke all on schema app from public, anon, authenticated, service_role;
grant usage on schema app to authenticated;
grant usage on schema app to service_role;
revoke all on schema public from public, anon, authenticated, service_role;
grant usage on schema public to anon;
grant usage on schema public to authenticated;
grant usage on schema public to service_role;
revoke all on schema secullum from public, anon, authenticated, service_role;
grant usage on schema secullum to service_role;
revoke all on schema util from public, anon, authenticated, service_role;
grant usage on schema util to authenticated;
grant usage on schema util to service_role;

-- grants
revoke all on table app.agreement_installment from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.agreement_installment to postgres;
grant delete, insert, select, update on table app.agreement_installment to authenticated;
revoke all on table app.ai_query from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.ai_query to postgres;
grant select on table app.ai_query to authenticated;
revoke all on table app.alert_queue from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.alert_queue to postgres;
grant select on table app.alert_queue to authenticated;
revoke all on table app.alert_rule from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.alert_rule to postgres;
grant delete, insert, select, update on table app.alert_rule to authenticated;
revoke all on table app.alert_rule_target from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.alert_rule_target to postgres;
grant delete, insert, select, update on table app.alert_rule_target to authenticated;
revoke all on table app.alert_sent from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.alert_sent to postgres;
grant select on table app.alert_sent to authenticated;
revoke all on table app.audit_log from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.audit_log to postgres;
grant select on table app.audit_log to authenticated;
revoke all on table app.batida_marcacao from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.batida_marcacao to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.batida_marcacao to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.batida_marcacao to service_role;
revoke all on table app.company from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.company to postgres;
grant delete, insert, select, update on table app.company to authenticated;
revoke all on table app.contact from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.contact to postgres;
grant delete, insert, select, update on table app.contact to authenticated;
revoke all on table app.cost_center from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.cost_center to postgres;
grant delete, insert, select, update on table app.cost_center to authenticated;
revoke all on table app.cursor_sincronizacao from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.cursor_sincronizacao to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.cursor_sincronizacao to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.cursor_sincronizacao to service_role;
revoke all on table app.department from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.department to postgres;
grant delete, insert, select, update on table app.department to authenticated;
revoke all on table app.detection_run from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.detection_run to postgres;
grant select on table app.detection_run to authenticated;
revoke all on table app.deviation_event from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.deviation_event to postgres;
grant select, update on table app.deviation_event to authenticated;
revoke all on table app.deviation_type from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.deviation_type to postgres;
grant select on table app.deviation_type to authenticated;
revoke all on table app.deviation_type_config from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.deviation_type_config to postgres;
grant delete, insert, select, update on table app.deviation_type_config to authenticated;
revoke all on table app.disciplinary_event from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.disciplinary_event to postgres;
grant insert, select, update on table app.disciplinary_event to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.disciplinary_event to service_role;
revoke all on table app.document from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.document to postgres;
grant delete, insert, select, update on table app.document to authenticated;
revoke all on table app.document_type from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.document_type to postgres;
grant delete, insert, select, update on table app.document_type to authenticated;
revoke all on table app.domain_permission from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.domain_permission to postgres;
grant select on table app.domain_permission to authenticated;
revoke all on table app.employee from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.employee to postgres;
grant delete, insert, select, update on table app.employee to authenticated;
revoke all on table app.employee_compensation from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.employee_compensation to postgres;
grant delete, insert, select, update on table app.employee_compensation to authenticated;
revoke all on table app.employee_pii from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.employee_pii to postgres;
grant delete, insert, select, update on table app.employee_pii to authenticated;
revoke all on table app.employee_position from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.employee_position to postgres;
grant delete, insert, select, update on table app.employee_position to authenticated;
revoke all on table app.empresa_evento_status from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.empresa_evento_status to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.empresa_evento_status to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.empresa_evento_status to service_role;
revoke all on table app.expected_workday from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.expected_workday to postgres;
grant select on table app.expected_workday to authenticated;
revoke all on table app.file_import from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.file_import to postgres;
grant insert, select on table app.file_import to authenticated;
revoke all on table app.financial_agreement from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.financial_agreement to postgres;
grant delete, insert, select, update on table app.financial_agreement to authenticated;
revoke all on table app.financial_threshold from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.financial_threshold to postgres;
grant delete, insert, select, update on table app.financial_threshold to authenticated;
revoke all on table app.funcionario_evento_status from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.funcionario_evento_status to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.funcionario_evento_status to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.funcionario_evento_status to service_role;
revoke all on table app.integration from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.integration to postgres;
grant delete, insert, select, update on table app.integration to authenticated;
revoke all on table app.integration_secret from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.integration_secret to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.integration_secret to service_role;
revoke all on table app.job_execucao from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.job_execucao to postgres;
grant delete, insert, select, update on table app.job_execucao to service_role;
revoke all on table app.justification from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.justification to postgres;
grant insert, select on table app.justification to authenticated;
revoke all on table app.leave_period from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.leave_period to postgres;
grant select on table app.leave_period to authenticated;
revoke all on table app.manager from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.manager to postgres;
grant select on table app.manager to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.manager to service_role;
revoke all on table app.message_template from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.message_template to postgres;
grant delete, insert, select, update on table app.message_template to authenticated;
revoke all on table app.metric from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.metric to postgres;
grant select on table app.metric to authenticated;
revoke all on table app.mv_deviation_day from public, anon, authenticated, service_role;
revoke all on table app.occupational_exam from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.occupational_exam to postgres;
grant delete, insert, select, update on table app.occupational_exam to authenticated;
revoke all on table app.payroll_charge from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.payroll_charge to postgres;
grant select on table app.payroll_charge to authenticated;
revoke all on table app.payroll_entry from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.payroll_entry to postgres;
grant select on table app.payroll_entry to authenticated;
revoke all on table app.payroll_event_map from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.payroll_event_map to postgres;
grant delete, insert, select, update on table app.payroll_event_map to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.payroll_event_map to service_role;
revoke all on table app.payroll_period from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.payroll_period to postgres;
grant select on table app.payroll_period to authenticated;
revoke all on table app.report_cycle from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.report_cycle to postgres;
grant select on table app.report_cycle to authenticated;
revoke all on table app.schedule_rotation_map from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.schedule_rotation_map to postgres;
grant delete, insert, select, update on table app.schedule_rotation_map to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.schedule_rotation_map to service_role;
revoke all on table app.sync_run from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.sync_run to postgres;
grant select on table app.sync_run to authenticated;
revoke all on table app.tenant from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.tenant to postgres;
grant select on table app.tenant to authenticated;
revoke all on table app.tenant_member from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.tenant_member to postgres;
grant delete, insert, select, update on table app.tenant_member to authenticated;
revoke all on table app.unit from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.unit to postgres;
grant delete, insert, select, update on table app.unit to authenticated;
revoke all on table app.unit_responsible from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.unit_responsible to postgres;
grant delete, insert, select, update on table app.unit_responsible to authenticated;
revoke all on table app.unit_secullum_map from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.unit_secullum_map to postgres;
grant delete, insert, select, update on table app.unit_secullum_map to authenticated;
revoke all on table app.user_scope from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.user_scope to postgres;
grant delete, insert, select, update on table app.user_scope to authenticated;
revoke all on table app.workforce_movement from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table app.workforce_movement to postgres;
grant select on table app.workforce_movement to authenticated;
revoke all on table public.vw_deviation_by_employee_day from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_deviation_by_employee_day to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_deviation_by_employee_day to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_deviation_by_employee_day to service_role;
revoke all on table public.vw_deviation_daily_trend from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_deviation_daily_trend to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_deviation_daily_trend to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_deviation_daily_trend to service_role;
revoke all on table public.vw_deviation_event from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_deviation_event to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_deviation_event to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_deviation_event to service_role;
revoke all on table public.vw_deviation_summary_by_unit from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_deviation_summary_by_unit to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_deviation_summary_by_unit to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_deviation_summary_by_unit to service_role;
revoke all on table public.vw_document_expiry from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_document_expiry to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_document_expiry to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_document_expiry to service_role;
revoke all on table public.vw_employee from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_employee to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_employee to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_employee to service_role;
revoke all on table public.vw_payroll_summary from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_payroll_summary to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_payroll_summary to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_payroll_summary to service_role;
revoke all on table public.vw_unit from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_unit to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_unit to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.vw_unit to service_role;
revoke all on table secullum."Batida" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Batida" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Batida" to service_role;
revoke all on table secullum."BatidaFonteDados" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."BatidaFonteDados" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."BatidaFonteDados" to service_role;
revoke all on table secullum."Cidade" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Cidade" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Cidade" to service_role;
revoke all on table secullum."Departamento" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Departamento" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Departamento" to service_role;
revoke all on table secullum."Empresa" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Empresa" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Empresa" to service_role;
revoke all on table secullum."Estrutura" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Estrutura" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Estrutura" to service_role;
revoke all on table secullum."Funcao" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Funcao" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Funcao" to service_role;
revoke all on table secullum."Funcionario" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Funcionario" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Funcionario" to service_role;
revoke all on table secullum."FuncionarioAfastamento" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."FuncionarioAfastamento" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."FuncionarioAfastamento" to service_role;
revoke all on table secullum."FuncionarioCentroCusto" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."FuncionarioCentroCusto" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."FuncionarioCentroCusto" to service_role;
revoke all on table secullum."Horario" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Horario" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Horario" to service_role;
revoke all on table secullum."HorarioDescanso" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioDescanso" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioDescanso" to service_role;
revoke all on table secullum."HorarioDescansoFaixaItem" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioDescansoFaixaItem" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioDescansoFaixaItem" to service_role;
revoke all on table secullum."HorarioDia" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioDia" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioDia" to service_role;
revoke all on table secullum."HorarioExtras" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioExtras" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioExtras" to service_role;
revoke all on table secullum."HorarioFaixasExtras" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioFaixasExtras" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioFaixasExtras" to service_role;
revoke all on table secullum."HorarioFaixasExtrasItem" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioFaixasExtrasItem" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioFaixasExtrasItem" to service_role;
revoke all on table secullum."HorarioToleranciaEspecifica" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioToleranciaEspecifica" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioToleranciaEspecifica" to service_role;
revoke all on table secullum."HorarioToleranciaEspecificaItem" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioToleranciaEspecificaItem" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioToleranciaEspecificaItem" to service_role;
revoke all on table secullum."HorariosOpcoes" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorariosOpcoes" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorariosOpcoes" to service_role;
revoke all on table secullum.departamento_gestor from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum.departamento_gestor to postgres;
grant insert, select, update on table secullum.departamento_gestor to service_role;
revoke all on table secullum.estrutura_evento_titular from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum.estrutura_evento_titular to postgres;
grant insert, select on table secullum.estrutura_evento_titular to service_role;
revoke all on function app.refresh_dashboard() from public, anon, authenticated, service_role;
grant execute on function app.refresh_dashboard() to postgres;
grant execute on function app.refresh_dashboard() to service_role;
revoke all on function app.revoke_deviation(p_id uuid, p_reason text, p_novo_status text) from public, anon, authenticated, service_role;
revoke all on function public.fn_data_freshness(p_stale_after_minutes integer) from public, anon, authenticated, service_role;
grant execute on function public.fn_data_freshness(p_stale_after_minutes integer) to postgres;
grant execute on function public.fn_data_freshness(p_stale_after_minutes integer) to authenticated;
grant execute on function public.fn_data_freshness(p_stale_after_minutes integer) to service_role;
revoke all on function public.fn_detection_health(p_backfill_max_age_hours integer) from public, anon, authenticated, service_role;
grant execute on function public.fn_detection_health(p_backfill_max_age_hours integer) to postgres;
grant execute on function public.fn_detection_health(p_backfill_max_age_hours integer) to authenticated;
grant execute on function public.fn_detection_health(p_backfill_max_age_hours integer) to service_role;
revoke all on function public.fn_kpi_period(p_de date, p_ate date, p_company_id uuid, p_unit_id uuid, p_department_id uuid, p_manager_id uuid) from public, anon, authenticated, service_role;
grant execute on function public.fn_kpi_period(p_de date, p_ate date, p_company_id uuid, p_unit_id uuid, p_department_id uuid, p_manager_id uuid) to postgres;
grant execute on function public.fn_kpi_period(p_de date, p_ate date, p_company_id uuid, p_unit_id uuid, p_department_id uuid, p_manager_id uuid) to authenticated;
grant execute on function public.fn_kpi_period(p_de date, p_ate date, p_company_id uuid, p_unit_id uuid, p_department_id uuid, p_manager_id uuid) to service_role;
revoke all on function public.fn_pending_justification(p_de date, p_ate date, p_unit_id uuid, p_department_id uuid, p_manager_id uuid) from public, anon, authenticated, service_role;
grant execute on function public.fn_pending_justification(p_de date, p_ate date, p_unit_id uuid, p_department_id uuid, p_manager_id uuid) to postgres;
grant execute on function public.fn_pending_justification(p_de date, p_ate date, p_unit_id uuid, p_department_id uuid, p_manager_id uuid) to authenticated;
grant execute on function public.fn_pending_justification(p_de date, p_ate date, p_unit_id uuid, p_department_id uuid, p_manager_id uuid) to service_role;
revoke all on function public.fn_ranking_by_employee(p_de date, p_ate date, p_company_id uuid, p_unit_id uuid, p_limite integer, p_department_id uuid, p_manager_id uuid) from public, anon, authenticated, service_role;
grant execute on function public.fn_ranking_by_employee(p_de date, p_ate date, p_company_id uuid, p_unit_id uuid, p_limite integer, p_department_id uuid, p_manager_id uuid) to postgres;
grant execute on function public.fn_ranking_by_employee(p_de date, p_ate date, p_company_id uuid, p_unit_id uuid, p_limite integer, p_department_id uuid, p_manager_id uuid) to authenticated;
grant execute on function public.fn_ranking_by_employee(p_de date, p_ate date, p_company_id uuid, p_unit_id uuid, p_limite integer, p_department_id uuid, p_manager_id uuid) to service_role;
revoke all on function public.fn_ranking_by_manager(p_de date, p_ate date, p_company_id uuid, p_unit_id uuid, p_limite integer, p_department_id uuid) from public, anon, authenticated, service_role;
grant execute on function public.fn_ranking_by_manager(p_de date, p_ate date, p_company_id uuid, p_unit_id uuid, p_limite integer, p_department_id uuid) to postgres;
grant execute on function public.fn_ranking_by_manager(p_de date, p_ate date, p_company_id uuid, p_unit_id uuid, p_limite integer, p_department_id uuid) to authenticated;
grant execute on function public.fn_ranking_by_manager(p_de date, p_ate date, p_company_id uuid, p_unit_id uuid, p_limite integer, p_department_id uuid) to service_role;
revoke all on function public.fn_ranking_by_unit(p_de date, p_ate date, p_company_id uuid, p_limite integer, p_department_id uuid, p_manager_id uuid) from public, anon, authenticated, service_role;
grant execute on function public.fn_ranking_by_unit(p_de date, p_ate date, p_company_id uuid, p_limite integer, p_department_id uuid, p_manager_id uuid) to postgres;
grant execute on function public.fn_ranking_by_unit(p_de date, p_ate date, p_company_id uuid, p_limite integer, p_department_id uuid, p_manager_id uuid) to authenticated;
grant execute on function public.fn_ranking_by_unit(p_de date, p_ate date, p_company_id uuid, p_limite integer, p_department_id uuid, p_manager_id uuid) to service_role;
revoke all on function public.fn_recurrence(p_de date, p_ate date, p_min_dias integer, p_unit_id uuid, p_department_id uuid, p_manager_id uuid) from public, anon, authenticated, service_role;
grant execute on function public.fn_recurrence(p_de date, p_ate date, p_min_dias integer, p_unit_id uuid, p_department_id uuid, p_manager_id uuid) to postgres;
grant execute on function public.fn_recurrence(p_de date, p_ate date, p_min_dias integer, p_unit_id uuid, p_department_id uuid, p_manager_id uuid) to authenticated;
grant execute on function public.fn_recurrence(p_de date, p_ate date, p_min_dias integer, p_unit_id uuid, p_department_id uuid, p_manager_id uuid) to service_role;
revoke all on function public.fn_whatsapp_readiness() from public, anon, authenticated, service_role;
grant execute on function public.fn_whatsapp_readiness() to postgres;
grant execute on function public.fn_whatsapp_readiness() to authenticated;
grant execute on function public.fn_whatsapp_readiness() to service_role;
revoke all on function public.rls_auto_enable() from public, anon, authenticated, service_role;
grant execute on function public.rls_auto_enable() to postgres;
grant execute on function public.rls_auto_enable() to authenticated;
grant execute on function public.rls_auto_enable() to service_role;
revoke all on function secullum.departamento_gestor_transition(p_close_id uuid, p_departamento_id uuid, p_estrutura_id uuid, p_departamento_id_secullum integer, p_estrutura_id_secullum integer, p_funcionarios_observados integer) from public, anon, authenticated, service_role;
grant execute on function secullum.departamento_gestor_transition(p_close_id uuid, p_departamento_id uuid, p_estrutura_id uuid, p_departamento_id_secullum integer, p_estrutura_id_secullum integer, p_funcionarios_observados integer) to postgres;
grant execute on function secullum.departamento_gestor_transition(p_close_id uuid, p_departamento_id uuid, p_estrutura_id uuid, p_departamento_id_secullum integer, p_estrutura_id_secullum integer, p_funcionarios_observados integer) to service_role;
revoke all on function util.block_table_in_public() from public, anon, authenticated, service_role;
grant execute on function util.block_table_in_public() to postgres;
revoke all on function util.can_see_company(p_empresa_id uuid) from public, anon, authenticated, service_role;
grant execute on function util.can_see_company(p_empresa_id uuid) to postgres;
grant execute on function util.can_see_company(p_empresa_id uuid) to authenticated;
grant execute on function util.can_see_company(p_empresa_id uuid) to service_role;
revoke all on function util.can_see_domain(p_tenant_id uuid, p_dominio app.sensitive_domain) from public, anon, authenticated, service_role;
grant execute on function util.can_see_domain(p_tenant_id uuid, p_dominio app.sensitive_domain) to postgres;
grant execute on function util.can_see_domain(p_tenant_id uuid, p_dominio app.sensitive_domain) to authenticated;
grant execute on function util.can_see_domain(p_tenant_id uuid, p_dominio app.sensitive_domain) to service_role;
revoke all on function util.can_see_employee(p_colaborador_id uuid) from public, anon, authenticated, service_role;
grant execute on function util.can_see_employee(p_colaborador_id uuid) to postgres;
grant execute on function util.can_see_employee(p_colaborador_id uuid) to authenticated;
grant execute on function util.can_see_employee(p_colaborador_id uuid) to service_role;
revoke all on function util.can_see_unit(p_unidade_id uuid) from public, anon, authenticated, service_role;
grant execute on function util.can_see_unit(p_unidade_id uuid) to postgres;
grant execute on function util.can_see_unit(p_unidade_id uuid) to authenticated;
grant execute on function util.can_see_unit(p_unidade_id uuid) to service_role;
revoke all on function util.has_tenant(p_tenant_id uuid) from public, anon, authenticated, service_role;
grant execute on function util.has_tenant(p_tenant_id uuid) to postgres;
grant execute on function util.has_tenant(p_tenant_id uuid) to authenticated;
grant execute on function util.has_tenant(p_tenant_id uuid) to service_role;
revoke all on function util.is_admin(p_tenant_id uuid) from public, anon, authenticated, service_role;
grant execute on function util.is_admin(p_tenant_id uuid) to postgres;
grant execute on function util.is_admin(p_tenant_id uuid) to authenticated;
grant execute on function util.is_admin(p_tenant_id uuid) to service_role;
revoke all on function util.lock_down_new_function() from public, anon, authenticated, service_role;
grant execute on function util.lock_down_new_function() to postgres;
revoke all on function util.roles_in_tenant(p_tenant_id uuid) from public, anon, authenticated, service_role;
grant execute on function util.roles_in_tenant(p_tenant_id uuid) to postgres;
grant execute on function util.roles_in_tenant(p_tenant_id uuid) to authenticated;
grant execute on function util.roles_in_tenant(p_tenant_id uuid) to service_role;
revoke all on function util.touch_atualizado_em() from public, anon, authenticated, service_role;
grant execute on function util.touch_atualizado_em() to postgres;
revoke all on function util.touch_updated_at() from public, anon, authenticated, service_role;
grant execute on function util.touch_updated_at() to postgres;
revoke all on function util.user_tenants() from public, anon, authenticated, service_role;
grant execute on function util.user_tenants() to postgres;
grant execute on function util.user_tenants() to authenticated;
grant execute on function util.user_tenants() to service_role;
revoke all on function util.validate_alert_payload() from public, anon, authenticated, service_role;
grant execute on function util.validate_alert_payload() to postgres;
revoke all on function util.validate_alert_target() from public, anon, authenticated, service_role;
grant execute on function util.validate_alert_target() to postgres;
revoke all on function util.validate_alert_template() from public, anon, authenticated, service_role;
grant execute on function util.validate_alert_template() to postgres;
revoke all on function util.validate_template_body() from public, anon, authenticated, service_role;
grant execute on function util.validate_template_body() to postgres;

-- privilégios default (o que uma tabela nova já nasce podendo)
alter default privileges for role postgres in schema public revoke all on sequences from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema public grant select, update, usage on sequences to authenticated;
alter default privileges for role postgres in schema public grant select, update, usage on sequences to service_role;
alter default privileges for role postgres in schema public revoke all on functions from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema public grant execute on functions to authenticated;
alter default privileges for role postgres in schema public grant execute on functions to service_role;
alter default privileges for role postgres in schema public revoke all on tables from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema public grant delete, insert, maintain, references, select, trigger, truncate, update on tables to authenticated;
alter default privileges for role postgres in schema public grant delete, insert, maintain, references, select, trigger, truncate, update on tables to service_role;
alter default privileges for role postgres in schema storage revoke all on sequences from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema storage grant select, update, usage on sequences to anon;
alter default privileges for role postgres in schema storage grant select, update, usage on sequences to authenticated;
alter default privileges for role postgres in schema storage grant select, update, usage on sequences to service_role;
alter default privileges for role postgres in schema storage revoke all on functions from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema storage grant execute on functions to anon;
alter default privileges for role postgres in schema storage grant execute on functions to authenticated;
alter default privileges for role postgres in schema storage grant execute on functions to service_role;
alter default privileges for role postgres in schema storage revoke all on tables from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema storage grant delete, insert, maintain, references, select, trigger, truncate, update on tables to anon;
alter default privileges for role postgres in schema storage grant delete, insert, maintain, references, select, trigger, truncate, update on tables to authenticated;
alter default privileges for role postgres in schema storage grant delete, insert, maintain, references, select, trigger, truncate, update on tables to service_role;

-- comentários de coluna
comment on column app.ai_query.model is 'Id do modelo que respondeu, da allowlist de operax/agente/agente.py. Sem ele os contadores de token não viram dinheiro, que é para o que eles existem.';
comment on column app.ai_query.output_tokens is 'Custo de LLM é variável e sai da sustentação mensal. Sem medir, não dá para saber se a margem virou negativa.';
comment on column app.alert_queue.idempotency_key is 'Reprocessar o mesmo período não reenvia. Consuma a fila com SELECT ... FOR UPDATE SKIP LOCKED.';
comment on column app.alert_rule.active is 'Nasce false de propósito. Regra só liga depois de homologada com o cliente e validada pelo jurídico/RH.';
comment on column app.alert_rule.template_code is 'Null = alerta de e-mail ou resumo livre. Para WhatsApp com provedor oficial é obrigatório: sem template aprovado a Meta recusa a mensagem.';
comment on column app.alert_sent.cost_cents is 'Cloud API cobra por mensagem. Sem esse campo não dá para saber se a sustentação mensal está com margem negativa.';
comment on column app.batida_marcacao."EquipId" is 'Campo `EquipIdEntradaN`/`EquipIdSaidaN`, des-posicionalizado. Id do equipamento/relogio que originou a coluna. Inteiro bruto, sem FK — o cadastro de equipamentos do Secullum nao e consumido.';
comment on column app.batida_marcacao."FonteDadosId" is 'Campo `FonteDadosIdEntradaN`/`SaidaN`, des-posicionalizado (o escalar do payload). ATRIBUTO, indice NAO-UNICO: confirmado em dados reais que uma coluna preenchida, inclusive vinda de relogio fisico ("EquipId" presente), pode ter este id nulo. Chave que as vezes e nula nao e chave.';
comment on column app.batida_marcacao."Memoria" is 'Campo `MemoriaEntradaN`/`MemoriaSaidaN`, DES-POSICIONALIZADO (o sufixo virou tipo_coluna/indice_coluna). Horario PREVISTO daquele dia, atalho de diagnostico. ⛔ NAO e a fonte da verdade do previsto nem da tolerancia: isso e "HorarioDia". Inverter essa ordem faz o sistema divergir do calculo oficial de folha. ✅ E o sinal de BATIDA FALTANTE quando "Memoria" existe e `hora` e nula.';
comment on column app.batida_marcacao.data is 'NOSSA, desnormalizada de "Batida"."Data" (por isso minuscula). Mesma finalidade de funcionario_id.';
comment on column app.batida_marcacao.desconsiderada is 'NOSSO (derivado de "BatidaFonteDados"."Tipo" = 3, Desconsiderado). A marcacao E persistida (para o reprocessamento nao oscilar e por rastreabilidade), mas nao gera desvio.';
comment on column app.batida_marcacao.funcionario_id is 'NOSSA FK, desnormalizada a partir de "Batida" de proposito (mesmo racional de "Funcionario".empresa_id): evita um join no caminho quente do relatorio (Sprint 3) e do dashboard (Sprint 4). Coerencia com "Batida" e responsabilidade da mesma transacao de escrita — so o job escreve aqui.';
comment on column app.batida_marcacao.hora is 'NOSSO (derivado). Preenchida SOMENTE quando valor_bruto e "HH:mm". Hora LOCAL (America/Sao_Paulo), armazenada sem conversao de fuso. Mutuamente exclusiva com status_rotulo. ⚠️ Linha com hora IS NULL NAO e batida: nao entra na deteccao e nao entra no denominador do KPI de batidas do dashboard.';
comment on column app.batida_marcacao.tipo_coluna is 'NOSSO. Valores ''Entrada'' | ''Saida'' — grafados exatamente como o PREFIXO da coluna no payload, de modo que tipo_coluna || indice_coluna reconstroi o nome literal do campo ("Entrada3").';
comment on column app.batida_marcacao.valor_bruto is 'NOSSO. Conteudo literal da coluna `EntradaN`/`SaidaN`, preservado como veio. Tres estados possiveis: "HH:mm" (batida), TEXTO DE STATUS (ex.: "Ferias") ou null. E a unica coluna que garante fidelidade ao payload — `hora` e `status_rotulo` sao interpretacoes dela.';
comment on column app.cursor_sincronizacao.atualizado_em is 'Momento da ultima atualizacao do cursor.';
comment on column app.cursor_sincronizacao.chave is 'Identificador logico do cursor (ex.: batidas_ultima_data_sincronizada).';
comment on column app.cursor_sincronizacao.valor is 'Valor do cursor em texto. Para /Batidas guarda a ultima DATA coberta pela janela deslizante, nao um ID.';
comment on column app.detection_run.scope is 'incremental = current day, after each sync (48x/day). backfill = 7-day retroactive window, once a day, off-peak.';
comment on column app.deviation_event.minutes is 'Assinado. Soma direta responde "minutos líquidos"; abs() responde "minutos de desvio". Nunca chamar de hora extra.';
comment on column app.deviation_event.reference_date is 'Data do fato. Dashboard SEMPRE filtra por ela. Relatório agrupa por ciclo — quando um desvio é detectado tarde, o relatório declara "inclui N ocorrências de dias anteriores".';
comment on column app.deviation_type_config.requires_justification is 'Nasce false, como triggers_alert. Política por cliente: atraso pode exigir explicação onde marcação incompleta não exige. Sem isto, "pendente de justificativa" não tem de onde sair — todo desvio pareceria pendente, ou nenhum.';
comment on column app.disciplinary_event.summary is 'Texto livre sobre uma pessoa, no domínio mais sensível dos quatro. NUNCA em view de public.';
comment on column app.employee.company_id is 'Sempre pelo caminho Funcionario->Empresa. NUNCA derivar de Departamento->Empresa (26% divergem).';
comment on column app.employee.exception_tracking is 'Fora do motor de detecção POR DECISÃO — "ponto por exceção", supervisão. Nasce false: quem aparece fora da medição sem alguém ter tirado é quem ninguém decidiu não medir. Quem está aqui não materializa jornada esperada e é contado à parte no monitor, separado de `unrostered`, que é falha de cobertura e tem a mesma aparência.';
comment on column app.employee.hr_code is 'ID RH do cliente. Chave ALTERNATIVA — nunca composta com a matrícula: cada uma identifica sozinha, e divergência entre elas é erro de linha no import. Anulável de propósito: fica vazia até o template de vínculo voltar preenchido.';
comment on column app.employee.manager_id is 'A quem esta pessoa responde, promovido de `Funcionario.EstruturaId`. NÃO confundir com `manager_employee_id`, que aponta para um `app.employee` e continua sem fonte: o espelho diz o NOME do gestor, não qual colaborador ele é.';
comment on column app.empresa_evento_status.detectado_em is 'Quando ESTA sincronizacao detectou a mudanca. NAO e quando a empresa foi desativada no Secullum (essa informacao nao existe na API). Erro >= intervalo entre execucoes do job; ilimitado se o job esteve parado.';
comment on column app.empresa_evento_status.origem is 'secullum_sync (job cadastral) | backfill (esta migration, para linhas ja existentes) | manual.';
comment on column app.empresa_evento_status.tipo_evento is 'baseline (primeira vez que a empresa foi observada; previous_active nulo) | deactivated | reactivated.';
comment on column app.expected_workday.confidence is 'Escala 12x36 inferida a partir do Horario do Secullum costuma ficar abaixo de 100. Linha com confianca baixa NÃO deve gerar alerta automático.';
comment on column app.financial_agreement.document_id is 'NOT NULL de propósito: desconto sem autorização documentada não se registra.';
comment on column app.funcionario_evento_status.data_evento is 'Data REAL do Secullum (`Admissao` em admission, `Demissao` em termination). NULL quando o evento nao tem data de origem. Para reconstruir estado historico: coalesce(data_evento, detectado_em::date).';
comment on column app.funcionario_evento_status.detectado_em is 'Quando a sincronizacao percebeu a mudanca. Pode ser POSTERIOR a event_date — ex.: desligamento com Demissao no dia 01 so detectado na execucao do dia 02. Isso e esperado.';
comment on column app.funcionario_evento_status.origem is 'secullum_sync (job cadastral) | backfill (esta migration, para linhas ja existentes) | manual.';
comment on column app.funcionario_evento_status.tipo_evento is 'baseline (primeira observacao) | admission (passou a ativo por admissao) | termination (passou a inativo por demissao) | reactivation (voltou a ativo sem nova admissao, ex.: Demissao corrigida para null) | date_correction (Admissao/Demissao mudou sem virar o status, inclusive desligamento programado para data futura).';
comment on column app.integration.provider is 'meta_cloud = API oficial da Meta, exige template aprovado e verificação de negócio. z_api e uazapi = não oficiais, baseados em QR/WhatsApp Web: dispensam template, mas o número do cliente pode ser banido sem recurso.';
comment on column app.job_execucao.erro is 'Somente error.message. Nunca payload, nunca linha de banco, nunca stack com dado interpolado.';
comment on column app.job_execucao.host is 'vercel / edge_function — comparação de contadores durante a transição do ADR-016.';
comment on column app.job_execucao.job is 'sync_cadastro / sync_batidas / deteccao / relatorio.';
comment on column app.job_execucao.resumo is 'Somente contadores e avisos agregados. Nunca PII, nunca payload bruto (docs/06-seguranca-lgpd.md).';
comment on column app.justification.status is 'Default accepted de propósito: até esta migration uma linha aqui ERA a resposta final, e nenhuma justificativa já escrita pode virar pendente retroativamente. Não existe tela que rejeite — enquanto não existir, "aceita" e "escrita" são a mesma coisa.';
comment on column app.manager.name is 'Vem de "Estrutura"."Descricao". Nome de pessoa, e é assim que o Secullum o guarda.';
comment on column app.message_template.category is 'utility para alerta operacional. Categoria errada faz a Meta reprovar o template ou cobrar como marketing — cerca de 9x mais caro no Brasil.';
comment on column app.schedule_rotation_map.anchor_date is 'Um dia em que o ciclo trabalha. O dia é de trabalho quando (data - âncora) mod ciclo é zero. A âncora pode ficar no meio da janela: o resto negativo do Postgres (-1 mod 2 = -1) não muda ESTE teste, porque só o zero decide e zero não tem sinal. Quem for calcular a POSIÇÃO no ciclo, e não só se é dia de trabalho, aí sim precisa normalizar.';
comment on column app.schedule_rotation_map.expected_exit is 'Pode ser MENOR que expected_entry: é assim que um turno noturno se declara, do mesmo jeito que "HorarioDia" o declara. Quem trata a virada é regras.py.';
comment on column app.sync_run.records_skipped is 'Registros lidos da origem que não viraram linha — tipicamente correlação quebrada (FuncionarioId sem colaborador local). Lido = escrito + pulado; sem esta coluna, uma execução que pulou tudo é indistinguível de uma janela vazia.';
comment on column app.sync_run.scope is 'incremental = janela curta, a cada 15 min (batidas) / 30 (cadastro). backfill = 7 dias, 1x/dia, fora de pico. As mesmas duas palavras de app.detection_run.scope (migration 13), de propósito.';
comment on column secullum."Batida"."Ajuste" is '[VALIDAR — Postman] Tipo real desconhecido (o cadastro de Justificativas trata Ajuste/Abono2..4 como boolean de abono automatico; no cartao ponto sao valores HH:mm). Modelado como TEXT para preservar o valor bruto sem risco de conversao errada. Mesma ressalva para "Abono2"/"Abono3"/"Abono4".';
comment on column secullum."Batida"."BatidaId" is 'Campo `Id` do topo do registro de /Batidas (forma qualificada, ver ADR-012). ATRIBUTO com indice NAO-UNICO — NAO e a chave de idempotencia (alteracao (A) ao ADR-007). A chave e (funcionario_id, "Data"), unica por construcao. Divergencia entre os dois (mesmo par funcionario/data reaparecendo com outro Id) deve ser LOGADA como anomalia, nunca contornada em silencio.';
comment on column secullum."Batida"."Data" is 'Campo `Data`. ⛔ Parsing OBRIGATORIO pelos 10 PRIMEIROS CARACTERES da string ("yyyy-MM-ddT00:00:00"). Nunca via new Date(...)/toISOString(): a Edge Function roda em UTC e a conversao ingenua desloca um dia. A parte de hora do campo e sempre 00:00:00 e nao tem significado.';
comment on column secullum."Batida"."FuncionarioId" is 'Campo `FuncionarioId` do payload — INTEIRO do Secullum, guardado como veio. E a chave de juncao com "Funcionario"."FuncionarioId". ⚠️ A FK real e funcionario_id (uuid), ao lado.';
comment on column secullum."Batida"."NBanco" is 'Campo `NBanco` (banco de horas do dia). ✅ Sob a nomenclatura literal (ADR-012) a abreviacao opaca deixou de ser um problema de decisao nossa: e simplesmente o nome que o Secullum usa.';
comment on column secullum."Batida"."Observacoes" is '⚠️ TEXTO LIVRE. Ate 2026-08-12 era explicitamente NAO sincronizado por LGPD (podia carregar motivo de afastamento = dado de saude). Passa a ser persistido por decisao expressa do Owner (ADR-011). ⛔ Nunca exibir em relatorio ao gestor, nunca logar. A base legal para reter isto esta PENDENTE.';
comment on column secullum."Batida".status_dia_rotulo is 'DERIVADO POR NOS (minusculo — nao procure este campo no payload): preenchido pelo parser quando as colunas do dia carregam TEXTO DE STATUS (ex.: rotulo de afastamento) em vez de horas. Torna explicito no relatorio que o dia nao e "falta", e status. ⛔ NUNCA e fonte de periodo de afastamento — essa e "FuncionarioAfastamento" (ADR-010).';
comment on column secullum."BatidaFonteDados"."DataInclusao" is 'Campo `DataInclusao` — quando o registro entrou no Secullum. Diagnostico de batida lancada RETROATIVAMENTE, que invalida desvio ja detectado e possivelmente ja enviado no relatorio.';
comment on column secullum."BatidaFonteDados"."Nsr" is 'Numero Sequencial de Registro do equipamento. TEXT (nao numerico): e identificador, nao quantidade, e pode vir com zeros a esquerda.';
comment on column secullum."BatidaFonteDados"."Origem" is 'Campo `Origem` BRUTO (0..8 documentados). ⚠️ Origem = 11 JA APARECEU em producao e nao consta da documentacao oficial; significado ainda [DECISAO DO OWNER]. Por isso: sem CHECK, sem enum, sem significado presumido, job nunca falha. Logar uma vez por valor desconhecido distinto por execucao.';
comment on column secullum."BatidaFonteDados"."Tipo" is 'Campo `Tipo` BRUTO (Original=0, Manual=1, PreAssinalado=2, Desconsiderado=3). smallint SEM CHECK e SEM enum do Postgres: valor fora do documentado e persistido, tolerado e traduzido apenas na apresentacao.';
comment on column secullum."BatidaFonteDados".batida_id is 'NOSSA FK, desnormalizada a partir de batida_marcacao para permitir DELETE/consulta no escopo do dia inteiro sem join. Ambas as FKs sao ON DELETE CASCADE — expurgo por titular chega ate aqui.';
comment on column secullum."Cidade"."CidadeId" is 'Campo `Cidade.Id`. NULLABLE e SEM UNIQUE de proposito: o que se confirmou foi a FORMA do no, NAO a unicidade global do Id — que nunca foi verificada. Este projeto ja quebrou em producao duas vezes supondo unicidade global de id do Secullum. A chave de idempotencia e "Descricao".';
comment on column secullum."Departamento"."DepartamentoId" is 'Campo `Departamento.Id`. Chave de idempotencia, UNIQUE GLOBAL (ADR-008). O detector de colisao (unit_name_changed / unit_ref_name_conflict nos logs) continua sendo a rede de seguranca.';
comment on column secullum."Departamento"."Nfolha" is 'Campo `Departamento.Nfolha` (grafia literal confirmada em payload real: "Nfolha", f minusculo). Numero visivel na folha. ⚠️ Se algum identificador de Departamento se repetir entre empresas, o candidato natural e este, NAO "DepartamentoId" (ADR-008).';
comment on column secullum."Departamento".ativo is 'DERIVADO/FIXO POR NOS (minusculo): o Secullum NAO expoe status de Departamento ({ Id, Descricao, Nfolha }). Fica fixo em true e NAO ha tabela de historico. ⛔ Nao inferir desativacao pela ausencia do DepartamentoId no lote de /Funcionarios (ADR-009).';
comment on column secullum."Departamento".empresa_id is 'NOSSA FK (uuid). ⚠️ EMPRESA DE REFERENCIA, nao de propriedade (ADR-008): e a empresa do PRIMEIRO funcionario visto naquele departamento. ⛔ Agregacao por Empresa usa SEMPRE "Funcionario".empresa_id, NUNCA esta coluna.';
comment on column secullum."Empresa"."Desativada" is 'Campo `Empresa.Desativada` — ESTADO ATUAL, sem data. O Secullum nao informa QUANDO a empresa foi desativada; por isso empresa_evento_status so tem detectado_em. Escreva AQUI, nunca em `ativo`.';
comment on column secullum."Empresa"."DiaFechamentoPonto" is '[VALIDAR — Postman] Tipo assumido smallint (dia do mes). Mesma ressalva de "FechamentoPonto".';
comment on column secullum."Empresa"."Documento" is 'Campo `Documento` (CNPJ/CPF) — chave natural de idempotencia da sincronizacao, que e a chave que o proprio Secullum usa na rota Empresas.';
comment on column secullum."Empresa"."EmitiuAtestadoTecnico" is '[VALIDAR — Postman] Nao consta do manual oficial; reportado pelo Owner no payload real.';
comment on column secullum."Empresa"."EmpresaId" is 'Campo `Empresa.Id`. ATRIBUTO com indice NAO-UNICO: a chave de idempotencia continua sendo "Documento", que e a chave que o proprio Secullum usa na rota Empresas. Nao promover a UNIQUE sem evidencia.';
comment on column secullum."Empresa"."FechamentoPonto" is '[VALIDAR — Postman] Tipo assumido smallint (por analogia com `HorarioDia.Fechamento`, Inteiro 0..23). Se o payload real trouxer "HH:mm" ou boolean, abrir migration corretiva — nao forcar conversao no parser.';
comment on column secullum."Empresa"."Logotipo" is 'Logotipo em base 64. Volume irrelevante com poucas empresas. ⚠️ Se o cadastro crescer, avaliar deixar de sincronizar — nao ha consumidor de produto para ele hoje.';
comment on column secullum."Empresa"."NfolhaEmpresa" is '[VALIDAR — Postman] Grafia assumida por analogia com `Departamento.Nfolha` (confirmado com f minusculo). Vem do cadastro do manual, nao do no aninhado — pode nunca ser populado (ver aviso abaixo).';
comment on column secullum."Empresa"."ResponsavelNome" is '⚠️ Responsavel LEGAL da empresa. NAO e o gestor que recebe o relatorio consolidado — esse vive na tabela "Estrutura", vem de `Funcionario.Estrutura` e e outra pessoa. Foi para evitar exatamente esta confusao que a tabela de gestor NAO se chama `Responsavel`.';
comment on column secullum."Empresa"."TipoDocumento" is 'Enum BRUTO (0=CNPJ, 1=CPF, 2=Outros). smallint SEM CHECK — disciplina do projeto para enum do Secullum: valor desconhecido e persistido e tolerado, nunca derruba o job.';
comment on column secullum."Empresa"."UsaFechamentoDoPontoEspecifico" is '[VALIDAR — Postman] Nao consta do manual oficial (pag. 7-9); reportado pelo Owner no payload real.';
comment on column secullum."Empresa".ativo is 'DERIVADA POR NOS (minusculo) e GERADA PELO POSTGRES: coalesce(not "Desativada", true). ⛔ O upsert da sincronizacao NAO pode incluir esta coluna — o Postgres rejeita escrita em coluna gerada. Grave "Desativada". Ver o cabecalho da secao 4 desta migration e ADR-009.';
comment on column secullum."Empresa".cidade_id is 'NOSSA FK (uuid) -> "Cidade". ⚠️ NAO confundir com "CidadeId" (inteiro do Secullum), ao lado.';
comment on column secullum."Estrutura"."Descricao" is 'Campo `Estrutura.Descricao` — na pratica, o NOME do gestor responsavel. E o unico dado de identificacao do gestor que o Secullum fornece: e-mail e WhatsApp nao existem la.';
comment on column secullum."Estrutura"."EstruturaId" is 'Campo `Funcionario.EstruturaId` (= `Estrutura.Id`) — chave de idempotencia. Nunca resolvido subindo por "EstruturaPaiId".';
comment on column secullum."Estrutura"."EstruturaPaiId" is 'Campo `Estrutura.EstruturaPaiId`. Guardado so como contexto/diagnostico. 0 = raiz. ⏳ EM ABERTO (ADR-006): qual nivel da arvore e o gestor quando a estrutura nao for raiz. Ate isso ser respondido pelo Owner, NAO subir a arvore.';
comment on column secullum."Estrutura".email is 'NOSSO (minusculo) apesar de o VALOR vir do Secullum: nao e um campo de `Estrutura`, e o `Funcionario.Email` do funcionario cujo "Nome" bate com "Descricao". E resultado da NOSSA logica de match, nao um no do payload.';
comment on column secullum."Estrutura".email_origem is 'NOSSO (minusculo). manual (default) | secullum. A sincronizacao SO escreve em email quando email IS NULL OU email_origem = ''secullum''. Valor cadastrado pelo Owner NUNCA e sobrescrito.';
comment on column secullum."Estrutura".whatsapp is 'NOSSO (minusculo) — SEMPRE cadastro manual do Owner, nao ha campo equivalente no Secullum. ⛔ NAO derivar de "Funcionario"."Celular"/"Telefone" (agora capturados): telefone pessoal nao e canal de notificacao autorizado. Ver docs/06-seguranca-lgpd.md.';
comment on column secullum."Funcao"."FuncaoId" is 'Campo `Funcao.Id`, quando presente. NULLABLE e sem UNIQUE — mesma disciplina de "Cidade"."CidadeId". A chave de idempotencia e "Descricao" (que e a chave usada pelo proprio Secullum na rota Funcoes).';
comment on column secullum."Funcionario"."Admissao" is 'Funcionario.Admissao (data real do Secullum, ja presente no payload de /Funcionarios). Entra na allow-list de PII: e dado de vinculo empregaticio necessario para saber se o funcionario estava ativo na janela do relatorio/dashboard. Ver docs/06-seguranca-lgpd.md.';
comment on column secullum."Funcionario"."Celular" is 'Campo `Celular`. ⛔ NAO usar como numero de WhatsApp para notificacao — telefone pessoal nao e canal autorizado. "Estrutura".whatsapp continua 100% manual ([DECISAO DO OWNER]).';
comment on column secullum."Funcionario"."ConfigEspecificaCapturaDeFotoNoMomentoDaInclusao" is '✅ Nome confirmado. ⚠️ E apenas a CONFIGURACAO. Nenhuma foto e buscada nem armazenada por este projeto (ver "PossuiFoto" e o cabecalho desta migration).';
comment on column secullum."Funcionario"."ConfigEspecificaInclusaoManualPonto" is '✅ Nome confirmado no payload real (2026-08-13). ⏳ [VALIDAR — Postman] TIPO: a inspecao entregou so a chave. Assumido boolean; se for enum de modo (0/1/2), abrir migration corretiva. ⛔ Parser deve normalizar e devolver NULL em valor inesperado, nunca derrubar o ciclo.';
comment on column secullum."Funcionario"."ConfigEspecificaInclusaoManualPontoFusoHorarioId" is '✅ Nome confirmado. Sufixo Id => integer bruto, SEM FK: o cadastro de fusos horarios do Secullum nao e consumido por este projeto.';
comment on column secullum."Funcionario"."Cpf" is 'Campo `Cpf`. Sem UNIQUE de proposito: duplicata no cadastro do cliente cai no caso "2+ candidatos" da correlacao de afastamentos, que se abstem em vez de errar o titular.';
comment on column secullum."Funcionario"."Demissao" is 'Funcionario.Demissao (data real do Secullum; null enquanto o vinculo estiver ativo). Pode vir com data FUTURA (desligamento programado) — ver a regra de derivacao de employee.active em docs/04-modelo-dados.md.';
comment on column secullum."Funcionario"."DepartamentoId" is 'Campo `Funcionario.DepartamentoId` — INTEIRO do Secullum. A FK usada e departamento_id (uuid).';
comment on column secullum."Funcionario"."DesabilitarAssinaturaEletronica" is '✅ Nome confirmado. ⏳ [VALIDAR — Postman] tipo assumido boolean, como os demais Bloquear*/Permite*/Desabilitar* deste bloco.';
comment on column secullum."Funcionario"."Email" is 'Campo `Email` do funcionario. ⚠️ Ate 2026-08-13 so era lido em memoria para resolver "Estrutura".email quando o funcionario ERA o gestor; agora e persistido para todos. Isso NAO autoriza usa-lo como canal de notificacao: destinatario de relatorio continua sendo apenas "Estrutura".email/"Estrutura".whatsapp.';
comment on column secullum."Funcionario"."EmpresaId" is 'Campo `Funcionario.EmpresaId` — INTEIRO do Secullum, como veio. ⚠️ A FK que o sistema usa e empresa_id (uuid). Nunca fazer join por esta coluna.';
comment on column secullum."Funcionario"."EstruturaId" is 'Campo `Funcionario.EstruturaId` — INTEIRO do Secullum; e a chave de idempotencia de "Estrutura" (tabela do gestor). Nao ha FK uuid daqui para "Estrutura": o vinculo gestor->departamento e o que importa ao produto, e resolve-lo por funcionario duplicaria a relacao.';
comment on column secullum."Funcionario"."Foto" is 'Campo literal do Secullum (imagem do funcionário), vinda do 6º endpoint (GET Funcionarios/fotos?funcionarioId=<Id>), NÃO de /Funcionarios. Guarda os BYTES JÁ DECODIFICADOS (o prefixo "data:<mime>;base64," da data URI NÃO é armazenado aqui — ver foto_mime). NULL = não temos (nunca buscada OU funcionário sem foto). 🔴 A coluna mais restrita do schema: nunca em view exposta ao painel, nunca em log, nunca em relatório (ADR-018 §6.3). ⛔ NUNCA escrita pelo upsert de sync-cadastro — só pelo UPDATE direcionado do job sync-fotos.';
comment on column secullum."Funcionario"."FuncionarioId" is 'Campo `Funcionario.Id` — nomeado na forma qualificada porque e literalmente assim que o Secullum o chama de fora (`Batidas.FuncionarioId`). Chave de idempotencia e chave de juncao com /Batidas.';
comment on column secullum."Funcionario"."HorarioAlternativo2Id" is 'Campo `HorarioAlternativo2Id` — inteiro BRUTO, sem FK para "Horario" de proposito: o horario referenciado pode nao existir localmente (ou ainda nao ter sido sincronizado no ciclo), e uma FK transformaria isso em falha de job. Resolucao para "Horario".id, se necessaria, e da consulta.';
comment on column secullum."Funcionario"."HorarioId" is 'Campo `Funcionario.HorarioId` — INTEIRO do Secullum. A FK usada e horario_id (uuid). ℹ️ Em /Funcionarios o objeto `Horario` aninhado vem com `Dias` = null POR DESIGN: a grade completa so vem de GET /Horarios.';
comment on column secullum."Funcionario"."Mae" is '⚠️ PII de TERCEIRO (a mae do funcionario nao e titular deste tratamento nem tem relacao com o controlador). Capturada por decisao do Owner; e o campo com a justificativa de finalidade mais fraca de todo o schema. Vale o mesmo para "Pai". Ver docs/06-seguranca-lgpd.md.';
comment on column secullum."Funcionario"."MotivoDemissaoId" is 'Campo `MotivoDemissaoId` bruto. A rota MotivosDemissao NAO e consumida (escopo de 5 endpoints), entao o motivo em texto nao existe localmente — o que, alias, e desejavel: motivo de demissao e dado sensivel de vinculo.';
comment on column secullum."Funcionario"."NumeroFolha" is 'Campo `NumeroFolha` (Texto(22)) — matricula na folha. Dado pessoal identificador.';
comment on column secullum."Funcionario"."NumeroPis" is 'Campo `NumeroPis`. Pode vir string vazia — tratar "" como AUSENTE. Sem UNIQUE, mesmo racional de "Cpf".';
comment on column secullum."Funcionario"."Observacao" is '⚠️ TEXTO LIVRE de RH (Texto(255)). Alto risco de conter dado de saude/condicao pessoal. Persistido por decisao do Owner (ADR-011), contrariando a regra anterior de descarte de texto livre. ⛔ Nunca exibir em relatorio ao gestor, nunca logar, nunca indexar para busca.';
comment on column secullum."Funcionario"."PeriodoEncerrado" is '[VALIDAR — Postman] Tipo desconhecido (data? boolean?). Modelado como TEXT para nao perder o valor nem quebrar o job por conversao errada; converter em migration corretiva depois da inspecao do payload.';
comment on column secullum."Funcionario"."PossuiFoto" is 'Apenas o indicador. A imagem em si exigiria a rota Funcionarios/fotos (6o endpoint) e NAO e buscada.';
comment on column secullum."Funcionario"."Rg" is '⚠️ PII sensivel, capturada a partir de 2026-08-13 por decisao do Owner (ADR-011). Antes era explicitamente descartada pelo parser. Nunca logar, nunca exibir em notificacao.';
comment on column secullum."Funcionario".afastado_hoje is 'DERIVADO POR NOS (minusculo). O nome declara a limitacao no proprio identificador: responde APENAS "esta afastado HOJE?". Para "estava afastado na data X?" (motor, relatorio, dashboard) a fonte da verdade e SEMPRE "FuncionarioAfastamento". E funcao do tempo: vira sozinho no primeiro e no ultimo dia do afastamento, sem nada mudar no Secullum.';
comment on column secullum."Funcionario".afastamento_atual_id is 'Ponteiro para o registro de employee_absence que cobre "hoje" (null quando on_leave = false). Existe para o painel mostrar "afastado ate DD/MM" com um unico join, sem duplicar as datas em employee (dado duplicado = dado que dessincroniza). ON DELETE SET NULL: se o afastamento sumir do Secullum e for removido pela convergencia, o ponteiro se limpa sozinho. Havendo mais de um periodo cobrindo hoje (sobreposicao), aponta o de maior end_date e a sobreposicao e logada como aviso (absence_overlap).';
comment on column secullum."Funcionario".ativo is 'DERIVADO POR NOS (minusculo, NAO e campo do Secullum): VINCULO EMPREGATICIO, calculado a partir das datas com "hoje" em America/Sao_Paulo: ativo = ("Admissao" is null or "Admissao" <= hoje) and ("Demissao" is null or "Demissao" >= hoje). ⛔ NAO e afetado por ferias/afastamento — para isso existe afastado_hoje. ⚠️ Continua sendo COLUNA NORMAL (ao contrario de "Empresa".ativo, que virou gerada): esta derivacao depende de "hoje", nao e funcao imutavel das colunas, e por isso NAO pode ser GENERATED. Ver ADR-009 e ADR-010.';
comment on column secullum."Funcionario".cidade_id is 'NOSSA FK (uuid) -> "Cidade". ⚠️ NAO confundir com "CidadeId" (inteiro do Secullum), ao lado.';
comment on column secullum."Funcionario".empresa_id is 'NOSSA FK (uuid). Desnormalizada de proposito em relacao a "Departamento".empresa_id — e assim que o Secullum entrega o dado, e o dashboard agrega por Empresa. ⛔ Agregacao por Empresa usa SEMPRE esta coluna. ⚠️ NAO confundir com "EmpresaId" (inteiro do Secullum), criada em 20260813161000.';
comment on column secullum."Funcionario".foto_bytes is 'NOSSA. Tamanho em bytes da imagem DECODIFICADA. Observabilidade/dimensionamento, sem depender de octet_length("Foto") (que exigiria ler o binário).';
comment on column secullum."Funcionario".foto_hash is 'NOSSA. sha256 em hex dos BYTES DECODIFICADOS de "Foto" (nunca da string base64/data URI original — duas fotos idênticas com prefixos textualmente diferentes têm o mesmo hash). Permite pular o UPDATE do binário quando nada mudou e é a única forma de dizer "a foto mudou" em log sem citar conteúdo.';
comment on column secullum."Funcionario".foto_mime is 'NOSSA. image/jpeg, image/png, ou NULL quando não determinável. Fonte primária: o prefixo da data URI do 6º endpoint (confirmado por payload real, 2026-08-31); o *magic number* dos bytes é usado só como CONFERÊNCIA (diverge => vence o conteúdo real, com aviso agregado foto_mime_divergente). ⛔ Sem CHECK e sem lista fechada — mesma disciplina dos demais enums/mime deste schema. ⛔ Nunca inferir por nome de arquivo, nunca assumir JPEG por padrão.';
comment on column secullum."Funcionario".foto_sincronizada_em is 'NOSSA. Timestamp da última sincronização BEM-SUCEDIDA do job sync-fotos — inclui o sucesso "não tem foto" (ausência confirmada pelo Secullum). Distinta de foto_tentativa_em: uma tentativa que deu ERRO atualiza só foto_tentativa_em, nunca esta coluna (ADR-018 §5.3 — erro nunca apaga/mascara dado real).';
comment on column secullum."Funcionario".foto_tentativa_em is 'NOSSA. Timestamp da última TENTATIVA do job sync-fotos, com ou sem sucesso. 🔴 É esta coluna (não foto_sincronizada_em) que ordena a fila (funcionario_foto_fila_idx, ORDER BY ... NULLS FIRST) — sem ela, um funcionário cuja busca falha sempre travaria a cabeça da fila para sempre (ADR-018 §4.1).';
comment on column secullum."Funcionario".funcao_id is 'NOSSA FK (uuid) -> "Funcao". ⚠️ NAO confundir com "FuncaoId" (inteiro do Secullum), ao lado.';
comment on column secullum."Funcionario".horario_id is 'NOSSA FK (uuid) -> "Horario". NULLABLE: funcionario sem horario cadastrado no Secullum nao derruba a sincronizacao (fica sem horario, com aviso em log). ⚠️ NAO confundir com "HorarioId" (inteiro do Secullum).';
comment on column secullum."FuncionarioAfastamento"."AfastamentoId" is 'Campo `Id` do registro de afastamento (nao consta da tabela oficial do manual; confirmado em payload real). Forma qualificada pelo mesmo motivo de "FuncionarioId": `Id` puro colidiria por case com o `id` interno. Unicidade global NUNCA verificada — por isso a chave e COMPOSTA com funcionario_id.';
comment on column secullum."FuncionarioAfastamento"."DataInclusao" is 'Campo `DataInclusao` (nao documentado na tabela oficial; confirmado em payload real). Quando o registro foi criado no Secullum. Serve para diagnosticar afastamento lancado RETROATIVAMENTE, que invalida desvios ja detectados na janela — ver requisito do motor em sprints/sprint-02-motor-deteccao.md.';
comment on column secullum."FuncionarioAfastamento"."Fim" is 'Campo `Fim`, INCLUSIVO (o dia de Fim ainda e afastamento). Parsing pelos 10 primeiros caracteres da string, nunca via Date/UTC. ⛔ Sem CHECK ("Fim" >= "Inicio") de proposito: registro invertido na origem nao pode derrubar o job — o parser loga absence_invalid_range, nao grava e segue.';
comment on column secullum."FuncionarioAfastamento"."Inicio" is 'Campo `Inicio` (Data, obrigatorio). Parsing obrigatorio: 10 PRIMEIROS CARACTERES da string. NUNCA via new Date(...)/toISOString() — a Edge Function roda em UTC e a conversao ingenua desloca um dia.';
comment on column secullum."FuncionarioAfastamento"."JustificativaNome" is 'Campo `JustificativaNome` (Texto(7)), bruto, sem CHECK e sem lista fechada. ⚠️ Tratar como potencialmente revelador de saude: nunca exibido cru em relatorio/painel e nunca logado junto de identificacao do titular. O cadastro de Justificativas NAO e consumido.';
comment on column secullum."FuncionarioAfastamento".correlacionado_por is 'NOSSO (minusculo) — diagnostico (pis | cpf): qual chave resolveu a correlacao. Nao e PII: guarda o TIPO de chave, nunca o valor.';
comment on column secullum."FuncionarioAfastamento".funcionario_id is 'Correlacao resolvida EM MEMORIA por NumeroPis (prioridade) com fallback para Cpf: este endpoint NAO tem FuncionarioId, diferente de /Batidas. NumeroPis pode vir string vazia (visto em payload real) — tratar "" como ausente. Comparacao sempre sobre digitos (strip de mascara) nos dois lados. Zero ou 2+ candidatos => registro DESCARTADO com aviso agregado, nunca escolha arbitraria (mesma regra do match de gestor, docs/03-integracao-secullum.md).';
comment on column secullum."FuncionarioAfastamento".sincronizado_em is 'Ultima vez que este registro foi visto na resposta do Secullum. Base do delete de convergencia (registro apagado no Secullum tem de sumir daqui, senao suprime desvio para sempre).';
comment on column secullum."FuncionarioCentroCusto"."Descricao" is 'Unico campo do item no payload. A chave (funcionario_id, "Descricao") e a unica identidade possivel.';
comment on column secullum."Horario"."HorarioId" is 'Campo `Horario.Id` — chave de idempotencia local.';
comment on column secullum."Horario"."Numero" is 'Campo `Horario.Numero` — chave de NEGOCIO do Secullum (a rota Horarios?numero=<N> usa este campo). NAO e a chave de idempotencia local, que e "HorarioId".';
comment on column secullum."Horario".ativo is 'DERIVADO POR NOS (minusculo) do campo `Desativar`. ⏳ O campo literal "Desativar" NAO foi criado: tipo/semantica exatos nao confirmados no payload real (docs/03-integracao-secullum.md). Nao inventar coluna — abrir migration corretiva quando o tipo for observado.';
comment on column secullum."HorarioDescanso"."IncluirFeriado" is 'Enum bruto (DescansoDomingo=0, DescansoDia=1, HoraNormalDia=2, HoraNormalDescanso=3), sem CHECK.';
comment on column secullum."HorarioDescanso"."LimiteHorasFaltas" is 'Texto(5) HH:mm — tambem DURACAO. Mesma razao de "ValorDescanso" para manter TEXT.';
comment on column secullum."HorarioDescanso"."Tipo" is 'Enum bruto (Automatico=0, Variavel=1), smallint sem CHECK.';
comment on column secullum."HorarioDescanso"."ValorDescanso" is 'Texto(5) no formato HH:mm, mas semanticamente uma DURACAO (valor do DSR), nao um horario do dia. Mantido TEXT de proposito: o tipo `time` do Postgres nao representa duracao acima de 24h e induziria comparacoes erradas. Este sistema nao calcula DSR.';
comment on column secullum."HorarioDescansoFaixaItem"."Limite" is 'Texto(5) HH:mm (DURACAO). Mantido TEXT — mesma razao de "HorarioDescanso"."ValorDescanso".';
comment on column secullum."HorarioDia"."Carga" is 'Campo `Carga`, EM MINUTOS de carga do dia. Discriminador de dia sem expediente (junto com os 10 pares nulos). ⚠️ NAO confundir com "HorariosOpcoes"."Carga", que e a carga configurada no nivel do HORARIO.';
comment on column secullum."HorarioDia"."DiaSemana" is 'Campo `DiaSemana`: 0=Segunda .. 6=Domingo. ⛔ NUNCA usar EXTRACT(DOW) (0=Domingo) ao comparar com uma data — usar EXTRACT(ISODOW)-1. ⚠️ NAO confundir com "HorarioFaixasExtras"."DiaSemana", que e um enum COMPLETAMENTE diferente (Uteis=0, Sabado=1, ... IntervaloFolgas=15).';
comment on column secullum."HorarioDia"."HorarioDiaId" is 'Campo `Dias[].Id`. ATRIBUTO de diagnostico (indice nao-unico) — NAO e chave de idempotencia: confirmado em producao que se repete entre Horarios diferentes (migration 20260812140000). A chave real e (horario_id, "DiaSemana").';
comment on column secullum."HorarioDia"."TipoEntrada1" is 'TipoEntradaN bruto (smallint, sem CHECK/enum — enum nao documentado pelo Secullum).';
comment on column secullum."HorarioDia"."ToleranciaExtra" is 'Campo `ToleranciaExtra`, EM MINUTOS (a unidade nao esta no nome porque o nome e literal do Secullum). ⛔ Junto com "ToleranciaFalta", e a UNICA tolerancia que o motor de deteccao pode aplicar — nunca uma tolerancia propria, sob pena de divergir do calculo oficial de folha.';
comment on column secullum."HorarioDia"."ToleranciaFalta" is 'Campo `ToleranciaFalta`, EM MINUTOS. ⚠️ ARMADILHA CONFIRMADA: dia de folga vem com "ToleranciaExtra"/"ToleranciaFalta" PREENCHIDOS. Presenca de tolerancia NAO significa que ha expediente.';
comment on column secullum."HorarioDia".sem_expediente is 'DERIVADO POR NOS — por isso minusculo, e NAO um campo que o Secullum manda. true quando "Carga" = 0 E os 10 pares Entrada/Saida sao nulos. Nome escolhido para nao colidir com `Batida.Folga` nem com `TipoDia = Folga(2)`, que sao tres coisas distintas.';
comment on column secullum."HorarioExtras"."Acumulo" is 'Enum BRUTO 0..8 (Independentes=0 ... UteisDomingo_e_SabadoFeriado=8), smallint SEM CHECK.';
comment on column secullum."HorarioExtras"."ControleHorasExtrasAutorizadas" is '⚠️ Regra de FOLHA: limita quanto de hora extra o Secullum considera autorizado. ⛔ O motor de deteccao NAO filtra desvio por esta regra — o relatorio consolidado reporta desvio de HORARIO, nao saldo autorizado de folha. Confundir os dois faz o relatorio deixar de mostrar exatamente o excesso que o gestor precisa ver.';
comment on column secullum."HorarioExtras"."DescontarFaltasExtras" is 'Enum BRUTO (MaisSignificativas=0, MenosSignificativas=1), smallint SEM CHECK — mesma disciplina de "HorarioDia"."TipoEntrada1" e de "BatidaFonteDados"."Origem".';
comment on column secullum."HorarioExtras"."DescontarIgnorarDiaEspecial" is '"Dia especial" aqui e o mesmo conceito de "HorarioFaixasExtras"."DiaEspecial" (Domingo=0..Sabado=6) — ⚠️ TERCEIRA convencao de dia da semana do schema, diferente de "HorarioDia"."DiaSemana".';
comment on column secullum."HorarioExtras"."Interjornada" is '⚠️⚠️ DIVERGENCIA CONFIRMADA DA DOCUMENTACAO OFICIAL. O manual declara `Interjornada` como Booleano, com uma descricao que nem sequer e deste campo ("marcar qualquer minuto adiantado como extra", copiada de HorariosOpcoes). O valor REAL observado na conta do cliente em 2026-08-13 e uma STRING — provavelmente o intervalo minimo entre jornadas em "HH:mm". ⛔ NAO "corrigir" para boolean com base no PDF: o payload e o contrato. Mantido TEXT (nao `time`): e DURACAO, nao horario do dia.';
comment on column secullum."HorarioExtras"."QuantidadeExtrasAutorizadas" is 'Texto "HH:mm" conforme o manual — e DURACAO, nao horario do dia. Mantido TEXT de proposito: o tipo `time` do Postgres nao representa duracao acima de 24h e induziria comparacao errada.';
comment on column secullum."HorarioExtras"."UsarInterjornada" is 'Booleano que liga o uso de "Interjornada". ⚠️ O manual repete, por erro de copia, descricoes de HorariosOpcoes em UsarInterjornada/Interjornada/InterjornadaSeparada. O NOME do campo e o contrato; a descricao do PDF nao e confiavel neste bloco.';
comment on column secullum."HorarioFaixasExtras"."Controle" is 'Enum bruto (Diario=0, Semanal=1, Mensal=2), sem CHECK.';
comment on column secullum."HorarioFaixasExtras"."DiaEspecial" is 'De Domingo(0) a Sabado(6) — ⚠️ TERCEIRA convencao de dia da semana neste schema, diferente das outras duas. Valor bruto do Secullum, sem conversao.';
comment on column secullum."HorarioFaixasExtras"."DiaSemana" is '⚠️⚠️ ENUM COMPLETAMENTE DIFERENTE de "HorarioDia"."DiaSemana", apesar do nome identico (os dois nomes sao literais do Secullum). Aqui: Uteis=0, Sabado=1, Domingo=2, Feriado=3, Folgas=4, Especial=5, NoturnoUteis=6, NoturnoSabado=7, NoturnoDomingo=8, NoturnoFeriado=9, NoturnoFolgas=10, IntervaloUteis=11, IntervaloSabado=12, IntervaloDomingo=13, IntervaloFeriado=14, IntervaloFolgas=15. Em "HorarioDia", "DiaSemana" e 0=Segunda..6=Domingo. Confundir os dois produz erro SILENCIOSO. smallint BRUTO, sem CHECK.';
comment on column secullum."HorarioFaixasExtrasItem"."Coluna" is 'Coluna de extra correspondente. Tipo `Duplo` no manual mesmo parecendo indice inteiro — preservamos `double precision` para nao perder valor fracionario nem falhar na conversao.';
comment on column secullum."HorarioToleranciaEspecifica"."UsaToleranciaEspecifica" is 'Quando true, o motor de deteccao LOGA AVISO e aplica a tolerancia padrao do dia — nunca silencia. A tolerancia especifica e expressa como FAIXA (De/Ate), nao como minutos, e por isso nao e aproximavel pela tolerancia padrao.';
comment on column secullum."HorarioToleranciaEspecificaItem"."DiaSemana" is '⚠️ O manual (pag. 18) declara DiaSemana como "Booleano" com a descricao "Usa tolerancia especifica" — sao dois erros evidentes de copia na tabela oficial. Modelado como smallint (dia da semana), coerente com o payload real. [VALIDAR — Postman] se algum dia houver caso real ativo neste cliente.';
comment on column secullum."HorariosOpcoes"."AlocarBatidas" is 'Numero no payload real; semantica/enum NAO documentados. INTEIRO BRUTO, sem CHECK — mesma disciplina de "HorarioDia"."TipoEntrada1" e de "BatidaFonteDados"."Origem". `integer` (e nao `smallint`) de proposito: sem faixa conhecida, o tipo mais largo evita derrubar a transacao inteira do ciclo por causa de um campo que nenhum consumidor le.';
comment on column secullum."HorariosOpcoes"."AlocarHorario24Horas" is 'Nivel HORARIO. ⚠️ Existe tambem "HorarioDia"."Alocar24Horas", nivel DIA. Sao dois campos distintos do Secullum; o relevante para jornada que cruza a meia-noite e o do dia.';
comment on column secullum."HorariosOpcoes"."Carga" is 'Carga configurada no nivel do HORARIO (acompanha "DefinirCargaAutomaticamente"). ⚠️ NAO confundir com "HorarioDia"."Carga", que e a carga do DIA em minutos e e a unica que interessa a "ha expediente?". Unidade deste campo (minutos vs. horas) nao confirmada; `double precision` para nao truncar valor fracionario nem falhar na conversao.';
comment on column secullum."HorariosOpcoes"."Compensacao" is '⏳ Veio `null` no registro real — TIPO NAO OBSERVADO. Modelado como smallint nullable (enum de modo de compensacao) porque a familia de irmaos booleanos "CompensacaoIgnorar*" implica fortemente um enum de modo. Bruto, sem CHECK.';
comment on column secullum."HorariosOpcoes"."CompensacaoMensalFechamento" is '⏳ Veio `null` no registro real e, ao contrario de "Compensacao", NAO tem contexto que permita inferir o tipo (dia do mes? data? objeto?). jsonb bruto de proposito: `text` transformaria um eventual objeto em "[object Object]" e `smallint` derrubaria a transacao se vier string. Estreitar quando houver exemplo.';
comment on column secullum."HorariosOpcoes"."CompletarBatidasFaltantes" is '⚠️ Opcao de FOLHA do Secullum que preenche batida ausente no calculo dele. ⛔ Isso NAO afeta o que /Batidas devolve a este sistema nem autoriza o motor a "completar" nada: batida faltante continua sendo detectada por slot com "Memoria" e sem hora.';
comment on column secullum."HorariosOpcoes"."HorarioId" is 'Campo `HorarioId` do proprio no (inteiro do Secullum). A FK usada e horario_id (uuid).';
comment on column secullum."HorariosOpcoes"."HorasRepousoFaixas" is '⏳ SHAPE NAO CONFIRMADO. Veio `null` no registro real — nao ha um unico exemplo populado. jsonb BRUTO de proposito: modelar tabela filha exigiria INVENTAR as colunas do item, e este projeto ja quebrou duas vezes em producao por supor estrutura do Secullum sem evidencia. Hipotese NAO confirmada (nao implementar): mesma forma de "HorarioDescansoFaixaItem" { Ordem, Limite, Desconto }. Quando aparecer exemplo populado, promover a tabela filha por migration corretiva. Sem PII: e parametro de horario.';
comment on column secullum."HorariosOpcoes"."LimiteMinimoDeFaltasNoDiaMinutos" is '⚠️ O manual oficial (pag. 11) descreve este campo como "Limite minimo de EXTRAS no dia" e o de extras como "de FALTAS" — as descricoes estao TROCADAS no PDF. Preservamos o NOME do campo, que e o contrato real; ⛔ nao inverter para "corrigir".';
comment on column secullum."HorariosOpcoes"."ListaHorasInItinere" is '⏳ SHAPE NAO CONFIRMADO. Veio `[]` no registro real. jsonb bruto, mesmo racional.';
comment on column secullum."HorariosOpcoes"."ListaHorasSobreAviso" is '⏳ SHAPE NAO CONFIRMADO. Veio `[]` no registro real — a lista existe, o item nunca foi observado. jsonb bruto pelo mesmo racional de "HorasRepousoFaixas". Nao inventar colunas.';
comment on column secullum."HorariosOpcoes"."PeriodoEspecialAdicionalNoturnoInicio" is 'Texto(5) "HH:mm". Mantido TEXT (nao `time`): e configuracao de folha, nunca comparada com hora de batida por este sistema, e converter introduziria risco de fuso sem nenhum ganho.';
comment on column secullum."HorariosOpcoes"."SubstituirBatidasAbaixoDasTolerancias" is '⚠️ Regra de folha que substitui a batida pelo horario previsto quando a diferenca cabe na tolerancia. ⛔ O motor NAO aplica isso — ele compara a hora crua de batida_marcacao.hora com o previsto de "HorarioDia". Ativar essa regra aqui mudaria o numero do relatorio sem mudar o do Secullum.';
comment on column secullum."HorariosOpcoes"."TipoPreencherQuandoDiaEstiverEmBranco" is 'Enum bruto, sem CHECK. Acompanha "PreencherFaltasQuandoDiaEstiverEmBranco". `integer` pelo mesmo motivo de "AlocarBatidas": faixa desconhecida.';
comment on column secullum."HorariosOpcoes"."ToleranciaRefeicoesMinutos" is '⚠️ Tolerancia de REFEICAO — nao confundir com "HorarioDia"."ToleranciaExtra"/"ToleranciaFalta", que sao as unicas que o motor pode usar.';
comment on column secullum.departamento_gestor.funcionarios_observados is 'Sinal de qualidade de cadastro, NÃO dado de produto: quantos funcionários deste departamento apontavam para esta "Estrutura" no ciclo em que a linha foi gravada/atualizada. Nunca usado para eleger titular (proibido eleição por maioria — ADR-013 §4/§4.1) — só contagem para diagnóstico humano.';
comment on column secullum.departamento_gestor.observado_ate is 'Data de DETECÇÃO do fim da vigência (quando ESTA sincronização deixou de observar o vínculo vigente), NUNCA data de negócio. NULL = vigente. Ver ADR-013 §3 — mesma limitação de observado_desde, e mesmo contraste com "FuncionarioAfastamento" (que TEM datas reais de Inicio/Fim vindas do Secullum — não confundir a semântica das duas tabelas).';
comment on column secullum.departamento_gestor.observado_desde is 'Data de DETECÇÃO (quando ESTA sincronização percebeu o vínculo), NUNCA data de negócio — o Secullum não expõe "desde quando fulano é gestor desta unidade". Precisão real: no melhor caso, o intervalo entre execuções do job cadastral; ilimitada se a mudança ocorreu em período sem sincronização. Ver ADR-013 §3.';
comment on column secullum.departamento_gestor.origem is 'secullum_sync (transição detectada pela sincronização normal) | backfill (migração desta tabela a partir de "Estrutura".departamento_id, no deploy da migration 20260821120000) | manual (ajuste do Owner, não usado pelo worker). ⚠️⚠️ CORRIGIDO em 2026-08-24 (ADR-013, 3º adendo) — a versão anterior deste comentário estava ERRADA: dizia que a limitação abaixo valia só para origem = ''backfill'' e só para dado anterior a uma política de "não reaproveitar cadastro de gestor". NENHUMA DAS DUAS PARTES é verdadeira. A troca de titular neste cliente é SEMPRE uma edição de "Estrutura"."Descricao" no MESMO EstruturaId (nunca um EstruturaId novo) — logo NENHUMA linha desta tabela, de QUALQUER origem, identifica a PESSOA que respondia pela unidade: toda linha identifica apenas qual EstruturaId (nó) respondia pelo departamento naquele intervalo. Para saber QUEM ocupava aquele nó, é OBRIGATÓRIO compor com estrutura_evento_titular (ver o comentário daquela tabela e ADR-013 §6 do 3º adendo — "Consulta canônica"). A diferença secullum_sync x backfill continua relevante só quanto à CONFIABILIDADE DA DATA de início do vínculo do nó (observado_desde), nunca quanto à identidade do ocupante.';
comment on column secullum.estrutura_evento_titular.detectado_em is 'Data de DETECÇÃO (quando ESTA sincronização percebeu a mudança), NUNCA data de negócio — mesma limitação e mesmo motivo do nome de departamento_gestor.observado_desde/observado_ate (ADR-013 §3): o Secullum não expõe "desde quando fulano ocupa este nó". Uma cobertura inteiramente contida entre duas execuções do job é invisível para sempre.';
comment on column secullum.estrutura_evento_titular.funcionario_id_anterior is 'Funcionario que a Descricao ANTERIOR resolvia, por match de nome ÚNICO — NULL = 0/ambíguo (nada se afirma). ON DELETE SET NULL (nunca CASCADE): expurgar esta pessoa não pode apagar a transição que documenta o SUCESSOR dela.';
comment on column secullum.estrutura_evento_titular.funcionario_id_novo is 'Funcionario que a Descricao NOVA resolve, por match de nome ÚNICO — NULL = 0/ambíguo. ON DELETE SET NULL pelo mesmo motivo de funcionario_id_anterior.';
comment on column secullum.estrutura_evento_titular.origem is 'secullum_sync (evento detectado pela sincronização normal, fase 3.b) | backfill (carga inicial, sem transição observada) | manual (ajuste do Owner, não usado pelo worker).';
comment on column secullum.estrutura_evento_titular.tipo_evento is 'Classificação pela EVIDÊNCIA observada, nunca por interpretação (ADR-013, 3º adendo, item 4). baseline: primeira observação deste nó, sem estado anterior conhecido. descricao_alterada_mesmo_funcionario: Descricao mudou mas o match de nome (mesmo mecanismo do e-mail do gestor) continua resolvendo para o MESMO Funcionario — correção de grafia/acento, NÃO troca de titular, e é distinguível com segurança (evidência de registro idêntico). descricao_alterada_outro_funcionario: Descricao mudou e o match passou a resolver para OUTRO Funcionario — a MELHOR evidência disponível de troca real, mas evidência, não prova (ver limitação no comentário da tabela: correção de nome ERRADO para o CERTO produz o mesmo sinal). descricao_alterada_indeterminada: Descricao mudou e o match ficou 0/ambíguo em pelo menos um lado — NADA se afirma sobre identidade, só se registra o fato (aviso estrutura_titular_indeterminado). email_alterado: só o e-mail mudou (Descricao igual) — tipicamente correção de contato do MESMO titular, sem indício de troca de pessoa. ⛔ NUNCA classificar por similaridade de string/distância de edição — só identidade de registro de Funcionario por match ÚNICO (mesma régua do ADR-006/ADR-013 item 7).';
