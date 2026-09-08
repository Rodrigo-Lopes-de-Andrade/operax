-- ============================================================================
-- OperaX — dp_payroll_code_map. A CURADORIA DE RUBRICA JÁ EXISTIA
-- ----------------------------------------------------------------------------
-- ⛔ NENHUMA TABELA NOVA. Decisão do dono, 07/09/2026.
-- `docs/SPEC-DP.md` §1i pedia `app.payroll_code_map` — "a curadoria que o P3 ia
-- construir". Ela **já foi construída**: `app.payroll_event_map` nasceu na
-- migration 30, em 28/08/2026, com a mesma chave `(tenant_id, code)`, a mesma
-- `category`, o mesmo `validated_by`/`validated_at`, e **está aplicada em
-- produção** — conferido na captura de `nklobmlxyidqxarzisph`. O `ANEXO` §4.5
-- ("falta só a tabela de mapeamento") ficou velho no dia seguinte ao que foi
-- escrito. Criar a segunda seria a curadoria escrita duas vezes, com a mesma
-- chave e dois vocabulários — o defeito que esta etapa já recusou três vezes.
--
-- Então esta migration é **aditiva**: as duas colunas que a §1i queria e que a
-- 30 não tem (`description` e `nature`), mais a semente e o que ela exige.
--
-- ⛔ SEM `validated boolean`. A §1i propunha um; a 30 tem `validated_at`. Dois
-- jeitos de dizer a mesma coisa divergem no primeiro `update` que atualiza um e
-- esquece o outro, e a metade que diverge é a que ninguém lê. "Validada" é
-- `validated_at is not null`, e ponto.
--
-- ⚠️ PRIMEIRA MIGRATION DESTA ETAPA A ALTERAR TABELA JÁ APLICADA EM PRODUÇÃO
-- As duas colunas são aditivas e **anuláveis** — linha existente continua legal
-- sem precisar de valor. O `do $$` no fim confere a anulabilidade das duas, e
-- não só a existência: uma coluna `not null` aqui recusaria toda linha que a
-- contabilidade já tivesse curado.
--
-- ⛔ `category` PASSA A SER ANULÁVEL, E É O QUE PERMITE A SEMENTE EXISTIR
-- A 30 a criou `not null`. A semente traz código do cliente que **ninguém
-- classificou ainda** — e semear `'other'` para todos seria o produto
-- decidindo, em migration, como o dinheiro é somado. A frase é da própria 30:
-- "palpite gravado não se distingue de fato lido". Pior: `'other'` é uma
-- categoria legítima, então a linha semeada ficaria indistinguível de uma
-- curada. A promessa de `not null` não some — ela fica **mais forte** e
-- condicional: `validated_at is null or category is not null`, ou seja,
-- validar EXIGE ter classificado. Não classificado passa a ser um estado
-- representável, que é o que ele é.
--
-- ⛔ A SEMENTE DA §1i ABORTA NA PRIMEIRA FOLHA REAL — MEDIDO EM 07/09/2026
-- `select distinct code, description, nature from app.payroll_entry` devolve
-- **mais de uma linha por código** assim que o mesmo código aparecer com duas
-- descrições ou duas naturezas — truncamento, rótulo trocado no meio do ano,
-- duas competências importadas. Medido: `duplicate key value violates unique
-- constraint`, e **zero linha entra**. É o mesmo padrão `Atested`/`ATEST M` que
-- o S3 encontrou noutra tabela. Hoje é inócuo porque a origem está vazia; seria
-- uma migration que não aplica no dia em que deixasse de estar.
-- O conserto: `distinct on (tenant_id, code)` com desempate **estável**
-- (`created_at desc, id`) — a descrição mais recente vence — e `tenant_id`, que o
-- `select` da SPEC não trazia e sem o qual não há o que inserir.
--
-- ⛔ E A IDEMPOTÊNCIA É `where not exists`, NÃO `on conflict do nothing` — A
--    ESCOLHA VEIO DE UMA MUTAÇÃO QUE SOBREVIVEU
-- A primeira versão desta semente usava `on conflict (tenant_id, code) do
-- nothing`. Medido em 07/09/2026: com ele, trocar `distinct on` pelo `distinct`
-- da SPEC **passa verde** — o conflito acontece dentro do próprio statement e é
-- engolido, e a descrição que fica passa a ser a que o planejador devolver
-- primeiro. O defeito deixa de ser um erro e vira uma escolha arbitrária, que é
-- pior: ninguém procura o que não reclamou.
-- Com o anti-join, o código já mapeado nem entra no `select` — reprocessar
-- continua não duplicando e não reescrevendo curadoria — e a duplicata de
-- dentro do statement volta a estourar `duplicate key`, alto, como deve.
--
-- ⛔ A SEMENTE NASCE VAZIA, E ISSO NÃO É DEFEITO DELA
-- `app.payroll_entry` tem **0 linhas** (medido em 07/09/2026 no banco de dev):
-- nenhuma folha foi importada ainda. A §1i promete que "a lista chega pronta
-- para a contabilidade conferir, não para levantar" — e ela chega pronta no dia
-- em que houver folha, com o mesmo `select`. Nenhum código de exemplo é semeado
-- para a lista não parecer vazia: seria inventar o plano de contas do cliente.
--
-- 📌 "LINHA NÃO VALIDADA NÃO ENTRA EM INDICADOR FINANCEIRO" — ONDE ISSO MORA
-- Não aqui. A leitura literal do gate não é enunciável hoje, e isso foi medido:
-- `public.vw_payroll_summary` soma `app.payroll_entry` **por `nature`**, sem
-- consultar mapa nenhum, e a folha base do painel de DP não vem de
-- `payroll_entry`. Nenhum indicador do repositório lê `category` de curadoria.
-- A regra mora em `backend/operax/dp/rubricas.py`: a função que entrega
-- categoria devolve **só linha validada**, e a não validada volta como pendência
-- **nomeada**, nunca como silêncio — a forma que o S3 deu à mesma regra em
-- `app.leave_justification_map`. Reenunciado pelo dono em 07/09/2026.
--
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

alter table app.payroll_event_map
  --: O que a folha do cliente chama a verba — "H.EXTRA 60%", "FERIAS GOZO". Vem
  --: de `app.payroll_entry.description`, e é o que a contabilidade reconhece na
  --: tela: quem confirma o mapeamento reconhece o nome, não o número.
  add column if not exists description text,
  --: `earning | deduction | base | payroll_charge | informational` — o "P / D / I"
  --: do legado, espelhado de `app.payroll_entry.nature`. NÃO é a classificação
  --: contábil: essa é a `category`, e é ela que a reunião preenche.
  add column if not exists nature text;

-- O vocabulário é o da origem, e o `do $$` compara os dois conjuntos: duas
-- listas escritas à mão em dois arquivos divergem na primeira mudança.
alter table app.payroll_event_map
  drop constraint if exists payroll_event_map_nature_check;
alter table app.payroll_event_map
  add constraint payroll_event_map_nature_check
  check (nature is null or nature in
         ('earning','deduction','base','payroll_charge','informational'));

-- A promessa de `not null` vira condicional, e mais forte: validar exige ter
-- classificado. Sem isto, `validated_at` marcaria como conferida uma linha sem
-- categoria — e a curadoria pareceria terminada com o trabalho por fazer.
alter table app.payroll_event_map
  alter column category drop not null;
alter table app.payroll_event_map
  drop constraint if exists payroll_event_map_validated_has_category;
alter table app.payroll_event_map
  add constraint payroll_event_map_validated_has_category
  check (validated_at is null or category is not null);

comment on column app.payroll_event_map.description is
  'A rubrica como a folha do cliente a escreve, semeada de app.payroll_entry.description. '
  'É o que a contabilidade reconhece na tela — quem confirma reconhece o nome, não o número.';
comment on column app.payroll_event_map.nature is
  'Espelha app.payroll_entry.nature (o P/D/I do legado). Não é a classificação contábil: '
  'essa é category, e linha sem validated_at não entra em indicador nenhum.';
comment on column app.payroll_event_map.category is
  'Nulo = código conhecido e AINDA NÃO classificado — o estado em que a semente entrega a '
  'lista. Validar exige classificar (payroll_event_map_validated_has_category).';


-- ---------------------------------------------------------------------------
-- A semente, e a prova viva dela
-- ---------------------------------------------------------------------------
-- ⚠️ O texto da semente vive numa variável e é executado nas DUAS pontas — a de
-- verdade e a da prova. Repeti-lo na prova seria provar uma CÓPIA da regra, e
-- uma cópia fica verde exatamente quando a original quebra.
do $$
declare
  v_semente constant text := $seed$
    insert into app.payroll_event_map (tenant_id, code, description, nature)
    select distinct on (e.tenant_id, e.code)
           e.tenant_id, e.code, e.description, e.nature
      from app.payroll_entry e
     where not exists (select 1 from app.payroll_event_map m
                        where m.tenant_id = e.tenant_id and m.code = e.code)
     order by e.tenant_id, e.code, e.created_at desc, e.id
  $seed$;
  v_tenant   uuid := '0d000000-0000-4000-8000-00000000ab12';
  v_company  uuid := '0d000000-0000-4000-8000-00000000ab13';
  v_period   uuid := '0d000000-0000-4000-8000-00000000ab14';
  --: O SEGUNDO tenant. Uma prova com um só não distingue o anti-join por
  --: (tenant, código) de um por código — ver o passo 4.
  v_tenant_b  uuid := '0d000000-0000-4000-8000-00000000ab16';
  v_company_b uuid := '0d000000-0000-4000-8000-00000000ab17';
  v_period_b  uuid := '0d000000-0000-4000-8000-00000000ab18';
  v_codigos  int;
  v_linhas   int;
  v_linha    record;
begin
  -- 1. A semente de verdade. Nasce vazia enquanto não houver folha importada —
  --    e o notice diz o número em vez de deixar o silêncio parecer sucesso.
  execute v_semente;
  select count(distinct (tenant_id, code)) into v_codigos from app.payroll_entry;
  raise notice 'semente: % código(s) distinto(s) em app.payroll_entry', v_codigos;

  -- =======================================================================
  -- 2. A PROVA VIVA. Cenário criado aqui e apagado no fim: depender de dado
  --    que já exista faria a prova pular calada no único ambiente que a roda.
  -- =======================================================================
  delete from app.tenant where id = v_tenant;
  insert into app.tenant (id, slug, name) values (v_tenant, 'prova-dp-rubricas', 'Prova');
  insert into app.company (id, tenant_id, legal_name) values (v_company, v_tenant, 'Prova SA');
  insert into app.payroll_period (id, tenant_id, year, month) values (v_period, v_tenant, 2026, 8);

  -- O MESMO código com DUAS descrições: é o que uma folha real tem, e é o que
  -- fazia a semente da §1i estourar `duplicate key` e não inserir nada.
  insert into app.payroll_entry
      (tenant_id, payroll_period_id, company_id, code, description, nature, amount, source, created_at)
  values
      (v_tenant, v_period, v_company, '0050', 'H EXTRA 60',  'earning', 10, 'spreadsheet', now() - interval '2 day'),
      (v_tenant, v_period, v_company, '0050', 'H.EXTRA 60%', 'earning', 20, 'spreadsheet', now() - interval '1 day'),
      (v_tenant, v_period, v_company, '0060', 'FERIAS GOZO', 'earning', 30, 'spreadsheet', now());

  execute v_semente;

  select count(*) into v_linhas from app.payroll_event_map where tenant_id = v_tenant;
  if v_linhas <> 2 then
    raise exception
      'a semente gravou % linha(s) para 2 códigos — o código com duas descrições ou duplicou ou derrubou a semente inteira',
      v_linhas;
  end if;

  -- ⛔ `is distinct from` NAS COMPARAÇÕES, E `into strict` NA LEITURA — as duas,
  --    porque elas pegam coisas diferentes e isso foi MEDIDO em 08/09/2026:
  --      · a semente sem `description` (ou sem `nature`) grava a linha com a
  --        COLUNA nula. `strict` acha a linha e não reclama; `NULL <> 'H.EXTRA
  --        60%'` é NULL, que não é `true`, e o `if` não dispara. As duas mutações
  --        fechavam VERDES com `<>` — só `is distinct from` as mata.
  --      · uma semente que não gravasse NADA deixaria o record inteiro NULL. Aí
  --        as duas formas pegam; `strict` pega mais cedo e nomeia a causa.
  select * into strict v_linha from app.payroll_event_map
   where tenant_id = v_tenant and code = '0050';
  if v_linha.description is distinct from 'H.EXTRA 60%' then
    raise exception
      'a semente escolheu a descrição "%" — o desempate tem de ser a linha mais recente, e estável',
      v_linha.description;
  end if;
  if v_linha.nature is distinct from 'earning' then
    raise exception 'a semente não trouxe a natureza da origem (veio "%")', v_linha.nature;
  end if;
  if v_linha.category is not null then
    raise exception
      'a semente classificou o código como "%" — classificar é da contabilidade, não da migration',
      v_linha.category;
  end if;
  if v_linha.validated_at is not null then
    raise exception 'a semente marcou como validada uma linha que ninguém conferiu';
  end if;

  -- 3. Reprocessar não duplica NEM reescreve o que já foi curado. É o anti-join
  --    do `where not exists`: sem ele, a segunda rodada estoura `duplicate key`
  --    — e é assim que ela falha ALTO em vez de devolver a linha curada ao
  --    estado de não classificada, calada.
  update app.payroll_event_map
     set category = 'overtime', validated_at = now()
   where tenant_id = v_tenant and code = '0050';

  execute v_semente;

  select count(*) into v_linhas from app.payroll_event_map where tenant_id = v_tenant;
  if v_linhas <> 2 then
    raise exception 'reprocessar a semente deixou % linha(s) — ela não é idempotente', v_linhas;
  end if;
  select * into strict v_linha from app.payroll_event_map
   where tenant_id = v_tenant and code = '0050';
  if v_linha.category is distinct from 'overtime' or v_linha.validated_at is null then
    raise exception 'a semente apagou a curadoria de quem já tinha classificado o código';
  end if;

  -- 4. ⛔ O ANTI-JOIN CASA POR (TENANT, CÓDIGO) — E COM UM TENANT SÓ ISSO NÃO SE
  --    PROVA. Medido em 07/09/2026: com `where m.code = e.code`, sem
  --    `m.tenant_id = e.tenant_id`, a prova acima fechava VERDE. Em produção
  --    multi-tenant esse é o pior sintoma possível — supressão cruzada e calada:
  --    o '0050' que o tenant A já curou impede a semente do '0050' do tenant B, e
  --    a lista de B nunca chega pronta. O passo 3 acabou de CURAR o '0050' de A,
  --    que é exatamente o estado em que a supressão morde.
  delete from app.tenant where id = v_tenant_b;
  insert into app.tenant (id, slug, name)
       values (v_tenant_b, 'prova-dp-rubricas-b', 'Prova B');
  insert into app.company (id, tenant_id, legal_name)
       values (v_company_b, v_tenant_b, 'Prova B SA');
  insert into app.payroll_period (id, tenant_id, year, month)
       values (v_period_b, v_tenant_b, 2026, 8);
  insert into app.payroll_entry
      (tenant_id, payroll_period_id, company_id, code, description, nature, amount, source, created_at)
  values
      (v_tenant_b, v_period_b, v_company_b, '0050', 'HORA EXTRA DO B', 'earning', 40, 'spreadsheet', now());

  execute v_semente;

  select count(*) into v_linhas from app.payroll_event_map where tenant_id = v_tenant_b;
  if v_linhas <> 1 then
    raise exception
      'o código 0050 do segundo tenant ficou com % linha(s) no mapa — o anti-join está casando só por código, e a curadoria de um cliente suprime a lista do outro',
      v_linhas;
  end if;
  select * into strict v_linha from app.payroll_event_map
   where tenant_id = v_tenant_b and code = '0050';
  if v_linha.description is distinct from 'HORA EXTRA DO B' then
    raise exception
      'a linha do segundo tenant veio com a descrição "%" — a semente atravessou tenant', v_linha.description;
  end if;
  if v_linha.category is not null then
    raise exception
      'o 0050 do tenant B nasceu classificado como "%" — a curadoria de A vazou para B', v_linha.category;
  end if;

  delete from app.tenant where id = v_tenant_b;
  delete from app.tenant where id = v_tenant;
  raise notice 'OK: a semente deduplica por (tenant, código), escolhe a linha mais recente, não reescreve curadoria e não atravessa tenant.';
end $$;

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v_policies  int;
  v_nullable  int;
  v_def       text;
  v_do_mapa   text[];
  v_da_folha  text[];
  v_tenant    uuid := '0d000000-0000-4000-8000-00000000ab15';
  v_recusou   boolean;
  v_faltando  int;
begin
  if to_regclass('app.payroll_event_map') is null then
    raise exception 'app.payroll_event_map não existe — a migration 30 não rodou antes desta';
  end if;

  -- 1. As duas colunas novas existem E são anuláveis. `not null` em qualquer
  --    uma recusaria toda linha que a contabilidade já tivesse curado em
  --    produção — e esta é a primeira migration da etapa a mexer em tabela com
  --    dado vivo.
  select count(*) into v_nullable from information_schema.columns
   where table_schema = 'app' and table_name = 'payroll_event_map'
     and column_name in ('description','nature');
  if v_nullable <> 2 then
    raise exception 'app.payroll_event_map não ganhou description e nature (achei % de 2)', v_nullable;
  end if;
  select count(*) into v_nullable from information_schema.columns
   where table_schema = 'app' and table_name = 'payroll_event_map'
     and column_name in ('description','nature','category') and is_nullable = 'NO';
  if v_nullable <> 0 then
    raise exception
      '% coluna(s) de payroll_event_map são not null — o desenho é aditivo, e category precisa representar "ainda não classificado"',
      v_nullable;
  end if;

  -- 2. ⛔ SEM `validated` booleano. Dois jeitos de dizer "validada" divergem no
  --    primeiro update que atualiza um e esquece o outro.
  if exists (
    select 1 from information_schema.columns
     where table_schema = 'app' and table_name = 'payroll_event_map' and column_name = 'validated'
  ) then
    raise exception 'apareceu uma coluna `validated` ao lado de `validated_at` — a verdade tem de ter um lugar só';
  end if;

  -- 3. ⛔ O VOCABULÁRIO DE `nature`, COMPARADO CONJUNTO A CONJUNTO COM A ORIGEM.
  --    `like` em cada valor pega o que falta e não o que sobra — o defeito das
  --    três ferramentas de guarda que a SPRINTS-DP.md já nomeou. Se as listas
  --    divergirem, a semente grava uma natureza que a origem não produz (ou
  --    recusa uma que ela produz), e o sintoma chega na primeira folha.
  select array_agg(v order by v) into v_do_mapa
    from (select unnest(regexp_split_to_array(
                   regexp_replace(pg_get_constraintdef(oid), '.*ARRAY\[(.*)\].*', '\1'), ',\s*')) as v
            from pg_constraint
           where conrelid = 'app.payroll_event_map'::regclass and contype = 'c'
             and conname = 'payroll_event_map_nature_check') s;
  select array_agg(v order by v) into v_da_folha
    from (select unnest(regexp_split_to_array(
                   regexp_replace(pg_get_constraintdef(oid), '.*ARRAY\[(.*)\].*', '\1'), ',\s*')) as v
            from pg_constraint
           where conrelid = 'app.payroll_entry'::regclass and contype = 'c'
             and pg_get_constraintdef(oid) like '%(nature = ANY%') s;
  if v_do_mapa is null or v_da_folha is null then
    raise exception 'não achei o check de nature em uma das duas tabelas (mapa: %, folha: %)',
      v_do_mapa, v_da_folha;
  end if;
  if v_do_mapa is distinct from v_da_folha then
    raise exception
      'o vocabulário de nature do mapa (%) não é o de app.payroll_entry (%)', v_do_mapa, v_da_folha;
  end if;

  -- 4. ⛔ SEM POLICY NOVA E SEM TABELA NOVA. A curadoria continua sendo a da 30.
  select count(*) into v_policies from pg_policies
   where schemaname = 'app' and tablename = 'payroll_event_map';
  if v_policies <> 1 then
    raise exception 'app.payroll_event_map tem % policies, esperava 1 (a admin da migration 30)', v_policies;
  end if;
  select qual into v_def from pg_policies
   where schemaname = 'app' and tablename = 'payroll_event_map'
     and policyname = 'payroll_event_map_admin';
  if coalesce(v_def, '') not like '%is_admin%' then
    raise exception 'payroll_event_map_admin sem util.is_admin no using';
  end if;
  if to_regclass('app.payroll_code_map') is not null then
    raise exception 'app.payroll_code_map existe — a curadoria de rubrica tem UM lugar, e ele é app.payroll_event_map';
  end if;

  -- 5. A semente não deixou código de fora. Com a origem vazia isto é vácuo, e
  --    o notice acima já disse o número; com folha importada, é a promessa da
  --    §1i ("a lista chega pronta") virando asserção.
  select count(*) into v_faltando from (
    select distinct e.tenant_id, e.code from app.payroll_entry e
     where not exists (select 1 from app.payroll_event_map m
                        where m.tenant_id = e.tenant_id and m.code = e.code)) s;
  if v_faltando <> 0 then
    raise exception '% código(s) da folha ficaram fora do mapa — a lista não chegou pronta', v_faltando;
  end if;

  -- 6. A PROVA VIVA da trava condicional: ela recusa validar sem classificar E
  --    deixa passar os dois casos legítimos. Só o negativo ficaria verde numa
  --    trava que recusasse tudo — e uma trava que barra o legítimo é pior que
  --    a ausência dela.
  delete from app.tenant where id = v_tenant;
  insert into app.tenant (id, slug, name) values (v_tenant, 'prova-dp-validada', 'Prova');

  v_recusou := false;
  begin
    insert into app.payroll_event_map (tenant_id, code, validated_at)
         values (v_tenant, '9999', now());
  exception when check_violation then v_recusou := true;
  end;
  if not v_recusou then
    raise exception 'uma linha foi marcada como validada sem categoria — a curadoria pareceria terminada com o trabalho por fazer';
  end if;

  --: não classificada e não validada: o estado em que a semente entrega
  insert into app.payroll_event_map (tenant_id, code, description, nature)
       values (v_tenant, '9998', 'H.EXTRA 60%', 'earning');
  --: classificada e validada: o estado em que a contabilidade a deixa
  insert into app.payroll_event_map (tenant_id, code, category, validated_at)
       values (v_tenant, '9997', 'overtime', now());

  delete from app.tenant where id = v_tenant;

  raise notice
    'OK: app.payroll_event_map ganhou description e nature anuláveis, category representa "não classificado", '
    'validar exige classificar, e nenhuma tabela nem policy nova nasceu.';
end $$;
