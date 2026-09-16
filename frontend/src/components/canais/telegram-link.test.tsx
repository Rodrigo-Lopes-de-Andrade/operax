import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TelegramLinkCard } from "@/components/canais/telegram-link";
import { ApiError } from "@/lib/api";
import type { InviteIssued, TelegramLink } from "@/lib/canais/queries";

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

const EMPLOYEE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

/** Vinculado às 13:05 UTC — 10:05 em São Paulo. */
const LINKED: TelegramLink = {
  linked: true,
  opted_in_at: "2026-09-15T13:05:00Z",
  revoked_at: null,
  invite_open_until: null,
};

/** Convite em aberto até 01:00 UTC do dia 20 — ainda dia 19 em São Paulo. */
const INVITED: TelegramLink = {
  linked: false,
  opted_in_at: null,
  revoked_at: null,
  invite_open_until: "2026-09-20T01:00:00Z",
};

/** Nunca aderiu: nada em data nenhuma. */
const NEVER: TelegramLink = {
  linked: false,
  opted_in_at: null,
  revoked_at: null,
  invite_open_until: null,
};

/**
 * O falso verde previsto: aderiu um dia e foi revogado. `opted_in_at`
 * preenchido, `linked: false` — um cartão que lesse a data em vez do booleano
 * diria "Vinculado". A revogação às 00:30 UTC do dia 16 é 21:30 do dia 15 em
 * São Paulo.
 */
const REVOKED: TelegramLink = {
  linked: false,
  opted_in_at: "2026-09-01T12:00:00Z",
  revoked_at: "2026-09-16T00:30:00Z",
  invite_open_until: null,
};

// A máscara vem como a API a mandou: um formato que a tela não conseguiria
// compor sozinha prova que ela mostra o que veio.
const ISSUED: InviteIssued = {
  invite_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
  expires_at: "2026-09-20T01:00:00Z",
  queued: true,
  destination_masked: "+55 11 •••••-0000",
};

const VOLUNTARY =
  "A adesão é voluntária: quem não aderir continua recebendo pelo WhatsApp.";

function convidar() {
  return screen.queryByRole("button", { name: "Convidar pelo WhatsApp" });
}

function outroConvite() {
  return screen.queryByRole("button", { name: "Enviar outro convite" });
}

function desvincular() {
  return screen.queryByRole("button", { name: "Desvincular" });
}

function renderCard(link: TelegramLink | null, canWrite = true) {
  return render(
    <TelegramLinkCard employeeId={EMPLOYEE} link={link} canWrite={canWrite} />,
  );
}

beforeEach(() => {
  request.mockReset();
  refresh.mockReset();
});

describe("critério 1 — os três estados, o badge, a data no fuso e o botão certo", () => {
  it("✅ vinculado → 'Vinculado' em verde, 'desde' no fuso do tenant, e só 'Desvincular'", () => {
    renderCard(LINKED);

    const badge = screen.getByText("Vinculado");
    expect(badge).toBeVisible();
    expect(badge.className).toContain("text-good");
    // 13:05 UTC → 10:05 em São Paulo.
    expect(screen.getByText("desde 15/09/2026 às 10:05")).toBeVisible();
    expect(desvincular()).toBeVisible();
    expect(convidar()).toBeNull();
    expect(outroConvite()).toBeNull();
    expect(screen.queryByText("Não aderiu")).toBeNull();
    expect(screen.queryByText("Convite enviado")).toBeNull();
  });

  it("✅ convite em aberto → 'Convite enviado' neutro, 'válido até' no fuso, e só 'Enviar outro convite'", () => {
    renderCard(INVITED);

    const badge = screen.getByText("Convite enviado");
    expect(badge).toBeVisible();
    expect(badge.className).toContain("text-ink-muted");
    // 01:00 UTC do dia 20 ainda é dia 19 em São Paulo.
    expect(screen.getByText("válido até 19/09/2026")).toBeVisible();
    expect(outroConvite()).toBeVisible();
    expect(convidar()).toBeNull();
    expect(desvincular()).toBeNull();
    expect(screen.queryByText("Vinculado")).toBeNull();
    expect(screen.queryByText("Não aderiu")).toBeNull();
  });

  it("✅ nunca aderiu → 'Não aderiu' neutro, sem data, e só 'Convidar pelo WhatsApp'", () => {
    renderCard(NEVER);

    const badge = screen.getByText("Não aderiu");
    expect(badge).toBeVisible();
    expect(badge.className).toContain("text-ink-muted");
    expect(screen.queryByText(/desde|válido até|revogado em/)).toBeNull();
    expect(convidar()).toBeVisible();
    expect(outroConvite()).toBeNull();
    expect(desvincular()).toBeNull();
  });

  it("⛔ FALSO VERDE: `linked: false` com `opted_in_at` preenchido é 'Não aderiu', com 'revogado em' — nunca 'Vinculado'", () => {
    renderCard(REVOKED);

    expect(screen.getByText("Não aderiu")).toBeVisible();
    expect(screen.queryByText("Vinculado")).toBeNull();
    expect(screen.queryByText(/desde/)).toBeNull();
    // 00:30 UTC do dia 16 é 21:30 do dia 15 em São Paulo.
    expect(screen.getByText("revogado em 15/09/2026")).toBeVisible();
    expect(convidar()).toBeVisible();
    expect(desvincular()).toBeNull();
  });

  it("⛔ … e o par: `linked: true` vence um `invite_open_until` que sobrou", () => {
    // A ordem é `linked` primeiro. Um cartão que olhasse o convite antes diria
    // "Convite enviado" para quem já aderiu.
    renderCard({ ...LINKED, invite_open_until: "2026-09-20T01:00:00Z" });

    expect(screen.getByText("Vinculado")).toBeVisible();
    expect(screen.queryByText("Convite enviado")).toBeNull();
    expect(desvincular()).toBeVisible();
    expect(outroConvite()).toBeNull();
  });

  it("⛔ 'desde' é de `opted_in_at`, não de outra data: vinculado sem a data é só o badge", () => {
    renderCard({ ...LINKED, opted_in_at: null });

    expect(screen.getByText("Vinculado")).toBeVisible();
    expect(screen.queryByText(/desde/)).toBeNull();
  });

  it("⛔ a hora depois das 21h muda de dia em UTC e não no fuso do tenant", () => {
    renderCard({ ...LINKED, opted_in_at: "2026-09-16T00:30:00Z" });

    expect(screen.getByText("desde 15/09/2026 às 21:30")).toBeVisible();
    expect(screen.queryByText(/16\/09/)).toBeNull();
  });

  it("⛔ `canWrite: false` → nenhum botão, nos três estados; o badge e a data ficam", () => {
    for (const [link, texto] of [
      [LINKED, "Vinculado"],
      [INVITED, "Convite enviado"],
      [NEVER, "Não aderiu"],
    ] as const) {
      const { unmount } = renderCard(link, false);

      expect(screen.getByText(texto)).toBeVisible();
      expect(screen.queryByRole("button")).toBeNull();
      unmount();
    }
    renderCard(LINKED, false);
    expect(screen.getByText("desde 15/09/2026 às 10:05")).toBeVisible();
  });

  it("⛔ `link: null` → a frase de leitura, nenhum badge e nenhum botão — mesmo para quem escreve", () => {
    renderCard(null, true);

    expect(
      screen.getByText("Não deu para ler o vínculo do Telegram agora."),
    ).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();
    expect(
      screen.queryByText(/Vinculado|Convite enviado|Não aderiu/),
    ).toBeNull();
  });

  it("o cartão se chama Telegram", () => {
    renderCard(LINKED);

    expect(screen.getByRole("heading", { name: "Telegram" })).toBeVisible();
  });
});

describe("critério 4 — a frase da adesão voluntária está em todos os estados", () => {
  it.each([
    ["vinculado", LINKED],
    ["convite em aberto", INVITED],
    ["nunca aderiu", NEVER],
    ["revogado", REVOKED],
    ["sem leitura", null],
  ] as const)("%s", (_nome, link) => {
    renderCard(link);

    expect(screen.getByText(VOLUNTARY)).toBeVisible();
  });

  it("⛔ nenhuma palavra de cobrança em estado nenhum: 'pendente', 'faltam', 'lembrete', 'aguardando'", () => {
    // Decisão do dono, 16/09/2026: o convite é oferta. Um "convite pendente"
    // ou "aguardando resposta" transformaria oferta em cobrança.
    for (const link of [LINKED, INVITED, NEVER, REVOKED, null]) {
      const { container, unmount } = renderCard(link);

      expect(container.textContent).not.toMatch(
        /pendente|faltam|falta |lembrete|aguardando|cobran/i,
      );
      unmount();
    }
  });
});

describe("critério 2 — o convite: o POST exato, o número mascarado como veio, e os erros", () => {
  it("✅ POST em `/canais/telegram/convites` com `{employee_id, contact_id: null}` — e nada mais", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(ISSUED);
    renderCard(NEVER);

    await user.click(convidar()!);

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0]).toStrictEqual([
      "/canais/telegram/convites",
      {
        method: "POST",
        body: { employee_id: EMPLOYEE, contact_id: null },
      },
    ]);
    // ⛔ Nada de tenant no corpo nem na URL.
    expect(JSON.stringify(request.mock.calls[0])).not.toMatch(/tenant/i);
  });

  it("✅ sucesso → status com o número mascarado COMO VEIO e a validade no fuso, e refresh", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(ISSUED);
    const { container } = renderCard(NEVER);

    await user.click(convidar()!);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Convite enviado para +55 11 •••••-0000, válido até 19/09/2026.",
    );
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).toBeNull();
    // ⛔ O painel nunca vê o link (§3.3): nenhum endereço, nenhum `t.me`, e o
    // id do convite também não — a tela só tem onde pôr o número mascarado e
    // a data.
    expect(container.textContent).not.toMatch(/t\.me|https?:|start=/);
    expect(container.textContent).not.toContain(ISSUED.invite_id);
    expect(container.querySelector("a")).toBeNull();
  });

  it("⛔ a máscara é a da resposta, não uma composta na tela", async () => {
    // Um cartão que mascarasse por conta própria não acertaria este formato.
    const user = userEvent.setup();
    request.mockResolvedValue({
      ...ISSUED,
      destination_masked: "zz-mascara-que-so-a-api-sabe",
    });
    renderCard(NEVER);

    await user.click(convidar()!);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Convite enviado para zz-mascara-que-so-a-api-sabe, válido até 19/09/2026.",
    );
  });

  it("'Enviar outro convite' faz o mesmo POST, com o mesmo corpo", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(ISSUED);
    renderCard(INVITED);

    await user.click(outroConvite()!);

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0]).toStrictEqual([
      "/canais/telegram/convites",
      {
        method: "POST",
        body: { employee_id: EMPLOYEE, contact_id: null },
      },
    ]);
    expect(await screen.findByRole("status")).toHaveTextContent(
      /Convite enviado para/,
    );
  });

  it("enquanto roda, o botão fica desabilitado com 'Enviando convite…'", async () => {
    const user = userEvent.setup();
    let resolve: (value: InviteIssued) => void = () => {};
    request.mockReturnValue(
      new Promise<InviteIssued>((done) => {
        resolve = done;
      }),
    );
    renderCard(NEVER);

    await user.click(convidar()!);

    const busy = await screen.findByRole("button", {
      name: "Enviando convite…",
    });
    expect(busy).toBeDisabled();
    expect(screen.queryByRole("status")).toBeNull();

    resolve(ISSUED);
    await screen.findByRole("status");
    // A prop ainda é a antiga (o refresh é quem a troca): o botão volta ao
    // que a prop diz, habilitado.
    expect(convidar()).toBeEnabled();
  });

  it.each([
    [
      "no_phone",
      "Este colaborador não tem telefone em cadastro; o convite não tem para onde ir.",
    ],
    ["invalid_phone", "O telefone em cadastro não parece um número válido."],
    ["no_bot", "Não há bot de Telegram ativo neste cliente."],
    [
      "no_whatsapp",
      "Não há provedor de WhatsApp ativo; o convite não tem por onde sair.",
    ],
    [
      "no_invite_template",
      "O template telegram_invite não existe ou está inativo — cadastre-o na aba de templates.",
    ],
    [
      "not_a_person",
      "O convite precisa de um colaborador ou de um responsável.",
    ],
  ])(
    '⛔ 422 `%s` → o `detail` como veio, em `role="alert"`, sem refresh e sem status',
    async (_code, detail) => {
      const user = userEvent.setup();
      request.mockRejectedValue(new ApiError(422, detail));
      renderCard(NEVER);

      await user.click(convidar()!);

      expect(await screen.findByRole("alert")).toHaveTextContent(detail);
      expect(refresh).not.toHaveBeenCalled();
      expect(screen.queryByRole("status")).toBeNull();
      expect(convidar()).toBeEnabled();
    },
  );

  it("403 → o `detail` da API", async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(
      new ApiError(403, "Convidar é do administrador do cliente."),
    );
    renderCard(NEVER);

    await user.click(convidar()!);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Convidar é do administrador do cliente.",
    );
    expect(refresh).not.toHaveBeenCalled();
  });

  it("500 sem `detail` → a frase padrão do convite, e o botão continua de pé", async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(new ApiError(500, null));
    renderCard(NEVER);

    await user.click(convidar()!);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não consegui enviar o convite.",
    );
    expect(convidar()).toBeEnabled();
  });

  it("um erro antigo some ao clicar de novo; um sucesso antigo some quando o clique seguinte falha", async () => {
    const user = userEvent.setup();
    let responder: (issued: InviteIssued) => void = () => {};
    request
      .mockRejectedValueOnce(new ApiError(422, "recusado na primeira"))
      .mockImplementationOnce(
        () =>
          new Promise<InviteIssued>((resolve) => {
            responder = resolve;
          }),
      )
      .mockRejectedValueOnce(new ApiError(422, "recusado na terceira"));
    renderCard(NEVER);

    await user.click(convidar()!);
    await screen.findByRole("alert");

    await user.click(convidar()!);
    // O erro antigo some no clique, não quando a resposta chega: com a
    // promessa ainda pendente, a tela já não o mostra.
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
    responder(ISSUED);
    await screen.findByRole("status");
    expect(screen.queryByRole("alert")).toBeNull();

    await user.click(convidar()!);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "recusado na terceira",
    );
    // "Convite enviado" ao lado de "recusado" é contradição na tela.
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("critério 3 — desvincular: a rota do colaborador, a frase, e o 409", () => {
  it("✅ POST em `/canais/telegram/vinculos/{id}/revogar` sem corpo, refresh e a frase de sucesso", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(REVOKED);
    renderCard(LINKED);

    await user.click(desvincular()!);

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0]).toStrictEqual([
      `/canais/telegram/vinculos/${EMPLOYEE}/revogar`,
      { method: "POST" },
    ]);
    expect(JSON.stringify(request.mock.calls[0])).not.toMatch(/tenant/i);
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Telegram desvinculado. Os avisos voltam a sair pelo WhatsApp.",
    );
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("⛔ … e é o id recebido que vai na rota", async () => {
    const user = userEvent.setup();
    const outro = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
    request.mockResolvedValue(REVOKED);
    render(<TelegramLinkCard employeeId={outro} link={LINKED} canWrite />);

    await user.click(desvincular()!);

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0][0]).toBe(
      `/canais/telegram/vinculos/${outro}/revogar`,
    );
  });

  it("enquanto roda, 'Desvinculando…' desabilitado", async () => {
    const user = userEvent.setup();
    request.mockReturnValue(new Promise<never>(() => {}));
    renderCard(LINKED);

    await user.click(desvincular()!);

    expect(
      await screen.findByRole("button", { name: "Desvinculando…" }),
    ).toBeDisabled();
  });

  it("⛔ 409 `not_linked` → o `detail` como veio, sem refresh", async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(
      new ApiError(409, "Este colaborador não tem vínculo vigente."),
    );
    renderCard(LINKED);

    await user.click(desvincular()!);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Este colaborador não tem vínculo vigente.",
    );
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.queryByRole("status")).toBeNull();
    expect(desvincular()).toBeEnabled();
  });

  it("403 → o `detail` da API", async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(
      new ApiError(403, "Desvincular é do administrador do cliente."),
    );
    renderCard(LINKED);

    await user.click(desvincular()!);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Desvincular é do administrador do cliente.",
    );
  });

  it("500 sem `detail` → a frase padrão é a de desvincular, não a do convite", async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(new ApiError(500, null));
    renderCard(LINKED);

    await user.click(desvincular()!);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não consegui desvincular o Telegram.",
    );
    expect(refresh).not.toHaveBeenCalled();
  });

  it("⛔ depois do refresh a tela mostra o que a prop trouxer — sem cópia local do vínculo", async () => {
    const user = userEvent.setup();
    // A resposta do servidor traz OUTRA data de revogação que a prop do
    // refresh: se a tela guardasse a resposta e a mostrasse por cima da
    // prop, o "10/09" apareceria. A prop tem de vencer, sempre.
    request.mockResolvedValue({
      ...REVOKED,
      revoked_at: "2026-09-10T12:00:00Z",
    });
    const { rerender } = renderCard(LINKED);

    await user.click(desvincular()!);
    await screen.findByRole("status");
    expect(refresh).toHaveBeenCalledTimes(1);
    // Antes de o refresh trazer a prop nova, a tela ainda é a da prop antiga.
    expect(screen.getByText("Vinculado")).toBeVisible();
    expect(screen.queryByText(/revogado em/)).toBeNull();

    // O que o refresh traz: revogado, e agora o botão é o de convidar.
    rerender(
      <TelegramLinkCard employeeId={EMPLOYEE} link={REVOKED} canWrite />,
    );
    expect(screen.getByText("Não aderiu")).toBeVisible();
    expect(screen.getByText("revogado em 15/09/2026")).toBeVisible();
    expect(screen.queryByText(/10\/09/)).toBeNull();
    expect(desvincular()).toBeNull();
    expect(convidar()).toBeVisible();
  });
});
