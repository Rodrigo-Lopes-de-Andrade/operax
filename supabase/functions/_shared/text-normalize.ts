// Normalização de nome usada exclusivamente na "Resolução do gestor"
// (docs/03-integracao-secullum.md). Regra obrigatória, não opcional:
//   1. trim + colapso de espaços internos repetidos em um único espaço;
//   2. case-insensitive;
//   3. remoção de acentos/diacríticos (Unicode NFD + descarte de marcas de combinação);
//   4. comparação por IGUALDADE EXATA da string inteira após normalização —
//      proibido contains/prefixo/fuzzy/distância de edição.
//
// Este módulo não deve crescer para virar um "matcher fuzzy" — a régua do
// projeto é deliberadamente rígida (docs/06-seguranca-lgpd.md: um match
// errado envia dados de jornada de uma unidade para a pessoa errada).

/**
 * Normaliza um nome de pessoa física para comparação exata.
 * Ex.: "  José  DA Silva " -> "jose da silva"
 */
const COMBINING_DIACRITICAL_MARKS = new RegExp("[\\u0300-\\u036f]", "g");

export function normalizePersonName(rawName: string): string {
  return rawName
    .normalize("NFD")
    .replace(COMBINING_DIACRITICAL_MARKS, "") // remove marcas de acentuação combinadas (NFD)
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
}
