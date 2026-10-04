#!/usr/bin/env python3
"""A lista do lançamento no Secullum (P1.4) contra o banco — a rota de verdade.

    ENSAIO_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55322/operax_test \\
      uv run --no-sync --project backend python scripts/77_teste_lista_lancamento.py

⛔ POR QUE ESTE NÃO É UM ROTEIRO DE `psql`
A leitura é SQL no backend (`server/routers/alcada.py`, `POSTING_LIST_SQL`), não
objeto do banco — decisão do dono de 04/10/2026: nada novo em `public`. O pytest
prova o que a rota decide com o banco de mentira; o que só o banco responde é se
a RLS, o papel repetido na consulta e a janela 21→20 recortam o que devem. Um
roteiro que copiasse a consulta provaria a cópia. Este chama `posting_list` e
executa `POSTING_LIST_SQL` importados do router, sob o `user_scope` de verdade.

Perguntas:
1. **Pendente e lançada se separam pela marca** — a lançada pela RPC real, com
   `posted_by` de quem marcou. Reprovada, revisão de fora da janela do FATO,
   justificativa sem revisão e o tenant vizinho não entram.
2. **A competência é a do fato**: a janela de 2026/09 é 21/08–20/09, e a
   justificativa de 25/09 está em 2026/10 — mesmo com a revisão gravada na
   competência importada de 2026/09. As quatro bordas (20/08, 21/08, 20/09,
   21/09) caem cada uma de um lado só: um `between` trocado por desigualdade
   estrita, ou a janela deslocada um dia, aparece aqui.
3. **Os filtros estreitam**: unidade, colaborador e data. A unidade é a do
   DESVIO quando há desvio: o colaborador da unidade Um com desvio na Dois sai
   na Dois, e não na Um.
4. **O supervisor não alcança nada.** A rota responde 403; e a CONSULTA, rodada
   como ele sem o pré-teste, devolve zero linha — embora a RLS (`review_read`)
   o deixe ler a revisão da unidade dele. É o filtro de papel que segura.
5. **O tenant vizinho não vaza**: o RH de B vê só B, e a consulta com o tenant
   de A como parâmetro devolve zero para ele. Quem é `hr` nos dois tenants vê,
   pelo token de B, só B: a RLS o deixaria ver os dois, e é o tenant do token
   na consulta que recorta.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date

DSN = os.environ.get("ENSAIO_DATABASE_URL")
if not DSN:
    print("  ✖ defina ENSAIO_DATABASE_URL com o DSN do banco de ensaio")
    raise SystemExit(1)

os.environ["DATABASE_URL"] = DSN
os.environ.setdefault("SUPABASE_URL", "https://project.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key-for-tests")
os.environ.setdefault(
    "SUPABASE_JWT_JWKS_URL", "https://project.supabase.co/auth/v1/.well-known/jwks.json"
)
os.environ.setdefault("ANTHROPIC_API_KEY", "anthropic-key-for-tests")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

import psycopg  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from operax.core.db import get_pools  # noqa: E402
from operax.core.tenant import TenantContext, UserRole, user_scope  # noqa: E402
from server.routers import alcada  # noqa: E402

TENANT_A = "77000000-0000-0000-0000-000000000001"
TENANT_B = "77000000-0000-0000-0000-000000000002"
HR_A = "77000000-0000-0000-0000-0000000000f1"
OWNER_A = "77000000-0000-0000-0000-0000000000f2"
SUP_A = "77000000-0000-0000-0000-0000000000f3"
HR_B = "77000000-0000-0000-0000-0000000000f4"
#: `hr` em A E em B. O backend recusa esse usuário na entrada
#: (`AmbiguousTenantMembershipError`); a consulta não confia nisso e filtra pelo
#: tenant do token também.
DUAL = "77000000-0000-0000-0000-0000000000f5"
COMPANY_A = "77000000-0000-0000-0000-0000000000c1"
COMPANY_B = "77000000-0000-0000-0000-0000000000c2"
UNIT_1 = "77000000-0000-0000-0000-0000000000a1"
UNIT_2 = "77000000-0000-0000-0000-0000000000a2"
UNIT_B = "77000000-0000-0000-0000-0000000000a3"
EMP_1 = "77000000-0000-0000-0000-0000000000e1"
EMP_2 = "77000000-0000-0000-0000-0000000000e2"
EMP_B = "77000000-0000-0000-0000-0000000000e3"
PERIOD_A = "77000000-0000-0000-0000-0000000000d1"
PERIOD_B = "77000000-0000-0000-0000-0000000000d2"


DEV_11 = "77000000-0000-0000-0000-0000000000d3"


def j(n: int) -> str:
    return f"77000000-0000-0000-0000-00000000a{n:03d}"


def r(n: int) -> str:
    return f"77000000-0000-0000-0000-00000000b{n:03d}"


_LIMPAR = f"""
delete from app.justification_review where tenant_id in ('{TENANT_A}', '{TENANT_B}');
delete from app.justification where tenant_id in ('{TENANT_A}', '{TENANT_B}');
delete from app.deviation_event where tenant_id in ('{TENANT_A}', '{TENANT_B}');
delete from app.payroll_period where tenant_id in ('{TENANT_A}', '{TENANT_B}');
delete from app.user_scope where tenant_id in ('{TENANT_A}', '{TENANT_B}');
delete from app.employee where tenant_id in ('{TENANT_A}', '{TENANT_B}');
delete from app.unit where tenant_id in ('{TENANT_A}', '{TENANT_B}');
delete from app.company where tenant_id in ('{TENANT_A}', '{TENANT_B}');
delete from app.tenant_member where tenant_id in ('{TENANT_A}', '{TENANT_B}');
delete from app.tenant where id in ('{TENANT_A}', '{TENANT_B}');
delete from auth.users where id in ('{HR_A}', '{OWNER_A}', '{SUP_A}', '{HR_B}', '{DUAL}');
"""

# As revisões entram como `postgres`: a revisão pela RPC tem o `98` e o `81`. A
# marca da j2 entra pela RPC real, como o RH, logo abaixo.
#   j1 E1 05/09 aprovada            -> 2026/09, pendente
#   j2 E2 10/09 aprovada e lançada  -> 2026/09, lançada
#   j3 E1 12/09 reprovada           -> fora (reprovada não se lança)
#   j4 E1 25/09 aprovada            -> 2026/10 (o fato), embora a revisão seja da 2026/09
#   j5 E1 06/09 pendente sem revisão -> fora
#   j6 EB 05/09 aprovada, em B      -> só para o RH de B
# As bordas da janela 21→20 (2026/09 = 21/08–20/09), cada uma com a vizinha:
#   j7  E1 20/09 aprovada -> 2026/09, não 2026/10 (último dia)
#   j8  E1 21/09 aprovada -> 2026/10, não 2026/09 (primeiro dia da seguinte)
#   j9  E1 21/08 aprovada -> 2026/09 (primeiro dia)
#   j10 E1 20/08 aprovada -> 2026/08, não 2026/09 (último dia da anterior)
# A unidade é a do DESVIO, e a do colaborador só sem desvio:
#   j11 E1 08/09 aprovada, desvio na unidade Dois — E1 é hoje da unidade Um
_CADASTRO = f"""
insert into auth.users (id, email) values
  ('{HR_A}', 'rh.a.p14l@teste'), ('{OWNER_A}', 'owner.a.p14l@teste'),
  ('{SUP_A}', 'sup.a.p14l@teste'), ('{HR_B}', 'rh.b.p14l@teste'),
  ('{DUAL}', 'rh.ab.p14l@teste');
insert into app.tenant (id, slug, name) values
  ('{TENANT_A}', 'p14-lista-a', 'P14L A'), ('{TENANT_B}', 'p14-lista-b', 'P14L B');
insert into app.tenant_member (tenant_id, user_id, role) values
  ('{TENANT_A}', '{HR_A}', 'hr'), ('{TENANT_A}', '{OWNER_A}', 'owner'),
  ('{TENANT_A}', '{SUP_A}', 'unit_supervisor'), ('{TENANT_B}', '{HR_B}', 'hr'),
  ('{TENANT_A}', '{DUAL}', 'hr'), ('{TENANT_B}', '{DUAL}', 'hr');
insert into app.company (id, tenant_id, legal_name, trade_name) values
  ('{COMPANY_A}', '{TENANT_A}', 'P14L A LTDA', 'P14L A'),
  ('{COMPANY_B}', '{TENANT_B}', 'P14L B LTDA', 'P14L B');
insert into app.unit (id, tenant_id, company_id, code, name) values
  ('{UNIT_1}', '{TENANT_A}', '{COMPANY_A}', 'L1', 'Lista Um'),
  ('{UNIT_2}', '{TENANT_A}', '{COMPANY_A}', 'L2', 'Lista Dois'),
  ('{UNIT_B}', '{TENANT_B}', '{COMPANY_B}', 'LB', 'Lista B');
insert into app.user_scope (tenant_id, user_id, unit_id) values
  ('{TENANT_A}', '{SUP_A}', '{UNIT_1}');
insert into app.employee (id, tenant_id, company_id, unit_id, name) values
  ('{EMP_1}', '{TENANT_A}', '{COMPANY_A}', '{UNIT_1}', 'Pessoa Um'),
  ('{EMP_2}', '{TENANT_A}', '{COMPANY_A}', '{UNIT_2}', 'Pessoa Dois'),
  ('{EMP_B}', '{TENANT_B}', '{COMPANY_B}', '{UNIT_B}', 'Pessoa B');
insert into app.deviation_event
  (id, tenant_id, employee_id, company_id, unit_id, reference_date, type, minutes, mode)
values ('{DEV_11}', '{TENANT_A}', '{EMP_1}', '{COMPANY_A}', '{UNIT_2}', '2026-09-08',
        'late_entry', -20, 'production');
insert into app.payroll_period (id, tenant_id, year, month, status) values
  ('{PERIOD_A}', '{TENANT_A}', 2026, 9, 'importada'),
  ('{PERIOD_B}', '{TENANT_B}', 2026, 9, 'importada');
insert into app.justification
  (id, tenant_id, deviation_event_id, employee_id, reference_date, text, status, source,
   author_name)
values
  ('{j(1)}', '{TENANT_A}', null, '{EMP_1}', '2026-09-05', 'um',     'pending', 'operax', 'Sup'),
  ('{j(2)}', '{TENANT_A}', null, '{EMP_2}', '2026-09-10', 'dois',   'pending', 'operax', 'Sup'),
  ('{j(3)}', '{TENANT_A}', null, '{EMP_1}', '2026-09-12', 'tres',   'pending', 'operax', 'Sup'),
  ('{j(4)}', '{TENANT_A}', null, '{EMP_1}', '2026-09-25', 'quatro', 'pending', 'operax', 'Sup'),
  ('{j(5)}', '{TENANT_A}', null, '{EMP_1}', '2026-09-06', 'cinco',  'pending', 'operax', 'Sup'),
  ('{j(6)}', '{TENANT_B}', null, '{EMP_B}', '2026-09-05', 'seis',   'pending', 'operax', 'Sup'),
  ('{j(7)}', '{TENANT_A}', null, '{EMP_1}', '2026-09-20', 'sete',   'pending', 'operax', 'Sup'),
  ('{j(8)}', '{TENANT_A}', null, '{EMP_1}', '2026-09-21', 'oito',   'pending', 'operax', 'Sup'),
  ('{j(9)}', '{TENANT_A}', null, '{EMP_1}', '2026-08-21', 'nove',   'pending', 'operax', 'Sup'),
  ('{j(10)}', '{TENANT_A}', null, '{EMP_1}', '2026-08-20', 'dez',   'pending', 'operax', 'Sup'),
  ('{j(11)}', '{TENANT_A}', '{DEV_11}', '{EMP_1}', '2026-09-08', 'onze',
   'pending', 'operax', 'Sup');
insert into app.justification_review
  (id, tenant_id, justification_id, payroll_period_id, decision, reason, reviewed_by)
values
  ('{r(1)}', '{TENANT_A}', '{j(1)}', '{PERIOD_A}', 'approved', null, '{OWNER_A}'),
  ('{r(2)}', '{TENANT_A}', '{j(2)}', '{PERIOD_A}', 'approved', null, '{OWNER_A}'),
  ('{r(3)}', '{TENANT_A}', '{j(3)}', '{PERIOD_A}', 'rejected', 'nao', '{OWNER_A}'),
  ('{r(4)}', '{TENANT_A}', '{j(4)}', '{PERIOD_A}', 'approved', null, '{OWNER_A}'),
  ('{r(6)}', '{TENANT_B}', '{j(6)}', '{PERIOD_B}', 'approved', null, '{HR_B}'),
  ('{r(7)}', '{TENANT_A}', '{j(7)}', '{PERIOD_A}', 'approved', null, '{OWNER_A}'),
  ('{r(8)}', '{TENANT_A}', '{j(8)}', '{PERIOD_A}', 'approved', null, '{OWNER_A}'),
  ('{r(9)}', '{TENANT_A}', '{j(9)}', '{PERIOD_A}', 'approved', null, '{OWNER_A}'),
  ('{r(10)}', '{TENANT_A}', '{j(10)}', '{PERIOD_A}', 'approved', null, '{OWNER_A}'),
  ('{r(11)}', '{TENANT_A}', '{j(11)}', '{PERIOD_A}', 'approved', null, '{OWNER_A}');
"""

falhas: list[str] = []


def igual(rotulo: str, obtido: object, esperado: object) -> None:
    if obtido != esperado:
        falhas.append(f"{rotulo}: esperado {esperado!r}, obtido {obtido!r}")
        print(f"  ✖ {rotulo}: esperado {esperado!r}, obtido {obtido!r}")
    else:
        print(f"  ok  {rotulo} ({obtido!r})")


def controle(texto: str) -> None:
    with psycopg.connect(DSN, autocommit=True) as conexao:
        conexao.execute(texto)


def ctx(user: str, tenant: str, role: UserRole) -> TenantContext:
    return TenantContext(tenant_id=uuid.UUID(tenant), user_id=uuid.UUID(user), role=role)


async def lista(context: TenantContext, ano: int = 2026, mes: int = 9, **filtros: object):
    return await alcada.posting_list(
        tenant=context,
        ano=ano,
        mes=mes,
        unidade=filtros.get("unidade"),
        colaborador=filtros.get("colaborador"),
        de=filtros.get("de"),
        ate=filtros.get("ate"),
    )


def separadas(resposta) -> tuple[list[str], list[str]]:
    """(pendentes, lançadas), pelo id da justificativa."""
    pend = [str(x.justification_id) for x in resposta.rows if x.posted_to_source_at is None]
    lanc = [str(x.justification_id) for x in resposta.rows if x.posted_to_source_at is not None]
    return pend, lanc


async def consulta_crua(context: TenantContext, tenant_param: str) -> int:
    """`POSTING_LIST_SQL` como o usuário, SEM o pré-teste da rota."""
    async with user_scope(context) as scope:
        await scope.execute(
            alcada.POSTING_LIST_SQL,
            {
                "year": 2026,
                "month": 9,
                "tenant_id": uuid.UUID(tenant_param),
                "unit_id": None,
                "employee_id": None,
                "de": None,
                "ate": None,
            },
        )
        return len(await scope.fetchall())


async def main() -> None:
    hr_a = ctx(HR_A, TENANT_A, UserRole.HR)
    owner_a = ctx(OWNER_A, TENANT_A, UserRole.OWNER)
    sup_a = ctx(SUP_A, TENANT_A, UserRole.UNIT_SUPERVISOR)
    hr_b = ctx(HR_B, TENANT_B, UserRole.HR)
    await get_pools().open()
    try:
        # A marca da j2 pela porta real (o SQL do POST), como o RH.
        async with user_scope(hr_a) as scope:
            await scope.execute(alcada.POSTING_SQL, {"review_id": uuid.UUID(r(2))})

        print("--- 1 e 2. a separação, e a competência do fato")
        for nome, quem in (("RH", hr_a), ("owner", owner_a)):
            resposta = await lista(quem)
            igual(
                f"{nome} de A, 2026/09: pendentes j9 j1 j11 j7 | lançada j2",
                separadas(resposta),
                ([j(9), j(1), j(11), j(7)], [j(2)]),
            )
            igual(
                f"{nome} de A: a janela vem do banco",
                (resposta.period_start, resposta.period_end),
                (date(2026, 8, 21), date(2026, 9, 20)),
            )
        lancada = next(x for x in (await lista(hr_a)).rows if x.posted_to_source_at)
        igual(
            "a lançada traz quem lançou (o RH) e quem aprovou (o owner)",
            (str(lancada.posted_by), str(lancada.reviewed_by)),
            (HR_A, OWNER_A),
        )
        igual(
            "2026/10: j8 (21/09, a borda) e j4 (25/09) — a revisão é da 2026/09",
            separadas(await lista(hr_a, 2026, 10)),
            ([j(8), j(4)], []),
        )
        igual(
            "2026/08: só a j10 (20/08, último dia) — a j9 de 21/08 já é 2026/09",
            separadas(await lista(hr_a, 2026, 8)),
            ([j(10)], []),
        )

        print("--- 3. os filtros estreitam")
        unidade_dois = await lista(hr_a, unidade=uuid.UUID(UNIT_2))
        igual(
            "unidade Dois: a j11 (desvio lá, colaborador da Um) e a j2",
            separadas(unidade_dois),
            ([j(11)], [j(2)]),
        )
        onze = next(x for x in unidade_dois.rows if str(x.justification_id) == j(11))
        igual(
            "a linha da j11 mostra a unidade do desvio",
            (str(onze.unit_id), onze.unit_name),
            (UNIT_2, "Lista Dois"),
        )
        igual(
            "unidade Um: sem a j11 — a unidade atual do colaborador não vale com desvio",
            separadas(await lista(hr_a, unidade=uuid.UUID(UNIT_1))),
            ([j(9), j(1), j(7)], []),
        )
        igual(
            "colaborador Um: j9 j1 j11 j7",
            separadas(await lista(hr_a, colaborador=uuid.UUID(EMP_1))),
            ([j(9), j(1), j(11), j(7)], []),
        )
        igual(
            "de = até = 10/09: só a j2",
            separadas(await lista(hr_a, de=date(2026, 9, 10), ate=date(2026, 9, 10))),
            ([], [j(2)]),
        )

        print("--- 4. o supervisor não alcança nada")
        try:
            await lista(sup_a)
            igual("supervisor na rota", "200", "403")
        except HTTPException as erro:
            igual(
                "supervisor na rota: 403 not_hr", (erro.status_code, erro.detail), (403, "not_hr")
            )
        async with user_scope(sup_a) as scope:
            await scope.execute(
                "select count(*) as n from app.justification_review where id = %(id)s",
                {"id": uuid.UUID(r(1))},
            )
            igual(
                "a RLS deixa o supervisor LER a revisão da unidade dele",
                (await scope.fetchone())["n"],
                1,
            )
        igual(
            "e a consulta, sem o pré-teste, devolve zero a ele",
            await consulta_crua(sup_a, TENANT_A),
            0,
        )

        print("--- 5. o tenant vizinho")
        igual("RH de B, 2026/09: só a j6", separadas(await lista(hr_b)), ([j(6)], []))
        igual("RH de B com o tenant de A na consulta: zero", await consulta_crua(hr_b, TENANT_A), 0)
        igual(
            "hr em A e em B, pelo token de B: só a j6 (o tenant do token filtra)",
            separadas(await lista(ctx(DUAL, TENANT_B, UserRole.HR))),
            ([j(6)], []),
        )
    finally:
        await get_pools().close()


controle(_LIMPAR)
controle(_CADASTRO)
try:
    asyncio.run(main())
finally:
    controle(_LIMPAR)

print()
if falhas:
    print(f"  ✖ {len(falhas)} FALHA(S)")
    sys.exit(1)
print("================================================")
print(" LISTA DO LANÇAMENTO (P1.4): TODOS OS TESTES OK")
print("================================================")
