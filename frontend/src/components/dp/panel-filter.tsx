import { X } from "lucide-react";
import Link from "next/link";

import { Card } from "@/components/ui/kpi-card";
import { SelectNav, type SelectGroup } from "@/components/ui/select-nav";
import type { CompanyChoice } from "@/lib/dp/queries";
import { panelHref, type PanelFilters } from "@/lib/dp/url";
import type { UnitOption } from "@/lib/ponto/queries";

/**
 * O recorte do painel: empresa e unidade, e nada além disso.
 *
 * Não há botão "aplicar" — cada opção é um link, o estado mora na query string,
 * e o link que um gestor cola numa conversa abre o painel no mesmo recorte. É a
 * mesma escolha da tela de Gestão de ponto, pelo mesmo motivo.
 *
 * Trocar de empresa limpa a unidade: a unidade escolhida pertence à empresa
 * anterior, e mantê-la devolveria um painel vazio com dois filtros que se
 * contradizem.
 */
export function PanelFilter({
  filters,
  companies,
  units,
}: {
  filters: PanelFilters;
  companies: CompanyChoice[];
  units: UnitOption[];
}) {
  const companyGroups: SelectGroup[] = [
    {
      label: "Empresas",
      options: companies.map((company) => ({
        value: company.id,
        label: company.name,
        href: panelHref(filters, { companyId: company.id, unitId: null }),
      })),
    },
  ];

  const unitGroups: SelectGroup[] = companies.map((company) => ({
    label: company.name,
    options: units
      .filter((unit) => unit.companyId === company.id)
      .map((unit) => ({
        value: unit.unitId,
        label: unit.name,
        href: panelHref(filters, {
          unitId: unit.unitId,
          companyId: unit.companyId,
        }),
      })),
  }));

  const cleared = panelHref({ unitId: null, companyId: null });
  const hasFilter = Boolean(filters.unitId || filters.companyId);

  return (
    <Card className="flex flex-wrap items-end justify-between gap-4 p-5">
      <div className="flex flex-wrap items-end gap-4">
        <SelectNav
          label="Empresa"
          placeholder="Todas as empresas"
          placeholderHref={panelHref(filters, {
            companyId: null,
            unitId: null,
          })}
          value={filters.companyId ?? ""}
          groups={companyGroups}
        />
        <SelectNav
          label="Unidade"
          placeholder="Todas as unidades"
          placeholderHref={panelHref(filters, { unitId: null })}
          value={filters.unitId ?? ""}
          groups={unitGroups}
        />
      </div>

      {hasFilter ? (
        <Link
          href={cleared}
          className="text-brand-strong inline-flex items-center gap-1.5 text-sm font-bold"
        >
          <X size={15} aria-hidden />
          Limpar recorte
        </Link>
      ) : null}
    </Card>
  );
}
