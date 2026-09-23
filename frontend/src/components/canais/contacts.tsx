"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";

import type { UnitChoice } from "@/components/dp/work-posts";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { TextField } from "@/components/ui/text-field";
import {
  CONTACT_TYPE_LABEL,
  CONTACT_TYPES,
  createContact,
  deactivateContact,
  EMAIL_PATTERN,
  failureMessage,
  holdingRules,
  replaceContactUnits,
  RESPONSIBILITIES,
  RESPONSIBILITY_LABEL,
  responsibilitiesFor,
  updateContact,
  WHATSAPP_PATTERN,
  type ContactRow,
  type ContactWrite,
  type HoldingRule,
  type UnitResponsibilityWrite,
} from "@/lib/canais/regras";
import { ruleHref } from "@/lib/canais/url";
import { formatNumber } from "@/lib/ponto/format";

const FIELD_CLASS =
  "bg-control border-control-line text-ink placeholder:text-ink-faint rounded-[10px] border px-3 text-base outline-none focus-visible:border-transparent";
const LABEL_CLASS =
  "text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase";

/** A regra 7 dita ao lado do seletor de tipo, sempre — antes de a pessoa escolher. */
const GROUP_NOTE =
  "Um grupo de WhatsApp só recebe regra agregada: conteúdo individual nunca vai para grupo.";

const WHATSAPP_HINT =
  "número no formato internacional, só dígitos: 5511999990000";
const EMAIL_HINT = "isto não parece um e-mail";
const ADDRESS_HINT = "informe ao menos um endereço: WhatsApp ou e-mail";

/**
 * A forma de cada campo, e só a forma — o mesmo que `ContactWrite` confere no
 * backend antes de tocar o banco (nome 1..120, o `check` do WhatsApp, o
 * `pattern` do e-mail, e ao menos um dos dois). Vazio é nulo no corpo.
 */
const contactSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, "Informe o nome.")
      .max(120, "No máximo 120 caracteres."),
    whatsapp: z
      .string()
      .trim()
      .refine(
        (value) => value === "" || WHATSAPP_PATTERN.test(value),
        WHATSAPP_HINT,
      ),
    email: z
      .string()
      .trim()
      .refine(
        (value) =>
          value === "" ||
          (value.length >= 3 &&
            value.length <= 254 &&
            EMAIL_PATTERN.test(value)),
        EMAIL_HINT,
      ),
    type: z.enum(CONTACT_TYPES),
  })
  .superRefine((values, ctx) => {
    if (values.whatsapp === "" && values.email === "") {
      ctx.addIssue({
        code: "custom",
        path: ["whatsapp"],
        message: ADDRESS_HINT,
      });
    }
  });

type ContactValues = z.infer<typeof contactSchema>;

const EMPTY_CONTACT: ContactValues = {
  name: "",
  whatsapp: "",
  email: "",
  type: "person",
};

function contactValues(row: ContactRow): ContactValues {
  return {
    name: row.name,
    whatsapp: row.whatsapp ?? "",
    email: row.email ?? "",
    type: row.type,
  };
}

/**
 * A matriz: sem repetição de `(unidade, responsabilidade)` — é a chave única
 * de `app.unit_responsible`, e o backend recusa 422 a repetição.
 */
const unitsSchema = z.object({
  units: z
    .array(
      z.object({
        unit_id: z.string().min(1, "Escolha a unidade."),
        responsibility: z.enum(RESPONSIBILITIES),
        is_primary: z.boolean(),
      }),
    )
    .superRefine((units, ctx) => {
      const seen = new Set<string>();

      units.forEach((unit, index) => {
        const key = `${unit.unit_id}:${unit.responsibility}`;

        if (seen.has(key)) {
          ctx.addIssue({
            code: "custom",
            path: [index, "responsibility"],
            message:
              "a mesma responsabilidade na mesma unidade aparece duas vezes",
          });
        }
        seen.add(key);
      });
    }),
});

type UnitsValues = z.infer<typeof unitsSchema>;

/** O que a tela está fazendo com um contato, ou nada. */
type Panel =
  | { kind: "new" }
  | { kind: "edit"; contactId: string }
  | { kind: "units"; contactId: string }
  | { kind: "deactivate"; contactId: string };

/**
 * O desfecho da última escrita. `held` é o 409 que lista regras: o `detail`
 * como veio e as regras com link — a pessoa vai até cada uma, troca o
 * destino ou desliga, e volta.
 */
type Outcome =
  | { kind: "saved"; message: string }
  | { kind: "error"; message: string }
  | { kind: "held"; message: string; rules: HoldingRule[] };

function outcomeOf(caught: unknown, fallback: string): Outcome {
  const rules = holdingRules(caught);
  const message = failureMessage(caught, fallback);

  return rules.length > 0
    ? { kind: "held", message, rules }
    : { kind: "error", message };
}

/** O 409 que segura o contato: a frase do backend e as regras, cada uma com link. */
function HeldByRules({
  message,
  rules,
}: {
  message: string;
  rules: HoldingRule[];
}) {
  return (
    <div
      role="alert"
      className="bg-bad-bg text-bad flex flex-col gap-2 rounded-[10px] px-3 py-2 text-sm font-medium"
    >
      <p>{message}</p>
      <ul
        aria-label="Regras que seguram o contato"
        className="flex flex-col gap-1"
      >
        {rules.map((rule) => (
          <li key={rule.id}>
            <Link href={ruleHref(rule.id)} className="underline">
              {rule.name}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function OutcomeView({ outcome }: { outcome: Outcome }) {
  if (outcome.kind === "saved") {
    return (
      <p role="status" className="text-good text-sm font-medium">
        {outcome.message}
      </p>
    );
  }

  if (outcome.kind === "held") {
    return <HeldByRules message={outcome.message} rules={outcome.rules} />;
  }

  return <Alert>{outcome.message}</Alert>;
}

/**
 * Criar e editar são o mesmo formulário; o pai remonta pelo `key` quando o
 * contato muda. O tipo mostra o rótulo e envia o valor; a nota da regra 7
 * fica ao lado do seletor sempre, não só quando "grupo" está escolhido.
 *
 * Os 422 e 409 do backend chegam como `detail` e são mostrados como vieram:
 * `group_responsibility` (virar grupo com responsabilidade que não é
 * `group` na matriz) e `individual_to_group` (virar grupo sendo destino de
 * regra individual).
 */
function ContactForm({
  editing,
  onOutcome,
  onCancel,
}: {
  editing: ContactRow | null;
  onOutcome: (outcome: Outcome | null, saved: boolean) => void;
  onCancel: () => void;
}) {
  const { register, handleSubmit, formState } = useForm<ContactValues>({
    resolver: zodResolver(contactSchema),
    defaultValues: editing ? contactValues(editing) : EMPTY_CONTACT,
  });

  const onSubmit = handleSubmit(async (values) => {
    onOutcome(null, false);

    const write: ContactWrite = {
      name: values.name,
      whatsapp: values.whatsapp === "" ? null : values.whatsapp,
      email: values.email === "" ? null : values.email,
      type: values.type,
    };

    try {
      const saved = editing
        ? await updateContact(editing.id, write)
        : await createContact(write);
      onOutcome(
        { kind: "saved", message: `Contato ${saved.name} gravado.` },
        true,
      );
    } catch (caught) {
      onOutcome(outcomeOf(caught, "Não consegui gravar o contato."), false);
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          id="contact-name"
          label="Nome"
          autoComplete="off"
          error={formState.errors.name?.message}
          {...register("name")}
        />
        <div className="flex flex-col gap-1.5">
          <label htmlFor="contact-type" className={LABEL_CLASS}>
            Tipo
          </label>
          <select
            id="contact-type"
            className={`${FIELD_CLASS} h-10 text-sm`}
            {...register("type")}
          >
            {CONTACT_TYPES.map((type) => (
              <option key={type} value={type}>
                {CONTACT_TYPE_LABEL[type]}
              </option>
            ))}
          </select>
          <p className="text-ink-faint text-xs text-pretty">{GROUP_NOTE}</p>
        </div>
        <TextField
          id="contact-whatsapp"
          label="WhatsApp"
          inputMode="tel"
          autoComplete="off"
          placeholder="5511999990000"
          error={formState.errors.whatsapp?.message}
          {...register("whatsapp")}
        />
        <TextField
          id="contact-email"
          label="E-mail"
          type="email"
          inputMode="email"
          autoComplete="off"
          error={formState.errors.email?.message}
          {...register("email")}
        />
      </div>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={formState.isSubmitting}>
          {formState.isSubmitting ? "Gravando…" : "Gravar contato"}
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
 * A matriz unidade × responsabilidade de um contato, substituída de uma vez
 * (`PUT /unidades`). As unidades vêm de `public.vw_unit` pelo Caminho 1,
 * como o resto do painel; as responsabilidades são as que o tipo do contato
 * admite — um grupo de WhatsApp só entra como "Grupo".
 *
 * O 409 `contact_last_responsible` pode vir daqui: a matriz nova tira a
 * responsabilidade que uma regra ligada resolve, e ninguém mais a tem na
 * unidade. Chega com as regras, e é a mesma renderização de "desativar".
 */
function UnitsForm({
  contact,
  units,
  onOutcome,
  onCancel,
}: {
  contact: ContactRow;
  units: UnitChoice[];
  onOutcome: (outcome: Outcome | null, saved: boolean) => void;
  onCancel: () => void;
}) {
  const allowed = responsibilitiesFor(contact.type);
  const { register, control, handleSubmit, formState } = useForm<UnitsValues>({
    resolver: zodResolver(unitsSchema),
    defaultValues: {
      units: contact.units.map((row) => ({
        unit_id: row.unit_id,
        responsibility: row.responsibility,
        is_primary: row.is_primary,
      })),
    },
  });
  const { fields, append, remove } = useFieldArray({ control, name: "units" });

  const onSubmit = handleSubmit(async (values) => {
    onOutcome(null, false);

    const write: UnitResponsibilityWrite[] = values.units.map((row) => ({
      unit_id: row.unit_id,
      responsibility: row.responsibility,
      is_primary: row.is_primary,
    }));

    try {
      await replaceContactUnits(contact.id, write);
      onOutcome(
        { kind: "saved", message: `Unidades de ${contact.name} gravadas.` },
        true,
      );
    } catch (caught) {
      onOutcome(
        outcomeOf(caught, "Não consegui gravar as unidades do contato."),
        false,
      );
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {contact.type === "whatsapp_group" ? (
        <p className="text-ink-muted text-sm text-pretty">{GROUP_NOTE}</p>
      ) : null}
      {fields.length === 0 ? (
        <p className="text-ink-muted text-sm">
          Nenhuma unidade: este contato só recebe regra que o nomeie
          diretamente.
        </p>
      ) : null}
      {fields.map((field, index) => (
        <fieldset
          key={field.id}
          className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto_auto]"
        >
          <legend className="sr-only">Linha {index + 1}</legend>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={`unit-${index}`} className={LABEL_CLASS}>
              Unidade
            </label>
            <select
              id={`unit-${index}`}
              className={`${FIELD_CLASS} h-10 text-sm`}
              aria-invalid={
                formState.errors.units?.[index]?.unit_id ? true : undefined
              }
              {...register(`units.${index}.unit_id`)}
            >
              <option value="">Escolha…</option>
              {units.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.name}
                </option>
              ))}
            </select>
            {formState.errors.units?.[index]?.unit_id ? (
              <p className="text-bad text-xs font-medium">
                {formState.errors.units[index].unit_id.message}
              </p>
            ) : null}
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={`responsibility-${index}`} className={LABEL_CLASS}>
              Responsabilidade
            </label>
            <select
              id={`responsibility-${index}`}
              className={`${FIELD_CLASS} h-10 text-sm`}
              {...register(`units.${index}.responsibility`)}
            >
              {allowed.map((responsibility) => (
                <option key={responsibility} value={responsibility}>
                  {RESPONSIBILITY_LABEL[responsibility]}
                </option>
              ))}
            </select>
            {formState.errors.units?.[index]?.responsibility ? (
              <p className="text-bad text-xs font-medium">
                {formState.errors.units[index].responsibility.message}
              </p>
            ) : null}
          </div>
          <label className="flex h-10 items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4"
              {...register(`units.${index}.is_primary`)}
            />
            <span className="text-ink">Primário</span>
          </label>
          <button
            type="button"
            onClick={() => remove(index)}
            className="text-ink-muted hover:text-ink h-10 text-xs font-bold underline"
          >
            remover linha {index + 1}
          </button>
        </fieldset>
      ))}
      <div>
        <button
          type="button"
          onClick={() =>
            append({
              unit_id: "",
              responsibility: allowed[0],
              is_primary: false,
            })
          }
          className="text-brand-strong text-xs font-bold underline"
        >
          adicionar unidade
        </button>
      </div>
      <p className="text-ink-faint text-xs text-pretty">
        Entre dois contatos com a mesma responsabilidade na unidade, o alerta
        vai para o primário.
      </p>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={formState.isSubmitting}>
          {formState.isSubmitting ? "Gravando…" : "Gravar unidades"}
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
 * Desativar, com a confirmação em texto. Nunca "excluir": o contato fica na
 * lista, marcado, porque pode ser destino de regra e alvo de auditoria. O
 * 409 (`contact_in_active_rule`, `contact_last_responsible`) chega com as
 * regras e a frase do backend, e nada muda.
 */
function DeactivateConfirm({
  contact,
  onOutcome,
  onCancel,
}: {
  contact: ContactRow;
  onOutcome: (outcome: Outcome | null, saved: boolean) => void;
  onCancel: () => void;
}) {
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setBusy(true);
    onOutcome(null, false);

    try {
      await deactivateContact(contact.id);
      onOutcome(
        { kind: "saved", message: `Contato ${contact.name} desativado.` },
        true,
      );
    } catch (caught) {
      onOutcome(outcomeOf(caught, "Não consegui desativar o contato."), false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-ink text-sm text-pretty">
        Desativar <strong>{contact.name}</strong>? O contato deixa de receber
        alerta e de contar como destino, mas continua na lista, marcado como
        inativo — o histórico fica.
      </p>
      <div className="flex items-center gap-3">
        <Button type="button" onClick={() => void confirm()} disabled={busy}>
          {busy ? "Desativando…" : "Confirmar desativação"}
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

/** Uma linha da lista: quem é, por onde, e onde responde. Inativo aparece, marcado. */
function ContactItem({
  contact,
  onOpen,
}: {
  contact: ContactRow;
  onOpen: (panel: Panel) => void;
}) {
  return (
    <li
      className={`flex flex-col gap-1.5 px-5 py-4 ${contact.active ? "" : "opacity-60"}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-ink text-sm font-bold">{contact.name}</span>
        <Badge tone={contact.type === "whatsapp_group" ? "alert" : "neutral"}>
          {CONTACT_TYPE_LABEL[contact.type]}
        </Badge>
        {contact.active ? null : <Badge tone="neutral">Inativo</Badge>}
        <div className="ml-auto flex items-center gap-3">
          <button
            type="button"
            onClick={() => onOpen({ kind: "edit", contactId: contact.id })}
            aria-label={`Editar ${contact.name}`}
            className="text-brand-strong text-xs font-bold underline"
          >
            Editar
          </button>
          <button
            type="button"
            onClick={() => onOpen({ kind: "units", contactId: contact.id })}
            aria-label={`Unidades de ${contact.name}`}
            className="text-brand-strong text-xs font-bold underline"
          >
            Unidades
          </button>
          {contact.active ? (
            <button
              type="button"
              onClick={() =>
                onOpen({ kind: "deactivate", contactId: contact.id })
              }
              aria-label={`Desativar ${contact.name}`}
              className="text-ink-muted hover:text-ink text-xs font-bold underline"
            >
              Desativar
            </button>
          ) : null}
        </div>
      </div>
      <p className="text-ink-muted text-xs">
        {contact.whatsapp ? (
          <>
            WhatsApp{" "}
            <span className="text-ink font-mono">{contact.whatsapp}</span>
          </>
        ) : (
          "sem WhatsApp"
        )}
        {" · "}
        {contact.email ? (
          <>
            e-mail <span className="text-ink font-mono">{contact.email}</span>
          </>
        ) : (
          "sem e-mail"
        )}
      </p>
      {contact.units.length > 0 ? (
        <ul
          aria-label={`Unidades de ${contact.name}`}
          className="text-ink-muted flex flex-wrap gap-x-3 gap-y-0.5 text-xs"
        >
          {contact.units.map((row) => (
            <li key={`${row.unit_id}:${row.responsibility}`}>
              {row.unit_name} · {RESPONSIBILITY_LABEL[row.responsibility]}
              {row.is_primary ? " (primário)" : ""}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-ink-faint text-xs">Sem unidade na matriz.</p>
      )}
    </li>
  );
}

/**
 * Destinatários — a lista, e um painel por vez: novo contato, editar,
 * unidades, desativar.
 *
 * Caminho 2 inteiro, menos as unidades do seletor (`vw_unit`, Caminho 1). O
 * backend revalida papel em cada escrita; a tela só reflete. Depois de
 * gravar, `router.refresh()` traz a lista nova do servidor — a tela não
 * mantém cópia que pudesse divergir.
 */
export function Contacts({
  contacts,
  units,
}: {
  contacts: ContactRow[];
  units: UnitChoice[];
}) {
  const router = useRouter();
  const [panel, setPanel] = useState<Panel | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  const selected =
    panel && panel.kind !== "new"
      ? (contacts.find((contact) => contact.id === panel.contactId) ?? null)
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

  const title =
    panel?.kind === "new"
      ? "Novo contato"
      : panel?.kind === "edit" && selected
        ? `Editar ${selected.name}`
        : panel?.kind === "units" && selected
          ? `Unidades de ${selected.name}`
          : panel?.kind === "deactivate" && selected
            ? `Desativar ${selected.name}`
            : null;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader
          eyebrow="Destinatários"
          title="Contatos"
          note={`${formatNumber(contacts.length)} ${contacts.length === 1 ? "contato" : "contatos"} neste cliente`}
          action={
            <Button type="button" onClick={() => open({ kind: "new" })}>
              Novo contato
            </Button>
          }
        />
        {outcome && !panel ? (
          <div className="border-line-subtle border-b px-5 py-3">
            <OutcomeView outcome={outcome} />
          </div>
        ) : null}
        {contacts.length > 0 ? (
          <ul
            aria-label="Contatos do cliente"
            className="divide-line-subtle divide-y"
          >
            {contacts.map((contact) => (
              <ContactItem key={contact.id} contact={contact} onOpen={open} />
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={Users}
            tone="neutral"
            title="Nenhum contato neste cliente"
            description="Um contato é quem recebe o alerta: pessoa, grupo de WhatsApp ou lista de e-mail. Cadastre o primeiro — de preferência você, para testar as regras antes de ligar."
          />
        )}
      </Card>

      {panel && title ? (
        <Card>
          <CardHeader eyebrow="Contato" title={title} />
          <div className="flex flex-col gap-4 px-5 py-5">
            {outcome ? <OutcomeView outcome={outcome} /> : null}
            {panel.kind === "new" || panel.kind === "edit" ? (
              <ContactForm
                key={selected?.id ?? "new"}
                editing={selected}
                onOutcome={settle}
                onCancel={close}
              />
            ) : null}
            {panel.kind === "units" && selected ? (
              <UnitsForm
                key={selected.id}
                contact={selected}
                units={units}
                onOutcome={settle}
                onCancel={close}
              />
            ) : null}
            {panel.kind === "deactivate" && selected ? (
              <DeactivateConfirm
                contact={selected}
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
