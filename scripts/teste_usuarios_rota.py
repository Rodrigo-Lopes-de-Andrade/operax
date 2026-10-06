#!/usr/bin/env python3
"""As rotas de usuário (U3) contra o banco — o router de verdade.

    ENSAIO_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55322/operax_test \\
      uv run --no-sync --project backend python scripts/teste_usuarios_rota.py

⛔ POR QUE ESTE NÃO É UM ROTEIRO DE `psql`
O convite é Admin API + RPC, e a lista é SQL no router (`server/routers/
usuarios.py`) lendo `auth.users` com a conexão do backend. O pytest prova o que
a rota decide com banco de mentira; o que só o banco responde é se a RPC,
chamada como o usuário, grava `viewer` com o autor certo, e se a leitura de
`auth.users` fica no tenant do token. Este chama as rotas importadas do router,
sob `tenant_scope`/`user_scope` de verdade. O GoTrue é falso (`httpx.
MockTransport`): ao convidar, ele faz o que o GoTrue faz — cria a linha em
`auth.users` — e responde com senha, link e tokens, que não podem voltar.

⚠️ `auth.users` do ensaio só tem `id` e `email`. As duas colunas que a rota lê e
que o Supabase tem (`raw_user_meta_data`, `email_confirmed_at`) entram aqui com
`add column if not exists` e saem no fim se foram este roteiro que as criou.

Perguntas:
1. **O convite novo**: o Admin API é chamado uma vez, com o nome em `data.name`; a RPC grava `viewer`,
   `invited_by` = quem convidou, o escopo pedido e a auditoria com o autor certo
   — prova de que ela rodou como o usuário, e não como `postgres`.
2. **`ja_e_membro` antes do Admin API**: o mesmo e-mail de novo, 409, e o GoTrue
   não é chamado.
3. **Escopo de outro tenant, antes do Admin API**: 422 `empresa_fora_do_tenant`,
   nenhuma identidade criada.
4. **Conta que já existe no Auth.** (a) ATIVA em B, convidada em A: 409
   `conta_em_outro_cliente` antes do Admin API, nenhum vínculo em A, e o token
   dela continua resolvendo B — um segundo vínculo ativo deixaria a resolução
   ambígua e a pessoa sem acesso a B. (b) Confirmada e só com vínculo INATIVO em
   B: reuso silencioso, nenhum e-mail, e o token passa a resolver A. (c) Sem
   senha e ATIVA em B: 409 também, sem reenviar e-mail. Em todas, o nome da
   conta não é reescrito. (d) ATIVA num tenant SUSPENSO: 409 também — reativado,
   o tenant deixaria o token dela ambíguo.
5. **A recusa tardia**: o papel de quem convida cai enquanto o GoTrue responde;
   a RPC recusa `not_admin`, nada é gravado, e a identidade criada FICA no Auth
   sem vínculo nenhum. O convite seguinte a acha sem senha e reenvia o e-mail.
   (b) A corrida: B vincula a mesma pessoa enquanto o GoTrue responde; a RPC
   recusa `conta_em_outro_cliente`, a rota responde 409, e sobra um vínculo.
6. **A lista**: nome, e-mail e quem convidou do recém-convidado; `scope_mode` e
   escopo por papel (o owner tem linha em `user_scope` e ela não aparece);
   nenhum membro do tenant vizinho — nem pela lista de A, nem pela de B.
7. **Reenviar convite**: só a membro deste tenant, só antes de aceitar.
8. **Nenhuma resposta carrega senha, link ou token.**

U4 — detalhe e matriz:
9. **A matriz vem de `app.domain_permission`**, do tenant do token: virar uma
   linha (o par fixado `viewer` -> `hr`: dar ao viewer um domínio, tirar um do
   hr) muda a resposta, e o vizinho, igual em tudo menos no tenant, não vaza.
10. **O papel**: o hr recebe 403 `not_owner` da rota e nada muda (nem papel,
    nem auditoria); o owner grava, com auditoria, e os quatro papéis de atalho
    saem `by_role` no detalhe; `ultimo_owner` vira 409.
11. **O escopo**: troca inteira pela RPC; recusa deixa o anterior; quem não
    administra recebe 403.
12. **Desativar**: `owner_so_por_owner`, `e_voce_mesmo` e o positivo — a linha
    fica, `active = false` e a data.
13. **Outro tenant**: GET e as três escritas em membro de B, pelo token de A,
    dão 404 e não mudam nada em B.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from typing import Any

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

import httpx  # noqa: E402
import psycopg  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from operax.core.auth_admin import get_auth_admin  # noqa: E402
from operax.core.db import get_pools  # noqa: E402
from operax.core.tenant import TenantContext, UserRole, resolve_membership  # noqa: E402
from server.models import (  # noqa: E402
    InvitationResendRequest,
    InvitationScopeEntry,
    MemberDeactivationRequest,
    MemberRoleRequest,
    MemberScopeRequest,
    UserInvitationRequest,
)
from server.routers import usuarios  # noqa: E402

TENANT_A = "0c3b0000-0000-0000-0000-000000000001"
TENANT_B = "0c3b0000-0000-0000-0000-000000000002"
#: Tenant SUSPENSO (`active = false`), com um membro ativo.
TENANT_C = "0c3b0000-0000-0000-0000-000000000003"
OWNER_A = "0c3b0000-0000-0000-0000-0000000000f1"
HR_A = "0c3b0000-0000-0000-0000-0000000000f2"
SUP_A = "0c3b0000-0000-0000-0000-0000000000f3"
PERS_A = "0c3b0000-0000-0000-0000-0000000000f4"
OWNER_B = "0c3b0000-0000-0000-0000-0000000000f5"
MEMBER_B = "0c3b0000-0000-0000-0000-0000000000f6"
#: Confirmada (tem senha), com vínculo INATIVO em B e nenhum ativo.
EX_B = "0c3b0000-0000-0000-0000-0000000000f7"
#: Convidada em B e nunca aceitou (sem senha), com vínculo ATIVO em B.
PEND_B = "0c3b0000-0000-0000-0000-0000000000f8"
#: SEM SENHA (nunca aceitou), membro ATIVO de C — que está suspenso. Sem senha
#: de propósito: é o caso em que a leitura da rota decide se um e-mail sai.
SUSP_C = "0c3b0000-0000-0000-0000-0000000000f9"
COMPANY_A = "0c3b0000-0000-0000-0000-0000000000c1"
COMPANY_B = "0c3b0000-0000-0000-0000-0000000000c2"
UNIT_A = "0c3b0000-0000-0000-0000-0000000000a1"
UNIT_B = "0c3b0000-0000-0000-0000-0000000000a2"
NOVO = "novo.u3@teste.dev"
ORFAO = "orfao.u3@teste.dev"
CORRIDA = "corrida.u3@teste.dev"
EMAIL_B = "membro.b.u3@teste.dev"
EMAIL_EX = "ex.b.u3@teste.dev"
EMAIL_PEND = "pendente.b.u3@teste.dev"
EMAIL_SUSP = "suspenso.c.u3@teste.dev"
FIXOS = (OWNER_A, HR_A, SUP_A, PERS_A, OWNER_B, MEMBER_B, EX_B, PEND_B, SUSP_C)

SECRETS = {
    "password": "pw-SEGREDO-U3",
    "token": "tk-SEGREDO-U3",
    "confirmation_token": "ct-SEGREDO-U3",
    "recovery_token": "rt-SEGREDO-U3",
    "action_link": "https://project.supabase.co/auth/v1/verify?token=al-SEGREDO-U3",
    "access_token": "at-SEGREDO-U3",
    "refresh_token": "rf-SEGREDO-U3",
}

_COLUNAS = """
select array_agg(column_name::text) as cols from information_schema.columns
 where table_schema = 'auth' and table_name = 'users'
   and column_name in ('raw_user_meta_data', 'email_confirmed_at')
"""

_LIMPAR = f"""
delete from app.audit_log where tenant_id in ('{TENANT_A}', '{TENANT_B}', '{TENANT_C}');
delete from app.user_scope where tenant_id in ('{TENANT_A}', '{TENANT_B}', '{TENANT_C}');
delete from app.tenant_member where tenant_id in ('{TENANT_A}', '{TENANT_B}', '{TENANT_C}');
delete from app.unit where tenant_id in ('{TENANT_A}', '{TENANT_B}', '{TENANT_C}');
delete from app.company where tenant_id in ('{TENANT_A}', '{TENANT_B}', '{TENANT_C}');
delete from app.tenant where id in ('{TENANT_A}', '{TENANT_B}', '{TENANT_C}');
delete from auth.users where id in ({", ".join(f"'{u}'" for u in FIXOS)})
                          or email in ('{NOVO}', '{ORFAO}', '{CORRIDA}');
"""

_CADASTRO = f"""
insert into auth.users (id, email, raw_user_meta_data, email_confirmed_at) values
  ('{OWNER_A}', 'owner.a.u3@teste.dev', '{{"name": "Owner A"}}', now()),
  ('{HR_A}',    'rh.a.u3@teste.dev',    '{{"name": "Pessoa do RH A"}}', now()),
  ('{SUP_A}',   'sup.a.u3@teste.dev',   '{{"name": "Supervisor A"}}', now()),
  ('{PERS_A}',  'dp.a.u3@teste.dev',    '{{"name": "Pessoal A"}}', now()),
  ('{OWNER_B}', 'owner.b.u3@teste.dev', '{{"name": "Owner B"}}', now()),
  ('{MEMBER_B}', '{EMAIL_B}',       '{{"name": "Membro de B"}}', now()),
  ('{EX_B}',    '{EMAIL_EX}',       '{{"name": "Ex de B"}}', now()),
  ('{PEND_B}',  '{EMAIL_PEND}',     '{{"name": "Pendente de B"}}', null),
  ('{SUSP_C}',  '{EMAIL_SUSP}',     '{{"name": "Suspenso de C"}}', null);
insert into app.tenant (id, slug, name) values
  ('{TENANT_A}', 'u3-rota-a', 'U3 A'), ('{TENANT_B}', 'u3-rota-b', 'U3 B');
insert into app.tenant (id, slug, name, active) values
  ('{TENANT_C}', 'u3-rota-c', 'U3 C (suspenso)', false);
insert into app.tenant_member (tenant_id, user_id, role) values
  ('{TENANT_A}', '{OWNER_A}', 'owner'), ('{TENANT_A}', '{HR_A}', 'hr'),
  ('{TENANT_A}', '{SUP_A}', 'unit_supervisor'), ('{TENANT_A}', '{PERS_A}', 'personnel'),
  ('{TENANT_B}', '{OWNER_B}', 'owner'), ('{TENANT_B}', '{MEMBER_B}', 'viewer'),
  ('{TENANT_B}', '{PEND_B}', 'viewer'),
  ('{TENANT_C}', '{SUSP_C}', 'viewer');
insert into app.tenant_member (tenant_id, user_id, role, active, deactivated_at) values
  ('{TENANT_B}', '{EX_B}', 'viewer', false, now());
insert into app.company (id, tenant_id, legal_name, trade_name) values
  ('{COMPANY_A}', '{TENANT_A}', 'U3 A LTDA', 'Alfa'),
  ('{COMPANY_B}', '{TENANT_B}', 'U3 B LTDA', 'Beta');
insert into app.unit (id, tenant_id, company_id, code, name) values
  ('{UNIT_A}', '{TENANT_A}', '{COMPANY_A}', 'U3A', 'Centro A'),
  ('{UNIT_B}', '{TENANT_B}', '{COMPANY_B}', 'U3B', 'Centro B');
-- A matriz (U4). A e B iguais em tudo menos no tenant e no viewer/pii, que é
-- `false` em A e `true` em B: sem o filtro de tenant, o viewer de A ganharia pii.
insert into app.domain_permission (tenant_id, role, domain, allowed)
select t.tenant_id, d.role::app.user_role, d.domain::app.sensitive_domain,
       case when d.role = 'viewer' then t.tenant_id = '{TENANT_B}' else true end
  from (values ('{TENANT_A}'::uuid), ('{TENANT_B}'::uuid)) as t(tenant_id)
 cross join (values ('owner', 'pii'), ('owner', 'banking'), ('hr', 'pii'),
                    ('hr', 'health'), ('hr', 'disciplinary'), ('viewer', 'pii')) as d(role, domain);
-- O owner TEM linha de escopo: a lista não pode mostrá-la (§3.2).
insert into app.user_scope (tenant_id, user_id, company_id, unit_id) values
  ('{TENANT_A}', '{OWNER_A}', '{COMPANY_A}', '{UNIT_A}'),
  ('{TENANT_A}', '{SUP_A}', '{COMPANY_A}', '{UNIT_A}');
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


def uma(sql: str, params: dict[str, Any] | None = None) -> Any:
    with psycopg.connect(DSN, autocommit=True) as conexao:
        return conexao.execute(sql, params or {}).fetchone()


class GoTrue:
    """Faz o que o GoTrue faz no convite: cria a identidade (ou acha a que não
    confirmou) e responde com o usuário — e com o que não pode vazar."""

    def __init__(self) -> None:
        self.chamadas: list[str] = []
        self.durante: str | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        corpo = json.loads(request.content)
        email = corpo["email"]
        self.chamadas.append(email)
        with psycopg.connect(DSN, autocommit=True) as conexao:
            row = conexao.execute(
                "select id from auth.users where lower(email) = %s", (email,)
            ).fetchone()
            user_id = row[0] if row else uuid.uuid4()
            if not row:
                # Como o GoTrue: `data` vira `raw_user_meta_data` da conta criada.
                conexao.execute(
                    "insert into auth.users (id, email, raw_user_meta_data) values (%s, %s, %s)",
                    (user_id, email, json.dumps(corpo.get("data", {}))),
                )
            if self.durante:
                conexao.execute(self.durante)
        return httpx.Response(200, json={"id": str(user_id), "email": email, **SECRETS})


def ctx(user: str, tenant: str, role: UserRole) -> TenantContext:
    return TenantContext(
        tenant_id=uuid.UUID(tenant), user_id=uuid.UUID(user), role=role
    )


def pedido(
    email: str, *entradas: tuple[str, str | None], name: str = "Nova Pessoa"
) -> UserInvitationRequest:
    return UserInvitationRequest(
        name=name,
        email=email,
        scope=[
            InvitationScopeEntry(company_id=uuid.UUID(c), unit_id=uuid.UUID(u))
            if u
            else InvitationScopeEntry(company_id=uuid.UUID(c))
            for c, u in entradas
        ],
    )


def sem_segredo(rotulo: str, modelo: Any) -> None:
    texto = modelo.model_dump_json()
    vazou = [k for k, v in SECRETS.items() if v in texto or f'"{k}"' in texto]
    igual(f"{rotulo}: sem senha, link nem token", vazou, [])


async def convidar(quem: TenantContext, req: UserInvitationRequest) -> Any:
    try:
        return await usuarios.invite_user(
            tenant=quem, request=req, auth_admin=get_auth_admin()
        )
    except HTTPException as erro:
        return (erro.status_code, erro.detail)


async def reenviar(quem: TenantContext, alvo: str) -> Any:
    try:
        return await usuarios.resend_invitation(
            tenant=quem,
            user_id=uuid.UUID(alvo),
            request=InvitationResendRequest(),
            auth_admin=get_auth_admin(),
        )
    except HTTPException as erro:
        return (erro.status_code, erro.detail)


async def rota(chamada: Any) -> Any:
    """A rota, ou o `(status, detail)` da recusa dela."""
    try:
        return await chamada
    except HTTPException as erro:
        return (erro.status_code, erro.detail)


def matriz(modelo: Any) -> dict[str, list[str]]:
    return {r.role.value: [d.value for d in r.domains] for r in modelo.roles}


async def main(gotrue: GoTrue) -> None:
    owner_a = ctx(OWNER_A, TENANT_A, UserRole.OWNER)
    hr_a = ctx(HR_A, TENANT_A, UserRole.HR)
    pers_a = ctx(PERS_A, TENANT_A, UserRole.PERSONNEL)
    owner_b = ctx(OWNER_B, TENANT_B, UserRole.OWNER)
    await get_pools().open()
    try:
        print("--- 1. o convite novo, pelo RH")
        feito = await convidar(hr_a, pedido(NOVO, (COMPANY_A, UNIT_A)))
        igual(
            "resposta: viewer, e-mail enviado",
            (feito.role, feito.invitation_sent),
            ("viewer", True),
        )
        igual("o Admin API foi chamado uma vez", gotrue.chamadas, [NOVO])
        sem_segredo("convite", feito)
        novo = str(feito.user_id)
        igual(
            "o vínculo: viewer, ativo, convidado pelo RH",
            uma(
                "select role::text, active, invited_by::text from app.tenant_member "
                "where tenant_id = %(t)s and user_id = %(u)s",
                {"t": TENANT_A, "u": novo},
            ),
            ("viewer", True, HR_A),
        )
        igual(
            "o escopo pedido",
            uma(
                "select company_id::text, unit_id::text from app.user_scope "
                "where tenant_id = %(t)s and user_id = %(u)s",
                {"t": TENANT_A, "u": novo},
            ),
            (COMPANY_A, UNIT_A),
        )
        igual(
            "a auditoria tem o RH como autor (a RPC rodou como o usuário)",
            uma(
                "select action, entity, user_id::text from app.audit_log "
                "where tenant_id = %(t)s and entity_id = %(u)s",
                {"t": TENANT_A, "u": novo},
            ),
            ("insert", "tenant_member", HR_A),
        )

        print("--- 2. ja_e_membro antes do Admin API")
        igual(
            "o mesmo e-mail, em maiúsculas: 409",
            await convidar(owner_a, pedido(NOVO.upper(), (COMPANY_A, None))),
            (409, "ja_e_membro"),
        )
        igual("o GoTrue não foi chamado de novo", gotrue.chamadas, [NOVO])

        print("--- 3. escopo de outro tenant, antes do Admin API")
        igual(
            "empresa de B num convite de A: 422",
            await convidar(owner_a, pedido(ORFAO, (COMPANY_B, None))),
            (422, "empresa_fora_do_tenant"),
        )
        igual(
            "unidade de B com a empresa de A: 422",
            await convidar(owner_a, pedido(ORFAO, (COMPANY_A, UNIT_B))),
            (422, "unidade_fora_da_empresa"),
        )
        igual("nenhuma chamada ao GoTrue", gotrue.chamadas, [NOVO])
        igual(
            "nenhuma identidade criada",
            uma("select count(*) from auth.users where email = %(e)s", {"e": ORFAO}),
            (0,),
        )

        print("--- 4a. conta ATIVA em B, convidada em A: recusada antes do Admin API")
        # Até o ciclo 1 da U3 este cenário afirmava o reuso — e o reuso criava um
        # segundo vínculo ativo, que deixava a pessoa sem acesso a B (resolução
        # ambígua, 403 em tudo). Decisão do dono, 05/10/2026: 409.
        igual(
            "409 conta_em_outro_cliente, sem dizer qual",
            await convidar(
                pers_a, pedido(EMAIL_B, (COMPANY_A, None), name="Outro Nome")
            ),
            (409, "conta_em_outro_cliente"),
        )
        igual("o GoTrue não foi chamado", gotrue.chamadas, [NOVO])
        igual(
            "nenhum vínculo criado em A; o de B intacto",
            uma(
                "select array_agg(t.slug || ':' || tm.role || ':' || tm.active order by t.slug) "
                "from app.tenant_member tm join app.tenant t on t.id = tm.tenant_id "
                "where tm.user_id = %(u)s",
                {"u": MEMBER_B},
            ),
            (["u3-rota-b:viewer:true"],),
        )
        resolvido = await resolve_membership(uuid.UUID(MEMBER_B))
        igual(
            "o token do membro de B continua resolvendo o vínculo dele",
            (str(resolvido.tenant_id), resolvido.role),
            (TENANT_B, UserRole.VIEWER),
        )
        igual(
            "o nome da conta existente não foi reescrito pelo convite",
            uma(
                "select raw_user_meta_data ->> 'name' from auth.users where id = %(u)s",
                {"u": MEMBER_B},
            ),
            ("Membro de B",),
        )

        print("--- 4b. conta CONFIRMADA, só com vínculo INATIVO em B: reuso silencioso")
        reuso = await convidar(
            pers_a, pedido(EMAIL_EX, (COMPANY_A, None), name="Outro Nome")
        )
        igual(
            "o id é o que já existia, e nenhum e-mail saiu",
            (str(reuso.user_id), reuso.invitation_sent),
            (EX_B, False),
        )
        igual("o GoTrue não foi chamado", gotrue.chamadas, [NOVO])
        resolvido = await resolve_membership(uuid.UUID(EX_B))
        igual(
            "o token dela resolve A, o único vínculo ativo",
            (str(resolvido.tenant_id), resolvido.role),
            (TENANT_A, UserRole.VIEWER),
        )
        igual(
            "o nome dela não foi reescrito",
            uma(
                "select raw_user_meta_data ->> 'name' from auth.users where id = %(u)s",
                {"u": EX_B},
            ),
            ("Ex de B",),
        )

        print("--- 4c. conta SEM SENHA e ATIVA em B: recusada antes de reenviar")
        igual(
            "409 conta_em_outro_cliente",
            await convidar(owner_a, pedido(EMAIL_PEND, (COMPANY_A, None))),
            (409, "conta_em_outro_cliente"),
        )
        igual("o GoTrue não foi chamado (nenhum e-mail saiu)", gotrue.chamadas, [NOVO])
        resolvido = await resolve_membership(uuid.UUID(PEND_B))
        igual(
            "e ela continua resolvendo B",
            (str(resolvido.tenant_id), resolvido.role),
            (TENANT_B, UserRole.VIEWER),
        )

        print("--- 4d. conta ATIVA num tenant SUSPENSO (C): recusada também (P3)")
        # A resolução do token ignora C hoje; reativado, ela ficaria ambígua.
        igual(
            "409 conta_em_outro_cliente",
            await convidar(owner_a, pedido(EMAIL_SUSP, (COMPANY_A, None))),
            (409, "conta_em_outro_cliente"),
        )
        igual("o GoTrue não foi chamado (nenhum e-mail saiu)", gotrue.chamadas, [NOVO])
        igual(
            "nenhum vínculo em A; o de C intacto",
            uma(
                "select array_agg(t.slug || ':' || tm.active) from app.tenant_member tm "
                "join app.tenant t on t.id = tm.tenant_id where tm.user_id = %(u)s",
                {"u": SUSP_C},
            ),
            (["u3-rota-c:true"],),
        )

        print("--- 5. a recusa tardia: o papel cai enquanto o GoTrue responde")
        gotrue.durante = (
            f"update app.tenant_member set role = 'viewer' "
            f"where tenant_id = '{TENANT_A}' and user_id = '{PERS_A}'"
        )
        igual(
            "a RPC recusa not_admin: 403",
            await convidar(pers_a, pedido(ORFAO, (COMPANY_A, None))),
            (403, "not_admin"),
        )
        gotrue.durante = None
        controle(
            f"update app.tenant_member set role = 'personnel' "
            f"where tenant_id = '{TENANT_A}' and user_id = '{PERS_A}'"
        )
        igual("o GoTrue foi chamado", gotrue.chamadas, [NOVO, ORFAO])
        igual(
            "a identidade FICA no Auth, sem vínculo nenhum",
            uma(
                "select count(*), count(tm.user_id) from auth.users u "
                "left join app.tenant_member tm on tm.user_id = u.id where u.email = %(e)s",
                {"e": ORFAO},
            ),
            (1, 0),
        )
        orfao_id = uma(
            "select id::text from auth.users where email = %(e)s", {"e": ORFAO}
        )[0]
        de_novo = await convidar(owner_a, pedido(ORFAO, (COMPANY_A, None), name="Órfã"))
        igual(
            "o próximo convite a acha sem senha e reenvia: mesmo id, e-mail enviado",
            (str(de_novo.user_id), de_novo.invitation_sent, gotrue.chamadas),
            (orfao_id, True, [NOVO, ORFAO, ORFAO]),
        )
        igual(
            "o reenvio não reescreveu o nome: fica o da criação, o 'Órfã' é descartado",
            uma(
                "select raw_user_meta_data ->> 'name' from auth.users where email = %(e)s",
                {"e": ORFAO},
            ),
            ("Nova Pessoa",),
        )

        print("--- 5b. a corrida: B vincula a mesma pessoa enquanto o GoTrue responde")
        gotrue.durante = (
            f"insert into app.tenant_member (tenant_id, user_id, role) "
            f"select '{TENANT_B}', id, 'viewer' from auth.users where email = '{CORRIDA}'"
        )
        igual(
            "a RPC recusa conta_em_outro_cliente, e a rota responde 409",
            await convidar(owner_a, pedido(CORRIDA, (COMPANY_A, None))),
            (409, "conta_em_outro_cliente"),
        )
        gotrue.durante = None
        igual(
            "a pessoa tem um vínculo ativo só, o de B",
            uma(
                "select array_agg(t.slug) from app.tenant_member tm "
                "join app.tenant t on t.id = tm.tenant_id "
                "join auth.users u on u.id = tm.user_id where u.email = %(e)s and tm.active",
                {"e": CORRIDA},
            ),
            (["u3-rota-b"],),
        )
        controle(
            f"delete from app.tenant_member where user_id = "
            f"(select id from auth.users where email = '{CORRIDA}')"
        )

        print("--- 6. a lista")
        # Sem simulação: o nome é o que o GoTrue falso gravou do `data` do convite.
        lista_a = await usuarios.list_users(tenant=owner_a)
        sem_segredo("lista de A", lista_a)
        por_id = {str(u.user_id): u for u in lista_a.users}
        linha = por_id[novo]
        igual(
            "recém-convidado: nome, e-mail, papel, aceite",
            (linha.name, linha.email, linha.role, linha.invitation_accepted),
            ("Nova Pessoa", NOVO, UserRole.VIEWER, False),
        )
        igual(
            "e quem o convidou",
            (
                str(linha.invited_by.user_id),
                linha.invited_by.email,
                linha.invited_by.name,
            ),
            (HR_A, "rh.a.u3@teste.dev", "Pessoa do RH A"),
        )
        igual(
            "escopo do recém-convidado",
            (linha.scope_mode, [(s.company_name, s.unit_name) for s in linha.scope]),
            ("by_scope", [("Alfa", "Centro A")]),
        )
        igual(
            "o owner é por papel, e a linha dele em user_scope não aparece",
            (por_id[OWNER_A].scope_mode, por_id[OWNER_A].scope),
            ("by_role", []),
        )
        igual(
            "hr e personnel também por papel",
            (por_id[HR_A].scope_mode, por_id[PERS_A].scope_mode),
            ("by_role", "by_role"),
        )
        igual(
            "o supervisor é pelo escopo",
            (por_id[SUP_A].scope_mode, [s.unit_name for s in por_id[SUP_A].scope]),
            ("by_scope", ["Centro A"]),
        )
        igual(
            "A vê os seus sete, e ninguém só de B",
            sorted(por_id),
            sorted([OWNER_A, HR_A, SUP_A, PERS_A, novo, EX_B, orfao_id]),
        )
        igual("nenhum vínculo de B na lista de A", OWNER_B in por_id, False)
        lista_b = await usuarios.list_users(tenant=owner_b)
        igual(
            "B vê os seus quatro (um inativo), e ninguém só de A",
            sorted(str(u.user_id) for u in lista_b.users),
            sorted([OWNER_B, MEMBER_B, EX_B, PEND_B]),
        )
        escopo_b = {str(u.user_id): u.scope for u in lista_b.users}
        igual("o escopo que ela tem em A não aparece em B", escopo_b[EX_B], [])

        print("--- 7. reenviar convite")
        reenvio = await reenviar(hr_a, novo)
        igual(
            "ao recém-convidado: 200",
            (str(reenvio.user_id), reenvio.email),
            (novo, NOVO),
        )
        sem_segredo("reenvio", reenvio)
        igual("o GoTrue recebeu o e-mail dele", gotrue.chamadas[-1], NOVO)
        igual(
            "a membro de B, pelo token de A: 404",
            await reenviar(hr_a, OWNER_B),
            (404, "member_not_found"),
        )
        igual(
            "a quem já aceitou: 409",
            await reenviar(hr_a, SUP_A),
            (409, "convite_ja_aceito"),
        )

        await u4(owner_a, hr_a, owner_b, novo)
    finally:
        await get_pools().close()


async def u4(
    owner_a: TenantContext, hr_a: TenantContext, owner_b: TenantContext, novo: str
) -> None:
    sup_a = ctx(SUP_A, TENANT_A, UserRole.UNIT_SUPERVISOR)
    roles = uma("select enum_range(null::app.user_role)::text[]")[0]
    vazio = {r: [] for r in roles}

    print("--- 9. a matriz vem de app.domain_permission, do tenant do token")
    m = await usuarios.domain_matrix(tenant=hr_a)
    sem_segredo("matriz", m)
    igual("um item por papel do enum, na ordem dele", [r.role.value for r in m.roles], roles)
    igual(
        "A: owner e hr com os seus; o viewer (false em A) e os outros vazios",
        matriz(m),
        vazio | {"owner": ["pii", "banking"], "hr": ["pii", "health", "disciplinary"]},
    )
    igual(
        "B: o viewer tem pii (true em B)",
        matriz(await usuarios.domain_matrix(tenant=owner_b))["viewer"],
        ["pii"],
    )
    controle(
        f"update app.domain_permission set allowed = true "
        f"where tenant_id = '{TENANT_A}' and role = 'viewer' and domain = 'pii'"
    )
    igual(
        "virou viewer/pii em A: o viewer passa a ter pii",
        matriz(await usuarios.domain_matrix(tenant=owner_a))["viewer"],
        ["pii"],
    )
    controle(
        f"update app.domain_permission set allowed = false "
        f"where tenant_id = '{TENANT_A}' and role = 'hr' and domain = 'health'"
    )
    igual(
        "virou hr/health em A: o hr perde health",
        matriz(await usuarios.domain_matrix(tenant=owner_a))["hr"],
        ["pii", "disciplinary"],
    )
    controle(
        f"update app.domain_permission set allowed = (role = 'hr') "
        f"where tenant_id = '{TENANT_A}' and role in ('viewer', 'hr')"
    )
    igual(
        "de volta: A como era",
        matriz(await usuarios.domain_matrix(tenant=owner_a)),
        vazio | {"owner": ["pii", "banking"], "hr": ["pii", "health", "disciplinary"]},
    )

    print("--- 10. o papel")
    auditoria = (
        "select count(*) from app.audit_log where tenant_id = %(t)s and entity_id = %(u)s "
        "and action = 'update' and entity = 'tenant_member'"
    )
    igual(
        "o hr: 403 not_owner da rota",
        await rota(
            usuarios.set_role(
                tenant=hr_a, user_id=uuid.UUID(novo), request=MemberRoleRequest(role=UserRole.HR)
            )
        ),
        (403, "not_owner"),
    )
    igual(
        "e nada mudou: papel e auditoria",
        (
            uma(
                "select role::text from app.tenant_member where tenant_id = %(t)s "
                "and user_id = %(u)s",
                {"t": TENANT_A, "u": novo},
            ),
            uma(auditoria, {"t": TENANT_A, "u": novo}),
        ),
        (("viewer",), (0,)),
    )
    for papel in (UserRole.EXECUTIVE, UserRole.HR, UserRole.PERSONNEL, UserRole.OWNER):
        feito = await usuarios.set_role(
            tenant=owner_a, user_id=uuid.UUID(novo), request=MemberRoleRequest(role=papel)
        )
        sem_segredo(f"papel {papel}", feito)
        detalhe = await usuarios.get_user(tenant=hr_a, user_id=uuid.UUID(novo))
        igual(
            f"{papel.value}: gravado, e o detalhe sai by_role sem a linha de user_scope",
            (feito.role, feito.scope_mode, feito.scope, detalhe.scope_mode, detalhe.scope),
            (papel, "by_role", [], "by_role", []),
        )
    volta = await usuarios.set_role(
        tenant=owner_a, user_id=uuid.UUID(novo), request=MemberRoleRequest(role=UserRole.VIEWER)
    )
    igual(
        "de volta a viewer: by_scope, com o escopo do convite",
        (volta.scope_mode, [(x.company_name, x.unit_name) for x in volta.scope]),
        ("by_scope", [("Alfa", "Centro A")]),
    )
    igual("uma auditoria por troca (cinco)", uma(auditoria, {"t": TENANT_A, "u": novo}), (5,))
    igual(
        "a primeira: viewer -> executive, com o owner como autor",
        uma(
            "select antes, depois, user_id::text from app.audit_log where tenant_id = %(t)s "
            "and entity_id = %(u)s and action = 'update' order by created_at, id limit 1",
            {"t": TENANT_A, "u": novo},
        ),
        ({"role": "viewer"}, {"role": "executive"}, OWNER_A),
    )
    igual(
        "o último owner rebaixando a si mesmo: 409",
        await rota(
            usuarios.set_role(
                tenant=owner_a,
                user_id=uuid.UUID(OWNER_A),
                request=MemberRoleRequest(role=UserRole.VIEWER),
            )
        ),
        (409, "ultimo_owner"),
    )

    print("--- 11. o escopo")
    escopo_sup = (
        "select array_agg(company_id::text || '/' || coalesce(unit_id::text, '*')) "
        "from app.user_scope where tenant_id = %(t)s and user_id = %(u)s"
    )
    trocado = await usuarios.set_scope(
        tenant=hr_a,
        user_id=uuid.UUID(SUP_A),
        request=MemberScopeRequest(scope=[InvitationScopeEntry(company_id=uuid.UUID(COMPANY_A))]),
    )
    sem_segredo("escopo", trocado)
    igual(
        "a empresa inteira, no retorno e no banco",
        (
            [(x.company_name, x.unit_name) for x in trocado.scope],
            uma(escopo_sup, {"t": TENANT_A, "u": SUP_A}),
        ),
        ([("Alfa", None)], ([f"{COMPANY_A}/*"],)),
    )
    igual(
        "empresa de B: 422, e o escopo anterior fica",
        (
            await rota(
                usuarios.set_scope(
                    tenant=owner_a,
                    user_id=uuid.UUID(SUP_A),
                    request=MemberScopeRequest(
                        scope=[InvitationScopeEntry(company_id=uuid.UUID(COMPANY_B))]
                    ),
                )
            ),
            uma(escopo_sup, {"t": TENANT_A, "u": SUP_A}),
        ),
        ((422, "empresa_fora_do_tenant"), ([f"{COMPANY_A}/*"],)),
    )
    igual(
        "o supervisor: 403 not_admin",
        await rota(
            usuarios.set_scope(
                tenant=sup_a,
                user_id=uuid.UUID(SUP_A),
                request=MemberScopeRequest(
                    scope=[
                        InvitationScopeEntry(
                            company_id=uuid.UUID(COMPANY_A), unit_id=uuid.UUID(UNIT_A)
                        )
                    ]
                ),
            )
        ),
        (403, "not_admin"),
    )

    print("--- 12. desativar")
    igual(
        "o hr desativando o owner: 403",
        await rota(
            usuarios.deactivate_user(
                tenant=hr_a, user_id=uuid.UUID(OWNER_A), request=MemberDeactivationRequest()
            )
        ),
        (403, "owner_so_por_owner"),
    )
    igual(
        "o hr desativando a si mesmo: 409",
        await rota(
            usuarios.deactivate_user(
                tenant=hr_a, user_id=uuid.UUID(HR_A), request=MemberDeactivationRequest()
            )
        ),
        (409, "e_voce_mesmo"),
    )
    fora = await usuarios.deactivate_user(
        tenant=hr_a, user_id=uuid.UUID(novo), request=MemberDeactivationRequest()
    )
    sem_segredo("desativar", fora)
    igual(
        "o recém-convidado: inativo, com a data, e a linha fica",
        (
            fora.active,
            fora.deactivated_at is not None,
            uma(
                "select count(*), bool_and(not active) from app.tenant_member "
                "where tenant_id = %(t)s and user_id = %(u)s",
                {"t": TENANT_A, "u": novo},
            ),
        ),
        (False, True, (1, True)),
    )

    print("--- 13. membro de outro tenant, pelo token de A: 404 e nada muda")
    estado_b = (
        "select (select array_agg(role::text || ':' || active order by user_id) "
        "          from app.tenant_member where tenant_id = %(t)s),"
        "       (select count(*) from app.user_scope where tenant_id = %(t)s),"
        "       (select count(*) from app.audit_log where tenant_id = %(t)s)"
    )
    antes = uma(estado_b, {"t": TENANT_B})
    alvo = uuid.UUID(MEMBER_B)
    igual(
        "GET, papel, escopo e desativar",
        [
            await rota(usuarios.get_user(tenant=owner_a, user_id=alvo)),
            await rota(
                usuarios.set_role(
                    tenant=owner_a, user_id=alvo, request=MemberRoleRequest(role=UserRole.OWNER)
                )
            ),
            await rota(
                usuarios.set_scope(
                    tenant=owner_a,
                    user_id=alvo,
                    request=MemberScopeRequest(
                        scope=[InvitationScopeEntry(company_id=uuid.UUID(COMPANY_A))]
                    ),
                )
            ),
            await rota(
                usuarios.deactivate_user(
                    tenant=owner_a, user_id=alvo, request=MemberDeactivationRequest()
                )
            ),
        ],
        [(404, "member_not_found")] * 4,
    )
    igual("B intacto: vínculos, escopo e auditoria", uma(estado_b, {"t": TENANT_B}), antes)
    igual(
        "nenhum vínculo do membro de B apareceu em A",
        uma(
            "select count(*) from app.tenant_member where tenant_id = %(t)s and user_id = %(u)s",
            {"t": TENANT_A, "u": MEMBER_B},
        ),
        (0,),
    )


cols = uma(_COLUNAS)[0] or []
criadas = [c for c in ("raw_user_meta_data", "email_confirmed_at") if c not in cols]
controle(
    "alter table auth.users add column if not exists raw_user_meta_data jsonb, "
    "add column if not exists email_confirmed_at timestamptz"
)
controle(_LIMPAR)
controle(_CADASTRO)
gotrue = GoTrue()
real = httpx.AsyncClient
transport = httpx.MockTransport(gotrue.handler)
httpx.AsyncClient = lambda **kw: real(transport=transport, **kw)  # type: ignore[assignment,misc]
try:
    asyncio.run(main(gotrue))
finally:
    httpx.AsyncClient = real  # type: ignore[misc]
    controle(_LIMPAR)
    for coluna in criadas:
        controle(f"alter table auth.users drop column {coluna}")

print()
if falhas:
    print(f"  ✖ {len(falhas)} FALHA(S)")
    sys.exit(1)
print("================================================")
print(" ROTAS DE USUÁRIO (U3 + U4): TODOS OS TESTES OK")
print("================================================")
