// Formato bruto do cadastro do Secullum — `GET /Funcionarios`, `/Horarios` e
// os afastamentos.
//
// ⚠️ ESTE ARQUIVO FOI RECONSTRUÍDO, NÃO RECUPERADO — 01/09/2026
// `cadastro-sync.ts` sempre o importou, e ele não existia nem aqui nem na
// nuvem, pelo mesmo motivo que o irmão `secullum-batida-types.ts` registra:
// `import type` é apagado na transpilação, então o módulo nunca chega ao
// runtime e não faz parte do que a plataforma guarda. O deploy funcionava; o
// `deno check` não passava em nada que dependesse deste arquivo, e por isso
// `deno.json` carrega `--no-check` nos testes.
//
// COMO ELE FOI RECONSTRUÍDO
// Pelo compilador, campo a campo, a partir de **cada acesso que o código faz**
// — não do que a documentação da origem promete, e não do que o espelho
// guardou. O levantamento é reproduzível: com as 15 interfaces vazias,
//
//     deno check _shared/cadastro-sync.ts
//
// lista cada propriedade que falta e em qual tipo ela falta. Foram 275.
//
// O espelho serviu de CONFERÊNCIA, não de fonte: cada tipo abaixo nomeia a
// tabela correspondente, e as contagens batem com folga esperada (o espelho
// tem colunas nossas — `id`, `tenant_id`, `criado_em` — que a origem não
// manda).
//
// A TIPAGEM É PERMISSIVA DE PROPÓSITO, e isso não é preguiça — é a mesma
// disciplina do irmão. Os leitores (`asNumber`, `asBoolean`, `asString`,
// `asTextPassthrough`, `parseSecullumDateOnly`, `parseHorarioDiaTimeField`)
// recebem `unknown` e validam em runtime. Declarar `Nome: string` aqui
// afirmaria sobre a origem uma garantia que o código não assume e que ninguém
// pode conferir: não existe sandbox do Secullum para este cliente, e todo
// ensaio roda contra produção real. Onde o tipo é forte abaixo, é porque o
// código atribui o valor direto — e aí a garantia é do nosso lado, não do
// deles.

/** Espelhado em `secullum."FuncionarioCentroCusto"`. 1 campos lidos pelo código. */
export interface RawCentroCusto {
  Descricao?: unknown;
}

/** Espelhado em `secullum."Cidade"`. 2 campos lidos pelo código. */
export interface RawCidade {
  Descricao?: unknown;
  Id?: unknown;
}

/** Espelhado em `secullum."Empresa"`. 25 campos lidos pelo código. */
export interface RawEmpresa {
  Bairro?: unknown;
  Cei?: unknown;
  Cep?: unknown;
  Cidade?: RawCidade | null;
  DiaFechamentoPonto?: unknown;
  EmitiuAtestadoTecnico?: unknown;
  Endereco?: unknown;
  Fax?: unknown;
  FechamentoPonto?: unknown;
  /** Usado como chave de `Set` de avisos. */
  Id: number;
  Inscricao?: unknown;
  Logotipo?: unknown;
  NfolhaEmpresa?: unknown;
  Pais?: unknown;
  PossuiLogo?: unknown;
  ResponsavelCargo?: unknown;
  ResponsavelEmail?: unknown;
  ResponsavelNome?: unknown;
  Telefone?: unknown;
  TipoDocumento?: unknown;
  Uf?: unknown;
  UsaFechamentoDoPontoEspecifico?: unknown;
  UtilizaRepA?: unknown;
  UtilizaRepC?: unknown;
  UtilizaRepP?: unknown;
  /** CNPJ/CPF — a CHAVE NATURAL da empresa. Empresa sem ele não sincroniza. */
  Documento?: string | null;
  /** Atribuído direto a `string`. */
  Nome: string;
  /** Lido por `deriveCompanyActive`, que recebe `unknown` e valida em runtime. */
  Desativada?: unknown;
}

/** Espelhado em `secullum."Funcao"`. 2 campos lidos pelo código. */
export interface RawFuncao {
  Descricao?: unknown;
  Id?: unknown;
}

/** Espelhado em `secullum."Funcionario"`. 72 campos lidos pelo código. */
export interface RawFuncionario {
  AceitouTermosLgpdApp?: unknown;
  Admissao?: unknown;
  Bairro?: unknown;
  BancoHorasId?: unknown;
  BloquearRegistroPontoTeclado?: unknown;
  Carteira?: unknown;
  Celular?: unknown;
  Cep?: unknown;
  /** Nó aninhado, lido por `extractCidadeNode`. */
  Cidade?: RawCidade | null;
  CodigoHolerite?: unknown;
  ConfigEspecificaCapturaDeFotoNoMomentoDaInclusao?: unknown;
  ConfigEspecificaDesativarVerificacaoLocalFicticio?: unknown;
  ConfigEspecificaInclusaoManualPonto?: unknown;
  ConfigEspecificaInclusaoManualPontoFusoHorarioId?: unknown;
  ConfigEspecificaInclusaoPontoOffline?: unknown;
  ConfigEspecificaInclusaoPontoSemLocalizacao?: unknown;
  Cpf?: string | null;
  DataAlteracao?: unknown;
  DataUltimoEnvio?: unknown;
  DataUltimoLogin?: unknown;
  Demissao?: unknown;
  Departamento?: RawDepartamentoNode | null;
  DepartamentoId: number;
  DesabilitarAssinaturaEletronica?: unknown;
  DesconsiderarPerimetrosGlobais?: unknown;
  Email?: string | null;
  /** Nó aninhado: é dele que sai `Documento`, a chave natural da empresa. */
  Empresa?: RawEmpresa | null;
  /** Regra 5: a empresa do colaborador sai daqui, nunca do departamento. */
  EmpresaId: number;
  Endereco?: unknown;
  EscolaridadeId?: unknown;
  /** O GESTOR, não a unidade — ver o comentário de `secullum."Estrutura"`. */
  Estrutura?: RawEstruturaNode | null;
  EstruturaId?: number | null;
  ExpedicaoRg?: unknown;
  Filtro1Id?: unknown;
  Filtro2Id?: unknown;
  /** Nó aninhado, lido por `extractFuncaoNode`. A rota `/Funcoes` não é chamada. */
  Funcao?: RawFuncao | null;
  Horario?: RawHorarioRef | null;
  HorarioAlternativo2Id?: unknown;
  HorarioAlternativo3Id?: unknown;
  HorarioAlternativo4Id?: unknown;
  HorarioId?: number | null;
  /** Chave natural do funcionário. Atribuída direto a `number`. */
  Id: number;
  Invisivel?: unknown;
  /** Lido por `extractCentroCustoDescricoes`. */
  ListaCentroDeCustos?: RawCentroCusto[] | null;
  Mae?: unknown;
  Masculino?: unknown;
  Master?: unknown;
  MotivoDemissaoId?: unknown;
  Nacionalidade?: unknown;
  NaoVerificarDigital?: unknown;
  Nascimento?: unknown;
  Naturalidade?: unknown;
  NivelPermissaoId?: unknown;
  /** Atribuído direto a `string` — é o nome que vira `"Nome"` no espelho. */
  Nome: string;
  NumeroCpf?: string | null;
  NumeroFolha?: unknown;
  NumeroIdentificador?: unknown;
  NumeroPis?: string | null;
  NumeroProvisorio?: unknown;
  Observacao?: unknown;
  Pai?: unknown;
  PerfilFuncionarioId?: unknown;
  PerfilId?: unknown;
  PeriodoEncerrado?: unknown;
  PermiteInclusaoDispositivosAutorizados?: unknown;
  PermiteInclusaoPontoManual?: unknown;
  Pis?: string | null;
  PossuiFoto?: unknown;
  Rg?: unknown;
  Ssp?: unknown;
  Telefone?: unknown;
  Uf?: unknown;
}

/** Espelhado em `secullum."FuncionarioAfastamento"`. 7 campos lidos pelo código. */
export interface RawFuncionarioAfastamento {
  Cpf?: string | null;
  DataInclusao?: unknown;
  Fim?: unknown;
  /** Atribuído direto a `number`. */
  Id: number;
  Inicio?: unknown;
  JustificativaNome?: string | null;
  NumeroPis?: string | null;
}

/** Espelhado em `secullum."Horario"`. 10 campos lidos pelo código. */
export interface RawHorario {
  Desativar?: unknown;
  Descanso?: RawHorarioDescanso | null;
  Descricao?: string | null;
  /** Percorrido com `for...of`. */
  Dias?: RawHorarioDia[] | null;
  Extras?: unknown;
  FaixasExtras?: unknown;
  /** Atribuído direto a `number`. */
  Id: number;
  Numero?: number | null;
  Opcoes?: unknown;
  ToleranciaEspecifica?: RawHorarioToleranciaEspecificaNode | null;
}

/** Espelhado em `secullum."HorarioDescanso"`. 9 campos lidos pelo código. */
export interface RawHorarioDescanso {
  DescontarFeriadosCasoFaltas?: unknown;
  FeriadoDomingoApenasUmDescanso?: unknown;
  HorarioId?: number | null;
  IncluirFeriado?: unknown;
  LimiteHorasFaltas?: unknown;
  NaoDescontarAntesAdmissao?: unknown;
  NaoDescontarDuranteAfastamento?: unknown;
  Tipo?: unknown;
  ValorDescanso?: unknown;
  /** Percorrido para gerar `HorarioDescansoFaixaItem`. */
  Faixas?: RawHorarioDescansoFaixaItem[] | null;
}

/** Espelhado em `secullum."HorarioDescansoFaixaItem"`. 3 campos lidos pelo código. */
export interface RawHorarioDescansoFaixaItem {
  Desconto?: unknown;
  Limite?: unknown;
  Ordem?: unknown;
}

/** Espelhado em `secullum."HorarioDia"`. 30 campos lidos pelo código. */
export interface RawHorarioDia {
  AlmocoLivre?: unknown;
  Alocar24Horas?: unknown;
  /** Carga do dia em minutos; `0` é o que define folga. */
  Carga?: number | null;
  Compensado?: unknown;
  /** Atribuído direto a `number`. */
  DiaSemana: number;
  Entrada1?: unknown;
  Entrada2?: unknown;
  Entrada3?: unknown;
  Entrada4?: unknown;
  Entrada5?: unknown;
  /** Atribuído direto a `number`. */
  Id: number;
  Neutro?: unknown;
  Saida1?: unknown;
  Saida2?: unknown;
  Saida3?: unknown;
  Saida4?: unknown;
  Saida5?: unknown;
  TipoDia?: number | null;
  TipoEntrada1?: number | null;
  TipoEntrada2?: number | null;
  TipoEntrada3?: number | null;
  TipoEntrada4?: number | null;
  TipoEntrada5?: number | null;
  TipoSaida1?: number | null;
  TipoSaida2?: number | null;
  TipoSaida3?: number | null;
  TipoSaida4?: number | null;
  TipoSaida5?: number | null;
  ToleranciaExtra?: number | null;
  ToleranciaFalta?: number | null;
}

/** Espelhado em `secullum."HorarioExtras"`. 31 campos lidos pelo código. */
export interface RawHorarioExtras {
  Acumulo?: unknown;
  AgruparExtras?: unknown;
  ApenasDividirJornadaFeriadoFolgaDiaSeguinte?: unknown;
  ControleHorasExtrasAutorizadas?: unknown;
  DescontarFaltasExtras?: unknown;
  DescontarFaltasExtrasNoturnas?: unknown;
  DescontarIgnorarDiaEspecial?: unknown;
  DescontarIgnorarDomingos?: unknown;
  DescontarIgnorarFeriados?: unknown;
  DescontarIgnorarFolgas?: unknown;
  DescontarIgnorarSabados?: unknown;
  DescontarIgnorarUteis?: unknown;
  DividirJornadaQuandoHouverFolga?: unknown;
  HabilitarMultiplicadorFaixaBancoHoras?: unknown;
  HorarioId?: number | null;
  Interjornada?: unknown;
  InterjornadaSeparada?: unknown;
  InterjornadaSeparadaBancoHoras?: unknown;
  MultiplicarExtrasPeloPercentual?: unknown;
  MultiplicarSomenteSaldoPositivo?: unknown;
  NaoDividirExtrasEmDomingos?: unknown;
  NaoDividirExtrasEmFeriados?: unknown;
  NaoDividirJornadaEmFeriados?: unknown;
  NaoDividirJornadaEmFolgas?: unknown;
  NaoReiniciarDivisoesExtrasDiurnasNoturnas?: unknown;
  QuantidadeExtrasAutorizadas?: unknown;
  SepararExtrasIntervalosDeExtrasNormais?: unknown;
  SepararExtrasNoturnasDeExtrasNormais?: unknown;
  SepararSomatoriaAposMeiaNoite?: unknown;
  SomenteGrupoExtras?: unknown;
  UsarInterjornada?: unknown;
}

/** Espelhado em `secullum."HorarioFaixasExtras"`. 4 campos lidos pelo código. */
export interface RawHorarioFaixasExtras {
  Controle?: unknown;
  DiaEspecial?: unknown;
  DiaSemana?: unknown;
  HorarioId?: number | null;
}

/** Espelhado em `secullum."HorarioFaixasExtrasItem"`. 3 campos lidos pelo código. */
export interface RawHorarioFaixasExtrasItem {
  Coluna?: unknown;
  Horas?: unknown;
  Ordem?: unknown;
}

/** Espelhado em `secullum."HorariosOpcoes"`. 54 campos lidos pelo código. */
export interface RawHorarioOpcoes {
  AlocarBatidas?: unknown;
  AlocarHorario24Horas?: unknown;
  CalcularBatidasIntermediarias?: unknown;
  CalcularFaltasSomenteParaDiaInteiro?: unknown;
  CalcularHorasInItinere?: unknown;
  CalcularHorasInItinereIninterruptas?: unknown;
  CalcularNoturnasIndependenteCompensado?: unknown;
  Carga?: unknown;
  ColunasRefeicao?: unknown;
  Compensacao?: unknown;
  CompensacaoCalcularHorasComoNormaisCompatibilidadePontoOff?: unknown;
  CompensacaoIgnorarDomingos?: unknown;
  CompensacaoIgnorarFeriados?: unknown;
  CompensacaoIgnorarFolgas?: unknown;
  CompensacaoIgnorarSabados?: unknown;
  CompensacaoMensalFechamento?: unknown;
  CompletarBatidasFaltantes?: unknown;
  ConsiderarFeriadosComoHoraExtra?: unknown;
  DefinirCargaAutomaticamente?: unknown;
  DesconsiderarNeutroQuandoHouverBatidasNoDia?: unknown;
  DescontarToleranciaDasHorasExtras?: unknown;
  DescontarToleranciaDasHorasFaltas?: unknown;
  ExibirColunaHorasRepousoFaltantesTrabalhoContinuo?: unknown;
  HorarioId?: number | null;
  HorasRepousoConfiguracaoPadrao?: unknown;
  HorasRepousoFaixas?: unknown;
  IgnorarLimiteMinimoCasoBatidaGerarExtrasSuperiorATolerancia?: unknown;
  IgnorarLimiteMinimoCasoBatidaGerarFaltasSuperiorATolerancia?: unknown;
  IncluirIntervaloNoAdicionalNoturno?: unknown;
  LimiteMinimoDeExtrasNoDiaMinutos?: unknown;
  LimiteMinimoDeFaltasNoDiaMinutos?: unknown;
  ListaHorasInItinere?: unknown;
  ListaHorasSobreAviso?: unknown;
  NaoCalcularHorasFaltaBatidasIntermediarias?: unknown;
  NaoCalcularNenhumaHoraNoturna?: unknown;
  NaoDescontarFaltasDeNormais?: unknown;
  PercentualCargaUsarTempoMaisMenosMinutos?: unknown;
  PeriodoEspecialAdicionalNoturnoFim?: unknown;
  PeriodoEspecialAdicionalNoturnoInicio?: unknown;
  PermitirFolgasAutomaticas?: unknown;
  PreencherFaltasQuandoDiaEstiverEmBranco?: unknown;
  QualquerMinutoAdiantadoComoExtra?: unknown;
  QualquerMinutoAtrasadoComoFalta?: unknown;
  QuantidadeFolgasAutomaticas?: unknown;
  SepararHorasNoturnasDeHorasNormais?: unknown;
  SinalizarEmVermelhoAlmocosCurtos?: unknown;
  SomarHorasInItinereNormais?: unknown;
  SubstituirBatidasAbaixoDasTolerancias?: unknown;
  TipoPreencherQuandoDiaEstiverEmBranco?: unknown;
  ToleranciaArtigo58?: unknown;
  ToleranciaRefeicoesMinutos?: unknown;
  UsarDataFechamentoEncerrarSemana?: unknown;
  UsarTempoMaisMenosCargaSuperior?: unknown;
  UsarToleranciaRefeicoes?: unknown;
}

/** Espelhado em `secullum."HorarioToleranciaEspecificaItem"`. 22 campos lidos pelo código. */
export interface RawHorarioToleranciaEspecificaItem {
  DiaSemana?: unknown;
  Entrada1Ate?: unknown;
  Entrada1De?: unknown;
  Entrada2Ate?: unknown;
  Entrada2De?: unknown;
  Entrada3Ate?: unknown;
  Entrada3De?: unknown;
  Entrada4Ate?: unknown;
  Entrada4De?: unknown;
  Entrada5Ate?: unknown;
  Entrada5De?: unknown;
  HorarioId?: number | null;
  Saida1Ate?: unknown;
  Saida1De?: unknown;
  Saida2Ate?: unknown;
  Saida2De?: unknown;
  Saida3Ate?: unknown;
  Saida3De?: unknown;
  Saida4Ate?: unknown;
  Saida4De?: unknown;
  Saida5Ate?: unknown;
  Saida5De?: unknown;
}

// ---------------------------------------------------------------------------
// Nós aninhados. Não são importados por `cadastro-sync.ts` — existem porque o
// código atravessa `raw.Empresa?.Documento`, `raw.Estrutura?.Id` e afins, e um
// `unknown` estreitado por truthiness vira `{}`, que não tem campo nenhum.
// Cada um declara SÓ o que é atravessado.
// ---------------------------------------------------------------------------

/** `Funcionario.Departamento` — a unidade. Espelhado em `secullum."Departamento"`. */
export interface RawDepartamentoNode {
  Descricao?: string | null;
}

/** `Funcionario.Estrutura` — o GESTOR. Espelhado em `secullum."Estrutura"`. */
export interface RawEstruturaNode {
  /** Usado como chave de `Map`. */
  Id: number;
  /** É o NOME do gestor, não o de uma unidade. Vai direto para `resolveManagerEmailMatch`. */
  Descricao: string;
  /** `0` significa "sem pai", e o código trata isso explicitamente. */
  EstruturaPaiId?: number | null;
}

/** `Funcionario.Horario` — só o id é atravessado. */
export interface RawHorarioRef {
  Id?: number | null;
}

/** `Horario.ToleranciaEspecifica`. */
export interface RawHorarioToleranciaEspecificaNode {
  UsaToleranciaEspecifica?: unknown;
  Tolerancias?: RawHorarioToleranciaEspecificaItem[] | null;
}
