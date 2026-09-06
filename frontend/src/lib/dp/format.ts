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
