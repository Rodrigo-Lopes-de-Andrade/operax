import { CircleAlert } from "lucide-react";

import { CompanyRollup } from "@/components/dp/company-rollup";
import { PanelAlerts } from "@/components/dp/panel-alerts";
import { PanelFilter } from "@/components/dp/panel-filter";
import { BenefitBreakdown, PanelKpis } from "@/components/dp/panel-kpis";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { formatDate } from "@/lib/dp/format";
import type {
  AlertsResult,
  CompanyChoice,
  CompanyRollupResult,
  PanelResult,
} from "@/lib/dp/queries";
import type { PanelFilters } from "@/lib/dp/url";
import type { UnitOption } from "@/lib/ponto/queries";

/**
 * O painel montado, com as duas metades que vêm por caminhos diferentes.
 *
 * ⛔ `forbidden` NÃO RENDERIZA NADA, E É ISSO QUE A REGRA 5 PEDE
 * Quem não alcança o domínio `compensation` recebe 403 do FastAPI, e aqui isso
 * vira ausência: nenhum cartão de dinheiro, nenhum cadeado, nenhum cinza,
 * nenhuma frase explicando o que ele não pode ver. O que sobra é o painel de
 * alertas do cadastro, que é a tela inteira de quem cuida de documento e ASO —
 * então não fica buraco no meio da página, fica uma página menor.
 *
 * ⚠️ `unavailable` RENDERIZA, E É O CONTRÁRIO DISSO
 * API fora do ar não é falta de permissão. As duas viram tela vazia em telas de
 * uma chamada só; aqui não podem, porque a metade de baixo continua respondendo
 * e um painel pela metade sem explicação seria lido como "a folha zerou".
 *
 * A ordem das seções é a do sistema atual (`ANEXO` §2a → §2e).
 */
export function PanelScreen({
  panel,
  alerts,
  rollup,
  filters,
  companies,
  units,
}: {
  panel: PanelResult;
  alerts: AlertsResult;
  /** `null` quando o consolidado não diz nada — ver a página. */
  rollup: CompanyRollupResult | null;
  filters: PanelFilters;
  companies: CompanyChoice[];
  units: UnitOption[];
}) {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Departamento pessoal
        </p>
        <h1 className="text-ink text-2xl font-extrabold">Painel de DP</h1>
        <p className="text-ink-muted mt-1 max-w-3xl text-sm text-pretty">
          {panel.status === "ok"
            ? `Posição de ${formatDate(panel.kpis.on)}. Os números mudam quando a sincronização roda, não enquanto esta tela está aberta.`
            : "Os contadores do cadastro são de hoje e mudam quando a sincronização roda, não enquanto esta tela está aberta."}
        </p>
      </header>

      <PanelFilter filters={filters} companies={companies} units={units} />

      {panel.status === "unavailable" ? (
        <Card className="p-6">
          <EmptyState
            icon={CircleAlert}
            tone="alert"
            title="Os indicadores de folha não puderam ser lidos"
            description="Eles vêm da API do painel, e ela não respondeu agora. Os alertas do cadastro abaixo vêm por outro caminho e continuam válidos."
          />
        </Card>
      ) : null}

      {panel.status === "ok" ? <PanelKpis kpis={panel.kpis} /> : null}

      <PanelAlerts alerts={alerts} />

      {panel.status === "ok" ? <BenefitBreakdown kpis={panel.kpis} /> : null}

      {panel.status === "ok" && rollup ? (
        <CompanyRollup
          rollup={rollup}
          basePayroll={panel.kpis.base_payroll}
          filters={filters}
        />
      ) : null}
    </div>
  );
}
