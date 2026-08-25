import { expect, test, type Page } from "@playwright/test";

/**
 * O gate do R3, na tela.
 *
 * O que a suíte de banco prova em SQL é que a policy filtra. O que só se prova
 * aqui é que a **ausência chega até o DOM**: uma aba de domínio que o papel não
 * alcança não pode existir como elemento desabilitado, nem com cadeado, nem com
 * um texto pedindo permissão — as três variantes contam que o dado existe.
 *
 * Precisa do Supabase local com o seed de desenvolvimento
 * (`supabase db reset`) e do env desse stack exportado — ver
 * playwright.config.ts. Sem isso o login falha e estes testes são pulados, em
 * vez de reportados como quebrados.
 */
const SEEDED =
  process.env.NEXT_PUBLIC_SUPABASE_URL?.includes("127.0.0.1") ?? false;

test.skip(!SEEDED, "requer o Supabase local com o seed de desenvolvimento");

const COLABORADORES = "/dashboard/administracao/colaboradores";

async function signIn(page: Page, email: string, next: string) {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha").fill("operax-dev");
  await page.getByRole("button", { name: "Entrar" }).click();
}

async function abrirPrimeiro(page: Page) {
  await expect(
    page.getByRole("heading", { name: "Colaboradores" }),
  ).toBeVisible({ timeout: 30_000 });
  await page.getByRole("row").nth(1).click();
  await expect(
    page.getByRole("navigation", { name: "Domínios do colaborador" }),
  ).toBeVisible();
}

test("o DP abre a lista ordenada por vencimento e chega no detalhe", async ({
  page,
}) => {
  await signIn(page, "dp@fastpark.dev", COLABORADORES);
  await abrirPrimeiro(page);

  // A aba de cadastro abre por padrão e mostra de onde cada valor do sync vem.
  await expect(page.getByText("Vem do sistema de ponto")).toBeVisible();
  await expect(
    page.getByText(/Secullum · leitura de \d{2}:\d{2}/),
  ).toBeVisible();
});

test("o domínio que o papel não alcança não vira aba: some do DOM", async ({
  page,
}) => {
  // `personnel` tem PII, remuneração e disciplinar — não tem saúde.
  await signIn(page, "dp@fastpark.dev", COLABORADORES);
  await abrirPrimeiro(page);

  const abas = page.getByRole("navigation", {
    name: "Domínios do colaborador",
  });

  await expect(abas.getByRole("link", { name: /Remuneração/ })).toBeVisible();
  await expect(
    abas.getByRole("link", { name: /Dados pessoais/ }),
  ).toBeVisible();
  // Ausente, não desabilitada: `count()` é zero, não "visível: false".
  await expect(abas.getByRole("link", { name: /ASO/ })).toHaveCount(0);
});

test("o owner alcança saúde, e a mesma tela ganha a aba", async ({ page }) => {
  await signIn(page, "owner@fastpark.dev", COLABORADORES);
  await abrirPrimeiro(page);

  const abas = page.getByRole("navigation", {
    name: "Domínios do colaborador",
  });
  await expect(abas.getByRole("link", { name: /ASO/ })).toBeVisible();

  await abas.getByRole("link", { name: /ASO/ }).click();
  // Regra 10 escrita na própria tela, não só na tabela.
  await expect(
    page.getByText(/Diagnóstico, CID e descrição de restrição/),
  ).toBeVisible();
});

test("quem lê e não escreve não recebe botão de editar", async ({ page }) => {
  // `executive` alcança remuneração e não é `util.is_admin`.
  await signIn(page, "diretoria@fastpark.dev", COLABORADORES);
  await abrirPrimeiro(page);

  await expect(
    page.getByRole("button", { name: "Salvar cadastro" }),
  ).toHaveCount(0);

  await page
    .getByRole("navigation", { name: "Domínios do colaborador" })
    .getByRole("link", { name: /Remuneração/ })
    .click();

  await expect(page.getByRole("button", { name: "Nova vigência" })).toHaveCount(
    0,
  );
});

test("o DP edita o cadastro e cria uma vigência de salário", async ({
  page,
}) => {
  await signIn(page, "dp@fastpark.dev", COLABORADORES);
  await abrirPrimeiro(page);

  const idRh = `E2E-${Date.now().toString().slice(-6)}`;
  await page.getByLabel("ID RH").fill(idRh);
  const gravacao = page.waitForResponse(
    (resposta) =>
      resposta.url().includes("/rh/employees/") &&
      resposta.request().method() === "PATCH",
  );
  await page.getByRole("button", { name: "Salvar cadastro" }).click();
  expect((await gravacao).status()).toBe(204);

  // E recarrega antes de conferir: o campo continuaria mostrando o que foi
  // digitado mesmo se a gravação tivesse falhado, e a asserção não valeria nada.
  await page.reload();
  await expect(page.getByLabel("ID RH")).toHaveValue(idRh, { timeout: 15_000 });

  await page
    .getByRole("navigation", { name: "Domínios do colaborador" })
    .getByRole("link", { name: /Remuneração/ })
    .click();

  // A data da faixa vigente é lida da própria linha do tempo, e a nova entra no
  // dia seguinte. É o que torna este teste repetível — a regra é "vigência nova
  // começa depois da vigente", então reusar uma data fixa funcionaria uma vez só
  // — e de quebra prova que a tela mostra desde quando a faixa aberta vale.
  const vigente = await page.getByRole("listitem").first().innerText();
  const desde = proximoDia(vigente);

  await page.getByRole("button", { name: "Nova vigência" }).click();

  // Sobrepor a faixa vigente é recusado com o motivo, não com "valor inválido".
  await page.getByLabel("Desde").fill(diaIso(vigente));
  await page.getByLabel("Salário").fill("4200");
  await page.getByRole("button", { name: "Registrar vigência" }).click();
  await expect(page.getByText(/revogue-a/)).toBeVisible();

  await page.getByLabel("Desde").fill(desde);
  await page.getByRole("button", { name: "Registrar vigência" }).click();

  const primeira = page.getByRole("listitem").first();
  await expect(primeira).toContainText("R$ 4.200,00", { timeout: 15_000 });
  await expect(primeira).toContainText("Vigente");
  await expect(primeira).toContainText("em vigor");
});

/** "R$ 1.900,00 26/09/2025 — em vigor · Admissão Vigente" -> "2025-09-26". */
function diaIso(linha: string): string {
  const achado = /(\d{2})\/(\d{2})\/(\d{4})/.exec(linha);
  if (!achado) {
    throw new Error(`sem data na faixa vigente: ${linha}`);
  }
  return `${achado[3]}-${achado[2]}-${achado[1]}`;
}

function proximoDia(linha: string): string {
  const data = new Date(`${diaIso(linha)}T00:00:00Z`);
  data.setUTCDate(data.getUTCDate() + 1);
  return data.toISOString().slice(0, 10);
}

test("o supervisor não alcança a administração, nem pelo menu nem pela URL", async ({
  page,
}) => {
  await signIn(page, "supervisor@fastpark.dev", "/dashboard");
  await expect(
    page.getByRole("heading", { name: "Gestão de ponto" }),
  ).toBeVisible({ timeout: 30_000 });

  // O menu não oferece a porta.
  await expect(
    page.getByRole("navigation", { name: "Administração" }),
  ).toHaveCount(0);

  // E digitar a URL também não abre: a página decide de novo, no servidor.
  await page.goto(COLABORADORES);
  await expect(
    page.getByRole("heading", { name: "Colaboradores" }),
  ).toHaveCount(0);
});

test("a importação vai do modelo à confirmação pela tela", async ({ page }) => {
  await signIn(page, "dp@fastpark.dev", "/dashboard/administracao/importacao");
  await expect(
    page.getByRole("heading", { name: "Importação", level: 1 }),
  ).toBeVisible({ timeout: 30_000 });

  await page.getByRole("button", { name: "Vínculo" }).click();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Baixar modelo" }).click();
  const arquivo = await (await download).path();
  expect(arquivo).toBeTruthy();

  // Sobe o modelo intocado: toda linha já diz o que o banco diz, então o
  // preview tem de fechar com zero a gravar e zero erro. É o caso que prova que
  // reenviar não reescreve ninguém.
  await page.getByLabel("Planilha preenchida").setInputFiles(arquivo!);
  await page.getByRole("button", { name: "Conferir sem gravar" }).click();

  await expect(page.getByText("Já estava assim")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("Nenhuma linha recusada.")).toBeVisible();
});

test("o filtro de pendência mostra o prazo daquela pendência, não o mais urgente", async ({
  page,
}) => {
  // Owner alcança saúde e PII: vê tanto o ASO (exame) quanto CNH (documento).
  await signIn(page, "owner@fastpark.dev", COLABORADORES);
  await expect(
    page.getByRole("heading", { name: "Colaboradores" }),
  ).toBeVisible({ timeout: 30_000 });

  // Escopo na tabela: o seletor de pendência também tem uma opção "ASO", e ela
  // não é uma linha.
  const prazos = page.getByRole("table");

  // Sem recorte, a coluna mostra o prazo mais urgente de cada pessoa, seja qual for.
  await expect(prazos.getByText("CNH", { exact: true }).first()).toBeVisible();

  await page.goto(`${COLABORADORES}?pd=aso`);
  await expect(
    page.getByRole("heading", { name: "Colaboradores" }),
  ).toBeVisible();

  // Recortado por ASO, nenhuma linha pode mostrar o prazo de outra coisa: quem
  // persegue ASO e lê "CNH · vence em 3 dias" tem de abrir a ficha para saber do
  // ASO — que é justamente o trabalho que esta coluna existe para poupar.
  await expect(prazos.getByText("CNH", { exact: true })).toHaveCount(0);
  await expect(prazos.getByText("ASO", { exact: true }).first()).toBeVisible();
});
