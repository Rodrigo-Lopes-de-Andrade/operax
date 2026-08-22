import { expect, test, type Page } from "@playwright/test";

/**
 * The two screens of the sprint that the database suite cannot reach: what a
 * unit supervisor sees on the monitor, and what the wall board never shows.
 *
 * Same requirement as gestao-de-ponto.spec.ts — the local Supabase stack with
 * the development seed. Without it the sign-in fails and these skip rather than
 * report as broken.
 */
const SEEDED =
  process.env.NEXT_PUBLIC_SUPABASE_URL?.includes("127.0.0.1") ?? false;

test.skip(!SEEDED, "requer o Supabase local com o seed de desenvolvimento");

async function signIn(
  page: Page,
  email: string,
  next: string,
  heading: string,
) {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha").fill("operax-dev");
  await page.getByRole("button", { name: "Entrar" }).click();
  // Generous for the same reason the dashboard suite is: the first hit compiles
  // the route in the dev server. The acceptance target is a production build.
  await expect(page.getByRole("heading", { name: heading })).toBeVisible({
    timeout: 30_000,
  });
}

test("o monitor separa escalado de sem indício, e diz que um não é presença", async ({
  page,
}) => {
  await signIn(
    page,
    "owner@fastpark.dev",
    "/dashboard/monitor",
    "Monitor diário",
  );

  await expect(page.getByText("Escalados hoje")).toBeVisible();
  await expect(
    page.getByRole("paragraph").filter({ hasText: /^Sem indício$/ }),
  ).toBeVisible();
  // A frase que separa "a leitura não encontrou nada" de "está todo mundo aqui".
  await expect(
    page.getByText("Não é confirmação de presença.", { exact: false }),
  ).toBeVisible();

  // A idade do dado é permanente no cabeçalho, como em toda tela do dia.
  await expect(page.getByText(/Dados de \d{2}:\d{2}/)).toBeVisible();

  await expect(
    page.getByRole("heading", { name: "Situação por unidade" }),
  ).toBeVisible();
});

test("o dia do monitor troca pelo link e volta na URL", async ({ page }) => {
  await signIn(
    page,
    "owner@fastpark.dev",
    "/dashboard/monitor",
    "Monitor diário",
  );

  await page.getByRole("link", { name: "Dia anterior" }).click();
  await expect(page).toHaveURL(/[?&]dia=\d{4}-\d{2}-\d{2}/);
  await expect(
    page.getByRole("link", { name: "Voltar para hoje" }),
  ).toBeVisible();

  // Adiante de hoje o controle não existe — não é um botão desabilitado.
  await page.getByRole("link", { name: "Voltar para hoje" }).click();
  await expect(page.getByRole("link", { name: "Próximo dia" })).toHaveCount(0);
});

test("o supervisor não alcança outra unidade no monitor", async ({ page }) => {
  await signIn(
    page,
    "supervisor@fastpark.dev",
    "/dashboard/monitor",
    "Monitor diário",
  );

  const unitSelect = page.getByLabel("Unidade");
  await expect(unitSelect.locator("option")).toHaveCount(2); // "Todas" + a dele
  await expect(unitSelect).toContainText("Shopping Norte");
  await expect(unitSelect).not.toContainText("Aeroporto");

  // E a tabela por unidade responde a mesma coisa: a RLS não devolve a outra.
  await expect(page.getByRole("cell", { name: "Aeroporto" })).toHaveCount(0);
});

test("o painel de TV não mostra o nome de ninguém", async ({ page }) => {
  await signIn(page, "owner@fastpark.dev", "/dashboard", "Gestão de ponto");

  // Os nomes proibidos são lidos da tela que pode mostrá-los, não fixados aqui:
  // quem tem indício muda a cada dia que o seed é carregado, e um teste com
  // nome fixo passaria amanhã sem ter verificado nada.
  const rows = page.getByRole("row");
  const sample = Math.min(await rows.count(), 4);
  const names: string[] = [];

  for (let index = 1; index < sample; index += 1) {
    const cell = await rows.nth(index).getByRole("cell").nth(1).innerText();
    const name = cell.split("\n")[0].trim();

    if (name) {
      names.push(name);
    }
  }

  expect(names.length).toBeGreaterThan(0);

  await page.goto("/tv");
  await expect(page.getByRole("heading", { name: "FastPark" })).toBeVisible();
  await expect(page.getByText("Ocorrências por unidade")).toBeVisible();
  await expect(page.getByText("Últimos 7 dias")).toBeVisible();

  // O critério de aceite do S5: nenhum nome de colaborador na tela de TV.
  for (const name of names) {
    await expect(page.locator("body")).not.toContainText(name);
  }
});

test("o painel de TV não oferece sair — ninguém está sentado nele", async ({
  page,
}) => {
  await signIn(page, "owner@fastpark.dev", "/tv", "FastPark");

  await expect(page.getByRole("button", { name: "Sair" })).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "Seções" })).toHaveCount(0);
});

test("o painel de TV exige sessão como qualquer outra tela", async ({
  browser,
}) => {
  const page = await browser.newPage({
    storageState: { cookies: [], origins: [] },
  });

  await page.goto("/tv");
  await expect(page).toHaveURL(/\/login\?next=%2Ftv/);

  await page.close();
});
