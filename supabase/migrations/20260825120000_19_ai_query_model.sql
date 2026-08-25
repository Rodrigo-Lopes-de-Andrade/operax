-- ============================================================================
-- OperaX — 19. TOKENS WITHOUT A MODEL NAME ARE NOT A COST
-- ----------------------------------------------------------------------------
-- Migration 09 created `app.ai_query` with `input_tokens` and `output_tokens`,
-- and said why in a comment on the column: "Custo de LLM é variável e sai da
-- sustentação mensal. Sem medir, não dá para saber se a margem virou negativa."
--
-- The measurement does not work. A token is not a price: the same 10.000 tokens
-- cost one number on a small model and another on a large one, the backend runs
-- multi-provider on purpose, and the model id is a field the panel may send. So
-- a table of token counts with no model column answers "quantos tokens?" and
-- cannot answer "quanto custou?", which is the only question the column was
-- created to answer.
--
-- The value is chosen by `operax.agente.agente.build_model` against a closed
-- allowlist, never by the client, so what lands here is one of a handful of
-- known ids and not free text from a request body.
--
-- Nullable, and it stays nullable: the rows written before this migration ran
-- have no honest value to backfill, and inventing today's default for them
-- would put a wrong price on a past month.
--
-- No RLS change, no grant change and no new column in a `public` view — the
-- policy of migration 09 (`user_id = auth.uid() or util.is_admin`) already
-- decides who reads this table, and it keeps deciding.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

alter table app.ai_query add column if not exists model text;

comment on column app.ai_query.model is
  'Id do modelo que respondeu, da allowlist de operax/agente/agente.py. Sem ele '
  'os contadores de token não viram dinheiro, que é para o que eles existem.';

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
declare
  v_tenant uuid;
  v_id     uuid;
  v_lido   text;
begin
  -- 1. A coluna existe, é texto e aceita nulo.
  if not exists (
    select 1 from information_schema.columns
    where table_schema = 'app' and table_name = 'ai_query' and column_name = 'model'
      and data_type = 'text' and is_nullable = 'YES'
  ) then
    raise exception 'app.ai_query.model não existe, não é text, ou é not null';
  end if;

  -- 2. A tabela continua fechada para `anon`. Uma coluna nova numa tabela com
  --    pergunta de gestor dentro não pode ter afrouxado nada.
  if has_table_privilege('anon', 'app.ai_query', 'select') then
    raise exception 'anon enxerga app.ai_query';
  end if;

  -- 3. Teste vivo: gravar e ler de volta.
  select id into v_tenant from app.tenant order by created_at limit 1;
  if v_tenant is null then
    raise notice 'sem tenant: prova viva pulada (a coluna já foi verificada acima)';
    return;
  end if;

  insert into app.ai_query (tenant_id, question, model, input_tokens, output_tokens)
  values (v_tenant, '__migration_19__', 'gpt-5.4-mini', 1, 1)
  returning id into v_id;

  select model into v_lido from app.ai_query where id = v_id;
  if v_lido is distinct from 'gpt-5.4-mini' then
    raise exception 'o modelo gravado não voltou: %', coalesce(v_lido, '<null>');
  end if;

  delete from app.ai_query where id = v_id;

  raise notice 'OK: app.ai_query registra qual modelo respondeu.';
end $$;
