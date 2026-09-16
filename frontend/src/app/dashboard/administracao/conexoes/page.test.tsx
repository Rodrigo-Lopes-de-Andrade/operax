import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ConexoesPage from "@/app/dashboard/administracao/conexoes/page";
import type { Channel } from "@/lib/canais/labels";
import type {
  ChannelCapabilities,
  ConnectionsScreen,
  CredentialField,
  CredentialStatus,
  ProviderForm,
} from "@/lib/canais/queries";
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
const loadConnections = vi.fn();
const loadCredential = vi.fn();
const loadProviderForms = vi.fn();

vi.mock("@/lib/identity", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/identity")>("@/lib/identity");

  // `isAdmin` fica o real: é a porta sob teste.
  return { ...actual, loadIdentity: () => loadIdentity() };
});

vi.mock("@/lib/canais/queries", () => ({
  loadConnections: () => loadConnections(),
  loadCredential: (channel: Channel) => loadCredential(channel),
  loadProviderForms: () => loadProviderForms(),
}));

function identidade(role: string): Identity {
  return {
    user_id: "11111111-1111-4111-8111-111111111111",
    email: `${role}@fastpark.dev`,
    tenant_id: "22222222-2222-4222-8222-222222222222",
    role,
  };
}

const OFFICIAL: ChannelCapabilities = {
  official: true,
  requires_templates: true,
  ban_risk: false,
  requires_recipient_opt_in: false,
};

const UNOFFICIAL: ChannelCapabilities = {
  official: false,
  requires_templates: false,
  ban_risk: true,
  requires_recipient_opt_in: false,
};

const OPT_IN: ChannelCapabilities = {
  official: true,
  requires_templates: false,
  ban_risk: false,
  requires_recipient_opt_in: true,
};

/** O estado da produção no primeiro dia: nenhum canal. */
const SEM_CANAL: ConnectionsScreen = { whatsapp: null, telegram: null };

const BLOQUEADO: ConnectionsScreen = {
  whatsapp: {
    provider: "meta_cloud",
    capabilities: OFFICIAL,
    templates_total: 1,
    templates_approved: 0,
    rules_blocked: 1,
    ready: false,
    blocked: [
      {
        rule_name: "Desvio individual",
        template_code: "deviation_individual",
        meta_status: "pending",
      },
    ],
  },
  telegram: {
    provider: "telegram",
    capabilities: OPT_IN,
    bot_username: "@zz_bot_inventado",
    webhook_configured: true,
    webhook_url:
      "https://api.zz-inventada.test/webhooks/telegram/zz-token-inventado-0123456789abcdef",
    webhook_path_token: "zz-token-inventado-0123456789abcdef",
    health_status: "connected",
    health_checked_at: "2026-09-15T13:05:00Z",
    health_changed_at: "2026-09-14T09:00:00Z",
    health_detail: null,
    ready: true,
  },
};

const NOT_CONFIGURED: Record<Channel, CredentialStatus> = {
  whatsapp: {
    channel: "whatsapp",
    configured: false,
    provider: null,
    updated_at: null,
    public_identity: null,
  },
  telegram: {
    channel: "telegram",
    configured: false,
    provider: null,
    updated_at: null,
    public_identity: null,
  },
};

const TELEGRAM_CONFIGURED: CredentialStatus = {
  channel: "telegram",
  configured: true,
  provider: "telegram",
  updated_at: "2026-09-15T13:05:00Z",
  public_identity: "@zz_bot_inventado",
};

/**
 * O mesmo nome de campo nos dois canais, **de propósito**: no backend o campo
 * do bot se chama `bot_token`, então o par que colide não existe hoje — este
 * fixture é o que prende que dois formulários na mesma página nunca partilhem
 * `id`, seja qual for o nome que um provedor futuro escolher.
 */
const TOKEN: CredentialField = {
  name: "token",
  label: "Token",
  pattern: "[A-Za-z0-9:_\\-]+",
  autocomplete: "one-time-code",
  inputmode: "text",
  secret: true,
  placeholder: "…",
  hint: "isto não parece um token",
};

const FORMS: ProviderForm[] = [
  {
    provider: "meta_cloud",
    channel: "whatsapp",
    capabilities: OFFICIAL,
    fields: [
      {
        name: "phone_number_id",
        label: "ID do número de telefone",
        pattern: "[0-9]{5,32}",
        autocomplete: "off",
        inputmode: "numeric",
        secret: false,
        placeholder: "123456789012345",
        hint: "isto não parece um ID de número: a Meta usa só dígitos",
      },
      { ...TOKEN, label: "Token de acesso permanente" },
    ],
  },
  {
    provider: "z_api",
    channel: "whatsapp",
    capabilities: UNOFFICIAL,
    fields: [{ ...TOKEN, label: "Token da instância" }],
  },
  {
    provider: "uazapi",
    channel: "whatsapp",
    capabilities: UNOFFICIAL,
    fields: [{ ...TOKEN, label: "Token da instância" }],
  },
  {
    provider: "telegram",
    channel: "telegram",
    capabilities: OPT_IN,
    fields: [{ ...TOKEN, label: "Token do bot" }],
  },
];

type Credentials = Partial<Record<Channel, CredentialStatus | null>>;

async function abrir(
  role: string,
  screenData: ConnectionsScreen | null,
  credentials: Credentials = NOT_CONFIGURED,
  forms: ProviderForm[] | null = FORMS,
) {
  loadIdentity.mockResolvedValue(identidade(role));
  loadConnections.mockResolvedValue(screenData);
  loadCredential.mockImplementation(async (channel: Channel) =>
    channel in credentials ? credentials[channel] : null,
  );
  loadProviderForms.mockResolvedValue(forms);

  return render(await ConexoesPage());
}

function formularios() {
  return screen.queryAllByRole("button", { name: "Validar e gravar" });
}

/** A região do formulário de um canal, pelo título. */
function credencial(titulo: string) {
  return within(screen.getByRole("region", { name: titulo }));
}

beforeEach(() => {
  notFound.mockClear();
  loadIdentity.mockReset();
  loadConnections.mockReset();
  loadCredential.mockReset();
  loadProviderForms.mockReset();
});

describe("a porta da página é `isAdmin`, mais estreita que a rota de propósito", () => {
  it("⛔ `unit_supervisor` recebe 404, e nenhuma das quatro leituras é chamada", async () => {
    loadIdentity.mockResolvedValue(identidade("unit_supervisor"));

    await expect(ConexoesPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalled();
    expect(loadConnections).not.toHaveBeenCalled();
    expect(loadCredential).not.toHaveBeenCalled();
    expect(loadProviderForms).not.toHaveBeenCalled();
  });

  it("⛔ `executive` também recebe 404 — lê a área de RH e não configura canal", async () => {
    // Ele está em `HR_ROLES` e não em `ADMIN_ROLES`. Sem este caso, trocar
    // `isAdmin` por `reachesHr` passaria verde: o supervisor continuaria fora.
    loadIdentity.mockResolvedValue(identidade("executive"));

    await expect(ConexoesPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadConnections).not.toHaveBeenCalled();
    expect(loadCredential).not.toHaveBeenCalled();
  });

  it("sem vínculo com o tenant não há tela", async () => {
    loadIdentity.mockResolvedValue(null);

    await expect(ConexoesPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadConnections).not.toHaveBeenCalled();
  });

  it("✅ `owner` entra e vê os dois canais, o que está preso, e os dois formulários", async () => {
    await abrir("owner", BLOQUEADO);

    expect(notFound).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", { level: 1, name: "Conexões" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "O que está preso" }),
    ).toBeVisible();
    expect(screen.getByText("deviation_individual")).toBeVisible();
    expect(screen.getByText("@zz_bot_inventado")).toBeVisible();
    // O admin vê a ação do bot.
    expect(screen.getByRole("button", { name: "Desconectar" })).toBeVisible();

    expect(formularios()).toHaveLength(2);
  });

  it("✅ `owner` sem canal vê os dois vazios — a tela do primeiro dia", async () => {
    await abrir("owner", SEM_CANAL);

    expect(notFound).not.toHaveBeenCalled();
    expect(screen.getByText("Nenhum provedor de WhatsApp ativo")).toBeVisible();
    expect(screen.getByText("Nenhum bot de Telegram ativo")).toBeVisible();
    expect(screen.queryByText("As conexões não puderam ser lidas")).toBeNull();
  });
});

describe("as quatro leituras — em paralelo, e `null` em qualquer uma não derruba", () => {
  it("⛔ `loadCredential` é chamada uma vez por canal, com o canal", async () => {
    await abrir("owner", SEM_CANAL);

    expect(loadCredential).toHaveBeenCalledTimes(2);
    expect(loadCredential.mock.calls.map(([channel]) => channel)).toEqual([
      "whatsapp",
      "telegram",
    ]);
    expect(loadConnections).toHaveBeenCalledTimes(1);
    expect(loadProviderForms).toHaveBeenCalledTimes(1);
  });

  it("null nas conexões (sessão, 401, 403) é 'não pôde ser lido' — outra frase, e não 'sem canal'", async () => {
    await abrir("owner", null, {}, null);

    expect(notFound).not.toHaveBeenCalled();
    expect(screen.getByText("As conexões não puderam ser lidas")).toBeVisible();
    expect(screen.queryByText("Nenhum provedor de WhatsApp ativo")).toBeNull();
    expect(screen.queryByText("Nenhum bot de Telegram ativo")).toBeNull();
    // Sem sessão de API não há formulário — e não há estado vazio novo.
    expect(formularios()).toHaveLength(0);
  });

  it("conexões lidas mas sem os formulários: a tela fica, formulário nenhum", async () => {
    await abrir("owner", SEM_CANAL, NOT_CONFIGURED, null);

    expect(screen.getByText("Nenhum provedor de WhatsApp ativo")).toBeVisible();
    expect(formularios()).toHaveLength(0);
    expect(screen.queryByRole("region", { name: /Credencial do/ })).toBeNull();
  });

  it("⛔ falta só a credencial do Telegram: o formulário de WhatsApp fica, o do Telegram não", async () => {
    // A corrida de milissegundos em que a sessão vence entre uma chamada e a
    // outra. A página não quebra e não inventa: mostra o que veio.
    await abrir("owner", SEM_CANAL, {
      whatsapp: NOT_CONFIGURED.whatsapp,
      telegram: null,
    });

    expect(formularios()).toHaveLength(1);
    expect(
      screen.getByRole("region", { name: "Credencial do WhatsApp" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("region", { name: "Credencial do Telegram" }),
    ).toBeNull();
  });

  it("… e o par: falta só a do WhatsApp", async () => {
    await abrir("owner", SEM_CANAL, {
      whatsapp: null,
      telegram: NOT_CONFIGURED.telegram,
    });

    expect(formularios()).toHaveLength(1);
    expect(
      screen.queryByRole("region", { name: "Credencial do WhatsApp" }),
    ).toBeNull();
    expect(
      screen.getByRole("region", { name: "Credencial do Telegram" }),
    ).toBeVisible();
  });
});

describe("critério 5 — dois formulários, cada um só com os provedores do seu canal", () => {
  it("⛔ o de WhatsApp tem três provedores e o de Telegram um — pelo `channel`", async () => {
    await abrir("owner", SEM_CANAL);

    const whatsapp = credencial("Credencial do WhatsApp");
    const telegram = credencial("Credencial do Telegram");

    expect(
      whatsapp.getAllByRole("option").map((option) => option.textContent),
    ).toEqual(["WhatsApp Cloud API (Meta)", "Z-API", "UAZAPI"]);
    expect(
      telegram.getAllByRole("option").map((option) => option.textContent),
    ).toEqual(["Telegram"]);
  });

  it("⛔ … e é o `channel` que separa, não o nome: um provedor de WhatsApp declarado como Telegram vai para o Telegram", async () => {
    // Um filtro por nome (`provider === "telegram"`) passaria no caso acima e
    // cai aqui.
    const trocado = FORMS.map((form) =>
      form.provider === "z_api"
        ? { ...form, channel: "telegram" as const }
        : form,
    );
    await abrir("owner", SEM_CANAL, NOT_CONFIGURED, trocado);

    expect(
      credencial("Credencial do WhatsApp")
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["WhatsApp Cloud API (Meta)", "UAZAPI"]);
    // Na ordem da API, como o filtro a preserva.
    expect(
      credencial("Credencial do Telegram")
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Z-API", "Telegram"]);
  });

  it("cada formulário mostra o estado da credencial do seu canal", async () => {
    await abrir("owner", SEM_CANAL, {
      whatsapp: NOT_CONFIGURED.whatsapp,
      telegram: TELEGRAM_CONFIGURED,
    });

    expect(
      credencial("Credencial do WhatsApp").getByText("Não configurada"),
    ).toBeVisible();
    expect(
      credencial("Credencial do Telegram").getByText("Configurada"),
    ).toBeVisible();
    expect(
      credencial("Credencial do Telegram").getByText("@zz_bot_inventado"),
    ).toBeVisible();
  });

  it("os títulos dos formulários são os dos canais, na ordem WhatsApp → Telegram", async () => {
    await abrir("owner", SEM_CANAL);

    const titulos = screen
      .getAllByRole("region", { name: /Credencial do/ })
      .map((region) => region.getAttribute("aria-labelledby"))
      .map((id) => (id ? document.getElementById(id)?.textContent : null));

    expect(titulos).toEqual([
      "Credencial do WhatsApp",
      "Credencial do Telegram",
    ]);
  });

  it("⛔ dois formulários com o mesmo nome de campo não partilham `id`: cada rótulo aponta para o seu input", async () => {
    // Com `id` derivado só do nome do campo, o segundo rótulo apontaria para o
    // primeiro input — clicar em "Token do bot" focaria o token da Meta.
    await abrir("owner", SEM_CANAL);

    const meta = screen.getByLabelText("Token de acesso permanente");
    const bot = screen.getByLabelText("Token do bot");

    expect(meta).not.toBe(bot);
    expect(meta.id).not.toBe(bot.id);
    expect(
      credencial("Credencial do Telegram").getByLabelText("Token do bot"),
    ).toBe(bot);

    const ids = Array.from(document.querySelectorAll("input")).map(
      (input) => input.id,
    );
    expect(new Set(ids).size).toBe(ids.length);
  });
});
