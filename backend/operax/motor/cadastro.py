"""The roster, promoted from the mirror — and the queue of what nobody mapped yet.

Production has 172 people in `secullum."Funcionario"` and **zero** rows in
`app.employee`. Nothing turned the mirror into the domain, so the workday engine
ran over an empty table and the dashboard opened with no data. This is that
missing link, and it lives next to `jornada.py` because it is the same shape:
read `secullum`, write `app`, idempotently, so the next sync lands instead of
leaving a stale copy behind.

COMPANY COMES FROM THE PERSON, NEVER FROM THE DEPARTMENT
Rule 5 of the project, and the reason it is a rule: about 26% of the FastPark
roster sits in a department that belongs to a different company than the person
does. `Funcionario.empresa_id` is the answer; `Departamento.empresa_id` is a
different question that looks like the same one. Deriving one from the other
would put a quarter of the payroll under the wrong company, consistently and
invisibly. The db-test asserts exactly this case.

UNITS ARE NOT INVENTED HERE
`app.unit` is **our** dimension — a physical car park — and the mirror has no
such concept. The bridge is `app.unit_secullum_map`, curated with the customer
one department at a time. So this module never creates a unit: a person whose
department has no mapping is promoted with `unit_id` null and shows up in the
pending queue, which is the S1 acceptance criterion ("zero colaborador ativo sem
unidade, **ou fila de pendência de mapeamento visível**"). Guessing a unit would
turn curation work into silent data.

THE MIRROR CARRIES NO MANAGER, SO NEITHER DOES THIS
`app.employee.manager_employee_id` stays null here. `secullum."Funcionario"` has
no column for a supervisor — checked against the production baseline, not
assumed — and it is one of the three fields `ownership.MATRIX` marks `pending`:
treated as the sync's until the customer says where it comes from. Filling it by
guessing the department's head would invent a hierarchy the source never claimed.

STATUS COMES FROM THE TERMINATION DATE, AND ONLY FROM IT
`Demissao` filled means `desligado`. Vacation and leave are day facts, not roster
facts — they live in `app.expected_workday` through `jornada.py`, which reads the
leave table directly. Writing `vacation` on a person here would make the status
mean two different things depending on who read it.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from uuid import UUID

from operax.core.tenant import SystemContext, active_tenants, tenant_scope

TASK = "motor.cadastro"

_COMPANIES_SQL = """
insert into app.company (tenant_id, cnpj, legal_name, trade_name, secullum_company_id, active)
select %(tenant_id)s::uuid,
       -- `[^0-9]` e não `\\D`: a classe POSIX não tem barra invertida, e o teste
       -- do `make db-test` lê este SQL como texto do arquivo — onde o escape do
       -- Python ainda está dobrado e chegaria ao Postgres como outra coisa.
       nullif(regexp_replace(e."Documento", '[^0-9]', '', 'g'), ''),
       e."Nome",
       e."Nome",
       e."EmpresaId",
       true
from secullum."Empresa" e
where e.tenant_id = %(tenant_id)s and e."EmpresaId" is not null
on conflict (tenant_id, secullum_company_id) do update set
    legal_name = excluded.legal_name,
    trade_name = excluded.trade_name,
    cnpj       = coalesce(excluded.cnpj, app.company.cnpj)
"""

#: O departamento é promovido para poder ser **nomeado** na fila de curadoria: sem
#: ele, a pendência seria um número do Secullum e ninguém saberia qual pátio é.
_DEPARTMENTS_SQL = """
insert into app.department (tenant_id, company_id, name, secullum_department_id, active)
select %(tenant_id)s::uuid, c.id, d."Descricao", d."DepartamentoId", d.ativo
from secullum."Departamento" d
join secullum."Empresa" e on e.id = d.empresa_id and e.tenant_id = %(tenant_id)s
join app.company c
  on c.tenant_id = %(tenant_id)s and c.secullum_company_id = e."EmpresaId"
where d.tenant_id = %(tenant_id)s and d."DepartamentoId" is not null
on conflict (tenant_id, secullum_department_id) do update set
    name       = excluded.name,
    company_id = excluded.company_id,
    active     = excluded.active
"""

#: ⛔ `company_id` sai de `Funcionario.empresa_id`. Trocar por
#:    `Departamento -> Empresa` põe cerca de um quarto da folha na empresa errada,
#:    de forma consistente e invisível — é a regra 5 do projeto.
_EMPLOYEES_SQL = """
insert into app.employee (
    tenant_id, company_id, unit_id, department_id, secullum_employee_id,
    registration_number, name, cargo, hired_on, terminated_on, status
)
select %(tenant_id)s::uuid,
       c.id,
       m.unit_id,
       dep.id,
       f."FuncionarioId",
       f."NumeroFolha",
       f."Nome",
       fu."Descricao",
       f."Admissao",
       f."Demissao",
       case when f."Demissao" is not null then 'desligado' else 'active' end
from secullum."Funcionario" f
join secullum."Empresa" e on e.id = f.empresa_id and e.tenant_id = %(tenant_id)s
join app.company c
  on c.tenant_id = %(tenant_id)s and c.secullum_company_id = e."EmpresaId"
left join secullum."Departamento" d
       on d.id = f.departamento_id and d.tenant_id = %(tenant_id)s
left join app.department dep
       on dep.tenant_id = %(tenant_id)s
      and dep.secullum_department_id = d."DepartamentoId"
left join app.unit_secullum_map m
       on m.tenant_id = %(tenant_id)s
      and m.secullum_department_id = d."DepartamentoId"
left join secullum."Funcao" fu on fu.id = f.funcao_id and fu.tenant_id = %(tenant_id)s
where f.tenant_id = %(tenant_id)s and f."FuncionarioId" is not null
on conflict (tenant_id, secullum_employee_id) do update set
    company_id          = excluded.company_id,
    department_id       = excluded.department_id,
    registration_number = excluded.registration_number,
    name                = excluded.name,
    cargo               = excluded.cargo,
    hired_on            = excluded.hired_on,
    terminated_on       = excluded.terminated_on,
    status              = excluded.status,
    -- A unidade só é escrita quando o mapa responde. Um mapeamento removido não
    -- pode apagar a lotação de quem já estava alocado: a curadoria é humana e a
    -- promoção não desfaz o trabalho dela.
    unit_id             = coalesce(excluded.unit_id, app.employee.unit_id),
    updated_at          = now()
"""

_TOTALS_SQL = """
select count(*)::int                                                    as employees,
       count(*) filter (where e.status <> 'desligado')::int              as active,
       count(*) filter (where e.status <> 'desligado' and e.unit_id is null)::int
                                                                        as without_unit
from app.employee e
where e.tenant_id = %(tenant_id)s
"""

#: A fila de curadoria: departamento sem mapa, com quanta gente depende dele.
#: Ordenada por peso porque é assim que se decide o que mapear primeiro.
_PENDING_SQL = """
select coalesce(d.name, '(sem departamento no espelho)') as department,
       d.secullum_department_id                          as secullum_id,
       count(*)::int                                     as employees
from app.employee e
left join app.department d on d.id = e.department_id
where e.tenant_id = %(tenant_id)s
  and e.status <> 'desligado'
  and e.unit_id is null
group by 1, 2
order by 3 desc, 1
"""


@dataclass(frozen=True, slots=True)
class PendingUnit:
    """Um departamento que ninguém mapeou, e o peso dele."""

    department: str
    secullum_id: int | None
    employees: int


@dataclass(frozen=True, slots=True)
class Promotion:
    tenant_id: UUID
    employees: int
    active: int
    without_unit: int
    pending: tuple[PendingUnit, ...]

    @property
    def mapped_ratio(self) -> float:
        return (self.active - self.without_unit) / self.active if self.active else 0.0


async def promote(context: SystemContext) -> Promotion:
    """Empresa, departamento e colaborador, do espelho para o domínio.

    Numa transação só: um colaborador promovido cuja empresa ainda não existe
    falha na FK, e meio quadro promovido é pior do que nenhum — o motor rodaria
    sobre uma base que parece completa.
    """
    async with tenant_scope(context) as scope:
        await scope.execute(_COMPANIES_SQL, {})
        await scope.execute(_DEPARTMENTS_SQL, {})
        await scope.execute(_EMPLOYEES_SQL, {})
        await scope.execute(_TOTALS_SQL, {})
        totais = await scope.fetchone()
        await scope.execute(_PENDING_SQL, {})
        pendentes = await scope.fetchall()

    return Promotion(
        tenant_id=context.tenant_id,
        employees=totais["employees"],
        active=totais["active"],
        without_unit=totais["without_unit"],
        pending=tuple(
            PendingUnit(
                department=p["department"], secullum_id=p["secullum_id"], employees=p["employees"]
            )
            for p in pendentes
        ),
    )


async def run() -> list[Promotion]:
    return [await promote(ctx) for ctx in await active_tenants(TASK)]


def relatorio(promocoes: list[Promotion]) -> str:
    """O aceite do S1 em texto: quadro promovido e fila de mapeamento visível."""
    linhas: list[str] = []
    for p in promocoes:
        linhas.append(
            f"tenant {p.tenant_id} · {p.employees} colaborador(es) no domínio, "
            f"{p.active} ativo(s) · {100 * p.mapped_ratio:.1f}% com unidade"
        )
        for pendente in p.pending:
            linhas.append(
                f"    sem unidade: {pendente.employees} em «{pendente.department}» "
                f"(Departamento {pendente.secullum_id})"
            )
        if not p.pending and p.active:
            linhas.append("    nenhuma pendência: todo ativo tem unidade")
    return "\n".join(linhas) or "nenhum tenant ativo"


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        description="Promove empresa, departamento e colaborador do espelho para o domínio."
    ).parse_args(argv)
    print(relatorio(asyncio.run(run())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
