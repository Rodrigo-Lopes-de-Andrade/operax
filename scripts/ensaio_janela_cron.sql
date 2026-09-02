-- ============================================================================
-- OperaX — ensaio de `scripts/janela_cron_runner.sql`
-- ----------------------------------------------------------------------------
--   psql -v ON_ERROR_STOP=1 -f scripts/ensaio_janela_cron.sql
--
-- Roda contra qualquer Postgres: `cron` é sempre simulado, e o Vault é usado de
-- verdade quando existe (banco de dev, `operax_test`) ou simulado quando não.
-- Nada persiste — tudo dentro de uma transação que termina em rollback.
--
-- POR QUE ELE EXISTE
-- O arquivo que ele ensaia troca o runner da sincronização de produção, e o
-- caminho feliz dele não tinha onde ser exercitado: o banco local não tem
-- `pg_cron`, e o projeto de staging também não (medido em 01/09/2026). Sem
-- isto, a primeira execução real seria dentro da janela, com a sincronização
-- parada — que é o que este runbook existe para evitar.
--
-- O QUE ELE PROVA
--   1. o arquivo compila e roda até o fim;
--   2. duas passadas deixam o mesmo estado (a janela pode reaplicar);
--   3. saem três jobs apontando para as Edge Functions, nenhum para a Vercel,
--      os jobids 3 e 4 preservados, e só o backfill carregando `scope`;
--   4. a guarda final reprova quando um job fica para trás — guarda que nunca
--      falhou não é guarda.
--
-- O QUE ELE NÃO PROVA
-- O comportamento do `pg_cron` de verdade: aqui `cron.alter_job` e
-- `cron.schedule` são funções de mentira com a mesma assinatura nomeada. Se a
-- assinatura real mudar, este ensaio segue verde e a janela falha. É a mesma
-- limitação do ensaio das Edge Functions contra o espelho, e pela mesma razão:
-- ensaio prova o que se pode montar, não o que só existe lá.
--
-- A pré-condição do Vault (reprovar nomeando as duas pendências de uma vez) foi
-- conferida à mão em 01/09/2026 contra o banco de desenvolvimento, que tem o
-- Vault de verdade. Não está aqui porque assertar uma falha esperada no meio de
-- um `\i` exige desligar o `ON_ERROR_STOP`, e aí o resto do ensaio deixa de
-- valer.
-- ============================================================================

\set ON_ERROR_STOP on
\pset pager off

begin;

create schema cron;
create table cron.job (
  jobid    bigserial primary key,
  jobname  text unique,
  schedule text,
  command  text,
  active   boolean default true
);

-- Os dois jobs como produção os tem hoje (medido em 01/09/2026).
insert into cron.job (jobid, jobname, schedule, command) values
 (3, 'sync-cadastro-cron', '*/30 * * * *',
  'select net.http_get(url := (select decrypted_secret from vault.decrypted_secrets where name = ''vercel_jobs_base_url'') || ''/api/sync-cadastro'');'),
 (4, 'sync-batidas-cron', '*/15 * * * *',
  'select net.http_get(url := (select decrypted_secret from vault.decrypted_secrets where name = ''vercel_jobs_base_url'') || ''/api/sync-batidas'');');

create function cron.alter_job(job_id bigint, schedule text default null,
                               command text default null) returns void as $f$
  update cron.job set schedule = coalesce($2, schedule), command = coalesce($3, command)
   where jobid = $1;
$f$ language sql;

create function cron.schedule(job_name text, schedule text, command text) returns bigint as $f$
  insert into cron.job (jobname, schedule, command) values ($1, $2, $3)
    on conflict (jobname) do update set schedule = excluded.schedule, command = excluded.command
  returning jobid;
$f$ language sql;

-- O Vault: usa o de verdade quando existe (banco de dev, `operax_test`) e
-- simula quando não existe (Postgres pelado). Os dois caminhos são desfeitos
-- pelo rollback — `vault.create_secret` grava numa tabela como qualquer outra.
do $$
declare
  v_valores text[][] := array[
    ['vercel_jobs_base_url',    'https://exemplo.vercel.app'],
    ['edge_functions_base_url', 'https://nklobmlxyidqxarzisph.supabase.co/functions/v1'],
    ['edge_functions_token',
     'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.assinatura-de-ensaio'],
    -- 44 caracteres, acima do piso de 32 que o script exige. Um valor curto
    -- aqui faria o ensaio passar por um caminho que produção reprovaria.
    ['sync_shared_secret', 'ensaio-de-segredo-compartilhado-com-44-chars']
  ];
  i int;
begin
  if to_regclass('vault.decrypted_secrets') is null then
    execute 'create schema if not exists vault';
    execute 'create table vault.decrypted_secrets (name text primary key, decrypted_secret text)';
    for i in 1 .. array_length(v_valores, 1) loop
      execute 'insert into vault.decrypted_secrets values ($1, $2)'
        using v_valores[i][1], v_valores[i][2];
    end loop;
    raise notice 'vault simulado';
  else
    for i in 1 .. array_length(v_valores, 1) loop
      -- Um segredo homônimo já existente faria o ensaio ler outro valor.
      if exists (select 1 from vault.decrypted_secrets where name = v_valores[i][1]) then
        raise exception 'o Vault deste banco já tem o segredo % — o ensaio leria o valor errado', v_valores[i][1];
      end if;
      perform vault.create_secret(v_valores[i][2], v_valores[i][1], 'ensaio da troca de runner');
    end loop;
    raise notice 'vault real, quatro segredos de ensaio criados (desfeitos no rollback)';
  end if;
end $$;

\echo '--- 1. primeira passada'
\i scripts/janela_cron_runner.sql
\echo '--- 2. segunda passada (idempotência)'
\i scripts/janela_cron_runner.sql

\echo '--- 3. o estado final, job a job'
do $$
declare v int;
begin
  select count(*) into v from cron.job;
  if v <> 3 then raise exception 'esperava 3 jobs, encontrei %', v; end if;

  select count(*) into v from cron.job where command ilike '%vercel%';
  if v <> 0 then raise exception '% job(s) ainda citam a Vercel', v; end if;

  select count(*) into v from cron.job where command ilike '%edge_functions_base_url%';
  if v <> 3 then raise exception 'esperava 3 jobs no Supabase, encontrei %', v; end if;

  select count(*) into v from cron.job where command ilike '%backfill%';
  if v <> 1 then raise exception 'esperava exatamente 1 job de backfill, encontrei %', v; end if;

  -- Os jobids têm de sobreviver: `cron.alter_job` preserva, um
  -- unschedule/schedule não preservaria, e o diário do runbook cita "jobs 3 e 4".
  if not exists (select 1 from cron.job where jobid = 3 and jobname = 'sync-cadastro-cron')
  or not exists (select 1 from cron.job where jobid = 4 and jobname = 'sync-batidas-cron') then
    raise exception 'os jobids 3 e 4 não sobreviveram à reescrita';
  end if;

  if exists (select 1 from cron.job
              where jobname = 'sync-batidas-cron' and command ilike '%backfill%') then
    raise exception 'o job incremental está pedindo backfill';
  end if;

  raise notice 'OK: 3 jobs, nenhum na Vercel, jobids preservados, 1 backfill';
end $$;

\echo '--- 4. com um job ainda na Vercel, a guarda final deve reprovar'
savepoint guarda;
update cron.job
   set command = 'select net.http_get(url := (select decrypted_secret from vault.decrypted_secrets where name = ''vercel_jobs_base_url''));'
 where jobname = 'sync-cadastro-cron';

do $$
declare v_vercel int; v_supa int;
begin
  select count(*) into v_vercel from cron.job where command ilike '%vercel_jobs_base_url%';
  select count(*) into v_supa   from cron.job where command ilike '%edge_functions_base_url%';

  -- Mesmas duas condições da guarda de `janela_cron_runner.sql`. Se ela mudar e
  -- esta cópia não, o ensaio segue verde — por isso a guarda de lá é a que vale,
  -- e esta existe só para provar que aquelas condições mordem.
  if v_vercel = 0 and v_supa = 3 then
    raise exception 'a guarda final NÃO pegaria um job deixado na Vercel';
  end if;
  raise notice 'OK: a guarda final pega (% na Vercel, % no Supabase)', v_vercel, v_supa;
end $$;
rollback to savepoint guarda;

rollback;

\echo ''
\echo '================================================'
\echo ' ENSAIO DA TROCA DE RUNNER: OK'
\echo '================================================'
