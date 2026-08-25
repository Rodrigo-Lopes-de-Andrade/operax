import type { RawSearchParams } from "@/lib/ponto/filters";

export const ADMIN_PATH = "/dashboard/administracao";
export const COLABORADORES_PATH = `${ADMIN_PATH}/colaboradores`;
export const IMPORTACAO_PATH = `${ADMIN_PATH}/importacao`;

export const STATUSES = [
  "active",
  "afastado",
  "vacation",
  "desligado",
] as const;
export type Status = (typeof STATUSES)[number];

export const PENDENCIAS = [
  "vinculo",
  "aso",
  "documento",
  "experiencia",
] as const;
export type Pendencia = (typeof PENDENCIAS)[number];

/**
 * The tabs of the detail. Which of them exist for a given person is decided by
 * the API — a block that arrives `null` has no tab at all — so this list is the
 * vocabulary, not the permission.
 */
export const TABS = [
  "cadastro",
  "posicao",
  "pessoais",
  "saude",
  "remuneracao",
  "afastamentos",
  "movimentacoes",
  "acordos",
] as const;
export type Tab = (typeof TABS)[number];
export const DEFAULT_TAB: Tab = "cadastro";

export type RhFilters = {
  unit: string | null;
  status: Status | null;
  pendencia: Pendencia | null;
  busca: string | null;
};

export const EMPTY_FILTERS: RhFilters = {
  unit: null,
  status: null,
  pendencia: null,
  busca: null,
};

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function oneOf<T extends string>(
  value: string | undefined,
  allowed: readonly T[],
): T | null {
  return value && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : null;
}

/**
 * The cut lives in the query string, never in component state: the list a
 * colleague is asked to look at is a link, and the browser's back button walks
 * the user's own filter history.
 */
export function parseRhFilters(params: RawSearchParams): RhFilters {
  const busca = first(params.q)?.trim();

  return {
    unit: first(params.un) ?? null,
    status: oneOf(first(params.st), STATUSES),
    pendencia: oneOf(first(params.pd), PENDENCIAS),
    busca: busca ? busca : null,
  };
}

export function parseTab(params: RawSearchParams): Tab {
  return oneOf(first(params.aba), TABS) ?? DEFAULT_TAB;
}

export function rhHref(
  filters: RhFilters,
  overrides: Partial<RhFilters> = {},
): string {
  const next: RhFilters = { ...filters, ...overrides };
  const query = new URLSearchParams();

  if (next.unit) query.set("un", next.unit);
  if (next.status) query.set("st", next.status);
  if (next.pendencia) query.set("pd", next.pendencia);
  if (next.busca) query.set("q", next.busca);

  const search = query.toString();
  return search ? `${COLABORADORES_PATH}?${search}` : COLABORADORES_PATH;
}

export function employeeHref(employeeId: string, tab?: Tab): string {
  const path = `${COLABORADORES_PATH}/${employeeId}`;
  return tab && tab !== DEFAULT_TAB ? `${path}?aba=${tab}` : path;
}

/** The query string the API asks for, built from the same filters. */
export function rhQuery(filters: RhFilters): string {
  const query = new URLSearchParams();

  if (filters.unit) query.set("unidade", filters.unit);
  if (filters.status) query.set("status", filters.status);
  if (filters.pendencia) query.set("pendencia", filters.pendencia);
  if (filters.busca) query.set("busca", filters.busca);

  return query.toString();
}
