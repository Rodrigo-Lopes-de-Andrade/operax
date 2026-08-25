// Implementação de `SyncRepository` (cadastro-sync.ts) sobre conexão direta
// ao Postgres (driver `postgres`, service_role via DATABASE_URL do
// Transaction Pooler) — ver `_shared/postgres-client.ts` para o motivo de
// não usar supabase-js aqui (PostgREST não alcança `secullum`/`app`, mesmo
// com service_role: a lista "Exposed schemas" do projeto só tem
// public/graphql_public, e secullum/app NUNCA devem entrar nela — ver
// CLAUDE.md). Uso exclusivo do worker (Edge Function `sync-cadastro`), nunca
// do painel do Owner.
//
// ⚠️ Toda escrita aqui é em LOTE (um único upsert por tabela, uma única
// consulta por leitura em massa) — nunca uma chamada de rede por linha. Ver
// a nota de performance no topo de cadastro-sync.ts: o desenho anterior (uma
// chamada por item, dentro de um `for`) chegava a ~950 idas-e-voltas de rede
// numa única invocação, o suficiente para a Edge Function ser derrubada por
// `WORKER_RESOURCE_LIMIT` mesmo com um volume de dados modesto.
//
// ⚠️ NOMENCLATURA (ADR-012, migration 20260813160000/161000/162000) — "a
// regra do caso": `"PascalCase" entre aspas` é a cópia literal de um campo do
// Secullum (schema `secullum`); `minusculo_com_underscore` é nosso (uuid, FK
// interna, timestamp de controle, campo derivado — schema `app` para as
// tabelas 100% nossas: empresa_evento_status, funcionario_evento_status).
// Ver docs/04-modelo-dados.md §0 para o mapa completo coluna a coluna.
//
// ⚠️ Cada `on conflict ... do update set` abaixo é escrito por extenso de
// propósito (sem helper dinâmico) — é o padrão documentado do driver
// `postgres` para essa composição, e elimina qualquer ambiguidade sobre como
// uma lista de colunas dinâmica se comportaria dentro de uma tagged
// template.

import { getSql } from "./postgres-client.ts";
import type {
  CentroCustoRow,
  CidadeRow,
  DepartamentoRow,
  EmpresaRow,
  EstruturaRow,
  ExistingCentroCustoRow,
  ExistingEmpresaRow,
  ExistingFuncionarioAfastamentoRow,
  ExistingFuncionarioRow,
  FuncaoRow,
  FuncionarioAfastamentoRow,
  FuncionarioRow,
  HorarioDescansoRow,
  HorarioFaixasExtrasRow,
  HorarioRow,
  HorarioToleranciaEspecificaRow,
  InsertEmpresaEventoStatusInput,
  InsertFuncionarioEventoStatusInput,
  InsertHorarioDescansoFaixaItemInput,
  InsertHorarioFaixasExtrasInput,
  InsertHorarioFaixasExtrasItemInput,
  InsertHorarioToleranciaEspecificaItemInput,
  SyncRepository,
  UpsertCentroCustoInput,
  UpsertCidadeInput,
  UpsertDepartamentoInput,
  UpsertEmpresaInput,
  UpsertEstruturaInput,
  UpsertFuncaoInput,
  UpsertFuncionarioAfastamentoInput,
  UpsertFuncionarioInput,
  UpsertFuncionarioLeaveStatusInput,
  UpsertHorarioDescansoInput,
  UpsertHorarioDiaInput,
  UpsertHorarioExtrasInput,
  UpsertHorarioInput,
  UpsertHorariosOpcoesInput,
  UpsertHorarioToleranciaEspecificaInput,
} from "./cadastro-sync.ts";

// Colunas de "Funcionario" reusadas por upsertEmployees E por
// applyEmployeeLeaveStatus (que reenvia a linha inteira — ver a nota em
// UpsertFuncionarioLeaveStatusInput sobre por que colunas NOT NULL não podem
// ser omitidas num upsert em lote).
const FUNCIONARIO_BASE_COLUMNS = [
  "FuncionarioId",
  "departamento_id",
  "empresa_id",
  "Nome",
  "Cpf",
  "NumeroPis",
  "horario_id",
  "Admissao",
  "Demissao",
  "ativo",
  "EmpresaId",
  "DepartamentoId",
  "HorarioId",
  "EstruturaId",
  "cidade_id",
  "CidadeId",
  "funcao_id",
  "FuncaoId",
  "NumeroFolha",
  "NumeroIdentificador",
  "NumeroProvisorio",
  "Carteira",
  "CodigoHolerite",
  "Observacao",
  "Endereco",
  "Bairro",
  "Uf",
  "Cep",
  "Telefone",
  "Celular",
  "Email",
  "Rg",
  "ExpedicaoRg",
  "Ssp",
  "Mae",
  "Pai",
  "Nascimento",
  "Masculino",
  "Nacionalidade",
  "Naturalidade",
  "NaoVerificarDigital",
  "Master",
  "PossuiFoto",
  "Invisivel",
  "PeriodoEncerrado",
  "DesconsiderarPerimetrosGlobais",
  "AceitouTermosLgpdApp",
  "DataUltimoEnvio",
  "DataUltimoLogin",
  "DataAlteracao",
  "EscolaridadeId",
  "Filtro1Id",
  "Filtro2Id",
  "MotivoDemissaoId",
  "NivelPermissaoId",
  "PerfilId",
  "PerfilFuncionarioId",
  "BancoHorasId",
  "HorarioAlternativo2Id",
  "HorarioAlternativo3Id",
  "HorarioAlternativo4Id",
  "ConfigEspecificaInclusaoManualPonto",
  "ConfigEspecificaInclusaoManualPontoFusoHorarioId",
  "ConfigEspecificaDesativarVerificacaoLocalFicticio",
  "ConfigEspecificaInclusaoPontoSemLocalizacao",
  "ConfigEspecificaInclusaoPontoOffline",
  "ConfigEspecificaCapturaDeFotoNoMomentoDaInclusao",
  "BloquearRegistroPontoTeclado",
  "PermiteInclusaoPontoManual",
  "PermiteInclusaoDispositivosAutorizados",
  "DesabilitarAssinaturaEletronica",
  "atualizado_em",
] as const;

export class SupabaseSyncRepository implements SyncRepository {
  private readonly sql = getSql();

  async listCompanies(): Promise<ExistingEmpresaRow[]> {
    // Leitura em lote do estado ATUAL (ADR-009) — tabela pequena (uma linha
    // por Empresa), lida uma única vez, nunca um SELECT por empresa.
    const rows = await this.sql<{ id: string; Documento: string; ativo: boolean }[]>`
      select id, "Documento", ativo from secullum."Empresa"
    `;
    return rows.map((row) => ({
      id: row.id,
      secullumDocumento: row.Documento,
      active: row.ativo,
    }));
  }

  async upsertCompanies(inputs: UpsertEmpresaInput[]): Promise<EmpresaRow[]> {
    if (!inputs.length) return [];
    const now = new Date().toISOString();
    const rows = inputs.map((input) => ({
      Documento: input.secullumDocumento,
      Nome: input.name,
      // ⛔ `ativo` é COLUNA GERADA (migration 20260813161000) — o Postgres
      // rejeita qualquer escrita nela. Grava-se "Desativada" (o campo
      // literal do Secullum, negado); `ativo` se resolve sozinho
      // (`generated always as (coalesce(not "Desativada", true)) stored`).
      // `input.active` continua sendo o booleano já derivado por
      // `deriveCompanyActive` em cadastro-sync.ts — só a persistência
      // muda de coluna, a lógica de negócio não. NUNCA incluir "ativo" nas
      // colunas abaixo.
      Desativada: !input.active,
      // ADR-011 (Fase 2) — cadastro completo de Empresa.
      EmpresaId: input.secullumEmpresaId,
      Inscricao: input.inscricao,
      Endereco: input.endereco,
      Bairro: input.bairro,
      cidade_id: input.cityId,
      CidadeId: input.secullumCidadeId,
      Cep: input.cep,
      Uf: input.uf,
      Pais: input.pais,
      Telefone: input.telefone,
      Fax: input.fax,
      Cei: input.cei,
      NfolhaEmpresa: input.nfolhaEmpresa,
      Logotipo: input.logotipo,
      PossuiLogo: input.possuiLogo,
      ResponsavelNome: input.responsavelNome,
      ResponsavelCargo: input.responsavelCargo,
      ResponsavelEmail: input.responsavelEmail,
      TipoDocumento: input.tipoDocumento,
      UtilizaRepC: input.utilizaRepC,
      UtilizaRepA: input.utilizaRepA,
      UtilizaRepP: input.utilizaRepP,
      UsaFechamentoDoPontoEspecifico: input.usaFechamentoDoPontoEspecifico,
      FechamentoPonto: input.fechamentoPonto,
      DiaFechamentoPonto: input.diaFechamentoPonto,
      EmitiuAtestadoTecnico: input.emitiuAtestadoTecnico,
      atualizado_em: now,
    }));
    const columns = [
      "Documento",
      "Nome",
      "Desativada",
      "EmpresaId",
      "Inscricao",
      "Endereco",
      "Bairro",
      "cidade_id",
      "CidadeId",
      "Cep",
      "Uf",
      "Pais",
      "Telefone",
      "Fax",
      "Cei",
      "NfolhaEmpresa",
      "Logotipo",
      "PossuiLogo",
      "ResponsavelNome",
      "ResponsavelCargo",
      "ResponsavelEmail",
      "TipoDocumento",
      "UtilizaRepC",
      "UtilizaRepA",
      "UtilizaRepP",
      "UsaFechamentoDoPontoEspecifico",
      "FechamentoPonto",
      "DiaFechamentoPonto",
      "EmitiuAtestadoTecnico",
      "atualizado_em",
    ];
    const result = await this.sql<{ id: string; Documento: string }[]>`
      insert into secullum."Empresa" ${this.sql(rows, ...columns)}
      on conflict ("Documento") do update set
        "Nome" = excluded."Nome",
        "Desativada" = excluded."Desativada",
        "EmpresaId" = excluded."EmpresaId",
        "Inscricao" = excluded."Inscricao",
        "Endereco" = excluded."Endereco",
        "Bairro" = excluded."Bairro",
        cidade_id = excluded.cidade_id,
        "CidadeId" = excluded."CidadeId",
        "Cep" = excluded."Cep",
        "Uf" = excluded."Uf",
        "Pais" = excluded."Pais",
        "Telefone" = excluded."Telefone",
        "Fax" = excluded."Fax",
        "Cei" = excluded."Cei",
        "NfolhaEmpresa" = excluded."NfolhaEmpresa",
        "Logotipo" = excluded."Logotipo",
        "PossuiLogo" = excluded."PossuiLogo",
        "ResponsavelNome" = excluded."ResponsavelNome",
        "ResponsavelCargo" = excluded."ResponsavelCargo",
        "ResponsavelEmail" = excluded."ResponsavelEmail",
        "TipoDocumento" = excluded."TipoDocumento",
        "UtilizaRepC" = excluded."UtilizaRepC",
        "UtilizaRepA" = excluded."UtilizaRepA",
        "UtilizaRepP" = excluded."UtilizaRepP",
        "UsaFechamentoDoPontoEspecifico" = excluded."UsaFechamentoDoPontoEspecifico",
        "FechamentoPonto" = excluded."FechamentoPonto",
        "DiaFechamentoPonto" = excluded."DiaFechamentoPonto",
        "EmitiuAtestadoTecnico" = excluded."EmitiuAtestadoTecnico",
        atualizado_em = excluded.atualizado_em
      returning id, "Documento"
    `;
    return result.map((row) => ({ id: row.id, secullumDocumento: row.Documento }));
  }

  async upsertCities(inputs: UpsertCidadeInput[]): Promise<CidadeRow[]> {
    if (!inputs.length) return [];
    // ADR-011 — "Cidade" não precisa de leitura prévia (sem histórico/
    // diffing): um único upsert em lote por "Descricao" (chave de
    // idempotência) resolve tanto "já existe" quanto "é nova".
    const now = new Date().toISOString();
    const rows = inputs.map((input) => ({
      Descricao: input.descricao,
      CidadeId: input.secullumCidadeId,
      atualizado_em: now,
    }));
    const result = await this.sql<{ id: string; Descricao: string }[]>`
      insert into secullum."Cidade" ${this.sql(rows, "Descricao", "CidadeId", "atualizado_em")}
      on conflict ("Descricao") do update set
        "CidadeId" = excluded."CidadeId",
        atualizado_em = excluded.atualizado_em
      returning id, "Descricao"
    `;
    return result.map((row) => ({ id: row.id, descricao: row.Descricao }));
  }

  async upsertFunctions(inputs: UpsertFuncaoInput[]): Promise<FuncaoRow[]> {
    if (!inputs.length) return [];
    const now = new Date().toISOString();
    const rows = inputs.map((input) => ({
      Descricao: input.descricao,
      FuncaoId: input.secullumFuncaoId,
      atualizado_em: now,
    }));
    const result = await this.sql<{ id: string; Descricao: string }[]>`
      insert into secullum."Funcao" ${this.sql(rows, "Descricao", "FuncaoId", "atualizado_em")}
      on conflict ("Descricao") do update set
        "FuncaoId" = excluded."FuncaoId",
        atualizado_em = excluded.atualizado_em
      returning id, "Descricao"
    `;
    return result.map((row) => ({ id: row.id, descricao: row.Descricao }));
  }

  async listUnits(): Promise<DepartamentoRow[]> {
    // Tabela pequena (uma linha por Departamento do Secullum) — uma única
    // leitura em massa substitui um SELECT por departamento dentro do laço de
    // funcionários.
    const rows = await this.sql<{ id: string; empresa_id: string; DepartamentoId: number }[]>`
      select id, empresa_id, "DepartamentoId" from secullum."Departamento"
    `;
    return rows.map((row) => ({
      id: row.id,
      companyId: row.empresa_id,
      secullumRef: row.DepartamentoId,
    }));
  }

  async upsertUnits(inputs: UpsertDepartamentoInput[]): Promise<DepartamentoRow[]> {
    if (!inputs.length) return [];
    const now = new Date().toISOString();
    const rows = inputs.map((input) => ({
      DepartamentoId: input.secullumRef,
      Descricao: input.name,
      empresa_id: input.companyId,
      ativo: input.active,
      atualizado_em: now,
    }));
    const result = await this.sql<{ id: string; empresa_id: string; DepartamentoId: number }[]>`
      insert into secullum."Departamento" ${
      this.sql(rows, "DepartamentoId", "Descricao", "empresa_id", "ativo", "atualizado_em")
    }
      on conflict ("DepartamentoId") do update set
        "Descricao" = excluded."Descricao",
        empresa_id = excluded.empresa_id,
        ativo = excluded.ativo,
        atualizado_em = excluded.atualizado_em
      returning id, empresa_id, "DepartamentoId"
    `;
    return result.map((row) => ({
      id: row.id,
      companyId: row.empresa_id,
      secullumRef: row.DepartamentoId,
    }));
  }

  async upsertWorkSchedules(inputs: UpsertHorarioInput[]): Promise<HorarioRow[]> {
    if (!inputs.length) return [];
    const now = new Date().toISOString();
    const rows = inputs.map((input) => ({
      HorarioId: input.secullumHorarioId,
      Numero: input.secullumHorarioNumero,
      Descricao: input.description,
      // ⚠️ Nenhuma coluna "UsaToleranciaEspecifica" aqui: foi REMOVIDA de
      // "Horario" pela migration 20260813162000 (a árvore completa de
      // Horarios — "HorarioToleranciaEspecifica" — vive em tabela própria).
      // O aviso `schedule_uses_specific_tolerance` continua emitido em
      // cadastro-sync.ts, lido direto do payload cru.
      ativo: input.active,
      sincronizado_em: now,
      atualizado_em: now,
    }));
    const result = await this.sql<{ id: string; HorarioId: number }[]>`
      insert into secullum."Horario" ${
      this.sql(rows, "HorarioId", "Numero", "Descricao", "ativo", "sincronizado_em", "atualizado_em")
    }
      on conflict ("HorarioId") do update set
        "Numero" = excluded."Numero",
        "Descricao" = excluded."Descricao",
        ativo = excluded.ativo,
        sincronizado_em = excluded.sincronizado_em,
        atualizado_em = excluded.atualizado_em
      returning id, "HorarioId"
    `;
    return result.map((row) => ({ id: row.id, secullumHorarioId: row.HorarioId }));
  }

  async upsertWorkScheduleDays(inputs: UpsertHorarioDiaInput[]): Promise<void> {
    if (!inputs.length) return;
    const now = new Date().toISOString();
    const rows = inputs.map((input) => ({
      horario_id: input.workScheduleId,
      HorarioDiaId: input.secullumHorarioDiaId,
      DiaSemana: input.weekday,
      Entrada1: input.entry1,
      Entrada2: input.entry2,
      Entrada3: input.entry3,
      Entrada4: input.entry4,
      Entrada5: input.entry5,
      Saida1: input.exit1,
      Saida2: input.exit2,
      Saida3: input.exit3,
      Saida4: input.exit4,
      Saida5: input.exit5,
      TipoEntrada1: input.entryType1,
      TipoEntrada2: input.entryType2,
      TipoEntrada3: input.entryType3,
      TipoEntrada4: input.entryType4,
      TipoEntrada5: input.entryType5,
      TipoSaida1: input.exitType1,
      TipoSaida2: input.exitType2,
      TipoSaida3: input.exitType3,
      TipoSaida4: input.exitType4,
      TipoSaida5: input.exitType5,
      ToleranciaExtra: input.toleranceExtraMinutes,
      ToleranciaFalta: input.toleranceAbsenceMinutes,
      Carga: input.workloadMinutes,
      TipoDia: input.dayType,
      Neutro: input.isNeutral,
      Compensado: input.isCompensated,
      AlmocoLivre: input.freeLunch,
      Alocar24Horas: input.allocate24Hours,
      sem_expediente: input.isDayOff,
      atualizado_em: now,
    }));
    const columns = [
      "horario_id",
      "HorarioDiaId",
      "DiaSemana",
      "Entrada1",
      "Entrada2",
      "Entrada3",
      "Entrada4",
      "Entrada5",
      "Saida1",
      "Saida2",
      "Saida3",
      "Saida4",
      "Saida5",
      "TipoEntrada1",
      "TipoEntrada2",
      "TipoEntrada3",
      "TipoEntrada4",
      "TipoEntrada5",
      "TipoSaida1",
      "TipoSaida2",
      "TipoSaida3",
      "TipoSaida4",
      "TipoSaida5",
      "ToleranciaExtra",
      "ToleranciaFalta",
      "Carga",
      "TipoDia",
      "Neutro",
      "Compensado",
      "AlmocoLivre",
      "Alocar24Horas",
      "sem_expediente",
      "atualizado_em",
    ];
    await this.sql`
      insert into secullum."HorarioDia" ${this.sql(rows, ...columns)}
      on conflict (horario_id, "DiaSemana") do update set
        "HorarioDiaId" = excluded."HorarioDiaId",
        "Entrada1" = excluded."Entrada1",
        "Entrada2" = excluded."Entrada2",
        "Entrada3" = excluded."Entrada3",
        "Entrada4" = excluded."Entrada4",
        "Entrada5" = excluded."Entrada5",
        "Saida1" = excluded."Saida1",
        "Saida2" = excluded."Saida2",
        "Saida3" = excluded."Saida3",
        "Saida4" = excluded."Saida4",
        "Saida5" = excluded."Saida5",
        "TipoEntrada1" = excluded."TipoEntrada1",
        "TipoEntrada2" = excluded."TipoEntrada2",
        "TipoEntrada3" = excluded."TipoEntrada3",
        "TipoEntrada4" = excluded."TipoEntrada4",
        "TipoEntrada5" = excluded."TipoEntrada5",
        "TipoSaida1" = excluded."TipoSaida1",
        "TipoSaida2" = excluded."TipoSaida2",
        "TipoSaida3" = excluded."TipoSaida3",
        "TipoSaida4" = excluded."TipoSaida4",
        "TipoSaida5" = excluded."TipoSaida5",
        "ToleranciaExtra" = excluded."ToleranciaExtra",
        "ToleranciaFalta" = excluded."ToleranciaFalta",
        "Carga" = excluded."Carga",
        "TipoDia" = excluded."TipoDia",
        "Neutro" = excluded."Neutro",
        "Compensado" = excluded."Compensado",
        "AlmocoLivre" = excluded."AlmocoLivre",
        "Alocar24Horas" = excluded."Alocar24Horas",
        sem_expediente = excluded.sem_expediente,
        atualizado_em = excluded.atualizado_em
    `;
  }

  async listManagers(): Promise<EstruturaRow[]> {
    // Tabela pequena (uma linha por Estrutura/gestor) — uma única leitura em
    // massa substitui um SELECT por gestor dentro do laço de funcionários.
    const rows = await this.sql<
      { id: string; EstruturaId: number; email: string | null; email_origem: "manual" | "secullum" }[]
    >`
      select id, "EstruturaId", email, email_origem from secullum."Estrutura"
    `;
    return rows.map((row) => ({
      id: row.id,
      secullumEstruturaId: row.EstruturaId,
      email: row.email ?? null,
      emailSource: row.email_origem,
    }));
  }

  async upsertManagers(inputs: UpsertEstruturaInput[]): Promise<EstruturaRow[]> {
    if (!inputs.length) return [];
    const now = new Date().toISOString();
    // Todo item já traz `email`/`emailSource` explícitos (nunca omitidos) —
    // ver a nota em `UpsertEstruturaInput.email` sobre por que isso é
    // obrigatório num upsert em LOTE (chave ausente em algum item vira
    // DEFAULT da coluna para TODAS as linhas do lote, o que sobrescreveria
    // silenciosamente um `email_origem = 'manual'` protegido).
    const rows = inputs.map((input) => ({
      EstruturaId: input.secullumEstruturaId,
      EstruturaPaiId: input.secullumEstruturaPaiId,
      departamento_id: input.unitId,
      Descricao: input.name,
      email: input.email,
      email_origem: input.emailSource,
      atualizado_em: now,
    }));
    const result = await this.sql<
      { id: string; EstruturaId: number; email: string | null; email_origem: "manual" | "secullum" }[]
    >`
      insert into secullum."Estrutura" ${
      this.sql(
        rows,
        "EstruturaId",
        "EstruturaPaiId",
        "departamento_id",
        "Descricao",
        "email",
        "email_origem",
        "atualizado_em",
      )
    }
      on conflict ("EstruturaId") do update set
        "EstruturaPaiId" = excluded."EstruturaPaiId",
        departamento_id = excluded.departamento_id,
        "Descricao" = excluded."Descricao",
        email = excluded.email,
        email_origem = excluded.email_origem,
        atualizado_em = excluded.atualizado_em
      returning id, "EstruturaId", email, email_origem
    `;
    return result.map((row) => ({
      id: row.id,
      secullumEstruturaId: row.EstruturaId,
      email: row.email ?? null,
      emailSource: row.email_origem,
    }));
  }

  async listEmployees(): Promise<ExistingFuncionarioRow[]> {
    // Leitura em lote do estado ATUAL (ADR-009) — necessária para comparar
    // com o snapshot recém-derivado e decidir o funcionario_evento_status,
    // sem nunca fazer um SELECT por funcionário dentro do laço.
    // ⚠️ Cast explícito para text: o driver `postgres` devolve colunas
    // `date` como objeto `Date` do JS por padrão, não como string
    // "YYYY-MM-DD" (diferença de PostgREST, que sempre serializa como
    // string) — sem o cast, buildEmployeeStatusEvent compararia Date !==
    // string sempre, gerando "date_correction" espúrio (violando o CHECK
    // funcionario_evento_status_mudanca_check quando active também não mudou
    // de fato).
    const rows = await this.sql<
      { id: string; FuncionarioId: number; ativo: boolean; Admissao: string | null; Demissao: string | null }[]
    >`
      select id, "FuncionarioId", ativo, "Admissao"::text as "Admissao", "Demissao"::text as "Demissao"
      from secullum."Funcionario"
    `;
    return rows.map((row) => ({
      id: row.id,
      secullumFuncionarioId: row.FuncionarioId,
      active: row.ativo,
      admissionDate: row.Admissao ?? null,
      terminationDate: row.Demissao ?? null,
    }));
  }

  /**
   * ADR-011 (Fase 2) — monta a linha COMPLETA de "Funcionario" a partir de um
   * `UpsertFuncionarioInput`. Extraído em método próprio porque é reusado por
   * `upsertEmployees` E por `applyEmployeeLeaveStatus` (que reenvia a linha
   * inteira num upsert em lote).
   *
   * ⚠️ TODA ESTA LINHA É DADO PESSOAL, incluindo PII sensível a partir daqui
   * (RG, endereço, telefone, filiação, nascimento, observação em texto
   * livre). Nunca logar o retorno desta função.
   */
  private buildFuncionarioRow(input: UpsertFuncionarioInput, now: string): Record<string, unknown> {
    return {
      FuncionarioId: input.secullumFuncionarioId,
      departamento_id: input.unitId,
      empresa_id: input.companyId,
      Nome: input.name,
      Cpf: input.secullumCpf,
      NumeroPis: input.secullumPis,
      horario_id: input.scheduleId,
      Admissao: input.admissionDate,
      Demissao: input.terminationDate,
      ativo: input.active,

      EmpresaId: input.secullumEmpresaId,
      DepartamentoId: input.secullumDepartamentoId,
      HorarioId: input.secullumHorarioId,
      EstruturaId: input.secullumEstruturaId,

      cidade_id: input.cityId,
      CidadeId: input.secullumCidadeId,
      funcao_id: input.functionId,
      FuncaoId: input.secullumFuncaoId,

      NumeroFolha: input.numeroFolha,
      NumeroIdentificador: input.numeroIdentificador,
      NumeroProvisorio: input.numeroProvisorio,
      Carteira: input.carteira,
      CodigoHolerite: input.codigoHolerite,
      Observacao: input.observacao,

      Endereco: input.endereco,
      Bairro: input.bairro,
      Uf: input.uf,
      Cep: input.cep,
      Telefone: input.telefone,
      Celular: input.celular,
      Email: input.email,

      Rg: input.rg,
      ExpedicaoRg: input.expedicaoRg,
      Ssp: input.ssp,
      Mae: input.mae,
      Pai: input.pai,
      Nascimento: input.nascimento,
      Masculino: input.masculino,
      Nacionalidade: input.nacionalidade,
      Naturalidade: input.naturalidade,

      NaoVerificarDigital: input.naoVerificarDigital,
      Master: input.master,
      PossuiFoto: input.possuiFoto,
      Invisivel: input.invisivel,
      PeriodoEncerrado: input.periodoEncerrado,
      DesconsiderarPerimetrosGlobais: input.desconsiderarPerimetrosGlobais,
      AceitouTermosLgpdApp: input.aceitouTermosLgpdApp,
      DataUltimoEnvio: input.dataUltimoEnvio,
      DataUltimoLogin: input.dataUltimoLogin,
      DataAlteracao: input.dataAlteracao,

      EscolaridadeId: input.escolaridadeId,
      Filtro1Id: input.filtro1Id,
      Filtro2Id: input.filtro2Id,
      MotivoDemissaoId: input.motivoDemissaoId,
      NivelPermissaoId: input.nivelPermissaoId,
      PerfilId: input.perfilId,
      PerfilFuncionarioId: input.perfilFuncionarioId,
      BancoHorasId: input.bancoHorasId,
      HorarioAlternativo2Id: input.horarioAlternativo2Id,
      HorarioAlternativo3Id: input.horarioAlternativo3Id,
      HorarioAlternativo4Id: input.horarioAlternativo4Id,

      ConfigEspecificaInclusaoManualPonto: input.configEspecificaInclusaoManualPonto,
      ConfigEspecificaInclusaoManualPontoFusoHorarioId:
        input.configEspecificaInclusaoManualPontoFusoHorarioId,
      ConfigEspecificaDesativarVerificacaoLocalFicticio:
        input.configEspecificaDesativarVerificacaoLocalFicticio,
      ConfigEspecificaInclusaoPontoSemLocalizacao:
        input.configEspecificaInclusaoPontoSemLocalizacao,
      ConfigEspecificaInclusaoPontoOffline: input.configEspecificaInclusaoPontoOffline,
      ConfigEspecificaCapturaDeFotoNoMomentoDaInclusao:
        input.configEspecificaCapturaDeFotoNoMomentoDaInclusao,
      BloquearRegistroPontoTeclado: input.bloquearRegistroPontoTeclado,
      PermiteInclusaoPontoManual: input.permiteInclusaoPontoManual,
      PermiteInclusaoDispositivosAutorizados: input.permiteInclusaoDispositivosAutorizados,
      DesabilitarAssinaturaEletronica: input.desabilitarAssinaturaEletronica,

      atualizado_em: now,
    };
  }

  async upsertEmployees(inputs: UpsertFuncionarioInput[]): Promise<FuncionarioRow[]> {
    if (!inputs.length) return [];
    const now = new Date().toISOString();
    const rows = inputs.map((input) => this.buildFuncionarioRow(input, now));
    const result = await this.sql<{ id: string; FuncionarioId: number }[]>`
      insert into secullum."Funcionario" ${this.sql(rows, ...FUNCIONARIO_BASE_COLUMNS)}
      on conflict ("FuncionarioId") do update set
        departamento_id = excluded.departamento_id,
        empresa_id = excluded.empresa_id,
        "Nome" = excluded."Nome",
        "Cpf" = excluded."Cpf",
        "NumeroPis" = excluded."NumeroPis",
        horario_id = excluded.horario_id,
        "Admissao" = excluded."Admissao",
        "Demissao" = excluded."Demissao",
        ativo = excluded.ativo,
        "EmpresaId" = excluded."EmpresaId",
        "DepartamentoId" = excluded."DepartamentoId",
        "HorarioId" = excluded."HorarioId",
        "EstruturaId" = excluded."EstruturaId",
        cidade_id = excluded.cidade_id,
        "CidadeId" = excluded."CidadeId",
        funcao_id = excluded.funcao_id,
        "FuncaoId" = excluded."FuncaoId",
        "NumeroFolha" = excluded."NumeroFolha",
        "NumeroIdentificador" = excluded."NumeroIdentificador",
        "NumeroProvisorio" = excluded."NumeroProvisorio",
        "Carteira" = excluded."Carteira",
        "CodigoHolerite" = excluded."CodigoHolerite",
        "Observacao" = excluded."Observacao",
        "Endereco" = excluded."Endereco",
        "Bairro" = excluded."Bairro",
        "Uf" = excluded."Uf",
        "Cep" = excluded."Cep",
        "Telefone" = excluded."Telefone",
        "Celular" = excluded."Celular",
        "Email" = excluded."Email",
        "Rg" = excluded."Rg",
        "ExpedicaoRg" = excluded."ExpedicaoRg",
        "Ssp" = excluded."Ssp",
        "Mae" = excluded."Mae",
        "Pai" = excluded."Pai",
        "Nascimento" = excluded."Nascimento",
        "Masculino" = excluded."Masculino",
        "Nacionalidade" = excluded."Nacionalidade",
        "Naturalidade" = excluded."Naturalidade",
        "NaoVerificarDigital" = excluded."NaoVerificarDigital",
        "Master" = excluded."Master",
        "PossuiFoto" = excluded."PossuiFoto",
        "Invisivel" = excluded."Invisivel",
        "PeriodoEncerrado" = excluded."PeriodoEncerrado",
        "DesconsiderarPerimetrosGlobais" = excluded."DesconsiderarPerimetrosGlobais",
        "AceitouTermosLgpdApp" = excluded."AceitouTermosLgpdApp",
        "DataUltimoEnvio" = excluded."DataUltimoEnvio",
        "DataUltimoLogin" = excluded."DataUltimoLogin",
        "DataAlteracao" = excluded."DataAlteracao",
        "EscolaridadeId" = excluded."EscolaridadeId",
        "Filtro1Id" = excluded."Filtro1Id",
        "Filtro2Id" = excluded."Filtro2Id",
        "MotivoDemissaoId" = excluded."MotivoDemissaoId",
        "NivelPermissaoId" = excluded."NivelPermissaoId",
        "PerfilId" = excluded."PerfilId",
        "PerfilFuncionarioId" = excluded."PerfilFuncionarioId",
        "BancoHorasId" = excluded."BancoHorasId",
        "HorarioAlternativo2Id" = excluded."HorarioAlternativo2Id",
        "HorarioAlternativo3Id" = excluded."HorarioAlternativo3Id",
        "HorarioAlternativo4Id" = excluded."HorarioAlternativo4Id",
        "ConfigEspecificaInclusaoManualPonto" = excluded."ConfigEspecificaInclusaoManualPonto",
        "ConfigEspecificaInclusaoManualPontoFusoHorarioId" = excluded."ConfigEspecificaInclusaoManualPontoFusoHorarioId",
        "ConfigEspecificaDesativarVerificacaoLocalFicticio" = excluded."ConfigEspecificaDesativarVerificacaoLocalFicticio",
        "ConfigEspecificaInclusaoPontoSemLocalizacao" = excluded."ConfigEspecificaInclusaoPontoSemLocalizacao",
        "ConfigEspecificaInclusaoPontoOffline" = excluded."ConfigEspecificaInclusaoPontoOffline",
        "ConfigEspecificaCapturaDeFotoNoMomentoDaInclusao" = excluded."ConfigEspecificaCapturaDeFotoNoMomentoDaInclusao",
        "BloquearRegistroPontoTeclado" = excluded."BloquearRegistroPontoTeclado",
        "PermiteInclusaoPontoManual" = excluded."PermiteInclusaoPontoManual",
        "PermiteInclusaoDispositivosAutorizados" = excluded."PermiteInclusaoDispositivosAutorizados",
        "DesabilitarAssinaturaEletronica" = excluded."DesabilitarAssinaturaEletronica",
        atualizado_em = excluded.atualizado_em
      returning id, "FuncionarioId"
    `;
    return result.map((row) => ({ id: row.id, secullumFuncionarioId: row.FuncionarioId }));
  }

  async insertCompanyStatusEvents(inputs: InsertEmpresaEventoStatusInput[]): Promise<void> {
    if (!inputs.length) return;
    // Único INSERT em lote — `empresa_evento_status` é append-only
    // (docs/04-modelo-dados.md): nunca UPDATE/DELETE aqui. `detectado_em`
    // (default now()) e `origem` (default 'secullum_sync') ficam a cargo do
    // DEFAULT da tabela.
    const rows = inputs.map((input) => ({
      empresa_id: input.companyId,
      tipo_evento: input.eventType,
      ativo_anterior: input.previousActive,
      ativo_novo: input.newActive,
    }));
    await this.sql`
      insert into app.empresa_evento_status ${
      this.sql(rows, "empresa_id", "tipo_evento", "ativo_anterior", "ativo_novo")
    }
    `;
  }

  async insertEmployeeStatusEvents(inputs: InsertFuncionarioEventoStatusInput[]): Promise<void> {
    if (!inputs.length) return;
    // Único INSERT em lote — `funcionario_evento_status` é append-only, mesma
    // disciplina de empresa_evento_status acima.
    const rows = inputs.map((input) => ({
      funcionario_id: input.employeeId,
      tipo_evento: input.eventType,
      ativo_anterior: input.previousActive,
      ativo_novo: input.newActive,
      data_evento: input.eventDate,
      admissao_anterior: input.previousAdmissionDate,
      admissao_nova: input.newAdmissionDate,
      demissao_anterior: input.previousTerminationDate,
      demissao_nova: input.newTerminationDate,
    }));
    await this.sql`
      insert into app.funcionario_evento_status ${
      this.sql(
        rows,
        "funcionario_id",
        "tipo_evento",
        "ativo_anterior",
        "ativo_novo",
        "data_evento",
        "admissao_anterior",
        "admissao_nova",
        "demissao_anterior",
        "demissao_nova",
      )
    }
    `;
  }

  async listEmployeeAbsences(): Promise<ExistingFuncionarioAfastamentoRow[]> {
    // Leitura em lote do estado ATUAL (ADR-010) — base da convergência e do
    // recálculo de afastado_hoje, nunca um SELECT por afastamento.
    // ⚠️ Cast explícito para text — mesmo motivo de listEmployees() acima.
    const rows = await this.sql<
      { id: string; funcionario_id: string; AfastamentoId: number; Inicio: string; Fim: string }[]
    >`
      select id, funcionario_id, "AfastamentoId", "Inicio"::text as "Inicio", "Fim"::text as "Fim"
      from secullum."FuncionarioAfastamento"
    `;
    return rows.map((row) => ({
      id: row.id,
      employeeId: row.funcionario_id,
      secullumAfastamentoId: row.AfastamentoId,
      startDate: row.Inicio,
      endDate: row.Fim,
    }));
  }

  async upsertEmployeeAbsences(
    inputs: UpsertFuncionarioAfastamentoInput[],
  ): Promise<FuncionarioAfastamentoRow[]> {
    if (!inputs.length) return [];
    const now = new Date().toISOString();
    // Chave de idempotência COMPOSTA (ADR-010, Decisão 3) — nunca
    // "AfastamentoId" sozinho (não confirmado como globalmente único).
    const rows = inputs.map((input) => ({
      funcionario_id: input.employeeId,
      AfastamentoId: input.secullumAfastamentoId,
      Inicio: input.startDate,
      Fim: input.endDate,
      JustificativaNome: input.justificationCode,
      DataInclusao: input.secullumIncludedAt,
      correlacionado_por: input.matchedBy,
      sincronizado_em: now,
      atualizado_em: now,
    }));
    const result = await this.sql<
      { id: string; funcionario_id: string; AfastamentoId: number }[]
    >`
      insert into secullum."FuncionarioAfastamento" ${
      this.sql(
        rows,
        "funcionario_id",
        "AfastamentoId",
        "Inicio",
        "Fim",
        "JustificativaNome",
        "DataInclusao",
        "correlacionado_por",
        "sincronizado_em",
        "atualizado_em",
      )
    }
      on conflict (funcionario_id, "AfastamentoId") do update set
        "Inicio" = excluded."Inicio",
        "Fim" = excluded."Fim",
        "JustificativaNome" = excluded."JustificativaNome",
        "DataInclusao" = excluded."DataInclusao",
        correlacionado_por = excluded.correlacionado_por,
        atualizado_em = excluded.atualizado_em
      returning id, funcionario_id, "AfastamentoId"
    `;
    return result.map((row) => ({
      id: row.id,
      employeeId: row.funcionario_id,
      secullumAfastamentoId: row.AfastamentoId,
    }));
  }

  async deleteEmployeeAbsencesByIds(ids: string[]): Promise<void> {
    if (!ids.length) return; // defensivo — nunca DELETE sem filtro (ADR-010, Decisão 7).
    await this.sql`delete from secullum."FuncionarioAfastamento" where id in ${this.sql(ids)}`;
  }

  async applyEmployeeLeaveStatus(inputs: UpsertFuncionarioLeaveStatusInput[]): Promise<void> {
    if (!inputs.length) return;
    const now = new Date().toISOString();
    // ⚠️ Reenvia a linha de `Funcionario` INTEIRA (ver a nota em
    // UpsertFuncionarioLeaveStatusInput sobre por que colunas NOT NULL não
    // podem ser omitidas num upsert em lote) — só isso e mais
    // afastado_hoje/afastamento_atual_id, nunca um UPDATE por funcionário.
    const rows = inputs.map((input) => ({
      ...this.buildFuncionarioRow(input, now),
      afastado_hoje: input.onLeave,
      afastamento_atual_id: input.currentAbsenceId,
    }));
    const columns = [...FUNCIONARIO_BASE_COLUMNS, "afastado_hoje", "afastamento_atual_id"];
    await this.sql`
      insert into secullum."Funcionario" ${this.sql(rows, ...columns)}
      on conflict ("FuncionarioId") do update set
        departamento_id = excluded.departamento_id,
        empresa_id = excluded.empresa_id,
        "Nome" = excluded."Nome",
        "Cpf" = excluded."Cpf",
        "NumeroPis" = excluded."NumeroPis",
        horario_id = excluded.horario_id,
        "Admissao" = excluded."Admissao",
        "Demissao" = excluded."Demissao",
        ativo = excluded.ativo,
        "EmpresaId" = excluded."EmpresaId",
        "DepartamentoId" = excluded."DepartamentoId",
        "HorarioId" = excluded."HorarioId",
        "EstruturaId" = excluded."EstruturaId",
        cidade_id = excluded.cidade_id,
        "CidadeId" = excluded."CidadeId",
        funcao_id = excluded.funcao_id,
        "FuncaoId" = excluded."FuncaoId",
        "NumeroFolha" = excluded."NumeroFolha",
        "NumeroIdentificador" = excluded."NumeroIdentificador",
        "NumeroProvisorio" = excluded."NumeroProvisorio",
        "Carteira" = excluded."Carteira",
        "CodigoHolerite" = excluded."CodigoHolerite",
        "Observacao" = excluded."Observacao",
        "Endereco" = excluded."Endereco",
        "Bairro" = excluded."Bairro",
        "Uf" = excluded."Uf",
        "Cep" = excluded."Cep",
        "Telefone" = excluded."Telefone",
        "Celular" = excluded."Celular",
        "Email" = excluded."Email",
        "Rg" = excluded."Rg",
        "ExpedicaoRg" = excluded."ExpedicaoRg",
        "Ssp" = excluded."Ssp",
        "Mae" = excluded."Mae",
        "Pai" = excluded."Pai",
        "Nascimento" = excluded."Nascimento",
        "Masculino" = excluded."Masculino",
        "Nacionalidade" = excluded."Nacionalidade",
        "Naturalidade" = excluded."Naturalidade",
        "NaoVerificarDigital" = excluded."NaoVerificarDigital",
        "Master" = excluded."Master",
        "PossuiFoto" = excluded."PossuiFoto",
        "Invisivel" = excluded."Invisivel",
        "PeriodoEncerrado" = excluded."PeriodoEncerrado",
        "DesconsiderarPerimetrosGlobais" = excluded."DesconsiderarPerimetrosGlobais",
        "AceitouTermosLgpdApp" = excluded."AceitouTermosLgpdApp",
        "DataUltimoEnvio" = excluded."DataUltimoEnvio",
        "DataUltimoLogin" = excluded."DataUltimoLogin",
        "DataAlteracao" = excluded."DataAlteracao",
        "EscolaridadeId" = excluded."EscolaridadeId",
        "Filtro1Id" = excluded."Filtro1Id",
        "Filtro2Id" = excluded."Filtro2Id",
        "MotivoDemissaoId" = excluded."MotivoDemissaoId",
        "NivelPermissaoId" = excluded."NivelPermissaoId",
        "PerfilId" = excluded."PerfilId",
        "PerfilFuncionarioId" = excluded."PerfilFuncionarioId",
        "BancoHorasId" = excluded."BancoHorasId",
        "HorarioAlternativo2Id" = excluded."HorarioAlternativo2Id",
        "HorarioAlternativo3Id" = excluded."HorarioAlternativo3Id",
        "HorarioAlternativo4Id" = excluded."HorarioAlternativo4Id",
        "ConfigEspecificaInclusaoManualPonto" = excluded."ConfigEspecificaInclusaoManualPonto",
        "ConfigEspecificaInclusaoManualPontoFusoHorarioId" = excluded."ConfigEspecificaInclusaoManualPontoFusoHorarioId",
        "ConfigEspecificaDesativarVerificacaoLocalFicticio" = excluded."ConfigEspecificaDesativarVerificacaoLocalFicticio",
        "ConfigEspecificaInclusaoPontoSemLocalizacao" = excluded."ConfigEspecificaInclusaoPontoSemLocalizacao",
        "ConfigEspecificaInclusaoPontoOffline" = excluded."ConfigEspecificaInclusaoPontoOffline",
        "ConfigEspecificaCapturaDeFotoNoMomentoDaInclusao" = excluded."ConfigEspecificaCapturaDeFotoNoMomentoDaInclusao",
        "BloquearRegistroPontoTeclado" = excluded."BloquearRegistroPontoTeclado",
        "PermiteInclusaoPontoManual" = excluded."PermiteInclusaoPontoManual",
        "PermiteInclusaoDispositivosAutorizados" = excluded."PermiteInclusaoDispositivosAutorizados",
        "DesabilitarAssinaturaEletronica" = excluded."DesabilitarAssinaturaEletronica",
        atualizado_em = excluded.atualizado_em,
        afastado_hoje = excluded.afastado_hoje,
        afastamento_atual_id = excluded.afastamento_atual_id
    `;
  }

  async listCostCenters(): Promise<ExistingCentroCustoRow[]> {
    // Tabela pequena (um centro de custo por funcionário-vínculo) — leitura
    // em massa, nunca um SELECT por funcionário (ADR-011).
    const rows = await this.sql<{ id: string; funcionario_id: string; Descricao: string }[]>`
      select id, funcionario_id, "Descricao" from secullum."FuncionarioCentroCusto"
    `;
    return rows.map((row) => ({
      id: row.id,
      employeeId: row.funcionario_id,
      descricao: row.Descricao,
    }));
  }

  async upsertCostCenters(inputs: UpsertCentroCustoInput[]): Promise<CentroCustoRow[]> {
    if (!inputs.length) return [];
    // Chave de idempotência COMPOSTA (funcionario_id, "Descricao") — mesmo
    // padrão de FuncionarioAfastamento (ADR-010). Sem `atualizado_em`: a
    // tabela não tem essa coluna (único campo do item é "Descricao", que já
    // é a própria chave — não há nada mais para atualizar num conflito, mas
    // o DO UPDATE precisa existir para o `returning` funcionar em cima da
    // linha existente).
    const rows = inputs.map((input) => ({
      funcionario_id: input.employeeId,
      Descricao: input.descricao,
    }));
    const result = await this.sql<{ id: string; funcionario_id: string; Descricao: string }[]>`
      insert into secullum."FuncionarioCentroCusto" ${
      this.sql(rows, "funcionario_id", "Descricao")
    }
      on conflict (funcionario_id, "Descricao") do update set
        "Descricao" = excluded."Descricao"
      returning id, funcionario_id, "Descricao"
    `;
    return result.map((row) => ({
      id: row.id,
      employeeId: row.funcionario_id,
      descricao: row.Descricao,
    }));
  }

  async deleteCostCentersByIds(ids: string[]): Promise<void> {
    if (!ids.length) return; // defensivo — nunca DELETE sem filtro.
    await this.sql`delete from secullum."FuncionarioCentroCusto" where id in ${this.sql(ids)}`;
  }

  // ---------------------------------------------------------------------------
  // ADR-011 Fase 3 (migration 20260813162000) — árvore completa de "Horario".
  // "HorariosOpcoes"/"HorarioExtras"/"HorarioDescanso"/"HorarioToleranciaEspecifica"
  // são 1:1 (UNIQUE em horario_id) -> upsert em lote, sem DELETE. As tabelas
  // *Item* e "HorarioFaixasExtras" não têm chave única de negócio -> DELETE
  // por id(s) do pai tocado(s) + INSERT puro do conjunto novo (nunca upsert).
  // ---------------------------------------------------------------------------

  async upsertScheduleOptions(inputs: UpsertHorariosOpcoesInput[]): Promise<void> {
    if (!inputs.length) return;
    const now = new Date().toISOString();
    const rows = inputs.map((input) => ({
      horario_id: input.horarioId,
      HorarioId: input.secullumHorarioId,
      ToleranciaArtigo58: input.toleranciaArtigo58,
      IgnorarLimiteMinimoCasoBatidaGerarExtrasSuperiorATolerancia:
        input.ignorarLimiteMinimoCasoBatidaGerarExtrasSuperiorATolerancia,
      IgnorarLimiteMinimoCasoBatidaGerarFaltasSuperiorATolerancia:
        input.ignorarLimiteMinimoCasoBatidaGerarFaltasSuperiorATolerancia,
      QualquerMinutoAdiantadoComoExtra: input.qualquerMinutoAdiantadoComoExtra,
      QualquerMinutoAtrasadoComoFalta: input.qualquerMinutoAtrasadoComoFalta,
      DescontarToleranciaDasHorasExtras: input.descontarToleranciaDasHorasExtras,
      DescontarToleranciaDasHorasFaltas: input.descontarToleranciaDasHorasFaltas,
      UsarToleranciaRefeicoes: input.usarToleranciaRefeicoes,
      ToleranciaRefeicoesMinutos: input.toleranciaRefeicoesMinutos,
      LimiteMinimoDeFaltasNoDiaMinutos: input.limiteMinimoDeFaltasNoDiaMinutos,
      LimiteMinimoDeExtrasNoDiaMinutos: input.limiteMinimoDeExtrasNoDiaMinutos,
      SubstituirBatidasAbaixoDasTolerancias: input.substituirBatidasAbaixoDasTolerancias,
      AlocarHorario24Horas: input.alocarHorario24Horas,
      AlocarBatidas: input.alocarBatidas,
      NaoDescontarFaltasDeNormais: input.naoDescontarFaltasDeNormais,
      PreencherFaltasQuandoDiaEstiverEmBranco: input.preencherFaltasQuandoDiaEstiverEmBranco,
      TipoPreencherQuandoDiaEstiverEmBranco: input.tipoPreencherQuandoDiaEstiverEmBranco,
      CalcularFaltasSomenteParaDiaInteiro: input.calcularFaltasSomenteParaDiaInteiro,
      ExibirColunaHorasRepousoFaltantesTrabalhoContinuo:
        input.exibirColunaHorasRepousoFaltantesTrabalhoContinuo,
      HorasRepousoConfiguracaoPadrao: input.horasRepousoConfiguracaoPadrao,
      HorasRepousoFaixas: input.horasRepousoFaixas,
      CompletarBatidasFaltantes: input.completarBatidasFaltantes,
      PermitirFolgasAutomaticas: input.permitirFolgasAutomaticas,
      QuantidadeFolgasAutomaticas: input.quantidadeFolgasAutomaticas,
      ColunasRefeicao: input.colunasRefeicao,
      SinalizarEmVermelhoAlmocosCurtos: input.sinalizarEmVermelhoAlmocosCurtos,
      NaoCalcularNenhumaHoraNoturna: input.naoCalcularNenhumaHoraNoturna,
      SepararHorasNoturnasDeHorasNormais: input.separarHorasNoturnasDeHorasNormais,
      IncluirIntervaloNoAdicionalNoturno: input.incluirIntervaloNoAdicionalNoturno,
      PeriodoEspecialAdicionalNoturnoInicio: input.periodoEspecialAdicionalNoturnoInicio,
      PeriodoEspecialAdicionalNoturnoFim: input.periodoEspecialAdicionalNoturnoFim,
      ConsiderarFeriadosComoHoraExtra: input.considerarFeriadosComoHoraExtra,
      UsarTempoMaisMenosCargaSuperior: input.usarTempoMaisMenosCargaSuperior,
      PercentualCargaUsarTempoMaisMenosMinutos: input.percentualCargaUsarTempoMaisMenosMinutos,
      DefinirCargaAutomaticamente: input.definirCargaAutomaticamente,
      Carga: input.carga,
      DesconsiderarNeutroQuandoHouverBatidasNoDia:
        input.desconsiderarNeutroQuandoHouverBatidasNoDia,
      UsarDataFechamentoEncerrarSemana: input.usarDataFechamentoEncerrarSemana,
      Compensacao: input.compensacao,
      CompensacaoIgnorarSabados: input.compensacaoIgnorarSabados,
      CompensacaoIgnorarDomingos: input.compensacaoIgnorarDomingos,
      CompensacaoIgnorarFeriados: input.compensacaoIgnorarFeriados,
      CompensacaoIgnorarFolgas: input.compensacaoIgnorarFolgas,
      CompensacaoMensalFechamento: input.compensacaoMensalFechamento,
      CompensacaoCalcularHorasComoNormaisCompatibilidadePontoOff:
        input.compensacaoCalcularHorasComoNormaisCompatibilidadePontoOff,
      CalcularNoturnasIndependenteCompensado: input.calcularNoturnasIndependenteCompensado,
      CalcularBatidasIntermediarias: input.calcularBatidasIntermediarias,
      NaoCalcularHorasFaltaBatidasIntermediarias:
        input.naoCalcularHorasFaltaBatidasIntermediarias,
      ListaHorasSobreAviso: input.listaHorasSobreAviso,
      CalcularHorasInItinere: input.calcularHorasInItinere,
      ListaHorasInItinere: input.listaHorasInItinere,
      SomarHorasInItinereNormais: input.somarHorasInItinereNormais,
      CalcularHorasInItinereIninterruptas: input.calcularHorasInItinereIninterruptas,
      sincronizado_em: now,
      atualizado_em: now,
    }));
    const columns = [
      "horario_id",
      "HorarioId",
      "ToleranciaArtigo58",
      "IgnorarLimiteMinimoCasoBatidaGerarExtrasSuperiorATolerancia",
      "IgnorarLimiteMinimoCasoBatidaGerarFaltasSuperiorATolerancia",
      "QualquerMinutoAdiantadoComoExtra",
      "QualquerMinutoAtrasadoComoFalta",
      "DescontarToleranciaDasHorasExtras",
      "DescontarToleranciaDasHorasFaltas",
      "UsarToleranciaRefeicoes",
      "ToleranciaRefeicoesMinutos",
      "LimiteMinimoDeFaltasNoDiaMinutos",
      "LimiteMinimoDeExtrasNoDiaMinutos",
      "SubstituirBatidasAbaixoDasTolerancias",
      "AlocarHorario24Horas",
      "AlocarBatidas",
      "NaoDescontarFaltasDeNormais",
      "PreencherFaltasQuandoDiaEstiverEmBranco",
      "TipoPreencherQuandoDiaEstiverEmBranco",
      "CalcularFaltasSomenteParaDiaInteiro",
      "ExibirColunaHorasRepousoFaltantesTrabalhoContinuo",
      "HorasRepousoConfiguracaoPadrao",
      "HorasRepousoFaixas",
      "CompletarBatidasFaltantes",
      "PermitirFolgasAutomaticas",
      "QuantidadeFolgasAutomaticas",
      "ColunasRefeicao",
      "SinalizarEmVermelhoAlmocosCurtos",
      "NaoCalcularNenhumaHoraNoturna",
      "SepararHorasNoturnasDeHorasNormais",
      "IncluirIntervaloNoAdicionalNoturno",
      "PeriodoEspecialAdicionalNoturnoInicio",
      "PeriodoEspecialAdicionalNoturnoFim",
      "ConsiderarFeriadosComoHoraExtra",
      "UsarTempoMaisMenosCargaSuperior",
      "PercentualCargaUsarTempoMaisMenosMinutos",
      "DefinirCargaAutomaticamente",
      "Carga",
      "DesconsiderarNeutroQuandoHouverBatidasNoDia",
      "UsarDataFechamentoEncerrarSemana",
      "Compensacao",
      "CompensacaoIgnorarSabados",
      "CompensacaoIgnorarDomingos",
      "CompensacaoIgnorarFeriados",
      "CompensacaoIgnorarFolgas",
      "CompensacaoMensalFechamento",
      "CompensacaoCalcularHorasComoNormaisCompatibilidadePontoOff",
      "CalcularNoturnasIndependenteCompensado",
      "CalcularBatidasIntermediarias",
      "NaoCalcularHorasFaltaBatidasIntermediarias",
      "ListaHorasSobreAviso",
      "CalcularHorasInItinere",
      "ListaHorasInItinere",
      "SomarHorasInItinereNormais",
      "CalcularHorasInItinereIninterruptas",
      "sincronizado_em",
      "atualizado_em",
    ];
    await this.sql`
      insert into secullum."HorariosOpcoes" ${this.sql(rows, ...columns)}
      on conflict (horario_id) do update set
        "HorarioId" = excluded."HorarioId",
        "ToleranciaArtigo58" = excluded."ToleranciaArtigo58",
        "IgnorarLimiteMinimoCasoBatidaGerarExtrasSuperiorATolerancia" = excluded."IgnorarLimiteMinimoCasoBatidaGerarExtrasSuperiorATolerancia",
        "IgnorarLimiteMinimoCasoBatidaGerarFaltasSuperiorATolerancia" = excluded."IgnorarLimiteMinimoCasoBatidaGerarFaltasSuperiorATolerancia",
        "QualquerMinutoAdiantadoComoExtra" = excluded."QualquerMinutoAdiantadoComoExtra",
        "QualquerMinutoAtrasadoComoFalta" = excluded."QualquerMinutoAtrasadoComoFalta",
        "DescontarToleranciaDasHorasExtras" = excluded."DescontarToleranciaDasHorasExtras",
        "DescontarToleranciaDasHorasFaltas" = excluded."DescontarToleranciaDasHorasFaltas",
        "UsarToleranciaRefeicoes" = excluded."UsarToleranciaRefeicoes",
        "ToleranciaRefeicoesMinutos" = excluded."ToleranciaRefeicoesMinutos",
        "LimiteMinimoDeFaltasNoDiaMinutos" = excluded."LimiteMinimoDeFaltasNoDiaMinutos",
        "LimiteMinimoDeExtrasNoDiaMinutos" = excluded."LimiteMinimoDeExtrasNoDiaMinutos",
        "SubstituirBatidasAbaixoDasTolerancias" = excluded."SubstituirBatidasAbaixoDasTolerancias",
        "AlocarHorario24Horas" = excluded."AlocarHorario24Horas",
        "AlocarBatidas" = excluded."AlocarBatidas",
        "NaoDescontarFaltasDeNormais" = excluded."NaoDescontarFaltasDeNormais",
        "PreencherFaltasQuandoDiaEstiverEmBranco" = excluded."PreencherFaltasQuandoDiaEstiverEmBranco",
        "TipoPreencherQuandoDiaEstiverEmBranco" = excluded."TipoPreencherQuandoDiaEstiverEmBranco",
        "CalcularFaltasSomenteParaDiaInteiro" = excluded."CalcularFaltasSomenteParaDiaInteiro",
        "ExibirColunaHorasRepousoFaltantesTrabalhoContinuo" = excluded."ExibirColunaHorasRepousoFaltantesTrabalhoContinuo",
        "HorasRepousoConfiguracaoPadrao" = excluded."HorasRepousoConfiguracaoPadrao",
        "HorasRepousoFaixas" = excluded."HorasRepousoFaixas",
        "CompletarBatidasFaltantes" = excluded."CompletarBatidasFaltantes",
        "PermitirFolgasAutomaticas" = excluded."PermitirFolgasAutomaticas",
        "QuantidadeFolgasAutomaticas" = excluded."QuantidadeFolgasAutomaticas",
        "ColunasRefeicao" = excluded."ColunasRefeicao",
        "SinalizarEmVermelhoAlmocosCurtos" = excluded."SinalizarEmVermelhoAlmocosCurtos",
        "NaoCalcularNenhumaHoraNoturna" = excluded."NaoCalcularNenhumaHoraNoturna",
        "SepararHorasNoturnasDeHorasNormais" = excluded."SepararHorasNoturnasDeHorasNormais",
        "IncluirIntervaloNoAdicionalNoturno" = excluded."IncluirIntervaloNoAdicionalNoturno",
        "PeriodoEspecialAdicionalNoturnoInicio" = excluded."PeriodoEspecialAdicionalNoturnoInicio",
        "PeriodoEspecialAdicionalNoturnoFim" = excluded."PeriodoEspecialAdicionalNoturnoFim",
        "ConsiderarFeriadosComoHoraExtra" = excluded."ConsiderarFeriadosComoHoraExtra",
        "UsarTempoMaisMenosCargaSuperior" = excluded."UsarTempoMaisMenosCargaSuperior",
        "PercentualCargaUsarTempoMaisMenosMinutos" = excluded."PercentualCargaUsarTempoMaisMenosMinutos",
        "DefinirCargaAutomaticamente" = excluded."DefinirCargaAutomaticamente",
        "Carga" = excluded."Carga",
        "DesconsiderarNeutroQuandoHouverBatidasNoDia" = excluded."DesconsiderarNeutroQuandoHouverBatidasNoDia",
        "UsarDataFechamentoEncerrarSemana" = excluded."UsarDataFechamentoEncerrarSemana",
        "Compensacao" = excluded."Compensacao",
        "CompensacaoIgnorarSabados" = excluded."CompensacaoIgnorarSabados",
        "CompensacaoIgnorarDomingos" = excluded."CompensacaoIgnorarDomingos",
        "CompensacaoIgnorarFeriados" = excluded."CompensacaoIgnorarFeriados",
        "CompensacaoIgnorarFolgas" = excluded."CompensacaoIgnorarFolgas",
        "CompensacaoMensalFechamento" = excluded."CompensacaoMensalFechamento",
        "CompensacaoCalcularHorasComoNormaisCompatibilidadePontoOff" = excluded."CompensacaoCalcularHorasComoNormaisCompatibilidadePontoOff",
        "CalcularNoturnasIndependenteCompensado" = excluded."CalcularNoturnasIndependenteCompensado",
        "CalcularBatidasIntermediarias" = excluded."CalcularBatidasIntermediarias",
        "NaoCalcularHorasFaltaBatidasIntermediarias" = excluded."NaoCalcularHorasFaltaBatidasIntermediarias",
        "ListaHorasSobreAviso" = excluded."ListaHorasSobreAviso",
        "CalcularHorasInItinere" = excluded."CalcularHorasInItinere",
        "ListaHorasInItinere" = excluded."ListaHorasInItinere",
        "SomarHorasInItinereNormais" = excluded."SomarHorasInItinereNormais",
        "CalcularHorasInItinereIninterruptas" = excluded."CalcularHorasInItinereIninterruptas",
        sincronizado_em = excluded.sincronizado_em,
        atualizado_em = excluded.atualizado_em
    `;
  }

  async upsertScheduleExtras(inputs: UpsertHorarioExtrasInput[]): Promise<void> {
    if (!inputs.length) return;
    const now = new Date().toISOString();
    const rows = inputs.map((input) => ({
      horario_id: input.horarioId,
      HorarioId: input.secullumHorarioId,
      AgruparExtras: input.agruparExtras,
      SomenteGrupoExtras: input.somenteGrupoExtras,
      DescontarFaltasExtras: input.descontarFaltasExtras,
      DescontarFaltasExtrasNoturnas: input.descontarFaltasExtrasNoturnas,
      DescontarIgnorarUteis: input.descontarIgnorarUteis,
      DescontarIgnorarSabados: input.descontarIgnorarSabados,
      DescontarIgnorarDomingos: input.descontarIgnorarDomingos,
      DescontarIgnorarFeriados: input.descontarIgnorarFeriados,
      DescontarIgnorarFolgas: input.descontarIgnorarFolgas,
      DescontarIgnorarDiaEspecial: input.descontarIgnorarDiaEspecial,
      UsarInterjornada: input.usarInterjornada,
      Interjornada: input.interjornada,
      InterjornadaSeparada: input.interjornadaSeparada,
      InterjornadaSeparadaBancoHoras: input.interjornadaSeparadaBancoHoras,
      SepararExtrasNoturnasDeExtrasNormais: input.separarExtrasNoturnasDeExtrasNormais,
      SepararExtrasIntervalosDeExtrasNormais: input.separarExtrasIntervalosDeExtrasNormais,
      SepararSomatoriaAposMeiaNoite: input.separarSomatoriaAposMeiaNoite,
      MultiplicarExtrasPeloPercentual: input.multiplicarExtrasPeloPercentual,
      HabilitarMultiplicadorFaixaBancoHoras: input.habilitarMultiplicadorFaixaBancoHoras,
      MultiplicarSomenteSaldoPositivo: input.multiplicarSomenteSaldoPositivo,
      NaoDividirExtrasEmFeriados: input.naoDividirExtrasEmFeriados,
      NaoDividirExtrasEmDomingos: input.naoDividirExtrasEmDomingos,
      DividirJornadaQuandoHouverFolga: input.dividirJornadaQuandoHouverFolga,
      NaoDividirJornadaEmFeriados: input.naoDividirJornadaEmFeriados,
      NaoDividirJornadaEmFolgas: input.naoDividirJornadaEmFolgas,
      ApenasDividirJornadaFeriadoFolgaDiaSeguinte:
        input.apenasDividirJornadaFeriadoFolgaDiaSeguinte,
      NaoReiniciarDivisoesExtrasDiurnasNoturnas: input.naoReiniciarDivisoesExtrasDiurnasNoturnas,
      ControleHorasExtrasAutorizadas: input.controleHorasExtrasAutorizadas,
      QuantidadeExtrasAutorizadas: input.quantidadeExtrasAutorizadas,
      Acumulo: input.acumulo,
      sincronizado_em: now,
      atualizado_em: now,
    }));
    const columns = [
      "horario_id",
      "HorarioId",
      "AgruparExtras",
      "SomenteGrupoExtras",
      "DescontarFaltasExtras",
      "DescontarFaltasExtrasNoturnas",
      "DescontarIgnorarUteis",
      "DescontarIgnorarSabados",
      "DescontarIgnorarDomingos",
      "DescontarIgnorarFeriados",
      "DescontarIgnorarFolgas",
      "DescontarIgnorarDiaEspecial",
      "UsarInterjornada",
      "Interjornada",
      "InterjornadaSeparada",
      "InterjornadaSeparadaBancoHoras",
      "SepararExtrasNoturnasDeExtrasNormais",
      "SepararExtrasIntervalosDeExtrasNormais",
      "SepararSomatoriaAposMeiaNoite",
      "MultiplicarExtrasPeloPercentual",
      "HabilitarMultiplicadorFaixaBancoHoras",
      "MultiplicarSomenteSaldoPositivo",
      "NaoDividirExtrasEmFeriados",
      "NaoDividirExtrasEmDomingos",
      "DividirJornadaQuandoHouverFolga",
      "NaoDividirJornadaEmFeriados",
      "NaoDividirJornadaEmFolgas",
      "ApenasDividirJornadaFeriadoFolgaDiaSeguinte",
      "NaoReiniciarDivisoesExtrasDiurnasNoturnas",
      "ControleHorasExtrasAutorizadas",
      "QuantidadeExtrasAutorizadas",
      "Acumulo",
      "sincronizado_em",
      "atualizado_em",
    ];
    await this.sql`
      insert into secullum."HorarioExtras" ${this.sql(rows, ...columns)}
      on conflict (horario_id) do update set
        "HorarioId" = excluded."HorarioId",
        "AgruparExtras" = excluded."AgruparExtras",
        "SomenteGrupoExtras" = excluded."SomenteGrupoExtras",
        "DescontarFaltasExtras" = excluded."DescontarFaltasExtras",
        "DescontarFaltasExtrasNoturnas" = excluded."DescontarFaltasExtrasNoturnas",
        "DescontarIgnorarUteis" = excluded."DescontarIgnorarUteis",
        "DescontarIgnorarSabados" = excluded."DescontarIgnorarSabados",
        "DescontarIgnorarDomingos" = excluded."DescontarIgnorarDomingos",
        "DescontarIgnorarFeriados" = excluded."DescontarIgnorarFeriados",
        "DescontarIgnorarFolgas" = excluded."DescontarIgnorarFolgas",
        "DescontarIgnorarDiaEspecial" = excluded."DescontarIgnorarDiaEspecial",
        "UsarInterjornada" = excluded."UsarInterjornada",
        "Interjornada" = excluded."Interjornada",
        "InterjornadaSeparada" = excluded."InterjornadaSeparada",
        "InterjornadaSeparadaBancoHoras" = excluded."InterjornadaSeparadaBancoHoras",
        "SepararExtrasNoturnasDeExtrasNormais" = excluded."SepararExtrasNoturnasDeExtrasNormais",
        "SepararExtrasIntervalosDeExtrasNormais" = excluded."SepararExtrasIntervalosDeExtrasNormais",
        "SepararSomatoriaAposMeiaNoite" = excluded."SepararSomatoriaAposMeiaNoite",
        "MultiplicarExtrasPeloPercentual" = excluded."MultiplicarExtrasPeloPercentual",
        "HabilitarMultiplicadorFaixaBancoHoras" = excluded."HabilitarMultiplicadorFaixaBancoHoras",
        "MultiplicarSomenteSaldoPositivo" = excluded."MultiplicarSomenteSaldoPositivo",
        "NaoDividirExtrasEmFeriados" = excluded."NaoDividirExtrasEmFeriados",
        "NaoDividirExtrasEmDomingos" = excluded."NaoDividirExtrasEmDomingos",
        "DividirJornadaQuandoHouverFolga" = excluded."DividirJornadaQuandoHouverFolga",
        "NaoDividirJornadaEmFeriados" = excluded."NaoDividirJornadaEmFeriados",
        "NaoDividirJornadaEmFolgas" = excluded."NaoDividirJornadaEmFolgas",
        "ApenasDividirJornadaFeriadoFolgaDiaSeguinte" = excluded."ApenasDividirJornadaFeriadoFolgaDiaSeguinte",
        "NaoReiniciarDivisoesExtrasDiurnasNoturnas" = excluded."NaoReiniciarDivisoesExtrasDiurnasNoturnas",
        "ControleHorasExtrasAutorizadas" = excluded."ControleHorasExtrasAutorizadas",
        "QuantidadeExtrasAutorizadas" = excluded."QuantidadeExtrasAutorizadas",
        "Acumulo" = excluded."Acumulo",
        sincronizado_em = excluded.sincronizado_em,
        atualizado_em = excluded.atualizado_em
    `;
  }

  async upsertScheduleRests(inputs: UpsertHorarioDescansoInput[]): Promise<HorarioDescansoRow[]> {
    if (!inputs.length) return [];
    const now = new Date().toISOString();
    const rows = inputs.map((input) => ({
      horario_id: input.horarioId,
      HorarioId: input.secullumHorarioId,
      Tipo: input.tipo,
      ValorDescanso: input.valorDescanso,
      LimiteHorasFaltas: input.limiteHorasFaltas,
      IncluirFeriado: input.incluirFeriado,
      FeriadoDomingoApenasUmDescanso: input.feriadoDomingoApenasUmDescanso,
      DescontarFeriadosCasoFaltas: input.descontarFeriadosCasoFaltas,
      NaoDescontarAntesAdmissao: input.naoDescontarAntesAdmissao,
      NaoDescontarDuranteAfastamento: input.naoDescontarDuranteAfastamento,
      sincronizado_em: now,
      atualizado_em: now,
    }));
    const result = await this.sql<{ id: string; horario_id: string }[]>`
      insert into secullum."HorarioDescanso" ${
      this.sql(
        rows,
        "horario_id",
        "HorarioId",
        "Tipo",
        "ValorDescanso",
        "LimiteHorasFaltas",
        "IncluirFeriado",
        "FeriadoDomingoApenasUmDescanso",
        "DescontarFeriadosCasoFaltas",
        "NaoDescontarAntesAdmissao",
        "NaoDescontarDuranteAfastamento",
        "sincronizado_em",
        "atualizado_em",
      )
    }
      on conflict (horario_id) do update set
        "HorarioId" = excluded."HorarioId",
        "Tipo" = excluded."Tipo",
        "ValorDescanso" = excluded."ValorDescanso",
        "LimiteHorasFaltas" = excluded."LimiteHorasFaltas",
        "IncluirFeriado" = excluded."IncluirFeriado",
        "FeriadoDomingoApenasUmDescanso" = excluded."FeriadoDomingoApenasUmDescanso",
        "DescontarFeriadosCasoFaltas" = excluded."DescontarFeriadosCasoFaltas",
        "NaoDescontarAntesAdmissao" = excluded."NaoDescontarAntesAdmissao",
        "NaoDescontarDuranteAfastamento" = excluded."NaoDescontarDuranteAfastamento",
        sincronizado_em = excluded.sincronizado_em,
        atualizado_em = excluded.atualizado_em
      returning id, horario_id
    `;
    return result.map((row) => ({ id: row.id, horarioId: row.horario_id }));
  }

  async deleteScheduleRestRangesByParentIds(horarioDescansoIds: string[]): Promise<void> {
    if (!horarioDescansoIds.length) return; // defensivo — nunca DELETE sem filtro.
    await this.sql`
      delete from secullum."HorarioDescansoFaixaItem"
      where horario_descanso_id in ${this.sql(horarioDescansoIds)}
    `;
  }

  async insertScheduleRestRanges(inputs: InsertHorarioDescansoFaixaItemInput[]): Promise<void> {
    if (!inputs.length) return;
    const rows = inputs.map((input) => ({
      horario_descanso_id: input.horarioDescansoId,
      Ordem: input.ordem,
      Limite: input.limite,
      Desconto: input.desconto,
    }));
    await this.sql`
      insert into secullum."HorarioDescansoFaixaItem" ${
      this.sql(rows, "horario_descanso_id", "Ordem", "Limite", "Desconto")
    }
    `;
  }

  async deleteScheduleExtraRangeGroupsByHorarioIds(horarioIds: string[]): Promise<void> {
    if (!horarioIds.length) return; // defensivo — nunca DELETE sem filtro.
    // ON DELETE CASCADE em "HorarioFaixasExtrasItem" cuida dos itens.
    await this.sql`
      delete from secullum."HorarioFaixasExtras" where horario_id in ${this.sql(horarioIds)}
    `;
  }

  async insertScheduleExtraRangeGroups(
    inputs: InsertHorarioFaixasExtrasInput[],
  ): Promise<HorarioFaixasExtrasRow[]> {
    if (!inputs.length) return [];
    const rows = inputs.map((input) => ({
      horario_id: input.horarioId,
      HorarioId: input.secullumHorarioId,
      DiaSemana: input.diaSemana,
      Controle: input.controle,
      DiaEspecial: input.diaEspecial,
    }));
    const result = await this.sql<
      { id: string; horario_id: string; DiaSemana: number | null }[]
    >`
      insert into secullum."HorarioFaixasExtras" ${
      this.sql(rows, "horario_id", "HorarioId", "DiaSemana", "Controle", "DiaEspecial")
    }
      returning id, horario_id, "DiaSemana"
    `;
    return result.map((row) => ({
      id: row.id,
      horarioId: row.horario_id,
      diaSemana: row.DiaSemana ?? null,
    }));
  }

  async insertScheduleExtraRangeGroupItems(
    inputs: InsertHorarioFaixasExtrasItemInput[],
  ): Promise<void> {
    if (!inputs.length) return;
    const rows = inputs.map((input) => ({
      horario_faixas_extras_id: input.horarioFaixasExtrasId,
      Ordem: input.ordem,
      Horas: input.horas,
      Coluna: input.coluna,
    }));
    await this.sql`
      insert into secullum."HorarioFaixasExtrasItem" ${
      this.sql(rows, "horario_faixas_extras_id", "Ordem", "Horas", "Coluna")
    }
    `;
  }

  async upsertScheduleSpecificTolerances(
    inputs: UpsertHorarioToleranciaEspecificaInput[],
  ): Promise<HorarioToleranciaEspecificaRow[]> {
    if (!inputs.length) return [];
    const now = new Date().toISOString();
    const rows = inputs.map((input) => ({
      horario_id: input.horarioId,
      UsaToleranciaEspecifica: input.usaToleranciaEspecifica,
      sincronizado_em: now,
      atualizado_em: now,
    }));
    const result = await this.sql<{ id: string; horario_id: string }[]>`
      insert into secullum."HorarioToleranciaEspecifica" ${
      this.sql(rows, "horario_id", "UsaToleranciaEspecifica", "sincronizado_em", "atualizado_em")
    }
      on conflict (horario_id) do update set
        "UsaToleranciaEspecifica" = excluded."UsaToleranciaEspecifica",
        sincronizado_em = excluded.sincronizado_em,
        atualizado_em = excluded.atualizado_em
      returning id, horario_id
    `;
    return result.map((row) => ({ id: row.id, horarioId: row.horario_id }));
  }

  async deleteScheduleSpecificToleranceItemsByParentIds(
    horarioToleranciaEspecificaIds: string[],
  ): Promise<void> {
    if (!horarioToleranciaEspecificaIds.length) return; // defensivo — nunca DELETE sem filtro.
    await this.sql`
      delete from secullum."HorarioToleranciaEspecificaItem"
      where horario_tolerancia_especifica_id in ${this.sql(horarioToleranciaEspecificaIds)}
    `;
  }

  async insertScheduleSpecificToleranceItems(
    inputs: InsertHorarioToleranciaEspecificaItemInput[],
  ): Promise<void> {
    if (!inputs.length) return;
    const rows = inputs.map((input) => ({
      horario_tolerancia_especifica_id: input.horarioToleranciaEspecificaId,
      HorarioId: input.secullumHorarioId,
      DiaSemana: input.diaSemana,
      Entrada1De: input.entrada1De,
      Entrada1Ate: input.entrada1Ate,
      Saida1De: input.saida1De,
      Saida1Ate: input.saida1Ate,
      Entrada2De: input.entrada2De,
      Entrada2Ate: input.entrada2Ate,
      Saida2De: input.saida2De,
      Saida2Ate: input.saida2Ate,
      Entrada3De: input.entrada3De,
      Entrada3Ate: input.entrada3Ate,
      Saida3De: input.saida3De,
      Saida3Ate: input.saida3Ate,
      Entrada4De: input.entrada4De,
      Entrada4Ate: input.entrada4Ate,
      Saida4De: input.saida4De,
      Saida4Ate: input.saida4Ate,
      Entrada5De: input.entrada5De,
      Entrada5Ate: input.entrada5Ate,
      Saida5De: input.saida5De,
      Saida5Ate: input.saida5Ate,
    }));
    await this.sql`
      insert into secullum."HorarioToleranciaEspecificaItem" ${
      this.sql(
        rows,
        "horario_tolerancia_especifica_id",
        "HorarioId",
        "DiaSemana",
        "Entrada1De",
        "Entrada1Ate",
        "Saida1De",
        "Saida1Ate",
        "Entrada2De",
        "Entrada2Ate",
        "Saida2De",
        "Saida2Ate",
        "Entrada3De",
        "Entrada3Ate",
        "Saida3De",
        "Saida3Ate",
        "Entrada4De",
        "Entrada4Ate",
        "Saida4De",
        "Saida4Ate",
        "Entrada5De",
        "Entrada5Ate",
        "Saida5De",
        "Saida5Ate",
      )
    }
    `;
  }
}

/**
 * Cria o repositório a partir das variáveis de ambiente padrão do projeto.
 * Uso exclusivo de Edge Functions — `DATABASE_URL` nunca deve chegar ao
 * painel/frontend (docs/06-seguranca-lgpd.md).
 */
export function createSupabaseSyncRepositoryFromEnv(): SupabaseSyncRepository {
  return new SupabaseSyncRepository();
}
