-- ============================================================================
-- OperaX — dp_absence_map. A CURADORIA QUE SEPARA FALTA DE ATESTADO
-- ----------------------------------------------------------------------------
-- Desenho: `docs/SPEC-DP.md` §1e, decisão do dono de 06/09/2026 ("promover o
-- espelho com curadoria"). O problema é o mesmo que `app.payroll_event_map`
-- (migration 30) já resolveu uma vez neste repositório, e o desenho é o dela.
--
-- ⛔ A DISTINÇÃO EXISTE SÓ COMO TEXTO LIVRE, E ISSO FOI MEDIDO
-- `secullum."FuncionarioAfastamento"` tem 62 linhas em produção. `AfastamentoId`
-- foi conferido e é IDENTIFICADOR DE REGISTRO — 62 distintos em 62 linhas —, não
-- código de tipo. Sobra o `JustificativaNome`, digitado no Secullum do cliente e
-- truncado em 7 caracteres:
--
--     Férias 43 · Atested 13 · ATEST M 4 · AFASTAD 1 · FALTA 1
--
-- `Atested` e `ATEST M` são o mesmo conceito escrito de dois jeitos. ⛔ A
-- curadoria TOLERA isso sem ADIVINHAR: as duas grafias entram como duas linhas,
-- cada uma classificada por uma pessoa. Nenhuma semelhança de texto é calculada
-- em lugar nenhum — palpite gravado não se distingue de fato lido, que é a frase
-- da migration 30 e continua valendo aqui.
--
-- ⛔ A REGRA QUE NÃO SE QUEBRA: STRING NÃO CURADA NÃO ENTRA EM CÁLCULO
-- E ela é mais estreita aqui do que na 30. Lá, linha sem `validated_at` é
-- "mapeamento provisório, sinalizar na UI" — o indicador sai com aviso. Aqui o
-- apurador RECUSA a competência inteira, nomeando a string. O motivo é o que a
-- §1e chama de mais perigoso: silêncio não é neutro, ele DÁ VALE TRANSPORTE A
-- QUEM FALTOU. Um provisório que vira "sem falta" tira dinheiro de ninguém e
-- entrega dinheiro a alguém — e ninguém reclama de receber a mais.
--
-- ⚠️ A CANONICALIZAÇÃO É DO BANCO, E É POR ISSO QUE ELA É UM `check`
-- A chave é `upper(btrim(justification))`. Sem a constraint, alguém curaria
-- `Atested` pela tela, o apurador procuraria `ATESTED`, não acharia, e a recusa
-- diria "não mapeada" sobre uma string que ESTÁ mapeada — o pior tipo de erro,
-- o que faz a pessoa desconfiar do conserto que ela acabou de fazer. Acento NÃO
-- é normalizado de propósito: 'FÉRIAS' e 'FERIAS' são strings diferentes e cada
-- uma se cura sozinha. Tirar acento é adivinhar que são a mesma coisa.
--
-- O ELO COM A `dp_leave_category`, E ELE É LOAD-BEARING
-- `category` aqui usa o MESMO vocabulário de `app.leave_period.category` — a
-- curadoria traduz a string do cliente para a categoria do domínio, e o destino
-- da promoção é aquela tabela. O bloco `do $$` compara as duas listas e falha
-- alto se elas divergirem: duas listas escritas à mão em dois arquivos divergem
-- na primeira mudança, e a metade que diverge é a que ninguém lê.
--
-- ⛔ SEM SEMENTE, E É DECISÃO
-- As cinco strings acima são o formato que existe, não uma classificação
-- aprovada. Semear `FALTA -> unjustified_absence` seria o produto decidindo, em
-- migration, quem perde a cesta. A tabela nasce vazia e o apurador recusa até
-- alguém do cliente classificar — que é exatamente o comportamento desejado.
--
-- ⛔ SEM GRANT PARA `authenticated` — a etapa DP inteira é Caminho 2
-- Difere da 30 nisto, e de propósito: lá a tela de curadoria fala PostgREST;
-- aqui a leitura é do apurador, no backend. A policy fica de pé para o dia em
-- que um PR conceder `select` por engano.
--
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

create table if not exists app.leave_justification_map (
  tenant_id     uuid not null references app.tenant(id) on delete cascade,
  --: O `JustificativaNome` do espelho, canonicalizado. É a chave porque é a
  --: única coisa que a origem oferece: `AfastamentoId` é identificador de
  --: registro, não de tipo (medido em 06/09/2026, 62 distintos em 62 linhas).
  justification text not null,
  --: O mesmo vocabulário de `app.leave_period.category` — a curadoria traduz
  --: para o domínio, e a promoção do espelho grava lá.
  category      text not null check (category in (
                  'vacation','leave_period','leave_of_absence','suspension',
                  'unjustified_absence')),
  validated_by  uuid references auth.users(id),
  validated_at  timestamptz,
  notes         text,
  created_at    timestamptz not null default now(),
  primary key (tenant_id, justification),
  --: A canonicalização é do banco. Ver o cabeçalho: sem isto, a linha curada
  --: pela tela e a busca do apurador deixam de se encontrar, em silêncio.
  constraint leave_justification_map_canonical
    check (justification = upper(btrim(justification))),
  constraint leave_justification_map_nao_vazia
    check (btrim(justification) <> '')
);

create index if not exists leave_justification_map_categoria_idx
  on app.leave_justification_map (tenant_id, category);

comment on table app.leave_justification_map is
  'JustificativaNome do espelho -> categoria do domínio. Linha sem validated_at NÃO entra em '
  'cálculo: o apurador de ciclo recusa a competência nomeando a string. Silêncio aqui dá vale '
  'transporte a quem faltou.';
comment on column app.leave_justification_map.justification is
  'Canonicalizada em upper(btrim(...)). Acento preservado: FÉRIAS e FERIAS são duas strings e '
  'cada uma se cura sozinha — normalizar acento seria adivinhar que são a mesma.';
comment on column app.leave_justification_map.validated_at is
  'Nulo = provisório, e provisório NÃO é usado. Mais estreito que app.payroll_event_map de '
  'propósito: lá o indicador sai com aviso, aqui a apuração para.';

alter table app.leave_justification_map enable row level security;
revoke all on table app.leave_justification_map from anon, authenticated;
-- Sem `delete`: mapeamento errado se corrige trocando a `category`, não
-- apagando a linha — a trilha de quem classificou o quê é o que torna a
-- curadoria auditável. Regra 6 do projeto estendida à curadoria.
grant select, insert, update on table app.leave_justification_map to service_role;

-- Uma policy só, e de admin — a mesma da 30, e pelo mesmo motivo: quem
-- reclassifica uma justificativa muda quem recebe cesta e quanto de VT cada um
-- recebe, sem que nenhum valor tenha mudado. É configuração do mesmo peso que
-- `app.unit_secullum_map`.
drop policy if exists leave_justification_map_admin on app.leave_justification_map;
create policy leave_justification_map_admin on app.leave_justification_map
  for all to authenticated
  using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v_policies   int;
  v_privilege  text;
  v_def        text;
  v_do_mapa    text[];
  v_do_leave   text[];
  v_tenant     uuid;
  v_recusou    boolean;
begin
  if to_regclass('app.leave_justification_map') is null then
    raise exception 'app.leave_justification_map não existe depois de ser criada';
  end if;

  -- 1. Regra 3 do CLAUDE.md.
  if not exists (
    select 1 from information_schema.columns
     where table_schema = 'app' and table_name = 'leave_justification_map'
       and column_name = 'tenant_id'
  ) then
    raise exception 'app.leave_justification_map sem tenant_id — regra 3 do CLAUDE.md';
  end if;
  if not (select relrowsecurity from pg_class
           where oid = 'app.leave_justification_map'::regclass) then
    raise exception 'app.leave_justification_map sem RLS — regra 3 do CLAUDE.md';
  end if;

  -- 2. Fora do PostgREST em TODOS os verbos. Perguntar só por `select` deixaria
  --    um `grant insert` passar — e inventar mapeamento alheio é pior que
  --    lê-lo: ele decide quem perde a cesta.
  foreach v_privilege in array array['SELECT','INSERT','UPDATE','DELETE'] loop
    if has_table_privilege('authenticated', 'app.leave_justification_map', v_privilege) then
      raise exception 'authenticated tem % em app.leave_justification_map — a etapa DP é só Caminho 2', v_privilege;
    end if;
    if has_table_privilege('anon', 'app.leave_justification_map', v_privilege) then
      raise exception 'anon tem % em app.leave_justification_map', v_privilege;
    end if;
  end loop;

  -- 3. O positivo. Sem ele o item 2 fica verde numa tabela que ninguém alcança.
  foreach v_privilege in array array['SELECT','INSERT','UPDATE'] loop
    if not has_table_privilege('service_role', 'app.leave_justification_map', v_privilege) then
      raise exception 'service_role não tem % em app.leave_justification_map — o apurador não leria a curadoria', v_privilege;
    end if;
  end loop;
  if has_table_privilege('service_role', 'app.leave_justification_map', 'DELETE') then
    raise exception 'service_role tem DELETE em app.leave_justification_map; mapeamento errado se corrige por update, não apagando quem classificou';
  end if;

  select count(*) into v_policies from pg_policies
   where schemaname = 'app' and tablename = 'leave_justification_map';
  if v_policies <> 1 then
    raise exception 'app.leave_justification_map tem % policies, esperava 1 (admin)', v_policies;
  end if;
  select qual into v_def from pg_policies
   where schemaname = 'app' and tablename = 'leave_justification_map'
     and policyname = 'leave_justification_map_admin';
  if coalesce(v_def, '') not like '%is_admin%' then
    raise exception 'leave_justification_map_admin sem util.is_admin no using';
  end if;
  select with_check into v_def from pg_policies
   where schemaname = 'app' and tablename = 'leave_justification_map'
     and policyname = 'leave_justification_map_admin';
  if coalesce(v_def, '') not like '%is_admin%' then
    raise exception 'leave_justification_map_admin sem util.is_admin no with check — é ele que decide o INSERT';
  end if;

  -- 4. ⛔ O ELO COM `app.leave_period.category`, COMPARADO CONJUNTO A CONJUNTO
  --    A curadoria traduz para o vocabulário do domínio. Se as duas listas
  --    divergirem, a promoção do espelho grava uma categoria que a tabela de
  --    destino recusa — e o sintoma chega no primeiro afastamento promovido,
  --    longe daqui. `like` em cada valor não bastaria: ele pega o que falta e
  --    não o que sobra, que é o defeito das três ferramentas de guarda que a
  --    `SPRINTS-DP.md` já nomeou.
  select array_agg(v order by v) into v_do_mapa
    from (select unnest(regexp_split_to_array(
                   regexp_replace(pg_get_constraintdef(oid), '.*ARRAY\[(.*)\].*', '\1'),
                   ',\s*')) as v
            from pg_constraint
           where conrelid = 'app.leave_justification_map'::regclass and contype = 'c'
             and pg_get_constraintdef(oid) like '%(category = ANY%') s;
  select array_agg(v order by v) into v_do_leave
    from (select unnest(regexp_split_to_array(
                   regexp_replace(pg_get_constraintdef(oid), '.*ARRAY\[(.*)\].*', '\1'),
                   ',\s*')) as v
            from pg_constraint
           where conrelid = 'app.leave_period'::regclass and contype = 'c'
             and pg_get_constraintdef(oid) like '%(category = ANY%') s;
  if v_do_mapa is null or v_do_leave is null then
    raise exception 'não achei o check de categoria em uma das duas tabelas (mapa: %, leave_period: %)',
      v_do_mapa, v_do_leave;
  end if;
  if v_do_mapa is distinct from v_do_leave then
    raise exception
      'o vocabulário do mapa (%) não é o de app.leave_period (%); a curadoria traduziria para uma categoria que o destino recusa',
      v_do_mapa, v_do_leave;
  end if;
  if not ('''unjustified_absence''::text' = any(v_do_mapa)) then
    raise exception 'o mapa não aceita unjustified_absence — a dp_leave_category não rodou antes desta';
  end if;

  -- 5. ⛔ SEM SEMENTE. Uma linha aqui é o produto decidindo quem perde a cesta.
  if exists (select 1 from app.leave_justification_map) then
    raise exception
      'app.leave_justification_map nasceu com % linha(s); a classificação é do cliente, não da migration',
      (select count(*) from app.leave_justification_map);
  end if;

  -- 6. A prova viva da canonicalização — a estrutura acima diz que o `check`
  --    existe; esta diz que ele recusa. Uma constraint que aceitasse 'Atested'
  --    deixaria a curadoria e a busca do apurador em universos separados.
  select t.id into v_tenant from app.tenant t order by t.created_at limit 1;
  if v_tenant is null then
    raise notice 'sem tenant: prova viva pulada (a estrutura já foi verificada acima)';
    return;
  end if;

  v_recusou := false;
  begin
    insert into app.leave_justification_map (tenant_id, justification, category)
    values (v_tenant, 'Atested', 'leave_period');
  exception when check_violation then
    v_recusou := true;
  end;
  if not v_recusou then
    delete from app.leave_justification_map where tenant_id = v_tenant;
    raise exception
      'app.leave_justification_map aceitou chave não canônica; a linha curada pela tela e a busca do apurador deixariam de se encontrar, em silêncio';
  end if;

  -- E a canônica entra, senão a trava barraria o legítimo — que é pior que a
  -- ausência dela.
  insert into app.leave_justification_map (tenant_id, justification, category)
  values (v_tenant, 'ATESTED', 'leave_period');
  delete from app.leave_justification_map where tenant_id = v_tenant;

  raise notice
    'OK: a curadoria de justificativa existe, vazia, fora do PostgREST, com chave canônica e o vocabulário de app.leave_period.';
end $$;
