import "server-only";

import type { SupabaseClient } from "@supabase/supabase-js";

import type { Database } from "@/lib/database.types";
import {
  eachDay,
  periodRange,
  slugify,
  todayInTenantZone,
  type DateRange,
  type PontoFilters,
} from "@/lib/ponto/filters";
import type { PageSize } from "@/lib/ponto/url";
import { getServerSupabase } from "@/lib/supabase-server";

/**
 * Every read on this screen is Caminho 1 of the contract: the browser session
 * talks to Supabase with the anon key, and RLS decides what comes back. The
 * client never sends a tenant, and a unit outside the user's scope is not
 * filtered out by this code — it never arrives. That is what makes "a unit
 * supervisor does not see another unit" a property of the database instead of a
 * property of this file.
 *
 * Reads happen on the server so the first paint already carries the numbers;
 * the cut is in the URL, so the server has everything it needs to run them.
 */

type Views = Database["public"]["Views"];
type Functions = Database["public"]["Functions"];

export type UnitOption = {
  unitId: string;
  code: string;
  slug: string;
  name: string;
  companyId: string;
  companyName: string;
  companySlug: string;
};

export type Kpi = Functions["fn_kpi_period"]["Returns"][number];
export type UnitRank = Functions["fn_ranking_by_unit"]["Returns"][number];
export type EmployeeRank =
  Functions["fn_ranking_by_employee"]["Returns"][number];
export type Recurrence = Functions["fn_recurrence"]["Returns"][number];
/**
 * O gestor vem de `app.manager`, promovido de `secullum."Estrutura"` — e não de
 * `employee.manager_employee_id`, que aponta para um colaborador e continua sem
 * fonte. `manager_id` nulo é uma linha legítima: quem o espelho não diz a quem
 * responde tem de aparecer como "sem gestor", não sumir do ranking.
 */
export type ManagerRank = Functions["fn_ranking_by_manager"]["Returns"][number];

export type Occurrence = {
  eventoId: string;
  referenceDate: string;
  unitName: string | null;
  employeeName: string;
  employeeId: string;
  type: string;
  typeDescription: string;
  direction: string;
  minutes: number;
  minutesAbs: number;
  expectedTime: string | null;
  actualTime: string | null;
  pendenteDeCiclo: boolean;
  detectedAt: string;
};

export type TrendDay = { day: string; surplus: number; shortfall: number };

export type TypeCount = { type: string; description: string; eventos: number };

/** The diverging chart is context, not cut: it always looks back 14 days. */
const TREND_DAYS = 14;
/**
 * Counting occurrences by type client-side is exact only while the whole cut
 * fits in one read. Past this the strip says so instead of showing a number
 * that quietly stopped counting.
 */
const TYPE_COUNT_CAP = 2000;

const OCCURRENCE_COLUMNS =
  "evento_id, reference_date, unit_name, employee_id, employee_name, type, type_description, direction, minutes, minutes_abs, expected_time, actual_time, pendente_de_ciclo, detected_at";

type OccurrenceRow = Pick<
  Views["vw_deviation_event"]["Row"],
  | "evento_id"
  | "reference_date"
  | "unit_name"
  | "employee_id"
  | "employee_name"
  | "type"
  | "type_description"
  | "direction"
  | "minutes"
  | "minutes_abs"
  | "expected_time"
  | "actual_time"
  | "pendente_de_ciclo"
  | "detected_at"
>;

function toOccurrence(row: OccurrenceRow): Occurrence {
  return {
    eventoId: row.evento_id ?? "",
    referenceDate: row.reference_date ?? "",
    unitName: row.unit_name,
    employeeId: row.employee_id ?? "",
    employeeName: row.employee_name ?? "",
    type: row.type ?? "",
    typeDescription: row.type_description ?? "",
    direction: row.direction ?? "neutral",
    minutes: row.minutes ?? 0,
    minutesAbs: row.minutes_abs ?? 0,
    expectedTime: row.expected_time,
    actualTime: row.actual_time,
    pendenteDeCiclo: row.pendente_de_ciclo ?? false,
    detectedAt: row.detected_at ?? "",
  };
}

/**
 * As unidades que a sessão alcança, na ordem em que os seletores as mostram.
 *
 * Uma definição só porque o slug é contrato de URL: duas telas derivando-o de
 * jeitos diferentes fariam o mesmo link abrir recortes diferentes.
 */
export async function loadUnits(
  supabase: SupabaseClient<Database>,
): Promise<UnitOption[]> {
  const unitRows = await supabase
    .from("vw_unit")
    .select("unit_id, code, name, company_id, company_name")
    .eq("active", true)
    .order("name");

  if (unitRows.error) {
    throw new Error(
      `Não foi possível ler as unidades: ${unitRows.error.message}`,
    );
  }

  return (unitRows.data ?? []).map((row) => ({
    unitId: row.unit_id ?? "",
    code: row.code ?? "",
    slug: slugify(row.code ?? ""),
    name: row.name ?? "",
    companyId: row.company_id ?? "",
    companyName: row.company_name ?? "",
    companySlug: slugify(row.company_name ?? ""),
  }));
}

/**
 * Uma ocorrência, para o detalhe que o `?ev=` abre. Devolve null tanto para o
 * indício revogado quanto para o que está fora do alcance de quem pediu — a
 * RLS não distingue os dois, e a tela também não deve fingir que distingue.
 */
export async function loadOccurrence(
  supabase: SupabaseClient<Database>,
  eventId: string,
): Promise<Occurrence | null> {
  const { data } = await supabase
    .from("vw_deviation_event")
    .select(OCCURRENCE_COLUMNS)
    .eq("evento_id", eventId)
    .maybeSingle();

  return data ? toOccurrence(data) : null;
}

export type Resolved = {
  units: UnitOption[];
  unit: UnitOption | null;
  company: { id: string; name: string; slug: string } | null;
  /** A key that came in the link and matches nothing the user can see. */
  unknownUnit: string | null;
  unknownCompany: string | null;
};

export type PontoScreen = Resolved & {
  today: string;
  range: DateRange;
  trendRange: DateRange;
  kpi: Kpi;
  occurrences: Occurrence[];
  occurrenceTotal: number;
  page: number;
  pageSize: PageSize;
  selected: Occurrence | null;
  /** Null when the block failed to load; the block renders its own state. */
  trend: TrendDay[] | null;
  byType: TypeCount[] | null;
  byTypeTruncated: boolean;
  unitRanking: UnitRank[] | null;
  employeeRanking: EmployeeRank[] | null;
  managerRanking: ManagerRank[] | null;
  recurrence: Recurrence[] | null;
};

const EMPTY_KPI: Kpi = {
  eventos: 0,
  colaboradores_afetados: 0,
  minutes_excedente: 0,
  minutes_faltante: 0,
  minutes_abs: 0,
  unidades_afetadas: 0,
  eventos_pendentes_ciclo: 0,
};

function shiftDays(day: string, days: number): string {
  const [year, month, date] = day.split("-").map(Number);

  return new Date(Date.UTC(year, month - 1, date + days))
    .toISOString()
    .slice(0, 10);
}

export async function loadPontoScreen(
  filters: PontoFilters,
  page: number,
  pageSize: PageSize,
): Promise<PontoScreen> {
  const supabase = await getServerSupabase();
  const today = todayInTenantZone();
  const range = periodRange(filters.period, today);
  const trendRange: DateRange = {
    de: shiftDays(range.ate, -(TREND_DAYS - 1)),
    ate: range.ate,
  };

  const units = await loadUnits(supabase);

  const unit = filters.unitCode
    ? (units.find((option) => option.slug === filters.unitCode) ?? null)
    : null;
  const companyUnit = filters.companySlug
    ? (units.find((option) => option.companySlug === filters.companySlug) ??
      null)
    : null;
  const company = companyUnit
    ? {
        id: companyUnit.companyId,
        name: companyUnit.companyName,
        slug: companyUnit.companySlug,
      }
    : null;

  // The unit filter wins: a link that names both and disagrees is answered by
  // the narrower one, never by the union.
  const companyId = unit ? undefined : (company?.id ?? undefined);
  const unitId = unit?.unitId;

  const from = (page - 1) * pageSize;

  const [
    kpiResult,
    occurrenceResult,
    trendResult,
    typeResult,
    unitRankResult,
    employeeRankResult,
    managerRankResult,
    recurrenceResult,
    selectedResult,
  ] = await Promise.all([
    supabase.rpc("fn_kpi_period", {
      p_de: range.de,
      p_ate: range.ate,
      p_company_id: companyId,
      p_unit_id: unitId,
    }),
    (() => {
      let query = supabase
        .from("vw_deviation_event")
        .select(OCCURRENCE_COLUMNS, { count: "exact" })
        .gte("reference_date", range.de)
        .lte("reference_date", range.ate)
        .order("reference_date", { ascending: false })
        .order("detected_at", { ascending: false })
        .range(from, from + pageSize - 1);

      if (unitId) {
        query = query.eq("unit_id", unitId);
      } else if (companyId) {
        query = query.eq("company_id", companyId);
      }

      return query;
    })(),
    (() => {
      let query = supabase
        .from("vw_deviation_daily_trend")
        .select("reference_date, direction, eventos, minutes_abs")
        .gte("reference_date", trendRange.de)
        .lte("reference_date", trendRange.ate);

      if (unitId) {
        query = query.eq("unit_id", unitId);
      } else if (company) {
        // The trend view has no company column, so the cut is expressed as the
        // units of that company.
        query = query.in(
          "unit_id",
          units
            .filter((option) => option.companyId === company.id)
            .map((option) => option.unitId),
        );
      }

      return query;
    })(),
    (() => {
      let query = supabase
        .from("vw_deviation_event")
        .select("type, type_description")
        .gte("reference_date", range.de)
        .lte("reference_date", range.ate)
        .limit(TYPE_COUNT_CAP);

      if (unitId) {
        query = query.eq("unit_id", unitId);
      } else if (companyId) {
        query = query.eq("company_id", companyId);
      }

      return query;
    })(),
    supabase.rpc("fn_ranking_by_unit", {
      p_de: range.de,
      p_ate: range.ate,
      p_company_id: companyId,
      p_limite: 6,
    }),
    supabase.rpc("fn_ranking_by_employee", {
      p_de: range.de,
      p_ate: range.ate,
      p_company_id: companyId,
      p_unit_id: unitId,
      p_limite: 6,
    }),
    supabase.rpc("fn_ranking_by_manager", {
      p_de: range.de,
      p_ate: range.ate,
      p_company_id: companyId,
      p_unit_id: unitId,
      p_limite: 6,
    }),
    supabase.rpc("fn_recurrence", {
      p_de: range.de,
      p_ate: range.ate,
      p_min_dias: 3,
      p_unit_id: unitId,
    }),
    filters.eventId
      ? loadOccurrence(supabase, filters.eventId)
      : Promise.resolve(null),
  ]);

  if (occurrenceResult.error) {
    throw new Error(
      `Não foi possível ler as ocorrências: ${occurrenceResult.error.message}`,
    );
  }

  const typeRows = typeResult.error ? null : (typeResult.data ?? []);
  const byType = typeRows ? countByType(typeRows) : null;

  return {
    units,
    unit,
    company,
    unknownUnit: filters.unitCode && !unit ? filters.unitCode : null,
    unknownCompany:
      filters.companySlug && !company ? filters.companySlug : null,
    today,
    range,
    trendRange,
    kpi: kpiResult.error ? EMPTY_KPI : (kpiResult.data?.[0] ?? EMPTY_KPI),
    occurrences: (occurrenceResult.data ?? []).map(toOccurrence),
    occurrenceTotal: occurrenceResult.count ?? 0,
    page,
    pageSize,
    selected: selectedResult,
    trend: trendResult.error
      ? null
      : foldTrend(trendResult.data ?? [], trendRange),
    byType,
    byTypeTruncated: (typeRows?.length ?? 0) >= TYPE_COUNT_CAP,
    unitRanking: unitRankResult.error ? null : (unitRankResult.data ?? []),
    employeeRanking: employeeRankResult.error
      ? null
      : (employeeRankResult.data ?? []),
    managerRanking: managerRankResult.error
      ? null
      : (managerRankResult.data ?? []),
    recurrence: recurrenceResult.error ? null : (recurrenceResult.data ?? []),
  };
}

type TrendRow = Pick<
  Views["vw_deviation_daily_trend"]["Row"],
  "reference_date" | "direction" | "eventos" | "minutes_abs"
>;

/**
 * The view is grouped by day, unit and direction, so one day arrives as several
 * rows. Folding here is what the view's own comment asks the client to do —
 * the heavy work stays in Postgres, the sum is trivial.
 *
 * A day with no occurrence still gets a bar of zero: a gap in the x axis would
 * read as "no data" when it means "nothing happened".
 */
function foldTrend(rows: TrendRow[], range: DateRange): TrendDay[] {
  const byDay = new Map<string, TrendDay>(
    eachDay(range).map((day) => [day, { day, surplus: 0, shortfall: 0 }]),
  );

  for (const row of rows) {
    const day = byDay.get(row.reference_date ?? "");

    if (!day) {
      continue;
    }
    if (row.direction === "surplus") {
      day.surplus += row.minutes_abs ?? 0;
    } else if (row.direction === "shortfall") {
      day.shortfall += row.minutes_abs ?? 0;
    }
  }

  return [...byDay.values()];
}

function countByType(
  rows: { type: string | null; type_description: string | null }[],
): TypeCount[] {
  const counts = new Map<string, TypeCount>();

  for (const row of rows) {
    const type = row.type ?? "";
    const current = counts.get(type);

    if (current) {
      current.eventos += 1;
    } else {
      counts.set(type, {
        type,
        description: row.type_description ?? type,
        eventos: 1,
      });
    }
  }

  return [...counts.values()].sort((a, b) => b.eventos - a.eventos);
}
