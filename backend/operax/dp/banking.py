"""Conta bancária — o único módulo em que o número completo encosta em código.

REGRA 10 DO `PRD-DP.md`, POR CONSTRUÇÃO E NÃO POR DISCIPLINA
A conta nunca chega ao navegador. O que faz isso valer não é uma revisão
lembrando de mascarar em cada rota nova: é o **tipo** que sai daqui.
`MaskedBankAccount` não tem campo para o número completo, então uma rota futura
que devolva o objeto inteiro continua devolvendo máscara — não há o que vazar.

A única função que devolve o número inteiro é a que monta o arquivo de remessa,
que escreve em `bytes` e nunca em JSON. **Ela ainda não existe** (é S3): nesta
sprint existe a máscara, e é por isso que `_row_to_masked` é o único caminho de
saída do `select`. Quando a remessa chegar, ela nasce aqui, ao lado, e não numa
segunda cópia deste SQL espalhada pelo backend.

⚠️ A MÁSCARA NÃO É DA COLUNA
No banco o número é inteiro, porque a remessa precisa dele. A fronteira é esta
camada, e é aqui que ela é testada — `tests/test_dp_banking.py` varre o JSON da
resposta, em vez de reler o código.

DUAS IDENTIDADES, COMO EM `operax/rh/repository.py`
Quem a pessoa é, e se quem pergunta a enxerga, é resolvido por `user_scope`: a
transação vira o usuário autenticado e as policies que já guardam o navegador
decidem. Só depois a escrita acontece por `tenant_scope`, porque `app.audit_log`
não concede insert a ninguém além de `service_role` e a linha e a trilha que a
descreve têm de commitar juntas.

TRÊS EIXOS PARA ESCREVER, E É O BACKEND QUEM DE FATO OS APLICA
A policy `employee_bank_account_write` exige domínio, pessoa e `util.is_admin`.
Ela não é o que barra hoje: o backend conecta como `postgres`, que é
`rolbypassrls`, então a policy passa direto (`SPRINTS-DP.md` §2a-bis). Quem
autoriza é esta camada — por isso as três perguntas são feitas ao banco, com as
MESMAS funções que a policy chama, e não deduzidas do papel que o token traz.
`util.is_admin` é `role in ('owner','hr','personnel')`: sem ela, `accounting`
teria `banking` e gravaria conta bancária sem ser admin.

⛔ A TRILHA TAMBÉM É MASCARADA
`app.audit_log` é lido por outras telas e cresce para sempre. Gravar o número
completo ali seria a segunda cópia que este módulo existe para não permitir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from operax.core.tenant import TenantContext, tenant_scope, user_scope
from operax.rh.repository import audit

_MASK_CHAR = "•"
_VISIBLE = 4


class BankAccountError(RuntimeError):
    """A gravação não encontrou a linha que acabou de escrever."""


def mask_account(account: str) -> str:
    """`'•••• 8723'` — a forma que a tela mostra, e a única que sai daqui.

    Conta curta demais para ter cauda é mascarada inteira: devolver o número todo
    porque ele é pequeno seria a máscara falhando exatamente onde ela é a única
    proteção. Nenhuma conta brasileira é assim, e é por isso que o caso passaria
    despercebido se dependesse de dado real.
    """
    limpa = account.strip()
    if len(limpa) <= _VISIBLE:
        return _MASK_CHAR * _VISIBLE
    return f"{_MASK_CHAR * _VISIBLE} {limpa[-_VISIBLE:]}"


@dataclass(frozen=True, slots=True)
class MaskedBankAccount:
    """A conta como o resto do produto pode vê-la.

    Não existe campo para o número completo, e a ausência é o desenho: um tipo
    que não carrega o dado não o vaza por descuido de serialização.
    """

    employee_id: UUID
    bank_code: str
    branch: str
    account_masked: str
    account_type: str
    holder_document: str | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class BankingPermissions:
    """O que o banco responde sobre quem está pedindo — nunca o que o token diz.

    Dois campos e não um: ler a conta pede `banking`, gravá-la pede `banking` e
    ser admin. `accounting` é exatamente quem separa os dois — ele concilia a
    remessa e não escreve nela.
    """

    banking: bool
    admin: bool


def _row_to_masked(row: dict[str, Any]) -> MaskedBankAccount:
    return MaskedBankAccount(
        employee_id=row["employee_id"],
        bank_code=row["bank_code"],
        branch=row["branch"],
        account_masked=mask_account(row["account"]),
        account_type=row["account_type"],
        holder_document=row["holder_document"],
        updated_at=row["updated_at"],
    )


def _trail(row: dict[str, Any]) -> dict[str, Any]:
    """O que a auditoria guarda: tudo, menos o número."""
    return {
        "bank_code": row["bank_code"],
        "branch": row["branch"],
        "account": mask_account(row["account"]),
        "account_type": row["account_type"],
        "holder_document": row["holder_document"],
    }


_PERMISSIONS_SQL = """
    select util.can_see_domain(%(tenant_id)s, 'banking') as banking,
           util.is_admin(%(tenant_id)s)                  as admin
"""

# Como o usuário: a policy de `app.employee` é quem responde se ele enxerga a
# pessoa. Reimplementar `util.can_see_employee` aqui seria a mesma regra escrita
# duas vezes, em duas linguagens, divergindo na primeira mudança de policy.
_EMPLOYEE_SQL = """
    select e.id
    from app.employee e
    where e.id = %(employee_id)s
"""

_LOAD_SQL = """
    select a.employee_id, a.bank_code, a.branch, a.account, a.account_type,
           a.holder_document, a.updated_at
    from app.employee_bank_account a
    where a.employee_id = %(employee_id)s
      and a.tenant_id = %(tenant_id)s
"""

_UPSERT_SQL = """
    insert into app.employee_bank_account
      (employee_id, tenant_id, bank_code, branch, account, account_type,
       holder_document, updated_at)
    values
      (%(employee_id)s, %(tenant_id)s, %(bank_code)s, %(branch)s, %(account)s,
       %(account_type)s, %(holder_document)s, now())
    on conflict (employee_id) do update
       set bank_code       = excluded.bank_code,
           branch          = excluded.branch,
           account         = excluded.account,
           account_type    = excluded.account_type,
           holder_document = excluded.holder_document,
           updated_at      = now()
     where employee_bank_account.tenant_id = %(tenant_id)s
    returning employee_id, bank_code, branch, account, account_type,
              holder_document, updated_at
"""


async def check_permissions(tenant: TenantContext) -> BankingPermissions:
    """Os dois eixos que não dependem da pessoa, perguntados ao banco como quem perguntou.

    São as mesmas funções que as policies chamam. Reimplementar `is_admin` aqui
    como `role in (...)` seria a regra escrita duas vezes, e a matriz de papéis
    muda por `UPDATE` — a cópia divergiria sem ninguém notar.
    """
    async with user_scope(tenant) as scope:
        await scope.execute(_PERMISSIONS_SQL, {"tenant_id": tenant.tenant_id})
        row = await scope.fetchone()
    return BankingPermissions(
        banking=bool(row and row["banking"]),
        admin=bool(row and row["admin"]),
    )


async def resolve_employee(tenant: TenantContext, employee_id: UUID) -> UUID | None:
    """A pessoa, se quem pergunta a enxerga. `None` cobre os dois casos de propósito.

    Inexistente e fora do escopo respondem igual: distinguir os dois confirmaria
    que alguém existe noutra unidade.
    """
    async with user_scope(tenant) as scope:
        await scope.execute(_EMPLOYEE_SQL, {"employee_id": employee_id})
        row = await scope.fetchone()
    return row["id"] if row else None


async def save_account(
    tenant: TenantContext,
    employee_id: UUID,
    *,
    bank_code: str,
    branch: str,
    account: str,
    account_type: str,
    holder_document: str | None,
) -> MaskedBankAccount:
    """Grava a conta e a trilha na mesma transação, e devolve a máscara.

    A resposta sai do que o banco gravou, e não do que o cliente enviou — inclusive
    logo depois da escrita. É a diferença entre "mascarei o que devolvi" e "só
    existe máscara para devolver".
    """
    async with tenant_scope(tenant) as scope:
        await scope.execute(_LOAD_SQL, {"employee_id": employee_id})
        anterior = await scope.fetchone()

        await scope.execute(
            _UPSERT_SQL,
            {
                "employee_id": employee_id,
                "bank_code": bank_code,
                "branch": branch,
                "account": account,
                "account_type": account_type,
                "holder_document": holder_document,
            },
        )
        gravada = await scope.fetchone()
        if gravada is None:
            raise BankAccountError(
                f"a conta de {employee_id} não foi gravada; a linha existente é de outro tenant"
            )

        await audit(
            scope,
            tenant,
            action="update" if anterior else "insert",
            entity="employee_bank_account",
            entity_id=employee_id,
            antes=_trail(dict(anterior)) if anterior else None,
            depois=_trail(dict(gravada)),
            origem={"route": "PATCH /dp/colaboradores/{id}/conta"},
        )

    return _row_to_masked(dict(gravada))
