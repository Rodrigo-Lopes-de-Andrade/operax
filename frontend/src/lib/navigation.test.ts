import { describe, expect, it } from "vitest";

import { DEFAULT_AUTHENTICATED_PATH, safeNextPath } from "@/lib/navigation";

/**
 * The origin of the application, which is what both sinks resolve against —
 * `new URL(target, request.url)` in proxy.ts and `router.replace()` in the
 * browser. It must never be the sentinel origin `safeNextPath` parses with: a
 * test that judges the result against the same private base as the function
 * inherits whatever that base cannot see.
 */
const APP_ORIGIN = "https://app.operax.test";

/**
 * The value reaches production already decoded, because both sinks read it
 * from a query string — proxy.ts through `nextUrl.searchParams` and the login
 * page through `searchParams`. Decoding here the same way is what makes
 * `/%09/evil.test` arrive as `/<TAB>/evil.test`.
 */
function asItArrives(rawQueryValue: string) {
  return new URLSearchParams(`next=${rawQueryValue}`).get("next");
}

/**
 * Hostile input, in the spelling an alert link would carry. Every one of these
 * has to collapse to the default screen — not merely stay on this origin,
 * because "stayed on the origin" is also true of a guard that returns "/" for
 * everything, and of one that returns the attacker's path verbatim.
 */
const REJECTED = [
  // Whitespace the URL parser strips before parsing (cycle 1).
  "/%09/evil.test",
  "/%0A/evil.test",
  "/%0D/evil.test",
  "/%09//evil.test",
  "/%09%5Cevil.test",
  // Authorities, in every spelling.
  "//evil.test",
  "///evil.test",
  "/%5Cevil.test",
  "%5C/%5C/evil.test",
  "//evil.test%00",
  "/%2f%2fevil.test",
  "//evil.test:8443",
  // Absolute URLs and other schemes.
  "https://evil.test/dashboard",
  "https:/evil.test",
  "http:%5C%5Cevil.test",
  "javascript:alert(1)",
  "data:text/html,%3Cscript%3E",
  // Not a path at all.
  "dashboard",
  "%20//evil.test",
  // Dot segments: the normaliser eats them and promotes the slash behind
  // them to the first character of the path (cycle 2).
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
  "/.//",
  "/..//",
  "/%2e//",
  // The sentinel's own host (cycle 3). These resolve to the private base the
  // guard parses with, so any check phrased against that base calls them
  // same-origin while the sink resolves them somewhere else entirely.
  "/.//operax.invalid",
  "/..//operax.invalid",
  "/%2e//operax.invalid",
  "/%2E//operax.invalid",
  "/%2e%2e//operax.invalid",
  "/.///operax.invalid",
  "/a/..//operax.invalid",
  "/dashboard/../..//operax.invalid",
  "/.//operax.invalid/painel?ev=4821",
  "/.//operax.invalid?a=1",
  "/.//OPERAX.INVALID",
  "/.//operax%2Einvalid",
  "/.//operax.invalid:443",
  "/.//evil.test@operax.invalid",
  "/.%5C%5Coperax.invalid",
  "/%09.//operax.invalid",
  "/.//operax%E3%80%82invalid",
  "//operax.invalid:8443",
  // Values that make the parser itself throw. Unhandled, each of these is a
  // 500 on the login of everyone already signed in.
  "//",
  "///",
  "////",
  "//%5B",
  "//%5D",
  "//:",
  "//%20",
  "/%5C",
  "/%5C%5C",
  "/%5C/",
  "/%09//",
  "/%0A//",
  "/%0D//",
  "//@",
  "//%23",
  "//%3F",
  "//a%20b",
  // The login itself: same-origin at every hop, and a chain of them is a
  // redirect loop aimed at the manager who is already signed in.
  "/login",
  "/login?next=%2Flogin",
  "/login?next=%2Fdashboard",
];

/**
 * Values that are a path on this origin and must survive exactly as they are.
 * Percent-escapes here are literal — they arrive this way when the link is
 * double-encoded — and decoding them before parsing would turn inert text into
 * an authority.
 */
const PRESERVED: Array<[string, string]> = [
  ["/dashboard", "/dashboard"],
  ["/dashboard?ev=4821", "/dashboard?ev=4821"],
  [
    "/dashboard?unit=42&de=2026-08-18&ate=2026-08-18",
    "/dashboard?unit=42&de=2026-08-18&ate=2026-08-18",
  ],
  [
    "/dashboard?empresa=kastro&unidade=shopping-norte&periodo=hoje&direcao=faltante",
    "/dashboard?empresa=kastro&unidade=shopping-norte&periodo=hoje&direcao=faltante",
  ],
  ["/relat%C3%B3rio?ev=4821", "/relat%C3%B3rio?ev=4821"],
  ["/%2F%2Fevil.test", "/%2F%2Fevil.test"],
  ["/%5C%5Cevil.test", "/%5C%5Cevil.test"],
  ["/%09//evil.test", "/%09//evil.test"],
  ["/%00//evil.test", "/%00//evil.test"],
  ["/%252F%252Fevil.test", "/%252F%252Fevil.test"],
  ["/%E2%81%84%E2%81%84evil.test", "/%E2%81%84%E2%81%84evil.test"],
  // Normalised, not rejected: the dot segments resolve inside the path.
  ["/dashboard/../dashboard?ev=4821", "/dashboard?ev=4821"],
  ["/./", "/"],
  ["/..", "/"],
];

describe("safeNextPath", () => {
  describe.each(REJECTED)("hostile input %s", (raw) => {
    const target = () => safeNextPath(asItArrives(raw));

    it("cannot leave the origin of the application", () => {
      expect(new URL(target(), APP_ORIGIN).origin).toBe(APP_ORIGIN);
    });

    it("collapses to the default screen", () => {
      expect(target()).toBe(DEFAULT_AUTHENTICATED_PATH);
    });

    it("hands the sink something it can parse", () => {
      expect(() => new URL(target(), APP_ORIGIN)).not.toThrow();
    });
  });

  it.each(PRESERVED)("keeps %s as %s", (input, expected) => {
    expect(safeNextPath(input)).toBe(expected);
    expect(new URL(safeNextPath(input), APP_ORIGIN).origin).toBe(APP_ORIGIN);
  });

  it("does not follow a chain of logins", () => {
    let chain = "/dashboard?ev=4821";
    for (let hop = 0; hop < 25; hop += 1) {
      chain = `/login?next=${encodeURIComponent(chain)}`;
    }

    expect(safeNextPath(chain)).toBe(DEFAULT_AUTHENTICATED_PATH);
  });

  it("falls back when the parameter is absent or repeated", () => {
    expect(safeNextPath(undefined)).toBe(DEFAULT_AUTHENTICATED_PATH);
    expect(safeNextPath(null)).toBe(DEFAULT_AUTHENTICATED_PATH);
    expect(safeNextPath(["/dashboard", "/other"])).toBe("/dashboard");
  });

  it("resolves an authority that points back at this application to its root", () => {
    // Documented, not accidental: the host is the guard's own parsing base, so
    // the path is empty and "/" is the honest answer. It is same-origin, and
    // "/" itself redirects to the default screen.
    expect(safeNextPath(asItArrives("//operax.invalid"))).toBe("/");
  });
});
