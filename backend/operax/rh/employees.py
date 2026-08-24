"""A aba Colaboradores — o que ela lê e as três coisas que ela escreve.

WHY THE READS RUN AS THE USER
The list mixes domains: a person's next expiry can be an ASO (health), a driving
licence (PII) or the end of the 30-day trial (neither). Deciding which of those a
caller may see in Python would be the sensitive-domain matrix written a second
time, in another language, drifting from the policies at the first change. So the
whole read runs through `user_scope` and RLS answers: whoever lacks the health
domain gets no ASO row, and the column simply does not mention one. Nothing to
hide, because nothing was fetched.

The detail asks `util.can_see_domain` on top of that, and only there, for the one
thing RLS cannot express: "you may not see salaries" and "this person has no
salary on record" are both an empty list, and the screen has to tell them apart —
one renders no tab at all, the other renders an empty state.

WHY THE WRITES RUN AS THE BACKEND
Same reason as the import (`repository.py`): `app.audit_log` grants insert to
nobody but `service_role`, and SPEC §8 requires every write to carry its author
and origin. The row and the log that describes it commit together or not at all.
Authorisation is not re-implemented — `check_permissions` asks the same
`util.is_admin` and `util.can_see_domain` the policies call, as the user asking,
before the write transaction opens.

WHY THE FORM CALLS THE SAME VALIDATORS AS THE SPREADSHEET
Rule 1 of the step. `PATCH /rh/employees/{id}` and a line of `hr_employee.xlsx`
are the same edit arriving by different doors, and they go through
`operax/rh/validators.py` either way. Upload is the form in bulk.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from operax.core.tenant import TenantContext, tenant_scope, user_scope
from operax.rh.ownership import MATRIX, Field, Owner
from operax.rh.repository import CLOSE_BAND_SQL, NEW_BAND_SQL, audit

#: Teto de linhas da lista. A FastPark tem ~172 pessoas; o corte existe para que
#: um tenant grande não derrube a tela, e a resposta diz que cortou.
MAX_ROWS = 300

#: O que a trilha de auditoria grava como origem da escrita vinda da tela.
_ORIGEM = {"form": "rh_colaboradores"}

#: Janela padrão de "próximos vencimentos", em dias. Só limita o futuro: o que já
#: venceu aparece sempre, porque vencido é exatamente o que a lista existe para
#: mostrar.
DEFAULT_WINDOW_DAYS = 60

# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
# `vencimentos` junta as três origens de prazo do cadastro. As duas primeiras
# passam por RLS — exame é domínio de saúde, documento é PII —, então quem não
# alcança o domínio não vê aquele prazo e a coluna nem o menciona. A terceira
# sai da data de admissão e não é sensível.
_LIST_SQL = """
with base as (
    select e.id as employee_id, e.name, e.registration_number, e.hr_code,
           e.cargo, e.status, e.hired_on, e.unit_id, u.name as unit_name
    from app.employee e
    left join app.unit u on u.id = e.unit_id
    where (%(unidade)s::uuid is null or e.unit_id = %(unidade)s::uuid)
      and (%(status)s::text is null or e.status = %(status)s::text)
      and (%(busca)s::text is null
           or e.name ilike %(busca)s
           or e.registration_number ilike %(busca)s
           or e.hr_code ilike %(busca)s)
),
vencimentos as (
    select x.employee_id, 'aso' as kind, 'ASO' as label, x.valid_until as due_on
    from app.occupational_exam x
    join base b on b.employee_id = x.employee_id
    where x.valid_until is not null
    union all
    select d.employee_id, 'documento', dt.name, d.valid_until
    from app.document d
    join app.document_type dt on dt.id = d.type_id
    join base b on b.employee_id = d.employee_id
    where d.status = 'active' and d.valid_until is not null
    union all
    -- Experiência só conta enquanto não passou. Documento vencido é problema de
    -- hoje; dia 30 de contrato que ficou para trás é história, e deixá-lo na
    -- fila colocaria toda gente admitida há mais de dois meses no topo da lista,
    -- para sempre.
    select b.employee_id, 'experiencia', 'Experiência 30 dias', b.hired_on + 30
    from base b where b.hired_on is not null and b.hired_on + 30 >= %(hoje)s::date
    union all
    select b.employee_id, 'experiencia', 'Experiência 60 dias', b.hired_on + 60
    from base b where b.hired_on is not null and b.hired_on + 60 >= %(hoje)s::date
)
select b.employee_id, b.name, b.registration_number, b.hr_code, b.cargo,
       b.status, b.hired_on, b.unit_id, b.unit_name,
       v.kind as due_kind, v.label as due_label, v.due_on
from base b
left join lateral (
    select k.kind, k.label, k.due_on
    from vencimentos k
    where k.employee_id = b.employee_id and k.due_on <= %(ate)s::date
    order by k.due_on
    limit 1
) v on true
where %(pendencia)s::text is null
   or (%(pendencia)s::text = 'vinculo' and b.hr_code is null)
   or exists (
        select 1 from vencimentos k
        where k.employee_id = b.employee_id
          and k.kind = %(pendencia)s::text
          and k.due_on <= %(ate)s::date
      )
order by v.due_on nulls last, b.name
limit %(limite)s
"""

_DETAIL_SQL = """
    select e.id as employee_id, e.name, e.registration_number, e.hr_code,
           e.cargo, e.status, e.hired_on, e.terminated_on, e.employment_type,
           e.unit_id, u.name as unit_name,
           c.trade_name as company_name,
           d.name as department_name,
           g.name as manager_name
    from app.employee e
    left join app.unit u        on u.id = e.unit_id
    left join app.company c     on c.id = e.company_id
    left join app.department d  on d.id = e.department_id
    left join app.employee g    on g.id = e.manager_employee_id
    where e.id = %(employee_id)s
"""

_POSITIONS_SQL = """
    select p.effective_from, p.effective_to, p.cargo, u.name as unit_name
    from app.employee_position p
    left join app.unit u on u.id = p.unit_id
    where p.employee_id = %(employee_id)s
    order by p.effective_from desc
"""

_COMPENSATION_SQL = """
    select r.effective_from, r.effective_to, r.salary, r.reason
    from app.employee_compensation r
    where r.employee_id = %(employee_id)s
    order by r.effective_from desc
"""

_PII_SQL = """
    select p.cpf, p.rg, p.pis, p.ctps, p.birth_date, p.mother_name,
           p.father_name, p.phone, p.personal_email
    from app.employee_pii p
    where p.employee_id = %(employee_id)s
"""

_DOCUMENTS_SQL = """
    select dt.name as type_name, doc.issued_on, doc.valid_until, doc.status
    from app.document doc
    join app.document_type dt on dt.id = doc.type_id
    where doc.employee_id = %(employee_id)s and doc.status = 'active'
    order by doc.valid_until nulls last
"""

_EXAMS_SQL = """
    select x.type, x.performed_on, x.valid_until, x.result
    from app.occupational_exam x
    where x.employee_id = %(employee_id)s
    order by x.performed_on desc
"""

_LEAVES_SQL = """
    select l.category, l.start_date, l.end_date, l.source
    from app.leave_period l
    where l.employee_id = %(employee_id)s
    order by l.start_date desc
"""

_MOVEMENTS_SQL = """
    select m.type, m.event_date, m.notes, u.name as unit_name
    from app.workforce_movement m
    left join app.unit u on u.id = m.unit_id
    where m.employee_id = %(employee_id)s
    order by m.event_date desc
"""

_AGREEMENTS_SQL = """
    select a.id, a.type, a.description, a.total_amount, a.installment_count,
           a.agreement_date, a.status,
           count(i.id) filter (where i.status = 'pending') as pending_installments
    from app.financial_agreement a
    left join app.agreement_installment i on i.agreement_id = a.id
    where a.employee_id = %(employee_id)s
    group by a.id
    order by a.agreement_date desc
"""

_CURRENT_FOR_EDIT_SQL = """
    select e.id as employee_id, e.registration_number, e.name, e.hr_code,
           e.employment_type, e.cargo, p.ctps
    from app.employee e
    left join app.employee_pii p on p.employee_id = e.id
    where e.id = %(employee_id)s
"""

_HR_CODE_TAKEN_SQL = """
    select e.id as employee_id, e.hr_code
    from app.employee e
    where e.hr_code is not null
"""

_OPEN_BAND_SQL = """
    select r.effective_from
    from app.employee_compensation r
    where r.employee_id = %(employee_id)s and r.effective_to is null
    order by r.effective_from desc
    limit 1
"""

_OPEN_POSITION_SQL = """
    select p.effective_from
    from app.employee_position p
    where p.employee_id = %(employee_id)s and p.effective_to is null
    order by p.effective_from desc
    limit 1
"""

# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------
_CLOSE_POSITION_SQL = """
    update app.employee_position
       set effective_to = (%(effective_from)s::date - 1)
     where employee_id = %(employee_id)s
       and tenant_id = %(tenant_id)s
       and effective_to is null
"""

_NEW_POSITION_SQL = """
    insert into app.employee_position
      (tenant_id, employee_id, effective_from, cargo, unit_id)
    values
      (%(tenant_id)s, %(employee_id)s, %(effective_from)s, %(cargo)s, %(unit_id)s)
    returning id
"""

# `employee.cargo` é o valor corrente e a vigência é quem manda: abrir uma
# posição nova sem mover o corrente deixaria a lista mostrando o cargo antigo.
_SYNC_CARGO_SQL = """
    update app.employee
       set cargo = %(cargo)s, updated_at = now()
     where id = %(employee_id)s and tenant_id = %(tenant_id)s
    returning id
"""


def _row(scope_row: Any) -> dict[str, Any]:
    return dict(scope_row) if scope_row else {}


async def list_employees(
    tenant: TenantContext,
    *,
    unidade: UUID | None,
    status: str | None,
    busca: str | None,
    pendencia: str | None,
    janela_dias: int,
    hoje: date,
) -> tuple[list[dict[str, Any]], bool]:
    """A lista da aba, com o prazo mais urgente de cada pessoa.

    Devolve também se cortou: uma lista truncada em silêncio faz o usuário
    concluir que quem falta não existe.
    """
    params = {
        "unidade": unidade,
        "status": status,
        "busca": f"%{busca.strip()}%" if busca and busca.strip() else None,
        "pendencia": pendencia,
        "hoje": hoje,
        "ate": hoje + timedelta(days=janela_dias),
        "limite": MAX_ROWS + 1,
    }
    async with user_scope(tenant) as scope:
        await scope.execute(_LIST_SQL, params)
        linhas = [dict(linha) for linha in await scope.fetchall()]
    return linhas[:MAX_ROWS], len(linhas) > MAX_ROWS


async def load_employee(
    tenant: TenantContext,
    employee_id: UUID,
    *,
    pii: bool,
    compensation: bool,
    health: bool,
) -> dict[str, Any] | None:
    """Uma pessoa, com os blocos que o domínio de quem pergunta alcança.

    Bloco fora do alcance volta `None` — ausente, não vazio. É a distinção que a
    tela usa para não renderizar a aba: quem não pode ver salário não fica
    sabendo que existe salário.
    """
    async with user_scope(tenant) as scope:
        await scope.execute(_DETAIL_SQL, {"employee_id": employee_id})
        pessoa = await scope.fetchone()
        if pessoa is None:
            return None

        await scope.execute(_POSITIONS_SQL, {"employee_id": employee_id})
        positions = [dict(linha) for linha in await scope.fetchall()]

        await scope.execute(_LEAVES_SQL, {"employee_id": employee_id})
        leaves = [dict(linha) for linha in await scope.fetchall()]

        await scope.execute(_MOVEMENTS_SQL, {"employee_id": employee_id})
        movements = [dict(linha) for linha in await scope.fetchall()]

        detalhe: dict[str, Any] = {
            "employee": dict(pessoa),
            "positions": positions,
            "leaves": leaves,
            "movements": movements,
            "pii": None,
            "documents": None,
            "exams": None,
            "compensation": None,
            "agreements": None,
        }

        if pii:
            await scope.execute(_PII_SQL, {"employee_id": employee_id})
            detalhe["pii"] = _row(await scope.fetchone())
            await scope.execute(_DOCUMENTS_SQL, {"employee_id": employee_id})
            detalhe["documents"] = [dict(linha) for linha in await scope.fetchall()]
        if health:
            await scope.execute(_EXAMS_SQL, {"employee_id": employee_id})
            detalhe["exams"] = [dict(linha) for linha in await scope.fetchall()]
        if compensation:
            await scope.execute(_COMPENSATION_SQL, {"employee_id": employee_id})
            detalhe["compensation"] = [dict(linha) for linha in await scope.fetchall()]
            await scope.execute(_AGREEMENTS_SQL, {"employee_id": employee_id})
            detalhe["agreements"] = [dict(linha) for linha in await scope.fetchall()]

    return detalhe


async def load_for_edit(
    tenant: TenantContext, employee_id: UUID
) -> tuple[dict[str, Any] | None, dict[str, UUID]]:
    """O valor corrente das colunas editáveis, e quem já usa cada ID RH."""
    async with user_scope(tenant) as scope:
        await scope.execute(_CURRENT_FOR_EDIT_SQL, {"employee_id": employee_id})
        atual = await scope.fetchone()
        await scope.execute(_HR_CODE_TAKEN_SQL)
        tomados = {
            str(linha["hr_code"]).strip(): linha["employee_id"] for linha in await scope.fetchall()
        }
    return (dict(atual) if atual else None), tomados


async def open_band(tenant: TenantContext, employee_id: UUID, *, position: bool) -> date | None:
    """O início da faixa aberta hoje — remuneração ou posição."""
    async with user_scope(tenant) as scope:
        await scope.execute(
            _OPEN_POSITION_SQL if position else _OPEN_BAND_SQL,
            {"employee_id": employee_id},
        )
        linha = await scope.fetchone()
    return linha["effective_from"] if linha else None


# ---------------------------------------------------------------------------
# As três escritas — cada uma com a auditoria na mesma transação
# ---------------------------------------------------------------------------
# O que o formulário de cadastro escreve, derivado da matriz em vez de listado à
# mão: dono RH, sem vigência, e numa das duas tabelas que a aba edita. Dá
# `hr_code`, `employment_type` e `ctps` — o resto ou é do sync, ou é vigência
# (que se cria, não se edita), ou não tem coluna. Derivar importa porque o dia em
# que a matriz mudar de ideia sobre um campo, esta lista muda junto.
_FORM_TABLES = ("employee", "employee_pii")
EDITABLE_FIELDS: tuple[Field, ...] = tuple(
    campo
    for campo in MATRIX
    if campo.owner is Owner.HR and not campo.versioned and campo.table in _FORM_TABLES
)
_TABELA_DA_COLUNA = {campo.column: campo.table for campo in EDITABLE_FIELDS}


async def update_employee(
    tenant: TenantContext,
    employee_id: UUID,
    valores: dict[str, Any],
    anteriores: dict[str, Any],
) -> None:
    """Grava os campos de dono RH, um `update` por tabela, tudo auditado."""
    por_tabela: dict[str, list[str]] = {}
    for coluna in valores:
        por_tabela.setdefault(_TABELA_DA_COLUNA[coluna], []).append(coluna)

    async with tenant_scope(tenant) as scope:
        for tabela, colunas in por_tabela.items():
            dados = {coluna: valores[coluna] for coluna in colunas}
            if tabela == "employee":
                sets = ", ".join(f"{coluna} = %({coluna})s" for coluna in colunas)
                await scope.execute(
                    f"update app.employee set {sets}, updated_at = now() "
                    f"where id = %(employee_id)s and tenant_id = %(tenant_id)s returning id",
                    {**dados, "employee_id": employee_id},
                )
            else:
                campos = ", ".join(colunas)
                marcadores = ", ".join(f"%({coluna})s" for coluna in colunas)
                atualiza = ", ".join(f"{coluna} = excluded.{coluna}" for coluna in colunas)
                await scope.execute(
                    f"insert into app.{tabela} (employee_id, tenant_id, {campos}, updated_at) "
                    f"values (%(employee_id)s, %(tenant_id)s, {marcadores}, now()) "
                    f"on conflict (employee_id) do update set {atualiza}, updated_at = now() "
                    f"where {tabela}.tenant_id = %(tenant_id)s "
                    f"returning employee_id",
                    {**dados, "employee_id": employee_id},
                )
            await audit(
                scope,
                tenant,
                action="update",
                entity=tabela,
                entity_id=employee_id,
                antes={coluna: anteriores.get(coluna) for coluna in colunas},
                depois=dados,
                origem=_ORIGEM,
            )


async def create_compensation(
    tenant: TenantContext,
    employee_id: UUID,
    *,
    effective_from: date,
    salary: Decimal,
    reason: str | None,
    anterior: dict[str, Any],
) -> None:
    """Fecha a faixa aberta e abre a próxima. Corrigir é revogar, não editar.

    O SQL é o mesmo que o import usa (`repository.CLOSE_BAND_SQL` /
    `NEW_BAND_SQL`): abrir faixa de vigência acontece num lugar só, ou o
    formulário e a planilha divergem no dia em que uma das duas mudar.
    """
    dados = {
        "employee_id": employee_id,
        "effective_from": effective_from,
        "salary": salary,
        "reason": reason,
        "user_id": tenant.user_id,
    }
    async with tenant_scope(tenant) as scope:
        await scope.execute(CLOSE_BAND_SQL, dados)
        await scope.execute(NEW_BAND_SQL, dados)
        criada = await scope.fetchone()
        await audit(
            scope,
            tenant,
            action="insert",
            entity="employee_compensation",
            entity_id=criada["id"] if criada else employee_id,
            antes=anterior,
            depois={chave: valor for chave, valor in dados.items() if chave != "user_id"},
            origem=_ORIGEM,
        )


async def create_position(
    tenant: TenantContext,
    employee_id: UUID,
    *,
    effective_from: date,
    cargo: str,
    unit_id: UUID | None,
    anterior: dict[str, Any],
) -> None:
    """Nova vigência de posição, e o cargo corrente andando junto."""
    dados = {
        "employee_id": employee_id,
        "effective_from": effective_from,
        "cargo": cargo,
        "unit_id": unit_id,
    }
    async with tenant_scope(tenant) as scope:
        await scope.execute(_CLOSE_POSITION_SQL, dados)
        await scope.execute(_NEW_POSITION_SQL, dados)
        criada = await scope.fetchone()
        await scope.execute(_SYNC_CARGO_SQL, {"employee_id": employee_id, "cargo": cargo})
        await audit(
            scope,
            tenant,
            action="insert",
            entity="employee_position",
            entity_id=criada["id"] if criada else employee_id,
            antes=anterior,
            depois=dados,
            origem=_ORIGEM,
        )
