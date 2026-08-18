#!/usr/bin/env python3
"""
Mapa de renomeação pt-BR -> en para o domínio do OperaX.

Decisão: o domínio segue inglês snake_case, alinhado com `work_schedule_day`,
que vocês já construíram. Identificadores brasileiros que são nome próprio de
instrumento legal (cnpj, cpf, rg, pis, ctps, fgts, inss, irrf, rat, aso)
permanecem — traduzir "CNPJ" para "tax_id" perde informação, não ganha.

Aplicar:  python3 scripts/rename_map.py --apply
Conferir: python3 scripts/rename_map.py            (dry-run, mostra contagem)
"""
import re, sys, glob, collections

# Ordem importa: o script aplica do mais longo para o mais curto, com
# fronteira de palavra, para `nome_mae` não virar `name_mae`.

TABELAS = {
    "tenant_membro": "tenant_member",
    "escopo_usuario": "user_scope",
    "permissao_dominio": "domain_permission",
    "empresa": "company",
    "unidade_mapa_secullum": "unit_secullum_map",
    "unidade_responsavel": "unit_responsible",
    "unidade": "unit",
    "departamento": "department",
    "colaborador_remuneracao": "employee_compensation",
    "colaborador_funcao": "employee_position",
    "colaborador_pii": "employee_pii",
    "colaborador": "employee",
    "afastamento": "leave_period",
    "contato": "contact",
    "desvio_tipo_config": "deviation_type_config",
    "desvio_tipo": "deviation_type",
    "jornada_dia": "expected_workday",
    "deteccao_execucao": "detection_run",
    "ciclo_relatorio": "report_cycle",
    "justificativa": "justification",
    "regra_alerta_destino": "alert_rule_target",
    "regra_alerta": "alert_rule",
    "alerta_fila": "alert_queue",
    "alerta_enviado": "alert_sent",
    "competencia": "payroll_period",
    "centro_custo": "cost_center",
    "folha_evento": "payroll_entry",
    "encargo": "payroll_charge",
    "movimentacao_pessoal": "workforce_movement",
    "limiar_financeiro": "financial_threshold",
    "documento_tipo": "document_type",
    "documento": "document",
    "exame_ocupacional": "occupational_exam",
    "acordo_financeiro": "financial_agreement",
    "acordo_parcela": "agreement_installment",
    "integracao_segredo": "integration_secret",
    "integracao": "integration",
    "sync_execucao": "sync_run",
    "importacao_arquivo": "file_import",
    "consulta_ia": "ai_query",
    "metrica": "metric",
    "mv_desvio_dia": "mv_deviation_day",
}

TIPOS = {
    "dominio_sensivel": "sensitive_domain",
    "papel": "user_role",
}

FUNCOES = {
    "tenants_do_usuario": "user_tenants",
    "tem_tenant": "has_tenant",
    "papeis_no_tenant": "roles_in_tenant",
    "pode_ver_dominio": "can_see_domain",
    "pode_ver_empresa": "can_see_company",
    "pode_ver_unidade": "can_see_unit",
    "pode_ver_colaborador": "can_see_employee",
    "eh_admin": "is_admin",
    "toca_atualizado_em": "touch_updated_at",
    "bloqueia_tabela_em_public": "block_table_in_public",
    "valida_destino_alerta": "validate_alert_target",
    "revogar_desvio": "revoke_deviation",
    "assert_eq": "assert_eq",
}

VIEWS = {
    "vw_desvio_resumo_unidade": "vw_deviation_summary_by_unit",
    "vw_desvio_tendencia_diaria": "vw_deviation_daily_trend",
    "vw_desvio_por_colaborador_dia": "vw_deviation_by_employee_day",
    "vw_desvio_evento": "vw_deviation_event",
    "vw_documento_vencimento": "vw_document_expiry",
    "vw_folha_resumo": "vw_payroll_summary",
    "vw_colaborador": "vw_employee",
    "vw_unidade": "vw_unit",
    "fn_kpi_periodo": "fn_kpi_period",
    "fn_ranking_unidade": "fn_ranking_by_unit",
    "fn_ranking_colaborador": "fn_ranking_by_employee",
    "fn_recorrencia": "fn_recurrence",
}

COLUNAS = {
    "atualizado_em": "updated_at",
    "criado_em": "created_at",
    "criado_por": "created_by",
    "nome_fantasia": "trade_name",
    "razao_social": "legal_name",
    "nome_arquivo": "file_name",
    "nome_mae": "mother_name",
    "nome_pai": "father_name",
    "data_nascimento": "birth_date",
    "email_pessoal": "personal_email",
    "telefone": "phone",
    "endereco": "address",
    "secullum_empresa_id": "secullum_company_id",
    "secullum_departamento_id": "secullum_department_id",
    "secullum_funcionario_id": "secullum_employee_id",
    "secullum_horario_id": "secullum_schedule_id",
    "validado_por": "validated_by",
    "validado_em": "validated_at",
    "observacao": "notes",
    "matricula": "registration_number",
    "tipo_contratacao": "employment_type",
    "data_admissao": "hired_on",
    "data_demissao": "terminated_on",
    "gestor_colaborador_id": "manager_employee_id",
    "empresa_id": "company_id",
    "unidade_id": "unit_id",
    "colaborador_id": "employee_id",
    "departamento_id": "department_id",
    "vigencia_inicio": "effective_from",
    "vigencia_fim": "effective_to",
    "salario": "salary",
    "registrado_por": "recorded_by",
    "data_inicio": "start_date",
    "data_fim": "end_date",
    "principal": "is_primary",
    "contato_id": "contact_id",
    "descricao": "description",
    "direcao": "direction",
    "categoria": "category",
    "conta_como_desvio": "counts_as_deviation",
    "gera_alerta": "triggers_alert",
    "tolerancia_extra_min": "tolerance_extra_minutes",
    "tolerancia_falta_min": "tolerance_absence_minutes",
    "data_ref": "reference_date",
    "tipo_dia": "day_type",
    "entrada_prevista": "expected_entry",
    "saida_prevista": "expected_exit",
    "intervalo_previsto_min": "expected_break_minutes",
    "carga_prevista_min": "workload_minutes",
    "confianca": "confidence",
    "periodo_inicio": "period_start",
    "periodo_fim": "period_end",
    "iniciado_em": "started_at",
    "terminado_em": "finished_at",
    "eventos_detectados": "events_detected",
    "eventos_publicados": "events_published",
    "versao_motor": "engine_version",
    "gerado_em": "generated_at",
    "enviado_em": "sent_at",
    "total_eventos": "total_events",
    "horario_previsto": "expected_time",
    "horario_realizado": "actual_time",
    "batida_ids": "punch_ids",
    "motivo_status": "status_reason",
    "execucao_id": "run_id",
    "ciclo_relatorio_id": "report_cycle_id",
    "detectado_em": "detected_at",
    "autor_user_id": "author_user_id",
    "autor_nome": "author_name",
    "escopo_unidade_id": "scope_unit_id",
    "conteudo": "content",
    "janela_cron": "cron_window",
    "limiar_minutos": "threshold_minutes",
    "limiar_ocorrencias": "threshold_occurrences",
    "silenciar_ate": "muted_until",
    "chave_idempotencia": "idempotency_key",
    "tentativas": "attempts",
    "proxima_tentativa": "next_attempt_at",
    "agendado_para": "scheduled_for",
    "fila_id": "queue_id",
    "regra_id": "rule_id",
    "provedor": "provider",
    "destino_hash": "destination_hash",
    "custo_centavos": "cost_cents",
    "fechada_em": "closed_at",
    "competencia_id": "payroll_period_id",
    "centro_custo_id": "cost_center_id",
    "natureza": "nature",
    "referencia": "reference",
    "importacao_id": "import_id",
    "base_calculo": "calculation_base",
    "data_evento": "event_date",
    "custo_estimado": "estimated_cost",
    "indicador": "indicator",
    "operador": "operator",
    "exige_validade": "requires_expiry",
    "dias_alerta_vencimento": "expiry_alert_days",
    "obrigatorio": "required",
    "tipo_id": "type_id",
    "emitido_em": "issued_on",
    "valido_ate": "valid_until",
    "substitui_id": "replaces_id",
    "realizado_em": "performed_on",
    "resultado": "result",
    "documento_id": "document_id",
    "valor_total": "total_amount",
    "qtd_parcelas": "installment_count",
    "data_acordo": "agreement_date",
    "autorizado_por": "authorized_by",
    "autorizado_em": "authorized_at",
    "acordo_id": "agreement_id",
    "numero": "number",
    "competencia_ano": "period_year",
    "competencia_mes": "period_month",
    "folha_evento_id": "payroll_entry_id",
    "processada_em": "processed_at",
    "apelido": "alias",
    "vault_id": "vault_id",
    "entidade_id": "entity_id",
    "entidade": "entity",
    "cursor_ate": "cursor_until",
    "registros_lidos": "records_read",
    "registros_gravados": "records_written",
    "layout_versao": "layout_version",
    "enviado_por": "uploaded_by",
    "linhas_total": "rows_total",
    "linhas_ok": "rows_ok",
    "linhas_erro": "rows_error",
    "relatorio": "report",
    "acao": "action",
    "pergunta": "question",
    "metrica_codigo": "metric_code",
    "parametros": "parameters",
    "linhas_retornadas": "rows_returned",
    "latencia_ms": "latency_ms",
    "tokens_entrada": "input_tokens",
    "tokens_saida": "output_tokens",
    "recusada": "refused",
    "motivo_recusa": "refusal_reason",
    "titulo": "title",
    "view_alvo": "target_view",
    "dimensoes": "dimensions",
    "filtros": "filters",
    "codigo": "code",
    "papel": "role",
    "dominio": "domain",
    "permitido": "allowed",
    "ativo": "active",
    "modo": "mode",
    "canal": "channel",
    "destino": "destination",
    "funcao": "responsibility",
    "minutos": "minutes",
    "motivo": "reason",
    "origem": "source",
    "erro": "error",
    "texto": "text",
    "chave": "key",
    "valor": "amount",
    "nome": "name",
    "tipo": "type",
    "ano": "year",
    "mes": "month",
}

# Valores de dado (códigos e enums), trocados dentro de aspas simples
VALORES = {
    "entrada_atrasada": "late_entry",
    "entrada_adiantada": "early_entry",
    "saida_antecipada": "early_exit",
    "saida_postergada": "late_exit",
    "intervalo_excedido": "break_exceeded",
    "intervalo_insuficiente": "break_too_short",
    "intervalo_sem_retorno": "break_no_return",
    "marcacao_incompleta": "incomplete_punches",
    "sem_marcacao": "no_punches",
    "batida_em_folga": "punch_on_day_off",
    "jornada_excedida": "workday_exceeded",
    "fora_perimetro": "outside_perimeter",
    "desvios_total": "deviations_total",
    "desvios_minutos": "deviations_minutes",
    "ranking_unidade": "ranking_by_unit",
    "ranking_colaborador": "ranking_by_employee",
    "tendencia_diaria": "daily_trend",
    "recorrencia": "recurrence",
    "documentos_vencendo": "documents_expiring",
    "folha_resumo": "payroll_summary",
    "diretoria": "executive",
    "rh": "hr",
    "dp": "personnel",
    "gestor_regional": "regional_manager",
    "supervisor_unidade": "unit_supervisor",
    "gestor_operacional": "operations_manager",
    "contabilidade": "accounting",
    "consulta": "viewer",
    "remuneracao": "compensation",
    "saude": "health",
    "disciplinar": "disciplinary",
    "sombra": "shadow",
    "producao": "production",
    "ativo": "active",
    "revogado": "revoked",
    "justificado": "justified",
    "ignorado": "ignored",
    "trabalho": "work",
    "folga": "day_off",
    "ferias": "vacation",
    "afastamento": "leave",
    "feriado": "holiday",
    "compensado": "compensated",
    "secullum_horario": "secullum_schedule",
    "escala_manual": "manual_roster",
    "inferido": "inferred",
    "executando": "running",
    "concluida": "completed",
    "falhou": "failed",
    "parcial": "partial",
    "aberto": "open",
    "enviado": "sent",
    "cancelado": "cancelled",
    "pendente": "pending",
    "enviando": "sending",
    "descartado": "discarded",
    "entregue": "delivered",
    "lido": "read",
    "gestor_unidade": "unit_manager",
    "supervisor_regional": "regional_supervisor",
    "grupo": "group",
    "pessoa": "person",
    "grupo_whatsapp": "whatsapp_group",
    "lista_email": "email_list",
    "individual": "individual",
    "agregado": "aggregate",
    "clt": "clt",
    "estagio": "internship",
    "temporario": "temporary",
    "aprendiz": "apprentice",
    "terceirizado": "contractor",
    "licenca": "leave_of_absence",
    "suspensao": "suspension",
    "manual": "manual",
    "planilha": "spreadsheet",
    "arquivo": "file",
    "dominio_api": "dominio_api",
    "provento": "earning",
    "desconto": "deduction",
    "base": "base",
    "informativo": "informational",
    "fgts": "fgts", "inss_patronal": "inss_employer", "inss_retido": "inss_withheld",
    "irrf": "irrf", "rat": "rat", "terceiros": "third_parties",
    "provisao_ferias": "vacation_accrual", "provisao_13": "thirteenth_accrual",
    "outros": "other",
    "admissao": "hire", "desligamento": "termination", "transferencia": "transfer",
    "promocao": "promotion", "retorno": "return_to_work",
    "folha_total": "total_payroll", "custo_unidade": "unit_cost",
    "custo_por_colaborador": "cost_per_employee", "horas_extras": "overtime",
    "desligamentos": "terminations",
    "maior_que": "greater_than", "menor_que": "less_than",
    "variacao_percentual": "percent_change",
    "admissional": "pre_employment", "periodico": "periodic",
    "demissional": "exit", "retorno_trabalho": "return_to_work_exam",
    "mudanca_funcao": "job_change",
    "apto": "fit", "inapto": "unfit", "apto_com_restricao": "fit_with_restriction",
    "parcelamento": "installment_plan", "dano_veiculo": "vehicle_damage",
    "dano_equipamento": "equipment_damage", "adiantamento": "advance",
    "emprestimo": "loan", "beneficio": "benefit", "outro": "other",
    "quitado": "settled", "suspenso": "suspended",
    "renegociada": "renegotiated", "processada": "processed", "cancelada": "cancelled",
    "recebido": "received", "validando": "validating",
    "erro_validacao": "validation_error", "processado": "processed",
    "descartada": "discarded",
    "colaborador": "employee", "escala": "roster",
    "login": "login", "export": "export",
    "consulta_sensivel": "sensitive_query",
    "entrada": "entry", "saida": "exit", "intervalo": "break",
    "integridade": "integrity", "perimetro": "perimeter",
    "excedente": "surplus", "faltante": "shortfall", "neutro": "neutral",
    "whatsapp": "whatsapp", "email": "email", "ambos": "both",
    "evolution": "evolution", "whatsapp_cloud": "whatsapp_cloud",
    "smtp": "smtp", "resend": "resend",
    "kastro-park": "kastro-park",
}


def build_ordered(*mapas):
    junto = {}
    for m in mapas:
        junto.update(m)
    return sorted(junto.items(), key=lambda kv: -len(kv[0]))


IDENTIFICADORES = build_ordered(TABELAS, TIPOS, FUNCOES, VIEWS, COLUNAS)
VALORES_ORD = sorted(VALORES.items(), key=lambda kv: -len(kv[0]))

ALVOS = (sorted(glob.glob("supabase/migrations/*.sql"))
         + ["scripts/98_teste_isolamento_tenant.sql",
            "scripts/99_verificacao_rls.sql",
            "scripts/01_preflight.sql"])


NOMES_TABELA = sorted(TABELAS.items(), key=lambda kv: -len(kv[0]))
SUFIXOS = {"leitura": "read", "escrita": "write", "admin": "admin"}


def renomear(texto):
    trocas = collections.Counter()
    # 0) nome de tabela DENTRO de aspas simples (listas de tabelas nos loops de
    #    RLS). Precisa vir antes dos valores: 'afastamento' como tabela é
    #    leave_period, como valor de categoria é leave.
    for velho, novo in NOMES_TABELA:
        padrao = re.compile(r"'" + re.escape(velho) + r"'")
        texto, n = padrao.subn("'" + novo + "'", texto)
        if n:
            trocas[f"tabela:'{velho}'"] += n
    # 1) valores entre aspas simples
    for velho, novo in VALORES_ORD:
        padrao = re.compile(r"'" + re.escape(velho) + r"'")
        texto, n = padrao.subn("'" + novo + "'", texto)
        if n:
            trocas[f"'{velho}'"] += n
    # 2) identificadores, fronteira de palavra, mais longo primeiro
    for velho, novo in IDENTIFICADORES:
        padrao = re.compile(r"(?<![A-Za-z0-9_\"])" + re.escape(velho) + r"(?![A-Za-z0-9_])")
        texto, n = padrao.subn(novo, texto)
        if n:
            trocas[velho] += n
    # 3) nomes compostos: índices, policies e constraints (tenant_membro_user_idx,
    #    colaborador_leitura, escopo_usuario_empresa_idx)
    for velho, novo in IDENTIFICADORES:
        pre = re.compile(r"(?<![A-Za-z0-9_\"])" + re.escape(velho) + r"_(?=[a-z])")
        texto, n1 = pre.subn(novo + "_", texto)
        pos = re.compile(r"(?<=[a-z0-9])_" + re.escape(velho) + r"(?![A-Za-z0-9_])")
        texto, n2 = pos.subn("_" + novo, texto)
        if n1 + n2:
            trocas[f"composto:{velho}"] += n1 + n2
    for velho, novo in SUFIXOS.items():
        pos = re.compile(r"(?<=[a-z0-9])_" + velho + r"(?![A-Za-z0-9_])")
        texto, n = pos.subn("_" + novo, texto)
        if n:
            trocas[f"sufixo:{velho}"] += n
    return texto, trocas


if __name__ == "__main__":
    aplicar = "--apply" in sys.argv
    total = collections.Counter()
    for caminho in ALVOS:
        original = open(caminho, encoding="utf-8").read()
        novo, trocas = renomear(original)
        total.update(trocas)
        if aplicar and novo != original:
            open(caminho, "w", encoding="utf-8").write(novo)
    print(f"{'APLICADO' if aplicar else 'DRY-RUN'} — {len(ALVOS)} arquivos, "
          f"{sum(total.values())} substituições em {len(total)} termos distintos")
    for termo, n in total.most_common(15):
        print(f"  {n:5d}  {termo}")
