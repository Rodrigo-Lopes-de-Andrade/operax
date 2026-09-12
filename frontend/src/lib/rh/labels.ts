/**
 * O vocabulário em pt-BR de tudo que o banco guarda em inglês.
 *
 * Fica no frontend de propósito. O domínio é snake_case inglês por convenção do
 * projeto, e a interface é pt-BR por decisão de produto; misturar as duas coisas
 * no backend faria a API carregar texto de tela, e aí a mesma palavra passaria a
 * ter dois donos.
 *
 * "Desvio" e "indício" — nunca "hora extra". O registro oficial é o do sistema
 * de ponto, e divergir dele com ação de gestor em cima é exposição do
 * fornecedor.
 */

export const STATUS_LABEL: Record<string, string> = {
  active: "Ativo",
  afastado: "Afastado",
  vacation: "Férias",
  desligado: "Desligado",
};

export const EMPLOYMENT_LABEL: Record<string, string> = {
  clt: "CLT",
  pj: "PJ",
  internship: "Estágio",
  temporary: "Temporário",
  apprentice: "Aprendiz",
  contractor: "Terceirizado",
};

export const EXAM_TYPE_LABEL: Record<string, string> = {
  pre_employment: "Admissional",
  periodic: "Periódico",
  exit: "Demissional",
  return_to_work_exam: "Retorno ao trabalho",
  job_change: "Mudança de função",
};

/** Aptidão e validade. Nunca diagnóstico, CID ou descrição de restrição. */
export const EXAM_RESULT_LABEL: Record<string, string> = {
  fit: "Apto",
  unfit: "Inapto",
  fit_with_restriction: "Apto com restrição",
};

/** Rótulo neutro: o motivo do afastamento é dado de saúde e não é capturado. */
export const LEAVE_LABEL: Record<string, string> = {
  vacation: "Férias",
  leave_period: "Afastamento",
  leave_of_absence: "Licença",
  suspension: "Suspensão",
};

export const MOVEMENT_LABEL: Record<string, string> = {
  hire: "Admissão",
  termination: "Desligamento",
  transfer: "Transferência",
  promotion: "Promoção",
  leave_period: "Afastamento",
  return_to_work: "Retorno",
};

export const AGREEMENT_TYPE_LABEL: Record<string, string> = {
  installment_plan: "Parcelamento",
  vehicle_damage: "Avaria em veículo",
  equipment_damage: "Avaria em equipamento",
  advance: "Adiantamento",
  loan: "Empréstimo",
  benefit: "Benefício",
  other: "Outro",
};

export const AGREEMENT_STATUS_LABEL: Record<string, string> = {
  active: "Ativo",
  settled: "Quitado",
  cancelled: "Cancelado",
  suspended: "Suspenso",
};

export const DOCUMENT_STATUS_LABEL: Record<string, string> = {
  active: "Vigente",
  vencido: "Vencido",
  substituido: "Substituído",
  removido: "Removido",
};

export const SOURCE_LABEL: Record<string, string> = {
  secullum: "Sistema de ponto",
  manual: "Lançamento manual",
  spreadsheet: "Planilha",
};

/** O bloco de proveniência: o nome de tela de cada coluna que o sync governa. */
export const SYNC_FIELD_LABEL: Record<string, string> = {
  registration_number: "Matrícula",
  name: "Nome",
  hired_on: "Admissão",
  status: "Situação",
  unit_id: "Unidade",
  company_id: "Empresa",
  department_id: "Departamento",
  manager_employee_id: "Supervisor",
  terminated_on: "Demissão",
};

export const PENDENCIA_LABEL: Record<string, string> = {
  vinculo: "Sem ID RH",
  aso: "ASO",
  documento: "Documento",
  experiencia: "Experiência",
};

export const TAB_LABEL: Record<string, string> = {
  cadastro: "Cadastro",
  posicao: "Posição",
  pessoais: "Dados pessoais",
  saude: "ASO",
  remuneracao: "Remuneração",
  afastamentos: "Afastamentos",
  movimentacoes: "Movimentações",
  acordos: "Acordos",
};

export function label(
  map: Record<string, string>,
  value: string | null,
): string {
  if (!value) {
    return "—";
  }

  return map[value] ?? value;
}

/**
 * Quantos dias faltam, ou faltaram. O sinal importa mais que o número: "venceu
 * há 3 dias" e "vence em 3 dias" são situações diferentes e a tela não pode
 * pedir que o usuário compare datas de cabeça.
 */
export function daysUntil(iso: string, today: Date): number {
  const due = new Date(`${iso}T00:00:00`);
  const base = new Date(today.getFullYear(), today.getMonth(), today.getDate());

  return Math.round((due.getTime() - base.getTime()) / 86_400_000);
}

export function dueLabel(days: number): string {
  if (days < 0) {
    return `venceu há ${Math.abs(days)} ${Math.abs(days) === 1 ? "dia" : "dias"}`;
  }

  if (days === 0) {
    return "vence hoje";
  }

  return `vence em ${days} ${days === 1 ? "dia" : "dias"}`;
}

/**
 * A janela de "a vencer", declarada UMA vez — e quem a explica ao usuário lê
 * daqui, nunca escreve o número de novo. Ver `dueTone`.
 */
export const DUE_SOON_DAYS = 30;

/** Vencido é falha; vencendo é alerta; o resto é apenas informação. */
export function dueTone(days: number): "bad" | "alert" | "neutral" {
  if (days < 0) {
    return "bad";
  }

  return days <= DUE_SOON_DAYS ? "alert" : "neutral";
}
