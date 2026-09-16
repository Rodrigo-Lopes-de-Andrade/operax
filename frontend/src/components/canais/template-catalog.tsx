"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { MessageSquareText } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { TextField } from "@/components/ui/text-field";
import { ApiError, requestApiAsUser } from "@/lib/api";
import { label, META_STATUS_LABEL } from "@/lib/canais/labels";
import type {
  ConnectionsScreen,
  TemplateRow,
  TemplateSyncResult,
  TemplateWrite,
} from "@/lib/canais/queries";
import { formatDayInTenantZone } from "@/lib/dp/format";
import { formatClock, formatNumber } from "@/lib/ponto/format";

const CATEGORIES = ["utility", "authentication", "marketing"] as const;

/**
 * A forma de cada campo, e só a forma — o mesmo que `PUT /canais/templates`
 * confere antes de tocar o banco. O que o corpo diz é outro juiz: o gatilho
 * `util.validate_template_body` recusa corpo que não usa uma variável
 * declarada, ou usa `{{n}}` além do declarado, e a frase dele chega como
 * `detail` do 422 e é mostrada como veio. Nenhuma regra sobre `{{n}}` mora
 * aqui, de propósito: uma cópia dela no navegador divergiria da do banco, e a
 * do banco é a que vale.
 */
const CODE_HINT =
  "letras minúsculas, dígitos e sublinhado, começando por letra";
const LANGUAGE_HINT = "código de idioma como pt_BR ou en_US";
const VARIABLE_HINT =
  "nome de variável: letras minúsculas, dígitos e sublinhado, começando por letra";
const REPEATED_HINT = "variável repetida";
const META_NAME_HINT = "nome na Meta: letras minúsculas, dígitos e sublinhado";

const CODE_PATTERN = /^[a-z][a-z0-9_]{2,63}$/;
const LANGUAGE_PATTERN = /^[a-z]{2}(_[A-Z]{2})?$/;
const VARIABLE_PATTERN = /^[a-z][a-z0-9_]{0,63}$/;
const META_NAME_PATTERN = /^[a-z0-9_]{1,512}$/;

const schema = z.object({
  code: z.string().trim().regex(CODE_PATTERN, CODE_HINT),
  category: z.enum(CATEGORIES),
  language: z.string().trim().regex(LANGUAGE_PATTERN, LANGUAGE_HINT),
  variables: z
    .array(
      z.object({
        name: z.string().trim().regex(VARIABLE_PATTERN, VARIABLE_HINT),
      }),
    )
    .min(1, "Declare ao menos uma variável.")
    .superRefine((variables, ctx) => {
      const seen = new Set<string>();

      variables.forEach((variable, index) => {
        if (seen.has(variable.name)) {
          ctx.addIssue({
            code: "custom",
            path: [index, "name"],
            message: REPEATED_HINT,
          });
        }
        seen.add(variable.name);
      });
    }),
  body: z.string().min(1, "Escreva o corpo da mensagem."),
  meta_template_name: z
    .string()
    .trim()
    .refine(
      (value) => value === "" || META_NAME_PATTERN.test(value),
      META_NAME_HINT,
    ),
  active: z.boolean(),
});

type Values = z.infer<typeof schema>;

const EMPTY: Values = {
  code: "",
  category: "utility",
  language: "pt_BR",
  variables: [{ name: "" }],
  body: "",
  meta_template_name: "",
  active: true,
};

/** A linha como veio, no formato do formulário — `useFieldArray` pede objeto. */
function valuesOf(row: TemplateRow): Values {
  return {
    code: row.code,
    category: row.category,
    language: row.language,
    variables: row.variables.map((name) => ({ name })),
    body: row.body,
    meta_template_name: row.meta_template_name ?? "",
    active: row.active,
  };
}

/** O desfecho do último envio: gravou, ou não — nunca os dois ao mesmo tempo. */
type Outcome =
  { kind: "saved"; row: TemplateRow } | { kind: "error"; message: string };

type SyncOutcome =
  | { kind: "done"; result: TemplateSyncResult }
  | { kind: "error"; message: string };

function mensagem(caught: unknown, padrao: string): string {
  return caught instanceof ApiError && caught.detail ? caught.detail : padrao;
}

/** `approved` é o único que entrega; `rejected` é a Meta dizendo não. O resto espera. */
function statusTone(status: TemplateRow["meta_status"]): Tone {
  if (status === "approved") {
    return "good";
  }

  return status === "rejected" ? "bad" : "neutral";
}

const FIELD_CLASS =
  "bg-control border-control-line text-ink placeholder:text-ink-faint rounded-[10px] border px-3 text-base outline-none focus-visible:border-transparent";
const LABEL_CLASS =
  "text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase";

/**
 * Criar e editar são o mesmo formulário: editar chega com a linha preenchida e
 * o `code` travado — ele é a chave da URL e da constraint, e mudá-lo criaria
 * outro template em vez de renomear este. O pai remonta o componente pelo
 * `key` quando a linha muda, então os `defaultValues` valem pela vida dele.
 *
 * As variáveis são um input por nome, e a ordem deles é a ordem dos `{{n}}` —
 * a ajuda abaixo do corpo lê essa ordem e diz qual número cada nome ocupa.
 * É orientação para escrever o corpo, não validação: quem recusa corpo é o
 * gatilho do banco, e a frase dele é a que aparece.
 */
function TemplateForm({
  editing,
  error,
  onOutcome,
  onCancel,
}: {
  editing: TemplateRow | null;
  error: string | null;
  onOutcome: (outcome: Outcome | null) => void;
  onCancel: () => void;
}) {
  const { register, control, handleSubmit, reset, formState } = useForm<Values>(
    {
      resolver: zodResolver(schema),
      defaultValues: editing ? valuesOf(editing) : EMPTY,
    },
  );
  const { fields, append, remove } = useFieldArray({
    control,
    name: "variables",
  });
  const variables = useWatch({ control, name: "variables" });
  const variablesError =
    formState.errors.variables?.root?.message ??
    formState.errors.variables?.message;

  const onSubmit = handleSubmit(async (values) => {
    onOutcome(null);

    const write: TemplateWrite = {
      category: values.category,
      language: values.language,
      variables: values.variables.map((variable) => variable.name),
      body: values.body,
      meta_template_name:
        values.meta_template_name === "" ? null : values.meta_template_name,
      active: values.active,
    };

    try {
      const saved = await requestApiAsUser<TemplateRow>(
        `/canais/templates/${values.code}`,
        { method: "PUT", body: write },
      );
      reset(EMPTY);
      onOutcome({ kind: "saved", row: saved });
    } catch (caught) {
      onOutcome({
        kind: "error",
        message: mensagem(caught, "Não consegui gravar o template."),
      });
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      <div className="grid gap-4 sm:grid-cols-3">
        <TextField
          id="template-code"
          label="Código"
          placeholder="alerta_desvio"
          readOnly={editing !== null}
          autoComplete="off"
          error={formState.errors.code?.message}
          {...register("code")}
        />
        <label className="flex flex-col gap-1.5">
          <span className={LABEL_CLASS}>Categoria</span>
          <select
            aria-label="Categoria"
            className={`${FIELD_CLASS} h-10 text-sm`}
            {...register("category")}
          >
            {CATEGORIES.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
          <span className="text-ink-faint text-xs text-pretty">
            utility para alerta operacional; categoria errada faz a Meta
            reprovar ou cobrar como marketing
          </span>
        </label>
        <TextField
          id="template-language"
          label="Idioma"
          autoComplete="off"
          error={formState.errors.language?.message}
          {...register("language")}
        />
      </div>

      <fieldset className="flex flex-col gap-3">
        <legend className={LABEL_CLASS}>Variáveis</legend>
        <p className="text-ink-faint text-xs text-pretty">
          Uma por linha, na ordem em que entram no corpo: a primeira é{" "}
          <code className="font-mono">{"{{1}}"}</code>, a segunda{" "}
          <code className="font-mono">{"{{2}}"}</code>, e assim por diante.
        </p>
        {fields.map((field, index) => (
          <div key={field.id} className="flex items-end gap-2">
            <div className="flex-1">
              <TextField
                id={`template-variavel-${index}`}
                label={`Variável ${index + 1}`}
                autoComplete="off"
                error={formState.errors.variables?.[index]?.name?.message}
                {...register(`variables.${index}.name`)}
              />
            </div>
            <button
              type="button"
              onClick={() => remove(index)}
              disabled={fields.length === 1}
              className="text-ink-muted hover:text-ink h-10 text-xs font-bold underline disabled:opacity-60"
            >
              remover variável {index + 1}
            </button>
          </div>
        ))}
        {variablesError ? (
          <p className="text-bad text-xs font-medium">{variablesError}</p>
        ) : null}
        <div>
          <button
            type="button"
            onClick={() => append({ name: "" })}
            className="text-brand-strong text-xs font-bold underline"
          >
            adicionar variável
          </button>
        </div>
      </fieldset>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="template-body" className={LABEL_CLASS}>
          Corpo
        </label>
        <textarea
          id="template-body"
          rows={5}
          aria-invalid={formState.errors.body ? true : undefined}
          aria-describedby={
            formState.errors.body
              ? "template-body-error template-body-map"
              : "template-body-map"
          }
          className={`${FIELD_CLASS} py-2 text-sm`}
          {...register("body")}
        />
        {formState.errors.body ? (
          <p id="template-body-error" className="text-bad text-xs font-medium">
            {formState.errors.body.message}
          </p>
        ) : null}
        <ul
          id="template-body-map"
          aria-label="Variáveis no corpo"
          className="text-ink-muted flex flex-col gap-0.5 text-xs"
        >
          {variables.map((variable, index) => (
            <li key={fields[index]?.id ?? index}>
              <code className="text-ink font-mono">{`{{${index + 1}}}`}</code> ={" "}
              {variable.name.trim() || "(sem nome)"}
            </li>
          ))}
        </ul>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <TextField
            id="template-meta-name"
            label="Nome na Meta (opcional)"
            autoComplete="off"
            error={formState.errors.meta_template_name?.message}
            {...register("meta_template_name")}
          />
          <p className="text-ink-faint text-xs text-pretty">
            mudar o nome volta o status para rascunho até a próxima
            sincronização
          </p>
        </div>
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <input type="checkbox" className="size-4" {...register("active")} />
          <span className="text-ink">Ativo</span>
          <span className="text-ink-faint text-xs">
            — só template ativo conta para a regra
          </span>
        </label>
      </div>

      {error ? <Alert>{error}</Alert> : null}

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={formState.isSubmitting}>
          {formState.isSubmitting ? "Gravando…" : "Gravar template"}
        </Button>
        {editing ? (
          <button
            type="button"
            onClick={onCancel}
            className="text-ink-muted hover:text-ink text-sm font-bold"
          >
            Cancelar
          </button>
        ) : null}
      </div>
    </form>
  );
}

/** Uma linha do catálogo: o que é, como a Meta a vê, e quando mudou. */
function TemplateItem({
  row,
  onEdit,
}: {
  row: TemplateRow;
  onEdit: () => void;
}) {
  return (
    <li
      className={`flex flex-col gap-1.5 px-5 py-4 ${row.active ? "" : "opacity-60"}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <code className="text-ink font-mono text-sm font-bold">{row.code}</code>
        <Badge tone={statusTone(row.meta_status)} dot>
          {label(META_STATUS_LABEL, row.meta_status)}
        </Badge>
        {row.active ? null : <Badge tone="neutral">Inativo</Badge>}
        <button
          type="button"
          onClick={onEdit}
          aria-label={`Editar ${row.code}`}
          className="text-brand-strong ml-auto text-xs font-bold underline"
        >
          Editar
        </button>
      </div>
      <p className="text-ink-muted text-xs">
        {row.category} · {row.language} ·{" "}
        {row.meta_template_name ? (
          <>
            na Meta como{" "}
            <code className="text-ink font-mono">{row.meta_template_name}</code>
          </>
        ) : (
          "sem nome na Meta"
        )}{" "}
        · atualizado em {formatDayInTenantZone(row.updated_at)} às{" "}
        {formatClock(row.updated_at)}
      </p>
      {row.meta_rejection ? (
        <p className="text-bad text-xs text-pretty">
          Motivo: {row.meta_rejection}
        </p>
      ) : null}
    </li>
  );
}

function SyncStatus({ result }: { result: TemplateSyncResult }) {
  const total = result.meta_total;
  const updated = result.updated.length;

  return (
    <p role="status" className="text-ink text-sm font-medium text-pretty">
      {formatNumber(total)} {total === 1 ? "template" : "templates"} na WABA ·{" "}
      {formatNumber(updated)} {updated === 1 ? "atualizado" : "atualizados"}
      {result.unmatched.length > 0 ? (
        <span className="text-alert">
          {" "}
          · sem par na WABA: {result.unmatched.join(", ")}
        </span>
      ) : null}
    </p>
  );
}

/**
 * O catálogo de templates do cliente — a lista, o formulário e o "Sincronizar".
 *
 * Caminho 2 inteiro: a lista vem de `GET /canais/templates`, o formulário
 * grava em `PUT /canais/templates/{code}` e o botão chama
 * `POST /canais/templates/sincronizar`. O backend revalida papel em cada um;
 * a tela só reflete.
 *
 * O que a tela reflete e não reimplementa: `meta_status` e `meta_rejection`
 * não têm input — quem os escreve é a sincronização; mudar o nome na Meta
 * volta o status a `draft` no backend, e a nota ao lado do campo avisa em vez
 * de simular. O botão existe pelas flags (`requires_templates`), nunca pelo
 * nome do provedor: para canal sem template o corpo local é o que sai, e a
 * frase no lugar do botão diz isso.
 *
 * Vazio, a tela mostra o estado vazio **e** o formulário: produção não tem
 * template nenhum, e a primeira coisa que o operador faz aqui é criar. Depois
 * de gravar, `router.refresh()` traz a lista nova do servidor — a tela não
 * mantém uma cópia da lista que pudesse divergir do que a sincronização
 * escreveu no meio do caminho.
 */
export function TemplateCatalog({
  templates,
  connections,
}: {
  templates: TemplateRow[];
  connections: ConnectionsScreen | null;
}) {
  const router = useRouter();
  const [editing, setEditing] = useState<TemplateRow | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [sync, setSync] = useState<SyncOutcome | null>(null);

  // O botão é do canal de WhatsApp: é a WABA que se sincroniza, e é a flag
  // desse canal que decide — o Telegram não tem template para sincronizar.
  const requiresTemplates =
    connections?.whatsapp?.capabilities.requires_templates === true;

  async function synchronize() {
    setSyncing(true);
    setSync(null);

    try {
      const result = await requestApiAsUser<TemplateSyncResult>(
        "/canais/templates/sincronizar",
        { method: "POST" },
      );
      setSync({ kind: "done", result });
      router.refresh();
    } catch (caught) {
      setSync({
        kind: "error",
        message: mensagem(caught, "Não consegui sincronizar com a Meta."),
      });
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader
          eyebrow="Catálogo"
          title="Templates"
          note={`${formatNumber(templates.length)} ${templates.length === 1 ? "template" : "templates"} neste cliente`}
          action={
            requiresTemplates ? (
              <Button
                type="button"
                onClick={() => void synchronize()}
                disabled={syncing}
              >
                {syncing ? "Consultando a WABA…" : "Sincronizar com a Meta"}
              </Button>
            ) : (
              <p className="text-ink-muted max-w-xs text-xs text-pretty">
                O estado na Meta só se sincroniza com a Cloud API da Meta. Nos
                outros canais, o corpo local é o que sai.
              </p>
            )
          }
        />

        {sync ? (
          <div className="border-line-subtle border-b px-5 py-3">
            {sync.kind === "done" ? (
              <SyncStatus result={sync.result} />
            ) : (
              <Alert>{sync.message}</Alert>
            )}
          </div>
        ) : null}

        {templates.length > 0 ? (
          <ul
            aria-label="Templates do cliente"
            className="divide-line-subtle divide-y"
          >
            {templates.map((row) => (
              <TemplateItem
                key={row.code}
                row={row}
                onEdit={() => {
                  setOutcome(null);
                  setEditing(row);
                }}
              />
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={MessageSquareText}
            tone="neutral"
            title="Nenhum template neste cliente"
            description="Um template é o texto do alerta e as variáveis que ele carrega. Crie o primeiro no formulário abaixo."
          />
        )}
      </Card>

      <Card>
        <CardHeader
          eyebrow="Template"
          title={editing ? `Editar ${editing.code}` : "Novo template"}
          note="O estado na Meta não se edita aqui: quem o escreve é a sincronização."
        />
        <div className="flex flex-col gap-4 px-5 py-5">
          {outcome?.kind === "saved" ? (
            <p role="status" className="text-good text-sm font-medium">
              Template {outcome.row.code} gravado.
            </p>
          ) : null}
          <TemplateForm
            key={editing?.code ?? "new"}
            editing={editing}
            error={outcome?.kind === "error" ? outcome.message : null}
            onOutcome={(next) => {
              setOutcome(next);
              if (next?.kind === "saved") {
                setEditing(null);
                router.refresh();
              }
            }}
            onCancel={() => {
              setOutcome(null);
              setEditing(null);
            }}
          />
        </div>
      </Card>
    </div>
  );
}
