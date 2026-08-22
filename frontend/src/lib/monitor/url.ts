import { slugify, type RawSearchParams } from "@/lib/ponto/filters";

/**
 * The cut of the daily monitor: a day and a unit, both in the query string.
 *
 * The day is here for the same reason the period is on the dashboard — the
 * alert that leaves by WhatsApp carries a link, and "look at what happened
 * yesterday at Aeroporto" has to survive the hop. It is not a picker with
 * state: `?dia=` is the whole of it.
 */
export const MONITOR_PATH = "/dashboard/monitor";

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

export type MonitorFilters = {
  /** `YYYY-MM-DD`. Never in the future: the monitor watches, it does not forecast. */
  day: string;
  /** `app.unit.code`, lowercased. */
  unitCode: string | null;
};

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/**
 * A day that is not a day, or a day after today, falls back to today rather
 * than to an error: a stale link in a WhatsApp thread must open the monitor,
 * not a stack trace. A day in the past is honoured — that is the point of the
 * parameter.
 */
export function parseMonitorFilters(
  params: RawSearchParams,
  today: string,
): MonitorFilters {
  const day = first(params.dia);
  const unit = first(params.un);

  return {
    day: day && ISO_DAY.test(day) && day <= today ? day : today,
    unitCode: unit ? slugify(unit) : null,
  };
}

export function monitorHref(
  filters: MonitorFilters,
  today: string,
  overrides: Partial<MonitorFilters> = {},
): string {
  const day = overrides.day ?? filters.day;
  const unitCode =
    overrides.unitCode !== undefined ? overrides.unitCode : filters.unitCode;

  const params = new URLSearchParams();

  // Today is the default, so the everyday link stays short enough to read
  // inside a message: `/dashboard/monitor?un=dev-norte`.
  if (day !== today) {
    params.set("dia", day);
  }
  if (unitCode) {
    params.set("un", unitCode);
  }

  const query = params.toString();

  return query ? `${MONITOR_PATH}?${query}` : MONITOR_PATH;
}

/** Calendar arithmetic, never local-`Date` arithmetic — see `ponto/filters`. */
export function shiftDay(day: string, days: number): string {
  const [year, month, date] = day.split("-").map(Number);

  return new Date(Date.UTC(year, month - 1, date + days))
    .toISOString()
    .slice(0, 10);
}
