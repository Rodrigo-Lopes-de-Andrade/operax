import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { MonthlyCycle } from "@/components/dp/monthly-cycle";
import { pageTitle } from "@/lib/brand";
import { parseCycleFilters } from "@/lib/dp/url";
import { isAdmin, loadIdentity } from "@/lib/identity";
import { todayInTenantZone, type RawSearchParams } from "@/lib/ponto/filters";

export const metadata: Metadata = {
  title: pageTitle("Ciclo mensal"),
};

/**
 * Ciclo mensal de cesta e de vale transporte.
 *
 * `isAdmin` como na tela de folha: apurar uma competência é escrita, e o
 * backend pergunta `util.is_admin` e o domínio de remuneração ao banco a cada
 * chamada. Quem não escreve receberia 403 em todos os botões, e uma tela cujos
 * botões todos recusam é pior que porta nenhuma.
 *
 * A competência mora na query string: o link que alguém manda pedindo "confere
 * o vale transporte de setembro" precisa abrir setembro, e não o mês de quem
 * clicou.
 */
export default async function CiclosPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const identity = await loadIdentity();

  if (!isAdmin(identity?.role)) {
    notFound();
  }

  const filters = parseCycleFilters(await searchParams, todayInTenantZone());

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Departamento pessoal
        </p>
        <h1 className="text-ink text-2xl font-extrabold">Ciclo mensal</h1>
        <p className="text-ink-muted mt-1 max-w-3xl text-sm text-pretty">
          Cesta e vale transporte são a mesma rotina com regras diferentes:
          apura-se a competência, confere-se pessoa a pessoa com o motivo de
          quem ficou de fora, e só então o ciclo é gerado. Gerar é o que congela
          o número — a partir dali, corrigir é ciclo novo.
        </p>
      </header>

      <MonthlyCycle filters={filters} />
    </div>
  );
}
