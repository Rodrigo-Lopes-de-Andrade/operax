"""Departamento Pessoal — o Caminho 2 das rotinas de DP.

Nesta sprint há uma rota só: a conta bancária, que é insumo obrigatório do
arquivo de remessa do vale transporte. O ciclo mensal, o apurador e a remessa
propriamente dita são S3 e não existem ainda.

⛔ A RESPOSTA É SEMPRE MASCARADA, INCLUSIVE LOGO DEPOIS DA ESCRITA
Regra 10 do `PRD-DP.md`. Quem garante isso não é esta rota lembrando de mascarar
— é o tipo que `operax/dp/banking.py` devolve, que não tem campo para o número
completo. A rota não teria como vazar a conta nem se quisesse.

TRÊS EIXOS, REVALIDADOS AQUI PORQUE É AQUI QUE ELES VALEM
`service_role` não é filtrado por policy — e o papel de conexão é `rolbypassrls`
(`SPRINTS-DP.md` §2a-bis), então a policy `employee_bank_account_write` não é o
que barra ninguém hoje. Quem autoriza é esta rota, e por isso ela repete os três
eixos da policy, perguntados ao banco: o domínio `banking`, o papel
(`util.is_admin`) e a pessoa, resolvida por `user_scope` — se ele não a enxerga,
ela não existe para esta rota.

⛔ O TERCEIRO EIXO É O QUE SEPARA LER DE ESCREVER
`accounting` tem `banking` e não é admin: ele concilia a remessa e não redigita a
conta. Sem `util.is_admin` aqui, ele seria o único papel do produto a gravar dado
sensível sem ser admin — e conta bancária é o campo que redireciona pagamento.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from operax.dp import banking
from server.deps import CurrentTenant
from server.models import BankAccountMasked, BankAccountPatch

router = APIRouter(prefix="/dp", tags=["dp"])


@router.patch("/colaboradores/{employee_id}/conta")
async def gravar_conta(
    employee_id: UUID, payload: BankAccountPatch, tenant: CurrentTenant
) -> BankAccountMasked:
    """Grava a conta do colaborador e devolve o que ficou gravado, mascarado."""
    permissoes = await banking.check_permissions(tenant)
    if not permissoes.banking:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu papel não alcança o domínio de dados bancários.",
        )
    # O papel vem antes da pessoa de propósito: quem não pode gravar não descobre
    # aqui se o colaborador existe.
    if not permissoes.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Alterar conta bancária exige papel administrativo. "
            "Seu papel consulta a conta, mas não a altera.",
        )

    if await banking.resolve_employee(tenant, employee_id) is None:
        # Fora do alcance e inexistente respondem igual: um 403 aqui confirmaria
        # que a pessoa existe noutra unidade.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Colaborador não encontrado."
        )

    conta = await banking.save_account(
        tenant,
        employee_id,
        bank_code=payload.bank_code,
        branch=payload.branch,
        account=payload.account,
        account_type=payload.account_type,
        holder_document=payload.holder_document,
    )
    return BankAccountMasked(
        employee_id=conta.employee_id,
        bank_code=conta.bank_code,
        branch=conta.branch,
        account_masked=conta.account_masked,
        account_type=conta.account_type,
        holder_document=conta.holder_document,
        updated_at=conta.updated_at,
    )
