import { CheckCheck } from "lucide-react";

import { Chip } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { SignedMinutes } from "@/components/ui/signed-minutes";
import { Table, type Column, type Row } from "@/components/ui/table";
import type { WorkdayRow } from "@/lib/colaborador/queries";
import { formatDayShort, formatTime, formatWeekday } from "@/lib/ponto/format";

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
  {
    key: "registrado",
    label: "Registrado",
    mono: true,
    numeric: true,
    width: "120px",
  },
  { key: "desvio", label: "Desvio", align: "right" },
];

/**
 * The day-by-day of the period.
 *
 * The handoff shows a "Marcações" column with the raw punch sequence
 * ("06:58 · 12:30 · 13:47 · —"). It is not here because there are no punches
 * yet: the mirror is empty until the sync exists, and a column of dashes would
 * read as "this person did not clock in". What the engine did observe — expected
 * against recorded — is shown instead.
 */
export function WorkdayHistory({ workdays }: { workdays: WorkdayRow[] }) {
  const rows: Row[] = workdays.map((day) => ({
    id: day.reference_date,
    cells: {
      dia: (
        <span className="flex flex-col">
          <span className="text-ink font-bold">
            {formatDayShort(day.reference_date)}
          </span>
          <span className="text-ink-faint text-xs">
            {formatWeekday(day.reference_date)}
          </span>
        </span>
      ),
      previsto: dayLabel(day),
      registrado: formatTime(day.actual_time),
      desvio: day.deviation_type ? (
        <span className="flex flex-col items-end gap-1">
          <SignedMinutes
            minutes={day.minutes ?? 0}
            direction={day.direction ?? "neutral"}
            size="sm"
          />
          <span className="text-ink-faint text-xs">
            {day.deviation_description}
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
        note="Marcações brutas entram com a sincronização da origem."
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
