import { CheckCheck, TriangleAlert } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Rankbar, type RankbarItem } from "@/components/ui/rankbar";
import { colaboradorHref } from "@/lib/colaborador/url";
import { formatNumber } from "@/lib/ponto/format";
import type { PontoScreen } from "@/lib/ponto/queries";

/**
 * The three rankings the handoff asks for — unit, employee and manager — plus
 * recurrence. The manager one arrived last, with migration 27, and it does not
 * come from `employee.manager_employee_id`: that column points at an employee
 * record and nothing can fill it. It comes from `app.manager`, promoted from
 * the mirror's `Estrutura`, which is where the Secullum actually keeps who
 * somebody answers to.
 *
 * ⚠️ VOLUME SEGUE EFETIVO, E O TOPO DA LISTA NÃO É "O PIOR GESTOR"
 * Quem tem vinte pessoas acumula mais ocorrência que quem tem três, e ordenar
 * por contagem põe o maior time em primeiro por aritmética. Por isso cada linha
 * carrega o número de pessoas ao lado: sem ele, a tela faria uma afirmação sobre
 * desempenho que o dado não sustenta — e sobre alguém com nome.
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
      href: colaboradorHref(row.employee_id),
    })) ?? [];

  const managerItems: RankbarItem[] =
    screen.managerRanking?.map((row) => ({
      // `manager_id` nulo é linha legítima: o espelho não diz a quem essa gente
      // responde. Escondê-la faria as ocorrências dela sumirem do recorte por
      // gestor sem aparecer como zero em lugar nenhum.
      key: row.manager_id ?? "sem-gestor",
      label: row.manager_name ?? "Sem gestor",
      value: row.eventos,
      display: `${formatNumber(row.eventos)} · ${formatNumber(row.colaboradores)} ${
        row.colaboradores === 1 ? "pessoa" : "pessoas"
      }`,
    })) ?? [];

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <RankCard
        title="Unidades com mais ocorrências"
        failed={screen.unitRanking === null}
        items={unitItems}
      />
      <RankCard
        title="Gestores com mais ocorrências"
        note="Ordenado por volume — o número de pessoas está ao lado"
        failed={screen.managerRanking === null}
        items={managerItems}
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
  note,
  items,
  failed,
}: {
  title: string;
  note?: string;
  items: RankbarItem[];
  failed: boolean;
}) {
  return (
    <Card>
      <CardHeader title={title} note={note} />
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
                  <Link
                    href={colaboradorHref(row.employee_id)}
                    className="text-ink-body hover:text-brand-strong block truncate text-sm font-semibold underline-offset-4 hover:underline"
                  >
                    {row.employee_name}
                  </Link>
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
