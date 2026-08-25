-- ============================================================================
-- OperaX — 15. REBRAND: O TENANT ÂNCORA É FASTPARK
-- ----------------------------------------------------------------------------
-- O produto é white-label. "OperaX" é o nome dele no repositório, nos
-- identificadores e nos documentos; o que o usuário vê é a marca do cliente.
-- O cliente âncora é FastPark, e o tenant que a migration 02 semeou precisa
-- dizer isso — é o `name` que vai para a tela e para o texto do alerta.
--
-- Por que uma migration nova em vez de corrigir a 02: migration aplicada não se
-- edita (CLAUDE.md). O replay continua sendo 02 insere `kastro-park`, 03 o
-- encontra pelo slug e levanta exceção se não encontrar, e esta migration, no
-- fim da fila, renomeia. Banco novo termina em FastPark sem que nenhum passo
-- anterior precise saber disso.
--
-- Nada de schema muda aqui. É uma linha de dado, e é o `id` — não o slug — que
-- todas as chaves estrangeiras carregam, então o rename não move nenhuma linha.
-- ============================================================================

update app.tenant
   set slug = 'fastpark',
       name = 'FastPark'
 where slug = 'kastro-park';

-- ---------------------------------------------------------------------------
-- Prova: o âncora existe com o nome novo e o antigo não sobrou em lugar nenhum.
-- ---------------------------------------------------------------------------
do $$
declare
  v_novo   bigint;
  v_antigo bigint;
begin
  select count(*) into v_novo   from app.tenant where slug = 'fastpark';
  select count(*) into v_antigo from app.tenant where slug = 'kastro-park';

  if v_novo <> 1 then
    raise exception 'esperava exatamente 1 tenant com slug fastpark, encontrei %', v_novo;
  end if;
  if v_antigo <> 0 then
    raise exception 'o tenant kastro-park continua existindo (% linha(s))', v_antigo;
  end if;

  raise notice 'OK: tenant âncora renomeado para FastPark.';
end $$;
