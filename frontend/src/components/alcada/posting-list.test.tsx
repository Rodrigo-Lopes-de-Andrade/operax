import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PostingList } from "@/components/alcada/posting-list";
import { ApiError } from "@/lib/api";
import {
  POSTING_ERROR_MESSAGE,
  type PostingListRow,
} from "@/lib/alcada/posting";

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

const EU = "99999999-9999-4999-8999-999999999999";
const OUTRO_RH = "88888888-8888-4888-8888-888888888888";
const REVIEW_MARIA = "11111111-1111-4111-8111-111111111111";
const REVIEW_JOAO = "22222222-2222-4222-8222-222222222222";
const REVIEW_ANA = "33333333-3333-4333-8333-333333333333";

function linha(overrides: Partial<PostingListRow>): PostingListRow {
  return {
    review_id: REVIEW_MARIA,
    justification_id: "44444444-4444-4444-8444-444444444444",
    employee_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    employee_name: "Maria Souza",
    unit_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    unit_name: "DEV Norte",
    reference_date: "2026-09-24",
    type: "early_exit",
    type_description: "Saída antecipada",
    minutes: 75,
    text: "Consulta médica com atestado entregue ao gestor.",
    author_name: "Carlos Supervisor",
    reviewed_by: OUTRO_RH,
    reviewed_at: "2026-09-26T13:00:00Z",
    posted_to_source_at: null,
    posted_by: null,
    ...overrides,
  };
}

// A ordem da API (pendentes primeiro) é de propósito embaralhada aqui: a
// separação tem de vir da marca, não da posição.
const LISTA: PostingListRow[] = [
  linha({
    review_id: REVIEW_ANA,
    justification_id: "55555555-5555-4555-8555-555555555555",
    employee_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    employee_name: "Ana Prado",
    reviewed_by: EU,
    posted_to_source_at: "2026-09-28T23:30:00Z",
    posted_by: EU,
  }),
  linha({}),
  linha({
    review_id: REVIEW_JOAO,
    justification_id: "66666666-6666-4666-8666-666666666666",
    employee_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    employee_name: "João Lima",
    type_description: "Atraso na entrada",
    minutes: 20,
    reviewed_by: EU,
  }),
];

function aLancar() {
  return screen.getByRole("list", { name: "A lançar no Secullum" });
}

function lancadas() {
  return screen.getByRole("list", { name: "Já lançadas" });
}

function contagem() {
  return screen.getByRole("group", { name: "Pendentes de lançamento" });
}

function montar(rows: PostingListRow[] = LISTA, currentUserId = EU) {
  return render(<PostingList rows={rows} currentUserId={currentUserId} />);
}

async function marcar(user: ReturnType<typeof userEvent.setup>, nome: string) {
  await user.click(
    within(within(aLancar()).getByRole("listitem", { name: nome })).getByRole(
      "button",
      { name: "Marcar como lançado no Secullum" },
    ),
  );
  await user.click(
    screen.getByRole("button", { name: "Confirmar: já lancei no Secullum" }),
  );
}

beforeEach(() => {
  request.mockReset();
  refresh.mockReset();
});

describe("as duas seções, separadas pela marca", () => {
  it("pendente em 'A lançar', marcada em 'Já lançadas' — seja qual for a ordem", () => {
    montar();

    const pendentes = within(aLancar()).getAllByRole("listitem");
    expect(pendentes.map((li) => li.getAttribute("aria-labelledby"))).toEqual([
      `lancamento-${REVIEW_MARIA}`,
      `lancamento-${REVIEW_JOAO}`,
    ]);
    expect(
      within(lancadas()).getByRole("listitem", { name: "Ana Prado" }),
    ).toBeVisible();
    expect(
      within(lancadas()).queryByRole("button", {
        name: "Marcar como lançado no Secullum",
      }),
    ).toBeNull();
  });

  it("a contagem de pendentes fica em destaque", () => {
    montar();

    expect(contagem()).toHaveTextContent("2pendentes");
    expect(
      screen.getByText("1 aprovação marcada como lançada no Secullum."),
    ).toBeVisible();
  });

  it("uma pendente fala no singular", () => {
    montar([linha({})]);

    expect(contagem()).toHaveTextContent("1pendente");
  });

  it("sem pendente, a seção diz que não há nada a lançar", () => {
    montar([LISTA[0]]);

    expect(contagem()).toHaveTextContent("0pendentes");
    expect(screen.getByText("Nada a lançar no recorte")).toBeVisible();
    expect(
      screen.queryByRole("list", { name: "A lançar no Secullum" }),
    ).toBeNull();
  });

  it("sem lançada, a outra seção diz isso — e não some", () => {
    montar([linha({})]);

    expect(
      screen.getByText(
        "Nenhuma aprovação deste recorte foi marcada como lançada ainda.",
      ),
    ).toBeVisible();
  });
});

describe("o item", () => {
  it("pendente: colaborador, unidade, data, tipo, minutos, texto, aprovação e o botão", () => {
    montar();

    const maria = within(aLancar()).getByRole("listitem", {
      name: "Maria Souza",
    });
    expect(within(maria).getByText("DEV Norte")).toBeVisible();
    expect(within(maria).getByText("24/09/2026")).toBeVisible();
    expect(within(maria).getByText("Saída antecipada")).toBeVisible();
    expect(within(maria).getByText("1h 15min")).toBeVisible();
    expect(
      within(maria).getByText(
        "Consulta médica com atestado entregue ao gestor.",
      ),
    ).toBeVisible();
    expect(
      within(maria).getByText("Aprovada em").nextSibling,
    ).toHaveTextContent(/^26\/09\/2026$/);
    expect(
      within(maria).getByRole("button", {
        name: "Marcar como lançado no Secullum",
      }),
    ).toBeVisible();
  });

  it("aprovada pelo próprio usuário diz 'por você'; por outro, só a data", () => {
    montar();

    const joao = within(aLancar()).getByRole("listitem", { name: "João Lima" });
    expect(within(joao).getByText("Aprovada em").nextSibling).toHaveTextContent(
      "26/09/2026, por você",
    );
  });

  it("lançada mostra quando — no dia do fuso do tenant, não no de UTC", () => {
    montar();

    // 23h30 UTC do dia 28 é 20h30 do dia 28 em Brasília.
    const ana = within(lancadas()).getByRole("listitem", { name: "Ana Prado" });
    expect(within(ana).getByText("Lançada em").nextSibling).toHaveTextContent(
      "28/09/2026, por você",
    );
  });

  it("⛔ nenhum uuid aparece na tela", () => {
    const { container } = montar(LISTA, "77777777-7777-4777-8777-777777777777");

    expect(container.textContent ?? "").not.toMatch(
      /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
    );
    expect(container.textContent ?? "").not.toMatch(/por você/);
  });

  it("⛔ nunca diz 'hora extra'", () => {
    const { container } = montar();

    expect(container.textContent ?? "").not.toMatch(/hora extra/i);
  });
});

describe("marcar como lançado", () => {
  it("o primeiro clique só abre a salvaguarda, que nomeia pessoa e dia e diz que é definitivo", async () => {
    const user = userEvent.setup();
    montar();

    await user.click(
      within(
        within(aLancar()).getByRole("listitem", { name: "Maria Souza" }),
      ).getByRole("button", { name: "Marcar como lançado no Secullum" }),
    );

    expect(request).not.toHaveBeenCalled();
    const form = screen.getByRole("form", {
      name: "Confirmar lançamento no Secullum",
    });
    expect(form).toHaveTextContent(
      "Marcar a justificativa de Maria Souza em 24/09/2026 como lançada no Secullum?",
    );
    expect(form).toHaveTextContent("definitiva e não pode ser desfeita");
  });

  it("cancelar volta ao botão sem enviar nada", async () => {
    const user = userEvent.setup();
    montar();

    await user.click(
      within(
        within(aLancar()).getByRole("listitem", { name: "Maria Souza" }),
      ).getByRole("button", { name: "Marcar como lançado no Secullum" }),
    );
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(request).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("form", { name: "Confirmar lançamento no Secullum" }),
    ).toBeNull();
  });

  it("✅ envia `{}` e, no 200, o item passa para 'Já lançadas' com a data", async () => {
    request.mockResolvedValue({
      review_id: REVIEW_MARIA,
      posted_to_source_at: "2026-10-04T12:00:00Z",
      posted_by: EU,
    });
    const user = userEvent.setup();
    montar();

    await marcar(user, "Maria Souza");

    await waitFor(() =>
      expect(
        within(lancadas()).getByRole("listitem", { name: "Maria Souza" }),
      ).toBeVisible(),
    );
    expect(request).toHaveBeenCalledWith(
      `/alcada/revisoes/${REVIEW_MARIA}/lancamento`,
      { method: "POST", body: {} },
    );
    expect(
      within(aLancar()).queryByRole("listitem", { name: "Maria Souza" }),
    ).toBeNull();
    const maria = within(lancadas()).getByRole("listitem", {
      name: "Maria Souza",
    });
    expect(within(maria).getByText("Lançada em").nextSibling).toHaveTextContent(
      "04/10/2026, por você",
    );
    expect(contagem()).toHaveTextContent("1pendente");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Justificativa de Maria Souza marcada como lançada no Secullum.",
    );
    expect(refresh).toHaveBeenCalled();
  });
});

describe("cada recusa tem a sua frase", () => {
  const CASOS: [string, number, boolean][] = [
    // [código, status, a lista é recarregada?]
    ["not_hr", 403, false],
    ["review_not_found", 404, true],
    ["not_approved", 409, false],
    ["already_posted", 409, true],
  ];

  it("os quatro códigos estão mapeados, e nenhum repete a frase de outro", () => {
    const frases = CASOS.map(([code]) => POSTING_ERROR_MESSAGE[code]);

    expect(frases.every(Boolean)).toBe(true);
    expect(new Set(frases).size).toBe(4);
    expect(frases.join(" ")).not.toMatch(/hora extra/i);
  });

  it.each(CASOS)("%s (%i)", async (code, status, recarrega) => {
    request.mockRejectedValue(new ApiError(status, code));
    const user = userEvent.setup();
    montar();

    await marcar(user, "Maria Souza");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      POSTING_ERROR_MESSAGE[code],
    );
    // Recusa nunca vira marca: a linha não vai para "Já lançadas".
    expect(
      within(lancadas()).queryByRole("listitem", { name: "Maria Souza" }),
    ).toBeNull();

    if (recarrega) {
      expect(refresh).toHaveBeenCalled();
      expect(
        screen.queryByRole("listitem", { name: "Maria Souza" }),
      ).toBeNull();
    } else {
      expect(refresh).not.toHaveBeenCalled();
      expect(
        within(aLancar()).getByRole("listitem", { name: "Maria Souza" }),
      ).toBeVisible();
    }
  });

  it("⛔ `already_posted`: depois do refresh, a linha volta em 'Já lançadas'", async () => {
    request.mockRejectedValue(new ApiError(409, "already_posted"));
    const user = userEvent.setup();
    const { rerender } = montar();

    await marcar(user, "Maria Souza");
    await screen.findByRole("alert");

    // O que o `router.refresh()` traz: a mesma linha, marcada por outra pessoa.
    rerender(
      <PostingList
        rows={LISTA.map((row) =>
          row.review_id === REVIEW_MARIA
            ? {
                ...row,
                posted_to_source_at: "2026-10-03T15:00:00Z",
                posted_by: OUTRO_RH,
              }
            : row,
        )}
        currentUserId={EU}
      />,
    );

    const maria = within(lancadas()).getByRole("listitem", {
      name: "Maria Souza",
    });
    expect(within(maria).getByText("Lançada em").nextSibling).toHaveTextContent(
      /^03\/10\/2026$/,
    );
  });

  it("falha sem código (rede, 500) não inventa causa", async () => {
    request.mockRejectedValue(new TypeError("fetch failed"));
    const user = userEvent.setup();
    montar();

    await marcar(user, "Maria Souza");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível registrar a marca. Nada foi alterado",
    );
    expect(
      within(aLancar()).getByRole("listitem", { name: "Maria Souza" }),
    ).toBeVisible();
  });
});
