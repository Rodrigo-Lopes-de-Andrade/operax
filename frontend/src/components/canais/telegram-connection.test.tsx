import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TelegramConnection } from "@/components/canais/telegram-connection";
import { ApiError } from "@/lib/api";
import type { TelegramChannel } from "@/lib/canais/queries";

const request = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push: vi.fn() }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    requestApiAsUser: (...args: unknown[]) => request(...args),
  };
});

// Caudas que nenhum bot real tem: o endereço só aparece se vier da prop.
const OLD_TOKEN = "zz-antigo-0123456789abcdefghij";
const NEW_TOKEN = "zz-novo-9876543210zyxwvutsrqpo";
// O endereço como o backend o registrou no `setWebhook`. O host **não** é o
// `NEXT_PUBLIC_API_URL` do ambiente de teste (`http://api.stub.test`): uma
// tela que compusesse o endereço em vez de mostrar o que veio cairia aqui.
const HOST = "https://api.zz-inventada.test/webhooks/telegram/";
const OLD_URL = `${HOST}${OLD_TOKEN}`;
const NEW_URL = `${HOST}${NEW_TOKEN}`;

function channel(overrides: Partial<TelegramChannel> = {}): TelegramChannel {
  return {
    provider: "telegram",
    capabilities: {
      official: true,
      requires_templates: false,
      ban_risk: false,
      requires_recipient_opt_in: true,
    },
    bot_username: "@zz_bot_inventado",
    webhook_configured: true,
    webhook_url: OLD_URL,
    webhook_path_token: OLD_TOKEN,
    health_status: "connected",
    health_checked_at: "2026-09-15T13:05:00Z",
    health_changed_at: "2026-09-14T09:00:00Z",
    health_detail: null,
    ready: true,
    ...overrides,
  };
}

/** Sem registro: o estado logo depois de gravar o token. */
const UNREGISTERED = channel({
  webhook_configured: false,
  webhook_url: null,
  webhook_path_token: null,
  health_status: null,
  health_checked_at: null,
  health_changed_at: null,
  ready: false,
});

function conectar() {
  return screen.queryByRole("button", { name: "Conectar bot" });
}

function desconectar() {
  return screen.queryByRole("button", { name: "Desconectar" });
}

function endereco() {
  return screen.queryByText(/\/webhooks\/telegram\//);
}

const writeText = vi.fn();

/**
 * O `userEvent.setup()` instala o próprio stub de `navigator.clipboard`; o
 * nosso entra por cima **depois** dele, senão o clique escreve no stub deles
 * e o mock nunca é chamado.
 */
function stubClipboard() {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
}

beforeEach(() => {
  request.mockReset();
  refresh.mockReset();
  writeText.mockReset();
  writeText.mockResolvedValue(undefined);
});

afterEach(() => {
  Reflect.deleteProperty(navigator, "clipboard");
});

describe("critério 4 — o botão certo, só para quem escreve", () => {
  it("⛔ sem registro e com credencial → 'Conectar bot', e não 'Desconectar'", () => {
    // A credencial existe porque o canal existe: `telegram` nulo é "nenhum
    // bot ativo", e aí este componente nem é montado.
    render(<TelegramConnection channel={UNREGISTERED} canWrite />);

    expect(conectar()).toBeVisible();
    expect(desconectar()).toBeNull();
    expect(endereco()).toBeNull();
    expect(
      screen.getByText(/ainda não está registrado no Telegram/),
    ).toBeVisible();
  });

  it("⛔ registrado → 'Desconectar', e não 'Conectar bot'", () => {
    render(<TelegramConnection channel={channel()} canWrite />);

    expect(desconectar()).toBeVisible();
    expect(conectar()).toBeNull();
  });

  it("⛔ `canWrite: false` → nenhum botão, nos dois estados", () => {
    const { unmount } = render(
      <TelegramConnection channel={UNREGISTERED} canWrite={false} />,
    );
    expect(screen.queryByRole("button")).toBeNull();
    unmount();

    render(<TelegramConnection channel={channel()} canWrite={false} />);
    // O de copiar não é escrita: fica.
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: "Copiar endereço do webhook" }),
    ).toBeVisible();
    expect(desconectar()).toBeNull();
    expect(conectar()).toBeNull();
  });

  it("⛔ nunca há 'reconectar' — nem para bot desconectado", () => {
    render(
      <TelegramConnection
        channel={channel({ health_status: "disconnected", ready: false })}
        canWrite
      />,
    );

    expect(screen.queryByRole("button", { name: /reconectar/i })).toBeNull();
    expect(desconectar()).toBeVisible();
  });
});

describe("critério 4 — conectar: POST sem corpo, pendente, sucesso e erro", () => {
  it("✅ POST em `/canais/telegram/conectar` sem corpo, depois refresh e a frase de sucesso", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(channel());
    render(<TelegramConnection channel={UNREGISTERED} canWrite />);

    await user.click(conectar()!);

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0]).toStrictEqual([
      "/canais/telegram/conectar",
      { method: "POST" },
    ]);
    // ⛔ Nada de tenant no corpo nem na URL — não há corpo.
    expect(JSON.stringify(request.mock.calls[0])).not.toMatch(/tenant/i);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Bot conectado. O Telegram vai chamar o endereço novo.",
    );
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("enquanto roda, o botão fica desabilitado com 'Registrando no Telegram…'", async () => {
    const user = userEvent.setup();
    let resolve: (value: TelegramChannel) => void = () => {};
    request.mockReturnValue(
      new Promise<TelegramChannel>((done) => {
        resolve = done;
      }),
    );
    render(<TelegramConnection channel={UNREGISTERED} canWrite />);

    await user.click(conectar()!);

    const busy = await screen.findByRole("button", {
      name: "Registrando no Telegram…",
    });
    expect(busy).toBeDisabled();
    expect(screen.queryByRole("status")).toBeNull();

    resolve(channel());
    await screen.findByRole("status");
    // A prop ainda é a antiga (o refresh é quem a troca): o botão volta ao
    // que a prop diz, habilitado.
    expect(conectar()).toBeEnabled();
  });

  it('⛔ 422 → o `detail` como veio, em `role="alert"`, sem refresh e sem status', async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(
      new ApiError(
        422,
        "A API não tem endereço público configurado; o Telegram não teria para onde chamar.",
      ),
    );
    render(<TelegramConnection channel={UNREGISTERED} canWrite />);

    await user.click(conectar()!);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A API não tem endereço público configurado; o Telegram não teria para onde chamar.",
    );
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.queryByRole("status")).toBeNull();
    expect(conectar()).toBeEnabled();
  });

  it("403 → o `detail` da API", async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(
      new ApiError(403, "Registrar o bot é do administrador do cliente."),
    );
    render(<TelegramConnection channel={UNREGISTERED} canWrite />);

    await user.click(conectar()!);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Registrar o bot é do administrador do cliente.",
    );
  });

  it("500 sem `detail` → a frase padrão, e o botão continua de pé", async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(new ApiError(500, null));
    render(<TelegramConnection channel={UNREGISTERED} canWrite />);

    await user.click(conectar()!);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não consegui registrar o bot no Telegram.",
    );
    expect(conectar()).toBeEnabled();
  });

  it("um erro antigo some ao clicar de novo; um sucesso antigo some quando o clique seguinte falha", async () => {
    const user = userEvent.setup();
    request
      .mockRejectedValueOnce(new ApiError(422, "recusado na primeira"))
      .mockResolvedValueOnce(channel())
      .mockRejectedValueOnce(new ApiError(422, "recusado na terceira"));
    render(<TelegramConnection channel={UNREGISTERED} canWrite />);

    await user.click(conectar()!);
    await screen.findByRole("alert");

    await user.click(conectar()!);
    await screen.findByRole("status");
    expect(screen.queryByRole("alert")).toBeNull();

    await user.click(conectar()!);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "recusado na terceira",
    );
    // "Bot conectado" ao lado de "recusado" é contradição na tela.
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("critério 4 — desconectar: a outra rota, a outra frase", () => {
  it("✅ POST em `/canais/telegram/desconectar` sem corpo, refresh e a frase de sucesso", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(UNREGISTERED);
    render(<TelegramConnection channel={channel()} canWrite />);

    await user.click(desconectar()!);

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0]).toStrictEqual([
      "/canais/telegram/desconectar",
      { method: "POST" },
    ]);
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Bot desconectado. O endereço antigo deixou de existir.",
    );
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("enquanto roda, 'Removendo…' desabilitado", async () => {
    const user = userEvent.setup();
    request.mockReturnValue(new Promise<never>(() => {}));
    render(<TelegramConnection channel={channel()} canWrite />);

    await user.click(desconectar()!);

    expect(
      await screen.findByRole("button", { name: "Removendo…" }),
    ).toBeDisabled();
  });

  it("⛔ erro ao desconectar → o `detail` como veio, e a frase padrão é a de remover", async () => {
    const user = userEvent.setup();
    request.mockRejectedValueOnce(new ApiError(500, null));
    render(<TelegramConnection channel={channel()} canWrite />);

    await user.click(desconectar()!);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não consegui remover o registro no Telegram.",
    );
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("critério 2 e 4 — o endereço: truncado, copiável, e o novo depois de reconectar", () => {
  it("⛔ o endereço mostrado é o `webhook_url` como veio, com a cauda truncada no meio — nunca inteira", () => {
    const { container } = render(
      <TelegramConnection channel={channel()} canWrite />,
    );

    expect(endereco()).toHaveTextContent(
      "https://api.zz-inventada.test/webhooks/telegram/zz-ant…efghij",
    );
    expect(container.textContent).not.toContain(OLD_TOKEN);
    expect(container.innerHTML).not.toContain(OLD_TOKEN);
    // ⛔ Não é composto com a URL da API do navegador.
    expect(container.textContent).not.toContain("api.stub.test");
  });

  it("⛔ … e o endereço que aparece é o da prop, não um escrito à mão", () => {
    render(
      <TelegramConnection
        channel={channel({
          webhook_url: NEW_URL,
          webhook_path_token: NEW_TOKEN,
        })}
        canWrite
      />,
    );

    expect(endereco()).toHaveTextContent("zz-nov…tsrqpo");
    expect(endereco()).not.toHaveTextContent("zz-ant");
  });

  it("⛔ a fonte é `webhook_url`, não `webhook_path_token`: quando divergem, a tela mostra a URL", () => {
    // O token fica no tipo, mas o endereço que o Telegram chama é o que o
    // backend registrou — e é esse que a tela mostra e copia.
    render(
      <TelegramConnection
        channel={channel({
          webhook_url: NEW_URL,
          webhook_path_token: OLD_TOKEN,
        })}
        canWrite
      />,
    );

    expect(endereco()).toHaveTextContent("zz-nov…tsrqpo");
    expect(endereco()).not.toHaveTextContent("zz-ant");
  });

  it("✅ 'copiar' põe o endereço inteiro na área de transferência, e diz que copiou", async () => {
    const user = userEvent.setup();
    stubClipboard();
    render(<TelegramConnection channel={channel()} canWrite />);

    await user.click(
      screen.getByRole("button", { name: "Copiar endereço do webhook" }),
    );

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText).toHaveBeenCalledWith(OLD_URL);
    expect(
      await screen.findByRole("button", { name: "Copiar endereço do webhook" }),
    ).toHaveTextContent("copiado");
    // O nome do botão é fixo; o que a tecnologia assistiva ouve é a região viva.
    expect(screen.getByRole("status")).toHaveTextContent("Endereço copiado.");
  });

  it("quando o navegador recusa a área de transferência, a tela diz — não finge", async () => {
    const user = userEvent.setup();
    stubClipboard();
    writeText.mockRejectedValue(new Error("NotAllowedError"));
    render(<TelegramConnection channel={channel()} canWrite />);

    await user.click(
      screen.getByRole("button", { name: "Copiar endereço do webhook" }),
    );

    expect(
      await screen.findByRole("button", { name: "Copiar endereço do webhook" }),
    ).toHaveTextContent("não deu para copiar");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Não deu para copiar o endereço.",
    );
  });

  it("⛔ desconectar e conectar de novo: o endereço mostrado é o NOVO — a prop muda pelo refresh", async () => {
    // SPEC §6: desconectar rotaciona a cauda; reconectar não devolve a antiga.
    // Sem cópia local: a tela mostra o que a prop trouxer.
    const user = userEvent.setup();
    request.mockResolvedValue(UNREGISTERED);
    const { rerender } = render(
      <TelegramConnection channel={channel()} canWrite />,
    );
    expect(endereco()).toHaveTextContent("zz-ant…efghij");

    await user.click(desconectar()!);
    await screen.findByRole("status");
    // O que o refresh traz: sem registro, sem endereço.
    rerender(<TelegramConnection channel={UNREGISTERED} canWrite />);
    expect(endereco()).toBeNull();
    expect(conectar()).toBeVisible();

    // A resposta do POST traz um endereço; o refresh traz outro. O que a tela
    // mostra é o da prop — uma cópia local da resposta morreria aqui.
    request.mockResolvedValue(
      channel({
        webhook_url: `${HOST}zz-resposta-nao-e-a-prop-000000`,
        webhook_path_token: "zz-resposta-nao-e-a-prop-000000",
      }),
    );
    await user.click(conectar()!);
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(2));
    rerender(
      <TelegramConnection
        channel={channel({
          webhook_url: NEW_URL,
          webhook_path_token: NEW_TOKEN,
        })}
        canWrite
      />,
    );

    expect(endereco()).toHaveTextContent("zz-nov…tsrqpo");
    expect(endereco()).not.toHaveTextContent("zz-ant");
    expect(endereco()).not.toHaveTextContent("zz-res");
    expect(desconectar()).toBeVisible();
  });

  it("registrado sem `webhook_url` na resposta: diz que está registrado, sem inventar endereço", () => {
    // Nem com a cauda na mão: o endereço é o que o backend registrou, ou nada.
    render(
      <TelegramConnection channel={channel({ webhook_url: null })} canWrite />,
    );

    expect(endereco()).toBeNull();
    expect(
      screen.getByText(/Registrado no Telegram; o endereço não veio/),
    ).toBeVisible();
    expect(desconectar()).toBeVisible();
  });
});
