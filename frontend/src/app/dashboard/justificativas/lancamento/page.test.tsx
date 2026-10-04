import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LancamentoNoSecullumPage from "@/app/dashboard/justificativas/lancamento/page";
import type { PostingListRow } from "@/lib/alcada/posting";
import type { PostingScreen } from "@/lib/alcada/queries";
import type { ApprovalFilters } from "@/lib/alcada/url";

vi.mock("server-only", () => ({}));

const notFound = vi.fn(() => {
  throw new Error("NEXT_NOT_FOUND");
});

vi.mock("next/navigation", () => ({
  notFound: () => notFound(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const loadIdentity = vi.fn();
const loadPostingScreen = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  // `reviewsJustifications` fica o real: é a porta sob teste.
  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/alcada/queries", () => ({
  loadPostingScreen: (filters: ApprovalFilters) => loadPostingScreen(filters),
}));

const EU = "99999999-9999-4999-8999-999999999999";
const NORTE = "3f2504e0-4f89-41d3-9a0c-0305e82c3301";

const MARIA: PostingListRow = {
  review_id: "11111111-1111-4111-8111-111111111111",
  justification_id: "44444444-4444-4444-8444-444444444444",
  employee_id: "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  employee_name: "Maria Souza",
  unit_id: NORTE,
  unit_name: "DEV Norte",
  reference_date: "2026-09-24",
  type: "early_exit",
  type_description: "Saída antecipada",
  minutes: 75,
  text: "Consulta médica com atestado entregue ao gestor.",
  author_name: "Carlos Supervisor",
  reviewed_by: EU,
  reviewed_at: "2026-09-26T13:00:00Z",
  posted_to_source_at: null,
  posted_by: null,
};

/** Uma janela que a regra do DP não produziria: a tela tem de só mostrá-la. */
function lista(
  ano = 2026,
  mes = 10,
  rows: PostingListRow[] = [],
): Extract<PostingScreen["list"], { status: "ok" }> {
  return {
    status: "ok",
    queue: {
      ano,
      mes,
      period_start: "2026-09-16",
      period_end: "2026-10-15",
      rows,
    },
  };
}

async function abrir(
  role: string,
  list: PostingScreen["list"],
  params: Record<string, string> = {},
) {
  loadIdentity.mockResolvedValue({ role, user_id: EU });
  loadPostingScreen.mockResolvedValue({ list, units: [] });

  return render(
    await LancamentoNoSecullumPage({ searchParams: Promise.resolve(params) }),
  );
}

beforeEach(() => {
  notFound.mockClear();
  loadIdentity.mockReset();
  loadPostingScreen.mockReset();
});

describe("a porta é a alçada: `hr` e `owner`", () => {
  it.each([
    "personnel",
    "executive",
    "accounting",
    "unit_supervisor",
    "viewer",
  ])("⛔ `%s` recebe 404, e a API nem é chamada", async (role) => {
    loadIdentity.mockResolvedValue({ role, user_id: EU });

    await expect(
      LancamentoNoSecullumPage({ searchParams: Promise.resolve({}) }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadPostingScreen).not.toHaveBeenCalled();
  });

  it("⛔ sem vínculo com o tenant não há tela", async () => {
    loadIdentity.mockResolvedValue(null);

    await expect(
      LancamentoNoSecullumPage({ searchParams: Promise.resolve({}) }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it.each(["hr", "owner"])("✅ `%s` entra", async (role) => {
    await abrir(role, lista());

    expect(notFound).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", { level: 1, name: "Lançamento no Secullum" }),
    ).toBeVisible();
  });
});

describe("o recorte mora na query string, e a competência vem da API", () => {
  it("sem nada na URL, mostra a competência que a resposta trouxe", async () => {
    await abrir("hr", lista(2027, 1));

    expect(loadPostingScreen).toHaveBeenCalledWith({
      year: null,
      month: null,
      unitId: null,
      employeeId: null,
      from: null,
      to: null,
    });
    expect(screen.getByText(/aprovadas de janeiro\/2027/)).toBeVisible();
    expect(screen.getByLabelText("Mês da competência")).toHaveValue("1");
    expect(
      screen.getByRole("link", { name: "Próxima competência" }),
    ).toHaveAttribute(
      "href",
      "/dashboard/justificativas/lancamento?ano=2027&mes=2",
    );
    expect(
      screen.getByRole("link", { name: "Competência anterior" }),
    ).toHaveAttribute(
      "href",
      "/dashboard/justificativas/lancamento?ano=2026&mes=12",
    );
    expect(screen.getByLabelText("Data inicial")).toHaveAttribute(
      "min",
      "2026-09-16",
    );
    expect(screen.getByLabelText("Data final")).toHaveAttribute(
      "max",
      "2026-10-15",
    );
  });

  it("unidade, colaborador e datas do link chegam à API e aos links", async () => {
    await abrir("hr", lista(2026, 10, [MARIA]), {
      ano: "2026",
      mes: "10",
      un: NORTE,
      col: MARIA.employee_id,
      de: "2026-09-22",
      ate: "2026-09-30",
    });

    expect(loadPostingScreen).toHaveBeenCalledWith({
      year: 2026,
      month: 10,
      unitId: NORTE,
      employeeId: MARIA.employee_id,
      from: "2026-09-22",
      to: "2026-09-30",
    });
    // Anterior/próxima levam unidade e colaborador, e soltam as datas.
    expect(
      screen.getByRole("link", { name: "Próxima competência" }),
    ).toHaveAttribute(
      "href",
      `/dashboard/justificativas/lancamento?ano=2026&mes=11&un=${NORTE}&col=${MARIA.employee_id}`,
    );
    const seletor = screen.getByLabelText("Colaborador");
    expect(
      within(seletor).getByRole("option", { name: "Maria Souza" }),
    ).toHaveValue(MARIA.employee_id);
  });

  it("a linha da resposta chega à seção de pendentes", async () => {
    await abrir("hr", lista(2026, 10, [MARIA]));

    expect(
      within(
        screen.getByRole("list", { name: "A lançar no Secullum" }),
      ).getByRole("listitem", { name: "Maria Souza" }),
    ).toHaveTextContent("26/09/2026, por você");
    expect(
      screen.getByRole("group", { name: "Pendentes de lançamento" }),
    ).toHaveTextContent("1pendente");
  });

  it("⛔ nenhum uuid aparece na tela", async () => {
    const { container } = await abrir("hr", lista(2026, 10, [MARIA]));

    expect(container.textContent ?? "").not.toMatch(
      /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
    );
  });
});

describe("403 e falha não quebram a tela, e nunca viram 'nada a lançar'", () => {
  it("⛔ 403 da API mostra 'sem acesso'", async () => {
    await abrir("owner", { status: "forbidden" });

    expect(
      screen.getByText("Sem acesso ao lançamento no Secullum"),
    ).toBeVisible();
    expect(screen.queryByText("Nada a lançar no recorte")).toBeNull();
  });

  it("⛔ 422 é 'recorte inválido', com o caminho para limpá-lo", async () => {
    await abrir(
      "owner",
      { status: "invalid" },
      { ano: "2026", mes: "8", un: NORTE },
    );

    expect(screen.getByText("Recorte inválido")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Limpar recorte" }),
    ).toHaveAttribute(
      "href",
      "/dashboard/justificativas/lancamento?ano=2026&mes=8",
    );
    expect(screen.queryByText("Nada a lançar no recorte")).toBeNull();
  });

  it("API fora do ar é outra frase", async () => {
    await abrir("owner", { status: "unavailable" });

    expect(
      screen.getByText("A lista do lançamento não pôde ser lida"),
    ).toBeVisible();
    expect(screen.queryByText("Nada a lançar no recorte")).toBeNull();
  });
});
