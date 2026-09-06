import { describe, expect, it } from "vitest";

import {
  catalogHref,
  catalogQuery,
  cycleHref,
  parseCatalogFilters,
  parseCycleFilters,
  parsePostosFilters,
  postosHref,
  postosQuery,
} from "@/lib/dp/url";

const UNIT = "11111111-1111-4111-8111-111111111111";

describe("recorte do Quadro de Postos", () => {
  it("leva a unidade para a query da API e para o link", () => {
    const filters = parsePostosFilters({ un: UNIT });

    expect(filters.unitId).toBe(UNIT);
    expect(postosQuery(filters)).toBe(`unidade=${UNIT}`);
    expect(postosHref(filters)).toBe(
      `/dashboard/administracao/postos?un=${UNIT}`,
    );
  });

  it("abre em todas as unidades quando o link traz lixo", () => {
    const filters = parsePostosFilters({ un: "unidade-que-nao-existe" });

    expect(filters.unitId).toBeNull();
    expect(postosQuery(filters)).toBe("");
    expect(postosHref(filters)).toBe("/dashboard/administracao/postos");
  });
});

describe("recorte do catálogo", () => {
  it("guarda a aba e a data da vigência consultada", () => {
    const filters = parseCatalogFilters({
      tipo: "health_plan",
      em: "2026-08-31",
    });

    expect(filters).toEqual({ type: "health_plan", on: "2026-08-31" });
    expect(catalogQuery(filters)).toBe("em=2026-08-31");
  });

  it("trocar de aba não perde a data — é o mesmo catálogo, noutro tipo", () => {
    const filters = parseCatalogFilters({
      tipo: "health_plan",
      em: "2026-08-31",
    });

    expect(catalogHref(filters, { type: "transport_voucher" })).toBe(
      "/dashboard/administracao/beneficios?tipo=transport_voucher&em=2026-08-31",
    );
  });

  it("data malformada vira ausência, e ausência é 'hoje' para o backend", () => {
    const filters = parseCatalogFilters({ em: "31/08/2026" });

    expect(filters.on).toBeNull();
    expect(catalogQuery(filters)).toBe("");
    expect(catalogHref(filters)).toBe("/dashboard/administracao/beneficios");
  });
});

describe("competência do ciclo", () => {
  it("lê rotina, ano e mês do link", () => {
    const filters = parseCycleFilters(
      { tipo: "transport_voucher", ano: "2026", mes: "9" },
      "2026-09-06",
    );

    expect(filters).toEqual({
      kind: "transport_voucher",
      year: 2026,
      month: 9,
    });
  });

  it("cai no mês corrente quando o link não diz nada", () => {
    expect(parseCycleFilters({}, "2026-09-06")).toEqual({
      kind: "food_basket",
      year: 2026,
      month: 9,
    });
  });

  it("recusa competência fora do que o backend aceita, sem quebrar a tela", () => {
    // 2100 é o teto de `CycleRequest`; 13 não é mês. Os dois voltariam 422 e a
    // tela não abriria — e um link velho tem de abrir.
    const filters = parseCycleFilters(
      { tipo: "cesta_basica", ano: "9999", mes: "13" },
      "2026-09-06",
    );

    expect(filters).toEqual({ kind: "food_basket", year: 2026, month: 9 });
  });

  it("o link carrega a competência inteira, sempre", () => {
    const filters = parseCycleFilters({}, "2026-09-06");

    // Sem os três, o link abriria no mês de quem clicou — que é o oposto de
    // "confere o vale transporte de agosto".
    expect(cycleHref(filters, { kind: "transport_voucher", month: 8 })).toBe(
      "/dashboard/dp/ciclos?tipo=transport_voucher&ano=2026&mes=8",
    );
  });
});
