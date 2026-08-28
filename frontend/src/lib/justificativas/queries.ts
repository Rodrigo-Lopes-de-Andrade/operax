import "server-only";

import type { Database } from "@/lib/database.types";
import type { PendingFilters } from "@/lib/justificativas/url";
import {
  periodRange,
  todayInTenantZone,
  type DateRange,
} from "@/lib/ponto/filters";
import {
  loadOccurrence,
  loadUnits,
  type Occurrence,
  type UnitOption,
} from "@/lib/ponto/queries";
import type { PageSize } from "@/lib/ponto/url";
import { getServerSupabase } from "@/lib/supabase-server";

/**
 * A fila de pendentes de justificativa.
 *
 * `public.fn_pending_justification` (migration 23) é `security invoker` e roda
 * como quem perguntou: a fila de um supervisor traz a unidade dele e nada mais,
 * e isso é propriedade do banco, não deste arquivo. É Caminho 1 do contrato,
 * como o resto do dashboard.
 *
 * ⚠️ A função devolve a EXISTÊNCIA da pendência, nunca o texto de justificativa
 * nenhuma — é o que o comentário dela declara, e é por isso que a fila pode ser
 * lida pelo navegador enquanto o veredito continua passando pelo FastAPI.
 */
type Functions = Database["public"]["Functions"];

export type PendingRow =
  Functions["fn_pending_justification"]["Returns"][number];

export type PendingScreen = {
  units: UnitOption[];
  unit: UnitOption | null;
  /** Uma unidade que veio no link e não corresponde a nada que o usuário vê. */
  unknownUnit: string | null;
  range: DateRange;
  rows: PendingRow[];
  total: number;
  page: number;
  pageSize: PageSize;
  selected: Occurrence | null;
};

export async function loadPendingScreen(
  filters: PendingFilters,
  page: number,
  pageSize: PageSize,
): Promise<PendingScreen> {
  const supabase = await getServerSupabase();
  const range = periodRange(filters.period, todayInTenantZone());
  const units = await loadUnits(supabase);

  const unit = filters.unitCode
    ? (units.find((option) => option.slug === filters.unitCode) ?? null)
    : null;

  const from = (page - 1) * pageSize;

  const [pendingResult, selected] = await Promise.all([
    supabase
      .rpc(
        "fn_pending_justification",
        { p_de: range.de, p_ate: range.ate, p_unit_id: unit?.unitId },
        { count: "exact" },
      )
      .range(from, from + pageSize - 1),
    filters.eventId
      ? loadOccurrence(supabase, filters.eventId)
      : Promise.resolve(null),
  ]);

  // A lista É a tela: degradar para vazio aqui diria "nada pendente" quando o
  // que houve foi uma leitura que não aconteceu.
  if (pendingResult.error) {
    throw new Error(
      `Não foi possível ler a fila de justificativas: ${pendingResult.error.message}`,
    );
  }

  return {
    units,
    unit,
    unknownUnit: filters.unitCode && !unit ? filters.unitCode : null,
    range,
    rows: pendingResult.data ?? [],
    total: pendingResult.count ?? 0,
    page,
    pageSize,
    selected,
  };
}
