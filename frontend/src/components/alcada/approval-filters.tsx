"use client";

import { ChevronLeft, ChevronRight, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Card } from "@/components/ui/kpi-card";
import { SelectNav, type SelectGroup } from "@/components/ui/select-nav";
import {
  approvalHref,
  isCalendarDay,
  shiftMonth,
  YEAR_MAX,
  YEAR_MIN,
  type ApprovalFilters,
  type ResolvedApprovalFilters,
} from "@/lib/alcada/url";
import type { ApprovalQueueRow } from "@/lib/alcada/review";
import { formatCompetencia, formatDate } from "@/lib/dp/format";
import { MESES } from "@/lib/folha/url";
import type { UnitOption } from "@/lib/ponto/queries";

const LABEL = "text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase";
const CONTROL =
  "border-control-line bg-control text-ink h-10 rounded-[10px] border px-3 text-sm font-semibold";

/** Ano seguinte e dois anteriores, sem sair dos limites que o parser aceita. */
function years(current: number): number[] {
  return [current + 1, current, current - 1, current - 2].filter(
    (year) => year >= YEAR_MIN && year <= YEAR_MAX,
  );
}

/**
 * O recorte da fila: competência, unidade, colaborador e data.
 *
 * Não há botão "aplicar" — cada escolha navega, o estado mora na query string,
 * e o link colado numa conversa abre a fila no mesmo recorte.
 *
 * ⛔ A TELA NÃO SABE ONDE A COMPETÊNCIA COMEÇA NEM ONDE TERMINA
 * `filters` traz a competência que a API usou e `period` a janela que ela
 * devolveu (`util.competencia_janela`, no banco). A frase da janela e o
 * `min`/`max` das datas saem dali; anterior/próxima é aritmética de mês, e
 * quem diz a janela da competência seguinte é a próxima resposta.
 *
 * ⚠️ O seletor de colaborador lista quem TEM justificativa na fila lida, e não
 * o cadastro inteiro: é o único recorte que responde alguma coisa aqui, e o
 * cadastro não precisa sair do banco para montar um `select`. Um colaborador
 * que veio no link e não está na fila continua selecionado, com o nome
 * desconhecido.
 */
export function ApprovalFiltersBar({
  filters,
  period,
  units,
  rows,
}: {
  filters: ResolvedApprovalFilters;
  period: { start: string; end: string };
  units: UnitOption[];
  rows: ApprovalQueueRow[];
}) {
  const router = useRouter();
  const previous = shiftMonth(filters.year, filters.month, -1);
  const next = shiftMonth(filters.year, filters.month, 1);

  const companies = [
    ...new Map(units.map((unit) => [unit.companyId, unit])).values(),
  ];

  const unitGroups: SelectGroup[] = companies.map((company) => ({
    label: company.companyName,
    options: units
      .filter((unit) => unit.companyId === company.companyId)
      .map((unit) => ({
        value: unit.unitId,
        label: unit.name,
        href: approvalHref(filters, { unitId: unit.unitId }),
      })),
  }));

  const employees = new Map(
    rows.map((row) => [row.employee_id, row.employee_name]),
  );

  if (filters.employeeId && !employees.has(filters.employeeId)) {
    employees.set(filters.employeeId, "Colaborador do link");
  }

  const employeeGroups: SelectGroup[] = [
    {
      label: "Com justificativa na fila",
      options: [...employees]
        .sort(([, a], [, b]) => a.localeCompare(b, "pt-BR"))
        .map(([id, name]) => ({
          value: id,
          label: name,
          href: approvalHref(filters, { employeeId: id }),
        })),
    },
  ];

  function goTo(overrides: Partial<ApprovalFilters>) {
    router.push(approvalHref(filters, overrides));
  }

  function day(value: string): string | null | undefined {
    if (value === "") return null;
    return isCalendarDay(value) ? value : undefined;
  }

  const hasCut = Boolean(
    filters.unitId || filters.employeeId || filters.from || filters.to,
  );

  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-end gap-4">
        <nav aria-label="Competência" className="flex items-center gap-1 pb-1">
          <Link
            href={approvalHref(filters, previous)}
            aria-label="Competência anterior"
            className="text-ink-muted hover:text-ink rounded-full p-1.5"
          >
            <ChevronLeft size={18} aria-hidden />
          </Link>
          <Link
            href={approvalHref(filters, next)}
            aria-label="Próxima competência"
            className="text-ink-muted hover:text-ink rounded-full p-1.5"
          >
            <ChevronRight size={18} aria-hidden />
          </Link>
        </nav>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Mês</span>
          <select
            aria-label="Mês da competência"
            value={filters.month}
            onChange={(event) => goTo({ month: Number(event.target.value) })}
            className={CONTROL}
          >
            {MESES.map((name, index) => (
              <option key={name} value={index + 1}>
                {name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Ano</span>
          <select
            aria-label="Ano da competência"
            value={filters.year}
            onChange={(event) => goTo({ year: Number(event.target.value) })}
            className={CONTROL}
          >
            {years(filters.year).map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>

        <SelectNav
          label="Unidade"
          placeholder="Todas as unidades"
          placeholderHref={approvalHref(filters, { unitId: null })}
          value={filters.unitId ?? ""}
          groups={unitGroups}
        />

        <SelectNav
          label="Colaborador"
          placeholder="Todos os colaboradores"
          placeholderHref={approvalHref(filters, { employeeId: null })}
          value={filters.employeeId ?? ""}
          groups={employeeGroups}
        />

        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>De</span>
          <input
            type="date"
            aria-label="Data inicial"
            value={filters.from ?? ""}
            min={period.start}
            max={period.end}
            onChange={(event) => {
              const next = day(event.target.value);
              if (next !== undefined) goTo({ from: next });
            }}
            className={CONTROL}
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Até</span>
          <input
            type="date"
            aria-label="Data final"
            value={filters.to ?? ""}
            min={period.start}
            max={period.end}
            onChange={(event) => {
              const next = day(event.target.value);
              if (next !== undefined) goTo({ to: next });
            }}
            className={CONTROL}
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-ink-muted text-xs">
          A competência de {formatCompetencia(filters.year, filters.month)} vai
          de {formatDate(period.start)} a {formatDate(period.end)}. As datas só
          estreitam essa janela.
        </p>
        {hasCut ? (
          <Link
            href={approvalHref({
              ...filters,
              unitId: null,
              employeeId: null,
              from: null,
              to: null,
            })}
            className="text-brand-strong inline-flex items-center gap-1.5 text-sm font-bold"
          >
            <X size={15} aria-hidden />
            Limpar recorte
          </Link>
        ) : null}
      </div>
    </Card>
  );
}
