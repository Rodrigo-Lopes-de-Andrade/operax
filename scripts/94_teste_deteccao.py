#!/usr/bin/env python3
"""Prova o motor de detecção com batidas reais e resultado esperado.

    python3 scripts/94_teste_deteccao.py

O SQL testado NÃO é digitado aqui: é extraído de
`backend/operax/motor/deteccao.py`, do mesmo jeito que a suíte 96 faz com o
motor de jornada. Duas cópias de um `insert ... select` de trezentas linhas
divergem, e a que diverge é sempre a do teste.

A jornada esperada entra escrita à mão, e não gerada pelo motor de jornada, de
propósito: o contrato do detector é `app.expected_workday`, e acoplar os dois
faria um bug de escala reprovar a regra de tolerância. Cada pessoa do cenário
existe por um caso, e o nome dela diz qual.

Roda em transação revertida.
"""

import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
# `operax.motor.regras` não importa driver nenhum de propósito: é o que permite
# a este script, que roda no python do sistema, executar exatamente o SQL do
# motor em vez de uma cópia dele.
sys.path.insert(0, str(RAIZ / "backend"))
from operax.motor import regras  # noqa: E402
ENV = {
    **os.environ,
    "PGHOST": os.environ.get("PGHOST", "/tmp"),
    "PGPORT": os.environ.get("PGPORT", "5433"),
    "PGUSER": os.environ.get("PGUSER", "postgres"),
    "PGDATABASE": os.environ.get("PGDATABASE", "operax_test"),
}

TENANT = "dddddddd-0000-0000-0000-000000000001"
RUN = "dddddddd-0000-0000-0000-0000000000f0"
DIA = "2026-08-10"  # segunda-feira


def ligar(corpo: str, *, run_id: str = RUN, mode: str = "shadow", exige_run: bool = True) -> str:
    """O SQL do motor com os parâmetros ligados, como o psycopg o entregaria."""
    obrigatorios = ["%(tenant_id)s", "%(start)s", "%(end)s", "%(mode)s"]
    if exige_run:
        obrigatorios.append("%(run_id)s")
    for marca in obrigatorios:
        if marca not in corpo:
            sys.exit(f"o SQL do motor deixou de ligar {marca} — o teste ficou cego")
    corpo = corpo.replace("%(tenant_id)s", f"'{TENANT}'")
    corpo = corpo.replace("%(start)s", f"'{DIA}'").replace("%(end)s", f"'{DIA}'")
    corpo = corpo.replace("%(mode)s", f"'{mode}'").replace("%(run_id)s", f"'{run_id}'")
    # `%%` é escape de psycopg; no psql o literal é `%`.
    return corpo.replace("%%", "%")


def sql_do_motor(run_id: str = RUN, mode: str = "shadow") -> str:
    return ligar(regras.DETECT_SQL, run_id=run_id, mode=mode)


# ---------------------------------------------------------------------------
# As pessoas do cenário: (n, nome, day_type, entrada prevista, saída prevista,
# intervalo previsto, carga, tol_extra, tol_falta, confiança)
# ---------------------------------------------------------------------------
# 08:00 às 18:00 com uma hora de intervalo dá 540 minutos de carga. O número tem
# de fechar com as batidas do dia certo, ou o dia certo vira jornada excedida.
TRABALHO = ("work", "'08:00'", "'18:00'", "60", "540", "10", "5", "100")
PESSOAS = [
    (1, "Pontual", *TRABALHO),
    (2, "Entrada Atrasada", *TRABALHO),
    (3, "Entrada Adiantada", *TRABALHO),
    (4, "Saida Antecipada", *TRABALHO),
    (5, "Saida Postergada", *TRABALHO),
    (6, "Intervalo Excedido", *TRABALHO),
    (7, "Intervalo Insuficiente", *TRABALHO),
    (8, "Sem Retorno", *TRABALHO),
    (9, "Sem Marcacao", *TRABALHO),
    (10, "Batida Em Folga", "day_off", "null", "null", "null", "null", "0", "0", "100"),
    # Escala não derivável: dia de trabalho sem carga declarada e confiança 0.
    (11, "Escala Cega", "work", "null", "null", "null", "null", "0", "0", "0"),
    (12, "Marcacao Incompleta", *TRABALHO),
    (13, "Jornada Excedida", *TRABALHO),
    (14, "Afastado", "leave_period", "null", "null", "null", "null", "0", "0", "100"),
    (15, "Desconsiderada", *TRABALHO),
]

#: (n, tipo_coluna, indice, hora ou null, memoria ou null, desconsiderada)
BATIDAS = [
    (1, "Entrada", 1, "'08:00'", "null", "false"),
    (1, "Saida", 1, "'12:00'", "null", "false"),
    (1, "Entrada", 2, "'13:00'", "null", "false"),
    (1, "Saida", 2, "'18:00'", "null", "false"),
    # 26 minutos além da tolerância de falta de 5.
    (2, "Entrada", 1, "'08:26'", "null", "false"),
    (2, "Saida", 1, "'18:00'", "null", "false"),
    # 20 minutos antes, além da tolerância extra de 10.
    (3, "Entrada", 1, "'07:40'", "null", "false"),
    (3, "Saida", 1, "'18:00'", "null", "false"),
    (4, "Entrada", 1, "'08:00'", "null", "false"),
    (4, "Saida", 1, "'16:52'", "null", "false"),
    (5, "Entrada", 1, "'08:00'", "null", "false"),
    (5, "Saida", 1, "'18:23'", "null", "false"),
    # Intervalo de 91 min contra 60 previstos, tolerância extra 10.
    (6, "Entrada", 1, "'08:00'", "null", "false"),
    (6, "Saida", 1, "'12:00'", "null", "false"),
    (6, "Entrada", 2, "'13:31'", "null", "false"),
    (6, "Saida", 2, "'18:00'", "null", "false"),
    # Intervalo de 20 min contra 60 previstos, tolerância de falta 5.
    (7, "Entrada", 1, "'08:00'", "null", "false"),
    (7, "Saida", 1, "'12:00'", "null", "false"),
    (7, "Entrada", 2, "'12:20'", "null", "false"),
    (7, "Saida", 2, "'18:00'", "null", "false"),
    # Saiu para o intervalo e não voltou: a coluna de retorno tem Memoria e não tem hora.
    (8, "Entrada", 1, "'08:00'", "null", "false"),
    (8, "Saida", 1, "'12:00'", "null", "false"),
    (8, "Entrada", 2, "null", "'13:00'", "false"),
    # 9 não bate nada.
    (10, "Entrada", 1, "'08:00'", "null", "false"),
    (10, "Saida", 1, "'12:00'", "null", "false"),
    # 11 é a escala cega e também não bate nada.
    (12, "Entrada", 1, "'08:00'", "null", "false"),
    (12, "Saida", 1, "'12:00'", "null", "false"),
    (12, "Entrada", 2, "'13:00'", "null", "false"),
    # 540 de carga + 10 de tolerância; 07:00 às 19:00 dá 720 trabalhados.
    (13, "Entrada", 1, "'07:00'", "null", "false"),
    (13, "Saida", 1, "'19:00'", "null", "false"),
    (14, "Entrada", 1, "'08:00'", "null", "false"),
    (14, "Saida", 1, "'23:00'", "null", "false"),
    # Um dia idêntico ao da pessoa 1 mais uma batida desconsiderada às 23:59: se
    # ela contasse, o dia viraria jornada excedida e par ímpar de uma vez.
    (15, "Entrada", 1, "'08:00'", "null", "false"),
    (15, "Saida", 1, "'12:00'", "null", "false"),
    (15, "Entrada", 2, "'13:00'", "null", "false"),
    (15, "Saida", 2, "'18:00'", "null", "false"),
    (15, "Saida", 3, "'23:59'", "null", "true"),
]


def valores_pessoas() -> str:
    return ",\n  ".join(
        f"({n}, '{nome}', '{dt}', {ent}, {sai}, {inter}, {carga}, {tx}, {tf}, {conf})"
        for n, nome, dt, ent, sai, inter, carga, tx, tf, conf in PESSOAS
    )


def valores_batidas() -> str:
    return ",\n  ".join(
        f"({n}, '{tipo}', {idx}, {hora}, {mem}, {desc})" for n, tipo, idx, hora, mem, desc in BATIDAS
    )


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

-- Quanto vale um desvio de um tipo para uma pessoa, ou '(nenhum)'.
create or replace function pg_temp.minutos(p_n int, p_type text)
returns text language sql as $$
  select coalesce(
    (select minutes::text from app.deviation_event
      where employee_id = md5('det-c' || $1)::uuid and type = $2
        and status = 'active' and mode = 'shadow'),
    '(nenhum)');
$$;

insert into app.tenant (id, slug, name) values ('{TENANT}', 'deteccao-teste', 'Detecção')
  on conflict do nothing;

insert into secullum."Empresa" (id, "EmpresaId", "Documento", "Nome", ativo, tenant_id) values
  ('dddddddd-0000-0000-0000-0000000000d1', 9500, '00000000000191', 'Detecção SA', true, '{TENANT}');
insert into secullum."Departamento" (id, "DepartamentoId", empresa_id, "Descricao", tenant_id) values
  ('dddddddd-0000-0000-0000-0000000000d2', 9500, 'dddddddd-0000-0000-0000-0000000000d1', 'D-999', '{TENANT}');

insert into app.company (id, tenant_id, legal_name, trade_name) values
  ('dddddddd-0000-0000-0000-0000000000e1', '{TENANT}', 'Detecção LTDA', 'D');
insert into app.unit (id, tenant_id, company_id, code, name) values
  ('dddddddd-0000-0000-0000-00000000ac01', '{TENANT}', 'dddddddd-0000-0000-0000-0000000000e1', 'D1', 'D Um'),
  ('dddddddd-0000-0000-0000-00000000ac02', '{TENANT}', 'dddddddd-0000-0000-0000-0000000000e1', 'D2', 'D Dois');

-- ---------------------------------------------------------------------------
-- As pessoas, o espelho delas e a jornada esperada do dia
-- ---------------------------------------------------------------------------
create temporary table cenario (
  n int, nome text, day_type text, entrada time, saida time, intervalo int,
  carga int, tol_extra int, tol_falta int, confianca int
) on commit drop;

insert into cenario values
  {valores_pessoas()};

insert into secullum."Funcionario"
  (id, "FuncionarioId", "Nome", empresa_id, departamento_id, tenant_id)
select md5('det-f' || c.n)::uuid, 9500 + c.n, c.nome,
       'dddddddd-0000-0000-0000-0000000000d1', 'dddddddd-0000-0000-0000-0000000000d2', '{TENANT}'
from cenario c;

insert into app.employee
  (id, tenant_id, company_id, unit_id, secullum_employee_id, name)
select md5('det-c' || c.n)::uuid, '{TENANT}', 'dddddddd-0000-0000-0000-0000000000e1',
       'dddddddd-0000-0000-0000-00000000ac01', 9500 + c.n, c.nome
from cenario c;

insert into app.expected_workday
  (tenant_id, employee_id, reference_date, day_type, expected_entry, expected_exit,
   expected_break_minutes, workload_minutes, tolerance_extra_minutes,
   tolerance_absence_minutes, source, confidence)
select '{TENANT}', md5('det-c' || c.n)::uuid, '{DIA}', c.day_type, c.entrada, c.saida,
       c.intervalo, c.carga, c.tol_extra, c.tol_falta, 'secullum_schedule', c.confianca
from cenario c;

-- ---------------------------------------------------------------------------
-- As batidas — registro-dia em `secullum."Batida"`, colunas em `app.batida_marcacao`
-- ---------------------------------------------------------------------------
insert into secullum."Batida" (id, funcionario_id, "FuncionarioId", "Data", tenant_id)
select md5('det-b' || c.n)::uuid, md5('det-f' || c.n)::uuid, 9500 + c.n, '{DIA}', '{TENANT}'
from cenario c;

create temporary table marcacao (
  n int, tipo text, idx smallint, hora time, memoria time, desconsiderada boolean
) on commit drop;

insert into marcacao values
  {valores_batidas()};

insert into app.batida_marcacao
  (batida_id, funcionario_id, data, tipo_coluna, indice_coluna, hora, "Memoria",
   "FonteDadosId", desconsiderada, tenant_id)
select md5('det-b' || m.n)::uuid, md5('det-f' || m.n)::uuid, '{DIA}', m.tipo, m.idx,
       m.hora, m.memoria, (m.n * 100 + m.idx)::bigint, m.desconsiderada, '{TENANT}'
from marcacao m;

-- ---------------------------------------------------------------------------
-- Primeira execução
-- ---------------------------------------------------------------------------
insert into app.detection_run (id, tenant_id, mode, period_start, period_end)
values ('{RUN}', '{TENANT}', 'shadow', '{DIA}', '{DIA}');

{{MOTOR}}

-- ---------------------------------------------------------------------------
-- A) o dia certo não produz indício nenhum
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('dia pontual não gera indício',
    (select count(*)::text from app.deviation_event
      where employee_id = md5('det-c1')::uuid), '0');
end $$;

-- ---------------------------------------------------------------------------
-- B) entrada e saída, com a tolerância de cada lado
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('entrada 26 min atrasada é faltante',
    pg_temp.minutos(2, 'late_entry'), '-26');
  perform pg_temp.assert_eq('entrada atrasada não vira também adiantada',
    pg_temp.minutos(2, 'early_entry'), '(nenhum)');
  perform pg_temp.assert_eq('entrada 20 min adiantada é excedente',
    pg_temp.minutos(3, 'early_entry'), '20');
  perform pg_temp.assert_eq('saída 68 min antes é faltante',
    pg_temp.minutos(4, 'early_exit'), '-68');
  perform pg_temp.assert_eq('saída 23 min depois é excedente',
    pg_temp.minutos(5, 'late_exit'), '23');
  perform pg_temp.assert_eq('a hora prevista viaja com o indício',
    (select expected_time::text from app.deviation_event
      where employee_id = md5('det-c2')::uuid and type = 'late_entry'), '08:00:00');
  perform pg_temp.assert_eq('a hora observada também',
    (select actual_time::text from app.deviation_event
      where employee_id = md5('det-c2')::uuid and type = 'late_entry'), '08:26:00');
end $$;

-- ---------------------------------------------------------------------------
-- C) intervalo: excedido, insuficiente e sem retorno
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('intervalo de 91 contra 60 é faltante de 31',
    pg_temp.minutos(6, 'break_exceeded'), '-31');
  perform pg_temp.assert_eq('intervalo de 20 contra 60 é excedente de 40',
    pg_temp.minutos(7, 'break_too_short'), '40');
  perform pg_temp.assert_eq('saiu e não voltou é neutro',
    pg_temp.minutos(8, 'break_no_return'), '0');
  -- E NÃO deixa o par incompleto: a coluna sem hora não é batida, então o dia
  -- tem duas batidas — número par. Quem pega este caso é `break_no_return`, e é
  -- por isso que ele existe além da regra de paridade da SPEC §3.2.
  perform pg_temp.assert_eq('sem retorno não é contado como par ímpar',
    pg_temp.minutos(8, 'incomplete_punches'), '(nenhum)');
  perform pg_temp.assert_eq('o dia pontual não tem indício de intervalo',
    pg_temp.minutos(1, 'break_exceeded'), '(nenhum)');
end $$;

-- ---------------------------------------------------------------------------
-- D) integridade e escala
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('dia de trabalho sem batida é a carga inteira, faltante',
    pg_temp.minutos(9, 'no_punches'), '-540');
  perform pg_temp.assert_eq('batida em folga é excedente do que foi trabalhado',
    pg_temp.minutos(10, 'punch_on_day_off'), '240');
  perform pg_temp.assert_eq('três batidas é par incompleto',
    pg_temp.minutos(12, 'incomplete_punches'), '0');
  perform pg_temp.assert_eq('jornada de 720 contra 540+10 é excedente de 170',
    pg_temp.minutos(13, 'workday_exceeded'), '170');
end $$;

-- ---------------------------------------------------------------------------
-- E) o que o motor NÃO pode dizer
-- ---------------------------------------------------------------------------
do $$ begin
  -- Escala não derivável: sem carga declarada não há falta a afirmar. É a guarda
  -- que impede a enxurrada de falso positivo em 12x36.
  perform pg_temp.assert_eq('escala cega não vira falta',
    (select count(*)::text from app.deviation_event
      where employee_id = md5('det-c11')::uuid), '0');
  -- Afastamento sai inteiro, inclusive com batida no dia.
  perform pg_temp.assert_eq('dia de afastamento não gera indício nenhum',
    (select count(*)::text from app.deviation_event
      where employee_id = md5('det-c14')::uuid), '0');
  -- A marcação desconsiderada está gravada e não conta.
  perform pg_temp.assert_eq('batida desconsiderada não vira indício',
    (select count(*)::text from app.deviation_event
      where employee_id = md5('det-c15')::uuid), '0');
end $$;

-- ---------------------------------------------------------------------------
-- F) a convenção de sinal, que é o que sustenta os dois KPIs
-- ---------------------------------------------------------------------------
do $$
declare
  v_liquido int;
  v_modulo  int;
  v_errado  text;
begin
  select sum(minutes), sum(abs(minutes)) into v_liquido, v_modulo
  from app.deviation_event where tenant_id = '{TENANT}' and status = 'active';
  if v_modulo <= abs(v_liquido) then
    raise exception 'o cenário não tem as duas direções: líquido % e módulo %', v_liquido, v_modulo;
  end if;

  -- A asserção que vale não é a contagem: é que o SINAL concorde com a direção
  -- declarada no catálogo. Contar eventos à mão envelhece a cada tipo novo; esta
  -- pega um sinal invertido em qualquer um dos doze, hoje e depois.
  select string_agg(distinct d.type || '=' || d.minutes || ' (' || t.direction || ')', ', ')
    into v_errado
  from app.deviation_event d
  join app.deviation_type t on t.code = d.type
  where d.tenant_id = '{TENANT}' and d.status = 'active'
    and ((t.direction = 'surplus'  and d.minutes < 0)
      or (t.direction = 'shortfall' and d.minutes > 0)
      or (t.direction = 'neutral'   and d.minutes <> 0));
  if v_errado is not null then
    raise exception 'sinal contra a direção do catálogo: %', v_errado;
  end if;
  raise notice '  ok  o sinal de cada indício concorda com a direção do catálogo';

  -- E um dia carrega mais de um tipo: a SPEC §3.2 manda emitir todos, e é a
  -- config do tenant que decide o que conta no indicador.
  perform pg_temp.assert_eq('um mesmo dia pode carregar vários tipos',
    (select count(*)::text from app.deviation_event
      where employee_id = md5('det-c13')::uuid and mode = 'shadow' and status = 'active'), '3');
end $$;

-- ---------------------------------------------------------------------------
-- G) evidência: a origem da batida viaja com o indício
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('o indício carrega os ids das batidas do dia',
    (select array_length(punch_ids, 1)::text from app.deviation_event
      where employee_id = md5('det-c2')::uuid and type = 'late_entry'), '2');
end $$;
"""

SEGUNDA_RODADA = f"""
-- ---------------------------------------------------------------------------
-- H) reprocessar não duplica, corrige — e não reescreve o passado
--
-- Entre as duas execuções acontecem as duas coisas que acontecem de verdade: a
-- batida é corrigida na origem e a pessoa muda de unidade. A primeira tem de
-- chegar ao indício; a segunda não, porque `unit_id` é gravado no momento do
-- fato (SPEC §3.3) e o histórico não pode se reescrever.
-- ---------------------------------------------------------------------------
create temporary table antes on commit drop as
select count(*) as eventos from app.deviation_event
 where tenant_id = '{TENANT}' and status = 'active';

update app.batida_marcacao set hora = '08:40'
 where funcionario_id = md5('det-f2')::uuid and tipo_coluna = 'Entrada' and indice_coluna = 1;

update app.employee set unit_id = 'dddddddd-0000-0000-0000-00000000ac02'
 where id = md5('det-c2')::uuid;

insert into app.detection_run (id, tenant_id, mode, period_start, period_end)
values ('dddddddd-0000-0000-0000-0000000000f1', '{TENANT}', 'shadow', '{DIA}', '{DIA}');

{{MOTOR2}}

do $$ begin
  perform pg_temp.assert_eq('reprocessar a mesma janela não muda a contagem',
    (select (select eventos from antes)::text), (select count(*)::text
      from app.deviation_event where tenant_id = '{TENANT}' and status = 'active'));
  perform pg_temp.assert_eq('a batida corrigida chega ao indício',
    pg_temp.minutos(2, 'late_entry'), '-40');
  perform pg_temp.assert_eq('a hora observada acompanha',
    (select actual_time::text from app.deviation_event
      where employee_id = md5('det-c2')::uuid and type = 'late_entry'), '08:40:00');
  perform pg_temp.assert_eq('a unidade do indício é a do dia do fato, não a de hoje',
    (select unit_id::text from app.deviation_event
      where employee_id = md5('det-c2')::uuid and type = 'late_entry'),
    'dddddddd-0000-0000-0000-00000000ac01');
  perform pg_temp.assert_eq('o indício aponta para a execução mais recente',
    (select run_id::text from app.deviation_event
      where employee_id = md5('det-c2')::uuid and type = 'late_entry'),
    'dddddddd-0000-0000-0000-0000000000f1');
end $$;

-- ---------------------------------------------------------------------------
-- I) sombra e produção convivem sem se misturar
-- ---------------------------------------------------------------------------
insert into app.detection_run (id, tenant_id, mode, period_start, period_end)
values ('dddddddd-0000-0000-0000-0000000000f2', '{TENANT}', 'production', '{DIA}', '{DIA}');

{{MOTOR3}}

do $$ begin
  perform pg_temp.assert_eq('a mesma janela em produção não colide com a sombra',
    (select count(*)::text from app.deviation_event
      where employee_id = md5('det-c2')::uuid and type = 'late_entry'
        and status = 'active'), '2');
  perform pg_temp.assert_eq('e cada uma no seu modo',
    (select string_agg(mode, ',' order by mode) from app.deviation_event
      where employee_id = md5('det-c2')::uuid and type = 'late_entry' and status = 'active'),
    'production,shadow');
end $$;

-- ---------------------------------------------------------------------------
-- J) o total do cenário
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('15 pessoas no cenário, 11 com indício em sombra',
    (select count(distinct employee_id)::text from app.deviation_event
      where tenant_id = '{TENANT}' and mode = 'shadow' and status = 'active'), '11');
  -- As quatro que não têm indício são as quatro que não podem ter: o dia certo,
  -- a escala cega, o afastamento e a batida desconsiderada.
  perform pg_temp.assert_eq('e as quatro sem indício são as quatro certas',
    (select string_agg(c.nome, ', ' order by c.nome) from cenario c
      where not exists (select 1 from app.deviation_event d
                         where d.employee_id = md5('det-c' || c.n)::uuid)),
    'Afastado, Desconsiderada, Escala Cega, Pontual');
end $$;

"""

TERCEIRA_RODADA = f"""
-- ---------------------------------------------------------------------------
-- K) o indício que deixou de existir é PERGUNTADO, não apagado
--
-- A saída da pessoa 4 é corrigida no relógio para 18:00. O `early_exit` some da
-- realidade — e um insert não tem como falar de uma linha que não devia mais
-- estar lá. Por isso a revogação pergunta, contra a mesma definição de `evento`
-- que o detector usa para escrever.
-- ---------------------------------------------------------------------------
update app.batida_marcacao set hora = '18:00'
 where funcionario_id = md5('det-f4')::uuid and tipo_coluna = 'Saida' and indice_coluna = 1;

create temporary table sumiu on commit drop as
{{VANISHED}};

do $$ begin
  perform pg_temp.assert_eq('a saída corrigida faz o indício sumir',
    (select string_agg(type, ',' order by type) from sumiu
      where employee_id = md5('det-c4')::uuid), 'early_exit');
  perform pg_temp.assert_eq('e o indício que continua valendo não é perguntado',
    (select count(*)::text from sumiu where employee_id = md5('det-c6')::uuid), '0');
end $$;

-- ---------------------------------------------------------------------------
-- L) o indício que já foi enviado não é reescrito em silêncio
--
-- A saída da pessoa 5 vira 18:45 depois de o relatório sair. O detector tem de
-- deixar a linha como o gestor a recebeu, e a supersessão tem de enxergá-la.
-- ---------------------------------------------------------------------------
insert into app.report_cycle (id, tenant_id, unit_id, period_start, period_end, status)
values ('dddddddd-0000-0000-0000-0000000000c1', '{TENANT}',
        'dddddddd-0000-0000-0000-00000000ac01', '{DIA}', '{DIA}', 'sent');

update app.deviation_event set report_cycle_id = 'dddddddd-0000-0000-0000-0000000000c1'
 where employee_id = md5('det-c5')::uuid and type = 'late_exit' and mode = 'shadow';

update app.batida_marcacao set hora = '18:45'
 where funcionario_id = md5('det-f5')::uuid and tipo_coluna = 'Saida' and indice_coluna = 1;

insert into app.detection_run (id, tenant_id, mode, period_start, period_end)
values ('dddddddd-0000-0000-0000-0000000000f3', '{TENANT}', 'shadow', '{DIA}', '{DIA}');

{{MOTOR4}}

do $$ begin
  perform pg_temp.assert_eq('o indício já enviado fica como foi enviado',
    pg_temp.minutos(5, 'late_exit'), '23');
end $$;

create temporary table substituir on commit drop as
{{SUPERSEDED}};

do $$ begin
  perform pg_temp.assert_eq('a supersessão vê o que mudou de tamanho depois do relatório',
    (select minutes_before::text || ' -> ' || minutes_now::text from substituir
      where employee_id = md5('det-c5')::uuid and type = 'late_exit'), '23 -> 45');
  perform pg_temp.assert_eq('e só o que já foi enviado entra nela',
    (select count(*)::text from substituir), '1');
end $$;

rollback;
"""


def main() -> None:
    script = (
        CENARIO.replace("{MOTOR}", sql_do_motor() + ";")
        + SEGUNDA_RODADA.replace(
            "{MOTOR2}", sql_do_motor(run_id="dddddddd-0000-0000-0000-0000000000f1") + ";"
        ).replace(
            "{MOTOR3}",
            sql_do_motor(run_id="dddddddd-0000-0000-0000-0000000000f2", mode="production") + ";",
        )
        + TERCEIRA_RODADA.replace("{VANISHED}", ligar(regras.VANISHED_SQL, exige_run=False))
        .replace(
            "{MOTOR4}", sql_do_motor(run_id="dddddddd-0000-0000-0000-0000000000f3") + ";"
        )
        .replace("{SUPERSEDED}", ligar(regras.SUPERSEDED_SQL, exige_run=False))
    )
    r = subprocess.run(
        ["psql", "-q", "-v", "ON_ERROR_STOP=1"],
        input=script,
        capture_output=True,
        text=True,
        env=ENV,
    )
    saida = "\n".join(
        linha
        for linha in (r.stdout + r.stderr).splitlines()
        if linha.strip()
        and not linha.startswith(("INSERT", "SELECT", "DO", "BEGIN", "ROLLBACK", "UPDATE", "CREATE"))
    )
    print(saida)
    if r.returncode != 0:
        sys.exit(r.returncode)
    print("\n================================================")
    print(" MOTOR DE DETECÇÃO: TODOS OS TESTES OK")
    print("================================================")


if __name__ == "__main__":
    main()
