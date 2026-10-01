import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AprovacaoDeJustificativasPage from "@/app/dashboard/justificativas/aprovacao/page";
import type { ApprovalScreen } from "@/lib/alcada/queries";
import type { ApprovalQueueRow } from "@/lib/alcada/review";
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
const loadApprovalScreen = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  // `reviewsJustifications` fica o real: é a porta sob teste.
  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/alcada/queries", () => ({
  loadApprovalScreen: (filters: ApprovalFilters) => loadApprovalScreen(filters),
}));

/** Uma janela que a regra do DP não produziria: a tela tem de só mostrá-la. */
function fila(
  ano = 2026,
  mes = 10,
  rows: ApprovalQueueRow[] = [],
): Extract<ApprovalScreen["queue"], { status: "ok" }> {
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
  queue: ApprovalScreen["queue"],
  params: Record<string, string> = {},
) {
  loadIdentity.mockResolvedValue({ role });
  loadApprovalScreen.mockResolvedValue({ queue, units: [] });

  return render(
    await AprovacaoDeJustificativasPage({
      searchParams: Promise.resolve(params),
    }),
  );
}

beforeEach(() => {
  notFound.mockClear();
  loadIdentity.mockReset();
  loadApprovalScreen.mockReset();
});

describe("a porta é a alçada: `hr` e `owner`", () => {
  it.each(["personnel", "executive", "unit_supervisor", "viewer"])(
    "⛔ `%s` recebe 404, e a API nem é chamada",
    async (role) => {
      loadIdentity.mockResolvedValue({ role });

      await expect(
        AprovacaoDeJustificativasPage({ searchParams: Promise.resolve({}) }),
      ).rejects.toThrow("NEXT_NOT_FOUND");
      expect(loadApprovalScreen).not.toHaveBeenCalled();
    },
  );

  it("⛔ sem vínculo com o tenant não há tela", async () => {
    loadIdentity.mockResolvedValue(null);

    await expect(
      AprovacaoDeJustificativasPage({ searchParams: Promise.resolve({}) }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it.each(["hr", "owner"])("✅ `%s` entra", async (role) => {
    await abrir(role, fila());

    expect(notFound).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", { name: "Aprovação de justificativas" }),
    ).toBeVisible();
  });
});

describe("a competência vem da API", () => {
  it("sem nada na URL, não escolhe competência — mostra a que a resposta trouxe", async () => {
    // Outro ano e outro mês que os de qualquer relógio do teste: se a tela
    // escolhesse a competência, ou montasse os links da URL em vez da
    // resposta, isto cairia.
    await abrir("hr", fila(2027, 1));

    expect(loadApprovalScreen).toHaveBeenCalledWith({
      year: null,
      month: null,
      unitId: null,
      employeeId: null,
      from: null,
      to: null,
    });
    expect(screen.getByText(/indícios de janeiro\/2027/)).toBeVisible();
    expect(screen.getByLabelText("Mês da competência")).toHaveValue("1");
    expect(screen.getByLabelText("Ano da competência")).toHaveValue("2027");
    // Os links partem da competência devolvida, e a levam na URL.
    expect(
      screen.getByRole("link", { name: "Próxima competência" }),
    ).toHaveAttribute(
      "href",
      "/dashboard/justificativas/aprovacao?ano=2027&mes=2",
    );
    expect(screen.getByLabelText("Data inicial")).toHaveAttribute(
      "min",
      "2026-09-16",
    );
  });

  it("a competência do link é a que a API recebe", async () => {
    await abrir("hr", fila(2026, 8), {
      ano: "2026",
      mes: "8",
      de: "2026-08-01",
    });

    expect(loadApprovalScreen).toHaveBeenCalledWith(
      expect.objectContaining({ year: 2026, month: 8, from: "2026-08-01" }),
    );
  });

  it("⛔ data impossível no link não chega à API", async () => {
    await abrir("hr", fila(), { de: "2026-02-31" });

    expect(loadApprovalScreen).toHaveBeenCalledWith(
      expect.objectContaining({ from: null }),
    );
  });
});

const MARIA: ApprovalQueueRow = {
  justification_id: "11111111-1111-4111-8111-111111111111",
  employee_id: "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  employee_name: "Maria Souza",
  unit_id: null,
  unit_name: "DEV Norte",
  reference_date: "2026-09-24",
  type: "early_exit",
  type_description: "Saída antecipada",
  minutes: 75,
  text: "Consulta médica com atestado entregue ao gestor.",
  author_name: "Carlos Supervisor",
  created_at: "2026-09-25T13:00:00Z",
  can_review: true,
  blocked_reason: null,
};

describe("as linhas da resposta chegam à fila e ao seletor", () => {
  it("✅ a linha aparece na fila, e o colaborador dela no seletor", async () => {
    // Sem linha no mock, uma página que passasse `rows={[]}` à fila ou aos
    // filtros cairia em "nada para aprovar" com a suíte inteira verde.
    await abrir("hr", fila(2026, 10, [MARIA]));

    expect(
      screen.getByRole("listitem", { name: "Maria Souza" }),
    ).toHaveTextContent("Consulta médica com atestado entregue ao gestor.");
    expect(
      screen.getByRole("heading", {
        name: "1 justificativa esperando revisão",
      }),
    ).toBeVisible();
    expect(screen.queryByText("Nada esperando revisão no recorte")).toBeNull();

    const seletor = screen.getByLabelText("Colaborador");
    expect(
      within(seletor).getByRole("option", { name: "Maria Souza" }),
    ).toHaveValue(MARIA.employee_id);
  });
});

describe("403 e falha não quebram a tela, e nunca viram fila vazia", () => {
  it("⛔ 403 da API mostra 'sem acesso'", async () => {
    await abrir("owner", { status: "forbidden" });

    expect(
      screen.getByText("Sem acesso à aprovação de justificativas"),
    ).toBeVisible();
    expect(screen.queryByText("Nada esperando revisão no recorte")).toBeNull();
  });

  it("⛔ 422 é 'recorte inválido', com o caminho para limpá-lo", async () => {
    await abrir(
      "owner",
      { status: "invalid" },
      { ano: "2026", mes: "8", un: "3f2504e0-4f89-41d3-9a0c-0305e82c3301" },
    );

    expect(screen.getByText("Recorte inválido")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Limpar recorte" }),
    ).toHaveAttribute(
      "href",
      "/dashboard/justificativas/aprovacao?ano=2026&mes=8",
    );
    expect(
      screen.queryByText("A fila de aprovação não pôde ser lida"),
    ).toBeNull();
  });

  it("API fora do ar é outra frase", async () => {
    await abrir("owner", { status: "unavailable" });

    expect(
      screen.getByText("A fila de aprovação não pôde ser lida"),
    ).toBeVisible();
    expect(screen.queryByText("Nada esperando revisão no recorte")).toBeNull();
  });
});
