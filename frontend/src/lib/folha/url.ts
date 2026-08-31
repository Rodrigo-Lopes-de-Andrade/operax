import { ADMIN_PATH } from "@/lib/rh/url";

export const FOLHA_PATH = `${ADMIN_PATH}/folha`;

export const MESES = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
] as const;

/**
 * A competência como quem lê holerite a escreve.
 *
 * O `AAAA-MM` é o que viaja entre a aba de controle, o banco e a API — e é o que
 * não pode aparecer na tela: "2026-08" é um identificador, "agosto/2026" é um
 * mês. A conversão mora aqui para que as duas pontas não inventem cada uma a
 * sua.
 */
export function competenciaLabel(period: string): string {
  const [ano, mes] = period.split("-");
  const indice = Number(mes) - 1;
  const nome = MESES[indice];

  return nome ? `${nome}/${ano}` : period;
}

/** O caminho do modelo da competência, do jeito que o endpoint o espera. */
export function templateHref(ano: number, mes: number): string {
  return `/folha/template?ano=${ano}&mes=${mes}`;
}

/** O nome que o arquivo salvo recebe se a resposta não trouxer um. */
export function templateFilename(ano: number, mes: number): string {
  return `folha-${ano}-${String(mes).padStart(2, "0")}.xlsx`;
}
