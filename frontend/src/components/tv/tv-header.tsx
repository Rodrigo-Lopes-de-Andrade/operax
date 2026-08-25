import { CircleAlert, Clock } from "lucide-react";
import { SquareParking } from "lucide-react";

import { currentBrand } from "@/lib/brand";
import type { DataFreshness } from "@/lib/freshness";
import { formatAge, formatClock, formatDayLong } from "@/lib/ponto/format";

/**
 * The band across the top of the board: whose screen, which cut, and how old
 * the numbers are.
 *
 * The age is the largest thing here after the unit name, and that is on
 * purpose. Everywhere else in the product the age is a pill on the chrome; on a
 * wall screen there is no chrome and nobody to hover, so a picture taken at
 * 08:40 has to announce itself at three metres or it announces nothing.
 */
export function TvHeader({
  unitName,
  today,
  freshness,
}: {
  unitName: string | null;
  today: string;
  freshness: DataFreshness | null;
}) {
  const brand = currentBrand();

  return (
    <header className="flex flex-wrap items-center justify-between gap-6">
      <div className="flex items-center gap-4">
        <span className="bg-brand text-on-brand flex size-12 items-center justify-center rounded-[14px]">
          <SquareParking aria-hidden className="size-7" strokeWidth={2.2} />
        </span>
        <div>
          {/* A real heading, even though nobody navigates this page with a
              screen reader: the route has to have one, and the unit is what
              this board is about. */}
          <h1 className="text-ink text-3xl leading-none font-extrabold">
            {unitName ?? brand.name}
          </h1>
          <p className="text-ink-muted mt-1.5 text-md font-semibold">
            {unitName ? brand.name : "Todas as unidades"} ·{" "}
            {formatDayLong(today)}
          </p>
        </div>
      </div>

      <Freshness freshness={freshness} />
    </header>
  );
}

function Freshness({ freshness }: { freshness: DataFreshness | null }) {
  if (!freshness) {
    return (
      <span className="text-ink-muted flex items-center gap-3 rounded-[18px] border border-line px-6 py-4 text-lg font-bold">
        <Clock size={22} aria-hidden />
        Sem leitura registrada
      </span>
    );
  }

  const Icon = freshness.isStale ? CircleAlert : Clock;

  return (
    <span
      className={`flex items-center gap-3 rounded-[18px] px-6 py-4 text-lg font-bold ${
        freshness.isStale
          ? "bg-alert-bg text-alert"
          : "border border-line text-ink-body"
      }`}
    >
      <Icon size={22} aria-hidden />
      <span className="tabular-nums">
        Dados de {formatClock(freshness.lastSyncAt)} ·{" "}
        {formatAge(freshness.ageMinutes)}
      </span>
      {freshness.isStale ? <span>— leitura atrasada</span> : null}
    </span>
  );
}
