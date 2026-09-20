import { ApiError, readDetail } from "@/lib/api";
import { publicEnv } from "@/lib/env";
import { createBrowserSupabaseClient } from "@/lib/supabase";

/**
 * O transporte do assistente. Nada aqui decide o que a pessoa lê — decide
 * apenas o que chegou.
 *
 * `EventSource` não serve, e não é preferência: ele não aceita header
 * `Authorization`, e o token de sessão do Supabase é o mesmo dos dois caminhos
 * do contrato. Então é `fetch` + `ReadableStream`, e a moldura do SSE é
 * desmontada aqui.
 *
 * O `res.ok` é conferido **antes** de a leitura começar. Um 401, um 403 ou um
 * 429 chegam como o JSON padrão do FastAPI, com status, e nunca como evento —
 * depois do primeiro byte não sobra status code para mudar. Ler primeiro e
 * decidir depois transformaria "sua sessão expirou" numa conversa vazia.
 */

export type MetricEvent = {
  type: "metrica";
  codigo: string;
  titulo: string;
  /** Só o que de fato filtrou a consulta. */
  parametros: Record<string, string>;
  /** O que o alvo não teve onde ligar, e por isso não filtrou nada. */
  ignorados: string[];
  linhas: number;
};

export type TokenEvent = { type: "token"; content: string };

/** Recusa é resposta válida, e chega dentro de um 200. */
export type RefusalEvent = { type: "recusa"; codigo: string; motivo: string };

export type StreamErrorEvent = { type: "error"; message: string };

export type DoneEvent = {
  type: "done";
  consulta_id: string;
  modelo: string;
  tokens_entrada: number;
  tokens_saida: number;
  latencia_ms: number;
};

export type AssistantEvent =
  MetricEvent | TokenEvent | RefusalEvent | StreamErrorEvent | DoneEvent;

const ASSISTANT_PATH = "/assistente/perguntar";

/**
 * Um quadro SSE em evento, ou `null` para o que não interessa a esta tela.
 *
 * `ping` cai aqui: ele existe para o proxy não derrubar um stream ocioso, e a
 * conversa não tem o que fazer com ele. Um `event:` desconhecido também vira
 * `null` em vez de erro — um evento novo no backend não pode quebrar uma aba
 * que ainda está com o bundle antigo.
 */
export function parseFrame(frame: string): AssistantEvent | null {
  let name = "";
  let data = "";

  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) {
      name = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      data += line.slice("data:".length).trim();
    }
  }

  if (!name || !data) {
    return null;
  }

  let payload: unknown;

  try {
    payload = JSON.parse(data);
  } catch {
    return null;
  }

  if (
    name !== "metrica" &&
    name !== "token" &&
    name !== "recusa" &&
    name !== "error" &&
    name !== "done"
  ) {
    return null;
  }

  return { type: name, ...(payload as object) } as AssistantEvent;
}

/**
 * Os eventos do corpo, na ordem. O quadro pode chegar partido em dois chunks —
 * um `token` cortado no meio do JSON é o caso comum, não o excepcional — então
 * o buffer só entrega o que já viu terminar em linha em branco.
 */
export async function* readEvents(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<AssistantEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();

      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      for (
        let cut = buffer.indexOf("\n\n");
        cut !== -1;
        cut = buffer.indexOf("\n\n")
      ) {
        const frame = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        const event = parseFrame(frame);

        if (event) {
          yield event;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export type StreamOptions = {
  onEvent: (event: AssistantEvent) => void;
  signal?: AbortSignal;
};

export type AskOptions = StreamOptions & {
  /** Validado contra a allowlist do backend — o cliente não escolhe sozinho. */
  model?: string;
};

/**
 * Um turno de SSE contra `path`, com a sessão do navegador. É o único lugar em
 * que o transporte do assistente existe: a conversa (`/assistente/perguntar`)
 * e o teste da configuração (`/assistente/configuracao/testar`) passam os dois
 * por aqui, e um parser só desmonta os quadros dos dois.
 */
export async function streamAssistant(
  path: string,
  body: Record<string, unknown>,
  { onEvent, signal }: StreamOptions,
): Promise<void> {
  const supabase = createBrowserSupabaseClient();
  const { data } = await supabase.auth.getSession();
  const accessToken = data.session?.access_token;

  if (!accessToken) {
    throw new ApiError(401, null);
  }

  const response = await fetch(`${publicEnv().NEXT_PUBLIC_API_URL}${path}`, {
    method: "POST",
    signal,
    headers: {
      Accept: "text/event-stream",
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }

  if (!response.body) {
    throw new ApiError(response.status, null);
  }

  for await (const event of readEvents(response.body)) {
    onEvent(event);
  }
}

export function askAssistant(
  question: string,
  { onEvent, signal, model }: AskOptions,
): Promise<void> {
  return streamAssistant(
    ASSISTANT_PATH,
    model ? { question, model } : { question },
    { onEvent, signal },
  );
}
