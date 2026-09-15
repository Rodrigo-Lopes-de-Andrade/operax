import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ConexoesPage from "@/app/dashboard/administracao/conexoes/page";
import type {
  ConnectionsScreen,
  CredentialStatus,
  ProviderForm,
} from "@/lib/canais/queries";
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
const loadCredential = vi.fn();
const loadProviderForms = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  // `isAdmin` fica o real: é a porta sob teste.
  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/canais/queries", () => ({
  loadConnections: () => loadConnections(),
  loadCredential: () => loadCredential(),
  loadProviderForms: () => loadProviderForms(),
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

const NOT_CONFIGURED: CredentialStatus = {
  configured: false,
  provider: null,
  updated_at: null,
  public_identity: null,
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

async function abrir(
  role: string,
  screen: ConnectionsScreen | null,
  credential: CredentialStatus | null = NOT_CONFIGURED,
  forms: ProviderForm[] | null = FORMS,
) {
  loadIdentity.mockResolvedValue(identidade(role));
  loadConnections.mockResolvedValue(screen);
  loadCredential.mockResolvedValue(credential);
  loadProviderForms.mockResolvedValue(forms);

  return render(await ConexoesPage());
}

function formulario() {
  return screen.queryByRole("button", { name: "Validar e gravar" });
}

beforeEach(() => {
  notFound.mockClear();
  loadIdentity.mockReset();
  loadConnections.mockReset();
  loadCredential.mockReset();
  loadProviderForms.mockReset();
});

describe("a porta da página é `isAdmin`, mais estreita que a rota de propósito", () => {
  it("⛔ `unit_supervisor` recebe 404, e a API nem é chamada", async () => {
    loadIdentity.mockResolvedValue(identidade("unit_supervisor"));

    await expect(ConexoesPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalled();
    expect(loadConnections).not.toHaveBeenCalled();
    expect(loadCredential).not.toHaveBeenCalled();
    expect(loadProviderForms).not.toHaveBeenCalled();
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

  it("✅ `owner` entra e vê o que está preso — e o formulário de credencial", async () => {
    await abrir("owner", BLOQUEADO);

    expect(notFound).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Conexões" })).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "O que está preso" }),
    ).toBeVisible();
    expect(screen.getByText("deviation_individual")).toBeVisible();

    // O C2 é o que traz a escrita para esta tela: o formulário vem dirigido
    // pelo que `GET /canais/provedores` descreveu.
    expect(
      screen.getByRole("heading", { name: "Credencial do canal" }),
    ).toBeVisible();
    expect(screen.getByLabelText("ID do número de telefone")).toBeVisible();
    expect(formulario()).toBeVisible();
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
    await abrir("owner", null, null, null);

    expect(notFound).not.toHaveBeenCalled();
    expect(screen.getByText("As conexões não puderam ser lidas")).toBeVisible();
    expect(
      screen.queryByText("Nenhum canal de WhatsApp configurado"),
    ).toBeNull();
    // Sem sessão de API não há formulário — e não há estado vazio novo.
    expect(formulario()).toBeNull();
  });

  it("`owner` com as conexões lidas mas sem os formulários: a tela fica, o formulário não", async () => {
    // A corrida de milissegundos em que a sessão vence entre uma chamada e a
    // outra. A página não quebra e não inventa um estado: mostra o que veio.
    await abrir("owner", SEM_CANAL, NOT_CONFIGURED, null);

    expect(
      screen.getByText("Nenhum canal de WhatsApp configurado"),
    ).toBeVisible();
    expect(formulario()).toBeNull();
    expect(
      screen.queryByRole("heading", { name: "Credencial do canal" }),
    ).toBeNull();
  });

  it("… e o mesmo quando falta só o estado da credencial", async () => {
    await abrir("owner", SEM_CANAL, null, FORMS);

    expect(
      screen.getByText("Nenhum canal de WhatsApp configurado"),
    ).toBeVisible();
    expect(formulario()).toBeNull();
  });

  it("✅ `owner` sem canal e com sessão vê o formulário — é a tela do primeiro dia com a saída", async () => {
    await abrir("owner", SEM_CANAL);

    expect(
      screen.getByText("Nenhum canal de WhatsApp configurado"),
    ).toBeVisible();
    expect(
      screen.getByText("Nenhuma credencial gravada neste cliente."),
    ).toBeVisible();
    expect(formulario()).toBeVisible();
  });
});
