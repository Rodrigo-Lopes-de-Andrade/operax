import { expect, test, type Page } from "@playwright/test";

/**
 * A curadoria origem → unidade, na tela.
 *
 * Duas coisas só se provam aqui. A primeira é que "provisório" chega ao DOM
 * como estado próprio, e não somado ao validado — a conta certa dentro do JSON
 * não ajuda ninguém se a tela mostrar a barra cheia. A segunda é o papel:
 * curadoria é escrita, escrita é `util.is_admin`, e `executive` não está lá
 * dentro por mais que alcance a área de RH.
 *
 * Estes testes **não escrevem**. O lote e o Enter são exercitados em jsdom,
 * onde podem repetir; aqui gravar validaria o seed e o segundo `npx playwright
 * test` da mesma máquina veria uma tela diferente da do primeiro.
 *
 * Precisa do Supabase local com o seed de desenvolvimento — ver
 * playwright.config.ts.
 */
const SEEDED =
  process.env.NEXT_PUBLIC_SUPABASE_URL?.includes("127.0.0.1") ?? false;

test.skip(!SEEDED, "requer o Supabase local com o seed de desenvolvimento");

const MAPEAMENTO = "/dashboard/administracao/mapeamento";

async function signIn(page: Page, email: string, next: string) {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha").fill("operax-dev");
  await page.getByRole("button", { name: "Entrar" }).click();
}

test("o provisório aparece com nome próprio, e não dentro do validado", async ({
  page,
}) => {
  await signIn(page, "owner@fastpark.dev", MAPEAMENTO);
  await expect(
    page.getByRole("heading", { name: "Mapeamento de unidades" }),
  ).toBeVisible({ timeout: 30_000 });

  // O menu ofereceu a porta a quem escreve.
  await expect(page.getByRole("link", { name: "Mapeamento" })).toBeVisible();

  // O seed tem quatro mapas confirmados e dois que ninguém confirmou. `exact`
  // porque a busca de texto do Playwright ignora caixa: sem ele, o rótulo da
  // faixa e os dois selos são a mesma consulta.
  await expect(page.getByText("Provisório", { exact: true })).toBeVisible();
  await expect(page.getByText("provisório", { exact: true })).toHaveCount(2);

  // E a frase que impede a leitura errada da barra.
  await expect(
    page.getByText(/mapeamento que existe e ninguém confirmou/),
  ).toBeVisible();
});

test("a sugestão aparece com o tamanho do palpite ao lado", async ({
  page,
}) => {
  await signIn(page, "owner@fastpark.dev", MAPEAMENTO);
  await expect(
    page.getByRole("heading", { name: "Mapeamento de unidades" }),
  ).toBeVisible({ timeout: 30_000 });

  // "Operação Hospital" x unidade "Hospital": uma das duas palavras encontra
  // par, e o número diz exatamente isso. Um palpite sem número é um palpite
  // que se lê como fato.
  await expect(page.getByText(/Sugestão: Hospital · \d+%/)).toBeVisible();

  // O lote nomeia quantas linhas alcança antes de ser apertado.
  await expect(
    page.getByRole("button", { name: /Aplicar \d+ sugest/ }),
  ).toBeVisible();
});

test("quem não escreve não recebe a porta da curadoria", async ({ page }) => {
  // `executive` alcança a área de RH para ler e não é `util.is_admin`.
  await signIn(page, "supervisor@fastpark.dev", "/dashboard");
  await expect(
    page.getByRole("heading", { name: "Gestão de ponto" }),
  ).toBeVisible({
    timeout: 30_000,
  });

  await expect(page.getByRole("link", { name: "Mapeamento" })).toHaveCount(0);

  await page.goto(MAPEAMENTO);
  await expect(
    page.getByRole("heading", { name: "Mapeamento de unidades" }),
  ).toHaveCount(0);
});
