import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LaudosPage from "@/app/dashboard/administracao/laudos/page";
import type { ComplianceReportList } from "@/lib/dp/queries";
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
const loadComplianceReports = vi.fn();
const loadUnits = vi.fn();

// A página NÃO deve perguntar o papel. O mock existe para que, se alguém
// acrescentar a porta, o teste do supervisor a encontre com um papel real.
vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/dp/queries", () => ({
  loadComplianceReports: (...args: unknown[]) => loadComplianceReports(...args),
}));

vi.mock("@/lib/ponto/queries", () => ({
  loadUnits: () => loadUnits(),
}));

// O cliente do Caminho 1 é identificável de propósito: é ele que a página tem
// de entregar ao carregador da lista, e não uma instância qualquer.
const { SUPABASE } = vi.hoisted(() => ({ SUPABASE: { caminho: 1 } }));

vi.mock("@/lib/supabase-server", () => ({
  getServerSupabase: async () => SUPABASE,
}));

const UNIT = "11111111-1111-4111-8111-111111111111";

function identidade(role: string): Identity {
  return {
    user_id: "11111111-1111-4111-8111-111111111111",
    email: `${role}@fastpark.dev`,
    tenant_id: "22222222-2222-4222-8222-222222222222",
    role,
  };
}

const UMA_LINHA: ComplianceReportList = {
  can_write: false,
  rows: [
    {
      id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
      unit_id: UNIT,
      unit_name: "Aeroporto",
      type: "PCMSO",
      valid_until: "2026-10-01",
      days_to_expiry: 20,
      renewal_count: 0,
      notes: null,
      created_at: "2026-09-01T12:00:00Z",
    },
  ],
};

async function abrir(
  role: string,
  screen: ComplianceReportList | null,
  params: Record<string, string> = {},
) {
  loadIdentity.mockResolvedValue(identidade(role));
  loadComplianceReports.mockResolvedValue(screen);
  loadUnits.mockResolvedValue([
    {
      unitId: UNIT,
      code: "AERO",
      slug: "aero",
      name: "Aeroporto",
      companyId: "33333333-3333-4333-8333-333333333333",
      companyName: "Dev Um",
      companySlug: "dev-um",
    },
  ]);

  return render(await LaudosPage({ searchParams: Promise.resolve(params) }));
}

beforeEach(() => {
  notFound.mockClear();
  loadIdentity.mockReset();
  loadComplianceReports.mockReset();
  loadUnits.mockReset();
});

describe("a página de laudos não fecha por papel", () => {
  it("✅ `unit_supervisor` ENTRA — a rota recorta pela unidade dele, e a tela não reergue a parede", async () => {
    // O ALTO 1 da revisão de frontend: `reachesHr` aqui trancaria fora a
    // persona que o PRD nomeia ("gestor de unidade consulta laudos da sua
    // unidade"). A API já respondeu só o que ele alcança.
    await abrir("unit_supervisor", UMA_LINHA);

    expect(notFound).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Laudos" })).toBeVisible();
    expect(screen.getByText("PCMSO")).toBeVisible();
    // ⛔ E ele não escreve: `can_write` veio falso, e o botão não existe.
    expect(screen.queryByRole("button", { name: "Renovar" })).toBeNull();
  });

  it("`viewer` também entra: quem decide o que ele vê é a policy, não a tela", async () => {
    await abrir("viewer", { rows: [], can_write: false });

    expect(notFound).not.toHaveBeenCalled();
    expect(loadIdentity).not.toHaveBeenCalled();
  });

  it("`owner` entra e a resposta da API é quem liga a escrita", async () => {
    await abrir("owner", { ...UMA_LINHA, can_write: true });

    expect(screen.getByRole("button", { name: "Renovar" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Novo laudo" })).toBeVisible();
  });
});

describe("os dois estados vazios são frases diferentes", () => {
  it("null (a leitura da view que falhou) é 'não pôde ser lido'", async () => {
    await abrir("unit_supervisor", null);

    expect(screen.getByText("Os laudos não puderam ser lidos")).toBeVisible();
    expect(screen.queryByText("Nenhum laudo vigente")).toBeNull();
  });

  it("⛔ a frase nomeia quem falhou — a lista não vem mais da API", async () => {
    // A tela irmã (Rubricas) diz "a API não respondeu" porque lá é verdade.
    // Aqui a lista é Caminho 1: null é a view que não respondeu, e a rota fora
    // do ar nem produz este estado — ela só decide o botão de escrever.
    await abrir("unit_supervisor", null);

    expect(screen.getByText(/view do banco/i)).toBeVisible();
    expect(screen.queryByText(/a API do painel/i)).toBeNull();
  });

  it("zero linhas com resposta ok é 'nenhum laudo vigente'", async () => {
    await abrir("unit_supervisor", { rows: [], can_write: false });

    expect(screen.getByText("Nenhum laudo vigente")).toBeVisible();
    expect(screen.queryByText("Os laudos não puderam ser lidos")).toBeNull();
  });
});

describe("o recorte vem da URL", () => {
  it("entrega o cliente do caminho 1 e a unidade; a situação fica na tela", async () => {
    await abrir("unit_supervisor", UMA_LINHA, {
      un: UNIT,
      situacao: "vencido",
    });

    // ⛔ O primeiro argumento é o cliente Supabase da sessão: a lista vem da
    // view (`public.vw_unit_compliance`), que é o consumidor que a migration
    // autorizou. Uma leitura só pela rota não teria o que passar aqui.
    expect(loadComplianceReports).toHaveBeenCalledWith(SUPABASE, {
      unitId: UNIT,
      status: "vencido",
    });
    // A única linha está em dia; com `situacao=vencido` ela some, e a tela diz
    // que ela existe fora do filtro.
    expect(screen.queryByText("PCMSO")).toBeNull();
    expect(screen.getByText("Nenhum laudo vencido")).toBeVisible();
  });

  it("oferece os dois seletores, com as três situações", async () => {
    await abrir("unit_supervisor", UMA_LINHA);

    expect(screen.getByLabelText("Unidade")).toBeVisible();
    const situacao = screen.getByLabelText("Situação");
    expect(situacao).toBeVisible();
    expect(
      [...situacao.querySelectorAll("option")].map((o) => o.textContent),
    ).toEqual(["Todas as situações", "Vencido", "A vencer", "Em dia"]);
  });
});
