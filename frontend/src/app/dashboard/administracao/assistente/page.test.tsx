import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AssistenteConfigPage from "@/app/dashboard/administracao/assistente/page";
import type {
  CapabilityRow,
  PromptScreen,
  VersionsScreen,
} from "@/lib/assistente/config";
import type { Identity } from "@/lib/identity";
import type { RawSearchParams } from "@/lib/ponto/filters";

vi.mock("server-only", () => ({}));

const notFound = vi.fn(() => {
  throw new Error("NEXT_NOT_FOUND");
});

vi.mock("next/navigation", () => ({
  notFound: () => notFound(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const loadIdentity = vi.fn();
const loadPromptScreen = vi.fn();
const loadVersions = vi.fn();
const loadCapabilities = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  // `isAdmin` fica o real: é a porta sob teste.
  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/assistente/queries", () => ({
  loadPromptScreen: () => loadPromptScreen(),
  loadVersions: () => loadVersions(),
  loadCapabilities: () => loadCapabilities(),
}));

function identidade(role: string): Identity {
  return {
    user_id: "11111111-1111-4111-8111-111111111111",
    email: `${role}@fastpark.dev`,
    tenant_id: "22222222-2222-4222-8222-222222222222",
    role,
  };
}

const V3_ID = "33333333-3333-4333-8333-333333333333";
const PLATFORM_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

const PROMPT: PromptScreen = {
  platform: {
    version_id: PLATFORM_ID,
    version_number: 1,
    content: "Doutrina zz.",
    provider: "openai",
    model: "gpt-zz",
    max_steps: 4,
    created_at: "2026-09-01T12:00:00Z",
  },
  tenant: {
    version_id: V3_ID,
    version_number: 3,
    content: "Texto zz no ar.",
    created_at: "2026-09-10T12:00:00Z",
    created_by: null,
  },
  draft: null,
  max_length: 12000,
  draft_ahead_of_air: false,
};

const VERSIONS: VersionsScreen = {
  tenant: [
    {
      version_id: V3_ID,
      version_number: 3,
      content: "Texto zz no ar.",
      created_at: "2026-09-10T12:00:00Z",
      created_by: null,
      on_air: true,
    },
  ],
  platform: [
    {
      version_id: PLATFORM_ID,
      version_number: 1,
      content: "Doutrina zz.",
      created_at: "2026-09-01T12:00:00Z",
      created_by: null,
      on_air: true,
    },
  ],
};

const CAPABILITIES: CapabilityRow[] = [
  {
    code: "zz_metrica_um",
    title: "Desvios por unidade",
    description: "Quantos indícios cada unidade acumulou no período.",
    domain: null,
    enabled: true,
    visible_to_me: true,
  },
];

async function abrir(role: string, params: RawSearchParams = {}) {
  loadIdentity.mockResolvedValue(identidade(role));
  loadPromptScreen.mockResolvedValue(PROMPT);
  loadVersions.mockResolvedValue(VERSIONS);
  loadCapabilities.mockResolvedValue(CAPABILITIES);

  return render(
    await AssistenteConfigPage({ searchParams: Promise.resolve(params) }),
  );
}

function abas() {
  return within(
    screen.getByRole("navigation", { name: "Configuração do assistente" }),
  );
}

beforeEach(() => {
  notFound.mockClear();
  loadIdentity.mockReset();
  loadPromptScreen.mockReset();
  loadVersions.mockReset();
  loadCapabilities.mockReset();
});

describe("a porta é `isAdmin`, como em Conexões", () => {
  it("⛔ `unit_supervisor` recebe 404, e nenhuma leitura acontece", async () => {
    loadIdentity.mockResolvedValue(identidade("unit_supervisor"));

    await expect(
      AssistenteConfigPage({ searchParams: Promise.resolve({}) }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalled();
    expect(loadPromptScreen).not.toHaveBeenCalled();
    expect(loadVersions).not.toHaveBeenCalled();
    expect(loadCapabilities).not.toHaveBeenCalled();
  });

  it("⛔ `executive` também: ele lê a área de RH e não configura o assistente", async () => {
    // Está em `HR_ROLES` e não em `ADMIN_ROLES`. Sem este caso, trocar
    // `isAdmin` por `reachesHr` passaria verde.
    loadIdentity.mockResolvedValue(identidade("executive"));

    await expect(
      AssistenteConfigPage({ searchParams: Promise.resolve({}) }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadPromptScreen).not.toHaveBeenCalled();
  });

  it("sem vínculo com o tenant não há tela", async () => {
    loadIdentity.mockResolvedValue(null);

    await expect(
      AssistenteConfigPage({ searchParams: Promise.resolve({}) }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadPromptScreen).not.toHaveBeenCalled();
  });

  it("✅ `owner` entra, e o título carrega o parêntese que o separa da conversa", async () => {
    await abrir("owner");

    expect(notFound).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Assistente (configuração)",
      }),
    ).toBeVisible();
  });

  it("✅ `personnel` também é admin e entra", async () => {
    await abrir("personnel");

    expect(notFound).not.toHaveBeenCalled();
    expect(abas().getAllByRole("link")).toHaveLength(4);
  });
});

describe("a aba mora na query string", () => {
  it("sem `aba=`, abre em Configuração — e ela é a marcada", async () => {
    await abrir("owner");

    expect(abas().getByRole("link", { name: "Configuração" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByText("Camada da plataforma — v1")).toBeVisible();
    expect(loadCapabilities).not.toHaveBeenCalled();
  });

  it("⛔ `?aba=historico` abre o Histórico, e lê as versões — não o catálogo", async () => {
    await abrir("owner", { aba: "historico" });

    expect(abas().getByRole("link", { name: "Histórico" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.getByRole("list", { name: "Versões do cliente" }),
    ).toBeVisible();
    expect(loadVersions).toHaveBeenCalledTimes(1);
    expect(loadCapabilities).not.toHaveBeenCalled();
  });

  it("⛔ `?aba=teste` abre o Teste, com a frase de dados reais", async () => {
    await abrir("owner", { aba: "teste" });

    expect(abas().getByRole("link", { name: "Teste" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.getByText("O teste consulta dados reais, com as suas permissões."),
    ).toBeVisible();
  });

  it("⛔ `?aba=capacidades` abre as Capacidades, com a linha da §4.1", async () => {
    await abrir("owner", { aba: "capacidades" });

    expect(abas().getByRole("link", { name: "Capacidades" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.getByText(
        "Desligar tira a métrica do assistente para todo mundo. Ligar não dá acesso a dado que o papel não alcança.",
      ),
    ).toBeVisible();
    expect(loadCapabilities).toHaveBeenCalledTimes(1);
    expect(loadPromptScreen).not.toHaveBeenCalled();
  });

  it("uma aba que não existe cai na primeira, sem erro", async () => {
    await abrir("owner", { aba: "zz-inventada" });

    expect(abas().getByRole("link", { name: "Configuração" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("⛔ o link de cada aba leva à própria aba — é assim que o link do relatório abre no lugar certo", async () => {
    await abrir("owner");

    expect(abas().getByRole("link", { name: "Histórico" })).toHaveAttribute(
      "href",
      "/dashboard/administracao/assistente?aba=historico",
    );
    // A aba padrão não carrega parâmetro: a URL limpa é a Configuração.
    expect(abas().getByRole("link", { name: "Configuração" })).toHaveAttribute(
      "href",
      "/dashboard/administracao/assistente",
    );
  });

  it("⛔ `?versao=` abre aquela versão dentro do Histórico", async () => {
    await abrir("owner", { aba: "historico", versao: V3_ID });

    expect(screen.getByLabelText("Texto da v3")).toBeVisible();
  });

  it("um `versao=` que não é uuid não abre nada, e não quebra a aba", async () => {
    await abrir("owner", { aba: "historico", versao: "'; drop table --" });

    expect(
      screen.getByRole("list", { name: "Versões do cliente" }),
    ).toBeVisible();
    expect(screen.queryByLabelText("Texto da v3")).toBeNull();
  });
});

describe("o estado em que a API não respondeu", () => {
  it("⛔ prompt nulo (503 sem camada de plataforma, 401, 403) é frase, não tela branca", async () => {
    loadIdentity.mockResolvedValue(identidade("owner"));
    loadPromptScreen.mockResolvedValue(null);
    loadVersions.mockResolvedValue(VERSIONS);

    render(await AssistenteConfigPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByText("A configuração não pôde ser lida")).toBeVisible();
    // A navegação por abas continua: a pessoa não fica presa.
    expect(abas().getAllByRole("link")).toHaveLength(4);
  });

  it("catálogo nulo na aba Capacidades também vira frase", async () => {
    loadIdentity.mockResolvedValue(identidade("owner"));
    loadCapabilities.mockResolvedValue(null);

    render(
      await AssistenteConfigPage({
        searchParams: Promise.resolve({ aba: "capacidades" }),
      }),
    );

    expect(screen.getByText("O catálogo não pôde ser lido")).toBeVisible();
  });

  it("⛔ na aba Teste, prompt nulo não impede testar a versão no ar — só desabilita o rascunho", async () => {
    loadIdentity.mockResolvedValue(identidade("owner"));
    loadPromptScreen.mockResolvedValue(null);

    render(
      await AssistenteConfigPage({
        searchParams: Promise.resolve({ aba: "teste" }),
      }),
    );

    expect(
      screen.getByRole("checkbox", {
        name: "Usar o rascunho em vez da versão no ar",
      }),
    ).toBeDisabled();
    // E a tela não afirma o que não sabe: a leitura falhou, não há fato.
    expect(
      screen.getByText(
        "Não foi possível saber se há rascunho: o teste usa a versão no ar.",
      ),
    ).toBeVisible();
  });
});
