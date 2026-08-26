"""Curadoria da rotação — o SQL da ponte que `app.schedule_rotation_map` guarda.

A fila aqui é o irmão da de `mapeamento.py`, e a diferença entre as duas decide
como cada uma é lida. Aquela sai de `app.department`, que é domínio nosso e tem
policy. Esta sai de `secullum."Horario"`, e `secullum` é revogado de
`authenticated` no nível do SCHEMA desde a migration 01: RLS não é o que a
impede de rodar como o usuário, é a ausência de `usage`.

Então vale a mesma ordem que `marcacao.py` documenta — autoriza primeiro,
enriquece depois. `util.is_admin` é perguntado ao banco como o usuário, e só
então a leitura roda sob `tenant_scope`. Não há alargamento de escopo nisso: a
policy `employee_read` já devolve o tenant inteiro para quem é admin, que é
exatamente quem esta tela deixa entrar.

O QUE A FILA MOSTRA, E O QUE ELA SE RECUSA A CONCLUIR
Cada linha traz os dias em que aquele horário de fato bateu ponto. É o dado de
que o curador precisa para decidir a âncora — e é ele quem decide. O sistema
NÃO propõe a âncora derivada das batidas, e a razão está na migration 25: os
dias em que a pessoa bateu são os dias em que ela trabalhou, então uma escala
derivada dali encaixa sempre. Uma escala que encaixa sempre nunca produz
`no_punches` nem `punch_on_day_off` — o motor passaria a concordar consigo
mesmo, e a concordância pareceria acerto.

Mostrar o que aconteceu é informação. Concluir a escala a partir do que
aconteceu é fechar o circuito.
"""

from __future__ import annotations

PERMISSION_SQL = """
    select util.is_admin(%(tenant_id)s) as admin
"""

#: Um horário do espelho por linha, e só os que não declaram expediente nenhum:
#: onde `HorarioDia` fala, ele é o registro oficial e não há o que curar.
#: Ordenado por quanta gente depende dele, como a fila de unidade.
ROWS_SQL = """
    with escala as (
        select hd.horario_id,
               count(*) filter (where not hd.sem_expediente) as work_days
        from secullum."HorarioDia" hd
        where hd.tenant_id = %(tenant_id)s
        group by 1
    ),
    pessoa as (
        select h."HorarioId" as secullum_schedule_id,
               h."Descricao" as schedule,
               f.id          as mirror_id,
               e.id          as employee_id,
               e.status
        from secullum."Horario" h
        left join escala esc on esc.horario_id = h.id
        join secullum."Funcionario" f
          on f.tenant_id = h.tenant_id and f.horario_id = h.id
        join app.employee e
          on e.tenant_id = f.tenant_id and e.secullum_employee_id = f."FuncionarioId"
        where h.tenant_id = %(tenant_id)s
          and coalesce(esc.work_days, 0) = 0
    ),
    batido as (
        -- Os dias em que o horário inteiro bateu. Todos no mesmo `Horario` giram
        -- em fase — "Par" e "Ímpar" são horários DIFERENTES no Secullum — então a
        -- união entre as pessoas dele é o conjunto de dias trabalhados do ciclo.
        select p.secullum_schedule_id, m.data
        from pessoa p
        join app.batida_marcacao m
          on m.tenant_id = %(tenant_id)s
         and m.funcionario_id = p.mirror_id
         and m.hora is not null
         and not m.desconsiderada
         and m.data >= current_date - %(dias)s::int
        group by 1, 2
    )
    select p.secullum_schedule_id,
           p.schedule,
           count(*) filter (where p.status <> 'desligado')::int as employees,
           r.cycle_length_days,
           r.anchor_date,
           r.expected_entry,
           r.expected_exit,
           r.expected_break_minutes,
           r.workload_minutes,
           r.tolerance_extra_minutes,
           r.tolerance_absence_minutes,
           r.validated_at,
           coalesce(
             (select array_agg(b.data order by b.data)
                from batido b where b.secullum_schedule_id = p.secullum_schedule_id),
             '{}'::date[]
           ) as observed_days
    from pessoa p
    left join app.schedule_rotation_map r
           on r.tenant_id = %(tenant_id)s
          and r.secullum_schedule_id = p.secullum_schedule_id
    group by p.secullum_schedule_id, p.schedule, r.cycle_length_days, r.anchor_date,
             r.expected_entry, r.expected_exit, r.expected_break_minutes,
             r.workload_minutes, r.tolerance_extra_minutes, r.tolerance_absence_minutes,
             r.validated_at
    order by count(*) filter (where p.status <> 'desligado') desc, p.schedule
"""

#: A conta da curadoria, e "provisório" fica de fora do resolvido pelo mesmo
#: motivo do mapa de unidade: uma rotação que ninguém carimbou não é lida pelo
#: motor, então somá-la ao pronto faria a barra fechar sem o trabalho fechar.
SUMMARY_SQL = """
    with escala as (
        select hd.horario_id,
               count(*) filter (where not hd.sem_expediente) as work_days
        from secullum."HorarioDia" hd
        where hd.tenant_id = %(tenant_id)s
        group by 1
    )
    select count(*) filter (where e.status <> 'desligado')::int as on_blank_schedule,
           count(*) filter (
               where e.status <> 'desligado' and r.validated_at is not null
           )::int as validated,
           count(*) filter (
               where e.status <> 'desligado'
                 and r.secullum_schedule_id is not null
                 and r.validated_at is null
           )::int as provisional
    from app.employee e
    join secullum."Funcionario" f
      on f.tenant_id = e.tenant_id and f."FuncionarioId" = e.secullum_employee_id
    join secullum."Horario" h on h.id = f.horario_id
    left join escala esc on esc.horario_id = h.id
    left join app.schedule_rotation_map r
           on r.tenant_id = e.tenant_id and r.secullum_schedule_id = h."HorarioId"
    where e.tenant_id = %(tenant_id)s
      and coalesce(esc.work_days, 0) = 0
"""

#: ⛔ O id do horário entra por JOIN contra o espelho do tenant, nunca como valor.
#:    A PK da tabela é (tenant_id, secullum_schedule_id) e o `secullum_schedule_id`
#:    não tem FK — sem este join, um id colado à mão gravaria uma rotação para um
#:    horário que este cliente não tem. Zero linha devolvida é 422, como na fila
#:    de unidade.
VALIDATE_SQL = """
    insert into app.schedule_rotation_map
      (tenant_id, secullum_schedule_id, cycle_length_days, anchor_date,
       expected_entry, expected_exit, expected_break_minutes, workload_minutes,
       tolerance_extra_minutes, tolerance_absence_minutes, validated_by, validated_at)
    select h.tenant_id, h."HorarioId", %(cycle_length_days)s, %(anchor_date)s,
           %(expected_entry)s, %(expected_exit)s, %(expected_break_minutes)s,
           %(workload_minutes)s, %(tolerance_extra_minutes)s,
           %(tolerance_absence_minutes)s, %(user_id)s, now()
    from secullum."Horario" h
    where h.tenant_id = %(tenant_id)s
      and h."HorarioId" = %(secullum_schedule_id)s
    on conflict (tenant_id, secullum_schedule_id) do update
       set cycle_length_days         = excluded.cycle_length_days,
           anchor_date               = excluded.anchor_date,
           expected_entry            = excluded.expected_entry,
           expected_exit             = excluded.expected_exit,
           expected_break_minutes    = excluded.expected_break_minutes,
           workload_minutes          = excluded.workload_minutes,
           tolerance_extra_minutes   = excluded.tolerance_extra_minutes,
           tolerance_absence_minutes = excluded.tolerance_absence_minutes,
           validated_by              = excluded.validated_by,
           validated_at              = excluded.validated_at
    returning secullum_schedule_id
"""

#: Quantas pessoas aquele horário destrava. Sai depois da gravação e do espelho,
#: e não do corpo do pedido: é o número que a tela mostra de volta.
AFFECTED_SQL = """
    select count(*)::int as employees
    from app.employee e
    join secullum."Funcionario" f
      on f.tenant_id = e.tenant_id and f."FuncionarioId" = e.secullum_employee_id
    join secullum."Horario" h on h.id = f.horario_id
    where e.tenant_id = %(tenant_id)s
      and h."HorarioId" = %(secullum_schedule_id)s
      and e.status <> 'desligado'
"""

AUDIT_SQL = """
    insert into app.audit_log
      (tenant_id, user_id, action, entity, entity_id, antes, depois)
    values
      (%(tenant_id)s, %(user_id)s, 'update', 'schedule_rotation_map',
       %(entity_id)s, %(antes)s, %(depois)s)
"""
