import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PanelScreen } from "@/components/dp/panel-screen";
import type {
  AlertsResult,
  CompanyRollupResult,
  DpPanelKpis,
  PanelResult,
} from "@/lib/dp/queries";
import type { UnitOption } from "@/lib/ponto/queries";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const EMPRESA = "11111111-1111-4111-8111-111111111111";
const UNIDADE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

const FILTERS = { unitId: null, companyId: null };

const UNITS: UnitOption[] = [
  {
    unitId: UNIDADE,
    code: "NOR",
    slug: "nor",
    name: "Shopping Norte",
    companyId: EMPRESA,
    companyName: "Dev Um",
    companySlug: "dev-um",
  },
];

const COMPANIES = [{ id: EMPRESA, name: "Dev Um" }];

const KPIS: DpPanelKpis = {
  on: "2026-09-07",
  total_analyzed: 42,
  active_headcount: 40,
  terminations: 2,
  retention: "0.9524",
  base_payroll: "109384.00",
  base_payroll_average: "2734.60",
  meal_voucher: "1500.00",
  cost_allowance: "9384.00",
  trust_and_hazard: "4000.00",
  without_salary: 0,
  units_with_open_installment: 3,
};

const ALERTS: AlertsResult = {
  status: "ok",
  counts: {
    birthday_month: 3,
    probation: 2,
    document_expired: 26,
    document_expiring: 25,
    exam_due: 18,
    vacation_upcoming: 4,
    vacation_today: 1,
    vacation_limit: 7,
  },
};

const ROLLUP: CompanyRollupResult = {
  status: "ok",
  rows: [
    {
      companyId: EMPRESA,
      companyName: "Dev Um",
      activeHeadcount: 40,
      basePayroll: "109384.00",
    },
  ],
};

function screenWith(panel: PanelResult, rollup: CompanyRollupResult | null) {
  return render(
    <PanelScreen
      panel={panel}
      alerts={ALERTS}
      rollup={rollup}
      filters={FILTERS}
      companies={COMPANIES}
      units={UNITS}
    />,
  );
}

describe("painel de DP — o que cada um vê", () => {
  it("com o domínio de remuneração, os dois lados aparecem", () => {
    screenWith({ status: "ok", kpis: KPIS }, ROLLUP);

    // Caminho 2 — os nove KPIs, o raio-X e o consolidado.
    expect(screen.getByText(/^total analisado$/i)).toBeVisible();
    expect(screen.getByText(/raio-x de benefícios/i)).toBeVisible();
    expect(screen.getByText(/resumo financeiro por empresa/i)).toBeVisible();
    expect(screen.getByText(/posição de 07\/09\/2026/i)).toBeVisible();
    // Caminho 1 — os oito contadores.
    expect(screen.getByText(/painel de alertas/i)).toBeVisible();
  });

  it("sem o domínio, o dinheiro simplesmente não existe — e os alertas ficam", () => {
    screenWith({ status: "forbidden" }, null);

    // ⛔ O NEGATIVO
    expect(screen.queryByText(/^total analisado$/i)).toBeNull();
    expect(screen.queryByText(/^efetivo ativo$/i)).toBeNull();
    expect(screen.queryByText(/raio-x de benefícios/i)).toBeNull();
    expect(screen.queryByText(/resumo financeiro por empresa/i)).toBeNull();
    expect(screen.queryByText(/unidades com sinistro ativo/i)).toBeNull();

    // ✅ O POSITIVO AO LADO — sem ele o teste ficaria verde numa tela vazia.
    expect(screen.getByText(/painel de alertas/i)).toBeVisible();
    expect(screen.getByText(/documentos vencidos/i)).toBeVisible();
    expect(screen.getByText("26")).toBeVisible();
  });

  it("sem o domínio não há cadeado, cinza nem aviso de permissão", () => {
    const { container } = screenWith({ status: "forbidden" }, null);

    // Regra 5 do projeto: quem não pode, não vê. Contar ao usuário o que ele
    // não alcança é a mesma coisa que mostrar o cadeado, com outras palavras.
    expect(container.textContent).not.toMatch(/permiss/i);
    expect(container.textContent).not.toMatch(/acesso/i);
    expect(container.textContent).not.toMatch(/remuneração/i);
    expect(container.textContent).not.toMatch(/não puderam ser lidos/i);
  });

  it("API fora do ar é erro visível, e não a mesma coisa que 403", () => {
    screenWith({ status: "unavailable" }, null);

    expect(screen.getByText(/não puderam ser lidos/i)).toBeVisible();
    // Continua sem inventar número nenhum de folha.
    expect(screen.queryByText(/^total analisado$/i)).toBeNull();
    // E a metade que respondeu continua na tela.
    expect(screen.getByText(/painel de alertas/i)).toBeVisible();
  });

  it("os alertas caídos não derrubam os KPIs, e vice-versa", () => {
    render(
      <PanelScreen
        panel={{ status: "ok", kpis: KPIS }}
        alerts={{ status: "unavailable" }}
        rollup={ROLLUP}
        filters={FILTERS}
        companies={COMPANIES}
        units={UNITS}
      />,
    );

    expect(screen.getByText(/^total analisado$/i)).toBeVisible();
    expect(
      screen.getByText(/os contadores não puderam ser lidos/i),
    ).toBeVisible();
  });

  it("o recorte fica na query string, nos dois seletores", () => {
    screenWith({ status: "ok", kpis: KPIS }, ROLLUP);

    const empresa = screen.getByRole("combobox", { name: /empresa/i });
    const unidade = screen.getByRole("combobox", { name: /unidade/i });

    expect(
      within(empresa).getByRole("option", { name: "Dev Um" }),
    ).toBeVisible();
    expect(
      within(unidade).getByRole("option", { name: "Shopping Norte" }),
    ).toBeVisible();
  });

  it("recorte aplicado mostra a saída, e recorte vazio não mostra", () => {
    const { unmount } = render(
      <PanelScreen
        panel={{ status: "ok", kpis: KPIS }}
        alerts={ALERTS}
        rollup={null}
        filters={{ unitId: UNIDADE, companyId: EMPRESA }}
        companies={COMPANIES}
        units={UNITS}
      />,
    );

    expect(
      screen.getByRole("link", { name: /limpar recorte/i }),
    ).toHaveAttribute("href", "/dashboard/dp/painel");
    unmount();

    screenWith({ status: "ok", kpis: KPIS }, ROLLUP);
    expect(screen.queryByRole("link", { name: /limpar recorte/i })).toBeNull();
  });

  it("a porta do ciclo mensal aparece para quem o painel abriu", () => {
    // As duas telas exigem `permissoes.compensation`, no mesmo
    // `check_permissions`: um painel `ok` é a prova de que o ciclo abre.
    screenWith({ status: "ok", kpis: KPIS }, ROLLUP);

    expect(screen.getByRole("link", { name: /ciclo mensal/i })).toHaveAttribute(
      "href",
      "/dashboard/dp/ciclos",
    );
  });

  it("e não aparece para quem não tem o domínio — link que leva a 404 é pior que link nenhum", () => {
    screenWith({ status: "forbidden" }, null);

    expect(screen.queryByRole("link", { name: /ciclo mensal/i })).toBeNull();
    // O positivo ao lado: a tela dele continua existindo inteira.
    expect(screen.getByText(/painel de alertas/i)).toBeVisible();
  });

  it("API fora do ar também não oferece a porta: ninguém sabe se ela abre", () => {
    screenWith({ status: "unavailable" }, null);

    expect(screen.queryByRole("link", { name: /ciclo mensal/i })).toBeNull();
  });

  it("nenhum nome de colaborador chega à tela, em nenhum dos dois caminhos", () => {
    const { container } = screenWith({ status: "ok", kpis: KPIS }, ROLLUP);

    // O painel do sistema atual nomeia quem tem parcela em aberto na abertura.
    // Aqui os dois contratos devolvem só número, e a tela não tem de onde tirar
    // um nome — este teste é o que mantém isso verdadeiro quando alguém mudar
    // o payload.
    expect(container.textContent).toMatch(/só a contagem/i);
    expect(screen.queryByRole("table", { name: /colaborador/i })).toBeNull();
  });
});
