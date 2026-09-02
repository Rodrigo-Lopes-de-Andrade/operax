// Implementação de `BatidaSyncRepository` (batida-sync.ts) sobre conexão
// direta ao Postgres (driver `postgres`, service_role via DATABASE_URL do
// Transaction Pooler) — ver `_shared/postgres-client.ts` para o motivo de
// não usar supabase-js aqui (PostgREST não alcança `secullum`/`app`, mesmo
// com service_role). Uso exclusivo do worker (Edge Function `sync-batidas`),
// nunca do painel do Owner.
//
// ⚠️ Toda escrita aqui é em LOTE (um único upsert/delete/insert por tabela
// por ciclo) — nunca uma chamada de rede por batida/funcionário/slot. Mesma
// disciplina de performance de supabase-cadastro-repository.ts (incidente de
// produção WORKER_RESOURCE_LIMIT, ver a nota no topo de cadastro-sync.ts).
//
// Nomenclatura (ADR-012): `"PascalCase" entre aspas` é cópia literal de um
// campo/tabela do Secullum (schema `secullum`); `minusculo_com_underscore`
// é nosso (schema `app`, exceto onde comentado o contrário). Ver o
// cabeçalho de supabase/migrations/20260813163000_batidas.sql para o
// racional completo de cada tabela.

import { getSql, type Sql } from "./postgres-client.ts";
import { writeSyncRun } from "./sync-run.ts";
import type {
  BatidaRow,
  BatidaSyncRepository,
  ExistingBatidaRow,
  ExistingMarcacaoRow,
  FuncionarioLookupRow,
  InsertFonteDadosInput,
  MarcacaoRow,
  SyncRunRecord,
  UpsertBatidaInput,
  UpsertMarcacaoInput,
} from "./batida-sync.ts";

export class SupabaseBatidaRepository implements BatidaSyncRepository {
  private readonly sql: Sql;

  /**
   * `sql` é injetável por um motivo só, e ele é a atomicidade: `transaction`
   * abre uma transação com `sql.begin` e devolve **outro repositório**,
   * construído sobre a conexão da transação. É o que permite `runBatidaSync`
   * escrever a fase inteira sem saber que existe transação — ele só chama
   * métodos do repositório que recebeu.
   */
  constructor(sql: Sql = getSql()) {
    this.sql = sql;
  }

  /**
   * Roda `work` dentro de uma transação. Ou tudo commita, ou nada.
   *
   * Sem isto, `upsertBatidas` commitava antes de `listMarcacoesByBatidaIds`
   * rodar, e uma falha no meio deixava linhas de `Batida` com **zero
   * marcação**. Esse estado não se lê como "faltou dado": o motor de detecção
   * o lê como `no_punches` — "o colaborador não bateu ponto naquele dia" — e
   * emite indício contra uma pessoa que bateu. É o risco 1 do §4b do
   * `PLANO-RECONCILIACAO-NUVEM.md`, e é o pior dos quatro porque o modo de
   * falha não é perder dado: é inventar um fato sobre alguém.
   */
  transaction<T>(work: (tx: BatidaSyncRepository) => Promise<T>): Promise<T> {
    return this.sql.begin((txSql) =>
      work(new SupabaseBatidaRepository(txSql as unknown as Sql))
    ) as Promise<T>;
  }

  async listFuncionariosBySecullumIds(
    secullumFuncionarioIds: number[],
  ): Promise<FuncionarioLookupRow[]> {
    if (!secullumFuncionarioIds.length) return [];
    // Leitura em lote, filtrada pelos FuncionarioId presentes no lote de
    // batidas — nunca uma consulta por funcionário.
    const rows = await this.sql<{ id: string; FuncionarioId: number }[]>`
      select id, "FuncionarioId"
      from secullum."Funcionario"
      where "FuncionarioId" in ${this.sql(secullumFuncionarioIds)}
    `;
    return rows.map((row) => ({
      id: row.id,
      secullumFuncionarioId: row.FuncionarioId,
    }));
  }

  async listBatidas(
    funcionarioIds: string[],
    dataInicio: string,
    dataFim: string,
  ): Promise<ExistingBatidaRow[]> {
    if (!funcionarioIds.length) return [];
    // Leitura em lote do estado ATUAL, restrita ao escopo (funcionários x
    // janela) — nunca a tabela inteira, nunca um SELECT por par
    // (funcionario_id, Data).
    // ⚠️ Cast explícito para text: o driver `postgres` devolve `date` como
    // objeto `Date` do JS por padrão (diferença de PostgREST) — sem o cast,
    // a chave de idempotência (funcionario_id, Data) nunca bateria com a
    // "Data" recém-parseada (string) vinda do Secullum, e todo par pareceria
    // "novo" no diff em batida-sync.ts.
    const rows = await this.sql<
      { id: string; funcionario_id: string; Data: string; BatidaId: number | null }[]
    >`
      select id, funcionario_id, "Data"::text as "Data", "BatidaId"
      from secullum."Batida"
      where funcionario_id in ${this.sql(funcionarioIds)}
        and "Data" >= ${dataInicio}
        and "Data" <= ${dataFim}
    `;
    return rows.map((row) => ({
      id: row.id,
      funcionarioId: row.funcionario_id,
      data: row.Data,
      secullumBatidaId: row.BatidaId ?? null,
    }));
  }

  async upsertBatidas(inputs: UpsertBatidaInput[]): Promise<BatidaRow[]> {
    if (!inputs.length) return [];
    const now = new Date().toISOString();
    // Chave de idempotência (funcionario_id, "Data") — "BatidaId" é
    // ATRIBUTO com índice não-único (alteração (A) ao ADR-007, ver ADR-011 e
    // o cabeçalho da migration 20260813163000).
    const rows = inputs.map((input) => ({
      funcionario_id: input.funcionarioId,
      FuncionarioId: input.secullumFuncionarioId,
      BatidaId: input.secullumBatidaId,
      Data: input.data,
      Observacoes: input.observacoes,
      Ajuste: input.ajuste,
      Abono2: input.abono2,
      Abono3: input.abono3,
      Abono4: input.abono4,
      Compensado: input.compensado,
      AlmocoLivre: input.almocoLivre,
      Neutro: input.neutro,
      NBanco: input.nBanco,
      Folga: input.folga,
      Refeicao: input.refeicao,
      status_dia_rotulo: input.statusDiaRotulo,
      sincronizado_em: now,
      atualizado_em: now,
    }));
    const columns = [
      "funcionario_id",
      "FuncionarioId",
      "BatidaId",
      "Data",
      "Observacoes",
      "Ajuste",
      "Abono2",
      "Abono3",
      "Abono4",
      "Compensado",
      "AlmocoLivre",
      "Neutro",
      "NBanco",
      "Folga",
      "Refeicao",
      "status_dia_rotulo",
      "sincronizado_em",
      "atualizado_em",
    ] as const;
    const result = await this.sql<
      { id: string; funcionario_id: string; Data: string; BatidaId: number | null }[]
    >`
      insert into secullum."Batida" ${this.sql(rows, ...columns)}
      on conflict (funcionario_id, "Data") do update set
        "FuncionarioId" = excluded."FuncionarioId",
        "BatidaId" = excluded."BatidaId",
        "Observacoes" = excluded."Observacoes",
        "Ajuste" = excluded."Ajuste",
        "Abono2" = excluded."Abono2",
        "Abono3" = excluded."Abono3",
        "Abono4" = excluded."Abono4",
        "Compensado" = excluded."Compensado",
        "AlmocoLivre" = excluded."AlmocoLivre",
        "Neutro" = excluded."Neutro",
        "NBanco" = excluded."NBanco",
        "Folga" = excluded."Folga",
        "Refeicao" = excluded."Refeicao",
        status_dia_rotulo = excluded.status_dia_rotulo,
        sincronizado_em = excluded.sincronizado_em,
        atualizado_em = excluded.atualizado_em
      returning id, funcionario_id, "Data"::text as "Data", "BatidaId"
    `;
    return result.map((row) => ({
      id: row.id,
      funcionarioId: row.funcionario_id,
      data: row.Data,
      secullumBatidaId: row.BatidaId ?? null,
    }));
  }

  async listMarcacoesByBatidaIds(batidaIds: string[]): Promise<ExistingMarcacaoRow[]> {
    if (!batidaIds.length) return [];
    const rows = await this.sql<
      { id: string; batida_id: string; tipo_coluna: "Entrada" | "Saida"; indice_coluna: number }[]
    >`
      select id, batida_id, tipo_coluna, indice_coluna
      from app.batida_marcacao
      where batida_id in ${this.sql(batidaIds)}
    `;
    return rows.map((row) => ({
      id: row.id,
      batidaId: row.batida_id,
      tipoColuna: row.tipo_coluna,
      indiceColuna: row.indice_coluna,
    }));
  }

  async upsertMarcacoes(inputs: UpsertMarcacaoInput[]): Promise<MarcacaoRow[]> {
    if (!inputs.length) return [];
    const now = new Date().toISOString();
    // Chave de idempotência POSICIONAL (batida_id, tipo_coluna,
    // indice_coluna) — nunca "FonteDadosId" (nullable, ADR-007).
    const rows = inputs.map((input) => ({
      batida_id: input.batidaId,
      funcionario_id: input.funcionarioId,
      data: input.data,
      tipo_coluna: input.tipoColuna,
      indice_coluna: input.indiceColuna,
      valor_bruto: input.valorBruto,
      hora: input.hora,
      status_rotulo: input.statusRotulo,
      Memoria: input.memoria,
      EquipId: input.equipId,
      FonteDadosId: input.fonteDadosId,
      desconsiderada: input.desconsiderada,
      sincronizado_em: now,
      atualizado_em: now,
    }));
    const columns = [
      "batida_id",
      "funcionario_id",
      "data",
      "tipo_coluna",
      "indice_coluna",
      "valor_bruto",
      "hora",
      "status_rotulo",
      "Memoria",
      "EquipId",
      "FonteDadosId",
      "desconsiderada",
      "sincronizado_em",
      "atualizado_em",
    ] as const;
    const result = await this.sql<
      { id: string; batida_id: string; tipo_coluna: "Entrada" | "Saida"; indice_coluna: number }[]
    >`
      insert into app.batida_marcacao ${this.sql(rows, ...columns)}
      on conflict (batida_id, tipo_coluna, indice_coluna) do update set
        funcionario_id = excluded.funcionario_id,
        data = excluded.data,
        valor_bruto = excluded.valor_bruto,
        hora = excluded.hora,
        status_rotulo = excluded.status_rotulo,
        "Memoria" = excluded."Memoria",
        "EquipId" = excluded."EquipId",
        "FonteDadosId" = excluded."FonteDadosId",
        desconsiderada = excluded.desconsiderada,
        sincronizado_em = excluded.sincronizado_em,
        atualizado_em = excluded.atualizado_em
      returning id, batida_id, tipo_coluna, indice_coluna
    `;
    return result.map((row) => ({
      id: row.id,
      batidaId: row.batida_id,
      tipoColuna: row.tipo_coluna,
      indiceColuna: row.indice_coluna,
    }));
  }

  async deleteMarcacoesByIds(ids: string[]): Promise<void> {
    if (!ids.length) return; // defensivo — nunca DELETE sem filtro.
    await this.sql`delete from app.batida_marcacao where id in ${this.sql(ids)}`;
  }

  async deleteFonteDadosByBatidaIds(batidaIds: string[]): Promise<void> {
    if (!batidaIds.length) return; // defensivo — nunca DELETE sem filtro.
    await this.sql`
      delete from secullum."BatidaFonteDados" where batida_id in ${this.sql(batidaIds)}
    `;
  }

  async insertFonteDados(inputs: InsertFonteDadosInput[]): Promise<void> {
    if (!inputs.length) return;
    const now = new Date().toISOString();
    const rows = inputs.map((input) => ({
      batida_marcacao_id: input.batidaMarcacaoId,
      batida_id: input.batidaId,
      FonteDadosId: input.fonteDadosId,
      Nsr: input.nsr,
      Hora: input.hora,
      Data: input.data,
      DataInclusao: input.dataInclusao,
      Tipo: input.tipo,
      Origem: input.origem,
      criado_em: now,
      atualizado_em: now,
    }));
    await this.sql`
      insert into secullum."BatidaFonteDados" ${
      this.sql(
        rows,
        "batida_marcacao_id",
        "batida_id",
        "FonteDadosId",
        "Nsr",
        "Hora",
        "Data",
        "DataInclusao",
        "Tipo",
        "Origem",
        "criado_em",
        "atualizado_em",
      )
    }
    `;
  }

  async setCursor(chave: string, valor: string): Promise<void> {
    // Só rastreio/diagnóstico (nunca usado para calcular a próxima janela —
    // ver batida-sync.ts). Upsert de uma única linha.
    await this.sql`
      insert into app.cursor_sincronizacao (chave, valor, atualizado_em)
      values (${chave}, ${valor}, ${new Date().toISOString()})
      on conflict (chave) do update set
        valor = excluded.valor,
        atualizado_em = excluded.atualizado_em
    `;
  }

  /** Grava o resultado da execução em `app.sync_run` — ver `sync-run.ts`. */
  async recordSyncRun(record: SyncRunRecord): Promise<void> {
    await writeSyncRun(this.sql, "[sync-batidas]", record);
  }
}

/**
 * Cria o repositório a partir das variáveis de ambiente padrão do projeto.
 * Uso exclusivo de Edge Functions — `DATABASE_URL` nunca deve chegar ao
 * painel/frontend (docs/06-seguranca-lgpd.md).
 */
export function createSupabaseBatidaRepositoryFromEnv(): SupabaseBatidaRepository {
  return new SupabaseBatidaRepository();
}
