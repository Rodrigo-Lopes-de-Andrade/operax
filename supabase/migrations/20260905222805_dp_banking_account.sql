-- ============================================================================
-- OperaX — dp_banking_account. A CONTA, QUE É INSUMO DE REMESSA E NÃO DE TELA
-- ----------------------------------------------------------------------------
-- Desenho em `docs/SPEC-DP.md` §1b. Depende de `dp_banking_domain`, que precisa
-- ter COMMITADO: o `'banking'::app.sensitive_domain` da semente é exatamente o
-- uso que o Postgres proíbe na transação que adiciona o valor.
--
-- ⛔ TABELA APARTADA, E NÃO COLUNAS EM `app.employee_pii`
-- O domínio da conta é `banking`, não `pii`. Pendurá-la na PII faria a policy de
-- PII governar dado que não é dela — e o efeito prático seria conceder conta
-- bancária a todo papel que hoje lê RG e CPF, `hr` inclusive.
--
-- ⛔ SEM GRANT PARA `authenticated` — o mesmo desenho de `app.employee_photo`
-- Esta tabela nunca é lida pelo PostgREST. Leitura e escrita só pelo Caminho 2,
-- com o backend revalidando papel e domínio. As policies existem mesmo assim, e
-- não por simetria: se um PR futuro conceder `select` a `authenticated` por
-- engano, a policy é o que ainda está de pé. Defesa que só age quando a anterior
-- falha é o ponto dela.
--
-- DOIS EIXOS PARA LER, TRÊS PARA ESCREVER
-- Leitura: `util.can_see_domain(tenant_id, 'banking')` E `util.can_see_employee(...)`.
-- Ter o domínio não basta se a pessoa está fora do escopo, e ver a pessoa não
-- basta sem o domínio — é o mesmo desenho que impede um supervisor de ler ASO.
--
-- ⛔ A ESCRITA LEVA UM TERCEIRO EIXO: `util.is_admin(tenant_id)`
-- A versão anterior deste arquivo dizia que dois eixos eram o padrão de "toda
-- tabela sensível do projeto". É falso, e se falsifica lendo o repositório:
-- `pii_write` (04), `remuneracao_write` (04), as de acordos (08) e
-- `employee_photo_write` (36 — a que este desenho cita como modelo) TODAS
-- carregam `util.is_admin`. Dois eixos é o padrão de LEITURA.
--
-- O efeito da omissão foi medido, não suposto: `util.is_admin` é
-- `role in ('owner','hr','personnel')` e a semente abaixo dá `banking` a
-- `owner`, `personnel` e `accounting`. Sem o terceiro eixo, `accounting` seria o
-- único papel do produto que grava dado sensível sem ser admin — e como a matriz
-- muda por UPDATE sem deploy, conceder `banking` a um `unit_supervisor` passaria
-- a dar a ele escrita da conta de quem ele supervisiona. Conta bancária é o
-- campo que redireciona pagamento.
--
-- `accounting` mantém `banking` e continua LENDO — a conciliação da remessa é
-- dele. Decisão do dono, 05/09/2026; `docs/SPEC-DP.md` §1b.
--
-- `hr` FICA DE FORA DA MATRIZ, DELIBERADAMENTE
-- Mesma lógica da nota que já existe em `02_tenancy_rls`: quem cuida de saúde
-- não precisa de conta bancária, e o inverso também vale. `owner`, `personnel` e
-- `accounting` são quem monta e confere a remessa.
--
-- ⚠️ O NÚMERO DA CONTA NÃO TEM MÁSCARA AQUI, E NÃO É PARA TER
-- A máscara é da resposta HTTP (`operax/dp/banking.py`), não da coluna: o
-- arquivo de remessa precisa do número inteiro. A regra 10 do `PRD-DP.md` diz
-- que ele nunca chega ao navegador — quem faz isso valer é o serializer, e é lá
-- que ele é testado.
--
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

create table if not exists app.employee_bank_account (
  employee_id  uuid primary key references app.employee(id) on delete cascade,
  tenant_id    uuid not null references app.tenant(id) on delete cascade,
  bank_code    text not null,
  branch       text not null,
  account      text not null,
  account_type text not null default 'checking'
    check (account_type in ('checking','savings','salary','payment')),
  --: Quando a conta não é do próprio colaborador. Documento de terceiro, sob o
  --: mesmo domínio: nunca em view de `public`, nunca em template que não seja
  --: do domínio.
  holder_document text,
  updated_at   timestamptz not null default now()
);

create index if not exists employee_bank_account_tenant_idx
  on app.employee_bank_account (tenant_id);

comment on table app.employee_bank_account is
  'Conta bancária do colaborador — insumo do arquivo de remessa do vale transporte. '
  'Domínio sensível `banking`, sem grant para `authenticated`: só Caminho 2. O número '
  'completo nunca chega ao navegador (regra 10 do PRD-DP); a tela vê máscara.';
comment on column app.employee_bank_account.account is
  'Número completo. Só o montador da remessa o devolve, e em bytes — nunca em JSON.';
comment on column app.employee_bank_account.holder_document is
  'CPF/CNPJ do titular quando a conta não é do colaborador. Documento de terceiro.';

-- ---------------------------------------------------------------------------
-- Fronteira
-- ---------------------------------------------------------------------------
alter table app.employee_bank_account enable row level security;

revoke all on table app.employee_bank_account from anon, authenticated;
-- ⛔ `select, insert, update` — e NÃO `grant all`, que é a convenção das outras
--    migrations. A exceção é deliberada e tem precedente: a `36_employee_photo`
--    desviou dela pelo mesmo motivo. `all` inclui `delete` e `truncate`, e esta
--    etapa declarou delete físico fora de escopo. Conceder o verbo e depois
--    afirmar que ninguém apaga seria a promessa sem a trava.
grant select, insert, update on table app.employee_bank_account to service_role;

drop policy if exists employee_bank_account_read on app.employee_bank_account;
create policy employee_bank_account_read on app.employee_bank_account
  for select to authenticated
  using (
    util.can_see_domain(tenant_id, 'banking')
    and util.can_see_employee(employee_id)
  );

drop policy if exists employee_bank_account_write on app.employee_bank_account;
create policy employee_bank_account_write on app.employee_bank_account
  for all to authenticated
  using (
    util.can_see_domain(tenant_id, 'banking')
    and util.can_see_employee(employee_id)
    and util.is_admin(tenant_id)
  )
  with check (
    util.can_see_domain(tenant_id, 'banking')
    and util.can_see_employee(employee_id)
    and util.is_admin(tenant_id)
  );

-- ---------------------------------------------------------------------------
-- Semente da matriz
-- ---------------------------------------------------------------------------
-- `do nothing` e não `do update`: o cliente muda a matriz por UPDATE, como a
-- migration 02 previu, e uma migration idempotente que sobrescreve a decisão do
-- cliente a cada `db reset` não é idempotente — é regressiva.
insert into app.domain_permission (tenant_id, role, domain, allowed)
select t.id, r.role, 'banking'::app.sensitive_domain,
       r.role in ('owner','personnel','accounting')
from app.tenant t
cross join (select unnest(enum_range(null::app.user_role)) as role) r
on conflict (tenant_id, role, domain) do nothing;

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v_policies   int;
  v_tenants    int;
  v_allowed    int;
  v_privilege  text;
  v_read_qual  text;
  v_write_qual text;
  v_write_chk  text;
begin
  -- 0. O pré-requisito, nomeado. Sem ele o cast da semente já teria estourado,
  --    mas com uma mensagem que não diz qual migration falta.
  if not exists (
    select 1 from pg_enum e
      join pg_type t      on t.oid = e.enumtypid
      join pg_namespace n  on n.oid = t.typnamespace
     where n.nspname = 'app' and t.typname = 'sensitive_domain'
       and e.enumlabel::text = 'banking'
  ) then
    raise exception 'app.sensitive_domain não tem banking — dp_banking_domain não foi aplicada';
  end if;

  if to_regclass('app.employee_bank_account') is null then
    raise exception 'app.employee_bank_account não existe depois de ser criada';
  end if;

  -- 1. Regra 3 do CLAUDE.md: tenant_id e RLS, as duas coisas.
  if not exists (
    select 1 from information_schema.columns
     where table_schema = 'app' and table_name = 'employee_bank_account'
       and column_name = 'tenant_id'
  ) then
    raise exception 'app.employee_bank_account sem tenant_id — regra 3 do CLAUDE.md';
  end if;
  if not (select relrowsecurity from pg_class where oid = 'app.employee_bank_account'::regclass) then
    raise exception 'app.employee_bank_account sem RLS — regra 3 do CLAUDE.md';
  end if;

  -- 2. Fora do PostgREST, em todos os verbos. Perguntar só por `select` deixaria
  --    um `grant insert` passar, e escrever conta alheia é pior que lê-la.
  foreach v_privilege in array array['SELECT','INSERT','UPDATE','DELETE'] loop
    if has_table_privilege('authenticated', 'app.employee_bank_account', v_privilege) then
      raise exception 'authenticated tem % em app.employee_bank_account — o desenho é só Caminho 2',
        v_privilege;
    end if;
    if has_table_privilege('anon', 'app.employee_bank_account', v_privilege) then
      raise exception 'anon tem % em app.employee_bank_account', v_privilege;
    end if;
  end loop;

  -- 3. O positivo. Sem ele o item 2 fica verde numa tabela que ninguém alcança —
  --    o falso verde que este projeto já pagou caro. São os três verbos do
  --    Caminho 2: ler a conta, gravá-la e corrigi-la.
  foreach v_privilege in array array['SELECT','INSERT','UPDATE'] loop
    if not has_table_privilege('service_role', 'app.employee_bank_account', v_privilege) then
      raise exception 'service_role não tem % em app.employee_bank_account — o Caminho 2 não funcionaria',
        v_privilege;
    end if;
  end loop;

  -- 3-bis. E o negativo do grant, feito ao papel que TERIA como apagar. Perguntar
  --    só a `authenticated`, que acabou de levar `revoke all`, é o conjunto
  --    só-negativo em forma pura: passa porque nada foi concedido, e o único que
  --    de fato apagaria não é interrogado. Delete físico está fora desta etapa.
  foreach v_privilege in array array['DELETE','TRUNCATE'] loop
    if has_table_privilege('service_role', 'app.employee_bank_account', v_privilege) then
      raise exception 'service_role tem % em app.employee_bank_account; esta etapa não apaga conta, e `grant all` foi trocado por isso',
        v_privilege;
    end if;
  end loop;

  -- 4. Duas policies, e as duas com os DOIS eixos. Conferir a contagem sem
  --    conferir o texto deixaria passar uma policy que esqueceu `can_see_employee`.
  select count(*) into v_policies from pg_policies
   where schemaname = 'app' and tablename = 'employee_bank_account';
  if v_policies <> 2 then
    raise exception 'app.employee_bank_account tem % policies, esperava 2 (read e write)', v_policies;
  end if;
  if exists (
    select 1 from pg_policies
     where schemaname = 'app' and tablename = 'employee_bank_account'
       and (coalesce(qual, '') not like '%can_see_domain%'
         or coalesce(qual, '') not like '%can_see_employee%')
  ) then
    raise exception 'policy de app.employee_bank_account sem os dois eixos (domínio e colaborador)';
  end if;
  if exists (
    select 1 from pg_policies
     where schemaname = 'app' and tablename = 'employee_bank_account'
       and with_check is not null
       and (with_check not like '%can_see_domain%' or with_check not like '%can_see_employee%')
  ) then
    raise exception 'with check de app.employee_bank_account sem os dois eixos';
  end if;

  -- 4-bis. O TERCEIRO eixo, e ele é só da escrita. As duas expressões são
  --    conferidas em separado de propósito: quem decide um INSERT é o
  --    `with check`, e olhar só o `using` deixaria passar exatamente a metade
  --    que decide.
  select qual, with_check into v_write_qual, v_write_chk
    from pg_policies
   where schemaname = 'app' and tablename = 'employee_bank_account'
     and policyname = 'employee_bank_account_write';
  if coalesce(v_write_qual, '') not like '%is_admin%' then
    raise exception 'employee_bank_account_write sem util.is_admin no using — accounting gravaria conta bancária sem ser admin';
  end if;
  if coalesce(v_write_chk, '') not like '%is_admin%' then
    raise exception 'employee_bank_account_write sem util.is_admin no with check — é o with check que decide o INSERT';
  end if;

  -- 4-ter. E a de LEITURA continua com DOIS. Ganhar o terceiro eixo aqui não
  --    seria "mais seguro": trancaria `accounting`, que tem `banking` e não é
  --    admin, fora da conciliação da remessa que é o trabalho dele.
  select qual into v_read_qual
    from pg_policies
   where schemaname = 'app' and tablename = 'employee_bank_account'
     and policyname = 'employee_bank_account_read';
  if coalesce(v_read_qual, '') like '%is_admin%' then
    raise exception 'employee_bank_account_read ganhou util.is_admin; accounting deixaria de ler a conta que ele concilia';
  end if;

  -- 5. A matriz. Três papéis por tenant, e `hr` fora — que é a linha desta
  --    migration que uma revisão distraída inverteria sem nenhum teste reclamar.
  select count(*) into v_tenants from app.tenant;
  select count(*) into v_allowed from app.domain_permission
   where domain = 'banking' and allowed;

  if v_tenants > 0 and v_allowed <> 3 * v_tenants then
    raise exception 'matriz de banking: % concessões para % tenant(s), esperava %',
      v_allowed, v_tenants, 3 * v_tenants;
  end if;
  if exists (
    select 1 from app.domain_permission
     where domain = 'banking' and allowed and role not in ('owner','personnel','accounting')
  ) then
    raise exception 'papel fora de owner/personnel/accounting alcança o domínio banking';
  end if;
  if exists (
    select 1 from app.domain_permission where domain = 'banking' and allowed and role = 'hr'
  ) then
    raise exception 'hr alcança conta bancária; quem cuida de saúde não precisa dela';
  end if;

  raise notice
    'OK: app.employee_bank_account fora do PostgREST, leitura com dois eixos e '
    'escrita com três (using e with check), % concessão(ões) de banking em % tenant(s).',
    v_allowed, v_tenants;
end $$;
