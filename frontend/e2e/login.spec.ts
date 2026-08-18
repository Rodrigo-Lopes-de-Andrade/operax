import { expect, test } from "@playwright/test";

test("sends an anonymous visitor from the dashboard to the login", async ({
  page,
}) => {
  await page.goto("/dashboard");

  await expect(page).toHaveURL(/\/login\?next=%2Fdashboard/);
  await expect(
    page.getByRole("heading", { name: "Entrar", level: 1 }),
  ).toBeVisible();
});

test("keeps the occurrence link and refuses empty credentials", async ({
  page,
}) => {
  await page.goto("/login?next=%2Fdashboard%3Fev%3D4821");

  // Pre-session surface: the notice mentions the link, never the employee.
  await expect(
    page.getByText("Você abriu um link de ocorrência."),
  ).toBeVisible();

  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByText("Informe um e-mail válido.")).toBeVisible();
});
