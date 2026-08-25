import { Card } from "@/components/ui/kpi-card";
import type { DailyMonitor } from "@/lib/monitor/queries";
import { todayInTenantZone } from "@/lib/ponto/filters";
import { formatClock, formatDayShort, formatNumber } from "@/lib/ponto/format";

/**
 * Com marcação / sem marcação até a leitura de HH:MM.
 *
 * O rótulo é o componente. Os dois números vêm de `app.batida_marcacao`, e o
 * instante em que eles foram lidos não é um detalhe de rodapé: quem bateu um
 * minuto depois da última leitura está em "sem marcação", e sem a hora ao lado
 * o cartão afirmaria que essa pessoa não bateu ponto.
 *
 * NÃO É "PRESENTES" E "AUSENTES", E ISSO NÃO É PREFERÊNCIA DE PALAVRA
 * Marcação é registro, presença é fato. Chamar um de outro é a decisão de
 * produto A12 da auditoria, aberta com o dono — e é justamente o tipo de frase
 * que um gestor repassa para um colaborador. "Você não bateu ponto até as 09:15"
 * é conferível; "você faltou" é uma acusação que o dado não sustenta.
 *
 * Sem leitura nenhuma, o cartão não mostra zeros. Dois zeros e "ninguém bateu"
 * são a mesma imagem e significados opostos.
 */
export function PunchReading({ monitor }: { monitor: DailyMonitor }) {
  if (!monitor.punches_read_at) {
    return (
      <Card className="flex flex-col gap-1 p-5">
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Marcações do dia
        </p>
        <p className="text-ink-muted text-sm text-pretty">
          Nenhuma leitura de marcação concluída para este cliente. Os números
          não são zero — eles não existem, e é diferente.
        </p>
      </Card>
    );
  }

  const reading = readingLabel(monitor.day, monitor.punches_read_at);

  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Marcações {reading}
        </p>
        <p className="text-ink-faint text-xs">
          {formatNumber(monitor.scheduled)} escalados
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-0.5">
          <dt className="text-ink-muted text-xs font-semibold">
            Com marcação {reading}
          </dt>
          <dd className="text-ink text-3xl leading-none font-extrabold tabular-nums">
            {formatNumber(monitor.with_punch)}
          </dd>
          <dd className="text-ink-faint text-2xs text-pretty">
            Registrou ao menos uma batida no dia. Não é confirmação de presença.
          </dd>
        </div>
        <div className="flex flex-col gap-0.5">
          <dt className="text-ink-muted text-xs font-semibold">
            Sem marcação {reading}
          </dt>
          <dd className="text-ink text-3xl leading-none font-extrabold tabular-nums">
            {formatNumber(monitor.without_punch)}
          </dd>
          <dd className="text-ink-faint text-2xs text-pretty">
            Nenhuma batida até essa leitura. Quem bateu depois dela está aqui.
          </dd>
        </div>
      </dl>
    </Card>
  );
}

/**
 * "até a leitura de 09:15" quando a leitura é do próprio dia observado, e
 * "na leitura de 22/08 às 03:10" quando não é. Um dia passado é relido depois
 * de fechado, e escrever "até as 03:10" ali sugeriria um recorte que não houve.
 */
function readingLabel(day: string, readAt: string): string {
  const readingDay = todayInTenantZone(new Date(readAt));

  return readingDay === day
    ? `até a leitura de ${formatClock(readAt)}`
    : `na leitura de ${formatDayShort(readingDay)} às ${formatClock(readAt)}`;
}
