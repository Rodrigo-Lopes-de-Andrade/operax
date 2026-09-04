import "server-only";

import { ApiError, requestApi } from "@/lib/api";
import { rhQuery, type RhFilters } from "@/lib/rh/url";
import { getServerSupabase } from "@/lib/supabase-server";

/**
 * Caminho 2, inteiro. A aba Colaboradores mistura domínios numa mesma linha — o
 * próximo vencimento de alguém pode ser um ASO (saúde), uma CNH (PII) ou o fim
 * do contrato de experiência (nenhum dos dois) — e o recorte por permissão é
 * responsabilidade do backend, não do navegador.
 *
 * Os cinco blocos sensíveis chegam `null`, e não `[]`, quando o papel não
 * alcança o domínio. É a diferença que constrói a tela: `null` não renderiza a
 * aba, `[]` renderiza a aba com um estado vazio. Sem cadeado e sem cinza — quem
 * não pode ver salário não fica sabendo que existe salário.
 */

export type HrDueDate = {
  kind: "aso" | "documento" | "experiencia";
  label: string;
  due_on: string;
};

export type HrEmployeeRow = {
  employee_id: string;
  name: string;
  registration_number: string | null;
  hr_code: string | null;
  cargo: string | null;
  status: string;
  hired_on: string | null;
  unit_id: string | null;
  unit_name: string | null;
  due: HrDueDate | null;
};

export type HrEmployeeList = {
  rows: HrEmployeeRow[];
  truncated: boolean;
  can_write: boolean;
};

export type HrSyncField = {
  column: string;
  value: string | null;
  mirror: string | null;
  pending: boolean;
};

export type HrIdentity = {
  employee_id: string;
  name: string;
  registration_number: string | null;
  hr_code: string | null;
  cargo: string | null;
  status: string;
  hired_on: string | null;
  terminated_on: string | null;
  employment_type: string | null;
  unit_id: string | null;
  unit_name: string | null;
  company_name: string | null;
  department_name: string | null;
  manager_name: string | null;
};

export type PositionBand = {
  effective_from: string;
  effective_to: string | null;
  cargo: string;
  unit_name: string | null;
};

export type CompensationBand = {
  effective_from: string;
  effective_to: string | null;
  salary: string;
  reason: string | null;
};

export type HrPii = {
  cpf: string | null;
  rg: string | null;
  pis: string | null;
  ctps: string | null;
  birth_date: string | null;
  mother_name: string | null;
  father_name: string | null;
  phone: string | null;
  personal_email: string | null;
};

export type HrDocument = {
  type_name: string;
  issued_on: string | null;
  valid_until: string | null;
  status: string;
};

export type HrExam = {
  type: string;
  performed_on: string;
  valid_until: string | null;
  result: string | null;
};

export type HrLeave = {
  category: string;
  start_date: string;
  end_date: string | null;
  source: string;
};

export type HrMovement = {
  type: string;
  event_date: string;
  notes: string | null;
  unit_name: string | null;
};

export type HrAgreement = {
  id: string;
  type: string;
  description: string | null;
  total_amount: string;
  installment_count: number;
  agreement_date: string;
  status: string;
  pending_installments: number;
};

/** Três estados, não dois: vazio sem explicação parece defeito (§6 da decisão). */
export type HrPhoto = {
  state: "ausente" | "pendente" | "disponivel";
  /** Idade do rosto é dado de tela, como a idade do dado no resto do produto. */
  synced_at: string | null;
};

export type HrEmployeeDetail = {
  employee: HrIdentity;
  sync_fields: HrSyncField[];
  editable_fields: string[];
  /** Os valores aceitos por campo editável, vindos do `check` do banco. */
  enums: Record<string, string[]>;
  can_write: boolean;
  positions: PositionBand[];
  leaves: HrLeave[];
  movements: HrMovement[];
  pii: HrPii | null;
  /**
   * Metadado da foto — nunca os bytes. `null` quando o papel não alcança `pii`.
   * A imagem vem por `GET /rh/employees/{id}/foto`, uma pessoa por requisição.
   * Ver docs/DECISAO-FOTO-DO-COLABORADOR.md §5.
   */
  photo: HrPhoto | null;
  documents: HrDocument[] | null;
  exams: HrExam[] | null;
  compensation: CompensationBand[] | null;
  agreements: HrAgreement[] | null;
};

async function accessToken(): Promise<string | null> {
  const supabase = await getServerSupabase();
  const { data } = await supabase.auth.getSession();

  return data.session?.access_token ?? null;
}

const EMPTY_LIST: HrEmployeeList = {
  rows: [],
  truncated: false,
  can_write: false,
};

export async function loadEmployees(
  filters: RhFilters,
): Promise<HrEmployeeList> {
  const token = await accessToken();

  if (!token) {
    return EMPTY_LIST;
  }

  const query = rhQuery(filters);

  return requestApi<HrEmployeeList>(
    query ? `/rh/employees?${query}` : "/rh/employees",
    { accessToken: token },
  );
}

/** Null when the person is outside the caller's scope, or does not exist. */
export async function loadHrEmployee(
  employeeId: string,
): Promise<HrEmployeeDetail | null> {
  const token = await accessToken();

  if (!token) {
    return null;
  }

  try {
    return await requestApi<HrEmployeeDetail>(`/rh/employees/${employeeId}`, {
      accessToken: token,
    });
  } catch (error) {
    // 404 answers both "does not exist" and "outside your scope", on purpose.
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }

    throw error;
  }
}
