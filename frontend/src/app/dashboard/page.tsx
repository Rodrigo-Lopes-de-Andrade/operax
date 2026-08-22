import type { Metadata } from "next";

import { pageTitle } from "@/lib/brand";

import { FilterBar } from "@/components/ponto/filter-bar";
import { KpiGrid } from "@/components/ponto/kpi-grid";
import { OccurrenceDrawer } from "@/components/ponto/occurrence-drawer";
import { OccurrencesCard } from "@/components/ponto/occurrences-card";
import { Rankings } from "@/components/ponto/rankings";
import { TrendCard } from "@/components/ponto/trend-card";
import { parseFilters, type RawSearchParams } from "@/lib/ponto/filters";
import { loadPontoScreen } from "@/lib/ponto/queries";
import { parsePaging } from "@/lib/ponto/url";

export const metadata: Metadata = {
  title: pageTitle("Gestão de ponto"),
};

/**
 * Gestão de ponto — the landing screen of the panel.
 *
 * The whole cut arrives in the query string, so the page is a pure function of
 * the URL: the WhatsApp alert link opens it already filtered, and the browser's
 * back button walks the manager's own filter history. Every read is Caminho 1,
 * and what the user may see is decided by RLS, not by this file.
 */
export default async function GestaoDePontoPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const params = await searchParams;
  const filters = parseFilters(params);
  const paging = parsePaging(params);
  const screen = await loadPontoScreen(filters, paging.page, paging.pageSize);

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Operação
        </p>
        <h1 className="text-ink text-2xl font-extrabold">Gestão de ponto</h1>
      </header>

      <FilterBar screen={screen} filters={filters} paging={paging} />
      <KpiGrid screen={screen} />
      <TrendCard screen={screen} />
      <Rankings screen={screen} />
      <OccurrencesCard screen={screen} filters={filters} paging={paging} />

      {filters.eventId ? (
        <OccurrenceDrawer
          occurrence={screen.selected}
          filters={filters}
          paging={paging}
        />
      ) : null}
    </div>
  );
}
