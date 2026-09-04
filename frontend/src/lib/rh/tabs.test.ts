import { describe, expect, it } from "vitest";

import type { HrEmployeeDetail } from "@/lib/rh/queries";
import { availableTabs } from "@/lib/rh/tabs";

/**
 * A asserção central do sprint: `null` e `[]` não são a mesma coisa.
 *
 * Um bloco que chega `null` é "você não alcança este domínio" e não pode virar
 * aba de jeito nenhum — nem desabilitada, nem com cadeado, nem com um texto
 * explicando que falta permissão, porque as três variantes informam que o dado
 * existe. Um bloco que chega `[]` é "não há nada registrado", e esse vira aba
 * com estado vazio.
 *
 * Testado como função pura porque é o tipo de regra que se quebra sem quebrar
 * nada: trocar `!== null` por `?.length` continua compilando, continua passando
 * em qualquer teste de "a tela renderiza", e vaza a existência de salário para
 * quem não pode vê-lo.
 */
function detalhe(overrides: Partial<HrEmployeeDetail> = {}): HrEmployeeDetail {
  return {
    employee: {
      employee_id: "aaaa0000-0000-4000-8000-000000000001",
      name: "Ana Personagem",
      registration_number: "1001",
      hr_code: "RH-01",
      cargo: "Operadora",
      status: "active",
      hired_on: "2024-03-01",
      terminated_on: null,
      employment_type: "clt",
      unit_id: null,
      unit_name: "Shopping Norte",
      company_name: null,
      department_name: null,
      manager_name: null,
    },
    sync_fields: [],
    editable_fields: [],
    enums: {},
    can_write: false,
    positions: [],
    leaves: [],
    movements: [],
    pii: null,
    // A foto acompanha `pii`; a aba de identificação não depende dela.
    photo: null,
    documents: null,
    exams: null,
    compensation: null,
    agreements: null,
    ...overrides,
  };
}

const valores = (detail: HrEmployeeDetail) =>
  availableTabs(detail).map((tab) => tab.value);

describe("availableTabs", () => {
  it("sem domínio nenhum, sobram só as abas que não são de domínio sensível", () => {
    expect(valores(detalhe())).toEqual([
      "cadastro",
      "posicao",
      "afastamentos",
      "movimentacoes",
    ]);
  });

  it("o domínio ausente não vira aba desabilitada: não vira aba", () => {
    const semRemuneracao = valores(
      detalhe({ pii: null, exams: [], compensation: null, agreements: null }),
    );

    expect(semRemuneracao).toContain("saude");
    expect(semRemuneracao).not.toContain("remuneracao");
    expect(semRemuneracao).not.toContain("acordos");
    expect(semRemuneracao).not.toContain("pessoais");
  });

  it("o domínio presente e vazio vira aba, porque vazio é um fato", () => {
    // A diferença que este teste existe para travar: `[]` não some da tela. "A
    // pessoa não tem salário registrado" é informação; escondê-la faria o
    // usuário concluir que não tem permissão.
    const tabs = availableTabs(detalhe({ compensation: [] }));

    expect(tabs.map((tab) => tab.value)).toContain("remuneracao");
    expect(tabs.find((tab) => tab.value === "remuneracao")?.count).toBe(0);
  });

  it("com todos os domínios, as oito abas aparecem", () => {
    expect(
      valores(
        detalhe({
          pii: {
            cpf: null,
            rg: null,
            pis: null,
            ctps: null,
            birth_date: null,
            mother_name: null,
            father_name: null,
            phone: null,
            personal_email: null,
          },
          documents: [],
          exams: [],
          compensation: [],
          agreements: [],
        }),
      ),
    ).toEqual([
      "cadastro",
      "posicao",
      "pessoais",
      "saude",
      "remuneracao",
      "afastamentos",
      "movimentacoes",
      "acordos",
    ]);
  });

  it("a contagem da aba é a do que veio, não a do que existe no banco", () => {
    const tabs = availableTabs(
      detalhe({
        positions: [
          {
            effective_from: "2024-03-01",
            effective_to: null,
            cargo: "Operadora",
            unit_name: null,
          },
        ],
      }),
    );

    expect(tabs.find((tab) => tab.value === "posicao")?.count).toBe(1);
  });
});
