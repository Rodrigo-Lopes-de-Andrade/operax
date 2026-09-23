import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DestinatariosPage from "@/app/dashboard/administracao/destinatarios/page";
import type { ContactRow } from "@/lib/canais/regras";
import type { Identity } from "@/lib/identity";
import type { UnitOption } from "@/lib/ponto/queries";

vi.mock("server-only", () => ({}));

const notFound = vi.fn(() => {
  throw new Error("NEXT_NOT_FOUND");
});

vi.mock("next/navigation", () => ({
  notFound: () => notFound(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const loadIdentity = vi.fn();
const loadContacts = vi.fn();
const loadUnits = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  // `isAdmin` fica o real: é a porta sob teste.
  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/canais/queries", () => ({
  loadContacts: () => loadContacts(),
}));

vi.mock("@/lib/ponto/queries", () => ({
  loadUnits: (...args: unknown[]) => loadUnits(...args),
}));

// O cliente do Caminho 1 é identificável de propósito: é ele que a página tem
// de entregar ao carregador das unidades.
const { SUPABASE } = vi.hoisted(() => ({ SUPABASE: { caminho: 1 } }));

vi.mock("@/lib/supabase-server", () => ({
  getServerSupabase: async () => SUPABASE,
}));

function identidade(role: string): Identity {
  return {
    user_id: "11111111-1111-4111-8111-111111111111",
    email: `${role}@fastpark.dev`,
    tenant_id: "22222222-2222-4222-8222-222222222222",
    role,
  };
}

const UNIDADE: UnitOption = {
  unitId: "11111111-1111-4111-8111-111111111111",
  code: "ZZA",
  slug: "zza",
  name: "Unidade Zz Alfa",
  companyId: "33333333-3333-4333-8333-333333333333",
  companyName: "Zz Ltda",
  companySlug: "zz-ltda",
};

const CONTATO: ContactRow = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  name: "Zz Pessoa",
  whatsapp: "5511999990000",
  email: "zz@fastpark.dev",
  type: "person",
  active: true,
  units: [],
};

async function abrir(role: string, contacts: ContactRow[] | null) {
  loadIdentity.mockResolvedValue(identidade(role));
  loadContacts.mockResolvedValue(contacts);
  loadUnits.mockResolvedValue([UNIDADE]);

  return render(await DestinatariosPage());
}

beforeEach(() => {
  notFound.mockClear();
  loadIdentity.mockReset();
  loadContacts.mockReset();
  loadUnits.mockReset();
});

describe("a porta da página é `isAdmin`", () => {
  it("⛔ `unit_supervisor` recebe 404, e nenhuma leitura é chamada", async () => {
    loadIdentity.mockResolvedValue(identidade("unit_supervisor"));

    await expect(DestinatariosPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalled();
    expect(loadContacts).not.toHaveBeenCalled();
    expect(loadUnits).not.toHaveBeenCalled();
  });

  it("⛔ `executive` também recebe 404 — lê a área de RH e não configura canal", async () => {
    loadIdentity.mockResolvedValue(identidade("executive"));

    await expect(DestinatariosPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadContacts).not.toHaveBeenCalled();
  });

  it("sem vínculo com o tenant não há tela", async () => {
    loadIdentity.mockResolvedValue(null);

    await expect(DestinatariosPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadContacts).not.toHaveBeenCalled();
  });

  it("✅ `owner` entra e vê a lista, com as unidades lidas pelo Caminho 1", async () => {
    await abrir("owner", [CONTATO]);

    expect(notFound).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", { level: 1, name: "Destinatários" }),
    ).toBeVisible();
    expect(screen.getByText("Zz Pessoa")).toBeVisible();
    expect(loadContacts).toHaveBeenCalledTimes(1);
    expect(loadUnits).toHaveBeenCalledWith(SUPABASE);
  });

  it("`null` nos contatos (sessão, 401, 403) é 'não puderam ser lidos' — não 'nenhum contato'", async () => {
    await abrir("owner", null);

    expect(
      screen.getByText("Os destinatários não puderam ser lidos"),
    ).toBeVisible();
    expect(screen.queryByText("Nenhum contato neste cliente")).toBeNull();
    expect(screen.queryByRole("button", { name: "Novo contato" })).toBeNull();
  });

  it("lista vazia é o estado do primeiro dia, com o botão de novo contato", async () => {
    await abrir("personnel", []);

    expect(screen.getByText("Nenhum contato neste cliente")).toBeVisible();
    expect(screen.getByRole("button", { name: "Novo contato" })).toBeVisible();
  });
});
