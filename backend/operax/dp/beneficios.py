"""Catálogo de verbas, reajuste por vigência e a folha salarial base.

⛔ A FOLHA BASE É DADO, NÃO CONSTANTE — E É POR ISSO QUE A SOMA MORA AQUI
`salary + sum(componentes) where benefit_type.composes_base`. A lista de códigos
que compõem a base **não existe em lugar nenhum deste arquivo**: quem decide é a
coluna `composes_base`, que o cliente edita na tela. Uma tupla de códigos escrita
em Python passaria no teste "VR fica fora" e quebraria a regra 8 do `PRD-DP.md`
no dia em que o cliente criasse a nona verba — sem sintoma, e com o KPI errado.

⚠️ A VIGÊNCIA É UMA FUNÇÃO PYTHON, E ISSO É ESCOLHA
`in_effect` é a única implementação de "vale nesta data" do módulo. Ela podia ter
virado predicado SQL em cada consulta; escrita nos dois lugares, ela divergiria
na primeira mudança, e a metade que diverge é a que ninguém testa — a suíte de
pytest não abre banco. Com a regra em Python, **todas** as asserções de vigência
do gate de S1 são exercitadas contra o código que roda em produção. O custo é
buscar o histórico junto: por tenant são dezenas de faixas de plano e algumas por
pessoa, e o recorte de tenant continua sendo do banco.

⛔ LEITURA NÃO RODA COMO O USUÁRIO
As quatro tabelas **não concedem nada a `authenticated`** — a etapa DP inteira é
Caminho 2 —, então um `select` sob `user_scope` morreria com `permission denied`
em vez de ser filtrado. As leituras rodam sob `tenant_scope`, com `where
tenant_id = %(tenant_id)s`, e quem autoriza é a rota: domínio `compensation` para
ler, `compensation` + `util.is_admin` para escrever, perguntados ao banco pelas
mesmas funções que as policies chamam (`operax/rh/repository.check_permissions`).

⛔ REAJUSTE É LINHA NOVA — NUNCA `UPDATE` NO VALOR PUBLICADO
`_close_*` só escreve `effective_to`. O valor que valeu continua onde estava,
porque o ciclo de VT do mês passado foi apurado com ele, e reescrevê-lo mudaria
o passado sem deixar rastro. A ordem também é obrigatória: fechar e só então
inserir — `benefit_plan_open_band_idx` e `transport_fare_open_band_idx` recusam
uma segunda faixa aberta, e é essa recusa que impede o preço do mês de depender
da ordem da leitura.

⚠️ CRIAR A PRIMEIRA FAIXA E REAJUSTAR SÃO DUAS PORTAS, E DE PROPÓSITO
`adjust_*` exige uma faixa aberta para reajustar e devolve `OpenBandNotFound`
quando não há; `create_*` cria a primeira e recusa se já houver uma aberta. A
lacuna foi reportada ao fim do S1 e o dono a resolveu em 06/09 abrindo as duas
rotas no S3. Uma porta só, do tipo "cria se não existir, senão reajusta", é pior
que duas: quem digita um código errado no formulário de reajuste criaria um plano
novo em silêncio, e o erro só apareceria no mês em que ninguém fosse cobrado.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from psycopg import errors

from operax.core.tenant import TenantContext, tenant_scope
from operax.rh.repository import audit
from operax.rh.validators import check_new_band

#: O que a trilha de auditoria grava como origem da escrita vinda da tela. Dois
#: valores porque são duas telas: criar a primeira vigência e reajustar a
#: vigente são ações diferentes, e uma trilha que as confunde não responde
#: "quem colocou este preço aqui?".
_ORIGEM = {"form": "dp_beneficios_reajuste"}
_ORIGEM_CRIACAO = {"form": "dp_beneficios_criacao"}

#: Duas casas, como as colunas `numeric(12,2)` e `numeric(14,2)` do banco.
_CENTAVOS = Decimal("0.01")

#: A faixa que sai fecha na véspera da que entra — sem buraco e sem sobreposição.
_UM_DIA = timedelta(days=1)

FIXED_AMOUNT = "fixed_amount"
SALARY_RATE = "salary_rate"


class BenefitError(RuntimeError):
    """Base das recusas deste módulo."""


class OpenBandNotFoundError(BenefitError):
    """Não há vigência aberta para reajustar — e reajuste não cria a primeira."""


class BandOverlapError(BenefitError):
    """Vigência nova não começa antes da vigente. Sobrepor não é corrigir."""


class OpenBandConflictError(BenefitError):
    """O índice único parcial recusou: outra vigência aberta apareceu no caminho.

    Acontece quando dois reajustes da mesma identidade correm ao mesmo tempo — um
    deles fecha e insere, o outro insere sobre a faixa que o primeiro já abriu.
    Não há escrita parcial: a transação inteira volta atrás. O que muda é a
    resposta, que passa a dizer o que houve em vez de estourar um 500 com o texto
    do Postgres — a mesma tradução que `postos.create_post` faz do choque dela.
    """


class BandAlreadyExistsError(BenefitError):
    """Já existe vigência aberta desta identidade. Criar de novo seria reajustar.

    A recusa é do índice único parcial, traduzida: `benefit_plan_open_band_idx` e
    `transport_fare_open_band_idx` garantem uma faixa aberta por identidade, e é
    essa garantia que impede o preço do mês de depender da ordem da leitura.
    """


class UnknownBenefitTypeError(BenefitError):
    """O plano aponta para uma verba que o catálogo do tenant não tem."""


class MalformedBenefitError(BenefitError):
    """Verba que compõe a base sem o valor que a define.

    Falha alto de propósito: uma verba de base que não sabe quanto vale
    contribuiria zero, e zero calado é exatamente o erro que só aparece na
    reconciliação com o legado, meses depois.
    """


# ---------------------------------------------------------------------------
# Vigência — a única implementação
# ---------------------------------------------------------------------------
def in_effect(on: date, effective_from: date, effective_to: date | None) -> bool:
    """Faixa aberta (`effective_to is null`) vale de `effective_from` em diante."""
    return effective_from <= on and (effective_to is None or on <= effective_to)


def _money(valor: Decimal) -> Decimal:
    """Duas casas, meio para cima.

    `ROUND_HALF_UP` e não o `ROUND_HALF_EVEN` que o `Decimal` traz por padrão:
    metade de centavo em folha vai para cima, e é assim que o legado — e todo
    holerite — arredonda. A escolha é exercitada por fixture com terceira casa
    decimal; sem ela, trocar isto por `ROUND_DOWN` não teria sintoma.
    """
    return valor.quantize(_CENTAVOS, rounding=ROUND_HALF_UP)


def _decimal(valor: Any) -> Decimal:
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class BenefitType:
    """Uma verba do catálogo do tenant. `composes_base` é a definição do KPI."""

    id: UUID
    code: str
    name: str
    composes_base: bool
    calculation: str
    domain: str
    active: bool


@dataclass(frozen=True, slots=True)
class BenefitPlanBand:
    """Uma vigência de plano — operadora e preço, do dia tal ao dia tal."""

    id: UUID
    benefit_type_code: str
    code: str
    provider: str
    name: str
    amount: Decimal
    effective_from: date
    effective_to: date | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class TransportFareBand:
    """Uma vigência de tarifa. `kind` faz parte da identidade, não do valor.

    `round_trip` não é sempre 2x `single`: integração e desconto de linha quebram
    a conta, e é por isso que os dois são dado.
    """

    id: UUID
    code: str
    name: str
    kind: str
    amount: Decimal
    effective_from: date
    effective_to: date | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class Catalog:
    """O catálogo como ele valia em `on` — nunca "o catálogo", sempre numa data."""

    on: date
    types: tuple[BenefitType, ...]
    plans: tuple[BenefitPlanBand, ...]
    fares: tuple[TransportFareBand, ...]


_TYPES_SQL = """
    select bt.id, bt.code, bt.name, bt.composes_base, bt.calculation,
           bt.domain::text as domain, bt.active
    from app.benefit_type bt
    where bt.tenant_id = %(tenant_id)s
    order by bt.name
"""

_PLANS_SQL = """
    select p.id, p.code, p.provider, p.name, p.amount,
           p.effective_from, p.effective_to, p.reason,
           bt.code as benefit_type_code
    from app.benefit_plan p
    join app.benefit_type bt on bt.id = p.benefit_type_id
    where p.tenant_id = %(tenant_id)s
    order by p.code, p.effective_from
"""

_FARES_SQL = """
    select f.id, f.code, f.name, f.kind, f.amount,
           f.effective_from, f.effective_to, f.reason
    from app.transport_fare f
    where f.tenant_id = %(tenant_id)s
    order by f.code, f.kind, f.effective_from
"""


def _vigentes(linhas: Sequence[Mapping[str, Any]], on: date) -> list[Mapping[str, Any]]:
    return [
        linha for linha in linhas if in_effect(on, linha["effective_from"], linha["effective_to"])
    ]


def build_catalog(
    on: date,
    types: Sequence[Mapping[str, Any]],
    plans: Sequence[Mapping[str, Any]],
    fares: Sequence[Mapping[str, Any]],
) -> Catalog:
    """A parte pura da leitura: escolher, entre as faixas, as que valiam em `on`."""
    return Catalog(
        on=on,
        types=tuple(
            BenefitType(
                id=linha["id"],
                code=linha["code"],
                name=linha["name"],
                composes_base=linha["composes_base"],
                calculation=linha["calculation"],
                domain=linha["domain"],
                active=linha["active"],
            )
            for linha in types
        ),
        plans=tuple(
            BenefitPlanBand(
                id=linha["id"],
                benefit_type_code=linha["benefit_type_code"],
                code=linha["code"],
                provider=linha["provider"],
                name=linha["name"],
                amount=_decimal(linha["amount"]),
                effective_from=linha["effective_from"],
                effective_to=linha["effective_to"],
                reason=linha["reason"],
            )
            for linha in _vigentes(plans, on)
        ),
        fares=tuple(
            TransportFareBand(
                id=linha["id"],
                code=linha["code"],
                name=linha["name"],
                kind=linha["kind"],
                amount=_decimal(linha["amount"]),
                effective_from=linha["effective_from"],
                effective_to=linha["effective_to"],
                reason=linha["reason"],
            )
            for linha in _vigentes(fares, on)
        ),
    )


async def read_catalog(tenant: TenantContext, *, on: date) -> Catalog:
    """O catálogo do tenant como ele valia em `on`.

    Os tipos vêm inteiros — inclusive os inativos —, porque a tela de catálogo é
    onde o cliente reativa um. As faixas de preço vêm recortadas pela data.
    """
    async with tenant_scope(tenant) as scope:
        await scope.execute(_TYPES_SQL)
        types = [dict(linha) for linha in await scope.fetchall()]

        await scope.execute(_PLANS_SQL)
        plans = [dict(linha) for linha in await scope.fetchall()]

        await scope.execute(_FARES_SQL)
        fares = [dict(linha) for linha in await scope.fetchall()]

    return build_catalog(on, types, plans, fares)


# ---------------------------------------------------------------------------
# Reajuste — fecha a faixa aberta, abre a próxima, nunca edita o valor
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AdjustedBand:
    """A vigência que nasceu do reajuste, e a que ela fechou.

    As duas viajam juntas porque a tela de reajuste tem de confirmar o que mudou:
    "R$ 4,80 até 31/08, R$ 5,10 a partir de 01/09" é a frase que o gestor confere.
    """

    target: str
    id: UUID
    code: str
    kind: str | None
    name: str
    amount: Decimal
    effective_from: date
    reason: str | None
    previous_id: UUID
    previous_amount: Decimal
    previous_effective_to: date


_OPEN_PLAN_SQL = """
    select p.id, p.code, p.benefit_type_id, p.provider, p.name, p.amount, p.effective_from
    from app.benefit_plan p
    where p.tenant_id = %(tenant_id)s and p.code = %(code)s and p.effective_to is null
"""

# ⛔ Só `effective_to`. O `amount` da faixa que sai não é tocado: ele é o preço
#    com que o ciclo do mês passado foi apurado.
_CLOSE_PLAN_SQL = """
    update app.benefit_plan
       set effective_to = (%(effective_from)s::date - 1)
     where tenant_id = %(tenant_id)s and code = %(code)s and effective_to is null
"""

_NEW_PLAN_SQL = """
    insert into app.benefit_plan
      (tenant_id, benefit_type_id, code, provider, name, amount, effective_from, reason)
    values
      (%(tenant_id)s, %(benefit_type_id)s, %(code)s, %(provider)s, %(name)s,
       %(amount)s, %(effective_from)s, %(reason)s)
    returning id, code, name, amount, effective_from, effective_to, reason
"""

_OPEN_FARE_SQL = """
    select f.id, f.code, f.name, f.kind, f.amount, f.effective_from
    from app.transport_fare f
    where f.tenant_id = %(tenant_id)s and f.code = %(code)s and f.kind = %(kind)s
      and f.effective_to is null
"""

_CLOSE_FARE_SQL = """
    update app.transport_fare
       set effective_to = (%(effective_from)s::date - 1)
     where tenant_id = %(tenant_id)s and code = %(code)s and kind = %(kind)s
       and effective_to is null
"""

_NEW_FARE_SQL = """
    insert into app.transport_fare
      (tenant_id, code, name, kind, amount, effective_from, reason)
    values
      (%(tenant_id)s, %(code)s, %(name)s, %(kind)s, %(amount)s, %(effective_from)s, %(reason)s)
    returning id, code, name, kind, amount, effective_from, effective_to, reason
"""


async def _new_band(
    tenant: TenantContext,
    *,
    target: str,
    entity: str,
    open_sql: str,
    close_sql: str,
    insert_sql: str,
    key: dict[str, Any],
    carried: tuple[str, ...],
    effective_from: date,
    amount: Decimal,
    reason: str | None,
) -> AdjustedBand:
    """Fecha a faixa aberta e abre a próxima, na mesma transação da trilha.

    Os campos de `carried` são copiados da faixa que sai — operadora e nome do
    plano são identidade, não preço, e pedi-los de novo no formulário de reajuste
    deixaria o gestor renomear a operadora por engano ao mudar o valor.
    """
    async with tenant_scope(tenant) as scope:
        await scope.execute(open_sql, key)
        aberta = await scope.fetchone()
        if aberta is None:
            raise OpenBandNotFoundError(f"não há vigência aberta de {key['code']} para reajustar")

        # A mesma regra — e a mesma frase — que a planilha de RH usa para faixa
        # salarial: vigência nova começa depois da vigente. Sem ela, o
        # fechamento produziria um período que termina antes de começar, e a
        # mensagem falaria de `check` de data em vez do que a pessoa fez.
        sobreposicao = check_new_band(effective_from, current_from=aberta["effective_from"])
        if sobreposicao:
            raise BandOverlapError(sobreposicao[0].message)

        fechada_em = effective_from - _UM_DIA
        await scope.execute(close_sql, {**key, "effective_from": effective_from})

        try:
            await scope.execute(
                insert_sql,
                {
                    **key,
                    **{coluna: aberta[coluna] for coluna in carried},
                    "effective_from": effective_from,
                    "amount": amount,
                    "reason": reason,
                },
            )
        except errors.UniqueViolation as choque:
            raise OpenBandConflictError(
                f"outra vigência de {key['code']} foi aberta ao mesmo tempo; "
                f"recarregue o catálogo e refaça o reajuste"
            ) from choque
        nova = await scope.fetchone()
        if nova is None:
            raise BenefitError(f"a vigência nova de {key['code']} não foi gravada")

        banda = AdjustedBand(
            target=target,
            id=nova["id"],
            code=nova["code"],
            kind=nova.get("kind"),
            name=nova["name"],
            amount=_decimal(nova["amount"]),
            effective_from=nova["effective_from"],
            reason=nova["reason"],
            previous_id=aberta["id"],
            previous_amount=_decimal(aberta["amount"]),
            previous_effective_to=fechada_em,
        )
        await audit(
            scope,
            tenant,
            action="insert",
            entity=entity,
            entity_id=banda.id,
            antes={
                "id": str(banda.previous_id),
                "code": banda.code,
                "amount": str(banda.previous_amount),
                "effective_to": str(banda.previous_effective_to),
            },
            depois={
                "code": banda.code,
                "kind": banda.kind,
                "amount": str(banda.amount),
                "effective_from": str(banda.effective_from),
                "reason": banda.reason,
            },
            origem=_ORIGEM,
        )
    return banda


async def adjust_plan(
    tenant: TenantContext,
    *,
    code: str,
    effective_from: date,
    amount: Decimal,
    reason: str | None,
) -> AdjustedBand:
    """Reajuste de plano: mesma operadora, mesmo nome, preço novo a partir de uma data."""
    return await _new_band(
        tenant,
        target="plan",
        entity="benefit_plan",
        open_sql=_OPEN_PLAN_SQL,
        close_sql=_CLOSE_PLAN_SQL,
        insert_sql=_NEW_PLAN_SQL,
        key={"code": code},
        carried=("benefit_type_id", "provider", "name"),
        effective_from=effective_from,
        amount=amount,
        reason=reason,
    )


async def adjust_fare(
    tenant: TenantContext,
    *,
    code: str,
    kind: str,
    effective_from: date,
    amount: Decimal,
    reason: str | None,
) -> AdjustedBand:
    """Reajuste de tarifa. `kind` entra na chave: a unitária e a ida-e-volta sobem separadas."""
    return await _new_band(
        tenant,
        target="fare",
        entity="transport_fare",
        open_sql=_OPEN_FARE_SQL,
        close_sql=_CLOSE_FARE_SQL,
        insert_sql=_NEW_FARE_SQL,
        key={"code": code, "kind": kind},
        carried=("name",),
        effective_from=effective_from,
        amount=amount,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Criação — a PRIMEIRA vigência, que reajuste não sabe fazer
# ---------------------------------------------------------------------------
# ⛔ ESTA PORTA É SEPARADA DA DE REAJUSTE, E É DECISÃO DO DONO (06/09/2026)
# Sem ela `app.benefit_plan` e `app.transport_fare` nascem vazias e ficam vazias,
# e o apurador de vale transporte não tem tarifa para ler. Com uma porta só —
# "cria se não existir, senão reajusta" — um código digitado errado no formulário
# de reajuste vira plano novo em silêncio, e o preço antigo continua valendo para
# quem já estava lá.
_TYPE_ID_SQL = """
    select bt.id
    from app.benefit_type bt
    where bt.tenant_id = %(tenant_id)s and bt.code = %(benefit_type_code)s
"""

_CREATE_PLAN_SQL = """
    insert into app.benefit_plan
      (tenant_id, benefit_type_id, code, provider, name, amount, effective_from, reason)
    values
      (%(tenant_id)s, %(benefit_type_id)s, %(code)s, %(provider)s, %(name)s,
       %(amount)s, %(effective_from)s, %(reason)s)
    returning id, code, name, amount, effective_from, effective_to, reason
"""

_CREATE_FARE_SQL = """
    insert into app.transport_fare
      (tenant_id, code, name, kind, amount, effective_from, reason)
    values
      (%(tenant_id)s, %(code)s, %(name)s, %(kind)s, %(amount)s, %(effective_from)s, %(reason)s)
    returning id, code, name, kind, amount, effective_from, effective_to, reason
"""


@dataclass(frozen=True, slots=True)
class NewBand:
    """A primeira vigência de uma identidade. Não há `previous_*`: não havia nada.

    A ausência dos campos de "anterior" é o desenho, e não economia: `AdjustedBand`
    os carrega porque a tela de reajuste confirma "R$ 4,80 até 31/08, R$ 5,10 a
    partir de 01/09". Aqui não houve nada antes, e inventar um anterior faria a
    tela confirmar um reajuste que não aconteceu.
    """

    target: str
    id: UUID
    code: str
    kind: str | None
    name: str
    amount: Decimal
    effective_from: date
    reason: str | None


async def _create_band(
    tenant: TenantContext,
    *,
    target: str,
    entity: str,
    insert_sql: str,
    params: dict[str, Any],
    identidade: str,
) -> NewBand:
    """Insere e grava a trilha na mesma transação.

    ⛔ QUEM RECUSA A SEGUNDA FAIXA ABERTA É O ÍNDICE, NÃO UM `select` ANTES
    Um `select ... where effective_to is null` aqui responderia "não há" e a outra
    transação abriria a dela no meio do caminho. O índice parcial único é a única
    coisa que serializa isso, e o que esta função faz é traduzir a recusa dele —
    a mesma tradução que `postos.create_post` faz do código duplicado.
    """
    async with tenant_scope(tenant) as scope:
        try:
            await scope.execute(insert_sql, params)
        except errors.UniqueViolation as choque:
            raise BandAlreadyExistsError(
                f"já existe vigência aberta de {identidade}; "
                f"use o reajuste para mudar o valor a partir de uma data"
            ) from choque
        linha = await scope.fetchone()
        if linha is None:
            raise BenefitError(f"a vigência de {identidade} não foi gravada")

        banda = NewBand(
            target=target,
            id=linha["id"],
            code=linha["code"],
            kind=linha.get("kind"),
            name=linha["name"],
            amount=_decimal(linha["amount"]),
            effective_from=linha["effective_from"],
            reason=linha["reason"],
        )
        await audit(
            scope,
            tenant,
            action="insert",
            entity=entity,
            entity_id=banda.id,
            antes=None,
            depois={
                "code": banda.code,
                "kind": banda.kind,
                "name": banda.name,
                "amount": str(banda.amount),
                "effective_from": str(banda.effective_from),
                "reason": banda.reason,
            },
            origem=_ORIGEM_CRIACAO,
        )
    return banda


async def create_plan(
    tenant: TenantContext,
    *,
    benefit_type_code: str,
    code: str,
    provider: str,
    name: str,
    effective_from: date,
    amount: Decimal,
    reason: str | None,
) -> NewBand:
    """O primeiro preço de um plano. A verba vem do catálogo, pelo código dela."""
    async with tenant_scope(tenant) as scope:
        await scope.execute(_TYPE_ID_SQL, {"benefit_type_code": benefit_type_code})
        tipo = await scope.fetchone()
    if tipo is None:
        raise UnknownBenefitTypeError(
            f"a verba «{benefit_type_code}» não existe no catálogo deste tenant"
        )

    return await _create_band(
        tenant,
        target="plan",
        entity="benefit_plan",
        insert_sql=_CREATE_PLAN_SQL,
        params={
            "benefit_type_id": tipo["id"],
            "code": code,
            "provider": provider,
            "name": name,
            "amount": amount,
            "effective_from": effective_from,
            "reason": reason,
        },
        identidade=f"do plano {code}",
    )


async def create_fare(
    tenant: TenantContext,
    *,
    code: str,
    name: str,
    kind: str,
    effective_from: date,
    amount: Decimal,
    reason: str | None,
) -> NewBand:
    """A primeira tarifa de uma linha. `kind` faz parte da identidade.

    A unitária e a ida-e-volta são duas chamadas: `round_trip` não é sempre duas
    vezes `single` — integração e desconto de linha quebram a conta —, e deduzir
    uma da outra aqui inventaria o preço que o apurador multiplica.
    """
    return await _create_band(
        tenant,
        target="fare",
        entity="transport_fare",
        insert_sql=_CREATE_FARE_SQL,
        params={
            "code": code,
            "name": name,
            "kind": kind,
            "amount": amount,
            "effective_from": effective_from,
            "reason": reason,
        },
        identidade=f"da tarifa {code} ({kind})",
    )


# ---------------------------------------------------------------------------
# Folha salarial base
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class BaseComponent:
    """Uma parcela que compõe a base, já resolvida em dinheiro."""

    code: str
    name: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class EmployeeBasePayroll:
    """A base de uma pessoa numa data: salário vigente mais o que compõe."""

    employee_id: UUID
    name: str
    salary: Decimal
    components: tuple[BaseComponent, ...]
    total: Decimal


@dataclass(frozen=True, slots=True)
class BasePayroll:
    """A folha base do tenant numa data.

    `without_salary` não é decoração: a linha de reconciliação de S1 é
    `OperaX − legado = 0`, e uma diferença sem esse número vira investigação. Com
    ele, "12 pessoas sem faixa salarial vigente" é diagnóstico na primeira leitura.

    ⚠️ **Admissão futura NÃO infla esta contagem, e não por uma segunda regra.**
    Quem foi admitido depois de `on` não chega até aqui: o recorte do vínculo
    (`_EMPLOYEES_SQL`) já o deixou de fora, pela mesma condição que exclui quem
    já havia sido desligado. Uma exceção extra em `compute_base_payroll` seria a
    regra do vínculo escrita duas vezes — e a segunda cópia é a que diverge.
    Quem sobra aqui é só quem estava na casa em `on` e não tem faixa salarial:
    cadastro incompleto, que é exatamente o que a contagem existe para nomear.
    """

    on: date
    lines: tuple[EmployeeBasePayroll, ...]
    total: Decimal
    without_salary: int


# ⛔ QUEM ESTAVA NA CASA EM `on`, NÃO QUEM ESTÁ HOJE
# `status <> 'desligado'` é estado ATUAL dentro de uma leitura que é datada, e
# a consequência não tem sintoma: ler uma competência fechada depois de alguém
# ser desligado ENCOLHE o número daquele mês, retroativamente. Como a
# reconciliação de S3 roda sobre mês fechado e reprova por divergência de uma
# pessoa, o defeito apareceria lá, longe daqui.
#
# O predicado é o que `operax/motor/jornada.py` já usa para decidir se o dia
# pertence ao vínculo — mesma forma, mesmas duas colunas. Data nula continua
# valendo, também como lá: cadastro sem admissão mapeada não é motivo para
# sumir da folha.
_EMPLOYEES_SQL = """
    select e.id as employee_id, e.name
    from app.employee e
    where e.tenant_id = %(tenant_id)s
      and (e.hired_on is null       or %(on)s::date >= e.hired_on)
      and (e.terminated_on is null  or %(on)s::date <= e.terminated_on)
    order by e.name
"""

_SALARY_SQL = """
    select c.employee_id, c.effective_from, c.effective_to, c.salary
    from app.employee_compensation c
    where c.tenant_id = %(tenant_id)s
    order by c.employee_id, c.effective_from
"""

# ⛔ `composes_base` VOLTA COMO COLUNA, e não como filtro do `where`.
#    Filtrar aqui deixaria a decisão do KPI invisível para o teste, que é
#    justamente onde ela precisa ser exercitada: virar a coluna de um tipo tem de
#    mudar o total, e isso só é demonstrável se a soma enxergar o valor.
_BENEFITS_SQL = """
    select eb.employee_id, eb.effective_from, eb.effective_to,
           eb.amount, eb.rate, eb.quantity,
           bt.code, bt.name, bt.composes_base, bt.calculation
    from app.employee_benefit eb
    join app.benefit_type bt on bt.id = eb.benefit_type_id
    where eb.tenant_id = %(tenant_id)s
      and bt.active
    order by eb.employee_id, eb.effective_from
"""


def _current_salary(bands: Sequence[Mapping[str, Any]], on: date) -> Decimal | None:
    """A faixa vigente mais recente. `None` quando não há faixa valendo em `on`."""
    vigentes = [b for b in bands if in_effect(on, b["effective_from"], b["effective_to"])]
    if not vigentes:
        return None
    return _decimal(max(vigentes, key=lambda b: b["effective_from"])["salary"])


def value_component(row: Mapping[str, Any], salary: Decimal) -> BaseComponent:
    """Quanto esta verba vale, segundo o `calculation` que o catálogo declara.

    ⛔ PÚBLICA DESDE O S4, E POR UM MOTIVO E NÃO POR CONVENIÊNCIA
    O painel precisa somar o VR — que **não** compõe a base e por isso não sai em
    `BasePayroll.lines[].components`. Valorizá-lo lá com uma segunda conta
    (`sum(amount)`, por exemplo) daria zero na verba de taxa e ninguém veria: o
    cartão mostraria um número menor com cara de número. Uma função só valoriza
    verba neste produto, componha ela a base ou não.

    `salary_rate` é o mecanismo do triênio: o valor deriva do salário vigente, e
    por isso acompanha o aumento na mesma leitura. Guardado como montante fixo
    ele congelaria — a pessoa recebe aumento e a verba fica velha em silêncio.
    """
    calculation = row["calculation"]
    if calculation == SALARY_RATE:
        # ⛔ AS DUAS COLUNAS SÃO EXIGIDAS, E PELA MESMA RAZÃO
        # `rate` ausente falhava alto e `quantity` ausente virava 1 em silêncio —
        # duas respostas para a mesma pergunta ("esta verba sabe quanto vale?"),
        # e a silenciosa INVENTA dinheiro numa parcela que compõe a base.
        # Consequência declarada: verba de taxa que é percentual puro
        # (periculosidade a 30%, por exemplo) grava `quantity = 1` explícito. O
        # dia em que o default for do banco, ele vira `default 1` na coluna e
        # esta exigência cai junto — mas o default nunca é do Python.
        if row["rate"] is None or row["quantity"] is None:
            faltando = "rate" if row["rate"] is None else "quantity"
            raise MalformedBenefitError(
                f"a verba {row['code']} é {SALARY_RATE} e não tem `{faltando}`; "
                f"ela compõe a folha base e não sabe quanto vale"
            )
        valor = _decimal(row["rate"]) * int(row["quantity"]) * salary
    elif calculation == FIXED_AMOUNT:
        if row["amount"] is None:
            raise MalformedBenefitError(
                f"a verba {row['code']} é {FIXED_AMOUNT} e não tem `amount`; "
                f"ela compõe a folha base e não sabe quanto vale"
            )
        valor = _decimal(row["amount"])
    else:
        raise MalformedBenefitError(
            f"a verba {row['code']} tem calculation '{calculation}', que esta soma não conhece"
        )
    return BaseComponent(code=row["code"], name=row["name"], amount=_money(valor))


def compute_base_payroll(
    on: date,
    employees: Sequence[Mapping[str, Any]],
    salary_bands: Sequence[Mapping[str, Any]],
    benefits: Sequence[Mapping[str, Any]],
) -> BasePayroll:
    """A folha base: salário vigente mais toda verba vigente que `composes_base`.

    Pura de propósito. A regra que define o KPI do cliente é exercitada por
    fixture, sem banco — é o que permite provar, no mesmo teste, que virar
    `composes_base` de um tipo muda o total.
    """
    por_pessoa: dict[UUID, list[Mapping[str, Any]]] = defaultdict(list)
    for band in salary_bands:
        por_pessoa[band["employee_id"]].append(band)

    verbas: dict[UUID, list[Mapping[str, Any]]] = defaultdict(list)
    for verba in benefits:
        verbas[verba["employee_id"]].append(verba)

    lines: list[EmployeeBasePayroll] = []
    sem_salario = 0
    for employee in employees:
        employee_id = employee["employee_id"]
        salary = _current_salary(por_pessoa[employee_id], on)
        if salary is None:
            sem_salario += 1
            continue

        componentes = tuple(
            value_component(verba, salary)
            for verba in verbas[employee_id]
            if verba["composes_base"]
            and in_effect(on, verba["effective_from"], verba["effective_to"])
        )
        lines.append(
            EmployeeBasePayroll(
                employee_id=employee_id,
                name=employee["name"],
                salary=_money(salary),
                components=componentes,
                total=_money(salary) + sum((c.amount for c in componentes), start=Decimal("0")),
            )
        )

    return BasePayroll(
        on=on,
        lines=tuple(lines),
        total=sum((line.total for line in lines), start=Decimal("0")),
        without_salary=sem_salario,
    )


@dataclass(frozen=True, slots=True)
class PayrollInputs:
    """As duas leituras de dinheiro que alimentam a folha base.

    ⛔ EXISTE PARA QUE HAJA UM LEITOR SÓ, e não por gosto de estrutura. O painel
    do S4 monta a mesma soma sobre uma população diferente (quem está ativo hoje,
    e não quem tinha vínculo em `on`), então ele não pode reusar
    `read_base_payroll` inteiro — mas se ele reescrevesse estes dois `select`, o
    dia em que um deles ganhasse um filtro o outro ficaria para trás, e o KPI de
    custo passaria a discordar da folha base sem sintoma nenhum.
    """

    salary_bands: list[dict[str, Any]]
    benefits: list[dict[str, Any]]


async def read_payroll_inputs(tenant: TenantContext) -> PayrollInputs:
    """Faixas salariais e verbas do tenant — o histórico inteiro, sem recorte de data.

    A vigência é decidida em Python (`in_effect`), então a consulta traz o
    histórico: é o custo declarado no cabeçalho deste módulo.
    """
    async with tenant_scope(tenant) as scope:
        await scope.execute(_SALARY_SQL)
        salary_bands = [dict(linha) for linha in await scope.fetchall()]

        await scope.execute(_BENEFITS_SQL)
        benefits = [dict(linha) for linha in await scope.fetchall()]

    return PayrollInputs(salary_bands=salary_bands, benefits=benefits)


async def read_base_payroll(tenant: TenantContext, *, on: date) -> BasePayroll:
    """A folha base do tenant em `on`.

    ⛔ Domínio `compensation`. Não há rota para isto em S1 — quem a criar
    revalida o domínio antes de chamar, como `GET /dp/beneficios/catalogo` faz.
    """
    async with tenant_scope(tenant) as scope:
        await scope.execute(_EMPLOYEES_SQL, {"on": on})
        employees = [dict(linha) for linha in await scope.fetchall()]

    entradas = await read_payroll_inputs(tenant)
    return compute_base_payroll(on, employees, entradas.salary_bands, entradas.benefits)
