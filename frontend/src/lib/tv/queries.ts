import "server-only";

import { slugify, todayInTenantZone } from "@/lib/ponto/filters";
import { getServerSupabase } from "@/lib/supabase-server";
import type { TvFilters } from "@/lib/tv/url";

/**
 * Caminho 1 only, and deliberately the narrow half of it.
 *
 * The board hangs where anyone walking past can read it, so the rule is not
 * "hide the names" — it is that no query on this screen returns one. That is
 * why `vw_deviation_event` and `vw_deviation_by_employee_day` are absent here
 * even though the session could read them: a screen that never asks for a name
 * cannot leak one through a refactor, a tooltip or a mistake.
 *
 * `vw_unit` gives the units, and the day's summary is left-joined onto it in
 * memory: a unit with nothing today has to appear as "sem indício", not vanish.
 * A missing tile reads as a broken board.
 */

export type TvUnit = {
  unitId: string;
  slug: string;
  name: string;
  eventos: number;
  colaboradores: number;
  minutesAbs: number;
};

export type TvTrendDay = { day: string; eventos: number };

export type TvBoard = {
  today: string;
  unitName: string | null;
  unknownUnit: string | null;
  eventos: number;
  colaboradores: number;
  minutesExcedente: number;
  minutesFaltante: number;
  unidadesAfetadas: number;
  units: TvUnit[];
  trend: TvTrendDay[];
  /** Null when a block failed; the board shows the gap instead of a zero. */
  degraded: boolean;
};

const TREND_DAYS = 7;

function shiftDays(day: string, days: number): string {
  const [year, month, date] = day.split("-").map(Number);

  return new Date(Date.UTC(year, month - 1, date + days))
    .toISOString()
    .slice(0, 10);
}

export async function loadTvBoard(filters: TvFilters): Promise<TvBoard> {
  const supabase = await getServerSupabase();
  const today = todayInTenantZone();
  const from = shiftDays(today, -(TREND_DAYS - 1));

  const unitRows = await supabase
    .from("vw_unit")
    .select("unit_id, code, name")
    .eq("active", true)
    .order("name");

  if (unitRows.error) {
    throw new Error(
      `Não foi possível ler as unidades: ${unitRows.error.message}`,
    );
  }

  const allUnits = (unitRows.data ?? []).map((row) => ({
    unitId: row.unit_id ?? "",
    slug: slugify(row.code ?? ""),
    name: row.name ?? "",
  }));

  const unit = filters.unitCode
    ? (allUnits.find((option) => option.slug === filters.unitCode) ?? null)
    : null;
  const scoped = unit ? [unit] : allUnits;

  const [kpiResult, summaryResult, trendResult] = await Promise.all([
    supabase.rpc("fn_kpi_period", {
      p_de: today,
      p_ate: today,
      p_unit_id: unit?.unitId,
    }),
    (() => {
      const query = supabase
        .from("vw_deviation_summary_by_unit")
        .select("unit_id, eventos, colaboradores, minutes_abs")
        .eq("reference_date", today);

      return unit ? query.eq("unit_id", unit.unitId) : query;
    })(),
    (() => {
      const query = supabase
        .from("vw_deviation_daily_trend")
        .select("reference_date, eventos")
        .gte("reference_date", from)
        .lte("reference_date", today);

      return unit ? query.eq("unit_id", unit.unitId) : query;
    })(),
  ]);

  const kpi = kpiResult.data?.[0];
  const summary = new Map(
    (summaryResult.data ?? []).map((row) => [row.unit_id, row]),
  );

  const trendByDay = new Map<string, number>(
    Array.from({ length: TREND_DAYS }, (_, index) => [
      shiftDays(from, index),
      0,
    ]),
  );

  for (const row of trendResult.data ?? []) {
    const day = row.reference_date ?? "";

    if (trendByDay.has(day)) {
      trendByDay.set(day, (trendByDay.get(day) ?? 0) + (row.eventos ?? 0));
    }
  }

  return {
    today,
    unitName: unit?.name ?? null,
    unknownUnit: filters.unitCode && !unit ? filters.unitCode : null,
    eventos: kpi?.eventos ?? 0,
    colaboradores: kpi?.colaboradores_afetados ?? 0,
    minutesExcedente: kpi?.minutes_excedente ?? 0,
    minutesFaltante: kpi?.minutes_faltante ?? 0,
    unidadesAfetadas: kpi?.unidades_afetadas ?? 0,
    units: scoped
      .map((option) => {
        const row = summary.get(option.unitId);

        return {
          ...option,
          eventos: row?.eventos ?? 0,
          colaboradores: row?.colaboradores ?? 0,
          minutesAbs: row?.minutes_abs ?? 0,
        };
      })
      .sort((a, b) => b.eventos - a.eventos || a.name.localeCompare(b.name)),
    trend: [...trendByDay.entries()].map(([day, eventos]) => ({
      day,
      eventos,
    })),
    degraded: Boolean(
      kpiResult.error || summaryResult.error || trendResult.error,
    ),
  };
}
