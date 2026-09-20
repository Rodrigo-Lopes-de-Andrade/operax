import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Capabilities } from "@/components/assistente/capabilities";
import { ApiError } from "@/lib/api";
import type { CapabilityRow } from "@/lib/assistente/config";

const saveCapability = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/assistente/config", async () => {
  const actual = await vi.importActual<
    typeof import("@/lib/assistente/config")
  >("@/lib/assistente/config");
  // `domainLabel` fica o real: os rótulos pt-BR estão sob teste.
  return {
    ...actual,
    saveCapability: (...args: unknown[]) => saveCapability(...args),
  };
});

function capability(overrides: Partial<CapabilityRow> = {}): CapabilityRow {
  return {
    code: "zz_metrica_um",
    title: "Desvios por unidade",
    description: "Quantos indícios cada unidade acumulou no período.",
    domain: null,
    enabled: true,
    visible_to_me: true,
    ...overrides,
  };
}

/** Ligada, com domínio que quem olha NÃO alcança — o selo existe por ela. */
const OUT_OF_REACH = capability({
  code: "zz_metrica_remuneracao",
  title: "Custo por unidade",
  description: "Quanto cada unidade custou no período.",
  domain: "compensation",
  enabled: true,
  visible_to_me: false,
});

/** Desligada pelo cliente: `visible_to_me` é falso por consequência, não por domínio. */
const DISABLED = capability({
  code: "zz_metrica_desligada",
  title: "Recorrência por colaborador",
  description: "Quem repetiu indício no período.",
  domain: "pii",
  enabled: false,
  visible_to_me: false,
});

const ROWS: CapabilityRow[] = [capability(), OUT_OF_REACH, DISABLED];

const RULE =
  "Desligar tira a métrica do assistente para todo mundo. Ligar não dá acesso a dado que o papel não alcança.";

function linhas() {
  return within(
    screen.getByRole("table", { name: "Métricas do assistente" }),
  ).getAllByRole("row");
}

function interruptor(titulo: string) {
  return screen.getByRole("switch", { name: `Ligada: ${titulo}` });
}

beforeEach(() => {
  saveCapability.mockReset();
});

describe("a §4.1 na tela — e o que ela NÃO é", () => {
  it("⛔ a linha fixa está em cima, literal", () => {
    render(<Capabilities rows={ROWS} />);

    expect(screen.getByText(RULE)).toBeVisible();
  });

  it("⛔ SEM 'criar métrica' (§4.4): nenhum botão de criar, e nenhum filtro, busca ou ordenação", () => {
    render(<Capabilities rows={ROWS} />);

    for (const proibido of [/criar/i, /nova métrica/i, /adicionar/i]) {
      expect(screen.queryByRole("button", { name: proibido })).toBeNull();
      expect(screen.queryByRole("link", { name: proibido })).toBeNull();
    }
    // Sem caixa de busca e sem select de ordenação: a lista é de ~15 linhas.
    expect(screen.queryByRole("searchbox")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    // Os únicos controles são os interruptores, um por linha.
    expect(screen.getAllByRole("switch")).toHaveLength(ROWS.length);
  });
});

describe("as linhas", () => {
  it("título, descrição, domínio em pt-BR e o estado do interruptor", () => {
    render(<Capabilities rows={ROWS} />);

    // Cabeçalho + três linhas.
    expect(linhas()).toHaveLength(4);
    expect(screen.getByText("Desvios por unidade")).toBeVisible();
    expect(
      screen.getByText("Quantos indícios cada unidade acumulou no período."),
    ).toBeVisible();
    expect(screen.getByText("Remuneração")).toBeVisible();
    expect(screen.getByText("Dados pessoais")).toBeVisible();
    // Domínio nulo é travessão, não vazio.
    expect(screen.getByText("—")).toBeVisible();

    expect(interruptor("Desvios por unidade")).toBeChecked();
    expect(interruptor("Recorrência por colaborador")).not.toBeChecked();
  });

  it("⛔ o selo 'fora do seu alcance' só na linha LIGADA que o papel não alcança", () => {
    render(<Capabilities rows={ROWS} />);

    const selos = screen.getAllByText("fora do seu alcance");
    expect(selos).toHaveLength(1);

    // Ele está na linha da métrica ligada e invisível…
    const linhaLigada = screen.getByText("Custo por unidade").closest("tr");
    expect(
      within(linhaLigada as HTMLElement).getByText("fora do seu alcance"),
    ).toBeVisible();

    // …e não na desligada, que também tem `visible_to_me: false`. A desligada
    // já diz o que precisa pelo interruptor: repetir o selo nela leria como
    // "o seu papel não alcança", que é outra coisa.
    const linhaDesligada = screen
      .getByText("Recorrência por colaborador")
      .closest("tr");
    expect(
      within(linhaDesligada as HTMLElement).queryByText("fora do seu alcance"),
    ).toBeNull();
  });

  it("uma métrica ligada e ao alcance não ganha selo nenhum", () => {
    render(<Capabilities rows={[capability()]} />);

    expect(screen.queryByText("fora do seu alcance")).toBeNull();
  });

  it("catálogo vazio mostra o estado vazio, e não uma tabela de zero linhas", () => {
    render(<Capabilities rows={[]} />);

    expect(screen.getByText("Nenhuma métrica no catálogo")).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("o interruptor", () => {
  it("⛔ chama PUT com o `enabled` INVERTIDO, e substitui a linha pela devolvida", async () => {
    const user = userEvent.setup();
    saveCapability.mockResolvedValue({
      ...capability(),
      enabled: false,
      visible_to_me: false,
    });
    render(<Capabilities rows={ROWS} />);

    await user.click(interruptor("Desvios por unidade"));

    expect(saveCapability).toHaveBeenCalledWith("zz_metrica_um", false);
    // A linha que volta é a que a tela mostra — não o que ela supôs.
    expect(interruptor("Desvios por unidade")).not.toBeChecked();
  });

  it("⛔ a tela reflete a RESPOSTA, mesmo quando ela contraria o clique", async () => {
    const user = userEvent.setup();
    // A régua é uma só: se o backend devolver ligada, ligada fica. Um estado
    // otimista teria mostrado desligada e divergido do runtime em silêncio.
    saveCapability.mockResolvedValue({ ...capability(), enabled: true });
    render(<Capabilities rows={[capability()]} />);

    await user.click(interruptor("Desvios por unidade"));

    expect(saveCapability).toHaveBeenCalledWith("zz_metrica_um", false);
    expect(interruptor("Desvios por unidade")).toBeChecked();
  });

  it("ligar uma desligada manda `true` — e o selo aparece se ela seguir fora do alcance", async () => {
    const user = userEvent.setup();
    saveCapability.mockResolvedValue({
      ...DISABLED,
      enabled: true,
      visible_to_me: false,
    });
    render(<Capabilities rows={[DISABLED]} />);

    expect(screen.queryByText("fora do seu alcance")).toBeNull();

    await user.click(interruptor("Recorrência por colaborador"));

    expect(saveCapability).toHaveBeenCalledWith("zz_metrica_desligada", true);
    expect(await screen.findByText("fora do seu alcance")).toBeVisible();
  });

  it("403 vira frase e a linha não muda", async () => {
    const user = userEvent.setup();
    saveCapability.mockRejectedValue(
      new ApiError(403, "Sem permissão para ligar ou desligar uma métrica."),
    );
    render(<Capabilities rows={[capability()]} />);

    await user.click(interruptor("Desvios por unidade"));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Sem permissão para ligar ou desligar uma métrica.",
    );
    expect(interruptor("Desvios por unidade")).toBeChecked();
  });

  it("404 é 'Métrica não encontrada.'", async () => {
    const user = userEvent.setup();
    saveCapability.mockRejectedValue(
      new ApiError(404, "Métrica não encontrada."),
    );
    render(<Capabilities rows={[capability()]} />);

    await user.click(interruptor("Desvios por unidade"));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Métrica não encontrada.",
    );
  });

  it("uma falha sem `detail` cai na frase genérica, e diz que nada mudou", async () => {
    const user = userEvent.setup();
    saveCapability.mockRejectedValue(new ApiError(504, null));
    render(<Capabilities rows={[capability()]} />);

    await user.click(interruptor("Desvios por unidade"));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não consegui gravar a métrica. Nada foi alterado.",
    );
  });
});
