import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ComplianceReports } from "@/components/dp/compliance-reports";
import type {
  ComplianceReportList,
  ComplianceReportRow,
} from "@/lib/dp/queries";
import { DUE_SOON_DAYS, dueTone } from "@/lib/rh/labels";

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

const UNIT_A = "11111111-1111-4111-8111-111111111111";
const UNIT_B = "22222222-2222-4222-8222-222222222222";

const UNITS = [
  { id: UNIT_A, name: "Aeroporto" },
  { id: UNIT_B, name: "Rodoviária" },
];

const VENCIDO = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const HOJE = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const EM_DIA = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";

function laudo(overrides: Partial<ComplianceReportRow>): ComplianceReportRow {
  return {
    id: EM_DIA,
    unit_id: UNIT_A,
    unit_name: "Aeroporto",
    type: "PCMSO",
    valid_until: "2026-10-12",
    days_to_expiry: 31,
    renewal_count: 0,
    notes: null,
    created_at: "2026-09-01T12:00:00Z",
    ...overrides,
  };
}

/** Três laudos, um em cada situação: -1, 0 e 31 dias. */
function tela(
  overrides: Partial<ComplianceReportList> = {},
): ComplianceReportList {
  return {
    can_write: true,
    rows: [
      laudo({
        id: VENCIDO,
        type: "PGR",
        valid_until: "2026-09-10",
        days_to_expiry: -1,
        renewal_count: 2,
        notes: "Aguardando a clínica",
      }),
      laudo({
        id: HOJE,
        unit_id: UNIT_B,
        unit_name: "Rodoviária",
        type: "LTCAT+LTIP",
        valid_until: "2026-09-11",
        days_to_expiry: 0,
      }),
      laudo({ id: EM_DIA }),
    ],
    ...overrides,
  };
}

function montar(
  screen: ComplianceReportList,
  status: "vencido" | "a_vencer" | "em_dia" | null = null,
  unitId: string | null = null,
) {
  return render(
    <ComplianceReports
      screen={screen}
      units={UNITS}
      status={status}
      unitId={unitId}
    />,
  );
}

function linha(tipo: string) {
  return screen.getByText(tipo).closest("tr") as HTMLTableRowElement;
}

/** `type="date"` não aceita digitação no jsdom; o valor entra por `change`. */
function preencher(label: string, valor: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value: valor } });
}

beforeEach(() => {
  request.mockReset();
  refresh.mockReset();
});

describe("a situação é derivada de `days_to_expiry`, com o limiar da ficha de RH", () => {
  it("-1 é VENCIDO, 0 é A VENCER, 31 é EM DIA — e a frase acompanha", () => {
    montar(tela());

    const vencido = linha("PGR");
    expect(within(vencido).getByText("Vencido")).toBeInTheDocument();
    expect(within(vencido).getByText("venceu há 1 dia")).toBeInTheDocument();

    const hoje = linha("LTCAT+LTIP");
    expect(within(hoje).getByText("A vencer")).toBeInTheDocument();
    expect(within(hoje).getByText("vence hoje")).toBeInTheDocument();

    // ✅ O positivo: 31 dias é EM DIA, e não apenas "não é vencido".
    const emDia = linha("PCMSO");
    expect(within(emDia).getByText("Em dia")).toBeInTheDocument();
    expect(within(emDia).getByText("vence em 31 dias")).toBeInTheDocument();
  });

  it("o tom do badge acompanha o rótulo: vencido é falha, a vencer é alerta", () => {
    // Um "Vencido" em cinza seria a tela contando duas histórias — o rótulo
    // certo com a cor de "informação". O tom é semântica, não decoração.
    montar(tela());

    expect(within(linha("PGR")).getByText("Vencido")).toHaveClass("text-bad");
    expect(within(linha("LTCAT+LTIP")).getByText("A vencer")).toHaveClass(
      "text-alert",
    );
    expect(within(linha("PCMSO")).getByText("Em dia")).toHaveClass(
      "text-ink-muted",
    );
  });

  it("30 dias ainda é A VENCER — a janela é a de `dueTone`, declarada uma vez", () => {
    montar(
      tela({
        rows: [
          laudo({ days_to_expiry: 30 }),
          laudo({ id: VENCIDO, type: "PGR", days_to_expiry: 31 }),
        ],
      }),
    );

    expect(within(linha("PCMSO")).getByText("A vencer")).toBeInTheDocument();
    expect(within(linha("PGR")).getByText("Em dia")).toBeInTheDocument();
  });

  it("mostra unidade, validade, renovações e observação de cada laudo", () => {
    montar(tela());

    const vencido = linha("PGR");
    expect(within(vencido).getByText("Aeroporto")).toBeInTheDocument();
    expect(within(vencido).getByText("10/09/2026")).toBeInTheDocument();
    expect(within(vencido).getByText("2")).toBeInTheDocument();
    expect(
      within(vencido).getByText("Aguardando a clínica"),
    ).toBeInTheDocument();
  });
});

describe("o filtro de situação é aplicado sobre o que a API devolveu", () => {
  it("`vencido` mostra só a vencida", () => {
    montar(tela(), "vencido");

    expect(screen.getByText("PGR")).toBeInTheDocument();
    expect(screen.queryByText("LTCAT+LTIP")).not.toBeInTheDocument();
    expect(screen.queryByText("PCMSO")).not.toBeInTheDocument();
  });

  it("`em_dia` mostra só a em dia", () => {
    montar(tela(), "em_dia");

    expect(screen.getByText("PCMSO")).toBeInTheDocument();
    expect(screen.queryByText("PGR")).not.toBeInTheDocument();
  });

  it("sem filtro mostra as três", () => {
    montar(tela());

    expect(screen.getAllByRole("row")).toHaveLength(4);
  });

  it("filtro sem linha diz que há laudos fora dele — não 'nenhum laudo vigente'", () => {
    montar(tela({ rows: [laudo({ days_to_expiry: 31 })] }), "vencido");

    expect(screen.getByText("Nenhum laudo vencido")).toBeInTheDocument();
    expect(
      screen.getByText(/1 laudo vigente fora desta situação/),
    ).toBeInTheDocument();
    expect(screen.queryByText("Nenhum laudo vigente")).not.toBeInTheDocument();
  });
});

describe("quem não escreve não vê a ação — e quem escreve vê", () => {
  it("com can_write, Renovar e Novo laudo existem", () => {
    montar(tela());

    expect(
      screen.getByRole("button", { name: "Novo laudo" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Renovar" })).toHaveLength(3);
  });

  it("sem can_write, as ações somem e a lista continua lá", () => {
    montar(tela({ can_write: false }));

    // O positivo ao lado do negativo: sem a lista, o negativo passaria numa
    // tela que não renderiza nada.
    expect(screen.getByText("PGR")).toBeInTheDocument();
    expect(screen.getByText("PCMSO")).toBeInTheDocument();

    expect(screen.queryByRole("button", { name: "Novo laudo" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Renovar" })).toBeNull();
  });

  it("resposta sem a chave vale como 'não pode', nunca como 'pode'", () => {
    // O que chega é JSON: uma renomeação no backend entregaria o objeto sem a
    // chave, e a regra da leitura é que tem de sobreviver a isso.
    const semChave = tela();
    delete (semChave as { can_write?: boolean }).can_write;

    montar(semChave);

    expect(screen.getByText("PGR")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Novo laudo" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Renovar" })).toBeNull();
  });
});

describe("renovar é linha nova — não existe editar a data vigente", () => {
  it("não há campo de data nem apagar na linha vigente", () => {
    montar(tela());

    expect(screen.queryByLabelText(/validade/i)).toBeNull();
    expect(
      screen.queryByRole("button", { name: /excluir|apagar|remover/i }),
    ).toBeNull();
  });

  it("envia a validade nova e a observação para a rota de renovação, e relê", async () => {
    request.mockResolvedValue({});
    const user = userEvent.setup();
    montar(tela());

    await user.click(
      within(linha("PGR")).getByRole("button", { name: "Renovar" }),
    );

    expect(
      screen.getByRole("heading", { name: "PGR · Aeroporto" }),
    ).toBeInTheDocument();

    preencher("Nova validade", "2027-09-10");
    await user.type(
      screen.getByLabelText("Observação (opcional)"),
      "Visita feita",
    );
    await user.click(screen.getByRole("button", { name: "Renovar laudo" }));

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(`/dp/laudos/${VENCIDO}/renovar`, {
        method: "POST",
        body: { valid_until: "2027-09-10", notes: "Visita feita" },
      }),
    );
    expect(refresh).toHaveBeenCalled();
  });

  it("manda `null` quando a observação fica em branco", async () => {
    request.mockResolvedValue({});
    const user = userEvent.setup();
    montar(tela());

    await user.click(
      within(linha("PCMSO")).getByRole("button", { name: "Renovar" }),
    );
    preencher("Nova validade", "2027-10-12");
    await user.click(screen.getByRole("button", { name: "Renovar laudo" }));

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(`/dp/laudos/${EM_DIA}/renovar`, {
        method: "POST",
        body: { valid_until: "2027-10-12", notes: null },
      }),
    );
  });

  it("não envia sem validade, e diz o que falta", async () => {
    const user = userEvent.setup();
    montar(tela());

    await user.click(
      within(linha("PGR")).getByRole("button", { name: "Renovar" }),
    );
    await user.click(screen.getByRole("button", { name: "Renovar laudo" }));

    expect(
      await screen.findByText("Informe a nova validade."),
    ).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("409 mostra a frase da API e relê a lista — alguém renovou antes", async () => {
    const { ApiError } = await import("@/lib/api");
    request.mockRejectedValue(
      new ApiError(409, "Este laudo já foi renovado; o vigente é outro."),
    );
    const user = userEvent.setup();
    montar(tela());

    await user.click(
      within(linha("PGR")).getByRole("button", { name: "Renovar" }),
    );
    preencher("Nova validade", "2027-09-10");
    await user.click(screen.getByRole("button", { name: "Renovar laudo" }));

    expect(
      await screen.findByText("Este laudo já foi renovado; o vigente é outro."),
    ).toBeInTheDocument();
    expect(refresh).toHaveBeenCalled();
    // O formulário fecha: a linha que ele apontava não é mais a vigente.
    expect(screen.queryByLabelText("Nova validade")).toBeNull();
  });

  it("erro sem detalhe diz que nada foi alterado, sem inventar causa", async () => {
    const { ApiError } = await import("@/lib/api");
    request.mockRejectedValue(new ApiError(500, null));
    const user = userEvent.setup();
    montar(tela());

    await user.click(
      within(linha("PGR")).getByRole("button", { name: "Renovar" }),
    );
    preencher("Nova validade", "2027-09-10");
    await user.click(screen.getByRole("button", { name: "Renovar laudo" }));

    expect(
      await screen.findByText(
        "Não consegui renovar o laudo. Nada foi alterado.",
      ),
    ).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("cadastro do primeiro laudo", () => {
  it("cadastra com unidade, tipo, validade e observação, e relê", async () => {
    request.mockResolvedValue({});
    const user = userEvent.setup();
    montar(tela());

    await user.click(screen.getByRole("button", { name: "Novo laudo" }));
    await user.selectOptions(
      screen.getByLabelText("Unidade do laudo"),
      "Rodoviária",
    );
    await user.type(screen.getByLabelText("Tipo"), "pgr");
    preencher("Validade", "2027-01-31");
    await user.type(screen.getByLabelText("Observação (opcional)"), "Primeiro");
    await user.click(screen.getByRole("button", { name: "Cadastrar laudo" }));

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/dp/laudos", {
        method: "POST",
        body: {
          unit_id: UNIT_B,
          type: "pgr",
          valid_until: "2027-01-31",
          notes: "Primeiro",
        },
      }),
    );
    expect(refresh).toHaveBeenCalled();
  });

  it("sugere os três tipos sem fechar a lista — o tipo é texto livre", async () => {
    const user = userEvent.setup();
    montar(tela());

    await user.click(screen.getByRole("button", { name: "Novo laudo" }));

    expect(screen.getByLabelText("Tipo")).toHaveAttribute(
      "list",
      "laudo-tipos",
    );
    const sugestoes = document.getElementById("laudo-tipos");
    expect(
      [...(sugestoes?.querySelectorAll("option") ?? [])].map((o) => o.value),
    ).toEqual(["PCMSO", "PGR", "LTCAT+LTIP"]);
  });

  it("409 mostra a frase da API — o caminho certo é renovar", async () => {
    const { ApiError } = await import("@/lib/api");
    request.mockRejectedValue(
      new ApiError(409, "Já existe PGR vigente nesta unidade; renove-o."),
    );
    const user = userEvent.setup();
    montar(tela());

    await user.click(screen.getByRole("button", { name: "Novo laudo" }));
    await user.type(screen.getByLabelText("Tipo"), "PGR");
    preencher("Validade", "2027-01-31");
    await user.click(screen.getByRole("button", { name: "Cadastrar laudo" }));

    expect(
      await screen.findByText("Já existe PGR vigente nesta unidade; renove-o."),
    ).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("não envia sem tipo, e diz o que falta", async () => {
    const user = userEvent.setup();
    montar(tela());

    await user.click(screen.getByRole("button", { name: "Novo laudo" }));
    preencher("Validade", "2027-01-31");
    await user.click(screen.getByRole("button", { name: "Cadastrar laudo" }));

    expect(
      await screen.findByText("Informe o tipo do laudo."),
    ).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
  });
});

describe("estado vazio", () => {
  it("zero linhas com resposta ok é 'nenhum laudo vigente'", () => {
    montar(tela({ rows: [] }));

    expect(screen.getByText("Nenhum laudo vigente")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("⛔ vazio COM unidade escolhida fala da unidade, não de todas", () => {
    // O recorte já foi aplicado na consulta à view, então zero linhas aqui
    // significa "esta unidade não tem laudo". Dizer "as unidades que você
    // acompanha não têm" é falso sempre que as outras têm — e o gestor que
    // abriu o link de uma unidade é justamente quem lê essa frase.
    montar(tela({ rows: [] }), null, UNIT_A);

    expect(
      screen.getByText(/A unidade Aeroporto não tem laudo cadastrado/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/unidades que você acompanha/)).toBeNull();
  });

  it("✅ sem unidade escolhida, a frase continua sendo a de todas", () => {
    montar(tela({ rows: [] }), null, null);

    expect(
      screen.getByText(/As unidades que você acompanha não têm laudo/),
    ).toBeInTheDocument();
  });

  it("id de unidade que o seletor não conhece não vira uuid na tela", () => {
    // O link pode trazer uma unidade que este usuário não enxerga. Sem nome, a
    // frase volta a ser a genérica em vez de mostrar um identificador cru.
    montar(tela({ rows: [] }), null, "dddddddd-dddd-4ddd-8ddd-dddddddddddd");

    expect(
      screen.getByText(/As unidades que você acompanha não têm laudo/),
    ).toBeInTheDocument();
  });

  it("quem escreve é convidado a cadastrar; quem não escreve, não", () => {
    const { unmount } = montar(tela({ rows: [] }));
    expect(screen.getByText(/Cadastre o primeiro acima/)).toBeInTheDocument();
    unmount();

    montar(tela({ rows: [], can_write: false }));
    expect(screen.queryByText(/Cadastre o primeiro acima/)).toBeNull();
  });
});

describe('a janela de "a vencer" é declarada uma vez só', () => {
  it("⛔ a prosa lê o mesmo número que o tom — nenhuma das duas mente sozinha", () => {
    // O limiar mora em `DUE_SOON_DAYS`, que é de onde `dueTone` o lê. Um `30`
    // escrito à mão na frase seria a segunda declaração: mudar a janela para
    // 45 pintaria o badge novo e continuaria prometendo 30 ao gestor.
    montar(tela());

    expect(
      screen.getByText(new RegExp(`vence em até ${DUE_SOON_DAYS} dias`)),
    ).toBeInTheDocument();
    expect(dueTone(DUE_SOON_DAYS)).toBe("alert");
    expect(dueTone(DUE_SOON_DAYS + 1)).toBe("neutral");
  });
});

describe("cadastrar sem unidade no seletor", () => {
  it("diz o que falta em vez de não fazer nada", async () => {
    // Sem unidade visível o `select` nasce vazio e a validação recusa. Sem a
    // mensagem ligada ao campo, o clique em "Cadastrar laudo" era silencioso:
    // nada acontecia e nada era dito.
    const user = userEvent.setup();
    render(
      <ComplianceReports
        screen={tela()}
        units={[]}
        status={null}
        unitId={null}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Novo laudo" }));
    await user.type(screen.getByLabelText("Tipo"), "PGR");
    preencher("Validade", "2027-01-31");
    await user.click(screen.getByRole("button", { name: "Cadastrar laudo" }));

    expect(
      await screen.findByText("Escolha a unidade do laudo."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Unidade do laudo")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(request).not.toHaveBeenCalled();
  });

  it("com unidade escolhida a mensagem não aparece", () => {
    // O positivo ao lado do negativo: uma mensagem que aparecesse sempre seria
    // ruído em cima do formulário que funciona.
    montar(tela());

    expect(screen.queryByText("Escolha a unidade do laudo.")).toBeNull();
  });
});
