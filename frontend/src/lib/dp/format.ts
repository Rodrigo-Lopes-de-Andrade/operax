import { MESES } from "@/lib/folha/url";

/**
 * Os dois formatos que as telas de DP mostram: dinheiro e competência.
 *
 * `Decimal` do Pydantic chega como **string** no JSON, e é assim que ela viaja
 * até aqui — converter cedo, no cliente da API, arredondaria em `number` um
 * valor que o backend guarda com duas casas exatas.
 */

const CURRENCY = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

export function formatCurrency(value: string | null | undefined): string {
  return value === null || value === undefined
    ? "—"
    : CURRENCY.format(Number(value));
}

/** `setembro/2026` — o mesmo vocabulário da tela de folha, de propósito. */
export function formatCompetencia(year: number, month: number): string {
  const nome = MESES[month - 1];

  return nome ? `${nome}/${year}` : `${String(month).padStart(2, "0")}/${year}`;
}

/** `21/08/2026` a partir do `date` que o Postgres entrega como `2026-08-21`. */
export function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }

  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

/**
 * A vigência de uma faixa, como o gestor a confere: "desde 01/09/2026" enquanto
 * está aberta, "01/01/2026 a 31/08/2026" depois de fechada pelo reajuste.
 */
export function formatBand(from: string, to: string | null): string {
  return to
    ? `${formatDate(from)} a ${formatDate(to)}`
    : `desde ${formatDate(from)}`;
}

const PERCENT = new Intl.NumberFormat("pt-BR", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/**
 * A proporção 0..1 que o backend manda com quatro casas. `null` é base vazia, e
 * "—" é o que ela merece: 0% diria "nenhum ativo" sobre uma lista sem ninguém.
 */
export function formatPercent(value: string | null | undefined): string {
  return value === null || value === undefined
    ? "—"
    : PERCENT.format(Number(value));
}

/**
 * Dinheiro em centavos inteiros, e não em `number` com vírgula.
 *
 * O raio-x subtrai duas verbas da folha base para achar o resto, e essa conta
 * tem de fechar: em ponto flutuante `109384.00 - 0.1 - 0.2` não fecha, e o
 * resíduo apareceria na tela como um centavo que ninguém consegue explicar.
 * Centavo inteiro é exato até R$ 90 trilhões, que é bem mais folha do que
 * qualquer tenant tem.
 */
export function toCents(value: string): number {
  const [whole, fraction = ""] = value.trim().split(".");
  const negative = whole.startsWith("-");
  const cents =
    Number(whole.replace("-", "")) * 100 + Number(`${fraction}00`.slice(0, 2));

  return negative ? -cents : cents;
}

export function formatCents(cents: number): string {
  return CURRENCY.format(cents / 100);
}

/**
 * A fatia de `part` dentro de `whole`, já arredondada para inteiro. Base zero
 * devolve `null` — uma folha vazia não tem composição, e 0% mentiria dizendo
 * que tem e que esta verba não entra nela.
 */
export function share(part: number, whole: number): number | null {
  return whole === 0 ? null : Math.round((part / whole) * 100);
}
