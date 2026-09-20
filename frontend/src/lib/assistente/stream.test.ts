import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import {
  askAssistant,
  parseFrame,
  readEvents,
  streamAssistant,
} from "@/lib/assistente/stream";

const getSession = vi.fn();

// A sessão do navegador, só para o token: o transporte a pede antes do fetch.
vi.mock("@/lib/supabase", () => ({
  createBrowserSupabaseClient: () => ({
    auth: { getSession: () => getSession() },
  }),
}));

/**
 * O que se testa aqui é a moldura, não a resposta: um quadro partido no meio do
 * JSON é o caso comum de um stream de token, e um `ping` que virasse texto na
 * tela seria uma falha visível em toda pergunta que demorasse quinze segundos.
 */

function stream(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();

  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

async function collect(body: ReadableStream<Uint8Array>) {
  const events = [];

  for await (const event of readEvents(body)) {
    events.push(event);
  }

  return events;
}

describe("parseFrame", () => {
  it("lê o evento e o payload", () => {
    expect(parseFrame('event: token\ndata: {"content":"oi"}')).toEqual({
      type: "token",
      content: "oi",
    });
  });

  it("descarta o ping, que é keep-alive e não conteúdo", () => {
    expect(parseFrame("event: ping\ndata: {}")).toBeNull();
  });

  it("descarta evento que não conhece em vez de quebrar a aba", () => {
    // Uma aba aberta há uma hora tem o bundle antigo; um evento novo no backend
    // não pode derrubar a conversa dela.
    expect(parseFrame('event: futuro\ndata: {"x":1}')).toBeNull();
  });

  it("descarta quadro com data que não é JSON", () => {
    expect(parseFrame("event: token\ndata: <html>")).toBeNull();
  });
});

describe("readEvents", () => {
  it("remonta o quadro partido entre dois chunks", async () => {
    const events = await collect(
      stream('event: token\ndata: {"cont', 'ent":"42"}\n\n'),
    );

    expect(events).toEqual([{ type: "token", content: "42" }]);
  });

  it("entrega vários quadros de um chunk só, na ordem", async () => {
    const events = await collect(
      stream(
        'event: metrica\ndata: {"codigo":"deviations_total","titulo":"Total","parametros":{},"ignorados":[],"linhas":1}\n\n' +
          'event: token\ndata: {"content":"Foram "}\n\n' +
          'event: token\ndata: {"content":"42."}\n\n' +
          'event: done\ndata: {"consulta_id":"abc","modelo":"m","tokens_entrada":10,"tokens_saida":2,"latencia_ms":30}\n\n',
      ),
    );

    expect(events.map((event) => event.type)).toEqual([
      "metrica",
      "token",
      "token",
      "done",
    ]);
  });

  it("atravessa o ping sem interromper o texto", async () => {
    const events = await collect(
      stream(
        'event: token\ndata: {"content":"a"}\n\n',
        "event: ping\ndata: {}\n\n",
        'event: token\ndata: {"content":"b"}\n\n',
      ),
    );

    expect(events).toEqual([
      { type: "token", content: "a" },
      { type: "token", content: "b" },
    ]);
  });

  it("a recusa chega como evento, e não como erro", async () => {
    const events = await collect(
      stream(
        'event: recusa\ndata: {"codigo":"sem_metrica","motivo":"Não tenho essa métrica."}\n\n',
      ),
    );

    expect(events).toEqual([
      {
        type: "recusa",
        codigo: "sem_metrica",
        motivo: "Não tenho essa métrica.",
      },
    ]);
  });
});

describe("streamAssistant e askAssistant — um transporte, dois caminhos", () => {
  function sseResponse(body: string, status = 200) {
    return new Response(body, {
      status,
      headers: { "Content-Type": "text/event-stream" },
    });
  }

  beforeEach(() => {
    getSession.mockResolvedValue({
      data: { session: { access_token: "token-de-teste" } },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("askAssistant continua batendo em /assistente/perguntar com `{question}`", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        sseResponse('event: token\ndata: {"content":"42"}\n\n'),
      );
    const onEvent = vi.fn();

    await askAssistant("Quantos?", { onEvent });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.stub.test/assistente/perguntar");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ question: "Quantos?" });
    expect((init?.headers as Record<string, string>).Authorization).toBe(
      "Bearer token-de-teste",
    );
    expect(onEvent).toHaveBeenCalledWith({ type: "token", content: "42" });
  });

  it("streamAssistant leva o caminho e o corpo que recebeu — é o que o teste da configuração usa", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        sseResponse('event: token\ndata: {"content":"ok"}\n\n'),
      );
    const onEvent = vi.fn();

    await streamAssistant(
      "/assistente/configuracao/testar",
      { question: "Quantos?", use_draft: true },
      { onEvent },
    );

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.stub.test/assistente/configuracao/testar");
    expect(JSON.parse(init?.body as string)).toEqual({
      question: "Quantos?",
      use_draft: true,
    });
    expect(onEvent).toHaveBeenCalledWith({ type: "token", content: "ok" });
  });

  it("⛔ `res.ok` é conferido antes do primeiro byte: um 404 vira ApiError com o detail, e nenhum evento", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Não há rascunho para testar." }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const onEvent = vi.fn();

    const failure = await streamAssistant(
      "/assistente/configuracao/testar",
      { question: "?", use_draft: true },
      { onEvent },
    ).catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(404);
    expect((failure as ApiError).detail).toBe("Não há rascunho para testar.");
    expect(onEvent).not.toHaveBeenCalled();
  });
});
