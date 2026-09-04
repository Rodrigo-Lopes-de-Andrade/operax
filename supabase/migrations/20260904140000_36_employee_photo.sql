-- ============================================================================
-- OperaX — 36. A FOTO IMPUTADA, QUE É DADO NOSSO E NÃO ESPELHO
-- ----------------------------------------------------------------------------
-- Decisão do dono em 04/09/2026: `docs/DECISAO-FOTO-DO-COLABORADOR.md` §4-ter.
-- O cliente precisa VER e INSERIR, e a posição contratual foi decidida como
-- "atender o cliente" — registrada na §4-bis como risco aceito por escrito, com
-- dono e data, que é o mecanismo que o próprio documento define.
--
-- ⛔ POR QUE NÃO ESCREVER EM `secullum."Funcionario"."Foto"`
-- O espelho é cópia literal da origem. Escrever nele seria a mesma classe de
-- erro que a outra equipe comete conosco — e, pior, seria apagado: a fila do
-- `sync-fotos` é `where "PossuiFoto"`, então no dia em que a origem passar a ter
-- a foto dessa pessoa o job sobrescreve o que o DP enviou. A tabela é nossa.
--
-- ⛔ SEM GRANT PARA `authenticated` — a diferença desta tabela para `employee_pii`
-- `employee_pii` concede a `authenticated` e deixa a RLS filtrar. Aqui não:
-- biometria não tem por que ser alcançável pelo PostgREST **de forma nenhuma**,
-- nem filtrada. Leitura e escrita só pelo Caminho 2, com o backend revalidando
-- papel e domínio. É o desenho que a §4-ter pede.
--
-- As policies existem mesmo assim, e não é redundância inútil: se alguém
-- conceder `select` a `authenticated` por engano num PR futuro, a policy é o que
-- ainda está lá. Defesa que só funciona quando a anterior falha é o ponto dela.
--
-- 📌 UMA LINHA ATIVA POR PESSOA, E NENHUMA APAGADA
-- A §4-ter diz que a foto enviada **nunca é apagada**. Então não há `delete`
-- concedido a ninguém, e substituir é carimbar `superseded_at` e inserir outra.
-- O índice único parcial garante que só uma esteja ativa por vez.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

create table if not exists app.employee_photo (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid        not null references app.tenant(id)   on delete cascade,
  employee_id    uuid        not null references app.employee(id) on delete cascade,

  --: Os bytes já decodificados, como no espelho. `bytea` e não bucket: bucket é
  --: mais uma superfície com política própria para acertar, e este produto já
  --: tem superfícies demais (§4-ter).
  content        bytea       not null,
  mime           text        not null,
  bytes          integer     not null,
  --: sha256 dos BYTES, nunca do base64 — o mesmo contrato que o espelho usa,
  --: para que as duas fotos sejam comparáveis sem decodificar.
  sha256         text        not null,

  uploaded_by    uuid        references auth.users(id),
  uploaded_at    timestamptz not null default now(),

  --: Quando a origem passou a ter foto desta pessoa. A partir daí a origem vence
  --: NA EXIBIÇÃO — mas a linha fica, porque a ficha precisa dizer "substituiu a
  --: foto enviada em DD/MM por [autor]". Substituição silenciosa é o erro que a
  --: revisão apontou.
  superseded_at  timestamptz,
  superseded_reason text,

  constraint employee_photo_mime_check
    check (mime in ('image/jpeg', 'image/png')),
  --: O comprimento declarado tem de ser o real. Sem isto, `bytes` vira um número
  --: que a tela mostra e ninguém confere — e foi exatamente a asserção que pegou
  --: zero divergências em 121 linhas do espelho.
  constraint employee_photo_bytes_check
    check (bytes = length(content) and bytes > 0 and bytes <= 5 * 1024 * 1024),
  constraint employee_photo_sha256_check
    check (sha256 ~ '^[0-9a-f]{64}$')
);

comment on table app.employee_photo is
  'Foto imputada pelo DP para quem a origem declara não ter (`"PossuiFoto" = false`). '
  'NÃO é espelho: dado nosso, criado aqui. Domínio sensível `pii`, sem grant para '
  '`authenticated` — só Caminho 2. Ver docs/DECISAO-FOTO-DO-COLABORADOR.md §4-ter.';

comment on column app.employee_photo.superseded_at is
  'Quando a origem passou a ter foto. A origem vence na exibição a partir daqui, e '
  'esta linha NUNCA é apagada: a ficha mostra que houve substituição, e de quando.';

-- Uma ativa por pessoa. Substituir é carimbar `superseded_at` e inserir outra.
create unique index if not exists employee_photo_ativa_key
  on app.employee_photo (tenant_id, employee_id)
  where superseded_at is null;

create index if not exists employee_photo_employee_idx
  on app.employee_photo (employee_id);

-- ---------------------------------------------------------------------------
-- Fronteira
-- ---------------------------------------------------------------------------
alter table app.employee_photo enable row level security;

revoke all on table app.employee_photo from anon, authenticated;
-- ⛔ `select, insert, update` — e NÃO `grant all`, que é a convenção das outras
--    12 migrations. A exceção é deliberada: `all` inclui `delete` e `truncate`, e
--    a §4-ter diz que a foto enviada NUNCA é apagada. Conceder e depois afirmar
--    que ninguém apaga seria a promessa sem a trava. O `update` basta para o
--    carimbo de substituição.
grant select, insert, update on table app.employee_photo to service_role;

drop policy if exists employee_photo_read on app.employee_photo;
create policy employee_photo_read on app.employee_photo
  for select to authenticated
  using (
    util.can_see_domain(tenant_id, 'pii')
    and util.can_see_employee(employee_id)
  );

drop policy if exists employee_photo_write on app.employee_photo;
create policy employee_photo_write on app.employee_photo
  for insert to authenticated
  with check (
    util.can_see_domain(tenant_id, 'pii')
    and util.is_admin(tenant_id)
    and util.can_see_employee(employee_id)
  );

drop policy if exists employee_photo_supersede on app.employee_photo;
create policy employee_photo_supersede on app.employee_photo
  for update to authenticated
  using (
    util.can_see_domain(tenant_id, 'pii')
    and util.is_admin(tenant_id)
    and util.can_see_employee(employee_id)
  );

-- ⛔ Não há policy de `delete`, e não há grant de `delete`. A ausência é a
--    decisão: a §4-ter diz que a foto enviada nunca é apagada, e a regra 6 deste
--    projeto já diz o mesmo sobre desvio. Um `grant all` futuro reintroduziria o
--    delete sem policy — que a RLS barraria, mas o certo é não conceder.

-- ---------------------------------------------------------------------------
-- Prova
-- ---------------------------------------------------------------------------
do $$
declare
  v_n int;
begin
  -- 1. A tabela não é alcançável pelo PostgREST — é o ponto do desenho.
  if has_table_privilege('authenticated', 'app.employee_photo', 'SELECT') then
    raise exception 'authenticated alcança app.employee_photo — o desenho é só Caminho 2';
  end if;
  if has_table_privilege('anon', 'app.employee_photo', 'SELECT') then
    raise exception 'anon alcança app.employee_photo';
  end if;

  -- 2. O backend alcança. Sem este positivo, o item 1 ficaria verde numa tabela
  --    que ninguém lê — o falso verde que este projeto já pagou caro.
  if not has_table_privilege('service_role', 'app.employee_photo', 'SELECT') then
    raise exception 'service_role não lê app.employee_photo — o Caminho 2 não funcionaria';
  end if;

  -- 3. RLS ligada, e as três policies no lugar.
  select count(*) into v_n from pg_policies
   where schemaname = 'app' and tablename = 'employee_photo';
  if v_n <> 3 then
    raise exception 'esperava 3 policies em app.employee_photo, encontrei %', v_n;
  end if;
  if not exists (
    select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'app' and c.relname = 'employee_photo' and c.relrowsecurity
  ) then
    raise exception 'RLS não está ligada em app.employee_photo';
  end if;

  -- 4. Ninguém apaga — e a pergunta é feita ao papel que TERIA como apagar.
  --    Perguntar só a `authenticated`, que acabou de levar `revoke all`, é o
  --    conjunto só-negativo em forma pura: passa porque nada foi concedido, e o
  --    único que de fato apagaria não é interrogado.
  if has_table_privilege('service_role', 'app.employee_photo', 'DELETE') then
    raise exception 'service_role apaga foto; a §4-ter diz que ela nunca é apagada';
  end if;
  if has_table_privilege('authenticated', 'app.employee_photo', 'DELETE') then
    raise exception 'authenticated apaga foto';
  end if;

  -- 5. O check de comprimento existe e diz o que deve dizer.
  --    ⚠️ Afirmado pelo CATÁLOGO, e não tentando violá-lo: o `insert ... select`
  --    que a primeira versão usava dependia de `app.tenant` e `app.employee`
  --    terem linha. Num banco sem semente ele grava ZERO linhas, nenhum check é
  --    violado, e a asserção acusava a constraint de ter falhado quando o que
  --    faltava era dado. Foi o `when others then null` que escondeu isso — e o
  --    gate de superfície mostrou que aquele handler tornava tudo aqui inerte.
  if not exists (
    select 1 from pg_constraint
     where conrelid = 'app.employee_photo'::regclass
       and conname  = 'employee_photo_bytes_check'
       and pg_get_constraintdef(oid) ilike '%length(content)%'
  ) then
    raise exception 'o check de bytes não confere o comprimento real do conteúdo';
  end if;

  if not exists (
    select 1 from pg_constraint
     where conrelid = 'app.employee_photo'::regclass
       and conname  = 'employee_photo_mime_check'
  ) then
    raise exception 'o check de mime não existe — a allowlist do banco sumiu';
  end if;

  raise notice 'OK: app.employee_photo fora do PostgREST, 3 policies, sem delete.';
end $$;
