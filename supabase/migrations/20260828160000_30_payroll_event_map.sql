-- ============================================================================
-- OperaX — 30. O PLANO DE CONTAS DE EVENTOS DA FOLHA VIRA DADO CURADO
-- ----------------------------------------------------------------------------
-- `app.payroll_entry.code` é o código do evento como a folha do cliente o
-- escreve — "0050", "H.EXTRA 60%", "FERIAS GOZO". O produto não tem como saber
-- o que cada um significa, e adivinhar por semelhança de texto é exatamente o
-- erro que a curadoria de unidade existe para evitar: palpite gravado não se
-- distingue de fato lido.
--
-- Sem este mapa, **8 dos 16 indicadores de 5.3 não saem**: custo de horas
-- extras, custo com férias, custo com desligamentos, projeção de 13º, e os três
-- de comparação, que precisam separar o que varia por evento. Está registrado
-- assim na `COBERTURA-ESCOPO.md` desde a primeira rodada.
--
-- Criar tabela em `app` com policy nova é uma das três paradas obrigatórias do
-- `CLAUDE.md`. **Autorizado pelo dono em 28/08/2026**, explicitamente.
--
-- O DESENHO É O MESMO DE `app.unit_secullum_map`, E NÃO POR PREGUIÇA
-- As duas resolvem o mesmo problema: um identificador do cliente que só uma
-- pessoa do cliente sabe traduzir. Então as duas têm `validated_by` e
-- `validated_at`, e as duas tratam linha sem validação como **provisória** —
-- que é o que permite a tela mostrar "mapeado" e "confirmado" como faixas
-- diferentes. Somar as duas faria a curadoria parecer terminada com metade do
-- trabalho por fazer.
--
-- O QUE ESTA MIGRATION NÃO FAZ
-- Não cria view, não cria indicador e não toca em `payroll_entry`. A categoria
-- é lida por quem monta o indicador, num PR que também traz a view — e aí sim
-- com `make db-test` provando o alvo. Aqui é só o lugar onde a curadoria pousa.
--
-- Idempotente. Seguro rodar repetidamente.
-- ============================================================================

create table if not exists app.payroll_event_map (
  tenant_id    uuid not null references app.tenant(id) on delete cascade,
  code         text not null,
  -- As nove categorias saem dos indicadores que o escopo pede, e nada além:
  -- quatro deles nomeiam a categoria diretamente (extra, férias, rescisão, 13º)
  -- e as outras cinco existem para que o resto da folha não seja empurrado para
  -- `other` — uma categoria "outros" que concentra 80% do valor não informa
  -- nada e não é conferível.
  category     text not null check (category in (
                 'base_salary', 'overtime', 'vacation', 'thirteenth', 'termination',
                 'benefit', 'charge', 'deduction', 'other')),
  -- O rótulo do plano de contas do cliente, como ele o chama. Existe para a
  -- tela de curadoria mostrar ao lado do código: quem confirma o mapeamento
  -- reconhece o nome, não o número.
  label        text,
  validated_by uuid references auth.users(id),
  validated_at timestamptz,
  notes        text,
  primary key (tenant_id, code)
);
create index if not exists payroll_event_map_categoria_idx
  on app.payroll_event_map (tenant_id, category);
comment on table app.payroll_event_map is
  'Código de evento da folha do cliente -> categoria do produto. Linha sem validated_at = '
  'mapeamento provisório, sinalizar na UI. Sem este mapa, metade do dashboard financeiro '
  'não existe — e com ele adivinhado, existe errado.';

alter table app.payroll_event_map enable row level security;
revoke all on table app.payroll_event_map from anon;
grant select, insert, update, delete on app.payroll_event_map to authenticated;
grant all on app.payroll_event_map to service_role;

-- Uma policy só, e de admin: o mapa decide como o dinheiro é somado. Quem pode
-- reclassificar um evento pode mudar todo indicador financeiro do tenant sem
-- que nenhum valor tenha mudado — é configuração de mesmo peso que a de
-- `app.unit_secullum_map`, e tem a mesma autorização.
drop policy if exists payroll_event_map_admin on app.payroll_event_map;
create policy payroll_event_map_admin on app.payroll_event_map
  for all to authenticated
  using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v_policies int;
  v_check    text;
begin
  if to_regclass('app.payroll_event_map') is null then
    raise exception 'app.payroll_event_map não existe depois de ser criada';
  end if;

  if not (select relrowsecurity from pg_class where oid = 'app.payroll_event_map'::regclass) then
    raise exception 'app.payroll_event_map sem RLS — regra 3 do CLAUDE.md';
  end if;

  select count(*) into v_policies from pg_policies
   where schemaname = 'app' and tablename = 'payroll_event_map';
  if v_policies <> 1 then
    raise exception 'app.payroll_event_map tem % policies, esperava 1', v_policies;
  end if;

  -- A chave é (tenant, código): o mesmo código em dois tenants são dois
  -- eventos diferentes, e um `unique (code)` global juntaria plano de contas
  -- de clientes distintos.
  if not exists (
    select 1 from pg_constraint
     where conrelid = 'app.payroll_event_map'::regclass and contype = 'p'
       and conkey = array[
             (select attnum from pg_attribute
               where attrelid = 'app.payroll_event_map'::regclass and attname = 'tenant_id'),
             (select attnum from pg_attribute
               where attrelid = 'app.payroll_event_map'::regclass and attname = 'code')
           ]::smallint[]
  ) then
    raise exception 'a chave primária não é (tenant_id, code)';
  end if;

  -- As quatro categorias que os indicadores do escopo nomeiam. Se alguém
  -- estreitar a lista, os indicadores param de ter onde se apoiar — e o
  -- sintoma seria um dashboard com zeros, não um erro.
  select pg_get_constraintdef(oid) into v_check from pg_constraint
   where conrelid = 'app.payroll_event_map'::regclass and contype = 'c';
  if v_check is null
     or v_check not like '%overtime%' or v_check not like '%vacation%'
     or v_check not like '%thirteenth%' or v_check not like '%termination%' then
    raise exception 'o check de categoria não cobre os quatro indicadores do escopo: %', v_check;
  end if;

  if has_table_privilege('anon', 'app.payroll_event_map', 'select') then
    raise exception 'anon alcança app.payroll_event_map';
  end if;

  raise notice 'OK: o mapa de evento de folha existe, com RLS de admin e chave por tenant.';
end $$;
