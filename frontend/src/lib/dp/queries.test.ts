import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  loadCompanyRollup,
  loadCycles,
  loadDpAlerts,
  loadDpPanel,
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
