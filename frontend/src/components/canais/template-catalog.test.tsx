import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TemplateCatalog } from "@/components/canais/template-catalog";
import { ApiError } from "@/lib/api";
import type {
  ConnectionsScreen,
  TemplateRow,
  TemplateSyncResult,
} from "@/lib/canais/queries";

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

/**
 * Códigos que nenhum template real tem (`deviation_individual` e
 * `deviation_summary` são os do seed). Uma lista escrita à mão no componente
 * não teria como acertar estes — a linha só aparece se vier da prop.
 */
function template(overrides: Partial<TemplateRow> = {}): TemplateRow {
  return {
    code: "zz_teste_um",
    category: "utility",
    language: "pt_BR",
    variables: ["data_observada", "horario"],
    body: "Em {{1}} às {{2}} houve um indício.",
    meta_template_name: "zz_teste_um_v1",
    meta_status: "pending",
    meta_rejection: null,
    active: true,
    // 13:05 UTC é 10:05 em São Paulo — a data sai no fuso do tenant.
    updated_at: "2026-09-15T13:05:00Z",
    ...overrides,
  };
}

const OFFICIAL: ConnectionsScreen = {
  provider: "meta_cloud",
  capabilities: { official: true, requires_templates: true, ban_risk: false },
  templates_total: 1,
  templates_approved: 0,
  rules_blocked: 0,
  ready: false,
  blocked: [],
};

const UNOFFICIAL: ConnectionsScreen = {
  ...OFFICIAL,
  provider: "z_api",
  capabilities: { official: false, requires_templates: false, ban_risk: true },
};

const SYNC_PHRASE = /só se sincroniza com a Cloud API da Meta/;

function linhas() {
  const lista = screen.queryByRole("list", { name: "Templates do cliente" });

  return lista ? within(lista).getAllByRole("listitem") : [];
}

function mapa() {
  return within(
    screen.getByRole("list", { name: "Variáveis no corpo" }),
  ).getAllByRole("listitem");
}

function codigo() {
  return screen.getByLabelText("Código");
}

function variavel(n: number) {
  return screen.getByLabelText(`Variável ${n}`);
}

function corpo() {
  return screen.getByLabelText("Corpo");
}

function gravar() {
  return screen.getByRole("button", { name: "Gravar template" });
}

function sincronizar() {
  return screen.queryByRole("button", { name: "Sincronizar com a Meta" });
}

type User = ReturnType<typeof userEvent.setup>;

/**
 * `user.type` lê `{` e `[` como descritor de tecla; o corpo de um template é
 * feito de `{{n}}`. Escapa os dois para que o que chega ao campo seja o texto.
 */
async function digitar(user: User, element: HTMLElement, text: string) {
  if (text !== "") {
    await user.type(element, text.replaceAll("{", "{{").replaceAll("[", "[["));
  }
}

/** Preenche o formulário de criação com um template válido pela forma. */
async function preencher(
  user: User,
  {
    code = "zz_teste_novo",
    variables = ["data_observada"],
    body = "Em {{1}}.",
  }: { code?: string; variables?: string[]; body?: string } = {},
) {
  await digitar(user, codigo(), code);
  for (const [index, name] of variables.entries()) {
    if (index > 0) {
      await user.click(
        screen.getByRole("button", { name: "adicionar variável" }),
      );
    }
    await digitar(user, variavel(index + 1), name);
  }
  await digitar(user, corpo(), body);
}

beforeEach(() => {
  request.mockReset();
  refresh.mockReset();
});

describe("critério 1 — a lista é a resposta da API, linha a linha", () => {
  it("cada linha traz código, categoria, idioma, estado, nome na Meta e a data no fuso do tenant", () => {
    render(
      <TemplateCatalog
        templates={[
          template(),
          template({
            code: "zz_teste_dois",
            category: "marketing",
            language: "en_US",
            meta_template_name: null,
            meta_status: "approved",
            updated_at: "2026-09-14T23:30:00Z",
          }),
        ]}
        connections={OFFICIAL}
      />,
    );

    const [primeira, segunda] = linhas();
    expect(linhas()).toHaveLength(2);

    expect(within(primeira).getByText("zz_teste_um")).toBeVisible();
    expect(primeira).toHaveTextContent("utility · pt_BR");
    expect(within(primeira).getByText("pendente")).toBeVisible();
    expect(within(primeira).getByText("zz_teste_um_v1")).toBeVisible();
    expect(primeira).toHaveTextContent("atualizado em 15/09/2026 às 10:05");

    expect(within(segunda).getByText("zz_teste_dois")).toBeVisible();
    expect(segunda).toHaveTextContent("marketing · en_US");
    expect(within(segunda).getByText("aprovado")).toBeVisible();
    expect(segunda).toHaveTextContent("sem nome na Meta");
    // 23:30 UTC do dia 14 ainda é dia 14 em São Paulo (20:30).
    expect(segunda).toHaveTextContent("atualizado em 14/09/2026 às 20:30");
  });

  it("⛔ a ordem e a contagem são as da prop — três códigos inventados, três linhas, na ordem", () => {
    render(
      <TemplateCatalog
        templates={[
          template({ code: "zz_c" }),
          template({ code: "zz_a" }),
          template({ code: "zz_b" }),
        ]}
        connections={OFFICIAL}
      />,
    );

    expect(
      linhas().map((linha) => linha.querySelector("code")?.textContent),
    ).toEqual(["zz_c", "zz_a", "zz_b"]);
    expect(screen.getByText(/3 templates neste cliente/)).toBeVisible();
  });

  it.each([
    ["approved", "aprovado", "bg-good-bg"],
    ["rejected", "rejeitado", "bg-bad-bg"],
    ["pending", "pendente", "bg-muted"],
    ["draft", "rascunho", "bg-muted"],
    ["paused", "pausado", "bg-muted"],
  ] as const)(
    "o badge de `%s` diz '%s' com o tom certo",
    (status, texto, classe) => {
      render(
        <TemplateCatalog
          templates={[template({ meta_status: status })]}
          connections={OFFICIAL}
        />,
      );

      const badge = within(linhas()[0]).getByText(texto);
      expect(badge).toBeVisible();
      expect(badge).toHaveClass(classe);
    },
  );

  it("a razão da Meta aparece quando há uma, e só então", () => {
    render(
      <TemplateCatalog
        templates={[
          template({
            code: "zz_reprovado",
            meta_status: "rejected",
            meta_rejection: "INVALID_FORMAT: placeholder sem exemplo",
          }),
          template({ code: "zz_limpo" }),
        ]}
        connections={OFFICIAL}
      />,
    );

    const [reprovado, limpo] = linhas();
    expect(reprovado).toHaveTextContent(
      "Motivo: INVALID_FORMAT: placeholder sem exemplo",
    );
    expect(limpo).not.toHaveTextContent(/Motivo:/);
  });

  it("inativo leva o badge 'Inativo' e o visual apagado; ativo não", () => {
    render(
      <TemplateCatalog
        templates={[
          template({ code: "zz_ativo" }),
          template({ code: "zz_inativo", active: false }),
        ]}
        connections={OFFICIAL}
      />,
    );

    const [ativo, inativo] = linhas();
    expect(within(inativo).getByText("Inativo")).toBeVisible();
    expect(inativo).toHaveClass("opacity-60");
    expect(within(ativo).queryByText("Inativo")).toBeNull();
    expect(ativo).not.toHaveClass("opacity-60");
  });

  it("✅ vazio → 'Nenhum template neste cliente' E o formulário aberto — a tela do primeiro dia", () => {
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    expect(screen.getByText("Nenhum template neste cliente")).toBeVisible();
    expect(linhas()).toHaveLength(0);
    expect(screen.getByText(/0 templates neste cliente/)).toBeVisible();
    // O formulário está lá, em modo de criação, e o código está livre.
    expect(gravar()).toBeVisible();
    expect(codigo()).not.toHaveAttribute("readonly");
    expect(
      screen.getByRole("heading", { name: "Novo template" }),
    ).toBeVisible();
  });
});

describe("critério 2 — o `code`: livre ao criar, travado ao editar, e a forma recusa antes do PUT", () => {
  it("⛔ 'Editar' preenche o formulário com a linha e trava o código", async () => {
    const user = userEvent.setup();
    render(
      <TemplateCatalog
        templates={[template({ active: false })]}
        connections={OFFICIAL}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "Editar zz_teste_um" }),
    );

    expect(
      screen.getByRole("heading", { name: "Editar zz_teste_um" }),
    ).toBeVisible();
    expect(codigo()).toHaveValue("zz_teste_um");
    expect(codigo()).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Categoria")).toHaveValue("utility");
    expect(screen.getByLabelText("Idioma")).toHaveValue("pt_BR");
    expect(variavel(1)).toHaveValue("data_observada");
    expect(variavel(2)).toHaveValue("horario");
    expect(corpo()).toHaveValue("Em {{1}} às {{2}} houve um indício.");
    expect(screen.getByLabelText("Nome na Meta (opcional)")).toHaveValue(
      "zz_teste_um_v1",
    );
    expect(screen.getByLabelText(/^Ativo/)).not.toBeChecked();
    // ✅ E nenhum input para o que a Meta escreve.
    expect(screen.queryByLabelText(/status/i)).toBeNull();
    expect(screen.queryByDisplayValue("pending")).toBeNull();
  });

  it("'Cancelar' volta ao formulário de criação, com o código livre", async () => {
    const user = userEvent.setup();
    render(<TemplateCatalog templates={[template()]} connections={OFFICIAL} />);

    await user.click(
      screen.getByRole("button", { name: "Editar zz_teste_um" }),
    );
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(
      screen.getByRole("heading", { name: "Novo template" }),
    ).toBeVisible();
    expect(codigo()).toHaveValue("");
    expect(codigo()).not.toHaveAttribute("readonly");
  });

  it("⛔ código com maiúscula ou hífen mostra a hint e não chama a API", async () => {
    const user = userEvent.setup();
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user, { code: "Alerta-Desvio" });
    await user.click(gravar());

    expect(
      await screen.findByText(
        "letras minúsculas, dígitos e sublinhado, começando por letra",
      ),
    ).toBeVisible();
    expect(codigo()).toHaveAttribute("aria-invalid", "true");
    expect(request).not.toHaveBeenCalled();
  });

  it("⛔ código curto demais (dois caracteres) também fica no navegador", async () => {
    const user = userEvent.setup();
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user, { code: "ab" });
    await user.click(gravar());

    expect(
      await screen.findByText(
        "letras minúsculas, dígitos e sublinhado, começando por letra",
      ),
    ).toBeVisible();
    expect(request).not.toHaveBeenCalled();
  });

  it("idioma fora de `xx` ou `xx_YY` fica no navegador", async () => {
    const user = userEvent.setup();
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user);
    await user.clear(screen.getByLabelText("Idioma"));
    await user.type(screen.getByLabelText("Idioma"), "portugues");
    await user.click(gravar());

    expect(
      await screen.findByText("código de idioma como pt_BR ou en_US"),
    ).toBeVisible();
    expect(request).not.toHaveBeenCalled();
  });

  it("nome na Meta com maiúscula fica no navegador", async () => {
    const user = userEvent.setup();
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user);
    await user.type(screen.getByLabelText("Nome na Meta (opcional)"), "Nome");
    await user.click(gravar());

    expect(
      await screen.findByText(
        "nome na Meta: letras minúsculas, dígitos e sublinhado",
      ),
    ).toBeVisible();
    expect(request).not.toHaveBeenCalled();
  });

  it("corpo vazio fica no navegador", async () => {
    const user = userEvent.setup();
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user, { body: "" });
    await user.click(gravar());

    const erro = await screen.findByText("Escreva o corpo da mensagem.");
    expect(erro).toBeVisible();
    expect(request).not.toHaveBeenCalled();
    // O erro é anunciado com o campo: `aria-invalid` e o `aria-describedby`
    // apontando para a frase — não só para a ajuda de `{{n}}`.
    expect(corpo()).toHaveAttribute("aria-invalid", "true");
    expect(corpo().getAttribute("aria-describedby")?.split(" ")).toContain(
      erro.id,
    );
  });
});

describe("critério 3 — as variáveis: um input por nome, a ajuda `{{n}}` segue a ordem", () => {
  it("nasce com um input, 'adicionar' põe outro, e a ajuda numera na ordem", async () => {
    const user = userEvent.setup();
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    expect(screen.getAllByLabelText(/^Variável \d+$/)).toHaveLength(1);
    expect(mapa().map((item) => item.textContent)).toEqual([
      "{{1}} = (sem nome)",
    ]);

    await user.type(variavel(1), "data_observada");
    await user.click(
      screen.getByRole("button", { name: "adicionar variável" }),
    );
    await user.type(variavel(2), "horario");

    expect(screen.getAllByLabelText(/^Variável \d+$/)).toHaveLength(2);
    expect(mapa().map((item) => item.textContent)).toEqual([
      "{{1}} = data_observada",
      "{{2}} = horario",
    ]);
  });

  it("⛔ remover uma variável do meio reindexa a ajuda", async () => {
    const user = userEvent.setup();
    render(
      <TemplateCatalog
        templates={[template({ variables: ["um", "dois", "tres"] })]}
        connections={OFFICIAL}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "Editar zz_teste_um" }),
    );
    expect(mapa().map((item) => item.textContent)).toEqual([
      "{{1}} = um",
      "{{2}} = dois",
      "{{3}} = tres",
    ]);

    await user.click(
      screen.getByRole("button", { name: "remover variável 2" }),
    );

    expect(screen.getAllByLabelText(/^Variável \d+$/)).toHaveLength(2);
    expect(variavel(1)).toHaveValue("um");
    expect(variavel(2)).toHaveValue("tres");
    expect(mapa().map((item) => item.textContent)).toEqual([
      "{{1}} = um",
      "{{2}} = tres",
    ]);
  });

  it("a última variável não se remove — o botão fica desabilitado", () => {
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    expect(
      screen.getByRole("button", { name: "remover variável 1" }),
    ).toBeDisabled();
  });

  it("⛔ variável repetida é recusada antes do PUT, e a hint fica na repetida", async () => {
    const user = userEvent.setup();
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user, {
      variables: ["data_observada", "data_observada"],
      body: "{{1}} {{2}}",
    });
    await user.click(gravar());

    expect(await screen.findByText("variável repetida")).toBeVisible();
    expect(variavel(2)).toHaveAttribute("aria-invalid", "true");
    expect(variavel(1)).not.toHaveAttribute("aria-invalid");
    expect(request).not.toHaveBeenCalled();
  });

  it("nome de variável com maiúscula é recusado pela forma", async () => {
    const user = userEvent.setup();
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user, { variables: ["DataObservada"] });
    await user.click(gravar());

    expect(
      await screen.findByText(
        "nome de variável: letras minúsculas, dígitos e sublinhado, começando por letra",
      ),
    ).toBeVisible();
    expect(request).not.toHaveBeenCalled();
  });

  it("⛔ o corpo NÃO é validado contra `{{n}}` no navegador: quem recusa é o banco", async () => {
    // Corpo que não usa {{1}} passa pela forma e chega ao PUT. Um Zod que
    // conferisse os placeholders seria uma cópia do gatilho, livre para
    // divergir — e é o gatilho que responde, com a frase dele.
    const user = userEvent.setup();
    request.mockResolvedValue(template({ code: "zz_teste_novo" }));
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user, { body: "sem placeholder nenhum" });
    await user.click(gravar());

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0][1].body.body).toBe("sem placeholder nenhum");
  });
});

describe("critério 4 — o PUT leva exatamente `TemplateWrite`, na URL com o código", () => {
  it("✅ criar: body estrito, sem `meta_status`, sem `code`, sem `tenant_id`", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(template({ code: "zz_teste_novo" }));
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user, {
      code: "zz_teste_novo",
      variables: ["data_observada", "horario"],
      body: "Em {{1}} às {{2}}.",
    });
    await user.type(
      screen.getByLabelText("Nome na Meta (opcional)"),
      "zz_teste_novo_v1",
    );
    await user.selectOptions(screen.getByLabelText("Categoria"), "marketing");
    await user.click(gravar());

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0]).toStrictEqual([
      "/canais/templates/zz_teste_novo",
      {
        method: "PUT",
        body: {
          category: "marketing",
          language: "pt_BR",
          variables: ["data_observada", "horario"],
          body: "Em {{1}} às {{2}}.",
          meta_template_name: "zz_teste_novo_v1",
          active: true,
        },
      },
    ]);
    // ⛔ O tenant sai do token; nem a URL nem o corpo o carregam.
    expect(JSON.stringify(request.mock.calls[0])).not.toMatch(/tenant/i);
  });

  it("nome na Meta vazio vai como `null`, e 'Ativo' desmarcado vai como `false`", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(template({ code: "zz_teste_novo" }));
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user);
    await user.click(screen.getByLabelText(/^Ativo/));
    await user.click(gravar());

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0][1].body).toStrictEqual({
      category: "utility",
      language: "pt_BR",
      variables: ["data_observada"],
      body: "Em {{1}}.",
      meta_template_name: null,
      active: false,
    });
  });

  it("✅ editar: a URL leva o código travado, o corpo leva o que mudou", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(template({ body: "Novo corpo {{1}} {{2}}." }));
    render(<TemplateCatalog templates={[template()]} connections={OFFICIAL} />);

    await user.click(
      screen.getByRole("button", { name: "Editar zz_teste_um" }),
    );
    await user.clear(corpo());
    await digitar(user, corpo(), "Novo corpo {{1}} {{2}}.");
    await user.click(gravar());

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0]).toStrictEqual([
      "/canais/templates/zz_teste_um",
      {
        method: "PUT",
        body: {
          category: "utility",
          language: "pt_BR",
          variables: ["data_observada", "horario"],
          body: "Novo corpo {{1}} {{2}}.",
          meta_template_name: "zz_teste_um_v1",
          active: true,
        },
      },
    ]);
  });

  it("espaço nas pontas do código e das variáveis é tirado antes de validar e enviar", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(template({ code: "zz_teste_novo" }));
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user, {
      code: " zz_teste_novo ",
      variables: [" data_observada "],
    });
    await user.click(gravar());

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0][0]).toBe("/canais/templates/zz_teste_novo");
    expect(request.mock.calls[0][1].body.variables).toStrictEqual([
      "data_observada",
    ]);
  });

  it("sucesso → 'gravado', `router.refresh()`, e o formulário volta ao zero", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(template({ code: "zz_teste_novo" }));
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user, { code: "zz_teste_novo" });
    await user.click(gravar());

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Template zz_teste_novo gravado.",
    );
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(codigo()).toHaveValue("");
    expect(corpo()).toHaveValue("");
  });

  it("sucesso ao editar volta ao formulário de criação", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(template());
    render(<TemplateCatalog templates={[template()]} connections={OFFICIAL} />);

    await user.click(
      screen.getByRole("button", { name: "Editar zz_teste_um" }),
    );
    await user.click(gravar());

    await screen.findByRole("status");
    expect(
      screen.getByRole("heading", { name: "Novo template" }),
    ).toBeVisible();
    expect(codigo()).not.toHaveAttribute("readonly");
  });

  it("o botão fica desabilitado enquanto a API responde", async () => {
    const user = userEvent.setup();
    let resolve: (row: TemplateRow) => void = () => {};
    request.mockReturnValue(
      new Promise<TemplateRow>((done) => {
        resolve = done;
      }),
    );
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user);
    await user.click(gravar());

    const busy = await screen.findByRole("button", { name: "Gravando…" });
    expect(busy).toBeDisabled();

    resolve(template({ code: "zz_teste_novo" }));
    expect(
      await screen.findByRole("button", { name: "Gravar template" }),
    ).toBeEnabled();
  });
});

describe("critério 5 — a recusa da API como veio, e o que foi digitado fica", () => {
  it("⛔ 422 `template_body` → a frase do gatilho, literal, e os valores nos campos", async () => {
    // Uma frase que o Python nunca geraria: se aparecer, veio do `detail`.
    const user = userEvent.setup();
    request.mockRejectedValue(
      new ApiError(
        422,
        "Template zz_teste_novo declara a variável 2 (horario) mas o corpo não usa {{2}}.",
      ),
    );
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user, {
      variables: ["data_observada", "horario"],
      body: "Só {{1}}.",
    });
    await user.click(gravar());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Template zz_teste_novo declara a variável 2 (horario) mas o corpo não usa {{2}}.",
    );
    expect(corpo()).toHaveValue("Só {{1}}.");
    expect(variavel(2)).toHaveValue("horario");
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("403 → o `detail` da API", async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(
      new ApiError(403, "Editar template é do administrador do cliente."),
    );
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user);
    await user.click(gravar());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Editar template é do administrador do cliente.",
    );
  });

  it("500 sem `detail` → a mensagem padrão, e o formulário continua de pé", async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(new ApiError(500, null));
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user);
    await user.click(gravar());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não consegui gravar o template.",
    );
    expect(gravar()).toBeEnabled();
    expect(codigo()).toHaveValue("zz_teste_novo");
  });

  it("um sucesso antigo some quando o envio seguinte é recusado", async () => {
    const user = userEvent.setup();
    request
      .mockResolvedValueOnce(template({ code: "zz_teste_novo" }))
      .mockRejectedValueOnce(new ApiError(422, "recusado na segunda"));
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    await preencher(user);
    await user.click(gravar());
    await screen.findByRole("status");

    await preencher(user, { code: "zz_teste_outro" });
    await user.click(gravar());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "recusado na segunda",
    );
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("um erro antigo some ao clicar em 'Editar'", async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(new ApiError(422, "recusado"));
    render(<TemplateCatalog templates={[template()]} connections={OFFICIAL} />);

    await preencher(user);
    await user.click(gravar());
    await screen.findByRole("alert");

    await user.click(
      screen.getByRole("button", { name: "Editar zz_teste_um" }),
    );

    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("critério 6 — o botão 'Sincronizar' existe pelas flags, nunca pelo nome", () => {
  it("`requires_templates: true` → o botão está lá, e a frase não", () => {
    render(<TemplateCatalog templates={[]} connections={OFFICIAL} />);

    expect(sincronizar()).toBeVisible();
    expect(screen.queryByText(SYNC_PHRASE)).toBeNull();
  });

  it("`requires_templates: false` → a frase no lugar do botão", () => {
    render(<TemplateCatalog templates={[]} connections={UNOFFICIAL} />);

    expect(sincronizar()).toBeNull();
    expect(screen.getByText(SYNC_PHRASE)).toBeVisible();
    expect(screen.getByText(/o corpo local é o que sai/)).toBeVisible();
  });

  it("`connections === null` → a frase, sem botão", () => {
    render(<TemplateCatalog templates={[]} connections={null} />);

    expect(sincronizar()).toBeNull();
    expect(screen.getByText(SYNC_PHRASE)).toBeVisible();
  });

  it("sem provedor (`capabilities: null`) → a frase, sem botão", () => {
    render(
      <TemplateCatalog
        templates={[]}
        connections={{ ...OFFICIAL, provider: null, capabilities: null }}
      />,
    );

    expect(sincronizar()).toBeNull();
    expect(screen.getByText(SYNC_PHRASE)).toBeVisible();
  });

  it("⛔ flags invertidas: nome oficial com flags de não oficial não ganha botão", () => {
    // Um `provider === "…"` passaria nos casos acima e cai aqui.
    render(
      <TemplateCatalog
        templates={[]}
        connections={{ ...OFFICIAL, capabilities: UNOFFICIAL.capabilities }}
      />,
    );

    expect(sincronizar()).toBeNull();
    expect(screen.getByText(SYNC_PHRASE)).toBeVisible();
  });

  it("⛔ … e o par: nome não oficial com flags do oficial ganha o botão", () => {
    render(
      <TemplateCatalog
        templates={[]}
        connections={{ ...UNOFFICIAL, capabilities: OFFICIAL.capabilities }}
      />,
    );

    expect(sincronizar()).toBeVisible();
    expect(screen.queryByText(SYNC_PHRASE)).toBeNull();
  });
});

describe("critério 7 — sincronizar: POST sem corpo, o resultado como veio", () => {
  const RESULT: TemplateSyncResult = {
    provider: "meta_cloud",
    meta_total: 4,
    updated: ["zz_teste_um", "zz_teste_dois"],
    unmatched: [],
    synced_at: "2026-09-15T13:05:00Z",
  };

  it("✅ sucesso → POST sem corpo, 'N templates na WABA · K atualizados', e refresh", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(RESULT);
    render(<TemplateCatalog templates={[template()]} connections={OFFICIAL} />);

    await user.click(sincronizar() as HTMLElement);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "4 templates na WABA · 2 atualizados",
    );
    expect(request.mock.calls[0]).toStrictEqual([
      "/canais/templates/sincronizar",
      { method: "POST" },
    ]);
    expect(JSON.stringify(request.mock.calls[0])).not.toMatch(/tenant/i);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/sem par na WABA/)).toBeNull();
  });

  it("os sem par na WABA aparecem nomeados", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue({
      ...RESULT,
      meta_total: 1,
      updated: ["zz_teste_um"],
      unmatched: ["zz_orfao_a", "zz_orfao_b"],
    });
    render(<TemplateCatalog templates={[template()]} connections={OFFICIAL} />);

    await user.click(sincronizar() as HTMLElement);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "1 template na WABA · 1 atualizado · sem par na WABA: zz_orfao_a, zz_orfao_b",
    );
  });

  it("⛔ 422 `no_official_provider` → o `detail` como veio, sem refresh", async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(
      new ApiError(
        422,
        "A sincronização só existe para a Cloud API da Meta; o canal ativo não é ela.",
      ),
    );
    render(<TemplateCatalog templates={[template()]} connections={OFFICIAL} />);

    await user.click(sincronizar() as HTMLElement);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A sincronização só existe para a Cloud API da Meta; o canal ativo não é ela.",
    );
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("erro sem `detail` → a mensagem padrão", async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(new ApiError(502, null));
    render(<TemplateCatalog templates={[template()]} connections={OFFICIAL} />);

    await user.click(sincronizar() as HTMLElement);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não consegui sincronizar com a Meta.",
    );
  });

  it("enquanto consulta a WABA o botão diz isso e fica desabilitado", async () => {
    const user = userEvent.setup();
    let resolve: (result: TemplateSyncResult) => void = () => {};
    request.mockReturnValue(
      new Promise<TemplateSyncResult>((done) => {
        resolve = done;
      }),
    );
    render(<TemplateCatalog templates={[template()]} connections={OFFICIAL} />);

    await user.click(sincronizar() as HTMLElement);

    const busy = await screen.findByRole("button", {
      name: "Consultando a WABA…",
    });
    expect(busy).toBeDisabled();

    resolve(RESULT);
    expect(await screen.findByRole("status")).toBeVisible();
    expect(sincronizar()).toBeEnabled();
  });

  it("um erro antigo some ao sincronizar de novo com sucesso", async () => {
    const user = userEvent.setup();
    request
      .mockRejectedValueOnce(new ApiError(422, "sem credencial"))
      .mockResolvedValueOnce(RESULT);
    render(<TemplateCatalog templates={[template()]} connections={OFFICIAL} />);

    await user.click(sincronizar() as HTMLElement);
    await screen.findByRole("alert");

    await user.click(sincronizar() as HTMLElement);

    await screen.findByRole("status");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
