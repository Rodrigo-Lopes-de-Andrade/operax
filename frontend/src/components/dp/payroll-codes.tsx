"use client";

import { ListChecks } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge, Chip } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Table, type Column } from "@/components/ui/table";
import { ApiError, requestApiAsUser } from "@/lib/api";
import {
  formatDayInTenantZone,
  PAYROLL_CATEGORIES,
  PAYROLL_CATEGORY_LABEL,
  PAYROLL_NATURE_LABEL,
} from "@/lib/dp/format";
import type { PayrollCodeList, PayrollCodeRow } from "@/lib/dp/queries";
import { label } from "@/lib/rh/labels";

const COLUMNS: Column[] = [
  { key: "codigo", label: "Código", mono: true, width: "12%" },
  { key: "rotulo", label: "Rótulo" },
  { key: "natureza", label: "Natureza", width: "12%" },
  { key: "categoria", label: "Categoria", width: "20%" },
  { key: "aval", label: "Aval", width: "18%" },
  { key: "acao", label: "", align: "right", width: "18%" },
];

/**
 * Curadoria de rubrica — o plano de contas do cliente, código a código.
 *
 * A LISTA CHEGA PRONTA, E O NÚMERO DO TOPO É A AFIRMAÇÃO DE COMPLETUDE
 * `pending` conta os códigos que a folha usa e ninguém classificou. Ele vem da
 * mesma função que entrega categoria a quem soma os indicadores financeiros, e
 * por isso a tela o mostra e não o recalcula: "sem pendência" tem de ser o
 * backend dizendo, não a ausência de aviso.
 *
 * ⛔ NÃO EXISTE APAGAR, E DESFAZER O AVAL NÃO APAGA
 * `validated: false` tira o aval e mantém a categoria — regra 6 estendida à
 * curadoria. Confirmar exige categoria: o banco não aceita validar sem
 * classificar, e o select vazio não envia nada.
 *
 * `in_payroll: false` é o código que alguém curou e a folha não usa mais. Ele
 * fica visível e marcado, e não conta como pendência — o número é da API.
 */
export function PayrollCodes({ screen }: { screen: PayrollCodeList }) {
  const router = useRouter();
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // `screen.can_write` só; nunca `?? true`. O que chega é JSON, e uma resposta
  // sem a chave vale "não pode".
  const canWrite = screen.can_write === true;

  function categoryFor(row: PayrollCodeRow): string {
    return chosen[row.code] ?? row.category ?? "";
  }

  async function patch(
    row: PayrollCodeRow,
    category: string,
    validated: boolean,
  ) {
    setBusy(row.code);
    setError(null);

    try {
      await requestApiAsUser(`/dp/rubricas/${encodeURIComponent(row.code)}`, {
        method: "PATCH",
        body: { category, validated },
      });
      setChosen((atual) => {
        const proximo = { ...atual };
        delete proximo[row.code];
        return proximo;
      });
      router.refresh();
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.detail
          ? caught.detail
          : "Não consegui gravar a rubrica. Nada foi alterado.",
      );
    } finally {
      setBusy(null);
    }
  }

  function confirm(row: PayrollCodeRow) {
    const category = categoryFor(row);

    if (!category) {
      setError(`Escolha a categoria de ${row.code} antes de confirmar.`);
      return;
    }

    void patch(row, category, true);
  }

  if (screen.rows.length === 0) {
    return (
      <Card className="p-6">
        <EmptyState
          icon={ListChecks}
          tone="neutral"
          title="Nenhum código de rubrica"
          description="A lista nasce da folha importada. Quando uma competência entrar, os códigos aparecem aqui para classificar."
        />
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-5">
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Pendências
        </p>
        <p
          role="status"
          className="text-ink text-lg font-extrabold tabular-nums"
        >
          {screen.pending === 0
            ? "Sem pendência"
            : `${screen.pending} ${screen.pending === 1 ? "código usado" : "códigos usados"} pela folha sem categoria`}
        </p>
        <p className="text-ink-muted text-xs text-pretty">
          {screen.pending === 0
            ? "Todo código que a folha usa tem categoria. Os indicadores financeiros saem completos."
            : "Enquanto houver pendência, o indicador financeiro que depende dessa verba sai incompleto — e diz isso."}
        </p>
      </Card>

      {error ? <Alert>{error}</Alert> : null}

      <Card>
        <CardHeader
          title="Plano de contas"
          note={`${screen.rows.length} ${screen.rows.length === 1 ? "código" : "códigos"}`}
        />
        <Table
          columns={COLUMNS}
          caption="Códigos de rubrica e a categoria de cada um"
          rows={screen.rows.map((row) => {
            // Capturada aqui para o `onClick` de baixo: o TS não leva o
            // estreitamento de `row.category` para dentro da closure.
            const category = row.category;

            return {
              id: row.code,
              cells: {
                codigo: (
                  <span className="flex flex-col gap-1">
                    <span>{row.code}</span>
                    {row.in_payroll ? null : <Chip>fora da folha</Chip>}
                  </span>
                ),
                rotulo: row.label ?? row.code,
                natureza: label(PAYROLL_NATURE_LABEL, row.nature),
                categoria: canWrite ? (
                  <select
                    aria-label={`Categoria de ${row.code}`}
                    value={categoryFor(row)}
                    onChange={(event) =>
                      setChosen((atual) => ({
                        ...atual,
                        [row.code]: event.target.value,
                      }))
                    }
                    disabled={busy === row.code}
                    className="border-control-line bg-control text-ink h-9 w-full rounded-[10px] border px-2 text-sm"
                  >
                    <option value="">— sem categoria —</option>
                    {PAYROLL_CATEGORIES.map((option) => (
                      <option key={option} value={option}>
                        {PAYROLL_CATEGORY_LABEL[option]}
                      </option>
                    ))}
                  </select>
                ) : (
                  label(PAYROLL_CATEGORY_LABEL, row.category)
                ),
                aval: <Approval row={row} />,
                acao: canWrite ? (
                  <span className="flex items-center justify-end gap-3">
                    <button
                      type="button"
                      onClick={() => confirm(row)}
                      disabled={busy === row.code}
                      className="text-brand-strong text-xs font-bold underline disabled:opacity-60"
                    >
                      {busy === row.code ? "Gravando…" : "Confirmar"}
                    </button>
                    {row.validated && category ? (
                      <button
                        type="button"
                        onClick={() => void patch(row, category, false)}
                        disabled={busy === row.code}
                        className="text-ink-muted text-xs font-bold underline disabled:opacity-60"
                      >
                        Desfazer aval
                      </button>
                    ) : null}
                  </span>
                ) : null,
              },
            };
          })}
        />
      </Card>
    </div>
  );
}

/**
 * O que a curadoria já disse do código. "Pendente" é só para o que a folha usa:
 * um código fora da folha sem categoria não conta, e a tela não o marca.
 */
function Approval({ row }: { row: PayrollCodeRow }) {
  if (row.validated) {
    return (
      <span className="flex flex-col gap-1">
        <Badge tone="good" dot>
          Conferida
        </Badge>
        {row.validated_at ? (
          <span className="text-ink-muted text-xs">
            em {formatDayInTenantZone(row.validated_at)}
          </span>
        ) : null}
      </span>
    );
  }

  if (row.category) {
    return <Chip>proposta, sem aval</Chip>;
  }

  return row.in_payroll ? (
    <Badge tone="alert" dot>
      Pendente
    </Badge>
  ) : (
    <span className="text-ink-faint">—</span>
  );
}
