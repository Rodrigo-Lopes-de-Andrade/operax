// Motor da sincronização de batidas (ingestão de /Batidas — antecipação
// consciente da Sprint 2, ver supabase/migrations/20260813163000_batidas.sql
// e docs/adr/ADR-007-granularidade-batidas.md). Escopo desta fase: SÓ
// ingestão ("Batida" + batida_marcacao + "BatidaFonteDados") — o motor de
// detecção de desvio (`desvio`, comparação x "HorarioDia") continua sendo
// Sprint 2 e NÃO é implementado aqui.
//
// Mesmo desenho arquitetural de cadastro-sync.ts: módulo independente de
// runtime (Deno/Supabase), recebe um `SecullumReader` (qualquer objeto com
// `.get<T>(path, query)`, compatível com `SecullumClient`) e um
// `BatidaSyncRepository` (abstração de persistência — implementação real em
// supabase-batida-repository.ts, implementação em memória em
// batida-sync.test.ts). Isso permite testar toda a lógica (parsing dos 3
// estados de slot, convergência de dia, correlação de funcionário) com
// fixtures locais, sem Secullum real nem Supabase real.
//
// Reaproveita de cadastro-sync.ts (funções puras, sem acoplamento de
// runtime): `parseHorarioDiaTimeField` (mesmo parser de 3 estados "HH:mm" /
// texto de status / vazio, já usado para "HorarioDia" — ver ADR-007),
// `asBoolean`/`asNumber`/`asString`/`asTextPassthrough` (normalização
// defensiva de tipo) e `parseSecullumDateOnly`/`TodayProvider`/
// `systemTodayInSaoPaulo` (mesma disciplina de fuso: extrair SEMPRE os 10
// primeiros caracteres de um campo de data do Secullum, nunca `new Date()` +
// `toISOString()` — a Edge Function roda em UTC e a conversão ingênua
// desloca um dia para horários locais brasileiros).
//
// Regras de negócio implementadas aqui — ver docs/03-integracao-secullum.md
// ("/Batidas — tabela básica do sistema") e a migration 20260813163000:
//   - Janela deslizante FIXA (hoje - 2 dias .. hoje), nunca reprocessa o
//     histórico completo. `cursor_sincronizacao` é atualizado só para
//     rastreio/diagnóstico, nunca para calcular a próxima janela.
//   - Correlação `Batida.FuncionarioId` -> `"Funcionario".id` é JOIN DIRETO
//     por `"Funcionario"."FuncionarioId"` (o mesmo inteiro) — sem match
//     fuzzy por nome/PIS (diferente de /FuncionariosAfastamentos). Leitura em
//     lote (uma única consulta), nunca uma consulta por funcionário.
//     `FuncionarioId` sem `Funcionario` local -> não falha o job, loga aviso
//     agregado, pula a batida.
//   - `"Batida"` upsert em lote por (funcionario_id, "Data") — `"BatidaId"`
//     é atributo com índice NÃO-único; divergência de `"BatidaId"` no mesmo
//     par (funcionario_id, "Data") entre execuções é ANOMALIA logada, nunca
//     silenciada (alteração (A) ao ADR-007, ver ADR-011).
//   - `batida_marcacao`: uma linha para CADA slot (Entrada1..5/Saida1..5)
//     com QUALQUER informação (valor OU Memoria OU EquipId OU FonteDados),
//     não só os que têm batida efetiva. `hora` só é preenchida quando o
//     valor bruto é "HH:mm" válido. Escrita por SUBSTITUIÇÃO DO DIA INTEIRO:
//     upsert das colunas presentes + DELETE das que deixaram de existir
//     desde a última sincronização daquele dia (sem isso, uma batida
//     removida no Secullum nunca some do cache — ver ADR-007).
//   - `"BatidaFonteDados"`: 1:1 opcional com batida_marcacao. `"Tipo"`/
//     `"Origem"` gravados brutos, sem CHECK — valor fora do intervalo
//     documentado (ex.: `Origem = 11`, já visto em produção) é TOLERADO,
//     nunca falha o job, log agregado uma vez por valor distinto por
//     execução.
//   - `"Observacoes"`/`"Ajuste"`/`"Abono2..4"` são persistidos (ADR-011),
//     mas NUNCA logados em nenhum aviso/erro, mesmo persistidos.
//   - Batching obrigatório: uma chamada de rede por tabela por ciclo (nunca
//     por batida/funcionário individual) — mesma disciplina de performance
//     de cadastro-sync.ts (incidente de produção WORKER_RESOURCE_LIMIT).
//   - Cliente Secullum continua GET-only — nenhuma escrita.
//
// ⚠️ Nota sobre "transação" (release notes desta fase): a migration pede
// "escrita por substituição do dia inteiro em transação". Este módulo segue
// exatamente o mesmo padrão JÁ ESTABELECIDO no restante do projeto para
// convergência (upsert em lote + DELETE em lote separado, ex.:
// employee_absence no ADR-010, "HorarioDescansoFaixaItem" no ADR-011): uma
// sequência de chamadas batched ao PostgREST via supabase-js, NÃO uma
// transação real (BEGIN/COMMIT) via RPC — nenhuma function deste projeto usa
// RPC para isso até aqui. Cada etapa é idempotente e a sequência final
// converge para o estado correto do Secullum mesmo se something falhar no
// meio (a próxima execução da janela corrige). Ver relatório desta tarefa
// para o racional completo.

import {
  asBoolean,
  asNumber,
  asString,
  asTextPassthrough,
  parseHorarioDiaTimeField,
  parseSecullumDateOnly,
  systemTodayInSaoPaulo,
  type TodayProvider,
} from "./cadastro-sync.ts";
import type { RawBatida, RawFonteDados } from "./secullum-batida-types.ts";
import type { SyncScope } from "./sync-run.ts";

// ---------------------------------------------------------------------------
// Contrato mínimo exigido do client Secullum (compatível com SecullumClient).
// ---------------------------------------------------------------------------
export interface SecullumReader {
  get<T>(path: string, query?: Record<string, string | undefined>): Promise<T>;
}

// ---------------------------------------------------------------------------
// Linhas / entradas de upsert do repositório.
// ---------------------------------------------------------------------------

export interface FuncionarioLookupRow {
  /** uuid local ("Funcionario".id). */
  id: string;
  secullumFuncionarioId: number;
}

/** Estado ATUAL de "Batida" no escopo (funcionários x janela), lido ANTES do upsert — base da detecção de anomalia de `"BatidaId"`. */
export interface ExistingBatidaRow {
  id: string;
  funcionarioId: string;
  /** "yyyy-MM-dd". */
  data: string;
  secullumBatidaId: number | null;
}

export interface UpsertBatidaInput {
  funcionarioId: string;
  secullumFuncionarioId: number;
  secullumBatidaId: number;
  /** "yyyy-MM-dd". */
  data: string;
  /** ⚠️ Texto livre — nunca logar (ver docs/06-seguranca-lgpd.md). */
  observacoes: string | null;
  ajuste: string | null;
  abono2: string | null;
  abono3: string | null;
  abono4: string | null;
  compensado: boolean;
  almocoLivre: boolean;
  neutro: boolean;
  nBanco: boolean;
  folga: boolean;
  refeicao: boolean;
  /** NOSSO — preenchido quando alguma coluna do dia carrega texto de status em vez de hora. */
  statusDiaRotulo: string | null;
}

export interface BatidaRow {
  id: string;
  funcionarioId: string;
  data: string;
  secullumBatidaId: number | null;
}

export type SlotTipoColuna = "Entrada" | "Saida";

/** Estado ATUAL de batida_marcacao para as "Batida" tocadas nesta execução — base do DELETE de convergência. */
export interface ExistingMarcacaoRow {
  id: string;
  batidaId: string;
  tipoColuna: SlotTipoColuna;
  indiceColuna: number;
}

export interface UpsertMarcacaoInput {
  batidaId: string;
  /** Desnormalizado de "Batida" (mesmo racional de "Funcionario".empresa_id) — evita join no caminho quente do motor/relatório/dashboard. */
  funcionarioId: string;
  data: string;
  tipoColuna: SlotTipoColuna;
  indiceColuna: number;
  valorBruto: string | null;
  hora: string | null;
  statusRotulo: string | null;
  memoria: string | null;
  equipId: number | null;
  fonteDadosId: number | null;
  desconsiderada: boolean;
}

export interface MarcacaoRow {
  id: string;
  batidaId: string;
  tipoColuna: SlotTipoColuna;
  indiceColuna: number;
}

export interface InsertFonteDadosInput {
  batidaMarcacaoId: string;
  /** Desnormalizado — permite DELETE/consulta no escopo do dia inteiro sem join (mesmo racional da migration). */
  batidaId: string;
  fonteDadosId: number | null;
  nsr: string | null;
  hora: string | null;
  data: string | null;
  /** ISO com ms, passado adiante como veio — coluna timestamptz. */
  dataInclusao: string | null;
  tipo: number | null;
  origem: number | null;
}

/**
 * Abstração de persistência da sincronização de batidas. Implementada por
 * `SupabaseBatidaRepository` (produção, supabase-js + service_role) e por um
 * repositório em memória em batida-sync.test.ts.
 *
 * Todo método de escrita recebe um ARRAY e faz UM upsert/delete/insert em
 * lote — nunca uma chamada por item (mesma disciplina de performance de
 * cadastro-sync.ts / SyncRepository).
 */
export interface BatidaSyncRepository {
  /** Leitura em lote — nunca uma consulta por funcionário. */
  listFuncionariosBySecullumIds(secullumFuncionarioIds: number[]): Promise<FuncionarioLookupRow[]>;
  /** Leitura em lote do estado ATUAL de "Batida", restrita a (funcionarioIds, dataInicio..dataFim). */
  listBatidas(
    funcionarioIds: string[],
    dataInicio: string,
    dataFim: string,
  ): Promise<ExistingBatidaRow[]>;
  /** Upsert em lote por (funcionario_id, "Data"). */
  upsertBatidas(inputs: UpsertBatidaInput[]): Promise<BatidaRow[]>;

  /** Leitura em lote do estado ATUAL de batida_marcacao para as "Batida" tocadas nesta execução. */
  listMarcacoesByBatidaIds(batidaIds: string[]): Promise<ExistingMarcacaoRow[]>;
  /** Upsert em lote por (batida_id, tipo_coluna, indice_coluna). */
  upsertMarcacoes(inputs: UpsertMarcacaoInput[]): Promise<MarcacaoRow[]>;
  /** DELETE em lote de convergência — slots que sumiram do Secullum desde a última sincronização do dia. */
  deleteMarcacoesByIds(ids: string[]): Promise<void>;

  /** DELETE em lote de "BatidaFonteDados" no escopo das "Batida" tocadas nesta execução (ANTES do INSERT do conjunto novo). */
  deleteFonteDadosByBatidaIds(batidaIds: string[]): Promise<void>;
  /** INSERT em lote (nunca upsert — sem diffing item a item, mesmo padrão de "HorarioDescansoFaixaItem"). */
  insertFonteDados(inputs: InsertFonteDadosInput[]): Promise<void>;

  /** `cursor_sincronizacao` — só rastreio/diagnóstico, NUNCA usado para calcular a próxima janela. */
  setCursor(chave: string, valor: string): Promise<void>;

  /**
   * Roda `work` numa transação, com um repositório ligado a ela. Ou tudo
   * commita, ou nada — ver o comentário em `SupabaseBatidaRepository`.
   */
  transaction<T>(work: (tx: BatidaSyncRepository) => Promise<T>): Promise<T>;
}

// `SyncScope` morou aqui enquanto a `sync-batidas` era a única a escrever o
// diário. Passou para `sync-run.ts`, junto da reivindicação e do fechamento, e
// continua reexportado daqui porque é deste módulo que `run-options.ts` o
// importa.
export type { SyncScope };

/**
 * A origem devolveu registros e **nenhum** deles encontrou funcionário local.
 *
 * É o risco 3 do §4b: `resolvedItems` vazio com `batidasFetched > 0` significa
 * correlação quebrada — o cadastro não sincronizou, ou os ids mudaram —, e o
 * código antigo respondia HTTP 200 `{ok: true}` com zero batidas gravadas. A
 * sincronização estava parada e o único sinal era um aviso dentro de um JSON que
 * ninguém lia. Janela genuinamente vazia (a origem devolveu zero) continua sendo
 * sucesso, e por isso a condição olha `batidasFetched`, não `resolvedItems`.
 */
export class BatidaCorrelationBrokenError extends Error {
  readonly summary: BatidaSyncSummary;

  constructor(summary: BatidaSyncSummary) {
    super(
      `Correlação quebrada: ${summary.batidasFetched} registro(s) lido(s) da origem e ` +
        `nenhum com "Funcionario" local correspondente ` +
        `(${summary.batidasSkippedMissingFuncionario} pulado(s)). Nada foi gravado.`,
    );
    this.name = "BatidaCorrelationBrokenError";
    this.summary = summary;
  }
}

// ---------------------------------------------------------------------------
// Logger mínimo (nunca deve receber PII — só ids/estrutura/contadores).
// ---------------------------------------------------------------------------
export interface SyncWarning {
  code: string;
  message: string;
}

export interface SyncLogger {
  warn(message: string): void;
  info(message: string): void;
}

export const consoleBatidaSyncLogger: SyncLogger = {
  warn: (m) => console.warn(`[sync-batidas] ${m}`),
  info: (m) => console.info(`[sync-batidas] ${m}`),
};

export interface BatidaSyncSummary {
  /** Qual passada produziu este resumo — a mesma palavra que `app.sync_run.scope`. */
  scope: SyncScope;
  /** Janela efetivamente lida, para o registro de execução dizer o que foi coberto. */
  windowDays: number;
  batidasFetched: number;
  batidasUpserted: number;
  batidasSkippedMissingFuncionario: number;
  /** Contagem de pares (funcionario_id, "Data") cujo "BatidaId" divergiu do já gravado — ANOMALIA, não falha. */
  batidaIdMismatches: number;
  marcacoesUpserted: number;
  marcacoesDeleted: number;
  fonteDadosInserted: number;
  warnings: SyncWarning[];
}

function emptySummary(scope: SyncScope, windowDays: number): BatidaSyncSummary {
  return {
    scope,
    windowDays,
    batidasFetched: 0,
    batidasUpserted: 0,
    batidasSkippedMissingFuncionario: 0,
    batidaIdMismatches: 0,
    marcacoesUpserted: 0,
    marcacoesDeleted: 0,
    fonteDadosInserted: 0,
    warnings: [],
  };
}

/** Mesmo teto de cadastro-sync.ts (WARNING_SAMPLE_CAP) — protege memória/log contra um cadastro com muitas ocorrências do mesmo aviso. */
const WARNING_SAMPLE_CAP = 50;

/** Chave do cursor de rastreio (semeada com `null` pela migration 20260813163000). */
export const BATIDAS_CURSOR_KEY = "batidas_ultima_data_sincronizada";

/**
 * Padrão da janela deslizante incremental, em dias antes de "hoje".
 *
 * Deixou de ser o tamanho fixo e passou a ser só o padrão: a janela é
 * configuração (`BATIDAS_WINDOW_DAYS` no ambiente da função) e a passada de
 * backfill usa `BACKFILL_WINDOW_DAYS`. Enquanto era constante, qualquer queda
 * que passasse de 48 h deixava um buraco de batidas que **nenhum caminho de
 * código conseguia preencher** — risco 2 do §4b.
 */
export const BATIDAS_WINDOW_DAYS = 2;

/**
 * Janela da passada retroativa diária, em dias. Sete, porque é o que a
 * `SPEC-TECNICA.md` contrata: correção feita na origem até D-7 tem de virar
 * revogação do indício já emitido.
 */
export const BACKFILL_WINDOW_DAYS = 7;

/** Intervalo documentado de `FonteDados.Tipo` (Original=0..Desconsiderado=3) — fora disso é tolerado, mas logado como valor desconhecido. */
const DOCUMENTED_TIPO_MAX = 3;
/** Intervalo documentado de `FonteDados.Origem` (0..8) — `11` já visto em produção (não bloqueia). */
const DOCUMENTED_ORIGEM_MAX = 8;

// ---------------------------------------------------------------------------
// Janela deslizante — SEMPRE hoje-2..hoje, nunca calculada a partir do
// cursor (que é só diagnóstico). `today` injetável (TodayProvider) para
// controle de data nos testes, mesmo padrão de cadastro-sync.ts.
// ---------------------------------------------------------------------------

/**
 * Calcula `{ dataInicio, dataFim }` da janela deslizante a partir de um
 * "hoje" já resolvido em America/Sao_Paulo ("yyyy-MM-dd" — ver
 * `systemTodayInSaoPaulo`). A subtração de dias é feita em aritmética UTC
 * PURA sobre um valor de calendário já conhecido (não uma conversão de fuso
 * de um instante) — não é a mesma armadilha documentada para `Data` de
 * `/Batidas`/`Admissao`/`Demissao` (essa armadilha é converter um INSTANTE
 * ambíguo; aqui não há instante nenhum envolvido, só aritmética de
 * calendário sobre uma string "yyyy-MM-dd" já correta).
 */
export function computeBatidasDateRange(
  todayStr: string,
  windowDays: number = BATIDAS_WINDOW_DAYS,
): { dataInicio: string; dataFim: string } {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(todayStr);
  // Defensivo: `todayStr` sempre vem de um TodayProvider no formato
  // "yyyy-MM-dd", mas um provider customizado (ex.: em teste) não deve
  // derrubar o job por formato inesperado.
  if (!match) return { dataInicio: todayStr, dataFim: todayStr };
  const [, year, month, day] = match;
  const base = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  base.setUTCDate(base.getUTCDate() - windowDays);
  const pad = (n: number, len = 2) => n.toString().padStart(len, "0");
  const dataInicio = `${pad(base.getUTCFullYear(), 4)}-${pad(base.getUTCMonth() + 1)}-${
    pad(base.getUTCDate())
  }`;
  return { dataInicio, dataFim: todayStr };
}

// ---------------------------------------------------------------------------
// Parsing de um slot (EntradaN/SaidaN) — os "3 estados" do ADR-007.
// ---------------------------------------------------------------------------

export interface ParsedFonteDados {
  nsr: string | null;
  hora: string | null;
  data: string | null;
  dataInclusao: string | null;
  tipo: number | null;
  origem: number | null;
}

export interface ParsedMarcacaoSlot {
  tipoColuna: SlotTipoColuna;
  indiceColuna: number;
  /** Literal de EntradaN/SaidaN, preservado como veio — único campo que garante fidelidade ao payload. */
  valorBruto: string | null;
  /** Preenchido só quando valorBruto é "HH:mm" válido. */
  hora: string | null;
  /** Preenchido só quando valorBruto é texto de status (não "HH:mm", não vazio). Mutuamente exclusivo com `hora`. */
  statusRotulo: string | null;
  /** Horário PREVISTO do dia (MemoriaEntradaN/SaidaN) — atalho de diagnóstico, nunca fonte de tolerância. */
  memoria: string | null;
  equipId: number | null;
  /** Atributo (não chave) — pode faltar mesmo em coluna preenchida (buraco conhecido do ADR-007). */
  fonteDadosId: number | null;
  fonteDados: ParsedFonteDados | null;
  /** Derivado de fonteDados.tipo === 3 (Desconsiderado). */
  desconsiderada: boolean;
}

/** Callback de aviso de enum desconhecido — dedupe fica a cargo do chamador (orquestrador). */
export type OnUnknownEnumValue = (field: "Tipo" | "Origem", value: number) => void;

export function parseFonteDados(
  raw: RawFonteDados | null | undefined,
  onUnknownEnumValue?: OnUnknownEnumValue,
): ParsedFonteDados | null {
  if (raw === null || raw === undefined || typeof raw !== "object") return null;

  const tipo = asNumber(raw.Tipo);
  if (tipo !== null && (tipo < 0 || tipo > DOCUMENTED_TIPO_MAX)) {
    onUnknownEnumValue?.("Tipo", tipo);
  }
  const origem = asNumber(raw.Origem);
  if (origem !== null && (origem < 0 || origem > DOCUMENTED_ORIGEM_MAX)) {
    onUnknownEnumValue?.("Origem", origem);
  }

  return {
    nsr: asTextPassthrough(raw.Nsr),
    hora: parseHorarioDiaTimeField(raw.Hora),
    data: parseSecullumDateOnly(raw.Data),
    // ISO com ms — passado adiante como veio (coluna timestamptz), nunca
    // reconstruído via `new Date()`/`toISOString()`.
    dataInclusao: typeof raw.DataInclusao === "string" && raw.DataInclusao.length > 0
      ? raw.DataInclusao
      : null,
    tipo,
    origem,
  };
}

const SLOT_DEFS: ReadonlyArray<{ tipoColuna: SlotTipoColuna; indiceColuna: number }> = [
  { tipoColuna: "Entrada", indiceColuna: 1 },
  { tipoColuna: "Entrada", indiceColuna: 2 },
  { tipoColuna: "Entrada", indiceColuna: 3 },
  { tipoColuna: "Entrada", indiceColuna: 4 },
  { tipoColuna: "Entrada", indiceColuna: 5 },
  { tipoColuna: "Saida", indiceColuna: 1 },
  { tipoColuna: "Saida", indiceColuna: 2 },
  { tipoColuna: "Saida", indiceColuna: 3 },
  { tipoColuna: "Saida", indiceColuna: 4 },
  { tipoColuna: "Saida", indiceColuna: 5 },
];

/**
 * Parseia um slot posicional (ex.: "Entrada3"). Retorna `null` quando o slot
 * não carrega NENHUMA informação (valor E Memoria E EquipId E FonteDadosId E
 * FonteDados todos ausentes) — alteração (B) ao ADR-007: colunas com
 * QUALQUER informação viram linha, não só as com batida efetiva (senão
 * perde-se o sinal de BATIDA FALTANTE: Memoria presente + hora nula).
 */
export function parseMarcacaoSlot(
  raw: RawBatida,
  tipoColuna: SlotTipoColuna,
  indiceColuna: number,
  onUnknownEnumValue?: OnUnknownEnumValue,
): ParsedMarcacaoSlot | null {
  const suffix = `${tipoColuna}${indiceColuna}`;
  const rawValue = raw[suffix];
  const rawMemoria = raw[`Memoria${suffix}`];
  const rawEquipId = raw[`EquipId${suffix}`];
  const rawFonteDadosId = raw[`FonteDadosId${suffix}`];
  const rawFonteDados = raw[`FonteDados${suffix}`] as RawFonteDados | null | undefined;

  const valorBruto = typeof rawValue === "string" && rawValue.length > 0 ? rawValue : null;
  const hora = parseHorarioDiaTimeField(rawValue);
  // Mutuamente exclusivo com `hora`: só existe quando havia valor E não era "HH:mm".
  const statusRotulo = valorBruto !== null && hora === null ? valorBruto : null;
  const memoria = parseHorarioDiaTimeField(rawMemoria);
  const equipId = asNumber(rawEquipId);
  const fonteDadosId = asNumber(rawFonteDadosId);
  const fonteDados = parseFonteDados(rawFonteDados, onUnknownEnumValue);

  const hasAnyInformation = valorBruto !== null || memoria !== null || equipId !== null ||
    fonteDadosId !== null || fonteDados !== null;
  if (!hasAnyInformation) return null;

  return {
    tipoColuna,
    indiceColuna,
    valorBruto,
    hora,
    statusRotulo,
    memoria,
    equipId,
    fonteDadosId,
    fonteDados,
    desconsiderada: fonteDados?.tipo === 3,
  };
}

// ---------------------------------------------------------------------------
// Parsing de um item completo de /Batidas (registro-dia).
// ---------------------------------------------------------------------------

export interface ParsedBatidaItem {
  secullumFuncionarioId: number;
  secullumBatidaId: number;
  /** "yyyy-MM-dd". */
  data: string;
  observacoes: string | null;
  ajuste: string | null;
  abono2: string | null;
  abono3: string | null;
  abono4: string | null;
  compensado: boolean;
  almocoLivre: boolean;
  neutro: boolean;
  nBanco: boolean;
  folga: boolean;
  refeicao: boolean;
  /** Primeiro statusRotulo não nulo encontrado entre os slots (ordem Entrada1..5, Saida1..5) — decisão de menor porte, ver relatório da tarefa. */
  statusDiaRotulo: string | null;
  slots: ParsedMarcacaoSlot[];
}

export interface ParseBatidaItemCallbacks {
  onUnknownEnumValue?: OnUnknownEnumValue;
  onUnexpectedBooleanFormat?: (field: string, typeReceived: string) => void;
  /** Chamado quando `raw.Data` não começa com "yyyy-MM-dd" — o item inteiro é descartado (defensivo, não deve ocorrer na prática). */
  onInvalidDate?: (rawValue: unknown) => void;
}

/**
 * Parseia um item de `/Batidas` (registro-dia). Retorna `null` só no caso
 * defensivo de `Data` vir em formato inesperado (o item não pode ser
 * gravado sem uma data válida) — nunca lança exceção.
 */
export function parseBatidaItem(
  raw: RawBatida,
  callbacks: ParseBatidaItemCallbacks = {},
): ParsedBatidaItem | null {
  const data = parseSecullumDateOnly(raw.Data);
  if (data === null) {
    callbacks.onInvalidDate?.(raw.Data);
    return null;
  }

  const boolField = (fieldName: string, rawValue: unknown): boolean =>
    asBoolean(
      rawValue,
      (typeReceived) => callbacks.onUnexpectedBooleanFormat?.(fieldName, typeReceived),
    ) ??
      false;

  const slots: ParsedMarcacaoSlot[] = [];
  let statusDiaRotulo: string | null = null;
  for (const { tipoColuna, indiceColuna } of SLOT_DEFS) {
    const slot = parseMarcacaoSlot(raw, tipoColuna, indiceColuna, callbacks.onUnknownEnumValue);
    if (!slot) continue;
    slots.push(slot);
    if (statusDiaRotulo === null && slot.statusRotulo !== null) {
      statusDiaRotulo = slot.statusRotulo;
    }
  }

  return {
    secullumFuncionarioId: raw.FuncionarioId,
    secullumBatidaId: raw.Id,
    data,
    // ⚠️ Texto livre — asString preserva o literal; NUNCA usado em warn()/log
    // pelo orquestrador abaixo (ver docs/06-seguranca-lgpd.md).
    observacoes: asString(raw.Observacoes),
    ajuste: asTextPassthrough(raw.Ajuste),
    abono2: asTextPassthrough(raw.Abono2),
    abono3: asTextPassthrough(raw.Abono3),
    abono4: asTextPassthrough(raw.Abono4),
    compensado: boolField("Compensado", raw.Compensado),
    almocoLivre: boolField("AlmocoLivre", raw.AlmocoLivre),
    neutro: boolField("Neutro", raw.Neutro),
    nBanco: boolField("NBanco", raw.NBanco),
    folga: boolField("Folga", raw.Folga),
    refeicao: boolField("Refeicao", raw.Refeicao),
    statusDiaRotulo,
    slots,
  };
}

// ---------------------------------------------------------------------------
// Orquestrador principal.
// ---------------------------------------------------------------------------

export async function runBatidaSync(
  secullum: SecullumReader,
  repo: BatidaSyncRepository,
  logger: SyncLogger = consoleBatidaSyncLogger,
  today: TodayProvider = systemTodayInSaoPaulo,
  windowDays: number = BATIDAS_WINDOW_DAYS,
  scope: SyncScope = "incremental",
): Promise<BatidaSyncSummary> {
  const summary = emptySummary(scope, windowDays);

  // Aviso com cap por código (ver WARNING_SAMPLE_CAP) — mesma proteção de
  // memória/log de cadastro-sync.ts.
  const warningCounts = new Map<string, number>();
  const warn = (code: string, message: string) => {
    const count = (warningCounts.get(code) ?? 0) + 1;
    warningCounts.set(code, count);
    if (count > WARNING_SAMPLE_CAP) return;
    summary.warnings.push({ code, message });
    logger.warn(message);
  };
  const flushSuppressedWarnings = () => {
    for (const [code, count] of warningCounts) {
      if (count <= WARNING_SAMPLE_CAP) continue;
      const suppressed = count - WARNING_SAMPLE_CAP;
      const message =
        `Aviso "${code}" ocorreu ${count} vez(es) nesta execução — exibidas as primeiras ${WARNING_SAMPLE_CAP}; ` +
        `${suppressed} ocorrência(s) adicional(is) suprimida(s) do log/summary.`;
      summary.warnings.push({ code: `${code}_suppressed_count`, message });
      logger.warn(message);
    }
  };

  const todayStr = today();
  const { dataInicio, dataFim } = computeBatidasDateRange(todayStr, windowDays);
  logger.info(`Sincronizando /Batidas — janela deslizante ${dataInicio}..${dataFim}.`);

  // Única chamada de rede a /Batidas nesta execução — janela de data, sem
  // paginação/cursor por Id (o endpoint não suporta, ver
  // docs/03-integracao-secullum.md).
  const rawBatidas = await secullum.get<RawBatida[]>("Batidas", { dataInicio, dataFim });
  summary.batidasFetched = rawBatidas.length;

  const warnedUnknownEnumValues = new Set<string>();
  const onUnknownEnumValue: OnUnknownEnumValue = (field, value) => {
    const key = `${field}:${value}`;
    if (warnedUnknownEnumValues.has(key)) return;
    warnedUnknownEnumValues.add(key);
    warn(
      "batida_fonte_dados_unknown_enum_value",
      `BatidaFonteDados.${field}=${value}: valor fora do intervalo documentado — persistido bruto, TOLERADO (ver docs/03-integracao-secullum.md, "Origem = 11").`,
    );
  };
  const warnedBooleanFields = new Set<string>();
  const onUnexpectedBooleanFormat = (field: string, typeReceived: string) => {
    if (warnedBooleanFields.has(field)) return;
    warnedBooleanFields.add(field);
    warn(
      "batida_boolean_unexpected_format",
      `Batida.${field}: formato inesperado (tipo recebido: ${typeReceived}) — gravado como false.`,
    );
  };
  let invalidDateCount = 0;
  const onInvalidDate = () => {
    invalidDateCount++;
  };

  const parsedItems: ParsedBatidaItem[] = [];
  for (const raw of rawBatidas) {
    const parsed = parseBatidaItem(raw, {
      onUnknownEnumValue,
      onUnexpectedBooleanFormat,
      onInvalidDate,
    });
    if (parsed) parsedItems.push(parsed);
  }
  if (invalidDateCount > 0) {
    warn(
      "batida_invalid_data_field",
      `${invalidDateCount} registro(s) de /Batidas com campo "Data" em formato inesperado — não sincronizados.`,
    );
  }

  // 1) Correlação FuncionarioId -> "Funcionario".id — leitura em lote, uma
  // única consulta filtrando pelos FuncionarioId presentes neste lote (nunca
  // uma consulta por funcionário).
  const secullumFuncionarioIds = [...new Set(parsedItems.map((p) => p.secullumFuncionarioId))];
  const funcionarioRows = secullumFuncionarioIds.length
    ? await repo.listFuncionariosBySecullumIds(secullumFuncionarioIds)
    : [];
  const funcionarioUuidBySecullumId = new Map(
    funcionarioRows.map((f) => [f.secullumFuncionarioId, f.id]),
  );

  const missingFuncionarioIds = new Set<number>();
  const resolvedItems: Array<{ parsed: ParsedBatidaItem; funcionarioId: string }> = [];
  for (const parsed of parsedItems) {
    const funcionarioId = funcionarioUuidBySecullumId.get(parsed.secullumFuncionarioId);
    if (!funcionarioId) {
      missingFuncionarioIds.add(parsed.secullumFuncionarioId);
      summary.batidasSkippedMissingFuncionario++;
      continue;
    }
    resolvedItems.push({ parsed, funcionarioId });
  }
  if (missingFuncionarioIds.size > 0) {
    warn(
      "batida_funcionario_not_found",
      `${missingFuncionarioIds.size} FuncionarioId(s) de /Batidas sem "Funcionario" local correspondente ` +
        `(${summary.batidasSkippedMissingFuncionario} registro(s)-dia pulado(s)) — funcionário ainda não sincronizado ou removido.`,
    );
  }

  if (resolvedItems.length === 0) {
    flushSuppressedWarnings();
    // Janela vazia é sucesso; janela cheia que não correlacionou com ninguém
    // não é. Ver BatidaCorrelationBrokenError.
    if (summary.batidasFetched > 0) throw new BatidaCorrelationBrokenError(summary);
    return summary;
  }

  // 2) "Batida" — leitura em lote do estado ATUAL no escopo (funcionários x
  // janela) ANTES do upsert, para detectar divergência de "BatidaId"
  // (anomalia) sem um SELECT por par (funcionario_id, Data).
  const distinctFuncionarioUuids = [...new Set(resolvedItems.map((r) => r.funcionarioId))];
  const existingBatidas = await repo.listBatidas(distinctFuncionarioUuids, dataInicio, dataFim);
  const existingBatidaByKey = new Map(
    existingBatidas.map((b) => [`${b.funcionarioId}|${b.data}`, b]),
  );

  for (const { parsed, funcionarioId } of resolvedItems) {
    const existing = existingBatidaByKey.get(`${funcionarioId}|${parsed.data}`);
    if (
      existing && existing.secullumBatidaId !== null &&
      existing.secullumBatidaId !== parsed.secullumBatidaId
    ) {
      summary.batidaIdMismatches++;
      warn(
        "batida_id_mismatch",
        `Batida funcionario_id=${funcionarioId} Data=${parsed.data}: "BatidaId" divergente entre execuções ` +
          `(anterior=${existing.secullumBatidaId}, novo=${parsed.secullumBatidaId}) — ANOMALIA logada; ` +
          `(funcionario_id, "Data") continua sendo a chave de idempotência (ADR-007/ADR-011).`,
      );
    }
  }

  const upsertBatidaInputs: UpsertBatidaInput[] = resolvedItems.map((
    { parsed, funcionarioId },
  ) => ({
    funcionarioId,
    secullumFuncionarioId: parsed.secullumFuncionarioId,
    secullumBatidaId: parsed.secullumBatidaId,
    data: parsed.data,
    observacoes: parsed.observacoes,
    ajuste: parsed.ajuste,
    abono2: parsed.abono2,
    abono3: parsed.abono3,
    abono4: parsed.abono4,
    compensado: parsed.compensado,
    almocoLivre: parsed.almocoLivre,
    neutro: parsed.neutro,
    nBanco: parsed.nBanco,
    folga: parsed.folga,
    refeicao: parsed.refeicao,
    statusDiaRotulo: parsed.statusDiaRotulo,
  }));
  // A fase de escrita inteira numa transação só. São dois pontos de falha
  // parcial documentados no §4b e eles têm a mesma cura: `upsertBatidas`
  // commitava antes de `listMarcacoesByBatidaIds`, e `deleteFonteDadosByBatidaIds`
  // commitava antes de `insertFonteDados`. O primeiro deixava `Batida` com zero
  // marcação, que o motor lê como "não bateu ponto"; o segundo apagava a
  // fonte-de-dados e não repunha. Nenhum dos dois é alcançável a partir daqui.
  await repo.transaction(async (tx) => {
    const batidaRows = await tx.upsertBatidas(upsertBatidaInputs);
    summary.batidasUpserted = batidaRows.length;
    const batidaRowByKey = new Map(batidaRows.map((b) => [`${b.funcionarioId}|${b.data}`, b]));

    // 3) batida_marcacao — substituição integral do dia: upsert das colunas
    // presentes + DELETE das que deixaram de existir. Todas as "Batida"
    // tocadas nesta execução (batidaRows) entram no escopo da convergência —
    // é sempre o registro-dia inteiro, nunca um slot isolado.
    const touchedBatidaIds = batidaRows.map((b) => b.id);
    const existingMarcacoes = touchedBatidaIds.length
      ? await tx.listMarcacoesByBatidaIds(touchedBatidaIds)
      : [];

    const upsertMarcacaoInputs: UpsertMarcacaoInput[] = [];
    const newMarcacaoKeys = new Set<string>();
    // Guarda o slot original (com fonteDados/fonteDadosId) por chave — usado
    // DEPOIS do upsert de batida_marcacao para montar "BatidaFonteDados", que
    // precisa do uuid gerado de batida_marcacao.
    const slotByMarcacaoKey = new Map<string, ParsedMarcacaoSlot>();

    for (const { parsed, funcionarioId } of resolvedItems) {
      const batidaRow = batidaRowByKey.get(`${funcionarioId}|${parsed.data}`);
      if (!batidaRow) continue; // defensivo — todo item enviado no lote acima está no mapa de retorno.
      for (const slot of parsed.slots) {
        const key = `${batidaRow.id}|${slot.tipoColuna}|${slot.indiceColuna}`;
        newMarcacaoKeys.add(key);
        slotByMarcacaoKey.set(key, slot);
        upsertMarcacaoInputs.push({
          batidaId: batidaRow.id,
          funcionarioId,
          data: parsed.data,
          tipoColuna: slot.tipoColuna,
          indiceColuna: slot.indiceColuna,
          valorBruto: slot.valorBruto,
          hora: slot.hora,
          statusRotulo: slot.statusRotulo,
          memoria: slot.memoria,
          equipId: slot.equipId,
          fonteDadosId: slot.fonteDadosId,
          desconsiderada: slot.desconsiderada,
        });
      }
    }

    const marcacaoRows = upsertMarcacaoInputs.length
      ? await tx.upsertMarcacoes(upsertMarcacaoInputs)
      : [];
    summary.marcacoesUpserted = marcacaoRows.length;

    const marcacaoIdsToDelete = existingMarcacoes
      .filter((m) => !newMarcacaoKeys.has(`${m.batidaId}|${m.tipoColuna}|${m.indiceColuna}`))
      .map((m) => m.id);
    if (marcacaoIdsToDelete.length) {
      await tx.deleteMarcacoesByIds(marcacaoIdsToDelete);
      summary.marcacoesDeleted = marcacaoIdsToDelete.length;
    }

    // 4) "BatidaFonteDados" — substituição integral por "Batida" tocada nesta
    // execução: DELETE do que existia + INSERT do conjunto novo (mesmo padrão
    // de "HorarioDescansoFaixaItem"/"HorarioFaixasExtrasItem" em
    // cadastro-sync.ts — sem chave única de negócio própria, e cobre tanto o
    // slot que sumiu (cascata via DELETE de batida_marcacao) quanto o slot que
    // ficou mas perdeu o FonteDados).
    if (touchedBatidaIds.length) {
      await tx.deleteFonteDadosByBatidaIds(touchedBatidaIds);
    }

    const marcacaoIdByKey = new Map(
      marcacaoRows.map((m) => [`${m.batidaId}|${m.tipoColuna}|${m.indiceColuna}`, m.id]),
    );
    const fonteDadosInputs: InsertFonteDadosInput[] = [];
    for (const [key, slot] of slotByMarcacaoKey) {
      if (!slot.fonteDados) continue;
      const marcacaoId = marcacaoIdByKey.get(key);
      if (!marcacaoId) continue; // defensivo — toda marcação foi enviada no lote de upsert acima.
      const batidaId = key.split("|")[0];
      fonteDadosInputs.push({
        batidaMarcacaoId: marcacaoId,
        batidaId,
        fonteDadosId: slot.fonteDadosId,
        nsr: slot.fonteDados.nsr,
        hora: slot.fonteDados.hora,
        data: slot.fonteDados.data,
        dataInclusao: slot.fonteDados.dataInclusao,
        tipo: slot.fonteDados.tipo,
        origem: slot.fonteDados.origem,
      });
    }
    if (fonteDadosInputs.length) {
      await tx.insertFonteDados(fonteDadosInputs);
      summary.fonteDadosInserted = fonteDadosInputs.length;
    }
  });

  // 5) Cursor de rastreio — só diagnóstico (nunca usado para calcular a
  // próxima janela). Atualizado por último, só depois de toda a escrita ter
  // sido bem-sucedida.
  await repo.setCursor(BATIDAS_CURSOR_KEY, todayStr);

  flushSuppressedWarnings();
  return summary;
}
