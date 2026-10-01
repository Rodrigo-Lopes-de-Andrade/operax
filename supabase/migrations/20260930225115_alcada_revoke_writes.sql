-- ============================================================================
-- OperaX — alcada_revoke_writes. OS CINCO CONTORNOS DA ALÇADA NO BANCO
-- ----------------------------------------------------------------------------
-- Sprint P1.2b de `docs/SPRINTS-ALCADA.md`. Decisões do dono de 29/09/2026
-- (as três primeiras tabelas) e de 30/09/2026 (`tenant_member` e `user_scope`),
-- paradas de policy/grant cumpridas: revogar a escrita de `authenticated`.
--
-- POR QUÊ. A revisão de justificativa só deveria entrar por
-- `public.fn_revisar_justificativa` (definer: checa o papel em
-- `app.tenant_member`, o autor, `approval_owner_only` em `app.employee`, e move
-- o desvio por `app.revoke_deviation`). Grants antigos, das migrations 02, 04 e
-- 05, davam a quem fala como `authenticated` cinco atalhos em volta dela:
--   1. `justification_write` (insert, `util.can_see_employee`): inserir uma
--      justificativa já `status = 'accepted'`, sem revisão nenhuma.
--   2. `deviation_write` (update, `util.is_admin`, que inclui `hr`): mover o
--      desvio para `justified` por UPDATE direto.
--   3. `employee_write` (`for all`, `util.is_admin`): o `hr` zerar a própria
--      `approval_owner_only` — e aí aprovar a si mesmo.
--   4. `tenant_member_admin` (`for all`, `util.is_admin`): o `hr` se promover
--      a `owner`, e o `personnel` (que é admin e não revisa) se promover a `hr`
--      e passar a aprovar pela própria RPC. É o papel que a RPC confere.
--   5. `escopo_admin` em `app.user_scope` (`for all`, `util.is_admin`): todo
--      admin redesenhar o recorte de qualquer usuário do tenant, inclusive o
--      próprio. Não é a decisão, é quem enxerga o quê — mesmo desenho, mesma
--      decisão do dono.
-- `app` está fora do PostgREST, então os cinco só eram alcançáveis por código
-- rodando como `authenticated` (hoje, `user_scope` no backend).
--
-- O QUE ISTO GARANTE, E O QUE NÃO GARANTE.
-- Garante: como `authenticated`, nenhuma tabela que a RPC consulta para decidir
-- é gravável — `tenant_member`, `justification`, `employee` e `deviation_event`
-- saem aqui; `justification_review` e `payroll_period` já não tinham grant de
-- escrita. O único caminho do usuário até uma decisão é a RPC.
-- NÃO garante, e continua dependendo de não existir código que o faça:
--   * o que o backend grava em `tenant_scope` e o motor/Edge Functions gravam
--     por conexão direta. Esses papéis (`postgres`/`service_role`) passam por
--     cima de grant e de RLS; quem escreve nessas cinco tabelas por ali tem de
--     autorizar antes, em código, como as rotas de hoje fazem no `user_scope`.
--     Uma rota nova que grave `tenant_member` ou `approval_owner_only` sem
--     checar `owner` reabre o contorno, e o banco não vê.
--   * as demais tabelas de `app` com escrita de admin (`unit`,
--     `unit_secullum_map`, `deviation_type_config`, `employee_pii`, …) seguem
--     como estão. Nenhuma é lida pela RPC; elas não foram tocadas.
--
-- PREMISSA MEDIDA (29/09 e 30/09 pelo orquestrador, refeita antes desta
-- migration): nenhum escritor dessas cinco tabelas roda como `authenticated`.
-- A rota de justificativa (`motor/justificativa.py`), a curadoria
-- (`ALLOCATE_SQL`, `EXCEPTION_SQL`), `rh/employees.py`, `rh/repository.py` e
-- `alertas/ciclo.py` autorizam no `user_scope` e gravam no `tenant_scope`; o
-- motor e `supabase/functions/` conectam direto; nenhuma rota, Edge Function ou
-- tela grava `tenant_member` ou `user_scope` (só `supabase/seed.sql` e os
-- testes, como `postgres`); `fn_revisar_justificativa` é definer; o `98` só
-- grava nelas no preparo, como `postgres`. Se essa premissa cair, quem escreve
-- como o usuário recebe `permission denied` — alto, que é o certo.
--
-- O QUE MUDA, e só isto:
--   * `app.justification`   — sai o INSERT de `authenticated` e a policy
--                             `justification_write`.
--   * `app.deviation_event` — sai o UPDATE de `authenticated` e a policy
--                             `deviation_write`.
--   * `app.employee`        — saem INSERT, UPDATE e DELETE de `authenticated`
--                             e a policy `employee_write`.
--   * `app.tenant_member`   — saem INSERT, UPDATE e DELETE de `authenticated`
--                             e a policy `tenant_member_admin`.
--   * `app.user_scope`      — saem INSERT, UPDATE e DELETE de `authenticated`
--                             e a policy `escopo_admin`.
-- O `revoke` no nível da tabela leva junto o privilégio de coluna (é a regra do
-- Postgres para REVOKE de tabela); o bloco final confere os dois níveis.
--
-- O QUE NÃO MUDA: SELECT de `authenticated` e as policies de leitura
-- (`justification_read`, `deviation_read`, `employee_read`,
-- `tenant_member_read`, `escopo_read`). Três das policies que saem eram
-- `for all` e por isso também davam SELECT; a leitura fica IGUAL sem elas,
-- porque policies permissivas somam por OR e o `using` de cada uma,
-- `util.is_admin(tenant_id)`, já está contido na de leitura:
--   * `employee_read` tem `util.is_admin(tenant_id)` como primeiro termo;
--   * `escopo_read` tem `... or util.is_admin(tenant_id)`;
--   * `tenant_member_read` é `util.has_tenant(tenant_id)`, e `util.is_admin`
--     é `util.has_tenant` com um filtro de papel a mais.
-- `service_role` não é tocado. Nenhuma outra tabela.
--
-- Idempotente: `drop policy if exists` e `revoke` de privilégio ausente é no-op.
-- ============================================================================

drop policy if exists justification_write on app.justification;
revoke insert on table app.justification from authenticated;

drop policy if exists deviation_write on app.deviation_event;
revoke update on table app.deviation_event from authenticated;

drop policy if exists employee_write on app.employee;
revoke insert, update, delete on table app.employee from authenticated;

drop policy if exists tenant_member_admin on app.tenant_member;
revoke insert, update, delete on table app.tenant_member from authenticated;

drop policy if exists escopo_admin on app.user_scope;
revoke insert, update, delete on table app.user_scope from authenticated;

-- ---------------------------------------------------------------------------
-- Garantia: falha alto se a escrita ou a policy sobreviver, ou se a leitura
-- tiver ido junto.
-- ---------------------------------------------------------------------------
do $$
declare
  v_tabela text;
  v_verbo  text;
begin
  foreach v_tabela in array array['app.justification', 'app.deviation_event', 'app.employee',
                                  'app.tenant_member', 'app.user_scope'] loop
    foreach v_verbo in array array['INSERT', 'UPDATE', 'DELETE'] loop
      if has_table_privilege('authenticated', v_tabela, v_verbo) then
        raise exception '% ainda concede % a authenticated (tabela)', v_tabela, v_verbo;
      end if;
      -- DELETE não existe no nível de coluna.
      if v_verbo <> 'DELETE'
         and has_any_column_privilege('authenticated', v_tabela, v_verbo) then
        raise exception '% ainda concede % a authenticated (coluna)', v_tabela, v_verbo;
      end if;
    end loop;
    if exists (
      select 1 from information_schema.column_privileges
       where table_schema = 'app' and table_name = split_part(v_tabela, '.', 2)
         and grantee = 'authenticated' and privilege_type in ('INSERT', 'UPDATE')
    ) then
      raise exception '% ainda concede escrita de coluna a authenticated', v_tabela;
    end if;
    if not has_table_privilege('authenticated', v_tabela, 'SELECT') then
      raise exception '% perdeu o SELECT de authenticated — a leitura não era para mudar', v_tabela;
    end if;
  end loop;

  if exists (
    select 1 from pg_policies
     where schemaname = 'app'
       and (tablename, policyname) in (('justification', 'justification_write'),
                                       ('deviation_event', 'deviation_write'),
                                       ('employee', 'employee_write'),
                                       ('tenant_member', 'tenant_member_admin'),
                                       ('user_scope', 'escopo_admin'))
  ) then
    raise exception 'uma das cinco policies de escrita (justification_write, deviation_write, employee_write, tenant_member_admin, escopo_admin) ainda existe';
  end if;

  -- As de leitura ficam, e ficam sozinhas: sem outra policy nessas tabelas,
  -- nenhuma escrita por RLS volta por um nome diferente.
  if (select array_agg(tablename || '.' || policyname order by tablename, policyname)
        from pg_policies
       where schemaname = 'app'
         and tablename in ('justification', 'deviation_event', 'employee',
                           'tenant_member', 'user_scope'))
     is distinct from
     array['deviation_event.deviation_read', 'employee.employee_read',
           'justification.justification_read', 'tenant_member.tenant_member_read',
           'user_scope.escopo_read']::text[] then
    raise exception 'as cinco tabelas deviam ter só as policies de leitura (deviation_read, employee_read, justification_read, tenant_member_read, escopo_read)';
  end if;

  raise notice 'OK: authenticated só lê justification, deviation_event, employee, tenant_member e user_scope; as cinco policies de escrita saíram.';
end $$;
