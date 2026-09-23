import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RegrasPage from "@/app/dashboard/administracao/regras/page";
import { DOCTRINE } from "@/components/canais/rules";
import type { TemplateRow } from "@/lib/canais/queries";
import type { AlertRuleRow, ContactRow } from "@/lib/canais/regras";
import type { Identity } from "@/lib/identity";
import type { UnitOption } from "@/lib/ponto/queries";

vi.mock("server-only", () => ({}));

const notFound = vi.fn(() => {
  throw new Error("NEXT_NOT_FOUND");
});

vi.mock("next/navigation", () => ({
  notFound: () => notFound(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const loadIdentity = vi.fn();
const loadRules = vi.fn();
const loadTemplates = vi.fn();
const loadContacts = vi.fn();
const loadUnits = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/canais/queries", () => ({
  loadRules: () => loadRules(),
  loadTemplates: () => loadTemplates(),
  loadContacts: () => loadContacts(),
}));

vi.mock("@/lib/ponto/queries", () => ({
  loadUnits: (...args: unknown[]) => loadUnits(...args),
}));

const { SUPABASE } = vi.hoisted(() => ({ SUPABASE: { caminho: 1 } }));

vi.mock("@/lib/supabase-server", () => ({
  getServerSupabase: async () => SUPABASE,
}));

function identidade(role: string): Identity {
  return {
    user_id: "11111111-1111-4111-8111-111111111111",
    email: `${role}@fastpark.dev`,
    tenant_id: "22222222-2222-4222-8222-222222222222",
    role,
  };
}

const UNIDADE: UnitOption = {
  unitId: "11111111-1111-4111-8111-111111111111",
  code: "ZZA",
  slug: "zza",
  name: "Unidade Zz Alfa",
  companyId: "33333333-3333-4333-8333-333333333333",
  companyName: "Zz Ltda",
  companySlug: "zz-ltda",
};

const TEMPLATES: TemplateRow[] = [];
const CONTATOS: ContactRow[] = [];

/** Uma regra ligada com a razão que só o backend escreve. */
const REGRA: AlertRuleRow = {
  id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  name: "Regra Zz",
  deviation_type: null,
  scope_unit_id: null,
  scope_unit_name: null,
  content: "aggregate",
  channel: "whatsapp",
  cron_window: null,
  threshold_minutes: null,
  threshold_occurrences: null,
  muted_until: null,
  template_code: null,
  active: true,
  targets: [],
  blocked_reason: "Zz razão que só o backend escreve.",
};

async function abrir(role: string, rules: AlertRuleRow[] | null) {
  loadIdentity.mockResolvedValue(identidade(role));
  loadRules.mockResolvedValue(rules);
  loadTemplates.mockResolvedValue(TEMPLATES);
  loadContacts.mockResolvedValue(CONTATOS);
  loadUnits.mockResolvedValue([UNIDADE]);

  return render(await RegrasPage());
}

beforeEach(() => {
  notFound.mockClear();
  for (const mock of [
    loadIdentity,
    loadRules,
    loadTemplates,
    loadContacts,
    loadUnits,
  ]) {
    mock.mockReset();
  }
});

describe("a porta da página é `isAdmin` — e aqui coincide com a rota", () => {
  it("⛔ `unit_supervisor` recebe 404, e nenhuma das cinco leituras é chamada", async () => {
    loadIdentity.mockResolvedValue(identidade("unit_supervisor"));

    await expect(RegrasPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalled();
    expect(loadRules).not.toHaveBeenCalled();
    expect(loadTemplates).not.toHaveBeenCalled();
    expect(loadContacts).not.toHaveBeenCalled();
    expect(loadUnits).not.toHaveBeenCalled();
  });

  it("⛔ `executive` também recebe 404", async () => {
    loadIdentity.mockResolvedValue(identidade("executive"));

    await expect(RegrasPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadRules).not.toHaveBeenCalled();
  });

  it("sem vínculo com o tenant não há tela", async () => {
    loadIdentity.mockResolvedValue(null);

    await expect(RegrasPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadRules).not.toHaveBeenCalled();
  });

  it("✅ `owner` entra e vê a doutrina, a regra com o rótulo do catálogo e o `blocked_reason` como veio", async () => {
    await abrir("owner", [REGRA]);

    expect(notFound).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", { level: 1, name: "Regras" }),
    ).toBeVisible();
    expect(screen.getByText(DOCTRINE)).toBeVisible();
    expect(screen.queryByText(/Atraso Zz/)).toBeNull();
    expect(
      screen.getByText("Zz razão que só o backend escreve."),
    ).toBeVisible();
    // As cinco leituras, uma vez cada; as unidades pelo cliente do Caminho 1.
    expect(loadRules).toHaveBeenCalledTimes(1);
    expect(loadTemplates).toHaveBeenCalledTimes(1);
    expect(loadContacts).toHaveBeenCalledTimes(1);
    expect(loadUnits).toHaveBeenCalledWith(SUPABASE);
  });

  it("`null` nas regras é 'não puderam ser lidas' — não 'nenhuma regra'", async () => {
    await abrir("hr", null);

    expect(screen.getByText("As regras não puderam ser lidas")).toBeVisible();
    expect(screen.queryByText("Nenhuma regra neste cliente")).toBeNull();
    expect(screen.queryByRole("button", { name: "Nova regra" })).toBeNull();
  });

  it("lista vazia é o estado do primeiro dia, com o botão de nova regra", async () => {
    await abrir("personnel", []);

    expect(screen.getByText("Nenhuma regra neste cliente")).toBeVisible();
    expect(screen.getByRole("button", { name: "Nova regra" })).toBeVisible();
  });
});
