import "server-only";

import { ApiError, requestApi } from "@/lib/api";
import type { MonitorFilters } from "@/lib/monitor/url";
import { slugify, todayInTenantZone } from "@/lib/ponto/filters";
import { getServerSupabase } from "@/lib/supabase-server";

/**
 * Both paths of the contract meet on this screen, and which one carries what is
 * not a style choice.
 *
 * The unit picker is Caminho 1: `vw_unit` under RLS, so the list a supervisor
 * sees has one unit in it and no code here does the filtering. The monitor
 * itself is Caminho 2: it reads `app.expected_workday`, which is not on the
 * public surface, and it is about named people on a specific day.
 *
 * The unit travels to FastAPI as a uuid, but the URL carries the unit *code* —
 * a link inside a WhatsApp message has to be readable, and a code is stable
 * where a uuid is noise. Resolving one to the other happens here, against the
 * units the session can actually see: a code that matches nothing is reported
 * as unknown and the cut stays open, exactly as the dashboard does it.
 */

export type MonitorUnitRow = {
  unit_id: string | null;
  unit_name: string | null;
  /** Headcount. `scheduled + on_vacation + on_leave + day_off + unrostered`. */
  active: number;
  scheduled: number;
  with_indication: number;
  clear: number;
  /** Escalados com marcação até a leitura. Nunca "presentes" — ver `DailyMonitor`. */
  with_punch: number;
  without_punch: number;
  on_vacation: number;
  on_leave: number;
  day_off: number;
  /** Ativo e sem jornada prevista — desenho ou falha de cobertura do motor. */
  unrostered: number;
  off_roster: number;
};

export type Severity = "critical" | "attention" | "watch";

export type MonitorRow = {
  employee_id: string;
  employee_name: string;
  unit_id: string | null;
  unit_name: string | null;
  day_type: string | null;
  expected_entry: string | null;
  expected_exit: string | null;
  confidence: number | null;
  type: string;
  type_description: string;
  direction: string;
  severity: Severity;
  minutes: number;
  expected_time: string | null;
  actual_time: string | null;
  detected_at: string;
};

/**
 * `with_punch` e `without_punch` são a segunda partição dos escalados, e não são
 * "presentes" e "ausentes": a conta é verdadeira em `punches_read_at`, nunca
 * agora, e quem bateu um minuto depois daquela leitura está em `without_punch`.
 * Afirmar presença é a decisão A12 da auditoria, aberta com o dono.
 *
 * `punches_read_at` null = não há leitura de que falar (nunca houve uma, ou o
 * espelho não está neste banco). Os dois números então **não significam nada** e
 * não podem ser mostrados — eles não são zerados, porque zerá-los quebraria
 * `with_punch + without_punch = scheduled`. Quem exibe checa `punches_read_at`.
 */
export type DailyMonitor = {
  day: string;
  active: number;
  scheduled: number;
  with_indication: number;
  clear: number;
  with_punch: number;
  without_punch: number;
  punches_read_at: string | null;
  on_vacation: number;
  on_leave: number;
  day_off: number;
  unrostered: number;
  off_roster: number;
  units: MonitorUnitRow[];
  rows: MonitorRow[];
  truncated: boolean;
};

export type MonitorUnitOption = {
  unitId: string;
  slug: string;
  name: string;
  companyName: string;
};

export type MonitorScreen = {
  today: string;
  filters: MonitorFilters;
  units: MonitorUnitOption[];
  unit: MonitorUnitOption | null;
  unknownUnit: string | null;
  /** Null when FastAPI refused or was unreachable; the screen says so. */
  monitor: DailyMonitor | null;
  unreachable: boolean;
};

export async function loadMonitorScreen(
  filters: MonitorFilters,
): Promise<MonitorScreen> {
  const supabase = await getServerSupabase();
  const today = todayInTenantZone();

  const [unitRows, session] = await Promise.all([
    supabase
      .from("vw_unit")
      .select("unit_id, code, name, company_name")
      .eq("active", true)
      .order("name"),
    supabase.auth.getSession(),
  ]);

  if (unitRows.error) {
    throw new Error(
      `Não foi possível ler as unidades: ${unitRows.error.message}`,
    );
  }

  const units: MonitorUnitOption[] = (unitRows.data ?? []).map((row) => ({
    unitId: row.unit_id ?? "",
    slug: slugify(row.code ?? ""),
    name: row.name ?? "",
    companyName: row.company_name ?? "",
  }));

  const unit = filters.unitCode
    ? (units.find((option) => option.slug === filters.unitCode) ?? null)
    : null;

  const accessToken = session.data.session?.access_token;
  const base = {
    today,
    filters,
    units,
    unit,
    unknownUnit: filters.unitCode && !unit ? filters.unitCode : null,
  };

  if (!accessToken) {
    return { ...base, monitor: null, unreachable: true };
  }

  const query = new URLSearchParams({ dia: filters.day });

  if (unit) {
    query.set("unidade", unit.unitId);
  }

  try {
    const monitor = await requestApi<DailyMonitor>(`/monitor/diario?${query}`, {
      accessToken,
    });

    return { ...base, monitor, unreachable: false };
  } catch (error) {
    // The API being down is not the same as a day with nothing on it, and the
    // difference matters more here than anywhere else in the product: an empty
    // monitor reads as "everything is fine".
    if (error instanceof ApiError) {
      return { ...base, monitor: null, unreachable: true };
    }

    throw error;
  }
}
