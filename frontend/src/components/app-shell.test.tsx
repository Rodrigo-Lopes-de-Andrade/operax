import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/app-shell";
import { isAdmin, reachesComplianceReports, reachesHr } from "@/lib/identity";

// `@/lib/identity` explode num bundle de cliente de propósito; aqui os dois
// predicados são exercitados fora do Next, e é deles que a sidebar depende.
vi.mock("server-only", () => ({}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard/ponto",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

// A pílula de frescor é Server Component assíncrono e o crachá lê o contexto de
// sessão. Os dois têm responsabilidade própria, e nenhuma delas é a navegação.
vi.mock("@/components/data-freshness", () => ({
  DataFreshness: () => <span>frescor</span>,
}));

vi.mock("@/components/user-badge", () => ({
  UserBadge: () => <span>crachá</span>,
}));

/**
 * A sidebar como o papel a recebe.
 *
 * Os dois predicados são os reais, e é isso que faz o teste falar de papel em
 * vez de booleano: `showAdmin`/`showAdminWrites` são a fiação de
 * `app/dashboard/layout.tsx`, e o defeito que este ciclo consertou estava
 * exatamente na escolha de qual lista alimenta qual.
 */
function comPapel(role: string) {
  return render(
    <AppShell
      showAdmin={reachesHr(role)}
      showAdminWrites={isAdmin(role)}
      showComplianceReports={reachesComplianceReports(role)}
    >
      <p>conteúdo</p>
    </AppShell>,
  );
}

function administracao() {
  return screen.getByRole("navigation", { name: "Administração" });
}

describe("a sidebar não oferece porta que não abre", () => {
  it("`owner` recebe as doze: cinco de leitura e sete de escrita", () => {
    comPapel("owner");

    const admin = administracao();
    for (const item of [
      "Colaboradores",
      "Importação",
      "Quadro de Postos",
      "Laudos",
      "Benefícios",
      "Folha",
      "Mapeamento",
      "Rubricas",
      "Escalas",
      "Conexões",
      "Templates",
      // O rótulo carrega o parêntese: o "Assistente" da Operação é a
      // conversa, e este é a configuração dela.
      "Assistente (configuração)",
    ]) {
      expect(within(admin).getByRole("link", { name: item })).toBeVisible();
    }
  });

  it("⛔ `executive` lê a área de RH e não escreve nela", () => {
    // `HR_ROLES` o inclui, `ADMIN_ROLES` não. As páginas de escrita respondem
    // 404 para ele, e um link que leva a 404 é pior do que link nenhum.
    comPapel("executive");

    const admin = administracao();
    // ✅ O positivo ao lado: sem ele, as três ausências passariam num bloco
    // Administração que simplesmente não foi renderizado.
    expect(
      within(admin).getByRole("link", { name: "Colaboradores" }),
    ).toBeVisible();
    expect(
      within(admin).getByRole("link", { name: "Benefícios" }),
    ).toBeVisible();
    expect(within(admin).getByRole("link", { name: "Laudos" })).toBeVisible();

    expect(within(admin).queryByRole("link", { name: "Folha" })).toBeNull();
    expect(
      within(admin).queryByRole("link", { name: "Mapeamento" }),
    ).toBeNull();
    expect(within(admin).queryByRole("link", { name: "Rubricas" })).toBeNull();
    expect(within(admin).queryByRole("link", { name: "Escalas" })).toBeNull();
    // Conexões é configuração de canal, e a página fecha por `isAdmin`: o
    // item fora de `showAdminWrites` seria um link que leva a 404 para ele.
    expect(within(admin).queryByRole("link", { name: "Conexões" })).toBeNull();
    // Templates é a ação ligada a Conexões, e fecha pela mesma guarda.
    expect(within(admin).queryByRole("link", { name: "Templates" })).toBeNull();
    // A configuração do assistente também: publicar prompt, restaurar versão e
    // ligar métrica são escrita, e a página fecha por `isAdmin`.
    expect(
      within(admin).queryByRole("link", { name: "Assistente (configuração)" }),
    ).toBeNull();
  });

  it("⛔ `hr` é admin e escreve — o eixo de escrita não é o domínio sensível", () => {
    // O par de `accounting`, e ele importa: `hr` **não** alcança
    // `compensation` (403 medido em `/dp/ciclos`) e mesmo assim escreve
    // curadoria e folha. Trocar `isAdmin` por qualquer lista derivada de
    // domínio o deixaria sem Folha.
    comPapel("hr");

    const admin = administracao();
    expect(within(admin).getByRole("link", { name: "Folha" })).toBeVisible();
    expect(
      within(admin).getByRole("link", { name: "Mapeamento" }),
    ).toBeVisible();
    // Rubricas também: a página abre para ele, e é a API que responde 403 com
    // a frase escrita para ele. Esconder o item aqui seria a matriz de
    // domínios copiada para a sidebar.
    expect(within(admin).getByRole("link", { name: "Rubricas" })).toBeVisible();
  });

  it("⛔ `personnel` está nas DUAS listas — lê a área de RH e escreve nela", () => {
    // Ele é o DP, e é o papel que mais usa estas telas. Sem este caso ele podia
    // cair de `HR_ROLES` (perdendo o bloco inteiro) ou de `ADMIN_ROLES`
    // (perdendo os três de escrita) sem um teste vermelho: `owner` cobre as
    // duas listas ao mesmo tempo e não separa quem está em qual.
    comPapel("personnel");

    const admin = administracao();
    expect(
      within(admin).getByRole("link", { name: "Colaboradores" }),
    ).toBeVisible();
    expect(within(admin).getByRole("link", { name: "Folha" })).toBeVisible();
    expect(
      within(admin).getByRole("link", { name: "Mapeamento" }),
    ).toBeVisible();
    expect(within(admin).getByRole("link", { name: "Escalas" })).toBeVisible();
    expect(within(admin).getByRole("link", { name: "Conexões" })).toBeVisible();
  });

  it("✅ `unit_supervisor` tem Laudos, e só Laudos", () => {
    // A porta da persona a quem a página foi deliberadamente aberta: a view
    // recorta por `util.can_see_unit` e a rota não checa domínio, então ele lê
    // os laudos da unidade dele. Enquanto o item viveu dentro de `showAdmin`
    // (= `reachesHr`, que não o inclui), a única porta era digitar a URL.
    comPapel("unit_supervisor");

    const admin = administracao();
    expect(within(admin).getByRole("link", { name: "Laudos" })).toBeVisible();

    // ⛔ E nada além disso: ele não alcança a área de RH.
    for (const item of [
      "Colaboradores",
      "Importação",
      "Quadro de Postos",
      "Benefícios",
      "Folha",
      "Mapeamento",
      "Rubricas",
      "Escalas",
      "Conexões",
      "Templates",
      "Assistente (configuração)",
    ]) {
      expect(within(admin).queryByRole("link", { name: item })).toBeNull();
    }
  });

  it.each(["regional_manager", "operations_manager"])(
    "✅ `%s` também tem Laudos, e só Laudos",
    (papel) => {
      // Os outros dois papéis de operação de unidade. `util.can_see_unit` os
      // libera pela linha de `app.user_scope`, igual ao supervisor — deixá-los
      // de fora repetiria calado o mesmo defeito: porta aberta pelo banco e
      // nenhum link para ela.
      comPapel(papel);

      const admin = administracao();
      expect(within(admin).getByRole("link", { name: "Laudos" })).toBeVisible();
      expect(
        within(admin).queryByRole("link", { name: "Colaboradores" }),
      ).toBeNull();
    },
  );

  it("⛔ `accounting` não tem bloco Administração, e o Painel de DP é a porta dele", () => {
    // Ele confere a remessa: tem `compensation` e `banking`, e não está em
    // `HR_ROLES`. Era assim que ele ficava sem porta nenhuma — o link do ciclo
    // saiu daqui e passou a viver dentro do painel, que pergunta o domínio ao
    // backend antes de oferecer.
    comPapel("accounting");

    expect(
      screen.queryByRole("navigation", { name: "Administração" }),
    ).toBeNull();
    expect(screen.queryByRole("link", { name: "Conexões" })).toBeNull();
    expect(
      within(
        screen.getByRole("navigation", { name: "Departamento pessoal" }),
      ).getByRole("link", { name: "Painel de DP" }),
    ).toBeVisible();
  });

  it("`viewer` fica com a Operação e o Painel de DP, e com mais nada", () => {
    comPapel("viewer");

    expect(
      screen.getByRole("navigation", { name: "Departamento pessoal" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("navigation", { name: "Administração" }),
    ).toBeNull();
    expect(screen.getByRole("link", { name: "Gestão de ponto" })).toBeVisible();
  });

  it("⛔ 'Ciclo mensal' não é item de menu para ninguém", () => {
    // `owner` é o caso mais permissivo da sidebar — ela só acrescenta itens,
    // nunca troca. Ausente para ele é ausente para todos.
    // O eixo do ciclo é o domínio `compensation`, que não chega ao frontend:
    // `hr` é admin e não o tem, `accounting` o tem sem ser admin. Nenhuma lista
    // de papéis deste arquivo acerta os dois.
    comPapel("owner");

    expect(screen.queryByRole("link", { name: "Ciclo mensal" })).toBeNull();
    expect(screen.queryByText(/ciclo/i)).toBeNull();
  });

  it("o conteúdo da página fica dentro do `main`", () => {
    comPapel("viewer");

    expect(
      within(screen.getByRole("main")).getByText("conteúdo"),
    ).toBeVisible();
  });
});
