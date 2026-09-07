import { describe, expect, it } from "vitest";

import {
  formatCents,
  formatCurrency,
  formatPercent,
  share,
  toCents,
} from "@/lib/dp/format";

const NBSP = " ";

describe("dinheiro em centavos", () => {
  it("lê o decimal que o Pydantic manda como string", () => {
    expect(toCents("109384.00")).toBe(10938400);
    expect(toCents("2604.38")).toBe(260438);
  });

  it("aceita o inteiro sem casas — é assim que um zero chega", () => {
    expect(toCents("0")).toBe(0);
    expect(toCents("7")).toBe(700);
  });

  it("a subtração fecha, que é a razão de ela não ser em ponto flutuante", () => {
    // 0.1 + 0.2 !== 0.3 em `number`, e o resíduo apareceria na tela como um
    // centavo sem dono na linha "salário e demais verbas da base".
    const base = toCents("1000.30");
    const resto = base - toCents("0.10") - toCents("0.20");

    expect(resto).toBe(100000);
    expect(formatCents(resto)).toBe(`R$${NBSP}1.000,00`);
  });

  it("formata centavo inteiro igual ao decimal em string", () => {
    expect(formatCents(toCents("109384.00"))).toBe(formatCurrency("109384.00"));
  });
});

describe("proporção", () => {
  it("mostra a retenção do backend em porcentagem", () => {
    expect(formatPercent("1.0000")).toBe("100,0%");
    expect(formatPercent("0.8571")).toBe("85,7%");
  });

  it("base vazia é travessão, e nunca zero por cento", () => {
    expect(formatPercent(null)).toBe("—");
  });

  it("fatia de uma folha zerada não existe — não é 0%", () => {
    expect(share(0, 0)).toBeNull();
    expect(share(2500, 10000)).toBe(25);
  });
});
