import { ArrowRight, Clock } from "lucide-react";
import Link from "next/link";

import { colaboradorHref } from "@/lib/colaborador/url";

import { Badge } from "@/components/ui/badge";
import { Drawer } from "@/components/ui/drawer";
import { SignedMinutes } from "@/components/ui/signed-minutes";
import type { PontoFilters } from "@/lib/ponto/filters";
import {
  directionWord,
  formatClock,
  formatDayLong,
  formatDuration,
  formatTime,
} from "@/lib/ponto/format";
import type { Occurrence } from "@/lib/ponto/queries";
import { pontoHref, type Paging } from "@/lib/ponto/url";

/**
 * Detail of one indication. Everything here is what the engine observed —
 * expected against recorded, and the reading that produced it. The screen never
 * claims a finding: it shows the two times side by side and says where the
 * official record lives.
 */
export function OccurrenceDrawer({
  occurrence,
  filters,
  paging,
}: {
  occurrence: Occurrence | null;
  filters: PontoFilters;
  paging: Paging;
}) {
  const closeHref = pontoHref(filters, paging, { eventId: null });

  if (!occurrence) {
    return (
      <Drawer
        title="Este indício não existe mais"
        closeHref={closeHref}
        eyebrow="Ocorrência"
      >
        <p className="text-ink-muted text-sm text-pretty">
          A ocorrência que o link aponta não está mais ativa. Ou a marcação foi
          corrigida na origem e o motor revogou o indício — desvio nunca é
          apagado, é revogado — ou ela está fora das unidades que você
          acompanha.
        </p>
      </Drawer>
    );
  }

  return (
    <Drawer
      eyebrow="Ocorrência"
      title={occurrence.employeeName}
      subtitle={`${occurrence.unitName ?? "Sem unidade"} · ${formatDayLong(occurrence.referenceDate)}`}
      closeHref={closeHref}
      footer={
        <div className="flex flex-col gap-3">
          <Link
            href={colaboradorHref(occurrence.employeeId)}
            className="text-brand-strong flex w-fit items-center gap-1.5 text-sm font-bold underline-offset-4 hover:underline"
          >
            Ver o colaborador
            <ArrowRight size={15} aria-hidden />
          </Link>
          <p className="text-ink-faint text-xs text-pretty">
            Registro oficial de jornada permanece no Secullum. O FastPark aponta
            indícios.
          </p>
        </div>
      }
    >
      <div className="flex flex-col gap-5">
        <section className="bg-muted flex flex-col gap-3 rounded-[14px] p-5">
          <p className="text-ink-body text-sm text-pretty">
            {sentence(occurrence)}
          </p>
          <SignedMinutes
            minutes={occurrence.minutes}
            direction={occurrence.direction}
            size="lg"
          />
          <p className="text-ink-muted text-xs">
            {formatDuration(occurrence.minutes)}{" "}
            {directionWord(occurrence.direction)}
          </p>
        </section>

        <section className="grid grid-cols-2 gap-3">
          <TimeBlock
            label="Previsto"
            value={formatTime(occurrence.expectedTime)}
          />
          <TimeBlock
            label="Registrado"
            value={formatTime(occurrence.actualTime)}
            fallback="ainda não registrada"
          />
        </section>

        <section className="flex flex-col gap-2">
          <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
            Situação
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={occurrence.pendenteDeCiclo ? "alert" : "good"} dot>
              {occurrence.pendenteDeCiclo
                ? "Pendente de ciclo"
                : "Em relatório"}
            </Badge>
            <span className="text-ink-muted flex items-center gap-1.5 text-xs">
              <Clock size={13} aria-hidden />
              Detectado na leitura das {formatClock(occurrence.detectedAt)}
            </span>
          </div>
          <p className="text-ink-muted text-xs text-pretty">
            A leitura roda a cada 30 minutos, então o alerta pode chegar até 40
            minutos depois do fato.
          </p>
        </section>
      </div>
    </Drawer>
  );
}

function sentence(occurrence: Occurrence): string {
  const expected = formatTime(occurrence.expectedTime);
  const actual = formatTime(occurrence.actualTime);

  if (expected && actual) {
    return `${occurrence.typeDescription}: previsto ${expected}, registrado ${actual}.`;
  }
  if (expected) {
    return `${occurrence.typeDescription}: previsto ${expected}, sem marcação correspondente.`;
  }

  return occurrence.typeDescription;
}

function TimeBlock({
  label,
  value,
  fallback,
}: {
  label: string;
  value: string | null;
  fallback?: string;
}) {
  return (
    <div className="border-line-subtle rounded-[12px] border px-4 py-3">
      <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
        {label}
      </p>
      <p
        className={`mt-1 font-mono font-bold tabular-nums ${
          value ? "text-ink text-xl" : "text-ink-faint text-sm"
        }`}
      >
        {value ?? fallback ?? "—"}
      </p>
    </div>
  );
}
