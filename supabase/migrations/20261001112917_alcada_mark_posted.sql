-- ============================================================================
-- OperaX — alcada_mark_posted. "APROVADO" E "APROVADO E LANÇADO" PASSAM A SER
-- DUAS COISAS DIFERENTES
-- ----------------------------------------------------------------------------
-- Desenho: `docs/DECISAO-ALCADA-APROVACAO.md` §4.2 (`posted_to_source_at` e
-- `posted_by`) e §6 (o risco de adoção); sprint P1.4 de `docs/SPRINTS-ALCADA.md`.
-- RPC nova em `public` aprovada pelo dono em 01/10/2026 (parada cumprida).
--
-- POR QUÊ. A decisão 5 diz que o RH digita a decisão no Secullum — o OperaX
-- não escreve na origem. Sem marcar o lançamento, "o que já foi digitado e o
-- que não foi" não tem resposta, e o esquecimento é silencioso. As duas colunas
-- já existem desde a P1.2 (`alcada_justification_review`) e nada as escrevia.
--
-- `public.fn_marcar_lancado(p_review_id uuid) returns timestamptz`.
-- QUATRO RECUSAS, NESTA ORDEM, CADA UMA `P0001` COM O CÓDIGO COMO MENSAGEM:
--   1. not_hr           — o chamador não tem `hr` nem `owner` em tenant
--                         NENHUM. Supervisor, DP e contabilidade param aqui.
--   2. review_not_found — inexistente, OU de tenant em que o chamador não é
--                         `hr`/`owner`. A mesma resposta de propósito: o RH do
--                         cliente A não aprende que um id do cliente B existe,
--                         nem se ele já foi lançado.
--   3. not_approved     — a revisão é `rejected`: reprovação não se digita
--                         como abono no Secullum.
--   4. already_posted   — já tem marca. É definitivo (decisão do dono,
--                         01/10/2026): não existe desfazer, e engano vira
--                         correção por SQL de operador.
-- Tudo depois do 2 só é respondido a quem é `hr`/`owner` do tenant da revisão.
-- O 3 vem antes do 4 sem que a ordem seja observável: uma reprovada nunca
-- recebe marca (o 3 a barra), então nenhuma linha satisfaz os dois.
--
-- GRAVA `posted_to_source_at = now()` e `posted_by = auth.uid()`, UMA VEZ SÓ, e
-- devolve a marca. `now()` é o início da transação do chamador — numa chamada
-- da API, a requisição.
--
-- O LOCK: a linha da revisão é travada (`for update`) só depois do 2, como na
-- `fn_revisar_justificativa` — quem não é `hr`/`owner` do tenant dela nunca
-- espera por ela, então o tempo de resposta não diz se o id existe. Duas
-- marcações concorrentes da mesma se serializam no lock, e a segunda recebe
-- `already_posted` em vez de sobrescrever quem lançou (provado em
-- `scripts/78_teste_lancamento_concorrente.py`).
--
-- O QUE NÃO ENTRA, DE PROPÓSITO: as recusas `own_justification` e `owner_only`
-- da revisão. Elas existem porque quem explica não DECIDE (decisão do dono,
-- 29/09); lançar não decide nada — a decisão já foi tomada, por outra pessoa,
-- e está gravada em `reviewed_by`. CONFIRMADO PELO DONO EM 04/10/2026: o autor
-- PODE marcar como lançada a própria justificativa aprovada por outro.
--
-- A LISTA do que falta lançar NÃO é objeto deste banco: é consulta do backend
-- (`server/routers/alcada.py`, `POSTING_LIST_SQL`) sob `user_scope`, provada em
-- `scripts/77_teste_lista_lancamento.py`. A competência dela é a do FATO (janela
-- 21→20 de `reference_date`, a da fila) — decisão do dono de 04/10/2026, que
-- supera o §4.2 nesse ponto: `payroll_period_id` continua sendo a competência em
-- que a revisão foi feita, mas não é por ela que a lista recorta (e o `hr` nem
-- lê `app.payroll_period`, que é domínio `compensation`).
--
-- NADA MAIS MUDA: nenhuma policy nova, nenhum grant de tabela. `authenticated`
-- continua só LENDO `app.justification_review` (`review_read`), e a marca entra
-- só por esta RPC, que é definer (dono `postgres`) e checa o papel ela mesma.
--
-- ⚠️ `trg_lock_down_new_function` NÃO cobre `public`: o revoke e o
--    `grant execute … to authenticated` estão escritos aqui.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

create or replace function public.fn_marcar_lancado(p_review_id uuid)
returns timestamptz
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_tenant   uuid;
  v_roles    app.user_role[];
  v_decision text;
  v_posted   timestamptz;
begin
  -- 1. Definer não herda RLS: o papel é checado aqui — antes de ler a linha.
  if not exists (
    select 1 from app.tenant_member tm
     where tm.user_id = (select auth.uid())
       and tm.active
       and tm.role in ('hr','owner')
  ) then
    raise exception 'not_hr' using errcode = 'P0001';
  end if;

  -- 2. Inexistente e alheia respondem igual. Sem lock: quem não é do tenant
  -- dela não espera por ela (ver o cabeçalho).
  select r.tenant_id into v_tenant
    from app.justification_review r
   where r.id = p_review_id;
  if found then
    v_roles := util.roles_in_tenant(v_tenant);
  end if;
  if v_tenant is null or not (v_roles && array['hr','owner']::app.user_role[]) then
    raise exception 'review_not_found' using errcode = 'P0001';
  end if;

  -- Trava a revisão: duas marcações concorrentes se serializam aqui, e a
  -- segunda vê a primeira (already_posted).
  select r.decision, r.posted_to_source_at
    into v_decision, v_posted
    from app.justification_review r
   where r.id = p_review_id
     for update;

  -- 3.
  if v_decision <> 'approved' then
    raise exception 'not_approved' using errcode = 'P0001';
  end if;

  -- 4.
  if v_posted is not null then
    raise exception 'already_posted' using errcode = 'P0001';
  end if;

  update app.justification_review
     set posted_to_source_at = now(),
         posted_by           = (select auth.uid())
   where id = p_review_id
  returning posted_to_source_at into v_posted;

  return v_posted;
end $$;

comment on function public.fn_marcar_lancado(uuid) is
  'O RH (ou o owner) declara que digitou no Secullum a decisão de uma revisão aprovada. '
  'Recusas P0001, nesta ordem: not_hr, review_not_found (inexistente ou de outro tenant), '
  'not_approved (revisão rejected), already_posted. Grava posted_to_source_at e posted_by '
  'uma vez só; não existe desfazer. Definer: checa o papel ela mesma. Devolve a marca.';

revoke execute on function public.fn_marcar_lancado(uuid) from public, anon;
grant  execute on function public.fn_marcar_lancado(uuid) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_fn  regprocedure := 'public.fn_marcar_lancado(uuid)'::regprocedure;
  v_def text;
  v_err text;
begin
  -- 1. Definer, com search_path travado.
  if not (select p.prosecdef and coalesce('search_path=""' = any(p.proconfig), false)
            from pg_proc p where p.oid = v_fn) then
    raise exception 'fn_marcar_lancado não é definer com search_path = ''''';
  end if;

  -- 2. Grants: authenticated executa; anon e PUBLIC não.
  if not has_function_privilege('authenticated', v_fn, 'execute') then
    raise exception 'authenticated não executa fn_marcar_lancado: o RH não marca nada';
  end if;
  if has_function_privilege('anon', v_fn, 'execute') then
    raise exception 'anon executa fn_marcar_lancado';
  end if;
  if exists (select 1 from pg_proc p, aclexplode(p.proacl) a
              where p.oid = v_fn and a.grantee = 0 and a.privilege_type = 'EXECUTE') then
    raise exception 'PUBLIC executa fn_marcar_lancado';
  end if;

  -- 3. A escrita entra só pela RPC: nenhuma policy nova, nenhuma escrita de
  -- authenticated, nem de tabela nem de coluna.
  if (select array_agg(policyname::text) from pg_policies
       where schemaname = 'app' and tablename = 'justification_review')
     is distinct from array['review_read'] then
    raise exception 'app.justification_review deve ter só review_read: a marca entra pela RPC';
  end if;
  if has_table_privilege('authenticated', 'app.justification_review', 'UPDATE')
     or has_any_column_privilege('authenticated', 'app.justification_review', 'UPDATE')
     or has_table_privilege('authenticated', 'app.justification_review', 'INSERT')
     or has_table_privilege('authenticated', 'app.justification_review', 'DELETE') then
    raise exception 'authenticated escreve app.justification_review: a marca teria um atalho';
  end if;

  -- 4. A ordem das recusas é a do cabeçalho, e o lock vem depois do papel e do
  -- tenant.
  v_def := pg_get_functiondef(v_fn);
  if not (position('''not_hr''' in v_def) < position('''review_not_found''' in v_def)
          and position('''review_not_found''' in v_def) < position('for update' in v_def)
          and position('for update' in v_def) < position('''not_approved''' in v_def)
          and position('''not_approved''' in v_def) < position('''already_posted''' in v_def)) then
    raise exception 'fn_marcar_lancado fora da ordem: not_hr, review_not_found, lock, not_approved, already_posted';
  end if;

  -- 5. Sem sessão não há papel: a primeira recusa é a primeira.
  begin
    perform public.fn_marcar_lancado(gen_random_uuid());
    v_err := null;
  exception when sqlstate 'P0001' then v_err := sqlerrm;
  end;
  if v_err is distinct from 'not_hr' then
    raise exception 'chamada sem papel recebeu %, não not_hr', coalesce(v_err, 'sucesso');
  end if;

  raise notice 'OK: a marca de lançamento entra só pela RPC, uma vez, e só pelo RH ou owner.';
end $$;
