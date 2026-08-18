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
create table public."Empresa" (
  "Id" bigint generated always as identity primary key,
  "Nome" text, "Cnpj" text, "Ativo" boolean default true
);
create table public."Departamento" (
  "Id" bigint generated always as identity primary key,
  "EmpresaId" bigint, "Descricao" text
);
create table public."Funcionario" (
  "Id" bigint generated always as identity primary key,
  "EmpresaId" bigint, "DepartamentoId" bigint,
  "Nome" text, "Cpf" text, "Rg" text, "NumeroPis" text,
  "DataNascimento" date, "Endereco" text, "Telefone" text,
  "Email" text, "NomeMae" text, "NomePai" text,
  "DataAdmissao" date, "DataDemissao" date, "Ativo" boolean default true
);
create table public."Estrutura" (
  "Id" bigint generated always as identity primary key,
  "DepartamentoId" bigint, "GestorNome" text
);
create table public."Horario" (
  "Id" bigint generated always as identity primary key,
  "Descricao" text, "ToleranciaExtra" integer, "ToleranciaFalta" integer
);
create table public."HorarioDia" (
  "Id" bigint generated always as identity primary key,
  "HorarioId" bigint, "DiaSemana" smallint,
  "Entrada" time, "Saida" time
);
create table public."FuncionarioAfastamento" (
  "Id" bigint generated always as identity primary key,
  "FuncionarioId" bigint, "DataInicio" date, "DataFim" date
);
create table public."Batida" (
  "Id" bigint generated always as identity primary key,
  "BatidaId" integer, "FuncionarioId" integer, funcionario_id uuid,
  "Data" date,
  -- O Secullum já entrega o status do DIA. O motor não precisa inferir folga.
  "Folga" boolean, "Neutro" boolean, "Compensado" boolean, "AlmocoLivre" boolean,
  "Refeicao" boolean, "NBanco" boolean, "Ajuste" text,
  "Abono2" text, "Abono3" text, "Abono4" text, "Observacoes" text,
  status_dia_rotulo text,
  sincronizado_em timestamptz, atualizado_em timestamptz default now(),
  unique (funcionario_id, "Data")
);

-- Tabelas reais reveladas pelo pg_stat_statements do projeto: o espelho do
-- Secullum é mais largo do que o palpite inicial, e a Batida é registro de DIA
-- (conflito em funcionario_id+Data), com as marcações individuais numa tabela
-- separada e a procedência numa terceira.
create table public."BatidaFonteDados" (
  "Id" bigint generated always as identity primary key,
  batida_id uuid, batida_marcacao_id uuid,
  "Data" date, "Hora" time, "Nsr" text, "Origem" smallint, "Tipo" smallint,
  "FonteDadosId" bigint, "DataInclusao" timestamptz,
  criado_em timestamptz default now(), atualizado_em timestamptz default now()
);
create table public."HorariosOpcoes" (
  "Id" bigint generated always as identity primary key,
  horario_id uuid, "HorarioId" integer,
  "ToleranciaArtigo58" boolean, "QualquerMinutoAtrasadoComoFalta" boolean,
  "QualquerMinutoAdiantadoComoExtra" boolean,
  "LimiteMinimoDeExtrasNoDiaMinutos" integer, "LimiteMinimoDeFaltasNoDiaMinutos" integer,
  "DescontarToleranciaDasHorasExtras" boolean, "DescontarToleranciaDasHorasFaltas" boolean,
  "Compensacao" smallint, "UsarInterjornada" boolean, "Interjornada" text,
  "PermitirFolgasAutomaticas" boolean, "QuantidadeFolgasAutomaticas" integer,
  "CompletarBatidasFaltantes" boolean, "SubstituirBatidasAbaixoDasTolerancias" boolean,
  "DividirJornadaQuandoHouverFolga" boolean, "HorasRepousoFaixas" jsonb,
  atualizado_em timestamptz default now()
);
create table public."HorarioExtras" (
  "Id" bigint generated always as identity primary key,
  horario_id uuid, "HorarioId" integer,
  "ControleHorasExtrasAutorizadas" boolean, "QuantidadeExtrasAutorizadas" text,
  atualizado_em timestamptz default now()
);
create table public."HorarioFaixasExtras" (
  id uuid primary key default gen_random_uuid(),
  horario_id uuid, "HorarioId" integer, "DiaSemana" smallint,
  "Controle" smallint, "DiaEspecial" smallint
);
create table public."HorarioToleranciaEspecificaItem" (
  "Id" bigint generated always as identity primary key,
  horario_tolerancia_especifica_id uuid, "HorarioId" integer, "DiaSemana" smallint,
  "Entrada1De" time, "Entrada1Ate" time, "Saida1De" time, "Saida1Ate" time
);

-- Camada de domínio que vocês já começaram, em inglês. É a razão de o modelo
-- novo seguir a mesma convenção.
create table public.work_schedule_day (
  id uuid primary key default gen_random_uuid(),
  work_schedule_id uuid, secullum_horario_dia_id integer, weekday smallint,
  day_type smallint, is_day_off boolean, is_neutral boolean, is_compensated boolean,
  free_lunch boolean, allocate_24_hours boolean,
  entry_1 time, exit_1 time, entry_2 time, exit_2 time,
  tolerance_extra_minutes integer, tolerance_absence_minutes integer,
  workload_minutes integer, updated_at timestamptz default now()
);
create table public.batida_marcacao (
  id uuid primary key default gen_random_uuid(),
  batida_id uuid, funcionario_id uuid, data date, hora time,
  tipo_coluna text, indice_coluna smallint, valor_bruto text,
  status_rotulo text, desconsiderada boolean,
  "EquipId" integer, "FonteDadosId" bigint, "Memoria" time,
  sincronizado_em timestamptz, atualizado_em timestamptz default now()
);

grant all on all tables in schema public to anon, authenticated, service_role;

-- Tabelas nossas em minúsculo, como no schema atual (a migration 00 não as toca).
create table public.empresa_evento_status (
  id bigint generated always as identity primary key,
  empresa_id bigint, status text, ocorrido_em timestamptz default now()
);
create table public.funcionario_evento_status (
  id bigint generated always as identity primary key,
  funcionario_id bigint, status text, ocorrido_em timestamptz default now()
);
grant all on public.empresa_evento_status, public.funcionario_evento_status to anon, authenticated, service_role;
