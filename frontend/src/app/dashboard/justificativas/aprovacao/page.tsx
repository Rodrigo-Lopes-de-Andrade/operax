import { FilterX, ShieldOff, TriangleAlert } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ApprovalFiltersBar } from "@/components/alcada/approval-filters";
import { ApprovalQueue } from "@/components/alcada/approval-queue";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { loadApprovalScreen } from "@/lib/alcada/queries";
import { approvalHref, parseApprovalFilters } from "@/lib/alcada/url";
import { pageTitle } from "@/lib/brand";
import { formatCompetencia } from "@/lib/dp/format";
import { loadIdentity, reviewsJustifications } from "@/lib/identity";
import type { RawSearchParams } from "@/lib/ponto/filters";

export const metadata: Metadata = {
  title: pageTitle("Aprovação de justificativas"),
};

/**
 * Aprovação de justificativas — a alçada do RH (P1.3).
 *
 * O supervisor explica o indício em `/dashboard/justificativas`; a explicação
 * nasce `pending` e só vale depois de revisada aqui. Quem revisa é `hr` ou
 * `owner` (`reviewsJustifications`, a cópia da checagem da rota). Outro papel
 * recebe 404, como nas outras telas de administração — a porta não é
 * oferecida. E se a lista daqui e a da API divergirem, manda a API: o 403
 * dela vira "sem acesso", nunca uma tela quebrada.
 *
 * O recorte inteiro vem da query string. Sem `ano`/`mes`, a API usa a
 * competência corrente — calculada no banco, com o relógio do tenant — e a
 * devolve junto com a janela. A tela não calcula nenhuma das duas.
 */
export default async function AprovacaoDeJustificativasPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const identity = await loadIdentity();

  if (!reviewsJustifications(identity?.role)) {
    notFound();
  }

  const filters = parseApprovalFilters(await searchParams);
  const screen = await loadApprovalScreen(filters);
  const { queue } = screen;

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Operação
        </p>
        <h1 className="text-ink text-2xl font-extrabold">
          Aprovação de justificativas
        </h1>
        <p className="text-ink-muted mt-1 max-w-3xl text-sm text-pretty">
          As justificativas que os supervisores escreveram para os indícios
          {queue.status === "ok"
            ? ` de ${formatCompetencia(queue.queue.ano, queue.queue.mes)}`
            : " da competência"}
          . Aprovada, o desvio passa a contar como justificado; reprovada, volta
          ao supervisor com o motivo.
        </p>
      </header>

      {queue.status === "ok" ? (
        <>
          {/* A competência dos links é a que a API usou: sem `ano`/`mes` na
              URL, é a corrente que o banco calculou. */}
          <ApprovalFiltersBar
            filters={{
              ...filters,
              year: queue.queue.ano,
              month: queue.queue.mes,
            }}
            period={{
              start: queue.queue.period_start,
              end: queue.queue.period_end,
            }}
            units={screen.units}
            rows={queue.queue.rows}
          />
          <ApprovalQueue
            key={JSON.stringify(filters)}
            rows={queue.queue.rows}
          />
        </>
      ) : (
        <Card className="p-6">
          {queue.status === "forbidden" ? (
            <EmptyState
              icon={ShieldOff}
              tone="neutral"
              title="Sem acesso à aprovação de justificativas"
              description="A revisão de justificativas é do RH e do owner, e a API não reconheceu o seu papel para isso. Se deveria ter acesso, fale com o administrador do cliente."
            />
          ) : queue.status === "invalid" ? (
            <EmptyState
              icon={FilterX}
              tone="neutral"
              title="Recorte inválido"
              description="A API não aceitou o recorte deste link — uma data ou um filtro que não existe. Nenhuma justificativa foi alterada."
            >
              <Link
                href={approvalHref({
                  ...filters,
                  unitId: null,
                  employeeId: null,
                  from: null,
                  to: null,
                })}
                className="text-brand-strong text-sm font-bold"
              >
                Limpar recorte
              </Link>
            </EmptyState>
          ) : (
            <EmptyState
              icon={TriangleAlert}
              tone="alert"
              title="A fila de aprovação não pôde ser lida"
              description="A fila vem da API do painel, e ela não respondeu agora. Nenhuma justificativa foi alterada — recarregue a página para tentar de novo."
            />
          )}
        </Card>
      )}
    </div>
  );
}
