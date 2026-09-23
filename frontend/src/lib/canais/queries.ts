import "server-only";

import { ApiError, requestApi } from "@/lib/api";
import type { Channel } from "@/lib/canais/labels";
import {
  CONTACTS_API_PATH,
  RULES_API_PATH,
  type AlertRuleRow,
  type ContactRow,
} from "@/lib/canais/regras";
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

/**
 * O pedido de convite (`InviteRequest`): um titular só, colaborador **ou**
 * responsável — o `check messaging_invite_um_titular` do banco, dito no tipo.
 * A ficha manda `{employee_id, contact_id: null}`; a de responsável não existe
 * ainda.
 */
export type InviteRequest = {
  employee_id: string | null;
  contact_id: string | null;
};

/**
 * O que volta de `POST /canais/telegram/convites` (`InviteIssued`).
 *
 * ⛔ SEM O LINK E SEM O NÚMERO INTEIRO — E NÃO HÁ ONDE MOSTRÁ-LOS
 * O convite viaja por WhatsApp para o número em cadastro (SPEC-CANAIS §3.3,
 * regra 4): o painel nunca vê o deep link, porque quem o abre vira o
 * destinatário. `destination_masked` chega como "+55 11 •••••-0000" e a tela o
 * mostra como veio. `queued` é "entrou na fila" — quem entrega é o sender.
 */
export type InviteIssued = {
  invite_id: string;
  expires_at: string;
  queued: boolean;
  destination_masked: string;
};

/**
 * O vínculo de um colaborador com o bot (`TelegramLink`), como a ficha o
 * mostra (§3.3, regra 5: visível e revogável). `linked` é o fato; as datas
 * são o contexto dele — `opted_in_at` preenchido com `linked: false` é um
 * vínculo que existiu e foi revogado, não um vínculo. `invite_open_until` é
 * o convite em aberto, se houver. Nenhum `chat_id`, em estado nenhum.
 */
export type TelegramLink = {
  linked: boolean;
  opted_in_at: string | null;
  revoked_at: string | null;
  invite_open_until: string | null;
};

/**
 * Uma linha de `public.fn_telegram_adhesion()`: contagem por unidade visível,
 * e nada que nomeie uma pessoa (SPEC-CANAIS §3.2). `pending` é "nunca teve
 * identidade" — na tela é **não aderiram**, porque a adesão é voluntária
 * (decisão do dono, 16/09/2026): é um número, não uma pendência. As três
 * somam os colaboradores ativos da unidade.
 */
export type TelegramAdhesionRow = {
  unit_id: string;
  unit_name: string;
  joined: number;
  pending: number;
  revoked: number;
};

/**
 * Uma linha de `public.fn_delivery_by_channel(p_weeks)`: uma por (semana,
 * canal, provedor), contagens e nada mais — a função não devolve nem o hash
 * do destino (SPEC-CANAIS §8, consequência 3). `week_start` é `date`, a
 * segunda-feira da semana, e chega como `YYYY-MM-DD`: formata-se por string,
 * sem passar por `Date`, porque não há hora para deslocar. `channel` é o que
 * agrega — o canal de um provedor nunca se infere pelo nome dele.
 */
export type DeliveryByChannelRow = {
  week_start: string;
  channel: string;
  provider: string;
  /** `sent` + `delivered` + `read` — o que saiu. */
  sent: number;
  failed: number;
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

/**
 * Os destinatários do cliente, com a matriz de unidades que quem lê enxerga
 * — inativos inclusive, porque `active` é coluna e a tela os marca. Os tipos
 * moram em `lib/canais/regras.ts`, que é o que o navegador importa.
 */
export function loadContacts(): Promise<ContactRow[] | null> {
  return readOrNull<ContactRow[]>(CONTACTS_API_PATH);
}

/**
 * As regras do cliente, com destinos e `blocked_reason`. A rota é do
 * administrador (`GET /canais/regras` responde 403 a quem não é): o 403 vira
 * `null`, e a página já fechou por `isAdmin` antes de chegar aqui.
 */
export function loadRules(): Promise<AlertRuleRow[] | null> {
  return readOrNull<AlertRuleRow[]>(RULES_API_PATH);
}

/**
 * O vínculo de um colaborador com o bot — Caminho 2, porque é dado individual.
 *
 * 404 vira `null` como em `loadHrEmployee`: a rota responde 404 quando não vê
 * o colaborador, pelo mesmo recorte da ficha, e as duas leituras vão no mesmo
 * `Promise.all` — um 404 relançado aqui derrubaria a página no error boundary
 * em vez de deixar a ficha dizer "Colaborador não encontrado".
 */
export async function loadTelegramLink(
  employeeId: string,
): Promise<TelegramLink | null> {
  try {
    return await readOrNull<TelegramLink>(
      `/canais/telegram/vinculos/${employeeId}`,
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }

    throw error;
  }
}

/**
 * A adesão por unidade — Caminho 1, e a única leitura desta área que vai
 * direta ao Supabase: é agregado sem nome, e a função é `security definer`
 * recortada por `util.user_tenants()` e `util.can_see_unit`, sem parâmetro
 * nenhum para o cliente mandar (`Args: never` no tipo gerado — a chamada vai
 * sem argumento, como `fn_dp_alerts`). Erro vira `null`, como o frescor faz;
 * lista vazia é lista vazia — "nenhuma unidade com colaboradores" e "não pôde
 * ser lida" são dois estados da tela.
 */
export async function loadTelegramAdhesion(): Promise<
  TelegramAdhesionRow[] | null
> {
  const supabase = await getServerSupabase();
  const { data, error } = await supabase.rpc("fn_telegram_adhesion");

  if (error || !data) {
    return null;
  }

  return data.map((row) => ({
    unit_id: row.unit_id,
    unit_name: row.unit_name,
    joined: row.joined,
    pending: row.pending,
    revoked: row.revoked,
  }));
}

/**
 * As entregas por semana, canal e provedor — Caminho 1, como a adesão: é
 * contagem, e a função é `security invoker` sobre `app.alert_sent`, então
 * quem recorta é a policy `alert_sent_read` (`util.is_admin`) — quem não é
 * admin recebe `[]`, e a página que a chama já é só de admin. `p_weeks` é o
 * único argumento, e conta para trás a partir da semana atual, inclusa; sem
 * `tenant_id`, que a policy não aceitaria de qualquer jeito. Erro vira
 * `null`; lista vazia é lista vazia — o sender ainda não está agendado, e
 * "nenhuma entrega" vai ser o estado normal por semanas.
 */
export async function loadDeliveryByChannel(
  weeks = 8,
): Promise<DeliveryByChannelRow[] | null> {
  const supabase = await getServerSupabase();
  const { data, error } = await supabase.rpc("fn_delivery_by_channel", {
    p_weeks: weeks,
  });

  if (error || !data) {
    return null;
  }

  return data.map((row) => ({
    week_start: row.week_start,
    channel: row.channel,
    provider: row.provider,
    sent: row.sent,
    failed: row.failed,
  }));
}
