// As cinco correções do §4b, cada uma com o teste que prova que ela existe.
//
// Não havia um único teste em `supabase/functions/` — o §4b registrou isso como
// parte do risco, porque era o que tornava as quatro falhas invisíveis. O
// repositório aqui é falso e registra o que foi chamado e em que ordem; nada
// toca rede nem banco.

import { assert, assertEquals, assertRejects } from "jsr:@std/assert@1";

import {
  BACKFILL_WINDOW_DAYS,
  BatidaCorrelationBrokenError,
  type BatidaRow,
  BATIDAS_WINDOW_DAYS,
  type BatidaSyncRepository,
  computeBatidasDateRange,
  type ExistingBatidaRow,
  type ExistingMarcacaoRow,
  type FuncionarioLookupRow,
  type InsertFonteDadosInput,
  type MarcacaoRow,
  runBatidaSync,
  type SecullumReader,
  type SyncLogger,
  type SyncRunRecord,
  type UpsertBatidaInput,
  type UpsertMarcacaoInput,
} from "./batida-sync.ts";
import { resolveRunOptions } from "./run-options.ts";

const HOJE = "2026-08-24";
const silencioso: SyncLogger = { warn: () => {}, info: () => {} };

function batidaCrua(overrides: Record<string, unknown> = {}) {
  return {
    Id: 900,
    FuncionarioId: 10,
    Data: "2026-08-24T00:00:00",
    Entrada1: "08:00",
    Saida1: "12:00",
    // Sem FonteDados o caminho de "BatidaFonteDados" não roda — e é justamente
    // um dos dois pontos de falha parcial do §4b.
    FonteDadosEntrada1: { Nsr: "12345", Hora: "08:00", Data: "2026-08-24", Tipo: 0, Origem: 0 },
    ...overrides,
  };
}

function leitor(itens: unknown[]): SecullumReader {
  return { get: <T>() => Promise.resolve(itens as T) };
}

/**
 * Repositório falso com dois papéis: registrar a sequência de chamadas e
 * simular falha num passo escolhido.
 *
 * `committed` só recebe as operações quando a transação fecha. É o que permite
 * afirmar que uma falha no meio da escrita não deixa estado parcial — sem isso,
 * o teste provaria apenas que o código chamou `transaction`, não que a
 * atomicidade tem efeito.
 */
class RepoFalso implements BatidaSyncRepository {
  readonly committed: string[] = [];
  readonly chamadas: string[] = [];
  readonly runs: SyncRunRecord[] = [];
  emTransacao = false;
  falharEm: string | null = null;
  funcionarios: FuncionarioLookupRow[] = [{ id: "uuid-10", secullumFuncionarioId: 10 }];

  private pendentes: string[] = [];

  private registra(op: string) {
    this.chamadas.push(op);
    if (this.emTransacao) this.pendentes.push(op);
    else this.committed.push(op);
    if (this.falharEm === op) throw new Error(`falha simulada em ${op}`);
  }

  async transaction<T>(work: (tx: BatidaSyncRepository) => Promise<T>): Promise<T> {
    this.emTransacao = true;
    this.pendentes = [];
    try {
      const resultado = await work(this);
      // Commit: só agora as operações da transação viram estado.
      this.committed.push(...this.pendentes);
      return resultado;
    } finally {
      this.emTransacao = false;
      this.pendentes = [];
    }
  }

  listFuncionariosBySecullumIds(_ids: number[]): Promise<FuncionarioLookupRow[]> {
    this.registra("listFuncionarios");
    return Promise.resolve(this.funcionarios);
  }
  listBatidas(): Promise<ExistingBatidaRow[]> {
    this.registra("listBatidas");
    return Promise.resolve([]);
  }
  upsertBatidas(inputs: UpsertBatidaInput[]): Promise<BatidaRow[]> {
    this.registra("upsertBatidas");
    return Promise.resolve(
      inputs.map((i, n) => ({
        id: `batida-${n}`,
        funcionarioId: i.funcionarioId,
        data: i.data,
        secullumBatidaId: i.secullumBatidaId,
      })) as BatidaRow[],
    );
  }
  listMarcacoesByBatidaIds(): Promise<ExistingMarcacaoRow[]> {
    this.registra("listMarcacoes");
    return Promise.resolve([]);
  }
  upsertMarcacoes(inputs: UpsertMarcacaoInput[]): Promise<MarcacaoRow[]> {
    this.registra("upsertMarcacoes");
    return Promise.resolve(
      inputs.map((i, n) => ({
        id: `marcacao-${n}`,
        batidaId: i.batidaId,
        tipoColuna: i.tipoColuna,
        indiceColuna: i.indiceColuna,
      })) as MarcacaoRow[],
    );
  }
  deleteMarcacoesByIds(): Promise<void> {
    this.registra("deleteMarcacoes");
    return Promise.resolve();
  }
  deleteFonteDadosByBatidaIds(): Promise<void> {
    this.registra("deleteFonteDados");
    return Promise.resolve();
  }
  insertFonteDados(_inputs: InsertFonteDadosInput[]): Promise<void> {
    this.registra("insertFonteDados");
    return Promise.resolve();
  }
  setCursor(): Promise<void> {
    this.registra("setCursor");
    return Promise.resolve();
  }
  recordSyncRun(record: SyncRunRecord): Promise<void> {
    this.runs.push(record);
    return Promise.resolve();
  }
}

// ---------------------------------------------------------------------------
// 1. Transação em toda escrita
// ---------------------------------------------------------------------------
Deno.test("a fase de escrita inteira roda dentro de uma transação", async () => {
  const repo = new RepoFalso();
  let dentroDaTransacao: string[] = [];
  const original = repo.transaction.bind(repo);
  repo.transaction = (work) =>
    original(async (tx) => {
      const antes = repo.chamadas.length;
      const r = await work(tx);
      dentroDaTransacao = repo.chamadas.slice(antes);
      return r;
    });

  await runBatidaSync(leitor([batidaCrua()]), repo, silencioso, () => HOJE);

  // Os dois pontos de falha parcial do §4b estão do mesmo lado da fronteira.
  assert(dentroDaTransacao.includes("upsertBatidas"));
  assert(dentroDaTransacao.includes("listMarcacoes"));
  assert(dentroDaTransacao.includes("deleteFonteDados"));
  assert(dentroDaTransacao.includes("insertFonteDados"));
});

Deno.test("falha no meio da escrita não deixa Batida sem marcação", async () => {
  const repo = new RepoFalso();
  // O ponto exato do §4b: `upsertBatidas` commitava e a leitura seguinte falhava.
  repo.falharEm = "listMarcacoes";

  await assertRejects(
    () => runBatidaSync(leitor([batidaCrua()]), repo, silencioso, () => HOJE),
    Error,
    "falha simulada",
  );

  // Nada da fase de escrita virou estado — em particular, nenhuma "Batida" sem
  // marcação, que o motor leria como "não bateu ponto".
  assertEquals(repo.committed.includes("upsertBatidas"), false);
  assertEquals(repo.committed.includes("insertFonteDados"), false);
  // E o cursor não avançou sobre uma janela que não foi gravada.
  assertEquals(repo.chamadas.includes("setCursor"), false);
});

// ---------------------------------------------------------------------------
// 2. Zero-ingestão deixa de ser sucesso
// ---------------------------------------------------------------------------
Deno.test("correlação quebrada levanta erro em vez de responder sucesso", async () => {
  const repo = new RepoFalso();
  repo.funcionarios = []; // nenhum FuncionarioId encontra colaborador local

  const erro = await assertRejects(
    () =>
      runBatidaSync(leitor([batidaCrua(), batidaCrua({ Id: 901 })]), repo, silencioso, () => HOJE),
    BatidaCorrelationBrokenError,
  );

  // O resumo viaja com o erro: é o que permite ler "parou" sem abrir o log.
  assertEquals(erro.summary.batidasFetched, 2);
  assertEquals(erro.summary.batidasSkippedMissingFuncionario, 2);
  assertEquals(erro.summary.batidasUpserted, 0);
});

Deno.test("janela genuinamente vazia continua sendo sucesso", async () => {
  const repo = new RepoFalso();

  const summary = await runBatidaSync(leitor([]), repo, silencioso, () => HOJE);

  assertEquals(summary.batidasFetched, 0);
  assertEquals(summary.batidasSkippedMissingFuncionario, 0);
});

// ---------------------------------------------------------------------------
// 3. Alarme com prova de resultado
// ---------------------------------------------------------------------------
Deno.test("o resumo carrega escopo e janela, que é o que a execução registra", async () => {
  const repo = new RepoFalso();

  const summary = await runBatidaSync(
    leitor([batidaCrua()]),
    repo,
    silencioso,
    () => HOJE,
    7,
    "backfill",
  );

  assertEquals(summary.scope, "backfill");
  assertEquals(summary.windowDays, 7);
  assertEquals(summary.batidasUpserted, 1);
});

// ---------------------------------------------------------------------------
// 4. Janela parametrizável + backfill
// ---------------------------------------------------------------------------
Deno.test("a janela deixou de ser fixa em 2 dias", () => {
  assertEquals(computeBatidasDateRange(HOJE), { dataInicio: "2026-08-22", dataFim: HOJE });
  assertEquals(computeBatidasDateRange(HOJE, BACKFILL_WINDOW_DAYS), {
    dataInicio: "2026-08-17",
    dataFim: HOJE,
  });
  assertEquals(computeBatidasDateRange(HOJE, 30).dataInicio, "2026-07-25");
});

Deno.test("a invocação escolhe escopo e janela, e um corpo inválido cai no padrão", async () => {
  const pedido = (corpo?: string, url = "http://x/sync-batidas") =>
    new Request(url, { method: "POST", body: corpo });

  assertEquals(await resolveRunOptions(pedido()), {
    scope: "incremental",
    windowDays: BATIDAS_WINDOW_DAYS,
  });
  assertEquals(await resolveRunOptions(pedido('{"scope":"backfill"}')), {
    scope: "backfill",
    windowDays: BACKFILL_WINDOW_DAYS,
  });
  assertEquals(await resolveRunOptions(pedido('{"windowDays":30}')), {
    scope: "incremental",
    windowDays: 30,
  });
  // O pg_cron manda POST sem corpo; um corpo quebrado não pode derrubar o job.
  assertEquals(await resolveRunOptions(pedido("nao é json")), {
    scope: "incremental",
    windowDays: BATIDAS_WINDOW_DAYS,
  });
  // Valor absurdo é ignorado em vez de virar uma janela de -1 dia.
  assertEquals((await resolveRunOptions(pedido('{"windowDays":0}'))).windowDays, 2);
  assertEquals(
    (await resolveRunOptions(pedido(undefined, "http://x/sync-batidas?scope=backfill"))).scope,
    "backfill",
  );
});
