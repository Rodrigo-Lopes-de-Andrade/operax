import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import {
  loadConnections,
  loadCredential,
  loadProviderForms,
  loadTemplates,
  type ConnectionsScreen,
  type CredentialStatus,
  type ProviderForm,
  type TemplateRow,
} from "@/lib/canais/queries";

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

const CREDENTIAL: CredentialStatus = {
  configured: true,
  provider: "meta_cloud",
  updated_at: "2026-09-14T13:05:00Z",
  public_identity: "+55 11 99999-0000",
};

const FORMS: ProviderForm[] = [
  {
    provider: "meta_cloud",
    capabilities: { official: true, requires_templates: true, ban_risk: false },
    fields: [
      {
        name: "phone_number_id",
        label: "ID do número de telefone",
        pattern: "[0-9]{5,32}",
        autocomplete: "off",
        inputmode: "numeric",
        secret: false,
        placeholder: "123456789012345",
        hint: "isto não parece um ID de número: a Meta usa só dígitos",
      },
    ],
  },
];

describe("a credencial — o estado, nunca o valor (caminho 2)", () => {
  it("200 devolve o estado como veio, com o token no header e sem tenant na URL", async () => {
    fetchMock.mockResolvedValue(answer(200, CREDENTIAL));

    const status = await loadCredential();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/canais\/credencial$/);
    expect(url).not.toMatch(/tenant/i);
    expect(init.headers.Authorization).toBe("Bearer token-de-teste");
    expect(status).toEqual(CREDENTIAL);
  });

  it("401 vira null", async () => {
    fetchMock.mockResolvedValue(answer(401, { detail: "…" }));

    expect(await loadCredential()).toBeNull();
  });

  it("403 vira null", async () => {
    fetchMock.mockResolvedValue(
      answer(403, { detail: "Sem vínculo ativo com este cliente." }),
    );

    expect(await loadCredential()).toBeNull();
  });

  it("⛔ 500 relança — a API fora do ar não é 'sem credencial'", async () => {
    fetchMock.mockResolvedValue(answer(500, { detail: "boom" }));

    await expect(loadCredential()).rejects.toMatchObject({ status: 500 });
  });
});

describe("os formulários dos provedores (caminho 2)", () => {
  it("200 devolve a lista na ordem da API, com o token no header e sem tenant na URL", async () => {
    fetchMock.mockResolvedValue(answer(200, FORMS));

    const forms = await loadProviderForms();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/canais\/provedores$/);
    expect(url).not.toMatch(/tenant/i);
    expect(init.headers.Authorization).toBe("Bearer token-de-teste");
    expect(forms).toEqual(FORMS);
  });

  it("401 vira null", async () => {
    fetchMock.mockResolvedValue(answer(401, { detail: "…" }));

    expect(await loadProviderForms()).toBeNull();
  });

  it("403 vira null", async () => {
    fetchMock.mockResolvedValue(
      answer(403, { detail: "Sem vínculo ativo com este cliente." }),
    );

    expect(await loadProviderForms()).toBeNull();
  });

  it("⛔ 500 relança", async () => {
    fetchMock.mockResolvedValue(answer(500, { detail: "boom" }));

    await expect(loadProviderForms()).rejects.toBeInstanceOf(ApiError);
  });

  it("sem sessão nenhuma das duas chega a chamar a API", async () => {
    getSession
      .mockResolvedValueOnce({ data: { session: null } })
      .mockResolvedValueOnce({ data: { session: null } });

    expect(await loadCredential()).toBeNull();
    expect(await loadProviderForms()).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

/** Códigos que nenhum template real tem: a leitura devolve o que a API mandou. */
const TEMPLATES: TemplateRow[] = [
  {
    code: "zz_teste_alfa",
    category: "utility",
    language: "pt_BR",
    variables: ["data_observada", "horario"],
    body: "Em {{1}} às {{2}}.",
    meta_template_name: null,
    meta_status: "draft",
    meta_rejection: null,
    active: true,
    updated_at: "2026-09-15T13:05:00Z",
  },
  {
    code: "zz_teste_beta",
    category: "marketing",
    language: "en_US",
    variables: ["unit"],
    body: "{{1}}",
    meta_template_name: "zz_teste_beta_v1",
    meta_status: "rejected",
    meta_rejection: "INVALID_FORMAT",
    active: false,
    updated_at: "2026-09-14T09:00:00Z",
  },
];

describe("o catálogo de templates (caminho 2)", () => {
  it("200 devolve a lista como veio, com o token no header e sem tenant na URL", async () => {
    fetchMock.mockResolvedValue(answer(200, TEMPLATES));

    const templates = await loadTemplates();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/canais\/templates$/);
    expect(url).not.toMatch(/tenant/i);
    expect(init.headers.Authorization).toBe("Bearer token-de-teste");
    expect(init.method).toBe("GET");
    expect(templates).toEqual(TEMPLATES);
  });

  it("401 vira null", async () => {
    fetchMock.mockResolvedValue(answer(401, { detail: "…" }));

    expect(await loadTemplates()).toBeNull();
  });

  it("403 vira null", async () => {
    fetchMock.mockResolvedValue(
      answer(403, { detail: "Sem vínculo ativo com este cliente." }),
    );

    expect(await loadTemplates()).toBeNull();
  });

  it("⛔ 500 relança — a API fora do ar não é 'nenhum template'", async () => {
    // Produção está vazia de verdade; engolir o 500 em null é o que deixaria
    // a queda da API indistinguível da tela do primeiro dia.
    fetchMock.mockResolvedValue(answer(500, { detail: "boom" }));

    await expect(loadTemplates()).rejects.toBeInstanceOf(ApiError);
    await expect(loadTemplates()).rejects.toMatchObject({ status: 500 });
  });

  it("sem sessão não chega a chamar a API", async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } });

    expect(await loadTemplates()).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
