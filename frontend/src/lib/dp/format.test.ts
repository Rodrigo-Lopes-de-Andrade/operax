import { describe, expect, it } from "vitest";

import {
  formatCents,
  formatCurrency,
  formatDayInTenantZone,
  formatPercent,
  LEAVE_CATEGORIES,
  LEAVE_CATEGORY_LABEL,
  PAYROLL_CATEGORIES,
  PAYROLL_CATEGORY_LABEL,
  PAYROLL_NATURE_LABEL,
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

describe("rótulos da curadoria de rubrica", () => {
  it("são as nove categorias do `check` da migration 30, na ordem do select", () => {
    expect(PAYROLL_CATEGORIES).toEqual([
      "base_salary",
      "overtime",
      "vacation",
      "thirteenth",
      "termination",
      "benefit",
      "charge",
      "deduction",
      "other",
    ]);
    expect(PAYROLL_CATEGORY_LABEL.overtime).toBe("Horas adicionais");
    expect(PAYROLL_CATEGORY_LABEL.thirteenth).toBe("13º salário");
  });

  it("⛔ nenhum rótulo de UI diz 'hora extra'", () => {
    // O registro oficial é o sistema de ponto, e o OperaX aponta indício —
    // vocabulário de produto do CLAUDE.md. `overtime` é a verba da folha, e o
    // nome dela na tela não pode ser um veredito sobre a jornada.
    for (const rotulo of [
      ...Object.values(PAYROLL_CATEGORY_LABEL),
      ...Object.values(PAYROLL_NATURE_LABEL),
    ]) {
      expect(rotulo.toLowerCase()).not.toMatch(/hora\s*extra/);
    }
  });
});

describe("rótulos da curadoria de justificativa de afastamento", () => {
  it("são as cinco do `check` da tabela, na ordem em que a curadoria escolhe", () => {
    expect(LEAVE_CATEGORIES).toEqual([
      "vacation",
      "leave_period",
      "leave_of_absence",
      "suspension",
      "unjustified_absence",
    ]);
  });

  it("⛔ a quinta existe aqui, e é a que `lib/rh/labels` não tem", () => {
    // `unjustified_absence` não aparece em nenhuma tela de RH, e é justamente a
    // que separa "uma em 64 é falta" de "as outras 63 não são". Importar o mapa
    // de lá deixaria a curadoria sem a categoria que decide perder a cesta.
    expect(LEAVE_CATEGORY_LABEL.unjustified_absence).toBe(
      "Falta injustificada",
    );
  });

  it("⛔ nenhum rótulo diz o motivo — regra 10, e ela vale na tela também", () => {
    // A categoria é do domínio, não do caso de alguém: este produto não guarda
    // diagnóstico, CID nem restrição, e um rótulo como "licença médica" faria a
    // tela nomear saúde onde o banco guarda só a classificação.
    for (const rotulo of Object.values(LEAVE_CATEGORY_LABEL)) {
      expect(rotulo.toLowerCase()).not.toMatch(
        /m[eé]dic|atestado|doen|sa[uú]de|cid|gestante|acidente/,
      );
    }
  });
});

describe("o dia de um timestamptz", () => {
  it("⛔ o aval das 21h30 é do dia 8, e não do 9 — o fuso é o do tenant", () => {
    // `2026-09-09T00:30:00Z` é 08/09 às 21h30 em Brasília. Cortar a string ISO
    // nos dez primeiros caracteres mostraria 09/09 para quem clicou no dia 8, e
    // a curadoria passaria a ter a data errada toda noite.
    expect(formatDayInTenantZone("2026-09-09T00:30:00Z")).toBe("08/09/2026");
    expect(formatDayInTenantZone("2026-09-08T14:30:00Z")).toBe("08/09/2026");
  });

  it("sem valor é travessão, e valor inválido também", () => {
    expect(formatDayInTenantZone(null)).toBe("—");
    expect(formatDayInTenantZone("")).toBe("—");
    expect(formatDayInTenantZone("nunca")).toBe("—");
  });
});
