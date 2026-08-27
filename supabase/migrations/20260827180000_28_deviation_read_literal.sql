-- ============================================================================
-- OperaX — 28. O RENAME DEIXOU 'producao' DENTRO DE UMA POLICY
-- ----------------------------------------------------------------------------
-- Achado pelo re-ensaio da fase 2 em 27/08/2026, contra um projeto Supabase de
-- verdade com o schema de produção renomeado.
--
-- A migration 11b traduz muita coisa e acerta quase tudo: as seis views de
-- `public` que filtram por modo, as check constraints de `deviation_event` e
-- `detection_run`, e o default da coluna. O que ela faz com as policies é
-- RENOMEAR — `deviation_leitura` vira `deviation_read` — e renomear uma policy
-- não reescreve a expressão dela. O literal em português sobrevive:
--
--     deviation_read:  ((mode = 'producao'::text) OR util.is_admin(tenant_id)) AND ...
--
-- Enquanto isso o default da coluna, as constraints, as views e todo o código
-- deste repositório passam a escrever `'production'`.
--
-- ⛔ A CONSEQUÊNCIA É SILENCIOSA E ATINGE EXATAMENTE QUEM O PRODUTO SERVE
-- O primeiro conjunto da policy vira `('production' = 'producao' or is_admin)`.
-- Para um admin, o `or` salva e ele vê tudo. Para qualquer outro papel é `false`,
-- e o `and` seguinte não importa mais: **o supervisor de unidade vê zero
-- desvios**. Sem erro, sem log — o painel abre vazio e parece um dia tranquilo.
--
-- Medido no staging renomeado, como o supervisor de A Centro: 1 unidade,
-- 1 colaborador, e 0 em `vw_deviation_event`, `fn_ranking_by_unit`,
-- `fn_ranking_by_employee` e `fn_ranking_by_manager`.
--
-- A varredura de literais em português dentro de policies achou EXATAMENTE esta.
-- As demais estão limpas.
--
-- POR QUE A SUÍTE NÃO PEGOU ANTES
-- Toda asserção de supervisor sobre desvio em `98_teste_isolamento_tenant.sql`
-- era `= 0`: "não vê a outra unidade", "não vê sombra". Nenhuma exigia que ele
-- VISSE algo. A asserção do ranking por gestor (migration 27) foi a primeira, e
-- caiu na hora. Esta migration vem junto com uma segunda asserção que fecha o
-- buraco de forma direta.
--
-- O TEXTO ABAIXO É CÓPIA FIEL DO DA MIGRATION 05
-- Não é policy nova nem regra nova: é a mesma autorização que este repositório
-- sempre teve, reafirmada por cima da que o rename deixou pela metade. Em banco
-- que nasceu das migrations daqui, roda e não muda nada.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

drop policy if exists deviation_read on app.deviation_event;
create policy deviation_read on app.deviation_event
  for select to authenticated
  using (
    (mode = 'production' or util.is_admin(tenant_id))
    and (
      util.is_admin(tenant_id)
      or (unit_id is not null and util.can_see_unit(unit_id))
      or (unit_id is null     and util.can_see_company(company_id))
    )
  );

do $$
declare v text;
begin
  select qual into v from pg_policies
   where schemaname = 'app' and tablename = 'deviation_event' and policyname = 'deviation_read';

  if v is null then
    raise exception 'deviation_read não existe depois de ser criada';
  end if;

  -- ⛔ A guarda é sobre o LITERAL, porque é o literal que o rename erra. Uma
  --    migration futura que recrie esta policy a partir do texto de produção
  --    reintroduz o bug, e é isto que a impede de passar despercebida.
  if v like '%producao%' then
    raise exception 'deviation_read ainda compara modo com um literal em português: %', v;
  end if;
  if v not like '%production%' then
    raise exception 'deviation_read não compara modo com ''production'': %', v;
  end if;

  raise notice 'OK: deviation_read compara modo em inglês, como o resto do schema.';
end $$;
