import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PunchReading } from "@/components/monitor/punch-reading";
import type { DailyMonitor } from "@/lib/monitor/queries";

function monitor(overrides: Partial<DailyMonitor> = {}): DailyMonitor {
  return {
    day: "2026-08-25",
    active: 39,
    scheduled: 25,
    with_indication: 4,
    clear: 21,
    with_punch: 22,
    without_punch: 3,
    // 12:15Z = 09:15 em São Paulo, que é o fuso do cliente.
    punches_read_at: "2026-08-25T12:15:00Z",
    on_vacation: 3,
    on_leave: 1,
    day_off: 7,
    unrostered: 3,
    off_roster: 11,
    units: [],
    rows: [],
    truncated: false,
    ...overrides,
  };
}

describe("PunchReading", () => {
  it("carrega a hora da leitura dentro do próprio rótulo", () => {
    // A hora não é rodapé: sem ela, "sem marcação: 3" afirma que três pessoas
    // não bateram ponto, quando o que se sabe é que não tinham batido às 09:15.
    render(<PunchReading monitor={monitor()} />);

    expect(
      screen.getByText("Com marcação até a leitura de 09:15"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Sem marcação até a leitura de 09:15"),
    ).toBeInTheDocument();
    expect(screen.getByText("22")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("nunca diz presente nem ausente", () => {
    // Decisão A12: marcação é registro, presença é fato. O gestor repassa esta
    // frase para o colaborador, e "você não bateu até as 09:15" é conferível
    // onde "você faltou" é uma acusação que o dado não sustenta.
    const { container } = render(<PunchReading monitor={monitor()} />);

    expect(container.textContent).not.toMatch(/presente|ausente|falta/i);
  });

  it("datar a leitura quando ela não é do dia observado", () => {
    // Um dia passado é relido depois de fechado. "Até as 03:10" sugeriria um
    // recorte do dia que nunca houve.
    render(
      <PunchReading
        monitor={monitor({
          day: "2026-08-20",
          punches_read_at: "2026-08-25T06:10:00Z",
        })}
      />,
    );

    // Três vezes: o cabeçalho do cartão e os dois rótulos.
    expect(screen.getAllByText(/na leitura de 25\/08 às 03:10/)).toHaveLength(
      3,
    );
  });

  it("sem leitura nenhuma não mostra zeros", () => {
    // Dois zeros e "ninguém leu a origem" são a mesma imagem com significados
    // opostos, e esta é a tela onde essa confusão custa mais caro.
    render(
      <PunchReading
        monitor={monitor({
          punches_read_at: null,
          with_punch: 0,
          without_punch: 0,
        })}
      />,
    );

    expect(screen.queryByText("0")).toBeNull();
    expect(
      screen.getByText(/Nenhuma leitura de marcação concluída/),
    ).toBeInTheDocument();
  });
});
