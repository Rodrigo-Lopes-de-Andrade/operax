-- ============================================================================
-- OperaX — dp_banking_domain. O QUARTO EIXO DE SENSIBILIDADE
-- ----------------------------------------------------------------------------
-- `app.sensitive_domain` declara três domínios desde a migration 02 e ganhou o
-- quarto — `disciplinary` — junto com a tabela que o usava. Conta bancária é o
-- quinto valor do enum e o quarto eixo que a etapa DP precisa: quem monta a
-- remessa do vale transporte alcança o número da conta, quem cuida de saúde não.
--
-- ⛔ ESTA MIGRATION FAZ UMA COISA SÓ, E A SOLIDÃO É O PONTO DELA
-- O Postgres aceita `ALTER TYPE ... ADD VALUE` dentro de uma transação, mas
-- **proíbe usar o valor novo na mesma transação** — e cada migration do Supabase
-- roda em uma. Semear `app.domain_permission` com `'banking'` aqui falharia com
-- `unsafe use of new value`, e falharia no deploy, não no teste: um banco que já
-- tem o valor passa pelo `if not exists` e nunca exercita o caminho ruim.
--
-- Por isso a tabela, as policies e a semente da matriz vivem em
-- `dp_banking_account`, o arquivo seguinte. Juntar os dois é regredir para um
-- erro que só aparece em banco novo. Ver `docs/SPEC-DP.md` §1a.
--
-- A prova abaixo lê o CATÁLOGO (`pg_enum.enumlabel`, que é texto) em vez de
-- comparar contra o valor do enum: comparar exigiria o cast que esta transação
-- não pode fazer, e a asserção derrubaria a própria migration.
--
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

alter type app.sensitive_domain add value if not exists 'banking';

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
begin
  if not exists (
    select 1
      from pg_enum e
      join pg_type t      on t.oid = e.enumtypid
      join pg_namespace n  on n.oid = t.typnamespace
     where n.nspname = 'app'
       and t.typname = 'sensitive_domain'
       and e.enumlabel::text = 'banking'
  ) then
    raise exception 'app.sensitive_domain não ganhou o valor banking';
  end if;

  raise notice 'OK: app.sensitive_domain tem o quarto eixo. A tabela vem na próxima migration.';
end $$;
