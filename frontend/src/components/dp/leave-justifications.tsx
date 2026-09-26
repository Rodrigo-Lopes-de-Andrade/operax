"use client";

import { CalendarOff } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge, Chip } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Table, type Column } from "@/components/ui/table";
import { ApiError, requestApiAsUser } from "@/lib/api";
import {
  formatDate,
  formatDayInTenantZone,
  LEAVE_CATEGORIES,
  LEAVE_CATEGORY_LABEL,
} from "@/lib/dp/format";
import type {
  LeaveJustificationList,
  LeaveJustificationRow,
} from "@/lib/dp/queries";

const COLUMNS: Column[] = [
  { key: "justificativa", label: "Justificativa", mono: true, width: "20%" },
  {
    key: "afastamentos",
    label: "Afastamentos",
    numeric: true,
    align: "right",
    width: "10%",
  },
  { key: "periodo", label: "Período", width: "16%" },
  { key: "categoria", label: "Categoria", width: "16%" },
  { key: "nota", label: "Nota", width: "18%" },
  { key: "estado", label: "Estado", width: "12%" },
  { key: "acao", label: "", align: "right", width: "18%" },
];

/** O id do aviso da nota, apontado por `aria-describedby` de cada campo. */
const AVISO_NOTA = "nota-permanente";

/**
 * Curadoria de justificativa de afastamento — a porta que o apurador nomeava.
 *
 * ⛔ SÃO DOIS ATOS, E A TELA NÃO OS JUNTA
 * Classificar grava a categoria e deixa a linha **provisória**; validar é o
 * outro clique, e é ele que libera a apuração. Provisória trava a competência
 * igual à que ninguém tocou — então a tela mostra os dois estados com nomes
 * diferentes e nunca chama uma de "pronta".
 *
 * ⛔ SALVAR DERRUBA O AVAL, SEMPRE — INCLUSIVE SEM TROCAR A CATEGORIA
 * O `on conflict do update` do backend zera `validated_at` em toda gravação. Por
 * isso "Salvar classificação" fica **desabilitado quando nada mudou**: um clique
 * inócuo numa linha validada faria a apuração voltar a recusar sem que ninguém
 * tivesse mudado nada. E quando há o que salvar numa linha avalizada, a tela diz
 * o que o clique custa antes de ele acontecer.
 *
 * ⛔ COM EDIÇÃO NÃO SALVA, "VALIDAR" SAI DA TELA
 * `POST /validar` leva só a chave: quem prende a categoria é o backend, com a
 * que **ele** leu. Deixar o botão ao lado de um `select` mexido seria oferecer
 * um aval sobre a categoria que ninguém gravou.
 *
 * ⚠️ E ISSO NÃO FECHA O BURACO INTEIRO, porque o contrato não deixa: numa fila
 * lida há dez minutos, validar carimba a categoria que estiver no banco AGORA —
 * não a que está na tela. A tela recarrega a fila depois de cada gravação e
 * depois de toda recusa de aval, e é o máximo que ela alcança sem um
 * `expected_category` no corpo. Reportado.
 *
 * ⚠️ NÃO HÁ `can_write`: as três rotas exigem o mesmo eixo (`util.is_admin`),
 * que é a porta da página. Quem lê esta fila é exatamente quem a escreve.
 */
export function LeaveJustifications({
  screen,
}: {
  screen: LeaveJustificationList;
}) {
  const router = useRouter();
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const [written, setWritten] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function categoryFor(row: LeaveJustificationRow): string {
    return chosen[row.justification] ?? row.category ?? "";
  }

  // A nota do campo nasce **da linha**, e não vazia: reclassificar sem reenviar
  // `notes` apaga a nota anterior (o backend grava o que chega, e a trilha só
  // guarda o "antes"). Então a tela manda sempre a linha inteira.
  function noteFor(row: LeaveJustificationRow): string {
    return written[row.justification] ?? row.notes ?? "";
  }

  function dirty(row: LeaveJustificationRow): boolean {
    return (
      categoryFor(row) !== (row.category ?? "") ||
      noteFor(row) !== (row.notes ?? "")
    );
  }

  function forget(justification: string) {
    setChosen((atual) => {
      const proximo = { ...atual };
      delete proximo[justification];
      return proximo;
    });
    setWritten((atual) => {
      const proximo = { ...atual };
      delete proximo[justification];
      return proximo;
    });
  }

  async function classify(row: LeaveJustificationRow) {
    const category = categoryFor(row);

    if (!category) {
      setError(
        `Escolha a categoria de «${row.justification}» antes de salvar.`,
      );
      return;
    }

    setBusy(row.justification);
    setError(null);

    try {
      await requestApiAsUser("/dp/justificativas/classificar", {
        method: "POST",
        // A chave vai no CORPO, e não na URL: `JustificativaNome` é texto livre
        // do Secullum do cliente, e uma barra na string faria a rota devolver
        // 404 sobre uma justificativa que está na tela.
        body: {
          justification: row.justification,
          category,
          notes: noteFor(row).trim() || null,
        },
      });
      forget(row.justification);
      router.refresh();
    } catch (caught) {
      setError(
        mensagem(
          caught,
          "Não consegui gravar a classificação. Nada foi alterado.",
        ),
      );
    } finally {
      setBusy(null);
    }
  }

  async function validate(row: LeaveJustificationRow) {
    setBusy(row.justification);
    setError(null);

    try {
      await requestApiAsUser("/dp/justificativas/validar", {
        method: "POST",
        body: { justification: row.justification },
      });
      router.refresh();
    } catch (caught) {
      setError(
        mensagem(caught, "Não consegui registrar o aval. Nada foi alterado."),
      );

      // 422 é a recusa nomeada do backend, e uma delas é "a classificação mudou
      // enquanto você conferia". A frase manda recarregar a fila — então a tela
      // recarrega, em vez de pedir à pessoa que faça o que ela já pediu.
      if (caught instanceof ApiError && caught.status === 422) {
        router.refresh();
      }
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Queue screen={screen} />

      {error ? <Alert>{error}</Alert> : null}

      {screen.rows.length === 0 ? (
        <Card className="p-6">
          <EmptyState
            icon={CalendarOff}
            tone="neutral"
            title="Nenhuma justificativa para classificar"
            description="A fila nasce dos afastamentos que o Secullum manda. Enquanto não houver afastamento no espelho, não há string para classificar — o que não quer dizer que a apuração esteja liberada: o número de cima é quem diz."
          />
        </Card>
      ) : (
        <Card>
          <CardHeader
            title="Justificativas do espelho"
            note={`${screen.rows.length} ${screen.rows.length === 1 ? "string" : "strings"} distintas, como a origem as escreve`}
          />
          <p
            id={AVISO_NOTA}
            className="border-line-subtle text-ink-muted border-b px-5 py-3 text-xs text-pretty"
          >
            ⛔ A nota é permanente e é sobre a <strong>string</strong>, nunca
            sobre o caso de alguém: ela é copiada para a trilha de auditoria,
            que não tem correção nem apagamento, e é lida por todo
            administrador. Escreva por que a categoria é essa — “mesma coisa que
            ATESTED, truncado pela origem” — e nunca diagnóstico, CID ou
            restrição.
          </p>
          <Table
            columns={COLUMNS}
            caption="Justificativas de afastamento e a categoria de cada uma"
            rows={screen.rows.map((row) => {
              const editando = dirty(row);
              const gravando = busy === row.justification;

              return {
                id: row.justification,
                cells: {
                  justificativa: (
                    <span className="flex flex-col gap-1">
                      {/* A string crua, como o banco a guarda. Consertar o
                          truncamento da origem aqui inventaria uma chave que o
                          apurador não procura. */}
                      <span>{row.justification}</span>
                      {row.in_mirror ? null : <Chip>fora do espelho</Chip>}
                    </span>
                  ),
                  afastamentos:
                    row.occurrences === 0 ? (
                      <span className="text-ink-faint">—</span>
                    ) : (
                      row.occurrences
                    ),
                  periodo:
                    row.occurrences === 0 ? (
                      <span className="text-ink-faint">—</span>
                    ) : (
                      `${formatDate(row.first_leave)} a ${formatDate(row.last_leave)}`
                    ),
                  categoria: (
                    <select
                      aria-label={`Categoria de ${row.justification}`}
                      value={categoryFor(row)}
                      onChange={(event) =>
                        setChosen((atual) => ({
                          ...atual,
                          [row.justification]: event.target.value,
                        }))
                      }
                      disabled={gravando}
                      className="border-control-line bg-control text-ink h-9 w-full rounded-[10px] border px-2 text-sm"
                    >
                      <option value="">— sem categoria —</option>
                      {LEAVE_CATEGORIES.map((option) => (
                        <option key={option} value={option}>
                          {LEAVE_CATEGORY_LABEL[option]}
                        </option>
                      ))}
                    </select>
                  ),
                  nota: (
                    <input
                      type="text"
                      aria-label={`Nota de ${row.justification}`}
                      aria-describedby={AVISO_NOTA}
                      maxLength={500}
                      value={noteFor(row)}
                      onChange={(event) =>
                        setWritten((atual) => ({
                          ...atual,
                          [row.justification]: event.target.value,
                        }))
                      }
                      disabled={gravando}
                      placeholder="por que esta categoria"
                      className="border-control-line bg-control text-ink placeholder:text-ink-faint h-9 w-full rounded-[10px] border px-2 text-sm"
                    />
                  ),
                  estado: <Curation row={row} />,
                  acao: (
                    <span className="flex flex-col items-end gap-1">
                      <span className="flex items-center justify-end gap-3">
                        <button
                          type="button"
                          onClick={() => void classify(row)}
                          disabled={gravando || !editando}
                          className="text-brand-strong text-xs font-bold underline disabled:opacity-60"
                        >
                          {gravando ? "Gravando…" : "Salvar classificação"}
                        </button>
                        {row.category && !row.validated && !editando ? (
                          <button
                            type="button"
                            onClick={() => void validate(row)}
                            disabled={gravando}
                            className="text-brand-strong text-xs font-bold underline disabled:opacity-60"
                          >
                            Validar
                          </button>
                        ) : null}
                      </span>
                      {row.validated && editando ? (
                        <span className="text-alert text-xs font-semibold">
                          salvar derruba o aval
                        </span>
                      ) : null}
                      {row.category && !row.validated && editando ? (
                        <span className="text-ink-faint text-xs">
                          salve antes de validar
                        </span>
                      ) : null}
                    </span>
                  ),
                },
              };
            })}
          />
        </Card>
      )}
    </div>
  );
}

/**
 * Os DOIS números, e eles ficam lado a lado porque um sozinho mente.
 *
 * `pending` é a fila curável; `without_justification` são os afastamentos que
 * chegaram sem nome nenhum, que travam a competência do mesmo jeito e **não têm
 * o que classificar** — a correção é na origem. Sem o segundo, "sem pendência"
 * seria dito sobre uma apuração que continua recusando.
 *
 * Os dois vêm da API e não são recalculados aqui: `pending` sai da mesma função
 * que o apurador consulta, e "sem pendência" tem de ser o backend afirmando.
 */
function Queue({ screen }: { screen: LeaveJustificationList }) {
  return (
    <Card className="grid gap-5 p-5 sm:grid-cols-2">
      <div>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Sem aval
        </p>
        <p
          role="status"
          className="text-ink text-lg font-extrabold tabular-nums"
        >
          {screen.pending === 0
            ? "Sem pendência"
            : `${screen.pending} ${screen.pending === 1 ? "justificativa" : "justificativas"} sem aval`}
        </p>
        <p className="text-ink-muted text-xs text-pretty">
          {screen.pending === 0
            ? "Toda justificativa do espelho está classificada e avalizada. A apuração deixa de recusar por este motivo."
            : "A apuração da competência recusa enquanto houver uma sem aval — classificada provisória trava igual à que ninguém tocou."}
        </p>
      </div>

      <div>
        <p className="text-2xs text-ink-faint font-bold tracking-[0.08em] uppercase">
          Sem justificativa na origem
        </p>
        <p
          role="status"
          className="text-ink text-lg font-extrabold tabular-nums"
        >
          {screen.without_justification === 0
            ? "Nenhum afastamento"
            : `${screen.without_justification} ${screen.without_justification === 1 ? "afastamento" : "afastamentos"} sem nome`}
        </p>
        <p className="text-ink-muted text-xs text-pretty">
          {screen.without_justification === 0
            ? "Todo afastamento do espelho chegou com uma justificativa escrita."
            : "Chegaram do Secullum sem justificativa nenhuma. Não há o que classificar aqui, e a apuração continua recusando: a correção é na origem."}
        </p>
      </div>
    </Card>
  );
}

/**
 * O que a curadoria já disse da string — e "proposta, sem aval" é um estado
 * próprio, não meio-caminho: ela não entra em cálculo de dinheiro.
 */
function Curation({ row }: { row: LeaveJustificationRow }) {
  if (row.validated) {
    return (
      <span className="flex flex-col gap-1">
        <Badge tone="good" dot>
          Validada
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

  return (
    <Badge tone="alert" dot>
      Pendente
    </Badge>
  );
}

function mensagem(caught: unknown, padrao: string): string {
  return caught instanceof ApiError && caught.detail ? caught.detail : padrao;
}
