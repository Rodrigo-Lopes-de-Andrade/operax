import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import {
  domainLabel,
  publishFailureMessage,
  publishPrompt,
  restoreVersion,
  saveCapability,
  saveDraft,
  testAssistant,
  type CapabilityRow,
} from "@/lib/assistente/config";

const request = vi.fn();
const stream = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    requestApiAsUser: (...args: unknown[]) => request(...args),
  };
});

vi.mock("@/lib/assistente/stream", () => ({
  streamAssistant: (...args: unknown[]) => stream(...args),
}));

const VERSION = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

beforeEach(() => {
  request.mockReset();
  stream.mockReset();
});

describe("as mutações batem na rota certa, com o corpo do contrato", () => {
  it("salvar o rascunho é PUT /rascunho com `{content}`", async () => {
    request.mockResolvedValue({
      content: "Chame de indício.",
      frozen_from_version_id: null,
      updated_at: "2026-09-18T12:00:00Z",
      updated_by: null,
    });

    await saveDraft("Chame de indício.");

    expect(request).toHaveBeenCalledWith("/assistente/configuracao/rascunho", {
      method: "PUT",
      body: { content: "Chame de indício." },
    });
  });

  it("publicar é POST /publicar sem corpo — o rascunho já está no servidor", async () => {
    request.mockResolvedValue({
      version_id: VERSION,
      version_number: 4,
      previous_version_id: null,
    });

    await publishPrompt("2026-09-20T12:00:00Z");

    expect(request).toHaveBeenCalledWith("/assistente/configuracao/publicar", {
      method: "POST",
      body: { seen_updated_at: "2026-09-20T12:00:00Z" },
    });
  });

  it("⛔ publicar diz QUAL rascunho a tela viu — sem isso `draft_moved` não existe", async () => {
    // A RPC congela o que estiver na tabela no instante da chamada. Se este
    // corpo não viajar, dois admins no mesmo minuto e um publica o texto do
    // outro: a recusa existe no banco desde a A4 e só dispara com o que a
    // tela leu. Nulo é válido — é a primeira publicação, sem rascunho lido.
    request.mockResolvedValue({
      version_id: VERSION,
      version_number: 1,
      previous_version_id: null,
    });

    await publishPrompt(null);

    const [, options] = request.mock.calls[0] as [
      string,
      { method: string; body?: Record<string, unknown> },
    ];
    expect(options.body).toEqual({ seen_updated_at: null });
  });

  it("restaurar é POST /versoes/{id}/restaurar com o id da versão", async () => {
    request.mockResolvedValue({
      version_id: VERSION,
      version_number: 2,
      content: "…",
      created_at: "2026-09-18T12:00:00Z",
      created_by: null,
    });

    await restoreVersion(VERSION);

    expect(request).toHaveBeenCalledWith(
      `/assistente/configuracao/versoes/${VERSION}/restaurar`,
      { method: "POST" },
    );
  });

  it("ligar ou desligar é PUT /capacidades/{code} com `{enabled}`, e devolve a linha da régua", async () => {
    const saved: CapabilityRow = {
      code: "deviations_total",
      title: "Total de desvios",
      description: "…",
      domain: null,
      enabled: false,
      visible_to_me: false,
    };
    request.mockResolvedValue(saved);

    await expect(saveCapability("deviations_total", false)).resolves.toBe(
      saved,
    );

    expect(request).toHaveBeenCalledWith(
      "/assistente/configuracao/capacidades/deviations_total",
      { method: "PUT", body: { enabled: false } },
    );
  });

  it("⛔ o teste vai pelo MESMO transporte da conversa, contra /testar, com `use_draft`", async () => {
    stream.mockResolvedValue(undefined);
    const onEvent = vi.fn();

    await testAssistant("Quantos desvios?", true, { onEvent });

    expect(stream).toHaveBeenCalledWith(
      "/assistente/configuracao/testar",
      { question: "Quantos desvios?", use_draft: true },
      { onEvent },
    );
    // Nenhum papel viaja no corpo: o teste roda como quem chamou, sempre.
    const [, body] = stream.mock.calls[0] as [string, Record<string, unknown>];
    expect(Object.keys(body).sort()).toEqual(["question", "use_draft"]);
  });

  it("⛔ e `use_draft` FALSO viaja falso — a intenção chega fiel ao corpo", async () => {
    // O caso negativo é o que importa: com `use_draft` preso em `true`, quem
    // NÃO marcou a caixa recebe a resposta do rascunho com o selo dizendo
    // "Versão no ar". É o defeito da SPEC §2 na aba que existe para dizer qual
    // texto governou — e o 404 do backend não o alcança, porque a metade da
    // frente é esta: o que a tela pediu.
    stream.mockResolvedValue(undefined);
    const onEvent = vi.fn();

    await testAssistant("Quantos desvios?", false, { onEvent });

    expect(stream).toHaveBeenCalledWith(
      "/assistente/configuracao/testar",
      { question: "Quantos desvios?", use_draft: false },
      { onEvent },
    );
  });
});

describe("os seis `detail` da publicação viram frase", () => {
  it.each([
    ["not_admin", "Sem permissão para publicar."],
    ["draft_not_found", "Salve o rascunho antes de publicar."],
    ["draft_empty", "O rascunho está vazio."],
    [
      "platform_layer_missing",
      "A camada da plataforma não está publicada — fale com o suporte.",
    ],
    [
      "draft_unchanged",
      "O texto já está no ar: nada mudou desde a última publicação.",
    ],
    [
      "draft_moved",
      "O rascunho mudou desde que você abriu esta tela — recarregue antes de " +
        "publicar. Nada foi alterado.",
    ],
  ])("%s → %s", (detail, phrase) => {
    expect(publishFailureMessage(new ApiError(409, detail))).toBe(phrase);
  });

  it("qualquer outro `detail` chega como veio; sem `detail`, a frase genérica", () => {
    expect(
      publishFailureMessage(new ApiError(429, "Aguarde 30 segundos.")),
    ).toBe("Aguarde 30 segundos.");
    expect(publishFailureMessage(new ApiError(504, null))).toBe(
      "Não consegui publicar. Nada foi alterado.",
    );
    expect(publishFailureMessage(new TypeError("fetch failed"))).toBe(
      "Não consegui publicar. Nada foi alterado.",
    );
  });
});

describe("domainLabel", () => {
  it.each([
    ["compensation", "Remuneração"],
    ["pii", "Dados pessoais"],
    ["health", "Saúde"],
    ["disciplinary", "Disciplinar"],
    ["banking", "Bancário"],
    [null, "—"],
  ])("%s → %s", (domain, label) => {
    expect(domainLabel(domain)).toBe(label);
  });

  it("um domínio que a tela não conhece aparece como veio, não como traço", () => {
    expect(domainLabel("zz_novo")).toBe("zz_novo");
  });
});
