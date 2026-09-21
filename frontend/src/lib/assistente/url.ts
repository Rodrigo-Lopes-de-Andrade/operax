import type { RawSearchParams } from "@/lib/ponto/filters";
import { ADMIN_PATH } from "@/lib/rh/url";

/**
 * O assistente não tem estado de filtro na URL — a conversa é o estado, e ela
 * vive na aba. O caminho existe para a navegação e para o `NavLink` marcarem a
 * seção ativa.
 */
export const ASSISTENTE_PATH = "/dashboard/assistente";

/**
 * A configuração do assistente é outra tela, na área de administração: o
 * "Assistente" do topo é a conversa; este é o que a governa. O rótulo carrega
 * o parêntese nos dois lugares em que aparece — navegação e título — para que
 * os dois itens nunca se confundam.
 */
export const ASSISTENTE_CONFIG_PATH = `${ADMIN_PATH}/assistente`;
export const ASSISTENTE_CONFIG_LABEL = "Assistente (configuração)";

/**
 * As cinco abas, na ordem da tela. A aba mora na query string (`aba=`), como
 * toda aba deste produto: um link abre na aba certa, e o botão "voltar" do
 * navegador anda por ela.
 */
export const CONFIG_TABS = [
  "configuracao",
  "historico",
  "teste",
  "capacidades",
  "execucoes",
] as const;
export type ConfigTab = (typeof CONFIG_TABS)[number];
export const DEFAULT_CONFIG_TAB: ConfigTab = "configuracao";

export const CONFIG_TAB_LABEL: Record<ConfigTab, string> = {
  configuracao: "Configuração",
  historico: "Histórico",
  teste: "Teste",
  capacidades: "Capacidades",
  execucoes: "Execuções",
};

/**
 * A janela de Execuções, em semanas, a atual inclusa — as mesmas opções nas
 * três leituras da aba. O backend recusa fora de 1..52 com 422, e a tela
 * trata isso como estado, não como exceção: um `?semanas=` digitado à mão
 * vira frase, nunca tela branca.
 */
export const WEEKS_OPTIONS = [4, 8, 12, 26, 52] as const;
export const DEFAULT_WEEKS = 8;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function parseConfigTab(params: RawSearchParams): ConfigTab {
  const value = first(params.aba);

  return value && (CONFIG_TABS as readonly string[]).includes(value)
    ? (value as ConfigTab)
    : DEFAULT_CONFIG_TAB;
}

/**
 * A versão aberta no Histórico (`versao=`), validada como uuid antes de virar
 * comparação: um valor que não é id não seleciona nada, e não vira erro.
 */
export function parseVersionParam(params: RawSearchParams): string | null {
  const value = first(params.versao);

  return value && UUID.test(value) ? value : null;
}

/**
 * A janela de Execuções (`semanas=`). Um valor que não é número inteiro cai no
 * padrão; um número **fora** da faixa passa como veio, de propósito: quem o
 * digitou tem de ler que a faixa é 1..52, e não receber calado um recorte
 * diferente do que pediu.
 */
export function parseWeeksParam(params: RawSearchParams): number {
  const value = first(params.semanas);

  return value && /^\d+$/.test(value) ? Number(value) : DEFAULT_WEEKS;
}

export function assistenteConfigHref(
  tab: ConfigTab,
  versionId: string | null = null,
  weeks: number | null = null,
): string {
  const query = new URLSearchParams();

  if (tab !== DEFAULT_CONFIG_TAB) query.set("aba", tab);
  if (versionId) query.set("versao", versionId);
  // A semana vai escrita mesmo quando é a padrão: o link é o recorte, e um
  // link sem ela abriria outra janela no dia em que o padrão mudar.
  if (weeks !== null) query.set("semanas", String(weeks));

  const suffix = query.toString();

  return suffix
    ? `${ASSISTENTE_CONFIG_PATH}?${suffix}`
    : ASSISTENTE_CONFIG_PATH;
}
