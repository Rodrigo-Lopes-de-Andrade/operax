"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { useController, useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/text-field";
import {
  hasCompanies,
  ScopePicker,
  scopeEntries,
} from "@/components/usuarios/scope-picker";
import { requestApiAsUser } from "@/lib/api";
import type { UnitOption } from "@/lib/ponto/queries";
import {
  INVITE_ERROR_MESSAGE,
  refusalMessage,
  type UserInvitation,
  type UserInvitationRequest,
} from "@/lib/usuarios/contract";

const inviteSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Informe o nome.")
    .max(120, "Use até 120 caracteres."),
  email: z.string().trim().pipe(z.email("Informe um e-mail válido.")),
  // ⛔ Sem estado vazio válido: zero entrada não submete.
  scope: z
    .array(z.string())
    .min(1, "Escolha pelo menos uma empresa ou unidade."),
});

type InviteValues = z.input<typeof inviteSchema>;

type Outcome =
  { kind: "sent"; message: string } | { kind: "error"; message: string };

/**
 * Convidar alguém para o painel: nome, e-mail e escopo.
 *
 * Sem campo de papel e sem campo de senha. A pessoa nasce `viewer` e define a
 * própria senha pelo link do e-mail (§2); papel só o owner concede, depois.
 */
export function InviteForm({ units }: { units: UnitOption[] }) {
  const router = useRouter();
  const idPrefix = useId();
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const offersScope = hasCompanies(units);

  const { register, handleSubmit, reset, control, formState } =
    useForm<InviteValues>({
      resolver: zodResolver(inviteSchema),
      defaultValues: { name: "", email: "", scope: [] },
    });
  const { field: scopeField, fieldState: scopeState } = useController({
    control,
    name: "scope",
  });

  const onSubmit = handleSubmit(async ({ name, email, scope }) => {
    setOutcome(null);
    const body: UserInvitationRequest = {
      name: name.trim(),
      email: email.trim(),
      scope: scopeEntries(scope, units),
    };

    try {
      const invitation = await requestApiAsUser<UserInvitation>(
        "/usuarios/convites",
        { method: "POST", body },
      );
      // Da resposta, só o e-mail e o `invitation_sent` chegam à tela.
      setOutcome({
        kind: "sent",
        message: invitation.invitation_sent
          ? `Convite enviado para ${invitation.email}.`
          : "Essa pessoa já tem conta; o acesso foi liberado sem novo e-mail.",
      });
      reset();
      router.refresh();
    } catch (caught) {
      setOutcome({
        kind: "error",
        message: refusalMessage(
          caught,
          INVITE_ERROR_MESSAGE,
          "Não consegui enviar o convite agora. Confira nome, e-mail e escopo e tente de novo.",
        ),
      });
    }
  });

  const scopeErrorId = `${idPrefix}scope-error`;

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      aria-label="Convidar usuário"
      className="flex flex-col gap-5"
    >
      <p className="text-ink-muted text-sm text-pretty">
        A pessoa entra como <strong className="text-ink">Consulta</strong>{" "}
        (viewer), sem acesso a dado sensível. Papel só o owner concede, depois
        do convite. A senha é ela quem define, pelo link do e-mail.
      </p>

      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          id={`${idPrefix}name`}
          label="Nome"
          autoComplete="off"
          maxLength={120}
          error={formState.errors.name?.message}
          {...register("name")}
        />
        <TextField
          id={`${idPrefix}email`}
          label="E-mail"
          type="email"
          autoComplete="off"
          error={formState.errors.email?.message}
          {...register("email")}
        />
      </div>

      <ScopePicker
        units={units}
        value={scopeField.value}
        onChange={scopeField.onChange}
        error={scopeState.error?.message}
        errorId={scopeErrorId}
      />

      {outcome?.kind === "error" ? <Alert>{outcome.message}</Alert> : null}
      {outcome?.kind === "sent" ? (
        <p role="status" className="text-good text-sm font-medium">
          {outcome.message}
        </p>
      ) : null}

      <div>
        <Button type="submit" disabled={formState.isSubmitting || !offersScope}>
          {formState.isSubmitting ? "Enviando convite…" : "Enviar convite"}
        </Button>
      </div>
    </form>
  );
}
