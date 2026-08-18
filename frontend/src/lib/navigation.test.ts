import { describe, expect, it } from "vitest";

import { DEFAULT_AUTHENTICATED_PATH, safeNextPath } from "@/lib/navigation";

describe("safeNextPath", () => {
  it("keeps a relative path with its query string", () => {
    expect(safeNextPath("/dashboard?unit=42&de=2026-08-18")).toBe(
      "/dashboard?unit=42&de=2026-08-18",
    );
  });

  it("refuses anything that could leave the application", () => {
    expect(safeNextPath("https://evil.test/dashboard")).toBe(
      DEFAULT_AUTHENTICATED_PATH,
    );
    expect(safeNextPath("//evil.test/dashboard")).toBe(
      DEFAULT_AUTHENTICATED_PATH,
    );
    expect(safeNextPath("/\\evil.test")).toBe(DEFAULT_AUTHENTICATED_PATH);
    expect(safeNextPath("dashboard")).toBe(DEFAULT_AUTHENTICATED_PATH);
  });

  it("falls back when the parameter is absent or repeated", () => {
    expect(safeNextPath(undefined)).toBe(DEFAULT_AUTHENTICATED_PATH);
    expect(safeNextPath(null)).toBe(DEFAULT_AUTHENTICATED_PATH);
    expect(safeNextPath(["/dashboard", "/other"])).toBe("/dashboard");
  });
});
