import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WorkPosts } from "@/components/dp/work-posts";
import type { WorkPostList } from "@/lib/dp/queries";

const request = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push: vi.fn() }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    requestApiAsUser: (...args: unknown[]) => request(...args),
  };
});

const UNIT_A = "11111111-1111-4111-8111-111111111111";
const UNIT_B = "22222222-2222-4222-8222-222222222222";

const UNITS = [
  { id: UNIT_A, name: "Aeroporto" },
  { id: UNIT_B, name: "Rodoviária" },
];

function quadro(overrides: Partial<WorkPostList> = {}): WorkPostList {
  return {
    can_write: true,
    rows: [
      {
        id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        unit_id: UNIT_A,
        unit_name: "Aeroporto",
        code: "7703",
        name: "Portaria",
        active: true,
        created_at: "2026-09-01T12:00:00Z",
      },
      {
        id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        unit_id: UNIT_B,
        unit_name: "Rodoviária",
        code: "8801",
        name: null,
        active: false,
        created_at: "2026-09-01T12:00:00Z",
      },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  request.mockReset();
  refresh.mockReset();
});

describe("a escala vinculada não tem dado, e a tela diz isso", () => {
  it("marca todas as linhas como não vinculadas e explica por quê", () => {
    render(<WorkPosts screen={quadro()} units={UNITS} />);

    // Uma marca por posto: um traço mudo seria lido como "este posto ficou sem
    // escala", e um nome qualquer seria dado inventado.
    expect(screen.getAllByText("não vinculada")).toHaveLength(2);
    expect(
      screen.getByText(/elo entre posto e escala ainda não existe no banco/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Nenhum posto tem escala vinculada hoje/),
    ).toBeInTheDocument();
  });

  it("mostra a coluna, para que a ausência apareça na conferência", () => {
    render(<WorkPosts screen={quadro()} units={UNITS} />);

    expect(
      screen.getAllByRole("columnheader", { name: "Escala vinculada" }),
    ).toHaveLength(2);
  });
});

describe("lista por unidade", () => {
  it("agrupa os postos pela unidade a que pertencem", () => {
    render(<WorkPosts screen={quadro()} units={UNITS} />);

    expect(
      screen.getByRole("heading", { name: "Aeroporto" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Rodoviária" }),
    ).toBeInTheDocument();

    const aeroporto = screen.getByRole("table", {
      name: "Postos da unidade Aeroporto",
    });
    expect(within(aeroporto).getByText("7703")).toBeInTheDocument();
    expect(within(aeroporto).queryByText("8801")).not.toBeInTheDocument();
  });

  it("diz quando o Quadro está vazio, sem fingir que há postos", () => {
    render(<WorkPosts screen={quadro({ rows: [] })} units={UNITS} />);

    expect(screen.getByText("Nenhum posto cadastrado")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("quem não escreve não vê a ação — e quem escreve vê", () => {
  it("com can_write, o cadastro e a saída de operação existem", () => {
    render(<WorkPosts screen={quadro()} units={UNITS} />);

    expect(
      screen.getByRole("button", { name: "Novo posto" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Tirar de operação" }),
    ).toBeInTheDocument();
  });

  it("sem can_write, as ações somem e a lista continua lá", () => {
    render(<WorkPosts screen={quadro({ can_write: false })} units={UNITS} />);

    // O positivo ao lado do negativo: sem a lista, o negativo passaria numa
    // tela que não renderiza nada.
    expect(screen.getByText("7703")).toBeInTheDocument();
    expect(screen.getByText("8801")).toBeInTheDocument();

    expect(
      screen.queryByRole("button", { name: "Novo posto" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Tirar de operação" }),
    ).not.toBeInTheDocument();
  });
});

describe("cadastro e saída de operação", () => {
  it("cadastra o posto com unidade, código e nome", async () => {
    request.mockResolvedValue({});
    const user = userEvent.setup();
    render(<WorkPosts screen={quadro()} units={UNITS} />);

    await user.click(screen.getByRole("button", { name: "Novo posto" }));
    await user.selectOptions(
      screen.getByLabelText("Unidade do posto"),
      "Rodoviária",
    );
    await user.type(screen.getByLabelText("Código"), "9001");
    await user.type(screen.getByLabelText("Nome (opcional)"), "Guarita");
    await user.click(screen.getByRole("button", { name: "Cadastrar posto" }));

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/dp/postos", {
        method: "POST",
        body: { unit_id: UNIT_B, code: "9001", name: "Guarita" },
      }),
    );
  });

  it("manda `null` quando o nome fica em branco, em vez de string vazia", async () => {
    request.mockResolvedValue({});
    const user = userEvent.setup();
    render(<WorkPosts screen={quadro()} units={UNITS} />);

    await user.click(screen.getByRole("button", { name: "Novo posto" }));
    await user.type(screen.getByLabelText("Código"), "9002");
    await user.click(screen.getByRole("button", { name: "Cadastrar posto" }));

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/dp/postos", {
        method: "POST",
        body: { unit_id: UNIT_A, code: "9002", name: null },
      }),
    );
  });

  it("não envia nada sem código, e diz o que falta", async () => {
    const user = userEvent.setup();
    render(<WorkPosts screen={quadro()} units={UNITS} />);

    await user.click(screen.getByRole("button", { name: "Novo posto" }));
    await user.click(screen.getByRole("button", { name: "Cadastrar posto" }));

    expect(
      await screen.findByText("Informe o código do posto."),
    ).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
  });

  it("mostra a recusa do banco quando o código repete na unidade", async () => {
    const { ApiError } = await import("@/lib/api");
    request.mockRejectedValue(
      new ApiError(409, "já existe o posto 7703 nesta unidade"),
    );
    const user = userEvent.setup();
    render(<WorkPosts screen={quadro()} units={UNITS} />);

    await user.click(screen.getByRole("button", { name: "Novo posto" }));
    await user.type(screen.getByLabelText("Código"), "7703");
    await user.click(screen.getByRole("button", { name: "Cadastrar posto" }));

    expect(
      await screen.findByText("já existe o posto 7703 nesta unidade"),
    ).toBeInTheDocument();
  });

  it("tira de operação em vez de apagar — não existe apagar", async () => {
    request.mockResolvedValue({});
    const user = userEvent.setup();
    render(<WorkPosts screen={quadro()} units={UNITS} />);

    expect(
      screen.queryByRole("button", { name: /excluir|apagar|remover/i }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Tirar de operação" }));

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(
        "/dp/postos/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        { method: "PATCH", body: { active: false } },
      ),
    );
    expect(refresh).toHaveBeenCalled();
  });

  it("devolve à operação o posto que estava fora", async () => {
    request.mockResolvedValue({});
    const user = userEvent.setup();
    render(<WorkPosts screen={quadro()} units={UNITS} />);

    await user.click(screen.getByRole("button", { name: "Voltar à operação" }));

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(
        "/dp/postos/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        { method: "PATCH", body: { active: true } },
      ),
    );
  });
});
