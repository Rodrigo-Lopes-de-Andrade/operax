import type { Metadata } from "next";

import { Brand } from "@/components/brand";
import { DEFAULT_AUTHENTICATED_PATH, safeNextPath } from "@/lib/navigation";

import { SignInForm } from "./sign-in-form";

export const metadata: Metadata = {
  title: "Entrar · OperaX",
};

type LoginPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const next = safeNextPath((await searchParams).next);
  const cameFromLink = next !== DEFAULT_AUTHENTICATED_PATH;

  return (
    <div className="bg-chrome flex min-h-dvh flex-col items-center justify-center gap-8 px-6 py-10">
      <Brand />

      <div className="bg-card w-full max-w-sm rounded-[24px] p-6 shadow-[var(--shadow-lg)]">
        {/* Pre-session surface: no employee data before authentication — no
            name, unit, time, occurrence type or count. The notice below speaks
            about the link, never about who or what is on the other side. */}
        {cameFromLink ? (
          <div className="border-line-subtle mb-5 border-b pb-5">
            <p className="text-ink text-base font-bold">
              Você abriu um link de ocorrência.
            </p>
            <p className="text-ink-muted mt-1 text-sm">
              Entre para vê-la. Você volta direto para esta ocorrência, não para
              a página inicial.
            </p>
          </div>
        ) : (
          <div className="mb-5">
            <h1 className="text-ink text-xl font-extrabold">Entrar</h1>
            <p className="text-ink-muted mt-1 text-sm">
              Use o e-mail cadastrado pela sua empresa.
            </p>
          </div>
        )}

        <SignInForm next={next} />
      </div>

      <p className="text-center text-xs text-white/50">
        Supervisor de unidade enxerga apenas a própria unidade.
      </p>
    </div>
  );
}
