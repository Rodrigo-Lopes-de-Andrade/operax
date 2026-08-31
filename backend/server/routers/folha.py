"""A folha do cliente entrando por planilha — modelo, preview e confirmação.

Caminho 2, sempre: o arquivo carrega matrícula, nome e valor pago pessoa a
pessoa. Domínio sensível `compensation` do começo ao fim, e nenhuma linha disto
passa perto do caminho anônimo.

OS QUATRO PASSOS DA TELA, E ONDE ELES CAEM
  competência → `GET /folha/template` devolve o modelo do mês, já preenchido com
                o que foi importado antes — corrigir é mexer na linha errada e
                reenviar, não redigitar mil linhas.
  arquivo     → `POST /folha/imports` guarda, julga e **não grava nada**.
  preview     → a mesma resposta, linha a linha, com os avisos ao lado.
  confirmar   → `POST /folha/imports/{id}/confirm` relê o arquivo guardado, julga
                de novo e substitui a competência com o que ele ainda aprova.

O QUE MUDA EM RELAÇÃO AO IMPORT DE RH, E POR QUÊ
Lá, arquivo com três linhas erradas entra com as outras e volta marcado como
parcial: cada linha é um fato independente sobre uma pessoa, e 77 fatos certos
valem 77 fatos. Aqui não. A folha é uma soma: importar 998 de 1000 linhas produz
um total que não bate com holerite nenhum e não avisa ninguém — é o mesmo motivo
pelo qual um valor ilegível vira erro na linha e nunca zero. Então **arquivo com
erro não é confirmável**, e isso já está dito no estado que ele recebe:
`validation_error` não entra na lista de confirmáveis.

O que **não** barra o arquivo é código de evento sem categoria. Ele entra, conta
no total, e volta na lista `unmapped_codes` — que é o insumo da curadoria com a
contabilidade, e o primeiro mês é justamente quando ela ainda não existe.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, NoReturn
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status

from operax.core.storage import FileStore, StorageError, get_file_store, import_path
from operax.core.tenant import TenantContext
from operax.imports import payroll, repository
from operax.imports.payroll import ParsedPayroll, Report
from operax.rh import repository as rh_repository
from server.deps import CurrentTenant
from server.models import (
    ImportLineError,
    PayrollCounts,
    PayrollLineReport,
    PayrollPreview,
    PayrollReplacement,
    PayrollResult,
)

router = APIRouter(prefix="/folha", tags=["folha"])

#: Uma folha de mil pessoas com dez eventos cada não passa de alguns MB. O limite
#: existe para que o arquivo trocado por engano falhe rápido.
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024

#: Os estados a partir dos quais confirmar faz sentido. `validation_error` fica
#: fora, e é assim que "folha não entra pela metade" vira estado e não opinião.
_CONFIRMAVEIS = frozenset({"received", "validating"})

#: A natureza volta para a planilha como a contabilidade a escreve.
_NATUREZA_PT = {ingles: pt for pt, ingles in payroll.NATURES.items()}


def get_store() -> FileStore:
    return get_file_store()


StoreDep = Annotated[FileStore, Depends(get_store)]


async def _autorizar(tenant: TenantContext) -> None:
    """Quem envia a folha, e por que a pergunta é feita ao banco.

    Duas condições, as mesmas que o import de RH faz: papel administrativo e o
    domínio sensível do dado que está entrando. `util.is_admin` e
    `util.can_see_domain` são as funções que as próprias policies chamam, e são
    perguntadas como o usuário que está pedindo — não deduzidas aqui.

    ⚠️ Premissa declarada: quem envia é RH/DP (`owner`, `hr`, `personnel`). O
    papel `accounting` existe para ler a folha, não para publicá-la; se o cliente
    disser que a contabilidade envia direto, é este `if` que muda.
    """
    permissoes = await rh_repository.check_permissions(tenant)
    if not permissoes.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu papel não importa folha de pagamento.",
        )
    if not permissoes.compensation:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem acesso ao domínio de remuneração.",
        )


def _counts(report: Report) -> PayrollCounts:
    return PayrollCounts(total=report.rows_total, ok=report.rows_ok, error=report.rows_error)


def _lines(report: Report) -> list[PayrollLineReport]:
    """Só as linhas que têm o que dizer. Mil linhas silenciosas não são relatório."""
    return [
        PayrollLineReport(
            line=o.line,
            errors=[
                ImportLineError(code=e.code, message=e.message, column=e.column) for e in o.errors
            ],
            warnings=[
                ImportLineError(code=w.code, message=w.message, column=w.column) for w in o.warnings
            ],
        )
        for o in report.outcomes
        if o.errors or o.warnings
    ]


def _replaces(estado: repository.PeriodState) -> PayrollReplacement | None:
    if not estado.entries:
        return None
    return PayrollReplacement(entries=estado.entries, imported_at=estado.imported_at)


def _report_json(
    report: Report, *, year: int, month: int, substitui: PayrollReplacement | None
) -> dict[str, Any]:
    return {
        **report.as_json(),
        "period": f"{year:04d}-{month:02d}",
        "replaces": substitui.model_dump(mode="json") if substitui else None,
    }


async def _recusar_arquivo(
    tenant: TenantContext, *, import_id: UUID, code: str, message: str, http_status: int
) -> NoReturn:
    """Guarda o motivo no registro do import e devolve a recusa ao usuário.

    O arquivo recusado continua guardado: ele é a prova do que foi enviado.
    """
    await rh_repository.save_report(
        tenant,
        import_id=import_id,
        status="validation_error",
        rows_total=0,
        rows_ok=0,
        rows_error=0,
        report={"file_error": {"code": code, "message": message}},
    )
    raise HTTPException(status_code=http_status, detail=message)


async def _julgar(
    tenant: TenantContext, lido: ParsedPayroll
) -> tuple[Report, dict[str, repository.EmployeeRef]]:
    """O veredito do arquivo, com o alcance de quem pediu e o mapa de eventos.

    Devolve as pessoas junto porque a gravação precisa delas — empresa e unidade
    da linha saem daqui, e reler a tabela inteira para reencontrá-las abriria a
    janela em que o veredito e a gravação enxergam quadros diferentes.
    """
    pessoas = await repository.fetch_employees(tenant)
    codigos = await repository.fetch_mapped_codes(tenant)
    veredito = payroll.verdict(
        lido.rows,
        employees={matricula: ref.employee_id for matricula, ref in pessoas.items()},
        mapped_codes=codigos,
    )
    return veredito, pessoas


# ---------------------------------------------------------------------------
# O modelo da competência
# ---------------------------------------------------------------------------
@router.get("/template")
async def baixar_modelo(
    tenant: CurrentTenant,
    ano: Annotated[int, Query(ge=2000, le=2100, description="Ano da competência")],
    mes: Annotated[int, Query(ge=1, le=12, description="Mês da competência")],
) -> Response:
    """O modelo da competência, já com o que foi importado nela.

    ⚠️ O décimo terceiro (`month = 13` em `app.payroll_period`) ainda não é
    expressável: a aba de controle carrega `AAAA-MM` e o parser aceita 1..12.
    Aceitar 13 aqui geraria um arquivo que o próprio parser recusa depois — a
    recusa aqui é a versão honesta da mesma falta.
    """
    await _autorizar(tenant)

    linhas = await repository.fetch_entries(tenant, year=ano, month=mes)
    conteudo = payroll.build_template(
        tenant_id=tenant.tenant_id,
        year=ano,
        month=mes,
        generated_at=datetime.now(UTC),
        rows=tuple(_para_planilha(linha) for linha in linhas),
    )
    await repository.record_template_export(tenant, year=ano, month=mes, rows=len(linhas))
    return Response(
        content=conteudo,
        media_type=payroll.CONTENT_TYPE,
        headers={"Content-Disposition": f'attachment; filename="folha-{ano:04d}-{mes:02d}.xlsx"'},
    )


def _para_planilha(linha: dict[str, Any]) -> dict[str, Any]:
    """A linha gravada de volta no vocabulário do arquivo."""
    return {**linha, "nature": _NATUREZA_PT.get(linha["nature"], linha["nature"])}


# ---------------------------------------------------------------------------
# O arquivo
# ---------------------------------------------------------------------------
@router.post("/imports", status_code=status.HTTP_201_CREATED)
async def enviar_folha(
    tenant: CurrentTenant,
    store: StoreDep,
    arquivo: Annotated[UploadFile, File(description="Planilha de folha gerada pelo sistema")],
) -> PayrollPreview:
    """Guarda o arquivo, julga cada linha e **não grava nada** na competência.

    A competência não vem no formulário: ela vem da aba de controle do arquivo.
    Perguntar duas vezes abriria a possibilidade de as duas respostas divergirem,
    e a que vale é a que está dentro do arquivo que será relido no confirm.
    """
    await _autorizar(tenant)

    conteudo = await arquivo.read()
    if len(conteudo) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Arquivo maior que 5 MB. Não parece uma planilha de folha.",
        )

    import_id = uuid4()
    caminho = import_path(tenant.tenant_id, import_id, "folha")
    try:
        await store.put(caminho, conteudo, payroll.CONTENT_TYPE)
    except StorageError as erro:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Não consegui guardar o arquivo enviado. {erro}",
        ) from erro

    await rh_repository.create_import(
        tenant,
        import_id=import_id,
        type=payroll.IMPORT_TYPE,
        layout_version=payroll.LAYOUT_VERSION,
        storage_path=caminho,
        file_name=arquivo.filename,
    )

    try:
        lido = payroll.parse_upload(conteudo, tenant_id=tenant.tenant_id)
    except payroll.WorkbookError as erro:
        await _recusar_arquivo(
            tenant,
            import_id=import_id,
            code=erro.code,
            message=erro.message,
            http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    periodo = await repository.fetch_period(tenant, year=lido.year, month=lido.month)
    if periodo.closed:
        await _recusar_arquivo(
            tenant,
            import_id=import_id,
            code="competencia_fechada",
            message=(
                f"A competência {lido.year:04d}-{lido.month:02d} está fechada e não recebe "
                "importação. Reabra a competência antes de reenviar."
            ),
            http_status=status.HTTP_409_CONFLICT,
        )

    veredito, _ = await _julgar(tenant, lido)
    substitui = _replaces(periodo)
    # Uma linha em erro basta: a folha não entra pela metade, e o estado é o que
    # impede o confirm mais adiante.
    estado = "validation_error" if veredito.rows_error else "validating"

    await rh_repository.save_report(
        tenant,
        import_id=import_id,
        status=estado,
        rows_total=veredito.rows_total,
        rows_ok=veredito.rows_ok,
        rows_error=veredito.rows_error,
        report=_report_json(veredito, year=lido.year, month=lido.month, substitui=substitui),
    )

    return PayrollPreview(
        import_id=import_id,
        period=f"{lido.year:04d}-{lido.month:02d}",
        layout_version=lido.layout_version,
        status=estado,
        counts=_counts(veredito),
        unmapped_codes=list(veredito.unmapped_codes),
        lines=_lines(veredito),
        replaces=substitui,
    )


@router.post("/imports/{import_id}/confirm")
async def confirmar_folha(import_id: UUID, tenant: CurrentTenant, store: StoreDep) -> PayrollResult:
    """Substitui a competência pelo arquivo — relendo o arquivo, não o veredito."""
    await _autorizar(tenant)

    registro = await rh_repository.load_import(tenant, import_id)
    if registro is None or registro["type"] != payroll.IMPORT_TYPE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Importação de folha não encontrada.",
        )
    if registro["status"] not in _CONFIRMAVEIS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Esta importação está em {registro['status']!r} e não pode ser confirmada. "
                "Envie o arquivo novamente."
            ),
        )

    try:
        conteudo = await store.get(registro["storage_path"])
    except StorageError as erro:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Não consegui reler o arquivo enviado. {erro}",
        ) from erro

    try:
        lido = payroll.parse_upload(conteudo, tenant_id=tenant.tenant_id)
    except payroll.WorkbookError as erro:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=erro.message
        ) from erro

    veredito, pessoas = await _julgar(tenant, lido)
    periodo = await repository.fetch_period(tenant, year=lido.year, month=lido.month)
    substitui = _replaces(periodo)
    relatorio = _report_json(veredito, year=lido.year, month=lido.month, substitui=substitui)

    if veredito.rows_error:
        # O julgamento entre o preview e a confirmação pode ter mudado — alguém
        # desligou um colaborador, o arquivo era outro. O registro recebe o
        # veredito novo, e ele deixa de ser confirmável.
        await rh_repository.save_report(
            tenant,
            import_id=import_id,
            status="validation_error",
            rows_total=veredito.rows_total,
            rows_ok=veredito.rows_ok,
            rows_error=veredito.rows_error,
            report=relatorio,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{veredito.rows_error} linha(s) em erro: a folha não é importada pela metade, "
                "porque a soma da competência deixaria de bater. Corrija o arquivo e reenvie."
            ),
        )

    try:
        aplicado = await repository.apply_payroll(
            tenant,
            import_id=import_id,
            year=lido.year,
            month=lido.month,
            outcomes=veredito.outcomes,
            employees={ref.employee_id: ref for ref in pessoas.values()},
            rows_total=veredito.rows_total,
            rows_ok=veredito.rows_ok,
            rows_error=veredito.rows_error,
            report=relatorio,
        )
    except repository.ClosedPeriodError as erro:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(erro)) from erro

    return PayrollResult(
        import_id=import_id,
        period=f"{lido.year:04d}-{lido.month:02d}",
        layout_version=lido.layout_version,
        status="processed",
        counts=_counts(veredito),
        unmapped_codes=list(veredito.unmapped_codes),
        lines=_lines(veredito),
        replaces=substitui,
        applied=aplicado.applied,
        replaced=aplicado.replaced,
    )
