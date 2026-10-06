"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import type { SupabaseClient } from "@supabase/supabase-js";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { TextField } from "@/components/ui/text-field";
import type { Database } from "@/lib/database.types";
import { DEFAULT_AUTHENTICATED_PATH } from "@/lib/navigation";
import { createInviteSupabaseClient } from "@/lib/supabase";
import { FLOW_PARAM, RECOVERY_FLOW } from "@/lib/usuarios/url";

/** bcrypt, que o Supabase Auth usa, só lê os primeiros 72 bytes. */
const passwordSchema = z
  .object({
    password: z
      .string()
      .min(8, "Use pelo menos 8 caracteres.")
      .max(72, "Use até 72 caracteres."),
    confirmation: z.string(),
  })
  .refine((values) => values.password === values.confirmation, {
    path: ["confirmation"],
    message: "As duas senhas não são iguais.",
  });

/** O link que trouxe a pessoa aqui: o convite, ou o "Esqueci minha senha". */
type Flow = "invite" | "recovery";

type Phase =
  | { kind: "checking" }
  | { kind: "invalid"; flow: Flow }
  | { kind: "ready"; flow: Flow; email: string | null; client: Client };

type Client = SupabaseClient<Database>;

const HEADING: Record<Flow, { title: string; lead: string }> = {
  invite: {
    title: "Defina sua senha",
    lead: "É com ela, e com o seu e-mail, que você vai entrar no painel. Ninguém mais a vê.",
  },
  recovery: {
    title: "Defina uma nova senha",
    lead: "A senha anterior deixa de valer. Ninguém mais vê a nova.",
  },
};

/**
 * A sessão a partir do link do e-mail — de convite ou de recuperação de senha
 * (`resetPasswordForEmail`, que volta para esta mesma rota). São três formas, e
 * quem decide qual chega é o template do e-mail no Supabase Auth, não esta
 * tela:
 *
 * - `#access_token=…&refresh_token=…&type=invite|recovery` — o fluxo implícito,
 *   que é o do link padrão (`{{ .ConfirmationURL }}`);
 * - `?code=…` — PKCE, que só se troca se o verificador estiver neste navegador;
 * - `?token_hash=…&type=invite|recovery` — o template recomendado para
 *   `@supabase/ssr`.
 *
 * Erro do Auth (`error`, `error_code`, `error_description`) vem na query ou no
 * fragmento, conforme o fluxo, e vira "link inválido" nos dois.
 *
 * Recuperação é `type=recovery` (fluxo implícito e `token_hash`) ou a marca
 * `?fluxo=recuperacao` que o próprio `redirectTo` do "Esqueci minha senha"
 * carrega — o PKCE volta só com `?code=`, sem `type`.
 *
 * ⛔ Sem link, não há formulário: a página não oferece troca de senha a uma
 * sessão que já estava aberta neste navegador. Quem recarregou depois de o link
 * ser consumido pede outro em "Esqueci minha senha".
 */
async function establishSession(client: Client, url: URL): Promise<Phase> {
  const fragment = new URLSearchParams(url.hash.replace(/^#/, ""));
  const param = (key: string) => fragment.get(key) ?? url.searchParams.get(key);
  const flow: Flow =
    param("type") === "recovery" || param(FLOW_PARAM) === RECOVERY_FLOW
      ? "recovery"
      : "invite";
  const invalid: Phase = { kind: "invalid", flow };

  if (param("error") || param("error_code") || param("error_description")) {
    return invalid;
  }

  const accessToken = fragment.get("access_token");
  const refreshToken = fragment.get("refresh_token");
  const code = url.searchParams.get("code");
  const tokenHash = url.searchParams.get("token_hash");

  let result;
  if (accessToken && refreshToken) {
    // `setSession` valida o token no Auth antes de gravar a sessão.
    result = await client.auth.setSession({
      access_token: accessToken,
      refresh_token: refreshToken,
    });
  } else if (code) {
    result = await client.auth.exchangeCodeForSession(code);
  } else if (tokenHash) {
    result = await client.auth.verifyOtp({ token_hash: tokenHash, type: flow });
  } else {
    return invalid;
  }

  const { data, error } = result;
  return error || !data.user
    ? invalid
    : { kind: "ready", flow, email: data.user.email ?? null, client };
}

function updateFailureMessage(code: string | undefined): string {
  switch (code) {
    case "weak_password":
      return "Essa senha é fraca demais para o Auth. Use uma mais longa, misturando letras, números e símbolos.";
    case "same_password":
      return "Essa já é a sua senha atual. Escolha outra.";
    case "over_request_rate_limit":
      return "Muitas tentativas. Aguarde alguns minutos e tente de novo.";
    default:
      return "Não foi possível gravar a senha agora. Tente de novo.";
  }
}

/**
 * Onde a pessoa define a PRÓPRIA senha (SPEC-USUARIOS §2, decisão 2): a
 * convidada, pelo link do convite, e quem esqueceu a senha, pelo link de
 * recuperação.
 *
 * ⛔ A senha vai do formulário direto ao Supabase Auth (`updateUser`), com a
 * sessão que o link abriu. Ela não passa pelo backend do OperaX, não é
 * registrada em log e não sai do estado deste formulário — que é desmontado na
 * navegação para o painel.
 */
export function AcceptInvite() {
  const router = useRouter();
  const started = useRef(false);
  const [phase, setPhase] = useState<Phase>({ kind: "checking" });
  const [failure, setFailure] = useState<string | null>(null);
  const { register, handleSubmit, reset, formState } = useForm({
    resolver: zodResolver(passwordSchema),
    defaultValues: { password: "", confirmation: "" },
  });

  useEffect(() => {
    // O link vale uma vez: o efeito duplo do modo estrito não pode lê-lo de novo.
    if (started.current) {
      return;
    }
    started.current = true;

    const url = new URL(window.location.href);
    // Os tokens saem da barra de endereço e do histórico antes de qualquer
    // outra coisa.
    window.history.replaceState(window.history.state, "", url.pathname);

    void (async () => {
      try {
        setPhase(await establishSession(createInviteSupabaseClient(), url));
      } catch {
        setPhase({ kind: "invalid", flow: "invite" });
      }
    })();
  }, []);

  const onSubmit = handleSubmit(async ({ password }) => {
    setFailure(null);

    if (phase.kind !== "ready") {
      return;
    }

    try {
      const { error } = await phase.client.auth.updateUser({ password });

      if (error) {
        if (error.status === 401 || error.code === "session_not_found") {
          setPhase({ kind: "invalid", flow: phase.flow });
          return;
        }
        setFailure(updateFailureMessage(error.code));
        return;
      }
    } catch {
      setFailure(updateFailureMessage(undefined));
      return;
    }

    reset();
    router.replace(DEFAULT_AUTHENTICATED_PATH);
    router.refresh();
  });

  if (phase.kind === "checking") {
    return (
      <p
        role="status"
        className="flex items-center gap-2 text-sm"
        style={{ color: "var(--entry-ink-muted)" }}
      >
        <Spinner /> Conferindo o link…
      </p>
    );
  }

  const heading = HEADING[phase.flow];

  return (
    <div>
      <h1
        className="text-[1.75rem] leading-tight font-bold"
        style={{ color: "var(--entry-ink)" }}
      >
        {heading.title}
      </h1>
      <p className="mt-2 text-sm" style={{ color: "var(--entry-ink-muted)" }}>
        {heading.lead}
      </p>

      <div className="mt-7">
        {phase.kind === "invalid" ? (
          phase.flow === "recovery" ? (
            <div className="flex flex-col gap-3">
              <Alert>Este link de nova senha é inválido ou expirou.</Alert>
              <p
                className="text-sm"
                style={{ color: "var(--entry-ink-muted)" }}
              >
                Peça outro em &quot;Esqueci minha senha&quot;, na tela de
                entrada, e abra-o no mesmo navegador em que fez o pedido. O link
                do e-mail vale uma vez só e por tempo limitado.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <Alert>Este link de convite é inválido ou expirou.</Alert>
              <p
                className="text-sm"
                style={{ color: "var(--entry-ink-muted)" }}
              >
                Peça um novo convite a quem convidou você. O link do e-mail vale
                uma vez só e por tempo limitado.
              </p>
            </div>
          )
        ) : (
          <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
            {phase.email ? (
              <p
                className="text-sm"
                style={{ color: "var(--entry-ink-muted)" }}
              >
                Conta: <strong>{phase.email}</strong>
              </p>
            ) : null}
            <TextField
              id="password"
              label="Nova senha"
              type="password"
              autoComplete="new-password"
              autoFocus
              error={formState.errors.password?.message}
              {...register("password")}
            />
            <TextField
              id="confirmation"
              label="Confirme a senha"
              type="password"
              autoComplete="new-password"
              error={formState.errors.confirmation?.message}
              {...register("confirmation")}
            />

            {failure ? <Alert>{failure}</Alert> : null}

            <Button
              type="submit"
              disabled={formState.isSubmitting}
              className="mt-1"
            >
              {formState.isSubmitting ? <Spinner /> : null}
              {formState.isSubmitting ? "Gravando…" : "Definir senha e entrar"}
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}
