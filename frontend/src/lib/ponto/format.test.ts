import { describe, expect, it } from "vitest";

import {
  directionWord,
  formatAge,
  formatDayShort,
  formatDuration,
  formatSignedMinutes,
  formatTime,
} from "@/lib/ponto/format";

describe("formatSignedMinutes", () => {
  it("always carries the sign, because colour alone is not the direction", () => {
    expect(formatSignedMinutes(42)).toBe("+42");
    expect(formatSignedMinutes(-15)).toBe("−15");
    expect(formatSignedMinutes(0)).toBe("0");
  });

  it("uses the typographic minus so the column stays aligned", () => {
    expect(formatSignedMinutes(-15).startsWith("-")).toBe(false);
  });
});

describe("directionWord", () => {
  it("gives the word that travels next to the colour", () => {
    expect(directionWord("surplus")).toBe("excedente");
    expect(directionWord("shortfall")).toBe("faltante");
    expect(directionWord("neutral")).toBe("sem par");
  });

  it("falls back to the neutral word for a direction it does not know", () => {
    expect(directionWord("qualquer")).toBe("sem par");
  });
});

describe("formatDuration", () => {
  it("reads a total in hours once it stops being readable in minutes", () => {
    expect(formatDuration(45)).toBe("45min");
    expect(formatDuration(60)).toBe("1h");
    expect(formatDuration(742)).toBe("12h 22min");
    expect(formatDuration(-542)).toBe("9h 2min");
  });
});

describe("formatAge", () => {
  it("says how old the data is, in the shape the header shows", () => {
    expect(formatAge(0)).toBe("agora");
    expect(formatAge(25)).toBe("há 25 min");
    expect(formatAge(112)).toBe("há 1h52");
  });
});

describe("time and day", () => {
  it("drops the seconds Postgres sends", () => {
    expect(formatTime("08:12:00")).toBe("08:12");
    expect(formatTime(null)).toBeNull();
  });

  it("shows the day the way the table does", () => {
    expect(formatDayShort("2026-08-22")).toBe("22/08");
  });
});
