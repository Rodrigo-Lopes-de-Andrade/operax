-- ============================================================================
-- OperaX — 27. O GESTOR EXISTE NO ESPELHO, E NÃO É `manager_employee_id`
-- ----------------------------------------------------------------------------
-- O escopo pede "comparação entre equipes e gestores" (COBERTURA §4.3 item 14) e
-- ele estava marcado ❌ com a justificativa de que `employee.manager_employee_id`
-- existe mas nada o agrega. A justificativa estava incompleta: **nada o
-- PREENCHE**, e nada pode.
--
-- `manager_employee_id` é FK para `app.employee` e está declarado em
-- `operax/rh/ownership.py` como `Owner.SYNC, pending=True` — e, ao contrário de
-- todos os outros campos de sync, SEM `mirror=`. Congelado como "o Secullum
-- manda", sem coluna do Secullum atrás. O filtro `p_manager_id` dos quatro RPCs
-- (migration 22) filtra por ele: hoje ele não pode casar com nada.
--
-- O QUE A MEDIÇÃO CONTRA PRODUÇÃO MOSTROU (26/08/2026)
-- O Secullum sabe o gestor. Ele chega como `Funcionario.EstruturaId` apontando
-- para `secullum."Estrutura"` — que o próprio `sync-cadastro` deste repositório
-- chama de gestor (`listManagers`, `upsertManagers`), e que o comentário do
-- baseline descreve como "tabela do gestor".
--
--   • 4 estruturas, todas ativas;
--   • 69 dos ~70 ativos têm `EstruturaId` — cobertura praticamente total;
--   • `EstruturaPaiId` nulo nas quatro: hierarquia de um nível só;
--   • `Descricao` tem exatamente duas palavras, sem dígito, e o primeiro nome
--     das quatro casa com o primeiro nome de alguém do quadro. É pessoa.
--
-- ⛔ O QUE **NÃO** DÁ PARA FAZER, E É POR ISSO QUE ESTA TABELA EXISTE
-- Resolver qual COLABORADOR é aquele gestor. Nome completo não casa em nenhuma
-- das quatro, e o `sync-cadastro`, que já tenta esse casamento para descobrir o
-- e-mail do gestor, resolveu ZERO de 4 em produção. Escrever
-- `manager_employee_id` por semelhança de nome seria exatamente o palpite que a
-- promoção proíbe — "palpite gravado não se distingue de fato lido" — e o dado
-- prova que o palpite erraria.
--
-- Então o gestor entra como DIMENSÃO PRÓPRIA, promovida do espelho, com o nome
-- que o espelho declara. É fato lido, não inferência: o Secullum afirma que esta
-- pessoa responde a esta estrutura. Ligar a estrutura a um registro de
-- colaborador é curadoria — e fica para quando alguém quiser, sem bloquear a
-- agregação que o escopo pede.
--
-- `manager_employee_id` fica onde está, intocado, respondendo à outra pergunta:
-- "qual dos nossos colaboradores É este gestor". As duas não são a mesma.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

create table if not exists app.manager (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid   not null references app.tenant(id) on delete cascade,
  secullum_structure_id bigint not null,
  name                  text   not null,
  active                boolean not null default true,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  unique (tenant_id, secullum_structure_id)
);

create index if not exists manager_tenant_idx on app.manager (tenant_id) where active;

comment on table app.manager is
  'O gestor como o espelho o declara: `secullum."Estrutura"`, alcançada por '
  '`Funcionario.EstruturaId`. É dimensão de agregação, NÃO vínculo com um registro de '
  'colaborador — resolver qual colaborador é este gestor exigiria casar nome, e a '
  'medição de 26/08 mostrou que o casamento falha nas quatro estruturas de produção.';

comment on column app.manager.name is
  'Vem de "Estrutura"."Descricao". Nome de pessoa, e é assim que o Secullum o guarda.';

alter table app.employee
  add column if not exists manager_id uuid references app.manager(id) on delete set null;

create index if not exists employee_manager_idx on app.employee (manager_id);

comment on column app.employee.manager_id is
  'A quem esta pessoa responde, promovido de `Funcionario.EstruturaId`. NÃO confundir com '
  '`manager_employee_id`, que aponta para um `app.employee` e continua sem fonte: o espelho '
  'diz o NOME do gestor, não qual colaborador ele é.';

-- ---------------------------------------------------------------------------
-- RLS — o gestor é visível para quem enxerga alguém sob ele
-- ---------------------------------------------------------------------------
alter table app.manager enable row level security;
revoke all on table app.manager from anon;
grant select on app.manager to authenticated;
grant all    on app.manager to service_role;

drop policy if exists manager_read on app.manager;
create policy manager_read on app.manager
  for select to authenticated using (
    util.is_admin(tenant_id)
    -- Mesmo recorte de `unit_read`: ver o gestor é ver quem responde a ele. Um
    -- supervisor de uma unidade não descobre a chefia das outras por aqui.
    or exists (
      select 1 from app.employee e
       where e.manager_id = app.manager.id
         and util.can_see_employee(e.id)
    )
  );

drop policy if exists manager_write on app.manager;
create policy manager_write on app.manager
  for all to authenticated using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

-- ---------------------------------------------------------------------------
-- O ranking que faltava
-- ---------------------------------------------------------------------------
drop function if exists public.fn_ranking_by_manager(date, date, uuid, uuid, int, uuid);

create or replace function public.fn_ranking_by_manager(
  p_de date, p_ate date,
  p_company_id    uuid default null,
  p_unit_id       uuid default null,
  p_limite        int  default 20,
  p_department_id uuid default null
) returns table (
  manager_id uuid, manager_name text,
  eventos bigint, minutes_abs bigint, colaboradores bigint, unidades bigint
)
language sql stable security invoker set search_path = ''
as $$
  -- ⚠️ `left join` e sem `where m.id is not null`: quem não tem gestor vira uma
  --    linha com `manager_id` nulo em vez de sumir do ranking. Um desvio que não
  --    aparece em recorte nenhum é a patologia que a fila de unidade existe para
  --    resolver, e ela não pode voltar por aqui.
  select e.manager_id, m.name, count(*), coalesce(sum(abs(d.minutes)),0),
         count(distinct d.employee_id), count(distinct d.unit_id)
  from app.deviation_event d
  join app.employee e on e.id = d.employee_id
  join app.deviation_type_config cfg
       on cfg.tenant_id = d.tenant_id and cfg.code = d.type and cfg.counts_as_deviation and cfg.active
  left join app.manager m on m.id = e.manager_id
  where d.status = 'active' and d.mode = 'production'
    and d.reference_date between p_de and p_ate
    and (p_company_id    is null or d.company_id = p_company_id)
    and (p_unit_id       is null or d.unit_id = p_unit_id)
    and (p_department_id is null or e.department_id = p_department_id)
  group by e.manager_id, m.name
  order by count(*) desc
  limit greatest(p_limite, 1);
$$;

revoke execute on function public.fn_ranking_by_manager(date, date, uuid, uuid, int, uuid)
  from public, anon;
grant execute on function public.fn_ranking_by_manager(date, date, uuid, uuid, int, uuid)
  to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v int;
begin
  select count(*) into v from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'app' and c.relname = 'manager' and c.relrowsecurity;
  if v <> 1 then
    raise exception 'app.manager sem RLS: tabela de app com tenant_id e sem RLS é vazamento';
  end if;

  if has_function_privilege('anon',
       'public.fn_ranking_by_manager(date,date,uuid,uuid,int,uuid)', 'execute')
  then
    raise exception 'anon executa fn_ranking_by_manager';
  end if;

  -- Roda, e devolve zero linha num período vazio em vez de estourar.
  perform * from public.fn_ranking_by_manager(date '1999-01-01', date '1999-12-31');

  -- ⛔ `manager_id` e `manager_employee_id` são colunas DIFERENTES e respondem a
  --    perguntas diferentes. Uma migration futura que "unifique" as duas apaga a
  --    distinção que esta aqui existe para criar.
  select count(*) into v from information_schema.columns
   where table_schema = 'app' and table_name = 'employee'
     and column_name in ('manager_id', 'manager_employee_id');
  if v <> 2 then
    raise exception 'app.employee deveria ter as duas colunas de gestor, tem %', v;
  end if;

  raise notice 'OK: o gestor virou dimensão, e o ranking por gestor existe.';
end $$;
