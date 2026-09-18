-- ============================================================================
-- OperaX — TESTE DAS CAMADAS DO ASSISTENTE (SPEC-AGENTE §2, §3a, §3b, §3c, §3d, §3e, §4, §5)
-- ----------------------------------------------------------------------------
-- 164 asserções (95 do A1 + 46 do A2 + 23 do A3), contadas pelas chamadas a
-- assert_eq, deve_falhar e rpc_recusa. Garantias que só valem se o banco as
-- sustentar:
--
--   A) As sete linhas da SPEC §3a — coerência de escopo, modelo só na
--      plataforma, versão imutável, um ponteiro por escopo, versão apontada
--      indestrutível E o cascade de app.tenant passando (a 7, que contradiz a
--      6 no papel e só passa porque o ponteiro morre primeiro).
--   B) A RPC de publicação, chamada COMO O PAPEL: as cinco recusas por código,
--      o `draft_unchanged` contra a versão APONTADA (não a última), e o
--      `not_admin` para o owner de OUTRO tenant — que é o caso que separa
--      `is_admin` de `has_tenant` num definer.
--   C) A RLS como os papéis: quem lê a plataforma, quem lê o tenant, quem
--      abre o rascunho, e que ninguém autenticado escreve versão ou ponteiro
--      pela tabela (é grant, antes de policy).
--   D) A trava de concorrência, na medida do SQL: o `for update` é a primeira
--      instrução do corpo da função, lido do catálogo.
--   E) Ciclo 2: o escopo amarrado à versão (ponteiro e rascunho só alcançam
--      versão do próprio (tenant, camada) — inclusive como owner pela tabela,
--      que é o caminho do painel), `not_admin` antes de `draft_not_found` (o
--      owner de outro tenant não aprende se este tem rascunho), `max + 1`
--      sobrevivendo a uma versão apagada pelo dono, o `update` final do
--      definer preso ao tenant, e `updated_at` do rascunho mantido por trigger.
--   A2) Capacidades (SPEC-AGENTE §4.1, a invariante virada em teste): a
--      tabela de escopo com as três policies da parada e ninguém apagando; o
--      catálogo pela régua única `fn_assistant_catalog` — ausência = habilitada,
--      desabilitar tira dos dois papéis, REABILITAR NÃO CONCEDE domínio ao
--      supervisor; quem não é membro recebe zero linhas; métrica inativa não
--      aparece nem com escopo `enabled = true` (a EURECA manda primeiro).
--   A3) O vínculo do turno (SPEC-AGENTE §3c; §7.1 decidida pelo dono em
--      17/09/2026): as três colunas de app.ai_query e as duas checks do hash;
--      a FK para a versão SEM cascade (apagar versão apontada por um turno é
--      recusado como dono do banco); o índice parcial do tráfego real;
--      `ai_query_read` funcionalmente inalterada (owner lê o tenant,
--      supervisor só o próprio, o outro tenant nada — o `98` não cobre
--      ai_query); e a MEDIÇÃO de que a FK aceita versão de outro tenant — é
--      log, e não há trigger de escopo nele de propósito.
--
-- A fidelidade da transcrição da v1 (o texto da migration renderizado ==
-- o que agente._prompt produzia, pinado em fixture antes de o literal sair)
-- é pytest — `backend/tests/test_agente_prompt_seed.py` — porque só o Python
-- sabe renderizar.
--
-- Roda em transação revertida. Não deixa resíduo.
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/97_teste_assistente.sql
-- ============================================================================

begin;

-- ---------------------------------------------------------------------------
-- Cenário: dois tenants, três pessoas
-- ---------------------------------------------------------------------------
insert into auth.users (id, email) values
  ('a1000000-0000-0000-0000-000000000001', 'owner.a@assistente'),
  ('a1000000-0000-0000-0000-000000000002', 'supervisor.a@assistente'),
  ('a1000000-0000-0000-0000-000000000004', 'owner.b@assistente');

insert into app.tenant (id, slug, name) values
  ('a1a00000-0000-0000-0000-00000000000a', 'assist-a', 'Cliente Assistente A'),
  ('a1b00000-0000-0000-0000-00000000000b', 'assist-b', 'Cliente Assistente B');

insert into app.tenant_member (tenant_id, user_id, role) values
  ('a1a00000-0000-0000-0000-00000000000a', 'a1000000-0000-0000-0000-000000000001', 'owner'),
  ('a1a00000-0000-0000-0000-00000000000a', 'a1000000-0000-0000-0000-000000000002', 'unit_supervisor'),
  ('a1b00000-0000-0000-0000-00000000000b', 'a1000000-0000-0000-0000-000000000004', 'owner');

-- ---------------------------------------------------------------------------
-- Utilitários
-- ---------------------------------------------------------------------------
create or replace function pg_temp.assert_eq(rotulo text, obtido bigint, esperado bigint)
returns void language plpgsql as $$
begin
  if obtido is distinct from esperado then
    raise exception 'FALHA [%]: esperado %, obtido %', rotulo, esperado, obtido;
  end if;
  raise notice '  ok  % (%)', rotulo, obtido;
end $$;

-- Executa e exige recusa cuja mensagem CONTÉM o trecho — para constraint,
-- trigger e permissão, cujas mensagens são do Postgres.
create or replace function pg_temp.deve_falhar(rotulo text, sql_text text, trecho text)
returns void language plpgsql as $$
begin
  begin
    execute sql_text;
  exception when others then
    if sqlerrm not like '%' || trecho || '%' then
      raise exception 'FALHA [%]: recusado pelo motivo errado — esperava "%", veio "%"', rotulo, trecho, sqlerrm;
    end if;
    raise notice '  ok  % — recusado: %', rotulo, left(sqlerrm, 60);
    return;
  end;
  raise exception 'FALHA [%]: deveria ter sido recusado e passou', rotulo;
end $$;

-- Executa e devolve a MENSAGEM da recusa (vazio se passou) — para afirmar
-- QUEM recusou quando dois guardas poderiam.
create or replace function pg_temp.deve_falhar_msg(sql_text text)
returns text language plpgsql as $$
begin
  execute sql_text;
  return '';
exception when others then
  return sqlerrm;
end $$;

-- Chama a RPC como quem está na sessão e exige o código EXATO, com P0001.
-- Mensagem = código é o contrato da SPEC §3d; "parecido" não serve.
create or replace function pg_temp.rpc_recusa(rotulo text, p_tenant uuid, codigo text)
returns void language plpgsql as $$
begin
  begin
    perform * from public.fn_publish_assistant_prompt(p_tenant);
  exception when others then
    if sqlerrm <> codigo or sqlstate <> 'P0001' then
      raise exception 'FALHA [%]: esperava % (P0001), veio % (%)', rotulo, codigo, sqlerrm, sqlstate;
    end if;
    raise notice '  ok  % — %', rotulo, codigo;
    return;
  end;
  raise exception 'FALHA [%]: a RPC deveria ter recusado com % e publicou', rotulo, codigo;
end $$;

-- ===========================================================================
\echo '--- A. As sete linhas da SPEC §3a (como dono do banco)'
-- ===========================================================================
do $$
declare
  v_platform uuid;
  v_pointed  uuid;
  v_n        bigint;
begin
  -- A v1 da plataforma existe e está apontada — o chão de tudo o que segue.
  select id into v_platform from app.assistant_prompt_version
   where layer = 'platform' and tenant_id is null and version_number = 1;
  if v_platform is null then raise exception 'FALHA: a v1 da plataforma não foi semeada'; end if;
  select version_id into v_pointed from app.assistant_prompt_pointer where layer = 'platform';
  perform pg_temp.assert_eq('0. o ponteiro de plataforma aponta para a v1',
    case when v_pointed = v_platform then 1 else 0 end, 1);

  -- 1. camada platform COM tenant_id
  perform pg_temp.deve_falhar('1. platform com tenant_id',
    $q$insert into app.assistant_prompt_version (tenant_id, layer, version_number, content)
       values ('a1a00000-0000-0000-0000-00000000000a', 'platform', 9, 'x')$q$,
    'assistant_prompt_scope_coerente');

  -- 2. camada tenant escolhendo model
  perform pg_temp.deve_falhar('2. tenant escolhendo model',
    $q$insert into app.assistant_prompt_version (tenant_id, layer, version_number, content, model)
       values ('a1a00000-0000-0000-0000-00000000000a', 'tenant', 9, 'x', 'gpt-5.4-mini')$q$,
    'assistant_prompt_modelo_so_na_plataforma');

  -- 3. um platform + um tenant válidos: aceitos (a platform é a v1 semeada).
  --    Dentro de savepoint para não interferir na numeração da RPC adiante.
  begin
    insert into app.assistant_prompt_version (tenant_id, layer, version_number, content)
    values ('a1a00000-0000-0000-0000-00000000000a', 'tenant', 9, 'linha 3');
    select count(*) into v_n from app.assistant_prompt_version
     where (layer = 'platform' and tenant_id is null)
        or (tenant_id = 'a1a00000-0000-0000-0000-00000000000a' and version_number = 9);
    perform pg_temp.assert_eq('3. um platform + um tenant válidos são aceitos', v_n, 2);
    raise exception using errcode = 'P9999', message = 'desfaz a linha 3';
  exception when sqlstate 'P9999' then
    null;
  end;

  -- 4. update numa versão: o trigger recusa com a frase que ensina o caminho
  perform pg_temp.deve_falhar('4. update na versão (mesmo como dono do banco)',
    format($q$update app.assistant_prompt_version set content = content || ' ' where id = %L$q$, v_platform),
    'mudança = versão nova; rollback = mover o ponteiro');
  perform pg_temp.deve_falhar('4b. update em coluna de ciclo de vida também (nada isento)',
    format($q$update app.assistant_prompt_version set created_at = now() where id = %L$q$, v_platform),
    'imutável');

  -- 5. segundo ponteiro de plataforma (tenant_id NULL nos dois)
  perform pg_temp.deve_falhar('5. segundo ponteiro de plataforma',
    format($q$insert into app.assistant_prompt_pointer (tenant_id, layer, version_id)
              values (null, 'platform', %L)$q$, v_platform),
    'assistant_pointer_platform_uk');

  -- 6. delete da versão APONTADA
  perform pg_temp.deve_falhar('6. delete da versão apontada',
    format($q$delete from app.assistant_prompt_version where id = %L$q$, v_platform),
    'assistant_prompt_pointer');

  -- 3b. o limite de tamanho da camada vale na escrita (SPEC §1)
  perform pg_temp.deve_falhar('3b. camada acima de 12000 caracteres',
    $q$insert into app.assistant_prompt_version (tenant_id, layer, version_number, content)
       values ('a1a00000-0000-0000-0000-00000000000a', 'tenant', 9, repeat('x', 12001))$q$,
    'assistant_prompt_tamanho');
  perform pg_temp.deve_falhar('3c. rascunho acima de 12000 caracteres',
    $q$insert into app.assistant_draft (tenant_id, content)
       values ('a1a00000-0000-0000-0000-00000000000a', repeat('x', 12001))$q$,
    'assistant_draft_tamanho');
end $$;

-- O backend (service_role) tem update na versão — e o trigger o barra do
-- mesmo jeito; e não tem delete, por grant. Append-only para o Caminho 2 também.
set local role service_role;
do $$
declare v_platform uuid;
begin
  select id into v_platform from app.assistant_prompt_version where layer = 'platform' and version_number = 1;
  perform pg_temp.deve_falhar('4c. service_role também não altera versão (trigger)',
    format($q$update app.assistant_prompt_version set content = 'x' where id = %L$q$, v_platform),
    'imutável');
  perform pg_temp.deve_falhar('6b. service_role não apaga versão (sem grant, apontada ou não)',
    $q$delete from app.assistant_prompt_version where tenant_id is not null$q$,
    'permission denied');
  perform pg_temp.deve_falhar('6c. service_role não apaga ponteiro',
    $q$delete from app.assistant_prompt_pointer$q$,
    'permission denied');
  perform pg_temp.deve_falhar('6d. service_role não apaga rascunho',
    $q$delete from app.assistant_draft$q$,
    'permission denied');
end $$;
reset role;

-- 7. delete do tenant inteiro PASSA e leva versão, ponteiro e rascunho.
--    Com a versão APONTADA antes de apagar: sem isso, um cascade no
--    version_id do ponteiro passaria também, e a linha 6 estaria furada.
do $$
declare
  v_c   uuid := 'a1c00000-0000-0000-0000-00000000000c';
  v_ver uuid;
  v_n   bigint;
begin
  insert into app.tenant (id, slug, name) values (v_c, 'assist-c', 'Cliente Assistente C');
  insert into app.assistant_prompt_version (tenant_id, layer, version_number, content)
  values (v_c, 'tenant', 1, 'camada do C') returning id into v_ver;
  insert into app.assistant_prompt_pointer (tenant_id, layer, version_id) values (v_c, 'tenant', v_ver);
  insert into app.assistant_draft (tenant_id, content, frozen_from_version_id) values (v_c, 'camada do C', v_ver);

  perform pg_temp.assert_eq('7a. o tenant C tem versão apontada e rascunho antes de sumir',
    (select count(*) from app.assistant_prompt_pointer where tenant_id = v_c)
    + (select count(*) from app.assistant_draft where tenant_id = v_c), 2);

  delete from app.tenant where id = v_c;

  select count(*) into v_n from app.assistant_prompt_version where tenant_id = v_c;
  perform pg_temp.assert_eq('7b. delete do tenant passou e a versão foi junto', v_n, 0);
  select count(*) into v_n from app.assistant_prompt_pointer where tenant_id = v_c;
  perform pg_temp.assert_eq('7c. e o ponteiro', v_n, 0);
  select count(*) into v_n from app.assistant_draft where tenant_id = v_c;
  perform pg_temp.assert_eq('7d. e o rascunho', v_n, 0);
  perform pg_temp.assert_eq('7e. a plataforma continua de pé',
    (select count(*) from app.assistant_prompt_version where tenant_id is null), 1);
end $$;

-- 8. Escopo amarrado à versão (ciclo 2). A FK aceita qualquer versão; o
--    trigger util.assistant_scope_matches exige (tenant_id, layer) iguais.
--    Tudo como dono do banco — que é quem alcança o ponteiro pela tabela.
--    Desfeito no fim pelo P9999: nada disto sobra para a seção B.
do $$
declare
  v_a uuid := 'a1a00000-0000-0000-0000-00000000000a';
  v_b uuid := 'a1b00000-0000-0000-0000-00000000000b';
  v_a9 uuid; v_b9 uuid; v_platform uuid;
begin
  begin
    insert into app.assistant_prompt_version (tenant_id, layer, version_number, content)
    values (v_a, 'tenant', 9, 'A9') returning id into v_a9;
    insert into app.assistant_prompt_version (tenant_id, layer, version_number, content)
    values (v_b, 'tenant', 9, 'B9') returning id into v_b9;
    select id into v_platform from app.assistant_prompt_version where layer = 'platform';

    perform pg_temp.deve_falhar('8a. D1: ponteiro de A apontando para versão de B',
      format($q$insert into app.assistant_prompt_pointer (tenant_id, layer, version_id) values (%L, 'tenant', %L)$q$, v_a, v_b9),
      'versão de outro escopo');
    perform pg_temp.deve_falhar('8b. D2: ponteiro de tenant apontando para a versão de PLATAFORMA',
      format($q$insert into app.assistant_prompt_pointer (tenant_id, layer, version_id) values (%L, 'tenant', %L)$q$, v_b, v_platform),
      'versão de outro escopo');
    perform pg_temp.deve_falhar('8c. D2b: ponteiro de plataforma movido para versão de tenant',
      format($q$update app.assistant_prompt_pointer set version_id = %L where layer = 'platform'$q$, v_a9),
      'versão de outro escopo');
    perform pg_temp.deve_falhar('8d. D3: rascunho de A partindo de versão de B',
      format($q$insert into app.assistant_draft (tenant_id, content, frozen_from_version_id) values (%L, 'x', %L)$q$, v_a, v_b9),
      'versão de outro escopo');

    -- O positivo: mesmo escopo passa (o trigger não barra o legítimo), e o
    -- update que muda para outro escopo cai — é update, não só insert.
    insert into app.assistant_prompt_pointer (tenant_id, layer, version_id) values (v_a, 'tenant', v_a9);
    perform pg_temp.assert_eq('8e. ponteiro de A na versão de A passa',
      (select count(*) from app.assistant_prompt_pointer where tenant_id = v_a and version_id = v_a9), 1);
    perform pg_temp.deve_falhar('8f. D1 por update: mover o ponteiro de A para versão de B',
      format($q$update app.assistant_prompt_pointer set version_id = %L where tenant_id = %L$q$, v_b9, v_a),
      'versão de outro escopo');
    insert into app.assistant_draft (tenant_id, content, frozen_from_version_id) values (v_a, 'x', v_a9);
    perform pg_temp.assert_eq('8g. rascunho de A partindo da versão de A passa; nulo também',
      (select count(*) from app.assistant_draft where tenant_id = v_a and frozen_from_version_id = v_a9), 1);
    update app.assistant_draft set frozen_from_version_id = null where tenant_id = v_a;
    -- A versão que não existe cai no TRIGGER, não na FK: é o que fecha o
    -- caminho "invoker não enxerga, FK aceita" medido no ciclo 2.
    perform pg_temp.assert_eq('8h. versão inexistente é recusada pelo trigger (não entregue à FK)',
      case when (select pg_temp.deve_falhar_msg(
        format($q$update app.assistant_draft set frozen_from_version_id = %L where tenant_id = %L$q$,
               'a1f00000-0000-0000-0000-0000000000ff', v_a))) like '%não existe%' then 1 else 0 end, 1);

    raise exception using errcode = 'P9999', message = 'desfaz o cenário 8';
  exception when sqlstate 'P9999' then
    null;
  end;
  perform pg_temp.assert_eq('8i. o cenário 8 não deixou rastro',
    (select count(*) from app.assistant_prompt_version where version_number = 9)
    + (select count(*) from app.assistant_draft)
    + (select count(*) from app.assistant_prompt_pointer where tenant_id is not null), 0);
end $$;

-- ===========================================================================
\echo '--- D. A trava de concorrência, lida do catálogo'
-- ===========================================================================
do $$
declare v_src text; v_body text; v_lock int; v_first_if int;
begin
  select pg_get_functiondef(p.oid) into v_src
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname = 'fn_publish_assistant_prompt';
  if v_src is null then raise exception 'FALHA: fn_publish_assistant_prompt não existe'; end if;
  v_body := substr(v_src, position('begin' in lower(v_src)));
  v_lock := position('for update' in lower(v_body));
  perform pg_temp.assert_eq('o for update está no corpo', case when v_lock > 0 then 1 else 0 end, 1);
  -- Nada é decidido antes de travar: o primeiro `if`, o primeiro `raise` e a
  -- primeira leitura de outra tabela vêm DEPOIS do `for update`.
  v_first_if := least(
    nullif(position(E'\n  if ' in v_body), 0),
    nullif(position('raise exception' in v_body), 0),
    nullif(position('assistant_prompt_pointer' in v_body), 0),
    nullif(position('is_admin' in v_body), 0));
  perform pg_temp.assert_eq('e é a primeira instrução (antes de qualquer if, raise ou outra tabela)',
    case when v_lock < v_first_if then 1 else 0 end, 1);
  perform pg_temp.assert_eq('a trava é no rascunho do tenant pedido',
    case when v_body like '%from app.assistant_draft d%where d.tenant_id = p_tenant_id%for update%' then 1 else 0 end, 1);
end $$;

-- ===========================================================================
\echo '--- B. A RPC, chamada como o papel'
-- ===========================================================================
-- Identidade como o 98 faz — `set role authenticated` + a claim. As DUAS
-- grafias vão juntas em cada troca: `auth.uid()` faz coalesce delas, e a
-- falha do segundo ramo é muda (nulo vira zero linha, não erro).

-- --- O bit que não vaza: `not_admin` vem ANTES de `draft_not_found`
-- Com a ordem invertida, o owner de B chamando com o id de A aprendia se A
-- tem rascunho — e se A existe. Aqui A ainda NÃO tem rascunho, e a resposta
-- tem de ser a mesma de quando tiver (mais abaixo): not_admin.
\echo '    owner B chamando com o tenant A, antes de A ter rascunho'
set local role authenticated;
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000004';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000004","role":"authenticated"}';
do $$ begin
  perform pg_temp.rpc_recusa('owner B publicando A, que ainda não tem rascunho',
    'a1a00000-0000-0000-0000-00000000000a', 'not_admin');
  perform pg_temp.rpc_recusa('owner B publicando um tenant que não existe',
    'a1f00000-0000-0000-0000-0000000000ff', 'not_admin');
end $$;

\echo '    owner A'
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000001';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000001","role":"authenticated"}';

do $$
declare
  v_a uuid := 'a1a00000-0000-0000-0000-00000000000a';
  r record;
  v_v1 uuid; v_v2 uuid;
begin
  -- Sem rascunho ainda: draft_not_found (é o owner, então passou de not_admin).
  perform pg_temp.rpc_recusa('owner A sem rascunho', v_a, 'draft_not_found');

  -- O owner escreve o rascunho pela tabela (§7.3: a policy é de escrita).
  -- `updated_at` explícito e velho: o trigger é `before update`, então o
  -- insert guarda o valor — e é isso que deixa medir o update a seguir.
  insert into app.assistant_draft (tenant_id, content, updated_by, updated_at)
  values (v_a, 'Vocabulário do cliente A, v0.', auth.uid(), '2000-01-01');
  perform pg_temp.assert_eq('owner A escreveu o rascunho de A',
    (select count(*) from app.assistant_draft where tenant_id = v_a), 1);
  perform pg_temp.assert_eq('o insert guardou o updated_at explícito (o trigger é só de update)',
    (select count(*) from app.assistant_draft where tenant_id = v_a and updated_at = '2000-01-01'), 1);

  -- Altera o content SEM tocar updated_at: o trigger tem de mover a data.
  update app.assistant_draft set content = 'Vocabulário do cliente A, v1.' where tenant_id = v_a;
  perform pg_temp.assert_eq('owner A alterou o content sem tocar updated_at, e updated_at mexeu (= now())',
    (select count(*) from app.assistant_draft where tenant_id = v_a and updated_at = now()), 1);

  -- Primeira publicação: v1, ponteiro na v1, previous nulo, rascunho congelado da v1.
  select * into r from public.fn_publish_assistant_prompt(v_a);
  perform pg_temp.assert_eq('1a publicação devolve version_number 1', r.version_number, 1);
  perform pg_temp.assert_eq('e previous_version_id nulo', case when r.previous_version_id is null then 1 else 0 end, 1);
  v_v1 := r.version_id;
  perform pg_temp.assert_eq('o ponteiro de A aponta para a v1',
    (select count(*) from app.assistant_prompt_pointer where tenant_id = v_a and version_id = v_v1), 1);
  perform pg_temp.assert_eq('o rascunho ficou frozen_from_version_id = v1',
    (select count(*) from app.assistant_draft where tenant_id = v_a and frozen_from_version_id = v_v1), 1);
  perform pg_temp.assert_eq('a versão registra quem publicou (created_by = auth.uid())',
    (select count(*) from app.assistant_prompt_version where id = v_v1 and created_by = auth.uid()), 1);

  -- Publicar de novo sem mudar: draft_unchanged e NENHUMA versão nova.
  perform pg_temp.rpc_recusa('publicar de novo sem mudar', v_a, 'draft_unchanged');
  perform pg_temp.assert_eq('e o tenant A continua com 1 versão',
    (select count(*) from app.assistant_prompt_version where tenant_id = v_a), 1);

  -- Muda e publica: v2, previous = v1.
  update app.assistant_draft set content = 'Vocabulário do cliente A, v2.' where tenant_id = v_a;
  select * into r from public.fn_publish_assistant_prompt(v_a);
  perform pg_temp.assert_eq('2a publicação devolve version_number 2', r.version_number, 2);
  perform pg_temp.assert_eq('e previous_version_id = v1', case when r.previous_version_id = v_v1 then 1 else 0 end, 1);
  v_v2 := r.version_id;
  perform pg_temp.assert_eq('o ponteiro de A moveu para a v2',
    (select count(*) from app.assistant_prompt_pointer where tenant_id = v_a and version_id = v_v2), 1);
  perform pg_temp.assert_eq('um ponteiro só para o tenant A (o upsert não duplicou)',
    (select count(*) from app.assistant_prompt_pointer where tenant_id = v_a), 1);

  -- Rascunho em branco: draft_empty, e nada publicado. Fica em branco para o
  -- supervisor logo abaixo.
  update app.assistant_draft set content = '   ' where tenant_id = v_a;
  perform pg_temp.rpc_recusa('rascunho em branco', v_a, 'draft_empty');
  perform pg_temp.assert_eq('e o tenant A continua com 2 versões',
    (select count(*) from app.assistant_prompt_version where tenant_id = v_a), 2);
end $$;

-- --- A ordem 1 < 3: quem não é admin não aprende que o rascunho está em branco
\echo '    supervisor de A, com o rascunho de A em branco'
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000002';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000002","role":"authenticated"}';
do $$ begin
  perform pg_temp.rpc_recusa('supervisor de A com rascunho em branco recebe not_admin, não draft_empty',
    'a1a00000-0000-0000-0000-00000000000a', 'not_admin');
end $$;

-- --- O falso verde do draft_unchanged: comparar com a ÚLTIMA em vez da APONTADA
-- Rollback = mover o ponteiro de A de volta para a v1 (como dono do banco).
-- O rascunho volta a ser igual à v2. Publicar TEM de criar a v3: o rascunho
-- difere do que está no ar. Uma função que comparasse com max(version_number)
-- recusaria aqui — e o rollback ficaria impossível de desfazer pela tela.
reset role;
update app.assistant_draft set content = 'Vocabulário do cliente A, v2.'
 where tenant_id = 'a1a00000-0000-0000-0000-00000000000a';
update app.assistant_prompt_pointer p
   set version_id = v.id
  from app.assistant_prompt_version v
 where p.tenant_id = 'a1a00000-0000-0000-0000-00000000000a' and p.layer = 'tenant'
   and v.tenant_id = p.tenant_id and v.layer = 'tenant' and v.version_number = 1;

set local role authenticated;
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000001';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000001","role":"authenticated"}';
do $$
declare
  v_a uuid := 'a1a00000-0000-0000-0000-00000000000a';
  r record; v_v1 uuid;
begin
  select id into v_v1 from app.assistant_prompt_version where tenant_id = v_a and version_number = 1;
  perform pg_temp.assert_eq('o rollback deixou a v1 no ar com o rascunho igual à v2',
    (select count(*) from app.assistant_prompt_pointer where tenant_id = v_a and version_id = v_v1), 1);
  select * into r from public.fn_publish_assistant_prompt(v_a);
  perform pg_temp.assert_eq('publicar depois do rollback cria a v3 (compara com a APONTADA, não com a última)',
    r.version_number, 3);
  perform pg_temp.assert_eq('e previous_version_id é a v1, a que estava no ar',
    case when r.previous_version_id = v_v1 then 1 else 0 end, 1);
end $$;

-- --- max + 1, não count + 1: uma versão apagada pelo dono do banco não pode
-- fazer a próxima colidir com um número ainda ocupado.
reset role;
do $$
declare v_a uuid := 'a1a00000-0000-0000-0000-00000000000a';
begin
  perform pg_temp.assert_eq('A tem 3 versões e o ponteiro está na v3',
    (select count(*) from app.assistant_prompt_version v
      where v.tenant_id = v_a) + (select count(*) from app.assistant_prompt_pointer p
      join app.assistant_prompt_version v on v.id = p.version_id
      where p.tenant_id = v_a and v.version_number = 3), 4);
  -- v1 não é apontada por ninguém (ponteiro na v3, rascunho partiu da v3).
  delete from app.assistant_prompt_version where tenant_id = v_a and version_number = 1;
  perform pg_temp.assert_eq('o dono do banco apagou a v1 não apontada: A fica com 2 versões (v2, v3)',
    (select count(*) from app.assistant_prompt_version where tenant_id = v_a), 2);
end $$;

set local role authenticated;
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000001';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000001","role":"authenticated"}';
do $$
declare
  v_a uuid := 'a1a00000-0000-0000-0000-00000000000a';
  r record; v_v3 uuid;
begin
  select id into v_v3 from app.assistant_prompt_version where tenant_id = v_a and version_number = 3;
  update app.assistant_draft set content = 'Vocabulário do cliente A, v4.' where tenant_id = v_a;
  select * into r from public.fn_publish_assistant_prompt(v_a);
  perform pg_temp.assert_eq('com a v1 apagada, publicar numera v4 (max + 1), não colide como count + 1 colidiria',
    r.version_number, 4);
  perform pg_temp.assert_eq('e previous_version_id é a v3',
    case when r.previous_version_id = v_v3 then 1 else 0 end, 1);
  perform pg_temp.assert_eq('A volta a ter 3 versões (v2, v3, v4)',
    (select count(*) from app.assistant_prompt_version where tenant_id = v_a), 3);
  -- Guarda o id da v4 para a conferência de escopo do rascunho, abaixo.
  perform set_config('a1.a_last', r.version_id::text, true);
end $$;

-- --- Quem não pode publicar
\echo '    owner B chamando com o tenant A'
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000004';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000004","role":"authenticated"}';
do $$
declare r record;
begin
  -- É a RPC que recusa, não a policy: definer não herda RLS. Aqui A TEM
  -- rascunho, e a resposta é a mesma de quando não tinha: not_admin.
  perform pg_temp.rpc_recusa('owner B publicando o tenant A (que agora tem rascunho)',
    'a1a00000-0000-0000-0000-00000000000a', 'not_admin');
  -- (que nada foi publicado em A por B nem pelo supervisor, a seção C prova
  --  como owner A — B não enxerga as versões de A, então contar aqui é vácuo)
  -- O próprio tenant B, sem rascunho: draft_not_found.
  perform pg_temp.rpc_recusa('owner B no tenant B, sem rascunho', 'a1b00000-0000-0000-0000-00000000000b', 'draft_not_found');
  -- E B publica o dele — a versão de B existe para os negativos de leitura não serem vácuo.
  insert into app.assistant_draft (tenant_id, content, updated_by)
  values ('a1b00000-0000-0000-0000-00000000000b', 'Vocabulário do cliente B.', auth.uid());
  select * into r from public.fn_publish_assistant_prompt('a1b00000-0000-0000-0000-00000000000b');
  perform pg_temp.assert_eq('owner B publica o tenant B (v1)', r.version_number, 1);
  perform set_config('a1.b_v1', r.version_id::text, true);
end $$;

-- --- O único write do definer sem asserção de escopo até o ciclo 2: o
-- `update` final do rascunho. Se ele perdesse o `where tenant_id`, a
-- publicação de B gravaria frozen_from_version_id/updated_by no rascunho de A.
reset role;
do $$ begin
  perform pg_temp.assert_eq('a publicação de B não tocou o rascunho de A: continua partindo da v4 de A, por owner A',
    (select count(*) from app.assistant_draft
      where tenant_id = 'a1a00000-0000-0000-0000-00000000000a'
        and frozen_from_version_id = current_setting('a1.a_last')::uuid
        and updated_by = 'a1000000-0000-0000-0000-000000000001'), 1);
  perform pg_temp.assert_eq('e o rascunho de B partiu da v1 de B, por owner B',
    (select count(*) from app.assistant_draft
      where tenant_id = 'a1b00000-0000-0000-0000-00000000000b'
        and frozen_from_version_id = current_setting('a1.b_v1')::uuid
        and updated_by = 'a1000000-0000-0000-0000-000000000004'), 1);
  perform pg_temp.assert_eq('nenhum rascunho aponta para versão de outro tenant',
    (select count(*) from app.assistant_draft d
      join app.assistant_prompt_version v on v.id = d.frozen_from_version_id
     where v.tenant_id is distinct from d.tenant_id), 0);
end $$;

\echo '    supervisor de A'
set local role authenticated;
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000002';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000002","role":"authenticated"}';
do $$ begin
  -- has_tenant sim, is_admin não. É ESTE o caso que separa `is_admin` de
  -- `has_tenant` no definer: o owner de B é recusado pelos dois helpers.
  perform pg_temp.rpc_recusa('supervisor de A publicando A', 'a1a00000-0000-0000-0000-00000000000a', 'not_admin');
end $$;

\echo '    anon'
reset role;
set local role anon;
do $$ begin
  perform pg_temp.deve_falhar('anon chamando a RPC',
    $q$select * from public.fn_publish_assistant_prompt('a1a00000-0000-0000-0000-00000000000a')$q$,
    'permission denied');
end $$;
reset role;

-- --- Sem ponteiro de plataforma: platform_layer_missing
-- Apagado como dono do banco, dentro de savepoint. O rascunho de A muda antes,
-- para que a recusa só possa ser a da camada (e não draft_unchanged).
savepoint sem_plataforma;
update app.assistant_draft set content = 'Vocabulário do cliente A, v5.'
 where tenant_id = 'a1a00000-0000-0000-0000-00000000000a';
delete from app.assistant_prompt_pointer where layer = 'platform' and tenant_id is null;
set local role authenticated;
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000001';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000001","role":"authenticated"}';
do $$ begin
  perform pg_temp.rpc_recusa('sem ponteiro de plataforma', 'a1a00000-0000-0000-0000-00000000000a', 'platform_layer_missing');
  perform pg_temp.assert_eq('e nada foi publicado',
    (select count(*) from app.assistant_prompt_version where tenant_id = 'a1a00000-0000-0000-0000-00000000000a'), 3);
end $$;
rollback to savepoint sem_plataforma;
do $$ begin
  perform pg_temp.assert_eq('o savepoint devolveu o ponteiro de plataforma',
    (select count(*) from app.assistant_prompt_pointer where layer = 'platform'), 1);
end $$;

-- ===========================================================================
\echo '--- C. A RLS como os papéis'
-- ===========================================================================
-- (o `rollback to savepoint` desfez o `set local`; a identidade entra de novo)
\echo '    supervisor de A: lê a plataforma e o tenant dele, não o outro; não abre o rascunho'
set local role authenticated;
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000002';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000002","role":"authenticated"}';
do $$
declare v_n bigint;
begin
  perform pg_temp.assert_eq('supervisor A lê a versão de plataforma',
    (select count(*) from app.assistant_prompt_version where tenant_id is null), 1);
  perform pg_temp.assert_eq('supervisor A lê as 3 versões de A (has_tenant)',
    (select count(*) from app.assistant_prompt_version where tenant_id = 'a1a00000-0000-0000-0000-00000000000a'), 3);
  perform pg_temp.assert_eq('supervisor A NÃO lê a versão de B',
    (select count(*) from app.assistant_prompt_version where tenant_id = 'a1b00000-0000-0000-0000-00000000000b'), 0);
  perform pg_temp.assert_eq('supervisor A vê os ponteiros de plataforma e de A, e só',
    (select count(*) from app.assistant_prompt_pointer), 2);
  perform pg_temp.assert_eq('supervisor A NÃO lê o rascunho de A (is_admin, não has_tenant)',
    (select count(*) from app.assistant_draft), 0);
  update app.assistant_draft set content = 'x'
   where tenant_id = 'a1a00000-0000-0000-0000-00000000000a';
  get diagnostics v_n = row_count;
  perform pg_temp.assert_eq('supervisor A não altera o rascunho de A (0 linhas alcançadas)', v_n, 0);
  perform pg_temp.deve_falhar('supervisor A não cria rascunho (with check)',
    $q$insert into app.assistant_draft (tenant_id, content)
       values ('a1a00000-0000-0000-0000-00000000000a', 'x')$q$,
    'row-level security');
  -- Escrita direta em versão e ponteiro: barrada pelo GRANT, antes da policy.
  perform pg_temp.deve_falhar('autenticado não insere versão pela tabela',
    $q$insert into app.assistant_prompt_version (tenant_id, layer, version_number, content)
       values ('a1a00000-0000-0000-0000-00000000000a', 'tenant', 99, 'x')$q$,
    'permission denied');
  perform pg_temp.deve_falhar('autenticado não altera versão pela tabela',
    $q$update app.assistant_prompt_version set content = 'x'$q$,
    'permission denied');
  perform pg_temp.deve_falhar('autenticado não move o ponteiro pela tabela',
    $q$update app.assistant_prompt_pointer set updated_at = now()$q$,
    'permission denied');
  perform pg_temp.deve_falhar('autenticado não insere ponteiro pela tabela',
    $q$insert into app.assistant_prompt_pointer (tenant_id, layer, version_id)
       select 'a1a00000-0000-0000-0000-00000000000a', 'tenant', id from app.assistant_prompt_version limit 1$q$,
    'permission denied');
  perform pg_temp.deve_falhar('autenticado não apaga rascunho (sem grant de delete)',
    $q$delete from app.assistant_draft$q$,
    'permission denied');
end $$;

\echo '    owner A: abre o rascunho de A, não o de B; lê A e a plataforma, não B'
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000001';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000001","role":"authenticated"}';
do $$
declare v_n bigint;
begin
  perform pg_temp.assert_eq('owner A lê o rascunho de A',
    (select count(*) from app.assistant_draft where tenant_id = 'a1a00000-0000-0000-0000-00000000000a'), 1);
  perform pg_temp.assert_eq('owner A NÃO lê o rascunho de B',
    (select count(*) from app.assistant_draft where tenant_id = 'a1b00000-0000-0000-0000-00000000000b'), 0);
  update app.assistant_draft set content = 'Vocabulário do cliente A, v4.'
   where tenant_id = 'a1a00000-0000-0000-0000-00000000000a';
  get diagnostics v_n = row_count;
  perform pg_temp.assert_eq('owner A altera o rascunho de A (1 linha)', v_n, 1);
  update app.assistant_draft set content = 'x'
   where tenant_id = 'a1b00000-0000-0000-0000-00000000000b';
  get diagnostics v_n = row_count;
  perform pg_temp.assert_eq('owner A não alcança o rascunho de B para alterar (0 linhas)', v_n, 0);
  perform pg_temp.assert_eq('owner A lê plataforma + 3 de A, e nenhuma de B',
    (select count(*) from app.assistant_prompt_version), 4);
  perform pg_temp.assert_eq('owner A NÃO lê a versão de B',
    (select count(*) from app.assistant_prompt_version where tenant_id = 'a1b00000-0000-0000-0000-00000000000b'), 0);

  -- D3b: o caminho que o painel alcança HOJE. O owner de A escreve o
  -- rascunho pela tabela e aponta frozen_from_version_id para a v1 de B —
  -- que ele nem enxerga (a FK ignora RLS). Quem barra é o trigger de escopo,
  -- e a mensagem diz "outro escopo", não "não encontrada" (definer).
  perform pg_temp.deve_falhar('D3b: owner A, pela tabela, não faz o rascunho de A partir da versão de B',
    format($q$update app.assistant_draft set frozen_from_version_id = %L
              where tenant_id = 'a1a00000-0000-0000-0000-00000000000a'$q$,
           current_setting('a1.b_v1')),
    'versão de outro escopo');
  -- E o legítimo passa: partir da v2 de A (não apontada, mesmo escopo).
  update app.assistant_draft
     set frozen_from_version_id = (select id from app.assistant_prompt_version
                                    where tenant_id = 'a1a00000-0000-0000-0000-00000000000a' and version_number = 2)
   where tenant_id = 'a1a00000-0000-0000-0000-00000000000a';
  get diagnostics v_n = row_count;
  perform pg_temp.assert_eq('e partir da v2 de A, pela tabela, passa (1 linha)', v_n, 1);
end $$;

\echo '    owner B: o espelho — B e a plataforma, nada de A'
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000004';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000004","role":"authenticated"}';
do $$ begin
  perform pg_temp.assert_eq('owner B lê plataforma + 1 de B',
    (select count(*) from app.assistant_prompt_version), 2);
  perform pg_temp.assert_eq('owner B NÃO lê versão de A',
    (select count(*) from app.assistant_prompt_version where tenant_id = 'a1a00000-0000-0000-0000-00000000000a'), 0);
  perform pg_temp.assert_eq('owner B lê só o rascunho de B',
    (select count(*) from app.assistant_draft), 1);
  perform pg_temp.assert_eq('owner B vê ponteiro de plataforma e de B',
    (select count(*) from app.assistant_prompt_pointer), 2);
end $$;

\echo '    a grafia JSON do PostgREST, sozinha'
reset request.jwt.claim.sub;
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000001","role":"authenticated"}';
do $$ begin
  -- O positivo é o que separa "recorte funcionando" de "auth.uid() nulo".
  perform pg_temp.assert_eq('auth.uid() responde pela grafia JSON: owner A ainda lê o rascunho de A',
    (select count(*) from app.assistant_draft), 1);
end $$;
reset request.jwt.claims;
reset role;

-- ===========================================================================
\echo '--- A2. Capacidades: o escopo do tenant e a régua única (SPEC-AGENTE §3b, §3e, §4)'
-- ===========================================================================
-- A invariante da §4.1: habilitar uma métrica NÃO concede acesso a dado; a
-- lista só estreita. Os três filtros da §4.2, nesta ordem e nunca ao
-- contrário: app.metric.active → assistant_metric_scope.enabled (ausência =
-- habilitada) → util.can_see_domain. Tudo lido pela RPC, como o papel — é a
-- régua única da §4.3, a mesma que a aba Capacidades e o runtime leem.
--
-- Quem tem o quê: owner A recebe `compensation` aqui (o cenário lá em cima
-- não semeia domain_permission); o supervisor de A não tem linha nenhuma, e
-- sem linha é negado. É esse par que separa "desabilitado" de "sem domínio".
-- Nada do que este bloco grava sai por delete como authenticated — não há
-- grant, e é o ponto: sai pelo rollback da transação.

-- --- Estrutura (como dono do banco)
reset role;
do $$
declare pols text[]; v_n bigint;
begin
  select array_agg(policyname::text order by policyname) into pols
    from pg_policies where schemaname = 'app' and tablename = 'assistant_metric_scope';
  perform pg_temp.assert_eq('A2-0a. exatamente as três policies da parada, por nome',
    case when pols = array['assistant_scope_insert', 'assistant_scope_read', 'assistant_scope_update'] then 1 else 0 end, 1);
  select count(*) into v_n from pg_policies
   where schemaname = 'app' and tablename = 'assistant_metric_scope'
     and ((policyname = 'assistant_scope_read'   and cmd = 'SELECT' and qual like '%has_tenant%' and qual not like '%is_admin%')
       or (policyname = 'assistant_scope_insert' and cmd = 'INSERT' and with_check like '%is_admin%')
       or (policyname = 'assistant_scope_update' and cmd = 'UPDATE' and qual like '%is_admin%' and with_check like '%is_admin%'));
  perform pg_temp.assert_eq('A2-0b. leitura por has_tenant (SELECT), escrita por is_admin (INSERT e UPDATE, não ALL)', v_n, 3);
  select count(*) into v_n from (values ('anon'), ('authenticated'), ('service_role')) r(papel)
   where has_table_privilege(r.papel, 'app.assistant_metric_scope', 'DELETE')
      or has_table_privilege(r.papel, 'app.assistant_metric_scope', 'TRUNCATE');
  perform pg_temp.assert_eq('A2-0c. ninguém apaga nem trunca (anon, authenticated, service_role)', v_n, 0);
  select count(*) into v_n from (values ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE')) p(priv)
   where has_table_privilege('anon', 'app.assistant_metric_scope', p.priv);
  perform pg_temp.assert_eq('A2-0d. anon não tem nada na tabela', v_n, 0);
  select count(*) into v_n from pg_constraint c
   where c.conrelid = 'app.assistant_metric_scope'::regclass and c.contype = 'f' and c.confdeltype = 'c'
     and c.confrelid in ('app.tenant'::regclass, 'app.metric'::regclass);
  perform pg_temp.assert_eq('A2-0e. as duas FKs (tenant, metric) são on delete cascade', v_n, 2);
end $$;

-- O domínio: owner A vê compensation; o supervisor de A não tem linha (= negado).
insert into app.domain_permission (tenant_id, role, domain, allowed)
values ('a1a00000-0000-0000-0000-00000000000a', 'owner', 'compensation', true);

-- --- (a) ausência de linha = habilitada; visível para quem tem o domínio
\echo '    (a) owner A, sem linha de escopo'
set local role authenticated;
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000001';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000001","role":"authenticated"}';
do $$
declare v_a uuid := 'a1a00000-0000-0000-0000-00000000000a';
begin
  perform pg_temp.assert_eq('A2-a1. o catálogo do owner A não é vácuo (toda métrica ativa aparece)',
    (select count(*) from public.fn_assistant_catalog(v_a)),
    (select count(*) from app.metric where active));
  perform pg_temp.assert_eq('A2-a2. sem linha de escopo, payroll_summary vem enabled = true',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'payroll_summary' and enabled), 1);
  perform pg_temp.assert_eq('A2-a3. e visible_to_me = true para o owner (tem compensation)',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'payroll_summary' and visible_to_me), 1);
  perform pg_temp.assert_eq('A2-a4. documents_expiring (pii) vem enabled e NÃO visível: domínio que o owner não recebeu aqui',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'documents_expiring' and enabled and not visible_to_me), 1);
end $$;

\echo '    (a) supervisor de A, sem linha de escopo'
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000002';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000002","role":"authenticated"}';
do $$
declare v_a uuid := 'a1a00000-0000-0000-0000-00000000000a';
begin
  perform pg_temp.assert_eq('A2-a5. o supervisor vê daily_trend (sem domínio): o catálogo dele não é vácuo',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'daily_trend' and visible_to_me), 1);
  perform pg_temp.assert_eq('A2-a6. payroll_summary vem enabled = true para o supervisor também (o escopo é do tenant)',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'payroll_summary' and enabled), 1);
  perform pg_temp.assert_eq('A2-a7. e visible_to_me = FALSE para o supervisor: sem compensation',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'payroll_summary' and not visible_to_me), 1);
end $$;

-- --- (b) o owner desabilita pela tabela: some para os dois
\echo '    (b) owner A desabilita payroll_summary'
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000001';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000001","role":"authenticated"}';
do $$
declare v_a uuid := 'a1a00000-0000-0000-0000-00000000000a';
begin
  -- updated_at explícito e velho: o trigger é before UPDATE, então o insert
  -- guarda o valor — e é isso que deixa medir o religar em (c).
  insert into app.assistant_metric_scope (tenant_id, metric_code, enabled, updated_by, updated_at)
  values (v_a, 'payroll_summary', false, auth.uid(), '2000-01-01');
  perform pg_temp.assert_eq('A2-b1. owner A gravou a exceção (insert pela tabela, is_admin)',
    (select count(*) from app.assistant_metric_scope where tenant_id = v_a and metric_code = 'payroll_summary' and not enabled), 1);
  perform pg_temp.assert_eq('A2-b2. payroll_summary vem enabled = false para o owner',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'payroll_summary' and not enabled), 1);
  perform pg_temp.assert_eq('A2-b3. e visible_to_me = false para o owner — mesmo tendo compensation',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'payroll_summary' and not visible_to_me), 1);
  perform pg_temp.assert_eq('A2-b4. as outras continuam no catálogo do owner (desabilitar é por métrica)',
    (select count(*) from public.fn_assistant_catalog(v_a) where code <> 'payroll_summary' and enabled),
    (select count(*) from app.metric where active) - 1);
end $$;

\echo '    (b) supervisor de A, com payroll_summary desabilitada'
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000002';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000002","role":"authenticated"}';
do $$
declare v_a uuid := 'a1a00000-0000-0000-0000-00000000000a';
begin
  perform pg_temp.assert_eq('A2-b5. enabled = false para o supervisor',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'payroll_summary' and not enabled), 1);
  perform pg_temp.assert_eq('A2-b6. e visible_to_me = false para o supervisor',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'payroll_summary' and not visible_to_me), 1);
end $$;

-- --- (c) o owner reabilita: volta para ele; o supervisor CONTINUA sem — a
--     tela só estreita, habilitar não concedeu domínio nenhum (§4.1).
\echo '    (c) owner A reabilita payroll_summary'
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000001';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000001","role":"authenticated"}';
do $$
declare v_a uuid := 'a1a00000-0000-0000-0000-00000000000a'; v_n bigint;
begin
  update app.assistant_metric_scope set enabled = true, updated_by = auth.uid()
   where tenant_id = v_a and metric_code = 'payroll_summary';
  get diagnostics v_n = row_count;
  perform pg_temp.assert_eq('A2-c1. owner A religou pela tabela (update, is_admin): 1 linha', v_n, 1);
  perform pg_temp.assert_eq('A2-c2. a linha FICA (reabilitar não é apagar): enabled = true',
    (select count(*) from app.assistant_metric_scope where tenant_id = v_a and metric_code = 'payroll_summary' and enabled), 1);
  perform pg_temp.assert_eq('A2-c3. e updated_at mexeu sem ninguém tocar nele (trg_updated_at)',
    (select count(*) from app.assistant_metric_scope where tenant_id = v_a and metric_code = 'payroll_summary' and updated_at = now()), 1);
  perform pg_temp.assert_eq('A2-c4. payroll_summary volta a enabled = true e visible_to_me = true para o owner',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'payroll_summary' and enabled and visible_to_me), 1);
end $$;

\echo '    (c) supervisor de A, com payroll_summary reabilitada'
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000002';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000002","role":"authenticated"}';
do $$
declare v_a uuid := 'a1a00000-0000-0000-0000-00000000000a';
begin
  perform pg_temp.assert_eq('A2-c5. enabled = true para o supervisor',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'payroll_summary' and enabled), 1);
  perform pg_temp.assert_eq('A2-c6. §4.1: e visible_to_me CONTINUA false — habilitar não concedeu compensation',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'payroll_summary' and not visible_to_me), 1);
end $$;

-- --- (d) o supervisor lê o escopo do próprio tenant e não escreve nele
\echo '    (d) supervisor de A escrevendo e lendo o escopo'
do $$
declare v_a uuid := 'a1a00000-0000-0000-0000-00000000000a'; v_n bigint;
begin
  perform pg_temp.assert_eq('A2-d1. supervisor A LÊ a linha de escopo de A (has_tenant: o runtime lê como ele)',
    (select count(*) from app.assistant_metric_scope where tenant_id = v_a), 1);
  perform pg_temp.deve_falhar('A2-d2. supervisor A não insere escopo (with check is_admin)',
    format($q$insert into app.assistant_metric_scope (tenant_id, metric_code, enabled) values (%L, 'daily_trend', false)$q$, v_a),
    'row-level security');
  update app.assistant_metric_scope set enabled = false where tenant_id = v_a and metric_code = 'payroll_summary';
  get diagnostics v_n = row_count;
  perform pg_temp.assert_eq('A2-d3. supervisor A não altera escopo (using is_admin: 0 linhas alcançadas)', v_n, 0);
  perform pg_temp.assert_eq('A2-d4. e payroll_summary segue habilitada (o update do supervisor não pegou)',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'payroll_summary' and enabled), 1);
end $$;

-- --- (e) quem não é membro: zero linhas na RPC, zero na tabela, insert recusado
\echo '    (e) owner B olhando para A'
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000004';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000004","role":"authenticated"}';
do $$
declare
  v_a uuid := 'a1a00000-0000-0000-0000-00000000000a';
  v_b uuid := 'a1b00000-0000-0000-0000-00000000000b';
begin
  perform pg_temp.assert_eq('A2-e1. owner B chamando fn_assistant_catalog(B) recebe o catálogo (o zero abaixo não é vácuo)',
    (select count(*) from public.fn_assistant_catalog(v_b)),
    (select count(*) from app.metric where active));
  perform pg_temp.assert_eq('A2-e2. owner B chamando fn_assistant_catalog(A) recebe ZERO linhas (has_tenant no corpo)',
    (select count(*) from public.fn_assistant_catalog(v_a)), 0);
  perform pg_temp.assert_eq('A2-e3. owner B não lê o escopo de A pela tabela',
    (select count(*) from app.assistant_metric_scope where tenant_id = v_a), 0);
  perform pg_temp.deve_falhar('A2-e4. owner B não insere escopo em A (is_admin de A, não de B)',
    format($q$insert into app.assistant_metric_scope (tenant_id, metric_code, enabled) values (%L, 'daily_trend', false)$q$, v_a),
    'row-level security');
end $$;

-- --- (f) delete: recusado por GRANT, para o owner e para o backend
\echo '    (f) delete como owner A e como service_role'
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000001';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000001","role":"authenticated"}';
do $$ begin
  perform pg_temp.deve_falhar('A2-f1. owner A não apaga escopo (sem grant de delete: reabilitar é enabled = true)',
    $q$delete from app.assistant_metric_scope where tenant_id = 'a1a00000-0000-0000-0000-00000000000a'$q$,
    'permission denied');
end $$;
reset role;
set local role service_role;
do $$ begin
  perform pg_temp.deve_falhar('A2-f2. service_role também não apaga escopo',
    $q$delete from app.assistant_metric_scope$q$,
    'permission denied');
end $$;
reset role;

-- --- (g) as nove colunas, e as três do runtime batendo com app.metric
\echo '    (g) o contrato da RPC, como owner A'
set local role authenticated;
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000001';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000001","role":"authenticated"}';
do $$
declare v_a uuid := 'a1a00000-0000-0000-0000-00000000000a'; v_result text;
begin
  select regexp_replace(pg_get_function_result('public.fn_assistant_catalog(uuid)'::regprocedure), '\s+', ' ', 'g') into v_result;
  perform pg_temp.assert_eq('A2-g1. as nove colunas, nesta ordem: as seis da SPEC §3e + target_view, dimensions, filters',
    case when v_result = 'TABLE(code text, title text, description text, domain app.sensitive_domain, enabled boolean, visible_to_me boolean, target_view text, dimensions text[], filters text[])' then 1 else 0 end, 1);
  perform pg_temp.assert_eq('A2-g2. target_view, dimensions e filters de payroll_summary são os de app.metric',
    (select count(*) from public.fn_assistant_catalog(v_a) c
       join app.metric m on m.code = c.code
      where c.code = 'payroll_summary'
        and c.target_view = m.target_view and c.dimensions = m.dimensions and c.filters = m.filters
        and c.domain = m.domain and c.title = m.title and c.description = m.description), 1);
end $$;

-- --- (h) anon
\echo '    (h) anon'
reset role;
set local role anon;
do $$ begin
  -- 'for function', não só 'permission denied': com o grant a anon, ela
  -- executaria e cairia em app.metric — recusa certa pelo guarda errado.
  perform pg_temp.deve_falhar('A2-h1. anon não executa fn_assistant_catalog (recusa da própria função)',
    $q$select * from public.fn_assistant_catalog('a1a00000-0000-0000-0000-00000000000a')$q$,
    'permission denied for function');
end $$;
reset role;

-- --- (i) a EURECA manda primeiro: métrica inativa não aparece, nem com
--     escopo enabled = true. Como dono do banco, dentro de savepoint.
\echo '    (i) métrica inativa em app.metric, com escopo enabled = true'
savepoint metrica_inativa;
update app.metric set active = false where code = 'daily_trend';
insert into app.assistant_metric_scope (tenant_id, metric_code, enabled)
values ('a1a00000-0000-0000-0000-00000000000a', 'daily_trend', true);
set local role authenticated;
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000001';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000001","role":"authenticated"}';
do $$
declare v_a uuid := 'a1a00000-0000-0000-0000-00000000000a';
begin
  perform pg_temp.assert_eq('A2-i1. daily_trend inativa não aparece no catálogo do owner, mesmo com escopo enabled = true',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'daily_trend'), 0);
  perform pg_temp.assert_eq('A2-i2. e o resto do catálogo continua (uma a menos)',
    (select count(*) from public.fn_assistant_catalog(v_a)),
    (select count(*) from app.metric where active));
end $$;
rollback to savepoint metrica_inativa;
-- (o rollback to savepoint desfez o set local; a identidade entra de novo)
set local role authenticated;
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000001';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000001","role":"authenticated"}';
do $$
declare v_a uuid := 'a1a00000-0000-0000-0000-00000000000a';
begin
  perform pg_temp.assert_eq('A2-i3. o savepoint religou daily_trend: volta ao catálogo do owner',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'daily_trend' and enabled and visible_to_me), 1);
  perform pg_temp.assert_eq('A2-i4. e a linha de escopo de daily_trend foi embora com ele (só a de payroll_summary fica)',
    (select count(*) from app.assistant_metric_scope where tenant_id = v_a), 1);
end $$;
reset role;

-- --- (j) quem é membro de A E de B: o escopo de B não narra A. O join do
--     escopo é por (tenant_id = p_tenant_id, metric_code); sem o tenant, a
--     linha de B contaria para A — a métrica que A não desligou apareceria
--     desligada, e a que os dois desligaram apareceria duas vezes, uma delas
--     habilitada. Medido pelo revisor em 17/09/2026: 12 linhas em vez de 11.
\echo '    (j) membro de A e de B: o escopo de B não narra A'
insert into auth.users (id, email) values
  ('a1000000-0000-0000-0000-000000000005', 'dois.tenants@assistente');
insert into app.tenant_member (tenant_id, user_id, role) values
  ('a1a00000-0000-0000-0000-00000000000a', 'a1000000-0000-0000-0000-000000000005', 'unit_supervisor'),
  ('a1b00000-0000-0000-0000-00000000000b', 'a1000000-0000-0000-0000-000000000005', 'owner');
set local role authenticated;
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000005';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000005","role":"authenticated"}';
-- Como owner de B: B desliga daily_trend (A não desligou) e grava a sua
-- própria linha de payroll_summary (A já tem uma, religada em (c)).
insert into app.assistant_metric_scope (tenant_id, metric_code, enabled) values
  ('a1b00000-0000-0000-0000-00000000000b', 'daily_trend', false),
  ('a1b00000-0000-0000-0000-00000000000b', 'payroll_summary', false);
do $$
declare
  v_a uuid := 'a1a00000-0000-0000-0000-00000000000a';
  v_b uuid := 'a1b00000-0000-0000-0000-00000000000b';
begin
  perform pg_temp.assert_eq('A2-j1. em B, daily_trend vem desligada (a linha de B conta em B — o zero abaixo não é vácuo)',
    (select count(*) from public.fn_assistant_catalog(v_b) where code = 'daily_trend' and not enabled), 1);
  perform pg_temp.assert_eq('A2-j2. em A, daily_trend continua enabled = true: o escopo de B não narra A',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'daily_trend' and enabled), 1);
  perform pg_temp.assert_eq('A2-j3. em A, payroll_summary aparece UMA vez, com o valor de A (enabled = true)',
    (select count(*) from public.fn_assistant_catalog(v_a) where code = 'payroll_summary' and enabled), 1);
  perform pg_temp.assert_eq('A2-j4. e o catálogo de A tem exatamente uma linha por métrica ativa (sem duplicata)',
    (select count(*) from public.fn_assistant_catalog(v_a)),
    (select count(*) from app.metric where active));
  perform pg_temp.assert_eq('A2-j5. e cada código aparece uma vez só',
    (select count(distinct code) from public.fn_assistant_catalog(v_a)),
    (select count(*) from public.fn_assistant_catalog(v_a)));
end $$;
reset role;

-- ===========================================================================
\echo '--- A3. O turno diz qual versão o produziu (SPEC-AGENTE §3c, §5, §7.1 decidida)'
-- ===========================================================================
-- Migration `assistant_run_link`: três colunas em app.ai_query, sem policy,
-- grant ou view nova. Aqui: as colunas e as duas checks; a FK sem cascade
-- (apagar versão apontada por um turno é recusado como dono do banco); o
-- índice parcial; `ai_query_read` funcionalmente inalterada (o `98` não
-- cobre ai_query — as três leituras são daqui); e a MEDIÇÃO, não asserção,
-- de que a FK aceita versão de outro tenant — é log, e não há trigger de
-- escopo nele de propósito.
\echo '    (a) as três colunas, as duas checks e o índice, como dono do banco'
do $$
declare
  v_unpointed uuid;
  v_id        uuid;
  v_n         bigint;
begin
  perform pg_temp.assert_eq('A3-a1. prompt_version_id é uuid nullable',
    (select count(*) from information_schema.columns
      where table_schema = 'app' and table_name = 'ai_query'
        and column_name = 'prompt_version_id' and data_type = 'uuid' and is_nullable = 'YES'), 1);
  perform pg_temp.assert_eq('A3-a2. is_dry_run é boolean not null default false',
    (select count(*) from information_schema.columns
      where table_schema = 'app' and table_name = 'ai_query'
        and column_name = 'is_dry_run' and data_type = 'boolean'
        and is_nullable = 'NO' and column_default = 'false'), 1);
  perform pg_temp.assert_eq('A3-a3. draft_content_hash é text nullable',
    (select count(*) from information_schema.columns
      where table_schema = 'app' and table_name = 'ai_query'
        and column_name = 'draft_content_hash' and data_type = 'text' and is_nullable = 'YES'), 1);

  -- Uma versão de A que nem ponteiro nem rascunho referenciam: só a FK do
  -- turno a segura. Criada aqui, como dono do banco, para ser determinística.
  insert into app.assistant_prompt_version (tenant_id, layer, version_number, content)
  values ('a1a00000-0000-0000-0000-00000000000a', 'tenant', 90, 'versão só referenciada por um turno')
  returning id into v_unpointed;

  -- Turno real, sem dry run: is_dry_run assume o default.
  insert into app.ai_query (tenant_id, user_id, question, model, prompt_version_id)
  values ('a1a00000-0000-0000-0000-00000000000a', 'a1000000-0000-0000-0000-000000000001',
          'turno real do owner A', 'fake-1', v_unpointed)
  returning id into v_id;
  perform pg_temp.assert_eq('A3-a4. turno gravado sem is_dry_run fica false (default)',
    (select count(*) from app.ai_query where id = v_id and not is_dry_run and draft_content_hash is null), 1);

  -- Dry run com hash válido: aceito.
  insert into app.ai_query (tenant_id, user_id, question, model, prompt_version_id, is_dry_run, draft_content_hash)
  values ('a1a00000-0000-0000-0000-00000000000a', 'a1000000-0000-0000-0000-000000000001',
          'teste do rascunho', 'fake-1',
          (select version_id from app.assistant_prompt_pointer where layer = 'platform'),
          true, encode(sha256('Rascunho testado.'::bytea), 'hex'));
  perform pg_temp.assert_eq('A3-a5. dry run com sha256 hex minúsculo é aceito',
    (select count(*) from app.ai_query where question = 'teste do rascunho' and is_dry_run
        and draft_content_hash ~ '^[0-9a-f]{64}$'), 1);

  -- As duas checks, cada uma pelo nome.
  perform pg_temp.deve_falhar('A3-a6. hash fora de dry run é recusado',
    format($q$insert into app.ai_query (tenant_id, question, is_dry_run, draft_content_hash)
              values ('a1a00000-0000-0000-0000-00000000000a', 'x', false, %L)$q$,
           encode(sha256('x'::bytea), 'hex')),
    'ai_query_draft_hash_only_in_dry_run');
  perform pg_temp.deve_falhar('A3-a7. hash com 63 caracteres é recusado',
    format($q$insert into app.ai_query (tenant_id, question, is_dry_run, draft_content_hash)
              values ('a1a00000-0000-0000-0000-00000000000a', 'x', true, %L)$q$,
           left(encode(sha256('x'::bytea), 'hex'), 63)),
    'ai_query_draft_hash_format');
  perform pg_temp.deve_falhar('A3-a8. hash em maiúsculas é recusado',
    format($q$insert into app.ai_query (tenant_id, question, is_dry_run, draft_content_hash)
              values ('a1a00000-0000-0000-0000-00000000000a', 'x', true, %L)$q$,
           upper(encode(sha256('x'::bytea), 'hex'))),
    'ai_query_draft_hash_format');

  -- A FK sem cascade: a versão apontada por um turno não some, nem como dono.
  perform pg_temp.deve_falhar('A3-a9. apagar a versão apontada por um turno é recusado (FK de ai_query, sem cascade)',
    format($q$delete from app.assistant_prompt_version where id = %L$q$, v_unpointed),
    'ai_query');
  perform pg_temp.assert_eq('A3-a10. e a FK não é cascade nem set null (confdeltype = a)',
    (select count(*) from pg_constraint
      where conrelid = 'app.ai_query'::regclass and contype = 'f'
        and confrelid = 'app.assistant_prompt_version'::regclass and confdeltype = 'a'), 1);
  perform pg_temp.deve_falhar('A3-a11. prompt_version_id que não é versão é recusado',
    $q$insert into app.ai_query (tenant_id, question, prompt_version_id)
       values ('a1a00000-0000-0000-0000-00000000000a', 'x', 'a1f00000-0000-0000-0000-0000000000ff')$q$,
    'ai_query_prompt_version_id_fkey');

  -- O índice parcial: só o tráfego real.
  perform pg_temp.assert_eq('A3-a12. ai_query_dry_run_idx é parcial em NOT is_dry_run',
    (select count(*) from pg_indexes
      where schemaname = 'app' and tablename = 'ai_query' and indexname = 'ai_query_dry_run_idx'
        and indexdef like '%WHERE (NOT is_dry_run)%'), 1);

  -- Nenhuma policy, grant ou view nova.
  perform pg_temp.assert_eq('A3-a13. app.ai_query continua com exatamente a policy ai_query_read',
    (select count(*) from pg_policies where schemaname = 'app' and tablename = 'ai_query'
        and policyname = 'ai_query_read'),
    (select count(*) from pg_policies where schemaname = 'app' and tablename = 'ai_query'));
  perform pg_temp.assert_eq('A3-a14. authenticated continua sem insert/update/delete em ai_query',
    (select count(*) from (values ('INSERT'), ('UPDATE'), ('DELETE')) as p(priv)
      where has_table_privilege('authenticated', 'app.ai_query', p.priv)), 0);
  perform pg_temp.assert_eq('A3-a15. anon continua sem select em ai_query',
    case when has_table_privilege('anon', 'app.ai_query', 'SELECT') then 1 else 0 end, 0);

  -- Um turno do supervisor de A, para as leituras abaixo não serem vácuo.
  insert into app.ai_query (tenant_id, user_id, question, model, prompt_version_id)
  values ('a1a00000-0000-0000-0000-00000000000a', 'a1000000-0000-0000-0000-000000000002',
          'turno do supervisor A', 'fake-1', v_unpointed);
  select count(*) into v_n from app.ai_query where tenant_id = 'a1a00000-0000-0000-0000-00000000000a';
  perform pg_temp.assert_eq('A3-a16. o cenário tem 3 turnos de A (2 do owner, 1 do supervisor)', v_n, 3);
end $$;

-- ---------------------------------------------------------------------------
-- (b) MEDIÇÃO, não asserção: a FK aceita versão de OUTRO tenant. É log — o
-- backend grava o id que acabou de ler pelo ponteiro como o usuário — e não
-- há trigger de escopo em ai_query de propósito. Registrado para que ninguém
-- leia a FK como isolamento. Como dono do banco (o papel de DATABASE_URL);
-- o grant de service_role em ai_query é medido ao lado.
-- ---------------------------------------------------------------------------
\echo '    (b) medição: a FK de prompt_version_id não confere o tenant'
do $$
declare
  v_b_version uuid;
  v_id        uuid;
begin
  select version_id into v_b_version from app.assistant_prompt_pointer
   where tenant_id = 'a1b00000-0000-0000-0000-00000000000b' and layer = 'tenant';
  begin
    insert into app.ai_query (tenant_id, user_id, question, prompt_version_id)
    values ('a1a00000-0000-0000-0000-00000000000a', 'a1000000-0000-0000-0000-000000000001',
            'medição: versão de B num turno de A', v_b_version)
    returning id into v_id;
    raise notice '  medido  A3-b1. um turno de A com prompt_version_id da versão de B é ACEITO pela FK (é log; não há trigger de escopo em ai_query, e não é para ter)';
    delete from app.ai_query where id = v_id;
  exception when others then
    raise notice '  medido  A3-b1. um turno de A com prompt_version_id da versão de B foi RECUSADO: % — isso é mudança de desenho, não o esperado', sqlerrm;
  end;
  raise notice '  medido  A3-b2. service_role tem INSERT em app.ai_query neste ensaio: % (o backend conecta como o dono de DATABASE_URL)',
    has_table_privilege('service_role', 'app.ai_query', 'INSERT');
end $$;

-- ---------------------------------------------------------------------------
-- (c) ai_query_read como os papéis: owner A lê as de A, supervisor A só as
-- próprias, owner B nenhuma de A. O `98` não cobre ai_query; é aqui.
-- ---------------------------------------------------------------------------
\echo '    (c) ai_query_read inalterada, como os papéis'
set local role authenticated;
set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000001';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000001","role":"authenticated"}';
do $$ begin
  perform pg_temp.assert_eq('A3-c1. owner A lê os 3 turnos de A (os dele e o do supervisor)',
    (select count(*) from app.ai_query where tenant_id = 'a1a00000-0000-0000-0000-00000000000a'), 3);
  perform pg_temp.assert_eq('A3-c2. e vê as três colunas novas (prompt_version_id preenchido nos 3)',
    (select count(*) from app.ai_query
      where tenant_id = 'a1a00000-0000-0000-0000-00000000000a' and prompt_version_id is not null), 3);
  perform pg_temp.assert_eq('A3-c3. o dry run é distinguível pela coluna, não pela pergunta',
    (select count(*) from app.ai_query
      where tenant_id = 'a1a00000-0000-0000-0000-00000000000a' and is_dry_run), 1);
end $$;

set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000002';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000002","role":"authenticated"}';
do $$ begin
  perform pg_temp.assert_eq('A3-c4. supervisor A lê só o próprio turno',
    (select count(*) from app.ai_query where tenant_id = 'a1a00000-0000-0000-0000-00000000000a'), 1);
  perform pg_temp.assert_eq('A3-c5. e é o dele',
    (select count(*) from app.ai_query where user_id = auth.uid()), 1);
end $$;

set local request.jwt.claim.sub = 'a1000000-0000-0000-0000-000000000004';
set local request.jwt.claims = '{"sub":"a1000000-0000-0000-0000-000000000004","role":"authenticated"}';
do $$ begin
  perform pg_temp.assert_eq('A3-c6. owner B não lê turno nenhum de A',
    (select count(*) from app.ai_query where tenant_id = 'a1a00000-0000-0000-0000-00000000000a'), 0);
  perform pg_temp.deve_falhar('A3-c7. e autenticado não grava turno pela tabela (grant, antes de policy)',
    $q$insert into app.ai_query (tenant_id, question) values ('a1b00000-0000-0000-0000-00000000000b', 'x')$q$,
    'permission denied');
end $$;
reset role;

\echo ''
\echo '================================================'
\echo ' CAMADAS DO ASSISTENTE: TODOS OS TESTES OK'
\echo '================================================'

rollback;
