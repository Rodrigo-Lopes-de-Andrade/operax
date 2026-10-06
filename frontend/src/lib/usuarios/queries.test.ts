import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadUserDetailScreen } from "@/lib/usuarios/queries";

vi.mock("server-only", () => ({}));

type Session = { access_token: string } | null;

const getSession = vi.fn(async (): Promise<{ data: { session: Session } }> => ({
  data: { session: { access_token: "token-de-teste" } },
}));

vi.mock("@/lib/supabase-server", () => ({
  getServerSupabase: async () => ({ auth: { getSession: () => getSession() } }),
}));

vi.mock("@/lib/ponto/queries", () => ({ loadUnits: async () => [] }));

const fetchMock = vi.fn();

const ALVO = "a0000000-0000-4000-8000-000000000001";
const MATRIZ = { roles: [{ role: "viewer", domains: [] }] };

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Responde por caminho: a matriz e o membro correm em paralelo. */
function route(user: Response, matrix: Response) {
  fetchMock.mockImplementation(async (url: string) =>
    url.endsWith("/usuarios/matriz") ? matrix : user,
  );
}

beforeEach(() => {
  fetchMock.mockReset();
  getSession.mockClear();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("loadUserDetailScreen — Caminho 2", () => {
  it("lê o membro e a matriz no FastAPI com o Bearer da sessão", async () => {
    route(answer(200, { user_id: ALVO }), answer(200, MATRIZ));

    const result = await loadUserDetailScreen(ALVO);

    expect(result.detail).toEqual({ status: "ok", user: { user_id: ALVO } });
    expect(result.matrix).toEqual(MATRIZ);
    const urls = fetchMock.mock.calls.map(([url]) => url as string);
    expect(urls).toContain(`http://api.stub.test/usuarios/${ALVO}`);
    expect(urls).toContain("http://api.stub.test/usuarios/matriz");
    for (const [, init] of fetchMock.mock.calls) {
      expect((init as RequestInit).headers).toMatchObject({
        Authorization: "Bearer token-de-teste",
      });
    }
  });

  it.each([
    [404, "not_found"],
    [403, "forbidden"],
    [500, "unavailable"],
    [401, "unavailable"],
  ])("membro %i → %s", async (status, expected) => {
    route(answer(status, { detail: "x" }), answer(200, MATRIZ));

    expect((await loadUserDetailScreen(ALVO)).detail).toEqual({
      status: expected,
    });
  });

  it("⛔ a matriz que falhou é null, nunca uma matriz vazia", async () => {
    route(answer(200, { user_id: ALVO }), answer(500, { detail: "x" }));

    expect((await loadUserDetailScreen(ALVO)).matrix).toBeNull();
  });

  it("sem sessão, nada vai à API", async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } });

    const result = await loadUserDetailScreen(ALVO);

    expect(result.detail).toEqual({ status: "unavailable" });
    expect(result.matrix).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
