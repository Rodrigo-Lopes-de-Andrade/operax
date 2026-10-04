import Link from "next/link";
import type { ReactNode } from "react";

import { Brand } from "@/components/brand";
import { DataFreshness } from "@/components/data-freshness";
import { NavLink } from "@/components/nav-link";
import { SignOutButton } from "@/components/sign-out-button";
import { UserBadge } from "@/components/user-badge";
import {
  ASSISTENTE_CONFIG_LABEL,
  ASSISTENTE_CONFIG_PATH,
  ASSISTENTE_PATH,
} from "@/lib/assistente/url";
import {
  CONEXOES_PATH,
  DESTINATARIOS_PATH,
  REGRAS_PATH,
  TEMPLATES_PATH,
} from "@/lib/canais/url";
import { APROVACAO_PATH, LANCAMENTO_PATH } from "@/lib/alcada/url";
import { JUSTIFICATIVAS_PATH } from "@/lib/justificativas/url";
import { MONITOR_PATH } from "@/lib/monitor/url";
import { PONTO_PATH } from "@/lib/ponto/url";
import { MAPEAMENTO_PATH, ROTACOES_PATH } from "@/lib/curadoria/url";
import {
  BENEFICIOS_PATH,
  CURADORIA_JUSTIFICATIVAS_PATH,
  LAUDOS_PATH,
  PAINEL_PATH,
  POSTOS_PATH,
  RUBRICAS_PATH,
} from "@/lib/dp/url";
import { FOLHA_PATH } from "@/lib/folha/url";
import { COLABORADORES_PATH, IMPORTACAO_PATH } from "@/lib/rh/url";
import { TV_PATH } from "@/lib/tv/url";

/**
 * Authenticated chrome: a 264px navy sidebar and an 84px header carrying the
 * permanent data-age pill.
 *
 * The navigation lists only what exists. The individual consultation is reached
 * from a row, not from here, because it is always about somebody you were
 * already looking at. Alert rules arrive with their own screen — a nav item that
 * leads nowhere reads as a defect, and a disabled one without a reason reads
 * worse.
 *
 * The administration section follows the same rule one step further: it is
 * absent, not disabled, for a role that does not reach it. The role comes from
 * the backend (`/me`), and hiding the link is not the boundary — the pages fail
 * closed on a typed URL and the API refuses every write. It is about not
 * offering a door that will not open.
 */
export function AppShell({
  children,
  showAdmin = false,
  showAdminWrites = false,
  showComplianceReports = false,
  showApprovals = false,
}: {
  children: ReactNode;
  showAdmin?: boolean;
  /**
   * Os itens que só escrevem — curadoria e folha. Escrita é `util.is_admin`, que
   * não inclui `executive`: ele alcança a área de RH para ler, não cura nada e
   * não publica folha. Então o item não aparece para ele: a página responde 404,
   * e um link que leva a 404 é pior do que link nenhum. Conexões entra aqui
   * pelo mesmo motivo: é configuração de canal, e a escrita de credencial que
   * a próxima etapa põe nela é de administrador — a página fecha por `isAdmin`.
   *
   * ⛔ O CICLO MENSAL SAIU DAQUI, e o motivo é que o eixo dele não é este.
   * Entrar na tela de ciclo exige o domínio `compensation` — que `hr` é admin e
   * **não** tem, e que `accounting` tem **sem** ser admin. Nenhuma lista de
   * papéis deste arquivo acerta os dois, e a matriz de domínios não chega ao
   * frontend (`/me` devolve só o papel). O link passou a viver dentro do Painel
   * de DP, que já perguntou o domínio ao backend e só o oferece quando a
   * resposta foi sim.
   */
  showAdminWrites?: boolean;
  /**
   * Laudos, e só ele — o eixo desta tela não é a área de RH.
   *
   * A view recorta por `util.can_see_unit` e a rota não checa domínio: o
   * supervisor de unidade lê os laudos da unidade dele. Ele não está em
   * `HR_ROLES`, então herdar `showAdmin` deixava a persona a que a página foi
   * aberta sem porta nenhuma — só URL digitada. Aqui a condição é própria
   * (`reachesComplianceReports`), e por isso o bloco Administração pode existir
   * com este item sozinho.
   */
  showComplianceReports?: boolean;
  /**
   * Aprovação de justificativas e Lançamento no Secullum — `hr` e `owner`, e
   * mais ninguém
   * (`reviewsJustifications`). O eixo é a alçada, não `util.is_admin`:
   * `personnel` escreve na Administração e não revisa justificativa.
   */
  showApprovals?: boolean;
}) {
  return (
    <div className="bg-canvas flex min-h-dvh">
      <aside className="bg-chrome hidden w-[var(--sidebar-width)] shrink-0 flex-col lg:flex">
        <div className="flex h-[var(--header-height)] items-center px-6">
          <Link href={PONTO_PATH}>
            <Brand />
          </Link>
        </div>

        <nav aria-label="Seções" className="flex flex-col gap-1 px-4 py-2">
          <p className="text-2xs px-3 py-2 font-bold tracking-[0.08em] text-white/80 uppercase">
            Operação
          </p>
          <NavLink href={PONTO_PATH} label="Gestão de ponto" />
          <NavLink href={MONITOR_PATH} label="Monitor diário" />
          <NavLink href={JUSTIFICATIVAS_PATH} label="Justificativas" />
          {showApprovals ? (
            <>
              <NavLink
                href={APROVACAO_PATH}
                label="Aprovação de justificativas"
              />
              <NavLink href={LANCAMENTO_PATH} label="Lançamento no Secullum" />
            </>
          ) : null}
          <NavLink href={TV_PATH} label="Painel de TV" />
          <NavLink href={ASSISTENTE_PATH} label="Assistente" />
        </nav>

        {/*
          ⛔ SEM PAPEL NENHUM DECIDINDO, E É A ÚNICA FORMA HONESTA
          O painel de DP abre para qualquer membro do tenant: quem alcança o
          domínio de remuneração recebe os nove KPIs, e quem não alcança recebe
          os oito contadores do cadastro recortados pela RLS — que é a tela
          inteira de quem cuida de documento, ASO e férias.

          ⚠️ Isso não é o mesmo que "nenhum papel vê nada": medido, `viewer`
          recebe 403 nos KPIs e oito contadores em zero. O zero não é desta
          tela — ele não tem linha em `app.user_scope` e fica vazio em todas as
          telas do produto. Esconder o item resolveria a aparência de uma conta
          por configurar, e não a conta.

          A alternativa seria uma lista de papéis, e ela erraria: `accounting`
          tem `compensation` e não está em `HR_ROLES`, então não veria o bloco
          Administração inteiro — e era assim que ele ficava sem porta.
        */}
        <nav
          aria-label="Departamento pessoal"
          className="flex flex-col gap-1 px-4 py-2"
        >
          <p className="text-2xs px-3 py-2 font-bold tracking-[0.08em] text-white/80 uppercase">
            Departamento pessoal
          </p>
          <NavLink href={PAINEL_PATH} label="Painel de DP" />
        </nav>

        {showAdmin || showComplianceReports ? (
          <nav
            aria-label="Administração"
            className="flex flex-col gap-1 px-4 py-2"
          >
            <p className="text-2xs px-3 py-2 font-bold tracking-[0.08em] text-white/80 uppercase">
              Administração
            </p>
            {showAdmin ? (
              <>
                <NavLink href={COLABORADORES_PATH} label="Colaboradores" />
                <NavLink href={IMPORTACAO_PATH} label="Importação" />
                <NavLink href={POSTOS_PATH} label="Quadro de Postos" />
              </>
            ) : null}
            {/*
              A condição é própria: `unit_supervisor` não está em `HR_ROLES` e
              esta é a tela dele. O bloco existe para ele com um item só, e é
              melhor do que um bloco a mais na navegação de quem não abre nada.
            */}
            {showComplianceReports ? (
              <NavLink href={LAUDOS_PATH} label="Laudos" />
            ) : null}
            {showAdmin ? (
              <NavLink href={BENEFICIOS_PATH} label="Benefícios" />
            ) : null}
            {showAdminWrites ? (
              <>
                <NavLink href={FOLHA_PATH} label="Folha" />
                <NavLink href={MAPEAMENTO_PATH} label="Mapeamento" />
                <NavLink href={RUBRICAS_PATH} label="Rubricas" />
                <NavLink href={ROTACOES_PATH} label="Escalas" />
                {/*
                  ⚠️ O RÓTULO CARREGA "DE AFASTAMENTO", E ISSO NÃO É VERBOSIDADE
                  A Operação já tem "Justificativas": lá o gestor explica o
                  indício de uma pessoa num dia, aqui a string do Secullum ganha
                  categoria de domínio para todos os afastamentos que a carregam.
                  Os dois nomes colidem no vocabulário do cliente, e dois itens
                  de menu com o mesmo rótulo levariam a telas de papéis
                  diferentes.

                  O item vive na Administração e não no bloco de DP: o eixo dele
                  é `util.is_admin` — exatamente `showAdminWrites` —, e o bloco de
                  DP não tem condição de papel nenhuma, de propósito.
                */}
                <NavLink
                  href={CURADORIA_JUSTIFICATIVAS_PATH}
                  label="Justificativas de afastamento"
                />
                <NavLink href={CONEXOES_PATH} label="Conexões" />
                <NavLink href={TEMPLATES_PATH} label="Templates" />
                <NavLink href={DESTINATARIOS_PATH} label="Destinatários" />
                <NavLink href={REGRAS_PATH} label="Regras" />
                <NavLink
                  href={ASSISTENTE_CONFIG_PATH}
                  label={ASSISTENTE_CONFIG_LABEL}
                />
              </>
            ) : null}
          </nav>
        ) : null}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="bg-chrome flex h-[var(--header-height)] items-center justify-between gap-4 px-6">
          <Link href={PONTO_PATH} className="lg:hidden">
            <Brand />
          </Link>
          <DataFreshness />
          <div className="flex items-center gap-4">
            <UserBadge />
            <SignOutButton />
          </div>
        </header>

        <main className="mx-auto w-full max-w-[var(--content-max)] flex-1 px-6 py-6">
          {children}
        </main>
      </div>
    </div>
  );
}
