"""Punches, read as domain — the one place the bridge to the mirror is written.

`app.batida_marcacao` is ingestion: the Edge Function transposes one column of
the source's day-record (`Entrada1`..`Saida5`) into one row here, and it keys the
person by `secullum."Funcionario".id`, a uuid of the mirror. Nothing in `app`
carries that uuid. Crossing from one to the other means
`app.employee.secullum_employee_id = secullum."Funcionario"."FuncionarioId"`,
tenant by tenant — the same bridge `regras.py` walks, written once here so the
monitor and the individual consultation cannot come to disagree about who
punched.

TWO CONSEQUENCES OF THE MIRROR BEING UNREACHABLE TO THE USER

`secullum` is revoked from `authenticated` at the schema level (migration 01), so
these statements **cannot** run under `user_scope`: RLS is not what stops them,
the absence of `usage` is. They run under `tenant_scope`, as `service_role`,
which ignores RLS — and that would be a hole if the caller chose the rows.

The caller never does. Both consumers authorise first and enrich second: the
individual consultation resolves the person under `user_scope` and answers 404
when the policies return nothing, and the monitor counts these ids inside its own
`user_scope` statement, so an id the caller may not see is an id that matches no
countable row. The scope filter stays where it already is — in the policy — and
is not written a second time here.

WHAT COUNTS AS A PUNCH, AND WHY IT MATCHES THE ENGINE
A row with `hora is null` is a column that exists and holds no time: a status
label ("Férias"), or the known hole where the source filled nothing. It is not a
punch, and the data dictionary says so. `desconsiderada` is a punch somebody
discarded at the source, and `regras.py` already excludes it from detection —
counting it here would put a person in "com marcação" on the same screen where
the engine reports `no_punches` about them.
"""

from __future__ import annotations

# The bridge. Two joins and a tenant, and every statement below opens with it.
_BRIDGE = """
    from app.batida_marcacao m
    join secullum."Funcionario" f on f.id = m.funcionario_id
    join app.employee e on e.tenant_id = m.tenant_id
                       and e.secullum_employee_id = f."FuncionarioId"
    where m.tenant_id = %(tenant_id)s
"""

#: Who left at least one punch on the day. Ids only — no name, no unit, nothing
#: the caller has not already been authorised to see.
PUNCHED_EMPLOYEES_SQL = f"""
    select distinct e.id as employee_id
    {_BRIDGE}
      and m.data = %(dia)s
      and m.hora is not null
      and not m.desconsiderada
"""

#: The columns of one person's days, punch or not. The empty ones stay in: a
#: `Memoria` with no `hora` is the source saying "a punch was expected here and
#: is missing", which is the row a manager most needs to see.
EMPLOYEE_PUNCHES_SQL = f"""
    select m.data           as reference_date,
           m.tipo_coluna    as column_type,
           m.indice_coluna  as column_index,
           m.hora           as punched_at,
           m.status_rotulo  as status_label,
           m."Memoria"      as expected_time,
           m.desconsiderada as disregarded
    {_BRIDGE}
      and e.id = %(employee_id)s
      and m.data between %(de)s and %(ate)s
    order by m.data desc, m.indice_coluna, m.tipo_coluna
"""

#: When the punches were last read, and whether they can be read at all. It runs
#: **before** the two statements above, and it is what allows them not to run.
#:
#: `read_at` is the instant every count derived from `app.batida_marcacao` is a
#: statement about — not now. It travels with the count instead of being looked
#: up separately, because two reads of two tables would let a screen show a
#: number from one reading beside the timestamp of the next.
#:
#: `mirror_present` is the part that is easy to miss. No migration in this
#: repository creates `secullum."Funcionario"`: migration 03 hardens whatever
#: mirror tables it finds, and finding none is a valid outcome. The development
#: database has `secullum` with zero tables, and so does any project built from
#: these migrations alone. A statement that names a relation which does not
#: exist fails at parse time — no `case`, no `coalesce` and no guard inside the
#: SQL can save it — so the caller asks first and skips.
#:
#: When the mirror is absent there is no reading, and the answer must say so
#: rather than report two zeros with a timestamp beside them: "nobody punched"
#: and "punches cannot be read here" are the same picture and opposite facts.
PUNCH_READING_SQL = """
    select max(s.finished_at) filter (
             where s.entity = 'Batida' and s.status = 'completed'
           ) as read_at,
           to_regclass('secullum."Funcionario"') is not null as mirror_present
    from app.sync_run s
    where s.tenant_id = %(tenant_id)s
"""
