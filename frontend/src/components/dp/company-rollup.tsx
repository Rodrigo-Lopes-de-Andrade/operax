import { Building2 } from "lucide-react";

import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Table, type Column } from "@/components/ui/table";
import { formatCents, formatCurrency, toCents } from "@/lib/dp/format";
import type { CompanyRollupResult } from "@/lib/dp/queries";
import { panelHref, type PanelFilters } from "@/lib/dp/url";
import { formatNumber } from "@/lib/ponto/format";

const COLUMNS: Column[] = [
  { key: "empresa", label: "Empresa" },
  {
    key: "ativos",
    label: "Ativos",
    align: "right",
    numeric: true,
    width: "18%",
  },
  {
    key: "folha",
    label: "Folha base",
    align: "right",
    numeric: true,
    width: "26%",
  },
];

/**
 * Resumo financeiro por empresa (`ANEXO` §2e) — e é ele que confirma a regra 5
 * do projeto: a agregação vai por colaborador → empresa, nunca por
 * departamento → empresa. Quem responde é `GET /dp/painel` recortado por
 * empresa, que é o mesmo caminho e a mesma conta do cartão de folha base.
 *
 * ⚠️ A SOMA DAS LINHAS É CONFERIDA CONTRA O TOTAL, NA TELA
 * A lista de empresas sai de `vw_unit`, então uma empresa sem unidade ativa no
 * cadastro não tem linha aqui — e ainda assim tem gente na folha base do cartão
 * acima. Uma tabela que soma menos que o número logo acima dela, em silêncio, é
 * a classe de defeito que custa a confiança do painel inteiro. Então a diferença
 * é calculada e dita.
 */
export function CompanyRollup({
  rollup,
  basePayroll,
  filters,
}: {
  rollup: CompanyRollupResult;
  /** A folha base do recorte inteiro — o total contra o qual as linhas fecham. */
  basePayroll: string;
  filters: PanelFilters;
}) {
  if (rollup.status === "unavailable") {
    return (
      <Card>
        <CardHeader
          eyebrow="Rodapé"
          title="Resumo financeiro por empresa"
          note="Ativos e folha base de cada CNPJ."
        />
        <div className="p-6">
          <EmptyState
            icon={Building2}
            tone="alert"
            title="O resumo por empresa não pôde ser montado"
            description="Ele é uma leitura por empresa, e pelo menos uma delas não respondeu. Uma lista à qual falta uma empresa somaria menos que a folha base sem dizer qual sumiu, então ela não é mostrada pela metade."
          />
        </div>
      </Card>
    );
  }

  const total = toCents(basePayroll);
  const somado = rollup.rows.reduce(
    (sum, row) => sum + toCents(row.basePayroll),
    0,
  );
  const diferenca = total - somado;

  const rows = rollup.rows
    .slice()
    .sort((a, b) => toCents(b.basePayroll) - toCents(a.basePayroll))
    .map((row) => ({
      id: row.companyId,
      href: panelHref(filters, { companyId: row.companyId, unitId: null }),
      cells: {
        empresa: <span className="text-ink font-bold">{row.companyName}</span>,
        ativos: formatNumber(row.activeHeadcount),
        folha: formatCurrency(row.basePayroll),
      },
    }));

  return (
    <Card>
      <CardHeader
        eyebrow="Rodapé"
        title="Resumo financeiro por empresa"
        note="Ativos e folha base de cada CNPJ. A linha abre o painel na empresa."
      />
      <Table
        columns={COLUMNS}
        rows={rows}
        caption="Ativos e folha salarial base por empresa"
        empty={
          <div className="p-6">
            <EmptyState
              icon={Building2}
              tone="neutral"
              title="Nenhuma empresa no recorte"
              compact
            />
          </div>
        }
      />
      <p className="text-ink-muted border-line-subtle border-t px-5 py-3 text-xs text-pretty">
        {diferenca === 0
          ? `As empresas somam ${formatCents(somado)} — a mesma folha base do recorte.`
          : `As empresas somam ${formatCents(somado)}, e a folha base do recorte é ${formatCents(
              total,
            )}: faltam ${formatCents(
              diferenca,
            )} de quem está numa empresa sem unidade ativa no cadastro, que é de onde esta lista sai.`}
      </p>
    </Card>
  );
}
