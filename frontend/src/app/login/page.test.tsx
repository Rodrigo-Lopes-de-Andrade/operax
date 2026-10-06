import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/login/page";

vi.mock("next/headers", () => ({
  headers: async () => new Headers({ host: "app.fastparks.com.br" }),
}));

vi.mock("./entry-canvas", () => ({ EntryCanvas: () => null }));
vi.mock("@/app/login/entry-canvas", () => ({ EntryCanvas: () => null }));
vi.mock("@/app/login/sign-in-form", () => ({
  SignInForm: () => <p>formulário de entrada</p>,
}));
vi.mock("@/app/login/forgot-password-form", () => ({
  ForgotPasswordForm: () => <p>formulário de esqueci</p>,
}));
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: ReactNode;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

async function abrir(params: Record<string, string> = {}) {
  render(await LoginPage({ searchParams: Promise.resolve(params) }));
}

describe("a tela de entrada", () => {
  it("oferece 'Esqueci minha senha', que leva a /login?esqueci", async () => {
    await abrir();

    expect(screen.getByText("formulário de entrada")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Esqueci minha senha" }),
    ).toHaveAttribute("href", "/login?esqueci");
  });

  it("`?esqueci` troca o formulário de entrada pelo de recuperação", async () => {
    await abrir({ esqueci: "" });

    expect(
      screen.getByRole("heading", { level: 1, name: "Esqueci minha senha" }),
    ).toBeInTheDocument();
    expect(screen.getByText("formulário de esqueci")).toBeInTheDocument();
    expect(screen.queryByText("formulário de entrada")).toBeNull();
  });
});
