import { Users } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Contacts } from "@/components/canais/contacts";
import type { UnitChoice } from "@/components/dp/work-posts";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { pageTitle } from "@/lib/brand";
import { loadContacts } from "@/lib/canais/queries";
import { isAdmin, loadIdentity } from "@/lib/identity";
import { loadUnits } from "@/lib/ponto/queries";
import { getServerSupabase } from "@/lib/supabase-server";

export const metadata: Metadata = {
  title: pageTitle("Destinatários"),
};

/**
 * Destinatários — quem recebe o alerta, e por qual unidade responde.
 *
 * A porta é a mesma de Conexões, e pelo mesmo motivo: cadastrar contato e
 * montar a matriz unidade × responsabilidade é escrita de configuração de
 * canal, e só o administrador a faz (`POST`/`PUT` de `/canais/destinatarios`
 * perguntam `util.is_admin` de novo no backend). Quem não alcança recebe 404
 * antes de qualquer leitura — uma tela vazia com este título já conta que a
 * área existe. O item da navegação obedece à mesma condição
 * (`showAdminWrites`).
 *
 * Duas leituras em paralelo: os contatos pela API (Caminho 2 — o WhatsApp e
 * o e-mail de um contato são dado individual) e as unidades do seletor por
 * `public.vw_unit` (Caminho 1), como o resto do painel. `null` nos contatos
 * é "não pôde ser lido", não "nenhum contato".
 */
export default async function DestinatariosPage() {
  const identity = await loadIdentity();

  if (!isAdmin(identity?.role)) {
    notFound();
  }

  const supabase = await getServerSupabase();
  const [contacts, units] = await Promise.all([
    loadContacts(),
    loadUnits(supabase),
  ]);

  const choices: UnitChoice[] = units.map((unit) => ({
    id: unit.unitId,
    name: unit.name,
  }));

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Administração
        </p>
        <h1 className="text-ink text-2xl font-extrabold">Destinatários</h1>
        <p className="text-ink-muted mt-1 max-w-2xl text-sm text-pretty">
          Quem recebe o alerta — pessoa, grupo de WhatsApp ou lista de e-mail —
          e por qual unidade cada um responde. Uma regra pode nomear o contato
          ou pedir a responsabilidade, que a matriz resolve por unidade na hora
          do envio. Um contato nunca é apagado: desativado, ele fica na lista.
        </p>
      </header>

      {contacts ? (
        <Contacts contacts={contacts} units={choices} />
      ) : (
        <Card className="p-6">
          <EmptyState
            icon={Users}
            tone="neutral"
            title="Os destinatários não puderam ser lidos"
            description="A lista vem da API do painel, e ela não respondeu agora. Nada foi alterado."
          />
        </Card>
      )}
    </div>
  );
}
