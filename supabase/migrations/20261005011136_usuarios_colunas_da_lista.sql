-- ============================================================================
-- OperaX — usuarios_colunas_da_lista. WHO INVITED, AND WHEN ACCESS ENDED
-- ----------------------------------------------------------------------------
-- Sprint U2 of `docs/SPRINTS-USUARIOS.md`, shape in `docs/SPEC-USUARIOS.md`
-- §5.3. The user list shows "who invited" and the deactivation date; neither
-- column existed.
--
--   * `invited_by`     — the member who called `public.fn_convidar_usuario`.
--                        NULL for every membership born before this migration
--                        (seed, operator SQL): unknown is NULL, never a guess.
--   * `deactivated_at` — written by `public.fn_desativar_membro` together with
--                        `active = false`. A member is never deleted.
--
-- Both are written ONLY by the two definer RPCs of `usuarios_rpc`:
-- `authenticated` has no INSERT/UPDATE on `app.tenant_member` since
-- `alcada_revoke_writes` (P1.2b), and this migration grants nothing.
-- Neither column enters a view of `public`.
--
-- Idempotent. Safe to run repeatedly.
-- ============================================================================

alter table app.tenant_member
  add column if not exists invited_by     uuid references auth.users(id),
  add column if not exists deactivated_at timestamptz;

comment on column app.tenant_member.invited_by is
  'Quem convidou (public.fn_convidar_usuario grava auth.uid()). Nulo = vínculo anterior ao convite pela tela.';
comment on column app.tenant_member.deactivated_at is
  'Quando o acesso foi encerrado (public.fn_desativar_membro, junto de active = false). Membro nunca é apagado.';

-- ---------------------------------------------------------------------------
-- Proof
-- ---------------------------------------------------------------------------
do $$
begin
  if (select format_type(a.atttypid, a.atttypmod) || ':' || (not a.attnotnull)::text
        from pg_attribute a
       where a.attrelid = 'app.tenant_member'::regclass
         and a.attname = 'invited_by' and not a.attisdropped) is distinct from 'uuid:true' then
    raise exception 'app.tenant_member.invited_by ausente, ou não é uuid anulável';
  end if;
  if not exists (
    select 1 from pg_constraint c
     where c.conrelid = 'app.tenant_member'::regclass and c.contype = 'f'
       and c.confrelid = 'auth.users'::regclass
       and c.conkey = array[(select attnum from pg_attribute
                              where attrelid = 'app.tenant_member'::regclass
                                and attname = 'invited_by')]::smallint[]
  ) then
    raise exception 'app.tenant_member.invited_by sem FK para auth.users';
  end if;
  if (select format_type(a.atttypid, a.atttypmod) || ':' || (not a.attnotnull)::text
        from pg_attribute a
       where a.attrelid = 'app.tenant_member'::regclass
         and a.attname = 'deactivated_at' and not a.attisdropped)
     is distinct from 'timestamp with time zone:true' then
    raise exception 'app.tenant_member.deactivated_at ausente, ou não é timestamptz anulável';
  end if;
  -- Nothing new was granted: the two columns are written only by the RPCs.
  if exists (select 1 from unnest(array['INSERT','UPDATE']) v
              where has_column_privilege('authenticated', 'app.tenant_member', 'invited_by', v)
                 or has_column_privilege('authenticated', 'app.tenant_member', 'deactivated_at', v)) then
    raise exception 'authenticated escreve invited_by/deactivated_at direto — só as RPCs de usuarios_rpc podem';
  end if;
  if exists (select 1 from information_schema.columns
              where table_schema = 'public' and column_name in ('invited_by', 'deactivated_at')) then
    raise exception 'invited_by/deactivated_at exposta em view de public — parada obrigatória';
  end if;
  raise notice 'OK: tenant_member ganhou invited_by (FK auth.users) e deactivated_at, sem grant novo e fora de public.';
end $$;
