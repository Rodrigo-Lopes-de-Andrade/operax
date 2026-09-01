-- ============================================================================
-- OperaX — o espelho de produção como alvo de ensaio
-- ----------------------------------------------------------------------------
-- Roda depois de `supabase/fixtures/espelho_secullum.sql`, que traz as 22
-- tabelas de `secullum` como produção as tem. Elas não nascem de migration
-- nossa: o espelho é desenho da outra equipe, e até 01/09/2026 não existia em
-- lugar nenhum além de produção.
--
-- A consequência disso foi medida na janela de 31/08: nenhum ensaio jamais
-- executou as Edge Functions deste repositório contra um espelho real, porque
-- não havia contra o que executar. Duas coisas passaram sem ninguém ver — a
-- `sync-cadastro` gravando `departamento_id` numa `Estrutura` que não tem a
-- coluna, e a 11b arrastando gatilhos de produção que este repositório nunca
-- teve. Ver docs/RUNBOOK-JANELA-CONVERGENCIA.md §3b.
--
-- O que este arquivo garante é só o começo: que o alvo existe e está inteiro.
-- Conferir as Edge Functions contra ele é o passo seguinte, e é da próxima
-- janela.
-- ============================================================================

do $$
declare
  v_n     int;
  v_falta text;
begin
  -- 1. O espelho inteiro, não um pedaço dele.
  select count(*) into v_n
    from pg_class c
    join pg_namespace ns on ns.oid = c.relnamespace
   where ns.nspname = 'secullum' and c.relkind in ('r', 'p');

  if v_n <> 22 then
    raise exception 'espelho incompleto: % tabela(s) em secullum, esperado 22', v_n;
  end if;

  -- 2. RLS ligada em toda tabela do espelho. Ele tem PII completa e ZERO policy.
  select string_agg(c.relname, ', ') into v_falta
    from pg_class c
    join pg_namespace ns on ns.oid = c.relnamespace
   where ns.nspname = 'secullum' and c.relkind in ('r', 'p')
     and not c.relrowsecurity;

  if v_falta is not null then
    raise exception 'espelho sem RLS: %', v_falta;
  end if;

  -- 3. FORCE nas PascalCase, que é o cinto que as migrations 00 e 03 põem.
  --    As duas snake_case ficam de fora porque produção as tem assim: foi a
  --    outra equipe que as criou, depois da 03, e ela não aplicou FORCE. Não é
  --    exposição — as duas revogam tudo de anon e authenticated (item 4 abaixo
  --    prova) e FORCE só sujeitaria o próprio dono. É um cinto a menos, e
  --    afirmar aqui que produção o tem seria afirmar o que ela não tem.
  select string_agg(c.relname, ', ') into v_falta
    from pg_class c
    join pg_namespace ns on ns.oid = c.relnamespace
   where ns.nspname = 'secullum' and c.relkind in ('r', 'p')
     and c.relname ~ '^[A-Z]'
     and not c.relforcerowsecurity;

  if v_falta is not null then
    raise exception 'espelho PascalCase sem RLS forçada: %', v_falta;
  end if;

  -- 4. O que de fato protege as 22: nenhum grant para anon nem authenticated.
  select string_agg(format('%s -> %s', c.relname, g.grantee), ', ') into v_falta
    from pg_class c
    join pg_namespace ns on ns.oid = c.relnamespace
    cross join lateral (values ('anon'), ('authenticated')) as g(grantee)
   where ns.nspname = 'secullum' and c.relkind in ('r', 'p')
     and has_table_privilege(g.grantee, c.oid, 'select, insert, update, delete');

  if v_falta is not null then
    raise exception 'espelho alcançável por papel de navegador: %', v_falta;
  end if;

  -- 5. As duas FKs que a migration 24 pula quando não há espelho. O baseline
  --    entrega `Batida` e `Funcionario` antes das migrations, então a 24 as
  --    encontra e a ponte nasce — o que esta asserção garante é que ela nasceu.
  select string_agg(esperada.nome, ', ') into v_falta
    from (values ('batida_marcacao_batida_id_fkey'),
                 ('batida_marcacao_funcionario_id_fkey')) as esperada(nome)
   where not exists (
     select 1 from pg_constraint where conname = esperada.nome and contype = 'f'
   );

  if v_falta is not null then
    raise exception 'a 24 não fechou a ponte para o espelho: falta %', v_falta;
  end if;

  raise notice 'OK: espelho com 22 tabelas, RLS em todas, fora do alcance de anon '
                'e authenticated, ponte da 24 fechada.';
end $$;
