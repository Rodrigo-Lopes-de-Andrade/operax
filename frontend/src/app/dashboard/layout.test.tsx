import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DashboardLayout from "@/app/dashboard/layout";

vi.mock("server-only", () => ({}));

const loadIdentity = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  // `isAdmin` e `reachesHr` ficam os reais: quais papéis cada lista contém já
  // tem teste, e o que falta é qual das duas alimenta qual prop.
  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/supabase-server", () => ({
  getCurrentUser: async () => ({ id: "u-1", email: "quem@fastpark.dev" }),
}));

vi.mock("next/headers", () => ({
  headers: async () => new Headers(),
}));

vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
  useRouter: () => ({ refresh: vi.fn() }),
}));

vi.mock("@/state/session", () => ({
  SessionProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

/** Grava a fiação em vez de renderizar a sidebar — ela tem teste próprio. */
const shellProps = vi.fn();

vi.mock("@/components/app-shell", () => ({
  AppShell: (props: { showAdmin: boolean; showAdminWrites: boolean }) => {
    shellProps(props);
    return null;
  },
}));

async function montar(role: string | null) {
  loadIdentity.mockResolvedValue(role === null ? null : { role });

  render(await DashboardLayout({ children: <p>conteúdo</p> }));

  const { showAdmin, showAdminWrites } = shellProps.mock.calls[0][0];
  return { showAdmin, showAdminWrites };
}

beforeEach(() => {
  loadIdentity.mockReset();
  shellProps.mockReset();
});

/**
 * Qual eixo alimenta qual prop — e só isso.
 *
 * A sidebar decide certo a partir das duas props, e isso é de
 * `app-shell.test.tsx`. Quem as escolhe é este arquivo, e trocar uma pela outra
 * deixa aquela suíte inteira verde: ela recebe booleanos, não papéis. O eixo de
 * leitura é `HR_ROLES` e o de escrita é `util.is_admin` — `executive` é a única
 * linha em que os dois discordam, e é por isso que é ele quem responde aqui.
 */
describe("o layout escolhe qual eixo alimenta a sidebar", () => {
  it("⛔ `executive` lê a área de RH e não recebe os itens de escrita", async () => {
    expect(await montar("executive")).toEqual({
      showAdmin: true,
      showAdminWrites: false,
    });
  });

  it("✅ `owner` recebe os dois — sem ele, um `false` fixo passaria acima", async () => {
    expect(await montar("owner")).toEqual({
      showAdmin: true,
      showAdminWrites: true,
    });
  });

  it("⛔ `personnel` recebe os dois: é o DP, e ele escreve", async () => {
    // O papel que mais usa estas telas, e o único de `util.is_admin` que não
    // era exercitado em lugar nenhum da suíte. `owner` acima passaria igual se
    // `personnel` saísse de qualquer uma das duas listas.
    expect(await montar("personnel")).toEqual({
      showAdmin: true,
      showAdminWrites: true,
    });
  });

  it("`accounting` não recebe nenhum dos dois: a porta dele é o Painel de DP", async () => {
    expect(await montar("accounting")).toEqual({
      showAdmin: false,
      showAdminWrites: false,
    });
  });

  it("sem vínculo com tenant nenhum, a sidebar não oferece área alguma", async () => {
    // `/me` responde 403 a quem entrou e ainda não pertence a tenant nenhum, e
    // `loadIdentity` devolve `null`. A área tem de renderizar sem seção de
    // administração, em vez de estourar num `undefined`.
    expect(await montar(null)).toEqual({
      showAdmin: false,
      showAdminWrites: false,
    });
  });
});
