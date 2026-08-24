import { expect, test, type Page } from "@playwright/test";

/**
 * O último critério de aceite do sprint do dashboard: "abre em menos de 3 s no
 * período padrão". Os outros três se provam na tela e vivem nos outros specs;
 * este é o único que é um número.
 *
 * Só roda com `E2E_PROD=1`, e a razão não é preferência: `next dev` compila a
 * rota na primeira requisição, então medir contra ele mede o compilador. Ver o
 * webServer em playwright.config.ts.
 *
 *     E2E_PROD=1 npx playwright test e2e/desempenho.spec.ts
 *
 * O QUE ESTE NÚMERO NÃO É: o número de produção. Aqui o Next e o Supabase estão
 * na mesma máquina, com o seed de desenvolvimento. Em produção há rede entre a
 * Vercel e o Supabase gerenciado, e o volume é outro. O que este teste protege é
 * o piso — uma regressão de renderização ou uma consulta que passou a varrer
 * aparece aqui. O teto continua sendo medido em homologação (S8).
 *
 * Medido em 24/08/2026, cinco execuções: 979, 1001, 1024, 1437 e 1516 ms.
 */
const SEEDED =
  process.env.NEXT_PUBLIC_SUPABASE_URL?.includes("127.0.0.1") ?? false;

test.skip(
  !process.env.E2E_PROD,
  "mede-se contra build de produção (E2E_PROD=1)",
);
test.skip(!SEEDED, "requer o Supabase local com o seed de desenvolvimento");

const ORCAMENTO_MS = 3_000;

async function signIn(page: Page) {
  await page.goto("/login?next=%2Fdashboard");
  await page.getByLabel("E-mail").fill("owner@fastpark.dev");
  await page.getByLabel("Senha").fill("operax-dev");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(
    page.getByRole("heading", { name: "Gestão de ponto" }),
  ).toBeVisible({ timeout: 30_000 });
}

test("o dashboard abre dentro do orçamento no período padrão", async ({
  page,
}) => {
  // O login vem antes da medição e fora dela: o critério é sobre o dashboard
  // abrir, não sobre autenticar. Ele também aquece o servidor, que é o estado
  // em que um usuário de verdade encontra a Vercel.
  await signIn(page);

  // Sem query string — é o que "período padrão" quer dizer, e é o recorte do
  // owner, o mais caro do seed: tenant inteiro.
  const inicio = Date.now();
  await page.goto("/dashboard");
  await expect(page.getByText("Ocorrências no recorte")).toBeVisible();
  await expect(
    page.getByText("Minutos de desvio", { exact: true }),
  ).toBeVisible();
  // A tabela é o que o gestor veio ler; sem ela a tela está "aberta" e vazia.
  await expect(page.getByRole("row").nth(1)).toBeVisible();
  const decorrido = Date.now() - inicio;

  // Um orçamento cujo número não se lê vale metade: quem rodar precisa saber se
  // passou com folga ou raspando.
  const nota = `abertura do dashboard: ${decorrido} ms (orçamento ${ORCAMENTO_MS} ms)`;
  test.info().annotations.push({ type: "desempenho", description: nota });
  console.log(nota);
  expect(decorrido).toBeLessThan(ORCAMENTO_MS);
});
