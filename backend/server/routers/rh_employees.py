"""A aba Colaboradores — leitura por domínio e as três escritas do formulário.

`rh.py` cuida do arquivo (modelo, preview, confirmação); este módulo cuida da
pessoa. Os dois vivem sob `/rh` e chamam o mesmo funil de validação, porque um
formulário que edita uma pessoa e uma planilha que edita oitenta são a mesma
edição chegando por portas diferentes.

O QUE NÃO CHEGA À TELA
Bloco de domínio que o papel não alcança volta `null`, não vazio. A tela usa isso
para **não renderizar a aba** — não para desabilitá-la. Cadeado é informação:
quem não pode ver salário não deveria descobrir que existe salário.

O QUE A TELA NÃO DECIDE
`can_write` vem de `util.is_admin`, perguntado ao banco como o usuário que
perguntou. Esconder o botão de editar é cortesia, não segurança: as três rotas de
escrita recusam por conta própria, e recusam de novo por domínio quando o campo é
sensível.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status

from operax.core.tenant import TenantContext
from operax.rh import employees as repo
from operax.rh import foto as foto_repo
from operax.rh.importer import retroactive_limit
from operax.rh.ownership import ENUMS, Domain, field
from operax.rh.repository import check_permissions, last_closed_period_end
from operax.rh.validators import (
    LineError,
    check_enums,
    check_new_band,
    check_unique,
    validate_compensation,
)
from server.deps import CurrentTenant
from server.models import (
    CompensationBand,
    EmployeeDocument,
    EmployeePatch,
    HrAgreement,
    HrDueDate,
    HrEmployeeDetail,
    HrEmployeeList,
    HrEmployeeRow,
    HrIdentity,
    HrLeave,
    HrMovement,
    HrPhoto,
    HrPhotoSuperseded,
    HrPii,
    HrSyncField,
    NewCompensation,
    NewPosition,
    OccupationalExamRow,
    PositionBand,
)

router = APIRouter(prefix="/rh", tags=["rh"])

_STATUS = ("active", "afastado", "vacation", "desligado")
_PENDENCIA = ("aso", "documento", "experiencia", "vinculo")

# O bloco de proveniência: a coluna que a matriz governa, e onde está o valor
# legível dela no detalhe. `unit_id` é `uuid` na tabela e "Shopping Norte" na
# tela — citar a coluna e mostrar o uuid não informaria ninguém.
_SYNC_BLOCK: tuple[tuple[str, str], ...] = (
    ("registration_number", "registration_number"),
    ("name", "name"),
    ("hired_on", "hired_on"),
    ("status", "status"),
    ("unit_id", "unit_name"),
    ("company_id", "company_name"),
    ("department_id", "department_name"),
    ("manager_employee_id", "manager_name"),
    ("terminated_on", "terminated_on"),
)


def _refuse(erros: list[LineError]) -> None:
    """Uma frase por erro, juntas, no `detail` padrão do FastAPI.

    O contrato do front diz que erro fora do stream vem como `{"detail": …}`, e a
    mensagem já nomeia a coluna e o valor — que é o que a pessoa que está
    corrigindo precisa ler.
    """
    if erros:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=" · ".join(erro.message for erro in erros),
        )


async def _require_write(tenant: TenantContext, domain: Domain | None = None):
    permissoes = await check_permissions(tenant)
    if not permissoes.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu papel não altera cadastro de colaborador.",
        )
    if not permissoes.has_domain(domain):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Você não tem acesso ao domínio de {domain}.",
        )
    return permissoes


@router.get("/employees")
async def listar_colaboradores(
    tenant: CurrentTenant,
    unidade: Annotated[UUID | None, Query(description="Filtra por unidade")] = None,
    status_vinculo: Annotated[str | None, Query(alias="status")] = None,
    busca: Annotated[str | None, Query(description="Nome, matrícula ou ID RH")] = None,
    pendencia: Annotated[
        str | None, Query(description="aso · documento · experiencia · vinculo")
    ] = None,
    janela: Annotated[
        int, Query(ge=1, le=365, description="Dias à frente")
    ] = repo.DEFAULT_WINDOW_DAYS,
) -> HrEmployeeList:
    """A lista da aba, ordenada pelo que vence primeiro."""
    if status_vinculo is not None and status_vinculo not in _STATUS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Status inválido. Aceitos: {', '.join(_STATUS)}.",
        )
    if pendencia is not None and pendencia not in _PENDENCIA:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Pendência inválida. Aceitas: {', '.join(_PENDENCIA)}.",
        )

    permissoes = await check_permissions(tenant)
    linhas, truncou = await repo.list_employees(
        tenant,
        unidade=unidade,
        status=status_vinculo,
        busca=busca,
        pendencia=pendencia,
        janela_dias=janela,
        hoje=date.today(),
    )
    return HrEmployeeList(
        rows=[_row(linha) for linha in linhas],
        truncated=truncou,
        can_write=permissoes.admin,
    )


def _row(linha: dict[str, Any]) -> HrEmployeeRow:
    due = (
        HrDueDate(kind=linha["due_kind"], label=linha["due_label"], due_on=linha["due_on"])
        if linha.get("due_on")
        else None
    )
    return HrEmployeeRow(
        employee_id=linha["employee_id"],
        name=linha["name"],
        registration_number=linha["registration_number"],
        hr_code=linha["hr_code"],
        cargo=linha["cargo"],
        status=linha["status"],
        hired_on=linha["hired_on"],
        unit_id=linha["unit_id"],
        unit_name=linha["unit_name"],
        due=due,
    )


def _photo_payload(info: foto_repo.PhotoInfo | None) -> HrPhoto | None:
    """Metadado da foto para o JSON. ⛔ Nunca bytes — só estado e datas."""
    if info is None:
        return None
    return HrPhoto(
        state=info.state.value,
        origin=info.origin.value if info.origin else None,
        synced_at=info.synced_at,
        uploaded_at=info.uploaded_at,
        uploaded_by_name=info.uploaded_by_name,
        superseded=(
            HrPhotoSuperseded(
                uploaded_at=info.superseded.uploaded_at,
                uploaded_by_name=info.superseded.uploaded_by_name,
            )
            if info.superseded
            else None
        ),
        can_upload=info.can_upload,
    )


@router.post("/employees/{employee_id}/foto")
async def enviar_foto(
    employee_id: UUID,
    tenant: CurrentTenant,
    arquivo: Annotated[UploadFile, File(alias="file")],
) -> HrPhoto:
    """O DP envia a foto de quem a origem declara não ter — §4-ter da decisão.

    ⚠️ **Isto CRIA dado biométrico**, e não espelha o que a origem já tinha. É
    postura de LGPD diferente da exibição, e o risco está aceito por escrito na
    §4-bis, com dono e data. Ver `docs/DECISAO-FOTO-DO-COLABORADOR.md`.

    ⛔ **Só onde `"PossuiFoto" = false`.** Recusar aqui é o que faz as duas fontes
    não se sobreporem por construção — sem isso, precedência deixaria de ser
    regra de exibição e viraria disputa de escrita.

    O mime sai do *magic number*, nunca do `Content-Type` que o cliente manda:
    aceitar a palavra de quem envia sobre o que os bytes são é confiar na
    extensão do arquivo.
    """
    permissoes = await check_permissions(tenant)
    if not permissoes.pii:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu papel não alcança o domínio de dados pessoais.",
        )
    if not permissoes.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu papel não altera cadastro de colaborador.",
        )

    conteudo = await arquivo.read()
    try:
        info = await foto_repo.upload_photo(
            tenant, employee_id, conteudo, uploaded_by=tenant.user_id
        )
    except foto_repo.UploadRecusadoError as recusa:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(recusa)
        ) from recusa

    if info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Colaborador não encontrado."
        )
    payload = _photo_payload(info)
    assert payload is not None
    return payload


#: O que a origem entrega. Fora disto, o mime da coluna não é obedecido.
_MIMES_ACEITOS = frozenset({"image/jpeg", "image/png"})


@router.get(
    "/employees/{employee_id}/foto",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}, "description": "A imagem."}},
)
async def obter_foto(employee_id: UUID, tenant: CurrentTenant) -> Response:
    """A foto de uma pessoa — Caminho 2, domínio `pii`, uma pessoa por vez.

    Decidida em 04/09/2026 pelo dono, a pedido do cliente:
    `docs/DECISAO-FOTO-DO-COLABORADOR.md`. O sistema que o cliente usa hoje já
    exibe a foto na ficha para o mesmo DP — isto reproduz uma exposição que já
    existe, não cria uma nova.

    ⛔ **Uma pessoa por requisição, e nunca em lista.** Não existe rota que
    devolva várias fotos, e o metadado da ficha não carrega bytes: 176 rostos
    numa listagem é exportação de biometria com outro nome (§5 da decisão).

    ⛔ **Sem URL pública, sem link assinado.** A resposta vive na sessão que a
    pediu — `private, no-store` — e não há bucket, não há URL que sobreviva ao
    logout.

    404 cobre três casos de propósito: pessoa inexistente, pessoa fora do
    alcance de quem pergunta, e pessoa sem foto. Distinguir os dois primeiros
    confirmaria que alguém existe noutra unidade.
    """
    permissoes = await check_permissions(tenant)
    if not permissoes.pii:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu papel não alcança o domínio de dados pessoais.",
        )

    imagem = await foto_repo.load_photo(tenant, employee_id)
    if imagem is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sem foto.")

    return Response(
        content=imagem.content,
        # ⛔ Allowlist, e não o valor da coluna. `foto_mime` é escrita FORA DE
        # BANDA pelo `sync-fotos` da Vercel, não tem `CHECK` e não tem lista
        # fechada — e com `Content-Disposition: inline` um mime inesperado faria
        # o navegador renderizar o conteúdo na origem da API. As duas formas são
        # as que a origem entrega (medido em 04/09/2026); o resto vira `jpeg`.
        media_type=imagem.mime if imagem.mime in _MIMES_ACEITOS else "image/jpeg",
        headers={
            # Nada de cache compartilhado: a foto é de uma pessoa e a resposta é
            # de uma sessão. `no-store` também mantém a imagem fora do disco do
            # navegador depois que a aba fecha.
            "Cache-Control": "private, no-store",
            "Content-Disposition": "inline",
            # ⛔ Desde que existe imputação, os bytes servidos aqui podem vir de
            # QUEM ENVIA — e não só do espelho. O `inline` na origem da API com
            # sniffing ligado deixaria o navegador decidir o tipo por conta; o
            # magic number cobre os 3 primeiros bytes, não um polyglot.
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/employees/{employee_id}")
async def obter_colaborador(employee_id: UUID, tenant: CurrentTenant) -> HrEmployeeDetail:
    """Uma pessoa, com as abas que o domínio de quem pergunta alcança."""
    permissoes = await check_permissions(tenant)
    detalhe = await repo.load_employee(
        tenant,
        employee_id,
        pii=permissoes.pii,
        compensation=permissoes.compensation,
        health=permissoes.health,
    )
    if detalhe is None:
        # Fora do escopo e inexistente respondem igual, como na consulta
        # individual: um 403 aqui confirmaria que a pessoa existe noutra unidade.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Colaborador não encontrado."
        )

    pessoa = detalhe["employee"]
    editaveis = [
        campo.column
        for campo in repo.EDITABLE_FIELDS
        if permissoes.has_domain(campo.domain.value if campo.domain else None)
    ]

    # A foto acompanha o domínio `pii`, como os demais blocos sensíveis: quem não
    # alcança o domínio recebe `null` e a aba não existe no DOM. Só o METADADO
    # viaja aqui — a imagem sai pela rota binária abaixo.
    info = await foto_repo.photo_info(tenant, employee_id) if permissoes.pii else None
    foto = _photo_payload(info)

    return HrEmployeeDetail(
        employee=HrIdentity(**pessoa),
        sync_fields=[_sync_field(pessoa, coluna, chave) for coluna, chave in _SYNC_BLOCK],
        editable_fields=editaveis if permissoes.admin else [],
        enums={
            coluna: sorted(valores) for (_, coluna), valores in ENUMS.items() if coluna in editaveis
        },
        can_write=permissoes.admin,
        positions=[PositionBand(**linha) for linha in detalhe["positions"]],
        leaves=[HrLeave(**linha) for linha in detalhe["leaves"]],
        movements=[HrMovement(**linha) for linha in detalhe["movements"]],
        pii=HrPii(**detalhe["pii"]) if detalhe["pii"] is not None else None,
        photo=foto,
        documents=(
            [EmployeeDocument(**linha) for linha in detalhe["documents"]]
            if detalhe["documents"] is not None
            else None
        ),
        exams=(
            [OccupationalExamRow(**linha) for linha in detalhe["exams"]]
            if detalhe["exams"] is not None
            else None
        ),
        compensation=(
            [CompensationBand(**linha) for linha in detalhe["compensation"]]
            if detalhe["compensation"] is not None
            else None
        ),
        agreements=(
            [HrAgreement(**linha) for linha in detalhe["agreements"]]
            if detalhe["agreements"] is not None
            else None
        ),
    )


def _sync_field(pessoa: dict[str, Any], coluna: str, chave: str) -> HrSyncField:
    matriz = field("employee", coluna)
    valor = pessoa.get(chave)
    return HrSyncField(
        column=coluna,
        value=None if valor is None else str(valor),
        mirror=matriz.mirror if matriz else None,
        pending=bool(matriz and matriz.pending),
    )


@router.patch("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def editar_cadastro(
    employee_id: UUID, payload: EmployeePatch, tenant: CurrentTenant
) -> Response:
    """Grava os campos de dono RH — os mesmos que o template `hr_employee` leva."""
    enviados = {
        coluna: getattr(payload, coluna)
        for coluna in payload.model_fields_set
        if coluna in {campo.column for campo in repo.EDITABLE_FIELDS}
    }
    if not enviados:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nenhum campo editável foi enviado.",
        )

    # Um campo sensível exige o domínio dele, não só o papel: quem não vê PII não
    # escreve CTPS.
    dominios = {
        campo.domain
        for campo in repo.EDITABLE_FIELDS
        if campo.column in enviados and campo.domain is not None
    }
    for dominio in dominios:
        await _require_write(tenant, dominio)
    if not dominios:
        await _require_write(tenant)

    atual, tomados = await repo.load_for_edit(tenant, employee_id)
    if atual is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Colaborador não encontrado."
        )

    erros: list[LineError] = []
    for tabela in ("employee", "employee_pii"):
        erros.extend(check_enums(enviados, table=tabela))
    if "hr_code" in enviados:
        erros.extend(
            check_unique(
                enviados["hr_code"],
                column="hr_code",
                label="ID RH",
                seen={},
                taken=tomados,
                employee_id=employee_id,
            )
        )
    _refuse(erros)

    mudou = {
        coluna: valor
        for coluna, valor in enviados.items()
        if _texto(valor) != _texto(atual.get(coluna))
    }
    if mudou:
        await repo.update_employee(tenant, employee_id, mudou, atual)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/employees/{employee_id}/compensation", status_code=status.HTTP_201_CREATED)
async def nova_vigencia_de_salario(
    employee_id: UUID, payload: NewCompensation, tenant: CurrentTenant
) -> Response:
    """Fecha a faixa aberta e abre a próxima. Corrigir a vigente é revogá-la."""
    await _require_write(tenant, Domain.COMPENSATION)

    atual, _ = await repo.load_for_edit(tenant, employee_id)
    if atual is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Colaborador não encontrado."
        )

    hoje = date.today()
    vigente = await repo.open_band(tenant, employee_id, position=False)
    _refuse(
        validate_compensation(
            {"effective_from": payload.effective_from},
            hoje=hoje,
            limite_dias=retroactive_limit(hoje, await last_closed_period_end(tenant)),
            current_from=vigente,
        )
    )

    await repo.create_compensation(
        tenant,
        employee_id,
        effective_from=payload.effective_from,
        salary=payload.salary,
        reason=payload.reason,
        anterior={"effective_from": vigente},
    )
    return Response(status_code=status.HTTP_201_CREATED)


@router.post("/employees/{employee_id}/position", status_code=status.HTTP_201_CREATED)
async def nova_vigencia_de_cargo(
    employee_id: UUID, payload: NewPosition, tenant: CurrentTenant
) -> Response:
    """Nova vigência de posição, com o cargo corrente andando junto."""
    await _require_write(tenant)

    atual, _ = await repo.load_for_edit(tenant, employee_id)
    if atual is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Colaborador não encontrado."
        )

    hoje = date.today()
    vigente = await repo.open_band(tenant, employee_id, position=True)
    # Posição não é competência de folha: o que a protege é não sobrepor a faixa
    # aberta, e o teto de retroatividade da folha não se aplica a cargo.
    erros = check_new_band(payload.effective_from, current_from=vigente)
    if payload.effective_from > hoje:
        erros.append(
            LineError(
                "vigencia_futura",
                f"effective_from está no futuro: {payload.effective_from}",
                "effective_from",
            )
        )
    _refuse(erros)

    await repo.create_position(
        tenant,
        employee_id,
        effective_from=payload.effective_from,
        cargo=payload.cargo,
        unit_id=payload.unit_id,
        anterior={"effective_from": vigente, "cargo": atual.get("cargo")},
    )
    return Response(status_code=status.HTTP_201_CREATED)


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()
