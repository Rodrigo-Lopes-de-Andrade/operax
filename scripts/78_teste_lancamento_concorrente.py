#!/usr/bin/env python3
"""O lock de `public.fn_marcar_lancado`, com duas sessões de verdade.

    ENSAIO_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55322/operax_test \\
      uv run --no-sync --project backend python scripts/78_teste_lancamento_concorrente.py

⛔ POR QUE ESTE NÃO ESTÁ NO `98`
O `98` é uma transação só, numa sessão só: nada nele espera por lock nenhum, e
`now()` é o mesmo instante do começo ao fim. A RPC sem o `for update` passa nele
inteira. O que está sob teste aqui é o que acontece ENTRE duas sessões.

Três perguntas, todas com a sessão 1 (o RH) segurando a marca sem commit:

1. **Quem não é `hr`/`owner` não espera.** O supervisor recebe `not_hr` na hora,
   e o RH de OUTRO tenant recebe `review_not_found` na hora — com `lock_timeout`
   curto, esperar pela linha vira erro `55P03`. Se esperassem, o tempo de
   resposta diria que o id existe.
2. **A segunda marcação espera a primeira** — e, quando a primeira confirma,
   recebe `already_posted`. Sem o lock ela leria `posted_to_source_at` nulo
   antes do commit da primeira e SOBRESCREVERIA quem lançou: a marca deixaria
   de ser "uma vez só" sem erro nenhum.
3. **Fica a marca da primeira**, com o autor da primeira.
"""

from __future__ import annotations

import os
import sys
import threading
import time

import psycopg

DSN = os.environ.get("ENSAIO_DATABASE_URL")
if not DSN:
    print("  ✖ defina ENSAIO_DATABASE_URL com o DSN do banco de ensaio")
    raise SystemExit(1)

TENANT_A = "78000000-0000-0000-0000-000000000001"
TENANT_B = "78000000-0000-0000-0000-000000000002"
HR_A = "78000000-0000-0000-0000-0000000000f1"
SUP_A = "78000000-0000-0000-0000-0000000000f2"
HR_B = "78000000-0000-0000-0000-0000000000f3"
OWNER_A = "78000000-0000-0000-0000-0000000000f4"
COMPANY = "78000000-0000-0000-0000-0000000000c1"
EMPLOYEE = "78000000-0000-0000-0000-0000000000e1"
PERIOD = "78000000-0000-0000-0000-0000000000d1"
JUST = "78000000-0000-0000-0000-00000000a001"
REVIEW = "78000000-0000-0000-0000-00000000b001"

_LIMPAR = f"""
delete from app.justification_review where tenant_id = '{TENANT_A}';
delete from app.justification where tenant_id = '{TENANT_A}';
delete from app.payroll_period where tenant_id = '{TENANT_A}';
delete from app.employee where tenant_id = '{TENANT_A}';
delete from app.company where tenant_id = '{TENANT_A}';
delete from app.tenant_member where tenant_id in ('{TENANT_A}', '{TENANT_B}');
delete from app.tenant where id in ('{TENANT_A}', '{TENANT_B}');
delete from auth.users where id in ('{HR_A}', '{SUP_A}', '{HR_B}', '{OWNER_A}');
"""

# A revisão aprovada entra como `postgres`: o que está sob teste é a marca, e a
# revisão pela RPC já tem o `81`.
_CADASTRO = f"""
insert into auth.users (id, email) values
  ('{HR_A}', 'rh.a.p14@teste'), ('{SUP_A}', 'sup.a.p14@teste'),
  ('{HR_B}', 'rh.b.p14@teste'), ('{OWNER_A}', 'owner.a.p14@teste');
insert into app.tenant (id, slug, name) values
  ('{TENANT_A}', 'p14-lock-a', 'P14 A'), ('{TENANT_B}', 'p14-lock-b', 'P14 B');
insert into app.tenant_member (tenant_id, user_id, role) values
  ('{TENANT_A}', '{HR_A}', 'hr'),
  ('{TENANT_A}', '{OWNER_A}', 'owner'),
  ('{TENANT_A}', '{SUP_A}', 'unit_supervisor'),
  ('{TENANT_B}', '{HR_B}', 'hr');
insert into app.company (id, tenant_id, legal_name, trade_name)
  values ('{COMPANY}', '{TENANT_A}', 'P14 LTDA', 'P14');
insert into app.employee (id, tenant_id, company_id, name)
  values ('{EMPLOYEE}', '{TENANT_A}', '{COMPANY}', 'P14 Colaborador');
insert into app.payroll_period (id, tenant_id, year, month, status)
  values ('{PERIOD}', '{TENANT_A}', 2026, 9, 'importada');
insert into app.justification
  (id, tenant_id, deviation_event_id, employee_id, reference_date, text, status, source)
values ('{JUST}', '{TENANT_A}', null, '{EMPLOYEE}', '2026-09-01', 'P14', 'pending', 'operax');
insert into app.justification_review
  (id, tenant_id, justification_id, payroll_period_id, decision, reviewed_by)
values ('{REVIEW}', '{TENANT_A}', '{JUST}', '{PERIOD}', 'approved', '{OWNER_A}');
"""

falhas: list[str] = []


def igual(rotulo: str, obtido: object, esperado: object) -> None:
    if obtido != esperado:
        falhas.append(f"{rotulo}: esperado {esperado!r}, obtido {obtido!r}")
        print(f"  ✖ {rotulo}: esperado {esperado!r}, obtido {obtido!r}")
    else:
        print(f"  ok  {rotulo} ({obtido!r})")


def controle(texto: str) -> list[tuple]:
    with psycopg.connect(DSN, autocommit=True) as conexao, conexao.cursor() as cur:
        cur.execute(texto)
        return cur.fetchall() if cur.description else []


def sessao(usuario: str) -> psycopg.Connection:
    """Uma conexão que fala como `usuario`, fora de transação."""
    conexao = psycopg.connect(DSN, autocommit=True)
    conexao.execute("set role authenticated")
    conexao.execute("select set_config('request.jwt.claim.sub', %s, false)", (usuario,))
    return conexao


def lanca(conexao: psycopg.Connection) -> str:
    """O que a RPC respondeu: 'ok', ou `sqlstate:mensagem`."""
    try:
        conexao.execute("select public.fn_marcar_lancado(%s)", (REVIEW,))
        return "ok"
    except psycopg.Error as erro:
        return f"{erro.sqlstate}:{erro.diag.message_primary}"


controle(_LIMPAR)
controle(_CADASTRO)

s1 = sessao(HR_A)
s2 = sessao(OWNER_A)
sup = sessao(SUP_A)
rh_b = sessao(HR_B)
try:
    # A sessão 1 marca e NÃO confirma: segura o lock da linha.
    s1.autocommit = False
    igual("sessão 1 (RH) marca lançado (sem commit ainda)", lanca(s1), "ok")

    # 1. Quem não alcança a revisão não espera por ela.
    for conexao in (sup, rh_b):
        conexao.execute("set lock_timeout = '300ms'")
    igual("supervisor, com a linha travada: not_hr na hora", lanca(sup), "P0001:not_hr")
    igual(
        "RH de outro tenant, com a linha travada: review_not_found na hora",
        lanca(rh_b),
        "P0001:review_not_found",
    )

    # 2. A segunda marcação da mesma espera, e depois vê a primeira.
    pid_s2 = s2.info.backend_pid
    resposta: dict[str, str] = {}
    fio = threading.Thread(target=lambda: resposta.update(s2=lanca(s2)))
    fio.start()
    esperando = False
    prazo = time.monotonic() + 10
    while time.monotonic() < prazo and fio.is_alive():
        linha = controle(f"select wait_event_type from pg_stat_activity where pid = {pid_s2}")
        if linha and linha[0][0] == "Lock":
            esperando = True
            break
        time.sleep(0.05)
    igual("a sessão 2 (owner) ficou esperando a sessão 1", esperando, True)
    s1.commit()
    fio.join(10)
    igual(
        "a sessão 2, depois do commit da 1: already_posted",
        resposta.get("s2"),
        "P0001:already_posted",
    )

    # 3.
    igual(
        "a marca é a da sessão 1: posted_by é o RH, não o owner",
        controle(
            f"select posted_by::text, posted_to_source_at is not null "
            f"from app.justification_review where id = '{REVIEW}'"
        ),
        [(HR_A, True)],
    )
finally:
    for conexao in (s1, s2, sup, rh_b):
        conexao.close()
    controle(_LIMPAR)

igual(
    "o teste não deixou rastro",
    controle(f"select count(*) from app.tenant where id in ('{TENANT_A}', '{TENANT_B}')")[0][0],
    0,
)

print()
if falhas:
    print(f"  ✖ {len(falhas)} FALHA(S)")
    sys.exit(1)
print("================================================")
print(" LANÇAMENTO CONCORRENTE (P1.4): TODOS OS TESTES OK")
print("================================================")
