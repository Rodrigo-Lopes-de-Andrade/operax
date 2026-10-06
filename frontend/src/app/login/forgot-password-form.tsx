"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { TextField } from "@/components/ui/text-field";
import { LOGIN_PATH } from "@/lib/navigation";
import { createBrowserSupabaseClient } from "@/lib/supabase";
import { recoveryRedirect } from "@/lib/usuarios/url";

const forgotSchema = z.object({
  email: z.string().trim().pipe(z.email("Informe um e-mail válido.")),
});

/**
 * A única resposta, para qualquer desfecho: conta existente, inexistente, erro
 * do Auth ou da rede. Dizer qualquer coisa diferente em um dos casos é contar a
 * quem testa e-mails quais têm conta.
 */
export const FORGOT_PASSWORD_ANSWER =
  "Se esse e-mail tiver conta, enviamos um link para definir uma nova senha.";

/**
 * "Esqueci minha senha" — decisão do dono, 05/10/2026: é também a saída de quem
 * abriu o link do convite e não definiu a senha (o reenvio responde
 * `convite_ja_aceito` para ela).
 *
 * Direto no Supabase Auth, pelo cliente do navegador: o e-mail não passa pelo
 * backend do OperaX. O link do e-mail volta para `/convite`, a mesma tela em
 * que o convidado define a senha. A origem é a desta página
 * (`window.location.origin`), que é o próprio painel — nunca um literal.
 */
export function ForgotPasswordForm() {
  const [answered, setAnswered] = useState(false);
  const { register, handleSubmit, formState } = useForm({
    resolver: zodResolver(forgotSchema),
    defaultValues: { email: "" },
  });

  const onSubmit = handleSubmit(async ({ email }) => {
    try {
      const supabase = createBrowserSupabaseClient();
      await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: recoveryRedirect(window.location.origin),
      });
    } catch {
      // A resposta é a mesma de propósito — ver FORGOT_PASSWORD_ANSWER.
    }
    setAnswered(true);
  });

  if (answered) {
    return (
      <div className="flex flex-col gap-4">
        <p
          role="status"
          className="text-sm font-medium"
          style={{ color: "var(--entry-ink)" }}
        >
          {FORGOT_PASSWORD_ANSWER}
        </p>
        <Link
          href={LOGIN_PATH}
          className="text-sm font-bold underline"
          style={{ color: "var(--entry-ink)" }}
        >
          Voltar para a entrada
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <TextField
        id="email"
        label="E-mail"
        type="email"
        autoComplete="email"
        autoFocus
        error={formState.errors.email?.message}
        {...register("email")}
      />

      <Button type="submit" disabled={formState.isSubmitting} className="mt-1">
        {formState.isSubmitting ? <Spinner /> : null}
        {formState.isSubmitting ? "Enviando…" : "Enviar link"}
      </Button>

      <Link
        href={LOGIN_PATH}
        className="text-sm font-bold underline"
        style={{ color: "var(--entry-ink)" }}
      >
        Voltar para a entrada
      </Link>
    </form>
  );
}
