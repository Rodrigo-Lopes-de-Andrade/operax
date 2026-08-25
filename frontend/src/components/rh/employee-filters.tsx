import { Card } from "@/components/ui/kpi-card";
import { SearchBox } from "@/components/rh/search-box";
import { SelectNav, type SelectGroup } from "@/components/ui/select-nav";
import { PENDENCIA_LABEL, STATUS_LABEL } from "@/lib/rh/labels";
import type { HrEmployeeRow } from "@/lib/rh/queries";
import { PENDENCIAS, STATUSES, rhHref, type RhFilters } from "@/lib/rh/url";

/**
 * O recorte da lista. Unidade, situação, pendência e busca — nada de "Aplicar":
 * cada controle é um link, o recorte é a URL, e o link é o que se manda para um
 * colega olhar.
 *
 * As unidades vêm das próprias linhas: quem não alcança uma unidade não recebe
 * nenhuma linha dela, então ela não aparece no filtro. Um filtro que oferece uma
 * unidade e devolve vazio ensina que a unidade existe.
 */
export function EmployeeFilters({
  filters,
  rows,
}: {
  filters: RhFilters;
  rows: HrEmployeeRow[];
}) {
  const units = [
    ...new Map(
      rows
        .filter((row) => row.unit_id && row.unit_name)
        .map((row) => [row.unit_id as string, row.unit_name as string]),
    ).entries(),
  ].sort((a, b) => a[1].localeCompare(b[1], "pt-BR"));

  const unitGroups: SelectGroup[] = [
    {
      label: "Unidades",
      options: units.map(([id, name]) => ({
        value: id,
        label: name,
        href: rhHref(filters, { unit: id }),
      })),
    },
  ];

  const statusGroups: SelectGroup[] = [
    {
      label: "Situação",
      options: STATUSES.map((status) => ({
        value: status,
        label: STATUS_LABEL[status],
        href: rhHref(filters, { status }),
      })),
    },
  ];

  const pendenciaGroups: SelectGroup[] = [
    {
      label: "Pendência",
      options: PENDENCIAS.map((pendencia) => ({
        value: pendencia,
        label: PENDENCIA_LABEL[pendencia],
        href: rhHref(filters, { pendencia }),
      })),
    },
  ];

  return (
    <Card className="flex flex-wrap items-end gap-4 px-5 py-4">
      <SearchBox filters={filters} />
      <SelectNav
        label="Unidade"
        value={filters.unit ?? ""}
        placeholder="Todas as unidades"
        placeholderHref={rhHref(filters, { unit: null })}
        groups={unitGroups}
      />
      <SelectNav
        label="Situação"
        value={filters.status ?? ""}
        placeholder="Todas"
        placeholderHref={rhHref(filters, { status: null })}
        groups={statusGroups}
      />
      <SelectNav
        label="Pendência"
        value={filters.pendencia ?? ""}
        placeholder="Qualquer"
        placeholderHref={rhHref(filters, { pendencia: null })}
        groups={pendenciaGroups}
      />
    </Card>
  );
}
