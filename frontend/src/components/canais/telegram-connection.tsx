"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError, requestApiAsUser } from "@/lib/api";
import type { TelegramChannel } from "@/lib/canais/queries";

type Action = "connect" | "disconnect";

/** O desfecho do último clique: feito, ou não — nunca os dois ao mesmo tempo. */
type Outcome =
  { kind: "done"; action: Action } | { kind: "error"; message: string };

const ROUTE: Record<Action, string> = {
  connect: "/canais/telegram/conectar",
  disconnect: "/canais/telegram/desconectar",
};

const BUSY: Record<Action, string> = {
  connect: "Registrando no Telegram…",
  disconnect: "Removendo…",
};

const DONE: Record<Action, string> = {
  connect: "Bot conectado. O Telegram vai chamar o endereço novo.",
  disconnect: "Bot desconectado. O endereço antigo deixou de existir.",
};

const FAILED: Record<Action, string> = {
  connect: "Não consegui registrar o bot no Telegram.",
  disconnect: "Não consegui remover o registro no Telegram.",
};

/** Um valor com o meio elidido — seis de cada lado. */
function truncateMiddle(value: string, keep = 6): string {
  return value.length <= keep * 2 + 1
    ? value
    : `${value.slice(0, keep)}…${value.slice(-keep)}`;
}

/**
 * O endereço com a cauda rotativa (o último segmento) truncada no meio: a
 * base e a rota ficam legíveis, e o token não fica inteiro na tela.
 */
function truncateTail(url: string): string {
  const at = url.lastIndexOf("/") + 1;

  return `${url.slice(0, at)}${truncateMiddle(url.slice(at))}`;
}

/**
 * O endereço que o Telegram chama (SPEC-CANAIS §6), **como o backend o
 * registrou no `setWebhook`** — a tela não o compõe, mostra o que veio. Não é
 * segredo — o segredo vai no header —, mas também não precisa ficar inteiro
 * na tela: a cauda aparece truncada no meio e o endereço inteiro só existe no
 * clique de copiar.
 */
function WebhookAddress({ url }: { url: string }) {
  const [copied, setCopied] = useState<"idle" | "done" | "failed">("idle");

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied("done");
    } catch {
      setCopied("failed");
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <code className="text-ink font-mono text-xs break-all">
        {truncateTail(url)}
      </code>
      <button
        type="button"
        onClick={() => void copy()}
        aria-label="Copiar endereço do webhook"
        className="text-brand-strong text-xs font-bold underline"
      >
        {copied === "done"
          ? "copiado"
          : copied === "failed"
            ? "não deu para copiar"
            : "copiar"}
      </button>
      {/* O `aria-label` fixo é o nome do botão; o desfecho precisa de uma
          região viva própria, ou o leitor de tela nunca ouve "copiado". Só
          existe com desfecho: o `role="status"` da ação de conectar é outro. */}
      {copied === "done" ? (
        <span role="status" className="sr-only">
          Endereço copiado.
        </span>
      ) : copied === "failed" ? (
        <span role="status" className="sr-only">
          Não deu para copiar o endereço.
        </span>
      ) : null}
    </div>
  );
}

/**
 * O registro do bot no Telegram — o endereço que ele chama, e a ação que o
 * cria ou remove.
 *
 * Caminho 2, sem corpo: `POST /canais/telegram/conectar` registra o webhook
 * e `POST /canais/telegram/desconectar` o remove **e rotaciona a cauda** do
 * endereço (SPEC §6) — reconectar não devolve o antigo, e a tela mostra o
 * que a prop trouxer depois do `router.refresh()`, sem cópia local: uma
 * cópia ficaria com o endereço que deixou de existir.
 *
 * O botão existe só para quem escreve (`canWrite`), e é um só: "Conectar bot"
 * quando não há registro, "Desconectar" quando há. Não existe "reconectar" —
 * nem aqui nem no vigia (§7): religar sozinho um canal que caiu por bloqueio
 * da plataforma é o que transforma suspensão em banimento. Quem religa é uma
 * pessoa, em dois cliques, olhando o motivo.
 *
 * O `detail` do 422 (`no_public_url`, `no_credential`, `unauthorized`,
 * `unreachable`, `malformed`) já vem em pt-BR e é mostrado como veio.
 */
export function TelegramConnection({
  channel,
  canWrite,
}: {
  channel: TelegramChannel;
  canWrite: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<Action | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  const action: Action = channel.webhook_configured ? "disconnect" : "connect";

  async function run() {
    setBusy(action);
    setOutcome(null);

    try {
      await requestApiAsUser<TelegramChannel>(ROUTE[action], {
        method: "POST",
      });
      setOutcome({ kind: "done", action });
      router.refresh();
    } catch (caught) {
      setOutcome({
        kind: "error",
        message:
          caught instanceof ApiError && caught.detail
            ? caught.detail
            : FAILED[action],
      });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Webhook
        </p>
        {channel.webhook_configured ? (
          channel.webhook_url ? (
            <WebhookAddress
              key={channel.webhook_url}
              url={channel.webhook_url}
            />
          ) : (
            <p className="text-ink-muted text-sm">
              Registrado no Telegram; o endereço não veio na resposta.
            </p>
          )
        ) : (
          <p className="text-ink-muted text-sm text-pretty">
            O bot ainda não está registrado no Telegram. Sem registro, nenhuma
            adesão chega.
          </p>
        )}
      </div>

      {outcome?.kind === "done" ? (
        <p role="status" className="text-good text-sm font-medium">
          {DONE[outcome.action]}
        </p>
      ) : null}
      {outcome?.kind === "error" ? <Alert>{outcome.message}</Alert> : null}

      {canWrite ? (
        <div>
          <Button
            type="button"
            onClick={() => void run()}
            disabled={busy !== null}
          >
            {busy
              ? BUSY[busy]
              : action === "connect"
                ? "Conectar bot"
                : "Desconectar"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
