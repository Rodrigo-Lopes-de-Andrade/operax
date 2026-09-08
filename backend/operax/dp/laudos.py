"""Laudos por unidade — PCMSO, PGR, LTCAT+LTIP, com renovação e sem edição.

⛔ RENOVAR É INSERIR, NUNCA `UPDATE` NA LINHA VIGENTE
Regra 6 do projeto: nada se apaga e o passado não se reescreve. O laudo anterior
guarda o vencimento que valeu, porque foi com ele que a unidade foi fiscalizada.
A migration não concede `delete` a ninguém, e não existe rota que altere a linha
vigente — o que existe é `renew`, que grava uma linha nova apontando
`replaces_id` para a que sai. É o mesmo desenho de "reajuste é vigência nova" do
S1.

⛔ VIGÊNCIA ÚNICA É DO BANCO, E ESTE MÓDULO SÓ TRADUZ A RECUSA
Três constraints garantem "uma vigente por (unidade, tipo)": uma raiz por trio,
um sucessor por laudo, e a renovação presa ao próprio trio. Reimplementar a
verificação aqui — ler antes e decidir em Python — seria trocar uma garantia à
prova de corrida por uma que não é: duas renovações simultâneas leriam o mesmo
estado e as duas passariam. Medido em 07/09/2026, com duas sessões concorrentes:
a forma declarativa deixa 1 vigente; um gatilho sem advisory lock deixa 2.
Aqui, `UniqueViolation` vira frase para o gestor, e é só isso.

⛔ LEITURA NÃO RODA COMO O USUÁRIO — E DESTA VEZ NÃO É POR FALTA DE GRANT
`app.unit_compliance_report` **concede `select` a `authenticated`**, ao contrário
das outras tabelas da etapa: `public.vw_unit_compliance` é `security_invoker` e
sem o grant devolveria `permission denied`. Mesmo assim a leitura desta rota vai
por `tenant_scope`, como todo o Caminho 2: quem responde "esta unidade é sua?" é
`app.unit`, pela policy `unit_read`, antes de a lista ser montada. A regra de
escopo continua morando na policy; aqui ela é consultada.

A LISTA SAI DA VIEW, E ISSO É DE PROPÓSITO
`public.vw_unit_compliance` já define o que é "vigente", `days_to_expiry` e o
contador de histórico. A tela de Unidades lê a view pelo Caminho 1 e esta rota lê
a mesma view — reescrever o `not exists` aqui deixaria as duas leituras
divergindo na primeira mudança, e a metade que divergisse seria a que ninguém
confere.

⛔ SITUAÇÃO NÃO É CAMPO, E A JANELA NÃO É DAQUI
`EM DIA` / `A VENCER` / `VENCIDO` se derivam de `days_to_expiry`. O limiar de "a
vencer" não existe no schema para laudo — a única janela configurável é
`app.document_type.expiry_alert_days`, que o tipo de laudo (texto livre) não
alcança. Inventar 30 dias aqui seria a constante com cara de configuração que o
S4 recusou.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from psycopg import errors

from operax.core.tenant import TenantContext, tenant_scope

# A pergunta autorizadora tem UMA implementação. `postos.can_see_unit` já chama
# `util.can_see_unit` — a mesma função da policy — e `visible_units` já pergunta
# à `app.unit` quais unidades a policy libera. Reescrevê-las aqui seria a mesma
# pergunta em dois lugares, divergindo na primeira mudança de `app.user_scope`.
from operax.dp.postos import can_see_unit, visible_units
from operax.rh.repository import audit

#: O que a trilha de auditoria grava como origem da escrita vinda da tela.
_ORIGEM = {"form": "dp_laudos"}

__all__ = [
    "AlreadyRenewedError",
    "ComplianceReport",
    "ComplianceReportError",
    "DuplicateComplianceReportError",
    "can_see_unit",
    "create_report",
    "list_reports",
    "load_report",
    "renew_report",
    "visible_units",
]


class ComplianceReportError(RuntimeError):
    """Base das recusas deste módulo."""


class DuplicateComplianceReportError(ComplianceReportError):
    """Já existe laudo deste tipo nesta unidade — e ele é que se renova.

    A trava é o índice `single_root_idx`. Sem ela, duas cadeias paralelas do
    mesmo tipo na mesma unidade dariam duas datas de vencimento igualmente
    "vigentes", e a tela mostraria a que fosse ordenada primeiro.
    """


class AlreadyRenewedError(ComplianceReportError):
    """Este laudo já foi renovado — quem se renova é a ponta da cadeia.

    A trava é o índice `single_successor_idx`, e ela é a metade que a SPEC não
    tinha: duas renovações do mesmo laudo são duas linhas que ninguém
    substituiu, isto é, duas vigentes.
    """


@dataclass(frozen=True, slots=True)
class ComplianceReport:
    """Um laudo vigente, como a view o entrega.

    `days_to_expiry` viaja negativo quando venceu — é o insumo da situação, não
    a situação. `renewal_count` é o contador de histórico da tela do legado.
    """

    id: UUID
    unit_id: UUID
    unit_name: str
    type: str
    valid_until: date
    days_to_expiry: int
    renewal_count: int
    notes: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
# `unit_id = any(...)` recebe os ids que a policy liberou. Lista vazia devolve
# zero linhas sem caso especial, que é a resposta certa para quem não enxerga
# unidade nenhuma.
_LIST_SQL = """
    select v.report_id, v.unit_id, v.unit_name, v.type, v.valid_until,
           v.days_to_expiry, v.renewal_count, v.notes, v.created_at
    from public.vw_unit_compliance v
    where v.tenant_id = %(tenant_id)s
      and v.unit_id = any(%(units)s::uuid[])
      and (%(unit_id)s::uuid is null or v.unit_id = %(unit_id)s::uuid)
    order by v.unit_name, v.type
"""

_READ_ONE_SQL = """
    select v.report_id, v.unit_id, v.unit_name, v.type, v.valid_until,
           v.days_to_expiry, v.renewal_count, v.notes, v.created_at
    from public.vw_unit_compliance v
    where v.tenant_id = %(tenant_id)s and v.report_id = %(report_id)s
"""

# A leitura de autorização vai à TABELA, não à view: renovar um laudo que já foi
# substituído tem de chegar ao banco e ser recusado lá, com a frase certa. Se
# esta leitura filtrasse por vigente, a recusa viraria "não encontrado" e o
# gestor procuraria um laudo que existe.
_LOAD_SQL = """
    select r.id, r.unit_id, u.name as unit_name, r.type, r.valid_until, r.notes, r.created_at
    from app.unit_compliance_report r
    join app.unit u on u.id = r.unit_id
    where r.id = %(report_id)s and r.tenant_id = %(tenant_id)s
"""

# ⛔ A CANONICALIZAÇÃO DO TIPO É DO BANCO, E POR ISSO ELA ESTÁ NO `insert`
# `upper(btrim(...))` é a mesma expressão do `check` da migration. Fazê-la em
# Python seria a mesma regra em duas linguagens, e `str.upper()` e `upper()` não
# concordam em toda entrada — a divergência apareceria como um 500 no dia em que
# concordassem menos.
_INSERT_SQL = """
    insert into app.unit_compliance_report
        (tenant_id, unit_id, type, valid_until, notes, replaces_id, created_by)
    values (%(tenant_id)s, %(unit_id)s, upper(btrim(%(type)s)), %(valid_until)s,
            %(notes)s, %(replaces_id)s, %(created_by)s)
    returning id
"""


def _row_to_report(row: dict[str, Any]) -> ComplianceReport:
    return ComplianceReport(
        id=row["report_id"],
        unit_id=row["unit_id"],
        unit_name=row["unit_name"],
        type=row["type"],
        valid_until=row["valid_until"],
        days_to_expiry=row["days_to_expiry"],
        renewal_count=row["renewal_count"],
        notes=row["notes"],
        created_at=row["created_at"],
    )


def _trail(unit_id: UUID, type: str, valid_until: date, notes: str | None) -> dict[str, Any]:
    return {
        "unit_id": str(unit_id),
        "type": type,
        "valid_until": valid_until.isoformat(),
        "notes": notes,
    }


async def list_reports(
    tenant: TenantContext, *, unit_id: UUID | None = None
) -> list[ComplianceReport]:
    """Os laudos VIGENTES das unidades que quem pergunta enxerga.

    O histórico não vem junto: quem quer saber quantas vezes o laudo já foi
    renovado lê `renewal_count`, e quem quer a cadeia inteira ainda não tem
    tela que a peça.
    """
    units = await visible_units(tenant)
    async with tenant_scope(tenant) as scope:
        await scope.execute(_LIST_SQL, {"units": units, "unit_id": unit_id})
        linhas = await scope.fetchall()
    return [_row_to_report(dict(linha)) for linha in linhas]


@dataclass(frozen=True, slots=True)
class StoredReport:
    """A linha crua da tabela — o que a renovação precisa saber sobre o anterior."""

    id: UUID
    unit_id: UUID
    unit_name: str
    type: str
    valid_until: date
    notes: str | None


async def load_report(tenant: TenantContext, report_id: UUID) -> StoredReport | None:
    """Um laudo do tenant, vigente ou não, sem recorte de unidade — quem recorta é quem chama."""
    async with tenant_scope(tenant) as scope:
        await scope.execute(_LOAD_SQL, {"report_id": report_id})
        linha = await scope.fetchone()
    if linha is None:
        return None
    return StoredReport(
        id=linha["id"],
        unit_id=linha["unit_id"],
        unit_name=linha["unit_name"],
        type=linha["type"],
        valid_until=linha["valid_until"],
        notes=linha["notes"],
    )


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------
async def _insert(
    tenant: TenantContext,
    *,
    unit_id: UUID,
    type: str,
    valid_until: date,
    notes: str | None,
    replaces_id: UUID | None,
    antes: dict[str, Any] | None,
) -> ComplianceReport:
    """Grava a linha, relê pela view e deixa a trilha — tudo numa transação só.

    A releitura não é luxo: `days_to_expiry` e `renewal_count` são da view, e
    recalculá-los aqui seria a terceira definição do mesmo número.
    """
    async with tenant_scope(tenant) as scope:
        await scope.execute(
            _INSERT_SQL,
            {
                "unit_id": unit_id,
                "type": type,
                "valid_until": valid_until,
                "notes": notes,
                "replaces_id": replaces_id,
                "created_by": tenant.user_id,
            },
        )
        gravado = await scope.fetchone()
        if gravado is None:
            raise ComplianceReportError(f"o laudo {type} não foi gravado")

        await scope.execute(_READ_ONE_SQL, {"report_id": gravado["id"]})
        linha = await scope.fetchone()
        if linha is None:
            raise ComplianceReportError(f"o laudo {gravado['id']} não voltou da view de vigentes")

        laudo = _row_to_report(dict(linha))
        await audit(
            scope,
            tenant,
            action="insert",
            entity="unit_compliance_report",
            entity_id=laudo.id,
            # `antes` preenchido é o que distingue renovação de cadastro na
            # trilha: o laudo que saiu fica gravado com o vencimento que valeu.
            antes=antes,
            depois=_trail(laudo.unit_id, laudo.type, laudo.valid_until, laudo.notes),
            origem=_ORIGEM,
        )
    return laudo


async def create_report(
    tenant: TenantContext,
    *,
    unit_id: UUID,
    type: str,
    valid_until: date,
    notes: str | None,
) -> ComplianceReport:
    """Cadastra o primeiro laudo daquele tipo na unidade.

    Segundo laudo do mesmo tipo não é cadastro, é renovação — e a recusa vem do
    índice, traduzida.
    """
    try:
        return await _insert(
            tenant,
            unit_id=unit_id,
            type=type,
            valid_until=valid_until,
            notes=notes,
            replaces_id=None,
            antes=None,
        )
    except errors.UniqueViolation as choque:
        # O tipo sai daqui como o gestor o digitou: canonicalizar em Python seria
        # a mesma regra em duas linguagens, que é o que o comentário do `_INSERT_SQL`
        # recusa. Numa mensagem de tela isso não muda número nenhum — mas é o
        # mesmo `str.upper()` que não concorda com `upper()` do Postgres em toda
        # entrada, e ele não precisa existir aqui.
        raise DuplicateComplianceReportError(
            f"já existe um laudo {type} nesta unidade — renove o vigente"
        ) from choque


async def renew_report(
    tenant: TenantContext,
    *,
    anterior: StoredReport,
    valid_until: date,
    notes: str | None,
) -> ComplianceReport:
    """Renova: linha nova apontando para a que sai. Nunca `update`, nunca `delete`.

    Unidade e tipo vêm do laudo anterior, não do cliente: renovação que
    atravessa unidade ou tipo não é renovação, e o FK composto a recusaria de
    qualquer jeito.
    """
    try:
        return await _insert(
            tenant,
            unit_id=anterior.unit_id,
            type=anterior.type,
            valid_until=valid_until,
            notes=notes,
            replaces_id=anterior.id,
            antes=_trail(anterior.unit_id, anterior.type, anterior.valid_until, anterior.notes),
        )
    except errors.UniqueViolation as choque:
        raise AlreadyRenewedError(
            f"o laudo {anterior.type} de {anterior.valid_until.isoformat()} já foi renovado; "
            "renove o vigente"
        ) from choque
