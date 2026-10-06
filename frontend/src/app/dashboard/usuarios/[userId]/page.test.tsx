import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import UsuarioPage from "@/app/dashboard/usuarios/[userId]/page";
import type { TenantUser } from "@/lib/usuarios/contract";
import type { UserDetailScreen } from "@/lib/usuarios/queries";

vi.mock("server-only", () => ({}));

const notFound = vi.fn(() => {
  throw new Error("NEXT_NOT_FOUND");
});

vi.mock("next/navigation", () => ({
  notFound: () => notFound(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const loadIdentity = vi.fn();
const loadUserDetailScreen = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  // `isAdmin` fica o real: é a porta sob teste.
  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/usuarios/queries", () => ({
  loadUserDetailScreen: (userId: string) => loadUserDetailScreen(userId),
}));

const ALVO = "a0000000-0000-4000-8000-000000000001";

const MEMBRO: TenantUser = {
  user_id: ALVO,
  email: "ana@fastpark.dev",
  name: "Ana Prado",
  role: "viewer",
  active: true,
  deactivated_at: null,
  invitation_accepted: true,
  invited_by: null,
  scope_mode: "by_scope",
  scope: [],
};

function tela(overrides: Partial<UserDetailScreen> = {}): UserDetailScreen {
  return {
    detail: { status: "ok", user: MEMBRO },
    matrix: { roles: [{ role: "viewer", domains: [] }] },
    units: [],
    ...overrides,
  };
}

async function abrir(
  role: string | null,
  screenData = tela(),
  userId: string = ALVO,
) {
  loadIdentity.mockResolvedValue(role === null ? null : { role });
  loadUserDetailScreen.mockResolvedValue(screenData);
  return render(await UsuarioPage({ params: Promise.resolve({ userId }) }));
}

beforeEach(() => {
  notFound.mockClear();
  loadIdentity.mockReset();
  loadUserDetailScreen.mockReset();
});

describe("/dashboard/usuarios/[userId] — quem abre", () => {
  it.each(["owner", "hr", "personnel"])("`%s` abre o detalhe", async (role) => {
    await abrir(role);

    expect(
      screen.getByRole("heading", { level: 1, name: "Detalhe do usuário" }),
    ).toBeInTheDocument();
    expect(loadUserDetailScreen).toHaveBeenCalledWith(ALVO);
  });

  it.each([
    "executive",
    "regional_manager",
    "unit_supervisor",
    "operations_manager",
    "accounting",
    "viewer",
    null,
  ])("⛔ `%s` recebe 404 e nada é lido", async (role) => {
    await expect(abrir(role)).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadUserDetailScreen).not.toHaveBeenCalled();
  });

  it("um id que não é uuid vira 404 sem chegar à API", async () => {
    await expect(abrir("owner", tela(), "matriz")).rejects.toThrow(
      "NEXT_NOT_FOUND",
    );
    expect(loadUserDetailScreen).not.toHaveBeenCalled();
  });
});

describe("o papel do chamador vem de /me", () => {
  it("owner: seletor de papel habilitado", async () => {
    await abrir("owner");

    expect(screen.getByRole("combobox", { name: "Papel" })).toBeEnabled();
  });

  it.each(["hr", "personnel"])(
    "⛔ `%s`: seletor de papel desabilitado",
    async (role) => {
      await abrir(role);

      expect(screen.getByRole("combobox", { name: "Papel" })).toBeDisabled();
    },
  );
});

describe("estados da leitura", () => {
  it("404 da API vira 'não encontrado'", async () => {
    await abrir("hr", tela({ detail: { status: "not_found" } }));

    expect(screen.getByText("Usuário não encontrado")).toBeInTheDocument();
  });

  it("403 da API vira 'sem acesso'", async () => {
    await abrir("hr", tela({ detail: { status: "forbidden" } }));

    expect(screen.getByText("Sem acesso a este usuário")).toBeInTheDocument();
  });

  it("API fora do ar vira 'não pôde ser lido', não tela branca", async () => {
    await abrir("owner", tela({ detail: { status: "unavailable" } }));

    expect(screen.getByText("O usuário não pôde ser lido")).toBeInTheDocument();
  });
});
