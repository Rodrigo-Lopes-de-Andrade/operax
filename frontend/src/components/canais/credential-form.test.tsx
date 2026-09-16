import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CredentialForm } from "@/components/canais/credential-form";
import { ApiError } from "@/lib/api";
import type {
  ChannelCapabilities,
  CredentialField,
  CredentialStatus,
  ProviderForm,
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

const OFFICIAL: ChannelCapabilities = {
  official: true,
  requires_templates: true,
  ban_risk: false,
  requires_recipient_opt_in: false,
};

const UNOFFICIAL: ChannelCapabilities = {
  official: false,
  requires_templates: false,
  ban_risk: true,
  requires_recipient_opt_in: false,
};

// Valores de teste óbvios — nenhum é credencial de ninguém.
const NUMBER_ID_VALUE = "123456789012345";
const TOKEN_VALUE = "token-de-teste-123";

/** O que `meta_cloud.py` declara, como a API o entrega. */
const NUMBER_ID: CredentialField = {
  name: "phone_number_id",
  label: "ID do número de telefone",
  pattern: "[0-9]{5,32}",
  autocomplete: "off",
  inputmode: "numeric",
  secret: false,
  placeholder: "123456789012345",
  hint: "isto não parece um ID de número: a Meta usa só dígitos",
};

const TOKEN: CredentialField = {
  name: "token",
  label: "Token de acesso permanente",
  pattern: "[A-Za-z0-9._\\-]+",
  autocomplete: "one-time-code",
  inputmode: "text",
  secret: true,
  placeholder: "EAAG…",
  hint: "isto não parece um token: só letras, dígitos, ponto, hífen e sublinhado",
};

const INSTANCE_ID: CredentialField = {
  name: "instance_id",
  label: "ID da instância",
  pattern: "[A-Za-z0-9]{8,64}",
  autocomplete: "off",
  inputmode: "text",
  secret: false,
  placeholder: "3C4E5F…",
  hint: "isto não parece um ID de instância: só letras e dígitos",
};

function official(overrides: Partial<ProviderForm> = {}): ProviderForm {
  return {
    provider: "meta_cloud",
    channel: "whatsapp",
    capabilities: OFFICIAL,
    fields: [NUMBER_ID, TOKEN],
    ...overrides,
  };
}

function unofficial(overrides: Partial<ProviderForm> = {}): ProviderForm {
  return {
    provider: "z_api",
    channel: "whatsapp",
    capabilities: UNOFFICIAL,
    fields: [INSTANCE_ID, { ...TOKEN, label: "Token da instância" }],
    ...overrides,
  };
}

const NOT_CONFIGURED: CredentialStatus = {
  channel: "whatsapp",
  configured: false,
  provider: null,
  updated_at: null,
  public_identity: null,
};

const CONFIGURED: CredentialStatus = {
  channel: "whatsapp",
  configured: true,
  provider: "meta_cloud",
  // 13:05 UTC é 10:05 em São Paulo — a data sai no fuso do tenant.
  updated_at: "2026-09-14T13:05:00Z",
  public_identity: "+55 11 99999-0000",
};

const TEMPLATE_PHRASE = /Exige template aprovado pela Meta/;
const BAN_PHRASE = /volume alto pode levar a banimento/;

function numberId() {
  return screen.getByLabelText("ID do número de telefone");
}

function token() {
  return screen.getByLabelText("Token de acesso permanente");
}

function submit() {
  return screen.getByRole("button", { name: "Validar e gravar" });
}

/** Preenche o formulário do oficial com valores válidos e envia. */
async function preencherEEnviar(user: ReturnType<typeof userEvent.setup>) {
  await user.type(numberId(), NUMBER_ID_VALUE);
  await user.type(token(), TOKEN_VALUE);
  await user.click(submit());
}

beforeEach(() => {
  request.mockReset();
  refresh.mockReset();
});

describe("critério 1 — os campos vêm da API, nenhum é escrito à mão", () => {
  it("um campo que nenhum provedor real tem aparece com o rótulo que a API deu", () => {
    render(
      <CredentialForm
        forms={[
          official({
            fields: [
              {
                ...NUMBER_ID,
                name: "xyz",
                label: "Campo inventado pela API",
              },
            ],
          }),
        ]}
        status={NOT_CONFIGURED}
      />,
    );

    expect(screen.getByLabelText("Campo inventado pela API")).toBeVisible();
    // ✅ E só ele: nenhum campo fixo apareceu junto.
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    expect(screen.queryByLabelText("ID do número de telefone")).toBeNull();
  });

  it("⛔ provedor sem campo nenhum não desenha input nenhum", () => {
    render(
      <CredentialForm
        forms={[official({ fields: [] })]}
        status={NOT_CONFIGURED}
      />,
    );

    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
    expect(document.querySelectorAll("input")).toHaveLength(0);
  });
});

describe("critério 2 — SPEC §5.4: autocomplete, inputmode e pattern vêm da API", () => {
  it("cada campo carrega os três atributos como a API os mandou", () => {
    render(<CredentialForm forms={[official()]} status={NOT_CONFIGURED} />);

    expect(numberId().getAttribute("autocomplete")).toBe("off");
    expect(numberId().getAttribute("inputmode")).toBe("numeric");
    expect(numberId().getAttribute("pattern")).toBe("[0-9]{5,32}");
    expect(numberId().getAttribute("placeholder")).toBe("123456789012345");

    expect(token().getAttribute("autocomplete")).toBe("one-time-code");
    expect(token().getAttribute("inputmode")).toBe("text");
    expect(token().getAttribute("pattern")).toBe("[A-Za-z0-9._\\-]+");
  });

  it("o pattern do fixture compila com a flag `v`, que é como o navegador compila o atributo", () => {
    // `[A-Za-z0-9._-]+` compila sem flag (o Zod) e não compila com `v` (o
    // atributo, descartado em silêncio). O fixture copia o que o backend
    // declara; se o backend regredir, quem prende é `test_canais_credencial.py`.
    for (const field of [NUMBER_ID, TOKEN, INSTANCE_ID]) {
      expect(() => new RegExp(field.pattern, "v")).not.toThrow();
    }
  });

  it("⛔ os atributos são repassados, não escolhidos: valores fora do comum chegam ao DOM iguais", () => {
    // Um componente que escrevesse `autoComplete="off"` à mão passaria no
    // caso acima. Este só passa se o valor do fixture chegar ao atributo.
    render(
      <CredentialForm
        forms={[
          official({
            fields: [
              {
                ...NUMBER_ID,
                autocomplete: "section-teste tel",
                inputmode: "decimal",
                pattern: "[a-z]{3}",
              },
            ],
          }),
        ]}
        status={NOT_CONFIGURED}
      />,
    );

    expect(numberId().getAttribute("autocomplete")).toBe("section-teste tel");
    expect(numberId().getAttribute("inputmode")).toBe("decimal");
    expect(numberId().getAttribute("pattern")).toBe("[a-z]{3}");
  });

  it("`secret` → password; não-secreto → text", () => {
    render(<CredentialForm forms={[official()]} status={NOT_CONFIGURED} />);

    expect(token()).toHaveAttribute("type", "password");
    expect(numberId()).toHaveAttribute("type", "text");
  });

  it("⛔ … e é a flag que decide, não o nome do campo", () => {
    // O mesmo `token` com `secret: false` vira texto; o ID com `secret: true`
    // vira senha. Um `name === "token"` passaria no caso acima e cai aqui.
    render(
      <CredentialForm
        forms={[
          official({
            fields: [
              { ...NUMBER_ID, secret: true },
              { ...TOKEN, secret: false },
            ],
          }),
        ]}
        status={NOT_CONFIGURED}
      />,
    );

    expect(numberId()).toHaveAttribute("type", "password");
    expect(token()).toHaveAttribute("type", "text");
  });
});

describe("critério 3 — formato inválido não sai do navegador; válido sai exato", () => {
  it("⛔ e-mail em 'ID do número' mostra a hint do campo e não chama a API", async () => {
    const user = userEvent.setup();
    render(<CredentialForm forms={[official()]} status={NOT_CONFIGURED} />);

    await user.type(numberId(), "gestor@fastpark.dev");
    await user.type(token(), TOKEN_VALUE);
    await user.click(submit());

    expect(await screen.findByText(NUMBER_ID.hint)).toBeVisible();
    expect(numberId()).toHaveAttribute("aria-invalid", "true");
    expect(request).not.toHaveBeenCalled();
    // ✅ O outro campo, válido, não recebeu a hint dele.
    expect(screen.queryByText(TOKEN.hint)).toBeNull();
  });

  it("⛔ a validação usa o `pattern` da API, não uma regex própria", async () => {
    // Mesmo valor numérico, `pattern` trocado no fixture: agora ele é
    // inválido, e "abc" é válido. Uma regex escrita no componente ignoraria a
    // troca e passaria no caso acima.
    const user = userEvent.setup();
    request.mockResolvedValue(CONFIGURED);
    render(
      <CredentialForm
        forms={[
          official({ fields: [{ ...NUMBER_ID, pattern: "[a-z]{3}" }, TOKEN] }),
        ]}
        status={NOT_CONFIGURED}
      />,
    );

    await user.type(numberId(), NUMBER_ID_VALUE);
    await user.type(token(), TOKEN_VALUE);
    await user.click(submit());

    expect(await screen.findByText(NUMBER_ID.hint)).toBeVisible();
    expect(request).not.toHaveBeenCalled();

    await user.clear(numberId());
    await user.type(numberId(), "abc");
    await user.click(submit());

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
  });

  it("⛔ o `pattern` é ancorado como o `fullmatch` do backend: casar no meio não basta", async () => {
    // `[0-9]{5,32}` sem âncora casa "12345" dentro de "abc12345def" — e o
    // backend recusaria com 422. Aqui tem de ser recusado antes.
    const user = userEvent.setup();
    render(<CredentialForm forms={[official()]} status={NOT_CONFIGURED} />);

    await user.type(numberId(), "abc12345def");
    await user.type(token(), TOKEN_VALUE);
    await user.click(submit());

    expect(await screen.findByText(NUMBER_ID.hint)).toBeVisible();
    expect(request).not.toHaveBeenCalled();
  });

  it("✅ válido → POST com o body exatamente `{ provider, fields }`", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(CONFIGURED);
    render(<CredentialForm forms={[official()]} status={NOT_CONFIGURED} />);

    await preencherEEnviar(user);

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0]).toStrictEqual([
      "/canais/credencial",
      {
        method: "POST",
        body: {
          provider: "meta_cloud",
          fields: { phone_number_id: NUMBER_ID_VALUE, token: TOKEN_VALUE },
        },
      },
    ]);
  });

  it("espaço nas pontas de um token colado é tirado antes de validar e enviar — como o backend faz", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(CONFIGURED);
    render(<CredentialForm forms={[official()]} status={NOT_CONFIGURED} />);

    await user.type(numberId(), ` ${NUMBER_ID_VALUE} `);
    await user.type(token(), `  ${TOKEN_VALUE}`);
    await user.click(submit());

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0][1].body.fields).toStrictEqual({
      phone_number_id: NUMBER_ID_VALUE,
      token: TOKEN_VALUE,
    });
  });

  it("o botão fica desabilitado enquanto o provedor responde", async () => {
    const user = userEvent.setup();
    let resolve: (status: CredentialStatus) => void = () => {};
    request.mockReturnValue(
      new Promise<CredentialStatus>((done) => {
        resolve = done;
      }),
    );
    render(<CredentialForm forms={[official()]} status={NOT_CONFIGURED} />);

    await preencherEEnviar(user);

    const busy = await screen.findByRole("button", {
      name: "Validando no provedor…",
    });
    expect(busy).toBeDisabled();

    resolve(CONFIGURED);
    expect(
      await screen.findByRole("button", { name: "Validar e gravar" }),
    ).toBeEnabled();
  });
});

describe("critério 4 — sucesso: a identidade aparece, o segredo some", () => {
  it("mostra 'conectado como …', chama router.refresh() e limpa o campo secreto", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(CONFIGURED);
    render(<CredentialForm forms={[official()]} status={NOT_CONFIGURED} />);

    await preencherEEnviar(user);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Conectado como +55 11 99999-0000",
    );
    expect(refresh).toHaveBeenCalledTimes(1);

    // ⛔ §5.3: o token digitado não está mais em lugar nenhum do DOM.
    expect(token()).toHaveValue("");
    expect(screen.queryByDisplayValue(TOKEN_VALUE)).toBeNull();
    // ✅ O identificador público fica — não é segredo, e a pessoa vai querer
    // conferi-lo.
    expect(screen.getByDisplayValue(NUMBER_ID_VALUE)).toBeVisible();
  });

  it("o estado acima do formulário passa a ser o que a API devolveu, sem esperar o refresh", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(CONFIGURED);
    render(<CredentialForm forms={[official()]} status={NOT_CONFIGURED} />);

    expect(
      screen.getByText("Nenhuma credencial gravada neste cliente."),
    ).toBeVisible();

    await preencherEEnviar(user);

    await screen.findByRole("status");
    expect(
      screen.queryByText("Nenhuma credencial gravada neste cliente."),
    ).toBeNull();
    expect(screen.getByText("Configurada")).toBeVisible();
  });
});

describe("critério 5 — erro: o `detail` como veio, e o que foi digitado fica", () => {
  it("⛔ 422 do provedor → a frase da API na tela, os valores nos campos, sem refresh", async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(
      new ApiError(422, "O provedor recusou a credencial. Nada foi gravado."),
    );
    render(<CredentialForm forms={[official()]} status={NOT_CONFIGURED} />);

    await preencherEEnviar(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "O provedor recusou a credencial. Nada foi gravado.",
    );
    expect(token()).toHaveValue(TOKEN_VALUE);
    expect(numberId()).toHaveValue(NUMBER_ID_VALUE);
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("403 → o `detail` da API", async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(
      new ApiError(
        403,
        "Gravar a credencial do canal é do administrador do cliente.",
      ),
    );
    render(<CredentialForm forms={[official()]} status={NOT_CONFIGURED} />);

    await preencherEEnviar(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Gravar a credencial do canal é do administrador do cliente.",
    );
  });

  it("500 sem `detail` → a mensagem padrão, e o formulário continua de pé", async () => {
    const user = userEvent.setup();
    request.mockRejectedValue(new ApiError(500, null));
    render(<CredentialForm forms={[official()]} status={NOT_CONFIGURED} />);

    await preencherEEnviar(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não consegui gravar a credencial.",
    );
    expect(submit()).toBeEnabled();
    expect(token()).toHaveValue(TOKEN_VALUE);
  });

  it("um erro antigo some ao reenviar", async () => {
    const user = userEvent.setup();
    request
      .mockRejectedValueOnce(new ApiError(422, "recusada na primeira"))
      .mockResolvedValueOnce(CONFIGURED);
    render(<CredentialForm forms={[official()]} status={NOT_CONFIGURED} />);

    await preencherEEnviar(user);
    await screen.findByRole("alert");

    await user.click(submit());

    await screen.findByRole("status");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("um sucesso antigo some quando o envio seguinte é recusado", async () => {
    const user = userEvent.setup();
    request
      .mockResolvedValueOnce(CONFIGURED)
      .mockRejectedValueOnce(new ApiError(422, "recusada na segunda"));
    render(<CredentialForm forms={[official()]} status={NOT_CONFIGURED} />);

    await preencherEEnviar(user);
    await screen.findByRole("status");

    await user.type(token(), TOKEN_VALUE);
    await user.click(submit());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "recusada na segunda",
    );
    // "Credencial gravada" ao lado de "nada foi gravado" é contradição na tela.
    expect(screen.queryByRole("status")).toBeNull();
    // O estado acima continua sendo o que foi gravado de fato.
    expect(screen.getByText("Configurada")).toBeVisible();
  });

  it("o sucesso de um provedor não fica em cima do formulário de outro", async () => {
    const user = userEvent.setup();
    request.mockResolvedValueOnce(CONFIGURED);
    render(
      <CredentialForm
        forms={[official(), unofficial()]}
        status={NOT_CONFIGURED}
      />,
    );

    await preencherEEnviar(user);
    await screen.findByRole("status");

    await user.selectOptions(screen.getByLabelText("Provedor"), "Z-API");

    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("critério 6 — o estado atual, e o formulário nos dois casos", () => {
  it("configurada → rótulo humano do provedor, identidade e data no fuso do tenant", () => {
    render(<CredentialForm forms={[official()]} status={CONFIGURED} />);

    expect(screen.getByText("Configurada")).toBeVisible();
    // No parágrafo do estado — a `<option>` do seletor também o escreve.
    expect(
      screen.getByText("WhatsApp Cloud API (Meta)", { selector: "p" }),
    ).toBeVisible();
    expect(screen.getByText("+55 11 99999-0000")).toBeVisible();
    expect(screen.getByText(/gravada em 14\/09\/2026 às 10:05/)).toBeVisible();
    expect(
      screen.queryByText("Nenhuma credencial gravada neste cliente."),
    ).toBeNull();
    // ✅ O formulário está lá para trocar a credencial.
    expect(submit()).toBeVisible();
  });

  it("não configurada → 'nenhuma credencial gravada', e o formulário também está lá", () => {
    render(<CredentialForm forms={[official()]} status={NOT_CONFIGURED} />);

    expect(screen.getByText("Não configurada")).toBeVisible();
    expect(
      screen.getByText("Nenhuma credencial gravada neste cliente."),
    ).toBeVisible();
    expect(screen.queryByText("Configurada")).toBeNull();
    expect(submit()).toBeVisible();
  });

  it("⛔ nenhum campo do estado carrega valor de credencial — só o que a API mandou", () => {
    // O `CredentialStatus` não tem o segredo; a tela não tem de onde tirá-lo.
    // O teste fecha a porta pelo outro lado: o DOM inicial não tem nenhum
    // input preenchido.
    render(<CredentialForm forms={[official()]} status={CONFIGURED} />);

    for (const input of document.querySelectorAll("input")) {
      expect(input).toHaveValue("");
    }
  });
});

describe("critério 7 — o seletor, e o que o canal exige vem das flags", () => {
  it("os provedores estão na ordem da API, e o configurado vem preselecionado", async () => {
    render(
      <CredentialForm
        forms={[unofficial(), official()]}
        status={{ ...CONFIGURED, provider: "meta_cloud" }}
      />,
    );

    const select = screen.getByLabelText("Provedor");
    const options = screen.getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual([
      "Z-API",
      "WhatsApp Cloud API (Meta)",
    ]);
    expect(select).toHaveValue("meta_cloud");
  });

  it("sem credencial, o primeiro da API é o escolhido", () => {
    render(
      <CredentialForm
        forms={[official(), unofficial()]}
        status={NOT_CONFIGURED}
      />,
    );

    expect(screen.getByLabelText("Provedor")).toHaveValue("meta_cloud");
    expect(screen.getByText(TEMPLATE_PHRASE)).toBeVisible();
  });

  it("trocar o provedor troca a frase e os campos", async () => {
    const user = userEvent.setup();
    render(
      <CredentialForm
        forms={[official(), unofficial()]}
        status={NOT_CONFIGURED}
      />,
    );

    expect(screen.getByText(TEMPLATE_PHRASE)).toBeVisible();
    expect(screen.queryByText(BAN_PHRASE)).toBeNull();
    expect(numberId()).toBeVisible();

    await user.selectOptions(screen.getByLabelText("Provedor"), "Z-API");

    expect(screen.getByText(BAN_PHRASE)).toBeVisible();
    expect(screen.queryByText(TEMPLATE_PHRASE)).toBeNull();
    expect(screen.getByLabelText("ID da instância")).toBeVisible();
    expect(screen.queryByLabelText("ID do número de telefone")).toBeNull();
  });

  it("⛔ a frase vem das flags, não do nome: flags invertidas em relação ao provedor", () => {
    // O mesmo par do C1, agora no seletor. Um `if provider === …` passaria
    // nos casos acima e cai aqui — o nome diz oficial e as flags dizem
    // banimento.
    render(
      <CredentialForm
        forms={[official({ capabilities: UNOFFICIAL })]}
        status={NOT_CONFIGURED}
      />,
    );

    expect(screen.getByText(BAN_PHRASE)).toBeVisible();
    expect(screen.queryByText(TEMPLATE_PHRASE)).toBeNull();
  });

  it("⛔ … e o par: nome não oficial com flags do oficial mostra template", () => {
    render(
      <CredentialForm
        forms={[unofficial({ capabilities: OFFICIAL })]}
        status={NOT_CONFIGURED}
      />,
    );

    expect(screen.getByText(TEMPLATE_PHRASE)).toBeVisible();
    expect(screen.queryByText(BAN_PHRASE)).toBeNull();
  });

  it("o que foi digitado para um provedor não sobrevive à troca", async () => {
    const user = userEvent.setup();
    render(
      <CredentialForm
        forms={[official(), unofficial()]}
        status={NOT_CONFIGURED}
      />,
    );

    await user.type(token(), TOKEN_VALUE);
    await user.selectOptions(screen.getByLabelText("Provedor"), "Z-API");

    expect(screen.queryByDisplayValue(TOKEN_VALUE)).toBeNull();

    // ✅ E o POST do novo provedor leva só os campos dele.
    request.mockResolvedValue(CONFIGURED);
    await user.type(screen.getByLabelText("ID da instância"), "ABCDEFGH1234");
    await user.type(screen.getByLabelText("Token da instância"), TOKEN_VALUE);
    await user.click(submit());

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request.mock.calls[0][1].body).toStrictEqual({
      provider: "z_api",
      fields: { instance_id: "ABCDEFGH1234", token: TOKEN_VALUE },
    });
  });
});
