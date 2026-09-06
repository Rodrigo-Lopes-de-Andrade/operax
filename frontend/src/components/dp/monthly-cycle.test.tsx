import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MonthlyCycle } from "@/components/dp/monthly-cycle";
import type { CycleView } from "@/lib/dp/queries";
import type { CycleFilters } from "@/lib/dp/url";

const request = vi.fn();
const download = vi.fn();
const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    requestApiAsUser: (...args: unknown[]) => request(...args),
    downloadApiAsUser: (...args: unknown[]) => download(...args),
  };
});

const CYCLE_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const SETEMBRO: CycleFilters = {
  kind: "transport_voucher",
  year: 2026,
  month: 9,
};

function ciclo(overrides: Partial<CycleView> = {}): CycleView {
  return {
    id: CYCLE_ID,
    kind: "transport_voucher",
    period_year: 2026,
    period_month: 9,
    window_start: "2026-08-21",
    window_end: "2026-09-20",
    business_days: 21,
    status: "draft",
    entitled_count: 1,
    denied_count: 1,
    total_amount: "201.60",
    rows: [
      {
        employee_id: "11111111-1111-4111-8111-111111111111",
        name: "Ana Ribeiro",
        registration_number: "1001",
        unit_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        unit_name: "Aeroporto",
        entitled: true,
        reason: null,
        days_base: 21,
        absences_prior: 0,
        net_days: 21,
        unit_amount: "4.80",
        round_trip_amount: "9.60",
        total_amount: "201.60",
      },
      {
        employee_id: "22222222-2222-4222-8222-222222222222",
        name: "Bruno Lima",
        registration_number: "1002",
        unit_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        unit_name: "Rodoviária",
        entitled: false,
        reason:
          "Sem dias líquidos: 21 dia(s) base menos 21 falta(s) injustificada(s) em 07/2026.",
        days_base: 21,
        absences_prior: 21,
        net_days: 0,
        unit_amount: "4.80",
        round_trip_amount: "9.60",
        total_amount: "0.00",
      },
    ],
    ...overrides,
  };
}

/** Apura e devolve o `user`, com o preview já na tela. */
async function apurar(cycle: CycleView, filters: CycleFilters = SETEMBRO) {
  request.mockResolvedValue(cycle);
  const user = userEvent.setup();
  render(<MonthlyCycle filters={filters} />);

  await user.click(screen.getByRole("button", { name: "Apurar competência" }));
  await screen.findByText("Arquivos da competência");

  return user;
}

beforeEach(() => {
  request.mockReset();
  download.mockReset();
  push.mockReset();
  URL.createObjectURL = vi.fn(() => "blob:ciclo");
  URL.revokeObjectURL = vi.fn();
});

describe("apurar é preview, gerar é o que congela", () => {
  it("pede a competência da URL e mostra a janela derivada dela", async () => {
    await apurar(ciclo());

    expect(request).toHaveBeenCalledWith("/dp/ciclos", {
      method: "POST",
      body: {
        kind: "transport_voucher",
        period_year: 2026,
        period_month: 9,
      },
    });
    expect(
      screen.getByText(/Janela de 21\/08\/2026 a 20\/09\/2026/),
    ).toBeInTheDocument();
    expect(screen.getByText("Rascunho")).toBeInTheDocument();
  });

  it("mostra o direito e o motivo de cada pessoa", async () => {
    await apurar(ciclo());

    const aeroporto = screen.getByRole("table", {
      name: "Apuração por pessoa — Aeroporto",
    });
    expect(within(aeroporto).getByText("Ana Ribeiro")).toBeInTheDocument();
    expect(within(aeroporto).getByText("Sim")).toBeInTheDocument();

    const rodoviaria = screen.getByRole("table", {
      name: "Apuração por pessoa — Rodoviária",
    });
    expect(within(rodoviaria).getByText("Não")).toBeInTheDocument();
    // O motivo é a resposta à pergunta que a pessoa vai fazer, e vem do
    // apurador — a tela não a reescreve.
    expect(
      within(rodoviaria).getByText(
        "Sem dias líquidos: 21 dia(s) base menos 21 falta(s) injustificada(s) em 07/2026.",
      ),
    ).toBeInTheDocument();
  });

  it("gerar congela, e o botão de gerar sai da tela", async () => {
    const user = await apurar(ciclo());
    request.mockResolvedValue(ciclo({ status: "generated" }));

    await user.click(screen.getByRole("button", { name: "Gerar ciclo" }));

    await waitFor(() =>
      expect(request).toHaveBeenLastCalledWith(`/dp/ciclos/${CYCLE_ID}/gerar`, {
        method: "POST",
      }),
    );
    expect(await screen.findByText("Gerado")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Gerar ciclo" }),
    ).not.toBeInTheDocument();
  });

  it("o preview não sobrevive à troca de competência", async () => {
    request.mockResolvedValue(ciclo());
    const user = userEvent.setup();
    const { rerender } = render(<MonthlyCycle filters={SETEMBRO} />);

    await user.click(
      screen.getByRole("button", { name: "Apurar competência" }),
    );
    expect(
      await screen.findByText("Arquivos da competência"),
    ).toBeInTheDocument();

    rerender(<MonthlyCycle filters={{ ...SETEMBRO, month: 8 }} />);

    // Os números de setembro embaixo do título de agosto são a pior tela
    // possível desta rotina: eles parecem certos.
    expect(screen.getByText("Nada apurado em agosto/2026")).toBeInTheDocument();
    expect(screen.queryByText("Ana Ribeiro")).not.toBeInTheDocument();
  });
});

describe("a recusa do apurador é resposta, não erro do sistema", () => {
  it("mostra qual jornada falta, com o texto do backend", async () => {
    const { ApiError } = await import("@/lib/api");
    request.mockRejectedValue(
      new ApiError(
        422,
        "app.expected_workday não cobre o período de 3 colaborador(es): Ana Ribeiro, Bruno Lima, Carla Souza. Rode o motor de jornada sobre a janela antes de apurar — dia sem linha não é dia sem expediente, e contá-lo como zero paga a menos",
      ),
    );
    const user = userEvent.setup();
    render(<MonthlyCycle filters={SETEMBRO} />);

    await user.click(
      screen.getByRole("button", { name: "Apurar competência" }),
    );

    expect(
      await screen.findByText(/app\.expected_workday não cobre o período/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/falta dado, não é falha do sistema/),
    ).toBeInTheDocument();
    // O par do negativo: a frase genérica não pode aparecer no lugar da
    // acionável, que é a única que diz o que fazer.
    expect(
      screen.queryByText("Não consegui apurar a competência."),
    ).not.toBeInTheDocument();
  });

  it("nomeia a justificativa que a curadoria não classificou", async () => {
    const { ApiError } = await import("@/lib/api");
    request.mockRejectedValue(
      new ApiError(
        422,
        "a justificativa «ATEST M» não está classificada em app.leave_justification_map; classifique-a antes de apurar — tratá-la como ausência de falta entrega benefício a quem faltou",
      ),
    );
    const user = userEvent.setup();
    render(<MonthlyCycle filters={SETEMBRO} />);

    await user.click(
      screen.getByRole("button", { name: "Apurar competência" }),
    );

    // A string literal é o que a pessoa vai procurar na curadoria. Resumir a
    // mensagem apagaria a única parte acionável dela.
    expect(
      await screen.findByText(/«ATEST M» não está classificada/),
    ).toBeInTheDocument();
  });

  it("falha sem mensagem continua sendo erro vermelho, e não recusa", async () => {
    const { ApiError } = await import("@/lib/api");
    request.mockRejectedValue(new ApiError(500, null));
    const user = userEvent.setup();
    render(<MonthlyCycle filters={SETEMBRO} />);

    await user.click(
      screen.getByRole("button", { name: "Apurar competência" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não consegui apurar a competência.",
    );
    expect(
      screen.queryByText(/falta dado, não é falha do sistema/),
    ).not.toBeInTheDocument();
  });
});

describe("o arquivo do banco só existe para quem tem o domínio bancário", () => {
  it("aparece para quem tem, num ciclo congelado, e baixa a remessa", async () => {
    const user = await apurar(
      ciclo({ status: "generated", can_export_remittance: true }),
    );
    download.mockResolvedValue({
      blob: new Blob(["1001;Ana"]),
      filename: "transport_voucher-2026-09.txt",
    });

    await user.click(screen.getByRole("button", { name: "Arquivo do banco" }));

    await waitFor(() =>
      expect(download).toHaveBeenCalledWith(
        `/dp/ciclos/${CYCLE_ID}/export?formato=banco`,
        "transport_voucher-2026-09",
      ),
    );
  });

  it("não aparece para quem não tem — e os outros dois continuam lá", async () => {
    await apurar(ciclo({ status: "generated", can_export_remittance: false }));

    // O positivo do par: sem estes dois, o negativo abaixo passaria numa tela
    // que não renderiza botão nenhum.
    expect(screen.getByRole("button", { name: "Excel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "PDF" })).toBeInTheDocument();

    expect(
      screen.queryByRole("button", { name: "Arquivo do banco" }),
    ).not.toBeInTheDocument();
    // Nem desabilitado, nem cadeado, nem explicação: quem não alcança dado
    // bancário não fica sabendo que existe um arquivo de banco.
    expect(screen.queryByText(/banco/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/remessa/i)).not.toBeInTheDocument();
  });

  it("resposta sem o campo vale como 'não pode', nunca como 'pode'", async () => {
    const semCampo = ciclo({ status: "generated" });
    delete semCampo.can_export_remittance;

    await apurar(semCampo);

    expect(screen.getByRole("button", { name: "Excel" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Arquivo do banco" }),
    ).not.toBeInTheDocument();
  });
});

describe("a remessa exige o ciclo congelado, e a tela diz por quê", () => {
  it("no rascunho, explica em vez de oferecer um botão que recusa", async () => {
    await apurar(ciclo({ status: "draft", can_export_remittance: true }));

    expect(
      screen.getByText(/O arquivo do banco exige o ciclo gerado/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /duas remessas do mesmo mês pagariam valores diferentes/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Arquivo do banco" }),
    ).not.toBeInTheDocument();

    // Excel e PDF saem do rascunho: eles são o preview, e é para conferir que
    // o rascunho existe.
    expect(screen.getByRole("button", { name: "Excel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "PDF" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Gerar ciclo" }),
    ).toBeInTheDocument();
  });

  it("baixa o Excel do rascunho — o preview é para conferir", async () => {
    const user = await apurar(ciclo({ status: "draft" }));
    download.mockResolvedValue({
      blob: new Blob(["planilha"]),
      filename: "transport_voucher-2026-09.xlsx",
    });

    await user.click(screen.getByRole("button", { name: "Excel" }));

    await waitFor(() =>
      expect(download).toHaveBeenCalledWith(
        `/dp/ciclos/${CYCLE_ID}/export?formato=xlsx`,
        "transport_voucher-2026-09",
      ),
    );
  });

  it("a cesta não tem arquivo de banco, e a tela diz o que ela é", async () => {
    await apurar(
      ciclo({
        kind: "food_basket",
        status: "generated",
        can_export_remittance: true,
        window_start: "2026-09-01",
        window_end: "2026-09-30",
      }),
      { kind: "food_basket", year: 2026, month: 9 },
    );

    expect(
      screen.getByText(/A cesta não tem arquivo de banco/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Arquivo do banco" }),
    ).not.toBeInTheDocument();
  });

  it("se o backend recusar a remessa, o motivo dele chega inteiro", async () => {
    const { ApiError } = await import("@/lib/api");
    const user = await apurar(
      ciclo({ status: "generated", can_export_remittance: true }),
    );
    download.mockRejectedValue(
      new ApiError(
        409,
        "este ciclo está em «draft» e a remessa só sai de ciclo congelado; gere o ciclo antes de exportar para o banco",
      ),
    );

    await user.click(screen.getByRole("button", { name: "Arquivo do banco" }));

    expect(
      await screen.findByText(/gere o ciclo antes de exportar para o banco/),
    ).toBeInTheDocument();
  });
});
