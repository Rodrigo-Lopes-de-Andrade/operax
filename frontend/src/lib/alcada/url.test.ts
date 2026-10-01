import { describe, expect, it } from "vitest";

import {
  approvalHref,
  approvalQuery,
  isCalendarDay,
  parseApprovalFilters,
  shiftMonth,
  type ApprovalFilters,
} from "@/lib/alcada/url";

const UNIT = "3f2504e0-4f89-41d3-9a0c-0305e82c3301";
const EMPLOYEE = "7c9e6679-7425-40de-944b-e07fc1f90ae7";

const NONE: ApprovalFilters = {
  year: null,
  month: null,
  unitId: null,
  employeeId: null,
  from: null,
  to: null,
};

const BASE: ApprovalFilters = {
  year: 2026,
  month: 10,
  unitId: null,
  employeeId: null,
  from: null,
  to: null,
};

describe("shiftMonth — aritmética de mês, sem janela", () => {
  it("anterior e seguinte", () => {
    expect(shiftMonth(2026, 10, -1)).toEqual({ year: 2026, month: 9 });
    expect(shiftMonth(2026, 10, 1)).toEqual({ year: 2026, month: 11 });
  });

  it("atravessa o ano nos dois sentidos", () => {
    expect(shiftMonth(2027, 1, -1)).toEqual({ year: 2026, month: 12 });
    expect(shiftMonth(2026, 12, 1)).toEqual({ year: 2027, month: 1 });
  });
});

describe("isCalendarDay", () => {
  it("aceita um dia que existe, inclusive 29/02 de ano bissexto", () => {
    expect(isCalendarDay("2026-09-30")).toBe(true);
    expect(isCalendarDay("2028-02-29")).toBe(true);
  });

  it("⛔ recusa o que a regex deixaria passar", () => {
    expect(isCalendarDay("2026-02-31")).toBe(false);
    expect(isCalendarDay("2026-02-29")).toBe(false);
    expect(isCalendarDay("2026-13-01")).toBe(false);
    expect(isCalendarDay("2026-09-00")).toBe(false);
    expect(isCalendarDay("30/09/2026")).toBe(false);
  });
});

describe("parseApprovalFilters", () => {
  it("sem nada na URL, a competência fica para a API decidir", () => {
    expect(parseApprovalFilters({})).toEqual(NONE);
  });

  it("⛔ ano sem mês (e mês sem ano) é descartado em par — a API daria 422", () => {
    expect(parseApprovalFilters({ ano: "2026" })).toEqual(NONE);
    expect(parseApprovalFilters({ mes: "9" })).toEqual(NONE);
  });

  it("⛔ data impossível é descartada como parâmetro ausente", () => {
    expect(
      parseApprovalFilters({ ano: "2026", mes: "3", de: "2026-02-31" }),
    ).toEqual({ ...NONE, year: 2026, month: 3 });
    expect(parseApprovalFilters({ ate: "2026-04-31" })).toEqual(NONE);
  });

  it("lê todas as chaves", () => {
    expect(
      parseApprovalFilters({
        ano: "2026",
        mes: "9",
        un: UNIT,
        col: EMPLOYEE.toUpperCase(),
        de: "2026-09-01",
        ate: "2026-09-10",
      }),
    ).toEqual({
      year: 2026,
      month: 9,
      unitId: UNIT,
      employeeId: EMPLOYEE,
      from: "2026-09-01",
      to: "2026-09-10",
    });
  });

  it("descarta o que a API recusaria, em vez de abrir uma tela que não abre", () => {
    expect(
      parseApprovalFilters({
        ano: "1999",
        mes: "13",
        un: "norte",
        col: "'; drop",
        de: "01/09/2026",
      }),
    ).toEqual(NONE);
  });
});

describe("approvalHref", () => {
  it("sem competência, o caminho é limpo — e a API escolhe a corrente", () => {
    expect(approvalHref(NONE)).toBe("/dashboard/justificativas/aprovacao");
  });

  it("leva a competência sempre, mesmo sem recorte", () => {
    expect(approvalHref(BASE)).toBe(
      "/dashboard/justificativas/aprovacao?ano=2026&mes=10",
    );
  });

  it("carrega unidade, colaborador e datas", () => {
    expect(
      approvalHref(BASE, {
        unitId: UNIT,
        employeeId: EMPLOYEE,
        from: "2026-09-22",
        to: "2026-09-25",
      }),
    ).toBe(
      `/dashboard/justificativas/aprovacao?ano=2026&mes=10&un=${UNIT}&col=${EMPLOYEE}&de=2026-09-22&ate=2026-09-25`,
    );
  });

  it("trocar de competência limpa as datas, que eram da janela anterior", () => {
    const filtered = { ...BASE, unitId: UNIT, from: "2026-09-22", to: null };

    expect(approvalHref(filtered, { month: 11 })).toBe(
      `/dashboard/justificativas/aprovacao?ano=2026&mes=11&un=${UNIT}`,
    );
  });
});

describe("approvalQuery", () => {
  it("usa os nomes da rota: unidade, colaborador, de, ate", () => {
    expect(
      approvalQuery({
        ...BASE,
        unitId: UNIT,
        employeeId: EMPLOYEE,
        from: "2026-09-22",
        to: "2026-09-25",
      }),
    ).toBe(
      `ano=2026&mes=10&unidade=${UNIT}&colaborador=${EMPLOYEE}&de=2026-09-22&ate=2026-09-25`,
    );
  });

  it("sem competência, não manda ano nem mês", () => {
    expect(approvalQuery({ ...NONE, unitId: UNIT })).toBe(`unidade=${UNIT}`);
  });

  it("não manda filtro ausente", () => {
    expect(approvalQuery(BASE)).toBe("ano=2026&mes=10");
  });
});
