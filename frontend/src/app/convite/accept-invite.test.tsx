import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AcceptInvite } from "@/app/convite/accept-invite";

const auth = {
  setSession: vi.fn(),
  exchangeCodeForSession: vi.fn(),
  verifyOtp: vi.fn(),
  getUser: vi.fn(),
  updateUser: vi.fn(),
};
const replace = vi.fn();
const refresh = vi.fn();
const api = {
  requestApi: vi.fn(),
  requestApiAsUser: vi.fn(),
  uploadApiAsUser: vi.fn(),
  downloadApiAsUser: vi.fn(),
};

vi.mock("@/lib/supabase", () => ({
  createInviteSupabaseClient: () => ({ auth }),
  createBrowserSupabaseClient: () => ({ auth }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh, push: vi.fn() }),
}));

// ⛔ A senha não vai ao backend do OperaX: nenhum cliente da API é chamado.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    requestApi: (...args: unknown[]) => api.requestApi(...args),
    requestApiAsUser: (...args: unknown[]) => api.requestApiAsUser(...args),
    uploadApiAsUser: (...args: unknown[]) => api.uploadApiAsUser(...args),
    downloadApiAsUser: (...args: unknown[]) => api.downloadApiAsUser(...args),
  };
});

const CONVIDADA = { id: "u-1", email: "nina@fastpark.dev" };
const SENHA = "Senha-Bem-Longa-42";

function abrirEm(path: string) {
  window.history.replaceState(null, "", path);
  return render(<AcceptInvite />);
}

async function definirSenha(confirmacao = SENHA) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Nova senha"), SENHA);
  await user.type(screen.getByLabelText("Confirme a senha"), confirmacao);
  await user.click(
    screen.getByRole("button", { name: "Definir senha e entrar" }),
  );
}

beforeEach(() => {
  for (const fn of [...Object.values(auth), ...Object.values(api)]) {
    fn.mockReset();
  }
  replace.mockReset();
  refresh.mockReset();
  auth.setSession.mockResolvedValue({
    data: { user: CONVIDADA, session: {} },
    error: null,
  });
  auth.updateUser.mockResolvedValue({ data: { user: CONVIDADA }, error: null });
});

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("/convite — a sessão a partir do link", () => {
  it("fragmento `#access_token`: abre a sessão com os dois tokens e os tira da URL", async () => {
    abrirEm(
      "/convite#access_token=AT-123&refresh_token=RT-456&expires_in=3600&token_type=bearer&type=invite",
    );

    expect(await screen.findByLabelText("Nova senha")).toBeInTheDocument();
    expect(auth.setSession).toHaveBeenCalledWith({
      access_token: "AT-123",
      refresh_token: "RT-456",
    });
    expect(window.location.hash).toBe("");
    expect(window.location.href).not.toContain("AT-123");
    // ⛔ Varredura: os tokens do link nunca são renderizados.
    expect(document.body.innerHTML).not.toContain("AT-123");
    expect(document.body.innerHTML).not.toContain("RT-456");
    expect(screen.getByText("nina@fastpark.dev")).toBeInTheDocument();
  });

  it("`?code=` (PKCE): troca o código pela sessão", async () => {
    auth.exchangeCodeForSession.mockResolvedValue({
      data: { user: CONVIDADA, session: {} },
      error: null,
    });
    abrirEm("/convite?code=CODE-1");

    expect(await screen.findByLabelText("Nova senha")).toBeInTheDocument();
    expect(auth.exchangeCodeForSession).toHaveBeenCalledWith("CODE-1");
    expect(window.location.search).toBe("");
  });

  it("`?token_hash=`: verifica o convite", async () => {
    auth.verifyOtp.mockResolvedValue({
      data: { user: CONVIDADA, session: {} },
      error: null,
    });
    abrirEm("/convite?token_hash=TH-1&type=invite");

    expect(await screen.findByLabelText("Nova senha")).toBeInTheDocument();
    expect(auth.verifyOtp).toHaveBeenCalledWith({
      token_hash: "TH-1",
      type: "invite",
    });
  });

  it("⛔ link expirado (erro no fragmento) mostra a mensagem e não abre sessão", async () => {
    // Há uma sessão neste navegador: o link com erro não pode cair nela.
    auth.getUser.mockResolvedValue({ data: { user: CONVIDADA }, error: null });
    abrirEm(
      "/convite#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired",
    );

    expect(
      await screen.findByText("Este link de convite é inválido ou expirou."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Peça um novo convite a quem convidou você/),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Nova senha")).toBeNull();
    expect(auth.setSession).not.toHaveBeenCalled();
  });

  it("⛔ erro na query também é link inválido", async () => {
    auth.getUser.mockResolvedValue({ data: { user: CONVIDADA }, error: null });
    abrirEm("/convite?error=access_denied&error_code=otp_expired");

    expect(
      await screen.findByText("Este link de convite é inválido ou expirou."),
    ).toBeInTheDocument();
  });

  it("⛔ token recusado pelo Auth é link inválido", async () => {
    auth.setSession.mockResolvedValue({
      data: { user: null, session: null },
      error: { message: "invalid JWT" },
    });
    abrirEm("/convite#access_token=velho&refresh_token=velho");

    expect(
      await screen.findByText("Este link de convite é inválido ou expirou."),
    ).toBeInTheDocument();
  });

  it("⛔ sem link, a sessão já aberta não ganha formulário de senha", async () => {
    auth.getUser.mockResolvedValue({ data: { user: CONVIDADA }, error: null });
    abrirEm("/convite");

    expect(
      await screen.findByText("Este link de convite é inválido ou expirou."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Nova senha")).toBeNull();
  });

  it("⛔ sem link e sem sessão, é link inválido", async () => {
    auth.getUser.mockResolvedValue({ data: { user: null }, error: null });
    abrirEm("/convite");

    expect(
      await screen.findByText("Este link de convite é inválido ou expirou."),
    ).toBeInTheDocument();
  });
});

describe("/convite — o link de recuperação ('Esqueci minha senha')", () => {
  it("`token_hash` com `type=recovery`: verifica como recuperação e grava a senha", async () => {
    auth.verifyOtp.mockResolvedValue({
      data: { user: CONVIDADA, session: {} },
      error: null,
    });
    abrirEm("/convite?token_hash=TH-R&type=recovery");

    expect(
      await screen.findByRole("heading", { name: "Defina uma nova senha" }),
    ).toBeInTheDocument();
    expect(auth.verifyOtp).toHaveBeenCalledWith({
      token_hash: "TH-R",
      type: "recovery",
    });
    expect(window.location.search).toBe("");

    await definirSenha();

    await waitFor(() =>
      expect(auth.updateUser).toHaveBeenCalledWith({ password: SENHA }),
    );
    expect(replace).toHaveBeenCalledWith("/dashboard");
    for (const fn of Object.values(api)) {
      expect(fn).not.toHaveBeenCalled();
    }
  });

  it("fragmento com `type=recovery`: o mesmo `setSession`, e grava a senha", async () => {
    abrirEm(
      "/convite#access_token=AT-R&refresh_token=RT-R&expires_in=3600&token_type=bearer&type=recovery",
    );

    expect(
      await screen.findByRole("heading", { name: "Defina uma nova senha" }),
    ).toBeInTheDocument();
    expect(auth.setSession).toHaveBeenCalledWith({
      access_token: "AT-R",
      refresh_token: "RT-R",
    });
    expect(window.location.hash).toBe("");

    await definirSenha();

    await waitFor(() =>
      expect(auth.updateUser).toHaveBeenCalledWith({ password: SENHA }),
    );
    for (const fn of Object.values(api)) {
      expect(fn).not.toHaveBeenCalled();
    }
  });

  it("PKCE `?code=…&fluxo=recuperacao` (sem `type`) é recuperação", async () => {
    auth.exchangeCodeForSession.mockResolvedValue({
      data: { user: CONVIDADA, session: {} },
      error: null,
    });
    abrirEm("/convite?fluxo=recuperacao&code=CODE-R");

    expect(
      await screen.findByRole("heading", { name: "Defina uma nova senha" }),
    ).toBeInTheDocument();
    expect(auth.exchangeCodeForSession).toHaveBeenCalledWith("CODE-R");
    expect(window.location.search).toBe("");

    await definirSenha();
    await waitFor(() =>
      expect(auth.updateUser).toHaveBeenCalledWith({ password: SENHA }),
    );
  });

  it("⛔ PKCE de recuperação que falha orienta a pedir outro link, não outro convite", async () => {
    auth.exchangeCodeForSession.mockResolvedValue({
      data: { user: null, session: null },
      error: { code: "bad_code_verifier" },
    });
    abrirEm("/convite?fluxo=recuperacao&code=CODE-R");

    expect(
      await screen.findByRole("heading", { name: "Defina uma nova senha" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Este link de nova senha é inválido ou expirou."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Peça um novo convite/)).toBeNull();
  });

  it("o convite continua com o título dele", async () => {
    abrirEm("/convite#access_token=AT&refresh_token=RT&type=invite");

    expect(
      await screen.findByRole("heading", { name: "Defina sua senha" }),
    ).toBeInTheDocument();
  });

  it("recuperação expirada orienta a pedir outro link, não outro convite", async () => {
    abrirEm(
      "/convite#error=access_denied&error_code=otp_expired&type=recovery",
    );

    expect(
      await screen.findByText("Este link de nova senha é inválido ou expirou."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Esqueci minha senha/)).toBeInTheDocument();
  });
});

describe("/convite — a senha", () => {
  it("chama `updateUser` com a senha e segue para o painel", async () => {
    abrirEm("/convite#access_token=AT&refresh_token=RT");

    await definirSenha();

    await waitFor(() =>
      expect(auth.updateUser).toHaveBeenCalledWith({ password: SENHA }),
    );
    expect(replace).toHaveBeenCalledWith("/dashboard");
  });

  it("⛔ a senha não vai ao backend do OperaX nem ao console", async () => {
    const espioes = [
      vi.spyOn(console, "log"),
      vi.spyOn(console, "error"),
      vi.spyOn(console, "warn"),
      vi.spyOn(console, "info"),
    ];
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    abrirEm("/convite#access_token=AT&refresh_token=RT");

    await definirSenha();
    await waitFor(() => expect(replace).toHaveBeenCalled());

    for (const fn of Object.values(api)) {
      expect(fn).not.toHaveBeenCalled();
    }
    expect(fetchSpy).not.toHaveBeenCalled();
    for (const espiao of espioes) {
      expect(JSON.stringify(espiao.mock.calls)).not.toContain(SENHA);
      espiao.mockRestore();
    }
    fetchSpy.mockRestore();
    expect(JSON.stringify(window.localStorage)).not.toContain(SENHA);
    expect(JSON.stringify(window.sessionStorage)).not.toContain(SENHA);
  });

  it("⛔ confirmação diferente não envia", async () => {
    abrirEm("/convite#access_token=AT&refresh_token=RT");

    await definirSenha("Outra-Senha-99");

    expect(
      await screen.findByText("As duas senhas não são iguais."),
    ).toBeInTheDocument();
    expect(auth.updateUser).not.toHaveBeenCalled();
  });

  it("⛔ senha curta não envia", async () => {
    const user = userEvent.setup();
    abrirEm("/convite#access_token=AT&refresh_token=RT");

    await user.type(await screen.findByLabelText("Nova senha"), "curta");
    await user.type(screen.getByLabelText("Confirme a senha"), "curta");
    await user.click(
      screen.getByRole("button", { name: "Definir senha e entrar" }),
    );

    expect(
      await screen.findByText("Use pelo menos 8 caracteres."),
    ).toBeInTheDocument();
    expect(auth.updateUser).not.toHaveBeenCalled();
  });

  it("senha fraca para o Auth mostra a frase e fica na tela", async () => {
    auth.updateUser.mockResolvedValue({
      data: { user: null },
      error: { code: "weak_password", status: 422 },
    });
    abrirEm("/convite#access_token=AT&refresh_token=RT");

    await definirSenha();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Essa senha é fraca demais",
    );
    expect(replace).not.toHaveBeenCalled();
  });

  it("sessão que caiu no meio vira link inválido", async () => {
    auth.updateUser.mockResolvedValue({
      data: { user: null },
      error: { code: "session_not_found", status: 403 },
    });
    abrirEm("/convite#access_token=AT&refresh_token=RT");

    await definirSenha();

    expect(
      await screen.findByText("Este link de convite é inválido ou expirou."),
    ).toBeInTheDocument();
  });
});
