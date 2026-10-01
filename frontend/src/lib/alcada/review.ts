import { ApiError } from "@/lib/api";

/**
 * O contrato de `routers/alcada.py`, do lado de cá — Caminho 2.
 *
 * A fila é dado individual (nome, texto da justificativa, autor), então vem do
 * FastAPI com o Bearer do Supabase, nunca da anon key. Os tipos são os de
 * `ApprovalQueueRow` e `JustificationReviewApplied` em `server/models.py`: o
 * contrato é da API, não de uma tabela, e por isso não saem de
 * `database.types.ts`.
 */

/** Por que uma linha está na fila e não pode ser revisada por quem pediu. */
export type BlockedReason = "own_justification" | "owner_only";

export type ApprovalQueueRow = {
  justification_id: string;
  employee_id: string;
  employee_name: string;
  unit_id: string | null;
  unit_name: string | null;
  reference_date: string;
  /** Nulos quando a justificativa não tem desvio. */
  type: string | null;
  type_description: string | null;
  minutes: number | null;
  text: string;
  author_name: string | null;
  created_at: string;
  can_review: boolean;
  blocked_reason: BlockedReason | null;
};

/**
 * A resposta de `GET /alcada/fila`. A competência e a janela vêm do banco
 * (`util.competencia_janela`): a tela não calcula nenhuma das duas, só as
 * mostra — e é com elas que monta os links e limita as datas.
 */
export type ApprovalQueueResponse = {
  ano: number;
  mes: number;
  period_start: string;
  period_end: string;
  rows: ApprovalQueueRow[];
};

export type ReviewDecision = "approved" | "rejected";

export type ReviewApplied = {
  review_id: string;
  justification_id: string;
  decision: ReviewDecision;
};

export const BLOCKED_REASON_LABEL: Record<BlockedReason, string> = {
  own_justification:
    "Você escreveu esta justificativa — outra pessoa do RH precisa revisá-la.",
  owner_only: "Este colaborador só pode ter justificativa revisada pelo owner.",
};

/**
 * As nove recusas de `fn_revisar_justificativa`, pelo código que a rota põe em
 * `detail`. A tela decide a frase; o backend decide o caso.
 */
export const REVIEW_ERROR_MESSAGE: Record<string, string> = {
  not_hr: "Revisar justificativa é do RH ou do owner. O seu papel não revisa.",
  justification_not_found:
    "Esta justificativa não foi encontrada. Ela pode ter sido removida — a fila foi recarregada.",
  own_justification:
    "Você escreveu esta justificativa — outra pessoa do RH precisa revisá-la.",
  owner_only: "Este colaborador só pode ter justificativa revisada pelo owner.",
  already_reviewed:
    "Outra pessoa já revisou esta justificativa. A fila foi recarregada.",
  source_is_mirror:
    "Esta justificativa veio do Secullum e já vale como registrada lá — não se revisa no painel.",
  not_pending:
    "Esta justificativa não está mais pendente. A fila foi recarregada.",
  no_open_period:
    "Não há competência aberta para registrar a revisão. Fale com o DP antes de revisar.",
  rejection_needs_reason:
    "Para reprovar, escreva o motivo — é ele que o supervisor vai ler.",
};

/**
 * As recusas que dizem "esta linha não é mais revisável por ninguém agora": a
 * tela a tira da lista e recarrega a fila, em vez de deixar um botão que só
 * pode falhar de novo.
 */
export const STALE_REVIEW_CODES: readonly string[] = [
  "justification_not_found",
  "already_reviewed",
  "source_is_mirror",
  "not_pending",
];

export function reviewErrorCode(error: unknown): string | null {
  return error instanceof ApiError ? error.detail : null;
}

export function reviewErrorMessage(error: unknown): string {
  const code = reviewErrorCode(error);

  if (code && code in REVIEW_ERROR_MESSAGE) {
    return REVIEW_ERROR_MESSAGE[code];
  }

  if (error instanceof ApiError && error.status === 401) {
    return "A sua sessão expirou. Entre de novo para revisar.";
  }

  return "Não foi possível registrar a revisão. Nada foi alterado — tente de novo.";
}
