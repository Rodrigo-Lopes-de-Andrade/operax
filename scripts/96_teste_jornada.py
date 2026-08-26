#!/usr/bin/env python3
"""Prova o motor de jornada com escalas reais e resultado esperado.

    python3 scripts/96_teste_jornada.py

O SQL testado NÃO é digitado aqui: é extraído de
`backend/operax/motor/jornada.py`, do mesmo jeito que `provar_postgrest.sh`
extrai o cenário da suíte 98. Duas cópias de um `insert ... select` de cem
linhas divergiriam, e a que diverge é sempre a do teste.

O cenário reproduz o que a leitura do schema de produção mostrou em 24/08/2026:
uma semana fixa que descreve a realidade, uma escala 12x36 cujo `HorarioDia`
chega inteiramente vazio porque a rotação não cabe numa semana de sete dias, e
afastamentos por cima das duas. Roda em transação revertida.
"""

import os
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ENV = {
    **os.environ,
    "PGHOST": os.environ.get("PGHOST", "/tmp"),
    "PGPORT": os.environ.get("PGPORT", "5433"),
    "PGUSER": os.environ.get("PGUSER", "postgres"),
    "PGDATABASE": os.environ.get("PGDATABASE", "operax_test"),
}

TENANT = "cccccccc-0000-0000-0000-000000000001"
# Uma segunda-feira, de propósito: `DiaSemana` é 0=segunda e `extract(dow)` é
# 0=domingo. Uma janela que começa na segunda e termina no domingo faz a troca
# entre os dois aparecer como dia trocado, não como número diferente.
INICIO, FIM = "2026-08-10", "2026-08-16"


def sql_do_motor() -> str:
    """O `insert ... select` como o módulo o executa, com os parâmetros ligados."""
    fonte = (RAIZ / "backend" / "operax" / "motor" / "jornada.py").read_text()
    achado = re.search(r'_MATERIALIZE_SQL = """(.*?)"""', fonte, re.S)
    if not achado:
        sys.exit("não encontrei _MATERIALIZE_SQL em backend/operax/motor/jornada.py")
    corpo = achado.group(1)
    for marca in ("%(tenant_id)s", "%(start)s", "%(end)s"):
        if marca not in corpo:
            sys.exit(f"o SQL do motor deixou de ligar {marca} — o teste ficou cego")
    corpo = corpo.replace("%(tenant_id)s", f"'{TENANT}'")
    corpo = corpo.replace("%(start)s", f"'{INICIO}'").replace("%(end)s", f"'{FIM}'")
    # `%%` é escape de psycopg; no psql o literal é `%`.
    return corpo.replace("%%", "%")


CENARIO = f"""
begin;

create or replace function pg_temp.assert_eq(rotulo text, obtido text, esperado text)
returns void language plpgsql as $$
begin
  if obtido is distinct from esperado then
    raise exception 'FALHA [%]: esperado %, obtido %', rotulo, esperado, obtido;
  end if;
  raise notice '  ok  % (%)', rotulo, obtido;
end $$;

insert into app.tenant (id, slug, name) values ('{TENANT}', 'jornada-teste', 'Jornada')
  on conflict do nothing;

-- O espelho real exige empresa e departamento: `Funcionario.empresa_id` e
-- `.departamento_id` são NOT NULL com FK. O stub simulado não exigia — e é
-- justamente por isso que o baseline real é que vale.
insert into secullum."Empresa" (id, "EmpresaId", "Documento", "Nome", ativo, tenant_id) values
  ('c0000000-0000-0000-0000-0000000000d1', 9000, '00000000000191', 'Jornada SA', true, '{TENANT}');
insert into secullum."Departamento" (id, "DepartamentoId", empresa_id, "Descricao", tenant_id) values
  ('c0000000-0000-0000-0000-0000000000d2', 9000, 'c0000000-0000-0000-0000-0000000000d1', 'U-999', '{TENANT}');

-- ---------------------------------------------------------------------------
-- Três horários, e cada um existe por um caso que produção tem de verdade.
-- ---------------------------------------------------------------------------
insert into secullum."Horario" (id, "HorarioId", "Numero", "Descricao", ativo, tenant_id) values
  ('c0000000-0000-0000-0000-0000000000f1', 9001, 9001, 'Seg a Sex 08:00 as 18:00', true, '{TENANT}'),
  ('c0000000-0000-0000-0000-0000000000f2', 9002, 9002, 'U-999 - P01 - 06h as 18h - Par', true, '{TENANT}'),
  ('c0000000-0000-0000-0000-0000000000f3', 9003, 9003, 'Seg a Sex sem hora de entrada', true, '{TENANT}'),
  ('c0000000-0000-0000-0000-0000000000f4', 9004, 9004, 'U-999 - P05 - Seg a Sex - 19:00h ás 07:00h', true, '{TENANT}'),
  ('c0000000-0000-0000-0000-0000000000f5', 9005, 9005, 'U-999 - P02 - 19h as 7h - Impar', true, '{TENANT}'),
  ('c0000000-0000-0000-0000-0000000000f6', 9006, 9006, 'U-999 - P06 - 06h as 18h - Par', true, '{TENANT}');

-- Semana fixa: expediente de segunda(0) a sexta(4), folga sábado(5) e domingo(6).
insert into secullum."HorarioDia"
  (id, horario_id, "HorarioDiaId", "DiaSemana", "Entrada1", "Saida1", "Entrada2", "Saida2",
   "Carga", "ToleranciaExtra", "ToleranciaFalta", sem_expediente, tenant_id)
select gen_random_uuid(), 'c0000000-0000-0000-0000-0000000000f1', 1, d,
       '08:00', '12:00', '13:00', '18:00', 528, 10, 5, false, '{TENANT}'
from generate_series(0, 4) d;
-- ⚠️ a folga chega com as duas tolerâncias preenchidas: é a armadilha
--    documentada na coluna, e o motor não pode carregá-las para o dia sem turno.
insert into secullum."HorarioDia"
  (id, horario_id, "HorarioDiaId", "DiaSemana", "Carga", "ToleranciaExtra", "ToleranciaFalta",
   sem_expediente, tenant_id)
select gen_random_uuid(), 'c0000000-0000-0000-0000-0000000000f1', 1, d, 0, 10, 5, true, '{TENANT}'
from generate_series(5, 6) d;

-- 12x36: sete linhas, todas sem expediente. É como a rotação chega.
insert into secullum."HorarioDia"
  (id, horario_id, "HorarioDiaId", "DiaSemana", "Carga", "ToleranciaExtra", "ToleranciaFalta",
   sem_expediente, tenant_id)
select gen_random_uuid(), 'c0000000-0000-0000-0000-0000000000f2', 1, d, 0, 10, 5, true, '{TENANT}'
from generate_series(0, 6) d;

-- Mais dois 12x36, e a diferença entre eles é a única coisa que este par prova:
-- um tem rotação curada e CARIMBADA, o outro tem a mesma rotação sem carimbo.
insert into secullum."HorarioDia"
  (id, horario_id, "HorarioDiaId", "DiaSemana", "Carga", "ToleranciaExtra", "ToleranciaFalta",
   sem_expediente, tenant_id)
select gen_random_uuid(), h, 1, d, 0, 10, 5, true, '{TENANT}'
from unnest(array['c0000000-0000-0000-0000-0000000000f5'::uuid,
                  'c0000000-0000-0000-0000-0000000000f6'::uuid]) h,
     generate_series(0, 6) d;

-- Turno noturno, copiado de `U-075 - P05` em produção: entra 19:00, sai para o
-- intervalo 22:48, VOLTA 00:00 e encerra 05:00 do dia seguinte. Duas viradas num
-- dia só — a do intervalo e a da saída — e a fonte declara as duas escrevendo
-- uma hora MENOR. Ele conta como semana fixa e pontua 100: é a escala que o
-- portão de 80 deixa passar, e por isso a que não pode estar errada.
insert into secullum."HorarioDia"
  (id, horario_id, "HorarioDiaId", "DiaSemana", "Entrada1", "Saida1", "Entrada2", "Saida2",
   "Carga", "ToleranciaExtra", "ToleranciaFalta", sem_expediente, tenant_id)
select gen_random_uuid(), 'c0000000-0000-0000-0000-0000000000f4', 1, d,
       '19:00', '22:48', '00:00', '05:00', 528, 10, 5, false, '{TENANT}'
from generate_series(0, 4) d;
insert into secullum."HorarioDia"
  (id, horario_id, "HorarioDiaId", "DiaSemana", "Carga", "ToleranciaExtra", "ToleranciaFalta",
   sem_expediente, tenant_id)
select gen_random_uuid(), 'c0000000-0000-0000-0000-0000000000f4', 1, d, 0, 10, 5, true, '{TENANT}'
from generate_series(5, 6) d;

-- Expediente declarado sem hora de entrada: sabe-se que trabalha, não quando.
insert into secullum."HorarioDia"
  (id, horario_id, "HorarioDiaId", "DiaSemana", "Carga", "ToleranciaExtra", "ToleranciaFalta",
   sem_expediente, tenant_id)
select gen_random_uuid(), 'c0000000-0000-0000-0000-0000000000f3', 1, d, 480, 10, 5, false, '{TENANT}'
from generate_series(0, 6) d;

-- ---------------------------------------------------------------------------
-- Cinco pessoas: semana fixa, 12x36, semana fixa em férias, semana fixa em
-- atestado sobre a folga, e uma sem nenhuma ligação com o espelho.
-- ---------------------------------------------------------------------------
insert into secullum."Funcionario"
  (id, "FuncionarioId", "Nome", empresa_id, departamento_id, horario_id, tenant_id)
select f.id, f.num, f.nome,
       'c0000000-0000-0000-0000-0000000000d1', 'c0000000-0000-0000-0000-0000000000d2',
       f.horario, '{TENANT}'
from (values
  ('c0000000-0000-0000-0000-0000000000a1'::uuid, 9101, 'Semana Fixa',      'c0000000-0000-0000-0000-0000000000f1'::uuid),
  ('c0000000-0000-0000-0000-0000000000a2'::uuid, 9102, 'Doze Por Trinta',  'c0000000-0000-0000-0000-0000000000f2'::uuid),
  ('c0000000-0000-0000-0000-0000000000a3'::uuid, 9103, 'De Ferias',        'c0000000-0000-0000-0000-0000000000f1'::uuid),
  ('c0000000-0000-0000-0000-0000000000a4'::uuid, 9104, 'Atestado',         'c0000000-0000-0000-0000-0000000000f1'::uuid),
  ('c0000000-0000-0000-0000-0000000000a5'::uuid, 9105, 'Sem Hora',         'c0000000-0000-0000-0000-0000000000f3'::uuid),
  ('c0000000-0000-0000-0000-0000000000a7'::uuid, 9107, 'Noturno',          'c0000000-0000-0000-0000-0000000000f4'::uuid),
  ('c0000000-0000-0000-0000-0000000000a8'::uuid, 9108, 'Rotacao Curada',   'c0000000-0000-0000-0000-0000000000f5'::uuid),
  ('c0000000-0000-0000-0000-0000000000a9'::uuid, 9109, 'Rotacao Provisoria','c0000000-0000-0000-0000-0000000000f6'::uuid)
) as f(id, num, nome, horario);

insert into app.company (id, tenant_id, legal_name, trade_name) values
  ('c0000000-0000-0000-0000-0000000000e1', '{TENANT}', 'Jornada LTDA', 'J');
insert into app.unit (id, tenant_id, company_id, code, name) values
  ('c0000000-0000-0000-0000-00000000ac01', '{TENANT}', 'c0000000-0000-0000-0000-0000000000e1', 'J1', 'J Um');

insert into app.employee (id, tenant_id, company_id, unit_id, secullum_employee_id, name) values
  ('c0000000-0000-0000-0000-0000000000c1', '{TENANT}', 'c0000000-0000-0000-0000-0000000000e1', 'c0000000-0000-0000-0000-00000000ac01', 9101, 'Semana Fixa'),
  ('c0000000-0000-0000-0000-0000000000c2', '{TENANT}', 'c0000000-0000-0000-0000-0000000000e1', 'c0000000-0000-0000-0000-00000000ac01', 9102, 'Doze Por Trinta e Seis'),
  ('c0000000-0000-0000-0000-0000000000c3', '{TENANT}', 'c0000000-0000-0000-0000-0000000000e1', 'c0000000-0000-0000-0000-00000000ac01', 9103, 'De Ferias'),
  ('c0000000-0000-0000-0000-0000000000c4', '{TENANT}', 'c0000000-0000-0000-0000-0000000000e1', 'c0000000-0000-0000-0000-00000000ac01', 9104, 'Atestado No Fim De Semana'),
  ('c0000000-0000-0000-0000-0000000000c5', '{TENANT}', 'c0000000-0000-0000-0000-0000000000e1', 'c0000000-0000-0000-0000-00000000ac01', 9105, 'Sem Hora De Entrada'),
  ('c0000000-0000-0000-0000-0000000000c6', '{TENANT}', 'c0000000-0000-0000-0000-0000000000e1', 'c0000000-0000-0000-0000-00000000ac01', null, 'Sem Espelho'),
  ('c0000000-0000-0000-0000-0000000000c7', '{TENANT}', 'c0000000-0000-0000-0000-0000000000e1', 'c0000000-0000-0000-0000-00000000ac01', 9107, 'Noturno'),
  ('c0000000-0000-0000-0000-0000000000c8', '{TENANT}', 'c0000000-0000-0000-0000-0000000000e1', 'c0000000-0000-0000-0000-00000000ac01', 9108, 'Rotacao Curada'),
  ('c0000000-0000-0000-0000-0000000000c9', '{TENANT}', 'c0000000-0000-0000-0000-0000000000e1', 'c0000000-0000-0000-0000-00000000ac01', 9109, 'Rotacao Provisoria');

-- ---------------------------------------------------------------------------
-- A rotação curada. Ciclo de 2 dias ancorado numa segunda: trabalha 10, 12, 14 e
-- 16; folga 11, 13 e 15. A segunda linha é IDÊNTICA menos o carimbo.
-- ---------------------------------------------------------------------------
insert into app.schedule_rotation_map
  (tenant_id, secullum_schedule_id, cycle_length_days, anchor_date, expected_entry,
   expected_exit, expected_break_minutes, workload_minutes, tolerance_extra_minutes,
   tolerance_absence_minutes, validated_at) values
  ('{TENANT}', 9005, 2, '{INICIO}', '19:00', '05:00', 72, 528, 10, 5, now()),
  ('{TENANT}', 9006, 2, '{INICIO}', '06:00', '18:00', 60, 660, 10, 5, null);

-- Férias cobrindo a semana inteira; atestado só no sábado, sobre a folga.
insert into secullum."FuncionarioAfastamento"
  (id, funcionario_id, "AfastamentoId", "Inicio", "Fim", "JustificativaNome", tenant_id) values
  (gen_random_uuid(), 'c0000000-0000-0000-0000-0000000000a3', 1, '{INICIO}', '{FIM}', 'Férias', '{TENANT}'),
  (gen_random_uuid(), 'c0000000-0000-0000-0000-0000000000a4', 2, '2026-08-15', '2026-08-15', 'Atested', '{TENANT}');

-- ---------------------------------------------------------------------------
-- O motor
-- ---------------------------------------------------------------------------
{{MOTOR}}

-- ---------------------------------------------------------------------------
-- A) semana fixa: o dia da semana tem que bater — ISODOW, não DOW
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('segunda 10/08 é trabalho',
    (select day_type from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c1' and reference_date='2026-08-10'), 'work');
  perform pg_temp.assert_eq('sábado 15/08 é folga',
    (select day_type from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c1' and reference_date='2026-08-15'), 'day_off');
  perform pg_temp.assert_eq('domingo 16/08 é folga',
    (select day_type from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c1' and reference_date='2026-08-16'), 'day_off');
  perform pg_temp.assert_eq('a semana rende 5 dias de trabalho',
    (select count(*)::text from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c1' and day_type='work'), '5');
  perform pg_temp.assert_eq('entrada, saída e intervalo vêm do horário',
    (select expected_entry::text||' '||expected_exit::text||' '||expected_break_minutes::text
       from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c1' and reference_date='2026-08-10'),
    '08:00:00 18:00:00 60');
  perform pg_temp.assert_eq('confiança 100 na semana fixa',
    (select min(confidence)::text from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c1'), '100');
end $$;

-- ---------------------------------------------------------------------------
-- B) a folga não herda tolerância — a armadilha documentada na coluna
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('folga não carrega tolerância',
    (select tolerance_extra_minutes::text||'/'||tolerance_absence_minutes::text
       from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c1' and reference_date='2026-08-15'), '0/0');
  perform pg_temp.assert_eq('o dia de turno carrega a do Secullum',
    (select tolerance_extra_minutes::text||'/'||tolerance_absence_minutes::text
       from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c1' and reference_date='2026-08-10'), '10/5');
end $$;

-- ---------------------------------------------------------------------------
-- C) 12x36: o HorarioDia vazio não vira folga, vira "não sei"
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('12x36 não é declarado folga',
    (select count(*)::text from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c2' and day_type='day_off'), '0');
  perform pg_temp.assert_eq('12x36 tem confiança zero',
    (select max(confidence)::text from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c2'), '0');
  perform pg_temp.assert_eq('12x36 é marcado como inferido',
    (select distinct source from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c2'), 'inferred');
  perform pg_temp.assert_eq('12x36 não inventa horário',
    (select count(*)::text from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c2' and expected_entry is not null), '0');
end $$;

-- ---------------------------------------------------------------------------
-- C2) o turno noturno: a saída é MENOR que a entrada, e não é erro
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('a saída do noturno sai como veio, 05:00',
    (select expected_entry::text||' '||expected_exit::text from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c7' and reference_date='2026-08-10'),
    '19:00:00 05:00:00');
  -- 00:00 menos 22:48 dá menos 1368. O detector leria isso como o intervalo que
  -- a pessoa não tirou, todas as noites.
  perform pg_temp.assert_eq('o intervalo que cruza a meia-noite é 72, não -1368',
    (select expected_break_minutes::text from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c7' and reference_date='2026-08-10'),
    '72');
  perform pg_temp.assert_eq('o noturno é semana fixa e pontua 100',
    (select min(confidence)::text from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c7'), '100');
end $$;

-- ---------------------------------------------------------------------------
-- C3) a rotação curada, e a que ninguém carimbou
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('a âncora é dia de trabalho',
    (select day_type from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c8' and reference_date='2026-08-10'), 'work');
  -- É o que o 12x36 sem curadoria NÃO consegue dizer: lá o dia vazio vira
  -- `work` sem hora, porque folga e ignorância têm a mesma aparência.
  perform pg_temp.assert_eq('o dia seguinte é folga, e agora dá para afirmar isso',
    (select day_type from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c8' and reference_date='2026-08-11'), 'day_off');
  perform pg_temp.assert_eq('e o ciclo volta no terceiro dia',
    (select day_type from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c8' and reference_date='2026-08-12'), 'work');
  perform pg_temp.assert_eq('quatro trabalhados e três de folga na janela',
    (select count(*) filter (where day_type='work')::text||'/'||
            count(*) filter (where day_type='day_off')::text
       from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c8'), '4/3');
  perform pg_temp.assert_eq('o turno vem da rotação, não do espelho vazio',
    (select expected_entry::text||' '||expected_exit::text||' '||expected_break_minutes::text
       from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c8' and reference_date='2026-08-10'),
    '19:00:00 05:00:00 72');
  perform pg_temp.assert_eq('e a folga da rotação não herda tolerância',
    (select tolerance_extra_minutes::text||'/'||tolerance_absence_minutes::text
       from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c8' and reference_date='2026-08-11'), '0/0');
  perform pg_temp.assert_eq('rotação carimbada é manual_roster, com confiança 100',
    (select distinct source||' '||confidence::text from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c8'), 'manual_roster 100');

  -- ⛔ A asserção que sustenta a regra: mesma rotação, sem carimbo, não vale
  --    nada. Se ela valesse, uma curadoria pela metade viraria alerta contra
  --    alguém com a autoridade de um fato lido.
  perform pg_temp.assert_eq('rotação sem carimbo não é lida: segue confiança 0',
    (select max(confidence)::text from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c9'), '0');
  perform pg_temp.assert_eq('e continua inferida, sem folga nenhuma declarada',
    (select distinct source from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c9'), 'inferred');
end $$;

-- ---------------------------------------------------------------------------
-- D) precedência: afastamento > folga > jornada
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('férias vencem o turno de segunda',
    (select day_type from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c3' and reference_date='2026-08-10'), 'vacation');
  perform pg_temp.assert_eq('férias vencem também a folga de sábado',
    (select day_type from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c3' and reference_date='2026-08-15'), 'vacation');
  perform pg_temp.assert_eq('férias não carregam horário previsto',
    (select count(*)::text from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c3' and expected_entry is not null), '0');
  perform pg_temp.assert_eq('atestado vira leave_period, e o motivo não é guardado',
    (select day_type from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c4' and reference_date='2026-08-15'), 'leave_period');
  perform pg_temp.assert_eq('fora do afastamento a semana volta a valer',
    (select day_type from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c4' and reference_date='2026-08-14'), 'work');
end $$;

-- ---------------------------------------------------------------------------
-- E) turno sem hora, e pessoa sem espelho
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('turno sem hora fica em 50, abaixo do portão',
    (select distinct confidence::text from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c5'), '50');
  perform pg_temp.assert_eq('sem espelho é confiança zero',
    (select max(confidence)::text from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c6'), '0');
  perform pg_temp.assert_eq('mas a pessoa sem espelho ainda aparece',
    (select count(*)::text from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c6'), '7');
end $$;

-- ---------------------------------------------------------------------------
-- F) idempotência: rodar de novo não duplica, e reflete escala corrigida
-- ---------------------------------------------------------------------------
create temporary table antes as
  select count(*) as n from app.expected_workday where tenant_id = '{TENANT}';

update secullum."HorarioDia" set "Entrada1" = '07:00'
 where horario_id = 'c0000000-0000-0000-0000-0000000000f1' and "DiaSemana" = 0;

{{MOTOR}}

do $$ begin
  perform pg_temp.assert_eq('reprocessar não muda a contagem',
    (select count(*)::text from app.expected_workday where tenant_id = '{TENANT}'),
    (select n::text from antes));
  perform pg_temp.assert_eq('escala corrigida no Secullum chega na próxima rodada',
    (select expected_entry::text from app.expected_workday
      where employee_id='c0000000-0000-0000-0000-0000000000c1' and reference_date='2026-08-10'),
    '07:00:00');
end $$;

-- ---------------------------------------------------------------------------
-- G) a janela inteira, e o corte de cobertura do S3
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('9 pessoas x 7 dias',
    (select count(*)::text from app.expected_workday where tenant_id='{TENANT}'), '63');
  perform pg_temp.assert_eq('5 de 9 com confiança >= 80',
    (select count(*)::text from (
       select employee_id from app.expected_workday
        where tenant_id='{TENANT}' group by 1 having min(confidence) >= 80) t), '5');
end $$;

rollback;
"""


def main() -> None:
    script = CENARIO.replace("{MOTOR}", sql_do_motor() + ";")
    r = subprocess.run(
        # o script vai por stdin: `-f -` não é aceito por todo wrapper de psql
        ["psql", "-q", "-v", "ON_ERROR_STOP=1"],
        input=script,
        capture_output=True,
        text=True,
        env=ENV,
    )
    saida = "\n".join(
        linha
        for linha in (r.stdout + r.stderr).splitlines()
        if linha.strip() and not linha.startswith(("INSERT", "SELECT", "DO", "BEGIN", "ROLLBACK"))
    )
    print(saida)
    if r.returncode != 0:
        sys.exit(r.returncode)
    print("\n================================================")
    print(" MOTOR DE JORNADA: TODOS OS TESTES OK")
    print("================================================")


if __name__ == "__main__":
    main()
