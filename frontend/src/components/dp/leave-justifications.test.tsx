import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LeaveJustifications } from "@/components/dp/leave-justifications";
import { ApiError } from "@/lib/api";
import type {
  LeaveJustificationList,
  LeaveJustificationRow,
} from "@/lib/dp/queries";

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

function justificativa(
  overrides: Partial<LeaveJustificationRow>,
): LeaveJustificationRow {
  return {
    justification: "FÉRIAS",
    occurrences: 43,
    first_leave: "2024-07-01",
    last_leave: "2026-09-20",
    category: null,
    validated: false,
    validated_at: null,
    notes: null,
    in_mirror: true,
    ...overrides,
  };
}

/**
 * As cinco do espelho de produção (medidas em 23/09/2026) mais uma que alguém
 * curou e o espelho não traz mais. Cada uma num estado: pendente, proposta,
 * validada, e fora do espelho.
 *
 * ⚠️ `ATESTED` e `ATEST M` são a MESMA coisa escrita de dois jeitos pela origem,
 * e continuam duas linhas: a chave é o que o Secullum oferece, e cada uma se
 * cura sozinha.
 */
function tela(overrides: Partial<LeaveJustificationList> = {}) {
  return {
    pending: 3,
    without_justification: 0,
    rows: [
      justificativa({}),
      justificativa({
        justification: "ATESTED",
        occurrences: 13,
        category: "leave_period",
        notes: "mesma coisa que ATEST M, truncado pela origem",
      }),
      justificativa({
        justification: "AFASTAD",
        occurrences: 2,
        first_leave: "2025-02-10",
        last_leave: "2025-03-01",
      }),
      justificativa({
        justification: "ATEST M",
        occurrences: 5,
        category: "leave_period",
        validated: true,
        validated_at: "2026-09-23T14:30:00Z",
      }),
      justificativa({
        justification: "FALTA",
        occurrences: 1,
        first_leave: "2026-03-11",
        last_leave: "2026-03-11",
        category: "unjustified_absence",
        validated: true,
        validated_at: "2026-09-23T14:31:00Z",
      }),
      justificativa({
        justification: "LICENCA",
        occurrences: 0,
        first_leave: null,
        last_leave: null,
        category: "leave_of_absence",
        validated: true,
        validated_at: "2026-09-10T12:00:00Z",
        in_mirror: false,
      }),
    ],
    ...overrides,
  } satisfies LeaveJustificationList;
}

function linha(chave: string) {
  return screen.getByText(chave).closest("tr") as HTMLTableRowElement;
}

function salvar(chave: string) {
  return within(linha(chave)).getByRole("button", {
    name: "Salvar classificação",
  });
}

beforeEach(() => {
  request.mockReset();
  refresh.mockReset();
});

describe("os dois números, e nenhum deles é recalculado aqui", () => {
  it("⛔ 'sem pendência' não é dito sozinho: o afastamento sem nome trava igual", () => {
    // O falso verde desta tela. A fila pode estar inteira curada e a competência
    // continuar recusando porque o Secullum mandou afastamento sem justificativa
    // nenhuma — e nessa não há o que classificar.
    render(
      <LeaveJustifications
        screen={tela({ pending: 0, without_justification: 2 })}
      />,
    );

    const numeros = screen.getAllByRole("status");
    expect(numeros[0]).toHaveTextContent("Sem pendência");
    expect(numeros[1]).toHaveTextContent("2 afastamentos sem nome");
    expect(
      screen.getByText(/a correção é na origem/, { exact: false }),
    ).toBeVisible();
  });

  it("a pendência vem da API, e o texto diz que provisória trava igual", () => {
    render(<LeaveJustifications screen={tela()} />);

    expect(screen.getAllByRole("status")[0]).toHaveTextContent(
      "3 justificativas sem aval",
    );
    expect(
      screen.getByText(/classificada provisória trava igual/, {
        exact: false,
      }),
    ).toBeVisible();
  });

  it("uma pendência só é singular, e nenhum afastamento sem nome tem frase própria", () => {
    render(
      <LeaveJustifications
        screen={tela({ pending: 1, without_justification: 0 })}
      />,
    );

    const numeros = screen.getAllByRole("status");
    expect(numeros[0]).toHaveTextContent("1 justificativa sem aval");
    expect(numeros[1]).toHaveTextContent("Nenhum afastamento");
  });

  it("fila vazia não diz 'liberado' — o número de cima é quem diz", () => {
    render(
      <LeaveJustifications
        screen={tela({ rows: [], pending: 0, without_justification: 4 })}
      />,
    );

    expect(
      screen.getByText("Nenhuma justificativa para classificar"),
    ).toBeVisible();
    expect(screen.getAllByRole("status")[1]).toHaveTextContent(
      "4 afastamentos sem nome",
    );
  });
});

describe("a string é a chave, e a tela não a conserta", () => {
  it("mostra o truncamento da origem como ele é, e a chave vai no corpo", async () => {
    render(<LeaveJustifications screen={tela()} />);

    expect(screen.getByText("ATEST M")).toBeVisible();
    expect(screen.getByText("AFASTAD")).toBeVisible();
    // O acento preservado: `FÉRIAS` e `FERIAS` seriam duas curadorias.
    expect(screen.getByText("FÉRIAS")).toBeVisible();

    await userEvent.selectOptions(
      within(linha("FÉRIAS")).getByLabelText("Categoria de FÉRIAS"),
      "vacation",
    );
    await userEvent.click(salvar("FÉRIAS"));

    await waitFor(() => expect(request).toHaveBeenCalled());
    const [path, init] = request.mock.calls[0] as [
      string,
      { method: string; body: Record<string, unknown> },
    ];
    expect(path).toBe("/dp/justificativas/classificar");
    expect(init.method).toBe("POST");
    expect(init.body.justification).toBe("FÉRIAS");
  });

  it("a curada que o espelho não traz mais fica na lista, marcada e sem contagem", () => {
    render(<LeaveJustifications screen={tela()} />);

    const fora = linha("LICENCA");
    expect(within(fora).getByText("fora do espelho")).toBeVisible();
    // Zero ocorrência é travessão, e não `0`: ela não é trabalho pendente.
    expect(within(fora).queryByText("0")).toBeNull();
    expect(within(fora).getByText("Validada")).toBeVisible();
  });
});

describe("classificar manda a linha inteira — a nota não se perde no caminho", () => {
  it("⛔ reclassificar reenvia a nota que está na tela", async () => {
    // O backend grava o que chega: reclassificar sem `notes` APAGA a nota
    // anterior, e a trilha só guarda o "antes". O campo nasce da linha por isso.
    render(<LeaveJustifications screen={tela()} />);

    await userEvent.selectOptions(
      within(linha("ATESTED")).getByLabelText("Categoria de ATESTED"),
      "leave_of_absence",
    );
    await userEvent.click(salvar("ATESTED"));

    await waitFor(() => expect(request).toHaveBeenCalled());
    const [, init] = request.mock.calls[0] as [
      string,
      { body: Record<string, unknown> },
    ];
    expect(init.body).toEqual({
      justification: "ATESTED",
      category: "leave_of_absence",
      notes: "mesma coisa que ATEST M, truncado pela origem",
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("nota em branco vira null, e não string vazia", async () => {
    render(<LeaveJustifications screen={tela()} />);

    await userEvent.selectOptions(
      within(linha("FÉRIAS")).getByLabelText("Categoria de FÉRIAS"),
      "vacation",
    );
    await userEvent.type(
      within(linha("FÉRIAS")).getByLabelText("Nota de FÉRIAS"),
      "   ",
    );
    await userEvent.click(salvar("FÉRIAS"));

    await waitFor(() => expect(request).toHaveBeenCalled());
    const [, init] = request.mock.calls[0] as [
      string,
      { body: Record<string, unknown> },
    ];
    expect(init.body).toEqual({
      justification: "FÉRIAS",
      category: "vacation",
      notes: null,
    });
  });

  it("nota sem categoria é recusada aqui, nomeando a string, e nada é enviado", async () => {
    render(<LeaveJustifications screen={tela()} />);

    await userEvent.type(
      within(linha("AFASTAD")).getByLabelText("Nota de AFASTAD"),
      "conferir com o RH",
    );
    await userEvent.click(salvar("AFASTAD"));

    expect(
      screen.getByText("Escolha a categoria de «AFASTAD» antes de salvar."),
    ).toBeVisible();
    expect(request).not.toHaveBeenCalled();
  });

  it("⛔ sem nada mudado não há o que salvar — o clique inócuo derrubaria o aval", () => {
    // Toda gravação zera `validated_at`. Um "Salvar" habilitado numa linha
    // validada e intocada seria um botão que só pode piorar a situação.
    render(<LeaveJustifications screen={tela()} />);

    expect(salvar("ATEST M")).toBeDisabled();
    expect(salvar("FÉRIAS")).toBeDisabled();
  });

  it("e quando há o que salvar numa linha validada, a tela diz o que custa", async () => {
    render(<LeaveJustifications screen={tela()} />);

    await userEvent.type(
      within(linha("ATEST M")).getByLabelText("Nota de ATEST M"),
      "igual a ATESTED",
    );

    expect(salvar("ATEST M")).toBeEnabled();
    expect(
      within(linha("ATEST M")).getByText("salvar derruba o aval"),
    ).toBeVisible();
  });

  it("a recusa da API é a frase da API — 404 da chave que não existe mais", async () => {
    render(<LeaveJustifications screen={tela()} />);
    request.mockRejectedValue(
      new ApiError(
        404,
        "a justificativa «AFASTAD» não aparece nos afastamentos do Secullum nem na curadoria deste cliente",
      ),
    );

    await userEvent.selectOptions(
      within(linha("AFASTAD")).getByLabelText("Categoria de AFASTAD"),
      "leave_period",
    );
    await userEvent.click(salvar("AFASTAD"));

    expect(
      await screen.findByText(
        "a justificativa «AFASTAD» não aparece nos afastamentos do Secullum nem na curadoria deste cliente",
      ),
    ).toBeVisible();
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("validar é o outro ato, e ele não valida o que ninguém gravou", () => {
  it("não existe antes de classificar", () => {
    render(<LeaveJustifications screen={tela()} />);

    expect(
      within(linha("FÉRIAS")).queryByRole("button", { name: "Validar" }),
    ).toBeNull();
  });

  it("não existe depois de validada — o aval não se dá duas vezes", () => {
    render(<LeaveJustifications screen={tela()} />);

    expect(
      within(linha("FALTA")).queryByRole("button", { name: "Validar" }),
    ).toBeNull();
  });

  it("leva só a chave, e recarrega a fila", async () => {
    render(<LeaveJustifications screen={tela()} />);

    await userEvent.click(
      within(linha("ATESTED")).getByRole("button", { name: "Validar" }),
    );

    await waitFor(() => expect(request).toHaveBeenCalled());
    expect(request).toHaveBeenCalledWith("/dp/justificativas/validar", {
      method: "POST",
      body: { justification: "ATESTED" },
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("⛔ com edição não salva o botão sai da tela, e a tela diz por quê", async () => {
    // `POST /validar` leva só a chave: quem prende a categoria é o backend, com
    // a que ELE leu. O botão ao lado de um `select` mexido ofereceria um aval
    // sobre a categoria que ninguém gravou.
    render(<LeaveJustifications screen={tela()} />);

    await userEvent.selectOptions(
      within(linha("ATESTED")).getByLabelText("Categoria de ATESTED"),
      "suspension",
    );

    expect(
      within(linha("ATESTED")).queryByRole("button", { name: "Validar" }),
    ).toBeNull();
    expect(
      within(linha("ATESTED")).getByText("salve antes de validar"),
    ).toBeVisible();
  });

  it("⛔ 422 mostra a recusa E recarrega a fila — a categoria mudou debaixo de quem conferia", async () => {
    render(<LeaveJustifications screen={tela()} />);
    request.mockRejectedValue(
      new ApiError(
        422,
        "a classificação de «ATESTED» mudou enquanto você conferia; recarregue a fila e confira a categoria nova antes de validar",
      ),
    );

    await userEvent.click(
      within(linha("ATESTED")).getByRole("button", { name: "Validar" }),
    );

    expect(
      await screen.findByText(
        "a classificação de «ATESTED» mudou enquanto você conferia; recarregue a fila e confira a categoria nova antes de validar",
      ),
    ).toBeVisible();
    // A frase manda recarregar; a tela recarrega em vez de repassar a tarefa.
    expect(refresh).toHaveBeenCalled();
  });

  it("falha sem detail não inventa causa, e não recarrega", async () => {
    render(<LeaveJustifications screen={tela()} />);
    request.mockRejectedValue(new Error("rede"));

    await userEvent.click(
      within(linha("ATESTED")).getByRole("button", { name: "Validar" }),
    );

    expect(
      await screen.findByText(
        "Não consegui registrar o aval. Nada foi alterado.",
      ),
    ).toBeVisible();
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("a nota é permanente, e o campo diz isso", () => {
  it("⛔ o aviso está ligado a cada campo, e nomeia o que a regra 10 proíbe", () => {
    render(<LeaveJustifications screen={tela()} />);

    const campo = within(linha("FÉRIAS")).getByLabelText("Nota de FÉRIAS");
    const avisoId = campo.getAttribute("aria-describedby");
    expect(avisoId).toBeTruthy();

    const aviso = document.getElementById(avisoId as string);
    expect(aviso).not.toBeNull();
    expect(aviso).toHaveTextContent(/trilha de auditoria/);
    expect(aviso).toHaveTextContent(/nunca diagnóstico, CID ou restrição/);
  });

  it("o campo respeita o teto de 500 do schema de entrada", () => {
    render(<LeaveJustifications screen={tela()} />);

    expect(
      within(linha("FÉRIAS")).getByLabelText("Nota de FÉRIAS"),
    ).toHaveAttribute("maxLength", "500");
  });
});

describe("as cinco categorias, e as cinco vêm do `check` da tabela", () => {
  it("o select oferece as cinco e mais 'sem categoria'", () => {
    render(<LeaveJustifications screen={tela()} />);

    const opcoes = within(
      within(linha("FÉRIAS")).getByLabelText("Categoria de FÉRIAS"),
    ).getAllByRole("option");

    expect(opcoes.map((opcao) => opcao.textContent)).toEqual([
      "— sem categoria —",
      "Férias",
      "Afastamento",
      "Licença",
      "Suspensão",
      "Falta injustificada",
    ]);
  });
});
