import type { Metadata } from "next";
import { headers } from "next/headers";

import { brandForHost, pageTitle } from "@/lib/brand";

import { AcceptInvite } from "./accept-invite";

export const metadata: Metadata = {
  title: pageTitle("Definir senha"),
};

/**
 * Para onde o link do e-mail de convite leva (`{dashboard_url}/convite`) — e
 * também o de "Esqueci minha senha" (`resetPasswordForEmail`).
 *
 * Fora do `/dashboard` de propósito: quem chega aqui ainda não tem sessão — o
 * link é que a abre —, e `proxy.ts` deixa a rota passar nos dois sentidos.
 * Superfície pré-sessão: nenhum dado do cliente antes da sessão existir.
 */
export default async function ConvitePage() {
  const brand = brandForHost((await headers()).get("host"));

  return (
    <main
      data-brand={brand.slug}
      data-entry=""
      className="flex min-h-dvh items-center justify-center px-6 py-12"
      style={{ background: "var(--entry-ground)" }}
    >
      <div className="w-full max-w-sm">
        <p
          className="text-xs font-semibold tracking-[0.14em] uppercase"
          style={{ color: "var(--entry-accent-text)" }}
        >
          Acesso ao painel
        </p>
        {/* O título é do componente: convite e recuperação usam esta rota, e
            só o link — lido no navegador — diz qual dos dois chegou. */}
        <div className="mt-2">
          <AcceptInvite />
        </div>
      </div>
    </main>
  );
}
