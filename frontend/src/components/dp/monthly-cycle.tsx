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
import type {
  CycleEntitlementRow,
  CycleListResult,
  CycleSummary,
  CycleView,
} from "@/lib/dp/queries";
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
type Failure =
  | { kind: "error"; message: string }
  | { kind: "refusal"; title: string; message: string };

/**
 * As tarjas de recusa. A frase é escolhida pelo chamador, e não pelo status: o
 * mesmo 409 quer dizer coisas opostas em rotas diferentes — apurar e gerar
 * recusam competência JÁ congelada; a remessa recusa ciclo AINDA em rascunho.
 * Um mapa global por status diria uma das duas frases no lugar errado, e diria
 * em cima do `detail` do backend, que é quem tem razão.
 *
 * O 422 é o único que fala de dado faltando, e ele é sempre do apurador —
 * jornada, curadoria, tarifa. `gerar` e `exportar` mantêm o 422 listado porque
 * um 422 deles seria recusa do mesmo jeito, mas nenhuma cena desta tela chega
 * lá: `gerar` só responde 403/404/409, e o único 422 da remessa é a cesta, para
 * a qual esta tela não oferece botão de banco.
 */
const MISSING_DATA_REFUSAL =
  "Apuração recusada — falta dado, não é falha do sistema";
const ALREADY_GENERATED_REFUSAL =
  "Competência já gerada — o estado não permite, não é falha do sistema";
//: ⛔ A FRASE DESCREVE A CONDIÇÃO, NÃO UM STATUS. O 409 de `?formato=banco`
//: dispara para todo status fora de `_PAGAVEL = {generated, exported}`
//: (`export.py:314`), o que inclui `cancelled` — que a migration do ciclo já
//: autoriza (`generated -> cancelled`) e `GET /dp/ciclos` já filtra. "Ainda em
//: rascunho" nasceria falsa nesse dia, e o `detail` embaixo, dizendo
//: «cancelled», desmentiria a tarja: a cor certa com o fato errado, que é a
//: classe de defeito que este conserto veio matar, um estado adiante.
const NOT_FROZEN_REFUSAL =
  "Ciclo não está congelado — o estado não permite, não é falha do sistema";

/**
 * A competência na tela, venha ela da apuração ou do histórico.
 *
 * `rows` é `null`, e não vazio, quando ela veio do histórico: `GET /dp/ciclos`
 * devolve o resumo sem as linhas, e não existe rota que as recupere. Vazio
 * diria "ninguém tem direito" sobre uma competência que pode ter duzentas
 * linhas — a diferença entre não ter e não ter sido carregado.
 */
type Displayed = {
  id: string | null;
  kind: CycleKind;
  period_year: number;
  period_month: number;
  window_start: string;
  window_end: string;
  business_days: number | null;
  status: string;
  entitled_count: number;
  denied_count: number;
  total_amount: string;
  can_export_remittance: boolean;
  rows: CycleEntitlementRow[] | null;
};

/**
 * Qual competência mostrar quando o histórico traz mais de uma linha.
 *
 * A congelada ganha da rascunho, sempre. O `unique` da competência inclui o
 * `status`, então um banco que já passou pelo bug do segundo rascunho tem as
 * duas — e mostrar o rascunho esconderia justamente a que virou remessa.
 */
function pickCycle(rows: CycleSummary[]): CycleSummary | null {
  return rows.find((row) => PAYABLE.includes(row.status)) ?? rows[0] ?? null;
}

function fromSummary(
  summary: CycleSummary,
  canExportRemittance: boolean,
): Displayed {
  return { ...summary, can_export_remittance: canExportRemittance, rows: null };
}

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
 *
 * ⛔ A COMPETÊNCIA VEM DO SERVIDOR, E "APURAR" SOME QUANDO ELA ESTÁ CONGELADA
 * Enquanto o ciclo vivia só em `useState`, um F5 dizia "nada apurado" para um
 * mês já gerado — e a única ação oferecida, apurar, **criava uma segunda linha**
 * ao lado da gerada, porque `save_draft` procura rascunho ABERTO e o `unique` da
 * competência inclui o `status`. O operador passava a ver "Rascunho" para uma
 * competência congelada, e a remessa que ele conferiu ficava inalcançável.
 *
 * ⚠️ ISSO FECHA O CAMINHO DE UM OPERADOR SÓ. NÃO FECHA O INSERT.
 * O banco continua aceitando a segunda linha: a `unique` de `app.benefit_cycle`
 * inclui o `status`, então o rascunho novo não colide com a gerada, e
 * `trg_benefit_cycle_immutable` é `before update or delete` — não cobre INSERT.
 * Duas abas, ou dois operadores no mesmo minuto, e ela nasce assim mesmo. A
 * guarda de verdade é do backend; o que esta camada faz é não **oferecer** o
 * clique, e é por isso que ela também se fecha quando não sabe (`podeApurar`).
 *
 * ✅ Desde `6c61592` (08/09/2026) o backend também recusa: a reserva de
 * `save_draft` perdeu o `status` do `where` e trava a competência inteira com
 * `for update`, e reapurar sobre `generated`/`exported` volta 409. O que esta
 * camada faz não mudou — ela continua não oferecendo o clique.
 */
export function MonthlyCycle({
  filters,
  history,
  canWrite,
}: {
  filters: CycleFilters;
  /** O que `GET /dp/ciclos` respondeu para esta competência. */
  history: CycleListResult;
  /** `util.is_admin` — apurar e gerar. Ler e exportar é outro eixo. */
  canWrite: boolean;
}) {
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
  const apurado = result?.key === chave ? result.cycle : null;

  const gravada = history.status === "ok" ? pickCycle(history.list.rows) : null;
  const cycle: Displayed | null =
    apurado ??
    (gravada
      ? fromSummary(
          gravada,
          history.status === "ok" && history.list.can_export_remittance,
        )
      : null);

  const congelada = cycle !== null && PAYABLE.includes(cycle.status);
  // Sem a lista do servidor a tela não sabe se este mês já foi gerado, e o
  // INSERT que o clique dispara não colide com a linha congelada. Não saber vale
  // como congelada: o alerta pede o F5, e o F5 é o que devolve o botão. O custo
  // de fechar é uma recarga; o de abrir é um rascunho que esconde a remessa.
  const historicoLegivel = history.status === "ok";
  // Reapurar rascunho é seguro e é para isso que o rascunho existe; reapurar
  // competência congelada é o que duplica a linha. O botão segue o estado.
  const podeApurar = canWrite && !congelada && historicoLegivel;

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
      // O rascunho recém-gravado passa a existir no histórico: sem isto, a
      // próxima leitura do servidor ainda diria que não há competência.
      router.refresh();
    } catch (caught) {
      setResult(null);
      setFailure(
        recusa(
          caught,
          {
            // 409: a competência já foi gerada. O dado está todo lá — o que
            // não permite é o estado, e "falta dado" aqui seria falso.
            409: ALREADY_GENERATED_REFUSAL,
            422: MISSING_DATA_REFUSAL,
          },
          "Não consegui apurar a competência.",
        ),
      );
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
      setFailure(
        recusa(
          caught,
          {
            // O mesmo estado do 409 do apurar — "este ciclo não está mais em
            // rascunho" —, então a mesma frase. A tela não precisa de uma
            // segunda para o mesmo fato.
            409: ALREADY_GENERATED_REFUSAL,
            422: MISSING_DATA_REFUSAL,
          },
          "Não consegui gerar o ciclo.",
        ),
      );
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
      setFailure(
        recusa(
          caught,
          {
            // ⛔ O ESTADO OPOSTO: aqui o ciclo é rascunho de menos, não gerado
            // demais. Reaproveitar a frase do apurar diria o inverso do que
            // aconteceu, e a tarja estaria certa de cor e errada de fato.
            409: NOT_FROZEN_REFUSAL,
            422: MISSING_DATA_REFUSAL,
          },
          "Não consegui gerar o arquivo.",
        ),
      );
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
            podeApurar ? (
              <Button onClick={apurar} disabled={busy === "apurar"}>
                {busy === "apurar" ? "Apurando…" : "Apurar competência"}
              </Button>
            ) : null
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

      {history.status === "unavailable" ? (
        <Alert>
          Não consegui ler as competências já apuradas. O que estiver na tela
          veio desta sessão, e apurar fica indisponível até a leitura voltar:
          sem ela não dá para saber se este mês já foi gerado, e apurar de novo
          abriria uma segunda apuração ao lado da que virou remessa. Recarregue
          a página.
        </Alert>
      ) : null}

      {failure ? <FailureBanner failure={failure} /> : null}

      {cycle ? (
        <>
          <Summary cycle={cycle} />
          <Exports
            cycle={cycle}
            busy={busy}
            canWrite={canWrite}
            onGerar={gerar}
            onExportar={exportar}
          />
          {cycle.rows === null ? (
            <Card className="p-6">
              <EmptyState
                icon={CalendarRange}
                tone="neutral"
                compact
                title="A conferência pessoa a pessoa sai nos arquivos"
                description="Esta competência foi lida do histórico, e a lista por pessoa não volta por ali — ela nasce na apuração. O Excel e o PDF acima trazem as mesmas linhas, com o motivo de quem ficou de fora."
              />
            </Card>
          ) : (
            <People kind={cycle.kind} rows={cycle.rows} />
          )}
        </>
      ) : (
        <Card className="p-6">
          <EmptyState
            icon={CalendarRange}
            tone="neutral"
            title={`Nada apurado em ${formatCompetencia(filters.year, filters.month)}`}
            description={
              podeApurar
                ? "Apurar não grava nada definitivo: o resultado é um preview, feito para ser conferido e reapurado. O que congela a competência é gerar o ciclo, depois."
                : "Quando alguém apurar esta competência, ela aparece aqui com os arquivos para conferência."
            }
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
        {failure.title}
      </p>
      <p className="text-sm text-pretty">{failure.message}</p>
    </div>
  );
}

function Summary({ cycle }: { cycle: Displayed }) {
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
  canWrite,
  onGerar,
  onExportar,
}: {
  cycle: Displayed;
  busy: string | null;
  canWrite: boolean;
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
          // Congelar é escrita, e `accounting` confere a remessa sem apurar
          // nada — o botão não fica cinza para ele, fica fora do DOM.
          congelado || !canWrite ? null : (
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
  cycle: Displayed;
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
function People({
  kind,
  rows,
}: {
  kind: CycleKind;
  rows: CycleEntitlementRow[];
}) {
  const grupos = groupByUnit(rows);
  const vt = kind === TRANSPORT_VOUCHER;

  if (rows.length === 0) {
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
 * deles é a resposta, não um detalhe técnico a esconder. O valor de cada um é a
 * tarja que a recusa recebe: um status listado com a frase do outro é a cor
 * certa com o motivo errado.
 */
function recusa(
  caught: unknown,
  refusals: Record<number, string>,
  padrao: string,
): Failure {
  if (caught instanceof ApiError && caught.detail) {
    const tarja = refusals[caught.status];
    return tarja
      ? { kind: "refusal", title: tarja, message: caught.detail }
      : { kind: "error", message: caught.detail };
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
