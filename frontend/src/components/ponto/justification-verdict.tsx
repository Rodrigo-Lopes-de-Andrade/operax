"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError, requestApiAsUser } from "@/lib/api";

/**
 * O veredito sobre um indício — quem produz `rejected`.
 *
 * A migration 23 fechou `app.justification.status` em `accepted` e `rejected` e
 * registrou que `rejected` não tinha produtor: enquanto não houvesse, "aceita" e
 * "escrita" eram a mesma coisa. Esta é a porta.
 *
 * O VEREDITO É ESCOLHIDO ANTES DE SER ESCRITO, E ISSO NÃO É ENFEITE
 * O banco só concede `insert` nesta tabela — não há update. Uma linha gravada
 * não volta atrás, e por isso a tela não tem um botão que grava direto: escolhe-
 * se aceitar ou rejeitar, o botão então diz qual dos dois vai acontecer, e só
 * depois grava. Dois botões lado a lado numa ação irreversível é um clique
 * errado a um pixel de distância.
 *
 * MUDAR DE IDEIA ESCREVE OUTRA LINHA, E É CORRETO QUE ESCREVA
 * `fn_pending_justification` pergunta se existe ALGUMA aceita. Uma rejeição
 * depois de uma aceitação não desaceita nada — o desvio já foi explicado uma
 * vez, por alguém, e apagar isso apagaria justamente o que a tabela existe para
 * guardar.
 */
export function JustificationVerdict({
  deviationEventId,
  employeeName,
}: {
  deviationEventId: string;
  employeeName: string;
}) {
  const router = useRouter();
  const [status, setStatus] = useState<"accepted" | "rejected">("accepted");
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
        { method: "POST", body: { text: text.trim(), status } },
      );

      setApplied(
        status === "accepted"
          ? "Justificativa aceita e registrada."
          : "Justificativa rejeitada e registrada.",
      );
      setText("");
      router.refresh();
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Não foi possível registrar. Tente de novo.",
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

      <div
        role="radiogroup"
        aria-label="Veredito"
        className="border-line-subtle flex gap-1 rounded-full border p-1"
      >
        <Choice
          checked={status === "accepted"}
          onSelect={() => setStatus("accepted")}
          label="Aceitar"
        />
        <Choice
          checked={status === "rejected"}
          onSelect={() => setStatus("rejected")}
          label="Rejeitar"
        />
      </div>

      <label className="flex flex-col gap-1.5">
        <span className="text-ink-muted text-xs">
          {status === "accepted"
            ? "O que explica o indício"
            : "Por que a explicação não foi aceita"}
        </span>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={3}
          maxLength={2000}
          className="border-line-subtle text-ink focus:border-brand-strong w-full rounded-[12px] border px-3 py-2 text-sm outline-none"
          placeholder={
            status === "accepted"
              ? "Atendimento externo autorizado pelo gestor."
              : "Sem autorização registrada para o horário."
          }
        />
      </label>

      {/* ⚠️ A frase diz o nome de quem recebe o veredito. Uma ação que não volta
          atrás sobre uma pessoa tem de nomeá-la antes, não depois. */}
      <p className="text-ink-faint text-xs text-pretty">
        Fica registrado com o seu nome, na ocorrência de {employeeName}. Não é
        possível editar depois — um veredito novo escreve outra linha.
      </p>

      <Button
        onClick={() => void record()}
        disabled={busy || tooShort}
        className="w-fit"
      >
        {busy
          ? "Registrando…"
          : status === "accepted"
            ? "Registrar aceite"
            : "Registrar rejeição"}
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

function Choice({
  checked,
  onSelect,
  label,
}: {
  checked: boolean;
  onSelect: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={checked}
      onClick={onSelect}
      className={`flex-1 rounded-full px-4 py-1.5 text-sm font-bold transition ${
        checked ? "bg-brand text-on-brand" : "text-ink-muted hover:bg-muted"
      }`}
    >
      {label}
    </button>
  );
}
