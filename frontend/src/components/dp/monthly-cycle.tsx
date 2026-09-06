"use client";

import {
  CalendarRange,
  Download,
  FileSpreadsheet,
  Landmark,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Table, type Column } from "@/components/ui/table";
import { ApiError, downloadApiAsUser, requestApiAsUser } from "@/lib/api";
import { formatCompetencia, formatCurrency, formatDate } from "@/lib/dp/format";
import type { CycleEntitlementRow, CycleView } from "@/lib/dp/queries";
import {
  CYCLE_KINDS,
  CYCLE_KIND_LABEL,
  cycleHref,
  type CycleFilters,
  type CycleKind,
} from "@/lib/dp/url";
import { MESES } from "@/lib/folha/url";
import { formatNumber } from "@/lib/ponto/format";

/** O único `kind` que vira dinheiro em conta. A cesta é pedido ao fornecedor. */
const TRANSPORT_VOUCHER: CycleKind = "transport_voucher";

/** Os estados em que a apuração está congelada — e só deles sai remessa. */
const PAYABLE = ["generated", "exported"];

const STATUS_LABEL: Record<string, string> = {
  draft: "Rascunho",
  generated: "Gerado",
  exported: "Exportado",
  cancelled: "Cancelado",
};

/**
 * Uma recusa do backend é resposta válida, não defeito.
 *
 * O apurador recusa quando falta dado para pagar certo — jornada não
 * materializada, justificativa de afastamento não classificada, tarifa sem
 * vigência — e a mensagem dele nomeia o que falta. Ela chega inteira à tela: um
 * "erro inesperado" aqui esconderia a única informação acionável que existe, e
 * quem opera não tem outro lugar para descobrir qual string não foi curada.
 */
type Failure = { kind: "refusal" | "error"; message: string };

const CESTA_COLUMNS: Column[] = [
  { key: "pessoa", label: "Colaborador" },
  { key: "direito", label: "Direito", width: "12%" },
  { key: "motivo", label: "Motivo" },
];

const VT_COLUMNS: Column[] = [
  { key: "pessoa", label: "Colaborador" },
  { key: "direito", label: "Direito", width: "10%" },
  { key: "dias", label: "Dias base", align: "right", numeric: true },
  { key: "faltas", label: "Faltas", align: "right", numeric: true },
  { key: "liquidos", label: "Dias líquidos", align: "right", numeric: true },
  { key: "ida_volta", label: "Ida e volta", align: "right", numeric: true },
  { key: "total", label: "Total", align: "right", numeric: true },
  { key: "motivo", label: "Motivo" },
];

/**
 * Ciclo mensal de cesta e vale transporte.
 *
 * ⚠️ APURAR NÃO É GERAR, E A TELA NÃO PODE DEIXAR ISSO IMPLÍCITO
 * A apuração devolve um **preview**: o rascunho é reapurado a cada conferência,
 * e é exatamente por isso que ele serve para conferir. Gerar congela — e é o
 * congelamento que faz o número que o gestor conferiu ser o número que o banco
 * paga. Foi medido nesta etapa: o mesmo rascunho produziu dois arquivos de banco
 * com valores diferentes, e por isso a remessa passou a exigir ciclo congelado.
 *
 * ⛔ O BOTÃO DA REMESSA NÃO EXISTE PARA QUEM NÃO TEM O DOMÍNIO BANCÁRIO
 * Não desabilitado, não com cadeado: ausente do DOM. Quem responde se ele
 * aparece é a API — `can_export_remittance` na resposta do ciclo —, e a ausência
 * da resposta vale como "não pode". Deduzir o domínio de uma lista de papéis
 * aqui seria a matriz de sensibilidade escrita uma segunda vez, longe do banco
 * que a altera por `update`.
 */
export function MonthlyCycle({ filters }: { filters: CycleFilters }) {
  const router = useRouter();
  const [result, setResult] = useState<{
    key: string;
    cycle: CycleView;
  } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  // O preview pertence à competência em que foi apurado. Trocar de mês na URL
  // não pode deixar os números de agosto embaixo do título de setembro.
  const chave = `${filters.kind}-${filters.year}-${filters.month}`;
  const cycle = result?.key === chave ? result.cycle : null;

  function navegar(overrides: Partial<CycleFilters>) {
    setFailure(null);
    router.push(cycleHref(filters, overrides));
  }

  async function apurar() {
    setBusy("apurar");
    setFailure(null);

    try {
      const apurado = await requestApiAsUser<CycleView>("/dp/ciclos", {
        method: "POST",
        body: {
          kind: filters.kind,
          period_year: filters.year,
          period_month: filters.month,
        },
      });
      setResult({ key: chave, cycle: apurado });
    } catch (caught) {
      setResult(null);
      setFailure(recusa(caught, [422], "Não consegui apurar a competência."));
    } finally {
      setBusy(null);
    }
  }

  async function gerar() {
    if (!cycle?.id) return;
    setBusy("gerar");
    setFailure(null);

    try {
      const congelado = await requestApiAsUser<CycleView>(
        `/dp/ciclos/${cycle.id}/gerar`,
        { method: "POST" },
      );
      setResult({ key: chave, cycle: congelado });
      router.refresh();
    } catch (caught) {
      setFailure(recusa(caught, [409, 422], "Não consegui gerar o ciclo."));
    } finally {
      setBusy(null);
    }
  }

  async function exportar(formato: "xlsx" | "pdf" | "banco") {
    if (!cycle?.id) return;
    setBusy(formato);
    setFailure(null);

    try {
      const { blob, filename } = await downloadApiAsUser(
        `/dp/ciclos/${cycle.id}/export?formato=${formato}`,
        `${filters.kind}-${filters.year}-${String(filters.month).padStart(2, "0")}`,
      );
      salvar(blob, filename);
    } catch (caught) {
      setFailure(recusa(caught, [409, 422], "Não consegui gerar o arquivo."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader
          title="Competência"
          note="A janela é derivada do mês pela regra da rotina — o vale transporte conta de 21 a 20, e ela não é um campo do formulário."
          action={
            <Button onClick={apurar} disabled={busy === "apurar"}>
              {busy === "apurar" ? "Apurando…" : "Apurar competência"}
            </Button>
          }
        />
        <div className="flex flex-wrap items-end gap-4 px-5 py-5">
          <div className="flex flex-col gap-1.5">
            <span className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
              Rotina
            </span>
            <SegmentedControl
              label="Rotina do ciclo"
              options={CYCLE_KINDS.map((kind) => ({
                value: kind,
                label: CYCLE_KIND_LABEL[kind],
              }))}
              value={filters.kind}
              hrefFor={(kind) => cycleHref(filters, { kind })}
            />
          </div>

          <label className="flex flex-col gap-1.5">
            <span className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
              Mês
            </span>
            <select
              value={filters.month}
              aria-label="Mês da competência"
              onChange={(event) =>
                navegar({ month: Number(event.target.value) })
              }
              className="border-control-line bg-control text-ink h-10 rounded-[10px] border px-3 text-sm"
            >
              {MESES.map((nome, indice) => (
                <option key={nome} value={indice + 1}>
                  {nome}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
              Ano
            </span>
            <select
              value={filters.year}
              aria-label="Ano da competência"
              onChange={(event) =>
                navegar({ year: Number(event.target.value) })
              }
              className="border-control-line bg-control text-ink h-10 rounded-[10px] border px-3 text-sm"
            >
              {anos(filters.year).map((valor) => (
                <option key={valor} value={valor}>
                  {valor}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Card>

      {failure ? <FailureBanner failure={failure} /> : null}

      {cycle ? (
        <>
          <Summary cycle={cycle} />
          <Exports
            cycle={cycle}
            busy={busy}
            onGerar={gerar}
            onExportar={exportar}
          />
          <People cycle={cycle} />
        </>
      ) : (
        <Card className="p-6">
          <EmptyState
            icon={CalendarRange}
            tone="neutral"
            title={`Nada apurado em ${formatCompetencia(filters.year, filters.month)}`}
            description="Apurar não grava nada definitivo: o resultado é um preview, feito para ser conferido e reapurado. O que congela a competência é gerar o ciclo, depois."
          />
        </Card>
      )}
    </div>
  );
}

/**
 * A recusa e o erro são estados diferentes, e a tela os separa.
 *
 * A recusa é o produto funcionando: falta dado, a mensagem diz qual, e quem
 * opera resolve. O erro é o produto falhando. Vermelho é reservado para o
 * segundo — usá-lo no primeiro treinaria o gestor a ignorar vermelho.
 */
function FailureBanner({ failure }: { failure: Failure }) {
  if (failure.kind === "error") {
    return <Alert>{failure.message}</Alert>;
  }

  return (
    <div
      role="status"
      className="bg-alert-bg text-alert flex flex-col gap-1 rounded-[10px] px-4 py-3"
    >
      <p className="text-2xs font-bold tracking-[0.08em] uppercase">
        Apuração recusada — falta dado, não é falha do sistema
      </p>
      <p className="text-sm text-pretty">{failure.message}</p>
    </div>
  );
}

function Summary({ cycle }: { cycle: CycleView }) {
  return (
    <Card>
      <CardHeader
        eyebrow={CYCLE_KIND_LABEL[cycle.kind]}
        title={formatCompetencia(cycle.period_year, cycle.period_month)}
        note={`Janela de ${formatDate(cycle.window_start)} a ${formatDate(cycle.window_end)}${
          cycle.business_days === null
            ? ""
            : ` · ${formatNumber(cycle.business_days)} dia(s) com expediente`
        }`}
        action={
          <Badge tone={PAYABLE.includes(cycle.status) ? "good" : "neutral"} dot>
            {STATUS_LABEL[cycle.status] ?? cycle.status}
          </Badge>
        }
      />
      <div className="flex flex-wrap gap-8 px-5 py-4">
        <Figure
          label="Com direito"
          value={formatNumber(cycle.entitled_count)}
        />
        <Figure label="Sem direito" value={formatNumber(cycle.denied_count)} />
        <Figure label="Total" value={formatCurrency(cycle.total_amount)} />
      </div>
    </Card>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex flex-col gap-1">
      <span className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
        {label}
      </span>
      <span className="text-ink text-xl font-extrabold tabular-nums">
        {value}
      </span>
    </span>
  );
}

function Exports({
  cycle,
  busy,
  onGerar,
  onExportar,
}: {
  cycle: CycleView;
  busy: string | null;
  onGerar: () => void;
  onExportar: (formato: "xlsx" | "pdf" | "banco") => void;
}) {
  const congelado = PAYABLE.includes(cycle.status);

  return (
    <Card>
      <CardHeader
        title="Arquivos da competência"
        note="Excel e PDF saem do rascunho: eles são o preview, e conferir é para o que o rascunho existe."
        action={
          congelado ? null : (
            <Button onClick={onGerar} disabled={busy === "gerar"}>
              {busy === "gerar" ? "Gerando…" : "Gerar ciclo"}
            </Button>
          )
        }
      />
      <div className="flex flex-wrap items-center gap-3 px-5 py-5">
        <Button onClick={() => onExportar("xlsx")} disabled={busy === "xlsx"}>
          <FileSpreadsheet size={15} aria-hidden />
          {busy === "xlsx" ? "Gerando…" : "Excel"}
        </Button>
        <Button onClick={() => onExportar("pdf")} disabled={busy === "pdf"}>
          <Download size={15} aria-hidden />
          {busy === "pdf" ? "Gerando…" : "PDF"}
        </Button>

        {/*
          ⛔ O terceiro botão é o único com eixo de domínio, e ele não é
          desabilitado: ou existe, ou não está aqui. Quem não alcança dado
          bancário não fica sabendo que existe um arquivo de banco.
        */}
        {cycle.can_export_remittance ? (
          <Remittance
            cycle={cycle}
            busy={busy}
            onExportar={() => onExportar("banco")}
          />
        ) : null}
      </div>

      {congelado ? (
        <p className="text-ink-muted px-5 pb-5 text-sm text-pretty">
          A competência está congelada. Corrigir daqui em diante é apurar um
          ciclo novo — o número que saiu para conferência é o que fica.
        </p>
      ) : null}
    </Card>
  );
}

/**
 * O arquivo de banco, e por que ele exige o ciclo congelado.
 *
 * O rascunho é reapurado a cada conferência: duas remessas do mesmo mês sairiam
 * com valores diferentes, e a segunda pagaria outra coisa. Por isso a frase fica
 * escrita ao lado — o gestor não pode descobrir a regra clicando e levando uma
 * recusa.
 */
function Remittance({
  cycle,
  busy,
  onExportar,
}: {
  cycle: CycleView;
  busy: string | null;
  onExportar: () => void;
}) {
  if (cycle.kind !== TRANSPORT_VOUCHER) {
    return (
      <p className="text-ink-muted max-w-md text-xs text-pretty">
        A cesta não tem arquivo de banco: ela é pedido ao fornecedor, não
        pagamento em conta.
      </p>
    );
  }

  if (!PAYABLE.includes(cycle.status)) {
    return (
      <p className="text-ink-muted max-w-md text-xs text-pretty">
        <strong className="text-ink">
          O arquivo do banco exige o ciclo gerado.
        </strong>{" "}
        Um rascunho é reapurado a cada conferência, e duas remessas do mesmo mês
        pagariam valores diferentes — o número conferido tem de ser o número
        pago. Gere o ciclo para baixar a remessa.
      </p>
    );
  }

  return (
    <Button onClick={onExportar} disabled={busy === "banco"}>
      <Landmark size={15} aria-hidden />
      {busy === "banco" ? "Gerando…" : "Arquivo do banco"}
    </Button>
  );
}

/**
 * A tabela por pessoa, agrupada por unidade.
 *
 * `entitled` e `reason` são as duas colunas que não podem faltar: quem perdeu o
 * direito vai perguntar por quê, e a resposta é do apurador — a tela não a
 * reescreve.
 */
function People({ cycle }: { cycle: CycleView }) {
  const grupos = groupByUnit(cycle.rows);
  const vt = cycle.kind === TRANSPORT_VOUCHER;

  if (cycle.rows.length === 0) {
    return (
      <Card className="p-6">
        <EmptyState
          icon={CalendarRange}
          tone="neutral"
          compact
          title="Nenhum vínculo na janela"
          description="A competência foi apurada e não encontrou colaborador ativo dentro do período."
        />
      </Card>
    );
  }

  return (
    <>
      {grupos.map(([unidade, linhas]) => (
        <Card key={unidade}>
          <CardHeader
            eyebrow="Unidade"
            title={unidade}
            note={`${formatNumber(linhas.filter((linha) => linha.entitled).length)} com direito · ${formatNumber(
              linhas.filter((linha) => !linha.entitled).length,
            )} sem direito`}
          />
          <Table
            columns={vt ? VT_COLUMNS : CESTA_COLUMNS}
            density="compact"
            caption={`Apuração por pessoa — ${unidade}`}
            rows={linhas.map((linha) => ({
              id: linha.employee_id,
              cells: {
                pessoa: (
                  <span className="flex flex-col">
                    <span className="text-ink font-semibold">{linha.name}</span>
                    {linha.registration_number ? (
                      <span className="text-ink-faint font-mono text-xs">
                        {linha.registration_number}
                      </span>
                    ) : null}
                  </span>
                ),
                direito: (
                  <Badge tone={linha.entitled ? "good" : "neutral"} dot>
                    {linha.entitled ? "Sim" : "Não"}
                  </Badge>
                ),
                dias: numero(linha.days_base),
                faltas: numero(linha.absences_prior),
                liquidos: numero(linha.net_days),
                ida_volta: linha.round_trip_amount
                  ? formatCurrency(linha.round_trip_amount)
                  : null,
                total: linha.total_amount
                  ? formatCurrency(linha.total_amount)
                  : null,
                motivo: linha.reason ? (
                  <span className="text-ink-muted text-xs text-pretty">
                    {linha.reason}
                  </span>
                ) : null,
              },
            }))}
          />
        </Card>
      ))}
    </>
  );
}

function numero(value: number | null): string | null {
  return value === null ? null : formatNumber(value);
}

function groupByUnit(
  rows: CycleEntitlementRow[],
): [string, CycleEntitlementRow[]][] {
  const grupos = new Map<string, CycleEntitlementRow[]>();

  for (const row of rows) {
    // Sem unidade não é zero: é gente que o mapeamento ainda não alcançou, e
    // ela precisa aparecer em algum grupo para não sumir da conferência.
    const chave = row.unit_name ?? "Sem unidade";
    const atual = grupos.get(chave);

    if (atual) {
      atual.push(row);
    } else {
      grupos.set(chave, [row]);
    }
  }

  return [...grupos.entries()];
}

/** As competências que valem no seletor: o ano em foco e os dois anteriores. */
function anos(atual: number): number[] {
  return [atual + 1, atual, atual - 1, atual - 2];
}

/**
 * Traduz a falha da API. Os status listados são os que o backend usa para dizer
 * "falta dado" ou "o estado não permite" — os dois são recusa, e a mensagem
 * deles é a resposta, não um detalhe técnico a esconder.
 */
function recusa(caught: unknown, refusals: number[], padrao: string): Failure {
  if (caught instanceof ApiError && caught.detail) {
    return {
      kind: refusals.includes(caught.status) ? "refusal" : "error",
      message: caught.detail,
    };
  }

  return { kind: "error", message: padrao };
}

/**
 * O arquivo chega como blob autenticado, então o download é um clique
 * sintético. A URL precisa sobreviver ao clique: revogar na linha seguinte
 * cancela o download que acabou de começar.
 */
function salvar(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
