import { describe, expect, it } from "vitest";

import {
  DEFAULT_PENDING_PERIOD,
  justificativasHref,
  parsePendingFilters,
  type PendingFilters,
} from "@/lib/justificativas/url";

const FILTERS: PendingFilters = {
  period: DEFAULT_PENDING_PERIOD,
  unitCode: null,
  eventId: null,
};

const PAGING = { page: 1, pageSize: 25 } as const;
const EVENT = "3f2504e0-4f89-41d3-9a0c-0305e82c3301";

describe("parsePendingFilters", () => {
  it("olha 30 dias por padrão, porque a fila é passivo e não recorte do dia", () => {
    expect(parsePendingFilters({})).toEqual({
      period: "30d",
      unitCode: null,
      eventId: null,
    });
  });

  it("aceita as mesmas chaves da gestão de ponto", () => {
    expect(
      parsePendingFilters({ un: "DEV Norte", per: "mes", ev: EVENT }),
    ).toEqual({ period: "mes", unitCode: "dev-norte", eventId: EVENT });
  });

  it("descarta um período inventado e uma ocorrência que não é uuid", () => {
    expect(parsePendingFilters({ per: "sempre", ev: "'; drop table" })).toEqual(
      {
        period: "30d",
        unitCode: null,
        eventId: null,
      },
    );
  });
});

describe("justificativasHref", () => {
  it("dá um caminho limpo para o recorte padrão", () => {
    expect(justificativasHref(FILTERS, PAGING)).toBe(
      "/dashboard/justificativas",
    );
  });

  it("abre o detalhe sem perder a página da fila", () => {
    expect(
      justificativasHref(
        FILTERS,
        { page: 3, pageSize: 50 },
        { eventId: EVENT },
      ),
    ).toBe(`/dashboard/justificativas?ev=${EVENT}&pg=3&tam=50`);
  });

  it("volta para a primeira página quando o recorte estreita", () => {
    expect(
      justificativasHref(
        FILTERS,
        { page: 7, pageSize: 25 },
        { unitCode: "dev-norte" },
      ),
    ).toBe("/dashboard/justificativas?un=dev-norte");
  });
});
