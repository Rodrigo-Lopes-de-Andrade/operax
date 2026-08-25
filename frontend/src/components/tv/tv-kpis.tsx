import type { TvBoard } from "@/lib/tv/queries";
import { formatDuration, formatNumber } from "@/lib/ponto/format";

/**
 * Four figures, read from across a room.
 *
 * Every one of them is a count or a sum. None of them is a person: the board
 * says "14 colaboradores" and never which fourteen, because the screen hangs
 * where anyone walking past can read it.
 */
export function TvKpis({ board }: { board: TvBoard }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Figure
        label="Ocorrências hoje"
        value={formatNumber(board.eventos)}
        note={
          board.unitName
            ? "Nesta unidade"
            : `${formatNumber(board.unidadesAfetadas)} unidades afetadas`
        }
      />
      <Figure
        label="Colaboradores"
        value={formatNumber(board.colaboradores)}
        note="Com pelo menos um indício"
      />
      <Figure
        label="Excedente"
        value={formatDuration(board.minutesExcedente)}
        tone="surplus"
        note="Além do previsto"
      />
      <Figure
        label="Faltante"
        value={formatDuration(board.minutesFaltante)}
        tone="shortfall"
        note="Aquém do previsto"
      />
    </div>
  );
}

const TONE_CLASS = {
  ink: "text-ink",
  surplus: "text-surplus",
  shortfall: "text-shortfall",
} as const;

function Figure({
  label,
  value,
  note,
  tone = "ink",
}: {
  label: string;
  value: string;
  note: string;
  tone?: keyof typeof TONE_CLASS;
}) {
  return (
    <section className="bg-card border-line-subtle flex flex-col gap-2 rounded-[18px] border p-6">
      <p className="text-ink-muted text-xs font-bold tracking-[0.08em] uppercase">
        {label}
      </p>
      <p
        className={`text-4xl leading-none font-extrabold tabular-nums ${TONE_CLASS[tone]}`}
      >
        {value}
      </p>
      <p className="text-ink-muted text-sm">{note}</p>
    </section>
  );
}
