import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DryRun } from "@/components/assistente/dry-run";
import { ApiError } from "@/lib/api";
import type { StreamOptions } from "@/lib/assistente/stream";

const testAssistant = vi.fn();

vi.mock("@/lib/assistente/config", async () => {
  const actual = await vi.importActual<
    typeof import("@/lib/assistente/config")
  >("@/lib/assistente/config");
  return {
    ...actual,
    testAssistant: (...args: unknown[]) => testAssistant(...args),
  };
});

/** Um turno inteiro, na ordem em que o backend o emite. */
function stream(...events: unknown[]) {
  return async (
    _question: string,
    _useDraft: boolean,
    options: StreamOptions,
  ) => {
    for (const event of events) {
      options.onEvent(event as never);
    }
  };
}

const METRIC = {
  type: "metrica",
  codigo: "zz_desvios_total",
  titulo: "Total de desvios",
  parametros: { start_date: "01/09/2026", end_date: "18/09/2026" },
  ignorados: ["unit"],
  linhas: 1,
};

const DONE = {
  type: "done",
  consulta_id: "zz-consulta",
  modelo: "zz-modelo",
  tokens_entrada: 900,
  tokens_saida: 100,
  latencia_ms: 2400,
};

const REAL_DATA = "O teste consulta dados reais, com as suas permissões.";

function pergunta() {
  return screen.getByLabelText("Pergunta");
}

function testar() {
  return screen.getByRole("button", { name: "Testar" });
}

function usarRascunho() {
  return screen.getByRole("checkbox", {
    name: "Usar o rascunho em vez da versão no ar",
  });
}

beforeEach(() => {
  testAssistant.mockReset();
});

describe("gate 2 — a frase fixa e a ausência de seletor de papel", () => {
  it("⛔ a frase está na tela, literal, antes de qualquer teste", () => {
    render(<DryRun hasDraft />);

    expect(screen.getByText(REAL_DATA)).toBeVisible();
  });

  it("⛔ e continua na tela depois de um turno inteiro — ela não é um aviso que some", async () => {
    const user = userEvent.setup();
    testAssistant.mockImplementation(
      stream(METRIC, { type: "token", content: "Foram 42." }, DONE),
    );
    render(<DryRun hasDraft />);

    await user.type(pergunta(), "Quantos desvios?");
    await user.click(testar());

    expect(await screen.findByText("Foram 42.")).toBeVisible();
    expect(screen.getByText(REAL_DATA)).toBeVisible();
  });

  it("⛔ NENHUM seletor de papel: sem combobox, sem radio, e nenhum texto de papel ou perfil", () => {
    render(<DryRun hasDraft />);

    const painel = screen.getByRole("region", { name: /Testar o assistente/ });

    expect(within(painel).queryByRole("combobox")).toBeNull();
    expect(within(painel).queryByRole("radio")).toBeNull();
    expect(within(painel).queryByRole("listbox")).toBeNull();
    expect(painel.querySelector("select")).toBeNull();

    // A ausência, também pelo texto: "ver como supervisor" é o recurso que a
    // SPEC §5 proíbe, e ele não entra nem como rótulo.
    for (const proibido of [
      /como supervisor/i,
      /\bpapel\b/i,
      /\bperfil\b/i,
      /ver como/i,
    ]) {
      expect(within(painel).queryByText(proibido)).toBeNull();
    }
  });

  it("⛔ a ausência vale depois do turno também — nada de seletor aparecer com a resposta", async () => {
    const user = userEvent.setup();
    testAssistant.mockImplementation(stream(METRIC, DONE));
    render(<DryRun hasDraft />);

    await user.type(pergunta(), "Quantos desvios?");
    await user.click(testar());

    await screen.findByText("Total de desvios");
    const painel = screen.getByRole("region", { name: /Testar o assistente/ });
    expect(within(painel).queryByRole("combobox")).toBeNull();
    expect(within(painel).queryByRole("radio")).toBeNull();
  });

  it("a aba diz onde se responde 'o que outra pessoa alcança' — nas Capacidades, não executando como ela", () => {
    render(<DryRun hasDraft />);

    expect(
      screen.getByText(
        "O teste roda sempre como você. O que cada pessoa alcança está na aba Capacidades.",
      ),
    ).toBeVisible();
  });
});

describe("o turno", () => {
  it("✅ `metrica` + `done` renderizam período, filtros ignorados e o custo", async () => {
    const user = userEvent.setup();
    testAssistant.mockImplementation(
      stream(METRIC, { type: "token", content: "Foram 42 desvios." }, DONE),
    );
    render(<DryRun hasDraft />);

    await user.type(pergunta(), "Quantos desvios em setembro?");
    await user.click(testar());

    expect(await screen.findByText("Total de desvios")).toBeVisible();
    expect(screen.getByText("01/09/2026")).toBeVisible();
    expect(screen.getByText("18/09/2026")).toBeVisible();
    // O filtro pedido e não aplicado é dito: é a diferença entre o número
    // certo e a frase errada.
    expect(screen.getByText("sem filtro de unidade")).toBeVisible();
    expect(screen.getByText("Foram 42 desvios.")).toBeVisible();
    expect(screen.getByText(/zz-modelo · 1000 tokens · 2.4s/)).toBeVisible();
  });

  it("a recusa é resposta, e chega sem virar erro", async () => {
    const user = userEvent.setup();
    testAssistant.mockImplementation(
      stream({
        type: "recusa",
        codigo: "sem_metrica",
        motivo: "Não tenho essa métrica no catálogo.",
      }),
    );
    render(<DryRun hasDraft />);

    await user.type(pergunta(), "Quanto cada um ganha?");
    await user.click(testar());

    expect(
      await screen.findByText("Não tenho essa métrica no catálogo."),
    ).toBeVisible();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("⛔ `error` no meio do stream mostra a mensagem que veio", async () => {
    const user = userEvent.setup();
    testAssistant.mockImplementation(
      stream({ type: "error", message: "O provedor não respondeu." }),
    );
    render(<DryRun hasDraft />);

    await user.type(pergunta(), "Quantos desvios?");
    await user.click(testar());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "O provedor não respondeu.",
    );
  });

  it("erro antes do primeiro byte (403 no rascunho) mostra o `detail`", async () => {
    const user = userEvent.setup();
    testAssistant.mockRejectedValue(
      new ApiError(403, "Sem permissão para testar o rascunho."),
    );
    render(<DryRun hasDraft />);

    await user.type(pergunta(), "Quantos desvios?");
    await user.click(testar());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Sem permissão para testar o rascunho.",
    );
  });

  it("o rodapé diz que o teste não entra nas médias — é o `is_dry_run`", () => {
    render(<DryRun hasDraft />);

    expect(screen.getByText("Teste — não entra nas médias.")).toBeVisible();
  });
});

describe("o rascunho", () => {
  it("⛔ sem rascunho, o checkbox está desabilitado e a explicação está ao lado", () => {
    render(<DryRun hasDraft={false} />);

    expect(usarRascunho()).toBeDisabled();
    expect(
      screen.getByText("Não há rascunho salvo: o teste usa a versão no ar."),
    ).toBeVisible();
  });

  it("⛔ leitura falhada NÃO vira 'não há rascunho': a tela diz que não sabe", () => {
    // Os dois estados colapsavam em `false`, e só um deles é um fato. O
    // comportamento é o mesmo (falha fechada); a frase é que não pode mentir.
    render(<DryRun hasDraft={null} />);

    expect(usarRascunho()).toBeDisabled();
    expect(
      screen.getByText(
        "Não foi possível saber se há rascunho: o teste usa a versão no ar.",
      ),
    ).toBeVisible();
    expect(
      screen.queryByText("Não há rascunho salvo: o teste usa a versão no ar."),
    ).toBeNull();
  });

  it("com rascunho, o checkbox liga e `use_draft` viaja verdadeiro", async () => {
    const user = userEvent.setup();
    testAssistant.mockImplementation(stream(DONE));
    render(<DryRun hasDraft />);

    expect(usarRascunho()).toBeEnabled();
    expect(
      screen.queryByText("Não há rascunho salvo: o teste usa a versão no ar."),
    ).toBeNull();

    await user.click(usarRascunho());
    await user.type(pergunta(), "Quantos desvios?");
    await user.click(testar());

    expect(testAssistant).toHaveBeenCalledWith(
      "Quantos desvios?",
      true,
      expect.anything(),
    );
  });

  it("sem marcar, `use_draft` viaja falso — o padrão é a versão no ar", async () => {
    const user = userEvent.setup();
    testAssistant.mockImplementation(stream(DONE));
    render(<DryRun hasDraft />);

    await user.type(pergunta(), "Quantos desvios?");
    await user.click(testar());

    expect(testAssistant).toHaveBeenCalledWith(
      "Quantos desvios?",
      false,
      expect.anything(),
    );
  });

  it("⛔ o turno guarda contra qual texto rodou: desmarcar depois não reetiqueta a resposta antiga", async () => {
    const user = userEvent.setup();
    testAssistant.mockImplementation(stream(DONE));
    render(<DryRun hasDraft />);

    await user.click(usarRascunho());
    await user.type(pergunta(), "Primeira");
    await user.click(testar());
    await screen.findByText("Rascunho");

    await user.click(usarRascunho());
    await user.type(pergunta(), "Segunda");
    await user.click(testar());

    const turnos = within(screen.getByRole("list", { name: "Testes" }));
    await within(turnos.getAllByRole("listitem")[1]).findByText("Versão no ar");
    // O primeiro continua dizendo "Rascunho": é o que ele de fato rodou.
    expect(
      within(turnos.getAllByRole("listitem")[0]).getByText("Rascunho"),
    ).toBeVisible();
  });
});
