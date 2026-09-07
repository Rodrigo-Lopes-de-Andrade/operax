import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PanelScreen } from "@/components/dp/panel-screen";
import { pageTitle } from "@/lib/brand";
import {
  loadCompanyRollup,
  loadDpAlerts,
  loadDpPanel,
  type CompanyChoice,
} from "@/lib/dp/queries";
import { parsePanelFilters } from "@/lib/dp/url";
import { loadIdentity } from "@/lib/identity";
import type { RawSearchParams } from "@/lib/ponto/filters";
import { loadUnits } from "@/lib/ponto/queries";
import { getServerSupabase } from "@/lib/supabase-server";

export const metadata: Metadata = {
  title: pageTitle("Painel de DP"),
};

/**
 * Painel de DP — e ele come pelos **dois** caminhos do contrato.
 *
 * Os nove KPIs são caminho 2: folha base é dinheiro de pessoa, o domínio
 * `compensation` é obrigatório, e o FastAPI o revalida a cada chamada. Os oito
 * contadores de alerta são caminho 1: `public.fn_dp_alerts()` devolve
 * `(code, total)` e o recorte de tenant e escopo mora dentro dela — o navegador
 * não manda `tenant_id`, e não adiantaria mandar.
 *
 * ⛔ NÃO HÁ LISTA DE PAPÉIS DECIDINDO ESTA TELA, E A AUSÊNCIA É A DECISÃO
 * Quem alcança os KPIs é quem tem `compensation`, e isso é linha de
 * `app.domain_permission` — dado que o cliente muda por `update`, não constante
 * de código. Uma lista de papéis aqui seria essa matriz escrita uma segunda vez,
 * longe do banco que a altera; e erraria hoje, porque `accounting` tem o domínio
 * e não está em nenhuma das listas de navegação deste frontend. Então a página
 * abre para quem tem vínculo com o tenant, e cada metade se fecha sozinha: o
 * FastAPI responde 403 a quem não tem o domínio, e a RLS decide quem entra em
 * cada contador.
 *
 * O recorte mora na query string, como no resto do produto: o link que alguém
 * cola pedindo "confere a folha da Norte" abre a Norte, e não o painel inteiro.
 */
export default async function PainelDePessoalPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const identity = await loadIdentity();

  if (!identity) {
    notFound();
  }

  const filters = parsePanelFilters(await searchParams);
  const supabase = await getServerSupabase();

  const [panel, alerts, units] = await Promise.all([
    loadDpPanel(filters),
    loadDpAlerts(supabase),
    loadUnits(supabase),
  ]);

  const companies: CompanyChoice[] = [
    ...new Map(
      units.map((unit) => [
        unit.companyId,
        { id: unit.companyId, name: unit.companyName },
      ]),
    ).values(),
  ];

  // ⚠️ Uma leitura por empresa, e só quando ela diz algo. Recortado numa
  // empresa, o painel inteiro já é aquela empresa e a tabela repetiria o cartão
  // acima; com uma empresa só, ela repetiria o total. Ver `loadCompanyRollup`
  // para o contrato que faria disto uma chamada só.
  const rollup =
    panel.status === "ok" && !filters.companyId && companies.length > 1
      ? await loadCompanyRollup(filters, companies)
      : null;

  return (
    <PanelScreen
      panel={panel}
      alerts={alerts}
      rollup={rollup}
      filters={filters}
      companies={companies}
      units={units}
    />
  );
}
