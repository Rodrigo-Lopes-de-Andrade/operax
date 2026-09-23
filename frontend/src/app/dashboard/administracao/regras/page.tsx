import { BellRing } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Rules } from "@/components/canais/rules";
import type { UnitChoice } from "@/components/dp/work-posts";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { pageTitle } from "@/lib/brand";
import { loadContacts, loadRules, loadTemplates } from "@/lib/canais/queries";
import { isAdmin, loadIdentity } from "@/lib/identity";
import { loadUnits } from "@/lib/ponto/queries";
import { getServerSupabase } from "@/lib/supabase-server";

export const metadata: Metadata = {
  title: pageTitle("Regras"),
};

/**
 * Regras — que desvio, de que unidade, vai para quem, por onde; e o modo de
 * teste do S6 como botão.
 *
 * A porta é `isAdmin`, e aqui ela coincide com a rota: `GET /canais/regras`
 * é do administrador, porque `alert_rule_target` só tem policy de admin e um
 * supervisor receberia toda regra com `targets: []` e um "sem destino"
 * falso. Quem não alcança recebe 404 antes de qualquer leitura. A fronteira
 * de segurança continua no backend: `ligar` é a única porta que liga, e é
 * ele que exige destino e template — a tela mostra o 409 como veio.
 *
 * Cinco leituras em paralelo: as regras, o catálogo de tipos de desvio
 * (`app.deviation_type` não chega ao navegador — vem pela API, com o rótulo
 * em pt-BR), os templates ativos, os contatos (para os destinos) e as
 * unidades do seletor por `public.vw_unit` (Caminho 1). `null` nas regras é
 * "não pôde ser lido"; `null` nas outras deixa a tela em pé e o seletor diz
 * o que faltou.
 */
export default async function RegrasPage() {
  const identity = await loadIdentity();

  if (!isAdmin(identity?.role)) {
    notFound();
  }

  const supabase = await getServerSupabase();
  const [rules, templates, contacts, units] = await Promise.all([
    loadRules(),
    loadTemplates(),
    loadContacts(),
    loadUnits(supabase),
  ]);

  const choices: UnitChoice[] = units.map((unit) => ({
    id: unit.unitId,
    name: unit.name,
  }));
  // O relógio é lido aqui, no servidor, como a página de Colaboradores já faz:
  // ler a hora durante o render do cliente é chamada impura, e a lista se
  // refaz por `router.refresh()` de todo jeito. É o que separa silêncio
  // vigente de silêncio vencido.
  const now = new Date().getTime();

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Administração
        </p>
        <h1 className="text-ink text-2xl font-extrabold">Regras</h1>
        <p className="text-ink-muted mt-1 max-w-2xl text-sm text-pretty">
          Cada regra diz que tipo de desvio, de que unidade, vai para quem e por
          qual canal. Ligar exige destino ativo e, na mensageria, template do
          catálogo — é o backend que confere. O que impede uma regra ligada de
          entregar hoje aparece ao lado dela.
        </p>
      </header>

      {rules ? (
        <Rules
          rules={rules}
          contacts={contacts}
          units={choices}
          now={now}
          templates={templates}
        />
      ) : (
        <Card className="p-6">
          <EmptyState
            icon={BellRing}
            tone="neutral"
            title="As regras não puderam ser lidas"
            description="A lista vem da API do painel, e ela não respondeu agora. Nada foi alterado."
          />
        </Card>
      )}
    </div>
  );
}
