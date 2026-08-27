"""O veredito sobre um desvio — quem produz `rejected`.

A migration 23 criou `app.justification.status` com `accepted` e `rejected`, e
disse no próprio cabeçalho o que ficava faltando:

    ⚠️ Não há tela que aceite ou rejeite. `rejected` existe no domínio e não tem
    quem o produza; enquanto isso não existir, "aceita" e "escrita" são a mesma
    coisa na prática.

Este módulo é quem o produz. Sem migration nenhuma: a coluna, a policy de escrita
e o grant existem desde a 05 e a 23 — o que faltava era a porta.

QUEM PODE, A POLICY JÁ RESPONDE, E NÃO É `is_admin`
`justification_write` é `for insert` com check `util.can_see_employee(employee_id)`.
Esse recorte é deliberadamente diferente do da curadoria: lá quem entra é o
administrador do cliente, aqui é quem enxerga a pessoa. O supervisor responde
pelo desvio da unidade dele, que é o desenho inteiro do produto — o alerta vai
para quem pode agir no dia, e quem pode agir é quem pode explicar.

Então a autorização aqui não é regra nova em Python: é ler o evento **como o
usuário** e ver se ele volta. Zero linha é a policy respondendo não, e a resposta
é a mesma para "não existe" e "não é seu" de propósito — distinguir as duas
contaria ao cliente A que um id do cliente B existe.

⛔ INSERT, NUNCA UPDATE — E ISSO É A SEMÂNTICA, NÃO UMA LIMITAÇÃO
A policy só concede `insert`. Um veredito é fato datado com autor: "a Ana aceitou
em 26/08, com este texto". Sobrescrever a linha apagaria quem disse o quê, que é
justamente a única pergunta que esta tabela existe para responder. Mudar de ideia
escreve OUTRA linha, e `fn_pending_justification` pergunta se existe alguma
aceita — então uma rejeição depois de uma aceitação não "desaceita" nada, e é
correto que não desaceite: o desvio já foi explicado uma vez, por alguém, e isso
aconteceu.

POR QUE A GRAVAÇÃO SAI DO `user_scope`
Mesmo motivo que `curadoria.py` e `rh/repository.py` documentam: `app.audit_log`
é escrito por `service_role`, e a linha e a trilha que a descreve precisam
commitar juntas. Autoriza-se antes, como o usuário; grava-se depois, junto da
auditoria.
"""

from __future__ import annotations

#: Lido **como o usuário**: a RLS de `app.deviation_event` é a autorização. O
#: `status = 'active'` recusa justificar o que foi revogado — um desvio que
#: deixou de existir não tem o que explicar, e aceitar a explicação faria a
#: revogação parecer reversível.
EVENT_SQL = """
select d.id,
       d.employee_id,
       d.reference_date,
       d.type,
       e.name as employee_name
from app.deviation_event d
join app.employee e on e.id = d.employee_id
where d.id = %(deviation_event_id)s
  and d.status = 'active'
"""

#: `author_name` sai de `auth.users` aqui dentro, e não do token: `TenantContext`
#: carrega tenant, usuário e papel — nome não, de propósito, porque nada mais no
#: backend precisa dele. Mas uma trilha cujo autor é um uuid é uma trilha que
#: ninguém lê, e a tela individual já mostra `author_name` desde a migration 05.
#: `author_user_id` continua sendo a chave; o nome é a cópia legível do dia em que
#: foi escrito, e é correto que ele NÃO acompanhe uma renomeação posterior.
INSERT_SQL = """
insert into app.justification
  (tenant_id, deviation_event_id, employee_id, reference_date,
   text, status, source, author_user_id, author_name)
select %(tenant_id)s, %(deviation_event_id)s, %(employee_id)s, %(reference_date)s,
       %(text)s, %(status)s, 'operax', u.id,
       coalesce(nullif(btrim(u.raw_user_meta_data->>'name'), ''), u.email)
from auth.users u
where u.id = %(user_id)s
returning id, created_at
"""

AUDIT_SQL = """
    insert into app.audit_log
      (tenant_id, user_id, action, entity, entity_id, antes, depois)
    values
      (%(tenant_id)s, %(user_id)s, 'insert', 'justification',
       %(entity_id)s, null, %(depois)s)
"""
