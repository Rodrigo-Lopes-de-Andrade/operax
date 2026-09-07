import { Card, CardHeader, KpiCard } from "@/components/ui/kpi-card";
import {
  formatCents,
  formatCurrency,
  formatPercent,
  share,
  toCents,
} from "@/lib/dp/format";
import type { DpPanelKpis } from "@/lib/dp/queries";
import { formatNumber } from "@/lib/ponto/format";

/**
 * Os nove KPIs de topo do painel de DP (`ANEXO` §2a), na ordem em que a tela do
 * legado os declara — é contra ela que o número é conferido no dia da virada.
 *
 * ⛔ NÃO HÁ NOME DE PESSOA AQUI, E NEM PODE HAVER
 * Todo campo de `GET /dp/painel` é número. O cartão de sinistro é **contagem**:
 * o painel do sistema atual nomeia quem tem parcela em aberto logo na abertura,
 * e no OperaX isso é conteúdo individual de domínio sensível dentro de um
 * agregado. Quem precisa do nome abre a ficha, onde o domínio é revalidado.
 *
 * ⚠️ "RETENÇÃO" É O RÓTULO DO LEGADO, E ELE NÃO DESCREVE A CONTA
 * A fórmula é `ativos ÷ total no filtro`, que muda de significado conforme o
 * filtro e vira 100% em qualquer recorte só de ativos. Ela está aqui transcrita
 * porque é contra o legado que o gate compara; consertá-la é decisão de produto,
 * pendente. O que a tela pode fazer sem esperar por ela é não deixar o gestor
 * ler "retenção de 100%" achando que ninguém pediu demissão — e é isso que a
 * nota do cartão faz.
 */
export function PanelKpis({ kpis }: { kpis: DpPanelKpis }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <KpiCard
          eyebrow="Total analisado"
          value={formatNumber(kpis.total_analyzed)}
          note="Vínculos no recorte, ativos e desligados. É a base de que os outros oito saem."
        />

        <KpiCard
          eyebrow="Efetivo ativo"
          value={formatNumber(kpis.active_headcount)}
          note="Quem tem vínculo aberto. Afastado e de férias continuam contando — custam folha."
        />

        <KpiCard
          eyebrow="Desligamentos"
          value={formatNumber(kpis.terminations)}
          note="Vínculos encerrados dentro do recorte, do histórico inteiro que o filtro alcança."
        />

        <KpiCard
          eyebrow="Retenção"
          value={formatPercent(kpis.retention)}
          note="Ativos ÷ total no filtro, como no sistema atual. Não é retenção por período: um recorte só de ativos dá 100% sem ninguém ter ficado."
        />

        <KpiCard
          eyebrow="Folha salarial base"
          value={formatCurrency(kpis.base_payroll)}
          note="Salário mais as verbas marcadas como parte da base no catálogo. O vale refeição fica de fora."
        />

        <KpiCard
          eyebrow="Média (folha base)"
          value={formatCurrency(kpis.base_payroll_average)}
          note={
            kpis.without_salary === 0
              ? "Folha base ÷ efetivo ativo. Todos os ativos do recorte têm faixa salarial vigente."
              : `Folha base ÷ efetivo ativo. ${formatNumber(kpis.without_salary)} ${
                  kpis.without_salary === 1
                    ? "ativo não tem faixa salarial vigente e entra no divisor sem entrar na soma"
                    : "ativos não têm faixa salarial vigente e entram no divisor sem entrar na soma"
                }.`
          }
        />

        <KpiCard
          eyebrow="Vale refeição (VR)"
          value={formatCurrency(kpis.meal_voucher)}
          note="Soma mensal dos ativos. Fora da folha base — é benefício, não remuneração."
        />

        <KpiCard
          eyebrow="Ajuda de custo"
          value={formatCurrency(kpis.cost_allowance)}
          note="Soma mensal dos ativos. Dentro da folha base."
        />

        <KpiCard
          eyebrow="Cargo de confiança + periculosidade"
          value={formatCurrency(kpis.trust_and_hazard)}
          note="Soma mensal dos ativos. Dentro da folha base."
        />
      </div>

      <Card>
        <CardHeader
          title="Unidades com sinistro ativo"
          note="Unidades com pelo menos uma parcela de acordo em aberto."
        />
        <div className="flex flex-wrap items-baseline gap-4 px-5 py-4">
          <p className="text-ink text-3xl leading-none font-extrabold tabular-nums">
            {formatNumber(kpis.units_with_open_installment)}
          </p>
          <p className="text-ink-muted max-w-2xl text-sm text-pretty">
            Só a contagem. O sistema atual lista aqui o nome de quem tem parcela
            em aberto; aqui não — nome com valor em aberto é dado individual de
            remuneração, e ele sai na ficha da pessoa, uma por vez.
          </p>
        </div>
      </Card>
    </div>
  );
}

/**
 * Raio-X de benefícios (`ANEXO` §2d) — o que a folha base tem dentro.
 *
 * ⚠️ A PRIMEIRA LINHA É UM RESTO, E O RÓTULO DIZ ISSO
 * `GET /dp/painel` manda a folha base fechada e três verbas nomeadas; o que
 * sobra ao subtrair as duas que compõem a base é salário **mais qualquer outra
 * verba que o tenant tenha marcado como parte da base**, e esse conjunto é
 * coluna editável (`benefit_type.composes_base`), não constante. Chamar a linha
 * de "salário" acertaria na semente e passaria a mentir calado no dia em que o
 * cliente criasse a nona verba. Chamando-a do que ela é, a conta fecha em
 * qualquer configuração.
 *
 * ⛔ SEIS DOS DEZ ITENS DO RAIO-X DO LEGADO NÃO TÊM FONTE, e o cartão diz quais
 * em vez de mostrar zero: zero é um número, e um número errado é pior que uma
 * ausência declarada.
 */
export function BenefitBreakdown({ kpis }: { kpis: DpPanelKpis }) {
  const base = toCents(kpis.base_payroll);
  const allowance = toCents(kpis.cost_allowance);
  const trust = toCents(kpis.trust_and_hazard);
  const remainder = base - allowance - trust;

  const rows = [
    { label: "Salário e demais verbas da base", cents: remainder },
    { label: "Ajuda de custo", cents: allowance },
    { label: "Cargo de confiança + periculosidade", cents: trust },
  ];

  return (
    <Card>
      <CardHeader
        eyebrow="Folha ativa"
        title="Raio-X de benefícios"
        note="Como a folha salarial base se divide, e o que fica fora dela."
      />
      <div className="flex flex-col gap-3 px-5 py-4">
        <dl className="flex flex-col gap-2">
          {rows.map((row) => (
            <div
              key={row.label}
              className="flex flex-wrap items-baseline justify-between gap-2"
            >
              <dt className="text-ink-body text-sm">{row.label}</dt>
              <dd className="text-ink text-sm font-bold tabular-nums">
                {formatCents(row.cents)}
                <span className="text-ink-faint ml-2 font-semibold">
                  {shareLabel(row.cents, base)}
                </span>
              </dd>
            </div>
          ))}

          <div className="border-line-subtle flex flex-wrap items-baseline justify-between gap-2 border-t pt-2">
            <dt className="text-ink text-sm font-bold">Folha salarial base</dt>
            <dd className="text-ink text-sm font-extrabold tabular-nums">
              {formatCents(base)}
            </dd>
          </div>

          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <dt className="text-ink-body text-sm">
              Vale refeição (VR){" "}
              <span className="text-ink-faint">— fora da base</span>
            </dt>
            <dd className="text-ink-body text-sm font-bold tabular-nums">
              {formatCurrency(kpis.meal_voucher)}
            </dd>
          </div>
        </dl>

        <p className="text-ink-muted max-w-3xl text-xs text-pretty">
          O raio-X do sistema atual traz mais seis linhas — usuários de vale
          transporte, plano odontológico, plano de saúde com custo aproximado,
          total de dependentes, vínculos em saúde e VR/cesta consolidados.
          Nenhum deles vem no painel hoje, e por isso não aparecem aqui nem como
          zero.
        </p>
      </div>
    </Card>
  );
}

function shareLabel(part: number, whole: number): string {
  const percent = share(part, whole);

  return percent === null ? "" : `${percent}%`;
}
