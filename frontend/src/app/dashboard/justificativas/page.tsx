import type { Metadata } from "next";

import { PendingBar } from "@/components/justificativas/pending-bar";
import { PendingCard } from "@/components/justificativas/pending-card";
import { OccurrenceDrawer } from "@/components/ponto/occurrence-drawer";
import { pageTitle } from "@/lib/brand";
import { loadPendingScreen } from "@/lib/justificativas/queries";
import {
  justificativasHref,
  parsePendingFilters,
} from "@/lib/justificativas/url";
import type { RawSearchParams } from "@/lib/ponto/filters";
import { parsePaging } from "@/lib/ponto/url";

export const metadata: Metadata = {
  title: pageTitle("Pendentes de justificativa"),
};

/**
 * Pendentes de justificativa — o passivo, e não o retrato do período.
 *
 * A migration 23 criou `fn_pending_justification` e o veredito ganhou porta em
 * 26/08; faltava a tela que perguntasse "o que ainda espera explicação". É esta.
 * Como o resto do dashboard, o recorte inteiro vem da query string, e o que o
 * usuário alcança é decidido pela RLS — a função é `security invoker`.
 */
export default async function PendentesDeJustificativaPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const params = await searchParams;
  const filters = parsePendingFilters(params);
  const paging = parsePaging(params);
  const screen = await loadPendingScreen(filters, paging.page, paging.pageSize);

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Operação
        </p>
        <h1 className="text-ink text-2xl font-extrabold">
          Pendentes de justificativa
        </h1>
      </header>

      <PendingBar screen={screen} filters={filters} paging={paging} />
      <PendingCard screen={screen} filters={filters} paging={paging} />

      {filters.eventId ? (
        <OccurrenceDrawer
          occurrence={screen.selected}
          closeHref={justificativasHref(filters, paging, { eventId: null })}
        />
      ) : null}
    </div>
  );
}
