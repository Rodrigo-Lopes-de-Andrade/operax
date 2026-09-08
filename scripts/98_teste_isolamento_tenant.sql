-- ============================================================================
-- OperaX — TESTE FUNCIONAL DE ISOLAMENTO MULTI-TENANT
-- ----------------------------------------------------------------------------
-- Não basta "a RLS está ligada". Este teste monta dois clientes com dados
-- reais e prova, consultando como cada usuário, que:
--
--   1. Tenant A não enxerga uma linha sequer do tenant B.
--   2. Supervisor de unit só vê a unit dele, mesmo dentro do seu tenant.
--   3. Supervisor não lê PII nem remuneração — ver a unit não basta.
--   4. DP lê PII mas não lê ASO (dado de saúde).
--   5. Evento em mode sombra não aparece para ninguém que não seja admin.
--   6. Contabilidade LÊ conta bancária e NÃO a escreve — a diferença é
--      `util.is_admin`, o terceiro eixo da policy de escrita.
--
-- Roda em transação revertida. Não deixa resíduo.
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/98_teste_isolamento_tenant.sql
-- ============================================================================

begin;

-- ---------------------------------------------------------------------------
-- Cenário
-- ---------------------------------------------------------------------------
insert into auth.users (id, email) values
  ('11111111-1111-1111-1111-111111111111', 'owner.a@teste'),
  ('22222222-2222-2222-2222-222222222222', 'supervisor.a@teste'),
  ('33333333-3333-3333-3333-333333333333', 'dp.a@teste'),
  ('44444444-4444-4444-4444-444444444444', 'owner.b@teste'),
  -- `hr` entrou com o quarto eixo (`banking`). Ele é o par negativo do domínio
  -- de conta bancária, e é um par honesto justamente porque `util.is_admin` o
  -- inclui: ele ENXERGA a pessoa, então o que o barra só pode ser o domínio.
  ('55555555-5555-5555-5555-555555555555', 'rh.a@teste'),
  -- A contabilidade, que é o papel que a escrita de conta bancária separa: ela
  -- TEM `banking` e NÃO é admin. Sem ela no elenco, o terceiro eixo da policy de
  -- escrita não tem quem o exerça, e a asserção de que ele existe seria uma
  -- afirmação sobre ninguém.
  ('66666666-6666-6666-6666-666666666666', 'contabil.a@teste');

insert into app.tenant (id, slug, name) values
  ('aaaaaaaa-0000-0000-0000-000000000001', 'tenant-a', 'Cliente A'),
  ('bbbbbbbb-0000-0000-0000-000000000002', 'tenant-b', 'Cliente B');

insert into app.domain_permission (tenant_id, role, domain, allowed)
select t.id, p.role, d.domain,
       case when p.role = 'owner' then true
            when p.role = 'personnel'    then d.domain in ('pii','compensation','disciplinary')
            else false end
from app.tenant t
cross join (select unnest(enum_range(null::app.user_role)) role) p
cross join (select unnest(enum_range(null::app.sensitive_domain)) domain) d
where t.slug in ('tenant-a','tenant-b')
on conflict do nothing;

-- O quarto eixo, com a MESMA regra da semente de `dp_banking_account`:
-- `owner`, `personnel` e `accounting` alcançam conta bancária; `hr` não.
-- O `do update` é necessário e não é um atalho: a semente genérica acima varre
-- `enum_range(app.sensitive_domain)` inteiro, e `banking` entrou nesse range —
-- ela já gravou `false` para todo mundo que não é `owner`.
insert into app.domain_permission (tenant_id, role, domain, allowed)
select t.id, r.role, 'banking'::app.sensitive_domain,
       r.role in ('owner','personnel','accounting')
from app.tenant t
cross join (select unnest(enum_range(null::app.user_role)) as role) r
where t.slug in ('tenant-a','tenant-b')
on conflict (tenant_id, role, domain) do update set allowed = excluded.allowed;

-- ⛔ `compensation` COM A MATRIZ REAL, e a divergência que isto conserta.
-- A semente genérica logo acima dá `compensation` a `owner` e `personnel` e zera
-- todo o resto. A semente do produto (migration 02) dá o domínio a QUATRO papéis:
-- `owner`, `personnel`, `executive` e `accounting`. Enquanto `compensation` só
-- guardava dado por pessoa isso não aparecia; desde 06/09 ele guarda também a
-- LEITURA do catálogo de verbas, e aí a divergência esconde justamente a
-- pergunta que importa — se o `accounting`, cujo trabalho é conciliar a folha,
-- continua alcançando a tabela de preços de que ele precisa.
-- Sem esta linha, "accounting é barrado no catálogo" ficaria verde no teste e
-- falso em produção. Mesmo padrão e mesmo motivo do bloco de `banking` acima.
insert into app.domain_permission (tenant_id, role, domain, allowed)
select t.id, r.role, 'compensation'::app.sensitive_domain,
       r.role in ('owner','personnel','executive','accounting')
from app.tenant t
cross join (select unnest(enum_range(null::app.user_role)) as role) r
where t.slug in ('tenant-a','tenant-b')
on conflict (tenant_id, role, domain) do update set allowed = excluded.allowed;

insert into app.tenant_member (tenant_id, user_id, role) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'owner'),
  ('aaaaaaaa-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'unit_supervisor'),
  ('aaaaaaaa-0000-0000-0000-000000000001', '33333333-3333-3333-3333-333333333333', 'personnel'),
  ('aaaaaaaa-0000-0000-0000-000000000001', '55555555-5555-5555-5555-555555555555', 'hr'),
  ('aaaaaaaa-0000-0000-0000-000000000001', '66666666-6666-6666-6666-666666666666', 'accounting'),
  ('bbbbbbbb-0000-0000-0000-000000000002', '44444444-4444-4444-4444-444444444444', 'owner');

insert into app.company (id, tenant_id, legal_name, trade_name) values
  ('a0000000-0000-0000-0000-0000000000e1', 'aaaaaaaa-0000-0000-0000-000000000001', 'Empresa A1 LTDA', 'A1'),
  ('b0000000-0000-0000-0000-0000000000e1', 'bbbbbbbb-0000-0000-0000-000000000002', 'Empresa B1 LTDA', 'B1');

insert into app.unit (id, tenant_id, company_id, code, name) values
  ('a0000000-0000-0000-0000-0000000000a1', 'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000e1', 'A-CENTRO', 'A Centro'),
  ('a0000000-0000-0000-0000-0000000000a2', 'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000e1', 'A-NORTE',  'A Norte'),
  ('b0000000-0000-0000-0000-0000000000a1', 'bbbbbbbb-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-0000000000e1', 'B-SUL',    'B Sul');

-- Supervisor A só tem escopo na unit A Centro.
insert into app.user_scope (tenant_id, user_id, unit_id) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '22222222-2222-2222-2222-222222222222', 'a0000000-0000-0000-0000-0000000000a1');

-- A contabilidade enxerga o tenant inteiro (empresa e unit nulas), e isso é a
-- realidade da conciliação: a remessa é do tenant, não de uma unidade. Sem esta
-- linha ela não é `owner/executive/hr/personnel` em `util.can_see_unit` nem é
-- admin, então `can_see_employee` diria não — e o "accounting não escreve" ficaria
-- verde pelo eixo errado, que é exatamente o falso verde que este arquivo caça.
insert into app.user_scope (tenant_id, user_id, company_id, unit_id) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '66666666-6666-6666-6666-666666666666', null, null);

insert into app.employee (id, tenant_id, company_id, unit_id, name) values
  ('a0000000-0000-0000-0000-0000000000c1', 'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000e1', 'a0000000-0000-0000-0000-0000000000a1', 'Colab A Centro'),
  ('a0000000-0000-0000-0000-0000000000c2', 'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000e1', 'a0000000-0000-0000-0000-0000000000a2', 'Colab A Norte'),
  ('b0000000-0000-0000-0000-0000000000c1', 'bbbbbbbb-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-0000000000e1', 'b0000000-0000-0000-0000-0000000000a1', 'Colab B Sul');

-- O gestor como dimensão (migration 27). Um por unidade em A, para o ranking
-- ter o que separar; um em B, para provar que ele não atravessa.
insert into app.manager (id, tenant_id, secullum_structure_id, name) values
  ('a0000000-0000-0000-0000-0000000000f1', 'aaaaaaaa-0000-0000-0000-000000000001', 8001, 'Gestor A Centro'),
  ('a0000000-0000-0000-0000-0000000000f2', 'aaaaaaaa-0000-0000-0000-000000000001', 8002, 'Gestor A Norte'),
  ('b0000000-0000-0000-0000-0000000000f1', 'bbbbbbbb-0000-0000-0000-000000000002', 8003, 'Gestor B Sul');

update app.employee set manager_id = 'a0000000-0000-0000-0000-0000000000f1'
 where id = 'a0000000-0000-0000-0000-0000000000c1';
update app.employee set manager_id = 'a0000000-0000-0000-0000-0000000000f2'
 where id = 'a0000000-0000-0000-0000-0000000000c2';
update app.employee set manager_id = 'b0000000-0000-0000-0000-0000000000f1'
 where id = 'b0000000-0000-0000-0000-0000000000c1';

insert into app.employee_pii (employee_id, tenant_id, cpf, rg) values
  ('a0000000-0000-0000-0000-0000000000c1', 'aaaaaaaa-0000-0000-0000-000000000001', '00000000191', 'MG-1'),
  ('b0000000-0000-0000-0000-0000000000c1', 'bbbbbbbb-0000-0000-0000-000000000002', '00000000272', 'SP-2');

-- Foto imputada (migration 36). ⛔ Tabela SEM grant para `authenticated`: o
-- desenho é só Caminho 2. As asserções abaixo provam os dois lados — que nenhum
-- papel a alcança pelo PostgREST, e que a fronteira não é vácuo.
insert into app.employee_photo
       (tenant_id, employee_id, content, mime, bytes, sha256)
select tenant_id, employee_id, '\xffd8ff00'::bytea, 'image/jpeg', 4,
       repeat('a', 64)
  from app.employee_pii limit 1;


-- Domínio disciplinar (migration 32) e domínio de saúde, uma linha cada — e no
-- colaborador que o supervisor **enxerga**, de propósito. Sem linha, "não lê"
-- conta zero numa tabela vazia e a asserção passa sem provar nada: foi o que a
-- migration 28 ensinou, e o exame ocupacional estava exatamente nesse estado.
-- Com a linha aqui, o que barra o supervisor é o domínio, não a falta de dado.
insert into app.disciplinary_event (tenant_id, employee_id, type, occurred_on, summary) values
  ('aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c1',
   'written_warning','2026-08-12','Fixture de teste — atraso reincidente');

insert into app.occupational_exam (tenant_id, employee_id, type, performed_on, result) values
  ('aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c1',
   'periodic','2026-08-12','fit');

-- Domínio `banking` (`dp_banking_account`). Uma conta em cada tenant, e a de A
-- no colaborador que o supervisor e o RH ENXERGAM — pelo mesmo motivo das duas
-- linhas acima: numa tabela vazia, "hr não lê" é verdade sobre o vazio.
insert into app.employee_bank_account
       (employee_id, tenant_id, bank_code, branch, account, account_type) values
  ('a0000000-0000-0000-0000-0000000000c1','aaaaaaaa-0000-0000-0000-000000000001',
   '341','1234','98765-4','checking'),
  ('b0000000-0000-0000-0000-0000000000c1','bbbbbbbb-0000-0000-0000-000000000002',
   '237','5678','11223-3','salary');

insert into app.deviation_type_config (tenant_id, code, active, counts_as_deviation)
select t.id, dt.code, true, true
from app.tenant t cross join app.deviation_type dt
where t.slug in ('tenant-a','tenant-b')
on conflict do nothing;

insert into app.deviation_event (tenant_id, employee_id, company_id, unit_id, reference_date, type, minutes, mode) values
  ('aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c1','a0000000-0000-0000-0000-0000000000e1','a0000000-0000-0000-0000-0000000000a1','2026-08-10','late_entry',-15,'production'),
  ('aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c2','a0000000-0000-0000-0000-0000000000e1','a0000000-0000-0000-0000-0000000000a2','2026-08-10','late_entry',-22,'production'),
  ('aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c1','a0000000-0000-0000-0000-0000000000e1','a0000000-0000-0000-0000-0000000000a1','2026-08-11','late_exit', 40,'shadow'),
  ('bbbbbbbb-0000-0000-0000-000000000002','b0000000-0000-0000-0000-0000000000c1','b0000000-0000-0000-0000-0000000000e1','b0000000-0000-0000-0000-0000000000a1','2026-08-10','late_entry',-99,'production');

-- Etapa DP / S1 — Quadro de Postos e catálogo de verbas.
-- As cinco tabelas do S1 têm a MESMA forma das duas do S2: nenhum grant para
-- `authenticated`. Então um `select` ali é `permission denied` para todo mundo,
-- e contar linhas como fulano não distingue quem pode de quem não pode. As
-- linhas abaixo existem para que o negativo não seja vácuo, e as asserções que
-- as usam avaliam a POLICY, não o grant — `pg_temp.policy_says_on`.
--
-- Um posto em CADA unidade de A, de propósito: sem o de A Centro, "o supervisor
-- não vê o posto de A Norte" ficaria verde num quadro vazio, que é exatamente o
-- falso verde que este arquivo persegue.
insert into app.work_post (id, tenant_id, unit_id, code, name) values
  ('a0000000-0000-0000-0000-0000000000d1','aaaaaaaa-0000-0000-0000-000000000001',
   'a0000000-0000-0000-0000-0000000000a1','7703','Portaria A Centro'),
  ('a0000000-0000-0000-0000-0000000000d2','aaaaaaaa-0000-0000-0000-000000000001',
   'a0000000-0000-0000-0000-0000000000a2','7704','Portaria A Norte'),
  ('b0000000-0000-0000-0000-0000000000d1','bbbbbbbb-0000-0000-0000-000000000002',
   'b0000000-0000-0000-0000-0000000000a1','7703','Portaria B Sul');

-- O catálogo é semeado pela própria migration, mas para os tenants que existiam
-- QUANDO ela rodou — e os dois deste cenário nascem aqui dentro, na transação.
-- Sem este insert, `benefit_type` fica vazia para A e B e toda asserção sobre
-- verba viraria afirmação sobre o vazio.
insert into app.benefit_type (tenant_id, code, name, composes_base)
select t.id, s.code, s.name, s.composes_base
from app.tenant t
cross join (values
  ('cost_allowance',    'Ajuda de custo',  true),
  ('meal_voucher',      'Vale refeição',   false),
  ('transport_voucher', 'Vale transporte', false)
) as s(code, name, composes_base)
where t.slug in ('tenant-a','tenant-b')
on conflict (tenant_id, code) do nothing;

-- A verba de pessoa, no colaborador que o RH e o supervisor ENXERGAM — pelo
-- mesmo motivo da conta bancária: numa tabela vazia, "hr não lê" é verdade
-- sobre o vazio e não diz nada sobre o domínio `compensation`.
insert into app.employee_benefit
       (tenant_id, employee_id, benefit_type_id, effective_from, amount)
select bt.tenant_id, c.id, bt.id, date '2026-08-01', 500.00
from app.benefit_type bt
join app.employee c on c.tenant_id = bt.tenant_id
where bt.code = 'cost_allowance'
  and c.id in ('a0000000-0000-0000-0000-0000000000c1',
               'b0000000-0000-0000-0000-0000000000c1');

-- ---------------------------------------------------------------------------
-- Etapa DP / S3 — o ciclo mensal de cesta e vale transporte.
-- ---------------------------------------------------------------------------
-- Mesmo motivo das linhas do S1 logo acima: as três tabelas do S3 também não
-- concedem nada a `authenticated`, então as asserções abaixo avaliam a POLICY.
-- A semente existe para que o negativo não seja vácuo e para que a contagem
-- estrutural tenha o que contar.
--
-- Um ciclo em CADA tenant, e em A uma linha para o colaborador de A CENTRO e
-- outra para o de A NORTE: sem as duas, "o accounting de escopo estreito não vê
-- a linha da outra unidade" ficaria verde num ciclo de uma linha só.
insert into app.benefit_cycle (id, tenant_id, kind, period_year, period_month,
       window_start, window_end, business_days, status) values
  ('a0000000-0000-0000-0000-0000000000b1','aaaaaaaa-0000-0000-0000-000000000001',
   'transport_voucher',2026,9,'2026-08-21','2026-09-20',21,'draft'),
  ('b0000000-0000-0000-0000-0000000000b1','bbbbbbbb-0000-0000-0000-000000000002',
   'transport_voucher',2026,9,'2026-08-21','2026-09-20',21,'draft');

insert into app.benefit_entitlement (id, tenant_id, cycle_id, employee_id, unit_id,
       entitled, total_amount) values
  ('a0000000-0000-0000-0000-0000000000b2','aaaaaaaa-0000-0000-0000-000000000001',
   'a0000000-0000-0000-0000-0000000000b1','a0000000-0000-0000-0000-0000000000c1',
   'a0000000-0000-0000-0000-0000000000a1', true, 161.50),
  ('a0000000-0000-0000-0000-0000000000b3','aaaaaaaa-0000-0000-0000-000000000001',
   'a0000000-0000-0000-0000-0000000000b1','a0000000-0000-0000-0000-0000000000c2',
   'a0000000-0000-0000-0000-0000000000a2', true, 161.50),
  ('b0000000-0000-0000-0000-0000000000b2','bbbbbbbb-0000-0000-0000-000000000002',
   'b0000000-0000-0000-0000-0000000000b1','b0000000-0000-0000-0000-0000000000c1',
   'b0000000-0000-0000-0000-0000000000a1', true, 99.00);

-- A curadoria de justificativa. `unjustified_absence` é a categoria que a
-- migration `dp_leave_category` acrescentou, e semeá-la aqui prova de passagem
-- que o check novo a aceita.
insert into app.leave_justification_map (tenant_id, justification, category, validated_at)
select t.id, s.justificativa, s.categoria::text, now()
from app.tenant t
cross join (values ('FALTA','unjustified_absence'), ('FÉRIAS','vacation'))
  as s(justificativa, categoria)
where t.slug in ('tenant-a','tenant-b')
on conflict do nothing;

-- ---------------------------------------------------------------------------
-- Utilitário de asserção
-- ---------------------------------------------------------------------------
create or replace function pg_temp.assert_eq(rotulo text, obtido bigint, esperado bigint)
returns void language plpgsql as $$
begin
  if obtido is distinct from esperado then
    raise exception 'FALHA [%]: esperado %, obtido %', rotulo, esperado, obtido;
  end if;
  raise notice '  ok  % (%)', rotulo, obtido;
end $$;

-- ---------------------------------------------------------------------------
-- Avaliador de policy — para tabela que `authenticated` não alcança
-- ---------------------------------------------------------------------------
-- `app.employee_bank_account` não concede NADA ao papel do navegador: um
-- `select` dali devolve `permission denied` para todo mundo, inclusive para quem
-- tem o domínio. Isso torna o teste habitual ("conte as linhas como fulano")
-- incapaz de distinguir quem pode de quem não pode — e um conjunto só de
-- negativas é exatamente o falso verde que este arquivo existe para não repetir.
--
-- Então a policy é avaliada como ela está NO CATÁLOGO, contra os valores da
-- linha semeada, na sessão do usuário que está sendo testado. Não é uma cópia da
-- regra: é a expressão da própria policy, lida de `pg_policies`. Reescrever a
-- policy muda o que este teste executa — que é o ponto.
--
-- ⛔ QUAL DAS DUAS EXPRESSÕES, E A PERGUNTA NÃO É RETÓRICA
-- Uma policy `for all` tem duas: o `using` (que linhas ela alcança) e o
-- `with check` (que valores ela aceita). Num INSERT quem decide é o `with check`
-- — o `using` é irrelevante. Hoje os dois textos de `employee_bank_account_write`
-- são idênticos, então avaliar um pelo outro daria o mesmo resultado POR
-- COINCIDÊNCIA; quem afrouxasse só o `with check` amanhã passaria verde. Por
-- isso o avaliador recebe qual delas rodar, e a asserção de escrita pede
-- explicitamente o `with_check`.
create or replace function pg_temp.policy_says(
  p_policy text, p_tenant uuid, p_employee uuid, p_which text default 'qual')
returns bigint language plpgsql as $$
declare
  v_expr text;
  v_ok   boolean;
begin
  if p_which not in ('qual','with_check') then
    raise exception 'FALHA: policy_says não sabe avaliar "%"', p_which;
  end if;
  select case when p_which = 'qual' then qual else with_check end
    into v_expr
    from pg_policies
   where schemaname = 'app' and tablename = 'employee_bank_account' and policyname = p_policy;
  if not found then
    raise exception 'FALHA: policy % não existe em app.employee_bank_account', p_policy;
  end if;
  -- Ausente não é "permitido": uma policy sem `with check` não avalia INSERT
  -- nenhum, e devolver 0 calado esconderia a policy que sumiu.
  if v_expr is null then
    raise exception 'FALHA: policy % não tem % — não há o que avaliar', p_policy, p_which;
  end if;
  execute format(
    'select (%s) from (select %L::uuid as tenant_id, %L::uuid as employee_id) s',
    v_expr, p_tenant, p_employee) into v_ok;
  return case when coalesce(v_ok, false) then 1 else 0 end;
end $$;

-- ---------------------------------------------------------------------------
-- Avaliador de policy, generalizado — as cinco tabelas do S1
-- ---------------------------------------------------------------------------
-- Irmão do `pg_temp.policy_says` acima, que é preso a `employee_bank_account`.
-- Mesmo princípio, e ele é o ponto: a expressão vem de `pg_policies`, na sessão
-- do usuário testado. Não é uma cópia da regra no teste — reescrever a policy
-- muda o que este arquivo executa.
--
-- A linha sintética carrega os TRÊS eixos que as policies do S1 mencionam
-- (`tenant_id`, `employee_id`, `unit_id`), porque elas diferem entre si:
-- `work_post_read` fala de unidade, `benefit_type_read` de tenant e
-- `employee_benefit_read` de tenant e pessoa.
create or replace function pg_temp.policy_says_on(
  p_table text, p_policy text, p_tenant uuid, p_employee uuid, p_unit uuid,
  p_which text default 'qual')
returns bigint language plpgsql as $$
declare
  v_expr text;
  v_ok   boolean;
begin
  if p_which not in ('qual','with_check') then
    raise exception 'FALHA: policy_says_on não sabe avaliar "%"', p_which;
  end if;
  select case when p_which = 'qual' then qual else with_check end
    into v_expr
    from pg_policies
   where schemaname = 'app' and tablename = p_table and policyname = p_policy;
  if not found then
    raise exception 'FALHA: policy % não existe em app.%', p_policy, p_table;
  end if;
  -- Ausente não é "permitido": uma policy sem `with check` não avalia INSERT
  -- nenhum, e devolver 0 calado esconderia a policy que sumiu.
  if v_expr is null then
    raise exception 'FALHA: policy % de app.% não tem % — não há o que avaliar',
      p_policy, p_table, p_which;
  end if;
  execute format(
    'select (%s) from (select %L::uuid as tenant_id, %L::uuid as employee_id, '
    '%L::uuid as unit_id) s',
    v_expr, p_tenant, p_employee, p_unit) into v_ok;
  return case when coalesce(v_ok, false) then 1 else 0 end;
end $$;

-- ---------------------------------------------------------------------------
\echo '--- Owner do tenant A'
-- ---------------------------------------------------------------------------
-- ⚠️ O anti-vácuo roda AQUI, como dono, e não no bloco do DP: lá o papel é
--    `authenticated`, que por desenho não alcança a tabela — a asserção falharia
--    por `permission denied`, que é o resultado que ela existe para confirmar
--    noutro lugar. Sem esta linha, "authenticated não alcança" ficaria verde numa
--    tabela vazia.
do $$ begin
  perform pg_temp.assert_eq('a foto imputada foi semeada (o negativo não é vácuo)',
    (select count(*) from app.employee_photo), 1);
end $$;

-- Mesmo raciocínio para a conta bancária, e pelos mesmos dois motivos: a linha
-- existe (o negativo não é vácuo) e a tabela está fora do PostgREST em TODOS os
-- verbos — perguntar só por `select` deixaria um `grant insert` passar, e
-- escrever conta alheia é pior que lê-la.
do $$ begin
  perform pg_temp.assert_eq('as 2 contas bancárias foram semeadas (o negativo não é vácuo)',
    (select count(*) from app.employee_bank_account), 2);
  perform pg_temp.assert_eq('authenticated não tem verbo nenhum em app.employee_bank_account',
    (select count(*) from unnest(array['SELECT','INSERT','UPDATE','DELETE']) v
      where has_table_privilege('authenticated', 'app.employee_bank_account', v)), 0);
  perform pg_temp.assert_eq('anon idem',
    (select count(*) from unnest(array['SELECT','INSERT','UPDATE','DELETE']) v
      where has_table_privilege('anon', 'app.employee_bank_account', v)), 0);
  -- E o backend alcança: sem este positivo, os dois acima ficariam verdes numa
  -- tabela que ninguém lê, e o Caminho 2 não existiria.
  perform pg_temp.assert_eq('service_role lê a conta (é o Caminho 2 que monta a remessa)',
    case when has_table_privilege('service_role', 'app.employee_bank_account', 'SELECT')
         then 1 else 0 end, 1);
end $$;

-- As cinco tabelas do S1, na mesma forma em que a conta bancária foi conferida:
-- o negativo não é vácuo, a porta do navegador está fechada em TODOS os verbos,
-- e o backend alcança. Roda AQUI, como dono, porque sob `authenticated` a
-- própria leitura de contagem seria `permission denied`.
do $$
declare v_tabela text;
begin
  perform pg_temp.assert_eq('os 3 postos do cenário foram semeados (o negativo não é vácuo)',
    (select count(*) from app.work_post), 3);
  perform pg_temp.assert_eq('as 2 verbas de pessoa foram semeadas (idem)',
    (select count(*) from app.employee_benefit), 2);
  perform pg_temp.assert_eq('o catálogo de verbas tem linha nos 2 tenants (idem)',
    (select count(*) from app.benefit_type
      where tenant_id in ('aaaaaaaa-0000-0000-0000-000000000001',
                          'bbbbbbbb-0000-0000-0000-000000000002')), 6);

  foreach v_tabela in array array['work_post','benefit_type','benefit_plan',
                                  'transport_fare','employee_benefit'] loop
    -- Perguntar só por `select` deixaria um `grant insert` passar — e inventar
    -- verba alheia é pior que lê-la: ela entra no KPI de custo do cliente.
    perform pg_temp.assert_eq('authenticated não tem verbo nenhum em app.' || v_tabela,
      (select count(*) from unnest(array['SELECT','INSERT','UPDATE','DELETE']) v
        where has_table_privilege('authenticated', 'app.' || v_tabela, v)), 0);
    perform pg_temp.assert_eq('anon idem em app.' || v_tabela,
      (select count(*) from unnest(array['SELECT','INSERT','UPDATE','DELETE']) v
        where has_table_privilege('anon', 'app.' || v_tabela, v)), 0);
    -- O positivo. Sem ele os dois acima ficam verdes em cinco tabelas que
    -- ninguém alcança, e o Caminho 2 não existiria.
    perform pg_temp.assert_eq('service_role LÊ app.' || v_tabela || ' (o Caminho 2 existe)',
      case when has_table_privilege('service_role', 'app.' || v_tabela, 'SELECT')
           then 1 else 0 end, 1);
    -- Regra 3 do CLAUDE.md, conferida no catálogo e não na migration: uma
    -- migration posterior pode desligar a RLS sem tocar no arquivo do S1.
    perform pg_temp.assert_eq('app.' || v_tabela || ' tem RLS ligada',
      case when (select relrowsecurity from pg_class
                  where oid = ('app.' || v_tabela)::regclass) then 1 else 0 end, 1);
    perform pg_temp.assert_eq('app.' || v_tabela || ' tem tenant_id',
      (select count(*) from information_schema.columns
        where table_schema = 'app' and table_name = v_tabela
          and column_name = 'tenant_id'), 1);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- A trava de faixa aberta de `app.employee_benefit`, pelos DOIS lados
-- ---------------------------------------------------------------------------
-- Decisão do dono de 06/09: uma faixa aberta por (colaborador, verba) NOS TIPOS
-- QUE COMPÕEM A BASE. A migration prova o gatilho com fixture própria; aqui ele
-- é exercido contra o cenário real deste arquivo — colaborador de verdade, verba
-- de verdade, a linha aberta que a semente já deixou.
--
-- ⛔ OS DOIS LADOS, e o segundo não é simetria: uma trava que barra o legítimo é
--    pior que a ausência dela. `transport_voucher` REPETE de propósito (duas
--    linhas de ônibus), e é o gatilho restrito que permite isso — um índice
--    único simples em (colaborador, verba) passaria no primeiro teste e
--    quebraria o vale transporte de todo mundo, calado.
--
-- Roda como dono e dentro de savepoint: `authenticated` não tem grant nenhum
-- aqui, e o `rollback to savepoint` desfaz sem apagar nada.
savepoint prova_da_trava;

do $$
declare
  v_tenant   uuid := 'aaaaaaaa-0000-0000-0000-000000000001';
  v_employee uuid := 'a0000000-0000-0000-0000-0000000000c1';
  v_compoe   uuid;
  v_nao      uuid;
  v_barrou   boolean := false;
begin
  select id into v_compoe from app.benefit_type
   where tenant_id = v_tenant and code = 'cost_allowance';
  select id into v_nao from app.benefit_type
   where tenant_id = v_tenant and code = 'transport_voucher';

  -- O ponto de partida, medido e não suposto: a semente deixou UMA faixa aberta
  -- de `cost_allowance` para este colaborador. Sem esta linha, a recusa abaixo
  -- poderia vir de qualquer outro motivo.
  perform pg_temp.assert_eq('o colaborador já tem 1 faixa aberta de verba que compõe a base',
    (select count(*) from app.employee_benefit
      where employee_id = v_employee and benefit_type_id = v_compoe
        and effective_to is null), 1);

  -- a) O NEGATIVO: a segunda faixa aberta do mesmo par é recusada.
  begin
    insert into app.employee_benefit
      (tenant_id, employee_id, benefit_type_id, effective_from, amount)
    values (v_tenant, v_employee, v_compoe, date '2026-09-01', 700);
  exception when unique_violation then
    v_barrou := true;
  end;
  perform pg_temp.assert_eq('a 2a faixa aberta de verba que COMPÕE a base é recusada',
    case when v_barrou then 1 else 0 end, 1);

  -- b) O POSITIVO: verba que não compõe repete à vontade.
  insert into app.employee_benefit
    (tenant_id, employee_id, benefit_type_id, effective_from, amount)
  values (v_tenant, v_employee, v_nao, date '2026-01-01', 10),
         (v_tenant, v_employee, v_nao, date '2026-01-01', 12);
  perform pg_temp.assert_eq('duas faixas abertas de VALE TRANSPORTE passam (a trava não barra o legítimo)',
    (select count(*) from app.employee_benefit
      where employee_id = v_employee and benefit_type_id = v_nao
        and effective_to is null), 2);

  -- c) E fechada a faixa, o par volta a aceitar — sem isto não haveria reajuste
  --    de verba nenhum, só o primeiro lançamento da vida.
  update app.employee_benefit set effective_to = date '2026-08-31'
   where employee_id = v_employee and benefit_type_id = v_compoe
     and effective_to is null;
  insert into app.employee_benefit
    (tenant_id, employee_id, benefit_type_id, effective_from, amount)
  values (v_tenant, v_employee, v_compoe, date '2026-09-01', 700);
  perform pg_temp.assert_eq('fechada a anterior, a verba de base aceita a faixa nova',
    (select count(*) from app.employee_benefit
      where employee_id = v_employee and benefit_type_id = v_compoe
        and effective_to is null), 1);
end $$;

rollback to savepoint prova_da_trava;

-- E o savepoint não deixou rastro: sem esta conferência, um `rollback to` que
-- não pegasse deixaria as linhas de prova contaminando as contagens abaixo.
do $$ begin
  perform pg_temp.assert_eq('a prova da trava não deixou rastro',
    (select count(*) from app.employee_benefit), 2);
end $$;

-- ---------------------------------------------------------------------------
-- As TRÊS tabelas do S3, na mesma forma das cinco do S1
-- ---------------------------------------------------------------------------
-- Roda como dono: sob `authenticated` a própria contagem seria permission denied.
do $$
declare v_tabela text;
begin
  perform pg_temp.assert_eq('os 2 ciclos do cenário foram semeados (o negativo não é vácuo)',
    (select count(*) from app.benefit_cycle), 2);
  perform pg_temp.assert_eq('as 3 linhas de direito foram semeadas (idem)',
    (select count(*) from app.benefit_entitlement), 3);
  perform pg_temp.assert_eq('a curadoria tem 2 linhas em cada tenant (idem)',
    (select count(*) from app.leave_justification_map), 4);

  foreach v_tabela in array array['benefit_cycle','benefit_entitlement',
                                  'leave_justification_map'] loop
    perform pg_temp.assert_eq('authenticated não tem verbo nenhum em app.' || v_tabela,
      (select count(*) from unnest(array['SELECT','INSERT','UPDATE','DELETE']) v
        where has_table_privilege('authenticated', 'app.' || v_tabela, v)), 0);
    perform pg_temp.assert_eq('anon idem em app.' || v_tabela,
      (select count(*) from unnest(array['SELECT','INSERT','UPDATE','DELETE']) v
        where has_table_privilege('anon', 'app.' || v_tabela, v)), 0);
    -- O positivo: sem ele os dois acima ficam verdes em tabela que ninguém alcança.
    perform pg_temp.assert_eq('service_role LÊ app.' || v_tabela || ' (o Caminho 2 existe)',
      case when has_table_privilege('service_role', 'app.' || v_tabela, 'SELECT')
           then 1 else 0 end, 1);
    perform pg_temp.assert_eq('app.' || v_tabela || ' tem RLS ligada',
      case when (select relrowsecurity from pg_class
                  where oid = ('app.' || v_tabela)::regclass) then 1 else 0 end, 1);
    perform pg_temp.assert_eq('app.' || v_tabela || ' tem tenant_id',
      (select count(*) from information_schema.columns
        where table_schema = 'app' and table_name = v_tabela
          and column_name = 'tenant_id'), 1);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- A trava de imutabilidade do ciclo, exercida — os DOIS lados
-- ---------------------------------------------------------------------------
-- ⛔ O avanço de status é fresta DECLARADA; o que ela não pode é deixar valor
--    mudar nem status VOLTAR. Uma trava que só dissesse "não" ao rascunho
--    também passaria num "generated é imutável" — por isso o rascunho mutável
--    entra como positivo.
savepoint prova_do_ciclo;

do $$
declare
  v_ciclo uuid := 'a0000000-0000-0000-0000-0000000000b1';
  v_erro  text;
begin
  -- a) POSITIVO: rascunho se refaz — é o fluxo de reapuração.
  update app.benefit_cycle set business_days = 22 where id = v_ciclo;
  perform pg_temp.assert_eq('rascunho aceita mudar valor (a trava não barra o legítimo)',
    (select business_days from app.benefit_cycle where id = v_ciclo), 22);
  update app.benefit_entitlement set total_amount = 170 where cycle_id = v_ciclo
     and employee_id = 'a0000000-0000-0000-0000-0000000000c1';

  update app.benefit_cycle set status = 'generated' where id = v_ciclo;

  -- b) POSITIVO: o status AVANÇA — generated -> exported.
  update app.benefit_cycle set status = 'exported' where id = v_ciclo;
  perform pg_temp.assert_eq('ciclo gerado avança para exported (fresta declarada)',
    case when (select status from app.benefit_cycle where id = v_ciclo) = 'exported'
         then 1 else 0 end, 1);

  -- c) NEGATIVO: e não VOLTA. A fresta é de mão única.
  begin
    update app.benefit_cycle set status = 'generated' where id = v_ciclo;
    v_erro := null;
  exception when others then v_erro := sqlerrm;
  end;
  perform pg_temp.assert_eq('exported NÃO volta para generated',
    case when v_erro like 'Transição de status%' then 1 else 0 end, 1);

  -- d) NEGATIVO: valor não muda em ciclo congelado.
  begin
    update app.benefit_cycle set business_days = 99 where id = v_ciclo;
    v_erro := null;
  exception when others then v_erro := sqlerrm;
  end;
  perform pg_temp.assert_eq('ciclo congelado NÃO deixa mudar valor',
    case when v_erro like '%imutável%' then 1 else 0 end, 1);

  -- e) NEGATIVO: linha de ciclo congelado não muda, não entra e não sai.
  begin
    update app.benefit_entitlement set total_amount = 999 where cycle_id = v_ciclo;
    v_erro := null;
  exception when others then v_erro := sqlerrm;
  end;
  perform pg_temp.assert_eq('linha de ciclo congelado NÃO muda',
    case when v_erro like '%não se mexe mais%' then 1 else 0 end, 1);
  begin
    delete from app.benefit_entitlement where cycle_id = v_ciclo;
    v_erro := null;
  exception when others then v_erro := sqlerrm;
  end;
  perform pg_temp.assert_eq('linha de ciclo congelado NÃO sai (regra 6: sem delete físico)',
    case when v_erro like '%não se mexe mais%' then 1 else 0 end, 1);

  -- f) NEGATIVO: nem o cabeçalho é apagado.
  begin
    delete from app.benefit_cycle where id = v_ciclo;
    v_erro := null;
  exception when others then v_erro := sqlerrm;
  end;
  perform pg_temp.assert_eq('ciclo gerado NÃO é apagado',
    case when v_erro like '%não é apagado%' then 1 else 0 end, 1);
end $$;

rollback to savepoint prova_do_ciclo;

do $$ begin
  perform pg_temp.assert_eq('a prova do ciclo não deixou rastro',
    (select count(*) from app.benefit_entitlement), 3);
  perform pg_temp.assert_eq('e o ciclo voltou a rascunho',
    case when (select status from app.benefit_cycle
                where id = 'a0000000-0000-0000-0000-0000000000b1') = 'draft'
         then 1 else 0 end, 1);
end $$;

set local role authenticated;
set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';

do $$ begin
  perform pg_temp.assert_eq('owner A vê 2 colaboradores (só do tenant A)',
    (select count(*) from public.vw_employee), 2);
  perform pg_temp.assert_eq('owner A vê 2 unidades',
    (select count(*) from public.vw_unit), 2);
  perform pg_temp.assert_eq('owner A vê 2 desvios em produção (sombra fora da view)',
    (select count(*) from public.vw_deviation_event), 2);
  perform pg_temp.assert_eq('owner A lê PII do seu tenant',
    (select count(*) from app.employee_pii), 1);
  perform pg_temp.assert_eq('KPI do período confere',
    (select eventos from public.fn_kpi_period('2026-08-01','2026-08-31')), 2);
  perform pg_temp.assert_eq('owner A vê os 2 gestores dele',
    (select count(*) from app.manager), 2);
  perform pg_temp.assert_eq('e o ranking por gestor separa os dois',
    (select count(*) from public.fn_ranking_by_manager('2026-08-01','2026-08-31')), 2);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- Owner do tenant B (não pode ver NADA de A)'
-- ---------------------------------------------------------------------------
set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';

do $$ begin
  perform pg_temp.assert_eq('owner B vê só o próprio employee',
    (select count(*) from public.vw_employee), 1);
  perform pg_temp.assert_eq('owner B não vê employee de A',
    (select count(*) from public.vw_employee where name like 'Colab A%'), 0);
  perform pg_temp.assert_eq('owner B não vê desvio de A',
    (select count(*) from public.vw_deviation_event where minutes <> -99), 0);
  perform pg_temp.assert_eq('owner B não vê gestor de A',
    (select count(*) from app.manager where tenant_id <> 'bbbbbbbb-0000-0000-0000-000000000002'), 0);
  perform pg_temp.assert_eq('owner B não lê PII de A',
    (select count(*) from app.employee_pii where rg = 'MG-1'), 0);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- Supervisor de unit (tenant A, escopo só em A Centro)'
-- ---------------------------------------------------------------------------
set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';

do $$ begin
  perform pg_temp.assert_eq('supervisor vê só a unit dele',
    (select count(*) from public.vw_unit), 1);
  perform pg_temp.assert_eq('supervisor vê só o employee da unit dele',
    (select count(*) from public.vw_employee), 1);
  -- ⛔ ESTA É A ASSERÇÃO QUE FALTAVA, E A AUSÊNCIA DELA CUSTOU CARO.
  --    Todas as asserções de supervisor sobre desvio eram `= 0` — "não vê a
  --    outra unidade", "não vê sombra". Nenhuma exigia que ele VISSE algo, e por
  --    isso o rename pôde deixar `mode = 'producao'` dentro de `deviation_read`
  --    (migration 28) sem que nada ficasse vermelho: um supervisor que não vê
  --    NADA passa em todo teste que só verifica o que ele não deve ver.
  perform pg_temp.assert_eq('supervisor VÊ o desvio da unidade dele',
    (select count(*) from public.vw_deviation_event), 1);
  perform pg_temp.assert_eq('supervisor não vê desvio da unit A Norte',
    (select count(*) from public.vw_deviation_event where unit_name = 'A Norte'), 0);
  perform pg_temp.assert_eq('supervisor NÃO lê PII (ver unit não basta)',
    (select count(*) from app.employee_pii), 0);
  perform pg_temp.assert_eq('supervisor NÃO lê ocorrência disciplinar (a linha é de quem ele vê)',
    (select count(*) from app.disciplinary_event), 0);
  perform pg_temp.assert_eq('supervisor NÃO lê remuneração',
    (select count(*) from app.employee_compensation), 0);
  perform pg_temp.assert_eq('supervisor não vê evento em mode sombra',
    (select count(*) from app.deviation_event where mode = 'shadow'), 0);
  -- A policy do gestor tem o mesmo recorte da de unidade: ver o gestor é ver
  -- quem responde a ele. Sem isso, a chefia das outras unidades vazaria por uma
  -- tabela de dimensão, que é onde ninguém procura vazamento.
  perform pg_temp.assert_eq('supervisor vê só o gestor de quem ele enxerga',
    (select count(*) from app.manager), 1);
  perform pg_temp.assert_eq('e o ranking por gestor devolve só a linha dele',
    (select count(*) from public.fn_ranking_by_manager('2026-08-01','2026-08-31')), 1);
end $$;

-- ⛔ O QUADRO DE POSTOS PELO RECORTE DE UNIDADE — com o positivo ao lado.
--    `app.work_post` não concede nada a `authenticated`, então contar linhas
--    aqui devolveria `permission denied` para o supervisor tanto na unidade dele
--    quanto na outra: as duas negativas ficariam verdes e nenhuma falaria da
--    policy. O que se avalia é `work_post_read` como ela está no catálogo.
do $$ begin
  perform pg_temp.assert_eq('supervisor VÊ o posto da unidade dele (o positivo)',
    pg_temp.policy_says_on('work_post', 'work_post_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null,
      'a0000000-0000-0000-0000-0000000000a1'), 1);
  perform pg_temp.assert_eq('e NÃO vê o posto de A Norte (mesma unidade, outro escopo)',
    pg_temp.policy_says_on('work_post', 'work_post_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null,
      'a0000000-0000-0000-0000-0000000000a2'), 0);
  perform pg_temp.assert_eq('e nem o posto do tenant B',
    pg_temp.policy_says_on('work_post', 'work_post_read',
      'bbbbbbbb-0000-0000-0000-000000000002', null,
      'b0000000-0000-0000-0000-0000000000a1'), 0);
  -- Ler o quadro não é administrá-lo. Sem esta linha, `work_post_admin` poderia
  -- ter trocado `is_admin` por `can_see_unit` e nada ficaria vermelho.
  perform pg_temp.assert_eq('supervisor NÃO administra o quadro, nem o da unidade dele',
    pg_temp.policy_says_on('work_post', 'work_post_admin',
      'aaaaaaaa-0000-0000-0000-000000000001', null,
      'a0000000-0000-0000-0000-0000000000a1', 'with_check'), 0);
  -- O supervisor tem `compensation`? Não — e por isso ele não lê verba de
  -- ninguém, inclusive de quem ele enxerga. O par positivo deste é o do DP.
  perform pg_temp.assert_eq('supervisor NÃO lê verba de quem ele enxerga (falta o domínio)',
    pg_temp.policy_says_on('employee_benefit', 'employee_benefit_read',
      'aaaaaaaa-0000-0000-0000-000000000001',
      'a0000000-0000-0000-0000-0000000000c1', null), 0);
end $$;

-- ⛔ O S3 PELO SUPERVISOR — e aqui o par NÃO fecha pelo eixo de unidade.
--    `unit_supervisor` não tem NENHUM domínio sensível na matriz do produto
--    (migration 02), então `compensation` já o barra: ele não vê o ciclo da
--    unidade dele NEM o da outra. Registrar isso é o ponto — a negativa por
--    unidade seria uma afirmação sobre um eixo que nunca chega a ser avaliado.
--    Quem exerce o eixo de unidade nestas tabelas é o `accounting`, mais abaixo.
do $$ begin
  perform pg_temp.assert_eq('supervisor NÃO alcança o domínio compensation',
    case when util.can_see_domain('aaaaaaaa-0000-0000-0000-000000000001', 'compensation')
         then 1 else 0 end, 0);
  perform pg_temp.assert_eq('e por isso NÃO vê o ciclo do tenant dele',
    pg_temp.policy_says_on('benefit_cycle', 'benefit_cycle_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 0);
  -- O eixo de unidade nem chega a decidir: nem a linha da unidade DELE ele vê.
  perform pg_temp.assert_eq('nem o direito do colaborador da unidade DELE',
    pg_temp.policy_says_on('benefit_entitlement', 'benefit_entitlement_read',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1', null), 0);
  perform pg_temp.assert_eq('nem o do colaborador de A Norte',
    pg_temp.policy_says_on('benefit_entitlement', 'benefit_entitlement_read',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c2', null), 0);
  -- E a curadoria de justificativa é ato de administração: ele não a lê.
  perform pg_temp.assert_eq('supervisor NÃO lê a curadoria de justificativa',
    pg_temp.policy_says_on('leave_justification_map', 'leave_justification_map_admin',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 0);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- DP (tenant A): lê PII, não lê saúde'
-- ---------------------------------------------------------------------------
set local request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';

do $$ begin
  perform pg_temp.assert_eq('DP lê PII',
    (select count(*) from app.employee_pii), 1);
  -- ⛔ O par da foto imputada, e ele é DIFERENTE dos outros domínios: aqui nem
  --    quem TEM `pii` alcança, porque a barreira é o GRANT e não a policy. O
  --    positivo correspondente é o backend (`service_role`), afirmado no bloco
  --    de prova da migration 36 — aqui prova-se que a porta do navegador está
  --    fechada mesmo para o papel mais habilitado.
  perform pg_temp.assert_eq('DP tem pii e AINDA ASSIM não alcança a foto imputada',
    (select count(*) from pg_catalog.has_table_privilege(
       'authenticated', 'app.employee_photo', 'SELECT') as t(p) where p), 0);
  perform pg_temp.assert_eq('DP LÊ ocorrência disciplinar',
    (select count(*) from app.disciplinary_event), 1);
  perform pg_temp.assert_eq('DP NÃO lê exame ocupacional (domínio saúde)',
    (select count(*) from app.occupational_exam), 0);
  perform pg_temp.assert_eq('DP vê os 2 colaboradores do tenant',
    (select count(*) from public.vw_employee), 2);
end $$;

-- ⛔ O POSITIVO do domínio `banking`, e é ele que faz o negativo do RH valer
--    alguma coisa. A conta bancária é o Caminho 2 puro: nem o DP a lê pelo
--    navegador, porque não há grant. O que se prova aqui é o que o backend
--    pergunta ao banco antes de responder — o domínio, e a policy inteira
--    avaliada como ela está no catálogo.
do $$ begin
  perform pg_temp.assert_eq('DP alcança o domínio banking (é quem monta a remessa)',
    case when util.can_see_domain('aaaaaaaa-0000-0000-0000-000000000001', 'banking')
         then 1 else 0 end, 1);
  perform pg_temp.assert_eq('e a policy de LEITURA da conta diz sim para o DP',
    pg_temp.policy_says('employee_bank_account_read',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1'), 1);
  -- A de escrita, nas DUAS expressões: o `with check` é quem decide o INSERT, e o
  -- `using` é quem decide se o UPDATE acha a linha. O DP é admin, então as duas
  -- dizem sim.
  perform pg_temp.assert_eq('a de ESCRITA diz sim no with check (o DP é admin)',
    pg_temp.policy_says('employee_bank_account_write',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1',
      'with_check'), 1);
  perform pg_temp.assert_eq('e no using também',
    pg_temp.policy_says('employee_bank_account_write',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1',
      'qual'), 1);
  -- Ter o domínio não atravessa tenant: o eixo do domínio é por tenant, e o DP
  -- de A não é membro de B.
  perform pg_temp.assert_eq('e nem por isso o DP de A alcança a conta do tenant B',
    pg_temp.policy_says('employee_bank_account_read',
      'bbbbbbbb-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-0000000000c1'), 0);
end $$;

-- ⛔ O POSITIVO do domínio `compensation`, e é ele que faz o negativo do RH
--    (logo abaixo) valer alguma coisa. Sem esta asserção, "o hr não lê verba"
--    ficaria verde numa policy que diz não para TODO MUNDO.
do $$ begin
  perform pg_temp.assert_eq('DP alcança o domínio compensation',
    case when util.can_see_domain('aaaaaaaa-0000-0000-0000-000000000001', 'compensation')
         then 1 else 0 end, 1);
  perform pg_temp.assert_eq('e a policy de LEITURA da verba diz SIM para o DP',
    pg_temp.policy_says_on('employee_benefit', 'employee_benefit_read',
      'aaaaaaaa-0000-0000-0000-000000000001',
      'a0000000-0000-0000-0000-0000000000c1', null), 1);
  -- Escrita: o DP é admin, então os três eixos dizem sim — e o `with check` é
  -- quem decide o INSERT.
  perform pg_temp.assert_eq('e a de ESCRITA também, no with check (o DP é admin)',
    pg_temp.policy_says_on('employee_benefit', 'employee_benefit_write',
      'aaaaaaaa-0000-0000-0000-000000000001',
      'a0000000-0000-0000-0000-0000000000c1', null, 'with_check'), 1);
  -- Ter o domínio não atravessa tenant.
  perform pg_temp.assert_eq('e o DP de A não alcança a verba do tenant B',
    pg_temp.policy_says_on('employee_benefit', 'employee_benefit_read',
      'bbbbbbbb-0000-0000-0000-000000000002',
      'b0000000-0000-0000-0000-0000000000c1', null), 0);
  -- O catálogo do tenant: o DP lê, e é o par positivo do isolamento entre
  -- clientes conferido logo em seguida.
  perform pg_temp.assert_eq('DP lê o catálogo de verbas do tenant dele',
    pg_temp.policy_says_on('benefit_type', 'benefit_type_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 1);
  perform pg_temp.assert_eq('e NÃO o catálogo do tenant B',
    pg_temp.policy_says_on('benefit_type', 'benefit_type_read',
      'bbbbbbbb-0000-0000-0000-000000000002', null, null), 0);
  -- As TRÊS, e não só `benefit_type`: elas foram apertadas no mesmo commit, e
  -- nada obriga as três a andarem juntas na próxima mudança. Conferir uma e
  -- afirmar as três é a extrapolação que este arquivo não faz.
  perform pg_temp.assert_eq('DP lê benefit_plan (preço do plano de saúde)',
    pg_temp.policy_says_on('benefit_plan', 'benefit_plan_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 1);
  perform pg_temp.assert_eq('DP lê transport_fare (tarifa de VT)',
    pg_temp.policy_says_on('transport_fare', 'transport_fare_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 1);
end $$;

-- ⛔ O S3 PELO DP — o POSITIVO das três tabelas, sem o qual todas as negativas
--    acima ficariam verdes num conjunto de policies que diz não para todo mundo.
do $$ begin
  perform pg_temp.assert_eq('DP LÊ o ciclo do tenant dele',
    pg_temp.policy_says_on('benefit_cycle', 'benefit_cycle_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 1);
  perform pg_temp.assert_eq('e NÃO o ciclo do tenant B',
    pg_temp.policy_says_on('benefit_cycle', 'benefit_cycle_read',
      'bbbbbbbb-0000-0000-0000-000000000002', null, null), 0);
  -- Apurar ciclo é ato de administração, e o DP é admin.
  perform pg_temp.assert_eq('DP APURA (with check do admin do ciclo)',
    pg_temp.policy_says_on('benefit_cycle', 'benefit_cycle_admin',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null, 'with_check'), 1);

  perform pg_temp.assert_eq('DP LÊ o direito do colaborador de A Centro',
    pg_temp.policy_says_on('benefit_entitlement', 'benefit_entitlement_read',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1', null), 1);
  perform pg_temp.assert_eq('e o de A Norte (ele é admin: enxerga o tenant inteiro)',
    pg_temp.policy_says_on('benefit_entitlement', 'benefit_entitlement_read',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c2', null), 1);
  perform pg_temp.assert_eq('e NÃO o do tenant B',
    pg_temp.policy_says_on('benefit_entitlement', 'benefit_entitlement_read',
      'bbbbbbbb-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-0000000000c1', null), 0);
  perform pg_temp.assert_eq('e ESCREVE a linha (with check, os três eixos)',
    pg_temp.policy_says_on('benefit_entitlement', 'benefit_entitlement_write',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1', null, 'with_check'), 1);

  -- A curadoria: o DP é quem a mantém. Este é o par positivo do "ninguém que
  -- não seja admin lê a curadoria" medido no accounting mais abaixo.
  perform pg_temp.assert_eq('DP LÊ a curadoria de justificativa',
    pg_temp.policy_says_on('leave_justification_map', 'leave_justification_map_admin',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 1);
  perform pg_temp.assert_eq('e ESCREVE nela (with check)',
    pg_temp.policy_says_on('leave_justification_map', 'leave_justification_map_admin',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null, 'with_check'), 1);
  perform pg_temp.assert_eq('e NÃO a do tenant B',
    pg_temp.policy_says_on('leave_justification_map', 'leave_justification_map_admin',
      'bbbbbbbb-0000-0000-0000-000000000002', null, null), 0);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- RH (tenant A): enxerga a pessoa e NÃO alcança conta bancária'
-- ---------------------------------------------------------------------------
set local request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';

do $$
declare
  v_negado boolean := false;
begin
  -- O gate da sprint na forma literal dele. O erro vem do GRANT, não da policy —
  -- e é por isso que as três asserções seguintes existem: sem elas, "hr não lê"
  -- seria verdade sobre todo mundo e não diria nada sobre o domínio.
  begin
    perform 1 from app.employee_bank_account;
  exception when insufficient_privilege then
    v_negado := true;
  end;
  perform pg_temp.assert_eq('hr recebe permission denied em app.employee_bank_account',
    case when v_negado then 1 else 0 end, 1);

  -- O que barra o RH é o DOMÍNIO, não o escopo: ele é admin e enxerga a pessoa.
  perform pg_temp.assert_eq('hr ENXERGA a pessoa (o que o barra é o domínio, não o escopo)',
    case when util.can_see_employee('a0000000-0000-0000-0000-0000000000c1')
         then 1 else 0 end, 1);
  perform pg_temp.assert_eq('hr NÃO alcança o domínio banking',
    case when util.can_see_domain('aaaaaaaa-0000-0000-0000-000000000001', 'banking')
         then 1 else 0 end, 0);
  perform pg_temp.assert_eq('e a policy de leitura da conta diz NÃO para o hr',
    pg_temp.policy_says('employee_bank_account_read',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1'), 0);
  perform pg_temp.assert_eq('a de escrita também diz NÃO, no with check',
    pg_temp.policy_says('employee_bank_account_write',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1',
      'with_check'), 0);
end $$;

-- ⛔ O NEGATIVO do domínio `compensation`, no par do positivo do DP acima.
--    O RH é admin e ENXERGA a pessoa (já provado no bloco da conta bancária):
--    a única coisa que pode barrá-lo na verba é o domínio.
do $$ begin
  perform pg_temp.assert_eq('hr NÃO alcança o domínio compensation',
    case when util.can_see_domain('aaaaaaaa-0000-0000-0000-000000000001', 'compensation')
         then 1 else 0 end, 0);
  perform pg_temp.assert_eq('e a policy de leitura da verba diz NÃO para o hr',
    pg_temp.policy_says_on('employee_benefit', 'employee_benefit_read',
      'aaaaaaaa-0000-0000-0000-000000000001',
      'a0000000-0000-0000-0000-0000000000c1', null), 0);
  perform pg_temp.assert_eq('e a de escrita também, no with check (é admin, e ainda assim não)',
    pg_temp.policy_says_on('employee_benefit', 'employee_benefit_write',
      'aaaaaaaa-0000-0000-0000-000000000001',
      'a0000000-0000-0000-0000-0000000000c1', null, 'with_check'), 0);

  -- ⛔ ESTA ASSERÇÃO MUDOU DE NATUREZA EM 06/09/2026, e o rótulo mudou com ela.
  --    Ela nasceu registrando uma LACUNA medida: as três tabelas de catálogo
  --    (`benefit_type`, `benefit_plan`, `transport_fare`) liam por
  --    `util.has_tenant`, SEM domínio, e a policy dizia SIM para o hr — quem
  --    barrava era só a rota (`permissoes.compensation`). O comentário anterior
  --    dizia, com todas as letras, que trocar o `1` por `0` seria a correção.
  --    A decisão do dono de 06/09 igualou policy e rota, e a troca aconteceu.
  --    Então o que era REGISTRO DE LACUNA passa a ser GARANTIA: o hr é barrado
  --    no banco, pela policy, e não mais só pelo código da rota. Manter o rótulo
  --    antigo com o valor novo faria o arquivo afirmar o oposto do que mede.
  --    ⚠️ As TRÊS são conferidas. Apertar uma e esquecer as outras duas é
  --    exatamente o erro que uma asserção só não pega.
  perform pg_temp.assert_eq('hr é barrado no catálogo PELA POLICY (benefit_type)',
    pg_temp.policy_says_on('benefit_type', 'benefit_type_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 0);
  perform pg_temp.assert_eq('idem benefit_plan (preço do plano de saúde)',
    pg_temp.policy_says_on('benefit_plan', 'benefit_plan_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 0);
  perform pg_temp.assert_eq('idem transport_fare (tarifa de VT)',
    pg_temp.policy_says_on('transport_fare', 'transport_fare_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 0);
  -- E o que a policy do catálogo SEPARA de verdade é o tenant e a escrita.
  perform pg_temp.assert_eq('o catálogo do tenant B continua fora do alcance do hr de A',
    pg_temp.policy_says_on('benefit_type', 'benefit_type_read',
      'bbbbbbbb-0000-0000-0000-000000000002', null, null), 0);
end $$;

-- ⛔ O S3 PELO RH — e ele separa DOIS eixos que andam juntos em todo lugar.
--    O hr é admin (`util.is_admin`) e NÃO tem `compensation`. Então ele é
--    barrado no ciclo e no direito (falta o domínio) e PASSA na curadoria
--    (basta ser admin). Sem as duas metades, "o hr é barrado no S3" seria falso.
do $$ begin
  perform pg_temp.assert_eq('hr é admin',
    case when util.is_admin('aaaaaaaa-0000-0000-0000-000000000001') then 1 else 0 end, 1);
  perform pg_temp.assert_eq('hr NÃO vê o ciclo (é admin, e ainda assim não: falta o domínio)',
    pg_temp.policy_says_on('benefit_cycle', 'benefit_cycle_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 0);
  perform pg_temp.assert_eq('hr NÃO vê o direito de quem ele ENXERGA',
    pg_temp.policy_says_on('benefit_entitlement', 'benefit_entitlement_read',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1', null), 0);
  perform pg_temp.assert_eq('e a escrita da linha também diz NÃO',
    pg_temp.policy_says_on('benefit_entitlement', 'benefit_entitlement_write',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1', null, 'with_check'), 0);
  -- A OUTRA metade: a curadoria é do admin, e o hr passa. Uma policy que
  -- dissesse não aqui trancaria o RH fora do cadastro que ele mantém.
  perform pg_temp.assert_eq('hr LÊ a curadoria (ela é do admin, e ele é admin)',
    pg_temp.policy_says_on('leave_justification_map', 'leave_justification_map_admin',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 1);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- Contabilidade (tenant A): LÊ a conta e NÃO escreve nela'
-- ---------------------------------------------------------------------------
-- O papel que a decisão de 05/09 separa, e o único do produto em que ler e
-- escrever divergem por causa do TERCEIRO eixo. Ele tem `banking` (concilia a
-- remessa) e não está em `util.is_admin` (`owner`, `hr`, `personnel`).
--
-- ⚠️ Os três primeiros itens não são cerimônia: são o que torna o quinto uma
--    prova. Com domínio SIM, pessoa SIM e admin NÃO, a única diferença possível
--    entre a leitura passar e a escrita falhar é `util.is_admin`. Sem eles, a
--    negativa passaria por qualquer motivo — inclusive por um escopo vazio.
set local request.jwt.claim.sub = '66666666-6666-6666-6666-666666666666';

do $$ begin
  perform pg_temp.assert_eq('accounting ALCANÇA o domínio banking',
    case when util.can_see_domain('aaaaaaaa-0000-0000-0000-000000000001', 'banking')
         then 1 else 0 end, 1);
  perform pg_temp.assert_eq('accounting ENXERGA a pessoa (escopo do tenant inteiro)',
    case when util.can_see_employee('a0000000-0000-0000-0000-0000000000c1')
         then 1 else 0 end, 1);
  perform pg_temp.assert_eq('accounting NÃO é admin',
    case when util.is_admin('aaaaaaaa-0000-0000-0000-000000000001')
         then 1 else 0 end, 0);

  -- O POSITIVO: a leitura continua com dois eixos, e é dela que a conciliação da
  -- remessa vive. Endurecer a policy de leitura trancaria o accounting fora do
  -- próprio trabalho — esta asserção é o que impede essa "melhoria".
  perform pg_temp.assert_eq('a policy de LEITURA da conta diz SIM para o accounting',
    pg_temp.policy_says('employee_bank_account_read',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1'), 1);

  -- O NEGATIVO, avaliado onde ele decide. Num INSERT quem responde é o
  -- `with check`; pedir a `qual` aqui seria acertar por os dois textos serem
  -- iguais hoje.
  perform pg_temp.assert_eq('a de ESCRITA diz NÃO no with check (tem banking, não é admin)',
    pg_temp.policy_says('employee_bank_account_write',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1',
      'with_check'), 0);
  perform pg_temp.assert_eq('e diz NÃO no using (o UPDATE não alcança a linha)',
    pg_temp.policy_says('employee_bank_account_write',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1',
      'qual'), 0);

  -- E o `permission denied` continua valendo para ele também: a tabela é Caminho
  -- 2 puro. É por isso que a policy acima é avaliada, e não consultada.
  perform pg_temp.assert_eq('accounting NÃO alcança a tabela pelo PostgREST',
    (select count(*) from unnest(array['SELECT','INSERT','UPDATE','DELETE']) v
      where has_table_privilege('authenticated', 'app.employee_bank_account', v)), 0);

  -- ⛔ O OUTRO POSITIVO do aperto de 06/09, e o que ele protege é o trabalho
  --    deste papel. `accounting` tem `compensation` na matriz do produto: exigir
  --    o domínio no catálogo barra o hr SEM barrar quem concilia a folha. Se um
  --    dia esta linha ficar vermelha, o aperto passou do ponto e a conciliação
  --    perdeu a tabela de preços — que é o dano que "barrar o legítimo" nomeia.
  perform pg_temp.assert_eq('accounting ALCANÇA o domínio compensation (matriz do produto)',
    case when util.can_see_domain('aaaaaaaa-0000-0000-0000-000000000001', 'compensation')
         then 1 else 0 end, 1);
  perform pg_temp.assert_eq('e LÊ o catálogo: benefit_type',
    pg_temp.policy_says_on('benefit_type', 'benefit_type_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 1);
  perform pg_temp.assert_eq('e benefit_plan',
    pg_temp.policy_says_on('benefit_plan', 'benefit_plan_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 1);
  perform pg_temp.assert_eq('e transport_fare',
    pg_temp.policy_says_on('transport_fare', 'transport_fare_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 1);
  -- Ler o catálogo não é editá-lo: o preço continua sendo ato de administração.
  perform pg_temp.assert_eq('e NÃO o administra (não é admin)',
    pg_temp.policy_says_on('benefit_type', 'benefit_type_admin',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null, 'with_check'), 0);
end $$;

-- ⛔ O S3 PELO ACCOUNTING — e é AQUI que o eixo de unidade das tabelas do S3
--    é de fato exercido. O `unit_supervisor` não serve para isso: ele não tem
--    `compensation` e morre no primeiro conjunto. O `accounting` tem o domínio
--    e NÃO está na lista curta de `util.can_see_unit`
--    (`owner`,`executive`,`hr`,`personnel`), então o escopo dele é o que
--    `app.user_scope` disser — que é a única combinação do produto em que
--    `can_see_employee` decide alguma coisa nestas tabelas.
do $$ begin
  perform pg_temp.assert_eq('accounting LÊ o ciclo (tem compensation)',
    pg_temp.policy_says_on('benefit_cycle', 'benefit_cycle_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 1);
  perform pg_temp.assert_eq('e NÃO o do tenant B',
    pg_temp.policy_says_on('benefit_cycle', 'benefit_cycle_read',
      'bbbbbbbb-0000-0000-0000-000000000002', null, null), 0);
  -- Conciliar não é apurar: o ciclo é do DP.
  perform pg_temp.assert_eq('accounting NÃO apura ciclo (não é admin)',
    pg_temp.policy_says_on('benefit_cycle', 'benefit_cycle_admin',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null, 'with_check'), 0);

  -- Escopo do tenant inteiro: ele vê as DUAS unidades. Este é o positivo do
  -- recorte que o savepoint abaixo estreita.
  perform pg_temp.assert_eq('com escopo do tenant, LÊ o direito de A Centro',
    pg_temp.policy_says_on('benefit_entitlement', 'benefit_entitlement_read',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1', null), 1);
  perform pg_temp.assert_eq('e o de A Norte',
    pg_temp.policy_says_on('benefit_entitlement', 'benefit_entitlement_read',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c2', null), 1);
  perform pg_temp.assert_eq('e NÃO escreve a linha (não é admin)',
    pg_temp.policy_says_on('benefit_entitlement', 'benefit_entitlement_write',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1', null, 'with_check'), 0);

  -- ⛔ A CONSEQUÊNCIA DA POLICY ÚNICA DE `leave_justification_map`, medida e não
  --    suposta: ela é `ALL` com `is_admin`, exatamente como
  --    `app.payroll_event_map` (migration 30). Então quem tem `compensation` e
  --    não é admin NÃO lê a curadoria — o accounting concilia a folha sem
  --    enxergar o mapa que classificou as faltas dela.
  --    Isto é o desenho herdado, não uma diferença que passou; e está registrado
  --    aqui para que a próxima mudança seja uma decisão e não um acidente.
  perform pg_temp.assert_eq('accounting NÃO lê a curadoria (é o desenho de payroll_event_map)',
    pg_temp.policy_says_on('leave_justification_map', 'leave_justification_map_admin',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 0);
end $$;

-- ⛔ O EIXO DE UNIDADE, ESTREITANDO O ESCOPO — o par que faltava.
--    Sem isto, `can_see_employee` em `benefit_entitlement_read` nunca é
--    exercido como discriminador: todo mundo que passa no domínio, neste
--    cenário, enxerga o tenant inteiro. A policy poderia ter perdido o segundo
--    conjunto e nada ficaria vermelho.
savepoint prova_do_recorte;

reset role;
update app.user_scope
   set unit_id = 'a0000000-0000-0000-0000-0000000000a1'
 where user_id = '66666666-6666-6666-6666-666666666666';
set local role authenticated;
set local request.jwt.claim.sub = '66666666-6666-6666-6666-666666666666';

do $$ begin
  perform pg_temp.assert_eq('recortado em A Centro, o accounting VÊ o direito de A Centro',
    pg_temp.policy_says_on('benefit_entitlement', 'benefit_entitlement_read',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c1', null), 1);
  perform pg_temp.assert_eq('e NÃO vê o de A Norte (o eixo de unidade decide)',
    pg_temp.policy_says_on('benefit_entitlement', 'benefit_entitlement_read',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c2', null), 0);
  -- E o cabeçalho do ciclo continua visível: ele é do TENANT, não da unidade.
  -- Registrado de propósito — quem ler "supervisor não vê ciclo de outra
  -- unidade" precisa saber que o ciclo não tem eixo de unidade nenhum.
  perform pg_temp.assert_eq('o CICLO não tem eixo de unidade: segue visível',
    pg_temp.policy_says_on('benefit_cycle', 'benefit_cycle_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 1);
end $$;

rollback to savepoint prova_do_recorte;

do $$ begin
  perform pg_temp.assert_eq('desfeito o recorte, A Norte volta ao alcance',
    pg_temp.policy_says_on('benefit_entitlement', 'benefit_entitlement_read',
      'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000c2', null), 1);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- Laudo de unidade (S5) — a primeira tabela do DP que chega ao navegador'
-- ---------------------------------------------------------------------------
-- ⛔ POR QUE ESTA SEÇÃO É DIFERENTE DAS OUTRAS DESTE ARQUIVO
-- `app.unit_compliance_report` é a primeira tabela da etapa DP com `grant
-- select` para `authenticated`, porque `public.vw_unit_compliance` é
-- `security_invoker` e uma view invoker sobre tabela sem grant devolve
-- `permission denied for table`, não linha filtrada. Consequência: a policy
-- `unit_compliance_report_read` deixou de ser defesa em profundidade e passou a
-- ser A fronteira — é ela, e mais nada, que decide o que a tela mostra.
--
-- ⛔ E POR QUE A FORMA "SUPERVISOR VÊ 1 E NÃO VÊ 0" NÃO BASTA SOZINHA
-- "supervisor não vê o laudo de A Norte = 0" fica verde de três jeitos errados:
--   (a) não existe laudo em A Norte para ver;
--   (b) a policy recusa todo mundo, e ninguém vê nada;
--   (c) a view filtra por vigência e o zero veio dali, não da policy.
-- É o mesmo falso verde que deixou `mode = 'producao'` entrar em
-- `deviation_read` — um supervisor que não vê NADA passa em todo teste que só
-- verifica o que ele não deve ver.
-- Então cada zero aqui tem uma TESTEMUNHA ao lado: o DP do mesmo tenant lê os
-- laudos de A Norte (2), o que prova que existe linha lá para vazar; e as
-- contagens de A Centro são DIFERENTES na view (1, vigente) e na tabela (2, a
-- cadeia inteira), o que separa o recorte da policy do filtro de vigência.

reset role;
-- A Centro: um laudo e a renovação dele — 2 linhas na tabela, 1 vigente na view.
insert into app.unit_compliance_report (id, tenant_id, unit_id, type, valid_until) values
  ('cc000000-0000-0000-0000-0000000000c1', 'aaaaaaaa-0000-0000-0000-000000000001',
   'a0000000-0000-0000-0000-0000000000a1', 'PCMSO', date '2027-01-31');
insert into app.unit_compliance_report (tenant_id, unit_id, type, valid_until, replaces_id) values
  ('aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000a1',
   'PCMSO', date '2028-01-31', 'cc000000-0000-0000-0000-0000000000c1');
-- A Norte: DOIS laudos vigentes, de tipos diferentes. São a testemunha dos zeros
-- do supervisor: contagem 2 num lugar e 0 no outro não se confunde com tabela
-- vazia nem com policy que recusa todo mundo.
insert into app.unit_compliance_report (tenant_id, unit_id, type, valid_until) values
  ('aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000a2', 'PCMSO', date '2027-03-31'),
  ('aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000a2', 'PGR',   date '2027-04-30');
-- Tenant B, para o eixo que este arquivo existe para guardar.
insert into app.unit_compliance_report (tenant_id, unit_id, type, valid_until) values
  ('bbbbbbbb-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-0000000000a1', 'PCMSO', date '2027-05-31');

set local role authenticated;

-- --- o supervisor de A Centro: o positivo primeiro, depois os zeros ---------
set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';

do $$ begin
  -- O POSITIVO. Sem ele os três zeros abaixo não valem nada.
  perform pg_temp.assert_eq('supervisor VÊ o laudo vigente da unidade dele (view)',
    (select count(*) from public.vw_unit_compliance where unit_name = 'A Centro'), 1);
  perform pg_temp.assert_eq('supervisor NÃO vê o laudo de A Norte (view)',
    (select count(*) from public.vw_unit_compliance where unit_name = 'A Norte'), 0);
  perform pg_temp.assert_eq('supervisor não vê laudo de OUTRO TENANT (view)',
    (select count(*) from public.vw_unit_compliance where unit_name = 'B Sul'), 0);
  perform pg_temp.assert_eq('e a view inteira, para ele, é só o laudo dele',
    (select count(*) from public.vw_unit_compliance), 1);

  -- A MESMA pergunta na TABELA, que é onde a policy mora. A view poderia perder
  -- o `security_invoker` amanhã e passar a rodar como dona: a asserção de view
  -- pegaria isso, e esta pega o contrário — uma policy afrouxada por baixo de
  -- uma view que continua correta.
  -- ⚠️ 2, e não 1: na tabela ele alcança a CADEIA de A Centro (original +
  -- renovação). O número ser diferente do da view é de propósito — é o que
  -- prova que o 1 de lá veio do filtro de vigência e o recorte veio daqui.
  perform pg_temp.assert_eq('supervisor ALCANÇA a tabela e lê a cadeia de A Centro',
    (select count(*) from app.unit_compliance_report
      where unit_id = 'a0000000-0000-0000-0000-0000000000a1'), 2);
  perform pg_temp.assert_eq('supervisor NÃO lê laudo de A Norte na tabela',
    (select count(*) from app.unit_compliance_report
      where unit_id = 'a0000000-0000-0000-0000-0000000000a2'), 0);
  perform pg_temp.assert_eq('supervisor NÃO lê laudo do tenant B na tabela',
    (select count(*) from app.unit_compliance_report
      where tenant_id = 'bbbbbbbb-0000-0000-0000-000000000002'), 0);

  -- A escrita continua no Caminho 2: o navegador lê e só. Conceder `select` para
  -- a view funcionar não pode ter trazido verbo junto.
  perform pg_temp.assert_eq('authenticated LÊ a tabela (é o que faz a view invoker funcionar)',
    has_table_privilege('authenticated', 'app.unit_compliance_report', 'SELECT')::int::bigint, 1);
  perform pg_temp.assert_eq('e NÃO insere',
    has_table_privilege('authenticated', 'app.unit_compliance_report', 'INSERT')::int::bigint, 0);
  perform pg_temp.assert_eq('e NÃO atualiza',
    has_table_privilege('authenticated', 'app.unit_compliance_report', 'UPDATE')::int::bigint, 0);
  perform pg_temp.assert_eq('e NÃO apaga (laudo não se apaga, renova-se — regra 6)',
    has_table_privilege('authenticated', 'app.unit_compliance_report', 'DELETE')::int::bigint, 0);
end $$;

-- --- a TESTEMUNHA: o DP do mesmo tenant lê o que o supervisor não lê ---------
-- Sem este bloco, todo zero acima é compatível com "não há laudo em A Norte" e
-- com "a policy recusa todo mundo".
set local request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';

do $$ begin
  perform pg_temp.assert_eq('o DP VÊ os dois laudos de A Norte — os zeros do supervisor são recorte, não vazio',
    (select count(*) from public.vw_unit_compliance where unit_name = 'A Norte'), 2);
  perform pg_temp.assert_eq('e também o de A Centro',
    (select count(*) from public.vw_unit_compliance where unit_name = 'A Centro'), 1);
  perform pg_temp.assert_eq('o DP vê o tenant A inteiro, e só ele',
    (select count(*) from public.vw_unit_compliance), 3);
  perform pg_temp.assert_eq('o DP NÃO vê o laudo do tenant B',
    (select count(*) from public.vw_unit_compliance where unit_name = 'B Sul'), 0);
end $$;

-- --- e o outro tenant enxerga o dele, que é o par positivo do eixo de tenant --
set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';

do $$ begin
  perform pg_temp.assert_eq('o owner do tenant B VÊ o laudo dele',
    (select count(*) from public.vw_unit_compliance where unit_name = 'B Sul'), 1);
  perform pg_temp.assert_eq('e nenhum do tenant A',
    (select count(*) from public.vw_unit_compliance where unit_name like 'A %'), 0);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- Usuário autenticado sem vínculo com nenhum tenant'
-- ---------------------------------------------------------------------------
set local request.jwt.claim.sub = '99999999-9999-9999-9999-999999999999';

do $$ begin
  perform pg_temp.assert_eq('usuário sem tenant não vê employee',
    (select count(*) from public.vw_employee), 0);
  perform pg_temp.assert_eq('usuário sem tenant não vê desvio',
    (select count(*) from public.vw_deviation_event), 0);
  perform pg_temp.assert_eq('usuário sem tenant não vê unit',
    (select count(*) from public.vw_unit), 0);
end $$;

reset role;

\echo ''
\echo '================================================'
\echo ' ISOLAMENTO MULTI-TENANT: TODOS OS TESTES OK'
\echo '================================================'

rollback;
