import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UserList } from "@/components/usuarios/user-list";
import { ApiError } from "@/lib/api";
import { RESEND_ERROR_MESSAGE, type TenantUser } from "@/lib/usuarios/contract";

const request = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    requestApiAsUser: (...args: unknown[]) => request(...args),
  };
});

const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

const COMPANY_ALFA = "c0000000-0000-4000-8000-00000000000a";
const COMPANY_BETA = "c0000000-0000-4000-8000-00000000000b";
const UNIT_NORTE = "d0000000-0000-4000-8000-000000000001";
const PENDENTE = "a0000000-0000-4000-8000-000000000003";

function usuario(overrides: Partial<TenantUser>): TenantUser {
  return {
    user_id: "a0000000-0000-4000-8000-000000000001",
    email: "ana@fastpark.dev",
    name: "Ana Prado",
    role: "unit_supervisor",
    active: true,
    deactivated_at: null,
    invitation_accepted: true,
    invited_by: {
      user_id: "a0000000-0000-4000-8000-0000000000ff",
      email: "rh@fastpark.dev",
      name: "Rita RH",
    },
    scope_mode: "by_scope",
    scope: [
      {
        company_id: COMPANY_ALFA,
        company_name: "Alfa Estacionamentos",
        unit_id: UNIT_NORTE,
        unit_name: "Unidade Norte",
      },
    ],
    ...overrides,
  };
}

const LISTA: TenantUser[] = [
  usuario({}),
  usuario({
    user_id: "a0000000-0000-4000-8000-000000000002",
    name: "Otávio Owner",
    email: "owner@fastpark.dev",
    role: "owner",
    scope_mode: "by_role",
    // ⛔ A API manda vazio; aqui vai cheio para provar que a tela não o lê.
    scope: [
      {
        company_id: COMPANY_BETA,
        company_name: "Beta Garagens",
        unit_id: null,
        unit_name: null,
      },
    ],
    invited_by: null,
  }),
  usuario({
    user_id: PENDENTE,
    name: null,
    email: "novo@fastpark.dev",
    role: "viewer",
    invitation_accepted: false,
    invited_by: {
      user_id: "a0000000-0000-4000-8000-0000000000fe",
      email: "dp@fastpark.dev",
      name: null,
    },
    scope: [
      {
        company_id: COMPANY_BETA,
        company_name: "Beta Garagens",
        unit_id: null,
        unit_name: null,
      },
    ],
  }),
  usuario({
    user_id: "a0000000-0000-4000-8000-000000000004",
    name: "Ivo Inativo",
    email: "ivo@fastpark.dev",
    active: false,
    deactivated_at: "2026-09-30T15:00:00Z",
  }),
];

function linhaDe(texto: string) {
  return screen.getByText(texto).closest("tr") as HTMLElement;
}

beforeEach(() => {
  request.mockReset();
});

describe("a lista de usuários", () => {
  it("mostra as colunas e o conteúdo de cada uma", () => {
    render(<UserList users={LISTA} />);

    for (const coluna of [
      "Nome",
      "E-mail",
      "Papel",
      "Escopo",
      "Status",
      "Convidado por",
    ]) {
      expect(
        screen.getByRole("columnheader", { name: coluna }),
      ).toBeInTheDocument();
    }

    const ana = linhaDe("Ana Prado");
    expect(within(ana).getByText("ana@fastpark.dev")).toBeInTheDocument();
    expect(within(ana).getByText("Supervisor de unidade")).toBeInTheDocument();
    expect(
      within(ana).getByText("Alfa Estacionamentos · Unidade Norte"),
    ).toBeInTheDocument();
    expect(within(ana).getByText("Ativo")).toBeInTheDocument();
    expect(within(ana).getByText("Rita RH")).toBeInTheDocument();
  });

  it("⛔ `by_role` diz 'todas as unidades (pelo papel)' e não lista o `scope`", () => {
    render(<UserList users={LISTA} />);

    const owner = linhaDe("Otávio Owner");
    expect(
      within(owner).getByText("todas as unidades (pelo papel)"),
    ).toBeInTheDocument();
    expect(within(owner).queryByText(/Beta Garagens/)).toBeNull();
  });

  it("empresa inteira aparece como 'todas as unidades' da empresa", () => {
    render(<UserList users={LISTA} />);

    const pendente = linhaDe("novo@fastpark.dev");
    expect(
      within(pendente).getByText("Beta Garagens · todas as unidades"),
    ).toBeInTheDocument();
  });

  it("quem convidou sem nome aparece pelo e-mail", () => {
    render(<UserList users={LISTA} />);

    expect(
      within(linhaDe("novo@fastpark.dev")).getByText("dp@fastpark.dev"),
    ).toBeInTheDocument();
  });

  it("inativo em cinza, com a data da desativação", () => {
    render(<UserList users={LISTA} />);

    const ivo = linhaDe("Ivo Inativo");
    expect(ivo).toHaveAttribute("data-inactive");
    expect(ivo).toHaveClass("text-ink-faint");
    expect(
      within(ivo).getByText("Inativo desde 30/09/2026"),
    ).toBeInTheDocument();

    // O positivo ao lado: ativo não é cinza.
    expect(linhaDe("Ana Prado")).not.toHaveAttribute("data-inactive");
    expect(linhaDe("Ana Prado")).not.toHaveClass("text-ink-faint");
  });

  it("nenhum uuid aparece na tela", () => {
    const { container } = render(<UserList users={LISTA} />);

    expect(container.textContent).not.toMatch(UUID_RE);
  });

  it("o nome abre o detalhe do usuário", () => {
    render(<UserList users={LISTA} />);

    expect(screen.getByRole("link", { name: "Ana Prado" })).toHaveAttribute(
      "href",
      "/dashboard/usuarios/a0000000-0000-4000-8000-000000000001",
    );
    expect(screen.getByRole("link", { name: "sem nome" })).toHaveAttribute(
      "href",
      `/dashboard/usuarios/${PENDENTE}`,
    );
  });

  it("'Reenviar convite' só para quem está ativo e não aceitou", () => {
    render(<UserList users={LISTA} />);

    const botoes = screen.getAllByRole("button", { name: "Reenviar convite" });
    expect(botoes).toHaveLength(1);
    expect(
      within(linhaDe("novo@fastpark.dev")).getByText("Convite pendente"),
    ).toBeInTheDocument();
  });
});

describe("reenviar convite", () => {
  it("são dois cliques, e o segundo manda `{}` para o membro certo", async () => {
    request.mockResolvedValue({
      user_id: PENDENTE,
      email: "novo@fastpark.dev",
    });
    const user = userEvent.setup();
    render(<UserList users={LISTA} />);

    await user.click(screen.getByRole("button", { name: "Reenviar convite" }));
    expect(request).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Confirmar reenvio" }));

    expect(request).toHaveBeenCalledWith(
      `/usuarios/${PENDENTE}/reenviar-convite`,
      { method: "POST", body: {} },
    );
    expect(
      await screen.findByText("Convite reenviado para novo@fastpark.dev."),
    ).toBeInTheDocument();
  });

  it.each(Object.entries(RESEND_ERROR_MESSAGE))(
    "a recusa `%s` vira a frase dela",
    async (code, message) => {
      request.mockRejectedValue(new ApiError(409, code));
      const user = userEvent.setup();
      render(<UserList users={LISTA} />);

      await user.click(
        screen.getByRole("button", { name: "Reenviar convite" }),
      );
      await user.click(
        screen.getByRole("button", { name: "Confirmar reenvio" }),
      );

      expect(await screen.findByRole("alert")).toHaveTextContent(message);
    },
  );

  it("`convite_ja_aceito` aponta para 'Esqueci minha senha' (decisão do dono, 05/10)", async () => {
    request.mockRejectedValue(new ApiError(409, "convite_ja_aceito"));
    const user = userEvent.setup();
    render(<UserList users={LISTA} />);

    await user.click(screen.getByRole("button", { name: "Reenviar convite" }));
    await user.click(screen.getByRole("button", { name: "Confirmar reenvio" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Essa pessoa já aceitou o convite. Se ela não lembra a senha, pode usar 'Esqueci minha senha' na tela de entrada.",
    );
  });

  it("código desconhecido cai na frase padrão, nunca no `detail` cru", async () => {
    request.mockRejectedValue(new ApiError(500, "algo_interno"));
    const user = userEvent.setup();
    render(<UserList users={LISTA} />);

    await user.click(screen.getByRole("button", { name: "Reenviar convite" }));
    await user.click(screen.getByRole("button", { name: "Confirmar reenvio" }));

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Não consegui reenviar o convite agora");
    expect(alerta).not.toHaveTextContent("algo_interno");
  });
});
