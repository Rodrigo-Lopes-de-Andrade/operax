-- ==========================================================================
-- Baseline REAL — o espelho como ele é em produção, antes da migration 00.
-- GERADO por scripts/gerar_baseline_nuvem.py — não editar à mão.
--
-- Substitui scripts/_test_stub_supabase.sql em scripts/testar_migrations.sh.
-- Sem tenant_id, sem RLS, sem grant: quem aplica isso são as migrations 00 e 03.
-- ==========================================================================

-- Stub local que imita o ambiente Supabase, apenas para testar as migrations.
-- NÃO faz parte do deploy. Uso: banco descartável em CI / máquina local.

-- Roles são cluster-wide: criar só se ainda não existirem (o banco de teste é
-- recriado a cada rodada, os roles não).
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon')          then create role anon          nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role')  then create role service_role  nologin bypassrls; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticator') then create role authenticator noinherit login; end if;
end $$;
grant anon, authenticated, service_role to authenticator;

create schema if not exists auth;
create schema if not exists extensions;
create schema if not exists vault;

create table auth.users (
  id    uuid primary key default gen_random_uuid(),
  email text
);

create or replace function auth.uid() returns uuid
language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;

create or replace function auth.role() returns text
language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claim.role', true), ''), current_user::text);
$$;

grant usage on schema auth, extensions to anon, authenticated, service_role;
grant select on auth.users to authenticated, service_role;

-- Supabase concede tudo em public por padrão — é justamente isso que a
-- migration 00 precisa desfazer.
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables    to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Espelho do Secullum como está HOJE: PascalCase em public, aberto, com PII.
-- ---------------------------------------------------------------------------


-- O espelho do Secullum, ainda em `public` e PascalCase.
create table if not exists public."Batida" (
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
  atualizado_em timestamp with time zone default now() not null
);
create table if not exists public."BatidaFonteDados" (
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
  atualizado_em timestamp with time zone default now() not null
);
create table if not exists public."Cidade" (
  id uuid default gen_random_uuid() not null,
  "CidadeId" integer,
  "Descricao" text not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null
);
create table if not exists public."Departamento" (
  id uuid default gen_random_uuid() not null,
  empresa_id uuid not null,
  "DepartamentoId" integer not null,
  "Descricao" text not null,
  ativo boolean default true not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null,
  "Nfolha" text
);
create table if not exists public."Empresa" (
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
  ativo boolean generated always as (COALESCE((NOT "Desativada"), true)) stored not null
);
create table if not exists public."Estrutura" (
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
  atualizado_em timestamp with time zone default now() not null
);
create table if not exists public."Funcao" (
  id uuid default gen_random_uuid() not null,
  "FuncaoId" integer,
  "Descricao" text not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null
);
create table if not exists public."Funcionario" (
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
  "Foto" bytea,
  foto_sincronizada_em timestamp with time zone,
  foto_tentativa_em timestamp with time zone,
  foto_hash text,
  foto_bytes integer,
  foto_mime text
);
create table if not exists public."FuncionarioAfastamento" (
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
  atualizado_em timestamp with time zone default now() not null
);
create table if not exists public."FuncionarioCentroCusto" (
  id uuid default gen_random_uuid() not null,
  funcionario_id uuid not null,
  "Descricao" text not null,
  criado_em timestamp with time zone default now() not null
);
create table if not exists public."Horario" (
  id uuid default gen_random_uuid() not null,
  "HorarioId" integer not null,
  "Numero" integer,
  "Descricao" text,
  ativo boolean default true not null,
  sincronizado_em timestamp with time zone,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null
);
create table if not exists public."HorarioDescanso" (
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
  atualizado_em timestamp with time zone default now() not null
);
create table if not exists public."HorarioDescansoFaixaItem" (
  id uuid default gen_random_uuid() not null,
  horario_descanso_id uuid not null,
  "Ordem" integer,
  "Limite" text,
  "Desconto" text,
  criado_em timestamp with time zone default now() not null
);
create table if not exists public."HorarioDia" (
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
  atualizado_em timestamp with time zone default now() not null
);
create table if not exists public."HorarioExtras" (
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
  atualizado_em timestamp with time zone default now() not null
);
create table if not exists public."HorarioFaixasExtras" (
  id uuid default gen_random_uuid() not null,
  horario_id uuid not null,
  "HorarioId" integer,
  "DiaSemana" smallint,
  "Controle" smallint,
  "DiaEspecial" smallint,
  criado_em timestamp with time zone default now() not null
);
create table if not exists public."HorarioFaixasExtrasItem" (
  id uuid default gen_random_uuid() not null,
  horario_faixas_extras_id uuid not null,
  "Ordem" integer,
  "Horas" double precision,
  "Coluna" double precision,
  criado_em timestamp with time zone default now() not null
);
create table if not exists public."HorarioToleranciaEspecifica" (
  id uuid default gen_random_uuid() not null,
  horario_id uuid not null,
  "UsaToleranciaEspecifica" boolean default false not null,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null
);
create table if not exists public."HorarioToleranciaEspecificaItem" (
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
  criado_em timestamp with time zone default now() not null
);
create table if not exists public."HorariosOpcoes" (
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
  atualizado_em timestamp with time zone default now() not null
);
create table if not exists public.batida_marcacao (
  id uuid default gen_random_uuid() not null,
  batida_id uuid not null,
  funcionario_id uuid not null,
  data date not null,
  tipo_coluna text not null,
  indice_coluna smallint not null,
  valor_bruto text,
  hora time without time zone,
  status_rotulo text,
  "Memoria" time without time zone,
  "EquipId" integer,
  "FonteDadosId" bigint,
  desconsiderada boolean default false not null,
  sincronizado_em timestamp with time zone default now() not null,
  criado_em timestamp with time zone default now() not null,
  atualizado_em timestamp with time zone default now() not null
);
create table if not exists public.cursor_sincronizacao (
  chave text not null,
  valor text,
  atualizado_em timestamp with time zone default now() not null
);
create table if not exists public.empresa_evento_status (
  id uuid default gen_random_uuid() not null,
  empresa_id uuid not null,
  tipo_evento text not null,
  ativo_anterior boolean,
  ativo_novo boolean not null,
  detectado_em timestamp with time zone default now() not null,
  origem text default 'secullum_sync'::text not null,
  criado_em timestamp with time zone default now() not null
);
create table if not exists public.funcionario_evento_status (
  id uuid default gen_random_uuid() not null,
  funcionario_id uuid not null,
  tipo_evento text not null,
  ativo_anterior boolean,
  ativo_novo boolean not null,
  data_evento date,
  admissao_anterior date,
  admissao_nova date,
  demissao_anterior date,
  demissao_nova date,
  detectado_em timestamp with time zone default now() not null,
  origem text default 'secullum_sync'::text not null,
  criado_em timestamp with time zone default now() not null
);

-- constraints (as que a 03 recria ficam de fora)
alter table public.batida_marcacao add constraint batida_marcacao_pkey PRIMARY KEY (id);
alter table public.cursor_sincronizacao add constraint cursor_sincronizacao_pkey PRIMARY KEY (chave);
alter table public.empresa_evento_status add constraint empresa_evento_status_pkey PRIMARY KEY (id);
alter table public.funcionario_evento_status add constraint funcionario_evento_status_pkey PRIMARY KEY (id);
alter table public."Batida" add constraint "Batida_pkey" PRIMARY KEY (id);
alter table public."BatidaFonteDados" add constraint "BatidaFonteDados_pkey" PRIMARY KEY (id);
alter table public."Cidade" add constraint "Cidade_pkey" PRIMARY KEY (id);
alter table public."Departamento" add constraint departamento_pkey PRIMARY KEY (id);
alter table public."Empresa" add constraint empresa_pkey PRIMARY KEY (id);
alter table public."Estrutura" add constraint estrutura_pkey PRIMARY KEY (id);
alter table public."Funcao" add constraint "Funcao_pkey" PRIMARY KEY (id);
alter table public."Funcionario" add constraint funcionario_pkey PRIMARY KEY (id);
alter table public."FuncionarioAfastamento" add constraint funcionario_afastamento_pkey PRIMARY KEY (id);
alter table public."FuncionarioCentroCusto" add constraint "FuncionarioCentroCusto_pkey" PRIMARY KEY (id);
alter table public."Horario" add constraint horario_pkey PRIMARY KEY (id);
alter table public."HorarioDescanso" add constraint "HorarioDescanso_pkey" PRIMARY KEY (id);
alter table public."HorarioDescansoFaixaItem" add constraint "HorarioDescansoFaixaItem_pkey" PRIMARY KEY (id);
alter table public."HorarioDia" add constraint horario_dia_pkey PRIMARY KEY (id);
alter table public."HorarioExtras" add constraint "HorarioExtras_pkey" PRIMARY KEY (id);
alter table public."HorarioFaixasExtras" add constraint "HorarioFaixasExtras_pkey" PRIMARY KEY (id);
alter table public."HorarioFaixasExtrasItem" add constraint "HorarioFaixasExtrasItem_pkey" PRIMARY KEY (id);
alter table public."HorarioToleranciaEspecifica" add constraint "HorarioToleranciaEspecifica_pkey" PRIMARY KEY (id);
alter table public."HorarioToleranciaEspecificaItem" add constraint "HorarioToleranciaEspecificaItem_pkey" PRIMARY KEY (id);
alter table public."HorariosOpcoes" add constraint "HorariosOpcoes_pkey" PRIMARY KEY (id);
alter table public.batida_marcacao add constraint batida_marcacao_posicao_key UNIQUE (batida_id, tipo_coluna, indice_coluna);
alter table public."Batida" add constraint batida_funcionario_id_data_key UNIQUE (funcionario_id, "Data");
alter table public."BatidaFonteDados" add constraint batida_fonte_dados_marcacao_key UNIQUE (batida_marcacao_id);
alter table public."Cidade" add constraint cidade_descricao_key UNIQUE ("Descricao");
alter table public."Departamento" add constraint departamento_departamentoid_key UNIQUE ("DepartamentoId");
alter table public."Empresa" add constraint empresa_documento_key UNIQUE ("Documento");
alter table public."Estrutura" add constraint estrutura_estruturaid_key UNIQUE ("EstruturaId");
alter table public."Funcao" add constraint funcao_descricao_key UNIQUE ("Descricao");
alter table public."Funcionario" add constraint funcionario_funcionarioid_key UNIQUE ("FuncionarioId");
alter table public."FuncionarioAfastamento" add constraint funcionario_afastamento_funcionario_afastamentoid_key UNIQUE (funcionario_id, "AfastamentoId");
alter table public."FuncionarioCentroCusto" add constraint funcionario_centro_custo_key UNIQUE (funcionario_id, "Descricao");
alter table public."Horario" add constraint horario_horarioid_key UNIQUE ("HorarioId");
alter table public."HorarioDescanso" add constraint horario_descanso_horario_id_key UNIQUE (horario_id);
alter table public."HorarioDia" add constraint horario_dia_horario_id_diasemana_key UNIQUE (horario_id, "DiaSemana");
alter table public."HorarioExtras" add constraint horario_extras_horario_id_key UNIQUE (horario_id);
alter table public."HorarioToleranciaEspecifica" add constraint horario_tolerancia_especifica_horario_id_key UNIQUE (horario_id);
alter table public."HorariosOpcoes" add constraint horarios_opcoes_horario_id_key UNIQUE (horario_id);
alter table public.batida_marcacao add constraint batida_marcacao_indice_coluna_check CHECK (((indice_coluna >= 1) AND (indice_coluna <= 5)));
alter table public.batida_marcacao add constraint batida_marcacao_tipo_coluna_check CHECK ((tipo_coluna = ANY (ARRAY['Entrada'::text, 'Saida'::text])));
alter table public.empresa_evento_status add constraint empresa_evento_status_baseline_check CHECK (((tipo_evento = 'baseline'::text) = (ativo_anterior IS NULL)));
alter table public.empresa_evento_status add constraint empresa_evento_status_direcao_check CHECK ((((tipo_evento = 'deactivated'::text) AND (ativo_novo = false)) OR ((tipo_evento = 'reactivated'::text) AND (ativo_novo = true)) OR (tipo_evento = 'baseline'::text)));
alter table public.empresa_evento_status add constraint empresa_evento_status_mudanca_check CHECK (((tipo_evento = 'baseline'::text) OR (ativo_anterior IS DISTINCT FROM ativo_novo)));
alter table public.empresa_evento_status add constraint empresa_evento_status_origem_check CHECK ((origem = ANY (ARRAY['secullum_sync'::text, 'backfill'::text, 'manual'::text])));
alter table public.empresa_evento_status add constraint empresa_evento_status_tipo_evento_check CHECK ((tipo_evento = ANY (ARRAY['baseline'::text, 'deactivated'::text, 'reactivated'::text])));
alter table public.funcionario_evento_status add constraint funcionario_evento_status_admissao_data_check CHECK (((tipo_evento <> 'admission'::text) OR (NOT (data_evento IS DISTINCT FROM admissao_nova))));
alter table public.funcionario_evento_status add constraint funcionario_evento_status_baseline_check CHECK (((tipo_evento = 'baseline'::text) = (ativo_anterior IS NULL)));
alter table public.funcionario_evento_status add constraint funcionario_evento_status_correcao_check CHECK (((tipo_evento <> 'date_correction'::text) OR (ativo_anterior = ativo_novo)));
alter table public.funcionario_evento_status add constraint funcionario_evento_status_demissao_data_check CHECK (((tipo_evento <> 'termination'::text) OR (NOT (data_evento IS DISTINCT FROM demissao_nova))));
alter table public.funcionario_evento_status add constraint funcionario_evento_status_direcao_check CHECK (((tipo_evento = ANY (ARRAY['baseline'::text, 'date_correction'::text])) OR ((tipo_evento = 'admission'::text) AND (ativo_novo = true)) OR ((tipo_evento = 'termination'::text) AND (ativo_novo = false)) OR ((tipo_evento = 'reactivation'::text) AND (ativo_novo = true))));
alter table public.funcionario_evento_status add constraint funcionario_evento_status_mudanca_check CHECK (((tipo_evento = 'baseline'::text) OR (ativo_anterior IS DISTINCT FROM ativo_novo) OR ((tipo_evento = 'date_correction'::text) AND ((admissao_anterior IS DISTINCT FROM admissao_nova) OR (demissao_anterior IS DISTINCT FROM demissao_nova)))));
alter table public.funcionario_evento_status add constraint funcionario_evento_status_origem_check CHECK ((origem = ANY (ARRAY['secullum_sync'::text, 'backfill'::text, 'manual'::text])));
alter table public.funcionario_evento_status add constraint funcionario_evento_status_tipo_evento_check CHECK ((tipo_evento = ANY (ARRAY['baseline'::text, 'admission'::text, 'termination'::text, 'reactivation'::text, 'date_correction'::text])));
alter table public."Estrutura" add constraint estrutura_canais_notificacao_check CHECK ((canais_notificacao <@ ARRAY['whatsapp'::text, 'email'::text]));
alter table public."Estrutura" add constraint estrutura_email_origem_check CHECK ((email_origem = ANY (ARRAY['manual'::text, 'secullum'::text])));
alter table public."FuncionarioAfastamento" add constraint funcionario_afastamento_correlacionado_por_check CHECK ((correlacionado_por = ANY (ARRAY['pis'::text, 'cpf'::text])));
alter table public."HorarioDia" add constraint horario_dia_diasemana_check CHECK ((("DiaSemana" >= 0) AND ("DiaSemana" <= 6)));
alter table public.batida_marcacao add constraint batida_marcacao_batida_id_fkey FOREIGN KEY (batida_id) REFERENCES public."Batida"(id) ON DELETE CASCADE;
alter table public.batida_marcacao add constraint batida_marcacao_funcionario_id_fkey FOREIGN KEY (funcionario_id) REFERENCES public."Funcionario"(id) ON DELETE CASCADE;
alter table public.empresa_evento_status add constraint empresa_evento_status_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public."Empresa"(id) ON DELETE CASCADE;
alter table public.funcionario_evento_status add constraint funcionario_evento_status_funcionario_id_fkey FOREIGN KEY (funcionario_id) REFERENCES public."Funcionario"(id) ON DELETE CASCADE;
alter table public."Batida" add constraint "Batida_funcionario_id_fkey" FOREIGN KEY (funcionario_id) REFERENCES public."Funcionario"(id) ON DELETE CASCADE;
alter table public."BatidaFonteDados" add constraint "BatidaFonteDados_batida_id_fkey" FOREIGN KEY (batida_id) REFERENCES public."Batida"(id) ON DELETE CASCADE;
alter table public."BatidaFonteDados" add constraint "BatidaFonteDados_batida_marcacao_id_fkey" FOREIGN KEY (batida_marcacao_id) REFERENCES public.batida_marcacao(id) ON DELETE CASCADE;
alter table public."Departamento" add constraint departamento_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public."Empresa"(id);
alter table public."Empresa" add constraint "Empresa_cidade_id_fkey" FOREIGN KEY (cidade_id) REFERENCES public."Cidade"(id);
alter table public."Funcionario" add constraint "Funcionario_cidade_id_fkey" FOREIGN KEY (cidade_id) REFERENCES public."Cidade"(id);
alter table public."Funcionario" add constraint "Funcionario_funcao_id_fkey" FOREIGN KEY (funcao_id) REFERENCES public."Funcao"(id);
alter table public."Funcionario" add constraint funcionario_afastamento_atual_id_fkey FOREIGN KEY (afastamento_atual_id) REFERENCES public."FuncionarioAfastamento"(id) ON DELETE SET NULL;
alter table public."Funcionario" add constraint funcionario_departamento_id_fkey FOREIGN KEY (departamento_id) REFERENCES public."Departamento"(id);
alter table public."Funcionario" add constraint funcionario_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public."Empresa"(id);
alter table public."Funcionario" add constraint funcionario_horario_id_fkey FOREIGN KEY (horario_id) REFERENCES public."Horario"(id);
alter table public."FuncionarioAfastamento" add constraint funcionario_afastamento_funcionario_id_fkey FOREIGN KEY (funcionario_id) REFERENCES public."Funcionario"(id) ON DELETE CASCADE;
alter table public."FuncionarioCentroCusto" add constraint "FuncionarioCentroCusto_funcionario_id_fkey" FOREIGN KEY (funcionario_id) REFERENCES public."Funcionario"(id) ON DELETE CASCADE;
alter table public."HorarioDescanso" add constraint "HorarioDescanso_horario_id_fkey" FOREIGN KEY (horario_id) REFERENCES public."Horario"(id) ON DELETE CASCADE;
alter table public."HorarioDescansoFaixaItem" add constraint "HorarioDescansoFaixaItem_horario_descanso_id_fkey" FOREIGN KEY (horario_descanso_id) REFERENCES public."HorarioDescanso"(id) ON DELETE CASCADE;
alter table public."HorarioDia" add constraint horario_dia_horario_id_fkey FOREIGN KEY (horario_id) REFERENCES public."Horario"(id) ON DELETE CASCADE;
alter table public."HorarioExtras" add constraint "HorarioExtras_horario_id_fkey" FOREIGN KEY (horario_id) REFERENCES public."Horario"(id) ON DELETE CASCADE;
alter table public."HorarioFaixasExtras" add constraint "HorarioFaixasExtras_horario_id_fkey" FOREIGN KEY (horario_id) REFERENCES public."Horario"(id) ON DELETE CASCADE;
alter table public."HorarioFaixasExtrasItem" add constraint "HorarioFaixasExtrasItem_horario_faixas_extras_id_fkey" FOREIGN KEY (horario_faixas_extras_id) REFERENCES public."HorarioFaixasExtras"(id) ON DELETE CASCADE;
alter table public."HorarioToleranciaEspecifica" add constraint "HorarioToleranciaEspecifica_horario_id_fkey" FOREIGN KEY (horario_id) REFERENCES public."Horario"(id) ON DELETE CASCADE;
alter table public."HorarioToleranciaEspecificaItem" add constraint "HorarioToleranciaEspecificaIt_horario_tolerancia_especific_fkey" FOREIGN KEY (horario_tolerancia_especifica_id) REFERENCES public."HorarioToleranciaEspecifica"(id) ON DELETE CASCADE;
alter table public."HorariosOpcoes" add constraint "HorariosOpcoes_horario_id_fkey" FOREIGN KEY (horario_id) REFERENCES public."Horario"(id) ON DELETE CASCADE;

-- índices
CREATE INDEX batida_marcacao_fontedadosid_idx ON public.batida_marcacao USING btree ("FonteDadosId");
CREATE INDEX batida_marcacao_funcionario_id_data_idx ON public.batida_marcacao USING btree (funcionario_id, data);
CREATE INDEX batida_marcacao_hora_idx ON public.batida_marcacao USING btree (funcionario_id, data) WHERE (hora IS NOT NULL);
CREATE UNIQUE INDEX empresa_evento_status_baseline_uniq ON public.empresa_evento_status USING btree (empresa_id) WHERE (tipo_evento = 'baseline'::text);
CREATE INDEX empresa_evento_status_empresa_detectado_idx ON public.empresa_evento_status USING btree (empresa_id, detectado_em DESC);
CREATE UNIQUE INDEX funcionario_evento_status_baseline_uniq ON public.funcionario_evento_status USING btree (funcionario_id) WHERE (tipo_evento = 'baseline'::text);
CREATE INDEX funcionario_evento_status_funcionario_data_evento_idx ON public.funcionario_evento_status USING btree (funcionario_id, data_evento);
CREATE INDEX funcionario_evento_status_funcionario_detectado_idx ON public.funcionario_evento_status USING btree (funcionario_id, detectado_em DESC);
CREATE INDEX batida_batidaid_idx ON public."Batida" USING btree ("BatidaId");
CREATE INDEX batida_data_idx ON public."Batida" USING btree ("Data");
CREATE INDEX batida_fonte_dados_batida_id_idx ON public."BatidaFonteDados" USING btree (batida_id);
CREATE INDEX batida_fonte_dados_fontedadosid_idx ON public."BatidaFonteDados" USING btree ("FonteDadosId");
CREATE INDEX "Departamento_empresa_id_fkidx" ON public."Departamento" USING btree (empresa_id);
CREATE INDEX empresa_cidade_id_idx ON public."Empresa" USING btree (cidade_id);
CREATE INDEX empresa_empresaid_idx ON public."Empresa" USING btree ("EmpresaId");
CREATE INDEX "Funcionario_afastamento_atual_id_fkidx" ON public."Funcionario" USING btree (afastamento_atual_id);
CREATE INDEX "Funcionario_departamento_id_fkidx" ON public."Funcionario" USING btree (departamento_id);
CREATE INDEX "Funcionario_empresa_id_fkidx" ON public."Funcionario" USING btree (empresa_id);
CREATE INDEX "Funcionario_horario_id_fkidx" ON public."Funcionario" USING btree (horario_id);
CREATE INDEX funcionario_afastado_hoje_idx ON public."Funcionario" USING btree (afastado_hoje) WHERE (afastado_hoje = true);
CREATE INDEX funcionario_cidade_id_idx ON public."Funcionario" USING btree (cidade_id);
CREATE INDEX funcionario_foto_fila_idx ON public."Funcionario" USING btree (foto_tentativa_em NULLS FIRST) WHERE "PossuiFoto";
CREATE INDEX funcionario_funcao_id_idx ON public."Funcionario" USING btree (funcao_id);
CREATE INDEX funcionario_afastamento_funcionario_janela_idx ON public."FuncionarioAfastamento" USING btree (funcionario_id, "Inicio", "Fim");
CREATE INDEX funcionario_afastamento_janela_idx ON public."FuncionarioAfastamento" USING btree ("Fim", "Inicio");
CREATE INDEX funcionario_centro_custo_funcionario_id_idx ON public."FuncionarioCentroCusto" USING btree (funcionario_id);
CREATE INDEX horario_descanso_faixa_item_pai_idx ON public."HorarioDescansoFaixaItem" USING btree (horario_descanso_id);
CREATE INDEX horario_dia_horariodiaid_idx ON public."HorarioDia" USING btree ("HorarioDiaId");
CREATE INDEX horario_faixas_extras_horario_id_idx ON public."HorarioFaixasExtras" USING btree (horario_id);
CREATE INDEX horario_faixas_extras_item_pai_idx ON public."HorarioFaixasExtrasItem" USING btree (horario_faixas_extras_id);
CREATE INDEX horario_tolerancia_especifica_item_pai_idx ON public."HorarioToleranciaEspecificaItem" USING btree (horario_tolerancia_especifica_id);

-- comentários (é onde mora o que se aprendeu do payload do Secullum)
comment on table public.batida_marcacao is 'TABELA NOSSA (minusculo, ADR-012): e a TRANSPOSICAO de uma coluna do registro-dia (Entrada1..Entrada5 / Saida1..Saida5) em linha. ⛔ NAO procure "Marcacao" no payload do Secullum — nao existe. Identidade POSICIONAL: (batida_id, tipo_coluna, indice_coluna) — nunca por FonteDadosId, que e nullable e portanto nao e chave (ADR-007). ⚠️ Escrita OBRIGATORIA por substituicao do dia inteiro em transacao: upsert das colunas presentes + DELETE das que deixaram de existir. Sem o DELETE, uma batida removida no Secullum sobrevive para sempre no cache e continua gerando desvio.';
comment on table public.cursor_sincronizacao is 'Controle de sincronizacao com o Secullum. TABELA 100% NOSSA — nao tem equivalente no Secullum, por isso nome e colunas em minusculo (regra do caso, ADR-012). Ver docs/04-modelo-dados.md.';
comment on table public.empresa_evento_status is 'TABELA 100% NOSSA (por isso tudo em minusculo) — historico APPEND-ONLY de mudancas de "Empresa".ativo. ⚠️⚠️ NAO EXISTE DATA REAL DE EVENTO AQUI: o Secullum entrega apenas `Empresa.Desativada` (boolean de estado atual). A unica data e detectado_em (quando a sincronizacao percebeu) e a ausencia de uma coluna de data de evento e PROPOSITAL. Contraste obrigatorio com funcionario_evento_status, que TEM data real. Ver ADR-009.';
comment on table public.funcionario_evento_status is 'TABELA 100% NOSSA (minusculo) — historico APPEND-ONLY de mudancas de vinculo ("Funcionario".ativo). ✅ AQUI EXISTE data real de evento (data_evento, de `Admissao`/`Demissao`). data_evento e detectado_em divergem legitimamente. Ver ADR-009 e docs/04-modelo-dados.md.';
comment on table public."Batida" is 'Registro-dia de ponto: UM item de GET /Batidas = um par (funcionario x data) com ate 5 pares Entrada/Saida em COLUNAS. NAO e uma batida individual — essa e batida_marcacao. Ver ADR-007 e ADR-011.';
comment on table public."BatidaFonteDados" is 'Objeto `FonteDados` aninhado em cada coluna de /Batidas — ate 10 por registro-dia (FonteDadosEntrada1..5 / FonteDadosSaida1..5). Nome composto: o prefixo "Batida" e NOSSO (agrupamento na listagem de tabelas); "FonteDados" e o tipo literal do Secullum, e cada linha E um desses objetos. 1:1 OPCIONAL com batida_marcacao: existe coluna preenchida SEM FonteDados (buraco conhecido, ADR-007).';
comment on table public."Cidade" is 'Cidade — no aninhado { Id, Descricao } em Funcionario e em Empresa. Forma confirmada em 2026-08-13. Ver ADR-011.';
comment on table public."Departamento" is 'Departamento = unidade de estacionamento. Espelha o no `Funcionario.Departamento { Id, Descricao, Nfolha }`; a rota standalone GET /Departamentos NAO e chamada. Ver ADR-006 e ADR-008.';
comment on table public."Empresa" is 'Empresa (agrupador) — espelha o no `Funcionario.Empresa` aninhado em /Funcionarios. ⚠️ ATENCAO AO ALCANCE REAL DOS CAMPOS: o no aninhado confirmado traz { Id, Nome, Documento, Desativada, ... }. As demais colunas vem do CADASTRO DE EMPRESAS do manual (rota GET /Empresas, que este projeto NAO chama) e podem permanecer NULAS para sempre. Elas existem porque o Owner pediu captura completa (ADR-011); nenhuma delas tem consumidor de produto hoje. Ver ADR-006, ADR-011 e ADR-012.';
comment on table public."Estrutura" is '⚠️ LEIA O CABECALHO DA SECAO 6 DE 20260813160000_rename_schema_secullum.sql ANTES DE MEXER AQUI. Esta tabela espelha o OBJETO ANINHADO `Funcionario.Estrutura` de /Funcionarios — NAO a rota standalone GET /Estruturas, que foi DESCARTADA pelo ADR-006 e nao e chamada em nenhum fluxo. Papel de negocio: e o GESTOR responsavel pelo(s) departamento(s); "Descricao" e o NOME dele. Origem hibrida: "Descricao"/"EstruturaPaiId" vem do Secullum; email vem por match de nome dentro do proprio /Funcionarios (com protecao via email_origem); whatsapp e canais_notificacao sao SEMPRE cadastro manual do Owner. ⚠️ NAO confundir com "Empresa"."ResponsavelNome" (responsavel LEGAL da empresa, outra pessoa). Ver docs/03-integracao-secullum.md ("Resolucao do gestor").';
comment on table public."Funcao" is 'Funcao/cargo do funcionario. Populada a partir do no aninhado em /Funcionarios — a rota standalone GET /Funcoes NAO e chamada (escopo de 5 endpoints, docs/03-integracao-secullum.md).';
comment on table public."Funcionario" is 'Funcionario. ⚠️ A partir de 2026-08-13 (ADR-011) esta tabela deixou de ser um "cache minimo" e passa a guardar TODO o cadastro devolvido por /Funcionarios, incluindo PII sensivel (RG, endereco, telefone, celular, e-mail, filiacao, nascimento). A minimizacao anterior foi REVERTIDA por decisao expressa do Owner. A base legal formal para essa retencao continua PENDENTE — ver docs/06-seguranca-lgpd.md.';
comment on table public."FuncionarioAfastamento" is 'Periodos (JANELAS) de afastamento/ferias — fonte: GET /IntegracaoExterna/FuncionariosAfastamentos. Nome escolhido a partir do nome da rota (o manual nao nomeia um tipo para o item) — ver secao 10 da migration 20260813160000. NAO confundir com funcionario_evento_status (transicoes de vinculo): o funcionario continua ativo = true durante ferias. Tabela MUTAVEL (upsert + DELETE de convergencia), ao contrario das tabelas *_evento_status, que sao append-only. Ver ADR-010.';
comment on table public."FuncionarioCentroCusto" is 'Centros de custo do funcionario (`ListaCentroDeCustos`, array de { Descricao } em /Funcionarios). ON DELETE CASCADE sustenta o expurgo por titular (docs/06-seguranca-lgpd.md). Escrita por substituicao integral por funcionario.';
comment on table public."Horario" is 'Horario (grade prevista) — espelha `Horario` de GET /Horarios (chamada sem parametro). Ver docs/04-modelo-dados.md.';
comment on table public."HorarioDescanso" is 'No `Horario.Descanso` (tipo `HorarioDescanso`, regras de DSR) — 1:1 com "Horario". Estrutura bate com o manual (confirmado em 2026-08-13). Regras de folha: capturadas, ⛔ NAO consumidas pelo motor.';
comment on table public."HorarioDescansoFaixaItem" is 'Itens de `Descanso.Faixas` (tipo `HorarioDescansoFaixaItem`: { Ordem, Limite, Desconto }). SEM chave unica de negocio de proposito: escrita por SUBSTITUICAO INTEGRAL do conjunto por "HorarioDescanso", dentro da transacao do ciclo. Nenhum item tem id estavel na origem.';
comment on table public."HorarioDia" is 'Grade por dia da semana. Um registro por item de `Horario.Dias[]`. Nome COMPOSTO por nos (`Horario` + `Dia`): o manual do Secullum nao nomeia um tipo para o item do array.';
comment on table public."HorarioExtras" is 'No `Horario.Extras` (tipo `HorarioExtras`). 1:1 com "Horario". ✅ ESTRUTURA FECHADA em 2026-08-13 contra a conta real: 31 campos incluindo "HorarioId" — nao 7 (manual) nem ~15 (estimativa). Regras de folha, capturadas mas ⛔ NAO usadas pelo motor de deteccao. Ver ADR-011.';
comment on table public."HorarioFaixasExtras" is 'No `Horario.FaixasExtras` (tipo `HorarioFaixasExtras`) — 1:N por horario, uma linha por "Dia Semana" do enum. Escrita por substituicao integral. Regras de folha: capturadas, ⛔ NAO consumidas pelo motor.';
comment on table public."HorarioFaixasExtrasItem" is 'Itens de `FaixasExtras.Faixas` (tipo `HorarioFaixasExtrasItem`). Escrita por substituicao integral junto com o pai. Sem chave unica de negocio — nenhum id estavel na origem.';
comment on table public."HorarioToleranciaEspecifica" is 'No `Horario.ToleranciaEspecifica` (SINGULAR, confirmado no payload real; tipo `HorarioToleranciaEspecifica` no manual) — 1:1 com "Horario". Em todos os registros ja inspecionados veio false / lista vazia: nao ha nenhum caso real ativo neste cliente.';
comment on table public."HorarioToleranciaEspecificaItem" is 'Itens de `ToleranciaEspecifica.Tolerancias` (tipo `HorarioToleranciaEspecificaItem`). Escrita por substituicao integral junto com o pai.';
comment on table public."HorariosOpcoes" is 'No `Horario.Opcoes` (tipo `HorariosOpcoes` no manual — plural no `Horarios` e literal, nao erro). 1:1 com "Horario". ✅ ESTRUTURA FECHADA em 2026-08-13 contra a conta real (inspecao GET-only, so nomes de campo e tipo, zero valores): 54 campos incluindo "HorarioId" — nao 21 (manual) nem ~35 (estimativa). REGRAS DE CALCULO DE FOLHA: capturadas para consulta/auditoria, ⛔ NAO consumidas pelo motor de deteccao. Ver ADR-011.';
comment on column public.batida_marcacao."EquipId" is 'Campo `EquipIdEntradaN`/`EquipIdSaidaN`, des-posicionalizado. Id do equipamento/relogio que originou a coluna. Inteiro bruto, sem FK — o cadastro de equipamentos do Secullum nao e consumido.';
comment on column public.batida_marcacao."FonteDadosId" is 'Campo `FonteDadosIdEntradaN`/`SaidaN`, des-posicionalizado (o escalar do payload). ATRIBUTO, indice NAO-UNICO: confirmado em dados reais que uma coluna preenchida, inclusive vinda de relogio fisico ("EquipId" presente), pode ter este id nulo. Chave que as vezes e nula nao e chave.';
comment on column public.batida_marcacao."Memoria" is 'Campo `MemoriaEntradaN`/`MemoriaSaidaN`, DES-POSICIONALIZADO (o sufixo virou tipo_coluna/indice_coluna). Horario PREVISTO daquele dia, atalho de diagnostico. ⛔ NAO e a fonte da verdade do previsto nem da tolerancia: isso e "HorarioDia". Inverter essa ordem faz o sistema divergir do calculo oficial de folha. ✅ E o sinal de BATIDA FALTANTE quando "Memoria" existe e `hora` e nula.';
comment on column public.batida_marcacao.data is 'NOSSA, desnormalizada de "Batida"."Data" (por isso minuscula). Mesma finalidade de funcionario_id.';
comment on column public.batida_marcacao.desconsiderada is 'NOSSO (derivado de "BatidaFonteDados"."Tipo" = 3, Desconsiderado). A marcacao E persistida (para o reprocessamento nao oscilar e por rastreabilidade), mas nao gera desvio.';
comment on column public.batida_marcacao.funcionario_id is 'NOSSA FK, desnormalizada a partir de "Batida" de proposito (mesmo racional de "Funcionario".empresa_id): evita um join no caminho quente do relatorio (Sprint 3) e do dashboard (Sprint 4). Coerencia com "Batida" e responsabilidade da mesma transacao de escrita — so o job escreve aqui.';
comment on column public.batida_marcacao.hora is 'NOSSO (derivado). Preenchida SOMENTE quando valor_bruto e "HH:mm". Hora LOCAL (America/Sao_Paulo), armazenada sem conversao de fuso. Mutuamente exclusiva com status_rotulo. ⚠️ Linha com hora IS NULL NAO e batida: nao entra na deteccao e nao entra no denominador do KPI de batidas do dashboard.';
comment on column public.batida_marcacao.tipo_coluna is 'NOSSO. Valores ''Entrada'' | ''Saida'' — grafados exatamente como o PREFIXO da coluna no payload, de modo que tipo_coluna || indice_coluna reconstroi o nome literal do campo ("Entrada3").';
comment on column public.batida_marcacao.valor_bruto is 'NOSSO. Conteudo literal da coluna `EntradaN`/`SaidaN`, preservado como veio. Tres estados possiveis: "HH:mm" (batida), TEXTO DE STATUS (ex.: "Ferias") ou null. E a unica coluna que garante fidelidade ao payload — `hora` e `status_rotulo` sao interpretacoes dela.';
comment on column public.cursor_sincronizacao.atualizado_em is 'Momento da ultima atualizacao do cursor.';
comment on column public.cursor_sincronizacao.chave is 'Identificador logico do cursor (ex.: batidas_ultima_data_sincronizada).';
comment on column public.cursor_sincronizacao.valor is 'Valor do cursor em texto. Para /Batidas guarda a ultima DATA coberta pela janela deslizante, nao um ID.';
comment on column public.empresa_evento_status.detectado_em is 'Quando ESTA sincronizacao detectou a mudanca. NAO e quando a empresa foi desativada no Secullum (essa informacao nao existe na API). Erro >= intervalo entre execucoes do job; ilimitado se o job esteve parado.';
comment on column public.empresa_evento_status.origem is 'secullum_sync (job cadastral) | backfill (esta migration, para linhas ja existentes) | manual.';
comment on column public.empresa_evento_status.tipo_evento is 'baseline (primeira vez que a empresa foi observada; previous_active nulo) | deactivated | reactivated.';
comment on column public.funcionario_evento_status.data_evento is 'Data REAL do Secullum (`Admissao` em admission, `Demissao` em termination). NULL quando o evento nao tem data de origem. Para reconstruir estado historico: coalesce(data_evento, detectado_em::date).';
comment on column public.funcionario_evento_status.detectado_em is 'Quando a sincronizacao percebeu a mudanca. Pode ser POSTERIOR a event_date — ex.: desligamento com Demissao no dia 01 so detectado na execucao do dia 02. Isso e esperado.';
comment on column public.funcionario_evento_status.origem is 'secullum_sync (job cadastral) | backfill (esta migration, para linhas ja existentes) | manual.';
comment on column public.funcionario_evento_status.tipo_evento is 'baseline (primeira observacao) | admission (passou a ativo por admissao) | termination (passou a inativo por demissao) | reactivation (voltou a ativo sem nova admissao, ex.: Demissao corrigida para null) | date_correction (Admissao/Demissao mudou sem virar o status, inclusive desligamento programado para data futura).';
comment on column public."Batida"."Ajuste" is '[VALIDAR — Postman] Tipo real desconhecido (o cadastro de Justificativas trata Ajuste/Abono2..4 como boolean de abono automatico; no cartao ponto sao valores HH:mm). Modelado como TEXT para preservar o valor bruto sem risco de conversao errada. Mesma ressalva para "Abono2"/"Abono3"/"Abono4".';
comment on column public."Batida"."BatidaId" is 'Campo `Id` do topo do registro de /Batidas (forma qualificada, ver ADR-012). ATRIBUTO com indice NAO-UNICO — NAO e a chave de idempotencia (alteracao (A) ao ADR-007). A chave e (funcionario_id, "Data"), unica por construcao. Divergencia entre os dois (mesmo par funcionario/data reaparecendo com outro Id) deve ser LOGADA como anomalia, nunca contornada em silencio.';
comment on column public."Batida"."Data" is 'Campo `Data`. ⛔ Parsing OBRIGATORIO pelos 10 PRIMEIROS CARACTERES da string ("yyyy-MM-ddT00:00:00"). Nunca via new Date(...)/toISOString(): a Edge Function roda em UTC e a conversao ingenua desloca um dia. A parte de hora do campo e sempre 00:00:00 e nao tem significado.';
comment on column public."Batida"."FuncionarioId" is 'Campo `FuncionarioId` do payload — INTEIRO do Secullum, guardado como veio. E a chave de juncao com "Funcionario"."FuncionarioId". ⚠️ A FK real e funcionario_id (uuid), ao lado.';
comment on column public."Batida"."NBanco" is 'Campo `NBanco` (banco de horas do dia). ✅ Sob a nomenclatura literal (ADR-012) a abreviacao opaca deixou de ser um problema de decisao nossa: e simplesmente o nome que o Secullum usa.';
comment on column public."Batida"."Observacoes" is '⚠️ TEXTO LIVRE. Ate 2026-08-12 era explicitamente NAO sincronizado por LGPD (podia carregar motivo de afastamento = dado de saude). Passa a ser persistido por decisao expressa do Owner (ADR-011). ⛔ Nunca exibir em relatorio ao gestor, nunca logar. A base legal para reter isto esta PENDENTE.';
comment on column public."Batida".status_dia_rotulo is 'DERIVADO POR NOS (minusculo — nao procure este campo no payload): preenchido pelo parser quando as colunas do dia carregam TEXTO DE STATUS (ex.: rotulo de afastamento) em vez de horas. Torna explicito no relatorio que o dia nao e "falta", e status. ⛔ NUNCA e fonte de periodo de afastamento — essa e "FuncionarioAfastamento" (ADR-010).';
comment on column public."BatidaFonteDados"."DataInclusao" is 'Campo `DataInclusao` — quando o registro entrou no Secullum. Diagnostico de batida lancada RETROATIVAMENTE, que invalida desvio ja detectado e possivelmente ja enviado no relatorio.';
comment on column public."BatidaFonteDados"."Nsr" is 'Numero Sequencial de Registro do equipamento. TEXT (nao numerico): e identificador, nao quantidade, e pode vir com zeros a esquerda.';
comment on column public."BatidaFonteDados"."Origem" is 'Campo `Origem` BRUTO (0..8 documentados). ⚠️ Origem = 11 JA APARECEU em producao e nao consta da documentacao oficial; significado ainda [DECISAO DO OWNER]. Por isso: sem CHECK, sem enum, sem significado presumido, job nunca falha. Logar uma vez por valor desconhecido distinto por execucao.';
comment on column public."BatidaFonteDados"."Tipo" is 'Campo `Tipo` BRUTO (Original=0, Manual=1, PreAssinalado=2, Desconsiderado=3). smallint SEM CHECK e SEM enum do Postgres: valor fora do documentado e persistido, tolerado e traduzido apenas na apresentacao.';
comment on column public."BatidaFonteDados".batida_id is 'NOSSA FK, desnormalizada a partir de batida_marcacao para permitir DELETE/consulta no escopo do dia inteiro sem join. Ambas as FKs sao ON DELETE CASCADE — expurgo por titular chega ate aqui.';
comment on column public."Cidade"."CidadeId" is 'Campo `Cidade.Id`. NULLABLE e SEM UNIQUE de proposito: o que se confirmou foi a FORMA do no, NAO a unicidade global do Id — que nunca foi verificada. Este projeto ja quebrou em producao duas vezes supondo unicidade global de id do Secullum. A chave de idempotencia e "Descricao".';
comment on column public."Departamento"."DepartamentoId" is 'Campo `Departamento.Id`. Chave de idempotencia, UNIQUE GLOBAL (ADR-008). O detector de colisao (unit_name_changed / unit_ref_name_conflict nos logs) continua sendo a rede de seguranca.';
comment on column public."Departamento"."Nfolha" is 'Campo `Departamento.Nfolha` (grafia literal confirmada em payload real: "Nfolha", f minusculo). Numero visivel na folha. ⚠️ Se algum identificador de Departamento se repetir entre empresas, o candidato natural e este, NAO "DepartamentoId" (ADR-008).';
comment on column public."Departamento".ativo is 'DERIVADO/FIXO POR NOS (minusculo): o Secullum NAO expoe status de Departamento ({ Id, Descricao, Nfolha }). Fica fixo em true e NAO ha tabela de historico. ⛔ Nao inferir desativacao pela ausencia do DepartamentoId no lote de /Funcionarios (ADR-009).';
comment on column public."Departamento".empresa_id is 'NOSSA FK (uuid). ⚠️ EMPRESA DE REFERENCIA, nao de propriedade (ADR-008): e a empresa do PRIMEIRO funcionario visto naquele departamento. ⛔ Agregacao por Empresa usa SEMPRE "Funcionario".empresa_id, NUNCA esta coluna.';
comment on column public."Empresa"."Desativada" is 'Campo `Empresa.Desativada` — ESTADO ATUAL, sem data. O Secullum nao informa QUANDO a empresa foi desativada; por isso empresa_evento_status so tem detectado_em. Escreva AQUI, nunca em `ativo`.';
comment on column public."Empresa"."DiaFechamentoPonto" is '[VALIDAR — Postman] Tipo assumido smallint (dia do mes). Mesma ressalva de "FechamentoPonto".';
comment on column public."Empresa"."Documento" is 'Campo `Documento` (CNPJ/CPF) — chave natural de idempotencia da sincronizacao, que e a chave que o proprio Secullum usa na rota Empresas.';
comment on column public."Empresa"."EmitiuAtestadoTecnico" is '[VALIDAR — Postman] Nao consta do manual oficial; reportado pelo Owner no payload real.';
comment on column public."Empresa"."EmpresaId" is 'Campo `Empresa.Id`. ATRIBUTO com indice NAO-UNICO: a chave de idempotencia continua sendo "Documento", que e a chave que o proprio Secullum usa na rota Empresas. Nao promover a UNIQUE sem evidencia.';
comment on column public."Empresa"."FechamentoPonto" is '[VALIDAR — Postman] Tipo assumido smallint (por analogia com `HorarioDia.Fechamento`, Inteiro 0..23). Se o payload real trouxer "HH:mm" ou boolean, abrir migration corretiva — nao forcar conversao no parser.';
comment on column public."Empresa"."Logotipo" is 'Logotipo em base 64. Volume irrelevante com poucas empresas. ⚠️ Se o cadastro crescer, avaliar deixar de sincronizar — nao ha consumidor de produto para ele hoje.';
comment on column public."Empresa"."NfolhaEmpresa" is '[VALIDAR — Postman] Grafia assumida por analogia com `Departamento.Nfolha` (confirmado com f minusculo). Vem do cadastro do manual, nao do no aninhado — pode nunca ser populado (ver aviso abaixo).';
comment on column public."Empresa"."ResponsavelNome" is '⚠️ Responsavel LEGAL da empresa. NAO e o gestor que recebe o relatorio consolidado — esse vive na tabela "Estrutura", vem de `Funcionario.Estrutura` e e outra pessoa. Foi para evitar exatamente esta confusao que a tabela de gestor NAO se chama `Responsavel`.';
comment on column public."Empresa"."TipoDocumento" is 'Enum BRUTO (0=CNPJ, 1=CPF, 2=Outros). smallint SEM CHECK — disciplina do projeto para enum do Secullum: valor desconhecido e persistido e tolerado, nunca derruba o job.';
comment on column public."Empresa"."UsaFechamentoDoPontoEspecifico" is '[VALIDAR — Postman] Nao consta do manual oficial (pag. 7-9); reportado pelo Owner no payload real.';
comment on column public."Empresa".ativo is 'DERIVADA POR NOS (minusculo) e GERADA PELO POSTGRES: coalesce(not "Desativada", true). ⛔ O upsert da sincronizacao NAO pode incluir esta coluna — o Postgres rejeita escrita em coluna gerada. Grave "Desativada". Ver o cabecalho da secao 4 desta migration e ADR-009.';
comment on column public."Empresa".cidade_id is 'NOSSA FK (uuid) -> "Cidade". ⚠️ NAO confundir com "CidadeId" (inteiro do Secullum), ao lado.';
comment on column public."Estrutura"."Descricao" is 'Campo `Estrutura.Descricao` — na pratica, o NOME do gestor responsavel. E o unico dado de identificacao do gestor que o Secullum fornece: e-mail e WhatsApp nao existem la.';
comment on column public."Estrutura"."EstruturaId" is 'Campo `Funcionario.EstruturaId` (= `Estrutura.Id`) — chave de idempotencia. Nunca resolvido subindo por "EstruturaPaiId".';
comment on column public."Estrutura"."EstruturaPaiId" is 'Campo `Estrutura.EstruturaPaiId`. Guardado so como contexto/diagnostico. 0 = raiz. ⏳ EM ABERTO (ADR-006): qual nivel da arvore e o gestor quando a estrutura nao for raiz. Ate isso ser respondido pelo Owner, NAO subir a arvore.';
comment on column public."Estrutura".email is 'NOSSO (minusculo) apesar de o VALOR vir do Secullum: nao e um campo de `Estrutura`, e o `Funcionario.Email` do funcionario cujo "Nome" bate com "Descricao". E resultado da NOSSA logica de match, nao um no do payload.';
comment on column public."Estrutura".email_origem is 'NOSSO (minusculo). manual (default) | secullum. A sincronizacao SO escreve em email quando email IS NULL OU email_origem = ''secullum''. Valor cadastrado pelo Owner NUNCA e sobrescrito.';
comment on column public."Estrutura".whatsapp is 'NOSSO (minusculo) — SEMPRE cadastro manual do Owner, nao ha campo equivalente no Secullum. ⛔ NAO derivar de "Funcionario"."Celular"/"Telefone" (agora capturados): telefone pessoal nao e canal de notificacao autorizado. Ver docs/06-seguranca-lgpd.md.';
comment on column public."Funcao"."FuncaoId" is 'Campo `Funcao.Id`, quando presente. NULLABLE e sem UNIQUE — mesma disciplina de "Cidade"."CidadeId". A chave de idempotencia e "Descricao" (que e a chave usada pelo proprio Secullum na rota Funcoes).';
comment on column public."Funcionario"."Admissao" is 'Funcionario.Admissao (data real do Secullum, ja presente no payload de /Funcionarios). Entra na allow-list de PII: e dado de vinculo empregaticio necessario para saber se o funcionario estava ativo na janela do relatorio/dashboard. Ver docs/06-seguranca-lgpd.md.';
comment on column public."Funcionario"."Celular" is 'Campo `Celular`. ⛔ NAO usar como numero de WhatsApp para notificacao — telefone pessoal nao e canal autorizado. "Estrutura".whatsapp continua 100% manual ([DECISAO DO OWNER]).';
comment on column public."Funcionario"."ConfigEspecificaCapturaDeFotoNoMomentoDaInclusao" is '✅ Nome confirmado. ⚠️ E apenas a CONFIGURACAO. Nenhuma foto e buscada nem armazenada por este projeto (ver "PossuiFoto" e o cabecalho desta migration).';
comment on column public."Funcionario"."ConfigEspecificaInclusaoManualPonto" is '✅ Nome confirmado no payload real (2026-08-13). ⏳ [VALIDAR — Postman] TIPO: a inspecao entregou so a chave. Assumido boolean; se for enum de modo (0/1/2), abrir migration corretiva. ⛔ Parser deve normalizar e devolver NULL em valor inesperado, nunca derrubar o ciclo.';
comment on column public."Funcionario"."ConfigEspecificaInclusaoManualPontoFusoHorarioId" is '✅ Nome confirmado. Sufixo Id => integer bruto, SEM FK: o cadastro de fusos horarios do Secullum nao e consumido por este projeto.';
comment on column public."Funcionario"."Cpf" is 'Campo `Cpf`. Sem UNIQUE de proposito: duplicata no cadastro do cliente cai no caso "2+ candidatos" da correlacao de afastamentos, que se abstem em vez de errar o titular.';
comment on column public."Funcionario"."Demissao" is 'Funcionario.Demissao (data real do Secullum; null enquanto o vinculo estiver ativo). Pode vir com data FUTURA (desligamento programado) — ver a regra de derivacao de employee.active em docs/04-modelo-dados.md.';
comment on column public."Funcionario"."DepartamentoId" is 'Campo `Funcionario.DepartamentoId` — INTEIRO do Secullum. A FK usada e departamento_id (uuid).';
comment on column public."Funcionario"."DesabilitarAssinaturaEletronica" is '✅ Nome confirmado. ⏳ [VALIDAR — Postman] tipo assumido boolean, como os demais Bloquear*/Permite*/Desabilitar* deste bloco.';
comment on column public."Funcionario"."Email" is 'Campo `Email` do funcionario. ⚠️ Ate 2026-08-13 so era lido em memoria para resolver "Estrutura".email quando o funcionario ERA o gestor; agora e persistido para todos. Isso NAO autoriza usa-lo como canal de notificacao: destinatario de relatorio continua sendo apenas "Estrutura".email/"Estrutura".whatsapp.';
comment on column public."Funcionario"."EmpresaId" is 'Campo `Funcionario.EmpresaId` — INTEIRO do Secullum, como veio. ⚠️ A FK que o sistema usa e empresa_id (uuid). Nunca fazer join por esta coluna.';
comment on column public."Funcionario"."EstruturaId" is 'Campo `Funcionario.EstruturaId` — INTEIRO do Secullum; e a chave de idempotencia de "Estrutura" (tabela do gestor). Nao ha FK uuid daqui para "Estrutura": o vinculo gestor->departamento e o que importa ao produto, e resolve-lo por funcionario duplicaria a relacao.';
comment on column public."Funcionario"."Foto" is 'Campo literal do Secullum (imagem do funcionário), vinda do 6º endpoint (GET Funcionarios/fotos?funcionarioId=<Id>), NÃO de /Funcionarios. Guarda os BYTES JÁ DECODIFICADOS (o prefixo "data:<mime>;base64," da data URI NÃO é armazenado aqui — ver foto_mime). NULL = não temos (nunca buscada OU funcionário sem foto). 🔴 A coluna mais restrita do schema: nunca em view exposta ao painel, nunca em log, nunca em relatório (ADR-018 §6.3). ⛔ NUNCA escrita pelo upsert de sync-cadastro — só pelo UPDATE direcionado do job sync-fotos.';
comment on column public."Funcionario"."FuncionarioId" is 'Campo `Funcionario.Id` — nomeado na forma qualificada porque e literalmente assim que o Secullum o chama de fora (`Batidas.FuncionarioId`). Chave de idempotencia e chave de juncao com /Batidas.';
comment on column public."Funcionario"."HorarioAlternativo2Id" is 'Campo `HorarioAlternativo2Id` — inteiro BRUTO, sem FK para "Horario" de proposito: o horario referenciado pode nao existir localmente (ou ainda nao ter sido sincronizado no ciclo), e uma FK transformaria isso em falha de job. Resolucao para "Horario".id, se necessaria, e da consulta.';
comment on column public."Funcionario"."HorarioId" is 'Campo `Funcionario.HorarioId` — INTEIRO do Secullum. A FK usada e horario_id (uuid). ℹ️ Em /Funcionarios o objeto `Horario` aninhado vem com `Dias` = null POR DESIGN: a grade completa so vem de GET /Horarios.';
comment on column public."Funcionario"."Mae" is '⚠️ PII de TERCEIRO (a mae do funcionario nao e titular deste tratamento nem tem relacao com o controlador). Capturada por decisao do Owner; e o campo com a justificativa de finalidade mais fraca de todo o schema. Vale o mesmo para "Pai". Ver docs/06-seguranca-lgpd.md.';
comment on column public."Funcionario"."MotivoDemissaoId" is 'Campo `MotivoDemissaoId` bruto. A rota MotivosDemissao NAO e consumida (escopo de 5 endpoints), entao o motivo em texto nao existe localmente — o que, alias, e desejavel: motivo de demissao e dado sensivel de vinculo.';
comment on column public."Funcionario"."NumeroFolha" is 'Campo `NumeroFolha` (Texto(22)) — matricula na folha. Dado pessoal identificador.';
comment on column public."Funcionario"."NumeroPis" is 'Campo `NumeroPis`. Pode vir string vazia — tratar "" como AUSENTE. Sem UNIQUE, mesmo racional de "Cpf".';
comment on column public."Funcionario"."Observacao" is '⚠️ TEXTO LIVRE de RH (Texto(255)). Alto risco de conter dado de saude/condicao pessoal. Persistido por decisao do Owner (ADR-011), contrariando a regra anterior de descarte de texto livre. ⛔ Nunca exibir em relatorio ao gestor, nunca logar, nunca indexar para busca.';
comment on column public."Funcionario"."PeriodoEncerrado" is '[VALIDAR — Postman] Tipo desconhecido (data? boolean?). Modelado como TEXT para nao perder o valor nem quebrar o job por conversao errada; converter em migration corretiva depois da inspecao do payload.';
comment on column public."Funcionario"."PossuiFoto" is 'Apenas o indicador. A imagem em si exigiria a rota Funcionarios/fotos (6o endpoint) e NAO e buscada.';
comment on column public."Funcionario"."Rg" is '⚠️ PII sensivel, capturada a partir de 2026-08-13 por decisao do Owner (ADR-011). Antes era explicitamente descartada pelo parser. Nunca logar, nunca exibir em notificacao.';
comment on column public."Funcionario".afastado_hoje is 'DERIVADO POR NOS (minusculo). O nome declara a limitacao no proprio identificador: responde APENAS "esta afastado HOJE?". Para "estava afastado na data X?" (motor, relatorio, dashboard) a fonte da verdade e SEMPRE "FuncionarioAfastamento". E funcao do tempo: vira sozinho no primeiro e no ultimo dia do afastamento, sem nada mudar no Secullum.';
comment on column public."Funcionario".afastamento_atual_id is 'Ponteiro para o registro de employee_absence que cobre "hoje" (null quando on_leave = false). Existe para o painel mostrar "afastado ate DD/MM" com um unico join, sem duplicar as datas em employee (dado duplicado = dado que dessincroniza). ON DELETE SET NULL: se o afastamento sumir do Secullum e for removido pela convergencia, o ponteiro se limpa sozinho. Havendo mais de um periodo cobrindo hoje (sobreposicao), aponta o de maior end_date e a sobreposicao e logada como aviso (absence_overlap).';
comment on column public."Funcionario".ativo is 'DERIVADO POR NOS (minusculo, NAO e campo do Secullum): VINCULO EMPREGATICIO, calculado a partir das datas com "hoje" em America/Sao_Paulo: ativo = ("Admissao" is null or "Admissao" <= hoje) and ("Demissao" is null or "Demissao" >= hoje). ⛔ NAO e afetado por ferias/afastamento — para isso existe afastado_hoje. ⚠️ Continua sendo COLUNA NORMAL (ao contrario de "Empresa".ativo, que virou gerada): esta derivacao depende de "hoje", nao e funcao imutavel das colunas, e por isso NAO pode ser GENERATED. Ver ADR-009 e ADR-010.';
comment on column public."Funcionario".cidade_id is 'NOSSA FK (uuid) -> "Cidade". ⚠️ NAO confundir com "CidadeId" (inteiro do Secullum), ao lado.';
comment on column public."Funcionario".empresa_id is 'NOSSA FK (uuid). Desnormalizada de proposito em relacao a "Departamento".empresa_id — e assim que o Secullum entrega o dado, e o dashboard agrega por Empresa. ⛔ Agregacao por Empresa usa SEMPRE esta coluna. ⚠️ NAO confundir com "EmpresaId" (inteiro do Secullum), criada em 20260813161000.';
comment on column public."Funcionario".foto_bytes is 'NOSSA. Tamanho em bytes da imagem DECODIFICADA. Observabilidade/dimensionamento, sem depender de octet_length("Foto") (que exigiria ler o binário).';
comment on column public."Funcionario".foto_hash is 'NOSSA. sha256 em hex dos BYTES DECODIFICADOS de "Foto" (nunca da string base64/data URI original — duas fotos idênticas com prefixos textualmente diferentes têm o mesmo hash). Permite pular o UPDATE do binário quando nada mudou e é a única forma de dizer "a foto mudou" em log sem citar conteúdo.';
comment on column public."Funcionario".foto_mime is 'NOSSA. image/jpeg, image/png, ou NULL quando não determinável. Fonte primária: o prefixo da data URI do 6º endpoint (confirmado por payload real, 2026-08-31); o *magic number* dos bytes é usado só como CONFERÊNCIA (diverge => vence o conteúdo real, com aviso agregado foto_mime_divergente). ⛔ Sem CHECK e sem lista fechada — mesma disciplina dos demais enums/mime deste schema. ⛔ Nunca inferir por nome de arquivo, nunca assumir JPEG por padrão.';
comment on column public."Funcionario".foto_sincronizada_em is 'NOSSA. Timestamp da última sincronização BEM-SUCEDIDA do job sync-fotos — inclui o sucesso "não tem foto" (ausência confirmada pelo Secullum). Distinta de foto_tentativa_em: uma tentativa que deu ERRO atualiza só foto_tentativa_em, nunca esta coluna (ADR-018 §5.3 — erro nunca apaga/mascara dado real).';
comment on column public."Funcionario".foto_tentativa_em is 'NOSSA. Timestamp da última TENTATIVA do job sync-fotos, com ou sem sucesso. 🔴 É esta coluna (não foto_sincronizada_em) que ordena a fila (funcionario_foto_fila_idx, ORDER BY ... NULLS FIRST) — sem ela, um funcionário cuja busca falha sempre travaria a cabeça da fila para sempre (ADR-018 §4.1).';
comment on column public."Funcionario".funcao_id is 'NOSSA FK (uuid) -> "Funcao". ⚠️ NAO confundir com "FuncaoId" (inteiro do Secullum), ao lado.';
comment on column public."Funcionario".horario_id is 'NOSSA FK (uuid) -> "Horario". NULLABLE: funcionario sem horario cadastrado no Secullum nao derruba a sincronizacao (fica sem horario, com aviso em log). ⚠️ NAO confundir com "HorarioId" (inteiro do Secullum).';
comment on column public."FuncionarioAfastamento"."AfastamentoId" is 'Campo `Id` do registro de afastamento (nao consta da tabela oficial do manual; confirmado em payload real). Forma qualificada pelo mesmo motivo de "FuncionarioId": `Id` puro colidiria por case com o `id` interno. Unicidade global NUNCA verificada — por isso a chave e COMPOSTA com funcionario_id.';
comment on column public."FuncionarioAfastamento"."DataInclusao" is 'Campo `DataInclusao` (nao documentado na tabela oficial; confirmado em payload real). Quando o registro foi criado no Secullum. Serve para diagnosticar afastamento lancado RETROATIVAMENTE, que invalida desvios ja detectados na janela — ver requisito do motor em sprints/sprint-02-motor-deteccao.md.';
comment on column public."FuncionarioAfastamento"."Fim" is 'Campo `Fim`, INCLUSIVO (o dia de Fim ainda e afastamento). Parsing pelos 10 primeiros caracteres da string, nunca via Date/UTC. ⛔ Sem CHECK ("Fim" >= "Inicio") de proposito: registro invertido na origem nao pode derrubar o job — o parser loga absence_invalid_range, nao grava e segue.';
comment on column public."FuncionarioAfastamento"."Inicio" is 'Campo `Inicio` (Data, obrigatorio). Parsing obrigatorio: 10 PRIMEIROS CARACTERES da string. NUNCA via new Date(...)/toISOString() — a Edge Function roda em UTC e a conversao ingenua desloca um dia.';
comment on column public."FuncionarioAfastamento"."JustificativaNome" is 'Campo `JustificativaNome` (Texto(7)), bruto, sem CHECK e sem lista fechada. ⚠️ Tratar como potencialmente revelador de saude: nunca exibido cru em relatorio/painel e nunca logado junto de identificacao do titular. O cadastro de Justificativas NAO e consumido.';
comment on column public."FuncionarioAfastamento".correlacionado_por is 'NOSSO (minusculo) — diagnostico (pis | cpf): qual chave resolveu a correlacao. Nao e PII: guarda o TIPO de chave, nunca o valor.';
comment on column public."FuncionarioAfastamento".funcionario_id is 'Correlacao resolvida EM MEMORIA por NumeroPis (prioridade) com fallback para Cpf: este endpoint NAO tem FuncionarioId, diferente de /Batidas. NumeroPis pode vir string vazia (visto em payload real) — tratar "" como ausente. Comparacao sempre sobre digitos (strip de mascara) nos dois lados. Zero ou 2+ candidatos => registro DESCARTADO com aviso agregado, nunca escolha arbitraria (mesma regra do match de gestor, docs/03-integracao-secullum.md).';
comment on column public."FuncionarioAfastamento".sincronizado_em is 'Ultima vez que este registro foi visto na resposta do Secullum. Base do delete de convergencia (registro apagado no Secullum tem de sumir daqui, senao suprime desvio para sempre).';
comment on column public."FuncionarioCentroCusto"."Descricao" is 'Unico campo do item no payload. A chave (funcionario_id, "Descricao") e a unica identidade possivel.';
comment on column public."Horario"."HorarioId" is 'Campo `Horario.Id` — chave de idempotencia local.';
comment on column public."Horario"."Numero" is 'Campo `Horario.Numero` — chave de NEGOCIO do Secullum (a rota Horarios?numero=<N> usa este campo). NAO e a chave de idempotencia local, que e "HorarioId".';
comment on column public."Horario".ativo is 'DERIVADO POR NOS (minusculo) do campo `Desativar`. ⏳ O campo literal "Desativar" NAO foi criado: tipo/semantica exatos nao confirmados no payload real (docs/03-integracao-secullum.md). Nao inventar coluna — abrir migration corretiva quando o tipo for observado.';
comment on column public."HorarioDescanso"."IncluirFeriado" is 'Enum bruto (DescansoDomingo=0, DescansoDia=1, HoraNormalDia=2, HoraNormalDescanso=3), sem CHECK.';
comment on column public."HorarioDescanso"."LimiteHorasFaltas" is 'Texto(5) HH:mm — tambem DURACAO. Mesma razao de "ValorDescanso" para manter TEXT.';
comment on column public."HorarioDescanso"."Tipo" is 'Enum bruto (Automatico=0, Variavel=1), smallint sem CHECK.';
comment on column public."HorarioDescanso"."ValorDescanso" is 'Texto(5) no formato HH:mm, mas semanticamente uma DURACAO (valor do DSR), nao um horario do dia. Mantido TEXT de proposito: o tipo `time` do Postgres nao representa duracao acima de 24h e induziria comparacoes erradas. Este sistema nao calcula DSR.';
comment on column public."HorarioDescansoFaixaItem"."Limite" is 'Texto(5) HH:mm (DURACAO). Mantido TEXT — mesma razao de "HorarioDescanso"."ValorDescanso".';
comment on column public."HorarioDia"."Carga" is 'Campo `Carga`, EM MINUTOS de carga do dia. Discriminador de dia sem expediente (junto com os 10 pares nulos). ⚠️ NAO confundir com "HorariosOpcoes"."Carga", que e a carga configurada no nivel do HORARIO.';
comment on column public."HorarioDia"."DiaSemana" is 'Campo `DiaSemana`: 0=Segunda .. 6=Domingo. ⛔ NUNCA usar EXTRACT(DOW) (0=Domingo) ao comparar com uma data — usar EXTRACT(ISODOW)-1. ⚠️ NAO confundir com "HorarioFaixasExtras"."DiaSemana", que e um enum COMPLETAMENTE diferente (Uteis=0, Sabado=1, ... IntervaloFolgas=15).';
comment on column public."HorarioDia"."HorarioDiaId" is 'Campo `Dias[].Id`. ATRIBUTO de diagnostico (indice nao-unico) — NAO e chave de idempotencia: confirmado em producao que se repete entre Horarios diferentes (migration 20260812140000). A chave real e (horario_id, "DiaSemana").';
comment on column public."HorarioDia"."TipoEntrada1" is 'TipoEntradaN bruto (smallint, sem CHECK/enum — enum nao documentado pelo Secullum).';
comment on column public."HorarioDia"."ToleranciaExtra" is 'Campo `ToleranciaExtra`, EM MINUTOS (a unidade nao esta no nome porque o nome e literal do Secullum). ⛔ Junto com "ToleranciaFalta", e a UNICA tolerancia que o motor de deteccao pode aplicar — nunca uma tolerancia propria, sob pena de divergir do calculo oficial de folha.';
comment on column public."HorarioDia"."ToleranciaFalta" is 'Campo `ToleranciaFalta`, EM MINUTOS. ⚠️ ARMADILHA CONFIRMADA: dia de folga vem com "ToleranciaExtra"/"ToleranciaFalta" PREENCHIDOS. Presenca de tolerancia NAO significa que ha expediente.';
comment on column public."HorarioDia".sem_expediente is 'DERIVADO POR NOS — por isso minusculo, e NAO um campo que o Secullum manda. true quando "Carga" = 0 E os 10 pares Entrada/Saida sao nulos. Nome escolhido para nao colidir com `Batida.Folga` nem com `TipoDia = Folga(2)`, que sao tres coisas distintas.';
comment on column public."HorarioExtras"."Acumulo" is 'Enum BRUTO 0..8 (Independentes=0 ... UteisDomingo_e_SabadoFeriado=8), smallint SEM CHECK.';
comment on column public."HorarioExtras"."ControleHorasExtrasAutorizadas" is '⚠️ Regra de FOLHA: limita quanto de hora extra o Secullum considera autorizado. ⛔ O motor de deteccao NAO filtra desvio por esta regra — o relatorio consolidado reporta desvio de HORARIO, nao saldo autorizado de folha. Confundir os dois faz o relatorio deixar de mostrar exatamente o excesso que o gestor precisa ver.';
comment on column public."HorarioExtras"."DescontarFaltasExtras" is 'Enum BRUTO (MaisSignificativas=0, MenosSignificativas=1), smallint SEM CHECK — mesma disciplina de "HorarioDia"."TipoEntrada1" e de "BatidaFonteDados"."Origem".';
comment on column public."HorarioExtras"."DescontarIgnorarDiaEspecial" is '"Dia especial" aqui e o mesmo conceito de "HorarioFaixasExtras"."DiaEspecial" (Domingo=0..Sabado=6) — ⚠️ TERCEIRA convencao de dia da semana do schema, diferente de "HorarioDia"."DiaSemana".';
comment on column public."HorarioExtras"."Interjornada" is '⚠️⚠️ DIVERGENCIA CONFIRMADA DA DOCUMENTACAO OFICIAL. O manual declara `Interjornada` como Booleano, com uma descricao que nem sequer e deste campo ("marcar qualquer minuto adiantado como extra", copiada de HorariosOpcoes). O valor REAL observado na conta do cliente em 2026-08-13 e uma STRING — provavelmente o intervalo minimo entre jornadas em "HH:mm". ⛔ NAO "corrigir" para boolean com base no PDF: o payload e o contrato. Mantido TEXT (nao `time`): e DURACAO, nao horario do dia.';
comment on column public."HorarioExtras"."QuantidadeExtrasAutorizadas" is 'Texto "HH:mm" conforme o manual — e DURACAO, nao horario do dia. Mantido TEXT de proposito: o tipo `time` do Postgres nao representa duracao acima de 24h e induziria comparacao errada.';
comment on column public."HorarioExtras"."UsarInterjornada" is 'Booleano que liga o uso de "Interjornada". ⚠️ O manual repete, por erro de copia, descricoes de HorariosOpcoes em UsarInterjornada/Interjornada/InterjornadaSeparada. O NOME do campo e o contrato; a descricao do PDF nao e confiavel neste bloco.';
comment on column public."HorarioFaixasExtras"."Controle" is 'Enum bruto (Diario=0, Semanal=1, Mensal=2), sem CHECK.';
comment on column public."HorarioFaixasExtras"."DiaEspecial" is 'De Domingo(0) a Sabado(6) — ⚠️ TERCEIRA convencao de dia da semana neste schema, diferente das outras duas. Valor bruto do Secullum, sem conversao.';
comment on column public."HorarioFaixasExtras"."DiaSemana" is '⚠️⚠️ ENUM COMPLETAMENTE DIFERENTE de "HorarioDia"."DiaSemana", apesar do nome identico (os dois nomes sao literais do Secullum). Aqui: Uteis=0, Sabado=1, Domingo=2, Feriado=3, Folgas=4, Especial=5, NoturnoUteis=6, NoturnoSabado=7, NoturnoDomingo=8, NoturnoFeriado=9, NoturnoFolgas=10, IntervaloUteis=11, IntervaloSabado=12, IntervaloDomingo=13, IntervaloFeriado=14, IntervaloFolgas=15. Em "HorarioDia", "DiaSemana" e 0=Segunda..6=Domingo. Confundir os dois produz erro SILENCIOSO. smallint BRUTO, sem CHECK.';
comment on column public."HorarioFaixasExtrasItem"."Coluna" is 'Coluna de extra correspondente. Tipo `Duplo` no manual mesmo parecendo indice inteiro — preservamos `double precision` para nao perder valor fracionario nem falhar na conversao.';
comment on column public."HorarioToleranciaEspecifica"."UsaToleranciaEspecifica" is 'Quando true, o motor de deteccao LOGA AVISO e aplica a tolerancia padrao do dia — nunca silencia. A tolerancia especifica e expressa como FAIXA (De/Ate), nao como minutos, e por isso nao e aproximavel pela tolerancia padrao.';
comment on column public."HorarioToleranciaEspecificaItem"."DiaSemana" is '⚠️ O manual (pag. 18) declara DiaSemana como "Booleano" com a descricao "Usa tolerancia especifica" — sao dois erros evidentes de copia na tabela oficial. Modelado como smallint (dia da semana), coerente com o payload real. [VALIDAR — Postman] se algum dia houver caso real ativo neste cliente.';
comment on column public."HorariosOpcoes"."AlocarBatidas" is 'Numero no payload real; semantica/enum NAO documentados. INTEIRO BRUTO, sem CHECK — mesma disciplina de "HorarioDia"."TipoEntrada1" e de "BatidaFonteDados"."Origem". `integer` (e nao `smallint`) de proposito: sem faixa conhecida, o tipo mais largo evita derrubar a transacao inteira do ciclo por causa de um campo que nenhum consumidor le.';
comment on column public."HorariosOpcoes"."AlocarHorario24Horas" is 'Nivel HORARIO. ⚠️ Existe tambem "HorarioDia"."Alocar24Horas", nivel DIA. Sao dois campos distintos do Secullum; o relevante para jornada que cruza a meia-noite e o do dia.';
comment on column public."HorariosOpcoes"."Carga" is 'Carga configurada no nivel do HORARIO (acompanha "DefinirCargaAutomaticamente"). ⚠️ NAO confundir com "HorarioDia"."Carga", que e a carga do DIA em minutos e e a unica que interessa a "ha expediente?". Unidade deste campo (minutos vs. horas) nao confirmada; `double precision` para nao truncar valor fracionario nem falhar na conversao.';
comment on column public."HorariosOpcoes"."Compensacao" is '⏳ Veio `null` no registro real — TIPO NAO OBSERVADO. Modelado como smallint nullable (enum de modo de compensacao) porque a familia de irmaos booleanos "CompensacaoIgnorar*" implica fortemente um enum de modo. Bruto, sem CHECK.';
comment on column public."HorariosOpcoes"."CompensacaoMensalFechamento" is '⏳ Veio `null` no registro real e, ao contrario de "Compensacao", NAO tem contexto que permita inferir o tipo (dia do mes? data? objeto?). jsonb bruto de proposito: `text` transformaria um eventual objeto em "[object Object]" e `smallint` derrubaria a transacao se vier string. Estreitar quando houver exemplo.';
comment on column public."HorariosOpcoes"."CompletarBatidasFaltantes" is '⚠️ Opcao de FOLHA do Secullum que preenche batida ausente no calculo dele. ⛔ Isso NAO afeta o que /Batidas devolve a este sistema nem autoriza o motor a "completar" nada: batida faltante continua sendo detectada por slot com "Memoria" e sem hora.';
comment on column public."HorariosOpcoes"."HorarioId" is 'Campo `HorarioId` do proprio no (inteiro do Secullum). A FK usada e horario_id (uuid).';
comment on column public."HorariosOpcoes"."HorasRepousoFaixas" is '⏳ SHAPE NAO CONFIRMADO. Veio `null` no registro real — nao ha um unico exemplo populado. jsonb BRUTO de proposito: modelar tabela filha exigiria INVENTAR as colunas do item, e este projeto ja quebrou duas vezes em producao por supor estrutura do Secullum sem evidencia. Hipotese NAO confirmada (nao implementar): mesma forma de "HorarioDescansoFaixaItem" { Ordem, Limite, Desconto }. Quando aparecer exemplo populado, promover a tabela filha por migration corretiva. Sem PII: e parametro de horario.';
comment on column public."HorariosOpcoes"."LimiteMinimoDeFaltasNoDiaMinutos" is '⚠️ O manual oficial (pag. 11) descreve este campo como "Limite minimo de EXTRAS no dia" e o de extras como "de FALTAS" — as descricoes estao TROCADAS no PDF. Preservamos o NOME do campo, que e o contrato real; ⛔ nao inverter para "corrigir".';
comment on column public."HorariosOpcoes"."ListaHorasInItinere" is '⏳ SHAPE NAO CONFIRMADO. Veio `[]` no registro real. jsonb bruto, mesmo racional.';
comment on column public."HorariosOpcoes"."ListaHorasSobreAviso" is '⏳ SHAPE NAO CONFIRMADO. Veio `[]` no registro real — a lista existe, o item nunca foi observado. jsonb bruto pelo mesmo racional de "HorasRepousoFaixas". Nao inventar colunas.';
comment on column public."HorariosOpcoes"."PeriodoEspecialAdicionalNoturnoInicio" is 'Texto(5) "HH:mm". Mantido TEXT (nao `time`): e configuracao de folha, nunca comparada com hora de batida por este sistema, e converter introduziria risco de fuso sem nenhum ganho.';
comment on column public."HorariosOpcoes"."SubstituirBatidasAbaixoDasTolerancias" is '⚠️ Regra de folha que substitui a batida pelo horario previsto quando a diferenca cabe na tolerancia. ⛔ O motor NAO aplica isso — ele compara a hora crua de batida_marcacao.hora com o previsto de "HorarioDia". Ativar essa regra aqui mudaria o numero do relatorio sem mudar o do Secullum.';
comment on column public."HorariosOpcoes"."TipoPreencherQuandoDiaEstiverEmBranco" is 'Enum bruto, sem CHECK. Acompanha "PreencherFaltasQuandoDiaEstiverEmBranco". `integer` pelo mesmo motivo de "AlocarBatidas": faixa desconhecida.';
comment on column public."HorariosOpcoes"."ToleranciaRefeicoesMinutos" is '⚠️ Tolerancia de REFEICAO — nao confundir com "HorarioDia"."ToleranciaExtra"/"ToleranciaFalta", que sao as unicas que o motor pode usar.';
