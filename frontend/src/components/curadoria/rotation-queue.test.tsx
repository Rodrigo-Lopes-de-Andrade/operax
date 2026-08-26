import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  RotationQueue,
  workload,
  type Draft,
} from "@/components/curadoria/rotation-queue";
import type { RotationScreen } from "@/lib/curadoria/queries";

const post = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, requestApiAsUser: (...args: unknown[]) => post(...args) };
});

function screenData(overrides: Partial<RotationScreen> = {}): RotationScreen {
  return {
    on_blank_schedule: 13,
    validated: 0,
    provisional: 0,
    rows: [
      {
        secullum_schedule_id: 9042,
        schedule: "U-042 - P01 - 19h as 7h - Impar",
        employees: 3,
        out_of_engine: 0,
        cycle_length_days: null,
        anchor_date: null,
        expected_entry: null,
        expected_exit: null,
        expected_break_minutes: null,
        workload_minutes: null,
        tolerance_extra_minutes: null,
        tolerance_absence_minutes: null,
        validated_at: null,
        observed_days: ["2026-08-10", "2026-08-12", "2026-08-14"],
      },
    ],
    ...overrides,
  };
}

function draft(overrides: Partial<Draft> = {}): Draft {
  return {
    cycle: 2,
    anchor: "2026-08-10",
    entry: "19:00",
    exit: "05:00",
    breakMinutes: 72,
    toleranceExtra: 10,
    toleranceAbsence: 5,
    ...overrides,
  };
}

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({ secullum_schedule_id: 9042, employees_covered: 3 });
});

describe("a carga é conta, e a virada de meia-noite entra nela", () => {
  it("19:00 às 05:00 com 1h12 de intervalo dá os 528 do Secullum", () => {
    // O número não é escolhido: é o `Carga` que `U-075 - P05` declara em
    // produção. Se a conta ignorasse a virada, daria negativo.
    expect(workload(draft())).toBe(528);
  });

  it("um turno de dia continua sendo subtração simples", () => {
    expect(
      workload(draft({ entry: "06:00", exit: "18:00", breakMinutes: 60 })),
    ).toBe(660);
  });

  it("sem entrada, saída ou dia trabalhado não há carga a declarar", () => {
    expect(workload(draft({ exit: "" }))).toBeNull();
    expect(workload(draft({ anchor: "" }))).toBeNull();
  });

  it("ciclo de um dia não é rotação, e a conta se recusa antes do botão", () => {
    expect(workload(draft({ cycle: 1 }))).toBeNull();
  });
});

describe("a tela mostra o que aconteceu e não conclui a escala", () => {
  it("os dias batidos aparecem, e clicar num deles preenche a âncora", async () => {
    const user = userEvent.setup();
    render(<RotationQueue screen={screenData()} />);

    const dia = screen.getByRole("button", { name: /12\/08/ });
    await user.click(dia);

    expect(
      screen.getByLabelText(
        "Dia trabalhado de U-042 - P01 - 19h as 7h - Impar",
      ),
    ).toHaveValue("2026-08-12");
  });

  it("não oferece âncora sugerida em lugar nenhum", () => {
    render(<RotationQueue screen={screenData()} />);

    // Escala derivada das batidas encaixa sempre, e escala que encaixa sempre
    // nunca produz "não bateu" nem "bateu na folga".
    expect(screen.queryByText(/sugest/i)).toBeNull();
    expect(
      screen.getByLabelText(
        "Dia trabalhado de U-042 - P01 - 19h as 7h - Impar",
      ),
    ).toHaveValue("");
  });

  it("sem marcação lida, diz que a âncora tem de vir de quem conhece a escala", () => {
    render(
      <RotationQueue
        screen={screenData({
          rows: [{ ...screenData().rows[0], observed_days: [] }],
        })}
      />,
    );

    expect(
      screen.getByText(/precisa vir de quem conhece a escala/),
    ).toBeTruthy();
  });
});

describe("o estado da linha", () => {
  it("provisória não conta como declarada", () => {
    render(
      <RotationQueue
        screen={screenData({
          validated: 0,
          provisional: 3,
          rows: [
            {
              ...screenData().rows[0],
              cycle_length_days: 2,
              anchor_date: "2026-08-10",
              validated_at: null,
            },
          ],
        })}
      />,
    );

    expect(screen.getByText("provisória")).toBeTruthy();
    expect(screen.queryByText("declarada")).toBeNull();
  });
});

describe("a gravação", () => {
  it("manda a carga calculada, e não um campo digitado", async () => {
    const user = userEvent.setup();
    render(
      <RotationQueue
        screen={screenData({
          rows: [
            {
              ...screenData().rows[0],
              cycle_length_days: 2,
              anchor_date: "2026-08-10",
              expected_entry: "19:00:00",
              expected_exit: "05:00:00",
              expected_break_minutes: 72,
              tolerance_extra_minutes: 10,
              tolerance_absence_minutes: 5,
            },
          ],
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Declarar escala" }));

    expect(post).toHaveBeenCalledWith("/curadoria/rotacoes", {
      method: "POST",
      body: {
        secullum_schedule_id: 9042,
        cycle_length_days: 2,
        anchor_date: "2026-08-10",
        expected_entry: "19:00",
        expected_exit: "05:00",
        expected_break_minutes: 72,
        workload_minutes: 528,
        tolerance_extra_minutes: 10,
        tolerance_absence_minutes: 5,
      },
    });
  });
});

describe("a outra resposta para um horário em branco", () => {
  it("oferece tirar do motor no mesmo cartão da escala", async () => {
    // Se a segunda resposta morasse noutra tela, ela nunca aconteceria e essa
    // gente ficaria em "sem escala" para sempre — sem indício e sem medição.
    const user = userEvent.setup();
    post.mockResolvedValue({
      secullum_schedule_id: 9042,
      employees_changed: 3,
    });
    render(<RotationQueue screen={screenData()} />);

    await user.click(
      screen.getByRole("button", { name: "não medir este horário" }),
    );

    expect(post).toHaveBeenCalledWith("/curadoria/fora-do-motor", {
      method: "POST",
      body: { secullum_schedule_id: 9042, exception_tracking: true },
    });
  });

  it("quando já estão fora, o convite vira o caminho de volta", () => {
    render(
      <RotationQueue
        screen={screenData({
          rows: [{ ...screenData().rows[0], out_of_engine: 3 }],
        })}
      />,
    );

    expect(screen.getByText(/3 de 3 já estão fora do motor/)).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "voltar a medir este horário" }),
    ).toBeTruthy();
  });
});
