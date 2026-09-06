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
