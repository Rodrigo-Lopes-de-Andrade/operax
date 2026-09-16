"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { type ComponentProps, useId, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Requirements } from "@/components/canais/connections";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { TextField } from "@/components/ui/text-field";
import { ApiError, requestApiAsUser } from "@/lib/api";
import { label, PROVIDER_LABEL } from "@/lib/canais/labels";
import type {
  CredentialField,
  CredentialStatus,
  ProviderForm,
} from "@/lib/canais/queries";
import { formatDayInTenantZone } from "@/lib/dp/format";
import { formatClock } from "@/lib/ponto/format";

type Values = Record<string, string>;

/** O desfecho do último envio: gravou, ou não — nunca os dois ao mesmo tempo. */
type Outcome =
  | { kind: "saved"; status: CredentialStatus }
  | { kind: "error"; message: string };

/** A união do React; o contrato da API é `str`, e o DOM ignora token que não conhece. */
type InputMode = NonNullable<ComponentProps<"input">["inputMode"]>;

/**
 * O mesmo `pattern` que a API impõe, ancorado como o `fullmatch` do backend o
 * ancora, e sobre o valor sem espaços nas pontas — também como lá. A frase de
 * erro é a `hint` do campo (§5.4): *"isto não parece um ID de número"*, e
 * nunca o valor.
 */
function schemaFor(fields: CredentialField[]) {
  return z.object(
    Object.fromEntries(
      fields.map((field) => [
        field.name,
        z
          .string()
          .trim()
          .regex(new RegExp(`^(?:${field.pattern})$`), field.hint),
      ]),
    ),
  );
}

function emptyValues(fields: CredentialField[]): Values {
  return Object.fromEntries(fields.map((field) => [field.name, ""]));
}

/** Depois de gravar, o segredo some do formulário; o identificador público fica. */
function withoutSecrets(fields: CredentialField[], values: Values): Values {
  return Object.fromEntries(
    fields.map((field) => [field.name, field.secret ? "" : values[field.name]]),
  );
}

function mensagem(caught: unknown, padrao: string): string {
  return caught instanceof ApiError && caught.detail ? caught.detail : padrao;
}

/**
 * O que se sabe da credencial: que existe, de qual provedor, como quem e desde
 * quando — nunca qual é (SPEC-CANAIS §5.3).
 */
function CurrentStatus({ status }: { status: CredentialStatus }) {
  if (!status.configured) {
    return (
      <div className="flex items-center gap-3">
        <Badge tone="neutral" dot>
          Não configurada
        </Badge>
        <p className="text-ink-muted text-sm">
          Nenhuma credencial gravada neste cliente.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-3">
        <Badge tone="good" dot>
          Configurada
        </Badge>
        {status.provider ? (
          <p className="text-ink text-sm font-bold">
            {label(PROVIDER_LABEL, status.provider)}
          </p>
        ) : null}
      </div>
      <p className="text-ink-muted text-sm">
        {status.public_identity ? (
          <>
            Conectado como{" "}
            <strong className="text-ink">{status.public_identity}</strong>
            {status.updated_at ? " · " : null}
          </>
        ) : null}
        {status.updated_at ? (
          <>
            gravada em {formatDayInTenantZone(status.updated_at)} às{" "}
            {formatClock(status.updated_at)}
          </>
        ) : null}
      </p>
    </div>
  );
}

/**
 * Os campos de um provedor, e o envio.
 *
 * Nada aqui sabe qual provedor é: os campos, o `pattern`, o `autocomplete`, o
 * `inputmode`, o `placeholder` e a `hint` vêm de `GET /canais/provedores`,
 * e `secret` decide o `type` do input. É a SPEC §5.4 num lugar só — o backend
 * — lida aqui, e não copiada.
 *
 * Um `useForm` por provedor (o `key` no pai remonta este componente ao trocar
 * o seletor): o schema é fixo enquanto o componente vive, e o que foi digitado
 * para um provedor não sobrevive à troca — um token digitado para um canal não
 * tem o que fazer no formulário de outro.
 */
function ProviderFields({
  form,
  error,
  onOutcome,
}: {
  form: ProviderForm;
  error: string | null;
  onOutcome: (outcome: Outcome | null) => void;
}) {
  const { register, handleSubmit, reset, formState } = useForm<Values>({
    resolver: zodResolver(schemaFor(form.fields)),
    defaultValues: emptyValues(form.fields),
  });
  // Um formulário por canal na mesma página, e dois provedores podem nomear o
  // mesmo campo: o `id` precisa ser desta instância, não do nome.
  const idPrefix = useId();

  const onSubmit = handleSubmit(async (values) => {
    onOutcome(null);

    try {
      const saved = await requestApiAsUser<CredentialStatus>(
        "/canais/credencial",
        { method: "POST", body: { provider: form.provider, fields: values } },
      );
      // §5.3: o segredo não volta e não fica. Em erro, nada é limpo — a pessoa
      // vai corrigir um caractere, não redigitar o token inteiro.
      reset(withoutSecrets(form.fields, values));
      onOutcome({ kind: "saved", status: saved });
    } catch (caught) {
      onOutcome({
        kind: "error",
        message: mensagem(caught, "Não consegui gravar a credencial."),
      });
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {form.fields.map((field) => (
          <TextField
            key={field.name}
            id={`${idPrefix}${field.name}`}
            label={field.label}
            type={field.secret ? "password" : "text"}
            autoComplete={field.autocomplete}
            inputMode={field.inputmode as InputMode}
            pattern={field.pattern}
            placeholder={field.placeholder}
            error={formState.errors[field.name]?.message}
            {...register(field.name)}
          />
        ))}
      </div>

      {error ? <Alert>{error}</Alert> : null}

      <div>
        <Button type="submit" disabled={formState.isSubmitting}>
          {formState.isSubmitting
            ? "Validando no provedor…"
            : "Validar e gravar"}
        </Button>
      </div>
    </form>
  );
}

/**
 * A credencial do canal de WhatsApp — o que está gravado, e o formulário para
 * gravar outra.
 *
 * Caminho 2 do começo ao fim: o navegador nunca toca a credencial com a chave
 * anônima (SPEC §5.1), o backend valida no provedor e só então grava (§5.2), e
 * o que volta é `configured`, o provedor, a identidade pública e a data —
 * nunca o valor (§5.3). A frase de sucesso é a confirmação legível que o
 * provedor deu: *"conectado como …"*. A recusa do provedor chega como `detail`
 * do 422, já em pt-BR e já dizendo "nada foi gravado", e é mostrada como veio.
 *
 * O seletor traz os provedores na ordem da API (o oficial primeiro), e o que
 * cada um exige é dito pelas flags de `capabilities` — o mesmo `<Requirements>`
 * da tela, nunca pelo nome. Preselecionado, o provedor já configurado, quando
 * há um: quem volta aqui para trocar o token não precisa reescolher o canal.
 *
 * Duas coisas separadas: o que foi gravado (`saved`, fato — segura o estado
 * acima até o `refresh` trazer a prop nova) e o desfecho do último envio
 * (`outcome`, notícia). A frase de sucesso e o erro nunca coexistem, e os dois
 * somem ao trocar o provedor — uma credencial gravada para um canal não é
 * notícia sobre o formulário de outro.
 */
export function CredentialForm({
  forms,
  status,
}: {
  forms: ProviderForm[];
  status: CredentialStatus;
}) {
  const router = useRouter();
  const [saved, setSaved] = useState<CredentialStatus | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [provider, setProvider] = useState(
    () =>
      forms.find((form) => form.provider === status.provider)?.provider ??
      forms[0]?.provider ??
      "",
  );

  const form = forms.find((candidate) => candidate.provider === provider);
  const current = saved ?? status;

  return (
    <Card>
      <CardHeader
        eyebrow="Credencial"
        title="Credencial do canal"
        note="Validada no provedor antes de gravar. O valor vai para o cofre e não volta para a tela."
      />
      <div className="flex flex-col gap-5 px-5 py-5">
        <CurrentStatus status={current} />

        {outcome?.kind === "saved" ? (
          <p role="status" className="text-good text-sm font-medium">
            Credencial gravada.
            {outcome.status.public_identity ? (
              <> Conectado como {outcome.status.public_identity}.</>
            ) : null}
          </p>
        ) : null}

        <label className="flex max-w-sm flex-col gap-1.5">
          <span className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
            Provedor
          </span>
          <select
            className="border-control-line bg-control text-ink h-10 rounded-[10px] border px-3 text-sm"
            value={provider}
            onChange={(event) => {
              setOutcome(null);
              setProvider(event.target.value);
            }}
          >
            {forms.map((candidate) => (
              <option key={candidate.provider} value={candidate.provider}>
                {label(PROVIDER_LABEL, candidate.provider)}
              </option>
            ))}
          </select>
        </label>

        {form ? (
          <>
            <Requirements capabilities={form.capabilities} />
            <ProviderFields
              key={form.provider}
              form={form}
              error={outcome?.kind === "error" ? outcome.message : null}
              onOutcome={(next) => {
                setOutcome(next);
                if (next?.kind === "saved") {
                  setSaved(next.status);
                  router.refresh();
                }
              }}
            />
          </>
        ) : null}
      </div>
    </Card>
  );
}
