"""Every statement the payroll import runs, and which identity runs it.

The split is the one `operax/rh/` already uses and for the same reason:
`payroll.py` decides and never writes, this module writes and never decides. The
preview screen has to show what *would* happen before anyone confirms, and a
decider that writes cannot be asked twice.

TWO IDENTITIES, THE SAME AS THE HR IMPORT
Reads go through `user_scope`: the transaction becomes the authenticated user and
the policies that already guard the browser decide what comes back. A payroll
line naming somebody the importer cannot see never resolves to an id, and the
answer is "matrícula não existe entre os colaboradores que você enxerga".

Writes go through `tenant_scope` (`service_role`), because `app.audit_log` grants
insert to nobody else and the rows plus the trail that describes them have to
commit together.

A exceção é `fetch_mapped_codes`, e ela está declarada lá: a curadoria de rubrica
é metadado do tenant, não dado de pessoa, e a pergunta "este código está curado?"
tem UM dono — `operax/dp/rubricas.py`.

WHAT IS AUDITED IS THE FILE, NOT THE LINE
The HR import audits every line, because each one is a fact a person edited about
another person. A payroll line is not that: it is one of a thousand rows of a
statement that only means anything whole, and a thousand `audit_log` rows per
month would bury the trail the table exists for (its own comment says it grows
fast). So the audit here is one row for the replacement and one for the import,
each carrying the competência, the row count and the total — and the per-line
detail stays where it is already kept whole: `app.file_import.report`, next to the
very file that produced it, in Storage.

A COMPETÊNCIA É SUBSTITUÍDA, NÃO SOMADA
Reenviar o arquivo de uma competência substitui o que estava lá. A folha é uma
declaração fechada do mês: somar o reenvio dobraria todo valor, e "pular o que já
existe" faria uma correção de valor não ter efeito nenhum — que é o pior dos
dois, porque parece que funcionou. O que garante que nada se perde é o arquivo
anterior continuar guardado e a auditoria dizer quantas linhas saíram.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from operax.core.tenant import TenantContext, tenant_scope, user_scope
from operax.dp import rubricas
from operax.imports.payroll import LineOutcome
from operax.rh.repository import SAVE_REPORT_SQL, audit, jsonb

#: O que `app.payroll_entry.source` recebe: o arquivo veio de planilha, e é essa
#: coluna que separa a folha importada de uma que um dia venha por API.
SOURCE = "spreadsheet"


class PayrollWriteError(RuntimeError):
    """A gravação da folha não pode acontecer como foi pedida."""


class ClosedPeriodError(PayrollWriteError):
    """A competência está fechada. Nada entra e nada sai dela."""


class PartialPayrollError(PayrollWriteError):
    """O arquivo tem linha com erro, e folha pela metade é soma errada."""


@dataclass(frozen=True, slots=True)
class EmployeeRef:
    """A pessoa que a matrícula encontra, com o que a linha da folha precisa.

    `company_id` vem daqui e nunca do departamento — regra 5 do `CLAUDE.md`, e
    ~26% dos vínculos da FastPark divergem entre os dois caminhos.
    """

    employee_id: UUID
    company_id: UUID
    unit_id: UUID | None


@dataclass(frozen=True, slots=True)
class PeriodState:
    """O que já existe na competência, antes de o arquivo tocar nela."""

    period_id: UUID | None
    status: str | None
    entries: int
    imported_at: datetime | None

    @property
    def closed(self) -> bool:
        return self.status == "fechada"


@dataclass(frozen=True, slots=True)
class Applied:
    """O que a confirmação fez."""

    period_id: UUID
    applied: int
    replaced: int


_EMPLOYEES_SQL = """
    select e.id           as employee_id,
           e.registration_number,
           e.company_id,
           e.unit_id
    from app.employee e
    where e.registration_number is not null
"""

_PERIOD_SQL = """
    select p.id, p.status,
           (select count(*) from app.payroll_entry e where e.payroll_period_id = p.id)
             as entries,
           (select max(f.created_at) from app.file_import f where f.payroll_period_id = p.id)
             as imported_at
    from app.payroll_period p
    where p.tenant_id = %(tenant_id)s and p.year = %(year)s and p.month = %(month)s
"""

_ENTRIES_SQL = """
    select e.registration_number as employee_code,
           e.name                as employee_name,
           pe.code, pe.description, pe.nature, pe.reference, pe.amount
    from app.payroll_entry pe
    join app.payroll_period pp on pp.id = pe.payroll_period_id
    left join app.employee e on e.id = pe.employee_id
    where pp.year = %(year)s and pp.month = %(month)s
    order by e.registration_number nulls last, pe.code
"""

# `do update` com `where` em vez de guarda só no Python: entre o preview e a
# confirmação alguém pode fechar a competência, e aí o insert não devolve id —
# que é como esta função descobre que precisa recusar.
_ENSURE_PERIOD_SQL = """
    insert into app.payroll_period (tenant_id, year, month, status)
    values (%(tenant_id)s, %(year)s, %(month)s, 'importada')
    on conflict (tenant_id, year, month) do update
       set status = 'importada'
     where app.payroll_period.status <> 'fechada'
    returning id
"""

_DELETE_ENTRIES_SQL = """
    delete from app.payroll_entry
     where tenant_id = %(tenant_id)s and payroll_period_id = %(period_id)s
    returning id
"""

_INSERT_ENTRY_SQL = """
    insert into app.payroll_entry
      (tenant_id, payroll_period_id, employee_id, company_id, unit_id,
       code, description, nature, reference, amount, source, import_id)
    values
      (%(tenant_id)s, %(period_id)s, %(employee_id)s, %(company_id)s, %(unit_id)s,
       %(code)s, %(description)s, %(nature)s, %(reference)s, %(amount)s,
       %(source)s, %(import_id)s)
"""

_LINK_PERIOD_SQL = """
    update app.file_import
       set payroll_period_id = %(period_id)s
     where id = %(import_id)s and tenant_id = %(tenant_id)s
"""


# ---------------------------------------------------------------------------
# Leitura — como o usuário
# ---------------------------------------------------------------------------
async def fetch_employees(tenant: TenantContext) -> dict[str, EmployeeRef]:
    """Matrícula -> pessoa, no alcance de quem está importando.

    Sem filtro de tenant no statement de propósito: sob `user_scope` a RLS está
    em vigor e a leitura de outro cliente não é filtro esquecido, é impossível.
    """
    async with user_scope(tenant) as scope:
        await scope.execute(_EMPLOYEES_SQL)
        linhas = await scope.fetchall()

    indice: dict[str, EmployeeRef] = {}
    for linha in linhas:
        matricula = str(linha["registration_number"]).strip()
        if matricula:
            indice[matricula] = EmployeeRef(
                employee_id=linha["employee_id"],
                company_id=linha["company_id"],
                unit_id=linha["unit_id"],
            )
    return indice


async def fetch_mapped_codes(tenant: TenantContext) -> frozenset[str]:
    """Os códigos de evento já curados com a contabilidade: classificados E conferidos.

    ⛔ QUEM RESPONDE "ESTÁ CURADO?" É `rubricas.read_curation`, E SÓ ELE
    Esta função já perguntou `select code from app.payroll_event_map`, e a
    resposta era exata enquanto `category` fosse `not null`: existir linha no
    mapa equivalia a ter categoria. `dp_payroll_code_map` semeia uma linha por
    código da folha com `category` NULO, e o mesmo predicado passou a responder
    outra pergunta — "o código é conhecido", que é verdade para TODOS eles. O
    sintoma seria a tela de import dizendo "nenhuma pendência" com a curadoria
    inteira por fazer, enquanto `PayrollCodeList.pending` dizia o contrário.
    Duas definições de "curado" discordando é exatamente o silêncio que a
    curadoria existe para eliminar.

    ⚠️ E A IDENTIDADE MUDA AQUI, DE PROPÓSITO. `read_curation` lê sob
    `tenant_scope`, não sob o `user_scope` das outras leituras deste módulo. As
    outras leem dado de PESSOA, e ver menos é a resposta certa para quem alcança
    menos; o catálogo de rubrica é metadado do tenant, sem pessoa e sem valor, e
    os dois lados do `union` carregam o próprio `tenant_id`. A rota já revalidou
    `is_admin` e o domínio `compensation` antes de chegar aqui.

    O que falta aqui não recusa linha nenhuma: vira o aviso `codigo_sem_categoria`
    e a lista que a curadoria recebe.
    """
    curadoria = await rubricas.read_curation(tenant)
    return frozenset(curadoria.categories)


async def fetch_period(tenant: TenantContext, *, year: int, month: int) -> PeriodState:
    """O estado da competência: existe, está fechada, tem quanto lá dentro."""
    async with tenant_scope(tenant) as scope:
        await scope.execute(_PERIOD_SQL, {"year": year, "month": month})
        linha = await scope.fetchone()
    if linha is None:
        return PeriodState(period_id=None, status=None, entries=0, imported_at=None)
    return PeriodState(
        period_id=linha["id"],
        status=linha["status"],
        entries=int(linha["entries"] or 0),
        imported_at=linha["imported_at"],
    )


async def fetch_entries(tenant: TenantContext, *, year: int, month: int) -> list[dict[str, Any]]:
    """O que está gravado na competência, no formato das colunas do modelo.

    É o pré-preenchimento do template: corrigir uma folha é baixar o que entrou,
    mexer na linha errada e reenviar — não redigitar mil linhas.
    """
    async with user_scope(tenant) as scope:
        await scope.execute(_ENTRIES_SQL, {"year": year, "month": month})
        return [dict(linha) for linha in await scope.fetchall()]


# ---------------------------------------------------------------------------
# Escrita — como o backend, com a auditoria na mesma transação
# ---------------------------------------------------------------------------
async def apply_payroll(
    tenant: TenantContext,
    *,
    import_id: UUID,
    year: int,
    month: int,
    outcomes: tuple[LineOutcome, ...],
    employees: dict[UUID, EmployeeRef],
    rows_total: int,
    rows_ok: int,
    rows_error: int,
    report: dict[str, Any],
) -> Applied:
    """Substitui a competência pelo arquivo, audita e fecha o import — de uma vez.

    Uma transação só, pelo mesmo motivo do RH: o log que diz "esta folha veio
    deste arquivo" não pode existir sem as linhas, nem elas sem ele. E aqui há um
    segundo motivo — entre apagar a competência antiga e gravar a nova não pode
    existir instante em que a folha do mês está vazia.
    """
    if any(o.errors for o in outcomes):
        # A recusa vive aqui, e não só no endpoint, porque é a que não se
        # contorna. Folha com linha fora é uma soma que não bate com holerite
        # nenhum, e "importei 998 de 1000" é justamente o erro que ninguém vê.
        raise PartialPayrollError(
            "arquivo com linha em erro não é importado pela metade: a soma da competência "
            "deixaria de bater. Corrija as linhas apontadas e reenvie o arquivo."
        )

    total = sum((o.values.get("amount") or Decimal(0)) for o in outcomes)

    async with tenant_scope(tenant) as scope:
        await scope.execute(_ENSURE_PERIOD_SQL, {"year": year, "month": month})
        criado = await scope.fetchone()
        if criado is None:
            raise ClosedPeriodError(
                f"a competência {year:04d}-{month:02d} está fechada e não recebe importação."
            )
        period_id = criado["id"]

        await scope.execute(_DELETE_ENTRIES_SQL, {"period_id": period_id})
        apagadas = len(await scope.fetchall())
        if apagadas:
            await audit(
                scope,
                tenant,
                action="delete",
                entity="payroll_entry",
                entity_id=period_id,
                antes={"period": _competencia(year, month), "rows": apagadas},
                depois={"replaced_by_import": str(import_id)},
                origem={"file_import_id": str(import_id)},
            )

        for outcome in outcomes:
            pessoa = employees[outcome.employee_id] if outcome.employee_id else None
            if pessoa is None:
                # Inalcançável: matrícula que não resolve é erro de linha, e
                # arquivo com erro parou lá em cima. A asserção é barata e o
                # sintoma sem ela seria uma linha de folha sem empresa.
                raise PartialPayrollError(
                    f"linha {outcome.line} chegou à gravação sem colaborador resolvido."
                )
            await scope.execute(
                _INSERT_ENTRY_SQL,
                {
                    "period_id": period_id,
                    "employee_id": pessoa.employee_id,
                    "company_id": pessoa.company_id,
                    "unit_id": pessoa.unit_id,
                    "code": outcome.values.get("code"),
                    "description": _ou_nulo(outcome.values.get("description")),
                    "nature": outcome.values.get("nature"),
                    "reference": outcome.values.get("reference"),
                    "amount": outcome.values.get("amount"),
                    "source": SOURCE,
                    "import_id": import_id,
                },
            )

        await audit(
            scope,
            tenant,
            action="insert",
            entity="payroll_entry",
            entity_id=period_id,
            antes={"rows": apagadas} if apagadas else None,
            depois={
                "period": _competencia(year, month),
                "rows": len(outcomes),
                "amount_total": total,
                "source": SOURCE,
            },
            origem={"file_import_id": str(import_id)},
        )

        await scope.execute(_LINK_PERIOD_SQL, {"period_id": period_id, "import_id": import_id})
        await scope.execute(
            SAVE_REPORT_SQL,
            {
                "import_id": import_id,
                "status": "processed",
                "rows_total": rows_total,
                "rows_ok": rows_ok,
                "rows_error": rows_error,
                "report": jsonb(report),
            },
        )

    return Applied(period_id=period_id, applied=len(outcomes), replaced=apagadas)


async def record_template_export(
    tenant: TenantContext, *, year: int, month: int, rows: int
) -> None:
    """O download do modelo é registrado — o arquivo leva o dado embora (SPEC §2)."""
    async with tenant_scope(tenant) as scope:
        await audit(
            scope,
            tenant,
            action="export",
            entity="payroll_template",
            entity_id=_competencia(year, month),
            antes=None,
            depois={"period": _competencia(year, month), "rows": rows},
            origem={"period": _competencia(year, month)},
        )


def _competencia(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _ou_nulo(valor: Any) -> Any:
    """Texto vazio é ausência de texto, e a coluna já aceita nulo."""
    return valor if valor not in ("", None) else None
