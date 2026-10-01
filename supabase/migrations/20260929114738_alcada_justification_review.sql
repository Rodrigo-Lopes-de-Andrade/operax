-- ============================================================================
-- OperaX — alcada_justification_review. A APROVAÇÃO COMO FATO NOVO, E A PORTA
-- ÚNICA QUE A ESCREVE
-- ----------------------------------------------------------------------------
-- Desenho: `docs/DECISAO-ALCADA-APROVACAO.md` §4.2 e §4.3; sprint P1.2 de
-- `docs/SPRINTS-ALCADA.md`. Policy, RPC e a retirada do grant de
-- `app.revoke_deviation` aprovadas pelo dono em 29/09/2026 (paradas cumpridas).
--
-- 1. `app.justification_review` — uma revisão por justificativa
--    (`justification_review_uk`). A justificativa é imutável (não há policy de
--    UPDATE, e é acerto): aprovar não edita a linha do supervisor, escreve
--    outra. Reprovada, o supervisor escreve justificativa NOVA, que ganha a
--    própria revisão. `payroll_period_id` é a competência em que o RH
--    PROCESSOU, não a do fato — a do fato é derivada de `reference_date`.
--
-- 2. LEITURA: `review_read`, quem enxerga o colaborador. ESCRITA: NENHUMA
--    policy, e nenhum grant de escrita a `authenticated`. A revisão entra só
--    por `public.fn_revisar_justificativa`, que checa o papel ela mesma.
--
-- 3. `public.fn_revisar_justificativa(id, decisão, motivo) returns uuid`.
--    NOVE RECUSAS, NESTA ORDEM, CADA UMA `P0001` COM O CÓDIGO COMO MENSAGEM:
--      1. not_hr                  — o chamador não tem `hr` nem `owner` em
--                                   tenant NENHUM. Supervisor para aqui.
--      2. justification_not_found — inexistente, OU de tenant em que o chamador
--                                   não é `hr`/`owner`. As duas respostas são a
--                                   mesma de propósito: o RH do cliente A não
--                                   aprende que um id do cliente B existe.
--      3. own_justification       — o chamador é o autor (`author_user_id`).
--                                   Decisão do dono (29/09): quem explica não
--                                   decide, nem o owner. Autor nulo não bloqueia.
--      4. owner_only              — o colaborador tem `approval_owner_only` e o
--                                   chamador não é `owner` no tenant. Decisão
--                                   do dono (29/09): o desvio de quem é do RH é
--                                   aprovado pelo owner.
--      5. already_reviewed        — já tem revisão.
--      6. source_is_mirror        — `source = 'secullum'`: a origem já decidiu.
--      7. not_pending             — `status` não é `pending`: a `accepted` e a
--                                   `rejected` legadas já foram decididas, e
--                                   revisá-las gravaria uma decisão sem efeito
--                                   (ou contrária à que vale). Decisão do dono
--                                   (29/09).
--      8. no_open_period          — nenhuma competência NÃO FECHADA (meses
--                                   1–12) no tenant.
--      9. rejection_needs_reason  — reprovar sem motivo.
--    Tudo depois do 2 só é respondido a quem é `hr`/`owner` do tenant da
--    justificativa: nenhuma recusa posterior vaza autoria, status ou origem de
--    justificativa alheia. `not_pending` vem DEPOIS de `source_is_mirror`
--    porque espelho nunca é pendente (`justification_espelho_nao_pende`, P1.1):
--    antes, ele tornaria `source_is_mirror` inalcançável.
--    Aprovada: grava a revisão E move o desvio para `justified` por
--    `app.revoke_deviation`, na MESMA transação (é uma chamada só). Reprovada:
--    grava a revisão, e o desvio continua `active`.
--
--    `owner_only` e não `not_hr`: o RH que recebe esta recusa É do RH, e a
--    tela precisa dizer "esta é do owner", não "você não é do RH".
--
--    O LOCK: a linha da justificativa é travada (`for update`) só depois do
--    2 — quem não é `hr`/`owner` do tenant dela nunca espera por ela, então o
--    tempo de resposta não diz se o id existe. Duas revisões concorrentes da
--    mesma se serializam no lock, e a segunda recebe `already_reviewed` em vez
--    de estourar no `justification_review_uk` (provado em
--    `scripts/81_teste_revisao_concorrente.py`).
--
--    A COMPETÊNCIA DE DESTINO é a NÃO FECHADA mais antiga (`status <>
--    'fechada'`), entre os meses 1–12. Decisão do dono (29/09): nada no
--    repositório grava `aberta` — o import de folha
--    (`backend/operax/imports/repository.py`) cria a competência já como
--    `importada` —, e exigir `aberta` recusaria toda aprovação com dado real.
--    `aberta`, `importada` e `conferida` recebem revisão; `fechada` não.
--    Mais de uma não fechada: a migration 07 NÃO impede — o único `unique` é
--    `(tenant_id, year, month)`. A mais antiga é a que ainda está em
--    processamento (uma competência futura criada antes da hora não recebe
--    revisão enquanto a anterior não fechou), e o mês 13 é o décimo terceiro,
--    que não é janela 21→20 de ponto nenhum.
--
-- 4. `app.employee.approval_owner_only` — a marca, no padrão de
--    `exception_tracking` (migration 26): na pessoa, `not null default false`.
--    Nasce false para todo mundo: ninguém sai da alçada do RH sem alguém ter
--    tirado. ⚠️ Não há rota nem tela que a escreva ainda (fora da P1.2); a
--    promoção do espelho lista as colunas uma a uma e não a apaga —
--    `scripts/92_teste_cadastro.py` afirma isso. Não entra em view de `public`.
--
-- 5. `revoke execute on app.revoke_deviation from authenticated`. Era a porta
--    sem papel: qualquer usuário que enxergasse o desvio o justificava. O
--    motor conecta como `postgres` (dono da função) e continua podendo; a RPC
--    acima é definer (dono `postgres`) e também.
--
-- 6. `public.fn_pending_justification` (migration 23) — mesma assinatura, mesmo
--    `security invoker`, mesmos grants, nenhuma coluna nova. Muda só o que
--    tira o desvio da lista: justificativa `accepted` (legada), ou `pending`
--    sem revisão REPROVADA (esperando o RH, ou aprovada). Revisão reprovada
--    devolve o desvio à fila do supervisor.
--
-- ⚠️ `trg_lock_down_new_function` NÃO cobre `public`: o revoke e o
--    `grant execute … to authenticated` estão escritos aqui.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 4. A marca na pessoa
-- ---------------------------------------------------------------------------
alter table app.employee
  add column if not exists approval_owner_only boolean not null default false;

comment on column app.employee.approval_owner_only is
  'Justificativa desta pessoa só é revisada pelo owner — decisão do dono (29/09/2026) para '
  'quem é do RH: ninguém aprova o próprio desvio. Nasce false: ninguém sai da alçada do RH '
  'sem alguém ter tirado. Lida por public.fn_revisar_justificativa.';

-- ---------------------------------------------------------------------------
-- 1. A revisão
-- ---------------------------------------------------------------------------
create table if not exists app.justification_review (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid not null references app.tenant(id) on delete cascade,
  justification_id    uuid not null references app.justification(id) on delete cascade,
  payroll_period_id   uuid not null references app.payroll_period(id),
  decision            text not null check (decision in ('approved','rejected')),
  reason              text,
  reviewed_by         uuid not null references auth.users(id),
  reviewed_at         timestamptz not null default now(),
  posted_to_source_at timestamptz,
  posted_by           uuid references auth.users(id)
);

create unique index if not exists justification_review_uk
  on app.justification_review (justification_id);

comment on table app.justification_review is
  'A decisão da alçada sobre uma justificativa — fato novo, nunca edição da justificativa. '
  'Uma por justificativa (justification_review_uk). Entra só por '
  'public.fn_revisar_justificativa; nenhuma policy de escrita.';
comment on column app.justification_review.payroll_period_id is
  'Competência em que a revisão foi FEITA (a não fechada mais antiga no momento), não a do '
  'fato: justificativa que chega depois do fechamento é revisada na seguinte, e nada reabre.';
comment on column app.justification_review.posted_to_source_at is
  'Quando o RH lançou a decisão no Secullum. Nulo = aprovado e ainda não lançado.';

alter table app.justification_review enable row level security;

revoke all on table app.justification_review from anon, authenticated;
grant select on table app.justification_review to authenticated;
grant select on table app.justification_review to service_role;

drop policy if exists review_read on app.justification_review;
create policy review_read on app.justification_review
  for select to authenticated
  using (exists (select 1 from app.justification j
                  where j.id = justification_id
                    and util.can_see_employee(j.employee_id)));

-- ---------------------------------------------------------------------------
-- 3. A porta
-- ---------------------------------------------------------------------------
create or replace function public.fn_revisar_justificativa(
  p_justification_id uuid, p_decision text, p_reason text)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_tenant     uuid;
  v_source     text;
  v_status     text;
  v_author     uuid;
  v_event      uuid;
  v_owner_only boolean;
  v_roles      app.user_role[];
  v_period     uuid;
  v_id         uuid;
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
  select j.tenant_id into v_tenant
    from app.justification j
   where j.id = p_justification_id;
  if found then
    v_roles := util.roles_in_tenant(v_tenant);
  end if;
  if v_tenant is null or not (v_roles && array['hr','owner']::app.user_role[]) then
    raise exception 'justification_not_found' using errcode = 'P0001';
  end if;

  -- Trava a justificativa: duas revisões concorrentes da mesma se serializam
  -- aqui, e a segunda vê a primeira (already_reviewed).
  select j.source, j.status, j.author_user_id, j.deviation_event_id, e.approval_owner_only
    into v_source, v_status, v_author, v_event, v_owner_only
    from app.justification j
    join app.employee e on e.id = j.employee_id
   where j.id = p_justification_id
     for update of j;

  -- 3. Quem explicou não decide. Autor nulo compara nulo e não bloqueia.
  if v_author = (select auth.uid()) then
    raise exception 'own_justification' using errcode = 'P0001';
  end if;

  -- 4. Quem é do RH tem o desvio aprovado pelo owner.
  if v_owner_only and not ('owner' = any(v_roles)) then
    raise exception 'owner_only' using errcode = 'P0001';
  end if;

  -- 5.
  if exists (select 1 from app.justification_review r
              where r.justification_id = p_justification_id) then
    raise exception 'already_reviewed' using errcode = 'P0001';
  end if;

  -- 6.
  if v_source = 'secullum' then
    raise exception 'source_is_mirror' using errcode = 'P0001';
  end if;

  -- 7. Depois do 6: espelho nunca é pendente (ver o cabeçalho).
  if v_status <> 'pending' then
    raise exception 'not_pending' using errcode = 'P0001';
  end if;

  -- 8. A não fechada mais antiga, fora o décimo terceiro — ver o cabeçalho.
  select p.id into v_period
    from app.payroll_period p
   where p.tenant_id = v_tenant
     and p.status <> 'fechada'
     and p.month between 1 and 12
   order by p.year, p.month
   limit 1;
  if v_period is null then
    raise exception 'no_open_period' using errcode = 'P0001';
  end if;

  -- 9.
  if p_decision = 'rejected' and coalesce(btrim(p_reason), '') = '' then
    raise exception 'rejection_needs_reason' using errcode = 'P0001';
  end if;

  -- Decisão fora do domínio cai no `check` da coluna, alto.
  insert into app.justification_review
    (tenant_id, justification_id, payroll_period_id, decision, reason, reviewed_by)
  values
    (v_tenant, p_justification_id, v_period, p_decision,
     nullif(btrim(p_reason), ''), (select auth.uid()))
  returning id into v_id;

  if p_decision = 'approved' and v_event is not null then
    perform app.revoke_deviation(v_event, 'justificativa aprovada na alçada', 'justified');
  end if;

  return v_id;
end $$;

comment on function public.fn_revisar_justificativa(uuid, text, text) is
  'A alçada: o RH (ou o owner) aprova ou reprova uma justificativa. Recusas P0001, nesta '
  'ordem: not_hr, justification_not_found (inexistente ou de outro tenant), own_justification '
  '(o chamador é o autor), owner_only (colaborador com approval_owner_only e chamador não '
  'owner), already_reviewed, source_is_mirror, not_pending (status não é pending), '
  'no_open_period (nenhuma competência não fechada, meses 1-12), rejection_needs_reason. A '
  'revisão vai para a competência não fechada mais antiga. Aprovar grava a revisão e move '
  'o desvio para justified na mesma transação; reprovar deixa o desvio active. Definer: '
  'checa o papel ela mesma. Devolve o id da revisão.';

revoke execute on function public.fn_revisar_justificativa(uuid, text, text) from public, anon;
grant  execute on function public.fn_revisar_justificativa(uuid, text, text)
  to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 5. A porta sem papel fecha
-- ---------------------------------------------------------------------------
-- `from public` também: a 11b recriou a função depois da 05, e o que sobrou no
-- ACL foi o EXECUTE de PUBLIC (medido no ensaio: `{=X/postgres,postgres=X/postgres}`)
-- — revogar só de `authenticated` deixaria o papel alcançando por herança.
-- Sem grant a ninguém: o dono (`postgres`) é quem o motor e a RPC usam.
revoke execute on function app.revoke_deviation(uuid, text, text) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 6. A fila do supervisor enxerga a revisão
-- ---------------------------------------------------------------------------
create or replace function public.fn_pending_justification(
  p_de date, p_ate date,
  p_unit_id       uuid default null,
  p_department_id uuid default null,
  p_manager_id    uuid default null
) returns table (
  deviation_event_id uuid,
  employee_id        uuid,
  employee_name      text,
  unit_id            uuid,
  unit_name          text,
  reference_date     date,
  type               text,
  type_description   text,
  minutes            integer,
  detected_at        timestamptz
)
language sql stable security invoker set search_path = ''
as $$
  select d.id, d.employee_id, e.name, d.unit_id, u.name,
         d.reference_date, d.type, t.description, d.minutes, d.detected_at
  from app.deviation_event d
  join app.employee e on e.id = d.employee_id
  join app.deviation_type t on t.code = d.type
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type
      and cfg.active and cfg.requires_justification
  left join app.unit u on u.id = d.unit_id
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_unit_id       is null or d.unit_id = p_unit_id)
    and (p_department_id is null or e.department_id = p_department_id)
    and (p_manager_id    is null or e.manager_employee_id = p_manager_id)
    and not exists (
      select 1 from app.justification j
      where j.deviation_event_id = d.id
        and (j.status = 'accepted'
             or (j.status = 'pending'
                 and not exists (select 1 from app.justification_review r
                                  where r.justification_id = j.id
                                    and r.decision = 'rejected')))
    )
  order by d.reference_date desc, e.name;
$$;

comment on function public.fn_pending_justification(date, date, uuid, uuid, uuid) is
  'Desvio ativo, de tipo que exige justificativa, que ninguém explicou: sem justificativa '
  'aceita (legada) nem pendente — esperando o RH ou aprovada. Reprovada pela alçada, volta. '
  'Devolve a existência da pendência, nunca o texto de justificativa nenhuma.';

revoke execute on function public.fn_pending_justification(date, date, uuid, uuid, uuid)
  from public, anon;
grant  execute on function public.fn_pending_justification(date, date, uuid, uuid, uuid)
  to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_tenant   uuid := gen_random_uuid();
  v_company  uuid := gen_random_uuid();
  v_employee uuid := gen_random_uuid();
  v_event    uuid;
  v_just     uuid;
  v_period   uuid;
  v_user     uuid;
  v_n        int;
  v_err      text;
begin
  -- 1. Catálogo.
  if (select column_default from information_schema.columns
      where table_schema = 'app' and table_name = 'employee'
        and column_name = 'approval_owner_only') is distinct from 'false'
     or (select is_nullable from information_schema.columns
         where table_schema = 'app' and table_name = 'employee'
           and column_name = 'approval_owner_only') <> 'NO' then
    raise exception 'approval_owner_only não é not null default false: gente sairia da alçada do RH sem ninguém ter tirado';
  end if;
  if exists (select 1 from information_schema.columns
             where table_schema = 'public' and column_name = 'approval_owner_only') then
    raise exception 'approval_owner_only exposta em public — parada obrigatória';
  end if;
  if not (select relrowsecurity from pg_class where oid = 'app.justification_review'::regclass) then
    raise exception 'app.justification_review sem RLS';
  end if;
  if not exists (select 1 from pg_indexes
                 where schemaname = 'app' and indexname = 'justification_review_uk'
                   and indexdef like 'CREATE UNIQUE INDEX%(justification_id)') then
    raise exception 'justification_review_uk ausente ou não é unique em justification_id';
  end if;
  if (select count(*) from pg_policies
      where schemaname = 'app' and tablename = 'justification_review') <> 1
     or not exists (select 1 from pg_policies
                    where schemaname = 'app' and tablename = 'justification_review'
                      and policyname = 'review_read' and cmd = 'SELECT') then
    raise exception 'app.justification_review deve ter exatamente review_read (SELECT) e nenhuma policy de escrita';
  end if;
  if exists (select 1 from unnest(array['INSERT','UPDATE','DELETE']) v
             where has_table_privilege('authenticated', 'app.justification_review', v))
     or not has_table_privilege('authenticated', 'app.justification_review', 'SELECT') then
    raise exception 'authenticated deve LER app.justification_review e nada mais';
  end if;
  if has_function_privilege('authenticated', 'app.revoke_deviation(uuid,text,text)', 'execute')
     or has_function_privilege('anon', 'app.revoke_deviation(uuid,text,text)', 'execute') then
    raise exception 'authenticated ainda executa app.revoke_deviation — a porta sem papel continua aberta';
  end if;
  -- O motor conecta como `postgres`, dono da função e da RPC.
  if not has_function_privilege('postgres', 'app.revoke_deviation(uuid,text,text)', 'execute') then
    raise exception 'postgres perdeu app.revoke_deviation — o motor não revoga mais nada';
  end if;
  if not has_function_privilege('authenticated',
       'public.fn_revisar_justificativa(uuid,text,text)', 'execute')
     or has_function_privilege('anon',
       'public.fn_revisar_justificativa(uuid,text,text)', 'execute') then
    raise exception 'fn_revisar_justificativa: authenticated precisa executar e anon não pode';
  end if;
  if not (select p.prosecdef and p.proconfig::text like '%search_path=%'
            from pg_proc p where p.oid = 'public.fn_revisar_justificativa(uuid,text,text)'::regprocedure) then
    raise exception 'fn_revisar_justificativa não é definer com search_path travado';
  end if;
  if (select p.prosecdef from pg_proc p
      where p.oid = 'public.fn_pending_justification(date,date,uuid,uuid,uuid)'::regprocedure)
     or has_function_privilege('anon',
          'public.fn_pending_justification(date,date,uuid,uuid,uuid)', 'execute')
     or not has_function_privilege('authenticated',
          'public.fn_pending_justification(date,date,uuid,uuid,uuid)', 'execute') then
    raise exception 'fn_pending_justification perdeu security invoker ou os grants';
  end if;

  -- 2. Prova viva, desfeita pela exceção 'OXP12' — só ela é engolida.
  begin
    -- Sem sessão, a primeira recusa é a primeira: not_hr.
    begin
      perform public.fn_revisar_justificativa(gen_random_uuid(), 'approved', null);
      v_err := null;
    exception when sqlstate 'P0001' then v_err := sqlerrm;
    end;
    if v_err is distinct from 'not_hr' then
      raise exception 'chamada sem papel recebeu %, não not_hr', coalesce(v_err, 'sucesso');
    end if;

    insert into app.tenant (id, slug, name)
    values (v_tenant, 'p12-proof-' || left(replace(v_tenant::text, '-', ''), 12), 'proof');
    insert into app.company (id, tenant_id, legal_name, trade_name)
    values (v_company, v_tenant, 'proof', 'proof');
    insert into app.employee (id, tenant_id, company_id, name)
    values (v_employee, v_tenant, v_company, 'proof');
    update app.deviation_type_config set requires_justification = true
     where tenant_id = v_tenant and code = 'late_entry';
    if not found then
      insert into app.deviation_type_config (tenant_id, code, active, counts_as_deviation, requires_justification)
      values (v_tenant, 'late_entry', true, true, true);
    end if;
    insert into app.deviation_event
      (tenant_id, employee_id, company_id, reference_date, type, minutes, mode)
    values (v_tenant, v_employee, v_company, '1999-03-01', 'late_entry', -15, 'production')
    returning id into v_event;

    select count(*) into v_n from public.fn_pending_justification('1999-03-01', '1999-03-01')
     where deviation_event_id = v_event;
    if v_n <> 1 then
      raise exception 'desvio sem justificativa não apareceu como pendente';
    end if;

    insert into app.justification
      (tenant_id, deviation_event_id, employee_id, reference_date, text, status, source)
    values (v_tenant, v_event, v_employee, '1999-03-01', 'proof', 'pending', 'operax')
    returning id into v_just;

    select count(*) into v_n from public.fn_pending_justification('1999-03-01', '1999-03-01')
     where deviation_event_id = v_event;
    if v_n <> 0 then
      raise exception 'justificativa pendente (esperando o RH) não tirou o desvio da fila do supervisor';
    end if;

    -- A revisão exige um autor em auth.users, que esta migration não cria.
    -- Com algum usuário no banco, a reprovação é provada aqui; sem, a suíte
    -- (98) a prova com usuários sintéticos.
    select id into v_user from auth.users limit 1;
    if v_user is not null then
      insert into app.payroll_period (tenant_id, year, month) values (v_tenant, 2000, 1)
      returning id into v_period;
      insert into app.justification_review
        (tenant_id, justification_id, payroll_period_id, decision, reason, reviewed_by)
      values (v_tenant, v_just, v_period, 'rejected', 'proof', v_user);
      select count(*) into v_n from public.fn_pending_justification('1999-03-01', '1999-03-01')
       where deviation_event_id = v_event;
      if v_n <> 1 then
        raise exception 'justificativa reprovada não devolveu o desvio à fila do supervisor';
      end if;
    else
      raise notice 'sem usuário em auth.users: a volta da reprovada à fila fica com o 98';
    end if;

    raise exception using errcode = 'OXP12', message = 'undo proof rows';
  exception when sqlstate 'OXP12' then null;
  end;

  if exists (select 1 from app.tenant where id = v_tenant) then
    raise exception 'a prova deixou rastro em app.tenant';
  end if;

  raise notice 'OK: a revisão é fato novo, só a RPC a escreve, revoke_deviation saiu do painel, e a fila enxerga a alçada.';
end $$;
