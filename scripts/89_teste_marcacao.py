#!/usr/bin/env python3
"""Prova a ponte entre a marcação da ingestão e o colaborador do domínio.

    python3 scripts/89_teste_marcacao.py

O SQL testado NÃO é digitado aqui: é o de `backend/operax/motor/marcacao.py`,
lido do módulo, do mesmo jeito que a suíte 94 faz com o motor de detecção.

POR QUE ISTO PRECISA DE UM BANCO DE VERDADE
A travessia é `app.batida_marcacao.funcionario_id` (uuid do espelho) →
`secullum."Funcionario"."FuncionarioId"` (bigint) → `app.employee`, e ela cruza
dois schemas e dois tipos de chave. Um teste com stub não a exercita: ele
compararia strings. O banco de desenvolvimento também não — ele tem `secullum`
com zero tabelas, que é justamente o outro caso provado aqui. Só a suíte de
banco, que aplica o baseline real, tem o espelho.

TRÊS AFIRMAÇÕES

1. A ponte encontra quem bateu. Se ela quebrar, o monitor conta zero e a tela
   diz "sem marcação" sobre gente que bateu ponto.
2. Ela não atravessa tenants. ⚠️ E a colisão precisa ser montada do lado do
   domínio, porque o espelho **não permite montá-la do lado dele**:
   `funcionario_funcionarioid_key` é `unique ("FuncionarioId")` — sem
   `tenant_id`. O espelho foi desenhado para um cliente só, o que é o mesmo
   problema já registrado sobre a credencial do Secullum, e é bom que apareça
   escrito aqui. Então a vizinha entra com o mesmo `secullum_employee_id` em
   `app.employee`, que é único por `(tenant_id, secullum_employee_id)` e aceita
   a repetição: sem `e.tenant_id = m.tenant_id` no join, a batida de uma
   apareceria como sendo da outra.
3. Coluna vazia e marcação desconsiderada não contam como marcação — as mesmas
   duas exclusões que `regras.py` aplica, porque contar aqui e não lá poria
   "com marcação" ao lado de `no_punches` sobre a mesma pessoa.

Roda em transação revertida.
"""

import os
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))
from operax.motor import marcacao  # noqa: E402

ENV = {
    **os.environ,
    "PGHOST": os.environ.get("PGHOST", "/tmp"),
    "PGPORT": os.environ.get("PGPORT", "5433"),
    "PGUSER": os.environ.get("PGUSER", "postgres"),
    "PGDATABASE": os.environ.get("PGDATABASE", "operax_test"),
}

TENANT = "eeeeeeee-0000-0000-0000-000000000001"
VIZINHO = "eeeeeeee-0000-0000-0000-000000000002"
DIA = "2026-08-11"


def ligar(corpo: str, **valores: str) -> str:
    """O SQL do módulo com os parâmetros ligados, como o psycopg o entregaria."""
    for nome, valor in valores.items():
        marca = f"%({nome})s"
        if marca not in corpo:
            sys.exit(f"o SQL de marcacao.py deixou de ligar {marca} — o teste ficou cego")
        corpo = corpo.replace(marca, f"'{valor}'")
    return corpo


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

insert into app.tenant (id, slug, name) values
  ('{TENANT}',  'marcacao-teste',  'Marcação'),
  ('{VIZINHO}', 'marcacao-vizinho', 'Vizinho');

-- `ativo` é coluna GERADA em produção (`coalesce(not "Desativada", true)`) e o
-- Postgres recusa escrita nela. Quem se grava é `"Desativada"`. Escrever `ativo`
-- passava enquanto a captura do espelho perdia a cláusula `generated`; desde
-- 01/09/2026 ela não perde mais.
insert into secullum."Empresa" (id, "EmpresaId", "Documento", "Nome", "Desativada", tenant_id) values
  ('eeeeeeee-0000-0000-0000-0000000000d1', 9600, '00000000000191', 'Marcação SA', false, '{TENANT}'),
  ('eeeeeeee-0000-0000-0000-0000000000d3', 9602, '00000000000272', 'Vizinha SA',  false, '{VIZINHO}');

insert into secullum."Departamento" (id, "DepartamentoId", empresa_id, "Descricao", tenant_id) values
  ('eeeeeeee-0000-0000-0000-0000000000d2', 9600, 'eeeeeeee-0000-0000-0000-0000000000d1', 'M-1', '{TENANT}'),
  ('eeeeeeee-0000-0000-0000-0000000000d4', 9602, 'eeeeeeee-0000-0000-0000-0000000000d3', 'V-1', '{VIZINHO}');

insert into app.company (id, tenant_id, legal_name, trade_name) values
  ('eeeeeeee-0000-0000-0000-0000000000e1', '{TENANT}',  'Marcação LTDA', 'M'),
  ('eeeeeeee-0000-0000-0000-0000000000e3', '{VIZINHO}', 'Vizinha LTDA',  'V');

-- No espelho os números são distintos, e não por escolha: `FuncionarioId` é
-- único GLOBALMENTE ali, sem tenant. A colisão vem logo abaixo, em app.employee.
insert into secullum."Funcionario"
  (id, "FuncionarioId", "Nome", empresa_id, departamento_id, tenant_id) values
  ('eeeeeeee-0000-0000-0000-0000000000f1', 9600, 'Alice',
   'eeeeeeee-0000-0000-0000-0000000000d1', 'eeeeeeee-0000-0000-0000-0000000000d2', '{TENANT}'),
  ('eeeeeeee-0000-0000-0000-0000000000f2', 9601, 'Bruno',
   'eeeeeeee-0000-0000-0000-0000000000d1', 'eeeeeeee-0000-0000-0000-0000000000d2', '{TENANT}'),
  ('eeeeeeee-0000-0000-0000-0000000000f3', 9602, 'Xavier',
   'eeeeeeee-0000-0000-0000-0000000000d3', 'eeeeeeee-0000-0000-0000-0000000000d4', '{VIZINHO}');

-- ⚠️ Xavier carrega o MESMO `secullum_employee_id` da Alice, de outro tenant. É
-- a colisão que o join tem de recusar, e ela é legítima: o único de app.employee
-- é por (tenant_id, secullum_employee_id).
insert into app.employee (id, tenant_id, company_id, secullum_employee_id, name) values
  ('eeeeeeee-0000-0000-0000-0000000000c1', '{TENANT}',  'eeeeeeee-0000-0000-0000-0000000000e1', 9600, 'Alice'),
  ('eeeeeeee-0000-0000-0000-0000000000c2', '{TENANT}',  'eeeeeeee-0000-0000-0000-0000000000e1', 9601, 'Bruno'),
  ('eeeeeeee-0000-0000-0000-0000000000c3', '{VIZINHO}', 'eeeeeeee-0000-0000-0000-0000000000e3', 9600, 'Xavier');

insert into secullum."Batida" (id, funcionario_id, "FuncionarioId", "Data", tenant_id) values
  ('eeeeeeee-0000-0000-0000-0000000000b1', 'eeeeeeee-0000-0000-0000-0000000000f1', 9600, '{DIA}', '{TENANT}'),
  ('eeeeeeee-0000-0000-0000-0000000000b2', 'eeeeeeee-0000-0000-0000-0000000000f2', 9601, '{DIA}', '{TENANT}'),
  ('eeeeeeee-0000-0000-0000-0000000000b3', 'eeeeeeee-0000-0000-0000-0000000000f3', 9602, '{DIA}', '{VIZINHO}');

-- Alice bateu. Bruno tem a coluna prevista e vazia — batida faltante, que NÃO é
-- marcação. Xavier, do vizinho, bateu e não pode aparecer para este tenant.
insert into app.batida_marcacao
  (batida_id, funcionario_id, data, tipo_coluna, indice_coluna, hora, "Memoria",
   desconsiderada, tenant_id) values
  ('eeeeeeee-0000-0000-0000-0000000000b1', 'eeeeeeee-0000-0000-0000-0000000000f1',
   '{DIA}', 'Entrada', 1, '08:02', '08:00', false, '{TENANT}'),
  ('eeeeeeee-0000-0000-0000-0000000000b1', 'eeeeeeee-0000-0000-0000-0000000000f1',
   '{DIA}', 'Saida',   1, '17:30', '17:00', true,  '{TENANT}'),
  ('eeeeeeee-0000-0000-0000-0000000000b2', 'eeeeeeee-0000-0000-0000-0000000000f2',
   '{DIA}', 'Entrada', 1, null,    '08:00', false, '{TENANT}'),
  ('eeeeeeee-0000-0000-0000-0000000000b3', 'eeeeeeee-0000-0000-0000-0000000000f3',
   '{DIA}', 'Entrada', 1, '07:55', '08:00', false, '{VIZINHO}');

-- ---------------------------------------------------------------------------
-- 1 e 2 — quem bateu, e só do tenant que perguntou
-- ---------------------------------------------------------------------------
create temporary table bateram on commit drop as
{{PUNCHED}};

select pg_temp.assert_eq(
  'a ponte encontra exatamente quem bateu',
  (select coalesce(string_agg(e.name, ',' order by e.name), '(ninguém)')
     from bateram b join app.employee e on e.id = b.employee_id),
  'Alice');

select pg_temp.assert_eq(
  'a colisão de secullum_employee_id entre tenants não atravessa',
  (select count(*)::text from bateram b
    join app.employee e on e.id = b.employee_id
   where e.tenant_id <> '{TENANT}'),
  '0');

-- ---------------------------------------------------------------------------
-- 3 — a coluna do dia, inclusive a vazia
-- ---------------------------------------------------------------------------
create temporary table colunas_alice on commit drop as
{{PUNCHES_ALICE}};

select pg_temp.assert_eq(
  'a marcação desconsiderada é devolvida, marcada',
  (select count(*) filter (where disregarded)::text from colunas_alice),
  '1');

create temporary table colunas_bruno on commit drop as
{{PUNCHES_BRUNO}};

select pg_temp.assert_eq(
  'a coluna prevista e vazia vira linha, em vez de sumir',
  (select coalesce(
     (select (punched_at is null and expected_time is not null)::text from colunas_bruno),
     'sem linha')),
  'true');

-- ---------------------------------------------------------------------------
-- A leitura, e o espelho que às vezes não existe
-- ---------------------------------------------------------------------------
insert into app.integration (id, tenant_id, provider, active) values
  ('eeeeeeee-0000-0000-0000-0000000000a1', '{TENANT}', 'secullum', true)
  on conflict do nothing;

insert into app.sync_run
  (tenant_id, integration_id, entity, status, finished_at, records_read, records_written)
values
  ('{TENANT}', 'eeeeeeee-0000-0000-0000-0000000000a1', 'Batida', 'completed',
   timestamptz '2026-08-11 09:15-03', 4, 4),
  ('{TENANT}', 'eeeeeeee-0000-0000-0000-0000000000a1', 'Batida', 'failed',
   timestamptz '2026-08-11 09:30-03', 0, 0),
  ('{TENANT}', 'eeeeeeee-0000-0000-0000-0000000000a1', 'Funcionario', 'completed',
   timestamptz '2026-08-11 23:00-03', 9, 9);

select pg_temp.assert_eq(
  'a leitura é a última de Batida CONCLUÍDA, não a última de todas',
  (select to_char(read_at at time zone 'America/Sao_Paulo', 'HH24:MI')
     from ({{READING}}) r),
  '09:15');

select pg_temp.assert_eq(
  'e o espelho está presente aqui, que é o que autoriza as consultas acima',
  (select mirror_present::text from ({{READING}}) r),
  'true');

rollback;
"""


def main() -> None:
    script = (
        CENARIO.replace("{PUNCHED}", ligar(marcacao.PUNCHED_EMPLOYEES_SQL, tenant_id=TENANT, dia=DIA))
        .replace(
            "{PUNCHES_ALICE}",
            ligar(
                marcacao.EMPLOYEE_PUNCHES_SQL,
                tenant_id=TENANT,
                employee_id="eeeeeeee-0000-0000-0000-0000000000c1",
                de=DIA,
                ate=DIA,
            ),
        )
        .replace(
            "{PUNCHES_BRUNO}",
            ligar(
                marcacao.EMPLOYEE_PUNCHES_SQL,
                tenant_id=TENANT,
                employee_id="eeeeeeee-0000-0000-0000-0000000000c2",
                de=DIA,
                ate=DIA,
            ),
        )
        .replace("{READING}", ligar(marcacao.PUNCH_READING_SQL, tenant_id=TENANT))
    )
    r = subprocess.run(
        ["psql", "-q", "-v", "ON_ERROR_STOP=1"],
        input=script,
        capture_output=True,
        text=True,
        env=ENV,
    )
    # O resultado de `select pg_temp.assert_eq(...)` é uma tabela vazia por
    # asserção. O que interessa é o NOTICE que a função emite.
    ruido = re.compile(r"^(\s*assert_eq\s*|-+|\(\d+ rows?\))$")
    saida = "\n".join(
        linha
        for linha in (r.stdout + r.stderr).splitlines()
        if linha.strip()
        and not ruido.match(linha)
        and not linha.startswith(("INSERT", "SELECT", "DO", "BEGIN", "ROLLBACK", "UPDATE", "CREATE"))
    )
    print(saida)
    if r.returncode != 0:
        sys.exit(r.returncode)
    print("\n================================================")
    print(" PONTE DA MARCAÇÃO: TODOS OS TESTES OK")
    print("================================================")


if __name__ == "__main__":
    main()
