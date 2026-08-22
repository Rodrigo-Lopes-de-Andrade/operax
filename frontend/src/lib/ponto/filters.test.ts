import { describe, expect, it } from "vitest";

import {
  DEFAULT_PERIOD,
  eachDay,
  parseFilters,
  periodRange,
  slugify,
  todayInTenantZone,
  toSearchParams,
  type PontoFilters,
} from "@/lib/ponto/filters";

const EVENT = "7c9e6679-7425-40de-944b-e07fc1f90ae7";

describe("parseFilters", () => {
  it("falls back to the default period when the value is not one of the four", () => {
    expect(parseFilters({ per: "trimestre" }).period).toBe(DEFAULT_PERIOD);
    expect(parseFilters({}).period).toBe(DEFAULT_PERIOD);
  });

  it("keeps the four periods the screen offers", () => {
    expect(parseFilters({ per: "hoje" }).period).toBe("hoje");
    expect(parseFilters({ per: "30d" }).period).toBe("30d");
    expect(parseFilters({ per: "mes" }).period).toBe("mes");
  });

  it("normalises the unit and company keys, so a link typed by hand still lands", () => {
    const filters = parseFilters({ un: "DEV-Norte", emp: "Dev Um" });

    expect(filters.unitCode).toBe("dev-norte");
    expect(filters.companySlug).toBe("dev-um");
  });

  it("takes the first value when a key repeats", () => {
    expect(parseFilters({ un: ["dev-norte", "dev-sul"] }).unitCode).toBe(
      "dev-norte",
    );
  });

  it("only accepts an occurrence id that is a uuid", () => {
    expect(parseFilters({ ev: EVENT }).eventId).toBe(EVENT);
    expect(parseFilters({ ev: "4821" }).eventId).toBeNull();
    expect(parseFilters({ ev: "' or 1=1--" }).eventId).toBeNull();
  });
});

describe("toSearchParams", () => {
  const base: PontoFilters = {
    period: DEFAULT_PERIOD,
    unitCode: null,
    companySlug: null,
    eventId: null,
  };

  it("omits the default period so a clean cut gives a clean URL", () => {
    expect(toSearchParams(base).toString()).toBe("");
  });

  it("round-trips every filter the screen sets", () => {
    const filters: PontoFilters = {
      period: "hoje",
      unitCode: "dev-norte",
      companySlug: "dev-um",
      eventId: EVENT,
    };

    expect(parseFilters(Object.fromEntries(toSearchParams(filters)))).toEqual(
      filters,
    );
  });

  it("orders the keys the way the alert link reads them", () => {
    expect(
      toSearchParams({
        ...base,
        period: "hoje",
        unitCode: "dev-norte",
      }).toString(),
    ).toBe("un=dev-norte&per=hoje");
  });
});

describe("periodRange", () => {
  it("counts today in, so '7 dias' is seven days and not eight", () => {
    expect(periodRange("7d", "2026-08-22")).toEqual({
      de: "2026-08-16",
      ate: "2026-08-22",
    });
    expect(eachDay(periodRange("7d", "2026-08-22"))).toHaveLength(7);
  });

  it("reads 'hoje' as a single day", () => {
    expect(periodRange("hoje", "2026-08-22")).toEqual({
      de: "2026-08-22",
      ate: "2026-08-22",
    });
  });

  it("crosses the month boundary without leaving the calendar", () => {
    expect(periodRange("30d", "2026-03-05")).toEqual({
      de: "2026-02-04",
      ate: "2026-03-05",
    });
    expect(periodRange("7d", "2026-01-02")).toEqual({
      de: "2025-12-27",
      ate: "2026-01-02",
    });
  });

  it("starts the month period on the first, not 30 days back", () => {
    expect(periodRange("mes", "2026-08-22")).toEqual({
      de: "2026-08-01",
      ate: "2026-08-22",
    });
  });
});

describe("todayInTenantZone", () => {
  it("uses the tenant day, not the server day", () => {
    // 02:30 UTC on the 23rd is still the 22nd in São Paulo (UTC-3), and the
    // dashboard of a night shift must not jump a day at 21:00 local.
    expect(todayInTenantZone(new Date("2026-08-23T02:30:00Z"))).toBe(
      "2026-08-22",
    );
  });
});

describe("slugify", () => {
  it("drops the accent so the link survives being retyped", () => {
    expect(slugify("Rodoviária")).toBe("rodoviaria");
    expect(slugify("Shopping Norte")).toBe("shopping-norte");
  });
});
