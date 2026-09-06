-- ============================================================================
-- OperaX — dp_work_post. O QUADRO DE POSTOS, E SÓ ELE
-- ----------------------------------------------------------------------------
-- Desenho em `docs/SPEC-DP.md` §1c. A tela de VT do legado declara a regra com
-- todas as letras: "a escala é obtida do Quadro de Postos (código do posto +
-- unidade)". O `unique (tenant_id, unit_id, code)` abaixo é essa frase.
--
-- ⛔ O ELO COM A ESCALA NÃO ESTÁ AQUI, E A AUSÊNCIA É A DECISÃO
-- A versão anterior deste desenho tinha `work_schedule_id`, apoiada na premissa
-- — falsa — de que uma tabela de escala por dia já existia no domínio com esse
-- nome. Ela não existe. O que existe são três camadas (`SPEC-DP.md` §0-bis):
-- `secullum."HorarioDia"` é a escala por dia da origem, `app.schedule_rotation_map`
-- é curadoria de ciclo (âncora + comprimento, não escala por dia), e
-- `app.expected_workday` é a materialização por pessoa, derivada — não cadastro.
--
-- Consequência de forma, já lida: a escala é propriedade do HORÁRIO, não da
-- pessoa e não do posto. Então o elo, quando existir, é um `secullum_schedule_id`
-- neste posto — o mesmo idioma de `app.unit_secullum_map` —, em migration
-- própria de sprint posterior. Uma FK chutada aqui travaria S1 inteiro para
-- fingir que a pergunta foi respondida.
--
-- ⛔ SEM GRANT PARA `authenticated` — a etapa DP inteira é Caminho 2
-- Mesmo desenho de `app.employee_photo` (36) e `app.employee_bank_account`. As
-- policies existem mesmo assim, e não por simetria: se um PR futuro conceder
-- `select` a `authenticated` por engano, a policy é o que ainda está de pé.
--
-- LEITURA POR UNIDADE, ESCRITA POR ADMIN
-- O posto é estrutura da unidade, não dado de pessoa: não há domínio sensível a
-- perguntar. Quem enxerga a unidade enxerga o quadro dela — `util.can_see_unit`,
-- o mesmo recorte de `app.unit_responsible`. Escrever o quadro é ato de
-- administração, como em `unit_write` e `contact_admin`: `util.is_admin`.
--
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

create table if not exists app.work_post (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references app.tenant(id) on delete cascade,
  unit_id    uuid not null references app.unit(id),
  --: "7703" no legado. Único dentro da unidade, nunca globalmente: dois clientes
  --: — e duas unidades do mesmo cliente — reusam a mesma numeração.
  code       text not null,
  name       text,
  active     boolean not null default true,
  created_at timestamptz not null default now(),
  unique (tenant_id, unit_id, code)
);

create index if not exists work_post_unit_idx on app.work_post (tenant_id, unit_id);

comment on table app.work_post is
  'Quadro de Postos — unidade + código, o par que a rotina de vale transporte usa '
  'para achar a escala do colaborador. O elo posto -> escala (secullum_schedule_id) '
  'entra em migration própria: ver docs/SPEC-DP.md §0-bis.';
comment on column app.work_post.code is
  'Código do posto dentro da unidade. Único por (tenant, unidade), nunca global.';

-- ---------------------------------------------------------------------------
-- Fronteira
-- ---------------------------------------------------------------------------
alter table app.work_post enable row level security;

revoke all on table app.work_post from anon, authenticated;
-- `select, insert, update` e não `grant all`: posto sai de operação virando
-- `active = false`, porque o histórico de VT do mês passado aponta para ele.
-- Conceder `delete` e depois afirmar que ninguém apaga seria a promessa sem a
-- trava. Mesmo desvio deliberado da 36 e da `dp_banking_account`.
grant select, insert, update on table app.work_post to service_role;

drop policy if exists work_post_read on app.work_post;
create policy work_post_read on app.work_post
  for select to authenticated
  using (util.can_see_unit(unit_id));

drop policy if exists work_post_admin on app.work_post;
create policy work_post_admin on app.work_post
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));

-- ---------------------------------------------------------------------------
-- A ficha: posto e nível
-- ---------------------------------------------------------------------------
-- Aditivo e anulável, os dois de propósito. `app.employee_position` está
-- aplicada desde a migration 04 e tem linha em produção; uma coluna `not null`
-- aqui exigiria valor para cargo que ainda não foi mapeado a posto nenhum — e o
-- mapeamento é justamente o trabalho que esta etapa começa.
alter table app.employee_position
  add column if not exists work_post_id uuid references app.work_post(id);
--: "Nível: OPERADOR" da ficha do legado. Texto porque a lista de níveis é do
--: cliente e muda sem deploy; um enum aqui viraria migration por rótulo novo.
alter table app.employee_position
  add column if not exists level text;

comment on column app.employee_position.work_post_id is
  'Posto do Quadro de Postos em que a pessoa exerce este cargo. Anulável: cargo sem posto mapeado é o estado inicial.';
comment on column app.employee_position.level is
  'Nível dentro do cargo ("OPERADOR" na ficha do legado). Rótulo do cliente, não enum.';

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v_privilege  text;
  v_policies   int;
  v_read_qual  text;
  v_admin_qual text;
  v_admin_chk  text;
  v_notnull    int;
begin
  if to_regclass('app.work_post') is null then
    raise exception 'app.work_post não existe depois de ser criada';
  end if;

  -- 1. Regra 3 do CLAUDE.md: tenant_id e RLS, as duas coisas.
  if not exists (
    select 1 from information_schema.columns
     where table_schema = 'app' and table_name = 'work_post' and column_name = 'tenant_id'
  ) then
    raise exception 'app.work_post sem tenant_id — regra 3 do CLAUDE.md';
  end if;
  if not (select relrowsecurity from pg_class where oid = 'app.work_post'::regclass) then
    raise exception 'app.work_post sem RLS — regra 3 do CLAUDE.md';
  end if;

  -- 2. A frase da tela de VT virando constraint. Sem ela, dois postos "7703" na
  --    mesma unidade tornam a busca da escala ambígua — e ambígua ela devolve a
  --    escala de outra pessoa, calada. O conjunto de colunas é comparado inteiro:
  --    um unique só em (tenant_id, code) proibiria o mesmo código em duas
  --    unidades, e um só em (unit_id, code) atravessaria tenant.
  if not exists (
    select 1
      from pg_constraint c
     where c.conrelid = 'app.work_post'::regclass
       and c.contype = 'u'
       and (select array_agg(a.attname::text order by a.attname)
              from unnest(c.conkey) k
              join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k)
           = array['code','tenant_id','unit_id']
  ) then
    raise exception 'app.work_post sem unique (tenant_id, unit_id, code) — a regra da tela de VT';
  end if;

  -- 3. Fora do PostgREST, em todos os verbos.
  foreach v_privilege in array array['SELECT','INSERT','UPDATE','DELETE'] loop
    if has_table_privilege('authenticated', 'app.work_post', v_privilege) then
      raise exception 'authenticated tem % em app.work_post — a etapa DP é só Caminho 2', v_privilege;
    end if;
    if has_table_privilege('anon', 'app.work_post', v_privilege) then
      raise exception 'anon tem % em app.work_post', v_privilege;
    end if;
  end loop;

  -- 4. O positivo. Sem ele o item 3 fica verde numa tabela que ninguém alcança.
  foreach v_privilege in array array['SELECT','INSERT','UPDATE'] loop
    if not has_table_privilege('service_role', 'app.work_post', v_privilege) then
      raise exception 'service_role não tem % em app.work_post — o Caminho 2 não funcionaria', v_privilege;
    end if;
  end loop;
  foreach v_privilege in array array['DELETE','TRUNCATE'] loop
    if has_table_privilege('service_role', 'app.work_post', v_privilege) then
      raise exception 'service_role tem % em app.work_post; posto sai de operação com active = false', v_privilege;
    end if;
  end loop;

  -- 5. Duas policies, e o texto de cada uma. Contar sem ler deixaria passar uma
  --    policy de leitura que trocou `can_see_unit` por `has_tenant` — o que daria
  --    o quadro de toda unidade ao supervisor de uma.
  select count(*) into v_policies from pg_policies
   where schemaname = 'app' and tablename = 'work_post';
  if v_policies <> 2 then
    raise exception 'app.work_post tem % policies, esperava 2 (read e admin)', v_policies;
  end if;

  select qual into v_read_qual from pg_policies
   where schemaname = 'app' and tablename = 'work_post' and policyname = 'work_post_read';
  if coalesce(v_read_qual, '') not like '%can_see_unit%' then
    raise exception 'work_post_read sem util.can_see_unit — o quadro de toda unidade vazaria para o supervisor de uma';
  end if;

  select qual, with_check into v_admin_qual, v_admin_chk from pg_policies
   where schemaname = 'app' and tablename = 'work_post' and policyname = 'work_post_admin';
  if coalesce(v_admin_qual, '') not like '%is_admin%' then
    raise exception 'work_post_admin sem util.is_admin no using';
  end if;
  -- As duas expressões em separado, e não por cerimônia: num INSERT quem decide
  -- é o `with check`; olhar só o `using` deixaria passar a metade que decide.
  if coalesce(v_admin_chk, '') not like '%is_admin%' then
    raise exception 'work_post_admin sem util.is_admin no with check — é ele que decide o INSERT';
  end if;

  -- 6. As duas colunas da ficha, e a anulabilidade delas. `not null` aqui
  --    quebraria toda linha de `app.employee_position` que já existe.
  if not exists (
    select 1 from information_schema.columns
     where table_schema = 'app' and table_name = 'employee_position' and column_name = 'work_post_id'
  ) then
    raise exception 'app.employee_position não ganhou work_post_id';
  end if;
  select count(*) into v_notnull from information_schema.columns
   where table_schema = 'app' and table_name = 'employee_position'
     and column_name in ('work_post_id','level') and is_nullable = 'NO';
  if v_notnull <> 0 then
    raise exception '% coluna(s) nova(s) de employee_position são not null — o desenho é aditivo e anulável', v_notnull;
  end if;
  if not exists (
    select 1 from pg_constraint c
     where c.conrelid = 'app.employee_position'::regclass
       and c.contype = 'f'
       and c.confrelid = 'app.work_post'::regclass
  ) then
    raise exception 'employee_position.work_post_id não referencia app.work_post';
  end if;

  raise notice
    'OK: app.work_post fora do PostgREST, unique (tenant, unidade, código) de pé, '
    'leitura por unidade e escrita por admin; employee_position com posto e nível anuláveis.';
end $$;
