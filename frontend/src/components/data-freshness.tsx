import { CircleAlert, Clock } from "lucide-react";

import { loadFreshness } from "@/lib/freshness";
import { formatAge, formatClock } from "@/lib/ponto/format";

/**
 * The age of the data, permanently on the chrome. Never a tooltip, never an
 * icon on its own: what the screen shows is a picture taken at a known time,
 * and the manager decides with that in mind.
 */
export async function DataFreshness() {
  const freshness = await loadFreshness();

  if (!freshness) {
    return (
      <span className="flex items-center gap-2 rounded-full bg-white/10 px-3.5 py-2 text-xs font-semibold text-white/70">
        <Clock size={14} aria-hidden />
        Sem leitura registrada
      </span>
    );
  }

  const Icon = freshness.isStale ? CircleAlert : Clock;

  return (
    <span
      className={`flex items-center gap-2 rounded-full px-3.5 py-2 text-xs font-semibold ${
        freshness.isStale
          ? "bg-alert-bg text-alert"
          : "bg-white/10 text-on-chrome"
      }`}
    >
      <Icon size={14} aria-hidden />
      <span className="tabular-nums">
        Dados de {formatClock(freshness.lastSyncAt)} ·{" "}
        {formatAge(freshness.ageMinutes)}
      </span>
      {freshness.isStale ? <span className="font-bold">atrasado</span> : null}
    </span>
  );
}
