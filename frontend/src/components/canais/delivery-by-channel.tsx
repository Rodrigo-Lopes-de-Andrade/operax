import { Card, CardHeader } from "@/components/ui/kpi-card";
import { CHANNEL_LABEL, CHANNELS, label } from "@/lib/canais/labels";
import type { DeliveryByChannelRow } from "@/lib/canais/queries";
import { share } from "@/lib/dp/format";
import { formatDayShort, formatNumber } from "@/lib/ponto/format";

/**
 * A frase que dá sentido ao cartão — a consequência 1 da SPEC-CANAIS §8, e o
 * gate do C5: o ganho é medível, e é este.
 */
const WHY = "Cada pessoa que adere ao Telegram sai do número de WhatsApp.";

/**
 * O canal que `alert_sent` registra e a tela de Conexões não configura: não
 * tem região, formulário nem provedor em `PROVIDER_LABEL`, e por isso não
 * está em `CHANNELS` — mas aparece no log, e uma coluna que sumisse deixaria
 * "Falhas" somando o que nenhuma coluna mostra. Um canal que nem este mapa
 * conhece sai com o código cru, como `label()` faz em toda parte.
 */
const OTHER_CHANNEL_LABEL: Record<string, string> = {
  email: "E-mail",
};

/** Uma semana da tabela: o `sent` somado por canal, e o `failed` de todos. */
type Week = {
  week_start: string;
  sent: Record<string, number>;
  failed: number;
};

/**
 * Agrupa as linhas (semana, canal, provedor) por semana, somando `sent` por
 * **canal** — pelo campo `channel` da linha, nunca pelo nome do provedor: o
 * canal de um provedor é o backend quem diz, e dois provedores de WhatsApp
 * na mesma semana são uma coluna só. A ordem é a da RPC (semana mais antiga
 * primeiro); os canais fora de `CHANNELS` entram na ordem em que aparecem.
 */
function byWeek(rows: DeliveryByChannelRow[]): {
  weeks: Week[];
  others: string[];
} {
  const weeks: Week[] = [];
  const others: string[] = [];

  for (const row of rows) {
    let week = weeks.at(-1);

    if (!week || week.week_start !== row.week_start) {
      week = { week_start: row.week_start, sent: {}, failed: 0 };
      weeks.push(week);
    }

    week.sent[row.channel] = (week.sent[row.channel] ?? 0) + row.sent;
    week.failed += row.failed;

    if (
      !(CHANNELS as readonly string[]).includes(row.channel) &&
      !others.includes(row.channel)
    ) {
      others.push(row.channel);
    }
  }

  return { weeks, others };
}

/**
 * A fatia do Telegram entre os dois canais que a adesão troca — WhatsApp e
 * Telegram, e só eles: o e-mail não entra no denominador porque ninguém sai
 * do número de WhatsApp para o e-mail. Base zero é `—`, não 0%.
 */
function telegramShare(sent: Record<string, number>): string {
  const telegram = sent.telegram ?? 0;
  const pct = share(telegram, (sent.whatsapp ?? 0) + telegram);

  return pct === null ? "—" : `${formatNumber(pct)}%`;
}

const HEAD_CLASS =
  "border-line-subtle text-ink-muted text-2xs border-b py-2.5 font-bold tracking-[0.06em] uppercase";
const NUMBER_CLASS = "px-4 py-2 text-right text-sm tabular-nums";

/**
 * Entregas por canal, semana a semana — `public.fn_delivery_by_channel`, o
 * relatório da SPEC-CANAIS §8 e o gate do C5: a coluna de WhatsApp cai
 * conforme a de Telegram sobe.
 *
 * Uma linha por semana (`DD/MM` da segunda-feira, formatado por string — é
 * `date`, não há hora para deslocar), uma coluna por canal com o `sent`
 * somado dos provedores dele, **Falhas** com o `failed` de todos, e
 * **Telegram %** sobre WhatsApp + Telegram. A coluna de e-mail só existe
 * quando há linha de e-mail. O rodapé soma o período. Sem nome, sem número,
 * sem `chat_id`: a RPC não os devolve, e a tela não os inventa.
 *
 * `null` é "não pôde ser lida"; `[]` é "nenhuma entrega" — e `[]` é o estado
 * normal enquanto o sender não está agendado, não um erro. A frase do porquê
 * fica sob o título nos três estados.
 */
export function DeliveryByChannel({
  rows,
}: {
  rows: DeliveryByChannelRow[] | null;
}) {
  return (
    <Card>
      <CardHeader eyebrow="Entregas" title="Entregas por canal" note={WHY} />
      <div className="py-2">
        <DeliveryTable rows={rows} />
      </div>
    </Card>
  );
}

function DeliveryTable({ rows }: { rows: DeliveryByChannelRow[] | null }) {
  if (rows === null) {
    return (
      <p className="text-ink-muted px-5 py-2 text-sm text-pretty">
        As entregas não puderam ser lidas agora.
      </p>
    );
  }

  if (rows.length === 0) {
    return (
      <p className="text-ink-muted px-5 py-2 text-sm text-pretty">
        Nenhuma entrega registrada nas últimas 8 semanas.
      </p>
    );
  }

  const { weeks, others } = byWeek(rows);
  const columns: { key: string; label: string }[] = [
    ...CHANNELS.map((channel) => ({
      key: channel,
      label: CHANNEL_LABEL[channel],
    })),
    ...others.map((channel) => ({
      key: channel,
      label: label(OTHER_CHANNEL_LABEL, channel),
    })),
  ];

  const totalSent: Record<string, number> = {};
  let totalFailed = 0;

  for (const week of weeks) {
    for (const column of columns) {
      totalSent[column.key] =
        (totalSent[column.key] ?? 0) + (week.sent[column.key] ?? 0);
    }
    totalFailed += week.failed;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <caption className="sr-only">Entregas por canal e semana</caption>
        <thead>
          <tr className="bg-muted">
            <th scope="col" className={`${HEAD_CLASS} px-[22px] text-left`}>
              Semana
            </th>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={`${HEAD_CLASS} px-4 text-right`}
              >
                {column.label}
              </th>
            ))}
            <th scope="col" className={`${HEAD_CLASS} px-4 text-right`}>
              Falhas
            </th>
            <th scope="col" className={`${HEAD_CLASS} px-[22px] text-right`}>
              {CHANNEL_LABEL.telegram} %
            </th>
          </tr>
        </thead>
        <tbody>
          {weeks.map((week) => (
            <tr key={week.week_start} className="border-line-subtle border-t">
              <th
                scope="row"
                className="text-ink px-[22px] py-2 text-left text-sm font-semibold tabular-nums"
              >
                {formatDayShort(week.week_start)}
              </th>
              {columns.map((column) => (
                <td key={column.key} className={`text-ink ${NUMBER_CLASS}`}>
                  {formatNumber(week.sent[column.key] ?? 0)}
                </td>
              ))}
              <td className={`text-ink ${NUMBER_CLASS}`}>
                {formatNumber(week.failed)}
              </td>
              <td className="text-ink px-[22px] py-2 text-right text-sm font-bold tabular-nums">
                {telegramShare(week.sent)}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-line-strong border-t-2">
            <th
              scope="row"
              className="text-ink px-[22px] py-2 text-left text-sm font-extrabold"
            >
              Total
            </th>
            {columns.map((column) => (
              <td
                key={column.key}
                className={`text-ink font-bold ${NUMBER_CLASS}`}
              >
                {formatNumber(totalSent[column.key] ?? 0)}
              </td>
            ))}
            <td className={`text-ink font-bold ${NUMBER_CLASS}`}>
              {formatNumber(totalFailed)}
            </td>
            <td className="text-ink px-[22px] py-2 text-right text-sm font-extrabold tabular-nums">
              {telegramShare(totalSent)}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
