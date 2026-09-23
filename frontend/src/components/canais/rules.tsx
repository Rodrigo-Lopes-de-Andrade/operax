"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { BellRing } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import type { UnitChoice } from "@/components/dp/work-posts";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { TextField } from "@/components/ui/text-field";
import { label, META_STATUS_LABEL, PROVIDER_LABEL } from "@/lib/canais/labels";
import type { TemplateRow } from "@/lib/canais/queries";
import {
  activateRule,
  createRule,
  deactivateRule,
  eligibleContacts,
  eligibleResponsibilities,
  failureMessage,
  muteRule,
  muteUntilIso,
  refusalCode,
  replaceRuleTargets,
  RESPONSIBILITY_LABEL,
  ROUTED_CHANNEL_LABEL,
  RULE_CHANNEL_LABEL,
  RULE_CHANNELS,
  RULE_CONTENT_LABEL,
  RULE_CONTENTS,
  testRule,
  updateRule,
  type AlertRuleRow,
  type AlertRuleTargetWrite,
  type AlertRuleWrite,
  type ContactRow,
  type Responsibility,
  type RuleTestResult,
} from "@/lib/canais/regras";
import { DESTINATARIOS_PATH } from "@/lib/canais/url";
import { formatDayInTenantZone } from "@/lib/dp/format";
import { TENANT_TIME_ZONE } from "@/lib/ponto/filters";
import { formatClock, formatNumber } from "@/lib/ponto/format";

const FIELD_CLASS =
  "bg-control border-control-line text-ink placeholder:text-ink-faint rounded-[10px] border px-3 text-base outline-none focus-visible:border-transparent";
const LABEL_CLASS =
  "text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase";

/** A doutrina do S6, numa linha fixa no topo. */
export const DOCTRINE =
  "Toda regra nasce desligada. Teste primeiro com destino em você mesmo; ligue depois de homologar com o cliente.";

/** O que o teste faz, dito antes do clique — em toda regra, ligada ou não. */
export const TEST_NOTE =
  "A mensagem de teste vai para o seu contato (o cadastrado com o seu e-mail), com dados reais dos últimos 7 dias. Com a entrega ainda não liberada, ela fica na fila e aparece em Conexões como esperando.";

/** Ligada não é entregando — o que a tela não vê daqui é do sender. */
const ACTIVE_NOTE =
  "Ligada não quer dizer entregando: com a entrega ainda não liberada, a fila espera — Conexões mostra o que está preso, e o que pode ser apontado desde já aparece ao lado da regra.";

/**
 * A forma de cada campo de `AlertRuleWrite`, e só a forma. **Sem `active`**:
 * a regra nasce desligada e o backend recusa 422 um `active` no corpo — a
 * única porta que a liga é o botão "Ligar". Os seletores mandam o código e
 * mostram o rótulo; vazio é nulo no corpo ("todo tipo", "todas as unidades",
 * "sem template", "na detecção").
 */
const ruleSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Informe o nome.")
    .max(120, "No máximo 120 caracteres."),
  scope_unit_id: z.string(),
  content: z.enum(RULE_CONTENTS),
  channel: z.enum(RULE_CHANNELS),
  template_code: z.string(),
});

type RuleValues = z.infer<typeof ruleSchema>;

const EMPTY_RULE: RuleValues = {
  name: "",
  scope_unit_id: "",
  content: "aggregate",
  channel: "whatsapp",
  template_code: "",
};

function ruleValues(row: AlertRuleRow): RuleValues {
  return {
    name: row.name,
    scope_unit_id: row.scope_unit_id ?? "",
    content: row.content,
    channel: row.channel,
    template_code: row.template_code ?? "",
  };
}

/** O que a tela está fazendo com uma regra, ou nada. */
type Panel =
  | { kind: "new" }
  | { kind: "edit"; ruleId: string }
  | { kind: "targets"; ruleId: string }
  | { kind: "mute"; ruleId: string };

type Outcome =
  { kind: "saved"; message: string } | { kind: "error"; message: string };

/**
 * O desfecho de uma ação imediata numa regra — ligar, desligar, testar —
 * mostrado na linha dela. `no_contact` é o 409 `caller_has_no_contact`: a
 * frase do backend e o caminho até Destinatários.
 */
type RuleOutcome =
  | Outcome
  | { kind: "tested"; result: RuleTestResult }
  | { kind: "no_contact"; message: string };

function OutcomeView({ outcome }: { outcome: Outcome }) {
  return outcome.kind === "saved" ? (
    <p role="status" className="text-good text-sm font-medium">
      {outcome.message}
    </p>
  ) : (
    <Alert>{outcome.message}</Alert>
  );
}

/**
 * Em quantas das unidades que a regra cobre há alguém ativo com esta
 * responsabilidade na matriz — e quantas ela cobre.
 *
 * ⛔ Conta **por unidade**, porque é assim que o destino é resolvido: o
 * `outbox._TARGETS_SQL` procura o responsável na unidade do ciclo, uma de
 * cada vez. Contar "existe alguém em alguma unidade" cala numa regra de
 * todas as unidades com um responsável só — que entrega a ninguém em todas
 * as outras. A regra recortada cobre uma unidade; a de todas cobre todas.
 */
function coverage(
  contacts: ContactRow[],
  units: UnitChoice[],
  responsibility: Responsibility,
  scopeUnitId: string | null,
): { covered: number; total: number } {
  const scope =
    scopeUnitId === null ? units.map((unit) => unit.id) : [scopeUnitId];
  const covered = scope.filter((unitId) =>
    contacts.some(
      (contact) =>
        contact.active &&
        contact.units.some(
          (row) =>
            row.responsibility === responsibility && row.unit_id === unitId,
        ),
    ),
  ).length;
  return { covered, total: scope.length };
}

/**
 * Criar e editar são o mesmo formulário; o pai remonta pelo `key` quando a
 * regra muda. Tipos de desvio, unidades e templates chegam por prop —
 * qualquer um deles nulo é "não pôde ser lido agora", e o seletor diz isso
 * em vez de fingir que o catálogo está vazio.
 */
function RuleForm({
  editing,
  units,
  templates,
  onOutcome,
  onCancel,
}: {
  editing: AlertRuleRow | null;
  units: UnitChoice[];
  templates: TemplateRow[] | null;
  onOutcome: (outcome: Outcome | null, saved: boolean) => void;
  onCancel: () => void;
}) {
  const { register, handleSubmit, formState } = useForm<RuleValues>({
    resolver: zodResolver(ruleSchema),
    defaultValues: editing ? ruleValues(editing) : EMPTY_RULE,
  });
  const activeTemplates = (templates ?? []).filter((row) => row.active);
  // O template atual de uma regra pode ter saído do catálogo ativo: o
  // seletor o mantém, nomeado, em vez de trocá-lo por "sem template" calado.
  const staleTemplate =
    editing?.template_code &&
    !activeTemplates.some((row) => row.code === editing.template_code)
      ? editing.template_code
      : null;

  const onSubmit = handleSubmit(async (values) => {
    onOutcome(null, false);

    const write: AlertRuleWrite = {
      name: values.name,
      // ⛔ Os quatro campos que o outbox não lê vão NULOS e não têm campo na
      // tela: `deviation_type`, `cron_window`, `threshold_minutes` e
      // `threshold_occurrences` são gravados por `AlertRuleWrite` e ignorados
      // por `outbox._TARGETS_SQL`. Oferecê-los era prometer um filtro que não
      // existe. Voltam junto com quem os leia.
      deviation_type: null,
      scope_unit_id: values.scope_unit_id || null,
      content: values.content,
      channel: values.channel,
      cron_window: null,
      threshold_minutes: null,
      threshold_occurrences: null,
      template_code: values.template_code || null,
    };

    try {
      const saved = editing
        ? await updateRule(editing.id, write)
        : await createRule(write);
      onOutcome(
        {
          kind: "saved",
          message: editing
            ? `Regra ${saved.name} gravada.`
            : `Regra ${saved.name} criada — desligada. Teste antes de ligar.`,
        },
        true,
      );
    } catch (caught) {
      onOutcome(
        {
          kind: "error",
          message: failureMessage(caught, "Não consegui gravar a regra."),
        },
        false,
      );
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          id="rule-name"
          label="Nome"
          autoComplete="off"
          error={formState.errors.name?.message}
          {...register("name")}
        />
        <div className="flex flex-col gap-1.5">
          <label htmlFor="rule-unit" className={LABEL_CLASS}>
            Unidade
          </label>
          <select
            id="rule-unit"
            className={`${FIELD_CLASS} h-10 text-sm`}
            {...register("scope_unit_id")}
          >
            <option value="">Todas as unidades</option>
            {units.map((unit) => (
              <option key={unit.id} value={unit.id}>
                {unit.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="rule-content" className={LABEL_CLASS}>
            Conteúdo
          </label>
          <select
            id="rule-content"
            className={`${FIELD_CLASS} h-10 text-sm`}
            {...register("content")}
          >
            {RULE_CONTENTS.map((content) => (
              <option key={content} value={content}>
                {RULE_CONTENT_LABEL[content]}
              </option>
            ))}
          </select>
          <p className="text-ink-faint text-xs text-pretty">
            individual nomeia a pessoa e nunca vai para grupo; agregado é a
            contagem da unidade
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="rule-channel" className={LABEL_CLASS}>
            Canal
          </label>
          <select
            id="rule-channel"
            className={`${FIELD_CLASS} h-10 text-sm`}
            {...register("channel")}
          >
            {RULE_CHANNELS.map((channel) => (
              <option key={channel} value={channel}>
                {RULE_CHANNEL_LABEL[channel]}
              </option>
            ))}
          </select>
          <p className="text-ink-faint text-xs text-pretty">
            mensageria é WhatsApp — ou o bot do Telegram, para quem aderiu
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="rule-template" className={LABEL_CLASS}>
            Template
          </label>
          <select
            id="rule-template"
            className={`${FIELD_CLASS} h-10 text-sm`}
            {...register("template_code")}
          >
            <option value="">Sem template</option>
            {activeTemplates.map((row) => (
              <option key={row.code} value={row.code}>
                {row.code} · {label(META_STATUS_LABEL, row.meta_status)}
              </option>
            ))}
            {staleTemplate ? (
              <option value={staleTemplate}>
                {staleTemplate} · fora do catálogo ativo
              </option>
            ) : null}
          </select>
          <p className="text-ink-faint text-xs text-pretty">
            a mensageria exige um template do catálogo; sem ele a regra não liga
          </p>
          {templates === null ? (
            <p className="text-bad text-xs font-medium">
              O catálogo de templates não pôde ser lido agora.
            </p>
          ) : null}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={formState.isSubmitting}>
          {formState.isSubmitting ? "Gravando…" : "Gravar regra"}
        </Button>
        <button
          type="button"
          onClick={onCancel}
          className="text-ink-muted hover:text-ink text-sm font-bold"
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}

/**
 * Os destinos da regra, substituídos de uma vez (`PUT /destinos`): contatos
 * ativos nomeados **ou** responsabilidades que o outbox resolve por unidade.
 *
 * A regra 7 antes do clique: numa regra `individual` a lista não oferece
 * grupo de WhatsApp nem a responsabilidade "Grupo" (`eligibleContacts`,
 * `eligibleResponsibilities`). O juiz continua sendo o gatilho do banco, e o
 * 409 dele vira frase se chegar. Um contato desativado entre os destinos
 * atuais não é oferecido e sai ao gravar — a tela o nomeia antes.
 */
function TargetsForm({
  rule,
  contacts,
  onOutcome,
  onCancel,
}: {
  rule: AlertRuleRow;
  contacts: ContactRow[];
  onOutcome: (outcome: Outcome | null, saved: boolean) => void;
  onCancel: () => void;
}) {
  const candidates = eligibleContacts(contacts, rule.content);
  const responsibilities = eligibleResponsibilities(rule.content);
  const [chosenContacts, setChosenContacts] = useState<Set<string>>(
    () =>
      new Set(
        rule.targets.flatMap((target) =>
          target.contact_id !== null ? [target.contact_id] : [],
        ),
      ),
  );
  const [chosenResponsibilities, setChosenResponsibilities] = useState<
    Set<Responsibility>
  >(
    () =>
      new Set(
        rule.targets.flatMap((target) =>
          target.responsibility !== null ? [target.responsibility] : [],
        ),
      ),
  );
  const [busy, setBusy] = useState(false);
  const dropped = rule.targets.filter(
    (target) =>
      target.contact_id !== null &&
      !candidates.some((contact) => contact.id === target.contact_id),
  );

  function toggle<T>(set: Set<T>, value: T, checked: boolean): Set<T> {
    const next = new Set(set);

    if (checked) {
      next.add(value);
    } else {
      next.delete(value);
    }

    return next;
  }

  async function save() {
    setBusy(true);
    onOutcome(null, false);

    const targets: AlertRuleTargetWrite[] = [
      ...candidates
        .filter((contact) => chosenContacts.has(contact.id))
        .map((contact) => ({ contact_id: contact.id, responsibility: null })),
      ...responsibilities
        .filter((responsibility) => chosenResponsibilities.has(responsibility))
        .map((responsibility) => ({ contact_id: null, responsibility })),
    ];

    try {
      await replaceRuleTargets(rule.id, targets);
      onOutcome(
        { kind: "saved", message: `Destinos de ${rule.name} gravados.` },
        true,
      );
    } catch (caught) {
      onOutcome(
        {
          kind: "error",
          message: failureMessage(
            caught,
            "Não consegui gravar os destinos da regra.",
          ),
        },
        false,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {rule.content === "individual" ? (
        <p className="text-ink-muted text-sm text-pretty">
          Regra individual: grupos de WhatsApp e a responsabilidade «Grupo» não
          são oferecidos — conteúdo individual nunca vai para grupo.
        </p>
      ) : null}
      {dropped.length > 0 ? (
        <p className="text-alert text-sm text-pretty">
          Fora da lista que esta regra pode nomear, e sai dos destinos ao
          gravar: {dropped.map((target) => target.contact_name).join(", ")}.
        </p>
      ) : null}
      <fieldset className="flex flex-col gap-2">
        <legend className={LABEL_CLASS}>Contatos</legend>
        {candidates.length === 0 ? (
          <p className="text-ink-muted text-sm">
            Nenhum contato ativo que esta regra possa nomear.
          </p>
        ) : null}
        {candidates.map((contact) => (
          <label key={contact.id} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4"
              checked={chosenContacts.has(contact.id)}
              onChange={(event) =>
                setChosenContacts(
                  toggle(chosenContacts, contact.id, event.target.checked),
                )
              }
            />
            <span className="text-ink">{contact.name}</span>
          </label>
        ))}
      </fieldset>
      <fieldset className="flex flex-col gap-2">
        <legend className={LABEL_CLASS}>Por responsabilidade</legend>
        <p className="text-ink-faint text-xs text-pretty">
          resolvida por unidade na matriz de Destinatários, na hora do envio
        </p>
        {responsibilities.map((responsibility) => (
          <label
            key={responsibility}
            className="flex items-center gap-2 text-sm"
          >
            <input
              type="checkbox"
              className="size-4"
              checked={chosenResponsibilities.has(responsibility)}
              onChange={(event) =>
                setChosenResponsibilities(
                  toggle(
                    chosenResponsibilities,
                    responsibility,
                    event.target.checked,
                  ),
                )
              }
            />
            <span className="text-ink">
              {RESPONSIBILITY_LABEL[responsibility]}
            </span>
          </label>
        ))}
      </fieldset>
      <div className="flex items-center gap-3">
        <Button type="button" onClick={() => void save()} disabled={busy}>
          {busy ? "Gravando…" : "Gravar destinos"}
        </Button>
        <button
          type="button"
          onClick={onCancel}
          className="text-ink-muted hover:text-ink text-sm font-bold"
        >
          Cancelar
        </button>
      </div>
    </div>
  );
}

/**
 * Silenciar até uma data e hora — lida no fuso do tenant e enviada com ele
 * (`muteUntilIso`). O passado é recusado aqui, antes de mandar, com a mesma
 * frase que o backend usaria. "Tirar o silêncio" manda `until: null`.
 */
function MuteForm({
  rule,
  onOutcome,
  onCancel,
}: {
  rule: AlertRuleRow;
  onOutcome: (outcome: Outcome | null, saved: boolean) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function send(until: string | null) {
    setBusy(true);
    onOutcome(null, false);

    try {
      await muteRule(rule.id, until);
      onOutcome(
        {
          kind: "saved",
          message: until
            ? `Regra ${rule.name} silenciada.`
            : `Silêncio de ${rule.name} retirado.`,
        },
        true,
      );
    } catch (caught) {
      onOutcome(
        {
          kind: "error",
          message: failureMessage(caught, "Não consegui silenciar a regra."),
        },
        false,
      );
    } finally {
      setBusy(false);
    }
  }

  function submit() {
    const iso = muteUntilIso(value);

    if (iso === null) {
      setError("Informe a data e a hora.");
      return;
    }

    if (new Date(iso).getTime() <= Date.now()) {
      setError("O silêncio termina no passado. Informe uma data futura.");
      return;
    }

    setError(null);
    void send(iso);
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="rule-mute-until" className={LABEL_CLASS}>
          Silenciar até
        </label>
        <input
          id="rule-mute-until"
          type="datetime-local"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby="rule-mute-zone"
          className={`${FIELD_CLASS} h-10 max-w-xs text-sm`}
        />
        <p id="rule-mute-zone" className="text-ink-faint text-xs">
          fuso: {TENANT_TIME_ZONE}
        </p>
        {error ? <p className="text-bad text-xs font-medium">{error}</p> : null}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" onClick={submit} disabled={busy}>
          {busy ? "Gravando…" : "Silenciar"}
        </Button>
        {rule.muted_until ? (
          <button
            type="button"
            onClick={() => void send(null)}
            disabled={busy}
            className="text-brand-strong text-sm font-bold underline"
          >
            Tirar o silêncio
          </button>
        ) : null}
        <button
          type="button"
          onClick={onCancel}
          className="text-ink-muted hover:text-ink text-sm font-bold"
        >
          Cancelar
        </button>
      </div>
    </div>
  );
}

/** O que o teste enfileirou — as metades, cada uma com o canal roteado e o provedor. */
function TestResultView({ result }: { result: RuleTestResult }) {
  return (
    <p role="status" className="text-good text-sm font-medium text-pretty">
      Teste enfileirado para {result.contact_name}:{" "}
      {result.queued
        .map(
          (message) =>
            `${label(ROUTED_CHANNEL_LABEL, message.channel)}${
              message.provider
                ? ` via ${label(PROVIDER_LABEL, message.provider)}`
                : ""
            }`,
        )
        .join(" · ")}
      . Com a entrega ainda não liberada, fica esperando em Conexões.
    </p>
  );
}

function RuleOutcomeView({ outcome }: { outcome: RuleOutcome }) {
  if (outcome.kind === "tested") {
    return <TestResultView result={outcome.result} />;
  }

  if (outcome.kind === "no_contact") {
    return (
      <div
        role="alert"
        className="bg-bad-bg text-bad flex flex-col gap-1 rounded-[10px] px-3 py-2 text-sm font-medium"
      >
        <p>{outcome.message}</p>
        <Link href={DESTINATARIOS_PATH} className="underline">
          Cadastrar em Destinatários
        </Link>
      </div>
    );
  }

  return <OutcomeView outcome={outcome} />;
}

/**
 * Uma regra: o que ela é, se está ligada, o que a impede de entregar
 * (`blocked_reason`, como veio — texto pronto do backend, nunca remontado
 * aqui), os destinos, e as ações. O botão de teste existe em toda regra,
 * ligada ou não: o teste vem antes de ligar.
 */
function RuleItem({
  rule,
  contacts,
  units,
  now,
  outcome,
  busy,
  onOpen,
  onActivate,
  onDeactivate,
  onTest,
}: {
  rule: AlertRuleRow;
  contacts: ContactRow[] | null;
  units: UnitChoice[];
  now: number;
  outcome: RuleOutcome | null;
  busy: boolean;
  onOpen: (panel: Panel) => void;
  onActivate: () => void;
  onDeactivate: () => void;
  onTest: () => void;
}) {
  return (
    <li id={`regra-${rule.id}`} className="flex flex-col gap-2 px-5 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-ink text-sm font-bold">{rule.name}</span>
        <Badge tone={rule.active ? "good" : "neutral"} dot>
          {rule.active ? "Ligada" : "Desligada"}
        </Badge>
        {/* Silêncio vencido não é silêncio: o outbox já entrega quando
            `muted_until <= now()`, e a insígnia sumiria só no próximo
            `PUT`. A tela lê o relógio, como o banco. */}
        {rule.muted_until && Date.parse(rule.muted_until) > now ? (
          <Badge tone="alert">
            silêncio até {formatDayInTenantZone(rule.muted_until)}{" "}
            {formatClock(rule.muted_until)}
          </Badge>
        ) : null}
        <Badge tone={rule.content === "individual" ? "brand" : "neutral"}>
          {RULE_CONTENT_LABEL[rule.content]}
        </Badge>
      </div>
      {/* Nem o tipo de desvio nem a janela aparecem: o outbox não filtra por
          eles, e mostrá-los ao lado da regra afirma um recorte que a entrega
          não faz. Voltam quando houver quem os leia. */}
      <p className="text-ink-muted text-xs">
        {rule.scope_unit_name ?? "todas as unidades"} ·{" "}
        {RULE_CHANNEL_LABEL[rule.channel]} ·{" "}
        {rule.template_code ? (
          <>
            template{" "}
            <code className="text-ink font-mono">{rule.template_code}</code>
          </>
        ) : (
          "sem template"
        )}
      </p>
      {rule.blocked_reason ? (
        <p className="bg-alert-bg text-alert rounded-[10px] px-3 py-2 text-xs font-medium text-pretty">
          {rule.blocked_reason}
        </p>
      ) : null}
      {rule.targets.length > 0 ? (
        <ul
          aria-label={`Destinos de ${rule.name}`}
          className="text-ink-muted flex flex-wrap gap-x-3 gap-y-0.5 text-xs"
        >
          {rule.targets.map((target) => {
            if (target.contact_id !== null) {
              return (
                <li key={target.id}>
                  {target.contact_name}
                  {target.contact_active === false ? " (inativo)" : ""}
                </li>
              );
            }

            // Exatamente um dos dois é preenchido (`AlertRuleTargetWrite`):
            // sem `contact_id`, a responsabilidade está lá.
            const responsibility = target.responsibility as Responsibility;
            const reach =
              contacts === null
                ? null
                : coverage(contacts, units, responsibility, rule.scope_unit_id);

            return (
              <li key={target.id}>
                por responsabilidade: {RESPONSIBILITY_LABEL[responsibility]}
                {reach !== null && reach.covered < reach.total ? (
                  <span className="text-alert">
                    {" "}
                    —{" "}
                    {reach.covered === 0
                      ? "ninguém ativo com esta responsabilidade na matriz"
                      : `resolve em ${reach.covered} de ${reach.total} unidades`}
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-ink-faint text-xs">Sem destino.</p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => onOpen({ kind: "edit", ruleId: rule.id })}
          aria-label={`Editar ${rule.name}`}
          className="text-brand-strong text-xs font-bold underline"
        >
          Editar
        </button>
        <button
          type="button"
          onClick={() => onOpen({ kind: "targets", ruleId: rule.id })}
          aria-label={`Destinos de ${rule.name}`}
          className="text-brand-strong text-xs font-bold underline"
        >
          Destinos
        </button>
        <button
          type="button"
          onClick={() => onOpen({ kind: "mute", ruleId: rule.id })}
          aria-label={`Silenciar ${rule.name}`}
          className="text-brand-strong text-xs font-bold underline"
        >
          Silenciar
        </button>
        {rule.active ? (
          <button
            type="button"
            onClick={onDeactivate}
            disabled={busy}
            aria-label={`Desligar ${rule.name}`}
            className="text-ink-muted hover:text-ink text-xs font-bold underline disabled:opacity-60"
          >
            Desligar
          </button>
        ) : (
          <button
            type="button"
            onClick={onActivate}
            disabled={busy}
            aria-label={`Ligar ${rule.name}`}
            className="text-brand-strong text-xs font-bold underline disabled:opacity-60"
          >
            Ligar
          </button>
        )}
        <button
          type="button"
          onClick={onTest}
          disabled={busy}
          aria-label={`Enviar teste para mim: ${rule.name}`}
          className="text-brand-strong ml-auto text-xs font-bold underline disabled:opacity-60"
        >
          Enviar teste para mim
        </button>
      </div>
      {outcome ? <RuleOutcomeView outcome={outcome} /> : null}
    </li>
  );
}

/**
 * Regras — a lista, e um painel por vez: nova regra, editar, destinos,
 * silenciar. Ligar, desligar e testar são imediatos, e o desfecho fica na
 * linha da regra.
 *
 * Caminho 2 inteiro, menos as unidades do seletor (`vw_unit`, Caminho 1). O
 * backend revalida papel em cada escrita e é ele que julga `ligar`; a tela
 * mostra o `detail` do 409 como veio. Depois de gravar, `router.refresh()`
 * traz a lista nova do servidor.
 */
export function Rules({
  rules,
  contacts,
  units,
  templates,
  now,
}: {
  rules: AlertRuleRow[];
  contacts: ContactRow[] | null;
  units: UnitChoice[];
  templates: TemplateRow[] | null;
  /** O instante do render do servidor — ver `regras/page.tsx`. */
  now: number;
}) {
  const router = useRouter();
  const [panel, setPanel] = useState<Panel | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [ruleOutcome, setRuleOutcome] = useState<{
    ruleId: string;
    outcome: RuleOutcome;
  } | null>(null);
  const [busyRule, setBusyRule] = useState<string | null>(null);

  const selected =
    panel && panel.kind !== "new"
      ? (rules.find((rule) => rule.id === panel.ruleId) ?? null)
      : null;

  function open(next: Panel) {
    setOutcome(null);
    setPanel(next);
  }

  function close() {
    setOutcome(null);
    setPanel(null);
  }

  function settle(next: Outcome | null, saved: boolean) {
    setOutcome(next);
    if (saved) {
      setPanel(null);
      router.refresh();
    }
  }

  async function run(
    rule: AlertRuleRow,
    action: "activate" | "deactivate" | "test",
  ) {
    setBusyRule(rule.id);
    setRuleOutcome(null);

    try {
      if (action === "test") {
        const result = await testRule(rule.id);
        setRuleOutcome({
          ruleId: rule.id,
          outcome: { kind: "tested", result },
        });
      } else {
        await (action === "activate"
          ? activateRule(rule.id)
          : deactivateRule(rule.id));
        setRuleOutcome({
          ruleId: rule.id,
          outcome: {
            kind: "saved",
            message:
              action === "activate"
                ? `Regra ${rule.name} ligada.`
                : `Regra ${rule.name} desligada.`,
          },
        });
        router.refresh();
      }
    } catch (caught) {
      const message = failureMessage(
        caught,
        action === "test"
          ? "Não consegui enfileirar o teste."
          : action === "activate"
            ? "Não consegui ligar a regra."
            : "Não consegui desligar a regra.",
      );
      setRuleOutcome({
        ruleId: rule.id,
        outcome:
          refusalCode(caught) === "caller_has_no_contact"
            ? { kind: "no_contact", message }
            : { kind: "error", message },
      });
    } finally {
      setBusyRule(null);
    }
  }

  const title =
    panel?.kind === "new"
      ? "Nova regra"
      : panel?.kind === "edit" && selected
        ? `Editar ${selected.name}`
        : panel?.kind === "targets" && selected
          ? `Destinos de ${selected.name}`
          : panel?.kind === "mute" && selected
            ? `Silenciar ${selected.name}`
            : null;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-ink text-sm font-medium text-pretty">{DOCTRINE}</p>

      <Card>
        <CardHeader
          eyebrow="Alertas"
          title="Regras"
          note={`${formatNumber(rules.length)} ${rules.length === 1 ? "regra" : "regras"} neste cliente`}
          action={
            <Button type="button" onClick={() => open({ kind: "new" })}>
              Nova regra
            </Button>
          }
        />
        <div className="border-line-subtle text-ink-muted flex flex-col gap-1 border-b px-5 py-3 text-xs text-pretty">
          <p>{TEST_NOTE}</p>
          <p>{ACTIVE_NOTE}</p>
        </div>
        {outcome && !panel ? (
          <div className="border-line-subtle border-b px-5 py-3">
            <OutcomeView outcome={outcome} />
          </div>
        ) : null}
        {rules.length > 0 ? (
          <ul
            aria-label="Regras de alerta"
            className="divide-line-subtle divide-y"
          >
            {rules.map((rule) => (
              <RuleItem
                key={rule.id}
                rule={rule}
                contacts={contacts}
                units={units}
                now={now}
                outcome={
                  ruleOutcome?.ruleId === rule.id ? ruleOutcome.outcome : null
                }
                busy={busyRule === rule.id}
                onOpen={open}
                onActivate={() => void run(rule, "activate")}
                onDeactivate={() => void run(rule, "deactivate")}
                onTest={() => void run(rule, "test")}
              />
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={BellRing}
            tone="neutral"
            title="Nenhuma regra neste cliente"
            description="Uma regra diz que desvio, de que unidade, vai para quem e por onde. Crie a primeira — ela nasce desligada."
          />
        )}
      </Card>

      {panel && title ? (
        <Card>
          <CardHeader eyebrow="Regra" title={title} />
          <div className="flex flex-col gap-4 px-5 py-5">
            {outcome ? <OutcomeView outcome={outcome} /> : null}
            {panel.kind === "new" || panel.kind === "edit" ? (
              <RuleForm
                key={selected?.id ?? "new"}
                editing={selected}
                units={units}
                templates={templates}
                onOutcome={settle}
                onCancel={close}
              />
            ) : null}
            {panel.kind === "targets" && selected ? (
              contacts ? (
                <TargetsForm
                  key={selected.id}
                  rule={selected}
                  contacts={contacts}
                  onOutcome={settle}
                  onCancel={close}
                />
              ) : (
                <Alert>
                  Os contatos não puderam ser lidos agora, e sem eles não há o
                  que escolher. Nada foi alterado.
                </Alert>
              )
            ) : null}
            {panel.kind === "mute" && selected ? (
              <MuteForm
                key={selected.id}
                rule={selected}
                onOutcome={settle}
                onCancel={close}
              />
            ) : null}
          </div>
        </Card>
      ) : null}
    </div>
  );
}
