import "server-only";

import type { SupabaseClient } from "@supabase/supabase-js";

import { ApiError, requestApi } from "@/lib/api";
import type { Database } from "@/lib/database.types";
import {
  catalogQuery,
  panelQuery,
  postosQuery,
  type CatalogFilters,
  type CycleKind,
  type PanelFilters,
  type PostosFilters,
} from "@/lib/dp/url";
import { getServerSupabase } from "@/lib/supabase-server";

/**
 * Caminho 2, e não poderia ser outro.
 *
 * Nenhuma das tabelas desta etapa concede leitura a `authenticated`, então não
 * existe view em `public` para o navegador ler direto: o Quadro de Postos e o
 * catálogo de preços vêm do FastAPI, que pergunta papel e domínio ao banco a
 * cada chamada. O que o painel lê pelo caminho 1 aqui é só a lista de unidades
 * do seletor, que é `vw_unit`.
 */

export type WorkPostRow = {
  id: string;
  unit_id: string;
  unit_name: string;
  code: string;
  name: string | null;
  active: boolean;
  created_at: string;
};

/** `can_write` é do backend: esconder o formulário é cortesia, não fronteira. */
export type WorkPostList = {
  rows: WorkPostRow[];
  can_write: boolean;
};

export type BenefitTypeRow = {
  code: string;
  name: string;
  /** Entra na folha salarial base. É a definição do KPI, não um rótulo. */
  composes_base: boolean;
  /** `fixed_amount` | `salary_rate`. */
  calculation: string;
  domain: string;
  active: boolean;
};

export type BenefitPlanRow = {
  id: string;
  benefit_type_code: string;
  code: string;
  provider: string;
  name: string;
  /** `Decimal` do Pydantic chega como string. Ver `lib/dp/format.ts`. */
  amount: string;
  effective_from: string;
  effective_to: string | null;
  reason: string | null;
};

export type TransportFareRow = {
  id: string;
  code: string;
  name: string;
  /** `single` | `round_trip` — faz parte da identidade da tarifa. */
  kind: string;
  amount: string;
  effective_from: string;
  effective_to: string | null;
  reason: string | null;
};

/**
 * O catálogo **numa data**, e nunca "o catálogo": `on` é a data em que ele foi
 * lido, e a tela a mostra porque um preço lido sem data acerta por acidente.
 */
export type BenefitCatalog = {
  on: string;
  types: BenefitTypeRow[];
  plans: BenefitPlanRow[];
  fares: TransportFareRow[];
  can_write: boolean;
};

/** A linha por pessoa do ciclo. ⛔ Não existe campo de conta bancária aqui. */
export type CycleEntitlementRow = {
  employee_id: string;
  name: string;
  registration_number: string | null;
  unit_id: string | null;
  unit_name: string | null;
  entitled: boolean;
  /** A frase que explica a perda do direito. A pessoa vai perguntar. */
  reason: string | null;
  days_base: number | null;
  absences_prior: number | null;
  net_days: number | null;
  unit_amount: string | null;
  round_trip_amount: string | null;
  total_amount: string | null;
};

export type CycleView = {
  id: string | null;
  kind: CycleKind;
  period_year: number;
  period_month: number;
  window_start: string;
  window_end: string;
  business_days: number | null;
  /** `draft` reapura, `generated` não — a diferença é a regra 9 do PRD. */
  status: string;
  entitled_count: number;
  denied_count: number;
  total_amount: string;
  rows: CycleEntitlementRow[];
  /**
   * ⚠️ CAMPO AINDA NÃO ENVIADO PELO BACKEND, E A AUSÊNCIA FECHA O BOTÃO.
   *
   * O domínio `banking` decide se o arquivo de remessa aparece (SPEC-DP §3), e
   * hoje nenhuma rota conta ao painel se quem perguntou o tem: `CycleView` não
   * traz o eixo e `/me` devolve só o papel. Deduzi-lo aqui de uma lista de
   * papéis seria a matriz `app.role_domain` escrita uma segunda vez, longe do
   * banco que a muda por `update` — exatamente o que `operax/dp/banking.py`
   * recusa fazer no backend.
   *
   * Então o painel lê o que o backend mandar e, sem campo, não mostra botão: a
   * falta de resposta vira "não pode", nunca "pode". O contrato pedido é um
   * booleano nesta resposta, no mesmo formato do `can_write` que as outras duas
   * rotas já devolvem.
   */
  can_export_remittance?: boolean;
};

async function accessToken(): Promise<string | null> {
  const supabase = await getServerSupabase();
  const { data } = await supabase.auth.getSession();

  return data.session?.access_token ?? null;
}

/**
 * Null quando a sessão acabou ou quando o papel não alcança — os dois viram o
 * mesmo estado vazio na tela, e nenhum deles é uma exceção.
 */
export async function loadWorkPosts(
  filters: PostosFilters,
): Promise<WorkPostList | null> {
  const token = await accessToken();

  if (!token) {
    return null;
  }

  const query = postosQuery(filters);

  try {
    return await requestApi<WorkPostList>(
      query ? `/dp/postos?${query}` : "/dp/postos",
      { accessToken: token },
    );
  } catch (error) {
    if (error instanceof ApiError && [401, 403].includes(error.status)) {
      return null;
    }

    throw error;
  }
}

export async function loadBenefitCatalog(
  filters: CatalogFilters,
): Promise<BenefitCatalog | null> {
  const token = await accessToken();

  if (!token) {
    return null;
  }

  const query = catalogQuery(filters);

  try {
    return await requestApi<BenefitCatalog>(
      query ? `/dp/beneficios/catalogo?${query}` : "/dp/beneficios/catalogo",
      { accessToken: token },
    );
  } catch (error) {
    // 403 aqui é o papel sem `compensation`. Vira o mesmo estado vazio de uma
    // API fora do ar: a tela não tem por que distinguir os dois, e o backend
    // recusa a escrita de qualquer jeito.
    if (error instanceof ApiError && [401, 403].includes(error.status)) {
      return null;
    }

    throw error;
  }
}

/**
 * Os nove KPIs de topo, mais os dois que o backend manda junto por honestidade
 * (`without_salary` e `units_with_open_installment`).
 *
 * ⛔ Nenhum campo aqui carrega pessoa — nem nome, nem id, nem lista. O cartão de
 * sinistro é **contagem**: o painel do legado nomeia quem tem parcela em aberto
 * na home, e aqui o nome exige abrir a ficha.
 *
 * `Decimal` do Pydantic chega como string. Ver `lib/dp/format.ts`.
 */
export type DpPanelKpis = {
  on: string;
  total_analyzed: number;
  active_headcount: number;
  terminations: number;
  /** `ativos / total no filtro`, com quatro casas. `null` na base vazia. */
  retention: string | null;
  base_payroll: string;
  base_payroll_average: string | null;
  meal_voucher: string;
  cost_allowance: string;
  trust_and_hazard: string;
  without_salary: number;
  units_with_open_installment: number;
};

/**
 * Três desfechos, e são três de propósito.
 *
 * `forbidden` é quem não alcança o domínio `compensation` — regra 5 do projeto:
 * quem não pode **não vê**, e a metade de cima da tela simplesmente não existe
 * para ele. Não é cadeado, não é cinza, não é erro.
 *
 * `unavailable` é a API fora do ar, e essa **precisa** aparecer: um painel em
 * branco por falha de rede lido como "não tenho acesso" é a mesma tela contando
 * duas histórias diferentes. As duas viraram um estado vazio só no catálogo do
 * S1, onde a tela inteira dependia da mesma chamada; aqui não dá, porque a
 * metade de baixo (os oito contadores) vem por outro caminho e continua de pé.
 */
export type PanelResult =
  | { status: "ok"; kpis: DpPanelKpis }
  | { status: "forbidden" }
  | { status: "unavailable" };

export async function loadDpPanel(filters: PanelFilters): Promise<PanelResult> {
  const token = await accessToken();

  if (!token) {
    return { status: "forbidden" };
  }

  const query = panelQuery(filters);

  try {
    const kpis = await requestApi<DpPanelKpis>(
      query ? `/dp/painel?${query}` : "/dp/painel",
      { accessToken: token },
    );

    return { status: "ok", kpis };
  } catch (error) {
    if (error instanceof ApiError && [401, 403].includes(error.status)) {
      return { status: "forbidden" };
    }

    // Sem `throw`: a página tem outra metade que não depende desta chamada, e
    // derrubá-la inteira levaria junto oito contadores que responderam bem.
    return { status: "unavailable" };
  }
}

/** Empresa do seletor e do consolidado, derivada de `vw_unit`. */
export type CompanyChoice = { id: string; name: string };

/** Uma linha do consolidado por empresa. O nome vem de `vw_unit`, caminho 1. */
export type CompanyPayrollRow = {
  companyId: string;
  companyName: string;
  activeHeadcount: number;
  basePayroll: string;
};

export type CompanyRollupResult =
  { status: "ok"; rows: CompanyPayrollRow[] } | { status: "unavailable" };

/**
 * O consolidado por empresa do `ANEXO` §2e — empresa, ativos, folha base.
 *
 * ⚠️ É UMA CHAMADA POR EMPRESA, E ISSO É O CONTRATO QUE FALTA
 * `GET /dp/painel` responde **um** agregado e aceita `empresa` como recorte; não
 * existe rota que devolva a quebra por empresa num payload só. Então a tela
 * compõe o que existe em vez de inventar rota que responderia 404 em produção —
 * as chamadas saem em paralelo e a FastPark tem cinco e poucos CNPJs. O contrato
 * que resolveria isso é uma lista por empresa dentro da própria resposta do
 * painel; enquanto não existe, o custo é este e está declarado.
 *
 * Uma empresa que falhe derruba o cartão inteiro, e não uma linha: um
 * consolidado a que falta uma empresa soma menos que o total logo acima, sem
 * nada na tela dizendo qual sumiu.
 */
export async function loadCompanyRollup(
  filters: PanelFilters,
  companies: CompanyChoice[],
): Promise<CompanyRollupResult> {
  const results = await Promise.all(
    companies.map(async (company) => ({
      company,
      result: await loadDpPanel({ ...filters, companyId: company.id }),
    })),
  );

  const rows: CompanyPayrollRow[] = [];

  for (const { company, result } of results) {
    if (result.status !== "ok") {
      return { status: "unavailable" };
    }

    rows.push({
      companyId: company.id,
      companyName: company.name,
      activeHeadcount: result.kpis.active_headcount,
      basePayroll: result.kpis.base_payroll,
    });
  }

  return { status: "ok", rows };
}

/**
 * Os oito contadores do painel de alertas — **caminho 1**.
 *
 * `public.fn_dp_alerts()` é `security definer` com o recorte de tenant e escopo
 * dentro dela, e devolve `(code, total)` e nada mais. O cliente não manda
 * `tenant_id`: a policy não confiaria nele. Cinco dos oito leem domínio
 * sensível e mesmo assim a função responde a `authenticated`, porque contar não
 * é ler — nenhum nome, nenhuma data de nascimento, nenhuma pessoa sai daqui.
 */
export type AlertCounts = Record<string, number>;

export type AlertsResult =
  { status: "ok"; counts: AlertCounts } | { status: "unavailable" };

export async function loadDpAlerts(
  supabase: SupabaseClient<Database>,
): Promise<AlertsResult> {
  const { data, error } = await supabase.rpc("fn_dp_alerts");

  if (error || !data) {
    return { status: "unavailable" };
  }

  const counts: AlertCounts = {};

  for (const row of data) {
    counts[row.code] = row.total;
  }

  return { status: "ok", counts };
}
