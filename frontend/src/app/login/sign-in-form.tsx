"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { TextField } from "@/components/ui/text-field";
import { createBrowserSupabaseClient } from "@/lib/supabase";

const signInSchema = z.object({
  email: z.string().trim().pipe(z.email("Informe um e-mail válido.")),
  password: z.string().min(1, "Informe sua senha."),
});

/**
 * Supabase error code to the sentence the user reads. Anything unmapped stays
 * generic on purpose: naming which half of the pair was wrong helps whoever is
 * guessing, not whoever forgot.
 */
function signInFailureMessage(code: string | undefined) {
  switch (code) {
    case "invalid_credentials":
      return "E-mail ou senha inválidos.";
    case "email_not_confirmed":
      return "Confirme seu e-mail antes de entrar.";
    case "over_request_rate_limit":
    case "over_email_send_rate_limit":
      return "Muitas tentativas. Aguarde alguns minutos e tente de novo.";
    default:
      return "Não foi possível entrar agora. Tente de novo.";
  }
}

/** Client Component: form state, validation and the sign-in call. */
export function SignInForm({ next }: { next: string }) {
  const router = useRouter();
  const [failure, setFailure] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm({
    resolver: zodResolver(signInSchema),
    defaultValues: { email: "", password: "" },
  });

  const onSubmit = handleSubmit(async ({ email, password }) => {
    setFailure(null);

    try {
      // Missing configuration throws here. Unhandled, it would stop the
      // spinner and say nothing at all — the one outcome a login screen
      // cannot have.
      const supabase = createBrowserSupabaseClient();
      const { error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (error) {
        setFailure(signInFailureMessage(error.code));
        return;
      }
    } catch (cause) {
      console.error(cause);
      setFailure(signInFailureMessage(undefined));
      return;
    }

    // Signing in only proves who the user is. What this session may see is
    // decided again on the server, so refresh instead of trusting this tab.
    router.replace(next);
    router.refresh();
  });

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
      <TextField
        id="password"
        label="Senha"
        type="password"
        autoComplete="current-password"
        error={formState.errors.password?.message}
        {...register("password")}
      />

      {failure ? <Alert>{failure}</Alert> : null}

      <Button type="submit" disabled={formState.isSubmitting} className="mt-1">
        {formState.isSubmitting ? <Spinner /> : null}
        {formState.isSubmitting ? "Entrando…" : "Entrar"}
      </Button>
    </form>
  );
}
