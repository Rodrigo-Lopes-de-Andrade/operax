-- ============================================================================
-- OperaX — usuarios_escopo_constraint. SCOPE STOPS HAVING WILDCARDS
-- ----------------------------------------------------------------------------
-- Sprint U1 of `docs/SPRINTS-USUARIOS.md`, shape in `docs/SPEC-USUARIOS.md`
-- §3.3 and §5.1. First migration of the stage, and alone on purpose: it may
-- fail on a finding, and failing alone is what keeps the finding readable.
--
-- WHY. `util.can_see_unit` and `util.can_see_company` (as recreated by
-- `11b_rename_pt_en.sql`; no later migration touches them) read a NULL column
-- in `app.user_scope` as "any":
--   can_see_unit:    (company_id is null or company_id = u.company_id)
--                and (unit_id    is null or unit_id    = u.id)
--   can_see_company: (company_id is null or company_id = emp.id)   -- only this
-- Two wildcards follow:
--   1. both NULL      -> the whole tenant, for every non-shortcut role;
--   2. unit_id only   -> one unit, but EVERY company of the tenant, because
--                        `can_see_company` never looks at `unit_id`. That is
--                        the row a user screen would write for every
--                        supervisor (SPEC §3.1, measured: 1 unit, 3 companies).
--
-- WHAT. Two checks and one unique index, and nothing else:
--   * `escopo_nao_vazio`           — a row names a company or a unit;
--   * `escopo_unidade_tem_empresa` — a unit always comes with its company,
--                                    which closes wildcard 2 without touching
--                                    `can_see_company`;
--   * `user_scope_sem_duplicata`   — one row per (user, tenant, company, unit),
--                                    NULLs folded by `coalesce` so that two
--                                    company-only rows collide too.
-- No change to `util.can_see_*`, to any policy or to any grant.
--
-- COST, declared (SPEC §3.3): "every unit" stops being a rule and becomes one
-- row per company. A new company joins nobody's scope by itself.
--
-- IF THIS FAILS TO APPLY, a wildcard scope exists in that database. That is the
-- finding: stop and report. Do not delete the rows — who could see what is
-- evidence.
-- ============================================================================

alter table app.user_scope
  drop constraint if exists escopo_nao_vazio,
  add  constraint escopo_nao_vazio
       check (unit_id is not null or company_id is not null);

alter table app.user_scope
  drop constraint if exists escopo_unidade_tem_empresa,
  add  constraint escopo_unidade_tem_empresa
       check (unit_id is null or company_id is not null);

create unique index if not exists user_scope_sem_duplicata
  on app.user_scope (user_id, tenant_id,
                     coalesce(company_id, '00000000-0000-0000-0000-000000000000'::uuid),
                     coalesce(unit_id,    '00000000-0000-0000-0000-000000000000'::uuid));

-- ---------------------------------------------------------------------------
-- The guarantee, checked by shape and not by name alone: a same-named index
-- without `coalesce` would let two company-only rows coexist, and
-- `if not exists` would keep it silently.
-- ---------------------------------------------------------------------------
do $$
declare
  v_def text;
begin
  select pg_get_constraintdef(c.oid) into v_def
    from pg_constraint c
   where c.conrelid = 'app.user_scope'::regclass
     and c.conname = 'escopo_nao_vazio' and c.contype = 'c' and c.convalidated;
  if v_def is distinct from 'CHECK (((unit_id IS NOT NULL) OR (company_id IS NOT NULL)))' then
    raise exception 'usuarios_escopo_constraint: escopo_nao_vazio ausente ou diferente (%)', v_def;
  end if;

  select pg_get_constraintdef(c.oid) into v_def
    from pg_constraint c
   where c.conrelid = 'app.user_scope'::regclass
     and c.conname = 'escopo_unidade_tem_empresa' and c.contype = 'c' and c.convalidated;
  if v_def is distinct from 'CHECK (((unit_id IS NULL) OR (company_id IS NOT NULL)))' then
    raise exception 'usuarios_escopo_constraint: escopo_unidade_tem_empresa ausente ou diferente (%)', v_def;
  end if;

  select pg_get_indexdef(i.indexrelid) into v_def
    from pg_index i
   where i.indexrelid = to_regclass('app.user_scope_sem_duplicata')
     and i.indrelid = 'app.user_scope'::regclass
     and i.indisunique and i.indisvalid and i.indpred is null
     -- Exactly the four keys: a fifth column would make the uniqueness finer
     -- than (user, tenant, company, unit) while every `like` below still passed.
     and i.indnatts = 4;
  if v_def is null
     or v_def not like '%(user_id, tenant_id, COALESCE(company_id, %'
     or v_def not like '%, COALESCE(unit_id, %' then
    raise exception 'usuarios_escopo_constraint: user_scope_sem_duplicata ausente, sem coalesce ou fora das quatro colunas (%)', v_def;
  end if;
end $$;
