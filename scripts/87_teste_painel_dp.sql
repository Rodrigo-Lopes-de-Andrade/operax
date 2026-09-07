-- ============================================================================
-- OperaX — TESTE DO PAINEL DE DP (os oito contadores de alerta)
-- ----------------------------------------------------------------------------
-- Duas garantias do gate do S4 que só valem contra Postgres de verdade, com
-- usuário de verdade:
--
--   A) As janelas vêm de `app.document_type.expiry_alert_days`, NÃO de constante.
--      Provado por mutação: muda-se a coluna e o contador muda; volta-se a
--      coluna e o contador volta. Um `90` escrito no SQL passaria por todo teste
--      de contagem e reprovaria aqui.
--   B) Supervisor de unidade não conta a outra unidade — E CONTA A DELE.
--      O negativo sozinho fica verde num banco onde ninguém lê nada, então cada
--      "ele não vê" vem com o "ele vê" ao lado, na mesma tabela de dados.
--
-- E uma terceira, que é o motivo de a função ser `security definer`:
--   C) O supervisor NÃO lê `app.employee_pii` (zero linhas, pela RLS) e ainda
--      assim recebe o contador de aniversariantes da unidade dele. Contar não é
--      ler. Se algum dia a função virar `security invoker`, o item C fica
--      vermelho — e é ele que explica por quê.
--
-- ⛔ Este arquivo NÃO substitui `scripts/98_teste_isolamento_tenant.sql`. Ele é
--    do painel; aquele é do modelo de acesso inteiro, e é de outro dono.
--
-- Roda em transação revertida. Não deixa resíduo.
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/87_teste_painel_dp.sql
-- ============================================================================

begin;

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

-- O contador, por código. Existe para que cada asserção abaixo seja uma linha
-- legível em vez de uma subconsulta repetida oito vezes.
create or replace function pg_temp.contador(p_code text)
returns bigint language sql stable as $$
  select a.total from public.fn_dp_alerts() a where a.code = p_code;
$$;

-- ---------------------------------------------------------------------------
-- Cenário
-- ---------------------------------------------------------------------------
-- Datas relativas a `current_date` de propósito: um teste de vencimento com data
-- fixa envelhece e passa a testar o passado.
insert into auth.users (id, email) values
  ('87000000-0000-0000-0000-000000000001', 'owner.painel@teste'),
  ('87000000-0000-0000-0000-000000000002', 'supervisor.painel@teste');

insert into app.tenant (id, slug, name) values
  ('87a70000-0000-0000-0000-0000000000a1', 'tenant-painel-a', 'Cliente Painel A'),
  ('87a70000-0000-0000-0000-0000000000a2', 'tenant-painel-b', 'Cliente Painel B');

insert into app.tenant_member (tenant_id, user_id, role) values
  ('87a70000-0000-0000-0000-0000000000a1', '87000000-0000-0000-0000-000000000001', 'owner'),
  ('87a70000-0000-0000-0000-0000000000a1', '87000000-0000-0000-0000-000000000002', 'unit_supervisor');

insert into app.company (id, tenant_id, legal_name) values
  ('87a70000-0000-0000-0000-0000000000e1', '87a70000-0000-0000-0000-0000000000a1', 'Empresa Painel A'),
  ('87a70000-0000-0000-0000-0000000000e2', '87a70000-0000-0000-0000-0000000000a2', 'Empresa Painel B');

insert into app.unit (id, tenant_id, company_id, code, name) values
  ('87a70000-0000-0000-0000-0000000000c1', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000e1', 'PAINEL-1', 'Unidade Painel 1'),
  ('87a70000-0000-0000-0000-0000000000c2', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000e1', 'PAINEL-2', 'Unidade Painel 2'),
  ('87a70000-0000-0000-0000-0000000000c3', '87a70000-0000-0000-0000-0000000000a2',
   '87a70000-0000-0000-0000-0000000000e2', 'PAINEL-3', 'Unidade Painel 3');

-- O supervisor enxerga a unidade 1 e nada mais. É a linha que `util.can_see_unit`
-- procura; sem ela ele não veria nem a dele, e o item B ficaria verde por vácuo.
insert into app.user_scope (tenant_id, user_id, unit_id) values
  ('87a70000-0000-0000-0000-0000000000a1', '87000000-0000-0000-0000-000000000002',
   '87a70000-0000-0000-0000-0000000000c1');

-- ⛔ NENHUMA LINHA EM `app.domain_permission` PARA ESTE TENANT, e isso é o teste.
-- Sem linha = negado (migration 02). O supervisor não alcança `pii` nem `health`,
-- e o item C prova que ele recebe a CONTAGEM mesmo assim.

insert into app.employee (id, tenant_id, company_id, unit_id, name, hired_on, status) values
  -- Ana: unidade 1, em experiência, aniversário no mês, férias hoje, férias no
  -- mês que vem, data limite dentro de 90 dias, um documento vencido e um a
  -- vencer em 40 dias.
  ('87a70000-0000-0000-0000-0000000000b1', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000e1', '87a70000-0000-0000-0000-0000000000c1',
   'Ana Painel', current_date - 10, 'active'),
  -- Bruno: unidade 2 — tudo o que é dele tem de sumir para o supervisor.
  ('87a70000-0000-0000-0000-0000000000b2', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000e1', '87a70000-0000-0000-0000-0000000000c2',
   'Bruno Painel', current_date - 10, 'active'),
  -- Carla: unidade 1, veterana, com ASO VENCIDO e sem documento ligado ao exame.
  -- Ela é quem prova que exame sem janela conhecida ainda conta depois de vencer.
  ('87a70000-0000-0000-0000-0000000000b3', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000e1', '87a70000-0000-0000-0000-0000000000c1',
   'Carla Painel', current_date - 2000, 'active'),
  -- Dilma: outro TENANT, aniversário no mês. O eixo de tenant tem de apagá-la.
  ('87a70000-0000-0000-0000-0000000000b4', '87a70000-0000-0000-0000-0000000000a2',
   '87a70000-0000-0000-0000-0000000000e2', '87a70000-0000-0000-0000-0000000000c3',
   'Dilma Painel', current_date - 10, 'active');

insert into app.employee_pii (employee_id, tenant_id, birth_date) values
  ('87a70000-0000-0000-0000-0000000000b1', '87a70000-0000-0000-0000-0000000000a1',
   (date_trunc('month', current_date) - interval '30 years')::date),
  ('87a70000-0000-0000-0000-0000000000b2', '87a70000-0000-0000-0000-0000000000a1',
   (date_trunc('month', current_date) - interval '30 years')::date),
  -- Carla faz aniversário daqui a seis meses: sem ela, "2 aniversariantes"
  -- também seria o resultado de contar todo mundo que tem data de nascimento.
  ('87a70000-0000-0000-0000-0000000000b3', '87a70000-0000-0000-0000-0000000000a1',
   (date_trunc('month', current_date) + interval '6 months' - interval '30 years')::date),
  ('87a70000-0000-0000-0000-0000000000b4', '87a70000-0000-0000-0000-0000000000a2',
   (date_trunc('month', current_date) - interval '30 years')::date);

insert into app.document_type (id, tenant_id, name, requires_expiry, expiry_alert_days, domain) values
  ('87a70000-0000-0000-0000-0000000000f1', '87a70000-0000-0000-0000-0000000000a1',
   '__painel_doc__', true, 30, 'pii'),
  ('87a70000-0000-0000-0000-0000000000f2', '87a70000-0000-0000-0000-0000000000a1',
   '__painel_aso__', true, 30, 'health');

insert into app.document
  (id, tenant_id, employee_id, type_id, storage_path, valid_until, status) values
  -- Vencido há 5 dias — não depende de janela nenhuma.
  ('87a70000-0000-0000-0000-00000000d001', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000b1', '87a70000-0000-0000-0000-0000000000f1',
   'painel/ana-vencido.pdf', current_date - 5, 'active'),
  -- A VENCER EM 40 DIAS. Com a janela de 30 ele está fora; com 45, dentro. É
  -- este par que a mutação do item A move.
  ('87a70000-0000-0000-0000-00000000d002', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000b1', '87a70000-0000-0000-0000-0000000000f1',
   'painel/ana-40d.pdf', current_date + 40, 'active'),
  ('87a70000-0000-0000-0000-00000000d003', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000b2', '87a70000-0000-0000-0000-0000000000f1',
   'painel/bruno-40d.pdf', current_date + 40, 'active'),
  -- Os anexos de ASO não têm validade própria: a validade é do EXAME. Sem isto
  -- eles entrariam nos contadores de documento e a conta do item A mudaria por
  -- um motivo que não é o testado.
  ('87a70000-0000-0000-0000-00000000d004', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000b1', '87a70000-0000-0000-0000-0000000000f2',
   'painel/ana-aso.pdf', null, 'active'),
  ('87a70000-0000-0000-0000-00000000d005', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000b2', '87a70000-0000-0000-0000-0000000000f2',
   'painel/bruno-aso.pdf', null, 'active');

insert into app.occupational_exam
  (id, tenant_id, employee_id, type, performed_on, valid_until, result, document_id) values
  -- Ana tem DOIS exames: o antigo vencido e o novo válido. Só o novo vale — é o
  -- caso que uma contagem sobre a tabela inteira erra, acusando pendência de
  -- quem está em dia.
  ('87a70000-0000-0000-0000-00000000e101', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000b1', 'periodic', current_date - 400,
   current_date - 35, 'fit', '87a70000-0000-0000-0000-00000000d004'),
  ('87a70000-0000-0000-0000-00000000e102', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000b1', 'periodic', current_date - 30,
   current_date + 300, 'fit', '87a70000-0000-0000-0000-00000000d004'),
  -- Bruno vence em 10 dias: dentro da janela de 30, fora da de 5.
  ('87a70000-0000-0000-0000-00000000e103', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000b2', 'periodic', current_date - 355,
   current_date + 10, 'fit', '87a70000-0000-0000-0000-00000000d005'),
  -- Carla: vencido há 3 dias e SEM anexo — janela desconhecida, conta assim mesmo.
  ('87a70000-0000-0000-0000-00000000e104', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000b3', 'periodic', current_date - 368,
   current_date - 3, 'fit', null);

insert into app.leave_period
  (id, tenant_id, employee_id, category, start_date, end_date, source, limit_date) values
  -- Ana em férias HOJE.
  ('87a70000-0000-0000-0000-00000000f101', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000b1', 'vacation',
   current_date - 2, current_date + 2, 'manual', current_date + 30),
  -- Bruno em férias no mês que vem.
  ('87a70000-0000-0000-0000-00000000f102', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000b2', 'vacation',
   (date_trunc('month', current_date) + interval '1 month' + interval '5 days')::date,
   (date_trunc('month', current_date) + interval '1 month' + interval '15 days')::date,
   'manual', null),
  -- Carla tem AFASTAMENTO, não férias, no mesmo período de Ana: sem esta linha,
  -- "em férias hoje = 1" também seria o resultado de ignorar a categoria.
  ('87a70000-0000-0000-0000-00000000f103', '87a70000-0000-0000-0000-0000000000a1',
   '87a70000-0000-0000-0000-0000000000b3', 'leave_of_absence',
   current_date - 2, current_date + 2, 'manual', current_date + 30);

-- ---------------------------------------------------------------------------
\echo '--- Owner do tenant A: os oito contadores, com o eixo de tenant valendo'
-- ---------------------------------------------------------------------------
set local role authenticated;
set local request.jwt.claim.sub = '87000000-0000-0000-0000-000000000001';

do $$ begin
  perform pg_temp.assert_eq('a função devolve OITO contadores',
    (select count(*) from public.fn_dp_alerts()), 8);

  -- Dilma faz aniversário no mês e é de outro tenant: 3 aqui seria o eixo de
  -- tenant ausente, e 0 seria a função não enxergando nada.
  perform pg_temp.assert_eq('aniversariantes do mês = Ana e Bruno (Dilma é de outro tenant)',
    pg_temp.contador('birthday_month'), 2);
  perform pg_temp.assert_eq('em experiência = Ana e Bruno (Carla tem 2000 dias de casa)',
    pg_temp.contador('probation'), 2);
  perform pg_temp.assert_eq('documento vencido = o de Ana',
    pg_temp.contador('document_expired'), 1);
  perform pg_temp.assert_eq('documento a vencer com janela de 30 = nenhum (os dois vencem em 40)',
    pg_temp.contador('document_expiring'), 0);
  perform pg_temp.assert_eq('ASO = Bruno (vence em 10, janela 30) + Carla (vencido, sem janela)',
    pg_temp.contador('exam_due'), 2);
  perform pg_temp.assert_eq('férias hoje = só Ana (o afastamento de Carla não é férias)',
    pg_temp.contador('vacation_today'), 1);
  perform pg_temp.assert_eq('férias no mês que vem = só Bruno',
    pg_temp.contador('vacation_upcoming'), 1);
  perform pg_temp.assert_eq('data limite dentro de 90 dias = só Ana (a de Carla não é férias)',
    pg_temp.contador('vacation_limit'), 1);
end $$;

-- ---------------------------------------------------------------------------
\echo '--- (A) A janela é a coluna: muda expiry_alert_days, muda o contador'
-- ---------------------------------------------------------------------------
reset role;
update app.document_type set expiry_alert_days = 45
 where id = '87a70000-0000-0000-0000-0000000000f1';

set local role authenticated;
set local request.jwt.claim.sub = '87000000-0000-0000-0000-000000000001';
do $$ begin
  perform pg_temp.assert_eq('janela 45: os dois documentos de 40 dias entram',
    pg_temp.contador('document_expiring'), 2);
  perform pg_temp.assert_eq('e o vencido continua vencido (a janela não o move)',
    pg_temp.contador('document_expired'), 1);
end $$;

reset role;
update app.document_type set expiry_alert_days = 30
 where id = '87a70000-0000-0000-0000-0000000000f1';

set local role authenticated;
set local request.jwt.claim.sub = '87000000-0000-0000-0000-000000000001';
do $$ begin
  -- A volta importa tanto quanto a ida: um contador que só cresce passaria na
  -- metade de cima e estaria lendo `>= current_date` sem teto.
  perform pg_temp.assert_eq('janela de volta em 30: nenhum documento a vencer',
    pg_temp.contador('document_expiring'), 0);
end $$;

reset role;
update app.document_type set expiry_alert_days = 5
 where id = '87a70000-0000-0000-0000-0000000000f2';

set local role authenticated;
set local request.jwt.claim.sub = '87000000-0000-0000-0000-000000000001';
do $$ begin
  -- O ASO de Bruno vence em 10 dias: com a janela do TIPO em 5, ele sai. Carla
  -- fica, porque vencido não depende de janela. Duas leituras diferentes da
  -- mesma coluna, e as duas mudam.
  perform pg_temp.assert_eq('janela do ASO em 5: Bruno sai, Carla (vencida) fica',
    pg_temp.contador('exam_due'), 1);
end $$;

reset role;
update app.document_type set expiry_alert_days = 30
 where id = '87a70000-0000-0000-0000-0000000000f2';

-- ---------------------------------------------------------------------------
\echo '--- (B) Supervisor da unidade 1: não conta a unidade 2, e conta a dele'
-- ---------------------------------------------------------------------------
set local role authenticated;
set local request.jwt.claim.sub = '87000000-0000-0000-0000-000000000002';

do $$ begin
  -- Cada par é "ele vê o dele" + "e só o dele". O número do owner acima é o
  -- que dá sentido a estes: 2 lá, 1 aqui.
  perform pg_temp.assert_eq('supervisor conta o aniversário de Ana',
    pg_temp.contador('birthday_month'), 1);
  perform pg_temp.assert_eq('supervisor conta a experiência de Ana, não a de Bruno',
    pg_temp.contador('probation'), 1);
  perform pg_temp.assert_eq('supervisor conta o documento vencido de Ana',
    pg_temp.contador('document_expired'), 1);
  perform pg_temp.assert_eq('supervisor conta o ASO de Carla, não o de Bruno',
    pg_temp.contador('exam_due'), 1);
  perform pg_temp.assert_eq('supervisor conta as férias de Ana, que é da unidade dele',
    pg_temp.contador('vacation_today'), 1);
  perform pg_temp.assert_eq('e NÃO conta as férias de Bruno no mês que vem',
    pg_temp.contador('vacation_upcoming'), 0);

  -- (C) O motivo de a função ser `security definer`, dito em duas linhas: ele
  -- não lê a tabela e recebe o número. Se ela virar `security invoker`, a
  -- primeira linha continua 0 e a segunda cai para 0 junto — e é a segunda que
  -- explica o que quebrou.
  perform pg_temp.assert_eq('supervisor NÃO lê app.employee_pii (sem o domínio pii)',
    (select count(*) from app.employee_pii), 0);
  perform pg_temp.assert_eq('e ainda assim recebe o contador de aniversariantes da unidade dele',
    pg_temp.contador('birthday_month'), 1);
end $$;

reset role;

\echo ''
\echo '================================================'
\echo ' PAINEL DE DP: OITO CONTADORES, JANELA E ESCOPO'
\echo '================================================'

rollback;
