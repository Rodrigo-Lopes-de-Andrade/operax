#!/usr/bin/env python3
"""A justificativa sobrevive a um reprocessamento do motor.

    python3 scripts/teste_justificativa_sobrevive.py

`docs/DECISAO-ALCADA-APROVACAO.md` §3 pediu este teste como
`teste_justificativa_sobrevive.sql`. Ele é um driver `.py` pelo mesmo motivo do
`94_teste_deteccao.py`: o que está sob teste é o `DETECT_SQL` de
`backend/operax/motor/regras.py`, e um `.sql` puro só alcançaria uma CÓPIA dele —
que continuaria verde com o motor quebrado. Aqui o SQL é importado do módulo e
ligado aos parâmetros como o psycopg o entregaria.

As quatro linhas da §3, uma por passo:

    | Passo                                   | Resultado                  |
    |-----------------------------------------|----------------------------|
    | Motor roda                              | 1 linha active/40          |
    | Motor roda de novo                      | 1 linha active/45          |
    | Supervisor justifica                    | 1 linha justified/45       |
    | Motor roda depois da justificativa      | 1 linha justified/45 — e   |
    |                                         | NENHUMA active nova        |

A quarta é a que nenhuma revisão de código pega: os índices únicos do motor são
parciais em `status = 'active'`, a linha justificada sai deles, e o `on conflict`
deixa de ter com quem conflitar.

Cada cláusula do `not exists` do conserto tem um caso que a derruba se ela virar
`true` — provado por mutação em 28/09/2026:

    j.status = 'accepted'               (b) rejeitada não cala o motor
    j_event.status = 'justified'        (a) aceita com evento active é reescrita,
                                        e (e) aceita sobre revogado — que é o que
                                        separa `= 'justified'` de `<> 'active'`
    j_event.type = e.type               (c) outro tipo no mesmo dia
    j_event.reference_date = ...        (d) outro dia da mesma pessoa
    j_event.mode = %(mode)s             (5) sombra não cala produção

Desde a P1.2 a justificativa nasce `pending` e a aprovação é linha em
`app.justification_review` — a justificativa continua `pending` depois de
aprovada. O filtro aceita `accepted` (legada) OU revisão `approved`:

    revisão approved                    (g) congela — o ramo da revisão
    r.decision = 'approved'             (h) revisão rejected NÃO congela
    pending sem revisão                 (f) NÃO congela: esperar o RH não é
                                        decisão

`j.tenant_id` fica SEM caso, de propósito: `j_event.employee_id = e.employee_id`
já implica o tenant, então nenhum cenário distingue a cláusula de `true`. Ela
está lá pela regra 4 (nenhuma consulta sem filtro de tenant), não pelo resultado.

Roda em transação revertida. Pessoas e ids são sintéticos.
"""

import importlib
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
# Mesmo mecanismo do 94: `regras` não importa driver, então o python do sistema
# carrega exatamente o SQL que o motor executa.
sys.path.insert(0, str(RAIZ / "backend"))
regras = importlib.import_module("operax.motor.regras")

ENV = {
    **os.environ,
    "PGHOST": os.environ.get("PGHOST", "/tmp"),
    "PGPORT": os.environ.get("PGPORT", "5433"),
    "PGUSER": os.environ.get("PGUSER", "postgres"),
    "PGDATABASE": os.environ.get("PGDATABASE", "operax_test"),
}

TENANT = "eeeeeeee-0000-0000-0000-000000000001"
DIA = "2026-08-10"
DIA2 = "2026-08-11"  # só a pessoa 1 trabalha nele, e nele ninguém justificou nada
NOW = "2026-08-12 12:00:00"  # os turnos dos dois dias já fecharam


def motor(run_id: str, mode: str = "shadow") -> str:
    corpo = regras.DETECT_SQL
    for marca in ("%(tenant_id)s", "%(start)s", "%(end)s", "%(mode)s", "%(now)s", "%(run_id)s"):
        if marca not in corpo:
            sys.exit(f"o SQL do motor deixou de ligar {marca} — o teste ficou cego")
    corpo = corpo.replace("%(tenant_id)s", f"'{TENANT}'")
    corpo = corpo.replace("%(start)s", f"'{DIA}'").replace("%(end)s", f"'{DIA2}'")
    corpo = corpo.replace("%(mode)s", f"'{mode}'").replace("%(run_id)s", f"'{run_id}'")
    corpo = corpo.replace("%(now)s", f"'{NOW}'")
    return f"""
insert into app.detection_run (id, tenant_id, mode, period_start, period_end)
values ('{run_id}', '{TENANT}', '{mode}', '{DIA}', '{DIA2}');
{corpo.replace("%%", "%")};
"""


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

-- As linhas de uma pessoa, num dia, tipo e modo, como `status/minutos`.
create or replace function pg_temp.linhas(
  p_n int, p_mode text, p_type text default 'late_exit', p_dia date default '{DIA}'
)
returns text language sql as $$
  select coalesce(string_agg(status || '/' || minutes, ' + ' order by status, minutes),
                  '(nenhuma)')
  from app.deviation_event
  where employee_id = md5('jus-c' || p_n)::uuid and type = p_type and mode = p_mode
    and reference_date = p_dia;
$$;

insert into app.tenant (id, slug, name) values ('{TENANT}', 'justificativa-teste', 'Justificativa');

insert into secullum."Empresa"
  (id, "EmpresaId", "Documento", "Nome", "Desativada", tenant_id)
values ('eeeeeeee-0000-0000-0000-0000000000d1', 9700, '00000000000272',
        'Justificativa SA', false, '{TENANT}');
insert into secullum."Departamento"
  (id, "DepartamentoId", empresa_id, "Descricao", tenant_id)
values ('eeeeeeee-0000-0000-0000-0000000000d2', 9700,
        'eeeeeeee-0000-0000-0000-0000000000d1', 'J-999', '{TENANT}');
insert into app.company (id, tenant_id, legal_name, trade_name) values
  ('eeeeeeee-0000-0000-0000-0000000000e1', '{TENANT}', 'Justificativa LTDA', 'J');
insert into app.unit (id, tenant_id, company_id, code, name) values
  ('eeeeeeee-0000-0000-0000-00000000ac01', '{TENANT}',
   'eeeeeeee-0000-0000-0000-0000000000e1', 'J1', 'J Um');

-- Quatro pessoas, cada uma por um caso:
--   1 — justificada e movida para `justified` (a §3); também trabalha em DIA2
--   2 — o controle, ninguém justificou
--   3 — justificativa aceita e evento ainda `active` (o caminho da rota de hoje)
--   4 — justificativa REJEITADA sobre evento movido para `justified`
--   5 — justificativa aceita sobre evento REVOGADO (não justificado)
--   6 — justificativa PENDENTE, sem revisão, sobre evento `justified`
--   7 — justificativa pendente com revisão APROVADA (o caminho da alçada)
--   8 — justificativa pendente com revisão REPROVADA sobre evento `justified`
insert into secullum."Funcionario"
  (id, "FuncionarioId", "Nome", empresa_id, departamento_id, tenant_id)
select md5('jus-f' || n)::uuid, 9700 + n, 'Pessoa Sintetica ' || n,
       'eeeeeeee-0000-0000-0000-0000000000d1', 'eeeeeeee-0000-0000-0000-0000000000d2', '{TENANT}'
from generate_series(1, 8) n;

insert into app.employee (id, tenant_id, company_id, unit_id, secullum_employee_id, name)
select md5('jus-c' || n)::uuid, '{TENANT}', 'eeeeeeee-0000-0000-0000-0000000000e1',
       'eeeeeeee-0000-0000-0000-00000000ac01', 9700 + n, 'Pessoa Sintetica ' || n
from generate_series(1, 8) n;

create temporary table dia_de (n int, dia date) on commit drop;
insert into dia_de select n, '{DIA}' from generate_series(1, 8) n;
insert into dia_de values (1, '{DIA2}');

-- 08:00 às 18:00 sem intervalo, carga 600 e tolerância extra 10: a mesma saída
-- produz dois tipos, `late_exit` e `workday_exceeded`, e o segundo é o que prova
-- que a justificativa de um tipo não cala o outro.
insert into app.expected_workday
  (tenant_id, employee_id, reference_date, day_type, expected_entry, expected_exit,
   expected_break_minutes, workload_minutes, tolerance_extra_minutes,
   tolerance_absence_minutes, source, confidence)
select '{TENANT}', md5('jus-c' || d.n)::uuid, d.dia, 'work', '08:00', '18:00',
       null, 600, 10, 5, 'secullum_schedule', 100
from dia_de d;

insert into secullum."Batida" (id, funcionario_id, "FuncionarioId", "Data", tenant_id)
select md5('jus-b' || d.n || d.dia)::uuid, md5('jus-f' || d.n)::uuid, 9700 + d.n, d.dia,
       '{TENANT}'
from dia_de d;

-- Saída às 18:40: 40 minutos além das 18:00.
insert into app.batida_marcacao
  (batida_id, funcionario_id, data, tipo_coluna, indice_coluna, hora, "FonteDadosId",
   desconsiderada, tenant_id)
select md5('jus-b' || d.n || d.dia)::uuid, md5('jus-f' || d.n)::uuid, d.dia, t.tipo, 1,
       t.hora, (d.n * 1000 + extract(day from d.dia) * 10 + t.ord)::bigint, false, '{TENANT}'
from dia_de d
cross join (values ('Entrada', time '08:00', 1), ('Saida', time '18:40', 2)) t(tipo, hora, ord);

-- ---------------------------------------------------------------------------
-- 1. Motor roda
-- ---------------------------------------------------------------------------
{{MOTOR1}}

do $$ begin
  perform pg_temp.assert_eq('1. motor roda: uma linha active/40',
    pg_temp.linhas(1, 'shadow'), 'active/40');
end $$;

-- ---------------------------------------------------------------------------
-- 2. Motor roda de novo, com a saída corrigida na origem para 18:45
-- ---------------------------------------------------------------------------
update app.batida_marcacao set hora = '18:45'
 where tenant_id = '{TENANT}' and tipo_coluna = 'Saida';

{{MOTOR2}}

do $$ begin
  perform pg_temp.assert_eq('2. motor roda de novo: reescreve, não duplica',
    pg_temp.linhas(1, 'shadow'), 'active/45');
end $$;

-- ---------------------------------------------------------------------------
-- 3. Os vereditos, todos sobre o `late_exit` de DIA
-- ---------------------------------------------------------------------------
insert into app.justification
  (tenant_id, deviation_event_id, employee_id, reference_date, text, status, source, author_name)
select '{TENANT}', d.id, d.employee_id, d.reference_date,
       'Texto sintetico de justificativa', v.status, 'operax', 'Supervisor Sintetico'
from app.deviation_event d
join (values (1, 'accepted'), (3, 'accepted'), (4, 'rejected'), (5, 'accepted'),
             (6, 'pending'), (7, 'pending'), (8, 'pending')) v(n, status)
  on d.employee_id = md5('jus-c' || v.n)::uuid
where d.type = 'late_exit' and d.reference_date = '{DIA}' and d.status = 'active';

-- A porta sancionada da regra 6 — para a 1 e a 4. A 3 fica `active`, como a
-- rota `POST /ocorrencias/{{id}}/justificativa` deixa hoje.
do $$ begin
  perform app.revoke_deviation(d.id, 'justificado pelo supervisor', 'justified')
  from app.deviation_event d
  where d.employee_id in (md5('jus-c1')::uuid, md5('jus-c4')::uuid, md5('jus-c6')::uuid,
                          md5('jus-c7')::uuid, md5('jus-c8')::uuid)
    and d.type = 'late_exit' and d.reference_date = '{DIA}' and d.status = 'active';
  -- A 5 é revogada, não justificada: o fato some e depois reaparece. Uma
  -- justificativa aceita não pode trancar um evento que não saiu como julgado.
  perform app.revoke_deviation(d.id, 'batida corrigida na origem', 'revoked')
  from app.deviation_event d
  where d.employee_id = md5('jus-c5')::uuid
    and d.type = 'late_exit' and d.reference_date = '{DIA}' and d.status = 'active';
end $$;

-- A alçada (P1.2): a revisão é linha nova, e a justificativa continua `pending`.
-- Inserida direto — a RPC que a escreve é provada no `98`; aqui o que está sob
-- teste é o filtro do motor.
insert into auth.users (id, email) values
  ('eeeeeeee-0000-0000-0000-0000000000a9', 'rh.sintetico@teste');
insert into app.payroll_period (id, tenant_id, year, month) values
  ('eeeeeeee-0000-0000-0000-0000000000a8', '{TENANT}', 2026, 8);
insert into app.justification_review
  (tenant_id, justification_id, payroll_period_id, decision, reason, reviewed_by)
select '{TENANT}', j.id, 'eeeeeeee-0000-0000-0000-0000000000a8', v.decision, 'Motivo sintetico',
       'eeeeeeee-0000-0000-0000-0000000000a9'
from app.justification j
join (values (7, 'approved'), (8, 'rejected')) v(n, decision)
  on j.employee_id = md5('jus-c' || v.n)::uuid;

do $$ begin
  perform pg_temp.assert_eq('3. supervisor justifica: uma linha justified/45',
    pg_temp.linhas(1, 'shadow'), 'justified/45');
end $$;

-- ---------------------------------------------------------------------------
-- 4. A batida muda outra vez (saída 18:50), e o motor roda depois dos vereditos
-- ---------------------------------------------------------------------------
-- Mudar a batida é o que dá dentes a cada caso abaixo: uma linha `active` que o
-- motor deixasse de alcançar ficaria em 45, e só o 50 prova que ele a alcançou.
update app.batida_marcacao set hora = '18:50'
 where tenant_id = '{TENANT}' and tipo_coluna = 'Saida';

{{MOTOR3}}

do $$ begin
  perform pg_temp.assert_eq('4. motor depois da justificativa: não recria o que foi julgado',
    pg_temp.linhas(1, 'shadow'), 'justified/45');
  perform pg_temp.assert_eq('   quem ninguém justificou continua detectado',
    pg_temp.linhas(2, 'shadow'), 'active/50');
  perform pg_temp.assert_eq('a) aceita com o evento ainda active: os minutos são reescritos',
    pg_temp.linhas(3, 'shadow'), 'active/50');
  perform pg_temp.assert_eq('b) rejeitada sobre evento justified: o motor ainda emite',
    pg_temp.linhas(4, 'shadow'), 'active/50 + justified/45');
  perform pg_temp.assert_eq('c) outro tipo no mesmo dia não é calado pela justificativa',
    pg_temp.linhas(1, 'shadow', 'workday_exceeded'), 'active/40');
  perform pg_temp.assert_eq('d) outro dia, sem justificativa, continua detectado',
    pg_temp.linhas(1, 'shadow', 'late_exit', '{DIA2}'), 'active/50');
  perform pg_temp.assert_eq('e) aceita sobre evento revogado: o fato que reaparece volta',
    pg_temp.linhas(5, 'shadow'), 'active/50 + revoked/45');
  perform pg_temp.assert_eq('f) pendente sem revisão: esperar o RH não congela',
    pg_temp.linhas(6, 'shadow'), 'active/50 + justified/45');
  perform pg_temp.assert_eq('g) revisão aprovada congela: o motor não recria',
    pg_temp.linhas(7, 'shadow'), 'justified/45');
  perform pg_temp.assert_eq('h) revisão reprovada não congela',
    pg_temp.linhas(8, 'shadow'), 'active/50 + justified/45');
end $$;

-- ---------------------------------------------------------------------------
-- 5. O modo é parte do grão: a justificativa foi dada ao indício em sombra, e
--    não fala pelo de produção — que é outro evento, com outro público.
-- ---------------------------------------------------------------------------
{{MOTOR4}}

do $$ begin
  perform pg_temp.assert_eq('5. justificativa em sombra não cala a produção',
    pg_temp.linhas(1, 'production'), 'active/50');
end $$;

rollback;
"""


_RUIDO = ("INSERT", "SELECT", "DO", "BEGIN", "ROLLBACK", "UPDATE", "CREATE")


def main() -> None:
    script = (
        CENARIO.replace("{MOTOR1}", motor("eeeeeeee-0000-0000-0000-0000000000f1"))
        .replace("{MOTOR2}", motor("eeeeeeee-0000-0000-0000-0000000000f2"))
        .replace("{MOTOR3}", motor("eeeeeeee-0000-0000-0000-0000000000f3"))
        .replace("{MOTOR4}", motor("eeeeeeee-0000-0000-0000-0000000000f4", mode="production"))
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
    print(" A JUSTIFICATIVA SOBREVIVE AO MOTOR: TODOS OS TESTES OK")
    print("================================================")


if __name__ == "__main__":
    main()
