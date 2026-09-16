import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ColaboradorRhPage from "@/app/dashboard/administracao/colaboradores/[id]/page";
import type { TelegramLink } from "@/lib/canais/queries";
import type { Identity } from "@/lib/identity";
import type { HrEmployeeDetail } from "@/lib/rh/queries";

vi.mock("server-only", () => ({}));

const notFound = vi.fn(() => {
  throw new Error("NEXT_NOT_FOUND");
});

vi.mock("next/navigation", () => ({
  notFound: () => notFound(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const loadIdentity = vi.fn();
const loadHrEmployee = vi.fn();
const loadFreshness = vi.fn();
const loadTelegramLink = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  // `reachesHr` fica o real: é a porta sob teste.
  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/rh/queries", () => ({
  loadHrEmployee: (...args: unknown[]) => loadHrEmployee(...args),
}));

vi.mock("@/lib/freshness", () => ({
  loadFreshness: () => loadFreshness(),
}));

vi.mock("@/lib/canais/queries", () => ({
  loadTelegramLink: (...args: unknown[]) => loadTelegramLink(...args),
}));

const EMPLOYEE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

function identidade(role: string): Identity {
  return {
    user_id: "11111111-1111-4111-8111-111111111111",
    email: `${role}@fastpark.dev`,
    tenant_id: "22222222-2222-4222-8222-222222222222",
    role,
  };
}

/**
 * A ficha mínima: sem domínio sensível (os cinco blocos `null`), sem foto e
 * sem campo editável — o que basta para a página montar as abas que existem
 * para todo papel de RH, e nada que dispare leitura no cliente.
 */
function ficha(overrides: Partial<HrEmployeeDetail> = {}): HrEmployeeDetail {
  return {
    employee: {
      employee_id: EMPLOYEE,
      name: "Zz Pessoa Inventada",
      registration_number: null,
      hr_code: null,
      cargo: null,
      status: "active",
      hired_on: null,
      terminated_on: null,
      employment_type: null,
      unit_id: null,
      unit_name: null,
      company_name: null,
      department_name: null,
      manager_name: null,
    },
    sync_fields: [],
    editable_fields: [],
    enums: {},
    can_write: true,
    positions: [],
    leaves: [],
    movements: [],
    pii: null,
    photo: null,
    documents: null,
    exams: null,
    compensation: null,
    agreements: null,
    ...overrides,
  };
}

const LINKED: TelegramLink = {
  linked: true,
  opted_in_at: "2026-09-15T13:05:00Z",
  revoked_at: null,
  invite_open_until: null,
};

async function abrir(
  role: string,
  detail: HrEmployeeDetail | null,
  link: TelegramLink | null = LINKED,
) {
  loadIdentity.mockResolvedValue(identidade(role));
  loadHrEmployee.mockResolvedValue(detail);
  loadFreshness.mockResolvedValue(null);
  loadTelegramLink.mockResolvedValue(link);

  return render(
    await ColaboradorRhPage({
      params: Promise.resolve({ id: EMPLOYEE }),
      searchParams: Promise.resolve({}),
    }),
  );
}

beforeEach(() => {
  notFound.mockClear();
  loadIdentity.mockReset();
  loadHrEmployee.mockReset();
  loadFreshness.mockReset();
  loadTelegramLink.mockReset();
});

describe("critério 8 — `reachesHr` fecha a porta antes de qualquer leitura", () => {
  it("⛔ `unit_supervisor` recebe 404, e nenhuma das três leituras é chamada", async () => {
    loadIdentity.mockResolvedValue(identidade("unit_supervisor"));

    await expect(
      ColaboradorRhPage({
        params: Promise.resolve({ id: EMPLOYEE }),
        searchParams: Promise.resolve({}),
      }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalled();
    expect(loadHrEmployee).not.toHaveBeenCalled();
    expect(loadFreshness).not.toHaveBeenCalled();
    // ⛔ A leitura nova obedece à mesma porta: o vínculo é dado individual.
    expect(loadTelegramLink).not.toHaveBeenCalled();
  });

  it("sem vínculo com o tenant não há ficha", async () => {
    loadIdentity.mockResolvedValue(null);

    await expect(
      ColaboradorRhPage({
        params: Promise.resolve({ id: EMPLOYEE }),
        searchParams: Promise.resolve({}),
      }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadTelegramLink).not.toHaveBeenCalled();
  });

  it("✅ `executive` entra: lê a área de RH, e a ficha abre", async () => {
    await abrir("executive", ficha({ can_write: false }));

    expect(notFound).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", { level: 1, name: "Zz Pessoa Inventada" }),
    ).toBeVisible();
  });
});

describe("critério 8 — o vínculo do Telegram entra na ficha", () => {
  it("✅ `loadTelegramLink` é chamada com o id da rota, uma vez", async () => {
    await abrir("owner", ficha());

    expect(loadTelegramLink).toHaveBeenCalledTimes(1);
    expect(loadTelegramLink).toHaveBeenCalledWith(EMPLOYEE);
    expect(loadHrEmployee).toHaveBeenCalledWith(EMPLOYEE);
  });

  it("✅ o cartão do Telegram está abaixo das abas, com o estado que a leitura trouxe", async () => {
    await abrir("owner", ficha());

    expect(screen.getByRole("heading", { name: "Telegram" })).toBeVisible();
    expect(screen.getByText("Vinculado")).toBeVisible();
    expect(screen.getByText("desde 15/09/2026 às 10:05")).toBeVisible();
    // ⛔ Não é aba: a navegação das abas não ganhou um item — e o cartão vem
    // DEPOIS dela no documento, não acima do cabeçalho da ficha.
    const abas = screen.getByRole("navigation", {
      name: "Domínios do colaborador",
    });
    expect(abas).not.toHaveTextContent("Telegram");
    const cartao = screen.getByRole("heading", { name: "Telegram" });
    expect(
      abas.compareDocumentPosition(cartao) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("⛔ o botão do cartão segue o `can_write` da ficha — `owner` com `can_write: true` vê 'Desvincular'", async () => {
    await abrir("owner", ficha({ can_write: true }));

    expect(screen.getByRole("button", { name: "Desvincular" })).toBeVisible();
  });

  it("⛔ … e `can_write: false` não vê botão nenhum, mesmo sendo `owner`", async () => {
    // O `can_write` vem do banco (`util.is_admin`), e a ficha confia nele e
    // não no papel do `/me` — o cartão do Telegram também.
    await abrir("owner", ficha({ can_write: false }));

    expect(screen.getByText("Vinculado")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Desvincular" })).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Convidar pelo WhatsApp" }),
    ).toBeNull();
  });

  it("`null` no vínculo → a frase de leitura, e a ficha inteira fica de pé", async () => {
    await abrir("owner", ficha(), null);

    expect(notFound).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", { level: 1, name: "Zz Pessoa Inventada" }),
    ).toBeVisible();
    expect(
      screen.getByText("Não deu para ler o vínculo do Telegram agora."),
    ).toBeVisible();
    expect(screen.queryByText("Vinculado")).toBeNull();
  });

  it("colaborador fora do recorte (detalhe nulo) → 'não encontrado', e nenhum cartão do Telegram", async () => {
    // O 404 do vínculo virou `null` na leitura; aqui a ficha nem chega a
    // montar o cartão — a mesma resposta para "não existe" e "fora do seu
    // acompanhamento", de propósito.
    await abrir("owner", null, null);

    expect(screen.getByText("Colaborador não encontrado")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Telegram" })).toBeNull();
    expect(screen.queryByText(/vínculo do Telegram/)).toBeNull();
  });
});
