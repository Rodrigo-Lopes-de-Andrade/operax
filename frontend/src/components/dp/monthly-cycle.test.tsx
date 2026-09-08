import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MonthlyCycle } from "@/components/dp/monthly-cycle";
import type {
  CycleListResult,
  CycleSummary,
  CycleView,
} from "@/lib/dp/queries";
import type { CycleFilters } from "@/lib/dp/url";

const request = vi.fn();
const download = vi.fn();
const push = vi.fn();
// `refresh` mora aqui e não dentro do `useRouter`: um `vi.fn()` criado a cada
// render é um espião que nenhuma asserção alcança, e era o que ele era.
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push }),
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
    can_export_remittance: false,
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

/** O histórico de `GET /dp/ciclos` para a competência da URL. */
function historico(
  rows: CycleSummary[] = [],
  canExportRemittance = false,
): CycleListResult {
  return {
    status: "ok",
    list: { rows, can_export_remittance: canExportRemittance },
  };
}

/** O resumo que a lista devolve — sem as linhas por pessoa, como a rota. */
function resumo(overrides: Partial<CycleSummary> = {}): CycleSummary {
  return {
    id: CYCLE_ID,
    kind: "transport_voucher",
    period_year: 2026,
    period_month: 9,
    window_start: "2026-08-21",
    window_end: "2026-09-20",
    business_days: 21,
    status: "generated",
    entitled_count: 1,
    denied_count: 1,
    total_amount: "201.60",
    ...overrides,
  };
}

/** Apura e devolve o `user`, com o preview já na tela. */
async function apurar(cycle: CycleView, filters: CycleFilters = SETEMBRO) {
  request.mockResolvedValue(cycle);
  const user = userEvent.setup();
  render(<MonthlyCycle filters={filters} history={historico()} canWrite />);

  await user.click(screen.getByRole("button", { name: "Apurar competência" }));
  await screen.findByText("Arquivos da competência");

  return user;
}

beforeEach(() => {
  request.mockReset();
  download.mockReset();
  push.mockReset();
  refresh.mockReset();
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
    // ⛔ E o servidor é avisado. Sem esta revalidação o rascunho recém-gravado
    // não entra no histórico, e o próximo F5 volta a dizer "nada apurado" sobre
    // um mês que já tem linha — que é o estado de onde saía o segundo rascunho.
    // `apurar()` é o único caminho que chamou `refresh` até aqui, então 1 é o
    // número, e não "pelo menos uma".
    expect(refresh).toHaveBeenCalledTimes(1);
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
    refresh.mockClear();

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

    // ⛔ E "APURAR COMPETÊNCIA" TAMBÉM SOME, NA MESMA SESSÃO E SEM F5
    // O congelamento vale para o ciclo que nasceu aqui, e não só para o que
    // veio do servidor: o histórico desta tela está vazio, então quem responde
    // por esta ausência é o `status` do preview e nada mais. Sem isto, o
    // operador que acabou de gerar recebe o botão de volta, e o clique cai no
    // INSERT que a `unique` com `status` não barra.
    expect(
      screen.queryByRole("button", { name: "Apurar competência" }),
    ).not.toBeInTheDocument();

    // O servidor precisa saber que a competência congelou; senão a próxima
    // leitura ainda traz o rascunho que ele acabou de substituir.
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("o preview não sobrevive à troca de competência", async () => {
    request.mockResolvedValue(ciclo());
    const user = userEvent.setup();
    const { rerender } = render(
      <MonthlyCycle filters={SETEMBRO} history={historico()} canWrite />,
    );

    await user.click(
      screen.getByRole("button", { name: "Apurar competência" }),
    );
    expect(
      await screen.findByText("Arquivos da competência"),
    ).toBeInTheDocument();

    rerender(
      <MonthlyCycle
        filters={{ ...SETEMBRO, month: 8 }}
        history={historico()}
        canWrite
      />,
    );

    // Os números de setembro embaixo do título de agosto são a pior tela
    // possível desta rotina: eles parecem certos.
    expect(screen.getByText("Nada apurado em agosto/2026")).toBeInTheDocument();
    expect(screen.queryByText("Ana Ribeiro")).not.toBeInTheDocument();
  });

  it("⛔ reapurar um rascunho JÁ GRAVADO troca o resumo pela conferência pessoa a pessoa", async () => {
    // O dia a dia da tela, e ele não tinha caso: apurar sobre histórico vazio é
    // o primeiro clique do mês, uma vez. Do segundo em diante existe rascunho
    // no servidor, e é aqui que a precedência entre o preview e o resumo
    // aparece — o resumo não traz linhas, e deixá-lo ganhar apaga a tabela que
    // o operador acabou de pedir, trocada pelo "sai nos arquivos".
    request.mockResolvedValue(ciclo({ status: "draft" }));
    const user = userEvent.setup();
    render(
      <MonthlyCycle
        filters={SETEMBRO}
        history={historico([resumo({ status: "draft", total_amount: "1.00" })])}
        canWrite
      />,
    );

    // ✅ O positivo de partida: antes do clique quem está na tela é o resumo do
    // servidor. Sem ele, o negativo abaixo passaria numa tela que nunca
    // renderizou o histórico.
    expect(screen.getByText("R$ 1,00")).toBeInTheDocument();
    expect(
      screen.getByText(/conferência pessoa a pessoa sai nos arquivos/i),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Apurar competência" }),
    );

    expect(await screen.findByText("Ana Ribeiro")).toBeInTheDocument();
    expect(screen.queryByText("R$ 1,00")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/conferência pessoa a pessoa sai nos arquivos/i),
    ).not.toBeInTheDocument();
  });

  it("trocar o mês vai para a URL, e a competência viaja inteira", async () => {
    // O filtro mora na query string: o link que alguém encaminha pedindo "olha
    // o vale transporte de agosto" tem de abrir agosto. Um `useState` aqui
    // deixaria a tela certa e o link errado, e nada na tela diria isso.
    const user = userEvent.setup();
    render(<MonthlyCycle filters={SETEMBRO} history={historico()} canWrite />);

    await user.selectOptions(screen.getByLabelText("Mês da competência"), "8");

    expect(push).toHaveBeenCalledWith(
      "/dashboard/dp/ciclos?tipo=transport_voucher&ano=2026&mes=8",
    );
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
    render(<MonthlyCycle filters={SETEMBRO} history={historico()} canWrite />);

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
    render(<MonthlyCycle filters={SETEMBRO} history={historico()} canWrite />);

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
    render(<MonthlyCycle filters={SETEMBRO} history={historico()} canWrite />);

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
    // O tipo diz obrigatório porque o contrato diz — mas o que chega é JSON, e
    // uma renomeação no backend entregaria o objeto sem a chave. A regra da
    // leitura é que tem de sobreviver a isso.
    const semCampo = ciclo({ status: "generated" });
    delete (semCampo as { can_export_remittance?: boolean })
      .can_export_remittance;

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

describe("a competência já apurada volta do servidor", () => {
  it("um F5 sobre um mês GERADO mostra o gerado, e não 'nada apurado'", () => {
    render(
      <MonthlyCycle
        filters={SETEMBRO}
        history={historico([resumo({ status: "generated" })])}
        canWrite
      />,
    );

    expect(screen.getByText("Gerado")).toBeInTheDocument();
    expect(
      screen.getByText(/Janela de 21\/08\/2026 a 20\/09\/2026/),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Nada apurado em setembro/2026"),
    ).not.toBeInTheDocument();
  });

  it("⛔ e 'Apurar competência' SOME, porque reapurar criaria um segundo rascunho", () => {
    // `save_draft` procura rascunho ABERTO; achando só um `generated`, insere
    // outra linha, porque o `unique` da competência inclui o `status`. O
    // operador passava a ver "Rascunho" para um mês congelado e perdia a
    // remessa que tinha conferido.
    render(
      <MonthlyCycle
        filters={SETEMBRO}
        history={historico([resumo({ status: "generated" })])}
        canWrite
      />,
    );

    expect(
      screen.queryByRole("button", { name: "Apurar competência" }),
    ).not.toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
  });

  it("✅ o positivo do par: sobre um RASCUNHO, apurar continua sendo reapurar", () => {
    render(
      <MonthlyCycle
        filters={SETEMBRO}
        history={historico([resumo({ status: "draft" })])}
        canWrite
      />,
    );

    expect(screen.getByText("Rascunho")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Apurar competência" }),
    ).toBeInTheDocument();
  });

  it("com rascunho E gerado na mesma competência, mostra o gerado", () => {
    // O banco que já passou pelo bug tem as duas linhas; a que virou remessa é
    // a que não pode sumir da tela.
    render(
      <MonthlyCycle
        filters={SETEMBRO}
        history={historico([
          resumo({ status: "draft", total_amount: "1.00" }),
          resumo({ status: "generated", total_amount: "201.60" }),
        ])}
        canWrite
      />,
    );

    expect(screen.getByText("Gerado")).toBeInTheDocument();
    expect(screen.queryByText("Rascunho")).not.toBeInTheDocument();
  });

  it("a lista não traz as linhas por pessoa, e a tela diz onde elas estão", () => {
    render(
      <MonthlyCycle
        filters={SETEMBRO}
        history={historico([resumo({ status: "generated" })])}
        canWrite
      />,
    );

    expect(
      screen.getByText(/conferência pessoa a pessoa sai nos arquivos/i),
    ).toBeInTheDocument();
    // ⛔ E nunca "nenhum vínculo na janela": não carregado não é vazio.
    expect(
      screen.queryByText("Nenhum vínculo na janela"),
    ).not.toBeInTheDocument();
  });

  it("⛔ histórico ilegível avisa E FECHA o apurar: não se apura às cegas", () => {
    // ⚠️ MUDANÇA DE COMPORTAMENTO DESTE CICLO, e ela é deliberada.
    // Antes o alerta pedia o F5 e o botão continuava clicável. Só que é o
    // clique que duplica: sem a lista a tela não sabe se este mês já foi
    // gerado, e o INSERT não colide com a linha congelada, porque a `unique`
    // inclui o `status` e `trg_benefit_cycle_immutable` não cobre INSERT. Não
    // saber vale como congelada. Fechar custa uma recarga — que é o que o
    // alerta já pedia; abrir custa um rascunho que esconde a remessa.
    render(
      <MonthlyCycle
        filters={SETEMBRO}
        history={{ status: "unavailable" }}
        canWrite
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      /não consegui ler as competências já apuradas/i,
    );
    // ⛔ E O ALERTA DIZ QUE O BOTÃO SUMIU — a ausência sem explicação é a tela
    // que parece quebrada. Sem esta linha dá para devolver ao texto a promessa
    // antiga ("apurar continua disponível") com o botão ausente do mesmo jeito,
    // e a suíte inteira segue verde enquanto a tela mente.
    expect(screen.getByRole("alert")).toHaveTextContent(
      /apurar fica indisponível/i,
    );
    expect(
      screen.queryByRole("button", { name: "Apurar competência" }),
    ).not.toBeInTheDocument();
  });

  it("✅ o par: com a lista legível, quem escreve continua tendo o que apurar", () => {
    // Sem este, o teste acima passaria com o botão removido da tela inteira.
    // `canWrite` é o mesmo, não há ciclo em nenhum dos dois, e a única coisa
    // que muda entre eles é a leitura do histórico ter chegado.
    render(<MonthlyCycle filters={SETEMBRO} history={historico()} canWrite />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Apurar competência" }),
    ).toBeInTheDocument();
    // ⛔ E A TELA VAZIA ENSINA QUE APURAR É PREVIEW, para quem pode apurar.
    // É a frase que separa apurar de gerar antes do primeiro clique — sem ela,
    // clicar parece definitivo, e quem acha que é definitivo não clica.
    expect(
      screen.getByText(/apurar não grava nada definitivo/i),
    ).toBeInTheDocument();
  });

  it("⛔ o preview desta sessão NÃO reabre o apurar: apurei agora e o refresh voltou ilegível", async () => {
    // A CENA QUE FALTAVA, e é a única em que a leitura do histórico responde
    // sozinha. Os dois testes acima têm a tela vazia, então `congelada` é falsa
    // porque não há ciclo nenhum — fechar por "não sei" e fechar por "não há
    // nada" ficam indistinguíveis, e prender `podeApurar` só na tela vazia
    // aceita `historicoLegivel || apurado !== null` sem uma falha sequer.
    // Aqui existe ciclo, ele é rascunho (logo `congelada` continua falsa), a
    // sessão é a mesma e `canWrite` também: de uma render para a outra só muda
    // a resposta de `GET /dp/ciclos`.
    request.mockResolvedValue(ciclo({ status: "draft" }));
    const user = userEvent.setup();
    const { rerender } = render(
      <MonthlyCycle filters={SETEMBRO} history={historico()} canWrite />,
    );

    await user.click(
      screen.getByRole("button", { name: "Apurar competência" }),
    );
    await screen.findByText("Arquivos da competência");

    // ✅ ANTES: com o preview em rascunho na tela, reapurar é oferecido — é o
    // dia a dia da conferência, e é ele que a ausência lá embaixo não pode
    // estar cobrando de um botão que já não existia.
    expect(
      screen.getByRole("button", { name: "Apurar competência" }),
    ).toBeInTheDocument();

    rerender(
      <MonthlyCycle
        filters={SETEMBRO}
        history={{ status: "unavailable" }}
        canWrite
      />,
    );

    // ✅ O preview SOBREVIVE à leitura falhar: o que o operador apurou continua
    // na tela. Sem estas duas linhas a ausência abaixo passaria numa tela que
    // perdeu o ciclo, que é outro defeito e não este.
    expect(screen.getByText("Rascunho")).toBeInTheDocument();
    expect(screen.getByText("Ana Ribeiro")).toBeInTheDocument();

    // ⛔ E MESMO ASSIM NÃO SE REAPURA ÀS CEGAS. O rascunho da sessão não prova
    // que o servidor não tem uma competência gerada — o refresh que ia contar
    // isso é justamente o que falhou. Reapurar aqui insere a segunda linha.
    expect(
      screen.queryByRole("button", { name: "Apurar competência" }),
    ).not.toBeInTheDocument();
  });

  it("⛔ 'Exportado' também é competência congelada — apurar não reabre sobre o pago", () => {
    // O estado é inalcançável pela tela hoje: quem escreve `exported` é o passo
    // de remessa, no backend. No dia em que ele escrever, reapurar por cima de
    // uma competência já paga insere a segunda linha do mesmo jeito — e é por
    // isso que `PAYABLE` tem dois valores e não um.
    render(
      <MonthlyCycle
        filters={SETEMBRO}
        history={historico([resumo({ status: "exported" })], true)}
        canWrite
      />,
    );

    expect(screen.getByText("Exportado")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Apurar competência" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Gerar ciclo" }),
    ).not.toBeInTheDocument();

    // ✅ E a remessa continua saindo: congelado é o que a torna possível, e
    // `exported` é congelado. Sem esta linha, as duas ausências acima passariam
    // numa tela que só sabe não renderizar botão.
    expect(
      screen.getByRole("button", { name: "Arquivo do banco" }),
    ).toBeInTheDocument();
  });
});

describe("quem confere a remessa não apura — e continua entrando", () => {
  it("sem escrita, apurar e gerar somem; conferir e exportar ficam", () => {
    render(
      <MonthlyCycle
        filters={SETEMBRO}
        history={historico([resumo({ status: "generated" })], true)}
        canWrite={false}
      />,
    );

    // ⛔ O NEGATIVO — `accounting` e `executive` têm `compensation` e não são
    // admin: `_pode_escrever_catalogo` recusaria os dois botões.
    expect(
      screen.queryByRole("button", { name: "Apurar competência" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Gerar ciclo" }),
    ).not.toBeInTheDocument();

    // ✅ O POSITIVO AO LADO — sem ele isto passaria numa tela vazia.
    expect(screen.getByText("Gerado")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Excel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "PDF" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Arquivo do banco" }),
    ).toBeInTheDocument();
  });

  it("sem escrita e sem nada apurado, a tela não oferece o botão que recusaria", () => {
    render(
      <MonthlyCycle
        filters={SETEMBRO}
        history={historico()}
        canWrite={false}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "Apurar competência" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/quando alguém apurar esta competência/i),
    ).toBeInTheDocument();
  });

  it("⛔ sobre um RASCUNHO, quem não escreve não recebe nenhum dos dois botões", () => {
    // O caso que isola `canWrite`: com a competência congelada, o próprio
    // congelamento já esconde os dois, e a asserção passaria sem provar nada.
    render(
      <MonthlyCycle
        filters={SETEMBRO}
        history={historico([resumo({ status: "draft" })], true)}
        canWrite={false}
      />,
    );

    expect(screen.getByText("Rascunho")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Apurar competência" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Gerar ciclo" }),
    ).not.toBeInTheDocument();

    // ✅ E conferir continua sendo dele: é para isso que ele entra na tela.
    expect(screen.getByRole("button", { name: "Excel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "PDF" })).toBeInTheDocument();
  });

  it("o botão de gerar existe para quem escreve, sobre um rascunho", () => {
    render(
      <MonthlyCycle
        filters={SETEMBRO}
        history={historico([resumo({ status: "draft" })])}
        canWrite
      />,
    );

    expect(
      screen.getByRole("button", { name: "Gerar ciclo" }),
    ).toBeInTheDocument();
  });
});

describe("a remessa de uma competência lida do histórico", () => {
  it("usa o `can_export_remittance` do container da lista", async () => {
    download.mockResolvedValue({
      blob: new Blob(["1001;Ana"]),
      filename: "transport_voucher-2026-09.txt",
    });
    const user = userEvent.setup();
    render(
      <MonthlyCycle
        filters={SETEMBRO}
        history={historico([resumo({ status: "generated" })], true)}
        canWrite
      />,
    );

    await user.click(screen.getByRole("button", { name: "Arquivo do banco" }));

    await waitFor(() =>
      expect(download).toHaveBeenCalledWith(
        `/dp/ciclos/${CYCLE_ID}/export?formato=banco`,
        "transport_voucher-2026-09",
      ),
    );
  });

  it("e some quando o container diz que não", () => {
    render(
      <MonthlyCycle
        filters={SETEMBRO}
        history={historico([resumo({ status: "generated" })], false)}
        canWrite
      />,
    );

    expect(screen.getByRole("button", { name: "Excel" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Arquivo do banco" }),
    ).not.toBeInTheDocument();
  });
});
