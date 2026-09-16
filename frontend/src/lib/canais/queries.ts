import "server-only";

import { ApiError, requestApi } from "@/lib/api";
import type { Channel } from "@/lib/canais/labels";
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
 * lá. As três famílias de restrição da SPEC-CANAIS §1.1, cada uma lida por si:
 * um canal pode não ter nenhuma das três, e isso não é "sem regra".
 */
export type ChannelCapabilities = {
  official: boolean;
  /** Hetero-restrição: a mensagem precisa nomear template aprovado pela Meta. */
  requires_templates: boolean;
  /** Auto-restrição: o número do cliente pode ser banido pelo volume. */
  ban_risk: boolean;
  /** Restrição de destinatário (§1.1): só alcança quem iniciou o bot. */
  requires_recipient_opt_in: boolean;
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
 * O canal de WhatsApp ativo do cliente — um dos três provedores — e por que o
 * alerta não sai por ele.
 *
 * `rules_blocked` e `blocked.length` são duas leituras do mesmo fato: a
 * contagem vem de `fn_channel_readiness` e a lista da consulta que repete o
 * predicado dela. A tela mostra a contagem que a API deu e a lista que veio —
 * as duas, sem fechar uma pela outra.
 */
export type WhatsAppChannel = {
  provider: string;
  capabilities: ChannelCapabilities;
  templates_total: number;
  templates_approved: number;
  rules_blocked: number;
  ready: boolean;
  blocked: BlockedAlertRule[];
};

/**
 * O bot de Telegram do cliente, e a saúde dele (SPEC-CANAIS §6 e §7).
 *
 * `webhook_url` é o endereço inteiro que o backend registrou no `setWebhook`
 * — exatamente o que o Telegram chama, nulo quando desconectado — e
 * `webhook_path_token` é a cauda rotativa dele: desconectar rotaciona de
 * propósito, e reconectar não devolve o antigo — a tela mostra o que veio.
 * Não é segredo (o segredo vai no header), mas também não precisa ficar
 * inteiro na tela.
 *
 * `health_status` nulo é "o vigia nunca mediu", e é diferente de `unknown`
 * ("mediu e o Telegram não respondeu"). `health_changed_at` só avança quando o
 * estado muda — é o tempo no estado, não a última conferência. `ready` só é
 * verdadeiro com saúde `connected`; e ninguém aqui religa nada (§7).
 */
export type TelegramChannel = {
  provider: string;
  capabilities: ChannelCapabilities;
  /** "@…", como o Telegram devolveu ao validar o token. */
  bot_username: string | null;
  webhook_configured: boolean;
  webhook_url: string | null;
  webhook_path_token: string | null;
  health_status: "connected" | "disconnected" | "unknown" | null;
  health_checked_at: string | null;
  health_changed_at: string | null;
  health_detail: string | null;
  ready: boolean;
};

/**
 * A tela de Conexões: os dois canais, que **coexistem** por desenho (SPEC
 * §2.1). Nulo num deles é "nenhum provedor ativo desse canal", e os dois nulos
 * é o estado da produção hoje — não um erro.
 */
export type ConnectionsScreen = {
  whatsapp: WhatsAppChannel | null;
  telegram: TelegramChannel | null;
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
 * `channel` é o que separa os quatro em dois formulários — pelo canal, nunca
 * pelo nome.
 */
export type ProviderForm = {
  provider: string;
  channel: Channel;
  capabilities: ChannelCapabilities;
  fields: CredentialField[];
};

/**
 * O que se diz da credencial gravada de um canal: que existe, não qual é
 * (SPEC §5.3). `CredentialStatus` em `models.py` — nenhum campo carrega valor
 * de segredo, em nenhum estado.
 */
export type CredentialStatus = {
  channel: Channel;
  configured: boolean;
  provider: string | null;
  updated_at: string | null;
  public_identity: string | null;
};

/**
 * Uma linha de `app.message_template`, como `GET /canais/templates` a entrega
 * (`TemplateRow` em `models.py`).
 *
 * `meta_status` e `meta_rejection` são o que a Meta disse do template e chegam
 * aqui só para leitura: quem os escreve é a sincronização, nunca o formulário.
 * `variables` é a ordem dos `{{n}}` do corpo — a posição na lista é o número
 * do placeholder — e o juiz do corpo é o gatilho do banco, não a tela.
 */
export type TemplateRow = {
  code: string;
  category: "utility" | "authentication" | "marketing";
  language: string;
  variables: string[];
  body: string;
  meta_template_name: string | null;
  meta_status: "draft" | "pending" | "approved" | "rejected" | "paused";
  meta_rejection: string | null;
  active: boolean;
  updated_at: string;
};

/**
 * O que o formulário grava em `PUT /canais/templates/{code}` (`TemplateWrite`).
 * Sem `meta_status` e sem `meta_rejection` de propósito: o backend recusa a
 * mão no estado da Meta, e trocar `meta_template_name` volta o status a
 * `draft` lá — a tela avisa e não simula.
 */
export type TemplateWrite = {
  category: TemplateRow["category"];
  language: string;
  variables: string[];
  body: string;
  meta_template_name: string | null;
  active: boolean;
};

/**
 * O resultado de `POST /canais/templates/sincronizar` (`TemplateSyncResult`):
 * quantos templates a WABA tem, quais linhas locais mudaram de estado e quais
 * ficaram sem par lá — estas voltam a `draft` no banco.
 */
export type TemplateSyncResult = {
  provider: string;
  meta_total: number;
  updated: string[];
  unmatched: string[];
  synced_at: string;
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

/**
 * Que a credencial do canal existe, de qual provedor e desde quando — nunca
 * qual é. Uma leitura por canal: a página chama as duas.
 */
export function loadCredential(
  channel: Channel,
): Promise<CredentialStatus | null> {
  return readOrNull<CredentialStatus>(`/canais/credencial?canal=${channel}`);
}

/** Os formulários dos quatro provedores, na ordem da API — o oficial primeiro. */
export function loadProviderForms(): Promise<ProviderForm[] | null> {
  return readOrNull<ProviderForm[]>("/canais/provedores");
}

/** O catálogo do cliente, ordenado por `code` como a API o entrega. */
export function loadTemplates(): Promise<TemplateRow[] | null> {
  return readOrNull<TemplateRow[]>("/canais/templates");
}
