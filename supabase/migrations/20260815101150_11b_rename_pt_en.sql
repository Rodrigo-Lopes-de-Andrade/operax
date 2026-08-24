-- ============================================================================
-- OperaX — 11b. RENAME pt→en DO PROJETO NA NUVEM
-- ----------------------------------------------------------------------------
-- Alinha um banco que rodou as migrations 00–11 na grafia em PORTUGUÊS com o
-- que este repositório define em inglês. É o caso do projeto de produção
-- (Kastro Park Ponto), que parou na migration 11 e cujo histórico guarda a
-- versão pt dos mesmos doze arquivos que aqui estão em en.
--
-- POR QUE O TIMESTAMP CAI ENTRE A 11 E A 12
-- As migrations 12 a 15 referenciam nomes em inglês. Se o rename rodasse depois
-- delas, a 12 encontraria `app.jornada_dia` e criaria uma segunda tabela ao
-- lado — que é exatamente o desfecho que esta migration existe para evitar.
--
-- NUM BANCO QUE JÁ ESTÁ EM INGLÊS ESTA MIGRATION NÃO FAZ NADA. Todo rename é
-- guardado por "o nome velho existe E o novo não". É o que mantém `make db-test`
-- verde: no banco local as migrations 00–11 já criaram tudo em inglês.
--
-- SE OS DOIS NOMES EXISTIREM, ELA PARA. Coexistência de `app.colaborador` e
-- `app.employee` significa que alguém já rodou metade da fusão, e seguir em
-- frente duplicaria o modelo em silêncio.
--
-- O QUE ELA NÃO TOCA, DE PROPÓSITO
--   • `secullum.*` — espelho literal da origem, PascalCase por convenção.
--   • As quatro tabelas da ingestão: app.batida_marcacao, app.cursor_sincronizacao,
--     app.empresa_evento_status e app.funcionario_evento_status. Elas nascem das
--     onze migrations anteriores a este repositório, as Edge Functions escrevem
--     nelas por nome literal em string JS, e não existe um único teste em
--     `supabase/functions/`. Renomeá-las exige alterar as funções no mesmo
--     instante, sem rede. Congelar é reversível; quebrar a sincronização não é.
--     A decisão é do dono — ver docs/PLANO-RECONCILIACAO-NUVEM.md §5.
--   • public.rls_auto_enable() — existe na nuvem e em nenhuma migration daqui.
--     É event trigger que liga RLS em tabela criada em `public`; complementa o
--     util.block_table_in_public() deste repositório, que é mais estrito.
--
-- GERADO por scripts/gerar_rename_nuvem.py confrontando o catálogo real dos dois
-- lados. Nenhum par foi digitado à mão.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 0. Guarda de coexistência
-- Antes de qualquer rename: se algum par (velho, novo) já estiver dos dois
-- lados, esta migration não sabe qual é o certo e não tem o direito de
-- escolher.
-- ---------------------------------------------------------------------------
do $$
declare
  r record;
  v_colisao text[] := '{}';
begin
  for r in
    select * from (values
  ('app', 'acordo_financeiro', 'financial_agreement'),
  ('app', 'acordo_parcela', 'agreement_installment'),
  ('app', 'afastamento', 'leave_period'),
  ('app', 'alerta_enviado', 'alert_sent'),
  ('app', 'alerta_fila', 'alert_queue'),
  ('app', 'centro_custo', 'cost_center'),
  ('app', 'ciclo_relatorio', 'report_cycle'),
  ('app', 'colaborador', 'employee'),
  ('app', 'colaborador_funcao', 'employee_position'),
  ('app', 'colaborador_pii', 'employee_pii'),
  ('app', 'colaborador_remuneracao', 'employee_compensation'),
  ('app', 'competencia', 'payroll_period'),
  ('app', 'consulta_ia', 'ai_query'),
  ('app', 'contato', 'contact'),
  ('app', 'departamento', 'department'),
  ('app', 'desvio_tipo', 'deviation_type'),
  ('app', 'desvio_tipo_config', 'deviation_type_config'),
  ('app', 'deteccao_execucao', 'detection_run'),
  ('app', 'documento', 'document'),
  ('app', 'documento_tipo', 'document_type'),
  ('app', 'empresa', 'company'),
  ('app', 'encargo', 'payroll_charge'),
  ('app', 'escopo_usuario', 'user_scope'),
  ('app', 'exame_ocupacional', 'occupational_exam'),
  ('app', 'folha_evento', 'payroll_entry'),
  ('app', 'importacao_arquivo', 'file_import'),
  ('app', 'integracao', 'integration'),
  ('app', 'integracao_segredo', 'integration_secret'),
  ('app', 'jornada_dia', 'expected_workday'),
  ('app', 'justificativa', 'justification'),
  ('app', 'limiar_financeiro', 'financial_threshold'),
  ('app', 'metrica', 'metric'),
  ('app', 'movimentacao_pessoal', 'workforce_movement'),
  ('app', 'permissao_dominio', 'domain_permission'),
  ('app', 'regra_alerta', 'alert_rule'),
  ('app', 'regra_alerta_destino', 'alert_rule_target'),
  ('app', 'sync_execucao', 'sync_run'),
  ('app', 'tenant_membro', 'tenant_member'),
  ('app', 'unidade', 'unit'),
  ('app', 'unidade_mapa_secullum', 'unit_secullum_map'),
  ('app', 'unidade_responsavel', 'unit_responsible')
) as t(sch, velho, novo)
  loop
    if to_regclass(format('%I.%I', r.sch, r.velho)) is not null
       and to_regclass(format('%I.%I', r.sch, r.novo)) is not null then
      v_colisao := v_colisao || format('%s.%s ↔ %s.%s', r.sch, r.velho, r.sch, r.novo);
    end if;
  end loop;
  if array_length(v_colisao, 1) > 0 then
    raise exception 'fusão pela metade: % par(es) coexistindo — %',
      array_length(v_colisao, 1), array_to_string(v_colisao, '; ')
      using hint = 'Alguém já rodou parte do rename. Resolver à mão antes de seguir.';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 1. Tipos e rótulos de enum
-- Os rótulos vêm antes do rename do tipo: `alter type ... rename value` precisa
-- do tipo pelo nome que ele tem agora.
-- ---------------------------------------------------------------------------
do $$
declare r record;
begin
  for r in
    select * from (values
  ('app', 'dominio_sensivel', 'remuneracao', 'compensation'),
  ('app', 'dominio_sensivel', 'saude', 'health'),
  ('app', 'dominio_sensivel', 'disciplinar', 'disciplinary'),
  ('app', 'papel', 'diretoria', 'executive'),
  ('app', 'papel', 'rh', 'hr'),
  ('app', 'papel', 'dp', 'personnel'),
  ('app', 'papel', 'gestor_regional', 'regional_manager'),
  ('app', 'papel', 'supervisor_unidade', 'unit_supervisor'),
  ('app', 'papel', 'gestor_operacional', 'operations_manager'),
  ('app', 'papel', 'contabilidade', 'accounting'),
  ('app', 'papel', 'consulta', 'viewer')
) as t(sch, tipo, velho, novo)
  loop
    if exists (
      select 1 from pg_enum e
      join pg_type ty on ty.oid = e.enumtypid
      join pg_namespace n on n.oid = ty.typnamespace
      where n.nspname = r.sch and ty.typname = r.tipo and e.enumlabel = r.velho
    ) and not exists (
      select 1 from pg_enum e
      join pg_type ty on ty.oid = e.enumtypid
      join pg_namespace n on n.oid = ty.typnamespace
      where n.nspname = r.sch and ty.typname = r.tipo and e.enumlabel = r.novo
    ) then
      execute format('alter type %I.%I rename value %L to %L',
                     r.sch, r.tipo, r.velho, r.novo);
    end if;
  end loop;

  for r in
    select * from (values
  ('app', 'dominio_sensivel', 'sensitive_domain'),
  ('app', 'papel', 'user_role')
) as t(sch, velho, novo)
  loop
    if exists (select 1 from pg_type ty join pg_namespace n on n.oid = ty.typnamespace
                where n.nspname = r.sch and ty.typname = r.velho)
       and not exists (select 1 from pg_type ty join pg_namespace n on n.oid = ty.typnamespace
                        where n.nspname = r.sch and ty.typname = r.novo) then
      execute format('alter type %I.%I rename to %I', r.sch, r.velho, r.novo);
    end if;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 2. Tabelas
-- `alter table ... rename` é baseado em OID: view, policy, índice e constraint
-- que apontam para a tabela seguem sozinhos, porque guardam o OID e não o texto.
-- ---------------------------------------------------------------------------
do $$
declare r record;
begin
  for r in
    select * from (values
  ('app', 'acordo_financeiro', 'financial_agreement'),
  ('app', 'acordo_parcela', 'agreement_installment'),
  ('app', 'afastamento', 'leave_period'),
  ('app', 'alerta_enviado', 'alert_sent'),
  ('app', 'alerta_fila', 'alert_queue'),
  ('app', 'centro_custo', 'cost_center'),
  ('app', 'ciclo_relatorio', 'report_cycle'),
  ('app', 'colaborador', 'employee'),
  ('app', 'colaborador_funcao', 'employee_position'),
  ('app', 'colaborador_pii', 'employee_pii'),
  ('app', 'colaborador_remuneracao', 'employee_compensation'),
  ('app', 'competencia', 'payroll_period'),
  ('app', 'consulta_ia', 'ai_query'),
  ('app', 'contato', 'contact'),
  ('app', 'departamento', 'department'),
  ('app', 'desvio_tipo', 'deviation_type'),
  ('app', 'desvio_tipo_config', 'deviation_type_config'),
  ('app', 'deteccao_execucao', 'detection_run'),
  ('app', 'documento', 'document'),
  ('app', 'documento_tipo', 'document_type'),
  ('app', 'empresa', 'company'),
  ('app', 'encargo', 'payroll_charge'),
  ('app', 'escopo_usuario', 'user_scope'),
  ('app', 'exame_ocupacional', 'occupational_exam'),
  ('app', 'folha_evento', 'payroll_entry'),
  ('app', 'importacao_arquivo', 'file_import'),
  ('app', 'integracao', 'integration'),
  ('app', 'integracao_segredo', 'integration_secret'),
  ('app', 'jornada_dia', 'expected_workday'),
  ('app', 'justificativa', 'justification'),
  ('app', 'limiar_financeiro', 'financial_threshold'),
  ('app', 'metrica', 'metric'),
  ('app', 'movimentacao_pessoal', 'workforce_movement'),
  ('app', 'permissao_dominio', 'domain_permission'),
  ('app', 'regra_alerta', 'alert_rule'),
  ('app', 'regra_alerta_destino', 'alert_rule_target'),
  ('app', 'sync_execucao', 'sync_run'),
  ('app', 'tenant_membro', 'tenant_member'),
  ('app', 'unidade', 'unit'),
  ('app', 'unidade_mapa_secullum', 'unit_secullum_map'),
  ('app', 'unidade_responsavel', 'unit_responsible')
) as t(sch, velho, novo)
  loop
    if to_regclass(format('%I.%I', r.sch, r.velho)) is not null
       and to_regclass(format('%I.%I', r.sch, r.novo)) is null then
      execute format('alter table %I.%I rename to %I', r.sch, r.velho, r.novo);
    end if;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 3. Colunas
-- A tabela já está com o nome novo (bloco 2), então o alvo aqui é o nome novo.
-- ---------------------------------------------------------------------------
do $$
declare r record;
begin
  for r in
    select * from (values
  ('app', 'financial_agreement', 'colaborador_id', 'employee_id'),
  ('app', 'financial_agreement', 'tipo', 'type'),
  ('app', 'financial_agreement', 'descricao', 'description'),
  ('app', 'financial_agreement', 'valor_total', 'total_amount'),
  ('app', 'financial_agreement', 'qtd_parcelas', 'installment_count'),
  ('app', 'financial_agreement', 'data_acordo', 'agreement_date'),
  ('app', 'financial_agreement', 'documento_id', 'document_id'),
  ('app', 'financial_agreement', 'autorizado_por', 'authorized_by'),
  ('app', 'financial_agreement', 'autorizado_em', 'authorized_at'),
  ('app', 'financial_agreement', 'criado_em', 'created_at'),
  ('app', 'agreement_installment', 'acordo_id', 'agreement_id'),
  ('app', 'agreement_installment', 'numero', 'number'),
  ('app', 'agreement_installment', 'competencia_ano', 'period_year'),
  ('app', 'agreement_installment', 'competencia_mes', 'period_month'),
  ('app', 'agreement_installment', 'valor', 'amount'),
  ('app', 'agreement_installment', 'folha_evento_id', 'payroll_entry_id'),
  ('app', 'agreement_installment', 'processada_em', 'processed_at'),
  ('app', 'leave_period', 'colaborador_id', 'employee_id'),
  ('app', 'leave_period', 'categoria', 'category'),
  ('app', 'leave_period', 'data_inicio', 'start_date'),
  ('app', 'leave_period', 'data_fim', 'end_date'),
  ('app', 'leave_period', 'origem', 'source'),
  ('app', 'leave_period', 'criado_em', 'created_at'),
  ('app', 'alert_sent', 'fila_id', 'queue_id'),
  ('app', 'alert_sent', 'regra_id', 'rule_id'),
  ('app', 'alert_sent', 'canal', 'channel'),
  ('app', 'alert_sent', 'provedor', 'provider'),
  ('app', 'alert_sent', 'destino_hash', 'destination_hash'),
  ('app', 'alert_sent', 'erro', 'error'),
  ('app', 'alert_sent', 'custo_centavos', 'cost_cents'),
  ('app', 'alert_sent', 'enviado_em', 'sent_at'),
  ('app', 'alert_queue', 'regra_id', 'rule_id'),
  ('app', 'alert_queue', 'ciclo_relatorio_id', 'report_cycle_id'),
  ('app', 'alert_queue', 'canal', 'channel'),
  ('app', 'alert_queue', 'destino', 'destination'),
  ('app', 'alert_queue', 'chave_idempotencia', 'idempotency_key'),
  ('app', 'alert_queue', 'tentativas', 'attempts'),
  ('app', 'alert_queue', 'proxima_tentativa', 'next_attempt_at'),
  ('app', 'alert_queue', 'agendado_para', 'scheduled_for'),
  ('app', 'alert_queue', 'criado_em', 'created_at'),
  ('app', 'audit_log', 'acao', 'action'),
  ('app', 'audit_log', 'entidade', 'entity'),
  ('app', 'audit_log', 'entidade_id', 'entity_id'),
  ('app', 'audit_log', 'criado_em', 'created_at'),
  ('app', 'cost_center', 'empresa_id', 'company_id'),
  ('app', 'cost_center', 'unidade_id', 'unit_id'),
  ('app', 'cost_center', 'codigo', 'code'),
  ('app', 'cost_center', 'nome', 'name'),
  ('app', 'report_cycle', 'unidade_id', 'unit_id'),
  ('app', 'report_cycle', 'periodo_inicio', 'period_start'),
  ('app', 'report_cycle', 'periodo_fim', 'period_end'),
  ('app', 'report_cycle', 'gerado_em', 'generated_at'),
  ('app', 'report_cycle', 'enviado_em', 'sent_at'),
  ('app', 'report_cycle', 'canal', 'channel'),
  ('app', 'report_cycle', 'total_eventos', 'total_events'),
  ('app', 'employee', 'empresa_id', 'company_id'),
  ('app', 'employee', 'unidade_id', 'unit_id'),
  ('app', 'employee', 'departamento_id', 'department_id'),
  ('app', 'employee', 'secullum_funcionario_id', 'secullum_employee_id'),
  ('app', 'employee', 'matricula', 'registration_number'),
  ('app', 'employee', 'nome', 'name'),
  ('app', 'employee', 'tipo_contratacao', 'employment_type'),
  ('app', 'employee', 'data_admissao', 'hired_on'),
  ('app', 'employee', 'data_demissao', 'terminated_on'),
  ('app', 'employee', 'gestor_colaborador_id', 'manager_employee_id'),
  ('app', 'employee', 'criado_em', 'created_at'),
  ('app', 'employee', 'atualizado_em', 'updated_at'),
  ('app', 'employee_position', 'colaborador_id', 'employee_id'),
  ('app', 'employee_position', 'vigencia_inicio', 'effective_from'),
  ('app', 'employee_position', 'vigencia_fim', 'effective_to'),
  ('app', 'employee_position', 'unidade_id', 'unit_id'),
  ('app', 'employee_position', 'criado_em', 'created_at'),
  ('app', 'employee_pii', 'colaborador_id', 'employee_id'),
  ('app', 'employee_pii', 'data_nascimento', 'birth_date'),
  ('app', 'employee_pii', 'nome_mae', 'mother_name'),
  ('app', 'employee_pii', 'nome_pai', 'father_name'),
  ('app', 'employee_pii', 'telefone', 'phone'),
  ('app', 'employee_pii', 'email_pessoal', 'personal_email'),
  ('app', 'employee_pii', 'endereco', 'address'),
  ('app', 'employee_pii', 'atualizado_em', 'updated_at'),
  ('app', 'employee_compensation', 'colaborador_id', 'employee_id'),
  ('app', 'employee_compensation', 'vigencia_inicio', 'effective_from'),
  ('app', 'employee_compensation', 'vigencia_fim', 'effective_to'),
  ('app', 'employee_compensation', 'salario', 'salary'),
  ('app', 'employee_compensation', 'motivo', 'reason'),
  ('app', 'employee_compensation', 'registrado_por', 'recorded_by'),
  ('app', 'employee_compensation', 'criado_em', 'created_at'),
  ('app', 'payroll_period', 'ano', 'year'),
  ('app', 'payroll_period', 'mes', 'month'),
  ('app', 'payroll_period', 'fechada_em', 'closed_at'),
  ('app', 'ai_query', 'pergunta', 'question'),
  ('app', 'ai_query', 'metrica_codigo', 'metric_code'),
  ('app', 'ai_query', 'parametros', 'parameters'),
  ('app', 'ai_query', 'linhas_retornadas', 'rows_returned'),
  ('app', 'ai_query', 'latencia_ms', 'latency_ms'),
  ('app', 'ai_query', 'tokens_entrada', 'input_tokens'),
  ('app', 'ai_query', 'tokens_saida', 'output_tokens'),
  ('app', 'ai_query', 'recusada', 'refused'),
  ('app', 'ai_query', 'motivo_recusa', 'refusal_reason'),
  ('app', 'ai_query', 'criado_em', 'created_at'),
  ('app', 'contact', 'nome', 'name'),
  ('app', 'contact', 'tipo', 'type'),
  ('app', 'contact', 'ativo', 'active'),
  ('app', 'contact', 'criado_em', 'created_at'),
  ('app', 'department', 'empresa_id', 'company_id'),
  ('app', 'department', 'nome', 'name'),
  ('app', 'department', 'secullum_departamento_id', 'secullum_department_id'),
  ('app', 'department', 'ativo', 'active'),
  ('app', 'deviation_type', 'codigo', 'code'),
  ('app', 'deviation_type', 'descricao', 'description'),
  ('app', 'deviation_type', 'direcao', 'direction'),
  ('app', 'deviation_type', 'categoria', 'category'),
  ('app', 'deviation_type_config', 'codigo', 'code'),
  ('app', 'deviation_type_config', 'ativo', 'active'),
  ('app', 'deviation_type_config', 'conta_como_desvio', 'counts_as_deviation'),
  ('app', 'deviation_type_config', 'gera_alerta', 'triggers_alert'),
  ('app', 'deviation_type_config', 'tolerancia_extra_min', 'tolerance_extra_minutes'),
  ('app', 'deviation_type_config', 'tolerancia_falta_min', 'tolerance_absence_minutes'),
  ('app', 'detection_run', 'modo', 'mode'),
  ('app', 'detection_run', 'periodo_inicio', 'period_start'),
  ('app', 'detection_run', 'periodo_fim', 'period_end'),
  ('app', 'detection_run', 'iniciado_em', 'started_at'),
  ('app', 'detection_run', 'terminado_em', 'finished_at'),
  ('app', 'detection_run', 'eventos_detectados', 'events_detected'),
  ('app', 'detection_run', 'eventos_publicados', 'events_published'),
  ('app', 'detection_run', 'versao_motor', 'engine_version'),
  ('app', 'detection_run', 'erro', 'error'),
  ('app', 'deviation_event', 'colaborador_id', 'employee_id'),
  ('app', 'deviation_event', 'empresa_id', 'company_id'),
  ('app', 'deviation_event', 'unidade_id', 'unit_id'),
  ('app', 'deviation_event', 'data_ref', 'reference_date'),
  ('app', 'deviation_event', 'tipo', 'type'),
  ('app', 'deviation_event', 'minutos', 'minutes'),
  ('app', 'deviation_event', 'horario_previsto', 'expected_time'),
  ('app', 'deviation_event', 'horario_realizado', 'actual_time'),
  ('app', 'deviation_event', 'batida_ids', 'punch_ids'),
  ('app', 'deviation_event', 'motivo_status', 'status_reason'),
  ('app', 'deviation_event', 'modo', 'mode'),
  ('app', 'deviation_event', 'execucao_id', 'run_id'),
  ('app', 'deviation_event', 'ciclo_relatorio_id', 'report_cycle_id'),
  ('app', 'deviation_event', 'detectado_em', 'detected_at'),
  ('app', 'deviation_event', 'atualizado_em', 'updated_at'),
  ('app', 'document', 'colaborador_id', 'employee_id'),
  ('app', 'document', 'tipo_id', 'type_id'),
  ('app', 'document', 'nome_arquivo', 'file_name'),
  ('app', 'document', 'emitido_em', 'issued_on'),
  ('app', 'document', 'valido_ate', 'valid_until'),
  ('app', 'document', 'substitui_id', 'replaces_id'),
  ('app', 'document', 'criado_por', 'created_by'),
  ('app', 'document', 'criado_em', 'created_at'),
  ('app', 'document_type', 'nome', 'name'),
  ('app', 'document_type', 'exige_validade', 'requires_expiry'),
  ('app', 'document_type', 'dias_alerta_vencimento', 'expiry_alert_days'),
  ('app', 'document_type', 'obrigatorio', 'required'),
  ('app', 'document_type', 'dominio', 'domain'),
  ('app', 'company', 'razao_social', 'legal_name'),
  ('app', 'company', 'nome_fantasia', 'trade_name'),
  ('app', 'company', 'secullum_empresa_id', 'secullum_company_id'),
  ('app', 'company', 'ativo', 'active'),
  ('app', 'company', 'criado_em', 'created_at'),
  ('app', 'payroll_charge', 'competencia_id', 'payroll_period_id'),
  ('app', 'payroll_charge', 'empresa_id', 'company_id'),
  ('app', 'payroll_charge', 'unidade_id', 'unit_id'),
  ('app', 'payroll_charge', 'tipo', 'type'),
  ('app', 'payroll_charge', 'base_calculo', 'calculation_base'),
  ('app', 'payroll_charge', 'valor', 'amount'),
  ('app', 'payroll_charge', 'origem', 'source'),
  ('app', 'payroll_charge', 'criado_em', 'created_at'),
  ('app', 'user_scope', 'empresa_id', 'company_id'),
  ('app', 'user_scope', 'unidade_id', 'unit_id'),
  ('app', 'user_scope', 'criado_em', 'created_at'),
  ('app', 'occupational_exam', 'colaborador_id', 'employee_id'),
  ('app', 'occupational_exam', 'tipo', 'type'),
  ('app', 'occupational_exam', 'realizado_em', 'performed_on'),
  ('app', 'occupational_exam', 'valido_ate', 'valid_until'),
  ('app', 'occupational_exam', 'resultado', 'result'),
  ('app', 'occupational_exam', 'documento_id', 'document_id'),
  ('app', 'occupational_exam', 'criado_por', 'created_by'),
  ('app', 'occupational_exam', 'criado_em', 'created_at'),
  ('app', 'payroll_entry', 'competencia_id', 'payroll_period_id'),
  ('app', 'payroll_entry', 'colaborador_id', 'employee_id'),
  ('app', 'payroll_entry', 'empresa_id', 'company_id'),
  ('app', 'payroll_entry', 'unidade_id', 'unit_id'),
  ('app', 'payroll_entry', 'centro_custo_id', 'cost_center_id'),
  ('app', 'payroll_entry', 'codigo', 'code'),
  ('app', 'payroll_entry', 'descricao', 'description'),
  ('app', 'payroll_entry', 'natureza', 'nature'),
  ('app', 'payroll_entry', 'referencia', 'reference'),
  ('app', 'payroll_entry', 'valor', 'amount'),
  ('app', 'payroll_entry', 'origem', 'source'),
  ('app', 'payroll_entry', 'importacao_id', 'import_id'),
  ('app', 'payroll_entry', 'criado_em', 'created_at'),
  ('app', 'file_import', 'tipo', 'type'),
  ('app', 'file_import', 'competencia_id', 'payroll_period_id'),
  ('app', 'file_import', 'nome_arquivo', 'file_name'),
  ('app', 'file_import', 'layout_versao', 'layout_version'),
  ('app', 'file_import', 'enviado_por', 'uploaded_by'),
  ('app', 'file_import', 'linhas_total', 'rows_total'),
  ('app', 'file_import', 'linhas_ok', 'rows_ok'),
  ('app', 'file_import', 'linhas_erro', 'rows_error'),
  ('app', 'file_import', 'relatorio', 'report'),
  ('app', 'file_import', 'criado_em', 'created_at'),
  ('app', 'integration', 'provedor', 'provider'),
  ('app', 'integration', 'apelido', 'alias'),
  ('app', 'integration', 'ativo', 'active'),
  ('app', 'integration', 'criado_em', 'created_at'),
  ('app', 'integration_secret', 'integracao_id', 'integration_id'),
  ('app', 'integration_secret', 'chave', 'key'),
  ('app', 'integration_secret', 'atualizado_em', 'updated_at'),
  ('app', 'expected_workday', 'colaborador_id', 'employee_id'),
  ('app', 'expected_workday', 'data_ref', 'reference_date'),
  ('app', 'expected_workday', 'tipo_dia', 'day_type'),
  ('app', 'expected_workday', 'entrada_prevista', 'expected_entry'),
  ('app', 'expected_workday', 'saida_prevista', 'expected_exit'),
  ('app', 'expected_workday', 'intervalo_previsto_min', 'expected_break_minutes'),
  ('app', 'expected_workday', 'carga_prevista_min', 'workload_minutes'),
  ('app', 'expected_workday', 'tolerancia_extra_min', 'tolerance_extra_minutes'),
  ('app', 'expected_workday', 'tolerancia_falta_min', 'tolerance_absence_minutes'),
  ('app', 'expected_workday', 'secullum_horario_id', 'secullum_schedule_id'),
  ('app', 'expected_workday', 'origem', 'source'),
  ('app', 'expected_workday', 'confianca', 'confidence'),
  ('app', 'justification', 'colaborador_id', 'employee_id'),
  ('app', 'justification', 'data_ref', 'reference_date'),
  ('app', 'justification', 'texto', 'text'),
  ('app', 'justification', 'origem', 'source'),
  ('app', 'justification', 'autor_user_id', 'author_user_id'),
  ('app', 'justification', 'autor_nome', 'author_name'),
  ('app', 'justification', 'criado_em', 'created_at'),
  ('app', 'financial_threshold', 'empresa_id', 'company_id'),
  ('app', 'financial_threshold', 'unidade_id', 'unit_id'),
  ('app', 'financial_threshold', 'indicador', 'indicator'),
  ('app', 'financial_threshold', 'operador', 'operator'),
  ('app', 'financial_threshold', 'valor', 'amount'),
  ('app', 'financial_threshold', 'ativo', 'active'),
  ('app', 'metric', 'codigo', 'code'),
  ('app', 'metric', 'titulo', 'title'),
  ('app', 'metric', 'descricao', 'description'),
  ('app', 'metric', 'view_alvo', 'target_view'),
  ('app', 'metric', 'dimensoes', 'dimensions'),
  ('app', 'metric', 'filtros', 'filters'),
  ('app', 'metric', 'dominio', 'domain'),
  ('app', 'metric', 'ativo', 'active'),
  ('app', 'workforce_movement', 'colaborador_id', 'employee_id'),
  ('app', 'workforce_movement', 'empresa_id', 'company_id'),
  ('app', 'workforce_movement', 'unidade_id', 'unit_id'),
  ('app', 'workforce_movement', 'tipo', 'type'),
  ('app', 'workforce_movement', 'data_evento', 'event_date'),
  ('app', 'workforce_movement', 'competencia_id', 'payroll_period_id'),
  ('app', 'workforce_movement', 'custo_estimado', 'estimated_cost'),
  ('app', 'workforce_movement', 'observacao', 'notes'),
  ('app', 'workforce_movement', 'criado_em', 'created_at'),
  ('app', 'domain_permission', 'papel', 'role'),
  ('app', 'domain_permission', 'dominio', 'domain'),
  ('app', 'domain_permission', 'permitido', 'allowed'),
  ('app', 'alert_rule', 'nome', 'name'),
  ('app', 'alert_rule', 'desvio_tipo', 'deviation_type'),
  ('app', 'alert_rule', 'escopo_unidade_id', 'scope_unit_id'),
  ('app', 'alert_rule', 'conteudo', 'content'),
  ('app', 'alert_rule', 'canal', 'channel'),
  ('app', 'alert_rule', 'janela_cron', 'cron_window'),
  ('app', 'alert_rule', 'limiar_minutos', 'threshold_minutes'),
  ('app', 'alert_rule', 'limiar_ocorrencias', 'threshold_occurrences'),
  ('app', 'alert_rule', 'silenciar_ate', 'muted_until'),
  ('app', 'alert_rule', 'ativo', 'active'),
  ('app', 'alert_rule', 'criado_em', 'created_at'),
  ('app', 'alert_rule_target', 'regra_id', 'rule_id'),
  ('app', 'alert_rule_target', 'contato_id', 'contact_id'),
  ('app', 'alert_rule_target', 'funcao', 'responsibility'),
  ('app', 'sync_run', 'integracao_id', 'integration_id'),
  ('app', 'sync_run', 'entidade', 'entity'),
  ('app', 'sync_run', 'iniciado_em', 'started_at'),
  ('app', 'sync_run', 'terminado_em', 'finished_at'),
  ('app', 'sync_run', 'cursor_ate', 'cursor_until'),
  ('app', 'sync_run', 'registros_lidos', 'records_read'),
  ('app', 'sync_run', 'registros_gravados', 'records_written'),
  ('app', 'sync_run', 'erro', 'error'),
  ('app', 'tenant', 'nome', 'name'),
  ('app', 'tenant', 'ativo', 'active'),
  ('app', 'tenant', 'criado_em', 'created_at'),
  ('app', 'tenant_member', 'papel', 'role'),
  ('app', 'tenant_member', 'ativo', 'active'),
  ('app', 'tenant_member', 'criado_em', 'created_at'),
  ('app', 'unit', 'empresa_id', 'company_id'),
  ('app', 'unit', 'codigo', 'code'),
  ('app', 'unit', 'nome', 'name'),
  ('app', 'unit', 'endereco', 'address'),
  ('app', 'unit', 'ativo', 'active'),
  ('app', 'unit', 'criado_em', 'created_at'),
  ('app', 'unit_secullum_map', 'secullum_departamento_id', 'secullum_department_id'),
  ('app', 'unit_secullum_map', 'unidade_id', 'unit_id'),
  ('app', 'unit_secullum_map', 'validado_por', 'validated_by'),
  ('app', 'unit_secullum_map', 'validado_em', 'validated_at'),
  ('app', 'unit_secullum_map', 'observacao', 'notes'),
  ('app', 'unit_responsible', 'unidade_id', 'unit_id'),
  ('app', 'unit_responsible', 'contato_id', 'contact_id'),
  ('app', 'unit_responsible', 'funcao', 'responsibility'),
  ('app', 'unit_responsible', 'principal', 'is_primary')
) as t(sch, tab, velho, novo)
  loop
    if to_regclass(format('%I.%I', r.sch, r.tab)) is not null
       and exists (select 1 from information_schema.columns
                    where table_schema = r.sch and table_name = r.tab
                      and column_name = r.velho)
       and not exists (select 1 from information_schema.columns
                        where table_schema = r.sch and table_name = r.tab
                          and column_name = r.novo) then
      execute format('alter table %I.%I rename column %I to %I',
                     r.sch, r.tab, r.velho, r.novo);
    end if;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 4. Constraints
-- Nome de check criado inline é gerado pelo Postgres (`colaborador_status_check`)
-- e não acompanha o rename da tabela: tem de vir explícito.
-- ---------------------------------------------------------------------------
do $$
declare r record;
begin
  for r in
    select * from (values
  ('app', 'financial_agreement', 'acordo_financeiro_autorizado_por_fkey', 'financial_agreement_authorized_by_fkey'),
  ('app', 'financial_agreement', 'acordo_financeiro_colaborador_id_fkey', 'financial_agreement_employee_id_fkey'),
  ('app', 'financial_agreement', 'acordo_financeiro_documento_id_fkey', 'financial_agreement_document_id_fkey'),
  ('app', 'financial_agreement', 'acordo_financeiro_pkey', 'financial_agreement_pkey'),
  ('app', 'financial_agreement', 'acordo_financeiro_tenant_id_fkey', 'financial_agreement_tenant_id_fkey'),
  ('app', 'agreement_installment', 'acordo_parcela_acordo_id_fkey', 'agreement_installment_agreement_id_fkey'),
  ('app', 'agreement_installment', 'acordo_parcela_acordo_id_numero_key', 'agreement_installment_agreement_id_number_key'),
  ('app', 'agreement_installment', 'acordo_parcela_folha_evento_id_fkey', 'agreement_installment_payroll_entry_id_fkey'),
  ('app', 'agreement_installment', 'acordo_parcela_pkey', 'agreement_installment_pkey'),
  ('app', 'agreement_installment', 'acordo_parcela_tenant_id_fkey', 'agreement_installment_tenant_id_fkey'),
  ('app', 'leave_period', 'afastamento_colaborador_id_fkey', 'leave_period_employee_id_fkey'),
  ('app', 'leave_period', 'afastamento_pkey', 'leave_period_pkey'),
  ('app', 'leave_period', 'afastamento_tenant_id_fkey', 'leave_period_tenant_id_fkey'),
  ('app', 'alert_sent', 'alerta_enviado_fila_id_fkey', 'alert_sent_queue_id_fkey'),
  ('app', 'alert_sent', 'alerta_enviado_pkey', 'alert_sent_pkey'),
  ('app', 'alert_sent', 'alerta_enviado_regra_id_fkey', 'alert_sent_rule_id_fkey'),
  ('app', 'alert_sent', 'alerta_enviado_tenant_id_fkey', 'alert_sent_tenant_id_fkey'),
  ('app', 'alert_queue', 'alerta_fila_chave_idempotencia_key', 'alert_queue_idempotency_key_key'),
  ('app', 'alert_queue', 'alerta_fila_ciclo_relatorio_id_fkey', 'alert_queue_report_cycle_id_fkey'),
  ('app', 'alert_queue', 'alerta_fila_deviation_event_id_fkey', 'alert_queue_deviation_event_id_fkey'),
  ('app', 'alert_queue', 'alerta_fila_pkey', 'alert_queue_pkey'),
  ('app', 'alert_queue', 'alerta_fila_regra_id_fkey', 'alert_queue_rule_id_fkey'),
  ('app', 'alert_queue', 'alerta_fila_tenant_id_fkey', 'alert_queue_tenant_id_fkey'),
  ('app', 'cost_center', 'centro_custo_empresa_id_fkey', 'cost_center_company_id_fkey'),
  ('app', 'cost_center', 'centro_custo_pkey', 'cost_center_pkey'),
  ('app', 'cost_center', 'centro_custo_tenant_id_codigo_key', 'cost_center_tenant_id_code_key'),
  ('app', 'cost_center', 'centro_custo_tenant_id_fkey', 'cost_center_tenant_id_fkey'),
  ('app', 'cost_center', 'centro_custo_unidade_id_fkey', 'cost_center_unit_id_fkey'),
  ('app', 'report_cycle', 'ciclo_relatorio_pkey', 'report_cycle_pkey'),
  ('app', 'report_cycle', 'ciclo_relatorio_tenant_id_fkey', 'report_cycle_tenant_id_fkey'),
  ('app', 'report_cycle', 'ciclo_relatorio_unidade_id_fkey', 'report_cycle_unit_id_fkey'),
  ('app', 'employee', 'colaborador_departamento_id_fkey', 'employee_department_id_fkey'),
  ('app', 'employee', 'colaborador_empresa_id_fkey', 'employee_company_id_fkey'),
  ('app', 'employee', 'colaborador_gestor_colaborador_id_fkey', 'employee_manager_employee_id_fkey'),
  ('app', 'employee', 'colaborador_pkey', 'employee_pkey'),
  ('app', 'employee', 'colaborador_tenant_id_fkey', 'employee_tenant_id_fkey'),
  ('app', 'employee', 'colaborador_tenant_id_secullum_funcionario_id_key', 'employee_tenant_id_secullum_employee_id_key'),
  ('app', 'employee', 'colaborador_unidade_id_fkey', 'employee_unit_id_fkey'),
  ('app', 'employee_position', 'colaborador_funcao_colaborador_id_fkey', 'employee_position_employee_id_fkey'),
  ('app', 'employee_position', 'colaborador_funcao_pkey', 'employee_position_pkey'),
  ('app', 'employee_position', 'colaborador_funcao_tenant_id_fkey', 'employee_position_tenant_id_fkey'),
  ('app', 'employee_position', 'colaborador_funcao_unidade_id_fkey', 'employee_position_unit_id_fkey'),
  ('app', 'employee_pii', 'colaborador_pii_colaborador_id_fkey', 'employee_pii_employee_id_fkey'),
  ('app', 'employee_pii', 'colaborador_pii_pkey', 'employee_pii_pkey'),
  ('app', 'employee_pii', 'colaborador_pii_tenant_id_fkey', 'employee_pii_tenant_id_fkey'),
  ('app', 'employee_compensation', 'colaborador_remuneracao_colaborador_id_fkey', 'employee_compensation_employee_id_fkey'),
  ('app', 'employee_compensation', 'colaborador_remuneracao_pkey', 'employee_compensation_pkey'),
  ('app', 'employee_compensation', 'colaborador_remuneracao_registrado_por_fkey', 'employee_compensation_recorded_by_fkey'),
  ('app', 'employee_compensation', 'colaborador_remuneracao_tenant_id_fkey', 'employee_compensation_tenant_id_fkey'),
  ('app', 'payroll_period', 'competencia_pkey', 'payroll_period_pkey'),
  ('app', 'payroll_period', 'competencia_tenant_id_ano_mes_key', 'payroll_period_tenant_id_year_month_key'),
  ('app', 'payroll_period', 'competencia_tenant_id_fkey', 'payroll_period_tenant_id_fkey'),
  ('app', 'ai_query', 'consulta_ia_pkey', 'ai_query_pkey'),
  ('app', 'ai_query', 'consulta_ia_tenant_id_fkey', 'ai_query_tenant_id_fkey'),
  ('app', 'ai_query', 'consulta_ia_user_id_fkey', 'ai_query_user_id_fkey'),
  ('app', 'contact', 'contato_pkey', 'contact_pkey'),
  ('app', 'contact', 'contato_tenant_id_fkey', 'contact_tenant_id_fkey'),
  ('app', 'department', 'departamento_empresa_id_fkey', 'department_company_id_fkey'),
  ('app', 'department', 'departamento_pkey', 'department_pkey'),
  ('app', 'department', 'departamento_tenant_id_fkey', 'department_tenant_id_fkey'),
  ('app', 'department', 'departamento_tenant_id_secullum_departamento_id_key', 'department_tenant_id_secullum_department_id_key'),
  ('app', 'deviation_type', 'desvio_tipo_pkey', 'deviation_type_pkey'),
  ('app', 'deviation_type_config', 'desvio_tipo_config_codigo_fkey', 'deviation_type_config_code_fkey'),
  ('app', 'deviation_type_config', 'desvio_tipo_config_pkey', 'deviation_type_config_pkey'),
  ('app', 'deviation_type_config', 'desvio_tipo_config_tenant_id_fkey', 'deviation_type_config_tenant_id_fkey'),
  ('app', 'detection_run', 'deteccao_execucao_pkey', 'detection_run_pkey'),
  ('app', 'detection_run', 'deteccao_execucao_tenant_id_fkey', 'detection_run_tenant_id_fkey'),
  ('app', 'deviation_event', 'deviation_event_ciclo_relatorio_id_fkey', 'deviation_event_report_cycle_id_fkey'),
  ('app', 'deviation_event', 'deviation_event_colaborador_id_fkey', 'deviation_event_employee_id_fkey'),
  ('app', 'deviation_event', 'deviation_event_empresa_id_fkey', 'deviation_event_company_id_fkey'),
  ('app', 'deviation_event', 'deviation_event_execucao_id_fkey', 'deviation_event_run_id_fkey'),
  ('app', 'deviation_event', 'deviation_event_tipo_fkey', 'deviation_event_type_fkey'),
  ('app', 'deviation_event', 'deviation_event_unidade_id_fkey', 'deviation_event_unit_id_fkey'),
  ('app', 'document', 'documento_colaborador_id_fkey', 'document_employee_id_fkey'),
  ('app', 'document', 'documento_criado_por_fkey', 'document_created_by_fkey'),
  ('app', 'document', 'documento_pkey', 'document_pkey'),
  ('app', 'document', 'documento_storage_bucket_storage_path_key', 'document_storage_bucket_storage_path_key'),
  ('app', 'document', 'documento_substitui_id_fkey', 'document_replaces_id_fkey'),
  ('app', 'document', 'documento_tenant_id_fkey', 'document_tenant_id_fkey'),
  ('app', 'document', 'documento_tipo_id_fkey', 'document_type_id_fkey'),
  ('app', 'document_type', 'documento_tipo_pkey', 'document_type_pkey'),
  ('app', 'document_type', 'documento_tipo_tenant_id_fkey', 'document_type_tenant_id_fkey'),
  ('app', 'document_type', 'documento_tipo_tenant_id_nome_key', 'document_type_tenant_id_name_key'),
  ('app', 'company', 'empresa_pkey', 'company_pkey'),
  ('app', 'company', 'empresa_tenant_id_cnpj_key', 'company_tenant_id_cnpj_key'),
  ('app', 'company', 'empresa_tenant_id_fkey', 'company_tenant_id_fkey'),
  ('app', 'company', 'empresa_tenant_id_secullum_empresa_id_key', 'company_tenant_id_secullum_company_id_key'),
  ('app', 'payroll_charge', 'encargo_competencia_id_fkey', 'payroll_charge_payroll_period_id_fkey'),
  ('app', 'payroll_charge', 'encargo_empresa_id_fkey', 'payroll_charge_company_id_fkey'),
  ('app', 'payroll_charge', 'encargo_pkey', 'payroll_charge_pkey'),
  ('app', 'payroll_charge', 'encargo_tenant_id_fkey', 'payroll_charge_tenant_id_fkey'),
  ('app', 'payroll_charge', 'encargo_unidade_id_fkey', 'payroll_charge_unit_id_fkey'),
  ('app', 'user_scope', 'escopo_usuario_empresa_fk', 'user_scope_empresa_fk'),
  ('app', 'user_scope', 'escopo_usuario_pkey', 'user_scope_pkey'),
  ('app', 'user_scope', 'escopo_usuario_tenant_id_fkey', 'user_scope_tenant_id_fkey'),
  ('app', 'user_scope', 'escopo_usuario_unidade_fk', 'user_scope_unidade_fk'),
  ('app', 'user_scope', 'escopo_usuario_user_id_fkey', 'user_scope_user_id_fkey'),
  ('app', 'occupational_exam', 'exame_ocupacional_colaborador_id_fkey', 'occupational_exam_employee_id_fkey'),
  ('app', 'occupational_exam', 'exame_ocupacional_criado_por_fkey', 'occupational_exam_created_by_fkey'),
  ('app', 'occupational_exam', 'exame_ocupacional_documento_id_fkey', 'occupational_exam_document_id_fkey'),
  ('app', 'occupational_exam', 'exame_ocupacional_pkey', 'occupational_exam_pkey'),
  ('app', 'occupational_exam', 'exame_ocupacional_tenant_id_fkey', 'occupational_exam_tenant_id_fkey'),
  ('app', 'payroll_entry', 'folha_evento_centro_custo_id_fkey', 'payroll_entry_cost_center_id_fkey'),
  ('app', 'payroll_entry', 'folha_evento_colaborador_id_fkey', 'payroll_entry_employee_id_fkey'),
  ('app', 'payroll_entry', 'folha_evento_competencia_id_fkey', 'payroll_entry_payroll_period_id_fkey'),
  ('app', 'payroll_entry', 'folha_evento_empresa_id_fkey', 'payroll_entry_company_id_fkey'),
  ('app', 'payroll_entry', 'folha_evento_importacao_fk', 'payroll_entry_importacao_fk'),
  ('app', 'payroll_entry', 'folha_evento_pkey', 'payroll_entry_pkey'),
  ('app', 'payroll_entry', 'folha_evento_tenant_id_fkey', 'payroll_entry_tenant_id_fkey'),
  ('app', 'payroll_entry', 'folha_evento_unidade_id_fkey', 'payroll_entry_unit_id_fkey'),
  ('app', 'file_import', 'importacao_arquivo_competencia_id_fkey', 'file_import_payroll_period_id_fkey'),
  ('app', 'file_import', 'importacao_arquivo_enviado_por_fkey', 'file_import_uploaded_by_fkey'),
  ('app', 'file_import', 'importacao_arquivo_pkey', 'file_import_pkey'),
  ('app', 'file_import', 'importacao_arquivo_tenant_id_fkey', 'file_import_tenant_id_fkey'),
  ('app', 'integration', 'integracao_pkey', 'integration_pkey'),
  ('app', 'integration', 'integracao_tenant_id_fkey', 'integration_tenant_id_fkey'),
  ('app', 'integration', 'integracao_tenant_id_provedor_apelido_key', 'integration_tenant_id_provider_alias_key'),
  ('app', 'integration_secret', 'integracao_segredo_integracao_id_fkey', 'integration_secret_integration_id_fkey'),
  ('app', 'integration_secret', 'integracao_segredo_pkey', 'integration_secret_pkey'),
  ('app', 'expected_workday', 'jornada_dia_colaborador_id_fkey', 'expected_workday_employee_id_fkey'),
  ('app', 'expected_workday', 'jornada_dia_pkey', 'expected_workday_pkey'),
  ('app', 'expected_workday', 'jornada_dia_tenant_id_fkey', 'expected_workday_tenant_id_fkey'),
  ('app', 'justification', 'justificativa_autor_user_id_fkey', 'justification_author_user_id_fkey'),
  ('app', 'justification', 'justificativa_colaborador_id_fkey', 'justification_employee_id_fkey'),
  ('app', 'justification', 'justificativa_deviation_event_id_fkey', 'justification_deviation_event_id_fkey'),
  ('app', 'justification', 'justificativa_pkey', 'justification_pkey'),
  ('app', 'justification', 'justificativa_tenant_id_fkey', 'justification_tenant_id_fkey'),
  ('app', 'financial_threshold', 'limiar_financeiro_empresa_id_fkey', 'financial_threshold_company_id_fkey'),
  ('app', 'financial_threshold', 'limiar_financeiro_pkey', 'financial_threshold_pkey'),
  ('app', 'financial_threshold', 'limiar_financeiro_tenant_id_fkey', 'financial_threshold_tenant_id_fkey'),
  ('app', 'financial_threshold', 'limiar_financeiro_unidade_id_fkey', 'financial_threshold_unit_id_fkey'),
  ('app', 'metric', 'metrica_pkey', 'metric_pkey'),
  ('app', 'workforce_movement', 'movimentacao_pessoal_colaborador_id_fkey', 'workforce_movement_employee_id_fkey'),
  ('app', 'workforce_movement', 'movimentacao_pessoal_competencia_id_fkey', 'workforce_movement_payroll_period_id_fkey'),
  ('app', 'workforce_movement', 'movimentacao_pessoal_empresa_id_fkey', 'workforce_movement_company_id_fkey'),
  ('app', 'workforce_movement', 'movimentacao_pessoal_pkey', 'workforce_movement_pkey'),
  ('app', 'workforce_movement', 'movimentacao_pessoal_tenant_id_fkey', 'workforce_movement_tenant_id_fkey'),
  ('app', 'workforce_movement', 'movimentacao_pessoal_unidade_id_fkey', 'workforce_movement_unit_id_fkey'),
  ('app', 'domain_permission', 'permissao_dominio_pkey', 'domain_permission_pkey'),
  ('app', 'domain_permission', 'permissao_dominio_tenant_id_fkey', 'domain_permission_tenant_id_fkey'),
  ('app', 'alert_rule', 'regra_alerta_desvio_tipo_fkey', 'alert_rule_deviation_type_fkey'),
  ('app', 'alert_rule', 'regra_alerta_escopo_unidade_id_fkey', 'alert_rule_scope_unit_id_fkey'),
  ('app', 'alert_rule', 'regra_alerta_pkey', 'alert_rule_pkey'),
  ('app', 'alert_rule', 'regra_alerta_tenant_id_fkey', 'alert_rule_tenant_id_fkey'),
  ('app', 'alert_rule_target', 'regra_alerta_destino_contato_id_fkey', 'alert_rule_target_contact_id_fkey'),
  ('app', 'alert_rule_target', 'regra_alerta_destino_pkey', 'alert_rule_target_pkey'),
  ('app', 'alert_rule_target', 'regra_alerta_destino_regra_id_fkey', 'alert_rule_target_rule_id_fkey'),
  ('app', 'sync_run', 'sync_execucao_integracao_id_fkey', 'sync_run_integration_id_fkey'),
  ('app', 'sync_run', 'sync_execucao_pkey', 'sync_run_pkey'),
  ('app', 'sync_run', 'sync_execucao_tenant_id_fkey', 'sync_run_tenant_id_fkey'),
  ('app', 'tenant_member', 'tenant_membro_pkey', 'tenant_member_pkey'),
  ('app', 'tenant_member', 'tenant_membro_tenant_id_fkey', 'tenant_member_tenant_id_fkey'),
  ('app', 'tenant_member', 'tenant_membro_user_id_fkey', 'tenant_member_user_id_fkey'),
  ('app', 'unit', 'unidade_empresa_id_fkey', 'unit_company_id_fkey'),
  ('app', 'unit', 'unidade_pkey', 'unit_pkey'),
  ('app', 'unit', 'unidade_tenant_id_codigo_key', 'unit_tenant_id_code_key'),
  ('app', 'unit', 'unidade_tenant_id_fkey', 'unit_tenant_id_fkey'),
  ('app', 'unit_secullum_map', 'unidade_mapa_secullum_pkey', 'unit_secullum_map_pkey'),
  ('app', 'unit_secullum_map', 'unidade_mapa_secullum_tenant_id_fkey', 'unit_secullum_map_tenant_id_fkey'),
  ('app', 'unit_secullum_map', 'unidade_mapa_secullum_unidade_id_fkey', 'unit_secullum_map_unit_id_fkey'),
  ('app', 'unit_secullum_map', 'unidade_mapa_secullum_validado_por_fkey', 'unit_secullum_map_validated_by_fkey'),
  ('app', 'unit_responsible', 'unidade_responsavel_contato_id_fkey', 'unit_responsible_contact_id_fkey'),
  ('app', 'unit_responsible', 'unidade_responsavel_pkey', 'unit_responsible_pkey'),
  ('app', 'unit_responsible', 'unidade_responsavel_tenant_id_fkey', 'unit_responsible_tenant_id_fkey'),
  ('app', 'unit_responsible', 'unidade_responsavel_unidade_id_contato_id_funcao_key', 'unit_responsible_unit_id_contact_id_responsibility_key'),
  ('app', 'unit_responsible', 'unidade_responsavel_unidade_id_fkey', 'unit_responsible_unit_id_fkey')
) as t(sch, tab, velho, novo)
  loop
    if to_regclass(format('%I.%I', r.sch, r.tab)) is null then
      continue;
    end if;
if exists (select 1 from pg_constraint c
                join pg_class rel on rel.oid = c.conrelid
                join pg_namespace n on n.oid = rel.relnamespace
                where n.nspname = r.sch and rel.relname = r.tab and c.conname = r.velho)
       and not exists (select 1 from pg_constraint c
                        join pg_class rel on rel.oid = c.conrelid
                        join pg_namespace n on n.oid = rel.relnamespace
                        where n.nspname = r.sch and rel.relname = r.tab and c.conname = r.novo) then
      execute format('alter table %I.%I rename constraint %I to %I',
                     r.sch, r.tab, r.velho, r.novo);
    end if;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 5. Índices
-- `alter index` é a forma para índice; constraint-índice (pkey, unique) já foi
-- renomeado no bloco 4 e o índice segue junto.
-- ---------------------------------------------------------------------------
do $$
declare r record;
begin
  for r in
    select * from (values
  ('app', 'financial_agreement', 'acordo_financeiro_autorizado_por_fkidx', 'financial_agreement_authorized_by_fkidx'),
  ('app', 'financial_agreement', 'acordo_financeiro_documento_id_fkidx', 'financial_agreement_document_id_fkidx'),
  ('app', 'financial_agreement', 'acordo_financeiro_pkey', 'financial_agreement_pkey'),
  ('app', 'financial_agreement', 'acordo_financeiro_tenant_id_fkidx', 'financial_agreement_tenant_id_fkidx'),
  ('app', 'agreement_installment', 'acordo_parcela_acordo_id_numero_key', 'agreement_installment_agreement_id_number_key'),
  ('app', 'agreement_installment', 'acordo_parcela_folha_evento_id_fkidx', 'agreement_installment_payroll_entry_id_fkidx'),
  ('app', 'agreement_installment', 'acordo_parcela_pkey', 'agreement_installment_pkey'),
  ('app', 'leave_period', 'afastamento_periodo_idx', 'leave_period_periodo_idx'),
  ('app', 'leave_period', 'afastamento_pkey', 'leave_period_pkey'),
  ('app', 'leave_period', 'afastamento_tenant_id_fkidx', 'leave_period_tenant_id_fkidx'),
  ('app', 'alert_sent', 'alerta_enviado_fila_id_fkidx', 'alert_sent_queue_id_fkidx'),
  ('app', 'alert_sent', 'alerta_enviado_pkey', 'alert_sent_pkey'),
  ('app', 'alert_sent', 'alerta_enviado_regra_id_fkidx', 'alert_sent_rule_id_fkidx'),
  ('app', 'alert_sent', 'alerta_enviado_tenant_idx', 'alert_sent_tenant_idx'),
  ('app', 'alert_queue', 'alerta_fila_chave_idempotencia_key', 'alert_queue_idempotency_key_key'),
  ('app', 'alert_queue', 'alerta_fila_ciclo_relatorio_id_fkidx', 'alert_queue_report_cycle_id_fkidx'),
  ('app', 'alert_queue', 'alerta_fila_evento_idx', 'alert_queue_evento_idx'),
  ('app', 'alert_queue', 'alerta_fila_pkey', 'alert_queue_pkey'),
  ('app', 'alert_queue', 'alerta_fila_proxima_idx', 'alert_queue_proxima_idx'),
  ('app', 'alert_queue', 'alerta_fila_regra_id_fkidx', 'alert_queue_rule_id_fkidx'),
  ('app', 'alert_queue', 'alerta_fila_tenant_id_fkidx', 'alert_queue_tenant_id_fkidx'),
  ('app', 'cost_center', 'centro_custo_empresa_id_fkidx', 'cost_center_company_id_fkidx'),
  ('app', 'cost_center', 'centro_custo_pkey', 'cost_center_pkey'),
  ('app', 'cost_center', 'centro_custo_tenant_id_codigo_key', 'cost_center_tenant_id_code_key'),
  ('app', 'cost_center', 'centro_custo_unidade_idx', 'cost_center_unidade_idx'),
  ('app', 'report_cycle', 'ciclo_relatorio_pkey', 'report_cycle_pkey'),
  ('app', 'report_cycle', 'ciclo_relatorio_tenant_id_fkidx', 'report_cycle_tenant_id_fkidx'),
  ('app', 'report_cycle', 'ciclo_relatorio_unidade_idx', 'report_cycle_unidade_idx'),
  ('app', 'employee', 'colaborador_departamento_idx', 'employee_departamento_idx'),
  ('app', 'employee', 'colaborador_empresa_idx', 'employee_empresa_idx'),
  ('app', 'employee', 'colaborador_gestor_idx', 'employee_gestor_idx'),
  ('app', 'employee', 'colaborador_pkey', 'employee_pkey'),
  ('app', 'employee', 'colaborador_tenant_id_secullum_funcionario_id_key', 'employee_tenant_id_secullum_employee_id_key'),
  ('app', 'employee', 'colaborador_tenant_unidade_idx', 'employee_tenant_unidade_idx'),
  ('app', 'employee', 'colaborador_unidade_id_fkidx', 'employee_unit_id_fkidx'),
  ('app', 'employee_position', 'colaborador_funcao_pkey', 'employee_position_pkey'),
  ('app', 'employee_position', 'colaborador_funcao_tenant_id_fkidx', 'employee_position_tenant_id_fkidx'),
  ('app', 'employee_position', 'colaborador_funcao_unidade_id_fkidx', 'employee_position_unit_id_fkidx'),
  ('app', 'employee_position', 'funcao_colab_idx', 'responsibility_colab_idx'),
  ('app', 'employee_pii', 'colaborador_pii_pkey', 'employee_pii_pkey'),
  ('app', 'employee_pii', 'colaborador_pii_tenant_idx', 'employee_pii_tenant_idx'),
  ('app', 'employee_compensation', 'colaborador_remuneracao_pkey', 'employee_compensation_pkey'),
  ('app', 'employee_compensation', 'colaborador_remuneracao_registrado_por_fkidx', 'employee_compensation_recorded_by_fkidx'),
  ('app', 'employee_compensation', 'colaborador_remuneracao_tenant_id_fkidx', 'employee_compensation_tenant_id_fkidx'),
  ('app', 'payroll_period', 'competencia_pkey', 'payroll_period_pkey'),
  ('app', 'payroll_period', 'competencia_tenant_id_ano_mes_key', 'payroll_period_tenant_id_year_month_key'),
  ('app', 'ai_query', 'consulta_ia_pkey', 'ai_query_pkey'),
  ('app', 'ai_query', 'consulta_ia_tenant_idx', 'ai_query_tenant_idx'),
  ('app', 'ai_query', 'consulta_ia_user_id_fkidx', 'ai_query_user_id_fkidx'),
  ('app', 'contact', 'contato_pkey', 'contact_pkey'),
  ('app', 'contact', 'contato_tenant_idx', 'contact_tenant_idx'),
  ('app', 'department', 'departamento_empresa_idx', 'department_empresa_idx'),
  ('app', 'department', 'departamento_pkey', 'department_pkey'),
  ('app', 'department', 'departamento_tenant_id_secullum_departamento_id_key', 'department_tenant_id_secullum_department_id_key'),
  ('app', 'deviation_type', 'desvio_tipo_pkey', 'deviation_type_pkey'),
  ('app', 'deviation_type_config', 'desvio_tipo_config_codigo_fkidx', 'deviation_type_config_code_fkidx'),
  ('app', 'deviation_type_config', 'desvio_tipo_config_pkey', 'deviation_type_config_pkey'),
  ('app', 'detection_run', 'deteccao_execucao_pkey', 'detection_run_pkey'),
  ('app', 'detection_run', 'deteccao_execucao_tenant_idx', 'detection_run_tenant_idx'),
  ('app', 'deviation_event', 'deviation_event_empresa_id_fkidx', 'deviation_event_company_id_fkidx'),
  ('app', 'deviation_event', 'deviation_event_tipo_fkidx', 'deviation_event_type_fkidx'),
  ('app', 'deviation_event', 'deviation_event_unico_ativo', 'deviation_event_unico_active'),
  ('app', 'deviation_event', 'deviation_event_unidade_id_fkidx', 'deviation_event_unit_id_fkidx'),
  ('app', 'document', 'documento_colab_idx', 'document_colab_idx'),
  ('app', 'document', 'documento_criado_por_fkidx', 'document_created_by_fkidx'),
  ('app', 'document', 'documento_pkey', 'document_pkey'),
  ('app', 'document', 'documento_storage_bucket_storage_path_key', 'document_storage_bucket_storage_path_key'),
  ('app', 'document', 'documento_substitui_id_fkidx', 'document_replaces_id_fkidx'),
  ('app', 'document', 'documento_tipo_id_fkidx', 'document_type_id_fkidx'),
  ('app', 'document', 'documento_vencimento_idx', 'document_vencimento_idx'),
  ('app', 'document_type', 'documento_tipo_pkey', 'document_type_pkey'),
  ('app', 'document_type', 'documento_tipo_tenant_id_nome_key', 'document_type_tenant_id_name_key'),
  ('app', 'company', 'empresa_pkey', 'company_pkey'),
  ('app', 'company', 'empresa_tenant_id_cnpj_key', 'company_tenant_id_cnpj_key'),
  ('app', 'company', 'empresa_tenant_id_secullum_empresa_id_key', 'company_tenant_id_secullum_company_id_key'),
  ('app', 'company', 'empresa_tenant_idx', 'company_tenant_idx'),
  ('app', 'payroll_charge', 'encargo_comp_idx', 'payroll_charge_comp_idx'),
  ('app', 'payroll_charge', 'encargo_empresa_id_fkidx', 'payroll_charge_company_id_fkidx'),
  ('app', 'payroll_charge', 'encargo_pkey', 'payroll_charge_pkey'),
  ('app', 'payroll_charge', 'encargo_tenant_id_fkidx', 'payroll_charge_tenant_id_fkidx'),
  ('app', 'payroll_charge', 'encargo_unidade_id_fkidx', 'payroll_charge_unit_id_fkidx'),
  ('app', 'user_scope', 'escopo_usuario_empresa_idx', 'user_scope_empresa_idx'),
  ('app', 'user_scope', 'escopo_usuario_lookup_idx', 'user_scope_lookup_idx'),
  ('app', 'user_scope', 'escopo_usuario_pkey', 'user_scope_pkey'),
  ('app', 'user_scope', 'escopo_usuario_tenant_id_fkidx', 'user_scope_tenant_id_fkidx'),
  ('app', 'user_scope', 'escopo_usuario_unidade_idx', 'user_scope_unidade_idx'),
  ('app', 'occupational_exam', 'exame_ocupacional_criado_por_fkidx', 'occupational_exam_created_by_fkidx'),
  ('app', 'occupational_exam', 'exame_ocupacional_documento_id_fkidx', 'occupational_exam_document_id_fkidx'),
  ('app', 'occupational_exam', 'exame_ocupacional_pkey', 'occupational_exam_pkey'),
  ('app', 'payroll_entry', 'folha_evento_cc_idx', 'payroll_entry_cc_idx'),
  ('app', 'payroll_entry', 'folha_evento_colab_idx', 'payroll_entry_colab_idx'),
  ('app', 'payroll_entry', 'folha_evento_comp_idx', 'payroll_entry_comp_idx'),
  ('app', 'payroll_entry', 'folha_evento_empresa_id_fkidx', 'payroll_entry_company_id_fkidx'),
  ('app', 'payroll_entry', 'folha_evento_import_idx', 'payroll_entry_import_idx'),
  ('app', 'payroll_entry', 'folha_evento_pkey', 'payroll_entry_pkey'),
  ('app', 'payroll_entry', 'folha_evento_tenant_id_fkidx', 'payroll_entry_tenant_id_fkidx'),
  ('app', 'payroll_entry', 'folha_evento_unidade_idx', 'payroll_entry_unidade_idx'),
  ('app', 'file_import', 'importacao_arquivo_competencia_id_fkidx', 'file_import_payroll_period_id_fkidx'),
  ('app', 'file_import', 'importacao_arquivo_enviado_por_fkidx', 'file_import_uploaded_by_fkidx'),
  ('app', 'file_import', 'importacao_arquivo_pkey', 'file_import_pkey'),
  ('app', 'integration', 'integracao_pkey', 'integration_pkey'),
  ('app', 'integration', 'integracao_tenant_id_provedor_apelido_key', 'integration_tenant_id_provider_alias_key'),
  ('app', 'integration_secret', 'integracao_segredo_pkey', 'integration_secret_pkey'),
  ('app', 'expected_workday', 'jornada_dia_baixa_confianca_idx', 'expected_workday_baixa_confianca_idx'),
  ('app', 'expected_workday', 'jornada_dia_pkey', 'expected_workday_pkey'),
  ('app', 'expected_workday', 'jornada_dia_tenant_data_idx', 'expected_workday_tenant_data_idx'),
  ('app', 'justification', 'justificativa_autor_user_id_fkidx', 'justification_author_user_id_fkidx'),
  ('app', 'justification', 'justificativa_colab_idx', 'justification_colab_idx'),
  ('app', 'justification', 'justificativa_evento_idx', 'justification_evento_idx'),
  ('app', 'justification', 'justificativa_pkey', 'justification_pkey'),
  ('app', 'justification', 'justificativa_tenant_id_fkidx', 'justification_tenant_id_fkidx'),
  ('app', 'financial_threshold', 'limiar_financeiro_empresa_id_fkidx', 'financial_threshold_company_id_fkidx'),
  ('app', 'financial_threshold', 'limiar_financeiro_pkey', 'financial_threshold_pkey'),
  ('app', 'financial_threshold', 'limiar_financeiro_tenant_idx', 'financial_threshold_tenant_idx'),
  ('app', 'financial_threshold', 'limiar_financeiro_unidade_id_fkidx', 'financial_threshold_unit_id_fkidx'),
  ('app', 'metric', 'metrica_pkey', 'metric_pkey'),
  ('app', 'workforce_movement', 'movimentacao_pessoal_competencia_id_fkidx', 'workforce_movement_payroll_period_id_fkidx'),
  ('app', 'workforce_movement', 'movimentacao_pessoal_empresa_id_fkidx', 'workforce_movement_company_id_fkidx'),
  ('app', 'workforce_movement', 'movimentacao_pessoal_pkey', 'workforce_movement_pkey'),
  ('app', 'workforce_movement', 'movimentacao_pessoal_unidade_id_fkidx', 'workforce_movement_unit_id_fkidx'),
  ('app', 'domain_permission', 'permissao_dominio_pkey', 'domain_permission_pkey'),
  ('app', 'domain_permission', 'permissao_dominio_rls_idx', 'domain_permission_rls_idx'),
  ('app', 'alert_rule', 'regra_alerta_desvio_tipo_fkidx', 'alert_rule_deviation_type_fkidx'),
  ('app', 'alert_rule', 'regra_alerta_escopo_unidade_id_fkidx', 'alert_rule_scope_unit_id_fkidx'),
  ('app', 'alert_rule', 'regra_alerta_pkey', 'alert_rule_pkey'),
  ('app', 'alert_rule', 'regra_alerta_tenant_idx', 'alert_rule_tenant_idx'),
  ('app', 'alert_rule_target', 'regra_alerta_destino_contato_id_fkidx', 'alert_rule_target_contact_id_fkidx'),
  ('app', 'alert_rule_target', 'regra_alerta_destino_pkey', 'alert_rule_target_pkey'),
  ('app', 'sync_run', 'sync_execucao_falha_idx', 'sync_run_falha_idx'),
  ('app', 'sync_run', 'sync_execucao_idx', 'sync_run_idx'),
  ('app', 'sync_run', 'sync_execucao_pkey', 'sync_run_pkey'),
  ('app', 'tenant_member', 'tenant_membro_pkey', 'tenant_member_pkey'),
  ('app', 'tenant_member', 'tenant_membro_rls_idx', 'tenant_member_rls_idx'),
  ('app', 'tenant_member', 'tenant_membro_user_idx', 'tenant_member_user_idx'),
  ('app', 'unit', 'unidade_empresa_id_fkidx', 'unit_company_id_fkidx'),
  ('app', 'unit', 'unidade_pkey', 'unit_pkey'),
  ('app', 'unit', 'unidade_tenant_empresa_idx', 'unit_tenant_empresa_idx'),
  ('app', 'unit', 'unidade_tenant_id_codigo_key', 'unit_tenant_id_code_key'),
  ('app', 'unit_secullum_map', 'unidade_mapa_secullum_pkey', 'unit_secullum_map_pkey'),
  ('app', 'unit_secullum_map', 'unidade_mapa_secullum_validado_por_fkidx', 'unit_secullum_map_validated_by_fkidx'),
  ('app', 'unit_secullum_map', 'unidade_mapa_unidade_idx', 'unit_mapa_unidade_idx'),
  ('app', 'unit_responsible', 'unidade_responsavel_contato_id_fkidx', 'unit_responsible_contact_id_fkidx'),
  ('app', 'unit_responsible', 'unidade_responsavel_pkey', 'unit_responsible_pkey'),
  ('app', 'unit_responsible', 'unidade_responsavel_tenant_id_fkidx', 'unit_responsible_tenant_id_fkidx'),
  ('app', 'unit_responsible', 'unidade_responsavel_unidade_id_contato_id_funcao_key', 'unit_responsible_unit_id_contact_id_responsibility_key'),
  ('app', 'unit_responsible', 'unidade_responsavel_unidade_idx', 'unit_responsible_unidade_idx')
) as t(sch, tab, velho, novo)
  loop
    if to_regclass(format('%I.%I', r.sch, r.tab)) is null then
      continue;
    end if;
if to_regclass(format('%I.%I', r.sch, r.velho)) is not null
       and to_regclass(format('%I.%I', r.sch, r.novo)) is null then
      execute format('alter index %I.%I rename to %I', r.sch, r.velho, r.novo);
    end if;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 6. Policies
-- `alter policy ... rename` preserva o predicado. Derrubar e recriar exigiria
-- ler 57 predicados de produção e reescrevê-los — e mudar policy de RLS é uma
-- das três coisas que este projeto sempre para e pergunta.
-- ---------------------------------------------------------------------------
do $$
declare r record;
begin
  for r in
    select * from (values
  ('app', 'financial_agreement', 'acordo_escrita', 'acordo_write'),
  ('app', 'financial_agreement', 'acordo_leitura', 'acordo_read'),
  ('app', 'agreement_installment', 'parcela_escrita', 'parcela_write'),
  ('app', 'agreement_installment', 'parcela_leitura', 'parcela_read'),
  ('app', 'leave_period', 'afastamento_leitura', 'leave_period_read'),
  ('app', 'alert_sent', 'alerta_enviado_leitura', 'alert_sent_read'),
  ('app', 'alert_queue', 'alerta_fila_admin', 'alert_queue_admin'),
  ('app', 'audit_log', 'audit_leitura', 'audit_read'),
  ('app', 'cost_center', 'centro_custo_leitura', 'cost_center_read'),
  ('app', 'report_cycle', 'ciclo_leitura', 'ciclo_read'),
  ('app', 'employee', 'colaborador_escrita', 'employee_write'),
  ('app', 'employee', 'colaborador_leitura', 'employee_read'),
  ('app', 'employee_position', 'funcao_leitura', 'responsibility_read'),
  ('app', 'employee_pii', 'pii_escrita', 'pii_write'),
  ('app', 'employee_pii', 'pii_leitura', 'pii_read'),
  ('app', 'employee_compensation', 'remuneracao_escrita', 'remuneracao_write'),
  ('app', 'employee_compensation', 'remuneracao_leitura', 'remuneracao_read'),
  ('app', 'payroll_period', 'competencia_leitura', 'payroll_period_read'),
  ('app', 'ai_query', 'consulta_ia_leitura', 'ai_query_read'),
  ('app', 'contact', 'contato_admin', 'contact_admin'),
  ('app', 'contact', 'contato_leitura', 'contact_read'),
  ('app', 'department', 'departamento_leitura', 'department_read'),
  ('app', 'deviation_type', 'desvio_tipo_leitura', 'deviation_type_read'),
  ('app', 'deviation_type_config', 'desvio_config_leitura', 'desvio_config_read'),
  ('app', 'detection_run', 'deteccao_execucao_leitura', 'detection_run_read'),
  ('app', 'deviation_event', 'deviation_escrita', 'deviation_write'),
  ('app', 'deviation_event', 'deviation_leitura', 'deviation_read'),
  ('app', 'document', 'documento_escrita', 'document_write'),
  ('app', 'document', 'documento_leitura', 'document_read'),
  ('app', 'document_type', 'documento_tipo_admin', 'document_type_admin'),
  ('app', 'document_type', 'documento_tipo_leitura', 'document_type_read'),
  ('app', 'company', 'empresa_escrita', 'company_write'),
  ('app', 'company', 'empresa_leitura', 'company_read'),
  ('app', 'payroll_charge', 'encargo_leitura', 'payroll_charge_read'),
  ('app', 'user_scope', 'escopo_leitura', 'escopo_read'),
  ('app', 'occupational_exam', 'exame_escrita', 'exame_write'),
  ('app', 'occupational_exam', 'exame_leitura', 'exame_read'),
  ('app', 'payroll_entry', 'folha_evento_leitura', 'payroll_entry_read'),
  ('app', 'file_import', 'importacao_escrita', 'importacao_write'),
  ('app', 'file_import', 'importacao_leitura', 'importacao_read'),
  ('app', 'integration', 'integracao_admin', 'integration_admin'),
  ('app', 'expected_workday', 'jornada_dia_leitura', 'expected_workday_read'),
  ('app', 'justification', 'justificativa_escrita', 'justification_write'),
  ('app', 'justification', 'justificativa_leitura', 'justification_read'),
  ('app', 'metric', 'metrica_leitura', 'metric_read'),
  ('app', 'workforce_movement', 'movimentacao_leitura', 'movimentacao_read'),
  ('app', 'domain_permission', 'permissao_dominio_leitura', 'domain_permission_read'),
  ('app', 'alert_rule', 'regra_alerta_admin', 'alert_rule_admin'),
  ('app', 'alert_rule', 'regra_alerta_leitura', 'alert_rule_read'),
  ('app', 'sync_run', 'sync_leitura', 'sync_read'),
  ('app', 'tenant', 'tenant_leitura', 'tenant_read'),
  ('app', 'tenant_member', 'tenant_membro_admin', 'tenant_member_admin'),
  ('app', 'tenant_member', 'tenant_membro_leitura', 'tenant_member_read'),
  ('app', 'unit', 'unidade_escrita', 'unit_write'),
  ('app', 'unit', 'unidade_leitura', 'unit_read'),
  ('app', 'unit_responsible', 'unidade_responsavel_admin', 'unit_responsible_admin'),
  ('app', 'unit_responsible', 'unidade_responsavel_leitura', 'unit_responsible_read')
) as t(sch, tab, velho, novo)
  loop
    if to_regclass(format('%I.%I', r.sch, r.tab)) is null then
      continue;
    end if;
if exists (select 1 from pg_policy p
                join pg_class rel on rel.oid = p.polrelid
                join pg_namespace n on n.oid = rel.relnamespace
                where n.nspname = r.sch and rel.relname = r.tab and p.polname = r.velho)
       and not exists (select 1 from pg_policy p
                        join pg_class rel on rel.oid = p.polrelid
                        join pg_namespace n on n.oid = rel.relnamespace
                        where n.nspname = r.sch and rel.relname = r.tab and p.polname = r.novo) then
      execute format('alter policy %I on %I.%I rename to %I',
                     r.velho, r.sch, r.tab, r.novo);
    end if;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 7. Triggers
-- O trigger segue a tabela; só o nome precisa mudar.
-- ---------------------------------------------------------------------------
do $$
declare r record;
begin
  for r in
    select * from (values
  ('app', 'employee', 'trg_atualizado_em', 'trg_updated_at'),
  ('app', 'employee_pii', 'trg_atualizado_em', 'trg_updated_at'),
  ('app', 'deviation_event', 'trg_atualizado_em', 'trg_updated_at'),
  ('app', 'integration_secret', 'trg_atualizado_em', 'trg_updated_at'),
  ('app', 'alert_rule_target', 'trg_valida_destino_alerta', 'trg_validate_alert_target')
) as t(sch, tab, velho, novo)
  loop
    if to_regclass(format('%I.%I', r.sch, r.tab)) is null then
      continue;
    end if;
if exists (select 1 from pg_trigger t
                join pg_class rel on rel.oid = t.tgrelid
                join pg_namespace n on n.oid = rel.relnamespace
                where n.nspname = r.sch and rel.relname = r.tab and t.tgname = r.velho)
       and not exists (select 1 from pg_trigger t
                        join pg_class rel on rel.oid = t.tgrelid
                        join pg_namespace n on n.oid = rel.relnamespace
                        where n.nspname = r.sch and rel.relname = r.tab and t.tgname = r.novo) then
      execute format('alter trigger %I on %I.%I rename to %I',
                     r.velho, r.sch, r.tab, r.novo);
    end if;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 8. Views de public
-- A definição de uma view é parse tree, não texto: os renames dos blocos 2 e 3
-- já a atualizaram por dentro. Só o nome dela precisa mudar.
-- ---------------------------------------------------------------------------
do $$
declare r record;
begin
  for r in
    select * from (values
  ('public', 'vw_colaborador', 'vw_employee'),
  ('public', 'vw_desvio_evento', 'vw_deviation_event'),
  ('public', 'vw_desvio_por_colaborador_dia', 'vw_deviation_by_employee_day'),
  ('public', 'vw_desvio_resumo_unidade', 'vw_deviation_summary_by_unit'),
  ('public', 'vw_desvio_tendencia_diaria', 'vw_deviation_daily_trend'),
  ('public', 'vw_documento_vencimento', 'vw_document_expiry'),
  ('public', 'vw_folha_resumo', 'vw_payroll_summary'),
  ('public', 'vw_unidade', 'vw_unit')
) as t(sch, velho, novo)
  loop
    if to_regclass(format('%I.%I', r.sch, r.velho)) is not null
       and to_regclass(format('%I.%I', r.sch, r.novo)) is null then
      execute format('alter view %I.%I rename to %I', r.sch, r.velho, r.novo);
    end if;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 8b. Colunas de saída das views
-- O corpo de uma view segue o rename sozinho (é parse tree), mas o NOME das
-- colunas que ela entrega, não: `select c.nome as colaborador_nome` guarda o
-- alias como texto. Sem este bloco a view renomeada continuaria devolvendo
-- `colaborador_id` — e é por esse nome que o frontend lê o resultado.
-- ---------------------------------------------------------------------------
do $$
declare r record;
begin
  for r in
    select * from (values
  ('public', 'vw_employee', 'colaborador_id', 'employee_id', 'v'),
  ('public', 'vw_employee', 'empresa_id', 'company_id', 'v'),
  ('public', 'vw_employee', 'unidade_id', 'unit_id', 'v'),
  ('public', 'vw_employee', 'nome', 'name', 'v'),
  ('public', 'vw_employee', 'matricula', 'registration_number', 'v'),
  ('public', 'vw_employee', 'data_admissao', 'hired_on', 'v'),
  ('public', 'vw_employee', 'unidade_nome', 'unit_name', 'v'),
  ('public', 'vw_employee', 'empresa_nome', 'company_name', 'v'),
  ('public', 'vw_employee', 'gestor_nome', 'gestor_name', 'v'),
  ('public', 'vw_deviation_event', 'data_ref', 'reference_date', 'v'),
  ('public', 'vw_deviation_event', 'empresa_id', 'company_id', 'v'),
  ('public', 'vw_deviation_event', 'unidade_id', 'unit_id', 'v'),
  ('public', 'vw_deviation_event', 'unidade_nome', 'unit_name', 'v'),
  ('public', 'vw_deviation_event', 'colaborador_id', 'employee_id', 'v'),
  ('public', 'vw_deviation_event', 'colaborador_nome', 'employee_name', 'v'),
  ('public', 'vw_deviation_event', 'tipo', 'type', 'v'),
  ('public', 'vw_deviation_event', 'tipo_descricao', 'type_description', 'v'),
  ('public', 'vw_deviation_event', 'direcao', 'direction', 'v'),
  ('public', 'vw_deviation_event', 'categoria', 'category', 'v'),
  ('public', 'vw_deviation_event', 'minutos', 'minutes', 'v'),
  ('public', 'vw_deviation_event', 'minutos_abs', 'minutes_abs', 'v'),
  ('public', 'vw_deviation_event', 'horario_previsto', 'expected_time', 'v'),
  ('public', 'vw_deviation_event', 'horario_realizado', 'actual_time', 'v'),
  ('public', 'vw_deviation_event', 'ciclo_relatorio_id', 'report_cycle_id', 'v'),
  ('public', 'vw_deviation_event', 'detectado_em', 'detected_at', 'v'),
  ('public', 'vw_deviation_event', 'conta_como_desvio', 'counts_as_deviation', 'v'),
  ('public', 'vw_deviation_by_employee_day', 'data_ref', 'reference_date', 'v'),
  ('public', 'vw_deviation_by_employee_day', 'colaborador_id', 'employee_id', 'v'),
  ('public', 'vw_deviation_by_employee_day', 'colaborador_nome', 'employee_name', 'v'),
  ('public', 'vw_deviation_by_employee_day', 'unidade_id', 'unit_id', 'v'),
  ('public', 'vw_deviation_by_employee_day', 'unidade_nome', 'unit_name', 'v'),
  ('public', 'vw_deviation_by_employee_day', 'minutos_abs', 'minutes_abs', 'v'),
  ('public', 'vw_deviation_summary_by_unit', 'data_ref', 'reference_date', 'v'),
  ('public', 'vw_deviation_summary_by_unit', 'unidade_id', 'unit_id', 'v'),
  ('public', 'vw_deviation_summary_by_unit', 'unidade_nome', 'unit_name', 'v'),
  ('public', 'vw_deviation_summary_by_unit', 'empresa_id', 'company_id', 'v'),
  ('public', 'vw_deviation_summary_by_unit', 'minutos_excedente', 'minutes_excedente', 'v'),
  ('public', 'vw_deviation_summary_by_unit', 'minutos_faltante', 'minutes_faltante', 'v'),
  ('public', 'vw_deviation_summary_by_unit', 'minutos_abs', 'minutes_abs', 'v'),
  ('public', 'vw_deviation_daily_trend', 'data_ref', 'reference_date', 'v'),
  ('public', 'vw_deviation_daily_trend', 'unidade_id', 'unit_id', 'v'),
  ('public', 'vw_deviation_daily_trend', 'direcao', 'direction', 'v'),
  ('public', 'vw_deviation_daily_trend', 'minutos_abs', 'minutes_abs', 'v'),
  ('public', 'vw_document_expiry', 'documento_id', 'document_id', 'v'),
  ('public', 'vw_document_expiry', 'colaborador_id', 'employee_id', 'v'),
  ('public', 'vw_document_expiry', 'colaborador_nome', 'employee_name', 'v'),
  ('public', 'vw_document_expiry', 'unidade_id', 'unit_id', 'v'),
  ('public', 'vw_document_expiry', 'tipo_nome', 'type_name', 'v'),
  ('public', 'vw_document_expiry', 'valido_ate', 'valid_until', 'v'),
  ('public', 'vw_document_expiry', 'dias_alerta_vencimento', 'expiry_alert_days', 'v'),
  ('public', 'vw_payroll_summary', 'ano', 'year', 'v'),
  ('public', 'vw_payroll_summary', 'mes', 'month', 'v'),
  ('public', 'vw_payroll_summary', 'empresa_id', 'company_id', 'v'),
  ('public', 'vw_payroll_summary', 'unidade_id', 'unit_id', 'v'),
  ('public', 'vw_unit', 'unidade_id', 'unit_id', 'v'),
  ('public', 'vw_unit', 'empresa_id', 'company_id', 'v'),
  ('public', 'vw_unit', 'empresa_nome', 'company_name', 'v'),
  ('public', 'vw_unit', 'codigo', 'code', 'v'),
  ('public', 'vw_unit', 'nome', 'name', 'v'),
  ('public', 'vw_unit', 'ativo', 'active', 'v')
) as t(sch, obj, velho, novo, kind)
  loop
    if to_regclass(format('%I.%I', r.sch, r.obj)) is not null
       and exists (select 1 from information_schema.columns
                    where table_schema = r.sch and table_name = r.obj and column_name = r.velho)
       and not exists (select 1 from information_schema.columns
                        where table_schema = r.sch and table_name = r.obj and column_name = r.novo) then
      if r.kind = 'm' then
        execute format('alter materialized view %I.%I rename column %I to %I',
                       r.sch, r.obj, r.velho, r.novo);
      else
        execute format('alter view %I.%I rename column %I to %I',
                       r.sch, r.obj, r.velho, r.novo);
      end if;
    end if;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 8c. Corpo das views que filtram por VALOR
-- Seis views de public filtram `status = 'ativo'` ou `modo = 'producao'`. O
-- corpo segue o rename de identificador sozinho, porque é parse tree — mas o
-- literal dentro dele é dado, não identificador, e não segue. Depois do bloco
-- 11 essas views devolveriam ZERO linha, filtrando por um valor que não existe
-- mais. Não dá erro; dá tela vazia.
--
-- `create or replace view` não renomeia coluna, e é por isso que o 8b vem
-- antes: aqui só o corpo é trocado, pela definição deste repositório.
-- ---------------------------------------------------------------------------
do $$
begin
  if to_regclass('public.vw_deviation_event') is not null then
    execute $vw$create or replace view public.vw_deviation_event with (security_invoker=on) as
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
  WHERE d.status = 'active'::text AND d.mode = 'production'::text$vw$;
  end if;
end $$;
do $$
begin
  if to_regclass('public.vw_deviation_by_employee_day') is not null then
    execute $vw$create or replace view public.vw_deviation_by_employee_day with (security_invoker=on) as
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
  GROUP BY d.tenant_id, d.reference_date, d.employee_id, c.name, d.unit_id, u.name$vw$;
  end if;
end $$;
do $$
begin
  if to_regclass('public.vw_deviation_summary_by_unit') is not null then
    execute $vw$create or replace view public.vw_deviation_summary_by_unit with (security_invoker=on) as
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
  GROUP BY d.tenant_id, d.reference_date, d.unit_id, u.name, d.company_id$vw$;
  end if;
end $$;
do $$
begin
  if to_regclass('public.vw_deviation_daily_trend') is not null then
    execute $vw$create or replace view public.vw_deviation_daily_trend with (security_invoker=on) as
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
  GROUP BY d.tenant_id, d.reference_date, d.unit_id, t.direction$vw$;
  end if;
end $$;
do $$
begin
  if to_regclass('public.vw_document_expiry') is not null then
    execute $vw$create or replace view public.vw_document_expiry with (security_invoker=on) as
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
  WHERE doc.status = 'active'::text AND doc.valid_until IS NOT NULL$vw$;
  end if;
end $$;
do $$
begin
  if to_regclass('public.vw_payroll_summary') is not null then
    execute $vw$create or replace view public.vw_payroll_summary with (security_invoker=on) as
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
  GROUP BY f.tenant_id, comp.year, comp.month, f.company_id, f.unit_id$vw$;
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 9. Funções
-- Aqui rename não basta. O corpo de uma função `language sql` declarada com
-- `as $$ ... $$` é TEXTO, e todas estas rodam com `search_path = ''`, então
-- citam `app.unidade` por extenso. Renomear a tabela não mexe no corpo: a
-- função continua apontando para um nome que não existe mais.
--
-- Renomeia-se primeiro (o OID é preservado, então as 57 policies que chamam
-- estes helpers continuam apontando para eles) e em seguida o corpo é
-- substituído pela definição em inglês. `create or replace` com a mesma
-- assinatura também preserva o OID.
-- ---------------------------------------------------------------------------
do $$
declare
  r record;
  v_sig text;
begin
  for r in
    select * from (values
  ('app', 'revogar_desvio', 'p_id uuid, p_motivo text, p_novo_status text', 'revoke_deviation', 3),
  ('public', 'fn_kpi_periodo', 'p_de date, p_ate date, p_empresa_id uuid, p_unidade_id uuid', 'fn_kpi_period', 4),
  ('public', 'fn_ranking_colaborador', 'p_de date, p_ate date, p_empresa_id uuid, p_unidade_id uuid, p_limite integer', 'fn_ranking_by_employee', 5),
  ('public', 'fn_ranking_unidade', 'p_de date, p_ate date, p_empresa_id uuid, p_limite integer', 'fn_ranking_by_unit', 4),
  ('public', 'fn_recorrencia', 'p_de date, p_ate date, p_min_dias integer, p_unidade_id uuid', 'fn_recurrence', 4),
  ('util', 'bloqueia_tabela_em_public', '', 'block_table_in_public', 0),
  ('util', 'eh_admin', 'p_tenant_id uuid', 'is_admin', 1),
  ('util', 'papeis_no_tenant', 'p_tenant_id uuid', 'roles_in_tenant', 1),
  ('util', 'pode_ver_colaborador', 'p_colaborador_id uuid', 'can_see_employee', 1),
  ('util', 'pode_ver_dominio', 'p_tenant_id uuid, p_dominio app.dominio_sensivel', 'can_see_domain', 2),
  ('util', 'pode_ver_empresa', 'p_empresa_id uuid', 'can_see_company', 1),
  ('util', 'pode_ver_unidade', 'p_unidade_id uuid', 'can_see_unit', 1),
  ('util', 'tem_tenant', 'p_tenant_id uuid', 'has_tenant', 1),
  ('util', 'tenants_do_usuario', '', 'user_tenants', 0),
  ('util', 'toca_atualizado_em', '', 'touch_updated_at', 0),
  ('util', 'valida_destino_alerta', '', 'validate_alert_target', 0)
) as t(sch, velho, args, novo, aridade)
  loop
    -- A assinatura é lida do catálogo pelo OID (`::regprocedure`), não montada a
    -- partir do que produção tinha: o tipo do parâmetro de `pode_ver_dominio` já
    -- foi renomeado no bloco 1 (app.dominio_sensivel -> app.sensitive_domain), e
    -- a assinatura literal antiga não existe mais para ser citada.
    if not exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                    where n.nspname = r.sch and p.proname = r.novo) then
      for v_sig in
        select p.oid::regprocedure::text
        from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = r.sch and p.proname = r.velho
          and p.pronargs = r.aridade
      loop
        execute format('alter function %s rename to %I', v_sig, r.novo);
      end loop;
    end if;
  end loop;
end $$;

-- Corpos em inglês.
--
-- `create or replace` NÃO consegue trocar o nome de um parâmetro
-- ("cannot change name of input parameter"), e nove funções trocam. Cinco delas
-- podem ser derrubadas e recriadas — nada depende delas. As outras quatro são os
-- helpers `util.pode_ver_*`, e o Postgres recusa derrubá-las: 57 policies as
-- citam no predicado. Para essas, o corpo novo entra com o nome de parâmetro
-- ANTIGO, porque policy chama por posição e o nome do parâmetro de um helper
-- `security definer` não é visto por ninguém. Fica registrado como divergência
-- deliberada em docs/PLANO-RECONCILIACAO-NUVEM.md.
--
-- Num banco que já está em inglês tudo isto redefine cada função com
-- exatamente o que ela já era.
CREATE OR REPLACE FUNCTION app.refresh_dashboard()
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
  refresh materialized view concurrently app.mv_deviation_day;
end $function$;
drop function if exists app.revoke_deviation(p_id uuid, p_motivo text, p_novo_status text);
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
drop function if exists public.fn_kpi_period(p_de date, p_ate date, p_empresa_id uuid, p_unidade_id uuid);
CREATE OR REPLACE FUNCTION public.fn_kpi_period(p_de date, p_ate date, p_company_id uuid DEFAULT NULL::uuid, p_unit_id uuid DEFAULT NULL::uuid)
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
  join app.deviation_type_config cfg
   on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  where d.status = 'active' and d.mode = 'production'
and d.reference_date between p_de and p_ate
and (p_company_id is null or d.company_id = p_company_id)
and (p_unit_id is null or d.unit_id = p_unit_id);
$function$;
drop function if exists public.fn_ranking_by_employee(p_de date, p_ate date, p_empresa_id uuid, p_unidade_id uuid, p_limite integer);
CREATE OR REPLACE FUNCTION public.fn_ranking_by_employee(p_de date, p_ate date, p_company_id uuid DEFAULT NULL::uuid, p_unit_id uuid DEFAULT NULL::uuid, p_limite integer DEFAULT 20)
 RETURNS TABLE(employee_id uuid, employee_name text, unit_name text, eventos bigint, minutes_abs bigint)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  select d.employee_id, c.name, u.name, count(*), coalesce(sum(abs(d.minutes)),0)
  from app.deviation_event d
  join app.employee c on c.id = d.employee_id
  join app.deviation_type_config cfg
   on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  left join app.unit u on u.id = d.unit_id
  where d.status = 'active' and d.mode = 'production'
and d.reference_date between p_de and p_ate
and (p_company_id is null or d.company_id = p_company_id)
and (p_unit_id is null or d.unit_id = p_unit_id)
  group by d.employee_id, c.name, u.name
  order by count(*) desc
  limit greatest(p_limite, 1);
$function$;
drop function if exists public.fn_ranking_by_unit(p_de date, p_ate date, p_empresa_id uuid, p_limite integer);
CREATE OR REPLACE FUNCTION public.fn_ranking_by_unit(p_de date, p_ate date, p_company_id uuid DEFAULT NULL::uuid, p_limite integer DEFAULT 20)
 RETURNS TABLE(unit_id uuid, unit_name text, eventos bigint, minutes_abs bigint, colaboradores bigint)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  select d.unit_id, u.name, count(*), coalesce(sum(abs(d.minutes)),0), count(distinct d.employee_id)
  from app.deviation_event d
  join app.deviation_type_config cfg
   on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  left join app.unit u on u.id = d.unit_id
  where d.status = 'active' and d.mode = 'production'
and d.reference_date between p_de and p_ate
and (p_company_id is null or d.company_id = p_company_id)
  group by d.unit_id, u.name
  order by count(*) desc
  limit greatest(p_limite, 1);
$function$;
drop function if exists public.fn_recurrence(p_de date, p_ate date, p_min_dias integer, p_unidade_id uuid);
CREATE OR REPLACE FUNCTION public.fn_recurrence(p_de date, p_ate date, p_min_dias integer DEFAULT 3, p_unit_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(employee_id uuid, employee_name text, unit_name text, dias_com_desvio bigint, eventos bigint)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  select d.employee_id, c.name, u.name,
     count(distinct d.reference_date), count(*)
  from app.deviation_event d
  join app.employee c on c.id = d.employee_id
  join app.deviation_type_config cfg
   on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  left join app.unit u on u.id = d.unit_id
  where d.status = 'active' and d.mode = 'production'
and d.reference_date between p_de and p_ate
and (p_unit_id is null or d.unit_id = p_unit_id)
  group by d.employee_id, c.name, u.name
  having count(distinct d.reference_date) >= greatest(p_min_dias, 1)
  order by count(distinct d.reference_date) desc;
$function$;
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
do $$
begin
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'util' and p.proname = 'can_see_employee'
                and pg_get_function_identity_arguments(p.oid) = 'p_colaborador_id uuid') then
    execute $fn$CREATE OR REPLACE FUNCTION util.can_see_employee(p_colaborador_id uuid)
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
$function$
$fn$;
  else
    execute $fn$CREATE OR REPLACE FUNCTION util.can_see_employee(p_employee_id uuid)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select exists (
select 1 from app.employee c
where c.id = p_employee_id
  and (
    util.is_admin(c.tenant_id)
    or (c.unit_id is not null and util.can_see_unit(c.unit_id))
    or (c.unit_id is null    and util.can_see_company(c.company_id))
  )
  );
$function$
$fn$;
  end if;
end $$;
do $$
begin
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'util' and p.proname = 'can_see_domain'
                and pg_get_function_identity_arguments(p.oid) = 'p_tenant_id uuid, p_dominio app.sensitive_domain') then
    execute $fn$CREATE OR REPLACE FUNCTION util.can_see_domain(p_tenant_id uuid, p_dominio app.sensitive_domain)
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
$function$
$fn$;
  else
    execute $fn$CREATE OR REPLACE FUNCTION util.can_see_domain(p_tenant_id uuid, p_domain app.sensitive_domain)
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
 and pd.domain   = p_domain
 and pd.allowed
where tm.tenant_id = p_tenant_id
  and tm.user_id = (select auth.uid())
  and tm.active
  );
$function$
$fn$;
  end if;
end $$;
do $$
begin
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'util' and p.proname = 'can_see_company'
                and pg_get_function_identity_arguments(p.oid) = 'p_empresa_id uuid') then
    execute $fn$CREATE OR REPLACE FUNCTION util.can_see_company(p_empresa_id uuid)
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
$function$
$fn$;
  else
    execute $fn$CREATE OR REPLACE FUNCTION util.can_see_company(p_company_id uuid)
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
where emp.id = p_company_id
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
$function$
$fn$;
  end if;
end $$;
do $$
begin
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'util' and p.proname = 'can_see_unit'
                and pg_get_function_identity_arguments(p.oid) = 'p_unidade_id uuid') then
    execute $fn$CREATE OR REPLACE FUNCTION util.can_see_unit(p_unidade_id uuid)
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
$function$
$fn$;
  else
    execute $fn$CREATE OR REPLACE FUNCTION util.can_see_unit(p_unit_id uuid)
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
where u.id = p_unit_id
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
$function$
$fn$;
  end if;
end $$;
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
CREATE OR REPLACE FUNCTION util.touch_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  new.updated_at := now();
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

-- ---------------------------------------------------------------------------
-- 10a. Derruba as check constraints que carregam VALOR
-- Trinta e nove das setenta e cinco checks de `app` não mudam só de nome: elas
-- listam os valores aceitos, e esses valores estão em português. Renomear
-- `desvio_tipo_direcao_check` para `deviation_type_direction_check` deixa uma
-- constraint que continua exigindo 'excedente' — e o update do bloco 11, que
-- grava 'surplus', bate nela.
--
-- Elas caem aqui e voltam no bloco 12, depois de o dado estar traduzido. Entre
-- os dois blocos a tabela fica sem essa checagem; é o único jeito, porque
-- `add constraint ... check` valida as linhas existentes na hora.
-- ---------------------------------------------------------------------------
do $$
declare r record;
begin
  for r in
    select * from (values
  ('app', 'financial_agreement', 'acordo_financeiro_status_check'),
  ('app', 'financial_agreement', 'acordo_financeiro_tipo_check'),
  ('app', 'agreement_installment', 'acordo_parcela_status_check'),
  ('app', 'leave_period', 'afastamento_categoria_check'),
  ('app', 'leave_period', 'afastamento_origem_check'),
  ('app', 'alert_sent', 'alerta_enviado_status_check'),
  ('app', 'alert_queue', 'alerta_fila_status_check'),
  ('app', 'audit_log', 'audit_log_acao_check'),
  ('app', 'report_cycle', 'ciclo_relatorio_canal_check'),
  ('app', 'report_cycle', 'ciclo_relatorio_status_check'),
  ('app', 'employee', 'colaborador_status_check'),
  ('app', 'employee', 'colaborador_tipo_contratacao_check'),
  ('app', 'contact', 'contato_tipo_check'),
  ('app', 'deviation_type', 'desvio_tipo_categoria_check'),
  ('app', 'deviation_type', 'desvio_tipo_direcao_check'),
  ('app', 'detection_run', 'deteccao_execucao_modo_check'),
  ('app', 'detection_run', 'deteccao_execucao_status_check'),
  ('app', 'deviation_event', 'deviation_event_modo_check'),
  ('app', 'deviation_event', 'deviation_event_status_check'),
  ('app', 'payroll_charge', 'encargo_tipo_check'),
  ('app', 'occupational_exam', 'exame_ocupacional_resultado_check'),
  ('app', 'occupational_exam', 'exame_ocupacional_tipo_check'),
  ('app', 'payroll_entry', 'folha_evento_natureza_check'),
  ('app', 'file_import', 'importacao_arquivo_status_check'),
  ('app', 'file_import', 'importacao_arquivo_tipo_check'),
  ('app', 'expected_workday', 'jornada_dia_origem_check'),
  ('app', 'expected_workday', 'jornada_dia_tipo_dia_check'),
  ('app', 'financial_threshold', 'limiar_financeiro_indicador_check'),
  ('app', 'financial_threshold', 'limiar_financeiro_operador_check'),
  ('app', 'workforce_movement', 'movimentacao_pessoal_tipo_check'),
  ('app', 'alert_rule', 'regra_alerta_canal_check'),
  ('app', 'alert_rule', 'regra_alerta_conteudo_check'),
  ('app', 'alert_rule_target', 'regra_alerta_destino_funcao_check'),
  ('app', 'sync_run', 'sync_execucao_status_check'),
  ('app', 'unit_responsible', 'unidade_responsavel_funcao_check'),
  ('app', 'financial_agreement', 'acordo_financeiro_qtd_parcelas_check'),
  ('app', 'financial_agreement', 'acordo_financeiro_valor_total_check'),
  ('app', 'agreement_installment', 'acordo_parcela_competencia_mes_check'),
  ('app', 'agreement_installment', 'acordo_parcela_numero_check'),
  ('app', 'agreement_installment', 'acordo_parcela_valor_check'),
  ('app', 'leave_period', 'afastamento_check'),
  ('app', 'alert_sent', 'alerta_enviado_provedor_check'),
  ('app', 'alert_queue', 'alerta_fila_canal_check'),
  ('app', 'report_cycle', 'ciclo_relatorio_check'),
  ('app', 'employee', 'colaborador_check'),
  ('app', 'employee_compensation', 'colaborador_remuneracao_check'),
  ('app', 'employee_compensation', 'colaborador_remuneracao_salario_check'),
  ('app', 'payroll_period', 'competencia_ano_check'),
  ('app', 'payroll_period', 'competencia_mes_check'),
  ('app', 'payroll_period', 'competencia_status_check'),
  ('app', 'contact', 'contato_whatsapp_check'),
  ('app', 'document', 'documento_status_check'),
  ('app', 'company', 'empresa_cnpj_check'),
  ('app', 'payroll_charge', 'encargo_origem_check'),
  ('app', 'payroll_entry', 'folha_evento_origem_check'),
  ('app', 'integration', 'integracao_provedor_check'),
  ('app', 'expected_workday', 'jornada_dia_confianca_check'),
  ('app', 'justification', 'justificativa_origem_check'),
  ('app', 'alert_rule_target', 'regra_alerta_destino_check')
) as t(sch, tab, velho)
  loop
    if to_regclass(format('%I.%I', r.sch, r.tab)) is not null
       and exists (select 1 from pg_constraint c
                    join pg_class rel on rel.oid = c.conrelid
                    join pg_namespace n on n.oid = rel.relnamespace
                    where n.nspname = r.sch and rel.relname = r.tab and c.conname = r.velho) then
      execute format('alter table %I.%I drop constraint %I', r.sch, r.tab, r.velho);
    end if;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 10b. Defaults de coluna que carregam valor
-- `status text default 'ativo'` continua gravando 'ativo' depois do rename, e a
-- check já refeita no bloco 10 recusaria a linha. O default vem do alvo.
-- ---------------------------------------------------------------------------
do $$
begin
  if to_regclass('app.financial_agreement') is not null
     and exists (select 1 from information_schema.columns
                  where table_schema = 'app' and table_name = 'financial_agreement'
                    and column_name = 'status') then
    execute $sql$alter table app.financial_agreement alter column status set default 'active'::text$sql$;
  end if;
  if to_regclass('app.agreement_installment') is not null
     and exists (select 1 from information_schema.columns
                  where table_schema = 'app' and table_name = 'agreement_installment'
                    and column_name = 'status') then
    execute $sql$alter table app.agreement_installment alter column status set default 'pending'::text$sql$;
  end if;
  if to_regclass('app.alert_queue') is not null
     and exists (select 1 from information_schema.columns
                  where table_schema = 'app' and table_name = 'alert_queue'
                    and column_name = 'status') then
    execute $sql$alter table app.alert_queue alter column status set default 'pending'::text$sql$;
  end if;
  if to_regclass('app.report_cycle') is not null
     and exists (select 1 from information_schema.columns
                  where table_schema = 'app' and table_name = 'report_cycle'
                    and column_name = 'status') then
    execute $sql$alter table app.report_cycle alter column status set default 'open'::text$sql$;
  end if;
  if to_regclass('app.employee') is not null
     and exists (select 1 from information_schema.columns
                  where table_schema = 'app' and table_name = 'employee'
                    and column_name = 'status') then
    execute $sql$alter table app.employee alter column status set default 'active'::text$sql$;
  end if;
  if to_regclass('app.contact') is not null
     and exists (select 1 from information_schema.columns
                  where table_schema = 'app' and table_name = 'contact'
                    and column_name = 'type') then
    execute $sql$alter table app.contact alter column type set default 'person'::text$sql$;
  end if;
  if to_regclass('app.detection_run') is not null
     and exists (select 1 from information_schema.columns
                  where table_schema = 'app' and table_name = 'detection_run'
                    and column_name = 'status') then
    execute $sql$alter table app.detection_run alter column status set default 'running'::text$sql$;
  end if;
  if to_regclass('app.deviation_event') is not null
     and exists (select 1 from information_schema.columns
                  where table_schema = 'app' and table_name = 'deviation_event'
                    and column_name = 'mode') then
    execute $sql$alter table app.deviation_event alter column mode set default 'production'::text$sql$;
  end if;
  if to_regclass('app.deviation_event') is not null
     and exists (select 1 from information_schema.columns
                  where table_schema = 'app' and table_name = 'deviation_event'
                    and column_name = 'status') then
    execute $sql$alter table app.deviation_event alter column status set default 'active'::text$sql$;
  end if;
  if to_regclass('app.document') is not null
     and exists (select 1 from information_schema.columns
                  where table_schema = 'app' and table_name = 'document'
                    and column_name = 'status') then
    execute $sql$alter table app.document alter column status set default 'active'::text$sql$;
  end if;
  if to_regclass('app.file_import') is not null
     and exists (select 1 from information_schema.columns
                  where table_schema = 'app' and table_name = 'file_import'
                    and column_name = 'status') then
    execute $sql$alter table app.file_import alter column status set default 'received'::text$sql$;
  end if;
  if to_regclass('app.alert_rule') is not null
     and exists (select 1 from information_schema.columns
                  where table_schema = 'app' and table_name = 'alert_rule'
                    and column_name = 'content') then
    execute $sql$alter table app.alert_rule alter column content set default 'aggregate'::text$sql$;
  end if;
  if to_regclass('app.sync_run') is not null
     and exists (select 1 from information_schema.columns
                  where table_schema = 'app' and table_name = 'sync_run'
                    and column_name = 'status') then
    execute $sql$alter table app.sync_run alter column status set default 'running'::text$sql$;
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 11. Valores de dado no catálogo
-- Rename de identificador não alcança o conteúdo das linhas. `deviation_type`
-- guarda 'entrada_atrasada' onde este repositório guarda 'late_entry', e o
-- código é chave primária referenciada por três FKs sem `on update cascade`.
--
-- Por isso a ordem é insere-novo → reaponta filho → apaga-velho, em vez de
-- `update`: nenhuma constraint precisa ser derrubada, e em nenhum instante uma
-- linha filha aponta para um código que não existe.
--
-- As direções e categorias são colunas comuns e vão por `update` direto.
-- ---------------------------------------------------------------------------
do $$
begin
  if to_regclass('app.deviation_type') is null then
    return;
  end if;

  insert into app.deviation_type (code, description, direction, category)
  select v.novo, t.description, t.direction, t.category
  from app.deviation_type t
  join (values
      ('batida_em_folga', 'punch_on_day_off'),
      ('entrada_adiantada', 'early_entry'),
      ('entrada_atrasada', 'late_entry'),
      ('fora_perimetro', 'outside_perimeter'),
      ('intervalo_excedido', 'break_exceeded'),
      ('intervalo_insuficiente', 'break_too_short'),
      ('intervalo_sem_retorno', 'break_no_return'),
      ('jornada_excedida', 'workday_exceeded'),
      ('marcacao_incompleta', 'incomplete_punches'),
      ('saida_antecipada', 'early_exit'),
      ('saida_postergada', 'late_exit'),
      ('sem_marcacao', 'no_punches')
   ) as v(velho, novo) on v.velho = t.code
  where not exists (select 1 from app.deviation_type x where x.code = v.novo);

  update app.deviation_type_config c set code = v.novo
    from (values
       ('batida_em_folga', 'punch_on_day_off'),
       ('entrada_adiantada', 'early_entry'),
       ('entrada_atrasada', 'late_entry'),
       ('fora_perimetro', 'outside_perimeter'),
       ('intervalo_excedido', 'break_exceeded'),
       ('intervalo_insuficiente', 'break_too_short'),
       ('intervalo_sem_retorno', 'break_no_return'),
       ('jornada_excedida', 'workday_exceeded'),
       ('marcacao_incompleta', 'incomplete_punches'),
       ('saida_antecipada', 'early_exit'),
       ('saida_postergada', 'late_exit'),
       ('sem_marcacao', 'no_punches')
     ) as v(velho, novo) where c.code = v.velho;

  update app.deviation_event d set type = v.novo
    from (values
       ('batida_em_folga', 'punch_on_day_off'),
       ('entrada_adiantada', 'early_entry'),
       ('entrada_atrasada', 'late_entry'),
       ('fora_perimetro', 'outside_perimeter'),
       ('intervalo_excedido', 'break_exceeded'),
       ('intervalo_insuficiente', 'break_too_short'),
       ('intervalo_sem_retorno', 'break_no_return'),
       ('jornada_excedida', 'workday_exceeded'),
       ('marcacao_incompleta', 'incomplete_punches'),
       ('saida_antecipada', 'early_exit'),
       ('saida_postergada', 'late_exit'),
       ('sem_marcacao', 'no_punches')
     ) as v(velho, novo) where d.type = v.velho;

  update app.alert_rule a set deviation_type = v.novo
    from (values
       ('batida_em_folga', 'punch_on_day_off'),
       ('entrada_adiantada', 'early_entry'),
       ('entrada_atrasada', 'late_entry'),
       ('fora_perimetro', 'outside_perimeter'),
       ('intervalo_excedido', 'break_exceeded'),
       ('intervalo_insuficiente', 'break_too_short'),
       ('intervalo_sem_retorno', 'break_no_return'),
       ('jornada_excedida', 'workday_exceeded'),
       ('marcacao_incompleta', 'incomplete_punches'),
       ('saida_antecipada', 'early_exit'),
       ('saida_postergada', 'late_exit'),
       ('sem_marcacao', 'no_punches')
     ) as v(velho, novo) where a.deviation_type = v.velho;

  delete from app.deviation_type where code in (
'batida_em_folga', 'entrada_adiantada', 'entrada_atrasada', 'fora_perimetro', 'intervalo_excedido', 'intervalo_insuficiente', 'intervalo_sem_retorno', 'jornada_excedida', 'marcacao_incompleta', 'saida_antecipada', 'saida_postergada', 'sem_marcacao'
  );
  update app.deviation_type set direction = 'surplus' where direction = 'excedente';
  update app.deviation_type set direction = 'shortfall' where direction = 'faltante';
  update app.deviation_type set direction = 'neutral' where direction = 'neutro';
  update app.deviation_type set category = 'entry' where category = 'entrada';
  update app.deviation_type set category = 'roster' where category = 'escala';
  update app.deviation_type set category = 'integrity' where category = 'integridade';
  update app.deviation_type set category = 'break' where category = 'intervalo';
  update app.deviation_type set category = 'perimeter' where category = 'perimetro';
  update app.deviation_type set category = 'exit' where category = 'saida';
end $$;

do $$
begin
  if to_regclass('app.metric') is null then
    return;
  end if;
  update app.metric set code = 'deviations_minutes', target_view = 'vw_deviation_by_employee_day', domain = null where code = 'desvios_minutos';
  update app.metric set code = 'deviations_total', target_view = 'vw_deviation_event', domain = null where code = 'desvios_total';
  update app.metric set code = 'documents_expiring', target_view = 'vw_document_expiry', domain = 'pii' where code = 'documentos_vencendo';
  update app.metric set code = 'payroll_summary', target_view = 'vw_payroll_summary', domain = 'compensation' where code = 'folha_resumo';
  update app.metric set code = 'ranking_by_employee', target_view = 'fn_ranking_by_employee', domain = null where code = 'ranking_colaborador';
  update app.metric set code = 'ranking_by_unit', target_view = 'fn_ranking_by_unit', domain = null where code = 'ranking_unidade';
  update app.metric set code = 'recurrence', target_view = 'fn_recurrence', domain = null where code = 'recorrencia';
  update app.metric set code = 'daily_trend', target_view = 'vw_deviation_daily_trend', domain = null where code = 'tendencia_diaria';
end $$;

-- ---------------------------------------------------------------------------
-- 12. Recria as check constraints, agora com os valores em inglês
-- `add constraint ... check` valida as linhas existentes, então este bloco só
-- funciona depois do 11. Se alguma linha tiver escapado da tradução, é aqui que
-- a migration para — que é o comportamento certo: melhor falhar do que aceitar
-- uma tabela cuja checagem não corresponde ao que ela guarda.
-- ---------------------------------------------------------------------------
do $$
declare r record;
begin
  for r in
    select * from (values
  ('app', 'financial_agreement', 'financial_agreement_status_check', 'CHECK ((status = ANY (ARRAY[''active''::text, ''settled''::text, ''cancelled''::text, ''suspended''::text])))'),
  ('app', 'financial_agreement', 'financial_agreement_type_check', 'CHECK ((type = ANY (ARRAY[''installment_plan''::text, ''vehicle_damage''::text, ''equipment_damage''::text, ''advance''::text, ''loan''::text, ''benefit''::text, ''other''::text])))'),
  ('app', 'agreement_installment', 'agreement_installment_status_check', 'CHECK ((status = ANY (ARRAY[''pending''::text, ''processed''::text, ''cancelled''::text, ''renegotiated''::text])))'),
  ('app', 'leave_period', 'leave_period_category_check', 'CHECK ((category = ANY (ARRAY[''vacation''::text, ''leave_period''::text, ''leave_of_absence''::text, ''suspension''::text])))'),
  ('app', 'leave_period', 'leave_period_source_check', 'CHECK ((source = ANY (ARRAY[''secullum''::text, ''manual''::text, ''spreadsheet''::text])))'),
  ('app', 'alert_sent', 'alert_sent_status_check', 'CHECK ((status = ANY (ARRAY[''sent''::text, ''delivered''::text, ''read''::text, ''failed''::text])))'),
  ('app', 'alert_queue', 'alert_queue_status_check', 'CHECK ((status = ANY (ARRAY[''pending''::text, ''sending''::text, ''sent''::text, ''failed''::text, ''discarded''::text])))'),
  ('app', 'audit_log', 'audit_log_action_check', 'CHECK ((action = ANY (ARRAY[''insert''::text, ''update''::text, ''delete''::text, ''login''::text, ''export''::text, ''sensitive_query''::text])))'),
  ('app', 'report_cycle', 'report_cycle_channel_check', 'CHECK ((channel = ANY (ARRAY[''whatsapp''::text, ''email''::text, ''both''::text])))'),
  ('app', 'report_cycle', 'report_cycle_status_check', 'CHECK ((status = ANY (ARRAY[''open''::text, ''sent''::text, ''failed''::text, ''cancelled''::text])))'),
  ('app', 'employee', 'employee_status_check', 'CHECK ((status = ANY (ARRAY[''active''::text, ''afastado''::text, ''vacation''::text, ''desligado''::text])))'),
  ('app', 'employee', 'employee_employment_type_check', 'CHECK ((employment_type = ANY (ARRAY[''clt''::text, ''pj''::text, ''internship''::text, ''temporary''::text, ''apprentice''::text, ''contractor''::text])))'),
  ('app', 'contact', 'contact_type_check', 'CHECK ((type = ANY (ARRAY[''person''::text, ''whatsapp_group''::text, ''email_list''::text])))'),
  ('app', 'deviation_type', 'deviation_type_category_check', 'CHECK ((category = ANY (ARRAY[''entry''::text, ''exit''::text, ''break''::text, ''integrity''::text, ''roster''::text, ''perimeter''::text])))'),
  ('app', 'deviation_type', 'deviation_type_direction_check', 'CHECK ((direction = ANY (ARRAY[''surplus''::text, ''shortfall''::text, ''neutral''::text])))'),
  ('app', 'detection_run', 'detection_run_mode_check', 'CHECK ((mode = ANY (ARRAY[''shadow''::text, ''production''::text])))'),
  ('app', 'detection_run', 'detection_run_status_check', 'CHECK ((status = ANY (ARRAY[''running''::text, ''completed''::text, ''failed''::text])))'),
  ('app', 'deviation_event', 'deviation_event_mode_check', 'CHECK ((mode = ANY (ARRAY[''shadow''::text, ''production''::text])))'),
  ('app', 'deviation_event', 'deviation_event_status_check', 'CHECK ((status = ANY (ARRAY[''active''::text, ''revoked''::text, ''justified''::text, ''ignored''::text])))'),
  ('app', 'payroll_charge', 'payroll_charge_type_check', 'CHECK ((type = ANY (ARRAY[''fgts''::text, ''inss_employer''::text, ''inss_withheld''::text, ''irrf''::text, ''rat''::text, ''third_parties''::text, ''vacation_accrual''::text, ''thirteenth_accrual''::text, ''other''::text])))'),
  ('app', 'occupational_exam', 'occupational_exam_result_check', 'CHECK ((result = ANY (ARRAY[''fit''::text, ''unfit''::text, ''fit_with_restriction''::text])))'),
  ('app', 'occupational_exam', 'occupational_exam_type_check', 'CHECK ((type = ANY (ARRAY[''pre_employment''::text, ''periodic''::text, ''exit''::text, ''return_to_work_exam''::text, ''job_change''::text])))'),
  ('app', 'payroll_entry', 'payroll_entry_nature_check', 'CHECK ((nature = ANY (ARRAY[''earning''::text, ''deduction''::text, ''base''::text, ''payroll_charge''::text, ''informational''::text])))'),
  ('app', 'file_import', 'file_import_status_check', 'CHECK ((status = ANY (ARRAY[''received''::text, ''validating''::text, ''validation_error''::text, ''processed''::text, ''discarded''::text])))'),
  ('app', 'file_import', 'file_import_type_check', 'CHECK ((type = ANY (ARRAY[''folha''::text, ''payroll_charge''::text, ''employee''::text, ''cost_center''::text, ''roster''::text, ''benefit''::text, ''other''::text])))'),
  ('app', 'expected_workday', 'expected_workday_source_check', 'CHECK ((source = ANY (ARRAY[''secullum_schedule''::text, ''manual_roster''::text, ''inferred''::text])))'),
  ('app', 'expected_workday', 'expected_workday_day_type_check', 'CHECK ((day_type = ANY (ARRAY[''work''::text, ''day_off''::text, ''vacation''::text, ''leave_period''::text, ''holiday''::text, ''compensated''::text])))'),
  ('app', 'financial_threshold', 'financial_threshold_indicator_check', 'CHECK ((indicator = ANY (ARRAY[''total_payroll''::text, ''unit_cost''::text, ''cost_per_employee''::text, ''overtime''::text, ''payroll_charge''::text, ''terminations''::text])))'),
  ('app', 'financial_threshold', 'financial_threshold_operator_check', 'CHECK ((operator = ANY (ARRAY[''greater_than''::text, ''less_than''::text, ''percent_change''::text])))'),
  ('app', 'workforce_movement', 'workforce_movement_type_check', 'CHECK ((type = ANY (ARRAY[''hire''::text, ''termination''::text, ''transfer''::text, ''promotion''::text, ''leave_period''::text, ''return_to_work''::text])))'),
  ('app', 'alert_rule', 'alert_rule_channel_check', 'CHECK ((channel = ANY (ARRAY[''whatsapp''::text, ''email''::text, ''both''::text])))'),
  ('app', 'alert_rule', 'alert_rule_content_check', 'CHECK ((content = ANY (ARRAY[''individual''::text, ''aggregate''::text])))'),
  ('app', 'alert_rule_target', 'alert_rule_target_responsibility_check', 'CHECK ((responsibility = ANY (ARRAY[''unit_manager''::text, ''regional_supervisor''::text, ''personnel''::text, ''hr''::text, ''executive''::text, ''group''::text])))'),
  ('app', 'sync_run', 'sync_run_status_check', 'CHECK ((status = ANY (ARRAY[''running''::text, ''completed''::text, ''failed''::text, ''partial''::text])))'),
  ('app', 'unit_responsible', 'unit_responsible_responsibility_check', 'CHECK ((responsibility = ANY (ARRAY[''unit_manager''::text, ''regional_supervisor''::text, ''personnel''::text, ''hr''::text, ''executive''::text, ''group''::text])))'),
  ('app', 'financial_agreement', 'financial_agreement_installment_count_check', 'CHECK ((installment_count >= 1))'),
  ('app', 'financial_agreement', 'financial_agreement_total_amount_check', 'CHECK ((total_amount > (0)::numeric))'),
  ('app', 'agreement_installment', 'agreement_installment_period_month_check', 'CHECK (((period_month >= 1) AND (period_month <= 13)))'),
  ('app', 'agreement_installment', 'agreement_installment_number_check', 'CHECK ((number >= 1))'),
  ('app', 'agreement_installment', 'agreement_installment_amount_check', 'CHECK ((amount > (0)::numeric))'),
  ('app', 'leave_period', 'leave_period_check', 'CHECK (((end_date IS NULL) OR (end_date >= start_date)))'),
  ('app', 'alert_sent', 'alert_sent_provider_check', 'CHECK ((provider = ANY (ARRAY[''meta_cloud''::text, ''z_api''::text, ''uazapi''::text, ''smtp''::text, ''resend''::text])))'),
  ('app', 'alert_queue', 'alert_queue_channel_check', 'CHECK ((channel = ANY (ARRAY[''whatsapp''::text, ''email''::text])))'),
  ('app', 'report_cycle', 'report_cycle_check', 'CHECK ((period_end >= period_start))'),
  ('app', 'employee', 'employee_check', 'CHECK (((terminated_on IS NULL) OR (hired_on IS NULL) OR (terminated_on >= hired_on)))'),
  ('app', 'employee_compensation', 'employee_compensation_check', 'CHECK (((effective_to IS NULL) OR (effective_to >= effective_from)))'),
  ('app', 'employee_compensation', 'employee_compensation_salary_check', 'CHECK ((salary >= (0)::numeric))'),
  ('app', 'payroll_period', 'payroll_period_year_check', 'CHECK (((year >= 2000) AND (year <= 2100)))'),
  ('app', 'payroll_period', 'payroll_period_month_check', 'CHECK (((month >= 1) AND (month <= 13)))'),
  ('app', 'payroll_period', 'payroll_period_status_check', 'CHECK ((status = ANY (ARRAY[''aberta''::text, ''importada''::text, ''conferida''::text, ''fechada''::text])))'),
  ('app', 'contact', 'contact_whatsapp_check', 'CHECK ((whatsapp ~ ''^\+?\d{10,15}$''::text))'),
  ('app', 'document', 'document_status_check', 'CHECK ((status = ANY (ARRAY[''active''::text, ''vencido''::text, ''substituido''::text, ''removido''::text])))'),
  ('app', 'company', 'company_cnpj_check', 'CHECK ((cnpj ~ ''^\d{14}$''::text))'),
  ('app', 'payroll_charge', 'payroll_charge_source_check', 'CHECK ((source = ANY (ARRAY[''domain_api''::text, ''spreadsheet''::text, ''file''::text, ''manual''::text])))'),
  ('app', 'payroll_entry', 'payroll_entry_source_check', 'CHECK ((source = ANY (ARRAY[''domain_api''::text, ''spreadsheet''::text, ''file''::text, ''manual''::text])))'),
  ('app', 'integration', 'integration_provider_check', 'CHECK ((provider = ANY (ARRAY[''secullum''::text, ''domain''::text, ''spreadsheet''::text, ''meta_cloud''::text, ''z_api''::text, ''uazapi''::text, ''smtp''::text, ''resend''::text])))'),
  ('app', 'expected_workday', 'expected_workday_confidence_check', 'CHECK (((confidence >= 0) AND (confidence <= 100)))'),
  ('app', 'justification', 'justification_source_check', 'CHECK ((source = ANY (ARRAY[''secullum''::text, ''operax''::text, ''whatsapp''::text])))'),
  ('app', 'alert_rule_target', 'alert_rule_target_check', 'CHECK (((contact_id IS NOT NULL) OR (responsibility IS NOT NULL)))')
) as t(sch, tab, nome, definicao)
  loop
    if to_regclass(format('%I.%I', r.sch, r.tab)) is not null
       and not exists (select 1 from pg_constraint c
                        join pg_class rel on rel.oid = c.conrelid
                        join pg_namespace n on n.oid = rel.relnamespace
                        where n.nspname = r.sch and rel.relname = r.tab and c.conname = r.nome) then
      execute format('alter table %I.%I add constraint %I %s', r.sch, r.tab, r.nome, r.definicao);
    end if;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 12b. Materialized view
-- `create or replace materialized view` não existe, e o corpo dela filtra
-- `status = 'ativo'` como as views do bloco 8c. Então ela cai e sobe de novo,
-- com os índices — que caem junto e voltam junto.
--
-- Vem aqui, no fim, porque `create materialized view` executa a consulta na
-- hora: antes do bloco 11 ela se popularia filtrando por um valor que a
-- tradução ainda não tinha gravado.
--
-- app.mv_deviation_day não respeita RLS e nunca é exposta — recriá-la não muda
-- quem enxerga o quê.
-- ---------------------------------------------------------------------------
do $$
begin
  if to_regclass('app.mv_desvio_dia') is not null then
    execute format('drop materialized view %I.%I cascade', 'app', 'mv_desvio_dia');
  end if;
  if to_regclass('app.mv_deviation_day') is null then
    execute $mv$create materialized view app.mv_deviation_day as
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
  GROUP BY d.tenant_id, d.reference_date, d.company_id, d.unit_id, d.type$mv$;
execute $ix$CREATE INDEX mv_deviation_day_periodo_idx ON app.mv_deviation_day USING btree (tenant_id, reference_date)$ix$;
execute $ix$CREATE UNIQUE INDEX mv_deviation_day_pk ON app.mv_deviation_day USING btree (tenant_id, reference_date, company_id, COALESCE(unit_id, '00000000-0000-0000-0000-000000000000'::uuid), type)$ix$;
  end if;
end $$;

