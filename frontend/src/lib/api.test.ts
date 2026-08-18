import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, requestApi } from "@/lib/api";

function jsonResponse(body: unknown, status: number) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("requestApi", () => {
  it("sends the Supabase access token to FastAPI", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ ok: true }, 200));

    const body = await requestApi<{ ok: boolean }>("/health", {
      accessToken: "token-123",
    });

    expect(body).toEqual({ ok: true });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.stub.test/health");
    expect((init?.headers as Record<string, string>).Authorization).toBe(
      "Bearer token-123",
    );
    // The tenant is never sent by the client: the token carries it.
    expect(JSON.stringify(init)).not.toContain("tenant_id");
  });

  it("turns a refusal into an ApiError carrying the detail", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "Fora do seu escopo." }, 403),
    );

    const failure = await requestApi("/employees/1", {
      accessToken: "token-123",
    }).catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(403);
    expect((failure as ApiError).detail).toBe("Fora do seu escopo.");
  });

  it("survives an error answer that is not JSON", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("gateway timeout", { status: 504 }),
    );

    const failure = await requestApi("/health", {
      accessToken: "token-123",
    }).catch((error: unknown) => error);

    expect((failure as ApiError).status).toBe(504);
    expect((failure as ApiError).detail).toBeNull();
  });
});
