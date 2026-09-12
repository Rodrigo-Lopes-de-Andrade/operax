import { ListChecks } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PayrollCodes } from "@/components/dp/payroll-codes";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { pageTitle } from "@/lib/brand";
import { loadPayrollCodes } from "@/lib/dp/queries";
import { isAdmin, loadIdentity } from "@/lib/identity";

export const metadata: Metadata = {
  title: pageTitle("Rubricas"),
};

/**
 * Curadoria de rubrica — como cada verba da folha é somada.
 *
 * A porta é `isAdmin`, como no mapeamento: lista fixa de papéis nos dois lados,
 * e por isso a cópia é tolerável. ⛔ O que NÃO se copia é a matriz de domínios:
 * a rota exige `compensation` **e** administração, e `hr` é admin sem
 * `compensation`. Ele passa esta porta, recebe 403 da API, e a tela mostra a
 * frase que o backend escreveu para ele — deduzir o domínio aqui seria a
 * matriz de sensibilidade escrita uma segunda vez, longe do banco que a altera.
 */
export default async function RubricasPage() {
  const identity = await loadIdentity();

  if (!isAdmin(identity?.role)) {
    notFound();
  }

  const result = await loadPayrollCodes();

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Administração
        </p>
        <h1 className="text-ink text-2xl font-extrabold">Rubricas</h1>
        <p className="text-ink-muted mt-1 max-w-2xl text-sm text-pretty">
          Cada código da folha do cliente recebe uma categoria contábil, e é ela
          que decide em qual indicador financeiro a verba entra. A lista nasce
          da folha importada; o trabalho aqui é conferir, não levantar.
        </p>
      </header>

      {result?.status === "ok" ? (
        <PayrollCodes screen={result.list} />
      ) : (
        <Card className="p-6">
          <EmptyState
            icon={ListChecks}
            tone="neutral"
            title={
              result?.status === "forbidden"
                ? "Este papel não classifica rubrica"
                : "As rubricas não puderam ser lidas"
            }
            description={
              result?.status === "forbidden"
                ? (result.detail ??
                  "A API recusou a leitura para o seu papel, sem dizer por quê.")
                : "A curadoria de rubricas vem da API do painel, e ela não respondeu agora. Nada foi alterado."
            }
          />
        </Card>
      )}
    </div>
  );
}
