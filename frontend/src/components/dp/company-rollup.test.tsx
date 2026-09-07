import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CompanyRollup } from "@/components/dp/company-rollup";
import type { CompanyRollupResult } from "@/lib/dp/queries";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
}));

const FILTERS = { unitId: null, companyId: null };

const UM = "11111111-1111-4111-8111-111111111111";
const DOIS = "22222222-2222-4222-8222-222222222222";

function rollup(): CompanyRollupResult {
  return {
    status: "ok",
    rows: [
      {
        companyId: DOIS,
        companyName: "Dev Dois",
        activeHeadcount: 14,
        basePayroll: "37140.00",
      },
      {
        companyId: UM,
        companyName: "Dev Um",
        activeHeadcount: 28,
        basePayroll: "72244.00",
      },
    ],
  };
}

function row(name: RegExp): HTMLElement {
  const cell = screen.getByText(name);
  const tr = cell.closest("tr");

  expect(tr).not.toBeNull();
  return tr as HTMLElement;
}

describe("resumo financeiro por empresa", () => {
  it("traz ativos e folha base de cada empresa", () => {
    render(
      <CompanyRollup
        rollup={rollup()}
        basePayroll="109384.00"
        filters={FILTERS}
      />,
    );

    expect(within(row(/Dev Um/)).getByText("28")).toBeVisible();
    expect(within(row(/Dev Um/)).getByText(/72\.244,00/)).toBeVisible();
    expect(within(row(/Dev Dois/)).getByText("14")).toBeVisible();
    expect(within(row(/Dev Dois/)).getByText(/37\.140,00/)).toBeVisible();
  });

  it("ordena pela folha, e não pela ordem em que as leituras voltaram", () => {
    render(
      <CompanyRollup
        rollup={rollup()}
        basePayroll="109384.00"
        filters={FILTERS}
      />,
    );

    const nomes = screen
      .getAllByRole("row")
      .slice(1)
      .map((linha) => linha.textContent);

    expect(nomes[0]).toMatch(/Dev Um/);
    expect(nomes[1]).toMatch(/Dev Dois/);
  });

  it("a linha abre o painel recortado na empresa, e larga a unidade", () => {
    push.mockClear();
    render(
      <CompanyRollup
        rollup={rollup()}
        basePayroll="109384.00"
        filters={{
          unitId: "44444444-4444-4444-8444-444444444444",
          companyId: null,
        }}
      />,
    );

    fireEvent.click(row(/Dev Um/));

    // A unidade do recorte anterior é de outra empresa: mantê-la devolveria um
    // painel vazio com dois filtros que se contradizem.
    expect(push).toHaveBeenCalledWith(`/dashboard/dp/painel?emp=${UM}`);
  });

  it("diz que as linhas somam a folha base quando somam", () => {
    render(
      <CompanyRollup
        rollup={rollup()}
        basePayroll="109384.00"
        filters={FILTERS}
      />,
    );

    expect(screen.getByText(/a mesma folha base do recorte/i)).toBeVisible();
    expect(screen.queryByText(/faltam/i)).toBeNull();
  });

  it("declara a diferença quando as linhas NÃO somam a folha base", () => {
    // A lista de empresas sai de `vw_unit`: quem está numa empresa sem unidade
    // ativa entra na folha base e não tem linha aqui. Uma tabela que soma menos
    // que o cartão acima, calada, é a classe de defeito que derruba a confiança
    // no painel inteiro.
    render(
      <CompanyRollup
        rollup={rollup()}
        basePayroll="120000.00"
        filters={FILTERS}
      />,
    );

    const rodape = screen.getByText(/faltam/i);
    expect(rodape).toHaveTextContent(/109\.384,00/);
    expect(rodape).toHaveTextContent(/120\.000,00/);
    expect(rodape).toHaveTextContent(/10\.616,00/);
    expect(screen.queryByText(/a mesma folha base do recorte/i)).toBeNull();
  });

  it("uma empresa que falhou tira a tabela inteira, não uma linha", () => {
    render(
      <CompanyRollup
        rollup={{ status: "unavailable" }}
        basePayroll="109384.00"
        filters={FILTERS}
      />,
    );

    expect(screen.getByText(/não pôde ser montado/i)).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
    // O positivo do outro lado: com as leituras de pé, a tabela existe.
    expect(screen.queryByText(/Dev Um/)).toBeNull();
  });
});
