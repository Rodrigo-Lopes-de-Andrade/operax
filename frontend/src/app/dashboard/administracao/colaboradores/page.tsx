import { UserRoundSearch, Users } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { EmployeeFilters } from "@/components/rh/employee-filters";
import { DueCell } from "@/components/rh/due-cell";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Table, type Column } from "@/components/ui/table";
import { pageTitle } from "@/lib/brand";
import { loadIdentity, reachesHr } from "@/lib/identity";
import type { RawSearchParams } from "@/lib/ponto/filters";
import { formatDayShort } from "@/lib/ponto/format";
import { STATUS_LABEL, label } from "@/lib/rh/labels";
import { loadEmployees } from "@/lib/rh/queries";
import { IMPORTACAO_PATH, employeeHref, parseRhFilters } from "@/lib/rh/url";

export const metadata: Metadata = {
  title: pageTitle("Colaboradores"),
};

const COLUMNS: Column[] = [
  { key: "pessoa", label: "Colaborador", width: "26%" },
  { key: "hr_code", label: "ID RH", mono: true, width: "10%" },
  { key: "cargo", label: "Cargo", width: "18%" },
  { key: "unidade", label: "Unidade", width: "16%" },
  { key: "situacao", label: "Situação", width: "12%" },
  { key: "vencimento", label: "Próximo vencimento", width: "18%" },
];

const STATUS_TONE: Record<string, "good" | "alert" | "neutral"> = {
  active: "good",
  afastado: "alert",
  vacation: "neutral",
  desligado: "neutral",
};

/**
 * A aba Colaboradores.
 *
 * A visibilidade da aba segue o papel, e a decisão é tomada aqui, no servidor:
 * quem não alcança a área recebe 404 em vez de uma tela vazia, porque uma tela
 * vazia com o título "Colaboradores" já conta que a área existe. Isso não é a
 * segurança — a segurança é a RLS filtrar o que volta e o backend recusar toda
 * escrita —, é não anunciar o que não se pode abrir.
 *
 * A ordem é a urgência: quem vence primeiro aparece primeiro. Uma lista de RH
 * ordenada por nome é uma agenda; ordenada por prazo, é trabalho.
 */
export default async function ColaboradoresPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const identity = await loadIdentity();

  if (!reachesHr(identity?.role)) {
    notFound();
  }

  const filters = parseRhFilters(await searchParams);
  const list = await loadEmployees(filters);
  const today = new Date();

  const rows = list.rows.map((row) => ({
    id: row.employee_id,
    href: employeeHref(row.employee_id),
    cells: {
      pessoa: (
        <span className="flex flex-col">
          <span className="text-ink font-bold">{row.name}</span>
          <span className="text-ink-faint font-mono text-xs">
            {row.registration_number ?? "sem matrícula"}
            {row.hired_on ? ` · desde ${formatDayShort(row.hired_on)}` : ""}
          </span>
        </span>
      ),
      hr_code: row.hr_code ?? (
        <span className="text-ink-faint">a vincular</span>
      ),
      cargo: row.cargo ?? "—",
      unidade: row.unit_name ?? "—",
      situacao: (
        <Badge tone={STATUS_TONE[row.status] ?? "neutral"} dot>
          {label(STATUS_LABEL, row.status)}
        </Badge>
      ),
      vencimento: <DueCell due={row.due} today={today} />,
    },
  }));

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
            Administração
          </p>
          <h1 className="text-ink text-xl font-extrabold">Colaboradores</h1>
        </div>
        <Link
          href={IMPORTACAO_PATH}
          className="text-brand-strong text-sm font-bold underline"
        >
          Importar planilha
        </Link>
      </header>

      <EmployeeFilters filters={filters} rows={list.rows} />

      <Card>
        <CardHeader
          title="Quadro"
          note={
            list.truncated
              ? `Mostrando as ${list.rows.length} primeiras. Estreite o filtro para ver o resto — a lista foi cortada, não terminou.`
              : `${list.rows.length} pessoa(s), ordenadas pelo que vence primeiro.`
          }
        />
        <Table
          columns={COLUMNS}
          rows={rows}
          caption="Colaboradores e próximos vencimentos"
          empty={
            <EmptyState
              icon={filters.busca ? UserRoundSearch : Users}
              tone="neutral"
              title={
                filters.busca
                  ? "Nenhum colaborador com esse termo"
                  : "Nenhum colaborador neste recorte"
              }
              description={
                filters.busca
                  ? "A busca cobre nome, matrícula e ID RH."
                  : "O quadro é espelhado do sistema de ponto. Se está vazio, a sincronização ainda não trouxe ninguém para este recorte."
              }
            />
          }
        />
      </Card>
    </div>
  );
}
