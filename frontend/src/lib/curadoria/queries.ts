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

/**
 * A fila de rotação — o outro eixo da mesma curadoria.
 *
 * O horário vem do sistema de ponto e o ciclo é nosso, porque `HorarioDia` é uma
 * semana fixa de sete dias e um 12x36 é ciclo de 48 h: sete não é múltiplo de
 * dois, e o padrão nunca fecha na semana.
 */
export type RotationRow = {
  secullum_schedule_id: number;
  schedule: string;
  employees: number;
  /**
   * Quantos desses já estão fora do motor por decisão. Um horário em branco tem
   * duas respostas possíveis, e esta é a outra: não falta rotação, não há
   * jornada devida.
   */
  out_of_engine: number;
  cycle_length_days: number | null;
  anchor_date: string | null;
  expected_entry: string | null;
  expected_exit: string | null;
  expected_break_minutes: number | null;
  workload_minutes: number | null;
  tolerance_extra_minutes: number | null;
  tolerance_absence_minutes: number | null;
  validated_at: string | null;
  /**
   * Os dias em que este horário de fato bateu ponto. Está aqui para o curador
   * conferir a âncora contra a realidade — e não para o sistema deduzi-la:
   * escala derivada das batidas encaixa sempre, e escala que encaixa sempre
   * nunca acusa falta.
   */
  observed_days: string[];
};

export type RotationScreen = {
  rows: RotationRow[];
  on_blank_schedule: number;
  /** Exclui o provisório: rotação sem carimbo o motor não lê. */
  validated: number;
  provisional: number;
};

/** Null quando o papel não alcança a curadoria, ou a sessão acabou. */
export async function loadRotationQueue(): Promise<RotationScreen | null> {
  const supabase = await getServerSupabase();
  const { data } = await supabase.auth.getSession();
  const accessToken = data.session?.access_token;

  if (!accessToken) {
    return null;
  }

  try {
    return await requestApi<RotationScreen>("/curadoria/rotacoes", {
      accessToken,
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      return null;
    }

    throw error;
  }
}
