"""Curadoria de rubrica — o código da folha do cliente ganhando categoria contábil.

⛔ A TABELA NÃO É NOVA, E ISSO É O ACHADO DESTA SPRINT
`docs/SPEC-DP.md` §1i pedia `app.payroll_code_map`, "a curadoria que o P3 ia
construir". Ela já existia: `app.payroll_event_map`, migration 30, aplicada em
produção desde 28/08/2026, com a mesma chave `(tenant_id, code)` e o mesmo
`validated_at`. Duas curadorias com a mesma chave classificando a mesma coisa
seriam a regra escrita duas vezes — e a metade que divergisse decidiria como o
dinheiro é somado. Decisão do dono, 07/09/2026: as colunas que faltavam
(`description`, `nature`) foram acrescentadas à que existe.

⛔ LINHA NÃO VALIDADA NÃO ENTRA EM INDICADOR FINANCEIRO
É a metade do gate do S5, e ela mora em `read_curation` — a única função que
entrega categoria para quem soma. Ela devolve **só** o que tem `validated_at`, e
o que a folha usa e ninguém classificou volta em `pending`, **nomeado**. É a
forma que o S3 deu à mesma regra em `app.leave_justification_map`: silêncio não é
neutro. Lá o silêncio dava vale transporte a quem faltou; aqui ele empurraria
valor para uma categoria que ninguém conferiu, e um total plausível é o erro que
ninguém procura.

⚠️ A LEITURA LITERAL DO GATE NÃO É ENUNCIÁVEL HOJE, E ISSO FOI MEDIDO
"Código não validado não aparece em indicador financeiro" pressupõe um indicador
que leia categoria. Não há: `public.vw_payroll_summary` soma `app.payroll_entry`
por `nature`, sem mapa nenhum, e a folha base do painel de DP não vem de
`payroll_entry`. Então o gate foi reenunciado pelo dono (07/09/2026) como
propriedade desta função — o que existe é provado, o que não existe não é
fingido. O dia em que o indicador nascer, ele chama `read_curation` e a regra já
está aqui.

⛔ VALIDADA É `validated_at is not null`, E SÓ
A §1i propunha um booleano `validated` ao lado. Dois jeitos de dizer a mesma
coisa divergem no primeiro `update` que atualiza um e esquece o outro. O banco
ainda exige que validar implique classificar
(`payroll_event_map_validated_has_category`), então "validada sem categoria" não
é estado alcançável — nem por esta rota, nem por SQL direto.

A LISTA VEM DE DUAS FONTES, E AS DUAS FILTRAM POR TENANT
Códigos que a folha usa (`app.payroll_entry`) e códigos que alguém já curou
(`app.payroll_event_map`). A semente cobre os primeiros no dia em que a migration
roda; import posterior traz códigos novos, e eles têm de aparecer para a
contabilidade sem esperar migration. Por isso a leitura une as duas — e por isso
cada lado carrega o próprio `tenant_id = %(tenant_id)s`: o lado não filtrado de
um `union` é uma das três fugas que `bind_tenant` não pega.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from operax.core.tenant import TenantContext, tenant_scope
from operax.rh.repository import audit

#: O que a trilha de auditoria grava como origem da escrita vinda da tela.
_ORIGEM = {"form": "dp_rubricas"}

#: As nove categorias do `check` da migration 30. Aqui elas existem para o
#: `Literal` do schema de entrada recusar antes do banco; quem recusa por último
#: continua sendo o `check`.
CATEGORIES = (
    "base_salary",
    "overtime",
    "vacation",
    "thirteenth",
    "termination",
    "benefit",
    "charge",
    "deduction",
    "other",
)


class PayrollCodeError(RuntimeError):
    """Base das recusas deste módulo."""


class UnknownPayrollCodeError(PayrollCodeError):
    """Curar código que não existe nem na folha nem no mapa.

    Não é preciosismo: a chave é digitada na URL, e um erro de digitação criaria
    uma linha curada para um código que nunca chegará — indistinguível, na tela,
    de uma classificação legítima esperando a folha.
    """


@dataclass(frozen=True, slots=True)
class PayrollCode:
    """Um código do plano de contas do cliente, com o que a curadoria já disse dele.

    `in_payroll` separa "código que a folha usa" de "código que alguém curou e
    a folha não usa (mais)". Sem ele, a lista de pendências incluiria código que
    não pode aparecer em soma nenhuma, e pendência que não trava nada vira
    ruído que se aprende a ignorar.
    """

    code: str
    description: str | None
    nature: str | None
    category: str | None
    validated_at: datetime | None
    in_payroll: bool

    @property
    def validated(self) -> bool:
        return self.validated_at is not None


@dataclass(frozen=True, slots=True)
class Curation:
    """O que a curadoria entrega a quem soma: o que vale, e o que falta.

    `categories` só tem linha validada. `pending` nomeia o que a folha usa e
    ninguém conferiu — nomeia mesmo, com o código, porque "há pendências" não
    diz a ninguém o que fazer a seguir.
    """

    categories: dict[str, str]
    pending: tuple[str, ...]


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
# `distinct on (e.code)` com desempate estável: o mesmo código aparece em várias
# competências, e a descrição que vale é a mais recente. É o mesmo desempate da
# semente da migration — se um dia divergirem, a tela mostra um rótulo e a
# curadoria guarda outro.
_LIST_SQL = """
    with entry as (
        select distinct on (e.code) e.code, e.description, e.nature
        from app.payroll_entry e
        where e.tenant_id = %(tenant_id)s
        order by e.code, e.created_at desc, e.id
    ),
    curated as (
        select m.code, m.description, m.nature, m.category, m.validated_at
        from app.payroll_event_map m
        where m.tenant_id = %(tenant_id)s
    ),
    codes as (
        select code from entry
        union
        select code from curated
    )
    select k.code,
           coalesce(c.description, e.description) as description,
           coalesce(c.nature, e.nature)           as nature,
           c.category,
           c.validated_at,
           (e.code is not null)                   as in_payroll
    from codes k
    left join entry   e on e.code = k.code
    left join curated c on c.code = k.code
    where (%(code)s::text is null or k.code = %(code)s::text)
    order by k.code
"""

_UPSERT_SQL = """
    insert into app.payroll_event_map
        (tenant_id, code, category, validated_by, validated_at)
    values (%(tenant_id)s, %(code)s, %(category)s, %(validated_by)s, %(validated_at)s)
    on conflict (tenant_id, code) do update
       set category     = excluded.category,
           validated_by = excluded.validated_by,
           validated_at = excluded.validated_at
    returning code
"""


def _row_to_code(row: dict[str, Any]) -> PayrollCode:
    return PayrollCode(
        code=row["code"],
        description=row["description"],
        nature=row["nature"],
        category=row["category"],
        validated_at=row["validated_at"],
        in_payroll=row["in_payroll"],
    )


async def list_codes(tenant: TenantContext, *, code: str | None = None) -> list[PayrollCode]:
    """A lista que a contabilidade confere — a folha do cliente e o que já foi curado."""
    async with tenant_scope(tenant) as scope:
        await scope.execute(_LIST_SQL, {"code": code})
        linhas = await scope.fetchall()
    return [_row_to_code(dict(linha)) for linha in linhas]


async def read_curation(tenant: TenantContext) -> Curation:
    """⛔ A porta única para quem soma dinheiro por categoria.

    A separação é feita **aqui**, em Python, e não no `where` da consulta: assim
    a leitura devolve as duas metades e apagar a regra é apagar uma linha que o
    teste vê. Um `where validated_at is not null` na consulta esconderia a
    pendência de quem chama, e "não veio" é indistinguível de "não existe".
    """
    categories: dict[str, str] = {}
    pending: list[str] = []
    for linha in await list_codes(tenant):
        if linha.validated_at is not None and linha.category is not None:
            categories[linha.code] = linha.category
        elif linha.in_payroll:
            # Código curado que a folha não usa não é pendência: ele não tem
            # como aparecer em soma nenhuma.
            pending.append(linha.code)
    return Curation(categories=categories, pending=tuple(pending))


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------
async def set_category(
    tenant: TenantContext, *, code: str, category: str, validated: bool
) -> PayrollCode:
    """Classifica o código e, se for o caso, marca quem conferiu e quando.

    Não há `delete`: reclassificar é trocar a categoria, porque a trilha de quem
    classificou o quê é o que torna a curadoria auditável — regra 6 estendida à
    curadoria, como em `app.leave_justification_map`.
    """
    agora = datetime.now().astimezone() if validated else None
    async with tenant_scope(tenant) as scope:
        await scope.execute(_LIST_SQL, {"code": code})
        atual = await scope.fetchone()
        if atual is None:
            raise UnknownPayrollCodeError(
                f"o código {code} não aparece na folha importada nem na curadoria"
            )
        anterior = _row_to_code(dict(atual))

        await scope.execute(
            _UPSERT_SQL,
            {
                "code": code,
                "category": category,
                "validated_by": tenant.user_id if validated else None,
                "validated_at": agora,
            },
        )
        if await scope.fetchone() is None:
            raise PayrollCodeError(f"a curadoria do código {code} não foi gravada")

        await scope.execute(_LIST_SQL, {"code": code})
        gravado = await scope.fetchone()
        if gravado is None:
            raise PayrollCodeError(f"a curadoria do código {code} não voltou da leitura")
        curado = _row_to_code(dict(gravado))

        await audit(
            scope,
            tenant,
            action="update",
            entity="payroll_event_map",
            entity_id=code,
            antes={"category": anterior.category, "validated": anterior.validated},
            depois={"category": curado.category, "validated": curado.validated},
            origem=_ORIGEM,
        )
    return curado
