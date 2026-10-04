import { ApiError } from "@/lib/api";

/**
 * O lançamento no Secullum, do lado de cá — Caminho 2.
 *
 * O painel não escreve no Secullum: o RH digita lá a decisão aprovada e volta
 * aqui para declarar que digitou. É essa marca (`posted_to_source_at`) que
 * separa "aprovada" de "aprovada e lançada" — sem ela, a aprovação vale no
 * painel e some no registro oficial, que é o maior risco do fluxo inteiro.
 *
 * Os tipos são os de `PostingListRow`, `PostingList` e `ReviewPostingApplied`
 * em `server/models.py`: contrato da API, não de uma tabela.
 */

export type PostingListRow = {
  review_id: string;
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
  /** uuid de quem aprovou — nunca mostrado: o nome mora em `auth.users`. */
  reviewed_by: string;
  reviewed_at: string;
  /** Nulo = aprovada e ainda não lançada no Secullum. */
  posted_to_source_at: string | null;
  /** uuid de quem marcou — nunca mostrado, pelo mesmo motivo. */
  posted_by: string | null;
};

/**
 * A resposta de `GET /alcada/lancamento`. A competência é a do FATO, com a
 * janela devolvida pelo banco — a mesma da fila, e a tela não calcula nada.
 */
export type PostingList = {
  ano: number;
  mes: number;
  period_start: string;
  period_end: string;
  rows: PostingListRow[];
};

export type ReviewPostingApplied = {
  review_id: string;
  posted_to_source_at: string;
  posted_by: string;
};

/**
 * As quatro recusas de `fn_marcar_lancado`, pelo código que a rota põe em
 * `detail`. A tela decide a frase; o backend decide o caso.
 */
export const POSTING_ERROR_MESSAGE: Record<string, string> = {
  not_hr:
    "Marcar como lançado no Secullum é do RH ou do owner. O seu papel não marca.",
  review_not_found:
    "Esta aprovação não foi encontrada. A lista foi recarregada.",
  not_approved:
    "Esta justificativa não está aprovada, então não há o que lançar no Secullum.",
  already_posted:
    "Esta aprovação já estava marcada como lançada no Secullum. A lista foi recarregada.",
};

/**
 * As recusas que dizem "a lista está velha": a tela recarrega em vez de
 * deixar um botão que só pode falhar de novo.
 */
export const STALE_POSTING_CODES: readonly string[] = [
  "review_not_found",
  "already_posted",
];

export function postingErrorCode(error: unknown): string | null {
  return error instanceof ApiError ? error.detail : null;
}

export function postingErrorMessage(error: unknown): string {
  const code = postingErrorCode(error);

  if (code && code in POSTING_ERROR_MESSAGE) {
    return POSTING_ERROR_MESSAGE[code];
  }

  if (error instanceof ApiError && error.status === 401) {
    return "A sua sessão expirou. Entre de novo para marcar.";
  }

  return "Não foi possível registrar a marca. Nada foi alterado — tente de novo.";
}
