import { ClipboardCheck } from "lucide-react";

import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Pagination } from "@/components/ui/pagination";
import { Table, type Column, type Row } from "@/components/ui/table";
import type { PendingScreen } from "@/lib/justificativas/queries";
import {
  justificativasHref,
  type PendingFilters,
} from "@/lib/justificativas/url";
import {
  formatDayShort,
  formatDuration,
  formatNumber,
  formatWeekday,
} from "@/lib/ponto/format";
import type { PageSize, Paging } from "@/lib/ponto/url";

const COLUMNS: Column[] = [
  { key: "observado", label: "Observado", width: "112px", noWrap: true },
  { key: "colaborador", label: "Colaborador" },
  { key: "tipo", label: "Tipo de desvio" },
  {
    key: "desvio",
    label: "Desvio",
    align: "right",
    numeric: true,
    width: "120px",
  },
];

/**
 * A fila. Cada linha abre o mesmo detalhe da gestão de ponto, e é lá que o
 * veredito é dado: quem decide precisa do previsto e do registrado lado a lado,
 * e eles não cabem — nem deveriam caber — numa linha de lista.
 *
 * Não há coluna de detecção. `formatClock` dá HH:MM, e numa fila de 30 dias uma
 * hora sem dia não responde nada — quanto tempo o indício está parado sai da
 * primeira coluna, que é o dia em que ele aconteceu.
 *
 * ⚠️ A coluna é "Desvio" e traz magnitude, não valor com sinal.
 * `fn_pending_justification` devolve `minutes` e não devolve `direction`, que é
 * propriedade do TIPO e não do sinal do número (`late_entry` é `shortfall`).
 * Deduzir a direção do sinal aqui seria a tela afirmando o que o dado não diz —
 * o detalhe, a um clique, mostra o valor assinado com a direção verdadeira.
 */
export function PendingCard({
  screen,
  filters,
  paging,
}: {
  screen: PendingScreen;
  filters: PendingFilters;
  paging: Paging;
}) {
  const pageCount = Math.max(Math.ceil(screen.total / paging.pageSize), 1);

  const rows: Row[] = screen.rows.map((pending) => ({
    id: pending.deviation_event_id,
    href: justificativasHref(filters, paging, {
      eventId: pending.deviation_event_id,
    }),
    cells: {
      observado: (
        <span className="flex flex-col">
          <span className="text-ink font-bold">
            {formatDayShort(pending.reference_date)}
          </span>
          <span className="text-ink-faint text-xs">
            {formatWeekday(pending.reference_date)}
          </span>
        </span>
      ),
      colaborador: (
        <span className="flex flex-col">
          <span className="text-ink font-semibold">
            {pending.employee_name}
          </span>
          <span className="text-ink-faint text-xs">
            {pending.unit_name ?? "Sem unidade"}
          </span>
        </span>
      ),
      tipo: <span className="text-ink-body">{pending.type_description}</span>,
      desvio: (
        <span className="text-ink font-semibold tabular-nums">
          {formatDuration(pending.minutes)}
        </span>
      ),
    },
  }));

  return (
    <Card>
      <CardHeader
        eyebrow="Pendentes"
        title={`${formatNumber(screen.total)} sem justificativa aceita`}
        note="Clique numa linha para ver o indício e registrar o veredito."
      />

      <Table
        columns={COLUMNS}
        rows={rows}
        caption="Ocorrências pendentes de justificativa no recorte"
        empty={
          <div className="px-5">
            {/* Fila vazia tem DUAS causas, e o tom bom só serve para uma delas.
                `requires_justification` nasce false para todo tipo (migration
                23), então um cliente que ainda não ligou a política vê zero
                aqui para sempre. Dizer só "está tudo justificado" seria a tela
                afirmando curadoria que talvez nunca tenha existido. */}
            <EmptyState
              icon={ClipboardCheck}
              tone="good"
              title="Nada esperando justificativa no recorte"
              description="Todo indício do período já tem uma justificativa aceita — ou nenhum tipo de desvio exige justificativa neste cliente ainda, política que nasce desligada e é ligada por tipo."
            />
          </div>
        }
      />

      {screen.total > 0 ? (
        <Pagination
          page={paging.page}
          pageCount={pageCount}
          total={screen.total}
          pageSize={paging.pageSize}
          label="pendentes"
          hrefForPage={(page) =>
            justificativasHref(filters, paging, { page, eventId: null })
          }
          hrefForSize={(pageSize: PageSize) =>
            justificativasHref(filters, paging, { pageSize, eventId: null })
          }
        />
      ) : null}

      <p className="text-ink-faint border-line-subtle border-t px-5 py-3 text-xs">
        Registro oficial de jornada permanece no Secullum. O FastPark aponta
        indícios.
      </p>
    </Card>
  );
}
