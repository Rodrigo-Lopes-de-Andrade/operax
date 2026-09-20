import { describe, expect, it } from "vitest";

import { diffLines } from "@/lib/assistente/diff";

/**
 * Os quatro movimentos que um prompt sofre entre versões — e o que a tela
 * mostra ao lado de uma versão do Histórico é a soma deles.
 */
describe("diffLines", () => {
  it("textos iguais: toda linha é `same`, e nenhuma é inventada", () => {
    const text = "Responda em português.\nDeclare o período.";

    expect(diffLines(text, text)).toEqual([
      { kind: "same", text: "Responda em português." },
      { kind: "same", text: "Declare o período." },
    ]);
  });

  it("inserção: a linha nova é `added` no lugar em que entrou", () => {
    expect(
      diffLines(
        "Responda em português.\nDeclare o período.",
        "Responda em português.\nNunca diga hora extra.\nDeclare o período.",
      ),
    ).toEqual([
      { kind: "same", text: "Responda em português." },
      { kind: "added", text: "Nunca diga hora extra." },
      { kind: "same", text: "Declare o período." },
    ]);
  });

  it("remoção: a linha que saiu é `removed`, e as outras seguem `same`", () => {
    expect(
      diffLines(
        "Responda em português.\nNunca diga hora extra.\nDeclare o período.",
        "Responda em português.\nDeclare o período.",
      ),
    ).toEqual([
      { kind: "same", text: "Responda em português." },
      { kind: "removed", text: "Nunca diga hora extra." },
      { kind: "same", text: "Declare o período." },
    ]);
  });

  it("troca: a linha antiga sai e a nova entra — as duas aparecem", () => {
    expect(
      diffLines(
        "Responda em português.\nSeja breve.\nDeclare o período.",
        "Responda em português.\nSeja direto.\nDeclare o período.",
      ),
    ).toEqual([
      { kind: "same", text: "Responda em português." },
      { kind: "removed", text: "Seja breve." },
      { kind: "added", text: "Seja direto." },
      { kind: "same", text: "Declare o período." },
    ]);
  });

  it("texto vazio não vira uma linha vazia: contra um texto, é tudo `added`", () => {
    expect(diffLines("", "Uma linha.")).toEqual([
      { kind: "added", text: "Uma linha." },
    ]);
    expect(diffLines("", "")).toEqual([]);
  });
});
