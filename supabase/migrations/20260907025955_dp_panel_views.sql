-- ============================================================================
-- OperaX — dp_panel_views. OS OITO CONTADORES DE ALERTA, E SÓ ELES
-- ----------------------------------------------------------------------------
-- Desenho em `docs/SPEC-DP.md` §1k (reescrita em 06/09/2026) e inventário em
-- `ANEXO-COBERTURA-LEGADO-FASTPARK.md` §2c.
--
-- ⛔ O QUE ESTA MIGRATION **NÃO** CRIA, E POR QUÊ
-- `public.fn_dp_panel` não nasce: decisão do dono, 06/09. Os 9 KPIs de topo vão
-- pelo Caminho 2, porque a folha base já existe em Python
-- (`operax/dp/beneficios.compute_base_payroll`) e o `ANEXO` §2a exige que ela
-- bata com a do cliente NA VÍRGULA — duas implementações de uma soma que precisa
-- bater na vírgula é o defeito, não a otimização. E é coerente com o Contrato:
-- folha base é `compensation`, e o Caminho 1 carrega só agregado não sensível.
-- `public.vw_unit_compliance` também não: ela lê `app.unit_compliance_report`,
-- tabela que o S5 cria e que não existe em migration nenhuma.
--
-- ⛔ CONTAGEM, NUNCA LINHA POR PESSOA
-- A função devolve `(code, total)`. Não há coluna de colaborador, de nome ou de
-- data que dispare — a lista por pessoa é dado individual e sai pelo Caminho 2,
-- com o domínio revalidado. O passo 3 da garantia varre o TIPO DE RETORNO atrás
-- disso, para que a promessa não dependa de quem escreve a próxima versão.
--
-- ⚠️ `security definer` É DELIBERADO, E O QUE ELE DISPENSA NÃO É O ESCOPO
-- Cinco dos oito contadores leem tabela de domínio sensível: aniversário está em
-- `app.employee_pii` (pii), ASO em `app.occupational_exam` (health). Sob
-- `security invoker`, o supervisor — que não tem nenhum dos dois — receberia
-- ZERO em cinco cartões, e um painel que mente com cara de calmaria é pior que
-- um painel ausente. Contar quantos vencimentos existem não revela de quem eles
-- são; ler a linha, sim, e é por isso que a lista não está aqui.
-- O que `security definer` NÃO dispensa é o recorte: o corpo filtra por
-- `util.user_tenants()` e por `util.can_see_employee`, que são as MESMAS funções
-- que as policies chamam. Sem elas a função devolveria a contagem de todos os
-- tenants — o mesmo desenho, e o mesmo cuidado, de `public.fn_whatsapp_readiness`.
--
-- ⚠️ CONSEQUÊNCIA DECLARADA: numa unidade de uma pessoa só, "1 aniversariante"
-- diz o mês de nascimento dela. É a inferência que todo agregado carrega; a
-- alternativa (esconder o cartão para escopo pequeno) foi descartada por ser
-- configuração não pedida. Registrado para o dono decidir se um dia incomoda.
--
-- ⛔ AS JANELAS DE DOCUMENTO VÊM DE `app.document_type.expiry_alert_days`
-- Nunca de constante. A coluna existe desde a migration 08
-- (`integer not null default 30`) e é POR TIPO: mudar a de um tipo muda o
-- contador, e `scripts/87_teste_painel_dp.sql` prova isso mudando a coluna e
-- vendo o número mudar.
--
-- ⚠️ E O QUE NÃO TEM DE ONDE VIR — LEIA ANTES DE "CORRIGIR"
-- Três janelas não são preferência de alerta e por isso não estão naquela
-- coluna: mês corrente (aniversário), hoje (em férias) e mês seguinte (férias
-- próximas) são calendário; 30/60 dias é o contrato de experiência da CLT; e os
-- 90 dias da data limite de férias são o que a tela do legado declara
-- (`ANEXO` §2c) — não existe config por tenant para eles em lugar nenhum do
-- produto. Estão escritos aqui com a fonte nomeada, em vez de inventarem uma
-- tabela de configuração que ninguém pediu.
--
-- ⚠️ O LEGADO ROTULA DOIS CARTÕES COMO "CNH", E ESTA FUNÇÃO NÃO
-- `app.document_type` não tem `code`: a identidade dele é o `name`, texto livre
-- por tenant ('CNH' na semente de desenvolvimento, e nada garante isso). Um
-- `ilike 'cnh%'` aqui poria regra de negócio numa string e erraria CALADO no
-- tenant que chamar o tipo de "Carteira de Habilitação". Então os dois
-- contadores são por VENCIMENTO DE DOCUMENTO, com a janela de cada tipo, e o
-- recorte por tipo é da lista — que é tela, e não esta função. Reportado.
--
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

create or replace function public.fn_dp_alerts()
returns table (code text, total integer)
language sql stable security definer set search_path = ''
as $$
  with visible as (
    -- O recorte inteiro mora aqui: tenant + escopo, pelas mesmas funções das
    -- policies. Desligado fica fora — alertar sobre o aniversário de quem não
    -- trabalha mais é ruído que some do painel para sempre.
    select e.id, e.hired_on
      from app.employee e
     where e.tenant_id = any (util.user_tenants())
       and e.status <> 'desligado'
       and util.can_see_employee(e.id)
  ),
  last_exam as (
    -- ⛔ O EXAME MAIS RECENTE, E NÃO TODOS: `app.occupational_exam` é histórico.
    -- Contar a tabela inteira somaria o ASO vencido de 2024 ao ASO válido de
    -- hoje, e o cartão acusaria pendência de quem está em dia.
    select distinct on (x.employee_id)
           x.employee_id, x.valid_until, x.document_id
      from app.occupational_exam x
      join visible v on v.id = x.employee_id
     order by x.employee_id, x.performed_on desc
  )
  select 'birthday_month', count(*)::int
    from visible v
    join app.employee_pii p on p.employee_id = v.id
   where p.birth_date is not null
     and extract(month from p.birth_date) = extract(month from current_date)

  union all
  -- Experiência: 1ª (1–30d) e 2ª (31–60d) são o contrato da CLT, e o cartão
  -- mostra o total. A divisão em duas metades é da lista, que nomeia quem.
  select 'probation', count(*)::int
    from visible v
   where v.hired_on is not null
     and current_date - v.hired_on between 1 and 60

  union all
  select 'document_expired', count(*)::int
    from app.document d
    join visible v on v.id = d.employee_id
    join app.document_type dt on dt.id = d.type_id
   where d.status = 'active'
     and dt.requires_expiry
     and d.valid_until is not null
     and d.valid_until < current_date

  union all
  select 'document_expiring', count(*)::int
    from app.document d
    join visible v on v.id = d.employee_id
    join app.document_type dt on dt.id = d.type_id
   where d.status = 'active'
     and dt.requires_expiry
     and d.valid_until is not null
     and d.valid_until >= current_date
     and d.valid_until <= current_date + dt.expiry_alert_days

  union all
  -- ASO = vencidos + a vencer, num cartão só (ANEXO §2c). A janela vem do tipo
  -- do documento anexado ao exame; exame sem anexo não tem janela conhecida, e
  -- então só conta depois de vencer. Uma janela padrão em constante mentiria com
  -- cara de configuração.
  select 'exam_due', count(*)::int
    from last_exam x
    left join app.document      xd  on xd.id  = x.document_id
    left join app.document_type xdt on xdt.id = xd.type_id
   where x.valid_until is not null
     and x.valid_until <= current_date + coalesce(xdt.expiry_alert_days, 0)

  union all
  select 'vacation_upcoming', count(distinct l.employee_id)::int
    from app.leave_period l
    join visible v on v.id = l.employee_id
   where l.category = 'vacation'
     and l.start_date >= (date_trunc('month', current_date) + interval '1 month')::date
     and l.start_date <  (date_trunc('month', current_date) + interval '2 months')::date

  union all
  select 'vacation_today', count(distinct l.employee_id)::int
    from app.leave_period l
    join visible v on v.id = l.employee_id
   where l.category = 'vacation'
     and l.start_date <= current_date
     and coalesce(l.end_date, l.start_date) >= current_date

  union all
  -- `limit_date` chegou com a migration `dp_leave_extension`. Quem nunca teve
  -- período gravado não aparece aqui: o legado deriva o limite de admissão+12m e
  -- essa derivação não existe no repositório. Pendência declarada, não silêncio.
  select 'vacation_limit', count(distinct l.employee_id)::int
    from app.leave_period l
    join visible v on v.id = l.employee_id
   where l.limit_date is not null
     and l.limit_date >= current_date
     and l.limit_date <= current_date + 90;
$$;

comment on function public.fn_dp_alerts() is
  'Os oito contadores do painel de alertas do DP. Devolve CONTAGEM, nunca linha por '
  'pessoa — a lista é individual e sai pelo Caminho 2. security definer porque cinco '
  'dos oito leem domínio sensível e contar não é ler; o recorte de tenant e escopo '
  'continua sendo util.user_tenants() + util.can_see_employee. Janela de documento '
  'vem de app.document_type.expiry_alert_days, por tipo.';

revoke execute on function public.fn_dp_alerts() from public, anon;
grant  execute on function public.fn_dp_alerts() to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
-- ⚠️ O que ela NÃO faz, de propósito: ela não monta usuário para provar recorte
-- nem janela. Isso exigiria escrever em `auth.users`, e esta migration roda em
-- produção. As duas provas funcionais — "supervisor não vê a outra unidade e VÊ
-- a dele" e "mudar `expiry_alert_days` muda o contador" — vivem em
-- `scripts/87_teste_painel_dp.sql`, dentro de transação revertida, e rodam no
-- `make db-test`.
do $$
declare
  v_oid        oid;
  v_secdef     boolean;
  v_config     text;
  v_resultado  text;
  v_codigos    text[];
  v_nulos      int;
  v_esperado   constant text[] := array[
    'birthday_month','probation','document_expired','document_expiring',
    'exam_due','vacation_upcoming','vacation_today','vacation_limit'];
begin
  select p.oid, p.prosecdef, coalesce(array_to_string(p.proconfig, ','), '')
    into v_oid, v_secdef, v_config
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.proname = 'fn_dp_alerts';

  if v_oid is null then
    raise exception 'public.fn_dp_alerts() não existe';
  end if;

  -- 1. `security definer` com `search_path` travado. Definer sem search_path é
  --    escalada de privilégio esperando um schema temporário — é a exigência que
  --    o item 9 de `scripts/99_verificacao_rls.sql` faz aos helpers de `util`.
  if not v_secdef then
    raise exception 'public.fn_dp_alerts() não é security definer — cinco cartões voltariam zerados para o supervisor';
  end if;
  if v_config not like '%search_path=%' then
    raise exception 'public.fn_dp_alerts() é security definer SEM search_path travado';
  end if;

  -- 2. `anon` não executa; `authenticated` executa. O negativo sozinho ficaria
  --    verde numa função que ninguém pode chamar.
  if pg_catalog.has_function_privilege('anon', v_oid, 'EXECUTE') then
    raise exception 'anon pode executar public.fn_dp_alerts()';
  end if;
  if not pg_catalog.has_function_privilege('authenticated', v_oid, 'EXECUTE') then
    raise exception 'authenticated NÃO pode executar public.fn_dp_alerts() — o painel não abre para ninguém';
  end if;

  -- 3. ⛔ CONTAGEM, NUNCA LINHA POR PESSOA — varrido no TIPO DE RETORNO
  --    Uma versão futura que acrescentasse `employee_id` ou `name` para "já que
  --    estamos aqui" não roda. É a mesma ideia de
  --    `test_nenhum_contrato_de_resposta_de_dp_tem_campo_account`, do lado do banco.
  v_resultado := pg_catalog.pg_get_function_result(v_oid);
  if v_resultado ~* '(employee|colaborador|name|nome|cpf|birth|registration)' then
    raise exception
      'public.fn_dp_alerts() devolve dado por pessoa (%) — ela é agregado de Caminho 1 e a lista é do Caminho 2',
      v_resultado;
  end if;

  -- 4. Os oito códigos, e oito linhas. Chamada sem usuário autenticado:
  --    `util.user_tenants()` devolve vazio, todo contador dá zero, e é
  --    exatamente isso que prova que o recorte de tenant existe — uma função sem
  --    o filtro devolveria a contagem do banco inteiro aqui.
  select array_agg(a.code order by a.code), count(*) filter (where a.total is null)
    into v_codigos, v_nulos
    from public.fn_dp_alerts() a;

  if v_codigos is distinct from (select array_agg(c order by c) from unnest(v_esperado) c) then
    raise exception 'public.fn_dp_alerts() devolveu os códigos % — esperava %',
      v_codigos, v_esperado;
  end if;
  if v_nulos > 0 then
    raise exception
      '% contador(es) vieram nulos — cartão sem número é indistinguível de cartão zerado na tela', v_nulos;
  end if;
  if exists (select 1 from public.fn_dp_alerts() a where a.total <> 0) then
    raise exception
      'public.fn_dp_alerts() contou linha sem usuário autenticado — o filtro por util.user_tenants() não está restringindo';
  end if;

  raise notice
    'OK: public.fn_dp_alerts() — oito contadores, security definer travado, anon fora, e nada por pessoa no retorno.';
end $$;
