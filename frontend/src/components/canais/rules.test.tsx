import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DOCTRINE, Rules, TEST_NOTE } from "@/components/canais/rules";
import type { UnitChoice } from "@/components/dp/work-posts";
import { ApiError } from "@/lib/api";
import type { TemplateRow } from "@/lib/canais/queries";
import type {
  AlertRuleRow,
  ContactRow,
  RuleTestResult,
} from "@/lib/canais/regras";

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
const RULE_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";

const UNIT_B = "22222222-2222-4222-8222-222222222222";
const UNITS: UnitChoice[] = [
  { id: UNIT_A, name: "Unidade Zz Alfa" },
  { id: UNIT_B, name: "Unidade Zz Beta" },
];

/** Códigos que nenhum tipo real tem: o rótulo só aparece se vier do catálogo. */
const TEMPLATES: TemplateRow[] = [
  {
    code: "zz_template",
    category: "utility",
    language: "pt_BR",
    variables: ["unidade"],
    body: "Zz {{1}}",
    meta_template_name: null,
    meta_status: "approved",
    meta_rejection: null,
    active: true,
    updated_at: "2026-09-15T13:05:00Z",
  },
  {
    code: "zz_inativo",
    category: "utility",
    language: "pt_BR",
    variables: ["unidade"],
    body: "Zz {{1}}",
    meta_template_name: null,
    meta_status: "draft",
    meta_rejection: null,
    active: false,
    updated_at: "2026-09-15T13:05:00Z",
  },
];

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

const PESSOA = contato();
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
const CONTATOS = [PESSOA, GRUPO, INATIVO];

function regra(overrides: Partial<AlertRuleRow> = {}): AlertRuleRow {
  return {
    id: RULE_ID,
    name: "Regra Zz",
    deviation_type: null,
    scope_unit_id: UNIT_A,
    scope_unit_name: "Unidade Zz Alfa",
    content: "aggregate",
    channel: "whatsapp",
    cron_window: null,
    threshold_minutes: null,
    threshold_occurrences: null,
    muted_until: null,
    template_code: "zz_template",
    active: false,
    targets: [],
    blocked_reason: null,
    ...overrides,
  };
}

/**
 * Um silêncio que não vence com o calendário: a insígnia só aparece enquanto
 * `muted_until` é futuro, então uma data próxima viraria um teste que passa
 * hoje e falha na semana que vem. 13:00 UTC é 10:00 em São Paulo.
 */
const SILENCIO_FUTURO = "2099-09-30T13:00:00Z";

/** Uma frase que a tela não tem como remontar: só aparece se vier da API. */
const RAZAO = "Zz motivo inventado pelo backend, com «aspas» e tudo.";

function abrir(
  rules: AlertRuleRow[],
  contacts: ContactRow[] | null = CONTATOS,
  templates: TemplateRow[] | null = TEMPLATES,
) {
  return render(
    <Rules
      rules={rules}
      contacts={contacts}
      units={UNITS}
      templates={templates}
      now={Date.now()}
    />,
  );
}

function opcoes(fieldset: string) {
  return within(screen.getByRole("group", { name: fieldset }))
    .queryAllByRole("checkbox")
    .map((box) => box.closest("label")?.textContent?.trim());
}

beforeEach(() => {
  request.mockReset();
  refresh.mockClear();
});

describe("a doutrina do S6 e a lista", () => {
  it("a linha fixa está no topo, e o texto do teste está antes de qualquer clique", () => {
    abrir([regra()]);

    expect(screen.getByText(DOCTRINE)).toBeVisible();
    expect(screen.getByText(TEST_NOTE)).toBeVisible();
    expect(screen.getByText(/Ligada não quer dizer entregando/)).toBeVisible();
  });

  it("mostra a regra com o rótulo do catálogo, a unidade, o conteúdo, o canal, o template e ligada/desligada", () => {
    abrir([
      regra(),
      regra({
        id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        name: "Regra Zz Ligada",
        deviation_type: null,
        scope_unit_id: null,
        scope_unit_name: null,
        channel: "both",
        active: true,
        muted_until: SILENCIO_FUTURO,
        targets: [
          {
            id: "t1",
            contact_id: PESSOA.id,
            contact_name: "Zz Pessoa",
            contact_active: true,
            responsibility: null,
          },
          {
            id: "t2",
            contact_id: null,
            contact_name: null,
            contact_active: null,
            responsibility: "hr",
          },
        ],
      }),
    ]);

    const lista = within(
      screen.getByRole("list", { name: "Regras de alerta" }),
    );
    // Nem o rótulo nem o código do tipo aparecem: o outbox não filtra por ele,
    // e mostrá-lo ao lado da regra afirmaria um recorte que a entrega não faz.
    expect(lista.queryByText(/Atraso Zz/)).toBeNull();
    expect(lista.queryByText(/zz_late/)).toBeNull();
    expect(lista.queryByText(/Todo tipo de desvio/)).toBeNull();
    expect(lista.getByText(/todas as unidades/)).toBeVisible();
    expect(lista.getByText(/Mensageria e e-mail/)).toBeVisible();
    expect(lista.getByText("Desligada")).toBeVisible();
    expect(lista.getByText("Ligada")).toBeVisible();
    // 13:00 UTC é 10:00 em São Paulo — o silêncio sai no fuso do tenant.
    expect(lista.getByText("silêncio até 30/09/2099 10:00")).toBeVisible();
    expect(lista.getByText("Zz Pessoa")).toBeVisible();
    expect(lista.getByText(/por responsabilidade: RH/)).toBeVisible();
    // Ninguém na matriz é RH: a linha diz isso, ao lado do destino.
    expect(
      lista.getByText(/ninguém ativo com esta responsabilidade na matriz/),
    ).toBeVisible();
  });

  it("⛔ o alcance do destino por responsabilidade é contado POR UNIDADE", () => {
    // Um gestor ativo só na Alfa. A regra de TODAS as unidades cobre duas, e
    // resolve numa: o outbox procura o responsável na unidade do ciclo, uma de
    // cada vez, então "existe alguém em alguma unidade" seria silêncio onde a
    // Beta entrega a ninguém.
    const soNaAlfa = contato({ id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee" });
    const porResponsabilidade = [
      {
        id: "t1",
        contact_id: null,
        contact_name: null,
        contact_active: null,
        responsibility: "unit_manager" as const,
      },
    ];

    const todas = abrir(
      [
        regra({
          scope_unit_id: null,
          scope_unit_name: null,
          targets: porResponsabilidade,
        }),
      ],
      [soNaAlfa],
    );
    expect(screen.getByText(/resolve em 1 de 2 unidades/)).toBeVisible();
    expect(
      screen.queryByText(/ninguém ativo com esta responsabilidade/),
    ).toBeNull();
    todas.unmount();

    // A mesma matriz, recortada na Beta: ninguém resolve lá.
    const beta = abrir(
      [
        regra({
          scope_unit_id: UNIT_B,
          scope_unit_name: "Unidade Zz Beta",
          targets: porResponsabilidade,
        }),
      ],
      [soNaAlfa],
    );
    expect(
      screen.getByText(/ninguém ativo com esta responsabilidade na matriz/),
    ).toBeVisible();
    beta.unmount();

    // Coberta em todas: nenhum aviso — o silêncio aqui é o certo.
    abrir(
      [
        regra({
          scope_unit_id: null,
          scope_unit_name: null,
          targets: porResponsabilidade,
        }),
      ],
      [
        soNaAlfa,
        contato({
          id: "ffffffff-ffff-4fff-8fff-ffffffffffff",
          name: "Zz Gestora da Beta",
          units: [
            {
              unit_id: UNIT_B,
              unit_name: "Unidade Zz Beta",
              responsibility: "unit_manager",
              is_primary: true,
            },
          ],
        }),
      ],
    );
    expect(screen.queryByText(/resolve em/)).toBeNull();
    expect(
      screen.queryByText(/ninguém ativo com esta responsabilidade/),
    ).toBeNull();
  });

  it("⛔ silêncio vencido não é insígnia de silêncio", () => {
    // O outbox entrega quando `muted_until <= now()`; a coluna só some no
    // próximo PUT. A tela lê o relógio, como o banco.
    const passado = abrir([
      regra({ muted_until: "2020-01-01T13:00:00+00:00" }),
    ]);
    expect(screen.queryByText(/silêncio até/)).toBeNull();
    passado.unmount();

    abrir([regra({ muted_until: SILENCIO_FUTURO })]);
    expect(screen.getByText(/silêncio até 30\/09\/2099/)).toBeVisible();
  });

  it("⛔ `blocked_reason` é renderizado como veio — nunca remontado aqui", () => {
    abrir([regra({ active: true, blocked_reason: RAZAO })]);

    expect(screen.getByText(RAZAO)).toBeVisible();
  });

  it("… e nulo é silêncio: nenhuma frase de bloqueio inventada", () => {
    abrir([regra({ active: true, blocked_reason: null })]);

    expect(screen.queryByText(/Nenhum destino ativo/)).toBeNull();
    expect(screen.queryByText(/Sem template/)).toBeNull();
  });

  it("vazio mostra o estado vazio, e a doutrina continua no topo", () => {
    abrir([]);

    expect(screen.getByText("Nenhuma regra neste cliente")).toBeVisible();
    expect(screen.getByText(DOCTRINE)).toBeVisible();
  });
});

describe("gate 1 — a regra 7 antes do clique, em Destinos", () => {
  it("⛔ regra individual: nem o grupo de WhatsApp nem a responsabilidade «Grupo» são oferecidos", async () => {
    const user = userEvent.setup();
    abrir([regra({ content: "individual" })]);

    await user.click(
      screen.getByRole("button", { name: "Destinos de Regra Zz" }),
    );

    expect(opcoes("Contatos")).toEqual(["Zz Pessoa"]);
    expect(opcoes("Por responsabilidade")).toEqual([
      "Gestor da unidade",
      "Supervisor regional",
      "Departamento pessoal",
      "RH",
      "Diretoria",
    ]);
    expect(
      screen.getByText(/conteúdo individual nunca vai para grupo/),
    ).toBeVisible();
  });

  it("✅ regra agregada: o grupo e a responsabilidade «Grupo» aparecem; o contato inativo não, em nenhuma", async () => {
    const user = userEvent.setup();
    abrir([regra({ content: "aggregate" })]);

    await user.click(
      screen.getByRole("button", { name: "Destinos de Regra Zz" }),
    );

    expect(opcoes("Contatos")).toEqual(["Zz Pessoa", "Zz Grupo"]);
    expect(opcoes("Por responsabilidade")).toContain("Grupo");
    expect(opcoes("Contatos")).not.toContain("Zz Inativa");
  });

  it("grava os destinos em `PUT /destinos`, cada um com exatamente um dos dois campos", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(regra());
    abrir([regra()]);

    await user.click(
      screen.getByRole("button", { name: "Destinos de Regra Zz" }),
    );
    await user.click(screen.getByRole("checkbox", { name: "Zz Grupo" }));
    await user.click(
      screen.getByRole("checkbox", { name: "Gestor da unidade" }),
    );
    await user.click(screen.getByRole("button", { name: "Gravar destinos" }));

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request).toHaveBeenCalledWith(`/canais/regras/${RULE_ID}/destinos`, {
      method: "PUT",
      body: {
        targets: [
          { contact_id: GRUPO.id, responsibility: null },
          { contact_id: null, responsibility: "unit_manager" },
        ],
      },
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("o 409 do gatilho (`individual_to_group`) vira a frase dele, e nada muda", async () => {
    const user = userEvent.setup();
    const detail =
      "regra individual não aceita destino de grupo — zz frase do gatilho";
    request.mockRejectedValue(
      new ApiError(409, detail, "individual_to_group", {
        detail,
        code: "individual_to_group",
      }),
    );
    abrir([regra({ content: "individual" })]);

    await user.click(
      screen.getByRole("button", { name: "Destinos de Regra Zz" }),
    );
    await user.click(screen.getByRole("checkbox", { name: "Zz Pessoa" }));
    await user.click(screen.getByRole("button", { name: "Gravar destinos" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(detail);
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("gate 2 — o modo de teste do S6 como botão", () => {
  it("⛔ o botão existe em regra DESLIGADA — o teste vem antes de ligar", () => {
    abrir([regra({ active: false })]);

    expect(
      screen.getByRole("button", { name: "Enviar teste para mim: Regra Zz" }),
    ).toBeEnabled();
    expect(screen.getByText(TEST_NOTE)).toBeVisible();
  });

  it("… e em regra ligada também", () => {
    abrir([regra({ active: true })]);

    expect(
      screen.getByRole("button", { name: "Enviar teste para mim: Regra Zz" }),
    ).toBeEnabled();
  });

  it("✅ o clique é um POST em `/testar`, e o resultado lista as metades enfileiradas com canal e provedor", async () => {
    const user = userEvent.setup();
    const result: RuleTestResult = {
      rule_id: RULE_ID,
      test_id: "ffffffff-ffff-4fff-8fff-ffffffffffff",
      contact_id: PESSOA.id,
      contact_name: "Zz Pessoa",
      queued: [
        { channel: "whatsapp", provider: "z_api" },
        { channel: "email", provider: null },
      ],
    };
    request.mockResolvedValue(result);
    abrir([regra()]);

    await user.click(
      screen.getByRole("button", { name: "Enviar teste para mim: Regra Zz" }),
    );

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request).toHaveBeenCalledWith(`/canais/regras/${RULE_ID}/testar`, {
      method: "POST",
    });
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(
      "Teste enfileirado para Zz Pessoa: WhatsApp via Z-API · E-mail.",
    );
    expect(status).toHaveTextContent(/fica esperando em Conexões/);
  });

  it("⛔ 409 `caller_has_no_contact` vira a frase do backend mais o link para Destinatários", async () => {
    const user = userEvent.setup();
    const detail =
      "Para testar, cadastre em Destinatários um contato do tipo pessoa com o seu e-mail (owner@fastpark.dev) e um número de WhatsApp — o teste vai para você.";
    request.mockRejectedValue(
      new ApiError(409, detail, "caller_has_no_contact", {
        detail,
        code: "caller_has_no_contact",
      }),
    );
    abrir([regra()]);

    await user.click(
      screen.getByRole("button", { name: "Enviar teste para mim: Regra Zz" }),
    );

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent(detail);
    expect(
      within(alerta).getByRole("link", { name: "Cadastrar em Destinatários" }),
    ).toHaveAttribute("href", "/dashboard/administracao/destinatarios");
  });

  it("⛔ o link sai do `code`, nunca da frase — nos dois sentidos", async () => {
    // O eixo declarado do contrato é o `code`. Ramificar pelo texto do
    // `detail` passaria despercebido enquanto as frases coincidissem — e
    // quebraria no dia em que o backend reescrevesse uma delas.
    const user = userEvent.setup();

    // 1. O código certo, com uma frase que NÃO cita Destinatários: link.
    const semACitacao = "Zz não há contato com o seu e-mail neste cliente.";
    request.mockRejectedValue(
      new ApiError(409, semACitacao, "caller_has_no_contact", {
        detail: semACitacao,
        code: "caller_has_no_contact",
      }),
    );
    const primeiro = abrir([regra()]);
    await user.click(
      screen.getByRole("button", { name: "Enviar teste para mim: Regra Zz" }),
    );
    let alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent(semACitacao);
    expect(
      within(alerta).getByRole("link", { name: "Cadastrar em Destinatários" }),
    ).toBeVisible();
    primeiro.unmount();

    // 2. Outro código, com uma frase que CITA Destinatários: sem link.
    const comACitacao =
      "Zz cadastre em Destinatários outra coisa — mas o código é outro.";
    request.mockRejectedValue(
      new ApiError(409, comACitacao, "no_channel", {
        detail: comACitacao,
        code: "no_channel",
      }),
    );
    abrir([regra()]);
    await user.click(
      screen.getByRole("button", { name: "Enviar teste para mim: Regra Zz" }),
    );
    alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent(comACitacao);
    expect(within(alerta).queryByRole("link")).toBeNull();
  });

  it("outro 409 do teste (`no_channel`) é só a frase — sem link", async () => {
    const user = userEvent.setup();
    const detail = "Nenhum canal de mensageria ativo — zz.";
    request.mockRejectedValue(
      new ApiError(409, detail, "no_channel", { detail, code: "no_channel" }),
    );
    abrir([regra()]);

    await user.click(
      screen.getByRole("button", { name: "Enviar teste para mim: Regra Zz" }),
    );

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent(detail);
    expect(within(alerta).queryByRole("link")).toBeNull();
  });
});

describe("o formulário de regra — `AlertRuleWrite`", () => {
  it("⛔ criar manda o corpo do contrato, NUNCA `active`, e os quatro inertes nulos", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(regra({ name: "Regra Zz Nova" }));
    abrir([]);

    await user.click(screen.getByRole("button", { name: "Nova regra" }));
    await user.type(screen.getByLabelText("Nome"), "Regra Zz Nova");
    await user.selectOptions(screen.getByLabelText("Unidade"), UNIT_A);
    await user.selectOptions(screen.getByLabelText("Conteúdo"), "aggregate");
    await user.selectOptions(screen.getByLabelText("Canal"), "both");
    await user.selectOptions(screen.getByLabelText("Template"), "zz_template");
    await user.click(screen.getByRole("button", { name: "Gravar regra" }));

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    const [path, options] = request.mock.calls[0] as [
      string,
      { method: string; body: Record<string, unknown> },
    ];
    expect(path).toBe("/canais/regras");
    expect(options.method).toBe("POST");
    expect(options.body).toEqual({
      name: "Regra Zz Nova",
      // ⛔ Os quatro que o outbox não lê vão NULOS, sempre: saíram da tela
      // porque nada os honra, e o contrato continua os aceitando.
      deviation_type: null,
      scope_unit_id: UNIT_A,
      content: "aggregate",
      channel: "both",
      cron_window: null,
      threshold_minutes: null,
      threshold_occurrences: null,
      template_code: "zz_template",
    });
    expect(options.body).not.toHaveProperty("active");
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Regra Zz Nova criada — desligada. Teste antes de ligar.",
    );
  });

  it("⛔ o formulário NÃO oferece os quatro campos que ninguém lê", async () => {
    // `deviation_type`, `cron_window`, `threshold_minutes` e
    // `threshold_occurrences` são gravados pela API e ignorados pelo
    // `outbox._TARGETS_SQL` — o `where` dele não cita nenhum deles. Oferecê-los
    // era prometer um recorte que a entrega não faz, e o gestor só descobriria
    // pelo alerta que não devia ter chegado. Voltam com quem os leia.
    const user = userEvent.setup();
    abrir([]);

    await user.click(screen.getByRole("button", { name: "Nova regra" }));

    for (const rotulo of [
      "Tipo de desvio",
      "Janela (opcional)",
      "Limiar em minutos (opcional)",
      "Limiar de ocorrências (opcional)",
    ]) {
      expect(screen.queryByLabelText(rotulo)).toBeNull();
    }
    // O que sobrou continua lá, e é o que de fato decide a entrega.
    expect(screen.getByLabelText("Unidade")).toBeVisible();
    expect(screen.getByLabelText("Canal")).toBeVisible();
    expect(
      within(screen.getByLabelText("Template"))
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Sem template", "zz_template · aprovado"]);
  });

  it("vazio é nulo no corpo: todo tipo, todas as unidades, sem template, na detecção", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(regra());
    abrir([]);

    await user.click(screen.getByRole("button", { name: "Nova regra" }));
    await user.type(screen.getByLabelText("Nome"), "Regra Zz");
    await user.click(screen.getByRole("button", { name: "Gravar regra" }));

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0][1]).toMatchObject({
      body: {
        deviation_type: null,
        scope_unit_id: null,
        template_code: null,
        cron_window: null,
        threshold_minutes: null,
        threshold_occurrences: null,
      },
    });
  });

  it("nome vazio é recusado na tela, antes de qualquer chamada", async () => {
    // Era o teste do limiar, que deixou de ter campo na tela. A validação do
    // formulário segue prendida pelo único obrigatório que sobrou.
    const user = userEvent.setup();
    abrir([]);

    await user.click(screen.getByRole("button", { name: "Nova regra" }));
    await user.click(screen.getByRole("button", { name: "Gravar regra" }));

    expect(await screen.findByText("Informe o nome.")).toBeVisible();
    expect(request).not.toHaveBeenCalled();
  });

  it("editar abre preenchida e grava em `PUT /regras/{id}`; o 409 de regra ligada aparece como veio", async () => {
    const user = userEvent.setup();
    const detail = "A regra não tem destino ativo — zz.";
    request.mockRejectedValue(
      new ApiError(409, detail, "rule_has_no_target", {
        detail,
        code: "rule_has_no_target",
      }),
    );
    abrir([regra({ active: true })]);

    await user.click(screen.getByRole("button", { name: "Editar Regra Zz" }));
    expect(screen.getByLabelText("Nome")).toHaveValue("Regra Zz");
    await user.click(screen.getByRole("button", { name: "Gravar regra" }));

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0][0]).toBe(`/canais/regras/${RULE_ID}`);
    expect(request.mock.calls[0][1]).toMatchObject({ method: "PUT" });
    expect(request.mock.calls[0][1].body).not.toHaveProperty("active");
    expect(await screen.findByRole("alert")).toHaveTextContent(detail);
  });

  it("catálogo de templates nulo: a tela fica em pé e o seletor diz que não pôde ler", async () => {
    const user = userEvent.setup();
    abrir([], CONTATOS, null);

    await user.click(screen.getByRole("button", { name: "Nova regra" }));

    expect(
      screen.getByText("O catálogo de templates não pôde ser lido agora."),
    ).toBeVisible();
  });
});

describe("ligar e desligar — é o backend que julga", () => {
  it("✅ ligar é um POST em `/ligar`; o 409 nomeado vira a frase do `detail`", async () => {
    const user = userEvent.setup();
    const detail =
      "A mensageria exige um template do catálogo. Escolha um em Templates antes de ligar.";
    request.mockRejectedValue(
      new ApiError(409, detail, "template_required", {
        detail,
        code: "template_required",
      }),
    );
    abrir([regra({ template_code: null })]);

    await user.click(screen.getByRole("button", { name: "Ligar Regra Zz" }));

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request).toHaveBeenCalledWith(`/canais/regras/${RULE_ID}/ligar`, {
      method: "POST",
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(detail);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("regra ligada tem Desligar, não Ligar; desligar é um POST em `/desligar`", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(regra({ active: false }));
    abrir([regra({ active: true })]);

    expect(screen.queryByRole("button", { name: "Ligar Regra Zz" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Desligar Regra Zz" }));

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request).toHaveBeenCalledWith(`/canais/regras/${RULE_ID}/desligar`, {
      method: "POST",
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Regra Regra Zz desligada.",
    );
    expect(refresh).toHaveBeenCalled();
  });

  it("⛔ com `blocked_reason` presente a razão fica ao lado, e o botão de ligar não é escondido", () => {
    // O backend só devolve `blocked_reason` em regra ligada; se um dia vier
    // numa desligada, a tela mostra a razão e deixa o backend julgar o clique.
    abrir([regra({ active: false, blocked_reason: RAZAO })]);

    expect(screen.getByText(RAZAO)).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Ligar Regra Zz" }),
    ).toBeEnabled();
  });
});

describe("silenciar — data e hora com fuso, no futuro", () => {
  it("✅ manda `until` como ISO com o fuso do tenant", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(regra({ muted_until: "2099-01-01T12:00:00Z" }));
    abrir([regra()]);

    await user.click(
      screen.getByRole("button", { name: "Silenciar Regra Zz" }),
    );
    expect(screen.getByText("fuso: America/Sao_Paulo")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Silenciar até"), {
      target: { value: "2099-01-01T09:00" },
    });
    await user.click(screen.getByRole("button", { name: "Silenciar" }));

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request).toHaveBeenCalledWith(
      `/canais/regras/${RULE_ID}/silenciar`,
      { method: "POST", body: { until: "2099-01-01T09:00:00-03:00" } },
    );
  });

  it("⛔ o passado é recusado na tela, antes de mandar", async () => {
    const user = userEvent.setup();
    abrir([regra()]);

    await user.click(
      screen.getByRole("button", { name: "Silenciar Regra Zz" }),
    );
    fireEvent.change(screen.getByLabelText("Silenciar até"), {
      target: { value: "2000-01-01T09:00" },
    });
    await user.click(screen.getByRole("button", { name: "Silenciar" }));

    expect(
      await screen.findByText(
        "O silêncio termina no passado. Informe uma data futura.",
      ),
    ).toBeVisible();
    expect(request).not.toHaveBeenCalled();
  });

  it("sem data e hora nada é mandado", async () => {
    const user = userEvent.setup();
    abrir([regra()]);

    await user.click(
      screen.getByRole("button", { name: "Silenciar Regra Zz" }),
    );
    await user.click(screen.getByRole("button", { name: "Silenciar" }));

    expect(await screen.findByText("Informe a data e a hora.")).toBeVisible();
    expect(request).not.toHaveBeenCalled();
  });

  it("«Tirar o silêncio» só existe numa regra silenciada, e manda `until: null`", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(regra());
    abrir([regra({ muted_until: SILENCIO_FUTURO })]);

    await user.click(
      screen.getByRole("button", { name: "Silenciar Regra Zz" }),
    );
    await user.click(screen.getByRole("button", { name: "Tirar o silêncio" }));

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request).toHaveBeenCalledWith(
      `/canais/regras/${RULE_ID}/silenciar`,
      { method: "POST", body: { until: null } },
    );
  });

  it("… e não existe numa regra sem silêncio", async () => {
    const user = userEvent.setup();
    abrir([regra()]);

    await user.click(
      screen.getByRole("button", { name: "Silenciar Regra Zz" }),
    );

    expect(
      screen.queryByRole("button", { name: "Tirar o silêncio" }),
    ).toBeNull();
  });
});
