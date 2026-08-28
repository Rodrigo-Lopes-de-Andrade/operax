import {
  PERIODS,
  slugify,
  type Period,
  type RawSearchParams,
} from "@/lib/ponto/filters";
import { DEFAULT_PAGE_SIZE, type Paging } from "@/lib/ponto/url";

/**
 * A fila de pendentes de justificativa — o recorte dela, na query string.
 *
 * Mesmas chaves da gestão de ponto (`un`, `per`, `ev`, `pg`, `tam`), porque um
 * link colado de uma tela na outra tem de continuar querendo dizer a mesma
 * coisa. Duas diferenças, e as duas são de propósito:
 *
 *  - **não há filtro de empresa.** `fn_pending_justification` recebe unidade,
 *    departamento e gestor, e nenhum parâmetro de empresa. Um seletor que
 *    aparecesse aqui e fosse descartado no caminho seria pior do que a ausência
 *    dele;
 *  - **o período padrão é 30 dias.** A fila é passivo, não recorte de análise:
 *    7 dias esconderiam o indício de duas semanas atrás que continua sem
 *    explicação — que é exatamente o que a tela existe para mostrar.
 */
export const JUSTIFICATIVAS_PATH = "/dashboard/justificativas";

export const DEFAULT_PENDING_PERIOD: Period = "30d";

export type PendingFilters = {
  period: Period;
  /** `app.unit.code`, lowercased. */
  unitCode: string | null;
  /** Ocorrência que o link aponta — abre o detalhe direto. */
  eventId: string | null;
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function parsePendingFilters(params: RawSearchParams): PendingFilters {
  const period = first(params.per);
  const unit = first(params.un);
  const event = first(params.ev);

  return {
    period: PERIODS.includes(period as Period)
      ? (period as Period)
      : DEFAULT_PENDING_PERIOD,
    unitCode: unit ? slugify(unit) : null,
    eventId: event && UUID.test(event) ? event.toLowerCase() : null,
  };
}

/**
 * Todo link da tela sai daqui. Mudar o recorte volta para a primeira página —
 * manter a página 7 depois de estreitar para uma unidade entrega uma fila
 * vazia que parece resolvida.
 */
export function justificativasHref(
  filters: PendingFilters,
  paging: Paging,
  overrides: Partial<PendingFilters & Paging> = {},
): string {
  const next: PendingFilters = {
    period: overrides.period ?? filters.period,
    unitCode:
      overrides.unitCode !== undefined ? overrides.unitCode : filters.unitCode,
    eventId:
      overrides.eventId !== undefined ? overrides.eventId : filters.eventId,
  };

  const filtersChanged =
    next.period !== filters.period || next.unitCode !== filters.unitCode;

  const pageSize = overrides.pageSize ?? paging.pageSize;
  const page =
    overrides.page ??
    (filtersChanged || pageSize !== paging.pageSize ? 1 : paging.page);

  const params = new URLSearchParams();

  if (next.unitCode) {
    params.set("un", next.unitCode);
  }
  if (next.period !== DEFAULT_PENDING_PERIOD) {
    params.set("per", next.period);
  }
  if (next.eventId) {
    params.set("ev", next.eventId);
  }
  if (page > 1) {
    params.set("pg", String(page));
  }
  if (pageSize !== DEFAULT_PAGE_SIZE) {
    params.set("tam", String(pageSize));
  }

  const query = params.toString();

  return query ? `${JUSTIFICATIVAS_PATH}?${query}` : JUSTIFICATIVAS_PATH;
}
