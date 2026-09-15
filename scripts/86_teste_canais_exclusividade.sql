-- ============================================================================
-- OperaX — TESTE DE EXCLUSIVIDADE DOS CANAIS (as oito linhas da SPEC-CANAIS §2.2)
-- ----------------------------------------------------------------------------
-- A SPEC §2.2 executou os dois índices lado a lado — `integration_whatsapp_
-- unico_ativo` (migration 14) e `integration_telegram_unico_ativo`
-- (`ch_telegram_provider`) — e registrou oito comportamentos. Este arquivo os
-- afirma um a um, contra o banco migrado, em transação revertida.
--
-- ⛔ A LINHA 1 É A RAZÃO DE O ARQUIVO EXISTIR
-- "WhatsApp ativo + Telegram ativo, mesmo tenant, coexistem." É exatamente o
-- que quebra se alguém acrescentar `'telegram'` ao predicado do índice de
-- WhatsApp — e o sintoma ("liguei o Telegram e o WhatsApp desligou") chega
-- como bug de produto, não como erro de migration. Revisão de código não pega
-- isso; só o índice real, exercido, responde. Por isso as recusas das linhas
-- 2 e 3 afirmam também QUAL constraint recusou: uma recusa "por qualquer
-- motivo" ficaria verde com os dois provedores no mesmo índice.
--
-- Mais quatro garantias das migrations `ch_messaging_identity` e
-- `ch_channel_health`, pelo mesmo método (exercer, não ler):
--   * convite com `token_hash` repetido é recusado;
--   * segunda identidade VIGENTE para o mesmo titular é recusada — e depois de
--     revogar a primeira, a segunda entra (a história sobrevive);
--   * um chat_id vigente não pode ser de duas pessoas do mesmo tenant;
--   * `fn_record_channel_health` duas vezes com o mesmo status NÃO avança
--     `status_changed_at`; com status novo, avança.
--
-- Roda em transação revertida. Não deixa resíduo.
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/86_teste_canais_exclusividade.sql
-- ============================================================================

begin;

-- ---------------------------------------------------------------------------
-- Utilitários de asserção — o padrão do 97
-- ---------------------------------------------------------------------------
create or replace function pg_temp.assert_eq(rotulo text, obtido text, esperado text)
returns void language plpgsql as $$
begin
  if obtido is distinct from esperado then
    raise exception 'FALHA [%]: esperado %, obtido %', rotulo, esperado, obtido;
  end if;
  raise notice '  ok  % (%)', rotulo, obtido;
end $$;

create or replace function pg_temp.deve_passar(rotulo text, sql_text text)
returns void language plpgsql as $$
begin
  execute sql_text;
  raise notice '  ok  % — aceito', rotulo;
exception when others then
  if sqlerrm like 'FALHA%' then raise; end if;
  raise exception 'FALHA [%]: deveria ter passado e foi recusado: %', rotulo, sqlerrm;
end $$;

-- Recusado, e POR QUEM. Devolve o nome da constraint que barrou; a asserção
-- compara com o nome esperado. "Recusado por qualquer motivo" é o falso verde
-- deste arquivo: com `'telegram'` no índice de WhatsApp, a linha 3 continuaria
-- sendo recusada — pelo índice errado.
create or replace function pg_temp.recusado_por(rotulo text, sql_text text)
returns text language plpgsql as $$
declare
  v_constraint text;
begin
  begin
    execute sql_text;
  exception when others then
    get stacked diagnostics v_constraint = constraint_name;
    raise notice '  ok  % — recusado por %', rotulo, coalesce(nullif(v_constraint, ''), sqlerrm);
    return coalesce(nullif(v_constraint, ''), sqlerrm);
  end;
  raise exception 'FALHA [%]: deveria ter sido recusado e passou', rotulo;
end $$;

-- ---------------------------------------------------------------------------
-- Cenário mínimo: um tenant, uma unidade, um colaborador, um responsável
-- ---------------------------------------------------------------------------
insert into app.tenant (id, slug, name) values
  ('c3000000-0000-0000-0000-0000000000a1', 'tenant-canais', 'Cliente Canais');

insert into app.company (id, tenant_id, legal_name) values
  ('c3000000-0000-0000-0000-0000000000e1', 'c3000000-0000-0000-0000-0000000000a1', 'Empresa Canais LTDA');

insert into app.unit (id, tenant_id, company_id, code, name) values
  ('c3000000-0000-0000-0000-0000000000c1', 'c3000000-0000-0000-0000-0000000000a1',
   'c3000000-0000-0000-0000-0000000000e1', 'CANAIS-1', 'Unidade Canais');

insert into app.employee (id, tenant_id, company_id, unit_id, name) values
  ('c3000000-0000-0000-0000-0000000000b1', 'c3000000-0000-0000-0000-0000000000a1',
   'c3000000-0000-0000-0000-0000000000e1', 'c3000000-0000-0000-0000-0000000000c1', 'Colab Canais');

insert into app.contact (id, tenant_id, name, type, whatsapp) values
  ('c3000000-0000-0000-0000-00000000f001', 'c3000000-0000-0000-0000-0000000000a1',
   'Gestor Canais', 'person', '+5511999990101');

-- ---------------------------------------------------------------------------
\echo '--- SPEC-CANAIS §2.2 — as oito linhas'
-- ---------------------------------------------------------------------------
do $$
declare
  v_por text;
begin
  -- 1. WhatsApp ativo + Telegram ativo, mesmo tenant: COEXISTEM.
  perform pg_temp.deve_passar('linha 1a: meta_cloud ativo', $q$
    insert into app.integration (id, tenant_id, provider, active)
    values ('c3000000-0000-0000-0000-00000000d001', 'c3000000-0000-0000-0000-0000000000a1', 'meta_cloud', true)
  $q$);
  perform pg_temp.deve_passar('linha 1b: telegram ativo AO LADO do meta_cloud ativo (os índices não se atropelam)', $q$
    insert into app.integration (id, tenant_id, provider, active)
    values ('c3000000-0000-0000-0000-00000000d002', 'c3000000-0000-0000-0000-0000000000a1', 'telegram', true)
  $q$);
  perform pg_temp.assert_eq('linha 1: 2 integrações de canal ativas no mesmo tenant',
    (select count(*)::text from app.integration
      where tenant_id = 'c3000000-0000-0000-0000-0000000000a1' and active
        and provider in ('meta_cloud','z_api','uazapi','telegram')), '2');

  -- 2. Segundo provedor de WhatsApp ativo: recusado — pelo índice de WhatsApp.
  v_por := pg_temp.recusado_por('linha 2: segundo WhatsApp (z_api) ativo', $q$
    insert into app.integration (tenant_id, provider, active)
    values ('c3000000-0000-0000-0000-0000000000a1', 'z_api', true)
  $q$);
  perform pg_temp.assert_eq('linha 2: quem recusou foi integration_whatsapp_unico_ativo',
    v_por, 'integration_whatsapp_unico_ativo');

  -- 3. Segundo bot de Telegram ativo: recusado — pelo índice IRMÃO, não pelo
  --    de WhatsApp. Alias distinto de propósito: a unique (tenant, provider,
  --    alias) não é quem barra.
  v_por := pg_temp.recusado_por('linha 3: segundo bot de Telegram ativo', $q$
    insert into app.integration (tenant_id, provider, alias, active)
    values ('c3000000-0000-0000-0000-0000000000a1', 'telegram', 'segundo-bot', true)
  $q$);
  perform pg_temp.assert_eq('linha 3: quem recusou foi integration_telegram_unico_ativo',
    v_por, 'integration_telegram_unico_ativo');

  -- 4. Bot INATIVO ao lado do ativo: aceito — o histórico sobrevive.
  perform pg_temp.deve_passar('linha 4: bot inativo ao lado do ativo', $q$
    insert into app.integration (id, tenant_id, provider, alias, active)
    values ('c3000000-0000-0000-0000-00000000d003', 'c3000000-0000-0000-0000-0000000000a1', 'telegram', 'bot-antigo', false)
  $q$);

  -- 5. Identidade com contact_id E employee_id: recusada.
  v_por := pg_temp.recusado_por('linha 5: identidade com os dois titulares', $q$
    insert into app.messaging_identity (tenant_id, channel, contact_id, employee_id, external_id)
    values ('c3000000-0000-0000-0000-0000000000a1', 'telegram',
            'c3000000-0000-0000-0000-00000000f001', 'c3000000-0000-0000-0000-0000000000b1', '100')
  $q$);
  perform pg_temp.assert_eq('linha 5: quem recusou foi o check de um titular',
    v_por, 'messaging_identity_um_titular');

  -- 6. Identidade SEM titular: recusada — chat_id órfão não entra.
  v_por := pg_temp.recusado_por('linha 6: identidade sem titular', $q$
    insert into app.messaging_identity (tenant_id, channel, external_id)
    values ('c3000000-0000-0000-0000-0000000000a1', 'telegram', '101')
  $q$);
  perform pg_temp.assert_eq('linha 6: quem recusou foi o check de um titular',
    v_por, 'messaging_identity_um_titular');

  -- 7. Um titular de cada tipo: aceitos.
  perform pg_temp.deve_passar('linha 7a: identidade do responsável', $q$
    insert into app.messaging_identity (id, tenant_id, channel, contact_id, external_id)
    values ('c3000000-0000-0000-0000-000000001d01', 'c3000000-0000-0000-0000-0000000000a1', 'telegram',
            'c3000000-0000-0000-0000-00000000f001', '200')
  $q$);
  perform pg_temp.deve_passar('linha 7b: identidade do colaborador', $q$
    insert into app.messaging_identity (id, tenant_id, channel, employee_id, external_id)
    values ('c3000000-0000-0000-0000-000000001d02', 'c3000000-0000-0000-0000-0000000000a1', 'telegram',
            'c3000000-0000-0000-0000-0000000000b1', '201')
  $q$);

  -- 8. Estado final: 1 WhatsApp ativo, 1 Telegram ativo, 1 Telegram inativo.
  perform pg_temp.assert_eq('linha 8: 1 WhatsApp ativo',
    (select count(*)::text from app.integration
      where tenant_id = 'c3000000-0000-0000-0000-0000000000a1' and active
        and provider in ('meta_cloud','z_api','uazapi')), '1');
  perform pg_temp.assert_eq('linha 8: 1 Telegram ativo',
    (select count(*)::text from app.integration
      where tenant_id = 'c3000000-0000-0000-0000-0000000000a1' and active
        and provider = 'telegram'), '1');
  perform pg_temp.assert_eq('linha 8: 1 Telegram inativo',
    (select count(*)::text from app.integration
      where tenant_id = 'c3000000-0000-0000-0000-0000000000a1' and not active
        and provider = 'telegram'), '1');
end $$;

-- ---------------------------------------------------------------------------
\echo '--- O convite: token_hash único, validade de 7 dias'
-- ---------------------------------------------------------------------------
do $$
declare
  v_por text;
begin
  perform pg_temp.deve_passar('convite do colaborador', $q$
    insert into app.messaging_invite (tenant_id, channel, employee_id, token_hash)
    values ('c3000000-0000-0000-0000-0000000000a1', 'telegram',
            'c3000000-0000-0000-0000-0000000000b1', 'hash-aaaa')
  $q$);
  -- Repetido, e para OUTRO titular: o hash é único na tabela inteira. Um token
  -- que resolvesse para duas pessoas vincularia a errada.
  v_por := pg_temp.recusado_por('convite com token_hash repetido (outro titular)', $q$
    insert into app.messaging_invite (tenant_id, channel, contact_id, token_hash)
    values ('c3000000-0000-0000-0000-0000000000a1', 'telegram',
            'c3000000-0000-0000-0000-00000000f001', 'hash-aaaa')
  $q$);
  perform pg_temp.assert_eq('quem recusou foi messaging_invite_token_uk',
    v_por, 'messaging_invite_token_uk');
  -- O default do dono (item 4): 7 dias a partir de agora.
  perform pg_temp.assert_eq('expires_at default = now() + 7 dias',
    (select (expires_at = now() + interval '7 days')::text
       from app.messaging_invite where token_hash = 'hash-aaaa'), 'true');
  -- E os dois titulares também valem aqui.
  v_por := pg_temp.recusado_por('convite sem titular', $q$
    insert into app.messaging_invite (tenant_id, channel, token_hash)
    values ('c3000000-0000-0000-0000-0000000000a1', 'telegram', 'hash-bbbb')
  $q$);
  perform pg_temp.assert_eq('quem recusou foi o check de um titular do convite',
    v_por, 'messaging_invite_um_titular');
end $$;

-- ---------------------------------------------------------------------------
\echo '--- A identidade: uma vigente por titular, e a história sobrevive'
-- ---------------------------------------------------------------------------
do $$
declare
  v_por text;
begin
  -- Segunda identidade VIGENTE para o mesmo colaborador: recusada.
  v_por := pg_temp.recusado_por('segunda identidade vigente do mesmo colaborador', $q$
    insert into app.messaging_identity (tenant_id, channel, employee_id, external_id)
    values ('c3000000-0000-0000-0000-0000000000a1', 'telegram',
            'c3000000-0000-0000-0000-0000000000b1', '202')
  $q$);
  perform pg_temp.assert_eq('quem recusou foi messaging_identity_vigente_employee_uk',
    v_por, 'messaging_identity_vigente_employee_uk');

  -- E para o mesmo responsável.
  v_por := pg_temp.recusado_por('segunda identidade vigente do mesmo responsável', $q$
    insert into app.messaging_identity (tenant_id, channel, contact_id, external_id)
    values ('c3000000-0000-0000-0000-0000000000a1', 'telegram',
            'c3000000-0000-0000-0000-00000000f001', '203')
  $q$);
  perform pg_temp.assert_eq('quem recusou foi messaging_identity_vigente_contact_uk',
    v_por, 'messaging_identity_vigente_contact_uk');

  -- O MESMO chat_id vigente em duas pessoas do tenant: recusado. É o irmão da
  -- regra 7 — conteúdo individual na tela de quem não é o titular.
  -- (Precisa de um segundo titular sem identidade: outro responsável.)
  insert into app.contact (id, tenant_id, name, type, whatsapp) values
    ('c3000000-0000-0000-0000-00000000f002', 'c3000000-0000-0000-0000-0000000000a1',
     'Outro Gestor', 'person', '+5511999990102');
  v_por := pg_temp.recusado_por('o chat_id 201 (do colaborador) numa segunda pessoa', $q$
    insert into app.messaging_identity (tenant_id, channel, contact_id, external_id)
    values ('c3000000-0000-0000-0000-0000000000a1', 'telegram',
            'c3000000-0000-0000-0000-00000000f002', '201')
  $q$);
  perform pg_temp.assert_eq('quem recusou foi messaging_identity_vigente_external_uk',
    v_por, 'messaging_identity_vigente_external_uk');

  -- Revogada a primeira, a segunda entra — e a primeira FICA.
  update app.messaging_identity
     set revoked_at = now(), revoked_reason = 'bloqueou o bot'
   where id = 'c3000000-0000-0000-0000-000000001d02';
  perform pg_temp.deve_passar('depois de revogar, a segunda identidade do colaborador entra', $q$
    insert into app.messaging_identity (tenant_id, channel, employee_id, external_id)
    values ('c3000000-0000-0000-0000-0000000000a1', 'telegram',
            'c3000000-0000-0000-0000-0000000000b1', '204')
  $q$);
  perform pg_temp.assert_eq('o colaborador tem 2 linhas (a história sobrevive)',
    (select count(*)::text from app.messaging_identity
      where employee_id = 'c3000000-0000-0000-0000-0000000000b1'), '2');
  perform pg_temp.assert_eq('e exatamente 1 vigente',
    (select count(*)::text from app.messaging_identity
      where employee_id = 'c3000000-0000-0000-0000-0000000000b1' and revoked_at is null), '1');
  -- O chat_id revogado pode reaparecer em outra pessoa? Sim — o índice é
  -- parcial em `revoked_at is null`. Quem trocou de aparelho e o número foi
  -- reatribuído não fica preso ao vínculo antigo.
  perform pg_temp.deve_passar('o chat_id 201, agora revogado, pode ser vinculado a outra pessoa', $q$
    insert into app.messaging_identity (tenant_id, channel, contact_id, external_id)
    values ('c3000000-0000-0000-0000-0000000000a1', 'telegram',
            'c3000000-0000-0000-0000-00000000f002', '201')
  $q$);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- fn_record_channel_health: status_changed_at só avança quando o status muda'
-- ---------------------------------------------------------------------------
-- `now()` é constante na transação, então "avançou" não é observável entre
-- duas chamadas aqui. Recua-se o relógio da linha à mão (uma hora), chama-se
-- de novo, e o que se mede é: com o MESMO status, `checked_at` volta para
-- agora e `status_changed_at` continua no passado; com status NOVO, os dois
-- voltam para agora.
do $$
declare
  v_bot   uuid := 'c3000000-0000-0000-0000-00000000d002';
  v_por   text;
begin
  perform app.fn_record_channel_health(v_bot, 'connected', 'getMe ok');
  perform pg_temp.assert_eq('primeira medição: 1 linha, connected',
    (select status from app.channel_health where integration_id = v_bot), 'connected');
  perform pg_temp.assert_eq('o tenant veio da integração, não do chamador',
    (select tenant_id::text from app.channel_health where integration_id = v_bot),
    'c3000000-0000-0000-0000-0000000000a1');

  -- Envelhece a linha uma hora.
  update app.channel_health
     set checked_at = now() - interval '1 hour',
         status_changed_at = now() - interval '1 hour'
   where integration_id = v_bot;

  -- Mesmo status: checked_at avança, status_changed_at NÃO.
  perform app.fn_record_channel_health(v_bot, 'connected', 'getMe ok de novo');
  perform pg_temp.assert_eq('mesmo status: continua 1 linha (upsert, não insert)',
    (select count(*)::text from app.channel_health where integration_id = v_bot), '1');
  perform pg_temp.assert_eq('mesmo status: checked_at voltou para agora',
    (select (checked_at = now())::text from app.channel_health where integration_id = v_bot), 'true');
  perform pg_temp.assert_eq('mesmo status: status_changed_at FICOU uma hora atrás',
    (select (status_changed_at = now() - interval '1 hour')::text
       from app.channel_health where integration_id = v_bot), 'true');
  perform pg_temp.assert_eq('mesmo status: o detail é o da última medição',
    (select detail from app.channel_health where integration_id = v_bot), 'getMe ok de novo');

  -- Status novo: os dois avançam.
  perform app.fn_record_channel_health(v_bot, 'disconnected', '401 Unauthorized');
  perform pg_temp.assert_eq('status novo: status mudou',
    (select status from app.channel_health where integration_id = v_bot), 'disconnected');
  perform pg_temp.assert_eq('status novo: status_changed_at avançou para agora',
    (select (status_changed_at = now())::text from app.channel_health where integration_id = v_bot), 'true');

  -- Falha alto, não em silêncio: integração inexistente e status fora do check.
  v_por := pg_temp.recusado_por('integração inexistente', $q$
    select app.fn_record_channel_health('00000000-0000-0000-0000-000000000000', 'connected', null)
  $q$);
  v_por := pg_temp.recusado_por('status fora do domínio', format($q$
    select app.fn_record_channel_health(%L, 'reconnecting', null)
  $q$, v_bot));
  perform pg_temp.assert_eq('status fora do domínio: quem recusou foi o check',
    v_por, 'channel_health_status_check');
end $$;

\echo ''
\echo '================================================'
\echo ' EXCLUSIVIDADE DOS CANAIS: TODOS OS TESTES OK'
\echo '================================================'

rollback;
