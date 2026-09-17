import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Connections, Requirements } from "@/components/canais/connections";
import { TEMPLATES_PATH } from "@/lib/canais/url";
import type {
  BlockedAlertRule,
  ChannelCapabilities,
  ConnectionsScreen,
  DeliveryByChannelRow,
  TelegramAdhesionRow,
  TelegramChannel,
  WhatsAppChannel,
} from "@/lib/canais/queries";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

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

/** A terceira família (SPEC §1.1): nem template nem banimento, só destinatário. */
const OPT_IN: ChannelCapabilities = {
  official: true,
  requires_templates: false,
  ban_risk: false,
  requires_recipient_opt_in: true,
};

/** Nenhuma das três — a matriz não emite, e a tela precisa dizer algo. */
const NONE: ChannelCapabilities = {
  official: false,
  requires_templates: false,
  ban_risk: false,
  requires_recipient_opt_in: false,
};

/** O caso 1 do contrato — o gate do C1. */
const PENDING: BlockedAlertRule = {
  rule_name: "Desvio individual",
  template_code: "deviation_individual",
  meta_status: "pending",
};

/** O caso 2: código que não existe ou está inativo — a resposta não distingue. */
const MISSING: BlockedAlertRule = {
  rule_name: "Resumo da unidade",
  template_code: "unit_summary",
  meta_status: null,
};

/** O caso 3: regra de WhatsApp sem template nenhum. */
const NO_TEMPLATE: BlockedAlertRule = {
  rule_name: "Sem batida",
  template_code: null,
  meta_status: null,
};

function official(overrides: Partial<WhatsAppChannel> = {}): WhatsAppChannel {
  return {
    provider: "meta_cloud",
    capabilities: OFFICIAL,
    templates_total: 2,
    templates_approved: 1,
    rules_blocked: 1,
    ready: false,
    blocked: [PENDING],
    ...overrides,
  };
}

function unofficial(overrides: Partial<WhatsAppChannel> = {}): WhatsAppChannel {
  return {
    provider: "z_api",
    capabilities: UNOFFICIAL,
    templates_total: 0,
    templates_approved: 0,
    rules_blocked: 0,
    ready: true,
    blocked: [],
    ...overrides,
  };
}

// Um nome de bot e uma cauda que nenhum bot real tem: a linha só aparece se
// vier da prop — um cartão escrito à mão não teria como acertá-los.
const BOT = "@zz_bot_inventado";
const TOKEN = "zz-token-inventado-0123456789abcdef";
// O host não é o `NEXT_PUBLIC_API_URL` de teste: o endereço vem da prop.
const WEBHOOK_URL = `https://api.zz-inventada.test/webhooks/telegram/${TOKEN}`;

function telegram(overrides: Partial<TelegramChannel> = {}): TelegramChannel {
  return {
    provider: "telegram",
    capabilities: OPT_IN,
    bot_username: BOT,
    webhook_configured: true,
    webhook_url: WEBHOOK_URL,
    webhook_path_token: TOKEN,
    health_status: "connected",
    // 13:05 UTC é 10:05 em São Paulo; 09:00 UTC é 06:00 — as datas saem no
    // fuso do tenant, não no da máquina.
    health_checked_at: "2026-09-15T13:05:00Z",
    health_changed_at: "2026-09-14T09:00:00Z",
    health_detail: null,
    ready: true,
    ...overrides,
  };
}

function tela(overrides: Partial<ConnectionsScreen> = {}): ConnectionsScreen {
  return { whatsapp: official(), telegram: telegram(), ...overrides };
}

/** O estado da produção hoje: nenhum canal. */
const EMPTY: ConnectionsScreen = { whatsapp: null, telegram: null };

/** Unidades inventadas, contagens — e nada que nomeie uma pessoa. */
const ADHESION: TelegramAdhesionRow[] = [
  {
    unit_id: "11111111-1111-4111-8111-111111111111",
    unit_name: "Unidade Zz Alfa",
    joined: 3,
    pending: 0,
    revoked: 1,
  },
  {
    unit_id: "22222222-2222-4222-8222-222222222222",
    unit_name: "Unidade Zz Beta",
    joined: 0,
    pending: 7,
    revoked: 0,
  },
];

/** Uma semana com os dois canais — contagens, e nada que nomeie uma pessoa. */
const DELIVERIES: DeliveryByChannelRow[] = [
  {
    week_start: "2026-08-31",
    channel: "whatsapp",
    provider: "meta_cloud",
    sent: 40,
    failed: 2,
  },
  {
    week_start: "2026-08-31",
    channel: "telegram",
    provider: "telegram",
    sent: 10,
    failed: 0,
  },
];

const TEMPLATE_PHRASE = /Exige template aprovado pela Meta/;
const BAN_PHRASE = /volume alto pode levar a banimento/;
const OPT_IN_PHRASE = /Só alcança quem aderiu pelo convite/;
const NONE_PHRASE = /Sem restrição declarada para este canal/;

const WHATSAPP_EMPTY = "Nenhum provedor de WhatsApp ativo";
const TELEGRAM_EMPTY = "Nenhum bot de Telegram ativo";

function regiao(name: string) {
  return within(screen.getByRole("region", { name }));
}

function whatsapp() {
  return regiao("WhatsApp");
}

function telegramRegiao() {
  return regiao("Telegram");
}

function preso() {
  return screen.queryByRole("heading", { name: "O que está preso" });
}

/** O bloco 3 inteiro — e só ele: o bloco 1 também é uma lista. */
function bloco3() {
  const bloco = preso()?.closest("section");

  if (!bloco) {
    throw new Error("o bloco 3 não está na tela");
  }

  return within(bloco);
}

function linhas() {
  return bloco3().getAllByRole("listitem");
}

function renderTela(
  screenData: ConnectionsScreen,
  canWrite = true,
  adhesion: TelegramAdhesionRow[] | null = ADHESION,
  deliveries: DeliveryByChannelRow[] | null = DELIVERIES,
): ReturnType<typeof render> {
  return render(
    <Connections
      screen={screenData}
      adhesion={adhesion}
      deliveries={deliveries}
      canWrite={canWrite}
    />,
  );
}

function entregas() {
  return screen.queryByRole("table", { name: "Entregas por canal e semana" });
}

function adesao() {
  return screen.queryByRole("table", {
    name: "Adesão ao Telegram por unidade",
  });
}

describe("critério 1 — os dois cartões existem sempre", () => {
  it("⛔ os dois nulos são dois vazios, cada um com a sua frase, e nenhum erro", () => {
    // Produção não tem canal nenhum: esta é a tela principal no primeiro dia.
    renderTela(EMPTY);

    // Contados por região, não por texto: um cartão que sumisse com o nulo
    // passaria em "sem erro" e cairia aqui.
    expect(screen.getAllByRole("region")).toHaveLength(2);
    expect(whatsapp().getByText(WHATSAPP_EMPTY)).toBeVisible();
    expect(telegramRegiao().getByText(TELEGRAM_EMPTY)).toBeVisible();
    expect(screen.queryByText(/Pronto|Bloqueado/)).toBeNull();
    expect(screen.queryByText(/Templates aprovados/)).toBeNull();
    expect(preso()).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("⛔ WhatsApp preenchido e Telegram nulo: o cartão do Telegram continua lá, vazio", () => {
    // SPEC §2.1: os dois coexistem. Esconder o nulo sugere que um substitui o
    // outro.
    renderTela(tela({ telegram: null }));

    expect(screen.getAllByRole("region")).toHaveLength(2);
    expect(
      whatsapp().getByRole("heading", { name: "WhatsApp Cloud API (Meta)" }),
    ).toBeVisible();
    expect(whatsapp().queryByText(WHATSAPP_EMPTY)).toBeNull();
    expect(telegramRegiao().getByText(TELEGRAM_EMPTY)).toBeVisible();
    expect(telegramRegiao().queryByText(BOT)).toBeNull();
  });

  it("⛔ … e o par: Telegram preenchido e WhatsApp nulo", () => {
    renderTela(tela({ whatsapp: null }));

    expect(screen.getAllByRole("region")).toHaveLength(2);
    expect(whatsapp().getByText(WHATSAPP_EMPTY)).toBeVisible();
    expect(whatsapp().queryByText(/Templates aprovados/)).toBeNull();
    expect(telegramRegiao().getByText(BOT)).toBeVisible();
    expect(telegramRegiao().queryByText(TELEGRAM_EMPTY)).toBeNull();
  });

  it("✅ os dois preenchidos: cada bloco na sua região, e os dados são os da prop", () => {
    renderTela(tela());

    expect(screen.queryByText(WHATSAPP_EMPTY)).toBeNull();
    expect(screen.queryByText(TELEGRAM_EMPTY)).toBeNull();
    expect(
      whatsapp().getByRole("heading", { name: "WhatsApp Cloud API (Meta)" }),
    ).toBeVisible();
    expect(whatsapp().getByText("Canal oficial")).toBeVisible();
    expect(telegramRegiao().getByText(BOT)).toBeVisible();
    // O bloco 3 é do WhatsApp; o Telegram não tem "o que está preso".
    expect(
      whatsapp().getByRole("heading", { name: "O que está preso" }),
    ).toBeVisible();
    expect(
      telegramRegiao().queryByRole("heading", { name: "O que está preso" }),
    ).toBeNull();
  });

  it("a ordem é WhatsApp primeiro, Telegram depois — o que já existe vem antes", () => {
    renderTela(EMPTY);

    const nomes = screen
      .getAllByRole("region")
      .map((region) => region.getAttribute("aria-labelledby"))
      .map((id) => (id ? document.getElementById(id)?.textContent : null));

    expect(nomes).toEqual(["WhatsApp", "Telegram"]);
  });
});

describe("bloco 1 do WhatsApp — o canal", () => {
  it("`requires_templates` → a frase de template, e não a de banimento", () => {
    renderTela(tela({ telegram: null }));

    expect(screen.getByText(TEMPLATE_PHRASE)).toBeVisible();
    expect(screen.queryByText(BAN_PHRASE)).toBeNull();
  });

  it("`ban_risk` → a frase de banimento, e não a de template", () => {
    renderTela(tela({ whatsapp: unofficial(), telegram: null }));

    expect(screen.getByText(BAN_PHRASE)).toBeVisible();
    expect(screen.queryByText(TEMPLATE_PHRASE)).toBeNull();
    expect(screen.getByText("Canal não oficial")).toBeVisible();
  });

  it("⛔ a frase vem das flags, não do nome: flags invertidas em relação ao provedor", () => {
    // SPEC §1: feature nenhuma pergunta *com quem* falamos. Um
    // `if provider === "meta_cloud"` passaria nos dois casos acima e cairia
    // aqui — o nome diz oficial e as flags dizem banimento.
    renderTela(
      tela({
        whatsapp: official({
          provider: "meta_cloud",
          capabilities: UNOFFICIAL,
        }),
        telegram: null,
      }),
    );

    expect(screen.getByText(BAN_PHRASE)).toBeVisible();
    expect(screen.queryByText(TEMPLATE_PHRASE)).toBeNull();
  });

  it("⛔ … e o par: nome não oficial com flags do oficial mostra template", () => {
    renderTela(
      tela({
        whatsapp: unofficial({ provider: "z_api", capabilities: OFFICIAL }),
        telegram: null,
      }),
    );

    expect(screen.getByText(TEMPLATE_PHRASE)).toBeVisible();
    expect(screen.queryByText(BAN_PHRASE)).toBeNull();
  });

  it("⛔ canal não oficial não menciona a Meta em lugar nenhum", () => {
    const { container } = renderTela(
      tela({ whatsapp: unofficial(), telegram: null }),
    );

    expect(container.textContent).not.toMatch(/\bMeta\b/);
    // ✅ O positivo: o mesmo teste enxerga a Meta quando ela está lá.
    const { container: oficial } = renderTela(tela({ telegram: null }));
    expect(oficial.textContent).toMatch(/\bMeta\b/);
  });
});

describe("bloco 2 do WhatsApp — a saúde", () => {
  it("⛔ `ready: true` diz Pronto, e o bloco 3 está ausente do DOM", () => {
    renderTela(
      tela({
        whatsapp: official({
          ready: true,
          rules_blocked: 0,
          blocked: [],
          templates_approved: 2,
        }),
        telegram: null,
      }),
    );

    expect(screen.getByText("Pronto")).toBeVisible();
    expect(screen.queryByText("Bloqueado")).toBeNull();
    expect(preso()).toBeNull();
    // "Pronto e nada mais": sem contagem para ler quando não há o que consertar.
    expect(screen.queryByText("Regras bloqueadas")).toBeNull();
    expect(screen.queryByText("Templates aprovados")).toBeNull();
  });

  it("`ready: false` diz Bloqueado, com os templates aprovados de total e as regras", () => {
    renderTela(tela({ telegram: null }));

    expect(screen.getByText("Bloqueado")).toBeVisible();
    expect(screen.queryByText("Pronto")).toBeNull();
    expect(
      screen.getByText("Templates aprovados").nextElementSibling,
    ).toHaveTextContent("1 de 2");
    expect(
      screen.getByText("Regras bloqueadas").nextElementSibling,
    ).toHaveTextContent("1");
  });

  it("⛔ a contagem é a da API, não o tamanho da lista — e nenhuma das duas some", () => {
    // `rules_blocked` e `blocked.length` são duas leituras do mesmo fato. O
    // backend já loga a diferença; a tela mostra as duas em vez de consertar.
    renderTela(
      tela({
        whatsapp: official({ rules_blocked: 3, blocked: [PENDING] }),
        telegram: null,
      }),
    );

    expect(
      screen.getByText("Regras bloqueadas").nextElementSibling,
    ).toHaveTextContent("3");
    expect(linhas()).toHaveLength(1);
    expect(
      screen.getByText(/A contagem da API diz 3 regras bloqueadas/),
    ).toBeVisible();
    expect(screen.getByText(/a lista traz 1\./)).toBeVisible();
  });

  it("✅ quando as duas leituras concordam, não há aviso de divergência", () => {
    renderTela(tela({ telegram: null }));

    expect(screen.queryByText(/A contagem da API diz/)).toBeNull();
  });
});

describe("bloco 3 do WhatsApp — o que está preso", () => {
  it("⛔ GATE do C1: template pendente numa regra ligada mostra a regra, o template e o estado", () => {
    renderTela(tela({ telegram: null }));

    const [linha] = linhas();
    expect(linha).toHaveTextContent(
      "a regra Desvio individual aponta para o template deviation_individual, que está pendente na Meta.",
    );
    expect(within(linha).getByText("Desvio individual")).toBeVisible();
    expect(within(linha).getByText("deviation_individual")).toBeVisible();
    expect(within(linha).getByText("pendente")).toBeVisible();
  });

  it("cada regra presa leva à ação que a solta: o link para a aba de templates", () => {
    renderTela(tela({ telegram: null }));

    const [linha] = linhas();
    expect(
      within(linha).getByRole("link", { name: "ver templates" }),
    ).toHaveAttribute("href", TEMPLATES_PATH);
  });

  it("estado que ninguém traduziu aparece cru, não some", () => {
    renderTela(
      tela({
        whatsapp: official({
          blocked: [{ ...PENDING, meta_status: "disabled" }],
        }),
        telegram: null,
      }),
    );

    expect(linhas()[0]).toHaveTextContent("que está disabled na Meta");
  });

  it("⛔ caso 2: `meta_status` nulo é 'não existe ou está inativo' — e NÃO a frase do caso 1", () => {
    renderTela(
      tela({ whatsapp: official({ blocked: [MISSING] }), telegram: null }),
    );

    const [linha] = linhas();
    expect(linha).toHaveTextContent(
      "a regra Resumo da unidade aponta para o template unit_summary, que não existe ou está inativo neste cliente.",
    );
    expect(linha).not.toHaveTextContent(/na Meta/);
  });

  it("⛔ caso 3: `template_code` nulo é 'não aponta para template nenhum' — e NÃO a frase do caso 2", () => {
    renderTela(
      tela({ whatsapp: official({ blocked: [NO_TEMPLATE] }), telegram: null }),
    );

    const [linha] = linhas();
    expect(linha).toHaveTextContent(
      "a regra Sem batida é de WhatsApp e não aponta para template nenhum.",
    );
    expect(linha).not.toHaveTextContent(/não existe ou está inativo/);
    expect(linha).not.toHaveTextContent(/na Meta/);
  });

  it("uma linha por item, na ordem em que vieram — inclusive a mesma regra duas vezes", () => {
    renderTela(
      tela({
        whatsapp: official({
          rules_blocked: 4,
          blocked: [PENDING, PENDING, MISSING, NO_TEMPLATE],
        }),
        telegram: null,
      }),
    );

    const todas = linhas();
    expect(todas).toHaveLength(4);
    expect(todas[0]).toHaveTextContent(/pendente na Meta/);
    expect(todas[1]).toHaveTextContent(/pendente na Meta/);
    expect(todas[2]).toHaveTextContent(/não existe ou está inativo/);
    expect(todas[3]).toHaveTextContent(/não aponta para template nenhum/);
  });

  it("⛔ sem lista e sem `ready`, o canal exige template aprovado e nenhum está", () => {
    renderTela(
      tela({
        whatsapp: official({
          templates_total: 2,
          templates_approved: 0,
          rules_blocked: 0,
          blocked: [],
        }),
        telegram: null,
      }),
    );

    expect(preso()).toBeVisible();
    expect(
      screen.getByText(
        /exige template aprovado pela Meta, e nenhum está aprovado \(0 de 2\)/,
      ),
    ).toBeVisible();
    expect(bloco3().queryByRole("listitem")).toBeNull();
  });

  it("contagem sem lista, com template aprovado, não inventa a causa", () => {
    renderTela(
      tela({
        whatsapp: official({
          templates_approved: 1,
          rules_blocked: 2,
          blocked: [],
        }),
        telegram: null,
      }),
    );

    expect(
      screen.getByText(
        /marcou o canal como bloqueado e a lista de regras veio vazia/,
      ),
    ).toBeVisible();
    expect(screen.queryByText(/nenhum está aprovado/)).toBeNull();
    expect(
      screen.getByText(/A contagem da API diz 2 regras bloqueadas/),
    ).toBeVisible();
  });
});

describe("critério 2 — o cartão do Telegram", () => {
  it("o bot como título do cartão, o oficial pela flag, e a frase da terceira família", () => {
    renderTela(tela({ whatsapp: null }));

    const t = telegramRegiao();
    expect(t.getByRole("heading", { name: BOT })).toBeVisible();
    expect(t.getByText("Canal oficial")).toBeVisible();
    expect(t.getByText(OPT_IN_PHRASE)).toBeVisible();
    expect(t.queryByText(TEMPLATE_PHRASE)).toBeNull();
    expect(t.queryByText(BAN_PHRASE)).toBeNull();
    expect(t.queryByText(/não informou o nome de usuário/)).toBeNull();
  });

  it("⛔ o badge oficial do bot é da flag: `official: false` diz 'não oficial'", () => {
    renderTela(
      tela({
        whatsapp: null,
        telegram: telegram({ capabilities: UNOFFICIAL }),
      }),
    );

    const t = telegramRegiao();
    expect(t.getByText("Canal não oficial")).toBeVisible();
    expect(t.queryByText("Canal oficial")).toBeNull();
  });

  it("sem `bot_username`, o título cai no rótulo do provedor e a tela diz que o Telegram não informou", () => {
    renderTela(
      tela({ whatsapp: null, telegram: telegram({ bot_username: null }) }),
    );

    const t = telegramRegiao();
    // Dois títulos "Telegram": o da região e o do cartão, que caiu no rótulo.
    expect(t.getAllByRole("heading", { name: "Telegram" })).toHaveLength(2);
    expect(t.getByText(/não informou o nome de usuário do bot/)).toBeVisible();
    expect(t.queryByText(/^@/)).toBeNull();
  });

  // A classe de texto de cada tom do `<Badge>` — `neutral` é o cinza do texto
  // apagado, não uma cor própria.
  const TONE_CLASS = {
    good: "text-good",
    bad: "text-bad",
    neutral: "text-ink-muted",
  } as const;

  it.each([
    ["connected", "Conectado", "good"],
    ["disconnected", "Desconectado", "bad"],
    ["unknown", "Sem resposta", "neutral"],
  ] as const)(
    "⛔ `health_status: %s` → badge '%s' com tom %s",
    (status, texto, tom) => {
      renderTela(
        tela({ whatsapp: null, telegram: telegram({ health_status: status }) }),
      );

      const badge = screen.getByText(texto);
      expect(badge).toBeVisible();
      expect(badge.className).toContain(TONE_CLASS[tom]);
      // E só esse: os outros três rótulos não estão na tela.
      for (const outro of [
        "Conectado",
        "Desconectado",
        "Sem resposta",
        "Nunca medido",
      ].filter((rotulo) => rotulo !== texto)) {
        expect(screen.queryByText(outro)).toBeNull();
      }
    },
  );

  it("⛔ `health_status: null` é 'Nunca medido', neutro — e não 'Sem resposta'", () => {
    // Nunca medido e medido-sem-resposta são fatos diferentes: um é o vigia
    // que não rodou, o outro é o Telegram que não respondeu.
    renderTela(
      tela({
        whatsapp: null,
        telegram: telegram({
          health_status: null,
          health_checked_at: null,
          health_changed_at: null,
          ready: false,
        }),
      }),
    );

    const badge = screen.getByText("Nunca medido");
    expect(badge).toBeVisible();
    expect(badge.className).toContain("text-ink-muted");
    expect(screen.queryByText("Sem resposta")).toBeNull();
    expect(screen.queryByText(/desde /)).toBeNull();
    expect(screen.queryByText(/conferido em/)).toBeNull();
  });

  it("⛔ as datas saem no fuso do tenant: 'desde' de `health_changed_at`, 'conferido em' de `health_checked_at`", () => {
    renderTela(tela({ whatsapp: null }));

    // 09:00 UTC → 06:00; 13:05 UTC → 10:05. Cada uma do seu campo.
    expect(screen.getByText("desde 14/09/2026 às 06:00")).toBeVisible();
    expect(screen.getByText("conferido em 15/09/2026 às 10:05")).toBeVisible();
  });

  it("⛔ … e cada data é do seu campo, não trocada", () => {
    renderTela(
      tela({
        whatsapp: null,
        telegram: telegram({
          health_changed_at: "2026-09-01T12:00:00Z",
          health_checked_at: "2026-09-15T23:30:00Z",
        }),
      }),
    );

    expect(screen.getByText("desde 01/09/2026 às 09:00")).toBeVisible();
    expect(screen.getByText("conferido em 15/09/2026 às 20:30")).toBeVisible();
  });

  it("`health_detail` aparece quando vem, e não há parágrafo quando é nulo", () => {
    const detail = "getWebhookInfo devolveu last_error_message: zz-detalhe";
    const { unmount } = renderTela(
      tela({
        whatsapp: null,
        telegram: telegram({
          health_status: "disconnected",
          health_detail: detail,
        }),
      }),
    );

    expect(screen.getByText(detail)).toBeVisible();
    unmount();

    // Também quando conectado: o backend grava "webhook registrado" junto do
    // `connected`, e esconder o detalhe nesse estado apagaria essa frase.
    const { unmount: unmount2 } = renderTela(
      tela({
        whatsapp: null,
        telegram: telegram({
          health_status: "connected",
          health_detail: "zz-detalhe-conectado",
        }),
      }),
    );
    expect(screen.getByText("zz-detalhe-conectado")).toBeVisible();
    unmount2();

    renderTela(tela({ whatsapp: null }));
    expect(screen.queryByText(/zz-detalhe/)).toBeNull();
  });

  it("⛔ `ready` é 'Pronto'/'Não pronto', e vem da prop — não da saúde", () => {
    // `fn_channel_readiness` decide; a tela não recalcula. Saúde conectada com
    // `ready: false` mostra "Não pronto" mesmo assim.
    renderTela(
      tela({
        whatsapp: null,
        telegram: telegram({ health_status: "connected", ready: false }),
      }),
    );

    expect(screen.getByText("Não pronto")).toBeVisible();
    expect(screen.getByText("Bot não pronto")).toBeVisible();
    expect(screen.queryByText("Pronto")).toBeNull();
  });

  it("✅ `ready: true` → 'Pronto'", () => {
    renderTela(tela({ whatsapp: null }));

    expect(screen.getByText("Pronto")).toBeVisible();
    expect(screen.getByText("Bot pronto")).toBeVisible();
    expect(screen.queryByText("Não pronto")).toBeNull();
  });

  it("⛔ o endereço do webhook aparece truncado só quando configurado — nunca inteiro", () => {
    const { container } = renderTela(tela({ whatsapp: null }));

    const endereco = screen.getByText(/\/webhooks\/telegram\//);
    expect(endereco).toBeVisible();
    expect(endereco).toHaveTextContent(
      "https://api.zz-inventada.test/webhooks/telegram/zz-tok…abcdef",
    );
    expect(container.textContent).not.toContain(TOKEN);
    expect(
      screen.getByRole("button", { name: "Copiar endereço do webhook" }),
    ).toBeVisible();
  });

  it("⛔ … e não aparece quando `webhook_configured` é falso", () => {
    renderTela(
      tela({
        whatsapp: null,
        telegram: telegram({
          webhook_configured: false,
          webhook_url: null,
          webhook_path_token: null,
          health_status: null,
          ready: false,
        }),
      }),
    );

    expect(screen.queryByText(/\/webhooks\/telegram\//)).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Copiar endereço do webhook" }),
    ).toBeNull();
    expect(
      screen.getByText(/ainda não está registrado no Telegram/),
    ).toBeVisible();
  });

  it("⛔ nenhum botão de reconexão automática, em nenhum estado de saúde", () => {
    // SPEC §7: o vigia não religa, e a tela também não. Um bot desconectado
    // oferece "Desconectar" (que rotaciona) e depois "Conectar bot" — dois
    // cliques de uma pessoa olhando o motivo.
    for (const status of ["disconnected", "unknown", null] as const) {
      const { unmount } = renderTela(
        tela({
          whatsapp: null,
          telegram: telegram({ health_status: status, ready: false }),
        }),
      );

      expect(screen.queryByRole("button", { name: /reconectar/i })).toBeNull();
      expect(screen.queryByText(/reconectar|religar/i)).toBeNull();
      unmount();
    }
  });

  it("`canWrite: false` → sem botão de conectar nem de desconectar; o endereço fica", () => {
    renderTela(tela({ whatsapp: null }), false);

    expect(screen.queryByRole("button", { name: "Desconectar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Conectar bot" })).toBeNull();
    expect(screen.getByText(/\/webhooks\/telegram\//)).toBeVisible();
  });

  it("`canWrite: true` → o botão certo para o estado", () => {
    renderTela(tela({ whatsapp: null }));

    expect(screen.getByRole("button", { name: "Desconectar" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Conectar bot" })).toBeNull();
  });
});

describe("critério 3 — <Requirements>: as três famílias, pelas flags", () => {
  it("⛔ `requires_recipient_opt_in` → a terceira frase, e nenhuma das outras duas", () => {
    render(<Requirements capabilities={OPT_IN} />);

    expect(screen.getByText(OPT_IN_PHRASE)).toBeVisible();
    expect(screen.getByText(/continua recebendo por WhatsApp/)).toBeVisible();
    expect(screen.queryByText(TEMPLATE_PHRASE)).toBeNull();
    expect(screen.queryByText(BAN_PHRASE)).toBeNull();
    expect(screen.queryByText(NONE_PHRASE)).toBeNull();
  });

  it("⛔ a inversão: flags do oficial no cartão do Telegram mostram template, não adesão", () => {
    // Um `provider === "telegram"` passaria no caso acima e cai aqui.
    renderTela(
      tela({
        whatsapp: null,
        telegram: telegram({ capabilities: OFFICIAL }),
      }),
    );

    expect(screen.getByText(TEMPLATE_PHRASE)).toBeVisible();
    expect(screen.queryByText(OPT_IN_PHRASE)).toBeNull();
  });

  it("⛔ … e o par: flags de adesão num provedor de WhatsApp mostram adesão", () => {
    renderTela(
      tela({
        whatsapp: official({ capabilities: OPT_IN }),
        telegram: null,
      }),
    );

    expect(screen.getByText(OPT_IN_PHRASE)).toBeVisible();
    expect(screen.queryByText(TEMPLATE_PHRASE)).toBeNull();
    expect(screen.queryByText(BAN_PHRASE)).toBeNull();
  });

  it("⛔ a terceira frase é da sua flag, não de `official`: opt-in sem oficial mostra; oficial sem opt-in não", () => {
    // Um proxy por outras flags (`official && !requires_templates`) passaria
    // nas inversões acima e cai aqui.
    const { unmount } = render(
      <Requirements capabilities={{ ...OPT_IN, official: false }} />,
    );
    expect(screen.getByText(OPT_IN_PHRASE)).toBeVisible();
    unmount();

    render(
      <Requirements
        capabilities={{ ...OFFICIAL, requires_templates: false }}
      />,
    );
    expect(screen.queryByText(OPT_IN_PHRASE)).toBeNull();
    expect(screen.getByText(NONE_PHRASE)).toBeVisible();
  });

  it("⛔ nenhuma das três → 'sem restrição declarada', e não silêncio", () => {
    // A dívida do C1: silêncio aqui seria a leitura "canal sem regra".
    render(<Requirements capabilities={NONE} />);

    expect(screen.getByText(NONE_PHRASE)).toBeVisible();
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("✅ com qualquer das três, a frase de 'sem restrição' não aparece", () => {
    for (const capabilities of [OFFICIAL, UNOFFICIAL, OPT_IN]) {
      const { unmount } = render(<Requirements capabilities={capabilities} />);

      expect(screen.queryByText(NONE_PHRASE)).toBeNull();
      expect(screen.getAllByRole("listitem")).toHaveLength(1);
      unmount();
    }
  });

  it("duas flags juntas mostram as duas — a tela não esconde uma", () => {
    render(
      <Requirements capabilities={{ ...OPT_IN, requires_templates: true }} />,
    );

    expect(screen.getByText(OPT_IN_PHRASE)).toBeVisible();
    expect(screen.getByText(TEMPLATE_PHRASE)).toBeVisible();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });
});

describe("C4 — a adesão por unidade vive dentro do cartão do Telegram", () => {
  it("✅ com bot, a tabela está na região do Telegram, sob o título 'Adesão por unidade' — e não na do WhatsApp", () => {
    renderTela(tela());

    const t = telegramRegiao();
    expect(
      t.getByRole("heading", { name: "Adesão por unidade" }),
    ).toBeVisible();
    expect(
      t.getByRole("table", { name: "Adesão ao Telegram por unidade" }),
    ).toBeVisible();
    expect(t.getByText("Unidade Zz Alfa")).toBeVisible();
    expect(whatsapp().queryByText("Unidade Zz Alfa")).toBeNull();
    expect(
      whatsapp().queryByRole("heading", { name: "Adesão por unidade" }),
    ).toBeNull();
  });

  it("⛔ sem bot não há adesão — nem tabela, nem título, nem as frases de vazio", () => {
    // Sem bot ninguém adere; um cartão de adesão ao lado de "Nenhum bot de
    // Telegram ativo" contaria zero de um jeito que parece defeito.
    renderTela(tela({ telegram: null }));

    expect(adesao()).toBeNull();
    expect(
      screen.queryByRole("heading", { name: "Adesão por unidade" }),
    ).toBeNull();
    expect(screen.queryByText("Unidade Zz Alfa")).toBeNull();
    expect(screen.queryByText(/Nenhuma unidade com colaboradores/)).toBeNull();
    expect(screen.queryByText(/A adesão não pôde ser lida/)).toBeNull();
  });

  it("a frase da adesão voluntária acompanha o cartão", () => {
    renderTela(tela({ whatsapp: null }));

    expect(
      telegramRegiao().getByText(
        "A adesão é voluntária: quem não aderir continua recebendo pelo WhatsApp.",
      ),
    ).toBeVisible();
  });

  it("`null` na adesão com bot → 'não pôde ser lida', e o resto do cartão do Telegram fica de pé", () => {
    renderTela(tela({ whatsapp: null }), true, null);

    expect(
      telegramRegiao().getByText("A adesão não pôde ser lida agora."),
    ).toBeVisible();
    expect(adesao()).toBeNull();
    expect(telegramRegiao().getByText(BOT)).toBeVisible();
    expect(screen.getByRole("button", { name: "Desconectar" })).toBeVisible();
  });

  it("lista vazia com bot → 'Nenhuma unidade com colaboradores'", () => {
    renderTela(tela({ whatsapp: null }), true, []);

    expect(
      telegramRegiao().getByText("Nenhuma unidade com colaboradores."),
    ).toBeVisible();
    expect(adesao()).toBeNull();
  });

  it("⛔ a adesão não depende de `canWrite`: quem lê a tela lê a contagem", () => {
    renderTela(tela({ whatsapp: null }), false);

    expect(adesao()).toBeVisible();
    expect(screen.getByText("Unidade Zz Beta")).toBeVisible();
  });
});

describe("C5 — as entregas por canal vivem abaixo das duas regiões, sempre", () => {
  it("✅ com os dois canais, o cartão está na tela, fora das duas regiões, com a tabela da prop", () => {
    renderTela(tela());

    expect(
      screen.getByRole("heading", { name: "Entregas por canal" }),
    ).toBeVisible();
    expect(entregas()).toBeVisible();
    // Fora das regiões: é de ambos os canais, e não de um.
    expect(
      whatsapp().queryByRole("heading", { name: "Entregas por canal" }),
    ).toBeNull();
    expect(
      telegramRegiao().queryByRole("heading", { name: "Entregas por canal" }),
    ).toBeNull();
    // E as duas regiões continuam sendo exatamente duas.
    expect(screen.getAllByRole("region")).toHaveLength(2);
    // 40 de WhatsApp, 10 de Telegram: 10/50 = 20%.
    expect(
      within(entregas()!.querySelector("tbody")!)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ).toEqual(["40", "10", "2", "20%"]);
  });

  it("⛔ sem canal nenhum, o cartão continua lá — o `[]` é a mensagem, não um cartão a menos", () => {
    // A produção hoje: nenhum canal, nenhuma entrega. O cartão diz isso.
    renderTela(EMPTY, true, ADHESION, []);

    expect(
      screen.getByRole("heading", { name: "Entregas por canal" }),
    ).toBeVisible();
    expect(
      screen.getByText("Nenhuma entrega registrada nas últimas 8 semanas."),
    ).toBeVisible();
    expect(entregas()).toBeNull();
    expect(screen.getAllByRole("region")).toHaveLength(2);
  });

  it("`null` nas entregas → 'não puderam ser lidas', e o resto da tela fica de pé", () => {
    renderTela(tela(), true, ADHESION, null);

    expect(
      screen.getByText("As entregas não puderam ser lidas agora."),
    ).toBeVisible();
    expect(entregas()).toBeNull();
    expect(telegramRegiao().getByText(BOT)).toBeVisible();
    expect(adesao()).toBeVisible();
  });

  it("a frase do porquê acompanha o cartão em qualquer estado", () => {
    const WHY = "Cada pessoa que adere ao Telegram sai do número de WhatsApp.";

    for (const deliveries of [DELIVERIES, [], null]) {
      const { unmount } = renderTela(EMPTY, true, ADHESION, deliveries);

      expect(screen.getByText(WHY)).toBeVisible();
      unmount();
    }
  });

  it("⛔ as entregas não dependem de `canWrite`: quem lê a tela lê a contagem", () => {
    renderTela(tela(), false);

    expect(entregas()).toBeVisible();
  });

  it("vem abaixo das duas regiões, na ordem do DOM", () => {
    renderTela(tela());

    const cartao = screen.getByRole("heading", { name: "Entregas por canal" });
    for (const region of screen.getAllByRole("region")) {
      expect(
        region.compareDocumentPosition(cartao) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
  });
});
