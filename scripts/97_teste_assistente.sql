-- ============================================================================
-- OperaX — TESTE DAS CAMADAS DO ASSISTENTE (SPEC-AGENTE §2, §3a, §3d)
-- ----------------------------------------------------------------------------
-- Quatro garantias que só valem se o banco as sustentar:
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
--
-- A fidelidade da transcrição da v1 (o texto da migration == agente._prompt)
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

\echo ''
\echo '================================================'
\echo ' CAMADAS DO ASSISTENTE: TODOS OS TESTES OK'
\echo '================================================'

rollback;
