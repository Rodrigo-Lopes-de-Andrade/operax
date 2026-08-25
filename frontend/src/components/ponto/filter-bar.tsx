import { TriangleAlert, X } from "lucide-react";
import Link from "next/link";

import { Card } from "@/components/ui/kpi-card";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { SelectNav, type SelectGroup } from "@/components/ui/select-nav";
import {
  PERIODS,
  PERIOD_LABEL,
  type PontoFilters,
  type Period,
} from "@/lib/ponto/filters";
import { formatRange } from "@/lib/ponto/format";
import type { PontoScreen } from "@/lib/ponto/queries";
import { PONTO_PATH, pontoHref, type Paging } from "@/lib/ponto/url";

const PERIOD_OPTIONS = PERIODS.map((period) => ({
  value: period,
  label: PERIOD_LABEL[period],
}));

/**
 * The cut. Company, unit and period — the three filters the public surface can
 * actually answer.
 *
 * There is no "Aplicar": every control is a link, so the cut is applied by
 * navigating, and the URL is always the truth. The link printed underneath is
 * the same one that leaves in the WhatsApp alert, which is why it is on screen
 * and not hidden behind a share button.
 */
export function FilterBar({
  screen,
  filters,
  paging,
}: {
  screen: PontoScreen;
  filters: PontoFilters;
  paging: Paging;
}) {
  const companies = [
    ...new Map(screen.units.map((unit) => [unit.companySlug, unit])).values(),
  ];

  const companyGroups: SelectGroup[] = [
    {
      label: "Empresas",
      options: companies.map((unit) => ({
        value: unit.companySlug,
        label: unit.companyName,
        href: pontoHref(filters, paging, {
          companySlug: unit.companySlug,
          unitCode: null,
          eventId: null,
        }),
      })),
    },
  ];

  const unitGroups: SelectGroup[] = companies.map((company) => ({
    label: company.companyName,
    options: screen.units
      .filter((unit) => unit.companySlug === company.companySlug)
      .map((unit) => ({
        value: unit.slug,
        label: unit.name,
        href: pontoHref(filters, paging, {
          unitCode: unit.slug,
          companySlug: unit.companySlug,
          eventId: null,
        }),
      })),
  }));

  const cleared = pontoHref(filters, paging, {
    companySlug: null,
    unitCode: null,
    eventId: null,
  });

  const currentHref = pontoHref(filters, paging, { eventId: null });
  const hasFilter = Boolean(filters.unitCode || filters.companySlug);

  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-wrap items-end gap-4">
          <SelectNav
            label="Empresa"
            placeholder="Todas as empresas"
            placeholderHref={pontoHref(filters, paging, {
              companySlug: null,
              unitCode: null,
              eventId: null,
            })}
            value={filters.companySlug ?? ""}
            groups={companyGroups}
          />
          <SelectNav
            label="Unidade"
            placeholder="Todas as unidades"
            placeholderHref={pontoHref(filters, paging, {
              unitCode: null,
              eventId: null,
            })}
            value={filters.unitCode ?? ""}
            groups={unitGroups}
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <SegmentedControl<Period>
            label="Período"
            options={PERIOD_OPTIONS}
            value={filters.period}
            hrefFor={(period) =>
              pontoHref(filters, paging, { period, eventId: null })
            }
          />
          {hasFilter ? (
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
        {screen.company ? (
          <Chip
            label={screen.company.name}
            removeHref={pontoHref(filters, paging, {
              companySlug: null,
              eventId: null,
            })}
          />
        ) : null}
        {screen.unit ? (
          <Chip
            label={screen.unit.name}
            removeHref={pontoHref(filters, paging, {
              unitCode: null,
              eventId: null,
            })}
          />
        ) : null}
        {screen.unknownUnit || screen.unknownCompany ? (
          <span className="bg-alert-bg text-alert text-2xs inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-bold">
            <TriangleAlert size={13} aria-hidden />
            {screen.unknownUnit
              ? `Unidade "${screen.unknownUnit}" não encontrada`
              : `Empresa "${screen.unknownCompany}" não encontrada`}
          </span>
        ) : null}
      </div>

      <p className="text-ink-faint truncate font-mono text-xs">
        {currentHref === PONTO_PATH
          ? `${PONTO_PATH} · recorte padrão`
          : currentHref}
      </p>
    </Card>
  );
}

function Chip({ label, removeHref }: { label: string; removeHref?: string }) {
  return (
    <span className="bg-brand-soft/40 text-brand-strong text-2xs inline-flex items-center gap-1.5 rounded-full py-1 pr-1.5 pl-2.5 font-bold">
      {label}
      {removeHref ? (
        <Link
          href={removeHref}
          aria-label={`Remover filtro ${label}`}
          className="hover:bg-brand-soft flex size-4 items-center justify-center rounded-full"
        >
          <X size={11} aria-hidden />
        </Link>
      ) : null}
    </span>
  );
}
