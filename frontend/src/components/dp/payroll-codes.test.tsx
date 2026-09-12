import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PayrollCodes } from "@/components/dp/payroll-codes";
import type { PayrollCodeList, PayrollCodeRow } from "@/lib/dp/queries";

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

function rubrica(overrides: Partial<PayrollCodeRow>): PayrollCodeRow {
  return {
    code: "0001",
    label: "SALARIO BASE",
    nature: "earning",
    category: null,
    validated: false,
    validated_at: null,
    in_payroll: true,
    ...overrides,
  };
}

/**
 * Quatro códigos, um em cada estado: pendente (usado, sem categoria), proposto
 * (categoria sem aval), conferido, e fora da folha sem categoria.
 */
function tela(overrides: Partial<PayrollCodeList> = {}): PayrollCodeList {
  return {
    can_write: true,
    pending: 1,
    rows: [
      rubrica({ code: "0001", label: "SALARIO BASE" }),
      rubrica({
        code: "0050",
        label: "H.EXTRA 60%",
        category: "overtime",
      }),
      rubrica({
        code: "0900",
        label: "INSS",
        nature: "deduction",
        category: "deduction",
        validated: true,
        validated_at: "2026-09-08T14:30:00Z",
      }),
      rubrica({
        code: "0777",
        label: null,
        nature: null,
        in_payroll: false,
      }),
    ],
    ...overrides,
  };
}

/** O código aparece duas vezes quando o rótulo é nulo; a primeira é a coluna. */
function linha(codigo: string) {
  return screen.getAllByText(codigo)[0].closest("tr") as HTMLTableRowElement;
}

beforeEach(() => {
  request.mockReset();
  refresh.mockReset();
});

describe("o cabeçalho é a afirmação de completude, e vem da API", () => {
  it("mostra o `pending` como veio, sem recalcular", () => {
    // A lista tem 1 pendência de verdade; o número passado é 7 de propósito.
    // Se a tela contasse as linhas, mostraria 1 — e o teste pegaria.
    render(<PayrollCodes screen={tela({ pending: 7 })} />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "7 códigos usados pela folha sem categoria",
    );
  });

  it("zero pendências com linhas é 'sem pendência' explícito", () => {
    render(<PayrollCodes screen={tela({ pending: 0 })} />);

    expect(screen.getByRole("status")).toHaveTextContent("Sem pendência");
    expect(screen.getByText("0001")).toBeInTheDocument();
  });

  it("singular para uma pendência", () => {
    render(<PayrollCodes screen={tela({ pending: 1 })} />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "1 código usado pela folha sem categoria",
    );
  });
});

describe("a lista", () => {
  it("mostra código, rótulo, natureza e a categoria em pt-BR", () => {
    render(<PayrollCodes screen={tela()} />);

    const salario = linha("0001");
    expect(within(salario).getByText("SALARIO BASE")).toBeInTheDocument();
    expect(within(salario).getByText("Provento")).toBeInTheDocument();
    expect(
      within(linha("0900")).getByLabelText("Categoria de 0900"),
    ).toHaveValue("deduction");
  });

  it("rótulo nulo mostra o código no lugar", () => {
    render(<PayrollCodes screen={tela()} />);

    // Duas vezes: na coluna de código e na de rótulo.
    expect(within(linha("0777")).getAllByText("0777")).toHaveLength(2);
  });

  it("⛔ `overtime` nunca aparece como 'hora extra'", () => {
    render(<PayrollCodes screen={tela()} />);

    expect(screen.queryByText(/hora\s*extra/i)).toBeNull();
    expect(
      within(screen.getByLabelText("Categoria de 0050")).getByRole("option", {
        name: "Horas adicionais",
      }),
    ).toBeInTheDocument();
  });

  it("pendente é só o código que a folha usa sem categoria", () => {
    render(<PayrollCodes screen={tela()} />);

    expect(within(linha("0001")).getByText("Pendente")).toBeInTheDocument();
    expect(
      within(linha("0050")).getByText("proposta, sem aval"),
    ).toBeInTheDocument();
    expect(within(linha("0900")).getByText("Conferida")).toBeInTheDocument();
    expect(
      within(linha("0900")).getByText("em 08/09/2026"),
    ).toBeInTheDocument();
  });

  it("⛔ o aval das 21h30 é do dia em que foi dado, e não do dia seguinte", () => {
    // `validated_at` é `timestamptz`, e o que chega é UTC: 00h30 do dia 9 é
    // 21h30 do dia 8 em Brasília. Cortar a string ISO mostraria 09/09 para
    // quem conferiu no dia 8 — todo aval dado à noite nasceria com a data
    // errada, e a curadoria é justamente o registro de quem avalizou e quando.
    render(
      <PayrollCodes
        screen={tela({
          rows: [
            rubrica({
              code: "0900",
              label: "INSS",
              category: "deduction",
              validated: true,
              validated_at: "2026-09-09T00:30:00Z",
            }),
          ],
        })}
      />,
    );

    expect(
      within(linha("0900")).getByText("em 08/09/2026"),
    ).toBeInTheDocument();
  });

  it("código fora da folha é marcado e NÃO é pendente, mesmo sem categoria", () => {
    render(<PayrollCodes screen={tela()} />);

    const fora = linha("0777");
    expect(within(fora).getByText("fora da folha")).toBeInTheDocument();
    expect(within(fora).queryByText("Pendente")).toBeNull();
    // E o que está na folha continua marcado — o positivo do par.
    expect(within(linha("0001")).queryByText("fora da folha")).toBeNull();
  });

  it("lista vazia diz de onde os códigos vêm", () => {
    render(<PayrollCodes screen={tela({ rows: [], pending: 0 })} />);

    expect(screen.getByText("Nenhum código de rubrica")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("quem não escreve não vê controle nenhum — e quem escreve vê", () => {
  it("com can_write há select, Confirmar e Desfazer aval", () => {
    render(<PayrollCodes screen={tela()} />);

    expect(screen.getAllByRole("combobox")).toHaveLength(4);
    expect(screen.getAllByRole("button", { name: "Confirmar" })).toHaveLength(
      4,
    );
    expect(
      screen.getAllByRole("button", { name: "Desfazer aval" }),
    ).toHaveLength(1);
  });

  it("sem can_write, a categoria vira texto e os botões somem", () => {
    render(<PayrollCodes screen={tela({ can_write: false })} />);

    expect(screen.getByText("0001")).toBeInTheDocument();
    expect(
      within(linha("0050")).getByText("Horas adicionais"),
    ).toBeInTheDocument();

    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Confirmar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Desfazer aval" })).toBeNull();
  });

  it("resposta sem a chave vale como 'não pode', nunca como 'pode'", () => {
    const semChave = tela();
    delete (semChave as { can_write?: boolean }).can_write;

    render(<PayrollCodes screen={semChave} />);

    expect(screen.getByText("0001")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Confirmar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Desfazer aval" })).toBeNull();
  });
});

describe("curadoria: confirmar classifica e avaliza; desfazer só tira o aval", () => {
  it("escolher categoria e confirmar envia `{category, validated: true}` e relê", async () => {
    request.mockResolvedValue({});
    const user = userEvent.setup();
    render(<PayrollCodes screen={tela()} />);

    await user.selectOptions(
      screen.getByLabelText("Categoria de 0001"),
      "base_salary",
    );
    await user.click(
      within(linha("0001")).getByRole("button", { name: "Confirmar" }),
    );

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/dp/rubricas/0001", {
        method: "PATCH",
        body: { category: "base_salary", validated: true },
      }),
    );
    expect(refresh).toHaveBeenCalled();
  });

  it("confirmar a proposta sem trocar envia a categoria que já estava", async () => {
    request.mockResolvedValue({});
    const user = userEvent.setup();
    render(<PayrollCodes screen={tela()} />);

    await user.click(
      within(linha("0050")).getByRole("button", { name: "Confirmar" }),
    );

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/dp/rubricas/0050", {
        method: "PATCH",
        body: { category: "overtime", validated: true },
      }),
    );
  });

  it("⛔ sem categoria não envia nada, e diz o que falta", async () => {
    const user = userEvent.setup();
    render(<PayrollCodes screen={tela()} />);

    await user.click(
      within(linha("0001")).getByRole("button", { name: "Confirmar" }),
    );

    expect(
      await screen.findByText(
        "Escolha a categoria de 0001 antes de confirmar.",
      ),
    ).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("desfazer aval envia a MESMA categoria com `validated: false` — não apaga", async () => {
    request.mockResolvedValue({});
    const user = userEvent.setup();
    render(<PayrollCodes screen={tela()} />);

    await user.click(screen.getByRole("button", { name: "Desfazer aval" }));

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/dp/rubricas/0900", {
        method: "PATCH",
        body: { category: "deduction", validated: false },
      }),
    );
    expect(refresh).toHaveBeenCalled();
    expect(request).not.toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("404 mostra a frase da API", async () => {
    const { ApiError } = await import("@/lib/api");
    request.mockRejectedValue(new ApiError(404, "Código 0050 não existe."));
    const user = userEvent.setup();
    render(<PayrollCodes screen={tela()} />);

    await user.click(
      within(linha("0050")).getByRole("button", { name: "Confirmar" }),
    );

    expect(
      await screen.findByText("Código 0050 não existe."),
    ).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("erro sem detalhe diz que nada foi alterado", async () => {
    const { ApiError } = await import("@/lib/api");
    request.mockRejectedValue(new ApiError(500, null));
    const user = userEvent.setup();
    render(<PayrollCodes screen={tela()} />);

    await user.click(
      within(linha("0050")).getByRole("button", { name: "Confirmar" }),
    );

    expect(
      await screen.findByText(
        "Não consegui gravar a rubrica. Nada foi alterado.",
      ),
    ).toBeInTheDocument();
  });

  it("o código vai codificado na rota", async () => {
    request.mockResolvedValue({});
    const user = userEvent.setup();
    render(
      <PayrollCodes
        screen={tela({
          rows: [rubrica({ code: "A/B 1", category: "other" })],
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(
        "/dp/rubricas/A%2FB%201",
        expect.anything(),
      ),
    );
  });
});
