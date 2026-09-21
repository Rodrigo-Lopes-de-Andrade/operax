import { BotOff, History } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Table, type Column, type Row } from "@/components/ui/table";
import type {
  AssistantCostByVersion,
  AssistantRun,
  AssistantTestCost,
} from "@/lib/assistente/config";
import type { ExecutionsResult } from "@/lib/assistente/queries";
import { assistenteConfigHref, WEEKS_OPTIONS } from "@/lib/assistente/url";
import { TENANT_TIME_ZONE } from "@/lib/ponto/filters";
import { formatNumber } from "@/lib/ponto/format";

/**
 * A aba Execuções: o que o assistente respondeu, com que texto, e o que isso
 * custou. É o que fecha a etapa — as colunas de token existiam desde a 09 e
 * não respondiam "quanto custou a v2", porque não havia versão ao lado
 * (SPEC-AGENTE §0.3).
 *
 * ⛔ `version_label` É RENDERIZADO COMO VEIO, SEMPRE
 * O rótulo é montado pelo banco e inclui `"antes do versionamento"` (turno
 * anterior ao versionamento) e `"versão fora do alcance"` (turno que aponta
 * para uma versão que quem lê não alcança). Remontá-lo a partir de
 * `prompt_version_id` — "se tem id, é vN" — atribuiria procedência que não se
 * tem, que é o erro que esta etapa inteira existe para não cometer. O mesmo
 * vale para `refusal_reason`: é o motivo em pt-BR que o agente gravou, não um
 * código para traduzir aqui.
 *
 * ⛔ RECUSA NÃO É ERRO (SPEC-TECNICA §7)
 * Ela chega dentro de um 200, a linha inteira fica visível, e o motivo aparece
 * junto. Vermelho é falha; recusa é resposta.
 *
 * ⛔ AS TRÊS FRASES DA TABELA DE CUSTO SÃO OBRIGATÓRIAS
 * Cada uma foi arrancada de uma medição deste ciclo, e sem elas a tabela
 * afirma o que o dado não sustenta: a competência é UTC (não o relógio de São
 * Paulo), o modelo é parte da chave porque é ele que vira preço, e a linha de
 * uma versão soma os turnos de ANTES e DEPOIS de um rollback.
 *
 * ⛔ O TOTAL DE TESTE FICA FORA DA TABELA
 * Dry run é dinheiro real e não é tráfego: somá-lo às médias moveria o único
 * número que esta etapa produz. Por isso ele é uma linha à parte, sob a
 * tabela, e nunca uma linha dela (decisão do dono, 20/09/2026).
 *
 * Lista curta não é erro nem falta de permissão: `ai_query_read` é
 * própria-ou-admin, então quem não administra vê os próprios turnos.
 */

const UTC_NOTE =
  "Competências em UTC: um turno às 21h de 30/09 em São Paulo entra na competência de outubro.";
const MODEL_NOTE =
  "O mesmo texto pode ter rodado em modelos diferentes: o preço segue o modelo, e por isso cada linha traz o seu.";
const ROLLBACK_NOTE =
  "A coluna Versão soma os turnos de antes e depois de um rollback: voltar para uma versão e publicar de novo não separa as duas eras dela.";
/**
 * A quarta, e ela não estava no despacho: a janela é contada em SEMANAS e as
 * competências são meses, então as duas pontas entram cortadas. Sem esta
 * linha, "agosto custou X" é um mês parcial lido como mês inteiro — o mesmo
 * erro de leitura que as outras três existem para impedir.
 */
const WINDOW_NOTE =
  "A janela é contada em semanas: a competência mais antiga começa no meio do mês e a atual ainda está acontecendo. Nenhuma das duas pontas é um mês fechado.";
const SCOPE_NOTE =
  "Cada pessoa vê os próprios turnos; quem administra vê os do cliente. Lista curta não é erro.";
const OUT_OF_RANGE =
  "A janela precisa estar entre 1 e 52 semanas. Escolha uma das opções acima.";

const RUN_COLUMNS: Column[] = [
  { key: "when", label: "Quando", noWrap: true },
  { key: "question", label: "Pergunta" },
  { key: "metric", label: "Métrica", noWrap: true },
  { key: "rows", label: "Linhas", align: "right", numeric: true },
  { key: "latency", label: "Latência", align: "right", numeric: true },
  { key: "input", label: "Tokens entrada", align: "right", numeric: true },
  { key: "output", label: "Tokens saída", align: "right", numeric: true },
  { key: "model", label: "Modelo", noWrap: true },
  { key: "version", label: "Versão", noWrap: true },
];

const COST_COLUMNS: Column[] = [
  { key: "month", label: "Competência", noWrap: true },
  { key: "version", label: "Versão", noWrap: true },
  { key: "model", label: "Modelo", noWrap: true },
  { key: "runs", label: "Turnos", align: "right", numeric: true },
  { key: "refused", label: "Recusas", align: "right", numeric: true },
  { key: "input", label: "Tokens entrada", align: "right", numeric: true },
  { key: "output", label: "Tokens saída", align: "right", numeric: true },
  { key: "latency", label: "Latência média", align: "right", numeric: true },
];

const DATE_TIME = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: TENANT_TIME_ZONE,
});

const MONTH = new Intl.DateTimeFormat("pt-BR", {
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

/** `setembro de 2026` a partir do primeiro dia da competência, em UTC. */
function monthLabel(monthStart: string): string {
  const [year, month, day] = monthStart.split("-").map(Number);

  return MONTH.format(new Date(Date.UTC(year, month - 1, day)));
}

/** `275,5` de `Decimal` vira `276 ms`; nulo some e a célula vira travessão. */
function latency(value: number | string | null): string | undefined {
  if (value === null) {
    return undefined;
  }

  const number = Number(value);

  return Number.isNaN(number)
    ? String(value)
    : `${formatNumber(Math.round(number))} ms`;
}

function count(value: number | null): string | undefined {
  return value === null ? undefined : formatNumber(value);
}

export function Executions({
  weeks,
  result,
}: {
  weeks: number;
  result: ExecutionsResult;
}) {
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader
          eyebrow="Janela"
          title="Execuções"
          note="Os turnos reais do assistente na janela, e o que eles custaram. O teste fica fora de toda média."
          action={
            <SegmentedControl
              label="Janela em semanas"
              options={WEEKS_OPTIONS.map((option) => ({
                value: String(option),
                label: `${option} sem`,
              }))}
              value={String(weeks)}
              hrefFor={(value) =>
                assistenteConfigHref("execucoes", null, Number(value))
              }
            />
          }
        />
        {result.status === "out_of_range" ? (
          <p className="text-ink px-5 py-4 text-sm font-medium text-pretty">
            {OUT_OF_RANGE}
          </p>
        ) : null}
        {result.status === "unavailable" ? (
          <EmptyState
            icon={BotOff}
            tone="neutral"
            compact
            title="As execuções não puderam ser lidas"
            description="Vem da API do painel, e ela não respondeu agora. Nada foi alterado."
          />
        ) : null}
      </Card>

      {result.status === "ok" ? (
        <>
          <RunsCard runs={result.screen.runs} weeks={weeks} />
          <CostCard
            rows={result.screen.cost}
            testCost={result.screen.testCost}
          />
        </>
      ) : null}
    </div>
  );
}

function RunsCard({ runs, weeks }: { runs: AssistantRun[]; weeks: number }) {
  const rows: Row[] = runs.map((run, index) => ({
    id: `${run.created_at}-${index}`,
    cells: {
      when: (
        <span className="text-ink-muted text-xs tabular-nums">
          {DATE_TIME.format(new Date(run.created_at))}
        </span>
      ),
      question: (
        <div className="flex flex-col gap-1">
          <span className="text-ink text-sm">{run.question}</span>
          {run.refused ? (
            <span className="flex flex-wrap items-center gap-2">
              <Badge tone="alert">Recusa</Badge>
              {run.refusal_reason ? (
                <span className="text-ink-muted text-xs text-pretty">
                  {run.refusal_reason}
                </span>
              ) : null}
            </span>
          ) : null}
        </div>
      ),
      metric: run.metric_code ? (
        <span className="text-ink-muted font-mono text-xs">
          {run.metric_code}
        </span>
      ) : undefined,
      rows: count(run.rows_returned),
      latency: latency(run.latency_ms),
      input: count(run.input_tokens),
      output: count(run.output_tokens),
      model: run.model ? (
        <span className="text-ink-muted text-xs">{run.model}</span>
      ) : undefined,
      // ⛔ Como veio. Sem remontar, sem mapear, sem "melhorar".
      version: (
        <span className="text-ink text-xs font-bold">{run.version_label}</span>
      ),
    },
  }));

  return (
    <Card>
      <CardHeader
        eyebrow="Turnos"
        title="O que o assistente respondeu"
        note={SCOPE_NOTE}
      />
      <Table
        columns={RUN_COLUMNS}
        rows={rows}
        density="compact"
        caption="Turnos do assistente na janela"
        empty={
          <EmptyState
            icon={History}
            tone="neutral"
            compact
            title="A janela está vazia"
            description={`Nenhum turno do assistente nas últimas ${weeks} ${weeks === 1 ? "semana" : "semanas"}. ${SCOPE_NOTE}`}
          />
        }
      />
    </Card>
  );
}

function CostCard({
  rows,
  testCost,
}: {
  rows: AssistantCostByVersion[];
  testCost: AssistantTestCost[];
}) {
  const tableRows: Row[] = rows.map((row, index) => ({
    id: `${row.month_start}-${row.prompt_version_id ?? "sem-versao"}-${row.model ?? "sem-modelo"}-${index}`,
    cells: {
      month: (
        <span className="text-ink text-sm font-semibold">
          {monthLabel(row.month_start)}
        </span>
      ),
      // ⛔ Como veio, aqui também.
      version: (
        <span className="text-ink text-xs font-bold">{row.version_label}</span>
      ),
      model: row.model ? (
        <span className="text-ink-muted text-xs">{row.model}</span>
      ) : undefined,
      runs: formatNumber(row.runs),
      refused: formatNumber(row.refused_runs),
      input: formatNumber(row.input_tokens),
      output: formatNumber(row.output_tokens),
      latency: latency(row.avg_latency_ms),
    },
  }));

  return (
    <Card>
      <CardHeader
        eyebrow="Custo"
        title="Custo por competência e versão"
        note={UTC_NOTE}
      />
      <div className="flex flex-col gap-3">
        <div className="border-line-subtle flex flex-col gap-1 border-b px-5 py-3">
          <p className="text-ink text-sm font-medium text-pretty">
            {MODEL_NOTE}
          </p>
          <p className="text-ink text-sm font-medium text-pretty">
            {ROLLBACK_NOTE}
          </p>
          <p className="text-ink text-sm font-medium text-pretty">
            {WINDOW_NOTE}
          </p>
        </div>
        <Table
          columns={COST_COLUMNS}
          rows={tableRows}
          caption="Custo por competência, versão de prompt e modelo"
          empty={
            <EmptyState
              icon={History}
              tone="neutral"
              compact
              title="A janela está vazia"
              description="Nenhum turno real na janela, então não há custo a somar."
            />
          }
        />
        {/* ⛔ FORA DA TABELA, E É O PONTO: dry run é dinheiro real e não é
            tráfego. Dentro dela, alguém somaria as duas colunas sem perceber. */}
        <TestTotal rows={testCost} />
      </div>
    </Card>
  );
}

function TestTotal({ rows }: { rows: AssistantTestCost[] }) {
  const runs = rows.reduce((total, row) => total + row.runs, 0);
  const input = rows.reduce((total, row) => total + row.input_tokens, 0);
  const output = rows.reduce((total, row) => total + row.output_tokens, 0);

  return (
    <p className="text-ink-muted border-line-subtle border-t px-5 py-3 text-sm text-pretty">
      {runs === 0
        ? "Testes do período: nenhum turno de teste na janela."
        : `Testes do período: ${formatNumber(runs)} ${runs === 1 ? "turno" : "turnos"}, ${formatNumber(input)} tokens de entrada, ${formatNumber(output)} de saída.`}{" "}
      <span className="text-ink font-semibold">Fora de toda média.</span>
    </p>
  );
}
