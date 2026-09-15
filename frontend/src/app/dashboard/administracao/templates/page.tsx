import { MessageSquareOff } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { TemplateCatalog } from "@/components/canais/template-catalog";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { pageTitle } from "@/lib/brand";
import { loadConnections, loadTemplates } from "@/lib/canais/queries";
import { isAdmin, loadIdentity } from "@/lib/identity";

export const metadata: Metadata = {
  title: pageTitle("Templates"),
};

/**
 * Templates — o catálogo de mensagens do cliente, e o "Sincronizar" da WABA.
 *
 * A porta é a mesma de Conexões, e pelo mesmo motivo: criar, editar e
 * sincronizar template é escrita de configuração de canal, e só o
 * administrador a faz. Quem não alcança recebe 404 antes de qualquer leitura.
 * A fronteira de segurança não é esta: cada `PUT` e o `POST` perguntam
 * `util.is_admin` de novo no backend, e a tela só reflete.
 *
 * As duas leituras vão em paralelo: o catálogo, e as conexões — que dizem, pelas
 * flags do canal ativo, se o botão "Sincronizar" faz sentido. `null` na
 * segunda não derruba a tela: sem canal lido, não há botão, e a frase no
 * lugar dele diz o que sincroniza.
 */
export default async function TemplatesPage() {
  const identity = await loadIdentity();

  if (!isAdmin(identity?.role)) {
    notFound();
  }

  const [templates, connections] = await Promise.all([
    loadTemplates(),
    loadConnections(),
  ]);

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Administração
        </p>
        <h1 className="text-ink text-2xl font-extrabold">Templates</h1>
        <p className="text-ink-muted mt-1 max-w-2xl text-sm text-pretty">
          O texto de cada alerta e as variáveis que ele carrega. O estado na
          Meta vem da sincronização com a WABA do cliente, nunca da mão; para os
          canais sem template, o corpo daqui é o que sai.
        </p>
      </header>

      {templates ? (
        <TemplateCatalog templates={templates} connections={connections} />
      ) : (
        <Card className="p-6">
          <EmptyState
            icon={MessageSquareOff}
            tone="neutral"
            title="Os templates não puderam ser lidos"
            description="O catálogo vem da API do painel, e ela não respondeu agora. Nada foi alterado."
          />
        </Card>
      )}
    </div>
  );
}
