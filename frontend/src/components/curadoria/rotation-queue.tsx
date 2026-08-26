"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError, requestApiAsUser } from "@/lib/api";
import type { RotationRow, RotationScreen } from "@/lib/curadoria/queries";
import {
  formatDayShort,
  formatDuration,
  formatNumber,
  formatTime,
  formatWeekday,
} from "@/lib/ponto/format";

/**
 * Curadoria horário → rotação.
 *
 * `secullum."HorarioDia"` tem chave (horário, dia da semana) de 0 a 6: é uma
 * semana fixa de sete dias. Um 12x36 é ciclo de 48 h, e sete não é múltiplo de
 * dois — o padrão nunca fecha na semana e não cabe lá. O contorno do próprio
 * Secullum está no dado: a escala chega como pares "Par"/"Ímpar" com os sete
 * dias vazios, e a rotação mora fora do arquivo.
 *
 * Enquanto ela não é declarada, essas pessoas materializam jornada com confiança
 * 0. Isso não gera alerta errado — o portão de 80 as barra — e é justamente o
 * problema: elas não são medidas. Não aparecem erradas, não aparecem.
 *
 * OS DIAS BATIDOS SÃO MOSTRADOS, E A ÂNCORA NÃO É DEDUZIDA DELES
 * Cada cartão traz os dias em que aquele horário de fato bateu ponto, e clicar
 * num deles preenche a âncora. Parece um detalhe de conveniência e é a decisão
 * central da tela: o sistema mostra o que aconteceu e a pessoa conclui a escala.
 * Deduzir a âncora seria fechar o circuito — os dias em que alguém bateu SÃO os
 * dias em que trabalhou, então uma escala derivada dali encaixa sempre, e uma
 * escala que encaixa sempre nunca produz "não bateu" nem "bateu na folga".
 *
 * A CARGA É CONTA, NÃO CAMPO
 * Ela sai de entrada, saída e intervalo, que é de onde ela sairia na mão. Um
 * campo a mais seria um lugar a mais para a carga discordar do turno — e a
 * conta bate com a produção: 19:00 às 05:00 com 1h12 de intervalo dá os mesmos
 * 528 minutos que o `Carga` do Secullum declara.
 */
export function RotationQueue({ screen }: { screen: RotationScreen }) {
  const router = useRouter();
  const [draft, setDraft] = useState<Record<number, Draft>>({});
  const [saving, setSaving] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState<string | null>(null);

  function current(row: RotationRow): Draft {
    return draft[row.secullum_schedule_id] ?? fromRow(row);
  }

  function change(row: RotationRow, patch: Partial<Draft>) {
    setDraft((all) => ({
      ...all,
      [row.secullum_schedule_id]: { ...current(row), ...patch },
    }));
  }

  async function declare(row: RotationRow) {
    const form = current(row);
    const load = workload(form);

    if (load === null) {
      return;
    }

    setSaving(row.secullum_schedule_id);
    setError(null);
    setApplied(null);

    try {
      const result = await requestApiAsUser<{
        secullum_schedule_id: number;
        employees_covered: number;
      }>("/curadoria/rotacoes", {
        method: "POST",
        body: {
          secullum_schedule_id: row.secullum_schedule_id,
          cycle_length_days: form.cycle,
          anchor_date: form.anchor,
          expected_entry: form.entry,
          expected_exit: form.exit,
          expected_break_minutes: form.breakMinutes,
          workload_minutes: load,
          tolerance_extra_minutes: form.toleranceExtra,
          tolerance_absence_minutes: form.toleranceAbsence,
        },
      });

      setDraft((all) => {
        const rest = { ...all };
        delete rest[row.secullum_schedule_id];
        return rest;
      });
      setApplied(
        `Escala declarada · ${formatNumber(result.employees_covered)} ${
          result.employees_covered === 1
            ? "colaborador sai da confiança zero"
            : "colaboradores saem da confiança zero"
        }`,
      );
      router.refresh();
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.detail
          ? caught.detail
          : "Não foi possível gravar agora. Nada foi alterado.",
      );
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Progress screen={screen} />

      {error ? <Alert>{error}</Alert> : null}
      {applied ? (
        <p
          role="status"
          className="bg-good-bg text-good rounded-[10px] px-3 py-2 text-sm font-medium"
        >
          {applied}
        </p>
      ) : null}

      {screen.rows.map((row) => {
        const form = current(row);
        const load = workload(form);
        const busy = saving === row.secullum_schedule_id;

        return (
          <section
            key={row.secullum_schedule_id}
            className="border-line-subtle bg-card flex flex-col gap-4 rounded-2xl border p-5"
          >
            <header className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-ink font-bold">{row.schedule}</h2>
                <p className="text-ink-faint font-mono text-xs">
                  #{row.secullum_schedule_id} · {formatNumber(row.employees)}{" "}
                  {row.employees === 1 ? "ativo" : "ativos"}
                </p>
              </div>
              <State row={row} />
            </header>

            <Observed
              row={row}
              onPick={(dia) => change(row, { anchor: dia })}
            />

            <div className="flex flex-wrap items-end gap-3">
              <Field label="Ciclo (dias)">
                <input
                  type="number"
                  min={2}
                  max={31}
                  value={form.cycle}
                  disabled={busy}
                  aria-label={`Ciclo de ${row.schedule}`}
                  onChange={(event) =>
                    change(row, { cycle: Number(event.target.value) })
                  }
                  className="border-line text-ink h-10 w-20 rounded-xl border px-3 text-sm font-bold tabular-nums"
                />
              </Field>
              <Field label="Trabalhou em">
                <input
                  type="date"
                  value={form.anchor}
                  disabled={busy}
                  aria-label={`Dia trabalhado de ${row.schedule}`}
                  onChange={(event) =>
                    change(row, { anchor: event.target.value })
                  }
                  className="border-line text-ink h-10 rounded-xl border px-3 text-sm"
                />
              </Field>
              <Field label="Entrada">
                <input
                  type="time"
                  value={form.entry}
                  disabled={busy}
                  aria-label={`Entrada de ${row.schedule}`}
                  onChange={(event) =>
                    change(row, { entry: event.target.value })
                  }
                  className="border-line text-ink h-10 rounded-xl border px-3 text-sm tabular-nums"
                />
              </Field>
              <Field label="Saída">
                <input
                  type="time"
                  value={form.exit}
                  disabled={busy}
                  aria-label={`Saída de ${row.schedule}`}
                  onChange={(event) =>
                    change(row, { exit: event.target.value })
                  }
                  className="border-line text-ink h-10 rounded-xl border px-3 text-sm tabular-nums"
                />
              </Field>
              <Field label="Intervalo (min)">
                <input
                  type="number"
                  min={0}
                  value={form.breakMinutes ?? ""}
                  disabled={busy}
                  aria-label={`Intervalo de ${row.schedule}`}
                  onChange={(event) =>
                    change(row, {
                      breakMinutes:
                        event.target.value === ""
                          ? null
                          : Number(event.target.value),
                    })
                  }
                  className="border-line text-ink h-10 w-24 rounded-xl border px-3 text-sm tabular-nums"
                />
              </Field>

              <Button
                onClick={() => void declare(row)}
                disabled={busy || load === null}
                className="h-10"
              >
                {busy ? "Gravando…" : "Declarar escala"}
              </Button>
            </div>

            <p className="text-ink-faint text-xs text-pretty">
              {load === null ? (
                "Preencha entrada, saída e o dia trabalhado para declarar a escala."
              ) : (
                <>
                  Carga do dia:{" "}
                  <strong className="text-ink-muted">
                    {formatDuration(load)}
                  </strong>{" "}
                  — entrada às {form.entry}, saída às {form.exit}
                  {form.breakMinutes
                    ? `, menos ${formatDuration(form.breakMinutes)} de intervalo`
                    : ""}
                  .{" "}
                  {crossesMidnight(form)
                    ? "A saída é no dia seguinte, e é assim que o turno noturno se declara."
                    : ""}
                </>
              )}
            </p>
          </section>
        );
      })}
    </div>
  );
}

export type Draft = {
  cycle: number;
  anchor: string;
  entry: string;
  exit: string;
  breakMinutes: number | null;
  toleranceExtra: number;
  toleranceAbsence: number;
};

function fromRow(row: RotationRow): Draft {
  return {
    cycle: row.cycle_length_days ?? 2,
    anchor: row.anchor_date ?? "",
    entry: formatTime(row.expected_entry) ?? "",
    exit: formatTime(row.expected_exit) ?? "",
    breakMinutes: row.expected_break_minutes,
    toleranceExtra: row.tolerance_extra_minutes ?? 0,
    toleranceAbsence: row.tolerance_absence_minutes ?? 0,
  };
}

/** Minutos do turno menos o intervalo, ou null enquanto falta o que somar. */
export function workload(form: Draft): number | null {
  if (!form.entry || !form.exit || !form.anchor || form.cycle < 2) {
    return null;
  }

  const total = shiftMinutes(form.entry, form.exit) - (form.breakMinutes ?? 0);

  return total > 0 ? total : null;
}

function shiftMinutes(entry: string, exit: string): number {
  const start = clockMinutes(entry);
  const end = clockMinutes(exit);

  // Uma saída que não é maior que a entrada é no dia seguinte. É a mesma
  // assinatura que o `HorarioDia` do Secullum usa para declarar a virada.
  return end > start ? end - start : end + 24 * 60 - start;
}

function clockMinutes(value: string): number {
  const [hour, minute] = value.split(":").map(Number);

  return hour * 60 + minute;
}

function crossesMidnight(form: Draft): boolean {
  return (
    Boolean(form.entry && form.exit) &&
    clockMinutes(form.exit) <= clockMinutes(form.entry)
  );
}

/**
 * Os dias batidos, e o convite a escolher um deles como âncora.
 *
 * É informação, não conclusão: quem olha 10, 12, 14 e 16 reconhece o 12x36 num
 * segundo, e quem clica está declarando "este dia esse pessoal trabalhou".
 */
function Observed({
  row,
  onPick,
}: {
  row: RotationRow;
  onPick: (dia: string) => void;
}) {
  if (row.observed_days.length === 0) {
    return (
      <p className="text-ink-faint text-xs">
        Nenhuma marcação lida para este horário nas últimas semanas — a âncora
        precisa vir de quem conhece a escala.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-2xs text-ink-faint font-bold tracking-[0.06em] uppercase">
        Dias com marcação
      </p>
      <div className="flex flex-wrap gap-1.5">
        {row.observed_days.map((dia) => (
          <button
            key={dia}
            type="button"
            onClick={() => onPick(dia)}
            className="border-line text-ink-muted hover:border-brand hover:text-ink rounded-lg border px-2 py-1 text-xs font-semibold tabular-nums"
          >
            {formatDayShort(dia)}
            <span className="text-ink-faint ml-1 font-normal">
              {formatWeekday(dia)}
            </span>
          </button>
        ))}
      </div>
      <p className="text-ink-faint text-xs">
        Clique num dia para usá-lo como referência do ciclo.
      </p>
    </div>
  );
}

/**
 * A barra da curadoria, e "provisório" é faixa própria — como no mapa de
 * unidade, e aqui por um motivo mais duro: rotação sem carimbo o motor não lê.
 */
function Progress({ screen }: { screen: RotationScreen }) {
  const pendente =
    screen.on_blank_schedule - screen.validated - screen.provisional;
  const partes = [
    { label: "Declarada", value: screen.validated, tone: "bg-good" },
    { label: "Provisória", value: screen.provisional, tone: "bg-brand" },
    { label: "Sem escala", value: pendente, tone: "bg-alert" },
  ];

  return (
    <section className="border-line-subtle bg-card flex flex-col gap-4 rounded-2xl border p-5">
      <div>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Curadoria
        </p>
        <p className="text-ink text-3xl leading-none font-extrabold tabular-nums">
          {formatNumber(screen.validated)}{" "}
          <span className="text-ink-muted text-base font-bold">
            de {formatNumber(screen.on_blank_schedule)} em horário sem
            expediente declarado
          </span>
        </p>
      </div>

      {screen.on_blank_schedule > 0 ? (
        <div className="flex h-2 overflow-hidden rounded-full" aria-hidden>
          {partes
            .filter((parte) => parte.value > 0)
            .map((parte) => (
              <span
                key={parte.label}
                className={parte.tone}
                style={{
                  width: `${(parte.value / screen.on_blank_schedule) * 100}%`,
                }}
              />
            ))}
        </div>
      ) : null}

      <dl className="grid grid-cols-3 gap-4">
        {partes.map((parte) => (
          <div key={parte.label} className="flex flex-col gap-0.5">
            <dt className="text-ink-muted flex items-center gap-1.5 text-xs font-semibold">
              <span
                aria-hidden
                className={`size-2 shrink-0 rounded-full ${parte.tone}`}
              />
              {parte.label}
            </dt>
            <dd className="text-ink text-xl leading-none font-extrabold tabular-nums">
              {formatNumber(Math.max(0, parte.value))}
            </dd>
          </div>
        ))}
      </dl>

      <p className="text-ink-faint text-xs text-pretty">
        Sem escala declarada, essas pessoas não geram indício errado — e também
        não são medidas. Elas não aparecem erradas: não aparecem.
      </p>
    </section>
  );
}

function State({ row }: { row: RotationRow }) {
  if (row.validated_at) {
    return <Badge tone="good">declarada</Badge>;
  }

  return row.cycle_length_days ? (
    <Badge tone="neutral">provisória</Badge>
  ) : (
    <Badge tone="alert">sem escala</Badge>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-ink-muted text-xs font-bold">{label}</span>
      {children}
    </label>
  );
}
