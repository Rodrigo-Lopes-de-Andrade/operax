import "server-only";

import { ApiError, requestApi } from "@/lib/api";
import {
  CONFIG_PATH,
  type AssistantCostByVersion,
  type AssistantRun,
  type AssistantTestCost,
  type CapabilityRow,
  type PromptScreen,
  type VersionsScreen,
} from "@/lib/assistente/config";
import { getServerSupabase } from "@/lib/supabase-server";

/**
 * As leituras da configuração do assistente, no servidor — o mesmo desenho de
 * `lib/canais/queries.ts`: a página lê como o usuário, com o token da sessão,
 * e entrega o resultado por prop ao componente que escreve.
 *
 * Nulo é "sessão acabou", "papel não alcança" ou, no caso do prompt, "o
 * assistente está sem camada da plataforma publicada" (503) — os três viram o
 * mesmo estado vazio da tela, e nenhum é exceção. A API fora do ar relança: é
 * o error boundary que a mostra, não um "sem configuração" falso.
 */
async function readOrNull<T>(
  path: string,
  nullStatuses: readonly number[] = [401, 403],
): Promise<T | null> {
  const supabase = await getServerSupabase();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;

  if (!token) {
    return null;
  }

  try {
    return await requestApi<T>(path, { accessToken: token });
  } catch (error) {
    if (error instanceof ApiError && nullStatuses.includes(error.status)) {
      return null;
    }

    throw error;
  }
}

/** As duas camadas no ar e o rascunho. 503 = sem ponteiro de plataforma. */
export function loadPromptScreen(): Promise<PromptScreen | null> {
  return readOrNull<PromptScreen>(`${CONFIG_PATH}/prompt`, [401, 403, 503]);
}

export function loadVersions(): Promise<VersionsScreen | null> {
  return readOrNull<VersionsScreen>(`${CONFIG_PATH}/versoes`);
}

/** Todas as linhas, como quem chama as vê — a desligada e a fora de alcance também. */
export function loadCapabilities(): Promise<CapabilityRow[] | null> {
  return readOrNull<CapabilityRow[]>(`${CONFIG_PATH}/capacidades`);
}

/** As três leituras da aba Execuções, na mesma janela. */
export type ExecutionsScreen = {
  runs: AssistantRun[];
  cost: AssistantCostByVersion[];
  testCost: AssistantTestCost[];
};

/**
 * Três estados, e nenhum deles é exceção:
 *
 * - `ok` — as três leituras voltaram (lista curta, inclusive vazia, é `ok`:
 *   a RLS de `app.ai_query` é própria-ou-admin, então quem não administra vê
 *   os próprios turnos, e isso não é falta de permissão);
 * - `out_of_range` — 422: a janela pedida está fora de 1..52. A pessoa
 *   digitou `?semanas=` à mão, e a tela diz a faixa em vez de quebrar;
 * - `unavailable` — 401/403, ou a sessão acabou.
 */
export type ExecutionsResult =
  | { status: "ok"; screen: ExecutionsScreen }
  | { status: "out_of_range" }
  | { status: "unavailable" };

/**
 * A aba Execuções: os turnos, o custo por competência e o total de teste — as
 * três na mesma janela, porque as três RPCs usam a mesma expressão de semana e
 * a tela as mostra sob um seletor só.
 *
 * As três saem em paralelo e falham juntas: um custo lido com a janela de uma
 * leitura e um total lido com a de outra é pior do que não mostrar nenhum.
 */
export async function loadExecutions(weeks: number): Promise<ExecutionsResult> {
  const supabase = await getServerSupabase();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;

  if (!token) {
    return { status: "unavailable" };
  }

  const query = `?weeks=${encodeURIComponent(weeks)}`;

  try {
    const [runs, cost, testCost] = await Promise.all([
      requestApi<AssistantRun[]>(`${CONFIG_PATH}/execucoes${query}`, {
        accessToken: token,
      }),
      requestApi<AssistantCostByVersion[]>(`${CONFIG_PATH}/custo${query}`, {
        accessToken: token,
      }),
      requestApi<AssistantTestCost[]>(`${CONFIG_PATH}/custo-de-teste${query}`, {
        accessToken: token,
      }),
    ]);

    return { status: "ok", screen: { runs, cost, testCost } };
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 422) {
        return { status: "out_of_range" };
      }

      if (error.status === 401 || error.status === 403) {
        return { status: "unavailable" };
      }
    }

    throw error;
  }
}
