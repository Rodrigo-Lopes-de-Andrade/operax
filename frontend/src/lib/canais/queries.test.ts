import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { loadConnections, type ConnectionsScreen } from "@/lib/canais/queries";

// `server-only` existe para explodir num bundle de cliente; aqui o módulo é
// exercitado fora do Next, e o stub é o que permite testar a leitura em si.
vi.mock("server-only", () => ({}));

type Session = { access_token: string } | null;

const getSession = vi.fn(async (): Promise<{ data: { session: Session } }> => ({
  data: { session: { access_token: "token-de-teste" } },
}));

vi.mock("@/lib/supabase-server", () => ({
  getServerSupabase: async () => ({ auth: { getSession: () => getSession() } }),
}));

const fetchMock = vi.fn();

const PAYLOAD: ConnectionsScreen = {
  provider: "meta_cloud",
  capabilities: { official: true, requires_templates: true, ban_risk: false },
  templates_total: 2,
  templates_approved: 1,
  rules_blocked: 1,
  ready: false,
  blocked: [
    {
      rule_name: "Desvio individual",
      template_code: "deviation_individual",
      meta_status: "pending",
    },
  ],
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

describe("a tela de Conexões — caminho 2", () => {
  it("200 devolve a resposta como veio, com o token no header e sem tenant na URL", async () => {
    fetchMock.mockResolvedValue(answer(200, PAYLOAD));

    const screen = await loadConnections();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/canais\/conexoes$/);
    // ⛔ O tenant sai do token, e o cliente não o manda em lugar nenhum.
    expect(url).not.toMatch(/tenant/i);
    expect(init.headers.Authorization).toBe("Bearer token-de-teste");
    expect(screen).toEqual(PAYLOAD);
  });

  it("401 é a sessão que venceu, e vira null", async () => {
    fetchMock.mockResolvedValue(answer(401, { detail: "…" }));

    expect(await loadConnections()).toBeNull();
  });

  it("403 é ausência de acesso, e vira null", async () => {
    fetchMock.mockResolvedValue(
      answer(403, { detail: "Sem vínculo ativo com este cliente." }),
    );

    expect(await loadConnections()).toBeNull();
  });

  it("⛔ 500 relança — a API fora do ar não é 'sem canal'", async () => {
    // Engolir o 500 em null renderizaria "não pôde ser lido" onde o error
    // boundary é que deveria aparecer; e um dia alguém trocaria a frase por
    // "nenhum canal configurado" e a tela mentiria numa queda de rede.
    fetchMock.mockResolvedValue(answer(500, { detail: "boom" }));

    await expect(loadConnections()).rejects.toBeInstanceOf(ApiError);
    await expect(loadConnections()).rejects.toMatchObject({ status: 500 });
  });

  it("sem sessão não chega a chamar a API", async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } });

    expect(await loadConnections()).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
