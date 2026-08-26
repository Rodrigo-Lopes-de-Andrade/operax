#!/usr/bin/env python3
"""Prova a promoção do espelho para o domínio — e a regra 5, que é o motivo dela.

    python3 scripts/92_teste_cadastro.py

Cerca de 26% do quadro da FastPark está num departamento que pertence a uma
empresa diferente da do próprio colaborador. Derivar a empresa pelo caminho
`Departamento → Empresa` põe um quarto da folha na empresa errada, de forma
consistente e invisível — este cenário tem esse caso e é ele que a asserção mais
importante olha.

O SQL é lido de `backend/operax/motor/cadastro.py`, não copiado: o módulo puxa o
driver e este teste roda fora do venv. Roda em transação revertida.
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

TENANT = "ffffffff-0000-0000-0000-000000000001"


def instrucoes() -> dict[str, str]:
    fonte = (RAIZ / "backend" / "operax" / "motor" / "cadastro.py").read_text()
    achadas = dict(re.findall(r'^(_[A-Z][A-Z_]*_SQL) = """(.*?)"""', fonte, re.S | re.M))
    for nome in (
        "_COMPANIES_SQL",
        "_DEPARTMENTS_SQL",
        "_MANAGERS_SQL",
        "_EMPLOYEES_SQL",
        "_PENDING_SQL",
    ):
        if nome not in achadas:
            sys.exit(f"não encontrei {nome} em backend/operax/motor/cadastro.py")
    return {n: s.replace("%(tenant_id)s", f"'{TENANT}'") for n, s in achadas.items()}


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

insert into app.tenant (id, slug, name) values ('{TENANT}', 'cadastro-teste', 'Cadastro')
  on conflict do nothing;

-- Duas empresas no espelho, e um departamento que pertence à primeira.
insert into secullum."Empresa" (id, "EmpresaId", "Documento", "Nome", ativo, tenant_id) values
  ('ffffffff-0000-0000-0000-0000000000e1', 7001, '11.222.333/0001-81', 'Empresa A', true, '{TENANT}'),
  ('ffffffff-0000-0000-0000-0000000000e2', 7002, '44.555.666/0001-72', 'Empresa B', true, '{TENANT}');

insert into secullum."Departamento" (id, "DepartamentoId", empresa_id, "Descricao", tenant_id) values
  ('ffffffff-0000-0000-0000-0000000000d1', 7101, 'ffffffff-0000-0000-0000-0000000000e1', 'Pátio Centro', '{TENANT}'),
  ('ffffffff-0000-0000-0000-0000000000d2', 7102, 'ffffffff-0000-0000-0000-0000000000e1', 'Pátio Norte', '{TENANT}');

insert into secullum."Funcao" (id, "FuncaoId", "Descricao", tenant_id) values
  ('ffffffff-0000-0000-0000-0000000000fa', 7201, 'Manobrista', '{TENANT}');

-- O gestor, como o Secullum o guarda: uma "Estrutura" cuja Descricao é nome de
-- pessoa. Duas delas, e a segunda existe para provar que cada um vai para a
-- estrutura DELE e não para a primeira que aparecer.
insert into secullum."Estrutura"
  (id, "EstruturaId", "EstruturaPaiId", departamento_id, "Descricao", ativo, tenant_id) values
  ('ffffffff-0000-0000-0000-00000000e5a1', 7401, null,
   'ffffffff-0000-0000-0000-0000000000d1', 'Helena Prado', true, '{TENANT}'),
  ('ffffffff-0000-0000-0000-00000000e5a2', 7402, null,
   'ffffffff-0000-0000-0000-0000000000d2', 'Ivo Ramalho', true, '{TENANT}');

-- F2 é o caso que a regra 5 existe para pegar: o departamento é da Empresa A e
-- a pessoa é da Empresa B.
insert into secullum."Funcionario"
  (id, "FuncionarioId", "Nome", "NumeroFolha", "Admissao", "Demissao",
   empresa_id, departamento_id, funcao_id, "EstruturaId", tenant_id)
values
  ('ffffffff-0000-0000-0000-0000000000a1', 7301, 'Alice Mapeada', '00001', '2024-03-01', null,
   'ffffffff-0000-0000-0000-0000000000e1', 'ffffffff-0000-0000-0000-0000000000d1',
   'ffffffff-0000-0000-0000-0000000000fa', 7401, '{TENANT}'),
  ('ffffffff-0000-0000-0000-0000000000a2', 7302, 'Bruno Empresa B', '00002', '2024-04-01', null,
   'ffffffff-0000-0000-0000-0000000000e2', 'ffffffff-0000-0000-0000-0000000000d1',
   null, 7402, '{TENANT}'),
  -- Sem estrutura no espelho: o Secullum não diz a quem ela responde, e o
  -- ranking por gestor tem de mostrá-la como "sem gestor" em vez de escondê-la.
  ('ffffffff-0000-0000-0000-0000000000a3', 7303, 'Carla Sem Mapa', '00003', '2024-05-01', null,
   'ffffffff-0000-0000-0000-0000000000e1', 'ffffffff-0000-0000-0000-0000000000d2',
   null, null, '{TENANT}'),
  ('ffffffff-0000-0000-0000-0000000000a4', 7304, 'Davi Desligado', '00004', '2023-01-01', '2026-06-30',
   'ffffffff-0000-0000-0000-0000000000e1', 'ffffffff-0000-0000-0000-0000000000d2',
   null, null, '{TENANT}');

-- ---------------------------------------------------------------------------
-- Primeira promoção: ainda sem unidade nenhuma cadastrada
-- ---------------------------------------------------------------------------
{COMPANIES};
{DEPARTMENTS};
{MANAGERS};
{EMPLOYEES};

do $$ begin
  perform pg_temp.assert_eq('as duas empresas do espelho viram empresa do domínio',
    (select count(*)::text from app.company where tenant_id = '{TENANT}'), '2');
  perform pg_temp.assert_eq('o CNPJ entra só com dígito',
    (select cnpj from app.company where tenant_id = '{TENANT}' and secullum_company_id = 7001),
    '11222333000181');
  perform pg_temp.assert_eq('os quatro colaboradores foram promovidos',
    (select count(*)::text from app.employee where tenant_id = '{TENANT}'), '4');
  perform pg_temp.assert_eq('sem unidade cadastrada, ninguém ganha lotação',
    (select count(*)::text from app.employee
      where tenant_id = '{TENANT}' and unit_id is not null), '0');
end $$;

-- ---------------------------------------------------------------------------
-- A) regra 5: a empresa vem da pessoa, nunca do departamento
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('quem é da Empresa B fica na Empresa B, mesmo num departamento da A',
    (select c.legal_name from app.employee e
      join app.company c on c.id = e.company_id
     where e.tenant_id = '{TENANT}' and e.secullum_employee_id = 7302), 'Empresa B');
  perform pg_temp.assert_eq('e o departamento dele continua sendo o da Empresa A',
    (select d.name from app.employee e
      join app.department d on d.id = e.department_id
     where e.tenant_id = '{TENANT}' and e.secullum_employee_id = 7302), 'Pátio Centro');
  perform pg_temp.assert_eq('quem é da A fica na A',
    (select c.legal_name from app.employee e
      join app.company c on c.id = e.company_id
     where e.tenant_id = '{TENANT}' and e.secullum_employee_id = 7301), 'Empresa A');
end $$;

-- ---------------------------------------------------------------------------
-- B) status e cargo saem do espelho
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('demissão preenchida vira desligado',
    (select status || ' ' || terminated_on::text from app.employee
      where tenant_id = '{TENANT}' and secullum_employee_id = 7304), 'desligado 2026-06-30');
  perform pg_temp.assert_eq('quem não tem demissão fica ativo',
    (select status from app.employee
      where tenant_id = '{TENANT}' and secullum_employee_id = 7301), 'active');
  perform pg_temp.assert_eq('a função do espelho vira o cargo',
    (select cargo from app.employee
      where tenant_id = '{TENANT}' and secullum_employee_id = 7301), 'Manobrista');
  -- ⛔ `manager_employee_id` aponta para um `app.employee`, e o espelho não diz
  --    QUAL colaborador é o gestor — só o nome dele. Casar nome resolveu zero de
  --    quatro em produção, e um vínculo adivinhado não se distingue de um lido.
  perform pg_temp.assert_eq('qual colaborador É o gestor continua sem resposta',
    (select count(*)::text from app.employee
      where tenant_id = '{TENANT}' and manager_employee_id is not null), '0');
end $$;

-- ---------------------------------------------------------------------------
-- B2) o gestor que o espelho DE FATO tem: "Estrutura"
-- ---------------------------------------------------------------------------
do $$ begin
  perform pg_temp.assert_eq('as duas estruturas viram gestores, com o nome do espelho',
    (select string_agg(name, ', ' order by name) from app.manager
      where tenant_id = '{TENANT}'), 'Helena Prado, Ivo Ramalho');
  -- Cada um vai para a estrutura DELE. Se o join caísse na primeira que
  -- aparecesse, os dois teriam a mesma chefia e o ranking somaria errado.
  perform pg_temp.assert_eq('cada pessoa responde à estrutura dela',
    (select g.name from app.employee e join app.manager g on g.id = e.manager_id
      where e.tenant_id = '{TENANT}' and e.secullum_employee_id = 7301), 'Helena Prado');
  perform pg_temp.assert_eq('e a outra, à outra',
    (select g.name from app.employee e join app.manager g on g.id = e.manager_id
      where e.tenant_id = '{TENANT}' and e.secullum_employee_id = 7302), 'Ivo Ramalho');
  -- Sem estrutura no espelho é nulo, não é a estrutura do departamento: derivar
  -- a chefia do departamento inventaria uma hierarquia que a origem não afirmou.
  perform pg_temp.assert_eq('sem estrutura no espelho, sem gestor',
    (select count(*)::text from app.employee
      where tenant_id = '{TENANT}' and secullum_employee_id = 7303
        and manager_id is null), '1');
end $$;

-- ---------------------------------------------------------------------------
-- C) a curadoria: mapear o departamento aloca quem depende dele
-- ---------------------------------------------------------------------------
insert into app.unit (id, tenant_id, company_id, code, name)
select 'ffffffff-0000-0000-0000-00000000ac01', '{TENANT}', c.id, 'U1', 'Unidade Centro'
from app.company c where c.tenant_id = '{TENANT}' and c.secullum_company_id = 7001;

insert into app.unit_secullum_map (tenant_id, secullum_department_id, unit_id, validated_at)
values ('{TENANT}', 7101, 'ffffffff-0000-0000-0000-00000000ac01', now());

{EMPLOYEES};

do $$ begin
  perform pg_temp.assert_eq('mapear o departamento aloca os dois que dependiam dele',
    (select count(*)::text from app.employee
      where tenant_id = '{TENANT}' and unit_id = 'ffffffff-0000-0000-0000-00000000ac01'), '2');
  -- E a unidade não vem da empresa da pessoa: quem é da Empresa B também é
  -- alocado, porque unidade é lotação física e o mapa é por departamento.
  perform pg_temp.assert_eq('inclusive quem é de outra empresa',
    (select unit_id::text from app.employee
      where tenant_id = '{TENANT}' and secullum_employee_id = 7302),
    'ffffffff-0000-0000-0000-00000000ac01');
end $$;

-- ---------------------------------------------------------------------------
-- D) a fila de pendência — o aceite do S1
-- ---------------------------------------------------------------------------
create temporary table pendencia on commit drop as
{PENDING};

do $$ begin
  perform pg_temp.assert_eq('a fila nomeia o departamento e o peso dele',
    (select department || ': ' || employees::text from pendencia), 'Pátio Norte: 1');
  perform pg_temp.assert_eq('o desligado não entra na fila de curadoria',
    (select count(*)::text from pendencia where employees > 1), '0');
end $$;

-- ---------------------------------------------------------------------------
-- E) promover de novo não duplica, e não desfaz curadoria
-- ---------------------------------------------------------------------------
-- Alguém alocou a Carla à mão, e depois o mapeamento do departamento dela foi
-- removido. A promoção seguinte não pode apagar o trabalho humano.
update app.employee set unit_id = 'ffffffff-0000-0000-0000-00000000ac01'
 where tenant_id = '{TENANT}' and secullum_employee_id = 7303;
delete from app.unit_secullum_map where tenant_id = '{TENANT}' and secullum_department_id = 7101;

-- E alguém tirou o Bruno do motor: supervisão, ponto por exceção. É decisão
-- humana, e a sincronização roda a cada 30 minutos por cima dela.
update app.employee set exception_tracking = true
 where tenant_id = '{TENANT}' and secullum_employee_id = 7302;

{COMPANIES};
{DEPARTMENTS};
{MANAGERS};
{EMPLOYEES};

do $$ begin
  perform pg_temp.assert_eq('promover de novo não duplica ninguém',
    (select count(*)::text from app.employee where tenant_id = '{TENANT}'), '4');
  perform pg_temp.assert_eq('nem duplica empresa ou departamento',
    (select (select count(*) from app.company where tenant_id = '{TENANT}')::text || '/' ||
            (select count(*) from app.department where tenant_id = '{TENANT}')::text), '2/2');
  perform pg_temp.assert_eq('a lotação feita à mão sobrevive ao mapa removido',
    (select unit_id::text from app.employee
      where tenant_id = '{TENANT}' and secullum_employee_id = 7303),
    'ffffffff-0000-0000-0000-00000000ac01');
  -- ⛔ O `do update set` da promoção lista as colunas uma a uma, então uma coluna
  --    nova sobrevive sozinha. Isso é propriedade do SQL de hoje e não do
  --    schema: no dia em que alguém trocar a lista por `excluded.*`, a
  --    sincronização passa a repor seis supervisores dentro do motor a cada
  --    trinta minutos, sem erro nenhum e sem ninguém ver.
  perform pg_temp.assert_eq('quem foi tirado do motor continua fora depois da promoção',
    (select exception_tracking::text from app.employee
      where tenant_id = '{TENANT}' and secullum_employee_id = 7302), 'true');
end $$;

rollback;
"""


def main() -> None:
    sql = instrucoes()
    script = CENARIO.replace("{TENANT}", TENANT)
    for marca, nome in (
        ("{COMPANIES}", "_COMPANIES_SQL"),
        ("{DEPARTMENTS}", "_DEPARTMENTS_SQL"),
        ("{MANAGERS}", "_MANAGERS_SQL"),
        ("{EMPLOYEES}", "_EMPLOYEES_SQL"),
        ("{PENDING}", "_PENDING_SQL"),
    ):
        script = script.replace(marca, sql[nome])

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
        and not linha.startswith(
            ("INSERT", "SELECT", "DO", "BEGIN", "ROLLBACK", "UPDATE", "CREATE", "DELETE")
        )
    )
    print(saida)
    if r.returncode != 0:
        sys.exit(r.returncode)
    print("\n================================================")
    print(" PROMOÇÃO DO ESPELHO: TODOS OS TESTES OK")
    print("================================================")


if __name__ == "__main__":
    main()
