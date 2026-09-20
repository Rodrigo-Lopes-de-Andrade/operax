"use client";

import { FlaskConical, Send } from "lucide-react";
import { useRef, useState } from "react";

import {
  novoTurno,
  TurnAnswer,
  type Turn,
} from "@/components/assistente/conversation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardHeader } from "@/components/ui/kpi-card";
import { Spinner } from "@/components/ui/spinner";
import { ApiError } from "@/lib/api";
import { testAssistant } from "@/lib/assistente/config";
import type { AssistantEvent } from "@/lib/assistente/stream";

/**
 * A aba Teste: a mesma pergunta da conversa, contra a versão no ar ou contra o
 * rascunho, gravada como dry run — fora de toda média.
 *
 * ⛔ O TESTE LÊ DADO REAL, E A TELA DIZ (SPEC-AGENTE §5)
 * Não há sandbox, e não deveria haver: um assistente testado contra dado falso
 * é testado contra outro produto. A frase fixa no topo é o que impede alguém
 * de colar o resultado num canal errado achando que era exemplo.
 *
 * ⛔ NENHUM SELETOR DE PAPEL — NEM SELECT, NEM RADIO, NEM "VER COMO"
 * O teste roda sempre como quem clicou. "Como ficaria para outra pessoa" tem
 * uma resposta legítima — a aba Capacidades lista o que ela alcança — e uma
 * ilegítima: executar como ela, que é escalação de privilégio com nome de
 * recurso. A única defesa é não construir o caminho, e o teste de tela cobra
 * a ausência.
 *
 * Cada turno guarda com qual texto rodou (rascunho ou versão no ar) no momento
 * do clique, e mostra isso ao lado da resposta: a caixa pode mudar entre um
 * teste e o outro, e a resposta antiga não pode mudar de rótulo junto.
 */

/** Um turno de teste: o da conversa, mais o texto contra o qual ele rodou. */
type TestTurn = Turn & { useDraft: boolean };

/**
 * O painel é uma região nomeada de propósito: o teste de tela precisa afirmar
 * a **ausência** de seletor de papel dentro dele, e uma ausência afirmada na
 * tela inteira é uma ausência que a navegação em volta pode encher.
 */
const TITLE = "Testar o assistente";
const REAL_DATA = "O teste consulta dados reais, com as suas permissões.";
const DRY_RUN = "Teste — não entra nas médias.";
const NO_DRAFT = "Não há rascunho salvo: o teste usa a versão no ar.";
/**
 * Quando a configuração não pôde ser lida, "não há rascunho" seria uma
 * afirmação sobre o que esta tela não sabe — e o único estado que o
 * administrador lê. O comportamento é o mesmo (falha fechada: testa a versão
 * no ar); o que muda é parar de afirmar.
 */
const UNKNOWN_DRAFT =
  "Não foi possível saber se há rascunho: o teste usa a versão no ar.";
const FAILED = "Não consegui falar com o assistente agora. Tente novamente.";

function applyEvent(turn: TestTurn, event: AssistantEvent): TestTurn {
  switch (event.type) {
    case "token":
      return { ...turn, text: turn.text + event.content };
    case "metrica":
      return { ...turn, metric: event };
    case "recusa":
      return {
        ...turn,
        refusal: { codigo: event.codigo, motivo: event.motivo },
      };
    case "error":
      return { ...turn, failure: event.message };
    case "done":
      return { ...turn, done: event };
  }
}

export function DryRun({ hasDraft }: { hasDraft: boolean | null }) {
  const [question, setQuestion] = useState("");
  const [useDraft, setUseDraft] = useState(false);
  const [turns, setTurns] = useState<TestTurn[]>([]);
  const [streaming, setStreaming] = useState(false);
  const field = useRef<HTMLTextAreaElement>(null);

  async function run() {
    const asked = question.trim();

    if (!asked || streaming) {
      return;
    }

    const turn: TestTurn = { ...novoTurno(asked), useDraft };
    const update = (change: (current: TestTurn) => TestTurn) =>
      setTurns((previous) =>
        previous.map((item) => (item.id === turn.id ? change(item) : item)),
      );

    setQuestion("");
    setStreaming(true);
    setTurns((previous) => [...previous, turn]);

    try {
      await testAssistant(asked, useDraft, {
        onEvent: (event) => update((current) => applyEvent(current, event)),
      });
    } catch (error) {
      // Antes do primeiro byte: 401, 403 (rascunho sem ser admin), 404 (sem
      // rascunho), 429. O `detail` já é a frase.
      update((current) => ({
        ...current,
        failure:
          error instanceof ApiError && error.detail ? error.detail : FAILED,
      }));
    } finally {
      setStreaming(false);
      field.current?.focus();
    }
  }

  return (
    <section aria-label={TITLE}>
      <Card>
        <CardHeader
          eyebrow="Teste"
          title={TITLE}
          note="O teste roda sempre como você. O que cada pessoa alcança está na aba Capacidades."
        />
        <div className="flex flex-col gap-4 px-5 py-4">
          <p className="bg-alert-bg text-alert rounded-[10px] px-3 py-2 text-sm font-bold">
            {REAL_DATA}
          </p>

          {turns.length === 0 ? (
            <EmptyState
              icon={FlaskConical}
              tone="neutral"
              compact
              title="Nenhum teste ainda"
              description="Faça uma pergunta como um gestor faria. A métrica escolhida, o período e os filtros aparecem acima da resposta."
            />
          ) : (
            <ol aria-label="Testes" className="flex flex-col gap-4">
              {turns.map((turn) => (
                <li key={turn.id} className="flex flex-col gap-2">
                  <p className="bg-muted text-ink ml-auto max-w-[80%] rounded-[14px] px-4 py-2 text-sm font-medium">
                    {turn.question}
                  </p>
                  <div className="border-line-subtle flex max-w-[90%] flex-col gap-3 rounded-[14px] border p-4">
                    <Badge tone={turn.useDraft ? "alert" : "neutral"}>
                      {turn.useDraft ? "Rascunho" : "Versão no ar"}
                    </Badge>
                    <TurnAnswer turn={turn} streaming={streaming} />
                  </div>
                </li>
              ))}
            </ol>
          )}

          <form
            className="flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              void run();
            }}
          >
            <label
              htmlFor="assistant-test-question"
              className="text-2xs text-ink-muted font-bold tracking-[0.08em] uppercase"
            >
              Pergunta
            </label>
            <textarea
              id="assistant-test-question"
              ref={field}
              rows={2}
              value={question}
              maxLength={1000}
              disabled={streaming}
              placeholder="Quantos desvios tivemos esta semana?"
              onChange={(event) => setQuestion(event.target.value)}
              className="bg-control border-control-line text-ink placeholder:text-ink-faint rounded-[10px] border px-3 py-2 text-base outline-none focus-visible:border-transparent disabled:opacity-60"
            />
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4"
                  checked={useDraft}
                  disabled={hasDraft !== true || streaming}
                  aria-describedby={
                    hasDraft === true ? undefined : "assistant-test-no-draft"
                  }
                  onChange={(event) => setUseDraft(event.target.checked)}
                />
                <span className="text-ink">
                  Usar o rascunho em vez da versão no ar
                </span>
              </label>
              {hasDraft === true ? null : (
                <span
                  id="assistant-test-no-draft"
                  className="text-ink-faint text-xs"
                >
                  {hasDraft === false ? NO_DRAFT : UNKNOWN_DRAFT}
                </span>
              )}
              <Button
                type="submit"
                disabled={streaming || question.trim().length === 0}
                className="ml-auto"
              >
                {streaming ? (
                  <Spinner />
                ) : (
                  <Send aria-hidden className="size-4" />
                )}
                {streaming ? "Testando…" : "Testar"}
              </Button>
            </div>
          </form>

          <p className="text-ink-faint border-line-subtle border-t pt-3 text-xs">
            {DRY_RUN}
          </p>
        </div>
      </Card>
    </section>
  );
}
