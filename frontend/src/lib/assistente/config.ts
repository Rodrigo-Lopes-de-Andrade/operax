import { ApiError, requestApiAsUser } from "@/lib/api";
import { streamAssistant, type StreamOptions } from "@/lib/assistente/stream";

/**
 * A configuração do assistente — Caminho 2 inteiro, e nada além dele.
 *
 * As quatro abas falam com `/assistente/configuracao/*` (SPEC-AGENTE §1, §2,
 * §4, §5), e os tipos abaixo espelham o bloco "Configuração do assistente" de
 * `backend/server/models.py` **campo a campo**. São resposta de API, não
 * tabela: o gerador de tipos do Supabase não os alcança, e é assim que
 * `lib/canais/queries.ts` faz.
 *
 * ⛔ NENHUM CAMPO OBRIGATÓRIO DO CONTRATO É OPCIONAL AQUI
 * `draft_ahead_of_air` que sumisse como `undefined` é exatamente a caixa
 * escondida que a SPEC §2 proíbe. Nulo é nulo; ausente é erro de contrato.
 *
 * As leituras do servidor (`GET`) vivem em `lib/assistente/queries.ts`, que é
 * `server-only`: este módulo é o que o navegador importa — as mutações, o
 * teste em stream e as frases — e um módulo `server-only` não entra num
 * componente de cliente.
 */

export const CONFIG_PATH = "/assistente/configuracao";

/**
 * A versão de plataforma no ar — a doutrina. Só leitura em toda rota: não
 * existe papel de plataforma (SPEC §1), e ela entra por migration.
 */
export type PlatformLayer = {
  version_id: string;
  version_number: number;
  content: string;
  /** Só a plataforma escolhe o modelo. Nulos = o padrão da instalação. */
  provider: string | null;
  model: string | null;
  /** Idas à ferramenta por turno. Nulo = sem teto. */
  max_steps: number | null;
  created_at: string;
};

/** A versão de tenant no ar, se o tenant já publicou. */
export type TenantLayer = {
  version_id: string;
  version_number: number;
  content: string;
  created_at: string;
  created_by: string | null;
};

/**
 * O rascunho — o único texto mutável. `frozen_from_version_id` é a versão de
 * que ele partiu; quando difere da apontada, a tela mostra as duas (SPEC §2).
 */
export type AssistantDraft = {
  content: string;
  frozen_from_version_id: string | null;
  updated_at: string;
  updated_by: string | null;
};

/** A aba Configuração inteira, numa leitura como o usuário. */
export type PromptScreen = {
  platform: PlatformLayer;
  tenant: TenantLayer | null;
  draft: AssistantDraft | null;
  /** O limite do banco, que a tela mostra como contador — nunca fixado aqui. */
  max_length: number;
  /**
   * Rascunho existe e `frozen_from_version_id` ≠ versão de tenant apontada: o
   * caso do rollback. A tela TEM de mostrar as duas e dizer qual o botão
   * substitui.
   */
  draft_ahead_of_air: boolean;
};

export type DraftWrite = { content: string };

/** A versão nova e a que estava apontada antes (nula na primeira publicação). */
export type PublishResult = {
  version_id: string;
  version_number: number;
  previous_version_id: string | null;
};

/** Uma versão do histórico. `on_air` = apontada pelo ponteiro do escopo dela. */
export type VersionRow = {
  version_id: string;
  version_number: number;
  content: string;
  created_at: string;
  created_by: string | null;
  on_air: boolean;
};

/** As versões do tenant (restauráveis) e as da plataforma (só leitura). */
export type VersionsScreen = {
  tenant: VersionRow[];
  platform: VersionRow[];
};

/**
 * Uma linha de `fn_assistant_catalog`, como quem chama a vê. `enabled` é o
 * interruptor do tenant; `visible_to_me` é o interruptor E o domínio ao
 * alcance de quem chama — habilitar nunca concede domínio (SPEC §4.1).
 */
export type CapabilityRow = {
  code: string;
  title: string;
  description: string;
  /** pii | compensation | health | disciplinary | banking — ou nulo. */
  domain: string | null;
  enabled: boolean;
  visible_to_me: boolean;
};

export type CapabilityWrite = { enabled: boolean };

/**
 * A pergunta do teste: a mesma da conversa, gravada como dry run. `use_draft`
 * roda o rascunho no lugar da camada de tenant — e roda sempre como quem
 * chamou: não há seletor de papel (SPEC §5), e não haverá.
 */
export type AssistantTest = {
  question: string;
  model?: string;
  use_draft: boolean;
};

// ---------------------------------------------------------------------------
// Mutações — cada uma revalidada no backend (`util.is_admin` como o usuário)
// ---------------------------------------------------------------------------

export function saveDraft(content: string): Promise<AssistantDraft> {
  const body: DraftWrite = { content };

  return requestApiAsUser<AssistantDraft>(`${CONFIG_PATH}/rascunho`, {
    method: "PUT",
    body,
  });
}

export function publishPrompt(): Promise<PublishResult> {
  return requestApiAsUser<PublishResult>(`${CONFIG_PATH}/publicar`, {
    method: "POST",
  });
}

export function restoreVersion(versionId: string): Promise<TenantLayer> {
  return requestApiAsUser<TenantLayer>(
    `${CONFIG_PATH}/versoes/${versionId}/restaurar`,
    { method: "POST" },
  );
}

export function saveCapability(
  code: string,
  enabled: boolean,
): Promise<CapabilityRow> {
  const body: CapabilityWrite = { enabled };

  return requestApiAsUser<CapabilityRow>(
    `${CONFIG_PATH}/capacidades/${encodeURIComponent(code)}`,
    { method: "PUT", body },
  );
}

/**
 * O teste — o mesmo transporte da conversa, contra `/testar`. O que muda é o
 * corpo (`use_draft`) e o que o backend grava (`is_dry_run`); o parser e o
 * `res.ok` antes do primeiro byte são os mesmos.
 */
export function testAssistant(
  question: string,
  useDraft: boolean,
  options: StreamOptions,
): Promise<void> {
  const body: AssistantTest = { question, use_draft: useDraft };

  return streamAssistant(`${CONFIG_PATH}/testar`, body, options);
}

// ---------------------------------------------------------------------------
// Frases
// ---------------------------------------------------------------------------

/**
 * As cinco recusas de `fn_publish_assistant_prompt`, que chegam como
 * `detail` = o código (`assistente_config.py`). A tela prende o código, não o
 * status: `draft_unchanged` e `platform_layer_missing` são os dois 409.
 */
export const PUBLISH_DETAIL_MESSAGE: Record<string, string> = {
  not_admin: "Sem permissão para publicar.",
  draft_not_found: "Salve o rascunho antes de publicar.",
  draft_empty: "O rascunho está vazio.",
  platform_layer_missing:
    "A camada da plataforma não está publicada — fale com o suporte.",
  draft_unchanged:
    "O texto já está no ar: nada mudou desde a última publicação.",
};

const PUBLISH_FAILED = "Não consegui publicar. Nada foi alterado.";

/** A frase de uma publicação que não aconteceu: código conhecido, `detail` como veio, ou a genérica. */
export function publishFailureMessage(caught: unknown): string {
  if (caught instanceof ApiError && caught.detail) {
    return PUBLISH_DETAIL_MESSAGE[caught.detail] ?? caught.detail;
  }

  return PUBLISH_FAILED;
}

/** O rótulo pt-BR de cada domínio sensível do catálogo; nulo é "—". */
export const DOMAIN_LABEL: Record<string, string> = {
  compensation: "Remuneração",
  pii: "Dados pessoais",
  health: "Saúde",
  disciplinary: "Disciplinar",
  banking: "Bancário",
};

export function domainLabel(domain: string | null): string {
  if (domain === null) {
    return "—";
  }

  return DOMAIN_LABEL[domain] ?? domain;
}
