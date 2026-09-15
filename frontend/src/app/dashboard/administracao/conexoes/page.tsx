import { Unplug } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Connections } from "@/components/canais/connections";
import { CredentialForm } from "@/components/canais/credential-form";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { pageTitle } from "@/lib/brand";
import {
  loadConnections,
  loadCredential,
  loadProviderForms,
} from "@/lib/canais/queries";
import { isAdmin, loadIdentity } from "@/lib/identity";

export const metadata: Metadata = {
  title: pageTitle("Conexões"),
};

/**
 * Conexões — o canal por onde os alertas saem, o que está travando o envio, e
 * a credencial que o liga.
 *
 * ⚠️ A PORTA É `isAdmin`, E ELA É MAIS ESTREITA QUE A ROTA DE PROPÓSITO
 * `GET /canais/conexoes` responde a qualquer membro do cliente — a leitura sai
 * por `user_scope` e quem recorta é a policy, que libera `alert_rule` e
 * `message_template` a todo `authenticated` do tenant. Esta página não segue a
 * rota, e não é esquecimento: Conexões é configuração de canal, e a escrita de
 * credencial (`POST /canais/credencial`) vive aqui — e só o administrador a
 * faz. Abrir a tela a quem não pode escrever nela seria oferecer uma porta que
 * fecha na cara. O item da navegação obedece à mesma condição
 * (`showAdminWrites`), para que as duas metades concordem.
 *
 * Quem não alcança recebe 404 em vez de tela vazia — uma tela vazia com este
 * título já conta que a área existe. A fronteira de segurança não é esta: é a
 * policy e o backend, que revalidam papel a cada chamada — o `POST` pergunta
 * `util.is_admin` de novo, e a tela só reflete.
 *
 * As três leituras vão em paralelo. O formulário só aparece quando as duas
 * dele (`credencial`, `provedores`) vieram; `null` numa delas é sessão ou
 * papel, e a página já tem o estado para isso — não inventa outro.
 */
export default async function ConexoesPage() {
  const identity = await loadIdentity();

  if (!isAdmin(identity?.role)) {
    notFound();
  }

  const [screen, credential, forms] = await Promise.all([
    loadConnections(),
    loadCredential(),
    loadProviderForms(),
  ]);

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Administração
        </p>
        <h1 className="text-ink text-2xl font-extrabold">Conexões</h1>
        <p className="text-ink-muted mt-1 max-w-2xl text-sm text-pretty">
          O canal de WhatsApp por onde os alertas saem, o que ele exige, e qual
          regra está presa em qual template. A única coisa que se grava aqui é a
          credencial do canal — validada no provedor antes.
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

      {credential && forms ? (
        <CredentialForm forms={forms} status={credential} />
      ) : null}
    </div>
  );
}
