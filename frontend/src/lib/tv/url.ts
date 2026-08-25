import { slugify, type RawSearchParams } from "@/lib/ponto/filters";

/**
 * The wall board. Outside `/dashboard` because it has no chrome: no sidebar, no
 * user badge, and above all no sign-out button — a screen nobody is sitting at
 * does not need a control that logs the whole floor out by accident.
 */
export const TV_PATH = "/tv";

/**
 * How often the board asks the server for the route again.
 *
 * Not the cadence of the data — the sync runs every 30 minutes — but often
 * enough that the age printed on screen is never far from the truth. A board
 * runs for weeks, so this is a cost that repeats about twenty times an hour,
 * forever.
 */
export const TV_REFRESH_SECONDS = 180;

export type TvFilters = {
  /** `app.unit.code`, lowercased. One board per site is the common setup. */
  unitCode: string | null;
};

export function parseTvFilters(params: RawSearchParams): TvFilters {
  const unit = Array.isArray(params.un) ? params.un[0] : params.un;

  return { unitCode: unit ? slugify(unit) : null };
}

export function tvHref(unitCode: string | null): string {
  return unitCode ? `${TV_PATH}?un=${unitCode}` : TV_PATH;
}
