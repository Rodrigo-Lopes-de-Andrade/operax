import type { TvBoard } from "@/lib/tv/queries";
import {
  formatDayShort,
  formatNumber,
  formatWeekday,
} from "@/lib/ponto/format";

/**
 * Seven days of occurrence counts, as plain bars.
 *
 * No chart library here on purpose: there is nothing to hover on a wall screen,
 * so a tooltip is dead weight and the interactive chart would ship a client
 * bundle to a page that never takes an event. Heights in CSS say the same
 * thing.
 *
 * The scale is the tallest day, and every day keeps a visible stub even at
 * zero — a missing bar reads as missing data, which is the one thing this board
 * must never imply by accident.
 */
export function TvTrend({ board }: { board: TvBoard }) {
  const peak = Math.max(...board.trend.map((day) => day.eventos), 1);

  return (
    <section className="bg-card border-line-subtle flex flex-col gap-4 rounded-[18px] border p-6">
      <h2 className="text-ink-muted text-xs font-bold tracking-[0.08em] uppercase">
        Últimos 7 dias
      </h2>

      <div className="flex h-[120px] items-end gap-3">
        {board.trend.map((day) => {
          const isToday = day.day === board.today;

          return (
            <div
              key={day.day}
              className="flex min-w-0 flex-1 flex-col items-center gap-2"
            >
              <span className="text-ink text-sm font-bold tabular-nums">
                {formatNumber(day.eventos)}
              </span>
              <span
                className={`w-full rounded-t-[6px] ${
                  isToday ? "bg-brand" : "bg-shortfall/70"
                }`}
                style={{
                  height: `${Math.max((day.eventos / peak) * 72, 3)}px`,
                }}
              />
            </div>
          );
        })}
      </div>

      <div className="flex gap-3">
        {board.trend.map((day) => (
          <p
            key={day.day}
            className={`min-w-0 flex-1 text-center text-xs ${
              day.day === board.today ? "text-ink font-bold" : "text-ink-muted"
            }`}
          >
            {formatWeekday(day.day)} {formatDayShort(day.day)}
          </p>
        ))}
      </div>
    </section>
  );
}
