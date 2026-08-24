"use client";

import { Check, Download, FileSpreadsheet } from "lucide-react";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Table, type Column } from "@/components/ui/table";
import {
  ApiError,
  downloadApiAsUser,
  requestApiAsUser,
  uploadApiAsUser,
} from "@/lib/api";

type LineError = { code: string; message: string; column: string | null };
type LineReport = {
  line: number;
  status: "ok" | "unchanged" | "error";
  errors: LineError[];
};
type Counts = { total: number; ok: number; unchanged: number; error: number };
type Preview = {
  import_id: string;
  type: string;
  layout_version: string;
  status: string;
  counts: Counts;
  lines: LineReport[];
};
type Result = Preview & { applied: number; partial: boolean };

const TIPOS = [
  {
    value: "hr_link",
    label: "Vínculo",
    note: "Matrícula e nome impressos; o ID RH é o que se preenche. É o primeiro de todos — sem ele, nenhum outro modelo casa a planilha do cliente com o cadastro.",
  },
  {
    value: "hr_employee",
    label: "Cadastro",
    note: "Regime e CTPS. Carrega dado pessoal, então só desce para quem alcança o domínio de PII.",
  },
  {
    value: "hr_exam",
    label: "ASO",
    note: "Um exame por pessoa: o modelo traz o mais recente e o upload é a diferença. Guarda aptidão e validade — nunca diagnóstico, CID ou descrição de restrição. Só desce para quem alcança o domínio de saúde.",
  },
  {
    value: "hr_compensation",
    label: "Remuneração",
    note: "Uma vigência por linha. Só desce para quem alcança o domínio de remuneração, e o download fica registrado na auditoria.",
  },
] as const;

const ERROR_COLUMNS: Column[] = [
  { key: "linha", label: "Linha", mono: true, width: "12%" },
  { key: "coluna", label: "Coluna", mono: true, width: "20%" },
  { key: "motivo", label: "Motivo" },
];

/**
 * Importação de RH — os quatro passos da tela: tipo · arquivo · preview ·
 * confirmar.
 *
 * O preview **não grava nada**. É a promessa central desta tela e é do backend,
 * não daqui: `POST /rh/imports` guarda o arquivo, julga cada linha e devolve o
 * relatório sem tocar no domínio. Confirmar relê o arquivo guardado e revalida
 * antes de aplicar — entre ver o preview e clicar, alguém pode ter tomado o ID
 * RH e a folha pode ter fechado uma competência.
 *
 * Erro de arquivo e erro de linha são coisas diferentes e aparecem em lugares
 * diferentes. Arquivo sem a aba de controle, de outro cliente ou com o cabeçalho
 * remontado à mão é recusado inteiro, antes da primeira linha — porque um
 * arquivo errado não tem linha certa.
 */
export function ImportWizard() {
  const [tipo, setTipo] = useState<string | null>(null);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState<"idle" | "modelo" | "envio" | "confirmacao">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);

  const step = result ? 4 : preview ? 3 : arquivo ? 2 : tipo ? 2 : 1;

  async function baixarModelo() {
    if (!tipo) return;
    setBusy("modelo");
    setError(null);

    try {
      const { blob, filename } = await downloadApiAsUser(
        `/rh/template/${tipo}`,
        `${tipo}.xlsx`,
      );
      // O link precisa estar no documento e a URL precisa sobreviver ao clique:
      // revogar na linha seguinte cancela o download que acabou de começar.
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.rel = "noopener";
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
    } catch (caught) {
      setError(mensagem(caught, "Não consegui gerar o modelo."));
    } finally {
      setBusy("idle");
    }
  }

  async function enviar() {
    if (!tipo || !arquivo) return;
    setBusy("envio");
    setError(null);
    setResult(null);

    const form = new FormData();
    form.set("tipo", tipo);
    form.set("arquivo", arquivo);

    try {
      setPreview(await uploadApiAsUser<Preview>("/rh/imports", form));
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
          `/rh/imports/${preview.import_id}/confirm`,
          { method: "POST" },
        ),
      );
    } catch (caught) {
      setError(mensagem(caught, "Não consegui confirmar a importação."));
    } finally {
      setBusy("idle");
    }
  }

  const relatorio = result ?? preview;
  const erros =
    relatorio?.lines.filter((line) => line.status === "error") ?? [];

  return (
    <div className="flex flex-col gap-4">
      <Steps current={step} />

      <Card>
        <CardHeader
          title="1. Tipo de importação"
          note="Um tipo por modelo — uma tabela por vez é restrição, não convenção."
        />
        <div className="grid gap-3 px-5 py-5 md:grid-cols-3">
          {TIPOS.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={tipo === item.value}
              onClick={() => {
                setTipo(item.value);
                setPreview(null);
                setResult(null);
                setError(null);
              }}
              className={`flex flex-col gap-1.5 rounded-[14px] border p-4 text-left transition ${
                tipo === item.value
                  ? "border-brand bg-brand-soft/25"
                  : "border-line-subtle hover:border-line-strong"
              }`}
            >
              <span className="text-ink text-md font-extrabold">
                {item.label}
              </span>
              <span className="text-ink-muted text-xs text-pretty">
                {item.note}
              </span>
            </button>
          ))}
        </div>
      </Card>

      {tipo ? (
        <Card>
          <CardHeader
            title="2. Arquivo"
            note="O modelo vem preenchido com o que já está gravado. Só se preenche o que falta."
            action={
              <Button onClick={baixarModelo} disabled={busy === "modelo"}>
                <Download size={15} aria-hidden />
                {busy === "modelo" ? "Gerando…" : "Baixar modelo"}
              </Button>
            }
          />
          <div className="flex flex-wrap items-center gap-4 px-5 py-5">
            <label className="flex flex-col gap-1.5">
              <span className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase">
                Planilha preenchida
              </span>
              <input
                type="file"
                accept=".xlsx"
                aria-label="Planilha preenchida"
                onChange={(event) => {
                  setArquivo(event.target.files?.[0] ?? null);
                  setPreview(null);
                  setResult(null);
                  setError(null);
                }}
                className="text-ink-muted text-sm"
              />
            </label>
            <Button onClick={enviar} disabled={!arquivo || busy === "envio"}>
              {busy === "envio" ? "Conferindo…" : "Conferir sem gravar"}
            </Button>
          </div>
        </Card>
      ) : null}

      {error ? <Alert>{error}</Alert> : null}

      {relatorio ? (
        <Card>
          <CardHeader
            title={result ? "4. Resultado" : "3. Preview"}
            note={
              result
                ? `${result.applied} linha(s) gravada(s).${
                    result.partial
                      ? " O import ficou parcial: as linhas recusadas continuam de fora até virem corrigidas."
                      : ""
                  }`
                : "Nada foi gravado ainda. O que está abaixo é o que aconteceria."
            }
            action={
              result ? null : (
                <Button
                  onClick={confirmar}
                  disabled={busy === "confirmacao" || relatorio.counts.ok === 0}
                >
                  {busy === "confirmacao"
                    ? "Gravando…"
                    : `Gravar ${relatorio.counts.ok} válida(s)`}
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
            {/* "Já estava assim" é informação, não sucesso escondido: sem esta
                contagem o usuário procuraria alterações que não aconteceram. */}
            <Contagem
              rotulo="Já estava assim"
              valor={relatorio.counts.unchanged}
            />
            <Contagem
              rotulo="Com erro"
              valor={relatorio.counts.error}
              tone={relatorio.counts.error > 0 ? "bad" : "neutral"}
            />
          </div>

          {erros.length > 0 ? (
            <Table
              columns={ERROR_COLUMNS}
              density="compact"
              caption="Linhas recusadas"
              rows={erros.flatMap((line) =>
                line.errors.map((erro, index) => ({
                  id: `${line.line}-${index}`,
                  cells: {
                    linha: String(line.line),
                    coluna: erro.column ?? "—",
                    motivo: erro.message,
                  },
                })),
              )}
            />
          ) : (
            <p className="text-ink-muted px-5 pb-5 text-sm">
              Nenhuma linha recusada.
            </p>
          )}
        </Card>
      ) : null}

      {result ? (
        <p className="text-ink-muted flex items-center gap-2 text-sm">
          <Check size={16} aria-hidden className="text-good" />
          Corrija as linhas recusadas na planilha e envie de novo: as que já
          entraram voltam como &ldquo;já estava assim&rdquo; e não são
          reescritas.
        </p>
      ) : null}
    </div>
  );
}

function Steps({ current }: { current: number }) {
  const passos = ["Tipo", "Arquivo", "Preview", "Confirmar"];

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

function mensagem(caught: unknown, padrao: string): string {
  return caught instanceof ApiError && caught.detail ? caught.detail : padrao;
}
