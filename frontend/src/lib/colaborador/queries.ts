import "server-only";

import { ApiError, requestApi } from "@/lib/api";
import type { DateRange } from "@/lib/ponto/filters";
import { getServerSupabase } from "@/lib/supabase-server";

/**
 * Caminho 2 of the contract. Everything on this screen is about one named
 * person, so none of it goes near the anon path: the browser session's access
 * token travels to FastAPI, which re-checks tenant, scope and sensitive domain
 * before answering.
 *
 * The three sensitive blocks arrive `null` — absent, not empty — when the
 * caller's role does not reach that domain. That distinction is the screen: a
 * `null` renders nothing at all, an empty array renders "nada registrado".
 * There is no padlock and no greyed-out card, because a role that may not see
 * salaries should not learn that salaries exist.
 */

export type EmployeeSummary = {
  employee_id: string;
  name: string;
  registration_number: string | null;
  cargo: string | null;
  status: string;
  hired_on: string | null;
  employment_type: string | null;
  unit_name: string | null;
  company_name: string | null;
  department_name: string | null;
  manager_name: string | null;
};

export type DeviationIndicators = {
  events: number;
  minutes_abs: number;
  minutes_balance: number;
  days_with_deviation: number;
  pending_cycle: number;
};

export type DeviationTypeCount = {
  type: string;
  description: string;
  events: number;
  minutes_abs: number;
};

export type WorkdayRow = {
  reference_date: string;
  day_type: string;
  expected_entry: string | null;
  expected_exit: string | null;
  confidence: number;
  deviation_type: string | null;
  deviation_description: string | null;
  direction: string | null;
  minutes: number | null;
  expected_time: string | null;
  actual_time: string | null;
};

/**
 * Uma coluna de um dia, do jeito que a origem a transpôs.
 *
 * `column_index` é a posição no registro-dia, e é ela que emparelha uma entrada
 * com a saída dela — emparelhar por ordem de horário inventaria um par sempre
 * que um dos lados faltasse.
 *
 * Linha sem `punched_at` não é ruído: ou `status_label` explica ("Férias"), ou
 * `expected_time` diz que uma marcação era esperada ali e não chegou.
 */
export type PunchRow = {
  reference_date: string;
  column_type: string;
  column_index: number;
  punched_at: string | null;
  status_label: string | null;
  expected_time: string | null;
  disregarded: boolean;
};

export type JustificationRow = {
  reference_date: string;
  text: string;
  author_name: string | null;
  source: string;
};

export type CompensationBand = {
  effective_from: string;
  effective_to: string | null;
  salary: string;
  reason: string | null;
};

export type EmployeeDocument = {
  type_name: string;
  valid_until: string | null;
  status: string;
};

export type OccupationalExamRow = {
  type: string;
  performed_on: string;
  valid_until: string | null;
  result: string | null;
};

export type EmployeeDetail = {
  employee: EmployeeSummary;
  indicators: DeviationIndicators;
  by_type: DeviationTypeCount[];
  workdays: WorkdayRow[];
  punches: PunchRow[];
  /** Null quando nunca houve leitura concluída — aí a lista vazia não afirma nada. */
  punches_read_at: string | null;
  justifications: JustificationRow[];
  compensation: CompensationBand[] | null;
  documents: EmployeeDocument[] | null;
  exams: OccupationalExamRow[] | null;
};

/** Null when the person is outside the caller's scope, or does not exist. */
export async function loadEmployee(
  employeeId: string,
  range: DateRange,
): Promise<EmployeeDetail | null> {
  const supabase = await getServerSupabase();
  const { data } = await supabase.auth.getSession();
  const accessToken = data.session?.access_token;

  if (!accessToken) {
    return null;
  }

  const query = new URLSearchParams({ de: range.de, ate: range.ate });

  try {
    return await requestApi<EmployeeDetail>(
      `/colaboradores/${employeeId}?${query}`,
      { accessToken },
    );
  } catch (error) {
    // The backend answers 404 both for "does not exist" and for "outside your
    // scope", on purpose: a 403 would confirm that the person exists in a unit
    // the caller may not see.
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }

    throw error;
  }
}
