-- ============================================================================
-- OperaX — dp_unit_compliance. LAUDO É DA UNIDADE, E RENOVAR É LINHA NOVA
-- ----------------------------------------------------------------------------
-- Desenho em `docs/SPEC-DP.md` §1f e `docs/ANEXO-COBERTURA-LEGADO-FASTPARK.md`
-- §4.8: PCMSO, PGR, LTCAT+LTIP por unidade, com vencimento, observação,
-- histórico e a ação **Renovar**. Não é RH de pessoa — é conformidade de local.
--
-- ⚠️ PRIMEIRA TABELA DA ETAPA DP CUJAS LINHAS CHEGAM AO NAVEGADOR
-- As demais tabelas do slot DP fazem `revoke all` de `authenticated` porque a
-- etapa inteira é Caminho 2. Esta concede **`select`** — e só `select` — porque
-- `public.vw_unit_compliance` existe e usa `security_invoker = on`: medido em
-- 07/09/2026, uma view invoker sobre tabela sem grant devolve `permission denied
-- for table`, não linha filtrada. Sem o grant, a view seria decoração.
-- Autorizado pelo dono em 07/09/2026, junto com a view.
--
-- ⚠️ E a precisão importa, porque o título acima é fácil de ler errado: a
-- TABELA continua inalcançável por PostgREST — `app` não está nos exposed
-- schemas, e o grant não muda isso. O que o navegador alcança é a VIEW, e o
-- grant existe para que ela execute em nome de quem perguntou. O que muda de
-- verdade é o peso da policy: `unit_compliance_report_read` deixa de ser defesa
-- em profundidade e passa a ser a fronteira que decide o que a tela vê. Escrita
-- continua fechada — `authenticated` não tem `insert`, `update` nem `delete`, e
-- o `do $$` no fim confere verbo por verbo.
--
-- ⛔ SEM `document_id`, E A AUSÊNCIA É A DECISÃO (dono, 07/09/2026)
-- A §1f propunha `document_id uuid references app.document(id)`. Medido:
-- `app.document.employee_id` é **`not null`** (migration 08). Laudo de unidade
-- não tem pessoa, então a coluna ou nasceria eternamente nula ou alguém
-- anexaria o PCMSO da unidade à ficha de um colaborador qualquer — e aí ele
-- entraria nos contadores `document_expired`/`document_expiring` de
-- `public.fn_dp_alerts` **como documento daquela pessoa**. Armazenamento de
-- documento por unidade é sprint própria, se for pedida.
--
-- ⛔ SITUAÇÃO É DERIVADA DE `valid_until`, NUNCA COLUNA
-- Coluna de status vence sozinha e ninguém percebe. A view devolve
-- `days_to_expiry` e **não** `situation`: `EM DIA`/`A VENCER`/`VENCIDO` exige
-- uma janela, e a única janela configurável do schema é
-- `app.document_type.expiry_alert_days`, que o `type` (texto livre) não alcança.
-- O S4 já recusou o atalho, com todas as letras: "uma janela padrão em constante
-- mentiria com cara de configuração". Quem classifica é a UI, com o limiar
-- declarado nela.
--
-- ============================================================================
-- ⛔ A TRAVA DE VIGÊNCIA ÚNICA — TRÊS CONSTRAINTS, E CADA UMA FOI MEDIDA
-- ----------------------------------------------------------------------------
-- O gate: "laudo renovado não deixa duas linhas vigentes para o mesmo (unidade,
-- tipo)". Vigente = a linha que ninguém substituiu — uma condição sobre OUTRAS
-- linhas, que predicado de índice parcial não enxerga. As formas, medidas em
-- 07/09/2026 num Postgres descartável:
--
--   | forma                                   | resultado                       |
--   |-----------------------------------------|---------------------------------|
--   | o índice único da §1f, palavra por       | criado; recusa o segundo        |
--   | palavra                                  | ORIGINAL; **aceita duas         |
--   |                                          | renovações do mesmo pai** -> 2  |
--   |                                          | linhas vigentes                 |
--   | predicado com subconsulta                | ERROR: cannot use subquery in   |
--   |                                          | index predicate                 |
--   | predicado citando outra linha por alias  | ERROR: missing FROM-clause      |
--   | predicado com função de lookup immutable | criado — e **barra a renovação  |
--   |                                          | legítima**, porque a entrada da |
--   |                                          | raiz não é reavaliada           |
--
-- A terceira é a armadilha que o S1 já tinha achado, aqui numa versão pior: lá
-- ela deixava passar o ilegítimo, aqui ela recusa o legítimo — e trava que barra
-- o legítimo é pior que a ausência dela.
--
-- O que funciona são três constraints juntas, medidas 15 de 15 (8 recusas
-- ilegítimas, 7 aceites legítimos, invariante = 1 vigente por trio):
--
--   (A) `single_root_idx`      — uma RAIZ por (tenant, unidade, tipo)
--   (B) `single_successor_idx` — cada laudo é substituído no MÁXIMO uma vez
--   (C) `replaces_same_scope`  — a renovação fica DENTRO do próprio trio
--
-- O argumento: com (C) toda linha do trio aponta para o mesmo trio; com (A) o
-- trio tem uma raiz só; com (B) cada linha tem um sucessor só. Cadeia única =>
-- uma ponta => uma vigente. O grafo é acíclico por construção — o pai já tem de
-- existir na hora do insert.
--
-- ⛔ MUTAÇÃO DA AUSÊNCIA, RODADA UMA A UMA: removendo (A), (B) ou (C), a mesma
-- sequência de ataque deixa **2 vigentes** no trio. As três carregam peso.
--
-- 📌 POR QUE ÍNDICE E NÃO GATILHO — e não é gosto. Medido com duas sessões
-- concorrentes renovando o mesmo laudo: na forma declarativa uma recebe `23505`
-- e sobra **1 vigente**; num gatilho que faz `exists` sem `pg_advisory_xact_lock`
-- as duas passam e sobram **2**. Aqui não há advisory lock a esquecer, nem
-- ordem de disparo.
--
-- ⚠️ O `and valid_until is not null` da §1f SAIU: a coluna é `not null` e o
-- conjunto nunca é falso. Predicado morto faz o índice parecer mais estreito do
-- que é, e o dia em que alguém tornar a coluna anulável vai achar que o índice
-- se adaptou.
--
-- CORRIGIR NÃO ENCRAVA, E ISSO TAMBÉM FOI MEDIDO
-- Trocar o `type` de um elo isolado é recusado (a cadeia se partiria), mas
-- trocar o da cadeia inteira num `update` só é aceito — o FK é conferido no fim
-- do statement. E apagar o tenant, com cadeia de dois laudos, funciona: o
-- `on delete cascade` não colide com o FK auto-referente.
--
-- ⛔ LAUDO NÃO SE APAGA — regra 6 do projeto. `grant` sem `delete`; laudo que
-- não vale mais é laudo renovado, e o anterior fica no histórico.
--
-- DOIS EIXOS, E O TERCEIRO NÃO É ENUNCIÁVEL
-- `employee_bank_account` carrega três (`can_see_domain` + `can_see_employee` +
-- `is_admin`) porque é dado sensível de pessoa. Laudo não tem domínio sensível
-- nem pessoa: exigir um domínio arbitrário seria cerimônia, e cerimônia se
-- satisfaz com tautologia. Sobram os dois eixos de `app.work_post` e
-- `app.unit_responsible` — unidade para ler, administração para escrever.
--
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

create table if not exists app.unit_compliance_report (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references app.tenant(id) on delete cascade,
  unit_id     uuid not null references app.unit(id),
  --: "PCMSO", "PGR", "LTCAT+LTIP" — a lista é do cliente e muda sem deploy, então
  --: texto e não enum. Canonicalizado em `upper(btrim(...))` pelo mesmo motivo de
  --: `app.leave_justification_map`: o tipo é METADE da identidade do laudo, e
  --: 'PCMSO' com 'pcmso' seriam duas cadeias vigentes para o que o gestor lê como
  --: um laudo só. Acento não é normalizado — normalizá-lo seria adivinhar.
  type        text not null,
  valid_until date not null,
  notes       text,
  --: A renovação aponta para a linha que ela substitui. Sem FK simples para
  --: `(id)`: o FK composto abaixo já a contém e ainda prende o trio.
  replaces_id uuid,
  created_by  uuid references auth.users(id),
  created_at  timestamptz not null default now(),
  constraint unit_compliance_report_type_canonical
    check (type = upper(btrim(type))),
  constraint unit_compliance_report_type_nao_vazio
    check (btrim(type) <> ''),
  --: (C-alvo) existe para o FK composto ter onde se apoiar. `id` já é PK; o que
  --: esta unique acrescenta é poder comparar as quatro colunas de uma vez.
  constraint unit_compliance_report_scope_key
    unique (id, tenant_id, unit_id, type),
  --: (C) a renovação não atravessa tenant, unidade nem tipo. Sem ela, um laudo
  --: de PGR podendo substituir um de PCMSO deixa o trio de origem sem vigente e
  --: o de destino com dois.
  constraint unit_compliance_report_replaces_same_scope
    foreign key (replaces_id, tenant_id, unit_id, type)
    references app.unit_compliance_report (id, tenant_id, unit_id, type)
);

-- (A) uma raiz por trio. É o índice da §1f, sem o conjunto morto.
create unique index if not exists unit_compliance_report_single_root_idx
  on app.unit_compliance_report (tenant_id, unit_id, type)
  where replaces_id is null;

-- (B) um sucessor por laudo. É o que a §1f não tinha, e é onde a dupla vigência
--     nascia: duas renovações do mesmo pai são duas pontas.
create unique index if not exists unit_compliance_report_single_successor_idx
  on app.unit_compliance_report (replaces_id)
  where replaces_id is not null;

create index if not exists unit_compliance_report_unit_idx
  on app.unit_compliance_report (tenant_id, unit_id);

comment on table app.unit_compliance_report is
  'Laudos por unidade (PCMSO, PGR, LTCAT+LTIP). Renovar é INSERIR apontando replaces_id para a '
  'vigente — nunca update na linha vigente, nunca delete. Vigente = a linha que ninguém '
  'substituiu; a garantia é o trio de constraints single_root + single_successor + '
  'replaces_same_scope. Situação é derivada de valid_until, jamais coluna.';
comment on column app.unit_compliance_report.type is
  'Tipo do laudo, canonicalizado em upper(btrim(...)). Metade da identidade do laudo: '
  'PCMSO e pcmso seriam duas cadeias vigentes para o que a tela mostra como uma.';
comment on column app.unit_compliance_report.replaces_id is
  'A linha que esta renovação substitui. Preso ao mesmo (tenant, unidade, tipo) por FK composto.';
comment on column app.unit_compliance_report.valid_until is
  'Único insumo da situação. EM DIA / A VENCER / VENCIDO se derivam daqui, na leitura.';

-- ---------------------------------------------------------------------------
-- Fronteira
-- ---------------------------------------------------------------------------
alter table app.unit_compliance_report enable row level security;

revoke all on table app.unit_compliance_report from anon, authenticated;
-- ⚠️ `select` e SÓ `select` para o navegador: é o mínimo que a view invoker
-- exige. Escrita segue pelo Caminho 2, revalidada na rota.
grant select on table app.unit_compliance_report to authenticated;
-- Sem `delete`: laudo que não vale mais é laudo renovado (regra 6). Conceder o
-- verbo e depois prometer que ninguém apaga seria a promessa sem a trava.
grant select, insert, update on table app.unit_compliance_report to service_role;

drop policy if exists unit_compliance_report_read on app.unit_compliance_report;
create policy unit_compliance_report_read on app.unit_compliance_report
  for select to authenticated
  using (util.can_see_unit(unit_id));

drop policy if exists unit_compliance_report_admin on app.unit_compliance_report;
create policy unit_compliance_report_admin on app.unit_compliance_report
  for all to authenticated
  using (util.is_admin(tenant_id))
  with check (util.is_admin(tenant_id));

-- ---------------------------------------------------------------------------
-- A superfície pública — Caminho 1, autorizada pelo dono em 07/09/2026
-- ---------------------------------------------------------------------------
-- Laudo é documento da UNIDADE: não há pessoa, não há valor e não há domínio
-- sensível, que é o que separa esta view das nove do painel de DP que não
-- existem. A tela de Unidades e o link filtrado leem daqui; a rota `/dp/laudos`
-- serve o retorno de `POST`/`renovar` e o `can_write`.
--
-- ⚠️ SÓ AS VIGENTES. O histórico não sai por aqui: quem quer a cadeia pede à
-- rota. E o `not exists` é seguro sob RLS por causa do FK (C) — o sucessor tem
-- obrigatoriamente o MESMO `unit_id`, então ele nunca fica invisível para quem
-- enxerga o substituído. Sem (C), uma renovação em unidade que o usuário não vê
-- faria a linha substituída reaparecer como vigente.
create or replace view public.vw_unit_compliance
with (security_invoker = on) as
select r.id                            as report_id,
       r.tenant_id,
       r.unit_id,
       u.name                          as unit_name,
       r.type,
       r.valid_until,
       --: Negativo = vencido há N dias. A UI classifica; a view não inventa janela.
       (r.valid_until - current_date)   as days_to_expiry,
       --: Quantas vezes este laudo já foi renovado — o "contador de histórico" do
       --: legado. A cadeia inteira do trio menos a própria linha original.
       ((select count(*)
           from app.unit_compliance_report h
          where h.tenant_id = r.tenant_id
            and h.unit_id   = r.unit_id
            and h.type      = r.type) - 1)::int as renewal_count,
       r.notes,
       r.created_at
from app.unit_compliance_report r
join app.unit u on u.id = r.unit_id
where not exists (
        select 1 from app.unit_compliance_report s where s.replaces_id = r.id
      );

comment on view public.vw_unit_compliance is
  'Laudos VIGENTES por unidade (Caminho 1). Sem coluna de situação: days_to_expiry é o insumo '
  'e a janela mora na UI — janela em constante no SQL mentiria com cara de configuração.';

revoke all on public.vw_unit_compliance from anon, public;
grant select on public.vw_unit_compliance to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v_privilege text;
  v_policies  int;
  v_qual      text;
  v_check     text;
  v_cols      text[];
  v_tenant    uuid := '0d000000-0000-4000-8000-00000000dead';
  v_company   uuid := '0d000000-0000-4000-8000-00000000c0de';
  v_unit_a    uuid := '0d000000-0000-4000-8000-00000000a11a';
  v_unit_b    uuid := '0d000000-0000-4000-8000-00000000b11b';
  v_raiz      uuid;
  v_ponta     uuid;
  v_recusou   boolean;
  v_vigentes  int;
  v_linha     record;
begin
  if to_regclass('app.unit_compliance_report') is null then
    raise exception 'app.unit_compliance_report não existe depois de ser criada';
  end if;

  -- 1. Regra 3 do CLAUDE.md: tenant_id e RLS, as duas coisas.
  if not exists (
    select 1 from information_schema.columns
     where table_schema = 'app' and table_name = 'unit_compliance_report'
       and column_name = 'tenant_id'
  ) then
    raise exception 'app.unit_compliance_report sem tenant_id — regra 3 do CLAUDE.md';
  end if;
  if not (select relrowsecurity from pg_class
           where oid = 'app.unit_compliance_report'::regclass) then
    raise exception 'app.unit_compliance_report sem RLS — regra 3 do CLAUDE.md';
  end if;

  -- 2. (A) e (B): as duas travas de índice, com o conjunto de colunas comparado
  --    INTEIRO e o predicado conferido. Um índice em (tenant_id, unit_id, type)
  --    sem o `where` proibiria a renovação; um em (tenant_id, type) atravessaria
  --    unidade. Contar índices não pega nem um nem outro.
  select array_agg(a.attname::text order by a.attname), pg_get_expr(i.indpred, i.indrelid)
    into v_cols, v_check
    from pg_index i
    join pg_class c on c.oid = i.indexrelid
    join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)
   where i.indrelid = 'app.unit_compliance_report'::regclass
     and c.relname = 'unit_compliance_report_single_root_idx'
   group by i.indpred, i.indrelid;
  if v_cols is distinct from array['tenant_id','type','unit_id'] then
    raise exception '(A) single_root_idx indexa %, esperava (tenant_id, unit_id, type)', v_cols;
  end if;
  if coalesce(v_check, '') not like '%replaces_id IS NULL%' then
    raise exception '(A) single_root_idx sem o predicado `replaces_id is null`: % — sem ele a renovação legítima seria recusada', v_check;
  end if;
  if not (select indisunique from pg_index i join pg_class c on c.oid = i.indexrelid
           where c.relname = 'unit_compliance_report_single_root_idx') then
    raise exception '(A) single_root_idx não é único — deixaria dois originais no mesmo trio';
  end if;

  select array_agg(a.attname::text order by a.attname), pg_get_expr(i.indpred, i.indrelid)
    into v_cols, v_check
    from pg_index i
    join pg_class c on c.oid = i.indexrelid
    join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)
   where i.indrelid = 'app.unit_compliance_report'::regclass
     and c.relname = 'unit_compliance_report_single_successor_idx'
   group by i.indpred, i.indrelid;
  if v_cols is distinct from array['replaces_id'] then
    raise exception '(B) single_successor_idx indexa %, esperava (replaces_id)', v_cols;
  end if;
  if not (select indisunique from pg_index i join pg_class c on c.oid = i.indexrelid
           where c.relname = 'unit_compliance_report_single_successor_idx') then
    raise exception '(B) single_successor_idx não é único — duas renovações do mesmo pai são duas vigentes';
  end if;

  -- 3. (C): o FK composto, com as quatro colunas e o alvo na própria tabela. Um
  --    FK só em `(replaces_id)` deixaria a renovação atravessar tipo e unidade.
  select array_agg(a.attname::text order by a.attname) into v_cols
    from pg_constraint c
    join unnest(c.conkey) k on true
    join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k
   where c.conrelid = 'app.unit_compliance_report'::regclass
     and c.contype = 'f'
     and c.conname = 'unit_compliance_report_replaces_same_scope'
   group by c.oid;
  if v_cols is distinct from array['replaces_id','tenant_id','type','unit_id'] then
    raise exception '(C) replaces_same_scope prende %, esperava (replaces_id, tenant_id, unit_id, type)', v_cols;
  end if;
  if not exists (
    select 1 from pg_constraint c
     where c.conname = 'unit_compliance_report_replaces_same_scope'
       and c.confrelid = 'app.unit_compliance_report'::regclass
  ) then
    raise exception '(C) replaces_same_scope não referencia a própria tabela';
  end if;

  -- 4. A porta do navegador: `select` e NADA além dele.
  if not has_table_privilege('authenticated', 'app.unit_compliance_report', 'SELECT') then
    raise exception 'authenticated não LÊ app.unit_compliance_report — public.vw_unit_compliance devolveria permission denied';
  end if;
  foreach v_privilege in array array['INSERT','UPDATE','DELETE'] loop
    if has_table_privilege('authenticated', 'app.unit_compliance_report', v_privilege) then
      raise exception 'authenticated tem % em app.unit_compliance_report — a escrita é Caminho 2', v_privilege;
    end if;
  end loop;
  foreach v_privilege in array array['SELECT','INSERT','UPDATE','DELETE'] loop
    if has_table_privilege('anon', 'app.unit_compliance_report', v_privilege) then
      raise exception 'anon tem % em app.unit_compliance_report', v_privilege;
    end if;
  end loop;

  -- 5. O positivo do backend, e o verbo que ele NÃO pode ter.
  foreach v_privilege in array array['SELECT','INSERT','UPDATE'] loop
    if not has_table_privilege('service_role', 'app.unit_compliance_report', v_privilege) then
      raise exception 'service_role não tem % em app.unit_compliance_report — o Caminho 2 não funcionaria', v_privilege;
    end if;
  end loop;
  foreach v_privilege in array array['DELETE','TRUNCATE'] loop
    if has_table_privilege('service_role', 'app.unit_compliance_report', v_privilege) then
      raise exception 'service_role tem % em app.unit_compliance_report; laudo não se apaga, renova-se', v_privilege;
    end if;
  end loop;

  -- 6. Duas policies, e o texto de cada uma. Contar sem ler deixaria passar uma
  --    leitura que trocou `can_see_unit` por `has_tenant` — e agora que o
  --    navegador alcança a tabela, isso daria o laudo de toda unidade ao
  --    supervisor de uma.
  select count(*) into v_policies from pg_policies
   where schemaname = 'app' and tablename = 'unit_compliance_report';
  if v_policies <> 2 then
    raise exception 'app.unit_compliance_report tem % policies, esperava 2 (read e admin)', v_policies;
  end if;
  select qual into v_qual from pg_policies
   where schemaname = 'app' and tablename = 'unit_compliance_report'
     and policyname = 'unit_compliance_report_read';
  if coalesce(v_qual, '') not like '%can_see_unit%' then
    raise exception 'unit_compliance_report_read sem util.can_see_unit — o laudo de toda unidade vazaria para o supervisor de uma';
  end if;
  select qual into v_qual from pg_policies
   where schemaname = 'app' and tablename = 'unit_compliance_report'
     and policyname = 'unit_compliance_report_admin';
  if coalesce(v_qual, '') not like '%is_admin%' then
    raise exception 'unit_compliance_report_admin sem util.is_admin no using';
  end if;
  select with_check into v_qual from pg_policies
   where schemaname = 'app' and tablename = 'unit_compliance_report'
     and policyname = 'unit_compliance_report_admin';
  if coalesce(v_qual, '') not like '%is_admin%' then
    raise exception 'unit_compliance_report_admin sem util.is_admin no with check — é ele que decide o INSERT';
  end if;

  -- 7. A view: existe, é invoker e não é alcançável por anon. Uma view em
  --    `public` sem `security_invoker` ignora a RLS da base — regra 2.
  if to_regclass('public.vw_unit_compliance') is null then
    raise exception 'public.vw_unit_compliance não existe depois de ser criada';
  end if;
  if not exists (
    select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and c.relname = 'vw_unit_compliance'
       and array_to_string(c.reloptions, ',') like '%security_invoker=on%'
  ) then
    raise exception 'public.vw_unit_compliance sem security_invoker = on — ela ignoraria a RLS de app.unit_compliance_report';
  end if;
  if has_table_privilege('anon', 'public.vw_unit_compliance', 'SELECT') then
    raise exception 'anon alcança public.vw_unit_compliance';
  end if;
  if not has_table_privilege('authenticated', 'public.vw_unit_compliance', 'SELECT') then
    raise exception 'authenticated não alcança public.vw_unit_compliance — o Caminho 1 não existiria';
  end if;

  -- =========================================================================
  -- 8. A PROVA VIVA. A estrutura acima diz que as travas existem; esta diz que
  --    elas recusam o ilegítimo E aceitam o legítimo.
  --    ⚠️ O cenário é CRIADO aqui e apagado no fim. Depender de tenant que já
  --    exista faria a prova pular calada no único ambiente que a executa — foi
  --    exatamente assim que o quarto falso verde do S1 sobreviveu.
  -- =========================================================================
  delete from app.tenant where id = v_tenant;
  insert into app.tenant (id, slug, name) values (v_tenant, 'prova-dp-laudos', 'Prova');
  insert into app.company (id, tenant_id, legal_name) values (v_company, v_tenant, 'Prova SA');
  insert into app.unit (id, tenant_id, company_id, code, name)
       values (v_unit_a, v_tenant, v_company, 'A', 'Unidade A'),
              (v_unit_b, v_tenant, v_company, 'B', 'Unidade B');

  -- 8.1 o original entra
  insert into app.unit_compliance_report (tenant_id, unit_id, type, valid_until)
       values (v_tenant, v_unit_a, 'PCMSO', date '2026-12-31')
    returning id into v_raiz;

  -- 8.2 o tipo não canônico é recusado, e o canônico entra (os dois lados)
  v_recusou := false;
  begin
    insert into app.unit_compliance_report (tenant_id, unit_id, type, valid_until)
         values (v_tenant, v_unit_b, 'pcmso', date '2026-12-31');
  exception when check_violation then v_recusou := true;
  end;
  if not v_recusou then
    raise exception 'o tipo não canônico entrou: PCMSO e pcmso seriam duas cadeias vigentes para o mesmo laudo';
  end if;
  insert into app.unit_compliance_report (tenant_id, unit_id, type, valid_until)
       values (v_tenant, v_unit_b, 'PCMSO', date '2026-12-31');

  -- 8.3 (A) o segundo ORIGINAL do mesmo trio é recusado
  v_recusou := false;
  begin
    insert into app.unit_compliance_report (tenant_id, unit_id, type, valid_until)
         values (v_tenant, v_unit_a, 'PCMSO', date '2027-01-31');
  exception when unique_violation then v_recusou := true;
  end;
  if not v_recusou then
    raise exception '(A) dois laudos originais no mesmo (unidade, tipo) — o trio nasce com duas vigentes';
  end if;

  -- 8.4 a RENOVAÇÃO LEGÍTIMA entra. É a operação inteira desta sprint: se ela
  --     for recusada, a trava barra o legítimo, que é pior que não existir.
  insert into app.unit_compliance_report (tenant_id, unit_id, type, valid_until, replaces_id)
       values (v_tenant, v_unit_a, 'PCMSO', date '2027-12-31', v_raiz)
    returning id into v_ponta;

  -- 8.5 (B) a SEGUNDA renovação do mesmo pai é recusada
  v_recusou := false;
  begin
    insert into app.unit_compliance_report (tenant_id, unit_id, type, valid_until, replaces_id)
         values (v_tenant, v_unit_a, 'PCMSO', date '2028-12-31', v_raiz);
  exception when unique_violation then v_recusou := true;
  end;
  if not v_recusou then
    raise exception '(B) o mesmo laudo foi renovado duas vezes — as duas renovações ficam vigentes';
  end if;

  -- 8.6 a renovação da PONTA continua a cadeia (o legítimo, de novo). A ponta
  --     passa a ser esta linha, e é ela que os ataques de (C) usam como pai.
  insert into app.unit_compliance_report (tenant_id, unit_id, type, valid_until, replaces_id)
       values (v_tenant, v_unit_a, 'PCMSO', date '2029-12-31', v_ponta)
    returning id into v_ponta;

  -- 8.7 (C) renovar atravessando TIPO e atravessando UNIDADE é recusado.
  --     ⚠️ O pai escolhido é a ponta SEM sucessor de propósito: assim (B) não
  --     tem o que dizer e a única trava que pode recusar é (C). E o handler é
  --     preso a `foreign_key_violation` — se quem recusasse fosse (B), o
  --     `unique_violation` sairia sem ser capturado e a migration falharia alto,
  --     em vez de creditar a (C) uma recusa que não é dela.
  v_recusou := false;
  begin
    insert into app.unit_compliance_report (tenant_id, unit_id, type, valid_until, replaces_id)
         values (v_tenant, v_unit_a, 'PGR', date '2027-06-30', v_ponta);
  exception when foreign_key_violation then v_recusou := true;
  end;
  if not v_recusou then
    raise exception '(C) uma renovação de PGR substituiu um laudo de PCMSO — o trio de origem fica sem vigente e o de destino com duas';
  end if;
  v_recusou := false;
  begin
    insert into app.unit_compliance_report (tenant_id, unit_id, type, valid_until, replaces_id)
         values (v_tenant, v_unit_b, 'PCMSO', date '2027-06-30', v_ponta);
  exception when foreign_key_violation then v_recusou := true;
  end;
  if not v_recusou then
    raise exception '(C) uma renovação da unidade B substituiu um laudo da unidade A';
  end if;

  -- 8.8 O INVARIANTE do gate, medido no estado que sobrou.
  select coalesce(max(c), 0) into v_vigentes from (
    select count(*) as c
      from app.unit_compliance_report x
     where x.tenant_id = v_tenant
       and not exists (select 1 from app.unit_compliance_report y where y.replaces_id = x.id)
     group by x.tenant_id, x.unit_id, x.type) s;
  if v_vigentes <> 1 then
    raise exception 'o trio ficou com % linha(s) vigente(s) — o gate do S5 é exatamente uma', v_vigentes;
  end if;

  -- 8.9 A view devolve a PONTA da cadeia, não a raiz, e conta o histórico.
  --     ⛔ `is distinct from`, E NÃO `<>`, NAS TRÊS COMPARAÇÕES ABAIXO.
  --     `select ... into` sem `strict` deixa o record NULL quando a consulta não
  --     devolve linha, e `NULL <> valor` é NULL — que não é `true`, então o `if`
  --     não dispara e as três passam EM BRANCO. Medido em 08/09/2026: com a view
  --     mutada para `join app.unit u on ... and false` (zero linha), esta
  --     migration fechava VERDE. Nada mais aqui prova que a view devolve linha —
  --     o passo 7 confere existência, invoker e grant, e o 8.8 lê a TABELA.
  --     ⚠️ E o `strict` vai junto porque ele pega o outro lado, que a comparação
  --     não pega: uma view sem o `not exists` devolveria a cadeia inteira, e aí
  --     `into` sem `strict` guarda UMA linha qualquer — a asserção passaria a
  --     depender da ordem de leitura.
  select * into strict v_linha from public.vw_unit_compliance
   where tenant_id = v_tenant and unit_id = v_unit_a;
  if v_linha.valid_until is distinct from date '2029-12-31' then
    raise exception 'a view devolveu o laudo de % — ela mostra a linha substituída em vez da vigente', v_linha.valid_until;
  end if;
  if v_linha.renewal_count is distinct from 2 then
    raise exception 'a view contou % renovação(ões), esperava 2 — o contador de histórico da tela', v_linha.renewal_count;
  end if;
  if v_linha.days_to_expiry is distinct from (date '2029-12-31' - current_date) then
    raise exception 'days_to_expiry não é derivado de valid_until';
  end if;

  delete from app.tenant where id = v_tenant;

  raise notice
    'OK: app.unit_compliance_report com vigência única provada (raiz, sucessor e escopo), '
    'fora da escrita do navegador, e public.vw_unit_compliance invoker devolvendo só a vigente.';
end $$;
