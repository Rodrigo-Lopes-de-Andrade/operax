import { TAB_LABEL } from "@/lib/rh/labels";
import type { HrEmployeeDetail } from "@/lib/rh/queries";
import type { Tab } from "@/lib/rh/url";

export type DomainTab = { value: Tab; label: string; count?: number };

/**
 * As abas que existem para quem está olhando.
 *
 * A regra inteira da tela mora aqui, e é uma só: bloco que chegou `null` — e não
 * `[]` — não vira aba. `null` é "você não alcança este domínio" e `[]` é "não há
 * nada registrado"; a primeira não pode aparecer na interface de forma alguma, a
 * segunda aparece como estado vazio.
 *
 * Uma aba desabilitada com o rótulo "Remuneração" informa que existe
 * remuneração, que é exatamente o que o domínio sensível existe para não
 * informar. Por isso a função devolve a lista e não uma lista com flags: o que
 * não está aqui não chega ao DOM.
 *
 * É função pura de propósito — é a asserção mais importante deste sprint, e ela
 * precisa ser verificável sem subir navegador.
 */
export function availableTabs(detail: HrEmployeeDetail): DomainTab[] {
  const tabs: DomainTab[] = [
    { value: "cadastro", label: TAB_LABEL.cadastro },
    {
      value: "posicao",
      label: TAB_LABEL.posicao,
      count: detail.positions.length,
    },
  ];

  if (detail.pii !== null) {
    tabs.push({
      value: "pessoais",
      label: TAB_LABEL.pessoais,
      count: detail.documents?.length ?? 0,
    });
  }

  if (detail.exams !== null) {
    tabs.push({
      value: "saude",
      label: TAB_LABEL.saude,
      count: detail.exams.length,
    });
  }

  if (detail.compensation !== null) {
    tabs.push({
      value: "remuneracao",
      label: TAB_LABEL.remuneracao,
      count: detail.compensation.length,
    });
  }

  tabs.push({
    value: "afastamentos",
    label: TAB_LABEL.afastamentos,
    count: detail.leaves.length,
  });
  tabs.push({
    value: "movimentacoes",
    label: TAB_LABEL.movimentacoes,
    count: detail.movements.length,
  });

  if (detail.agreements !== null) {
    tabs.push({
      value: "acordos",
      label: TAB_LABEL.acordos,
      count: detail.agreements.length,
    });
  }

  return tabs;
}
