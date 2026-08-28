-- ============================================================================
-- OperaX — 29. DUAS LEITURAS QUE O BANCO TEM E O ASSISTENTE NÃO ALCANÇA
-- ----------------------------------------------------------------------------
-- `public.fn_ranking_by_manager` existe desde a migration 27 e
-- `public.fn_pending_justification` desde a 23. As duas são `security invoker`,
-- as duas já têm `execute` para `authenticated`, e as duas já têm tela lendo
-- pelo Caminho 1. O assistente não chega em nenhuma das duas — não por falta de
-- permissão, mas porque `app.metric` nunca ganhou a linha.
--
-- O catálogo é fechado por desenho (regra 9): métrica ausente daqui é pergunta
-- que o assistente recusa. A recusa está certa; a ausência é que não estava.
-- "Qual gestor tem mais ocorrências?" e "o que está pendente de justificativa?"
-- são as duas perguntas que a fila e o ranking existem para responder, e hoje
-- as duas recebem "não tenho esse dado".
--
-- NADA NOVO É EXPOSTO
-- Nenhuma view, nenhuma coluna, nenhum grant e nenhuma policy. As duas funções
-- já são alcançáveis pelo navegador com o token da pessoa; esta migration edita
-- configuração do assistente, que é o que `app.metric` é.
--
-- `manager` É DIMENSÃO DE SAÍDA, COMO `unit` NO RANKING DE UNIDADE
-- `fn_ranking_by_manager` ordena gestores. Filtrar um ranking de gestores por um
-- gestor é pedir o ranking de um item só — então `manager` descreve o resultado
-- e não vira argumento, exatamente como `unit` em `ranking_by_unit` e `employee`
-- em `ranking_by_employee`. Quem filtra é `unit` e `company`.
--
-- ⚠️ `pending_justification` NÃO DECLARA `manager`, E A OMISSÃO É A DECISÃO
-- A função aceita `p_manager_id`, e ele filtra por `app.employee.manager_employee_id`
-- — a coluna que nada preenche, e que é a razão de a migration 27 ter criado a
-- dimensão de gestor de verdade. Ligar o catálogo nela entregaria um filtro que
-- devolve zero linhas em silêncio, que é pior que filtro nenhum: o assistente
-- responderia "nenhuma pendência para esse gestor" sobre uma fila cheia.
-- `p_department_id` também fica de fora, das duas: o prompt lista unidades e não
-- lista departamentos, então um identificador de departamento só entraria
-- inventado.
--
-- POR QUE UMA MÉTRICA DE LISTA É ACEITÁVEL AQUI, DEPOIS DA 20
-- A 20 tirou duas métricas de cima de views de linha porque elas prometiam uma
-- CONTAGEM e devolviam o teto de 200 como se fosse o total. O título é o que
-- promete: este aqui promete a **fila**, e uma fila cortada em 200 continua
-- sendo a fila. O teto não é silencioso — `truncado` viaja para o modelo junto
-- com as linhas desde o primeiro dia do agente.
--
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

insert into app.metric (code, title, description, target_view, dimensions, filters, domain) values
  ('ranking_by_manager',     'Ranking de desvios por gestor',
   'Gestores ordenados por ocorrências no período',
   'fn_ranking_by_manager',     array['manager', 'unit', 'company'], array['start_date', 'end_date'], null),
  ('pending_justification',  'Ocorrências pendentes de justificativa',
   'Fila do que exige justificativa e ainda não teve nenhuma aceita',
   'fn_pending_justification',  array['unit'],                       array['start_date', 'end_date'], null)
on conflict (code) do nothing;

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  m       record;
  v_oid   oid;
  v_args  text;
  v_linhas int;
begin
  -- 1. As duas linhas existem e estão ativas.
  for m in select code, target_view, dimensions, filters, active from app.metric
            where code in ('ranking_by_manager', 'pending_justification') loop
    if not m.active then
      raise exception '% entrou inativa: o assistente não a enxerga', m.code;
    end if;

    -- 2. O alvo existe em `public` e é função — o mesmo que a 20 confere para o
    --    catálogo inteiro, dito aqui para as duas que esta migration cria.
    select p.oid, pg_get_function_arguments(p.oid) into v_oid, v_args
      from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public' and p.proname = m.target_view;
    if v_oid is null then
      raise exception '%: a função public.% não existe', m.code, m.target_view;
    end if;

    -- 3. É `authenticated` quem vai executar: o assistente roda como a pessoa
    --    que perguntou, sob `user_scope`. Sem este grant a métrica entraria no
    --    prompt e falharia na chamada.
    if not has_function_privilege('authenticated', v_oid, 'execute') then
      raise exception '%: authenticated não pode executar public.%', m.code, m.target_view;
    end if;

    -- 4. Toda dimensão que o catálogo promete como FILTRO tem argumento no
    --    alvo. `manager` não está aqui de propósito: ele descreve a saída.
    if 'unit' = any(m.dimensions) and v_args not like '%p_unit_id%' then
      raise exception '%: declara unidade e public.% não tem p_unit_id', m.code, m.target_view;
    end if;
    if 'company' = any(m.dimensions) and v_args not like '%p_company_id%' then
      raise exception '%: declara empresa e public.% não tem p_company_id', m.code, m.target_view;
    end if;

    -- 5. Período é obrigatório nas duas: sem recorte a fila varre o histórico.
    if not (m.filters @> array['start_date', 'end_date']) then
      raise exception '%: não declara as duas pontas do período: %', m.code, m.filters;
    end if;
  end loop;

  -- 6. `manager` como filtro seria um recorte que a função não faz.
  if exists (select 1 from app.metric
              where code = 'pending_justification' and 'manager' = any(dimensions)) then
    raise exception 'pending_justification declara gestor, e o p_manager_id dela filtra '
                    'manager_employee_id, que nada preenche';
  end if;

  -- 7. Teste vivo: as duas rodam e devolvem zero linhas num período vazio —
  --    zero, e não erro, é o que separa "nada aconteceu" de "não compila".
  select count(*) into v_linhas
    from public.fn_ranking_by_manager(date '1999-01-01', date '1999-12-31');
  if v_linhas <> 0 then
    raise exception 'fn_ranking_by_manager devolveu % linhas para 1999', v_linhas;
  end if;

  select count(*) into v_linhas
    from public.fn_pending_justification(date '1999-01-01', date '1999-12-31');
  if v_linhas <> 0 then
    raise exception 'fn_pending_justification devolveu % linhas para 1999', v_linhas;
  end if;

  raise notice 'OK: o ranking por gestor e a fila de pendências entraram no catálogo.';
end $$;
