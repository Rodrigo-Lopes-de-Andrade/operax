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
| `model` | text | sim |  |  | Id do modelo que respondeu, da allowlist de operax/agente/agente.py. Sem ele os contadores de token não viram dinheiro, que é para o que eles existem. |

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
| `template_code` | text | sim |  |  |  |
| `provider` | text | sim |  |  |  |

**Restrições**

- `CHECK (((provider IS NULL) OR (provider = ANY (ARRAY['meta_cloud'::text, 'z_api'::text, 'uazapi'::text, 'smtp'::text, 'resend'::text]))))`
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
| `template_code` | text | sim |  |  | Null = alerta de e-mail ou resumo livre. Para WhatsApp com provedor oficial é obrigatório: sem template aprovado a Meta recusa a mensagem. |

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

- `CHECK ((provider = ANY (ARRAY['meta_cloud'::text, 'z_api'::text, 'uazapi'::text, 'smtp'::text, 'resend'::text])))`
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

> TABELA NOSSA (minusculo, ADR-012): e a TRANSPOSICAO de uma coluna do registro-dia (Entrada1..Entrada5 / Saida1..Saida5) em linha. ⛔ NAO procure "Marcacao" no payload do Secullum — nao existe. Identidade POSICIONAL: (batida_id, tipo_coluna, indice_coluna) — nunca por FonteDadosId, que e nullable e portanto nao e chave (ADR-007). ⚠️ Escrita OBRIGATORIA por substituicao do dia inteiro em transacao: upsert das colunas presentes + DELETE das que deixaram de existir. Sem o DELETE, uma batida removida no Secullum sobrevive para sempre no cache e continua gerando desvio.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `batida_id` | uuid | não |  | `secullum.Batida` |  |
| `funcionario_id` | uuid | não |  | `secullum.Funcionario` | NOSSA FK, desnormalizada a partir de "Batida" de proposito (mesmo racional de "Funcionario".empresa_id): evita um join no caminho quente do relatorio (Sprint 3) e do dashboard (Sprint 4). Coerencia com "Batida" e responsabilidade da mesma transacao de escrita — so o job escreve aqui. |
| `data` | date | não |  |  | NOSSA, desnormalizada de "Batida"."Data" (por isso minuscula). Mesma finalidade de funcionario_id. |
| `tipo_coluna` | text | não |  |  | NOSSO. Valores 'Entrada' | 'Saida' — grafados exatamente como o PREFIXO da coluna no payload, de modo que tipo_coluna || indice_coluna reconstroi o nome literal do campo ("Entrada3"). |
| `indice_coluna` | smallint | não |  |  |  |
| `valor_bruto` | text | sim |  |  | NOSSO. Conteudo literal da coluna `EntradaN`/`SaidaN`, preservado como veio. Tres estados possiveis: "HH:mm" (batida), TEXTO DE STATUS (ex.: "Ferias") ou null. E a unica coluna que garante fidelidade ao payload — `hora` e `status_rotulo` sao interpretacoes dela. |
| `hora` | time without time zone | sim |  |  | NOSSO (derivado). Preenchida SOMENTE quando valor_bruto e "HH:mm". Hora LOCAL (America/Sao_Paulo), armazenada sem conversao de fuso. Mutuamente exclusiva com status_rotulo. ⚠️ Linha com hora IS NULL NAO e batida: nao entra na deteccao e nao entra no denominador do KPI de batidas do dashboard. |
| `status_rotulo` | text | sim |  |  |  |
| `Memoria` | time without time zone | sim |  |  | Campo `MemoriaEntradaN`/`MemoriaSaidaN`, DES-POSICIONALIZADO (o sufixo virou tipo_coluna/indice_coluna). Horario PREVISTO daquele dia, atalho de diagnostico. ⛔ NAO e a fonte da verdade do previsto nem da tolerancia: isso e "HorarioDia". Inverter essa ordem faz o sistema divergir do calculo oficial de folha. ✅ E o sinal de BATIDA FALTANTE quando "Memoria" existe e `hora` e nula. |
| `EquipId` | integer | sim |  |  | Campo `EquipIdEntradaN`/`EquipIdSaidaN`, des-posicionalizado. Id do equipamento/relogio que originou a coluna. Inteiro bruto, sem FK — o cadastro de equipamentos do Secullum nao e consumido. |
| `FonteDadosId` | bigint | sim |  |  | Campo `FonteDadosIdEntradaN`/`SaidaN`, des-posicionalizado (o escalar do payload). ATRIBUTO, indice NAO-UNICO: confirmado em dados reais que uma coluna preenchida, inclusive vinda de relogio fisico ("EquipId" presente), pode ter este id nulo. Chave que as vezes e nula nao e chave. |
| `desconsiderada` | boolean | não | `false` |  | NOSSO (derivado de "BatidaFonteDados"."Tipo" = 3, Desconsiderado). A marcacao E persistida (para o reprocessamento nao oscilar e por rastreabilidade), mas nao gera desvio. |
| `sincronizado_em` | timestamp with time zone | não | `now()` |  |  |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | sim | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Restrições**

- `CHECK (((indice_coluna >= 1) AND (indice_coluna <= 5)))`
- `CHECK ((tipo_coluna = ANY (ARRAY['Entrada'::text, 'Saida'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `batida_marcacao_tenant_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `batida_marcacao_fontedadosid_idx` — `app.batida_marcacao USING btree ("FonteDadosId")`
- `batida_marcacao_funcionario_id_data_idx` — `app.batida_marcacao USING btree (funcionario_id, data)`
- `batida_marcacao_hora_idx` — `app.batida_marcacao USING btree (funcionario_id, data) WHERE (hora IS NOT NULL)`
- `batida_marcacao_tenant_idx` — `app.batida_marcacao USING btree (tenant_id)`
- `UNIQUE batida_marcacao_posicao_key` — `app.batida_marcacao USING btree (batida_id, tipo_coluna, indice_coluna)`

</details>


## `app.benefit_cycle`

> Competência de cesta ou de vale transporte. Um modelo, dois kind. Ciclo generated ou exported é imutável (regra 9 do PRD-DP): correção é ciclo novo com reason, nunca update.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `kind` | text | não |  |  |  |
| `period_year` | smallint | não |  |  |  |
| `period_month` | smallint | não |  |  |  |
| `window_start` | date | não |  |  |  |
| `window_end` | date | não |  |  |  |
| `business_days` | smallint | sim |  |  | Dias com expediente na janela. Cabeçalho da tela; nunca entra em net_days nem em total_amount. |
| `status` | text | não | `'draft'::text` |  |  |
| `generated_at` | timestamp with time zone | sim |  |  |  |
| `generated_by` | uuid | sim |  |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK (((period_month >= 1) AND (period_month <= 12)))`
- `CHECK ((kind = ANY (ARRAY['food_basket'::text, 'transport_voucher'::text])))`
- `CHECK ((status = ANY (ARRAY['draft'::text, 'generated'::text, 'exported'::text, 'cancelled'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `benefit_cycle_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |
| `benefit_cycle_read` | SELECT | `util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain)` | `-` |

<details><summary>Índices</summary>

- `benefit_cycle_competencia_idx` — `app.benefit_cycle USING btree (tenant_id, kind, period_year DESC, period_month DESC)`
- `UNIQUE benefit_cycle_period_key` — `app.benefit_cycle USING btree (tenant_id, kind, period_year, period_month, status)`

</details>


## `app.benefit_entitlement`

> Uma linha por pessoa por ciclo. Colunas de dias nulas para cesta. reason grava QUAL causa tirou o direito — falta injustificada ou admissão depois do início do período.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `cycle_id` | uuid | não |  | `app.benefit_cycle` |  |
| `employee_id` | uuid | não |  | `app.employee` |  |
| `unit_id` | uuid | sim |  | `app.unit` |  |
| `entitled` | boolean | não |  |  |  |
| `reason` | text | sim |  |  |  |
| `days_base` | smallint | sim |  |  |  |
| `absences_prior` | smallint | sim |  |  |  |
| `net_days` | smallint | sim |  |  |  |
| `unit_amount` | numeric(12,2) | sim |  |  |  |
| `round_trip_amount` | numeric(12,2) | sim |  |  |  |
| `total_amount` | numeric(12,2) | sim |  |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `benefit_entitlement_read` | SELECT | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.can_see_employee(employee_id))` | `-` |
| `benefit_entitlement_write` | ALL | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.can_see_employee(employee_id) A` | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) ` |

<details><summary>Índices</summary>

- `benefit_entitlement_ciclo_idx` — `app.benefit_entitlement USING btree (tenant_id, cycle_id)`
- `benefit_entitlement_colab_idx` — `app.benefit_entitlement USING btree (tenant_id, employee_id)`
- `UNIQUE benefit_entitlement_cycle_id_employee_id_key` — `app.benefit_entitlement USING btree (cycle_id, employee_id)`

</details>


## `app.benefit_plan`

> Plano de benefício (operadora e preço) com vigência. Reajuste = linha nova; o valor de uma vigência já publicada nunca é editado.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `benefit_type_id` | uuid | não |  | `app.benefit_type` |  |
| `code` | text | não |  |  |  |
| `provider` | text | não |  |  |  |
| `name` | text | não |  |  |  |
| `amount` | numeric(12,2) | não |  |  |  |
| `effective_from` | date | não |  |  |  |
| `effective_to` | date | sim |  |  |  |
| `reason` | text | sim |  |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK (((effective_to IS NULL) OR (effective_to >= effective_from)))`
- `CHECK ((amount >= (0)::numeric))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `benefit_plan_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |
| `benefit_plan_read` | SELECT | `util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain)` | `-` |

<details><summary>Índices</summary>

- `UNIQUE benefit_plan_open_band_idx` — `app.benefit_plan USING btree (tenant_id, code) WHERE (effective_to IS NULL)`

</details>


## `app.benefit_type`

> Catálogo de verbas do tenant. `composes_base` é a regra 8 do PRD-DP virando dado: a folha base é salary + sum(amount) where composes_base, nunca uma lista no backend.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `code` | text | não |  |  |  |
| `name` | text | não |  |  |  |
| `composes_base` | boolean | não |  |  | Entra na folha salarial base. Definição do KPI: mudar esta coluna muda o número da tela. |
| `calculation` | text | não | `'fixed_amount'::text` |  | fixed_amount = valor digitado; salary_rate = derivado do salário vigente (mecanismo do triênio). |
| `domain` | app.sensitive_domain | não | `'compensation'::app.sensitive_domain` |  |  |
| `active` | boolean | não | `true` |  |  |

**Restrições**

- `CHECK ((calculation = ANY (ARRAY['fixed_amount'::text, 'salary_rate'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `benefit_type_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |
| `benefit_type_read` | SELECT | `util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain)` | `-` |

<details><summary>Índices</summary>

- `UNIQUE benefit_type_tenant_id_code_key` — `app.benefit_type USING btree (tenant_id, code)`

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


## `app.cursor_sincronizacao`

> Controle de sincronizacao com o Secullum. TABELA 100% NOSSA — nao tem equivalente no Secullum, por isso nome e colunas em minusculo (regra do caso, ADR-012). Ver docs/04-modelo-dados.md.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `chave` 🔑 | text | não |  |  | Identificador logico do cursor (ex.: batidas_ultima_data_sincronizada). |
| `valor` | text | sim |  |  | Valor do cursor em texto. Para /Batidas guarda a ultima DATA coberta pela janela deslizante, nao um ID. |
| `atualizado_em` | timestamp with time zone | não | `now()` |  | Momento da ultima atualizacao do cursor. |
| `tenant_id` | uuid | sim | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `cursor_sincronizacao_tenant_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `cursor_sincronizacao_tenant_idx` — `app.cursor_sincronizacao USING btree (tenant_id)`

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
- `UNIQUE deviation_event_unico_active_modo` — `app.deviation_event USING btree (employee_id, reference_date, type, mode) WHERE (status = 'active'::text)`

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
| `requires_justification` | boolean | não | `false` |  | Nasce false, como triggers_alert. Política por cliente: atraso pode exigir explicação onde marcação incompleta não exige. Sem isto, "pendente de justificativa" não tem de onde sair — todo desvio pareceria pendente, ou nenhum. |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `desvio_config_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |
| `desvio_config_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `deviation_type_config_code_fkidx` — `app.deviation_type_config USING btree (code)`

</details>


## `app.disciplinary_event`

> Advertência, suspensão e anotação administrativa. Domínio sensível `disciplinary`: ver a unidade não basta e ser gestor dela não basta. Sem delete para o painel — registro aplicado por engano se corrige por update, com trilha, nunca por apagamento.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `employee_id` | uuid | não |  | `app.employee` |  |
| `type` | text | não |  |  |  |
| `occurred_on` | date | não |  |  |  |
| `days` | integer | sim |  |  |  |
| `summary` | text | sim |  |  | Texto livre sobre uma pessoa, no domínio mais sensível dos quatro. NUNCA em view de public. |
| `document_id` | uuid | sim |  | `app.document` |  |
| `acknowledged_on` | date | sim |  |  |  |
| `created_by` | uuid | sim |  | `auth.users` |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK (((days IS NULL) OR (days > 0)))`
- `CHECK (((days IS NULL) OR (type = 'suspension'::text)))`
- `CHECK ((type = ANY (ARRAY['verbal_warning'::text, 'written_warning'::text, 'suspension'::text, 'administrative_note'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `disciplinary_read` | SELECT | `(util.can_see_domain(tenant_id, 'disciplinary'::app.sensitive_domain) AND util.can_see_employee(employee_id))` | `-` |
| `disciplinary_write` | ALL | `util.can_see_domain(tenant_id, 'disciplinary'::app.sensitive_domain)` | `util.can_see_domain(tenant_id, 'disciplinary'::app.sensitive_domain)` |

<details><summary>Índices</summary>

- `disciplinary_colab_idx` — `app.disciplinary_event USING btree (employee_id, occurred_on DESC)`
- `disciplinary_tenant_idx` — `app.disciplinary_event USING btree (tenant_id, occurred_on DESC)`

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
| `hr_code` | text | sim |  |  | ID RH do cliente. Chave ALTERNATIVA — nunca composta com a matrícula: cada uma identifica sozinha, e divergência entre elas é erro de linha no import. Anulável de propósito: fica vazia até o template de vínculo voltar preenchido. |
| `exception_tracking` | boolean | não | `false` |  | Fora do motor de detecção POR DECISÃO — "ponto por exceção", supervisão. Nasce false: quem aparece fora da medição sem alguém ter tirado é quem ninguém decidiu não medir. Quem está aqui não materializa jornada esperada e é contado à parte no monitor, separado de `unrostered`, que é falha de cobertura e tem a mesma aparência. |
| `manager_id` | uuid | sim |  | `app.manager` | A quem esta pessoa responde, promovido de `Funcionario.EstruturaId`. NÃO confundir com `manager_employee_id`, que aponta para um `app.employee` e continua sem fonte: o espelho diz o NOME do gestor, não qual colaborador ele é. |

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
- `employee_manager_idx` — `app.employee USING btree (manager_id)`
- `employee_tenant_unidade_idx` — `app.employee USING btree (tenant_id, unit_id) WHERE (status <> 'desligado'::text)`
- `employee_unit_id_fkidx` — `app.employee USING btree (unit_id)`
- `UNIQUE employee_hr_code_unique` — `app.employee USING btree (tenant_id, hr_code) WHERE (hr_code IS NOT NULL)`
- `UNIQUE employee_tenant_id_secullum_employee_id_key` — `app.employee USING btree (tenant_id, secullum_employee_id)`

</details>


## `app.employee_bank_account`

> Conta bancária do colaborador — insumo do arquivo de remessa do vale transporte. Domínio sensível `banking`, sem grant para `authenticated`: só Caminho 2. O número completo nunca chega ao navegador (regra 10 do PRD-DP); a tela vê máscara.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `employee_id` 🔑 | uuid | não |  | `app.employee` |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `bank_code` | text | não |  |  |  |
| `branch` | text | não |  |  |  |
| `account` | text | não |  |  | Número completo. Só o montador da remessa o devolve, e em bytes — nunca em JSON. |
| `account_type` | text | não | `'checking'::text` |  |  |
| `holder_document` | text | sim |  |  | CPF/CNPJ do titular quando a conta não é do colaborador. Documento de terceiro. |
| `updated_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((account_type = ANY (ARRAY['checking'::text, 'savings'::text, 'salary'::text, 'payment'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `employee_bank_account_read` | SELECT | `(util.can_see_domain(tenant_id, 'banking'::app.sensitive_domain) AND util.can_see_employee(employee_id))` | `-` |
| `employee_bank_account_write` | ALL | `(util.can_see_domain(tenant_id, 'banking'::app.sensitive_domain) AND util.can_see_employee(employee_id) AND ut` | `(util.can_see_domain(tenant_id, 'banking'::app.sensitive_domain) AND u` |

<details><summary>Índices</summary>

- `employee_bank_account_tenant_idx` — `app.employee_bank_account USING btree (tenant_id)`

</details>


## `app.employee_benefit`

> Verba do colaborador com vigência. Domínio compensation: leitura com dois eixos, escrita com três. A folha base soma daqui filtrando por benefit_type.composes_base.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `employee_id` | uuid | não |  | `app.employee` |  |
| `benefit_type_id` | uuid | não |  | `app.benefit_type` |  |
| `effective_from` | date | não |  |  |  |
| `effective_to` | date | sim |  |  |  |
| `amount` | numeric(12,2) | sim |  |  |  |
| `rate` | numeric(6,4) | sim |  |  | Percentual por unidade (mecanismo do triênio). Com quantity, o valor deriva do salário vigente e acompanha o aumento. |
| `quantity` | smallint | sim |  |  |  |
| `benefit_plan_id` | uuid | sim |  | `app.benefit_plan` |  |
| `transport_fare_id` | uuid | sim |  | `app.transport_fare` |  |
| `reason` | text | sim |  |  |  |
| `recorded_by` | uuid | sim |  |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `employee_benefit_read` | SELECT | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.can_see_employee(employee_id))` | `-` |
| `employee_benefit_write` | ALL | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) AND util.can_see_employee(employee_id) A` | `(util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain) ` |

<details><summary>Índices</summary>

- `employee_benefit_colab_idx` — `app.employee_benefit USING btree (tenant_id, employee_id, effective_from DESC)`

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


## `app.employee_photo`

> Foto imputada pelo DP para quem a origem declara não ter (`"PossuiFoto" = false`). NÃO é espelho: dado nosso, criado aqui. Domínio sensível `pii`, sem grant para `authenticated` — só Caminho 2. Ver docs/DECISAO-FOTO-DO-COLABORADOR.md §4-ter.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `employee_id` | uuid | não |  | `app.employee` |  |
| `content` | bytea | não |  |  |  |
| `mime` | text | não |  |  |  |
| `bytes` | integer | não |  |  |  |
| `sha256` | text | não |  |  |  |
| `uploaded_by` | uuid | sim |  | `auth.users` |  |
| `uploaded_at` | timestamp with time zone | não | `now()` |  |  |
| `superseded_at` | timestamp with time zone | sim |  |  | Quando a origem passou a ter foto. A origem vence na exibição a partir daqui, e esta linha NUNCA é apagada: a ficha mostra que houve substituição, e de quando. |
| `superseded_reason` | text | sim |  |  |  |

**Restrições**

- `CHECK (((bytes = length(content)) AND (bytes > 0) AND (bytes <= ((5 * 1024) * 1024))))`
- `CHECK ((mime = ANY (ARRAY['image/jpeg'::text, 'image/png'::text])))`
- `CHECK ((sha256 ~ '^[0-9a-f]{64}$'::text))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `employee_photo_read` | SELECT | `(util.can_see_domain(tenant_id, 'pii'::app.sensitive_domain) AND util.can_see_employee(employee_id))` | `-` |
| `employee_photo_supersede` | UPDATE | `(util.can_see_domain(tenant_id, 'pii'::app.sensitive_domain) AND util.is_admin(tenant_id) AND util.can_see_emp` | `-` |
| `employee_photo_write` | INSERT | `-` | `(util.can_see_domain(tenant_id, 'pii'::app.sensitive_domain) AND util.` |

<details><summary>Índices</summary>

- `employee_photo_employee_idx` — `app.employee_photo USING btree (employee_id)`
- `UNIQUE employee_photo_ativa_key` — `app.employee_photo USING btree (tenant_id, employee_id) WHERE (superseded_at IS NULL)`

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
| `work_post_id` | uuid | sim |  | `app.work_post` | Posto do Quadro de Postos em que a pessoa exerce este cargo. Anulável: cargo sem posto mapeado é o estado inicial. |
| `level` | text | sim |  |  | Nível dentro do cargo ("OPERADOR" na ficha do legado). Rótulo do cliente, não enum. |

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

> TABELA 100% NOSSA (por isso tudo em minusculo) — historico APPEND-ONLY de mudancas de "Empresa".ativo. ⚠️⚠️ NAO EXISTE DATA REAL DE EVENTO AQUI: o Secullum entrega apenas `Empresa.Desativada` (boolean de estado atual). A unica data e detectado_em (quando a sincronizacao percebeu) e a ausencia de uma coluna de data de evento e PROPOSITAL. Contraste obrigatorio com funcionario_evento_status, que TEM data real. Ver ADR-009.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `empresa_id` | uuid | não |  | `secullum.Empresa` |  |
| `tipo_evento` | text | não |  |  | baseline (primeira vez que a empresa foi observada; previous_active nulo) | deactivated | reactivated. |
| `ativo_anterior` | boolean | sim |  |  |  |
| `ativo_novo` | boolean | não |  |  |  |
| `detectado_em` | timestamp with time zone | não | `now()` |  | Quando ESTA sincronizacao detectou a mudanca. NAO e quando a empresa foi desativada no Secullum (essa informacao nao existe na API). Erro >= intervalo entre execucoes do job; ilimitado se o job esteve parado. |
| `origem` | text | não | `'secullum_sync'::text` |  | secullum_sync (job cadastral) | backfill (esta migration, para linhas ja existentes) | manual. |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | sim | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Restrições**

- `CHECK ((((tipo_evento = 'deactivated'::text) AND (ativo_novo = false)) OR ((tipo_evento = 'reactivated'::text) AND (ativo_novo = true)) OR (tipo_evento = 'baseline'::text)))`
- `CHECK (((tipo_evento = 'baseline'::text) = (ativo_anterior IS NULL)))`
- `CHECK (((tipo_evento = 'baseline'::text) OR (ativo_anterior IS DISTINCT FROM ativo_novo)))`
- `CHECK ((origem = ANY (ARRAY['secullum_sync'::text, 'backfill'::text, 'manual'::text])))`
- `CHECK ((tipo_evento = ANY (ARRAY['baseline'::text, 'deactivated'::text, 'reactivated'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `empresa_evento_status_tenant_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `empresa_evento_status_empresa_detectado_idx` — `app.empresa_evento_status USING btree (empresa_id, detectado_em DESC)`
- `empresa_evento_status_tenant_idx` — `app.empresa_evento_status USING btree (tenant_id)`
- `UNIQUE empresa_evento_status_baseline_uniq` — `app.empresa_evento_status USING btree (empresa_id) WHERE (tipo_evento = 'baseline'::text)`

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
- `CHECK ((type = ANY (ARRAY['benefit'::text, 'cost_center'::text, 'employee'::text, 'folha'::text, 'hr_agreement'::text, 'hr_compensation'::text, 'hr_document'::text, 'hr_employee'::text, 'hr_exam'::text, 'hr_leave'::text, 'hr_link'::text, 'hr_movement'::text, 'other'::text, 'payroll_charge'::text, 'roster'::text])))`

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

> TABELA 100% NOSSA (minusculo) — historico APPEND-ONLY de mudancas de vinculo ("Funcionario".ativo). ✅ AQUI EXISTE data real de evento (data_evento, de `Admissao`/`Demissao`). data_evento e detectado_em divergem legitimamente. Ver ADR-009 e docs/04-modelo-dados.md.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `funcionario_id` | uuid | não |  | `secullum.Funcionario` |  |
| `tipo_evento` | text | não |  |  | baseline (primeira observacao) | admission (passou a ativo por admissao) | termination (passou a inativo por demissao) | reactivation (voltou a ativo sem nova admissao, ex.: Demissao corrigida para null) | date_correction (Admissao/Demissao mudou sem virar o status, inclusive desligamento programado para data futura). |
| `ativo_anterior` | boolean | sim |  |  |  |
| `ativo_novo` | boolean | não |  |  |  |
| `data_evento` | date | sim |  |  | Data REAL do Secullum (`Admissao` em admission, `Demissao` em termination). NULL quando o evento nao tem data de origem. Para reconstruir estado historico: coalesce(data_evento, detectado_em::date). |
| `admissao_anterior` | date | sim |  |  |  |
| `admissao_nova` | date | sim |  |  |  |
| `demissao_anterior` | date | sim |  |  |  |
| `demissao_nova` | date | sim |  |  |  |
| `detectado_em` | timestamp with time zone | não | `now()` |  | Quando a sincronizacao percebeu a mudanca. Pode ser POSTERIOR a event_date — ex.: desligamento com Demissao no dia 01 so detectado na execucao do dia 02. Isso e esperado. |
| `origem` | text | não | `'secullum_sync'::text` |  | secullum_sync (job cadastral) | backfill (esta migration, para linhas ja existentes) | manual. |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | sim | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Restrições**

- `CHECK (((tipo_evento <> 'admission'::text) OR (NOT (data_evento IS DISTINCT FROM admissao_nova))))`
- `CHECK (((tipo_evento <> 'date_correction'::text) OR (ativo_anterior = ativo_novo)))`
- `CHECK (((tipo_evento <> 'termination'::text) OR (NOT (data_evento IS DISTINCT FROM demissao_nova))))`
- `CHECK (((tipo_evento = 'baseline'::text) = (ativo_anterior IS NULL)))`
- `CHECK (((tipo_evento = 'baseline'::text) OR (ativo_anterior IS DISTINCT FROM ativo_novo) OR ((tipo_evento = 'date_correction'::text) AND ((admissao_anterior IS DISTINCT FROM admissao_nova) OR (demissao_anterior IS DISTINCT FROM demissao_nova)))))`
- `CHECK (((tipo_evento = ANY (ARRAY['baseline'::text, 'date_correction'::text])) OR ((tipo_evento = 'admission'::text) AND (ativo_novo = true)) OR ((tipo_evento = 'termination'::text) AND (ativo_novo = false)) OR ((tipo_evento = 'reactivation'::text) AND (ativo_novo = true))))`
- `CHECK ((origem = ANY (ARRAY['secullum_sync'::text, 'backfill'::text, 'manual'::text])))`
- `CHECK ((tipo_evento = ANY (ARRAY['baseline'::text, 'admission'::text, 'termination'::text, 'reactivation'::text, 'date_correction'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `funcionario_evento_status_tenant_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `funcionario_evento_status_funcionario_data_evento_idx` — `app.funcionario_evento_status USING btree (funcionario_id, data_evento)`
- `funcionario_evento_status_funcionario_detectado_idx` — `app.funcionario_evento_status USING btree (funcionario_id, detectado_em DESC)`
- `funcionario_evento_status_tenant_idx` — `app.funcionario_evento_status USING btree (tenant_id)`
- `UNIQUE funcionario_evento_status_baseline_uniq` — `app.funcionario_evento_status USING btree (funcionario_id) WHERE (tipo_evento = 'baseline'::text)`

</details>


## `app.integration`

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `provider` | text | não |  |  | meta_cloud = API oficial da Meta, exige template aprovado e verificação de negócio. z_api e uazapi = não oficiais, baseados em QR/WhatsApp Web: dispensam template, mas o número do cliente pode ser banido sem recurso. |
| `alias` | text | sim |  |  |  |
| `config` | jsonb | não | `'{}'::jsonb` |  |  |
| `active` | boolean | não | `false` |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((provider = ANY (ARRAY['secullum'::text, 'domain'::text, 'spreadsheet'::text, 'meta_cloud'::text, 'z_api'::text, 'uazapi'::text, 'smtp'::text, 'resend'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `integration_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |

<details><summary>Índices</summary>

- `UNIQUE integration_tenant_id_provider_alias_key` — `app.integration USING btree (tenant_id, provider, alias)`
- `UNIQUE integration_whatsapp_unico_ativo` — `app.integration USING btree (tenant_id) WHERE (active AND (provider = ANY (ARRAY['meta_cloud'::text, 'z_api'::text, 'uazapi'::text])))`

</details>


## `app.integration_secret`

> Só o ponteiro. O valor está no Vault. Nenhum role do painel lê esta tabela — nem owner.

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
| `status` | text | não | `'accepted'::text` |  | Default accepted de propósito: até esta migration uma linha aqui ERA a resposta final, e nenhuma justificativa já escrita pode virar pendente retroativamente. Não existe tela que rejeite — enquanto não existir, "aceita" e "escrita" são a mesma coisa. |

**Restrições**

- `CHECK ((source = ANY (ARRAY['secullum'::text, 'operax'::text, 'whatsapp'::text])))`
- `CHECK ((status = ANY (ARRAY['accepted'::text, 'rejected'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `justification_read` | SELECT | `util.can_see_employee(employee_id)` | `-` |
| `justification_write` | INSERT | `-` | `util.can_see_employee(employee_id)` |

<details><summary>Índices</summary>

- `justification_aceita_idx` — `app.justification USING btree (deviation_event_id) WHERE (status = 'accepted'::text)`
- `justification_author_user_id_fkidx` — `app.justification USING btree (author_user_id)`
- `justification_colab_idx` — `app.justification USING btree (employee_id, reference_date DESC)`
- `justification_evento_idx` — `app.justification USING btree (deviation_event_id)`
- `justification_tenant_id_fkidx` — `app.justification USING btree (tenant_id)`

</details>


## `app.leave_justification_map`

> JustificativaNome do espelho -> categoria do domínio. Linha sem validated_at NÃO entra em cálculo: o apurador de ciclo recusa a competência nomeando a string. Silêncio aqui dá vale transporte a quem faltou.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `tenant_id` 🔑 | uuid | não |  | `app.tenant` |  |
| `justification` 🔑 | text | não |  |  | Canonicalizada em upper(btrim(...)). Acento preservado: FÉRIAS e FERIAS são duas strings e cada uma se cura sozinha — normalizar acento seria adivinhar que são a mesma. |
| `category` | text | não |  |  |  |
| `validated_by` | uuid | sim |  | `auth.users` |  |
| `validated_at` | timestamp with time zone | sim |  |  | Nulo = provisório, e provisório NÃO é usado. Mais estreito que app.payroll_event_map de propósito: lá o indicador sai com aviso, aqui a apuração para. |
| `notes` | text | sim |  |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((btrim(justification) <> ''::text))`
- `CHECK ((category = ANY (ARRAY['vacation'::text, 'leave_period'::text, 'leave_of_absence'::text, 'suspension'::text, 'unjustified_absence'::text])))`
- `CHECK ((justification = upper(btrim(justification))))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `leave_justification_map_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |

<details><summary>Índices</summary>

- `leave_justification_map_categoria_idx` — `app.leave_justification_map USING btree (tenant_id, category)`

</details>


## `app.leave_period`

> Rótulo neutro por decisão de produto. Motivo de leave_period é dado de saúde e não é capturado.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `employee_id` | uuid | não |  | `app.employee` |  |
| `category` | text | não |  |  | Rótulo neutro: nunca o motivo. unjustified_absence é a exceção deliberada — ela afirma a AUSÊNCIA de justificativa, não uma condição, e as duas rotinas financeiras do DP (cesta e vale transporte) a leem. Sem ela, quem faltou recebe como quem trabalhou. |
| `start_date` | date | não |  |  |  |
| `end_date` | date | sim |  |  |  |
| `source` | text | não | `'secullum'::text` |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK (((end_date IS NULL) OR (end_date >= start_date)))`
- `CHECK ((category = ANY (ARRAY['vacation'::text, 'leave_period'::text, 'leave_of_absence'::text, 'suspension'::text, 'unjustified_absence'::text])))`
- `CHECK ((source = ANY (ARRAY['secullum'::text, 'manual'::text, 'spreadsheet'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `leave_period_read` | SELECT | `util.can_see_employee(employee_id)` | `-` |

<details><summary>Índices</summary>

- `leave_period_periodo_idx` — `app.leave_period USING btree (employee_id, start_date, end_date)`
- `leave_period_tenant_id_fkidx` — `app.leave_period USING btree (tenant_id)`

</details>


## `app.manager`

> O gestor como o espelho o declara: `secullum."Estrutura"`, alcançada por `Funcionario.EstruturaId`. É dimensão de agregação, NÃO vínculo com um registro de colaborador — resolver qual colaborador é este gestor exigiria casar nome, e a medição de 26/08 mostrou que o casamento falha nas quatro estruturas de produção.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `secullum_structure_id` | bigint | não |  |  |  |
| `name` | text | não |  |  | Vem de "Estrutura"."Descricao". Nome de pessoa, e é assim que o Secullum o guarda. |
| `active` | boolean | não | `true` |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |
| `updated_at` | timestamp with time zone | não | `now()` |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `manager_read` | SELECT | `(util.is_admin(tenant_id) OR (EXISTS ( SELECT 1` | `` |
| `manager_write` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |

<details><summary>Índices</summary>

- `manager_tenant_idx` — `app.manager USING btree (tenant_id) WHERE active`
- `UNIQUE manager_tenant_id_secullum_structure_id_key` — `app.manager USING btree (tenant_id, secullum_structure_id)`

</details>


## `app.message_template`

> Contrato único das três integrações de WhatsApp. `variables` é a ordem dos placeholders do template da Meta E o conjunto de chaves exigido no payload da fila. `body` é o mesmo texto renderizado localmente para os provedores não oficiais, que não têm template.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `code` | text | não |  |  |  |
| `category` | text | não | `'utility'::text` |  | utility para alerta operacional. Categoria errada faz a Meta reprovar o template ou cobrar como marketing — cerca de 9x mais caro no Brasil. |
| `language` | text | não | `'pt_BR'::text` |  |  |
| `variables` | text[] | não |  |  |  |
| `body` | text | não |  |  |  |
| `meta_template_name` | text | sim |  |  |  |
| `meta_status` | text | não | `'draft'::text` |  |  |
| `meta_rejection` | text | sim |  |  |  |
| `active` | boolean | não | `true` |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |
| `updated_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK ((category = ANY (ARRAY['utility'::text, 'authentication'::text, 'marketing'::text])))`
- `CHECK ((meta_status = ANY (ARRAY['draft'::text, 'pending'::text, 'approved'::text, 'rejected'::text, 'paused'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `message_template_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |
| `message_template_read` | SELECT | `util.has_tenant(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `message_template_tenant_idx` — `app.message_template USING btree (tenant_id, code) WHERE active`
- `UNIQUE message_template_tenant_id_code_language_key` — `app.message_template USING btree (tenant_id, code, language)`

</details>


## `app.metric`

> Catálogo fechado do assistente de IA. Métrica ausente daqui = pergunta que ele responde "não tenho esse dado", em vez de inventar. O alvo tem de responder o que o título promete: uma métrica de contagem apontada para uma view de linhas devolve o teto de linhas como se fosse a contagem.

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

> DADO DE SAÚDE (LGPD art. 5º II). Sem diagnóstico, sem CID, sem descrição de restrição. Só aptidão e validade. Importável pelo template `hr_exam` desde a migration 17, por quem tem o domínio `health`.

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


## `app.payroll_event_map`

> Código de evento da folha do cliente -> categoria do produto. Linha sem validated_at = mapeamento provisório, sinalizar na UI. Sem este mapa, metade do dashboard financeiro não existe — e com ele adivinhado, existe errado.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `tenant_id` 🔑 | uuid | não |  | `app.tenant` |  |
| `code` 🔑 | text | não |  |  |  |
| `category` | text | não |  |  |  |
| `label` | text | sim |  |  |  |
| `validated_by` | uuid | sim |  | `auth.users` |  |
| `validated_at` | timestamp with time zone | sim |  |  |  |
| `notes` | text | sim |  |  |  |

**Restrições**

- `CHECK ((category = ANY (ARRAY['base_salary'::text, 'overtime'::text, 'vacation'::text, 'thirteenth'::text, 'termination'::text, 'benefit'::text, 'charge'::text, 'deduction'::text, 'other'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `payroll_event_map_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |

<details><summary>Índices</summary>

- `payroll_event_map_categoria_idx` — `app.payroll_event_map USING btree (tenant_id, category)`

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


## `app.schedule_rotation_map`

> Rotação que o "HorarioDia" do Secullum não consegue escrever — 12x36 e afins. Uma linha por horário do espelho, curada com o cliente. Linha SEM validated_at é provisória e o motor de jornada NÃO a lê: rotação errada vira confiança 100 e alerta contra alguém. Vale apenas onde o horário não declara expediente nenhum.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `tenant_id` 🔑 | uuid | não |  | `app.tenant` |  |
| `secullum_schedule_id` 🔑 | bigint | não |  |  |  |
| `cycle_length_days` | smallint | não |  |  |  |
| `anchor_date` | date | não |  |  | Um dia em que o ciclo trabalha. O dia é de trabalho quando (data - âncora) mod ciclo é zero. A âncora pode ficar no meio da janela: o resto negativo do Postgres (-1 mod 2 = -1) não muda ESTE teste, porque só o zero decide e zero não tem sinal. Quem for calcular a POSIÇÃO no ciclo, e não só se é dia de trabalho, aí sim precisa normalizar. |
| `expected_entry` | time without time zone | não |  |  |  |
| `expected_exit` | time without time zone | não |  |  | Pode ser MENOR que expected_entry: é assim que um turno noturno se declara, do mesmo jeito que "HorarioDia" o declara. Quem trata a virada é regras.py. |
| `expected_break_minutes` | integer | sim |  |  |  |
| `workload_minutes` | integer | não |  |  |  |
| `tolerance_extra_minutes` | integer | não | `0` |  |  |
| `tolerance_absence_minutes` | integer | não | `0` |  |  |
| `validated_by` | uuid | sim |  | `auth.users` |  |
| `validated_at` | timestamp with time zone | sim |  |  |  |
| `notes` | text | sim |  |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK (((cycle_length_days >= 2) AND (cycle_length_days <= 31)))`
- `CHECK ((expected_break_minutes >= 0))`
- `CHECK ((tolerance_absence_minutes >= 0))`
- `CHECK ((tolerance_extra_minutes >= 0))`
- `CHECK ((workload_minutes > 0))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `rotation_map_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |


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
| `records_skipped` | integer | não | `0` |  | Registros lidos da origem que não viraram linha — tipicamente correlação quebrada (FuncionarioId sem colaborador local). Lido = escrito + pulado; sem esta coluna, uma execução que pulou tudo é indistinguível de uma janela vazia. |
| `scope` | text | não | `'incremental'::text` |  | incremental = janela curta, a cada 15 min (batidas) / 30 (cadastro). backfill = 7 dias, 1x/dia, fora de pico. As mesmas duas palavras de app.detection_run.scope (migration 13), de propósito. |

**Restrições**

- `CHECK ((scope = ANY (ARRAY['incremental'::text, 'backfill'::text])))`
- `CHECK ((status = ANY (ARRAY['running'::text, 'completed'::text, 'failed'::text, 'partial'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `sync_read` | SELECT | `util.is_admin(tenant_id)` | `-` |

<details><summary>Índices</summary>

- `sync_run_backfill_idx` — `app.sync_run USING btree (tenant_id, entity, started_at DESC) WHERE ((scope = 'backfill'::text) AND (status = 'completed'::text))`
- `sync_run_falha_idx` — `app.sync_run USING btree (tenant_id, started_at DESC) WHERE (status = 'failed'::text)`
- `sync_run_freshness_idx` — `app.sync_run USING btree (tenant_id, entity, finished_at DESC) WHERE (status = 'completed'::text)`
- `sync_run_idx` — `app.sync_run USING btree (integration_id, entity, started_at DESC)`
- `UNIQUE sync_run_em_andamento_key` — `app.sync_run USING btree (tenant_id, entity) WHERE (status = 'running'::text)`

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


## `app.transport_fare`

> Tarifa de transporte por linha e tipo (unitária ou ida-e-volta), com vigência. Reajuste = linha nova; a anterior fecha a faixa e mantém o valor que valeu.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `code` | text | não |  |  |  |
| `name` | text | não |  |  |  |
| `kind` | text | não |  |  |  |
| `amount` | numeric(12,2) | não |  |  |  |
| `effective_from` | date | não |  |  |  |
| `effective_to` | date | sim |  |  |  |
| `reason` | text | sim |  |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Restrições**

- `CHECK (((effective_to IS NULL) OR (effective_to >= effective_from)))`
- `CHECK ((amount >= (0)::numeric))`
- `CHECK ((kind = ANY (ARRAY['single'::text, 'round_trip'::text])))`

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `transport_fare_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |
| `transport_fare_read` | SELECT | `util.can_see_domain(tenant_id, 'compensation'::app.sensitive_domain)` | `-` |

<details><summary>Índices</summary>

- `UNIQUE transport_fare_open_band_idx` — `app.transport_fare USING btree (tenant_id, code, kind) WHERE (effective_to IS NULL)`

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


## `app.work_post`

> Quadro de Postos — unidade + código, o par que a rotina de vale transporte usa para achar a escala do colaborador. O elo posto -> escala (secullum_schedule_id) entra em migration própria: ver docs/SPEC-DP.md §0-bis.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `tenant_id` | uuid | não |  | `app.tenant` |  |
| `unit_id` | uuid | não |  | `app.unit` |  |
| `code` | text | não |  |  | Código do posto dentro da unidade. Único por (tenant, unidade), nunca global. |
| `name` | text | sim |  |  |  |
| `active` | boolean | não | `true` |  |  |
| `created_at` | timestamp with time zone | não | `now()` |  |  |

**Policies**

| Policy | Comando | USING | WITH CHECK |
|---|---|---|---|
| `work_post_admin` | ALL | `util.is_admin(tenant_id)` | `util.is_admin(tenant_id)` |
| `work_post_read` | SELECT | `util.can_see_unit(unit_id)` | `-` |

<details><summary>Índices</summary>

- `work_post_unit_idx` — `app.work_post USING btree (tenant_id, unit_id)`
- `UNIQUE work_post_tenant_id_unit_id_code_key` — `app.work_post USING btree (tenant_id, unit_id, code)`

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

> Registro-dia de ponto: UM item de GET /Batidas = um par (funcionario x data) com ate 5 pares Entrada/Saida em COLUNAS. NAO e uma batida individual — essa e batida_marcacao. Ver ADR-007 e ADR-011.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `BatidaId` | integer | sim |  |  | Campo `Id` do topo do registro de /Batidas (forma qualificada, ver ADR-012). ATRIBUTO com indice NAO-UNICO — NAO e a chave de idempotencia (alteracao (A) ao ADR-007). A chave e (funcionario_id, "Data"), unica por construcao. Divergencia entre os dois (mesmo par funcionario/data reaparecendo com outro Id) deve ser LOGADA como anomalia, nunca contornada em silencio. |
| `funcionario_id` | uuid | não |  | `secullum.Funcionario` |  |
| `FuncionarioId` | integer | sim |  |  | Campo `FuncionarioId` do payload — INTEIRO do Secullum, guardado como veio. E a chave de juncao com "Funcionario"."FuncionarioId". ⚠️ A FK real e funcionario_id (uuid), ao lado. |
| `Data` | date | não |  |  | Campo `Data`. ⛔ Parsing OBRIGATORIO pelos 10 PRIMEIROS CARACTERES da string ("yyyy-MM-ddT00:00:00"). Nunca via new Date(...)/toISOString(): a Edge Function roda em UTC e a conversao ingenua desloca um dia. A parte de hora do campo e sempre 00:00:00 e nao tem significado. |
| `Observacoes` | text | sim |  |  | ⚠️ TEXTO LIVRE. Ate 2026-08-12 era explicitamente NAO sincronizado por LGPD (podia carregar motivo de afastamento = dado de saude). Passa a ser persistido por decisao expressa do Owner (ADR-011). ⛔ Nunca exibir em relatorio ao gestor, nunca logar. A base legal para reter isto esta PENDENTE. |
| `Ajuste` | text | sim |  |  | [VALIDAR — Postman] Tipo real desconhecido (o cadastro de Justificativas trata Ajuste/Abono2..4 como boolean de abono automatico; no cartao ponto sao valores HH:mm). Modelado como TEXT para preservar o valor bruto sem risco de conversao errada. Mesma ressalva para "Abono2"/"Abono3"/"Abono4". |
| `Abono2` | text | sim |  |  |  |
| `Abono3` | text | sim |  |  |  |
| `Abono4` | text | sim |  |  |  |
| `Compensado` | boolean | não | `false` |  |  |
| `AlmocoLivre` | boolean | não | `false` |  |  |
| `Neutro` | boolean | não | `false` |  |  |
| `NBanco` | boolean | não | `false` |  | Campo `NBanco` (banco de horas do dia). ✅ Sob a nomenclatura literal (ADR-012) a abreviacao opaca deixou de ser um problema de decisao nossa: e simplesmente o nome que o Secullum usa. |
| `Folga` | boolean | não | `false` |  |  |
| `Refeicao` | boolean | não | `false` |  |  |
| `status_dia_rotulo` | text | sim |  |  | DERIVADO POR NOS (minusculo — nao procure este campo no payload): preenchido pelo parser quando as colunas do dia carregam TEXTO DE STATUS (ex.: rotulo de afastamento) em vez de horas. Torna explicito no relatorio que o dia nao e "falta", e status. ⛔ NUNCA e fonte de periodo de afastamento — essa e "FuncionarioAfastamento" (ADR-010). |
| `sincronizado_em` | timestamp with time zone | não | `now()` |  |  |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `batida_batidaid_idx` — `secullum."Batida" USING btree ("BatidaId")`
- `batida_data_idx` — `secullum."Batida" USING btree ("Data")`
- `batida_tenant_idx` — `secullum."Batida" USING btree (tenant_id)`
- `UNIQUE batida_funcionario_id_data_key` — `secullum."Batida" USING btree (funcionario_id, "Data")`

</details>


## `secullum.BatidaFonteDados`

> Objeto `FonteDados` aninhado em cada coluna de /Batidas — ate 10 por registro-dia (FonteDadosEntrada1..5 / FonteDadosSaida1..5). Nome composto: o prefixo "Batida" e NOSSO (agrupamento na listagem de tabelas); "FonteDados" e o tipo literal do Secullum, e cada linha E um desses objetos. 1:1 OPCIONAL com batida_marcacao: existe coluna preenchida SEM FonteDados (buraco conhecido, ADR-007).

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `batida_marcacao_id` | uuid | não |  | `app.batida_marcacao` |  |
| `batida_id` | uuid | não |  | `secullum.Batida` | NOSSA FK, desnormalizada a partir de batida_marcacao para permitir DELETE/consulta no escopo do dia inteiro sem join. Ambas as FKs sao ON DELETE CASCADE — expurgo por titular chega ate aqui. |
| `FonteDadosId` | bigint | sim |  |  |  |
| `Nsr` | text | sim |  |  | Numero Sequencial de Registro do equipamento. TEXT (nao numerico): e identificador, nao quantidade, e pode vir com zeros a esquerda. |
| `Hora` | time without time zone | sim |  |  |  |
| `Data` | date | sim |  |  |  |
| `DataInclusao` | timestamp with time zone | sim |  |  | Campo `DataInclusao` — quando o registro entrou no Secullum. Diagnostico de batida lancada RETROATIVAMENTE, que invalida desvio ja detectado e possivelmente ja enviado no relatorio. |
| `Tipo` | smallint | sim |  |  | Campo `Tipo` BRUTO (Original=0, Manual=1, PreAssinalado=2, Desconsiderado=3). smallint SEM CHECK e SEM enum do Postgres: valor fora do documentado e persistido, tolerado e traduzido apenas na apresentacao. |
| `Origem` | smallint | sim |  |  | Campo `Origem` BRUTO (0..8 documentados). ⚠️ Origem = 11 JA APARECEU em producao e nao consta da documentacao oficial; significado ainda [DECISAO DO OWNER]. Por isso: sem CHECK, sem enum, sem significado presumido, job nunca falha. Logar uma vez por valor desconhecido distinto por execucao. |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `batida_fonte_dados_batida_id_idx` — `secullum."BatidaFonteDados" USING btree (batida_id)`
- `batida_fonte_dados_fontedadosid_idx` — `secullum."BatidaFonteDados" USING btree ("FonteDadosId")`
- `batidafontedados_tenant_idx` — `secullum."BatidaFonteDados" USING btree (tenant_id)`
- `UNIQUE batida_fonte_dados_marcacao_key` — `secullum."BatidaFonteDados" USING btree (batida_marcacao_id)`

</details>


## `secullum.Cidade`

> Cidade — no aninhado { Id, Descricao } em Funcionario e em Empresa. Forma confirmada em 2026-08-13. Ver ADR-011.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `CidadeId` | integer | sim |  |  | Campo `Cidade.Id`. NULLABLE e SEM UNIQUE de proposito: o que se confirmou foi a FORMA do no, NAO a unicidade global do Id — que nunca foi verificada. Este projeto ja quebrou em producao duas vezes supondo unicidade global de id do Secullum. A chave de idempotencia e "Descricao". |
| `Descricao` | text | não |  |  |  |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `cidade_tenant_idx` — `secullum."Cidade" USING btree (tenant_id)`
- `UNIQUE cidade_descricao_key` — `secullum."Cidade" USING btree ("Descricao")`

</details>


## `secullum.Departamento`

> Departamento = unidade de estacionamento. Espelha o no `Funcionario.Departamento { Id, Descricao, Nfolha }`; a rota standalone GET /Departamentos NAO e chamada. Ver ADR-006 e ADR-008.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `empresa_id` | uuid | não |  | `secullum.Empresa` | NOSSA FK (uuid). ⚠️ EMPRESA DE REFERENCIA, nao de propriedade (ADR-008): e a empresa do PRIMEIRO funcionario visto naquele departamento. ⛔ Agregacao por Empresa usa SEMPRE "Funcionario".empresa_id, NUNCA esta coluna. |
| `DepartamentoId` | integer | não |  |  | Campo `Departamento.Id`. Chave de idempotencia, UNIQUE GLOBAL (ADR-008). O detector de colisao (unit_name_changed / unit_ref_name_conflict nos logs) continua sendo a rede de seguranca. |
| `Descricao` | text | não |  |  |  |
| `ativo` | boolean | não | `true` |  | DERIVADO/FIXO POR NOS (minusculo): o Secullum NAO expoe status de Departamento ({ Id, Descricao, Nfolha }). Fica fixo em true e NAO ha tabela de historico. ⛔ Nao inferir desativacao pela ausencia do DepartamentoId no lote de /Funcionarios (ADR-009). |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `Nfolha` | text | sim |  |  | Campo `Departamento.Nfolha` (grafia literal confirmada em payload real: "Nfolha", f minusculo). Numero visivel na folha. ⚠️ Se algum identificador de Departamento se repetir entre empresas, o candidato natural e este, NAO "DepartamentoId" (ADR-008). |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `"Departamento_empresa_id_fkidx"` — `secullum."Departamento" USING btree (empresa_id)`
- `departamento_tenant_idx` — `secullum."Departamento" USING btree (tenant_id)`
- `UNIQUE departamento_departamentoid_key` — `secullum."Departamento" USING btree ("DepartamentoId")`

</details>


## `secullum.Empresa`

> Empresa (agrupador) — espelha o no `Funcionario.Empresa` aninhado em /Funcionarios. ⚠️ ATENCAO AO ALCANCE REAL DOS CAMPOS: o no aninhado confirmado traz { Id, Nome, Documento, Desativada, ... }. As demais colunas vem do CADASTRO DE EMPRESAS do manual (rota GET /Empresas, que este projeto NAO chama) e podem permanecer NULAS para sempre. Elas existem porque o Owner pediu captura completa (ADR-011); nenhuma delas tem consumidor de produto hoje. Ver ADR-006, ADR-011 e ADR-012.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `Documento` | text | não |  |  | Campo `Documento` (CNPJ/CPF) — chave natural de idempotencia da sincronizacao, que e a chave que o proprio Secullum usa na rota Empresas. |
| `Nome` | text | não |  |  |  |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `EmpresaId` | integer | sim |  |  | Campo `Empresa.Id`. ATRIBUTO com indice NAO-UNICO: a chave de idempotencia continua sendo "Documento", que e a chave que o proprio Secullum usa na rota Empresas. Nao promover a UNIQUE sem evidencia. |
| `Desativada` | boolean | sim |  |  | Campo `Empresa.Desativada` — ESTADO ATUAL, sem data. O Secullum nao informa QUANDO a empresa foi desativada; por isso empresa_evento_status so tem detectado_em. Escreva AQUI, nunca em `ativo`. |
| `Inscricao` | text | sim |  |  |  |
| `Endereco` | text | sim |  |  |  |
| `Bairro` | text | sim |  |  |  |
| `cidade_id` | uuid | sim |  | `secullum.Cidade` | NOSSA FK (uuid) -> "Cidade". ⚠️ NAO confundir com "CidadeId" (inteiro do Secullum), ao lado. |
| `CidadeId` | integer | sim |  |  |  |
| `Cep` | text | sim |  |  |  |
| `Uf` | text | sim |  |  |  |
| `Pais` | text | sim |  |  |  |
| `Telefone` | text | sim |  |  |  |
| `Fax` | text | sim |  |  |  |
| `Cei` | text | sim |  |  |  |
| `NfolhaEmpresa` | text | sim |  |  | [VALIDAR — Postman] Grafia assumida por analogia com `Departamento.Nfolha` (confirmado com f minusculo). Vem do cadastro do manual, nao do no aninhado — pode nunca ser populado (ver aviso abaixo). |
| `Logotipo` | text | sim |  |  | Logotipo em base 64. Volume irrelevante com poucas empresas. ⚠️ Se o cadastro crescer, avaliar deixar de sincronizar — nao ha consumidor de produto para ele hoje. |
| `PossuiLogo` | boolean | sim |  |  |  |
| `ResponsavelNome` | text | sim |  |  | ⚠️ Responsavel LEGAL da empresa. NAO e o gestor que recebe o relatorio consolidado — esse vive na tabela "Estrutura", vem de `Funcionario.Estrutura` e e outra pessoa. Foi para evitar exatamente esta confusao que a tabela de gestor NAO se chama `Responsavel`. |
| `ResponsavelCargo` | text | sim |  |  |  |
| `ResponsavelEmail` | text | sim |  |  |  |
| `TipoDocumento` | smallint | sim |  |  | Enum BRUTO (0=CNPJ, 1=CPF, 2=Outros). smallint SEM CHECK — disciplina do projeto para enum do Secullum: valor desconhecido e persistido e tolerado, nunca derruba o job. |
| `UtilizaRepC` | boolean | sim |  |  |  |
| `UtilizaRepA` | boolean | sim |  |  |  |
| `UtilizaRepP` | boolean | sim |  |  |  |
| `UsaFechamentoDoPontoEspecifico` | boolean | sim |  |  | [VALIDAR — Postman] Nao consta do manual oficial (pag. 7-9); reportado pelo Owner no payload real. |
| `FechamentoPonto` | smallint | sim |  |  | [VALIDAR — Postman] Tipo assumido smallint (por analogia com `HorarioDia.Fechamento`, Inteiro 0..23). Se o payload real trouxer "HH:mm" ou boolean, abrir migration corretiva — nao forcar conversao no parser. |
| `DiaFechamentoPonto` | smallint | sim |  |  | [VALIDAR — Postman] Tipo assumido smallint (dia do mes). Mesma ressalva de "FechamentoPonto". |
| `EmitiuAtestadoTecnico` | boolean | sim |  |  | [VALIDAR — Postman] Nao consta do manual oficial; reportado pelo Owner no payload real. |
| `ativo` | boolean | não | `COALESCE((NOT "Desativada"), true)` |  | DERIVADA POR NOS (minusculo) e GERADA PELO POSTGRES: coalesce(not "Desativada", true). ⛔ O upsert da sincronizacao NAO pode incluir esta coluna — o Postgres rejeita escrita em coluna gerada. Grave "Desativada". Ver o cabecalho da secao 4 desta migration e ADR-009. |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `empresa_cidade_id_idx` — `secullum."Empresa" USING btree (cidade_id)`
- `empresa_empresaid_idx` — `secullum."Empresa" USING btree ("EmpresaId")`
- `empresa_tenant_idx` — `secullum."Empresa" USING btree (tenant_id)`
- `UNIQUE empresa_documento_key` — `secullum."Empresa" USING btree ("Documento")`

</details>


## `secullum.Estrutura`

> ⚠️ LEIA O CABECALHO DA SECAO 6 DE 20260813160000_rename_schema_secullum.sql ANTES DE MEXER AQUI. Esta tabela espelha o OBJETO ANINHADO `Funcionario.Estrutura` de /Funcionarios — NAO a rota standalone GET /Estruturas, que foi DESCARTADA pelo ADR-006 e nao e chamada em nenhum fluxo. Papel de negocio: e o GESTOR responsavel pelo(s) departamento(s); "Descricao" e o NOME dele. Origem hibrida: "Descricao"/"EstruturaPaiId" vem do Secullum; email vem por match de nome dentro do proprio /Funcionarios (com protecao via email_origem); whatsapp e canais_notificacao sao SEMPRE cadastro manual do Owner. ⚠️ NAO confundir com "Empresa"."ResponsavelNome" (responsavel LEGAL da empresa, outra pessoa). Ver docs/03-integracao-secullum.md ("Resolucao do gestor").

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `EstruturaId` | integer | não |  |  | Campo `Funcionario.EstruturaId` (= `Estrutura.Id`) — chave de idempotencia. Nunca resolvido subindo por "EstruturaPaiId". |
| `EstruturaPaiId` | integer | sim |  |  | Campo `Estrutura.EstruturaPaiId`. Guardado so como contexto/diagnostico. 0 = raiz. ⏳ EM ABERTO (ADR-006): qual nivel da arvore e o gestor quando a estrutura nao for raiz. Ate isso ser respondido pelo Owner, NAO subir a arvore. |
| `Descricao` | text | não |  |  | Campo `Estrutura.Descricao` — na pratica, o NOME do gestor responsavel. E o unico dado de identificacao do gestor que o Secullum fornece: e-mail e WhatsApp nao existem la. |
| `email` | text | sim |  |  | NOSSO (minusculo) apesar de o VALOR vir do Secullum: nao e um campo de `Estrutura`, e o `Funcionario.Email` do funcionario cujo "Nome" bate com "Descricao". E resultado da NOSSA logica de match, nao um no do payload. |
| `email_origem` | text | não | `'manual'::text` |  | NOSSO (minusculo). manual (default) | secullum. A sincronizacao SO escreve em email quando email IS NULL OU email_origem = 'secullum'. Valor cadastrado pelo Owner NUNCA e sobrescrito. |
| `whatsapp` | text | sim |  |  | NOSSO (minusculo) — SEMPRE cadastro manual do Owner, nao ha campo equivalente no Secullum. ⛔ NAO derivar de "Funcionario"."Celular"/"Telefone" (agora capturados): telefone pessoal nao e canal de notificacao autorizado. Ver docs/06-seguranca-lgpd.md. |
| `canais_notificacao` | text[] | não | `'{}'::text[]` |  |  |
| `ativo` | boolean | não | `true` |  |  |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Restrições**

- `CHECK ((canais_notificacao <@ ARRAY['whatsapp'::text, 'email'::text]))`
- `CHECK ((email_origem = ANY (ARRAY['manual'::text, 'secullum'::text])))`

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `estrutura_tenant_idx` — `secullum."Estrutura" USING btree (tenant_id)`
- `UNIQUE estrutura_estruturaid_key` — `secullum."Estrutura" USING btree ("EstruturaId")`

</details>


## `secullum.Funcao`

> Funcao/cargo do funcionario. Populada a partir do no aninhado em /Funcionarios — a rota standalone GET /Funcoes NAO e chamada (escopo de 5 endpoints, docs/03-integracao-secullum.md).

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `FuncaoId` | integer | sim |  |  | Campo `Funcao.Id`, quando presente. NULLABLE e sem UNIQUE — mesma disciplina de "Cidade"."CidadeId". A chave de idempotencia e "Descricao" (que e a chave usada pelo proprio Secullum na rota Funcoes). |
| `Descricao` | text | não |  |  |  |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `funcao_tenant_idx` — `secullum."Funcao" USING btree (tenant_id)`
- `UNIQUE funcao_descricao_key` — `secullum."Funcao" USING btree ("Descricao")`

</details>


## `secullum.Funcionario`

> Funcionario. ⚠️ A partir de 2026-08-13 (ADR-011) esta tabela deixou de ser um "cache minimo" e passa a guardar TODO o cadastro devolvido por /Funcionarios, incluindo PII sensivel (RG, endereco, telefone, celular, e-mail, filiacao, nascimento). A minimizacao anterior foi REVERTIDA por decisao expressa do Owner. A base legal formal para essa retencao continua PENDENTE — ver docs/06-seguranca-lgpd.md.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `departamento_id` | uuid | não |  | `secullum.Departamento` |  |
| `empresa_id` | uuid | não |  | `secullum.Empresa` | NOSSA FK (uuid). Desnormalizada de proposito em relacao a "Departamento".empresa_id — e assim que o Secullum entrega o dado, e o dashboard agrega por Empresa. ⛔ Agregacao por Empresa usa SEMPRE esta coluna. ⚠️ NAO confundir com "EmpresaId" (inteiro do Secullum), criada em 20260813161000. |
| `FuncionarioId` | integer | não |  |  | Campo `Funcionario.Id` — nomeado na forma qualificada porque e literalmente assim que o Secullum o chama de fora (`Batidas.FuncionarioId`). Chave de idempotencia e chave de juncao com /Batidas. |
| `Cpf` | text | sim |  |  | Campo `Cpf`. Sem UNIQUE de proposito: duplicata no cadastro do cliente cai no caso "2+ candidatos" da correlacao de afastamentos, que se abstem em vez de errar o titular. |
| `NumeroPis` | text | sim |  |  | Campo `NumeroPis`. Pode vir string vazia — tratar "" como AUSENTE. Sem UNIQUE, mesmo racional de "Cpf". |
| `Nome` | text | não |  |  |  |
| `horario_id` | uuid | sim |  | `secullum.Horario` | NOSSA FK (uuid) -> "Horario". NULLABLE: funcionario sem horario cadastrado no Secullum nao derruba a sincronizacao (fica sem horario, com aviso em log). ⚠️ NAO confundir com "HorarioId" (inteiro do Secullum). |
| `ativo` | boolean | não | `true` |  | DERIVADO POR NOS (minusculo, NAO e campo do Secullum): VINCULO EMPREGATICIO, calculado a partir das datas com "hoje" em America/Sao_Paulo: ativo = ("Admissao" is null or "Admissao" <= hoje) and ("Demissao" is null or "Demissao" >= hoje). ⛔ NAO e afetado por ferias/afastamento — para isso existe afastado_hoje. ⚠️ Continua sendo COLUNA NORMAL (ao contrario de "Empresa".ativo, que virou gerada): esta derivacao depende de "hoje", nao e funcao imutavel das colunas, e por isso NAO pode ser GENERATED. Ver ADR-009 e ADR-010. |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `Admissao` | date | sim |  |  | Funcionario.Admissao (data real do Secullum, ja presente no payload de /Funcionarios). Entra na allow-list de PII: e dado de vinculo empregaticio necessario para saber se o funcionario estava ativo na janela do relatorio/dashboard. Ver docs/06-seguranca-lgpd.md. |
| `Demissao` | date | sim |  |  | Funcionario.Demissao (data real do Secullum; null enquanto o vinculo estiver ativo). Pode vir com data FUTURA (desligamento programado) — ver a regra de derivacao de employee.active em docs/04-modelo-dados.md. |
| `afastado_hoje` | boolean | não | `false` |  | DERIVADO POR NOS (minusculo). O nome declara a limitacao no proprio identificador: responde APENAS "esta afastado HOJE?". Para "estava afastado na data X?" (motor, relatorio, dashboard) a fonte da verdade e SEMPRE "FuncionarioAfastamento". E funcao do tempo: vira sozinho no primeiro e no ultimo dia do afastamento, sem nada mudar no Secullum. |
| `afastamento_atual_id` | uuid | sim |  | `secullum.FuncionarioAfastamento` | Ponteiro para o registro de employee_absence que cobre "hoje" (null quando on_leave = false). Existe para o painel mostrar "afastado ate DD/MM" com um unico join, sem duplicar as datas em employee (dado duplicado = dado que dessincroniza). ON DELETE SET NULL: se o afastamento sumir do Secullum e for removido pela convergencia, o ponteiro se limpa sozinho. Havendo mais de um periodo cobrindo hoje (sobreposicao), aponta o de maior end_date e a sobreposicao e logada como aviso (absence_overlap). |
| `NumeroFolha` | text | sim |  |  | Campo `NumeroFolha` (Texto(22)) — matricula na folha. Dado pessoal identificador. |
| `NumeroIdentificador` | text | sim |  |  |  |
| `NumeroProvisorio` | text | sim |  |  |  |
| `Carteira` | text | sim |  |  |  |
| `CodigoHolerite` | text | sim |  |  |  |
| `Observacao` | text | sim |  |  | ⚠️ TEXTO LIVRE de RH (Texto(255)). Alto risco de conter dado de saude/condicao pessoal. Persistido por decisao do Owner (ADR-011), contrariando a regra anterior de descarte de texto livre. ⛔ Nunca exibir em relatorio ao gestor, nunca logar, nunca indexar para busca. |
| `Endereco` | text | sim |  |  |  |
| `Bairro` | text | sim |  |  |  |
| `cidade_id` | uuid | sim |  | `secullum.Cidade` | NOSSA FK (uuid) -> "Cidade". ⚠️ NAO confundir com "CidadeId" (inteiro do Secullum), ao lado. |
| `CidadeId` | integer | sim |  |  |  |
| `Uf` | text | sim |  |  |  |
| `Cep` | text | sim |  |  |  |
| `Telefone` | text | sim |  |  |  |
| `Celular` | text | sim |  |  | Campo `Celular`. ⛔ NAO usar como numero de WhatsApp para notificacao — telefone pessoal nao e canal autorizado. "Estrutura".whatsapp continua 100% manual ([DECISAO DO OWNER]). |
| `Email` | text | sim |  |  | Campo `Email` do funcionario. ⚠️ Ate 2026-08-13 so era lido em memoria para resolver "Estrutura".email quando o funcionario ERA o gestor; agora e persistido para todos. Isso NAO autoriza usa-lo como canal de notificacao: destinatario de relatorio continua sendo apenas "Estrutura".email/"Estrutura".whatsapp. |
| `Rg` | text | sim |  |  | ⚠️ PII sensivel, capturada a partir de 2026-08-13 por decisao do Owner (ADR-011). Antes era explicitamente descartada pelo parser. Nunca logar, nunca exibir em notificacao. |
| `ExpedicaoRg` | date | sim |  |  |  |
| `Ssp` | text | sim |  |  |  |
| `Mae` | text | sim |  |  | ⚠️ PII de TERCEIRO (a mae do funcionario nao e titular deste tratamento nem tem relacao com o controlador). Capturada por decisao do Owner; e o campo com a justificativa de finalidade mais fraca de todo o schema. Vale o mesmo para "Pai". Ver docs/06-seguranca-lgpd.md. |
| `Pai` | text | sim |  |  |  |
| `Nascimento` | date | sim |  |  |  |
| `Masculino` | boolean | sim |  |  |  |
| `Nacionalidade` | text | sim |  |  |  |
| `Naturalidade` | text | sim |  |  |  |
| `funcao_id` | uuid | sim |  | `secullum.Funcao` | NOSSA FK (uuid) -> "Funcao". ⚠️ NAO confundir com "FuncaoId" (inteiro do Secullum), ao lado. |
| `FuncaoId` | integer | sim |  |  |  |
| `EmpresaId` | integer | sim |  |  | Campo `Funcionario.EmpresaId` — INTEIRO do Secullum, como veio. ⚠️ A FK que o sistema usa e empresa_id (uuid). Nunca fazer join por esta coluna. |
| `DepartamentoId` | integer | sim |  |  | Campo `Funcionario.DepartamentoId` — INTEIRO do Secullum. A FK usada e departamento_id (uuid). |
| `HorarioId` | integer | sim |  |  | Campo `Funcionario.HorarioId` — INTEIRO do Secullum. A FK usada e horario_id (uuid). ℹ️ Em /Funcionarios o objeto `Horario` aninhado vem com `Dias` = null POR DESIGN: a grade completa so vem de GET /Horarios. |
| `EstruturaId` | integer | sim |  |  | Campo `Funcionario.EstruturaId` — INTEIRO do Secullum; e a chave de idempotencia de "Estrutura" (tabela do gestor). Nao ha FK uuid daqui para "Estrutura": o vinculo gestor->departamento e o que importa ao produto, e resolve-lo por funcionario duplicaria a relacao. |
| `NaoVerificarDigital` | boolean | sim |  |  |  |
| `Master` | boolean | sim |  |  |  |
| `PossuiFoto` | boolean | sim |  |  | Apenas o indicador. A imagem em si exigiria a rota Funcionarios/fotos (6o endpoint) e NAO e buscada. |
| `Invisivel` | boolean | sim |  |  |  |
| `PeriodoEncerrado` | text | sim |  |  | [VALIDAR — Postman] Tipo desconhecido (data? boolean?). Modelado como TEXT para nao perder o valor nem quebrar o job por conversao errada; converter em migration corretiva depois da inspecao do payload. |
| `DesconsiderarPerimetrosGlobais` | boolean | sim |  |  |  |
| `AceitouTermosLgpdApp` | boolean | sim |  |  |  |
| `DataUltimoEnvio` | timestamp with time zone | sim |  |  |  |
| `DataUltimoLogin` | timestamp with time zone | sim |  |  |  |
| `DataAlteracao` | timestamp with time zone | sim |  |  |  |
| `EscolaridadeId` | integer | sim |  |  |  |
| `Filtro1Id` | integer | sim |  |  |  |
| `Filtro2Id` | integer | sim |  |  |  |
| `MotivoDemissaoId` | integer | sim |  |  | Campo `MotivoDemissaoId` bruto. A rota MotivosDemissao NAO e consumida (escopo de 5 endpoints), entao o motivo em texto nao existe localmente — o que, alias, e desejavel: motivo de demissao e dado sensivel de vinculo. |
| `NivelPermissaoId` | integer | sim |  |  |  |
| `PerfilId` | integer | sim |  |  |  |
| `PerfilFuncionarioId` | integer | sim |  |  |  |
| `BancoHorasId` | integer | sim |  |  |  |
| `HorarioAlternativo2Id` | integer | sim |  |  | Campo `HorarioAlternativo2Id` — inteiro BRUTO, sem FK para "Horario" de proposito: o horario referenciado pode nao existir localmente (ou ainda nao ter sido sincronizado no ciclo), e uma FK transformaria isso em falha de job. Resolucao para "Horario".id, se necessaria, e da consulta. |
| `HorarioAlternativo3Id` | integer | sim |  |  |  |
| `HorarioAlternativo4Id` | integer | sim |  |  |  |
| `ConfigEspecificaInclusaoManualPonto` | boolean | sim |  |  | ✅ Nome confirmado no payload real (2026-08-13). ⏳ [VALIDAR — Postman] TIPO: a inspecao entregou so a chave. Assumido boolean; se for enum de modo (0/1/2), abrir migration corretiva. ⛔ Parser deve normalizar e devolver NULL em valor inesperado, nunca derrubar o ciclo. |
| `ConfigEspecificaInclusaoManualPontoFusoHorarioId` | integer | sim |  |  | ✅ Nome confirmado. Sufixo Id => integer bruto, SEM FK: o cadastro de fusos horarios do Secullum nao e consumido por este projeto. |
| `ConfigEspecificaDesativarVerificacaoLocalFicticio` | boolean | sim |  |  |  |
| `ConfigEspecificaInclusaoPontoSemLocalizacao` | boolean | sim |  |  |  |
| `ConfigEspecificaInclusaoPontoOffline` | boolean | sim |  |  |  |
| `ConfigEspecificaCapturaDeFotoNoMomentoDaInclusao` | boolean | sim |  |  | ✅ Nome confirmado. ⚠️ E apenas a CONFIGURACAO. Nenhuma foto e buscada nem armazenada por este projeto (ver "PossuiFoto" e o cabecalho desta migration). |
| `BloquearRegistroPontoTeclado` | boolean | sim |  |  |  |
| `PermiteInclusaoPontoManual` | boolean | sim |  |  |  |
| `PermiteInclusaoDispositivosAutorizados` | boolean | sim |  |  |  |
| `DesabilitarAssinaturaEletronica` | boolean | sim |  |  | ✅ Nome confirmado. ⏳ [VALIDAR — Postman] tipo assumido boolean, como os demais Bloquear*/Permite*/Desabilitar* deste bloco. |
| `Foto` | bytea | sim |  |  | Campo literal do Secullum (imagem do funcionário), vinda do 6º endpoint (GET Funcionarios/fotos?funcionarioId=<Id>), NÃO de /Funcionarios. Guarda os BYTES JÁ DECODIFICADOS (o prefixo "data:<mime>;base64," da data URI NÃO é armazenado aqui — ver foto_mime). NULL = não temos (nunca buscada OU funcionário sem foto). 🔴 A coluna mais restrita do schema: nunca em view exposta ao painel, nunca em log, nunca em relatório (ADR-018 §6.3). ⛔ NUNCA escrita pelo upsert de sync-cadastro — só pelo UPDATE direcionado do job sync-fotos. |
| `foto_sincronizada_em` | timestamp with time zone | sim |  |  | NOSSA. Timestamp da última sincronização BEM-SUCEDIDA do job sync-fotos — inclui o sucesso "não tem foto" (ausência confirmada pelo Secullum). Distinta de foto_tentativa_em: uma tentativa que deu ERRO atualiza só foto_tentativa_em, nunca esta coluna (ADR-018 §5.3 — erro nunca apaga/mascara dado real). |
| `foto_tentativa_em` | timestamp with time zone | sim |  |  | NOSSA. Timestamp da última TENTATIVA do job sync-fotos, com ou sem sucesso. 🔴 É esta coluna (não foto_sincronizada_em) que ordena a fila (funcionario_foto_fila_idx, ORDER BY ... NULLS FIRST) — sem ela, um funcionário cuja busca falha sempre travaria a cabeça da fila para sempre (ADR-018 §4.1). |
| `foto_hash` | text | sim |  |  | NOSSA. sha256 em hex dos BYTES DECODIFICADOS de "Foto" (nunca da string base64/data URI original — duas fotos idênticas com prefixos textualmente diferentes têm o mesmo hash). Permite pular o UPDATE do binário quando nada mudou e é a única forma de dizer "a foto mudou" em log sem citar conteúdo. |
| `foto_bytes` | integer | sim |  |  | NOSSA. Tamanho em bytes da imagem DECODIFICADA. Observabilidade/dimensionamento, sem depender de octet_length("Foto") (que exigiria ler o binário). |
| `foto_mime` | text | sim |  |  | NOSSA. image/jpeg, image/png, ou NULL quando não determinável. Fonte primária: o prefixo da data URI do 6º endpoint (confirmado por payload real, 2026-08-31); o *magic number* dos bytes é usado só como CONFERÊNCIA (diverge => vence o conteúdo real, com aviso agregado foto_mime_divergente). ⛔ Sem CHECK e sem lista fechada — mesma disciplina dos demais enums/mime deste schema. ⛔ Nunca inferir por nome de arquivo, nunca assumir JPEG por padrão. |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `"Funcionario_afastamento_atual_id_fkidx"` — `secullum."Funcionario" USING btree (afastamento_atual_id)`
- `"Funcionario_departamento_id_fkidx"` — `secullum."Funcionario" USING btree (departamento_id)`
- `"Funcionario_empresa_id_fkidx"` — `secullum."Funcionario" USING btree (empresa_id)`
- `"Funcionario_horario_id_fkidx"` — `secullum."Funcionario" USING btree (horario_id)`
- `funcionario_afastado_hoje_idx` — `secullum."Funcionario" USING btree (afastado_hoje) WHERE (afastado_hoje = true)`
- `funcionario_cidade_id_idx` — `secullum."Funcionario" USING btree (cidade_id)`
- `funcionario_foto_fila_idx` — `secullum."Funcionario" USING btree (foto_tentativa_em NULLS FIRST) WHERE "PossuiFoto"`
- `funcionario_funcao_id_idx` — `secullum."Funcionario" USING btree (funcao_id)`
- `funcionario_tenant_idx` — `secullum."Funcionario" USING btree (tenant_id)`
- `UNIQUE funcionario_funcionarioid_key` — `secullum."Funcionario" USING btree ("FuncionarioId")`

</details>


## `secullum.FuncionarioAfastamento`

> Periodos (JANELAS) de afastamento/ferias — fonte: GET /IntegracaoExterna/FuncionariosAfastamentos. Nome escolhido a partir do nome da rota (o manual nao nomeia um tipo para o item) — ver secao 10 da migration 20260813160000. NAO confundir com funcionario_evento_status (transicoes de vinculo): o funcionario continua ativo = true durante ferias. Tabela MUTAVEL (upsert + DELETE de convergencia), ao contrario das tabelas *_evento_status, que sao append-only. Ver ADR-010.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `funcionario_id` | uuid | não |  | `secullum.Funcionario` | Correlacao resolvida EM MEMORIA por NumeroPis (prioridade) com fallback para Cpf: este endpoint NAO tem FuncionarioId, diferente de /Batidas. NumeroPis pode vir string vazia (visto em payload real) — tratar "" como ausente. Comparacao sempre sobre digitos (strip de mascara) nos dois lados. Zero ou 2+ candidatos => registro DESCARTADO com aviso agregado, nunca escolha arbitraria (mesma regra do match de gestor, docs/03-integracao-secullum.md). |
| `AfastamentoId` | integer | não |  |  | Campo `Id` do registro de afastamento (nao consta da tabela oficial do manual; confirmado em payload real). Forma qualificada pelo mesmo motivo de "FuncionarioId": `Id` puro colidiria por case com o `id` interno. Unicidade global NUNCA verificada — por isso a chave e COMPOSTA com funcionario_id. |
| `Inicio` | date | não |  |  | Campo `Inicio` (Data, obrigatorio). Parsing obrigatorio: 10 PRIMEIROS CARACTERES da string. NUNCA via new Date(...)/toISOString() — a Edge Function roda em UTC e a conversao ingenua desloca um dia. |
| `Fim` | date | não |  |  | Campo `Fim`, INCLUSIVO (o dia de Fim ainda e afastamento). Parsing pelos 10 primeiros caracteres da string, nunca via Date/UTC. ⛔ Sem CHECK ("Fim" >= "Inicio") de proposito: registro invertido na origem nao pode derrubar o job — o parser loga absence_invalid_range, nao grava e segue. |
| `JustificativaNome` | text | sim |  |  | Campo `JustificativaNome` (Texto(7)), bruto, sem CHECK e sem lista fechada. ⚠️ Tratar como potencialmente revelador de saude: nunca exibido cru em relatorio/painel e nunca logado junto de identificacao do titular. O cadastro de Justificativas NAO e consumido. |
| `DataInclusao` | timestamp with time zone | sim |  |  | Campo `DataInclusao` (nao documentado na tabela oficial; confirmado em payload real). Quando o registro foi criado no Secullum. Serve para diagnosticar afastamento lancado RETROATIVAMENTE, que invalida desvios ja detectados na janela — ver requisito do motor em sprints/sprint-02-motor-deteccao.md. |
| `correlacionado_por` | text | não | `'pis'::text` |  | NOSSO (minusculo) — diagnostico (pis | cpf): qual chave resolveu a correlacao. Nao e PII: guarda o TIPO de chave, nunca o valor. |
| `sincronizado_em` | timestamp with time zone | não | `now()` |  | Ultima vez que este registro foi visto na resposta do Secullum. Base do delete de convergencia (registro apagado no Secullum tem de sumir daqui, senao suprime desvio para sempre). |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Restrições**

- `CHECK ((correlacionado_por = ANY (ARRAY['pis'::text, 'cpf'::text])))`

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `funcionario_afastamento_funcionario_janela_idx` — `secullum."FuncionarioAfastamento" USING btree (funcionario_id, "Inicio", "Fim")`
- `funcionario_afastamento_janela_idx` — `secullum."FuncionarioAfastamento" USING btree ("Fim", "Inicio")`
- `funcionarioafastamento_tenant_idx` — `secullum."FuncionarioAfastamento" USING btree (tenant_id)`
- `UNIQUE funcionario_afastamento_funcionario_afastamentoid_key` — `secullum."FuncionarioAfastamento" USING btree (funcionario_id, "AfastamentoId")`

</details>


## `secullum.FuncionarioCentroCusto`

> Centros de custo do funcionario (`ListaCentroDeCustos`, array de { Descricao } em /Funcionarios). ON DELETE CASCADE sustenta o expurgo por titular (docs/06-seguranca-lgpd.md). Escrita por substituicao integral por funcionario.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `funcionario_id` | uuid | não |  | `secullum.Funcionario` |  |
| `Descricao` | text | não |  |  | Unico campo do item no payload. A chave (funcionario_id, "Descricao") e a unica identidade possivel. |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `funcionario_centro_custo_funcionario_id_idx` — `secullum."FuncionarioCentroCusto" USING btree (funcionario_id)`
- `funcionariocentrocusto_tenant_idx` — `secullum."FuncionarioCentroCusto" USING btree (tenant_id)`
- `UNIQUE funcionario_centro_custo_key` — `secullum."FuncionarioCentroCusto" USING btree (funcionario_id, "Descricao")`

</details>


## `secullum.Horario`

> Horario (grade prevista) — espelha `Horario` de GET /Horarios (chamada sem parametro). Ver docs/04-modelo-dados.md.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `HorarioId` | integer | não |  |  | Campo `Horario.Id` — chave de idempotencia local. |
| `Numero` | integer | sim |  |  | Campo `Horario.Numero` — chave de NEGOCIO do Secullum (a rota Horarios?numero=<N> usa este campo). NAO e a chave de idempotencia local, que e "HorarioId". |
| `Descricao` | text | sim |  |  |  |
| `ativo` | boolean | não | `true` |  | DERIVADO POR NOS (minusculo) do campo `Desativar`. ⏳ O campo literal "Desativar" NAO foi criado: tipo/semantica exatos nao confirmados no payload real (docs/03-integracao-secullum.md). Nao inventar coluna — abrir migration corretiva quando o tipo for observado. |
| `sincronizado_em` | timestamp with time zone | sim |  |  |  |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horario_tenant_idx` — `secullum."Horario" USING btree (tenant_id)`
- `UNIQUE horario_horarioid_key` — `secullum."Horario" USING btree ("HorarioId")`

</details>


## `secullum.HorarioDescanso`

> No `Horario.Descanso` (tipo `HorarioDescanso`, regras de DSR) — 1:1 com "Horario". Estrutura bate com o manual (confirmado em 2026-08-13). Regras de folha: capturadas, ⛔ NAO consumidas pelo motor.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `horario_id` | uuid | não |  | `secullum.Horario` |  |
| `HorarioId` | integer | sim |  |  |  |
| `Tipo` | smallint | sim |  |  | Enum bruto (Automatico=0, Variavel=1), smallint sem CHECK. |
| `ValorDescanso` | text | sim |  |  | Texto(5) no formato HH:mm, mas semanticamente uma DURACAO (valor do DSR), nao um horario do dia. Mantido TEXT de proposito: o tipo `time` do Postgres nao representa duracao acima de 24h e induziria comparacoes erradas. Este sistema nao calcula DSR. |
| `LimiteHorasFaltas` | text | sim |  |  | Texto(5) HH:mm — tambem DURACAO. Mesma razao de "ValorDescanso" para manter TEXT. |
| `IncluirFeriado` | smallint | sim |  |  | Enum bruto (DescansoDomingo=0, DescansoDia=1, HoraNormalDia=2, HoraNormalDescanso=3), sem CHECK. |
| `FeriadoDomingoApenasUmDescanso` | boolean | sim |  |  |  |
| `DescontarFeriadosCasoFaltas` | boolean | sim |  |  |  |
| `NaoDescontarAntesAdmissao` | boolean | sim |  |  |  |
| `NaoDescontarDuranteAfastamento` | boolean | sim |  |  |  |
| `sincronizado_em` | timestamp with time zone | não | `now()` |  |  |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horariodescanso_tenant_idx` — `secullum."HorarioDescanso" USING btree (tenant_id)`
- `UNIQUE horario_descanso_horario_id_key` — `secullum."HorarioDescanso" USING btree (horario_id)`

</details>


## `secullum.HorarioDescansoFaixaItem`

> Itens de `Descanso.Faixas` (tipo `HorarioDescansoFaixaItem`: { Ordem, Limite, Desconto }). SEM chave unica de negocio de proposito: escrita por SUBSTITUICAO INTEGRAL do conjunto por "HorarioDescanso", dentro da transacao do ciclo. Nenhum item tem id estavel na origem.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `horario_descanso_id` | uuid | não |  | `secullum.HorarioDescanso` |  |
| `Ordem` | integer | sim |  |  |  |
| `Limite` | text | sim |  |  | Texto(5) HH:mm (DURACAO). Mantido TEXT — mesma razao de "HorarioDescanso"."ValorDescanso". |
| `Desconto` | text | sim |  |  |  |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horario_descanso_faixa_item_pai_idx` — `secullum."HorarioDescansoFaixaItem" USING btree (horario_descanso_id)`
- `horariodescansofaixaitem_tenant_idx` — `secullum."HorarioDescansoFaixaItem" USING btree (tenant_id)`

</details>


## `secullum.HorarioDia`

> Grade por dia da semana. Um registro por item de `Horario.Dias[]`. Nome COMPOSTO por nos (`Horario` + `Dia`): o manual do Secullum nao nomeia um tipo para o item do array.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `horario_id` | uuid | não |  | `secullum.Horario` |  |
| `HorarioDiaId` | integer | não |  |  | Campo `Dias[].Id`. ATRIBUTO de diagnostico (indice nao-unico) — NAO e chave de idempotencia: confirmado em producao que se repete entre Horarios diferentes (migration 20260812140000). A chave real e (horario_id, "DiaSemana"). |
| `DiaSemana` | smallint | não |  |  | Campo `DiaSemana`: 0=Segunda .. 6=Domingo. ⛔ NUNCA usar EXTRACT(DOW) (0=Domingo) ao comparar com uma data — usar EXTRACT(ISODOW)-1. ⚠️ NAO confundir com "HorarioFaixasExtras"."DiaSemana", que e um enum COMPLETAMENTE diferente (Uteis=0, Sabado=1, ... IntervaloFolgas=15). |
| `Entrada1` | time without time zone | sim |  |  |  |
| `Entrada2` | time without time zone | sim |  |  |  |
| `Entrada3` | time without time zone | sim |  |  |  |
| `Entrada4` | time without time zone | sim |  |  |  |
| `Entrada5` | time without time zone | sim |  |  |  |
| `Saida1` | time without time zone | sim |  |  |  |
| `Saida2` | time without time zone | sim |  |  |  |
| `Saida3` | time without time zone | sim |  |  |  |
| `Saida4` | time without time zone | sim |  |  |  |
| `Saida5` | time without time zone | sim |  |  |  |
| `TipoEntrada1` | smallint | sim |  |  | TipoEntradaN bruto (smallint, sem CHECK/enum — enum nao documentado pelo Secullum). |
| `TipoEntrada2` | smallint | sim |  |  |  |
| `TipoEntrada3` | smallint | sim |  |  |  |
| `TipoEntrada4` | smallint | sim |  |  |  |
| `TipoEntrada5` | smallint | sim |  |  |  |
| `TipoSaida1` | smallint | sim |  |  |  |
| `TipoSaida2` | smallint | sim |  |  |  |
| `TipoSaida3` | smallint | sim |  |  |  |
| `TipoSaida4` | smallint | sim |  |  |  |
| `TipoSaida5` | smallint | sim |  |  |  |
| `ToleranciaExtra` | integer | sim |  |  | Campo `ToleranciaExtra`, EM MINUTOS (a unidade nao esta no nome porque o nome e literal do Secullum). ⛔ Junto com "ToleranciaFalta", e a UNICA tolerancia que o motor de deteccao pode aplicar — nunca uma tolerancia propria, sob pena de divergir do calculo oficial de folha. |
| `ToleranciaFalta` | integer | sim |  |  | Campo `ToleranciaFalta`, EM MINUTOS. ⚠️ ARMADILHA CONFIRMADA: dia de folga vem com "ToleranciaExtra"/"ToleranciaFalta" PREENCHIDOS. Presenca de tolerancia NAO significa que ha expediente. |
| `Carga` | integer | sim |  |  | Campo `Carga`, EM MINUTOS de carga do dia. Discriminador de dia sem expediente (junto com os 10 pares nulos). ⚠️ NAO confundir com "HorariosOpcoes"."Carga", que e a carga configurada no nivel do HORARIO. |
| `TipoDia` | smallint | sim |  |  |  |
| `Neutro` | boolean | não | `false` |  |  |
| `Compensado` | boolean | não | `false` |  |  |
| `AlmocoLivre` | boolean | não | `false` |  |  |
| `Alocar24Horas` | boolean | não | `false` |  |  |
| `sem_expediente` | boolean | não | `false` |  | DERIVADO POR NOS — por isso minusculo, e NAO um campo que o Secullum manda. true quando "Carga" = 0 E os 10 pares Entrada/Saida sao nulos. Nome escolhido para nao colidir com `Batida.Folga` nem com `TipoDia = Folga(2)`, que sao tres coisas distintas. |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Restrições**

- `CHECK ((("DiaSemana" >= 0) AND ("DiaSemana" <= 6)))`

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horario_dia_horariodiaid_idx` — `secullum."HorarioDia" USING btree ("HorarioDiaId")`
- `horariodia_tenant_idx` — `secullum."HorarioDia" USING btree (tenant_id)`
- `UNIQUE horario_dia_horario_id_diasemana_key` — `secullum."HorarioDia" USING btree (horario_id, "DiaSemana")`

</details>


## `secullum.HorarioExtras`

> No `Horario.Extras` (tipo `HorarioExtras`). 1:1 com "Horario". ✅ ESTRUTURA FECHADA em 2026-08-13 contra a conta real: 31 campos incluindo "HorarioId" — nao 7 (manual) nem ~15 (estimativa). Regras de folha, capturadas mas ⛔ NAO usadas pelo motor de deteccao. Ver ADR-011.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `horario_id` | uuid | não |  | `secullum.Horario` |  |
| `HorarioId` | integer | sim |  |  |  |
| `AgruparExtras` | boolean | sim |  |  |  |
| `SomenteGrupoExtras` | boolean | sim |  |  |  |
| `DescontarFaltasExtras` | smallint | sim |  |  | Enum BRUTO (MaisSignificativas=0, MenosSignificativas=1), smallint SEM CHECK — mesma disciplina de "HorarioDia"."TipoEntrada1" e de "BatidaFonteDados"."Origem". |
| `DescontarFaltasExtrasNoturnas` | boolean | sim |  |  |  |
| `DescontarIgnorarUteis` | boolean | sim |  |  |  |
| `DescontarIgnorarSabados` | boolean | sim |  |  |  |
| `DescontarIgnorarDomingos` | boolean | sim |  |  |  |
| `DescontarIgnorarFeriados` | boolean | sim |  |  |  |
| `DescontarIgnorarFolgas` | boolean | sim |  |  |  |
| `DescontarIgnorarDiaEspecial` | boolean | sim |  |  | "Dia especial" aqui e o mesmo conceito de "HorarioFaixasExtras"."DiaEspecial" (Domingo=0..Sabado=6) — ⚠️ TERCEIRA convencao de dia da semana do schema, diferente de "HorarioDia"."DiaSemana". |
| `UsarInterjornada` | boolean | sim |  |  | Booleano que liga o uso de "Interjornada". ⚠️ O manual repete, por erro de copia, descricoes de HorariosOpcoes em UsarInterjornada/Interjornada/InterjornadaSeparada. O NOME do campo e o contrato; a descricao do PDF nao e confiavel neste bloco. |
| `Interjornada` | text | sim |  |  | ⚠️⚠️ DIVERGENCIA CONFIRMADA DA DOCUMENTACAO OFICIAL. O manual declara `Interjornada` como Booleano, com uma descricao que nem sequer e deste campo ("marcar qualquer minuto adiantado como extra", copiada de HorariosOpcoes). O valor REAL observado na conta do cliente em 2026-08-13 e uma STRING — provavelmente o intervalo minimo entre jornadas em "HH:mm". ⛔ NAO "corrigir" para boolean com base no PDF: o payload e o contrato. Mantido TEXT (nao `time`): e DURACAO, nao horario do dia. |
| `InterjornadaSeparada` | boolean | sim |  |  |  |
| `InterjornadaSeparadaBancoHoras` | boolean | sim |  |  |  |
| `SepararExtrasNoturnasDeExtrasNormais` | boolean | sim |  |  |  |
| `SepararExtrasIntervalosDeExtrasNormais` | boolean | sim |  |  |  |
| `SepararSomatoriaAposMeiaNoite` | boolean | sim |  |  |  |
| `MultiplicarExtrasPeloPercentual` | boolean | sim |  |  |  |
| `HabilitarMultiplicadorFaixaBancoHoras` | boolean | sim |  |  |  |
| `MultiplicarSomenteSaldoPositivo` | boolean | sim |  |  |  |
| `NaoDividirExtrasEmFeriados` | boolean | sim |  |  |  |
| `NaoDividirExtrasEmDomingos` | boolean | sim |  |  |  |
| `DividirJornadaQuandoHouverFolga` | boolean | sim |  |  |  |
| `NaoDividirJornadaEmFeriados` | boolean | sim |  |  |  |
| `NaoDividirJornadaEmFolgas` | boolean | sim |  |  |  |
| `ApenasDividirJornadaFeriadoFolgaDiaSeguinte` | boolean | sim |  |  |  |
| `NaoReiniciarDivisoesExtrasDiurnasNoturnas` | boolean | sim |  |  |  |
| `ControleHorasExtrasAutorizadas` | boolean | sim |  |  | ⚠️ Regra de FOLHA: limita quanto de hora extra o Secullum considera autorizado. ⛔ O motor de deteccao NAO filtra desvio por esta regra — o relatorio consolidado reporta desvio de HORARIO, nao saldo autorizado de folha. Confundir os dois faz o relatorio deixar de mostrar exatamente o excesso que o gestor precisa ver. |
| `QuantidadeExtrasAutorizadas` | text | sim |  |  | Texto "HH:mm" conforme o manual — e DURACAO, nao horario do dia. Mantido TEXT de proposito: o tipo `time` do Postgres nao representa duracao acima de 24h e induziria comparacao errada. |
| `Acumulo` | smallint | sim |  |  | Enum BRUTO 0..8 (Independentes=0 ... UteisDomingo_e_SabadoFeriado=8), smallint SEM CHECK. |
| `sincronizado_em` | timestamp with time zone | não | `now()` |  |  |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horarioextras_tenant_idx` — `secullum."HorarioExtras" USING btree (tenant_id)`
- `UNIQUE horario_extras_horario_id_key` — `secullum."HorarioExtras" USING btree (horario_id)`

</details>


## `secullum.HorarioFaixasExtras`

> No `Horario.FaixasExtras` (tipo `HorarioFaixasExtras`) — 1:N por horario, uma linha por "Dia Semana" do enum. Escrita por substituicao integral. Regras de folha: capturadas, ⛔ NAO consumidas pelo motor.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `horario_id` | uuid | não |  | `secullum.Horario` |  |
| `HorarioId` | integer | sim |  |  |  |
| `DiaSemana` | smallint | sim |  |  | ⚠️⚠️ ENUM COMPLETAMENTE DIFERENTE de "HorarioDia"."DiaSemana", apesar do nome identico (os dois nomes sao literais do Secullum). Aqui: Uteis=0, Sabado=1, Domingo=2, Feriado=3, Folgas=4, Especial=5, NoturnoUteis=6, NoturnoSabado=7, NoturnoDomingo=8, NoturnoFeriado=9, NoturnoFolgas=10, IntervaloUteis=11, IntervaloSabado=12, IntervaloDomingo=13, IntervaloFeriado=14, IntervaloFolgas=15. Em "HorarioDia", "DiaSemana" e 0=Segunda..6=Domingo. Confundir os dois produz erro SILENCIOSO. smallint BRUTO, sem CHECK. |
| `Controle` | smallint | sim |  |  | Enum bruto (Diario=0, Semanal=1, Mensal=2), sem CHECK. |
| `DiaEspecial` | smallint | sim |  |  | De Domingo(0) a Sabado(6) — ⚠️ TERCEIRA convencao de dia da semana neste schema, diferente das outras duas. Valor bruto do Secullum, sem conversao. |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horario_faixas_extras_horario_id_idx` — `secullum."HorarioFaixasExtras" USING btree (horario_id)`
- `horariofaixasextras_tenant_idx` — `secullum."HorarioFaixasExtras" USING btree (tenant_id)`

</details>


## `secullum.HorarioFaixasExtrasItem`

> Itens de `FaixasExtras.Faixas` (tipo `HorarioFaixasExtrasItem`). Escrita por substituicao integral junto com o pai. Sem chave unica de negocio — nenhum id estavel na origem.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `horario_faixas_extras_id` | uuid | não |  | `secullum.HorarioFaixasExtras` |  |
| `Ordem` | integer | sim |  |  |  |
| `Horas` | double precision | sim |  |  |  |
| `Coluna` | double precision | sim |  |  | Coluna de extra correspondente. Tipo `Duplo` no manual mesmo parecendo indice inteiro — preservamos `double precision` para nao perder valor fracionario nem falhar na conversao. |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horario_faixas_extras_item_pai_idx` — `secullum."HorarioFaixasExtrasItem" USING btree (horario_faixas_extras_id)`
- `horariofaixasextrasitem_tenant_idx` — `secullum."HorarioFaixasExtrasItem" USING btree (tenant_id)`

</details>


## `secullum.HorarioToleranciaEspecifica`

> No `Horario.ToleranciaEspecifica` (SINGULAR, confirmado no payload real; tipo `HorarioToleranciaEspecifica` no manual) — 1:1 com "Horario". Em todos os registros ja inspecionados veio false / lista vazia: nao ha nenhum caso real ativo neste cliente.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `horario_id` | uuid | não |  | `secullum.Horario` |  |
| `UsaToleranciaEspecifica` | boolean | não | `false` |  | Quando true, o motor de deteccao LOGA AVISO e aplica a tolerancia padrao do dia — nunca silencia. A tolerancia especifica e expressa como FAIXA (De/Ate), nao como minutos, e por isso nao e aproximavel pela tolerancia padrao. |
| `sincronizado_em` | timestamp with time zone | não | `now()` |  |  |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horariotoleranciaespecifica_tenant_idx` — `secullum."HorarioToleranciaEspecifica" USING btree (tenant_id)`
- `UNIQUE horario_tolerancia_especifica_horario_id_key` — `secullum."HorarioToleranciaEspecifica" USING btree (horario_id)`

</details>


## `secullum.HorarioToleranciaEspecificaItem`

> Itens de `ToleranciaEspecifica.Tolerancias` (tipo `HorarioToleranciaEspecificaItem`). Escrita por substituicao integral junto com o pai.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `horario_tolerancia_especifica_id` | uuid | não |  | `secullum.HorarioToleranciaEspecifica` |  |
| `HorarioId` | integer | sim |  |  |  |
| `DiaSemana` | smallint | sim |  |  | ⚠️ O manual (pag. 18) declara DiaSemana como "Booleano" com a descricao "Usa tolerancia especifica" — sao dois erros evidentes de copia na tabela oficial. Modelado como smallint (dia da semana), coerente com o payload real. [VALIDAR — Postman] se algum dia houver caso real ativo neste cliente. |
| `Entrada1De` | time without time zone | sim |  |  |  |
| `Entrada1Ate` | time without time zone | sim |  |  |  |
| `Saida1De` | time without time zone | sim |  |  |  |
| `Saida1Ate` | time without time zone | sim |  |  |  |
| `Entrada2De` | time without time zone | sim |  |  |  |
| `Entrada2Ate` | time without time zone | sim |  |  |  |
| `Saida2De` | time without time zone | sim |  |  |  |
| `Saida2Ate` | time without time zone | sim |  |  |  |
| `Entrada3De` | time without time zone | sim |  |  |  |
| `Entrada3Ate` | time without time zone | sim |  |  |  |
| `Saida3De` | time without time zone | sim |  |  |  |
| `Saida3Ate` | time without time zone | sim |  |  |  |
| `Entrada4De` | time without time zone | sim |  |  |  |
| `Entrada4Ate` | time without time zone | sim |  |  |  |
| `Saida4De` | time without time zone | sim |  |  |  |
| `Saida4Ate` | time without time zone | sim |  |  |  |
| `Entrada5De` | time without time zone | sim |  |  |  |
| `Entrada5Ate` | time without time zone | sim |  |  |  |
| `Saida5De` | time without time zone | sim |  |  |  |
| `Saida5Ate` | time without time zone | sim |  |  |  |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horario_tolerancia_especifica_item_pai_idx` — `secullum."HorarioToleranciaEspecificaItem" USING btree (horario_tolerancia_especifica_id)`
- `horariotoleranciaespecificaitem_tenant_idx` — `secullum."HorarioToleranciaEspecificaItem" USING btree (tenant_id)`

</details>


## `secullum.HorariosOpcoes`

> No `Horario.Opcoes` (tipo `HorariosOpcoes` no manual — plural no `Horarios` e literal, nao erro). 1:1 com "Horario". ✅ ESTRUTURA FECHADA em 2026-08-13 contra a conta real (inspecao GET-only, so nomes de campo e tipo, zero valores): 54 campos incluindo "HorarioId" — nao 21 (manual) nem ~35 (estimativa). REGRAS DE CALCULO DE FOLHA: capturadas para consulta/auditoria, ⛔ NAO consumidas pelo motor de deteccao. Ver ADR-011.

*tabela — RLS ligada*

| Coluna | Tipo | Nulo | Default | Referência | Nota |
|---|---|---|---|---|---|
| `id` 🔑 | uuid | não | `gen_random_uuid()` |  |  |
| `horario_id` | uuid | não |  | `secullum.Horario` |  |
| `HorarioId` | integer | sim |  |  | Campo `HorarioId` do proprio no (inteiro do Secullum). A FK usada e horario_id (uuid). |
| `ToleranciaArtigo58` | boolean | sim |  |  |  |
| `IgnorarLimiteMinimoCasoBatidaGerarExtrasSuperiorATolerancia` | boolean | sim |  |  |  |
| `IgnorarLimiteMinimoCasoBatidaGerarFaltasSuperiorATolerancia` | boolean | sim |  |  |  |
| `QualquerMinutoAdiantadoComoExtra` | boolean | sim |  |  |  |
| `QualquerMinutoAtrasadoComoFalta` | boolean | sim |  |  |  |
| `DescontarToleranciaDasHorasExtras` | boolean | sim |  |  |  |
| `DescontarToleranciaDasHorasFaltas` | boolean | sim |  |  |  |
| `UsarToleranciaRefeicoes` | boolean | sim |  |  |  |
| `ToleranciaRefeicoesMinutos` | integer | sim |  |  | ⚠️ Tolerancia de REFEICAO — nao confundir com "HorarioDia"."ToleranciaExtra"/"ToleranciaFalta", que sao as unicas que o motor pode usar. |
| `LimiteMinimoDeFaltasNoDiaMinutos` | integer | sim |  |  | ⚠️ O manual oficial (pag. 11) descreve este campo como "Limite minimo de EXTRAS no dia" e o de extras como "de FALTAS" — as descricoes estao TROCADAS no PDF. Preservamos o NOME do campo, que e o contrato real; ⛔ nao inverter para "corrigir". |
| `LimiteMinimoDeExtrasNoDiaMinutos` | integer | sim |  |  |  |
| `SubstituirBatidasAbaixoDasTolerancias` | boolean | sim |  |  | ⚠️ Regra de folha que substitui a batida pelo horario previsto quando a diferenca cabe na tolerancia. ⛔ O motor NAO aplica isso — ele compara a hora crua de batida_marcacao.hora com o previsto de "HorarioDia". Ativar essa regra aqui mudaria o numero do relatorio sem mudar o do Secullum. |
| `AlocarHorario24Horas` | boolean | sim |  |  | Nivel HORARIO. ⚠️ Existe tambem "HorarioDia"."Alocar24Horas", nivel DIA. Sao dois campos distintos do Secullum; o relevante para jornada que cruza a meia-noite e o do dia. |
| `AlocarBatidas` | integer | sim |  |  | Numero no payload real; semantica/enum NAO documentados. INTEIRO BRUTO, sem CHECK — mesma disciplina de "HorarioDia"."TipoEntrada1" e de "BatidaFonteDados"."Origem". `integer` (e nao `smallint`) de proposito: sem faixa conhecida, o tipo mais largo evita derrubar a transacao inteira do ciclo por causa de um campo que nenhum consumidor le. |
| `NaoDescontarFaltasDeNormais` | boolean | sim |  |  |  |
| `PreencherFaltasQuandoDiaEstiverEmBranco` | boolean | sim |  |  |  |
| `TipoPreencherQuandoDiaEstiverEmBranco` | integer | sim |  |  | Enum bruto, sem CHECK. Acompanha "PreencherFaltasQuandoDiaEstiverEmBranco". `integer` pelo mesmo motivo de "AlocarBatidas": faixa desconhecida. |
| `CalcularFaltasSomenteParaDiaInteiro` | boolean | sim |  |  |  |
| `ExibirColunaHorasRepousoFaltantesTrabalhoContinuo` | boolean | sim |  |  |  |
| `HorasRepousoConfiguracaoPadrao` | boolean | sim |  |  |  |
| `HorasRepousoFaixas` | jsonb | sim |  |  | ⏳ SHAPE NAO CONFIRMADO. Veio `null` no registro real — nao ha um unico exemplo populado. jsonb BRUTO de proposito: modelar tabela filha exigiria INVENTAR as colunas do item, e este projeto ja quebrou duas vezes em producao por supor estrutura do Secullum sem evidencia. Hipotese NAO confirmada (nao implementar): mesma forma de "HorarioDescansoFaixaItem" { Ordem, Limite, Desconto }. Quando aparecer exemplo populado, promover a tabela filha por migration corretiva. Sem PII: e parametro de horario. |
| `CompletarBatidasFaltantes` | boolean | sim |  |  | ⚠️ Opcao de FOLHA do Secullum que preenche batida ausente no calculo dele. ⛔ Isso NAO afeta o que /Batidas devolve a este sistema nem autoriza o motor a "completar" nada: batida faltante continua sendo detectada por slot com "Memoria" e sem hora. |
| `PermitirFolgasAutomaticas` | boolean | sim |  |  |  |
| `QuantidadeFolgasAutomaticas` | integer | sim |  |  |  |
| `ColunasRefeicao` | integer | sim |  |  |  |
| `SinalizarEmVermelhoAlmocosCurtos` | boolean | sim |  |  |  |
| `NaoCalcularNenhumaHoraNoturna` | boolean | sim |  |  |  |
| `SepararHorasNoturnasDeHorasNormais` | boolean | sim |  |  |  |
| `IncluirIntervaloNoAdicionalNoturno` | boolean | sim |  |  |  |
| `PeriodoEspecialAdicionalNoturnoInicio` | text | sim |  |  | Texto(5) "HH:mm". Mantido TEXT (nao `time`): e configuracao de folha, nunca comparada com hora de batida por este sistema, e converter introduziria risco de fuso sem nenhum ganho. |
| `PeriodoEspecialAdicionalNoturnoFim` | text | sim |  |  |  |
| `ConsiderarFeriadosComoHoraExtra` | boolean | sim |  |  |  |
| `UsarTempoMaisMenosCargaSuperior` | boolean | sim |  |  |  |
| `PercentualCargaUsarTempoMaisMenosMinutos` | double precision | sim |  |  |  |
| `DefinirCargaAutomaticamente` | boolean | sim |  |  |  |
| `Carga` | double precision | sim |  |  | Carga configurada no nivel do HORARIO (acompanha "DefinirCargaAutomaticamente"). ⚠️ NAO confundir com "HorarioDia"."Carga", que e a carga do DIA em minutos e e a unica que interessa a "ha expediente?". Unidade deste campo (minutos vs. horas) nao confirmada; `double precision` para nao truncar valor fracionario nem falhar na conversao. |
| `DesconsiderarNeutroQuandoHouverBatidasNoDia` | boolean | sim |  |  |  |
| `UsarDataFechamentoEncerrarSemana` | boolean | sim |  |  |  |
| `Compensacao` | smallint | sim |  |  | ⏳ Veio `null` no registro real — TIPO NAO OBSERVADO. Modelado como smallint nullable (enum de modo de compensacao) porque a familia de irmaos booleanos "CompensacaoIgnorar*" implica fortemente um enum de modo. Bruto, sem CHECK. |
| `CompensacaoIgnorarSabados` | boolean | sim |  |  |  |
| `CompensacaoIgnorarDomingos` | boolean | sim |  |  |  |
| `CompensacaoIgnorarFeriados` | boolean | sim |  |  |  |
| `CompensacaoIgnorarFolgas` | boolean | sim |  |  |  |
| `CompensacaoMensalFechamento` | jsonb | sim |  |  | ⏳ Veio `null` no registro real e, ao contrario de "Compensacao", NAO tem contexto que permita inferir o tipo (dia do mes? data? objeto?). jsonb bruto de proposito: `text` transformaria um eventual objeto em "[object Object]" e `smallint` derrubaria a transacao se vier string. Estreitar quando houver exemplo. |
| `CompensacaoCalcularHorasComoNormaisCompatibilidadePontoOff` | boolean | sim |  |  |  |
| `CalcularNoturnasIndependenteCompensado` | boolean | sim |  |  |  |
| `CalcularBatidasIntermediarias` | boolean | sim |  |  |  |
| `NaoCalcularHorasFaltaBatidasIntermediarias` | boolean | sim |  |  |  |
| `ListaHorasSobreAviso` | jsonb | sim |  |  | ⏳ SHAPE NAO CONFIRMADO. Veio `[]` no registro real — a lista existe, o item nunca foi observado. jsonb bruto pelo mesmo racional de "HorasRepousoFaixas". Nao inventar colunas. |
| `CalcularHorasInItinere` | boolean | sim |  |  |  |
| `ListaHorasInItinere` | jsonb | sim |  |  | ⏳ SHAPE NAO CONFIRMADO. Veio `[]` no registro real. jsonb bruto, mesmo racional. |
| `SomarHorasInItinereNormais` | boolean | sim |  |  |  |
| `CalcularHorasInItinereIninterruptas` | boolean | sim |  |  |  |
| `sincronizado_em` | timestamp with time zone | não | `now()` |  |  |
| `criado_em` | timestamp with time zone | não | `now()` |  |  |
| `atualizado_em` | timestamp with time zone | não | `now()` |  |  |
| `tenant_id` | uuid | não | `'<tenant fastpark>'::uuid` | `app.tenant` |  |

**Sem policy** — nenhuma linha passa para `authenticated`. Só `service_role`. Intencional.

<details><summary>Índices</summary>

- `horariosopcoes_tenant_idx` — `secullum."HorariosOpcoes" USING btree (tenant_id)`
- `UNIQUE horarios_opcoes_horario_id_key` — `secullum."HorariosOpcoes" USING btree (horario_id)`

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
public.fn_data_freshness(p_stale_after_minutes integer DEFAULT NULL::integer)
  returns TABLE(tenant_id uuid, entity text, last_sync_at timestamp with time zone, age_minutes integer, is_stale boolean)
```

Idade do dado por entidade sincronizada, e o deadman da ingestão. Sem argumento, o limiar é 1,5x a cadência da entidade — 25 min para Batida (cadência 15), 2160 para Foto (cadência diária) e 45 para as demais (cadência 30) — de modo que uma execução perdida não alarma e duas seguidas alarmam. Com argumento, ele vale para todas. Ver docs/DECISAO-CADENCIA-SYNC.md.


### `fn_detection_health`

```sql
public.fn_detection_health(p_backfill_max_age_hours integer DEFAULT 26)
  returns TABLE(tenant_id uuid, last_incremental_at timestamp with time zone, incremental_age_minutes integer, last_backfill_at timestamp with time zone, backfill_age_hours integer, backfill_overdue boolean)
```

Backfill overdue is true when it has not completed in p_backfill_max_age_hours OR has never run. Never-ran must read as overdue, not as null.


### `fn_kpi_period`

```sql
public.fn_kpi_period(p_de date, p_ate date, p_company_id uuid DEFAULT NULL::uuid, p_unit_id uuid DEFAULT NULL::uuid, p_department_id uuid DEFAULT NULL::uuid, p_manager_id uuid DEFAULT NULL::uuid)
  returns TABLE(eventos bigint, colaboradores_afetados bigint, minutes_excedente bigint, minutes_faltante bigint, minutes_abs bigint, unidades_afetadas bigint, eventos_pendentes_ciclo bigint)
```

### `fn_pending_justification`

```sql
public.fn_pending_justification(p_de date, p_ate date, p_unit_id uuid DEFAULT NULL::uuid, p_department_id uuid DEFAULT NULL::uuid, p_manager_id uuid DEFAULT NULL::uuid)
  returns TABLE(deviation_event_id uuid, employee_id uuid, employee_name text, unit_id uuid, unit_name text, reference_date date, type text, type_description text, minutes integer, detected_at timestamp with time zone)
```

Desvio ativo, de tipo que exige justificativa, sem nenhuma justificativa aceita. Devolve a existência da pendência, nunca o texto de justificativa nenhuma.


### `fn_ranking_by_employee`

```sql
public.fn_ranking_by_employee(p_de date, p_ate date, p_company_id uuid DEFAULT NULL::uuid, p_unit_id uuid DEFAULT NULL::uuid, p_limite integer DEFAULT 20, p_department_id uuid DEFAULT NULL::uuid, p_manager_id uuid DEFAULT NULL::uuid)
  returns TABLE(employee_id uuid, employee_name text, unit_name text, eventos bigint, minutes_abs bigint)
```

### `fn_ranking_by_manager`

```sql
public.fn_ranking_by_manager(p_de date, p_ate date, p_company_id uuid DEFAULT NULL::uuid, p_unit_id uuid DEFAULT NULL::uuid, p_limite integer DEFAULT 20, p_department_id uuid DEFAULT NULL::uuid)
  returns TABLE(manager_id uuid, manager_name text, eventos bigint, minutes_abs bigint, colaboradores bigint, unidades bigint)
```

### `fn_ranking_by_unit`

```sql
public.fn_ranking_by_unit(p_de date, p_ate date, p_company_id uuid DEFAULT NULL::uuid, p_limite integer DEFAULT 20, p_department_id uuid DEFAULT NULL::uuid, p_manager_id uuid DEFAULT NULL::uuid)
  returns TABLE(unit_id uuid, unit_name text, eventos bigint, minutes_abs bigint, colaboradores bigint)
```

### `fn_recurrence`

```sql
public.fn_recurrence(p_de date, p_ate date, p_min_dias integer DEFAULT 3, p_unit_id uuid DEFAULT NULL::uuid, p_department_id uuid DEFAULT NULL::uuid, p_manager_id uuid DEFAULT NULL::uuid)
  returns TABLE(employee_id uuid, employee_name text, unit_name text, dias_com_desvio bigint, eventos bigint)
```

### `fn_whatsapp_readiness`

```sql
public.fn_whatsapp_readiness()
  returns TABLE(tenant_id uuid, provider text, official boolean, templates_total integer, templates_approved integer, rules_blocked integer, ready boolean)
```

ready = false quando o tenant está no provedor oficial e existe regra ligada apontando para template não aprovado. Nesse estado o alerta falha calado.


## Helpers de RLS (`util`)

Não são API. `security definer` com `search_path` travado, `EXECUTE` revogado de `anon`.

| Função | Assinatura | Retorno |
|---|---|---|
| `util.block_table_in_public` | `` | `event_trigger` |
| `util.can_see_company` | `p_company_id uuid` | `boolean` |
| `util.can_see_domain` | `p_tenant_id uuid, p_domain app.sensitive_domain` | `boolean` |
| `util.can_see_employee` | `p_employee_id uuid` | `boolean` |
| `util.can_see_unit` | `p_unit_id uuid` | `boolean` |
| `util.enforce_benefit_cycle_immutable` | `` | `trigger` |
| `util.enforce_benefit_entitlement_immutable` | `` | `trigger` |
| `util.enforce_single_open_base_benefit` | `` | `trigger` |
| `util.has_tenant` | `p_tenant_id uuid` | `boolean` |
| `util.is_admin` | `p_tenant_id uuid` | `boolean` |
| `util.lock_down_new_function` | `` | `event_trigger` |
| `util.roles_in_tenant` | `p_tenant_id uuid` | `app.user_role[]` |
| `util.touch_atualizado_em` | `` | `trigger` |
| `util.touch_updated_at` | `` | `trigger` |
| `util.user_tenants` | `` | `uuid[]` |
| `util.validate_alert_payload` | `` | `trigger` |
| `util.validate_alert_target` | `` | `trigger` |
| `util.validate_alert_template` | `` | `trigger` |
| `util.validate_template_body` | `` | `trigger` |


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

