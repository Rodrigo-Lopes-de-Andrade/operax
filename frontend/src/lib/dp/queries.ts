import "server-only";

import type { SupabaseClient } from "@supabase/supabase-js";

import { ApiError, requestApi } from "@/lib/api";
import type { Database } from "@/lib/database.types";
import {
  catalogQuery,
  cyclesQuery,
  laudosQuery,
  panelQuery,
  postosQuery,
  type CatalogFilters,
  type CycleFilters,
  type CycleKind,
  type LaudosFilters,
  type PanelFilters,
  type PostosFilters,
} from "@/lib/dp/url";
import { getServerSupabase } from "@/lib/supabase-server";

/**
 * Caminho 2 quase sempre, e a exceção está nomeada.
 *
 * Quase nenhuma tabela desta etapa concede leitura a `authenticated`, então não
 * existe view em `public` para o navegador ler direto: o Quadro de Postos e o
 * catálogo de preços vêm do FastAPI, que pergunta papel e domínio ao banco a
 * cada chamada. O que o painel lê pelo caminho 1 é a lista de unidades do
 * seletor (`vw_unit`) e os oito contadores de alerta (`fn_dp_alerts`).
 *
 * ⚠️ `app.unit_compliance_report` É A EXCEÇÃO DO S5, E ELA É DELIBERADA
 * A migration `20260907182520_dp_unit_compliance.sql` concede `select` nela a
 * `authenticated` porque `public.vw_unit_compliance` é `security_invoker` e
 * sem o grant devolveria `permission denied` — e a concede **para esta tela**,
 * pelo Caminho 1, autorizada pelo dono em 07/09/2026. Laudo é documento da
 * unidade: não há pessoa, não há valor e não há domínio sensível. Ver
 * `loadComplianceReports`.
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

/**
 * Um laudo VIGENTE da unidade.
 *
 * ⛔ Não há campo de situação, e a ausência é do contrato (`ComplianceReportRow`):
 * EM DIA / A VENCER / VENCIDO se derivam de `days_to_expiry` com o limiar que a
 * UI já declara em `lib/rh/labels.ts` (`dueTone`). `days_to_expiry` é negativo
 * quando venceu; `renewal_count` é quantas vezes esta cadeia já foi renovada.
 */
export type ComplianceReportRow = {
  id: string;
  unit_id: string;
  unit_name: string;
  type: string;
  valid_until: string;
  days_to_expiry: number;
  renewal_count: number;
  notes: string | null;
  created_at: string;
};

/** `can_write` é cortesia do backend para esconder Renovar — não é fronteira. */
export type ComplianceReportList = {
  rows: ComplianceReportRow[];
  can_write: boolean;
};

/**
 * Um código do plano de contas do cliente e o que a curadoria já disse dele.
 *
 * `category` nula = conhecido e ainda não classificado — o estado em que a
 * semente entrega a lista. `validated` é `validated_at is not null`, e não uma
 * coluna. `in_payroll` distingue o código que a folha usa daquele que alguém
 * curou e a folha não usa mais: o segundo não conta como pendência.
 */
export type PayrollCodeRow = {
  code: string;
  label: string | null;
  nature: string | null;
  category: string | null;
  validated: boolean;
  validated_at: string | null;
  in_payroll: boolean;
};

/**
 * `pending` conta **códigos que a folha usa e ninguém classificou** — o número
 * que diz se algum indicador financeiro está incompleto. Vem da mesma função
 * que entrega categoria a quem soma; a tela não o recalcula.
 */
export type PayrollCodeList = {
  rows: PayrollCodeRow[];
  pending: number;
  can_write: boolean;
};

/**
 * `forbidden` carrega o `detail` da API de propósito: `hr` é admin, passa a
 * porta da página, e recebe 403 porque não tem `compensation` — e a frase que
 * explica isso é escrita no backend para o usuário ler.
 */
export type PayrollCodesResult =
  | { status: "ok"; list: PayrollCodeList }
  | { status: "forbidden"; detail: string | null };

/**
 * Uma justificativa de afastamento do Secullum e o que a curadoria disse dela.
 *
 * `justification` é a chave como o BANCO a guarda — `upper(btrim(...))`, acento
 * preservado, truncada como a origem a mandou (`ATEST M`, `AFASTAD`).
 * "Consertá-la" na tela inventaria uma chave que o apurador não procura.
 *
 * `category` nula = conhecida e não classificada; `validated` é
 * `validated_at is not null`, e não uma coluna. `in_mirror` distingue a que o
 * espelho traz daquela que alguém curou e o espelho não traz mais.
 *
 * ⚠️ NÃO HÁ `validated_by` — a coluna existe na tabela e o contrato não a
 * devolve. A tela mostra QUANDO alguém avalizou, nunca QUEM. Reportado.
 */
export type LeaveJustificationRow = {
  justification: string;
  occurrences: number;
  first_leave: string | null;
  last_leave: string | null;
  category: string | null;
  validated: boolean;
  validated_at: string | null;
  notes: string | null;
  in_mirror: boolean;
};

/**
 * A fila de curadoria e os **dois** números que dizem se a apuração vai recusar.
 *
 * `pending` conta o que o espelho traz e ninguém validou — classificado ou não,
 * porque provisório trava igual. `without_justification` conta os afastamentos
 * que chegaram sem nome nenhum: eles travam a competência e **não há o que
 * classificar neles**. Sem esse segundo número a tela diria "tudo curado"
 * enquanto o dinheiro segue parado, que é o falso verde desta tela.
 */
export type LeaveJustificationList = {
  rows: LeaveJustificationRow[];
  pending: number;
  without_justification: number;
};

/**
 * `forbidden` carrega o `detail` porque a recusa é deliberada e escrita para o
 * usuário: a rota exige `util.is_admin` e a frase nomeia o que está em jogo.
 * A página já fecha por `isAdmin`, mas as duas listas de papéis podem divergir
 * — quando divergirem, quem manda é a API, e ela explica.
 */
export type LeaveJustificationsResult =
  | { status: "ok"; list: LeaveJustificationList }
  | { status: "forbidden"; detail: string | null };

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

/** As colunas da view, na ordem em que a linha da tabela as mostra. */
const COMPLIANCE_COLUMNS =
  "report_id, unit_id, unit_name, type, valid_until, days_to_expiry, renewal_count, notes, created_at";

/**
 * A lista pelo Caminho 1 — a leitura que a migration autorizou.
 *
 * O recorte de unidade vai na consulta, e não numa filtragem depois: a policy
 * já recortou por escopo, e trazer o resto para descartar aqui seria ler o que
 * a tela não mostra. A ordem é a mesma da rota (`unit_name, type`), para que as
 * duas leituras da mesma view não discordem na ordem das linhas.
 *
 * O `| null` de cada coluna é artefato do gerador de tipos para view; na tabela
 * elas são `not null`. Os defaults seguem o que `toOccurrence` já faz com
 * `vw_deviation_event`.
 */
async function readComplianceView(
  supabase: SupabaseClient<Database>,
  filters: LaudosFilters,
): Promise<ComplianceReportRow[] | null> {
  let query = supabase
    .from("vw_unit_compliance")
    .select(COMPLIANCE_COLUMNS)
    .order("unit_name")
    .order("type");

  if (filters.unitId) {
    query = query.eq("unit_id", filters.unitId);
  }

  const { data, error } = await query;

  if (error || !data) {
    return null;
  }

  return data.map((row) => ({
    id: row.report_id ?? "",
    unit_id: row.unit_id ?? "",
    unit_name: row.unit_name ?? "",
    type: row.type ?? "",
    valid_until: row.valid_until ?? "",
    days_to_expiry: row.days_to_expiry ?? 0,
    renewal_count: row.renewal_count ?? 0,
    notes: row.notes,
    created_at: row.created_at ?? "",
  }));
}

/**
 * A única coisa que a rota responde para esta tela: se quem pergunta escreve.
 *
 * Falha nenhuma daqui derruba a tela. `can_write` é cortesia para esconder
 * Renovar, e **ausência vale "não pode"** — a API revalida `util.is_admin` em
 * todo `POST`, então esconder o botão por não ter conseguido perguntar não
 * fecha porta nenhuma que estivesse aberta.
 */
async function readComplianceWrite(filters: LaudosFilters): Promise<boolean> {
  const token = await accessToken();

  if (!token) {
    return false;
  }

  const query = laudosQuery(filters);

  try {
    const list = await requestApi<ComplianceReportList>(
      query ? `/dp/laudos?${query}` : "/dp/laudos",
      { accessToken: token },
    );

    return list.can_write === true;
  } catch {
    return false;
  }
}

/**
 * Os laudos vigentes das unidades que quem pergunta enxerga: a lista da view,
 * o `can_write` da rota, as duas em paralelo.
 *
 * ⛔ A LISTA VEM DA VIEW, E É A MIGRATION QUE MANDA
 * `20260907182520_dp_unit_compliance.sql` escreve, na seção da superfície
 * pública: "a tela de Unidades e o link filtrado leem daqui; a rota
 * `/dp/laudos` serve o retorno de `POST`/`renovar` e o `can_write`" — Caminho
 * 1, autorizado pelo dono em 07/09/2026. Ler a lista pela rota deixaria
 * `public.vw_unit_compliance` com um grant a `authenticated` vivo e nenhum
 * consumidor no repositório: superfície sem dono.
 *
 * ⚠️ O QUE ISSO CUSTA, E A DECISÃO É DO DONO, NÃO DESTA CAMADA
 * `GET /dp/laudos` devolve `rows` que esta função **descarta**: a chamada existe
 * pelo `can_write`. É o preço de a view ter o consumidor que a autorizou. O
 * recorte não diverge — a rota lê a mesma view, com o mesmo filtro de unidade.
 *
 * Sem porta por papel: a policy recorta por `util.can_see_unit`, e o supervisor
 * de unidade recebe os laudos da unidade dele — persona nomeada no PRD.
 *
 * Null é "a lista não foi lida", e só a view o produz: sessão sem
 * `authenticated`, view ausente no ambiente, banco fora. A rota que não responde
 * não é isso — ver `readComplianceWrite`.
 */
export async function loadComplianceReports(
  supabase: SupabaseClient<Database>,
  filters: LaudosFilters,
): Promise<ComplianceReportList | null> {
  const [rows, canWrite] = await Promise.all([
    readComplianceView(supabase, filters),
    readComplianceWrite(filters),
  ]);

  return rows === null ? null : { rows, can_write: canWrite };
}

/**
 * O plano de contas com a curadoria — e o 403 aqui NÃO é o mesmo estado que o
 * 401.
 *
 * A rota exige `compensation` **e** administração. `hr` é admin sem
 * `compensation`: passa a porta da página (`isAdmin`) e é recusado pela API com
 * uma frase escrita para ele. Devolvê-la é o que faz a tela concordar com o
 * backend em vez de mostrar "não pôde ser lido" para uma recusa deliberada.
 * Sessão ausente, 401 e a API fora do ar viram null: nada foi lido.
 */
export async function loadPayrollCodes(): Promise<PayrollCodesResult | null> {
  const token = await accessToken();

  if (!token) {
    return null;
  }

  try {
    const list = await requestApi<PayrollCodeList>("/dp/rubricas", {
      accessToken: token,
    });

    return { status: "ok", list };
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      return { status: "forbidden", detail: error.detail };
    }

    return null;
  }
}

/**
 * A fila da curadoria de justificativa de afastamento — Caminho 2 inteiro.
 *
 * ⛔ NÃO HÁ CAMINHO 1 AQUI, E NÃO É ESCOLHA DESTA CAMADA
 * A fila sai de `secullum."FuncionarioAfastamento"`, e `secullum` não tem
 * `usage` para `authenticated` desde a migration 01; `app.leave_justification_map`
 * tem `revoke all` dos dois papéis do PostgREST. Um `select` do navegador
 * morreria com `permission denied` em vez de ser filtrado.
 *
 * ⚠️ E NÃO HÁ `can_write`, DE PROPÓSITO: as três rotas exigem o MESMO eixo
 * (`util.is_admin`), então quem lê a fila é exatamente quem a escreve. Um
 * `can_write` aqui seria sempre `true` — um campo que só pode mentir.
 *
 * 403 é recusa deliberada com frase própria; 401 e API fora do ar viram null:
 * nada foi lido, e a tela diz isso em vez de dizer "sem pendência".
 */
export async function loadLeaveJustifications(): Promise<LeaveJustificationsResult | null> {
  const token = await accessToken();

  if (!token) {
    return null;
  }

  try {
    const list = await requestApi<LeaveJustificationList>(
      "/dp/justificativas",
      { accessToken: token },
    );

    return { status: "ok", list };
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      return { status: "forbidden", detail: error.detail };
    }

    return null;
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
