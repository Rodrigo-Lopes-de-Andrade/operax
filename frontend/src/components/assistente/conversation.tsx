"use client";

import { Ban, MessageSquareText, Send, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Card } from "@/components/ui/kpi-card";
import { Spinner } from "@/components/ui/spinner";
import { ApiError } from "@/lib/api";
import {
  askAssistant,
  type DoneEvent,
  type MetricEvent,
} from "@/lib/assistente/stream";

/**
 * A conversa. Um turno é uma pergunta e o que voltou dela — e "o que voltou"
 * tem quatro formas, não uma: a métrica que rodou, o texto, uma recusa ou uma
 * falha.
 *
 * A métrica aparece **acima** do texto e sempre, mesmo quando a resposta é uma
 * frase curta. É ela que deixa a pessoa conferir o recorte: um número de agosto
 * quando ela pensava em julho é indistinguível de um número certo até que o
 * período esteja escrito na tela. O que se mostra ali é o filtro que de fato
 * rodou — o backend manda os descartados à parte, e eles aparecem dizendo que
 * não filtraram.
 *
 * A recusa não é um erro e não usa vermelho: vermelho é falha, e a regra vale
 * na tela inteira do produto. Recusa é resposta.
 */

type Turn = {
  id: string;
  question: string;
  metric: MetricEvent | null;
  text: string;
  refusal: { codigo: string; motivo: string } | null;
  failure: string | null;
  done: DoneEvent | null;
};

const SUGESTOES = [
  "Quantos desvios tivemos este mês?",
  "Qual unidade teve mais desvios nos últimos 30 dias?",
  "Quais colaboradores repetiram desvio nesta semana?",
];

function novoTurno(question: string): Turn {
  return {
    id: crypto.randomUUID(),
    question,
    metric: null,
    text: "",
    refusal: null,
    failure: null,
    done: null,
  };
}

export function Conversation() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const fim = useRef<HTMLDivElement>(null);
  const campo = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fim.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  async function perguntar(question: string) {
    const pergunta = question.trim();

    if (!pergunta || streaming) {
      return;
    }

    const turn = novoTurno(pergunta);

    setDraft("");
    setStreaming(true);
    setTurns((anteriores) => [...anteriores, turn]);

    const atualizar = (mudanca: Partial<Turn>) =>
      setTurns((anteriores) =>
        anteriores.map((item) =>
          item.id === turn.id ? { ...item, ...mudanca } : item,
        ),
      );

    try {
      await askAssistant(pergunta, {
        onEvent: (event) => {
          if (event.type === "token") {
            setTurns((anteriores) =>
              anteriores.map((item) =>
                item.id === turn.id
                  ? { ...item, text: item.text + event.content }
                  : item,
              ),
            );
          } else if (event.type === "metrica") {
            atualizar({ metric: event });
          } else if (event.type === "recusa") {
            atualizar({
              refusal: { codigo: event.codigo, motivo: event.motivo },
            });
          } else if (event.type === "error") {
            atualizar({ failure: event.message });
          } else {
            atualizar({ done: event });
          }
        },
      });
    } catch (error) {
      // Erro antes do primeiro byte: 401, 403, 429 ou 400. O `detail` do
      // FastAPI já é a frase em pt-BR que a pessoa precisa ler — e o 429 diz
      // quantos segundos esperar.
      atualizar({
        failure:
          error instanceof ApiError && error.detail
            ? error.detail
            : "Não consegui falar com o assistente agora. Tente novamente.",
      });
    } finally {
      setStreaming(false);
      campo.current?.focus();
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {turns.length === 0 ? (
        <Card className="p-6">
          <EmptyState
            icon={MessageSquareText}
            title="Pergunte sobre jornada e desvios"
            description="O assistente responde a partir das métricas do painel — ele não estima e não inventa número. Quando a pergunta não couber em nenhuma métrica, ele diz isso."
          >
            <div className="flex flex-wrap justify-center gap-2 pt-1">
              {SUGESTOES.map((sugestao) => (
                <button
                  key={sugestao}
                  type="button"
                  onClick={() => void perguntar(sugestao)}
                  className="border-line-subtle text-ink-muted hover:border-brand hover:text-ink rounded-full border px-3 py-1.5 text-xs font-medium transition"
                >
                  {sugestao}
                </button>
              ))}
            </div>
          </EmptyState>
        </Card>
      ) : (
        <ol className="flex flex-col gap-4">
          {turns.map((turn) => (
            <li key={turn.id} className="flex flex-col gap-2">
              <p className="bg-muted text-ink ml-auto max-w-[80%] rounded-[14px] px-4 py-2 text-sm font-medium">
                {turn.question}
              </p>
              <Card className="max-w-[90%] p-4">
                <TurnAnswer turn={turn} streaming={streaming} />
              </Card>
            </li>
          ))}
        </ol>
      )}

      <div ref={fim} />

      <form
        className="flex items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void perguntar(draft);
        }}
      >
        <label htmlFor="pergunta" className="sr-only">
          Sua pergunta
        </label>
        <textarea
          id="pergunta"
          ref={campo}
          rows={1}
          value={draft}
          maxLength={1000}
          disabled={streaming}
          placeholder="Quantos desvios tivemos esta semana?"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            // Enter envia, Shift+Enter quebra linha: é uma conversa, não um
            // formulário.
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void perguntar(draft);
            }
          }}
          className="bg-control border-control-line text-ink placeholder:text-ink-faint min-h-10 flex-1 resize-none rounded-[10px] border px-3 py-2 text-base outline-none focus-visible:border-transparent disabled:opacity-60"
        />
        <Button type="submit" disabled={streaming || draft.trim().length === 0}>
          {streaming ? <Spinner /> : <Send aria-hidden className="size-4" />}
          {streaming ? "Consultando…" : "Perguntar"}
        </Button>
      </form>
    </div>
  );
}

function TurnAnswer({ turn, streaming }: { turn: Turn; streaming: boolean }) {
  const esperando = !turn.text && !turn.refusal && !turn.failure;

  return (
    <div className="flex flex-col gap-3">
      {turn.metric ? <MetricChip metric={turn.metric} /> : null}

      {turn.refusal ? (
        <div className="bg-alert-bg text-alert flex gap-2 rounded-[10px] px-3 py-2">
          <Ban aria-hidden className="mt-0.5 size-4 shrink-0" />
          <p className="text-sm font-medium">{turn.refusal.motivo}</p>
        </div>
      ) : null}

      {turn.failure ? <Alert>{turn.failure}</Alert> : null}

      {turn.text ? (
        <p
          aria-live="polite"
          className="text-ink text-sm leading-relaxed whitespace-pre-wrap"
        >
          {turn.text}
        </p>
      ) : null}

      {esperando && streaming ? (
        <p className="text-ink-faint flex items-center gap-2 text-sm">
          <Spinner />
          Consultando o painel…
        </p>
      ) : null}

      {turn.done ? <Cost done={turn.done} /> : null}
    </div>
  );
}

/**
 * O recorte, em português. `parametros` traz só o que filtrou; `ignorados` traz
 * o que a métrica não filtra — e ele é dito, porque um filtro pedido e não
 * aplicado é a diferença entre o número certo e a frase errada.
 */
function MetricChip({ metric }: { metric: MetricEvent }) {
  const filtros = Object.entries(metric.parametros);

  return (
    <div className="border-line-subtle flex flex-wrap items-center gap-2 border-b pb-3">
      <Badge tone="brand">{metric.titulo}</Badge>
      {filtros.map(([nome, valor]) => (
        <span key={nome} className="text-ink-muted text-xs">
          {LABELS[nome] ?? nome}:{" "}
          <strong className="font-semibold">{valor}</strong>
        </span>
      ))}
      {metric.ignorados.length > 0 ? (
        <span className="text-alert flex items-center gap-1 text-xs">
          <TriangleAlert aria-hidden className="size-3.5" />
          sem filtro de {metric.ignorados.map((n) => LABELS[n] ?? n).join(", ")}
        </span>
      ) : null}
    </div>
  );
}

const LABELS: Record<string, string> = {
  start_date: "de",
  end_date: "até",
  unit: "unidade",
  company: "empresa",
  employee: "colaborador",
  type: "tipo",
  year: "ano",
  month: "mês",
  days_ahead: "dias à frente",
};

/**
 * Custo de LLM é variável e sai da sustentação mensal — e quem pergunta é quem
 * gasta. Deixar isso visível é critério de aceite do sprint, não enfeite.
 */
function Cost({ done }: { done: DoneEvent }) {
  return (
    <p className="text-ink-faint text-2xs">
      {done.modelo} · {done.tokens_entrada + done.tokens_saida} tokens ·{" "}
      {(done.latencia_ms / 1000).toFixed(1)}s
    </p>
  );
}
