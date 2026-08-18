import { describe, expect, it } from "vitest";

import { DEFAULT_AUTHENTICATED_PATH, safeNextPath } from "@/lib/navigation";

const APP_ORIGIN = "https://app.operax.test";

/**
 * The value reaches production already decoded, because both sinks read it
 * from a query string — proxy.ts through `nextUrl.searchParams` and the login
 * page through `searchParams`. Decoding here the same way is what makes
 * `/%09/evil.test` arrive as `/<TAB>/evil.test`, which is the whole point.
 */
function asItArrives(rawQueryValue: string) {
  return new URLSearchParams(`next=${rawQueryValue}`).get("next");
}

/**
 * Every vector an alert link could carry. The assertion is never string
 * equality: what matters is that the value cannot resolve to another origin
 * once `new URL()` or `router.replace()` gets hold of it.
 */
const ESCAPE_VECTORS = [
  // Whitespace the URL parser removes before parsing — the reason a regex on
  // the raw string is not enough.
  "/%09/evil.test",
  "/%0A/evil.test",
  "/%0D/evil.test",
  "/%09//evil.test",
  "/%09%5Cevil.test",
  "/%09%5C%5Cevil.test",
  // Authorities, in every spelling.
  "//evil.test",
  "///evil.test",
  "/%5Cevil.test",
  "%5C/%5C/evil.test",
  "//evil.test%00",
  "/%2f%2fevil.test",
  // Absolute URLs and other schemes.
  "https://evil.test/dashboard",
  "https:/evil.test",
  "http:%5C%5Cevil.test",
  "javascript:alert(1)",
  "data:text/html,%3Cscript%3E",
  // Not a path at all.
  "dashboard",
  "%20//evil.test",
  // Dot segments. The path normaliser eats ".", "..", "%2e" and "%2E", and
  // the slash behind them becomes the first character of the path — an
  // authority the input never spelled out.
  "/.//evil.test",
  "/..//evil.test",
  "/%2e//evil.test",
  "/%2E//evil.test",
  "/%2e%2e//evil.test",
  "/.///evil.test",
  "/a/..//evil.test",
  "/dashboard/../..//evil.test",
  "/%252e//evil.test",
  "/.%2F%2Fevil.test",
  // Encodings and look-alikes that stay on this origin and must not be
  // mistaken for an escape.
  "/%252F%252Fevil.test",
  "/%E2%81%84%E2%81%84evil.test",
  "/%EF%BC%8F%EF%BC%8Fevil.test",
  "/%0B/evil.test",
  "/%0C/evil.test",
  "/%00/evil.test",
];

describe("safeNextPath", () => {
  it.each(ESCAPE_VECTORS)("cannot leave the application origin: %s", (raw) => {
    const target = safeNextPath(asItArrives(raw));

    expect(new URL(target, APP_ORIGIN).origin).toBe(APP_ORIGIN);
  });

  it("closes the TAB, LF and CR redirect", () => {
    // Regression: these three passed a regex guard and resolved to
    // //evil.test, in the proxy and after a successful sign-in alike.
    expect(safeNextPath("/\t/evil.test")).toBe(DEFAULT_AUTHENTICATED_PATH);
    expect(safeNextPath("/\n/evil.test")).toBe(DEFAULT_AUTHENTICATED_PATH);
    expect(safeNextPath("/\r/evil.test")).toBe(DEFAULT_AUTHENTICATED_PATH);
  });

  it.each(["/.//", "/..//", "/%2e//", "/./", "/.."])(
    "hands the sink something it can parse: %s",
    (raw) => {
      // A path that normalises to "//" with no host makes `new URL()` throw,
      // which in the proxy is a 500 on the login of everyone already signed in.
      const target = safeNextPath(asItArrives(raw));

      expect(() => new URL(target, APP_ORIGIN)).not.toThrow();
    },
  );

  it("keeps a relative path with its query string", () => {
    expect(safeNextPath("/dashboard?unit=42&de=2026-08-18")).toBe(
      "/dashboard?unit=42&de=2026-08-18",
    );
    // The shape the consolidated report will send over WhatsApp.
    expect(
      safeNextPath("/dashboard?unit=42&de=2026-08-18&ate=2026-08-18"),
    ).toBe("/dashboard?unit=42&de=2026-08-18&ate=2026-08-18");
  });

  it("returns a value already normalised for the caller", () => {
    // Whatever survives is what proxy.ts and router.replace() receive, so it
    // must not need a second parse to be safe.
    expect(safeNextPath("/dashboard/../dashboard?ev=4821")).toBe(
      "/dashboard?ev=4821",
    );
    expect(safeNextPath(asItArrives("/%09/evil.test"))).toBe(
      DEFAULT_AUTHENTICATED_PATH,
    );
  });

  it("falls back when the parameter is absent or repeated", () => {
    expect(safeNextPath(undefined)).toBe(DEFAULT_AUTHENTICATED_PATH);
    expect(safeNextPath(null)).toBe(DEFAULT_AUTHENTICATED_PATH);
    expect(safeNextPath(["/dashboard", "/other"])).toBe("/dashboard");
  });
});
