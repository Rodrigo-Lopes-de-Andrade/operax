import { expect, test, type Page } from "@playwright/test";

/**
 * Needs the local Supabase stack with the development seed
 * (`supabase db reset`, which loads `supabase/seed.sql`) and the env of that
 * stack exported — see playwright.config.ts. Without it the sign-in fails and
 * these tests are skipped rather than reported as broken.
 *
 * What they prove is the acceptance criterion of the dashboard sprint that the
 * database suite cannot: that a unit supervisor sees one unit *on the screen*,
 * not merely in a policy.
 */
const SEEDED =
  process.env.NEXT_PUBLIC_SUPABASE_URL?.includes("127.0.0.1") ?? false;

test.skip(!SEEDED, "requer o Supabase local com o seed de desenvolvimento");

async function signIn(page: Page, email: string, next = "/dashboard") {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha").fill("operax-dev");
  await page.getByRole("button", { name: "Entrar" }).click();
  // Generous, and only here: the first hit compiles the route in the dev server
  // and the owner's cut is the whole tenant, so the slowest sign-in of the suite
  // is the first one. The 3-second acceptance target is measured against a
  // production build, not against this.
  await expect(
    page.getByRole("heading", { name: "Gestão de ponto" }),
  ).toBeVisible({ timeout: 30_000 });
}

/**
 * Abre a ficha do colaborador a partir da primeira ocorrência da lista.
 *
 * O `waitForURL` não é cautela: a gaveta é renderizada pelo servidor a partir de
 * `?ev=`, e o App Router **pinta a rota nova antes de confirmar a transição**.
 * Existe uma janela em que o link "Ver o colaborador" já está na tela e a URL
 * ainda é `/dashboard` — clicar nela dispara a segunda navegação, a primeira
 * confirma depois e ganha, e o navegador termina em `/dashboard?ev=…` com a
 * ficha nunca aberta. Sob carga a janela cresce, e era o que fazia estes dois
 * testes falharem só na suíte completa.
 *
 * Depois disso a âncora é o bloco de ponto, que existe para todo papel que
 * alcança a pessoa: esperar por ele separa "a ficha ainda não chegou" de "este
 * papel não vê remuneração", que é a distinção que estes dois testes provam.
 */
async function abrirFicha(page: Page) {
  await page.getByRole("row").nth(1).click();
  await page.waitForURL(/[?&]ev=/);
  await page.getByRole("link", { name: "Ver o colaborador" }).click();
  await expect(page.getByText("Dia a dia do período")).toBeVisible();
}

test("o owner vê o recorte inteiro e abre o indício pelo link", async ({
  page,
}) => {
  await signIn(page, "owner@fastpark.dev");

  await expect(page.getByText("Ocorrências no recorte")).toBeVisible();
  await expect(
    page.getByText("Minutos de desvio", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByText("Registro oficial de jornada permanece no Secullum.", {
        exact: false,
      })
      .first(),
  ).toBeVisible();

  // A idade do dado é permanente no cabeçalho, não um tooltip.
  await expect(page.getByText(/Dados de \d{2}:\d{2}/)).toBeVisible();

  // Clicar numa linha leva o recorte para a URL e abre a gaveta.
  await page.getByRole("row").nth(1).click();
  await expect(page).toHaveURL(/[?&]ev=/);
  await expect(page.getByRole("dialog")).toBeVisible();

  // Esc fecha, e fechar é voltar para o mesmo recorte sem a ocorrência.
  await page.keyboard.press("Escape");
  await expect(page).not.toHaveURL(/[?&]ev=/);
});

test("o período troca pelo link e o recorte aparece na URL", async ({
  page,
}) => {
  await signIn(page, "owner@fastpark.dev");

  await page
    .getByRole("group", { name: "Período" })
    .getByRole("link", { name: "Hoje" })
    .click();
  await expect(page).toHaveURL(/[?&]per=hoje/);
});

test("o supervisor de unidade não vê outra unidade na tela", async ({
  page,
}) => {
  await signIn(page, "supervisor@fastpark.dev");

  // O escopo do seed dá a ele Shopping Norte e mais nenhuma.
  const unitSelect = page.getByLabel("Unidade");
  await expect(unitSelect.locator("option")).toHaveCount(2); // "Todas" + a dele
  await expect(unitSelect).toContainText("Shopping Norte");
  await expect(unitSelect).not.toContainText("Aeroporto");

  // E o link de outra unidade não vira dado: a RLS não devolve linha nenhuma.
  await page.goto("/dashboard?un=dev-aero");
  await expect(
    page.getByText('Unidade "dev-aero" não encontrada'),
  ).toBeVisible();
});

test("o link da ocorrência de outro escopo não vaza o colaborador", async ({
  page,
}) => {
  await signIn(page, "supervisor@fastpark.dev");

  // Um uuid válido que o supervisor não pode ler: a gaveta explica, não mostra.
  await page.goto("/dashboard?ev=00000000-0000-4000-8000-000000000000");
  await expect(page.getByText("Este indício não existe mais")).toBeVisible();
});

test("o DP alcança os blocos sensíveis do colaborador", async ({ page }) => {
  await signIn(page, "dp@fastpark.dev");
  await abrirFicha(page);

  await expect(
    page.getByRole("heading", { name: "Histórico de remuneração" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Documentos" })).toBeVisible();
  // Departamento pessoal não alcança o domínio de saúde: exame não existe aqui.
  await expect(page.getByText("Exame ocupacional guarda apenas")).toHaveCount(
    0,
  );
});

test("o supervisor não vê o bloco sensível — nem cadeado, nem cinza", async ({
  page,
}) => {
  await signIn(page, "supervisor@fastpark.dev");
  await abrirFicha(page);

  // O ponto do colaborador está lá; o domínio sensível simplesmente não existe.
  await expect(page.getByText("Histórico de remuneração")).toHaveCount(0);
  await expect(page.getByText("Domínio sensível")).toHaveCount(0);
  await expect(page.getByText(/cadeado|sem permissão|bloqueado/i)).toHaveCount(
    0,
  );
});

test("colaborador fora do escopo responde a mesma coisa que colaborador inexistente", async ({
  page,
}) => {
  await signIn(page, "supervisor@fastpark.dev");

  await page.goto(
    "/dashboard/colaborador/00000000-0000-4000-8000-000000000000",
  );
  await expect(page.getByText("Colaborador não encontrado")).toBeVisible();
});
