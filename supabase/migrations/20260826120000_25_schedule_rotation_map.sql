-- ============================================================================
-- OperaX — 25. A ROTAÇÃO QUE O ESPELHO NÃO CONSEGUE ESCREVER
-- ----------------------------------------------------------------------------
-- `secullum."HorarioDia"` tem chave (horario_id, "DiaSemana") com "DiaSemana" de
-- 0 a 6: é uma semana fixa de sete dias, sem índice de ciclo e sem data de
-- início. Um 12x36 é ciclo de 48 h, e sete não é múltiplo de dois — o padrão
-- nunca fecha na semana e não cabe ali. O contorno do próprio Secullum está
-- visível no dado: a rotação chega como pares de horários "Par"/"Ímpar" cujo
-- `HorarioDia` vem INTEIRAMENTE vazio, sete linhas todas sem expediente.
--
-- Medido em produção (26/08/2026): oito horários nesse estado, quatro deles com
-- pessoa ativa. Elas materializam `expected_workday` com confiança 0, que é o
-- motor sendo honesto — e é também a razão de nunca terem gerado alerta: o
-- portão de 80 as para antes. O custo não é falso positivo, é ausência: quem
-- pontua 0 não é medido, e o G4 tem quatro pessoas fora da conta.
--
-- POR QUE ISTO É PONTE E NÃO CADASTRO DE ESCALA
-- A rotação é propriedade do HORÁRIO, não da pessoa: todos em
-- `U-042 - P01 - 19h as 7h - Impar` giram juntos, e `Funcionario.horario_id` já
-- diz quem está nele. Então não há tabela de atribuição a inventar — o espelho
-- já atribui. O que falta é o mesmo que faltava para departamento → unidade: um
-- lugar curado onde a informação que a origem não carrega é declarada uma vez.
-- Daí o formato ser o do `app.unit_secullum_map`, e não um cadastro paralelo.
--
-- TRÊS DECISÕES QUE ESTÃO NO SCHEMA, E NÃO NO CÓDIGO
--
-- 1. UM CICLO É ÂNCORA MAIS COMPRIMENTO, e o dia de trabalho é o resto zero.
--    Cobre 12x36 (ciclo 2), 24x48 (3) e 24x72 (4) com a mesma conta. Não cobre
--    6x1 — e não precisa: 6x1 tem seis dias declarados e o espelho o escreve
--    sozinho. Guardar posição a posição seria tabela filha para um caso que a
--    origem já resolve.
--
-- 2. LINHA SEM `validated_at` NÃO VALE. É a mesma regra da curadoria de
--    unidade: mapa provisório é faixa própria, nunca somado ao validado. Aqui a
--    consequência é maior — uma rotação provisória entraria como confiança 100 e
--    viraria alerta contra alguém. Quem lê é `jornada.py`, e ele exige o carimbo.
--
-- 3. A ROTAÇÃO SÓ VALE ONDE O ESPELHO NÃO FALA. Se `HorarioDia` declara
--    expediente, ele é o registro oficial e a curadoria não o sobrescreve. Esta
--    tabela existe para o silêncio da origem, não para discordar dela.
--
-- ⚠️ O QUE ESTA TABELA NÃO PODE VIRAR: rotação inferida das batidas. Os dias em
--    que a pessoa bateu SÃO os dias em que ela trabalhou, então uma âncora
--    derivada daí encaixa sempre — e uma escala que encaixa sempre nunca produz
--    `no_punches` nem `punch_on_day_off`. O motor passaria a concordar consigo
--    mesmo. Sugerir a partir das batidas é legítimo; gravar sem humano no meio
--    não é, e é por isso que `validated_by` é coluna e não conveniência.
--
-- Idempotente. Safe to run repeatedly.
-- ============================================================================

create table if not exists app.schedule_rotation_map (
  tenant_id                 uuid     not null references app.tenant(id) on delete cascade,
  secullum_schedule_id      bigint   not null,
  cycle_length_days         smallint not null check (cycle_length_days between 2 and 31),
  anchor_date               date     not null,
  expected_entry            time     not null,
  expected_exit             time     not null,
  expected_break_minutes    integer  check (expected_break_minutes >= 0),
  workload_minutes          integer  not null check (workload_minutes > 0),
  tolerance_extra_minutes   integer  not null default 0 check (tolerance_extra_minutes >= 0),
  tolerance_absence_minutes integer  not null default 0 check (tolerance_absence_minutes >= 0),
  validated_by              uuid     references auth.users(id),
  validated_at              timestamptz,
  notes                     text,
  created_at                timestamptz not null default now(),
  primary key (tenant_id, secullum_schedule_id)
);

comment on table app.schedule_rotation_map is
  'Rotação que o "HorarioDia" do Secullum não consegue escrever — 12x36 e afins. '
  'Uma linha por horário do espelho, curada com o cliente. Linha SEM validated_at é '
  'provisória e o motor de jornada NÃO a lê: rotação errada vira confiança 100 e alerta '
  'contra alguém. Vale apenas onde o horário não declara expediente nenhum.';

comment on column app.schedule_rotation_map.anchor_date is
  'Um dia em que o ciclo trabalha. O dia é de trabalho quando (data - âncora) mod ciclo é '
  'zero. A âncora pode ficar no meio da janela: o resto negativo do Postgres (-1 mod 2 = -1) '
  'não muda ESTE teste, porque só o zero decide e zero não tem sinal. Quem for calcular a '
  'POSIÇÃO no ciclo, e não só se é dia de trabalho, aí sim precisa normalizar.';

comment on column app.schedule_rotation_map.expected_exit is
  'Pode ser MENOR que expected_entry: é assim que um turno noturno se declara, do mesmo '
  'jeito que "HorarioDia" o declara. Quem trata a virada é regras.py.';

-- ---------------------------------------------------------------------------
-- RLS — curadoria é do admin, como o mapa de unidade (policy mapa_admin)
-- ---------------------------------------------------------------------------
alter table app.schedule_rotation_map enable row level security;
revoke all on table app.schedule_rotation_map from anon;
grant select, insert, update, delete on app.schedule_rotation_map to authenticated;
grant all    on app.schedule_rotation_map to service_role;

drop policy if exists rotation_map_admin on app.schedule_rotation_map;
create policy rotation_map_admin on app.schedule_rotation_map
  for all to authenticated using (util.is_admin(tenant_id)) with check (util.is_admin(tenant_id));

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$
declare
  v int;
begin
  select count(*) into v from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'app' and c.relname = 'schedule_rotation_map' and c.relrowsecurity;
  if v <> 1 then
    raise exception 'schedule_rotation_map sem RLS: tabela de app com tenant_id e sem RLS é vazamento';
  end if;

  select count(*) into v from pg_policy p
    where p.polrelid = 'app.schedule_rotation_map'::regclass;
  if v < 1 then
    raise exception 'schedule_rotation_map com RLS e sem policy nenhuma: ninguém lê, nem o dono';
  end if;

  -- Um ciclo de 1 dia é "trabalha todo dia", que é semana fixa e não rotação; um
  -- de 0 divide por zero. Os dois entram como escala plausível e saem como
  -- jornada prevista todo santo dia, com confiança 100.
  --
  -- A verificação é estrutural, e não um insert de teste, porque `app.tenant`
  -- está vazia quando as migrations rodam do zero: um insert que não insere
  -- linha nenhuma passa sem ter testado nada, e essa é a asserção que mente.
  select count(*) into v from pg_constraint
   where conrelid = 'app.schedule_rotation_map'::regclass
     and contype = 'c'
     and pg_get_constraintdef(oid) like '%cycle_length_days%';
  if v <> 1 then
    raise exception 'sem check em cycle_length_days: ciclo 1 vira semana fixa e ciclo 0 divide por zero';
  end if;

  select count(*) into v from pg_constraint
   where conrelid = 'app.schedule_rotation_map'::regclass
     and contype = 'c'
     and pg_get_constraintdef(oid) like '%workload_minutes%';
  if v <> 1 then
    raise exception 'sem check em workload_minutes: carga zero faz o dia inteiro sumir da conta';
  end if;

  raise notice 'OK: a rotação tem onde ser declarada, e provisória não conta.';
end $$;
