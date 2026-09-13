import "server-only";

import { ApiError, requestApi } from "@/lib/api";
import { getServerSupabase } from "@/lib/supabase-server";

/**
 * Caminho 2, e não há Caminho 1 nesta tela.
 *
 * `public.fn_whatsapp_readiness` até atende o navegador, mas o que ela não
 * devolve é o que a tela existe para dizer: **qual** regra e **qual** template.
 * Esses dois vivem em `app`, fora dos exposed schemas, e expor uma view nova
 * para isso é uma das três paradas obrigatórias do projeto. Então tudo vem de
 * `GET /canais/conexoes`, e os tipos abaixo são escritos à mão a partir de
 * `backend/server/models.py` (`ConnectionsScreen`) — é resposta de API, não
 * tabela, e o gerador de tipos não a alcança.
 *
 * ⛔ NENHUM CAMPO OBRIGATÓRIO DO CONTRATO É OPCIONAL AQUI
 * Todo campo de `ConnectionsScreen` tem default no Pydantic e por isso está
 * sempre no JSON. Declará-lo com `?` transformaria uma renomeação no backend em
 * `undefined` silencioso — e um `rules_blocked` que some é exatamente o
 * diagnóstico invisível que a tela veio consertar.
 */

/**
 * O que o canal permite — cópia de `operax/alertas/capacidades.py`, decidida
 * lá. `null` no lugar deste objeto é "nenhum provedor de WhatsApp ativo", e
 * não "sem restrição".
 */
export type ChannelCapabilities = {
  official: boolean;
  /** Hetero-restrição: a mensagem precisa nomear template aprovado pela Meta. */
  requires_templates: boolean;
  /** Auto-restrição: o número do cliente pode ser banido pelo volume. */
  ban_risk: boolean;
};

/**
 * Uma regra ligada que não tem como entregar, e por quê.
 *
 * ⚠️ TRÊS CASOS, E NENHUM DOS NULOS É "ESTÁ TUDO BEM"
 * 1. `template_code` e `meta_status` preenchidos — o template existe e está num
 *    estado que não é `approved`.
 * 2. `template_code` preenchido, `meta_status` nulo — a regra aponta para um
 *    código que não existe neste cliente **ou** está inativo. A resposta não
 *    distingue os dois, e a frase da tela não pode fingir que distingue.
 * 3. `template_code` nulo — a regra é de WhatsApp e não aponta para template
 *    nenhum.
 */
export type BlockedAlertRule = {
  rule_name: string;
  template_code: string | null;
  meta_status: string | null;
};

/**
 * `rules_blocked` e `blocked.length` são duas leituras do mesmo fato: a
 * contagem vem de `fn_whatsapp_readiness` e a lista da consulta que repete o
 * predicado dela. A tela mostra a contagem que a API deu e a lista que veio —
 * as duas, sem fechar uma pela outra.
 */
export type ConnectionsScreen = {
  provider: string | null;
  capabilities: ChannelCapabilities | null;
  templates_total: number;
  templates_approved: number;
  rules_blocked: number;
  ready: boolean;
  blocked: BlockedAlertRule[];
};

async function accessToken(): Promise<string | null> {
  const supabase = await getServerSupabase();
  const { data } = await supabase.auth.getSession();

  return data.session?.access_token ?? null;
}

/**
 * Null quando a sessão acabou ou quando o papel não alcança — os dois viram o
 * mesmo estado vazio na tela, e nenhum deles é uma exceção. A API fora do ar
 * relança: é o error boundary que a mostra, não um "sem canal" falso.
 */
export async function loadConnections(): Promise<ConnectionsScreen | null> {
  const token = await accessToken();

  if (!token) {
    return null;
  }

  try {
    return await requestApi<ConnectionsScreen>("/canais/conexoes", {
      accessToken: token,
    });
  } catch (error) {
    if (error instanceof ApiError && [401, 403].includes(error.status)) {
      return null;
    }

    throw error;
  }
}
