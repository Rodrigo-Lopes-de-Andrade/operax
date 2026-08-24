"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/text-field";
import { ApiError, requestApiAsUser } from "@/lib/api";

type Kind = "compensation" | "position";

/**
 * Nova vigência — de salário ou de cargo.
 *
 * Não existe "editar a faixa vigente". Corrigir é revogar e criar outra, e essa
 * decisão está no banco (a faixa aberta é fechada em `desde - 1`) antes de estar
 * aqui: um formulário de edição direta produziria um histórico que diz que o
 * salário sempre foi o de agora.
 *
 * O backend recusa a vigência que retroage para competência de folha já fechada,
 * e a recusa chega inteira no lugar do erro — com a data e o motivo, não um
 * "valor inválido".
 */
export function BandForm({
  employeeId,
  kind,
  onDone,
}: {
  employeeId: string;
  kind: Kind;
  onDone?: () => void;
}) {
  const router = useRouter();
  const [from, setFrom] = useState("");
  const [amount, setAmount] = useState("");
  const [cargo, setCargo] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);

    const body =
      kind === "compensation"
        ? {
            effective_from: from,
            salary: amount,
            reason: reason.trim() || null,
          }
        : { effective_from: from, cargo: cargo.trim() };

    try {
      await requestApiAsUser(`/rh/employees/${employeeId}/${kind}`, {
        method: "POST",
        body,
      });
      setFrom("");
      setAmount("");
      setCargo("");
      setReason("");
      router.refresh();
      onDone?.();
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.detail
          ? caught.detail
          : "Não consegui registrar a vigência. Tente novamente.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          id={`${kind}-desde`}
          label="Desde"
          type="date"
          required
          value={from}
          onChange={(event) => setFrom(event.target.value)}
        />
        {kind === "compensation" ? (
          <TextField
            id="salario"
            label="Salário"
            type="number"
            step="0.01"
            min="0"
            required
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        ) : (
          <TextField
            id="cargo"
            label="Cargo"
            required
            value={cargo}
            onChange={(event) => setCargo(event.target.value)}
          />
        )}
      </div>

      {kind === "compensation" ? (
        <TextField
          id="motivo"
          label="Motivo"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Promoção, dissídio, correção…"
        />
      ) : null}

      {error ? <Alert>{error}</Alert> : null}

      <Button type="submit" disabled={saving}>
        {saving ? "Registrando…" : "Registrar vigência"}
      </Button>
    </form>
  );
}
