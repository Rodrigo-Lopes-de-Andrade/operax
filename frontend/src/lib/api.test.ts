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

  it("carries the `code` and the body of a named refusal beside the detail", async () => {
    // The 409 of `POST /canais/destinatarios/contatos/{id}/desativar`: the
    // screen branches on `code` and lists `rules` — neither fits in `detail`.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(
        {
          detail: "Este contato é destino de regra ligada.",
          code: "contact_in_active_rule",
          rules: [{ id: "r-1", name: "Regra Zz" }],
        },
        409,
      ),
    );

    const failure = (await requestApi("/canais/x", {
      accessToken: "token-123",
    }).catch((error: unknown) => error)) as ApiError;

    expect(failure.status).toBe(409);
    expect(failure.detail).toBe("Este contato é destino de regra ligada.");
    expect(failure.code).toBe("contact_in_active_rule");
    expect(failure.payload).toEqual({
      detail: "Este contato é destino de regra ligada.",
      code: "contact_in_active_rule",
      rules: [{ id: "r-1", name: "Regra Zz" }],
    });
  });

  it("an answer without `code` leaves it null — and a non-string one too", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "Fora do seu escopo.", code: 42 }, 403),
    );

    const failure = (await requestApi("/employees/1", {
      accessToken: "token-123",
    }).catch((error: unknown) => error)) as ApiError;

    expect(failure.detail).toBe("Fora do seu escopo.");
    expect(failure.code).toBeNull();
  });

  it("leaves a non-string `detail` null — the 422 of FastAPI is a list", async () => {
    // A validação do FastAPI devolve `detail` como lista de erros. Despejá-la
    // na tela seria JSON cru onde deveria haver uma frase — e o `payload`
    // continua lá para quem souber lê-la.
    const detail = [{ loc: ["body", "name"], msg: "field required" }];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail }, 422),
    );

    const failure = (await requestApi("/canais/regras", {
      accessToken: "token-123",
      method: "POST",
      body: {},
    }).catch((error: unknown) => error)) as ApiError;

    expect(failure.status).toBe(422);
    expect(failure.detail).toBeNull();
    expect(failure.code).toBeNull();
    expect(failure.payload).toEqual({ detail });
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
    expect((failure as ApiError).code).toBeNull();
    expect((failure as ApiError).payload).toBeNull();
  });
});
