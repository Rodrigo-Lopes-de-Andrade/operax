import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PanelAlerts } from "@/components/dp/panel-alerts";
import type { AlertCounts, AlertsResult } from "@/lib/dp/queries";

/** Os oito códigos que `public.fn_dp_alerts()` devolve, e nenhum a mais. */
const COUNTS: AlertCounts = {
  birthday_month: 3,
  probation: 2,
  document_expired: 26,
  document_expiring: 25,
  exam_due: 18,
  vacation_upcoming: 4,
  vacation_today: 1,
  vacation_limit: 7,
};

function ok(counts: AlertCounts = COUNTS): AlertsResult {
  return { status: "ok", counts };
}

/** O cartão inteiro, achado pelo rótulo — valor e nota juntos. */
function card(eyebrow: RegExp): HTMLElement {
  const label = screen.getByText(eyebrow);
  const section = label.closest("section");

  expect(section).not.toBeNull();
  return section as HTMLElement;
}

describe("painel de alertas", () => {
  it("mostra os oito contadores com o número que a função devolveu", () => {
    render(<PanelAlerts alerts={ok()} />);

    expect(
      within(card(/aniversariantes do mês/i)).getByText("3"),
    ).toBeVisible();
    expect(within(card(/em experiência/i)).getByText("2")).toBeVisible();
    expect(within(card(/documentos vencidos/i)).getByText("26")).toBeVisible();
    expect(within(card(/documentos a vencer/i)).getByText("25")).toBeVisible();
    expect(
      within(card(/ASO vencido ou a vencer/i)).getByText("18"),
    ).toBeVisible();
    expect(within(card(/férias no próximo mês/i)).getByText("4")).toBeVisible();
    expect(within(card(/em férias hoje/i)).getByText("1")).toBeVisible();
    expect(within(card(/prazo de férias/i)).getByText("7")).toBeVisible();
  });

  it("os dois cartões de documento contam DOCUMENTO, e dizem isso", () => {
    render(<PanelAlerts alerts={ok()} />);

    const vencidos = card(/documentos vencidos/i);
    expect(within(vencidos).getByText("documentos")).toBeVisible();
    expect(vencidos).toHaveTextContent(/documentos, não de pessoas/i);

    const aVencer = card(/documentos a vencer/i);
    expect(within(aVencer).getByText("documentos")).toBeVisible();
    expect(aVencer).toHaveTextContent(/contagem de documentos/i);
  });

  it("os outros seis contam PESSOA, e é o oposto do de documento", () => {
    render(<PanelAlerts alerts={ok()} />);

    for (const eyebrow of [
      /aniversariantes do mês/i,
      /em experiência/i,
      /ASO vencido ou a vencer/i,
      /férias no próximo mês/i,
      /prazo de férias/i,
    ]) {
      expect(within(card(eyebrow)).getByText("pessoas")).toBeVisible();
    }

    // Um só é "pessoa", não "pessoas" — o plural não pode ser fixo.
    expect(within(card(/em férias hoje/i)).getByText("pessoa")).toBeVisible();
  });

  it("nenhum cartão de documento se chama CNH", () => {
    render(<PanelAlerts alerts={ok()} />);

    // `app.document_type` não tem código: a identidade do tipo é o nome, texto
    // livre por tenant. Rotular o cartão de CNH poria regra de negócio numa
    // string e erraria calado no tenant que escrevesse "Carteira de Habilitação".
    //
    // A asserção é sobre o CARTÃO inteiro, e não só sobre o rótulo: uma nota
    // que voltasse a estreitar o sentido — "CNH e demais documentos" — passaria
    // por uma verificação que olhasse apenas o eyebrow.
    for (const eyebrow of [/documentos vencidos/i, /documentos a vencer/i]) {
      const cartao = card(eyebrow);
      expect(cartao.textContent).toMatch(/\bdocumentos\b/);
      // A única menção tolerada é a que NEGA o recorte por tipo.
      const mencoes = cartao.textContent?.match(/CNH/g) ?? [];
      expect(mencoes.length).toBeLessThanOrEqual(1);
      if (mencoes.length === 1) {
        expect(cartao).toHaveTextContent(/não só CNH/i);
      }
    }
  });

  it("o prazo de férias diz que o vencido está dentro do número", () => {
    render(<PanelAlerts alerts={ok()} />);

    // Sem isto o gestor lê "7 a vencer" e trata como aviso com folga. Vencido é
    // onde o período passa a custar em dobro (CLT art. 137).
    const prazo = card(/prazo de férias/i);
    expect(prazo).toHaveTextContent(/vencido ou a vencer/i);
    expect(prazo).toHaveTextContent(/já passou do prazo/i);
    expect(prazo).toHaveTextContent(/em dobro/i);
  });

  it("código que não veio na resposta vale zero, e o cartão continua de pé", () => {
    render(<PanelAlerts alerts={ok({ birthday_month: 3 })} />);

    expect(within(card(/em férias hoje/i)).getByText("0")).toBeVisible();
    expect(within(card(/documentos vencidos/i)).getByText("0")).toBeVisible();
  });

  it("leitura que falhou vira erro visível, não oito zeros", () => {
    render(<PanelAlerts alerts={{ status: "unavailable" }} />);

    expect(screen.getByText(/não puderam ser lidos/i)).toBeVisible();
    // O positivo ao lado do negativo: com a leitura de pé os cartões existem.
    expect(screen.queryByText(/aniversariantes do mês/i)).toBeNull();
    expect(screen.queryByText("0")).toBeNull();
  });

  it("nenhum nome de pessoa sai deste bloco", () => {
    const { container } = render(<PanelAlerts alerts={ok()} />);

    // `fn_dp_alerts()` devolve (code, total) e nada mais. Se um dia devolver
    // linha por pessoa, este bloco não é o lugar de mostrá-la.
    expect(container.querySelectorAll("table")).toHaveLength(0);
    expect(container.querySelectorAll("a")).toHaveLength(0);
  });
});
