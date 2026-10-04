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

-- Os ids são explícitos desde 09/09/2026 porque o veredito do censo aponta para
-- um evento pelo id, e a asserção precisa nomear qual.
insert into app.deviation_event (id, tenant_id, employee_id, company_id, unit_id, reference_date, type, minutes, mode) values
  ('a0000000-0000-0000-0000-00000000ad01','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c1','a0000000-0000-0000-0000-0000000000e1','a0000000-0000-0000-0000-0000000000a1','2026-08-10','late_entry',-15,'production'),
  ('a0000000-0000-0000-0000-00000000ad02','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c2','a0000000-0000-0000-0000-0000000000e1','a0000000-0000-0000-0000-0000000000a2','2026-08-10','late_entry',-22,'production'),
  ('a0000000-0000-0000-0000-00000000ad03','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c1','a0000000-0000-0000-0000-0000000000e1','a0000000-0000-0000-0000-0000000000a1','2026-08-11','late_exit', 40,'shadow'),
  ('b0000000-0000-0000-0000-00000000ad04','bbbbbbbb-0000-0000-0000-000000000002','b0000000-0000-0000-0000-0000000000c1','b0000000-0000-0000-0000-0000000000e1','b0000000-0000-0000-0000-0000000000a1','2026-08-10','late_entry',-99,'production');

-- O censo de adjudicação (migration 37). Uma linha em CADA tenant: sem a de B,
-- "o owner de A não vê o veredito de B" ficaria verde num universo onde só
-- existe A, que é o falso verde que este arquivo existe para não repetir.
insert into app.deviation_adjudication (tenant_id, deviation_event_id, verdict, cause, author_name) values
  ('aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-00000000ad03','false_positive','exempt_from_punching','Censo A'),
  ('bbbbbbbb-0000-0000-0000-000000000002','b0000000-0000-0000-0000-00000000ad04','true_positive',null,'Censo B');

-- A liberação da entrega (migration 38). Uma em cada tenant, pelo mesmo motivo
-- do censo: sem a de B, "A não vê a liberação de B" seria verde no vácuo.
insert into app.alert_release (tenant_id, released_by, census_size, judged, false_positives, measured_rate) values
  ('aaaaaaaa-0000-0000-0000-000000000001', 'Owner A', 100, 100, 3, 3.00),
  ('bbbbbbbb-0000-0000-0000-000000000002', 'Owner B', 50, 50, 1, 2.00);

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

-- --- a MESMA prova, pela grafia de claim que o PostgREST realmente manda ------
-- ⛔ O resto deste arquivo injeta identidade com `request.jwt.claim.sub`, e o
-- PostgREST manda `request.jwt.claims`, um JSON. As duas grafias chegam à mesma
-- pessoa porque `auth.uid()` faz `coalesce` das duas — em produção e, desde
-- 12/09/2026, também no stub do ensaio, que era mais estreito que o de verdade.
--
-- Esta é a única asserção do arquivo que exercita o segundo ramo, e ela existe
-- porque a falha dele é MUDA: `auth.uid()` nulo não estoura, devolve zero linha,
-- e zero linha é indistinguível de recorte funcionando. O positivo é o que
-- separa os dois — por isso aqui se conta 1, e não 0.
reset request.jwt.claim.sub;
set local request.jwt.claims = '{"sub":"22222222-2222-2222-2222-222222222222","role":"authenticated"}';

do $$ begin
  perform pg_temp.assert_eq('auth.uid() responde pela grafia JSON do PostgREST',
    (select count(*) from public.vw_unit_compliance where unit_name = 'A Centro'), 1);
  perform pg_temp.assert_eq('e o recorte continua valendo por essa grafia',
    (select count(*) from public.vw_unit_compliance where unit_name = 'A Norte'), 0);
end $$;

reset request.jwt.claims;

-- ---------------------------------------------------------------------------
\echo '--- O censo de adjudicação (migration 37) — quem julga o indício em sombra'
-- ---------------------------------------------------------------------------
-- A policy é `util.is_admin`, autorizada pelo dono em 09/09/2026, e o conjunto
-- que ela nomeia é o MESMO que `deviation_read` já deixa ver evento em sombra:
-- owner, hr e personnel. As asserções abaixo existem para que essa frase pare
-- de ser uma leitura da policy e passe a ser uma medição — os três que podem
-- contam 1, os dois que não podem contam 0, e o de fora conta 0 por outro
-- motivo (tenant), que é a diferença que um teste só-negativo não enxerga.

set local role authenticated;
set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
do $$ begin
  perform pg_temp.assert_eq('owner A LÊ o veredito do tenant dele',
    (select count(*) from app.deviation_adjudication), 1);
  perform pg_temp.assert_eq('e o veredito que ele lê é o do evento em sombra dele',
    (select count(*) from app.deviation_adjudication
      where deviation_event_id = 'a0000000-0000-0000-0000-00000000ad03'), 1);
end $$;

set local request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
do $$ begin
  perform pg_temp.assert_eq('DP lê o veredito (é quem faz o censo)',
    (select count(*) from app.deviation_adjudication), 1);
end $$;

set local request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
do $$ begin
  -- ⚠️ Esta é a asserção que fixa a decisão do dono. `util.is_admin` inclui
  --    `hr`, então RH julga. Trocar a policy para {owner, personnel} deixa esta
  --    linha vermelha, que é exatamente o aviso que se quer.
  perform pg_temp.assert_eq('RH lê o veredito — util.is_admin o inclui, e a decisão foi essa',
    (select count(*) from app.deviation_adjudication), 1);
end $$;

set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
do $$
declare v_barrou boolean := false;
begin
  perform pg_temp.assert_eq('supervisor NÃO lê veredito (não é admin, e não vê o evento)',
    (select count(*) from app.deviation_adjudication), 0);
  -- O eixo de escrita, que a contagem acima não alcança: sem isto, um
  -- `with check` afrouxado passaria verde enquanto o `using` segurasse a leitura.
  begin
    insert into app.deviation_adjudication (tenant_id, deviation_event_id, verdict)
    values ('aaaaaaaa-0000-0000-0000-000000000001',
            'a0000000-0000-0000-0000-00000000ad01', 'true_positive');
  exception when insufficient_privilege then
    v_barrou := true;
  end;
  perform pg_temp.assert_eq('supervisor NÃO grava veredito (with check da policy)',
    case when v_barrou then 1 else 0 end, 1);
end $$;

set local request.jwt.claim.sub = '66666666-6666-6666-6666-666666666666';
do $$ begin
  perform pg_temp.assert_eq('contabilidade NÃO lê veredito (tem domínio, não é admin)',
    (select count(*) from app.deviation_adjudication), 0);
end $$;

set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$ begin
  perform pg_temp.assert_eq('owner B lê só o veredito dele',
    (select count(*) from app.deviation_adjudication), 1);
  perform pg_temp.assert_eq('owner B não lê o veredito de A',
    (select count(*) from app.deviation_adjudication
      where deviation_event_id = 'a0000000-0000-0000-0000-00000000ad03'), 0);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- A liberação da entrega (migration 38) — lida por quem vê o censo, escrita por ninguém'
-- ---------------------------------------------------------------------------
set local role authenticated;
set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
do $$
declare v_barrou boolean := false;
begin
  perform pg_temp.assert_eq('owner A LÊ a liberação do tenant dele',
    (select count(*) from app.alert_release), 1);
  perform pg_temp.assert_eq('e é a dele, com a taxa que sustentou a decisão',
    (select count(*) from app.alert_release where released_by = 'Owner A' and measured_rate = 3.00), 1);
  -- Liberar é ato do comando, nunca clique: até o owner toma permission denied.
  begin
    insert into app.alert_release (tenant_id, released_by, census_size, judged, false_positives, measured_rate)
    values ('aaaaaaaa-0000-0000-0000-000000000001', 'clique', 10, 10, 0, 0.00);
  exception when insufficient_privilege then v_barrou := true; end;
  perform pg_temp.assert_eq('owner NÃO grava liberação pelo navegador (sem grant de insert)',
    case when v_barrou then 1 else 0 end, 1);
end $$;

set local request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
do $$ begin
  perform pg_temp.assert_eq('RH lê a liberação (util.is_admin)',
    (select count(*) from app.alert_release), 1);
end $$;

set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
do $$ begin
  perform pg_temp.assert_eq('supervisor NÃO lê a liberação',
    (select count(*) from app.alert_release), 0);
end $$;

set local request.jwt.claim.sub = '66666666-6666-6666-6666-666666666666';
do $$ begin
  perform pg_temp.assert_eq('contabilidade NÃO lê a liberação',
    (select count(*) from app.alert_release), 0);
end $$;

set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$ begin
  perform pg_temp.assert_eq('owner B lê só a liberação dele',
    (select count(*) from app.alert_release where released_by = 'Owner B'), 1);
  perform pg_temp.assert_eq('owner B não lê a liberação de A',
    (select count(*) from app.alert_release where released_by = 'Owner A'), 0);
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

-- ---------------------------------------------------------------------------
\echo '--- Canais / C3 (Telegram): o chat_id que ninguém do painel lê, e a saúde que todos leem'
-- ---------------------------------------------------------------------------
-- Decisão do dono de 15/09/2026 (`docs/SPRINTS-CANAIS.md` §C3, "As duas paradas
-- foram abertas"): `app.messaging_identity` e `app.messaging_invite` com RLS
-- ligada e NENHUMA policy, sem grant a `authenticated` — a régua de
-- `app.integration_secret`. `app.channel_health` lida por `util.has_tenant`,
-- escrita só `service_role`. O que a tela precisa vem de duas RPCs definer.
--
-- ⛔ `permission denied`, E NÃO ZERO LINHAS
-- Numa tabela sem grant, contar linhas como owner devolve erro, não zero. Se a
-- asserção fosse "owner conta 0", ela ficaria verde de dois jeitos errados: a
-- tabela vazia e um `grant select` esquecido com RLS recusando tudo. Aqui o que
-- se afirma é o ERRO — `insufficient_privilege` — e ao lado dele, na MESMA
-- transação, o mesmo papel lendo `employee_pii`: é o positivo que prova que a
-- negação não é um banco onde ninguém lê nada.
--
-- A semente desta seção vive num savepoint: ela acrescenta dois colaboradores
-- em A Centro, e as contagens do resto do arquivo ("owner A vê 2
-- colaboradores") não podem ser tocadas.
savepoint prova_c3;
reset role;

-- Dois canais ativos em A (a linha 1 da SPEC §2.2, vista pela RPC) e dois em
-- B — em B o WhatsApp é `z_api`, NÃO oficial, de propósito: é o par que prova
-- que a contagem de regra bloqueada é só do WhatsApp OFICIAL (ver abaixo).
insert into app.integration (id, tenant_id, provider, active) values
  ('c3a00000-0000-0000-0000-0000000000d1', 'aaaaaaaa-0000-0000-0000-000000000001', 'meta_cloud', true),
  ('c3a00000-0000-0000-0000-0000000000d2', 'aaaaaaaa-0000-0000-0000-000000000001', 'telegram',   true),
  ('c3b00000-0000-0000-0000-0000000000d1', 'bbbbbbbb-0000-0000-0000-000000000002', 'telegram',   true),
  ('c3b00000-0000-0000-0000-0000000000d2', 'bbbbbbbb-0000-0000-0000-000000000002', 'z_api',      true);

-- A saúde, gravada pela porta única — SÓ para o bot de A (connected).
-- ⛔ O bot de B fica DELIBERADAMENTE sem medição até o bloco do owner de B: é
--    ali que se afirma que bot sem medição NÃO está pronto. Gravar a saúde
--    dos dois aqui deixava `coalesce(h.status = 'connected', true)` passar
--    verde na suíte inteira — medido na revisão do ciclo 1 (mutação C7). O
--    `disconnected` de B é gravado depois, no próprio bloco.
do $$ begin
  perform app.fn_record_channel_health('c3a00000-0000-0000-0000-0000000000d2', 'connected', 'getMe ok');
end $$;

-- Uma regra de WhatsApp ligada apontando para template `draft` em CADA tenant.
-- Em A o WhatsApp é meta_cloud (oficial): a regra CONTA como bloqueada. Em B é
-- z_api (não oficial): NÃO conta — e a linha telegram, que também é `official`,
-- não pode ser a que faz a regra de B contar. Sem este par, a restrição
-- `p.channel = 'whatsapp' and p.official` da CTE `blocked` só era presa por
-- texto (mutação C6 da revisão).
insert into app.message_template (tenant_id, code, variables, body, meta_status) values
  ('aaaaaaaa-0000-0000-0000-000000000001', 'deviation_summary', array['unit','occurrences'],
   'OperaX: {{1}} com {{2}} ocorrencias.', 'draft'),
  ('bbbbbbbb-0000-0000-0000-000000000002', 'deviation_summary', array['unit','occurrences'],
   'OperaX: {{1}} com {{2}} ocorrencias.', 'draft');
insert into app.alert_rule (tenant_id, name, content, channel, active, template_code) values
  ('aaaaaaaa-0000-0000-0000-000000000001', 'Resumo A, template rascunho', 'aggregate', 'whatsapp', true, 'deviation_summary'),
  ('bbbbbbbb-0000-0000-0000-000000000002', 'Resumo B, template rascunho', 'aggregate', 'whatsapp', true, 'deviation_summary');

-- Mais três colaboradores em A CENTRO: c1 aderiu, c3 tem convite em aberto,
-- c4 revogou — e c5 é DESLIGADO, sem nada. A Norte fica só com c2, sem nada —
-- que é `pending`.
-- ⛔ O desligado existe para que `status <> 'desligado'` seja exercido, não
--    lido: sem ele a soma 3 fica verde com o filtro apagado (mutação C11 da
--    revisão). Com o filtro, c5 não entra em contagem nenhuma; sem ele, vira
--    `pending` e a soma sobe para 4.
insert into app.employee (id, tenant_id, company_id, unit_id, name, status) values
  ('a0000000-0000-0000-0000-0000000000c3', 'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000e1', 'a0000000-0000-0000-0000-0000000000a1', 'Colab A Centro 3', 'active'),
  ('a0000000-0000-0000-0000-0000000000c4', 'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000e1', 'a0000000-0000-0000-0000-0000000000a1', 'Colab A Centro 4', 'active'),
  ('a0000000-0000-0000-0000-0000000000c5', 'aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000e1', 'a0000000-0000-0000-0000-0000000000a1', 'Colab A Centro 5 (desligado)', 'desligado');

insert into app.messaging_identity (tenant_id, channel, employee_id, external_id, revoked_at) values
  ('aaaaaaaa-0000-0000-0000-000000000001', 'telegram', 'a0000000-0000-0000-0000-0000000000c1', '9001', null),
  ('aaaaaaaa-0000-0000-0000-000000000001', 'telegram', 'a0000000-0000-0000-0000-0000000000c4', '9004', now() - interval '1 day');

insert into app.messaging_invite (tenant_id, channel, employee_id, token_hash) values
  ('aaaaaaaa-0000-0000-0000-000000000001', 'telegram', 'a0000000-0000-0000-0000-0000000000c3', 'hash-c3');

-- O RH com `pii`, como a matriz do PRODUTO (migration 02) o tem. A semente
-- genérica deste arquivo não dá `pii` ao hr; aqui ele precisa LER `employee_pii`
-- para que o `permission denied` dele em `messaging_identity` seja sobre a
-- tabela, e não sobre um papel que não lê nada. Vale só dentro do savepoint.
update app.domain_permission set allowed = true
 where tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001' and role = 'hr' and domain = 'pii';

-- O anti-vácuo e a fronteira, conferidos como dono — sob `authenticated` a
-- própria contagem seria permission denied.
do $$
declare v_tabela text;
begin
  perform pg_temp.assert_eq('as 2 identidades foram semeadas (o negativo não é vácuo)',
    (select count(*) from app.messaging_identity), 2);
  perform pg_temp.assert_eq('o convite foi semeado (idem)',
    (select count(*) from app.messaging_invite), 1);
  perform pg_temp.assert_eq('a saúde do bot de A foi gravada; a de B, de propósito, ainda não',
    (select count(*) from app.channel_health), 1);
  perform pg_temp.assert_eq('as 2 regras ligadas apontando para template rascunho foram semeadas (uma por tenant)',
    (select count(*) from app.alert_rule r
      join app.message_template m on m.tenant_id = r.tenant_id and m.code = r.template_code
     where r.active and r.channel = 'whatsapp' and m.meta_status = 'draft'), 2);
  perform pg_temp.assert_eq('o desligado de A Centro foi semeado (o filtro de ativos não é vácuo)',
    (select count(*) from app.employee
      where unit_id = 'a0000000-0000-0000-0000-0000000000a1' and status = 'desligado'), 1);

  foreach v_tabela in array array['messaging_identity','messaging_invite'] loop
    perform pg_temp.assert_eq('authenticated não tem verbo nenhum em app.' || v_tabela,
      (select count(*) from unnest(array['SELECT','INSERT','UPDATE','DELETE']) v
        where has_table_privilege('authenticated', 'app.' || v_tabela, v)), 0);
    perform pg_temp.assert_eq('anon idem em app.' || v_tabela,
      (select count(*) from unnest(array['SELECT','INSERT','UPDATE','DELETE']) v
        where has_table_privilege('anon', 'app.' || v_tabela, v)), 0);
    -- Zero policy é a GARANTIA aqui, não a falta dela: uma policy seria uma
    -- porta para authenticated, e ninguém do painel lê o chat_id.
    perform pg_temp.assert_eq('app.' || v_tabela || ' tem ZERO policies (decisão do dono)',
      (select count(*) from pg_policies where schemaname = 'app' and tablename = v_tabela), 0);
    perform pg_temp.assert_eq('service_role LÊ app.' || v_tabela || ' (o Caminho 2 existe)',
      case when has_table_privilege('service_role', 'app.' || v_tabela, 'SELECT')
           then 1 else 0 end, 1);
    perform pg_temp.assert_eq('e NÃO apaga app.' || v_tabela || ' (revogar é revoked_at)',
      case when has_table_privilege('service_role', 'app.' || v_tabela, 'DELETE')
           then 1 else 0 end, 0);
    perform pg_temp.assert_eq('app.' || v_tabela || ' tem RLS ligada',
      case when (select relrowsecurity from pg_class
                  where oid = ('app.' || v_tabela)::regclass) then 1 else 0 end, 1);
  end loop;
end $$;

-- --- owner de B, ANTES de o vigia medir o bot dele: sem medição NÃO está pronto --
-- SPEC §4: para telegram, ready = integração ativa E channel_health.status =
-- 'connected'. A metade "sem medição não está pronto" é o `coalesce(..., false)`
-- da função, e é a única defesa contra um bot que ninguém testou aparecer
-- verde na tela. Afirmada aqui, com o bot de B ativo e sem linha de saúde:
-- a linha da RPC EXISTE (o positivo), a saúde vem nula, e ready é false.
set local role authenticated;
set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';

do $$ begin
  perform pg_temp.assert_eq('owner B ainda não vê saúde nenhuma (o vigia não mediu o bot dele)',
    (select count(*) from app.channel_health), 0);
  perform pg_temp.assert_eq('mas a linha telegram de B EXISTE na fn_channel_readiness',
    (select count(*) from public.fn_channel_readiness() where provider = 'telegram'), 1);
  perform pg_temp.assert_eq('e vem com health_status NULO',
    (select count(*) from public.fn_channel_readiness()
      where provider = 'telegram' and health_status is null and health_changed_at is null), 1);
  perform pg_temp.assert_eq('e NÃO pronta: bot sem medição não está pronto (SPEC §4)',
    (select count(*) from public.fn_channel_readiness()
      where provider = 'telegram' and not ready), 1);
end $$;

-- Agora o vigia mede o bot de B: `disconnected`, valor DIFERENTE do de A para
-- que "owner A não vê a linha de B" não seja indistinguível de "vê a dele
-- duas vezes".
reset role;
do $$ begin
  perform app.fn_record_channel_health('c3b00000-0000-0000-0000-0000000000d1', 'disconnected', '401');
end $$;

-- --- owner de A: permission denied nas duas, e LÊ PII ao lado -----------------
set local role authenticated;
set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';

do $$
declare v_negado boolean;
begin
  perform pg_temp.assert_eq('owner A LÊ employee_pii (o positivo: ele lê o que tem grant)',
    (select count(*) from app.employee_pii), 1);

  v_negado := false;
  begin
    perform 1 from app.messaging_identity;
  exception when insufficient_privilege then v_negado := true; end;
  perform pg_temp.assert_eq('owner A recebe permission denied em app.messaging_identity (não zero linhas)',
    case when v_negado then 1 else 0 end, 1);

  v_negado := false;
  begin
    perform 1 from app.messaging_invite;
  exception when insufficient_privilege then v_negado := true; end;
  perform pg_temp.assert_eq('owner A recebe permission denied em app.messaging_invite',
    case when v_negado then 1 else 0 end, 1);

  -- channel_health: a linha de A, e NÃO a de B. Os valores diferem, então o
  -- 1 é de fato a linha dele e não uma duplicata.
  perform pg_temp.assert_eq('owner A LÊ app.channel_health: 1 linha',
    (select count(*) from app.channel_health), 1);
  perform pg_temp.assert_eq('e é a do bot dele (connected), não a de B (disconnected)',
    (select count(*) from app.channel_health where status = 'connected'
       and integration_id = 'c3a00000-0000-0000-0000-0000000000d2'), 1);
  perform pg_temp.assert_eq('owner A NÃO vê a saúde do bot de B',
    (select count(*) from app.channel_health
      where tenant_id = 'bbbbbbbb-0000-0000-0000-000000000002'), 0);

  -- E não grava saúde: o vigia é service_role.
  v_negado := false;
  begin
    insert into app.channel_health (integration_id, tenant_id, status)
    values ('c3a00000-0000-0000-0000-0000000000d1', 'aaaaaaaa-0000-0000-0000-000000000001', 'connected');
  exception when insufficient_privilege then v_negado := true; end;
  perform pg_temp.assert_eq('owner A recebe permission denied ao INSERIR em app.channel_health',
    case when v_negado then 1 else 0 end, 1);
end $$;

-- --- as duas RPCs, como owner de A --------------------------------------------
do $$ begin
  -- fn_channel_readiness: as DUAS linhas de A — meta_cloud e telegram lado a
  -- lado. É a linha 1 da SPEC §2.2 vista pela RPC.
  perform pg_temp.assert_eq('fn_channel_readiness: owner A vê 2 linhas',
    (select count(*) from public.fn_channel_readiness()), 2);
  perform pg_temp.assert_eq('e as duas são de A',
    (select count(*) from public.fn_channel_readiness()
      where tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001'), 2);
  perform pg_temp.assert_eq('uma é telegram (channel telegram, connected, ready)',
    (select count(*) from public.fn_channel_readiness()
      where provider = 'telegram' and channel = 'telegram'
        and health_status = 'connected' and ready), 1);
  perform pg_temp.assert_eq('a outra é meta_cloud (channel whatsapp)',
    (select count(*) from public.fn_channel_readiness()
      where provider = 'meta_cloud' and channel = 'whatsapp'), 1);
  -- O POSITIVO da contagem de regra bloqueada: meta_cloud é oficial, a regra de
  -- A aponta para template rascunho, e ela conta EXATAMENTE uma vez — não duas.
  -- Sem a restrição `p.channel = 'whatsapp'` na CTE `blocked`, a regra casaria
  -- também com a linha telegram (que é `official`) e viria 2 nas duas linhas.
  perform pg_temp.assert_eq('a linha meta_cloud conta a regra bloqueada UMA vez (rules_blocked = 1) e não está pronta',
    (select count(*) from public.fn_channel_readiness()
      where provider = 'meta_cloud' and rules_blocked = 1 and not ready), 1);
  -- Telegram não tem template a aprovar: os três contadores valem 0 nele.
  perform pg_temp.assert_eq('a linha telegram traz templates_total = 0 e rules_blocked = 0',
    (select count(*) from public.fn_channel_readiness()
      where provider = 'telegram' and templates_total = 0
        and templates_approved = 0 and rules_blocked = 0), 1);

  -- fn_telegram_adhesion: A Centro = (1, 1, 1); A Norte = (0, 1, 0).
  perform pg_temp.assert_eq('fn_telegram_adhesion: owner A vê as 2 unidades',
    (select count(*) from public.fn_telegram_adhesion()), 2);
  perform pg_temp.assert_eq('A Centro: joined = 1',
    (select joined from public.fn_telegram_adhesion()
      where unit_id = 'a0000000-0000-0000-0000-0000000000a1'), 1);
  perform pg_temp.assert_eq('A Centro: pending = 1 (o do convite em aberto)',
    (select pending from public.fn_telegram_adhesion()
      where unit_id = 'a0000000-0000-0000-0000-0000000000a1'), 1);
  perform pg_temp.assert_eq('A Centro: revoked = 1',
    (select revoked from public.fn_telegram_adhesion()
      where unit_id = 'a0000000-0000-0000-0000-0000000000a1'), 1);
  -- Os três somam os ativos da unidade: nenhum estado mudo fica de fora.
  perform pg_temp.assert_eq('A Centro: joined + pending + revoked = 3 ativos',
    (select joined + pending + revoked from public.fn_telegram_adhesion()
      where unit_id = 'a0000000-0000-0000-0000-0000000000a1'), 3);
  -- ⛔ E são 4 na tabela: o quarto é o DESLIGADO, e ele fica fora da soma. Sem
  --    o filtro `status <> 'desligado'` ele viraria `pending` e a soma daria 4.
  perform pg_temp.assert_eq('A Centro tem 4 colaboradores na tabela (o owner os vê)',
    (select count(*) from public.vw_employee
      where unit_id = 'a0000000-0000-0000-0000-0000000000a1'), 4);
  perform pg_temp.assert_eq('e 1 deles é desligado — o que não entra em contagem nenhuma',
    (select count(*) from public.vw_employee
      where unit_id = 'a0000000-0000-0000-0000-0000000000a1' and status = 'desligado'), 1);
  perform pg_temp.assert_eq('A Norte: (0, 1, 0) — c2 nunca aderiu',
    (select count(*) from public.fn_telegram_adhesion()
      where unit_id = 'a0000000-0000-0000-0000-0000000000a2'
        and joined = 0 and pending = 1 and revoked = 0), 1);

  -- ⛔ Nenhuma coluna da resposta nomeia pessoa. Afirmado no tipo de retorno
  --    (os OUT args em pg_proc), por nome exato.
  perform pg_temp.assert_eq('fn_telegram_adhesion não devolve external_id, chat_id, contact_id, employee_id nem name',
    (select count(*)
       from pg_proc p join pg_namespace n on n.oid = p.pronamespace,
            unnest(p.proargnames, p.proargmodes) as a(nome, modo)
      where n.nspname = 'public' and p.proname = 'fn_telegram_adhesion' and a.modo = 't'
        and a.nome in ('external_id','chat_id','contact_id','employee_id','name')), 0);
  perform pg_temp.assert_eq('e devolve exatamente as 5 colunas do contrato',
    (select count(*)
       from pg_proc p join pg_namespace n on n.oid = p.pronamespace,
            unnest(p.proargnames, p.proargmodes) as a(nome, modo)
      where n.nspname = 'public' and p.proname = 'fn_telegram_adhesion' and a.modo = 't'
        and a.nome in ('unit_id','unit_name','joined','pending','revoked')), 5);
end $$;

-- --- personnel e hr: o mesmo par (permission denied + PII lida ao lado) --------
set local request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
do $$
declare v_negado boolean := false;
begin
  perform pg_temp.assert_eq('DP LÊ employee_pii (o positivo)',
    (select count(*) from app.employee_pii), 1);
  begin
    perform 1 from app.messaging_identity;
  exception when insufficient_privilege then v_negado := true; end;
  perform pg_temp.assert_eq('DP tem pii e AINDA ASSIM recebe permission denied em app.messaging_identity',
    case when v_negado then 1 else 0 end, 1);
  v_negado := false;
  begin
    perform 1 from app.messaging_invite;
  exception when insufficient_privilege then v_negado := true; end;
  perform pg_temp.assert_eq('e em app.messaging_invite',
    case when v_negado then 1 else 0 end, 1);
end $$;

set local request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
do $$
declare v_negado boolean := false;
begin
  perform pg_temp.assert_eq('RH LÊ employee_pii (o positivo — com pii, como na matriz do produto)',
    (select count(*) from app.employee_pii), 1);
  begin
    perform 1 from app.messaging_identity;
  exception when insufficient_privilege then v_negado := true; end;
  perform pg_temp.assert_eq('RH recebe permission denied em app.messaging_identity',
    case when v_negado then 1 else 0 end, 1);
  v_negado := false;
  begin
    perform 1 from app.messaging_invite;
  exception when insufficient_privilege then v_negado := true; end;
  perform pg_temp.assert_eq('e em app.messaging_invite',
    case when v_negado then 1 else 0 end, 1);
end $$;

-- --- supervisor de unidade de A: lê a saúde, e as RPCs só na unidade dele -----
set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
do $$ begin
  -- Estado do canal é do tenant (has_tenant): o supervisor lê.
  perform pg_temp.assert_eq('supervisor LÊ app.channel_health (é estado do canal, has_tenant)',
    (select count(*) from app.channel_health), 1);
  -- A mesma régua de fn_whatsapp_readiness: a prontidão responde a ele.
  perform pg_temp.assert_eq('fn_channel_readiness responde ao supervisor (2 linhas de A)',
    (select count(*) from public.fn_channel_readiness()), 2);
  -- E a adesão, só na unidade dele — A Centro, com os números certos.
  perform pg_temp.assert_eq('fn_telegram_adhesion: supervisor vê SÓ a unidade dele',
    (select count(*) from public.fn_telegram_adhesion()), 1);
  perform pg_temp.assert_eq('e é A Centro, com (1, 1, 1)',
    (select count(*) from public.fn_telegram_adhesion()
      where unit_id = 'a0000000-0000-0000-0000-0000000000a1'
        and joined = 1 and pending = 1 and revoked = 1), 1);
  perform pg_temp.assert_eq('supervisor NÃO vê A Norte na adesão',
    (select count(*) from public.fn_telegram_adhesion()
      where unit_id = 'a0000000-0000-0000-0000-0000000000a2'), 0);
end $$;

-- --- owner de B: nada de A ----------------------------------------------------
set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$ begin
  perform pg_temp.assert_eq('fn_channel_readiness: owner B vê as 2 linhas dele (z_api e telegram)',
    (select count(*) from public.fn_channel_readiness()), 2);
  -- O NEGATIVO do par: z_api NÃO é oficial, então a regra de B apontando para
  -- template rascunho NÃO é bloqueio — nem na linha z_api, nem na telegram
  -- (que é `official`, e sem `p.channel = 'whatsapp'` na CTE seria ela a fazer
  -- a regra contar). z_api está pronta por existir.
  perform pg_temp.assert_eq('a linha z_api tem rules_blocked = 0 e está pronta (não oficial: template não a trava)',
    (select count(*) from public.fn_channel_readiness()
      where provider = 'z_api' and channel = 'whatsapp' and rules_blocked = 0 and ready), 1);
  perform pg_temp.assert_eq('e a linha telegram de B também tem rules_blocked = 0',
    (select count(*) from public.fn_channel_readiness()
      where provider = 'telegram' and rules_blocked = 0), 1);
  perform pg_temp.assert_eq('e zero linhas de A',
    (select count(*) from public.fn_channel_readiness()
      where tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001'), 0);
  perform pg_temp.assert_eq('o bot de B está disconnected e NÃO pronto',
    (select count(*) from public.fn_channel_readiness()
      where provider = 'telegram' and health_status = 'disconnected' and not ready), 1);
  perform pg_temp.assert_eq('owner B lê só a saúde do bot dele',
    (select count(*) from app.channel_health), 1);
  perform pg_temp.assert_eq('fn_telegram_adhesion: owner B vê só B Sul',
    (select count(*) from public.fn_telegram_adhesion()), 1);
  perform pg_temp.assert_eq('e B Sul é (0, 1, 0)',
    (select count(*) from public.fn_telegram_adhesion()
      where unit_id = 'b0000000-0000-0000-0000-0000000000a1'
        and joined = 0 and pending = 1 and revoked = 0), 1);
end $$;

-- --- anon: permission denied nas três --------------------------------------
reset request.jwt.claim.sub;
set local role anon;
do $$
declare v_tabela text; v_negado boolean;
begin
  foreach v_tabela in array array['messaging_identity','messaging_invite','channel_health'] loop
    v_negado := false;
    begin
      execute format('select 1 from app.%I', v_tabela);
    exception when insufficient_privilege then v_negado := true; end;
    perform pg_temp.assert_eq('anon recebe permission denied em app.' || v_tabela,
      case when v_negado then 1 else 0 end, 1);
  end loop;
end $$;

rollback to savepoint prova_c3;

-- O savepoint não deixou rastro — nem os dois colaboradores extras.
reset role;
do $$ begin
  perform pg_temp.assert_eq('a prova do C3 não deixou rastro (identidades)',
    (select count(*) from app.messaging_identity), 0);
  perform pg_temp.assert_eq('nem colaborador extra em A Centro',
    (select count(*) from app.employee
      where unit_id = 'a0000000-0000-0000-0000-0000000000a1'), 1);
end $$;

reset role;

\echo '--- Canais / C5: entregas por canal — o admin vê a semana do próprio tenant, e só ela'
-- ---------------------------------------------------------------------------
-- `public.fn_delivery_by_channel` (migration `ch_delivery_by_channel`) é
-- security INVOKER: lê `app.alert_sent` pela policy `alert_sent_read`
-- (`util.is_admin` — owner, hr, personnel). Então o que se afirma aqui é a
-- policy, vista pela RPC: owner e RH de A veem a semana de A; o supervisor vê
-- ZERO linhas (é o desenho: log de entrega é instrumento do administrador);
-- owner de B vê só B; anon recebe permission denied na função.
--
-- Os valores diferem por tenant (A: telegram + meta_cloud; B: z_api) para que
-- "owner A não vê B" não seja indistinguível de "vê o dele duas vezes". E uma
-- linha de A está NOVE semanas atrás: fora da janela padrão de 8, dentro da de
-- 10 — sem ela, um `where` apagado ficaria verde.
savepoint prova_c5;
reset role;

insert into app.alert_sent (tenant_id, channel, provider, destination_hash, status, error, sent_at) values
  ('aaaaaaaa-0000-0000-0000-000000000001', 'telegram', 'telegram',   repeat('a', 64), 'sent',   null,      now()),
  ('aaaaaaaa-0000-0000-0000-000000000001', 'whatsapp', 'meta_cloud', repeat('b', 64), 'failed', 'blocked', now()),
  ('aaaaaaaa-0000-0000-0000-000000000001', 'whatsapp', 'meta_cloud', repeat('c', 64), 'sent',   null,      now() - interval '9 weeks'),
  ('bbbbbbbb-0000-0000-0000-000000000002', 'whatsapp', 'z_api',      repeat('d', 64), 'sent',   null,      now());

-- O anti-vácuo, como dono: as 4 linhas estão lá, e `telegram` passou no check
-- de provedor (`ch_telegram_provider`).
do $$ begin
  perform pg_temp.assert_eq('as 4 linhas de alert_sent foram semeadas (2 tenants, 3 provedores)',
    (select count(*) from app.alert_sent), 4);
  perform pg_temp.assert_eq('e uma delas é telegram/telegram',
    (select count(*) from app.alert_sent where channel = 'telegram' and provider = 'telegram'), 1);
end $$;

-- --- owner de A ---------------------------------------------------------------
set local role authenticated;
set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
do $$ begin
  perform pg_temp.assert_eq('owner A lê 3 linhas de alert_sent (as dele, pela policy)',
    (select count(*) from app.alert_sent), 3);
  perform pg_temp.assert_eq('fn_delivery_by_channel: owner A vê 2 linhas nesta semana (telegram, whatsapp)',
    (select count(*) from public.fn_delivery_by_channel()), 2);
  perform pg_temp.assert_eq('a linha telegram: sent 1, failed 0',
    (select count(*) from public.fn_delivery_by_channel()
      where channel = 'telegram' and provider = 'telegram' and sent = 1 and failed = 0), 1);
  perform pg_temp.assert_eq('a linha whatsapp/meta_cloud: sent 0, failed 1 (o blocked)',
    (select count(*) from public.fn_delivery_by_channel()
      where channel = 'whatsapp' and provider = 'meta_cloud' and sent = 0 and failed = 1), 1);
  perform pg_temp.assert_eq('as duas são desta semana',
    (select count(*) from public.fn_delivery_by_channel()
      where week_start = date_trunc('week', now())::date), 2);
  perform pg_temp.assert_eq('a de 9 semanas atrás fica FORA da janela padrão (8)',
    (select count(*) from public.fn_delivery_by_channel()
      where week_start < date_trunc('week', now())::date), 0);
  perform pg_temp.assert_eq('e ENTRA com p_weeks = 10, como semana própria',
    (select count(*) from public.fn_delivery_by_channel(10)), 3);
  perform pg_temp.assert_eq('p_weeks = 0 é a semana atual, não tudo',
    (select count(*) from public.fn_delivery_by_channel(0)), 2);
  -- A ordem é week_start, channel, provider: a semana antiga primeiro, depois
  -- telegram antes de whatsapp na atual. Conferida pela lista inteira.
  perform pg_temp.assert_eq('e vem ordenada: week_start, channel, provider',
    case when (select array_agg(channel || '/' || provider) from public.fn_delivery_by_channel(10))
              = array['whatsapp/meta_cloud', 'telegram/telegram', 'whatsapp/meta_cloud']
         then 1 else 0 end, 1);
  perform pg_temp.assert_eq('owner A NÃO vê a linha z_api (é de B)',
    (select count(*) from public.fn_delivery_by_channel(10) where provider = 'z_api'), 0);
end $$;

-- --- RH de A (is_admin) e supervisor de A (não é) ----------------------------
set local request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
do $$ begin
  perform pg_temp.assert_eq('RH A vê as 2 linhas da semana (util.is_admin inclui hr)',
    (select count(*) from public.fn_delivery_by_channel()), 2);
end $$;

set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
do $$ begin
  -- O positivo ao lado: o supervisor VÊ a unidade dele — não é um papel vazio.
  perform pg_temp.assert_eq('supervisor A vê a unidade dele (o positivo)',
    (select count(*) from public.vw_unit), 1);
  perform pg_temp.assert_eq('supervisor A: ZERO linhas de alert_sent (alert_sent_read é is_admin)',
    (select count(*) from app.alert_sent), 0);
  perform pg_temp.assert_eq('e ZERO na RPC — invoker, a policy é o recorte (o desenho, não bug)',
    (select count(*) from public.fn_delivery_by_channel(10)), 0);
end $$;

-- --- owner de B: só B ---------------------------------------------------------
set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$ begin
  perform pg_temp.assert_eq('owner B vê 1 linha: z_api, sent 1',
    (select count(*) from public.fn_delivery_by_channel(10)
      where channel = 'whatsapp' and provider = 'z_api' and sent = 1 and failed = 0), 1);
  perform pg_temp.assert_eq('e só ela',
    (select count(*) from public.fn_delivery_by_channel(10)), 1);
  perform pg_temp.assert_eq('nenhuma telegram (a de A) chega a B',
    (select count(*) from public.fn_delivery_by_channel(10) where channel = 'telegram'), 0);
end $$;

-- --- anon: permission denied na função ----------------------------------------
reset request.jwt.claim.sub;
set local role anon;
do $$
declare v_negado boolean := false;
begin
  begin
    perform * from public.fn_delivery_by_channel();
  exception when insufficient_privilege then v_negado := true; end;
  perform pg_temp.assert_eq('anon recebe permission denied em fn_delivery_by_channel (não zero linhas)',
    case when v_negado then 1 else 0 end, 1);
end $$;

rollback to savepoint prova_c5;

reset role;
do $$ begin
  perform pg_temp.assert_eq('a prova do C5 não deixou rastro em alert_sent',
    (select count(*) from app.alert_sent), 0);
end $$;

reset role;

-- ---------------------------------------------------------------------------
\echo '--- Calendário de feriados (P0.3): lê quem vê o tenant e a unidade; escreve só o owner'
-- ---------------------------------------------------------------------------
-- Policy aprovada pelo dono em 28/09/2026. `app.holiday` não tem grant para
-- `authenticated` (Caminho 2), então a policy é avaliada como está no catálogo,
-- com `pg_temp.policy_says_on`, na sessão de cada papel. Cada negativo tem o
-- seu positivo: sem ele, um "não lê" ficaria verde numa policy que não deixa
-- ninguém ler.
insert into app.holiday (tenant_id, reference_date, jurisdiction, unit_id, name) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '2026-09-07', 'national',  null,
   'Independência A'),
  ('aaaaaaaa-0000-0000-0000-000000000001', '2026-11-20', 'municipal',
   'a0000000-0000-0000-0000-0000000000a2', 'Municipal de A Norte'),
  ('bbbbbbbb-0000-0000-0000-000000000002', '2026-09-07', 'national',  null,
   'Independência B');

do $$ begin
  perform pg_temp.assert_eq('os 3 feriados foram semeados (o negativo não é vácuo)',
    (select count(*) from app.holiday), 3);
  perform pg_temp.assert_eq('authenticated não tem verbo nenhum em app.holiday',
    (select count(*) from unnest(array['SELECT','INSERT','UPDATE','DELETE']) v
      where has_table_privilege('authenticated', 'app.holiday', v)), 0);
  perform pg_temp.assert_eq('anon idem em app.holiday',
    (select count(*) from unnest(array['SELECT','INSERT','UPDATE','DELETE']) v
      where has_table_privilege('anon', 'app.holiday', v)), 0);
  perform pg_temp.assert_eq('service_role LÊ e GRAVA app.holiday (o motor e a API existem)',
    (select count(*) from unnest(array['SELECT','INSERT','UPDATE']) v
      where has_table_privilege('service_role', 'app.holiday', v)), 3);
  perform pg_temp.assert_eq('e NÃO apaga (feriado sai com active = false)',
    case when has_table_privilege('service_role', 'app.holiday', 'DELETE') then 1 else 0 end, 0);
end $$;

set local role authenticated;

-- --- owner de A: lê e escreve A, nada de B ------------------------------------
set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
do $$ begin
  perform pg_temp.assert_eq('owner A lê o feriado nacional de A',
    pg_temp.policy_says_on('holiday', 'holiday_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 1);
  perform pg_temp.assert_eq('owner A lê o municipal de A Norte',
    pg_temp.policy_says_on('holiday', 'holiday_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, 'a0000000-0000-0000-0000-0000000000a2'), 1);
  perform pg_temp.assert_eq('owner A NÃO lê o feriado de B',
    pg_temp.policy_says_on('holiday', 'holiday_read',
      'bbbbbbbb-0000-0000-0000-000000000002', null, null), 0);
  perform pg_temp.assert_eq('owner A ESCREVE o calendário de A (with check)',
    pg_temp.policy_says_on('holiday', 'holiday_owner_insert',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null, 'with_check'), 1);
  perform pg_temp.assert_eq('owner A NÃO escreve o calendário de B',
    pg_temp.policy_says_on('holiday', 'holiday_owner_insert',
      'bbbbbbbb-0000-0000-0000-000000000002', null, null, 'with_check'), 0);
  -- O positivo do `using` do update: sem ele, um `using (... and false)` deixaria
  -- verdes todos os "não alcança linha para alterar" abaixo.
  perform pg_temp.assert_eq('owner A ALCANÇA a linha de A para alterar (using do update)',
    pg_temp.policy_says_on('holiday', 'holiday_owner_update',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 1);
  perform pg_temp.assert_eq('e grava a alteração (with check do update)',
    pg_temp.policy_says_on('holiday', 'holiday_owner_update',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null, 'with_check'), 1);
  perform pg_temp.assert_eq('owner A NÃO alcança a linha de B para alterar',
    pg_temp.policy_says_on('holiday', 'holiday_owner_update',
      'bbbbbbbb-0000-0000-0000-000000000002', null, null), 0);
  perform pg_temp.assert_eq('app.holiday não tem policy de DELETE nem FOR ALL',
    (select count(*) from pg_policies
      where schemaname = 'app' and tablename = 'holiday' and cmd in ('DELETE', 'ALL')), 0);
end $$;

-- --- supervisor de A Centro: lê o nacional e a unidade dele, não escreve -----
set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
do $$ begin
  perform pg_temp.assert_eq('supervisor lê o nacional do tenant dele',
    pg_temp.policy_says_on('holiday', 'holiday_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 1);
  perform pg_temp.assert_eq('supervisor lê o feriado local da unidade DELE (A Centro)',
    pg_temp.policy_says_on('holiday', 'holiday_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, 'a0000000-0000-0000-0000-0000000000a1'), 1);
  perform pg_temp.assert_eq('supervisor NÃO lê o municipal de A Norte',
    pg_temp.policy_says_on('holiday', 'holiday_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, 'a0000000-0000-0000-0000-0000000000a2'), 0);
  perform pg_temp.assert_eq('supervisor NÃO escreve o calendário',
    pg_temp.policy_says_on('holiday', 'holiday_owner_insert',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null, 'with_check'), 0);
end $$;

-- --- DP (personnel) e RH (hr): são admin e NÃO são owner ---------------------
-- O par que prova que o eixo é `owner` e não `util.is_admin`: os dois passam no
-- `is_admin` (positivo) e mesmo assim não escrevem (negativo).
set local request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
do $$ begin
  perform pg_temp.assert_eq('DP é admin do tenant A',
    case when util.is_admin('aaaaaaaa-0000-0000-0000-000000000001') then 1 else 0 end, 1);
  perform pg_temp.assert_eq('DP lê o calendário de A',
    pg_temp.policy_says_on('holiday', 'holiday_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, 'a0000000-0000-0000-0000-0000000000a2'), 1);
  perform pg_temp.assert_eq('e DP NÃO escreve o calendário (não é owner)',
    pg_temp.policy_says_on('holiday', 'holiday_owner_insert',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null, 'with_check'), 0);
  perform pg_temp.assert_eq('nem alcança linha para alterar (using do update)',
    pg_temp.policy_says_on('holiday', 'holiday_owner_update',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 0);
  perform pg_temp.assert_eq('nem grava o que alterasse (with check do update)',
    pg_temp.policy_says_on('holiday', 'holiday_owner_update',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null, 'with_check'), 0);
end $$;

set local request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
do $$ begin
  perform pg_temp.assert_eq('RH é admin do tenant A',
    case when util.is_admin('aaaaaaaa-0000-0000-0000-000000000001') then 1 else 0 end, 1);
  perform pg_temp.assert_eq('RH lê o calendário de A',
    pg_temp.policy_says_on('holiday', 'holiday_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 1);
  perform pg_temp.assert_eq('e RH NÃO escreve o calendário (não é owner)',
    pg_temp.policy_says_on('holiday', 'holiday_owner_insert',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null, 'with_check'), 0);
end $$;

-- --- owner de B: o espelho do owner de A -------------------------------------
set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$ begin
  perform pg_temp.assert_eq('owner B lê o feriado de B',
    pg_temp.policy_says_on('holiday', 'holiday_read',
      'bbbbbbbb-0000-0000-0000-000000000002', null, null), 1);
  perform pg_temp.assert_eq('owner B NÃO lê o feriado de A',
    pg_temp.policy_says_on('holiday', 'holiday_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null), 0);
  perform pg_temp.assert_eq('owner B NÃO lê o municipal de A Norte',
    pg_temp.policy_says_on('holiday', 'holiday_read',
      'aaaaaaaa-0000-0000-0000-000000000001', null, 'a0000000-0000-0000-0000-0000000000a2'), 0);
  perform pg_temp.assert_eq('owner B escreve o calendário de B',
    pg_temp.policy_says_on('holiday', 'holiday_owner_insert',
      'bbbbbbbb-0000-0000-0000-000000000002', null, null, 'with_check'), 1);
  perform pg_temp.assert_eq('owner B NÃO escreve o calendário de A',
    pg_temp.policy_says_on('holiday', 'holiday_owner_insert',
      'aaaaaaaa-0000-0000-0000-000000000001', null, null, 'with_check'), 0);
end $$;

reset request.jwt.claim.sub;
reset role;

-- ---------------------------------------------------------------------------
\echo '--- Alçada (P1.2): a revisão só entra pela RPC, e a RPC checa o papel'
-- ---------------------------------------------------------------------------
-- `public.fn_revisar_justificativa`, aprovada pelo dono em 29/09/2026. Cada
-- recusa tem ao lado o positivo que a separa de "a RPC recusa tudo":
--   not_hr (supervisor)             x  hr devolve id
--   owner_only (hr, marcado)        x  owner devolve id no marcado; hr no não marcado
--   already_reviewed                x  a primeira revisão entrou (count = 1)
--   source_is_mirror                x  a mesma chamada, com source operax, passa
--   no_open_period (B sem aberta)   x  A com aberta devolve id
--   rejection_needs_reason          x  com motivo, devolve id e o desvio fica active
--   justification_not_found         x  o dono do tenant certo alcança a mesma linha
insert into app.employee (id, tenant_id, company_id, unit_id, name, approval_owner_only) values
  ('a0000000-0000-0000-0000-0000000000c3', 'aaaaaaaa-0000-0000-0000-000000000001',
   'a0000000-0000-0000-0000-0000000000e1', 'a0000000-0000-0000-0000-0000000000a1',
   'Analista RH A Centro', true);

insert into app.deviation_event (id, tenant_id, employee_id, company_id, unit_id, reference_date, type, minutes, mode) values
  ('a0000000-0000-0000-0000-00000000ad05','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c3','a0000000-0000-0000-0000-0000000000e1','a0000000-0000-0000-0000-0000000000a1','2026-08-10','late_entry',-12,'production'),
  ('a0000000-0000-0000-0000-00000000ad06','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c1','a0000000-0000-0000-0000-0000000000e1','a0000000-0000-0000-0000-0000000000a1','2026-08-12','late_exit',30,'production');

insert into app.justification (id, tenant_id, deviation_event_id, employee_id, reference_date, text, status, source) values
  ('a0000000-0000-0000-0000-00000000f101','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-00000000ad01','a0000000-0000-0000-0000-0000000000c1','2026-08-10','Consulta medica','pending','operax'),
  ('a0000000-0000-0000-0000-00000000f102','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-00000000ad02','a0000000-0000-0000-0000-0000000000c2','2026-08-10','Transito','pending','operax'),
  ('a0000000-0000-0000-0000-00000000f103','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-00000000ad05','a0000000-0000-0000-0000-0000000000c3','2026-08-10','Reuniao externa','pending','operax'),
  ('a0000000-0000-0000-0000-00000000f104','aaaaaaaa-0000-0000-0000-000000000001',null,'a0000000-0000-0000-0000-0000000000c1','2026-08-10','Abono da origem','accepted','secullum'),
  ('b0000000-0000-0000-0000-00000000f105','bbbbbbbb-0000-0000-0000-000000000002','b0000000-0000-0000-0000-00000000ad04','b0000000-0000-0000-0000-0000000000c1','2026-08-10','Justificativa B','pending','operax'),
  ('a0000000-0000-0000-0000-00000000f106','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-00000000ad06','a0000000-0000-0000-0000-0000000000c1','2026-08-12','Saida tardia combinada','pending','operax');

-- A: uma fechada, e DUAS abertas — a revisão vai para a mais antiga aberta.
-- B: nenhuma aberta (no_open_period).
insert into app.payroll_period (id, tenant_id, year, month, status) values
  ('a0000000-0000-0000-0000-00000000e208','aaaaaaaa-0000-0000-0000-000000000001',2026,8,'fechada'),
  ('a0000000-0000-0000-0000-00000000e209','aaaaaaaa-0000-0000-0000-000000000001',2026,9,'aberta'),
  ('a0000000-0000-0000-0000-00000000e210','aaaaaaaa-0000-0000-0000-000000000001',2026,10,'aberta'),
  ('b0000000-0000-0000-0000-00000000e209','bbbbbbbb-0000-0000-0000-000000000002',2026,9,'fechada');

update app.deviation_type_config set requires_justification = true
 where tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001' and code in ('late_entry','late_exit');

-- Uma chamada, e o que ela respondeu: o código da recusa, ou 'ok'.
create or replace function pg_temp.revisa(p_id uuid, p_decision text, p_reason text)
returns text language plpgsql as $$
begin
  perform public.fn_revisar_justificativa(p_id, p_decision, p_reason);
  return 'ok';
exception when sqlstate 'P0001' then return sqlerrm;
end $$;

create or replace function pg_temp.assert_txt(rotulo text, obtido text, esperado text)
returns void language plpgsql as $$
begin
  if obtido is distinct from esperado then
    raise exception 'FALHA [%]: esperado %, obtido %', rotulo, esperado, obtido;
  end if;
  raise notice '  ok  % (%)', rotulo, obtido;
end $$;

do $$ begin
  perform pg_temp.assert_eq('authenticated NÃO executa app.revoke_deviation (a porta sem papel fechou)',
    case when has_function_privilege('authenticated', 'app.revoke_deviation(uuid,text,text)', 'execute')
         then 1 else 0 end, 0);
  perform pg_temp.assert_eq('authenticated EXECUTA public.fn_revisar_justificativa',
    case when has_function_privilege('authenticated', 'public.fn_revisar_justificativa(uuid,text,text)', 'execute')
         then 1 else 0 end, 1);
  perform pg_temp.assert_eq('anon NÃO executa public.fn_revisar_justificativa',
    case when has_function_privilege('anon', 'public.fn_revisar_justificativa(uuid,text,text)', 'execute')
         then 1 else 0 end, 0);
  perform pg_temp.assert_eq('o motor (postgres) continua executando app.revoke_deviation',
    case when has_function_privilege('postgres', 'app.revoke_deviation(uuid,text,text)', 'execute')
         then 1 else 0 end, 1);
  perform pg_temp.assert_eq('authenticated não escreve app.justification_review (só lê)',
    (select count(*) from unnest(array['INSERT','UPDATE','DELETE']) v
      where has_table_privilege('authenticated', 'app.justification_review', v)), 0);
end $$;

set local role authenticated;

-- --- supervisor de A Centro: enxerga a pessoa e NÃO revisa -----------------
set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
do $$ begin
  perform pg_temp.assert_eq('supervisor ENXERGA a justificativa de A Centro (a recusa não é de escopo)',
    (select count(*) from app.justification where id = 'a0000000-0000-0000-0000-00000000f101'), 1);
  perform pg_temp.assert_txt('supervisor revisando recebe not_hr',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f101', 'approved', null), 'not_hr');
  -- A porta antiga: a RLS de update do desvio não é o que barra — o EXECUTE é.
  begin
    perform app.revoke_deviation('a0000000-0000-0000-0000-00000000ad01', 'contorno', 'justified');
    raise exception 'FALHA: supervisor executou app.revoke_deviation';
  exception when insufficient_privilege then
    raise notice '  ok  supervisor não chama app.revoke_deviation (permission denied)';
  end;
end $$;

-- --- RH de A ------------------------------------------------------------------
set local request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
do $$ begin
  perform pg_temp.assert_txt('RH aprova a justificativa de colaborador não marcado',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f101', 'approved', null), 'ok');
  perform pg_temp.assert_txt('segunda revisão da mesma: already_reviewed',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f101', 'rejected', 'mudei de ideia'),
    'already_reviewed');
  perform pg_temp.assert_txt('RH revisando colaborador do RH (approval_owner_only): owner_only',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f103', 'approved', null), 'owner_only');
  perform pg_temp.assert_txt('justificativa espelhada do Secullum: source_is_mirror',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f104', 'approved', null), 'source_is_mirror');
  perform pg_temp.assert_txt('reprovar sem motivo: rejection_needs_reason',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f102', 'rejected', '   '),
    'rejection_needs_reason');
  perform pg_temp.assert_txt('reprovar com motivo passa',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f102', 'rejected', 'Sem comprovante'), 'ok');
  perform pg_temp.assert_txt('RH de A com id de B: justification_not_found',
    pg_temp.revisa('b0000000-0000-0000-0000-00000000f105', 'approved', null),
    'justification_not_found');
  perform pg_temp.assert_txt('id inexistente: justification_not_found (a mesma resposta)',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000ffff', 'approved', null),
    'justification_not_found');
end $$;

-- --- owner de A: aprova o marcado ---------------------------------------------
set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
do $$ begin
  perform pg_temp.assert_txt('owner aprova a justificativa do colaborador marcado',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f103', 'approved', null), 'ok');
end $$;

-- --- owner de B: tenant sem competência aberta --------------------------------
set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$ begin
  perform pg_temp.assert_txt('owner B alcança a justificativa de B — e B não tem aberta: no_open_period',
    pg_temp.revisa('b0000000-0000-0000-0000-00000000f105', 'approved', null), 'no_open_period');
  perform pg_temp.assert_txt('owner B com id de A: justification_not_found',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f106', 'approved', null),
    'justification_not_found');
end $$;

reset request.jwt.claim.sub;
reset role;

-- --- o que as chamadas deixaram -----------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('a justificativa revisada duas vezes tem UMA revisão',
    (select count(*) from app.justification_review
      where justification_id = 'a0000000-0000-0000-0000-00000000f101'), 1);
  perform pg_temp.assert_eq('aprovar gravou approved, pelo RH, na mais antiga aberta (2026/09)',
    (select count(*) from app.justification_review
      where justification_id = 'a0000000-0000-0000-0000-00000000f101'
        and decision = 'approved'
        and reviewed_by = '55555555-5555-5555-5555-555555555555'
        and payroll_period_id = 'a0000000-0000-0000-0000-00000000e209'), 1);
  perform pg_temp.assert_txt('aprovar moveu o desvio para justified',
    (select status from app.deviation_event where id = 'a0000000-0000-0000-0000-00000000ad01'),
    'justified');
  perform pg_temp.assert_txt('a justificativa aprovada continua pending (imutável)',
    (select status from app.justification where id = 'a0000000-0000-0000-0000-00000000f101'),
    'pending');
  perform pg_temp.assert_txt('reprovar deixou o desvio active',
    (select status from app.deviation_event where id = 'a0000000-0000-0000-0000-00000000ad02'),
    'active');
  perform pg_temp.assert_eq('e gravou a revisão rejected com o motivo',
    (select count(*) from app.justification_review
      where justification_id = 'a0000000-0000-0000-0000-00000000f102'
        and decision = 'rejected' and reason = 'Sem comprovante'), 1);
  perform pg_temp.assert_txt('o owner moveu o desvio do marcado para justified',
    (select status from app.deviation_event where id = 'a0000000-0000-0000-0000-00000000ad05'),
    'justified');
  perform pg_temp.assert_eq('as recusas não gravaram nada: espelho, B e o marcado pelo RH',
    (select count(*) from app.justification_review
      where justification_id in ('a0000000-0000-0000-0000-00000000f104',
                                 'b0000000-0000-0000-0000-00000000f105')), 0);
  perform pg_temp.assert_eq('o marcado tem só a revisão do owner',
    (select count(*) from app.justification_review
      where justification_id = 'a0000000-0000-0000-0000-00000000f103'
        and reviewed_by = '11111111-1111-1111-1111-111111111111'), 1);
end $$;

-- --- atomicidade: a revisão não fica se o desvio não se move -------------------
savepoint prova_da_atomicidade;

create function app.p12_boom() returns trigger language plpgsql as $$
begin
  raise exception 'p12_boom: update de deviation_event barrado';
end $$;
create trigger p12_boom before update on app.deviation_event
  for each row execute function app.p12_boom();

set local role authenticated;
set local request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
do $$
declare v_err text;
begin
  begin
    perform public.fn_revisar_justificativa('a0000000-0000-0000-0000-00000000f106', 'approved', null);
    v_err := null;
  exception when others then v_err := sqlerrm;
  end;
  perform pg_temp.assert_txt('a aprovação falhou NO UPDATE do desvio (depois do insert da revisão)',
    coalesce(v_err, 'sucesso'), 'p12_boom: update de deviation_event barrado');
end $$;
reset request.jwt.claim.sub;
reset role;

do $$ begin
  perform pg_temp.assert_eq('e a revisão NÃO ficou: aprovar é uma transação só',
    (select count(*) from app.justification_review
      where justification_id = 'a0000000-0000-0000-0000-00000000f106'), 0);
  perform pg_temp.assert_txt('e o desvio continua active',
    (select status from app.deviation_event where id = 'a0000000-0000-0000-0000-00000000ad06'),
    'active');
end $$;

rollback to savepoint prova_da_atomicidade;

-- --- leitura: review_read ------------------------------------------------------
set local role authenticated;

set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
do $$ begin
  perform pg_temp.assert_eq('supervisor de A Centro LÊ a revisão de A Centro',
    (select count(*) from app.justification_review
      where justification_id = 'a0000000-0000-0000-0000-00000000f101'), 1);
  perform pg_temp.assert_eq('supervisor de A Centro NÃO lê a revisão de A Norte',
    (select count(*) from app.justification_review
      where justification_id = 'a0000000-0000-0000-0000-00000000f102'), 0);
end $$;

set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
do $$ begin
  perform pg_temp.assert_eq('owner A lê as três revisões de A',
    (select count(*) from app.justification_review), 3);
  -- A fila do supervisor enxerga a alçada: reprovada volta, pendente e
  -- aprovada saem.
  perform pg_temp.assert_eq('reprovada volta à fila (fn_pending_justification)',
    (select count(*) from public.fn_pending_justification('2026-08-01', '2026-08-31')
      where deviation_event_id = 'a0000000-0000-0000-0000-00000000ad02'), 1);
  perform pg_temp.assert_eq('pendente esperando o RH sai da fila',
    (select count(*) from public.fn_pending_justification('2026-08-01', '2026-08-31')
      where deviation_event_id = 'a0000000-0000-0000-0000-00000000ad06'), 0);
end $$;

set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$ begin
  perform pg_temp.assert_eq('owner B NÃO lê revisão de A',
    (select count(*) from app.justification_review), 0);
end $$;

reset request.jwt.claim.sub;
reset role;

-- ---------------------------------------------------------------------------
\echo '--- Alçada (P1.2, ciclo 1): competência não fechada, not_pending e own_justification'
-- ---------------------------------------------------------------------------
-- Decisões do dono de 29/09/2026 sobre a reprovação da P1.2:
--   ALTO-1   a revisão vai para a competência NÃO FECHADA mais antiga (meses
--            1–12): o import grava `importada`, nada grava `aberta`.
--   MÉDIO-2  o mês 13 não recebe revisão, mesmo sendo o mais antigo.
--   MÉDIO-3  justificativa que não está `pending` é recusada: not_pending.
--   segregação  o autor não revisa a própria: own_justification; autor nulo
--            (todas as de cima) não bloqueia.
-- Cada recusa tem o positivo ao lado; cada escolha de competência é conferida
-- pelo id da competência gravada, não só por "devolveu id".
insert into app.justification (id, tenant_id, deviation_event_id, employee_id, reference_date, text, status, source, author_user_id) values
  ('b0000000-0000-0000-0000-00000000f107','bbbbbbbb-0000-0000-0000-000000000002',null,'b0000000-0000-0000-0000-0000000000c1','2026-08-11','Segunda de B','pending','operax',null),
  ('a0000000-0000-0000-0000-00000000f108','aaaaaaaa-0000-0000-0000-000000000001',null,'a0000000-0000-0000-0000-0000000000c1','2026-08-13','Legada aceita','accepted','operax',null),
  ('a0000000-0000-0000-0000-00000000f109','aaaaaaaa-0000-0000-0000-000000000001',null,'a0000000-0000-0000-0000-0000000000c1','2026-08-14','Legada rejeitada','rejected','operax',null),
  ('a0000000-0000-0000-0000-00000000f110','aaaaaaaa-0000-0000-0000-000000000001',null,'a0000000-0000-0000-0000-0000000000c1','2026-08-17','Escrita pelo RH','pending','operax','55555555-5555-5555-5555-555555555555'),
  ('a0000000-0000-0000-0000-00000000f111','aaaaaaaa-0000-0000-0000-000000000001',null,'a0000000-0000-0000-0000-0000000000c1','2026-08-18','Escrita pelo supervisor','pending','operax','22222222-2222-2222-2222-222222222222'),
  ('a0000000-0000-0000-0000-00000000f112','aaaaaaaa-0000-0000-0000-000000000001',null,'a0000000-0000-0000-0000-0000000000c1','2026-08-19','Escrita pelo owner','pending','operax','11111111-1111-1111-1111-111111111111');

-- --- a competência de destino, em B (só a fechada 2026/09 até aqui) ---------
-- 1) O décimo terceiro NÃO FECHADO, e mais antigo que tudo, não recebe.
insert into app.payroll_period (id, tenant_id, year, month, status) values
  ('b0000000-0000-0000-0000-00000000e513','bbbbbbbb-0000-0000-0000-000000000002',2025,13,'importada');
set local role authenticated;
set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$ begin
  perform pg_temp.assert_txt('B com só a fechada e um mês 13 importada: no_open_period (o 13 não recebe)',
    pg_temp.revisa('b0000000-0000-0000-0000-00000000f105', 'approved', null), 'no_open_period');
end $$;
reset request.jwt.claim.sub;
reset role;

-- 2) Uma `conferida` recebe — e não a fechada mais antiga, nem o 13.
insert into app.payroll_period (id, tenant_id, year, month, status) values
  ('b0000000-0000-0000-0000-00000000e211','bbbbbbbb-0000-0000-0000-000000000002',2026,11,'conferida');
set local role authenticated;
set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$ begin
  perform pg_temp.assert_txt('competência conferida recebe a revisão',
    pg_temp.revisa('b0000000-0000-0000-0000-00000000f105', 'approved', null), 'ok');
end $$;
reset request.jwt.claim.sub;
reset role;

-- 3) Uma `importada` mais antiga que a conferida: é ela que recebe.
insert into app.payroll_period (id, tenant_id, year, month, status) values
  ('b0000000-0000-0000-0000-00000000e210','bbbbbbbb-0000-0000-0000-000000000002',2026,10,'importada');
set local role authenticated;
set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$ begin
  perform pg_temp.assert_txt('competência importada recebe a revisão',
    pg_temp.revisa('b0000000-0000-0000-0000-00000000f107', 'approved', null), 'ok');
  -- A recusa de status não vaza para o tenant vizinho: antes do not_pending
  -- vem o justification_not_found.
  perform pg_temp.assert_txt('owner B com a aceita legada de A: justification_not_found (não not_pending)',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f108', 'approved', null),
    'justification_not_found');
  perform pg_temp.assert_txt('owner B com a escrita pelo RH de A: justification_not_found',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f110', 'approved', null),
    'justification_not_found');
end $$;
reset request.jwt.claim.sub;
reset role;

do $$ begin
  perform pg_temp.assert_eq('a conferida 2026/11 recebeu — nem a fechada 2026/09 nem o 13 de 2025',
    (select count(*) from app.justification_review
      where justification_id = 'b0000000-0000-0000-0000-00000000f105'
        and payroll_period_id = 'b0000000-0000-0000-0000-00000000e211'), 1);
  perform pg_temp.assert_eq('a importada 2026/10, a não fechada mais antiga, recebeu',
    (select count(*) from app.justification_review
      where justification_id = 'b0000000-0000-0000-0000-00000000f107'
        and payroll_period_id = 'b0000000-0000-0000-0000-00000000e210'), 1);
  perform pg_temp.assert_eq('o mês 13 não recebeu revisão nenhuma',
    (select count(*) from app.justification_review
      where payroll_period_id = 'b0000000-0000-0000-0000-00000000e513'), 0);
end $$;

-- --- not_pending e own_justification, em A ----------------------------------
set local role authenticated;

set local request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
do $$ begin
  perform pg_temp.assert_txt('RH com a aceita legada: not_pending',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f108', 'rejected', 'contrária'), 'not_pending');
  perform pg_temp.assert_txt('RH com a rejeitada legada: not_pending',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f109', 'approved', null), 'not_pending');
  perform pg_temp.assert_txt('RH revisando a que ele escreveu: own_justification',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f110', 'approved', null), 'own_justification');
  perform pg_temp.assert_txt('RH aprova a escrita pelo supervisor (autor não nulo e alheio passa)',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f111', 'approved', null), 'ok');
  perform pg_temp.assert_txt('RH aprova a escrita pelo owner',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f112', 'approved', null), 'ok');
end $$;

set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
do $$ begin
  perform pg_temp.assert_txt('owner aprova a escrita pelo RH (a mesma que o RH não pôde)',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f110', 'approved', null), 'ok');
end $$;

reset request.jwt.claim.sub;
reset role;

-- O owner autor, isolado: a f112 já foi revisada pelo RH acima, e o
-- already_reviewed viria depois do own_justification de qualquer jeito — mas
-- a prova limpa é numa pendente sem revisão.
insert into app.justification (id, tenant_id, deviation_event_id, employee_id, reference_date, text, status, source, author_user_id) values
  ('a0000000-0000-0000-0000-00000000f113','aaaaaaaa-0000-0000-0000-000000000001',null,'a0000000-0000-0000-0000-0000000000c1','2026-08-20','Escrita pelo owner, sem revisão','pending','operax','11111111-1111-1111-1111-111111111111');
set local role authenticated;
set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
do $$ begin
  perform pg_temp.assert_txt('owner revisando a que ele escreveu: own_justification (o owner também)',
    pg_temp.revisa('a0000000-0000-0000-0000-00000000f113', 'approved', null), 'own_justification');
end $$;
reset request.jwt.claim.sub;
reset role;

do $$ begin
  perform pg_temp.assert_eq('as recusadas por not_pending e own_justification não gravaram nada',
    (select count(*) from app.justification_review
      where justification_id in ('a0000000-0000-0000-0000-00000000f108',
                                 'a0000000-0000-0000-0000-00000000f109',
                                 'a0000000-0000-0000-0000-00000000f113')), 0);
  perform pg_temp.assert_eq('a escrita pelo RH tem só a revisão do owner',
    (select count(*) from app.justification_review
      where justification_id = 'a0000000-0000-0000-0000-00000000f110'
        and reviewed_by = '11111111-1111-1111-1111-111111111111'), 1);
  perform pg_temp.assert_eq('e nenhuma revisão foi feita pelo próprio autor',
    (select count(*) from app.justification_review r
       join app.justification j on j.id = r.justification_id
      where r.reviewed_by = j.author_user_id), 0);
  perform pg_temp.assert_txt('as legadas continuam como estavam',
    (select string_agg(status, ',' order by id) from app.justification
      where id in ('a0000000-0000-0000-0000-00000000f108','a0000000-0000-0000-0000-00000000f109')),
    'accepted,rejected');
end $$;

-- ---------------------------------------------------------------------------
\echo '--- Alçada (P1.3): a fila de aprovação — competência 21→20, filtros e escopo'
-- ---------------------------------------------------------------------------
-- `public.fn_fila_aprovacao`, decisões do dono de 29/09/2026: janela 21→20 por
-- `util.competencia_janela`, `security invoker`, e só `hr`/`owner` recebem
-- linha (os demais recebem a fila VAZIA, e o backend responde 403 antes).
-- O cenário mora em nov/dez/2026 e jan/2027, longe das justificativas de
-- agosto acima, para cada borda ter uma linha só de cada lado:
--   q1  A Centro  2026-11-20  sem desvio  -> competência 2026/11, não 2026/12
--   q2  A Centro  2026-11-21  com desvio  -> 2026/12 (o 21 do mês anterior)
--   q3  A Norte   2026-12-20  com desvio  -> 2026/12 (o 20 do mês)
--   q4  A Norte   2026-12-21  com desvio  -> 2027/01 (virada de ano)
--   q5  B Sul     2026-12-01              -> só B
--   q6  A Centro  2026-12-05              -> aprovada pelo RH: sai
--   q7  A Norte   2026-12-06              -> reprovada pelo RH: sai
--   q8  A Centro  2026-12-07  accepted    -> legada decidida: nunca entra
--   q9  colaborador de A Centro, desvio de 2027-01-10 em A NORTE -> a unidade
--       da fila é a do dia (a do desvio), não a do cadastro de hoje
insert into app.deviation_event (id, tenant_id, employee_id, company_id, unit_id, reference_date, type, minutes, mode) values
  ('a0000000-0000-0000-0000-00000000ad12','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c1','a0000000-0000-0000-0000-0000000000e1','a0000000-0000-0000-0000-0000000000a1','2026-11-21','late_entry',-17,'production'),
  ('a0000000-0000-0000-0000-00000000ad13','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c2','a0000000-0000-0000-0000-0000000000e1','a0000000-0000-0000-0000-0000000000a2','2026-12-20','late_exit',41,'production'),
  ('a0000000-0000-0000-0000-00000000ad14','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c2','a0000000-0000-0000-0000-0000000000e1','a0000000-0000-0000-0000-0000000000a2','2026-12-21','late_entry',-8,'production'),
  ('a0000000-0000-0000-0000-00000000ad15','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-0000000000c1','a0000000-0000-0000-0000-0000000000e1','a0000000-0000-0000-0000-0000000000a2','2027-01-10','late_entry',-5,'production');

insert into app.justification (id, tenant_id, deviation_event_id, employee_id, reference_date, text, status, source, author_name) values
  ('a0000000-0000-0000-0000-0000000fa001','aaaaaaaa-0000-0000-0000-000000000001',null,'a0000000-0000-0000-0000-0000000000c1','2026-11-20','Fila q1','pending','operax',null),
  ('a0000000-0000-0000-0000-0000000fa002','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-00000000ad12','a0000000-0000-0000-0000-0000000000c1','2026-11-21','Fila q2','pending','operax','Supervisor A'),
  ('a0000000-0000-0000-0000-0000000fa003','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-00000000ad13','a0000000-0000-0000-0000-0000000000c2','2026-12-20','Fila q3','pending','operax','Supervisor Norte'),
  ('a0000000-0000-0000-0000-0000000fa004','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-00000000ad14','a0000000-0000-0000-0000-0000000000c2','2026-12-21','Fila q4','pending','operax',null),
  ('b0000000-0000-0000-0000-0000000fa005','bbbbbbbb-0000-0000-0000-000000000002',null,'b0000000-0000-0000-0000-0000000000c1','2026-12-01','Fila q5','pending','operax',null),
  ('a0000000-0000-0000-0000-0000000fa006','aaaaaaaa-0000-0000-0000-000000000001',null,'a0000000-0000-0000-0000-0000000000c1','2026-12-05','Fila q6','pending','operax',null),
  ('a0000000-0000-0000-0000-0000000fa007','aaaaaaaa-0000-0000-0000-000000000001',null,'a0000000-0000-0000-0000-0000000000c2','2026-12-06','Fila q7','pending','operax',null),
  ('a0000000-0000-0000-0000-0000000fa008','aaaaaaaa-0000-0000-0000-000000000001',null,'a0000000-0000-0000-0000-0000000000c1','2026-12-07','Fila q8','accepted','operax',null),
  ('a0000000-0000-0000-0000-0000000fa009','aaaaaaaa-0000-0000-0000-000000000001','a0000000-0000-0000-0000-00000000ad15','a0000000-0000-0000-0000-0000000000c1','2027-01-10','Fila q9','pending','operax',null);

-- Os ids que a fila devolveu, na ordem da fila, com o prefixo cortado: 'q2,q3'.
create or replace function pg_temp.fila(
  p_year int, p_month int, p_unit uuid default null, p_employee uuid default null,
  p_de date default null, p_ate date default null)
returns text language sql as $$
  select coalesce(string_agg('q' || right(f.justification_id::text, 1), ','
                             order by f.reference_date, f.justification_id), '')
    from public.fn_fila_aprovacao(p_year, p_month, p_unit, p_employee, p_de, p_ate) f
   where f.justification_id::text like '%0000000fa00_';
$$;

do $$ begin
  perform pg_temp.assert_eq('authenticated EXECUTA public.fn_fila_aprovacao',
    case when has_function_privilege('authenticated',
           'public.fn_fila_aprovacao(integer,integer,uuid,uuid,date,date)', 'execute')
         then 1 else 0 end, 1);
  perform pg_temp.assert_eq('anon NÃO executa public.fn_fila_aprovacao',
    case when has_function_privilege('anon',
           'public.fn_fila_aprovacao(integer,integer,uuid,uuid,date,date)', 'execute')
         then 1 else 0 end, 0);
  perform pg_temp.assert_eq('anon NÃO executa util.competencia_janela',
    case when has_function_privilege('anon', 'util.competencia_janela(integer,integer)', 'execute')
         then 1 else 0 end, 0);
  perform pg_temp.assert_eq('fn_fila_aprovacao é security INVOKER (a RLS do chamador vale)',
    (select case when p.prosecdef then 1 else 0 end from pg_proc p
      where p.oid = 'public.fn_fila_aprovacao(integer,integer,uuid,uuid,date,date)'::regprocedure), 0);
  perform pg_temp.assert_eq('a janela da fila vem de util.competencia_janela, não de constante',
    (select case when pg_get_functiondef(p.oid) like '%util.competencia_janela(p_year, p_month)%'
                 then 1 else 0 end from pg_proc p
      where p.oid = 'public.fn_fila_aprovacao(integer,integer,uuid,uuid,date,date)'::regprocedure), 1);
  perform pg_temp.assert_txt('competência 2027/01 = 21/12/2026 a 20/01/2027 (virada de ano)',
    (select period_start || '..' || period_end from util.competencia_janela(2027, 1)),
    '2026-12-21..2027-01-20');
  perform pg_temp.assert_txt('competência 2024/03 = 21/02 a 20/03 (bissexto não muda o 21)',
    (select period_start || '..' || period_end from util.competencia_janela(2024, 3)),
    '2024-02-21..2024-03-20');
end $$;

set local role authenticated;

-- --- RH de A: a fila do tenant, recortada pela janela e pelos filtros --------
set local request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
do $$ begin
  perform pg_temp.assert_txt('RH: fila 2026/12 = q2 (dia 21 de nov), q3 (dia 20), q6, q7 — sem q8 legada',
    pg_temp.fila(2026, 12), 'q2,q6,q7,q3');
  perform pg_temp.assert_txt('RH: o dia 20 de nov é da competência 2026/11, e o 21 não',
    pg_temp.fila(2026, 11), 'q1');
  perform pg_temp.assert_txt('RH: o dia 21 de dez é da competência 2027/01 (virada de ano)',
    pg_temp.fila(2027, 1), 'q4,q9');
  perform pg_temp.assert_txt('RH: a unidade da fila é a do desvio (q9 em A Norte, cadastro em A Centro)',
    pg_temp.fila(2027, 1, 'a0000000-0000-0000-0000-0000000000a2'), 'q4,q9');
  perform pg_temp.assert_txt('RH: e q9 não aparece pela unidade do cadastro (A Centro)',
    pg_temp.fila(2027, 1, 'a0000000-0000-0000-0000-0000000000a1'), '');
  perform pg_temp.assert_txt('RH: filtro de colaborador (Colab A Norte)',
    pg_temp.fila(2026, 12, null, 'a0000000-0000-0000-0000-0000000000c2'), 'q7,q3');
  perform pg_temp.assert_txt('RH: filtro de unidade (A Centro)',
    pg_temp.fila(2026, 12, 'a0000000-0000-0000-0000-0000000000a1'), 'q2,q6');
  perform pg_temp.assert_txt('RH: filtro de um dia (de = até = 20/12)',
    pg_temp.fila(2026, 12, null, null, '2026-12-20', '2026-12-20'), 'q3');
  perform pg_temp.assert_txt('RH: só o "de" (a partir de 06/12)',
    pg_temp.fila(2026, 12, null, null, '2026-12-06', null), 'q7,q3');
  perform pg_temp.assert_txt('RH: só o "até" (até 30/11)',
    pg_temp.fila(2026, 12, null, null, null, '2026-11-30'), 'q2');
  perform pg_temp.assert_txt('RH: a data fora da janela não alarga a janela (21/12 a 31/12 em 2026/12)',
    pg_temp.fila(2026, 12, null, null, '2026-12-21', '2026-12-31'), '');
  perform pg_temp.assert_txt('RH: a linha traz colaborador, unidade, tipo, minutos, texto e autor do desvio',
    (select f.employee_name || '|' || f.unit_name || '|' || f.type || '|' || f.type_description
            || '|' || f.minutes || '|' || f.text || '|' || f.author_name
            || '|' || (f.created_at is not null)
       from public.fn_fila_aprovacao(2026, 12, null, null, null, null) f
      where f.justification_id = 'a0000000-0000-0000-0000-0000000fa003'),
    'Colab A Norte|A Norte|late_exit|' ||
      (select description from app.deviation_type where code = 'late_exit') ||
      '|41|Fila q3|Supervisor Norte|true');
  perform pg_temp.assert_txt('RH: justificativa sem desvio vem com a unidade do colaborador e sem tipo',
    (select coalesce(f.type, '<nulo>') || '|' || f.unit_name
       from public.fn_fila_aprovacao(2026, 11, null, null, null, null) f
      where f.justification_id = 'a0000000-0000-0000-0000-0000000fa001'),
    '<nulo>|A Centro');
  perform pg_temp.assert_txt('RH de A: a de B não aparece por colaborador de B',
    pg_temp.fila(2026, 12, null, 'b0000000-0000-0000-0000-0000000000c1'), '');
  perform pg_temp.assert_txt('RH de A: a de B não aparece por unidade de B',
    pg_temp.fila(2026, 12, 'b0000000-0000-0000-0000-0000000000a1'), '');

  -- A revisão tira da fila — aprovada ou reprovada.
  perform pg_temp.assert_txt('RH aprova q6',
    pg_temp.revisa('a0000000-0000-0000-0000-0000000fa006', 'approved', null), 'ok');
  perform pg_temp.assert_txt('RH reprova q7',
    pg_temp.revisa('a0000000-0000-0000-0000-0000000fa007', 'rejected', 'Sem comprovante'), 'ok');
  perform pg_temp.assert_txt('RH: aprovada e reprovada saíram da fila 2026/12',
    pg_temp.fila(2026, 12), 'q2,q3');
end $$;

-- --- owner de A: a mesma fila ---------------------------------------------------
set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
do $$ begin
  perform pg_temp.assert_txt('owner A: fila 2026/12 = a do RH', pg_temp.fila(2026, 12), 'q2,q3');
end $$;

-- --- supervisor de A Centro: nada, por nenhum filtro ----------------------------
set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
do $$ begin
  perform pg_temp.assert_eq('supervisor ENXERGA q2 na tabela (a fila vazia não é de escopo)',
    (select count(*) from app.justification where id = 'a0000000-0000-0000-0000-0000000fa002'), 1);
  perform pg_temp.assert_txt('supervisor: fila 2026/12 sem filtro = vazia',
    pg_temp.fila(2026, 12), '');
  perform pg_temp.assert_txt('supervisor: por competência 2027/01 = vazia', pg_temp.fila(2027, 1), '');
  perform pg_temp.assert_txt('supervisor: pela unidade A Norte = vazia',
    pg_temp.fila(2026, 12, 'a0000000-0000-0000-0000-0000000000a2'), '');
  perform pg_temp.assert_txt('supervisor: pela própria unidade (A Centro) = vazia',
    pg_temp.fila(2026, 12, 'a0000000-0000-0000-0000-0000000000a1'), '');
  perform pg_temp.assert_txt('supervisor: pelo colaborador de A Norte = vazia',
    pg_temp.fila(2026, 12, null, 'a0000000-0000-0000-0000-0000000000c2'), '');
  perform pg_temp.assert_txt('supervisor: pela data 20/12 (a de A Norte) = vazia',
    pg_temp.fila(2026, 12, null, null, '2026-12-20', '2026-12-20'), '');
end $$;

-- --- DP e contabilidade: também nada --------------------------------------------
set local request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
do $$ begin
  perform pg_temp.assert_txt('DP (personnel): fila 2026/12 = vazia', pg_temp.fila(2026, 12), '');
end $$;
set local request.jwt.claim.sub = '66666666-6666-6666-6666-666666666666';
do $$ begin
  perform pg_temp.assert_txt('contabilidade: fila 2026/12 = vazia', pg_temp.fila(2026, 12), '');
end $$;

-- --- owner de B: só a de B --------------------------------------------------------
set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$ begin
  perform pg_temp.assert_txt('owner B: fila 2026/12 = só q5', pg_temp.fila(2026, 12), 'q5');
  perform pg_temp.assert_txt('owner B: pelo colaborador de A = vazia',
    pg_temp.fila(2026, 12, null, 'a0000000-0000-0000-0000-0000000000c1'), '');
  perform pg_temp.assert_txt('owner B: pela unidade de A = vazia',
    pg_temp.fila(2026, 12, 'a0000000-0000-0000-0000-0000000000a2'), '');
  perform pg_temp.assert_txt('owner B: pela data de A (20/12) = vazia',
    pg_temp.fila(2026, 12, null, null, '2026-12-20', '2026-12-20'), '');
end $$;

reset request.jwt.claim.sub;
reset role;

-- ---------------------------------------------------------------------------
\echo '--- Alçada (P1.3): can_review e blocked_reason — a fila diz o que a RPC recusaria'
-- ---------------------------------------------------------------------------
-- Decisão do dono de 29/09/2026: a linha bloqueada continua na fila, com o
-- motivo. A regra é a dos passos 3 e 4 de `fn_revisar_justificativa`, na ordem
-- dela — e a prova é a RPC: para cada linha, `pg_temp.paridade` tenta aprovar
-- (desfazendo) e confere que `can_review = false` ⇔ a RPC recusa com
-- exatamente `blocked_reason`. O cenário é a competência 2027/02, longe do resto:
--   qa  Colab A Centro           autor RH      -> RH: own_justification | owner: ok
--   qb  Analista RH (marcado)    autor nulo    -> RH: owner_only        | owner: ok
--   qc  Colab A Centro           autor owner   -> RH: ok                | owner: own_justification
--   qd  Analista RH (marcado)    autor RH      -> RH: own_justification (as duas valem;
--                                                 a RPC diz esta primeiro) | owner: ok
insert into app.justification (id, tenant_id, deviation_event_id, employee_id, reference_date, text, status, source, author_user_id) values
  ('a0000000-0000-0000-0000-0000000fa00a','aaaaaaaa-0000-0000-0000-000000000001',null,'a0000000-0000-0000-0000-0000000000c1','2027-02-01','Fila qa','pending','operax','55555555-5555-5555-5555-555555555555'),
  ('a0000000-0000-0000-0000-0000000fa00b','aaaaaaaa-0000-0000-0000-000000000001',null,'a0000000-0000-0000-0000-0000000000c3','2027-02-02','Fila qb','pending','operax',null),
  ('a0000000-0000-0000-0000-0000000fa00c','aaaaaaaa-0000-0000-0000-000000000001',null,'a0000000-0000-0000-0000-0000000000c1','2027-02-03','Fila qc','pending','operax','11111111-1111-1111-1111-111111111111'),
  ('a0000000-0000-0000-0000-0000000fa00d','aaaaaaaa-0000-0000-0000-000000000001',null,'a0000000-0000-0000-0000-0000000000c3','2027-02-04','Fila qd','pending','operax','55555555-5555-5555-5555-555555555555');

-- 'qa=own_justification,qb=owner_only,...' — 'ok' quando can_review.
create or replace function pg_temp.fila_bloqueio(p_year int, p_month int)
returns text language sql as $$
  select coalesce(string_agg('q' || right(f.justification_id::text, 1) || '='
                             || case when f.can_review then 'ok' else f.blocked_reason end, ','
                             order by f.reference_date, f.justification_id), '')
    from public.fn_fila_aprovacao(p_year, p_month) f
   where f.justification_id::text like '%0000000fa00_';
$$;

-- As linhas em que a fila e a RPC discordam, com o que cada uma disse. A
-- aprovação é desfeita pela exceção OXP13 — só ela é engolida.
create or replace function pg_temp.paridade(p_year int, p_month int)
returns text language plpgsql as $$
declare r record; v text; falhas text := ''; n int := 0;
begin
  for r in select * from public.fn_fila_aprovacao(p_year, p_month) loop
    n := n + 1;
    begin
      v := pg_temp.revisa(r.justification_id, 'approved', null);
      raise exception using errcode = 'OXP13', message = v;
    exception when sqlstate 'OXP13' then v := sqlerrm;
    end;
    if r.can_review is null
       or (r.can_review and (r.blocked_reason is not null
                             or v in ('own_justification', 'owner_only')))
       or (not r.can_review and v is distinct from r.blocked_reason) then
      falhas := falhas || format('%s(fila %s/%s, RPC %s) ', r.justification_id,
                                 r.can_review, r.blocked_reason, v);
    end if;
  end loop;
  return n || ' linhas; ' || coalesce(nullif(falhas, ''), 'sem divergência');
end $$;

set local role authenticated;

set local request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
do $$ begin
  perform pg_temp.assert_txt('RH: autor RH own_justification, marcado owner_only, autor owner ok, os dois -> own_justification',
    pg_temp.fila_bloqueio(2027, 2), 'qa=own_justification,qb=owner_only,qc=ok,qd=own_justification');
  perform pg_temp.assert_txt('RH: autor nulo pode revisar (q2, q3)',
    pg_temp.fila_bloqueio(2026, 12), 'q2=ok,q3=ok');
  perform pg_temp.assert_txt('RH: a RPC recusa exatamente o que a fila bloqueia (2027/02)',
    pg_temp.paridade(2027, 2), '4 linhas; sem divergência');
  perform pg_temp.assert_txt('RH: e não recusa por esses códigos o que a fila libera (2026/12)',
    pg_temp.paridade(2026, 12), '2 linhas; sem divergência');
end $$;

set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
do $$ begin
  perform pg_temp.assert_txt('owner: marcado ok, autor owner own_justification, autor RH ok',
    pg_temp.fila_bloqueio(2027, 2), 'qa=ok,qb=ok,qc=own_justification,qd=ok');
  perform pg_temp.assert_txt('owner: a RPC recusa exatamente o que a fila bloqueia (2027/02)',
    pg_temp.paridade(2027, 2), '4 linhas; sem divergência');
end $$;

reset request.jwt.claim.sub;
reset role;

do $$ begin
  perform pg_temp.assert_eq('a paridade não deixou revisão nenhuma (as aprovações foram desfeitas)',
    (select count(*) from app.justification_review
      where justification_id in ('a0000000-0000-0000-0000-0000000fa00a','a0000000-0000-0000-0000-0000000fa00b',
                                 'a0000000-0000-0000-0000-0000000fa00c','a0000000-0000-0000-0000-0000000fa00d',
                                 'a0000000-0000-0000-0000-0000000fa002','a0000000-0000-0000-0000-0000000fa003')), 0);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- Alçada (P1.3, ciclo 1): o papel vale no tenant DA LINHA, não em qualquer tenant'
-- ---------------------------------------------------------------------------
-- Um usuário `hr` em A e `unit_supervisor` em B, com escopo em B Sul: a RLS o
-- deixa LER a justificativa de B (a prova abaixo), então o que a tira da fila
-- dele só pode ser o papel checado no tenant da linha. Sem este usuário, "hr em
-- qualquer tenant" e "hr no tenant da linha" davam o mesmo resultado em todas
-- as fixtures acima. O backend recusa esse usuário (`AmbiguousTenantMembership`);
-- o banco não, e a garantia é do banco.
insert into auth.users (id, email) values
  ('77777777-7777-7777-7777-777777777777', 'rh.a.sup.b@teste');
insert into app.tenant_member (tenant_id, user_id, role) values
  ('aaaaaaaa-0000-0000-0000-000000000001', '77777777-7777-7777-7777-777777777777', 'hr'),
  ('bbbbbbbb-0000-0000-0000-000000000002', '77777777-7777-7777-7777-777777777777', 'unit_supervisor');
insert into app.user_scope (tenant_id, user_id, unit_id) values
  ('bbbbbbbb-0000-0000-0000-000000000002', '77777777-7777-7777-7777-777777777777', 'b0000000-0000-0000-0000-0000000000a1');

set local role authenticated;
set local request.jwt.claim.sub = '77777777-7777-7777-7777-777777777777';
do $$ begin
  perform pg_temp.assert_eq('hr-A/supervisor-B LÊ a justificativa q5 de B (a RLS deixa)',
    (select count(*) from app.justification where id = 'b0000000-0000-0000-0000-0000000fa005'), 1);
  perform pg_temp.assert_txt('hr-A/supervisor-B: fila 2026/12 = a de A, sem q5 de B',
    pg_temp.fila(2026, 12), 'q2,q3');
  perform pg_temp.assert_txt('hr-A/supervisor-B: pelo colaborador de B = vazia',
    pg_temp.fila(2026, 12, null, 'b0000000-0000-0000-0000-0000000000c1'), '');
  perform pg_temp.assert_txt('hr-A/supervisor-B: pela unidade de B = vazia',
    pg_temp.fila(2026, 12, 'b0000000-0000-0000-0000-0000000000a1'), '');
end $$;
reset request.jwt.claim.sub;
reset role;

do $$ begin
  perform pg_temp.assert_txt('competencia_de: 20/12/2026 é 2026/12, 21/12/2026 é 2027/01',
    (select string_agg(c.period_year || '/' || c.period_month, ',' order by d)
       from unnest(array['2026-12-20','2026-12-21']::date[]) d,
            util.competencia_de(d) c),
    '2026/12,2027/1');
  perform pg_temp.assert_eq('anon NÃO executa util.competencia_de',
    case when has_function_privilege('anon', 'util.competencia_de(date)', 'execute')
         then 1 else 0 end, 0);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- Alçada (P1.2b): authenticated só LÊ justification, deviation_event e employee'
-- ---------------------------------------------------------------------------
-- Os três contornos da alçada, fechados pela migration `alcada_revoke_writes`
-- (decisão do dono, 29/09/2026): inserir justificativa já `accepted`, mover o
-- desvio para `justified` por UPDATE, e o `hr` zerar a própria
-- `approval_owner_only`. Cada negativo tem o positivo que o separa de "o banco
-- recusa tudo": a LEITURA das três tabelas continua a mesma, papel por papel.
do $$
declare
  v_tabela text;
begin
  foreach v_tabela in array array['app.justification', 'app.deviation_event', 'app.employee'] loop
    perform pg_temp.assert_eq('authenticated não escreve ' || v_tabela || ' (tabela)',
      (select count(*) from unnest(array['INSERT','UPDATE','DELETE']) v
        where has_table_privilege('authenticated', v_tabela, v)), 0);
    perform pg_temp.assert_eq('nem por coluna em ' || v_tabela,
      (select count(*) from unnest(array['INSERT','UPDATE']) v
        where has_any_column_privilege('authenticated', v_tabela, v)), 0);
    perform pg_temp.assert_eq('e LÊ ' || v_tabela || ' (o SELECT ficou)',
      case when has_table_privilege('authenticated', v_tabela, 'SELECT') then 1 else 0 end, 1);
  end loop;
  perform pg_temp.assert_eq('as três policies de escrita saíram',
    (select count(*) from pg_policies
      where schemaname = 'app'
        and policyname in ('justification_write', 'deviation_write', 'employee_write')), 0);
  perform pg_temp.assert_eq('as três de leitura ficaram',
    (select count(*) from pg_policies
      where schemaname = 'app' and cmd = 'SELECT'
        and (tablename, policyname) in (('justification', 'justification_read'),
                                        ('deviation_event', 'deviation_read'),
                                        ('employee', 'employee_read'))), 3);
end $$;

-- A leitura de ANTES, avaliada como `postgres` com o usuário na sessão: a soma
-- (OR) das policies de SELECT do catálogo e, em `app.employee`, também o
-- `using` da `employee_write` que saiu (`util.is_admin(tenant_id)` — ela era
-- `for all`, então também dava SELECT). Se a leitura de agora, pela RLS, bate
-- com esta, tirar a `employee_write` não mudou o que ninguém lê.
create temporary table p12b_leitura (user_id uuid, tabela text, esperado bigint);
grant select on p12b_leitura to authenticated;

do $$
declare
  v_user   uuid;
  v_tabela text;
  v_expr   text;
  v_n      bigint;
begin
  foreach v_user in array array[
    '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222',
    '33333333-3333-3333-3333-333333333333', '44444444-4444-4444-4444-444444444444',
    '55555555-5555-5555-5555-555555555555', '66666666-6666-6666-6666-666666666666',
    '77777777-7777-7777-7777-777777777777']::uuid[] loop
    perform set_config('request.jwt.claim.sub', v_user::text, true);
    foreach v_tabela in array array['justification', 'deviation_event', 'employee'] loop
      select string_agg('(' || qual || ')', ' or ') into v_expr
        from pg_policies
       where schemaname = 'app' and tablename = v_tabela and cmd = 'SELECT';
      if v_expr is null then
        raise exception 'FALHA: app.% sem policy de leitura', v_tabela;
      end if;
      if v_tabela = 'employee' then
        v_expr := v_expr || ' or util.is_admin(tenant_id)';
      end if;
      execute format('select count(*) from app.%I where %s', v_tabela, v_expr) into v_n;
      insert into p12b_leitura values (v_user, v_tabela, v_n);
    end loop;
  end loop;
end $$;
reset request.jwt.claim.sub;

-- E as contagens MEDIDAS pela RLS na árvore sem a migration (30/09/2026), por
-- usuário. Elas amarram o "antes" a um número, e não só ao catálogo: se um dos
-- dois lados mudar, as duas comparações abaixo discordam.
create temporary table p12b_medido (user_id uuid, tabela text, medido bigint);
grant select on p12b_medido to authenticated;
insert into p12b_medido (user_id, tabela, medido)
select u::uuid, t, n
from (values
  ('11111111-1111-1111-1111-111111111111', 23, 9, 3),   -- owner A
  ('22222222-2222-2222-2222-222222222222', 19, 4, 2),   -- supervisor de A Centro
  ('33333333-3333-3333-3333-333333333333', 23, 9, 3),   -- DP A
  ('44444444-4444-4444-4444-444444444444',  3, 1, 1),   -- owner B
  ('55555555-5555-5555-5555-555555555555', 23, 9, 3),   -- hr A
  ('66666666-6666-6666-6666-666666666666', 23, 8, 3),   -- contabilidade A (não é admin)
  ('77777777-7777-7777-7777-777777777777', 26, 10, 4)   -- hr A / supervisor de B
) as m(u, j, d, e)
cross join lateral (values ('justification', j), ('deviation_event', d), ('employee', e)) as x(t, n);

do $$ begin
  perform pg_temp.assert_eq('as 21 leituras de antes foram medidas (7 usuários x 3 tabelas)',
    (select count(*) from p12b_leitura l join p12b_medido m using (user_id, tabela)), 21);
end $$;

set local role authenticated;
do $$
declare
  r   record;
  v_n bigint;
begin
  for r in select l.user_id, l.tabela, l.esperado, m.medido
             from p12b_leitura l join p12b_medido m using (user_id, tabela)
            order by l.user_id, l.tabela loop
    perform set_config('request.jwt.claim.sub', r.user_id::text, true);
    execute format('select count(*) from app.%I', r.tabela) into v_n;
    perform pg_temp.assert_eq(
      'leitura de app.' || r.tabela || ' por ' || left(r.user_id::text, 8) || ' = a medida antes',
      v_n, r.medido);
    perform pg_temp.assert_eq(
      '  e = a soma das policies de antes (catálogo)', v_n, r.esperado);
  end loop;
end $$;
reset request.jwt.claim.sub;
reset role;

-- --- os negativos: cada contorno, por cada papel que o alcançava ------------
-- `insufficient_privilege` (42501) é também o código da RLS recusando uma linha
-- nova. Aceitar o código sozinho deixaria o negativo verde com o grant de volta
-- e só a policy faltando — então a mensagem tem de ser a do GRANT.
create or replace function pg_temp.p12b_sem_grant(p_msg text)
returns void language plpgsql as $$
begin
  if p_msg not like 'permission denied for table %' then
    raise exception 'FALHA: recusado, mas não por falta de grant: %', p_msg;
  end if;
end $$;

set local role authenticated;
do $$
declare
  v_user uuid;
begin
  foreach v_user in array array[
    '11111111-1111-1111-1111-111111111111',   -- owner A
    '55555555-5555-5555-5555-555555555555',   -- hr A
    '22222222-2222-2222-2222-222222222222'    -- supervisor de A Centro
  ]::uuid[] loop
    perform set_config('request.jwt.claim.sub', v_user::text, true);

    -- 1. Justificativa nascida `accepted`, no colaborador que os três enxergam.
    begin
      insert into app.justification (tenant_id, deviation_event_id, employee_id, reference_date, text, status, source)
      values ('aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-00000000ad06',
              'a0000000-0000-0000-0000-0000000000c1', '2026-08-12', 'contorno', 'accepted', 'operax');
      raise exception 'FALHA: % inseriu justificativa accepted direto', left(v_user::text, 8);
    exception when insufficient_privilege then
      perform pg_temp.p12b_sem_grant(sqlerrm);
      raise notice '  ok  % não insere justificativa accepted (permission denied)', left(v_user::text, 8);
    end;

    -- 2. O desvio movido para `justified` sem passar pela RPC.
    begin
      update app.deviation_event set status = 'justified'
       where id = 'a0000000-0000-0000-0000-00000000ad06';
      raise exception 'FALHA: % fez UPDATE em app.deviation_event', left(v_user::text, 8);
    exception when insufficient_privilege then
      perform pg_temp.p12b_sem_grant(sqlerrm);
      raise notice '  ok  % não move o desvio para justified (permission denied)', left(v_user::text, 8);
    end;
  end loop;

  -- 3. O `hr` zerando a própria marca — e, para cobrir os três verbos, o owner
  --    inserindo e apagando colaborador.
  perform set_config('request.jwt.claim.sub', '55555555-5555-5555-5555-555555555555', true);
  begin
    update app.employee set approval_owner_only = false
     where id = 'a0000000-0000-0000-0000-0000000000c3';
    raise exception 'FALHA: hr fez UPDATE em app.employee';
  exception when insufficient_privilege then
      perform pg_temp.p12b_sem_grant(sqlerrm);
    raise notice '  ok  hr não zera approval_owner_only (permission denied)';
  end;

  perform set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', true);
  begin
    insert into app.employee (tenant_id, company_id, unit_id, name)
    values ('aaaaaaaa-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-0000000000e1',
            'a0000000-0000-0000-0000-0000000000a1', 'contorno');
    raise exception 'FALHA: owner fez INSERT em app.employee';
  exception when insufficient_privilege then
      perform pg_temp.p12b_sem_grant(sqlerrm);
    raise notice '  ok  owner não insere colaborador (permission denied)';
  end;
  begin
    delete from app.employee where id = 'a0000000-0000-0000-0000-0000000000c3';
    raise exception 'FALHA: owner fez DELETE em app.employee';
  exception when insufficient_privilege then
      perform pg_temp.p12b_sem_grant(sqlerrm);
    raise notice '  ok  owner não apaga colaborador (permission denied)';
  end;
end $$;
reset request.jwt.claim.sub;
reset role;

do $$ begin
  perform pg_temp.assert_eq('nada entrou: nenhuma justificativa "contorno"',
    (select count(*) from app.justification where text = 'contorno'), 0);
  perform pg_temp.assert_eq('o desvio ad06 não foi movido por UPDATE direto',
    (select count(*) from app.deviation_event
      where id = 'a0000000-0000-0000-0000-00000000ad06' and status = 'justified'), 0);
  perform pg_temp.assert_eq('a marca do colaborador do RH continua de pé',
    (select count(*) from app.employee
      where id = 'a0000000-0000-0000-0000-0000000000c3' and approval_owner_only), 1);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- Alçada (P1.2b, ciclo 1): authenticated só LÊ tenant_member e user_scope'
-- ---------------------------------------------------------------------------
-- O quarto e o quinto contornos (decisão do dono, 30/09/2026): com
-- `tenant_member_admin`, o `hr` se promovia a `owner` e o `personnel` a `hr` —
-- e o papel é exatamente o que `fn_revisar_justificativa` confere. Com
-- `escopo_admin`, todo admin redesenhava o recorte de qualquer usuário. Mesma
-- forma do bloco acima: estrutura, a leitura igual papel por papel, e o
-- negativo pela mensagem do GRANT (`pg_temp.p12b_sem_grant`).
do $$
declare
  v_tabela text;
begin
  foreach v_tabela in array array['app.tenant_member', 'app.user_scope'] loop
    perform pg_temp.assert_eq('authenticated não escreve ' || v_tabela || ' (tabela)',
      (select count(*) from unnest(array['INSERT','UPDATE','DELETE']) v
        where has_table_privilege('authenticated', v_tabela, v)), 0);
    perform pg_temp.assert_eq('nem por coluna em ' || v_tabela,
      (select count(*) from unnest(array['INSERT','UPDATE']) v
        where has_any_column_privilege('authenticated', v_tabela, v)), 0);
    perform pg_temp.assert_eq('e LÊ ' || v_tabela || ' (o SELECT ficou)',
      case when has_table_privilege('authenticated', v_tabela, 'SELECT') then 1 else 0 end, 1);
  end loop;
  perform pg_temp.assert_eq('tenant_member_admin e escopo_admin saíram',
    (select count(*) from pg_policies
      where schemaname = 'app'
        and (tablename, policyname) in (('tenant_member', 'tenant_member_admin'),
                                        ('user_scope', 'escopo_admin'))), 0);
  perform pg_temp.assert_eq('tenant_member_read e escopo_read ficaram',
    (select count(*) from pg_policies
      where schemaname = 'app' and cmd = 'SELECT'
        and (tablename, policyname) in (('tenant_member', 'tenant_member_read'),
                                        ('user_scope', 'escopo_read'))), 2);
end $$;

-- A leitura de ANTES pelo catálogo: as policies de SELECT somadas e o `using`
-- das duas `for all` que saíram (`util.is_admin(tenant_id)`, as duas).
create temporary table p12b2_leitura (user_id uuid, tabela text, esperado bigint);
grant select on p12b2_leitura to authenticated;

do $$
declare
  v_user   uuid;
  v_tabela text;
  v_expr   text;
  v_n      bigint;
begin
  foreach v_user in array array[
    '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222',
    '33333333-3333-3333-3333-333333333333', '44444444-4444-4444-4444-444444444444',
    '55555555-5555-5555-5555-555555555555', '66666666-6666-6666-6666-666666666666',
    '77777777-7777-7777-7777-777777777777']::uuid[] loop
    perform set_config('request.jwt.claim.sub', v_user::text, true);
    foreach v_tabela in array array['tenant_member', 'user_scope'] loop
      select string_agg('(' || qual || ')', ' or ') into v_expr
        from pg_policies
       where schemaname = 'app' and tablename = v_tabela and cmd = 'SELECT';
      if v_expr is null then
        raise exception 'FALHA: app.% sem policy de leitura', v_tabela;
      end if;
      v_expr := v_expr || ' or util.is_admin(tenant_id)';
      execute format('select count(*) from app.%I where %s', v_tabela, v_expr) into v_n;
      insert into p12b2_leitura values (v_user, v_tabela, v_n);
    end loop;
  end loop;
end $$;
reset request.jwt.claim.sub;

-- As contagens MEDIDAS pela RLS sem a extensão da migration (30/09/2026):
-- tenant_member / user_scope.
create temporary table p12b2_medido (user_id uuid, tabela text, medido bigint);
grant select on p12b2_medido to authenticated;
insert into p12b2_medido (user_id, tabela, medido)
select u::uuid, t, n
from (values
  ('11111111-1111-1111-1111-111111111111', 6, 2),   -- owner A
  ('22222222-2222-2222-2222-222222222222', 6, 1),   -- supervisor de A Centro (só o próprio escopo)
  ('33333333-3333-3333-3333-333333333333', 6, 2),   -- DP A
  ('44444444-4444-4444-4444-444444444444', 2, 1),   -- owner B
  ('55555555-5555-5555-5555-555555555555', 6, 2),   -- hr A
  ('66666666-6666-6666-6666-666666666666', 6, 1),   -- contabilidade A (só o próprio escopo)
  ('77777777-7777-7777-7777-777777777777', 8, 3)    -- hr A / supervisor de B
) as m(u, tm, us)
cross join lateral (values ('tenant_member', tm), ('user_scope', us)) as x(t, n);

do $$ begin
  perform pg_temp.assert_eq('as 14 leituras de antes foram medidas (7 usuários x 2 tabelas)',
    (select count(*) from p12b2_leitura l join p12b2_medido m using (user_id, tabela)), 14);
end $$;

set local role authenticated;
do $$
declare
  r   record;
  v_n bigint;
begin
  for r in select l.user_id, l.tabela, l.esperado, m.medido
             from p12b2_leitura l join p12b2_medido m using (user_id, tabela)
            order by l.user_id, l.tabela loop
    perform set_config('request.jwt.claim.sub', r.user_id::text, true);
    execute format('select count(*) from app.%I', r.tabela) into v_n;
    perform pg_temp.assert_eq(
      'leitura de app.' || r.tabela || ' por ' || left(r.user_id::text, 8) || ' = a medida antes',
      v_n, r.medido);
    perform pg_temp.assert_eq(
      '  e = a soma das policies de antes (catálogo)', v_n, r.esperado);
  end loop;
end $$;
reset request.jwt.claim.sub;
reset role;

-- --- os negativos ------------------------------------------------------------
set local role authenticated;
do $$ begin
  -- 4a. O `hr` se promovendo a `owner`.
  perform set_config('request.jwt.claim.sub', '55555555-5555-5555-5555-555555555555', true);
  begin
    update app.tenant_member set role = 'owner'
     where tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001'
       and user_id = '55555555-5555-5555-5555-555555555555';
    raise exception 'FALHA: hr se promoveu a owner';
  exception when insufficient_privilege then
    perform pg_temp.p12b_sem_grant(sqlerrm);
    raise notice '  ok  hr não se promove a owner (permission denied)';
  end;

  -- 4b. O `hr` inserindo membro (o owner de B como hr de A).
  begin
    insert into app.tenant_member (tenant_id, user_id, role)
    values ('aaaaaaaa-0000-0000-0000-000000000001', '44444444-4444-4444-4444-444444444444', 'hr');
    raise exception 'FALHA: hr inseriu membro';
  exception when insufficient_privilege then
    perform pg_temp.p12b_sem_grant(sqlerrm);
    raise notice '  ok  hr não insere membro (permission denied)';
  end;

  -- 5. O `hr` alterando o recorte do supervisor.
  begin
    update app.user_scope set unit_id = null
     where tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001'
       and user_id = '22222222-2222-2222-2222-222222222222';
    raise exception 'FALHA: hr alterou user_scope';
  exception when insufficient_privilege then
    perform pg_temp.p12b_sem_grant(sqlerrm);
    raise notice '  ok  hr não altera user_scope (permission denied)';
  end;

  -- 4c. O `personnel` se promovendo a `hr` — e aí aprovaria pela RPC.
  perform set_config('request.jwt.claim.sub', '33333333-3333-3333-3333-333333333333', true);
  begin
    update app.tenant_member set role = 'hr'
     where tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001'
       and user_id = '33333333-3333-3333-3333-333333333333';
    raise exception 'FALHA: personnel se promoveu a hr';
  exception when insufficient_privilege then
    perform pg_temp.p12b_sem_grant(sqlerrm);
    raise notice '  ok  personnel não se promove a hr (permission denied)';
  end;

  -- Os verbos que faltam, pelo owner: DELETE de membro, INSERT e DELETE de escopo.
  perform set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', true);
  begin
    delete from app.tenant_member
     where tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001'
       and user_id = '55555555-5555-5555-5555-555555555555';
    raise exception 'FALHA: owner apagou membro';
  exception when insufficient_privilege then
    perform pg_temp.p12b_sem_grant(sqlerrm);
    raise notice '  ok  owner não apaga membro (permission denied)';
  end;
  begin
    insert into app.user_scope (tenant_id, user_id, unit_id)
    values ('aaaaaaaa-0000-0000-0000-000000000001', '55555555-5555-5555-5555-555555555555',
            'a0000000-0000-0000-0000-0000000000a2');
    raise exception 'FALHA: owner inseriu user_scope';
  exception when insufficient_privilege then
    perform pg_temp.p12b_sem_grant(sqlerrm);
    raise notice '  ok  owner não insere user_scope (permission denied)';
  end;
  begin
    delete from app.user_scope
     where tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001'
       and user_id = '22222222-2222-2222-2222-222222222222';
    raise exception 'FALHA: owner apagou user_scope';
  exception when insufficient_privilege then
    perform pg_temp.p12b_sem_grant(sqlerrm);
    raise notice '  ok  owner não apaga user_scope (permission denied)';
  end;
end $$;
reset request.jwt.claim.sub;
reset role;

do $$ begin
  perform pg_temp.assert_eq('os papéis de A ficaram como estavam (hr segue hr, personnel segue personnel)',
    (select count(*) from app.tenant_member
      where tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001'
        and (user_id, role) in (('55555555-5555-5555-5555-555555555555'::uuid, 'hr'::app.user_role),
                                ('33333333-3333-3333-3333-333333333333'::uuid, 'personnel'::app.user_role))), 2);
  perform pg_temp.assert_eq('o owner de B não virou membro de A',
    (select count(*) from app.tenant_member
      where tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001'
        and user_id = '44444444-4444-4444-4444-444444444444'), 0);
  perform pg_temp.assert_eq('o recorte do supervisor continua A Centro',
    (select count(*) from app.user_scope
      where user_id = '22222222-2222-2222-2222-222222222222'
        and unit_id = 'a0000000-0000-0000-0000-0000000000a1'), 1);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- Alçada (P1.4): o lançamento no Secullum — a marca entra só pela RPC, uma vez'
-- ---------------------------------------------------------------------------
-- `public.fn_marcar_lancado`, decisão do dono de 01/10/2026. Cada recusa tem ao
-- lado o positivo que a separa de "a RPC recusa tudo":
--   not_hr (supervisor, DP, contabilidade) x  hr e owner marcam
--   review_not_found (B, inexistente)     x  o owner de B marca a mesma de B
--   not_approved (reprovada)              x  a aprovada ao lado é marcada
--   already_posted                        x  a primeira marca entrou, e é UMA
-- As revisões de A vêm da P1.2: f101 aprovada (RH), f102 reprovada, f103 e
-- f110 aprovadas (owner), f111 e f112 aprovadas (RH). De B: f105 e f107.
-- O id de cada revisão vai para um GUC de sessão: o RH de A não a lê em B, e a
-- chamada precisa do id mesmo assim.
do $$ begin
  perform set_config('p14.' || right(justification_id::text, 4), id::text, false)
     from app.justification_review
    where justification_id in ('a0000000-0000-0000-0000-00000000f101','a0000000-0000-0000-0000-00000000f102',
                               'a0000000-0000-0000-0000-00000000f103','a0000000-0000-0000-0000-00000000f110',
                               'a0000000-0000-0000-0000-00000000f111','a0000000-0000-0000-0000-00000000f112',
                               'b0000000-0000-0000-0000-00000000f105','b0000000-0000-0000-0000-00000000f107');
end $$;

create or replace function pg_temp.rv(p_sufixo text) returns uuid
language sql as $$ select current_setting('p14.' || p_sufixo)::uuid $$;

-- Uma chamada, e o que ela respondeu: o código da recusa, ou 'ok'.
create or replace function pg_temp.lanca(p_review uuid)
returns text language plpgsql as $$
begin
  perform public.fn_marcar_lancado(p_review);
  return 'ok';
exception when sqlstate 'P0001' then return sqlerrm;
end $$;

-- As de A que o chamador LÊ, separadas: 'pendente:<ids>|lancada:<ids>'.
create or replace function pg_temp.lancamento_a() returns text
language sql as $$
  select coalesce(string_agg(right(r.justification_id::text, 4), ',' order by r.justification_id)
                    filter (where r.posted_to_source_at is null), '')
         || '|' ||
         coalesce(string_agg(right(r.justification_id::text, 4), ',' order by r.justification_id)
                    filter (where r.posted_to_source_at is not null), '')
    from app.justification_review r
   where r.decision = 'approved'
     and r.justification_id in ('a0000000-0000-0000-0000-00000000f101','a0000000-0000-0000-0000-00000000f103',
                                'a0000000-0000-0000-0000-00000000f110','a0000000-0000-0000-0000-00000000f111',
                                'a0000000-0000-0000-0000-00000000f112')
$$;

do $$ begin
  perform pg_temp.assert_eq('as oito revisões do cenário existem (P1.2)',
    (select count(*) from app.justification_review
      where id in (pg_temp.rv('f101'), pg_temp.rv('f102'), pg_temp.rv('f103'), pg_temp.rv('f110'),
                   pg_temp.rv('f111'), pg_temp.rv('f112'), pg_temp.rv('f105'), pg_temp.rv('f107'))), 8);
  perform pg_temp.assert_eq('nenhuma revisão nasce lançada',
    (select count(*) from app.justification_review where posted_to_source_at is not null
                                                       or posted_by is not null), 0);
  perform pg_temp.assert_eq('authenticated EXECUTA public.fn_marcar_lancado',
    case when has_function_privilege('authenticated', 'public.fn_marcar_lancado(uuid)', 'execute')
         then 1 else 0 end, 1);
  perform pg_temp.assert_eq('anon NÃO executa public.fn_marcar_lancado',
    case when has_function_privilege('anon', 'public.fn_marcar_lancado(uuid)', 'execute')
         then 1 else 0 end, 0);
  perform pg_temp.assert_eq('PUBLIC NÃO executa public.fn_marcar_lancado',
    (select count(*) from pg_proc p, aclexplode(p.proacl) a
      where p.oid = 'public.fn_marcar_lancado(uuid)'::regprocedure
        and a.grantee = 0 and a.privilege_type = 'EXECUTE'), 0);
  perform pg_temp.assert_eq('fn_marcar_lancado é security DEFINER (checa o papel ela mesma)',
    (select count(*) from pg_proc p
      where p.oid = 'public.fn_marcar_lancado(uuid)'::regprocedure and p.prosecdef), 1);
  perform pg_temp.assert_eq('authenticated continua sem UPDATE em app.justification_review (tabela e coluna)',
    case when has_table_privilege('authenticated', 'app.justification_review', 'UPDATE')
           or has_any_column_privilege('authenticated', 'app.justification_review', 'UPDATE')
         then 1 else 0 end, 0);
  perform pg_temp.assert_eq('app.justification_review segue só com review_read (nenhuma policy nova)',
    (select count(*) from pg_policies
      where schemaname = 'app' and tablename = 'justification_review'
        and policyname <> 'review_read'), 0);
end $$;

set local role authenticated;

-- --- quem não é do RH: nem marca, nem muda nada ------------------------------
set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
do $$ begin
  perform pg_temp.assert_eq('supervisor ENXERGA a revisão de A Centro (a recusa não é de escopo)',
    (select count(*) from app.justification_review where id = pg_temp.rv('f101')), 1);
  perform pg_temp.assert_txt('supervisor marcando lançado: not_hr',
    pg_temp.lanca(pg_temp.rv('f101')), 'not_hr');
  perform pg_temp.assert_txt('supervisor com id inexistente: not_hr (o papel vem antes da linha)',
    pg_temp.lanca('a0000000-0000-0000-0000-00000000ffff'), 'not_hr');
end $$;
set local request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
do $$ begin
  perform pg_temp.assert_txt('DP marcando lançado: not_hr',
    pg_temp.lanca(pg_temp.rv('f101')), 'not_hr');
end $$;
set local request.jwt.claim.sub = '66666666-6666-6666-6666-666666666666';
do $$ begin
  perform pg_temp.assert_txt('contabilidade marcando lançado: not_hr',
    pg_temp.lanca(pg_temp.rv('f101')), 'not_hr');
end $$;

-- --- RH de A ------------------------------------------------------------------
set local request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
do $$ begin
  perform pg_temp.assert_txt('RH de A antes de marcar: tudo pendente, nada lançado',
    pg_temp.lancamento_a(), 'f101,f103,f110,f111,f112|');
  perform pg_temp.assert_txt('RH de A com a revisão de B: review_not_found',
    pg_temp.lanca(pg_temp.rv('f105')), 'review_not_found');
  perform pg_temp.assert_txt('id inexistente: review_not_found (a mesma resposta)',
    pg_temp.lanca('a0000000-0000-0000-0000-00000000ffff'), 'review_not_found');
  perform pg_temp.assert_txt('revisão reprovada: not_approved',
    pg_temp.lanca(pg_temp.rv('f102')), 'not_approved');
  perform pg_temp.assert_txt('RH marca a aprovada f101',
    pg_temp.lanca(pg_temp.rv('f101')), 'ok');
  perform pg_temp.assert_txt('segunda marcação da f101: already_posted',
    pg_temp.lanca(pg_temp.rv('f101')), 'already_posted');
  perform pg_temp.assert_txt('a reprovada continua not_approved depois (não vira already_posted)',
    pg_temp.lanca(pg_temp.rv('f102')), 'not_approved');
  -- A porta direta continua fechada: só a RPC escreve a marca.
  begin
    update app.justification_review set posted_to_source_at = now(), posted_by = (select auth.uid())
     where id = pg_temp.rv('f103');
    raise exception 'FALHA: RH gravou posted_to_source_at por UPDATE direto';
  exception when insufficient_privilege then
    raise notice '  ok  RH não grava a marca por UPDATE direto (permission denied)';
  end;
end $$;

-- --- owner de A ---------------------------------------------------------------
set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
do $$ begin
  perform pg_temp.assert_txt('owner tentando remarcar a f101 (lançada pelo RH): already_posted',
    pg_temp.lanca(pg_temp.rv('f101')), 'already_posted');
  perform pg_temp.assert_txt('owner marca a aprovada f111',
    pg_temp.lanca(pg_temp.rv('f111')), 'ok');
  perform pg_temp.assert_txt('owner com a revisão de B: review_not_found',
    pg_temp.lanca(pg_temp.rv('f107')), 'review_not_found');
end $$;

-- --- hr em A e supervisor em B: o papel vale no tenant DA REVISÃO ------------
set local request.jwt.claim.sub = '77777777-7777-7777-7777-777777777777';
do $$ begin
  perform pg_temp.assert_txt('hr-A/supervisor-B com a revisão de B: review_not_found',
    pg_temp.lanca(pg_temp.rv('f105')), 'review_not_found');
end $$;

-- --- owner de B ---------------------------------------------------------------
set local request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$ begin
  perform pg_temp.assert_txt('owner B com a f101 de A, JÁ LANÇADA: review_not_found (não already_posted)',
    pg_temp.lanca(pg_temp.rv('f101')), 'review_not_found');
  perform pg_temp.assert_txt('owner B com a reprovada de A: review_not_found (não not_approved)',
    pg_temp.lanca(pg_temp.rv('f102')), 'review_not_found');
  perform pg_temp.assert_txt('owner B marca a f105 de B — a mesma que o RH de A não alcançou',
    pg_temp.lanca(pg_temp.rv('f105')), 'ok');
  perform pg_temp.assert_eq('owner B não lê revisão de A (nem a lançada)',
    (select count(*) from app.justification_review where tenant_id = 'aaaaaaaa-0000-0000-0000-000000000001'), 0);
end $$;

-- --- a lista separa pendente de lançado, para quem a lê -----------------------
set local request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
do $$ begin
  perform pg_temp.assert_txt('RH de A: pendentes f103,f110,f112 | lançadas f101,f111',
    pg_temp.lancamento_a(), 'f103,f110,f112|f101,f111');
end $$;
set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
do $$ begin
  perform pg_temp.assert_txt('owner de A vê a mesma separação',
    pg_temp.lancamento_a(), 'f103,f110,f112|f101,f111');
end $$;

reset request.jwt.claim.sub;
reset role;

-- --- o que as chamadas deixaram -----------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('a f101 tem UMA marca, do RH — a segunda e a do owner não sobrescreveram',
    (select count(*) from app.justification_review
      where id = pg_temp.rv('f101')
        and posted_to_source_at is not null
        and posted_by = '55555555-5555-5555-5555-555555555555'), 1);
  perform pg_temp.assert_eq('a f111 foi marcada pelo owner',
    (select count(*) from app.justification_review
      where id = pg_temp.rv('f111') and posted_to_source_at is not null
        and posted_by = '11111111-1111-1111-1111-111111111111'), 1);
  perform pg_temp.assert_eq('a f105 de B foi marcada pelo owner de B, e só por ele',
    (select count(*) from app.justification_review
      where id = pg_temp.rv('f105') and posted_to_source_at is not null
        and posted_by = '44444444-4444-4444-4444-444444444444'), 1);
  perform pg_temp.assert_eq('a reprovada não foi marcada',
    (select count(*) from app.justification_review
      where id = pg_temp.rv('f102') and (posted_to_source_at is not null or posted_by is not null)), 0);
  perform pg_temp.assert_eq('a f107 de B (só o owner de A tentou) continua sem marca',
    (select count(*) from app.justification_review
      where id = pg_temp.rv('f107') and (posted_to_source_at is not null or posted_by is not null)), 0);
  perform pg_temp.assert_eq('marca e autor andam juntos: nenhuma linha com um sem o outro',
    (select count(*) from app.justification_review
      where (posted_to_source_at is null) <> (posted_by is null)), 0);
  perform pg_temp.assert_eq('no total, exatamente três marcas (f101, f111, f105)',
    (select count(*) from app.justification_review where posted_to_source_at is not null), 3);
  perform pg_temp.assert_eq('marcar não mexeu na decisão de ninguém',
    (select count(*) from app.justification_review
      where id in (pg_temp.rv('f101'), pg_temp.rv('f111'), pg_temp.rv('f105'))
        and decision = 'approved'), 3);
end $$;

\echo ''
\echo '================================================'
\echo ' ISOLAMENTO MULTI-TENANT: TODOS OS TESTES OK'
\echo '================================================'

rollback;
