import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadApprovalScreen, loadPostingScreen } from "@/lib/alcada/queries";
import type { ApprovalFilters } from "@/lib/alcada/url";

vi.mock("server-only", () => ({}));

type Session = { access_token: string } | null;

const getSession = vi.fn(async (): Promise<{ data: { session: Session } }> => ({
  data: { session: { access_token: "token-de-teste" } },
}));

vi.mock("@/lib/supabase-server", () => ({
  getServerSupabase: async () => ({ auth: { getSession: () => getSession() } }),
}));

// As unidades são Caminho 1 e têm teste próprio; aqui o que importa é a fila.
vi.mock("@/lib/ponto/queries", () => ({ loadUnits: async () => [] }));

const fetchMock = vi.fn();

const FILTERS: ApprovalFilters = {
  year: 2026,
  month: 10,
  unitId: "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
  employeeId: null,
  from: "2026-09-22",
  to: null,
};

const RESPOSTA = {
  ano: 2026,
  mes: 10,
  period_start: "2026-09-16",
  period_end: "2026-10-15",
  rows: [],
};

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  getSession.mockClear();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("loadApprovalScreen — Caminho 2", () => {
  it("pede a fila ao FastAPI com o Bearer da sessão e o recorte da URL", async () => {
    fetchMock.mockResolvedValue(answer(200, RESPOSTA));

    const screen = await loadApprovalScreen(FILTERS);

    expect(screen.queue).toEqual({ status: "ok", queue: RESPOSTA });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      "http://api.stub.test/alcada/fila?ano=2026&mes=10&unidade=3f2504e0-4f89-41d3-9a0c-0305e82c3301&de=2026-09-22",
    );
    expect(init.headers.Authorization).toBe("Bearer token-de-teste");
  });

  it("sem competência na URL, não manda ano nem mês — quem escolhe é o banco", async () => {
    fetchMock.mockResolvedValue(answer(200, RESPOSTA));

    await loadApprovalScreen({
      ...FILTERS,
      year: null,
      month: null,
      unitId: null,
      from: null,
    });

    expect(fetchMock.mock.calls[0][0]).toBe("http://api.stub.test/alcada/fila");
  });

  it("⛔ 422 é recorte inválido, e não 'API fora do ar'", async () => {
    fetchMock.mockResolvedValue(answer(422, { detail: [] }));

    expect((await loadApprovalScreen(FILTERS)).queue).toEqual({
      status: "invalid",
    });
  });

  it("⛔ 403 `not_hr` vira 'sem acesso', e não fila vazia", async () => {
    fetchMock.mockResolvedValue(answer(403, { detail: "not_hr" }));

    expect((await loadApprovalScreen(FILTERS)).queue).toEqual({
      status: "forbidden",
    });
  });

  it("500 e sessão ausente viram 'não pôde ser lida'", async () => {
    fetchMock.mockResolvedValue(answer(500, { detail: "boom" }));
    expect((await loadApprovalScreen(FILTERS)).queue).toEqual({
      status: "unavailable",
    });

    getSession.mockResolvedValueOnce({ data: { session: null } });
    fetchMock.mockClear();
    expect((await loadApprovalScreen(FILTERS)).queue).toEqual({
      status: "unavailable",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("loadPostingScreen — Caminho 2", () => {
  it("pede a lista do lançamento ao FastAPI, com o Bearer e o mesmo recorte", async () => {
    fetchMock.mockResolvedValue(answer(200, RESPOSTA));

    const screen = await loadPostingScreen(FILTERS);

    expect(screen.list).toEqual({ status: "ok", queue: RESPOSTA });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      "http://api.stub.test/alcada/lancamento?ano=2026&mes=10&unidade=3f2504e0-4f89-41d3-9a0c-0305e82c3301&de=2026-09-22",
    );
    expect(init.headers.Authorization).toBe("Bearer token-de-teste");
  });

  it("sem competência na URL, a rota vai sem query", async () => {
    fetchMock.mockResolvedValue(answer(200, RESPOSTA));

    await loadPostingScreen({
      ...FILTERS,
      year: null,
      month: null,
      unitId: null,
      from: null,
    });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://api.stub.test/alcada/lancamento",
    );
  });

  it.each([
    [403, { detail: "not_hr" }, "forbidden"],
    [422, { detail: [] }, "invalid"],
    [500, { detail: "boom" }, "unavailable"],
  ])("%i vira %s, e nunca lista vazia", async (status, body, expected) => {
    fetchMock.mockResolvedValue(answer(status, body));

    expect((await loadPostingScreen(FILTERS)).list).toEqual({
      status: expected,
    });
  });
});
