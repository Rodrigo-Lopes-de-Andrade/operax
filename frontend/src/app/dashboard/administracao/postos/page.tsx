import { MapPinned } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { WorkPosts, type UnitChoice } from "@/components/dp/work-posts";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { SelectNav, type SelectGroup } from "@/components/ui/select-nav";
import { pageTitle } from "@/lib/brand";
import { loadWorkPosts } from "@/lib/dp/queries";
import { parsePostosFilters, postosHref } from "@/lib/dp/url";
import { loadIdentity, reachesHr } from "@/lib/identity";
import type { RawSearchParams } from "@/lib/ponto/filters";
import { loadUnits } from "@/lib/ponto/queries";
import { getServerSupabase } from "@/lib/supabase-server";

export const metadata: Metadata = {
  title: pageTitle("Quadro de Postos"),
};

/**
 * Quadro de Postos — a estrutura da unidade, não dado de pessoa.
 *
 * Por isso o backend não pergunta domínio sensível nenhum aqui: o recorte é
 * `util.can_see_unit`, e o supervisor de uma unidade recebe o quadro dela e
 * nada mais. Quem escreve é `util.is_admin`, e é a própria resposta da API que
 * diz isso (`can_write`) — a tela não deduz de papel.
 *
 * O recorte de unidade mora na query string como no resto do produto: o link
 * do quadro de uma unidade tem de abrir nela.
 */
export default async function PostosPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const identity = await loadIdentity();

  if (!reachesHr(identity?.role)) {
    notFound();
  }

  const filters = parsePostosFilters(await searchParams);
  const supabase = await getServerSupabase();
  const [screen, units] = await Promise.all([
    loadWorkPosts(filters),
    loadUnits(supabase),
  ]);

  const choices: UnitChoice[] = units.map((unit) => ({
    id: unit.unitId,
    name: unit.name,
  }));

  const grupos: SelectGroup[] = [
    {
      label: "Unidades",
      options: choices.map((unit) => ({
        value: unit.id,
        label: unit.name,
        href: postosHref({ unitId: unit.id }),
      })),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
            Administração · Unidades
          </p>
          <h1 className="text-ink text-2xl font-extrabold">Quadro de Postos</h1>
        </div>
        <SelectNav
          label="Unidade"
          value={filters.unitId ?? ""}
          placeholder="Todas as unidades"
          placeholderHref={postosHref({ unitId: null })}
          groups={grupos}
        />
      </header>

      {screen ? (
        <WorkPosts screen={screen} units={choices} />
      ) : (
        <Card className="p-6">
          <EmptyState
            icon={MapPinned}
            tone="neutral"
            title="O Quadro não pôde ser lido"
            description="O Quadro de Postos vem da API do painel, e ela não respondeu agora. Nada foi alterado."
          />
        </Card>
      )}
    </div>
  );
}
