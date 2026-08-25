// Formato bruto de `GET /Batidas` do Secullum.
//
// ⚠️ ESTE ARQUIVO FOI RECONSTRUÍDO, NÃO RECUPERADO — 25/08/2026
// `batida-sync.ts` sempre o importou, e ele não existia nem aqui nem na nuvem:
// `supabase functions download` (produção, 25/08) baixa os oito módulos da
// função e **não traz este**. O motivo é banal e vale registrar, porque a mesma
// coisa vale para `secullum-cadastro-types.ts`: `import type` é apagado na
// transpilação, então o módulo nunca chega ao runtime e não faz parte do que a
// plataforma guarda. O deploy funciona; o `deno check` não passa; e os tipos da
// integração existiam só na máquina de quem os escreveu.
//
// COMO ELE FOI RECONSTRUÍDO
// Campo a campo, a partir de **cada acesso que o código faz** — não do que a
// documentação da origem promete e não de dedução sobre o Secullum. O
// levantamento é reproduzível:
//
//     grep -o 'raw\.[A-Za-z0-9_]*' _shared/batida-sync.ts | sort -u
//
// A tipagem é permissiva de propósito, e isso não é preguiça: `asNumber`,
// `asBoolean`, `asString`, `asTextPassthrough`, `parseSecullumDateOnly` e
// `parseHorarioDiaTimeField` **todos recebem `unknown`** e validam em runtime.
// Declarar `Compensado: boolean` aqui afirmaria sobre a origem uma garantia que
// o código não assume — e que ninguém pode conferir, porque não existe sandbox
// do Secullum para este cliente (todo teste roda contra produção real). Os dois
// únicos campos com tipo forte são os que o código atribui direto a um `number`.

/** `FonteDados` de um slot — a procedência de uma marcação (NSR, equipamento, ajuste). */
export interface RawFonteDados {
  /** Número Sequencial de Registro do REP. Lido por `asTextPassthrough`. */
  Nsr?: unknown;
  /** "HH:mm". Lido por `parseHorarioDiaTimeField`. */
  Hora?: unknown;
  /** Data da marcação. Lida por `parseSecullumDateOnly`. */
  Data?: unknown;
  /** Data de inclusão no REP. Lida por `parseSecullumDateOnly`. */
  DataInclusao?: unknown;
  /** Original=0..Desconsiderado=3. `Tipo === 3` é o que marca `desconsiderada`. */
  Tipo?: unknown;
  /** 0..8 documentado; `11` já visto em produção e tolerado. */
  Origem?: unknown;
}

/**
 * Um registro-dia de `/Batidas`.
 *
 * A assinatura de índice não é frouxidão: `parseMarcacaoSlot` lê os slots por
 * nome montado (`raw["Entrada1"]`, `raw["MemoriaSaida3"]`, `raw["EquipId..."]`,
 * `raw["FonteDados..."]`), e são 10 slots × 4 campos. Enumerar os 40 daria uma
 * lista que ninguém manteria e que mentiria no dia em que o Secullum acrescentar
 * `Entrada6`.
 */
export interface RawBatida {
  /** `BatidaId` da origem. Atribuído direto a `number`. */
  Id: number;
  /** Atribuído direto a `number` — é a chave de correlação com `secullum."Funcionario"`. */
  FuncionarioId: number;
  /** Data do registro-dia. Lida por `parseSecullumDateOnly`; item sem data válida é descartado. */
  Data?: unknown;
  Observacoes?: unknown;
  Ajuste?: unknown;
  Abono2?: unknown;
  Abono3?: unknown;
  Abono4?: unknown;
  Compensado?: unknown;
  AlmocoLivre?: unknown;
  Neutro?: unknown;
  NBanco?: unknown;
  Folga?: unknown;
  Refeicao?: unknown;
  /** `Entrada1..5`, `Saida1..5` e os acompanhantes `Memoria*`, `EquipId*`, `FonteDadosId*`, `FonteDados*`. */
  [slot: string]: unknown;
}
