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
-- ⛔ PRÉ-REQUISITO QUE NÃO SE RESOLVE AQUI: TRÊS SEGREDOS NOVOS NO VAULT
-- Hoje o Vault de produção tem só `vercel_jobs_base_url` e `vercel_cron_secret`
-- (medido em 01/09/2026). Reaproveitar esses nomes para apontar ao Supabase
-- deixaria o comando mentindo sobre para onde ele chama, então este arquivo
-- exige nomes novos:
--
--     edge_functions_base_url  -> https://<ref>.supabase.co/functions/v1
--     edge_functions_token     -> um JWT válido do projeto (ver a nota abaixo)
--     sync_shared_secret       -> o segredo que fecha o endpoint (>= 32 chars)
--
-- Criar antes da janela, com:
--     select vault.create_secret('<valor>', '<nome>', '<descrição>');
--
-- ⚠️ O `sync_shared_secret` tem de ser o MESMO valor do secret
-- `SYNC_SHARED_SECRET` das Edge Functions. São dois lugares porque são dois
-- lados: aqui quem envia, lá quem confere. Divergir entre eles dá 401 a cada
-- ciclo — sincronização parada respondendo, que é o pior modo de falha.
--
-- ✅ O TOKEN NÃO É O QUE PROTEGE O ENDPOINT — E POR ISSO EXISTE O TERCEIRO SEGREDO
-- Quem barra uma Edge Function é o `verify_jwt` do gateway do Supabase, e ele
-- aceita QUALQUER JWT do projeto, inclusive a anon key, que é pública por
-- definição: ela vive no bundle do painel. Sem mais nada, qualquer um que abrisse
-- o DevTools dispararia uma sincronização.
--
-- ⛔ E não era risco futuro. Medido em 02/09/2026: as três funções já estavam
-- ACTIVE em produção desde 31/08, com `verify_jwt=true` — publicadas na noite da
-- janela e nunca religadas ao cron. Ficaram invocáveis por qualquer um durante
-- dois dias.
--
-- Decisão do dono em 02/09: fechar. As três funções passaram a exigir o header
-- `x-sync-secret`, conferido contra o secret `SYNC_SHARED_SECRET` delas — ver
-- `supabase/functions/_shared/require-secret.ts`. Este arquivo é o outro lado:
-- os três comandos enviam o header, com o valor lido do Vault.
--
-- Não se confere o papel do JWT em vez disso — seria de graça, já que o gateway
-- validou a assinatura — porque exigir `service_role` obrigaria a chave mestra a
-- morar no Vault para o `pg_cron` enviá-la, e a Regra 4 do CLAUDE.md diz que ela
-- só vive no backend FastAPI.
--
-- O QUE MUDA, JOB A JOB
--   jobid 3  sync-cadastro-cron    */30   -> POST .../sync-cadastro
--   jobid 4  sync-batidas-cron     */15   -> POST .../sync-batidas   (incremental)
--   jobid 5  sync-fotos-cron       17 3 * -> POST .../sync-fotos
--   novo     sync-batidas-backfill  7 4 * -> POST .../sync-batidas {"scope":"backfill"}
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
  v_base      text;
  v_token     text;
  v_segredo   text;
  v_faltam    text[] := '{}';
  v_estranhos text[];
  v_nome      text;
begin
  ---------------------------------------------------------------------------
  -- 1. Pré-condições. Tudo que falta é nomeado de uma vez: descobrir a segunda
  --    pendência só depois de resolver a primeira custa uma rodada de janela.
  ---------------------------------------------------------------------------
  foreach v_nome in array array['edge_functions_base_url', 'edge_functions_token', 'sync_shared_secret'] loop
    if not exists (select 1 from vault.decrypted_secrets where name = v_nome) then
      v_faltam := v_faltam || v_nome;
    end if;
  end loop;

  if cardinality(v_faltam) > 0 then
    raise exception
      'segredo(s) ausente(s) no Vault: %. Criar com vault.create_secret() antes da janela — ver o cabeçalho deste arquivo',
      array_to_string(v_faltam, ', ');
  end if;

  ---------------------------------------------------------------------------
  -- 1b. Job na Vercel que este arquivo NÃO reescreve.
  --
  -- A guarda final já exige zero jobs na Vercel, mas ela roda DEPOIS dos
  -- `alter_job` — e fora de transação (é assim que a janela roda, por
  -- `sb_sql.sh -f`) cada bloco anônimo commita sozinho. O resultado seria a pior
  -- combinação possível: dois jobs trocados, um terceiro ainda na Vercel, e o
  -- script saindo não-zero. Aqui a mesma condição reprova antes de escrever.
  --
  -- ⛔ Foi assim que o `sync-fotos-cron` apareceu (jobid 5, `17 3 * * *`, criado
  -- pela outra equipe em 02/09/2026). Ele deixou de ser estranho no mesmo dia:
  -- a função `sync-fotos` passou a existir neste repositório e este arquivo o
  -- reescreve junto dos outros dois. A condição fica, porque o próximo job que
  -- aparecer sem aviso é o que ela existe para pegar.
  ---------------------------------------------------------------------------
  select array_agg(jobname order by jobid) into v_estranhos
    from cron.job
   where command ilike '%vercel_jobs_base_url%'
     and jobname not in ('sync-cadastro-cron', 'sync-batidas-cron', 'sync-fotos-cron');

  if v_estranhos is not null then
    raise exception
      'há job(s) na Vercel que este arquivo não reescreve: %. Trocar só os dois deixaria a '
      'sincronização partida entre dois runners, e os exposed schemas seguiriam bloqueados. '
      'Decidir o que fazer com ele(s) ANTES da janela.',
      array_to_string(v_estranhos, ', ');
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

  -- Um segredo curto é pior que nenhum: ele faz o endpoint parecer fechado.
  -- 32 caracteres é o piso de quem gera com `openssl rand -base64 32`.
  select decrypted_secret into strict v_segredo
    from vault.decrypted_secrets where name = 'sync_shared_secret';
  if length(v_segredo) < 32 then
    raise exception
      'sync_shared_secret tem % caracteres; abaixo de 32 ele fecha o endpoint só na aparência',
      length(v_segredo);
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
  if not exists (select 1 from cron.job where jobname = 'sync-fotos-cron') then
    raise exception 'job sync-fotos-cron não existe — este arquivo reescreve, não cria';
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
                 where name = 'edge_functions_token'),
            'x-sync-secret', (
                select decrypted_secret from vault.decrypted_secrets
                 where name = 'sync_shared_secret')
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
                 where name = 'edge_functions_token'),
            'x-sync-secret', (
                select decrypted_secret from vault.decrypted_secrets
                 where name = 'sync_shared_secret')
        ),
        timeout_milliseconds := 590000
    );
    $cmd$
  );

  -- Fotos: cadência diária, herdada de quem criou o job. O minuto 17 fica fora
  -- da grade de 15 pelo mesmo motivo do backfill — sem colidir com o
  -- incremental, e mantendo a heurística de contar a cadência do diário.
  perform cron.alter_job(
    job_id  => (select jobid from cron.job where jobname = 'sync-fotos-cron'),
    schedule => '17 3 * * *',
    command => $cmd$
    select net.http_post(
        url := (select decrypted_secret from vault.decrypted_secrets
                 where name = 'edge_functions_base_url') || '/sync-fotos',
        body := '{}'::jsonb,
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'Authorization', 'Bearer ' || (
                select decrypted_secret from vault.decrypted_secrets
                 where name = 'edge_functions_token'),
            'x-sync-secret', (
                select decrypted_secret from vault.decrypted_secrets
                 where name = 'sync_shared_secret')
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
                 where name = 'edge_functions_token'),
            'x-sync-secret', (
                select decrypted_secret from vault.decrypted_secrets
                 where name = 'sync_shared_secret')
        ),
        timeout_milliseconds := 590000
    );
    $cmd$
  );

  raise notice 'runner trocado: 3 jobs reescritos e o backfill agendado';
end $$;

-- ----------------------------------------------------------------------------
-- Guarda final: falha alto se a garantia deste arquivo não se sustentar.
-- Um `alter_job` que não pegou não avisa sozinho — ele responde e segue.
-- ----------------------------------------------------------------------------
do $$
declare
  v_vercel    int;
  v_supa      int;
  v_fechados  int;
begin
  select count(*) into v_vercel from cron.job where command ilike '%vercel_jobs_base_url%';
  select count(*) into v_supa   from cron.job where command ilike '%edge_functions_base_url%';
  select count(*) into v_fechados from cron.job where command ilike '%x-sync-secret%';

  if v_vercel > 0 then
    raise exception
      '% job(s) ainda chamam o vercel_jobs_base_url — a troca NÃO valeu', v_vercel;
  end if;

  if v_supa <> 4 then
    raise exception
      'esperava 4 jobs apontando para as Edge Functions, encontrei % — conferir cron.job antes de religar', v_supa;
  end if;

  -- Sem o header, o job toma 401 a cada ciclo e a sincronização fica parada
  -- respondendo — exatamente a classe de falha que este arquivo existe para não
  -- deixar acontecer às 2h da manhã.
  if v_fechados <> 4 then
    raise exception
      'esperava 4 jobs enviando x-sync-secret, encontrei % — os outros tomariam 401', v_fechados;
  end if;

  raise notice 'OK: nenhum job chama a Vercel, os 4 apontam para as Edge Functions e enviam o segredo';
end $$;
