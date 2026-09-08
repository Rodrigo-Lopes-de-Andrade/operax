import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CiclosPage from "@/app/dashboard/dp/ciclos/page";
import type { CycleListResult, CycleSummary } from "@/lib/dp/queries";
import type { Identity } from "@/lib/identity";

vi.mock("server-only", () => ({}));

const notFound = vi.fn(() => {
  throw new Error("NEXT_NOT_FOUND");
});

vi.mock("next/navigation", () => ({
  notFound: () => notFound(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const loadIdentity = vi.fn();
const loadCycles = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  // `isAdmin` fica o real: ele é o eixo de escrita sob teste.
  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/dp/queries", () => ({
  loadCycles: (...args: unknown[]) => loadCycles(...args),
}));

function identidade(role: string): Identity {
  return {
    user_id: "11111111-1111-4111-8111-111111111111",
    email: `${role}@fastpark.dev`,
    tenant_id: "22222222-2222-4222-8222-222222222222",
    role,
  };
}

function resumo(status = "generated"): CycleSummary {
  return {
    id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    kind: "transport_voucher",
    period_year: 2026,
    period_month: 9,
    window_start: "2026-08-21",
    window_end: "2026-09-20",
    business_days: 21,
    status,
    entitled_count: 1,
    denied_count: 0,
    total_amount: "201.60",
  };
}

const COMPETENCIA = { tipo: "transport_voucher", ano: "2026", mes: "9" };

async function abrir(
  role: string,
  history: CycleListResult,
  params: Record<string, string> = COMPETENCIA,
) {
  loadIdentity.mockResolvedValue(identidade(role));
  loadCycles.mockResolvedValue(history);

  return render(await CiclosPage({ searchParams: Promise.resolve(params) }));
}

const ABERTO: CycleListResult = {
  status: "ok",
  list: { rows: [resumo()], can_export_remittance: true },
};

beforeEach(() => {
  notFound.mockClear();
  loadIdentity.mockReset();
  loadCycles.mockReset();
});

describe("quem entra na tela de ciclo é quem tem `compensation`", () => {
  it("⛔ 403 na leitura fecha a porta — a tela não existe para quem não alcança", async () => {
    loadIdentity.mockResolvedValue(identidade("hr"));
    loadCycles.mockResolvedValue({ status: "forbidden" });

    await expect(
      CiclosPage({ searchParams: Promise.resolve(COMPETENCIA) }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalled();
  });

  it("✅ `accounting` ENTRA — e era ele que a guarda por papel trancava fora", async () => {
    // `ADMIN_ROLES` é owner|hr|personnel. `accounting` tem `compensation` e
    // `banking`, e a migration do S2 o nomeia como quem confere a remessa: ele
    // não é admin e precisa da tela. Sem usuário `accounting` no seed de dev,
    // isto nunca apareceria em teste manual.
    await abrir("accounting", ABERTO);

    expect(notFound).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Ciclo mensal" })).toBeVisible();
    expect(screen.getByText("Gerado")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Arquivo do banco" }),
    ).toBeVisible();
  });

  it("`accounting` confere e não apura: os dois botões de escrita não existem", async () => {
    await abrir("accounting", ABERTO);

    expect(
      screen.queryByRole("button", { name: "Apurar competência" }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "Gerar ciclo" })).toBeNull();
  });

  it("⛔ e nem sobre um RASCUNHO: o eixo de escrita é o papel, não o estado", async () => {
    // Com a competência congelada os dois botões somem pelo congelamento, e a
    // asserção anterior passaria mesmo se a página mandasse `canWrite` fixo.
    await abrir("accounting", {
      status: "ok",
      list: { rows: [resumo("draft")], can_export_remittance: true },
    });

    expect(screen.getByText("Rascunho")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Apurar competência" }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "Gerar ciclo" })).toBeNull();
  });

  it("`executive` cai no mesmo lugar de `accounting`", async () => {
    await abrir("executive", ABERTO);

    expect(notFound).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Ciclo mensal" })).toBeVisible();
  });

  it("⛔ e nem sobre um RASCUNHO: `executive` lê o ciclo e não o escreve", async () => {
    // O par do teste acima, e ele existe pelo mesmo motivo do par de
    // `accounting`: sobre `ABERTO` os dois botões somem pelo congelamento, e a
    // asserção passaria com `canWrite` fixo em qualquer coisa. Sobre um
    // rascunho quem responde é só o papel — `executive` tem `compensation` e
    // não está em `ADMIN_ROLES`.
    await abrir("executive", {
      status: "ok",
      list: { rows: [resumo("draft")], can_export_remittance: true },
    });

    expect(screen.getByText("Rascunho")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Apurar competência" }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "Gerar ciclo" })).toBeNull();
  });

  it("`owner` entra e escreve — o eixo de escrita continua sendo `util.is_admin`", async () => {
    await abrir("owner", {
      status: "ok",
      list: { rows: [resumo("draft")], can_export_remittance: true },
    });

    expect(notFound).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Apurar competência" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Gerar ciclo" })).toBeVisible();
  });

  it("sem vínculo com o tenant não há tela, e a API nem é chamada", async () => {
    loadIdentity.mockResolvedValue(null);

    await expect(
      CiclosPage({ searchParams: Promise.resolve(COMPETENCIA) }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadCycles).not.toHaveBeenCalled();
  });

  it("API fora do ar não é falta de permissão: a tela abre e avisa", async () => {
    await abrir("owner", { status: "unavailable" });

    expect(notFound).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      /não consegui ler as competências já apuradas/i,
    );
  });

  it("pergunta ao servidor a competência que está na URL", async () => {
    await abrir("owner", ABERTO, {
      tipo: "food_basket",
      ano: "2026",
      mes: "3",
    });

    expect(loadCycles).toHaveBeenCalledWith({
      kind: "food_basket",
      year: 2026,
      month: 3,
    });
  });
});
