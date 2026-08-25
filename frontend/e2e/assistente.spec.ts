import { expect, test, type Page } from "@playwright/test";

/**
 * O assistente ponta a ponta. Precisa do Supabase local com o seed
 * (`supabase db reset`) e do env desse stack exportado — sem ele o login falha e
 * estes testes se pulam em vez de reportar quebra.
 *
 * O que só é provável aqui: que o SSE **atravessa**. Os testes de unidade do
 * backend leem o stream com o TestClient, que o entrega inteiro, e os do
 * frontend leem um `ReadableStream` montado à mão. Nenhum dos dois prova que
 * uvicorn, a rede e o `fetch` do navegador entregam quadro por quadro — e é
 * disso que a tela depende.
 *
 * O provider é o falso (`E2E_FAKE_LLM=1`, em playwright.config.ts): ele escolhe
 * do mesmo catálogo e passa pelo mesmo `choose`, então o número que aparece na
 * tela veio do banco através da RLS.
 */
const SEEDED =
  process.env.NEXT_PUBLIC_SUPABASE_URL?.includes("127.0.0.1") ?? false;

test.skip(!SEEDED, "requer o Supabase local com o seed de desenvolvimento");

async function signIn(page: Page) {
  await page.goto("/login?next=%2Fdashboard%2Fassistente");
  await page.getByLabel("E-mail").fill("owner@fastpark.dev");
  await page.getByLabel("Senha").fill("operax-dev");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("heading", { name: "Assistente" })).toBeVisible({
    timeout: 30_000,
  });
}

async function perguntar(page: Page, pergunta: string) {
  await page.getByLabel("Sua pergunta").fill(pergunta);
  await page.getByRole("button", { name: "Perguntar" }).click();
}

test("a pergunta volta com a métrica, o texto e o custo", async ({ page }) => {
  await signIn(page);

  await perguntar(page, "quantos desvios tivemos este mês?");

  // A métrica primeiro: é ela que deixa a pessoa conferir o recorte antes de
  // acreditar no número.
  await expect(page.getByText("Total de desvios no período")).toBeVisible({
    timeout: 30_000,
  });
  // O número sai de `fn_kpi_period`, atravessa a RLS e volta: o provider falso
  // monta a frase a partir do que a ferramenta devolveu, nunca de um texto fixo.
  await expect(page.getByText(/Foram \d+ desvios no período/)).toBeVisible();
  // Custo de tokens visível — critério de aceite do sprint.
  await expect(page.getByText(/tokens ·/)).toBeVisible();
});

test("a pergunta fora do catálogo recebe recusa, e não um número", async ({
  page,
}) => {
  await signIn(page);

  await perguntar(page, "quanto gastamos de folha em agosto?");

  await expect(
    page.getByText("Nenhuma métrica do catálogo responde sobre folha."),
  ).toBeVisible({ timeout: 30_000 });
  // Recusa é resposta: nenhum número, e nenhuma métrica anunciada.
  await expect(page.getByText("Total de desvios no período")).toHaveCount(0);
});
