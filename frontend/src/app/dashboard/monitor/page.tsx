import { PlugZap } from "lucide-react";
import type { Metadata } from "next";

import { IndicationGroups } from "@/components/monitor/indication-groups";
import { MonitorBar } from "@/components/monitor/monitor-bar";
import { PresenceGrid } from "@/components/monitor/presence-grid";
import { RosterBand } from "@/components/monitor/roster-band";
import { UnitPresence } from "@/components/monitor/unit-presence";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { pageTitle } from "@/lib/brand";
import { loadMonitorScreen } from "@/lib/monitor/queries";
import { parseMonitorFilters } from "@/lib/monitor/url";
import { todayInTenantZone, type RawSearchParams } from "@/lib/ponto/filters";

export const metadata: Metadata = {
  title: pageTitle("Monitor diário"),
};

/**
 * Monitor diário — the day as it stands, by unit.
 *
 * The screen the manager keeps open, so its honesty matters more than its
 * density. The age of the reading is permanently on the chrome above, and the
 * one figure that could be misread — "sem indício" — carries its caveat in the
 * card rather than in a tooltip nobody hovers on a phone.
 */
export default async function MonitorDiarioPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const filters = parseMonitorFilters(await searchParams, todayInTenantZone());
  const screen = await loadMonitorScreen(filters);

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Operação
        </p>
        <h1 className="text-ink text-2xl font-extrabold">Monitor diário</h1>
      </header>

      <MonitorBar screen={screen} />

      {screen.monitor ? (
        <>
          <RosterBand monitor={screen.monitor} />
          <PresenceGrid monitor={screen.monitor} />
          <UnitPresence screen={screen} filters={filters} />
          <IndicationGroups monitor={screen.monitor} />
        </>
      ) : (
        <Card>
          {/* An unreachable API and a day with nothing on it must never look
              alike here: an empty monitor reads as "está tudo certo". */}
          <EmptyState
            icon={PlugZap}
            tone="alert"
            title="O monitor não conseguiu ler o dia"
            description="A situação do dia vem da API do painel, e ela não respondeu agora. Isto não quer dizer que não há indícios — quer dizer que ninguém os leu. Recarregue em instantes."
          />
        </Card>
      )}
    </div>
  );
}
