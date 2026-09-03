-- ============================================================================
-- OperaX — 35. O LIMIAR DE FRESCOR DA ENTIDADE DIÁRIA
-- ----------------------------------------------------------------------------
-- A `sync-fotos` deste repositório grava `app.sync_run` com `entity = 'Foto'`, e
-- a cadência dela é DIÁRIA — `17 3 * * *`, contra 15 min das batidas e 30 do
-- cadastro.
--
-- `fn_data_freshness` (migration 21) usa 1,5x a cadência de cada entidade, com
-- 45 min de padrão. Para uma entidade diária, 45 min significa **sempre velha**.
-- E isso não ficaria confinado a uma linha: `frontend/src/lib/freshness.ts`
-- reduz a resposta à entidade **mais velha** — "o quadro só é tão fresco quanto
-- a coisa mais velha nele" —, então uma entidade diária faria o painel inteiro
-- dizer "atrasado" para sempre, com a sincronização perfeita.
--
-- 36 h = 1,5 x 24 h. A mesma regra das outras duas, aplicada à cadência que esta
-- tem. Não é exceção: é a regra continuando a valer.
--
-- ⚠️ O limiar mora aqui, em código, e não em tabela de configuração — pelos dois
-- motivos da 21: é decisão escrita (docs/DECISAO-CADENCIA-SYNC.md) e não ajuste
-- de operação, e tabela nova em `app` exigiria policy nova, que é uma das três
-- paradas obrigatórias deste projeto.
--
-- Nenhuma tabela nova, nenhuma coluna nova, nenhuma policy nova. A assinatura da
-- função não muda.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

create or replace function public.fn_data_freshness(p_stale_after_minutes int default null)
returns table (
  tenant_id      uuid,
  entity         text,
  last_sync_at   timestamptz,
  age_minutes    integer,
  is_stale       boolean
)
language sql stable security definer set search_path = ''
as $$
  select s.tenant_id,
         s.entity,
         max(s.finished_at)                                           as last_sync_at,
         (extract(epoch from (now() - max(s.finished_at))) / 60)::int as age_minutes,
         now() - max(s.finished_at) > make_interval(mins => greatest(
           coalesce(
             p_stale_after_minutes,
             -- 1,5x a cadência da entidade, arredondado para cima.
             case s.entity
               when 'Batida' then 25      -- cadência 15 min
               when 'Foto'   then 2160    -- cadência diária: 1,5 x 24 h
               else 45                    -- cadência 30 min
             end
           ), 1))
    from app.sync_run s
   where s.status = 'completed'
     and s.finished_at is not null
     and s.tenant_id = any (util.user_tenants())
   group by s.tenant_id, s.entity;
$$;

comment on function public.fn_data_freshness(int) is
  'Idade do dado por entidade sincronizada, e o deadman da ingestão. Sem argumento, '
  'o limiar é 1,5x a cadência da entidade — 25 min para Batida (cadência 15), 2160 para '
  'Foto (cadência diária) e 45 para as demais (cadência 30) — de modo que uma execução '
  'perdida não alarma e duas seguidas alarmam. Com argumento, ele vale para todas. '
  'Ver docs/DECISAO-CADENCIA-SYNC.md.';

revoke execute on function public.fn_data_freshness(int) from public, anon;
grant  execute on function public.fn_data_freshness(int) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Prova
-- ---------------------------------------------------------------------------
do $$
declare
  v_stale boolean;
begin
  -- 1. `anon` continua sem alcançar a função.
  if has_function_privilege('anon', 'public.fn_data_freshness(int)', 'execute') then
    raise exception 'anon executa fn_data_freshness';
  end if;

  -- 2. Uma Foto de 20 h atrás está FRESCA — sob o limiar antigo estaria velha, e
  --    o painel inteiro (que mostra a mais velha) diria "atrasado".
  select now() - (now() - interval '20 hours')
         > make_interval(mins => case 'Foto'
             when 'Batida' then 25 when 'Foto' then 2160 else 45 end)
    into v_stale;
  if v_stale then
    raise exception 'Foto com 20 h deveria estar fresca sob o limiar de 36 h';
  end if;

  -- 3. E uma de 40 h está velha: o limiar existe, não é "nunca alarma".
  select now() - (now() - interval '40 hours')
         > make_interval(mins => case 'Foto'
             when 'Batida' then 25 when 'Foto' then 2160 else 45 end)
    into v_stale;
  if not v_stale then
    raise exception 'Foto com 40 h deveria estar velha (limiar 36 h)';
  end if;

  -- 4. As outras duas não foram afetadas.
  select now() - (now() - interval '30 minutes')
         > make_interval(mins => case 'Batida'
             when 'Batida' then 25 when 'Foto' then 2160 else 45 end)
    into v_stale;
  if not v_stale then
    raise exception 'Batida com 30 min deveria continuar velha (limiar 25)';
  end if;

  select now() - (now() - interval '30 minutes')
         > make_interval(mins => case 'Funcionario'
             when 'Batida' then 25 when 'Foto' then 2160 else 45 end)
    into v_stale;
  if v_stale then
    raise exception 'Funcionario com 30 min deveria continuar fresco (limiar 45)';
  end if;

  raise notice 'OK: Foto tem limiar de 36 h, e Batida e Funcionario seguem como estavam.';
end $$;
