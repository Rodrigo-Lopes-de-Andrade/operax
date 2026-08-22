import {
  toSearchParams,
  type PontoFilters,
  type RawSearchParams,
} from "@/lib/ponto/filters";

/** The point-management screen is the landing screen of the panel. */
export const PONTO_PATH = "/dashboard";

/** Page sizes the occurrences table offers. */
export const PAGE_SIZES = [25, 50, 100] as const;
export type PageSize = (typeof PAGE_SIZES)[number];
export const DEFAULT_PAGE_SIZE: PageSize = 25;

export type Paging = { page: number; pageSize: PageSize };

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function parsePaging(params: RawSearchParams): Paging {
  const page = Number(first(params.pg));
  const size = Number(first(params.tam));

  return {
    page: Number.isInteger(page) && page > 0 ? page : 1,
    pageSize: (PAGE_SIZES as readonly number[]).includes(size)
      ? (size as PageSize)
      : DEFAULT_PAGE_SIZE,
  };
}

/**
 * Every link on the screen is built here, so the cut in the URL is the only
 * copy of the filter state — a chip, the period control and the pagination all
 * write to the same place the WhatsApp link reads from.
 *
 * Changing a filter sends the table back to page one: keeping page 7 while
 * narrowing to one unit lands the manager on an empty page.
 */
export function pontoHref(
  filters: PontoFilters,
  paging: Paging,
  overrides: Partial<PontoFilters & Paging> = {},
): string {
  const next: PontoFilters = {
    period: overrides.period ?? filters.period,
    unitCode:
      overrides.unitCode !== undefined ? overrides.unitCode : filters.unitCode,
    companySlug:
      overrides.companySlug !== undefined
        ? overrides.companySlug
        : filters.companySlug,
    eventId:
      overrides.eventId !== undefined ? overrides.eventId : filters.eventId,
  };

  const filtersChanged =
    next.period !== filters.period ||
    next.unitCode !== filters.unitCode ||
    next.companySlug !== filters.companySlug;

  const pageSize = overrides.pageSize ?? paging.pageSize;
  const page =
    overrides.page ??
    (filtersChanged || pageSize !== paging.pageSize ? 1 : paging.page);

  const params = toSearchParams(next);

  if (page > 1) {
    params.set("pg", String(page));
  }
  if (pageSize !== DEFAULT_PAGE_SIZE) {
    params.set("tam", String(pageSize));
  }

  const query = params.toString();

  return query ? `${PONTO_PATH}?${query}` : PONTO_PATH;
}
