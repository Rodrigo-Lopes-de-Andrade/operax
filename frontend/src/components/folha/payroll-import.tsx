"use client";

import { Check, Download, FileSpreadsheet } from "lucide-react";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge, Chip } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Table, type Column } from "@/components/ui/table";
import {
  ApiError,
  downloadApiAsUser,
  requestApiAsUser,
  uploadApiAsUser,
} from "@/lib/api";
import {
  MESES,
  competenciaLabel,
  templateFilename,
  templateHref,
} from "@/lib/folha/url";

type LineError = { code: string; message: string; column: string | null };
type LineReport = { line: number; errors: LineError[]; warnings: LineError[] };
type Counts = { total: number; ok: number; error: number };
type Replacement = { entries: number; imported_at: string | null };
type Preview = {
  import_id: string;
  period: string;
  layout_version: string;
  status: string;
  counts: Counts;
  unmapped_codes: string[];
  lines: LineReport[];
  replaces: Replacement | null;
};
type Result = Preview & { applied: number; replaced: number };

const ERROR_COLUMNS: Column[] = [
  { key: "linha", label: "Linha", mono: true, width: "12%" },
  { key: "coluna", label: "Coluna", mono: true, width: "20%" },
  { key: "motivo", label: "Motivo" },
];

const AVISO_COLUMNS: Column[] = [
  { key: "linha", label: "Linha", mono: true, width: "12%" },
  { key: "motivo", label: "Aviso" },
];

/** O aviso que já é contado em massa pelos códigos — não vira uma linha cada. */
const CODIGO_SEM_CATEGORIA = "codigo_sem_categoria";

/**
 * Importação da folha — competência · arquivo · preview · confirmar.
 *
 * Mesmo fluxo de quatro passos do import de RH, e duas diferenças que não são de
 * estilo:
 *
 * **A folha não entra pela metade.** Uma linha em erro barra o arquivo inteiro,
 * e o botão de confirmar sai do ar com o motivo escrito ao lado — não desabilita
 * calado. Lá, cada linha é um fato independente sobre uma pessoa e as boas
 * entram; aqui as linhas são parcelas de uma soma, e "998 de 1000" é um total
 * que não bate com holerite nenhum e não avisa ninguém.
 *
 * **Confirmar substitui a competência.** O botão diz quantos lançamentos serão
 * substituídos antes de alguém clicar: reenviar a folha de um mês é apagar o que
 * estava lá, e um botão que só diz "Confirmar" esconde justamente isso.
 *
 * Código de evento sem categoria **não** é erro: a linha entra e o valor conta.
 * Ele aparece como código, uma vez cada, e não como mil avisos de linha — a
 * primeira importação de um cliente tem o plano de contas inteiro por mapear, e
 * uma tabela de mil linhas idênticas não é relatório, é ruído.
 */
export function PayrollImport() {
  const hoje = new Date();
  // A competência escolhida aqui vale para **baixar** o modelo. O arquivo
  // enviado vale pelo que a aba de controle dele declara, e é isso que o preview
  // devolve — por isso o seletor não vira estado de filtro na URL: ele não é o
  // recorte de nada, é o mês do arquivo que se quer pegar.
  const [ano, setAno] = useState(hoje.getFullYear());
  const [mes, setMes] = useState(hoje.getMonth() + 1);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState<"idle" | "modelo" | "envio" | "confirmacao">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);

  const step = result ? 4 : preview ? 3 : arquivo ? 2 : 1;

  function limpar() {
    setPreview(null);
    setResult(null);
    setError(null);
  }

  async function baixarModelo() {
    setBusy("modelo");
    setError(null);

    try {
      const { blob, filename } = await downloadApiAsUser(
        templateHref(ano, mes),
        templateFilename(ano, mes),
      );
      salvar(blob, filename);
    } catch (caught) {
      setError(mensagem(caught, "Não consegui gerar o modelo."));
    } finally {
      setBusy("idle");
    }
  }

  async function enviar() {
    if (!arquivo) return;
    setBusy("envio");
    setError(null);
    setResult(null);

    const form = new FormData();
    form.set("arquivo", arquivo);

    try {
      setPreview(await uploadApiAsUser<Preview>("/folha/imports", form));
    } catch (caught) {
      setPreview(null);
      setError(mensagem(caught, "Não consegui ler o arquivo enviado."));
    } finally {
      setBusy("idle");
    }
  }

  async function confirmar() {
    if (!preview) return;
    setBusy("confirmacao");
    setError(null);

    try {
      setResult(
        await requestApiAsUser<Result>(
          `/folha/imports/${preview.import_id}/confirm`,
          { method: "POST" },
        ),
      );
    } catch (caught) {
      setError(mensagem(caught, "Não consegui gravar a folha."));
    } finally {
      setBusy("idle");
    }
  }

  const relatorio = result ?? preview;
  const erros = relatorio?.lines.filter((line) => line.errors.length > 0) ?? [];
  const avisos =
    relatorio?.lines.flatMap((line) =>
      line.warnings
        .filter((aviso) => aviso.code !== CODIGO_SEM_CATEGORIA)
        .map((aviso) => ({ line: line.line, aviso })),
    ) ?? [];

  return (
    <div className="flex flex-col gap-4">
      <Steps current={step} />

      <Card>
        <CardHeader
          title="1. Competência"
          note="O modelo é o do mês. O arquivo enviado vale pela competência que a aba de controle dele declara — não pela escolhida aqui."
        />
        <div className="flex flex-wrap items-end gap-4 px-5 py-5">
          <label className="flex flex-col gap-1.5">
            <span className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
              Mês
            </span>
            <select
              value={mes}
              aria-label="Mês da competência"
              onChange={(event) => {
                setMes(Number(event.target.value));
                limpar();
              }}
              className="border-line-strong text-ink rounded-[10px] border px-3 py-2 text-sm"
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
              value={ano}
              aria-label="Ano da competência"
              onChange={(event) => {
                setAno(Number(event.target.value));
                limpar();
              }}
              className="border-line-strong text-ink rounded-[10px] border px-3 py-2 text-sm"
            >
              {anos(hoje.getFullYear()).map((valor) => (
                <option key={valor} value={valor}>
                  {valor}
                </option>
              ))}
            </select>
          </label>

          <Button onClick={baixarModelo} disabled={busy === "modelo"}>
            <Download size={15} aria-hidden />
            {busy === "modelo" ? "Gerando…" : "Baixar modelo"}
          </Button>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="2. Arquivo"
          note="O modelo vem preenchido com o que já foi importado na competência: corrigir é mexer na linha errada e reenviar."
        />
        <div className="flex flex-wrap items-center gap-4 px-5 py-5">
          <label className="flex flex-col gap-1.5">
            <span className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
              Planilha da folha
            </span>
            <input
              type="file"
              accept=".xlsx"
              aria-label="Planilha da folha"
              onChange={(event) => {
                setArquivo(event.target.files?.[0] ?? null);
                limpar();
              }}
              className="text-ink-muted text-sm"
            />
          </label>
          <Button onClick={enviar} disabled={!arquivo || busy === "envio"}>
            {busy === "envio" ? "Conferindo…" : "Conferir sem gravar"}
          </Button>
        </div>
      </Card>

      {error ? <Alert>{error}</Alert> : null}

      {relatorio ? (
        <Card>
          <CardHeader
            eyebrow={competenciaLabel(relatorio.period)}
            title={result ? "4. Resultado" : "3. Preview"}
            note={
              result
                ? `${result.applied} lançamento(s) gravado(s)${
                    result.replaced > 0
                      ? `, no lugar de ${result.replaced} que estavam na competência.`
                      : "."
                  }`
                : "Nada foi gravado ainda. O que está abaixo é o que aconteceria."
            }
            action={
              result ? null : (
                <Button
                  onClick={confirmar}
                  disabled={
                    busy === "confirmacao" || relatorio.counts.error > 0
                  }
                >
                  {busy === "confirmacao"
                    ? "Gravando…"
                    : relatorio.replaces
                      ? `Substituir ${relatorio.replaces.entries} lançamento(s)`
                      : `Gravar ${relatorio.counts.total} linha(s)`}
                </Button>
              )
            }
          />

          <div className="flex flex-wrap gap-6 px-5 py-4">
            <Contagem rotulo="Linhas lidas" valor={relatorio.counts.total} />
            <Contagem
              rotulo="A gravar"
              valor={relatorio.counts.ok}
              tone="good"
            />
            <Contagem
              rotulo="Com erro"
              valor={relatorio.counts.error}
              tone={relatorio.counts.error > 0 ? "bad" : "neutral"}
            />
          </div>

          {!result && relatorio.counts.error > 0 ? (
            <div className="px-5 pb-4">
              <Alert>
                {relatorio.counts.error} linha(s) em erro. A folha não é
                importada pela metade — a soma da competência deixaria de bater
                com o holerite. Corrija as linhas abaixo na planilha e envie de
                novo.
              </Alert>
            </div>
          ) : null}

          {!result && relatorio.replaces ? (
            <p className="text-ink-muted px-5 pb-4 text-sm text-pretty">
              A competência {competenciaLabel(relatorio.period)} já tem{" "}
              <strong className="text-ink">
                {relatorio.replaces.entries} lançamento(s)
              </strong>
              . Confirmar <strong className="text-ink">substitui</strong> todos
              eles pelo conteúdo deste arquivo — a folha do mês é o que o último
              arquivo diz, não a soma dos enviados.
            </p>
          ) : null}

          {relatorio.unmapped_codes.length > 0 ? (
            <div className="border-line-subtle flex flex-col gap-2 border-t px-5 py-4">
              <p className="text-ink-muted text-sm text-pretty">
                {relatorio.unmapped_codes.length} código(s) de evento ainda sem
                categoria. As linhas entram e os valores contam no total; elas
                só não aparecem nos indicadores por categoria até a curadoria
                com a contabilidade acontecer.
              </p>
              <div className="flex flex-wrap gap-1.5">
                {relatorio.unmapped_codes.map((codigo) => (
                  <Chip key={codigo}>{codigo}</Chip>
                ))}
              </div>
            </div>
          ) : null}

          {erros.length > 0 ? (
            <Table
              columns={ERROR_COLUMNS}
              density="compact"
              caption="Linhas recusadas"
              rows={erros.flatMap((line) =>
                line.errors.map((erro, index) => ({
                  id: `e-${line.line}-${index}`,
                  cells: {
                    linha: String(line.line),
                    coluna: erro.column ?? "—",
                    motivo: erro.message,
                  },
                })),
              )}
            />
          ) : null}

          {avisos.length > 0 ? (
            <Table
              columns={AVISO_COLUMNS}
              density="compact"
              caption="Avisos"
              rows={avisos.map(({ line, aviso }, index) => ({
                id: `a-${line}-${index}`,
                cells: { linha: String(line), motivo: aviso.message },
              }))}
            />
          ) : null}

          {erros.length === 0 && avisos.length === 0 ? (
            <p className="text-ink-muted px-5 pb-5 text-sm">
              Nenhuma linha recusada.
            </p>
          ) : null}
        </Card>
      ) : null}

      {result ? (
        <p className="text-ink-muted flex items-center gap-2 text-sm text-pretty">
          <Check size={16} aria-hidden className="text-good" />A competência{" "}
          {competenciaLabel(result.period)} está gravada. Reenviar um arquivo
          desta mesma competência substitui o que acabou de entrar.
        </p>
      ) : null}
    </div>
  );
}

function Steps({ current }: { current: number }) {
  const passos = ["Competência", "Arquivo", "Preview", "Confirmar"];

  return (
    <ol className="flex flex-wrap gap-2">
      {passos.map((passo, index) => {
        const numero = index + 1;
        const estado =
          numero < current ? "feito" : numero === current ? "atual" : "futuro";

        return (
          <li
            key={passo}
            aria-current={estado === "atual" ? "step" : undefined}
            className={`flex items-center gap-2 rounded-full px-3.5 py-1.5 text-xs font-bold ${
              estado === "feito"
                ? "bg-good-bg text-good"
                : estado === "atual"
                  ? "bg-brand text-on-brand"
                  : "bg-muted text-ink-faint"
            }`}
          >
            {estado === "feito" ? (
              <Check size={13} aria-hidden />
            ) : (
              <FileSpreadsheet size={13} aria-hidden />
            )}
            {numero}. {passo}
          </li>
        );
      })}
    </ol>
  );
}

function Contagem({
  rotulo,
  valor,
  tone = "neutral",
}: {
  rotulo: string;
  valor: number;
  tone?: "neutral" | "good" | "bad";
}) {
  return (
    <span className="flex flex-col gap-1">
      <span className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
        {rotulo}
      </span>
      <Badge tone={tone}>{valor}</Badge>
    </span>
  );
}

/** As competências que valem a pena existir no seletor: este ano e os dois anteriores. */
function anos(atual: number): number[] {
  return [atual, atual - 1, atual - 2];
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

function mensagem(caught: unknown, padrao: string): string {
  return caught instanceof ApiError && caught.detail ? caught.detail : padrao;
}
