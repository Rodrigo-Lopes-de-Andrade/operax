import type { Metadata } from "next";

import { pageTitle } from "@/lib/brand";

import { Brand } from "@/components/brand";
import { DEFAULT_AUTHENTICATED_PATH, safeNextPath } from "@/lib/navigation";

import { SignInForm } from "./sign-in-form";

export const metadata: Metadata = {
  title: pageTitle("Entrar"),
};

type LoginPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const next = safeNextPath((await searchParams).next);
  const cameFromLink = next !== DEFAULT_AUTHENTICATED_PATH;

  return (
    <main className="bg-chrome flex min-h-dvh flex-col items-center justify-center gap-8 px-6 py-10">
      <Brand />

      <div className="bg-card w-full max-w-sm rounded-[24px] p-6 shadow-[var(--shadow-lg)]">
        {/* Pre-session surface: no employee data before authentication — no
            name, unit, time, occurrence type or count. The notice below speaks
            about the link, never about who or what is on the other side.

            Both branches carry the <h1>: every alert link lands on the one
            below, and a screen without a heading breaks heading navigation on
            the busiest surface of the product. */}
        <div
          className={
            cameFromLink ? "border-line-subtle mb-5 border-b pb-5" : "mb-5"
          }
        >
          <h1
            className={
              cameFromLink
                ? "text-ink text-base font-bold"
                : "text-ink text-xl font-extrabold"
            }
          >
            {cameFromLink ? "Você abriu um link de ocorrência." : "Entrar"}
          </h1>
          <p className="text-ink-muted mt-1 text-sm">
            {cameFromLink
              ? "Entre para vê-la. Você volta direto para esta ocorrência, não para a página inicial."
              : "Use o e-mail cadastrado pela sua empresa."}
          </p>
        </div>

        <SignInForm next={next} />
      </div>

      <p className="text-center text-xs text-white/80">
        Supervisor de unidade enxerga apenas a própria unidade.
      </p>
    </main>
  );
}
