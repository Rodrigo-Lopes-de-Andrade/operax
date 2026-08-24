import { describe, expect, it } from "vitest";

import {
  daysUntil,
  dueLabel,
  dueTone,
  label,
  STATUS_LABEL,
} from "@/lib/rh/labels";

const HOJE = new Date(2026, 7, 24); // 24/08/2026, hora local

/**
 * A coluna de vencimento é a razão de a lista existir, e ela é lida de relance.
 * Um erro de um dia aqui é a diferença entre "vence hoje" e "venceu ontem" para
 * um ASO — e entre a pessoa poder ou não trabalhar amanhã.
 */
describe("daysUntil", () => {
  it("conta em dias de calendário, não em horas", () => {
    // A data do banco chega como "AAAA-MM-DD" e vira meia-noite local. Somar
    // horas daria 0.7 dia e arredondaria para o lado errado perto do fuso.
    expect(daysUntil("2026-08-24", HOJE)).toBe(0);
    expect(daysUntil("2026-08-25", HOJE)).toBe(1);
    expect(daysUntil("2026-08-23", HOJE)).toBe(-1);
  });

  it("atravessa a virada de mês", () => {
    expect(daysUntil("2026-09-01", HOJE)).toBe(8);
  });

  it("a hora do dia não muda a contagem", () => {
    const fimDoDia = new Date(2026, 7, 24, 23, 59);

    expect(daysUntil("2026-08-25", fimDoDia)).toBe(1);
  });
});

describe("dueLabel", () => {
  it("distingue o que venceu do que vai vencer", () => {
    expect(dueLabel(-3)).toBe("venceu há 3 dias");
    expect(dueLabel(0)).toBe("vence hoje");
    expect(dueLabel(3)).toBe("vence em 3 dias");
  });

  it("um dia é dia, não dias", () => {
    expect(dueLabel(1)).toBe("vence em 1 dia");
    expect(dueLabel(-1)).toBe("venceu há 1 dia");
  });
});

describe("dueTone", () => {
  it("vencido é falha; a janela de 30 dias é alerta; o resto é informação", () => {
    expect(dueTone(-1)).toBe("bad");
    expect(dueTone(0)).toBe("alert");
    expect(dueTone(30)).toBe("alert");
    expect(dueTone(31)).toBe("neutral");
  });
});

describe("label", () => {
  it("traduz o que conhece", () => {
    expect(label(STATUS_LABEL, "desligado")).toBe("Desligado");
  });

  it("valor novo no banco aparece cru em vez de sumir", () => {
    // O código-fonte do rótulo é o banco. Se um valor novo entrar num `check`
    // antes de alguém traduzi-lo, a tela mostra o código — feio, e honesto.
    expect(label(STATUS_LABEL, "aposentado")).toBe("aposentado");
  });

  it("ausência vira travessão, não string vazia", () => {
    expect(label(STATUS_LABEL, null)).toBe("—");
  });
});
