import "server-only";

import type { SupabaseClient } from "@supabase/supabase-js";

import { ApiError, requestApi } from "@/lib/api";
import type { Database } from "@/lib/database.types";
import {
  catalogQuery,
  cyclesQuery,
  panelQuery,
  postosQuery,
  type CatalogFilters,
  type CycleFilters,
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
   * O eixo do botão de remessa, respondido pelo backend a cada chamada.
   *
   * ⛔ OBRIGATÓRIO, e o tipo diz isso porque o contrato diz: `can_export_remittance`
   * está em `CycleView.required` e em `CycleList.required`. Declará-lo opcional
   * transformaria uma renomeação no backend em `undefined` silencioso — o botão
   * sumiria para sempre, sem um erro de tipo em lugar nenhum.
   *
   * A regra que sobrevive a qualquer mudança é a da leitura, não a do tipo:
   * **ausência vale "não pode"**, nunca "pode". Deduzir o domínio `banking` de
   * uma lista de papéis aqui seria a matriz de sensibilidade escrita uma segunda
   * vez, longe do banco que a altera por `update`.
   */
  can_export_remittance: boolean;
};

/**
 * Uma competência na lista — sem as linhas por pessoa, de propósito.
 *
 * ⛔ ELA NÃO TEM `rows`, E NÃO EXISTE ROTA QUE AS DEVOLVA
 * As linhas nascem na resposta de `POST /dp/ciclos` e não há
 * `GET /dp/ciclos/{id}`. Para uma competência congelada, a conferência pessoa a
 * pessoa sai pelo Excel e pelo PDF, que a tela oferece — a tabela na tela é do
 * preview. Reportado como lacuna de contrato.
 */
export type CycleSummary = {
  id: string;
  kind: CycleKind;
  period_year: number;
  period_month: number;
  window_start: string;
  window_end: string;
  business_days: number | null;
  status: string;
  entitled_count: number;
  denied_count: number;
  total_amount: string;
};

export type CycleList = {
  rows: CycleSummary[];
  /** Propriedade de **quem perguntou**, não da competência — por isso no container. */
  can_export_remittance: boolean;
};

export type CycleListResult =
  | { status: "ok"; list: CycleList }
  | { status: "forbidden" }
  | { status: "unavailable" };

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
 * As competências já apuradas desta rotina e deste mês — **e é ela que decide
 * quem entra na tela de ciclo**.
 *
 * ⛔ O EIXO É `compensation`, E NÃO "SER ADMINISTRADOR"
 * `GET /dp/ciclos` responde 403 exatamente a quem não alcança o domínio de
 * remuneração, e nada além disso: `accounting` e `executive` entram sem serem
 * admin, e `hr` — que é admin e não tem o domínio — não entra. Perguntar à rota
 * é o que faz a tela concordar com o backend em vez de reergueur a parede uma
 * porta adiante.
 *
 * ⚠️ E É ELA QUE REDUZ O SEGUNDO RASCUNHO — REDUZ, E NÃO IMPEDE
 * Sem esta leitura a competência vivia só em `useState`: depois de um F5 a tela
 * dizia "nada apurado" para um mês já gerado, e a única ação era apurar de novo
 * — o que **insere uma segunda linha**, porque `save_draft` procura rascunho
 * ABERTO e o `unique` da competência inclui o `status`. A remessa congelada
 * ficava inalcançável atrás de um rascunho novo.
 *
 * O que esta leitura fecha é esse caminho, que era determinístico e de um
 * operador só. O INSERT continua possível: nada no banco o barra hoje —
 * `trg_benefit_cycle_immutable` é `before update or delete` e não cobre INSERT,
 * e a `unique` inclui o `status`, então a linha nova não colide com a gerada.
 * Duas abas abertas, ou dois operadores no mesmo minuto, e o segundo rascunho
 * nasce assim mesmo. A guarda tem de ser do backend, e não desta função.
 *
 * ✅ E ela passou a existir: desde `6c61592` (08/09/2026) a reserva de
 * `save_draft` perdeu o `status` do `where` e trava a competência inteira com
 * `for update`, e reapurar sobre `generated`/`exported` volta 409. O papel desta
 * leitura não mudou — ela é o que faz a tela não oferecer o clique.
 */
export async function loadCycles(
  filters: CycleFilters,
): Promise<CycleListResult> {
  const token = await accessToken();

  if (!token) {
    return { status: "forbidden" };
  }

  try {
    const list = await requestApi<CycleList>(
      `/dp/ciclos?${cyclesQuery(filters)}`,
      { accessToken: token },
    );

    return { status: "ok", list };
  } catch (error) {
    if (error instanceof ApiError && [401, 403].includes(error.status)) {
      return { status: "forbidden" };
    }

    // A API fora do ar não é falta de permissão: fechar a porta aqui diria
    // "esta tela não existe" sobre uma falha que passa sozinha.
    return { status: "unavailable" };
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
