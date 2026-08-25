// Escopo e janela de uma execução de `sync-batidas`.
//
// Vive fora do `index.ts` porque o `index.ts` chama `Deno.serve` no topo:
// importá-lo de um teste subiria um servidor HTTP. A regra de precedência é a
// coisa testável aqui, e ela não deveria exigir um servidor para ser exercida.

import { BACKFILL_WINDOW_DAYS, BATIDAS_WINDOW_DAYS, type SyncScope } from "./batida-sync.ts";

export interface RunOptions {
  scope: SyncScope;
  windowDays: number;
}

function positiveInt(value: unknown): number | null {
  const n = typeof value === "string" ? Number(value) : value;
  if (typeof n !== "number" || !Number.isFinite(n) || !Number.isInteger(n) || n < 1) return null;
  return n;
}

/**
 * O escopo e a janela desta execução.
 *
 * Precedência: o que a invocação pediu, depois o ambiente, depois o padrão do
 * código. A janela deixou de ser constante para que uma parada longa possa ser
 * recuperada **sem redeploy** — que era a única saída antes.
 *
 * O `Request` era descartado (`Deno.serve(() => handleRequest())`), então não
 * havia por onde alargar a janela nem pedir o backfill. Agora ele é lido, e um
 * corpo inválido não derruba a execução: cai no padrão, que é a passada normal.
 */
export async function resolveRunOptions(request: Request): Promise<RunOptions> {
  let pedido: Record<string, unknown> = {};
  try {
    const url = new URL(request.url);
    for (const [k, v] of url.searchParams) pedido[k] = v;
    if (request.body) {
      const corpo = await request.json();
      if (corpo && typeof corpo === "object") pedido = { ...pedido, ...corpo };
    }
  } catch {
    // Corpo ausente ou não-JSON: a invocação do pg_cron é um POST sem corpo.
  }

  const scope: SyncScope = pedido.scope === "backfill" ? "backfill" : "incremental";
  const padrao = scope === "backfill" ? BACKFILL_WINDOW_DAYS : BATIDAS_WINDOW_DAYS;
  const doAmbiente = Deno.env.get(
    scope === "backfill" ? "BACKFILL_WINDOW_DAYS" : "BATIDAS_WINDOW_DAYS",
  );

  const windowDays = positiveInt(pedido.windowDays) ?? positiveInt(doAmbiente) ?? padrao;
  return { scope, windowDays };
}
