import { CheckCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Pagination } from "@/components/ui/pagination";
import { SignedMinutes } from "@/components/ui/signed-minutes";
import { Table, type Column, type Row } from "@/components/ui/table";
import type { PontoFilters } from "@/lib/ponto/filters";
import {
  formatDayShort,
  formatNumber,
  formatTime,
  formatWeekday,
} from "@/lib/ponto/format";
import type { PontoScreen } from "@/lib/ponto/queries";
import { pontoHref, type PageSize, type Paging } from "@/lib/ponto/url";

const COLUMNS: Column[] = [
  { key: "observado", label: "Observado", width: "112px", noWrap: true },
  { key: "colaborador", label: "Colaborador" },
  { key: "tipo", label: "Tipo de desvio" },
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
    width: "104px",
  },
  {
    key: "minutos",
    label: "Minutos",
    align: "right",
    numeric: true,
    width: "148px",
  },
  {
    key: "situacao",
    label: "Situação",
    align: "right",
    width: "176px",
    noWrap: true,
  },
];

export function OccurrencesCard({
  screen,
  filters,
  paging,
}: {
  screen: PontoScreen;
  filters: PontoFilters;
  paging: Paging;
}) {
  const pageCount = Math.max(
    Math.ceil(screen.occurrenceTotal / paging.pageSize),
    1,
  );

  const rows: Row[] = screen.occurrences.map((occurrence) => ({
    id: occurrence.eventoId,
    href: pontoHref(filters, paging, { eventId: occurrence.eventoId }),
    cells: {
      observado: (
        <span className="flex flex-col">
          <span className="text-ink font-bold">
            {formatDayShort(occurrence.referenceDate)}
          </span>
          <span className="text-ink-faint text-xs">
            {formatWeekday(occurrence.referenceDate)}
          </span>
        </span>
      ),
      colaborador: (
        <span className="flex flex-col">
          <span className="text-ink font-semibold">
            {occurrence.employeeName}
          </span>
          <span className="text-ink-faint text-xs">
            {occurrence.unitName ?? "Sem unidade"}
          </span>
        </span>
      ),
      tipo: <span className="text-ink-body">{occurrence.typeDescription}</span>,
      previsto: formatTime(occurrence.expectedTime),
      registrado: formatTime(occurrence.actualTime) ?? (
        <span className="text-ink-faint font-sans text-xs">
          ainda não registrada
        </span>
      ),
      minutos: (
        <SignedMinutes
          minutes={occurrence.minutes}
          direction={occurrence.direction}
          size="sm"
        />
      ),
      situacao: occurrence.pendenteDeCiclo ? (
        <Badge tone="alert" dot>
          Pendente de ciclo
        </Badge>
      ) : (
        <Badge tone="good" dot>
          Em relatório
        </Badge>
      ),
    },
  }));

  return (
    <Card>
      <CardHeader
        eyebrow="Ocorrências"
        title={`${formatNumber(screen.occurrenceTotal)} no recorte`}
        note="Clique numa linha para ver o indício."
      />

      <Table
        columns={COLUMNS}
        rows={rows}
        caption="Ocorrências de desvio no recorte"
        empty={
          <div className="px-5">
            <EmptyState
              icon={CheckCheck}
              tone="good"
              title="Nenhuma ocorrência no recorte"
              description="Todas as jornadas do período ficaram dentro do previsto para as unidades que você acompanha."
            />
          </div>
        }
      />

      {screen.occurrenceTotal > 0 ? (
        <Pagination
          page={paging.page}
          pageCount={pageCount}
          total={screen.occurrenceTotal}
          pageSize={paging.pageSize}
          hrefForPage={(page) =>
            pontoHref(filters, paging, { page, eventId: null })
          }
          hrefForSize={(pageSize: PageSize) =>
            pontoHref(filters, paging, { pageSize, eventId: null })
          }
        />
      ) : null}

      {/* Frase fixa, não decorativa: o OperaX aponta indício, quem apura é o
          sistema de ponto. É o que separa gestão de exposição trabalhista. */}
      <p className="text-ink-faint border-line-subtle border-t px-5 py-3 text-xs">
        Registro oficial de jornada permanece no Secullum. O OperaX aponta
        indícios.
      </p>
    </Card>
  );
}
