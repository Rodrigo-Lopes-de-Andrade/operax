import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BenefitBreakdown, PanelKpis } from "@/components/dp/panel-kpis";
import type { DpPanelKpis } from "@/lib/dp/queries";

/**
 * O payload de `GET /dp/painel`. A folha base fecha na conta do raio-X:
 * 109.384,00 − 9.384,00 − 4.000,00 = 96.000,00.
 */
function kpis(overrides: Partial<DpPanelKpis> = {}): DpPanelKpis {
  return {
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
    ...overrides,
  };
}

function card(eyebrow: RegExp): HTMLElement {
  const label = screen.getByText(eyebrow);
  const section = label.closest("section");

  expect(section).not.toBeNull();
  return section as HTMLElement;
}

describe("os nove KPIs de topo", () => {
  it("mostra os nove, com o número que o backend mandou", () => {
    render(<PanelKpis kpis={kpis()} />);

    expect(within(card(/^total analisado$/i)).getByText("42")).toBeVisible();
    expect(within(card(/^efetivo ativo$/i)).getByText("40")).toBeVisible();
    expect(within(card(/^desligamentos$/i)).getByText("2")).toBeVisible();
    expect(within(card(/^retenção$/i)).getByText("95,2%")).toBeVisible();
    expect(
      within(card(/^folha salarial base$/i)).getByText(/109\.384,00/),
    ).toBeVisible();
    expect(
      within(card(/^média \(folha base\)$/i)).getByText(/2\.734,60/),
    ).toBeVisible();
    expect(
      within(card(/^vale refeição \(VR\)$/i)).getByText(/1\.500,00/),
    ).toBeVisible();
    expect(
      within(card(/^ajuda de custo$/i)).getByText(/9\.384,00/),
    ).toBeVisible();
    expect(
      within(card(/^cargo de confiança \+ periculosidade$/i)).getByText(
        /4\.000,00/,
      ),
    ).toBeVisible();
  });

  it("a retenção diz que não é retenção por período", () => {
    render(<PanelKpis kpis={kpis()} />);

    // Transcrita do legado por decisão do dono; o rótulo é canetada pendente.
    // Enquanto isso a nota impede que 100% seja lido como "ninguém saiu".
    expect(card(/^retenção$/i)).toHaveTextContent(/ativos ÷ total no filtro/i);
    expect(card(/^retenção$/i)).toHaveTextContent(
      /não é retenção por período/i,
    );
  });

  it("base vazia mostra travessão na retenção, e não 0%", () => {
    render(<PanelKpis kpis={kpis({ retention: null })} />);

    expect(within(card(/^retenção$/i)).getByText("—")).toBeVisible();
  });

  it("a média conta quem ficou de fora da soma — e diz quando não há ninguém", () => {
    const { unmount } = render(
      <PanelKpis kpis={kpis({ without_salary: 0 })} />,
    );

    expect(card(/^média \(folha base\)$/i)).toHaveTextContent(
      /todos os ativos do recorte têm faixa salarial vigente/i,
    );
    unmount();

    render(<PanelKpis kpis={kpis({ without_salary: 5 })} />);
    expect(card(/^média \(folha base\)$/i)).toHaveTextContent(
      /5 ativos não têm faixa salarial vigente/i,
    );
  });

  it("um sozinho não vira 'ativos'", () => {
    render(<PanelKpis kpis={kpis({ without_salary: 1 })} />);

    expect(card(/^média \(folha base\)$/i)).toHaveTextContent(
      /1 ativo não tem faixa salarial vigente/i,
    );
  });

  it("o cartão de sinistro é contagem, e diz que o nome não sai aqui", () => {
    render(<PanelKpis kpis={kpis()} />);

    const sinistro = card(/unidades com sinistro ativo/i);
    expect(within(sinistro).getByText("3")).toBeVisible();
    expect(sinistro).toHaveTextContent(/só a contagem/i);
    expect(sinistro).toHaveTextContent(/ficha da pessoa/i);
  });

  it("o bloco inteiro não tem tabela nem link — é número e nada mais", () => {
    const { container } = render(<PanelKpis kpis={kpis()} />);

    expect(container.querySelectorAll("table")).toHaveLength(0);
    expect(container.querySelectorAll("a")).toHaveLength(0);
  });
});

/** A linha do raio-X, achada pelo rótulo: valor e fatia no mesmo `div`. */
function line(label: RegExp): HTMLElement {
  const term = screen.getByText(label);
  const row = term.closest("div");

  expect(row).not.toBeNull();
  return row as HTMLElement;
}

describe("raio-X de benefícios", () => {
  it("a composição fecha na folha base", () => {
    render(<BenefitBreakdown kpis={kpis()} />);

    // 96.000,00 é o resto: base − ajuda de custo − cargo/periculosidade.
    expect(line(/salário e demais verbas da base/i)).toHaveTextContent(
      /96\.000,00/,
    );
    expect(line(/^ajuda de custo$/i)).toHaveTextContent(/9\.384,00/);
    expect(line(/^cargo de confiança \+ periculosidade$/i)).toHaveTextContent(
      /4\.000,00/,
    );
    expect(line(/^folha salarial base$/i)).toHaveTextContent(/109\.384,00/);
  });

  it("mostra a fatia de cada verba dentro da base", () => {
    render(<BenefitBreakdown kpis={kpis()} />);

    expect(line(/salário e demais verbas da base/i)).toHaveTextContent("88%");
    expect(line(/^ajuda de custo$/i)).toHaveTextContent("9%");
    expect(line(/^cargo de confiança \+ periculosidade$/i)).toHaveTextContent(
      "4%",
    );
  });

  it("o resto não se chama salário — o conjunto da base é configurável", () => {
    render(<BenefitBreakdown kpis={kpis()} />);

    // `benefit_type.composes_base` é coluna que o cliente edita: uma nona verba
    // marcada como base entraria nesta linha, e chamá-la de "salário" passaria a
    // mentir sem que nada quebrasse.
    expect(screen.getByText(/salário e demais verbas da base/i)).toBeVisible();
  });

  it("o VR aparece marcado como fora da base", () => {
    render(<BenefitBreakdown kpis={kpis()} />);

    expect(screen.getByText(/fora da base/i)).toBeVisible();
    expect(line(/vale refeição \(VR\)/i)).toHaveTextContent(/1\.500,00/);
  });

  it("declara os seis itens do raio-X do legado que não têm fonte", () => {
    render(<BenefitBreakdown kpis={kpis()} />);

    const ausentes =
      /usuários de vale[\s\S]*odontológico[\s\S]*plano de saúde[\s\S]*dependentes[\s\S]*vínculos em saúde[\s\S]*VR\/cesta/i;
    expect(screen.getByText(ausentes)).toBeVisible();
    // ⛔ E não aparecem como zero: um número errado é pior que a ausência dita.
    expect(screen.queryByText(/^0$/)).toBeNull();
  });

  it("folha zerada não inventa porcentagem", () => {
    render(
      <BenefitBreakdown
        kpis={kpis({
          base_payroll: "0",
          cost_allowance: "0",
          trust_and_hazard: "0",
        })}
      />,
    );

    expect(screen.queryByText(/%$/)).toBeNull();
  });
});
