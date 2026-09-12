import { describe, expect, it } from "vitest";

import {
  catalogHref,
  catalogQuery,
  cycleHref,
  laudosHref,
  laudosQuery,
  parseCatalogFilters,
  panelHref,
  panelQuery,
  parseCycleFilters,
  parseLaudosFilters,
  parsePanelFilters,
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

describe("recorte do painel de DP", () => {
  const EMPRESA = "22222222-2222-4222-8222-222222222222";

  it("leva empresa e unidade para a query da API e para o link", () => {
    const filters = parsePanelFilters({ un: UNIT, emp: EMPRESA });

    expect(filters).toEqual({ unitId: UNIT, companyId: EMPRESA });
    expect(panelQuery(filters)).toBe(`empresa=${EMPRESA}&unidade=${UNIT}`);
    expect(panelHref(filters)).toBe(
      `/dashboard/dp/painel?emp=${EMPRESA}&un=${UNIT}`,
    );
  });

  it("abre no tenant inteiro quando o link traz lixo", () => {
    const filters = parsePanelFilters({ un: "a-unidade-do-joao", emp: "x" });

    expect(filters).toEqual({ unitId: null, companyId: null });
    expect(panelQuery(filters)).toBe("");
    expect(panelHref(filters)).toBe("/dashboard/dp/painel");
  });

  it("trocar de empresa larga a unidade da empresa anterior", () => {
    const filters = parsePanelFilters({ un: UNIT, emp: EMPRESA });
    const outra = "33333333-3333-4333-8333-333333333333";

    expect(panelHref(filters, { companyId: outra, unitId: null })).toBe(
      `/dashboard/dp/painel?emp=${outra}`,
    );
  });

  it("só a unidade também é recorte, e a empresa não é obrigatória", () => {
    const filters = parsePanelFilters({ un: UNIT });

    expect(panelQuery(filters)).toBe(`unidade=${UNIT}`);
    expect(panelHref(filters)).toBe(`/dashboard/dp/painel?un=${UNIT}`);
  });

  // A data existe no backend (`em`) e de propósito não existe aqui: os oito
  // contadores de alerta comparam com `current_date` dentro do SQL e não a
  // aceitam. Um `em` na URL que movesse metade da tela seria pior que nenhum.
  it("ignora uma data na URL em vez de mover metade do painel", () => {
    const filters = parsePanelFilters({ em: "2026-08-31", un: UNIT });

    expect(panelQuery(filters)).toBe(`unidade=${UNIT}`);
    expect(panelHref(filters)).not.toContain("em=");
  });
});

describe("recorte dos laudos", () => {
  it("leva a unidade para a query da API e os dois filtros para o link", () => {
    const filters = parseLaudosFilters({ un: UNIT, situacao: "vencido" });

    expect(filters).toEqual({ unitId: UNIT, status: "vencido" });
    expect(laudosQuery(filters)).toBe(`unidade=${UNIT}`);
    expect(laudosHref(filters)).toBe(
      `/dashboard/administracao/laudos?un=${UNIT}&situacao=vencido`,
    );
  });

  it("⛔ a situação NÃO viaja para a API — a rota não filtra por ela de propósito", () => {
    // "A vencer" precisa de uma janela que o schema não tem para laudo; ela é
    // declarada na UI e aplicada sobre o que a API devolveu.
    const filters = parseLaudosFilters({ situacao: "a_vencer" });

    expect(filters).toEqual({ unitId: null, status: "a_vencer" });
    expect(laudosQuery(filters)).toBe("");
    expect(laudosHref(filters)).toBe(
      "/dashboard/administracao/laudos?situacao=a_vencer",
    );
  });

  it("situação que não existe cai em 'todas', e a unidade sobrevive", () => {
    const filters = parseLaudosFilters({ un: UNIT, situacao: "atrasado" });

    expect(filters).toEqual({ unitId: UNIT, status: null });
    expect(laudosHref(filters)).toBe(
      `/dashboard/administracao/laudos?un=${UNIT}`,
    );
  });

  it("abre em todas as unidades quando o link traz lixo", () => {
    const filters = parseLaudosFilters({ un: "unidade-que-nao-existe" });

    expect(filters).toEqual({ unitId: null, status: null });
    expect(laudosQuery(filters)).toBe("");
    expect(laudosHref(filters)).toBe("/dashboard/administracao/laudos");
  });

  it("trocar a situação mantém a unidade, e vice-versa", () => {
    const filters = parseLaudosFilters({ un: UNIT, situacao: "em_dia" });

    expect(laudosHref(filters, { status: "vencido" })).toBe(
      `/dashboard/administracao/laudos?un=${UNIT}&situacao=vencido`,
    );
    expect(laudosHref(filters, { unitId: null })).toBe(
      "/dashboard/administracao/laudos?situacao=em_dia",
    );
  });
});
