import { CheckCheck } from "lucide-react";

import { Chip } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { SignedMinutes } from "@/components/ui/signed-minutes";
import { Table, type Column, type Row } from "@/components/ui/table";
import type { PunchRow, WorkdayRow } from "@/lib/colaborador/queries";
import {
  formatClock,
  formatDayShort,
  formatTime,
  formatWeekday,
} from "@/lib/ponto/format";

/** Below this, the roster was inferred rather than read, and it is not a finding. */
const CONFIDENCE_THRESHOLD = 80;

const DAY_TYPE_LABEL: Record<string, string> = {
  work: "",
  day_off: "folga",
  vacation: "férias",
  leave_period: "afastamento",
  holiday: "feriado",
  compensated: "compensado",
};

const COLUMNS: Column[] = [
  { key: "dia", label: "Data", width: "104px", noWrap: true },
  {
    key: "previsto",
    label: "Previsto",
    mono: true,
    numeric: true,
    width: "120px",
  },
  { key: "marcacoes", label: "Marcações", mono: true },
  {
    key: "registrado",
    label: "Registrado",
    mono: true,
    numeric: true,
    width: "120px",
  },
  { key: "desvio", label: "Desvio", align: "right" },
];

type DayLine = {
  date: string;
  workday: WorkdayRow | null;
  punches: PunchRow[];
};

/**
 * The day-by-day of the period, with the raw punch sequence beside it.
 *
 * "Registrado" is what the engine compared — one time, the one that produced the
 * indication. "Marcações" is the whole day as the source recorded it, in the
 * order the columns come in, and the two answer different questions: the first
 * says why there is a finding, the second says what actually happened.
 *
 * A DAY WITH PUNCHES AND NO ROSTER STILL GETS A LINE
 * The list is the union of the two, not the roster with punches attached.
 * `punch_on_day_off` exists precisely because somebody punched on a day nobody
 * expected them, and building the rows from `app.expected_workday` alone would
 * drop exactly that day.
 *
 * A dash is a column the source left empty. It is not "did not clock in" — the
 * whole list is only true as of the last reading, and the header says when that
 * was rather than leaving it to be assumed.
 */
export function WorkdayHistory({
  workdays,
  punches,
  readAt,
}: {
  workdays: WorkdayRow[];
  punches: PunchRow[];
  readAt: string | null;
}) {
  const rows: Row[] = mergeByDay(workdays, punches).map((line) => ({
    id: line.date,
    cells: {
      dia: (
        <span className="flex flex-col">
          <span className="text-ink font-bold">
            {formatDayShort(line.date)}
          </span>
          <span className="text-ink-faint text-xs">
            {formatWeekday(line.date)}
          </span>
        </span>
      ),
      previsto: line.workday ? (
        dayLabel(line.workday)
      ) : (
        <span className="text-ink-faint font-sans text-xs">sem jornada</span>
      ),
      marcacoes: <PunchSequence punches={line.punches} />,
      registrado: formatTime(line.workday?.actual_time ?? null),
      desvio: line.workday?.deviation_type ? (
        <span className="flex flex-col items-end gap-1">
          <SignedMinutes
            minutes={line.workday.minutes ?? 0}
            direction={line.workday.direction ?? "neutral"}
            size="sm"
          />
          <span className="text-ink-faint text-xs">
            {line.workday.deviation_description}
          </span>
        </span>
      ) : (
        <span className="text-ink-faint text-xs">sem desvio</span>
      ),
    },
  }));

  return (
    <Card>
      <CardHeader
        eyebrow="Jornada"
        title="Dia a dia do período"
        note={
          readAt
            ? `Marcações como estavam na leitura de ${formatClock(readAt)}.`
            : "Ainda não houve leitura de marcação concluída para este cliente."
        }
      />
      <Table
        columns={COLUMNS}
        rows={rows}
        density="compact"
        caption="Jornada dia a dia"
        empty={
          <div className="px-5">
            <EmptyState
              icon={CheckCheck}
              tone="neutral"
              compact
              title="Nenhum dia no período"
              description="A escala esperada deste colaborador ainda não foi materializada para estas datas."
            />
          </div>
        }
      />
    </Card>
  );
}

/**
 * As colunas do dia na ordem em que a origem as guarda: Entrada1, Saída1,
 * Entrada2… Ordenar por horário parece mais natural e esconde exatamente o
 * caso que importa — o par cuja saída faltou.
 */
function PunchSequence({ punches }: { punches: PunchRow[] }) {
  if (punches.length === 0) {
    return <span className="text-ink-faint font-sans text-xs">—</span>;
  }

  return (
    <span className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
      {punches.map((punch, index) => (
        <span
          key={`${punch.column_type}-${punch.column_index}`}
          className="flex items-center gap-1.5"
        >
          {index > 0 ? (
            <span className="text-ink-faint" aria-hidden>
              ·
            </span>
          ) : null}
          <PunchMark punch={punch} />
        </span>
      ))}
    </span>
  );
}

function PunchMark({ punch }: { punch: PunchRow }) {
  if (punch.punched_at) {
    // Desconsiderada continua visível: o motor a ignora, e esconder a marcação
    // esconderia a curadoria feita na origem.
    return punch.disregarded ? (
      <span className="text-ink-faint line-through" title="Desconsiderada">
        {formatTime(punch.punched_at)}
      </span>
    ) : (
      <span className="text-ink">{formatTime(punch.punched_at)}</span>
    );
  }

  if (punch.status_label) {
    return (
      <span className="text-ink-muted font-sans text-xs">
        {punch.status_label}
      </span>
    );
  }

  // Previsto sem marcação é o sinal de batida faltante, e ele tem cara própria.
  return (
    <span
      className="text-alert font-bold"
      title={`Previsto ${formatTime(punch.expected_time) ?? ""} e sem marcação`}
    >
      —
    </span>
  );
}

function mergeByDay(workdays: WorkdayRow[], punches: PunchRow[]): DayLine[] {
  const lines = new Map<string, DayLine>();

  for (const workday of workdays) {
    lines.set(workday.reference_date, {
      date: workday.reference_date,
      workday,
      punches: [],
    });
  }

  for (const punch of punches) {
    const line = lines.get(punch.reference_date) ?? {
      date: punch.reference_date,
      workday: null,
      punches: [],
    };
    line.punches.push(punch);
    lines.set(punch.reference_date, line);
  }

  return [...lines.values()].sort((a, b) => b.date.localeCompare(a.date));
}

function dayLabel(day: WorkdayRow) {
  const label = DAY_TYPE_LABEL[day.day_type] ?? day.day_type;

  if (label) {
    return <span className="text-ink-faint font-sans text-xs">{label}</span>;
  }

  const expected = formatTime(day.expected_entry);

  // Escala não confirmada é estado de primeira classe: aparece como selo, não
  // vira desvio silencioso.
  if (day.confidence < CONFIDENCE_THRESHOLD) {
    return (
      <span className="flex flex-col items-start gap-1">
        <span>{expected}</span>
        <Chip>escala não confirmada</Chip>
      </span>
    );
  }

  return expected;
}
