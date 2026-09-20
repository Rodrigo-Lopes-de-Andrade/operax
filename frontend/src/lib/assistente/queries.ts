import "server-only";

import { ApiError, requestApi } from "@/lib/api";
import {
  CONFIG_PATH,
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
