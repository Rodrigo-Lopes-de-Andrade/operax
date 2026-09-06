import "server-only";

import { ApiError, requestApi } from "@/lib/api";
import {
  catalogQuery,
  postosQuery,
  type CatalogFilters,
  type CycleKind,
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
