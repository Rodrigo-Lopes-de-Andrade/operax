import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadExecutions } from "@/lib/assistente/queries";

// `server-only` existe para explodir num bundle de cliente; aqui o módulo é
// exercitado fora do Next, e o stub é o que permite testar a leitura em si.
vi.mock("server-only", () => ({}));

type Session = { access_token: string } | null;

const getSession = vi.fn(async (): Promise<{ data: { session: Session } }> => ({
  data: { session: { access_token: "token-de-teste" } },
}));

vi.mock("@/lib/supabase-server", () => ({
  getServerSupabase: async () => ({
    auth: { getSession: () => getSession() },
  }),
}));

const fetchMock = vi.fn();

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  getSession.mockReset();
  getSession.mockResolvedValue({
    data: { session: { access_token: "token-de-teste" } },
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a aba Execuções lê as três na mesma janela", () => {
  it("as três chamadas levam a MESMA semana, e o token no header", async () => {
    // Uma `Response` só não serve para três leituras: o corpo se esgota.
    fetchMock.mockImplementation(() => Promise.resolve(answer(200, [])));

    const result = await loadExecutions(12);

    expect(result).toEqual({
      status: "ok",
      screen: { runs: [], cost: [], testCost: [] },
    });

    const urls = fetchMock.mock.calls.map(([url]) => url as string);
    expect(urls).toHaveLength(3);
    expect(urls.some((url) => url.includes("/execucoes?weeks=12"))).toBe(true);
    expect(urls.some((url) => url.includes("/custo?weeks=12"))).toBe(true);
    // ⛔ Janelas diferentes entre a tabela e o total seriam dois períodos na
    // mesma tela, e ninguém veria a diferença.
    expect(urls.some((url) => url.includes("/custo-de-teste?weeks=12"))).toBe(
      true,
    );
    expect(urls.every((url) => url.includes("weeks=12"))).toBe(true);
    // O tenant sai do token, e o cliente não o manda em lugar nenhum.
    expect(urls.every((url) => !/tenant/i.test(url))).toBe(true);
    for (const [, init] of fetchMock.mock.calls) {
      expect(init.headers.Authorization).toBe("Bearer token-de-teste");
    }
  });

  it("lista vazia é `ok`, não ausência de permissão", async () => {
    // A RLS de `app.ai_query` é própria-ou-admin: uma lista curta é o recorte
    // funcionando, e a aba não pode apresentá-la como falta de acesso.
    fetchMock.mockImplementation(() => Promise.resolve(answer(200, [])));

    expect((await loadExecutions(8)).status).toBe("ok");
  });

  it("⛔ 422 é a janela fora de 1..52 — estado, não exceção", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        answer(422, {
          detail: [{ msg: "Input should be less than or equal" }],
        }),
      ),
    );

    expect(await loadExecutions(99)).toEqual({ status: "out_of_range" });
  });

  it("401 e 403 viram o mesmo estado vazio", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(answer(401, { detail: "…" })),
    );
    expect(await loadExecutions(8)).toEqual({ status: "unavailable" });

    fetchMock.mockImplementation(() =>
      Promise.resolve(answer(403, { detail: "…" })),
    );
    expect(await loadExecutions(8)).toEqual({ status: "unavailable" });
  });

  it("sem sessão não há leitura nenhuma", async () => {
    getSession.mockResolvedValue({ data: { session: null } });

    expect(await loadExecutions(8)).toEqual({ status: "unavailable" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("⛔ 500 relança: é o error boundary que o mostra, não uma janela vazia falsa", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(answer(500, { detail: "boom" })),
    );

    await expect(loadExecutions(8)).rejects.toThrow();
  });
});
