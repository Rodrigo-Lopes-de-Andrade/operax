import { CheckCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { SignedMinutes } from "@/components/ui/signed-minutes";
import { Table, type Column, type Row } from "@/components/ui/table";
import { colaboradorHref } from "@/lib/colaborador/url";
import type { DailyMonitor, MonitorRow, Severity } from "@/lib/monitor/queries";
import { formatClock, formatNumber, formatTime } from "@/lib/ponto/format";

const COLUMNS: Column[] = [
  { key: "colaborador", label: "Colaborador" },
  { key: "tipo", label: "O que a leitura encontrou" },
  {
    key: "previsto",
    label: "Previsto",
    mono: true,
    numeric: true,
    width: "96px",
  },
  {
    key: "registrado",
    label: "Registrado",
    mono: true,
    numeric: true,
    width: "112px",
  },
  {
    key: "minutos",
    label: "Minutos",
    align: "right",
    numeric: true,
    width: "140px",
  },
  {
    key: "leitura",
    label: "Detectado",
    align: "right",
    numeric: true,
    width: "104px",
  },
];

/**
 * Urgency is carried by grouping and by order, not by a third colour scale.
 *
 * The palette already spends hue on one thing — the direction of the deviation,
 * teal against burnt orange — and a second hue axis on the same table would
 * make both unreadable. Three headings with their own counts say what colour
 * would have said, and say it to somebody reading the screen in the sun.
 */
const GROUPS: {
  severity: Severity;
  title: string;
  note: string;
  urgent?: boolean;
}[] = [
  {
    severity: "critical",
    title: "Agora",
    note: "Posto sem ninguém neste momento, segundo a última leitura.",
    urgent: true,
  },
  {
    severity: "attention",
    title: "Ainda hoje",
    note: "O dia já saiu do previsto e ainda dá tempo de tratar.",
  },
  {
    severity: "watch",
    title: "No fechamento",
    note: "Entra no relatório do ciclo. Não pede ação agora.",
  },
];

export function IndicationGroups({ monitor }: { monitor: DailyMonitor }) {
  if (monitor.rows.length === 0) {
    return (
      <Card>
        <CardHeader eyebrow="Indícios" title="Nada a tratar neste dia" />
        <EmptyState
          icon={CheckCheck}
          tone="good"
          title="Nenhum indício no dia"
          description="Até a última leitura, todas as jornadas previstas para as unidades que você acompanha estavam dentro do esperado."
        />
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {GROUPS.map((group) => {
        const rows = monitor.rows.filter(
          (row) => row.severity === group.severity,
        );

        if (rows.length === 0) {
          return null;
        }

        return (
          <Card key={group.severity}>
            <CardHeader
              eyebrow="Indícios"
              title={`${group.title} · ${formatNumber(rows.length)}`}
              note={group.note}
              action={
                group.urgent ? (
                  <Badge tone="alert" dot>
                    Exige ação
                  </Badge>
                ) : undefined
              }
            />
            <Table
              columns={COLUMNS}
              rows={rows.map(toRow)}
              density="compact"
              caption={`Indícios do dia — ${group.title}`}
            />
          </Card>
        );
      })}

      {monitor.truncated ? (
        <p className="text-ink-muted text-xs text-pretty">
          O dia tem mais indícios do que esta tela carrega de uma vez. Filtre
          por unidade para ver o restante — a contagem por unidade acima
          continua completa.
        </p>
      ) : null}

      <p className="text-ink-faint text-xs text-pretty">
        Registro oficial de jornada permanece no Secullum. O FastPark aponta
        indícios.
      </p>
    </div>
  );
}

function toRow(row: MonitorRow): Row {
  return {
    // A person can hold two indications on the same day, so the key is the pair.
    id: `${row.employee_id}:${row.type}`,
    href: colaboradorHref(row.employee_id),
    cells: {
      colaborador: (
        <span className="flex flex-col">
          <span className="text-ink font-semibold">{row.employee_name}</span>
          <span className="text-ink-faint text-xs">
            {row.unit_name ?? "Sem unidade"}
          </span>
        </span>
      ),
      tipo: (
        <span className="flex flex-col">
          <span className="text-ink-body">{row.type_description}</span>
          {row.day_type === null ? (
            <span className="text-ink-faint text-xs">
              Sem jornada prevista para o dia
            </span>
          ) : null}
        </span>
      ),
      previsto: formatTime(row.expected_time),
      registrado: formatTime(row.actual_time) ?? (
        <span className="text-ink-faint font-sans text-xs">sem marcação</span>
      ),
      minutos: (
        <SignedMinutes
          minutes={row.minutes}
          direction={row.direction}
          size="sm"
        />
      ),
      leitura: (
        <span className="text-ink-muted text-xs">
          {formatClock(row.detected_at)}
        </span>
      ),
    },
  };
}
