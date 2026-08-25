import { ChartColumnBig, TriangleAlert } from "lucide-react";

import { ChartDiverging } from "@/components/ui/chart-diverging";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { formatRange } from "@/lib/ponto/format";
import type { PontoScreen } from "@/lib/ponto/queries";

/**
 * The trend is context, not cut: it always looks back the same 14 days ending
 * on the last day of the period, so switching to "hoje" does not collapse the
 * chart into a single bar with nothing to compare against.
 */
export function TrendCard({ screen }: { screen: PontoScreen }) {
  const scope =
    screen.unit?.name ?? screen.company?.name ?? "todas as unidades";

  return (
    <Card>
      <CardHeader
        eyebrow="Tendência diária"
        title="Minutos de desvio por dia"
        note={`${formatRange(screen.trendRange.de, screen.trendRange.ate)} · ${scope}`}
      />
      <div className="px-5 py-5">
        {screen.trend === null ? (
          <EmptyState
            icon={TriangleAlert}
            tone="alert"
            compact
            title="Não foi possível carregar a tendência"
            description="Os demais blocos da tela continuam válidos. Recarregue para tentar de novo."
          />
        ) : screen.trend.every(
            (day) => day.surplus === 0 && day.shortfall === 0,
          ) ? (
          <EmptyState
            icon={ChartColumnBig}
            tone="good"
            compact
            title="Nenhum desvio nos últimos 14 dias"
            description="Todas as jornadas do recorte ficaram dentro do previsto."
          />
        ) : (
          <ChartDiverging data={screen.trend} />
        )}
      </div>
    </Card>
  );
}
