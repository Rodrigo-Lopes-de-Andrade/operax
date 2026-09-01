-- ============================================================================
-- OperaX — 33. O GATILHO QUE FOI TRADUZIDO SEM A TABELA DELE
-- ----------------------------------------------------------------------------
-- A migration 11b renomeou `util.toca_atualizado_em` para
-- `util.touch_updated_at` e reescreveu o corpo dela para gravar
-- `new.updated_at`. Junto, renomeou quatro gatilhos `trg_atualizado_em` para
-- `trg_updated_at` — em `employee`, `employee_pii`, `deviation_event` e
-- `integration_secret`, que ganharam a coluna em inglês no mesmo lote.
--
-- As tabelas de ingestão ficaram de fora da renomeação, e isso foi decisão:
-- `app.batida_marcacao` e `app.cursor_sincronizacao` são escritas pelo runner
-- da sincronização, que não é deste repositório. Renomeá-las quebraria a
-- escrita dele — que é exatamente o que a exclusão evitou.
--
-- Só que o gatilho delas não foi excluído junto. As duas seguiram com
-- `atualizado_em` na tabela e `util.touch_updated_at()` no gatilho, e um
-- `update` numa delas passou a estourar:
--
--     record "new" has no field "updated_at"
--
-- Em produção isso derrubou a sincronização de batidas por quatro horas em
-- 31/08/2026: `net._http_response` mostra o último 200 às 21:00 UTC e 500 em
-- todo ciclo a partir das 21:45, o primeiro depois de as 22 migrations serem
-- aplicadas. O insert seguia passando — o gatilho é `before update`, e a
-- escrita da sincronização é upsert de janela deslizante, que atualiza.
--
-- O conserto tem duas metades, e a segunda é a que importa:
--
--   1. Uma função de toque em português para as tabelas em português, e os
--      dois gatilhos repontados para ela. A coluna volta a existir.
--
--   2. A asserção que faltava: todo gatilho de toque grava numa coluna que a
--      tabela dele tem. Essa invariante nunca foi verificada, e é por isso que
--      a 11b passou verde em três suítes e quebrou na primeira escrita real.
-- ============================================================================

-- 1. A função em português, para as tabelas que deliberadamente continuaram
--    em português. Mesma forma da irmã em inglês — inclusive o `search_path`
--    vazio, que obriga o nome qualificado em tudo que ela tocar.
create or replace function util.touch_atualizado_em()
returns trigger
language plpgsql
set search_path to ''
as $function$
begin
  new.atualizado_em := now();
  return new;
end $function$;

comment on function util.touch_atualizado_em() is
  'Toque de `atualizado_em` nas tabelas de ingestão, que ficaram fora da '
  'renomeação da 11b porque o runner da sincronização escreve nelas. '
  'A irmã em inglês é util.touch_updated_at().';

-- 2. Os dois gatilhos que a 11b deixou apontando para a função errada.
drop trigger if exists trg_atualizado_em on app.batida_marcacao;
create trigger trg_atualizado_em
  before update on app.batida_marcacao
  for each row execute function util.touch_atualizado_em();

drop trigger if exists trg_atualizado_em on app.cursor_sincronizacao;
create trigger trg_atualizado_em
  before update on app.cursor_sincronizacao
  for each row execute function util.touch_atualizado_em();

-- ============================================================================
-- A garantia: nenhum gatilho de toque grava numa coluna que não existe.
-- ============================================================================
do $$
declare
  v_quebrados text;
  v_n         int;
begin
  -- A invariante, dita uma vez e válida para os dois idiomas: a função de
  -- toque nomeia a coluna que grava, então a tabela precisa tê-la.
  select string_agg(format('%s.%s (gatilho %s -> %s, falta %s)',
                           c.relnamespace::regnamespace, c.relname,
                           t.tgname, p.proname, esperado.col), '; '),
         count(*)
    into v_quebrados, v_n
  from pg_trigger t
  join pg_class c on c.oid = t.tgrelid
  join pg_proc  p on p.oid = t.tgfoid
  cross join lateral (
    select case p.proname
             when 'touch_updated_at'    then 'updated_at'
             when 'touch_atualizado_em' then 'atualizado_em'
           end as col
  ) as esperado
  where not t.tgisinternal
    and p.pronamespace = 'util'::regnamespace
    and esperado.col is not null
    and not exists (
      select 1 from pg_attribute a
       where a.attrelid = c.oid
         and a.attname  = esperado.col
         and a.attnum > 0
         and not a.attisdropped
    );

  if v_n > 0 then
    raise exception 'gatilho de toque sem a coluna que ele grava: %', v_quebrados;
  end if;

  -- E o caso concreto que motivou a migration, nomeado para não voltar em
  -- silêncio se alguém repontar os gatilhos de novo.
  if (select count(*)
        from pg_trigger t
        join pg_class c on c.oid = t.tgrelid
        join pg_proc  p on p.oid = t.tgfoid
       where not t.tgisinternal
         and p.proname = 'touch_atualizado_em'
         and c.relname in ('batida_marcacao', 'cursor_sincronizacao')
         and c.relnamespace = 'app'::regnamespace) <> 2 then
    raise exception 'as duas tabelas de ingestão não estão no toque em português';
  end if;

  select count(*) into v_n
    from pg_trigger t
    join pg_proc p on p.oid = t.tgfoid
   where not t.tgisinternal and p.pronamespace = 'util'::regnamespace
     and p.proname in ('touch_updated_at', 'touch_atualizado_em');

  raise notice 'OK: % gatilho(s) de toque, todos gravando em coluna existente.', v_n;
end $$;
