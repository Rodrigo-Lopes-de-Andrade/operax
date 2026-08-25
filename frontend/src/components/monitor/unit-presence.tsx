import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Table, type Column, type Row } from "@/components/ui/table";
import type { MonitorFilters } from "@/lib/monitor/url";
import { monitorHref } from "@/lib/monitor/url";
import type { MonitorScreen } from "@/lib/monitor/queries";
import { formatNumber } from "@/lib/ponto/format";

const COLUMNS: Column[] = [
  { key: "unidade", label: "Unidade" },
  {
    key: "escalados",
    label: "Escalados",
    align: "right",
    numeric: true,
    width: "104px",
  },
  {
    key: "indicio",
    label: "Com indício",
    align: "right",
    numeric: true,
    width: "116px",
  },
  {
    key: "limpo",
    label: "Sem indício",
    align: "right",
    numeric: true,
    width: "116px",
  },
  {
    key: "fora",
    label: "Fora da escala",
    align: "right",
    numeric: true,
    width: "132px",
  },
  { key: "barra", label: "Proporção", width: "180px" },
];

/**
 * Presence per unit — the answer to "onde eu olho primeiro".
 *
 * The bar is proportion, not count: a unit of six with two indications is in
 * worse shape than a unit of ninety with five, and a chart drawn on counts says
 * the opposite. The counts are right there in their own columns for whoever
 * needs the absolute number.
 *
 * A unit only ever appears here if the roster expected somebody in it, so this
 * is not the list of the tenant's units — it is the list of the units that had
 * a day today.
 */
export function UnitPresence({
  screen,
  filters,
}: {
  screen: MonitorScreen;
  filters: MonitorFilters;
}) {
  const units = screen.monitor?.units ?? [];

  const rows: Row[] = units.map((unit) => {
    const share =
      unit.scheduled > 0 ? unit.with_indication / unit.scheduled : 0;
    const option = screen.units.find((each) => each.unitId === unit.unit_id);

    return {
      id: unit.unit_id ?? "sem-unidade",
      href: option
        ? monitorHref(filters, screen.today, { unitCode: option.slug })
        : undefined,
      cells: {
        unidade: (
          <span className="text-ink font-semibold">
            {unit.unit_name ?? "Sem unidade"}
          </span>
        ),
        escalados: formatNumber(unit.scheduled),
        indicio: (
          <span
            className={unit.with_indication > 0 ? "text-ink font-bold" : ""}
          >
            {formatNumber(unit.with_indication)}
          </span>
        ),
        limpo: formatNumber(unit.clear),
        fora: formatNumber(unit.off_roster),
        barra: (
          <span className="flex items-center gap-2">
            <span
              className="bg-muted relative h-1.5 w-full overflow-hidden rounded-full"
              role="img"
              aria-label={`${Math.round(share * 100)}% dos escalados com indício`}
            >
              <span
                className="bg-shortfall absolute inset-y-0 left-0 rounded-full"
                style={{ width: `${Math.min(share * 100, 100)}%` }}
              />
            </span>
            <span className="text-ink-muted text-2xs w-9 shrink-0 text-right font-bold tabular-nums">
              {Math.round(share * 100)}%
            </span>
          </span>
        ),
      },
    };
  });

  return (
    <Card>
      <CardHeader
        eyebrow="Presença"
        title="Situação por unidade"
        note="A barra é a fatia dos escalados com pelo menos um indício."
      />
      <Table
        columns={COLUMNS}
        rows={rows}
        density="compact"
        caption="Situação do dia por unidade"
        empty={
          <p className="text-ink-muted px-5 py-8 text-center text-sm">
            Nenhuma unidade tinha jornada prevista neste dia.
          </p>
        }
      />
    </Card>
  );
}
