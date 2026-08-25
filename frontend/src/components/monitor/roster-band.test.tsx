import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RosterBand } from "@/components/monitor/roster-band";
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

describe("RosterBand", () => {
  it("mostra o efetivo e as cinco partes que fecham nele", () => {
    render(<RosterBand monitor={monitor()} />);

    expect(screen.getByText("39")).toBeInTheDocument();
    expect(screen.getByText("colaboradores ativos")).toBeInTheDocument();
    for (const rotulo of [
      "Escalados",
      "Em férias",
      "Afastados",
      "Folga",
      "Sem jornada",
    ]) {
      expect(screen.getByText(rotulo)).toBeInTheDocument();
    }
  });

  it("chama pelo nome quem está ativo sem jornada prevista", () => {
    // O número existe para separar desenho de falha de cobertura do motor. Se
    // ele não aparecer, as duas continuam indistinguíveis.
    render(<RosterBand monitor={monitor({ unrostered: 6 })} />);

    expect(screen.getByText(/6 sem jornada prevista para o dia/)).toBeVisible();
  });

  it("cala a ressalva quando não há ninguém sem jornada", () => {
    render(<RosterBand monitor={monitor({ unrostered: 0 })} />);

    expect(screen.queryByText(/sem jornada prevista para o dia —/)).toBeNull();
  });

  it("não chama nada de presença", () => {
    // Marcação é registro; presença é fato. Um cartão "presentes" alimentado
    // por "escalado e sem indício" seria a única mentira desta tela — e mesmo
    // com a marcação lida, afirmar presença continua sendo a decisão A12.
    const { container } = render(<RosterBand monitor={monitor()} />);

    expect(container.textContent).not.toMatch(/presente|ausente/i);
  });

  it("não divide por zero num dia sem efetivo", () => {
    render(
      <RosterBand
        monitor={monitor({
          active: 0,
          scheduled: 0,
          on_vacation: 0,
          on_leave: 0,
          day_off: 0,
          unrostered: 0,
          with_punch: 0,
          without_punch: 0,
        })}
      />,
    );

    expect(screen.getByText("colaboradores ativos")).toBeInTheDocument();
  });
});
