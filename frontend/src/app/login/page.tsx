import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";

import { brandForHost, pageTitle } from "@/lib/brand";
import { FORGOT_PASSWORD_PARAM } from "@/lib/usuarios/url";
import {
  DEFAULT_AUTHENTICATED_PATH,
  LOGIN_PATH,
  safeNextPath,
} from "@/lib/navigation";

import { EntryCanvas } from "./entry-canvas";
import { ForgotPasswordForm } from "./forgot-password-form";
import { SignInForm } from "./sign-in-form";

export const metadata: Metadata = {
  title: pageTitle("Entrar"),
};

type LoginPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const next = safeNextPath(params.next);
  const cameFromLink = next !== DEFAULT_AUTHENTICATED_PATH;
  // "Esqueci minha senha" é um estado desta rota, não uma rota nova: o
  // `/login` já abre sem sessão, e `proxy.ts` não precisa de regra a mais.
  const forgot = params[FORGOT_PASSWORD_PARAM] !== undefined;

  /**
   * A marca vem do HOST, e é a única resolução possível aqui: o login é a tela
   * sem sessão, então não há `tenant_id` de onde tirá-la. O host já é por
   * cliente — `app.fastparks.com.br` é o endereço da FastPark e de mais ninguém.
   */
  const brand = brandForHost((await headers()).get("host"));

  return (
    <main
      data-brand={brand.slug}
      data-entry=""
      className="grid min-h-dvh lg:grid-cols-[1.05fr_1fr]"
      style={{ background: "var(--entry-ground)" }}
    >
      {/* ── Painel da marca ─────────────────────────────────────────────────
          Some abaixo de `lg`: no telefone a tela é o formulário, e um painel
          decorativo empurrando o campo de e-mail para fora da dobra é o oposto
          de carregar a marca. */}
      <section className="relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-between lg:p-12">
        <EntryCanvas />

        <FastParkMark />

        <div className="relative">
          <p
            className="text-[clamp(2rem,1.3rem+2.6vw,3.25rem)] leading-[1.05] font-light"
            style={{ color: "var(--entry-ink)" }}
          >
            Nosso cuidado,
            <br />
            <em className="font-semibold not-italic">no seu ritmo.</em>
          </p>

          {/* ⛔ Os números do protótipo ("24 unidades · 1.180 vagas") NÃO estão
              aqui, e a decisão é de 04/09/2026. Dois motivos, e o segundo é o
              que decide: (1) é dado operacional do cliente numa página sem
              autenticação; (2) o número já nascia ERRADO — produção tem 27
              unidades, não 24 — e texto fixo sobre coisa que muda mente na
              primeira tela que qualquer pessoa vê. A localização fica: é marca,
              e não envelhece. */}
          <p
            className="mt-6 text-sm tracking-wide"
            style={{ color: "var(--entry-ink-muted)" }}
          >
            São&nbsp;Paulo&nbsp;·&nbsp;SP
          </p>
        </div>
      </section>

      {/* ── Acesso ──────────────────────────────────────────────────────── */}
      <section className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="lg:hidden">
            <FastParkMark compact />
          </div>

          {/* Superfície pré-sessão: nenhum dado de colaborador antes da
              autenticação — nem nome, unidade, hora, tipo de ocorrência ou
              contagem. O aviso fala do LINK, nunca de quem está do outro lado.

              Os dois ramos carregam o <h1>: todo link de alerta cai aqui, e uma
              tela sem cabeçalho quebra a navegação por títulos na superfície
              mais movimentada do produto. */}
          <p
            className="mt-8 text-xs font-semibold tracking-[0.14em] uppercase lg:mt-0"
            style={{ color: "var(--entry-accent-text)" }}
          >
            Painel operacional
          </p>

          <h1
            className={
              cameFromLink && !forgot
                ? "mt-2 text-xl font-bold"
                : "mt-2 text-[1.75rem] leading-tight font-bold"
            }
            style={{ color: "var(--entry-ink)" }}
          >
            {forgot
              ? "Esqueci minha senha"
              : cameFromLink
                ? "Você abriu um link de ocorrência."
                : "Entrar na sua conta"}
          </h1>

          <p
            className="mt-2 text-sm"
            style={{ color: "var(--entry-ink-muted)" }}
          >
            {forgot
              ? "Informe o seu e-mail. O link que chegar nele leva à tela de nova senha."
              : cameFromLink
                ? "Entre para vê-la. Você volta direto para esta ocorrência, não para a página inicial."
                : "Use o e-mail corporativo cadastrado pelo RH."}
          </p>

          <div className="mt-7">
            {forgot ? (
              <ForgotPasswordForm />
            ) : (
              <>
                <SignInForm next={next} />
                <Link
                  href={`${LOGIN_PATH}?${FORGOT_PASSWORD_PARAM}`}
                  className="mt-4 inline-block text-sm font-bold underline"
                  style={{ color: "var(--entry-ink)" }}
                >
                  Esqueci minha senha
                </Link>
              </>
            )}
          </div>

          <p
            className="mt-8 border-t pt-5 text-xs"
            style={{
              borderColor: "var(--entry-rule)",
              color: "var(--entry-ink-muted)",
            }}
          >
            Supervisor de unidade enxerga apenas a própria unidade.
          </p>
        </div>
      </section>
    </main>
  );
}

/**
 * O logotipo: moldura 151 C e sorriso 425 C, com a área de proteção do manual.
 *
 * ⚠️ As cores saem dos tokens do tenant (`--fp-151`, `--fp-425`), nunca de
 * literais aqui — é a regra de white-label, e é o que faz um segundo tenant ser
 * uma entrada nova em `brand.ts` e nada mais.
 */
function FastParkMark({ compact = false }: { compact?: boolean }) {
  return (
    <svg
      viewBox="0 0 268 62"
      role="img"
      aria-label="FastPark"
      className={compact ? "relative h-8" : "relative h-10"}
    >
      <g fill="none" strokeLinecap="round" strokeWidth="7.5">
        <path
          stroke="var(--fp-151)"
          d="M13.5 47.5 V19 A11 11 0 0 1 24.5 8 H49.5 A11 11 0 0 1 60.5 19 V47.5"
        />
        <path stroke="var(--fp-425)" d="M13.5 42 C21 55.5 53 55.5 60.5 42" />
      </g>
      <g
        fontFamily="var(--font-hanken), Verdana, sans-serif"
        fontSize="44"
        fontWeight="600"
        letterSpacing="-1.2"
      >
        <text x="86" y="46" fill="var(--entry-ink)">
          Fast
        </text>
        <text x="169" y="46" fill="var(--fp-151)">
          Park
        </text>
      </g>
    </svg>
  );
}
