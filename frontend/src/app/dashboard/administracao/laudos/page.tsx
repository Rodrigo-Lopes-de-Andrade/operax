import { FileCheck2 } from "lucide-react";
import type { Metadata } from "next";

import { ComplianceReports } from "@/components/dp/compliance-reports";
import type { UnitChoice } from "@/components/dp/work-posts";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { SelectNav, type SelectGroup } from "@/components/ui/select-nav";
import { pageTitle } from "@/lib/brand";
import { loadComplianceReports } from "@/lib/dp/queries";
import {
  laudosHref,
  parseLaudosFilters,
  REPORT_STATUS_LABEL,
  REPORT_STATUSES,
} from "@/lib/dp/url";
import type { RawSearchParams } from "@/lib/ponto/filters";
import { loadUnits } from "@/lib/ponto/queries";
import { getServerSupabase } from "@/lib/supabase-server";

export const metadata: Metadata = {
  title: pageTitle("Laudos"),
};

/**
 * Laudos — conformidade do local, não dado de pessoa.
 *
 * ⛔ A PÁGINA NÃO FECHA POR PAPEL, E A AUSÊNCIA É O DESENHO
 * A policy de `public.vw_unit_compliance` recorta por `util.can_see_unit` e a
 * rota não checa domínio: o supervisor de unidade recebe os laudos da unidade
 * dele, e é persona nomeada no PRD ("gestor de unidade consulta laudos da sua
 * unidade"). Repetir `reachesHr` aqui seria reerguer a parede uma porta adiante
 * — o ALTO 1 da revisão de frontend. Quem escreve é `util.is_admin`, e é a
 * resposta da rota que diz isso (`can_write`).
 *
 * Os dois recortes moram na query string. A unidade vai para a consulta da
 * view; a situação fica na tela, porque a view não tem coluna de situação de
 * propósito — a janela de "a vencer" é declaração da UI.
 */
export default async function LaudosPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const filters = parseLaudosFilters(await searchParams);
  const supabase = await getServerSupabase();
  const [screen, units] = await Promise.all([
    loadComplianceReports(supabase, filters),
    loadUnits(supabase),
  ]);

  const choices: UnitChoice[] = units.map((unit) => ({
    id: unit.unitId,
    name: unit.name,
  }));

  const unidades: SelectGroup[] = [
    {
      label: "Unidades",
      options: choices.map((unit) => ({
        value: unit.id,
        label: unit.name,
        href: laudosHref(filters, { unitId: unit.id }),
      })),
    },
  ];

  const situacoes: SelectGroup[] = [
    {
      label: "Situação",
      options: REPORT_STATUSES.map((status) => ({
        value: status,
        label: REPORT_STATUS_LABEL[status],
        href: laudosHref(filters, { status }),
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
          <h1 className="text-ink text-2xl font-extrabold">Laudos</h1>
        </div>
        <div className="flex flex-wrap gap-3">
          <SelectNav
            label="Unidade"
            value={filters.unitId ?? ""}
            placeholder="Todas as unidades"
            placeholderHref={laudosHref(filters, { unitId: null })}
            groups={unidades}
          />
          <SelectNav
            label="Situação"
            value={filters.status ?? ""}
            placeholder="Todas as situações"
            placeholderHref={laudosHref(filters, { status: null })}
            groups={situacoes}
          />
        </div>
      </header>

      {screen ? (
        <ComplianceReports
          screen={screen}
          units={choices}
          status={filters.status}
          unitId={filters.unitId}
        />
      ) : (
        <Card className="p-6">
          <EmptyState
            icon={FileCheck2}
            tone="neutral"
            title="Os laudos não puderam ser lidos"
            description="A lista de laudos vem de uma view do banco, e a leitura não respondeu agora. Nada foi alterado."
          />
        </Card>
      )}
    </div>
  );
}
