import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PayrollImport } from "@/components/folha/payroll-import";

const upload = vi.fn();
const post = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    uploadApiAsUser: (...args: unknown[]) => upload(...args),
    requestApiAsUser: (...args: unknown[]) => post(...args),
    downloadApiAsUser: vi.fn(),
  };
});

const IMPORT_ID = "77777777-7777-4777-8777-777777777777";

type Preview = Parameters<typeof previewLimpo>[0];

function previewLimpo(overrides: Record<string, unknown> = {}) {
  return {
    import_id: IMPORT_ID,
    period: "2026-08",
    layout_version: "folha-1",
    status: "validating",
    counts: { total: 3, ok: 3, error: 0 },
    unmapped_codes: ["H_EXTRA_60"],
    lines: [
      {
        line: 3,
        errors: [],
        warnings: [
          {
            code: "codigo_sem_categoria",
            message: "O código 'H_EXTRA_60' ainda não tem categoria mapeada.",
            column: "code",
          },
        ],
      },
    ],
    replaces: null,
    ...overrides,
  };
}

async function enviarArquivo(preview: Preview) {
  upload.mockResolvedValue(preview);
  const user = userEvent.setup();
  render(<PayrollImport />);

  await user.upload(
    screen.getByLabelText("Planilha da folha"),
    new File(["conteudo"], "folha.xlsx"),
  );
  await user.click(screen.getByRole("button", { name: "Conferir sem gravar" }));
  await screen.findByRole("heading", { name: "3. Preview" });

  return user;
}

beforeEach(() => {
  upload.mockReset();
  post.mockReset();
});

describe("preview da folha", () => {
  it("mostra a competência do arquivo, não a escolhida no seletor", async () => {
    await enviarArquivo(previewLimpo({ period: "2026-05" }));

    // A competência vale pelo que a aba de controle declara: quem baixou o
    // modelo de agosto e enviou o de maio precisa ver maio na tela.
    expect(screen.getByText("maio/2026")).toBeInTheDocument();
  });

  it("trata código sem categoria como pendência da curadoria, não como erro", async () => {
    await enviarArquivo(previewLimpo());

    expect(screen.getByText("H_EXTRA_60")).toBeInTheDocument();
    expect(
      screen.getByText(/só não aparecem nos indicadores por categoria/),
    ).toBeInTheDocument();
    // O aviso de código sem categoria é contado uma vez por código, e não vira
    // uma linha de tabela cada: a primeira importação tem o plano de contas
    // inteiro por mapear.
    expect(screen.queryByText("Avisos")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Gravar 3 linha(s)" }),
    ).toBeEnabled();
  });

  it("grava e devolve o que entrou", async () => {
    const user = await enviarArquivo(previewLimpo());
    post.mockResolvedValue({
      ...previewLimpo(),
      status: "processed",
      applied: 3,
      replaced: 0,
    });

    await user.click(screen.getByRole("button", { name: "Gravar 3 linha(s)" }));

    await screen.findByRole("heading", { name: "4. Resultado" });
    expect(post).toHaveBeenCalledWith(`/folha/imports/${IMPORT_ID}/confirm`, {
      method: "POST",
    });
    expect(
      screen.getByText(/3 lançamento\(s\) gravado\(s\)\./),
    ).toBeInTheDocument();
  });
});

describe("a folha não entra pela metade", () => {
  it("desabilita a confirmação com o motivo escrito, e não em silêncio", async () => {
    await enviarArquivo(
      previewLimpo({
        status: "validation_error",
        counts: { total: 3, ok: 2, error: 1 },
        unmapped_codes: [],
        lines: [
          {
            line: 4,
            errors: [
              {
                code: "colaborador_desconhecido",
                message: "Não encontrei a matrícula '9999'.",
                column: "employee_code",
              },
            ],
            warnings: [],
          },
        ],
      }),
    );

    expect(screen.getByRole("button", { name: /Gravar/ })).toBeDisabled();
    expect(
      screen.getByText(/A folha não é importada pela metade/),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Não encontrei a matrícula '9999'."),
    ).toBeInTheDocument();
  });
});

describe("reenvio da mesma competência", () => {
  it("diz que vai substituir, e quanto, antes de alguém clicar", async () => {
    await enviarArquivo(
      previewLimpo({
        replaces: { entries: 1234, imported_at: "2026-09-02T12:00:00Z" },
      }),
    );

    expect(
      screen.getByRole("button", { name: "Substituir 1234 lançamento(s)" }),
    ).toBeEnabled();
    // O aviso da substituição é texto corrido, não só o rótulo do botão.
    expect(screen.getByText("1234 lançamento(s)")).toBeInTheDocument();
    expect(screen.getByText(/não a soma dos enviados/)).toBeInTheDocument();
  });

  it("conta no resultado o que saiu no lugar do que entrou", async () => {
    const user = await enviarArquivo(
      previewLimpo({ replaces: { entries: 3, imported_at: null } }),
    );
    post.mockResolvedValue({
      ...previewLimpo(),
      status: "processed",
      applied: 3,
      replaced: 3,
    });

    await user.click(screen.getByRole("button", { name: /Substituir/ }));

    await waitFor(() =>
      expect(
        screen.getByText(/no lugar de 3 que estavam na competência/),
      ).toBeInTheDocument(),
    );
  });
});

describe("recusa do arquivo inteiro", () => {
  it("mostra a frase da API, que é a que diz o que fazer", async () => {
    const { ApiError } =
      await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
    upload.mockRejectedValue(
      new ApiError(
        409,
        "A competência 2026-08 está fechada e não recebe importação.",
      ),
    );
    const user = userEvent.setup();
    render(<PayrollImport />);

    await user.upload(
      screen.getByLabelText("Planilha da folha"),
      new File(["conteudo"], "folha.xlsx"),
    );
    await user.click(
      screen.getByRole("button", { name: "Conferir sem gravar" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A competência 2026-08 está fechada e não recebe importação.",
    );
    expect(
      screen.queryByRole("heading", { name: "3. Preview" }),
    ).not.toBeInTheDocument();
  });
});
