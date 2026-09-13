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

export const PROVIDER_LABEL: Record<string, string> = {
  meta_cloud: "WhatsApp Cloud API (Meta)",
  z_api: "Z-API",
  uazapi: "UAZAPI",
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
