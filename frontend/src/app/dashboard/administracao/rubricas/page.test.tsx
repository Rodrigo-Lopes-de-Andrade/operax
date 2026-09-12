import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RubricasPage from "@/app/dashboard/administracao/rubricas/page";
import type { PayrollCodesResult } from "@/lib/dp/queries";
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
const loadPayrollCodes = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  // `isAdmin` fica o real: é a porta sob teste.
  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/dp/queries", () => ({
  loadPayrollCodes: () => loadPayrollCodes(),
}));

function identidade(role: string): Identity {
  return {
    user_id: "11111111-1111-4111-8111-111111111111",
    email: `${role}@fastpark.dev`,
    tenant_id: "22222222-2222-4222-8222-222222222222",
    role,
  };
}

const LISTA: PayrollCodesResult = {
  status: "ok",
  list: {
    rows: [
      {
        code: "0001",
        label: "SALARIO BASE",
        nature: "earning",
        category: null,
        validated: false,
        validated_at: null,
        in_payroll: true,
      },
    ],
    pending: 1,
    can_write: true,
  },
};

const RECUSA_DA_API =
  "Classificar rubrica exige papel administrativo. Seu papel consulta a folha, mas não define como ela é somada.";

async function abrir(role: string, result: PayrollCodesResult | null) {
  loadIdentity.mockResolvedValue(identidade(role));
  loadPayrollCodes.mockResolvedValue(result);

  return render(await RubricasPage());
}

beforeEach(() => {
  notFound.mockClear();
  loadIdentity.mockReset();
  loadPayrollCodes.mockReset();
});

describe("a porta da página é `isAdmin`; o domínio é a API quem responde", () => {
  it("⛔ `unit_supervisor` recebe 404, e a API nem é chamada", async () => {
    loadIdentity.mockResolvedValue(identidade("unit_supervisor"));

    await expect(RubricasPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalled();
    expect(loadPayrollCodes).not.toHaveBeenCalled();
  });

  it("⛔ `executive` também recebe 404 — lê a área de RH e não cura nada", async () => {
    // Ele está em `HR_ROLES` e não em `ADMIN_ROLES`. Sem este caso, trocar
    // `isAdmin` por `reachesHr` passaria verde: `supervisor` continuaria fora.
    loadIdentity.mockResolvedValue(identidade("executive"));

    await expect(RubricasPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadPayrollCodes).not.toHaveBeenCalled();
  });

  it("sem vínculo com o tenant não há tela", async () => {
    loadIdentity.mockResolvedValue(null);

    await expect(RubricasPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadPayrollCodes).not.toHaveBeenCalled();
  });

  it("✅ `owner` entra e vê a curadoria", async () => {
    await abrir("owner", LISTA);

    expect(notFound).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Rubricas" })).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent(
      "1 código usado pela folha sem categoria",
    );
    expect(screen.getByText("0001")).toBeVisible();
  });

  it("⛔ `hr` passa a porta, recebe 403, e a tela mostra a frase da API", async () => {
    // `hr` é admin e não tem `compensation`. Copiar a matriz de domínios aqui
    // seria a segunda cópia dela, longe do banco; a frase que explica a recusa
    // é escrita no backend, e é ela que a pessoa lê.
    await abrir("hr", { status: "forbidden", detail: RECUSA_DA_API });

    expect(notFound).not.toHaveBeenCalled();
    expect(screen.getByText(RECUSA_DA_API)).toBeVisible();
    expect(screen.getByText("Este papel não classifica rubrica")).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("403 sem detail não inventa a causa", async () => {
    await abrir("hr", { status: "forbidden", detail: null });

    expect(
      screen.getByText(/A API recusou a leitura para o seu papel/),
    ).toBeVisible();
  });

  it("null (sessão, 401, API fora do ar) é 'não pôde ser lido' — outra frase", async () => {
    await abrir("owner", null);

    expect(notFound).not.toHaveBeenCalled();
    expect(screen.getByText("As rubricas não puderam ser lidas")).toBeVisible();
    expect(screen.queryByText(RECUSA_DA_API)).toBeNull();
    expect(screen.queryByText("Este papel não classifica rubrica")).toBeNull();
  });
});
