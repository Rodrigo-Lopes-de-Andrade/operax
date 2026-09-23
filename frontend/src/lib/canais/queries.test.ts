import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import {
  loadConnections,
  loadContacts,
  loadCredential,
  loadDeliveryByChannel,
  loadProviderForms,
  loadRules,
  loadTelegramAdhesion,
  loadTelegramLink,
  loadTemplates,
  type ConnectionsScreen,
  type CredentialStatus,
  type DeliveryByChannelRow,
  type ProviderForm,
  type TelegramAdhesionRow,
  type TelegramLink,
  type TemplateRow,
} from "@/lib/canais/queries";

// `server-only` existe para explodir num bundle de cliente; aqui o módulo é
// exercitado fora do Next, e o stub é o que permite testar a leitura em si.
vi.mock("server-only", () => ({}));

type Session = { access_token: string } | null;

const getSession = vi.fn(async (): Promise<{ data: { session: Session } }> => ({
  data: { session: { access_token: "token-de-teste" } },
}));

/** O `rpc` do Caminho 1 — a adesão por unidade e as entregas por canal. */
const rpc = vi.fn();

vi.mock("@/lib/supabase-server", () => ({
  getServerSupabase: async () => ({
    auth: { getSession: () => getSession() },
    rpc: (...args: unknown[]) => rpc(...args),
  }),
}));

const fetchMock = vi.fn();

/** Os dois canais preenchidos — a leitura devolve o que veio, canal a canal. */
const PAYLOAD: ConnectionsScreen = {
  whatsapp: {
    provider: "meta_cloud",
    capabilities: {
      official: true,
      requires_templates: true,
      ban_risk: false,
      requires_recipient_opt_in: false,
    },
    templates_total: 2,
    templates_approved: 1,
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
    capabilities: {
      official: true,
      requires_templates: false,
      ban_risk: false,
      requires_recipient_opt_in: true,
    },
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

/** O estado da produção hoje: cliente sem canal nenhum. */
const SEM_CANAL: ConnectionsScreen = { whatsapp: null, telegram: null };

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  rpc.mockReset();
  getSession.mockClear();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a tela de Conexões — caminho 2", () => {
  it("200 devolve a resposta como veio, com o token no header e sem tenant na URL", async () => {
    fetchMock.mockResolvedValue(answer(200, PAYLOAD));

    const screen = await loadConnections();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/canais\/conexoes$/);
    // ⛔ O tenant sai do token, e o cliente não o manda em lugar nenhum.
    expect(url).not.toMatch(/tenant/i);
    expect(init.headers.Authorization).toBe("Bearer token-de-teste");
    expect(screen).toEqual(PAYLOAD);
  });

  it("os dois canais nulos são resposta válida, não null — é a produção hoje", async () => {
    // `null` da leitura é sessão ou papel; `{ whatsapp: null, telegram: null }`
    // é um cliente sem canal, e a tela tem estado próprio para cada um.
    fetchMock.mockResolvedValue(answer(200, SEM_CANAL));

    expect(await loadConnections()).toEqual(SEM_CANAL);
  });

  it("401 é a sessão que venceu, e vira null", async () => {
    fetchMock.mockResolvedValue(answer(401, { detail: "…" }));

    expect(await loadConnections()).toBeNull();
  });

  it("403 é ausência de acesso, e vira null", async () => {
    fetchMock.mockResolvedValue(
      answer(403, { detail: "Sem vínculo ativo com este cliente." }),
    );

    expect(await loadConnections()).toBeNull();
  });

  it("⛔ 500 relança — a API fora do ar não é 'sem canal'", async () => {
    // Engolir o 500 em null renderizaria "não pôde ser lido" onde o error
    // boundary é que deveria aparecer; e um dia alguém trocaria a frase por
    // "nenhum canal configurado" e a tela mentiria numa queda de rede.
    fetchMock.mockResolvedValue(answer(500, { detail: "boom" }));

    await expect(loadConnections()).rejects.toBeInstanceOf(ApiError);
    await expect(loadConnections()).rejects.toMatchObject({ status: 500 });
  });

  it("sem sessão não chega a chamar a API", async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } });

    expect(await loadConnections()).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

const CREDENTIAL: CredentialStatus = {
  channel: "whatsapp",
  configured: true,
  provider: "meta_cloud",
  updated_at: "2026-09-14T13:05:00Z",
  public_identity: "+55 11 99999-0000",
};

const TELEGRAM_CREDENTIAL: CredentialStatus = {
  channel: "telegram",
  configured: true,
  provider: "telegram",
  updated_at: "2026-09-15T13:05:00Z",
  public_identity: "@zz_bot_inventado",
};

const FORMS: ProviderForm[] = [
  {
    provider: "meta_cloud",
    channel: "whatsapp",
    capabilities: {
      official: true,
      requires_templates: true,
      ban_risk: false,
      requires_recipient_opt_in: false,
    },
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
    ],
  },
];

describe("a credencial — o estado, nunca o valor (caminho 2), um canal por vez", () => {
  it("200 devolve o estado como veio, com o token no header e sem tenant na URL", async () => {
    fetchMock.mockResolvedValue(answer(200, CREDENTIAL));

    const status = await loadCredential("whatsapp");

    const [url, init] = fetchMock.mock.calls[0];
    // ⛔ O canal vai na query string, e é o único parâmetro.
    expect(url).toMatch(/\/canais\/credencial\?canal=whatsapp$/);
    expect(url).not.toMatch(/tenant/i);
    expect(init.headers.Authorization).toBe("Bearer token-de-teste");
    expect(status).toEqual(CREDENTIAL);
  });

  it("⛔ o canal do Telegram pede `?canal=telegram` — e não o do WhatsApp", async () => {
    // Uma função que ignorasse o argumento passaria no caso acima e cai aqui.
    fetchMock.mockResolvedValue(answer(200, TELEGRAM_CREDENTIAL));

    const status = await loadCredential("telegram");

    const [url] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/canais\/credencial\?canal=telegram$/);
    expect(url).not.toMatch(/whatsapp/);
    expect(status).toEqual(TELEGRAM_CREDENTIAL);
  });

  it("401 vira null", async () => {
    fetchMock.mockResolvedValue(answer(401, { detail: "…" }));

    expect(await loadCredential("whatsapp")).toBeNull();
  });

  it("403 vira null", async () => {
    fetchMock.mockResolvedValue(
      answer(403, { detail: "Sem vínculo ativo com este cliente." }),
    );

    expect(await loadCredential("telegram")).toBeNull();
  });

  it("⛔ 500 relança — a API fora do ar não é 'sem credencial'", async () => {
    fetchMock.mockResolvedValue(answer(500, { detail: "boom" }));

    await expect(loadCredential("whatsapp")).rejects.toMatchObject({
      status: 500,
    });
  });
});

describe("os formulários dos provedores (caminho 2)", () => {
  it("200 devolve a lista na ordem da API, com o token no header e sem tenant na URL", async () => {
    fetchMock.mockResolvedValue(answer(200, FORMS));

    const forms = await loadProviderForms();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/canais\/provedores$/);
    expect(url).not.toMatch(/tenant/i);
    expect(init.headers.Authorization).toBe("Bearer token-de-teste");
    expect(forms).toEqual(FORMS);
  });

  it("401 vira null", async () => {
    fetchMock.mockResolvedValue(answer(401, { detail: "…" }));

    expect(await loadProviderForms()).toBeNull();
  });

  it("403 vira null", async () => {
    fetchMock.mockResolvedValue(
      answer(403, { detail: "Sem vínculo ativo com este cliente." }),
    );

    expect(await loadProviderForms()).toBeNull();
  });

  it("⛔ 500 relança", async () => {
    fetchMock.mockResolvedValue(answer(500, { detail: "boom" }));

    await expect(loadProviderForms()).rejects.toBeInstanceOf(ApiError);
  });

  it("sem sessão nenhuma das duas chega a chamar a API", async () => {
    getSession
      .mockResolvedValueOnce({ data: { session: null } })
      .mockResolvedValueOnce({ data: { session: null } });

    expect(await loadCredential("whatsapp")).toBeNull();
    expect(await loadProviderForms()).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

/** Códigos que nenhum template real tem: a leitura devolve o que a API mandou. */
const TEMPLATES: TemplateRow[] = [
  {
    code: "zz_teste_alfa",
    category: "utility",
    language: "pt_BR",
    variables: ["data_observada", "horario"],
    body: "Em {{1}} às {{2}}.",
    meta_template_name: null,
    meta_status: "draft",
    meta_rejection: null,
    active: true,
    updated_at: "2026-09-15T13:05:00Z",
  },
  {
    code: "zz_teste_beta",
    category: "marketing",
    language: "en_US",
    variables: ["unit"],
    body: "{{1}}",
    meta_template_name: "zz_teste_beta_v1",
    meta_status: "rejected",
    meta_rejection: "INVALID_FORMAT",
    active: false,
    updated_at: "2026-09-14T09:00:00Z",
  },
];

describe("o catálogo de templates (caminho 2)", () => {
  it("200 devolve a lista como veio, com o token no header e sem tenant na URL", async () => {
    fetchMock.mockResolvedValue(answer(200, TEMPLATES));

    const templates = await loadTemplates();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/canais\/templates$/);
    expect(url).not.toMatch(/tenant/i);
    expect(init.headers.Authorization).toBe("Bearer token-de-teste");
    expect(init.method).toBe("GET");
    expect(templates).toEqual(TEMPLATES);
  });

  it("401 vira null", async () => {
    fetchMock.mockResolvedValue(answer(401, { detail: "…" }));

    expect(await loadTemplates()).toBeNull();
  });

  it("403 vira null", async () => {
    fetchMock.mockResolvedValue(
      answer(403, { detail: "Sem vínculo ativo com este cliente." }),
    );

    expect(await loadTemplates()).toBeNull();
  });

  it("⛔ 500 relança — a API fora do ar não é 'nenhum template'", async () => {
    // Produção está vazia de verdade; engolir o 500 em null é o que deixaria
    // a queda da API indistinguível da tela do primeiro dia.
    fetchMock.mockResolvedValue(answer(500, { detail: "boom" }));

    await expect(loadTemplates()).rejects.toBeInstanceOf(ApiError);
    await expect(loadTemplates()).rejects.toMatchObject({ status: 500 });
  });

  it("sem sessão não chega a chamar a API", async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } });

    expect(await loadTemplates()).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

const EMPLOYEE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

/** Vinculado — e nenhum `chat_id` no contrato para vir junto. */
const LINKED: TelegramLink = {
  linked: true,
  opted_in_at: "2026-09-15T13:05:00Z",
  revoked_at: null,
  invite_open_until: null,
};

describe("o vínculo de um colaborador com o bot (caminho 2)", () => {
  it("200 devolve o vínculo como veio, na rota do colaborador, com o token no header e sem tenant na URL", async () => {
    fetchMock.mockResolvedValue(answer(200, LINKED));

    const link = await loadTelegramLink(EMPLOYEE);

    const [url, init] = fetchMock.mock.calls[0];
    // ⛔ O id vai no caminho, e é o único parâmetro: o tenant sai do token.
    expect(url).toMatch(new RegExp(`/canais/telegram/vinculos/${EMPLOYEE}$`));
    expect(url).not.toMatch(/tenant/i);
    expect(init.headers.Authorization).toBe("Bearer token-de-teste");
    expect(init.method).toBe("GET");
    expect(link).toEqual(LINKED);
  });

  it("⛔ … e é o id recebido que vai na rota, não um fixo", async () => {
    // Uma função que ignorasse o argumento passaria no caso acima e cai aqui.
    const outro = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
    fetchMock.mockResolvedValue(answer(200, LINKED));

    await loadTelegramLink(outro);

    const [url] = fetchMock.mock.calls[0];
    expect(url).toMatch(new RegExp(`/canais/telegram/vinculos/${outro}$`));
    expect(url).not.toContain(EMPLOYEE);
  });

  it("401 vira null", async () => {
    fetchMock.mockResolvedValue(answer(401, { detail: "…" }));

    expect(await loadTelegramLink(EMPLOYEE)).toBeNull();
  });

  it("403 vira null", async () => {
    fetchMock.mockResolvedValue(
      answer(403, { detail: "Sem vínculo ativo com este cliente." }),
    );

    expect(await loadTelegramLink(EMPLOYEE)).toBeNull();
  });

  it("404 vira null — 'não vê o colaborador' é o mesmo recorte da ficha, e a ficha é quem diz isso", async () => {
    // As duas leituras vão no mesmo `Promise.all`: um 404 relançado aqui
    // derrubaria a página no error boundary em vez de deixar a ficha mostrar
    // "Colaborador não encontrado".
    fetchMock.mockResolvedValue(answer(404, { detail: "não encontrado" }));

    expect(await loadTelegramLink(EMPLOYEE)).toBeNull();
  });

  it("⛔ 500 relança — a API fora do ar não é 'sem vínculo'", async () => {
    fetchMock.mockResolvedValue(answer(500, { detail: "boom" }));

    await expect(loadTelegramLink(EMPLOYEE)).rejects.toBeInstanceOf(ApiError);
    await expect(loadTelegramLink(EMPLOYEE)).rejects.toMatchObject({
      status: 500,
    });
  });

  it("sem sessão não chega a chamar a API", async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } });

    expect(await loadTelegramLink(EMPLOYEE)).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

/** Nomes de unidade inventados; contagens, e nada que nomeie uma pessoa. */
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

describe("a adesão por unidade (caminho 1)", () => {
  it("✅ chama `fn_telegram_adhesion` sem parâmetro nenhum — o tenant e o escopo saem da sessão", async () => {
    rpc.mockResolvedValue({ data: ADHESION, error: null });

    const rows = await loadTelegramAdhesion();

    expect(rpc).toHaveBeenCalledTimes(1);
    // ⛔ Sem `tenant_id`, sem unidade, sem nada: a função não aceita argumento
    // (`Args: never`), e é `util.user_tenants()` + `util.can_see_unit` que
    // recortam. Um argumento a mais aqui não seria filtro — seria a tela
    // acreditando que filtra.
    expect(rpc).toHaveBeenCalledWith("fn_telegram_adhesion");
    expect(JSON.stringify(rpc.mock.calls[0])).not.toMatch(/tenant/i);
    expect(rows).toEqual(ADHESION);
    // E nenhuma chamada à API: é Caminho 1.
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("⛔ devolve só as cinco colunas do contrato — nada além do que a RPC promete chega à tela", async () => {
    // A função de banco tem prova de que o tipo de retorno não nomeia pessoa;
    // a leitura repete a fronteira: uma coluna a mais que aparecesse na
    // resposta não passa daqui.
    rpc.mockResolvedValue({
      data: [{ ...ADHESION[0], zz_coluna_a_mais: "não passa" }],
      error: null,
    });

    const rows = await loadTelegramAdhesion();

    expect(rows).toEqual([ADHESION[0]]);
    expect(Object.keys(rows![0]).sort()).toEqual([
      "joined",
      "pending",
      "revoked",
      "unit_id",
      "unit_name",
    ]);
  });

  it("lista vazia é lista vazia — 'nenhuma unidade' é um estado, e não é o de erro", async () => {
    rpc.mockResolvedValue({ data: [], error: null });

    expect(await loadTelegramAdhesion()).toEqual([]);
  });

  it("erro do Postgres vira null, como o frescor faz", async () => {
    rpc.mockResolvedValue({
      data: null,
      error: { message: "permission denied" },
    });

    expect(await loadTelegramAdhesion()).toBeNull();
  });

  it("`data` nulo sem erro também é null — não há linha para mostrar", async () => {
    rpc.mockResolvedValue({ data: null, error: null });

    expect(await loadTelegramAdhesion()).toBeNull();
  });
});

/**
 * Duas semanas, e na primeira dois provedores de WhatsApp — a leitura devolve
 * as linhas como vieram; quem soma é o cartão. Nenhum nome, nenhum destino.
 */
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
    channel: "whatsapp",
    provider: "z_api",
    sent: 5,
    failed: 1,
  },
  {
    week_start: "2026-09-07",
    channel: "telegram",
    provider: "telegram",
    sent: 12,
    failed: 0,
  },
];

describe("as entregas por canal (caminho 1)", () => {
  it("✅ chama `fn_delivery_by_channel` com `{ p_weeks: 8 }` por padrão — e nada mais", async () => {
    rpc.mockResolvedValue({ data: DELIVERIES, error: null });

    const rows = await loadDeliveryByChannel();

    expect(rpc).toHaveBeenCalledTimes(1);
    // ⛔ O único argumento é a janela. O tenant sai da sessão, e a policy
    // `alert_sent_read` é quem recorta — um `tenant_id` aqui não seria
    // filtro, seria a tela acreditando que filtra.
    expect(rpc).toHaveBeenCalledWith("fn_delivery_by_channel", { p_weeks: 8 });
    expect(JSON.stringify(rpc.mock.calls[0])).not.toMatch(/tenant/i);
    expect(rows).toEqual(DELIVERIES);
    // E nenhuma chamada à API: é Caminho 1.
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("… e é a janela recebida que vai no argumento, não a fixa", async () => {
    // Uma função que ignorasse o argumento passaria no caso acima e cai aqui.
    rpc.mockResolvedValue({ data: [], error: null });

    await loadDeliveryByChannel(12);

    expect(rpc).toHaveBeenCalledWith("fn_delivery_by_channel", {
      p_weeks: 12,
    });
  });

  it("⛔ devolve só as cinco colunas do contrato — uma sexta na resposta não passa", async () => {
    // A função de banco prova, pelo nome, que o retorno não tem destino nem
    // hash; a leitura repete a fronteira do lado de cá.
    rpc.mockResolvedValue({
      data: [{ ...DELIVERIES[0], destination_hash: "não passa" }],
      error: null,
    });

    const rows = await loadDeliveryByChannel();

    expect(rows).toEqual([DELIVERIES[0]]);
    expect(Object.keys(rows![0]).sort()).toEqual([
      "channel",
      "failed",
      "provider",
      "sent",
      "week_start",
    ]);
  });

  it("lista vazia é lista vazia — 'nenhuma entrega' é o estado normal enquanto o sender não roda, e não é o de erro", async () => {
    rpc.mockResolvedValue({ data: [], error: null });

    expect(await loadDeliveryByChannel()).toEqual([]);
  });

  it("erro do Postgres vira null", async () => {
    rpc.mockResolvedValue({
      data: null,
      error: { message: "permission denied" },
    });

    expect(await loadDeliveryByChannel()).toBeNull();
  });

  it("`data` nulo sem erro também é null", async () => {
    rpc.mockResolvedValue({ data: null, error: null });

    expect(await loadDeliveryByChannel()).toBeNull();
  });
});

describe("C6 — destinatários, regras e o catálogo de tipos de desvio (caminho 2)", () => {
  it("✅ os contatos vêm de `/canais/destinatarios/contatos`, como vieram, com o token e sem tenant", async () => {
    // Um contato inativo e a matriz dele: a leitura não filtra nada — quem
    // marca é a tela.
    const contatos = [
      {
        id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        name: "Zz Pessoa",
        whatsapp: "5511999990000",
        email: "zz@fastpark.dev",
        type: "person",
        active: false,
        units: [
          {
            unit_id: "11111111-1111-4111-8111-111111111111",
            unit_name: "Unidade Zz",
            responsibility: "unit_manager",
            is_primary: true,
          },
        ],
      },
    ];
    fetchMock.mockResolvedValue(answer(200, contatos));

    const rows = await loadContacts();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/canais\/destinatarios\/contatos$/);
    expect(url).not.toMatch(/tenant/i);
    expect(init.headers.Authorization).toBe("Bearer token-de-teste");
    expect(rows).toEqual(contatos);
  });

  it("✅ as regras vêm de `/canais/regras`, com `blocked_reason` como veio — nulo inclusive", async () => {
    const regras = [
      {
        id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
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
        template_code: "zz_template",
        active: true,
        targets: [],
        blocked_reason: "Nenhum destino ativo: zz frase do backend.",
      },
    ];
    fetchMock.mockResolvedValue(answer(200, regras));

    const rows = await loadRules();

    expect(fetchMock.mock.calls[0][0]).toMatch(/\/canais\/regras$/);
    expect(rows).toEqual(regras);
  });

  it("403 vira null nas duas — `GET /regras` é do administrador, e a página já fechou antes", async () => {
    fetchMock.mockResolvedValue(
      answer(403, { detail: "Ler regras e destinos é do administrador." }),
    );

    expect(await loadContacts()).toBeNull();
    expect(await loadRules()).toBeNull();
  });

  it("⛔ 500 relança — a API fora do ar não é 'nenhuma regra'", async () => {
    fetchMock.mockResolvedValue(answer(500, { detail: "boom" }));

    await expect(loadRules()).rejects.toBeInstanceOf(ApiError);
  });

  it("sem sessão não chega a chamar a API", async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } });

    expect(await loadContacts()).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
