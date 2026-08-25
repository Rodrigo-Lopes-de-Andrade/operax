/**
 * The filter cut ("recorte") of the point-management screen, encoded in the
 * query string.
 *
 * Filter state lives in the URL and nowhere else (CLAUDE.md): the alert that
 * leaves by WhatsApp carries a link, and that link has to open the dashboard
 * already filtered on the manager's phone. A value that lived in React state
 * would be lost on the first hop.
 *
 * Keys are short because the whole thing is read by a human inside a WhatsApp
 * message: `?un=dev-norte&per=hoje&ev=…`.
 */

export const PERIODS = ["hoje", "7d", "30d", "mes"] as const;

export type Period = (typeof PERIODS)[number];

export const DEFAULT_PERIOD: Period = "7d";

export const PERIOD_LABEL: Record<Period, string> = {
  hoje: "Hoje",
  "7d": "7 dias",
  "30d": "30 dias",
  mes: "Mês atual",
};

export const TENANT_TIME_ZONE = "America/Sao_Paulo";

export type PontoFilters = {
  period: Period;
  /** `app.unit.code`, lowercased. Stable and unique per tenant. */
  unitCode: string | null;
  /** Slug of the company trade name, resolved against the units the user can see. */
  companySlug: string | null;
  /** Occurrence the link points at — opens the drawer straight away. */
  eventId: string | null;
};

/** Shape Next hands to a page as `searchParams`. */
export type RawSearchParams = Record<string, string | string[] | undefined>;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/**
 * Turns a name into the key that travels in the URL. Accent-insensitive so
 * "Rodoviária" and a link typed without the accent land on the same company.
 */
export function slugify(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function parseFilters(params: RawSearchParams): PontoFilters {
  const period = first(params.per);
  const unit = first(params.un);
  const company = first(params.emp);
  const event = first(params.ev);

  return {
    period: PERIODS.includes(period as Period)
      ? (period as Period)
      : DEFAULT_PERIOD,
    unitCode: unit ? slugify(unit) : null,
    companySlug: company ? slugify(company) : null,
    eventId: event && UUID.test(event) ? event.toLowerCase() : null,
  };
}

/**
 * Back to a query string. The default period is omitted so that a clean cut
 * gives a clean URL — the screen prints it for the user to read and copy.
 */
export function toSearchParams(filters: PontoFilters): URLSearchParams {
  const params = new URLSearchParams();

  if (filters.companySlug) {
    params.set("emp", filters.companySlug);
  }
  if (filters.unitCode) {
    params.set("un", filters.unitCode);
  }
  if (filters.period !== DEFAULT_PERIOD) {
    params.set("per", filters.period);
  }
  if (filters.eventId) {
    params.set("ev", filters.eventId);
  }

  return params;
}

export type DateRange = { de: string; ate: string };

/** `YYYY-MM-DD` for the tenant's own day, not the server's. */
export function todayInTenantZone(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: TENANT_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

/**
 * Date arithmetic on the calendar day, never on a local `Date`: the range that
 * goes to `fn_kpi_period` is a `date` in Postgres, and an off-by-one hour must
 * not become an off-by-one day at 21:00 in São Paulo.
 */
function shiftDays(day: string, days: number): string {
  const [year, month, date] = day.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, date + days));

  return shifted.toISOString().slice(0, 10);
}

export function periodRange(period: Period, today: string): DateRange {
  switch (period) {
    case "hoje":
      return { de: today, ate: today };
    case "30d":
      return { de: shiftDays(today, -29), ate: today };
    case "mes":
      return { de: `${today.slice(0, 7)}-01`, ate: today };
    case "7d":
      return { de: shiftDays(today, -6), ate: today };
  }
}

/** Days of the range, oldest first — the x axis of the trend chart. */
export function eachDay({ de, ate }: DateRange): string[] {
  const days: string[] = [];

  for (let day = de; day <= ate; day = shiftDays(day, 1)) {
    days.push(day);
  }

  return days;
}
