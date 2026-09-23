import { ADMIN_PATH } from "@/lib/rh/url";

export const CONEXOES_PATH = `${ADMIN_PATH}/conexoes`;
export const TEMPLATES_PATH = `${ADMIN_PATH}/templates`;
export const DESTINATARIOS_PATH = `${ADMIN_PATH}/destinatarios`;
export const REGRAS_PATH = `${ADMIN_PATH}/regras`;

/**
 * Uma regra dentro da lista de Regras — o destino do link que o 409 de
 * Destinatários oferece para cada regra que segura um contato. É âncora, não
 * filtro: a lista é a mesma, e a URL só diz onde olhar.
 */
export function ruleHref(ruleId: string): string {
  return `${REGRAS_PATH}#regra-${ruleId}`;
}
