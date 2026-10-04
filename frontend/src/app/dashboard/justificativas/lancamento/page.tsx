import { FilterX, ShieldOff, TriangleAlert } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ApprovalFiltersBar } from "@/components/alcada/approval-filters";
import { PostingList } from "@/components/alcada/posting-list";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { loadPostingScreen } from "@/lib/alcada/queries";
import {
  LANCAMENTO_PATH,
  parseApprovalFilters,
  postingHref,
} from "@/lib/alcada/url";
import { pageTitle } from "@/lib/brand";
import { formatCompetencia } from "@/lib/dp/format";
import { loadIdentity, reviewsJustifications } from "@/lib/identity";
import type { RawSearchParams } from "@/lib/ponto/filters";

export const metadata: Metadata = {
  title: pageTitle("Lançamento no Secullum"),
};

/**
 * Lançamento no Secullum — a última ponta da alçada (P1.4).
 *
 * O RH aprova no painel e digita a decisão no Secullum; esta tela diz o que
 * ainda falta digitar e recebe a marca de "já lancei". Quem entra é quem
 * revisa (`reviewsJustifications`): `hr` e `owner`. Outro papel recebe 404, e
 * o 403 da API, se as duas listas divergirem, vira "sem acesso".
 *
 * O recorte é o da fila, na query string: a competência é a do FATO nas duas
 * telas (decisão do dono, 04/10/2026), e a janela vem da resposta.
 */
export default async function LancamentoNoSecullumPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const identity = await loadIdentity();

  if (!reviewsJustifications(identity?.role)) {
    notFound();
  }

  const filters = parseApprovalFilters(await searchParams);
  const screen = await loadPostingScreen(filters);
  const { list } = screen;

  return (
    <div className="flex flex-col gap-4">
      <header>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Operação
        </p>
        <h1 className="text-ink text-2xl font-extrabold">
          Lançamento no Secullum
        </h1>
        <p className="text-ink-muted mt-1 max-w-3xl text-sm text-pretty">
          As justificativas aprovadas
          {list.status === "ok"
            ? ` de ${formatCompetencia(list.queue.ano, list.queue.mes)}`
            : " da competência"}
          . O painel não escreve no Secullum: depois de digitar a decisão lá,
          marque aqui — é a marca que separa o aprovado do aprovado e lançado.
        </p>
      </header>

      {list.status === "ok" ? (
        <>
          <ApprovalFiltersBar
            path={LANCAMENTO_PATH}
            employeeGroupLabel="Com justificativa aprovada"
            filters={{
              ...filters,
              year: list.queue.ano,
              month: list.queue.mes,
            }}
            period={{
              start: list.queue.period_start,
              end: list.queue.period_end,
            }}
            units={screen.units}
            rows={list.queue.rows}
          />
          <PostingList
            key={JSON.stringify(filters)}
            rows={list.queue.rows}
            currentUserId={identity?.user_id ?? null}
          />
        </>
      ) : (
        <Card className="p-6">
          {list.status === "forbidden" ? (
            <EmptyState
              icon={ShieldOff}
              tone="neutral"
              title="Sem acesso ao lançamento no Secullum"
              description="Marcar o lançamento é do RH e do owner, e a API não reconheceu o seu papel para isso. Se deveria ter acesso, fale com o administrador do cliente."
            />
          ) : list.status === "invalid" ? (
            <EmptyState
              icon={FilterX}
              tone="neutral"
              title="Recorte inválido"
              description="A API não aceitou o recorte deste link — uma data ou um filtro que não existe. Nenhuma marca foi alterada."
            >
              <Link
                href={postingHref({
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
              title="A lista do lançamento não pôde ser lida"
              description="A lista vem da API do painel, e ela não respondeu agora. Isso não quer dizer que não há nada a lançar — recarregue a página para tentar de novo."
            />
          )}
        </Card>
      )}
    </div>
  );
}
