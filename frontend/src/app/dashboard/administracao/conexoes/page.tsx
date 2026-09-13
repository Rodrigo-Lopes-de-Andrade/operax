import { Unplug } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Connections } from "@/components/canais/connections";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { pageTitle } from "@/lib/brand";
import { loadConnections } from "@/lib/canais/queries";
import { isAdmin, loadIdentity } from "@/lib/identity";

export const metadata: Metadata = {
  title: pageTitle("Conexões"),
};

/**
 * Conexões — o canal por onde os alertas saem, e o que está travando o envio.
 *
 * ⚠️ A PORTA É `isAdmin`, E ELA É MAIS ESTREITA QUE A ROTA DE PROPÓSITO
 * `GET /canais/conexoes` responde a qualquer membro do cliente — a leitura sai
 * por `user_scope` e quem recorta é a policy, que libera `alert_rule` e
 * `message_template` a todo `authenticated` do tenant. Esta página não segue a
 * rota, e não é esquecimento: Conexões é configuração de canal, e a próxima
 * etapa (C2) põe aqui a escrita de credencial — que só o administrador faz.
 * Abrir a tela a quem não vai poder escrever nela seria oferecer, hoje, uma
 * porta que amanhã fecha na cara. O item da navegação obedece à mesma
 * condição (`showAdminWrites`), para que as duas metades concordem.
 *
 * Quem não alcança recebe 404 em vez de tela vazia — uma tela vazia com este
 * título já conta que a área existe. A fronteira de segurança não é esta: é a
 * policy e o backend, que revalidam papel a cada chamada.
 */
export default async function ConexoesPage() {
  const identity = await loadIdentity();

  if (!isAdmin(identity?.role)) {
    notFound();
  }

  const screen = await loadConnections();

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Administração
        </p>
        <h1 className="text-ink text-2xl font-extrabold">Conexões</h1>
        <p className="text-ink-muted mt-1 max-w-2xl text-sm text-pretty">
          O canal de WhatsApp por onde os alertas saem, o que ele exige, e qual
          regra está presa em qual template. Tudo aqui é lido do que o produto
          já sabe; nada é alterado nesta tela.
        </p>
      </header>

      {screen ? (
        <Connections screen={screen} />
      ) : (
        <Card className="p-6">
          <EmptyState
            icon={Unplug}
            tone="neutral"
            title="As conexões não puderam ser lidas"
            description="O estado do canal vem da API do painel, e ela não respondeu agora. Nada foi alterado."
          />
        </Card>
      )}
    </div>
  );
}
