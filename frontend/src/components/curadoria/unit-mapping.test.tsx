import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { UnitMapping } from "@/components/curadoria/unit-mapping";
import type { UnitMappingScreen } from "@/lib/curadoria/queries";

const post = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, requestApiAsUser: (...args: unknown[]) => post(...args) };
});

const UNIT_A = "55555555-5555-4555-8555-555555555551";
const UNIT_B = "55555555-5555-4555-8555-555555555552";

function screenData(
  overrides: Partial<UnitMappingScreen> = {},
): UnitMappingScreen {
  return {
    active: 40,
    validated: 22,
    provisional: 6,
    without_unit: 12,
    units: [
      {
        unit_id: UNIT_A,
        code: "AER01",
        name: "Aeroporto 01",
        company_id: "c1",
        company_name: "FastPark Norte",
      },
      {
        unit_id: UNIT_B,
        code: "SHN",
        name: "Shopping Norte",
        company_id: "c1",
        company_name: "FastPark Norte",
      },
    ],
    rows: [
      {
        secullum_department_id: 101,
        department: "Estac. AEROPORTO-01",
        company_id: "c1",
        company_name: "FastPark Norte",
        employees: 12,
        unmapped: 12,
        unit_id: null,
        unit_name: null,
        validated_at: null,
        suggestion: {
          unit_id: UNIT_A,
          unit_name: "Aeroporto 01",
          confidence: 80,
        },
      },
      {
        secullum_department_id: 102,
        department: "Manutenção",
        company_id: "c1",
        company_name: "FastPark Norte",
        employees: 3,
        unmapped: 3,
        unit_id: null,
        unit_name: null,
        validated_at: null,
        suggestion: {
          unit_id: UNIT_B,
          unit_name: "Shopping Norte",
          confidence: 55,
        },
      },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({ validated: 1, employees_allocated: 12 });
});

describe("UnitMapping", () => {
  it("o lote diz quantas linhas alcança antes de ser apertado", async () => {
    // "Aplicar tudo" é assinar embaixo de quarenta palpites. Com o número no
    // botão, a pessoa vê o tamanho da decisão antes de tomá-la.
    render(<UnitMapping screen={screenData()} />);

    expect(
      screen.getByRole("button", { name: /Aplicar 1 sugestão ≥ 80%/ }),
    ).toBeEnabled();
  });

  it("baixar o limiar aumenta o alcance do lote", () => {
    render(<UnitMapping screen={screenData()} />);

    fireEvent.change(screen.getByLabelText("Confiança mínima"), {
      target: { value: "50" },
    });

    expect(
      screen.getByRole("button", { name: /Aplicar 2 sugestões ≥ 50%/ }),
    ).toBeEnabled();
  });

  it("o lote manda uma requisição só, com os pares dentro", async () => {
    // Quarenta requisições fariam metade da decisão sobreviver a uma queda de
    // rede, e a outra metade voltaria para a fila sem ninguém saber qual.
    const user = userEvent.setup();
    render(<UnitMapping screen={screenData()} />);

    fireEvent.change(screen.getByLabelText("Confiança mínima"), {
      target: { value: "50" },
    });
    await user.click(screen.getByRole("button", { name: /Aplicar 2/ }));

    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][1].body).toEqual({
      mappings: [
        { secullum_department_id: 101, unit_id: UNIT_A },
        { secullum_department_id: 102, unit_id: UNIT_B },
      ],
    });
  });

  it("o lote nunca alcança o que já foi curado", async () => {
    const user = userEvent.setup();
    const data = screenData();
    data.rows[0].validated_at = "2026-08-20T12:00:00Z";
    data.rows[0].unit_id = UNIT_A;
    data.rows[0].suggestion = null;

    render(<UnitMapping screen={data} />);

    fireEvent.change(screen.getByLabelText("Confiança mínima"), {
      target: { value: "50" },
    });
    await user.click(screen.getByRole("button", { name: /Aplicar 1/ }));

    expect(post.mock.calls[0][1].body.mappings).toEqual([
      { secullum_department_id: 102, unit_id: UNIT_B },
    ]);
  });

  it("Enter no seletor confirma a linha em foco", async () => {
    // A fila é percorrida em rajada por uma pessoa só. Tirar a mão do teclado
    // quarenta vezes é o que faz a curadoria não ser terminada.
    const user = userEvent.setup();
    render(<UnitMapping screen={screenData()} />);

    const seletor = screen.getByLabelText("Unidade de Estac. AEROPORTO-01");
    seletor.focus();
    await user.keyboard("{Enter}");

    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][1].body.mappings).toEqual([
      { secullum_department_id: 101, unit_id: UNIT_A },
    ]);
  });

  it("o provisório aparece com nome próprio e fora do validado", () => {
    render(<UnitMapping screen={screenData()} />);

    expect(
      screen.getByText(
        (_, element) =>
          element?.textContent?.replace(/\s+/g, " ").trim() ===
          "22 de 40 ativos com unidade validada",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Provisório")).toBeInTheDocument();
    // 22 + 6 + 12 = 40: as três faixas fecham no efetivo, e a validada é só a
    // primeira. Somar validado com provisório levaria a barra ao fim cedo.
    expect(screen.getByText("6")).toBeInTheDocument();
  });

  it("a recusa do backend chega inteira, e nada é dado como salvo", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api");
    post.mockRejectedValue(
      new ApiError(
        422,
        "Departamento 101 ou unidade escolhida não pertencem a este cliente.",
      ),
    );

    render(<UnitMapping screen={screenData()} />);
    await user.click(screen.getByRole("button", { name: /Aplicar 1/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /não pertencem a este cliente/,
    );
    expect(screen.queryByRole("status")).toBeNull();
  });
});
