import { Card } from "@/components/ui/kpi-card";
import type { DailyMonitor } from "@/lib/monitor/queries";
import { formatNumber } from "@/lib/ponto/format";

/**
 * Quadro do dia — onde está cada pessoa do efetivo.
 *
 * Os cinco números fecham no total, e é por isso que eles são cinco e não
 * quatro: escalado, férias, afastamento e folga não somam o efetivo, porque
 * existe gente ativa sem jornada prevista para o dia. Na FastPark são seis
 * pessoas da administração, e é por desenho — os horários delas se chamam
 * "Ponto por exceção". Mas falha de cobertura do motor tem exatamente a mesma
 * aparência, e a única forma de distinguir as duas é o número existir.
 *
 * "Presentes" e "ausentes" não estão aqui, e a ausência é deliberada. A marcação
 * do dia existe — em `app.batida_marcacao` —, mas ela é tabela de ingestão
 * congelada, ausente do banco de desenvolvimento, e o que a alimenta é decisão
 * em aberto do dono. Enquanto isso, um cartão chamado "presentes" alimentado por
 * "escalado e sem indício" seria a única mentira desta tela.
 */
export function RosterBand({ monitor }: { monitor: DailyMonitor }) {
  const partes = [
    {
      label: "Escalados",
      value: monitor.scheduled,
      tone: "bg-brand",
      note: "Com jornada prevista",
    },
    {
      label: "Em férias",
      value: monitor.on_vacation,
      tone: "bg-good",
      note: "Férias no dia",
    },
    {
      label: "Afastados",
      value: monitor.on_leave,
      tone: "bg-alert",
      note: "Afastamento no dia",
    },
    {
      label: "Folga",
      value: monitor.day_off,
      tone: "bg-ink-faint",
      note: "Folga, feriado ou compensado",
    },
    {
      label: "Sem jornada",
      value: monitor.unrostered,
      tone: "bg-line-subtle",
      note: "Ativo e sem jornada prevista para o dia",
    },
  ];

  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
            Quadro do dia
          </p>
          <p className="text-ink text-3xl leading-none font-extrabold tabular-nums">
            {formatNumber(monitor.active)}{" "}
            <span className="text-ink-muted text-base font-bold">
              colaboradores ativos
            </span>
          </p>
        </div>
        {monitor.unrostered > 0 ? (
          <p className="text-ink-muted max-w-xs text-xs text-pretty">
            {formatNumber(monitor.unrostered)} sem jornada prevista para o dia —
            pode ser desenho, pode ser cobertura do motor.
          </p>
        ) : null}
      </div>

      {monitor.active > 0 ? (
        <div
          className="flex h-2 overflow-hidden rounded-full"
          aria-hidden="true"
        >
          {partes
            .filter((parte) => parte.value > 0)
            .map((parte) => (
              <span
                key={parte.label}
                className={parte.tone}
                style={{ width: `${(parte.value / monitor.active) * 100}%` }}
              />
            ))}
        </div>
      ) : null}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-5">
        {partes.map((parte) => (
          <div key={parte.label} className="flex flex-col gap-0.5">
            <dt className="text-ink-muted flex items-center gap-1.5 text-xs font-semibold">
              <span
                aria-hidden="true"
                className={`size-2 shrink-0 rounded-full ${parte.tone}`}
              />
              {parte.label}
            </dt>
            <dd className="text-ink text-xl leading-none font-extrabold tabular-nums">
              {formatNumber(parte.value)}
            </dd>
            <dd className="text-ink-faint text-2xs text-pretty">
              {parte.note}
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
