import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import UsuariosPage from "@/app/dashboard/usuarios/page";
import type { UnitOption } from "@/lib/ponto/queries";
import type { TenantUser } from "@/lib/usuarios/contract";
import type { UsersScreen } from "@/lib/usuarios/queries";

vi.mock("server-only", () => ({}));

const notFound = vi.fn(() => {
  throw new Error("NEXT_NOT_FOUND");
});

vi.mock("next/navigation", () => ({
  notFound: () => notFound(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const loadIdentity = vi.fn();
const loadUsersScreen = vi.fn();
const request = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  // `isAdmin` fica o real: é a porta sob teste.
  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/usuarios/queries", () => ({
  loadUsersScreen: () => loadUsersScreen(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    requestApiAsUser: (...args: unknown[]) => request(...args),
  };
});

/**
 * Os campos que nenhuma resposta deve carregar — e, se carregar, que nenhuma
 * tela pode mostrar. O backend já não os manda (varredura do U3, lado API);
 * aqui a prova é que a tela não lê nada além do que o contrato nomeia.
 */
const VAZAMENTO = {
  password: "SENHA-VAZADA-1",
  token: "TOKEN-VAZADO-2",
  action_link: "https://auth.example/verify?token=LINK-VAZADO-3",
  access_token: "ACCESS-VAZADO-4",
};
const SENTINELAS = Object.values(VAZAMENTO);

const UNIDADES: UnitOption[] = [
  {
    unitId: "d0000000-0000-4000-8000-000000000001",
    code: "N01",
    slug: "n01",
    name: "Norte",
    companyId: "c0000000-0000-4000-8000-00000000000a",
    companyName: "Alfa Estacionamentos",
    companySlug: "alfa-estacionamentos",
  },
];

const PENDENTE: TenantUser = {
  user_id: "a0000000-0000-4000-8000-000000000003",
  email: "novo@fastpark.dev",
  name: "Nina Nova",
  role: "viewer",
  active: true,
  deactivated_at: null,
  invitation_accepted: false,
  invited_by: {
    user_id: "a0000000-0000-4000-8000-0000000000ff",
    email: "rh@fastpark.dev",
    name: "Rita RH",
    ...VAZAMENTO,
  } as TenantUser["invited_by"],
  scope_mode: "by_scope",
  scope: [
    {
      company_id: "c0000000-0000-4000-8000-00000000000a",
      company_name: "Alfa Estacionamentos",
      unit_id: null,
      unit_name: null,
      ...VAZAMENTO,
    } as TenantUser["scope"][number],
  ],
  ...VAZAMENTO,
} as TenantUser;

function tela(overrides: Partial<UsersScreen> = {}): UsersScreen {
  return {
    list: { status: "ok", list: { users: [PENDENTE] } },
    units: UNIDADES,
    ...overrides,
  };
}

async function abrir(role: string | null, screenData = tela()) {
  loadIdentity.mockResolvedValue(role === null ? null : { role });
  loadUsersScreen.mockResolvedValue(screenData);
  return render(await UsuariosPage());
}

function semVazamento(container: HTMLElement) {
  for (const sentinela of SENTINELAS) {
    expect(container.innerHTML).not.toContain(sentinela);
  }
}

beforeEach(() => {
  notFound.mockClear();
  loadIdentity.mockReset();
  loadUsersScreen.mockReset();
  request.mockReset();
});

describe("/dashboard/usuarios — quem abre", () => {
  it.each(["owner", "hr", "personnel"])("`%s` abre a tela", async (role) => {
    await abrir(role);

    expect(
      screen.getByRole("heading", { level: 1, name: "Usuários" }),
    ).toBeInTheDocument();
    expect(notFound).not.toHaveBeenCalled();
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
    expect(loadUsersScreen).not.toHaveBeenCalled();
  });

  it("o 403 da API vira 'sem acesso', não lista vazia", async () => {
    await abrir("hr", tela({ list: { status: "forbidden" } }));

    expect(
      screen.getByText("Sem acesso à lista de usuários"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Nenhum usuário neste cliente ainda."),
    ).toBeNull();
  });

  it("API fora do ar vira 'não pôde ser lida', não lista vazia", async () => {
    await abrir("owner", tela({ list: { status: "unavailable" } }));

    expect(
      screen.getByText("A lista de usuários não pôde ser lida"),
    ).toBeInTheDocument();
  });

  it("sem as unidades, o convite não aparece com um seletor vazio", async () => {
    await abrir("owner", tela({ units: null }));

    expect(
      screen.getByText("As unidades não puderam ser lidas"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enviar convite" })).toBeNull();
  });
});

describe("⛔ varredura: nenhuma tela mostra senha, token ou link de convite", () => {
  it("a lista, com os quatro campos vindos da API", async () => {
    const { container } = await abrir("owner");

    expect(screen.getByText("Nina Nova")).toBeInTheDocument();
    semVazamento(container);
  });

  it("a resposta do convite", async () => {
    request.mockResolvedValue({
      user_id: "a0000000-0000-4000-8000-000000000009",
      email: "zeca@fastpark.dev",
      role: "viewer",
      invitation_sent: true,
      ...VAZAMENTO,
    });
    const user = userEvent.setup();
    const { container } = await abrir("owner");

    await user.type(screen.getByLabelText("Nome"), "Zeca");
    await user.type(screen.getByLabelText("E-mail"), "zeca@fastpark.dev");
    await user.click(screen.getByLabelText("Norte"));
    await user.click(screen.getByRole("button", { name: "Enviar convite" }));

    expect(
      await screen.findByText("Convite enviado para zeca@fastpark.dev."),
    ).toBeInTheDocument();
    semVazamento(container);
  });

  it("a resposta do reenvio", async () => {
    request.mockResolvedValue({
      user_id: PENDENTE.user_id,
      email: "novo@fastpark.dev",
      ...VAZAMENTO,
    });
    const user = userEvent.setup();
    const { container } = await abrir("owner");

    await user.click(screen.getByRole("button", { name: "Reenviar convite" }));
    await user.click(screen.getByRole("button", { name: "Confirmar reenvio" }));

    expect(
      await screen.findByText("Convite reenviado para novo@fastpark.dev."),
    ).toBeInTheDocument();
    semVazamento(container);
  });
});
