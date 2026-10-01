"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ClipboardCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import {
  BLOCKED_REASON_LABEL,
  reviewErrorCode,
  reviewErrorMessage,
  STALE_REVIEW_CODES,
  type ApprovalQueueRow,
  type ReviewApplied,
  type ReviewDecision,
} from "@/lib/alcada/review";
import { requestApiAsUser } from "@/lib/api";
import { formatDate, formatDayInTenantZone } from "@/lib/dp/format";
import {
  formatDuration,
  formatNumber,
  formatWeekday,
} from "@/lib/ponto/format";

const SECONDARY =
  "border-line-strong text-ink hover:bg-muted inline-flex h-10 items-center justify-center rounded-full border px-5 text-sm font-bold transition disabled:cursor-not-allowed disabled:opacity-60";

type Notice = { tone: "done" | "failure"; text: string };

/**
 * A fila da alçada: o RH (ou o owner) aprova ou reprova a justificativa que o
 * supervisor escreveu.
 *
 * ⛔ A REVISÃO NÃO VOLTA ATRÁS
 * `app.justification_review` tem uma linha por justificativa e nenhum update.
 * Por isso nenhum clique grava direto: o botão abre a confirmação, que nomeia
 * a pessoa e o dia e diz o que acontece com o indício, e só o segundo clique
 * envia. Reprovado, o supervisor escreve uma justificativa nova — que ganha a
 * própria revisão.
 *
 * Quem decide se a linha pode ser revisada é o backend (`can_review`), com a
 * mesma regra da RPC. A tela só esconde os botões e diz o motivo; a RPC recusa
 * de novo se a tela estiver velha, e a frase da recusa é a mesma.
 */
export function ApprovalQueue({ rows }: { rows: ApprovalQueueRow[] }) {
  const router = useRouter();
  const [removed, setRemoved] = useState<ReadonlySet<string>>(new Set());
  const [notice, setNotice] = useState<Notice | null>(null);

  const visible = rows.filter((row) => !removed.has(row.justification_id));

  function drop(id: string) {
    setRemoved((current) => new Set(current).add(id));
    router.refresh();
  }

  function reviewed(row: ApprovalQueueRow, decision: ReviewDecision) {
    drop(row.justification_id);
    setNotice({
      tone: "done",
      text:
        decision === "approved"
          ? `Justificativa de ${row.employee_name} aprovada.`
          : `Justificativa de ${row.employee_name} reprovada. Ela volta para o supervisor.`,
    });
  }

  function stale(row: ApprovalQueueRow, message: string) {
    drop(row.justification_id);
    setNotice({ tone: "failure", text: `${row.employee_name}: ${message}` });
  }

  const count = visible.length;

  return (
    <Card>
      <CardHeader
        eyebrow="Aprovação"
        title={
          count === 1
            ? "1 justificativa esperando revisão"
            : `${formatNumber(count)} justificativas esperando revisão`
        }
        note="Aprovar faz o indício contar como justificado; reprovar o devolve ao supervisor, com o motivo."
      />

      {notice ? (
        <div className="px-5 pt-4">
          {notice.tone === "failure" ? (
            <Alert>{notice.text}</Alert>
          ) : (
            <p role="status" className="text-ink-muted text-sm font-semibold">
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
            title="Nada esperando revisão no recorte"
            description="Toda justificativa desta competência já foi revisada — ou nenhuma foi escrita ainda. Troque a competência ou limpe o recorte para ver outras."
          />
        </div>
      ) : (
        <ul
          aria-label="Justificativas esperando revisão"
          className="divide-line-subtle flex flex-col divide-y"
        >
          {visible.map((row) => (
            <ReviewItem
              key={row.justification_id}
              row={row}
              onReviewed={(decision) => reviewed(row, decision)}
              onStale={(message) => stale(row, message)}
            />
          ))}
        </ul>
      )}

      <p className="text-ink-faint border-line-subtle border-t px-5 py-3 text-xs">
        Registro oficial de jornada permanece no Secullum. O painel aponta
        indícios.
      </p>
    </Card>
  );
}

function ReviewItem({
  row,
  onReviewed,
  onStale,
}: {
  row: ApprovalQueueRow;
  onReviewed: (decision: ReviewDecision) => void;
  onStale: (message: string) => void;
}) {
  const [mode, setMode] = useState<ReviewDecision | null>(null);
  const titleId = `revisao-${row.justification_id}`;

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
          <dt className="text-ink-faint">Autor</dt>
          <dd className="font-semibold">
            {row.author_name ?? "Autor não registrado"}, em{" "}
            {formatDayInTenantZone(row.created_at)}
          </dd>
        </div>
      </dl>

      <blockquote className="border-line-subtle text-ink bg-muted rounded-[12px] border px-3 py-2 text-sm text-pretty whitespace-pre-line">
        {row.text}
      </blockquote>

      {!row.can_review ? (
        <p className="flex flex-wrap items-center gap-2 text-xs">
          <Badge tone="neutral">Sem alçada</Badge>
          <span className="text-ink-muted">
            {row.blocked_reason
              ? BLOCKED_REASON_LABEL[row.blocked_reason]
              : "Você não pode revisar esta justificativa."}
          </span>
        </p>
      ) : mode ? (
        <ConfirmReview
          key={mode}
          row={row}
          decision={mode}
          onCancel={() => setMode(null)}
          onReviewed={onReviewed}
          onStale={onStale}
        />
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setMode("approved")}>Aprovar</Button>
          <button
            type="button"
            onClick={() => setMode("rejected")}
            className={SECONDARY}
          >
            Reprovar
          </button>
        </div>
      )}
    </li>
  );
}

const MAX_REASON = 2000;

const approveSchema = z.object({
  motivo: z
    .string()
    .max(MAX_REASON, `O motivo cabe em ${MAX_REASON} caracteres.`),
});

// A RPC recusa `rejection_needs_reason` quando o motivo é vazio depois do
// `btrim`. Esta é a cópia conveniente, que poupa a viagem — a regra é a de lá,
// e o 422 continua tratado abaixo.
const rejectSchema = z.object({
  motivo: z
    .string()
    .max(MAX_REASON, `O motivo cabe em ${MAX_REASON} caracteres.`)
    .refine(
      (value) => value.trim().length > 0,
      "Para reprovar, escreva o motivo — é ele que o supervisor vai ler.",
    ),
});

function ConfirmReview({
  row,
  decision,
  onCancel,
  onReviewed,
  onStale,
}: {
  row: ApprovalQueueRow;
  decision: ReviewDecision;
  onCancel: () => void;
  onReviewed: (decision: ReviewDecision) => void;
  onStale: (message: string) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const rejecting = decision === "rejected";
  const fieldId = `motivo-${row.justification_id}`;
  const errorId = `${fieldId}-erro`;

  const {
    register,
    handleSubmit,
    setError: setFieldError,
    formState,
  } = useForm({
    resolver: zodResolver(rejecting ? rejectSchema : approveSchema),
    defaultValues: { motivo: "" },
  });

  const onSubmit = handleSubmit(async ({ motivo }) => {
    setError(null);

    try {
      await requestApiAsUser<ReviewApplied>(
        `/alcada/justificativas/${row.justification_id}/revisao`,
        {
          method: "POST",
          body: {
            decisao: decision,
            ...(motivo.trim() ? { motivo: motivo.trim() } : {}),
          },
        },
      );
      onReviewed(decision);
    } catch (caught) {
      const code = reviewErrorCode(caught);
      const message = reviewErrorMessage(caught);

      if (code === "rejection_needs_reason") {
        setFieldError("motivo", { message });
        return;
      }

      if (code && STALE_REVIEW_CODES.includes(code)) {
        onStale(message);
        return;
      }

      setError(message);
    }
  });

  const fieldError = formState.errors.motivo?.message;

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      aria-label={rejecting ? "Confirmar reprovação" : "Confirmar aprovação"}
      className="border-line-subtle flex flex-col gap-3 rounded-[12px] border p-4"
    >
      {/* ⚠️ A frase nomeia a pessoa e o dia ANTES do envio: a revisão não
          volta atrás, e uma ação irreversível sobre alguém tem de dizer sobre
          quem é. */}
      <p className="text-ink text-sm text-pretty">
        {rejecting ? "Reprovar" : "Aprovar"} a justificativa de{" "}
        <strong>{row.employee_name}</strong> em {formatDate(row.reference_date)}
        ?{" "}
        {rejecting
          ? "O indício volta para o supervisor, que precisa escrever uma justificativa nova."
          : "O indício passa a contar como justificado."}{" "}
        A revisão fica registrada com o seu nome e não pode ser desfeita.
      </p>

      <div className="flex flex-col gap-1.5">
        <label
          htmlFor={fieldId}
          className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase"
        >
          {rejecting ? "Motivo da reprovação" : "Observação (opcional)"}
        </label>
        <textarea
          id={fieldId}
          rows={3}
          maxLength={MAX_REASON}
          aria-invalid={fieldError ? true : undefined}
          aria-describedby={fieldError ? errorId : undefined}
          className="border-line-subtle text-ink focus:border-brand-strong w-full rounded-[12px] border px-3 py-2 text-sm outline-none"
          placeholder={
            rejecting
              ? "A saída antecipada não foi autorizada pelo gestor."
              : undefined
          }
          {...register("motivo")}
        />
        {fieldError ? (
          <p id={errorId} className="text-bad text-xs font-medium">
            {fieldError}
          </p>
        ) : null}
      </div>

      {error ? <Alert>{error}</Alert> : null}

      <div className="flex flex-wrap items-center gap-2">
        {rejecting ? (
          <button
            type="submit"
            disabled={formState.isSubmitting}
            className={SECONDARY}
          >
            {formState.isSubmitting ? "Reprovando…" : "Confirmar reprovação"}
          </button>
        ) : (
          <Button type="submit" disabled={formState.isSubmitting}>
            {formState.isSubmitting ? "Aprovando…" : "Confirmar aprovação"}
          </Button>
        )}
        <button
          type="button"
          onClick={onCancel}
          disabled={formState.isSubmitting}
          className="text-ink-muted hover:text-ink text-sm font-bold"
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}
