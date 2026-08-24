import { describe, expect, it } from "vitest";

import {
  COLABORADORES_PATH,
  DEFAULT_TAB,
  EMPTY_FILTERS,
  employeeHref,
  parseRhFilters,
  parseTab,
  rhHref,
  rhQuery,
} from "@/lib/rh/url";

/**
 * O recorte mora na URL, e a URL vem de fora. Um valor que o backend recusaria
 * não pode chegar até ele vindo daqui — e, mais importante, não pode virar
 * estado de tela: um filtro "?st=demitido" que a tela mostra como aplicado e a
 * API ignora é uma lista errada com cara de lista certa.
 */
describe("parseRhFilters", () => {
  it("lê o recorte inteiro da query string", () => {
    expect(
      parseRhFilters({ un: "u-1", st: "afastado", pd: "aso", q: " silva " }),
    ).toEqual({
      unit: "u-1",
      status: "afastado",
      pendencia: "aso",
      busca: "silva",
    });
  });

  it("descarta valor fora do catálogo em vez de repassá-lo", () => {
    expect(parseRhFilters({ st: "demitido", pd: "uniforme" })).toEqual({
      unit: null,
      status: null,
      pendencia: null,
      busca: null,
    });
  });

  it("busca só com espaço é busca vazia", () => {
    expect(parseRhFilters({ q: "   " }).busca).toBeNull();
  });

  it("parâmetro repetido usa o primeiro, como o resto do produto", () => {
    expect(parseRhFilters({ st: ["active", "desligado"] }).status).toBe(
      "active",
    );
  });
});

describe("rhHref", () => {
  it("sem filtro nenhum, o caminho fica limpo", () => {
    expect(rhHref(EMPTY_FILTERS)).toBe(COLABORADORES_PATH);
  });

  it("limpar um filtro tira o parâmetro da URL", () => {
    const comUnidade = {
      ...EMPTY_FILTERS,
      unit: "u-1",
      status: "active" as const,
    };

    expect(rhHref(comUnidade, { unit: null })).toBe(
      `${COLABORADORES_PATH}?st=active`,
    );
  });

  it("o link e a leitura são a mesma coisa: ida e volta preserva o recorte", () => {
    const filtros = parseRhFilters({ un: "u-9", st: "vacation", q: "ana" });
    const href = rhHref(filtros);
    const devolta = parseRhFilters(
      Object.fromEntries(new URL(href, "https://x.test").searchParams),
    );

    expect(devolta).toEqual(filtros);
  });
});

describe("rhQuery", () => {
  it("traduz o recorte para os nomes que a API espera", () => {
    expect(
      rhQuery({
        unit: "u-1",
        status: "desligado",
        pendencia: "vinculo",
        busca: "ana",
      }),
    ).toBe("unidade=u-1&status=desligado&pendencia=vinculo&busca=ana");
  });

  it("filtro vazio não vira parâmetro vazio", () => {
    expect(rhQuery(EMPTY_FILTERS)).toBe("");
  });
});

describe("parseTab", () => {
  it("aba desconhecida cai na primeira, sem erro", () => {
    expect(parseTab({ aba: "salarios" })).toBe(DEFAULT_TAB);
  });

  it("aba conhecida é respeitada", () => {
    expect(parseTab({ aba: "remuneracao" })).toBe("remuneracao");
  });
});

describe("employeeHref", () => {
  it("a aba padrão não suja o link", () => {
    expect(employeeHref("abc")).toBe(`${COLABORADORES_PATH}/abc`);
    expect(employeeHref("abc", DEFAULT_TAB)).toBe(`${COLABORADORES_PATH}/abc`);
  });

  it("a aba escolhida vai na URL, para o link abrir onde se estava", () => {
    expect(employeeHref("abc", "saude")).toBe(
      `${COLABORADORES_PATH}/abc?aba=saude`,
    );
  });
});
