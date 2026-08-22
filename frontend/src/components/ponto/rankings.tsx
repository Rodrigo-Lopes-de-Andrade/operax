import { CheckCheck, TriangleAlert } from "lucide-react";

import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Rankbar, type RankbarItem } from "@/components/ui/rankbar";
import { formatNumber } from "@/lib/ponto/format";
import type { PontoScreen } from "@/lib/ponto/queries";

/**
 * Three rankings in the handoff — unit, employee and manager. The manager one
 * is not here: the public surface exposes the manager's name on `vw_employee`
 * but no aggregate answers by manager, and inventing one would mean a new
 * object in `public`. Two rankings plus recurrence, and the gap named.
 */
export function Rankings({ screen }: { screen: PontoScreen }) {
  const unitItems: RankbarItem[] =
    screen.unitRanking?.map((row) => ({
      key: row.unit_id ?? row.unit_name,
      label: row.unit_name ?? "Sem unidade",
      value: row.eventos,
      display: `${formatNumber(row.eventos)} · ${formatNumber(row.minutes_abs)} min`,
    })) ?? [];

  const employeeItems: RankbarItem[] =
    screen.employeeRanking?.map((row) => ({
      key: row.employee_id,
      label: row.employee_name,
      value: row.eventos,
      display: `${formatNumber(row.eventos)} · ${formatNumber(row.minutes_abs)} min`,
    })) ?? [];

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <RankCard
        title="Unidades com mais ocorrências"
        failed={screen.unitRanking === null}
        items={unitItems}
      />
      <RankCard
        title="Colaboradores com mais ocorrências"
        failed={screen.employeeRanking === null}
        items={employeeItems}
      />
      <RecurrenceCard screen={screen} />
    </div>
  );
}

function RankCard({
  title,
  items,
  failed,
}: {
  title: string;
  items: RankbarItem[];
  failed: boolean;
}) {
  return (
    <Card>
      <CardHeader title={title} />
      <div className="px-5 py-5">
        {failed ? (
          <EmptyState
            icon={TriangleAlert}
            tone="alert"
            compact
            title="Não foi possível carregar"
            description="Recarregue a página para tentar de novo."
          />
        ) : items.length === 0 ? (
          <EmptyState
            icon={CheckCheck}
            tone="good"
            compact
            title="Nada a ranquear"
            description="Nenhuma ocorrência no recorte."
          />
        ) : (
          <Rankbar items={items} />
        )}
      </div>
    </Card>
  );
}

/**
 * Deviation on three or more distinct days in the window. It is the signal that
 * separates a bad day from a pattern, which is the only one worth a
 * conversation with the manager.
 */
function RecurrenceCard({ screen }: { screen: PontoScreen }) {
  return (
    <Card>
      <CardHeader
        title="Recorrência"
        note="Desvio em 3 dias ou mais dentro do recorte"
      />
      <div className="px-5 py-5">
        {screen.recurrence === null ? (
          <EmptyState
            icon={TriangleAlert}
            tone="alert"
            compact
            title="Não foi possível carregar"
            description="Recarregue a página para tentar de novo."
          />
        ) : screen.recurrence.length === 0 ? (
          <EmptyState
            icon={CheckCheck}
            tone="good"
            compact
            title="Nenhuma recorrência"
            description="Ninguém acumulou desvio em três dias distintos no período."
          />
        ) : (
          <ul className="flex flex-col gap-3">
            {screen.recurrence.slice(0, 6).map((row) => (
              <li
                key={row.employee_id}
                className="flex items-baseline justify-between gap-3"
              >
                <span className="min-w-0">
                  {/* Sem link: a consulta individual é outra tela e ainda não
                      existe. Link que não leva a lugar nenhum é defeito. */}
                  <span className="text-ink-body block truncate text-sm font-semibold">
                    {row.employee_name}
                  </span>
                  <span className="text-ink-faint text-xs">
                    {row.unit_name ?? "Sem unidade"}
                  </span>
                </span>
                <span className="text-ink text-sm font-bold whitespace-nowrap tabular-nums">
                  {row.dias_com_desvio} dias · {row.eventos}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
