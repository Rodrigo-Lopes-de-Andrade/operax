# OperaX — Dicionário de dados e superfície de API

> Gerado por introspecção do banco (`scripts/gerar_dicionario.py`).
> Não editar à mão: regerar depois de cada migration.

## Arquitetura de schemas

| Schema | Papel | Exposto ao PostgREST |
|---|---|---|
| `secullum` | Espelho literal do Secullum — Não exposto ao PostgREST. PII completa. Só `service_role`. | Não |
| `app` | Domínio OperaX — Não exposto ao PostgREST. RLS obrigatória em toda tabela. | Não |
| `util` | Helpers de RLS — Não exposto. Funções `security definer` com `search_path` travado. | Não |
| `public` | Superfície de API — ÚNICO schema exposto. Só views (`security_invoker = on`) e RPCs. | **Sim, e só ele** |

A anon key vive no bundle do painel: qualquer pessoa chama o PostgREST direto.
Por isso a fronteira real é **topologia de schema**, não policy. Tabela fora do
schema exposto é inalcançável mesmo com policy errada.

## Matriz de sensibilidade

Quatro domínios em `app.sensitive_domain`. Quem vê o quê está em
`app.domain_permission` — é dado, não código, e muda por `UPDATE`.

| Domínio | Onde vive | Padrão de acesso |
|---|---|---|
| `pii` | `app.employee_pii` | owner, DP, RH |
| `remuneracao` | `app.employee_compensation`, `app.payroll_entry`, `app.payroll_charge`, `app.acordo_*` | owner, DP, diretoria, contabilidade |
| `saude` | `app.occupational_exam` | owner, RH |
| `disciplinar` | ocorrências administrativas | owner, DP, RH |

Gestor regional, supervisor de unidade, gestor operacional e consulta **não**
recebem nenhum domínio sensível: veem ocorrência de ponto da sua unidade, não
veem salário, RG nem ASO. Ver a unidade não dá direito a ver o dado sensível —
as policies exigem escopo **e** domínio.


---

# Schema `app`

Domínio OperaX. Não exposto ao PostgREST. RLS obrigatória em toda tabela.


## `app.agreement_installment`

> Parcela pendente cuja competência já passou = alerta de "parcela não processada" (item 9 da proposta).

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `agreement_id` | uuid | não |  | `app.financial_agreement` |  |
| `number` | integer | não |  |  |  |
| `period_year` | smallint | não |  |  |  |
| `period_month` | smallint | não |  |  |  |
| `amount` | numeric(14,2) | não |  |  |  |
| `status` | text | não | `'pending'::text` |  |  |
| `payroll_entry_id` | uuid | sim |  | `app.payroll_entry` |  |
| `processed_at` | timestamp with time zone | sim |  |  |  |

**Restrições**

- `CHECK (((period_month >= 1) AND (period_month <= 13)))`
- `CHECK ((amount > (0)::numeric))`
- `CHECK ((number >= 1))`
- `CHECK ((status = ANY (ARRAY['pending'::text, 'processed'::text, 'cancelled'::text, 'renegotiated'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `parcela_read` | SELECT | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND (EXISTS ( SELECT 1` | `` |
| `parcela_write` | ALL | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.is_admin(tenant_id))` | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) ` |

<details><summary>Índices</summary>

- `agreement_installment_payroll_entry_id_fkidx` — `app.agreement_installment USING btree (payroll_entry_id)`
- `parcela_competencia_idx` — `app.agreement_installment USING btree (tenant_id, period_year, period_month) WHERE (status = 'pending'::text)`
- `UNIQUE agreement_installment_agreement_id_number_key` — `app.agreement_installment USING btree (agreement_id, number)`

</details>


## `app.ai_query`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `user_id` | uuid | sim |  | `auth.users` |  |
| `question` | text | não |  |  |  |
| `metric_code` | text | sim |  |  |  |
| `parameters` | jsonb | sim |  |  |  |
| `rows_returned` | integer | sim |  |  |  |
| `latency_ms` | integer | sim |  |  |  |
| `input_tokens` | integer | sim |  |  |  |
| `output_tokens` | integer | sim |  |  | Custo de LLM é variável e sai da sustentação mensal. Sem medir, não dá para saber se a margem virou negativa. |
| `refused` | boolean | não | `false` |  |  |
| `refusal_reason` | text | sim |  |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `ai_query_read` | SELECT | `((user_id = ( SELECT auth.uid() AS uid)) OR util.is_admin(tenant_id))` | `-` |

<details><summary>Índices</summary>

- `ai_query_tenant_idx` — `app.ai_query USING btree (tenant_id, created_at DESC)`
- `ai_query_user_id_fkidx` — `app.ai_query USING btree (user_id)`

</details>


## `app.alert_queue`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `rule_id` | uuid | sim |  | `app.alert_rule` |  |
| `deviation_event_id` | uuid | sim |  | `app.deviation_event` |  |
| `report_cycle_id` | uuid | sim |  | `app.report_cycle` |  |
| `channel` | text | não |  |  |  |
| `destination` | text | não |  |  |  |
| `payload` | jsonb | não |  |  |  |
| `idempotency_key` | text | não |  |  | Reprocessar o mesmo período não reenvia. Consuma a fila com SELECT ... FOR UPDATE SKIP LOCKED. |
| `status` | text | não | `'pending'::text` |  |  |
| `attempts` | integer | não | `0` |  |  |
| `next_attempt_at` | timestamp with time zone | não | `now()` |  |  |
| `scheduled_for` | timestamp with time zone | não | `now()` |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((channel = ANY (ARRAY['whatsapp'::text, 'email'::text])))`
- `CHECK ((status = ANY (ARRAY['pending'::text, 'sending'::text, 'sent'::text, 'failed'::text, 'discarded'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `alert_queue_admin` | SELECT | `util.is_admin(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `alert_queue_evento_idx` — `app.alert_queue USING btree (deviation_event_id)`
- `alert_queue_proxima_idx` — `app.alert_queue USING btree (next_attempt_at) WHERE (status = ANY (ARRAY['pending'::text, 'failed'::text]))`
- `alert_queue_report_cycle_id_fkidx` — `app.alert_queue USING btree (report_cycle_id)`
- `alert_queue_rule_id_fkidx` — `app.alert_queue USING btree (rule_id)`
- `alert_queue_tenant_id_fkidx` — `app.alert_queue USING btree (tenant_id)`
- `UNIQUE alert_queue_idempotency_key_key` — `app.alert_queue USING btree (idempotency_key)`

</details>


## `app.alert_rule`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `name` | text | não |  |  |  |
| `deviation_type` | text | sim |  | `app.deviation_type` |  |
| `scope_unit_id` | uuid | sim |  | `app.unit` |  |
| `content` | text | não | `'aggregate'::text` |  |  |
| `channel` | text | não |  |  |  |
| `cron_window` | text | sim |  |  |  |
| `threshold_minutes` | integer | sim |  |  |  |
| `threshold_occurrences` | integer | sim |  |  |  |
| `muted_until` | timestamp with time zone | sim |  |  |  |
| `active` | boolean | não | `false` |  | Nasce false de propósito. Regra só liga depois de homologada com o cliente e validada pelo jurídico/RH. |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((channel = ANY (ARRAY['whatsapp'::text, 'email'::text, 'both'::text])))`
- `CHECK ((content = ANY (ARRAY['individual'::text, 'aggregate'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `alert_rule_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |
| `alert_rule_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `alert_rule_deviation_type_fkidx` — `app.alert_rule USING btree (deviation_type)`
- `alert_rule_scope_unit_id_fkidx` — `app.alert_rule USING btree (scope_unit_id)`
- `alert_rule_tenant_idx` — `app.alert_rule USING btree (tenant_id) WHERE active`

</details>


## `app.alert_rule_target`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `rule_id` | uuid | não |  | `app.alert_rule` |  |
| `contact_id` | uuid | sim |  | `app.contact` |  |
| `responsibility` | text | sim |  |  |  |

**Restrições**

- `CHECK (((contact_id IS NOT NULL) OR (responsibility IS NOT NULL)))`
- `CHECK ((responsibility = ANY (ARRAY['unit_manager'::text, 'regional_supervisor'::text, 'personnel'::text, 'hr'::text, 'executive'::text, 'group'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `regra_destino_admin` | ALL | `(EXISTS ( SELECT 1` | `` |

<details><summary>Índices</summary>

- `alert_rule_target_contact_id_fkidx` — `app.alert_rule_target USING btree (contact_id)`
- `regra_destino_regra_idx` — `app.alert_rule_target USING btree (rule_id)`

</details>


## `app.alert_sent`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `queue_id` | uuid | sim |  | `app.alert_queue` |  |
| `rule_id` | uuid | sim |  | `app.alert_rule` |  |
| `channel` | text | não |  |  |  |
| `provider` | text | não |  |  |  |
| `destination_hash` | text | não |  |  |  |
| `provider_message_id` | text | sim |  |  |  |
| `status` | text | não |  |  |  |
| `error` | text | sim |  |  |  |
| `cost_cents` | integer | sim |  |  | Cloud API cobra por mensagem. Sem esse campo não dá para saber se a sustentação mensal está com margem negativa. |
| `sent_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((provider = ANY (ARRAY['evolution'::text, 'whatsapp_cloud'::text, 'smtp'::text, 'resend'::text])))`
- `CHECK ((status = ANY (ARRAY['sent'::text, 'delivered'::text, 'read'::text, 'failed'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `alert_sent_read` | SELECT | `util.is_admin(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `alert_sent_queue_id_fkidx` — `app.alert_sent USING btree (queue_id)`
- `alert_sent_rule_id_fkidx` — `app.alert_sent USING btree (rule_id)`
- `alert_sent_tenant_idx` — `app.alert_sent USING btree (tenant_id, sent_at DESC)`

</details>


## `app.audit_log`

> Cresce rápido. Quando passar de ~50M linhas, particionar por mês (created_at) e mover partição antiga para armazenamento frio.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | bigint | não |  |  |  |
| `tenant_id` | uuid | sim |  | `app.tenant` |  |
| `user_id` | uuid | sim |  | `auth.users` |  |
| `action` | text | não |  |  |  |
| `entity` | text | não |  |  |  |
| `entity_id` | text | sim |  |  |  |
| `antes` | jsonb | sim |  |  |  |
| `depois` | jsonb | sim |  |  |  |
| `ip` | inet | sim |  |  |  |
| `user_agent` | text | sim |  |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((action = ANY (ARRAY['insert'::text, 'update'::text, 'delete'::text, 'login'::text, 'export'::text, 'sensitive_query'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `audit_read` | SELECT | `util.is_admin(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `audit_log_entidade_idx` — `app.audit_log USING btree (entity, entity_id)`
- `audit_log_tenant_idx` — `app.audit_log USING btree (tenant_id, created_at DESC)`
- `audit_log_user_id_fkidx` — `app.audit_log USING btree (user_id)`

</details>


## `app.batida_marcacao`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `batida_id` | uuid | sim |  |  |  |
| `funcionario_id` | uuid | sim |  |  |  |
| `data` | date | sim |  |  |  |
| `hora` | time without time zone | sim |  |  |  |
| `tipo_coluna` | text | sim |  |  |  |
| `indice_coluna` | smallint | sim |  |  |  |
| `valor_bruto` | text | sim |  |  |  |
| `status_rotulo` | text | sim |  |  |  |
| `desconsiderada` | boolean | sim |  |  |  |
| `EquipId` | integer | sim |  |  |  |
| `FonteDadosId` | bigint | sim |  |  |  |
| `Memoria` | time without time zone | sim |  |  |  |
| `sincronizado_em` | timestamp with time zone | sim |  |  |  |
| `atualizado_em` | timestamp with time zone | sim | `now()` |  |  |
| `tenant_id` | uuid | sim | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `batida_marcacao_tenant_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `batida_marcacao_tenant_idx` — `app.batida_marcacao USING btree (tenant_id)`

</details>


## `app.company`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `cnpj` | text | sim |  |  |  |
| `legal_name` | text | não |  |  |  |
| `trade_name` | text | sim |  |  |  |
| `secullum_company_id` | bigint | sim |  |  |  |
| `active` | boolean | não | `true` |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((cnpj ~ '^\d{14}$'::text))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `company_read` | SELECT | `util.can_see_company(id)` | `-` |
| `company_write` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |

<details><summary>Índices</summary>

- `company_tenant_idx` — `app.company USING btree (tenant_id) WHERE active`
- `UNIQUE company_tenant_id_cnpj_key` — `app.company USING btree (tenant_id, cnpj)`
- `UNIQUE company_tenant_id_secullum_company_id_key` — `app.company USING btree (tenant_id, secullum_company_id)`

</details>


## `app.contact`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `name` | text | não |  |  |  |
| `whatsapp` | text | sim |  |  |  |
| `email` | text | sim |  |  |  |
| `type` | text | não | `'person'::text` |  |  |
| `active` | boolean | não | `true` |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((type = ANY (ARRAY['person'::text, 'whatsapp_group'::text, 'email_list'::text])))`
- `CHECK ((whatsapp ~ '^\+?\d{10,15}$'::text))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `contact_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |
| `contact_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `contact_tenant_idx` — `app.contact USING btree (tenant_id) WHERE active`

</details>


## `app.cost_center`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `company_id` | uuid | sim |  | `app.company` |  |
| `unit_id` | uuid | sim |  | `app.unit` |  |
| `code` | text | não |  |  |  |
| `name` | text | não |  |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `cost_center_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `cost_center_company_id_fkidx` — `app.cost_center USING btree (company_id)`
- `cost_center_unidade_idx` — `app.cost_center USING btree (unit_id)`
- `UNIQUE cost_center_tenant_id_code_key` — `app.cost_center USING btree (tenant_id, code)`

</details>


## `app.department`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `company_id` | uuid | não |  | `app.company` |  |
| `name` | text | não |  |  |  |
| `secullum_department_id` | bigint | sim |  |  |  |
| `active` | boolean | não | `true` |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `department_read` | SELECT | `util.can_see_company(company_id)` | `-` |

<details><summary>Índices</summary>

- `department_empresa_idx` — `app.department USING btree (company_id)`
- `UNIQUE department_tenant_id_secullum_department_id_key` — `app.department USING btree (tenant_id, secullum_department_id)`

</details>


## `app.detection_run`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `mode` | text | não |  |  |  |
| `period_start` | date | não |  |  |  |
| `period_end` | date | não |  |  |  |
| `started_at` | timestamp with time zone | não | `now()` |  |  |
| `finished_at` | timestamp with time zone | sim |  |  |  |
| `status` | text | não | `'running'::text` |  |  |
| `events_detected` | integer | não | `0` |  |  |
| `events_published` | integer | não | `0` |  |  |
| `engine_version` | text | sim |  |  |  |
| `error` | text | sim |  |  |  |
| `scope` | text | não | `'incremental'::text` |  | incremental = current day, after each sync (48x/day). backfill = 7-day retroactive window, once a day, off-peak. |

**Restrições**

- `CHECK ((mode = ANY (ARRAY['shadow'::text, 'production'::text])))`
- `CHECK ((scope = ANY (ARRAY['incremental'::text, 'backfill'::text])))`
- `CHECK ((status = ANY (ARRAY['running'::text, 'completed'::text, 'failed'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `detection_run_read` | SELECT | `util.is_admin(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `detection_run_backfill_idx` — `app.detection_run USING btree (tenant_id, started_at DESC) WHERE ((scope = 'backfill'::text) AND (status = 'completed'::text))`
- `detection_run_incremental_idx` — `app.detection_run USING btree (tenant_id, started_at DESC) WHERE ((scope = 'incremental'::text) AND (status = 'completed'::text))`
- `detection_run_tenant_idx` — `app.detection_run USING btree (tenant_id, started_at DESC)`

</details>


## `app.deviation_event`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `employee_id` | uuid | não |  | `app.employee` |  |
| `company_id` | uuid | não |  | `app.company` |  |
| `unit_id` | uuid | sim |  | `app.unit` |  |
| `reference_date` | date | não |  |  | Data do fato. Dashboard SEMPRE filtra por ela. Relatório agrupa por ciclo — quando um desvio é detectado tarde, o relatório declara "inclui N ocorrências de dias anteriores". |
| `type` | text | não |  | `app.deviation_type` |  |
| `minutes` | integer | não | `0` |  | Assinado. Soma direta responde "minutos líquidos"; abs() responde "minutos de desvio". Nunca chamar de hora extra. |
| `expected_time` | time without time zone | sim |  |  |  |
| `actual_time` | time without time zone | sim |  |  |  |
| `punch_ids` | bigint[] | não | `'{}'::bigint[]` |  |  |
| `status` | text | não | `'active'::text` |  |  |
| `supersede_id` | uuid | sim |  | `app.deviation_event` |  |
| `status_reason` | text | sim |  |  |  |
| `mode` | text | não | `'production'::text` |  |  |
| `run_id` | uuid | sim |  | `app.detection_run` |  |
| `report_cycle_id` | uuid | sim |  | `app.report_cycle` |  |
| `detected_at` | timestamp with time zone | não | `now()` |  |  |
| `updated_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((mode = ANY (ARRAY['shadow'::text, 'production'::text])))`
- `CHECK ((status = ANY (ARRAY['active'::text, 'revoked'::text, 'justified'::text, 'ignored'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `deviation_read` | SELECT | `(((mode = 'production'::text) OR util.is_admin(tenant_id)) AND (util.is_admin(tenant_id) OR ((unit_id IS NOT N` | `-` |
| `deviation_write` | UPDATE | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |

<details><summary>Índices</summary>

- `deviation_event_ciclo_idx` — `app.deviation_event USING btree (report_cycle_id) WHERE (report_cycle_id IS NOT NULL)`
- `deviation_event_colab_idx` — `app.deviation_event USING btree (employee_id, reference_date DESC) WHERE ((status = 'active'::text) AND (mode = 'production'::text))`
- `deviation_event_company_id_fkidx` — `app.deviation_event USING btree (company_id)`
- `deviation_event_dash_idx` — `app.deviation_event USING btree (tenant_id, reference_date, unit_id) WHERE ((status = 'active'::text) AND (mode = 'production'::text))`
- `deviation_event_execucao_idx` — `app.deviation_event USING btree (run_id)`
- `deviation_event_pendente_idx` — `app.deviation_event USING btree (tenant_id, unit_id) WHERE ((report_cycle_id IS NULL) AND (status = 'active'::text) AND (mode = 'production'::text))`
- `deviation_event_supersede_idx` — `app.deviation_event USING btree (supersede_id)`
- `deviation_event_type_fkidx` — `app.deviation_event USING btree (type)`
- `deviation_event_unit_id_fkidx` — `app.deviation_event USING btree (unit_id)`
- `deviation_periodo_idx` — `app.deviation_event USING btree (tenant_id, unit_id, reference_date) WHERE ((status = 'active'::text) AND (mode = 'production'::text))`
- `deviation_tipo_periodo_idx` — `app.deviation_event USING btree (tenant_id, type, reference_date) WHERE ((status = 'active'::text) AND (mode = 'production'::text))`
- `UNIQUE deviation_event_unico_active` — `app.deviation_event USING btree (employee_id, reference_date, type) WHERE ((status = 'active'::text) AND (mode = 'production'::text))`

</details>


## `app.deviation_type`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `code` 🔑 | text | não |  |  |  |
| `description` | text | não |  |  |  |
| `direction` | text | não |  |  |  |
| `category` | text | não |  |  |  |

**Restrições**

- `CHECK ((category = ANY (ARRAY['entry'::text, 'exit'::text, 'break'::text, 'integrity'::text, 'roster'::text, 'perimeter'::text])))`
- `CHECK ((direction = ANY (ARRAY['surplus'::text, 'shortfall'::text, 'neutral'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `deviation_type_read` | SELECT | `true` | `-` |


## `app.deviation_type_config`

> Onde a decisão "direção do desvio contabilizada" vive. Cliente diferente, política diferente, mesmo schema.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `tenant_id` 🔑 | uuid | não |  | `app.tenant` |  |
| `code` 🔑 | text | não |  | `app.deviation_type` |  |
| `active` | boolean | não | `true` |  |  |
| `counts_as_deviation` | boolean | não | `true` |  |  |
| `triggers_alert` | boolean | não | `false` |  |  |
| `tolerance_extra_minutes` | integer | sim |  |  |  |
| `tolerance_absence_minutes` | integer | sim |  |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `desvio_config_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |
| `desvio_config_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `deviation_type_config_code_fkidx` — `app.deviation_type_config USING btree (code)`

</details>


## `app.document`

> O arquivo vive no Supabase Storage. A policy do bucket precisa espelhar util.can_see_employee — RLS de tabela não protege o objeto.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `employee_id` | uuid | não |  | `app.employee` |  |
| `type_id` | uuid | não |  | `app.document_type` |  |
| `storage_bucket` | text | não | `'documentos'::text` |  |  |
| `storage_path` | text | não |  |  |  |
| `file_name` | text | sim |  |  |  |
| `issued_on` | date | sim |  |  |  |
| `valid_until` | date | sim |  |  |  |
| `status` | text | não | `'active'::text` |  |  |
| `replaces_id` | uuid | sim |  | `app.document` |  |
| `created_by` | uuid | sim |  | `auth.users` |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((status = ANY (ARRAY['active'::text, 'vencido'::text, 'substituido'::text, 'removido'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `document_read` | SELECT | `(util.can_see_employee(employee_id) AND (EXISTS ( SELECT 1` | `` |
| `document_write` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |

<details><summary>Índices</summary>

- `document_colab_idx` — `app.document USING btree (employee_id, type_id)`
- `document_created_by_fkidx` — `app.document USING btree (created_by)`
- `document_replaces_id_fkidx` — `app.document USING btree (replaces_id)`
- `document_type_id_fkidx` — `app.document USING btree (type_id)`
- `document_vencimento_idx` — `app.document USING btree (tenant_id, valid_until) WHERE ((status = 'active'::text) AND (valid_until IS NOT NULL))`
- `UNIQUE document_storage_bucket_storage_path_key` — `app.document USING btree (storage_bucket, storage_path)`

</details>


## `app.document_type`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `name` | text | não |  |  |  |
| `requires_expiry` | boolean | não | `false` |  |  |
| `expiry_alert_days` | integer | não | `30` |  |  |
| `required` | boolean | não | `false` |  |  |
| `domain` | app.sensitive_domain | não | `'pii'::app.sensitive_domain` |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `document_type_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |
| `document_type_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `UNIQUE document_type_tenant_id_name_key` — `app.document_type USING btree (tenant_id, name)`

</details>


## `app.domain_permission`

> Salário, RG, ASO e ocorrência disciplinar são decisão de dado, não de código.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `tenant_id` 🔑 | uuid | não |  | `app.tenant` |  |
| `role` 🔑 | app.user_role | não |  |  |  |
| `domain` 🔑 | app.sensitive_domain | não |  |  |  |
| `allowed` | boolean | não | `false` |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `domain_permission_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `domain_permission_rls_idx` — `app.domain_permission USING btree (tenant_id, role, domain) WHERE allowed`

</details>


## `app.employee`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `company_id` | uuid | não |  | `app.company` | Sempre pelo caminho Funcionario->Empresa. NUNCA derivar de Departamento->Empresa (26% divergem). |
| `unit_id` | uuid | sim |  | `app.unit` |  |
| `department_id` | uuid | sim |  | `app.department` |  |
| `secullum_employee_id` | bigint | sim |  |  |  |
| `registration_number` | text | sim |  |  |  |
| `name` | text | não |  |  |  |
| `cargo` | text | sim |  |  |  |
| `employment_type` | text | sim |  |  |  |
| `hired_on` | date | sim |  |  |  |
| `terminated_on` | date | sim |  |  |  |
| `manager_employee_id` | uuid | sim |  | `app.employee` |  |
| `status` | text | não | `'active'::text` |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |
| `updated_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK (((terminated_on IS NULL) OR (hired_on IS NULL) OR (terminated_on >= hired_on)))`
- `CHECK ((employment_type = ANY (ARRAY['clt'::text, 'pj'::text, 'internship'::text, 'temporary'::text, 'apprentice'::text, 'contractor'::text])))`
- `CHECK ((status = ANY (ARRAY['active'::text, 'afastado'::text, 'vacation'::text, 'desligado'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `employee_read` | SELECT | `(util.is_admin(tenant_id) OR ((unit_id IS NOT NULL) AND util.can_see_unit(unit_id)) OR ((unit_id IS NULL) AND ` | `-` |
| `employee_write` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |

<details><summary>Índices</summary>

- `employee_departamento_idx` — `app.employee USING btree (department_id)`
- `employee_empresa_idx` — `app.employee USING btree (company_id)`
- `employee_gestor_idx` — `app.employee USING btree (manager_employee_id)`
- `employee_tenant_unidade_idx` — `app.employee USING btree (tenant_id, unit_id) WHERE (status <> 'desligado'::text)`
- `employee_unit_id_fkidx` — `app.employee USING btree (unit_id)`
- `UNIQUE employee_tenant_id_secullum_employee_id_key` — `app.employee USING btree (tenant_id, secullum_employee_id)`

</details>


## `app.employee_compensation`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `employee_id` | uuid | não |  | `app.employee` |  |
| `effective_from` | date | não |  |  |  |
| `effective_to` | date | sim |  |  |  |
| `salary` | numeric(14,2) | não |  |  |  |
| `reason` | text | sim |  |  |  |
| `recorded_by` | uuid | sim |  | `auth.users` |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK (((effective_to IS NULL) OR (effective_to >= effective_from)))`
- `CHECK ((salary >= (0)::numeric))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `remuneracao_read` | SELECT | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.can_see_employee(employee_id))` | `-` |
| `remuneracao_write` | ALL | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.is_admin(tenant_id))` | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) ` |

<details><summary>Índices</summary>

- `employee_compensation_recorded_by_fkidx` — `app.employee_compensation USING btree (recorded_by)`
- `employee_compensation_tenant_id_fkidx` — `app.employee_compensation USING btree (tenant_id)`
- `remuneracao_colab_idx` — `app.employee_compensation USING btree (employee_id, effective_from DESC)`

</details>


## `app.employee_pii`

> Dado pessoal direto. Acesso exige util.can_see_domain(tenant, 'pii'). Nunca entra em view de dashboard.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `employee_id` 🔑 | uuid | não |  | `app.employee` |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `cpf` | text | sim |  |  |  |
| `rg` | text | sim |  |  |  |
| `pis` | text | sim |  |  |  |
| `ctps` | text | sim |  |  |  |
| `birth_date` | date | sim |  |  |  |
| `mother_name` | text | sim |  |  |  |
| `father_name` | text | sim |  |  |  |
| `phone` | text | sim |  |  |  |
| `personal_email` | text | sim |  |  |  |
| `address` | jsonb | sim |  |  |  |
| `updated_at` | timestamp with time zone | não | `now()` |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `pii_read` | SELECT | `(util.can_see_domain(tenant_id, 'pii'::app.sensitive_domain) AND util.can_see_employee(employee_id))` | `-` |
| `pii_write` | ALL | `(util.can_see_domain(tenant_id, 'pii'::app.sensitive_domain) AND util.is_admin(tenant_id))` | `(util.can_see_domain(tenant_id, 'pii'::app.sensitive_domain) AND util.` |

<details><summary>Índices</summary>

- `employee_pii_tenant_idx` — `app.employee_pii USING btree (tenant_id)`

</details>


## `app.employee_position`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `employee_id` | uuid | não |  | `app.employee` |  |
| `effective_from` | date | não |  |  |  |
| `effective_to` | date | sim |  |  |  |
| `cargo` | text | não |  |  |  |
| `unit_id` | uuid | sim |  | `app.unit` |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `responsibility_read` | SELECT | `util.can_see_employee(employee_id)` | `-` |

<details><summary>Índices</summary>

- `employee_position_tenant_id_fkidx` — `app.employee_position USING btree (tenant_id)`
- `employee_position_unit_id_fkidx` — `app.employee_position USING btree (unit_id)`
- `responsibility_colab_idx` — `app.employee_position USING btree (employee_id, effective_from DESC)`

</details>


## `app.empresa_evento_status`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | bigint | não |  |  |  |
| `empresa_id` | bigint | sim |  |  |  |
| `status` | text | sim |  |  |  |
| `ocorrido_em` | timestamp with time zone | sim | `now()` |  |  |
| `tenant_id` | uuid | sim | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `empresa_evento_status_tenant_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `empresa_evento_status_tenant_idx` — `app.empresa_evento_status USING btree (tenant_id)`

</details>


## `app.expected_workday`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `employee_id` 🔑 | uuid | não |  | `app.employee` |  |
| `reference_date` 🔑 | date | não |  |  |  |
| `day_type` | text | não |  |  |  |
| `expected_entry` | time without time zone | sim |  |  |  |
| `expected_exit` | time without time zone | sim |  |  |  |
| `expected_break_minutes` | integer | sim |  |  |  |
| `workload_minutes` | integer | sim |  |  |  |
| `tolerance_extra_minutes` | integer | não | `0` |  |  |
| `tolerance_absence_minutes` | integer | não | `0` |  |  |
| `secullum_schedule_id` | bigint | sim |  |  |  |
| `source` | text | não |  |  |  |
| `confidence` | smallint | não | `100` |  | Escala 12x36 inferida a partir do Horario do Secullum costuma ficar abaixo de 100. Linha com confidence baixa NÃO deve gerar alerta automático. |

**Restrições**

- `CHECK (((confidence >= 0) AND (confidence <= 100)))`
- `CHECK ((day_type = ANY (ARRAY['work'::text, 'day_off'::text, 'vacation'::text, 'leave_period'::text, 'holiday'::text, 'compensated'::text])))`
- `CHECK ((source = ANY (ARRAY['secullum_schedule'::text, 'manual_roster'::text, 'inferred'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `expected_workday_read` | SELECT | `util.can_see_employee(employee_id)` | `-` |

<details><summary>Índices</summary>

- `expected_workday_baixa_confianca_idx` — `app.expected_workday USING btree (tenant_id, reference_date) WHERE (confidence < 80)`
- `expected_workday_tenant_data_idx` — `app.expected_workday USING btree (tenant_id, reference_date)`

</details>


## `app.file_import`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `type` | text | não |  |  |  |
| `payroll_period_id` | uuid | sim |  | `app.payroll_period` |  |
| `storage_path` | text | não |  |  |  |
| `file_name` | text | sim |  |  |  |
| `layout_version` | text | sim |  |  |  |
| `uploaded_by` | uuid | sim |  | `auth.users` |  |
| `status` | text | não | `'received'::text` |  |  |
| `rows_total` | integer | sim |  |  |  |
| `rows_ok` | integer | sim |  |  |  |
| `rows_error` | integer | sim |  |  |  |
| `report` | jsonb | sim |  |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((status = ANY (ARRAY['received'::text, 'validating'::text, 'validation_error'::text, 'processed'::text, 'discarded'::text])))`
- `CHECK ((type = ANY (ARRAY['folha'::text, 'payroll_charge'::text, 'employee'::text, 'cost_center'::text, 'roster'::text, 'benefit'::text, 'other'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `importacao_read` | SELECT | `util.is_admin(tenant_id)` | `-` |
| `importacao_write` | INSERT | `-` | `util.is_admin(tenant_id)` |

<details><summary>Índices</summary>

- `file_import_payroll_period_id_fkidx` — `app.file_import USING btree (payroll_period_id)`
- `file_import_uploaded_by_fkidx` — `app.file_import USING btree (uploaded_by)`
- `importacao_tenant_idx` — `app.file_import USING btree (tenant_id, created_at DESC)`

</details>


## `app.financial_agreement`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `employee_id` | uuid | não |  | `app.employee` |  |
| `type` | text | não |  |  |  |
| `description` | text | sim |  |  |  |
| `total_amount` | numeric(14,2) | não |  |  |  |
| `installment_count` | integer | não | `1` |  |  |
| `agreement_date` | date | não |  |  |  |
| `document_id` | uuid | não |  | `app.document` | NOT NULL de propósito: desconto sem autorização documentada não se registra. |
| `authorized_by` | uuid | não |  | `auth.users` |  |
| `authorized_at` | timestamp with time zone | não | `now()` |  |  |
| `status` | text | não | `'active'::text` |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((installment_count >= 1))`
- `CHECK ((status = ANY (ARRAY['active'::text, 'settled'::text, 'cancelled'::text, 'suspended'::text])))`
- `CHECK ((total_amount > (0)::numeric))`
- `CHECK ((type = ANY (ARRAY['installment_plan'::text, 'vehicle_damage'::text, 'equipment_damage'::text, 'advance'::text, 'loan'::text, 'benefit'::text, 'other'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `acordo_read` | SELECT | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.can_see_employee(employee_id))` | `-` |
| `acordo_write` | ALL | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.is_admin(tenant_id))` | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) ` |

<details><summary>Índices</summary>

- `acordo_colab_idx` — `app.financial_agreement USING btree (employee_id, status)`
- `financial_agreement_authorized_by_fkidx` — `app.financial_agreement USING btree (authorized_by)`
- `financial_agreement_document_id_fkidx` — `app.financial_agreement USING btree (document_id)`
- `financial_agreement_tenant_id_fkidx` — `app.financial_agreement USING btree (tenant_id)`

</details>


## `app.financial_threshold`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `company_id` | uuid | sim |  | `app.company` |  |
| `unit_id` | uuid | sim |  | `app.unit` |  |
| `indicator` | text | não |  |  |  |
| `operator` | text | não |  |  |  |
| `amount` | numeric(14,2) | não |  |  |  |
| `active` | boolean | não | `true` |  |  |

**Restrições**

- `CHECK ((indicator = ANY (ARRAY['total_payroll'::text, 'unit_cost'::text, 'cost_per_employee'::text, 'overtime'::text, 'payroll_charge'::text, 'terminations'::text])))`
- `CHECK ((operator = ANY (ARRAY['greater_than'::text, 'less_than'::text, 'percent_change'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `limiar_admin` | ALL | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.is_admin(tenant_id))` | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) ` |

<details><summary>Índices</summary>

- `financial_threshold_company_id_fkidx` — `app.financial_threshold USING btree (company_id)`
- `financial_threshold_tenant_idx` — `app.financial_threshold USING btree (tenant_id) WHERE active`
- `financial_threshold_unit_id_fkidx` — `app.financial_threshold USING btree (unit_id)`

</details>


## `app.funcionario_evento_status`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | bigint | não |  |  |  |
| `funcionario_id` | bigint | sim |  |  |  |
| `status` | text | sim |  |  |  |
| `ocorrido_em` | timestamp with time zone | sim | `now()` |  |  |
| `tenant_id` | uuid | sim | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `funcionario_evento_status_tenant_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `funcionario_evento_status_tenant_idx` — `app.funcionario_evento_status USING btree (tenant_id)`

</details>


## `app.integration`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `provider` | text | não |  |  |  |
| `alias` | text | sim |  |  |  |
| `config` | jsonb | não | `'{}'::jsonb` |  |  |
| `active` | boolean | não | `false` |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((provider = ANY (ARRAY['secullum'::text, 'domain'::text, 'evolution'::text, 'whatsapp_cloud'::text, 'smtp'::text, 'spreadsheet'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `integration_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |

<details><summary>Índices</summary>

- `UNIQUE integration_tenant_id_provider_alias_key` — `app.integration USING btree (tenant_id, provider, alias)`

</details>


## `app.integration_secret`

> Só o ponteiro. O amount está no Vault. Nenhum role do painel lê esta tabela — nem owner.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `integration_id` 🔑 | uuid | não |  | `app.integration` |  |
| `key` 🔑 | text | não |  |  |  |
| `vault_id` | uuid | não |  |  |  |
| `updated_at` | timestamp with time zone | não | `now()` |  |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.


## `app.justification`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `deviation_event_id` | uuid | sim |  | `app.deviation_event` |  |
| `employee_id` | uuid | não |  | `app.employee` |  |
| `reference_date` | date | não |  |  |  |
| `text` | text | não |  |  |  |
| `source` | text | não | `'operax'::text` |  |  |
| `author_user_id` | uuid | sim |  | `auth.users` |  |
| `author_name` | text | sim |  |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((source = ANY (ARRAY['secullum'::text, 'operax'::text, 'whatsapp'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `justification_read` | SELECT | `util.can_see_employee(employee_id)` | `-` |
| `justification_write` | INSERT | `-` | `util.can_see_employee(employee_id)` |

<details><summary>Índices</summary>

- `justification_author_user_id_fkidx` — `app.justification USING btree (author_user_id)`
- `justification_colab_idx` — `app.justification USING btree (employee_id, reference_date DESC)`
- `justification_evento_idx` — `app.justification USING btree (deviation_event_id)`
- `justification_tenant_id_fkidx` — `app.justification USING btree (tenant_id)`

</details>


## `app.leave_period`

> Rótulo neutro por decisão de produto. Motivo de leave_period é dado de saúde e não é capturado.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `employee_id` | uuid | não |  | `app.employee` |  |
| `category` | text | não |  |  |  |
| `start_date` | date | não |  |  |  |
| `end_date` | date | sim |  |  |  |
| `source` | text | não | `'secullum'::text` |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK (((end_date IS NULL) OR (end_date >= start_date)))`
- `CHECK ((category = ANY (ARRAY['vacation'::text, 'leave_period'::text, 'leave_of_absence'::text, 'suspension'::text])))`
- `CHECK ((source = ANY (ARRAY['secullum'::text, 'manual'::text, 'spreadsheet'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `leave_period_read` | SELECT | `util.can_see_employee(employee_id)` | `-` |

<details><summary>Índices</summary>

- `leave_period_periodo_idx` — `app.leave_period USING btree (employee_id, start_date, end_date)`
- `leave_period_tenant_id_fkidx` — `app.leave_period USING btree (tenant_id)`

</details>


## `app.metric`

> Catálogo fechado do assistente de IA. Métrica ausente daqui = question que ele responde "não tenho esse dado", em vez de inventar.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `code` 🔑 | text | não |  |  |  |
| `title` | text | não |  |  |  |
| `description` | text | não |  |  |  |
| `target_view` | text | não |  |  |  |
| `dimensions` | text[] | não | `'{}'::text[]` |  |  |
| `filters` | text[] | não | `'{}'::text[]` |  |  |
| `domain` | app.sensitive_domain | sim |  |  |  |
| `active` | boolean | não | `true` |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `metric_read` | SELECT | `active` | `-` |


## `app.mv_deviation_day`

*materialized view — **não respeita RLS por natureza** — contém todos os tenants, não é exposta, só é lida server-side com `service_role`*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `tenant_id` | uuid | sim |  |  |  |
| `reference_date` | date | sim |  |  |  |
| `company_id` | uuid | sim |  |  |  |
| `unit_id` | uuid | sim |  |  |  |
| `type` | text | sim |  |  |  |
| `eventos` | bigint | sim |  |  |  |
| `colaboradores` | bigint | sim |  |  |  |
| `minutes_excedente` | bigint | sim |  |  |  |
| `minutes_faltante` | bigint | sim |  |  |  |

<details><summary>Índices</summary>

- `mv_deviation_day_periodo_idx` — `app.mv_deviation_day USING btree (tenant_id, reference_date)`
- `UNIQUE mv_deviation_day_pk` — `app.mv_deviation_day USING btree (tenant_id, reference_date, company_id, COALESCE(unit_id, '00000000-0000-0000-0000-000000000000'::uuid), type)`

</details>


## `app.occupational_exam`

> DADO DE SAÚDE (LGPD art. 5º II). Sem diagnóstico, sem CID, sem descrição de restrição. Só aptidão e validade.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `employee_id` | uuid | não |  | `app.employee` |  |
| `type` | text | não |  |  |  |
| `performed_on` | date | não |  |  |  |
| `valid_until` | date | sim |  |  |  |
| `result` | text | sim |  |  |  |
| `document_id` | uuid | sim |  | `app.document` |  |
| `created_by` | uuid | sim |  | `auth.users` |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((result = ANY (ARRAY['fit'::text, 'unfit'::text, 'fit_with_restriction'::text])))`
- `CHECK ((type = ANY (ARRAY['pre_employment'::text, 'periodic'::text, 'exit'::text, 'return_to_work_exam'::text, 'job_change'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `exame_read` | SELECT | `(util.can_see_domain(tenant_id, 'health'::app.sensitive_domain) AND util.can_see_employee(employee_id))` | `-` |
| `exame_write` | ALL | `util.can_see_domain(tenant_id, 'health'::app.sensitive_domain)` | `util.can_see_domain(tenant_id, 'health'::app.sensitive_domain)` |

<details><summary>Índices</summary>

- `exame_colab_idx` — `app.occupational_exam USING btree (employee_id, performed_on DESC)`
- `exame_vencimento_idx` — `app.occupational_exam USING btree (tenant_id, valid_until) WHERE (valid_until IS NOT NULL)`
- `occupational_exam_created_by_fkidx` — `app.occupational_exam USING btree (created_by)`
- `occupational_exam_document_id_fkidx` — `app.occupational_exam USING btree (document_id)`

</details>


## `app.payroll_charge`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `payroll_period_id` | uuid | não |  | `app.payroll_period` |  |
| `company_id` | uuid | não |  | `app.company` |  |
| `unit_id` | uuid | sim |  | `app.unit` |  |
| `type` | text | não |  |  |  |
| `calculation_base` | numeric(14,2) | sim |  |  |  |
| `amount` | numeric(14,2) | não |  |  |  |
| `source` | text | não |  |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((source = ANY (ARRAY['domain_api'::text, 'spreadsheet'::text, 'file'::text, 'manual'::text])))`
- `CHECK ((type = ANY (ARRAY['fgts'::text, 'inss_employer'::text, 'inss_withheld'::text, 'irrf'::text, 'rat'::text, 'third_parties'::text, 'vacation_accrual'::text, 'thirteenth_accrual'::text, 'other'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `payroll_charge_read` | SELECT | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.can_see_company(company_id))` | `-` |

<details><summary>Índices</summary>

- `payroll_charge_comp_idx` — `app.payroll_charge USING btree (payroll_period_id, company_id)`
- `payroll_charge_company_id_fkidx` — `app.payroll_charge USING btree (company_id)`
- `payroll_charge_tenant_id_fkidx` — `app.payroll_charge USING btree (tenant_id)`
- `payroll_charge_unit_id_fkidx` — `app.payroll_charge USING btree (unit_id)`

</details>


## `app.payroll_entry`

> Espelho do que a folha oficial calculou. O OperaX NÃO calcula obrigação trabalhista — item 20 do escopo.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `payroll_period_id` | uuid | não |  | `app.payroll_period` |  |
| `employee_id` | uuid | sim |  | `app.employee` |  |
| `company_id` | uuid | não |  | `app.company` |  |
| `unit_id` | uuid | sim |  | `app.unit` |  |
| `cost_center_id` | uuid | sim |  | `app.cost_center` |  |
| `code` | text | não |  |  |  |
| `description` | text | sim |  |  |  |
| `nature` | text | não |  |  |  |
| `reference` | numeric(14,4) | sim |  |  |  |
| `amount` | numeric(14,2) | não |  |  |  |
| `source` | text | não |  |  |  |
| `import_id` | uuid | sim |  | `app.file_import` |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((nature = ANY (ARRAY['earning'::text, 'deduction'::text, 'base'::text, 'payroll_charge'::text, 'informational'::text])))`
- `CHECK ((source = ANY (ARRAY['domain_api'::text, 'spreadsheet'::text, 'file'::text, 'manual'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `payroll_entry_read` | SELECT | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND (util.is_admin(tenant_id) OR ((unit_` | `-` |

<details><summary>Índices</summary>

- `payroll_entry_cc_idx` — `app.payroll_entry USING btree (cost_center_id)`
- `payroll_entry_colab_idx` — `app.payroll_entry USING btree (employee_id, payroll_period_id)`
- `payroll_entry_comp_idx` — `app.payroll_entry USING btree (payroll_period_id, company_id)`
- `payroll_entry_company_id_fkidx` — `app.payroll_entry USING btree (company_id)`
- `payroll_entry_import_idx` — `app.payroll_entry USING btree (import_id)`
- `payroll_entry_tenant_id_fkidx` — `app.payroll_entry USING btree (tenant_id)`
- `payroll_entry_unidade_idx` — `app.payroll_entry USING btree (unit_id, payroll_period_id)`

</details>


## `app.payroll_period`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `year` | smallint | não |  |  |  |
| `month` | smallint | não |  |  |  |
| `status` | text | não | `'aberta'::text` |  |  |
| `closed_at` | timestamp with time zone | sim |  |  |  |

**Restrições**

- `CHECK (((month >= 1) AND (month <= 13)))`
- `CHECK (((year >= 2000) AND (year <= 2100)))`
- `CHECK ((status = ANY (ARRAY['aberta'::text, 'importada'::text, 'conferida'::text, 'fechada'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `payroll_period_read` | SELECT | `util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain)` | `-` |

<details><summary>Índices</summary>

- `UNIQUE payroll_period_tenant_id_year_month_key` — `app.payroll_period USING btree (tenant_id, year, month)`

</details>


## `app.report_cycle`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `unit_id` | uuid | sim |  | `app.unit` |  |
| `period_start` | date | não |  |  |  |
| `period_end` | date | não |  |  |  |
| `generated_at` | timestamp with time zone | não | `now()` |  |  |
| `sent_at` | timestamp with time zone | sim |  |  |  |
| `channel` | text | sim |  |  |  |
| `status` | text | não | `'open'::text` |  |  |
| `total_events` | integer | não | `0` |  |  |

**Restrições**

- `CHECK ((channel = ANY (ARRAY['whatsapp'::text, 'email'::text, 'both'::text])))`
- `CHECK ((period_end >= period_start))`
- `CHECK ((status = ANY (ARRAY['open'::text, 'sent'::text, 'failed'::text, 'cancelled'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `ciclo_read` | SELECT | `(((unit_id IS NULL) AND util.is_admin(tenant_id)) OR util.can_see_unit(unit_id))` | `-` |

<details><summary>Índices</summary>

- `report_cycle_tenant_id_fkidx` — `app.report_cycle USING btree (tenant_id)`
- `report_cycle_unidade_idx` — `app.report_cycle USING btree (unit_id, period_start DESC)`

</details>


## `app.sync_run`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `integration_id` | uuid | não |  | `app.integration` |  |
| `entity` | text | não |  |  |  |
| `started_at` | timestamp with time zone | não | `now()` |  |  |
| `finished_at` | timestamp with time zone | sim |  |  |  |
| `status` | text | não | `'running'::text` |  |  |
| `cursor_until` | timestamp with time zone | sim |  |  |  |
| `records_read` | integer | não | `0` |  |  |
| `records_written` | integer | não | `0` |  |  |
| `error` | text | sim |  |  |  |

**Restrições**

- `CHECK ((status = ANY (ARRAY['running'::text, 'completed'::text, 'failed'::text, 'partial'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `sync_read` | SELECT | `util.is_admin(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `sync_run_falha_idx` — `app.sync_run USING btree (tenant_id, started_at DESC) WHERE (status = 'failed'::text)`
- `sync_run_freshness_idx` — `app.sync_run USING btree (tenant_id, entity, finished_at DESC) WHERE (status = 'completed'::text)`
- `sync_run_idx` — `app.sync_run USING btree (integration_id, entity, started_at DESC)`

</details>


## `app.tenant`

> OperaX customer. Kastro Park is the first.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `slug` | text | não |  |  |  |
| `name` | text | não |  |  |  |
| `active` | boolean | não | `true` |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((slug ~ '^[a-z0-9-]{2,40}$'::text))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `tenant_read` | SELECT | `util.has_tenant(id)` | `-` |

<details><summary>Índices</summary>

- `UNIQUE tenant_slug_key` — `app.tenant USING btree (slug)`

</details>


## `app.tenant_member`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `tenant_id` 🔑 | uuid | não |  | `app.tenant` |  |
| `user_id` 🔑 | uuid | não |  | `auth.users` |  |
| `role` | app.user_role | não |  |  |  |
| `active` | boolean | não | `true` |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `tenant_member_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |
| `tenant_member_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `tenant_member_rls_idx` — `app.tenant_member USING btree (user_id, tenant_id, role) WHERE active`
- `tenant_member_user_idx` — `app.tenant_member USING btree (user_id) WHERE active`

</details>


## `app.unit`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `company_id` | uuid | não |  | `app.company` |  |
| `code` | text | não |  |  |  |
| `name` | text | não |  |  |  |
| `address` | text | sim |  |  |  |
| `timezone` | text | não | `'America/Sao_Paulo'::text` |  |  |
| `active` | boolean | não | `true` |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `unit_read` | SELECT | `util.can_see_unit(id)` | `-` |
| `unit_write` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |

<details><summary>Índices</summary>

- `unit_company_id_fkidx` — `app.unit USING btree (company_id)`
- `unit_tenant_empresa_idx` — `app.unit USING btree (tenant_id, company_id) WHERE active`
- `UNIQUE unit_tenant_id_code_key` — `app.unit USING btree (tenant_id, code)`

</details>


## `app.unit_responsible`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `unit_id` | uuid | não |  | `app.unit` |  |
| `contact_id` | uuid | não |  | `app.contact` |  |
| `responsibility` | text | não |  |  |  |
| `is_primary` | boolean | não | `false` |  |  |

**Restrições**

- `CHECK ((responsibility = ANY (ARRAY['unit_manager'::text, 'regional_supervisor'::text, 'personnel'::text, 'hr'::text, 'executive'::text, 'group'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `unit_responsible_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |
| `unit_responsible_read` | SELECT | `util.can_see_unit(unit_id)` | `-` |

<details><summary>Índices</summary>

- `unit_responsible_contact_id_fkidx` — `app.unit_responsible USING btree (contact_id)`
- `unit_responsible_tenant_id_fkidx` — `app.unit_responsible USING btree (tenant_id)`
- `unit_responsible_unidade_idx` — `app.unit_responsible USING btree (unit_id)`
- `UNIQUE unit_responsible_unit_id_contact_id_responsibility_key` — `app.unit_responsible USING btree (unit_id, contact_id, responsibility)`

</details>


## `app.unit_secullum_map`

> Resolve a divergência Empresa x Departamento do Secullum. Linha sem validated_at = mapeamento provisório, sinalizar na UI.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `tenant_id` 🔑 | uuid | não |  | `app.tenant` |  |
| `secullum_department_id` 🔑 | bigint | não |  |  |  |
| `unit_id` | uuid | não |  | `app.unit` |  |
| `validated_by` | uuid | sim |  | `auth.users` |  |
| `validated_at` | timestamp with time zone | sim |  |  |  |
| `notes` | text | sim |  |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `mapa_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |

<details><summary>Índices</summary>

- `unit_mapa_unidade_idx` — `app.unit_secullum_map USING btree (unit_id)`
- `unit_secullum_map_validated_by_fkidx` — `app.unit_secullum_map USING btree (validated_by)`

</details>


## `app.user_scope`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `user_id` | uuid | não |  | `auth.users` |  |
| `company_id` | uuid | sim |  | `app.company` |  |
| `unit_id` | uuid | sim |  | `app.unit` |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `escopo_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |
| `escopo_read` | SELECT | `((user_id = ( SELECT auth.uid() AS uid)) OR util.is_admin(tenant_id))` | `-` |

<details><summary>Índices</summary>

- `escopo_rls_idx` — `app.user_scope USING btree (user_id, tenant_id, company_id, unit_id)`
- `user_scope_empresa_idx` — `app.user_scope USING btree (company_id) WHERE (company_id IS NOT NULL)`
- `user_scope_lookup_idx` — `app.user_scope USING btree (user_id, tenant_id)`
- `user_scope_tenant_id_fkidx` — `app.user_scope USING btree (tenant_id)`
- `user_scope_unidade_idx` — `app.user_scope USING btree (unit_id) WHERE (unit_id IS NOT NULL)`

</details>


## `app.work_schedule_day`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `work_schedule_id` | uuid | sim |  |  |  |
| `secullum_horario_dia_id` | integer | sim |  |  |  |
| `weekday` | smallint | sim |  |  |  |
| `day_type` | smallint | sim |  |  |  |
| `is_day_off` | boolean | sim |  |  |  |
| `is_neutral` | boolean | sim |  |  |  |
| `is_compensated` | boolean | sim |  |  |  |
| `free_lunch` | boolean | sim |  |  |  |
| `allocate_24_hours` | boolean | sim |  |  |  |
| `entry_1` | time without time zone | sim |  |  |  |
| `exit_1` | time without time zone | sim |  |  |  |
| `entry_2` | time without time zone | sim |  |  |  |
| `exit_2` | time without time zone | sim |  |  |  |
| `tolerance_extra_minutes` | integer | sim |  |  |  |
| `tolerance_absence_minutes` | integer | sim |  |  |  |
| `workload_minutes` | integer | sim |  |  |  |
| `updated_at` | timestamp with time zone | sim | `now()` |  |  |
| `tenant_id` | uuid | sim | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `work_schedule_day_tenant_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `work_schedule_day_tenant_idx` — `app.work_schedule_day USING btree (tenant_id)`

</details>


## `app.workforce_movement`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `employee_id` | uuid | não |  | `app.employee` |  |
| `company_id` | uuid | não |  | `app.company` |  |
| `unit_id` | uuid | sim |  | `app.unit` |  |
| `type` | text | não |  |  |  |
| `event_date` | date | não |  |  |  |
| `payroll_period_id` | uuid | sim |  | `app.payroll_period` |  |
| `estimated_cost` | numeric(14,2) | sim |  |  |  |
| `notes` | text | sim |  |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((type = ANY (ARRAY['hire'::text, 'termination'::text, 'transfer'::text, 'promotion'::text, 'leave_period'::text, 'return_to_work'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `movimentacao_read` | SELECT | `(util.is_admin(tenant_id) OR ((unit_id IS NOT NULL) AND util.can_see_unit(unit_id)))` | `-` |

<details><summary>Índices</summary>

- `movimentacao_colab_idx` — `app.workforce_movement USING btree (employee_id)`
- `movimentacao_data_idx` — `app.workforce_movement USING btree (tenant_id, event_date DESC)`
- `workforce_movement_company_id_fkidx` — `app.workforce_movement USING btree (company_id)`
- `workforce_movement_payroll_period_id_fkidx` — `app.workforce_movement USING btree (payroll_period_id)`
- `workforce_movement_unit_id_fkidx` — `app.workforce_movement USING btree (unit_id)`

</details>


---

# Schema `secullum`

Espelho literal do Secullum. Não exposto ao PostgREST. PII completa. Só `service_role`.


## `secullum.Batida`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `Id` 🔑 | bigint | não |  |  |  |
| `BatidaId` | integer | sim |  |  |  |
| `FuncionarioId` | integer | sim |  |  |  |
| `funcionario_id` | uuid | sim |  |  |  |
| `Data` | date | sim |  |  |  |
| `Folga` | boolean | sim |  |  |  |
| `Neutro` | boolean | sim |  |  |  |
| `Compensado` | boolean | sim |  |  |  |
| `AlmocoLivre` | boolean | sim |  |  |  |
| `Refeicao` | boolean | sim |  |  |  |
| `NBanco` | boolean | sim |  |  |  |
| `Ajuste` | text | sim |  |  |  |
| `Abono2` | text | sim |  |  |  |
| `Abono3` | text | sim |  |  |  |
| `Abono4` | text | sim |  |  |  |
| `Observacoes` | text | sim |  |  |  |
| `status_dia_rotulo` | text | sim |  |  |  |
| `sincronizado_em` | timestamp with time zone | sim |  |  |  |
| `atualizado_em` | timestamp with time zone | sim | `now()` |  |  |
| `tenant_id` | uuid | não | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `batida_tenant_idx` — `secullum."Batida" USING btree (tenant_id)`
- `UNIQUE "Batida_funcionario_id_Data_key"` — `secullum."Batida" USING btree (funcionario_id, "Data")`

</details>


## `secullum.BatidaFonteDados`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `Id` 🔑 | bigint | não |  |  |  |
| `batida_id` | uuid | sim |  |  |  |
| `batida_marcacao_id` | uuid | sim |  |  |  |
| `Data` | date | sim |  |  |  |
| `Hora` | time without time zone | sim |  |  |  |
| `Nsr` | text | sim |  |  |  |
| `Origem` | smallint | sim |  |  |  |
| `Tipo` | smallint | sim |  |  |  |
| `FonteDadosId` | bigint | sim |  |  |  |
| `DataInclusao` | timestamp with time zone | sim |  |  |  |
| `criado_em` | timestamp with time zone | sim | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | sim | `now()` |  |  |
| `tenant_id` | uuid | não | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `batidafontedados_tenant_idx` — `secullum."BatidaFonteDados" USING btree (tenant_id)`

</details>


## `secullum.Departamento`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `Id` 🔑 | bigint | não |  |  |  |
| `EmpresaId` | bigint | sim |  |  |  |
| `Descricao` | text | sim |  |  |  |
| `tenant_id` | uuid | não | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `departamento_tenant_idx` — `secullum."Departamento" USING btree (tenant_id)`

</details>


## `secullum.Empresa`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `Id` 🔑 | bigint | não |  |  |  |
| `Nome` | text | sim |  |  |  |
| `Cnpj` | text | sim |  |  |  |
| `Ativo` | boolean | sim | `true` |  |  |
| `tenant_id` | uuid | não | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `empresa_tenant_idx` — `secullum."Empresa" USING btree (tenant_id)`

</details>


## `secullum.Estrutura`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `Id` 🔑 | bigint | não |  |  |  |
| `DepartamentoId` | bigint | sim |  |  |  |
| `GestorNome` | text | sim |  |  |  |
| `tenant_id` | uuid | não | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `estrutura_tenant_idx` — `secullum."Estrutura" USING btree (tenant_id)`

</details>


## `secullum.Funcionario`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `Id` 🔑 | bigint | não |  |  |  |
| `EmpresaId` | bigint | sim |  |  |  |
| `DepartamentoId` | bigint | sim |  |  |  |
| `Nome` | text | sim |  |  |  |
| `Cpf` | text | sim |  |  |  |
| `Rg` | text | sim |  |  |  |
| `NumeroPis` | text | sim |  |  |  |
| `DataNascimento` | date | sim |  |  |  |
| `Endereco` | text | sim |  |  |  |
| `Telefone` | text | sim |  |  |  |
| `Email` | text | sim |  |  |  |
| `NomeMae` | text | sim |  |  |  |
| `NomePai` | text | sim |  |  |  |
| `DataAdmissao` | date | sim |  |  |  |
| `DataDemissao` | date | sim |  |  |  |
| `Ativo` | boolean | sim | `true` |  |  |
| `tenant_id` | uuid | não | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `funcionario_tenant_idx` — `secullum."Funcionario" USING btree (tenant_id)`

</details>


## `secullum.FuncionarioAfastamento`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `Id` 🔑 | bigint | não |  |  |  |
| `FuncionarioId` | bigint | sim |  |  |  |
| `DataInicio` | date | sim |  |  |  |
| `DataFim` | date | sim |  |  |  |
| `tenant_id` | uuid | não | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `funcionarioafastamento_tenant_idx` — `secullum."FuncionarioAfastamento" USING btree (tenant_id)`

</details>


## `secullum.Horario`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `Id` 🔑 | bigint | não |  |  |  |
| `Descricao` | text | sim |  |  |  |
| `ToleranciaExtra` | integer | sim |  |  |  |
| `ToleranciaFalta` | integer | sim |  |  |  |
| `tenant_id` | uuid | não | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horario_tenant_idx` — `secullum."Horario" USING btree (tenant_id)`

</details>


## `secullum.HorarioDia`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `Id` 🔑 | bigint | não |  |  |  |
| `HorarioId` | bigint | sim |  |  |  |
| `DiaSemana` | smallint | sim |  |  |  |
| `Entrada` | time without time zone | sim |  |  |  |
| `Saida` | time without time zone | sim |  |  |  |
| `tenant_id` | uuid | não | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horariodia_tenant_idx` — `secullum."HorarioDia" USING btree (tenant_id)`

</details>


## `secullum.HorarioExtras`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `Id` 🔑 | bigint | não |  |  |  |
| `horario_id` | uuid | sim |  |  |  |
| `HorarioId` | integer | sim |  |  |  |
| `ControleHorasExtrasAutorizadas` | boolean | sim |  |  |  |
| `QuantidadeExtrasAutorizadas` | text | sim |  |  |  |
| `atualizado_em` | timestamp with time zone | sim | `now()` |  |  |
| `tenant_id` | uuid | não | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horarioextras_tenant_idx` — `secullum."HorarioExtras" USING btree (tenant_id)`

</details>


## `secullum.HorarioFaixasExtras`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `horario_id` | uuid | sim |  |  |  |
| `HorarioId` | integer | sim |  |  |  |
| `DiaSemana` | smallint | sim |  |  |  |
| `Controle` | smallint | sim |  |  |  |
| `DiaEspecial` | smallint | sim |  |  |  |
| `tenant_id` | uuid | não | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horariofaixasextras_tenant_idx` — `secullum."HorarioFaixasExtras" USING btree (tenant_id)`

</details>


## `secullum.HorarioToleranciaEspecificaItem`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `Id` 🔑 | bigint | não |  |  |  |
| `horario_tolerancia_especifica_id` | uuid | sim |  |  |  |
| `HorarioId` | integer | sim |  |  |  |
| `DiaSemana` | smallint | sim |  |  |  |
| `Entrada1De` | time without time zone | sim |  |  |  |
| `Entrada1Ate` | time without time zone | sim |  |  |  |
| `Saida1De` | time without time zone | sim |  |  |  |
| `Saida1Ate` | time without time zone | sim |  |  |  |
| `tenant_id` | uuid | não | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horariotoleranciaespecificaitem_tenant_idx` — `secullum."HorarioToleranciaEspecificaItem" USING btree (tenant_id)`

</details>


## `secullum.HorariosOpcoes`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `Id` 🔑 | bigint | não |  |  |  |
| `horario_id` | uuid | sim |  |  |  |
| `HorarioId` | integer | sim |  |  |  |
| `ToleranciaArtigo58` | boolean | sim |  |  |  |
| `QualquerMinutoAtrasadoComoFalta` | boolean | sim |  |  |  |
| `QualquerMinutoAdiantadoComoExtra` | boolean | sim |  |  |  |
| `LimiteMinimoDeExtrasNoDiaMinutos` | integer | sim |  |  |  |
| `LimiteMinimoDeFaltasNoDiaMinutos` | integer | sim |  |  |  |
| `DescontarToleranciaDasHorasExtras` | boolean | sim |  |  |  |
| `DescontarToleranciaDasHorasFaltas` | boolean | sim |  |  |  |
| `Compensacao` | smallint | sim |  |  |  |
| `UsarInterjornada` | boolean | sim |  |  |  |
| `Interjornada` | text | sim |  |  |  |
| `PermitirFolgasAutomaticas` | boolean | sim |  |  |  |
| `QuantidadeFolgasAutomaticas` | integer | sim |  |  |  |
| `CompletarBatidasFaltantes` | boolean | sim |  |  |  |
| `SubstituirBatidasAbaixoDasTolerancias` | boolean | sim |  |  |  |
| `DividirJornadaQuandoHouverFolga` | boolean | sim |  |  |  |
| `HorasRepousoFaixas` | jsonb | sim |  |  |  |
| `atualizado_em` | timestamp with time zone | sim | `now()` |  |  |
| `tenant_id` | uuid | não | `'5cfd39c3-b673-47fd-8d9b-07d089f919db'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horariosopcoes_tenant_idx` — `secullum."HorariosOpcoes" USING btree (tenant_id)`

</details>


---

# Schema `public` — superfície de API

Único schema exposto. Toda view usa `security_invoker = on`: a RLS do usuário
que consulta continua valendo. `anon` não lê nada — o painel autentica antes.


## `public.vw_deviation_by_employee_day`  ✅ `security_invoker`

| Coluna | Tipo |
|---|---|
| `tenant_id` | uuid |
| `reference_date` | date |
| `employee_id` | uuid |
| `employee_name` | text |
| `unit_id` | uuid |
| `unit_name` | text |
| `eventos` | bigint |
| `minutes_abs` | bigint |


## `public.vw_deviation_daily_trend`  ✅ `security_invoker`

| Coluna | Tipo |
|---|---|
| `tenant_id` | uuid |
| `reference_date` | date |
| `unit_id` | uuid |
| `direction` | text |
| `eventos` | bigint |
| `minutes_abs` | bigint |


## `public.vw_deviation_event`  ✅ `security_invoker`

| Coluna | Tipo |
|---|---|
| `evento_id` | uuid |
| `tenant_id` | uuid |
| `reference_date` | date |
| `company_id` | uuid |
| `unit_id` | uuid |
| `unit_name` | text |
| `employee_id` | uuid |
| `employee_name` | text |
| `type` | text |
| `type_description` | text |
| `direction` | text |
| `category` | text |
| `minutes` | integer |
| `minutes_abs` | integer |
| `expected_time` | time without time zone |
| `actual_time` | time without time zone |
| `status` | text |
| `report_cycle_id` | uuid |
| `pendente_de_ciclo` | boolean |
| `detected_at` | timestamp with time zone |
| `counts_as_deviation` | boolean |


## `public.vw_deviation_summary_by_unit`  ✅ `security_invoker`

| Coluna | Tipo |
|---|---|
| `tenant_id` | uuid |
| `reference_date` | date |
| `unit_id` | uuid |
| `unit_name` | text |
| `company_id` | uuid |
| `eventos` | bigint |
| `colaboradores` | bigint |
| `minutes_excedente` | bigint |
| `minutes_faltante` | bigint |
| `minutes_abs` | bigint |


## `public.vw_document_expiry`  ✅ `security_invoker`

| Coluna | Tipo |
|---|---|
| `document_id` | uuid |
| `tenant_id` | uuid |
| `employee_id` | uuid |
| `employee_name` | text |
| `unit_id` | uuid |
| `type_name` | text |
| `valid_until` | date |
| `dias_para_vencer` | integer |
| `expiry_alert_days` | integer |
| `em_alerta` | boolean |


## `public.vw_employee`  ✅ `security_invoker`

| Coluna | Tipo |
|---|---|
| `employee_id` | uuid |
| `tenant_id` | uuid |
| `company_id` | uuid |
| `unit_id` | uuid |
| `name` | text |
| `registration_number` | text |
| `cargo` | text |
| `hired_on` | date |
| `status` | text |
| `unit_name` | text |
| `company_name` | text |
| `gestor_name` | text |


## `public.vw_payroll_summary`  ✅ `security_invoker`

| Coluna | Tipo |
|---|---|
| `tenant_id` | uuid |
| `year` | smallint |
| `month` | smallint |
| `company_id` | uuid |
| `unit_id` | uuid |
| `total_proventos` | numeric |
| `total_descontos` | numeric |
| `total_encargos` | numeric |
| `colaboradores` | bigint |


## `public.vw_unit`  ✅ `security_invoker`

| Coluna | Tipo |
|---|---|
| `unit_id` | uuid |
| `tenant_id` | uuid |
| `company_id` | uuid |
| `company_name` | text |
| `code` | text |
| `name` | text |
| `timezone` | text |
| `active` | boolean |


## RPCs

Funções com período parametrizado. `security invoker`: herdam a RLS de quem chama.


### `fn_data_freshness`

```sql
public.fn_data_freshness(p_stale_after_minutes integer DEFAULT 45)
  returns TABLE(tenant_id uuid, entity text, last_sync_at timestamp with time zone, age_minutes integer, is_stale boolean)
```

Data age per synced entity, for the "updated N minutes ago" indicator. Default threshold is 45 min — 1.5x the 30-minute cadence, so a single missed run does not raise a false alarm but two in a row do.


### `fn_detection_health`

```sql
public.fn_detection_health(p_backfill_max_age_hours integer DEFAULT 26)
  returns TABLE(tenant_id uuid, last_incremental_at timestamp with time zone, incremental_age_minutes integer, last_backfill_at timestamp with time zone, backfill_age_hours integer, backfill_overdue boolean)
```

Backfill overdue is true when it has not completed in p_backfill_max_age_hours OR has never run. Never-ran must read as overdue, not as null.


### `fn_kpi_period`

```sql
public.fn_kpi_period(p_de date, p_ate date, p_company_id uuid DEFAULT NULL::uuid, p_unit_id uuid DEFAULT NULL::uuid)
  returns TABLE(eventos bigint, colaboradores_afetados bigint, minutes_excedente bigint, minutes_faltante bigint, minutes_abs bigint, unidades_afetadas bigint, eventos_pendentes_ciclo bigint)
```

### `fn_ranking_by_employee`

```sql
public.fn_ranking_by_employee(p_de date, p_ate date, p_company_id uuid DEFAULT NULL::uuid, p_unit_id uuid DEFAULT NULL::uuid, p_limite integer DEFAULT 20)
  returns TABLE(employee_id uuid, employee_name text, unit_name text, eventos bigint, minutes_abs bigint)
```

### `fn_ranking_by_unit`

```sql
public.fn_ranking_by_unit(p_de date, p_ate date, p_company_id uuid DEFAULT NULL::uuid, p_limite integer DEFAULT 20)
  returns TABLE(unit_id uuid, unit_name text, eventos bigint, minutes_abs bigint, colaboradores bigint)
```

### `fn_recurrence`

```sql
public.fn_recurrence(p_de date, p_ate date, p_min_dias integer DEFAULT 3, p_unit_id uuid DEFAULT NULL::uuid)
  returns TABLE(employee_id uuid, employee_name text, unit_name text, dias_com_desvio bigint, eventos bigint)
```

## Helpers de RLS (`util`)

Não são API. `security definer` com `search_path` travado, `EXECUTE` revogado de `anon`.

| Função | Assinatura | Retorno |
|---|---|---|
| `util.block_table_in_public` | `` | `event_trigger` |
| `util.can_see_company` | `p_company_id uuid` | `boolean` |
| `util.can_see_domain` | `p_tenant_id uuid, p_domain app.sensitive_domain` | `boolean` |
| `util.can_see_employee` | `p_employee_id uuid` | `boolean` |
| `util.can_see_unit` | `p_unit_id uuid` | `boolean` |
| `util.has_tenant` | `p_tenant_id uuid` | `boolean` |
| `util.is_admin` | `p_tenant_id uuid` | `boolean` |
| `util.lock_down_new_function` | `` | `event_trigger` |
| `util.roles_in_tenant` | `p_tenant_id uuid` | `app.user_role[]` |
| `util.touch_updated_at` | `` | `trigger` |
| `util.user_tenants` | `` | `uuid[]` |
| `util.validate_alert_payload` | `` | `trigger` |
| `util.validate_alert_target` | `` | `trigger` |


---

# Como consumir

## Caminho 1 — navegador direto no Supabase (anon key)

Só agregado não sensível. A RLS filtra por tenant e escopo automaticamente.

```ts
const supabase = createClient(NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY)

// KPIs do período — filters vêm da query string do link do relatório
const { data } = await supabase.rpc('fn_kpi_period', {
  p_de: '2026-08-01', p_ate: '2026-08-31',
  p_unidade_id: searchParams.get('unit'),
})

// Série diária para o gráfico de tendência
const { data: serie } = await supabase
  .from('vw_deviation_daily_trend')
  .select('reference_date, direction, eventos, minutos_abs')
  .gte('reference_date', de).lte('reference_date', ate)
  .order('reference_date')
```

`anon` não lê nada: a sessão precisa estar autenticada. O cliente **não** manda
`tenant_id` — e não adianta mandar, porque a policy não confia em parâmetro do
cliente.

## Caminho 2 — navegador → FastAPI (individual, identificável ou sensível)

O `service_role` vive **somente** no backend FastAPI no Railway. Nunca no
Next.js, nunca no navegador. Uma chave que ignora toda a RLS não pode ter duas
cópias em dois provedores de deploy diferentes.

```python
# backend/server/routers/employee.py
@router.get("/employee/{employee_id}/pii")
async def ler_pii(employee_id: UUID, ctx: TenantContext = Depends(tenant_ctx)):
    # ctx vem do JWT do Supabase, validado contra o JWKS do projeto.
    # service_role IGNORA RLS — o filtro de tenant é obrigação nossa.
    async with pool_app.connection() as conn:
        row = await conn.execute(
            "select cpf, rg from app.employee_pii "
            "where tenant_id = %s and employee_id = %s",   # NUNCA omitir o tenant
            (ctx.tenant_id, employee_id),
        )
    return row
```

Antes de responder, o backend revalida papel e domínio sensível — não confia no
que o frontend diz que o usuário pode ver.

## Do sync — espelho do Secullum

```python
# backend/operax/core/db.py — conexão direta; upsert em lote é bem mais
# rápido que via PostgREST, e `secullum` nem é exposto ao PostgREST.
pool_secullum = ConnectionPool(
    DATABASE_URL,
    kwargs={"options": "-c search_path=secullum"},
)
```

**Regra para todo código com `service_role`:** nenhuma consulta sem filtro
explícito de `tenant_id`. É onde vazamento entre clientes acontece na prática,
porque a rede de proteção da RLS está desligada.

