-- ============================================================================
-- OperaX — 31. O RENAME TRADUZIU O NOME DA MÉTRICA E NÃO OS PARÂMETROS DELA
-- ----------------------------------------------------------------------------
-- Irmã da 28, achada do mesmo jeito: rodando a pilha de verdade contra o
-- staging, que carrega o **dado** de produção — não o catálogo que a suíte cria
-- do zero em inglês.
--
-- O 11b atualiza `app.metric` em oito linhas de `update`, e todas elas mexem em
-- `code`, `target_view` e `domain`. Nenhuma toca `dimensions` e `filters`, que
-- são `text[]` de dado. Então em produção, depois da janela, o catálogo fica
-- assim:
--
--     ranking_by_unit | dimensions {unidade} | filters {data_inicio, data_fim}
--
-- Nome em inglês, parâmetros em português.
--
-- ⛔ A CONSEQUÊNCIA É O ASSISTENTE INTEIRO, E ELA NÃO É SUTIL
-- `catalogo.TYPES` é código e fala inglês. Todo parâmetro aceito tem de ter tipo
-- declarado lá, e `_coerce` levanta `UntypedParameterError` quando não tem. O
-- caminho é: o modelo escolhe a métrica, o catálogo aceita `data_inicio` porque
-- a linha do banco diz que ela aceita, e a conversão estoura. A pessoa recebe
-- "Falha ao consultar o modelo", que é a mensagem de erro de provider — e o
-- provider está bem. Medido em 28/08 contra o staging: **8 das 11 métricas**
-- nesse estado, e o token da pergunta já pago.
--
-- POR QUE NENHUM TESTE PEGOU
-- O mesmo motivo da 28. `scripts/91_teste_catalogo.py` confere catálogo contra
-- `BINDINGS`/`TYPES` — e roda contra o banco descartável, onde `app.metric`
-- nasce da migration 09, já em inglês. O teste está certo; o dado que ele vê é
-- que não é o dado de produção. A guarda abaixo fecha isso pelo outro lado:
-- ela roda onde o dado real está.
--
-- O MAPA É O `scripts/rename_map.py`, NÃO UM PALPITE
-- Cada par abaixo sai de lá, que é o que o CLAUDE.md manda consultar antes de
-- nomear qualquer coisa. `dias` -> `days_ahead` é o único que não é tradução
-- direta: o nome em inglês veio da migration 09 e é o que `TYPES` declara.
--
-- Idempotente: valor já em inglês mapeia para ele mesmo.
-- ============================================================================

with mapa(pt, en) as (
  values ('unidade', 'unit'), ('empresa', 'company'), ('colaborador', 'employee'),
         ('tipo', 'type'), ('competencia', 'payroll_period'),
         ('data_inicio', 'start_date'), ('data_fim', 'end_date'),
         ('dias', 'days_ahead'), ('ano', 'year'), ('mes', 'month')
)
update app.metric m
   set dimensions = coalesce((
         select array_agg(coalesce(mapa.en, u.valor) order by u.ord)
           from unnest(m.dimensions) with ordinality as u(valor, ord)
           left join mapa on mapa.pt = u.valor
       ), '{}'),
       filters = coalesce((
         select array_agg(coalesce(mapa.en, u.valor) order by u.ord)
           from unnest(m.filters) with ordinality as u(valor, ord)
           left join mapa on mapa.pt = u.valor
       ), '{}')
 where exists (
   select 1 from unnest(m.dimensions || m.filters) as v(valor)
   join mapa on mapa.pt = v.valor
 );

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
-- Não confere só o que esta migration traduziu: confere o vocabulário inteiro,
-- contra a lista que `catalogo.TYPES` declara. Uma métrica futura que entre com
-- parâmetro fora dela para aqui, em vez de parar na cara de quem perguntou.
do $$
declare
  v_aceitos text[] := array[
    'start_date', 'end_date', 'days_ahead', 'stale_after_minutes',
    'year', 'month', 'unit', 'company', 'employee', 'manager',
    'type', 'payroll_period', 'entity'
  ];
  m       record;
  v_ruins text := '';
begin
  for m in select code, dimensions, filters from app.metric loop
    if exists (
      select 1 from unnest(m.dimensions || m.filters) as v(valor)
      where not (v.valor = any(v_aceitos))
    ) then
      v_ruins := v_ruins || format('%s(%s) ', m.code,
        (select string_agg(v.valor, ',') from unnest(m.dimensions || m.filters) as v(valor)
          where not (v.valor = any(v_aceitos))));
    end if;
  end loop;

  if v_ruins <> '' then
    raise exception 'métrica com parâmetro fora do vocabulário de catalogo.TYPES -> %', v_ruins;
  end if;

  raise notice 'OK: os parâmetros do catálogo falam a mesma língua que TYPES.';
end $$;
