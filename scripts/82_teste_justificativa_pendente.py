#!/usr/bin/env python3
"""`pending` existe, e o espelho do Secullum não consegue pender.

    python3 scripts/82_teste_justificativa_pendente.py

Gate da P1.1 (`docs/SPRINTS-ALCADA.md`), `docs/DECISAO-ALCADA-APROVACAO.md` §4.1.
Dois blocos, e o primeiro é o que importa:

  A. A TRAVA DO ESPELHO, no banco já migrado. `source='secullum'` já foi decidido
     no registro oficial: nascer pendente — pedido ou pelo default — é recusado
     pelo `check`, não por código que alguém tenha de lembrar. Ao lado, os
     positivos: `operax` pende (e pende por default), `secullum` aceito entra.

  B. NADA VIRA PENDENTE RETROATIVAMENTE. O banco volta ao estado que a migration
     23 deixou (check sem `pending`, default `accepted`), recebe linhas escritas
     sob aquele estado — inclusive as que tomaram o default —, e a migration desta
     sprint é aplicada POR CIMA delas, duas vezes. Cada linha tem de sair como
     entrou. É o arquivo real de `supabase/migrations/` que roda aqui, não uma
     cópia: uma cópia continuaria verde com um `update` retroativo no original.

Roda em transação revertida. Tenant, pessoa e textos são sintéticos.
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

TENANT = "82000000-0000-0000-0000-000000000001"
COMPANY = "82000000-0000-0000-0000-0000000000e1"
EMPLOYEE = "82000000-0000-0000-0000-0000000000c1"

# `p_status` nulo = a coluna omitida, que é o único jeito de alcançar o default.
CABECALHO = f"""
begin;

create or replace function pg_temp.assert_eq(rotulo text, obtido text, esperado text)
returns void language plpgsql as $$
begin
  if obtido is distinct from esperado then
    raise exception 'FALHA [%]: esperado %, obtido %', rotulo, esperado, obtido;
  end if;
  raise notice '  ok  % (%)', rotulo, obtido;
end $$;

create or replace function pg_temp.insere(p_source text, p_status text)
returns app.justification language plpgsql as $$
declare v app.justification;
begin
  if p_status is null then
    insert into app.justification
      (tenant_id, employee_id, reference_date, text, source, author_name)
    values ('{TENANT}', '{EMPLOYEE}', '2026-08-10', 'Texto sintetico', p_source,
            'Autor Sintetico')
    returning * into v;
  else
    insert into app.justification
      (tenant_id, employee_id, reference_date, text, source, author_name, status)
    values ('{TENANT}', '{EMPLOYEE}', '2026-08-10', 'Texto sintetico', p_source,
            'Autor Sintetico', p_status)
    returning * into v;
  end if;
  return v;
end $$;

-- O que o banco respondeu: o status gravado, ou o nome do `check` que recusou.
create or replace function pg_temp.grava(p_source text, p_status text)
returns text language plpgsql as $$
declare v_check text;
begin
  return 'entrou:' || (pg_temp.insere(p_source, p_status)).status;
exception when check_violation then
  get stacked diagnostics v_check = constraint_name;
  return 'recusado:' || v_check;
end $$;

insert into app.tenant (id, slug, name) values ('{TENANT}', 'pendente-teste', 'Pendente');
insert into app.company (id, tenant_id, legal_name, trade_name)
values ('{COMPANY}', '{TENANT}', 'Pendente LTDA', 'P');
insert into app.employee (id, tenant_id, company_id, secullum_employee_id, name)
values ('{EMPLOYEE}', '{TENANT}', '{COMPANY}', 98201, 'Pessoa Sintetica');
"""

TRAVA = (
    CABECALHO
    + """
do $$ begin
  -- O gate, primeiro: é o que o schema anterior não sustenta.
  perform pg_temp.assert_eq('A1. secullum pedindo pending: o banco recusa',
    pg_temp.grava('secullum', 'pending'), 'recusado:justification_espelho_nao_pende');
  perform pg_temp.assert_eq('A2. secullum sem status: o default pending é recusado',
    pg_temp.grava('secullum', null), 'recusado:justification_espelho_nao_pende');
  perform pg_temp.assert_eq('A3. secullum rejected: o OperaX não reprova a origem',
    pg_temp.grava('secullum', 'rejected'), 'recusado:justification_espelho_nao_pende');

  -- Os positivos ao lado: sem eles, um check que recusasse tudo passaria acima.
  perform pg_temp.assert_eq('A4. operax pending entra',
    pg_temp.grava('operax', 'pending'), 'entrou:pending');
  perform pg_temp.assert_eq('A5. operax sem status nasce pending',
    pg_temp.grava('operax', null), 'entrou:pending');
  perform pg_temp.assert_eq('A6. whatsapp pending entra',
    pg_temp.grava('whatsapp', 'pending'), 'entrou:pending');
  perform pg_temp.assert_eq('A7. secullum accepted entra',
    pg_temp.grava('secullum', 'accepted'), 'entrou:accepted');

  -- O domínio continua fechado: `pending` entrou, não "qualquer coisa".
  perform pg_temp.assert_eq('A8. status fora do domínio segue recusado',
    pg_temp.grava('operax', 'approved'), 'recusado:justification_status_check');
end $$;

rollback;
"""
)

RETROATIVO = (
    CABECALHO
    + """
-- O estado que a migration 23 deixou, reconstruído dentro da transação.
alter table app.justification drop constraint if exists justification_espelho_nao_pende;
alter table app.justification drop constraint if exists justification_status_check;
alter table app.justification
  add constraint justification_status_check check (status in ('accepted','rejected'));
alter table app.justification alter column status set default 'accepted';

-- Linhas escritas sob aquele estado. As que omitem o status são as que a troca
-- de default "levaria junto" se a migration tivesse um `update` retroativo.
create temporary table antes (rotulo text, source text, pedido text, id uuid, status text)
  on commit drop;
insert into antes (rotulo, source, pedido) values
  ('operax aceita explícita',      'operax',   'accepted'),
  ('operax rejeitada',             'operax',   'rejected'),
  ('operax pelo default antigo',   'operax',   null),
  ('secullum pelo default antigo', 'secullum', null),
  ('whatsapp pelo default antigo', 'whatsapp', null);

with gravada as (
  select s.rotulo, j.id, j.status
  from antes s cross join lateral pg_temp.insere(s.source, s.pedido) j
)
update antes a set id = g.id, status = g.status from gravada g where g.rotulo = a.rotulo;

do $$ begin
  perform pg_temp.assert_eq('B0. antes da migration: nenhuma pendente, rejeitada preservada',
    (select string_agg(status, ',' order by rotulo) from antes),
    'accepted,accepted,rejected,accepted,accepted');
end $$;

{MIGRATION}

create or replace function pg_temp.confere(p_passada text) returns void
language plpgsql as $$
begin
  perform pg_temp.assert_eq(p_passada || ': toda linha antiga sai como entrou',
    (select string_agg(a.rotulo || '=' || j.status, '; ' order by a.rotulo)
       from antes a join app.justification j on j.id = a.id),
    (select string_agg(a.rotulo || '=' || a.status, '; ' order by a.rotulo) from antes a));
  perform pg_temp.assert_eq(p_passada || ': nenhuma linha antiga virou pending',
    (select count(*)::text from app.justification j join antes a on a.id = j.id
      where j.status = 'pending'), '0');
  perform pg_temp.assert_eq(p_passada || ': linha nova operax, sem status, nasce pending',
    pg_temp.grava('operax', null), 'entrou:pending');
end $$;

do $$ begin perform pg_temp.confere('B1. primeira aplicação'); end $$;

{MIGRATION}

do $$ begin perform pg_temp.confere('B2. segunda aplicação (idempotência)'); end $$;

rollback;
"""
)

_RUIDO = ("INSERT", "SELECT", "DO", "BEGIN", "ROLLBACK", "UPDATE", "CREATE", "ALTER", "COMMENT")


def roda(rotulo: str, script: str) -> None:
    print(f"--- {rotulo}")
    r = subprocess.run(
        ["psql", "-q", "-v", "ON_ERROR_STOP=1"],
        input=script,
        capture_output=True,
        text=True,
        env=ENV,
        cwd=RAIZ,
        check=False,
    )
    print(
        "\n".join(
            linha
            for linha in (r.stdout + r.stderr).splitlines()
            if linha.strip() and not linha.startswith(_RUIDO)
        )
    )
    if r.returncode != 0:
        sys.exit(r.returncode)


def main() -> None:
    roda("A. a trava do espelho, no banco migrado", TRAVA)

    achadas = sorted((RAIZ / "supabase" / "migrations").glob("*_alcada_justification_pending.sql"))
    if len(achadas) != 1:
        sys.exit(f"esperava uma migration alcada_justification_pending, achei {len(achadas)}")
    migration = achadas[0]
    # Guarda estática ao lado da prova viva: o que a sprint proíbe, nomeado.
    if re.search(r"\bupdate\s+app\.justification\b", migration.read_text(), re.IGNORECASE):
        sys.exit(f"{migration.name} tem `update app.justification` — retroativo é proibido")

    roda(
        "B. a migration aplicada por cima de linhas já escritas",
        # O texto do arquivo real, embutido: `\\i` exigiria que o psql enxergasse o
        # caminho do host, e o wrapper local só enxerga o repo montado.
        RETROATIVO.replace("{MIGRATION}", migration.read_text()),
    )

    print("\n================================================")
    print(" PENDING EXISTE E O ESPELHO NÃO PENDE: TODOS OS TESTES OK")
    print("================================================")


if __name__ == "__main__":
    main()
