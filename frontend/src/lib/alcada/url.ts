import type { RawSearchParams } from "@/lib/ponto/filters";

/**
 * A fila de aprovação de justificativas — o recorte dela, na query string.
 *
 * Vive embaixo de `/dashboard/justificativas` porque é a outra ponta do mesmo
 * fluxo: lá o gestor explica o indício, aqui o RH (ou o owner) decide.
 *
 * As chaves seguem o resto do produto: `ano`/`mes` como no ciclo mensal, `un`
 * como no Quadro de Postos (uuid, porque é o que a API espera em `unidade`).
 * `col`, `de` e `ate` são novas e dizem o que parecem dizer.
 */
export const APROVACAO_PATH = "/dashboard/justificativas/aprovacao";

export type ApprovalFilters = {
  /**
   * A competência, sempre em par: os dois ou nenhum. Nula, a API usa a
   * corrente — calculada no banco (`util.competencia_janela`), com o relógio
   * do tenant — e a devolve na resposta.
   */
  year: number | null;
  month: number | null;
  unitId: string | null;
  employeeId: string | null;
  /** `AAAA-MM-DD`, inclusivo. Só estreita a janela da competência. */
  from: string | null;
  /** `AAAA-MM-DD`, inclusivo. */
  to: string | null;
};

/** O recorte com a competência que a API de fato usou — a da URL ou a corrente. */
export type ResolvedApprovalFilters = ApprovalFilters & {
  year: number;
  month: number;
};

/** Os limites de `ano` em `GET /alcada/fila` — fora deles a API responde 422. */
export const YEAR_MIN = 2000;
export const YEAR_MAX = 2100;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/**
 * Um dia que existe no calendário. A regex sozinha deixa passar `2026-02-31`,
 * que a API recusa com 422 — e a tela diria "a API não respondeu" sobre um
 * link malformado. Descartado aqui, vale como parâmetro ausente.
 */
export function isCalendarDay(value: string): boolean {
  if (!ISO_DAY.test(value)) {
    return false;
  }

  const [year, month, day] = value.split("-").map(Number);
  const at = new Date(Date.UTC(year, month - 1, day));

  return (
    at.getUTCFullYear() === year &&
    at.getUTCMonth() === month - 1 &&
    at.getUTCDate() === day
  );
}

/**
 * Aritmética de mês, e só dela: o mês anterior e o seguinte de uma
 * competência. Onde a janela de cada uma começa e termina é do banco.
 */
export function shiftMonth(
  year: number,
  month: number,
  delta: number,
): { year: number; month: number } {
  const index = year * 12 + (month - 1) + delta;

  return { year: Math.floor(index / 12), month: (index % 12) + 1 };
}

export function parseApprovalFilters(params: RawSearchParams): ApprovalFilters {
  const year = Number(first(params.ano));
  const month = Number(first(params.mes));
  const unit = first(params.un);
  const employee = first(params.col);
  const from = first(params.de);
  const to = first(params.ate);

  // Os limites são os de `GET /alcada/fila`, e o par vai junto ou não vai: um
  // sem o outro a API recusa com 422. Fora deles, a tela abre na competência
  // corrente em vez de não abrir.
  const competence =
    Number.isInteger(year) &&
    year >= YEAR_MIN &&
    year <= YEAR_MAX &&
    Number.isInteger(month) &&
    month >= 1 &&
    month <= 12;

  return {
    year: competence ? year : null,
    month: competence ? month : null,
    unitId: unit && UUID.test(unit) ? unit.toLowerCase() : null,
    employeeId: employee && UUID.test(employee) ? employee.toLowerCase() : null,
    from: from && isCalendarDay(from) ? from : null,
    to: to && isCalendarDay(to) ? to : null,
  };
}

/**
 * Todo link da tela sai daqui. Quem monta os links da tela passa a competência
 * que a API devolveu, então ela viaja inteira: um link sem mês abriria na
 * competência de quem clicou, e não na de quem mandou.
 *
 * Trocar de competência limpa `de`/`ate` — as datas pertencem à janela
 * anterior, e mantê-las devolveria uma fila vazia que parece resolvida.
 */
export function approvalHref(
  filters: ApprovalFilters,
  overrides: Partial<ApprovalFilters> = {},
): string {
  const competenceChanged =
    (overrides.year !== undefined && overrides.year !== filters.year) ||
    (overrides.month !== undefined && overrides.month !== filters.month);

  const next: ApprovalFilters = {
    ...filters,
    ...(competenceChanged ? { from: null, to: null } : {}),
    ...overrides,
  };

  const params = new URLSearchParams();

  if (next.year !== null && next.month !== null) {
    params.set("ano", String(next.year));
    params.set("mes", String(next.month));
  }
  if (next.unitId) params.set("un", next.unitId);
  if (next.employeeId) params.set("col", next.employeeId);
  if (next.from) params.set("de", next.from);
  if (next.to) params.set("ate", next.to);

  const query = params.toString();

  return query ? `${APROVACAO_PATH}?${query}` : APROVACAO_PATH;
}

/** A query de `GET /alcada/fila`, com os nomes que a rota usa. */
export function approvalQuery(filters: ApprovalFilters): string {
  const params = new URLSearchParams();

  if (filters.year !== null && filters.month !== null) {
    params.set("ano", String(filters.year));
    params.set("mes", String(filters.month));
  }
  if (filters.unitId) params.set("unidade", filters.unitId);
  if (filters.employeeId) params.set("colaborador", filters.employeeId);
  if (filters.from) params.set("de", filters.from);
  if (filters.to) params.set("ate", filters.to);

  return params.toString();
}
