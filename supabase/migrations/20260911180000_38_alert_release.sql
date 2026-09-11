-- ============================================================================
-- OperaX — 38. A ENTREGA DE ALERTA PASSA A EXIGIR UMA LIBERAÇÃO REGISTRADA
-- ----------------------------------------------------------------------------
-- O gate do sender (`backend/operax/alertas/sender.py`, `_GATE_SQL`) perguntava
-- uma coisa só: "existe execução completa do motor em produção?". A premissa,
-- escrita no próprio comentário, era que promover o motor É "a sombra fechou".
--
-- Em 09/09/2026 a premissa quebrou: o dono promoveu o motor para o DP ver dado
-- no painel, com o censo do G4 ainda em zero adjudicações. Desde então a porta
-- do sender está aberta, e o que impede uma mensagem de chegar a um gestor com a
-- taxa de falso positivo não medida é a ausência de regra de alerta cadastrada —
-- acidente, não desenho. A regra 8 do `CLAUDE.md` diz "nenhum alerta antes de a
-- sombra fechar com falso positivo ≤5%", e "fechar" é uma medição, não um
-- deploy.
--
-- ESTA TABELA É A MEDIÇÃO VIRANDO FATO
-- Uma linha aqui é alguém dizendo, com nome, data e o número na mão: "o censo
-- fechou, a taxa foi X, liberem". Quem grava é o comando `liberar` de
-- `backend/operax/motor/adjudicacao.py`, que só aceita gravar depois de `medir`
-- responder PASSA sobre censo COMPLETO. O sender passa a exigir as duas coisas:
-- motor promovido E liberação vigente. Sem a linha, nada sai — com ou sem regra,
-- com ou sem credencial de provedor.
--
-- POR QUE UMA LINHA POR LIBERAÇÃO, COM REVOGAÇÃO NA PRÓPRIA LINHA
-- Uma trava que só fecha é uma porta de mão única. Se a taxa subir depois de
-- liberada, alguém precisa poder fechar de novo, e a revogação fica NA linha
-- que ela desfaz: `revoked_at` preenchido é liberação que deixou de valer. Uma
-- nova liberação é linha nova. O histórico é a tabela inteira, sem delete.
--
-- POLICY: quem vê o censo vê a liberação
-- `util.is_admin` (owner, hr, personnel) — o mesmo conjunto que lê
-- `app.deviation_adjudication` e o evento em sombra. Só `select`: gravar é ato
-- do comando, que roda como o backend, nunca do navegador. Autorizada pelo dono
-- em 11/09/2026.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

create table if not exists app.alert_release (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references app.tenant(id) on delete cascade,
  --: Quem liberou, como veio da linha de comando — o mesmo par de
  --: `app.deviation_adjudication.author_name`: não há sessão autenticada num
  --: comando, e inventar um usuário de sistema seria fingir uma identidade.
  released_by    text not null,
  released_at    timestamptz not null default now(),
  --: Os números que sustentaram a decisão, copiados no ato. Se o censo mudar
  --: depois, esta linha continua dizendo o que era verdade quando alguém
  --: assinou embaixo.
  census_size    integer not null,
  judged         integer not null,
  false_positives integer not null,
  measured_rate  numeric(5,2) not null,
  note           text,
  revoked_by     text,
  revoked_at     timestamptz,
  revoked_note   text,
  constraint alert_release_census_complete
    check (judged = census_size and census_size > 0),
  constraint alert_release_rate_within_gate
    check (measured_rate >= 0 and measured_rate <= 5.00),
  constraint alert_release_revocation_whole
    check ((revoked_at is null) = (revoked_by is null))
);

comment on table app.alert_release is
  'Liberação registrada da entrega de alertas — a regra 8 virando fato. Uma linha por '
  'liberação, gravada pelo comando `liberar` só depois de `medir` responder PASSA sobre '
  'censo completo; `revoked_at` preenchido é liberação que deixou de valer. O sender exige '
  'motor promovido E uma linha vigente aqui. Ver docs/DECISAO-VERDADE-DE-REFERENCIA-G4.md.';

comment on column app.alert_release.measured_rate is
  'Falso positivo em porcentagem no ato da liberação. O check em 5.00 é a regra 8 escrita '
  'no schema: uma liberação acima do teto não existe.';

alter table app.alert_release enable row level security;

revoke all on table app.alert_release from anon, authenticated;
grant select on table app.alert_release to authenticated;
grant select, insert, update on table app.alert_release to service_role;

drop policy if exists alert_release_read on app.alert_release;
create policy alert_release_read on app.alert_release
  for select to authenticated
  using (util.is_admin(tenant_id));

-- ---------------------------------------------------------------------------
-- Prova viva
-- ---------------------------------------------------------------------------
do $$
declare
  v_tenant    uuid;
  v_id        uuid;
  v_barrou    boolean;
  v_sintetico boolean := false;
begin
  if not exists (
    select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'app' and c.relname = 'alert_release' and c.relrowsecurity
  ) then
    raise exception 'app.alert_release sem RLS';
  end if;

  if not exists (
    select 1 from pg_policies
     where schemaname = 'app' and tablename = 'alert_release'
       and policyname = 'alert_release_read' and cmd = 'SELECT'
  ) then
    raise exception 'alert_release_read não existe ou não é só de leitura';
  end if;

  -- O navegador lê e NÃO escreve: é o verbo ausente que faz da linha um ato.
  if has_table_privilege('authenticated', 'app.alert_release', 'insert')
     or has_table_privilege('authenticated', 'app.alert_release', 'update')
     or has_table_privilege('authenticated', 'app.alert_release', 'delete') then
    raise exception 'authenticated pode escrever em alert_release — liberar viraria clique';
  end if;
  if not has_table_privilege('authenticated', 'app.alert_release', 'select') then
    raise exception 'authenticated não lê alert_release — a policy autorizada ficaria inerte';
  end if;

  select id into v_tenant from app.tenant order by created_at limit 1;
  if v_tenant is null then
    insert into app.tenant (slug, name) values ('migration-38-prova', 'Prova da migration 38')
    returning id into v_tenant;
    v_sintetico := true;
  end if;

  -- 1. Liberação acima do teto é recusada pelo schema, não só pelo comando.
  v_barrou := false;
  begin
    insert into app.alert_release (tenant_id, released_by, census_size, judged, false_positives, measured_rate)
    values (v_tenant, '__migration_38__', 100, 100, 6, 6.00);
  exception when check_violation then v_barrou := true; end;
  if not v_barrou then raise exception 'liberação com 6%% de falso positivo foi aceita'; end if;

  -- 2. Censo incompleto é recusado: taxa sobre parcial é o falso verde de sempre.
  v_barrou := false;
  begin
    insert into app.alert_release (tenant_id, released_by, census_size, judged, false_positives, measured_rate)
    values (v_tenant, '__migration_38__', 100, 40, 0, 0.00);
  exception when check_violation then v_barrou := true; end;
  if not v_barrou then raise exception 'liberação sobre censo parcial foi aceita'; end if;

  -- 3. A legítima passa — sem isto, as duas acima ficariam verdes numa tabela
  --    que recusa tudo.
  insert into app.alert_release (tenant_id, released_by, census_size, judged, false_positives, measured_rate)
  values (v_tenant, '__migration_38__', 100, 100, 3, 3.00)
  returning id into v_id;

  -- 4. Revogação pela metade é recusada: quem revoga assina.
  v_barrou := false;
  begin
    update app.alert_release set revoked_at = now() where id = v_id;
  exception when check_violation then v_barrou := true; end;
  if not v_barrou then raise exception 'revogação sem autor foi aceita'; end if;

  update app.alert_release set revoked_at = now(), revoked_by = '__migration_38__' where id = v_id;

  delete from app.alert_release where released_by = '__migration_38__';
  if v_sintetico then delete from app.tenant where id = v_tenant; end if;

  raise notice 'OK: liberação só com censo completo e taxa no teto, revogação assinada, navegador só lê.';
end $$;
