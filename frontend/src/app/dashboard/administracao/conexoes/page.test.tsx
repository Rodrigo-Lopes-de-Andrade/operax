import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ConexoesPage from "@/app/dashboard/administracao/conexoes/page";
import type { ConnectionsScreen } from "@/lib/canais/queries";
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
const loadConnections = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  // `isAdmin` fica o real: é a porta sob teste.
  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/canais/queries", () => ({
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

/** O estado da produção no primeiro dia: nenhum canal. */
const SEM_CANAL: ConnectionsScreen = {
  provider: null,
  capabilities: null,
  templates_total: 0,
  templates_approved: 0,
  rules_blocked: 0,
  ready: false,
  blocked: [],
};

const BLOQUEADO: ConnectionsScreen = {
  provider: "meta_cloud",
  capabilities: { official: true, requires_templates: true, ban_risk: false },
  templates_total: 1,
  templates_approved: 0,
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

async function abrir(role: string, screen: ConnectionsScreen | null) {
  loadIdentity.mockResolvedValue(identidade(role));
  loadConnections.mockResolvedValue(screen);

  return render(await ConexoesPage());
}

beforeEach(() => {
  notFound.mockClear();
  loadIdentity.mockReset();
  loadConnections.mockReset();
});

describe("a porta da página é `isAdmin`, mais estreita que a rota de propósito", () => {
  it("⛔ `unit_supervisor` recebe 404, e a API nem é chamada", async () => {
    loadIdentity.mockResolvedValue(identidade("unit_supervisor"));

    await expect(ConexoesPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalled();
    expect(loadConnections).not.toHaveBeenCalled();
  });

  it("⛔ `executive` também recebe 404 — lê a área de RH e não configura canal", async () => {
    // Ele está em `HR_ROLES` e não em `ADMIN_ROLES`. Sem este caso, trocar
    // `isAdmin` por `reachesHr` passaria verde: o supervisor continuaria fora.
    loadIdentity.mockResolvedValue(identidade("executive"));

    await expect(ConexoesPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadConnections).not.toHaveBeenCalled();
  });

  it("sem vínculo com o tenant não há tela", async () => {
    loadIdentity.mockResolvedValue(null);

    await expect(ConexoesPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadConnections).not.toHaveBeenCalled();
  });

  it("✅ `owner` entra e vê o que está preso", async () => {
    await abrir("owner", BLOQUEADO);

    expect(notFound).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Conexões" })).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "O que está preso" }),
    ).toBeVisible();
    expect(screen.getByText("deviation_individual")).toBeVisible();
  });

  it("✅ `owner` sem canal vê o estado vazio — a tela do primeiro dia", async () => {
    await abrir("owner", SEM_CANAL);

    expect(notFound).not.toHaveBeenCalled();
    expect(
      screen.getByText("Nenhum canal de WhatsApp configurado"),
    ).toBeVisible();
    expect(screen.queryByText("As conexões não puderam ser lidas")).toBeNull();
  });

  it("null (sessão, 401, 403) é 'não pôde ser lido' — outra frase, e não 'sem canal'", async () => {
    await abrir("owner", null);

    expect(notFound).not.toHaveBeenCalled();
    expect(screen.getByText("As conexões não puderam ser lidas")).toBeVisible();
    expect(
      screen.queryByText("Nenhum canal de WhatsApp configurado"),
    ).toBeNull();
  });
});
