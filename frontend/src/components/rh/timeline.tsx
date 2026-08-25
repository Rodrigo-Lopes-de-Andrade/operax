"use client";

import { useState } from "react";

import { BandForm } from "@/components/rh/band-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

// Com o ano, e não `formatDayShort`: numa linha do tempo, duas faixas em "26/09"
// de anos diferentes são indistinguíveis, que é o oposto do que ela existe para
// mostrar.
const DIA = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  timeZone: "UTC",
});

function dia(iso: string): string {
  return DIA.format(new Date(`${iso}T00:00:00Z`));
}

export type Band = {
  effective_from: string;
  effective_to: string | null;
  headline: string;
  note: string | null;
};

/**
 * Remuneração e posição como linha do tempo, e não como um campo com o valor de
 * hoje.
 *
 * A faixa aberta fica no topo e marcada como vigente; as fechadas continuam
 * visíveis com o período. É o que responde "desde quando ele ganha isso?" sem
 * que ninguém precise abrir a auditoria — e é o que impede a pergunta seguinte,
 * "quem mudou e quando", de não ter resposta.
 */
export function Timeline({
  employeeId,
  kind,
  bands,
  canWrite,
  emptyText,
}: {
  employeeId: string;
  kind: "compensation" | "position";
  bands: Band[];
  canWrite: boolean;
  emptyText: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex flex-col gap-4">
      {canWrite ? (
        <div className="flex justify-end">
          <Button onClick={() => setOpen((value) => !value)}>
            {open ? "Cancelar" : "Nova vigência"}
          </Button>
        </div>
      ) : null}

      {open ? (
        <div className="bg-muted rounded-[14px] p-4">
          <p className="text-ink-muted mb-3 text-xs text-pretty">
            A faixa vigente é fechada no dia anterior a esta data. Para corrigir
            a faixa que está aberta, revogue-a — vigência nova começa depois
            dela.
          </p>
          <BandForm
            employeeId={employeeId}
            kind={kind}
            onDone={() => setOpen(false)}
          />
        </div>
      ) : null}

      {bands.length === 0 ? (
        <p className="text-ink-faint text-sm">{emptyText}</p>
      ) : (
        <ol className="flex flex-col gap-3">
          {bands.map((band) => (
            <li
              key={`${band.effective_from}-${band.headline}`}
              className="border-line-subtle flex flex-wrap items-baseline justify-between gap-2 border-l-2 pl-4"
            >
              <span className="flex flex-col">
                <span className="text-ink text-md font-extrabold">
                  {band.headline}
                </span>
                <span className="text-ink-muted text-xs">
                  {dia(band.effective_from)}
                  {band.effective_to
                    ? ` até ${dia(band.effective_to)}`
                    : " — em vigor"}
                  {band.note ? ` · ${band.note}` : ""}
                </span>
              </span>
              {band.effective_to ? null : <Badge tone="good">Vigente</Badge>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
