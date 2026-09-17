import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DeliveryByChannel } from "@/components/canais/delivery-by-channel";
import type { DeliveryByChannelRow } from "@/lib/canais/queries";

const WHY = "Cada pessoa que adere ao Telegram sai do número de WhatsApp.";

function row(
  week_start: string,
  channel: string,
  provider: string,
  sent: number,
  failed: number,
): DeliveryByChannelRow {
  return { week_start, channel, provider, sent, failed };
}

/**
 * Três semanas, na ordem da RPC, escolhidas para que cada soma errada caia
 * em alguma linha:
 *
 * - 31/08: DOIS provedores de WhatsApp (o oficial e um não oficial) — uma
 *   agregação por provedor daria duas colunas, ou perderia um dos dois.
 * - 07/09: WhatsApp, Telegram E e-mail — um `%` sobre o total das três
 *   colunas daria 18% em vez de 45%.
 * - 14/09: só e-mail — o denominador do `%` é zero, e a célula é `—`.
 *
 * Nenhum nome, nenhum número de telefone, nenhum `chat_id`: a RPC não os
 * devolve, e o tipo não tem por onde eles entrarem.
 */
const ROWS: DeliveryByChannelRow[] = [
  row("2026-08-31", "whatsapp", "meta_cloud", 40, 2),
  row("2026-08-31", "whatsapp", "z_api", 5, 1),
  row("2026-08-31", "telegram", "telegram", 15, 0),
  row("2026-09-07", "whatsapp", "meta_cloud", 30, 0),
  row("2026-09-07", "telegram", "telegram", 25, 2),
  row("2026-09-07", "email", "smtp", 100, 4),
  row("2026-09-14", "email", "resend", 7, 0),
];

/** Só os dois canais da tela — a coluna de e-mail não tem o que mostrar. */
const SEM_EMAIL: DeliveryByChannelRow[] = ROWS.filter(
  (r) => r.channel !== "email",
);

function tabela() {
  return screen.getByRole("table", { name: "Entregas por canal e semana" });
}

function cabecalhos(): string[] {
  return within(tabela())
    .getAllByRole("columnheader")
    .map((th) => th.textContent ?? "");
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

function semana(row: HTMLElement): string {
  return within(row).getByRole("rowheader").textContent ?? "";
}

describe("o cartão — título, a frase do porquê, e os três estados", () => {
  it("✅ o título é 'Entregas por canal' e a frase fixa está sob ele", () => {
    render(<DeliveryByChannel rows={ROWS} />);

    expect(
      screen.getByRole("heading", { name: "Entregas por canal" }),
    ).toBeVisible();
    expect(screen.getByText(WHY)).toBeVisible();
  });

  it("⛔ `null` → 'não puderam ser lidas', sem tabela — e a frase fixa continua lá", () => {
    render(<DeliveryByChannel rows={null} />);

    expect(
      screen.getByText("As entregas não puderam ser lidas agora."),
    ).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText(/Nenhuma entrega/)).toBeNull();
    expect(screen.getByText(WHY)).toBeVisible();
  });

  it("⛔ `[]` → 'Nenhuma entrega registrada nas últimas 8 semanas.', sem tabela — outra frase, e não a de erro", () => {
    // O sender ainda não está agendado: este é o estado normal por semanas.
    render(<DeliveryByChannel rows={[]} />);

    expect(
      screen.getByText("Nenhuma entrega registrada nas últimas 8 semanas."),
    ).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText(/não puderam ser lidas/)).toBeNull();
    expect(screen.getByText(WHY)).toBeVisible();
  });
});

describe("a tabela — uma linha por semana, agregada por CANAL", () => {
  it("✅ uma linha por semana, na ordem da RPC, com `DD/MM` da segunda-feira como cabeçalho da linha", () => {
    render(<DeliveryByChannel rows={ROWS} />);

    expect(corpo().map(semana)).toEqual(["31/08", "07/09", "14/09"]);
  });

  it("as colunas com e-mail presente: Semana, WhatsApp, Telegram, E-mail, Falhas, Telegram %", () => {
    render(<DeliveryByChannel rows={ROWS} />);

    expect(cabecalhos()).toEqual([
      "Semana",
      "WhatsApp",
      "Telegram",
      "E-mail",
      "Falhas",
      "Telegram %",
    ]);
  });

  it("⛔ FALSO VERDE: dois provedores de WhatsApp na mesma semana somam numa coluna só — pelo campo `channel`", () => {
    // Uma agregação por provedor que mapeasse para canal pelo nome passaria
    // com um provedor por canal. Aqui a semana de 31/08 tem o oficial (40) e
    // um não oficial (5): WhatsApp 45, Telegram 15, E-mail 0, Falhas 2+1+0,
    // 15/(45+15) = 25%.
    render(<DeliveryByChannel rows={ROWS} />);

    const [w1] = corpo();
    expect(celulas(w1)).toEqual(["45", "15", "0", "3", "25%"]);
    // E a coluna de WhatsApp existe uma vez — não uma por provedor.
    expect(cabecalhos().filter((h) => h === "WhatsApp")).toHaveLength(1);
  });

  it("⛔ … e é o `channel` da linha que decide, não o nome do provedor", () => {
    // Um provedor com nome de WhatsApp declarado como Telegram pelo backend
    // conta como Telegram: a tela não tem opinião sobre com quem falamos.
    render(
      <DeliveryByChannel
        rows={[
          row("2026-08-31", "whatsapp", "meta_cloud", 10, 0),
          row("2026-08-31", "telegram", "z_api", 30, 0),
        ]}
      />,
    );

    const [w1] = corpo();
    // WhatsApp 10, Telegram 30, Falhas 0, 30/40 = 75%.
    expect(celulas(w1)).toEqual(["10", "30", "0", "75%"]);
  });

  it("⛔ FALSO VERDE: o `%` é Telegram / (WhatsApp + Telegram) — o e-mail NÃO entra no denominador", () => {
    // 07/09: WhatsApp 30, Telegram 25, E-mail 100. Sobre o total das três
    // seria 25/155 = 16%; sobre WhatsApp + Telegram é 25/55 = 45%.
    render(<DeliveryByChannel rows={ROWS} />);

    const [, w2] = corpo();
    expect(celulas(w2)).toEqual(["30", "25", "100", "6", "45%"]);
  });

  it("⛔ denominador zero → `—`, e não 0% nem NaN", () => {
    // 14/09 só tem e-mail: WhatsApp 0, Telegram 0, E-mail 7, Falhas 0.
    render(<DeliveryByChannel rows={ROWS} />);

    const [, , w3] = corpo();
    expect(celulas(w3)).toEqual(["0", "0", "7", "0", "—"]);
    expect(tabela().textContent).not.toMatch(/NaN|Infinity/);
  });

  it("⛔ o rodapé soma cada coluna do período, e o `%` do período é sobre as somas", () => {
    // WhatsApp 45+30+0 = 75 · Telegram 15+25+0 = 40 · E-mail 0+100+7 = 107 ·
    // Falhas 3+6+0 = 9 · 40/(75+40) = 34,78 → 35% (sobre as três colunas
    // seria 40/222 = 18%). ⚠️ Nesta fixture a média dos `%` semanais
    // (25 e 45) também dá 35 — é o teste seguinte quem separa as duas.
    render(<DeliveryByChannel rows={ROWS} />);

    const total = rodape();
    expect(within(total).getByRole("rowheader")).toHaveTextContent("Total");
    expect(celulas(total)).toEqual(["75", "40", "107", "9", "35%"]);
  });

  it("as falhas somam TODOS os canais — inclusive o e-mail", () => {
    // 07/09: 0 + 2 + 4 = 6. Uma soma só de WhatsApp + Telegram daria 2.
    render(<DeliveryByChannel rows={ROWS} />);

    const [, w2] = corpo();
    expect(celulas(w2)[3]).toBe("6");
  });

  it("⛔ os números são os da prop, não de uma tabela escrita à mão", () => {
    render(
      <DeliveryByChannel
        rows={[
          row("2026-08-31", "whatsapp", "meta_cloud", 1100, 13),
          row("2026-08-31", "telegram", "telegram", 1100, 17),
        ]}
      />,
    );

    // Milhares em pt-BR, e 1100/2200 = 50%.
    expect(celulas(corpo()[0])).toEqual(["1.100", "1.100", "30", "50%"]);
    expect(celulas(rodape())).toEqual(["1.100", "1.100", "30", "50%"]);
  });

  it("um canal sem linha numa semana mostra 0 nessa semana, e a semana não some", () => {
    render(
      <DeliveryByChannel
        rows={[
          row("2026-08-31", "whatsapp", "meta_cloud", 12, 0),
          row("2026-09-07", "telegram", "telegram", 8, 1),
        ]}
      />,
    );

    const [w1, w2] = corpo();
    expect(celulas(w1)).toEqual(["12", "0", "0", "0%"]);
    expect(celulas(w2)).toEqual(["0", "8", "1", "100%"]);
    // ⛔ FALSO VERDE: a média dos `%` semanais (0 e 100) daria 50%; a razão
    // das somas é 8/(12+8) = 40%. O rodapé é a segunda.
    expect(celulas(rodape())).toEqual(["12", "8", "1", "40%"]);
  });
});

describe("a coluna de e-mail só existe quando há linha de e-mail", () => {
  it("⛔ sem linha de e-mail: cinco colunas, e nenhuma 'E-mail'", () => {
    render(<DeliveryByChannel rows={SEM_EMAIL} />);

    expect(cabecalhos()).toEqual([
      "Semana",
      "WhatsApp",
      "Telegram",
      "Falhas",
      "Telegram %",
    ]);
    // 31/08: WhatsApp 45, Telegram 15, Falhas 3, 25%.
    expect(celulas(corpo()[0])).toEqual(["45", "15", "3", "25%"]);
    expect(celulas(rodape())).toEqual(["75", "40", "5", "35%"]);
  });

  it("✅ com uma linha de e-mail em qualquer semana, a coluna aparece para todas", () => {
    render(<DeliveryByChannel rows={ROWS} />);

    expect(cabecalhos()).toContain("E-mail");
    // A semana sem e-mail mostra 0 na coluna, e não uma célula a menos.
    expect(celulas(corpo()[0])).toHaveLength(5);
  });

  it("um canal que a tela não conhece aparece com o código cru, e não some da soma", () => {
    // Um quarto canal no log sem rótulo aqui: feio e honesto, como `label()`.
    render(
      <DeliveryByChannel
        rows={[
          row("2026-08-31", "whatsapp", "meta_cloud", 10, 0),
          row("2026-08-31", "zz_canal_novo", "zz_prov", 3, 1),
        ]}
      />,
    );

    expect(cabecalhos()).toEqual([
      "Semana",
      "WhatsApp",
      "Telegram",
      "zz_canal_novo",
      "Falhas",
      "Telegram %",
    ]);
    expect(celulas(corpo()[0])).toEqual(["10", "0", "3", "1", "0%"]);
  });
});

describe("a semana é `date`, e sai sem deslocar", () => {
  const TZ = process.env.TZ;

  afterEach(() => {
    process.env.TZ = TZ;
  });

  it.each(["America/Sao_Paulo", "Pacific/Kiritimati", "UTC"])(
    "⛔ FALSO VERDE: `2026-09-01` é `01/09` com TZ=%s — não `31/08` nem `02/09`",
    (zone) => {
      // A suíte roda em UTC (vitest.config), onde `new Date("2026-09-01")`
      // formatado no fuso da máquina ainda dá 01/09. Em São Paulo daria
      // 31/08 (só fusos negativos deslocam a meia-noite UTC; a +14 continua
      // dia 01 — o caso está aqui como controle): `week_start` é `date`, não
      // há hora para deslocar, e o formato é por string. O Node honra `TZ`
      // trocado em runtime — medido antes deste teste.
      process.env.TZ = zone;

      render(
        <DeliveryByChannel
          rows={[row("2026-09-01", "whatsapp", "meta_cloud", 1, 0)]}
        />,
      );

      expect(corpo().map(semana)).toEqual(["01/09"]);
    },
  );

  it("✅ o positivo do falso verde: um formatador por `Date` desloca em São Paulo", () => {
    // Sem isto, o `it.each` acima passaria mesmo que trocar `TZ` não
    // surtisse efeito no processo.
    process.env.TZ = "America/Sao_Paulo";

    expect(new Date("2026-09-01").toLocaleDateString("pt-BR")).toBe(
      "31/08/2026",
    );
  });
});

describe("sem nome, sem número, sem `chat_id`, sem juízo", () => {
  it("⛔ o DOM tem semanas, rótulos de canal e números — e é só", () => {
    const { container } = render(<DeliveryByChannel rows={ROWS} />);

    expect(container.innerHTML).not.toMatch(
      /chat_id|chat-id|employee|cpf|destination|\+55|@\w/i,
    );
    // Os nomes de provedor são `key` de agregação, não conteúdo.
    expect(container.textContent).not.toMatch(/meta_cloud|z_api|smtp|resend/);
  });

  it("⛔ o percentual é número, não veredito: nada de 'bom', 'ruim', 'meta' ou 'hora extra'", () => {
    const { container } = render(<DeliveryByChannel rows={ROWS} />);

    expect(container.textContent).not.toMatch(
      /\b(bom|boa|ruim|ótimo|péssimo|meta|alvo|atingiu|hora extra)\b/i,
    );
  });

  it("⛔ nenhuma classe de laranja como texto — o laranja é preenchimento, nunca texto", () => {
    const { container } = render(<DeliveryByChannel rows={ROWS} />);

    expect(container.innerHTML).not.toMatch(
      /text-brand(?!-strong)|text-orange/,
    );
  });
});
