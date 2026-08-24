import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ImportWizard } from "@/components/rh/import-wizard";
import { pageTitle } from "@/lib/brand";
import { loadIdentity, reachesHr } from "@/lib/identity";
import { COLABORADORES_PATH } from "@/lib/rh/url";

export const metadata: Metadata = {
  title: pageTitle("Importação"),
};

/**
 * Importação de RH.
 *
 * Hoje a tela cobre os três modelos de RH. A importação de folha, desenhada no
 * mesmo fluxo de quatro passos, entra na trilha dela — o que muda é o tipo e o
 * destino, não a tela.
 */
export default async function ImportacaoPage() {
  const identity = await loadIdentity();

  if (!reachesHr(identity?.role)) {
    notFound();
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
            Administração
          </p>
          <h1 className="text-ink text-xl font-extrabold">Importação</h1>
        </div>
        <Link
          href={COLABORADORES_PATH}
          className="text-brand-strong text-sm font-bold underline"
        >
          Ver colaboradores
        </Link>
      </header>

      <ImportWizard />
    </div>
  );
}
