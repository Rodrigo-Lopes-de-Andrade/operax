import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Connections } from "@/components/canais/connections";
import { TEMPLATES_PATH } from "@/lib/canais/url";
import type {
  BlockedAlertRule,
  ChannelCapabilities,
  ConnectionsScreen,
} from "@/lib/canais/queries";

const OFFICIAL: ChannelCapabilities = {
  official: true,
  requires_templates: true,
  ban_risk: false,
};

const UNOFFICIAL: ChannelCapabilities = {
  official: false,
  requires_templates: false,
  ban_risk: true,
};

/** O caso 1 do contrato — o gate da sprint. */
const PENDING: BlockedAlertRule = {
  rule_name: "Desvio individual",
  template_code: "deviation_individual",
  meta_status: "pending",
};

/** O caso 2: código que não existe ou está inativo — a resposta não distingue. */
const MISSING: BlockedAlertRule = {
  rule_name: "Resumo da unidade",
  template_code: "unit_summary",
  meta_status: null,
};

/** O caso 3: regra de WhatsApp sem template nenhum. */
const NO_TEMPLATE: BlockedAlertRule = {
  rule_name: "Sem batida",
  template_code: null,
  meta_status: null,
};

function official(
  overrides: Partial<ConnectionsScreen> = {},
): ConnectionsScreen {
  return {
    provider: "meta_cloud",
    capabilities: OFFICIAL,
    templates_total: 2,
    templates_approved: 1,
    rules_blocked: 1,
    ready: false,
    blocked: [PENDING],
    ...overrides,
  };
}

function unofficial(
  overrides: Partial<ConnectionsScreen> = {},
): ConnectionsScreen {
  return {
    provider: "z_api",
    capabilities: UNOFFICIAL,
    templates_total: 0,
    templates_approved: 0,
    rules_blocked: 0,
    ready: true,
    blocked: [],
    ...overrides,
  };
}

const EMPTY: ConnectionsScreen = {
  provider: null,
  capabilities: null,
  templates_total: 0,
  templates_approved: 0,
  rules_blocked: 0,
  ready: false,
  blocked: [],
};

const TEMPLATE_PHRASE = /Exige template aprovado pela Meta/;
const BAN_PHRASE = /volume alto pode levar a banimento/;

function preso() {
  return screen.queryByRole("heading", { name: "O que está preso" });
}

/** O bloco 3 inteiro — e só ele: o bloco 1 também é uma lista. */
function bloco3() {
  const bloco = preso()?.closest("section");

  if (!bloco) {
    throw new Error("o bloco 3 não está na tela");
  }

  return within(bloco);
}

function linhas() {
  return bloco3().getAllByRole("listitem");
}

describe("bloco 1 — o canal", () => {
  it("⛔ sem provedor é o estado vazio, e nenhum dos outros blocos existe", () => {
    // Produção não tem canal nenhum: esta é a tela principal no primeiro dia.
    render(<Connections screen={EMPTY} />);

    expect(
      screen.getByText("Nenhum canal de WhatsApp configurado"),
    ).toBeVisible();
    expect(
      screen.getByText(/não têm por onde sair até haver um canal ativo/),
    ).toBeVisible();
    expect(screen.queryByText(/Pronto|Bloqueado/)).toBeNull();
    expect(screen.queryByText(/Templates aprovados/)).toBeNull();
    expect(preso()).toBeNull();
    // Sem promessa de botão: a escrita de credencial é o C2, com parada do dono.
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByText(/configurar/i)).toBeNull();
  });

  it("⛔ provedor sem `capabilities` também é o estado vazio, não 'sem restrição'", () => {
    // O backend nunca emite esse par (`capabilities_for` levanta), mas um
    // fallback de flags falsas aqui leria "aceita tudo" — o erro que a matriz
    // existe para impedir.
    render(<Connections screen={official({ capabilities: null })} />);

    expect(
      screen.getByText("Nenhum canal de WhatsApp configurado"),
    ).toBeVisible();
    expect(screen.queryByText(TEMPLATE_PHRASE)).toBeNull();
    expect(screen.queryByText(BAN_PHRASE)).toBeNull();
    expect(preso()).toBeNull();
  });

  it("✅ com provedor o estado vazio não aparece, e o rótulo é o humano", () => {
    render(<Connections screen={official()} />);

    expect(
      screen.queryByText("Nenhum canal de WhatsApp configurado"),
    ).toBeNull();
    expect(
      screen.getByRole("heading", { name: "WhatsApp Cloud API (Meta)" }),
    ).toBeVisible();
    expect(screen.getByText("Canal oficial")).toBeVisible();
  });

  it("`requires_templates` → a frase de template, e não a de banimento", () => {
    render(<Connections screen={official()} />);

    expect(screen.getByText(TEMPLATE_PHRASE)).toBeVisible();
    expect(screen.queryByText(BAN_PHRASE)).toBeNull();
  });

  it("`ban_risk` → a frase de banimento, e não a de template", () => {
    render(<Connections screen={unofficial()} />);

    expect(screen.getByText(BAN_PHRASE)).toBeVisible();
    expect(screen.queryByText(TEMPLATE_PHRASE)).toBeNull();
    expect(screen.getByText("Canal não oficial")).toBeVisible();
  });

  it("⛔ a frase vem das flags, não do nome: flags invertidas em relação ao provedor", () => {
    // SPEC §1: feature nenhuma pergunta *com quem* falamos. Um
    // `if provider === "meta_cloud"` passaria nos dois casos acima e cairia
    // aqui — o nome diz oficial e as flags dizem banimento.
    render(
      <Connections
        screen={official({ provider: "meta_cloud", capabilities: UNOFFICIAL })}
      />,
    );

    expect(screen.getByText(BAN_PHRASE)).toBeVisible();
    expect(screen.queryByText(TEMPLATE_PHRASE)).toBeNull();
  });

  it("⛔ … e o par: nome não oficial com flags do oficial mostra template", () => {
    render(
      <Connections
        screen={unofficial({ provider: "z_api", capabilities: OFFICIAL })}
      />,
    );

    expect(screen.getByText(TEMPLATE_PHRASE)).toBeVisible();
    expect(screen.queryByText(BAN_PHRASE)).toBeNull();
  });

  it("⛔ canal não oficial não menciona a Meta em lugar nenhum", () => {
    const { container } = render(<Connections screen={unofficial()} />);

    expect(container.textContent).not.toMatch(/\bMeta\b/);
    // ✅ O positivo: o mesmo teste enxerga a Meta quando ela está lá.
    const { container: oficial } = render(<Connections screen={official()} />);
    expect(oficial.textContent).toMatch(/\bMeta\b/);
  });
});

describe("bloco 2 — a saúde", () => {
  it("⛔ `ready: true` diz Pronto, e o bloco 3 está ausente do DOM", () => {
    render(
      <Connections
        screen={official({
          ready: true,
          rules_blocked: 0,
          blocked: [],
          templates_approved: 2,
        })}
      />,
    );

    expect(screen.getByText("Pronto")).toBeVisible();
    expect(screen.queryByText("Bloqueado")).toBeNull();
    expect(preso()).toBeNull();
    // "Pronto e nada mais": sem contagem para ler quando não há o que consertar.
    expect(screen.queryByText("Regras bloqueadas")).toBeNull();
    expect(screen.queryByText("Templates aprovados")).toBeNull();
  });

  it("`ready: false` diz Bloqueado, com os templates aprovados de total e as regras", () => {
    render(<Connections screen={official()} />);

    expect(screen.getByText("Bloqueado")).toBeVisible();
    expect(screen.queryByText("Pronto")).toBeNull();
    expect(
      screen.getByText("Templates aprovados").nextElementSibling,
    ).toHaveTextContent("1 de 2");
    expect(
      screen.getByText("Regras bloqueadas").nextElementSibling,
    ).toHaveTextContent("1");
  });

  it("⛔ a contagem é a da API, não o tamanho da lista — e nenhuma das duas some", () => {
    // `rules_blocked` e `blocked.length` são duas leituras do mesmo fato. O
    // backend já loga a diferença; a tela mostra as duas em vez de consertar.
    render(
      <Connections
        screen={official({ rules_blocked: 3, blocked: [PENDING] })}
      />,
    );

    expect(
      screen.getByText("Regras bloqueadas").nextElementSibling,
    ).toHaveTextContent("3");
    expect(linhas()).toHaveLength(1);
    expect(
      screen.getByText(/A contagem da API diz 3 regras bloqueadas/),
    ).toBeVisible();
    expect(screen.getByText(/a lista traz 1\./)).toBeVisible();
  });

  it("✅ quando as duas leituras concordam, não há aviso de divergência", () => {
    render(<Connections screen={official()} />);

    expect(screen.queryByText(/A contagem da API diz/)).toBeNull();
  });
});

describe("bloco 3 — o que está preso", () => {
  it("⛔ GATE: template pendente numa regra ligada mostra a regra, o template e o estado", () => {
    // O defeito que a sprint fecha: hoje esse estado existe, é calculado por
    // `fn_whatsapp_readiness`, e é invisível.
    render(<Connections screen={official()} />);

    const [linha] = linhas();
    expect(linha).toHaveTextContent(
      "a regra Desvio individual aponta para o template deviation_individual, que está pendente na Meta.",
    );
    expect(within(linha).getByText("Desvio individual")).toBeVisible();
    expect(within(linha).getByText("deviation_individual")).toBeVisible();
    expect(within(linha).getByText("pendente")).toBeVisible();
  });

  it("cada regra presa leva à ação que a solta: o link para a aba de templates", () => {
    render(<Connections screen={official()} />);

    const [linha] = linhas();
    expect(
      within(linha).getByRole("link", { name: "ver templates" }),
    ).toHaveAttribute("href", TEMPLATES_PATH);
  });

  it("estado que ninguém traduziu aparece cru, não some", () => {
    render(
      <Connections
        screen={official({
          blocked: [{ ...PENDING, meta_status: "disabled" }],
        })}
      />,
    );

    expect(linhas()[0]).toHaveTextContent("que está disabled na Meta");
  });

  it("⛔ caso 2: `meta_status` nulo é 'não existe ou está inativo' — e NÃO a frase do caso 1", () => {
    // A resposta não distingue código inexistente de template inativo (os dois
    // caem em `m.id is null`), e a frase não pode fingir que distingue.
    render(<Connections screen={official({ blocked: [MISSING] })} />);

    const [linha] = linhas();
    expect(linha).toHaveTextContent(
      "a regra Resumo da unidade aponta para o template unit_summary, que não existe ou está inativo neste cliente.",
    );
    expect(linha).not.toHaveTextContent(/na Meta/);
  });

  it("⛔ caso 3: `template_code` nulo é 'não aponta para template nenhum' — e NÃO a frase do caso 2", () => {
    render(<Connections screen={official({ blocked: [NO_TEMPLATE] })} />);

    const [linha] = linhas();
    expect(linha).toHaveTextContent(
      "a regra Sem batida é de WhatsApp e não aponta para template nenhum.",
    );
    expect(linha).not.toHaveTextContent(/não existe ou está inativo/);
    expect(linha).not.toHaveTextContent(/na Meta/);
  });

  it("uma linha por item, na ordem em que vieram — inclusive a mesma regra duas vezes", () => {
    // O mesmo `code` em dois idiomas casa duas vezes no `left join`, e a
    // função conta as duas. Deduplicar aqui quebraria o par com a contagem.
    render(
      <Connections
        screen={official({
          rules_blocked: 4,
          blocked: [PENDING, PENDING, MISSING, NO_TEMPLATE],
        })}
      />,
    );

    const todas = linhas();
    expect(todas).toHaveLength(4);
    expect(todas[0]).toHaveTextContent(/pendente na Meta/);
    expect(todas[1]).toHaveTextContent(/pendente na Meta/);
    expect(todas[2]).toHaveTextContent(/não existe ou está inativo/);
    expect(todas[3]).toHaveTextContent(/não aponta para template nenhum/);
  });

  it("⛔ sem lista e sem `ready`, o canal exige template aprovado e nenhum está", () => {
    // Provedor oficial com zero templates aprovados e nenhuma regra ligada:
    // `ready` é falso pela outra metade da condição da função.
    render(
      <Connections
        screen={official({
          templates_total: 2,
          templates_approved: 0,
          rules_blocked: 0,
          blocked: [],
        })}
      />,
    );

    expect(preso()).toBeVisible();
    expect(
      screen.getByText(
        /exige template aprovado pela Meta, e nenhum está aprovado \(0 de 2\)/,
      ),
    ).toBeVisible();
    expect(bloco3().queryByRole("listitem")).toBeNull();
  });

  it("contagem sem lista, com template aprovado, não inventa a causa", () => {
    // `rules_blocked: 2` e `blocked: []` com um template aprovado: a frase de
    // "nenhum está aprovado" seria falsa. A tela diz que a lista veio vazia e
    // mostra a divergência.
    render(
      <Connections
        screen={official({
          templates_approved: 1,
          rules_blocked: 2,
          blocked: [],
        })}
      />,
    );

    expect(
      screen.getByText(
        /marcou o canal como bloqueado e a lista de regras veio vazia/,
      ),
    ).toBeVisible();
    expect(screen.queryByText(/nenhum está aprovado/)).toBeNull();
    expect(
      screen.getByText(/A contagem da API diz 2 regras bloqueadas/),
    ).toBeVisible();
  });
});
