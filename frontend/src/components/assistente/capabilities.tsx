"use client";

import { ListChecks } from "lucide-react";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Table, type Column, type Row } from "@/components/ui/table";
import { ApiError } from "@/lib/api";
import {
  domainLabel,
  saveCapability,
  type CapabilityRow,
} from "@/lib/assistente/config";

/**
 * A aba Capacidades: as métricas do catálogo, e o interruptor de cada uma.
 *
 * ⛔ NÃO É UMA TELA DE PERMISSÃO (SPEC-AGENTE §4.1)
 * Habilitar uma métrica não concede acesso a dado: o executor roda a view
 * como o usuário, e a RLS dele decide o que volta. A lista só estreita —
 * desligar tira a métrica do assistente para todo mundo; ligar nunca amplia
 * além do que o papel já podia. A linha fixa no topo diz isso, e o selo "fora
 * do seu alcance" é o exemplo vivo: ligada para o cliente, e mesmo assim fora
 * do domínio de quem está olhando.
 *
 * ⛔ SEM "CRIAR MÉTRICA" (§4.4), SEM FILTRO, SEM BUSCA, SEM ORDENAÇÃO
 * Métrica exige view e migration; pedir uma nova é chamado, não formulário.
 * E a lista tem uma dúzia de linhas: a ordem é a da API (`code`).
 *
 * A linha gravada volta da mesma régua que a aba lê (`fn_assistant_catalog`),
 * e é ela que substitui a linha da tela — não o que a tela achava que ia
 * acontecer.
 */

const RULE =
  "Desligar tira a métrica do assistente para todo mundo. Ligar não dá acesso a dado que o papel não alcança.";
const NOT_FOUND = "Métrica não encontrada.";
const FORBIDDEN = "Sem permissão para ligar ou desligar uma métrica.";
const FAILED = "Não consegui gravar a métrica. Nada foi alterado.";

const COLUMNS: Column[] = [
  { key: "metric", label: "Métrica" },
  { key: "domain", label: "Domínio", noWrap: true },
  { key: "enabled", label: "Ligada", align: "right", width: "96px" },
];

function failureMessage(caught: unknown): string {
  if (caught instanceof ApiError) {
    if (caught.status === 404) {
      return NOT_FOUND;
    }

    if (caught.status === 403) {
      return caught.detail ?? FORBIDDEN;
    }

    if (caught.detail) {
      return caught.detail;
    }
  }

  return FAILED;
}

export function Capabilities({ rows: initial }: { rows: CapabilityRow[] }) {
  const [rows, setRows] = useState(initial);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle(row: CapabilityRow) {
    setBusy(row.code);
    setError(null);

    try {
      const saved = await saveCapability(row.code, !row.enabled);
      setRows((previous) =>
        previous.map((item) => (item.code === saved.code ? saved : item)),
      );
    } catch (caught) {
      setError(failureMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  const tableRows: Row[] = rows.map((row) => ({
    id: row.code,
    cells: {
      metric: (
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-ink font-bold">{row.title}</span>
            {row.enabled && !row.visible_to_me ? (
              <Badge tone="neutral">fora do seu alcance</Badge>
            ) : null}
          </div>
          <span className="text-ink-muted text-xs text-pretty">
            {row.description}
          </span>
        </div>
      ),
      domain: (
        <span className="text-ink-muted text-xs">
          {domainLabel(row.domain)}
        </span>
      ),
      enabled: (
        <input
          type="checkbox"
          role="switch"
          aria-label={`Ligada: ${row.title}`}
          aria-checked={row.enabled}
          checked={row.enabled}
          disabled={busy !== null}
          onChange={() => void toggle(row)}
          className="size-4"
        />
      ),
    },
  }));

  return (
    <Card>
      <CardHeader
        eyebrow="Catálogo"
        title="Capacidades"
        note={`${rows.length} ${rows.length === 1 ? "métrica" : "métricas"} no catálogo. A ordem é a da API.`}
      />
      <div className="flex flex-col gap-3">
        <p className="text-ink border-line-subtle border-b px-5 py-3 text-sm font-medium text-pretty">
          {RULE}
        </p>
        {error ? (
          <div className="px-5">
            <Alert>{error}</Alert>
          </div>
        ) : null}
        <Table
          columns={COLUMNS}
          rows={tableRows}
          caption="Métricas do assistente"
          empty={
            <EmptyState
              icon={ListChecks}
              tone="neutral"
              compact
              title="Nenhuma métrica no catálogo"
              description="O catálogo é semeado por migration. Sem métrica, o assistente só recusa."
            />
          }
        />
      </div>
    </Card>
  );
}
