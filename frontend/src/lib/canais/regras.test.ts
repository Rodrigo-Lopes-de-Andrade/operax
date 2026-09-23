import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import {
  activateRule,
  createContact,
  createRule,
  deactivateContact,
  deactivateRule,
  eligibleContacts,
  eligibleResponsibilities,
  failureMessage,
  holdingRules,
  muteRule,
  muteUntilIso,
  refusalCode,
  replaceContactUnits,
  replaceRuleTargets,
  RESPONSIBILITIES,
  responsibilitiesFor,
  testRule,
  updateContact,
  updateRule,
  type AlertRuleWrite,
  type ContactRow,
  type ContactWrite,
} from "@/lib/canais/regras";

const request = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    requestApiAsUser: (...args: unknown[]) => request(...args),
  };
});

const ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const UNIT = "11111111-1111-4111-8111-111111111111";

function contato(overrides: Partial<ContactRow> = {}): ContactRow {
  return {
    id: ID,
    name: "Zz Pessoa",
    whatsapp: "5511999990000",
    email: "zz@fastpark.dev",
    type: "person",
    active: true,
    units: [],
    ...overrides,
  };
}

const REGRA: AlertRuleWrite = {
  name: "Regra Zz",
  deviation_type: null,
  scope_unit_id: null,
  content: "aggregate",
  channel: "whatsapp",
  cron_window: null,
  threshold_minutes: null,
  threshold_occurrences: null,
  template_code: "zz_template",
};

beforeEach(() => {
  request.mockReset();
  request.mockResolvedValue({});
});

describe("as mutações — cada uma na rota e com o corpo do contrato", () => {
  it("cria e edita contato com `ContactWrite`, sem `active`", async () => {
    const write: ContactWrite = {
      name: "Zz Pessoa",
      whatsapp: "5511999990000",
      email: null,
      type: "person",
    };

    await createContact(write);
    await updateContact(ID, write);

    expect(request).toHaveBeenNthCalledWith(
      1,
      "/canais/destinatarios/contatos",
      { method: "POST", body: write },
    );
    expect(request).toHaveBeenNthCalledWith(
      2,
      `/canais/destinatarios/contatos/${ID}`,
      { method: "PUT", body: write },
    );
    for (const [, options] of request.mock.calls) {
      expect((options as { body: object }).body).not.toHaveProperty("active");
    }
  });

  it("⛔ desativar é um POST em `/desativar` — nunca um DELETE", async () => {
    await deactivateContact(ID);

    expect(request).toHaveBeenCalledWith(
      `/canais/destinatarios/contatos/${ID}/desativar`,
      { method: "POST" },
    );
    expect(request.mock.calls[0][1]).not.toMatchObject({ method: "DELETE" });
  });

  it("a matriz vai inteira em `PUT /unidades`, dentro de `units`", async () => {
    await replaceContactUnits(ID, [
      { unit_id: UNIT, responsibility: "unit_manager", is_primary: true },
    ]);

    expect(request).toHaveBeenCalledWith(
      `/canais/destinatarios/contatos/${ID}/unidades`,
      {
        method: "PUT",
        body: {
          units: [
            { unit_id: UNIT, responsibility: "unit_manager", is_primary: true },
          ],
        },
      },
    );
  });

  it("⛔ criar e editar regra mandam `AlertRuleWrite` e NUNCA `active`", async () => {
    // `extra="forbid"` no backend: um `active` no corpo é 422, e a regra nasce
    // desligada de qualquer jeito. A única porta que a liga é `ligar`.
    await createRule(REGRA);
    await updateRule(ID, REGRA);

    expect(request).toHaveBeenNthCalledWith(1, "/canais/regras", {
      method: "POST",
      body: REGRA,
    });
    expect(request).toHaveBeenNthCalledWith(2, `/canais/regras/${ID}`, {
      method: "PUT",
      body: REGRA,
    });
    for (const [, options] of request.mock.calls) {
      const body = (options as { body: object }).body;
      expect(body).not.toHaveProperty("active");
      expect(body).not.toHaveProperty("muted_until");
    }
  });

  it("destinos vão em `PUT /destinos`, cada um com exatamente um dos dois campos", async () => {
    await replaceRuleTargets(ID, [
      { contact_id: ID, responsibility: null },
      { contact_id: null, responsibility: "unit_manager" },
    ]);

    expect(request).toHaveBeenCalledWith(`/canais/regras/${ID}/destinos`, {
      method: "PUT",
      body: {
        targets: [
          { contact_id: ID, responsibility: null },
          { contact_id: null, responsibility: "unit_manager" },
        ],
      },
    });
  });

  it("ligar, desligar e testar são POSTs sem corpo nas rotas nomeadas", async () => {
    await activateRule(ID);
    await deactivateRule(ID);
    await testRule(ID);

    expect(request.mock.calls).toEqual([
      [`/canais/regras/${ID}/ligar`, { method: "POST" }],
      [`/canais/regras/${ID}/desligar`, { method: "POST" }],
      [`/canais/regras/${ID}/testar`, { method: "POST" }],
    ]);
  });

  it("silenciar manda `until` como veio — ISO com fuso, ou nulo para tirar o silêncio", async () => {
    await muteRule(ID, "2099-01-01T09:00:00-03:00");
    await muteRule(ID, null);

    expect(request).toHaveBeenNthCalledWith(
      1,
      `/canais/regras/${ID}/silenciar`,
      { method: "POST", body: { until: "2099-01-01T09:00:00-03:00" } },
    );
    expect(request).toHaveBeenNthCalledWith(
      2,
      `/canais/regras/${ID}/silenciar`,
      { method: "POST", body: { until: null } },
    );
  });
});

describe("`muteUntilIso` — o `datetime-local` lido no fuso do tenant, enviado com o fuso", () => {
  it("✅ São Paulo é -03:00: o ISO carrega o deslocamento, não um Z", () => {
    // A suíte roda em UTC (`vitest.config.ts`): sem o fuso do tenant o
    // resultado sairia `Z`, e o silêncio terminaria três horas mais cedo.
    expect(muteUntilIso("2099-01-01T09:00")).toBe("2099-01-01T09:00:00-03:00");
    expect(muteUntilIso("2099-07-15T23:30")).toBe("2099-07-15T23:30:00-03:00");
  });

  it("o mesmo valor em outro fuso sai com o deslocamento desse fuso", () => {
    expect(muteUntilIso("2099-01-01T09:00", "UTC")).toBe(
      "2099-01-01T09:00:00+00:00",
    );
    expect(muteUntilIso("2099-01-01T09:00", "Asia/Kolkata")).toBe(
      "2099-01-01T09:00:00+05:30",
    );
  });

  it("⛔ o instante é o certo: 09:00 em São Paulo é 12:00 UTC", () => {
    const iso = muteUntilIso("2099-01-01T09:00");

    expect(iso).not.toBeNull();
    expect(new Date(iso as string).toISOString()).toBe(
      "2099-01-01T12:00:00.000Z",
    );
  });

  it("o que não é uma data e hora inteira é nulo — vazio, só a data, ou lixo", () => {
    expect(muteUntilIso("")).toBeNull();
    expect(muteUntilIso("2099-01-01")).toBeNull();
    expect(muteUntilIso("amanhã")).toBeNull();
  });
});

describe("a regra 7 antes do clique", () => {
  const pessoa = contato({ id: "p", name: "Pessoa" });
  const grupo = contato({
    id: "g",
    name: "Grupo",
    type: "whatsapp_group",
    email: null,
  });
  const lista = contato({ id: "l", name: "Lista", type: "email_list" });
  const inativo = contato({ id: "i", name: "Inativo", active: false });

  it("⛔ regra individual: nenhum grupo de WhatsApp entre os contatos elegíveis", () => {
    expect(
      eligibleContacts([pessoa, grupo, lista, inativo], "individual").map(
        (contact) => contact.id,
      ),
    ).toEqual(["p", "l"]);
  });

  it("✅ regra agregada: o grupo entra; o inativo não, em nenhuma", () => {
    expect(
      eligibleContacts([pessoa, grupo, lista, inativo], "aggregate").map(
        (contact) => contact.id,
      ),
    ).toEqual(["p", "g", "l"]);
  });

  it("⛔ a responsabilidade `group` só é oferecida ao agregado", () => {
    expect(eligibleResponsibilities("individual")).not.toContain("group");
    expect(eligibleResponsibilities("individual")).toHaveLength(5);
    expect(eligibleResponsibilities("aggregate")).toEqual([
      ...RESPONSIBILITIES,
    ]);
  });

  it("⛔ um grupo de WhatsApp só entra na matriz como `group`; os outros tipos, com as seis", () => {
    expect(responsibilitiesFor("whatsapp_group")).toEqual(["group"]);
    expect(responsibilitiesFor("person")).toEqual([...RESPONSIBILITIES]);
    expect(responsibilitiesFor("email_list")).toEqual([...RESPONSIBILITIES]);
  });
});

describe("o que se lê de uma recusa", () => {
  const detail = "Este contato é destino de regra ligada.";
  const rules = [
    { id: "r1", name: "Regra Um" },
    { id: "r2", name: "Regra Dois" },
  ];

  it("`holdingRules` lê as regras do corpo do 409, e nada mais", () => {
    const caught = new ApiError(409, detail, "contact_in_active_rule", {
      detail,
      code: "contact_in_active_rule",
      rules,
    });

    expect(holdingRules(caught)).toEqual(rules);
    expect(refusalCode(caught)).toBe("contact_in_active_rule");
    expect(failureMessage(caught, "genérica")).toBe(detail);
  });

  it("sem `rules` no corpo — ou sem corpo, ou sem ApiError — a lista é vazia", () => {
    expect(
      holdingRules(new ApiError(422, "x", "group_responsibility", { x: 1 })),
    ).toEqual([]);
    expect(holdingRules(new ApiError(504, null))).toEqual([]);
    expect(holdingRules(new Error("rede"))).toEqual([]);
    expect(refusalCode(new Error("rede"))).toBeNull();
    expect(failureMessage(new Error("rede"), "genérica")).toBe("genérica");
  });

  it("uma lista malformada não passa: sem `id` ou sem `name` é vazia", () => {
    expect(
      holdingRules(
        new ApiError(409, detail, "contact_last_responsible", {
          rules: [{ id: "r1" }],
        }),
      ),
    ).toEqual([]);
  });
});
