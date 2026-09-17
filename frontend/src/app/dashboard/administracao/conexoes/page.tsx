import { Unplug } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Connections } from "@/components/canais/connections";
import { CredentialForm } from "@/components/canais/credential-form";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { pageTitle } from "@/lib/brand";
import { CHANNEL_LABEL, CHANNELS } from "@/lib/canais/labels";
import {
  loadConnections,
  loadCredential,
  loadDeliveryByChannel,
  loadProviderForms,
  loadTelegramAdhesion,
} from "@/lib/canais/queries";
import { isAdmin, loadIdentity } from "@/lib/identity";

export const metadata: Metadata = {
  title: pageTitle("Conexões"),
};

/**
 * Conexões — os dois canais por onde os alertas saem, o que está travando o
 * envio em cada um, e a credencial que liga cada um.
 *
 * ⚠️ A PORTA É `isAdmin`, E ELA É MAIS ESTREITA QUE A ROTA DE PROPÓSITO
 * `GET /canais/conexoes` responde a qualquer membro do cliente — a leitura sai
 * por `user_scope` e quem recorta é a policy, que libera `alert_rule` e
 * `message_template` a todo `authenticated` do tenant. Esta página não segue a
 * rota, e não é esquecimento: Conexões é configuração de canal, e a escrita de
 * credencial (`POST /canais/credencial`) e o registro do bot
 * (`POST /canais/telegram/conectar`) vivem aqui — e só o administrador os
 * faz. Abrir a tela a quem não pode escrever nela seria oferecer uma porta
 * que fecha na cara. O item da navegação obedece à mesma condição
 * (`showAdminWrites`), para que as duas metades concordem.
 *
 * Quem não alcança recebe 404 em vez de tela vazia — uma tela vazia com este
 * título já conta que a área existe. A fronteira de segurança não é esta: é a
 * policy e o backend, que revalidam papel a cada chamada — cada `POST`
 * pergunta `util.is_admin` de novo, e a tela só reflete.
 *
 * As seis leituras vão em paralelo: as conexões, os formulários, uma
 * credencial por canal, a adesão por unidade e as entregas por canal — as
 * duas últimas pelo Caminho 1, porque são contagem sem nome. Cada formulário
 * só aparece quando as duas dele (`credencial` do canal, `provedores`)
 * vieram; `null` numa delas é sessão ou papel, e a página já tem o estado
 * para isso — não inventa outro. Os canais e a ordem deles vêm de `CHANNELS`:
 * nenhum nome de canal é escrito aqui.
 */
export default async function ConexoesPage() {
  const identity = await loadIdentity();

  if (!isAdmin(identity?.role)) {
    notFound();
  }

  const [screen, forms, credentials, adhesion, deliveries] = await Promise.all([
    loadConnections(),
    loadProviderForms(),
    Promise.all(CHANNELS.map((channel) => loadCredential(channel))),
    loadTelegramAdhesion(),
    loadDeliveryByChannel(),
  ]);

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Administração
        </p>
        <h1 className="text-ink text-2xl font-extrabold">Conexões</h1>
        <p className="text-ink-muted mt-1 max-w-2xl text-sm text-pretty">
          Os canais por onde os alertas saem, o que cada um exige, e o que está
          preso em cada um. WhatsApp e Telegram coexistem: quem aderiu ao bot
          recebe por Telegram, quem não aderiu continua recebendo por WhatsApp.
          O que se grava aqui é a credencial de cada canal — validada no
          provedor antes — e o registro do bot no Telegram.
        </p>
      </header>

      {screen ? (
        <Connections
          screen={screen}
          adhesion={adhesion}
          deliveries={deliveries}
          canWrite={isAdmin(identity?.role)}
        />
      ) : (
        <Card className="p-6">
          <EmptyState
            icon={Unplug}
            tone="neutral"
            title="As conexões não puderam ser lidas"
            description="O estado dos canais vem da API do painel, e ela não respondeu agora. Nada foi alterado."
          />
        </Card>
      )}

      {forms
        ? CHANNELS.map((channel, index) => {
            const credential = credentials[index];

            return credential ? (
              <section
                key={channel}
                aria-labelledby={`credential-${channel}`}
                className="flex flex-col gap-3"
              >
                <h2
                  id={`credential-${channel}`}
                  className="text-ink text-lg font-extrabold"
                >
                  Credencial do {CHANNEL_LABEL[channel]}
                </h2>
                <CredentialForm
                  forms={forms.filter((form) => form.channel === channel)}
                  status={credential}
                />
              </section>
            ) : null;
          })
        : null}
    </div>
  );
}
