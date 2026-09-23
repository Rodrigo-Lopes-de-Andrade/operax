import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Contacts } from "@/components/canais/contacts";
import type { UnitChoice } from "@/components/dp/work-posts";
import { ApiError } from "@/lib/api";
import type { ContactRow } from "@/lib/canais/regras";

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

const UNIT_A = "11111111-1111-4111-8111-111111111111";
const UNIT_B = "22222222-2222-4222-8222-222222222222";

const UNITS: UnitChoice[] = [
  { id: UNIT_A, name: "Unidade Zz Alfa" },
  { id: UNIT_B, name: "Unidade Zz Beta" },
];

/** Nomes que nenhum contato real tem: a linha só aparece se vier da prop. */
function contato(overrides: Partial<ContactRow> = {}): ContactRow {
  return {
    id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    name: "Zz Pessoa",
    whatsapp: "5511999990000",
    email: "zz@fastpark.dev",
    type: "person",
    active: true,
    units: [
      {
        unit_id: UNIT_A,
        unit_name: "Unidade Zz Alfa",
        responsibility: "unit_manager",
        is_primary: true,
      },
    ],
    ...overrides,
  };
}

const GRUPO = contato({
  id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  name: "Zz Grupo",
  type: "whatsapp_group",
  email: null,
  units: [],
});

const INATIVO = contato({
  id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
  name: "Zz Inativa",
  active: false,
  units: [],
});

/** O 409 de `desativar` e de `PUT /unidades`, como o backend o escreve. */
function segurado(code: string, detail: string) {
  return new ApiError(409, detail, code, {
    detail,
    code,
    rules: [
      { id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd", name: "Regra Zz Um" },
      { id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", name: "Regra Zz Dois" },
    ],
  });
}

function lista() {
  return within(screen.getByRole("list", { name: "Contatos do cliente" }));
}

beforeEach(() => {
  request.mockReset();
  refresh.mockClear();
});

describe("a lista", () => {
  it("mostra cada contato com tipo, endereços, unidades — e o inativo aparece, marcado", () => {
    render(<Contacts contacts={[contato(), GRUPO, INATIVO]} units={UNITS} />);

    const itens = lista().getAllByRole("listitem");
    // Três contatos, mais a linha da matriz de quem tem unidade.
    expect(itens.length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("Zz Pessoa")).toBeVisible();
    // Os três fixtures partilham o número e o e-mail: o que se prende é que
    // os endereços estão na tela, em claro.
    expect(screen.getAllByText("5511999990000")[0]).toBeVisible();
    expect(screen.getAllByText("zz@fastpark.dev")[0]).toBeVisible();
    expect(
      screen.getByText("Unidade Zz Alfa · Gestor da unidade (primário)"),
    ).toBeVisible();
    expect(screen.getByText("Grupo de WhatsApp")).toBeVisible();
    // ⛔ O inativo está na lista, marcado — nunca some.
    expect(screen.getByText("Zz Inativa")).toBeVisible();
    expect(screen.getByText("Inativo")).toBeVisible();
    // … e não tem botão de desativar de novo.
    expect(
      screen.queryByRole("button", { name: "Desativar Zz Inativa" }),
    ).toBeNull();
  });

  it("⛔ a palavra 'excluir' não existe nesta tela — um contato desativa, nunca some", () => {
    render(<Contacts contacts={[contato(), GRUPO]} units={UNITS} />);

    expect(screen.queryByText(/exclu/i)).toBeNull();
    expect(
      screen.getByRole("button", { name: "Desativar Zz Pessoa" }),
    ).toBeVisible();
  });

  it("vazio mostra o estado vazio, e o botão de novo contato continua lá", () => {
    render(<Contacts contacts={[]} units={UNITS} />);

    expect(screen.getByText("Nenhum contato neste cliente")).toBeVisible();
    expect(screen.getByRole("button", { name: "Novo contato" })).toBeVisible();
  });
});

describe("o formulário de contato — `ContactWrite`", () => {
  it("⛔ exige ao menos um endereço: sem WhatsApp e sem e-mail nada é enviado", async () => {
    const user = userEvent.setup();
    render(<Contacts contacts={[]} units={UNITS} />);

    await user.click(screen.getByRole("button", { name: "Novo contato" }));
    await user.type(screen.getByLabelText("Nome"), "Zz Nova");
    await user.click(screen.getByRole("button", { name: "Gravar contato" }));

    expect(
      await screen.findByText(
        "informe ao menos um endereço: WhatsApp ou e-mail",
      ),
    ).toBeVisible();
    expect(request).not.toHaveBeenCalled();
  });

  it("a nota da regra 7 fica ao lado do seletor de tipo, e os três tipos têm rótulo pt-BR", async () => {
    const user = userEvent.setup();
    render(<Contacts contacts={[]} units={UNITS} />);

    await user.click(screen.getByRole("button", { name: "Novo contato" }));

    expect(
      screen.getByText(
        "Um grupo de WhatsApp só recebe regra agregada: conteúdo individual nunca vai para grupo.",
      ),
    ).toBeVisible();
    expect(
      within(screen.getByLabelText("Tipo"))
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Pessoa", "Grupo de WhatsApp", "Lista de e-mail"]);
  });

  it("✅ cria com o corpo do contrato: vazio vira nulo, `type` é o valor, e nada de `active`", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(contato({ name: "Zz Nova" }));
    render(<Contacts contacts={[]} units={UNITS} />);

    await user.click(screen.getByRole("button", { name: "Novo contato" }));
    await user.type(screen.getByLabelText("Nome"), "Zz Nova");
    await user.selectOptions(screen.getByLabelText("Tipo"), "email_list");
    await user.type(screen.getByLabelText("E-mail"), "nova@fastpark.dev");
    await user.click(screen.getByRole("button", { name: "Gravar contato" }));

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request).toHaveBeenCalledWith("/canais/destinatarios/contatos", {
      method: "POST",
      body: {
        name: "Zz Nova",
        whatsapp: null,
        email: "nova@fastpark.dev",
        type: "email_list",
      },
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Contato Zz Nova gravado.",
    );
    expect(refresh).toHaveBeenCalled();
  });

  it("o WhatsApp fora do E.164 é recusado na tela, antes de mandar", async () => {
    const user = userEvent.setup();
    render(<Contacts contacts={[]} units={UNITS} />);

    await user.click(screen.getByRole("button", { name: "Novo contato" }));
    await user.type(screen.getByLabelText("Nome"), "Zz Nova");
    await user.type(screen.getByLabelText("WhatsApp"), "11 99999-0000");
    await user.click(screen.getByRole("button", { name: "Gravar contato" }));

    expect(
      await screen.findByText(/número no formato internacional/),
    ).toBeVisible();
    expect(request).not.toHaveBeenCalled();
  });

  it("editar abre com a linha preenchida e grava em `PUT /contatos/{id}`; o `detail` de um 422 aparece como veio", async () => {
    const user = userEvent.setup();
    const detail =
      "Um grupo de WhatsApp só pode ter a responsabilidade «group» na unidade — zz.";
    request.mockRejectedValue(
      new ApiError(422, detail, "group_responsibility", {
        detail,
        code: "group_responsibility",
      }),
    );
    render(<Contacts contacts={[contato()]} units={UNITS} />);

    await user.click(screen.getByRole("button", { name: "Editar Zz Pessoa" }));
    expect(screen.getByLabelText("Nome")).toHaveValue("Zz Pessoa");
    await user.selectOptions(screen.getByLabelText("Tipo"), "whatsapp_group");
    await user.click(screen.getByRole("button", { name: "Gravar contato" }));

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0][0]).toBe(
      "/canais/destinatarios/contatos/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    );
    expect(request.mock.calls[0][1]).toMatchObject({ method: "PUT" });
    expect(await screen.findByRole("alert")).toHaveTextContent(detail);
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("desativar — confirmação em texto, e o 409 que lista as regras", () => {
  it("⛔ pede confirmação antes de qualquer chamada, e a confirmação é um POST em `/desativar`", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(contato({ active: false }));
    render(<Contacts contacts={[contato()]} units={UNITS} />);

    await user.click(
      screen.getByRole("button", { name: "Desativar Zz Pessoa" }),
    );
    expect(request).not.toHaveBeenCalled();
    expect(
      screen.getByText(/continua na lista, marcado como inativo/),
    ).toBeVisible();

    await user.click(
      screen.getByRole("button", { name: "Confirmar desativação" }),
    );

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request).toHaveBeenCalledWith(
      "/canais/destinatarios/contatos/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/desativar",
      { method: "POST" },
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Contato Zz Pessoa desativado.",
    );
  });

  it("⛔ 409 `contact_in_active_rule`: a frase do backend e as regras, cada uma com link para Regras", async () => {
    const user = userEvent.setup();
    const detail =
      "Este contato é destino de regra ligada. Troque o destino nas regras listadas — ou desligue-as — antes de desativá-lo.";
    request.mockRejectedValue(segurado("contact_in_active_rule", detail));
    render(<Contacts contacts={[contato()]} units={UNITS} />);

    await user.click(
      screen.getByRole("button", { name: "Desativar Zz Pessoa" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Confirmar desativação" }),
    );

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent(detail);
    const regras = within(alerta).getByRole("list", {
      name: "Regras que seguram o contato",
    });
    expect(
      within(regras)
        .getAllByRole("link")
        .map((link) => [link.textContent, link.getAttribute("href")]),
    ).toEqual([
      [
        "Regra Zz Um",
        "/dashboard/administracao/regras#regra-dddddddd-dddd-4ddd-8ddd-dddddddddddd",
      ],
      [
        "Regra Zz Dois",
        "/dashboard/administracao/regras#regra-eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
      ],
    ]);
    // Nada mudou: a lista continua, e o contato não foi marcado.
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.queryByText("Inativo")).toBeNull();
  });

  it("… e o 409 `contact_last_responsible` tem a mesma renderização — com a frase dele", async () => {
    const user = userEvent.setup();
    const detail =
      "Este contato é o único responsável ativo que resolve o destino por responsabilidade de regra ligada. Cadastre outro responsável na unidade — ou desligue as regras listadas — antes.";
    request.mockRejectedValue(segurado("contact_last_responsible", detail));
    render(<Contacts contacts={[contato()]} units={UNITS} />);

    await user.click(
      screen.getByRole("button", { name: "Desativar Zz Pessoa" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Confirmar desativação" }),
    );

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent(detail);
    expect(within(alerta).getAllByRole("link")).toHaveLength(2);
  });
});

describe("a matriz unidade × responsabilidade — `PUT /unidades`", () => {
  it("✅ abre com as linhas atuais, e grava a matriz inteira com `unit_id`, `responsibility` e `is_primary`", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(contato());
    render(<Contacts contacts={[contato()]} units={UNITS} />);

    await user.click(
      screen.getByRole("button", { name: "Unidades de Zz Pessoa" }),
    );
    expect(screen.getByLabelText("Unidade")).toHaveValue(UNIT_A);
    expect(screen.getByLabelText("Responsabilidade")).toHaveValue(
      "unit_manager",
    );
    expect(screen.getByLabelText("Primário")).toBeChecked();

    await user.click(screen.getByRole("button", { name: "adicionar unidade" }));
    const unidades = screen.getAllByLabelText("Unidade");
    await user.selectOptions(unidades[1], UNIT_B);
    await user.selectOptions(
      screen.getAllByLabelText("Responsabilidade")[1],
      "hr",
    );
    await user.click(screen.getByRole("button", { name: "Gravar unidades" }));

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request).toHaveBeenCalledWith(
      "/canais/destinatarios/contatos/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/unidades",
      {
        method: "PUT",
        body: {
          units: [
            {
              unit_id: UNIT_A,
              responsibility: "unit_manager",
              is_primary: true,
            },
            { unit_id: UNIT_B, responsibility: "hr", is_primary: false },
          ],
        },
      },
    );
  });

  it("as responsabilidades têm os seis valores em pt-BR para uma pessoa", async () => {
    const user = userEvent.setup();
    render(<Contacts contacts={[contato()]} units={UNITS} />);

    await user.click(
      screen.getByRole("button", { name: "Unidades de Zz Pessoa" }),
    );

    expect(
      within(screen.getByLabelText("Responsabilidade"))
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual([
      "Gestor da unidade",
      "Supervisor regional",
      "Departamento pessoal",
      "RH",
      "Diretoria",
      "Grupo",
    ]);
  });

  it("⛔ para um grupo de WhatsApp a tela só oferece «Grupo» — o 422 `group_responsibility` nem chega a existir", async () => {
    const user = userEvent.setup();
    render(<Contacts contacts={[GRUPO]} units={UNITS} />);

    await user.click(
      screen.getByRole("button", { name: "Unidades de Zz Grupo" }),
    );
    await user.click(screen.getByRole("button", { name: "adicionar unidade" }));

    expect(
      within(screen.getByLabelText("Responsabilidade"))
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Grupo"]);
  });

  it("a mesma responsabilidade na mesma unidade duas vezes é recusada na tela", async () => {
    const user = userEvent.setup();
    render(<Contacts contacts={[contato()]} units={UNITS} />);

    await user.click(
      screen.getByRole("button", { name: "Unidades de Zz Pessoa" }),
    );
    await user.click(screen.getByRole("button", { name: "adicionar unidade" }));
    await user.selectOptions(screen.getAllByLabelText("Unidade")[1], UNIT_A);
    await user.click(screen.getByRole("button", { name: "Gravar unidades" }));

    expect(
      await screen.findByText(
        "a mesma responsabilidade na mesma unidade aparece duas vezes",
      ),
    ).toBeVisible();
    expect(request).not.toHaveBeenCalled();
  });

  it("⛔ o 409 `contact_last_responsible` também pode vir daqui, e lista as regras do mesmo jeito", async () => {
    const user = userEvent.setup();
    const detail = "Este contato é o único responsável ativo — zz.";
    request.mockRejectedValue(segurado("contact_last_responsible", detail));
    render(<Contacts contacts={[contato()]} units={UNITS} />);

    await user.click(
      screen.getByRole("button", { name: "Unidades de Zz Pessoa" }),
    );
    await user.click(screen.getByRole("button", { name: "remover linha 1" }));
    await user.click(screen.getByRole("button", { name: "Gravar unidades" }));

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent(detail);
    expect(
      within(alerta).getByRole("link", { name: "Regra Zz Um" }),
    ).toHaveAttribute(
      "href",
      "/dashboard/administracao/regras#regra-dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    );
    expect(refresh).not.toHaveBeenCalled();
  });
});
