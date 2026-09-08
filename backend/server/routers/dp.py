"""Departamento Pessoal — o Caminho 2 das rotinas de DP.

Quatro assuntos aqui: a conta bancária (S2), o Quadro de Postos e o catálogo de
verbas com vigência (S1), e a rotina mensal de cesta e vale transporte, com os
três arquivos que ela exporta (S3).

⛔ QUEM AUTORIZA É A ROTA, NÃO A POLICY
Vale para as cinco. O papel de conexão é `rolbypassrls` (`SPRINTS-DP.md` §2a-bis),
então nenhuma das policies desta etapa barra ninguém no Caminho 2 — elas ficam de
pé para o dia em que o papel mudar, e para o caso de um PR futuro conceder
`select` a `authenticated` por engano. O que barra hoje é o que está escrito
abaixo, perguntado ao banco pelas **mesmas funções** que as policies chamam.

E os eixos diferem por assunto, porque as tabelas diferem. Posto é estrutura da
unidade: os eixos são `util.can_see_unit` para ler e `util.is_admin` mais a
unidade para escrever — não há domínio sensível a perguntar, e exigir um seria
cerimônia. Verba é dinheiro de pessoa: domínio `compensation` para ler, e
`compensation` mais `util.is_admin` para escrever.

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

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from operax.core.tenant import tenant_scope
from operax.dp import banking, beneficios, ciclo, export, laudos, painel, postos, rubricas
from operax.rh.repository import audit, check_permissions
from server.deps import CurrentTenant
from server.models import (
    AdjustedBandRow,
    BankAccountMasked,
    BankAccountPatch,
    BenefitAdjustment,
    BenefitCatalog,
    BenefitPlanCreate,
    BenefitPlanRow,
    BenefitTypeRow,
    ComplianceReportCreate,
    ComplianceReportList,
    ComplianceReportRenewal,
    ComplianceReportRow,
    CycleEntitlementRow,
    CycleList,
    CycleRequest,
    CycleSummary,
    CycleView,
    DpPanel,
    NewBandRow,
    PayrollCodeList,
    PayrollCodePatch,
    PayrollCodeRow,
    TransportFareCreate,
    TransportFareRow,
    WorkPostCreate,
    WorkPostList,
    WorkPostPatch,
    WorkPostRow,
)

router = APIRouter(prefix="/dp", tags=["dp"])

_SEM_COMPENSATION = "Seu papel não alcança o domínio de remuneração."
_SEM_ADMIN = "Seu papel consulta este cadastro, mas não o altera."


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


# ---------------------------------------------------------------------------
# Quadro de Postos
# ---------------------------------------------------------------------------
def _posto(post: postos.WorkPost) -> WorkPostRow:
    return WorkPostRow(
        id=post.id,
        unit_id=post.unit_id,
        unit_name=post.unit_name,
        code=post.code,
        name=post.name,
        active=post.active,
        created_at=post.created_at,
    )


@router.get("/postos")
async def listar_postos(
    tenant: CurrentTenant,
    unidade: Annotated[UUID | None, Query(description="Filtra por unidade")] = None,
) -> WorkPostList:
    """O Quadro das unidades que quem pergunta enxerga.

    Sem checagem de domínio: posto é estrutura da unidade, não dado de pessoa. O
    recorte vem de `util.can_see_unit`, pela policy de `app.unit` — o supervisor
    de uma unidade recebe o quadro dela e nada mais.
    """
    permissoes = await check_permissions(tenant)
    quadro = await postos.list_posts(tenant, unit_id=unidade)
    return WorkPostList(rows=[_posto(post) for post in quadro], can_write=permissoes.admin)


@router.post("/postos", status_code=status.HTTP_201_CREATED)
async def criar_posto(payload: WorkPostCreate, tenant: CurrentTenant) -> WorkPostRow:
    """Cria um posto na unidade. Administração, e só na unidade que ela enxerga."""
    permissoes = await check_permissions(tenant)
    if not permissoes.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_SEM_ADMIN)

    # O papel vem antes da unidade de propósito: quem não pode escrever não
    # descobre aqui se a unidade existe.
    if not await postos.can_see_unit(tenant, payload.unit_id):
        # Fora do alcance e inexistente respondem igual — inclusive unidade de
        # outro tenant, que `util.can_see_unit` recusa pelo mesmo caminho.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unidade não encontrada.")

    try:
        criado = await postos.create_post(
            tenant, unit_id=payload.unit_id, code=payload.code, name=payload.name
        )
    except postos.DuplicateWorkPostError as choque:
        # 409 e não 422: o pedido está bem formado, o estado é que não permite.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(choque)) from choque
    return _posto(criado)


@router.patch("/postos/{post_id}")
async def alterar_posto(
    post_id: UUID, payload: WorkPostPatch, tenant: CurrentTenant
) -> WorkPostRow:
    """Renomeia ou tira de operação. Não existe rota que apague um posto."""
    permissoes = await check_permissions(tenant)
    if not permissoes.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_SEM_ADMIN)

    anterior = await postos.load_post(tenant, post_id)
    # A unidade do posto é conferida depois de ele ser encontrado, e as duas
    # recusas são o mesmo 404: um 403 aqui confirmaria que o posto existe noutra
    # unidade.
    if anterior is None or not await postos.can_see_unit(tenant, anterior.unit_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Posto não encontrado.")

    gravado = await postos.update_post(
        tenant, post_id, anterior=anterior, name=payload.name, active=payload.active
    )
    return _posto(gravado)


# ---------------------------------------------------------------------------
# Catálogo de verbas e reajuste
# ---------------------------------------------------------------------------
@router.get("/beneficios/catalogo")
async def catalogo_de_beneficios(
    tenant: CurrentTenant,
    em: Annotated[
        date | None, Query(description="Data da vigência consultada; ausente = hoje")
    ] = None,
) -> BenefitCatalog:
    """O catálogo como ele valia em `em` — preço tem vigência, e a resposta diz qual.

    Domínio `compensation`: o catálogo é a tabela de preços da remuneração, e
    `composes_base` é a definição do KPI de custo de pessoal.
    """
    permissoes = await check_permissions(tenant)
    if not permissoes.compensation:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_SEM_COMPENSATION)

    on = em or date.today()
    catalogo = await beneficios.read_catalog(tenant, on=on)
    return BenefitCatalog(
        on=catalogo.on,
        types=[
            BenefitTypeRow(
                code=tipo.code,
                name=tipo.name,
                composes_base=tipo.composes_base,
                calculation=tipo.calculation,
                domain=tipo.domain,
                active=tipo.active,
            )
            for tipo in catalogo.types
        ],
        plans=[
            BenefitPlanRow(
                id=plano.id,
                benefit_type_code=plano.benefit_type_code,
                code=plano.code,
                provider=plano.provider,
                name=plano.name,
                amount=plano.amount,
                effective_from=plano.effective_from,
                effective_to=plano.effective_to,
                reason=plano.reason,
            )
            for plano in catalogo.plans
        ],
        fares=[
            TransportFareRow(
                id=tarifa.id,
                code=tarifa.code,
                name=tarifa.name,
                kind=tarifa.kind,
                amount=tarifa.amount,
                effective_from=tarifa.effective_from,
                effective_to=tarifa.effective_to,
                reason=tarifa.reason,
            )
            for tarifa in catalogo.fares
        ],
        can_write=permissoes.admin,
    )


@router.post("/beneficios/reajuste", status_code=status.HTTP_201_CREATED)
async def reajustar(payload: BenefitAdjustment, tenant: CurrentTenant) -> AdjustedBandRow:
    """Abre a vigência nova e fecha a anterior. ⛔ Não existe `PUT` no valor.

    O verbo é `POST` porque o que acontece é uma criação: a faixa que sai mantém
    o valor que valeu, porque o ciclo do mês passado foi apurado com ele.
    """
    permissoes = await check_permissions(tenant)
    if not permissoes.compensation:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_SEM_COMPENSATION)
    if not permissoes.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reajustar exige papel administrativo. "
            "Seu papel consulta o catálogo, mas não altera preço.",
        )

    try:
        if payload.target == "plan":
            banda = await beneficios.adjust_plan(
                tenant,
                code=payload.code,
                effective_from=payload.effective_from,
                amount=payload.amount,
                reason=payload.reason,
            )
        else:
            # `kind` é obrigatório para tarifa, e quem garante isso é
            # `BenefitAdjustment._kind_combina_com_o_alvo` — o pedido sem ele nem
            # chega aqui, volta 422 do próprio schema.
            banda = await beneficios.adjust_fare(
                tenant,
                code=payload.code,
                kind=payload.kind,
                effective_from=payload.effective_from,
                amount=payload.amount,
                reason=payload.reason,
            )
    except beneficios.OpenBandNotFoundError as ausente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ausente)) from ausente
    except beneficios.BandOverlapError as sobreposicao:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(sobreposicao)
        ) from sobreposicao
    except beneficios.OpenBandConflictError as choque:
        # 409 e não 500: o pedido está bem formado e nada ficou gravado pela
        # metade — outro reajuste da mesma identidade chegou primeiro. Mesma
        # tradução que `POST /dp/postos` faz do choque de código duplicado.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(choque)) from choque

    return AdjustedBandRow(
        target=banda.target,
        id=banda.id,
        code=banda.code,
        kind=banda.kind,
        name=banda.name,
        amount=banda.amount,
        effective_from=banda.effective_from,
        reason=banda.reason,
        previous_id=banda.previous_id,
        previous_amount=banda.previous_amount,
        previous_effective_to=banda.previous_effective_to,
    )


# ---------------------------------------------------------------------------
# A primeira vigência — a porta que faltava
# ---------------------------------------------------------------------------
# ⛔ DUAS ROTAS, E NÃO UMA QUE "CRIA OU REAJUSTA"
# Decisão do dono, 06/09/2026. Uma porta só transformaria um código digitado
# errado no formulário de reajuste num plano novo, calado — e o preço antigo
# continuaria valendo para quem já estava lá. Os eixos são os do reajuste:
# `compensation` para alcançar o catálogo, `util.is_admin` para mexer em preço.
async def _pode_escrever_catalogo(tenant: CurrentTenant) -> None:
    permissoes = await check_permissions(tenant)
    if not permissoes.compensation:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_SEM_COMPENSATION)
    if not permissoes.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cadastrar preço exige papel administrativo. "
            "Seu papel consulta o catálogo, mas não define valor.",
        )


def _nova_banda(banda: beneficios.NewBand) -> NewBandRow:
    return NewBandRow(
        target=banda.target,
        id=banda.id,
        code=banda.code,
        kind=banda.kind,
        name=banda.name,
        amount=banda.amount,
        effective_from=banda.effective_from,
        reason=banda.reason,
    )


@router.post("/beneficios/planos", status_code=status.HTTP_201_CREATED)
async def criar_plano(payload: BenefitPlanCreate, tenant: CurrentTenant) -> NewBandRow:
    """A primeira vigência de um plano. Para mudar o valor depois, use o reajuste."""
    await _pode_escrever_catalogo(tenant)
    try:
        banda = await beneficios.create_plan(
            tenant,
            benefit_type_code=payload.benefit_type_code,
            code=payload.code,
            provider=payload.provider,
            name=payload.name,
            effective_from=payload.effective_from,
            amount=payload.amount,
            reason=payload.reason,
        )
    except beneficios.UnknownBenefitTypeError as ausente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ausente)) from ausente
    except beneficios.BandAlreadyExistsError as choque:
        # 409 e não 422: o pedido está bem formado, o estado é que não permite —
        # e a saída é o reajuste, que a mensagem nomeia.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(choque)) from choque
    return _nova_banda(banda)


@router.post("/beneficios/tarifas", status_code=status.HTTP_201_CREATED)
async def criar_tarifa(payload: TransportFareCreate, tenant: CurrentTenant) -> NewBandRow:
    """A primeira tarifa de uma linha. A unitária e a ida-e-volta são dois pedidos."""
    await _pode_escrever_catalogo(tenant)
    try:
        banda = await beneficios.create_fare(
            tenant,
            code=payload.code,
            name=payload.name,
            kind=payload.kind,
            effective_from=payload.effective_from,
            amount=payload.amount,
            reason=payload.reason,
        )
    except beneficios.BandAlreadyExistsError as choque:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(choque)) from choque
    return _nova_banda(banda)


# ---------------------------------------------------------------------------
# O ciclo mensal
# ---------------------------------------------------------------------------
# ⛔ APURAR É `compensation` + ADMIN; CONFERIR A REMESSA É `compensation` +
#    `banking`, E NÃO EXIGE ADMIN
# `accounting` tem os dois domínios e não é admin: ele concilia a remessa e não
# apura a competência de ninguém. Exigir admin no download da remessa trancaria
# fora exatamente o papel que existe para conferi-la — e uma trava que barra o
# legítimo é pior que a ausência dela.
_SEM_BANKING = "Seu papel não alcança o domínio de dados bancários."


def _linha(linha: ciclo.EntitlementLine) -> CycleEntitlementRow:
    return CycleEntitlementRow(
        employee_id=linha.employee_id,
        name=linha.name,
        registration_number=linha.registration_number,
        unit_id=linha.unit_id,
        unit_name=linha.unit_name,
        entitled=linha.entitled,
        reason=linha.reason,
        days_base=linha.days_base,
        absences_prior=linha.absences_prior,
        net_days=linha.net_days,
        unit_amount=linha.unit_amount,
        round_trip_amount=linha.round_trip_amount,
        total_amount=linha.total_amount,
    )


async def pode_exportar_remessa(tenant: CurrentTenant) -> bool:
    """O eixo da remessa, perguntado ao banco. **Uma implementação só.**

    ⛔ O CAMPO E A GUARDA SAEM DAQUI, E É ISSO QUE OS FAZ CONCORDAR
    Um `can_export_remittance` que a rota calcula e que a guarda real não usa
    seria pior que campo nenhum: a tela esconderia o botão e o endpoint
    continuaria aceitando: uma falsa sensação de trava, do tipo que só se
    descobre quando alguém digita a URL. Com uma função, quem não vê o botão
    recebe 403 pela mesma resposta do banco — e
    `test_o_botao_e_a_guarda_concordam` percorre a matriz inteira provando isso.

    ⚠️ `banking` e NÃO `is_admin`: `accounting` confere a remessa sem apurar.
    """
    return (await banking.check_permissions(tenant)).banking


def _ciclo(cycle: ciclo.Cycle, *, can_export_remittance: bool) -> CycleView:
    return CycleView(
        can_export_remittance=can_export_remittance,
        id=cycle.id,
        kind=cycle.kind,
        period_year=cycle.period_year,
        period_month=cycle.period_month,
        window_start=cycle.window_start,
        window_end=cycle.window_end,
        business_days=cycle.business_days,
        status=cycle.status,
        entitled_count=cycle.entitled_count,
        denied_count=cycle.denied_count,
        total_amount=cycle.total_amount,
        rows=[_linha(linha) for linha in cycle.lines],
    )


def _recusa_de_apuracao(erro: ciclo.CycleError) -> HTTPException:
    """As recusas do apurador viram 422, e o texto delas é o que a pessoa conserta.

    422 e não 500: o pedido está bem formado e o produto está funcionando — o que
    falta é dado (curadoria, jornada materializada, tarifa vigente). Um 500 aqui
    diria "erro do sistema" sobre algo que só quem opera pode resolver, e o texto
    se perderia no Sentry em vez de chegar à tela.
    """
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(erro))


@router.post("/ciclos", status_code=status.HTTP_201_CREATED)
async def apurar_ciclo(payload: CycleRequest, tenant: CurrentTenant) -> CycleView:
    """Apura a competência e devolve o preview. Nada aqui é definitivo.

    O que fica gravado é um ciclo em `draft` com as linhas dele — e rascunho não
    é linha definitiva: reapurar a mesma competência refaz as MESMAS linhas, sem
    duplicar ninguém. O que congela é `POST /dp/ciclos/{id}/gerar`, e ele não
    reapura: o número que o gestor conferiu é o número que vai para a remessa.
    """
    await _pode_escrever_catalogo(tenant)
    try:
        apurado = await ciclo.compute_cycle(
            tenant,
            kind=payload.kind,
            period_year=payload.period_year,
            period_month=payload.period_month,
        )
        gravado = await ciclo.save_draft(tenant, apurado)
    except ciclo.CycleAlreadyGeneratedError as choque:
        # ⛔ ANTES do `except CycleError`, que é a base dela: apanhada lá, esta
        # recusa viraria 422 ("falta dado"), e o que falta não é dado — a
        # competência está congelada. 409 é o mesmo que `POST /gerar` já responde
        # para a mesma situação, e a tela não precisa aprender uma segunda frase.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(choque)) from choque
    except ciclo.CycleError as recusa:
        raise _recusa_de_apuracao(recusa) from recusa
    return _ciclo(gravado, can_export_remittance=await pode_exportar_remessa(tenant))


@router.post("/ciclos/{cycle_id}/gerar")
async def gerar_ciclo(cycle_id: UUID, tenant: CurrentTenant) -> CycleView:
    """Congela o rascunho. A partir daqui, correção é ciclo novo com motivo."""
    await _pode_escrever_catalogo(tenant)
    if await ciclo.load_cycle(tenant, cycle_id) is None:
        # Inexistente e de outro tenant respondem igual.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ciclo não encontrado.")
    try:
        congelado = await ciclo.freeze(tenant, cycle_id)
    except ciclo.CycleAlreadyGeneratedError as choque:
        # 409: o pedido está bem formado, o estado é que não permite.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(choque)) from choque
    return _ciclo(congelado, can_export_remittance=await pode_exportar_remessa(tenant))


@router.get("/ciclos")
async def listar_ciclos(
    tenant: CurrentTenant,
    kind: Annotated[
        Literal["food_basket", "transport_voucher"] | None,
        Query(description="Filtra por tipo de ciclo"),
    ] = None,
    situacao: Annotated[
        Literal["draft", "generated", "exported", "cancelled"] | None,
        Query(description="Filtra por status"),
    ] = None,
    ano: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    mes: Annotated[int | None, Query(ge=1, le=12)] = None,
) -> CycleList:
    """As competências já apuradas. Leitura: `compensation`, **sem admin**.

    ⛔ SEM ADMIN DE PROPÓSITO, e é metade do motivo de esta rota existir.
    `accounting` baixa a remessa sem ser admin (decisão do S3) e não tinha por
    onde chegar a um ciclo: o `id` só nascia na resposta do `POST /dp/ciclos`,
    que exige admin. Exigir admin aqui devolveria a mesma parede uma porta
    adiante.

    ⚠️ A outra metade: recarregar a página perdia o ciclo congelado, e
    reencontrá-lo obrigava a apurar de novo — o que **cria um segundo rascunho
    ao lado do gerado**, porque o `unique` da competência inclui o `status`.
    """
    permissoes = await check_permissions(tenant)
    if not permissoes.compensation:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_SEM_COMPENSATION)

    competencias = await ciclo.list_cycles(
        tenant, kind=kind, status=situacao, period_year=ano, period_month=mes
    )
    return CycleList(
        rows=[
            CycleSummary(
                id=resumo.id,
                kind=resumo.kind,
                period_year=resumo.period_year,
                period_month=resumo.period_month,
                window_start=resumo.window_start,
                window_end=resumo.window_end,
                business_days=resumo.business_days,
                status=resumo.status,
                entitled_count=resumo.entitled_count,
                denied_count=resumo.denied_count,
                total_amount=resumo.total_amount,
            )
            for resumo in competencias
        ],
        can_export_remittance=await pode_exportar_remessa(tenant),
    )


_EXPORTS: dict[str, tuple[str, str]] = {
    "xlsx": (export.XLSX_CONTENT_TYPE, "xlsx"),
    "pdf": (export.PDF_CONTENT_TYPE, "pdf"),
    "banco": (export.REMITTANCE_CONTENT_TYPE, "txt"),
}


@router.get("/ciclos/{cycle_id}/export")
async def exportar_ciclo(
    cycle_id: UUID,
    tenant: CurrentTenant,
    formato: Annotated[Literal["xlsx", "pdf", "banco"], Query(description="Formato do arquivo")],
) -> Response:
    """Os três arquivos do ciclo. `banco` exige o domínio bancário.

    ⛔ A RESPOSTA É `bytes`, E É POR ISSO QUE A CONTA PODE ESTAR DENTRO
    Nenhum schema Pydantic participa desta rota. `CycleEntitlementRow` não tem
    campo de conta, então nenhuma outra rota do produto poderia devolvê-la nem
    querendo — e esta devolve um arquivo, não um objeto.

    ⚠️ `GET` NÃO MUDA ESTADO, e por isso baixar não marca o ciclo como
    `exported`. O valor existe no check da SPEC e a trava do banco já o cobre;
    quem o escrever escreverá por uma ação própria, não por um download.
    """
    permissoes = await check_permissions(tenant)
    if not permissoes.compensation:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_SEM_COMPENSATION)

    cycle = await ciclo.load_cycle(tenant, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ciclo não encontrado.")

    content_type, extensao = _EXPORTS[formato]
    if formato == "xlsx":
        corpo = export.build_xlsx(cycle)
    elif formato == "pdf":
        corpo = export.build_pdf(cycle)
    else:
        corpo = await _remessa(tenant, cycle_id, cycle)

    nome = f"{cycle.kind}-{cycle.period_year}-{cycle.period_month:02d}.{extensao}"
    return Response(
        content=corpo,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


async def _remessa(tenant: CurrentTenant, cycle_id: UUID, cycle: ciclo.Cycle) -> bytes:
    """A remessa, com o eixo bancário e a trilha que a `SPEC-DP.md` §5 exige."""
    if not await pode_exportar_remessa(tenant):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_SEM_BANKING)

    # ⛔ O ESTADO É CONFERIDO ANTES DE AS CONTAS SEREM LIDAS
    # `build_remittance` confere de novo — é a mesma função, e é ela que fecha o
    # caminho para qualquer chamador futuro. Aqui a chamada é adiantada por um
    # motivo próprio: buscar número de conta de um ciclo que não pode pagar é
    # leitura de dado sensível sem motivo nenhum.
    try:
        export.ensure_payable(cycle)
    except export.DraftRemittanceError as rascunho:
        # 409 e não 422: o pedido está bem formado, o estado é que não permite —
        # e a saída é `POST /dp/ciclos/{id}/gerar`, que a mensagem nomeia.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(rascunho)
        ) from rascunho
    except export.RemittanceError as recusa:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(recusa)
        ) from recusa

    contas = await banking.load_accounts(
        tenant, [linha.employee_id for linha in cycle.lines if linha.entitled]
    )
    arquivo, sem_conta = export.build_remittance(cycle, contas)

    # "audit_log em toda leitura que monte remessa — quem gerou, quando, para
    # qual ciclo" (SPEC §5). A trilha é mascarada: gravar o número inteiro nela
    # seria a segunda cópia que `operax/dp/banking.py` existe para não permitir.
    async with tenant_scope(tenant) as scope:
        await audit(
            scope,
            tenant,
            action="export",
            entity="benefit_cycle",
            entity_id=cycle_id,
            antes=None,
            depois=export.remittance_trail(cycle, contas, sem_conta),
            origem={"route": "GET /dp/ciclos/{id}/export?formato=banco"},
        )
    return arquivo


# ---------------------------------------------------------------------------
# O painel de DP
# ---------------------------------------------------------------------------
@router.get("/painel")
async def painel_de_dp(
    tenant: CurrentTenant,
    unidade: Annotated[
        UUID | None, Query(description="Filtra pela unidade de ATUAÇÃO, não pela lotação")
    ] = None,
    empresa: Annotated[UUID | None, Query(description="Filtra pela empresa do colaborador")] = None,
    em: Annotated[date | None, Query(description="Data da leitura; ausente = hoje")] = None,
) -> DpPanel:
    """Os nove KPIs de topo. **Caminho 2, e a decisão está no `painel.py`.**

    ⛔ `compensation` PARA LER, SEM ADMIN
    A folha base é dinheiro de pessoa, então o domínio é obrigatório; ser
    administrador não é. `executive` e `accounting` têm `compensation` e não são
    admin — são exatamente os papéis que existem para olhar este painel, e exigir
    admin trancaria fora quem ele serve. Mesma escolha de `GET /dp/ciclos`.

    ⛔ O ESCOPO NÃO É REVALIDADO AQUI, E ISSO É DE PROPÓSITO
    A população é lida sob `user_scope`, com a RLS de pé: quem não enxerga a
    unidade não recebe a linha, pela policy `employee_read`. Repetir o recorte
    neste arquivo seria `util.can_see_unit` escrito uma segunda vez, em Python, e
    a segunda cópia é a que diverge na primeira mudança de policy.
    """
    permissoes = await check_permissions(tenant)
    if not permissoes.compensation:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_SEM_COMPENSATION)

    kpis = await painel.read_panel(
        tenant, on=em or date.today(), unit_id=unidade, company_id=empresa
    )
    return DpPanel(
        on=kpis.on,
        total_analyzed=kpis.total_analyzed,
        active_headcount=kpis.active_headcount,
        terminations=kpis.terminations,
        retention=kpis.retention,
        base_payroll=kpis.base_payroll,
        base_payroll_average=kpis.base_payroll_average,
        meal_voucher=kpis.meal_voucher,
        cost_allowance=kpis.cost_allowance,
        trust_and_hazard=kpis.trust_and_hazard,
        without_salary=kpis.without_salary,
        units_with_open_installment=kpis.units_with_open_installment,
    )


# ---------------------------------------------------------------------------
# Laudos por unidade
# ---------------------------------------------------------------------------
_LAUDO_NAO_ENCONTRADO = "Laudo não encontrado."


def _laudo(report: laudos.ComplianceReport) -> ComplianceReportRow:
    return ComplianceReportRow(
        id=report.id,
        unit_id=report.unit_id,
        unit_name=report.unit_name,
        type=report.type,
        valid_until=report.valid_until,
        days_to_expiry=report.days_to_expiry,
        renewal_count=report.renewal_count,
        notes=report.notes,
        created_at=report.created_at,
    )


async def _pode_escrever_laudo(tenant: CurrentTenant) -> None:
    permissoes = await check_permissions(tenant)
    if not permissoes.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_SEM_ADMIN)


@router.get("/laudos")
async def listar_laudos(
    tenant: CurrentTenant,
    unidade: Annotated[UUID | None, Query(description="Filtra por unidade")] = None,
) -> ComplianceReportList:
    """Os laudos VIGENTES das unidades que quem pergunta enxerga.

    Sem checagem de domínio: laudo é conformidade do local, não dado de pessoa —
    o mesmo argumento de `GET /dp/postos`, e o motivo de a tabela ter dois eixos
    de RLS em vez de três. O recorte vem de `util.can_see_unit`, pela policy de
    `app.unit`.

    ⛔ Sem filtro por situação, e a ausência é o desenho: "a vencer" precisa de
    uma janela que o schema não tem para laudo. A UI classifica com o limiar
    declarado nela, a partir de `days_to_expiry`.
    """
    permissoes = await check_permissions(tenant)
    lista = await laudos.list_reports(tenant, unit_id=unidade)
    return ComplianceReportList(
        rows=[_laudo(report) for report in lista], can_write=permissoes.admin
    )


@router.post("/laudos", status_code=status.HTTP_201_CREATED)
async def cadastrar_laudo(
    payload: ComplianceReportCreate, tenant: CurrentTenant
) -> ComplianceReportRow:
    """Cadastra o primeiro laudo daquele tipo na unidade. Administração, e só na unidade dela."""
    await _pode_escrever_laudo(tenant)

    # O papel vem antes da unidade, como no Quadro de Postos: quem não pode
    # escrever não descobre aqui se a unidade existe.
    if not await laudos.can_see_unit(tenant, payload.unit_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unidade não encontrada.")

    try:
        criado = await laudos.create_report(
            tenant,
            unit_id=payload.unit_id,
            type=payload.type,
            valid_until=payload.valid_until,
            notes=payload.notes,
        )
    except laudos.DuplicateComplianceReportError as choque:
        # 409 e não 422: o pedido está bem formado, o estado é que não permite —
        # e o caminho certo é renovar o que já existe.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(choque)) from choque
    return _laudo(criado)


@router.post("/laudos/{report_id}/renovar", status_code=status.HTTP_201_CREATED)
async def renovar_laudo(
    report_id: UUID, payload: ComplianceReportRenewal, tenant: CurrentTenant
) -> ComplianceReportRow:
    """Renova: **linha nova** apontando para a que sai, com o histórico intacto.

    ⛔ Não existe rota que altere a data do laudo vigente, e não existe rota que
    apague laudo — regra 6. O vencimento anterior é o que valeu na fiscalização
    da unidade, e reescrevê-lo mudaria o passado sem deixar rastro.
    """
    await _pode_escrever_laudo(tenant)

    anterior = await laudos.load_report(tenant, report_id)
    # As duas recusas são o mesmo 404: um 403 aqui confirmaria que o laudo
    # existe em outra unidade.
    if anterior is None or not await laudos.can_see_unit(tenant, anterior.unit_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_LAUDO_NAO_ENCONTRADO)

    try:
        renovado = await laudos.renew_report(
            tenant, anterior=anterior, valid_until=payload.valid_until, notes=payload.notes
        )
    except laudos.AlreadyRenewedError as choque:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(choque)) from choque
    return _laudo(renovado)


# ---------------------------------------------------------------------------
# Curadoria de rubrica
# ---------------------------------------------------------------------------
def _rubrica(linha: rubricas.PayrollCode) -> PayrollCodeRow:
    return PayrollCodeRow(
        code=linha.code,
        label=linha.label,
        nature=linha.nature,
        category=linha.category,
        validated=linha.validated,
        validated_at=linha.validated_at,
        in_payroll=linha.in_payroll,
    )


async def _pode_curar_rubrica(tenant: CurrentTenant) -> None:
    """⛔ `compensation` **e** administração — e a exclusão que isso causa é declarada.

    A policy `payroll_event_map_admin` (migration 30) é `util.is_admin`, então
    uma rota que aceitasse menos que isso seria **mais frouxa que a policy** —
    o defeito que as duas revisões do S1 acharam sozinhas no catálogo de verbas.
    E o mapa decide como o dinheiro é somado, então `compensation` também entra,
    como em `POST /dp/beneficios/reajuste`.

    ⚠️ Consequência, escrita: `accounting` tem `compensation` e **não** é admin
    — é a mesma exclusão que o S3 declarou para `app.leave_justification_map` e
    que fica revisável quando a contabilidade precisar curar sozinha. `hr` é
    admin e não tem `compensation`, então também fica de fora. Sobram `owner` e
    `personnel`.
    """
    permissoes = await check_permissions(tenant)
    if not permissoes.compensation:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_SEM_COMPENSATION)
    if not permissoes.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Classificar rubrica exige papel administrativo. "
            "Seu papel consulta a folha, mas não define como ela é somada.",
        )


@router.get("/rubricas")
async def listar_rubricas(tenant: CurrentTenant) -> PayrollCodeList:
    """O plano de contas do cliente com o que a curadoria já disse de cada código.

    `pending` conta o que a **folha usa** e ninguém classificou — o número que
    diz se algum indicador financeiro sairia incompleto. Ele vem de
    `rubricas.read_curation`, a mesma função que entrega categoria a quem soma:
    a lista e a soma não podem discordar sobre o que está pendente.
    """
    await _pode_curar_rubrica(tenant)
    lista = await rubricas.list_codes(tenant)
    curadoria = await rubricas.read_curation(tenant)
    return PayrollCodeList(
        rows=[_rubrica(linha) for linha in lista],
        pending=len(curadoria.pending),
        can_write=True,
    )


@router.patch("/rubricas/{code}")
async def curar_rubrica(
    code: str, payload: PayrollCodePatch, tenant: CurrentTenant
) -> PayrollCodeRow:
    """Classifica o código e registra quem conferiu. Não existe rota que apague a linha."""
    await _pode_curar_rubrica(tenant)
    try:
        curado = await rubricas.set_category(
            tenant, code=code, category=payload.category, validated=payload.validated
        )
    except rubricas.UnknownPayrollCodeError as ausente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ausente)) from ausente
    return _rubrica(curado)
