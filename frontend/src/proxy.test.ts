// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PATHNAME_HEADER } from "@/lib/navigation";
import { proxy } from "@/proxy";

const APP_ORIGIN = "https://app.operax.test";

const mocks = vi.hoisted(() => ({ getUser: vi.fn() }));

vi.mock("@/lib/supabase-server", () => ({
  createServerSupabaseClient: () => ({ auth: { getUser: mocks.getUser } }),
}));

function signedIn(user: { id: string } | null) {
  mocks.getUser.mockResolvedValue({ data: { user }, error: null });
}

function request(path: string) {
  return new NextRequest(new URL(path, APP_ORIGIN));
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("proxy", () => {
  it("sends the anonymous visitor to the login keeping the deep link", async () => {
    signedIn(null);

    const response = await proxy(request("/dashboard?unit=42&de=2026-08-18"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      `${APP_ORIGIN}/login?next=%2Fdashboard%3Funit%3D42%26de%3D2026-08-18`,
    );
  });

  it("lets the anonymous visitor reach the login and forwards the path", async () => {
    signedIn(null);

    const response = await proxy(request("/login?next=%2Fdashboard"));

    expect(response.headers.get("location")).toBeNull();
    expect(
      response.headers.get("x-middleware-request-" + PATHNAME_HEADER),
    ).toBe("/login?next=%2Fdashboard");
  });

  it("takes the signed-in user from the login to where the link pointed", async () => {
    signedIn({ id: "user-1" });

    const response = await proxy(
      request("/login?next=%2Fdashboard%3Fev%3D4821"),
    );

    expect(response.headers.get("location")).toBe(
      `${APP_ORIGIN}/dashboard?ev=4821`,
    );
  });

  it.each([
    "/.//operax.invalid",
    "/..//operax.invalid",
    "/.//evil.test",
    "/..//evil.test",
    "/%2e//evil.test",
    "/%09/evil.test",
    "/%0A/evil.test",
    "/%0D/evil.test",
    "//evil.test",
    "https://evil.test/dashboard",
  ])("never redirects off this origin for next=%s", async (raw) => {
    signedIn({ id: "user-1" });

    const response = await proxy(request(`/login?next=${raw}`));
    const location = response.headers.get("location");

    expect(location).not.toBeNull();
    expect(new URL(location as string).origin).toBe(APP_ORIGIN);
  });

  it.each(["//", "/%5C", "/.//", "/%09//"])(
    "answers with a redirect, never an exception, for next=%s",
    async (raw) => {
      // These make `new URL()` throw. Unhandled in the proxy that is a 500 on
      // the login of everyone already signed in.
      signedIn({ id: "user-1" });

      const response = await proxy(request(`/login?next=${raw}`));
      const location = response.headers.get("location");

      expect(response.status).toBe(307);
      expect(new URL(location as string).origin).toBe(APP_ORIGIN);
    },
  );

  it("answers a chain of logins with a single redirect", async () => {
    signedIn({ id: "user-1" });

    let chain = "/dashboard?ev=4821";
    for (let hop = 0; hop < 25; hop += 1) {
      chain = `/login?next=${encodeURIComponent(chain)}`;
    }

    const response = await proxy(
      request(`/login?next=${encodeURIComponent(chain)}`),
    );

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(`${APP_ORIGIN}/dashboard`);
  });

  it("lets the anonymous visitor reach the invitation landing", async () => {
    // The link in the e-mail opens the session in the browser, from a URL
    // fragment this server never sees: there is no session yet to require.
    signedIn(null);

    const response = await proxy(request("/convite"));

    expect(response.headers.get("location")).toBeNull();
  });

  it("does not bounce a signed-in user away from the invitation landing", async () => {
    // The link may belong to another account than the one already signed in
    // on this browser; the page decides, not the proxy.
    signedIn({ id: "user-1" });

    const response = await proxy(request("/convite?code=abc"));

    expect(response.headers.get("location")).toBeNull();
  });

  it("does not open anything below the invitation landing", async () => {
    signedIn(null);

    const response = await proxy(request("/convite/outra"));

    expect(response.status).toBe(307);
  });

  it("leaves the signed-in user alone on a protected route", async () => {
    signedIn({ id: "user-1" });

    const response = await proxy(request("/dashboard"));

    expect(response.headers.get("location")).toBeNull();
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });
});
