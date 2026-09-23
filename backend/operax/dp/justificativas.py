"""Curadoria da justificativa de afastamento — a porta que o apurador já nomeava.

⛔ A TABELA ESTÁ PRONTA DESDE 06/09/2026, VAZIA, E NINGUÉM ESCREVIA NELA
`app.leave_justification_map` traduz o `JustificativaNome` do Secullum para a
categoria do domínio, e `operax/dp/ciclo.py` a lê. Quando a string não está lá —
ou está e ninguém validou — a apuração da competência inteira para, nomeando a
string: *"a justificativa «X» não está classificada em
`app.leave_justification_map`; classifique-a antes de apurar"*. Medido em
produção em 23/09/2026: **zero linhas no mapa e nenhuma rota que o escrevesse**.
A mensagem certa apontava para uma porta que não existia. Este módulo é a porta.

⛔ DOIS ATOS, E ELES NÃO SE JUNTAM
`classify` grava `category` (e `notes`) e deixa `validated_at` NULO; `validate` é
o outro ato, e é ele que carimba. O comentário da coluna é explícito — *"nulo =
provisório, e provisório NÃO é usado"* —, e juntar os dois faria a classificação
entrar em cálculo de dinheiro no mesmo clique em que foi escrita.

⛔ E POR ISSO RECLASSIFICAR DERRUBA A VALIDAÇÃO
Trocar `FALTA` de `unjustified_absence` para `vacation` muda quem recebe cesta e
quantos dias de vale transporte, sem que nenhum valor tenha mudado. Se a linha
seguisse validada, a troca entraria na próxima apuração sem ninguém conferir —
o mesmo clique único, escrito de outro jeito. Voltando a provisória, o lado para
o qual o erro cai é o de PARAR a apuração, nunca o de pagar sozinho.

⛔ NUNCA UM `delete` — E A GARANTIA É A AUSÊNCIA DE ROTA, NÃO O GRANT
Mapeamento errado se corrige trocando a `category`: a trilha de quem classificou
o quê é o que torna a curadoria auditável — regra 6 do projeto estendida à
curadoria, como em `app.payroll_event_map`.

⚠️ E a frase "o banco não deixa" precisa de rodapé: `service_role` de fato não
tem `delete` aqui (a migration recusa alto se um dia tiver), **mas o backend não
conecta como `service_role`** — o DSN é o do papel `postgres`, que tem `delete` e
`truncate` nesta tabela (medido na revisão do S6). O grant é cinto; o suspensório
é não existir rota que apague. Vale para a regra 6 inteira, não só para cá.

⚠️ A CANONICALIZAÇÃO É UMA SÓ, E ELA É DO BANCO
A chave é `upper(btrim(...))`, um `check` da tabela — e `btrim` apara **só**
espaço, não tabulação nem NBSP. São TRÊS juízes que precisam concordar: esta
porta, o `group by` da fila e o `check`. Quem canonicaliza aqui é
`ciclo.canonical_justification` — **importada, não copiada**: se esta porta
gravasse `Atested` e o apurador procurasse `ATESTED`, a recusa diria "não
mapeada" sobre uma string que ESTÁ mapeada, que é o pior erro possível — o que
faz a pessoa desconfiar do conserto que ela acabou de fazer. Acento não é
normalizado: `FÉRIAS` e `FERIAS` são duas strings e cada uma se cura sozinha.
E a string truncada da origem (`Atested`, `ATEST M`, `AFASTAD`) não se
"conserta" aqui: ela é a chave que a origem oferece.

⛔ A LEITURA NÃO RODA COMO O USUÁRIO, E NÃO É ESCOLHA
A fila sai de `secullum."FuncionarioAfastamento"`, e `secullum` não tem `usage`
para `authenticated` desde a migration 01; `app.leave_justification_map` tem
`revoke all` dos dois papéis do PostgREST. Um `select` sob `user_scope` morreria
com `permission denied` em vez de ser filtrado. Então a autorização acontece
antes, na rota, perguntando `util.is_admin` ao banco como o usuário — a mesma
ordem que `routers/curadoria.py` documenta para a fila de rotações.

⚠️ O AFASTAMENTO SEM NOME DE JUSTIFICATIVA NÃO É CURÁVEL, E É CONTADO
`ciclo.resolve_absence_days` também para a apuração quando o Secullum manda um
afastamento sem justificativa nenhuma — e essa não tem o que classificar: a
chave vazia é recusada pelo `check` da tabela. Escondê-la deixaria a tela dizer
"tudo curado" enquanto a apuração continuasse recusando, que é o falso verde
desta sprint. Ela sai da lista (ninguém pode curá-la) e volta contada em
`Queue.without_justification`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from operax.core.tenant import TenantContext, TenantScope, tenant_scope
from operax.dp.ciclo import canonical_justification
from operax.rh.repository import audit

#: O que a trilha de auditoria grava como origem da escrita vinda da tela.
_ORIGEM = {"form": "dp_justificativas"}

#: As cinco do `check` da migration `dp_absence_map`, que são as mesmas de
#: `app.leave_period.category` (a migration compara as duas listas e falha alto
#: se divergirem). Aqui elas existem para o `Literal` do schema de entrada
#: recusar antes do banco; quem recusa por último continua sendo o `check`.
CATEGORIES = (
    "vacation",
    "leave_period",
    "leave_of_absence",
    "suspension",
    "unjustified_absence",
)


class JustificationError(RuntimeError):
    """Base das recusas deste módulo."""


class UnknownJustificationError(JustificationError):
    """Curar uma string que não está nos afastamentos nem no mapa.

    A chave é texto livre digitado no Secullum, e o pedido a carrega inteira: um
    erro de digitação criaria uma linha curada para uma justificativa que nunca
    chegará — indistinguível, na tela, de uma classificação legítima.
    """


class UnclassifiedJustificationError(JustificationError):
    """Validar o que ninguém classificou.

    Validar é conferir uma classificação. Sem linha no mapa não há o que
    conferir, e um `insert` aqui teria de inventar a categoria — que é
    exatamente o que a curadoria existe para não fazer.
    """


@dataclass(frozen=True, slots=True)
class Justification:
    """Uma justificativa do espelho, com o que a curadoria já disse dela.

    `in_mirror` separa "o que o Secullum manda" de "o que alguém curou e o
    espelho não traz (mais)". A segunda continua na lista de propósito: sumir
    com ela esconderia curadoria antiga, e quem a fez precisa poder revê-la.
    """

    justification: str
    occurrences: int
    first_leave: date | None
    last_leave: date | None
    category: str | None
    validated_at: datetime | None
    notes: str | None
    in_mirror: bool

    @property
    def validated(self) -> bool:
        return self.validated_at is not None


@dataclass(frozen=True, slots=True)
class Queue:
    """A fila de curadoria: o que dá para curar, e o que trava a apuração.

    `pending` conta **o que o espelho traz e ninguém validou** — classificado ou
    não, porque provisório trava a apuração do mesmo jeito. É o número que diz
    se a competência vai recusar, e existe para que "sem pendência" seja uma
    afirmação e não a ausência de aviso.
    """

    rows: tuple[Justification, ...]
    without_justification: int

    @property
    def pending(self) -> int:
        return sum(1 for row in self.rows if row.in_mirror and not row.validated)


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
# As duas fontes, cada uma com o próprio `tenant_id = %(tenant_id)s`: o lado não
# filtrado de um `union` é uma das três fugas que `bind_tenant` declara não
# pegar.
#
# ⚠️ A chave do agrupamento é `upper(btrim(...))`, a MESMA expressão do `check`
# da tabela — e não uma aproximação dela. `Atested` e `ATESTED` têm de cair na
# mesma linha da fila, senão a tela ofereceria duas para curar e a segunda
# jamais seria encontrada pelo apurador.
#
# A ordem é a do trabalho: o que ninguém tocou primeiro, depois o provisório,
# depois o validado — e, dentro de cada faixa, o que aparece mais vezes na
# frente. Validado não é trabalho pendente.
_LIST_SQL = """
    with mirror as (
        select upper(btrim(coalesce(a."JustificativaNome", ''))) as justification,
               count(*)::int                                    as occurrences,
               min(a."Inicio"::date)                            as first_leave,
               max(a."Fim"::date)                               as last_leave
        from secullum."FuncionarioAfastamento" a
        where a.tenant_id = %(tenant_id)s
        group by upper(btrim(coalesce(a."JustificativaNome", '')))
    ),
    curated as (
        select m.justification, m.category, m.validated_at, m.notes
        from app.leave_justification_map m
        where m.tenant_id = %(tenant_id)s
    ),
    keys as (
        select justification from mirror
        union
        select justification from curated
    )
    select k.justification,
           coalesce(e.occurrences, 0)    as occurrences,
           e.first_leave,
           e.last_leave,
           c.category,
           c.validated_at,
           c.notes,
           (e.justification is not null) as in_mirror
    from keys k
    left join mirror  e on e.justification = k.justification
    left join curated c on c.justification = k.justification
    where (%(justification)s::text is null or k.justification = %(justification)s::text)
    order by (c.validated_at is not null),
             (c.category is not null),
             coalesce(e.occurrences, 0) desc,
             k.justification
"""

# `validated_by`/`validated_at` viram nulo INCLUSIVE no `do update`: é o que faz
# reclassificar derrubar a validação. Ver o cabeçalho.
_CLASSIFY_SQL = """
    insert into app.leave_justification_map
        (tenant_id, justification, category, notes, validated_by, validated_at)
    values (%(tenant_id)s, %(justification)s, %(category)s, %(notes)s, null, null)
    on conflict (tenant_id, justification) do update
       set category     = excluded.category,
           notes        = excluded.notes,
           validated_by = null,
           validated_at = null
    returning justification
"""

# `update`, e não `insert ... on conflict`: validar uma justificativa que
# ninguém classificou teria de inventar a `category`, que é `not null`. Zero
# linha aqui é a recusa nomeada.
#: ⛔ O `and category = %(category)s` não é redundante com a leitura logo acima:
#: ele é o que impede validar a categoria que o validador NÃO leu. Sem ele, duas
#: sessões — uma validando, outra reclassificando — deixam a linha validada com
#: a categoria nova, que ninguém conferiu, e é essa que entra na cesta e no VT.
#: É o clique único da sprint montado por dois administradores em vez de um
#: (medido na revisão do S6). Zero linha aqui é "mudou debaixo de mim".
_VALIDATE_SQL = """
    update app.leave_justification_map
       set validated_by = %(user_id)s,
           validated_at = now()
     where tenant_id = %(tenant_id)s
       and justification = %(justification)s
       and category = %(category)s
    returning justification
"""


def _row_to_justification(row: dict[str, Any]) -> Justification:
    return Justification(
        justification=row["justification"],
        occurrences=row["occurrences"],
        first_leave=row["first_leave"],
        last_leave=row["last_leave"],
        category=row["category"],
        validated_at=row["validated_at"],
        notes=row["notes"],
        in_mirror=row["in_mirror"],
    )


async def _read_one(scope: TenantScope, justification: str) -> Justification | None:
    await scope.execute(_LIST_SQL, {"justification": justification})
    linha = await scope.fetchone()
    return None if linha is None else _row_to_justification(dict(linha))


async def read_queue(tenant: TenantContext) -> Queue:
    """A fila que quem cura precisa ver: o que falta, o que é provisório, o que vale."""
    async with tenant_scope(tenant) as scope:
        await scope.execute(_LIST_SQL, {"justification": None})
        linhas = [dict(linha) for linha in await scope.fetchall()]

    # A separação acontece aqui, e não num `where` da consulta: a chave vazia
    # precisa ser CONTADA e não pode ser oferecida para curar. Escondê-la na
    # consulta faria "não veio" e "não existe" ficarem indistinguíveis.
    # E a vazieza é decidida pela MESMA função das outras duas pontas, não por
    # comparação com "": se a canonicalização mudar de novo, o balde muda junto.
    # Antes, "sem nome" seguia a régua do SQL e "curável" seguia a do Python —
    # e uma linha podia aparecer como trabalho curável que nenhuma rota aceita.
    vazia = {
        linha["justification"]: canonical_justification(linha["justification"]) == ""
        for linha in linhas
    }
    sem_nome = sum(linha["occurrences"] for linha in linhas if vazia[linha["justification"]])
    return Queue(
        rows=tuple(
            _row_to_justification(linha) for linha in linhas if not vazia[linha["justification"]]
        ),
        without_justification=sem_nome,
    )


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------
async def classify(
    tenant: TenantContext, *, justification: str, category: str, notes: str | None = None
) -> Justification:
    """Classifica a justificativa e a deixa **provisória** — validar é o outro ato."""
    chave = canonical_justification(justification)
    if not chave:
        raise UnknownJustificationError(
            "afastamento sem justificativa no Secullum não tem o que classificar; "
            "a correção é na origem, não aqui"
        )

    async with tenant_scope(tenant) as scope:
        anterior = await _read_one(scope, chave)
        if anterior is None:
            raise UnknownJustificationError(
                f"a justificativa «{chave}» não aparece nos afastamentos do Secullum "
                "nem na curadoria deste cliente"
            )

        await scope.execute(
            _CLASSIFY_SQL, {"justification": chave, "category": category, "notes": notes}
        )
        gravado = await _read_one(scope, chave)
        if gravado is None:
            raise JustificationError(f"a curadoria de «{chave}» não voltou da leitura")

        await audit(
            scope,
            tenant,
            action="update",
            entity="leave_justification_map",
            entity_id=chave,
            antes=_trilha(anterior),
            depois=_trilha(gravado),
            origem=_ORIGEM,
        )
    return gravado


async def validate(tenant: TenantContext, *, justification: str) -> Justification:
    """Carimba quem conferiu e quando — e é só isto que libera a apuração."""
    chave = canonical_justification(justification)

    async with tenant_scope(tenant) as scope:
        anterior = await _read_one(scope, chave)
        if anterior is None or anterior.category is None:
            raise UnclassifiedJustificationError(
                f"a justificativa «{chave}» ainda não foi classificada; "
                "validar é conferir uma classificação, e não há o que conferir"
            )

        await scope.execute(
            _VALIDATE_SQL,
            {
                "justification": chave,
                "user_id": tenant.user_id,
                "category": anterior.category,
            },
        )
        if await scope.fetchone() is None:
            raise UnclassifiedJustificationError(
                f"a classificação de «{chave}» mudou enquanto você conferia; "
                "recarregue a fila e confira a categoria nova antes de validar"
            )

        gravado = await _read_one(scope, chave)
        if gravado is None:
            raise JustificationError(f"a curadoria de «{chave}» não voltou da leitura")

        await audit(
            scope,
            tenant,
            action="update",
            entity="leave_justification_map",
            entity_id=chave,
            antes=_trilha(anterior),
            depois=_trilha(gravado),
            origem=_ORIGEM,
        )
    return gravado


def _trilha(linha: Justification) -> dict[str, Any]:
    """O que a trilha guarda dos dois atos: a categoria e se ela vale dinheiro."""
    return {
        "category": linha.category,
        "validated": linha.validated,
        "notes": linha.notes,
    }
