import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  FORGOT_PASSWORD_ANSWER,
  ForgotPasswordForm,
} from "@/app/login/forgot-password-form";

const resetPasswordForEmail = vi.fn();
const api = { requestApi: vi.fn(), requestApiAsUser: vi.fn() };

vi.mock("@/lib/supabase", () => ({
  createBrowserSupabaseClient: () => ({ auth: { resetPasswordForEmail } }),
}));

// ⛔ O e-mail não vai ao backend do OperaX.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    requestApi: (...args: unknown[]) => api.requestApi(...args),
    requestApiAsUser: (...args: unknown[]) => api.requestApiAsUser(...args),
  };
});

async function pedir(email = "nina@fastpark.dev") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("E-mail"), email);
  await user.click(screen.getByRole("button", { name: "Enviar link" }));
}

beforeEach(() => {
  resetPasswordForEmail.mockReset();
  api.requestApi.mockReset();
  api.requestApiAsUser.mockReset();
});

describe("Esqueci minha senha", () => {
  it("chama `resetPasswordForEmail` com o `redirectTo` da origem do painel + /convite marcado como recuperação", async () => {
    resetPasswordForEmail.mockResolvedValue({ data: {}, error: null });
    render(<ForgotPasswordForm />);

    await pedir();

    expect(resetPasswordForEmail).toHaveBeenCalledWith("nina@fastpark.dev", {
      redirectTo: `${window.location.origin}/convite?fluxo=recuperacao`,
    });
    expect(api.requestApi).not.toHaveBeenCalled();
    expect(api.requestApiAsUser).not.toHaveBeenCalled();
  });

  it.each([
    [
      "sucesso",
      () => resetPasswordForEmail.mockResolvedValue({ data: {}, error: null }),
    ],
    [
      "e-mail inexistente (o Auth não diz)",
      () => resetPasswordForEmail.mockResolvedValue({ data: {}, error: null }),
    ],
    [
      "erro do Auth",
      () =>
        resetPasswordForEmail.mockResolvedValue({
          data: null,
          error: { code: "over_email_send_rate_limit", status: 429 },
        }),
    ],
    [
      "erro de rede",
      () => resetPasswordForEmail.mockRejectedValue(new TypeError("fetch")),
    ],
  ])("⛔ a resposta é a mesma: %s", async (_caso, arrange) => {
    arrange();
    render(<ForgotPasswordForm />);

    await pedir();

    expect(await screen.findByRole("status")).toHaveTextContent(
      FORGOT_PASSWORD_ANSWER,
    );
    expect(FORGOT_PASSWORD_ANSWER).toBe(
      "Se esse e-mail tiver conta, enviamos um link para definir uma nova senha.",
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("⛔ o botão fica desabilitado enquanto envia — um pedido só", async () => {
    let release: (value: unknown) => void = () => {};
    resetPasswordForEmail.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    const user = userEvent.setup();
    render(<ForgotPasswordForm />);

    await user.type(screen.getByLabelText("E-mail"), "nina@fastpark.dev");
    await user.click(screen.getByRole("button", { name: "Enviar link" }));

    const botao = await screen.findByRole("button", { name: /Enviando/ });
    expect(botao).toBeDisabled();
    await user.click(botao);
    expect(resetPasswordForEmail).toHaveBeenCalledTimes(1);

    release({ data: {}, error: null });
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        FORGOT_PASSWORD_ANSWER,
      ),
    );
  });

  it("e-mail inválido não chama o Auth", async () => {
    render(<ForgotPasswordForm />);

    await pedir("nao-e-email");

    expect(
      await screen.findByText("Informe um e-mail válido."),
    ).toBeInTheDocument();
    expect(resetPasswordForEmail).not.toHaveBeenCalled();
  });
});
