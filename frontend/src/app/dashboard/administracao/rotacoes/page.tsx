import { RotateCw } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { RotationQueue } from "@/components/curadoria/rotation-queue";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { pageTitle } from "@/lib/brand";
import { loadRotationQueue } from "@/lib/curadoria/queries";
import { isAdmin, loadIdentity } from "@/lib/identity";

export const metadata: Metadata = {
  title: pageTitle("Escalas de revezamento"),
};

/**
 * Curadoria horário → rotação.
 *
 * O papel decide aqui, no servidor, e quem não alcança recebe 404 em vez de uma
 * tela vazia — uma tela vazia com este título já conta que a área existe. A
 * segurança não é essa: é a policy `rotation_map_admin` e o backend recusarem a
 * escrita.
 */
export default async function RotacoesPage() {
  const identity = await loadIdentity();

  if (!isAdmin(identity?.role)) {
    notFound();
  }

  const screen = await loadRotationQueue();

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Administração
        </p>
        <h1 className="text-ink text-2xl font-extrabold">
          Escalas de revezamento
        </h1>
        <p className="text-ink-muted mt-1 max-w-2xl text-sm text-pretty">
          O sistema de ponto guarda a escala como uma semana de sete dias, e um
          12x36 gira a cada 48 horas — não cabe. Enquanto o ciclo não for
          declarado aqui, quem está nesses horários não gera indício errado e
          também não é medido.
        </p>
      </header>

      {screen && screen.rows.length > 0 ? (
        <RotationQueue screen={screen} />
      ) : (
        <Card className="p-6">
          <EmptyState
            icon={RotateCw}
            tone="neutral"
            title={
              screen
                ? "Nenhum horário sem expediente declarado"
                : "A fila de escalas não pôde ser lida"
            }
            description={
              screen
                ? "Só entram aqui os horários que a origem deixa em branco — os que ela descreve valem como estão, e não há o que curar."
                : "A curadoria vem da API do painel, e ela não respondeu agora. Nada foi alterado."
            }
          />
        </Card>
      )}
    </div>
  );
}
