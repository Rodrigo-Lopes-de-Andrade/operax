#!/usr/bin/env python3
"""O feriado no motor: quem folga, quem trabalha, e o que vira indício.

    python3 scripts/83_teste_feriado.py

Gate da P0.3 (`docs/SPRINTS-ALCADA.md`). Decisões do dono de 28/09/2026 que este
arquivo prova, uma por bloco:

  * o sinal de "quem folga no feriado" é o TIPO DE ESCALA, não a unidade: o
    feriado vira `holiday` só para a jornada de semana fixa do Secullum; a
    rotação curada (`manual_roster`) e a inferida seguem a escala sem mudança;
  * trabalhar no feriado é indício (`punch_on_holiday`) só para quem é de semana
    fixa — o revezamento que trabalhou no feriado não gera nada;
  * precedência: afastamento > feriado > escala (o feriado vence até a folga
    semanal, para que a batida vire indício de feriado e não de folga);
  * VT: quem bateu no feriado recebe o dia (`holiday_worked`); quem folgou não;
  * indício que já saiu em relatório é revogado quando o feriado chega depois.

Nenhum SQL do motor é digitado aqui. A jornada é extraída de
`backend/operax/motor/jornada.py`, a escala do VT de
`backend/operax/dp/ciclo.py` (os dois por regex, como o `96_teste_jornada.py`), e
a detecção e a revogação vêm de `backend/operax/motor/regras.py` por import, como
o `94_teste_deteccao.py`. Uma cópia no teste continuaria verde com o motor
quebrado.

Cenário, todo sintético (tenant, pessoas e horários inventados):

    D1 = seg 10/08  feriado NACIONAL
    D2 = ter 11/08  feriado MUNICIPAL só da unidade A
    D3 = qua 12/08  dia comum — o controle; tem um nacional DESATIVADO do próprio
                    tenant e dois feriados do tenant VIZINHO (um apontando para
                    a unidade A deste), e nenhum dos três pode valer
    D4 = qui 13/08  dia comum que recebe um feriado DEPOIS de já ter saído em
                    relatório

Roda em transação revertida.
"""

import importlib
import os
import pathlib
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))
regras = importlib.import_module("operax.motor.regras")

ENV = {
    **os.environ,
    "PGHOST": os.environ.get("PGHOST", "/tmp"),
    "PGPORT": os.environ.get("PGPORT", "5433"),
    "PGUSER": os.environ.get("PGUSER", "postgres"),
    "PGDATABASE": os.environ.get("PGDATABASE", "operax_test"),
}

T1 = "f8300000-0000-0000-0000-000000000001"
T2 = "f8300000-0000-0000-0000-000000000002"
D1, D2, D3, D4 = "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13"
# Todos os turnos da janela já fecharam: as quatro faltas esperam o fim do turno.
NOW = "2026-08-14 12:00:00"


def _extrai(arquivo: str, nome: str, marcas: tuple[str, ...]) -> str:
    fonte = (RAIZ / "backend" / "operax" / arquivo).read_text()
    achado = re.search(rf'{nome} = """(.*?)"""', fonte, re.DOTALL)
    if not achado:
        sys.exit(f"não encontrei {nome} em backend/operax/{arquivo}")
    corpo = achado.group(1)
    for marca in marcas:
        if marca not in corpo:
            sys.exit(f"{nome} deixou de ligar {marca} — o teste ficou cego")
    return corpo


def _liga(corpo: str, valores: dict[str, str]) -> str:
    for nome, valor in valores.items():
        corpo = corpo.replace(f"%({nome})s", f"'{valor}'")
    sobra = re.findall(r"%\((\w+)\)s", corpo)
    if sobra:
        sys.exit(f"sobrou parâmetro sem ligar: {sobra}")
    # `%%` é escape de psycopg; no psql o literal é `%`.
    return corpo.replace("%%", "%")


def jornada(inicio: str, fim: str) -> str:
    corpo = _extrai(
        "motor/jornada.py",
        "_MATERIALIZE_SQL",
        ("%(tenant_id)s", "%(start)s", "%(end)s"),
    )
    return _liga(corpo, {"tenant_id": T1, "start": inicio, "end": fim}) + ";"


def deteccao(run_id: str, inicio: str, fim: str) -> str:
    corpo = regras.DETECT_SQL
    for marca in (
        "%(tenant_id)s",
        "%(start)s",
        "%(end)s",
        "%(mode)s",
        "%(now)s",
        "%(run_id)s",
    ):
        if marca not in corpo:
            sys.exit(f"o SQL do motor deixou de ligar {marca} — o teste ficou cego")
    ligado = _liga(
        corpo,
        {
            "tenant_id": T1,
            "start": inicio,
            "end": fim,
            "mode": "shadow",
            "now": NOW,
            "run_id": run_id,
        },
    )
    return f"""
insert into app.detection_run (id, tenant_id, mode, period_start, period_end)
values ('{run_id}', '{T1}', 'shadow', '{inicio}', '{fim}');
{ligado};
"""


def sumidos(inicio: str, fim: str) -> str:
    """`VANISHED_SQL` guardado numa tabela temporária para as asserções."""
    ligado = _liga(
        regras.VANISHED_SQL,
        {"tenant_id": T1, "start": inicio, "end": fim, "mode": "shadow", "now": NOW},
    )
    return f"create temporary table sumido as {ligado};"


def escala_vt(inicio: str, fim: str) -> str:
    corpo = _extrai(
        "dp/ciclo.py",
        "_SCHEDULE_SQL",
        ("%(tenant_id)s", "%(window_start)s", "%(window_end)s"),
    )
    ligado = _liga(corpo, {"tenant_id": T1, "window_start": inicio, "window_end": fim})
    return f"create temporary table escala_vt as {ligado};"


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

create or replace function pg_temp.pessoa(p text) returns uuid language sql as $$
  select md5('fer-c' || p)::uuid;
$$;

-- O dia de uma pessoa como `day_type`.
create or replace function pg_temp.dia(p text, d date) returns text language sql as $$
  select coalesce((select day_type from app.expected_workday
                    where employee_id = pg_temp.pessoa(p) and reference_date = d), '(sem linha)');
$$;

-- Os indícios ativos de uma pessoa num dia, em ordem, ou '(nenhum)'.
create or replace function pg_temp.indicios(p text, d date) returns text language sql as $$
  select coalesce(string_agg(type, ',' order by type), '(nenhum)')
    from app.deviation_event
   where employee_id = pg_temp.pessoa(p) and reference_date = d
     and status = 'active' and mode = 'shadow';
$$;

create or replace function pg_temp.conta(p_type text, d date) returns text language sql as $$
  select count(*)::text from app.deviation_event
   where tenant_id = '{T1}' and type = p_type and reference_date = d
     and status = 'active' and mode = 'shadow';
$$;

insert into app.tenant (id, slug, name) values
  ('{T1}', 'feriado-teste', 'Feriado'),
  ('{T2}', 'feriado-vizinho', 'Vizinho');

insert into secullum."Empresa" (id, "EmpresaId", "Documento", "Nome", "Desativada", tenant_id)
values ('f8300000-0000-0000-0000-0000000000d1', 8300, '00000000000383', 'Feriado SA', false, '{T1}');
insert into secullum."Departamento" (id, "DepartamentoId", empresa_id, "Descricao", tenant_id)
values ('f8300000-0000-0000-0000-0000000000d2', 8300,
        'f8300000-0000-0000-0000-0000000000d1', 'F-999', '{T1}');
insert into app.company (id, tenant_id, legal_name, trade_name)
values ('f8300000-0000-0000-0000-0000000000e1', '{T1}', 'Feriado LTDA', 'F');

-- Quatro unidades: A tem feriado municipal em D2; B, C e D não.
insert into app.unit (id, tenant_id, company_id, code, name)
select md5('fer-u' || u)::uuid, '{T1}', 'f8300000-0000-0000-0000-0000000000e1',
       'F-' || u, 'Unidade Sintetica ' || u
from unnest(array['A','B','C','D']) u;

-- ---------------------------------------------------------------------------
-- Quatro horários, um por forma de escala
-- ---------------------------------------------------------------------------
insert into secullum."Horario" (id, "HorarioId", "Numero", "Descricao", ativo, tenant_id) values
  (md5('fer-h1')::uuid, 8301, 8301, 'Seg a Sex 08h as 17h', true, '{T1}'),
  (md5('fer-h2')::uuid, 8302, 8302, 'Ter a Sab 08h as 17h', true, '{T1}'),
  (md5('fer-h3')::uuid, 8303, 8303, 'F-999 - P01 - 12x36 sem curadoria', true, '{T1}'),
  (md5('fer-h4')::uuid, 8304, 8304, 'F-999 - P02 - 12x36 curada', true, '{T1}'),
  (md5('fer-h5')::uuid, 8305, 8305, 'Ter a Sex sem a linha de segunda', true, '{T1}');

-- H1: semana fixa, seg(0) a sex(4); sáb e dom sem expediente.
insert into secullum."HorarioDia"
  (id, horario_id, "HorarioDiaId", "DiaSemana", "Entrada1", "Saida1", "Entrada2", "Saida2",
   "Carga", "ToleranciaExtra", "ToleranciaFalta", sem_expediente, tenant_id)
select gen_random_uuid(), md5('fer-h1')::uuid, 1, d, '08:00', '12:00', '13:00', '17:00',
       480, 10, 5, false, '{T1}'
from generate_series(0, 4) d;
insert into secullum."HorarioDia"
  (id, horario_id, "HorarioDiaId", "DiaSemana", "Carga", "ToleranciaExtra", "ToleranciaFalta",
   sem_expediente, tenant_id)
select gen_random_uuid(), md5('fer-h1')::uuid, 1, d, 0, 10, 5, true, '{T1}'
from generate_series(5, 6) d;

-- H2: semana fixa em que a SEGUNDA é folga (ter a sáb).
insert into secullum."HorarioDia"
  (id, horario_id, "HorarioDiaId", "DiaSemana", "Entrada1", "Saida1", "Entrada2", "Saida2",
   "Carga", "ToleranciaExtra", "ToleranciaFalta", sem_expediente, tenant_id)
select gen_random_uuid(), md5('fer-h2')::uuid, 1, d, '08:00', '12:00', '13:00', '17:00',
       480, 10, 5, false, '{T1}'
from generate_series(1, 5) d;
insert into secullum."HorarioDia"
  (id, horario_id, "HorarioDiaId", "DiaSemana", "Carga", "ToleranciaExtra", "ToleranciaFalta",
   sem_expediente, tenant_id)
select gen_random_uuid(), md5('fer-h2')::uuid, 1, d, 0, 10, 5, true, '{T1}'
from unnest(array[0, 6]) d;

-- H5: semana fixa que NÃO declara a segunda — nem turno, nem folga. É o
-- `dow is null` da jornada: o dia sai `day_off` inferido com confiança 0, e o
-- feriado não o transforma em fato.
insert into secullum."HorarioDia"
  (id, horario_id, "HorarioDiaId", "DiaSemana", "Entrada1", "Saida1", "Entrada2", "Saida2",
   "Carga", "ToleranciaExtra", "ToleranciaFalta", sem_expediente, tenant_id)
select gen_random_uuid(), md5('fer-h5')::uuid, 1, d, '08:00', '12:00', '13:00', '17:00',
       480, 10, 5, false, '{T1}'
from generate_series(1, 4) d;
insert into secullum."HorarioDia"
  (id, horario_id, "HorarioDiaId", "DiaSemana", "Carga", "ToleranciaExtra", "ToleranciaFalta",
   sem_expediente, tenant_id)
select gen_random_uuid(), md5('fer-h5')::uuid, 1, d, 0, 10, 5, true, '{T1}'
from generate_series(5, 6) d;

-- H3 e H4: sete dias sem expediente — é como o revezamento chega do Secullum.
insert into secullum."HorarioDia"
  (id, horario_id, "HorarioDiaId", "DiaSemana", "Carga", "ToleranciaExtra", "ToleranciaFalta",
   sem_expediente, tenant_id)
select gen_random_uuid(), h, 1, d, 0, 10, 5, true, '{T1}'
from unnest(array[md5('fer-h3')::uuid, md5('fer-h4')::uuid]) h, generate_series(0, 6) d;

-- H4 tem rotação curada e carimbada: ciclo de 2 ancorado em D1 — trabalha D1 e
-- D3, folga D2 e D4.
insert into app.schedule_rotation_map
  (tenant_id, secullum_schedule_id, cycle_length_days, anchor_date, expected_entry,
   expected_exit, expected_break_minutes, workload_minutes, tolerance_extra_minutes,
   tolerance_absence_minutes, validated_at)
values ('{T1}', 8304, 2, '{D1}', '08:00', '17:00', 60, 480, 10, 5, now());

-- ---------------------------------------------------------------------------
-- As pessoas. Cada uma existe por um caso.
-- ---------------------------------------------------------------------------
create temporary table elenco (n int, p text, horario text, unidade text) on commit drop;
insert into elenco values
  ( 1, 'wA',          'h1', 'A'),   -- semana fixa, nunca bate
  ( 2, 'wB',          'h1', 'B'),   -- idem, a que sai em relatório no D4
  ( 3, 'wC',          'h1', 'C'),
  ( 4, 'wD',          'h1', 'D'),
  ( 5, 'wSemUnidade', 'h1', null),  -- o nacional vale; o municipal não
  ( 6, 'wA2',         'h1', 'A'),   -- bate em D1 e D2
  ( 7, 'wImpar',      'h1', 'B'),   -- uma batida só em D1
  ( 8, 'wSegFolga',   'h2', 'C'),   -- a segunda é folga dela, e ela bate em D1
  ( 9, 'wFerias',     'h1', 'A'),   -- férias em D1
  (10, 'rotFalta',    'h4', 'A'),   -- revezamento curado, não bate
  (11, 'rotTrabalha', 'h4', 'B'),   -- revezamento curado, bate em D1
  (12, 'inferido',    'h3', 'C'),   -- revezamento sem curadoria, bate em D1
  -- Os três do VT: nenhum deles bateu NO feriado, e cada um tem uma batida que
  -- um critério frouxo de "bateu" confundiria com trabalho no feriado.
  (13, 'wFolgaBate',  'h1', 'D'),   -- folga o feriado e bate em D2 e D3
  (14, 'wDescons',    'h1', 'D'),   -- no feriado, só marcação desconsiderada
  (15, 'wSemHora',    'h1', 'D'),   -- no feriado, só a coluna sem hora
  (16, 'wSemDia',     'h5', 'D');   -- a escala não declara a segunda

insert into secullum."Funcionario"
  (id, "FuncionarioId", "Nome", empresa_id, departamento_id, horario_id, tenant_id)
select md5('fer-f' || e.p)::uuid, 8300 + e.n, 'Pessoa Sintetica ' || e.n,
       'f8300000-0000-0000-0000-0000000000d1', 'f8300000-0000-0000-0000-0000000000d2',
       md5('fer-' || e.horario)::uuid, '{T1}'
from elenco e;

insert into app.employee (id, tenant_id, company_id, unit_id, secullum_employee_id, name)
select pg_temp.pessoa(e.p), '{T1}', 'f8300000-0000-0000-0000-0000000000e1',
       case when e.unidade is not null then md5('fer-u' || e.unidade)::uuid end,
       8300 + e.n, 'Pessoa Sintetica ' || e.n
from elenco e;

insert into secullum."FuncionarioAfastamento"
  (id, funcionario_id, "AfastamentoId", "Inicio", "Fim", "JustificativaNome", tenant_id)
values (gen_random_uuid(), md5('fer-fwFerias')::uuid, 8301, '{D1}', '{D1}', 'Férias', '{T1}');

-- As batidas. Um dia inteiro é 08-12 / 13-17, exatamente o previsto das escalas:
-- nenhum atraso nem intervalo pode se misturar com o que está sob teste.
create temporary table bateu (p text, dia date, completo boolean) on commit drop;
insert into bateu values
  ('wA2', '{D1}', true), ('wA2', '{D2}', true),
  ('wImpar', '{D1}', false),
  ('wSegFolga', '{D1}', true),
  ('rotTrabalha', '{D1}', true),
  ('inferido', '{D1}', true),
  ('wFolgaBate', '{D2}', true), ('wFolgaBate', '{D3}', true);

insert into secullum."Batida" (id, funcionario_id, "FuncionarioId", "Data", tenant_id)
select md5('fer-b' || b.p || b.dia)::uuid, md5('fer-f' || b.p)::uuid, 8300 + e.n, b.dia, '{T1}'
from bateu b join elenco e on e.p = b.p;

insert into app.batida_marcacao
  (batida_id, funcionario_id, data, tipo_coluna, indice_coluna, hora, "FonteDadosId",
   desconsiderada, tenant_id)
select md5('fer-b' || b.p || b.dia)::uuid, md5('fer-f' || b.p)::uuid, b.dia, t.tipo, t.indice,
       t.hora, (83000000 + e.n * 1000 + extract(day from b.dia)::int * 10 + t.ord)::bigint,
       false, '{T1}'
from bateu b
join elenco e on e.p = b.p
cross join (values ('Entrada', 1, time '08:00', 1), ('Saida', 1, time '12:00', 2),
                   ('Entrada', 2, time '13:00', 3), ('Saida', 2, time '17:00', 4))
       as t(tipo, indice, hora, ord)
where b.completo or t.ord = 1;

-- O que no feriado NÃO é batida: o dia inteiro desconsiderado, e a coluna que
-- existe sem hora. O detector não conta nenhum dos dois, e o VT também não pode.
insert into secullum."Batida" (id, funcionario_id, "FuncionarioId", "Data", tenant_id)
values (md5('fer-bwDescons')::uuid, md5('fer-fwDescons')::uuid, 8314, '{D1}', '{T1}'),
       (md5('fer-bwSemHora')::uuid, md5('fer-fwSemHora')::uuid, 8315, '{D1}', '{T1}');
insert into app.batida_marcacao
  (batida_id, funcionario_id, data, tipo_coluna, indice_coluna, hora, "FonteDadosId",
   desconsiderada, tenant_id)
select md5('fer-bwDescons')::uuid, md5('fer-fwDescons')::uuid, '{D1}', t.tipo, t.indice,
       t.hora, 83900000 + t.ord, true, '{T1}'
from (values ('Entrada', 1, time '08:00', 1), ('Saida', 1, time '12:00', 2),
             ('Entrada', 2, time '13:00', 3), ('Saida', 2, time '17:00', 4))
     as t(tipo, indice, hora, ord);
insert into app.batida_marcacao
  (batida_id, funcionario_id, data, tipo_coluna, indice_coluna, hora, "FonteDadosId",
   desconsiderada, tenant_id)
values (md5('fer-bwSemHora')::uuid, md5('fer-fwSemHora')::uuid, '{D1}', 'Entrada', 1, null,
        83900011, false, '{T1}');

-- ---------------------------------------------------------------------------
-- O calendário
-- ---------------------------------------------------------------------------
insert into app.holiday (tenant_id, reference_date, jurisdiction, unit_id, name, active) values
  ('{T1}', '{D1}', 'national',  null,                   'Feriado Nacional Sintetico', true),
  ('{T1}', '{D2}', 'municipal', md5('fer-uA')::uuid,    'Feriado Municipal Sintetico', true),
  -- Desativado: cadastrado por engano. Não pode valer.
  ('{T1}', '{D3}', 'national',  null,                   'Feriado Desativado', false),
  -- O vizinho: um nacional dele, e um municipal que aponta para a unidade A
  -- DESTE tenant. Nenhuma FK composta impede a linha; o motor é que não pode
  -- deixar que ela case com ninguém daqui.
  ('{T2}', '{D3}', 'national',  null,                   'Feriado do Vizinho', true),
  ('{T2}', '{D3}', 'municipal', md5('fer-uA')::uuid,    'Feriado Alheio', true);

-- ---------------------------------------------------------------------------
-- O motor: jornada, depois detecção
-- ---------------------------------------------------------------------------
{{JORNADA_D1_D4}}
{{DETECCAO_1}}

-- ---------------------------------------------------------------------------
-- 1. (pos) Feriado nacional: semana fixa vira `holiday`, em TODAS as unidades
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('1a. D1: as 11 pessoas de semana fixa sem afastamento viram holiday',
    (select count(*)::text from elenco e
      where pg_temp.dia(e.p, '{D1}') = 'holiday'), '11');
  perform pg_temp.assert_eq('1f. D1: a semana que não declara a segunda segue a escala (inferida)',
    (select day_type || ' ' || source || '/' || confidence from app.expected_workday
      where employee_id = pg_temp.pessoa('wSemDia') and reference_date = '{D1}'),
    'day_off inferred/0');
  perform pg_temp.assert_eq('1b. D1: as quatro unidades e a pessoa sem unidade têm holiday',
    (select string_agg(coalesce(e.unidade, '-'), ',' order by coalesce(e.unidade, '-'))
       from (select distinct unidade from elenco
              where pg_temp.dia(p, '{D1}') = 'holiday') e), '-,A,B,C,D');
  perform pg_temp.assert_eq('1c. o dia de feriado é fato: confiança 100, sem hora, sem tolerância',
    (select distinct confidence::text || ' ' || coalesce(expected_entry::text, 'sem-entrada')
            || ' ' || coalesce(workload_minutes::text, 'sem-carga')
            || ' ' || tolerance_extra_minutes || '/' || tolerance_absence_minutes
            || ' ' || source
       from app.expected_workday
      where tenant_id = '{T1}' and reference_date = '{D1}' and day_type = 'holiday'),
    '100 sem-entrada sem-carga 0/0 secullum_schedule');
  perform pg_temp.assert_eq('1d. D1: ZERO no_punches de semana fixa, em todas as unidades',
    (select count(*)::text from app.deviation_event d
       join app.expected_workday w
         on w.employee_id = d.employee_id and w.reference_date = d.reference_date
      where d.tenant_id = '{T1}' and d.type = 'no_punches' and d.reference_date = '{D1}'
        and w.source = 'secullum_schedule'), '0');
  perform pg_temp.assert_eq('1e. D1: o único no_punches do tenant é o do revezamento que faltou',
    pg_temp.conta('no_punches', '{D1}') || ' ' || pg_temp.indicios('rotFalta', '{D1}'),
    '1 no_punches');
end $$;

-- ---------------------------------------------------------------------------
-- 2. (neg) Feriado municipal da unidade A não alcança a B — nem ninguém fora de A
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('2a. D2: quem é de A folga',
    pg_temp.dia('wA', '{D2}') || ' ' || pg_temp.indicios('wA', '{D2}'), 'holiday (nenhum)');
  perform pg_temp.assert_eq('2b. D2: quem é de B trabalha, e faltar é falta',
    pg_temp.dia('wB', '{D2}') || ' ' || pg_temp.indicios('wB', '{D2}'), 'work no_punches');
  perform pg_temp.assert_eq('2c. D2: nem C, nem D, nem quem não tem unidade',
    pg_temp.dia('wC', '{D2}') || ' ' || pg_temp.dia('wD', '{D2}') || ' '
      || pg_temp.dia('wSemUnidade', '{D2}'), 'work work work');
  perform pg_temp.assert_eq('2d. D2: nove faltas fora de A, nenhuma dentro',
    pg_temp.conta('no_punches', '{D2}') || ' / '
      || (select count(*)::text from app.deviation_event d
           where d.tenant_id = '{T1}' and d.type = 'no_punches'
             and d.reference_date = '{D2}' and d.unit_id = md5('fer-uA')::uuid),
    '9 / 0');
end $$;

-- ---------------------------------------------------------------------------
-- 3. Revezamento: o feriado não muda a escala
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('3a. D1: revezamento curado segue work, e faltar é falta',
    pg_temp.dia('rotFalta', '{D1}') || ' ' || pg_temp.indicios('rotFalta', '{D1}'),
    'work no_punches');
  perform pg_temp.assert_eq('3b. D1: revezamento curado que trabalhou NÃO gera indício',
    pg_temp.dia('rotTrabalha', '{D1}') || ' ' || pg_temp.indicios('rotTrabalha', '{D1}'),
    'work (nenhum)');
  perform pg_temp.assert_eq('3c. D1: revezamento sem curadoria segue inferido e sem indício',
    pg_temp.dia('inferido', '{D1}') || ' '
      || (select source || '/' || confidence from app.expected_workday
           where employee_id = pg_temp.pessoa('inferido') and reference_date = '{D1}')
      || ' ' || pg_temp.indicios('inferido', '{D1}'),
    'work inferred/0 (nenhum)');
  perform pg_temp.assert_eq('3d. D2: a folga do ciclo continua folga',
    pg_temp.dia('rotFalta', '{D2}'), 'day_off');
end $$;

-- ---------------------------------------------------------------------------
-- 4. Semana fixa que bateu no feriado: `punch_on_holiday`
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('4a. D1: semana fixa que bateu gera punch_on_holiday',
    pg_temp.indicios('wA2', '{D1}'), 'punch_on_holiday');
  perform pg_temp.assert_eq('4b. com os minutos trabalhados, como excedente',
    (select minutes::text from app.deviation_event
      where employee_id = pg_temp.pessoa('wA2') and reference_date = '{D1}'
        and type = 'punch_on_holiday'), '480');
  perform pg_temp.assert_eq('4c. D2: o municipal de A também — ela é de A',
    pg_temp.indicios('wA2', '{D2}'), 'punch_on_holiday');
  perform pg_temp.assert_eq('4d. precedência: feriado vence a folga semanal (não é punch_on_day_off)',
    pg_temp.dia('wSegFolga', '{D1}') || ' ' || pg_temp.indicios('wSegFolga', '{D1}'),
    'holiday punch_on_holiday');
  perform pg_temp.assert_eq('4e. batida ímpar no feriado: o indício e a marcação incompleta',
    pg_temp.indicios('wImpar', '{D1}'), 'incomplete_punches,punch_on_holiday');
  perform pg_temp.assert_eq('4f. D1: três punch_on_holiday e nenhum punch_on_day_off',
    pg_temp.conta('punch_on_holiday', '{D1}') || '/' || pg_temp.conta('punch_on_day_off', '{D1}'),
    '3/0');
  perform pg_temp.assert_eq('4h. marcação desconsiderada e coluna sem hora não são batida no feriado',
    pg_temp.indicios('wDescons', '{D1}') || ' ' || pg_temp.indicios('wSemHora', '{D1}'),
    '(nenhum) (nenhum)');
  -- A linha de `deviation_type_config` por tenant é garantia da migration (os
  -- tenants deste teste nascem depois dela); aqui, o catálogo que a UI lê.
  perform pg_temp.assert_eq('4g. o tipo novo está no catálogo, com rótulo de batida em feriado',
    (select description || ' / ' || direction || ' / ' || category
       from app.deviation_type where code = 'punch_on_holiday'),
    'Batida em feriado / surplus / roster');
end $$;

-- ---------------------------------------------------------------------------
-- 5. Afastamento vence o feriado
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('5. D1: férias continuam férias',
    pg_temp.dia('wFerias', '{D1}'), 'vacation');
end $$;

-- ---------------------------------------------------------------------------
-- 6. O controle: D3 prova que o teste não é cego — e que desativado, vizinho e
--    unidade alheia não valem
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('6a. D3: 12 de semana fixa + 2 de revezamento faltam = 14 no_punches',
    pg_temp.conta('no_punches', '{D3}'), '14');
  perform pg_temp.assert_eq('6b. D3: nenhum holiday no tenant (desativado, vizinho e alheio)',
    (select count(*)::text from app.expected_workday
      where tenant_id = '{T1}' and reference_date = '{D3}' and day_type = 'holiday'), '0');
  perform pg_temp.assert_eq('6c. D3: a unidade A, alvo da linha do vizinho, trabalha',
    pg_temp.dia('wA', '{D3}') || ' ' || pg_temp.indicios('wA', '{D3}'), 'work no_punches');
end $$;

-- ---------------------------------------------------------------------------
-- 7. Idempotência: jornada e detecção de novo, as mesmas contagens
-- ---------------------------------------------------------------------------
create temporary table antes as
  select (select count(*) from app.expected_workday where tenant_id = '{T1}') as dias,
         (select count(*) from app.deviation_event where tenant_id = '{T1}') as eventos,
         (select string_agg(type || '@' || reference_date, ',' order by type, reference_date)
            from app.deviation_event where tenant_id = '{T1}' and status = 'active') as quais;

{{JORNADA_D1_D4}}
{{DETECCAO_2}}

do $$ begin
  perform pg_temp.assert_eq('7. rodar de novo não duplica nem muda nada',
    (select count(*) from app.expected_workday where tenant_id = '{T1}')::text || ' '
      || (select count(*) from app.deviation_event where tenant_id = '{T1}')::text || ' '
      || (select string_agg(type || '@' || reference_date, ',' order by type, reference_date)
            from app.deviation_event where tenant_id = '{T1}' and status = 'active'),
    (select dias::text || ' ' || eventos::text || ' ' || quais from antes));
end $$;

-- ---------------------------------------------------------------------------
-- 8. VT: a escala que o apurador lê
-- ---------------------------------------------------------------------------
{{ESCALA_VT}}

create or replace function pg_temp.vt(p text, d date) returns text language sql as $$
  select coalesce((select day_type from escala_vt
                    where employee_id = pg_temp.pessoa(p) and reference_date = d), '(sem linha)');
$$;

do $$ begin
  perform pg_temp.assert_eq('8a. semana fixa que bateu no feriado: holiday_worked (recebe o VT)',
    pg_temp.vt('wA2', '{D1}') || ' ' || pg_temp.vt('wImpar', '{D1}'),
    'holiday_worked holiday_worked');
  perform pg_temp.assert_eq('8b. semana fixa que folgou no feriado: holiday (não recebe)',
    pg_temp.vt('wA', '{D1}'), 'holiday');
  perform pg_temp.assert_eq('8c. revezamento no feriado segue work, tenha ou não batido',
    pg_temp.vt('rotTrabalha', '{D1}') || ' ' || pg_temp.vt('rotFalta', '{D1}'), 'work work');
  perform pg_temp.assert_eq('8d. dia comum continua work (o holiday_worked não vaza)',
    pg_temp.vt('wA2', '{D3}'), 'work');
  -- As três que dão dentes ao critério "bateu NO feriado": cada uma derruba uma
  -- cláusula do `exists` de `_SCHEDULE_SQL` se ela virar `true`.
  perform pg_temp.assert_eq('8f. bateu em outros dias da janela, não no feriado: holiday',
    pg_temp.vt('wFolgaBate', '{D1}') || ' ' || pg_temp.vt('wFolgaBate', '{D2}'), 'holiday work');
  perform pg_temp.assert_eq('8g. só marcação desconsiderada no feriado: holiday',
    pg_temp.vt('wDescons', '{D1}'), 'holiday');
  perform pg_temp.assert_eq('8h. só a coluna sem hora no feriado: holiday',
    pg_temp.vt('wSemHora', '{D1}'), 'holiday');
  perform pg_temp.assert_eq('8e. a escala do VT não traz linha de outro tenant',
    (select count(*)::text from escala_vt e
       join app.employee c on c.id = e.employee_id where c.tenant_id <> '{T1}'), '0');
end $$;

-- ---------------------------------------------------------------------------
-- 9. O feriado que chega DEPOIS do relatório: o indício é revogado, não apagado
-- ---------------------------------------------------------------------------
insert into app.report_cycle (id, tenant_id, unit_id, period_start, period_end, status)
values ('f8300000-0000-0000-0000-0000000000c1', '{T1}', md5('fer-uB')::uuid,
        '{D4}', '{D4}', 'sent');
update app.deviation_event set report_cycle_id = 'f8300000-0000-0000-0000-0000000000c1'
 where employee_id = pg_temp.pessoa('wB') and reference_date = '{D4}' and type = 'no_punches';

do $$ begin
  -- O antes: sem ele o "foi revogado" abaixo poderia ser um evento que nunca existiu.
  perform pg_temp.assert_eq('9a. antes do feriado, D4 é falta de wB e já saiu em relatório',
    (select status || ' ' || (report_cycle_id is not null)::text from app.deviation_event
      where employee_id = pg_temp.pessoa('wB') and reference_date = '{D4}'
        and type = 'no_punches'), 'active true');
end $$;

create temporary table total_antes as
  select count(*) as n from app.deviation_event where tenant_id = '{T1}';

insert into app.holiday (tenant_id, reference_date, jurisdiction, unit_id, name)
values ('{T1}', '{D4}', 'national', null, 'Feriado Cadastrado Com Atraso');

-- O reprocessamento por data: jornada, detecção e a pergunta da revogação, só em D4.
{{JORNADA_D4}}
{{DETECCAO_D4}}
{{SUMIDOS_D4}}

do $$ begin
  perform pg_temp.assert_eq('9b. a jornada de D4 virou holiday',
    pg_temp.dia('wB', '{D4}'), 'holiday');
  perform pg_temp.assert_eq('9c. a detecção NÃO reescreveu o evento que saiu em relatório',
    (select status from app.deviation_event
      where employee_id = pg_temp.pessoa('wB') and reference_date = '{D4}'
        and type = 'no_punches'), 'active');
  perform pg_temp.assert_eq('9d. o revogador o encontra, e sabe que o motivo é o feriado',
    (select day_type from sumido
      where employee_id = pg_temp.pessoa('wB') and type = 'no_punches'), 'holiday');
  perform pg_temp.assert_eq('9e. todo no_punches de semana fixa em D4 sumiu (13), e só eles',
    (select count(*)::text from sumido where type = 'no_punches' and day_type = 'holiday')
      || '/' || (select count(*)::text from sumido), '13/13');
  -- A porta sancionada da regra 6.
  perform app.revoke_deviation(s.id, 'feriado cadastrado', 'revoked') from sumido s;
  perform pg_temp.assert_eq('9f. revogado, com o vínculo ao relatório preservado',
    (select status || ' ' || (report_cycle_id is not null)::text from app.deviation_event
      where employee_id = pg_temp.pessoa('wB') and reference_date = '{D4}'
        and type = 'no_punches'), 'revoked true');
  perform pg_temp.assert_eq('9g. nenhuma linha apagada',
    (select count(*)::text from app.deviation_event where tenant_id = '{T1}'),
    (select n::text from total_antes));
end $$;

-- ---------------------------------------------------------------------------
-- 10. O passo automático só refaz o feriado ESCRITO recentemente
-- ---------------------------------------------------------------------------
-- `_DATES_SQL` de `backend/operax/motor/feriados.py`, executado como está.
-- Todo feriado acima foi escrito agora. Mais três:
--   * um antigo, escrito há dez dias e nunca tocado — NÃO pode voltar;
--   * um antigo desativado agora — o trigger renova `updated_at`, e ele volta;
--   * um do vizinho, recente — não é deste tenant.
insert into app.holiday
  (tenant_id, reference_date, jurisdiction, unit_id, name, created_at, updated_at) values
  ('{T1}', '2026-08-14', 'national', null, 'Antigo Inalterado',
   now() - interval '10 days', now() - interval '10 days'),
  ('{T1}', '2026-08-17', 'national', null, 'Antigo Desativado Agora',
   now() - interval '10 days', now() - interval '10 days'),
  ('{T2}', '2026-08-18', 'national', null, 'Recente do Vizinho', now(), now());
update app.holiday set active = false
 where tenant_id = '{T1}' and reference_date = '2026-08-17';

{{DATAS_RECENTES}}

do $$ begin
  perform pg_temp.assert_eq('10a. o trigger renovou updated_at de quem foi desativado',
    (select (updated_at > now() - interval '1 minute')::text from app.holiday
      where tenant_id = '{T1}' and reference_date = '2026-08-17'), 'true');
  perform pg_temp.assert_eq('10b. refaz o recente e o desativado agora; não o antigo nem o do vizinho',
    (select string_agg(reference_date::text, ',' order by reference_date) from datas_recentes),
    '2026-08-10,2026-08-11,2026-08-12,2026-08-13,2026-08-17');
end $$;

rollback;
"""


_RUIDO = ("INSERT", "SELECT", "DO", "BEGIN", "ROLLBACK", "UPDATE", "CREATE")


def datas_recentes(inicio: str, fim: str) -> str:
    corpo = _extrai(
        "motor/feriados.py",
        "_DATES_SQL",
        ("%(tenant_id)s", "%(start)s", "%(end)s", "%(since)s"),
    )
    desde = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    ligado = _liga(
        corpo, {"tenant_id": T1, "start": inicio, "end": fim, "since": desde}
    )
    return f"create temporary table datas_recentes as {ligado};"


def main() -> None:
    script = (
        CENARIO.replace("{JORNADA_D1_D4}", jornada(D1, D4))
        .replace(
            "{DETECCAO_1}", deteccao("f8300000-0000-0000-0000-0000000000f1", D1, D4)
        )
        .replace(
            "{DETECCAO_2}", deteccao("f8300000-0000-0000-0000-0000000000f2", D1, D4)
        )
        .replace("{ESCALA_VT}", escala_vt(D1, D4))
        .replace("{JORNADA_D4}", jornada(D4, D4))
        .replace(
            "{DETECCAO_D4}", deteccao("f8300000-0000-0000-0000-0000000000f3", D4, D4)
        )
        .replace("{SUMIDOS_D4}", sumidos(D4, D4))
        .replace("{DATAS_RECENTES}", datas_recentes(D1, "2026-08-20"))
    )
    r = subprocess.run(
        ["psql", "-q", "-v", "ON_ERROR_STOP=1"],
        input=script,
        capture_output=True,
        text=True,
        env=ENV,
        check=False,
    )
    saida = "\n".join(
        linha
        for linha in (r.stdout + r.stderr).splitlines()
        if linha.strip() and not linha.startswith(_RUIDO)
    )
    print(saida)
    if r.returncode != 0:
        sys.exit(r.returncode)
    print("\n================================================")
    print(" O FERIADO NO MOTOR: TODOS OS TESTES OK")
    print("================================================")


if __name__ == "__main__":
    main()
