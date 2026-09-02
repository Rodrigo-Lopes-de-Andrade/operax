// Motor da sincronização cadastral (Sprint 1): Funcionarios (+ Empresa
// aninhada) -> company/unit/employee (+ manager.name/manager.email),
// Horarios -> work_schedule/work_schedule_day.
//
// Este módulo é deliberadamente independente de runtime (Deno/Supabase): ele
// recebe um client Secullum (qualquer objeto com `.get<T>(path, query)`,
// compatível com `SecullumClient` de secullum-client.ts) e um `SyncRepository`
// (abstração de persistência — ver supabase-repository.ts para a
// implementação real via supabase-js e cadastro-sync.test.ts para a
// implementação em memória usada nos testes). Isso permite testar toda a
// lógica de negócio (resolução de gestor, allow-list de PII, idempotência)
// com fixtures locais, sem Secullum real nem Supabase real.
//
// Regras de negócio implementadas aqui — ver docs/03-integracao-secullum.md
// ("Resolução do gestor"), docs/04-modelo-dados.md e docs/06-seguranca-lgpd.md:
//   - Nenhuma chamada a GET /Estruturas (o objeto Estrutura já vem aninhado
//     em cada Funcionario).
//   - Nenhuma chamada a GET /Empresas (o objeto Empresa já vem aninhado em
//     cada Funcionario) — `company` é derivada de `Funcionario.Empresa`, com
//     a mesma disciplina de deduplicação já usada para `Departamento`/
//     `Estrutura` (chave natural: `Empresa.Documento`, mesma coluna
//     `secullum_documento`/`company_secullum_documento_key` de sempre).
//   - manager.email só é sincronizado com match ÚNICO de nome normalizado; 0
//     ou 2+ matches => abstenção + aviso (nunca escolha arbitrária).
//   - manager.email_source = 'manual' nunca é sobrescrito.
//   - ADR-011 (2026-08-13, Fase 2) — REVERSÃO da minimização de LGPD: employee
//     ("Funcionario") passa a gravar o cadastro COMPLETO (RG, endereço,
//     telefone, celular, e-mail, filiação, nascimento, texto livre incluídos),
//     por decisão explícita do Owner. A allow-list (`parseFuncionarioAllowList`)
//     foi REMOVIDA — `parseFuncionario` extrai todos os campos confirmados na
//     migration `20260813161000_cadastro_captura_completa.sql`. As únicas
//     exceções continuam sendo `SenhaEquipamento` (credencial) e `Foto`
//     (exigiria 6º endpoint) — ver o cabeçalho daquela migration.
//   - Erros não fatais (funcionário sem horário, empresa não encontrada,
//     EstruturaPaiId != 0) viram warnings estruturados, nunca exceção.
//
// ADR-010 (2026-08-13) — GET /FuncionariosAfastamentos (5º e último endpoint
// do escopo), executado DEPOIS de employee (fase 3.c): esta rota não tem
// FuncionarioId, então a correlação com `employee` é feita em memória por
// NumeroPis/Cpf (só em memória, nunca persistidos — mesmo padrão do objeto
// Funcionario aninhado em /Batidas). `Motivo` (texto livre) nunca é lido.
// employee_absence é MUTÁVEL (upsert + DELETE de convergência), ao contrário
// do restante deste módulo — ver docs/adr/ADR-010-afastamentos-ferias.md.
// ⚠️ Chamada com `dataInicio`/`dataFim` OBRIGATÓRIOS (correção de
// 2026-08-13, pós-diagnóstico contra o Secullum real — sem eles a rota
// responde HTTP 400), numa janela FIXA e larga (ver
// `computeAfastamentosDateRange`), não numa janela deslizante.
//
// ⚠️ Regra de performance (incidente de produção 2026-08-12 —
// WORKER_RESOURCE_LIMIT): este módulo grava cada tabela em LOTES (um único
// upsert por tabela, no máximo um por fase), nunca uma chamada de rede por
// linha dentro de um `for`. Com um volume modesto (93 horários x 7 dias, 140
// funcionários) o desenho anterior (um `await repo.upsertX(...)` por item)
// já produzia ~950 idas-e-voltas de rede sequenciais numa única invocação —
// cada uma com custo real de CPU no runtime da Edge Function (montagem da
// query do supabase-js, serialização/parsing de JSON), o suficiente para
// estourar a cota de CPU do runtime mesmo sem nenhuma complexidade
// algorítmica não-linear. Volume de dados desta sincronização cabe
// tranquilamente numa única invocação (ver docs/03-integracao-secullum.md,
// "Volume irrisório... cabe em uma invocação de Edge Function, sem
// paginação") — o problema era só a granularidade das chamadas de rede, não
// o tamanho dos dados.

import { normalizePersonName } from "./text-normalize.ts";
import type {
  RawCentroCusto,
  RawCidade,
  RawEmpresa,
  RawFuncao,
  RawFuncionario,
  RawFuncionarioAfastamento,
  RawHorario,
  RawHorarioDescanso,
  RawHorarioDescansoFaixaItem,
  RawHorarioDia,
  RawHorarioExtras,
  RawHorarioFaixasExtras,
  RawHorarioFaixasExtrasItem,
  RawHorarioOpcoes,
  RawHorarioToleranciaEspecificaItem,
} from "./secullum-cadastro-types.ts";

// ---------------------------------------------------------------------------
// Contrato mínimo exigido do client Secullum (compatível com SecullumClient).
// ---------------------------------------------------------------------------
export interface SecullumReader {
  get<T>(path: string, query?: Record<string, string | undefined>): Promise<T>;
}

// ---------------------------------------------------------------------------
// Linhas / entradas de upsert do repositório (nomes já no domínio interno).
//
// Toda `*Row` abaixo carrega também a chave natural do Secullum (ex.:
// `secullumDocumento`, `secullumRef`) — necessário para mapear a RESPOSTA de
// um upsert em LOTE de volta para cada item de entrada em memória, já que o
// lote não preserva 1:1 "índice de entrada -> índice de saída" (ver upsert
// em lote no Postgres/PostgREST).
// ---------------------------------------------------------------------------
export interface EmpresaRow {
  id: string;
  secullumDocumento: string;
}

/**
 * Estado ATUAL de `company` lido em lote ANTES do upsert (ADR-009) — usado
 * para comparar com o `active` recém-derivado e decidir se um
 * `company_status_event` deve ser gerado (baseline/deactivated/reactivated),
 * sem nunca fazer um SELECT por empresa dentro de um laço.
 */
export interface ExistingEmpresaRow {
  id: string;
  secullumDocumento: string;
  active: boolean;
}

// ---------------------------------------------------------------------------
// "Cidade" / "Funcao" (ADR-011) — nós aninhados compartilhados por
// "Funcionario" e (só "Cidade") por "Empresa". Chave de idempotência:
// "Descricao" (a mesma que o próprio Secullum usa nas rotas Cidades/Funcoes,
// que este projeto não chama). Sem histórico/diffing necessário — um único
// upsert em lote por ciclo é suficiente, sem leitura prévia.
// ---------------------------------------------------------------------------
export interface CidadeRow {
  id: string;
  descricao: string;
}

export interface UpsertCidadeInput {
  descricao: string;
  /** `Cidade.Id` do Secullum, quando presente — atributo, NULLABLE, sem UNIQUE (ver migration). */
  secullumCidadeId: number | null;
}

export interface FuncaoRow {
  id: string;
  descricao: string;
}

export interface UpsertFuncaoInput {
  descricao: string;
  secullumFuncaoId: number | null;
}

// ---------------------------------------------------------------------------
// "FuncionarioCentroCusto" (ADR-011) — array `ListaCentroDeCustos` de
// `Funcionario`. Escrita por SUBSTITUIÇÃO INTEGRAL por funcionário: leitura em
// lote do estado atual, upsert do que veio, DELETE do que sumiu — mesmo
// padrão de `employee_absence` (ADR-010) e da árvore de `Horario` (ADR-011).
// ---------------------------------------------------------------------------
export interface ExistingCentroCustoRow {
  id: string;
  employeeId: string;
  descricao: string;
}

export interface UpsertCentroCustoInput {
  employeeId: string;
  descricao: string;
}

export interface CentroCustoRow {
  id: string;
  employeeId: string;
  descricao: string;
}

export interface DepartamentoRow {
  id: string;
  companyId: string;
  secullumRef: number;
}

export interface HorarioRow {
  id: string;
  secullumHorarioId: number;
}

export interface EstruturaRow {
  id: string;
  secullumEstruturaId: number;
  email: string | null;
  emailSource: "manual" | "secullum";
}

/**
 * ADR-011 (Fase 2) — cadastro completo de "Empresa". Além de
 * `secullumDocumento`/`name`/`active` (já existentes), captura os ~25 campos
 * novos confirmados na migration `20260813161000`. Grande parte deles vem do
 * CADASTRO de Empresas do manual (rota `GET /Empresas`, não chamada por este
 * projeto) e pode permanecer `null` para sempre — isso é esperado, não um bug
 * (ver docs/04-modelo-dados.md §0.5).
 *
 * ⛔ Sem `active`->`ativo`: "Empresa".ativo é coluna GERADA a partir de
 * "Desativada" (ADR-012). O repositório grava "Desativada" = `!active`.
 */
export interface UpsertEmpresaInput {
  secullumDocumento: string;
  name: string;
  active: boolean;
  secullumEmpresaId: number | null;
  inscricao: string | null;
  endereco: string | null;
  bairro: string | null;
  /** NOSSA FK (uuid) -> "Cidade", já resolvida pelo orquestrador antes do upsert de Empresa. */
  cityId: string | null;
  /** `Empresa.Cidade.Id` do Secullum — atributo, ao lado de `cityId`. */
  secullumCidadeId: number | null;
  cep: string | null;
  uf: string | null;
  pais: string | null;
  telefone: string | null;
  fax: string | null;
  cei: string | null;
  nfolhaEmpresa: string | null;
  logotipo: string | null;
  possuiLogo: boolean | null;
  responsavelNome: string | null;
  responsavelCargo: string | null;
  responsavelEmail: string | null;
  tipoDocumento: number | null;
  utilizaRepC: boolean | null;
  utilizaRepA: boolean | null;
  utilizaRepP: boolean | null;
  usaFechamentoDoPontoEspecifico: boolean | null;
  fechamentoPonto: number | null;
  diaFechamentoPonto: number | null;
  emitiuAtestadoTecnico: boolean | null;
}

export interface UpsertDepartamentoInput {
  secullumRef: number;
  name: string;
  companyId: string;
  active: boolean;
}

/**
 * ⚠️ Sem `usesSpecificTolerance` de propósito (existia até a migration
 * 20260813160000, sob o nome `"UsaToleranciaEspecifica"`): a coluna foi
 * REMOVIDA de `"Horario"` pela migration 20260813162000 — a árvore completa
 * de `Horarios` (`"HorarioToleranciaEspecifica"`) é fase 3 (fora do escopo
 * desta sincronização). O aviso `schedule_uses_specific_tolerance` continua
 * emitido pelo orquestrador (`runCadastroSync`), lido direto do payload cru
 * (`horario.ToleranciaEspecifica?.UsaToleranciaEspecifica`) — não depende de
 * nenhum campo persistido aqui.
 */
export interface UpsertHorarioInput {
  secullumHorarioId: number;
  secullumHorarioNumero: number | null;
  description: string | null;
  active: boolean;
}

export interface UpsertHorarioDiaInput {
  workScheduleId: string;
  secullumHorarioDiaId: number;
  weekday: number;
  entry1: string | null;
  entry2: string | null;
  entry3: string | null;
  entry4: string | null;
  entry5: string | null;
  exit1: string | null;
  exit2: string | null;
  exit3: string | null;
  exit4: string | null;
  exit5: string | null;
  entryType1: number | null;
  entryType2: number | null;
  entryType3: number | null;
  entryType4: number | null;
  entryType5: number | null;
  exitType1: number | null;
  exitType2: number | null;
  exitType3: number | null;
  exitType4: number | null;
  exitType5: number | null;
  toleranceExtraMinutes: number | null;
  toleranceAbsenceMinutes: number | null;
  workloadMinutes: number | null;
  dayType: number | null;
  isNeutral: boolean;
  isCompensated: boolean;
  freeLunch: boolean;
  allocate24Hours: boolean;
  isDayOff: boolean;
}

// ---------------------------------------------------------------------------
// Árvore completa de "Horario" (ADR-011 Fase 3, migration 20260813162000):
// "HorariosOpcoes" / "HorarioExtras" / "HorarioDescanso"(+Faixas) /
// "HorarioFaixasExtras"(+Faixas) / "HorarioToleranciaEspecifica"(+Tolerancias).
//
// ⛔ CAPTURAR NAO E USAR — nenhum campo aqui alimenta o motor de deteccao
// (Sprint 2 continua exclusivamente com "HorarioDia"."ToleranciaExtra"/
// "ToleranciaFalta"). Ver o cabecalho da migration.
//
// Padrao de escrita (herdado da migration, nao redecidido aqui):
//   - "HorariosOpcoes"/"HorarioExtras"/"HorarioDescanso"/
//     "HorarioToleranciaEspecifica" sao 1:1 (constraint UNIQUE em horario_id)
//     -> upsert em lote por horario_id, SEM delete (o upsert ja substitui o
//     conteudo da unica linha).
//   - "HorarioDescansoFaixaItem"/"HorarioFaixasExtrasItem"/
//     "HorarioToleranciaEspecificaItem" (tabelas *Item*) E
//     "HorarioFaixasExtras" (o proprio grupo por "Dia Semana") NAO tem chave
//     unica de negocio (nenhum item tem id estavel confirmado na origem) ->
//     SUBSTITUICAO INTEGRAL por pai a cada ciclo: DELETE por id(s) do pai
//     tocado(s) nesta execucao + INSERT do conjunto novo — nunca upsert/diff.
//     Mesma disciplina de "FuncionarioCentroCusto" (ADR-011)/employee_absence
//     (ADR-010), adaptada para o caso sem chave natural nenhuma.
// ---------------------------------------------------------------------------

/** `Horario.Opcoes` -> "HorariosOpcoes" (54 campos incl. horario_id/HorarioId). Todo campo normalizado defensivamente (nenhum valor cru repassado). */
export interface UpsertHorariosOpcoesInput {
  horarioId: string;
  secullumHorarioId: number | null;
  toleranciaArtigo58: boolean | null;
  ignorarLimiteMinimoCasoBatidaGerarExtrasSuperiorATolerancia: boolean | null;
  ignorarLimiteMinimoCasoBatidaGerarFaltasSuperiorATolerancia: boolean | null;
  qualquerMinutoAdiantadoComoExtra: boolean | null;
  qualquerMinutoAtrasadoComoFalta: boolean | null;
  descontarToleranciaDasHorasExtras: boolean | null;
  descontarToleranciaDasHorasFaltas: boolean | null;
  usarToleranciaRefeicoes: boolean | null;
  toleranciaRefeicoesMinutos: number | null;
  limiteMinimoDeFaltasNoDiaMinutos: number | null;
  limiteMinimoDeExtrasNoDiaMinutos: number | null;
  substituirBatidasAbaixoDasTolerancias: boolean | null;
  alocarHorario24Horas: boolean | null;
  /** Enum bruto, semântica não documentada — `integer` sem CHECK (ver migration). */
  alocarBatidas: number | null;
  naoDescontarFaltasDeNormais: boolean | null;
  preencherFaltasQuandoDiaEstiverEmBranco: boolean | null;
  tipoPreencherQuandoDiaEstiverEmBranco: number | null;
  calcularFaltasSomenteParaDiaInteiro: boolean | null;
  exibirColunaHorasRepousoFaltantesTrabalhoContinuo: boolean | null;
  horasRepousoConfiguracaoPadrao: boolean | null;
  /** jsonb genérico — shape não confirmado, grava o valor bruto tal como veio. */
  horasRepousoFaixas: JsonDesconhecido;
  completarBatidasFaltantes: boolean | null;
  permitirFolgasAutomaticas: boolean | null;
  quantidadeFolgasAutomaticas: number | null;
  colunasRefeicao: number | null;
  sinalizarEmVermelhoAlmocosCurtos: boolean | null;
  naoCalcularNenhumaHoraNoturna: boolean | null;
  separarHorasNoturnasDeHorasNormais: boolean | null;
  incluirIntervaloNoAdicionalNoturno: boolean | null;
  /** Texto(5) "HH:mm" — mantido TEXT (não `time`), nunca comparado com hora de batida por este sistema. */
  periodoEspecialAdicionalNoturnoInicio: string | null;
  periodoEspecialAdicionalNoturnoFim: string | null;
  considerarFeriadosComoHoraExtra: boolean | null;
  usarTempoMaisMenosCargaSuperior: boolean | null;
  percentualCargaUsarTempoMaisMenosMinutos: number | null;
  definirCargaAutomaticamente: boolean | null;
  /** Carga no nível do HORÁRIO — não confundir com "HorarioDia"."Carga" (nível dia). */
  carga: number | null;
  desconsiderarNeutroQuandoHouverBatidasNoDia: boolean | null;
  usarDataFechamentoEncerrarSemana: boolean | null;
  /** ⏳ Tipo não observado (veio `null`) — enum bruto, `smallint` nullable. */
  compensacao: number | null;
  compensacaoIgnorarSabados: boolean | null;
  compensacaoIgnorarDomingos: boolean | null;
  compensacaoIgnorarFeriados: boolean | null;
  compensacaoIgnorarFolgas: boolean | null;
  /** jsonb genérico — shape não confirmado. */
  compensacaoMensalFechamento: JsonDesconhecido;
  compensacaoCalcularHorasComoNormaisCompatibilidadePontoOff: boolean | null;
  calcularNoturnasIndependenteCompensado: boolean | null;
  calcularBatidasIntermediarias: boolean | null;
  naoCalcularHorasFaltaBatidasIntermediarias: boolean | null;
  /** jsonb genérico — shape não confirmado (veio `[]`). */
  listaHorasSobreAviso: JsonDesconhecido;
  calcularHorasInItinere: boolean | null;
  /** jsonb genérico — shape não confirmado (veio `[]`). */
  listaHorasInItinere: JsonDesconhecido;
  somarHorasInItinereNormais: boolean | null;
  calcularHorasInItinereIninterruptas: boolean | null;
}

/** `Horario.Extras` -> "HorarioExtras" (31 campos incl. horario_id/HorarioId). */
export interface UpsertHorarioExtrasInput {
  horarioId: string;
  secullumHorarioId: number | null;
  agruparExtras: boolean | null;
  somenteGrupoExtras: boolean | null;
  /** Enum bruto (MaisSignificativas=0, MenosSignificativas=1), `smallint` sem CHECK. */
  descontarFaltasExtras: number | null;
  descontarFaltasExtrasNoturnas: boolean | null;
  descontarIgnorarUteis: boolean | null;
  descontarIgnorarSabados: boolean | null;
  descontarIgnorarDomingos: boolean | null;
  descontarIgnorarFeriados: boolean | null;
  descontarIgnorarFolgas: boolean | null;
  descontarIgnorarDiaEspecial: boolean | null;
  usarInterjornada: boolean | null;
  /** ⚠️⚠️ Divergência confirmada do manual — valor real é STRING (não boolean). Mantido TEXT. */
  interjornada: string | null;
  interjornadaSeparada: boolean | null;
  interjornadaSeparadaBancoHoras: boolean | null;
  separarExtrasNoturnasDeExtrasNormais: boolean | null;
  separarExtrasIntervalosDeExtrasNormais: boolean | null;
  separarSomatoriaAposMeiaNoite: boolean | null;
  multiplicarExtrasPeloPercentual: boolean | null;
  habilitarMultiplicadorFaixaBancoHoras: boolean | null;
  multiplicarSomenteSaldoPositivo: boolean | null;
  naoDividirExtrasEmFeriados: boolean | null;
  naoDividirExtrasEmDomingos: boolean | null;
  dividirJornadaQuandoHouverFolga: boolean | null;
  naoDividirJornadaEmFeriados: boolean | null;
  naoDividirJornadaEmFolgas: boolean | null;
  apenasDividirJornadaFeriadoFolgaDiaSeguinte: boolean | null;
  naoReiniciarDivisoesExtrasDiurnasNoturnas: boolean | null;
  /** ⚠️ Regra de FOLHA — o motor de detecção NUNCA filtra desvio por esta regra (ver migration). */
  controleHorasExtrasAutorizadas: boolean | null;
  /** Texto "HH:mm" — DURAÇÃO, mantido TEXT. */
  quantidadeExtrasAutorizadas: string | null;
  /** Enum bruto 0..8, `smallint` sem CHECK. */
  acumulo: number | null;
}

/** `Horario.Descanso` -> "HorarioDescanso" (1:1, regras de DSR). */
export interface UpsertHorarioDescansoInput {
  horarioId: string;
  secullumHorarioId: number | null;
  /** Enum bruto (Automatico=0, Variavel=1). */
  tipo: number | null;
  /** Texto(5) HH:mm — DURAÇÃO (valor do DSR), mantido TEXT. */
  valorDescanso: string | null;
  limiteHorasFaltas: string | null;
  /** Enum bruto (DescansoDomingo=0, DescansoDia=1, HoraNormalDia=2, HoraNormalDescanso=3). */
  incluirFeriado: number | null;
  feriadoDomingoApenasUmDescanso: boolean | null;
  descontarFeriadosCasoFaltas: boolean | null;
  naoDescontarAntesAdmissao: boolean | null;
  naoDescontarDuranteAfastamento: boolean | null;
}

export interface HorarioDescansoRow {
  id: string;
  horarioId: string;
}

/** Item de `Descanso.Faixas` -> "HorarioDescansoFaixaItem". SEM chave única de negócio — substituição integral junto com o pai. */
export interface InsertHorarioDescansoFaixaItemInput {
  horarioDescansoId: string;
  ordem: number | null;
  /** Texto(5) HH:mm — DURAÇÃO. */
  limite: string | null;
  desconto: string | null;
}

/** Um grupo `Horario.FaixasExtras[i]` -> uma linha de "HorarioFaixasExtras" (por "Dia Semana" do enum de tipo de dia). */
export interface InsertHorarioFaixasExtrasInput {
  horarioId: string;
  secullumHorarioId: number | null;
  /** ⚠️ Enum de TIPO DE DIA (Uteis=0..IntervaloFolgas=15) — diferente de "HorarioDia"."DiaSemana", apesar do nome idêntico. */
  diaSemana: number | null;
  /** Enum bruto (Diario=0, Semanal=1, Mensal=2). */
  controle: number | null;
  /** De Domingo(0) a Sabado(6) — TERCEIRA convenção de dia da semana do schema. */
  diaEspecial: number | null;
}

export interface HorarioFaixasExtrasRow {
  id: string;
  horarioId: string;
  diaSemana: number | null;
}

/** Item de `FaixasExtras.Faixas` -> "HorarioFaixasExtrasItem". SEM chave única de negócio. */
export interface InsertHorarioFaixasExtrasItemInput {
  horarioFaixasExtrasId: string;
  ordem: number | null;
  /** `Duplo` no manual mesmo parecendo índice inteiro — `double precision`. */
  horas: number | null;
  coluna: number | null;
}

/** `Horario.ToleranciaEspecifica` -> "HorarioToleranciaEspecifica" (1:1). Sempre gravada (mesmo `false`/sem itens) — é a fonte única de `UsaToleranciaEspecifica` desde que a coluna equivalente foi removida de "Horario". */
export interface UpsertHorarioToleranciaEspecificaInput {
  horarioId: string;
  usaToleranciaEspecifica: boolean;
}

export interface HorarioToleranciaEspecificaRow {
  id: string;
  horarioId: string;
}

/** Item de `ToleranciaEspecifica.Tolerancias` -> "HorarioToleranciaEspecificaItem". SEM chave única de negócio. */
export interface InsertHorarioToleranciaEspecificaItemInput {
  horarioToleranciaEspecificaId: string;
  secullumHorarioId: number | null;
  /** `[VALIDAR — Postman]` — o manual declara Booleano com descrição errada (copiada de outro campo); modelado como enum bruto (dia da semana). */
  diaSemana: number | null;
  entrada1De: string | null;
  entrada1Ate: string | null;
  saida1De: string | null;
  saida1Ate: string | null;
  entrada2De: string | null;
  entrada2Ate: string | null;
  saida2De: string | null;
  saida2Ate: string | null;
  entrada3De: string | null;
  entrada3Ate: string | null;
  saida3De: string | null;
  saida3Ate: string | null;
  entrada4De: string | null;
  entrada4Ate: string | null;
  saida4De: string | null;
  saida4Ate: string | null;
  entrada5De: string | null;
  entrada5Ate: string | null;
  saida5De: string | null;
  saida5Ate: string | null;
}

export interface UpsertEstruturaInput {
  secullumEstruturaId: number;
  secullumEstruturaPaiId: number | null;
  name: string;
  /**
   * ⚠️ Sempre explícito (nunca `undefined`/omitido) nesta versão do
   * contrato — diferente da Sprint 1 original. Motivo: upsert em LOTE
   * (múltiplas linhas numa única chamada) via PostgREST/Postgres usa a
   * UNIÃO das chaves presentes em qualquer item do lote como colunas do
   * `ON CONFLICT DO UPDATE`; um item que omitisse `email`/`emailSource`
   * teria essas colunas preenchidas com o DEFAULT da tabela (NULL /
   * 'manual'), e não "deixadas como estavam" — ao contrário do upsert
   * linha-a-linha antigo. Por isso o orquestrador (`runCadastroSync`)
   * sempre resolve o valor final (preservando o e-mail atual quando
   * protegido/sem match) antes de montar este input. Ver
   * `SupabaseSyncRepository.upsertManagers`.
   */
  email: string | null;
  emailSource: "secullum" | "manual";
}

/**
 * ADR-011 (Fase 2) — cadastro completo de "Funcionario". Além dos campos já
 * existentes (vínculo, cpf/pis, datas), captura ~45 campos novos confirmados
 * na migration `20260813161000`, incluindo PII sensível (RG, endereço,
 * telefone, celular, e-mail, filiação, nascimento, texto livre).
 *
 * ⚠️ TODO ESTE INPUT CARREGA DADO PESSOAL. Nunca logar, nunca incluir em
 * relatório ao gestor, nunca `select *` exposto ao painel (docs/06-seguranca-lgpd.md).
 */
export interface UpsertFuncionarioInput {
  secullumFuncionarioId: number;
  unitId: string;
  companyId: string;
  name: string;
  secullumCpf: string | null;
  secullumPis: string | null;
  scheduleId: string | null;
  /** ADR-009 — `Funcionario.Admissao`, já parseada por `parseSecullumDateOnly`. */
  admissionDate: string | null;
  /** ADR-009 — `Funcionario.Demissao`. Pode ser uma data FUTURA (desligamento programado). */
  terminationDate: string | null;
  /** Agora DERIVADO de admissionDate/terminationDate (ver `deriveEmployeeActive`), nunca fixo. */
  active: boolean;

  // --- Atributos "<Entidade>Id" (inteiro do Secullum, ao lado das FKs uuid acima) ---
  secullumEmpresaId: number | null;
  secullumDepartamentoId: number | null;
  secullumHorarioId: number | null;
  secullumEstruturaId: number | null;

  // --- NOSSAS FKs resolvidas pelo orquestrador antes do upsert ---
  /** -> "Cidade". Pode ser cidade DIFERENTE da de `company` (cada uma resolvida independentemente). */
  cityId: string | null;
  secullumCidadeId: number | null;
  /** -> "Funcao". */
  functionId: string | null;
  secullumFuncaoId: number | null;

  // --- Identificação / folha ---
  numeroFolha: string | null;
  numeroIdentificador: string | null;
  numeroProvisorio: string | null;
  carteira: string | null;
  codigoHolerite: string | null;
  /** ⚠️ Texto livre de RH — nunca exibir em relatório/log (ver docs/06-seguranca-lgpd.md). */
  observacao: string | null;

  // --- Endereço / contato ---
  endereco: string | null;
  bairro: string | null;
  uf: string | null;
  cep: string | null;
  telefone: string | null;
  /** ⛔ NÃO é canal de WhatsApp autorizado. */
  celular: string | null;
  /** `Funcionario.Email` do PRÓPRIO registro — não confundir com o e-mail do GESTOR ("Estrutura".email). */
  email: string | null;

  // --- Documentos / dados civis (PII sensível) ---
  rg: string | null;
  expedicaoRg: string | null;
  ssp: string | null;
  /** ⚠️ PII de TERCEIRO. */
  mae: string | null;
  /** ⚠️ PII de TERCEIRO. */
  pai: string | null;
  nascimento: string | null;
  masculino: boolean | null;
  nacionalidade: string | null;
  naturalidade: string | null;

  // --- Flags / operação ---
  naoVerificarDigital: boolean | null;
  master: boolean | null;
  possuiFoto: boolean | null;
  invisivel: boolean | null;
  /** `[VALIDAR — Postman]` tipo desconhecido — modelado como texto (coluna `text`). */
  periodoEncerrado: string | null;
  desconsiderarPerimetrosGlobais: boolean | null;
  aceitouTermosLgpdApp: boolean | null;
  dataUltimoEnvio: string | null;
  dataUltimoLogin: string | null;
  dataAlteracao: string | null;

  // --- Ids de entidades não modeladas localmente (inteiro bruto, sem FK) ---
  escolaridadeId: number | null;
  filtro1Id: number | null;
  filtro2Id: number | null;
  motivoDemissaoId: number | null;
  nivelPermissaoId: number | null;
  perfilId: number | null;
  perfilFuncionarioId: number | null;
  bancoHorasId: number | null;
  horarioAlternativo2Id: number | null;
  horarioAlternativo3Id: number | null;
  horarioAlternativo4Id: number | null;

  // --- Bloco ConfigEspecifica*/Bloquear*/Permite*/Desabilitar* (nomes confirmados, tipos [VALIDAR — Postman]) ---
  configEspecificaInclusaoManualPonto: boolean | null;
  configEspecificaInclusaoManualPontoFusoHorarioId: number | null;
  configEspecificaDesativarVerificacaoLocalFicticio: boolean | null;
  configEspecificaInclusaoPontoSemLocalizacao: boolean | null;
  configEspecificaInclusaoPontoOffline: boolean | null;
  configEspecificaCapturaDeFotoNoMomentoDaInclusao: boolean | null;
  bloquearRegistroPontoTeclado: boolean | null;
  permiteInclusaoPontoManual: boolean | null;
  permiteInclusaoDispositivosAutorizados: boolean | null;
  desabilitarAssinaturaEletronica: boolean | null;
}

export interface FuncionarioRow {
  id: string;
  secullumFuncionarioId: number;
}

/**
 * Estado ATUAL de `employee` lido em lote ANTES do upsert (ADR-009) — mesmo
 * racional de `ExistingEmpresaRow`, mas com as duas datas de vínculo também,
 * necessárias para decidir entre `admission`/`termination`/`reactivation`/
 * `date_correction` (ver `buildEmployeeStatusEvent`).
 */
export interface ExistingFuncionarioRow {
  id: string;
  secullumFuncionarioId: number;
  active: boolean;
  admissionDate: string | null;
  terminationDate: string | null;
}

/** Corpo (sem `companyId`, adicionado pelo chamador) de um novo `company_status_event`. */
export interface CompanyStatusEventFields {
  eventType: "baseline" | "deactivated" | "reactivated";
  previousActive: boolean | null;
  newActive: boolean;
}

export interface InsertEmpresaEventoStatusInput extends CompanyStatusEventFields {
  companyId: string;
}

/** Corpo (sem `employeeId`, adicionado pelo chamador) de um novo `employee_status_event`. */
export interface EmployeeStatusEventFields {
  eventType: "baseline" | "admission" | "termination" | "reactivation" | "date_correction";
  previousActive: boolean | null;
  newActive: boolean;
  eventDate: string | null;
  previousAdmissionDate: string | null;
  newAdmissionDate: string | null;
  previousTerminationDate: string | null;
  newTerminationDate: string | null;
}

export interface InsertFuncionarioEventoStatusInput extends EmployeeStatusEventFields {
  employeeId: string;
}

// ---------------------------------------------------------------------------
// employee_absence (ADR-010) — janelas de afastamento/férias.
// ---------------------------------------------------------------------------

/**
 * Estado ATUAL de `employee_absence` lido em lote ANTES do upsert/delete —
 * base tanto da convergência (Decisão 7 do ADR-010: apagar o que sumiu do
 * Secullum, só dentro do escopo buscado) quanto do recálculo de
 * `employee.on_leave`/`current_absence_id` (que precisa considerar TODA
 * janela conhecida, tenha ou não sido tocada nesta execução).
 */
export interface ExistingFuncionarioAfastamentoRow {
  id: string;
  employeeId: string;
  secullumAfastamentoId: number;
  startDate: string;
  endDate: string;
}

/** Corpo de upsert de uma linha de `employee_absence`. Nunca inclui PIS/CPF/Motivo (ADR-010). */
export interface UpsertFuncionarioAfastamentoInput {
  employeeId: string;
  secullumAfastamentoId: number;
  startDate: string;
  endDate: string;
  justificationCode: string | null;
  secullumIncludedAt: string | null;
  matchedBy: "pis" | "cpf";
}

/** Linha retornada pelo upsert em lote — id + chave natural composta (ADR-010, Decisão 3). */
export interface FuncionarioAfastamentoRow {
  id: string;
  employeeId: string;
  secullumAfastamentoId: number;
}

/**
 * Corpo do recálculo de `employee.on_leave`/`current_absence_id` (ADR-010).
 * ⚠️ Estende `UpsertFuncionarioInput` (não só `{id, onLeave, currentAbsenceId}`)
 * de propósito: um upsert em LOTE via PostgREST monta um INSERT real por
 * trás do `ON CONFLICT DO UPDATE`, e esse INSERT precisa satisfazer as
 * colunas `NOT NULL` da tabela (`unit_id`, `company_id`, `name`, ...) mesmo
 * quando a linha já existe — omiti-las faria o Postgres rejeitar o lote
 * inteiro com "null value in column ... violates not-null constraint" antes
 * de sequer chegar ao `ON CONFLICT`. Reenviar a linha completa (já
 * disponível em memória, sem SELECT adicional) é o preço para continuar
 * batendo a regra de performance deste módulo (um único upsert em lote,
 * nunca um `UPDATE` por funcionário) sem introduzir uma função remota
 * (RPC)/migration nova só para isso.
 */
export type UpsertFuncionarioLeaveStatusInput = UpsertFuncionarioInput & {
  onLeave: boolean;
  currentAbsenceId: string | null;
};

/**
 * Abstração de persistência da sincronização cadastral. Implementada por
 * `SupabaseSyncRepository` (produção, supabase-js + service_role) e por um
 * repositório em memória nos testes (cadastro-sync.test.ts).
 *
 * Todo método de escrita recebe um ARRAY e faz UM upsert em lote (ver nota de
 * performance no topo do arquivo) — nunca uma chamada por item. `listUnits`/
 * `listManagers` existem para permitir resolver "já existe?" com uma única
 * leitura em massa (as tabelas são pequenas — dezenas/poucas centenas de
 * linhas), em vez de um `SELECT` por item dentro do laço de funcionários.
 */
export interface SyncRepository {
  /** Leitura em lote do estado ATUAL de company (ADR-009) — usada antes do upsert, para gerar eventos de histórico. */
  listCompanies(): Promise<ExistingEmpresaRow[]>;
  upsertCompanies(inputs: UpsertEmpresaInput[]): Promise<EmpresaRow[]>;
  listUnits(): Promise<DepartamentoRow[]>;
  upsertUnits(inputs: UpsertDepartamentoInput[]): Promise<DepartamentoRow[]>;
  /** ADR-011 — upsert em lote de "Cidade" por "Descricao". Sem leitura prévia: sem histórico/diffing necessário. */
  upsertCities(inputs: UpsertCidadeInput[]): Promise<CidadeRow[]>;
  /** ADR-011 — upsert em lote de "Funcao" por "Descricao". Mesmo racional de `upsertCities`. */
  upsertFunctions(inputs: UpsertFuncaoInput[]): Promise<FuncaoRow[]>;
  upsertWorkSchedules(inputs: UpsertHorarioInput[]): Promise<HorarioRow[]>;
  upsertWorkScheduleDays(inputs: UpsertHorarioDiaInput[]): Promise<void>;
  listManagers(): Promise<EstruturaRow[]>;
  upsertManagers(inputs: UpsertEstruturaInput[]): Promise<EstruturaRow[]>;

  /** Linhas VIGENTES de `secullum.departamento_gestor` (`observado_ate is null`). */
  listCurrentDepartmentManagers(): Promise<VigenciaGestor[]>;
  /**
   * Aplica uma transição pela RPC `secullum.departamento_gestor_transition`.
   *
   * A RPC é o **único** caminho de escrita da tabela, e o motivo está no
   * comentário dela: fechar a anterior e abrir a nova numa transação só. Um
   * `update` seguido de `insert` daqui reintroduziria a janela em que o
   * departamento fica sem gestor vigente, ou com dois.
   */
  transitionDepartmentManager(transicao: TransicaoGestor): Promise<void>;
  /** Leitura em lote do estado ATUAL de employee (ADR-009) — usada antes do upsert, para gerar eventos de histórico. */
  listEmployees(): Promise<ExistingFuncionarioRow[]>;
  /** Retorna as linhas upsertadas (id + chave natural) — necessário para vincular `employee_status_event.employee_id`. */
  upsertEmployees(inputs: UpsertFuncionarioInput[]): Promise<FuncionarioRow[]>;
  /** Um único INSERT em lote — nunca uma linha por empresa (ADR-009, mesma disciplina de performance do restante do módulo). */
  insertCompanyStatusEvents(inputs: InsertEmpresaEventoStatusInput[]): Promise<void>;
  /** Um único INSERT em lote — nunca uma linha por funcionário (ADR-009). */
  insertEmployeeStatusEvents(inputs: InsertFuncionarioEventoStatusInput[]): Promise<void>;

  /** Leitura em lote do estado ATUAL de employee_absence (ADR-010) — base da convergência e do recálculo de on_leave. */
  listEmployeeAbsences(): Promise<ExistingFuncionarioAfastamentoRow[]>;
  /** Upsert em lote por `(employee_id, secullum_afastamento_id)` — ver ADR-010, Decisão 3. */
  upsertEmployeeAbsences(
    inputs: UpsertFuncionarioAfastamentoInput[],
  ): Promise<FuncionarioAfastamentoRow[]>;
  /**
   * DELETE em lote de convergência (ADR-010, Decisão 7) — só chamado pelo
   * orquestrador com ids que já existiam e não vieram na resposta desta
   * execução, e nunca quando a resposta do Secullum veio vazia.
   */
  deleteEmployeeAbsencesByIds(ids: string[]): Promise<void>;
  /** Um único upsert em lote — recálculo de `employee.on_leave`/`current_absence_id` (ADR-010). */
  applyEmployeeLeaveStatus(inputs: UpsertFuncionarioLeaveStatusInput[]): Promise<void>;

  /** ADR-011 — leitura em lote do estado ATUAL de "FuncionarioCentroCusto" (base da substituição integral por funcionário). */
  listCostCenters(): Promise<ExistingCentroCustoRow[]>;
  /** ADR-011 — upsert em lote por `(funcionario_id, "Descricao")`. */
  upsertCostCenters(inputs: UpsertCentroCustoInput[]): Promise<CentroCustoRow[]>;
  /** ADR-011 — DELETE em lote de convergência (centro de custo que sumiu do Secullum para aquele funcionário). */
  deleteCostCentersByIds(ids: string[]): Promise<void>;

  // -------------------------------------------------------------------------
  // ADR-011 Fase 3 (migration 20260813162000) — árvore completa de "Horario".
  // Ver o comentário no topo dos tipos `UpsertHorariosOpcoesInput` e
  // seguintes para o padrão de escrita de cada tabela (1:1 upsert vs.
  // substituição integral DELETE+INSERT).
  // -------------------------------------------------------------------------

  /** Upsert em lote por horario_id — "HorariosOpcoes" (1:1, sem delete: o upsert substitui a única linha). */
  upsertScheduleOptions(inputs: UpsertHorariosOpcoesInput[]): Promise<void>;
  /** Upsert em lote por horario_id — "HorarioExtras" (1:1). */
  upsertScheduleExtras(inputs: UpsertHorarioExtrasInput[]): Promise<void>;

  /** Upsert em lote por horario_id — "HorarioDescanso" (1:1). Retorna as linhas para resolver a FK de "HorarioDescansoFaixaItem". */
  upsertScheduleRests(inputs: UpsertHorarioDescansoInput[]): Promise<HorarioDescansoRow[]>;
  /** DELETE em lote por horario_descanso_id — convergência de "HorarioDescansoFaixaItem" ANTES do INSERT do conjunto novo. */
  deleteScheduleRestRangesByParentIds(horarioDescansoIds: string[]): Promise<void>;
  /** INSERT em lote (nunca upsert — sem chave única de negócio) de "HorarioDescansoFaixaItem". */
  insertScheduleRestRanges(inputs: InsertHorarioDescansoFaixaItemInput[]): Promise<void>;

  /** DELETE em lote por horario_id — convergência de "HorarioFaixasExtras" (cascata para "HorarioFaixasExtrasItem") ANTES do INSERT do conjunto novo. */
  deleteScheduleExtraRangeGroupsByHorarioIds(horarioIds: string[]): Promise<void>;
  /** INSERT em lote de "HorarioFaixasExtras". Retorna as linhas (com "DiaSemana") para resolver a FK de "HorarioFaixasExtrasItem". */
  insertScheduleExtraRangeGroups(
    inputs: InsertHorarioFaixasExtrasInput[],
  ): Promise<HorarioFaixasExtrasRow[]>;
  /** INSERT em lote de "HorarioFaixasExtrasItem". */
  insertScheduleExtraRangeGroupItems(inputs: InsertHorarioFaixasExtrasItemInput[]): Promise<void>;

  /** Upsert em lote por horario_id — "HorarioToleranciaEspecifica" (1:1, sempre gravada). Retorna as linhas para resolver a FK de "HorarioToleranciaEspecificaItem". */
  upsertScheduleSpecificTolerances(
    inputs: UpsertHorarioToleranciaEspecificaInput[],
  ): Promise<HorarioToleranciaEspecificaRow[]>;
  /** DELETE em lote por horario_tolerancia_especifica_id — convergência de "HorarioToleranciaEspecificaItem" ANTES do INSERT do conjunto novo. */
  deleteScheduleSpecificToleranceItemsByParentIds(
    horarioToleranciaEspecificaIds: string[],
  ): Promise<void>;
  /** INSERT em lote de "HorarioToleranciaEspecificaItem". */
  insertScheduleSpecificToleranceItems(
    inputs: InsertHorarioToleranciaEspecificaItemInput[],
  ): Promise<void>;
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

export const consoleSyncLogger: SyncLogger = {
  warn: (m) => console.warn(`[sync-cadastro] ${m}`),
  info: (m) => console.info(`[sync-cadastro] ${m}`),
};

export interface SyncSummary {
  companiesUpserted: number;
  unitsUpserted: number;
  managersUpserted: number;
  /**
   * Funcionários LIDOS da origem nesta execução — o `records_read` do diário.
   *
   * Contado da resposta, e não derivado de `employeesUpserted + employeesSkipped`:
   * derivar tornaria a soma verdadeira por construção, e é justamente ela que
   * denuncia um caminho de saída novo no laço que não incrementa contador nenhum.
   */
  employeesFetched: number;
  employeesUpserted: number;
  employeesSkipped: number;
  schedulesUpserted: number;
  scheduleDaysUpserted: number;
  /** ADR-009 — linhas inseridas em `company_status_event` nesta execução (baseline + transições). */
  companyStatusEventsInserted: number;
  /** ADR-009 — linhas inseridas em `employee_status_event` nesta execução. */
  employeeStatusEventsInserted: number;
  /** ADR-010 — linhas upsertadas em `employee_absence` nesta execução (0 quando a resposta veio vazia). */
  absencesUpserted: number;
  /** ADR-010 — linhas apagadas de `employee_absence` na convergência desta execução. */
  absencesDeleted: number;
  /** Transições gravadas em `secullum.departamento_gestor` nesta execução (ADR-013). */
  departmentManagerTransitions: number;
  /** ADR-011 — linhas upsertadas em "Cidade" nesta execução (deduplicadas entre Funcionario e Empresa). */
  citiesUpserted: number;
  /** ADR-011 — linhas upsertadas em "Funcao" nesta execução. */
  functionsUpserted: number;
  /** ADR-011 — linhas upsertadas em "FuncionarioCentroCusto" nesta execução. */
  costCentersUpserted: number;
  /** ADR-011 — linhas apagadas de "FuncionarioCentroCusto" na convergência (substituição integral por funcionário). */
  costCentersDeleted: number;
  /** ADR-011 Fase 3 — linhas upsertadas em "HorariosOpcoes" nesta execução. */
  scheduleOptionsUpserted: number;
  /** ADR-011 Fase 3 — linhas upsertadas em "HorarioExtras" nesta execução. */
  scheduleExtrasUpserted: number;
  /** ADR-011 Fase 3 — linhas upsertadas em "HorarioDescanso" nesta execução. */
  scheduleRestsUpserted: number;
  /** ADR-011 Fase 3 — linhas inseridas em "HorarioDescansoFaixaItem" nesta execução (substituição integral). */
  scheduleRestRangesInserted: number;
  /** ADR-011 Fase 3 — linhas inseridas em "HorarioFaixasExtras" nesta execução (substituição integral). */
  scheduleExtraRangeGroupsInserted: number;
  /** ADR-011 Fase 3 — linhas inseridas em "HorarioFaixasExtrasItem" nesta execução. */
  scheduleExtraRangeItemsInserted: number;
  /** ADR-011 Fase 3 — linhas upsertadas em "HorarioToleranciaEspecifica" nesta execução. */
  scheduleSpecificTolerancesUpserted: number;
  /** ADR-011 Fase 3 — linhas inseridas em "HorarioToleranciaEspecificaItem" nesta execução (substituição integral). */
  scheduleSpecificToleranceItemsInserted: number;
  warnings: SyncWarning[];
}

function emptySummary(): SyncSummary {
  return {
    companiesUpserted: 0,
    departmentManagerTransitions: 0,
    unitsUpserted: 0,
    managersUpserted: 0,
    employeesFetched: 0,
    employeesUpserted: 0,
    employeesSkipped: 0,
    schedulesUpserted: 0,
    scheduleDaysUpserted: 0,
    companyStatusEventsInserted: 0,
    employeeStatusEventsInserted: 0,
    absencesUpserted: 0,
    absencesDeleted: 0,
    citiesUpserted: 0,
    functionsUpserted: 0,
    costCentersUpserted: 0,
    costCentersDeleted: 0,
    scheduleOptionsUpserted: 0,
    scheduleExtrasUpserted: 0,
    scheduleRestsUpserted: 0,
    scheduleRestRangesInserted: 0,
    scheduleExtraRangeGroupsInserted: 0,
    scheduleExtraRangeItemsInserted: 0,
    scheduleSpecificTolerancesUpserted: 0,
    scheduleSpecificToleranceItemsInserted: 0,
    warnings: [],
  };
}

/**
 * Máximo de ocorrências do MESMO código de aviso mantidas em
 * `summary.warnings` (e efetivamente logadas) numa execução.
 *
 * ⚠️ Proteção obrigatória (incidente de produção 2026-08-12): sem este
 * limite, um cadastro com muitos valores de status em `EntradaN`/`SaidaN`
 * (ex.: "Férias" em várias linhas de `Horario.Dias`) pode gerar milhares de
 * avisos quase idênticos — cada `push` no array e cada `console.warn`
 * adicional é trabalho extra de CPU dentro da MESMA invocação, e um array de
 * avisos sem limite no `summary` também não é o que
 * `docs/06-seguranca-lgpd.md` pede ("resposta só com contadores/avisos
 * agregados"). Passado o limite, só a CONTAGEM é mantida em memória — o
 * detalhe de cada ocorrência adicional é descartado, e um único aviso
 * agregado por código é anexado ao final com o total real.
 */
const WARNING_SAMPLE_CAP = 50;

// ---------------------------------------------------------------------------
// Normalização defensiva de tipo — ADR-011.
// ---------------------------------------------------------------------------

/**
 * Normaliza um campo booleano "solto" do Secullum (bloco
 * `ConfigEspecifica*`/`Bloquear*`/`Permite*`/`Desabilitar*` de `Funcionario`
 * e alguns campos de `Empresa` — tipo NÃO confirmado, só o NOME foi
 * confirmado, ver migration `20260813161000`). Aceita
 * `true/false/0/1/"true"/"false"/"0"/"1"`; qualquer outro formato vira `null`
 * — NUNCA repassa o valor cru (um número bruto numa coluna `boolean`
 * derrubaria a transação inteira do ciclo) e NUNCA lança exceção.
 */
export function asBoolean(
  value: unknown,
  onUnexpectedFormat?: (typeReceived: string) => void,
): boolean | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (value === 0) return false;
    if (value === 1) return true;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (normalized === "true" || normalized === "1") return true;
    if (normalized === "false" || normalized === "0") return false;
  }
  onUnexpectedFormat?.(typeof value);
  return null;
}

/** Normaliza um campo `unknown` para `string | null` — só aceita string, qualquer outra coisa vira `null` (sem lançar). */
export function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/**
 * Normaliza um campo `unknown` para `number | null` — só aceita `number`
 * finito, qualquer outra coisa vira `null`, sem lançar. `onUnexpectedFormat`
 * é opcional (a maioria dos atributos `"<Entidade>Id"` já é integer bruto e
 * dispensa aviso); usado pelo bloco `ConfigEspecifica*` (tipo `[VALIDAR —
 * Postman]`, ADR-011), mesmo padrão de `asBoolean`.
 */
export function asNumber(
  value: unknown,
  onUnexpectedFormat?: (typeReceived: string) => void,
): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  onUnexpectedFormat?.(typeof value);
  return null;
}

/**
 * `Funcionario.PeriodoEncerrado` — tipo desconhecido (`[VALIDAR — Postman]`),
 * modelado como `text` para não perder o valor nem quebrar o job por
 * conversão errada (docs/04-modelo-dados.md §0.6). Qualquer valor primitivo
 * é convertido para string; `null`/`undefined`/objeto viram `null`.
 */
export function asTextPassthrough(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return null;
}

/**
 * Passa um valor `jsonb` bruto adiante SEM tentar tipar (ADR-011 Fase 3,
 * migration `20260813162000` — `"HorasRepousoFaixas"`, `"ListaHorasSobreAviso"`,
 * `"ListaHorasInItinere"`, `"CompensacaoMensalFechamento"`). `undefined` vira
 * `null` (o Postgres não aceita `undefined`); qualquer outro valor
 * (`null`/objeto/array/primitivo) é preservado exatamente como veio — nenhum
 * destes campos tem shape confirmado, e modelar colunas filhas aqui
 * significaria inventar estrutura sem evidência (mesmo erro que já quebrou
 * este projeto duas vezes em produção).
 */
export type JsonDesconhecido =
  | null
  | boolean
  | number
  | string
  | JsonDesconhecido[]
  | { [chave: string]: JsonDesconhecido };

export function asJsonPassthrough(value: unknown): JsonDesconhecido {
  // O único cast do arquivo, e ele NÃO afirma shape: diz apenas "isto é JSON",
  // que é o que a coluna `jsonb` do espelho já declara. Sem ele o driver recusa
  // `unknown` como parâmetro, e a alternativa seria modelar as colunas do item
  // — exatamente o que os comentários acima proíbem por falta de evidência.
  return (value === undefined ? null : value) as JsonDesconhecido;
}

// ---------------------------------------------------------------------------
// "Cidade" / "Funcao" — resolução dos nós aninhados compartilhados por
// "Funcionario" e "Empresa" (ADR-011). Forma CONFIRMADA: sempre um objeto
// `{ Id, Descricao }`, nunca string solta — nenhum ramo `typeof === "string"`.
// ---------------------------------------------------------------------------

interface CidadeNode {
  descricao: string;
  secullumCidadeId: number | null;
}

/** Extrai `{ Descricao, Id }` de um nó `Cidade` aninhado — `null` se ausente ou sem `Descricao` (chave de idempotência obrigatória). */
export function extractCidadeNode(raw: RawCidade | null | undefined): CidadeNode | null {
  if (!raw || typeof raw.Descricao !== "string" || raw.Descricao.length === 0) return null;
  return { descricao: raw.Descricao, secullumCidadeId: asNumber(raw.Id) };
}

interface FuncaoNode {
  descricao: string;
  secullumFuncaoId: number | null;
}

/** Extrai `{ Descricao, Id }` de um nó `Funcao` aninhado — mesmo racional de `extractCidadeNode`. */
export function extractFuncaoNode(raw: RawFuncao | null | undefined): FuncaoNode | null {
  if (!raw || typeof raw.Descricao !== "string" || raw.Descricao.length === 0) return null;
  return { descricao: raw.Descricao, secullumFuncaoId: asNumber(raw.Id) };
}

/** Extrai as `Descricao` de `Funcionario.ListaCentroDeCustos` — descarta itens sem `Descricao`, sem lançar. */
export function extractCentroCustoDescricoes(raw: RawCentroCusto[] | null | undefined): string[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => item?.Descricao)
    .filter((d): d is string => typeof d === "string" && d.length > 0);
}

// ---------------------------------------------------------------------------
// Parsing — cadastro completo de funcionário (ADR-011, migration 20260813161000).
// ---------------------------------------------------------------------------

/**
 * Campos extraídos de um `Funcionario` para virar `"Funcionario"` — captura
 * COMPLETA (ADR-011): não é mais allow-list. `Cidade`/`Funcao` ficam como nós
 * brutos (`cidade`/`funcao`, resolvidos para FK pelo orquestrador, que
 * precisa deduplicar/upsertar em lote ANTES de montar o `UpsertFuncionarioInput`
 * final); `centroCustoDescricoes` é a lista já normalizada de
 * `ListaCentroDeCustos`, escrita por substituição integral.
 *
 * ⚠️ Deliberadamente NÃO faz spread (`...raw`) — cada campo é extraído
 * explicitamente, então um campo novo do payload não vaza por acidente antes
 * de alguém decidir conscientemente capturá-lo (mesmo espírito da antiga
 * allow-list, agora aplicado a um conjunto muito maior de campos).
 * `SenhaEquipamento` e `Foto` NUNCA aparecem aqui — ver RawFuncionario.
 */
export interface ParsedFuncionario {
  id: number;
  name: string;
  empresaId: number;
  departamentoId: number;
  estruturaId: number | null;
  horarioId: number | null;
  cpf: string | null;
  pis: string | null;
  /** ADR-009 — `Funcionario.Admissao`, já normalizada para "yyyy-MM-dd" (ou `null`). */
  admissionDate: string | null;
  /** ADR-009 — `Funcionario.Demissao`, já normalizada para "yyyy-MM-dd" (ou `null`). */
  terminationDate: string | null;

  cidade: CidadeNode | null;
  funcao: FuncaoNode | null;
  centroCustoDescricoes: string[];

  numeroFolha: string | null;
  numeroIdentificador: string | null;
  numeroProvisorio: string | null;
  carteira: string | null;
  codigoHolerite: string | null;
  observacao: string | null;

  endereco: string | null;
  bairro: string | null;
  uf: string | null;
  cep: string | null;
  telefone: string | null;
  celular: string | null;
  email: string | null;

  rg: string | null;
  expedicaoRg: string | null;
  ssp: string | null;
  mae: string | null;
  pai: string | null;
  nascimento: string | null;
  masculino: boolean | null;
  nacionalidade: string | null;
  naturalidade: string | null;

  naoVerificarDigital: boolean | null;
  master: boolean | null;
  possuiFoto: boolean | null;
  invisivel: boolean | null;
  periodoEncerrado: string | null;
  desconsiderarPerimetrosGlobais: boolean | null;
  aceitouTermosLgpdApp: boolean | null;
  dataUltimoEnvio: string | null;
  dataUltimoLogin: string | null;
  dataAlteracao: string | null;

  escolaridadeId: number | null;
  filtro1Id: number | null;
  filtro2Id: number | null;
  motivoDemissaoId: number | null;
  nivelPermissaoId: number | null;
  perfilId: number | null;
  perfilFuncionarioId: number | null;
  bancoHorasId: number | null;
  horarioAlternativo2Id: number | null;
  horarioAlternativo3Id: number | null;
  horarioAlternativo4Id: number | null;

  configEspecificaInclusaoManualPonto: boolean | null;
  configEspecificaInclusaoManualPontoFusoHorarioId: number | null;
  configEspecificaDesativarVerificacaoLocalFicticio: boolean | null;
  configEspecificaInclusaoPontoSemLocalizacao: boolean | null;
  configEspecificaInclusaoPontoOffline: boolean | null;
  configEspecificaCapturaDeFotoNoMomentoDaInclusao: boolean | null;
  bloquearRegistroPontoTeclado: boolean | null;
  permiteInclusaoPontoManual: boolean | null;
  permiteInclusaoDispositivosAutorizados: boolean | null;
  desabilitarAssinaturaEletronica: boolean | null;
}

/**
 * Extrai TODOS os campos confirmados de `RawFuncionario` (ADR-011, migration
 * `20260813161000`) — substitui a antiga `parseFuncionarioAllowList`. O
 * bloco `ConfigEspecifica*`/`Bloquear*`/`Permite*`/`Desabilitar*` é
 * normalizado via `asBoolean`/`asNumber` com aviso opcional (uma vez por
 * campo por execução, a cargo do chamador) em formato inesperado — nunca
 * derruba o ciclo por causa de um campo que nenhum consumidor lê hoje.
 */
export function parseFuncionario(
  raw: RawFuncionario,
  warnUnexpectedFieldFormat?: (fieldName: string, typeReceived: string) => void,
): ParsedFuncionario {
  const warnField = (fieldName: string) => (typeReceived: string) =>
    warnUnexpectedFieldFormat?.(fieldName, typeReceived);

  return {
    id: raw.Id,
    name: raw.Nome,
    empresaId: raw.EmpresaId,
    departamentoId: raw.DepartamentoId,
    estruturaId: raw.EstruturaId ?? raw.Estrutura?.Id ?? null,
    horarioId: raw.HorarioId ?? raw.Horario?.Id ?? null,
    cpf: raw.Cpf ?? raw.NumeroCpf ?? null,
    pis: raw.Pis ?? raw.NumeroPis ?? null,
    admissionDate: parseSecullumDateOnly(raw.Admissao),
    terminationDate: parseSecullumDateOnly(raw.Demissao),

    cidade: extractCidadeNode(raw.Cidade),
    funcao: extractFuncaoNode(raw.Funcao),
    centroCustoDescricoes: extractCentroCustoDescricoes(raw.ListaCentroDeCustos),

    numeroFolha: asString(raw.NumeroFolha),
    numeroIdentificador: asString(raw.NumeroIdentificador),
    numeroProvisorio: asString(raw.NumeroProvisorio),
    carteira: asString(raw.Carteira),
    codigoHolerite: asString(raw.CodigoHolerite),
    observacao: asString(raw.Observacao),

    endereco: asString(raw.Endereco),
    bairro: asString(raw.Bairro),
    uf: asString(raw.Uf),
    cep: asString(raw.Cep),
    telefone: asString(raw.Telefone),
    celular: asString(raw.Celular),
    email: raw.Email ?? null,

    rg: asString(raw.Rg),
    expedicaoRg: parseSecullumDateOnly(raw.ExpedicaoRg),
    ssp: asString(raw.Ssp),
    mae: asString(raw.Mae),
    pai: asString(raw.Pai),
    nascimento: parseSecullumDateOnly(raw.Nascimento),
    masculino: asBoolean(raw.Masculino, warnField("Masculino")),
    nacionalidade: asString(raw.Nacionalidade),
    naturalidade: asString(raw.Naturalidade),

    naoVerificarDigital: asBoolean(raw.NaoVerificarDigital, warnField("NaoVerificarDigital")),
    master: asBoolean(raw.Master, warnField("Master")),
    possuiFoto: asBoolean(raw.PossuiFoto, warnField("PossuiFoto")),
    invisivel: asBoolean(raw.Invisivel, warnField("Invisivel")),
    periodoEncerrado: asTextPassthrough(raw.PeriodoEncerrado),
    desconsiderarPerimetrosGlobais: asBoolean(
      raw.DesconsiderarPerimetrosGlobais,
      warnField("DesconsiderarPerimetrosGlobais"),
    ),
    aceitouTermosLgpdApp: asBoolean(raw.AceitouTermosLgpdApp, warnField("AceitouTermosLgpdApp")),
    dataUltimoEnvio: asString(raw.DataUltimoEnvio),
    dataUltimoLogin: asString(raw.DataUltimoLogin),
    dataAlteracao: asString(raw.DataAlteracao),

    escolaridadeId: asNumber(raw.EscolaridadeId),
    filtro1Id: asNumber(raw.Filtro1Id),
    filtro2Id: asNumber(raw.Filtro2Id),
    motivoDemissaoId: asNumber(raw.MotivoDemissaoId),
    nivelPermissaoId: asNumber(raw.NivelPermissaoId),
    perfilId: asNumber(raw.PerfilId),
    perfilFuncionarioId: asNumber(raw.PerfilFuncionarioId),
    bancoHorasId: asNumber(raw.BancoHorasId),
    horarioAlternativo2Id: asNumber(raw.HorarioAlternativo2Id),
    horarioAlternativo3Id: asNumber(raw.HorarioAlternativo3Id),
    horarioAlternativo4Id: asNumber(raw.HorarioAlternativo4Id),

    configEspecificaInclusaoManualPonto: asBoolean(
      raw.ConfigEspecificaInclusaoManualPonto,
      warnField("ConfigEspecificaInclusaoManualPonto"),
    ),
    configEspecificaInclusaoManualPontoFusoHorarioId: asNumber(
      raw.ConfigEspecificaInclusaoManualPontoFusoHorarioId,
      warnField("ConfigEspecificaInclusaoManualPontoFusoHorarioId"),
    ),
    configEspecificaDesativarVerificacaoLocalFicticio: asBoolean(
      raw.ConfigEspecificaDesativarVerificacaoLocalFicticio,
      warnField("ConfigEspecificaDesativarVerificacaoLocalFicticio"),
    ),
    configEspecificaInclusaoPontoSemLocalizacao: asBoolean(
      raw.ConfigEspecificaInclusaoPontoSemLocalizacao,
      warnField("ConfigEspecificaInclusaoPontoSemLocalizacao"),
    ),
    configEspecificaInclusaoPontoOffline: asBoolean(
      raw.ConfigEspecificaInclusaoPontoOffline,
      warnField("ConfigEspecificaInclusaoPontoOffline"),
    ),
    configEspecificaCapturaDeFotoNoMomentoDaInclusao: asBoolean(
      raw.ConfigEspecificaCapturaDeFotoNoMomentoDaInclusao,
      warnField("ConfigEspecificaCapturaDeFotoNoMomentoDaInclusao"),
    ),
    bloquearRegistroPontoTeclado: asBoolean(
      raw.BloquearRegistroPontoTeclado,
      warnField("BloquearRegistroPontoTeclado"),
    ),
    permiteInclusaoPontoManual: asBoolean(
      raw.PermiteInclusaoPontoManual,
      warnField("PermiteInclusaoPontoManual"),
    ),
    permiteInclusaoDispositivosAutorizados: asBoolean(
      raw.PermiteInclusaoDispositivosAutorizados,
      warnField("PermiteInclusaoDispositivosAutorizados"),
    ),
    desabilitarAssinaturaEletronica: asBoolean(
      raw.DesabilitarAssinaturaEletronica,
      warnField("DesabilitarAssinaturaEletronica"),
    ),
  };
}

/**
 * Extrai os campos novos de `RawEmpresa` (ADR-011) que acompanham
 * `secullumDocumento`/`name`/`active` já resolvidos pelo chamador (ver
 * `deriveCompanyActive`). Mesma disciplina de `parseFuncionario`: extração
 * explícita, sem spread, com normalização defensiva de tipo.
 */
export function pickEmpresaFields(raw: RawEmpresa): Omit<
  UpsertEmpresaInput,
  "secullumDocumento" | "name" | "active" | "cityId"
> {
  return {
    secullumEmpresaId: asNumber(raw.Id),
    inscricao: asString(raw.Inscricao),
    endereco: asString(raw.Endereco),
    bairro: asString(raw.Bairro),
    secullumCidadeId: asNumber(raw.Cidade?.Id),
    cep: asString(raw.Cep),
    uf: asString(raw.Uf),
    pais: asString(raw.Pais),
    telefone: asString(raw.Telefone),
    fax: asString(raw.Fax),
    cei: asString(raw.Cei),
    nfolhaEmpresa: asString(raw.NfolhaEmpresa),
    logotipo: asString(raw.Logotipo),
    possuiLogo: asBoolean(raw.PossuiLogo),
    responsavelNome: asString(raw.ResponsavelNome),
    responsavelCargo: asString(raw.ResponsavelCargo),
    responsavelEmail: asString(raw.ResponsavelEmail),
    tipoDocumento: asNumber(raw.TipoDocumento),
    utilizaRepC: asBoolean(raw.UtilizaRepC),
    utilizaRepA: asBoolean(raw.UtilizaRepA),
    utilizaRepP: asBoolean(raw.UtilizaRepP),
    usaFechamentoDoPontoEspecifico: asBoolean(raw.UsaFechamentoDoPontoEspecifico),
    fechamentoPonto: asNumber(raw.FechamentoPonto),
    diaFechamentoPonto: asNumber(raw.DiaFechamentoPonto),
    emitiuAtestadoTecnico: asBoolean(raw.EmitiuAtestadoTecnico),
  };
}

// ---------------------------------------------------------------------------
// Resolução do gestor — match de nome (docs/03-integracao-secullum.md).
// ---------------------------------------------------------------------------

interface NameCandidate {
  email: string | null;
}

/** Índice nome-normalizado -> candidatos, construído sobre a lista COMPLETA de /Funcionarios do ciclo. */
export type NameIndex = Map<string, NameCandidate[]>;

export function buildFuncionarioNameIndex(funcionarios: RawFuncionario[]): NameIndex {
  const index: NameIndex = new Map();
  for (const f of funcionarios) {
    if (!f.Nome) continue;
    const key = normalizePersonName(f.Nome);
    const list = index.get(key) ?? [];
    list.push({ email: f.Email ?? null });
    index.set(key, list);
  }
  return index;
}

export type ManagerEmailMatch =
  | { outcome: "unique"; email: string | null }
  | { outcome: "zero" }
  | { outcome: "multiple"; count: number };

/**
 * Resolve o e-mail do gestor por igualdade EXATA de nome normalizado — sem
 * contains/prefixo/fuzzy (regra obrigatória, docs/03-integracao-secullum.md).
 */
export function resolveManagerEmailMatch(
  index: NameIndex,
  estruturaDescricao: string,
): ManagerEmailMatch {
  const candidates = index.get(normalizePersonName(estruturaDescricao)) ?? [];
  if (candidates.length === 1) return { outcome: "unique", email: candidates[0].email };
  if (candidates.length === 0) return { outcome: "zero" };
  return { outcome: "multiple", count: candidates.length };
}

// ---------------------------------------------------------------------------
// Parsing de Horario / Horario.Dias (docs/03 — "Grade de horário").
// ---------------------------------------------------------------------------

/** `Horario.Desativar` — semântica/tipo exatos não confirmados (docs/04-modelo-dados.md); tratamos qualquer valor "truthy" como inativo. */
export function deriveScheduleActive(desativar: RawHorario["Desativar"]): boolean {
  if (desativar === null || desativar === undefined) return true;
  if (typeof desativar === "boolean") return !desativar;
  return desativar === 0;
}

// ---------------------------------------------------------------------------
// Histórico de status de company/employee — ADR-009 (2026-08-13).
// Nenhuma chamada nova ao Secullum: os três campos abaixo (Empresa.Desativada,
// Admissao, Demissao) já vêm no mesmo payload de /Funcionarios buscado na
// fase 1 de runCadastroSync. Toda escrita é local (Supabase).
// ---------------------------------------------------------------------------

/**
 * `Funcionario.Empresa.Desativada` -> `company.active = NOT Desativada`.
 *
 * Tipo exato não confirmado pelo Secullum (`[VALIDAR — Owner]`, ADR-009,
 * pendência 3) — tratado defensivamente, mesmo padrão de `deriveScheduleActive`:
 * boolean e `0`/`1` numérico são interpretados diretamente; `"true"`/`"false"`/
 * `"0"`/`"1"` em string também são aceitos (variação plausível de serialização).
 * Qualquer outro formato (objeto, número fora de 0/1 etc.) cai no FALLBACK
 * SEGURO — assume NÃO desativada (mesma escolha conservadora usada para
 * `null`/`undefined`) e nunca lança exceção; o chamador é responsável por
 * logar um aviso quando `onUnexpectedFormat` é invocado, para investigação
 * manual sem derrubar o job.
 */
export function deriveCompanyActive(
  desativada: unknown,
  onUnexpectedFormat?: (typeReceived: string) => void,
): boolean {
  if (desativada === null || desativada === undefined) return true;
  if (typeof desativada === "boolean") return !desativada;
  if (typeof desativada === "number") return desativada === 0;
  if (typeof desativada === "string") {
    const normalized = desativada.trim().toLowerCase();
    if (normalized === "true" || normalized === "1") return false;
    if (normalized === "false" || normalized === "0" || normalized === "") return true;
  }
  onUnexpectedFormat?.(typeof desativada);
  return true; // fallback seguro — ver comentário acima.
}

/**
 * Extrai a parte de DATA (`"yyyy-MM-dd"`) de um campo de data do Secullum
 * (`Admissao`/`Demissao`), no mesmo padrão já documentado para `Data` de
 * `/Batidas`: string ISO `"yyyy-MM-ddT00:00:00"`, sem timezone — pegar
 * SEMPRE os 10 primeiros caracteres, nunca `new Date(...)`/`toISOString()`
 * (desloca um dia no runtime UTC da Edge Function). Qualquer formato que não
 * comece com `"yyyy-MM-dd"` vira `null` — nunca lança exceção.
 */
const DATE_ONLY_PREFIX_PATTERN = /^\d{4}-\d{2}-\d{2}/;

export function parseSecullumDateOnly(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const match = DATE_ONLY_PREFIX_PATTERN.exec(value);
  return match ? match[0] : null;
}

/**
 * `employee.active` — DERIVADO das datas de vínculo, nunca fixo (ADR-009):
 * `active = (admissionDate is null or admissionDate <= today)
 *       and (terminationDate is null or terminationDate >= today)`
 * `today` é injetado (ver `TodayProvider`/`systemTodayInSaoPaulo`) para que os
 * testes controlem a data sem depender do relógio real — o resultado desta
 * função pode mudar de uma execução para outra mesmo sem nenhuma mudança no
 * Secullum (ex.: desligamento programado cuja data chegou).
 */
export function deriveEmployeeActive(
  admissionDate: string | null,
  terminationDate: string | null,
  today: string,
): boolean {
  const admittedByToday = admissionDate === null || admissionDate <= today;
  const stillWithinTermination = terminationDate === null || terminationDate >= today;
  return admittedByToday && stillWithinTermination;
}

/** Fornece o "hoje" usado pela derivação de `employee.active` — injetável para testes. */
export type TodayProvider = () => string;

/**
 * "Hoje" em **America/Sao_Paulo** (nunca UTC — a Edge Function roda em UTC e
 * a conversão ingênua desloca um dia, mesma armadilha documentada em
 * docs/03-integracao-secullum.md), no formato `"yyyy-MM-dd"` — comparável por
 * string com `admission_date`/`termination_date`.
 */
export const systemTodayInSaoPaulo: TodayProvider = () => {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return formatter.format(new Date());
};

/**
 * Decide o `company_status_event` (se houver) comparando o `active`
 * PERSISTIDO (lido em lote antes do upsert) com o `active` recém-derivado.
 * `previousActive = null` significa "nunca observada antes" (company nova) —
 * gera `baseline`. Retorna `null` quando nada mudou: o `CHECK` do banco
 * (`company_status_event_must_change_check`) tornaria um evento no-op
 * impossível de qualquer forma, mas o código nem tenta inserir.
 */
export function buildCompanyStatusEvent(
  previousActive: boolean | null,
  newActive: boolean,
): CompanyStatusEventFields | null {
  if (previousActive === null) {
    return { eventType: "baseline", previousActive: null, newActive };
  }
  if (previousActive === newActive) return null;
  return { eventType: newActive ? "reactivated" : "deactivated", previousActive, newActive };
}

/** Snapshot mínimo de employee usado por `buildEmployeeStatusEvent` (antes/depois). */
export interface EmployeeStatusSnapshot {
  active: boolean;
  admissionDate: string | null;
  terminationDate: string | null;
}

/**
 * Decide o `employee_status_event` (se houver), comparando o snapshot
 * PERSISTIDO (lido em lote antes do upsert) com o snapshot recém-derivado.
 * `previous = null` significa "funcionário nunca observado antes" -> `baseline`.
 *
 * Regras (docs/04-modelo-dados.md, ADR-009):
 *   - nada mudou (status e as duas datas) => `null` (nenhum evento);
 *   - status não mudou mas alguma data mudou => `date_correction` (inclui
 *     desligamento programado sendo reagendado para outra data futura);
 *   - status virou `true`:
 *       - se a ÚNICA coisa que "libertou" o funcionário foi Demissao ter sido
 *         limpa (existia e virou null) SEM nova Admissao => `reactivation`
 *         (event_date null — o Secullum não dá data para "desfazer demissão");
 *       - caso contrário => `admission` (event_date = new_admission_date,
 *         inclui a virada de uma admissão futura ao chegar o dia, mesmo sem
 *         nenhuma mudança de payload nesta execução);
 *   - status virou `false` => `termination` (event_date = new_termination_date,
 *     mesmo quando a Demissao já era conhecida e só o relógio avançou).
 */
export function buildEmployeeStatusEvent(
  previous: EmployeeStatusSnapshot | null,
  next: EmployeeStatusSnapshot,
): EmployeeStatusEventFields | null {
  if (previous === null) {
    return {
      eventType: "baseline",
      previousActive: null,
      newActive: next.active,
      eventDate: next.admissionDate,
      previousAdmissionDate: null,
      newAdmissionDate: next.admissionDate,
      previousTerminationDate: null,
      newTerminationDate: next.terminationDate,
    };
  }

  const admissionChanged = previous.admissionDate !== next.admissionDate;
  const terminationChanged = previous.terminationDate !== next.terminationDate;
  const activeChanged = previous.active !== next.active;

  if (!activeChanged && !admissionChanged && !terminationChanged) {
    return null; // no-op — rejeitado pelo CHECK do banco de qualquer forma, mas nem tentamos.
  }

  const dateFields = {
    previousAdmissionDate: previous.admissionDate,
    newAdmissionDate: next.admissionDate,
    previousTerminationDate: previous.terminationDate,
    newTerminationDate: next.terminationDate,
  };

  if (!activeChanged) {
    // Alguma data mudou, mas sem virar o status (ex.: desligamento programado
    // reagendado de uma data futura para outra data futura).
    return {
      eventType: "date_correction",
      previousActive: previous.active,
      newActive: next.active,
      eventDate: null,
      ...dateFields,
    };
  }

  if (next.active) {
    // Virou ativo: reactivation (Demissao existia e sumiu, sem nova Admissao)
    // ou admission (qualquer outro caso, inclusive admissão futura chegando).
    const terminationCleared = previous.terminationDate !== null && next.terminationDate === null;
    if (terminationCleared && !admissionChanged) {
      return {
        eventType: "reactivation",
        previousActive: previous.active,
        newActive: next.active,
        eventDate: null,
        ...dateFields,
      };
    }
    return {
      eventType: "admission",
      previousActive: previous.active,
      newActive: next.active,
      eventDate: next.admissionDate,
      ...dateFields,
    };
  }

  // Virou inativo: termination — mesmo quando Demissao não mudou nesta
  // execução e só "chegou a data" (desligamento programado).
  return {
    eventType: "termination",
    previousActive: previous.active,
    newActive: next.active,
    eventDate: next.terminationDate,
    ...dateFields,
  };
}

/** Formato estrito "HH:mm" exigido pela coluna Postgres `time` — mesmo padrão usado no diagnóstico de /Batidas. */
const TIME_PATTERN = /^\d{2}:\d{2}$/;

/**
 * Normaliza um campo posicional `EntradaN`/`SaidaN` de `Horario.Dias` para o
 * que a coluna `time` do Postgres aceita: `"HH:mm"` válido ou `null`.
 *
 * O mesmo campo, no payload real do Secullum, pode chegar em três formatos
 * (mesmo "três estados" documentado para /Batidas em ADR-007 — ver
 * docs/03-integracao-secullum.md): horário efetivo (`"HH:mm"`), texto de
 * status (ex.: rótulo de afastamento como "Férias") ou ausência de valor —
 * que por sua vez pode vir como `null`/`undefined` OU como string vazia
 * `""` (visto em produção). Qualquer coisa que não seja `"HH:mm"` vira
 * `null` — nunca lança exceção (o job não pode cair por causa de um valor
 * bruto inesperado numa coluna posicional).
 */
export function parseHorarioDiaTimeField(value: unknown): string | null {
  if (typeof value !== "string") return null;
  return TIME_PATTERN.test(value) ? value : null;
}

export function parseHorarioDia(
  workScheduleId: string,
  dia: RawHorarioDia,
  warnInvalidTime?: (fieldName: string, rawValue: unknown) => void,
): UpsertHorarioDiaInput {
  const entryFields = [
    ["Entrada1", dia.Entrada1],
    ["Entrada2", dia.Entrada2],
    ["Entrada3", dia.Entrada3],
    ["Entrada4", dia.Entrada4],
    ["Entrada5", dia.Entrada5],
  ] as const;
  const exitFields = [
    ["Saida1", dia.Saida1],
    ["Saida2", dia.Saida2],
    ["Saida3", dia.Saida3],
    ["Saida4", dia.Saida4],
    ["Saida5", dia.Saida5],
  ] as const;

  const parseField = ([fieldName, rawValue]: readonly [string, unknown]): string | null => {
    const parsed = parseHorarioDiaTimeField(rawValue);
    // Só avisa quando havia algo a descartar (não para null/undefined "normais").
    if (parsed === null && rawValue !== null && rawValue !== undefined) {
      warnInvalidTime?.(fieldName, rawValue);
    }
    return parsed;
  };

  const entries = entryFields.map(parseField);
  const exits = exitFields.map(parseField);
  const workloadMinutes = dia.Carga ?? 0;
  // Dia sem expediente: Carga = 0 E todos os 10 pares nulos (docs/03 — armadilha
  // "dia de folga vem com tolerância preenchida").
  const isDayOff = (workloadMinutes ?? 0) === 0 &&
    entries.every((e) => e === null) &&
    exits.every((e) => e === null);

  return {
    workScheduleId,
    secullumHorarioDiaId: dia.Id,
    weekday: dia.DiaSemana,
    entry1: entries[0],
    entry2: entries[1],
    entry3: entries[2],
    entry4: entries[3],
    entry5: entries[4],
    exit1: exits[0],
    exit2: exits[1],
    exit3: exits[2],
    exit4: exits[3],
    exit5: exits[4],
    entryType1: dia.TipoEntrada1 ?? null,
    entryType2: dia.TipoEntrada2 ?? null,
    entryType3: dia.TipoEntrada3 ?? null,
    entryType4: dia.TipoEntrada4 ?? null,
    entryType5: dia.TipoEntrada5 ?? null,
    exitType1: dia.TipoSaida1 ?? null,
    exitType2: dia.TipoSaida2 ?? null,
    exitType3: dia.TipoSaida3 ?? null,
    exitType4: dia.TipoSaida4 ?? null,
    exitType5: dia.TipoSaida5 ?? null,
    toleranceExtraMinutes: dia.ToleranciaExtra ?? null,
    toleranceAbsenceMinutes: dia.ToleranciaFalta ?? null,
    workloadMinutes,
    dayType: dia.TipoDia ?? null,
    isNeutral: !!dia.Neutro,
    isCompensated: !!dia.Compensado,
    freeLunch: !!dia.AlmocoLivre,
    allocate24Hours: !!dia.Alocar24Horas,
    isDayOff,
  };
}

// ---------------------------------------------------------------------------
// Árvore completa de "Horario" — parsing (ADR-011 Fase 3, migration
// 20260813162000). Cada função aqui extrai um nó aninhado de RawHorario para
// o Input de upsert/insert correspondente; a resolução da FK `horarioId`
// (uuid) fica a cargo do orquestrador (`runCadastroSync`), que só a conhece
// DEPOIS do upsert em lote de "Horario". Todo campo booleano/numérico passa
// por `asBoolean`/`asNumber` (nunca repassa valor cru); os 4 campos jsonb
// passam por `asJsonPassthrough`.
// ---------------------------------------------------------------------------

/** `Horario.Opcoes` -> `UpsertHorariosOpcoesInput` (sem `horarioId`, preenchido pelo orquestrador). */
export function parseHorarioOpcoes(
  raw: RawHorarioOpcoes,
  warnUnexpectedFieldFormat?: (fieldName: string, typeReceived: string) => void,
): Omit<UpsertHorariosOpcoesInput, "horarioId"> {
  const warnField = (fieldName: string) => (typeReceived: string) =>
    warnUnexpectedFieldFormat?.(`Opcoes.${fieldName}`, typeReceived);
  return {
    secullumHorarioId: asNumber(raw.HorarioId),
    toleranciaArtigo58: asBoolean(raw.ToleranciaArtigo58, warnField("ToleranciaArtigo58")),
    ignorarLimiteMinimoCasoBatidaGerarExtrasSuperiorATolerancia: asBoolean(
      raw.IgnorarLimiteMinimoCasoBatidaGerarExtrasSuperiorATolerancia,
      warnField("IgnorarLimiteMinimoCasoBatidaGerarExtrasSuperiorATolerancia"),
    ),
    ignorarLimiteMinimoCasoBatidaGerarFaltasSuperiorATolerancia: asBoolean(
      raw.IgnorarLimiteMinimoCasoBatidaGerarFaltasSuperiorATolerancia,
      warnField("IgnorarLimiteMinimoCasoBatidaGerarFaltasSuperiorATolerancia"),
    ),
    qualquerMinutoAdiantadoComoExtra: asBoolean(
      raw.QualquerMinutoAdiantadoComoExtra,
      warnField("QualquerMinutoAdiantadoComoExtra"),
    ),
    qualquerMinutoAtrasadoComoFalta: asBoolean(
      raw.QualquerMinutoAtrasadoComoFalta,
      warnField("QualquerMinutoAtrasadoComoFalta"),
    ),
    descontarToleranciaDasHorasExtras: asBoolean(
      raw.DescontarToleranciaDasHorasExtras,
      warnField("DescontarToleranciaDasHorasExtras"),
    ),
    descontarToleranciaDasHorasFaltas: asBoolean(
      raw.DescontarToleranciaDasHorasFaltas,
      warnField("DescontarToleranciaDasHorasFaltas"),
    ),
    usarToleranciaRefeicoes: asBoolean(
      raw.UsarToleranciaRefeicoes,
      warnField("UsarToleranciaRefeicoes"),
    ),
    toleranciaRefeicoesMinutos: asNumber(raw.ToleranciaRefeicoesMinutos),
    limiteMinimoDeFaltasNoDiaMinutos: asNumber(raw.LimiteMinimoDeFaltasNoDiaMinutos),
    limiteMinimoDeExtrasNoDiaMinutos: asNumber(raw.LimiteMinimoDeExtrasNoDiaMinutos),
    substituirBatidasAbaixoDasTolerancias: asBoolean(
      raw.SubstituirBatidasAbaixoDasTolerancias,
      warnField("SubstituirBatidasAbaixoDasTolerancias"),
    ),
    alocarHorario24Horas: asBoolean(raw.AlocarHorario24Horas, warnField("AlocarHorario24Horas")),
    alocarBatidas: asNumber(raw.AlocarBatidas),
    naoDescontarFaltasDeNormais: asBoolean(
      raw.NaoDescontarFaltasDeNormais,
      warnField("NaoDescontarFaltasDeNormais"),
    ),
    preencherFaltasQuandoDiaEstiverEmBranco: asBoolean(
      raw.PreencherFaltasQuandoDiaEstiverEmBranco,
      warnField("PreencherFaltasQuandoDiaEstiverEmBranco"),
    ),
    tipoPreencherQuandoDiaEstiverEmBranco: asNumber(raw.TipoPreencherQuandoDiaEstiverEmBranco),
    calcularFaltasSomenteParaDiaInteiro: asBoolean(
      raw.CalcularFaltasSomenteParaDiaInteiro,
      warnField("CalcularFaltasSomenteParaDiaInteiro"),
    ),
    exibirColunaHorasRepousoFaltantesTrabalhoContinuo: asBoolean(
      raw.ExibirColunaHorasRepousoFaltantesTrabalhoContinuo,
      warnField("ExibirColunaHorasRepousoFaltantesTrabalhoContinuo"),
    ),
    horasRepousoConfiguracaoPadrao: asBoolean(
      raw.HorasRepousoConfiguracaoPadrao,
      warnField("HorasRepousoConfiguracaoPadrao"),
    ),
    horasRepousoFaixas: asJsonPassthrough(raw.HorasRepousoFaixas),
    completarBatidasFaltantes: asBoolean(
      raw.CompletarBatidasFaltantes,
      warnField("CompletarBatidasFaltantes"),
    ),
    permitirFolgasAutomaticas: asBoolean(
      raw.PermitirFolgasAutomaticas,
      warnField("PermitirFolgasAutomaticas"),
    ),
    quantidadeFolgasAutomaticas: asNumber(raw.QuantidadeFolgasAutomaticas),
    colunasRefeicao: asNumber(raw.ColunasRefeicao),
    sinalizarEmVermelhoAlmocosCurtos: asBoolean(
      raw.SinalizarEmVermelhoAlmocosCurtos,
      warnField("SinalizarEmVermelhoAlmocosCurtos"),
    ),
    naoCalcularNenhumaHoraNoturna: asBoolean(
      raw.NaoCalcularNenhumaHoraNoturna,
      warnField("NaoCalcularNenhumaHoraNoturna"),
    ),
    separarHorasNoturnasDeHorasNormais: asBoolean(
      raw.SepararHorasNoturnasDeHorasNormais,
      warnField("SepararHorasNoturnasDeHorasNormais"),
    ),
    incluirIntervaloNoAdicionalNoturno: asBoolean(
      raw.IncluirIntervaloNoAdicionalNoturno,
      warnField("IncluirIntervaloNoAdicionalNoturno"),
    ),
    periodoEspecialAdicionalNoturnoInicio: asString(raw.PeriodoEspecialAdicionalNoturnoInicio),
    periodoEspecialAdicionalNoturnoFim: asString(raw.PeriodoEspecialAdicionalNoturnoFim),
    considerarFeriadosComoHoraExtra: asBoolean(
      raw.ConsiderarFeriadosComoHoraExtra,
      warnField("ConsiderarFeriadosComoHoraExtra"),
    ),
    usarTempoMaisMenosCargaSuperior: asBoolean(
      raw.UsarTempoMaisMenosCargaSuperior,
      warnField("UsarTempoMaisMenosCargaSuperior"),
    ),
    percentualCargaUsarTempoMaisMenosMinutos: asNumber(
      raw.PercentualCargaUsarTempoMaisMenosMinutos,
    ),
    definirCargaAutomaticamente: asBoolean(
      raw.DefinirCargaAutomaticamente,
      warnField("DefinirCargaAutomaticamente"),
    ),
    carga: asNumber(raw.Carga),
    desconsiderarNeutroQuandoHouverBatidasNoDia: asBoolean(
      raw.DesconsiderarNeutroQuandoHouverBatidasNoDia,
      warnField("DesconsiderarNeutroQuandoHouverBatidasNoDia"),
    ),
    usarDataFechamentoEncerrarSemana: asBoolean(
      raw.UsarDataFechamentoEncerrarSemana,
      warnField("UsarDataFechamentoEncerrarSemana"),
    ),
    compensacao: asNumber(raw.Compensacao),
    compensacaoIgnorarSabados: asBoolean(
      raw.CompensacaoIgnorarSabados,
      warnField("CompensacaoIgnorarSabados"),
    ),
    compensacaoIgnorarDomingos: asBoolean(
      raw.CompensacaoIgnorarDomingos,
      warnField("CompensacaoIgnorarDomingos"),
    ),
    compensacaoIgnorarFeriados: asBoolean(
      raw.CompensacaoIgnorarFeriados,
      warnField("CompensacaoIgnorarFeriados"),
    ),
    compensacaoIgnorarFolgas: asBoolean(
      raw.CompensacaoIgnorarFolgas,
      warnField("CompensacaoIgnorarFolgas"),
    ),
    compensacaoMensalFechamento: asJsonPassthrough(raw.CompensacaoMensalFechamento),
    compensacaoCalcularHorasComoNormaisCompatibilidadePontoOff: asBoolean(
      raw.CompensacaoCalcularHorasComoNormaisCompatibilidadePontoOff,
      warnField("CompensacaoCalcularHorasComoNormaisCompatibilidadePontoOff"),
    ),
    calcularNoturnasIndependenteCompensado: asBoolean(
      raw.CalcularNoturnasIndependenteCompensado,
      warnField("CalcularNoturnasIndependenteCompensado"),
    ),
    calcularBatidasIntermediarias: asBoolean(
      raw.CalcularBatidasIntermediarias,
      warnField("CalcularBatidasIntermediarias"),
    ),
    naoCalcularHorasFaltaBatidasIntermediarias: asBoolean(
      raw.NaoCalcularHorasFaltaBatidasIntermediarias,
      warnField("NaoCalcularHorasFaltaBatidasIntermediarias"),
    ),
    listaHorasSobreAviso: asJsonPassthrough(raw.ListaHorasSobreAviso),
    calcularHorasInItinere: asBoolean(
      raw.CalcularHorasInItinere,
      warnField("CalcularHorasInItinere"),
    ),
    listaHorasInItinere: asJsonPassthrough(raw.ListaHorasInItinere),
    somarHorasInItinereNormais: asBoolean(
      raw.SomarHorasInItinereNormais,
      warnField("SomarHorasInItinereNormais"),
    ),
    calcularHorasInItinereIninterruptas: asBoolean(
      raw.CalcularHorasInItinereIninterruptas,
      warnField("CalcularHorasInItinereIninterruptas"),
    ),
  };
}

/** `Horario.Extras` -> `UpsertHorarioExtrasInput` (sem `horarioId`, preenchido pelo orquestrador). */
export function parseHorarioExtras(
  raw: RawHorarioExtras,
  warnUnexpectedFieldFormat?: (fieldName: string, typeReceived: string) => void,
): Omit<UpsertHorarioExtrasInput, "horarioId"> {
  const warnField = (fieldName: string) => (typeReceived: string) =>
    warnUnexpectedFieldFormat?.(`Extras.${fieldName}`, typeReceived);
  return {
    secullumHorarioId: asNumber(raw.HorarioId),
    agruparExtras: asBoolean(raw.AgruparExtras, warnField("AgruparExtras")),
    somenteGrupoExtras: asBoolean(raw.SomenteGrupoExtras, warnField("SomenteGrupoExtras")),
    descontarFaltasExtras: asNumber(raw.DescontarFaltasExtras),
    descontarFaltasExtrasNoturnas: asBoolean(
      raw.DescontarFaltasExtrasNoturnas,
      warnField("DescontarFaltasExtrasNoturnas"),
    ),
    descontarIgnorarUteis: asBoolean(
      raw.DescontarIgnorarUteis,
      warnField("DescontarIgnorarUteis"),
    ),
    descontarIgnorarSabados: asBoolean(
      raw.DescontarIgnorarSabados,
      warnField("DescontarIgnorarSabados"),
    ),
    descontarIgnorarDomingos: asBoolean(
      raw.DescontarIgnorarDomingos,
      warnField("DescontarIgnorarDomingos"),
    ),
    descontarIgnorarFeriados: asBoolean(
      raw.DescontarIgnorarFeriados,
      warnField("DescontarIgnorarFeriados"),
    ),
    descontarIgnorarFolgas: asBoolean(
      raw.DescontarIgnorarFolgas,
      warnField("DescontarIgnorarFolgas"),
    ),
    descontarIgnorarDiaEspecial: asBoolean(
      raw.DescontarIgnorarDiaEspecial,
      warnField("DescontarIgnorarDiaEspecial"),
    ),
    usarInterjornada: asBoolean(raw.UsarInterjornada, warnField("UsarInterjornada")),
    // ⛔ Interjornada NUNCA passa por asBoolean — divergência confirmada do
    // manual, o valor real é STRING (ver RawHorarioExtras.Interjornada).
    interjornada: asString(raw.Interjornada),
    interjornadaSeparada: asBoolean(
      raw.InterjornadaSeparada,
      warnField("InterjornadaSeparada"),
    ),
    interjornadaSeparadaBancoHoras: asBoolean(
      raw.InterjornadaSeparadaBancoHoras,
      warnField("InterjornadaSeparadaBancoHoras"),
    ),
    separarExtrasNoturnasDeExtrasNormais: asBoolean(
      raw.SepararExtrasNoturnasDeExtrasNormais,
      warnField("SepararExtrasNoturnasDeExtrasNormais"),
    ),
    separarExtrasIntervalosDeExtrasNormais: asBoolean(
      raw.SepararExtrasIntervalosDeExtrasNormais,
      warnField("SepararExtrasIntervalosDeExtrasNormais"),
    ),
    separarSomatoriaAposMeiaNoite: asBoolean(
      raw.SepararSomatoriaAposMeiaNoite,
      warnField("SepararSomatoriaAposMeiaNoite"),
    ),
    multiplicarExtrasPeloPercentual: asBoolean(
      raw.MultiplicarExtrasPeloPercentual,
      warnField("MultiplicarExtrasPeloPercentual"),
    ),
    habilitarMultiplicadorFaixaBancoHoras: asBoolean(
      raw.HabilitarMultiplicadorFaixaBancoHoras,
      warnField("HabilitarMultiplicadorFaixaBancoHoras"),
    ),
    multiplicarSomenteSaldoPositivo: asBoolean(
      raw.MultiplicarSomenteSaldoPositivo,
      warnField("MultiplicarSomenteSaldoPositivo"),
    ),
    naoDividirExtrasEmFeriados: asBoolean(
      raw.NaoDividirExtrasEmFeriados,
      warnField("NaoDividirExtrasEmFeriados"),
    ),
    naoDividirExtrasEmDomingos: asBoolean(
      raw.NaoDividirExtrasEmDomingos,
      warnField("NaoDividirExtrasEmDomingos"),
    ),
    dividirJornadaQuandoHouverFolga: asBoolean(
      raw.DividirJornadaQuandoHouverFolga,
      warnField("DividirJornadaQuandoHouverFolga"),
    ),
    naoDividirJornadaEmFeriados: asBoolean(
      raw.NaoDividirJornadaEmFeriados,
      warnField("NaoDividirJornadaEmFeriados"),
    ),
    naoDividirJornadaEmFolgas: asBoolean(
      raw.NaoDividirJornadaEmFolgas,
      warnField("NaoDividirJornadaEmFolgas"),
    ),
    apenasDividirJornadaFeriadoFolgaDiaSeguinte: asBoolean(
      raw.ApenasDividirJornadaFeriadoFolgaDiaSeguinte,
      warnField("ApenasDividirJornadaFeriadoFolgaDiaSeguinte"),
    ),
    naoReiniciarDivisoesExtrasDiurnasNoturnas: asBoolean(
      raw.NaoReiniciarDivisoesExtrasDiurnasNoturnas,
      warnField("NaoReiniciarDivisoesExtrasDiurnasNoturnas"),
    ),
    controleHorasExtrasAutorizadas: asBoolean(
      raw.ControleHorasExtrasAutorizadas,
      warnField("ControleHorasExtrasAutorizadas"),
    ),
    quantidadeExtrasAutorizadas: asString(raw.QuantidadeExtrasAutorizadas),
    acumulo: asNumber(raw.Acumulo),
  };
}

/** `Horario.Descanso` -> `UpsertHorarioDescansoInput` (sem `horarioId`, preenchido pelo orquestrador). */
export function parseHorarioDescanso(
  raw: RawHorarioDescanso,
  warnUnexpectedFieldFormat?: (fieldName: string, typeReceived: string) => void,
): Omit<UpsertHorarioDescansoInput, "horarioId"> {
  const warnField = (fieldName: string) => (typeReceived: string) =>
    warnUnexpectedFieldFormat?.(`Descanso.${fieldName}`, typeReceived);
  return {
    secullumHorarioId: asNumber(raw.HorarioId),
    tipo: asNumber(raw.Tipo),
    valorDescanso: asString(raw.ValorDescanso),
    limiteHorasFaltas: asString(raw.LimiteHorasFaltas),
    incluirFeriado: asNumber(raw.IncluirFeriado),
    feriadoDomingoApenasUmDescanso: asBoolean(
      raw.FeriadoDomingoApenasUmDescanso,
      warnField("FeriadoDomingoApenasUmDescanso"),
    ),
    descontarFeriadosCasoFaltas: asBoolean(
      raw.DescontarFeriadosCasoFaltas,
      warnField("DescontarFeriadosCasoFaltas"),
    ),
    naoDescontarAntesAdmissao: asBoolean(
      raw.NaoDescontarAntesAdmissao,
      warnField("NaoDescontarAntesAdmissao"),
    ),
    naoDescontarDuranteAfastamento: asBoolean(
      raw.NaoDescontarDuranteAfastamento,
      warnField("NaoDescontarDuranteAfastamento"),
    ),
  };
}

/** Item de `Descanso.Faixas` -> `InsertHorarioDescansoFaixaItemInput` (sem `horarioDescansoId`, resolvido pelo orquestrador após o upsert do pai). */
export function parseHorarioDescansoFaixaItem(
  raw: RawHorarioDescansoFaixaItem,
): Omit<InsertHorarioDescansoFaixaItemInput, "horarioDescansoId"> {
  return {
    ordem: asNumber(raw.Ordem),
    limite: asString(raw.Limite),
    desconto: asString(raw.Desconto),
  };
}

/** Um grupo `Horario.FaixasExtras[i]` -> `InsertHorarioFaixasExtrasInput` (sem `horarioId`, preenchido pelo orquestrador). */
export function parseHorarioFaixasExtrasGroup(
  raw: RawHorarioFaixasExtras,
): Omit<InsertHorarioFaixasExtrasInput, "horarioId"> {
  return {
    secullumHorarioId: asNumber(raw.HorarioId),
    diaSemana: asNumber(raw.DiaSemana),
    controle: asNumber(raw.Controle),
    diaEspecial: asNumber(raw.DiaEspecial),
  };
}

/** Item de `FaixasExtras.Faixas` -> `InsertHorarioFaixasExtrasItemInput` (sem `horarioFaixasExtrasId`, resolvido pelo orquestrador após o insert do grupo). */
export function parseHorarioFaixasExtrasItem(
  raw: RawHorarioFaixasExtrasItem,
): Omit<InsertHorarioFaixasExtrasItemInput, "horarioFaixasExtrasId"> {
  return {
    ordem: asNumber(raw.Ordem),
    horas: asNumber(raw.Horas),
    coluna: asNumber(raw.Coluna),
  };
}

/** Item de `ToleranciaEspecifica.Tolerancias` -> `InsertHorarioToleranciaEspecificaItemInput` (sem `horarioToleranciaEspecificaId`, resolvido pelo orquestrador). Campos `EntradaNDe/Ate`/`SaidaNDe/Ate` parseados com a mesma disciplina estrita "HH:mm" de `parseHorarioDiaTimeField` (coluna Postgres `time`). */
export function parseHorarioToleranciaEspecificaItem(
  raw: RawHorarioToleranciaEspecificaItem,
  warnInvalidTime?: (fieldName: string, rawValue: unknown) => void,
): Omit<InsertHorarioToleranciaEspecificaItemInput, "horarioToleranciaEspecificaId"> {
  const parseTime = (fieldName: string, rawValue: unknown): string | null => {
    const parsed = parseHorarioDiaTimeField(rawValue);
    if (parsed === null && rawValue !== null && rawValue !== undefined) {
      warnInvalidTime?.(fieldName, rawValue);
    }
    return parsed;
  };
  return {
    secullumHorarioId: asNumber(raw.HorarioId),
    diaSemana: asNumber(raw.DiaSemana),
    entrada1De: parseTime("Entrada1De", raw.Entrada1De),
    entrada1Ate: parseTime("Entrada1Ate", raw.Entrada1Ate),
    saida1De: parseTime("Saida1De", raw.Saida1De),
    saida1Ate: parseTime("Saida1Ate", raw.Saida1Ate),
    entrada2De: parseTime("Entrada2De", raw.Entrada2De),
    entrada2Ate: parseTime("Entrada2Ate", raw.Entrada2Ate),
    saida2De: parseTime("Saida2De", raw.Saida2De),
    saida2Ate: parseTime("Saida2Ate", raw.Saida2Ate),
    entrada3De: parseTime("Entrada3De", raw.Entrada3De),
    entrada3Ate: parseTime("Entrada3Ate", raw.Entrada3Ate),
    saida3De: parseTime("Saida3De", raw.Saida3De),
    saida3Ate: parseTime("Saida3Ate", raw.Saida3Ate),
    entrada4De: parseTime("Entrada4De", raw.Entrada4De),
    entrada4Ate: parseTime("Entrada4Ate", raw.Entrada4Ate),
    saida4De: parseTime("Saida4De", raw.Saida4De),
    saida4Ate: parseTime("Saida4Ate", raw.Saida4Ate),
    entrada5De: parseTime("Entrada5De", raw.Entrada5De),
    entrada5Ate: parseTime("Entrada5Ate", raw.Entrada5Ate),
    saida5De: parseTime("Saida5De", raw.Saida5De),
    saida5Ate: parseTime("Saida5Ate", raw.Saida5Ate),
  };
}

// ---------------------------------------------------------------------------
// Afastamentos e férias — ADR-010 (2026-08-13).
// GET /FuncionariosAfastamentos, 5º e último endpoint do escopo. Sem
// FuncionarioId: correlação em memória por NumeroPis (prioridade) com
// fallback para Cpf, sobre os `employee` já resolvidos neste mesmo ciclo.
// ---------------------------------------------------------------------------

/** Campos extraídos de um `FuncionarioAfastamento` — allow-list (`Motivo` nunca é lido, ver RawFuncionarioAfastamento). */
export interface ParsedAfastamento {
  secullumAfastamentoId: number;
  /** PII — usado SÓ EM MEMÓRIA para correlação (ver `resolveAbsenceEmployeeMatch`); nunca persistido. */
  numeroPis: string | null;
  /** PII — usado SÓ EM MEMÓRIA para correlação (fallback); nunca persistido. */
  cpf: string | null;
  /** Valor bruto de `Inicio` — parseado por `parseAbsenceWindow`, nunca por `Date`/UTC. */
  inicio: unknown;
  /** Valor bruto de `Fim` — mesma regra de `inicio`. */
  fim: unknown;
  justificationCode: string | null;
  secullumIncludedAt: string | null;
}

/**
 * Allow-list explícita de `RawFuncionarioAfastamento` — mesmo padrão de
 * `parseFuncionarioAllowList`. `Motivo` (ADR-010, decisão de LGPD) nunca
 * aparece nesta função nem no tipo de origem: não há como lê-lo por engano.
 */
export function parseFuncionarioAfastamentoAllowList(
  raw: RawFuncionarioAfastamento,
): ParsedAfastamento {
  return {
    secullumAfastamentoId: raw.Id,
    numeroPis: raw.NumeroPis ?? null,
    cpf: raw.Cpf ?? null,
    inicio: raw.Inicio,
    fim: raw.Fim,
    justificationCode: raw.JustificativaNome ?? null,
    secullumIncludedAt: typeof raw.DataInclusao === "string" ? raw.DataInclusao : null,
  };
}

/**
 * Remove tudo que não for dígito — comparação de `NumeroPis`/`Cpf` é sempre
 * sobre dígitos (strip de máscara/pontuação), nos dois lados
 * (docs/03-integracao-secullum.md). String vazia/`null`/`undefined` viram
 * `""`, tratados como AUSENTES pelos chamadores (nunca como valor).
 */
export function stripNonDigits(value: string | null | undefined): string {
  if (!value) return "";
  return value.replace(/\D/g, "");
}

/** Índice dígitos-do-identificador -> employeeId(s) candidato(s), construído sobre os `employee` já resolvidos neste ciclo. */
export type EmployeeIdentifierIndex = Map<string, string[]>;

export function buildEmployeeIdentifierIndex(
  entries: Array<{ employeeId: string; identifier: string | null }>,
): EmployeeIdentifierIndex {
  const index: EmployeeIdentifierIndex = new Map();
  for (const { employeeId, identifier } of entries) {
    const digits = stripNonDigits(identifier);
    if (!digits) continue; // "" é ausente, nunca valor.
    const list = index.get(digits) ?? [];
    list.push(employeeId);
    index.set(digits, list);
  }
  return index;
}

export type AbsenceEmployeeMatch =
  | { outcome: "unique"; employeeId: string; matchedBy: "pis" | "cpf" }
  | { outcome: "zero" }
  | { outcome: "multiple"; count: number };

/**
 * Resolve o `employee_id` de um afastamento por `NumeroPis` (prioridade) com
 * fallback para `Cpf` — mesma prioridade que o manual do Secullum descreve
 * para os parâmetros de filtro `funcionarioPis`/`funcionarioCpf` desta rota
 * (docs/03-integracao-secullum.md, ADR-010 Decisão 4).
 *
 * PIS resolve para exatamente 1 candidato -> usa PIS. Caso contrário (PIS
 * ausente, 0 ou 2+ candidatos por PIS) tenta CPF: 1 candidato -> usa CPF; 0
 * ou 2+ -> abstenção. Sem CPF disponível para tentar, o resultado do PIS
 * (0 ou 2+) é o resultado final. **Nunca escolhe um candidato arbitrariamente.**
 */
export function resolveAbsenceEmployeeMatch(
  pisIndex: EmployeeIdentifierIndex,
  cpfIndex: EmployeeIdentifierIndex,
  numeroPis: string | null | undefined,
  cpf: string | null | undefined,
): AbsenceEmployeeMatch {
  const pisDigits = stripNonDigits(numeroPis);
  if (pisDigits) {
    const candidates = pisIndex.get(pisDigits) ?? [];
    if (candidates.length === 1) {
      return { outcome: "unique", employeeId: candidates[0], matchedBy: "pis" };
    }
  }

  const cpfDigits = stripNonDigits(cpf);
  if (cpfDigits) {
    const candidates = cpfIndex.get(cpfDigits) ?? [];
    if (candidates.length === 1) {
      return { outcome: "unique", employeeId: candidates[0], matchedBy: "cpf" };
    }
    if (candidates.length >= 2) return { outcome: "multiple", count: candidates.length };
    return { outcome: "zero" };
  }

  if (pisDigits) {
    const candidates = pisIndex.get(pisDigits) ?? [];
    if (candidates.length >= 2) return { outcome: "multiple", count: candidates.length };
  }

  return { outcome: "zero" };
}

export type AbsenceWindowParseResult =
  | { outcome: "ok"; startDate: string; endDate: string }
  | { outcome: "unparseable" }
  | { outcome: "invalid_range"; startDate: string; endDate: string };

/**
 * Parseia `Inicio`/`Fim` de um afastamento (pelos 10 primeiros caracteres,
 * via `parseSecullumDateOnly` — nunca `Date`/UTC) e valida o intervalo.
 * `Fim < Inicio` não é um erro de parsing — é dado ruim de origem: o
 * resultado é `invalid_range`, e é o CHAMADOR quem decide não gravar a linha
 * e logar `absence_invalid_range` (a tabela não tem `CHECK` de propósito,
 * ver ADR-010 Decisão 3 — um único registro invertido não pode derrubar o job).
 */
export function parseAbsenceWindow(inicio: unknown, fim: unknown): AbsenceWindowParseResult {
  const startDate = parseSecullumDateOnly(inicio);
  const endDate = parseSecullumDateOnly(fim);
  if (!startDate || !endDate) return { outcome: "unparseable" };
  if (endDate < startDate) return { outcome: "invalid_range", startDate, endDate };
  return { outcome: "ok", startDate, endDate };
}

/** Uma janela de afastamento mínima para o cálculo de on_leave (id + intervalo, ambos inclusivos). */
export interface AbsenceWindowForLeaveCalc {
  id: string;
  startDate: string;
  endDate: string;
}

export interface LeaveStatus {
  onLeave: boolean;
  currentAbsenceId: string | null;
  /** `true` quando mais de um período cobre "hoje" — o chamador deve logar `absence_overlap`. */
  overlapping: boolean;
}

/**
 * `employee.on_leave`/`current_absence_id` (ADR-010): `true` quando "hoje"
 * (data injetada — America/Sao_Paulo, nunca UTC, mesma armadilha de
 * `deriveEmployeeActive`) cai dentro de `[startDate, endDate]` (ambos
 * inclusivos) de algum período. Havendo sobreposição, aponta o de maior
 * `endDate` — critério determinístico, nunca escolha arbitrária.
 */
export function computeEmployeeLeaveStatus(
  absences: AbsenceWindowForLeaveCalc[],
  today: string,
): LeaveStatus {
  const covering = absences.filter((a) => a.startDate <= today && today <= a.endDate);
  if (covering.length === 0) {
    return { onLeave: false, currentAbsenceId: null, overlapping: false };
  }
  const chosen = covering.reduce((best, current) =>
    current.endDate > best.endDate ? current : best
  );
  return { onLeave: true, currentAbsenceId: chosen.id, overlapping: covering.length > 1 };
}

/** Chave de correlação `(employee_id, secullum_afastamento_id)` — mesma chave composta da constraint do banco (ADR-010, Decisão 3). */
function absenceKey(employeeId: string, secullumAfastamentoId: number): string {
  return `${employeeId}:${secullumAfastamentoId}`;
}

/**
 * `dataInicio` fixo da janela de `GET /FuncionariosAfastamentos` — bem
 * anterior a qualquer cadastro real deste cliente (ver
 * `computeAfastamentosDateRange` abaixo).
 */
const AFASTAMENTOS_DATA_INICIO = "2000-01-01";

/** Quantos anos à frente de "hoje" o `dataFim` da janela de afastamentos cobre — ver `computeAfastamentosDateRange`. */
const AFASTAMENTOS_HORIZON_YEARS = 5;

/**
 * Janela FIXA e larga de `dataInicio`/`dataFim` para `GET
 * /FuncionariosAfastamentos` (ADR-010).
 *
 * ⚠️ Correção de 2026-08-13, pós-deploy real: a suposição original deste
 * módulo ("chamada sem filtro, como `/Horarios`") estava ERRADA. Diagnóstico
 * direto contra o Secullum real (GET-only, janela conservadora, ver "regra
 * de ouro" em docs/03-integracao-secullum.md) confirmou que esta rota EXIGE
 * `dataInicio`/`dataFim` — sem eles o Secullum responde HTTP 400, que o
 * client traduzia em "Secullum validation error: corpo de erro vazio/
 * inesperado" (o 400 desta rota não vem no formato usual
 * `[{Property, Message}]`).
 *
 * Ao mesmo tempo, o mesmo diagnóstico mostrou que a rota **não** tem limite
 * prático de intervalo (diferente de `Calcular`, com limite documentado de 1
 * mês e 100 req/hora): `dataInicio=2024-01-01&dataFim=2026-12-31` e
 * `dataInicio=2000-01-01&dataFim=2035-12-31` devolveram exatamente a mesma
 * contagem de registros no cliente testado. Por isso este módulo usa uma
 * janela FIXA e larga o suficiente para cobrir todo o histórico e qualquer
 * afastamento futuro já programado, em vez de uma janela deslizante (que só
 * faria sentido havendo limite de intervalo, como em `/Batidas`).
 *
 * `dataFim` é calculado a partir de `today` (mesmo `TodayProvider`/
 * `systemTodayInSaoPaulo` usado pelo resto deste módulo) — nunca um ano
 * hardcoded, que expiraria.
 */
export function computeAfastamentosDateRange(
  todayStr: string,
): { dataInicio: string; dataFim: string } {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(todayStr);
  // Defensivo: `todayStr` sempre vem de um TodayProvider no formato
  // "yyyy-MM-dd", mas um provider customizado (ex.: em teste) não deve
  // derrubar o job por um formato inesperado — cai num dataFim = todayStr
  // bruto, sem o horizonte de anos, em vez de lançar exceção.
  if (!match) return { dataInicio: AFASTAMENTOS_DATA_INICIO, dataFim: todayStr };
  const [, year, month, day] = match;
  const dataFim = `${
    (Number(year) + AFASTAMENTOS_HORIZON_YEARS)
      .toString()
      .padStart(4, "0")
  }-${month}-${day}`;
  return { dataInicio: AFASTAMENTOS_DATA_INICIO, dataFim };
}

// ---------------------------------------------------------------------------
// Orquestrador principal.
// ---------------------------------------------------------------------------

export async function runCadastroSync(
  secullum: SecullumReader,
  repo: SyncRepository,
  logger: SyncLogger = consoleSyncLogger,
  // ADR-009: "hoje" injetável (em vez de `new Date()` direto no meio da
  // lógica) para que os testes controlem a data usada por
  // `deriveEmployeeActive` sem depender do relógio real.
  today: TodayProvider = systemTodayInSaoPaulo,
): Promise<SyncSummary> {
  const summary = emptySummary();
  // Resolvido UMA única vez no início da execução — todas as comparações
  // "ativo hoje?" desta sincronização usam o MESMO "hoje", mesmo que a
  // execução leve alguns segundos.
  const todayStr = today();

  // Aviso com cap por código (ver WARNING_SAMPLE_CAP) — protege memória/log
  // contra um cadastro com muitas ocorrências do mesmo tipo de aviso.
  const warningCounts = new Map<string, number>();
  const warn = (code: string, message: string) => {
    const count = (warningCounts.get(code) ?? 0) + 1;
    warningCounts.set(code, count);
    if (count > WARNING_SAMPLE_CAP) return; // contabilizado, mas não mantido/logado individualmente
    summary.warnings.push({ code, message });
    logger.warn(message);
  };
  const flushSuppressedWarnings = () => {
    for (const [code, count] of warningCounts) {
      if (count <= WARNING_SAMPLE_CAP) continue;
      const suppressed = count - WARNING_SAMPLE_CAP;
      const message =
        `Aviso "${code}" ocorreu ${count} vez(es) nesta execução — exibidas as primeiras ${WARNING_SAMPLE_CAP}; ` +
        `${suppressed} ocorrência(s) adicional(is) suprimida(s) do log/summary para não sobrecarregar a resposta.`;
      summary.warnings.push({ code: `${code}_suppressed_count`, message });
      logger.warn(message);
    }
  };

  // 1) Funcionarios — buscado uma única vez nesta execução; reaproveitado
  // tanto para derivar `company` (a partir do objeto `Empresa` aninhado,
  // igual a `Departamento`/`Estrutura`) quanto pelas fases 3.a/3.b/3.c
  // abaixo. Nenhuma chamada a GET /Empresas: `Funcionario.Empresa` já traz
  // tudo que `company` precisa (Documento, Nome).
  const funcionarios = await secullum.get<RawFuncionario[]>("Funcionarios");
  summary.employeesFetched = funcionarios.length;

  // 1.0) "Cidade" / "Funcao" (ADR-011) — resolvidos ANTES de company/employee,
  // porque ambos precisam da FK (cidade_id/funcao_id) já pronta. Deduplicado
  // por "Descricao" em memória (um único upsert em lote por tabela, nunca um
  // upsert por funcionário/empresa). "Cidade" é coletada tanto de
  // `Funcionario.Cidade` quanto de `Funcionario.Empresa.Cidade` — podem ser
  // cidades DIFERENTES, cada uma resolvida independentemente (ver ADR-011).
  const cidadeInputByDescricao = new Map<string, UpsertCidadeInput>();
  const funcaoInputByDescricao = new Map<string, UpsertFuncaoInput>();
  for (const raw of funcionarios) {
    const funcionarioCidade = extractCidadeNode(raw.Cidade);
    if (funcionarioCidade && !cidadeInputByDescricao.has(funcionarioCidade.descricao)) {
      cidadeInputByDescricao.set(funcionarioCidade.descricao, {
        descricao: funcionarioCidade.descricao,
        secullumCidadeId: funcionarioCidade.secullumCidadeId,
      });
    }
    const empresaCidade = extractCidadeNode(raw.Empresa?.Cidade);
    if (empresaCidade && !cidadeInputByDescricao.has(empresaCidade.descricao)) {
      cidadeInputByDescricao.set(empresaCidade.descricao, {
        descricao: empresaCidade.descricao,
        secullumCidadeId: empresaCidade.secullumCidadeId,
      });
    }
    const funcao = extractFuncaoNode(raw.Funcao);
    if (funcao && !funcaoInputByDescricao.has(funcao.descricao)) {
      funcaoInputByDescricao.set(funcao.descricao, {
        descricao: funcao.descricao,
        secullumFuncaoId: funcao.secullumFuncaoId,
      });
    }
  }
  const cidadeInputs = [...cidadeInputByDescricao.values()];
  const funcaoInputs = [...funcaoInputByDescricao.values()];
  const cidadeRows = cidadeInputs.length ? await repo.upsertCities(cidadeInputs) : [];
  summary.citiesUpserted = cidadeRows.length;
  const cidadeByDescricao = new Map(cidadeRows.map((c) => [c.descricao, c]));
  const funcaoRows = funcaoInputs.length ? await repo.upsertFunctions(funcaoInputs) : [];
  summary.functionsUpserted = funcaoRows.length;
  const funcaoByDescricao = new Map(funcaoRows.map((f) => [f.descricao, f]));

  // 1.a) Funcionario.Empresa (aninhado) -> company (upsert em lote,
  // deduplicado por `Documento` — mesma chave natural de idempotência
  // `secullum_documento`/`company_secullum_documento_key` de quando a
  // company vinha de um GET /Empresas separado). Um funcionário sem objeto
  // `Empresa` aninhado, ou com `Empresa` sem `Documento`, não bloqueia o
  // job: fica sem company resolvida e é contabilizado/avisado na fase de
  // employee (3.c) abaixo — mesmo padrão já usado para "unit não
  // encontrada" logo ali.
  const companyInputs: UpsertEmpresaInput[] = [];
  const seenCompanyDocumentos = new Set<string>();
  const warnedEmpresaIdsMissingDocumento = new Set<number>();
  const warnedEmpresaIdsDesativadaFormat = new Set<number>();
  for (const raw of funcionarios) {
    const empresa = raw.Empresa;
    if (!empresa) continue;
    if (!empresa.Documento) {
      // Deduplicado por Empresa.Id (não por funcionário): evita um aviso por
      // funcionário quando muitos compartilham a mesma empresa mal cadastrada.
      if (!warnedEmpresaIdsMissingDocumento.has(empresa.Id)) {
        warnedEmpresaIdsMissingDocumento.add(empresa.Id);
        warn(
          "company_missing_documento",
          `Empresa secullum_id=${empresa.Id}: sem Documento — não sincronizada (chave natural obrigatória).`,
        );
      }
      continue;
    }
    if (seenCompanyDocumentos.has(empresa.Documento)) continue;
    seenCompanyDocumentos.add(empresa.Documento);
    // ADR-009: active = NOT Empresa.Desativada (era fixo em `true`).
    const active = deriveCompanyActive(empresa.Desativada, (typeReceived) => {
      if (warnedEmpresaIdsDesativadaFormat.has(empresa.Id)) return;
      warnedEmpresaIdsDesativadaFormat.add(empresa.Id);
      warn(
        "company_desativada_unexpected_format",
        `Empresa secullum_id=${empresa.Id}: Empresa.Desativada em formato inesperado (tipo recebido: ${typeReceived}) — assumindo NÃO desativada (fallback seguro, ver ADR-009).`,
      );
    });
    // ADR-011: cidade da Empresa resolvida independentemente da cidade de
    // qualquer Funcionario vinculado — mesmo nó (`Cidade { Id, Descricao }`),
    // mas duas referências distintas.
    const empresaCidadeNode = extractCidadeNode(empresa.Cidade);
    const empresaCidadeRow = empresaCidadeNode
      ? cidadeByDescricao.get(empresaCidadeNode.descricao)
      : undefined;
    companyInputs.push({
      secullumDocumento: empresa.Documento,
      name: empresa.Nome,
      active,
      cityId: empresaCidadeRow?.id ?? null,
      ...pickEmpresaFields(empresa),
    });
  }
  // Leitura em lote do estado ATUAL (ANTES do upsert) — necessária para
  // decidir baseline/deactivated/reactivated (ADR-009). Mesmo padrão de
  // listUnits/listManagers: uma única leitura em massa, nunca um SELECT por
  // company dentro do laço.
  const existingCompanies = companyInputs.length ? await repo.listCompanies() : [];
  const existingCompanyByDocumento = new Map(
    existingCompanies.map((c) => [c.secullumDocumento, c]),
  );
  const companyRows = companyInputs.length ? await repo.upsertCompanies(companyInputs) : [];
  summary.companiesUpserted = companyRows.length;
  const companyByDocumento = new Map(companyRows.map((c) => [c.secullumDocumento, c]));

  // ADR-009: um único INSERT em lote de company_status_event, comparando o
  // `active` recém-derivado (companyInputs) com o `active` PERSISTIDO (lido
  // acima, antes do upsert) — nunca um insert por empresa.
  const companyStatusEvents: InsertEmpresaEventoStatusInput[] = [];
  for (const input of companyInputs) {
    const row = companyByDocumento.get(input.secullumDocumento);
    if (!row) continue; // defensivo: toda company enviada no lote acima está no mapa de retorno.
    const existing = existingCompanyByDocumento.get(input.secullumDocumento) ?? null;
    const event = buildCompanyStatusEvent(existing ? existing.active : null, input.active);
    if (event) companyStatusEvents.push({ companyId: row.id, ...event });
  }
  if (companyStatusEvents.length) await repo.insertCompanyStatusEvents(companyStatusEvents);
  summary.companyStatusEventsInserted = companyStatusEvents.length;

  // 2) Horarios -> work_schedule (lote) + work_schedule_day (um único lote
  // com TODAS as linhas de TODOS os horários, em vez de um upsert por dia).
  const horarios = await secullum.get<RawHorario[]>("Horarios");
  const scheduleInputs: UpsertHorarioInput[] = horarios.map((horario) => ({
    secullumHorarioId: horario.Id,
    secullumHorarioNumero: horario.Numero ?? null,
    description: horario.Descricao ?? null,
    active: deriveScheduleActive(horario.Desativar),
  }));
  const scheduleRows = scheduleInputs.length ? await repo.upsertWorkSchedules(scheduleInputs) : [];
  summary.schedulesUpserted = scheduleRows.length;
  const scheduleBySecullumId = new Map(scheduleRows.map((s) => [s.secullumHorarioId, s]));

  const scheduleDayInputs: UpsertHorarioDiaInput[] = [];
  for (const horario of horarios) {
    if (horario.ToleranciaEspecifica?.UsaToleranciaEspecifica) {
      warn(
        "schedule_uses_specific_tolerance",
        `Horario secullum_id=${horario.Id} usa ToleranciaEspecifica; motor de detecção (Sprint 2) aplicará a tolerância padrão do dia, sem silenciar (ver docs/03-integracao-secullum.md).`,
      );
    }

    const scheduleRow = scheduleBySecullumId.get(horario.Id);
    if (!scheduleRow) continue; // defensivo: todo horario enviado no lote acima está no mapa de retorno.

    for (const dia of horario.Dias ?? []) {
      const parsed = parseHorarioDia(scheduleRow.id, dia, (fieldName, rawValue) => {
        // Não loga o valor bruto (pode ser texto de status, ver ADR-007) —
        // só campo/tipo, suficiente para diagnóstico sem risco de log de PII.
        warn(
          "schedule_day_invalid_time_value",
          `Horario secullum_id=${horario.Id} Dia secullum_horario_dia_id=${dia.Id}: ${fieldName} não é um horário "HH:mm" válido (tipo recebido: ${typeof rawValue}) — gravado como null.`,
        );
      });
      scheduleDayInputs.push(parsed);
    }
  }
  if (scheduleDayInputs.length) await repo.upsertWorkScheduleDays(scheduleDayInputs);
  summary.scheduleDaysUpserted = scheduleDayInputs.length;

  // 2.x) Árvore completa de "Horario" (ADR-011 Fase 3, migration
  // 20260813162000): "HorariosOpcoes"/"HorarioExtras"/"HorarioDescanso"(+Faixas)/
  // "HorarioFaixasExtras"(+Faixas)/"HorarioToleranciaEspecifica"(+Tolerancias).
  // ⛔ CAPTURAR NAO E USAR — nada aqui alimenta o motor de detecção (ver
  // cabeçalho da migration). Nenhuma chamada de rede nova: todos os nós já
  // vêm no MESMO payload de `/Horarios` buscado acima.
  //
  // Regra de presença (decisão de menor porte do desenvolvedor — não fixada
  // literalmente pelo ADR): um nó AUSENTE (`undefined`) num Horario
  // específico não gera upsert/convergência para ELE, preservando o que já
  // estava sincronizado (mesmo espírito de "funcionário sem Empresa aninhada
  // não é tocado"). Um nó PRESENTE (mesmo `[]`/`false`) é a verdade deste
  // ciclo para aquele Horario e dispara a substituição integral
  // correspondente — sempre em lote, nunca por horario dentro de um laço.
  const warnedScheduleTreeFields = new Set<string>();
  const warnUnexpectedScheduleFieldFormat = (fieldName: string, typeReceived: string) => {
    if (warnedScheduleTreeFields.has(fieldName)) return;
    warnedScheduleTreeFields.add(fieldName);
    warn(
      "schedule_tree_boolean_field_unexpected_format",
      `Horario.${fieldName}: formato inesperado (tipo recebido: ${typeReceived}) — gravado como null (ADR-011 Fase 3).`,
    );
  };

  const scheduleOptionInputs: UpsertHorariosOpcoesInput[] = [];
  const scheduleExtrasInputs: UpsertHorarioExtrasInput[] = [];
  const scheduleRestInputs: UpsertHorarioDescansoInput[] = [];
  const pendingRestFaixasByHorarioUuid = new Map<string, RawHorarioDescansoFaixaItem[]>();
  const pendingFaixasExtrasGroups: Array<{
    horarioId: string;
    group: Omit<InsertHorarioFaixasExtrasInput, "horarioId">;
    faixas: RawHorarioFaixasExtrasItem[];
  }> = [];
  const touchedFaixasExtrasHorarioIds = new Set<string>();
  const scheduleToleranceInputs: UpsertHorarioToleranciaEspecificaInput[] = [];
  const pendingToleranceItemsByHorarioUuid = new Map<
    string,
    { secullumHorarioId: number; items: RawHorarioToleranciaEspecificaItem[] }
  >();

  for (const horario of horarios) {
    const scheduleRow = scheduleBySecullumId.get(horario.Id);
    if (!scheduleRow) continue; // defensivo — todo horario enviado no lote de upsertWorkSchedules está no mapa de retorno.

    if (horario.Opcoes) {
      scheduleOptionInputs.push({
        horarioId: scheduleRow.id,
        ...parseHorarioOpcoes(horario.Opcoes, warnUnexpectedScheduleFieldFormat),
      });
    }
    if (horario.Extras) {
      scheduleExtrasInputs.push({
        horarioId: scheduleRow.id,
        ...parseHorarioExtras(horario.Extras, warnUnexpectedScheduleFieldFormat),
      });
    }
    if (horario.Descanso) {
      scheduleRestInputs.push({
        horarioId: scheduleRow.id,
        ...parseHorarioDescanso(horario.Descanso, warnUnexpectedScheduleFieldFormat),
      });
      pendingRestFaixasByHorarioUuid.set(scheduleRow.id, horario.Descanso.Faixas ?? []);
    }
    if (Array.isArray(horario.FaixasExtras)) {
      // Presença do array (mesmo vazio) = verdade deste ciclo para este
      // horario -> entra no escopo da convergência DELETE+INSERT abaixo.
      touchedFaixasExtrasHorarioIds.add(scheduleRow.id);
      for (const rawGroup of horario.FaixasExtras) {
        pendingFaixasExtrasGroups.push({
          horarioId: scheduleRow.id,
          group: parseHorarioFaixasExtrasGroup(rawGroup),
          faixas: rawGroup.Faixas ?? [],
        });
      }
    }
    if (horario.ToleranciaEspecifica) {
      scheduleToleranceInputs.push({
        horarioId: scheduleRow.id,
        usaToleranciaEspecifica: asBoolean(
          horario.ToleranciaEspecifica.UsaToleranciaEspecifica,
          (typeReceived) =>
            warnUnexpectedScheduleFieldFormat(
              "ToleranciaEspecifica.UsaToleranciaEspecifica",
              typeReceived,
            ),
        ) ?? false,
      });
      pendingToleranceItemsByHorarioUuid.set(scheduleRow.id, {
        secullumHorarioId: horario.Id,
        items: horario.ToleranciaEspecifica.Tolerancias ?? [],
      });
    }
  }

  // "HorariosOpcoes" / "HorarioExtras" — 1:1, upsert em lote, sem delete (o
  // upsert por horario_id já substitui o conteúdo da única linha).
  if (scheduleOptionInputs.length) {
    await repo.upsertScheduleOptions(scheduleOptionInputs);
    summary.scheduleOptionsUpserted = scheduleOptionInputs.length;
  }
  if (scheduleExtrasInputs.length) {
    await repo.upsertScheduleExtras(scheduleExtrasInputs);
    summary.scheduleExtrasUpserted = scheduleExtrasInputs.length;
  }

  // "HorarioDescanso" (1:1, upsert) + "HorarioDescansoFaixaItem" (1:N, sem
  // chave única de negócio -> substituição integral: DELETE por
  // horario_descanso_id + INSERT do conjunto novo).
  if (scheduleRestInputs.length) {
    const restRows = await repo.upsertScheduleRests(scheduleRestInputs);
    summary.scheduleRestsUpserted = restRows.length;
    const restIdByHorarioUuid = new Map(restRows.map((r) => [r.horarioId, r.id]));
    await repo.deleteScheduleRestRangesByParentIds(restRows.map((r) => r.id));
    const restRangeInputs: InsertHorarioDescansoFaixaItemInput[] = [];
    for (const [horarioUuid, faixas] of pendingRestFaixasByHorarioUuid) {
      const descansoId = restIdByHorarioUuid.get(horarioUuid);
      if (!descansoId) continue; // defensivo — todo horario enviado no lote acima está no mapa de retorno.
      for (const rawFaixa of faixas) {
        restRangeInputs.push({
          horarioDescansoId: descansoId,
          ...parseHorarioDescansoFaixaItem(rawFaixa),
        });
      }
    }
    if (restRangeInputs.length) {
      await repo.insertScheduleRestRanges(restRangeInputs);
      summary.scheduleRestRangesInserted = restRangeInputs.length;
    }
  }

  // "HorarioFaixasExtras" (1:N por horario) + "HorarioFaixasExtrasItem" (1:N
  // dela) — NENHUMA das duas tem chave única de negócio -> substituição
  // integral: DELETE por horario_id (cascata para os itens) + INSERT do
  // conjunto novo.
  if (touchedFaixasExtrasHorarioIds.size) {
    await repo.deleteScheduleExtraRangeGroupsByHorarioIds([...touchedFaixasExtrasHorarioIds]);
    if (pendingFaixasExtrasGroups.length) {
      const groupRows = await repo.insertScheduleExtraRangeGroups(
        pendingFaixasExtrasGroups.map((pending) => ({
          horarioId: pending.horarioId,
          ...pending.group,
        })),
      );
      summary.scheduleExtraRangeGroupsInserted = groupRows.length;

      // Casamento pai -> linha recém-inserida por CHAVE, nunca por posição
      // (decisão de menor porte, ver relatório do desenvolvedor): como
      // "HorarioFaixasExtras" não tem constraint única, a chave usada AQUI é
      // (horario_id, "DiaSemana") só para resolver esta correlação EM
      // MEMÓRIA — nunca persistida como unicidade no banco. Fila FIFO por
      // chave cobre com segurança o caso (não confirmado, mas não
      // descartável) de duas entradas com o mesmo "DiaSemana" para o mesmo
      // horario dentro do mesmo ciclo.
      const rowIdsByKey = new Map<string, string[]>();
      for (const row of groupRows) {
        const key = `${row.horarioId}:${row.diaSemana}`;
        const list = rowIdsByKey.get(key) ?? [];
        list.push(row.id);
        rowIdsByKey.set(key, list);
      }
      const groupItemInputs: InsertHorarioFaixasExtrasItemInput[] = [];
      for (const pending of pendingFaixasExtrasGroups) {
        const key = `${pending.horarioId}:${pending.group.diaSemana}`;
        const rowId = rowIdsByKey.get(key)?.shift();
        if (!rowId) continue; // defensivo — todo grupo enviado no lote acima está no mapa de retorno.
        for (const rawItem of pending.faixas) {
          groupItemInputs.push({
            horarioFaixasExtrasId: rowId,
            ...parseHorarioFaixasExtrasItem(rawItem),
          });
        }
      }
      if (groupItemInputs.length) {
        await repo.insertScheduleExtraRangeGroupItems(groupItemInputs);
        summary.scheduleExtraRangeItemsInserted = groupItemInputs.length;
      }
    }
  }

  // "HorarioToleranciaEspecifica" (1:1, upsert — SEMPRE gravada quando o nó
  // está presente, mesmo `UsaToleranciaEspecifica=false`/sem itens: é a
  // única fonte da flag desde que a coluna equivalente saiu de "Horario") +
  // "HorarioToleranciaEspecificaItem" (1:N, sem chave única de negócio ->
  // substituição integral).
  if (scheduleToleranceInputs.length) {
    const toleranceRows = await repo.upsertScheduleSpecificTolerances(scheduleToleranceInputs);
    summary.scheduleSpecificTolerancesUpserted = toleranceRows.length;
    const toleranceIdByHorarioUuid = new Map(toleranceRows.map((r) => [r.horarioId, r.id]));
    await repo.deleteScheduleSpecificToleranceItemsByParentIds(toleranceRows.map((r) => r.id));
    const toleranceItemInputs: InsertHorarioToleranciaEspecificaItemInput[] = [];
    for (const [horarioUuid, pending] of pendingToleranceItemsByHorarioUuid) {
      const parentId = toleranceIdByHorarioUuid.get(horarioUuid);
      if (!parentId) continue; // defensivo.
      for (const rawItem of pending.items) {
        toleranceItemInputs.push({
          horarioToleranciaEspecificaId: parentId,
          ...parseHorarioToleranciaEspecificaItem(
            rawItem,
            (fieldName, rawValue) =>
              warn(
                "schedule_tolerance_item_invalid_time_value",
                `Horario secullum_id=${pending.secullumHorarioId} ToleranciaEspecifica.Tolerancias[]: ${fieldName} não é um horário "HH:mm" válido (tipo recebido: ${typeof rawValue}) — gravado como null.`,
              ),
          ),
        });
      }
    }
    if (toleranceItemInputs.length) {
      await repo.insertScheduleSpecificToleranceItems(toleranceItemInputs);
      summary.scheduleSpecificToleranceItemsInserted = toleranceItemInputs.length;
    }
  }

  // 3) unit, manager (nome + e-mail), employee — a partir dos mesmos
  // `funcionarios` já buscados/reaproveitados na fase 1 acima (nenhuma nova
  // chamada de rede a /Funcionarios).
  const nameIndex = buildFuncionarioNameIndex(funcionarios);

  // 3.a) Unidades: UMA leitura em massa da tabela (pequena — uma linha por
  // Departamento) em vez de um SELECT por funcionário, seguida de UM upsert
  // em lote só com as unidades novas encontradas neste ciclo. A ordem de
  // varredura de `funcionarios` é preservada para manter o mesmo
  // comportamento de "primeiro funcionário do Departamento decide a company
  // da unit nova" e "aviso de divergência uma única vez por unit" que a
  // versão linha-a-linha tinha.
  const existingUnits = await repo.listUnits();
  const unitBySecullumRef = new Map(existingUnits.map((u) => [u.secullumRef, u]));
  const newUnitInputs: UpsertDepartamentoInput[] = [];
  const seenDepartamentoIds = new Set<number>();

  for (const raw of funcionarios) {
    // Só os campos de vínculo (empresa/unidade) são necessários aqui — sem
    // custo de normalizar o resto do cadastro (nem gerar avisos duplicados de
    // ConfigEspecifica*, já emitidos uma vez na fase 3.c abaixo).
    const parsed = parseFuncionario(raw);
    const empresaDocumento = raw.Empresa?.Documento;
    const company = empresaDocumento ? companyByDocumento.get(empresaDocumento) : undefined;
    if (!company) continue; // avisado/contabilizado na fase de employee (3.c) abaixo.
    if (seenDepartamentoIds.has(parsed.departamentoId)) continue;
    seenDepartamentoIds.add(parsed.departamentoId);

    const existing = unitBySecullumRef.get(parsed.departamentoId);
    if (existing) {
      if (existing.companyId !== company.id) {
        warn(
          "unit_company_mismatch",
          `Unit secullum_ref=${parsed.departamentoId}: já vinculada a outra company — mantendo vínculo existente (divergência de cadastro no Secullum).`,
        );
      }
    } else {
      newUnitInputs.push({
        secullumRef: parsed.departamentoId,
        name: raw.Departamento?.Descricao ?? `Departamento ${parsed.departamentoId}`,
        companyId: company.id,
        active: true,
      });
    }
  }
  const createdUnits = newUnitInputs.length ? await repo.upsertUnits(newUnitInputs) : [];
  summary.unitsUpserted = createdUnits.length;
  for (const u of createdUnits) unitBySecullumRef.set(u.secullumRef, u);

  // 3.b) Gestores: mesma estratégia — UMA leitura em massa + UM upsert em
  // lote, com o e-mail final (protegido/matched/mantido) sempre resolvido
  // EXPLICITAMENTE antes do upsert (ver nota em UpsertEstruturaInput.email
  // sobre por que "omitir a chave" não é seguro num upsert em lote).
  const existingManagers = await repo.listManagers();
  const managerByEstruturaId = new Map(existingManagers.map((m) => [m.secullumEstruturaId, m]));
  const newManagerInputs: UpsertEstruturaInput[] = [];
  const seenEstruturaIds = new Set<number>();
  const estruturaMissingWarned = new Set<number>();

  for (const raw of funcionarios) {
    const parsed = parseFuncionario(raw);
    if (parsed.estruturaId === null) continue;
    if (seenEstruturaIds.has(parsed.estruturaId)) continue;

    if (!raw.Estrutura) {
      // EstruturaId presente mas objeto aninhado ausente: não há como
      // resolver o gestor sem Descricao. Não é erro fatal — a unidade fica
      // sem gestor resolvido nesta execução.
      if (!estruturaMissingWarned.has(parsed.estruturaId)) {
        estruturaMissingWarned.add(parsed.estruturaId);
        warn(
          "manager_estrutura_object_missing",
          `Estrutura secullum_id=${parsed.estruturaId}: EstruturaId presente mas objeto Estrutura aninhado ausente — gestor não resolvido para esta estrutura nesta execução.`,
        );
      }
      continue; // não marca seenEstruturaIds: outro funcionário da mesma estrutura pode trazer o objeto.
    }

    seenEstruturaIds.add(parsed.estruturaId);
    const estrutura = raw.Estrutura;
    const unit = unitBySecullumRef.get(parsed.departamentoId);
    if (!unit) continue; // defensivo — funcionário sem company/unit resolvida não chega a ter gestor sincronizado.

    if (estrutura.EstruturaPaiId !== 0) {
      // Informativo — não é erro (docs/03: "não se sobe a árvore", mas o
      // caso é registrado para diagnóstico).
      logger.info(
        `Estrutura secullum_id=${estrutura.Id}: EstruturaPaiId=${estrutura.EstruturaPaiId} (!=0) — gestor continua sendo a estrutura diretamente vinculada ao funcionário.`,
      );
    }

    const existingManager = managerByEstruturaId.get(estrutura.Id);
    const emailMatch = resolveManagerEmailMatch(nameIndex, estrutura.Descricao);
    // Regra de proteção (docs/04-modelo-dados.md): nunca sobrescrever
    // email_source = 'manual'.
    const protectManualEmail = existingManager?.emailSource === "manual";

    let email: string | null;
    let emailSource: "secullum" | "manual";
    if (protectManualEmail) {
      email = existingManager!.email;
      emailSource = "manual";
    } else if (emailMatch.outcome === "unique") {
      email = emailMatch.email;
      emailSource = "secullum";
    } else {
      if (emailMatch.outcome === "zero") {
        warn(
          "manager_email_zero_matches",
          `Estrutura secullum_id=${estrutura.Id}: nenhum Funcionario com Nome correspondente encontrado na lista sincronizada — e-mail não atribuído (0 candidatos).`,
        );
      } else {
        warn(
          "manager_email_multiple_matches",
          `Estrutura secullum_id=${estrutura.Id}: ${emailMatch.count} Funcionarios com Nome correspondente — e-mail não atribuído (match ambíguo).`,
        );
      }
      // Sem match seguro: mantém o que já existia (ou nulo/manual para um gestor novo).
      email = existingManager?.email ?? null;
      emailSource = existingManager?.emailSource ?? "manual";
    }

    newManagerInputs.push({
      secullumEstruturaId: estrutura.Id,
      secullumEstruturaPaiId: estrutura.EstruturaPaiId ?? null,
      name: estrutura.Descricao,
      email,
      emailSource,
    });
  }
  const upsertedManagers = newManagerInputs.length
    ? await repo.upsertManagers(newManagerInputs)
    : [];
  summary.managersUpserted = upsertedManagers.length;
  for (const m of upsertedManagers) managerByEstruturaId.set(m.secullumEstruturaId, m);

  // 3.c) Funcionarios -> employee: nenhuma chamada de rede dentro deste
  // laço — company/unit/schedule já estão resolvidos em memória; um único
  // upsert em lote ao final.
  //
  // ADR-009: leitura em lote do estado ATUAL de employee (admission_date /
  // termination_date / active PERSISTIDOS) antes do upsert — mesmo padrão de
  // listUnits/listManagers/listCompanies acima, nunca um SELECT por
  // funcionário dentro do laço.
  const existingEmployees = funcionarios.length ? await repo.listEmployees() : [];
  const existingEmployeeBySecullumId = new Map(
    existingEmployees.map((e) => [e.secullumFuncionarioId, e]),
  );

  const employeeInputs: UpsertFuncionarioInput[] = [];
  const warnedMissingAdmissionDate = new Set<number>();
  const warnedUnparseableAdmissao = new Set<number>();
  // ADR-011: aviso de formato inesperado do bloco ConfigEspecifica*/Bloquear*/
  // Permite*/Desabilitar* (e demais booleanos [VALIDAR — Postman]) — UMA vez
  // por CAMPO nesta execução (não por funcionário), conforme exigido pela
  // migration 20260813161000.
  const warnedUnexpectedBooleanFields = new Set<string>();
  const warnUnexpectedFieldFormat = (fieldName: string, typeReceived: string) => {
    if (warnedUnexpectedBooleanFields.has(fieldName)) return;
    warnedUnexpectedBooleanFields.add(fieldName);
    warn(
      "employee_boolean_field_unexpected_format",
      `Funcionario.${fieldName}: formato inesperado (tipo recebido: ${typeReceived}) — gravado como null (tipo ainda [VALIDAR — Postman], ver ADR-011).`,
    );
  };
  // ADR-011 — `ListaCentroDeCustos` por funcionário (chave secullum_funcionario_id),
  // usado na fase 3.d abaixo, DEPOIS que o employee tiver um `id` (uuid) resolvido.
  const centroCustoDescricoesBySecullumFuncionarioId = new Map<number, string[]>();

  for (const raw of funcionarios) {
    const parsed = parseFuncionario(raw, warnUnexpectedFieldFormat);

    // ADR-009: `Admissao` ausente ⇒ "sem restrição de início" (não bloqueia o
    // job), mas é logado — é dado de vínculo esperado para a maioria dos
    // funcionários. Distinto do caso "veio, mas em formato não reconhecido".
    if (parsed.admissionDate === null) {
      if (raw.Admissao !== null && raw.Admissao !== undefined) {
        if (!warnedUnparseableAdmissao.has(parsed.id)) {
          warnedUnparseableAdmissao.add(parsed.id);
          warn(
            "employee_admissao_unparseable",
            `Funcionario secullum_funcionario_id=${parsed.id}: Admissao em formato inesperado (não é uma data "yyyy-MM-dd..." reconhecível) — tratada como ausente.`,
          );
        }
      } else if (!warnedMissingAdmissionDate.has(parsed.id)) {
        warnedMissingAdmissionDate.add(parsed.id);
        warn(
          "employee_missing_admission_date",
          `Funcionario secullum_funcionario_id=${parsed.id}: sem Admissao — tratado como "sem restrição de início" (ver docs/04-modelo-dados.md).`,
        );
      }
    }

    const empresaDocumento = raw.Empresa?.Documento;
    const company = empresaDocumento ? companyByDocumento.get(empresaDocumento) : undefined;
    if (!company) {
      warn(
        "employee_company_not_found",
        `Funcionario secullum_funcionario_id=${parsed.id}: empresa não resolvida (objeto Empresa aninhado ausente ou sem Documento) — funcionário não sincronizado nesta execução.`,
      );
      summary.employeesSkipped++;
      continue;
    }

    const unit = unitBySecullumRef.get(parsed.departamentoId);
    if (!unit) {
      // Defensivo: toda unit referenciada por um funcionário com company
      // resolvida já foi criada/resolvida na fase 3.a acima.
      warn(
        "employee_unit_not_resolved",
        `Funcionario secullum_funcionario_id=${parsed.id}: unit secullum_ref=${parsed.departamentoId} não resolvida — funcionário não sincronizado nesta execução.`,
      );
      summary.employeesSkipped++;
      continue;
    }

    // Critério de aceite 2: divergência employee.company_id x unit.company_id
    // não falha o job, só gera aviso.
    if (company.id !== unit.companyId) {
      warn(
        "employee_unit_company_divergence",
        `Funcionario secullum_funcionario_id=${parsed.id}: company resolvida (${company.id}) difere de unit.company_id (${unit.companyId}).`,
      );
    }

    let scheduleId: string | null = null;
    if (parsed.horarioId !== null) {
      const schedule = scheduleBySecullumId.get(parsed.horarioId);
      if (schedule) {
        scheduleId = schedule.id;
      } else {
        warn(
          "employee_schedule_not_found",
          `Funcionario secullum_funcionario_id=${parsed.id}: HorarioId=${parsed.horarioId} não encontrado entre os Horarios sincronizados — funcionário fica sem horário.`,
        );
      }
    } else {
      warn(
        "employee_without_schedule",
        `Funcionario secullum_funcionario_id=${parsed.id}: sem HorarioId cadastrado no Secullum — funcionário fica sem horário.`,
      );
    }

    // ADR-009: active = derivado de admissionDate/terminationDate (era fixo em `true`).
    const active = deriveEmployeeActive(parsed.admissionDate, parsed.terminationDate, todayStr);

    // ADR-011: cidade/função resolvidas na fase 1.0 (upsert em lote,
    // deduplicado por Descricao) — aqui é só um lookup em memória.
    const cidadeRow = parsed.cidade ? cidadeByDescricao.get(parsed.cidade.descricao) : undefined;
    const funcaoRow = parsed.funcao ? funcaoByDescricao.get(parsed.funcao.descricao) : undefined;

    employeeInputs.push({
      secullumFuncionarioId: parsed.id,
      unitId: unit.id,
      companyId: company.id,
      name: parsed.name,
      secullumCpf: parsed.cpf,
      secullumPis: parsed.pis,
      scheduleId,
      admissionDate: parsed.admissionDate,
      terminationDate: parsed.terminationDate,
      active,

      secullumEmpresaId: parsed.empresaId,
      secullumDepartamentoId: parsed.departamentoId,
      secullumHorarioId: parsed.horarioId,
      secullumEstruturaId: parsed.estruturaId,

      cityId: cidadeRow?.id ?? null,
      secullumCidadeId: parsed.cidade?.secullumCidadeId ?? null,
      functionId: funcaoRow?.id ?? null,
      secullumFuncaoId: parsed.funcao?.secullumFuncaoId ?? null,

      numeroFolha: parsed.numeroFolha,
      numeroIdentificador: parsed.numeroIdentificador,
      numeroProvisorio: parsed.numeroProvisorio,
      carteira: parsed.carteira,
      codigoHolerite: parsed.codigoHolerite,
      observacao: parsed.observacao,

      endereco: parsed.endereco,
      bairro: parsed.bairro,
      uf: parsed.uf,
      cep: parsed.cep,
      telefone: parsed.telefone,
      celular: parsed.celular,
      email: parsed.email,

      rg: parsed.rg,
      expedicaoRg: parsed.expedicaoRg,
      ssp: parsed.ssp,
      mae: parsed.mae,
      pai: parsed.pai,
      nascimento: parsed.nascimento,
      masculino: parsed.masculino,
      nacionalidade: parsed.nacionalidade,
      naturalidade: parsed.naturalidade,

      naoVerificarDigital: parsed.naoVerificarDigital,
      master: parsed.master,
      possuiFoto: parsed.possuiFoto,
      invisivel: parsed.invisivel,
      periodoEncerrado: parsed.periodoEncerrado,
      desconsiderarPerimetrosGlobais: parsed.desconsiderarPerimetrosGlobais,
      aceitouTermosLgpdApp: parsed.aceitouTermosLgpdApp,
      dataUltimoEnvio: parsed.dataUltimoEnvio,
      dataUltimoLogin: parsed.dataUltimoLogin,
      dataAlteracao: parsed.dataAlteracao,

      escolaridadeId: parsed.escolaridadeId,
      filtro1Id: parsed.filtro1Id,
      filtro2Id: parsed.filtro2Id,
      motivoDemissaoId: parsed.motivoDemissaoId,
      nivelPermissaoId: parsed.nivelPermissaoId,
      perfilId: parsed.perfilId,
      perfilFuncionarioId: parsed.perfilFuncionarioId,
      bancoHorasId: parsed.bancoHorasId,
      horarioAlternativo2Id: parsed.horarioAlternativo2Id,
      horarioAlternativo3Id: parsed.horarioAlternativo3Id,
      horarioAlternativo4Id: parsed.horarioAlternativo4Id,

      configEspecificaInclusaoManualPonto: parsed.configEspecificaInclusaoManualPonto,
      configEspecificaInclusaoManualPontoFusoHorarioId:
        parsed.configEspecificaInclusaoManualPontoFusoHorarioId,
      configEspecificaDesativarVerificacaoLocalFicticio:
        parsed.configEspecificaDesativarVerificacaoLocalFicticio,
      configEspecificaInclusaoPontoSemLocalizacao:
        parsed.configEspecificaInclusaoPontoSemLocalizacao,
      configEspecificaInclusaoPontoOffline: parsed.configEspecificaInclusaoPontoOffline,
      configEspecificaCapturaDeFotoNoMomentoDaInclusao:
        parsed.configEspecificaCapturaDeFotoNoMomentoDaInclusao,
      bloquearRegistroPontoTeclado: parsed.bloquearRegistroPontoTeclado,
      permiteInclusaoPontoManual: parsed.permiteInclusaoPontoManual,
      permiteInclusaoDispositivosAutorizados: parsed.permiteInclusaoDispositivosAutorizados,
      desabilitarAssinaturaEletronica: parsed.desabilitarAssinaturaEletronica,
    });

    if (parsed.centroCustoDescricoes.length) {
      centroCustoDescricoesBySecullumFuncionarioId.set(parsed.id, parsed.centroCustoDescricoes);
    }
  }
  const employeeRows = employeeInputs.length ? await repo.upsertEmployees(employeeInputs) : [];
  summary.employeesUpserted = employeeInputs.length;

  // -------------------------------------------------------------------------
  // `secullum.departamento_gestor` — vigência de gestor por unidade.
  //
  // Roda DEPOIS do upsert de funcionários porque a observação é sobre eles: é o
  // `EstruturaId` de cada ativo que diz qual "Estrutura" responde pela unidade.
  // A regra está em `decideDepartmentManagerTransitions`, e a premissa dela
  // está declarada no comentário daquela função — o ADR-013 não está aqui.
  // -------------------------------------------------------------------------
  const observadasPorUnidade = new Map<string, Map<number, number>>();
  const departamentoSecullumPorUnidade = new Map<string, number>();
  for (const input of employeeInputs) {
    if (input.secullumDepartamentoId !== null) {
      departamentoSecullumPorUnidade.set(input.unitId, input.secullumDepartamentoId);
    }
    // Só ativos: um desligado não diz mais nada sobre quem responde pela
    // unidade hoje, e contá-lo faria uma unidade inteira de desligados manter
    // um gestor vigente para sempre.
    if (!input.active || input.secullumEstruturaId === null) continue;
    const porEstrutura = observadasPorUnidade.get(input.unitId) ?? new Map<number, number>();
    porEstrutura.set(
      input.secullumEstruturaId,
      (porEstrutura.get(input.secullumEstruturaId) ?? 0) + 1,
    );
    observadasPorUnidade.set(input.unitId, porEstrutura);
  }

  const observacoesGestor: ObservacaoGestor[] = [];
  for (const [unitId, porEstrutura] of observadasPorUnidade) {
    const estruturas: EstruturaObservada[] = [];
    for (const [secullumEstruturaId, ativos] of porEstrutura) {
      const manager = managerByEstruturaId.get(secullumEstruturaId);
      if (!manager) {
        // A "Estrutura" não chegou ao espelho nesta passada. Ignorá-la é mais
        // seguro que inventar: sem o id dela não há o que gravar, e tratá-la
        // como inexistente poderia tornar a unidade "inequívoca" por omissão.
        warn(
          "gestor_sem_estrutura",
          `Unidade ${unitId}: EstruturaId=${secullumEstruturaId} observado em ` +
            `funcionário ativo mas ausente do espelho — vigência não avaliada.`,
        );
        continue;
      }
      estruturas.push({ managerId: manager.id, secullumEstruturaId, ativos });
    }
    const secullumDepartamentoId = departamentoSecullumPorUnidade.get(unitId);
    if (secullumDepartamentoId === undefined) {
      // `"DepartamentoId"` é `not null` na tabela: sem ele não há linha a
      // gravar. Silenciar seria pior que avisar — some uma unidade inteira.
      warn(
        "gestor_sem_departamento_id",
        `Unidade ${unitId}: nenhum funcionário trouxe DepartamentoId — vigência não avaliada.`,
      );
      continue;
    }
    observacoesGestor.push({ unitId, secullumDepartamentoId, estruturas });
  }

  const vigenciasGestor = await repo.listCurrentDepartmentManagers();
  const transicoesGestor = decideDepartmentManagerTransitions(observacoesGestor, vigenciasGestor);
  for (const transicao of transicoesGestor) {
    await repo.transitionDepartmentManager(transicao);
  }
  summary.departmentManagerTransitions = transicoesGestor.length;

  // ADR-009: um único INSERT em lote de employee_status_event, comparando o
  // snapshot recém-derivado (employeeInputs) com o snapshot PERSISTIDO (lido
  // acima, antes do upsert) — nunca um insert por funcionário.
  const employeeRowBySecullumId = new Map(employeeRows.map((e) => [e.secullumFuncionarioId, e]));
  const employeeStatusEvents: InsertFuncionarioEventoStatusInput[] = [];
  for (const input of employeeInputs) {
    const row = employeeRowBySecullumId.get(input.secullumFuncionarioId);
    if (!row) continue; // defensivo: todo employee enviado no lote acima está no mapa de retorno.
    const existing = existingEmployeeBySecullumId.get(input.secullumFuncionarioId) ?? null;
    const previousSnapshot: EmployeeStatusSnapshot | null = existing
      ? {
        active: existing.active,
        admissionDate: existing.admissionDate,
        terminationDate: existing.terminationDate,
      }
      : null;
    const nextSnapshot: EmployeeStatusSnapshot = {
      active: input.active,
      admissionDate: input.admissionDate,
      terminationDate: input.terminationDate,
    };
    const event = buildEmployeeStatusEvent(previousSnapshot, nextSnapshot);
    if (event) employeeStatusEvents.push({ employeeId: row.id, ...event });
  }
  if (employeeStatusEvents.length) await repo.insertEmployeeStatusEvents(employeeStatusEvents);
  summary.employeeStatusEventsInserted = employeeStatusEvents.length;

  // 3.d) "FuncionarioCentroCusto" (ADR-011) — escrita por SUBSTITUIÇÃO
  // INTEGRAL por funcionário (delete do que sumiu + upsert do que veio),
  // mesmo padrão de employee_absence (ADR-010). UMA leitura em massa (nunca
  // um SELECT por funcionário) seguida de no máximo um upsert e um delete em
  // lote no total.
  const existingCostCenters = await repo.listCostCenters();
  const targetCostCenterInputs: UpsertCentroCustoInput[] = [];
  for (const [secullumFuncionarioId, descricoes] of centroCustoDescricoesBySecullumFuncionarioId) {
    const row = employeeRowBySecullumId.get(secullumFuncionarioId);
    if (!row) continue; // defensivo — mesmo padrão do restante do módulo.
    for (const descricao of descricoes) {
      targetCostCenterInputs.push({ employeeId: row.id, descricao });
    }
  }
  const targetCostCenterKeys = new Set(
    targetCostCenterInputs.map((i) => `${i.employeeId}:${i.descricao}`),
  );
  // Só convergimos (DELETE) para funcionários EFETIVAMENTE presentes nesta
  // execução — um funcionário fora do lote desta execução (ex.: skipped por
  // company/unit não resolvida) não deve ter seus centros de custo apagados
  // por "ausência" de um dado que nem foi buscado com sucesso.
  const employeeIdsInThisRun = new Set(
    [...employeeRowBySecullumId.values()].map((r) => r.id),
  );
  const costCentersToDelete = existingCostCenters.filter(
    (row) =>
      employeeIdsInThisRun.has(row.employeeId) &&
      !targetCostCenterKeys.has(`${row.employeeId}:${row.descricao}`),
  );
  if (costCentersToDelete.length) {
    await repo.deleteCostCentersByIds(costCentersToDelete.map((r) => r.id));
    summary.costCentersDeleted = costCentersToDelete.length;
  }
  if (targetCostCenterInputs.length) {
    const upsertedCostCenters = await repo.upsertCostCenters(targetCostCenterInputs);
    summary.costCentersUpserted = upsertedCostCenters.length;
  }

  // 4) FuncionariosAfastamentos -> employee_absence (+ employee.on_leave /
  // employee.current_absence_id) — ADR-010, 5º e último endpoint do escopo.
  // Roda DEPOIS de employee (fase 3.c): esta rota não tem FuncionarioId — a
  // correlação depende dos `employee` já sincronizados neste ciclo
  // (NumeroPis/Cpf).
  //
  // ⚠️ `dataInicio`/`dataFim` são OBRIGATÓRIOS nesta rota (correção de
  // 2026-08-13 — ver `computeAfastamentosDateRange` acima). A janela é FIXA
  // e larga o suficiente para cobrir, na prática, todo o histórico e futuro
  // relevante — por isso a lógica de convergência (DELETE) logo abaixo
  // continua tratando o escopo buscado como "a base inteira", sem precisar
  // de nenhuma restrição adicional por causa do filtro de data.
  const { dataInicio: afastamentosDataInicio, dataFim: afastamentosDataFim } =
    computeAfastamentosDateRange(todayStr);
  const rawAfastamentos = await secullum.get<RawFuncionarioAfastamento[]>(
    "FuncionariosAfastamentos",
    { dataInicio: afastamentosDataInicio, dataFim: afastamentosDataFim },
  );

  // Índices de correlação em memória — construídos SOMENTE sobre os
  // funcionários já resolvidos com sucesso neste ciclo (docs/03,
  // ADR-010 Decisão 4). `secullumPis`/`secullumCpf` aqui são os do CADASTRO
  // do funcionário (/Funcionarios) — nunca o NumeroPis/Cpf DESTE payload de
  // afastamentos, que não é persistido em nenhum lugar.
  const pisIndexEntries: Array<{ employeeId: string; identifier: string | null }> = [];
  const cpfIndexEntries: Array<{ employeeId: string; identifier: string | null }> = [];
  for (const input of employeeInputs) {
    const row = employeeRowBySecullumId.get(input.secullumFuncionarioId);
    if (!row) continue; // defensivo — mesmo padrão do restante do módulo.
    pisIndexEntries.push({ employeeId: row.id, identifier: input.secullumPis });
    cpfIndexEntries.push({ employeeId: row.id, identifier: input.secullumCpf });
  }
  const pisIndex = buildEmployeeIdentifierIndex(pisIndexEntries);
  const cpfIndex = buildEmployeeIdentifierIndex(cpfIndexEntries);

  // Leitura em lote do estado ATUAL de employee_absence (ANTES do
  // upsert/delete) — base da convergência (ADR-010, Decisão 7) e do
  // recálculo de on_leave abaixo, nunca um SELECT por afastamento.
  const existingAbsences = await repo.listEmployeeAbsences();

  const absenceInputs: UpsertFuncionarioAfastamentoInput[] = [];
  for (const raw of rawAfastamentos) {
    const parsed = parseFuncionarioAfastamentoAllowList(raw);

    const match = resolveAbsenceEmployeeMatch(pisIndex, cpfIndex, parsed.numeroPis, parsed.cpf);
    if (match.outcome === "zero") {
      warn(
        "absence_correlation_zero_candidates",
        `Afastamento secullum_afastamento_id=${parsed.secullumAfastamentoId}: nenhum employee correlacionado por PIS/CPF — registro descartado (0 candidatos).`,
      );
      continue;
    }
    if (match.outcome === "multiple") {
      warn(
        "absence_correlation_multiple_candidates",
        `Afastamento secullum_afastamento_id=${parsed.secullumAfastamentoId}: ${match.count} employees correlacionados por PIS/CPF — registro descartado (correlação ambígua).`,
      );
      continue;
    }

    const window = parseAbsenceWindow(parsed.inicio, parsed.fim);
    if (window.outcome === "unparseable") {
      warn(
        "absence_unparseable_dates",
        `Afastamento secullum_afastamento_id=${parsed.secullumAfastamentoId}: Inicio/Fim em formato inesperado — registro descartado.`,
      );
      continue;
    }
    if (window.outcome === "invalid_range") {
      warn(
        "absence_invalid_range",
        `Afastamento secullum_afastamento_id=${parsed.secullumAfastamentoId}: Fim (${window.endDate}) anterior a Inicio (${window.startDate}) — registro descartado, sem derrubar o job (ADR-010).`,
      );
      continue;
    }

    absenceInputs.push({
      employeeId: match.employeeId,
      secullumAfastamentoId: parsed.secullumAfastamentoId,
      startDate: window.startDate,
      endDate: window.endDate,
      justificationCode: parsed.justificationCode,
      secullumIncludedAt: parsed.secullumIncludedAt,
      matchedBy: match.matchedBy,
    });
  }

  // Inventário de JustificativaNome (código + contagem, SEM titular) —
  // ADR-010, pendência 3: nenhum código de férias confirmado ainda pelo Owner.
  if (absenceInputs.length) {
    const justificationCounts = new Map<string, number>();
    for (const input of absenceInputs) {
      const code = input.justificationCode ?? "(sem código)";
      justificationCounts.set(code, (justificationCounts.get(code) ?? 0) + 1);
    }
    const inventory = [...justificationCounts.entries()]
      .map(([code, count]) => `${code}=${count}`)
      .join(", ");
    logger.info(
      `Afastamentos: inventário de JustificativaNome desta execução (código=contagem, sem titular): ${inventory}.`,
    );
  }

  let upsertedAbsences: FuncionarioAfastamentoRow[] = [];
  // Estado FINAL (pós upsert+delete) de employee_absence, usado no recálculo
  // de on_leave logo abaixo. Semeado com o estado ANTERIOR (existingAbsences)
  // e só alterado quando a resposta desta execução não é vazia (trava
  // obrigatória abaixo, ADR-010 Decisão 7).
  const finalAbsenceByKey = new Map<
    string,
    { id: string; employeeId: string; startDate: string; endDate: string }
  >();
  for (const row of existingAbsences) {
    finalAbsenceByKey.set(absenceKey(row.employeeId, row.secullumAfastamentoId), row);
  }

  if (rawAfastamentos.length === 0) {
    // ⛔ Trava obrigatória (ADR-010, Decisão 7): resposta vazia NUNCA apaga
    // nada. Zero registros pode ser falha parcial/mudança de contrato — se
    // convergêssemos aqui, apagaríamos employee_absence inteira e
    // desligaríamos a supressão de desvios de TODA a base. upsert/delete são
    // pulados por completo; o recálculo de on_leave abaixo usa o estado
    // ANTERIOR, intacto.
    warn(
      "absence_empty_response_skip_convergence",
      "FuncionariosAfastamentos retornou 0 registros nesta execução — convergência (DELETE) abortada por segurança; employee_absence permanece intacta.",
    );
  } else {
    if (absenceInputs.length) {
      upsertedAbsences = await repo.upsertEmployeeAbsences(absenceInputs);
    }
    summary.absencesUpserted = upsertedAbsences.length;

    // Convergência: linha local que já existia e não veio nesta resposta
    // (chave `employee_id` + `secullum_afastamento_id`) é apagada — dentro do
    // escopo efetivamente buscado. Apesar de a rota exigir `dataInicio`/
    // `dataFim` (correção de 2026-08-13), a janela usada é FIXA e larga o
    // suficiente para cobrir todo o histórico e futuro relevante (ver
    // `computeAfastamentosDateRange`) — na prática, equivalente a "a base
    // inteira", como já era o caso quando a chamada era assumida sem filtro.
    //
    // ⚠️ Decisão de menor porte (não coberta literalmente pelo ADR — ver
    // relatório do desenvolvedor): um registro cujo `Id` apareceu na resposta
    // mas cuja correlação FALHOU nesta execução (0 ou 2+ candidatos) não tem
    // `employee_id` conhecido. A linha local eventualmente já persistida (de
    // uma correlação bem-sucedida em execução anterior, hoje ambígua por
    // exemplo por um novo homônimo ter entrado no cadastro) é PRESERVADA, não
    // apagada — não há como compará-la com segurança contra este registro. É
    // perda de convergência aceita, mesmo espírito da abstenção: melhor
    // manter um dado potencialmente obsoleto do que apagar por engano.
    const seenKeys = new Set(
      absenceInputs.map((i) => absenceKey(i.employeeId, i.secullumAfastamentoId)),
    );
    const rowsToDelete = existingAbsences.filter(
      (row) => !seenKeys.has(absenceKey(row.employeeId, row.secullumAfastamentoId)),
    );
    if (rowsToDelete.length) {
      await repo.deleteEmployeeAbsencesByIds(rowsToDelete.map((row) => row.id));
      summary.absencesDeleted = rowsToDelete.length;
      for (const row of rowsToDelete) {
        finalAbsenceByKey.delete(absenceKey(row.employeeId, row.secullumAfastamentoId));
      }
    }

    const upsertedRowByKey = new Map(
      upsertedAbsences.map((row) => [absenceKey(row.employeeId, row.secullumAfastamentoId), row]),
    );
    for (const input of absenceInputs) {
      const key = absenceKey(input.employeeId, input.secullumAfastamentoId);
      const upserted = upsertedRowByKey.get(key);
      if (!upserted) continue; // defensivo: todo item enviado no lote acima está no mapa de retorno.
      finalAbsenceByKey.set(key, {
        id: upserted.id,
        employeeId: input.employeeId,
        startDate: input.startDate,
        endDate: input.endDate,
      });
    }
  }

  // employee.on_leave / employee.current_absence_id — RECALCULADOS a cada
  // sincronização (ADR-010), "hoje" em America/Sao_Paulo (todayStr, mesma
  // variável usada por deriveEmployeeActive acima). Roda para todo
  // funcionário sincronizado neste ciclo, mesmo quando nada mudou em
  // employee_absence — é função do tempo, igual a `active` (vira sozinho
  // quando o período começa/termina, sem nenhuma mudança no Secullum).
  const absencesByEmployeeId = new Map<string, AbsenceWindowForLeaveCalc[]>();
  for (const row of finalAbsenceByKey.values()) {
    const list = absencesByEmployeeId.get(row.employeeId) ?? [];
    list.push({ id: row.id, startDate: row.startDate, endDate: row.endDate });
    absencesByEmployeeId.set(row.employeeId, list);
  }

  const leaveStatusInputs: UpsertFuncionarioLeaveStatusInput[] = [];
  for (const input of employeeInputs) {
    const row = employeeRowBySecullumId.get(input.secullumFuncionarioId);
    if (!row) continue; // defensivo.
    const absences = absencesByEmployeeId.get(row.id) ?? [];
    const status = computeEmployeeLeaveStatus(absences, todayStr);
    if (status.overlapping) {
      warn(
        "absence_overlap",
        `employee_id=${row.id}: mais de um período de afastamento cobre hoje — current_absence_id aponta o de maior end_date (ADR-010).`,
      );
    }
    leaveStatusInputs.push({
      ...input,
      onLeave: status.onLeave,
      currentAbsenceId: status.currentAbsenceId,
    });
  }
  if (leaveStatusInputs.length) {
    await repo.applyEmployeeLeaveStatus(leaveStatusInputs);
  }

  flushSuppressedWarnings();
  return summary;
}

// ---------------------------------------------------------------------------
// `secullum.departamento_gestor` — qual "Estrutura" responde por um
// "Departamento", COM VIGÊNCIA (ADR-013).
//
// ⚠️ O ADR-013 não está neste repositório. A regra abaixo foi DERIVADA das 25
// linhas de produção em 01/09/2026 e dos comentários da própria tabela, e a
// premissa está declarada porque ela pode estar errada:
//
//   • Eleição por MAIORIA é proibida — o comentário de `funcionarios_observados`
//     diz isso literalmente ("proibido eleição por maioria — ADR-013 §4/§4.1").
//     O campo é diagnóstico humano, não critério.
//   • Atribuição inicial só acontece quando o departamento é INEQUÍVOCO: os
//     colaboradores ativos apontam para uma única "Estrutura". Medido: dos dois
//     departamentos ambíguos de produção, o que nunca teve momento inequívoco
//     não tem linha nenhuma.
//   • Uma vez vigente, a atribuição GRUDA enquanto ainda for observada, mesmo
//     que outra "Estrutura" apareça no departamento. Medido: o outro ambíguo
//     mantém a "Estrutura" que tinha 3 observados quando a linha foi escrita, e
//     hoje tem 2, com uma segunda "Estrutura" ao lado.
//   • Não existe FECHAR SEM SUBSTITUTO: a RPC `departamento_gestor_transition`
//     exige `p_estrutura_id`, então toda transição abre uma linha. Confere com
//     produção, onde um departamento sem nenhum ativo hoje segue com a linha
//     aberta.
// ---------------------------------------------------------------------------

/** Uma "Estrutura" observada num departamento, com quantos ativos a apontam. */
export interface EstruturaObservada {
  managerId: string;
  secullumEstruturaId: number;
  ativos: number;
}

/** O que este ciclo observou para um departamento. */
export interface ObservacaoGestor {
  unitId: string;
  secullumDepartamentoId: number;
  estruturas: EstruturaObservada[];
}

/** A linha vigente hoje, se houver. */
export interface VigenciaGestor {
  /** `p_close_id` da RPC. */
  id: string;
  unitId: string;
  managerId: string;
}

/** Uma chamada de `secullum.departamento_gestor_transition`. */
export interface TransicaoGestor {
  closeId: string | null;
  unitId: string;
  managerId: string;
  secullumDepartamentoId: number;
  secullumEstruturaId: number;
  funcionariosObservados: number;
}

/**
 * Decide quais transições este ciclo deve gravar.
 *
 * Pura de propósito: a regra é a única parte deste trabalho que foi inferida em
 * vez de lida, então ela mora onde um teste pode contradizê-la sem banco.
 */
export function decideDepartmentManagerTransitions(
  observacoes: ObservacaoGestor[],
  vigentes: VigenciaGestor[],
): TransicaoGestor[] {
  const vigentePorUnidade = new Map(vigentes.map((v) => [v.unitId, v]));
  const transicoes: TransicaoGestor[] = [];

  for (const obs of observacoes) {
    if (obs.estruturas.length === 0) continue; // nada observado: nada a dizer
    const vigente = vigentePorUnidade.get(obs.unitId);

    // Gruda: a vigente continua sendo observada, então não houve substituição.
    if (vigente && obs.estruturas.some((e) => e.managerId === vigente.managerId)) continue;

    // Sem unanimidade não há candidato — e eleger por maioria é proibido.
    if (obs.estruturas.length > 1) continue;

    const escolhida = obs.estruturas[0];
    transicoes.push({
      closeId: vigente?.id ?? null,
      unitId: obs.unitId,
      managerId: escolhida.managerId,
      secullumDepartamentoId: obs.secullumDepartamentoId,
      secullumEstruturaId: escolhida.secullumEstruturaId,
      funcionariosObservados: escolhida.ativos,
    });
  }
  return transicoes;
}
