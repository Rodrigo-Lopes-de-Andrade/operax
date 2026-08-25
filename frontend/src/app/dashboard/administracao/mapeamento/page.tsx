import { Waypoints } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { UnitMapping } from "@/components/curadoria/unit-mapping";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { pageTitle } from "@/lib/brand";
import { loadUnitMapping } from "@/lib/curadoria/queries";
import { isAdmin, loadIdentity } from "@/lib/identity";

export const metadata: Metadata = {
  title: pageTitle("Mapeamento de unidades"),
};

/**
 * Curadoria origem → unidade.
 *
 * A fila que `cadastro.py` produz a cada promoção, do lado de quem a fecha. O
 * papel decide aqui, no servidor, e quem não alcança recebe 404 em vez de uma
 * tela vazia — uma tela vazia com este título já conta que a área existe. A
 * segurança não é essa: é a policy `mapa_admin` e o backend recusarem a escrita.
 */
export default async function MapeamentoPage() {
  const identity = await loadIdentity();

  if (!isAdmin(identity?.role)) {
    notFound();
  }

  const screen = await loadUnitMapping();

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Administração
        </p>
        <h1 className="text-ink text-2xl font-extrabold">
          Mapeamento de unidades
        </h1>
        <p className="text-ink-muted mt-1 max-w-2xl text-sm text-pretty">
          O departamento vem do sistema de ponto e a unidade é nossa. Enquanto
          os dois não estiverem ligados, quem está no departamento não aparece
          em nenhum recorte por unidade — não aparece como zero, some.
        </p>
      </header>

      {screen && screen.rows.length > 0 ? (
        <UnitMapping screen={screen} />
      ) : (
        <Card className="p-6">
          <EmptyState
            icon={Waypoints}
            tone="neutral"
            title={
              screen
                ? "Nenhum departamento veio da origem ainda"
                : "O mapeamento não pôde ser lido"
            }
            description={
              screen
                ? "A fila de curadoria nasce da promoção do cadastro. Quando a sincronização trouxer departamentos, eles aparecem aqui."
                : "A curadoria vem da API do painel, e ela não respondeu agora. Nada foi alterado."
            }
          />
        </Card>
      )}
    </div>
  );
}
