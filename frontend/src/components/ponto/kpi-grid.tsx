import { KpiCard } from "@/components/ui/kpi-card";
import {
  formatDuration,
  formatNumber,
  formatSignedMinutes,
} from "@/lib/ponto/format";
import type { PontoScreen } from "@/lib/ponto/queries";

/** How many low-weight counts the secondary strip shows. */
const STRIP_SIZE = 6;

export function KpiGrid({ screen }: { screen: PontoScreen }) {
  const { kpi } = screen;
  const total = kpi.minutes_excedente + kpi.minutes_faltante;
  const surplusShare = total === 0 ? 0 : (kpi.minutes_excedente / total) * 100;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 md:grid-cols-3">
        <KpiCard
          eyebrow="Ocorrências no recorte"
          value={formatNumber(kpi.eventos)}
          note={`${formatNumber(kpi.colaboradores_afetados)} colaboradores em ${formatNumber(
            kpi.unidades_afetadas,
          )} unidades`}
        />

        <KpiCard
          eyebrow="Minutos de desvio"
          value={formatDuration(kpi.minutes_abs)}
          note="Soma em módulo. As duas direções contam, e nenhuma delas é hora extra."
        >
          <div className="flex flex-col gap-2">
            <div className="bg-muted flex h-2 overflow-hidden rounded-full">
              <span
                className="bg-surplus h-full"
                style={{ width: `${surplusShare}%` }}
                aria-hidden
              />
              <span className="bg-shortfall h-full flex-1" aria-hidden />
            </div>
            <div className="flex flex-wrap gap-4">
              <span className="text-surplus text-xs font-bold tabular-nums">
                Excedente {formatSignedMinutes(kpi.minutes_excedente)}
              </span>
              <span className="text-shortfall text-xs font-bold tabular-nums">
                Faltante {formatSignedMinutes(-kpi.minutes_faltante)}
              </span>
            </div>
          </div>
        </KpiCard>

        {/* O desenho chama este cartão de "pendentes de justificativa". O número
            que a superfície pública responde é outro: ocorrência que ainda não
            entrou em ciclo de relatório — ninguém foi convidado a justificar
            ainda. O rótulo segue o dado. */}
        <KpiCard
          eyebrow="Pendentes de ciclo"
          value={formatNumber(kpi.eventos_pendentes_ciclo)}
          note="Ainda não entraram em um relatório enviado ao gestor."
        />
      </div>

      <TypeStrip screen={screen} />
    </div>
  );
}

function TypeStrip({ screen }: { screen: PontoScreen }) {
  if (!screen.byType) {
    return null;
  }

  if (screen.byTypeTruncated) {
    return (
      <p className="text-ink-faint text-xs">
        Contagem por tipo omitida: o recorte tem ocorrências demais para somar
        sem agregação no banco. Estreite o período ou a unidade.
      </p>
    );
  }

  const strip = screen.byType.slice(0, STRIP_SIZE);

  if (strip.length === 0) {
    return null;
  }

  return (
    <ul className="border-line-subtle bg-card grid gap-px overflow-hidden rounded-[14px] border sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {strip.map((entry) => (
        <li key={entry.type} className="bg-card px-4 py-3">
          <p className="text-ink text-lg font-extrabold tabular-nums">
            {formatNumber(entry.eventos)}
          </p>
          <p className="text-ink-muted text-xs text-pretty">
            {entry.description}
          </p>
        </li>
      ))}
    </ul>
  );
}
