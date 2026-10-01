import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApprovalQueue } from "@/components/alcada/approval-queue";
import { ApiError } from "@/lib/api";
import {
  REVIEW_ERROR_MESSAGE,
  type ApprovalQueueRow,
} from "@/lib/alcada/review";

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

const MARIA = "11111111-1111-4111-8111-111111111111";
const JOAO = "22222222-2222-4222-8222-222222222222";
const ANA = "33333333-3333-4333-8333-333333333333";

function linha(overrides: Partial<ApprovalQueueRow>): ApprovalQueueRow {
  return {
    justification_id: MARIA,
    employee_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    employee_name: "Maria Souza",
    unit_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
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
    ...overrides,
  };
}

const FILA: ApprovalQueueRow[] = [
  linha({}),
  linha({
    justification_id: JOAO,
    employee_name: "João Lima",
    type_description: "Atraso na entrada",
    minutes: 20,
    can_review: false,
    blocked_reason: "own_justification",
  }),
  linha({
    justification_id: ANA,
    employee_name: "Ana Prado",
    can_review: false,
    blocked_reason: "owner_only",
  }),
];

function item(name: string) {
  return screen.getByRole("listitem", { name });
}

beforeEach(() => {
  request.mockReset();
  refresh.mockReset();
});

describe("a lista", () => {
  it("mostra colaborador, unidade, data, tipo, minutos, texto e autor", () => {
    render(<ApprovalQueue rows={FILA} />);

    const maria = item("Maria Souza");
    expect(within(maria).getByText("DEV Norte")).toBeVisible();
    expect(within(maria).getByText("24/09/2026")).toBeVisible();
    expect(within(maria).getByText("Saída antecipada")).toBeVisible();
    expect(within(maria).getByText("1h 15min")).toBeVisible();
    expect(
      within(maria).getByText(
        "Consulta médica com atestado entregue ao gestor.",
      ),
    ).toBeVisible();
    expect(within(maria).getByText(/Carlos Supervisor/)).toBeVisible();
    expect(
      screen.getByRole("heading", {
        name: "3 justificativas esperando revisão",
      }),
    ).toBeVisible();
  });

  it("⛔ nunca diz 'hora extra'", () => {
    const { container } = render(<ApprovalQueue rows={FILA} />);

    expect(container.textContent ?? "").not.toMatch(/hora extra/i);
  });

  it("fila vazia é estado próprio, não uma tabela sem linhas", () => {
    render(<ApprovalQueue rows={[]} />);

    expect(screen.getByText("Nada esperando revisão no recorte")).toBeVisible();
    expect(screen.queryByRole("list")).toBeNull();
  });
});

describe("item bloqueado", () => {
  it("⛔ a própria justificativa aparece sem botões e com o motivo", () => {
    render(<ApprovalQueue rows={FILA} />);

    const joao = item("João Lima");
    expect(within(joao).queryByRole("button")).toBeNull();
    expect(
      within(joao).getByText(
        "Você escreveu esta justificativa — outra pessoa do RH precisa revisá-la.",
      ),
    ).toBeVisible();
  });

  it("⛔ colaborador só do owner aparece sem botões e com o motivo", () => {
    render(<ApprovalQueue rows={FILA} />);

    const ana = item("Ana Prado");
    expect(within(ana).queryByRole("button")).toBeNull();
    expect(
      within(ana).getByText(
        "Este colaborador só pode ter justificativa revisada pelo owner.",
      ),
    ).toBeVisible();
  });

  it("✅ o item revisável tem os dois botões", () => {
    render(<ApprovalQueue rows={FILA} />);

    const maria = item("Maria Souza");
    expect(
      within(maria).getByRole("button", { name: "Aprovar" }),
    ).toBeVisible();
    expect(
      within(maria).getByRole("button", { name: "Reprovar" }),
    ).toBeVisible();
  });
});

describe("aprovar", () => {
  it("o primeiro clique só abre a confirmação, que nomeia a pessoa e o dia", async () => {
    const user = userEvent.setup();
    render(<ApprovalQueue rows={FILA} />);

    await user.click(
      within(item("Maria Souza")).getByRole("button", { name: "Aprovar" }),
    );

    expect(request).not.toHaveBeenCalled();
    const form = screen.getByRole("form", { name: "Confirmar aprovação" });
    expect(form).toHaveTextContent(
      "Aprovar a justificativa de Maria Souza em 24/09/2026?",
    );
    expect(form).toHaveTextContent("não pode ser desfeita");
  });

  it("✅ 201 tira o item da lista e recarrega a fila", async () => {
    request.mockResolvedValue({
      review_id: "r-1",
      justification_id: MARIA,
      decision: "approved",
    });
    const user = userEvent.setup();
    render(<ApprovalQueue rows={FILA} />);

    await user.click(
      within(item("Maria Souza")).getByRole("button", { name: "Aprovar" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Confirmar aprovação" }),
    );

    await waitFor(() =>
      expect(
        screen.queryByRole("listitem", { name: "Maria Souza" }),
      ).toBeNull(),
    );
    expect(request).toHaveBeenCalledWith(
      `/alcada/justificativas/${MARIA}/revisao`,
      { method: "POST", body: { decisao: "approved" } },
    );
    expect(refresh).toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Justificativa de Maria Souza aprovada.",
    );
    expect(
      screen.getByRole("heading", {
        name: "2 justificativas esperando revisão",
      }),
    ).toBeVisible();
  });

  it("cancelar volta aos botões sem enviar nada", async () => {
    const user = userEvent.setup();
    render(<ApprovalQueue rows={FILA} />);

    await user.click(
      within(item("Maria Souza")).getByRole("button", { name: "Aprovar" }),
    );
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(request).not.toHaveBeenCalled();
    expect(
      within(item("Maria Souza")).getByRole("button", { name: "Aprovar" }),
    ).toBeVisible();
  });
});

describe("reprovar", () => {
  async function abrirReprovacao() {
    const user = userEvent.setup();
    render(<ApprovalQueue rows={FILA} />);
    await user.click(
      within(item("Maria Souza")).getByRole("button", { name: "Reprovar" }),
    );
    return user;
  }

  it("⛔ sem motivo não sai da tela", async () => {
    const user = await abrirReprovacao();

    await user.type(screen.getByLabelText("Motivo da reprovação"), "   ");
    await user.click(
      screen.getByRole("button", { name: "Confirmar reprovação" }),
    );

    expect(request).not.toHaveBeenCalled();
    expect(
      await screen.findByText(
        "Para reprovar, escreva o motivo — é ele que o supervisor vai ler.",
      ),
    ).toBeVisible();
    expect(screen.getByLabelText("Motivo da reprovação")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("✅ com motivo, envia o motivo aparado e tira o item", async () => {
    request.mockResolvedValue({
      review_id: "r-2",
      justification_id: MARIA,
      decision: "rejected",
    });
    const user = await abrirReprovacao();

    await user.type(
      screen.getByLabelText("Motivo da reprovação"),
      "  Sem atestado.  ",
    );
    await user.click(
      screen.getByRole("button", { name: "Confirmar reprovação" }),
    );

    await waitFor(() =>
      expect(
        screen.queryByRole("listitem", { name: "Maria Souza" }),
      ).toBeNull(),
    );
    expect(request).toHaveBeenCalledWith(
      `/alcada/justificativas/${MARIA}/revisao`,
      {
        method: "POST",
        body: { decisao: "rejected", motivo: "Sem atestado." },
      },
    );
  });

  it("o 422 do backend é tratado mesmo com a validação do cliente", async () => {
    request.mockRejectedValue(new ApiError(422, "rejection_needs_reason"));
    const user = await abrirReprovacao();

    await user.type(screen.getByLabelText("Motivo da reprovação"), "x");
    await user.click(
      screen.getByRole("button", { name: "Confirmar reprovação" }),
    );

    expect(
      await screen.findByText(REVIEW_ERROR_MESSAGE.rejection_needs_reason),
    ).toBeVisible();
    expect(item("Maria Souza")).toBeVisible();
  });
});

describe("cada recusa tem a sua frase", () => {
  const CASOS: [string, number, boolean][] = [
    // [código, status, a linha sai da fila?]
    ["not_hr", 403, false],
    ["own_justification", 403, false],
    ["owner_only", 403, false],
    ["justification_not_found", 404, true],
    ["already_reviewed", 409, true],
    ["source_is_mirror", 409, true],
    ["not_pending", 409, true],
    ["no_open_period", 409, false],
    ["rejection_needs_reason", 422, false],
  ];

  it("os nove códigos estão mapeados, e nenhum repete a frase de outro", () => {
    const frases = CASOS.map(([code]) => REVIEW_ERROR_MESSAGE[code]);

    expect(frases.every(Boolean)).toBe(true);
    expect(new Set(frases).size).toBe(9);
    expect(frases.join(" ")).not.toMatch(/hora extra/i);
  });

  it.each(CASOS)("%s (%i)", async (code, status, sai) => {
    request.mockRejectedValue(new ApiError(status, code));
    const user = userEvent.setup();
    render(<ApprovalQueue rows={FILA} />);

    await user.click(
      within(item("Maria Souza")).getByRole("button", { name: "Reprovar" }),
    );
    await user.type(
      screen.getByLabelText("Motivo da reprovação"),
      "Sem atestado.",
    );
    await user.click(
      screen.getByRole("button", { name: "Confirmar reprovação" }),
    );

    // A recusa do motivo vai para o campo; as outras, para um alerta. Os
    // textos de bloqueio de outras linhas repetem duas frases, e é por isso
    // que a busca é pelo alerta e não pelo texto solto.
    if (code === "rejection_needs_reason") {
      expect(await screen.findByText(REVIEW_ERROR_MESSAGE[code])).toBeVisible();
    } else {
      expect(await screen.findByRole("alert")).toHaveTextContent(
        REVIEW_ERROR_MESSAGE[code],
      );
    }

    if (sai) {
      expect(
        screen.queryByRole("listitem", { name: "Maria Souza" }),
      ).toBeNull();
      expect(refresh).toHaveBeenCalled();
    } else {
      expect(item("Maria Souza")).toBeVisible();
      expect(refresh).not.toHaveBeenCalled();
    }
  });

  it("falha sem código (rede, 500) não inventa causa", async () => {
    request.mockRejectedValue(new TypeError("fetch failed"));
    const user = userEvent.setup();
    render(<ApprovalQueue rows={FILA} />);

    await user.click(
      within(item("Maria Souza")).getByRole("button", { name: "Aprovar" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Confirmar aprovação" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível registrar a revisão. Nada foi alterado",
    );
    expect(item("Maria Souza")).toBeVisible();
  });
});
