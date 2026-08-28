import { TriangleAlert } from "lucide-react";
import Link from "next/link";

import { Card } from "@/components/ui/kpi-card";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { SelectNav, type SelectGroup } from "@/components/ui/select-nav";
import type { PendingScreen } from "@/lib/justificativas/queries";
import {
  justificativasHref,
  type PendingFilters,
} from "@/lib/justificativas/url";
import { PERIODS, PERIOD_LABEL, type Period } from "@/lib/ponto/filters";
import { formatRange } from "@/lib/ponto/format";
import type { Paging } from "@/lib/ponto/url";

const PERIOD_OPTIONS = PERIODS.map((period) => ({
  value: period,
  label: PERIOD_LABEL[period],
}));

/**
 * O recorte da fila: unidade e período, e mais nada.
 *
 * Não há seletor de empresa porque `fn_pending_justification` não recebe
 * empresa — as unidades continuam agrupadas por ela no seletor, que é onde a
 * empresa ajuda a achar a unidade sem prometer um filtro que a função não faz.
 */
export function PendingBar({
  screen,
  filters,
  paging,
}: {
  screen: PendingScreen;
  filters: PendingFilters;
  paging: Paging;
}) {
  const companies = [
    ...new Map(screen.units.map((unit) => [unit.companySlug, unit])).values(),
  ];

  const unitGroups: SelectGroup[] = companies.map((company) => ({
    label: company.companyName,
    options: screen.units
      .filter((unit) => unit.companySlug === company.companySlug)
      .map((unit) => ({
        value: unit.slug,
        label: unit.name,
        href: justificativasHref(filters, paging, {
          unitCode: unit.slug,
          eventId: null,
        }),
      })),
  }));

  const cleared = justificativasHref(filters, paging, {
    unitCode: null,
    eventId: null,
  });

  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <SelectNav
          label="Unidade"
          placeholder="Todas as unidades"
          placeholderHref={cleared}
          value={filters.unitCode ?? ""}
          groups={unitGroups}
        />

        <div className="flex flex-wrap items-center gap-3">
          <SegmentedControl<Period>
            label="Período"
            options={PERIOD_OPTIONS}
            value={filters.period}
            hrefFor={(period) =>
              justificativasHref(filters, paging, { period, eventId: null })
            }
          />
          {filters.unitCode ? (
            <Link
              href={cleared}
              className="text-ink-muted hover:text-ink text-xs font-bold underline underline-offset-4"
            >
              Limpar
            </Link>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Chip label={formatRange(screen.range.de, screen.range.ate)} />
        {screen.unit ? <Chip label={screen.unit.name} /> : null}
        {screen.unknownUnit ? (
          <span className="bg-alert-bg text-alert text-2xs inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-bold">
            <TriangleAlert size={13} aria-hidden />
            {`Unidade "${screen.unknownUnit}" não encontrada`}
          </span>
        ) : null}
      </div>
    </Card>
  );
}

function Chip({ label }: { label: string }) {
  return (
    <span className="bg-brand-soft/40 text-brand-strong text-2xs inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-bold">
      {label}
    </span>
  );
}
