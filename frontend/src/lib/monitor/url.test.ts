import { describe, expect, it } from "vitest";

import {
  monitorHref,
  MONITOR_PATH,
  parseMonitorFilters,
  shiftDay,
  type MonitorFilters,
} from "@/lib/monitor/url";

const TODAY = "2026-08-22";
const FILTERS: MonitorFilters = { day: TODAY, unitCode: null };

describe("parseMonitorFilters", () => {
  it("watches today when the link says nothing", () => {
    expect(parseMonitorFilters({}, TODAY)).toEqual({
      day: TODAY,
      unitCode: null,
    });
  });

  it("honours a day in the past — that is what the parameter is for", () => {
    expect(parseMonitorFilters({ dia: "2026-08-19" }, TODAY).day).toBe(
      "2026-08-19",
    );
  });

  it("refuses to look forward", () => {
    // A monitor watches; it does not forecast. Tomorrow has a roster and no
    // readings, so the screen would show a whole shift as "sem indício".
    expect(parseMonitorFilters({ dia: "2026-08-23" }, TODAY).day).toBe(TODAY);
  });

  it("falls back to today on a day that is not one", () => {
    expect(parseMonitorFilters({ dia: "ontem" }, TODAY).day).toBe(TODAY);
    expect(parseMonitorFilters({ dia: "2026-8-2" }, TODAY).day).toBe(TODAY);
    expect(parseMonitorFilters({ dia: "" }, TODAY).day).toBe(TODAY);
  });

  it("normalises the unit the way every other link does", () => {
    expect(parseMonitorFilters({ un: "Dev Norte" }, TODAY).unitCode).toBe(
      "dev-norte",
    );
  });

  it("reads the first value when a key repeats", () => {
    expect(
      parseMonitorFilters({ dia: ["2026-08-20", "2026-08-21"] }, TODAY).day,
    ).toBe("2026-08-20");
  });
});

describe("monitorHref", () => {
  it("keeps the everyday link short enough to read inside a message", () => {
    expect(monitorHref(FILTERS, TODAY)).toBe(MONITOR_PATH);
    expect(monitorHref(FILTERS, TODAY, { unitCode: "dev-norte" })).toBe(
      `${MONITOR_PATH}?un=dev-norte`,
    );
  });

  it("writes the day only when it is not today", () => {
    expect(monitorHref(FILTERS, TODAY, { day: "2026-08-19" })).toBe(
      `${MONITOR_PATH}?dia=2026-08-19`,
    );
  });

  it("clears the unit with an explicit null, and keeps it otherwise", () => {
    const scoped: MonitorFilters = { day: TODAY, unitCode: "dev-norte" };

    expect(monitorHref(scoped, TODAY, { day: "2026-08-19" })).toBe(
      `${MONITOR_PATH}?dia=2026-08-19&un=dev-norte`,
    );
    expect(monitorHref(scoped, TODAY, { unitCode: null })).toBe(MONITOR_PATH);
  });
});

describe("shiftDay", () => {
  it("walks the calendar, not the clock", () => {
    expect(shiftDay("2026-08-22", -1)).toBe("2026-08-21");
    expect(shiftDay("2026-03-01", -1)).toBe("2026-02-28");
    expect(shiftDay("2026-12-31", 1)).toBe("2027-01-01");
  });

  it("crosses a DST change without losing a day", () => {
    // São Paulo has no DST today, but the arithmetic must not depend on that:
    // a local `Date` would give 21 hours here and land on the wrong day.
    expect(shiftDay("2026-10-18", 1)).toBe("2026-10-19");
  });
});
