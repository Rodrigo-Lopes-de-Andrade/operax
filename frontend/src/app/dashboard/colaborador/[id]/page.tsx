import { ArrowLeft, UserX } from "lucide-react";
import type { Metadata } from "next";

import { pageTitle } from "@/lib/brand";
import Link from "next/link";

import { EmployeeHeader } from "@/components/colaborador/employee-header";
import {
  CompensationCard,
  DocumentsCard,
} from "@/components/colaborador/sensitive-blocks";
import { WorkdayHistory } from "@/components/colaborador/workday-history";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader, KpiCard } from "@/components/ui/kpi-card";
import { Rankbar } from "@/components/ui/rankbar";
import { SignedMinutes } from "@/components/ui/signed-minutes";
import { loadEmployee } from "@/lib/colaborador/queries";
import {
  DEFAULT_PERIOD,
  PERIODS,
  periodRange,
  todayInTenantZone,
  type Period,
  type RawSearchParams,
} from "@/lib/ponto/filters";
import {
  formatDayLong,
  formatDuration,
  formatNumber,
  formatRange,
} from "@/lib/ponto/format";
import { PONTO_PATH } from "@/lib/ponto/url";

export const metadata: Metadata = {
  title: pageTitle("Colaborador"),
};

/**
 * Individual consultation — Caminho 2 from end to end.
 *
 * What exists on this screen is decided by the caller's role, not by a flag this
 * page reads: the backend simply does not send the blocks a role may not reach,
 * and what is not sent is not rendered. There is no padlock to explain and no
 * layout that shifts when someone has more permission.
 */
export default async function ColaboradorPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<RawSearchParams>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const requested = Array.isArray(query.per) ? query.per[0] : query.per;
  const period: Period = PERIODS.includes(requested as Period)
    ? (requested as Period)
    : DEFAULT_PERIOD;
  const range = periodRange(period, todayInTenantZone());

  const detail = await loadEmployee(id, range);

  if (!detail) {
    return (
      <Card className="p-6">
        <EmptyState
          icon={UserX}
          tone="neutral"
          title="Colaborador não encontrado"
          description="Ou a pessoa não existe, ou está numa unidade fora do seu acompanhamento. As duas respostas são a mesma de propósito."
        >
          <Link
            href={PONTO_PATH}
            className="text-brand-strong text-sm font-bold underline"
          >
            Voltar para a gestão de ponto
          </Link>
        </EmptyState>
      </Card>
    );
  }

  const { employee, indicators, by_type, workdays, justifications } = detail;

  return (
    <div className="flex flex-col gap-4">
      <Link
        href={PONTO_PATH}
        className="text-ink-muted hover:text-ink flex w-fit items-center gap-1.5 text-xs font-bold"
      >
        <ArrowLeft size={14} aria-hidden />
        Gestão de ponto
      </Link>

      <EmployeeHeader employee={employee} period={period} />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          eyebrow="Ocorrências"
          value={formatNumber(indicators.events)}
          note={formatRange(range.de, range.ate)}
        />
        <KpiCard
          eyebrow="Minutos de desvio"
          value={formatDuration(indicators.minutes_abs)}
          note="Soma em módulo das duas direções."
        />
        <KpiCard
          eyebrow="Dias com desvio"
          value={formatNumber(indicators.days_with_deviation)}
          note="Três ou mais é padrão, não dia ruim."
        />
        <KpiCard
          eyebrow="Pendentes de ciclo"
          value={formatNumber(indicators.pending_cycle)}
          note="Ainda não entraram em relatório."
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          {/* Deliberadamente NAO e o "saldo de horas" do desenho. Espelhar o
              saldo do sistema de ponto ou calcula-lo e decisao em aberto
              (docs/COBERTURA-ESCOPO.md), e este numero nao a antecipa: e a soma
              assinada dos minutos de desvio do recorte, nada alem disso. */}
          <CardHeader title="Soma dos desvios no período" />
          <div className="flex flex-col gap-3 px-5 py-5">
            <SignedMinutes
              minutes={indicators.minutes_balance}
              direction={balanceDirection(indicators.minutes_balance)}
              size="lg"
            />
            {/* Nunca "hora extra": o registro oficial e o do sistema de ponto. */}
            <p className="text-ink-muted text-xs text-pretty">
              Soma assinada dos minutos apontados no recorte. Não é saldo de
              horas: a apuração válida é a do sistema de ponto.
            </p>
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader title="Desvio por tipo" />
          <div className="px-5 py-5">
            {by_type.length === 0 ? (
              <p className="text-ink-faint text-sm">
                Nenhum desvio no período.
              </p>
            ) : (
              <Rankbar
                items={by_type.map((entry) => ({
                  key: entry.type,
                  label: entry.description,
                  value: entry.events,
                  display: `${formatNumber(entry.events)} · ${formatNumber(entry.minutes_abs)} min`,
                }))}
              />
            )}
          </div>
        </Card>
      </div>

      <WorkdayHistory
        workdays={workdays}
        punches={detail.punches}
        readAt={detail.punches_read_at}
      />

      <Card>
        <CardHeader
          title="Justificativas"
          note="Quem justifica não decide sozinho se a justificativa vale."
        />
        <div className="px-5 py-5">
          {justifications.length === 0 ? (
            <p className="text-ink-faint text-sm">
              Nenhuma justificativa registrada.
            </p>
          ) : (
            <ul className="flex flex-col gap-4">
              {justifications.map((justification, index) => (
                <li
                  key={`${justification.reference_date}-${index}`}
                  className="flex flex-col gap-1"
                >
                  <span className="text-ink-faint font-mono text-xs">
                    {formatDayLong(justification.reference_date)}
                  </span>
                  <span className="text-ink-body text-sm">
                    {justification.text}
                  </span>
                  <span className="text-ink-faint text-xs">
                    {justification.author_name ?? "Autor não registrado"} ·{" "}
                    {justification.source}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      {detail.compensation || detail.documents || detail.exams ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {detail.compensation ? (
            <CompensationCard bands={detail.compensation} />
          ) : null}
          {detail.documents || detail.exams ? (
            <DocumentsCard documents={detail.documents} exams={detail.exams} />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function balanceDirection(minutes: number): string {
  if (minutes > 0) {
    return "surplus";
  }

  return minutes < 0 ? "shortfall" : "neutral";
}
