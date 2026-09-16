import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TelegramAdhesion } from "@/components/canais/telegram-adhesion";
import type { TelegramAdhesionRow } from "@/lib/canais/queries";

/**
 * Nomes de unidade inventados, e contagens escolhidas para que a soma NÃO
 * seja óbvia: linhas com zero em colunas diferentes, para que um total que
 * somasse só duas colunas — ou mostrasse `joined` — caia em alguma linha.
 */
const ROWS: TelegramAdhesionRow[] = [
  {
    unit_id: "11111111-1111-4111-8111-111111111111",
    unit_name: "Unidade Zz Alfa",
    joined: 3,
    pending: 0,
    revoked: 1,
  },
  {
    unit_id: "22222222-2222-4222-8222-222222222222",
    unit_name: "Unidade Zz Beta",
    joined: 0,
    pending: 7,
    revoked: 0,
  },
  {
    unit_id: "33333333-3333-4333-8333-333333333333",
    unit_name: "Unidade Zz Gama",
    joined: 2,
    pending: 2,
    revoked: 2,
  },
  {
    unit_id: "44444444-4444-4444-8444-444444444444",
    unit_name: "Unidade Zz Delta",
    joined: 0,
    pending: 0,
    revoked: 0,
  },
];

function tabela() {
  return screen.getByRole("table", { name: "Adesão ao Telegram por unidade" });
}

/** As linhas do corpo — nem o cabeçalho nem o rodapé. */
function corpo() {
  return within(tabela().querySelector("tbody")!).getAllByRole("row");
}

function rodape() {
  return within(tabela().querySelector("tfoot")!).getByRole("row");
}

/** As células de uma linha como texto, na ordem das colunas. */
function celulas(row: HTMLElement): string[] {
  return within(row)
    .getAllByRole("cell")
    .map((cell) => cell.textContent ?? "");
}

describe("critério 5 — a adesão por unidade: linhas, colunas, soma", () => {
  it('✅ uma linha por unidade, contada por `role="row"` no corpo, com o nome da unidade como cabeçalho da linha', () => {
    render(<TelegramAdhesion rows={ROWS} />);

    const linhas = corpo();
    expect(linhas).toHaveLength(4);
    expect(
      linhas.map((row) => within(row).getByRole("rowheader").textContent),
    ).toEqual([
      "Unidade Zz Alfa",
      "Unidade Zz Beta",
      "Unidade Zz Gama",
      "Unidade Zz Delta",
    ]);
  });

  it("⛔ as colunas são 'Aderiram', 'Não aderiram', 'Revogaram' e 'Total' — nunca 'pendentes' nem 'faltam'", () => {
    // Decisão do dono, 16/09/2026: a adesão é voluntária. `pending` da RPC é
    // "não aderiram" na tela — um número, não uma pendência.
    const { container } = render(<TelegramAdhesion rows={ROWS} />);

    expect(
      within(tabela())
        .getAllByRole("columnheader")
        .map((th) => th.textContent),
    ).toEqual(["Unidade", "Aderiram", "Não aderiram", "Revogaram", "Total"]);
    expect(container.textContent).not.toMatch(
      /pendente|faltam|falta |lembrete|aguardando/i,
    );
  });

  it("⛔ FALSO VERDE: o total de cada linha é a soma das TRÊS colunas dela — com zeros em lugares diferentes", () => {
    render(<TelegramAdhesion rows={ROWS} />);

    const [alfa, beta, gama, delta] = corpo();
    // 3 + 0 + 1: um total que somasse só aderiram+não aderiram daria 3.
    expect(celulas(alfa)).toEqual(["3", "0", "1", "4"]);
    // 0 + 7 + 0: um total que mostrasse `joined` daria 0.
    expect(celulas(beta)).toEqual(["0", "7", "0", "7"]);
    // 2 + 2 + 2: um total que somasse duas daria 4.
    expect(celulas(gama)).toEqual(["2", "2", "2", "6"]);
    // 0 + 0 + 0: a unidade sem ninguém ativo mostra zero, e não some.
    expect(celulas(delta)).toEqual(["0", "0", "0", "0"]);
  });

  it("⛔ o rodapé soma cada coluna, e o total do rodapé é a soma dos totais", () => {
    render(<TelegramAdhesion rows={ROWS} />);

    const total = rodape();
    expect(within(total).getByRole("rowheader")).toHaveTextContent("Total");
    // 3+0+2+0 = 5 · 0+7+2+0 = 9 · 1+0+2+0 = 3 · 5+9+3 = 17
    expect(celulas(total)).toEqual(["5", "9", "3", "17"]);
  });

  it("⛔ os números são os da prop, não de uma tabela escrita à mão", () => {
    render(
      <TelegramAdhesion
        rows={[{ ...ROWS[0], joined: 11, pending: 13, revoked: 17 }]}
      />,
    );

    expect(celulas(corpo()[0])).toEqual(["11", "13", "17", "41"]);
    expect(celulas(rodape())).toEqual(["11", "13", "17", "41"]);
  });

  it("os milhares saem em pt-BR", () => {
    render(
      <TelegramAdhesion
        rows={[{ ...ROWS[0], joined: 1200, pending: 0, revoked: 0 }]}
      />,
    );

    expect(celulas(corpo()[0])).toEqual(["1.200", "0", "0", "1.200"]);
  });

  it("as linhas saem na ordem em que a RPC as entregou", () => {
    render(<TelegramAdhesion rows={[ROWS[2], ROWS[0]]} />);

    expect(
      corpo().map((row) => within(row).getByRole("rowheader").textContent),
    ).toEqual(["Unidade Zz Gama", "Unidade Zz Alfa"]);
  });

  it("⛔ sem nome de pessoa e sem `chat_id`: o DOM tem unidades e números, e é só", () => {
    // O contrato da RPC não tem por onde eles chegarem; o teste prende que a
    // tela também não os inventa — nem em atributo, nem em texto escondido.
    const { container } = render(<TelegramAdhesion rows={ROWS} />);

    expect(container.innerHTML).not.toMatch(/chat_id|chat-id|employee|cpf/i);
    // Os ids de unidade também não vão para o DOM: são `key`, não conteúdo.
    expect(container.innerHTML).not.toContain(ROWS[0].unit_id);
  });
});

describe("critério 5 — os dois estados sem tabela", () => {
  it("lista vazia → 'Nenhuma unidade com colaboradores.', e nenhuma tabela", () => {
    render(<TelegramAdhesion rows={[]} />);

    expect(
      screen.getByText("Nenhuma unidade com colaboradores."),
    ).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText(/não pôde ser lida/)).toBeNull();
  });

  it("⛔ `null` → 'A adesão não pôde ser lida agora.' — outra frase, e não a de vazio", () => {
    render(<TelegramAdhesion rows={null} />);

    expect(screen.getByText("A adesão não pôde ser lida agora.")).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText(/Nenhuma unidade/)).toBeNull();
  });
});
