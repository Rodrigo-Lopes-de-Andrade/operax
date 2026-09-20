"use client";

import { History } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { ApiError } from "@/lib/api";
import {
  restoreVersion,
  type VersionRow,
  type VersionsScreen,
} from "@/lib/assistente/config";
import { diffLines } from "@/lib/assistente/diff";
import { assistenteConfigHref } from "@/lib/assistente/url";
import { formatDayInTenantZone } from "@/lib/dp/format";
import { formatClock } from "@/lib/ponto/format";

/**
 * A aba Histórico: as versões do cliente, a que está no ar, e o que cada uma
 * tem de diferente dela. As da plataforma ficam numa lista à parte, só para
 * ler — ninguém as restaura pelo painel (SPEC-AGENTE §1).
 *
 * A versão aberta mora na query string (`versao=`), como toda seleção deste
 * produto: é um link, e o botão "voltar" anda por ela.
 *
 * Restaurar move o ponteiro — e só ele. O rascunho não muda, e é isso que
 * cria o caso da SPEC §2 que a aba Configuração mostra depois: a confirmação
 * diz as duas coisas antes do clique. Depois, `router.refresh()` traz a lista
 * nova do servidor — a tela não guarda uma cópia que pudesse divergir.
 */

type Outcome =
  | { kind: "restored"; version_number: number }
  | { kind: "error"; message: string };

const RESTORE_FAILED = "Não consegui restaurar a versão. Nada foi alterado.";

function when(row: VersionRow): string {
  return `${formatDayInTenantZone(row.created_at)} às ${formatClock(row.created_at)}`;
}

function VersionText({ row }: { row: VersionRow }) {
  return (
    <pre
      aria-label={`Texto da v${row.version_number}`}
      className="bg-muted text-ink rounded-[10px] px-3 py-2 font-mono text-sm whitespace-pre-wrap"
    >
      {row.content}
    </pre>
  );
}

/**
 * A diferença da versão aberta em relação à que está no ar: `+` é o que ela
 * tem a mais, `−` o que ela não tem. A cor acompanha o sinal, mas o sinal é
 * o que se lê — cor sozinha não é informação.
 */
function Diff({
  onAir,
  selected,
}: {
  onAir: VersionRow;
  selected: VersionRow;
}) {
  const lines = diffLines(onAir.content, selected.content);

  return (
    <div className="flex flex-col gap-2">
      <h4 className="text-ink text-sm font-bold">
        Diferença em relação à v{onAir.version_number} (no ar)
      </h4>
      <ol
        aria-label="Diferenças"
        className="border-line-subtle overflow-x-auto rounded-[10px] border font-mono text-sm"
      >
        {lines.map((line, index) => (
          <li
            key={`${index}-${line.kind}`}
            data-kind={line.kind}
            className={`flex gap-3 px-3 py-0.5 whitespace-pre-wrap ${
              line.kind === "added"
                ? "bg-good-bg text-good"
                : line.kind === "removed"
                  ? "bg-bad-bg text-bad"
                  : "text-ink-muted"
            }`}
          >
            <span aria-hidden className="w-3 shrink-0 select-none">
              {line.kind === "added"
                ? "+"
                : line.kind === "removed"
                  ? "−"
                  : " "}
            </span>
            <span className="sr-only">
              {line.kind === "added"
                ? "linha a mais: "
                : line.kind === "removed"
                  ? "linha a menos: "
                  : ""}
            </span>
            <span>{line.text}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function VersionList({
  rows,
  label,
  selectedId,
  linkable,
}: {
  rows: VersionRow[];
  label: string;
  selectedId: string | null;
  linkable: boolean;
}) {
  return (
    <ol aria-label={label} className="divide-line-subtle divide-y">
      {rows.map((row) => {
        const selected = row.version_id === selectedId;

        return (
          <li
            key={row.version_id}
            aria-current={selected ? "true" : undefined}
            className={`flex flex-wrap items-center gap-2 px-5 py-3 text-sm ${
              selected ? "bg-muted" : ""
            }`}
          >
            {linkable ? (
              <Link
                href={assistenteConfigHref("historico", row.version_id)}
                className="text-brand-strong font-bold underline"
              >
                v{row.version_number}
              </Link>
            ) : (
              <span className="text-ink font-bold">v{row.version_number}</span>
            )}
            <span className="text-ink-muted">{when(row)}</span>
            {row.on_air ? (
              <Badge tone="good" dot>
                No ar
              </Badge>
            ) : null}
            {linkable ? null : (
              <details className="basis-full">
                <summary className="text-brand-strong cursor-pointer text-xs font-bold">
                  Ver o texto
                </summary>
                <div className="mt-2">
                  <VersionText row={row} />
                </div>
              </details>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export function VersionHistory({
  versions,
  selectedId,
}: {
  versions: VersionsScreen;
  selectedId: string | null;
}) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  const onAir = versions.tenant.find((row) => row.on_air) ?? null;
  const selected =
    versions.tenant.find((row) => row.version_id === selectedId) ?? null;

  async function restore(row: VersionRow) {
    setBusy(true);
    setOutcome(null);

    try {
      const moved = await restoreVersion(row.version_id);
      setConfirming(false);
      setOutcome({ kind: "restored", version_number: moved.version_number });
      router.refresh();
    } catch (caught) {
      setOutcome({
        kind: "error",
        message:
          caught instanceof ApiError && caught.detail
            ? caught.detail
            : RESTORE_FAILED,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader
          eyebrow="Cliente"
          title="Versões do cliente"
          note="Cada publicação é uma versão imutável. Restaurar move o que está no ar; o rascunho não muda."
        />
        {versions.tenant.length > 0 ? (
          <VersionList
            rows={versions.tenant}
            label="Versões do cliente"
            selectedId={selectedId}
            linkable
          />
        ) : (
          <EmptyState
            icon={History}
            tone="neutral"
            compact
            title="Nenhuma versão publicada ainda"
            description="O assistente roda só com a camada da plataforma. A primeira publicação na aba Configuração cria a v1."
          />
        )}
      </Card>

      {selected ? (
        <Card>
          <CardHeader
            eyebrow="Versão"
            title={`v${selected.version_number}`}
            note={`Publicada em ${when(selected)}.`}
            action={
              selected.on_air ? (
                <Badge tone="good" dot>
                  No ar
                </Badge>
              ) : null
            }
          />
          <div className="flex flex-col gap-4 px-5 py-4">
            <VersionText row={selected} />

            {selected.on_air ? (
              <p className="text-ink-muted text-sm">Esta é a versão no ar.</p>
            ) : (
              <>
                {onAir ? <Diff onAir={onAir} selected={selected} /> : null}

                {outcome?.kind === "restored" ? (
                  <p role="status" className="text-good text-sm font-medium">
                    A v{outcome.version_number} está no ar.
                  </p>
                ) : null}
                {outcome?.kind === "error" ? (
                  <Alert>{outcome.message}</Alert>
                ) : null}

                {confirming ? (
                  <div
                    role="group"
                    aria-label="Confirmar restauração"
                    className="bg-alert-bg text-alert flex flex-col gap-3 rounded-[10px] px-4 py-3"
                  >
                    <p className="text-sm font-medium">
                      Restaurar a v{selected.version_number} move o que está no
                      ar. O rascunho não muda.
                    </p>
                    <div className="flex items-center gap-3">
                      <Button
                        type="button"
                        onClick={() => void restore(selected)}
                        disabled={busy}
                      >
                        {busy ? "Restaurando…" : "Confirmar"}
                      </Button>
                      <button
                        type="button"
                        onClick={() => setConfirming(false)}
                        disabled={busy}
                        className="text-ink-muted hover:text-ink text-sm font-bold"
                      >
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : (
                  <div>
                    <Button
                      type="button"
                      onClick={() => {
                        setOutcome(null);
                        setConfirming(true);
                      }}
                    >
                      Restaurar esta versão
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        </Card>
      ) : null}

      <Card>
        <CardHeader
          eyebrow="Plataforma"
          title="Versões da plataforma"
          note="Só leitura: a doutrina do produto entra por migration, e ninguém a restaura pelo painel."
        />
        {versions.platform.length > 0 ? (
          <VersionList
            rows={versions.platform}
            label="Versões da plataforma"
            selectedId={null}
            linkable={false}
          />
        ) : (
          <p className="text-ink-muted px-5 py-4 text-sm">
            Nenhuma versão da plataforma foi lida.
          </p>
        )}
      </Card>
    </div>
  );
}
