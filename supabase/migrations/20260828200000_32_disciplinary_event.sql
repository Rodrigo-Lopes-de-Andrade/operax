-- ============================================================================
-- OperaX — 32. O DOMÍNIO SENSÍVEL QUE PROTEGIA O VAZIO
-- ----------------------------------------------------------------------------
-- `app.sensitive_domain` declara quatro domínios desde a migration 02, e
-- `app.domain_permission` já concede `disciplinary` a `owner`, `hr` e
-- `personnel` — com `owner` por regra e os outros dois por escolha explícita.
-- O eixo de autorização inteiro existe, configurado e testado.
--
-- E não havia uma única tabela usando esse domínio.
--
-- Não é lacuna de escopo apenas: é inconsistência do nosso próprio modelo, e
-- está registrada como tal na `COBERTURA-ESCOPO.md` (§7). O escopo contratado
-- pede "advertências e ocorrências" na base integrada de pessoas; o modelo já
-- tinha a fechadura, faltava a porta.
--
-- O DESENHO SEGUE `app.occupational_exam`, QUE É O VIZINHO CERTO
-- As duas guardam fato sobre uma pessoa que só um domínio sensível alcança:
-- leitura exige o domínio **e** enxergar a pessoa (`can_see_employee`), escrita
-- exige o domínio. Ver a unidade não basta, e ser gestor da unidade não basta —
-- é o mesmo desenho que impede um supervisor de ler ASO.
--
-- ⛔ SEM DELETE PARA O PAINEL, E ISSO É DELIBERADO
-- Advertência apagada não deixa rastro, e a regra 6 deste projeto já diz o que
-- fazer com fato que perdeu validade: revoga-se, não se apaga. Aqui o painel
-- recebe `select`, `insert` e `update` — nunca `delete`. Registro aplicado por
-- engano se corrige por `update` com trilha em `app.audit_log`, que é o que
-- distingue "corrigido" de "nunca existiu" numa discussão trabalhista.
--
-- `days` SÓ EXISTE PARA SUSPENSÃO
-- Suspensão sem duração não é registro completo, e "3 dias" pendurado numa
-- advertência verbal é dado que ninguém consegue interpretar depois. A restrição
-- amarra os dois.
--
-- ⚠️ `summary` é texto livre sobre uma pessoa, dentro do domínio mais sensível
-- dos quatro. Ele existe porque advertência sem motivo não serve para nada — e
-- **nunca** pode aparecer em view de `public`, nem resumido.
--
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

create table if not exists app.disciplinary_event (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references app.tenant(id) on delete cascade,
  employee_id     uuid not null references app.employee(id) on delete cascade,
  type            text not null check (type in (
                    'verbal_warning', 'written_warning', 'suspension', 'administrative_note')),
  occurred_on     date not null,
  days            integer,
  summary         text,
  -- A carta de advertência assinada, quando existe. `app.document` já guarda
  -- arquivo com vencimento e tipo; não se cria um segundo lugar para papel.
  document_id     uuid references app.document(id) on delete set null,
  -- Ciência do colaborador. Nulo = ainda não deu, e essa diferença importa.
  acknowledged_on date,
  created_by      uuid references auth.users(id),
  created_at      timestamptz not null default now(),
  constraint disciplinary_days_positive check (days is null or days > 0),
  constraint disciplinary_days_only_suspension check (days is null or type = 'suspension')
);
create index if not exists disciplinary_colab_idx
  on app.disciplinary_event (employee_id, occurred_on desc);
create index if not exists disciplinary_tenant_idx
  on app.disciplinary_event (tenant_id, occurred_on desc);
comment on table app.disciplinary_event is
  'Advertência, suspensão e anotação administrativa. Domínio sensível `disciplinary`: ver a '
  'unidade não basta e ser gestor dela não basta. Sem delete para o painel — registro '
  'aplicado por engano se corrige por update, com trilha, nunca por apagamento.';
comment on column app.disciplinary_event.summary is
  'Texto livre sobre uma pessoa, no domínio mais sensível dos quatro. NUNCA em view de public.';

alter table app.disciplinary_event enable row level security;
revoke all on table app.disciplinary_event from anon;
grant select, insert, update on app.disciplinary_event to authenticated;
grant all on app.disciplinary_event to service_role;

drop policy if exists disciplinary_read on app.disciplinary_event;
create policy disciplinary_read on app.disciplinary_event
  for select to authenticated
  using (util.can_see_domain(tenant_id, 'disciplinary') and util.can_see_employee(employee_id));

drop policy if exists disciplinary_write on app.disciplinary_event;
create policy disciplinary_write on app.disciplinary_event
  for all to authenticated
  using (util.can_see_domain(tenant_id, 'disciplinary'))
  with check (util.can_see_domain(tenant_id, 'disciplinary'));

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v_policies int;
  v_papeis   int;
begin
  if to_regclass('app.disciplinary_event') is null then
    raise exception 'app.disciplinary_event não existe depois de ser criada';
  end if;

  if not (select relrowsecurity from pg_class where oid = 'app.disciplinary_event'::regclass) then
    raise exception 'app.disciplinary_event sem RLS — regra 3 do CLAUDE.md';
  end if;

  select count(*) into v_policies from pg_policies
   where schemaname = 'app' and tablename = 'disciplinary_event';
  if v_policies <> 2 then
    raise exception 'app.disciplinary_event tem % policies, esperava 2 (read e write)', v_policies;
  end if;

  if has_table_privilege('anon', 'app.disciplinary_event', 'select') then
    raise exception 'anon alcança app.disciplinary_event';
  end if;

  -- ⛔ A ausência do delete é decisão, não esquecimento. Um `grant all` futuro
  --    a devolveria em silêncio, e o silêncio é o problema.
  if has_table_privilege('authenticated', 'app.disciplinary_event', 'delete') then
    raise exception 'o painel ganhou delete em app.disciplinary_event; a regra 6 diz corrigir, não apagar';
  end if;

  -- As duas restrições que amarram duração a suspensão.
  if (select count(*) from pg_constraint
       where conrelid = 'app.disciplinary_event'::regclass and contype = 'c'
         and conname in ('disciplinary_days_positive', 'disciplinary_days_only_suspension')) <> 2 then
    raise exception 'as restrições de `days` não sobreviveram';
  end if;

  -- E o que motivou a migration: o domínio deixa de proteger o vazio.
  select count(*) into v_papeis from app.domain_permission
   where domain = 'disciplinary' and allowed;
  if v_papeis = 0 then
    raise exception 'nenhum papel alcança o domínio disciplinary: a tabela nasceria invisível';
  end if;

  raise notice 'OK: o domínio disciplinary tem tabela, e % concessão(ões) de papel a alcançam.', v_papeis;
end $$;
