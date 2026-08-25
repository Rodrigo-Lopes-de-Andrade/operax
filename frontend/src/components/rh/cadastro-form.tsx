"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/text-field";
import { ApiError, requestApiAsUser } from "@/lib/api";
import { EMPLOYMENT_LABEL, label } from "@/lib/rh/labels";

type Values = {
  hr_code: string;
  employment_type: string;
  ctps: string;
};

/**
 * Os campos que o RH é dono. Três, e é para ser pouco: a matriz dono-do-campo
 * decide quais são, e o resto ou vem do ponto, ou é vigência — que se cria, não
 * se edita.
 *
 * `editable` chega do backend já recortado pelo domínio de quem está olhando.
 * Quem não alcança PII não recebe `ctps` na lista e o campo não é renderizado;
 * quem não escreve não recebe lista nenhuma e este formulário nem é montado.
 * Esconder o campo não é a segurança — o `PATCH` recusa por conta própria —, é
 * não oferecer o que não vai funcionar.
 *
 * Só o que mudou é enviado. Reenviar o valor idêntico geraria uma linha de
 * auditoria dizendo que alguém alterou o que ninguém alterou.
 */
export function CadastroForm({
  employeeId,
  editable,
  enums,
  initial,
}: {
  employeeId: string;
  editable: string[];
  enums: Record<string, string[]>;
  initial: Values;
}) {
  const router = useRouter();
  const [values, setValues] = useState<Values>(initial);
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);

  const changed = (Object.keys(values) as (keyof Values)[]).filter(
    (key) => editable.includes(key) && values[key] !== initial[key],
  );

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setState("saving");
    setError(null);

    const body: Record<string, string | null> = {};
    for (const key of changed) {
      body[key] = values[key].trim() === "" ? null : values[key].trim();
    }

    try {
      await requestApiAsUser(`/rh/employees/${employeeId}`, {
        method: "PATCH",
        body,
      });
      setState("saved");
      // O servidor é quem tem a verdade depois da gravação: a tela recarrega em
      // vez de acreditar no que acabou de mandar.
      router.refresh();
    } catch (caught) {
      setState("idle");
      setError(
        caught instanceof ApiError && caught.detail
          ? caught.detail
          : "Não consegui gravar. Tente novamente.",
      );
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {editable.includes("hr_code") ? (
          <TextField
            id="hr_code"
            label="ID RH"
            value={values.hr_code}
            onChange={(event) =>
              setValues({ ...values, hr_code: event.target.value })
            }
            placeholder="Vazio até vincular"
          />
        ) : null}

        {editable.includes("employment_type") ? (
          <label className="flex flex-col gap-1.5">
            <span className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
              Regime
            </span>
            <select
              value={values.employment_type}
              onChange={(event) =>
                setValues({ ...values, employment_type: event.target.value })
              }
              className="bg-control border-control-line text-ink h-10 rounded-[10px] border px-3 text-base outline-none"
            >
              <option value="">Não informado</option>
              {/* A lista vem do `check` do próprio banco, pela API: uma cópia
                  aqui envelheceria oferecendo o que o banco recusa. */}
              {(enums.employment_type ?? []).map((value) => (
                <option key={value} value={value}>
                  {label(EMPLOYMENT_LABEL, value)}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {editable.includes("ctps") ? (
          <TextField
            id="ctps"
            label="CTPS"
            value={values.ctps}
            onChange={(event) =>
              setValues({ ...values, ctps: event.target.value })
            }
          />
        ) : null}
      </div>

      {error ? <Alert>{error}</Alert> : null}

      <div className="flex items-center gap-3">
        <Button
          type="submit"
          disabled={state === "saving" || changed.length === 0}
        >
          {state === "saving" ? "Gravando…" : "Salvar cadastro"}
        </Button>
        {state === "saved" && changed.length === 0 ? (
          <span className="text-good text-sm font-semibold">Gravado.</span>
        ) : null}
      </div>
    </form>
  );
}
