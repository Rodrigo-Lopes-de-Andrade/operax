import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SignInForm } from "@/app/login/sign-in-form";

const mocks = vi.hoisted(() => ({
  signInWithPassword: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
  clientThrows: false,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }),
}));

vi.mock("@/lib/supabase", () => ({
  createBrowserSupabaseClient: () => {
    if (mocks.clientThrows) {
      throw new Error("Missing or invalid frontend environment");
    }

    return { auth: { signInWithPassword: mocks.signInWithPassword } };
  },
}));

afterEach(() => {
  vi.clearAllMocks();
  mocks.clientThrows = false;
});

describe("SignInForm", () => {
  it("refuses an invalid e-mail without asking Supabase", async () => {
    const user = userEvent.setup();
    render(<SignInForm next="/dashboard" />);

    await user.type(screen.getByLabelText("E-mail"), "nao-e-email");
    await user.type(screen.getByLabelText("Senha"), "segredo");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByText("Informe um e-mail válido.")).toBeVisible();
    expect(mocks.signInWithPassword).not.toHaveBeenCalled();
  });

  it("shows a single message when the credentials are wrong", async () => {
    mocks.signInWithPassword.mockResolvedValue({
      error: { code: "invalid_credentials", message: "Invalid login" },
    });
    const user = userEvent.setup();
    render(<SignInForm next="/dashboard" />);

    await user.type(screen.getByLabelText("E-mail"), "gestor@kastro.test");
    await user.type(screen.getByLabelText("Senha"), "errada");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("E-mail ou senha inválidos.");
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it("returns to the screen the link pointed at once signed in", async () => {
    mocks.signInWithPassword.mockResolvedValue({ error: null });
    const user = userEvent.setup();
    render(<SignInForm next="/dashboard?ev=4821" />);

    await user.type(screen.getByLabelText("E-mail"), "gestor@kastro.test");
    await user.type(screen.getByLabelText("Senha"), "correta");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(mocks.signInWithPassword).toHaveBeenCalledWith({
      email: "gestor@kastro.test",
      password: "correta",
    });
    expect(mocks.replace).toHaveBeenCalledWith("/dashboard?ev=4821");
    // The server re-decides what this session may see.
    expect(mocks.refresh).toHaveBeenCalled();
  });

  it("says something when the client cannot even be built", async () => {
    // Missing configuration throws before any request. Without the catch the
    // spinner would stop and the screen would stay silent.
    mocks.clientThrows = true;
    vi.spyOn(console, "error").mockImplementation(() => {});
    const user = userEvent.setup();
    render(<SignInForm next="/dashboard" />);

    await user.type(screen.getByLabelText("E-mail"), "gestor@kastro.test");
    await user.type(screen.getByLabelText("Senha"), "correta");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível entrar agora. Tente de novo.",
    );
    expect(mocks.replace).not.toHaveBeenCalled();
  });
});
