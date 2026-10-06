"""Usuários do painel — convite, reenvio e lista (SPEC-USUARIOS §5.4, §5.6, §6).

Caminho 2. Quem escreve vínculo e escopo são as RPCs `security definer` de
`usuarios_rpc`, chamadas como o usuário; esta rota faz o que o banco não
alcança: criar a identidade no Auth (Admin API) e ler nome e e-mail em
`auth.users`, que não é exposto ao PostgREST.

O CONVITE (`POST /usuarios/convites`), nesta ordem:
  (a) o papel: só `owner`, `hr` e `personnel` (o `util.is_admin`), senão 403
      `not_admin` — o código da própria RPC;
  (b) ⛔ `ja_e_membro` ANTES do Admin API: o e-mail já é de uma identidade do
      Auth que tem vínculo (ativo ou não) com ESTE tenant? 409, e o Admin API
      não é chamado. Convidar e recusar depois mandaria e-mail a quem não devia;
  (c) ⛔ `conta_em_outro_cliente` ANTES do Admin API: a identidade tem vínculo
      ATIVO em qualquer outro tenant (ativo ou suspenso)? 409, sem dizer qual.
      Um segundo vínculo ativo faria `resolve_membership` levantar
      `AmbiguousTenantMembershipError`, e a pessoa perderia o acesso ao cliente
      dela inteiro (403 em tudo, até no `/me`). Esta leitura é a cortesia que
      evita o e-mail; a GUARDA é a RPC, que refaz a mesma condição sob uma
      trava por usuário (decisão do dono, 05/10/2026);
  (d) o escopo, pelo MESMO parser da RPC (`util.parse_user_scope`), também
      antes do Admin API: empresa de outro tenant ou unidade fora da empresa
      recusam aqui, sem e-mail. É a função da RPC, não uma cópia da regra;
  (e) a identidade (decisão do dono, 05/10/2026):
      * e-mail novo -> `POST /auth/v1/invite` cria a conta com `data.name` e
        manda o e-mail (`invitation_sent = true`);
      * conta que existe e NÃO confirmou (sem senha) -> o Admin API é chamado
        de novo, sem `data`, e reenvia o e-mail (`invitation_sent = true`);
      * conta que existe e JÁ confirmou (tem senha), sem vínculo ativo em
        lugar nenhum -> REUSADA em silêncio: nenhum e-mail sai, a pessoa entra
        com a senha que já tem (`invitation_sent = false`).
      Nas duas últimas o `name` pedido é DESCARTADO: os metadados da conta
      existente não são reescritos. `redirect_to` =
      `{dashboard_url}{INVITE_LANDING_PATH}`;
  (f) `public.fn_convidar_usuario` como o usuário (`user_scope`): a RPC refaz
      papel, `ja_e_membro` e escopo sob o lock do tenant, e
      `conta_em_outro_cliente` sob o lock do usuário — é ela que fecha a
      corrida de dois tenants convidando a mesma pessoa, que nenhuma leitura
      desta rota alcança — e grava a auditoria com o autor certo. Recusa
      `P0001` vira HTTP pelo `INVITE_STATUS`, código no `detail`.

Se a RPC recusar DEPOIS do Admin API (só uma corrida chega aqui: o papel caiu,
a empresa sumiu, outro admin — deste ou de outro tenant — vinculou a mesma
pessoa no meio), a identidade
criada FICA no Auth, sem vínculo nenhum: ela não entra no painel (o `/me` dá
403 sem vínculo), e o próximo convite do mesmo e-mail a acha sem senha e
reenvia o e-mail para ela. Não se apaga:
`tenant_member.user_id` e `user_scope.user_id` são `on delete cascade`, e apagar
uma identidade que outro tenant acabou de vincular apagaria o vínculo dele.

O DETALHE (U4): `GET /usuarios/{id}` é a linha da lista, pelo mesmo SQL com o
membro no predicado; `PUT .../papel`, `PUT .../escopo` e `POST .../desativar`
chamam `fn_definir_papel`, `fn_definir_escopo` e `fn_desativar_membro` como o
usuário e devolvem a linha relida. O papel é recusado PELA ROTA a quem não é
`owner` (403 `not_owner`, sem abrir a RPC); a RPC continua sendo a garantia.
`GET /usuarios/matriz` lê `app.domain_permission` do tenant a cada requisição.

⛔ Nenhum campo de senha, link ou token em lugar nenhum: o Admin API devolve só
o `UUID` para cá (`operax/core/auth_admin.py`), e as respostas desta rota são os
modelos `UserInvitation`, `InvitationResent` e `TenantUserList`.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import errors
from psycopg.rows import DictRow
from psycopg.types.json import Jsonb

from operax.core.auth_admin import AuthAdmin, AuthAdminError, get_auth_admin
from operax.core.config import get_settings
from operax.core.tenant import TenantContext, UserRole, tenant_scope, user_scope
from server.deps import CurrentTenant
from server.models import (
    InvitationResendRequest,
    InvitationResent,
    MemberDeactivationRequest,
    MemberRoleRequest,
    MemberScopeRequest,
    RoleDomainMatrix,
    RoleDomains,
    ScopeMode,
    SensitiveDomain,
    TenantUser,
    TenantUserInviter,
    TenantUserList,
    TenantUserScope,
    UserInvitation,
    UserInvitationRequest,
)

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

#: Quem administra usuários: o `util.is_admin` (migration 02). A RPC confere de
#: novo; a rota confere antes para que o Admin API nunca seja chamado por quem
#: a RPC recusaria.
ADMIN_ROLES = frozenset({UserRole.OWNER, UserRole.HR, UserRole.PERSONNEL})

#: O atalho de papel de `util.can_see_unit` e `util.can_see_company`: com ele, o
#: conteúdo de `app.user_scope` não diz o que a pessoa vê (§3.2).
#: `tests/test_usuarios.py` confere esta lista contra a migration.
BY_ROLE_ROLES = frozenset({UserRole.OWNER, UserRole.EXECUTIVE, UserRole.HR, UserRole.PERSONNEL})

#: A rota do painel em que o link do e-mail de convite aterrissa — a tela onde a
#: pessoa define a própria senha. A origem vem de `Settings.dashboard_url`.
#: ⚠️ `{dashboard_url}/convite` precisa estar nas Redirect URLs do Supabase Auth;
#: fora delas o GoTrue cai na Site URL.
INVITE_LANDING_PATH = "/convite"

NOT_ADMIN = "not_admin"

#: As recusas de `fn_convidar_usuario` e do parser, na ordem da migration
#: `usuarios_rpc`. 403: quem pede não administra este tenant; 409: o e-mail já é
#: membro; 422: o escopo pedido não vale neste tenant.
INVITE_STATUS = {
    "not_admin": status.HTTP_403_FORBIDDEN,
    "ja_e_membro": status.HTTP_409_CONFLICT,
    "conta_em_outro_cliente": status.HTTP_409_CONFLICT,
    "escopo_vazio": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "escopo_invalido": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "escopo_sem_empresa": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "empresa_fora_do_tenant": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "unidade_fora_da_empresa": status.HTTP_422_UNPROCESSABLE_CONTENT,
}

#: (b), (c) e (e): a identidade do e-mail — se já confirmou, se tem vínculo com
#: ESTE tenant, e se tem vínculo ativo em OUTRO.
#: ⚠️ O lado de `auth.users` NÃO é recortado por tenant, e de propósito: a
#: identidade é global (uma pessoa, um login), e é ela que o convite precisa
#: achar para não criar outra. Sai o id e três booleanos — nunca qual é o outro
#: tenant. `active_elsewhere` é a condição de `fn_convidar_usuario`: vínculo
#: ativo em qualquer outro tenant, SEM olhar se o tenant está ativo — mais
#: estrita que `_MEMBERSHIP_SQL`, de propósito: o suspenso, reativado, deixaria
#: a resolução do token ambígua.
IDENTITY_SQL = """
    select u.id as user_id,
           u.email_confirmed_at is not null as confirmed,
           exists (select 1 from app.tenant_member tm
                    where tm.tenant_id = %(tenant_id)s and tm.user_id = u.id) as is_member,
           exists (select 1 from app.tenant_member o
                    where o.tenant_id <> %(tenant_id)s and o.user_id = u.id
                      and o.active) as active_elsewhere
      from auth.users u
     where lower(u.email) = %(email)s
"""

#: (d) O escopo pelo parser da RPC, antes do Admin API. Recusa com o mesmo
#: `P0001` que a RPC daria. Ancorado no vínculo de quem pede, neste tenant.
SCOPE_CHECK_SQL = """
    select count(*) as entries
      from app.tenant_member tm
      cross join lateral util.parse_user_scope(tm.tenant_id, %(scope)s) s
     where tm.tenant_id = %(tenant_id)s
       and tm.user_id = %(caller)s
"""

#: (f) A RPC, como o usuário.
INVITE_SQL = """
    select public.fn_convidar_usuario(%(tenant_id)s, %(user_id)s, %(scope)s)
"""

#: O membro deste tenant a quem reenviar o convite.
RESEND_TARGET_SQL = """
    select u.email, tm.active, u.email_confirmed_at is not null as accepted
      from app.tenant_member tm
      join auth.users u on u.id = tm.user_id
     where tm.tenant_id = %(tenant_id)s
       and tm.user_id = %(user_id)s
"""

#: A lista: os vínculos DESTE tenant, com nome e e-mail do Auth — e os de quem
#: convidou. `auth.users` só entra pelo `user_id`/`invited_by` de um vínculo
#: deste tenant: nenhuma identidade de fora aparece. O detalhe é o mesmo SQL com
#: um predicado a mais (`{member}`), não uma cópia.
_MEMBERS_SQL = """
    select tm.user_id, u.email, nullif(btrim(u.raw_user_meta_data ->> 'name'), '') as name,
           tm.role, tm.active, tm.deactivated_at,
           u.email_confirmed_at is not null as invitation_accepted,
           tm.invited_by, inv.email as invited_by_email,
           nullif(btrim(inv.raw_user_meta_data ->> 'name'), '') as invited_by_name
      from app.tenant_member tm
      join auth.users u on u.id = tm.user_id
      left join auth.users inv on inv.id = tm.invited_by
     where tm.tenant_id = %(tenant_id)s{member}
     order by tm.active desc, lower(coalesce(nullif(btrim(u.raw_user_meta_data ->> 'name'), ''),
                                             u.email))
"""

_SCOPE_SQL = """
    select s.user_id, s.company_id, coalesce(c.trade_name, c.legal_name) as company_name,
           s.unit_id, un.name as unit_name
      from app.user_scope s
      join app.company c on c.id = s.company_id and c.tenant_id = s.tenant_id
      left join app.unit un on un.id = s.unit_id and un.tenant_id = s.tenant_id
     where s.tenant_id = %(tenant_id)s{member}
     order by company_name, un.name nulls first
"""

LIST_SQL = _MEMBERS_SQL.format(member="")
SCOPE_LIST_SQL = _SCOPE_SQL.format(member="")
DETAIL_SQL = _MEMBERS_SQL.format(member="\n       and tm.user_id = %(user_id)s")
SCOPE_DETAIL_SQL = _SCOPE_SQL.format(member="\n       and s.user_id = %(user_id)s")

#: A matriz de domínios: um item por valor de `app.user_role` (o enum, não as
#: linhas — papel sem domínio vem com lista vazia), com os domínios que
#: `app.domain_permission` DESTE tenant libera. Papéis e domínios na ordem do
#: enum. Lida a cada requisição: quem concede vê o que concede (§6).
MATRIX_SQL = """
    select r.role, coalesce(array_agg(dp.domain::text order by dp.domain)
                              filter (where dp.domain is not null), '{}') as domains
      from unnest(enum_range(null::app.user_role)) as r(role)
      left join app.domain_permission dp
        on dp.role = r.role and dp.allowed and dp.tenant_id = %(tenant_id)s
     group by r.role
     order by r.role
"""

#: As três escritas do detalhe: as RPCs da U2, como o usuário. Elas refazem o
#: papel, acham o membro SÓ neste tenant e gravam a auditoria com o autor certo.
ROLE_SQL = """
    select public.fn_definir_papel(%(tenant_id)s, %(user_id)s, %(role)s::app.user_role)
"""
SCOPE_SQL = """
    select public.fn_definir_escopo(%(tenant_id)s, %(user_id)s, %(scope)s)
"""
DEACTIVATE_SQL = """
    select public.fn_desativar_membro(%(tenant_id)s, %(user_id)s)
"""

NOT_OWNER = "not_owner"
MEMBER_NOT_FOUND = "member_not_found"

#: As recusas de cada RPC, na ordem da migration `usuarios_rpc`. Código fora da
#: tabela da rota não vira resposta: sobe como erro (500).
ROLE_STATUS = {
    "not_owner": status.HTTP_403_FORBIDDEN,
    "member_not_found": status.HTTP_404_NOT_FOUND,
    "ultimo_owner": status.HTTP_409_CONFLICT,
}
SCOPE_STATUS = {
    "not_admin": status.HTTP_403_FORBIDDEN,
    "member_not_found": status.HTTP_404_NOT_FOUND,
    "escopo_vazio": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "escopo_invalido": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "escopo_sem_empresa": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "empresa_fora_do_tenant": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "unidade_fora_da_empresa": status.HTTP_422_UNPROCESSABLE_CONTENT,
}
DEACTIVATE_STATUS = {
    "not_admin": status.HTTP_403_FORBIDDEN,
    "e_voce_mesmo": status.HTTP_409_CONFLICT,
    "member_not_found": status.HTTP_404_NOT_FOUND,
    "owner_so_por_owner": status.HTTP_403_FORBIDDEN,
    "ultimo_owner": status.HTTP_409_CONFLICT,
}


def _require_admin(tenant: TenantContext) -> None:
    """O papel resolvido do banco nesta requisição (`resolve_membership`)."""
    if tenant.role not in ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=NOT_ADMIN)


def _refusal(
    recusa: errors.RaiseException, statuses: dict[str, int] = INVITE_STATUS
) -> HTTPException:
    code = recusa.diag.message_primary or ""
    if code not in statuses:
        raise recusa
    return HTTPException(status_code=statuses[code], detail=code)


def _redirect_to() -> str:
    return f"{get_settings().dashboard_url.rstrip('/')}{INVITE_LANDING_PATH}"


def _admin_api_failed() -> HTTPException:
    # A causa (só o status do GoTrue) fica na exceção encadeada, no servidor.
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="convite_nao_enviado")


@router.post("/convites", status_code=status.HTTP_201_CREATED)
async def invite_user(
    tenant: CurrentTenant,
    request: UserInvitationRequest,
    auth_admin: Annotated[AuthAdmin, Depends(get_auth_admin)],
) -> UserInvitation:
    """Convida por e-mail com o escopo. O convidado nasce `viewer` (§2.1)."""
    _require_admin(tenant)
    scope = Jsonb([entry.model_dump(mode="json", exclude_none=True) for entry in request.scope])

    async with tenant_scope(tenant) as bound:
        await bound.execute(IDENTITY_SQL, {"email": request.email})
        identities = await bound.fetchall()
        if len(identities) > 1:
            raise RuntimeError("mais de uma identidade no Auth para o mesmo e-mail")
        existing = identities[0] if identities else None
        if existing is not None and existing["is_member"]:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ja_e_membro")
        if existing is not None and existing["active_elsewhere"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="conta_em_outro_cliente"
            )
        try:
            await bound.execute(SCOPE_CHECK_SQL, {"scope": scope, "caller": tenant.user_id})
        except errors.RaiseException as recusa:
            raise _refusal(recusa) from None
        checked = await bound.fetchone()
        if not checked or checked["entries"] == 0:
            # Zero linha aqui seria o parser sem rodar — e o Admin API chamado sem
            # escopo validado. O chamador é membro ativo (o token o resolveu).
            raise RuntimeError("o escopo do convite não foi validado")

    if existing is not None and existing["confirmed"]:
        user_id: UUID = existing["user_id"]
        sent = False
    else:
        # Conta existente sem senha: reenvio, sem `data` — o nome dela fica.
        name = None if existing is not None else request.name
        try:
            user_id = await auth_admin.invite(request.email, _redirect_to(), name)
        except AuthAdminError as falha:
            raise _admin_api_failed() from falha
        if existing is not None and user_id != existing["user_id"]:
            raise RuntimeError("o Admin API respondeu com outra identidade para o mesmo e-mail")
        sent = True

    try:
        async with user_scope(tenant) as scope_cursor:
            await scope_cursor.execute(
                INVITE_SQL, {"tenant_id": tenant.tenant_id, "user_id": user_id, "scope": scope}
            )
    except errors.RaiseException as recusa:
        raise _refusal(recusa) from None

    return UserInvitation(user_id=user_id, email=request.email, invitation_sent=sent)


@router.post("/{user_id}/reenviar-convite")
async def resend_invitation(
    tenant: CurrentTenant,
    user_id: UUID,
    request: InvitationResendRequest,
    auth_admin: Annotated[AuthAdmin, Depends(get_auth_admin)],
) -> InvitationResent:
    """Reenvia o e-mail de convite a um membro deste tenant que ainda não o aceitou.

    "Reenviar convite", nunca "resetar senha" (§5.6): quem já aceitou tem senha
    própria e recebe 409 `convite_ja_aceito`; membro desativado, 409
    `membro_inativo`; quem não é membro deste tenant, 404 `member_not_found`.
    """
    _require_admin(tenant)
    async with tenant_scope(tenant) as bound:
        await bound.execute(RESEND_TARGET_SQL, {"user_id": user_id})
        target = await bound.fetchone()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="member_not_found")
    if not target["active"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="membro_inativo")
    if target["accepted"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="convite_ja_aceito")
    try:
        await auth_admin.invite(target["email"], _redirect_to())
    except AuthAdminError as falha:
        raise _admin_api_failed() from falha
    return InvitationResent(user_id=user_id, email=target["email"])


def _scope_mode(role: UserRole) -> ScopeMode:
    return "by_role" if role in BY_ROLE_ROLES else "by_scope"


def _users(members: list[DictRow], scope_rows: list[DictRow]) -> list[TenantUser]:
    """A montagem da linha, a mesma na lista e no detalhe."""
    scopes: dict[UUID, list[TenantUserScope]] = {}
    for row in scope_rows:
        scopes.setdefault(row["user_id"], []).append(
            TenantUserScope(
                company_id=row["company_id"],
                company_name=row["company_name"],
                unit_id=row["unit_id"],
                unit_name=row["unit_name"],
            )
        )

    users = []
    for m in members:
        role = UserRole(m["role"])
        mode = _scope_mode(role)
        users.append(
            TenantUser(
                user_id=m["user_id"],
                email=m["email"],
                name=m["name"],
                role=role,
                active=m["active"],
                deactivated_at=m["deactivated_at"],
                invitation_accepted=m["invitation_accepted"],
                invited_by=(
                    TenantUserInviter(
                        user_id=m["invited_by"],
                        email=m["invited_by_email"],
                        name=m["invited_by_name"],
                    )
                    if m["invited_by"] is not None
                    else None
                ),
                scope_mode=mode,
                # ⛔ §3.2: para o atalho de papel, o conteúdo de `user_scope` mentiria.
                scope=scopes.get(m["user_id"], []) if mode == "by_scope" else [],
            )
        )
    return users


async def _member(tenant: TenantContext, user_id: UUID) -> TenantUser:
    """O membro DESTE tenant, ou 404 — inclusive membro de outro tenant."""
    params = {"user_id": user_id}
    async with tenant_scope(tenant) as bound:
        await bound.execute(DETAIL_SQL, params)
        members = await bound.fetchall()
        await bound.execute(SCOPE_DETAIL_SQL, params)
        scope_rows = await bound.fetchall()
    if not members:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MEMBER_NOT_FOUND)
    (user,) = _users(members, scope_rows)
    return user


async def _call_rpc(
    tenant: TenantContext, statement: str, params: dict[str, Any], statuses: dict[str, int]
) -> None:
    try:
        async with user_scope(tenant) as cursor:
            await cursor.execute(statement, {"tenant_id": tenant.tenant_id, **params})
    except errors.RaiseException as recusa:
        raise _refusal(recusa, statuses) from None


@router.get("")
async def list_users(tenant: CurrentTenant) -> TenantUserList:
    """Os usuários deste tenant, ativos primeiro, com escopo e quem convidou."""
    _require_admin(tenant)
    async with tenant_scope(tenant) as bound:
        await bound.execute(LIST_SQL)
        members = await bound.fetchall()
        await bound.execute(SCOPE_LIST_SQL)
        scope_rows = await bound.fetchall()
    return TenantUserList(users=_users(members, scope_rows))


# ⛔ Antes de `/{user_id}`: senão "matriz" é lido como um id e recusado (422).
@router.get("/matriz")
async def domain_matrix(tenant: CurrentTenant) -> RoleDomainMatrix:
    """Os domínios sensíveis que cada papel enxerga neste tenant (§6)."""
    _require_admin(tenant)
    async with tenant_scope(tenant) as bound:
        await bound.execute(MATRIX_SQL)
        rows = await bound.fetchall()
    return RoleDomainMatrix(
        roles=[
            RoleDomains(
                role=UserRole(r["role"]), domains=[SensitiveDomain(d) for d in r["domains"]]
            )
            for r in rows
        ]
    )


@router.get("/{user_id}")
async def get_user(tenant: CurrentTenant, user_id: UUID) -> TenantUser:
    """Um membro deste tenant, montado como a linha da lista."""
    _require_admin(tenant)
    return await _member(tenant, user_id)


@router.put("/{user_id}/papel")
async def set_role(tenant: CurrentTenant, user_id: UUID, request: MemberRoleRequest) -> TenantUser:
    """Define o papel. Só o `owner`: para os outros a rota recusa ANTES da RPC,
    que continua sendo a garantia."""
    if tenant.role is not UserRole.OWNER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=NOT_OWNER)
    await _call_rpc(tenant, ROLE_SQL, {"user_id": user_id, "role": request.role.value}, ROLE_STATUS)
    return await _member(tenant, user_id)


@router.put("/{user_id}/escopo")
async def set_scope(
    tenant: CurrentTenant, user_id: UUID, request: MemberScopeRequest
) -> TenantUser:
    """Troca o escopo inteiro. A RPC valida a lista nova antes de apagar a velha."""
    _require_admin(tenant)
    scope = Jsonb([entry.model_dump(mode="json", exclude_none=True) for entry in request.scope])
    await _call_rpc(tenant, SCOPE_SQL, {"user_id": user_id, "scope": scope}, SCOPE_STATUS)
    return await _member(tenant, user_id)


@router.post("/{user_id}/desativar")
async def deactivate_user(
    tenant: CurrentTenant, user_id: UUID, request: MemberDeactivationRequest
) -> TenantUser:
    """`active = false` e a data. Nunca apaga o vínculo."""
    _require_admin(tenant)
    await _call_rpc(tenant, DEACTIVATE_SQL, {"user_id": user_id}, DEACTIVATE_STATUS)
    return await _member(tenant, user_id)
