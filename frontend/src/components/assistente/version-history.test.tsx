import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { VersionHistory } from "@/components/assistente/version-history";
import { ApiError } from "@/lib/api";
import type { VersionRow, VersionsScreen } from "@/lib/assistente/config";

const restoreVersion = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push: vi.fn() }),
}));

vi.mock("@/lib/assistente/config", async () => {
  const actual = await vi.importActual<
    typeof import("@/lib/assistente/config")
  >("@/lib/assistente/config");
  return {
    ...actual,
    restoreVersion: (...args: unknown[]) => restoreVersion(...args),
  };
});

const V1_ID = "11111111-1111-4111-8111-111111111111";
const V2_ID = "22222222-2222-4222-8222-222222222222";
const V3_ID = "33333333-3333-4333-8333-333333333333";
const PLATFORM_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

function version(
  id: string,
  number: number,
  content: string,
  onAir = false,
): VersionRow {
  return {
    version_id: id,
    version_number: number,
    content,
    // 13:05 UTC é 10:05 em São Paulo — a data sai no fuso do tenant.
    created_at: "2026-09-15T13:05:00Z",
    created_by: null,
    on_air: onAir,
  };
}

/** Rollback feito: a v1 está no ar, a v3 é a mais nova. */
const VERSIONS: VersionsScreen = {
  tenant: [
    version(
      V3_ID,
      3,
      "Responda em português.\nSeja direto.\nDeclare o período.",
    ),
    version(V2_ID, 2, "Responda em português.\nDeclare o período."),
    version(
      V1_ID,
      1,
      "Responda em português.\nSeja breve.\nDeclare o período.",
      true,
    ),
  ],
  platform: [version(PLATFORM_ID, 1, "Doutrina zz.", true)],
};

function lista(nome: string) {
  return within(screen.getByRole("list", { name: nome }));
}

beforeEach(() => {
  restoreVersion.mockReset();
  refresh.mockReset();
});

describe("a lista", () => {
  it("as versões do cliente, com número, data e o selo 'No ar' na apontada — e a plataforma à parte, sem link", () => {
    render(<VersionHistory versions={VERSIONS} selectedId={null} />);

    const tenant = lista("Versões do cliente");
    expect(tenant.getAllByRole("listitem")).toHaveLength(3);
    expect(tenant.getByRole("link", { name: "v3" })).toHaveAttribute(
      "href",
      `/dashboard/administracao/assistente?aba=historico&versao=${V3_ID}`,
    );
    expect(tenant.getAllByText("15/09/2026 às 10:05")).toHaveLength(3);
    // Um selo só, na v1.
    expect(tenant.getAllByText("No ar")).toHaveLength(1);
    expect(
      within(tenant.getAllByRole("listitem")[2]).getByText("No ar"),
    ).toBeVisible();

    const platform = lista("Versões da plataforma");
    expect(platform.getAllByRole("listitem")).toHaveLength(1);
    expect(platform.queryByRole("link")).toBeNull();
    expect(platform.getByText("No ar")).toBeVisible();
    expect(platform.getByText("Doutrina zz.")).toBeInTheDocument();
  });

  it("sem versão do cliente, a frase de vazio — e nenhum botão de restaurar", () => {
    render(
      <VersionHistory
        versions={{ tenant: [], platform: VERSIONS.platform }}
        selectedId={null}
      />,
    );

    expect(screen.getByText("Nenhuma versão publicada ainda")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Restaurar esta versão" }),
    ).toBeNull();
  });
});

describe("a versão aberta", () => {
  it("mostra o texto e o diff contra a que está no ar — a linha trocada aparece nos dois sentidos", () => {
    render(<VersionHistory versions={VERSIONS} selectedId={V3_ID} />);

    expect(screen.getByLabelText("Texto da v3")).toHaveTextContent(
      "Seja direto.",
    );
    expect(screen.getByText("Diferença em relação à v1 (no ar)")).toBeVisible();

    const linhas = within(
      screen.getByRole("list", { name: "Diferenças" }),
    ).getAllByRole("listitem");
    expect(linhas.map((linha) => linha.getAttribute("data-kind"))).toEqual([
      "same",
      "removed",
      "added",
      "same",
    ]);
    expect(linhas[1]).toHaveTextContent("Seja breve.");
    expect(linhas[2]).toHaveTextContent("Seja direto.");
  });

  it("⛔ a que já está no ar não tem botão de restaurar, nem diff", () => {
    render(<VersionHistory versions={VERSIONS} selectedId={V1_ID} />);

    expect(screen.getByText("Esta é a versão no ar.")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Restaurar esta versão" }),
    ).toBeNull();
    expect(screen.queryByRole("list", { name: "Diferenças" })).toBeNull();
  });

  it("um `versao=` que não é do cliente não abre nada", () => {
    render(<VersionHistory versions={VERSIONS} selectedId={PLATFORM_ID} />);

    expect(
      screen.queryByRole("button", { name: "Restaurar esta versão" }),
    ).toBeNull();
    expect(screen.queryByRole("list", { name: "Diferenças" })).toBeNull();
  });
});

describe("restaurar", () => {
  it("⛔ pede confirmação em texto, e só o Confirmar chama a rota — com o id certo", async () => {
    const user = userEvent.setup();
    restoreVersion.mockResolvedValue(version(V3_ID, 3, "…", true));
    render(<VersionHistory versions={VERSIONS} selectedId={V3_ID} />);

    await user.click(
      screen.getByRole("button", { name: "Restaurar esta versão" }),
    );

    expect(
      screen.getByText(
        "Restaurar a v3 move o que está no ar. O rascunho não muda.",
      ),
    ).toBeVisible();
    expect(restoreVersion).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    expect(restoreVersion).toHaveBeenCalledWith(V3_ID);
    expect(await screen.findByText("A v3 está no ar.")).toBeVisible();
    expect(refresh).toHaveBeenCalled();
  });

  it("Cancelar fecha a confirmação sem chamar nada", async () => {
    const user = userEvent.setup();
    render(<VersionHistory versions={VERSIONS} selectedId={V2_ID} />);

    await user.click(
      screen.getByRole("button", { name: "Restaurar esta versão" }),
    );
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(
      screen.queryByText(
        "Restaurar a v2 move o que está no ar. O rascunho não muda.",
      ),
    ).toBeNull();
    expect(restoreVersion).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Restaurar esta versão" }),
    ).toBeVisible();
  });

  it("404 (versão de outro cliente, ou apagada) mostra o `detail` e não recarrega", async () => {
    const user = userEvent.setup();
    restoreVersion.mockRejectedValue(
      new ApiError(404, "Versão não encontrada."),
    );
    render(<VersionHistory versions={VERSIONS} selectedId={V2_ID} />);

    await user.click(
      screen.getByRole("button", { name: "Restaurar esta versão" }),
    );
    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Versão não encontrada.",
    );
    expect(refresh).not.toHaveBeenCalled();
  });
});
