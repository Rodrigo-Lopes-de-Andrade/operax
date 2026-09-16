/**
 * O vocabulário em pt-BR do canal de alertas.
 *
 * ⛔ O ÚNICO ARQUIVO DE `src/` QUE ESCREVE O NOME DE UM PROVEDOR
 * É o análogo, no frontend, de `operax/alertas/capacidades.py`: um lugar só com
 * os nomes, e todo o resto pergunta. A SPEC-CANAIS §1 manda que feature nenhuma
 * decida por *com quem* falamos, só por *o que o canal permite* — e o que o
 * canal permite chega pronto em `capabilities`, calculado pelo backend a partir
 * da matriz. Aqui o nome serve para uma coisa: o rótulo que a pessoa lê.
 * `labels.test.ts` varre `src/` e reprova o primeiro `if provider === "…"` que
 * aparecer fora daqui.
 */

/**
 * Os dois canais, na ordem em que a tela os mostra, e o rótulo de cada um.
 *
 * `telegram` é o único nome que é canal **e** provedor ao mesmo tempo, e a
 * varredura de `labels.test.ts` não distingue os dois usos — nem precisa,
 * desde que todo `telegram` do `src/` saia deste arquivo. Por isso o tipo
 * `Channel` mora aqui e não em `queries.ts`: escrever a união lá seria o
 * primeiro literal fora de casa.
 */
export const CHANNELS = ["whatsapp", "telegram"] as const;

export type Channel = (typeof CHANNELS)[number];

export const CHANNEL_LABEL: Record<Channel, string> = {
  whatsapp: "WhatsApp",
  telegram: "Telegram",
};

/**
 * Os quatro provedores: os três de WhatsApp (o par de `WHATSAPP_PROVIDERS` do
 * backend e do índice `integration_whatsapp_unico_ativo`) e o do Telegram (o
 * quarto de `CHANNEL_PROVIDERS`, com o índice irmão `integration_telegram_unico_ativo`).
 */
export const PROVIDER_LABEL: Record<string, string> = {
  meta_cloud: "WhatsApp Cloud API (Meta)",
  z_api: "Z-API",
  uazapi: "UAZAPI",
  telegram: "Telegram",
};

/**
 * Os cinco estados de `app.message_template.meta_status` (migration 14). O
 * estado é o que a Meta diz do template, e a tela o traduz sem o esconder: um
 * valor novo no `check` aparece cru até alguém o traduzir aqui.
 */
export const META_STATUS_LABEL: Record<string, string> = {
  draft: "rascunho",
  pending: "pendente",
  approved: "aprovado",
  rejected: "rejeitado",
  paused: "pausado",
};

/** O código cru quando não há tradução — feio, e honesto. */
export function label(map: Record<string, string>, code: string): string {
  return map[code] ?? code;
}
