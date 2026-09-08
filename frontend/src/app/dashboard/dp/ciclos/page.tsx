import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { MonthlyCycle } from "@/components/dp/monthly-cycle";
import { pageTitle } from "@/lib/brand";
import { loadCycles } from "@/lib/dp/queries";
import { parseCycleFilters } from "@/lib/dp/url";
import { isAdmin, loadIdentity } from "@/lib/identity";
import { todayInTenantZone, type RawSearchParams } from "@/lib/ponto/filters";

export const metadata: Metadata = {
  title: pageTitle("Ciclo mensal"),
};

/**
 * Ciclo mensal de cesta e de vale transporte.
 *
 * ⛔ QUEM ENTRA É QUEM TEM `compensation`, E NÃO QUEM É ADMINISTRADOR
 * O portão é a resposta de `GET /dp/ciclos`: 403 vira ausência de tela. Uma
 * lista de papéis aqui erraria nos dois sentidos, e erra hoje —
 * `app.domain_permission` dá `compensation` a `accounting` e a `executive`, que
 * **não** são admin, e não o dá a `hr`, que é. A migration do S2 nomeia
 * `accounting` como quem confere a remessa, e o backend tirou a exigência de
 * admin desta leitura exatamente por isso: *"exigir admin aqui devolveria a
 * mesma parede uma porta adiante"* (`routers/dp.py`). Era essa parede.
 *
 * ⚠️ ESCREVER É OUTRO EIXO, E ELE CONTINUA SENDO `util.is_admin`
 * Apurar e gerar exigem `compensation` **e** admin (`_pode_escrever_catalogo`).
 * `isAdmin` é a cópia de `util.is_admin`, que é lista de papéis fixa nos dois
 * lados e já vivia em `lib/identity.ts` — não é a matriz de domínios, que é
 * dado que o cliente edita. Nenhuma rota de ciclo devolve `can_write`; quando
 * devolver, esta linha sai. Reportado.
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

  if (!identity) {
    notFound();
  }

  const filters = parseCycleFilters(await searchParams, todayInTenantZone());
  const history = await loadCycles(filters);

  if (history.status === "forbidden") {
    notFound();
  }

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

      <MonthlyCycle
        filters={filters}
        history={history}
        canWrite={isAdmin(identity.role)}
      />
    </div>
  );
}
