-- ============================================================================
-- OperaX — dp_benefit_catalog. A REGRA 8 DO PRD VIRANDO COLUNA
-- ----------------------------------------------------------------------------
-- Desenho em `docs/SPEC-DP.md` §1d e §1d-bis. Quatro tabelas: o catálogo de
-- verbas do tenant (`benefit_type`), os dois cadastros com preço e vigência
-- (`benefit_plan`, `transport_fare`) e o vínculo pessoa <-> verba
-- (`employee_benefit`).
--
-- ⛔ `composes_base` É A DEFINIÇÃO DO KPI, E É POR ISSO QUE ELA É COLUNA
-- A folha base deixa de ser constante no backend: ela é
-- `salary + sum(amount) where composes_base`. Um tipo novo de verba passa a ser
-- uma linha de dado, não um deploy — e, mais importante, quem decide se a verba
-- compõe é o cliente na tela, não uma lista escrita em Python que ninguém acha
-- quando o número diverge.
--
-- ⛔ OITO TIPOS NA SEMENTE, E O NONO É NOMEADO
-- `seniority_bonus` (triênio) FICA DE FORA. Decisão do dono em 04/09/2026,
-- reconfirmada em 05/09. O motivo não é preferência: a medição da §1d-bis não
-- teve resposta empírica — `app.payroll_entry` tem zero linhas em produção —, e
-- semear um triênio que talvez já esteja embutido no salário base do legado
-- CONTA DUAS VEZES e corrompe o KPI sem nenhum sintoma. A garantia no fim deste
-- arquivo falha alto se ele aparecer.
--
-- ⚠️ O MECANISMO DO TRIÊNIO PERMANECE — saiu o tipo, não as colunas
-- `benefit_type.calculation` (`fixed_amount` | `salary_rate`) e
-- `employee_benefit.rate` / `quantity` existem desde já. Triênio é TAXA, não
-- montante: na ficha é uma contagem, e o valor deriva de contagem x percentual x
-- salário vigente. Guardado como `amount` fixo ele congela — a pessoa recebe
-- aumento e a verba fica velha em silêncio. Tirar as colunas obrigaria migration
-- nova no dia em que o triênio voltar, e mantê-las foi decisão explícita (05/09).
--
-- ⛔ `trust_position` E `hazard_pay` SÃO SEPARADOS
-- O legado os mostra num card só. A soma é idêntica, e a distinção se perde para
-- sempre se nascer fundida. Consequência para a reconciliação: comparar
-- `trust_position + hazard_pay` contra o card único do legado — diferença ali é
-- de forma, não de valor.
--
-- ⛔ SEM GRANT PARA `authenticated` — a etapa DP inteira é Caminho 2
-- Mesmo desenho de `app.employee_photo` (36) e de `app.employee_bank_account`.
--
-- OS EIXOS, E ELES DIFEREM ENTRE AS QUATRO TABELAS
-- `benefit_type`, `benefit_plan` e `transport_fare` são CATÁLOGO DO TENANT: não
-- há pessoa neles, então não há `can_see_employee` a pedir. Leem quem é do
-- tenant (`util.has_tenant`), escreve quem administra (`util.is_admin`) — o par
-- de `app.contact`.
-- `employee_benefit` guarda valor POR COLABORADOR e é do domínio `compensation`:
-- leitura com os dois eixos (`can_see_domain` + `can_see_employee`) e escrita com
-- os TRÊS (mais `util.is_admin`), que é o padrão real deste repositório —
-- `pii_write`, `remuneracao_write`, acordos (08) e `employee_photo_write` (36)
-- todas o carregam. Dois eixos é o padrão de LEITURA; escrita sempre teve três.
--
-- Depende de `dp_work_post` só pela ordem do diretório, não por objeto.
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. O catálogo de verbas
-- ---------------------------------------------------------------------------
create table if not exists app.benefit_type (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references app.tenant(id) on delete cascade,
  --: cost_allowance, meal_voucher, trust_position…
  code          text not null,
  --: Rótulo pt-BR da UI. O código é do sistema; este é o que o gestor lê.
  name          text not null,
  --: Entra na "folha salarial base"? Sem default DE PROPÓSITO: um tipo novo
  --: obriga quem o cria a responder, e o silêncio não vira `false` calado.
  composes_base boolean not null,
  --: `salary_rate` é o mecanismo do triênio: o valor deriva do salário vigente
  --: em vez de ser digitado. Nenhum dos oito semeados o usa hoje.
  calculation   text not null default 'fixed_amount'
    check (calculation in ('fixed_amount','salary_rate')),
  domain        app.sensitive_domain not null default 'compensation',
  active        boolean not null default true,
  unique (tenant_id, code)
);

comment on table app.benefit_type is
  'Catálogo de verbas do tenant. `composes_base` é a regra 8 do PRD-DP virando dado: '
  'a folha base é salary + sum(amount) where composes_base, nunca uma lista no backend.';
comment on column app.benefit_type.composes_base is
  'Entra na folha salarial base. Definição do KPI: mudar esta coluna muda o número da tela.';
comment on column app.benefit_type.calculation is
  'fixed_amount = valor digitado; salary_rate = derivado do salário vigente (mecanismo do triênio).';

-- ---------------------------------------------------------------------------
-- 2. Plano (operadora e preço) e tarifa de transporte — os dois com vigência
-- ---------------------------------------------------------------------------
-- Padrão de `app.employee_compensation`: `effective_from` / `effective_to`, e
-- NUNCA `update` no valor. Um reajuste é uma linha nova; a tela "Reajuste" do
-- legado — "nova vigência (desde, valor, motivo)" — é exatamente isto.
--
-- `code` é a identidade do plano ATRAVÉS das vigências, do mesmo jeito que
-- `employee_id` é a identidade da faixa salarial. Sem ele não há como saber qual
-- faixa fechar ao reajustar, e o reajuste viraria adivinhação por nome.
create table if not exists app.benefit_plan (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references app.tenant(id) on delete cascade,
  benefit_type_id uuid not null references app.benefit_type(id),
  code            text not null,
  --: Operadora. "Unimed", "Odontoprev".
  provider        text not null,
  name            text not null,
  amount          numeric(12,2) not null check (amount >= 0),
  effective_from  date not null,
  effective_to    date,
  reason          text,
  created_at      timestamptz not null default now(),
  check (effective_to is null or effective_to >= effective_from)
);

-- A tradução estrutural de "reajuste cria vigência nova": um plano tem no máximo
-- UMA faixa aberta. Sem este índice, um reajuste que esquecesse de fechar a
-- anterior deixaria duas vigentes e o preço do mês passaria a depender da ordem
-- da leitura — divergência sem sintoma, que é o pior tipo.
create unique index if not exists benefit_plan_open_band_idx
  on app.benefit_plan (tenant_id, code) where effective_to is null;

comment on table app.benefit_plan is
  'Plano de benefício (operadora e preço) com vigência. Reajuste = linha nova; '
  'o valor de uma vigência já publicada nunca é editado.';

create table if not exists app.transport_fare (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references app.tenant(id) on delete cascade,
  code           text not null,
  --: "Linha 302 — Centro". Rótulo do cliente.
  name           text not null,
  --: Tipo da tarifa. `round_trip` não é sempre 2x `single`: integração e
  --: desconto de linha quebram a conta, e é por isso que os dois são dado.
  kind           text not null check (kind in ('single','round_trip')),
  amount         numeric(12,2) not null check (amount >= 0),
  effective_from date not null,
  effective_to   date,
  reason         text,
  created_at     timestamptz not null default now(),
  check (effective_to is null or effective_to >= effective_from)
);

create unique index if not exists transport_fare_open_band_idx
  on app.transport_fare (tenant_id, code, kind) where effective_to is null;

comment on table app.transport_fare is
  'Tarifa de transporte por linha e tipo (unitária ou ida-e-volta), com vigência. '
  'Reajuste = linha nova; a anterior fecha a faixa e mantém o valor que valeu.';

-- ---------------------------------------------------------------------------
-- 3. O vínculo pessoa <-> verba
-- ---------------------------------------------------------------------------
-- ⛔ TABELA ESTREITA, E NÃO COLUNAS EM `app.employee_compensation`
-- A linha larga forçaria uma vigência nova do pacote INTEIRO para mudar só o VR
-- — e `employee_compensation` já está aplicada, e migration aplicada não se
-- edita. Com esta, um tipo novo de verba não exige migration nenhuma.
create table if not exists app.employee_benefit (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references app.tenant(id) on delete cascade,
  employee_id       uuid not null references app.employee(id) on delete cascade,
  benefit_type_id   uuid not null references app.benefit_type(id),
  effective_from    date not null,
  effective_to      date,
  --: Montante, quando `calculation = 'fixed_amount'`. Anulável porque a verba
  --: por taxa não tem montante próprio: ele deriva na leitura.
  amount            numeric(12,2),
  --: Percentual por unidade, quando `calculation = 'salary_rate'`.
  rate              numeric(6,4),
  --: Contagem (triênios, por exemplo). O valor é quantity x rate x salário.
  quantity          smallint,
  benefit_plan_id   uuid references app.benefit_plan(id),
  transport_fare_id uuid references app.transport_fare(id),
  reason            text,
  recorded_by       uuid,
  created_at        timestamptz not null default now()
);

create index if not exists employee_benefit_colab_idx
  on app.employee_benefit (tenant_id, employee_id, effective_from desc);

comment on table app.employee_benefit is
  'Verba do colaborador com vigência. Domínio compensation: leitura com dois eixos, '
  'escrita com três. A folha base soma daqui filtrando por benefit_type.composes_base.';
comment on column app.employee_benefit.rate is
  'Percentual por unidade (mecanismo do triênio). Com quantity, o valor deriva do salário vigente e acompanha o aumento.';

-- ---------------------------------------------------------------------------
-- Fronteira
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['benefit_type','benefit_plan','transport_fare','employee_benefit'] loop
    execute format('alter table app.%I enable row level security', t);
    execute format('revoke all on table app.%I from anon, authenticated', t);
    -- `select, insert, update` e não `grant all`: verba não se apaga, fecha
    -- vigência — o ciclo de VT do mês passado aponta para ela. `update` é o que
    -- fecha a faixa, e é a única escrita destrutiva que esta etapa concede.
    execute format('grant select, insert, update on table app.%I to service_role', t);
  end loop;
end $$;

-- Catálogo do tenant: quem alcança o domínio de remuneração lê, quem administra
-- escreve. Não há pessoa nestas três, então não há `can_see_employee` a pedir —
-- exigi-lo aqui seria cerimônia, e cerimônia se satisfaz com tautologia.
--
-- ⛔ `can_see_domain` E NÃO `has_tenant`, E A DIFERENÇA SÓ APARECE NO DIA DO ERRO
-- A primeira versão destas três dizia `util.has_tenant(tenant_id)` — sem domínio
-- —, enquanto `GET /dp/beneficios/catalogo` exige `compensation`. A policy dizia
-- SIM para o `hr`, que a rota nega, e as duas descreviam clientes diferentes.
--
-- Isso não muda comportamento nenhum hoje: não há grant para `authenticated`, e
-- o Caminho 2 conecta como papel `rolbypassrls`. Muda o que acontece no dia em
-- que um PR conceder `select` por engano — que é a única razão pela qual o
-- cabeçalho deste arquivo diz que as policies existem. Com `has_tenant`, aquele
-- dia entregava preço de plano a um supervisor sem `compensation`, e a frase do
-- cabeçalho seria falsa justamente quando precisasse ser verdadeira.
--
-- A escrita (`*_admin`, `util.is_admin`) fica como está: administrar o catálogo
-- é ato de administração, e `is_admin` já é mais estreito que o domínio.
drop policy if exists benefit_type_read on app.benefit_type;
create policy benefit_type_read on app.benefit_type
  for select to authenticated using (util.can_see_domain(tenant_id, 'compensation'));

drop policy if exists benefit_type_admin on app.benefit_type;
create policy benefit_type_admin on app.benefit_type
  for all to authenticated
  using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

drop policy if exists benefit_plan_read on app.benefit_plan;
create policy benefit_plan_read on app.benefit_plan
  for select to authenticated using (util.can_see_domain(tenant_id, 'compensation'));

drop policy if exists benefit_plan_admin on app.benefit_plan;
create policy benefit_plan_admin on app.benefit_plan
  for all to authenticated
  using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

drop policy if exists transport_fare_read on app.transport_fare;
create policy transport_fare_read on app.transport_fare
  for select to authenticated using (util.can_see_domain(tenant_id, 'compensation'));

drop policy if exists transport_fare_admin on app.transport_fare;
create policy transport_fare_admin on app.transport_fare
  for all to authenticated
  using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

-- Valor por pessoa, domínio `compensation`. Dois eixos para ler.
drop policy if exists employee_benefit_read on app.employee_benefit;
create policy employee_benefit_read on app.employee_benefit
  for select to authenticated
  using (
    util.can_see_domain(tenant_id, 'compensation')
    and util.can_see_employee(employee_id)
  );

-- ⛔ TRÊS PARA ESCREVER. O terceiro eixo é o que separa quem confere de quem
--    altera: `accounting` concilia a folha e não redigita verba de ninguém, e a
--    matriz de domínios muda por UPDATE sem deploy — conceder `compensation` a
--    um `unit_supervisor` é uma linha de dado, e sem `is_admin` passaria a dar a
--    ele escrita da verba de quem ele supervisiona.
drop policy if exists employee_benefit_write on app.employee_benefit;
create policy employee_benefit_write on app.employee_benefit
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
-- 4. Uma faixa aberta por (colaborador, verba) — só nas que compõem a base
-- ---------------------------------------------------------------------------
-- ⛔ POR QUE GATILHO, E NÃO ÍNDICE PARCIAL COMO EM `benefit_plan`
-- Medido em 06/09/2026, não deduzido — as três formas de índice foram tentadas:
--
--   · predicado citando a outra tabela  -> `missing FROM-clause entry for
--     table "bt"`. O predicado só enxerga colunas da tabela indexada, e
--     `composes_base` mora em `app.benefit_type`.
--   · predicado com subconsulta         -> `cannot use subquery in index
--     predicate`. Recusa explícita do Postgres.
--   · predicado chamando função de lookup declarada `immutable` -> O ÍNDICE É
--     CRIADO, e é a armadilha: ele parece funcionar e está errado. Medido, com
--     `composes_base` virando `true` depois: TRÊS faixas abertas do mesmo par
--     sobreviveram. O índice não reavalia o predicado de linha que já entrou, e
--     a mentira sobre imutabilidade cobra na hora em que o cliente usa a tela.
--
-- Então o instrumento é gatilho. Ele é mais caro e tem ordem de disparo, e a
-- troca está declarada aqui em vez de descoberta depois.
--
-- ⛔ RESTRITO AOS TIPOS QUE COMPÕEM A BASE — decisão do dono, 06/09/2026
-- Duas linhas de VT abertas são LEGÍTIMAS (duas linhas de ônibus), e uma trava
-- que barra o legítimo é pior que a ausência dela. O que não pode repetir é o
-- que entra na soma: `compute_base_payroll` soma TODAS as verbas vigentes, então
-- duas ajudas de custo abertas contariam duas vezes, caladas — a mesma classe
-- que este arquivo chama de "o pior tipo" ao justificar os índices de plano.
--
-- ⚠️ GATILHO NÃO É ÍNDICE ÚNICO: ELE NÃO SERIALIZA SOZINHO
-- Duas transações concorrentes fariam o `exists` cada uma antes de a outra
-- confirmar, e as duas passariam — exatamente o furo que o índice de
-- `benefit_plan` não tem. O `pg_advisory_xact_lock` abaixo é o que devolve essa
-- propriedade: o par (colaborador, verba) serializa, e sob READ COMMITTED o
-- `exists` seguinte já enxerga a linha que a outra transação confirmou.
create or replace function util.enforce_single_open_base_benefit()
returns trigger
language plpgsql security definer set search_path = ''
as $trg$
declare v_composes boolean;
begin
  -- Faixa fechada não disputa nada: o que a trava protege é o que vale hoje.
  if new.effective_to is not null then
    return new;
  end if;

  select bt.composes_base into v_composes
    from app.benefit_type bt
   where bt.id = new.benefit_type_id;

  -- `coalesce` porque a FK garante que o tipo existe, mas não que a leitura
  -- devolva verdadeiro: tipo que não compõe passa direto, de propósito.
  if not coalesce(v_composes, false) then
    return new;
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      new.tenant_id::text || '/' || new.employee_id::text || '/' || new.benefit_type_id::text,
      0));

  -- `eb.id <> new.id` cobre o UPDATE, em que a própria linha já está na tabela;
  -- no INSERT ela ainda não está, e a condição é inócua.
  if exists (
    select 1 from app.employee_benefit eb
     where eb.tenant_id       = new.tenant_id
       and eb.employee_id     = new.employee_id
       and eb.benefit_type_id = new.benefit_type_id
       and eb.effective_to is null
       and eb.id <> new.id
  ) then
    -- `unique_violation` e não `raise_exception`: é a mesma regra que o índice
    -- de `benefit_plan` aplica, e quem escrever o caminho de gravação trata as
    -- duas do mesmo jeito, sem descobrir que há dois códigos para um choque só.
    raise exception using
      errcode = 'unique_violation',
      message = 'Já existe vigência aberta desta verba para este colaborador.',
      hint    = 'Verba que compõe a folha base tem no máximo uma faixa aberta: feche a atual antes de abrir a próxima. Verba que não compõe (vale transporte, por exemplo) pode repetir.';
  end if;
  return new;
end $trg$;

comment on function util.enforce_single_open_base_benefit() is
  'Uma faixa aberta por (colaborador, verba) nos tipos com composes_base. Índice '
  'parcial não serve: o predicado não alcança app.benefit_type (medido em 06/09/2026).';

drop trigger if exists trg_single_open_base_benefit on app.employee_benefit;
create trigger trg_single_open_base_benefit
  before insert or update on app.employee_benefit
  for each row execute function util.enforce_single_open_base_benefit();

-- ---------------------------------------------------------------------------
-- A semente — OITO tipos, transcritos da SPEC §1d
-- ---------------------------------------------------------------------------
-- `do nothing` e não `do update`: o cliente edita o catálogo pela tela, e uma
-- migration idempotente que sobrescreve a decisão dele a cada `db reset` não é
-- idempotente — é regressiva. Mesmo raciocínio da semente de `dp_banking_account`.
insert into app.benefit_type (tenant_id, code, name, composes_base)
select t.id, s.code, s.name, s.composes_base
from app.tenant t
cross join (values
  ('cost_allowance',    'Ajuda de custo',      true),
  ('trust_position',    'Cargo de confiança',  true),
  ('hazard_pay',        'Periculosidade',      true),
  ('meal_voucher',      'Vale refeição',       false),
  ('food_basket',       'Cesta básica',        false),
  ('transport_voucher', 'Vale transporte',     false),
  ('health_plan',       'Plano de saúde',      false),
  ('dental_plan',       'Plano odontológico',  false)
) as s(code, name, composes_base)
on conflict (tenant_id, code) do nothing;

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v_table     text;
  v_privilege text;
  v_tenants   int;
  v_seeded    int;
  v_compoem   int;
  v_qual      text;
  v_chk       text;
  v_policies  int;
  --: Os oito códigos da semente, num lugar só. As asserções abaixo falam DELES,
  --: não do catálogo inteiro — ver o passo 8.
  v_semente   constant text[] := array[
                'cost_allowance','trust_position','hazard_pay','meal_voucher',
                'food_basket','transport_voucher','health_plan','dental_plan'];
  v_trigger   record;
  v_tenant    uuid;
  v_company   uuid;
  v_employee  uuid;
  v_compoe    uuid;
  v_nao       uuid;
  v_barrou    boolean := false;
  v_index     text;
  v_relation  text;
  v_expected  text[];
  v_unique    boolean;
  v_predicate text;
  v_columns   text[];
begin
  foreach v_table in array array['benefit_type','benefit_plan','transport_fare','employee_benefit'] loop
    if to_regclass('app.' || v_table) is null then
      raise exception 'app.% não existe depois de ser criada', v_table;
    end if;

    -- 1. Regra 3 do CLAUDE.md: tenant_id e RLS, nas quatro.
    if not exists (
      select 1 from information_schema.columns
       where table_schema = 'app' and table_name = v_table and column_name = 'tenant_id'
    ) then
      raise exception 'app.% sem tenant_id — regra 3 do CLAUDE.md', v_table;
    end if;
    if not (select relrowsecurity from pg_class where oid = ('app.' || v_table)::regclass) then
      raise exception 'app.% sem RLS — regra 3 do CLAUDE.md', v_table;
    end if;

    -- 2. Fora do PostgREST, em todos os verbos. Perguntar só por `select`
    --    deixaria um `grant insert` passar, e inventar verba alheia é pior que
    --    lê-la: ela entra no KPI que o cliente usa para reconhecer o custo dele.
    foreach v_privilege in array array['SELECT','INSERT','UPDATE','DELETE'] loop
      if has_table_privilege('authenticated', 'app.' || v_table, v_privilege) then
        raise exception 'authenticated tem % em app.% — a etapa DP é só Caminho 2', v_privilege, v_table;
      end if;
      if has_table_privilege('anon', 'app.' || v_table, v_privilege) then
        raise exception 'anon tem % em app.%', v_privilege, v_table;
      end if;
    end loop;

    -- 3. O positivo. Sem ele o item 2 fica verde em quatro tabelas que ninguém
    --    alcança, e o Caminho 2 não existiria.
    foreach v_privilege in array array['SELECT','INSERT','UPDATE'] loop
      if not has_table_privilege('service_role', 'app.' || v_table, v_privilege) then
        raise exception 'service_role não tem % em app.% — o Caminho 2 não funcionaria', v_privilege, v_table;
      end if;
    end loop;
    foreach v_privilege in array array['DELETE','TRUNCATE'] loop
      if has_table_privilege('service_role', 'app.' || v_table, v_privilege) then
        raise exception 'service_role tem % em app.%; verba não se apaga, fecha vigência', v_privilege, v_table;
      end if;
    end loop;

    select count(*) into v_policies from pg_policies
     where schemaname = 'app' and tablename = v_table;
    if v_policies <> 2 then
      raise exception 'app.% tem % policies, esperava 2 (read e write)', v_table, v_policies;
    end if;
  end loop;

  -- 4. As três de catálogo: leitura por tenant, escrita por admin, e o `with
  --    check` conferido em separado porque é ele que decide o INSERT.
  foreach v_table in array array['benefit_type','benefit_plan','transport_fare'] loop
    select qual into v_qual from pg_policies
     where schemaname = 'app' and tablename = v_table and policyname = v_table || '_read';
    if coalesce(v_qual, '') not like '%can_see_domain%' then
      raise exception '%_read não exige o domínio compensation; com um grant a authenticated por engano, preço de plano vazaria para quem a rota nega', v_table;
    end if;
    -- O domínio certo, e não qualquer um: `can_see_domain(tenant, ''pii'')`
    -- passaria pela linha acima e liberaria o catálogo para outro papel.
    if coalesce(v_qual, '') not like '%compensation%' then
      raise exception '%_read cita can_see_domain mas não o domínio compensation', v_table;
    end if;
    select qual, with_check into v_qual, v_chk from pg_policies
     where schemaname = 'app' and tablename = v_table and policyname = v_table || '_admin';
    if coalesce(v_qual, '') not like '%is_admin%' then
      raise exception '%_admin sem util.is_admin no using', v_table;
    end if;
    if coalesce(v_chk, '') not like '%is_admin%' then
      raise exception '%_admin sem util.is_admin no with check — é ele que decide o INSERT', v_table;
    end if;
  end loop;

  -- 5. A de pessoa: DOIS eixos para ler.
  select qual into v_qual from pg_policies
   where schemaname = 'app' and tablename = 'employee_benefit' and policyname = 'employee_benefit_read';
  if coalesce(v_qual, '') not like '%can_see_domain%' or coalesce(v_qual, '') not like '%can_see_employee%' then
    raise exception 'employee_benefit_read sem os dois eixos (domínio e colaborador)';
  end if;
  -- E ela NÃO ganha o terceiro: endurecer a leitura trancaria quem confere a
  -- folha sem ser admin fora do próprio trabalho.
  if coalesce(v_qual, '') like '%is_admin%' then
    raise exception 'employee_benefit_read ganhou util.is_admin; quem concilia a folha sem ser admin deixaria de ler';
  end if;

  -- 6. TRÊS para escrever, nas DUAS expressões. Olhar só o `using` deixaria
  --    passar exatamente a metade que decide um INSERT.
  select qual, with_check into v_qual, v_chk from pg_policies
   where schemaname = 'app' and tablename = 'employee_benefit' and policyname = 'employee_benefit_write';
  if coalesce(v_qual, '') not like '%can_see_domain%'
     or coalesce(v_qual, '') not like '%can_see_employee%'
     or coalesce(v_qual, '') not like '%is_admin%' then
    raise exception 'employee_benefit_write sem os três eixos no using';
  end if;
  if coalesce(v_chk, '') not like '%can_see_domain%'
     or coalesce(v_chk, '') not like '%can_see_employee%'
     or coalesce(v_chk, '') not like '%is_admin%' then
    raise exception 'employee_benefit_write sem os três eixos no with check — é ele que decide o INSERT';
  end if;

  -- 7. O mecanismo do triênio, que fica mesmo sem o tipo. Tirar estas colunas
  --    obrigaria migration nova no dia em que ele voltar.
  if not exists (
    select 1 from information_schema.columns
     where table_schema = 'app' and table_name = 'benefit_type' and column_name = 'calculation'
  ) then
    raise exception 'benefit_type sem calculation — o mecanismo do triênio permanece (SPEC §1d-bis)';
  end if;
  if (select count(*) from information_schema.columns
       where table_schema = 'app' and table_name = 'employee_benefit'
         and column_name in ('rate','quantity')) <> 2 then
    raise exception 'employee_benefit sem rate/quantity — sem elas o triênio vira montante congelado';
  end if;

  -- 8. A semente. OITO por tenant, e os três que compõem são exatamente os três.
  select count(*) into v_tenants from app.tenant;
  select count(*) into v_seeded from app.benefit_type where code = any(v_semente);
  if v_tenants > 0 and v_seeded <> 8 * v_tenants then
    raise exception 'semente de benefit_type: % linha(s) para % tenant(s), esperava %',
      v_seeded, v_tenants, 8 * v_tenants;
  end if;

  -- ⛔ AS TRÊS ASSERÇÕES FALAM DA SEMENTE, E NÃO DO CATÁLOGO INTEIRO
  -- A versão anterior contava `where composes_base` sem recorte, e isso
  -- contradizia o "Idempotente. Seguro rodar repetidamente" do cabeçalho: no
  -- dia em que o cliente marcasse uma nona verba como compondo a base — PELA
  -- TELA, que é a única razão de a coluna existir —, reaplicar este arquivo
  -- levantava exceção sobre o comportamento desenhado.
  --
  -- O recorte não afrouxa nada: o que a garantia protege é a definição do KPI
  -- COMO SEMEADA, e é sobre as oito linhas que ela tem autoridade. Verba que o
  -- cliente criou é dele, e uma migration que reprova o cliente legítimo é uma
  -- migration que ninguém reaplica.
  select count(*) into v_compoem
    from app.benefit_type where composes_base and code = any(v_semente);
  if v_tenants > 0 and v_compoem <> 3 * v_tenants then
    raise exception 'composes_base verdadeiro em % linha(s) da semente, esperava % (ajuda de custo, cargo de confiança, periculosidade)',
      v_compoem, 3 * v_tenants;
  end if;
  if exists (
    select 1 from app.benefit_type
     where composes_base
       and code = any(v_semente)
       and code not in ('cost_allowance','trust_position','hazard_pay')
  ) then
    raise exception 'verba da semente fora de cost_allowance/trust_position/hazard_pay compõe a folha base — a definição do KPI mudou sem decisão';
  end if;
  if exists (
    select 1 from app.benefit_type
     where code in ('cost_allowance','trust_position','hazard_pay') and not composes_base
  ) then
    raise exception 'verba que compõe a folha base foi semeada como false — o KPI ficaria menor que o legado';
  end if;

  -- 9. ⛔ O NONO, nomeado. Decisão do dono de 04/09, reconfirmada em 05/09: o
  --    triênio fica fora da semente até haver folha importada que prove que ele
  --    NÃO está embutido no salário base do legado. Somá-lo antes disso conta
  --    duas vezes. Reverter a decisão é migration nova, não `insert` calado.
  if exists (select 1 from app.benefit_type where code = 'seniority_bonus') then
    raise exception 'seniority_bonus existe em app.benefit_type; ele ficou FORA por decisão do dono (04/09, reconfirmada 05/09) — a linha de reconciliação vigente é OperaX - legado = 0, e semeá-lo conta o triênio duas vezes';
  end if;

  -- 10. ⛔ OS DOIS ÍNDICES PARCIAIS — "reajuste cria vigência nova" virando estrutura
  --     Esta migration chama, mais acima, de "o pior tipo" a divergência em que o
  --     preço do mês depende da ordem da leitura. É exatamente o que acontece com
  --     duas faixas abertas para a mesma identidade, e o índice parcial é a única
  --     coisa que a impede — o backend fecha antes de inserir, mas quem garante
  --     que ele fechou é o banco recusando quando ele não fecha.
  --
  --     Sem esta verificação, a garantia desta migration passava verde numa base
  --     em que os dois índices tivessem sido derrubados por uma migration
  --     posterior: falso verde dentro do bloco que existe para não haver nenhum.
  --
  --     As QUATRO propriedades são conferidas em separado, porque cada uma falha
  --     de um jeito diferente e calado:
  --       · existir  — sem ele não há recusa nenhuma;
  --       · `unique` — um índice não único aceita as duas faixas abertas;
  --       · parcial  — sem o `where`, ele proibiria REAJUSTE, recusando a segunda
  --                    vigência de um preço que mudou (o oposto do que se quer);
  --       · colunas  — `(tenant_id, code)` sem `kind` na tarifa faria o reajuste da
  --                    unitária colidir com a ida-e-volta, e um índice só em
  --                    `(code)` atravessaria tenant.
  --
  --     Conjunto de colunas comparado INTEIRO, como a `dp_work_post` faz com o
  --     unique dela — e não `like` em `indexdef`, que casaria com um índice de
  --     colunas a mais.
  for v_index, v_relation, v_expected in
    select x.idx, x.rel, x.cols
      from (values
        ('benefit_plan_open_band_idx',   'benefit_plan',   array['code','tenant_id']),
        ('transport_fare_open_band_idx', 'transport_fare', array['code','kind','tenant_id'])
      ) as x(idx, rel, cols)
  loop
    select i.indisunique,
           pg_get_expr(i.indpred, i.indrelid),
           (select array_agg(a.attname::text order by a.attname)
              from unnest(i.indkey::int2[]) k
              join pg_attribute a on a.attrelid = i.indrelid and a.attnum = k)
      into v_unique, v_predicate, v_columns
      from pg_index i
      join pg_class c     on c.oid = i.indexrelid
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'app'
       and c.relname = v_index
       and i.indrelid = ('app.' || v_relation)::regclass;

    if not found then
      raise exception
        'app.% não tem o índice %; sem ele um reajuste que esquecesse de fechar a faixa anterior deixaria duas vigentes, e o preço do mês passaria a depender da ordem da leitura',
        v_relation, v_index;
    end if;
    if not v_unique then
      raise exception
        '% existe mas não é unique; um índice não único aceita as duas faixas abertas que ele deveria recusar',
        v_index;
    end if;
    -- `pg_get_expr` deparsa `where effective_to is null` sempre nesta forma; a
    -- comparação é exata de propósito, porque um predicado PARECIDO — por
    -- exemplo `effective_to is null and active` — deixaria passar duas faixas
    -- abertas de um plano inativo, que é justamente o que ninguém olha.
    if v_predicate is distinct from '(effective_to IS NULL)' then
      raise exception
        '% tem predicado %, esperava (effective_to IS NULL) — sem o parcial ele proibiria o próprio reajuste',
        v_index, coalesce(v_predicate, 'nenhum (índice total)');
    end if;
    if v_columns is distinct from v_expected then
      raise exception '% cobre %, esperava %', v_index, v_columns, v_expected;
    end if;
  end loop;

  -- 11. ⛔ A TRAVA DE FAIXA ABERTA — estrutura E recusa de fato
  --     Quatro propriedades, quatro mensagens: existir, estar na tabela certa
  --     com o momento e o nível certos, RECUSAR o que compõe a base, e ACEITAR
  --     o que não compõe. A quarta não é simetria: uma trava que barra duas
  --     linhas de vale transporte — duas linhas de ônibus, que são legítimas —
  --     é pior que a ausência dela, porque o cliente contorna e ninguém revê.
  select t.tgname, t.tgtype, t.tgenabled, p.proname
    into v_trigger
    from pg_trigger t
    join pg_proc p on p.oid = t.tgfoid
   where t.tgrelid = 'app.employee_benefit'::regclass
     and t.tgname  = 'trg_single_open_base_benefit'
     and not t.tgisinternal;
  if not found then
    raise exception 'app.employee_benefit não tem trg_single_open_base_benefit; duas faixas abertas da mesma verba contariam duas vezes na folha base, caladas';
  end if;
  if v_trigger.proname <> 'enforce_single_open_base_benefit' then
    raise exception 'trg_single_open_base_benefit aponta para %, não para util.enforce_single_open_base_benefit', v_trigger.proname;
  end if;
  -- `tgtype` é bitmap: 1 = for each row, 2 = before, 4 = insert, 16 = update.
  -- Conferido bit a bit porque cada um falha calado por conta própria — um
  -- gatilho `after` deixaria a linha entrar, e um que só cobre insert deixaria
  -- um `update` reabrir a segunda faixa.
  if (v_trigger.tgtype & 1) = 0 then
    raise exception 'trg_single_open_base_benefit não é FOR EACH ROW';
  end if;
  if (v_trigger.tgtype & 2) = 0 then
    raise exception 'trg_single_open_base_benefit não é BEFORE — depois da linha entrar já é tarde';
  end if;
  if (v_trigger.tgtype & 4) = 0 or (v_trigger.tgtype & 16) = 0 then
    raise exception 'trg_single_open_base_benefit não cobre INSERT e UPDATE; reabrir faixa por update escaparia';
  end if;
  if v_trigger.tgenabled = 'D' then
    raise exception 'trg_single_open_base_benefit existe mas está desabilitado';
  end if;

  --     A prova viva, no padrão da migration 34: fixture própria, as duas
  --     direções, e tudo desfeito ao fim. Sem tenant não há o que provar, e o
  --     estrutural acima já correu.
  --     ⛔ A FIXTURE É INTEIRAMENTE PRÓPRIA, E ISSO FOI APRENDIDO NA MARRA
  --     A primeira versão desta prova reusava uma `app.company` existente,
  --     porque `app.employee.company_id` é NOT NULL. Medido em 06/09/2026: o
  --     banco de ensaio do `make db-test` tem 1 tenant e ZERO empresas, então a
  --     prova pulava — e pulava calada, no único lugar em que ela roda. Duas
  --     sabotagens do gatilho passaram verdes por causa disso.
  --     Uma garantia que depende de dado que o ambiente não tem é um verde
  --     falso; então ela cria a empresa também, e desfaz tudo ao fim.
  select t.id into v_tenant from app.tenant t order by t.created_at limit 1;
  if v_tenant is null then
    raise notice 'sem tenant: prova viva da trava pulada (a estrutura já foi verificada acima)';
    return;
  end if;

  insert into app.company (tenant_id, legal_name, active)
  values (v_tenant, '__dp_bc_prova__', false)
  returning id into v_company;

  insert into app.benefit_type (tenant_id, code, name, composes_base)
  values (v_tenant, '__dp_bc_compoe__', 'prova da trava', true)
  on conflict (tenant_id, code) do update set composes_base = true
  returning id into v_compoe;
  insert into app.benefit_type (tenant_id, code, name, composes_base)
  values (v_tenant, '__dp_bc_nao_compoe__', 'prova da trava', false)
  on conflict (tenant_id, code) do update set composes_base = false
  returning id into v_nao;
  insert into app.employee (tenant_id, company_id, name)
  values (v_tenant, v_company, '__dp_bc_prova__')
  returning id into v_employee;

  -- a) a primeira faixa aberta passa;
  insert into app.employee_benefit
    (tenant_id, employee_id, benefit_type_id, effective_from, amount)
  values (v_tenant, v_employee, v_compoe, date '2026-01-01', 100);

  -- b) a segunda, do mesmo par, é barrada;
  begin
    insert into app.employee_benefit
      (tenant_id, employee_id, benefit_type_id, effective_from, amount)
    values (v_tenant, v_employee, v_compoe, date '2026-02-01', 200);
  exception when unique_violation then
    v_barrou := true;
  end;
  if not v_barrou then
    raise exception 'duas faixas abertas da mesma verba de base foram aceitas — a trava não tranca, e a folha base contaria a verba duas vezes';
  end if;

  -- c) mas verba que NÃO compõe repete à vontade: duas linhas de ônibus.
  --    O `exception` não é cerimônia: sem ele a falha aqui sobe com a mensagem
  --    de quem recusou, e quem lê a migration não descobre O QUE quebrou.
  begin
    insert into app.employee_benefit
      (tenant_id, employee_id, benefit_type_id, effective_from, amount)
    values (v_tenant, v_employee, v_nao, date '2026-01-01', 10),
           (v_tenant, v_employee, v_nao, date '2026-01-01', 12);
  exception when unique_violation then
    raise exception 'a trava barrou verba que NÃO compõe a base — duas linhas de vale transporte são legítimas, e uma trava que barra o legítimo é pior que a ausência dela';
  end;

  -- d) e fechada a primeira, o par volta a aceitar — sem isto não haveria
  --    reajuste de verba nenhum, só o primeiro lançamento da vida.
  update app.employee_benefit set effective_to = date '2026-01-31'
   where employee_id = v_employee and benefit_type_id = v_compoe;
  begin
    insert into app.employee_benefit
      (tenant_id, employee_id, benefit_type_id, effective_from, amount)
    values (v_tenant, v_employee, v_compoe, date '2026-02-01', 200);
  exception when unique_violation then
    raise exception 'o par não voltou a aceitar depois de a faixa fechar — a verba teria um lançamento só na vida, e nenhum reajuste';
  end;

  delete from app.employee_benefit where employee_id = v_employee;
  delete from app.employee where id = v_employee;
  delete from app.benefit_type where id in (v_compoe, v_nao);
  delete from app.company where id = v_company;

  raise notice
    'OK: quatro tabelas fora do PostgREST, catálogo por tenant e verba de pessoa com três eixos na escrita; '
    '% tipo(s) semeado(s) em % tenant(s), 3 compõem a folha base, seniority_bonus fora; '
    'as duas faixas abertas recusadas por índice parcial único e, na verba de base, por gatilho.',
    v_seeded, v_tenants;
end $$;
