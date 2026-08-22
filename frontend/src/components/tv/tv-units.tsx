import type { TvBoard } from "@/lib/tv/queries";
import { formatDuration, formatNumber } from "@/lib/ponto/format";

/**
 * One tile per unit, busiest first.
 *
 * A unit with nothing today keeps its tile and shows a zero. Dropping it would
 * be the cheaper render and the worse board: on a wall screen, a unit that is
 * simply absent reads as a unit nobody is watching.
 *
 * The tile carries a count of people, never a name — F15 of the PRD, and the
 * reason this whole route reads from the aggregate views only.
 */
export function TvUnits({ board }: { board: TvBoard }) {
  if (board.units.length === 0) {
    return null;
  }

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-ink-muted text-xs font-bold tracking-[0.08em] uppercase">
        Ocorrências por unidade
      </h2>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {board.units.map((unit) => (
          <article
            key={unit.unitId}
            className={`bg-card flex items-center justify-between gap-4 rounded-[16px] border p-5 ${
              unit.eventos > 0 ? "border-shortfall/40" : "border-line-subtle"
            }`}
          >
            <div className="min-w-0">
              <p className="text-ink truncate text-xl font-extrabold">
                {unit.name}
              </p>
              <p className="text-ink-muted mt-1 text-sm">
                {unit.eventos === 0
                  ? "Sem indício até a última leitura"
                  : `${formatNumber(unit.colaboradores)} ${
                      unit.colaboradores === 1 ? "colaborador" : "colaboradores"
                    } · ${formatDuration(unit.minutesAbs)}`}
              </p>
            </div>
            <p
              className={`shrink-0 text-4xl leading-none font-extrabold tabular-nums ${
                unit.eventos > 0 ? "text-shortfall" : "text-ink-faint"
              }`}
            >
              {formatNumber(unit.eventos)}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
