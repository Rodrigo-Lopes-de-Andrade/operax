import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApprovalFiltersBar } from "@/components/alcada/approval-filters";
import type { ApprovalQueueRow } from "@/lib/alcada/review";
import type { ResolvedApprovalFilters } from "@/lib/alcada/url";
import type { UnitOption } from "@/lib/ponto/queries";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
}));

const NORTE = "3f2504e0-4f89-41d3-9a0c-0305e82c3301";
const MARIA = "7c9e6679-7425-40de-944b-e07fc1f90ae7";
const PATH = "/dashboard/justificativas/aprovacao";

const FILTERS: ResolvedApprovalFilters = {
  year: 2026,
  month: 10,
  unitId: null,
  employeeId: null,
  from: null,
  to: null,
};

const UNITS: UnitOption[] = [
  {
    unitId: NORTE,
    code: "NORTE",
    slug: "norte",
    name: "DEV Norte",
    companyId: "c-1",
    companyName: "FastPark Dev",
    companySlug: "fastpark-dev",
  },
];

const ROWS = [
  {
    employee_id: MARIA,
    employee_name: "Maria Souza",
  },
] as ApprovalQueueRow[];

/**
 * A janela da resposta é, de propósito, uma que a regra do DP NÃO produziria:
 * se a tela a recalculasse em vez de lê-la, as asserções abaixo cairiam.
 */
const PERIOD = { start: "2026-09-16", end: "2026-10-15" };

function montar(filters: ResolvedApprovalFilters = FILTERS) {
  return render(
    <ApprovalFiltersBar
      filters={filters}
      period={PERIOD}
      units={UNITS}
      rows={ROWS}
    />,
  );
}

beforeEach(() => push.mockReset());

describe("o recorte mora na query string", () => {
  it("declara a janela que a API devolveu, sem calcular nada", () => {
    montar();

    expect(
      screen.getByText(
        /A competência de outubro\/2026 vai de 16\/09\/2026 a 15\/10\/2026/,
      ),
    ).toBeVisible();
    expect(screen.getByLabelText("Mês da competência")).toHaveValue("10");
    expect(screen.getByLabelText("Ano da competência")).toHaveValue("2026");
  });

  it("trocar o mês navega para a competência nova", async () => {
    const user = userEvent.setup();
    montar();

    await user.selectOptions(screen.getByLabelText("Mês da competência"), "9");

    expect(push).toHaveBeenCalledWith(`${PATH}?ano=2026&mes=9`);
  });

  it("anterior e próxima são aritmética de mês, e limpam as datas", () => {
    montar({ ...FILTERS, month: 1, year: 2027, from: "2026-12-28" });

    expect(
      screen.getByRole("link", { name: "Competência anterior" }),
    ).toHaveAttribute("href", `${PATH}?ano=2026&mes=12`);
    expect(
      screen.getByRole("link", { name: "Próxima competência" }),
    ).toHaveAttribute("href", `${PATH}?ano=2027&mes=2`);
  });

  it("o seletor de ano não oferece o que o parser descartaria", () => {
    montar({ ...FILTERS, year: 2100 });

    const anos = screen
      .getAllByRole("option")
      .map((option) => option.textContent)
      .filter((text) => /^\d{4}$/.test(text ?? ""));
    expect(anos).toEqual(["2100", "2099", "2098"]);
  });

  it("unidade e colaborador vão para a URL pelo id", async () => {
    const user = userEvent.setup();
    montar();

    await user.selectOptions(screen.getByLabelText("Unidade"), NORTE);
    expect(push).toHaveBeenLastCalledWith(
      `${PATH}?ano=2026&mes=10&un=${NORTE}`,
    );

    await user.selectOptions(screen.getByLabelText("Colaborador"), MARIA);
    expect(push).toHaveBeenLastCalledWith(
      `${PATH}?ano=2026&mes=10&col=${MARIA}`,
    );
  });

  it("as datas vão para a URL e ficam presas à janela da resposta", () => {
    montar();

    const de = screen.getByLabelText("Data inicial");
    expect(de).toHaveAttribute("min", "2026-09-16");
    expect(de).toHaveAttribute("max", "2026-10-15");
    expect(screen.getByLabelText("Data final")).toHaveAttribute(
      "max",
      "2026-10-15",
    );

    fireEvent.change(de, { target: { value: "2026-09-25" } });
    expect(push).toHaveBeenLastCalledWith(
      `${PATH}?ano=2026&mes=10&de=2026-09-25`,
    );

    fireEvent.change(screen.getByLabelText("Data final"), {
      target: { value: "2026-09-30" },
    });
    expect(push).toHaveBeenLastCalledWith(
      `${PATH}?ano=2026&mes=10&ate=2026-09-30`,
    );
  });

  it("um colaborador do link fora da fila continua selecionado", () => {
    const outro = "44444444-4444-4444-8444-444444444444";
    montar({ ...FILTERS, employeeId: outro });

    expect(screen.getByLabelText("Colaborador")).toHaveValue(outro);
    expect(
      screen.getByRole("option", { name: "Colaborador do link" }),
    ).toBeInTheDocument();
  });

  it("limpar o recorte mantém a competência", () => {
    montar({ ...FILTERS, unitId: NORTE, from: "2026-09-25" });

    expect(
      screen.getByRole("link", { name: "Limpar recorte" }),
    ).toHaveAttribute("href", `${PATH}?ano=2026&mes=10`);
  });
});
