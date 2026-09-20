"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { ApiError } from "@/lib/api";
import {
  publishFailureMessage,
  publishPrompt,
  saveDraft,
  type PlatformLayer,
  type PromptScreen,
  type TenantLayer,
  type VersionsScreen,
} from "@/lib/assistente/config";
import { formatDayInTenantZone } from "@/lib/dp/format";
import { formatClock } from "@/lib/ponto/format";

/**
 * A aba Configuração: a camada da plataforma em leitura, a versão do cliente
 * no ar, e o rascunho — o único texto que se edita.
 *
 * ⛔ O CASO DA SPEC-AGENTE §2, E O QUE ESTA TELA EXISTE PARA NÃO ESCONDER
 * Depois de um rollback o rascunho fica mais novo do que o que está no ar. O
 * backend diz isso em `draft_ahead_of_air`, e aqui isso vira um aviso com os
 * dois números **e as duas caixas visíveis ao mesmo tempo**: o texto no ar e o
 * rascunho. O modo de falhar é o clique que substitui o texto bom pelo que a
 * tela não mostrava — então nenhuma das duas se dobra enquanto o aviso existe.
 *
 * PUBLICAR PEDE O RASCUNHO SALVO, E NÃO SALVA POR CONTA PRÓPRIA
 * O texto na caixa e o rascunho no servidor são duas coisas até "Salvar
 * rascunho" as igualar. Publicar com a caixa diferente do que foi salvo não
 * chama a API: a tela pede para salvar. Salvar-e-publicar num clique só
 * transformaria uma edição que a pessoa só queria guardar no texto que passa
 * a governar o assistente — e publicar é a única ação daqui que muda o que o
 * runtime lê.
 *
 * O limite do contador vem da API (`max_length`), nunca daqui: o dono dele é o
 * banco.
 */

type Outcome =
  | { kind: "saved" }
  | { kind: "published"; version_number: number }
  | { kind: "notice"; message: string }
  | { kind: "error"; message: string };

const SAVE_FAILED = "Não consegui salvar o rascunho.";
const SAVE_FIRST = "Salve o rascunho antes de publicar.";

const TEXT_CLASS =
  "bg-control border-control-line text-ink placeholder:text-ink-faint rounded-[10px] border px-3 py-2 font-mono text-sm outline-none focus-visible:border-transparent";

/**
 * O número da versão de que o rascunho partiu, pela lista do histórico: a
 * API manda o id, e o aviso precisa do número. Nulo quando o rascunho nasceu
 * antes da primeira publicação, ou quando a lista não veio.
 */
function originNumber(
  frozenFrom: string | null,
  versions: VersionsScreen | null,
): number | null {
  if (frozenFrom === null || versions === null) {
    return null;
  }

  return (
    versions.tenant.find((row) => row.version_id === frozenFrom)
      ?.version_number ?? null
  );
}

function aheadOfAirPhrase(
  frozenFrom: string | null,
  origin: number | null,
  tenant: TenantLayer | null,
): string {
  const from =
    origin !== null
      ? `Seu rascunho partiu da v${origin}.`
      : frozenFrom === null
        ? "Seu rascunho partiu de antes da primeira versão publicada."
        : "Seu rascunho partiu de uma versão que não está no histórico.";
  const air = tenant
    ? `No ar está a v${tenant.version_number}. Publicar substitui a v${tenant.version_number}.`
    : "No ar está só a camada da plataforma. Publicar põe o rascunho no ar.";

  return `${from} ${air}`;
}

function PlatformCard({ platform }: { platform: PlatformLayer }) {
  return (
    <Card>
      <CardHeader
        eyebrow="Plataforma"
        title={`Camada da plataforma — v${platform.version_number}`}
        note="É a doutrina do produto: vale para todos os clientes e não se edita pelo painel."
      />
      <div className="flex flex-col gap-3 px-5 py-4">
        <dl className="text-ink-muted flex flex-wrap gap-x-6 gap-y-1 text-xs">
          <div className="flex gap-1">
            <dt className="font-bold">Provedor:</dt>
            <dd>{platform.provider ?? "padrão da instalação"}</dd>
          </div>
          <div className="flex gap-1">
            <dt className="font-bold">Modelo:</dt>
            <dd>{platform.model ?? "padrão da instalação"}</dd>
          </div>
          <div className="flex gap-1">
            <dt className="font-bold">Idas à ferramenta por turno:</dt>
            <dd>{platform.max_steps ?? "sem teto"}</dd>
          </div>
          <div className="flex gap-1">
            <dt className="font-bold">Publicada em:</dt>
            <dd>
              {formatDayInTenantZone(platform.created_at)} às{" "}
              {formatClock(platform.created_at)}
            </dd>
          </div>
        </dl>
        <details>
          <summary className="text-brand-strong cursor-pointer text-xs font-bold">
            Ver o texto inteiro
          </summary>
          <pre className="text-ink mt-3 font-mono text-sm whitespace-pre-wrap">
            {platform.content}
          </pre>
        </details>
      </div>
    </Card>
  );
}

/** O texto no ar, como o runtime o lê agora. */
function OnAirText({ tenant }: { tenant: TenantLayer }) {
  return (
    <pre
      aria-label={`Texto no ar — v${tenant.version_number}`}
      className="bg-muted text-ink rounded-[10px] px-3 py-2 font-mono text-sm whitespace-pre-wrap"
    >
      {tenant.content}
    </pre>
  );
}

export function PromptEditor({
  screen,
  versions,
}: {
  screen: PromptScreen;
  versions: VersionsScreen | null;
}) {
  const router = useRouter();
  const [text, setText] = useState(screen.draft?.content ?? "");
  // O que o servidor tem: nulo enquanto nenhum rascunho foi salvo.
  const [saved, setSaved] = useState<string | null>(
    screen.draft?.content ?? null,
  );
  const [busy, setBusy] = useState<"save" | "publish" | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  const ahead = screen.draft_ahead_of_air;
  const dirty = saved === null || text !== saved;

  async function save() {
    setBusy("save");
    setOutcome(null);

    try {
      const draft = await saveDraft(text);
      setSaved(draft.content);
      setOutcome({ kind: "saved" });
      router.refresh();
    } catch (caught) {
      setOutcome({
        kind: "error",
        message:
          caught instanceof ApiError && caught.detail
            ? caught.detail
            : SAVE_FAILED,
      });
    } finally {
      setBusy(null);
    }
  }

  async function publish() {
    setOutcome(null);

    if (dirty) {
      setOutcome({ kind: "notice", message: SAVE_FIRST });
      return;
    }

    setBusy("publish");

    try {
      const result = await publishPrompt();
      setOutcome({ kind: "published", version_number: result.version_number });
      router.refresh();
    } catch (caught) {
      setOutcome({ kind: "error", message: publishFailureMessage(caught) });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <PlatformCard platform={screen.platform} />

      <Card>
        <CardHeader
          eyebrow="Cliente"
          title="Camada do cliente"
          note="Vocabulário local, contexto da operação e tom. Ela se soma à camada da plataforma — nunca a substitui."
        />
        <div className="flex flex-col gap-4 px-5 py-4">
          {ahead ? (
            <p
              role="status"
              className="bg-alert-bg text-alert rounded-[10px] px-3 py-2 text-sm font-medium"
            >
              {aheadOfAirPhrase(
                screen.draft?.frozen_from_version_id ?? null,
                originNumber(
                  screen.draft?.frozen_from_version_id ?? null,
                  versions,
                ),
                screen.tenant,
              )}
            </p>
          ) : null}

          {screen.tenant ? (
            <section
              aria-labelledby="assistant-on-air"
              className="flex flex-col gap-2"
            >
              <h3
                id="assistant-on-air"
                className="text-ink flex items-center gap-2 text-sm font-bold"
              >
                No ar — v{screen.tenant.version_number}
                <Badge tone="good" dot>
                  No ar
                </Badge>
                <span className="text-ink-faint text-xs font-normal">
                  desde {formatDayInTenantZone(screen.tenant.created_at)} às{" "}
                  {formatClock(screen.tenant.created_at)}
                </span>
              </h3>
              {ahead ? (
                <OnAirText tenant={screen.tenant} />
              ) : (
                <details>
                  <summary className="text-brand-strong cursor-pointer text-xs font-bold">
                    Ver o texto no ar
                  </summary>
                  <div className="mt-2">
                    <OnAirText tenant={screen.tenant} />
                  </div>
                </details>
              )}
            </section>
          ) : (
            <p className="text-ink-muted text-sm">
              Nenhuma versão do cliente no ar: o assistente roda só com a camada
              da plataforma.
            </p>
          )}

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="assistant-draft"
              className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase"
            >
              Rascunho
            </label>
            <textarea
              id="assistant-draft"
              rows={12}
              value={text}
              maxLength={screen.max_length}
              disabled={busy !== null}
              aria-describedby="assistant-draft-count"
              placeholder="Vocabulário da operação, nomes das unidades como o time as chama, o que o assistente deve chamar de desvio…"
              onChange={(event) => setText(event.target.value)}
              className={`${TEXT_CLASS} disabled:opacity-60`}
            />
            <p
              id="assistant-draft-count"
              className="text-ink-faint text-xs tabular-nums"
            >
              {text.length} / {screen.max_length}
            </p>
            {screen.draft ? (
              <p className="text-ink-faint text-xs">
                Rascunho salvo em{" "}
                {formatDayInTenantZone(screen.draft.updated_at)} às{" "}
                {formatClock(screen.draft.updated_at)}.
              </p>
            ) : null}
          </div>

          {outcome?.kind === "saved" ? (
            <p role="status" className="text-good text-sm font-medium">
              Rascunho salvo.
            </p>
          ) : null}
          {outcome?.kind === "published" ? (
            <p role="status" className="text-good text-sm font-medium">
              Publicada a v{outcome.version_number}.
            </p>
          ) : null}
          {outcome?.kind === "notice" ? (
            <p
              role="status"
              className="bg-alert-bg text-alert rounded-[10px] px-3 py-2 text-sm font-medium"
            >
              {outcome.message}
            </p>
          ) : null}
          {outcome?.kind === "error" ? <Alert>{outcome.message}</Alert> : null}

          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              onClick={() => void save()}
              disabled={busy !== null || text.length === 0 || !dirty}
            >
              {busy === "save" ? "Salvando…" : "Salvar rascunho"}
            </Button>
            <Button
              type="button"
              onClick={() => void publish()}
              disabled={busy !== null}
            >
              {busy === "publish" ? "Publicando…" : "Publicar"}
            </Button>
            <span className="text-ink-faint text-xs">
              {dirty
                ? "Publicar usa o rascunho salvo — salve antes."
                : "Publicar congela o rascunho salvo numa versão e a põe no ar."}
            </span>
          </div>
        </div>
      </Card>
    </div>
  );
}
