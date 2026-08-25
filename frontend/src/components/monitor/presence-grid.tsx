import { KpiCard } from "@/components/ui/kpi-card";
import type { DailyMonitor } from "@/lib/monitor/queries";
import { formatNumber } from "@/lib/ponto/format";

/**
 * Presence of the day, by the numbers.
 *
 * "Sem indício" is the one figure on this product that could be read as
 * something it is not, so the caveat travels with it instead of living in a
 * tooltip: punches are not mirrored into the OperaX schema, so the monitor
 * knows what the engine found, never who walked through the door.
 */
export function PresenceGrid({ monitor }: { monitor: DailyMonitor }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard
        eyebrow="Escalados hoje"
        value={formatNumber(monitor.scheduled)}
        note="Colaboradores com jornada prevista para o dia."
      />
      <KpiCard
        eyebrow="Com indício"
        value={formatNumber(monitor.with_indication)}
        note="Pessoas, não ocorrências: quem tem mais de um indício conta uma vez."
      />
      <KpiCard
        eyebrow="Sem indício"
        value={formatNumber(monitor.clear)}
        note="O que a última leitura não encontrou. Não é confirmação de presença."
      />
      <KpiCard
        eyebrow="Fora da escala"
        value={formatNumber(monitor.off_roster)}
        note="Folga, férias ou afastamento. O quadro acima abre os três."
      />
    </div>
  );
}
