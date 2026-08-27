-- ============================================================================
-- OperaX — limpezas que precedem o lote de migrations da janela
-- ----------------------------------------------------------------------------
-- Roda UMA VEZ, no início do passo 2 da janela, antes do lote inteiro (a
-- verificação aceita tanto `util.tem_tenant` quanto `util.has_tenant`, então
-- tanto faz vir antes ou depois do 11b). E roda igual no ensaio, senão o ensaio prova um caminho que a janela
-- não vai percorrer.
--
-- POR QUE ISTO NÃO É UMA MIGRATION
-- Só existe uma coisa aqui, e ela conserta a aplicação da migration 24 sobre um
-- banco que a 24 não previu. Uma migration nova não serviria: ela rodaria
-- DEPOIS da 24, e a 24 é justamente quem aborta. Editar a 24 também não —
-- migration aplicada não se edita (CLAUDE.md), e ela já está aplicada na suíte e
-- no banco de desenvolvimento.
--
-- O QUE A 24 ENCONTRA EM PRODUÇÃO
-- As quatro tabelas de ingestão existem lá desde antes deste repositório, cada
-- uma com a policy `<tabela>_tenant_leitura`. A 24 cria `<tabela>_tenant_read`.
-- Resultado: duas policies, e a guarda da própria 24 derruba a aplicação com
--
--     app.batida_marcacao tem 2 policies, esperava 1
--
-- ⛔ NÃO HÁ MUDANÇA SEMÂNTICA AQUI, E ISSO É VERIFICÁVEL
-- As duas policies são `for select to authenticated using (util.has_tenant(tenant_id))`
-- — o mesmo comando, o mesmo papel, o mesmo predicado. Em produção a antiga
-- ainda diz `util.tem_tenant`, e o 11b a reescreve para `util.has_tenant` ao
-- renomear a função. Policies são combinadas por OR, então uma ou duas cópias do
-- mesmo predicado autorizam exatamente as mesmas linhas. O que muda é o nome.
--
-- SE A JANELA ABORTAR ENTRE ESTE ARQUIVO E A 24
-- As quatro ficam com RLS ligada e ZERO policy — que em Postgres nega tudo. O
-- modo de falha é fechado, não aberto: ninguém passa a ver o que não via. O
-- conserto é aplicar a 24, ou restaurar o ponto de restauração.
--
-- Idempotente.
-- ============================================================================

do $$
declare
  t   text;
  pol text;
  v   int;
begin
  foreach t in array array[
    'batida_marcacao','cursor_sincronizacao','empresa_evento_status','funcionario_evento_status'
  ] loop
    if to_regclass('app.' || quote_ident(t)) is null then
      continue;  -- banco que nunca teve a tabela: a 24 a cria, e não há o que limpar
    end if;

    pol := t || '_tenant_leitura';

    -- Só remove o que for de fato a duplicata: mesmo comando, mesmo predicado.
    -- Uma policy homônima com outra regra não é o caso previsto aqui, e apagá-la
    -- em silêncio seria mudar autorização por engano.
    select count(*) into v
      from pg_policies
     where schemaname = 'app' and tablename = t and policyname = pol
       and cmd = 'SELECT'
       and qual in ('util.has_tenant(tenant_id)', 'util.tem_tenant(tenant_id)');

    if v = 1 then
      execute format('drop policy %I on app.%I', pol, t);
      raise notice 'removida a duplicata app.%.%', t, pol;
    elsif exists (select 1 from pg_policies
                   where schemaname='app' and tablename=t and policyname=pol) then
      raise exception
        'app.%.% existe mas não é a duplicata esperada — conferir antes de seguir', t, pol;
    end if;
  end loop;
end $$;
