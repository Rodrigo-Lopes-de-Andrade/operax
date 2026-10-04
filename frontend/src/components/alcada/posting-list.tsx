"use client";

import { ClipboardCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import {
  postingErrorCode,
  postingErrorMessage,
  STALE_POSTING_CODES,
  type PostingListRow,
  type ReviewPostingApplied,
} from "@/lib/alcada/posting";
import { requestApiAsUser } from "@/lib/api";
import { formatDate, formatDayInTenantZone } from "@/lib/dp/format";
import {
  formatDuration,
  formatNumber,
  formatWeekday,
} from "@/lib/ponto/format";

type Notice = { tone: "done" | "failure"; text: string };

/**
 * O que falta digitar no Secullum, e o que já foi.
 *
 * A API devolve as aprovadas da competência numa lista só; a tela separa pela
 * marca (`posted_to_source_at`). A contagem de pendentes fica no alto e com
 * destaque: aprovação que não chega ao Secullum vale no painel e some no
 * registro oficial, e o RH só sabe o que falta se a tela disser.
 *
 * ⛔ A MARCA NÃO VOLTA ATRÁS
 * `fn_marcar_lancado` grava uma vez só e não existe desfazer (decisão do dono,
 * 01/10/2026). Por isso o botão abre a confirmação, que nomeia a pessoa e o dia
 * e diz que é definitivo, e só o segundo clique envia.
 *
 * Quem aprovou e quem lançou chegam como uuid — o nome mora em `auth.users`,
 * que a sessão não lê. A tela nunca mostra o uuid: mostra a data e, quando é o
 * próprio usuário, "por você".
 */
export function PostingList({
  rows,
  currentUserId,
}: {
  rows: PostingListRow[];
  currentUserId: string | null;
}) {
  const router = useRouter();
  const [marked, setMarked] = useState<
    Readonly<Record<string, ReviewPostingApplied>>
  >({});
  const [removed, setRemoved] = useState<ReadonlySet<string>>(new Set());
  const [notice, setNotice] = useState<Notice | null>(null);

  // A marca recebida agora vale até o refresh trazer a mesma linha lançada. O
  // `removed` só esconde pendente: depois do refresh, a linha que voltar
  // lançada aparece na outra seção.
  const merged = rows
    .filter(
      (row) => row.posted_to_source_at !== null || !removed.has(row.review_id),
    )
    .map((row) => {
      const mark = marked[row.review_id];
      return row.posted_to_source_at === null && mark
        ? {
            ...row,
            posted_to_source_at: mark.posted_to_source_at,
            posted_by: mark.posted_by,
          }
        : row;
    });

  const pending = merged.filter((row) => row.posted_to_source_at === null);
  const posted = merged.filter((row) => row.posted_to_source_at !== null);

  function done(row: PostingListRow, applied: ReviewPostingApplied) {
    setMarked((current) => ({ ...current, [row.review_id]: applied }));
    setNotice({
      tone: "done",
      text: `Justificativa de ${row.employee_name} marcada como lançada no Secullum.`,
    });
    router.refresh();
  }

  function stale(row: PostingListRow, message: string) {
    setRemoved((current) => new Set(current).add(row.review_id));
    setNotice({ tone: "failure", text: `${row.employee_name}: ${message}` });
    router.refresh();
  }

  const count = pending.length;

  return (
    <div className="flex flex-col gap-4">
      <section aria-labelledby="a-lancar" className="contents">
        <Card>
          <header className="border-line-subtle flex flex-wrap items-center justify-between gap-4 border-b px-5 py-4">
            <div>
              <h2 id="a-lancar" className="text-ink text-md font-extrabold">
                A lançar no Secullum
              </h2>
              <p className="text-ink-muted mt-0.5 max-w-2xl text-xs">
                Aprovadas no painel e ainda não digitadas no Secullum. Enquanto
                não forem lançadas lá, o registro oficial não muda.
              </p>
            </div>
            <div
              role="group"
              aria-label="Pendentes de lançamento"
              className={`flex items-baseline gap-2 rounded-[12px] px-4 py-2 ${
                count > 0 ? "bg-alert-bg text-alert" : "bg-good-bg text-good"
              }`}
            >
              <span className="text-3xl font-extrabold tabular-nums">
                {formatNumber(count)}
              </span>
              <span className="text-sm font-bold">
                {count === 1 ? "pendente" : "pendentes"}
              </span>
            </div>
          </header>

          {notice ? (
            <div className="px-5 pt-4">
              {notice.tone === "failure" ? (
                <Alert>{notice.text}</Alert>
              ) : (
                <p
                  role="status"
                  className="text-ink-muted text-sm font-semibold"
                >
                  {notice.text}
                </p>
              )}
            </div>
          ) : null}

          {count === 0 ? (
            <div className="px-5">
              <EmptyState
                icon={ClipboardCheck}
                tone="good"
                title="Nada a lançar no recorte"
                description="Toda aprovação desta competência já foi marcada como lançada no Secullum — ou nenhuma foi aprovada ainda."
              />
            </div>
          ) : (
            <ul
              aria-label="A lançar no Secullum"
              className="divide-line-subtle flex flex-col divide-y"
            >
              {pending.map((row) => (
                <PendingItem
                  key={row.review_id}
                  row={row}
                  currentUserId={currentUserId}
                  onPosted={(applied) => done(row, applied)}
                  onStale={(message) => stale(row, message)}
                />
              ))}
            </ul>
          )}
        </Card>
      </section>

      <section aria-labelledby="ja-lancadas" className="contents">
        <Card>
          <header className="border-line-subtle border-b px-5 py-4">
            <h2 id="ja-lancadas" className="text-ink text-md font-extrabold">
              Já lançadas
            </h2>
            <p className="text-ink-muted mt-0.5 text-xs">
              {posted.length === 1
                ? "1 aprovação marcada como lançada no Secullum."
                : `${formatNumber(posted.length)} aprovações marcadas como lançadas no Secullum.`}
            </p>
          </header>

          {posted.length === 0 ? (
            <p className="text-ink-muted px-5 py-4 text-sm">
              Nenhuma aprovação deste recorte foi marcada como lançada ainda.
            </p>
          ) : (
            <ul
              aria-label="Já lançadas"
              className="divide-line-subtle flex flex-col divide-y"
            >
              {posted.map((row) => (
                <Item key={row.review_id} row={row}>
                  <Facts row={row} currentUserId={currentUserId} />
                </Item>
              ))}
            </ul>
          )}

          <p className="text-ink-faint border-line-subtle border-t px-5 py-3 text-xs">
            Registro oficial de jornada permanece no Secullum. O painel aponta
            indícios.
          </p>
        </Card>
      </section>
    </div>
  );
}

function byYou(userId: string | null, currentUserId: string | null): string {
  return userId !== null && userId === currentUserId ? ", por você" : "";
}

function Item({ row, children }: { row: PostingListRow; children: ReactNode }) {
  const titleId = `lancamento-${row.review_id}`;

  return (
    <li aria-labelledby={titleId} className="flex flex-col gap-3 px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col">
          <h3 id={titleId} className="text-ink text-sm font-extrabold">
            {row.employee_name}
          </h3>
          <span className="text-ink-faint text-xs">
            {row.unit_name ?? "Sem unidade"}
          </span>
        </div>
        <div className="flex flex-col items-end">
          <span className="text-ink text-sm font-bold">
            {formatDate(row.reference_date)}
          </span>
          <span className="text-ink-faint text-xs">
            {formatWeekday(row.reference_date)}
          </span>
        </div>
      </div>
      {children}
    </li>
  );
}

function Facts({
  row,
  currentUserId,
}: {
  row: PostingListRow;
  currentUserId: string | null;
}) {
  return (
    <dl className="text-ink-body flex flex-wrap gap-x-6 gap-y-1 text-xs">
      <div className="flex gap-1.5">
        <dt className="text-ink-faint">Desvio</dt>
        <dd className="font-semibold">
          {row.type_description ?? "Sem desvio vinculado"}
        </dd>
      </div>
      <div className="flex gap-1.5">
        <dt className="text-ink-faint">Minutos</dt>
        <dd className="font-semibold tabular-nums">
          {row.minutes === null ? "—" : formatDuration(row.minutes)}
        </dd>
      </div>
      <div className="flex gap-1.5">
        <dt className="text-ink-faint">Aprovada em</dt>
        <dd className="font-semibold">
          {formatDayInTenantZone(row.reviewed_at)}
          {byYou(row.reviewed_by, currentUserId)}
        </dd>
      </div>
      {row.posted_to_source_at !== null ? (
        <div className="flex gap-1.5">
          <dt className="text-ink-faint">Lançada em</dt>
          <dd className="font-semibold">
            {formatDayInTenantZone(row.posted_to_source_at)}
            {byYou(row.posted_by, currentUserId)}
          </dd>
        </div>
      ) : null}
    </dl>
  );
}

function PendingItem({
  row,
  currentUserId,
  onPosted,
  onStale,
}: {
  row: PostingListRow;
  currentUserId: string | null;
  onPosted: (applied: ReviewPostingApplied) => void;
  onStale: (message: string) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSending(true);

    try {
      // O corpo é `{}`, obrigatório e fechado: quando e quem lançou são do
      // banco (`now()` e o `sub` do token), nunca do cliente.
      const applied = await requestApiAsUser<ReviewPostingApplied>(
        `/alcada/revisoes/${row.review_id}/lancamento`,
        { method: "POST", body: {} },
      );
      onPosted(applied);
    } catch (caught) {
      const code = postingErrorCode(caught);
      const message = postingErrorMessage(caught);

      if (code && STALE_POSTING_CODES.includes(code)) {
        onStale(message);
        return;
      }

      setError(message);
      setSending(false);
    }
  }

  return (
    <Item row={row}>
      <Facts row={row} currentUserId={currentUserId} />

      <blockquote className="border-line-subtle text-ink bg-muted rounded-[12px] border px-3 py-2 text-sm text-pretty whitespace-pre-line">
        {row.text}
      </blockquote>

      {confirming ? (
        <form
          onSubmit={confirm}
          aria-label="Confirmar lançamento no Secullum"
          className="border-line-subtle flex flex-col gap-3 rounded-[12px] border p-4"
        >
          {/* ⚠️ A frase nomeia a pessoa e o dia ANTES do envio: a marca é
              definitiva, e uma ação sem volta sobre alguém diz sobre quem é. */}
          <p className="text-ink text-sm text-pretty">
            Marcar a justificativa de <strong>{row.employee_name}</strong> em{" "}
            {formatDate(row.reference_date)} como lançada no Secullum? Faça isso
            só depois de digitar a decisão no Secullum. A marca é definitiva e
            não pode ser desfeita.
          </p>

          {error ? <Alert>{error}</Alert> : null}

          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={sending}>
              {sending ? "Marcando…" : "Confirmar: já lancei no Secullum"}
            </Button>
            <button
              type="button"
              onClick={() => {
                setConfirming(false);
                setError(null);
              }}
              disabled={sending}
              className="text-ink-muted hover:text-ink text-sm font-bold"
            >
              Cancelar
            </button>
          </div>
        </form>
      ) : (
        <div>
          <Button onClick={() => setConfirming(true)}>
            Marcar como lançado no Secullum
          </Button>
        </div>
      )}
    </Item>
  );
}
