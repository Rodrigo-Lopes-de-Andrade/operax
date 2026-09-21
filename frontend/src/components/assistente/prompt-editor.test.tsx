import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PromptEditor } from "@/components/assistente/prompt-editor";
import { ApiError } from "@/lib/api";
import type {
  AssistantDraft,
  PromptScreen,
  VersionRow,
  VersionsScreen,
} from "@/lib/assistente/config";

const saveDraft = vi.fn();
const publishPrompt = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push: vi.fn() }),
}));

vi.mock("@/lib/assistente/config", async () => {
  const actual = await vi.importActual<
    typeof import("@/lib/assistente/config")
  >("@/lib/assistente/config");
  // `publishFailureMessage` fica a real: o mapeamento dos cinco `detail` é o
  // que está sob teste.
  return {
    ...actual,
    saveDraft: (...args: unknown[]) => saveDraft(...args),
    // Com o argumento: é ELE que a corrida do `draft_moved` depende — um mock
    // que o descarta deixa `publishPrompt(null)` passar na suíte inteira.
    publishPrompt: (...args: unknown[]) => publishPrompt(...args),
  };
});

const PLATFORM_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const V3_ID = "33333333-3333-4333-8333-333333333333";
const V7_ID = "77777777-7777-4777-8777-777777777777";

const PLATFORM_TEXT = "Doutrina zz: nunca inventar número.";
const V3_TEXT = "Texto zz da v3, no ar.";
const V7_TEXT = "Texto zz da v7, o rascunho mais novo.";

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
    created_at: "2026-09-10T12:00:00Z",
    created_by: null,
    on_air: onAir,
  };
}

const VERSIONS: VersionsScreen = {
  tenant: [version(V7_ID, 7, V7_TEXT), version(V3_ID, 3, V3_TEXT, true)],
  platform: [version(PLATFORM_ID, 1, PLATFORM_TEXT, true)],
};

function draft(overrides: Partial<AssistantDraft> = {}): AssistantDraft {
  return {
    content: V7_TEXT,
    frozen_from_version_id: V7_ID,
    updated_at: "2026-09-17T12:00:00Z",
    updated_by: null,
    ...overrides,
  };
}

/** Um limite que não é o do backend hoje: prende que o contador lê a API. */
function prompt(overrides: Partial<PromptScreen> = {}): PromptScreen {
  return {
    platform: {
      version_id: PLATFORM_ID,
      version_number: 1,
      content: PLATFORM_TEXT,
      provider: "openai",
      model: "gpt-zz",
      max_steps: 4,
      created_at: "2026-09-01T12:00:00Z",
    },
    tenant: {
      version_id: V3_ID,
      version_number: 3,
      content: V3_TEXT,
      created_at: "2026-09-10T12:00:00Z",
      created_by: null,
    },
    draft: draft(),
    max_length: 500,
    draft_ahead_of_air: false,
    ...overrides,
  };
}

/** O estado da SPEC §2: rollback para a v3 com o rascunho partido da v7. */
const AHEAD = prompt({ draft_ahead_of_air: true });

const PHRASE =
  "Seu rascunho partiu da v7. No ar está a v3. Publicar substitui a v3.";

function textarea() {
  return screen.getByLabelText("Rascunho") as HTMLTextAreaElement;
}

function publicar() {
  return screen.getByRole("button", { name: "Publicar" });
}

function salvar() {
  return screen.getByRole("button", { name: "Salvar rascunho" });
}

beforeEach(() => {
  saveDraft.mockReset();
  publishPrompt.mockReset();
  refresh.mockReset();
});

describe("gate 1 — o caso da SPEC §2: as duas versões na tela", () => {
  it("⛔ com `draft_ahead_of_air`, a frase exata com 7 e 3 — e os dois textos visíveis ao mesmo tempo", () => {
    render(<PromptEditor screen={AHEAD} versions={VERSIONS} />);

    expect(screen.getByText(PHRASE)).toBeVisible();
    // As duas caixas, e as duas visíveis: o texto no ar não está dobrado, e o
    // rascunho é o que está na caixa de edição.
    expect(screen.getByText(V3_TEXT)).toBeVisible();
    expect(textarea()).toBeVisible();
    expect(textarea().value).toBe(V7_TEXT);
  });

  it("sem `draft_ahead_of_air` não há aviso", () => {
    render(<PromptEditor screen={prompt()} versions={VERSIONS} />);

    expect(screen.queryByText(/Seu rascunho partiu/)).toBeNull();
    // O texto no ar continua na tela — dobrado, mas lá.
    expect(screen.getByText(V3_TEXT)).toBeInTheDocument();
  });

  it("⛔ o número da origem vem da lista de versões, não do id: sem lista, a frase diz que não sabe — e ainda mostra as duas caixas", () => {
    render(<PromptEditor screen={AHEAD} versions={null} />);

    expect(
      screen.getByText(
        "Seu rascunho partiu de uma versão que não está no histórico. No ar está a v3. Publicar substitui a v3.",
      ),
    ).toBeVisible();
    expect(screen.getByText(V3_TEXT)).toBeVisible();
  });

  it("rascunho de antes da primeira publicação, com versão no ar: a frase diz isso e o que Publicar substitui", () => {
    render(
      <PromptEditor
        screen={prompt({
          draft: draft({ frozen_from_version_id: null }),
          draft_ahead_of_air: true,
        })}
        versions={VERSIONS}
      />,
    );

    expect(
      screen.getByText(
        "Seu rascunho partiu de antes da primeira versão publicada. No ar está a v3. Publicar substitui a v3.",
      ),
    ).toBeVisible();
  });

  it("sem versão de tenant no ar: 'No ar está só a camada da plataforma.'", () => {
    render(
      <PromptEditor
        screen={prompt({ tenant: null, draft_ahead_of_air: true })}
        versions={VERSIONS}
      />,
    );

    expect(
      screen.getByText(
        "Seu rascunho partiu da v7. No ar está só a camada da plataforma. Publicar põe o rascunho no ar.",
      ),
    ).toBeVisible();
  });
});

describe("a camada da plataforma é leitura", () => {
  it("mostra provedor, modelo, teto de idas e o texto inteiro — e diz que não se edita pelo painel", () => {
    render(<PromptEditor screen={prompt()} versions={VERSIONS} />);

    expect(screen.getByText("Camada da plataforma — v1")).toBeVisible();
    expect(screen.getByText("openai")).toBeVisible();
    expect(screen.getByText("gpt-zz")).toBeVisible();
    expect(screen.getByText("4")).toBeVisible();
    expect(screen.getByText(PLATFORM_TEXT)).toBeInTheDocument();
    expect(screen.getByText(/não se edita pelo painel/)).toBeVisible();
    // Uma caixa de edição só: a do rascunho.
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
  });

  it("`max_steps` nulo é 'sem teto', não zero", () => {
    render(
      <PromptEditor
        screen={prompt({ platform: { ...prompt().platform, max_steps: null } })}
        versions={VERSIONS}
      />,
    );

    expect(screen.getByText("sem teto")).toBeVisible();
  });
});

describe("o contador lê o limite da API", () => {
  it("⛔ `n / max_length` com o valor que veio — não os 12000 do backend de hoje", async () => {
    const user = userEvent.setup();
    render(
      <PromptEditor
        screen={prompt({ draft: null, draft_ahead_of_air: false })}
        versions={VERSIONS}
      />,
    );

    expect(screen.getByText("0 / 500")).toBeVisible();
    expect(textarea()).toHaveAttribute("maxlength", "500");

    await user.type(textarea(), "doze letras");

    expect(screen.getByText("11 / 500")).toBeVisible();
  });
});

describe("salvar e publicar", () => {
  it("Salvar rascunho é PUT com o texto da caixa, e a tela recarrega", async () => {
    const user = userEvent.setup();
    saveDraft.mockResolvedValue(draft({ content: "Texto zz novo" }));
    render(
      <PromptEditor screen={prompt({ draft: null })} versions={VERSIONS} />,
    );

    await user.type(textarea(), "Texto zz novo");
    await user.click(salvar());

    await waitFor(() =>
      expect(saveDraft).toHaveBeenCalledWith("Texto zz novo"),
    );
    expect(await screen.findByText("Rascunho salvo.")).toBeVisible();
    expect(refresh).toHaveBeenCalled();
  });

  it("⛔ Publicar com a caixa diferente do salvo NÃO chama a API: pede para salvar", async () => {
    const user = userEvent.setup();
    render(<PromptEditor screen={prompt()} versions={VERSIONS} />);

    await user.type(textarea(), " mais uma frase");
    await user.click(publicar());

    expect(
      screen.getByText("Salve o rascunho antes de publicar."),
    ).toBeVisible();
    expect(publishPrompt).not.toHaveBeenCalled();
  });

  it("⛔ sem rascunho nenhum no servidor, Publicar também pede para salvar antes", async () => {
    const user = userEvent.setup();
    render(
      <PromptEditor screen={prompt({ draft: null })} versions={VERSIONS} />,
    );

    await user.click(publicar());

    expect(
      screen.getByText("Salve o rascunho antes de publicar."),
    ).toBeVisible();
    expect(publishPrompt).not.toHaveBeenCalled();
  });

  it("✅ com o rascunho salvo, Publicar chama a API, diz a versão e recarrega", async () => {
    const user = userEvent.setup();
    publishPrompt.mockResolvedValue({
      version_id: "88888888-8888-4888-8888-888888888888",
      version_number: 8,
      previous_version_id: V3_ID,
    });
    render(<PromptEditor screen={AHEAD} versions={VERSIONS} />);

    await user.click(publicar());

    expect(await screen.findByText("Publicada a v8.")).toBeVisible();
    expect(publishPrompt).toHaveBeenCalledTimes(1);
    // ⛔ E diz QUAL rascunho a tela viu: o `updated_at` do render. Sem isso a
    // RPC congela o que estiver na tabela na hora, e dois admins no mesmo
    // minuto publicam o texto um do outro.
    expect(publishPrompt).toHaveBeenCalledWith("2026-09-17T12:00:00Z");
  });

  it("⛔ Salvar e depois Publicar manda o updated_at NOVO, não o do render", async () => {
    // Se o `seenAt` não acompanhasse o salvamento, todo Publicar depois de um
    // Salvar viraria `draft_moved` — o painel deixaria de publicar, com a
    // suíte verde. O mock devolve um `updated_at` posterior ao do render.
    const user = userEvent.setup();
    saveDraft.mockResolvedValue(
      draft({ content: "Texto zz novo", updated_at: "2026-09-20T15:30:00Z" }),
    );
    publishPrompt.mockResolvedValue({
      version_id: "88888888-8888-4888-8888-888888888888",
      version_number: 8,
      previous_version_id: V3_ID,
    });
    render(<PromptEditor screen={AHEAD} versions={VERSIONS} />);

    await user.clear(textarea());
    await user.type(textarea(), "Texto zz novo");
    await user.click(salvar());
    expect(await screen.findByText("Rascunho salvo.")).toBeVisible();
    await user.click(publicar());

    expect(await screen.findByText("Publicada a v8.")).toBeVisible();
    expect(publishPrompt).toHaveBeenCalledWith("2026-09-20T15:30:00Z");
    expect(publishPrompt).not.toHaveBeenCalledWith("2026-09-17T12:00:00Z");
    expect(refresh).toHaveBeenCalled();
  });

  it.each([
    [403, "not_admin", "Sem permissão para publicar."],
    [404, "draft_not_found", "Salve o rascunho antes de publicar."],
    [422, "draft_empty", "O rascunho está vazio."],
    [
      409,
      "platform_layer_missing",
      "A camada da plataforma não está publicada — fale com o suporte.",
    ],
    [
      409,
      "draft_unchanged",
      "O texto já está no ar: nada mudou desde a última publicação.",
    ],
  ])("%s `%s` → %s", async (status, detail, phrase) => {
    const user = userEvent.setup();
    publishPrompt.mockRejectedValue(new ApiError(status, detail));
    render(<PromptEditor screen={prompt()} versions={VERSIONS} />);

    await user.click(publicar());

    expect(await screen.findByRole("alert")).toHaveTextContent(phrase);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("um `detail` que não é dos cinco chega como veio", async () => {
    const user = userEvent.setup();
    publishPrompt.mockRejectedValue(new ApiError(429, "Aguarde 30 segundos."));
    render(<PromptEditor screen={prompt()} versions={VERSIONS} />);

    await user.click(publicar());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Aguarde 30 segundos.",
    );
  });

  it("um erro ao salvar mostra o `detail` e não diz que salvou", async () => {
    const user = userEvent.setup();
    saveDraft.mockRejectedValue(
      new ApiError(403, "Sem permissão para editar o rascunho."),
    );
    render(
      <PromptEditor screen={prompt({ draft: null })} versions={VERSIONS} />,
    );

    await user.type(textarea(), "x");
    await user.click(salvar());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Sem permissão para editar o rascunho.",
    );
    expect(screen.queryByText("Rascunho salvo.")).toBeNull();
    expect(refresh).not.toHaveBeenCalled();
  });
});
