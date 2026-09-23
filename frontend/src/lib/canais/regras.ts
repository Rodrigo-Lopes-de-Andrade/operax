import { z } from "zod";

import { ApiError, requestApiAsUser } from "@/lib/api";
import { CHANNEL_LABEL } from "@/lib/canais/labels";
import { TENANT_TIME_ZONE } from "@/lib/ponto/filters";

/**
 * Destinatários e regras de alerta — Caminho 2 inteiro (SPRINTS-CANAIS, C6).
 *
 * Os tipos abaixo espelham o bloco "Destinatários e regras de alerta" de
 * `backend/server/models.py` **campo a campo**. São resposta de API, não
 * tabela: `app.contact`, `app.unit_responsible`, `app.alert_rule` e
 * `app.alert_rule_target` não chegam ao navegador, e o gerador de tipos do
 * Supabase não os alcança — é assim que `lib/canais/queries.ts` faz.
 *
 * As leituras do servidor (`GET`) vivem em `lib/canais/queries.ts`, que é
 * `server-only`: este módulo é o que o navegador importa — as mutações, os
 * rótulos e o que se lê de uma recusa — e um módulo `server-only` não entra
 * num componente de cliente (o mesmo par de `lib/assistente/config.ts`).
 *
 * ⛔ NENHUM CAMPO OBRIGATÓRIO DO CONTRATO É OPCIONAL AQUI
 * `blocked_reason` que sumisse como `undefined` viraria "nada a apontar" —
 * exatamente a leitura que a tela existe para impedir. Nulo é nulo; ausente
 * é erro de contrato.
 */

export const CONTACTS_API_PATH = "/canais/destinatarios/contatos";
export const RULES_API_PATH = "/canais/regras";

/**
 * Os valores dos `check` de `app.unit_responsible.responsibility` e de
 * `app.alert_rule_target.responsibility`. `group` é o que
 * `util.validate_alert_target` recusa num alerta individual (regra 7).
 */
export const RESPONSIBILITIES = [
  "unit_manager",
  "regional_supervisor",
  "personnel",
  "hr",
  "executive",
  "group",
] as const;
export type Responsibility = (typeof RESPONSIBILITIES)[number];

/** `app.contact.type`. `whatsapp_group` é o outro valor que a regra 7 recusa. */
export const CONTACT_TYPES = [
  "person",
  "whatsapp_group",
  "email_list",
] as const;
export type ContactType = (typeof CONTACT_TYPES)[number];

/**
 * `app.alert_rule.channel`: mensageria, e-mail ou as duas metades. A regra
 * diz mensageria e quem escolhe entre WhatsApp e o bot é a identidade de quem
 * recebe (SPEC-CANAIS §8) — por isso não há um quarto valor aqui.
 */
export const RULE_CHANNELS = ["whatsapp", "email", "both"] as const;
export type RuleChannel = (typeof RULE_CHANNELS)[number];

export const RULE_CONTENTS = ["individual", "aggregate"] as const;
export type RuleContent = (typeof RULE_CONTENTS)[number];

/** O `check` de `app.contact.whatsapp`, o mesmo que o backend confere antes do banco. */
export const WHATSAPP_PATTERN = /^\+?\d{10,15}$/;
/** O `pattern` de `ContactWrite.email`: algo, arroba, algo — o resto é do provedor. */
export const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+$/;

/** Uma linha da matriz unidade × responsabilidade de um contato (`UnitResponsibilityRow`). */
export type UnitResponsibilityRow = {
  unit_id: string;
  unit_name: string;
  responsibility: Responsibility;
  /** Entre dois contatos com a mesma responsabilidade na unidade, o outbox entrega ao primário. */
  is_primary: boolean;
};

/**
 * Um destinatário (`ContactRow`). `active` é coluna: a lista traz os
 * desativados e a tela os marca — um contato nunca é apagado.
 */
export type ContactRow = {
  id: string;
  name: string;
  /** E.164 com ou sem `+`. */
  whatsapp: string | null;
  email: string | null;
  type: ContactType;
  active: boolean;
  units: UnitResponsibilityRow[];
};

/**
 * O que o administrador grava num contato (`ContactWrite`). Sem `active`:
 * desativar é `POST /desativar`, com trilha própria. Ao menos um endereço —
 * o backend recusa 422 sem os dois.
 */
export type ContactWrite = {
  name: string;
  whatsapp: string | null;
  email: string | null;
  type: ContactType;
};

export type UnitResponsibilityWrite = {
  unit_id: string;
  responsibility: Responsibility;
  is_primary: boolean;
};

/** A matriz inteira do contato, substituída de uma vez (`ContactUnits`). */
export type ContactUnits = { units: UnitResponsibilityWrite[] };

/**
 * Um destino de regra (`AlertRuleTargetRow`): contato nomeado OU
 * responsabilidade que o outbox resolve por unidade. `contact_active` é nulo
 * no destino por responsabilidade; um contato desativado continua listado e
 * não conta como destino para `ligar`.
 */
export type AlertRuleTargetRow = {
  id: string;
  contact_id: string | null;
  contact_name: string | null;
  contact_active: boolean | null;
  responsibility: Responsibility | null;
};

/**
 * Uma regra de alerta (`AlertRuleRow`), com destinos e o que a impede de
 * entregar hoje.
 *
 * `blocked_reason` é texto pronto do backend e só existe em regra ligada.
 * Nulo é "nada a apontar", **não** "vai entregar": o gate G4 e a saúde do
 * provedor na hora do envio são do sender, e a tela não os vê daqui.
 */
export type AlertRuleRow = {
  id: string;
  name: string;
  /** Nulo = todo tipo. */
  deviation_type: string | null;
  /** Nulo = todas as unidades. */
  scope_unit_id: string | null;
  scope_unit_name: string | null;
  content: RuleContent;
  channel: RuleChannel;
  cron_window: string | null;
  threshold_minutes: number | null;
  threshold_occurrences: number | null;
  muted_until: string | null;
  template_code: string | null;
  active: boolean;
  targets: AlertRuleTargetRow[];
  blocked_reason: string | null;
};

/**
 * O que o administrador grava numa regra (`AlertRuleWrite`) — e o que ele
 * NÃO grava. `active` não existe aqui de propósito: o backend tem
 * `extra="forbid"` e um `active` no corpo é 422. A regra nasce desligada e a
 * única porta que a liga é `POST /{id}/ligar`. `muted_until` é de
 * `POST /{id}/silenciar`.
 */
export type AlertRuleWrite = {
  name: string;
  deviation_type: string | null;
  scope_unit_id: string | null;
  content: RuleContent;
  channel: RuleChannel;
  cron_window: string | null;
  threshold_minutes: number | null;
  threshold_occurrences: number | null;
  template_code: string | null;
};

/** Um destino a gravar: exatamente um de `contact_id` e `responsibility`. */
export type AlertRuleTargetWrite = {
  contact_id: string | null;
  responsibility: Responsibility | null;
};

export type AlertRuleTargets = { targets: AlertRuleTargetWrite[] };

/** `MuteRequest`: ISO com fuso, sempre; nulo tira o silêncio. */
export type MuteRequest = { until: string | null };

/** Uma linha que o teste pôs na fila: o canal ROTEADO e o provedor. Sem destino. */
export type QueuedTestMessage = {
  channel: string;
  provider: string | null;
};

/** O modo de teste do S6 (`RuleTestResult`): a regra enfileirada para quem clicou. */
export type RuleTestResult = {
  rule_id: string;
  test_id: string;
  contact_id: string;
  contact_name: string;
  queued: QueuedTestMessage[];
};

// ---------------------------------------------------------------------------
// Rótulos
// ---------------------------------------------------------------------------

export const RESPONSIBILITY_LABEL: Record<Responsibility, string> = {
  unit_manager: "Gestor da unidade",
  regional_supervisor: "Supervisor regional",
  personnel: "Departamento pessoal",
  hr: "RH",
  executive: "Diretoria",
  group: "Grupo",
};

export const CONTACT_TYPE_LABEL: Record<ContactType, string> = {
  person: "Pessoa",
  whatsapp_group: "Grupo de WhatsApp",
  email_list: "Lista de e-mail",
};

export const RULE_CHANNEL_LABEL: Record<RuleChannel, string> = {
  whatsapp: "Mensageria",
  email: "E-mail",
  both: "Mensageria e e-mail",
};

export const RULE_CONTENT_LABEL: Record<RuleContent, string> = {
  individual: "Individual",
  aggregate: "Agregado",
};

/**
 * O canal que o teste ROTEOU: um dos dois de `CHANNEL_LABEL`, ou a metade de
 * e-mail. Estende o mapa em vez de repetir o nome de canal fora de `labels.ts`.
 */
export const ROUTED_CHANNEL_LABEL: Record<string, string> = {
  ...CHANNEL_LABEL,
  email: "E-mail",
};

// ---------------------------------------------------------------------------
// A regra 7 antes do clique
// ---------------------------------------------------------------------------

/**
 * Os contatos que uma regra pode nomear como destino: ativos, e — numa regra
 * `individual` — nunca um grupo de WhatsApp. É a regra 7 oferecida antes do
 * clique; o juiz continua sendo `util.validate_alert_target`, e o 409 dele
 * é a rede.
 */
export function eligibleContacts(
  contacts: ContactRow[],
  content: RuleContent,
): ContactRow[] {
  return contacts.filter(
    (contact) =>
      contact.active &&
      (content === "aggregate" || contact.type !== "whatsapp_group"),
  );
}

/** As responsabilidades que uma regra pode resolver: `group` só no agregado. */
export function eligibleResponsibilities(
  content: RuleContent,
): Responsibility[] {
  return RESPONSIBILITIES.filter(
    (responsibility) => content === "aggregate" || responsibility !== "group",
  );
}

/**
 * As responsabilidades que um contato pode ter na matriz: um grupo de
 * WhatsApp só como `group` — é por ela que a regra 7 o reconhece num destino
 * por responsabilidade. O backend recusa 422 `group_responsibility`; a tela
 * nem oferece.
 */
export function responsibilitiesFor(type: ContactType): Responsibility[] {
  return type === "whatsapp_group"
    ? RESPONSIBILITIES.filter((responsibility) => responsibility === "group")
    : [...RESPONSIBILITIES];
}

// ---------------------------------------------------------------------------
// O silêncio, com fuso
// ---------------------------------------------------------------------------

const LOCAL_DATE_TIME = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/;

/** Minutos que o fuso está à frente do UTC no instante `at` (negativo a oeste). */
function zoneOffsetMinutes(zone: string, at: number): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: zone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(new Date(at));
  const field = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((part) => part.type === type)?.value);
  const wall = Date.UTC(
    field("year"),
    field("month") - 1,
    field("day"),
    field("hour"),
    field("minute"),
    field("second"),
  );

  return Math.round((wall - at) / 60_000);
}

/**
 * O valor de um `<input type="datetime-local">`, lido no fuso do tenant, como
 * o ISO **com fuso** que `MuteRequest` exige: `2026-09-22T09:00` vira
 * `2026-09-22T09:00:00-03:00`. Sem o fuso o backend recusa 422 — e com o fuso
 * do navegador o silêncio de quem viaja terminaria na hora errada. Nulo
 * quando o valor não é uma data e hora inteira.
 */
export function muteUntilIso(
  local: string,
  zone: string = TENANT_TIME_ZONE,
): string | null {
  const match = LOCAL_DATE_TIME.exec(local);

  if (!match) {
    return null;
  }

  const [, year, month, day, hour, minute] = match.map(Number);
  const guess = Date.UTC(year, month - 1, day, hour, minute);
  let offset = zoneOffsetMinutes(zone, guess);
  const again = zoneOffsetMinutes(zone, guess - offset * 60_000);

  if (again !== offset) {
    offset = again;
  }

  const sign = offset < 0 ? "-" : "+";
  const magnitude = Math.abs(offset);
  const pad = (value: number) => String(value).padStart(2, "0");

  return `${local}:00${sign}${pad(Math.floor(magnitude / 60))}:${pad(magnitude % 60)}`;
}

// ---------------------------------------------------------------------------
// Mutações — cada uma revalidada no backend (`util.is_admin` como o usuário)
// ---------------------------------------------------------------------------

export function createContact(body: ContactWrite): Promise<ContactRow> {
  return requestApiAsUser<ContactRow>(CONTACTS_API_PATH, {
    method: "POST",
    body,
  });
}

export function updateContact(
  contactId: string,
  body: ContactWrite,
): Promise<ContactRow> {
  return requestApiAsUser<ContactRow>(`${CONTACTS_API_PATH}/${contactId}`, {
    method: "PUT",
    body,
  });
}

/** `active = false`, nunca apagar: o contato fica na lista, marcado. */
export function deactivateContact(contactId: string): Promise<ContactRow> {
  return requestApiAsUser<ContactRow>(
    `${CONTACTS_API_PATH}/${contactId}/desativar`,
    { method: "POST" },
  );
}

export function replaceContactUnits(
  contactId: string,
  units: UnitResponsibilityWrite[],
): Promise<ContactRow> {
  const body: ContactUnits = { units };

  return requestApiAsUser<ContactRow>(
    `${CONTACTS_API_PATH}/${contactId}/unidades`,
    { method: "PUT", body },
  );
}

/** Cria a regra — desligada, sempre: o corpo não carrega `active`. */
export function createRule(body: AlertRuleWrite): Promise<AlertRuleRow> {
  return requestApiAsUser<AlertRuleRow>(RULES_API_PATH, {
    method: "POST",
    body,
  });
}

export function updateRule(
  ruleId: string,
  body: AlertRuleWrite,
): Promise<AlertRuleRow> {
  return requestApiAsUser<AlertRuleRow>(`${RULES_API_PATH}/${ruleId}`, {
    method: "PUT",
    body,
  });
}

export function replaceRuleTargets(
  ruleId: string,
  targets: AlertRuleTargetWrite[],
): Promise<AlertRuleRow> {
  const body: AlertRuleTargets = { targets };

  return requestApiAsUser<AlertRuleRow>(
    `${RULES_API_PATH}/${ruleId}/destinos`,
    { method: "PUT", body },
  );
}

/** A única porta que liga. O backend exige destino ativo e template; 409 nomeado se faltar. */
export function activateRule(ruleId: string): Promise<AlertRuleRow> {
  return requestApiAsUser<AlertRuleRow>(`${RULES_API_PATH}/${ruleId}/ligar`, {
    method: "POST",
  });
}

export function deactivateRule(ruleId: string): Promise<AlertRuleRow> {
  return requestApiAsUser<AlertRuleRow>(
    `${RULES_API_PATH}/${ruleId}/desligar`,
    { method: "POST" },
  );
}

/** `until` é ISO com fuso (`muteUntilIso`) ou nulo para tirar o silêncio. */
export function muteRule(
  ruleId: string,
  until: string | null,
): Promise<AlertRuleRow> {
  const body: MuteRequest = { until };

  return requestApiAsUser<AlertRuleRow>(
    `${RULES_API_PATH}/${ruleId}/silenciar`,
    { method: "POST", body },
  );
}

/** O modo de teste do S6: a regra enfileirada para quem clicou, ligada ou não. */
export function testRule(ruleId: string): Promise<RuleTestResult> {
  return requestApiAsUser<RuleTestResult>(
    `${RULES_API_PATH}/${ruleId}/testar`,
    { method: "POST" },
  );
}

// ---------------------------------------------------------------------------
// O que se lê de uma recusa
// ---------------------------------------------------------------------------

/** Uma regra ligada que segura um contato, como o 409 a lista. */
export type HoldingRule = { id: string; name: string };

const holdingRulesSchema = z.object({
  rules: z.array(z.object({ id: z.string(), name: z.string() })),
});

/**
 * As regras que um 409 lista ao lado do `detail` — `contact_in_active_rule`
 * (o contato é destino direto) e `contact_last_responsible` (é o único
 * responsável ativo que resolve um destino por responsabilidade). Vazio
 * quando a resposta não as traz.
 */
export function holdingRules(caught: unknown): HoldingRule[] {
  if (!(caught instanceof ApiError)) {
    return [];
  }

  const parsed = holdingRulesSchema.safeParse(caught.payload);

  return parsed.success ? parsed.data.rules : [];
}

/** O `code` estável de uma recusa nomeada, ou nulo. */
export function refusalCode(caught: unknown): string | null {
  return caught instanceof ApiError ? caught.code : null;
}

/** O `detail` como veio — já em pt-BR — ou a frase genérica. */
export function failureMessage(caught: unknown, fallback: string): string {
  return caught instanceof ApiError && caught.detail ? caught.detail : fallback;
}
