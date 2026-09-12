import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  loadCompanyRollup,
  loadComplianceReports,
  loadCycles,
  loadDpAlerts,
  loadDpPanel,
  loadPayrollCodes,
  type CompanyChoice,
} from "@/lib/dp/queries";

// `server-only` existe para explodir num bundle de cliente; aqui o módulo é
// exercitado fora do Next, e o stub é o que permite testar a leitura em si.
vi.mock("server-only", () => ({}));

type Session = { access_token: string } | null;

const getSession = vi.fn(async (): Promise<{ data: { session: Session } }> => ({
  data: { session: { access_token: "token-de-teste" } },
}));

vi.mock("@/lib/supabase-server", () => ({
  getServerSupabase: async () => ({ auth: { getSession: () => getSession() } }),
}));

const fetchMock = vi.fn();

const PAYLOAD = {
  on: "2026-09-07",
  total_analyzed: 42,
  active_headcount: 42,
  terminations: 0,
  retention: "1.0000",
  base_payroll: "109384.00",
  base_payroll_average: "2604.38",
  meal_voucher: "0",
  cost_allowance: "0",
  trust_and_hazard: "0",
  without_salary: 0,
  units_with_open_installment: 0,
};

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  getSession.mockClear();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("os nove KPIs — caminho 2", () => {
  it("leva o recorte na query, e nunca o tenant", async () => {
    fetchMock.mockImplementation(async () => answer(200, PAYLOAD));

    await loadDpPanel({
      unitId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      companyId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/dp/painel?empresa=bbbbbbbb");
    expect(url).toContain("unidade=aaaaaaaa");
    // ⛔ O tenant sai do token, e o cliente não o manda em lugar nenhum.
    expect(url).not.toMatch(/tenant/i);
    expect(init.headers.Authorization).toBe("Bearer token-de-teste");
  });

  it("sem recorte não manda query vazia", async () => {
    fetchMock.mockImplementation(async () => answer(200, PAYLOAD));

    const result = await loadDpPanel({ unitId: null, companyId: null });

    expect(fetchMock.mock.calls[0][0]).toMatch(/\/dp\/painel$/);
    expect(result).toEqual({ status: "ok", kpis: PAYLOAD });
  });

  it("403 é ausência de acesso, não erro", async () => {
    fetchMock.mockResolvedValue(
      answer(403, {
        detail: "Seu papel não alcança o domínio de remuneração.",
      }),
    );

    expect(await loadDpPanel({ unitId: null, companyId: null })).toEqual({
      status: "forbidden",
    });
  });

  it("401 também — a sessão que venceu não é uma falha da API", async () => {
    fetchMock.mockResolvedValue(answer(401, { detail: "…" }));

    expect(await loadDpPanel({ unitId: null, companyId: null })).toEqual({
      status: "forbidden",
    });
  });

  it("500 é a API fora do ar, e NÃO vira ausência de acesso", async () => {
    // A distinção é a razão de o desfecho ter três valores: um painel em branco
    // por falha de rede, lido como "não tenho acesso", é a mesma tela contando
    // duas histórias.
    fetchMock.mockResolvedValue(answer(500, { detail: "boom" }));

    expect(await loadDpPanel({ unitId: null, companyId: null })).toEqual({
      status: "unavailable",
    });
  });

  it("rede caída também é indisponibilidade, e não exceção na página", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));

    expect(await loadDpPanel({ unitId: null, companyId: null })).toEqual({
      status: "unavailable",
    });
  });

  it("sem sessão não chega a chamar a API", async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } });

    expect(await loadDpPanel({ unitId: null, companyId: null })).toEqual({
      status: "forbidden",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("consolidado por empresa", () => {
  const COMPANIES: CompanyChoice[] = [
    { id: "11111111-1111-4111-8111-111111111111", name: "Dev Um" },
    { id: "22222222-2222-4222-8222-222222222222", name: "Dev Dois" },
  ];

  it("uma leitura por empresa, com a empresa no recorte", async () => {
    fetchMock.mockImplementation(async () => answer(200, PAYLOAD));

    const rollup = await loadCompanyRollup(
      { unitId: null, companyId: null },
      COMPANIES,
    );

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toContain("empresa=11111111");
    expect(fetchMock.mock.calls[1][0]).toContain("empresa=22222222");
    expect(rollup).toEqual({
      status: "ok",
      rows: [
        {
          companyId: COMPANIES[0].id,
          companyName: "Dev Um",
          activeHeadcount: 42,
          basePayroll: "109384.00",
        },
        {
          companyId: COMPANIES[1].id,
          companyName: "Dev Dois",
          activeHeadcount: 42,
          basePayroll: "109384.00",
        },
      ],
    });
  });

  it("uma empresa que falha derruba o consolidado inteiro", async () => {
    // Meia lista somaria menos que a folha base logo acima, sem dizer qual
    // empresa sumiu.
    fetchMock
      .mockResolvedValueOnce(answer(200, PAYLOAD))
      .mockResolvedValueOnce(answer(500, { detail: "boom" }));

    expect(
      await loadCompanyRollup({ unitId: null, companyId: null }, COMPANIES),
    ).toEqual({ status: "unavailable" });
  });

  it("a unidade do recorte acompanha cada empresa", async () => {
    fetchMock.mockImplementation(async () => answer(200, PAYLOAD));

    await loadCompanyRollup(
      { unitId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", companyId: null },
      [COMPANIES[0]],
    );

    expect(fetchMock.mock.calls[0][0]).toContain("unidade=aaaaaaaa");
  });
});

describe("os oito contadores — caminho 1", () => {
  function client(answer: { data: unknown; error: unknown }) {
    return {
      rpc: vi.fn(async () => answer),
    } as unknown as Parameters<typeof loadDpAlerts>[0];
  }

  it("chama a RPC sem argumento nenhum — o recorte mora dentro dela", async () => {
    const supabase = client({
      data: [
        { code: "birthday_month", total: 3 },
        { code: "document_expired", total: 26 },
      ],
      error: null,
    });

    const result = await loadDpAlerts(supabase);

    expect(supabase.rpc).toHaveBeenCalledWith("fn_dp_alerts");
    expect(supabase.rpc).toHaveBeenCalledTimes(1);
    expect(result).toEqual({
      status: "ok",
      counts: { birthday_month: 3, document_expired: 26 },
    });
  });

  it("erro da RPC vira indisponibilidade, e não oito zeros", async () => {
    const result = await loadDpAlerts(
      client({ data: null, error: { message: "permission denied" } }),
    );

    expect(result).toEqual({ status: "unavailable" });
  });
});

describe("as competências já apuradas — o portão da tela de ciclo", () => {
  const SETEMBRO = {
    kind: "transport_voucher" as const,
    year: 2026,
    month: 9,
  };

  const LISTA = {
    rows: [
      {
        id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        kind: "transport_voucher",
        period_year: 2026,
        period_month: 9,
        window_start: "2026-08-21",
        window_end: "2026-09-20",
        business_days: 21,
        status: "generated",
        entitled_count: 1,
        denied_count: 0,
        total_amount: "201.60",
      },
    ],
    can_export_remittance: true,
  };

  it("pergunta pela competência da URL, e não pelo histórico inteiro", async () => {
    fetchMock.mockImplementation(async () => answer(200, LISTA));

    const result = await loadCycles(SETEMBRO);

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain("/dp/ciclos?kind=transport_voucher");
    expect(url).toContain("ano=2026");
    expect(url).toContain("mes=9");
    expect(result).toEqual({ status: "ok", list: LISTA });
  });

  it("403 fecha a tela: o eixo é `compensation`, e a rota é quem responde", async () => {
    fetchMock.mockResolvedValue(
      answer(403, {
        detail: "Seu papel não alcança o domínio de remuneração.",
      }),
    );

    expect(await loadCycles(SETEMBRO)).toEqual({ status: "forbidden" });
  });

  it("401 fecha também — a sessão que venceu não é a API fora do ar", async () => {
    // O par de baixo do 403: os dois fecham a tela, e o 500 abaixo não. Sem
    // este caso, tirar o 401 da lista deixaria a sessão vencida cair no
    // `unavailable`, e a tela abriria pedindo para recarregar em vez de mandar
    // a pessoa para o login.
    fetchMock.mockResolvedValue(answer(401, { detail: "…" }));

    expect(await loadCycles(SETEMBRO)).toEqual({ status: "forbidden" });
  });

  it("500 NÃO fecha a tela — API fora do ar não é falta de permissão", async () => {
    fetchMock.mockResolvedValue(answer(500, { detail: "boom" }));

    expect(await loadCycles(SETEMBRO)).toEqual({ status: "unavailable" });
  });

  it("sem sessão não chega a perguntar", async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } });

    expect(await loadCycles(SETEMBRO)).toEqual({ status: "forbidden" });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("os laudos vigentes — a lista pelo caminho 1, o `can_write` pela rota", () => {
  const UNIDADE = "11111111-1111-4111-8111-111111111111";

  /** Uma linha como `public.vw_unit_compliance` a devolve: a chave é `report_id`. */
  const DA_VIEW = {
    report_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    unit_id: UNIDADE,
    unit_name: "Aeroporto",
    type: "PCMSO",
    valid_until: "2026-10-01",
    days_to_expiry: 20,
    renewal_count: 1,
    notes: null,
    created_at: "2026-09-01T12:00:00Z",
  };

  /** A linha já traduzida para a tela — `report_id` vira `id`, e nada mais muda. */
  const NA_TELA = {
    id: DA_VIEW.report_id,
    unit_id: UNIDADE,
    unit_name: "Aeroporto",
    type: "PCMSO",
    valid_until: "2026-10-01",
    days_to_expiry: 20,
    renewal_count: 1,
    notes: null,
    created_at: "2026-09-01T12:00:00Z",
  };

  /**
   * O que a ROTA devolve, e que a tela descarta: o `id` aqui é outro de
   * propósito. Se a lista voltar a sair da rota, as asserções abaixo o veem.
   */
  const DA_ROTA = {
    rows: [{ ...NA_TELA, id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee" }],
    can_write: true,
  };

  function view(resposta: { data: unknown; error: unknown }) {
    const builder = {
      select: vi.fn(() => builder),
      order: vi.fn(() => builder),
      eq: vi.fn(() => builder),
      then: (ok: (value: unknown) => unknown) => ok(resposta),
    };
    const from = vi.fn(() => builder);

    return {
      client: { from } as unknown as Parameters<
        typeof loadComplianceReports
      >[0],
      from,
      builder,
    };
  }

  it("⛔ a LISTA sai da view, e da rota só se usa `can_write`", async () => {
    // A migration `20260907182520_dp_unit_compliance.sql` autoriza esta tela a
    // ler `public.vw_unit_compliance` pelo Caminho 1 — é o único consumidor do
    // grant a `authenticated`. Trocar a leitura da view pela da rota deixaria o
    // grant vivo sem dono, e este teste é o que segura isso.
    fetchMock.mockImplementation(async () => answer(200, DA_ROTA));
    const { client, from, builder } = view({ data: [DA_VIEW], error: null });

    const result = await loadComplianceReports(client, {
      unitId: null,
      status: null,
    });

    expect(from).toHaveBeenCalledWith("vw_unit_compliance");
    expect(builder.select).toHaveBeenCalledWith(
      expect.stringContaining("report_id"),
    );
    // A linha é a da view — o `id` da rota não aparece em lugar nenhum.
    expect(result).toEqual({ rows: [NA_TELA], can_write: true });
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/dp\/laudos$/);
  });

  it("o recorte de unidade vai NA CONSULTA da view, e o tenant nunca vai", async () => {
    fetchMock.mockImplementation(async () => answer(200, DA_ROTA));
    const { client, builder } = view({ data: [DA_VIEW], error: null });

    await loadComplianceReports(client, {
      unitId: UNIDADE,
      status: "vencido",
    });

    expect(builder.eq).toHaveBeenCalledWith("unit_id", UNIDADE);
    // ⛔ O cliente não manda tenant: a policy não confiaria nele.
    expect(builder.eq).toHaveBeenCalledTimes(1);
    // A situação não viaja para lado nenhum — ela é derivada na tela.
    expect(fetchMock.mock.calls[0][0]).not.toMatch(/situacao|tenant/i);
    // ⛔ E a ROTA leva o MESMO recorte. O docstring de `loadComplianceReports`
    // afirma que as duas leituras não divergem; sem esta linha a afirmação
    // ficava só no comentário, e o comentário que ninguém segura é o que vira
    // mentira — foi assim que nasceu o achado ALTO do ciclo 1.
    expect(fetchMock.mock.calls[0][0]).toMatch(
      new RegExp(`/dp/laudos\\?.*unidade=${UNIDADE}`),
    );
  });

  it("sem recorte não há `eq` nenhum nem query vazia na rota", async () => {
    fetchMock.mockImplementation(async () => answer(200, DA_ROTA));
    const { client, builder } = view({ data: [], error: null });

    await loadComplianceReports(client, { unitId: null, status: null });

    expect(builder.eq).not.toHaveBeenCalled();
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/dp\/laudos$/);
  });

  it("a ordem é a mesma da rota: unidade e depois tipo", async () => {
    // As duas leituras são da MESMA view; discordar na ordem faria a lista
    // mudar de forma conforme quem a leu.
    fetchMock.mockImplementation(async () => answer(200, DA_ROTA));
    const { client, builder } = view({ data: [DA_VIEW], error: null });

    await loadComplianceReports(client, { unitId: null, status: null });

    expect(builder.order).toHaveBeenCalledTimes(2);
    expect(builder.order).toHaveBeenNthCalledWith(1, "unit_name");
    expect(builder.order).toHaveBeenNthCalledWith(2, "type");
  });

  it("⛔ `can_write` é da rota, e a view não tem como inventá-lo", async () => {
    fetchMock.mockImplementation(async () =>
      answer(200, { ...DA_ROTA, can_write: false }),
    );
    const { client } = view({ data: [DA_VIEW], error: null });

    const result = await loadComplianceReports(client, {
      unitId: null,
      status: null,
    });

    expect(result).toEqual({ rows: [NA_TELA], can_write: false });
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe(
      "Bearer token-de-teste",
    );
  });

  it("resposta da rota sem a chave vale 'não pode'", async () => {
    fetchMock.mockImplementation(async () => answer(200, { rows: [] }));
    const { client } = view({ data: [DA_VIEW], error: null });

    expect(
      await loadComplianceReports(client, { unitId: null, status: null }),
    ).toEqual({ rows: [NA_TELA], can_write: false });
  });

  it("a view que falha é null — não há lista para mostrar", async () => {
    fetchMock.mockImplementation(async () => answer(200, DA_ROTA));
    const { client } = view({
      data: null,
      error: { message: "permission denied for view vw_unit_compliance" },
    });

    expect(
      await loadComplianceReports(client, { unitId: null, status: null }),
    ).toBeNull();
  });

  it("⛔ 500 da ROTA não derruba a lista: ela é lida pelo outro caminho", async () => {
    // O 500 tem lado, e é este: a rota fora do ar tira o botão de escrever e
    // não a lista, que não depende dela. Relançar aqui mandaria a tela inteira
    // para o error boundary por causa de um booleano.
    fetchMock.mockResolvedValue(answer(500, { detail: "boom" }));
    const { client } = view({ data: [DA_VIEW], error: null });

    expect(
      await loadComplianceReports(client, { unitId: null, status: null }),
    ).toEqual({ rows: [NA_TELA], can_write: false });
  });

  it("401 e 403 da rota também só tiram a escrita", async () => {
    fetchMock.mockResolvedValueOnce(answer(403, { detail: "…" }));
    const primeira = view({ data: [DA_VIEW], error: null });
    expect(
      await loadComplianceReports(primeira.client, {
        unitId: null,
        status: null,
      }),
    ).toEqual({ rows: [NA_TELA], can_write: false });

    fetchMock.mockResolvedValueOnce(answer(401, { detail: "…" }));
    const segunda = view({ data: [DA_VIEW], error: null });
    expect(
      await loadComplianceReports(segunda.client, {
        unitId: null,
        status: null,
      }),
    ).toEqual({ rows: [NA_TELA], can_write: false });
  });

  it("a rede caída na rota não tira a lista do ar", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const { client } = view({ data: [DA_VIEW], error: null });

    expect(
      await loadComplianceReports(client, { unitId: null, status: null }),
    ).toEqual({ rows: [NA_TELA], can_write: false });
  });

  it("sem sessão a rota não é chamada, e a view responde pela RLS", async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } });
    const { client, from } = view({ data: [], error: null });

    expect(
      await loadComplianceReports(client, { unitId: null, status: null }),
    ).toEqual({ rows: [], can_write: false });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(from).toHaveBeenCalledWith("vw_unit_compliance");
  });
});

describe("a curadoria de rubrica — o 403 carrega a frase da API", () => {
  const RUBRICAS = {
    rows: [
      {
        code: "0001",
        label: "SALARIO BASE",
        nature: "earning",
        category: null,
        validated: false,
        validated_at: null,
        in_payroll: true,
      },
    ],
    pending: 1,
    can_write: true,
  };

  it("200 devolve a lista com `pending` e `can_write` como vieram", async () => {
    fetchMock.mockImplementation(async () => answer(200, RUBRICAS));

    const result = await loadPayrollCodes();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/dp\/rubricas$/);
    expect(init.headers.Authorization).toBe("Bearer token-de-teste");
    expect(result).toEqual({ status: "ok", list: RUBRICAS });
  });

  it("⛔ 403 é `forbidden` COM o detail — `hr` é admin, passa a página, e a API explica", async () => {
    fetchMock.mockResolvedValue(
      answer(403, {
        detail:
          "Classificar rubrica exige papel administrativo. Seu papel consulta a folha, mas não define como ela é somada.",
      }),
    );

    expect(await loadPayrollCodes()).toEqual({
      status: "forbidden",
      detail:
        "Classificar rubrica exige papel administrativo. Seu papel consulta a folha, mas não define como ela é somada.",
    });
  });

  it("401 é null, e não `forbidden`: sessão vencida não tem frase para mostrar", async () => {
    fetchMock.mockResolvedValue(answer(401, { detail: "Not authenticated" }));

    expect(await loadPayrollCodes()).toBeNull();
  });

  it("API fora do ar também é null — nada foi lido", async () => {
    fetchMock.mockResolvedValue(answer(500, { detail: "boom" }));

    expect(await loadPayrollCodes()).toBeNull();
  });

  it("sem sessão não chega a chamar a API", async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } });

    expect(await loadPayrollCodes()).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
