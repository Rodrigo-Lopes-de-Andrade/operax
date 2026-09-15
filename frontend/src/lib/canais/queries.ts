import "server-only";

import { ApiError, requestApi } from "@/lib/api";
import { getServerSupabase } from "@/lib/supabase-server";

/**
 * Caminho 2, e não há Caminho 1 nesta tela.
 *
 * `public.fn_whatsapp_readiness` até atende o navegador, mas o que ela não
 * devolve é o que a tela existe para dizer: **qual** regra e **qual** template.
 * Esses dois vivem em `app`, fora dos exposed schemas, e expor uma view nova
 * para isso é uma das três paradas obrigatórias do projeto. Então tudo vem da
 * API (`/canais/conexoes`, `/canais/credencial`, `/canais/provedores`), e os
 * tipos abaixo são escritos à mão a partir de `backend/server/models.py` — é
 * resposta de API, não tabela, e o gerador de tipos não a alcança.
 *
 * A credencial em si nunca passa por aqui: o navegador não a lê com a chave
 * anônima (SPEC-CANAIS §5.1), e o `GET` diz que ela existe, não qual é (§5.3).
 *
 * ⛔ NENHUM CAMPO OBRIGATÓRIO DO CONTRATO É OPCIONAL AQUI
 * Todo campo destes modelos tem default no Pydantic e por isso está sempre no
 * JSON. Declará-lo com `?` transformaria uma renomeação no backend em
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

/**
 * Um campo do formulário de credencial, como o provedor o declara
 * (`FieldForm` em `models.py`). É a SPEC-CANAIS §5.4 num lugar só: `pattern`
 * é o mesmo que a API impõe com `fullmatch` antes de qualquer HTTP;
 * `autocomplete` e `inputmode` são o que impede o navegador de despejar e-mail
 * num campo numérico; `hint` é a frase que a tela mostra quando `pattern`
 * falha. `secret` decide o `type` do input e o que é limpo depois de gravar.
 */
export type CredentialField = {
  name: string;
  label: string;
  pattern: string;
  autocomplete: string;
  inputmode: string;
  secret: boolean;
  placeholder: string;
  hint: string;
};

/**
 * O formulário de um provedor (`ProviderForm`). Sem rótulo humano: ele vive em
 * `lib/canais/labels.ts`, e um segundo aqui seria uma cópia livre para divergir.
 */
export type ProviderForm = {
  provider: string;
  capabilities: ChannelCapabilities;
  fields: CredentialField[];
};

/**
 * O que se diz da credencial gravada: que existe, não qual é (SPEC §5.3).
 * `CredentialStatus` em `models.py` — nenhum campo carrega valor de segredo,
 * em nenhum estado.
 */
export type CredentialStatus = {
  configured: boolean;
  provider: string | null;
  updated_at: string | null;
  public_identity: string | null;
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
async function readOrNull<T>(path: string): Promise<T | null> {
  const token = await accessToken();

  if (!token) {
    return null;
  }

  try {
    return await requestApi<T>(path, { accessToken: token });
  } catch (error) {
    if (error instanceof ApiError && [401, 403].includes(error.status)) {
      return null;
    }

    throw error;
  }
}

export function loadConnections(): Promise<ConnectionsScreen | null> {
  return readOrNull<ConnectionsScreen>("/canais/conexoes");
}

/** Que a credencial existe, de qual provedor e desde quando — nunca qual é. */
export function loadCredential(): Promise<CredentialStatus | null> {
  return readOrNull<CredentialStatus>("/canais/credencial");
}

/** Os formulários, na ordem da API — o oficial primeiro. */
export function loadProviderForms(): Promise<ProviderForm[] | null> {
  return readOrNull<ProviderForm[]>("/canais/provedores");
}
