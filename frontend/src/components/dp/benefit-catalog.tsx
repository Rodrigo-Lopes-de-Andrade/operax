"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Check, Plus, Tags } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Table, type Column } from "@/components/ui/table";
import { TextField } from "@/components/ui/text-field";
import { ApiError, requestApiAsUser } from "@/lib/api";
import { formatBand, formatCurrency, formatDate } from "@/lib/dp/format";
import { catalogHref, type CatalogFilters } from "@/lib/dp/url";
import type {
  BenefitCatalog as Catalog,
  BenefitTypeRow,
} from "@/lib/dp/queries";

/**
 * O código de verba cujo catálogo de preços são **tarifas**, e não planos.
 *
 * É vocabulário da semente (SPEC-DP §1d), não regra de cálculo: `transport_fare`
 * não carrega o tipo a que pertence, e a aba precisa saber o que mostrar. Onde
 * o dinheiro é decidido — quem compõe a folha base, quanto vale a tarifa — quem
 * responde continua sendo o backend.
 */
const TRANSPORT_VOUCHER = "transport_voucher";

const COLUMNS: Column[] = [
  { key: "identidade", label: "Item" },
  { key: "valor", label: "Valor vigente", align: "right", width: "16%" },
  { key: "vigencia", label: "Vigência", width: "24%" },
  { key: "motivo", label: "Motivo", width: "18%" },
  { key: "acao", label: "", align: "right", width: "14%" },
];

type Band = {
  id: string;
  target: "plan" | "fare";
  code: string;
  kind: string | null;
  name: string;
  detail: string | null;
  amount: string;
  effective_from: string;
  effective_to: string | null;
  reason: string | null;
};

type NewBand = {
  target: "plan" | "fare";
  code: string;
  kind: string | null;
  name: string;
  amount: string;
  effective_from: string;
};

type AdjustedBand = NewBand & {
  previous_amount: string;
  previous_effective_to: string;
};

const KIND_LABEL: Record<string, string> = {
  single: "unitário",
  round_trip: "ida e volta",
};

/**
 * Catálogo de benefícios — preço com vigência, por tipo.
 *
 * ⛔ NÃO EXISTE LÁPIS NO VALOR VIGENTE, E A AUSÊNCIA É O DESENHO
 * Um reajuste é **linha nova**: a faixa que sai mantém o valor que valeu,
 * porque o ciclo do mês passado foi apurado com ele. Um campo editável aqui
 * produziria um catálogo que afirma que o preço sempre foi o de agora — e o
 * ciclo já fechado passaria a não bater com o próprio arquivo que gerou. Por
 * isso o valor da faixa aberta é texto, e a única ação é "Reajustar".
 *
 * ⚠️ CRIAR A PRIMEIRA E REAJUSTAR SÃO DUAS PORTAS DIFERENTES
 * São duas rotas no backend por decisão do dono: uma porta só transformaria um
 * código digitado errado no formulário de reajuste num plano novo, calado,
 * enquanto o preço antigo continuaria valendo para quem já estava lá. A tela
 * respeita a separação — "Cadastrar" abre item novo, "Reajustar" só existe em
 * cima de uma faixa que já está aberta.
 */
export function BenefitCatalog({
  catalog,
  filters,
  type,
}: {
  catalog: Catalog;
  filters: CatalogFilters;
  type: BenefitTypeRow;
}) {
  const router = useRouter();
  const [open, setOpen] = useState<
    { mode: "create" } | { mode: "adjust"; band: Band } | null
  >(null);
  const [done, setDone] = useState<string | null>(null);

  const fares = type.code === TRANSPORT_VOUCHER;
  const bands = fares ? fareBands(catalog) : planBands(catalog, type.code);
  const rotulo = fares ? "tarifa" : "plano";

  function concluido(mensagem: string) {
    setOpen(null);
    setDone(mensagem);
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      <CatalogDate filters={filters} on={catalog.on} />

      <Card>
        <CardHeader
          eyebrow={type.active ? "Verba" : "Verba inativa"}
          title={type.name}
          note={
            type.composes_base
              ? "Compõe a folha salarial base — muda o custo de pessoal que o painel mostra."
              : "Fora da folha salarial base — é benefício, e não entra no custo de remuneração."
          }
          action={
            catalog.can_write ? (
              <Button onClick={() => setOpen({ mode: "create" })}>
                <Plus size={15} aria-hidden />
                {fares ? "Nova tarifa" : "Novo plano"}
              </Button>
            ) : null
          }
        />

        <div className="flex flex-wrap gap-2 px-5 py-4">
          <Badge tone={type.composes_base ? "brand" : "neutral"}>
            {type.composes_base ? "Compõe a base" : "Fora da base"}
          </Badge>
          <Badge tone="neutral">
            {type.calculation === "salary_rate"
              ? "Taxa sobre o salário"
              : "Valor fixo"}
          </Badge>
          <Badge tone={type.active ? "good" : "neutral"} dot>
            {type.active ? "Ativa" : "Inativa"}
          </Badge>
        </div>

        {done ? (
          <p className="text-ink-muted flex items-center gap-2 px-5 pb-4 text-sm text-pretty">
            <Check size={16} aria-hidden className="text-good" />
            {done}
          </p>
        ) : null}

        {bands.length > 0 ? (
          <Table
            columns={COLUMNS}
            caption={`Preços vigentes de ${type.name}`}
            rows={bands.map((band) => ({
              id: band.id,
              cells: {
                identidade: (
                  <span className="flex flex-col">
                    <span className="text-ink font-semibold">{band.name}</span>
                    <span className="text-ink-faint font-mono text-xs">
                      {band.code}
                      {band.kind
                        ? ` · ${KIND_LABEL[band.kind] ?? band.kind}`
                        : ""}
                      {band.detail ? ` · ${band.detail}` : ""}
                    </span>
                  </span>
                ),
                valor: (
                  <span className="text-ink font-bold tabular-nums">
                    {formatCurrency(band.amount)}
                  </span>
                ),
                vigencia: formatBand(band.effective_from, band.effective_to),
                motivo: band.reason,
                acao: catalog.can_write ? (
                  <button
                    type="button"
                    onClick={() => {
                      setDone(null);
                      setOpen({ mode: "adjust", band });
                    }}
                    className="text-brand-strong text-xs font-bold underline"
                  >
                    Reajustar
                  </button>
                ) : null,
              },
            }))}
          />
        ) : (
          <div className="px-5 pb-5">
            <EmptyState
              icon={Tags}
              tone="neutral"
              compact
              title={`Nenhum${fares ? "a" : ""} ${rotulo} cadastrad${fares ? "a" : "o"} em ${formatDate(catalog.on)}`}
              description={
                fares
                  ? "O catálogo de tarifas nasce vazio, e o vale transporte lê a tarifa daqui: sem a primeira vigência, a apuração do mês recusa por falta de valor de ida e volta."
                  : "O catálogo deste tipo nasce vazio. Cadastre a primeira vigência para que ele passe a valer a partir de uma data."
              }
            >
              {catalog.can_write ? (
                <Button onClick={() => setOpen({ mode: "create" })}>
                  <Plus size={15} aria-hidden />
                  Cadastrar {fares ? "a primeira tarifa" : "o primeiro plano"}
                </Button>
              ) : null}
            </EmptyState>
          </div>
        )}
      </Card>

      {open?.mode === "create" ? (
        <Card>
          <CardHeader
            title={`${rotulo === "tarifa" ? "Nova tarifa" : "Novo plano"}`}
            note="Esta é a PRIMEIRA vigência do item — ela nasce aberta, e a data de fim é escrita pelo reajuste que a substituir. Para mudar o valor de algo que já existe, use Reajustar."
          />
          <FirstBandForm
            typeCode={type.code}
            fare={fares}
            onDone={concluido}
            onCancel={() => setOpen(null)}
          />
        </Card>
      ) : null}

      {open?.mode === "adjust" ? (
        <Card>
          <CardHeader
            eyebrow={open.band.name}
            title="Reajuste"
            note="O reajuste é uma vigência nova: a faixa atual é fechada no dia anterior e mantém o valor que valeu. Nada do que já foi apurado muda."
          />
          <AdjustBandForm
            band={open.band}
            onDone={concluido}
            onCancel={() => setOpen(null)}
          />
        </Card>
      ) : null}
    </div>
  );
}

/**
 * A data em que o catálogo é lido, na query string.
 *
 * Preço tem vigência, e o catálogo sem data é o de hoje — que no dia seguinte a
 * um reajuste responde outra coisa. Quem confere um ciclo do mês passado precisa
 * do preço daquele dia, e o link tem de carregá-lo.
 */
function CatalogDate({ filters, on }: { filters: CatalogFilters; on: string }) {
  const router = useRouter();

  return (
    <div className="border-line-subtle bg-card flex flex-wrap items-end gap-4 rounded-[18px] border px-5 py-4">
      <label className="flex flex-col gap-1.5">
        <span className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
          Catálogo em
        </span>
        <input
          type="date"
          value={on}
          aria-label="Data da vigência consultada"
          onChange={(event) =>
            router.push(
              catalogHref(filters, { on: event.target.value || null }),
            )
          }
          className="border-control-line bg-control text-ink h-10 rounded-[10px] border px-3 text-sm"
        />
      </label>
      <p className="text-ink-faint max-w-xl text-xs text-pretty">
        Os valores abaixo são os que valiam em {formatDate(on)}. Um reajuste não
        apaga o preço anterior — ele abre a próxima vigência, e esta data é como
        se volta à que valeu.
      </p>
    </div>
  );
}

const schemaAdjust = z.object({
  effective_from: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Informe a data em que o novo valor começa."),
  amount: z
    .string()
    .regex(/^\d+(\.\d{1,2})?$/, "Informe o valor com até duas casas."),
  reason: z.string().max(200, "O motivo cabe em 200 caracteres.").optional(),
});

function AdjustBandForm({
  band,
  onDone,
  onCancel,
}: {
  band: Band;
  onDone: (mensagem: string) => void;
  onCancel: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm({
    resolver: zodResolver(schemaAdjust),
    defaultValues: { effective_from: "", amount: "", reason: "" },
  });

  const onSubmit = handleSubmit(async (valores) => {
    setError(null);

    try {
      // ⛔ Nada aqui identifica a linha a alterar, e é o desenho: o backend
      // acha a faixa aberta pelo alvo e pela identidade, fecha-a e abre a
      // próxima. Mandar o id da faixa seria pedir uma edição.
      const nova = await requestApiAsUser<AdjustedBand>(
        "/dp/beneficios/reajuste",
        {
          method: "POST",
          body: {
            target: band.target,
            code: band.code,
            kind: band.kind,
            effective_from: valores.effective_from,
            amount: valores.amount,
            reason: valores.reason?.trim() || null,
          },
        },
      );

      onDone(
        `${formatCurrency(nova.previous_amount)} até ${formatDate(nova.previous_effective_to)}, ` +
          `${formatCurrency(nova.amount)} a partir de ${formatDate(nova.effective_from)}.`,
      );
    } catch (caught) {
      setError(mensagem(caught, "Não consegui registrar o reajuste."));
    }
  });

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="flex flex-col gap-4 px-5 py-5"
    >
      <p className="text-ink-muted text-sm text-pretty">
        Valor atual de <strong className="text-ink">{band.name}</strong>:{" "}
        <strong className="text-ink">{formatCurrency(band.amount)}</strong>,{" "}
        {formatBand(band.effective_from, band.effective_to)}. Ele continua
        valendo até o dia anterior ao novo.
      </p>

      <div className="grid gap-4 sm:grid-cols-3">
        <TextField
          id="reajuste-desde"
          label="Desde"
          type="date"
          error={formState.errors.effective_from?.message}
          {...register("effective_from")}
        />
        <TextField
          id="reajuste-valor"
          label="Novo valor"
          type="number"
          step="0.01"
          min="0"
          error={formState.errors.amount?.message}
          {...register("amount")}
        />
        <TextField
          id="reajuste-motivo"
          label="Motivo"
          placeholder="Reajuste anual, dissídio…"
          error={formState.errors.reason?.message}
          {...register("reason")}
        />
      </div>

      {error ? <Alert>{error}</Alert> : null}

      <div className="flex items-center gap-2">
        <Button type="submit" disabled={formState.isSubmitting}>
          {formState.isSubmitting ? "Registrando…" : "Registrar reajuste"}
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

const schemaPlan = z.object({
  code: z.string().trim().min(1, "Informe o código do item."),
  name: z.string().trim().min(1, "Informe o nome do item."),
  provider: z.string().trim().min(1, "Informe a operadora."),
  effective_from: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Informe a data em que o valor começa."),
  amount: z
    .string()
    .regex(/^\d+(\.\d{1,2})?$/, "Informe o valor com até duas casas."),
  reason: z.string().max(200, "O motivo cabe em 200 caracteres.").optional(),
});

const schemaFare = z.object({
  code: z.string().trim().min(1, "Informe o código da linha."),
  name: z.string().trim().min(1, "Informe o nome da linha."),
  kind: z.enum(["single", "round_trip"]),
  effective_from: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Informe a data em que o valor começa."),
  amount: z
    .string()
    .regex(/^\d+(\.\d{1,2})?$/, "Informe o valor com até duas casas."),
  reason: z.string().max(200, "O motivo cabe em 200 caracteres.").optional(),
});

/**
 * A primeira vigência de um plano ou de uma tarifa.
 *
 * Sem campo de fim, e a ausência é do contrato: uma vigência nasce aberta, e a
 * data de fim é escrita pelo reajuste que a substituir. Um campo de fim aqui
 * convidaria a cadastrar um preço que já nasce vencido.
 *
 * A tarifa unitária e a de ida e volta são dois cadastros, não um com dobro:
 * `round_trip` não é sempre duas vezes `single` — integração e desconto de linha
 * quebram a conta —, e é a de ida e volta que o apurador multiplica por dias
 * líquidos.
 */
function FirstBandForm({
  typeCode,
  fare,
  onDone,
  onCancel,
}: {
  typeCode: string;
  fare: boolean;
  onDone: (mensagem: string) => void;
  onCancel: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const plano = useForm({
    resolver: zodResolver(schemaPlan),
    defaultValues: {
      code: "",
      name: "",
      provider: "",
      effective_from: "",
      amount: "",
      reason: "",
    },
  });
  const tarifa = useForm({
    resolver: zodResolver(schemaFare),
    defaultValues: {
      code: "",
      name: "",
      kind: "round_trip" as "single" | "round_trip",
      effective_from: "",
      amount: "",
      reason: "",
    },
  });

  async function enviar(path: string, body: Record<string, unknown>) {
    setError(null);

    try {
      const nova = await requestApiAsUser<NewBand>(path, {
        method: "POST",
        body,
      });
      onDone(
        `${nova.name} cadastrad${fare ? "a" : "o"} por ${formatCurrency(nova.amount)}, a partir de ${formatDate(nova.effective_from)}.`,
      );
    } catch (caught) {
      setError(
        mensagem(
          caught,
          `Não consegui cadastrar ${fare ? "a tarifa" : "o plano"}.`,
        ),
      );
    }
  }

  if (fare) {
    const onSubmit = tarifa.handleSubmit((valores) =>
      enviar("/dp/beneficios/tarifas", {
        code: valores.code.trim(),
        name: valores.name.trim(),
        kind: valores.kind,
        effective_from: valores.effective_from,
        amount: valores.amount,
        reason: valores.reason?.trim() || null,
      }),
    );

    return (
      <form
        onSubmit={onSubmit}
        noValidate
        className="flex flex-col gap-4 px-5 py-5"
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <TextField
            id="tarifa-codigo"
            label="Código da linha"
            error={tarifa.formState.errors.code?.message}
            {...tarifa.register("code")}
          />
          <TextField
            id="tarifa-nome"
            label="Nome"
            placeholder="Ônibus, Metrô, Integração…"
            error={tarifa.formState.errors.name?.message}
            {...tarifa.register("name")}
          />
          <label className="flex flex-col gap-1.5">
            <span className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
              Tipo
            </span>
            <select
              aria-label="Tipo da tarifa"
              className="border-control-line bg-control text-ink h-10 rounded-[10px] border px-3 text-sm"
              {...tarifa.register("kind")}
            >
              <option value="round_trip">Ida e volta</option>
              <option value="single">Unitário</option>
            </select>
          </label>
          <TextField
            id="tarifa-desde"
            label="Desde"
            type="date"
            error={tarifa.formState.errors.effective_from?.message}
            {...tarifa.register("effective_from")}
          />
          <TextField
            id="tarifa-valor"
            label="Valor"
            type="number"
            step="0.01"
            min="0"
            error={tarifa.formState.errors.amount?.message}
            {...tarifa.register("amount")}
          />
          <TextField
            id="tarifa-motivo"
            label="Motivo"
            placeholder="Cadastro inicial"
            error={tarifa.formState.errors.reason?.message}
            {...tarifa.register("reason")}
          />
        </div>

        <p className="text-ink-faint text-xs text-pretty">
          A tarifa de ida e volta é a que o vale transporte multiplica por dias
          líquidos. A unitária entra como segundo cadastro, com o mesmo código.
        </p>

        {error ? <Alert>{error}</Alert> : null}

        <div className="flex items-center gap-2">
          <Button type="submit" disabled={tarifa.formState.isSubmitting}>
            {tarifa.formState.isSubmitting
              ? "Cadastrando…"
              : "Cadastrar tarifa"}
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

  const onSubmit = plano.handleSubmit((valores) =>
    enviar("/dp/beneficios/planos", {
      benefit_type_code: typeCode,
      code: valores.code.trim(),
      provider: valores.provider.trim(),
      name: valores.name.trim(),
      effective_from: valores.effective_from,
      amount: valores.amount,
      reason: valores.reason?.trim() || null,
    }),
  );

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="flex flex-col gap-4 px-5 py-5"
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <TextField
          id="plano-codigo"
          label="Código"
          error={plano.formState.errors.code?.message}
          {...plano.register("code")}
        />
        <TextField
          id="plano-nome"
          label="Nome"
          placeholder="Enfermaria, Apartamento…"
          error={plano.formState.errors.name?.message}
          {...plano.register("name")}
        />
        <TextField
          id="plano-operadora"
          label="Operadora"
          error={plano.formState.errors.provider?.message}
          {...plano.register("provider")}
        />
        <TextField
          id="plano-desde"
          label="Desde"
          type="date"
          error={plano.formState.errors.effective_from?.message}
          {...plano.register("effective_from")}
        />
        <TextField
          id="plano-valor"
          label="Valor"
          type="number"
          step="0.01"
          min="0"
          error={plano.formState.errors.amount?.message}
          {...plano.register("amount")}
        />
        <TextField
          id="plano-motivo"
          label="Motivo"
          placeholder="Cadastro inicial"
          error={plano.formState.errors.reason?.message}
          {...plano.register("reason")}
        />
      </div>

      {error ? <Alert>{error}</Alert> : null}

      <div className="flex items-center gap-2">
        <Button type="submit" disabled={plano.formState.isSubmitting}>
          {plano.formState.isSubmitting ? "Cadastrando…" : "Cadastrar plano"}
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

function planBands(catalog: Catalog, typeCode: string): Band[] {
  return catalog.plans
    .filter((plan) => plan.benefit_type_code === typeCode)
    .map((plan) => ({
      id: plan.id,
      target: "plan" as const,
      code: plan.code,
      kind: null,
      name: plan.name,
      detail: plan.provider,
      amount: plan.amount,
      effective_from: plan.effective_from,
      effective_to: plan.effective_to,
      reason: plan.reason,
    }));
}

function fareBands(catalog: Catalog): Band[] {
  return catalog.fares.map((fare) => ({
    id: fare.id,
    target: "fare" as const,
    code: fare.code,
    kind: fare.kind,
    name: fare.name,
    detail: null,
    amount: fare.amount,
    effective_from: fare.effective_from,
    effective_to: fare.effective_to,
    reason: fare.reason,
  }));
}

function mensagem(caught: unknown, padrao: string): string {
  return caught instanceof ApiError && caught.detail ? caught.detail : padrao;
}
