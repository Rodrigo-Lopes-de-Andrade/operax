"""HR — template, preview and confirmation. Caminho 2, always.

Nothing here is aggregate and nothing here is anonymous: the file carries names,
registration numbers and, depending on the type, salaries. So it never goes
through the anon path, and every route asks the database — as the caller — who
the caller is before answering.

THE FOUR STEPS OF THE IMPORT SCREEN, AND WHERE THEY LAND
  tipo     → `GET /rh/template/{type}` builds the file already filled in.
  arquivo  → `POST /rh/imports` stores it, judges it and writes **nothing**.
  preview  → the same response, line by line.
  confirmar→ `POST /rh/imports/{id}/confirm` re-reads the stored file, judges it
             again, and applies only what it still approves.

Refusing the file is not the same as refusing a line. A file without `_meta`, from
another tenant, or with a header that was edited, is refused whole and before the
first line — because a wrong file has no right line. That answer is 422 with the
sentence the user needs: baixe o modelo atual.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status

from operax.core.storage import FileStore, StorageError, get_file_store, import_path
from operax.core.tenant import TenantContext
from operax.rh import repository
from operax.rh.importer import ImportContext, LineOutcome, retroactive_limit, validate
from operax.rh.templates import SEM_TEMPLATE, Template, get_template
from operax.rh.workbook import CONTENT_TYPE, WorkbookError, build, parse
from server.deps import CurrentTenant
from server.models import (
    ImportCounts,
    ImportLineError,
    ImportLineReport,
    ImportPreview,
    ImportResult,
)

router = APIRouter(prefix="/rh", tags=["rh"])

# Uma planilha de cadastro de um cliente inteiro não passa de algumas centenas de
# KB. O limite existe para que um arquivo trocado por engano falhe rápido, em vez
# de ocupar memória do processo inteiro enquanto é lido.
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024

#: Os estados a partir dos quais confirmar faz sentido. `processed` já foi
#: aplicado e `validation_error` não tem o que aplicar.
_CONFIRMAVEIS = frozenset({"received", "validating"})


def get_store() -> FileStore:
    return get_file_store()


StoreDep = Annotated[FileStore, Depends(get_store)]


async def _resolve(tipo: str, tenant: TenantContext) -> Template:
    """O template pedido, se ele existe e se quem pede alcança o domínio dele."""
    template = get_template(tipo)
    if template is None:
        motivo = SEM_TEMPLATE.get(tipo)
        if motivo:
            # 501 e não 404: o tipo existe no banco desde a migration 16, o que
            # não existe ainda é o caminho de volta. "Ainda não" e "nunca" são
            # respostas diferentes para quem está esperando o arquivo.
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"Ainda não há modelo para {tipo!r}: {motivo}.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tipo de importação desconhecido: {tipo!r}.",
        )

    permissoes = await repository.check_permissions(tenant)
    if not permissoes.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu papel não altera cadastro de colaborador.",
        )
    if not permissoes.has_domain(template.domain):
        # O template vem preenchido com o dado do domínio: quem não vê o domínio
        # não baixa o arquivo, senão o arquivo seria a porta dos fundos da tela.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Você não tem acesso ao domínio de {template.domain}.",
        )
    return template


async def _context(tenant: TenantContext, template: Template) -> ImportContext:
    linhas = await repository.fetch_current(tenant, template)
    hoje = date.today()
    return ImportContext(
        by_registration=repository.index_by(linhas, "registration_number"),
        by_hr_code=repository.index_by(linhas, "hr_code"),
        current=repository.to_current_map(linhas),
        today=hoje,
        retroactive_limit_days=retroactive_limit(
            hoje, await repository.last_closed_period_end(tenant)
        ),
    )


def _counts(outcomes: list[LineOutcome]) -> ImportCounts:
    return ImportCounts(
        total=len(outcomes),
        ok=sum(1 for o in outcomes if o.status == "ok"),
        unchanged=sum(1 for o in outcomes if o.status == "unchanged"),
        error=sum(1 for o in outcomes if o.status == "error"),
    )


def _lines(outcomes: list[LineOutcome]) -> list[ImportLineReport]:
    return [
        ImportLineReport(
            line=o.line,
            status=o.status,
            errors=[
                ImportLineError(code=e.code, message=e.message, column=e.column) for e in o.errors
            ],
        )
        for o in outcomes
    ]


def _report(layout_version: str, counts: ImportCounts, lines: list[ImportLineReport]) -> dict:
    return {
        "layout_version": layout_version,
        "counts": counts.model_dump(),
        "lines": [line.model_dump() for line in lines],
    }


@router.get("/template/{tipo}")
async def baixar_template(tipo: str, tenant: CurrentTenant) -> Response:
    """O modelo do tipo pedido, já preenchido com o que está gravado."""
    template = await _resolve(tipo, tenant)
    linhas = await repository.fetch_current(tenant, template)
    conteudo = build(
        template,
        linhas,
        tenant_id=tenant.tenant_id,
        generated_at=datetime.now(UTC),
    )
    await repository.record_export(tenant, template=template, rows=len(linhas))
    return Response(
        content=conteudo,
        media_type=CONTENT_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{template.type}.xlsx"'},
    )


@router.post("/imports", status_code=status.HTTP_201_CREATED)
async def enviar_planilha(
    tenant: CurrentTenant,
    store: StoreDep,
    tipo: Annotated[str, Form(description="Tipo de importação, ex.: hr_link")],
    arquivo: Annotated[UploadFile, File(description="Planilha gerada pelo sistema")],
) -> ImportPreview:
    """Guarda o arquivo, julga cada linha e **não grava nada** no domínio."""
    template = await _resolve(tipo, tenant)

    conteudo = await arquivo.read()
    if len(conteudo) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Arquivo maior que 5 MB. Não parece uma planilha de cadastro.",
        )

    import_id = uuid4()
    caminho = import_path(tenant.tenant_id, import_id)
    try:
        await store.put(caminho, conteudo, CONTENT_TYPE)
    except StorageError as erro:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Não consegui guardar o arquivo enviado. {erro}",
        ) from erro

    await repository.create_import(
        tenant,
        import_id=import_id,
        template=template,
        storage_path=caminho,
        file_name=arquivo.filename,
    )

    try:
        lido = parse(conteudo, template=template, tenant_id=tenant.tenant_id)
    except WorkbookError as erro:
        # O arquivo recusado fica guardado: ele é a prova do que foi enviado.
        await repository.save_report(
            tenant,
            import_id=import_id,
            status="validation_error",
            rows_total=0,
            rows_ok=0,
            rows_error=0,
            report={"file_error": {"code": erro.code, "message": erro.message}},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=erro.message
        ) from erro

    contexto = await _context(tenant, template)
    resultados = validate(template, lido.rows, contexto)
    contagem = _counts(resultados)
    linhas = _lines(resultados)
    # Nenhuma linha aproveitável não é um preview: é um arquivo que não passou.
    estado = "validation_error" if contagem.error and not contagem.ok else "validating"

    await repository.save_report(
        tenant,
        import_id=import_id,
        status=estado,
        rows_total=contagem.total,
        rows_ok=contagem.ok + contagem.unchanged,
        rows_error=contagem.error,
        report=_report(lido.layout_version, contagem, linhas),
    )
    return ImportPreview(
        import_id=import_id,
        type=template.type,
        layout_version=lido.layout_version,
        status=estado,
        counts=contagem,
        lines=linhas,
    )


@router.post("/imports/{import_id}/confirm")
async def confirmar_importacao(
    import_id: UUID, tenant: CurrentTenant, store: StoreDep
) -> ImportResult:
    """Aplica as linhas que continuam válidas — relendo o arquivo, não o veredito."""
    registro = await repository.load_import(tenant, import_id)
    if registro is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Importação não encontrada."
        )
    if registro["status"] not in _CONFIRMAVEIS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Esta importação está em {registro['status']!r} e não pode ser confirmada. "
                "Envie o arquivo novamente."
            ),
        )

    template = await _resolve(registro["type"], tenant)

    try:
        conteudo = await store.get(registro["storage_path"])
    except StorageError as erro:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Não consegui reler o arquivo enviado. {erro}",
        ) from erro

    try:
        lido = parse(conteudo, template=template, tenant_id=tenant.tenant_id)
    except WorkbookError as erro:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=erro.message
        ) from erro

    contexto = await _context(tenant, template)
    resultados = validate(template, lido.rows, contexto)
    contagem = _counts(resultados)
    linhas = _lines(resultados)

    aplicadas = await repository.apply_lines(
        tenant,
        template=template,
        outcomes=resultados,
        import_id=import_id,
        status="processed",
        rows_total=contagem.total,
        rows_ok=contagem.ok + contagem.unchanged,
        rows_error=contagem.error,
        report=_report(lido.layout_version, contagem, linhas),
    )

    return ImportResult(
        import_id=import_id,
        type=template.type,
        layout_version=lido.layout_version,
        status="processed",
        counts=contagem,
        lines=linhas,
        applied=aplicadas,
        partial=contagem.error > 0,
    )
