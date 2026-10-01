"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError, requestApiAsUser } from "@/lib/api";

/**
 * A justificativa do supervisor sobre um indício — que nasce `pending`.
 *
 * Desde a P1.2 o supervisor explica e o RH decide: `POST
 * /ocorrencias/{id}/justificativa` recebe só `{ text }` e grava sempre
 * `pending`. Aceitar ou reprovar é do RH, por `fn_revisar_justificativa`, numa
 * tela própria — este componente não escolhe veredito, e mandar `status` no
 * corpo passou a ser recusado pelo backend.
 *
 * A LINHA GRAVADA NÃO VOLTA ATRÁS
 * O banco só concede `insert` em `app.justification` — não há update. Por isso a
 * tela nomeia a pessoa afetada antes do envio e o botão diz o que vai
 * acontecer. Mudar de ideia escreve outra linha, e é correto que escreva: a
 * explicação dada uma vez é justamente o que a tabela existe para guardar.
 */
export function JustificationVerdict({
  deviationEventId,
  employeeName,
}: {
  deviationEventId: string;
  employeeName: string;
}) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState<string | null>(null);

  // O backend recusa abaixo de 3 (`JustificationVerdict.text`). Recusar aqui
  // também poupa a viagem, mas a regra continua sendo a de lá — esta é a cópia
  // conveniente, não a fonte.
  const tooShort = text.trim().length < 3;

  async function record() {
    setBusy(true);
    setError(null);
    setApplied(null);

    try {
      await requestApiAsUser<{ justification_id: string }>(
        `/ocorrencias/${deviationEventId}/justificativa`,
        { method: "POST", body: { text: text.trim() } },
      );

      setApplied("Justificativa enviada para aprovação do RH.");
      setText("");
      router.refresh();
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Não foi possível enviar. Tente de novo.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="border-line-subtle flex flex-col gap-3 rounded-[14px] border p-5">
      <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
        Justificativa
      </p>

      <label className="flex flex-col gap-1.5">
        <span className="text-ink-muted text-xs">O que explica o indício</span>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={3}
          maxLength={2000}
          className="border-line-subtle text-ink focus:border-brand-strong w-full rounded-[12px] border px-3 py-2 text-sm outline-none"
          placeholder="Atendimento externo autorizado pelo gestor."
        />
      </label>

      {/* ⚠️ A frase diz o nome de quem é afetado pela justificativa. Uma ação
          que não volta atrás sobre uma pessoa tem de nomeá-la antes, não depois. */}
      <p className="text-ink-faint text-xs text-pretty">
        Fica registrada com o seu nome, na ocorrência de {employeeName}, e segue
        para aprovação do RH. Não é possível editar depois — uma justificativa
        nova escreve outra linha.
      </p>

      <Button
        onClick={() => void record()}
        disabled={busy || tooShort}
        className="w-fit"
      >
        {busy ? "Enviando…" : "Enviar justificativa"}
      </Button>

      {error ? <Alert>{error}</Alert> : null}
      {applied ? (
        <p role="status" className="text-ink-muted text-xs font-semibold">
          {applied}
        </p>
      ) : null}
    </section>
  );
}
