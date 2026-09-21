import { BotOff } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { Capabilities } from "@/components/assistente/capabilities";
import { DryRun } from "@/components/assistente/dry-run";
import { Executions } from "@/components/assistente/executions";
import { PromptEditor } from "@/components/assistente/prompt-editor";
import { VersionHistory } from "@/components/assistente/version-history";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { Tabs, type TabItem } from "@/components/ui/tabs";
import {
  loadCapabilities,
  loadExecutions,
  loadPromptScreen,
  loadVersions,
} from "@/lib/assistente/queries";
import {
  ASSISTENTE_CONFIG_LABEL,
  assistenteConfigHref,
  CONFIG_TAB_LABEL,
  CONFIG_TABS,
  parseConfigTab,
  parseVersionParam,
  parseWeeksParam,
  type ConfigTab,
} from "@/lib/assistente/url";
import { pageTitle } from "@/lib/brand";
import { isAdmin, loadIdentity } from "@/lib/identity";
import type { RawSearchParams } from "@/lib/ponto/filters";

export const metadata: Metadata = {
  title: pageTitle(ASSISTENTE_CONFIG_LABEL),
};

/**
 * Assistente (configuração) — as duas camadas do prompt, o histórico com
 * rollback, o teste, as capacidades e as execuções. O "Assistente" do topo é
 * a conversa; este é o que a governa.
 *
 * A porta é a mesma de Conexões, e pelo mesmo motivo: `GET /prompt` e
 * `GET /versoes` respondem a qualquer membro (a RLS devolve `draft = null` a
 * quem não é admin), mas tudo o que se faz aqui é escrita de configuração —
 * salvar, publicar, restaurar, ligar e desligar métrica — e só o administrador
 * a faz. Abrir a tela a quem não pode escrever nela seria oferecer uma porta
 * que fecha na cara; quem não alcança recebe 404 em vez de tela vazia. A
 * fronteira de segurança não é esta: cada escrita pergunta `util.is_admin` de
 * novo no backend, e a tela só reflete.
 *
 * A aba mora na query string (`aba=`), a versão aberta no Histórico também
 * (`versao=`) e a janela de Execuções também (`semanas=`): um link abre no
 * lugar certo, com o recorte certo. Cada aba lê só o que ela usa —
 * Configuração precisa do prompt e das versões (o aviso da SPEC §2 resolve o
 * id da origem a número pela lista); Teste precisa do prompt para saber se
 * há rascunho; Histórico, das versões; Capacidades, do catálogo; Execuções,
 * dos turnos, do custo e do total de teste da janela.
 */
export default async function AssistenteConfigPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const identity = await loadIdentity();

  if (!isAdmin(identity?.role)) {
    notFound();
  }

  const params = await searchParams;
  const tab = parseConfigTab(params);
  const content = await loadTab(
    tab,
    parseVersionParam(params),
    parseWeeksParam(params),
  );

  const items: TabItem[] = CONFIG_TABS.map((value) => ({
    value,
    label: CONFIG_TAB_LABEL[value],
    href: assistenteConfigHref(value),
  }));

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Administração
        </p>
        <h1 className="text-ink text-2xl font-extrabold">
          {ASSISTENTE_CONFIG_LABEL}
        </h1>
        <p className="text-ink-muted mt-1 max-w-2xl text-sm text-pretty">
          O texto que governa o assistente é a camada da plataforma somada à do
          cliente. Aqui se edita a do cliente, se vê o histórico do que esteve
          no ar, se testa contra dado real e se escolhe quais métricas o
          assistente enxerga.
        </p>
      </header>

      <Tabs items={items} value={tab} label="Configuração do assistente" />

      {content}
    </div>
  );
}

async function loadTab(
  tab: ConfigTab,
  versionId: string | null,
  weeks: number,
): Promise<ReactNode> {
  switch (tab) {
    case "configuracao": {
      const [screen, versions] = await Promise.all([
        loadPromptScreen(),
        loadVersions(),
      ]);

      return screen ? (
        <PromptEditor screen={screen} versions={versions} />
      ) : (
        <Unavailable title="A configuração não pôde ser lida" />
      );
    }
    case "historico": {
      const versions = await loadVersions();

      return versions ? (
        <VersionHistory versions={versions} selectedId={versionId} />
      ) : (
        <Unavailable title="O histórico não pôde ser lido" />
      );
    }
    case "teste": {
      const screen = await loadPromptScreen();

      // `null` quando a leitura falhou (401/403/503), e a aba diz isso em vez
      // de afirmar que não há rascunho — a mesma honestidade da Configuração.
      return (
        <DryRun hasDraft={screen === null ? null : screen.draft !== null} />
      );
    }
    case "capacidades": {
      const rows = await loadCapabilities();

      return rows ? (
        <Capabilities rows={rows} />
      ) : (
        <Unavailable title="O catálogo não pôde ser lido" />
      );
    }
    // A aba traz os três estados dela mesma — inclusive o 422 de uma janela
    // digitada à mão —, porque o seletor de semanas tem de continuar na tela
    // em todos: sem ele, quem errou a janela não tem como voltar.
    case "execucoes":
      return <Executions weeks={weeks} result={await loadExecutions(weeks)} />;
  }
}

function Unavailable({ title }: { title: string }) {
  return (
    <Card className="p-6">
      <EmptyState
        icon={BotOff}
        tone="neutral"
        title={title}
        description="Vem da API do painel, e ela não respondeu agora — ou o assistente está sem camada da plataforma publicada. Nada foi alterado."
      />
    </Card>
  );
}
