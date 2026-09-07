import { BellRing } from "lucide-react";

import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader, KpiCard } from "@/components/ui/kpi-card";
import type { AlertsResult } from "@/lib/dp/queries";
import { formatNumber } from "@/lib/ponto/format";

/**
 * O que cada contador é, palavra por palavra.
 *
 * `unit` não é enfeite de texto: seis dos oito contam **pessoa** e dois contam
 * **documento**, e a diferença está no `comment on function` de
 * `public.fn_dp_alerts()`. Com CNH — um documento por pessoa — as duas leituras
 * dão o mesmo número, que é justamente por que a tela do sistema atual não
 * resolve a dúvida e por que ela chegou aqui aberta. O rótulo segue o dado.
 */
type AlertCard = {
  code: string;
  eyebrow: string;
  unit: (total: number) => string;
  note: string;
};

const CARDS: AlertCard[] = [
  {
    code: "birthday_month",
    eyebrow: "Aniversariantes do mês",
    unit: people,
    note: "Aniversário no mês corrente. Quem já saiu não conta.",
  },
  {
    code: "probation",
    eyebrow: "Em experiência",
    unit: people,
    note: "Até 60 dias de casa — as duas metades do contrato, a de 30 e a de 60 dias, num número só.",
  },
  {
    code: "document_expired",
    eyebrow: "Documentos vencidos",
    unit: documents,
    // ⛔ "CNH" NÃO ENTRA NESTE RÓTULO, e não é descuido de redação.
    // O sistema atual chama os dois cartões de documento de "CNH" porque CNH é
    // o que ele tem. Aqui o contador varre todo tipo com validade, e o tipo é
    // texto livre por tenant (`app.document_type` não tem código) — não há como
    // recortar por CNH sem pôr regra de negócio numa string, que erraria calado
    // no tenant que escrevesse "Carteira de Habilitação".
    note: "Contagem de documentos, não de pessoas: quem tem dois vencidos aparece duas vezes. Vale para todo tipo com validade, não só CNH.",
  },
  {
    code: "document_expiring",
    eyebrow: "Documentos a vencer",
    unit: documents,
    note: "Contagem de documentos. A janela é a cadastrada em cada tipo, e não 90 dias fixos para todos.",
  },
  {
    code: "exam_due",
    eyebrow: "ASO vencido ou a vencer",
    unit: people,
    note: "Só o exame mais recente de cada pessoa. Vencidos e a vencer no mesmo número, como no sistema atual.",
  },
  {
    code: "vacation_upcoming",
    eyebrow: "Férias no próximo mês",
    unit: people,
    note: "Períodos que começam no mês seguinte ao corrente.",
  },
  {
    code: "vacation_today",
    eyebrow: "Em férias hoje",
    unit: people,
    note: "Períodos em curso na data de hoje.",
  },
  {
    code: "vacation_limit",
    // ⚠️ O PRAZO VENCIDO ENTRA NESTE NÚMERO, DE PROPÓSITO
    // É onde o empregador passa a dever em dobro (CLT art. 137), e era o único
    // estado que o painel do legado não mostrava. Um rótulo "a vencer" faria o
    // gestor ler o número como um aviso com folga; ele é o contrário disso.
    eyebrow: "Prazo de férias — vencido ou a vencer",
    unit: people,
    note: "Inclui quem já passou do prazo, e não só quem está perto: passado o limite, o período custa em dobro. Janela de 90 dias à frente.",
  },
];

function people(total: number): string {
  return total === 1 ? "pessoa" : "pessoas";
}

function documents(total: number): string {
  return total === 1 ? "documento" : "documentos";
}

/**
 * O painel de alertas — **caminho 1** do contrato, direto no Supabase.
 *
 * `public.fn_dp_alerts()` devolve `(code, total)` e nada mais, com o recorte de
 * tenant e de escopo dentro dela: um supervisor de unidade recebe os números da
 * unidade dele sem que esta tela filtre coisa alguma, e sem mandar `tenant_id`.
 *
 * ⛔ OS OITO CARTÕES NÃO LEVAM A LISTA NENHUMA, E ISSO É MEDIDO
 * O `ANEXO` §2c pede "8 contadores + 8 listas", e não existe rota para essas
 * listas — nenhuma das treze rotas de `/dp` devolve quem está com documento
 * vencido. Mandar o clique para a lista de Colaboradores filtrada por pendência
 * seria pior que não mandar: aquela lista conta **pessoa** onde estes contam
 * documento, usa outra janela e outro conjunto de status, e passa por RLS de
 * domínio — no banco de desenvolvimento o contador de ASO diz 18 e a lista
 * equivalente devolve 0 linhas para o mesmo usuário, porque contar não é ler.
 * Um número que leva a outro número é lido como defeito, e com razão.
 */
export function PanelAlerts({ alerts }: { alerts: AlertsResult }) {
  if (alerts.status === "unavailable") {
    return (
      <Card>
        <CardHeader
          eyebrow="Alertas"
          title="Painel de alertas"
          note="Os oito contadores do cadastro."
        />
        <div className="p-6">
          <EmptyState
            icon={BellRing}
            tone="alert"
            title="Os contadores não puderam ser lidos"
            description="Os oito alertas vêm direto do banco e a leitura falhou agora. Recarregue a página; nada do cadastro foi alterado."
          />
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        eyebrow="Alertas"
        title="Painel de alertas"
        note="Só a contagem: quem aparece em cada um sai na ficha da pessoa, e a lista por alerta ainda não existe no painel."
      />
      <div className="grid gap-4 p-5 sm:grid-cols-2 xl:grid-cols-4">
        {CARDS.map((card) => {
          const total = alerts.counts[card.code] ?? 0;

          return (
            <KpiCard
              key={card.code}
              eyebrow={card.eyebrow}
              value={
                <>
                  {formatNumber(total)}{" "}
                  <span className="text-ink-faint text-sm font-bold">
                    {card.unit(total)}
                  </span>
                </>
              }
              note={card.note}
            />
          );
        })}
      </div>
    </Card>
  );
}
