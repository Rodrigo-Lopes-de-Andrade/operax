import type { RawSearchParams } from "@/lib/ponto/filters";
import { ADMIN_PATH } from "@/lib/rh/url";

/**
 * O recorte das três telas de DP, na query string e em lugar nenhum mais.
 *
 * Vale aqui pelo mesmo motivo do resto do produto (CLAUDE.md): o link que
 * alguém cola numa conversa tem de abrir a tela já no mesmo lugar. E há um
 * motivo próprio desta etapa: a competência de um ciclo é a diferença entre
 * dois números certos, e "o mês que estava selecionado" não sobrevive a um
 * encaminhamento.
 */

export const POSTOS_PATH = `${ADMIN_PATH}/postos`;
export const BENEFICIOS_PATH = `${ADMIN_PATH}/beneficios`;
export const CICLO_PATH = "/dashboard/dp/ciclos";
export const PAINEL_PATH = "/dashboard/dp/painel";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Os dois `kind` de `app.benefit_cycle`. Um modelo, duas rotinas. */
export const CYCLE_KINDS = ["food_basket", "transport_voucher"] as const;
export type CycleKind = (typeof CYCLE_KINDS)[number];

export const CYCLE_KIND_LABEL: Record<CycleKind, string> = {
  food_basket: "Cesta",
  transport_voucher: "Vale transporte",
};

export const DEFAULT_CYCLE_KIND: CycleKind = "food_basket";

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/** Filtro do Quadro de Postos: uma unidade, pelo id que a API espera em `unidade`. */
export type PostosFilters = { unitId: string | null };

export function parsePostosFilters(params: RawSearchParams): PostosFilters {
  const unit = first(params.un);

  // Um `un` que não é uuid volta como "todas" em vez de virar erro: o link
  // velho de uma unidade renomeada tem de abrir a tela, não uma exceção.
  return { unitId: unit && UUID.test(unit) ? unit : null };
}

export function postosHref(filters: PostosFilters): string {
  return filters.unitId ? `${POSTOS_PATH}?un=${filters.unitId}` : POSTOS_PATH;
}

/** A query que `GET /dp/postos` espera, montada do mesmo recorte. */
export function postosQuery(filters: PostosFilters): string {
  return filters.unitId ? `unidade=${encodeURIComponent(filters.unitId)}` : "";
}

/**
 * Recorte do catálogo: a aba (o tipo de verba) e **a data da vigência**.
 *
 * A data não é enfeite. Preço tem vigência, e o catálogo respondido sem data é
 * o de hoje — que no dia seguinte a um reajuste responde outra coisa. Quem
 * confere um ciclo do mês passado precisa do link que abre o catálogo como ele
 * era naquele dia.
 */
export type CatalogFilters = { type: string | null; on: string | null };

export function parseCatalogFilters(params: RawSearchParams): CatalogFilters {
  const type = first(params.tipo)?.trim();
  const on = first(params.em);

  return {
    type: type ? type : null,
    on: on && ISO_DAY.test(on) ? on : null,
  };
}

export function catalogHref(
  filters: CatalogFilters,
  overrides: Partial<CatalogFilters> = {},
): string {
  const next = { ...filters, ...overrides };
  const query = new URLSearchParams();

  if (next.type) query.set("tipo", next.type);
  if (next.on) query.set("em", next.on);

  const search = query.toString();
  return search ? `${BENEFICIOS_PATH}?${search}` : BENEFICIOS_PATH;
}

/** A query de `GET /dp/beneficios/catalogo`. Sem `em`, o backend responde por hoje. */
export function catalogQuery(filters: CatalogFilters): string {
  return filters.on ? `em=${filters.on}` : "";
}

/** A competência de um ciclo: a rotina e o mês. A janela o backend deriva. */
export type CycleFilters = { kind: CycleKind; year: number; month: number };

export function parseCycleFilters(
  params: RawSearchParams,
  today: string,
): CycleFilters {
  const [defaultYear, defaultMonth] = today.split("-").map(Number);
  const kind = first(params.tipo);
  const year = Number(first(params.ano));
  const month = Number(first(params.mes));

  return {
    kind: (CYCLE_KINDS as readonly string[]).includes(kind ?? "")
      ? (kind as CycleKind)
      : DEFAULT_CYCLE_KIND,
    // Os limites são os de `CycleRequest` no backend. Fora deles o pedido
    // voltaria 422, e uma tela que não abre é pior que uma que abre no mês
    // corrente.
    year:
      Number.isInteger(year) && year >= 2000 && year <= 2100
        ? year
        : defaultYear,
    month:
      Number.isInteger(month) && month >= 1 && month <= 12
        ? month
        : defaultMonth,
  };
}

export function cycleHref(
  filters: CycleFilters,
  overrides: Partial<CycleFilters> = {},
): string {
  const next = { ...filters, ...overrides };
  const query = new URLSearchParams({
    tipo: next.kind,
    ano: String(next.year),
    mes: String(next.month),
  });

  // A competência viaja inteira, sempre: um link sem mês abriria no mês de quem
  // clicou, e não no de quem mandou.
  return `${CICLO_PATH}?${query}`;
}

/**
 * A query de `GET /dp/ciclos` — a mesma competência, com os nomes que a rota usa.
 *
 * Os três parâmetros vão juntos e sem exceção: a rota sem filtro devolve o
 * histórico inteiro do tenant, e a tela precisa exatamente da competência que
 * está na URL. Uma lista maior aqui só daria trabalho de escolher a linha certa
 * no cliente — que é onde escolher errado não aparece.
 */
export function cyclesQuery(filters: CycleFilters): string {
  return new URLSearchParams({
    kind: filters.kind,
    ano: String(filters.year),
    mes: String(filters.month),
  }).toString();
}

/**
 * Recorte do painel de DP: empresa e unidade, pelos ids que a API espera em
 * `empresa` e `unidade`. As mesmas chaves de query do resto do produto (`emp`,
 * `un`), para que um link colado entre telas continue querendo dizer a mesma
 * coisa.
 *
 * ⛔ A DATA NÃO ENTRA, E A AUSÊNCIA É DECISÃO
 * `GET /dp/painel` aceita `em` e responderia o painel de outro dia. Os oito
 * contadores de alerta **não** aceitam data: `public.fn_dp_alerts()` compara com
 * `current_date` dentro do SQL e não tem parâmetro. Um seletor de data moveria
 * a metade de cima da tela e deixaria a de baixo parada em hoje, sem nada na
 * tela dizendo isso — que é pior do que uma tela que só sabe falar do presente.
 * A data lida volta no payload (`on`) e a tela a mostra.
 */
export type PanelFilters = { unitId: string | null; companyId: string | null };

export function parsePanelFilters(params: RawSearchParams): PanelFilters {
  const unit = first(params.un);
  const company = first(params.emp);

  // Id que não é uuid vira "todas", como no Quadro de Postos: o link velho de
  // uma unidade que saiu do cadastro tem de abrir o painel, não uma exceção.
  return {
    unitId: unit && UUID.test(unit) ? unit : null,
    companyId: company && UUID.test(company) ? company : null,
  };
}

export function panelHref(
  filters: PanelFilters,
  overrides: Partial<PanelFilters> = {},
): string {
  const next = { ...filters, ...overrides };
  const query = new URLSearchParams();

  if (next.companyId) query.set("emp", next.companyId);
  if (next.unitId) query.set("un", next.unitId);

  const search = query.toString();
  return search ? `${PAINEL_PATH}?${search}` : PAINEL_PATH;
}

/** A query que `GET /dp/painel` espera, montada do mesmo recorte. */
export function panelQuery(filters: PanelFilters): string {
  const query = new URLSearchParams();

  if (filters.companyId) query.set("empresa", filters.companyId);
  if (filters.unitId) query.set("unidade", filters.unitId);

  return query.toString();
}
