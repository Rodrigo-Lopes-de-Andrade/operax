-- ============================================================================
-- OperaX — a linha de `app.integration` sem a qual o passo 7 reprova
-- ----------------------------------------------------------------------------
-- Roda UMA VEZ, no preparo da janela, ANTES de o runner novo subir.
--
-- O QUE ACONTECE SEM ELA, E POR QUE NÃO É UM ERRO BARULHENTO
-- `SupabaseBatidaRepository.recordSyncRun` procura a integração antes de gravar:
--
--     select id, tenant_id from app.integration
--      where provider = 'secullum' and active order by created_at limit 1
--
-- Não achando, ele **falha macio**: escreve no log e volta. A sincronização
-- termina com `ok: true`, as batidas entram, e `app.sync_run` fica vazia.
--
-- Medido em produção em 01/09/2026: `app.integration` tem **0 linhas**, e
-- `app.sync_run.tenant_id`/`integration_id` são `not null` com FK. Então, sem
-- esta linha, a janela "dá certo" e o critério de saída reprova:
-- `fn_data_freshness` devolve zero linha e `scripts/90_reconciliar_sync.py`
-- para na afirmação 1 — *"app.sync_run não tem nenhuma execução de 'Batida'"*.
-- Descobrir isso depois de religar custa a leitura errada de que o runner novo
-- não funciona.
--
-- POR QUE NÃO É MIGRATION
-- É **dado**, não schema — e dado de um tenant específico. A migration 21 já
-- insere uma linha assim, mas como prova viva, e a apaga no fim. Semear uma
-- linha real de produção por migration a criaria também em dev e no ensaio,
-- onde ela não corresponde a integração nenhuma.
--
-- EFEITO COLATERAL: NENHUM, E ISSO FOI CONFERIDO
-- Os dois leitores de `app.integration` são o `recordSyncRun` acima e o
-- `_PROVIDER_SQL` de `backend/operax/alertas/outbox.py`, que filtra
-- `provider in ('meta_cloud','z_api','uazapi')` — uma linha `secullum` é
-- invisível para ele. O índice único da migration 14 também só alcança os três
-- provedores de WhatsApp. Nenhuma view de `public` lê esta tabela.
--
-- ⛔ O QUE ESTE ARQUIVO NÃO RESOLVE
-- `app.job_execucao` carrega o **lock de sobreposição** — o índice único parcial
-- `(job) where status = 'running'`. `app.sync_run` não tem equivalente. Trocar
-- de diário sem trocar de lock entrega sobreposição silenciosa. É decisão
-- separada, e está no passo 7 do runbook.
--
-- Idempotente.
-- ============================================================================

do $$
declare
  v_tenant      uuid;
  v_tenants     int;
  v_integration uuid;
begin
  select count(*) into v_tenants from app.tenant;
  if v_tenants <> 1 then
    -- Com mais de um tenant, a qual deles a credencial de projeto pertence não
    -- é pergunta que este arquivo possa responder — a credencial do Secullum
    -- hoje é secret do projeto, não `app.integration_secret` por tenant.
    raise exception
      'app.tenant tem % linha(s); este arquivo só serve para o caso de um tenant só', v_tenants;
  end if;

  select id into strict v_tenant from app.tenant;

  insert into app.integration (tenant_id, provider, alias, active)
  values (v_tenant, 'secullum', 'secullum', true)
  on conflict (tenant_id, provider, alias) do update set active = true
  returning id into v_integration;

  raise notice 'integração secullum: % (tenant %)', v_integration, v_tenant;
end $$;

-- ----------------------------------------------------------------------------
-- Guarda: não basta a linha existir — o que importa é a escrita que ela
-- destrava. Aqui a gravação é feita de verdade e desfeita pelo bloco aninhado:
-- uma exceção dentro de `begin ... exception` desfaz o que aquele bloco
-- escreveu, e só isso.
-- ----------------------------------------------------------------------------
do $$
declare
  v_id     uuid;
  v_tenant uuid;
begin
  -- A mesma consulta do `recordSyncRun`, palavra por palavra: conferir por outro
  -- caminho provaria outra coisa.
  select id, tenant_id into v_id, v_tenant
    from app.integration
   where provider = 'secullum' and active
   order by created_at
   limit 1;

  if v_id is null then
    raise exception 'nenhuma integração secullum ativa — a linha não ficou';
  end if;

  begin
    insert into app.sync_run (
      tenant_id, integration_id, entity, scope, started_at, finished_at,
      status, records_read, records_written, records_skipped
    ) values (
      v_tenant, v_id, '__prova_janela__', 'incremental',
      now(), now(), 'completed', 0, 0, 0
    );
    raise exception using errcode = 'OP001';  -- desfaz a prova
  exception
    when sqlstate 'OP001' then
      raise notice 'OK: app.sync_run aceita escrita com esta integração (prova desfeita)';
  end;
end $$;
