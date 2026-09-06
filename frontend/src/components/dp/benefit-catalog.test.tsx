import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BenefitCatalog } from "@/components/dp/benefit-catalog";
import type {
  BenefitCatalog as Catalog,
  BenefitTypeRow,
} from "@/lib/dp/queries";

const request = vi.fn();
const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    requestApiAsUser: (...args: unknown[]) => request(...args),
  };
});

const SAUDE: BenefitTypeRow = {
  code: "health_plan",
  name: "Plano de saúde",
  composes_base: false,
  calculation: "fixed_amount",
  domain: "compensation",
  active: true,
};

const VT: BenefitTypeRow = {
  code: "transport_voucher",
  name: "Vale transporte",
  composes_base: false,
  calculation: "fixed_amount",
  domain: "compensation",
  active: true,
};

const AJUDA: BenefitTypeRow = {
  code: "cost_allowance",
  name: "Ajuda de custo",
  composes_base: true,
  calculation: "fixed_amount",
  domain: "compensation",
  active: true,
};

const FILTERS = { type: null, on: null };

function catalogo(overrides: Partial<Catalog> = {}): Catalog {
  return {
    on: "2026-09-06",
    can_write: true,
    types: [SAUDE, VT, AJUDA],
    plans: [
      {
        id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        benefit_type_code: "health_plan",
        code: "ENF",
        provider: "Unimed",
        name: "Enfermaria",
        amount: "180.00",
        effective_from: "2026-01-01",
        effective_to: null,
        reason: null,
      },
    ],
    fares: [
      {
        id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        code: "ONIBUS",
        name: "Ônibus",
        kind: "round_trip",
        amount: "9.60",
        effective_from: "2026-01-01",
        effective_to: null,
        reason: "Cadastro inicial",
      },
    ],
    ...overrides,
  };
}

/**
 * `date` e `number` do jsdom recusam valor parcial: digitados caractere a
 * caractere, "2026-09-01" nunca chega a ser data válida e "190.00" perde as
 * casas em "190." — o teste mediria a sanitização do jsdom, não a tela.
 */
function preencher(label: string, valor: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value: valor } });
}

beforeEach(() => {
  request.mockReset();
  push.mockReset();
});

describe("o valor vigente não é editável", () => {
  it("mostra o preço como texto, sem campo e sem lápis", () => {
    render(
      <BenefitCatalog catalog={catalogo()} filters={FILTERS} type={SAUDE} />,
    );

    const tabela = screen.getByRole("table", {
      name: "Preços vigentes de Plano de saúde",
    });

    expect(within(tabela).getByText("R$ 180,00")).toBeInTheDocument();
    expect(within(tabela).queryByRole("textbox")).not.toBeInTheDocument();
    expect(within(tabela).queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /editar|salvar valor|corrigir/i }),
    ).not.toBeInTheDocument();
    // O positivo do par: a ação existe, e ela é a de abrir vigência nova.
    expect(
      within(tabela).getByRole("button", { name: "Reajustar" }),
    ).toBeInTheDocument();
  });

  it("o reajuste abre um valor em branco, não o valor de hoje pré-carregado", async () => {
    const user = userEvent.setup();
    render(
      <BenefitCatalog catalog={catalogo()} filters={FILTERS} type={SAUDE} />,
    );

    await user.click(screen.getByRole("button", { name: "Reajustar" }));

    // Um campo já preenchido com 180,00 é a tela dizendo "corrija aqui"; ela
    // não corrige, ela abre a próxima vigência.
    expect(screen.getByLabelText("Novo valor")).toHaveValue(null);
    expect(screen.getByLabelText("Desde")).toHaveValue("");
  });
});

describe("reajustar é vigência nova", () => {
  it("manda alvo, código e a data de início — e nenhum id de linha", async () => {
    request.mockResolvedValue({
      target: "plan",
      code: "ENF",
      kind: null,
      name: "Enfermaria",
      amount: "190.00",
      effective_from: "2026-09-01",
      previous_amount: "180.00",
      previous_effective_to: "2026-08-31",
    });
    const user = userEvent.setup();
    render(
      <BenefitCatalog catalog={catalogo()} filters={FILTERS} type={SAUDE} />,
    );

    await user.click(screen.getByRole("button", { name: "Reajustar" }));
    preencher("Desde", "2026-09-01");
    preencher("Novo valor", "190.00");
    await user.type(screen.getByLabelText("Motivo"), "Reajuste anual");
    await user.click(
      screen.getByRole("button", { name: "Registrar reajuste" }),
    );

    // O corpo inteiro, e não uma parte dele: um `id` a mais aqui seria pedir
    // uma edição da faixa publicada, que é o que esta tela existe para não
    // permitir.
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/dp/beneficios/reajuste", {
        method: "POST",
        body: {
          target: "plan",
          code: "ENF",
          kind: null,
          effective_from: "2026-09-01",
          amount: "190.00",
          reason: "Reajuste anual",
        },
      }),
    );
  });

  it("confirma o que mudou com as duas faixas, como o gestor confere", async () => {
    request.mockResolvedValue({
      target: "plan",
      code: "ENF",
      kind: null,
      name: "Enfermaria",
      amount: "190.00",
      effective_from: "2026-09-01",
      previous_amount: "180.00",
      previous_effective_to: "2026-08-31",
    });
    const user = userEvent.setup();
    render(
      <BenefitCatalog catalog={catalogo()} filters={FILTERS} type={SAUDE} />,
    );

    await user.click(screen.getByRole("button", { name: "Reajustar" }));
    preencher("Desde", "2026-09-01");
    preencher("Novo valor", "190.00");
    await user.click(
      screen.getByRole("button", { name: "Registrar reajuste" }),
    );

    expect(
      await screen.findByText(
        "R$ 180,00 até 31/08/2026, R$ 190,00 a partir de 01/09/2026.",
      ),
    ).toBeInTheDocument();
  });

  it("a tarifa reajustada leva o tipo junto — sem ele subiria a outra", async () => {
    request.mockResolvedValue({
      target: "fare",
      code: "ONIBUS",
      kind: "round_trip",
      name: "Ônibus",
      amount: "10.20",
      effective_from: "2026-09-01",
      previous_amount: "9.60",
      previous_effective_to: "2026-08-31",
    });
    const user = userEvent.setup();
    render(<BenefitCatalog catalog={catalogo()} filters={FILTERS} type={VT} />);

    await user.click(screen.getByRole("button", { name: "Reajustar" }));
    preencher("Desde", "2026-09-01");
    preencher("Novo valor", "10.20");
    await user.click(
      screen.getByRole("button", { name: "Registrar reajuste" }),
    );

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/dp/beneficios/reajuste", {
        method: "POST",
        body: {
          target: "fare",
          code: "ONIBUS",
          kind: "round_trip",
          effective_from: "2026-09-01",
          amount: "10.20",
          reason: null,
        },
      }),
    );
  });

  it("mostra a recusa do backend em vez de engolir o motivo", async () => {
    const { ApiError } = await import("@/lib/api");
    request.mockRejectedValue(
      new ApiError(
        422,
        "a vigência nova começa antes da faixa aberta; escolha uma data posterior",
      ),
    );
    const user = userEvent.setup();
    render(
      <BenefitCatalog catalog={catalogo()} filters={FILTERS} type={SAUDE} />,
    );

    await user.click(screen.getByRole("button", { name: "Reajustar" }));
    preencher("Desde", "2025-01-01");
    preencher("Novo valor", "190.00");
    await user.click(
      screen.getByRole("button", { name: "Registrar reajuste" }),
    );

    expect(
      await screen.findByText(
        "a vigência nova começa antes da faixa aberta; escolha uma data posterior",
      ),
    ).toBeInTheDocument();
  });
});

describe("criar a primeira vigência é caminho próprio", () => {
  it("um tipo sem preço oferece cadastrar, e não tem o que reajustar", () => {
    render(
      <BenefitCatalog catalog={catalogo()} filters={FILTERS} type={AJUDA} />,
    );

    expect(
      screen.getByText("Nenhum plano cadastrado em 06/09/2026"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Cadastrar o primeiro plano" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Reajustar" }),
    ).not.toBeInTheDocument();
  });

  it("sem tarifa, a tela diz que a apuração do vale transporte recusa", () => {
    render(
      <BenefitCatalog
        catalog={catalogo({ fares: [] })}
        filters={FILTERS}
        type={VT}
      />,
    );

    expect(
      screen.getByText("Nenhuma tarifa cadastrada em 06/09/2026"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /a apuração do mês recusa por falta de valor de ida e volta/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Cadastrar a primeira tarifa" }),
    ).toBeInTheDocument();
  });

  it("cadastra o primeiro plano na rota de criação, com o tipo da aba", async () => {
    request.mockResolvedValue({
      target: "plan",
      code: "AJC",
      kind: null,
      name: "Ajuda padrão",
      amount: "250.00",
      effective_from: "2026-09-01",
    });
    const user = userEvent.setup();
    render(
      <BenefitCatalog catalog={catalogo()} filters={FILTERS} type={AJUDA} />,
    );

    await user.click(
      screen.getByRole("button", { name: "Cadastrar o primeiro plano" }),
    );
    await user.type(screen.getByLabelText("Código"), "AJC");
    await user.type(screen.getByLabelText("Nome"), "Ajuda padrão");
    await user.type(screen.getByLabelText("Operadora"), "Interna");
    preencher("Desde", "2026-09-01");
    preencher("Valor", "250.00");
    await user.click(screen.getByRole("button", { name: "Cadastrar plano" }));

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/dp/beneficios/planos", {
        method: "POST",
        body: {
          benefit_type_code: "cost_allowance",
          code: "AJC",
          provider: "Interna",
          name: "Ajuda padrão",
          effective_from: "2026-09-01",
          amount: "250.00",
          reason: null,
        },
      }),
    );
  });

  it("cadastra a primeira tarifa com o tipo, na rota de tarifa", async () => {
    request.mockResolvedValue({
      target: "fare",
      code: "METRO",
      kind: "round_trip",
      name: "Metrô",
      amount: "11.00",
      effective_from: "2026-09-01",
    });
    const user = userEvent.setup();
    render(
      <BenefitCatalog
        catalog={catalogo({ fares: [] })}
        filters={FILTERS}
        type={VT}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "Cadastrar a primeira tarifa" }),
    );
    await user.type(screen.getByLabelText("Código da linha"), "METRO");
    await user.type(screen.getByLabelText("Nome"), "Metrô");
    preencher("Desde", "2026-09-01");
    preencher("Valor", "11.00");
    await user.click(screen.getByRole("button", { name: "Cadastrar tarifa" }));

    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/dp/beneficios/tarifas", {
        method: "POST",
        body: {
          code: "METRO",
          name: "Metrô",
          kind: "round_trip",
          effective_from: "2026-09-01",
          amount: "11.00",
          reason: null,
        },
      }),
    );
  });

  it("a criação não tem campo de fim de vigência", async () => {
    const user = userEvent.setup();
    render(
      <BenefitCatalog catalog={catalogo()} filters={FILTERS} type={AJUDA} />,
    );

    await user.click(
      screen.getByRole("button", { name: "Cadastrar o primeiro plano" }),
    );

    // Uma vigência nasce aberta. Um campo de fim aqui convidaria a cadastrar um
    // preço que já nasce vencido.
    expect(screen.getByLabelText("Desde")).toBeInTheDocument();
    expect(screen.queryByLabelText(/até|fim/i)).not.toBeInTheDocument();
  });
});

describe("o catálogo é lido numa data", () => {
  it("diz de quando são os valores e leva a data para o link", () => {
    render(
      <BenefitCatalog catalog={catalogo()} filters={FILTERS} type={SAUDE} />,
    );

    expect(
      screen.getByText(/Os valores abaixo são os que valiam em 06\/09\/2026/),
    ).toBeInTheDocument();

    preencher("Data da vigência consultada", "2026-08-31");

    expect(push).toHaveBeenLastCalledWith(
      "/dashboard/administracao/beneficios?em=2026-08-31",
    );
  });
});

describe("quem só lê o catálogo não vê ação de escrita", () => {
  it("sem can_write não há reajuste nem cadastro — e os preços continuam", () => {
    render(
      <BenefitCatalog
        catalog={catalogo({ can_write: false })}
        filters={FILTERS}
        type={SAUDE}
      />,
    );

    expect(screen.getByText("R$ 180,00")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Reajustar" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Cadastrar plano" }),
    ).not.toBeInTheDocument();
  });
});
