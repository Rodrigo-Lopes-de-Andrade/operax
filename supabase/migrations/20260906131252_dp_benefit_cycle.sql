-- ============================================================================
-- OperaX — dp_benefit_cycle. A ROTINA MENSAL, UM MODELO PARA AS DUAS
-- ----------------------------------------------------------------------------
-- DDL transcrito de `docs/SPEC-DP.md` §1e. Cesta e vale transporte são o MESMO
-- objeto: um ciclo do mês que apura direito por pessoa com um motivo. Um modelo,
-- dois `kind` — não dois modelos paralelos, que divergiriam na primeira regra
-- que valesse só para um deles.
--
-- ⛔ CICLO `generated` OU `exported` É IMUTÁVEL — REGRA 9 DO `PRD-DP.md`
-- Correção é ciclo NOVO com `reason`, nunca `update`. O que faz isso valer não é
-- a rota lembrar: é o gatilho `trg_benefit_cycle_immutable`. Um ciclo gerado é o
-- documento que diz quanto cada pessoa recebeu naquele mês; reescrevê-lo muda o
-- passado sem deixar rastro, e a conferência do mês seguinte passa a comparar
-- contra um número que nunca foi pago.
--
-- ⚠️ E A TRAVA COBRE AS DUAS TABELAS, SENÃO ELA É METADE
-- Congelar só o cabeçalho e deixar `app.benefit_entitlement` aberta congelaria a
-- janela e liberaria O DINHEIRO. `trg_benefit_entitlement_immutable` recusa
-- insert, update E delete de linha cujo ciclo não está em `draft` — inclusive o
-- insert, porque acrescentar uma pessoa a um ciclo já gerado é a mesma
-- reescrita, feita pela porta dos fundos.
--
-- O QUE A TRAVA DEIXA PASSAR, E POR QUÊ
-- `status` avança sozinho: `generated -> exported`, `generated -> cancelled`,
-- `exported -> cancelled`. Sem essa fresta, o valor `exported` do próprio check
-- da SPEC seria inalcançável e `cancelled` também — e cancelar é a metade
-- necessária de "correção é ciclo novo": alguém tem de aposentar o errado.
-- Nenhuma outra coluna muda, e `cancelled` não volta atrás.
-- ⚠️ Nada nesta sprint escreve `exported`: a rota de export é `GET`, e `GET` não
-- muda estado. O valor existe porque a SPEC o declara, e a trava já o cobre para
-- quando a ação de marcar existir.
--
-- ⚠️ O `unique` VEM DA SPEC COM `status` DENTRO, E ISSO NÃO É DESCUIDO
-- `(tenant, kind, ano, mês, status)` permite um `draft` e um `generated` da mesma
-- competência convivendo — que é exatamente o fluxo: preview enquanto se
-- confere, congelado quando fecha. Ele é `deferrable initially deferred` como a
-- SPEC manda; a consequência prática está declarada em `operax/dp/ciclo.py`:
-- índice adiável NÃO serve de árbitro para `on conflict`, então a reserva do
-- rascunho é `select` e depois `insert`, e a corrida de dois pedidos simultâneos
-- estoura no commit e vira 409.
--
-- ⛔ SEM GRANT PARA `authenticated` — a etapa DP inteira é Caminho 2
-- Mesmo desenho de `app.employee_bank_account` e das quatro da
-- `dp_benefit_catalog`. As policies ficam de pé para o dia em que um PR conceder
-- `select` por engano.
--
-- AS POLICIES SÃO AS JÁ APROVADAS NESTA ETAPA, SEM EIXO NOVO
-- `benefit_cycle` é objeto do tenant e não tem pessoa: leitura por
-- `util.can_see_domain(tenant, 'compensation')`, escrita por `util.is_admin` — o
-- par de `benefit_type`/`benefit_plan`/`transport_fare`, apertado por decisão do
-- dono em 06/09. `benefit_entitlement` guarda valor POR COLABORADOR: leitura com
-- dois eixos, escrita com três, que é a forma de `employee_benefit`.
--
-- Depende de `dp_benefit_catalog` (tarifa e vínculo) e de `dp_absence_map`
-- (curadoria da falta) pela ordem do diretório.
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. O ciclo — a competência
-- ---------------------------------------------------------------------------
create table if not exists app.benefit_cycle (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references app.tenant(id) on delete cascade,
  kind          text not null check (kind in ('food_basket','transport_voucher')),
  period_year   smallint not null,
  period_month  smallint not null check (period_month between 1 and 12),
  --: VT: 21 do mês anterior.
  window_start  date not null,
  --: VT: 20 do mês de referência.
  window_end    date not null,
  --: Dias com expediente na janela, derivados da MESMA fonte de `days_base`
  --: (`app.expected_workday`). Cabeçalho: nunca entra em dinheiro.
  business_days smallint,
  status        text not null default 'draft'
    check (status in ('draft','generated','exported','cancelled')),
  generated_at  timestamptz,
  generated_by  uuid,
  created_at    timestamptz not null default now(),
  --: Nome explícito: o automático passaria de 63 caracteres e viria truncado,
  --: e a garantia lá embaixo precisa achá-lo.
  constraint benefit_cycle_period_key
    unique (tenant_id, kind, period_year, period_month, status)
    deferrable initially deferred
);

create index if not exists benefit_cycle_competencia_idx
  on app.benefit_cycle (tenant_id, kind, period_year desc, period_month desc);

comment on table app.benefit_cycle is
  'Competência de cesta ou de vale transporte. Um modelo, dois kind. Ciclo generated ou '
  'exported é imutável (regra 9 do PRD-DP): correção é ciclo novo com reason, nunca update.';
comment on column app.benefit_cycle.business_days is
  'Dias com expediente na janela. Cabeçalho da tela; nunca entra em net_days nem em total_amount.';

-- ---------------------------------------------------------------------------
-- 2. A linha por pessoa
-- ---------------------------------------------------------------------------
-- As colunas de dias ficam NULAS para cesta — mesmo modelo, campos que não se
-- aplicam vazios. É mais barato que duas tabelas quase iguais, e é a decisão da
-- §1e.
--
-- ⛔ `reason` NÃO É DECORAÇÃO: a §1e manda gravar QUAL das duas causas tirou a
--    cesta ("a pessoa vai perguntar"). Uma coluna `entitled` sozinha responde
--    "não" e obriga o DP a refazer a conta à mão para saber por quê.
create table if not exists app.benefit_entitlement (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references app.tenant(id) on delete cascade,
  cycle_id          uuid not null references app.benefit_cycle(id) on delete cascade,
  employee_id       uuid not null references app.employee(id) on delete cascade,
  --: Lotação em `app.employee.unit_id`. A "unidade atuando" do legado é
  --: projeção da movimentação vigente e chega com `dp_movement_period` (S4).
  unit_id           uuid references app.unit(id),
  entitled          boolean not null,
  reason            text,
  --: Nulas para cesta.
  days_base         smallint,
  absences_prior    smallint,
  net_days          smallint,
  unit_amount       numeric(12,2),
  round_trip_amount numeric(12,2),
  total_amount      numeric(12,2),
  created_at        timestamptz not null default now(),
  --: O grão que a §1e declara em prosa ("a linha por pessoa"), virando
  --: estrutura. É ele que faz o rascunho ser reconstruível sem duplicar.
  unique (cycle_id, employee_id)
);

create index if not exists benefit_entitlement_ciclo_idx
  on app.benefit_entitlement (tenant_id, cycle_id);
create index if not exists benefit_entitlement_colab_idx
  on app.benefit_entitlement (tenant_id, employee_id);

comment on table app.benefit_entitlement is
  'Uma linha por pessoa por ciclo. Colunas de dias nulas para cesta. reason grava QUAL causa '
  'tirou o direito — falta injustificada ou admissão depois do início do período.';

-- ---------------------------------------------------------------------------
-- 3. Fronteira
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['benefit_cycle','benefit_entitlement'] loop
    execute format('alter table app.%I enable row level security', t);
    execute format('revoke all on table app.%I from anon, authenticated', t);
  end loop;
end $$;

-- Ciclo não se apaga: sai por `status = 'cancelled'`, porque o mês passado foi
-- pago com ele. Regra 6 do projeto estendida à competência.
grant select, insert, update on table app.benefit_cycle to service_role;
-- A linha, sim, precisa de `delete`: reconstruir um RASCUNHO é apagar as linhas
-- dele e recalcular. O que impede isso de alcançar um ciclo gerado é o gatilho,
-- não a ausência do grant — e `update` não é concedido porque linha de ciclo
-- não se edita: ou o rascunho é refeito, ou o ciclo é outro.
grant select, insert, delete on table app.benefit_entitlement to service_role;

drop policy if exists benefit_cycle_read on app.benefit_cycle;
create policy benefit_cycle_read on app.benefit_cycle
  for select to authenticated using (util.can_see_domain(tenant_id, 'compensation'));

drop policy if exists benefit_cycle_admin on app.benefit_cycle;
create policy benefit_cycle_admin on app.benefit_cycle
  for all to authenticated
  using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

-- Valor por pessoa: dois eixos para ler.
drop policy if exists benefit_entitlement_read on app.benefit_entitlement;
create policy benefit_entitlement_read on app.benefit_entitlement
  for select to authenticated
  using (
    util.can_see_domain(tenant_id, 'compensation')
    and util.can_see_employee(employee_id)
  );

-- ⛔ TRÊS para escrever. O terceiro eixo separa quem confere de quem apura:
--    `accounting` concilia a remessa e não refaz o ciclo de ninguém.
drop policy if exists benefit_entitlement_write on app.benefit_entitlement;
create policy benefit_entitlement_write on app.benefit_entitlement
  for all to authenticated
  using (
    util.can_see_domain(tenant_id, 'compensation')
    and util.can_see_employee(employee_id)
    and util.is_admin(tenant_id)
  )
  with check (
    util.can_see_domain(tenant_id, 'compensation')
    and util.can_see_employee(employee_id)
    and util.is_admin(tenant_id)
  );

-- ---------------------------------------------------------------------------
-- 4. A imutabilidade
-- ---------------------------------------------------------------------------
-- ⚠️ `check_violation` E NÃO UM CÓDIGO PRÓPRIO
-- É o código que o Postgres usa para "esta linha viola uma regra da tabela", que
-- é literalmente o caso. Inventar um SQLSTATE novo obrigaria todo caminho de
-- escrita a conhecer um dialeto deste repositório — e a `dp_benefit_catalog` já
-- fixou o padrão de reusar o código padrão que significa a mesma coisa
-- (`unique_violation`, lá).
create or replace function util.enforce_benefit_cycle_immutable()
returns trigger
language plpgsql security definer set search_path = ''
as $trg$
begin
  -- Rascunho é rascunho: enquanto ninguém congelou, refazer é o fluxo.
  if old.status = 'draft' then
    if tg_op = 'DELETE' then
      return old;
    end if;
    return new;
  end if;

  if tg_op = 'DELETE' then
    raise exception using
      errcode = 'check_violation',
      message = 'Ciclo já gerado não é apagado.',
      hint    = 'Cancele o ciclo (status = cancelled) e apure um ciclo novo com o motivo. Regra 6 do projeto: nada de delete físico.';
  end if;

  -- Daqui para baixo, `old.status` é generated, exported ou cancelled.
  if new.status is distinct from old.status then
    if not (
         (old.status = 'generated' and new.status in ('exported','cancelled'))
      or (old.status = 'exported'  and new.status = 'cancelled')
    ) then
      raise exception using
        errcode = 'check_violation',
        message = format('Transição de status %s -> %s não existe.', old.status, new.status),
        hint    = 'Um ciclo avança de generated para exported ou cancelled, e de exported para cancelled. Voltar atrás seria reescrever o que já foi pago.';
    end if;
  end if;

  -- E só o status muda. A comparação é da linha INTEIRA menos o status: listar
  -- coluna por coluna deixaria a próxima coluna nova fora da trava, calada — e
  -- a próxima coluna nova é justamente a que ninguém revisa. `to_jsonb` e não
  -- `hstore`: a extensão não está instalada, e uma trava que depende de
  -- extensão ausente não tranca nada.
  if (to_jsonb(new) - 'status') is distinct from (to_jsonb(old) - 'status') then
    raise exception using
      errcode = 'check_violation',
      message = 'Ciclo gerado é imutável: só o status avança.',
      hint    = 'Correção é ciclo novo com reason, nunca update. Regra 9 do PRD-DP.';
  end if;

  return new;
end $trg$;

comment on function util.enforce_benefit_cycle_immutable() is
  'Regra 9 do PRD-DP virando gatilho. Ciclo generated/exported só avança de status; nada é '
  'apagado. Correção é ciclo novo com reason.';

drop trigger if exists trg_benefit_cycle_immutable on app.benefit_cycle;
create trigger trg_benefit_cycle_immutable
  before update or delete on app.benefit_cycle
  for each row execute function util.enforce_benefit_cycle_immutable();

create or replace function util.enforce_benefit_entitlement_immutable()
returns trigger
language plpgsql security definer set search_path = ''
as $trg$
declare
  v_cycle  uuid;
  v_status text;
begin
  v_cycle := case when tg_op = 'DELETE' then old.cycle_id else new.cycle_id end;
  select c.status into v_status from app.benefit_cycle c where c.id = v_cycle;

  -- `coalesce` porque a FK garante que o ciclo existe, não que a leitura
  -- devolva linha: ciclo ausente é estado impossível, e tratá-lo como
  -- congelado é a resposta segura.
  if coalesce(v_status, 'generated') <> 'draft' then
    raise exception using
      errcode = 'check_violation',
      message = format('O ciclo está em %s: a apuração dele não se mexe mais.',
                       coalesce(v_status, 'estado desconhecido')),
      hint    = 'Congelar o cabeçalho e deixar as linhas abertas congelaria a janela e liberaria o dinheiro. Correção é ciclo novo com reason.';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end $trg$;

comment on function util.enforce_benefit_entitlement_immutable() is
  'A outra metade da regra 9: linha de ciclo congelado não entra, não muda e não sai. Sem ela, '
  'a trava do cabeçalho congelaria a janela e deixaria o dinheiro aberto.';

drop trigger if exists trg_benefit_entitlement_immutable on app.benefit_entitlement;
create trigger trg_benefit_entitlement_immutable
  before insert or update or delete on app.benefit_entitlement
  for each row execute function util.enforce_benefit_entitlement_immutable();

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v_table     text;
  v_privilege text;
  v_policies  int;
  v_qual      text;
  v_chk       text;
  v_trigger   record;
  v_columns   text[];
  v_deferred  boolean;
  v_tenant    uuid;
  v_company   uuid;
  v_employee  uuid;
  v_cycle     uuid;
  v_line      uuid;
  v_barrou    boolean;
begin
  foreach v_table in array array['benefit_cycle','benefit_entitlement'] loop
    if to_regclass('app.' || v_table) is null then
      raise exception 'app.% não existe depois de ser criada', v_table;
    end if;

    -- 1. Regra 3 do CLAUDE.md.
    if not exists (
      select 1 from information_schema.columns
       where table_schema = 'app' and table_name = v_table and column_name = 'tenant_id'
    ) then
      raise exception 'app.% sem tenant_id — regra 3 do CLAUDE.md', v_table;
    end if;
    if not (select relrowsecurity from pg_class where oid = ('app.' || v_table)::regclass) then
      raise exception 'app.% sem RLS — regra 3 do CLAUDE.md', v_table;
    end if;

    -- 2. Fora do PostgREST em todos os verbos. Perguntar só por `select`
    --    deixaria um `grant insert` passar — e inventar linha de ciclo é pior
    --    que lê-la: ela é o valor que a remessa paga.
    foreach v_privilege in array array['SELECT','INSERT','UPDATE','DELETE'] loop
      if has_table_privilege('authenticated', 'app.' || v_table, v_privilege) then
        raise exception 'authenticated tem % em app.% — a etapa DP é só Caminho 2', v_privilege, v_table;
      end if;
      if has_table_privilege('anon', 'app.' || v_table, v_privilege) then
        raise exception 'anon tem % em app.%', v_privilege, v_table;
      end if;
    end loop;

    -- 3. O positivo: sem ele o item 2 fica verde em duas tabelas que ninguém
    --    alcança, e o Caminho 2 não existiria.
    foreach v_privilege in array array['SELECT','INSERT'] loop
      if not has_table_privilege('service_role', 'app.' || v_table, v_privilege) then
        raise exception 'service_role não tem % em app.% — o apurador não gravaria', v_privilege, v_table;
      end if;
    end loop;

    select count(*) into v_policies from pg_policies
     where schemaname = 'app' and tablename = v_table;
    if v_policies <> 2 then
      raise exception 'app.% tem % policies, esperava 2 (read e write)', v_table, v_policies;
    end if;
  end loop;

  -- 4. O ciclo não se apaga; a linha do rascunho, sim.
  if has_table_privilege('service_role', 'app.benefit_cycle', 'DELETE') then
    raise exception 'service_role tem DELETE em app.benefit_cycle; competência sai por status = cancelled, não por delete';
  end if;
  if not has_table_privilege('service_role', 'app.benefit_entitlement', 'DELETE') then
    raise exception 'service_role não tem DELETE em app.benefit_entitlement; refazer um rascunho seria impossível';
  end if;
  if has_table_privilege('service_role', 'app.benefit_entitlement', 'UPDATE') then
    raise exception 'service_role tem UPDATE em app.benefit_entitlement; linha de ciclo não se edita — ou o rascunho é refeito, ou o ciclo é outro';
  end if;

  -- 5. As policies, uma a uma. `with_check` conferido em separado porque é ele
  --    que decide o INSERT — olhar só o `using` deixa passar a metade que
  --    grava.
  select qual into v_qual from pg_policies
   where schemaname = 'app' and tablename = 'benefit_cycle' and policyname = 'benefit_cycle_read';
  if coalesce(v_qual, '') not like '%can_see_domain%'
     or coalesce(v_qual, '') not like '%compensation%' then
    raise exception 'benefit_cycle_read não exige o domínio compensation; com um grant a authenticated por engano, a competência vazaria para quem a rota nega';
  end if;
  select qual, with_check into v_qual, v_chk from pg_policies
   where schemaname = 'app' and tablename = 'benefit_cycle' and policyname = 'benefit_cycle_admin';
  if coalesce(v_qual, '') not like '%is_admin%' or coalesce(v_chk, '') not like '%is_admin%' then
    raise exception 'benefit_cycle_admin sem util.is_admin nas duas expressões';
  end if;

  select qual into v_qual from pg_policies
   where schemaname = 'app' and tablename = 'benefit_entitlement'
     and policyname = 'benefit_entitlement_read';
  if coalesce(v_qual, '') not like '%can_see_domain%'
     or coalesce(v_qual, '') not like '%can_see_employee%' then
    raise exception 'benefit_entitlement_read sem os dois eixos (domínio e colaborador)';
  end if;
  if coalesce(v_qual, '') like '%is_admin%' then
    raise exception 'benefit_entitlement_read ganhou util.is_admin; quem concilia a remessa sem ser admin deixaria de ler';
  end if;
  select qual, with_check into v_qual, v_chk from pg_policies
   where schemaname = 'app' and tablename = 'benefit_entitlement'
     and policyname = 'benefit_entitlement_write';
  if coalesce(v_qual, '') not like '%can_see_domain%'
     or coalesce(v_qual, '') not like '%can_see_employee%'
     or coalesce(v_qual, '') not like '%is_admin%' then
    raise exception 'benefit_entitlement_write sem os três eixos no using';
  end if;
  if coalesce(v_chk, '') not like '%can_see_domain%'
     or coalesce(v_chk, '') not like '%can_see_employee%'
     or coalesce(v_chk, '') not like '%is_admin%' then
    raise exception 'benefit_entitlement_write sem os três eixos no with check — é ele que decide o INSERT';
  end if;

  -- 6. O `unique` da competência, com o conjunto de colunas comparado INTEIRO e
  --    o `deferrable` conferido. `like` em `pg_get_constraintdef` casaria com um
  --    unique de colunas a mais; e um unique NÃO adiável tornaria impossível o
  --    fluxo que a SPEC desenha, porque a transição de status passaria pelo
  --    instante em que duas linhas têm o mesmo status.
  select (select array_agg(a.attname::text order by a.attname)
            from unnest(c.conkey) k
            join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k),
         c.condeferrable
    into v_columns, v_deferred
    from pg_constraint c
   where c.conrelid = 'app.benefit_cycle'::regclass
     and c.conname  = 'benefit_cycle_period_key';
  if v_columns is null then
    raise exception 'benefit_cycle_period_key não existe; duas apurações da mesma competência conviveriam e a remessa dependeria de qual foi lida';
  end if;
  if v_columns is distinct from array['kind','period_month','period_year','status','tenant_id'] then
    raise exception 'benefit_cycle_period_key cobre %, esperava (tenant_id, kind, period_year, period_month, status)', v_columns;
  end if;
  if not v_deferred then
    raise exception 'benefit_cycle_period_key não é deferrable; a SPEC §1e o declara adiável';
  end if;

  -- 7. Uma linha por pessoa por ciclo — o grão que a §1e declara em prosa.
  if not exists (
    select 1 from pg_constraint c
     where c.conrelid = 'app.benefit_entitlement'::regclass
       and c.contype  = 'u'
       and (select array_agg(a.attname::text order by a.attname)
              from unnest(c.conkey) k
              join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k)
           = array['cycle_id','employee_id']
  ) then
    raise exception 'app.benefit_entitlement sem unique (cycle_id, employee_id); refazer um rascunho duplicaria a pessoa e a remessa pagaria duas vezes';
  end if;

  -- 8. Os dois gatilhos, bit a bit. Cada bit falha calado por conta própria: um
  --    gatilho `after` deixaria a linha entrar, e um que só cobre `update`
  --    deixaria o `delete` apagar a competência inteira.
  for v_trigger in
    select x.rel, x.trg, x.fn, x.ins
      from (values
        ('benefit_cycle',       'trg_benefit_cycle_immutable',
         'enforce_benefit_cycle_immutable',       false),
        ('benefit_entitlement', 'trg_benefit_entitlement_immutable',
         'enforce_benefit_entitlement_immutable', true)
      ) as x(rel, trg, fn, ins)
  loop
    declare
      v_found record;
    begin
      select t.tgtype, t.tgenabled, p.proname
        into v_found
        from pg_trigger t
        join pg_proc p on p.oid = t.tgfoid
       where t.tgrelid = ('app.' || v_trigger.rel)::regclass
         and t.tgname  = v_trigger.trg
         and not t.tgisinternal;
      if not found then
        raise exception 'app.% não tem %; um ciclo gerado poderia ser reescrito, e o mês passado mudaria sem rastro',
          v_trigger.rel, v_trigger.trg;
      end if;
      if v_found.proname <> v_trigger.fn then
        raise exception '% aponta para %, não para util.%', v_trigger.trg, v_found.proname, v_trigger.fn;
      end if;
      -- tgtype: 1 = row, 2 = before, 4 = insert, 8 = delete, 16 = update.
      if (v_found.tgtype & 1) = 0 then
        raise exception '% não é FOR EACH ROW', v_trigger.trg;
      end if;
      if (v_found.tgtype & 2) = 0 then
        raise exception '% não é BEFORE — depois de a linha mudar já é tarde', v_trigger.trg;
      end if;
      if (v_found.tgtype & 8) = 0 or (v_found.tgtype & 16) = 0 then
        raise exception '% não cobre UPDATE e DELETE', v_trigger.trg;
      end if;
      if v_trigger.ins and (v_found.tgtype & 4) = 0 then
        raise exception '% não cobre INSERT; acrescentar pessoa a ciclo gerado é a mesma reescrita pela porta dos fundos', v_trigger.trg;
      end if;
      if v_found.tgenabled = 'D' then
        raise exception '% existe mas está desabilitado', v_trigger.trg;
      end if;
    end;
  end loop;

  -- 9. A PROVA VIVA. O estrutural acima diz que os gatilhos existem; esta diz
  --    que eles recusam — e que recusam o que deve ser recusado e SÓ isso.
  --
  --    ⛔ A FIXTURE É INTEIRAMENTE PRÓPRIA, e a lição é da `dp_benefit_catalog`:
  --    o banco de ensaio tem 1 tenant e ZERO empresas, e `app.employee.company_id`
  --    é NOT NULL. Reusar empresa existente fez duas sabotagens passarem verdes lá.
  --
  --    ⛔ E ELA SE DESFAZ POR SUBTRANSAÇÃO, NÃO POR `delete`
  --    Um ciclo congelado é justamente o que esta migration prova não poder ser
  --    apagado — então limpar a fixture com `delete` seria impossível, e
  --    desligar o gatilho para conseguir exigiria ser dono da tabela e provaria
  --    o contrário do que se quer. O bloco `begin ... exception` do PL/pgSQL é
  --    uma subtransação: levantar o sentinela no fim descarta tudo o que ele
  --    escreveu, e qualquer OUTRO erro é relevantado como veio.
  select t.id into v_tenant from app.tenant t order by t.created_at limit 1;
  if v_tenant is null then
    raise notice 'sem tenant: prova viva pulada (a estrutura já foi verificada acima)';
    return;
  end if;

  begin
    insert into app.company (tenant_id, legal_name, active)
    values (v_tenant, '__dp_bcy_prova__', false) returning id into v_company;
    insert into app.employee (tenant_id, company_id, name)
    values (v_tenant, v_company, '__dp_bcy_prova__') returning id into v_employee;

    insert into app.benefit_cycle
      (tenant_id, kind, period_year, period_month, window_start, window_end)
    values (v_tenant, 'transport_voucher', 2026, 9, date '2026-08-21', date '2026-09-20')
    returning id into v_cycle;

    -- a) rascunho é editável, senão não haveria preview. Sem esta, uma trava que
    --    recusasse TUDO passaria em todas as recusas abaixo — e a rotina mensal
    --    não teria como apurar duas vezes antes de fechar.
    insert into app.benefit_entitlement
      (tenant_id, cycle_id, employee_id, entitled, days_base, absences_prior,
       net_days, total_amount)
    values (v_tenant, v_cycle, v_employee, true, 22, 0, 22, 220)
    returning id into v_line;
    update app.benefit_cycle set business_days = 22 where id = v_cycle;
    delete from app.benefit_entitlement where id = v_line;
    insert into app.benefit_entitlement
      (tenant_id, cycle_id, employee_id, entitled, days_base, absences_prior,
       net_days, total_amount)
    values (v_tenant, v_cycle, v_employee, true, 22, 0, 22, 220)
    returning id into v_line;

    -- b) congelado, a janela não muda mais;
    update app.benefit_cycle set status = 'generated', generated_at = now() where id = v_cycle;
    v_barrou := false;
    begin
      update app.benefit_cycle set window_end = date '2026-09-30' where id = v_cycle;
    exception when check_violation then
      v_barrou := true;
    end;
    if not v_barrou then
      raise exception 'ciclo gerado aceitou update na janela — o mês passado mudaria sem rastro';
    end if;

    -- c) nem o dinheiro. É a metade que a trava do cabeçalho sozinha deixaria
    --    aberta, e é a que paga.
    v_barrou := false;
    begin
      delete from app.benefit_entitlement where id = v_line;
    exception when check_violation then
      v_barrou := true;
    end;
    if not v_barrou then
      raise exception 'linha de ciclo gerado foi apagada — congelar o cabeçalho e deixar as linhas abertas congela a janela e libera o dinheiro';
    end if;
    v_barrou := false;
    begin
      insert into app.benefit_entitlement (tenant_id, cycle_id, employee_id, entitled)
      values (v_tenant, v_cycle, v_employee, false);
    exception when check_violation then
      v_barrou := true;
    end;
    if not v_barrou then
      raise exception 'pessoa nova entrou em ciclo gerado — acrescentar é reescrever pela porta dos fundos';
    end if;

    -- d) e o ciclo não se apaga.
    v_barrou := false;
    begin
      delete from app.benefit_cycle where id = v_cycle;
    exception when check_violation then
      v_barrou := true;
    end;
    if not v_barrou then
      raise exception 'ciclo gerado foi apagado — competência sai por cancelled, nunca por delete';
    end if;

    -- e) ⛔ MAS O STATUS AVANÇA. Sem esta, `exported` e `cancelled` seriam
    --    inalcançáveis, e "correção é ciclo novo" ficaria sem a metade que
    --    aposenta o errado. Uma trava que barra o legítimo é pior que a ausência
    --    dela — a lição das oito sabotagens da `dp_benefit_catalog`.
    begin
      update app.benefit_cycle set status = 'exported' where id = v_cycle;
      update app.benefit_cycle set status = 'cancelled' where id = v_cycle;
    exception when check_violation then
      raise exception 'a trava barrou o avanço de status; cancelar seria impossível e a correção por ciclo novo não teria como aposentar o errado';
    end;

    -- f) e não volta atrás.
    v_barrou := false;
    begin
      update app.benefit_cycle set status = 'draft' where id = v_cycle;
    exception when check_violation then
      v_barrou := true;
    end;
    if not v_barrou then
      raise exception 'ciclo cancelado voltou a rascunho — o que já foi pago viraria editável de novo';
    end if;

    -- O sentinela. Tudo acima volta atrás com ele.
    raise exception using errcode = 'OX000', message = 'prova viva concluida';
  exception when others then
    if sqlstate <> 'OX000' then
      raise;
    end if;
  end;

  raise notice
    'OK: competência e linha por pessoa fora do PostgREST, com dois eixos para ler e três para escrever; ciclo gerado recusa update, delete e linha nova, o status ainda avança, e a prova não deixou rastro.';
end $$;
