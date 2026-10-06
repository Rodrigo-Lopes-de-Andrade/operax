#!/usr/bin/env python3
"""The tenant lock of the user RPCs (sprint U2), with two real sessions.

    ENSAIO_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55322/operax_test \\
      uv run --no-sync --project backend python scripts/teste_usuarios_concorrencia.py

WHY THIS IS NOT IN `teste_usuarios_rpc.sql`
That file is one transaction in one session: nothing in it waits for a lock,
and the four RPCs without `for no key update` pass it whole. What is under
test here happens BETWEEN two sessions.

Tenant with two owners, O1 and O2, and an hr. Session 1 (O1) demotes O2 and
does NOT commit. Then:

1. O2, in session 2, demotes O1 — it waits for session 1, and after the commit
   gets `not_owner`: the role check runs after the lock, and O2 is no longer
   owner. Without the lock both demotions pass on stale snapshots and the
   tenant ends with ZERO owners.
2. Same opening, but O2 deactivates O1 — it waits, and after the commit is
   no longer owner and gets `owner_so_por_owner` (only an owner deactivates an
   owner, owner decision of 05/10). Without the lock: zero owners again.
3. In both, the tenant ends with exactly one active owner.
4. While session 1 holds the tenant row, the owner of ANOTHER tenant calls the
   four RPCs with a short `lock_timeout` and gets the role refusal at once:
   membership is checked before the lock, so an outsider neither waits for
   nor holds another tenant's row. With the check after the lock, the call
   waits and dies on `55P03`.
5. TWO TENANTS INVITING THE SAME PERSON (U3 review, P2; owner decision of
   05/10: one customer per user). Session 1 (the hr of the tenant) invites NEW
   and does NOT commit; session 2 (the owner of the other tenant) invites the
   same NEW. The tenant lock does not order them — each takes its own tenant —
   so what makes session 2 wait is the per-user advisory lock, and after the
   commit its check sees the membership and refuses `conta_em_outro_cliente`.
   NEW ends with exactly one active membership. Without the advisory lock both
   `exists` run on snapshots that cannot see the other, both insert, and NEW
   ends active in two tenants — locked out of both.
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

TENANT = "d2c00000-0000-0000-0000-0000000000a1"
OUTRO = "d2c00000-0000-0000-0000-0000000000a2"
O1 = "d2c00000-0000-0000-0000-000000000001"
O2 = "d2c00000-0000-0000-0000-000000000002"
HR = "d2c00000-0000-0000-0000-000000000003"
XO = "d2c00000-0000-0000-0000-000000000004"
NEW = "d2c00000-0000-0000-0000-000000000005"
EMPRESA = "d2c00000-0000-0000-0000-0000000000c1"
EMPRESA_X = "d2c00000-0000-0000-0000-0000000000c2"

_LIMPAR = f"""
delete from app.audit_log where tenant_id in ('{TENANT}', '{OUTRO}');
delete from app.user_scope where tenant_id in ('{TENANT}', '{OUTRO}');
delete from app.tenant_member where tenant_id in ('{TENANT}', '{OUTRO}');
delete from app.company where tenant_id in ('{TENANT}', '{OUTRO}');
delete from app.tenant where id in ('{TENANT}', '{OUTRO}');
delete from auth.users where id in ('{O1}', '{O2}', '{HR}', '{XO}', '{NEW}');
"""

_CADASTRO = f"""
insert into auth.users (id, email) values
  ('{O1}', 'o1.u2c@teste'), ('{O2}', 'o2.u2c@teste'), ('{HR}', 'hr.u2c@teste'),
  ('{XO}', 'xo.u2c@teste'), ('{NEW}', 'new.u2c@teste');
insert into app.tenant (id, slug, name) values
  ('{TENANT}', 'u2-corrida', 'U2 corrida'), ('{OUTRO}', 'u2-corrida-x', 'U2 corrida X');
insert into app.tenant_member (tenant_id, user_id, role) values
  ('{TENANT}', '{O1}', 'owner'), ('{TENANT}', '{O2}', 'owner'), ('{TENANT}', '{HR}', 'hr'),
  ('{OUTRO}', '{XO}', 'owner');
insert into app.company (id, tenant_id, legal_name) values
  ('{EMPRESA}', '{TENANT}', 'U2 corrida LTDA'), ('{EMPRESA_X}', '{OUTRO}', 'U2 corrida X LTDA');
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
    """A connection that speaks as `usuario`, outside a transaction."""
    conexao = psycopg.connect(DSN, autocommit=True)
    conexao.execute("set role authenticated")
    conexao.execute("select set_config('request.jwt.claim.sub', %s, false)", (usuario,))
    return conexao


def chama(conexao: psycopg.Connection, sql: str, params: tuple) -> str:
    """What the RPC answered: 'ok', or `sqlstate:message`."""
    try:
        conexao.execute(sql, params)
        return "ok"
    except psycopg.Error as erro:
        return f"{erro.sqlstate}:{erro.diag.message_primary}"


def owners_ativos() -> int:
    return controle(
        f"select count(*) from app.tenant_member "
        f"where tenant_id = '{TENANT}' and role = 'owner' and active"
    )[0][0]


def corrida(rotulo: str, segundo: str, sql: str, params: tuple, esperado: str) -> None:
    controle(_LIMPAR)
    controle(_CADASTRO)
    s1 = sessao(O1)
    s2 = sessao(segundo)
    try:
        s1.autocommit = False
        igual(
            f"[{rotulo}] sessão 1: O1 rebaixa O2 (sem commit ainda)",
            chama(
                s1,
                "select public.fn_definir_papel(%s, %s, 'hr')",
                (TENANT, O2),
            ),
            "ok",
        )
        # 4. The outsider, with the row held: refused at once, never waiting.
        if rotulo == "dois owners":
            fora = sessao(XO)
            try:
                fora.execute("set lock_timeout = '300ms'")
                for sql_fora, params_fora, codigo in (
                    (
                        "select public.fn_definir_papel(%s, %s, 'owner')",
                        (TENANT, XO),
                        "not_owner",
                    ),
                    (
                        "select public.fn_desativar_membro(%s, %s)",
                        (TENANT, O1),
                        "not_admin",
                    ),
                    (
                        "select public.fn_definir_escopo(%s, %s, '[]')",
                        (TENANT, HR),
                        "not_admin",
                    ),
                    (
                        "select public.fn_convidar_usuario(%s, %s, '[]')",
                        (TENANT, XO),
                        "not_admin",
                    ),
                ):
                    igual(
                        f"[{rotulo}] owner de outro tenant, com a linha travada: {codigo} na hora",
                        chama(fora, sql_fora, params_fora),
                        f"P0001:{codigo}",
                    )
            finally:
                fora.close()
        pid = s2.info.backend_pid
        resposta: dict[str, str] = {}
        fio = threading.Thread(
            target=lambda: resposta.update(s2=chama(s2, sql, params))
        )
        fio.start()
        esperando = False
        prazo = time.monotonic() + 10
        while time.monotonic() < prazo and fio.is_alive():
            linha = controle(
                f"select wait_event_type from pg_stat_activity where pid = {pid}"
            )
            if linha and linha[0][0] == "Lock":
                esperando = True
                break
            time.sleep(0.05)
        igual(f"[{rotulo}] a sessão 2 ficou esperando a sessão 1", esperando, True)
        s1.commit()
        fio.join(10)
        igual(
            f"[{rotulo}] a sessão 2, depois do commit da 1",
            resposta.get("s2"),
            esperado,
        )
        igual(
            f"[{rotulo}] o tenant ficou com exatamente um owner ativo",
            owners_ativos(),
            1,
        )
    finally:
        s1.close()
        s2.close()
        controle(_LIMPAR)


corrida(
    "dois owners",
    O2,
    "select public.fn_definir_papel(%s, %s, 'hr')",
    (TENANT, O1),
    "P0001:not_owner",
)
corrida(
    "owner desativando owner",
    O2,
    "select public.fn_desativar_membro(%s, %s)",
    (TENANT, O1),
    "P0001:owner_so_por_owner",
)


def corrida_de_tenants() -> None:
    """5. O hr de TENANT e o owner de OUTRO convidam o mesmo NEW ao mesmo tempo."""
    controle(_LIMPAR)
    controle(_CADASTRO)
    s1 = sessao(HR)
    s2 = sessao(XO)
    convite = "select public.fn_convidar_usuario(%s, %s, %s::jsonb)"
    try:
        s1.autocommit = False
        igual(
            "[dois tenants] sessão 1: o hr convida NEW no tenant (sem commit ainda)",
            chama(s1, convite, (TENANT, NEW, f'[{{"company_id": "{EMPRESA}"}}]')),
            "ok",
        )
        pid = s2.info.backend_pid
        resposta: dict[str, str] = {}
        fio = threading.Thread(
            target=lambda: resposta.update(
                s2=chama(
                    s2, convite, (OUTRO, NEW, f'[{{"company_id": "{EMPRESA_X}"}}]')
                )
            )
        )
        fio.start()
        espera = None
        prazo = time.monotonic() + 10
        while time.monotonic() < prazo and fio.is_alive():
            linha = controle(
                f"select wait_event_type, wait_event from pg_stat_activity where pid = {pid}"
            )
            if linha and linha[0][0] == "Lock":
                espera = linha[0][1]
                break
            time.sleep(0.05)
        igual(
            "[dois tenants] a sessão 2 espera a trava POR USUÁRIO (não a do tenant)",
            espera,
            "advisory",
        )
        s1.commit()
        fio.join(10)
        igual(
            "[dois tenants] a sessão 2, depois do commit da 1",
            resposta.get("s2"),
            "P0001:conta_em_outro_cliente",
        )
        igual(
            "[dois tenants] NEW ficou com exatamente um vínculo ativo, no tenant da sessão 1",
            controle(
                f"select array_agg(tenant_id::text) from app.tenant_member "
                f"where user_id = '{NEW}' and active"
            )[0][0],
            [TENANT],
        )
    finally:
        s1.close()
        s2.close()
        controle(_LIMPAR)


corrida_de_tenants()

igual(
    "o teste não deixou rastro",
    controle(f"select count(*) from app.tenant where id in ('{TENANT}', '{OUTRO}')")[0][
        0
    ],
    0,
)

print()
if falhas:
    print(f"  ✖ {len(falhas)} FALHA(S)")
    sys.exit(1)
print("================================================")
print(" CORRIDA DE OWNERS (U2) E DE TENANTS (U3): TODOS OS TESTES OK")
print("================================================")
