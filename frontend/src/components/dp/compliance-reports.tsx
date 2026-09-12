"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { FileCheck2, Plus } from "lucide-react";
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
import { Table, type Column } from "@/components/ui/table";
import { TextField } from "@/components/ui/text-field";
import { ApiError, requestApiAsUser } from "@/lib/api";
import { formatDate } from "@/lib/dp/format";
import type {
  ComplianceReportList,
  ComplianceReportRow,
} from "@/lib/dp/queries";
import { REPORT_STATUS_LABEL, type ReportStatus } from "@/lib/dp/url";
import { DUE_SOON_DAYS, dueLabel, dueTone } from "@/lib/rh/labels";

const COLUMNS: Column[] = [
  { key: "unidade", label: "Unidade", width: "18%" },
  { key: "tipo", label: "Tipo", mono: true, width: "12%" },
  { key: "validade", label: "Validade", width: "12%", noWrap: true },
  { key: "situacao", label: "Situação", width: "16%" },
  { key: "renovacoes", label: "Renovações", align: "right", width: "10%" },
  { key: "observacao", label: "Observação" },
  { key: "acao", label: "", align: "right", width: "10%" },
];

/** Sugestões, não lista fechada: o tipo é texto livre e o banco canonicaliza. */
const TYPE_SUGGESTIONS = ["PCMSO", "PGR", "LTCAT+LTIP"];
const TYPE_LIST_ID = "laudo-tipos";

/**
 * A situação sai do mesmo limiar que a ficha de RH usa para documento e ASO:
 * `dueTone` diz vencido / a vencer / em dia, e a janela é `DUE_SOON_DAYS` —
 * declarada lá e lida aqui, inclusive pela frase que a explica ao gestor. Um
 * número escrito de novo, aqui ou na prosa, seria a segunda declaração.
 *
 * O tom do badge e o rótulo saem da MESMA chamada: `bad` é vencido, `alert` é
 * a vencer, e um "Vencido" em cinza seria a tela contando duas histórias.
 */
function statusOf(tone: ReturnType<typeof dueTone>): ReportStatus {
  if (tone === "bad") {
    return "vencido";
  }

  return tone === "alert" ? "a_vencer" : "em_dia";
}

function reportStatus(days: number): ReportStatus {
  return statusOf(dueTone(days));
}

/**
 * Laudos por unidade — PCMSO, PGR, LTCAT+LTIP.
 *
 * ⛔ NÃO EXISTE CAMPO DE DATA NA LINHA VIGENTE, E A AUSÊNCIA É O DESENHO
 * Renovar é **linha nova** apontando para a que sai (`POST /laudos/{id}/renovar`),
 * e o vencimento anterior é o que valeu na fiscalização da unidade. Reescrevê-lo
 * mudaria o passado sem deixar rastro — regra 6 do projeto estendida ao laudo.
 * Não existe apagar pelo mesmo motivo.
 *
 * A situação NÃO é coluna: `public.vw_unit_compliance` entrega `days_to_expiry`
 * e nada mais, e o filtro `situacao` da URL é aplicado aqui, sobre as linhas que
 * a view devolveu. A janela de "a vencer" não existe no schema para laudo — ela
 * é declaração da UI, e é por isso que nem a view nem a rota filtram por ela.
 */
export function ComplianceReports({
  screen,
  units,
  status,
  unitId,
}: {
  screen: ComplianceReportList;
  units: UnitChoice[];
  status: ReportStatus | null;
  /**
   * A unidade escolhida no filtro, quando há uma. O recorte já foi aplicado na
   * consulta à view, então a lista vazia com unidade escolhida significa "esta
   * unidade não tem laudo" — e não "nenhuma das suas unidades tem", que é o
   * que a tela dizia e era falso.
   */
  unitId: string | null;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [renewingId, setRenewingId] = useState<string | null>(null);

  // `screen.can_write` só; nunca `?? true`. O que chega é JSON, e uma resposta
  // sem a chave vale "não pode".
  const canWrite = screen.can_write === true;
  // O nome sai da lista que o seletor já usa; um id sem nome vira `null`, e a
  // frase volta a ser a genérica em vez de mostrar um uuid ao gestor.
  const unidadeEscolhida = unitId
    ? (units.find((unit) => unit.id === unitId)?.name ?? null)
    : null;
  const visible = status
    ? screen.rows.filter((row) => reportStatus(row.days_to_expiry) === status)
    : screen.rows;
  // Derivado da lista, e não guardado: depois de um `refresh` o laudo renovado
  // tem outro id, e o formulário que apontava para o antigo fecha sozinho.
  const renewing = canWrite
    ? (screen.rows.find((row) => row.id === renewingId) ?? null)
    : null;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-ink-muted max-w-3xl text-sm text-pretty">
        A situação é lida da validade:{" "}
        <strong className="text-ink">vencido</strong> já passou,{" "}
        <strong className="text-ink">a vencer</strong> vence em até{" "}
        {DUE_SOON_DAYS} dias. Renovar cria um registro novo e guarda o anterior
        — a data do laudo vigente não se edita.
      </p>

      {error ? <Alert>{error}</Alert> : null}

      {canWrite ? (
        <Card>
          <CardHeader
            title="Novo laudo"
            note="O primeiro laudo de cada tipo na unidade. Se já existe um vigente, o caminho é renovar — e a recusa vem do banco, não daqui."
            action={
              <Button onClick={() => setCreating((open) => !open)}>
                <Plus size={15} aria-hidden />
                {creating ? "Fechar" : "Novo laudo"}
              </Button>
            }
          />
          {creating ? (
            <NewReportForm
              units={units}
              onDone={() => {
                setCreating(false);
                router.refresh();
              }}
            />
          ) : null}
        </Card>
      ) : null}

      {renewing ? (
        <Card>
          <CardHeader
            eyebrow="Renovar"
            title={`${renewing.type} · ${renewing.unit_name}`}
            note={`Vigente até ${formatDate(renewing.valid_until)}. O registro atual é mantido como histórico.`}
          />
          <RenewReportForm
            key={renewing.id}
            report={renewing}
            onDone={() => {
              setRenewingId(null);
              router.refresh();
            }}
            onConflict={(detail) => {
              // Alguém renovou antes: a mensagem é da API, e a lista tem de
              // ser relida para mostrar o laudo que agora vale.
              setError(detail);
              setRenewingId(null);
              router.refresh();
            }}
            onCancel={() => setRenewingId(null)}
          />
        </Card>
      ) : null}

      {screen.rows.length === 0 ? (
        <Card className="p-6">
          <EmptyState
            icon={FileCheck2}
            tone="neutral"
            title="Nenhum laudo vigente"
            description={`${
              unidadeEscolhida
                ? `A unidade ${unidadeEscolhida} não tem laudo cadastrado.`
                : "As unidades que você acompanha não têm laudo cadastrado."
            }${canWrite ? " Cadastre o primeiro acima." : ""}`}
          />
        </Card>
      ) : visible.length === 0 ? (
        <Card className="p-6">
          <EmptyState
            icon={FileCheck2}
            tone="neutral"
            // Este ramo só existe com situação escolhida: sem ela `visible` é
            // a lista inteira, e a condição acima não se sustenta.
            title={`Nenhum laudo ${REPORT_STATUS_LABEL[status!].toLowerCase()}`}
            description={`Há ${screen.rows.length} ${screen.rows.length === 1 ? "laudo vigente" : "laudos vigentes"} fora desta situação. Escolha "Todas as situações" para vê-los.`}
          />
        </Card>
      ) : (
        <Card>
          <CardHeader
            title="Laudos vigentes"
            note={`${visible.length} de ${screen.rows.length} ${screen.rows.length === 1 ? "laudo" : "laudos"}`}
          />
          <Table
            columns={COLUMNS}
            caption="Laudos vigentes por unidade"
            rows={visible.map((row) => {
              const tone = dueTone(row.days_to_expiry);

              return {
                id: row.id,
                cells: {
                  unidade: row.unit_name,
                  tipo: row.type,
                  validade: formatDate(row.valid_until),
                  situacao: (
                    <span className="flex flex-col gap-1">
                      <Badge tone={tone} dot>
                        {REPORT_STATUS_LABEL[statusOf(tone)]}
                      </Badge>
                      <span className="text-ink-muted text-xs">
                        {dueLabel(row.days_to_expiry)}
                      </span>
                    </span>
                  ),
                  renovacoes: row.renewal_count,
                  observacao: row.notes ?? (
                    <span className="text-ink-faint">—</span>
                  ),
                  acao: canWrite ? (
                    <button
                      type="button"
                      onClick={() => {
                        setError(null);
                        setRenewingId(row.id);
                      }}
                      className="text-brand-strong text-xs font-bold underline"
                    >
                      Renovar
                    </button>
                  ) : null,
                },
              };
            })}
          />
        </Card>
      )}
    </div>
  );
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

const renewSchema = z.object({
  valid_until: z.string().regex(ISO_DAY, "Informe a nova validade."),
  notes: z.string().max(500, "A observação cabe em 500 caracteres.").optional(),
});

/**
 * Só a validade nova e a observação. Unidade e tipo não estão aqui porque uma
 * renovação que os troca é outro laudo — e `ComplianceReportRenewal` recusa os
 * campos antes de o pedido sair da tela.
 */
function RenewReportForm({
  report,
  onDone,
  onConflict,
  onCancel,
}: {
  report: ComplianceReportRow;
  onDone: () => void;
  onConflict: (detail: string) => void;
  onCancel: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm({
    resolver: zodResolver(renewSchema),
    defaultValues: { valid_until: "", notes: "" },
  });

  const onSubmit = handleSubmit(async (valores) => {
    setError(null);

    try {
      await requestApiAsUser(`/dp/laudos/${report.id}/renovar`, {
        method: "POST",
        body: {
          valid_until: valores.valid_until,
          notes: valores.notes?.trim() || null,
        },
      });
      onDone();
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        onConflict(
          caught.detail ?? "Este laudo já foi renovado por outra pessoa.",
        );
        return;
      }

      setError(
        mensagem(caught, "Não consegui renovar o laudo. Nada foi alterado."),
      );
    }
  });

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="flex flex-col gap-4 px-5 py-5"
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <TextField
          id="renovar-validade"
          label="Nova validade"
          type="date"
          error={formState.errors.valid_until?.message}
          {...register("valid_until")}
        />
        <TextField
          id="renovar-observacao"
          label="Observação (opcional)"
          placeholder="Renovado após visita técnica"
          error={formState.errors.notes?.message}
          {...register("notes")}
        />
      </div>

      {error ? <Alert>{error}</Alert> : null}

      <div className="flex items-center gap-2">
        <Button type="submit" disabled={formState.isSubmitting}>
          {formState.isSubmitting ? "Renovando…" : "Renovar laudo"}
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

const createSchema = z.object({
  unit_id: z.string().min(1, "Escolha a unidade do laudo."),
  type: z
    .string()
    .trim()
    .min(1, "Informe o tipo do laudo.")
    .max(60, "O tipo cabe em 60 caracteres."),
  valid_until: z.string().regex(ISO_DAY, "Informe a validade do laudo."),
  notes: z.string().max(500, "A observação cabe em 500 caracteres.").optional(),
});

const UNIT_ERROR_ID = "laudo-unidade-error";

/** O primeiro laudo daquele tipo na unidade. O segundo é renovação, e a API diz isso. */
function NewReportForm({
  units,
  onDone,
}: {
  units: UnitChoice[];
  onDone: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, reset, formState } = useForm({
    resolver: zodResolver(createSchema),
    defaultValues: {
      unit_id: units[0]?.id ?? "",
      type: "",
      valid_until: "",
      notes: "",
    },
  });

  const onSubmit = handleSubmit(async (valores) => {
    setError(null);

    try {
      await requestApiAsUser("/dp/laudos", {
        method: "POST",
        body: {
          unit_id: valores.unit_id,
          type: valores.type.trim(),
          valid_until: valores.valid_until,
          notes: valores.notes?.trim() || null,
        },
      });
      reset({ unit_id: valores.unit_id, type: "", valid_until: "", notes: "" });
      onDone();
    } catch (caught) {
      setError(
        mensagem(caught, "Não consegui cadastrar o laudo. Nada foi alterado."),
      );
    }
  });

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="flex flex-col gap-4 px-5 py-5"
    >
      <div className="grid gap-4 sm:grid-cols-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
            Unidade
          </span>
          <select
            aria-label="Unidade do laudo"
            aria-invalid={formState.errors.unit_id ? true : undefined}
            aria-describedby={
              formState.errors.unit_id ? UNIT_ERROR_ID : undefined
            }
            className="border-control-line bg-control text-ink h-10 rounded-[10px] border px-3 text-sm"
            {...register("unit_id")}
          >
            {units.map((unit) => (
              <option key={unit.id} value={unit.id}>
                {unit.name}
              </option>
            ))}
          </select>
          {/*
            Sem unidade nenhuma no seletor o `submit` era silencioso: a validação
            recusava e ninguém via por quê. A mensagem é a mesma do schema.
          */}
          {formState.errors.unit_id ? (
            <p id={UNIT_ERROR_ID} className="text-bad text-xs font-medium">
              {formState.errors.unit_id.message}
            </p>
          ) : null}
        </label>
        <TextField
          id="laudo-tipo"
          label="Tipo"
          placeholder="PCMSO"
          list={TYPE_LIST_ID}
          error={formState.errors.type?.message}
          {...register("type")}
        />
        <datalist id={TYPE_LIST_ID}>
          {TYPE_SUGGESTIONS.map((tipo) => (
            <option key={tipo} value={tipo} />
          ))}
        </datalist>
        <TextField
          id="laudo-validade"
          label="Validade"
          type="date"
          error={formState.errors.valid_until?.message}
          {...register("valid_until")}
        />
        <TextField
          id="laudo-observacao"
          label="Observação (opcional)"
          placeholder="Emitido pela clínica X"
          error={formState.errors.notes?.message}
          {...register("notes")}
        />
      </div>

      {error ? <Alert>{error}</Alert> : null}

      <Button type="submit" disabled={formState.isSubmitting}>
        {formState.isSubmitting ? "Cadastrando…" : "Cadastrar laudo"}
      </Button>
    </form>
  );
}

function mensagem(caught: unknown, padrao: string): string {
  return caught instanceof ApiError && caught.detail ? caught.detail : padrao;
}
