import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/app-shell";
import { isAdmin, reachesHr } from "@/lib/identity";

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
    <AppShell showAdmin={reachesHr(role)} showAdminWrites={isAdmin(role)}>
      <p>conteúdo</p>
    </AppShell>,
  );
}

function administracao() {
  return screen.getByRole("navigation", { name: "Administração" });
}

describe("a sidebar não oferece porta que não abre", () => {
  it("`owner` recebe as sete: quatro de leitura e três de escrita", () => {
    comPapel("owner");

    const admin = administracao();
    for (const item of [
      "Colaboradores",
      "Importação",
      "Quadro de Postos",
      "Benefícios",
      "Folha",
      "Mapeamento",
      "Escalas",
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

    expect(within(admin).queryByRole("link", { name: "Folha" })).toBeNull();
    expect(
      within(admin).queryByRole("link", { name: "Mapeamento" }),
    ).toBeNull();
    expect(within(admin).queryByRole("link", { name: "Escalas" })).toBeNull();
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
  });

  it("⛔ `accounting` não tem bloco Administração, e o Painel de DP é a porta dele", () => {
    // Ele confere a remessa: tem `compensation` e `banking`, e não está em
    // `HR_ROLES`. Era assim que ele ficava sem porta nenhuma — o link do ciclo
    // saiu daqui e passou a viver dentro do painel, que pergunta o domínio ao
    // backend antes de oferecer.
    comPapel("accounting");

    expect(
      screen.queryByRole("navigation", { name: "Administração" }),
    ).toBeNull();
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
