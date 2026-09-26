import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import JustificativasDeAfastamentoPage from "@/app/dashboard/dp/justificativas/page";
import type { LeaveJustificationsResult } from "@/lib/dp/queries";
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
const loadLeaveJustifications = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  // `isAdmin` fica o real: é a porta sob teste, e ela é a mesma lista que
  // `util.is_admin` — o único eixo que as três rotas exigem.
  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/dp/queries", () => ({
  loadLeaveJustifications: () => loadLeaveJustifications(),
}));

function identidade(role: string): Identity {
  return {
    user_id: "11111111-1111-4111-8111-111111111111",
    email: `${role}@fastpark.dev`,
    tenant_id: "22222222-2222-4222-8222-222222222222",
    role,
  };
}

const FILA: LeaveJustificationsResult = {
  status: "ok",
  list: {
    rows: [
      {
        justification: "FALTA",
        occurrences: 1,
        first_leave: "2026-03-11",
        last_leave: "2026-03-11",
        category: null,
        validated: false,
        validated_at: null,
        notes: null,
        in_mirror: true,
      },
    ],
    pending: 1,
    without_justification: 0,
  },
};

const RECUSA_DA_API =
  "Classificar justificativa de afastamento é do administrador do cliente. Quem classifica decide quem perde cesta e quantos dias de vale transporte.";

async function abrir(role: string, result: LeaveJustificationsResult | null) {
  loadIdentity.mockResolvedValue(identidade(role));
  loadLeaveJustifications.mockResolvedValue(result);

  return render(await JustificativasDeAfastamentoPage());
}

beforeEach(() => {
  notFound.mockClear();
  loadIdentity.mockReset();
  loadLeaveJustifications.mockReset();
});

describe("a porta é `isAdmin`, e ela é o mesmo eixo que a rota exige", () => {
  it("⛔ `viewer` recebe 404, e a API nem é chamada", async () => {
    loadIdentity.mockResolvedValue(identidade("viewer"));

    await expect(JustificativasDeAfastamentoPage()).rejects.toThrow(
      "NEXT_NOT_FOUND",
    );
    expect(notFound).toHaveBeenCalled();
    expect(loadLeaveJustifications).not.toHaveBeenCalled();
  });

  it("⛔ `executive` também: lê a área de RH e não cura nada", async () => {
    // Ele está em `HR_ROLES` e não em `ADMIN_ROLES`. Sem este caso, trocar
    // `isAdmin` por `reachesHr` passaria verde.
    loadIdentity.mockResolvedValue(identidade("executive"));

    await expect(JustificativasDeAfastamentoPage()).rejects.toThrow(
      "NEXT_NOT_FOUND",
    );
    expect(loadLeaveJustifications).not.toHaveBeenCalled();
  });

  it("sem vínculo com o tenant não há tela", async () => {
    loadIdentity.mockResolvedValue(null);

    await expect(JustificativasDeAfastamentoPage()).rejects.toThrow(
      "NEXT_NOT_FOUND",
    );
    expect(loadLeaveJustifications).not.toHaveBeenCalled();
  });

  it("✅ `hr` entra — o eixo aqui é `util.is_admin` sozinho, sem domínio ao lado", async () => {
    // A diferença de Rubricas, e ela é o motivo de esta tela existir para o DP:
    // `hr` é admin e **não** tem `compensation`. Uma porta copiada de lá o
    // deixaria de fora da fila que destrava a apuração.
    await abrir("hr", FILA);

    expect(notFound).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", { name: "Justificativas de afastamento" }),
    ).toBeVisible();
    expect(screen.getAllByRole("status")[0]).toHaveTextContent(
      "1 justificativa sem aval",
    );
    expect(screen.getByText("FALTA")).toBeVisible();
  });

  it("✅ `owner` também, e a tela é a mesma", async () => {
    await abrir("owner", FILA);

    expect(notFound).not.toHaveBeenCalled();
    expect(screen.getByRole("table")).toBeVisible();
  });

  it("⛔ 403 mostra a frase que o backend escreveu, e não a tela", async () => {
    await abrir("owner", { status: "forbidden", detail: RECUSA_DA_API });

    expect(notFound).not.toHaveBeenCalled();
    expect(screen.getByText(RECUSA_DA_API)).toBeVisible();
    expect(
      screen.getByText(
        "Este papel não classifica justificativa de afastamento",
      ),
    ).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("403 sem detail não inventa a causa", async () => {
    await abrir("owner", { status: "forbidden", detail: null });

    expect(
      screen.getByText(/A API recusou a leitura para o seu papel/),
    ).toBeVisible();
  });

  it("null (sessão, 401, API fora do ar) é outra frase — e nunca 'sem pendência'", async () => {
    // O falso verde mais barato desta tela seria a fila não lida parecer curada.
    await abrir("owner", null);

    expect(notFound).not.toHaveBeenCalled();
    expect(
      screen.getByText("A fila de curadoria não pôde ser lida"),
    ).toBeVisible();
    expect(screen.queryByText("Sem pendência")).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
