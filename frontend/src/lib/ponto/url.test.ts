import { describe, expect, it } from "vitest";

import { DEFAULT_PERIOD, type PontoFilters } from "@/lib/ponto/filters";
import { parsePaging, pontoHref } from "@/lib/ponto/url";

const FILTERS: PontoFilters = {
  period: DEFAULT_PERIOD,
  unitCode: null,
  companySlug: null,
  eventId: null,
};

const PAGING = { page: 1, pageSize: 25 } as const;

describe("parsePaging", () => {
  it("defaults to the first page and the smallest size", () => {
    expect(parsePaging({})).toEqual({ page: 1, pageSize: 25 });
  });

  it("refuses a page or a size the table does not offer", () => {
    expect(parsePaging({ pg: "0", tam: "7" })).toEqual({
      page: 1,
      pageSize: 25,
    });
    expect(parsePaging({ pg: "-3" })).toEqual({ page: 1, pageSize: 25 });
    expect(parsePaging({ pg: "2.5" })).toEqual({ page: 1, pageSize: 25 });
  });

  it("keeps a page and a size that exist", () => {
    expect(parsePaging({ pg: "4", tam: "100" })).toEqual({
      page: 4,
      pageSize: 100,
    });
  });
});

describe("pontoHref", () => {
  it("writes the link the WhatsApp alert carries", () => {
    expect(
      pontoHref(FILTERS, PAGING, { unitCode: "dev-norte", period: "hoje" }),
    ).toBe("/dashboard?un=dev-norte&per=hoje");
  });

  it("gives a clean path for the default cut", () => {
    expect(pontoHref(FILTERS, PAGING)).toBe("/dashboard");
  });

  it("sends the table back to page one when the cut narrows", () => {
    const deep = pontoHref(
      { ...FILTERS },
      { page: 7, pageSize: 25 },
      { unitCode: "dev-norte" },
    );

    expect(deep).toBe("/dashboard?un=dev-norte");
  });

  it("keeps the page when only the occurrence changes", () => {
    const href = pontoHref(
      FILTERS,
      { page: 3, pageSize: 50 },
      { eventId: "abc" },
    );

    expect(href).toBe("/dashboard?ev=abc&pg=3&tam=50");
  });

  it("resets the page when the page size changes, since page 7 of 25 is not page 7 of 100", () => {
    expect(
      pontoHref(FILTERS, { page: 7, pageSize: 25 }, { pageSize: 100 }),
    ).toBe("/dashboard?tam=100");
  });
});
