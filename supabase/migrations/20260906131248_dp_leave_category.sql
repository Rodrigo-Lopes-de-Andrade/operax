-- ============================================================================
-- OperaX — dp_leave_category. A CATEGORIA QUE O CHECK NÃO TINHA
-- ----------------------------------------------------------------------------
-- ⛔ A `SPEC-DP.md` §1e AFIRMAVA ALGO FALSO, E ESTA MIGRATION É A CORREÇÃO
-- Ela dizia que as rotinas de cesta e de vale transporte "leem `app.leave_period`
-- com `category` de falta injustificada". O check da coluna aceita
-- ('vacation','leave_period','leave_of_absence','suspension') — e NENHUM deles é
-- falta. Medido em 06/09/2026; a SPEC foi corrigida no mesmo dia.
--
-- Não era descuido: o comentário da tabela (migration 04) declara o porquê —
-- "rótulo neutro por decisão de produto, motivo de leave_period é dado de saúde e
-- não é capturado". A decisão continua valendo, e esta migration NÃO a desfaz.
--
-- ⚠️ FALTA INJUSTIFICADA NÃO É DADO DE SAÚDE, E É POR ISSO QUE ELA PODE ENTRAR
-- As quatro categorias existentes são neutras porque "por que a pessoa se
-- afastou" é saúde (regra 10 do projeto: só aptidão e validade, nunca
-- diagnóstico). `unjustified_absence` diz o oposto de um motivo de saúde: ela
-- afirma que NÃO houve justificativa. Guardá-la não revela condição nenhuma — e
-- não guardá-la é o que custa dinheiro do colaborador, porque as duas rotinas
-- financeiras do DP dependem dela (`ANEXO-COBERTURA-LEGADO-FASTPARK.md` §4.7:
-- "falta injustificada aqui é o que tira a cesta e reduz dias líquidos do VT").
--
-- ⛔ A `04` ESTÁ APLICADA E NÃO SE EDITA
-- Então o instrumento é `drop constraint` + `add constraint` aqui, com o nome
-- que a `11b` deixou (`leave_period_category_check`). As quatro categorias
-- antigas continuam válidas: nenhuma linha existente fica ilegal, e é por isso
-- que esta migration roda sem janela.
--
-- ⚠️ O CÓDIGO PYTHON QUE COPIA ESTE CHECK MUDA JUNTO, E ISSO É MEDIDO
-- `operax/rh/ownership.py::ENUMS` guarda a mesma lista, e
-- `scripts/95_teste_matriz_rh.py` compara as duas a cada `make db-test` — um
-- valor a mais no banco e a menos no código faz a suíte reprovar com o diff na
-- mão. A alteração do Python acompanha este arquivo no mesmo PR.
--
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

alter table app.leave_period
  drop constraint if exists leave_period_category_check;

alter table app.leave_period
  add constraint leave_period_category_check
  check (category in (
    'vacation',
    'leave_period',
    'leave_of_absence',
    'suspension',
    -- A quinta, e a única cuja ausência tinha preço. Ver o cabeçalho.
    'unjustified_absence'
  ));

comment on column app.leave_period.category is
  'Rótulo neutro: nunca o motivo. unjustified_absence é a exceção deliberada — ela afirma a '
  'AUSÊNCIA de justificativa, não uma condição, e as duas rotinas financeiras do DP (cesta e '
  'vale transporte) a leem. Sem ela, quem faltou recebe como quem trabalhou.';

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v_def       text;
  v_checks    int;
  v_value     text;
  v_tenant    uuid;
  v_company   uuid;
  v_employee  uuid;
  v_recusou   boolean := false;
begin
  -- 1. Um check de categoria, e um só. Dois — o antigo sobrevivendo ao lado do
  --    novo — deixaria o mais estreito mandando, e o sintoma seria uma recusa
  --    que ninguém consegue explicar lendo a definição nova.
  select count(*) into v_checks
    from pg_constraint
   where conrelid = 'app.leave_period'::regclass
     and contype  = 'c'
     and pg_get_constraintdef(oid) like '%(category = ANY%';
  if v_checks <> 1 then
    raise exception 'app.leave_period tem % check(s) de categoria, esperava 1', v_checks;
  end if;

  select pg_get_constraintdef(oid) into v_def
    from pg_constraint
   where conrelid = 'app.leave_period'::regclass
     and conname  = 'leave_period_category_check';
  if v_def is null then
    raise exception 'leave_period_category_check não existe depois de ser recriada';
  end if;

  -- 2. As cinco, uma a uma. Conferir só a nova deixaria passar uma recriação que
  --    perdeu as quatro antigas pelo caminho — e aí toda linha de férias já
  --    gravada viraria ilegal na próxima escrita.
  foreach v_value in array array[
    'vacation','leave_period','leave_of_absence','suspension','unjustified_absence'
  ] loop
    if v_def not like '%''' || v_value || '''%' then
      raise exception 'leave_period_category_check não aceita %; definição: %', v_value, v_def;
    end if;
  end loop;

  -- 3. A prova viva. O estrutural acima confere o TEXTO da constraint; esta
  --    confere que ela se comporta — aceita a quinta e continua recusando o que
  --    não está na lista. Uma constraint que aceitasse qualquer coisa passaria
  --    nos dois itens anteriores.
  --    ⛔ Fixture inteiramente própria, e a lição é da `dp_benefit_catalog`: o
  --    banco de ensaio tem 1 tenant e ZERO empresas, e `app.employee.company_id`
  --    é NOT NULL — reusar empresa existente fez duas provas pularem caladas lá.
  select t.id into v_tenant from app.tenant t order by t.created_at limit 1;
  if v_tenant is null then
    raise notice 'sem tenant: prova viva pulada (a estrutura já foi verificada acima)';
    return;
  end if;

  insert into app.company (tenant_id, legal_name, active)
  values (v_tenant, '__dp_lc_prova__', false)
  returning id into v_company;
  insert into app.employee (tenant_id, company_id, name)
  values (v_tenant, v_company, '__dp_lc_prova__')
  returning id into v_employee;

  -- a) a quinta entra;
  insert into app.leave_period (tenant_id, employee_id, category, start_date, end_date, source)
  values (v_tenant, v_employee, 'unjustified_absence',
          date '2026-01-05', date '2026-01-05', 'manual');

  -- b) e o que não está na lista continua barrado.
  begin
    insert into app.leave_period (tenant_id, employee_id, category, start_date, end_date, source)
    values (v_tenant, v_employee, 'falta_injustificada',
            date '2026-01-06', date '2026-01-06', 'manual');
  exception when check_violation then
    v_recusou := true;
  end;
  if not v_recusou then
    raise exception
      'app.leave_period aceitou categoria fora da lista — o check virou decoração, e o rótulo neutro deixou de ser garantia';
  end if;

  delete from app.leave_period where employee_id = v_employee;
  delete from app.employee where id = v_employee;
  delete from app.company  where id = v_company;

  raise notice
    'OK: app.leave_period.category aceita as cinco categorias, recusa o resto, e a falta injustificada passou a ter onde morar.';
end $$;
