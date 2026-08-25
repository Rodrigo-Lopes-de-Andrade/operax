#!/usr/bin/env python3
"""Prova o ciclo de relatório: um desvio em exatamente um ciclo.

    python3 scripts/93_teste_ciclo.py

Duas coisas em uma. Primeiro compila **toda** instrução fixa de `operax/alertas/`
contra o schema real — `prepare` analisa e planeja sem executar, que é o que pega
coluna errada e join inválido antes de a primeira mensagem sair. Depois roda o
cenário funcional da reserva, que é a garantia que o produto vende: o mesmo
desvio não pode entrar em dois relatórios, e o desvio detectado tarde não pode
ficar de fora do próximo.

O SQL é lido dos módulos em vez de copiado: os três puxam o driver e este teste
roda fora do venv, e uma cópia à mão divergiria na primeira alteração — que é
sempre a cópia do teste.
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

TENANT = "eeeeeeee-0000-0000-0000-000000000001"
HOJE = "2026-08-24"
ANTES = "2026-08-10"  # a ocorrência detectada tarde, anterior ao início do ciclo

MODULOS = ("ciclo.py", "outbox.py", "sender.py")


def instrucoes() -> list[tuple[str, str]]:
    achadas: list[tuple[str, str]] = []
    for modulo in MODULOS:
        fonte = (RAIZ / "backend" / "operax" / "alertas" / modulo).read_text()
        achadas += re.findall(r'^(_?[A-Z][A-Z_]*_SQL) = """(.*?)"""', fonte, re.S | re.M)
    return achadas


def posicionar(sql: str) -> str:
    """`%(nome)s` do psycopg vira `$n` do Postgres, na ordem de aparição."""
    ordem: list[str] = []

    def trocar(m: re.Match) -> str:
        if m.group(1) not in ordem:
            ordem.append(m.group(1))
        return f"${ordem.index(m.group(1)) + 1}"

    return re.sub(r"%\((\w+)\)s", trocar, sql)


def psql(argumentos: list[str], entrada: str | None = None):
    return subprocess.run(
        ["psql", "-q", "-v", "ON_ERROR_STOP=1", *argumentos],
        input=entrada,
        capture_output=True,
        text=True,
        env=ENV,
    )


def ligar(sql: str, **valores: str) -> str:
    for nome, valor in valores.items():
        sql = sql.replace(f"%({nome})s", f"'{valor}'")
    return sql


CENARIO = """
begin;

create or replace function pg_temp.assert_eq(rotulo text, obtido text, esperado text)
returns void language plpgsql as $$
begin
  if obtido is distinct from esperado then
    raise exception 'FALHA [%]: esperado %, obtido %', rotulo, esperado, obtido;
  end if;
  raise notice '  ok  % (%)', rotulo, obtido;
end $$;

insert into app.tenant (id, slug, name) values ('{TENANT}', 'ciclo-teste', 'Ciclo')
  on conflict do nothing;

insert into app.company (id, tenant_id, legal_name, trade_name) values
  ('eeeeeeee-0000-0000-0000-0000000000e1', '{TENANT}', 'Ciclo LTDA', 'C');

-- Duas unidades: uma com regra ligada, outra sem. A segunda não pode ganhar
-- ciclo — e, mais importante, os desvios dela não podem ser reservados.
insert into app.unit (id, tenant_id, company_id, code, name, active) values
  ('eeeeeeee-0000-0000-0000-00000000ac01', '{TENANT}', 'eeeeeeee-0000-0000-0000-0000000000e1', 'C1', 'Com Regra', true),
  ('eeeeeeee-0000-0000-0000-00000000ac02', '{TENANT}', 'eeeeeeee-0000-0000-0000-0000000000e1', 'C2', 'Sem Regra', true);

insert into app.employee (id, tenant_id, company_id, unit_id, name) values
  ('eeeeeeee-0000-0000-0000-0000000000c1', '{TENANT}', 'eeeeeeee-0000-0000-0000-0000000000e1', 'eeeeeeee-0000-0000-0000-00000000ac01', 'Com Regra Um'),
  ('eeeeeeee-0000-0000-0000-0000000000c2', '{TENANT}', 'eeeeeeee-0000-0000-0000-0000000000e1', 'eeeeeeee-0000-0000-0000-00000000ac02', 'Sem Regra Um');

-- A regra é recortada na unidade 1. Com `scope_unit_id` nulo ela cobriria todas,
-- que é o padrão do produto — aqui o recorte é o próprio caso sob teste.
insert into app.alert_rule (id, tenant_id, name, content, channel, active, scope_unit_id) values
  ('eeeeeeee-0000-0000-0000-0000000000a1', '{TENANT}', 'Resumo diário', 'aggregate', 'whatsapp',
   true, 'eeeeeeee-0000-0000-0000-00000000ac01');

-- Um ciclo já enviado na semana passada: é dele que sai o início do próximo.
insert into app.report_cycle (id, tenant_id, unit_id, period_start, period_end, status)
values ('eeeeeeee-0000-0000-0000-0000000000d1', '{TENANT}',
        'eeeeeeee-0000-0000-0000-00000000ac01', '2026-08-11', '2026-08-17', 'sent');

-- ---------------------------------------------------------------------------
-- Os desvios. Cada linha existe por um caso.
-- ---------------------------------------------------------------------------
insert into app.deviation_event
  (id, tenant_id, employee_id, company_id, unit_id, reference_date, type, minutes,
   mode, status, report_cycle_id)
values
  -- dentro do período novo, livre: entra
  ('eeeeeeee-0000-0000-0000-00000000e001', '{TENANT}', 'eeeeeeee-0000-0000-0000-0000000000c1',
   'eeeeeeee-0000-0000-0000-0000000000e1', 'eeeeeeee-0000-0000-0000-00000000ac01',
   '2026-08-20', 'late_entry', -26, 'production', 'active', null),
  ('eeeeeeee-0000-0000-0000-00000000e002', '{TENANT}', 'eeeeeeee-0000-0000-0000-0000000000c1',
   'eeeeeeee-0000-0000-0000-0000000000e1', 'eeeeeeee-0000-0000-0000-00000000ac01',
   '2026-08-21', 'late_exit', 23, 'production', 'active', null),
  -- detectado tarde: é de antes do início do ciclo e TEM que entrar
  ('eeeeeeee-0000-0000-0000-00000000e003', '{TENANT}', 'eeeeeeee-0000-0000-0000-0000000000c1',
   'eeeeeeee-0000-0000-0000-0000000000e1', 'eeeeeeee-0000-0000-0000-00000000ac01',
   '{ANTES}', 'no_punches', -540, 'production', 'active', null),
  -- já reservado num ciclo enviado: não pode sair de lá
  ('eeeeeeee-0000-0000-0000-00000000e004', '{TENANT}', 'eeeeeeee-0000-0000-0000-0000000000c1',
   'eeeeeeee-0000-0000-0000-0000000000e1', 'eeeeeeee-0000-0000-0000-00000000ac01',
   '2026-08-12', 'late_entry', -15, 'production', 'active',
   'eeeeeeee-0000-0000-0000-0000000000d1'),
  -- sombra: o relatório é de produção
  ('eeeeeeee-0000-0000-0000-00000000e005', '{TENANT}', 'eeeeeeee-0000-0000-0000-0000000000c1',
   'eeeeeeee-0000-0000-0000-0000000000e1', 'eeeeeeee-0000-0000-0000-00000000ac01',
   '2026-08-22', 'early_exit', -68, 'shadow', 'active', null),
  -- revogado: não se relata o que deixou de valer
  ('eeeeeeee-0000-0000-0000-00000000e006', '{TENANT}', 'eeeeeeee-0000-0000-0000-0000000000c1',
   'eeeeeeee-0000-0000-0000-0000000000e1', 'eeeeeeee-0000-0000-0000-00000000ac01',
   '2026-08-23', 'break_exceeded', -31, 'production', 'revoked', null),
  -- unidade sem regra: não entra em ciclo nenhum
  ('eeeeeeee-0000-0000-0000-00000000e007', '{TENANT}', 'eeeeeeee-0000-0000-0000-0000000000c2',
   'eeeeeeee-0000-0000-0000-0000000000e1', 'eeeeeeee-0000-0000-0000-00000000ac02',
   '2026-08-20', 'late_entry', -10, 'production', 'active', null);

-- ---------------------------------------------------------------------------
-- A montagem
-- ---------------------------------------------------------------------------
create temporary table unidades on commit drop as
{UNITS};

do $$ begin
  perform pg_temp.assert_eq('só a unidade com regra ligada monta ciclo',
    (select string_agg(unit_name, ',' order by unit_name) from unidades), 'Com Regra');
  perform pg_temp.assert_eq('o período começa no dia seguinte ao último ciclo',
    (select period_start::text from unidades), '2026-08-18');
end $$;

insert into app.report_cycle (id, tenant_id, unit_id, period_start, period_end, status)
select 'eeeeeeee-0000-0000-0000-0000000000d2', '{TENANT}', u.unit_id, u.period_start, '{HOJE}', 'open'
from unidades u;

create temporary table reservados on commit drop as
with r as ({RESERVE}) select * from r;

-- ---------------------------------------------------------------------------
-- A garantia
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('a reserva pega três: as duas do período e a atrasada',
    (select count(*)::text from reservados), '3');
  perform pg_temp.assert_eq('a ocorrência detectada tarde entra no ciclo novo',
    (select count(*)::text from reservados where reference_date = '{ANTES}'), '1');
  perform pg_temp.assert_eq('o que já estava num ciclo continua nele',
    (select report_cycle_id::text from app.deviation_event
      where id = 'eeeeeeee-0000-0000-0000-00000000e004'),
    'eeeeeeee-0000-0000-0000-0000000000d1');
  perform pg_temp.assert_eq('a sombra não vai para relatório',
    (select coalesce(report_cycle_id::text, '(nenhum)') from app.deviation_event
      where id = 'eeeeeeee-0000-0000-0000-00000000e005'), '(nenhum)');
  perform pg_temp.assert_eq('o revogado não vai para relatório',
    (select coalesce(report_cycle_id::text, '(nenhum)') from app.deviation_event
      where id = 'eeeeeeee-0000-0000-0000-00000000e006'), '(nenhum)');
  perform pg_temp.assert_eq('a unidade sem regra fica intocada',
    (select coalesce(report_cycle_id::text, '(nenhum)') from app.deviation_event
      where id = 'eeeeeeee-0000-0000-0000-00000000e007'), '(nenhum)');
end $$;

-- ---------------------------------------------------------------------------
-- Exatamente um: reservar de novo não move nada
-- ---------------------------------------------------------------------------
create temporary table segunda on commit drop as
with r as ({RESERVE2}) select * from r;

do $$ begin
  perform pg_temp.assert_eq('reservar de novo não pega ninguém',
    (select count(*)::text from segunda), '0');
  perform pg_temp.assert_eq('e nenhum desvio está em dois ciclos',
    (select count(*)::text from (
       select id from app.deviation_event
        where tenant_id = '{TENANT}' and report_cycle_id is not null
        group by id having count(distinct report_cycle_id) > 1) t), '0');
end $$;

rollback;
"""


def main() -> None:
    problemas: list[str] = []
    fixas = instrucoes()
    if len(fixas) < 8:
        problemas.append(f"esperava ao menos 8 instruções fixas de alerta, achei {len(fixas)}")
    for nome, sql in fixas:
        r = psql(["-c", f"prepare p as {posicionar(sql)}"])
        if r.returncode != 0:
            problemas.append(f"{nome} não compila: {r.stderr.strip().splitlines()[0]}")

    if problemas:
        for p in problemas:
            print(f"  ✖ {p}")
        sys.exit(1)
    print(f"  instruções fixas de alerta compiladas: {len(fixas)}")

    por_nome = dict(fixas)
    reserva = ligar(
        por_nome["_RESERVE_SQL"],
        tenant_id=TENANT,
        cycle_id="eeeeeeee-0000-0000-0000-0000000000d2",
        unit_id="eeeeeeee-0000-0000-0000-00000000ac01",
        ate=HOJE,
    )
    script = (
        CENARIO.replace("{TENANT}", TENANT)
        .replace("{HOJE}", HOJE)
        .replace("{ANTES}", ANTES)
        .replace("{UNITS}", ligar(por_nome["_UNITS_SQL"], tenant_id=TENANT, ate=HOJE))
        .replace("{RESERVE2}", reserva)
        .replace("{RESERVE}", reserva)
    )

    r = psql([], script)
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
    print(" CICLO DE RELATÓRIO: TODOS OS TESTES OK")
    print("================================================")


if __name__ == "__main__":
    main()
