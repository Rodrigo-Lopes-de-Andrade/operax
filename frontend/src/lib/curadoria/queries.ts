import "server-only";

import { ApiError, requestApi } from "@/lib/api";
import { getServerSupabase } from "@/lib/supabase-server";

/**
 * Caminho 2, e não poderia ser outro: a curadoria escreve, e escreve numa tabela
 * cuja policy é `util.is_admin`. O backend pergunta a permissão ao banco, como o
 * usuário, antes de abrir qualquer transação.
 */

export type UnitOption = {
  unit_id: string;
  code: string;
  name: string;
  company_id: string;
  company_name: string;
};

export type UnitSuggestion = {
  unit_id: string;
  unit_name: string;
  /** Semelhança de nome, e nada mais. Não é gravada em lugar nenhum. */
  confidence: number;
};

export type UnitMappingRow = {
  secullum_department_id: number;
  department: string;
  company_id: string;
  company_name: string;
  employees: number;
  unmapped: number;
  unit_id: string | null;
  unit_name: string | null;
  validated_at: string | null;
  suggestion: UnitSuggestion | null;
};

export type UnitMappingScreen = {
  rows: UnitMappingRow[];
  units: UnitOption[];
  active: number;
  /** Exclui o provisório de propósito — ver o cartão da tela. */
  validated: number;
  provisional: number;
  without_unit: number;
};

/** Null quando o papel não alcança a curadoria, ou a sessão acabou. */
export async function loadUnitMapping(): Promise<UnitMappingScreen | null> {
  const supabase = await getServerSupabase();
  const { data } = await supabase.auth.getSession();
  const accessToken = data.session?.access_token;

  if (!accessToken) {
    return null;
  }

  try {
    return await requestApi<UnitMappingScreen>("/curadoria/unidades", {
      accessToken,
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      return null;
    }

    throw error;
  }
}
