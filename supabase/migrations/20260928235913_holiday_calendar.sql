-- ============================================================================
-- OperaX — holiday_calendar. O CALENDÁRIO QUE O ESPELHO NÃO TRAZ
-- ----------------------------------------------------------------------------
-- Desenho: `docs/SPRINTS-ALCADA.md` P0.3, com as decisões do dono de 28/09/2026.
--
-- ⛔ ORDEM DE DEPLOY — APLICAR ESTA MIGRATION ANTES DO PUSH
-- O Railway faz deploy a cada push e nenhum deploy aplica migration (CLAUDE.md,
-- Deploy). O código que acompanha esta migration lê `app.holiday` na jornada:
-- com o push antes dela, os dois crons do motor morrem em
-- `relation "app.holiday" does not exist`. A ordem é:
--   1. aplicar esta migration;
--   2. push;
--   3. `python -m operax.motor.feriados carga --ano 2026 --ano 2027`;
--   4. o `operax-motor-retro` da manhã seguinte reprocessa o 07/09/2026 sozinho
--      (a carga grava `updated_at` agora, e o passo automático refaz o feriado
--      escrito nos últimos dois dias). Isto é escrita em produção: Regra 0.
--
-- ⛔ O PROBLEMA, MEDIDO EM PRODUÇÃO (agregado, 28/09/2026)
-- O motor não conhecia feriado: `jornada.py` materializava o dia como `work`.
-- Em 07/09/2026 (Independência, segunda) houve 64 `no_punches` ativos contra
-- 8–10 nas segundas vizinhas. Quem é de escala semanal do Secullum folgou (1 de
-- 63 bateu) e quem é de revezamento trabalhou (5 de 8) — em TODAS as unidades.
--
-- POR ISSO O SINAL É O TIPO DE ESCALA, E NÃO A UNIDADE
-- Não existe tabela de "unidade opera no feriado". O feriado vira
-- `expected_workday.day_type = 'holiday'` só para jornada de semana fixa do
-- Secullum; revezamento (rotação curada ou inferida) segue a escala. A regra
-- vive em `backend/operax/motor/jornada.py`, e esta migration só dá a ela o
-- calendário e o tipo de indício.
--
-- A TABELA
-- Nacional = `unit_id` nulo. Estadual e municipal = uma linha por unidade
-- atingida: a unidade não carrega cidade, UF nem IBGE em lugar nenhum, e duas
-- unidades em cidades diferentes têm feriados municipais diferentes.
--
-- ⛔ SEM DELETE. Feriado errado sai com `active = false`: ele explica revogações
-- de indício, e a linha que some não explica nada. Sem policy de delete e sem
-- grant de delete a `authenticated` nem a `service_role`. ⚠️ O backend conecta
-- como `postgres`, dono da tabela, que ignora grant e RLS: para ele, "sem
-- delete" é garantido só pela ausência de rota que apague, não pelo banco.
--
-- A FRONTEIRA (policy aprovada pelo dono em 28/09/2026 — parada cumprida)
--   * leitura: quem enxerga o tenant e, na linha de unidade, a unidade;
--   * escrita: só `owner` — `'owner' = any(util.roles_in_tenant(tenant_id))`.
--     NÃO `util.is_admin`, que inclui `hr` e `personnel`: calendário muda quem
--     deve jornada no dia, e com isso quem tem falta e quem recebe VT. Duas
--     policies, uma por verbo (insert e update), e NENHUMA de delete nem
--     `for all` (decisão do dono, 28/09/2026);
--   * fora do PostgREST (sem grant a `authenticated`), escrita pelo backend, que
--     pergunta ao banco como o usuário antes de gravar junto da auditoria.
--
-- O TIPO NOVO, `punch_on_holiday`
-- Batida de quem é de semana fixa num feriado. Não é extensão de
-- `punch_on_day_off`: o rótulo diria "dia sem jornada prevista" para um feriado,
-- e o cliente pode querer contar os dois de forma diferente. A linha de
-- `deviation_type_config` vai para TODOS os tenants: as RPCs de KPI fazem inner
-- join nela, e sem a linha o tipo some dos números.
--
-- Unidade de outro tenant: não há FK composta `(tenant_id, unit_id)` no repo.
-- O backend confere a unidade contra o tenant antes de gravar, e o motor filtra
-- `holiday.tenant_id` — uma linha com unidade alheia não casa com ninguém.
--
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

create table if not exists app.holiday (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references app.tenant(id) on delete cascade,
  reference_date date not null,
  jurisdiction   text not null check (jurisdiction in ('national','state','municipal')),
  --: Nulo = toda unidade do tenant. Estadual e municipal apontam a unidade.
  unit_id        uuid references app.unit(id),
  name           text not null check (length(btrim(name)) > 0),
  --: Feriado errado sai com active = false, nunca com delete.
  active         boolean not null default true,
  created_by     uuid references auth.users(id),
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint holiday_jurisdiction_unit_check
    check ((jurisdiction = 'national') = (unit_id is null))
);

-- Um por (tenant, dia) no nacional; um por (tenant, dia, unidade) no resto.
-- Sem `active` no predicado: desativar não abre vaga para a carga recriar.
create unique index if not exists holiday_national_uq
  on app.holiday (tenant_id, reference_date) where unit_id is null;
create unique index if not exists holiday_unit_uq
  on app.holiday (tenant_id, reference_date, unit_id) where unit_id is not null;

comment on table app.holiday is
  'Calendário de feriados por tenant. Nacional = unit_id nulo; estadual e municipal = uma '
  'linha por unidade atingida. Lido por jornada.py: vira expected_workday.day_type = '
  '''holiday'' só para jornada de semana fixa do Secullum (afastamento > feriado > escala); '
  'revezamento segue a escala. Sem delete: desativar com active = false.';
comment on column app.holiday.active is
  'false = cadastrado por engano. A linha fica: ela explica as revogações de indício que causou.';

drop trigger if exists holiday_touch on app.holiday;
create trigger holiday_touch before update on app.holiday
  for each row execute function util.touch_updated_at();

-- ---------------------------------------------------------------------------
-- Fronteira — Caminho 2
-- ---------------------------------------------------------------------------
alter table app.holiday enable row level security;

revoke all on table app.holiday from anon, authenticated;
grant select, insert, update on table app.holiday to service_role;

drop policy if exists holiday_read on app.holiday;
create policy holiday_read on app.holiday
  for select to authenticated
  using (util.has_tenant(tenant_id)
         and (unit_id is null or util.can_see_unit(unit_id)));

-- Uma policy por verbo, e nenhuma para delete: `for all` cobriria o delete na
-- policy, e só o grant ausente o barraria.
drop policy if exists holiday_owner on app.holiday;

drop policy if exists holiday_owner_insert on app.holiday;
create policy holiday_owner_insert on app.holiday
  for insert to authenticated
  with check ('owner' = any (util.roles_in_tenant(tenant_id)));

drop policy if exists holiday_owner_update on app.holiday;
create policy holiday_owner_update on app.holiday
  for update to authenticated
  using ('owner' = any (util.roles_in_tenant(tenant_id)))
  with check ('owner' = any (util.roles_in_tenant(tenant_id)));

-- ---------------------------------------------------------------------------
-- O tipo de indício
-- ---------------------------------------------------------------------------
insert into app.deviation_type (code, description, direction, category) values
  ('punch_on_holiday', 'Batida em feriado', 'surplus', 'roster')
on conflict (code) do nothing;

-- Todos os tenants, sem amarrar slug: a 05 amarrou 'kastro-park', e o slug mudou.
insert into app.deviation_type_config (tenant_id, code, active, counts_as_deviation, triggers_alert)
select t.id, 'punch_on_holiday', true, true, false
from app.tenant t
on conflict (tenant_id, code) do nothing;

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v           int;
  v_privilege text;
  v_qual      text;
  v_chk       text;
begin
  -- 1. Regra 3 do CLAUDE.md.
  if not (select relrowsecurity from pg_class where oid = 'app.holiday'::regclass) then
    raise exception 'app.holiday sem RLS — regra 3 do CLAUDE.md';
  end if;
  select count(*) into v from information_schema.columns
   where table_schema = 'app' and table_name = 'holiday'
     and column_name = 'tenant_id' and is_nullable = 'NO';
  if v <> 1 then
    raise exception 'app.holiday sem tenant_id not null — regra 3 do CLAUDE.md';
  end if;

  -- 2. Fora do PostgREST em TODOS os verbos, e o backend alcança sem apagar.
  foreach v_privilege in array array['SELECT','INSERT','UPDATE','DELETE'] loop
    if has_table_privilege('authenticated', 'app.holiday', v_privilege) then
      raise exception 'authenticated tem % em app.holiday — a escrita é do backend', v_privilege;
    end if;
    if has_table_privilege('anon', 'app.holiday', v_privilege) then
      raise exception 'anon tem % em app.holiday', v_privilege;
    end if;
  end loop;
  foreach v_privilege in array array['SELECT','INSERT','UPDATE'] loop
    if not has_table_privilege('service_role', 'app.holiday', v_privilege) then
      raise exception 'service_role sem % em app.holiday — o motor não leria o calendário', v_privilege;
    end if;
  end loop;
  if has_table_privilege('service_role', 'app.holiday', 'DELETE') then
    raise exception 'service_role com DELETE em app.holiday; feriado sai com active = false';
  end if;

  -- 3. As três policies, e só elas: leitura, insert e update. Nenhuma de
  --    delete e nenhuma `for all` (que cobriria o delete).
  select count(*) into v from pg_policies where schemaname = 'app' and tablename = 'holiday';
  if v <> 3 then
    raise exception 'app.holiday tem % policies, esperava 3 (holiday_read, holiday_owner_insert, holiday_owner_update)', v;
  end if;
  if exists (select 1 from pg_policies
              where schemaname = 'app' and tablename = 'holiday'
                and cmd in ('DELETE', 'ALL')) then
    raise exception 'app.holiday tem policy de DELETE ou FOR ALL — feriado não se apaga, desativa-se';
  end if;
  select count(*) into v from pg_policies
   where schemaname = 'app' and tablename = 'holiday'
     and (policyname, cmd) in (('holiday_read', 'SELECT'),
                               ('holiday_owner_insert', 'INSERT'),
                               ('holiday_owner_update', 'UPDATE'));
  if v <> 3 then
    raise exception 'as policies de app.holiday não são leitura/insert/update com os nomes esperados';
  end if;

  select qual into v_qual from pg_policies
   where schemaname = 'app' and tablename = 'holiday' and policyname = 'holiday_read';
  if coalesce(v_qual, '') not like '%has_tenant%' or v_qual not like '%can_see_unit%' then
    raise exception 'holiday_read sem has_tenant + can_see_unit: %', v_qual;
  end if;

  -- ⛔ A escrita é só do owner. `is_admin` inclui hr e personnel, e é o padrão
  --    das outras curadorias: esta asserção é o que impede a volta silenciosa a
  --    ele, no using E no with check (é o with check que decide o INSERT).
  select with_check into v_chk from pg_policies
   where schemaname = 'app' and tablename = 'holiday' and policyname = 'holiday_owner_insert';
  if coalesce(v_chk, '') not like '%roles_in_tenant%' or v_chk not like '%owner%' then
    raise exception 'holiday_owner_insert sem ''owner'' = any(util.roles_in_tenant(...)) no with check';
  end if;
  select qual, with_check into v_qual, v_chk from pg_policies
   where schemaname = 'app' and tablename = 'holiday' and policyname = 'holiday_owner_update';
  if coalesce(v_qual, '') not like '%roles_in_tenant%' or v_qual not like '%owner%'
     or coalesce(v_chk, '') not like '%roles_in_tenant%' or v_chk not like '%owner%' then
    raise exception 'holiday_owner_update sem ''owner'' = any(util.roles_in_tenant(...)) no using e no with check';
  end if;
  if exists (select 1 from pg_policies
              where schemaname = 'app' and tablename = 'holiday'
                and (coalesce(qual, '') like '%is_admin%'
                     or coalesce(with_check, '') like '%is_admin%')) then
    raise exception 'uma policy de app.holiday aceita util.is_admin';
  end if;

  -- 4. A forma dos dados.
  if not exists (select 1 from pg_constraint
                  where conrelid = 'app.holiday'::regclass
                    and conname = 'holiday_jurisdiction_unit_check') then
    raise exception 'sem o check nacional <=> unit_id nulo: municipal sem unidade viraria nacional';
  end if;
  select count(*) into v from pg_indexes
   where schemaname = 'app' and tablename = 'holiday'
     and indexname in ('holiday_national_uq','holiday_unit_uq');
  if v <> 2 then
    raise exception 'app.holiday sem os dois uniques — a carga nacional duplicaria';
  end if;

  -- 5. O motor escreve 'holiday' em expected_workday: se o check deixar de
  --    aceitar, a jornada inteira do tenant falha no feriado.
  if not exists (select 1 from pg_constraint
                  where conrelid = 'app.expected_workday'::regclass and contype = 'c'
                    and pg_get_constraintdef(oid) like '%''holiday''%') then
    raise exception 'expected_workday.day_type não aceita holiday';
  end if;

  -- 6. O tipo existe, e nenhum tenant ficou sem a linha de política — sem ela o
  --    tipo some dos KPIs (as RPCs fazem inner join em deviation_type_config).
  if not exists (select 1 from app.deviation_type where code = 'punch_on_holiday') then
    raise exception 'punch_on_holiday não está em app.deviation_type';
  end if;
  select count(*) into v from app.tenant t
   where not exists (select 1 from app.deviation_type_config c
                      where c.tenant_id = t.id and c.code = 'punch_on_holiday');
  if v <> 0 then
    raise exception '% tenant(s) sem deviation_type_config para punch_on_holiday', v;
  end if;

  raise notice 'OK: app.holiday fora do PostgREST, insert e update só por owner, sem policy nem grant de delete; punch_on_holiday em todos os tenants.';
end $$;
