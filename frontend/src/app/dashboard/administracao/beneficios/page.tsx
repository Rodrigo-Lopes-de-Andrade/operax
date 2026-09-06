import { Tags } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { BenefitCatalog } from "@/components/dp/benefit-catalog";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { Tabs, type TabItem } from "@/components/ui/tabs";
import { pageTitle } from "@/lib/brand";
import { loadBenefitCatalog } from "@/lib/dp/queries";
import { catalogHref, parseCatalogFilters } from "@/lib/dp/url";
import { loadIdentity, reachesHr } from "@/lib/identity";
import type { RawSearchParams } from "@/lib/ponto/filters";

export const metadata: Metadata = {
  title: pageTitle("Benefícios"),
};

/**
 * Catálogo de benefícios — o preço do tenant, com vigência.
 *
 * A aba mora na query string, como toda aba deste produto: ela é parte do
 * recorte, e o botão "voltar" do navegador tem de andar por ela. A data também
 * — "o catálogo" sem data é o de hoje, e quem confere um ciclo do mês passado
 * precisa do preço daquele dia.
 *
 * Domínio `compensation`: quem não o alcança recebe 403 da API e a tela mostra
 * o estado vazio. A fronteira é essa recusa, não o `notFound` abaixo, que só
 * evita oferecer uma porta da área de administração a quem não a acompanha.
 */
export default async function BeneficiosPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const identity = await loadIdentity();

  if (!reachesHr(identity?.role)) {
    notFound();
  }

  const filters = parseCatalogFilters(await searchParams);
  const catalog = await loadBenefitCatalog(filters);

  if (!catalog || catalog.types.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        <Header />
        <Card className="p-6">
          <EmptyState
            icon={Tags}
            tone="neutral"
            title={
              catalog
                ? "Nenhuma verba no catálogo"
                : "O catálogo não pôde ser lido"
            }
            description={
              catalog
                ? "O catálogo de verbas do tenant está vazio. Ele é semeado com a migração do catálogo de benefícios."
                : "O catálogo vem da API do painel, e ela não respondeu — ou seu papel não alcança o domínio de remuneração. Nada foi alterado."
            }
          />
        </Card>
      </div>
    );
  }

  const active =
    catalog.types.find((type) => type.code === filters.type) ??
    catalog.types[0];

  const items: TabItem[] = catalog.types.map((type) => ({
    value: type.code,
    label: type.name,
    href: catalogHref(filters, { type: type.code }),
    count:
      type.code === "transport_voucher"
        ? catalog.fares.length
        : catalog.plans.filter((plan) => plan.benefit_type_code === type.code)
            .length,
  }));

  return (
    <div className="flex flex-col gap-4">
      <Header />
      <Tabs items={items} value={active.code} label="Tipos de benefício" />
      <BenefitCatalog catalog={catalog} filters={filters} type={active} />
    </div>
  );
}

function Header() {
  return (
    <header>
      <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
        Administração
      </p>
      <h1 className="text-ink text-2xl font-extrabold">Benefícios</h1>
      <p className="text-ink-muted mt-1 max-w-3xl text-sm text-pretty">
        O catálogo é o preço do tenant — plano, operadora e tarifa —, e cada
        valor vale a partir de uma data. Reajustar é abrir a próxima vigência,
        nunca corrigir a atual: o mês já apurado foi fechado com o valor que
        valia nele.
      </p>
    </header>
  );
}
