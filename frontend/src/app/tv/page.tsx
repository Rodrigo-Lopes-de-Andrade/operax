import { TriangleAlert } from "lucide-react";
import type { Metadata } from "next";

import { AutoRefresh } from "@/components/auto-refresh";
import { TvHeader } from "@/components/tv/tv-header";
import { TvKpis } from "@/components/tv/tv-kpis";
import { TvTrend } from "@/components/tv/tv-trend";
import { TvUnits } from "@/components/tv/tv-units";
import { pageTitle } from "@/lib/brand";
import { loadFreshness } from "@/lib/freshness";
import type { RawSearchParams } from "@/lib/ponto/filters";
import { loadTvBoard } from "@/lib/tv/queries";
import { parseTvFilters, TV_REFRESH_SECONDS } from "@/lib/tv/url";

export const metadata: Metadata = {
  title: pageTitle("Painel"),
};

/**
 * The board that hangs on a wall.
 *
 * Aggregates only, and no employee name anywhere on it — F15 of the PRD, and
 * the reason `lib/tv/queries` reads from the summary views and never from
 * `vw_deviation_event`. The rule is enforced by what the page can ask for, not
 * by what it chooses to render.
 */
export default async function PainelDeTvPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const filters = parseTvFilters(await searchParams);
  const [board, freshness] = await Promise.all([
    loadTvBoard(filters),
    loadFreshness(),
  ]);

  return (
    <main className="mx-auto flex w-full max-w-[1600px] flex-col gap-6 px-8 py-8">
      <AutoRefresh seconds={TV_REFRESH_SECONDS} />

      <TvHeader
        unitName={board.unitName}
        today={board.today}
        freshness={freshness}
      />

      {board.unknownUnit ? (
        <p className="bg-alert-bg text-alert flex items-center gap-2 rounded-[14px] px-5 py-3 text-md font-bold">
          <TriangleAlert size={18} aria-hidden />
          Unidade &quot;{board.unknownUnit}&quot; não encontrada — o painel está
          mostrando todas.
        </p>
      ) : null}

      {board.degraded ? (
        // A board that quietly renders zeros is worse than one that admits a
        // gap: on a wall screen nobody is around to notice the difference.
        <p className="bg-alert-bg text-alert flex items-center gap-2 rounded-[14px] px-5 py-3 text-md font-bold">
          <TriangleAlert size={18} aria-hidden />
          Parte dos números não pôde ser lida agora. O que está na tela pode
          estar incompleto.
        </p>
      ) : null}

      <TvKpis board={board} />
      <TvUnits board={board} />
      <TvTrend board={board} />
    </main>
  );
}
