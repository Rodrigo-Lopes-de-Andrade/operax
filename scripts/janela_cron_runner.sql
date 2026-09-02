-- ============================================================================
-- OperaX — a troca do runner: os jobs de pg_cron deixam de chamar a Vercel
-- ----------------------------------------------------------------------------
-- Roda UMA VEZ, no passo 4 item 2 da janela (docs/RUNBOOK-JANELA-CONVERGENCIA.md),
-- depois do `supabase functions deploy` das três e depois do lote de migrations.
--
-- POR QUE ISTO É UM ARQUIVO, E NÃO UM COMANDO NA HORA
-- É a reescrita do comando dos jobs que desliga a chamada ao `kastropark-jobs` —
-- não existe gesto separado para isso. Um `cron.alter_job` digitado às 2h da
-- manhã, com a sincronização parada, é a pior forma de descobrir que o nome de
-- um segredo do Vault estava errado. Aqui as pré-condições falham alto e ANTES
-- de qualquer escrita, e o arquivo pode ser lido com calma dias antes.
--
-- ⛔ PRÉ-REQUISITO QUE NÃO SE RESOLVE AQUI: DOIS SEGREDOS NOVOS NO VAULT
-- Hoje o Vault de produção tem só `vercel_jobs_base_url` e `vercel_cron_secret`
-- (medido em 01/09/2026). Reaproveitar esses nomes para apontar ao Supabase
-- deixaria o comando mentindo sobre para onde ele chama, então este arquivo
-- exige nomes novos:
--
--     edge_functions_base_url  -> https://<ref>.supabase.co/functions/v1
--     edge_functions_token     -> um JWT válido do projeto (ver a nota abaixo)
--
-- Criar antes da janela, com:
--     select vault.create_secret('<valor>', '<nome>', '<descrição>');
--
-- ⚠️ O TOKEN NÃO É O QUE PROTEGE O ENDPOINT — E ISSO É DECISÃO DO DONO
-- As três funções não conferem autorização nenhuma no corpo delas: quem barra é
-- o `verify_jwt` do gateway do Supabase, e ele aceita QUALQUER JWT do projeto,
-- inclusive a anon key, que é pública por definição. Ou seja: depois desta
-- troca, qualquer um que tenha a anon key consegue disparar uma sincronização.
--
-- O que isso custa, medido e não estimado: a resposta não carrega PII (é
-- contrato das funções, e os avisos referenciam por Id), então não é vazamento.
-- É custo e carga na origem — e, pior, `app.sync_run` NÃO tem o equivalente do
-- `job_execucao_em_andamento_key`, o índice único parcial que hoje impede duas
-- passadas simultâneas. Disparos repetidos rodam concorrentes.
--
-- Fechar isso é mudança de contrato das funções (um segredo compartilhado
-- conferido dentro delas), não deste arquivo. Fica nomeado para ser decidido
-- antes da janela, não descoberto depois.
--
-- O QUE MUDA, JOB A JOB
--   jobid 3  sync-cadastro-cron    */30  -> POST .../sync-cadastro
--   jobid 4  sync-batidas-cron     */15  -> POST .../sync-batidas   (incremental)
--   novo     sync-batidas-backfill 7 4 * -> POST .../sync-batidas {"scope":"backfill"}
--
-- O backfill é o que devolve o contrato da SPEC-TECNICA — correção na origem até
-- D-7 vira revogação do indício. Com o runner da Vercel ele não existia: toda
-- passada carimbava janela deslizante de 2 dias, e nenhuma leitura mostrou aquele
-- runner aceitando `scope`.
--
-- ⚠️ O MINUTO 7 QUEBRA UMA HEURÍSTICA QUE ESTE PROJETO USA, DE PROPÓSITO
-- Hoje dá para provar que não há um segundo invocador contando a cadência do
-- diário: todo início cai em múltiplo de 15. Um backfill em múltiplo de 15
-- colidiria com o incremental — e sem lock de sobreposição isso é duas passadas
-- ao mesmo tempo. Então ele sai da grade, e a heurística passa a ser
-- "96 + 48 + 1 por dia, e a única fora da grade é o backfill das 04:07 UTC".
--
-- Idempotente: reaplicar deixa exatamente o mesmo estado.
-- ============================================================================

do $$
declare
  v_base   text;
  v_token  text;
  v_faltam text[] := '{}';
  v_nome   text;
begin
  ---------------------------------------------------------------------------
  -- 1. Pré-condições. Tudo que falta é nomeado de uma vez: descobrir a segunda
  --    pendência só depois de resolver a primeira custa uma rodada de janela.
  ---------------------------------------------------------------------------
  foreach v_nome in array array['edge_functions_base_url', 'edge_functions_token'] loop
    if not exists (select 1 from vault.decrypted_secrets where name = v_nome) then
      v_faltam := v_faltam || v_nome;
    end if;
  end loop;

  if cardinality(v_faltam) > 0 then
    raise exception
      'segredo(s) ausente(s) no Vault: %. Criar com vault.create_secret() antes da janela — ver o cabeçalho deste arquivo',
      array_to_string(v_faltam, ', ');
  end if;

  select decrypted_secret into strict v_base
    from vault.decrypted_secrets where name = 'edge_functions_base_url';
  select decrypted_secret into strict v_token
    from vault.decrypted_secrets where name = 'edge_functions_token';

  -- Erro de barra no fim é o tipo de coisa que só aparece como 404 no primeiro
  -- ciclo depois de religar, quando ninguém está mais olhando.
  if v_base !~ '^https://[a-z0-9-]+\.supabase\.co/functions/v1$' then
    raise exception
      'edge_functions_base_url não tem a forma https://<ref>.supabase.co/functions/v1 (sem barra final)';
  end if;

  if v_token !~ '^ey[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$' then
    raise exception 'edge_functions_token não parece um JWT do projeto';
  end if;

  ---------------------------------------------------------------------------
  -- 2. Os dois jobs existentes. `cron.alter_job` preserva o jobid, e é o
  --    caminho que funciona: `update` direto em `cron.job` é negado, porque a
  --    tabela é do `supabase_admin` (medido na janela de 31/08).
  ---------------------------------------------------------------------------
  if not exists (select 1 from cron.job where jobname = 'sync-cadastro-cron') then
    raise exception 'job sync-cadastro-cron não existe — este arquivo reescreve, não cria';
  end if;
  if not exists (select 1 from cron.job where jobname = 'sync-batidas-cron') then
    raise exception 'job sync-batidas-cron não existe — este arquivo reescreve, não cria';
  end if;

  perform cron.alter_job(
    job_id  => (select jobid from cron.job where jobname = 'sync-cadastro-cron'),
    schedule => '*/30 * * * *',
    command => $cmd$
    select net.http_post(
        url := (select decrypted_secret from vault.decrypted_secrets
                 where name = 'edge_functions_base_url') || '/sync-cadastro',
        body := '{}'::jsonb,
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'Authorization', 'Bearer ' || (
                select decrypted_secret from vault.decrypted_secrets
                 where name = 'edge_functions_token')
        ),
        timeout_milliseconds := 590000
    );
    $cmd$
  );

  perform cron.alter_job(
    job_id  => (select jobid from cron.job where jobname = 'sync-batidas-cron'),
    schedule => '*/15 * * * *',
    command => $cmd$
    select net.http_post(
        url := (select decrypted_secret from vault.decrypted_secrets
                 where name = 'edge_functions_base_url') || '/sync-batidas',
        body := '{}'::jsonb,
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'Authorization', 'Bearer ' || (
                select decrypted_secret from vault.decrypted_secrets
                 where name = 'edge_functions_token')
        ),
        timeout_milliseconds := 590000
    );
    $cmd$
  );

  ---------------------------------------------------------------------------
  -- 3. O backfill. `cron.schedule` com nome já é upsert por nome, então
  --    reaplicar não duplica.
  ---------------------------------------------------------------------------
  perform cron.schedule(
    'sync-batidas-backfill',
    '7 4 * * *',
    $cmd$
    select net.http_post(
        url := (select decrypted_secret from vault.decrypted_secrets
                 where name = 'edge_functions_base_url') || '/sync-batidas',
        body := '{"scope":"backfill"}'::jsonb,
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'Authorization', 'Bearer ' || (
                select decrypted_secret from vault.decrypted_secrets
                 where name = 'edge_functions_token')
        ),
        timeout_milliseconds := 590000
    );
    $cmd$
  );

  raise notice 'runner trocado: 2 jobs reescritos e o backfill agendado';
end $$;

-- ----------------------------------------------------------------------------
-- Guarda final: falha alto se a garantia deste arquivo não se sustentar.
-- Um `alter_job` que não pegou não avisa sozinho — ele responde e segue.
-- ----------------------------------------------------------------------------
do $$
declare
  v_vercel int;
  v_supa   int;
begin
  select count(*) into v_vercel from cron.job where command ilike '%vercel_jobs_base_url%';
  select count(*) into v_supa   from cron.job where command ilike '%edge_functions_base_url%';

  if v_vercel > 0 then
    raise exception
      '% job(s) ainda chamam o vercel_jobs_base_url — a troca NÃO valeu', v_vercel;
  end if;

  if v_supa <> 3 then
    raise exception
      'esperava 3 jobs apontando para as Edge Functions, encontrei % — conferir cron.job antes de religar', v_supa;
  end if;

  raise notice 'OK: nenhum job chama a Vercel, e os 3 apontam para as Edge Functions';
end $$;
