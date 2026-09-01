-- ==========================================================================
-- Schema do projeto Supabase nklobmlxyidqxarzisph, reconstruído do catálogo.
-- RECORTE: apenas o(s) schema(s) secullum.
-- GERADO por scripts/introspeccao_nuvem.py — não editar à mão.
--
-- Só catálogo foi lido: nenhuma linha de dado de cliente entrou aqui.
-- Não é backup. É o mapa contra o qual o schema deste repositório é conferido.
-- ==========================================================================

-- Histórico de migration aplicado neste projeto:
--   20260811120000  init_sync_cursor
--   20260812130000  cadastro_sync_schema
--   20260812131000  sync_cadastro_cron
--   20260812140000  fix_work_schedule_day_horario_dia_id_uniqueness
--   20260813120000  status_history_company_employee
--   20260813150000  employee_absence
--   20260813160000  rename_schema_secullum
--   20260813161000  cadastro_captura_completa
--   20260813162000  horario_arvore_completa
--   20260813163000  batidas
--   20260813164000  sync_batidas_cron
--   20260815100000  00_blindagem_imediata
--   20260815100100  01_fundacao_schemas
--   20260815100200  02_tenancy_rls
--   20260815100300  03_isolar_secullum
--   20260815100400  04_organizacao_colaborador
--   20260815100500  05_ponto_desvio
--   20260815100600  06_alertas
--   20260815100700  07_folha_custos
--   20260815100800  08_documentos_saude_acordos
--   20260815100900  09_integracoes_auditoria
--   20260815101000  10_views_publicas
--   20260815101100  11_performance
--   20260815101150  
--   20260815101200  
--   20260815101300  
--   20260815101400  
--   20260822160000  
--   20260824140000  
--   20260824170000  
--   20260824190000  
--   20260825120000  
--   20260825140000  
--   20260825160000  
--   20260825180000  
--   20260825200000  
--   20260825220000  
--   20260826120000  
--   20260826140000  
--   20260826160000  
--   20260827180000  
--   20260828120000  
--   20260828160000  
--   20260828180000  
--   20260828200000  
--   20260831230000  33_ingestion_touch_trigger

create schema if not exists secullum;


create table if not exists secullum."Batida" (
  id uuid default gen_random_uuid() not null,
  "BatidaId" integer,
  funcionario_id uuid not null,
  "FuncionarioId" integer,
  "Data" date not null,
  "Observacoes" text,
  "Ajuste" text,
  "Abono2" text,
  "Abono3" text,
  "Abono4" text,
  "Compensado" boolean default false not null,
  "AlmocoLivre" boolean default false not null,
  "Neutro" boolean default false not null,
  "NBanco" boolean default false not null,
  "Folga" boolean default false not null,
  "Refeicao" boolean default false not null,
  status_dia_rotulo text,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."Batida" enable row level security;
alter table secullum."Batida" force row level security;
comment on table secullum."Batida" is 'Registro-dia de ponto: UM item de GET /Batidas = um par (funcionario x data) com ate 5 pares Entrada/Saida em COLUNAS. NAO e uma batida individual — essa e batida_marcacao. Ver ADR-007 e ADR-011.';

create table if not exists secullum."BatidaFonteDados" (
  id uuid default gen_random_uuid() not null,
  batida_marcacao_id uuid not null,
  batida_id uuid not null,
  "FonteDadosId" bigint,
  "Nsr" text,
  "Hora" time without time zone,
  "Data" date,
  "DataInclusao" timestamp with time zone,
  "Tipo" smallint,
  "Origem" smallint,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."BatidaFonteDados" enable row level security;
alter table secullum."BatidaFonteDados" force row level security;
comment on table secullum."BatidaFonteDados" is 'Objeto `FonteDados` aninhado em cada coluna de /Batidas — ate 10 por registro-dia (FonteDadosEntrada1..5 / FonteDadosSaida1..5). Nome composto: o prefixo "Batida" e NOSSO (agrupamento na listagem de tabelas); "FonteDados" e o tipo literal do Secullum, e cada linha E um desses objetos. 1:1 OPCIONAL com batida_marcacao: existe coluna preenchida SEM FonteDados (buraco conhecido, ADR-007).';

create table if not exists secullum."Cidade" (
  id uuid default gen_random_uuid() not null,
  "CidadeId" integer,
  "Descricao" text not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."Cidade" enable row level security;
alter table secullum."Cidade" force row level security;
comment on table secullum."Cidade" is 'Cidade — no aninhado { Id, Descricao } em Funcionario e em Empresa. Forma confirmada em 2026-08-13. Ver ADR-011.';

create table if not exists secullum."Departamento" (
  id uuid default gen_random_uuid() not null,
  empresa_id uuid not null,
  "DepartamentoId" integer not null,
  "Descricao" text not null,
  ativo boolean default true not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  "Nfolha" text,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."Departamento" enable row level security;
alter table secullum."Departamento" force row level security;
comment on table secullum."Departamento" is 'Departamento = unidade de estacionamento. Espelha o no `Funcionario.Departamento { Id, Descricao, Nfolha }`; a rota standalone GET /Departamentos NAO e chamada. Ver ADR-006 e ADR-008.';

create table if not exists secullum."Empresa" (
  id uuid default gen_random_uuid() not null,
  "Documento" text not null,
  "Nome" text not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  "EmpresaId" integer,
  "Desativada" boolean,
  "Inscricao" text,
  "Endereco" text,
  "Bairro" text,
  cidade_id uuid,
  "CidadeId" integer,
  "Cep" text,
  "Uf" text,
  "Pais" text,
  "Telefone" text,
  "Fax" text,
  "Cei" text,
  "NfolhaEmpresa" text,
  "Logotipo" text,
  "PossuiLogo" boolean,
  "ResponsavelNome" text,
  "ResponsavelCargo" text,
  "ResponsavelEmail" text,
  "TipoDocumento" smallint,
  "UtilizaRepC" boolean,
  "UtilizaRepA" boolean,
  "UtilizaRepP" boolean,
  "UsaFechamentoDoPontoEspecifico" boolean,
  "FechamentoPonto" smallint,
  "DiaFechamentoPonto" smallint,
  "EmitiuAtestadoTecnico" boolean,
  ativo boolean not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."Empresa" enable row level security;
alter table secullum."Empresa" force row level security;
comment on table secullum."Empresa" is 'Empresa (agrupador) — espelha o no `Funcionario.Empresa` aninhado em /Funcionarios. ⚠️ ATENCAO AO ALCANCE REAL DOS CAMPOS: o no aninhado confirmado traz { Id, Nome, Documento, Desativada, ... }. As demais colunas vem do CADASTRO DE EMPRESAS do manual (rota GET /Empresas, que este projeto NAO chama) e podem permanecer NULAS para sempre. Elas existem porque o Owner pediu captura completa (ADR-011); nenhuma delas tem consumidor de produto hoje. Ver ADR-006, ADR-011 e ADR-012.';

create table if not exists secullum."Estrutura" (
  id uuid default gen_random_uuid() not null,
  "EstruturaId" integer not null,
  "EstruturaPaiId" integer,
  "Descricao" text not null,
  email text,
  email_origem text default 'manual'::text not null,
  whatsapp text,
  canais_notificacao text[] default '{}'::text[] not null,
  ativo boolean default true not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."Estrutura" enable row level security;
alter table secullum."Estrutura" force row level security;
comment on table secullum."Estrutura" is '⚠️ LEIA O CABECALHO DA SECAO 6 DE 20260813160000_rename_schema_secullum.sql ANTES DE MEXER AQUI. Esta tabela espelha o OBJETO ANINHADO `Funcionario.Estrutura` de /Funcionarios — NAO a rota standalone GET /Estruturas, que foi DESCARTADA pelo ADR-006 e nao e chamada em nenhum fluxo. Papel de negocio: e o GESTOR responsavel pelo(s) departamento(s); "Descricao" e o NOME dele. Origem hibrida: "Descricao"/"EstruturaPaiId" vem do Secullum; email vem por match de nome dentro do proprio /Funcionarios (com protecao via email_origem); whatsapp e canais_notificacao sao SEMPRE cadastro manual do Owner. ⚠️ NAO confundir com "Empresa"."ResponsavelNome" (responsavel LEGAL da empresa, outra pessoa). Ver docs/03-integracao-secullum.md ("Resolucao do gestor").';

create table if not exists secullum."Funcao" (
  id uuid default gen_random_uuid() not null,
  "FuncaoId" integer,
  "Descricao" text not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."Funcao" enable row level security;
alter table secullum."Funcao" force row level security;
comment on table secullum."Funcao" is 'Funcao/cargo do funcionario. Populada a partir do no aninhado em /Funcionarios — a rota standalone GET /Funcoes NAO e chamada (escopo de 5 endpoints, docs/03-integracao-secullum.md).';

create table if not exists secullum."Funcionario" (
  id uuid default gen_random_uuid() not null,
  departamento_id uuid not null,
  empresa_id uuid not null,
  "FuncionarioId" integer not null,
  "Cpf" text,
  "NumeroPis" text,
  "Nome" text not null,
  horario_id uuid,
  ativo boolean default true not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  "Admissao" date,
  "Demissao" date,
  afastado_hoje boolean default false not null,
  afastamento_atual_id uuid,
  "NumeroFolha" text,
  "NumeroIdentificador" text,
  "NumeroProvisorio" text,
  "Carteira" text,
  "CodigoHolerite" text,
  "Observacao" text,
  "Endereco" text,
  "Bairro" text,
  cidade_id uuid,
  "CidadeId" integer,
  "Uf" text,
  "Cep" text,
  "Telefone" text,
  "Celular" text,
  "Email" text,
  "Rg" text,
  "ExpedicaoRg" date,
  "Ssp" text,
  "Mae" text,
  "Pai" text,
  "Nascimento" date,
  "Masculino" boolean,
  "Nacionalidade" text,
  "Naturalidade" text,
  funcao_id uuid,
  "FuncaoId" integer,
  "EmpresaId" integer,
  "DepartamentoId" integer,
  "HorarioId" integer,
  "EstruturaId" integer,
  "NaoVerificarDigital" boolean,
  "Master" boolean,
  "PossuiFoto" boolean,
  "Invisivel" boolean,
  "PeriodoEncerrado" text,
  "DesconsiderarPerimetrosGlobais" boolean,
  "AceitouTermosLgpdApp" boolean,
  "DataUltimoEnvio" timestamp with time zone,
  "DataUltimoLogin" timestamp with time zone,
  "DataAlteracao" timestamp with time zone,
  "EscolaridadeId" integer,
  "Filtro1Id" integer,
  "Filtro2Id" integer,
  "MotivoDemissaoId" integer,
  "NivelPermissaoId" integer,
  "PerfilId" integer,
  "PerfilFuncionarioId" integer,
  "BancoHorasId" integer,
  "HorarioAlternativo2Id" integer,
  "HorarioAlternativo3Id" integer,
  "HorarioAlternativo4Id" integer,
  "ConfigEspecificaInclusaoManualPonto" boolean,
  "ConfigEspecificaInclusaoManualPontoFusoHorarioId" integer,
  "ConfigEspecificaDesativarVerificacaoLocalFicticio" boolean,
  "ConfigEspecificaInclusaoPontoSemLocalizacao" boolean,
  "ConfigEspecificaInclusaoPontoOffline" boolean,
  "ConfigEspecificaCapturaDeFotoNoMomentoDaInclusao" boolean,
  "BloquearRegistroPontoTeclado" boolean,
  "PermiteInclusaoPontoManual" boolean,
  "PermiteInclusaoDispositivosAutorizados" boolean,
  "DesabilitarAssinaturaEletronica" boolean,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."Funcionario" enable row level security;
alter table secullum."Funcionario" force row level security;
comment on table secullum."Funcionario" is 'Funcionario. ⚠️ A partir de 2026-08-13 (ADR-011) esta tabela deixou de ser um "cache minimo" e passa a guardar TODO o cadastro devolvido por /Funcionarios, incluindo PII sensivel (RG, endereco, telefone, celular, e-mail, filiacao, nascimento). A minimizacao anterior foi REVERTIDA por decisao expressa do Owner. A base legal formal para essa retencao continua PENDENTE — ver docs/06-seguranca-lgpd.md.';

create table if not exists secullum."FuncionarioAfastamento" (
  id uuid default gen_random_uuid() not null,
  funcionario_id uuid not null,
  "AfastamentoId" integer not null,
  "Inicio" date not null,
  "Fim" date not null,
  "JustificativaNome" text,
  "DataInclusao" timestamp with time zone,
  correlacionado_por text default 'pis'::text not null,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."FuncionarioAfastamento" enable row level security;
alter table secullum."FuncionarioAfastamento" force row level security;
comment on table secullum."FuncionarioAfastamento" is 'Periodos (JANELAS) de afastamento/ferias — fonte: GET /IntegracaoExterna/FuncionariosAfastamentos. Nome escolhido a partir do nome da rota (o manual nao nomeia um tipo para o item) — ver secao 10 da migration 20260813160000. NAO confundir com funcionario_evento_status (transicoes de vinculo): o funcionario continua ativo = true durante ferias. Tabela MUTAVEL (upsert + DELETE de convergencia), ao contrario das tabelas *_evento_status, que sao append-only. Ver ADR-010.';

create table if not exists secullum."FuncionarioCentroCusto" (
  id uuid default gen_random_uuid() not null,
  funcionario_id uuid not null,
  "Descricao" text not null,
  criado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."FuncionarioCentroCusto" enable row level security;
alter table secullum."FuncionarioCentroCusto" force row level security;
comment on table secullum."FuncionarioCentroCusto" is 'Centros de custo do funcionario (`ListaCentroDeCustos`, array de { Descricao } em /Funcionarios). ON DELETE CASCADE sustenta o expurgo por titular (docs/06-seguranca-lgpd.md). Escrita por substituicao integral por funcionario.';

create table if not exists secullum."Horario" (
  id uuid default gen_random_uuid() not null,
  "HorarioId" integer not null,
  "Numero" integer,
  "Descricao" text,
  ativo boolean default true not null,
  sincronizado_em timestamp with time zone,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."Horario" enable row level security;
alter table secullum."Horario" force row level security;
comment on table secullum."Horario" is 'Horario (grade prevista) — espelha `Horario` de GET /Horarios (chamada sem parametro). Ver docs/04-modelo-dados.md.';

create table if not exists secullum."HorarioDescanso" (
  id uuid default gen_random_uuid() not null,
  horario_id uuid not null,
  "HorarioId" integer,
  "Tipo" smallint,
  "ValorDescanso" text,
  "LimiteHorasFaltas" text,
  "IncluirFeriado" smallint,
  "FeriadoDomingoApenasUmDescanso" boolean,
  "DescontarFeriadosCasoFaltas" boolean,
  "NaoDescontarAntesAdmissao" boolean,
  "NaoDescontarDuranteAfastamento" boolean,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioDescanso" enable row level security;
alter table secullum."HorarioDescanso" force row level security;
comment on table secullum."HorarioDescanso" is 'No `Horario.Descanso` (tipo `HorarioDescanso`, regras de DSR) — 1:1 com "Horario". Estrutura bate com o manual (confirmado em 2026-08-13). Regras de folha: capturadas, ⛔ NAO consumidas pelo motor.';

create table if not exists secullum."HorarioDescansoFaixaItem" (
  id uuid default gen_random_uuid() not null,
  horario_descanso_id uuid not null,
  "Ordem" integer,
  "Limite" text,
  "Desconto" text,
  criado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioDescansoFaixaItem" enable row level security;
alter table secullum."HorarioDescansoFaixaItem" force row level security;
comment on table secullum."HorarioDescansoFaixaItem" is 'Itens de `Descanso.Faixas` (tipo `HorarioDescansoFaixaItem`: { Ordem, Limite, Desconto }). SEM chave unica de negocio de proposito: escrita por SUBSTITUICAO INTEGRAL do conjunto por "HorarioDescanso", dentro da transacao do ciclo. Nenhum item tem id estavel na origem.';

create table if not exists secullum."HorarioDia" (
  id uuid default gen_random_uuid() not null,
  horario_id uuid not null,
  "HorarioDiaId" integer not null,
  "DiaSemana" smallint not null,
  "Entrada1" time without time zone,
  "Entrada2" time without time zone,
  "Entrada3" time without time zone,
  "Entrada4" time without time zone,
  "Entrada5" time without time zone,
  "Saida1" time without time zone,
  "Saida2" time without time zone,
  "Saida3" time without time zone,
  "Saida4" time without time zone,
  "Saida5" time without time zone,
  "TipoEntrada1" smallint,
  "TipoEntrada2" smallint,
  "TipoEntrada3" smallint,
  "TipoEntrada4" smallint,
  "TipoEntrada5" smallint,
  "TipoSaida1" smallint,
  "TipoSaida2" smallint,
  "TipoSaida3" smallint,
  "TipoSaida4" smallint,
  "TipoSaida5" smallint,
  "ToleranciaExtra" integer,
  "ToleranciaFalta" integer,
  "Carga" integer,
  "TipoDia" smallint,
  "Neutro" boolean default false not null,
  "Compensado" boolean default false not null,
  "AlmocoLivre" boolean default false not null,
  "Alocar24Horas" boolean default false not null,
  sem_expediente boolean default false not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioDia" enable row level security;
alter table secullum."HorarioDia" force row level security;
comment on table secullum."HorarioDia" is 'Grade por dia da semana. Um registro por item de `Horario.Dias[]`. Nome COMPOSTO por nos (`Horario` + `Dia`): o manual do Secullum nao nomeia um tipo para o item do array.';

create table if not exists secullum."HorarioExtras" (
  id uuid default gen_random_uuid() not null,
  horario_id uuid not null,
  "HorarioId" integer,
  "AgruparExtras" boolean,
  "SomenteGrupoExtras" boolean,
  "DescontarFaltasExtras" smallint,
  "DescontarFaltasExtrasNoturnas" boolean,
  "DescontarIgnorarUteis" boolean,
  "DescontarIgnorarSabados" boolean,
  "DescontarIgnorarDomingos" boolean,
  "DescontarIgnorarFeriados" boolean,
  "DescontarIgnorarFolgas" boolean,
  "DescontarIgnorarDiaEspecial" boolean,
  "UsarInterjornada" boolean,
  "Interjornada" text,
  "InterjornadaSeparada" boolean,
  "InterjornadaSeparadaBancoHoras" boolean,
  "SepararExtrasNoturnasDeExtrasNormais" boolean,
  "SepararExtrasIntervalosDeExtrasNormais" boolean,
  "SepararSomatoriaAposMeiaNoite" boolean,
  "MultiplicarExtrasPeloPercentual" boolean,
  "HabilitarMultiplicadorFaixaBancoHoras" boolean,
  "MultiplicarSomenteSaldoPositivo" boolean,
  "NaoDividirExtrasEmFeriados" boolean,
  "NaoDividirExtrasEmDomingos" boolean,
  "DividirJornadaQuandoHouverFolga" boolean,
  "NaoDividirJornadaEmFeriados" boolean,
  "NaoDividirJornadaEmFolgas" boolean,
  "ApenasDividirJornadaFeriadoFolgaDiaSeguinte" boolean,
  "NaoReiniciarDivisoesExtrasDiurnasNoturnas" boolean,
  "ControleHorasExtrasAutorizadas" boolean,
  "QuantidadeExtrasAutorizadas" text,
  "Acumulo" smallint,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioExtras" enable row level security;
alter table secullum."HorarioExtras" force row level security;
comment on table secullum."HorarioExtras" is 'No `Horario.Extras` (tipo `HorarioExtras`). 1:1 com "Horario". ✅ ESTRUTURA FECHADA em 2026-08-13 contra a conta real: 31 campos incluindo "HorarioId" — nao 7 (manual) nem ~15 (estimativa). Regras de folha, capturadas mas ⛔ NAO usadas pelo motor de deteccao. Ver ADR-011.';

create table if not exists secullum."HorarioFaixasExtras" (
  id uuid default gen_random_uuid() not null,
  horario_id uuid not null,
  "HorarioId" integer,
  "DiaSemana" smallint,
  "Controle" smallint,
  "DiaEspecial" smallint,
  criado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioFaixasExtras" enable row level security;
alter table secullum."HorarioFaixasExtras" force row level security;
comment on table secullum."HorarioFaixasExtras" is 'No `Horario.FaixasExtras` (tipo `HorarioFaixasExtras`) — 1:N por horario, uma linha por "Dia Semana" do enum. Escrita por substituicao integral. Regras de folha: capturadas, ⛔ NAO consumidas pelo motor.';

create table if not exists secullum."HorarioFaixasExtrasItem" (
  id uuid default gen_random_uuid() not null,
  horario_faixas_extras_id uuid not null,
  "Ordem" integer,
  "Horas" double precision,
  "Coluna" double precision,
  criado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioFaixasExtrasItem" enable row level security;
alter table secullum."HorarioFaixasExtrasItem" force row level security;
comment on table secullum."HorarioFaixasExtrasItem" is 'Itens de `FaixasExtras.Faixas` (tipo `HorarioFaixasExtrasItem`). Escrita por substituicao integral junto com o pai. Sem chave unica de negocio — nenhum id estavel na origem.';

create table if not exists secullum."HorarioToleranciaEspecifica" (
  id uuid default gen_random_uuid() not null,
  horario_id uuid not null,
  "UsaToleranciaEspecifica" boolean default false not null,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioToleranciaEspecifica" enable row level security;
alter table secullum."HorarioToleranciaEspecifica" force row level security;
comment on table secullum."HorarioToleranciaEspecifica" is 'No `Horario.ToleranciaEspecifica` (SINGULAR, confirmado no payload real; tipo `HorarioToleranciaEspecifica` no manual) — 1:1 com "Horario". Em todos os registros ja inspecionados veio false / lista vazia: nao ha nenhum caso real ativo neste cliente.';

create table if not exists secullum."HorarioToleranciaEspecificaItem" (
  id uuid default gen_random_uuid() not null,
  horario_tolerancia_especifica_id uuid not null,
  "HorarioId" integer,
  "DiaSemana" smallint,
  "Entrada1De" time without time zone,
  "Entrada1Ate" time without time zone,
  "Saida1De" time without time zone,
  "Saida1Ate" time without time zone,
  "Entrada2De" time without time zone,
  "Entrada2Ate" time without time zone,
  "Saida2De" time without time zone,
  "Saida2Ate" time without time zone,
  "Entrada3De" time without time zone,
  "Entrada3Ate" time without time zone,
  "Saida3De" time without time zone,
  "Saida3Ate" time without time zone,
  "Entrada4De" time without time zone,
  "Entrada4Ate" time without time zone,
  "Saida4De" time without time zone,
  "Saida4Ate" time without time zone,
  "Entrada5De" time without time zone,
  "Entrada5Ate" time without time zone,
  "Saida5De" time without time zone,
  "Saida5Ate" time without time zone,
  criado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorarioToleranciaEspecificaItem" enable row level security;
alter table secullum."HorarioToleranciaEspecificaItem" force row level security;
comment on table secullum."HorarioToleranciaEspecificaItem" is 'Itens de `ToleranciaEspecifica.Tolerancias` (tipo `HorarioToleranciaEspecificaItem`). Escrita por substituicao integral junto com o pai.';

create table if not exists secullum."HorariosOpcoes" (
  id uuid default gen_random_uuid() not null,
  horario_id uuid not null,
  "HorarioId" integer,
  "ToleranciaArtigo58" boolean,
  "IgnorarLimiteMinimoCasoBatidaGerarExtrasSuperiorATolerancia" boolean,
  "IgnorarLimiteMinimoCasoBatidaGerarFaltasSuperiorATolerancia" boolean,
  "QualquerMinutoAdiantadoComoExtra" boolean,
  "QualquerMinutoAtrasadoComoFalta" boolean,
  "DescontarToleranciaDasHorasExtras" boolean,
  "DescontarToleranciaDasHorasFaltas" boolean,
  "UsarToleranciaRefeicoes" boolean,
  "ToleranciaRefeicoesMinutos" integer,
  "LimiteMinimoDeFaltasNoDiaMinutos" integer,
  "LimiteMinimoDeExtrasNoDiaMinutos" integer,
  "SubstituirBatidasAbaixoDasTolerancias" boolean,
  "AlocarHorario24Horas" boolean,
  "AlocarBatidas" integer,
  "NaoDescontarFaltasDeNormais" boolean,
  "PreencherFaltasQuandoDiaEstiverEmBranco" boolean,
  "TipoPreencherQuandoDiaEstiverEmBranco" integer,
  "CalcularFaltasSomenteParaDiaInteiro" boolean,
  "ExibirColunaHorasRepousoFaltantesTrabalhoContinuo" boolean,
  "HorasRepousoConfiguracaoPadrao" boolean,
  "HorasRepousoFaixas" jsonb,
  "CompletarBatidasFaltantes" boolean,
  "PermitirFolgasAutomaticas" boolean,
  "QuantidadeFolgasAutomaticas" integer,
  "ColunasRefeicao" integer,
  "SinalizarEmVermelhoAlmocosCurtos" boolean,
  "NaoCalcularNenhumaHoraNoturna" boolean,
  "SepararHorasNoturnasDeHorasNormais" boolean,
  "IncluirIntervaloNoAdicionalNoturno" boolean,
  "PeriodoEspecialAdicionalNoturnoInicio" text,
  "PeriodoEspecialAdicionalNoturnoFim" text,
  "ConsiderarFeriadosComoHoraExtra" boolean,
  "UsarTempoMaisMenosCargaSuperior" boolean,
  "PercentualCargaUsarTempoMaisMenosMinutos" double precision,
  "DefinirCargaAutomaticamente" boolean,
  "Carga" double precision,
  "DesconsiderarNeutroQuandoHouverBatidasNoDia" boolean,
  "UsarDataFechamentoEncerrarSemana" boolean,
  "Compensacao" smallint,
  "CompensacaoIgnorarSabados" boolean,
  "CompensacaoIgnorarDomingos" boolean,
  "CompensacaoIgnorarFeriados" boolean,
  "CompensacaoIgnorarFolgas" boolean,
  "CompensacaoMensalFechamento" jsonb,
  "CompensacaoCalcularHorasComoNormaisCompatibilidadePontoOff" boolean,
  "CalcularNoturnasIndependenteCompensado" boolean,
  "CalcularBatidasIntermediarias" boolean,
  "NaoCalcularHorasFaltaBatidasIntermediarias" boolean,
  "ListaHorasSobreAviso" jsonb,
  "CalcularHorasInItinere" boolean,
  "ListaHorasInItinere" jsonb,
  "SomarHorasInItinereNormais" boolean,
  "CalcularHorasInItinereIninterruptas" boolean,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  tenant_id uuid default '6fcb0cc4-c89e-4549-8e6b-6b348f810371'::uuid not null
);
alter table secullum."HorariosOpcoes" enable row level security;
alter table secullum."HorariosOpcoes" force row level security;
comment on table secullum."HorariosOpcoes" is 'No `Horario.Opcoes` (tipo `HorariosOpcoes` no manual — plural no `Horarios` e literal, nao erro). 1:1 com "Horario". ✅ ESTRUTURA FECHADA em 2026-08-13 contra a conta real (inspecao GET-only, so nomes de campo e tipo, zero valores): 54 campos incluindo "HorarioId" — nao 21 (manual) nem ~35 (estimativa). REGRAS DE CALCULO DE FOLHA: capturadas para consulta/auditoria, ⛔ NAO consumidas pelo motor de deteccao. Ver ADR-011.';

create table if not exists secullum.departamento_gestor (
  id uuid default gen_random_uuid() not null,
  departamento_id uuid not null,
  estrutura_id uuid not null,
  "DepartamentoId" integer not null,
  "EstruturaId" integer not null,
  observado_desde timestamp with time zone default now() not null,
  observado_ate timestamp with time zone,
  funcionarios_observados integer default 0 not null,
  origem text default 'secullum_sync'::text not null,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null
);
alter table secullum.departamento_gestor enable row level security;
comment on table secullum.departamento_gestor is 'Atribuição de gestor ("Estrutura") a unidade ("Departamento") COM VIGÊNCIA (ADR-013). "Estrutura" 1:N "Departamento" (um gestor cobre vários departamentos); cada "Departamento" tem NO MÁXIMO UM gestor vigente a cada instante (índice único parcial abaixo). NÃO é uma junção N:N: o Owner confirmou (2026-08-21) que não existe "unidade com dois gestores simultâneos" — o que existe é substituição temporal (titular afastado -> substituto), registrada como uma nova linha vigente após fechar a anterior.';

create table if not exists secullum.estrutura_evento_titular (
  id uuid default gen_random_uuid() not null,
  estrutura_id uuid not null,
  "EstruturaId" integer not null,
  tipo_evento text not null,
  descricao_anterior text,
  descricao_nova text not null,
  email_anterior text,
  email_novo text,
  funcionario_id_anterior uuid,
  funcionario_id_novo uuid,
  detectado_em timestamp with time zone default now() not null,
  origem text default 'secullum_sync'::text not null,
  criado_em timestamp with time zone default now() not null
);
alter table secullum.estrutura_evento_titular enable row level security;
comment on table secullum.estrutura_evento_titular is 'Histórico APPEND-ONLY de identidade de um nó "Estrutura" (ADR-013, 3º adendo, 2026-08-24). "Estrutura" é a POSIÇÃO (nó do organograma, EstruturaId estável), não a PESSOA: "Descricao"/email contêm o nome/contato de quem ocupa o nó AGORA, e a troca de titular (permanente OU temporária por afastamento — o Secullum não distingue) é sempre uma edição desses campos no MESMO EstruturaId. `departamento_gestor` responde "qual NÓ cobre esta unidade"; esta tabela responde "quem ocupava este nó" — as duas precisam ser compostas para responder "quem respondia pela unidade U em T" (ver ADR-013 §6 do 3º adendo). ⚠️ LIMITAÇÃO NOMEADA (não contornável): uma edição de Descricao NÃO distingue, no payload, "o supervisor mudou de A para B" de "o nó estava rotulado com a pessoa ERRADA e o RH corrigiu" — os dois casos chegam byte a byte idênticos. Esta tabela registra a IDENTIDADE OBSERVADA do nó e quando a sincronização a percebeu, NUNCA "a pessoa mudou nesta data" como fato de negócio certo. `tipo_evento` expõe essa incerteza explicitamente em vez de escondê-la (ver comentário da coluna).';

-- constraints (pk e unique primeiro, depois check, fk por último)
do $$ begin
  alter table secullum."Batida" add constraint "Batida_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."BatidaFonteDados" add constraint "BatidaFonteDados_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Cidade" add constraint "Cidade_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Departamento" add constraint departamento_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Empresa" add constraint empresa_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Estrutura" add constraint estrutura_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcao" add constraint "Funcao_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint funcionario_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioAfastamento" add constraint funcionario_afastamento_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioCentroCusto" add constraint "FuncionarioCentroCusto_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Horario" add constraint horario_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDescanso" add constraint "HorarioDescanso_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDescansoFaixaItem" add constraint "HorarioDescansoFaixaItem_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDia" add constraint horario_dia_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioExtras" add constraint "HorarioExtras_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioFaixasExtras" add constraint "HorarioFaixasExtras_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioFaixasExtrasItem" add constraint "HorarioFaixasExtrasItem_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioToleranciaEspecifica" add constraint "HorarioToleranciaEspecifica_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioToleranciaEspecificaItem" add constraint "HorarioToleranciaEspecificaItem_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorariosOpcoes" add constraint "HorariosOpcoes_pkey" PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.departamento_gestor add constraint departamento_gestor_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_pkey PRIMARY KEY (id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Batida" add constraint batida_funcionario_id_data_key UNIQUE (funcionario_id, "Data");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."BatidaFonteDados" add constraint batida_fonte_dados_marcacao_key UNIQUE (batida_marcacao_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Cidade" add constraint cidade_descricao_key UNIQUE ("Descricao");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Departamento" add constraint departamento_departamentoid_key UNIQUE ("DepartamentoId");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Empresa" add constraint empresa_documento_key UNIQUE ("Documento");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Estrutura" add constraint estrutura_estruturaid_key UNIQUE ("EstruturaId");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcao" add constraint funcao_descricao_key UNIQUE ("Descricao");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint funcionario_funcionarioid_key UNIQUE ("FuncionarioId");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioAfastamento" add constraint funcionario_afastamento_funcionario_afastamentoid_key UNIQUE (funcionario_id, "AfastamentoId");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioCentroCusto" add constraint funcionario_centro_custo_key UNIQUE (funcionario_id, "Descricao");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Horario" add constraint horario_horarioid_key UNIQUE ("HorarioId");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDescanso" add constraint horario_descanso_horario_id_key UNIQUE (horario_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDia" add constraint horario_dia_horario_id_diasemana_key UNIQUE (horario_id, "DiaSemana");
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioExtras" add constraint horario_extras_horario_id_key UNIQUE (horario_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioToleranciaEspecifica" add constraint horario_tolerancia_especifica_horario_id_key UNIQUE (horario_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorariosOpcoes" add constraint horarios_opcoes_horario_id_key UNIQUE (horario_id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Estrutura" add constraint estrutura_canais_notificacao_check CHECK ((canais_notificacao <@ ARRAY['whatsapp'::text, 'email'::text]));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Estrutura" add constraint estrutura_email_origem_check CHECK ((email_origem = ANY (ARRAY['manual'::text, 'secullum'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioAfastamento" add constraint funcionario_afastamento_correlacionado_por_check CHECK ((correlacionado_por = ANY (ARRAY['pis'::text, 'cpf'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDia" add constraint horario_dia_diasemana_check CHECK ((("DiaSemana" >= 0) AND ("DiaSemana" <= 6)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.departamento_gestor add constraint departamento_gestor_intervalo_check CHECK (((observado_ate IS NULL) OR (observado_ate >= observado_desde)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.departamento_gestor add constraint departamento_gestor_origem_check CHECK ((origem = ANY (ARRAY['secullum_sync'::text, 'backfill'::text, 'manual'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_baseline_check CHECK (((tipo_evento <> 'baseline'::text) OR ((descricao_anterior IS NULL) AND (email_anterior IS NULL) AND (funcionario_id_anterior IS NULL))));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_coerencia_check CHECK (
CASE
    WHEN (tipo_evento ~~ 'descricao_alterada%'::text) THEN (descricao_anterior IS DISTINCT FROM descricao_nova)
    WHEN (tipo_evento = 'email_alterado'::text) THEN ((NOT (descricao_anterior IS DISTINCT FROM descricao_nova)) AND (email_anterior IS DISTINCT FROM email_novo))
    ELSE true
END);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_mudanca_check CHECK (((tipo_evento = 'baseline'::text) OR (descricao_anterior IS DISTINCT FROM descricao_nova) OR (email_anterior IS DISTINCT FROM email_novo)));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_origem_check CHECK ((origem = ANY (ARRAY['secullum_sync'::text, 'backfill'::text, 'manual'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_outro_funcionario_check CHECK (((tipo_evento <> 'descricao_alterada_outro_funcionario'::text) OR ((funcionario_id_anterior IS NOT NULL) AND (funcionario_id_novo IS NOT NULL) AND (funcionario_id_anterior <> funcionario_id_novo))));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_tipo_evento_check CHECK ((tipo_evento = ANY (ARRAY['baseline'::text, 'descricao_alterada_outro_funcionario'::text, 'descricao_alterada_mesmo_funcionario'::text, 'descricao_alterada_indeterminada'::text, 'email_alterado'::text])));
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Batida" add constraint "Batida_funcionario_id_fkey" FOREIGN KEY (funcionario_id) REFERENCES secullum."Funcionario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Batida" add constraint "Batida_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."BatidaFonteDados" add constraint "BatidaFonteDados_batida_id_fkey" FOREIGN KEY (batida_id) REFERENCES secullum."Batida"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."BatidaFonteDados" add constraint "BatidaFonteDados_batida_marcacao_id_fkey" FOREIGN KEY (batida_marcacao_id) REFERENCES app.batida_marcacao(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."BatidaFonteDados" add constraint "BatidaFonteDados_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Cidade" add constraint "Cidade_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Departamento" add constraint "Departamento_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Departamento" add constraint departamento_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES secullum."Empresa"(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Empresa" add constraint "Empresa_cidade_id_fkey" FOREIGN KEY (cidade_id) REFERENCES secullum."Cidade"(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Empresa" add constraint "Empresa_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Estrutura" add constraint "Estrutura_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcao" add constraint "Funcao_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint "Funcionario_cidade_id_fkey" FOREIGN KEY (cidade_id) REFERENCES secullum."Cidade"(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint "Funcionario_funcao_id_fkey" FOREIGN KEY (funcao_id) REFERENCES secullum."Funcao"(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint "Funcionario_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint funcionario_afastamento_atual_id_fkey FOREIGN KEY (afastamento_atual_id) REFERENCES secullum."FuncionarioAfastamento"(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint funcionario_departamento_id_fkey FOREIGN KEY (departamento_id) REFERENCES secullum."Departamento"(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint funcionario_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES secullum."Empresa"(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Funcionario" add constraint funcionario_horario_id_fkey FOREIGN KEY (horario_id) REFERENCES secullum."Horario"(id);
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioAfastamento" add constraint "FuncionarioAfastamento_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioAfastamento" add constraint funcionario_afastamento_funcionario_id_fkey FOREIGN KEY (funcionario_id) REFERENCES secullum."Funcionario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioCentroCusto" add constraint "FuncionarioCentroCusto_funcionario_id_fkey" FOREIGN KEY (funcionario_id) REFERENCES secullum."Funcionario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."FuncionarioCentroCusto" add constraint "FuncionarioCentroCusto_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."Horario" add constraint "Horario_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDescanso" add constraint "HorarioDescanso_horario_id_fkey" FOREIGN KEY (horario_id) REFERENCES secullum."Horario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDescanso" add constraint "HorarioDescanso_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDescansoFaixaItem" add constraint "HorarioDescansoFaixaItem_horario_descanso_id_fkey" FOREIGN KEY (horario_descanso_id) REFERENCES secullum."HorarioDescanso"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDescansoFaixaItem" add constraint "HorarioDescansoFaixaItem_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDia" add constraint "HorarioDia_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioDia" add constraint horario_dia_horario_id_fkey FOREIGN KEY (horario_id) REFERENCES secullum."Horario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioExtras" add constraint "HorarioExtras_horario_id_fkey" FOREIGN KEY (horario_id) REFERENCES secullum."Horario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioExtras" add constraint "HorarioExtras_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioFaixasExtras" add constraint "HorarioFaixasExtras_horario_id_fkey" FOREIGN KEY (horario_id) REFERENCES secullum."Horario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioFaixasExtras" add constraint "HorarioFaixasExtras_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioFaixasExtrasItem" add constraint "HorarioFaixasExtrasItem_horario_faixas_extras_id_fkey" FOREIGN KEY (horario_faixas_extras_id) REFERENCES secullum."HorarioFaixasExtras"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioFaixasExtrasItem" add constraint "HorarioFaixasExtrasItem_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioToleranciaEspecifica" add constraint "HorarioToleranciaEspecifica_horario_id_fkey" FOREIGN KEY (horario_id) REFERENCES secullum."Horario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioToleranciaEspecifica" add constraint "HorarioToleranciaEspecifica_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioToleranciaEspecificaItem" add constraint "HorarioToleranciaEspecificaIt_horario_tolerancia_especific_fkey" FOREIGN KEY (horario_tolerancia_especifica_id) REFERENCES secullum."HorarioToleranciaEspecifica"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorarioToleranciaEspecificaItem" add constraint "HorarioToleranciaEspecificaItem_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorariosOpcoes" add constraint "HorariosOpcoes_horario_id_fkey" FOREIGN KEY (horario_id) REFERENCES secullum."Horario"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum."HorariosOpcoes" add constraint "HorariosOpcoes_tenant_id_fkey" FOREIGN KEY (tenant_id) REFERENCES app.tenant(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.departamento_gestor add constraint departamento_gestor_departamento_id_fkey FOREIGN KEY (departamento_id) REFERENCES secullum."Departamento"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.departamento_gestor add constraint departamento_gestor_estrutura_id_fkey FOREIGN KEY (estrutura_id) REFERENCES secullum."Estrutura"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_estrutura_id_fkey FOREIGN KEY (estrutura_id) REFERENCES secullum."Estrutura"(id) ON DELETE CASCADE;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_funcionario_id_anterior_fkey FOREIGN KEY (funcionario_id_anterior) REFERENCES secullum."Funcionario"(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;
do $$ begin
  alter table secullum.estrutura_evento_titular add constraint estrutura_evento_titular_funcionario_id_novo_fkey FOREIGN KEY (funcionario_id_novo) REFERENCES secullum."Funcionario"(id) ON DELETE SET NULL;
exception when duplicate_object or duplicate_table
     or invalid_table_definition then null;
end $$;

set check_function_bodies = off;
-- funções
CREATE OR REPLACE FUNCTION secullum.departamento_gestor_transition(p_close_id uuid, p_departamento_id uuid, p_estrutura_id uuid, p_departamento_id_secullum integer, p_estrutura_id_secullum integer, p_funcionarios_observados integer)
 RETURNS secullum.departamento_gestor
 LANGUAGE plpgsql
AS $function$
declare
    v_row secullum.departamento_gestor;
begin
    if p_close_id is not null then
        update secullum.departamento_gestor
           set observado_ate = now(),
               atualizado_em = now()
         where id = p_close_id
           and observado_ate is null;
    end if;

    insert into secullum.departamento_gestor (
        departamento_id, estrutura_id, "DepartamentoId", "EstruturaId",
        funcionarios_observados, origem
    ) values (
        p_departamento_id, p_estrutura_id, p_departamento_id_secullum, p_estrutura_id_secullum,
        p_funcionarios_observados, 'secullum_sync'
    )
    returning * into v_row;

    return v_row;
end;
$function$;
comment on function secullum.departamento_gestor_transition(p_close_id uuid, p_departamento_id uuid, p_estrutura_id uuid, p_departamento_id_secullum integer, p_estrutura_id_secullum integer, p_funcionarios_observados integer) is 'Único caminho de escrita para abrir uma nova linha VIGENTE de departamento_gestor (fechando a anterior, se p_close_id não for null) em uma única transação (ADR-013 §4). p_close_id = null => primeira linha vigente do departamento (sem titular anterior). Chamado exclusivamente pelo worker de sincronização cadastral (service_role) — nunca por UPDATE + INSERT como duas chamadas HTTP separadas.';

reset check_function_bodies;

-- views

-- índices (os que sustentam constraint já vieram acima)
CREATE INDEX IF NOT EXISTS batida_batidaid_idx ON secullum."Batida" USING btree ("BatidaId");
CREATE INDEX IF NOT EXISTS batida_data_idx ON secullum."Batida" USING btree ("Data");
CREATE INDEX IF NOT EXISTS batida_tenant_idx ON secullum."Batida" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS batida_fonte_dados_batida_id_idx ON secullum."BatidaFonteDados" USING btree (batida_id);
CREATE INDEX IF NOT EXISTS batida_fonte_dados_fontedadosid_idx ON secullum."BatidaFonteDados" USING btree ("FonteDadosId");
CREATE INDEX IF NOT EXISTS batidafontedados_tenant_idx ON secullum."BatidaFonteDados" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS cidade_tenant_idx ON secullum."Cidade" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS "Departamento_empresa_id_fkidx" ON secullum."Departamento" USING btree (empresa_id);
CREATE INDEX IF NOT EXISTS departamento_tenant_idx ON secullum."Departamento" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS empresa_cidade_id_idx ON secullum."Empresa" USING btree (cidade_id);
CREATE INDEX IF NOT EXISTS empresa_empresaid_idx ON secullum."Empresa" USING btree ("EmpresaId");
CREATE INDEX IF NOT EXISTS empresa_tenant_idx ON secullum."Empresa" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS estrutura_tenant_idx ON secullum."Estrutura" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS funcao_tenant_idx ON secullum."Funcao" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS "Funcionario_afastamento_atual_id_fkidx" ON secullum."Funcionario" USING btree (afastamento_atual_id);
CREATE INDEX IF NOT EXISTS "Funcionario_departamento_id_fkidx" ON secullum."Funcionario" USING btree (departamento_id);
CREATE INDEX IF NOT EXISTS "Funcionario_empresa_id_fkidx" ON secullum."Funcionario" USING btree (empresa_id);
CREATE INDEX IF NOT EXISTS "Funcionario_horario_id_fkidx" ON secullum."Funcionario" USING btree (horario_id);
CREATE INDEX IF NOT EXISTS funcionario_afastado_hoje_idx ON secullum."Funcionario" USING btree (afastado_hoje) WHERE (afastado_hoje = true);
CREATE INDEX IF NOT EXISTS funcionario_cidade_id_idx ON secullum."Funcionario" USING btree (cidade_id);
CREATE INDEX IF NOT EXISTS funcionario_funcao_id_idx ON secullum."Funcionario" USING btree (funcao_id);
CREATE INDEX IF NOT EXISTS funcionario_tenant_idx ON secullum."Funcionario" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS funcionario_afastamento_funcionario_janela_idx ON secullum."FuncionarioAfastamento" USING btree (funcionario_id, "Inicio", "Fim");
CREATE INDEX IF NOT EXISTS funcionario_afastamento_janela_idx ON secullum."FuncionarioAfastamento" USING btree ("Fim", "Inicio");
CREATE INDEX IF NOT EXISTS funcionarioafastamento_tenant_idx ON secullum."FuncionarioAfastamento" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS funcionario_centro_custo_funcionario_id_idx ON secullum."FuncionarioCentroCusto" USING btree (funcionario_id);
CREATE INDEX IF NOT EXISTS funcionariocentrocusto_tenant_idx ON secullum."FuncionarioCentroCusto" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horario_tenant_idx ON secullum."Horario" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horariodescanso_tenant_idx ON secullum."HorarioDescanso" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horario_descanso_faixa_item_pai_idx ON secullum."HorarioDescansoFaixaItem" USING btree (horario_descanso_id);
CREATE INDEX IF NOT EXISTS horariodescansofaixaitem_tenant_idx ON secullum."HorarioDescansoFaixaItem" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horario_dia_horariodiaid_idx ON secullum."HorarioDia" USING btree ("HorarioDiaId");
CREATE INDEX IF NOT EXISTS horariodia_tenant_idx ON secullum."HorarioDia" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horarioextras_tenant_idx ON secullum."HorarioExtras" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horario_faixas_extras_horario_id_idx ON secullum."HorarioFaixasExtras" USING btree (horario_id);
CREATE INDEX IF NOT EXISTS horariofaixasextras_tenant_idx ON secullum."HorarioFaixasExtras" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horario_faixas_extras_item_pai_idx ON secullum."HorarioFaixasExtrasItem" USING btree (horario_faixas_extras_id);
CREATE INDEX IF NOT EXISTS horariofaixasextrasitem_tenant_idx ON secullum."HorarioFaixasExtrasItem" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horariotoleranciaespecifica_tenant_idx ON secullum."HorarioToleranciaEspecifica" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horario_tolerancia_especifica_item_pai_idx ON secullum."HorarioToleranciaEspecificaItem" USING btree (horario_tolerancia_especifica_id);
CREATE INDEX IF NOT EXISTS horariotoleranciaespecificaitem_tenant_idx ON secullum."HorarioToleranciaEspecificaItem" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS horariosopcoes_tenant_idx ON secullum."HorariosOpcoes" USING btree (tenant_id);
CREATE INDEX IF NOT EXISTS departamento_gestor_estrutura_vigente_idx ON secullum.departamento_gestor USING btree (estrutura_id) WHERE (observado_ate IS NULL);
CREATE INDEX IF NOT EXISTS departamento_gestor_historico_idx ON secullum.departamento_gestor USING btree (departamento_id, observado_desde DESC);
CREATE UNIQUE INDEX IF NOT EXISTS departamento_gestor_vigente_key ON secullum.departamento_gestor USING btree (departamento_id) WHERE (observado_ate IS NULL);
CREATE UNIQUE INDEX IF NOT EXISTS estrutura_evento_titular_baseline_uniq ON secullum.estrutura_evento_titular USING btree (estrutura_id) WHERE (tipo_evento = 'baseline'::text);
CREATE INDEX IF NOT EXISTS estrutura_evento_titular_estrutura_detectado_idx ON secullum.estrutura_evento_titular USING btree (estrutura_id, detectado_em DESC);

-- policies

-- triggers

-- grants de schema
revoke all on schema secullum from public, anon, authenticated, service_role;
grant usage on schema secullum to service_role;

-- grants
revoke all on table secullum."Batida" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Batida" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Batida" to service_role;
revoke all on table secullum."BatidaFonteDados" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."BatidaFonteDados" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."BatidaFonteDados" to service_role;
revoke all on table secullum."Cidade" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Cidade" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Cidade" to service_role;
revoke all on table secullum."Departamento" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Departamento" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Departamento" to service_role;
revoke all on table secullum."Empresa" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Empresa" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Empresa" to service_role;
revoke all on table secullum."Estrutura" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Estrutura" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Estrutura" to service_role;
revoke all on table secullum."Funcao" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Funcao" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Funcao" to service_role;
revoke all on table secullum."Funcionario" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Funcionario" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Funcionario" to service_role;
revoke all on table secullum."FuncionarioAfastamento" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."FuncionarioAfastamento" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."FuncionarioAfastamento" to service_role;
revoke all on table secullum."FuncionarioCentroCusto" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."FuncionarioCentroCusto" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."FuncionarioCentroCusto" to service_role;
revoke all on table secullum."Horario" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Horario" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."Horario" to service_role;
revoke all on table secullum."HorarioDescanso" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioDescanso" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioDescanso" to service_role;
revoke all on table secullum."HorarioDescansoFaixaItem" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioDescansoFaixaItem" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioDescansoFaixaItem" to service_role;
revoke all on table secullum."HorarioDia" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioDia" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioDia" to service_role;
revoke all on table secullum."HorarioExtras" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioExtras" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioExtras" to service_role;
revoke all on table secullum."HorarioFaixasExtras" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioFaixasExtras" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioFaixasExtras" to service_role;
revoke all on table secullum."HorarioFaixasExtrasItem" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioFaixasExtrasItem" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioFaixasExtrasItem" to service_role;
revoke all on table secullum."HorarioToleranciaEspecifica" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioToleranciaEspecifica" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioToleranciaEspecifica" to service_role;
revoke all on table secullum."HorarioToleranciaEspecificaItem" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioToleranciaEspecificaItem" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorarioToleranciaEspecificaItem" to service_role;
revoke all on table secullum."HorariosOpcoes" from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorariosOpcoes" to postgres;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum."HorariosOpcoes" to service_role;
revoke all on table secullum.departamento_gestor from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum.departamento_gestor to postgres;
grant insert, select, update on table secullum.departamento_gestor to service_role;
revoke all on table secullum.estrutura_evento_titular from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table secullum.estrutura_evento_titular to postgres;
grant insert, select on table secullum.estrutura_evento_titular to service_role;
revoke all on function secullum.departamento_gestor_transition(p_close_id uuid, p_departamento_id uuid, p_estrutura_id uuid, p_departamento_id_secullum integer, p_estrutura_id_secullum integer, p_funcionarios_observados integer) from public, anon, authenticated, service_role;
grant execute on function secullum.departamento_gestor_transition(p_close_id uuid, p_departamento_id uuid, p_estrutura_id uuid, p_departamento_id_secullum integer, p_estrutura_id_secullum integer, p_funcionarios_observados integer) to postgres;
grant execute on function secullum.departamento_gestor_transition(p_close_id uuid, p_departamento_id uuid, p_estrutura_id uuid, p_departamento_id_secullum integer, p_estrutura_id_secullum integer, p_funcionarios_observados integer) to service_role;

-- privilégios default (o que uma tabela nova já nasce podendo)

-- comentários de coluna
comment on column secullum."Batida"."Ajuste" is '[VALIDAR — Postman] Tipo real desconhecido (o cadastro de Justificativas trata Ajuste/Abono2..4 como boolean de abono automatico; no cartao ponto sao valores HH:mm). Modelado como TEXT para preservar o valor bruto sem risco de conversao errada. Mesma ressalva para "Abono2"/"Abono3"/"Abono4".';
comment on column secullum."Batida"."BatidaId" is 'Campo `Id` do topo do registro de /Batidas (forma qualificada, ver ADR-012). ATRIBUTO com indice NAO-UNICO — NAO e a chave de idempotencia (alteracao (A) ao ADR-007). A chave e (funcionario_id, "Data"), unica por construcao. Divergencia entre os dois (mesmo par funcionario/data reaparecendo com outro Id) deve ser LOGADA como anomalia, nunca contornada em silencio.';
comment on column secullum."Batida"."Data" is 'Campo `Data`. ⛔ Parsing OBRIGATORIO pelos 10 PRIMEIROS CARACTERES da string ("yyyy-MM-ddT00:00:00"). Nunca via new Date(...)/toISOString(): a Edge Function roda em UTC e a conversao ingenua desloca um dia. A parte de hora do campo e sempre 00:00:00 e nao tem significado.';
comment on column secullum."Batida"."FuncionarioId" is 'Campo `FuncionarioId` do payload — INTEIRO do Secullum, guardado como veio. E a chave de juncao com "Funcionario"."FuncionarioId". ⚠️ A FK real e funcionario_id (uuid), ao lado.';
comment on column secullum."Batida"."NBanco" is 'Campo `NBanco` (banco de horas do dia). ✅ Sob a nomenclatura literal (ADR-012) a abreviacao opaca deixou de ser um problema de decisao nossa: e simplesmente o nome que o Secullum usa.';
comment on column secullum."Batida"."Observacoes" is '⚠️ TEXTO LIVRE. Ate 2026-08-12 era explicitamente NAO sincronizado por LGPD (podia carregar motivo de afastamento = dado de saude). Passa a ser persistido por decisao expressa do Owner (ADR-011). ⛔ Nunca exibir em relatorio ao gestor, nunca logar. A base legal para reter isto esta PENDENTE.';
comment on column secullum."Batida".status_dia_rotulo is 'DERIVADO POR NOS (minusculo — nao procure este campo no payload): preenchido pelo parser quando as colunas do dia carregam TEXTO DE STATUS (ex.: rotulo de afastamento) em vez de horas. Torna explicito no relatorio que o dia nao e "falta", e status. ⛔ NUNCA e fonte de periodo de afastamento — essa e "FuncionarioAfastamento" (ADR-010).';
comment on column secullum."BatidaFonteDados"."DataInclusao" is 'Campo `DataInclusao` — quando o registro entrou no Secullum. Diagnostico de batida lancada RETROATIVAMENTE, que invalida desvio ja detectado e possivelmente ja enviado no relatorio.';
comment on column secullum."BatidaFonteDados"."Nsr" is 'Numero Sequencial de Registro do equipamento. TEXT (nao numerico): e identificador, nao quantidade, e pode vir com zeros a esquerda.';
comment on column secullum."BatidaFonteDados"."Origem" is 'Campo `Origem` BRUTO (0..8 documentados). ⚠️ Origem = 11 JA APARECEU em producao e nao consta da documentacao oficial; significado ainda [DECISAO DO OWNER]. Por isso: sem CHECK, sem enum, sem significado presumido, job nunca falha. Logar uma vez por valor desconhecido distinto por execucao.';
comment on column secullum."BatidaFonteDados"."Tipo" is 'Campo `Tipo` BRUTO (Original=0, Manual=1, PreAssinalado=2, Desconsiderado=3). smallint SEM CHECK e SEM enum do Postgres: valor fora do documentado e persistido, tolerado e traduzido apenas na apresentacao.';
comment on column secullum."BatidaFonteDados".batida_id is 'NOSSA FK, desnormalizada a partir de batida_marcacao para permitir DELETE/consulta no escopo do dia inteiro sem join. Ambas as FKs sao ON DELETE CASCADE — expurgo por titular chega ate aqui.';
comment on column secullum."Cidade"."CidadeId" is 'Campo `Cidade.Id`. NULLABLE e SEM UNIQUE de proposito: o que se confirmou foi a FORMA do no, NAO a unicidade global do Id — que nunca foi verificada. Este projeto ja quebrou em producao duas vezes supondo unicidade global de id do Secullum. A chave de idempotencia e "Descricao".';
comment on column secullum."Departamento"."DepartamentoId" is 'Campo `Departamento.Id`. Chave de idempotencia, UNIQUE GLOBAL (ADR-008). O detector de colisao (unit_name_changed / unit_ref_name_conflict nos logs) continua sendo a rede de seguranca.';
comment on column secullum."Departamento"."Nfolha" is 'Campo `Departamento.Nfolha` (grafia literal confirmada em payload real: "Nfolha", f minusculo). Numero visivel na folha. ⚠️ Se algum identificador de Departamento se repetir entre empresas, o candidato natural e este, NAO "DepartamentoId" (ADR-008).';
comment on column secullum."Departamento".ativo is 'DERIVADO/FIXO POR NOS (minusculo): o Secullum NAO expoe status de Departamento ({ Id, Descricao, Nfolha }). Fica fixo em true e NAO ha tabela de historico. ⛔ Nao inferir desativacao pela ausencia do DepartamentoId no lote de /Funcionarios (ADR-009).';
comment on column secullum."Departamento".empresa_id is 'NOSSA FK (uuid). ⚠️ EMPRESA DE REFERENCIA, nao de propriedade (ADR-008): e a empresa do PRIMEIRO funcionario visto naquele departamento. ⛔ Agregacao por Empresa usa SEMPRE "Funcionario".empresa_id, NUNCA esta coluna.';
comment on column secullum."Empresa"."Desativada" is 'Campo `Empresa.Desativada` — ESTADO ATUAL, sem data. O Secullum nao informa QUANDO a empresa foi desativada; por isso empresa_evento_status so tem detectado_em. Escreva AQUI, nunca em `ativo`.';
comment on column secullum."Empresa"."DiaFechamentoPonto" is '[VALIDAR — Postman] Tipo assumido smallint (dia do mes). Mesma ressalva de "FechamentoPonto".';
comment on column secullum."Empresa"."Documento" is 'Campo `Documento` (CNPJ/CPF) — chave natural de idempotencia da sincronizacao, que e a chave que o proprio Secullum usa na rota Empresas.';
comment on column secullum."Empresa"."EmitiuAtestadoTecnico" is '[VALIDAR — Postman] Nao consta do manual oficial; reportado pelo Owner no payload real.';
comment on column secullum."Empresa"."EmpresaId" is 'Campo `Empresa.Id`. ATRIBUTO com indice NAO-UNICO: a chave de idempotencia continua sendo "Documento", que e a chave que o proprio Secullum usa na rota Empresas. Nao promover a UNIQUE sem evidencia.';
comment on column secullum."Empresa"."FechamentoPonto" is '[VALIDAR — Postman] Tipo assumido smallint (por analogia com `HorarioDia.Fechamento`, Inteiro 0..23). Se o payload real trouxer "HH:mm" ou boolean, abrir migration corretiva — nao forcar conversao no parser.';
comment on column secullum."Empresa"."Logotipo" is 'Logotipo em base 64. Volume irrelevante com poucas empresas. ⚠️ Se o cadastro crescer, avaliar deixar de sincronizar — nao ha consumidor de produto para ele hoje.';
comment on column secullum."Empresa"."NfolhaEmpresa" is '[VALIDAR — Postman] Grafia assumida por analogia com `Departamento.Nfolha` (confirmado com f minusculo). Vem do cadastro do manual, nao do no aninhado — pode nunca ser populado (ver aviso abaixo).';
comment on column secullum."Empresa"."ResponsavelNome" is '⚠️ Responsavel LEGAL da empresa. NAO e o gestor que recebe o relatorio consolidado — esse vive na tabela "Estrutura", vem de `Funcionario.Estrutura` e e outra pessoa. Foi para evitar exatamente esta confusao que a tabela de gestor NAO se chama `Responsavel`.';
comment on column secullum."Empresa"."TipoDocumento" is 'Enum BRUTO (0=CNPJ, 1=CPF, 2=Outros). smallint SEM CHECK — disciplina do projeto para enum do Secullum: valor desconhecido e persistido e tolerado, nunca derruba o job.';
comment on column secullum."Empresa"."UsaFechamentoDoPontoEspecifico" is '[VALIDAR — Postman] Nao consta do manual oficial (pag. 7-9); reportado pelo Owner no payload real.';
comment on column secullum."Empresa".ativo is 'DERIVADA POR NOS (minusculo) e GERADA PELO POSTGRES: coalesce(not "Desativada", true). ⛔ O upsert da sincronizacao NAO pode incluir esta coluna — o Postgres rejeita escrita em coluna gerada. Grave "Desativada". Ver o cabecalho da secao 4 desta migration e ADR-009.';
comment on column secullum."Empresa".cidade_id is 'NOSSA FK (uuid) -> "Cidade". ⚠️ NAO confundir com "CidadeId" (inteiro do Secullum), ao lado.';
comment on column secullum."Estrutura"."Descricao" is 'Campo `Estrutura.Descricao` — na pratica, o NOME do gestor responsavel. E o unico dado de identificacao do gestor que o Secullum fornece: e-mail e WhatsApp nao existem la.';
comment on column secullum."Estrutura"."EstruturaId" is 'Campo `Funcionario.EstruturaId` (= `Estrutura.Id`) — chave de idempotencia. Nunca resolvido subindo por "EstruturaPaiId".';
comment on column secullum."Estrutura"."EstruturaPaiId" is 'Campo `Estrutura.EstruturaPaiId`. Guardado so como contexto/diagnostico. 0 = raiz. ⏳ EM ABERTO (ADR-006): qual nivel da arvore e o gestor quando a estrutura nao for raiz. Ate isso ser respondido pelo Owner, NAO subir a arvore.';
comment on column secullum."Estrutura".email is 'NOSSO (minusculo) apesar de o VALOR vir do Secullum: nao e um campo de `Estrutura`, e o `Funcionario.Email` do funcionario cujo "Nome" bate com "Descricao". E resultado da NOSSA logica de match, nao um no do payload.';
comment on column secullum."Estrutura".email_origem is 'NOSSO (minusculo). manual (default) | secullum. A sincronizacao SO escreve em email quando email IS NULL OU email_origem = ''secullum''. Valor cadastrado pelo Owner NUNCA e sobrescrito.';
comment on column secullum."Estrutura".whatsapp is 'NOSSO (minusculo) — SEMPRE cadastro manual do Owner, nao ha campo equivalente no Secullum. ⛔ NAO derivar de "Funcionario"."Celular"/"Telefone" (agora capturados): telefone pessoal nao e canal de notificacao autorizado. Ver docs/06-seguranca-lgpd.md.';
comment on column secullum."Funcao"."FuncaoId" is 'Campo `Funcao.Id`, quando presente. NULLABLE e sem UNIQUE — mesma disciplina de "Cidade"."CidadeId". A chave de idempotencia e "Descricao" (que e a chave usada pelo proprio Secullum na rota Funcoes).';
comment on column secullum."Funcionario"."Admissao" is 'Funcionario.Admissao (data real do Secullum, ja presente no payload de /Funcionarios). Entra na allow-list de PII: e dado de vinculo empregaticio necessario para saber se o funcionario estava ativo na janela do relatorio/dashboard. Ver docs/06-seguranca-lgpd.md.';
comment on column secullum."Funcionario"."Celular" is 'Campo `Celular`. ⛔ NAO usar como numero de WhatsApp para notificacao — telefone pessoal nao e canal autorizado. "Estrutura".whatsapp continua 100% manual ([DECISAO DO OWNER]).';
comment on column secullum."Funcionario"."ConfigEspecificaCapturaDeFotoNoMomentoDaInclusao" is '✅ Nome confirmado. ⚠️ E apenas a CONFIGURACAO. Nenhuma foto e buscada nem armazenada por este projeto (ver "PossuiFoto" e o cabecalho desta migration).';
comment on column secullum."Funcionario"."ConfigEspecificaInclusaoManualPonto" is '✅ Nome confirmado no payload real (2026-08-13). ⏳ [VALIDAR — Postman] TIPO: a inspecao entregou so a chave. Assumido boolean; se for enum de modo (0/1/2), abrir migration corretiva. ⛔ Parser deve normalizar e devolver NULL em valor inesperado, nunca derrubar o ciclo.';
comment on column secullum."Funcionario"."ConfigEspecificaInclusaoManualPontoFusoHorarioId" is '✅ Nome confirmado. Sufixo Id => integer bruto, SEM FK: o cadastro de fusos horarios do Secullum nao e consumido por este projeto.';
comment on column secullum."Funcionario"."Cpf" is 'Campo `Cpf`. Sem UNIQUE de proposito: duplicata no cadastro do cliente cai no caso "2+ candidatos" da correlacao de afastamentos, que se abstem em vez de errar o titular.';
comment on column secullum."Funcionario"."Demissao" is 'Funcionario.Demissao (data real do Secullum; null enquanto o vinculo estiver ativo). Pode vir com data FUTURA (desligamento programado) — ver a regra de derivacao de employee.active em docs/04-modelo-dados.md.';
comment on column secullum."Funcionario"."DepartamentoId" is 'Campo `Funcionario.DepartamentoId` — INTEIRO do Secullum. A FK usada e departamento_id (uuid).';
comment on column secullum."Funcionario"."DesabilitarAssinaturaEletronica" is '✅ Nome confirmado. ⏳ [VALIDAR — Postman] tipo assumido boolean, como os demais Bloquear*/Permite*/Desabilitar* deste bloco.';
comment on column secullum."Funcionario"."Email" is 'Campo `Email` do funcionario. ⚠️ Ate 2026-08-13 so era lido em memoria para resolver "Estrutura".email quando o funcionario ERA o gestor; agora e persistido para todos. Isso NAO autoriza usa-lo como canal de notificacao: destinatario de relatorio continua sendo apenas "Estrutura".email/"Estrutura".whatsapp.';
comment on column secullum."Funcionario"."EmpresaId" is 'Campo `Funcionario.EmpresaId` — INTEIRO do Secullum, como veio. ⚠️ A FK que o sistema usa e empresa_id (uuid). Nunca fazer join por esta coluna.';
comment on column secullum."Funcionario"."EstruturaId" is 'Campo `Funcionario.EstruturaId` — INTEIRO do Secullum; e a chave de idempotencia de "Estrutura" (tabela do gestor). Nao ha FK uuid daqui para "Estrutura": o vinculo gestor->departamento e o que importa ao produto, e resolve-lo por funcionario duplicaria a relacao.';
comment on column secullum."Funcionario"."FuncionarioId" is 'Campo `Funcionario.Id` — nomeado na forma qualificada porque e literalmente assim que o Secullum o chama de fora (`Batidas.FuncionarioId`). Chave de idempotencia e chave de juncao com /Batidas.';
comment on column secullum."Funcionario"."HorarioAlternativo2Id" is 'Campo `HorarioAlternativo2Id` — inteiro BRUTO, sem FK para "Horario" de proposito: o horario referenciado pode nao existir localmente (ou ainda nao ter sido sincronizado no ciclo), e uma FK transformaria isso em falha de job. Resolucao para "Horario".id, se necessaria, e da consulta.';
comment on column secullum."Funcionario"."HorarioId" is 'Campo `Funcionario.HorarioId` — INTEIRO do Secullum. A FK usada e horario_id (uuid). ℹ️ Em /Funcionarios o objeto `Horario` aninhado vem com `Dias` = null POR DESIGN: a grade completa so vem de GET /Horarios.';
comment on column secullum."Funcionario"."Mae" is '⚠️ PII de TERCEIRO (a mae do funcionario nao e titular deste tratamento nem tem relacao com o controlador). Capturada por decisao do Owner; e o campo com a justificativa de finalidade mais fraca de todo o schema. Vale o mesmo para "Pai". Ver docs/06-seguranca-lgpd.md.';
comment on column secullum."Funcionario"."MotivoDemissaoId" is 'Campo `MotivoDemissaoId` bruto. A rota MotivosDemissao NAO e consumida (escopo de 5 endpoints), entao o motivo em texto nao existe localmente — o que, alias, e desejavel: motivo de demissao e dado sensivel de vinculo.';
comment on column secullum."Funcionario"."NumeroFolha" is 'Campo `NumeroFolha` (Texto(22)) — matricula na folha. Dado pessoal identificador.';
comment on column secullum."Funcionario"."NumeroPis" is 'Campo `NumeroPis`. Pode vir string vazia — tratar "" como AUSENTE. Sem UNIQUE, mesmo racional de "Cpf".';
comment on column secullum."Funcionario"."Observacao" is '⚠️ TEXTO LIVRE de RH (Texto(255)). Alto risco de conter dado de saude/condicao pessoal. Persistido por decisao do Owner (ADR-011), contrariando a regra anterior de descarte de texto livre. ⛔ Nunca exibir em relatorio ao gestor, nunca logar, nunca indexar para busca.';
comment on column secullum."Funcionario"."PeriodoEncerrado" is '[VALIDAR — Postman] Tipo desconhecido (data? boolean?). Modelado como TEXT para nao perder o valor nem quebrar o job por conversao errada; converter em migration corretiva depois da inspecao do payload.';
comment on column secullum."Funcionario"."PossuiFoto" is 'Apenas o indicador. A imagem em si exigiria a rota Funcionarios/fotos (6o endpoint) e NAO e buscada.';
comment on column secullum."Funcionario"."Rg" is '⚠️ PII sensivel, capturada a partir de 2026-08-13 por decisao do Owner (ADR-011). Antes era explicitamente descartada pelo parser. Nunca logar, nunca exibir em notificacao.';
comment on column secullum."Funcionario".afastado_hoje is 'DERIVADO POR NOS (minusculo). O nome declara a limitacao no proprio identificador: responde APENAS "esta afastado HOJE?". Para "estava afastado na data X?" (motor, relatorio, dashboard) a fonte da verdade e SEMPRE "FuncionarioAfastamento". E funcao do tempo: vira sozinho no primeiro e no ultimo dia do afastamento, sem nada mudar no Secullum.';
comment on column secullum."Funcionario".afastamento_atual_id is 'Ponteiro para o registro de employee_absence que cobre "hoje" (null quando on_leave = false). Existe para o painel mostrar "afastado ate DD/MM" com um unico join, sem duplicar as datas em employee (dado duplicado = dado que dessincroniza). ON DELETE SET NULL: se o afastamento sumir do Secullum e for removido pela convergencia, o ponteiro se limpa sozinho. Havendo mais de um periodo cobrindo hoje (sobreposicao), aponta o de maior end_date e a sobreposicao e logada como aviso (absence_overlap).';
comment on column secullum."Funcionario".ativo is 'DERIVADO POR NOS (minusculo, NAO e campo do Secullum): VINCULO EMPREGATICIO, calculado a partir das datas com "hoje" em America/Sao_Paulo: ativo = ("Admissao" is null or "Admissao" <= hoje) and ("Demissao" is null or "Demissao" >= hoje). ⛔ NAO e afetado por ferias/afastamento — para isso existe afastado_hoje. ⚠️ Continua sendo COLUNA NORMAL (ao contrario de "Empresa".ativo, que virou gerada): esta derivacao depende de "hoje", nao e funcao imutavel das colunas, e por isso NAO pode ser GENERATED. Ver ADR-009 e ADR-010.';
comment on column secullum."Funcionario".cidade_id is 'NOSSA FK (uuid) -> "Cidade". ⚠️ NAO confundir com "CidadeId" (inteiro do Secullum), ao lado.';
comment on column secullum."Funcionario".empresa_id is 'NOSSA FK (uuid). Desnormalizada de proposito em relacao a "Departamento".empresa_id — e assim que o Secullum entrega o dado, e o dashboard agrega por Empresa. ⛔ Agregacao por Empresa usa SEMPRE esta coluna. ⚠️ NAO confundir com "EmpresaId" (inteiro do Secullum), criada em 20260813161000.';
comment on column secullum."Funcionario".funcao_id is 'NOSSA FK (uuid) -> "Funcao". ⚠️ NAO confundir com "FuncaoId" (inteiro do Secullum), ao lado.';
comment on column secullum."Funcionario".horario_id is 'NOSSA FK (uuid) -> "Horario". NULLABLE: funcionario sem horario cadastrado no Secullum nao derruba a sincronizacao (fica sem horario, com aviso em log). ⚠️ NAO confundir com "HorarioId" (inteiro do Secullum).';
comment on column secullum."FuncionarioAfastamento"."AfastamentoId" is 'Campo `Id` do registro de afastamento (nao consta da tabela oficial do manual; confirmado em payload real). Forma qualificada pelo mesmo motivo de "FuncionarioId": `Id` puro colidiria por case com o `id` interno. Unicidade global NUNCA verificada — por isso a chave e COMPOSTA com funcionario_id.';
comment on column secullum."FuncionarioAfastamento"."DataInclusao" is 'Campo `DataInclusao` (nao documentado na tabela oficial; confirmado em payload real). Quando o registro foi criado no Secullum. Serve para diagnosticar afastamento lancado RETROATIVAMENTE, que invalida desvios ja detectados na janela — ver requisito do motor em sprints/sprint-02-motor-deteccao.md.';
comment on column secullum."FuncionarioAfastamento"."Fim" is 'Campo `Fim`, INCLUSIVO (o dia de Fim ainda e afastamento). Parsing pelos 10 primeiros caracteres da string, nunca via Date/UTC. ⛔ Sem CHECK ("Fim" >= "Inicio") de proposito: registro invertido na origem nao pode derrubar o job — o parser loga absence_invalid_range, nao grava e segue.';
comment on column secullum."FuncionarioAfastamento"."Inicio" is 'Campo `Inicio` (Data, obrigatorio). Parsing obrigatorio: 10 PRIMEIROS CARACTERES da string. NUNCA via new Date(...)/toISOString() — a Edge Function roda em UTC e a conversao ingenua desloca um dia.';
comment on column secullum."FuncionarioAfastamento"."JustificativaNome" is 'Campo `JustificativaNome` (Texto(7)), bruto, sem CHECK e sem lista fechada. ⚠️ Tratar como potencialmente revelador de saude: nunca exibido cru em relatorio/painel e nunca logado junto de identificacao do titular. O cadastro de Justificativas NAO e consumido.';
comment on column secullum."FuncionarioAfastamento".correlacionado_por is 'NOSSO (minusculo) — diagnostico (pis | cpf): qual chave resolveu a correlacao. Nao e PII: guarda o TIPO de chave, nunca o valor.';
comment on column secullum."FuncionarioAfastamento".funcionario_id is 'Correlacao resolvida EM MEMORIA por NumeroPis (prioridade) com fallback para Cpf: este endpoint NAO tem FuncionarioId, diferente de /Batidas. NumeroPis pode vir string vazia (visto em payload real) — tratar "" como ausente. Comparacao sempre sobre digitos (strip de mascara) nos dois lados. Zero ou 2+ candidatos => registro DESCARTADO com aviso agregado, nunca escolha arbitraria (mesma regra do match de gestor, docs/03-integracao-secullum.md).';
comment on column secullum."FuncionarioAfastamento".sincronizado_em is 'Ultima vez que este registro foi visto na resposta do Secullum. Base do delete de convergencia (registro apagado no Secullum tem de sumir daqui, senao suprime desvio para sempre).';
comment on column secullum."FuncionarioCentroCusto"."Descricao" is 'Unico campo do item no payload. A chave (funcionario_id, "Descricao") e a unica identidade possivel.';
comment on column secullum."Horario"."HorarioId" is 'Campo `Horario.Id` — chave de idempotencia local.';
comment on column secullum."Horario"."Numero" is 'Campo `Horario.Numero` — chave de NEGOCIO do Secullum (a rota Horarios?numero=<N> usa este campo). NAO e a chave de idempotencia local, que e "HorarioId".';
comment on column secullum."Horario".ativo is 'DERIVADO POR NOS (minusculo) do campo `Desativar`. ⏳ O campo literal "Desativar" NAO foi criado: tipo/semantica exatos nao confirmados no payload real (docs/03-integracao-secullum.md). Nao inventar coluna — abrir migration corretiva quando o tipo for observado.';
comment on column secullum."HorarioDescanso"."IncluirFeriado" is 'Enum bruto (DescansoDomingo=0, DescansoDia=1, HoraNormalDia=2, HoraNormalDescanso=3), sem CHECK.';
comment on column secullum."HorarioDescanso"."LimiteHorasFaltas" is 'Texto(5) HH:mm — tambem DURACAO. Mesma razao de "ValorDescanso" para manter TEXT.';
comment on column secullum."HorarioDescanso"."Tipo" is 'Enum bruto (Automatico=0, Variavel=1), smallint sem CHECK.';
comment on column secullum."HorarioDescanso"."ValorDescanso" is 'Texto(5) no formato HH:mm, mas semanticamente uma DURACAO (valor do DSR), nao um horario do dia. Mantido TEXT de proposito: o tipo `time` do Postgres nao representa duracao acima de 24h e induziria comparacoes erradas. Este sistema nao calcula DSR.';
comment on column secullum."HorarioDescansoFaixaItem"."Limite" is 'Texto(5) HH:mm (DURACAO). Mantido TEXT — mesma razao de "HorarioDescanso"."ValorDescanso".';
comment on column secullum."HorarioDia"."Carga" is 'Campo `Carga`, EM MINUTOS de carga do dia. Discriminador de dia sem expediente (junto com os 10 pares nulos). ⚠️ NAO confundir com "HorariosOpcoes"."Carga", que e a carga configurada no nivel do HORARIO.';
comment on column secullum."HorarioDia"."DiaSemana" is 'Campo `DiaSemana`: 0=Segunda .. 6=Domingo. ⛔ NUNCA usar EXTRACT(DOW) (0=Domingo) ao comparar com uma data — usar EXTRACT(ISODOW)-1. ⚠️ NAO confundir com "HorarioFaixasExtras"."DiaSemana", que e um enum COMPLETAMENTE diferente (Uteis=0, Sabado=1, ... IntervaloFolgas=15).';
comment on column secullum."HorarioDia"."HorarioDiaId" is 'Campo `Dias[].Id`. ATRIBUTO de diagnostico (indice nao-unico) — NAO e chave de idempotencia: confirmado em producao que se repete entre Horarios diferentes (migration 20260812140000). A chave real e (horario_id, "DiaSemana").';
comment on column secullum."HorarioDia"."TipoEntrada1" is 'TipoEntradaN bruto (smallint, sem CHECK/enum — enum nao documentado pelo Secullum).';
comment on column secullum."HorarioDia"."ToleranciaExtra" is 'Campo `ToleranciaExtra`, EM MINUTOS (a unidade nao esta no nome porque o nome e literal do Secullum). ⛔ Junto com "ToleranciaFalta", e a UNICA tolerancia que o motor de deteccao pode aplicar — nunca uma tolerancia propria, sob pena de divergir do calculo oficial de folha.';
comment on column secullum."HorarioDia"."ToleranciaFalta" is 'Campo `ToleranciaFalta`, EM MINUTOS. ⚠️ ARMADILHA CONFIRMADA: dia de folga vem com "ToleranciaExtra"/"ToleranciaFalta" PREENCHIDOS. Presenca de tolerancia NAO significa que ha expediente.';
comment on column secullum."HorarioDia".sem_expediente is 'DERIVADO POR NOS — por isso minusculo, e NAO um campo que o Secullum manda. true quando "Carga" = 0 E os 10 pares Entrada/Saida sao nulos. Nome escolhido para nao colidir com `Batida.Folga` nem com `TipoDia = Folga(2)`, que sao tres coisas distintas.';
comment on column secullum."HorarioExtras"."Acumulo" is 'Enum BRUTO 0..8 (Independentes=0 ... UteisDomingo_e_SabadoFeriado=8), smallint SEM CHECK.';
comment on column secullum."HorarioExtras"."ControleHorasExtrasAutorizadas" is '⚠️ Regra de FOLHA: limita quanto de hora extra o Secullum considera autorizado. ⛔ O motor de deteccao NAO filtra desvio por esta regra — o relatorio consolidado reporta desvio de HORARIO, nao saldo autorizado de folha. Confundir os dois faz o relatorio deixar de mostrar exatamente o excesso que o gestor precisa ver.';
comment on column secullum."HorarioExtras"."DescontarFaltasExtras" is 'Enum BRUTO (MaisSignificativas=0, MenosSignificativas=1), smallint SEM CHECK — mesma disciplina de "HorarioDia"."TipoEntrada1" e de "BatidaFonteDados"."Origem".';
comment on column secullum."HorarioExtras"."DescontarIgnorarDiaEspecial" is '"Dia especial" aqui e o mesmo conceito de "HorarioFaixasExtras"."DiaEspecial" (Domingo=0..Sabado=6) — ⚠️ TERCEIRA convencao de dia da semana do schema, diferente de "HorarioDia"."DiaSemana".';
comment on column secullum."HorarioExtras"."Interjornada" is '⚠️⚠️ DIVERGENCIA CONFIRMADA DA DOCUMENTACAO OFICIAL. O manual declara `Interjornada` como Booleano, com uma descricao que nem sequer e deste campo ("marcar qualquer minuto adiantado como extra", copiada de HorariosOpcoes). O valor REAL observado na conta do cliente em 2026-08-13 e uma STRING — provavelmente o intervalo minimo entre jornadas em "HH:mm". ⛔ NAO "corrigir" para boolean com base no PDF: o payload e o contrato. Mantido TEXT (nao `time`): e DURACAO, nao horario do dia.';
comment on column secullum."HorarioExtras"."QuantidadeExtrasAutorizadas" is 'Texto "HH:mm" conforme o manual — e DURACAO, nao horario do dia. Mantido TEXT de proposito: o tipo `time` do Postgres nao representa duracao acima de 24h e induziria comparacao errada.';
comment on column secullum."HorarioExtras"."UsarInterjornada" is 'Booleano que liga o uso de "Interjornada". ⚠️ O manual repete, por erro de copia, descricoes de HorariosOpcoes em UsarInterjornada/Interjornada/InterjornadaSeparada. O NOME do campo e o contrato; a descricao do PDF nao e confiavel neste bloco.';
comment on column secullum."HorarioFaixasExtras"."Controle" is 'Enum bruto (Diario=0, Semanal=1, Mensal=2), sem CHECK.';
comment on column secullum."HorarioFaixasExtras"."DiaEspecial" is 'De Domingo(0) a Sabado(6) — ⚠️ TERCEIRA convencao de dia da semana neste schema, diferente das outras duas. Valor bruto do Secullum, sem conversao.';
comment on column secullum."HorarioFaixasExtras"."DiaSemana" is '⚠️⚠️ ENUM COMPLETAMENTE DIFERENTE de "HorarioDia"."DiaSemana", apesar do nome identico (os dois nomes sao literais do Secullum). Aqui: Uteis=0, Sabado=1, Domingo=2, Feriado=3, Folgas=4, Especial=5, NoturnoUteis=6, NoturnoSabado=7, NoturnoDomingo=8, NoturnoFeriado=9, NoturnoFolgas=10, IntervaloUteis=11, IntervaloSabado=12, IntervaloDomingo=13, IntervaloFeriado=14, IntervaloFolgas=15. Em "HorarioDia", "DiaSemana" e 0=Segunda..6=Domingo. Confundir os dois produz erro SILENCIOSO. smallint BRUTO, sem CHECK.';
comment on column secullum."HorarioFaixasExtrasItem"."Coluna" is 'Coluna de extra correspondente. Tipo `Duplo` no manual mesmo parecendo indice inteiro — preservamos `double precision` para nao perder valor fracionario nem falhar na conversao.';
comment on column secullum."HorarioToleranciaEspecifica"."UsaToleranciaEspecifica" is 'Quando true, o motor de deteccao LOGA AVISO e aplica a tolerancia padrao do dia — nunca silencia. A tolerancia especifica e expressa como FAIXA (De/Ate), nao como minutos, e por isso nao e aproximavel pela tolerancia padrao.';
comment on column secullum."HorarioToleranciaEspecificaItem"."DiaSemana" is '⚠️ O manual (pag. 18) declara DiaSemana como "Booleano" com a descricao "Usa tolerancia especifica" — sao dois erros evidentes de copia na tabela oficial. Modelado como smallint (dia da semana), coerente com o payload real. [VALIDAR — Postman] se algum dia houver caso real ativo neste cliente.';
comment on column secullum."HorariosOpcoes"."AlocarBatidas" is 'Numero no payload real; semantica/enum NAO documentados. INTEIRO BRUTO, sem CHECK — mesma disciplina de "HorarioDia"."TipoEntrada1" e de "BatidaFonteDados"."Origem". `integer` (e nao `smallint`) de proposito: sem faixa conhecida, o tipo mais largo evita derrubar a transacao inteira do ciclo por causa de um campo que nenhum consumidor le.';
comment on column secullum."HorariosOpcoes"."AlocarHorario24Horas" is 'Nivel HORARIO. ⚠️ Existe tambem "HorarioDia"."Alocar24Horas", nivel DIA. Sao dois campos distintos do Secullum; o relevante para jornada que cruza a meia-noite e o do dia.';
comment on column secullum."HorariosOpcoes"."Carga" is 'Carga configurada no nivel do HORARIO (acompanha "DefinirCargaAutomaticamente"). ⚠️ NAO confundir com "HorarioDia"."Carga", que e a carga do DIA em minutos e e a unica que interessa a "ha expediente?". Unidade deste campo (minutos vs. horas) nao confirmada; `double precision` para nao truncar valor fracionario nem falhar na conversao.';
comment on column secullum."HorariosOpcoes"."Compensacao" is '⏳ Veio `null` no registro real — TIPO NAO OBSERVADO. Modelado como smallint nullable (enum de modo de compensacao) porque a familia de irmaos booleanos "CompensacaoIgnorar*" implica fortemente um enum de modo. Bruto, sem CHECK.';
comment on column secullum."HorariosOpcoes"."CompensacaoMensalFechamento" is '⏳ Veio `null` no registro real e, ao contrario de "Compensacao", NAO tem contexto que permita inferir o tipo (dia do mes? data? objeto?). jsonb bruto de proposito: `text` transformaria um eventual objeto em "[object Object]" e `smallint` derrubaria a transacao se vier string. Estreitar quando houver exemplo.';
comment on column secullum."HorariosOpcoes"."CompletarBatidasFaltantes" is '⚠️ Opcao de FOLHA do Secullum que preenche batida ausente no calculo dele. ⛔ Isso NAO afeta o que /Batidas devolve a este sistema nem autoriza o motor a "completar" nada: batida faltante continua sendo detectada por slot com "Memoria" e sem hora.';
comment on column secullum."HorariosOpcoes"."HorarioId" is 'Campo `HorarioId` do proprio no (inteiro do Secullum). A FK usada e horario_id (uuid).';
comment on column secullum."HorariosOpcoes"."HorasRepousoFaixas" is '⏳ SHAPE NAO CONFIRMADO. Veio `null` no registro real — nao ha um unico exemplo populado. jsonb BRUTO de proposito: modelar tabela filha exigiria INVENTAR as colunas do item, e este projeto ja quebrou duas vezes em producao por supor estrutura do Secullum sem evidencia. Hipotese NAO confirmada (nao implementar): mesma forma de "HorarioDescansoFaixaItem" { Ordem, Limite, Desconto }. Quando aparecer exemplo populado, promover a tabela filha por migration corretiva. Sem PII: e parametro de horario.';
comment on column secullum."HorariosOpcoes"."LimiteMinimoDeFaltasNoDiaMinutos" is '⚠️ O manual oficial (pag. 11) descreve este campo como "Limite minimo de EXTRAS no dia" e o de extras como "de FALTAS" — as descricoes estao TROCADAS no PDF. Preservamos o NOME do campo, que e o contrato real; ⛔ nao inverter para "corrigir".';
comment on column secullum."HorariosOpcoes"."ListaHorasInItinere" is '⏳ SHAPE NAO CONFIRMADO. Veio `[]` no registro real. jsonb bruto, mesmo racional.';
comment on column secullum."HorariosOpcoes"."ListaHorasSobreAviso" is '⏳ SHAPE NAO CONFIRMADO. Veio `[]` no registro real — a lista existe, o item nunca foi observado. jsonb bruto pelo mesmo racional de "HorasRepousoFaixas". Nao inventar colunas.';
comment on column secullum."HorariosOpcoes"."PeriodoEspecialAdicionalNoturnoInicio" is 'Texto(5) "HH:mm". Mantido TEXT (nao `time`): e configuracao de folha, nunca comparada com hora de batida por este sistema, e converter introduziria risco de fuso sem nenhum ganho.';
comment on column secullum."HorariosOpcoes"."SubstituirBatidasAbaixoDasTolerancias" is '⚠️ Regra de folha que substitui a batida pelo horario previsto quando a diferenca cabe na tolerancia. ⛔ O motor NAO aplica isso — ele compara a hora crua de batida_marcacao.hora com o previsto de "HorarioDia". Ativar essa regra aqui mudaria o numero do relatorio sem mudar o do Secullum.';
comment on column secullum."HorariosOpcoes"."TipoPreencherQuandoDiaEstiverEmBranco" is 'Enum bruto, sem CHECK. Acompanha "PreencherFaltasQuandoDiaEstiverEmBranco". `integer` pelo mesmo motivo de "AlocarBatidas": faixa desconhecida.';
comment on column secullum."HorariosOpcoes"."ToleranciaRefeicoesMinutos" is '⚠️ Tolerancia de REFEICAO — nao confundir com "HorarioDia"."ToleranciaExtra"/"ToleranciaFalta", que sao as unicas que o motor pode usar.';
comment on column secullum.departamento_gestor.funcionarios_observados is 'Sinal de qualidade de cadastro, NÃO dado de produto: quantos funcionários deste departamento apontavam para esta "Estrutura" no ciclo em que a linha foi gravada/atualizada. Nunca usado para eleger titular (proibido eleição por maioria — ADR-013 §4/§4.1) — só contagem para diagnóstico humano.';
comment on column secullum.departamento_gestor.observado_ate is 'Data de DETECÇÃO do fim da vigência (quando ESTA sincronização deixou de observar o vínculo vigente), NUNCA data de negócio. NULL = vigente. Ver ADR-013 §3 — mesma limitação de observado_desde, e mesmo contraste com "FuncionarioAfastamento" (que TEM datas reais de Inicio/Fim vindas do Secullum — não confundir a semântica das duas tabelas).';
comment on column secullum.departamento_gestor.observado_desde is 'Data de DETECÇÃO (quando ESTA sincronização percebeu o vínculo), NUNCA data de negócio — o Secullum não expõe "desde quando fulano é gestor desta unidade". Precisão real: no melhor caso, o intervalo entre execuções do job cadastral; ilimitada se a mudança ocorreu em período sem sincronização. Ver ADR-013 §3.';
comment on column secullum.departamento_gestor.origem is 'secullum_sync (transição detectada pela sincronização normal) | backfill (migração desta tabela a partir de "Estrutura".departamento_id, no deploy da migration 20260821120000) | manual (ajuste do Owner, não usado pelo worker). ⚠️⚠️ CORRIGIDO em 2026-08-24 (ADR-013, 3º adendo) — a versão anterior deste comentário estava ERRADA: dizia que a limitação abaixo valia só para origem = ''backfill'' e só para dado anterior a uma política de "não reaproveitar cadastro de gestor". NENHUMA DAS DUAS PARTES é verdadeira. A troca de titular neste cliente é SEMPRE uma edição de "Estrutura"."Descricao" no MESMO EstruturaId (nunca um EstruturaId novo) — logo NENHUMA linha desta tabela, de QUALQUER origem, identifica a PESSOA que respondia pela unidade: toda linha identifica apenas qual EstruturaId (nó) respondia pelo departamento naquele intervalo. Para saber QUEM ocupava aquele nó, é OBRIGATÓRIO compor com estrutura_evento_titular (ver o comentário daquela tabela e ADR-013 §6 do 3º adendo — "Consulta canônica"). A diferença secullum_sync x backfill continua relevante só quanto à CONFIABILIDADE DA DATA de início do vínculo do nó (observado_desde), nunca quanto à identidade do ocupante.';
comment on column secullum.estrutura_evento_titular.detectado_em is 'Data de DETECÇÃO (quando ESTA sincronização percebeu a mudança), NUNCA data de negócio — mesma limitação e mesmo motivo do nome de departamento_gestor.observado_desde/observado_ate (ADR-013 §3): o Secullum não expõe "desde quando fulano ocupa este nó". Uma cobertura inteiramente contida entre duas execuções do job é invisível para sempre.';
comment on column secullum.estrutura_evento_titular.funcionario_id_anterior is 'Funcionario que a Descricao ANTERIOR resolvia, por match de nome ÚNICO — NULL = 0/ambíguo (nada se afirma). ON DELETE SET NULL (nunca CASCADE): expurgar esta pessoa não pode apagar a transição que documenta o SUCESSOR dela.';
comment on column secullum.estrutura_evento_titular.funcionario_id_novo is 'Funcionario que a Descricao NOVA resolve, por match de nome ÚNICO — NULL = 0/ambíguo. ON DELETE SET NULL pelo mesmo motivo de funcionario_id_anterior.';
comment on column secullum.estrutura_evento_titular.origem is 'secullum_sync (evento detectado pela sincronização normal, fase 3.b) | backfill (carga inicial, sem transição observada) | manual (ajuste do Owner, não usado pelo worker).';
comment on column secullum.estrutura_evento_titular.tipo_evento is 'Classificação pela EVIDÊNCIA observada, nunca por interpretação (ADR-013, 3º adendo, item 4). baseline: primeira observação deste nó, sem estado anterior conhecido. descricao_alterada_mesmo_funcionario: Descricao mudou mas o match de nome (mesmo mecanismo do e-mail do gestor) continua resolvendo para o MESMO Funcionario — correção de grafia/acento, NÃO troca de titular, e é distinguível com segurança (evidência de registro idêntico). descricao_alterada_outro_funcionario: Descricao mudou e o match passou a resolver para OUTRO Funcionario — a MELHOR evidência disponível de troca real, mas evidência, não prova (ver limitação no comentário da tabela: correção de nome ERRADO para o CERTO produz o mesmo sinal). descricao_alterada_indeterminada: Descricao mudou e o match ficou 0/ambíguo em pelo menos um lado — NADA se afirma sobre identidade, só se registra o fato (aviso estrutura_titular_indeterminado). email_alterado: só o e-mail mudou (Descricao igual) — tipicamente correção de contato do MESMO titular, sem indício de troca de pessoa. ⛔ NUNCA classificar por similaridade de string/distância de edição — só identidade de registro de Funcionario por match ÚNICO (mesma régua do ADR-006/ADR-013 item 7).';
