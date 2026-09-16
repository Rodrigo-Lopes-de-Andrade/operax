import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TemplatesPage from "@/app/dashboard/administracao/templates/page";
import type { ConnectionsScreen, TemplateRow } from "@/lib/canais/queries";
import type { Identity } from "@/lib/identity";

vi.mock("server-only", () => ({}));

const notFound = vi.fn(() => {
  throw new Error("NEXT_NOT_FOUND");
});

vi.mock("next/navigation", () => ({
  notFound: () => notFound(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const loadIdentity = vi.fn();
const loadTemplates = vi.fn();
const loadConnections = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  // `isAdmin` fica o real: é a porta sob teste.
  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/canais/queries", () => ({
  loadTemplates: () => loadTemplates(),
  loadConnections: () => loadConnections(),
}));

function identidade(role: string): Identity {
  return {
    user_id: "11111111-1111-4111-8111-111111111111",
    email: `${role}@fastpark.dev`,
    tenant_id: "22222222-2222-4222-8222-222222222222",
    role,
  };
}

/** Um código que nenhum template real tem: a linha só existe se vier da API. */
const TEMPLATE: TemplateRow = {
  code: "zz_teste_pagina",
  category: "utility",
  language: "pt_BR",
  variables: ["data_observada"],
  body: "Em {{1}}.",
  meta_template_name: null,
  meta_status: "draft",
  meta_rejection: null,
  active: true,
  updated_at: "2026-09-15T13:05:00Z",
};

const OFICIAL: ConnectionsScreen = {
  whatsapp: {
    provider: "meta_cloud",
    capabilities: {
      official: true,
      requires_templates: true,
      ban_risk: false,
      requires_recipient_opt_in: false,
    },
    templates_total: 1,
    templates_approved: 0,
    rules_blocked: 0,
    ready: false,
    blocked: [],
  },
  telegram: null,
};

async function abrir(
  role: string,
  templates: TemplateRow[] | null,
  connections: ConnectionsScreen | null = OFICIAL,
) {
  loadIdentity.mockResolvedValue(identidade(role));
  loadTemplates.mockResolvedValue(templates);
  loadConnections.mockResolvedValue(connections);

  return render(await TemplatesPage());
}

function sincronizar() {
  return screen.queryByRole("button", { name: "Sincronizar com a Meta" });
}

/** As linhas do catálogo — e não os itens da ajuda `{{n}}` do formulário. */
function linhas() {
  const lista = screen.queryByRole("list", { name: "Templates do cliente" });

  return lista ? within(lista).getAllByRole("listitem") : [];
}

beforeEach(() => {
  notFound.mockClear();
  loadIdentity.mockReset();
  loadTemplates.mockReset();
  loadConnections.mockReset();
});

describe("a porta da página é `isAdmin`, como a de Conexões", () => {
  it("⛔ `unit_supervisor` recebe 404, e a API nem é chamada", async () => {
    loadIdentity.mockResolvedValue(identidade("unit_supervisor"));

    await expect(TemplatesPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalled();
    expect(loadTemplates).not.toHaveBeenCalled();
    expect(loadConnections).not.toHaveBeenCalled();
  });

  it("⛔ `executive` também recebe 404 — lê a área de RH e não edita template", async () => {
    // Está em `HR_ROLES` e não em `ADMIN_ROLES`: trocar `isAdmin` por
    // `reachesHr` passaria no caso acima e cai aqui.
    loadIdentity.mockResolvedValue(identidade("executive"));

    await expect(TemplatesPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadTemplates).not.toHaveBeenCalled();
  });

  it("sem vínculo com o tenant não há tela", async () => {
    loadIdentity.mockResolvedValue(null);

    await expect(TemplatesPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadTemplates).not.toHaveBeenCalled();
  });

  it("✅ `owner` entra e vê a lista, o formulário e o botão de sincronizar", async () => {
    await abrir("owner", [TEMPLATE]);

    expect(notFound).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", { level: 1, name: "Templates" }),
    ).toBeVisible();
    expect(linhas()).toHaveLength(1);
    expect(screen.getByText("zz_teste_pagina")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Gravar template" }),
    ).toBeVisible();
    expect(sincronizar()).toBeVisible();
  });

  it("✅ `owner` sem template vê o estado vazio e o formulário aberto — a tela do primeiro dia", async () => {
    await abrir("owner", []);

    expect(screen.getByText("Nenhum template neste cliente")).toBeVisible();
    expect(linhas()).toHaveLength(0);
    expect(
      screen.getByRole("button", { name: "Gravar template" }),
    ).toBeVisible();
    expect(screen.queryByText("Os templates não puderam ser lidos")).toBeNull();
  });

  it("null no catálogo (sessão, 401, 403) é 'não pôde ser lido' — outra frase, e não 'nenhum template'", async () => {
    await abrir("owner", null, null);

    expect(notFound).not.toHaveBeenCalled();
    expect(
      screen.getByText("Os templates não puderam ser lidos"),
    ).toBeVisible();
    expect(screen.queryByText("Nenhum template neste cliente")).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Gravar template" }),
    ).toBeNull();
  });

  it("null só nas conexões não derruba a tela: a lista fica, e no lugar do botão vem a frase", async () => {
    await abrir("owner", [TEMPLATE], null);

    expect(screen.getByText("zz_teste_pagina")).toBeVisible();
    expect(sincronizar()).toBeNull();
    expect(
      screen.getByText(/só se sincroniza com a Cloud API da Meta/),
    ).toBeVisible();
  });
});
