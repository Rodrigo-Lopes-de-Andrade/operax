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

  it("leaves the signed-in user alone on a protected route", async () => {
    signedIn({ id: "user-1" });

    const response = await proxy(request("/dashboard"));

    expect(response.headers.get("location")).toBeNull();
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });
});
