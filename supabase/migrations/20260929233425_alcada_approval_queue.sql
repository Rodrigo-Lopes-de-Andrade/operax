-- ============================================================================
-- OperaX — alcada_approval_queue. A FILA DO RH, NA JANELA 21→20
-- ----------------------------------------------------------------------------
-- Desenho: `docs/DECISAO-ALCADA-APROVACAO.md` §4.4; sprint P1.3 de
-- `docs/SPRINTS-ALCADA.md`. Decisões do dono de 29/09/2026 (paradas cumpridas):
-- janela 21→20, `security invoker`, e só `hr`/`owner` usam a fila.
--
-- 1. `util.competencia_janela(ano, mês) -> (period_start, period_end)` — 21 do
--    mês ANTERIOR a 20 do mês, com virada de ano. É a mesma janela do vale
--    transporte (`backend/operax/dp/ciclo.py`, `cycle_window`), e
--    `scripts/80_teste_janela_competencia.py` confere as duas mês a mês. Mês
--    fora de 1–12 estoura no `make_date`, alto: o 13º não tem janela de ponto.
--    Pura: não lê tabela nenhuma, então não é definer.
--
-- 1b. `util.competencia_de(data) -> (period_year, period_month)` — a competência
--    que CONTÉM a data. Não é uma segunda cópia da regra: não há 21 nem 20
--    aqui. Ela pergunta a `util.competencia_janela` qual das duas candidatas (o
--    mês da data e o seguinte) contém a data — a única premissa é que a janela
--    tem cerca de um mês e termina no mês de referência. O backend a usa para a
--    competência corrente da fila (o "hoje" vem do relógio do tenant), e
--    `scripts/80_teste_janela_competencia.py` confere, dia a dia, que a
--    resposta é única e que a janela dela contém a data.
--
-- 2. `public.fn_fila_aprovacao(ano, mês, unidade?, colaborador?, de?, até?)` —
--    as justificativas `pending` SEM revisão cujo FATO (`reference_date` da
--    justificativa, que é a do desvio) cai na janela da competência.
--    `security invoker`: a RLS do chamador vale inteira (`justification_read`,
--    `employee`, `deviation_event`, `unit`, `review_read`) — o tenant NÃO é
--    parâmetro, e não adianta mandar.
--    FILTROS: unidade, colaborador e data. A data é `de`/`até`, os dois
--    opcionais e inclusivos — um dia é `de = até`. Eles só ESTREITAM: a janela
--    continua valendo, então uma data fora dela devolve vazio em vez de alargar
--    a competência.
--    QUEM RECEBE LINHA: só quem é `hr` ou `owner` no tenant DA LINHA
--    (`util.roles_in_tenant`). Para os demais a fila é VAZIA, não erro — é a
--    mesma semântica da RLS ("você vê o que pode"), e o backend responde 403
--    antes de chamá-la. Com isso o supervisor não alcança linha nenhuma, de
--    unidade nenhuma, por filtro nenhum; e se esta checagem sumir, a RLS ainda
--    o prende à própria unidade.
--    UNIDADE: a do desvio (`deviation_event.unit_id`, a do dia, como
--    `fn_pending_justification`); a do colaborador quando a justificativa não
--    tem desvio.
--    COLUNAS: justification_id, employee_id, employee_name, unit_id, unit_name,
--    reference_date, type, type_description, minutes, text, author_name,
--    created_at, can_review, blocked_reason. `type`/`type_description`/`minutes`
--    são nulos sem desvio.
--    `can_review` / `blocked_reason` — decisão do dono (29/09/2026): o chamador
--    pode revisar esta linha AGORA? Bloqueada, a linha CONTINUA na fila, com o
--    motivo: `own_justification` (o chamador é o autor; autor nulo não
--    bloqueia) ou `owner_only` (colaborador com `approval_owner_only` e
--    chamador sem `owner` no tenant). Com as duas, vale a que
--    `fn_revisar_justificativa` devolve primeiro: `own_justification`. É a
--    MESMA regra, na MESMA ordem, dos passos 3 e 4 da RPC — o `98` chama a RPC
--    em cada linha da fila e confere que ela recusa com exatamente esse código.
--    O estado do desvio NÃO filtra: uma pendente cujo desvio foi revogado
--    continua na fila — some o indício, não some a pergunta ao RH.
--
-- ⚠️ `trg_lock_down_new_function` NÃO cobre `public`: o revoke e o
--    `grant execute … to authenticated` estão escritos aqui. Em `util` ele tira
--    PUBLIC e anon; o grant a `authenticated` também está escrito, porque a
--    fila é invoker e chama a janela como o usuário.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. A janela
-- ---------------------------------------------------------------------------
create or replace function util.competencia_janela(p_year int, p_month int)
returns table (period_start date, period_end date)
language sql immutable set search_path = ''
as $$
  select (make_date(p_year, p_month, 1) - interval '1 month' + interval '20 days')::date,
         make_date(p_year, p_month, 20);
$$;

comment on function util.competencia_janela(int, int) is
  'A janela da competência: 21 do mês anterior a 20 do mês (virada de ano incluída). A mesma '
  'de backend/operax/dp/ciclo.py (cycle_window, VT), conferida por '
  'scripts/80_teste_janela_competencia.py. Decisão do dono, 29/09/2026.';

revoke execute on function util.competencia_janela(int, int) from public, anon;
grant  execute on function util.competencia_janela(int, int) to authenticated, service_role;

create or replace function util.competencia_de(p_date date)
returns table (period_year int, period_month int)
language sql immutable set search_path = ''
as $$
  select extract(year from c.m)::int, extract(month from c.m)::int
    from (values (date_trunc('month', p_date)),
                 (date_trunc('month', p_date) + interval '1 month')) c(m)
   cross join lateral util.competencia_janela(extract(year from c.m)::int,
                                              extract(month from c.m)::int) w
   where p_date between w.period_start and w.period_end;
$$;

comment on function util.competencia_de(date) is
  'A competência (ano, mês) cuja janela util.competencia_janela contém a data. Derivada da '
  'janela, sem cópia da regra 21→20. Conferida dia a dia por scripts/80_teste_janela_competencia.py.';

revoke execute on function util.competencia_de(date) from public, anon;
grant  execute on function util.competencia_de(date) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. A fila
-- ---------------------------------------------------------------------------
create or replace function public.fn_fila_aprovacao(
  p_year        int,
  p_month       int,
  p_unit_id     uuid default null,
  p_employee_id uuid default null,
  p_de          date default null,
  p_ate         date default null
) returns table (
  justification_id uuid,
  employee_id      uuid,
  employee_name    text,
  unit_id          uuid,
  unit_name        text,
  reference_date   date,
  type             text,
  type_description text,
  minutes          integer,
  text             text,
  author_name      text,
  created_at       timestamptz,
  can_review       boolean,
  blocked_reason   text
)
language sql stable security invoker set search_path = ''
as $$
  select j.id, j.employee_id, e.name, coalesce(d.unit_id, e.unit_id), u.name,
         j.reference_date, d.type, t.description, d.minutes, j.text, j.author_name,
         j.created_at, b.reason is null, b.reason
  from util.competencia_janela(p_year, p_month) w
  join app.justification j
       on j.reference_date between w.period_start and w.period_end
  join app.employee e on e.id = j.employee_id
  left join app.deviation_event d on d.id = j.deviation_event_id
  left join app.deviation_type t on t.code = d.type
  left join app.unit u on u.id = coalesce(d.unit_id, e.unit_id)
  -- Os passos 3 e 4 de fn_revisar_justificativa, na ordem dela.
  cross join lateral (
    select case
             when j.author_user_id = (select auth.uid()) then 'own_justification'
             when e.approval_owner_only
                  and not ('owner' = any(util.roles_in_tenant(j.tenant_id))) then 'owner_only'
           end as reason
  ) b
  where j.status = 'pending'
    and util.roles_in_tenant(j.tenant_id) && array['hr','owner']::app.user_role[]
    and not exists (select 1 from app.justification_review r
                     where r.justification_id = j.id)
    and (p_unit_id     is null or coalesce(d.unit_id, e.unit_id) = p_unit_id)
    and (p_employee_id is null or j.employee_id = p_employee_id)
    and (p_de          is null or j.reference_date >= p_de)
    and (p_ate         is null or j.reference_date <= p_ate)
  order by j.reference_date, e.name, j.created_at;
$$;

comment on function public.fn_fila_aprovacao(int, int, uuid, uuid, date, date) is
  'A fila da alçada: justificativas pending sem revisão cujo fato cai na janela 21→20 da '
  'competência (util.competencia_janela), com filtros de unidade, colaborador e data (de/até, '
  'inclusivos, só estreitam). Invoker: a RLS do chamador vale. Só hr e owner recebem linha; '
  'os demais recebem vazio. can_review/blocked_reason: se o chamador pode revisar a linha '
  'agora; senão own_justification ou owner_only, na ordem de fn_revisar_justificativa — a '
  'linha bloqueada continua na fila. Chamada pelo backend como o usuário (Caminho 2).';

revoke execute on function public.fn_fila_aprovacao(int, int, uuid, uuid, date, date)
  from public, anon;
grant  execute on function public.fn_fila_aprovacao(int, int, uuid, uuid, date, date)
  to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_fila regprocedure := 'public.fn_fila_aprovacao(int,int,uuid,uuid,date,date)'::regprocedure;
  v_jan  regprocedure := 'util.competencia_janela(int,int)'::regprocedure;
  v_s    date;
  v_e    date;
begin
  -- 1. A janela, nas bordas que importam.
  select period_start, period_end into v_s, v_e from util.competencia_janela(2027, 1);
  if (v_s, v_e) <> ('2026-12-21'::date, '2027-01-20'::date) then
    raise exception 'competencia_janela(2027,1) = %..%, esperado 2026-12-21..2027-01-20', v_s, v_e;
  end if;
  select period_start, period_end into v_s, v_e from util.competencia_janela(2024, 3);
  if (v_s, v_e) <> ('2024-02-21'::date, '2024-03-20'::date) then
    raise exception 'competencia_janela(2024,3) = %..%, esperado 2024-02-21..2024-03-20', v_s, v_e;
  end if;
  if (select count(*) from util.competencia_de('2026-12-20')) <> 1
     or (select row(period_year, period_month)::text from util.competencia_de('2026-12-20'))
        <> '(2026,12)'
     or (select row(period_year, period_month)::text from util.competencia_de('2026-12-21'))
        <> '(2027,1)' then
    raise exception 'competencia_de fora da janela: 20/12/2026 é 2026/12 e 21/12/2026 é 2027/01';
  end if;
  if has_function_privilege('anon', 'util.competencia_de(date)', 'execute')
     or not has_function_privilege('authenticated', 'util.competencia_de(date)', 'execute') then
    raise exception 'util.competencia_de: authenticated executa e anon não';
  end if;
  select period_start, period_end into v_s, v_e from util.competencia_janela(2026, 12);
  if (v_s, v_e) <> ('2026-11-21'::date, '2026-12-20'::date) then
    raise exception 'competencia_janela(2026,12) = %..%, esperado 2026-11-21..2026-12-20', v_s, v_e;
  end if;

  -- 2. A fila é invoker, com search_path travado, e a janela é a do util.
  if (select p.prosecdef from pg_proc p where p.oid = v_fila) then
    raise exception 'fn_fila_aprovacao é definer: ignoraria a RLS e devolveria justificativa de toda unidade';
  end if;
  if not (select coalesce(p.proconfig::text like '%search_path=%', false)
            from pg_proc p where p.oid = v_fila) then
    raise exception 'fn_fila_aprovacao sem search_path travado';
  end if;
  if pg_get_functiondef(v_fila) not like '%util.competencia_janela(p_year, p_month)%' then
    raise exception 'fn_fila_aprovacao não tira a janela de util.competencia_janela';
  end if;
  if pg_get_function_result(v_fila) not like '%can_review boolean, blocked_reason text)' then
    raise exception 'fn_fila_aprovacao sem can_review/blocked_reason no fim do retorno';
  end if;
  if position('own_justification' in pg_get_functiondef(v_fila))
     > position('owner_only' in pg_get_functiondef(v_fila))
     or position('owner_only' in pg_get_functiondef(v_fila)) = 0 then
    raise exception 'blocked_reason fora da ordem da RPC: own_justification vem antes de owner_only';
  end if;
  if pg_get_functiondef(v_fila) not like '%util.roles_in_tenant(j.tenant_id)%' then
    raise exception 'fn_fila_aprovacao perdeu a checagem de hr/owner no tenant da linha';
  end if;

  -- 3. Grants.
  if has_function_privilege('anon', v_fila, 'execute')
     or has_function_privilege('anon', v_jan, 'execute') then
    raise exception 'anon executa a fila ou a janela';
  end if;
  if not has_function_privilege('authenticated', v_fila, 'execute')
     or not has_function_privilege('authenticated', v_jan, 'execute') then
    raise exception 'authenticated precisa executar a fila e a janela (a fila é invoker)';
  end if;

  -- 4. Sem sessão não há papel: a fila responde vazio, nunca a fila de todos.
  if exists (select 1 from public.fn_fila_aprovacao(2026, 9)) then
    raise exception 'fn_fila_aprovacao devolveu linha sem usuário na sessão';
  end if;

  raise notice 'OK: a janela é 21→20, a fila é invoker, só hr/owner recebem linha, e anon não chama.';
end $$;
