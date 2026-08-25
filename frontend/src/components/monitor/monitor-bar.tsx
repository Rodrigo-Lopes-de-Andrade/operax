import { ChevronLeft, ChevronRight, TriangleAlert } from "lucide-react";
import Link from "next/link";

import { Card } from "@/components/ui/kpi-card";
import { SelectNav, type SelectGroup } from "@/components/ui/select-nav";
import { monitorHref, shiftDay, MONITOR_PATH } from "@/lib/monitor/url";
import type { MonitorScreen } from "@/lib/monitor/queries";
import { formatDayLong, formatWeekday } from "@/lib/ponto/format";

/**
 * Day and unit — the whole cut of the monitor.
 *
 * The day steps by link, like everything else on this product: the cut lives in
 * the URL so the manager can send "olha ontem no Aeroporto" to a colleague and
 * have it open on the same screen. Forward past today is not a disabled button,
 * it is absent — a control that exists and refuses is a small lie about what
 * the product can do.
 */
export function MonitorBar({ screen }: { screen: MonitorScreen }) {
  const { filters, today, units } = screen;
  const isToday = filters.day === today;
  const previous = shiftDay(filters.day, -1);
  const next = shiftDay(filters.day, 1);

  const companies = [...new Set(units.map((unit) => unit.companyName))];
  const unitGroups: SelectGroup[] = companies.map((company) => ({
    label: company,
    options: units
      .filter((unit) => unit.companyName === company)
      .map((unit) => ({
        value: unit.slug,
        label: unit.name,
        href: monitorHref(filters, today, { unitCode: unit.slug }),
      })),
  }));

  const currentHref = monitorHref(filters, today);

  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-wrap items-end gap-4">
          <SelectNav
            label="Unidade"
            placeholder="Todas as unidades"
            placeholderHref={monitorHref(filters, today, { unitCode: null })}
            value={filters.unitCode ?? ""}
            groups={unitGroups}
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div
            role="group"
            aria-label="Dia observado"
            className="bg-muted border-line-subtle flex items-center gap-1 rounded-full border p-0.5"
          >
            <Step
              href={monitorHref(filters, today, { day: previous })}
              label="Dia anterior"
              icon={<ChevronLeft size={15} aria-hidden />}
            />
            <span className="text-ink px-2 text-xs font-bold">
              {formatWeekday(filters.day)}, {formatDayLong(filters.day)}
            </span>
            {isToday ? (
              <span className="w-8" aria-hidden />
            ) : (
              <Step
                href={monitorHref(filters, today, { day: next })}
                label="Próximo dia"
                icon={<ChevronRight size={15} aria-hidden />}
              />
            )}
          </div>

          {isToday ? null : (
            <Link
              href={monitorHref(filters, today, { day: today })}
              className="text-brand-strong text-xs font-bold underline underline-offset-4"
            >
              Voltar para hoje
            </Link>
          )}
        </div>
      </div>

      {screen.unknownUnit ? (
        <span className="bg-alert-bg text-alert text-2xs inline-flex w-fit items-center gap-1.5 rounded-full px-2.5 py-1 font-bold">
          <TriangleAlert size={13} aria-hidden />
          Unidade &quot;{screen.unknownUnit}&quot; não encontrada
        </span>
      ) : null}

      <p className="text-ink-faint truncate font-mono text-xs">
        {currentHref === MONITOR_PATH
          ? `${MONITOR_PATH} · hoje, todas as unidades`
          : currentHref}
      </p>
    </Card>
  );
}

function Step({
  href,
  label,
  icon,
}: {
  href: string;
  label: string;
  icon: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-label={label}
      className="text-ink-muted hover:bg-card hover:text-ink flex size-8 items-center justify-center rounded-full transition-colors"
    >
      {icon}
    </Link>
  );
}
