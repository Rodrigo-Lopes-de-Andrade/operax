-- ============================================================================
-- OperaX — 20. A METRIC THAT COUNTS MUST POINT AT SOMETHING THAT COUNTS
-- ----------------------------------------------------------------------------
-- `deviations_total` is described in `app.metric` as "Contagem de ocorrências
-- ativas" and pointed at `vw_deviation_event`, which returns one row per event.
-- `deviations_minutes` is described as "Soma de minutes" and pointed at
-- `vw_deviation_by_employee_day`, one row per employee per day. Neither target
-- counts or sums anything: the counting was left to whoever read the rows.
--
-- That was harmless while the only reader was a dashboard that aggregated in
-- the page. It stopped being harmless when the assistant became a reader. The
-- assistant caps what it reads at 200 rows — it has to, because those rows are
-- paid for by the token — so "quantos desvios tivemos este mês?" against a
-- tenant with 508 events answered **200**. Not an error, not an empty answer: a
-- confident wrong number, which is the one outcome the whole catalogue design
-- exists to prevent. Measured against the development seed, which has 508.
--
-- `public.fn_kpi_period` already does the counting, already exists since
-- migration 10, is already `security invoker`, and is already granted to
-- `authenticated` — it is what the dashboard KPI row reads. Re-pointing the two
-- metrics at it is the same move migration 10 made for four other metrics.
--
-- THE DIMENSIONS SHRINK, AND THAT IS THE POINT
-- `fn_kpi_period` takes a period, a company and a unit. It does not take an
-- employee or a deviation type. So `employee` and `type` come off both metrics:
-- a catalogue that declares a dimension its target cannot honour produces a
-- filter that is silently dropped, and an answer that claims a cut that never
-- happened. Better to have the assistant refuse "essa métrica não aceita tipo"
-- by name — which it now does, because the parameter stops being declared.
--
-- Nothing is exposed that was not exposed: no new view, no new column, no grant
-- and no policy. `app.metric` is configuration of the assistant, and this
-- migration edits two rows of it.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

update app.metric
   set target_view = 'fn_kpi_period',
       dimensions  = array['unit', 'company']
 where code in ('deviations_total', 'deviations_minutes');

comment on table app.metric is
  'Catálogo fechado do assistente de IA. Métrica ausente daqui = pergunta que ele '
  'responde "não tenho esse dado", em vez de inventar. O alvo tem de responder o que o '
  'título promete: uma métrica de contagem apontada para uma view de linhas devolve o '
  'teto de linhas como se fosse a contagem.';

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_eventos bigint;
  v_linhas  int;
  m         record;
begin
  -- 1. As duas métricas apontam para a função, e não declaram mais o que ela
  --    não aceita.
  for m in select code, target_view, dimensions from app.metric
            where code in ('deviations_total', 'deviations_minutes') loop
    if m.target_view <> 'fn_kpi_period' then
      raise exception '% ainda aponta para %', m.code, m.target_view;
    end if;
    if 'employee' = any(m.dimensions) or 'type' = any(m.dimensions) then
      raise exception '% ainda declara uma dimensão que fn_kpi_period não aceita: %',
        m.code, m.dimensions;
    end if;
  end loop;

  -- 2. Todo alvo de métrica ativa existe em `public`. É o mesmo que o
  --    `scripts/91_teste_catalogo.py` confere, dito aqui para que a migration
  --    não possa deixar o catálogo apontando para o nada.
  for m in select code, target_view from app.metric where active loop
    if m.target_view like 'fn\_%' then
      if not exists (
        select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.proname = m.target_view
      ) then
        raise exception '%: a função public.% não existe', m.code, m.target_view;
      end if;
    elsif to_regclass('public.' || m.target_view) is null then
      raise exception '%: a view public.% não existe', m.code, m.target_view;
    end if;
  end loop;

  -- 3. Teste vivo: a função devolve UMA linha, que é a diferença inteira entre
  --    contar e listar.
  select count(*) into v_linhas
    from public.fn_kpi_period(date '1999-01-01', date '1999-12-31');
  if v_linhas <> 1 then
    raise exception 'fn_kpi_period devolveu % linhas para um período vazio', v_linhas;
  end if;

  select eventos into v_eventos
    from public.fn_kpi_period(date '1999-01-01', date '1999-12-31');
  if v_eventos is null then
    raise exception 'fn_kpi_period devolveu contagem nula em vez de zero';
  end if;

  raise notice 'OK: a métrica de contagem aponta para quem conta.';
end $$;
