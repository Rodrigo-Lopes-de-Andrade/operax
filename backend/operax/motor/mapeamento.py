"""Curadoria do mapa origem → unidade.

`cadastro.py` promove o quadro e devolve a **fila de mapeamento pendente**: os
departamentos do Secullum que ninguém ligou a uma unidade, com quanta gente
depende de cada um. Este módulo é o outro lado — o que fecha a fila.

POR QUE ADIVINHAR UNIDADE É PROIBIDO E SUGERIR NÃO É
A promoção nunca chuta: quem não tem mapa é promovido com `unit_id` nulo e
aparece na fila, porque um palpite gravado é indistinguível de um fato lido, e o
relatório sai errado sem ninguém saber. A sugestão daqui é o oposto disso: ela
não é gravada, tem um número ao lado dizendo o quanto é palpite, e só vira dado
quando uma pessoa aperta o botão. `validated_by` e `validated_at` registram quem
apertou.

A SEMELHANÇA É CALCULADA AQUI, E NÃO NO BANCO
`pg_trgm` faria o mesmo com uma extensão a mais e uma migration a mais. O
conjunto é pequeno — departamentos × unidades de um tenant — e a comparação é
uma função pura, que é o que permite testá-la sem banco nenhum.

O QUE A ESCRITA NÃO FAZ
Ela não move quem já tem unidade. É a mesma regra que a promoção aplica com
`coalesce(excluded.unit_id, app.employee.unit_id)`: alocação existente é trabalho
humano, e curar o mapa não desfaz o trabalho de outra pessoa. Quem já está
alocado continua onde está, e a tela diz isso.

⚠️ `secullum_department_id` e `unit_id` chegam do cliente. Nenhum dos dois é
escrito como veio: o `insert` os resolve **por join** contra `app.department` e
`app.unit` do tenant, então um id de outro cliente não insere linha nenhuma em
vez de inserir uma linha errada. A FK de `unit_secullum_map.unit_id` aponta para
`app.unit(id)` sem conferir tenant, e é exatamente essa a brecha que o join fecha.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

#: Abaixo disto a sugestão não é oferecida. Não é o limiar do lote — esse é
#: escolhido por quem cura, na tela — é o ponto em que exibir um palpite passa a
#: atrapalhar mais do que ajudar. Com a medida por palavra abaixo, 50 significa
#: "pelo menos metade das palavras dos dois lados se encontraram".
MIN_CONFIDENCE = 50

#: Duas palavras são a mesma palavra a partir daqui. Alto de propósito: serve
#: para "aeroport" e "aeroporto", não para "aeroporto" e "operacao".
_SAME_WORD = 0.85

PERMISSION_SQL = """
    select util.is_admin(%(tenant_id)s) as admin
"""

#: Um departamento do espelho por linha, com o peso e o mapa atual. Sai por peso
#: porque é assim que se decide o que curar primeiro, e o que já foi validado vai
#: para o fim: ele não é trabalho pendente.
ROWS_SQL = """
    select d.secullum_department_id,
           d.name                     as department,
           d.company_id,
           c.trade_name               as company_name,
           count(e.id) filter (where e.status <> 'desligado')::int as employees,
           count(e.id) filter (
               where e.status <> 'desligado' and e.unit_id is null
           )::int                     as unmapped,
           m.unit_id,
           u.name                     as unit_name,
           m.validated_at
    from app.department d
    join app.company c on c.id = d.company_id
    left join app.employee e
           on e.tenant_id = d.tenant_id and e.department_id = d.id
    left join app.unit_secullum_map m
           on m.tenant_id = d.tenant_id
          and m.secullum_department_id = d.secullum_department_id
    left join app.unit u on u.id = m.unit_id
    where d.secullum_department_id is not null
    group by d.secullum_department_id, d.name, d.company_id, c.trade_name,
             m.unit_id, u.name, m.validated_at
    order by (m.validated_at is not null),
             count(e.id) filter (where e.status <> 'desligado' and e.unit_id is null) desc,
             d.name
"""

UNITS_SQL = """
    select u.id as unit_id, u.code, u.name, u.company_id, c.trade_name as company_name
    from app.unit u
    join app.company c on c.id = u.company_id
    where u.active
    order by c.trade_name, u.name
"""

#: A visão consolidada da curadoria, e o "não validado" sai dela de propósito.
#: Uma pessoa cuja unidade veio de um mapa que ninguém confirmou está alocada e
#: não está curada; somá-la ao total resolvido faria a barra chegar a 100% com
#: metade do trabalho por fazer.
SUMMARY_SQL = """
    select count(*) filter (where e.status <> 'desligado')::int as active,
           count(*) filter (
               where e.status <> 'desligado' and e.unit_id is null
           )::int as without_unit,
           count(*) filter (
               where e.status <> 'desligado'
                 and e.unit_id is not null
                 and m.secullum_department_id is not null
                 and m.validated_at is null
           )::int as provisional
    from app.employee e
    left join app.department d on d.id = e.department_id
    left join app.unit_secullum_map m
           on m.tenant_id = e.tenant_id
          and m.secullum_department_id = d.secullum_department_id
    where e.tenant_id = %(tenant_id)s
"""

#: Os dois ids do cliente entram por join, nunca como valor. Zero linha devolvida
#: significa "um dos dois não é deste tenant", e o endpoint responde isso.
VALIDATE_SQL = """
    insert into app.unit_secullum_map
      (tenant_id, secullum_department_id, unit_id, validated_by, validated_at)
    select d.tenant_id, d.secullum_department_id, u.id, %(user_id)s, now()
    from app.department d
    join app.unit u on u.tenant_id = d.tenant_id and u.id = %(unit_id)s
    where d.tenant_id = %(tenant_id)s
      and d.secullum_department_id = %(secullum_department_id)s
    on conflict (tenant_id, secullum_department_id) do update
       set unit_id      = excluded.unit_id,
           validated_by = excluded.validated_by,
           validated_at = excluded.validated_at
    returning secullum_department_id, unit_id
"""

#: A unidade sai do mapa recém-gravado, e não do corpo do pedido: assim é
#: impossível alocar alguém numa unidade que não passou pela validação acima.
ALLOCATE_SQL = """
    update app.employee e
       set unit_id = m.unit_id, updated_at = now()
      from app.unit_secullum_map m
      join app.department d
        on d.tenant_id = m.tenant_id
       and d.secullum_department_id = m.secullum_department_id
     where m.tenant_id = %(tenant_id)s
       and m.secullum_department_id = %(secullum_department_id)s
       and e.tenant_id = %(tenant_id)s
       and e.department_id = d.id
       and e.unit_id is null
       and e.status <> 'desligado'
    returning e.id
"""

AUDIT_SQL = """
    insert into app.audit_log
      (tenant_id, user_id, action, entity, entity_id, antes, depois)
    values
      (%(tenant_id)s, %(user_id)s, 'update', 'unit_secullum_map',
       %(entity_id)s, %(antes)s, %(depois)s)
"""


@dataclass(frozen=True, slots=True)
class Suggestion:
    """Um palpite com o tamanho do palpite ao lado."""

    unit_id: str
    unit_name: str
    confidence: int


def normalise(text: str) -> str:
    """Minúsculas, sem acento, e sem nada que não seja letra ou número.

    "Estac. AEROPORTO-01" e "Aeroporto 01" são o mesmo lugar escrito por duas
    pessoas diferentes, e é esse o caso que a tela existe para resolver.
    """
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    return " ".join("".join(c if c.isalnum() else " " for c in sem_acento.lower()).split())


def score(left: str, right: str) -> int:
    """Quanto dois nomes se parecem, contado por PALAVRA e não por letra.

    Comparar as duas frases inteiras letra a letra parece a escolha óbvia e
    produz palpites que não existem: "Departamento 4471" e "Aeroporto 01"
    compartilham vogais suficientes para chegar perto de 50%, e um palpite
    errado exibido com meio termômetro é pior do que palpite nenhum — ele vira
    o clique automático de quem está curando quarenta linhas.

    Então cada palavra procura par do outro lado, e o resultado é o coeficiente
    de Dice: `2 x pares / (palavras de um + palavras do outro)`. Duas palavras
    são a mesma quando são iguais ou quase — `_SAME_WORD` cobre o erro de
    digitação e a abreviação curta, e recusa palavras diferentes que por acaso
    se parecem.
    """
    esquerda = normalise(left).split()
    direita = normalise(right).split()
    if not esquerda or not direita:
        return 0

    restantes = list(direita)
    pares = 0
    for palavra in esquerda:
        par = next(
            (
                outra
                for outra in restantes
                if outra == palavra or SequenceMatcher(None, palavra, outra).ratio() >= _SAME_WORD
            ),
            None,
        )
        if par is not None:
            restantes.remove(par)
            pares += 1

    return round(200 * pares / (len(esquerda) + len(direita)))


def suggest(department: str, units: list[dict]) -> Suggestion | None:
    """A unidade cujo nome mais se parece com o do departamento.

    Empate é resolvido pela ordem em que as unidades chegam, que é alfabética por
    empresa e nome — estável, e portanto a mesma sugestão em duas aberturas da
    tela. Uma sugestão que muda sozinha entre um F5 e outro não é sugestão.

    A empresa **não** restringe a busca. Departamento e empresa divergem em
    ~26% dos vínculos da FastPark (regra 5), então filtrar candidatas pela
    empresa do departamento esconderia justamente a unidade certa.
    """
    melhor: Suggestion | None = None
    for unidade in units:
        for candidato in (unidade["name"], unidade["code"]):
            if not candidato:
                continue
            confianca = score(department, candidato)
            if confianca >= MIN_CONFIDENCE and (melhor is None or confianca > melhor.confidence):
                melhor = Suggestion(
                    unit_id=str(unidade["unit_id"]),
                    unit_name=unidade["name"],
                    confidence=confianca,
                )

    return melhor
