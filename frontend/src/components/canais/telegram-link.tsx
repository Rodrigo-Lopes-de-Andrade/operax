"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { ApiError, requestApiAsUser } from "@/lib/api";
import { CHANNEL_LABEL } from "@/lib/canais/labels";
import type {
  InviteIssued,
  InviteRequest,
  TelegramLink,
} from "@/lib/canais/queries";
import { formatDayInTenantZone } from "@/lib/dp/format";
import { formatClock } from "@/lib/ponto/format";

type Action = "invite" | "revoke";

/** O desfecho do último clique: um só, e nunca um sucesso ao lado de um erro. */
type Outcome =
  | { kind: "invited"; issued: InviteIssued }
  | { kind: "revoked" }
  | { kind: "error"; message: string };

const BUSY: Record<Action, string> = {
  invite: "Enviando convite…",
  revoke: "Desvinculando…",
};

const FAILED: Record<Action, string> = {
  invite: "Não consegui enviar o convite.",
  revoke: "Não consegui desvincular o Telegram.",
};

/**
 * A decisão do dono (16/09/2026): a adesão é voluntária. A frase fica em todo
 * estado do cartão — inclusive quando há convite em aberto — para que ninguém
 * leia "convite enviado" como "falta responder".
 */
const VOLUNTARY =
  "A adesão é voluntária: quem não aderir continua recebendo pelo WhatsApp.";

/** Dia e hora no fuso do tenant — a mesma forma da tela de Conexões. */
function at(timestamp: string): string {
  return `${formatDayInTenantZone(timestamp)} às ${formatClock(timestamp)}`;
}

/**
 * Os três estados de um vínculo, lidos de `linked` primeiro e das datas
 * depois. `opted_in_at` preenchido com `linked: false` é um vínculo que
 * existiu e foi revogado — a data não é o fato, o booleano é.
 */
type State = "linked" | "invited" | "not_joined";

function stateOf(link: TelegramLink): State {
  if (link.linked) {
    return "linked";
  }

  return link.invite_open_until ? "invited" : "not_joined";
}

const BADGE: Record<State, { tone: Tone; label: string }> = {
  linked: { tone: "good", label: "Vinculado" },
  invited: { tone: "neutral", label: "Convite enviado" },
  not_joined: { tone: "neutral", label: "Não aderiu" },
};

const ACTION: Record<State, Action> = {
  linked: "revoke",
  invited: "invite",
  not_joined: "invite",
};

const BUTTON: Record<State, string> = {
  linked: "Desvincular",
  invited: "Enviar outro convite",
  not_joined: "Convidar pelo WhatsApp",
};

/**
 * A linha de contexto abaixo do badge — a data que explica o estado, no fuso
 * do tenant. Sem data não há linha: "Vinculado" sem `opted_in_at` é só o
 * badge, e "Não aderiu" sem `revoked_at` também.
 */
function Context({ link, state }: { link: TelegramLink; state: State }) {
  const text =
    state === "linked"
      ? link.opted_in_at
        ? `desde ${at(link.opted_in_at)}`
        : null
      : state === "invited"
        ? `válido até ${formatDayInTenantZone(link.invite_open_until)}`
        : link.revoked_at
          ? `revogado em ${formatDayInTenantZone(link.revoked_at)}`
          : null;

  return text ? <p className="text-ink-muted text-sm">{text}</p> : null;
}

/**
 * O bloco do Telegram na ficha do colaborador — SPEC-CANAIS §3.3, regra 5:
 * vínculo visível e revogável. Vínculo silencioso não tem como ser contestado
 * por quem foi prejudicado; este cartão é o lugar em que ele deixa de ser
 * silencioso.
 *
 * Três estados, decididos por `linked` e pelas datas (ver `stateOf`), e um
 * quarto que é a API não ter respondido (`link === null`): a frase, e botão
 * nenhum. O botão existe só para quem escreve (`canWrite`, o `can_write` da
 * ficha) e é um por estado — "Desvincular", "Enviar outro convite", "Convidar
 * pelo WhatsApp".
 *
 * O convite (regra 4) sai por `POST /canais/telegram/convites` com
 * `{employee_id, contact_id: null}` e viaja **por WhatsApp para o número em
 * cadastro**: a resposta traz o número mascarado e a validade, e **não traz o
 * link** — quem abre o link vira o destinatário, então o painel nunca o vê, e
 * este cartão não tem onde mostrá-lo. O `detail` do 422 (`not_a_person`,
 * `no_phone`, `invalid_phone`, `no_bot`, `no_whatsapp`, `no_invite_template`)
 * já vem em pt-BR e é mostrado como veio. ⏳ O `code` que acompanha o
 * `detail` não atravessa `ApiError` hoje; o atalho para a aba de templates no
 * `no_invite_template` espera por ele.
 *
 * Desvincular é `POST /canais/telegram/vinculos/{id}/revogar`: o histórico
 * fica (a identidade é revogada, nunca apagada), e os avisos voltam para o
 * WhatsApp sozinhos (§8). Nos dois casos a tela mostra o que a prop trouxer
 * depois do `router.refresh()`, sem cópia local do vínculo.
 *
 * Nada de `chat_id`, em estado nenhum — a API não o devolve, e o tipo não o
 * tem.
 */
export function TelegramLinkCard({
  employeeId,
  link,
  canWrite,
}: {
  employeeId: string;
  link: TelegramLink | null;
  canWrite: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<Action | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  const state = link ? stateOf(link) : null;

  async function run(action: Action) {
    setBusy(action);
    setOutcome(null);

    try {
      if (action === "invite") {
        const body: InviteRequest = {
          employee_id: employeeId,
          contact_id: null,
        };
        const issued = await requestApiAsUser<InviteIssued>(
          "/canais/telegram/convites",
          { method: "POST", body },
        );
        setOutcome({ kind: "invited", issued });
      } else {
        await requestApiAsUser<TelegramLink>(
          `/canais/telegram/vinculos/${employeeId}/revogar`,
          { method: "POST" },
        );
        setOutcome({ kind: "revoked" });
      }
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
    <Card>
      <CardHeader
        eyebrow="Canal"
        title={CHANNEL_LABEL.telegram}
        action={
          state ? (
            <Badge tone={BADGE[state].tone} dot>
              {BADGE[state].label}
            </Badge>
          ) : undefined
        }
      />
      <div className="flex flex-col gap-3 px-5 py-4">
        {link && state ? (
          <Context link={link} state={state} />
        ) : (
          <p className="text-ink-muted text-sm text-pretty">
            Não deu para ler o vínculo do Telegram agora.
          </p>
        )}

        <p className="text-ink-muted text-xs text-pretty">{VOLUNTARY}</p>

        {outcome?.kind === "invited" ? (
          <p role="status" className="text-good text-sm font-medium">
            Convite enviado para {outcome.issued.destination_masked}, válido até{" "}
            {formatDayInTenantZone(outcome.issued.expires_at)}.
          </p>
        ) : null}
        {outcome?.kind === "revoked" ? (
          <p role="status" className="text-good text-sm font-medium">
            Telegram desvinculado. Os avisos voltam a sair pelo WhatsApp.
          </p>
        ) : null}
        {outcome?.kind === "error" ? <Alert>{outcome.message}</Alert> : null}

        {canWrite && state ? (
          <div>
            <Button
              type="button"
              onClick={() => void run(ACTION[state])}
              disabled={busy !== null}
            >
              {busy ? BUSY[busy] : BUTTON[state]}
            </Button>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
