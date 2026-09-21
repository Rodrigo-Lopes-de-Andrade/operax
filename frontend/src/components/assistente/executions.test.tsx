import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Executions } from "@/components/assistente/executions";
import type {
  AssistantCostByVersion,
  AssistantRun,
  AssistantTestCost,
} from "@/lib/assistente/config";
import type { ExecutionsResult } from "@/lib/assistente/queries";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

const V2 = "44444444-4444-4444-8444-444444444443";
const OUTRA = "44444444-4444-4444-8444-444444444499";

const TURNOS = "Turnos do assistente na janela";
const CUSTO = "Custo por competência, versão de prompt e modelo";

/** As três frases obrigatórias, letra por letra — cada uma saiu de uma medição. */
const UTC_NOTE =
  "Competências em UTC: um turno às 21h de 30/09 em São Paulo entra na competência de outubro.";
const MODEL_NOTE =
  "O mesmo texto pode ter rodado em modelos diferentes: o preço segue o modelo, e por isso cada linha traz o seu.";
const ROLLBACK_NOTE =
  "A coluna Versão soma os turnos de antes e depois de um rollback: voltar para uma versão e publicar de novo não separa as duas eras dela.";
const WINDOW_NOTE =
  "A janela é contada em semanas: a competência mais antiga começa no meio do mês e a atual ainda está acontecendo. Nenhuma das duas pontas é um mês fechado.";

function run(overrides: Partial<AssistantRun> = {}): AssistantRun {
  return {
    // 21h30 de 30/09 em São Paulo — e competência de OUTUBRO em UTC.
    created_at: "2026-10-01T00:30:00Z",
    question: "quantos desvios ontem?",
    metric_code: "deviations_total",
    rows_returned: 3,
    latency_ms: 500,
    input_tokens: 100,
    output_tokens: 20,
    model: "fake-1",
    refused: false,
    refusal_reason: null,
    prompt_version_id: V2,
    version_label: "v2",
    ...overrides,
  };
}

function cost(
  overrides: Partial<AssistantCostByVersion> = {},
): AssistantCostByVersion {
  return {
    month_start: "2026-10-01",
    version_label: "v2",
    prompt_version_id: V2,
    model: "gpt-5.4-mini",
    runs: 4,
    refused_runs: 1,
    input_tokens: 400,
    output_tokens: 90,
    avg_latency_ms: "275.5",
    ...overrides,
  };
}

const TESTE: AssistantTestCost = {
  month_start: "2026-10-01",
  runs: 12,
  input_tokens: 1998,
  output_tokens: 430,
};

function abrir(
  {
    runs = [run()],
    costs = [cost()],
    testCost = [TESTE],
  }: {
    runs?: AssistantRun[];
    costs?: AssistantCostByVersion[];
    testCost?: AssistantTestCost[];
  } = {},
  weeks = 8,
) {
  const result: ExecutionsResult = {
    status: "ok",
    screen: { runs, cost: costs, testCost },
  };

  return render(<Executions weeks={weeks} result={result} />);
}

function tabela(nome: string) {
  return within(screen.getByRole("table", { name: nome }));
}

describe("⛔ o rótulo da versão é renderizado como veio — o gate da etapa", () => {
  it('"antes do versionamento" aparece assim, e NUNCA como "v1"', () => {
    abrir({
      runs: [
        run({
          prompt_version_id: null,
          version_label: "antes do versionamento",
        }),
      ],
      costs: [
        cost({
          prompt_version_id: null,
          version_label: "antes do versionamento",
        }),
      ],
    });

    expect(
      tabela(CUSTO).getByText("antes do versionamento"),
    ).toBeInTheDocument();
    expect(
      tabela(TURNOS).getByText("antes do versionamento"),
    ).toBeInTheDocument();
    // ⛔ Atribuir a v1 a um turno sem versão é inventar procedência — o erro
    // que esta etapa inteira existe para não cometer.
    expect(screen.queryByText("v1")).toBeNull();
  });

  it('"versão fora do alcance" também aparece como veio, e não vira travessão', () => {
    // A FK de `ai_query` aceita versão de outro tenant de propósito (é log).
    // Sob invoker o join vem vazio, e o banco rotula. A tela não "conserta".
    abrir({
      runs: [
        run({
          prompt_version_id: OUTRA,
          version_label: "versão fora do alcance",
        }),
      ],
      costs: [
        cost({
          prompt_version_id: OUTRA,
          version_label: "versão fora do alcance",
        }),
      ],
    });

    expect(
      tabela(CUSTO).getByText("versão fora do alcance"),
    ).toBeInTheDocument();
    expect(
      tabela(TURNOS).getByText("versão fora do alcance"),
    ).toBeInTheDocument();
  });

  it('"plataforma v1" e "v2" passam inteiros, sem remontagem', () => {
    abrir({
      runs: [
        run({ version_label: "plataforma v1" }),
        run({ version_label: "v2" }),
      ],
    });

    expect(tabela(TURNOS).getByText("plataforma v1")).toBeInTheDocument();
    expect(tabela(TURNOS).getByText("v2")).toBeInTheDocument();
  });
});

describe("⛔ as frases obrigatórias da tabela de custo", () => {
  it("competências em UTC — um turno das 21h de 30/09 em São Paulo cai em outubro", () => {
    abrir();

    expect(screen.getByText(UTC_NOTE)).toBeVisible();
    // E a tela mostra as duas coisas de uma vez: o turno às 21h30 de 30/09 e
    // a competência de outubro. A frase é o que liga uma à outra.
    expect(tabela(TURNOS).getByText("30/09, 21:30")).toBeVisible();
    expect(tabela(CUSTO).getByText("outubro de 2026")).toBeVisible();
  });

  it("o modelo é parte da chave porque é ele que vira preço", () => {
    abrir();

    expect(screen.getByText(MODEL_NOTE)).toBeVisible();
  });

  it("a ressalva do rollback: a linha soma as duas eras da mesma versão", () => {
    abrir();

    expect(screen.getByText(ROLLBACK_NOTE)).toBeVisible();
  });

  it("a ponta da janela não é um mês fechado, e a tela diz isso", () => {
    // A janela é semanas e a competência é mês: a mais antiga começa no meio
    // do mês. Sem a frase, "agosto custou X" lê um mês parcial como inteiro.
    abrir();

    expect(screen.getByText(WINDOW_NOTE)).toBeVisible();
  });

  it("as quatro continuam na tela quando a janela está vazia", () => {
    // É quando elas mais importam: uma tabela vazia não explica nada sozinha.
    abrir({ runs: [], costs: [], testCost: [] });

    expect(screen.getByText(UTC_NOTE)).toBeVisible();
    expect(screen.getByText(MODEL_NOTE)).toBeVisible();
    expect(screen.getByText(ROLLBACK_NOTE)).toBeVisible();
    expect(screen.getByText(WINDOW_NOTE)).toBeVisible();
  });
});

describe("⛔ duas linhas com a mesma versão e modelos diferentes são duas linhas", () => {
  it("a tela não as soma — o preço segue o modelo", () => {
    abrir({
      costs: [
        cost({ model: "gpt-5.4-mini", runs: 4, input_tokens: 400 }),
        cost({ model: "gpt-5.4", runs: 1, input_tokens: 900 }),
      ],
    });

    const custo = tabela(CUSTO);

    expect(custo.getAllByText("v2")).toHaveLength(2);
    expect(custo.getByText("gpt-5.4-mini")).toBeInTheDocument();
    expect(custo.getByText("gpt-5.4")).toBeInTheDocument();
    expect(custo.getByText("400")).toBeInTheDocument();
    expect(custo.getByText("900")).toBeInTheDocument();
    // ⛔ 1.300 seria a soma dos dois preços sob um rótulo só, e 5 os turnos
    // dela: é exatamente o número que a decisão de 20/09 existe para impedir.
    expect(custo.queryByText("1.300")).toBeNull();
    expect(custo.queryByText("5")).toBeNull();
  });

  it("a latência média é a de cada modelo, não a mistura", () => {
    abrir({
      costs: [
        cost({ model: "gpt-5.4-mini", avg_latency_ms: "500" }),
        cost({ model: "gpt-5.4", avg_latency_ms: "50" }),
      ],
    });

    const custo = tabela(CUSTO);

    expect(custo.getByText("500 ms")).toBeInTheDocument();
    expect(custo.getByText("50 ms")).toBeInTheDocument();
    expect(custo.queryByText("275 ms")).toBeNull();
  });
});

describe("⛔ o total de teste é uma linha à parte, nunca uma linha da tabela", () => {
  it("aparece FORA da `<table>` de custo", () => {
    abrir();

    const total = screen.getByText(/Testes do período:/);

    expect(total).toBeVisible();
    // ⛔ Dentro da tabela, alguém soma as duas colunas sem perceber: uma é
    // tráfego, a outra é ajuste de prompt.
    expect(total.closest("table")).toBeNull();
    expect(tabela(CUSTO).queryByText(/Testes do período:/)).toBeNull();
  });

  it("traz turnos, entrada e saída, e diz que está fora de toda média", () => {
    abrir();

    expect(
      screen.getByText(
        /Testes do período: 12 turnos, 1\.998 tokens de entrada, 430 de saída\./,
      ),
    ).toBeVisible();
    expect(screen.getByText("Fora de toda média.")).toBeVisible();
  });

  it("⛔ com duas competências, o total é a SOMA — não a primeira linha", () => {
    // A janela é semanas e a competência é mês, então a função devolve uma
    // linha por competência e a janela quase sempre tem mais de uma. Um total
    // que lesse só `rows[0]` sub-reportava o gasto com a suíte verde.
    abrir({
      testCost: [
        TESTE,
        {
          month_start: "2026-09-01",
          runs: 3,
          input_tokens: 502,
          output_tokens: 70,
        },
      ],
    });

    expect(
      screen.getByText(
        /Testes do período: 15 turnos, 2\.500 tokens de entrada, 500 de saída\./,
      ),
    ).toBeVisible();
  });

  it("sem teste na janela, a linha diz isso em vez de sumir", () => {
    abrir({ testCost: [] });

    expect(
      screen.getByText(/Testes do período: nenhum turno de teste na janela\./),
    ).toBeVisible();
  });
});

describe("⛔ recusa é resposta válida, não erro", () => {
  it("a linha inteira fica visível, com o motivo ao lado", () => {
    abrir({
      runs: [
        run({
          refused: true,
          refusal_reason: "A métrica pedida não está no catálogo.",
          metric_code: null,
          rows_returned: null,
        }),
      ],
    });

    const turnos = tabela(TURNOS);

    expect(turnos.getByText("quantos desvios ontem?")).toBeVisible();
    expect(turnos.getByText("Recusa")).toBeVisible();
    expect(
      turnos.getByText("A métrica pedida não está no catálogo."),
    ).toBeVisible();
    // ⛔ E nada de estado de erro: recusa chega dentro de um 200.
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("a janela mora na query string", () => {
  it("cada opção é um link que troca `semanas=`", () => {
    abrir({}, 8);

    const seletor = within(
      screen.getByRole("group", { name: "Janela em semanas" }),
    );

    expect(seletor.getByRole("link", { name: "12 sem" })).toHaveAttribute(
      "href",
      "/dashboard/administracao/assistente?aba=execucoes&semanas=12",
    );
    // A janela aberta é a marcada, e o link dela carrega a própria semana: o
    // link copiado abre a mesma janela que a pessoa está vendo.
    expect(seletor.getByRole("link", { name: "8 sem" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(seletor.getByRole("link", { name: "8 sem" })).toHaveAttribute(
      "href",
      "/dashboard/administracao/assistente?aba=execucoes&semanas=8",
    );
  });

  it("as cinco opções estão lá", () => {
    abrir();

    const seletor = within(
      screen.getByRole("group", { name: "Janela em semanas" }),
    );

    expect(seletor.getAllByRole("link")).toHaveLength(5);
  });

  it("⛔ 422 vira frase, com o seletor ainda na tela para voltar", () => {
    render(<Executions weeks={99} result={{ status: "out_of_range" }} />);

    expect(
      screen.getByText(
        "A janela precisa estar entre 1 e 52 semanas. Escolha uma das opções acima.",
      ),
    ).toBeVisible();
    expect(
      screen.getByRole("group", { name: "Janela em semanas" }),
    ).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("a API fora do ar é estado, não tela branca", () => {
    render(<Executions weeks={8} result={{ status: "unavailable" }} />);

    expect(
      screen.getByText("As execuções não puderam ser lidas"),
    ).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("⛔ lista curta não é erro nem falta de permissão", () => {
  it("um turno só aparece, e a tela não fala em permissão", () => {
    // `ai_query_read` é própria-ou-admin: quem não administra vê os próprios
    // turnos. Esconder a aba, ou trocar a lista por um aviso de permissão,
    // seria a tela desmentindo a policy.
    abrir({ runs: [run({ question: "quantos desvios ontem?" })] });

    expect(
      tabela(TURNOS).getByText("quantos desvios ontem?"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Cada pessoa vê os próprios turnos; quem administra vê os do cliente. Lista curta não é erro.",
      ),
    ).toBeVisible();
    expect(screen.queryByText(/permiss/i)).toBeNull();
  });

  it("janela vazia é vazio, e diz a janela — não é erro", () => {
    abrir({ runs: [], costs: [], testCost: [] }, 4);

    expect(screen.getAllByText("A janela está vazia")).toHaveLength(2);
    expect(
      screen.getByText(/Nenhum turno do assistente nas últimas 4 semanas\./),
    ).toBeVisible();
    expect(screen.queryByText(/permiss/i)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("a linha do turno traz o que a aba existe para mostrar", () => {
  it("métrica, linhas, latência, tokens, modelo e versão", () => {
    abrir({ runs: [run()] });

    const turnos = tabela(TURNOS);

    expect(turnos.getByText("deviations_total")).toBeInTheDocument();
    expect(turnos.getByText("3")).toBeInTheDocument();
    expect(turnos.getByText("500 ms")).toBeInTheDocument();
    expect(turnos.getByText("100")).toBeInTheDocument();
    expect(turnos.getByText("20")).toBeInTheDocument();
    expect(turnos.getByText("fake-1")).toBeInTheDocument();
    expect(turnos.getByText("v2")).toBeInTheDocument();
  });

  it("o turno sem métrica não inventa uma", () => {
    abrir({
      runs: [run({ metric_code: null, rows_returned: null, model: null })],
    });

    // O travessão é da `Table`, para toda célula vazia.
    expect(tabela(TURNOS).getAllByText("—").length).toBeGreaterThanOrEqual(3);
  });
});
