"""O gate de S1: a folha base é dado, o reajuste é linha nova, e o tenant é um só.

A PERGUNTA DO FALSO VERDE, E O QUE ELA MUDOU AQUI
"Salário + ajuda de custo + cargo de confiança + periculosidade entram, VR fica
fora" é satisfeito por uma tupla de códigos escrita em Python — e essa tupla é
exatamente o defeito que `benefit_type.composes_base` existe para impedir. Por
isso o teste central não confere o total: ele **vira a coluna** e exige que o
total mude. Um backend com a lista escrita responderia o mesmo número nas duas
leituras, e é assim que ele é reprovado.

POR QUE A FÓRMULA É PURA, E O QUE ISSO CUSTOU AO DESENHO
`compute_base_payroll` recebe linhas e devolve dinheiro. Nada de banco. É o que
permite que as seis exigências do gate sejam exercitadas contra o código que roda
em produção, em vez de contra um dublê que reimplementa SQL em Python — um teste
que confere a soma de um fake não prova soma nenhuma. A contrapartida está
declarada no módulo: a vigência é uma função Python, não um predicado SQL, e por
isso a busca traz o histórico junto.

O QUE O FAKE **NÃO** PROVA, E ONDE ISSO É PROVADO
`FakeDB` modela dois invariantes do banco — o filtro por tenant e o índice único
parcial de faixa aberta — e falha alto quando o código os viola. Ele não é o
banco: quem prova que `benefit_plan_open_band_idx` existe é a migration
`20260906120100_dp_benefit_catalog.sql`, e quem prova que `hr` não lê verba de
ninguém é `scripts/98_teste_isolamento_tenant.sql`, contra Postgres de verdade.
Esta suíte não substitui aquela e não tenta.

⛔ `seniority_bonus` NÃO ESTÁ NA SEMENTE, E CONTINUA FORA
O tipo `salary_rate` deste arquivo é **fixture**, criado dentro do teste. Decisão
do dono (04/09, reconfirmada em 05/09): o mecanismo é exercitado, o tipo não
existe em produção. Ver `docs/SPEC-DP.md` §1d-bis.

POR QUE O QUADRO DE POSTOS TAMBÉM ESTÁ AQUI
O nome do arquivo é do gate, mas S1 entregou dois assuntos e o despacho abriu um
arquivo de teste só. Rota sem teste é pior que arquivo com nome largo.
"""

from __future__ import annotations

import ast
import inspect
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from psycopg import errors

from operax.core.tenant import bind_tenant
from operax.dp import beneficios, postos
from operax.rh import repository as rh_repository
from tests.conftest import TENANT_ID

OUTRO_TENANT = UUID("33333333-3333-4333-8333-000000000003")

ANA = UUID("aaaa0000-0000-4000-8000-000000000001")
BRUNO = UUID("aaaa0000-0000-4000-8000-000000000002")

UNIDADE_VISIVEL = UUID("bbbb0000-0000-4000-8000-000000000001")
UNIDADE_DE_OUTRO_SUPERVISOR = UUID("bbbb0000-0000-4000-8000-000000000002")

POSTO_7703 = UUID("cccc0000-0000-4000-8000-000000000001")
POSTO_DE_FORA = UUID("cccc0000-0000-4000-8000-000000000002")

#: A data em que tudo neste arquivo é lido, salvo quando o teste diz outra.
HOJE = date(2026, 9, 1)
INICIO = date(2026, 1, 1)

#: Os oito códigos da semente. Nenhum deles pode aparecer no módulo que soma.
SEMENTE = (
    "cost_allowance",
    "trust_position",
    "hazard_pay",
    "meal_voucher",
    "food_basket",
    "transport_voucher",
    "health_plan",
    "dental_plan",
)


# ---------------------------------------------------------------------------
# Fixtures sintéticas da folha — as linhas como o `select` as devolve
# ---------------------------------------------------------------------------
def pessoa(
    employee_id: UUID = ANA,
    nome: str = "Ana Ribeiro",
    *,
    hired_on: date | None = None,
    terminated_on: date | None = None,
    status: str = "active",
) -> dict[str, Any]:
    """A linha de `app.employee`. As três últimas colunas só o dublê lê.

    `compute_base_payroll` usa `employee_id` e `name`: quem recorta o vínculo é o
    `where` da consulta, não a soma. É o dublê que precisa das datas, para poder
    responder ao statement em vez de responder sempre a mesma coisa.
    """
    return {
        "employee_id": employee_id,
        "name": nome,
        "hired_on": hired_on,
        "terminated_on": terminated_on,
        "status": status,
    }


def salario(
    valor: str,
    *,
    employee_id: UUID = ANA,
    desde: date = INICIO,
    ate: date | None = None,
) -> dict[str, Any]:
    return {
        "employee_id": employee_id,
        "effective_from": desde,
        "effective_to": ate,
        "salary": Decimal(valor),
    }


def verba(
    code: str,
    *,
    composes_base: bool,
    amount: str | None = None,
    rate: str | None = None,
    quantity: int | None = None,
    calculation: str = beneficios.FIXED_AMOUNT,
    employee_id: UUID = ANA,
    desde: date = INICIO,
    ate: date | None = None,
) -> dict[str, Any]:
    return {
        "employee_id": employee_id,
        "effective_from": desde,
        "effective_to": ate,
        "amount": Decimal(amount) if amount is not None else None,
        "rate": Decimal(rate) if rate is not None else None,
        "quantity": quantity,
        "code": code,
        "name": code.replace("_", " ").title(),
        "composes_base": composes_base,
        "calculation": calculation,
    }


def folha_da_ficha(*, vr_compoe: bool = False) -> list[dict[str, Any]]:
    """A ficha do legado: salário, os três que compõem, e o VR que não compõe."""
    return [
        verba("cost_allowance", amount="300.00", composes_base=True),
        verba("trust_position", amount="500.00", composes_base=True),
        verba("hazard_pay", amount="200.00", composes_base=True),
        verba("meal_voucher", amount="600.00", composes_base=vr_compoe),
    ]


def uma_linha(resultado: beneficios.BasePayroll) -> beneficios.EmployeeBasePayroll:
    assert len(resultado.lines) == 1
    return resultado.lines[0]


# ---------------------------------------------------------------------------
# 1. A folha base — salário mais o que compõe, e nada mais
# ---------------------------------------------------------------------------
def test_folha_base_soma_os_tres_e_deixa_o_vr_de_fora() -> None:
    resultado = beneficios.compute_base_payroll(
        HOJE, [pessoa()], [salario("2000.00")], folha_da_ficha()
    )

    linha = uma_linha(resultado)
    assert linha.salary == Decimal("2000.00")
    assert linha.total == Decimal("3000.00")
    # O VR não entra, e não entra por ausência: ele não vira componente nenhum.
    assert {c.code for c in linha.components} == {
        "cost_allowance",
        "trust_position",
        "hazard_pay",
    }
    assert resultado.total == Decimal("3000.00")


def test_virar_composes_base_do_vr_muda_o_total() -> None:
    """⛔ O CORAÇÃO DO GATE.

    Mesma fixture, um campo diferente: `meal_voucher.composes_base` passa a
    `true`. Um backend com a lista de códigos escrita em Python responde 3000,00
    nas duas leituras — e é exatamente esse backend que esta asserção reprova.
    """
    sem_vr = beneficios.compute_base_payroll(
        HOJE, [pessoa()], [salario("2000.00")], folha_da_ficha(vr_compoe=False)
    )
    com_vr = beneficios.compute_base_payroll(
        HOJE, [pessoa()], [salario("2000.00")], folha_da_ficha(vr_compoe=True)
    )

    assert uma_linha(sem_vr).total == Decimal("3000.00")
    assert uma_linha(com_vr).total == Decimal("3600.00")
    assert uma_linha(com_vr).total != uma_linha(sem_vr).total
    assert "meal_voucher" in {c.code for c in uma_linha(com_vr).components}


def _corpo_executavel(modulo: object) -> str:
    """O módulo sem comentários e sem docstrings — só o que roda.

    A varredura sobre o texto cru proibiria o módulo de **mencionar** um código
    de verba num comentário para sempre, e a mensagem acusaria "escrito no
    backend" sobre uma linha que não executa. Comentário some no `ast`;
    docstring vira `pass`. Literal de SQL FICA, e é o que se quer: um código de
    verba dentro de um `where` é exatamente o defeito.
    """
    arvore = ast.parse(inspect.getsource(modulo))
    for no in ast.walk(arvore):
        if isinstance(
            no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ) and ast.get_docstring(no):
            no.body[0] = ast.Pass()
    return ast.unparse(ast.fix_missing_locations(arvore))


def test_nenhum_codigo_da_semente_aparece_no_modulo_que_soma() -> None:
    """A mesma pergunta feita ao texto: se a lista existisse, ela estaria escrita.

    A asserção acima prova o comportamento; esta prova a ausência do mecanismo
    errado, inclusive num caminho que a fixture não exercite.
    """
    corpo = _corpo_executavel(beneficios)
    presentes = [code for code in SEMENTE if code in corpo]
    assert presentes == [], f"código de verba escrito no backend: {presentes}"


def test_a_varredura_ignora_comentario_e_docstring_mas_pega_codigo() -> None:
    """A armadilha, fechada — e a prova de que fechá-la não desarmou a asserção.

    Sem isto, "restringi ao corpo executável" seria afirmação sem evidência: um
    recorte que apagasse tudo passaria igual no teste acima.
    """
    cru = inspect.getsource(beneficios)
    corpo = _corpo_executavel(beneficios)

    #: Duas frases que existem no arquivo e **não** executam: uma de docstring,
    #: uma de comentário. Conferidas no texto cru primeiro — sem isso, o dia em
    #: que elas fossem reescritas este teste passaria a não provar nada.
    so_prosa = ("REAJUSTE É LINHA NOVA", "VOLTA COMO COLUNA")
    for frase in so_prosa:
        assert frase in cru, f"a frase {frase!r} saiu do módulo; o teste ficou vazio"
        assert frase not in corpo, f"o recorte não tirou {frase!r} do corpo executável"

    # E o recorte não apagou tudo: `composes_base` é coluna, está no SQL, executa.
    assert "composes_base" in corpo


def test_verba_fora_da_vigencia_nao_conta() -> None:
    """Ajuda de custo que terminou em agosto não entra na folha de setembro."""
    encerrada = folha_da_ficha()
    encerrada[0] = verba(
        "cost_allowance", amount="300.00", composes_base=True, ate=date(2026, 8, 31)
    )

    resultado = beneficios.compute_base_payroll(HOJE, [pessoa()], [salario("2000.00")], encerrada)

    linha = uma_linha(resultado)
    assert "cost_allowance" not in {c.code for c in linha.components}
    assert linha.total == Decimal("2700.00")


def test_verba_que_ainda_nao_comecou_nao_conta() -> None:
    futura = folha_da_ficha()
    futura[1] = verba(
        "trust_position", amount="500.00", composes_base=True, desde=date(2026, 10, 1)
    )

    resultado = beneficios.compute_base_payroll(HOJE, [pessoa()], [salario("2000.00")], futura)

    assert uma_linha(resultado).total == Decimal("2500.00")


def test_salario_vigente_e_o_da_faixa_aberta() -> None:
    """Duas faixas, uma fechada em agosto: setembro lê a que abriu em setembro."""
    resultado = beneficios.compute_base_payroll(
        HOJE,
        [pessoa()],
        [
            salario("2000.00", desde=INICIO, ate=date(2026, 8, 31)),
            salario("2400.00", desde=date(2026, 9, 1)),
        ],
        [],
    )

    assert uma_linha(resultado).salary == Decimal("2400.00")


def test_faixa_salarial_futura_nao_vale_na_data_lida() -> None:
    """⛔ O item 3 do gate aplicado ao SALÁRIO, que é o maior termo da soma.

    Duas faixas, a segunda começando em outubro: lida em setembro, vale a de
    janeiro. Sem a regra de vigência, um `max(effective_from)` ingênuo pegaria a
    faixa que ainda não começou e pagaria o aumento antes da hora.
    """
    resultado = beneficios.compute_base_payroll(
        HOJE,
        [pessoa()],
        [
            salario("2000.00", desde=INICIO),
            salario("2400.00", desde=date(2026, 10, 1)),
        ],
        [],
    )

    assert uma_linha(resultado).salary == Decimal("2000.00")
    assert uma_linha(resultado).total == Decimal("2000.00")


def test_faixa_salarial_encerrada_antes_da_data_nao_vale() -> None:
    """A outra ponta: faixa fechada em julho não sustenta a folha de setembro.

    A pessoa não vira salário zero — ela sai da folha e entra na contagem, que é
    a diferença entre "custa nada" e "falta cadastro".
    """
    resultado = beneficios.compute_base_payroll(
        HOJE,
        [pessoa()],
        [salario("2000.00", desde=INICIO, ate=date(2026, 7, 31))],
        [],
    )

    assert resultado.lines == ()
    assert resultado.without_salary == 1
    assert resultado.total == Decimal("0")


def test_pessoa_sem_faixa_salarial_vigente_fica_fora_e_e_contada() -> None:
    """Contribuir zero calado é o erro que só aparece na reconciliação com o legado."""
    resultado = beneficios.compute_base_payroll(
        HOJE,
        [pessoa(), pessoa(BRUNO, "Bruno Alves")],
        [salario("2000.00")],
        [],
    )

    assert [linha.employee_id for linha in resultado.lines] == [ANA]
    assert resultado.without_salary == 1
    assert resultado.total == Decimal("2000.00")


# ---------------------------------------------------------------------------
# 2. O mecanismo do triênio — por fixture, nunca por semente
# ---------------------------------------------------------------------------
def trienio(quantidade: int) -> dict[str, Any]:
    """⛔ Tipo sintético. `seniority_bonus` não existe no catálogo de produção."""
    return verba(
        "seniority_bonus",
        composes_base=True,
        calculation=beneficios.SALARY_RATE,
        rate="0.0300",
        quantity=quantidade,
    )


def test_verba_por_taxa_acompanha_o_aumento_de_salario() -> None:
    """Triênio é TAXA, não montante: guardado como `amount` ele congelaria."""
    antes = beneficios.compute_base_payroll(HOJE, [pessoa()], [salario("2000.00")], [trienio(2)])
    depois = beneficios.compute_base_payroll(HOJE, [pessoa()], [salario("3000.00")], [trienio(2)])

    # 2 x 3% x salário — 120,00 sobre 2000, 180,00 sobre 3000.
    assert uma_linha(antes).components[0].amount == Decimal("120.00")
    assert uma_linha(depois).components[0].amount == Decimal("180.00")
    assert uma_linha(antes).total == Decimal("2120.00")
    assert uma_linha(depois).total == Decimal("3180.00")


def test_meio_centavo_vai_para_cima() -> None:
    """A premissa de arredondamento — 1750,00 x 3,31% = 57,925.

    ⛔ O 3,31% NÃO É DECORAÇÃO, E A VERSÃO ANTERIOR DESTE TESTE NÃO PROVAVA NADA
    Com 3,33% dava 58,275, e o dígito anterior é ímpar: `ROUND_HALF_UP` e
    `ROUND_HALF_EVEN` respondem **os dois** 58,28. Como `ROUND_HALF_EVEN` é o
    default do `Decimal`, **apagar o argumento `rounding=` inteiro** passava
    verde — e apagar um argumento que parece ruído é a regressão plausível, bem
    mais do que trocar por `ROUND_DOWN`.

    Com 3,31% o dígito anterior é par e os três se separam: HALF_UP 57,93,
    HALF_EVEN 57,92, DOWN 57,92. Um dígito de diferença na fixture é a diferença
    entre a asserção existir e não existir.
    """
    resultado = beneficios.compute_base_payroll(
        HOJE,
        [pessoa()],
        [salario("1750.00")],
        [
            verba(
                "seniority_bonus",
                composes_base=True,
                calculation=beneficios.SALARY_RATE,
                rate="0.0331",
                quantity=1,
            )
        ],
    )

    linha = uma_linha(resultado)
    assert linha.components[0].amount == Decimal("57.93")
    assert linha.total == Decimal("1807.93")


def test_verba_por_taxa_com_quantity_zero_vale_zero() -> None:
    """Zero triênios é uma resposta; ausência de contagem não é.

    A ficha do legado mostrava `TRIÊNIOS: 0`, e esse caso tem valor definido — a
    parcela existe e soma nada. É o que separa o `0` do `None` no teste seguinte.
    """
    resultado = beneficios.compute_base_payroll(
        HOJE, [pessoa()], [salario("2000.00")], [trienio(0)]
    )

    linha = uma_linha(resultado)
    assert linha.components[0].amount == Decimal("0.00")
    assert linha.total == Decimal("2000.00")


def test_verba_por_taxa_sem_quantity_falha_alto() -> None:
    """⛔ A incoerência que o revisor pegou, fechada pelo lado do rigor.

    `rate` ausente falhava alto e `quantity` ausente virava 1 em silêncio —
    duas respostas para a mesma pergunta, e a silenciosa INVENTA dinheiro numa
    parcela que compõe a base. Agora as duas colunas são exigidas.
    """
    sem_contagem = verba(
        "seniority_bonus",
        composes_base=True,
        calculation=beneficios.SALARY_RATE,
        rate="0.0300",
    )

    with pytest.raises(beneficios.MalformedBenefitError, match="quantity"):
        beneficios.compute_base_payroll(HOJE, [pessoa()], [salario("2000.00")], [sem_contagem])


def test_verba_por_taxa_sem_rate_falha_alto() -> None:
    """Zero calado num tipo que compõe a base corromperia o KPI sem sintoma."""
    quebrada = verba("seniority_bonus", composes_base=True, calculation=beneficios.SALARY_RATE)

    with pytest.raises(beneficios.MalformedBenefitError):
        beneficios.compute_base_payroll(HOJE, [pessoa()], [salario("2000.00")], [quebrada])


def test_verba_de_montante_sem_amount_falha_alto() -> None:
    quebrada = verba("cost_allowance", composes_base=True)

    with pytest.raises(beneficios.MalformedBenefitError):
        beneficios.compute_base_payroll(HOJE, [pessoa()], [salario("2000.00")], [quebrada])


def test_verba_quebrada_que_nao_compoe_a_base_e_ignorada() -> None:
    """A recusa é sobre a base. Verba fora dela não é somada e não é conferida."""
    resultado = beneficios.compute_base_payroll(
        HOJE,
        [pessoa()],
        [salario("2000.00")],
        [verba("meal_voucher", composes_base=False)],
    )

    assert uma_linha(resultado).total == Decimal("2000.00")


# ---------------------------------------------------------------------------
# O banco de mentira — dois invariantes reais, e falha alta quando violados
# ---------------------------------------------------------------------------
#: O predicado que todo `select`/`update` sob `tenant_scope` tem de trazer.
_PREDICADO_TENANT = "tenant_id = %(tenant_id)s"


def _no_mesmo_nivel(trecho: str) -> str:
    """`trecho` com tudo que está dentro de parênteses apagado.

    Serve para perguntar "há um `or` NESTE nível?" sem que um `or` legítimo
    aninhado — `(%(unit_id)s::uuid is null or p.unit_id = ...)`, que o Quadro de
    Postos usa — responda que sim.
    """
    saida: list[str] = []
    profundidade = 0
    for caractere in trecho:
        if caractere == "(":
            profundidade += 1
            saida.append(" ")
        elif caractere == ")":
            profundidade -= 1
            saida.append(" ")
        else:
            saida.append(caractere if profundidade == 0 else " ")
    return "".join(saida)


def _grupo_do_predicado_de_tenant(sql: str) -> str:
    """O grupo de parênteses em que o predicado de tenant vive.

    Sem parênteses ao redor, é o statement inteiro; dentro de `(... or true)`, é
    só o conteúdo desse par. É o recorte em que a pergunta "este predicado é
    conjunto ou alternativa?" tem resposta.
    """
    alvo = sql.index(_PREDICADO_TENANT)

    relativa, inicio = 0, 0
    for i in range(alvo - 1, -1, -1):
        if sql[i] == ")":
            relativa += 1
        elif sql[i] == "(":
            if relativa == 0:
                inicio = i + 1
                break
            relativa -= 1

    relativa, fim = 0, len(sql)
    for i in range(alvo + len(_PREDICADO_TENANT), len(sql)):
        if sql[i] == "(":
            relativa += 1
        elif sql[i] == ")":
            if relativa == 0:
                fim = i
                break
            relativa -= 1

    return sql[inicio:fim]


class FakeCursor:
    """Cursor endereçado por trecho de statement.

    ⚠️ O QUE A ASSERÇÃO ESTRUTURAL PROVA, E O QUE ELA NÃO PROVA
    Sob `tenant_scope` ela roda `bind_tenant` de verdade e exige duas coisas do
    statement: que ele traga `tenant_id = %(tenant_id)s`, e que esse predicado
    seja **conjunto e não alternativa** — `where (tenant_id = %(tenant_id)s or
    true)` é recusado, e é a forma que a `DECISAO-FRONTEIRA-CAMINHO-2.md` §3.1
    nomeia. `bind_tenant` sozinho pega nenhuma das duas: ele confere que o
    placeholder aparece, e uma citação dentro de comentário já o satisfaz.

    ⛔ **Três formas continuam passando aqui, e a lista é exaustiva de propósito:**
    o lado não filtrado de um `join` ou de um `union`; um predicado
    semanticamente frouxo que não use `or` (`tenant_id = coalesce(%(tenant_id)s,
    tenant_id)`); e o predicado fechado no próprio par de parênteses com o `or`
    do lado de fora — `where (tenant_id = %(tenant_id)s) or (1=1)` —, porque o
    grupo recortado passa a ser só o predicado e o `or` fica fora dele.

    A terceira **não** foi coberta de propósito: o erro plausível é escrever
    `a = b or c = d` sem parênteses, e esse é pego. Parentizar o predicado
    sozinho e disjungir por fora não é descuido de quem escreve SQL — é quem
    quer passar pela guarda. Alargar o recorte para pegá-la custaria falsos
    positivos em `or` legítimo, e a fronteira de verdade não é esta.

    Nenhuma inspeção de string pega as três sem virar adivinhação, e quem as
    pega é `scripts/98_teste_isolamento_tenant.sql`, contra Postgres.

    E o `FakeDB` filtrar por `params["tenant_id"]` **não é evidência de nada** —
    é conveniência do dublê, que devolve linhas plausíveis. Quem contradiz uma
    consulta mal escrita é a asserção acima, não o filtro do fake.
    """

    def __init__(self, estado: FakeDB, context: Any, checar_tenant: bool) -> None:
        self._estado = estado
        self._context = context
        self._checar = checar_tenant
        self._resultado: list[dict[str, Any]] = []

    async def execute(self, statement: str, params: Any = None) -> None:
        if self._checar:
            params = bind_tenant(statement, params, self._context)
        sql = " ".join(statement.split())
        if self._checar and sql.startswith(("select", "update")):
            assert _PREDICADO_TENANT in sql, f"consulta sem filtro de tenant: {sql}"
            grupo = _no_mesmo_nivel(_grupo_do_predicado_de_tenant(sql))
            assert " or " not in grupo, (
                f"o filtro de tenant é uma alternativa, não uma condição — "
                f"`or` no mesmo nível do predicado: {sql}"
            )
        self._estado.statements.append((sql, dict(params or {})))
        self._resultado = self._estado.responder(sql, dict(params or {}))

    async def fetchone(self) -> dict[str, Any] | None:
        return self._resultado[0] if self._resultado else None

    async def fetchall(self) -> list[dict[str, Any]]:
        return list(self._resultado)


class FakeScope:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    async def __aenter__(self) -> FakeCursor:
        return self._cursor

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeDB:
    """As tabelas desta sprint, com os dois invariantes que o banco garante."""

    def __init__(self) -> None:
        self.admin = True
        self.compensation = True
        #: As unidades que `util.can_see_unit` responde `true`.
        self.unidades_visiveis: set[UUID] = {UNIDADE_VISIVEL}
        #: ⛔ Quando ligado, o fechamento da faixa vira no-op — é como se o código
        #: tivesse esquecido de fechar. Serve para provar que o índice único
        #: parcial é o que impede a segunda faixa aberta.
        self.pular_fechamento = False

        self.tipos: list[dict[str, Any]] = []
        self.planos: list[dict[str, Any]] = []
        self.tarifas: list[dict[str, Any]] = []
        self.postos: list[dict[str, Any]] = []
        self.unidades: list[dict[str, Any]] = []
        self.colaboradores: list[dict[str, Any]] = []
        self.salarios: list[dict[str, Any]] = []
        self.verbas: list[dict[str, Any]] = []

        self.audit: list[dict[str, Any]] = []
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self._proximo_id = 0

    # -- utilidades ---------------------------------------------------------
    def novo_id(self) -> UUID:
        self._proximo_id += 1
        return UUID(f"dddd0000-0000-4000-8000-{self._proximo_id:012d}")

    def _do_tenant(
        self, linhas: list[dict[str, Any]], params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return [linha for linha in linhas if linha["tenant_id"] == params["tenant_id"]]

    def abertas(self, linhas: list[dict[str, Any]], chave: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            linha
            for linha in linhas
            if linha["effective_to"] is None
            and all(linha[campo] == valor for campo, valor in chave.items())
        ]

    # -- semeadura ----------------------------------------------------------
    def semear_tipo(self, code: str, *, composes_base: bool, tenant_id: UUID = TENANT_ID) -> UUID:
        tipo_id = self.novo_id()
        self.tipos.append(
            {
                "id": tipo_id,
                "tenant_id": tenant_id,
                "code": code,
                "name": code,
                "composes_base": composes_base,
                "calculation": beneficios.FIXED_AMOUNT,
                "domain": "compensation",
                "active": True,
            }
        )
        return tipo_id

    def semear_tarifa(
        self,
        code: str,
        kind: str,
        amount: str,
        *,
        desde: date = INICIO,
        ate: date | None = None,
        tenant_id: UUID = TENANT_ID,
    ) -> UUID:
        tarifa_id = self.novo_id()
        self.tarifas.append(
            {
                "id": tarifa_id,
                "tenant_id": tenant_id,
                "code": code,
                "name": f"Linha {code}",
                "kind": kind,
                "amount": Decimal(amount),
                "effective_from": desde,
                "effective_to": ate,
                "reason": None,
            }
        )
        return tarifa_id

    def semear_plano(
        self,
        code: str,
        amount: str,
        *,
        benefit_type_id: UUID,
        desde: date = INICIO,
        ate: date | None = None,
        tenant_id: UUID = TENANT_ID,
    ) -> UUID:
        plano_id = self.novo_id()
        self.planos.append(
            {
                "id": plano_id,
                "tenant_id": tenant_id,
                "benefit_type_id": benefit_type_id,
                "code": code,
                "provider": "Unimed",
                "name": f"Plano {code}",
                "amount": Decimal(amount),
                "effective_from": desde,
                "effective_to": ate,
                "reason": None,
            }
        )
        return plano_id

    def semear_unidade(self, unit_id: UUID, nome: str, tenant_id: UUID = TENANT_ID) -> None:
        self.unidades.append({"id": unit_id, "tenant_id": tenant_id, "name": nome})

    def semear_posto(
        self,
        post_id: UUID,
        unit_id: UUID,
        code: str,
        *,
        active: bool = True,
        tenant_id: UUID = TENANT_ID,
    ) -> None:
        self.postos.append(
            {
                "id": post_id,
                "tenant_id": tenant_id,
                "unit_id": unit_id,
                "code": code,
                "name": f"Posto {code}",
                "active": active,
                "created_at": datetime(2026, 9, 1, 12, 0),
            }
        )

    # -- o despacho ---------------------------------------------------------
    def responder(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if "util.can_see_domain" in sql and "util.is_admin" in sql:
            return [
                {
                    "admin": self.admin,
                    "pii": True,
                    "compensation": self.compensation,
                    "health": True,
                }
            ]
        if "util.can_see_unit(" in sql:
            return [{"visible": params["unit_id"] in self.unidades_visiveis}]

        if "from app.benefit_type bt" in sql:
            return [dict(linha) for linha in self._do_tenant(self.tipos, params)]
        if "from app.benefit_plan p" in sql:
            return [self._plano(linha) for linha in self._do_tenant(self.planos, params)]
        if "from app.transport_fare f" in sql:
            return [dict(linha) for linha in self._do_tenant(self.tarifas, params)]

        if "update app.benefit_plan" in sql:
            return self._fechar(self.planos, params, {"code": params["code"]})
        if "insert into app.benefit_plan" in sql:
            return self._abrir_plano(params)
        if "update app.transport_fare" in sql:
            return self._fechar(
                self.tarifas, params, {"code": params["code"], "kind": params["kind"]}
            )
        if "insert into app.transport_fare" in sql:
            return self._abrir_tarifa(params)

        if "from app.work_post p" in sql:
            return self._listar_postos(sql, params)
        if "insert into app.work_post" in sql:
            return self._criar_posto(params)
        if "update app.work_post" in sql:
            return self._alterar_posto(params)
        if "from app.unit u" in sql:
            # `_VISIBLE_UNITS_SQL`, sob `user_scope`: a policy `unit_read` é quem
            # filtra, e aqui ela é o conjunto de unidades visíveis.
            return [
                {"id": unidade["id"]}
                for unidade in self.unidades
                if unidade["id"] in self.unidades_visiveis
            ]

        if "from app.employee e" in sql:
            return self._vinculo(sql, params)
        if "from app.employee_compensation c" in sql:
            return [dict(linha) for linha in self._do_tenant(self.salarios, params)]
        if "from app.employee_benefit eb" in sql:
            return [dict(linha) for linha in self._do_tenant(self.verbas, params)]

        if "insert into app.audit_log" in sql:
            self.audit.append(dict(params))
            return []
        raise AssertionError(f"statement inesperado: {sql}")

    def _vinculo(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Quem a consulta traz — e o dublê responde ao que ELA diz.

        Sem este ramo, trocar o recorte datado de volta por `status <>
        'desligado'` não teria sintoma: o fake filtraria por data de qualquer
        jeito e o teste seguiria verde sobre o defeito.
        """
        linhas = self._do_tenant(self.colaboradores, params)
        if "terminated_on" in sql:
            on = params["on"]
            return [
                {"employee_id": linha["employee_id"], "name": linha["name"]}
                for linha in linhas
                if (linha["hired_on"] is None or on >= linha["hired_on"])
                and (linha["terminated_on"] is None or on <= linha["terminated_on"])
            ]
        # O recorte por ESTADO ATUAL — o que a leitura datada não pode usar.
        return [
            {"employee_id": linha["employee_id"], "name": linha["name"]}
            for linha in linhas
            if linha["status"] != "desligado"
        ]

    def _plano(self, linha: dict[str, Any]) -> dict[str, Any]:
        tipo = next(t for t in self.tipos if t["id"] == linha["benefit_type_id"])
        return {**linha, "benefit_type_code": tipo["code"]}

    def _fechar(
        self, linhas: list[dict[str, Any]], params: dict[str, Any], chave: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if self.pular_fechamento:
            return []
        for linha in linhas:
            if linha["tenant_id"] != params["tenant_id"]:
                continue
            if linha["effective_to"] is not None:
                continue
            if all(linha[campo] == valor for campo, valor in chave.items()):
                linha["effective_to"] = params["effective_from"] - timedelta(days=1)
        return []

    def _abrir_plano(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        self._recusar_segunda_faixa_aberta(
            self.planos, params, {"code": params["code"]}, "benefit_plan_open_band_idx"
        )
        linha = {
            "id": self.novo_id(),
            "tenant_id": params["tenant_id"],
            "benefit_type_id": params["benefit_type_id"],
            "code": params["code"],
            "provider": params["provider"],
            "name": params["name"],
            "amount": Decimal(str(params["amount"])),
            "effective_from": params["effective_from"],
            "effective_to": None,
            "reason": params["reason"],
        }
        self.planos.append(linha)
        return [dict(linha)]

    def _abrir_tarifa(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        self._recusar_segunda_faixa_aberta(
            self.tarifas,
            params,
            {"code": params["code"], "kind": params["kind"]},
            "transport_fare_open_band_idx",
        )
        linha = {
            "id": self.novo_id(),
            "tenant_id": params["tenant_id"],
            "code": params["code"],
            "name": params["name"],
            "kind": params["kind"],
            "amount": Decimal(str(params["amount"])),
            "effective_from": params["effective_from"],
            "effective_to": None,
            "reason": params["reason"],
        }
        self.tarifas.append(linha)
        return [dict(linha)]

    def _recusar_segunda_faixa_aberta(
        self,
        linhas: list[dict[str, Any]],
        params: dict[str, Any],
        chave: dict[str, Any],
        indice: str,
    ) -> None:
        """O índice único parcial da migration, modelado.

        `create unique index ... where effective_to is null`: uma identidade tem
        no máximo uma faixa aberta. Sem isso, o preço do mês passaria a depender
        da ordem da leitura.
        """
        do_tenant = [linha for linha in linhas if linha["tenant_id"] == params["tenant_id"]]
        if self.abertas(do_tenant, chave):
            raise errors.UniqueViolation(f'duplicate key value violates unique index "{indice}"')

    def _listar_postos(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        linhas = self._do_tenant(self.postos, params)
        if "p.id = %(post_id)s" in sql:
            linhas = [linha for linha in linhas if linha["id"] == params["post_id"]]
        else:
            linhas = [linha for linha in linhas if linha["unit_id"] in set(params["units"])]
            if params["unit_id"] is not None:
                linhas = [linha for linha in linhas if linha["unit_id"] == params["unit_id"]]
        return [self._posto(linha) for linha in linhas]

    def _posto(self, linha: dict[str, Any]) -> dict[str, Any]:
        unidade = next(u for u in self.unidades if u["id"] == linha["unit_id"])
        return {**linha, "unit_name": unidade["name"]}

    def _criar_posto(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        duplicado = any(
            linha["tenant_id"] == params["tenant_id"]
            and linha["unit_id"] == params["unit_id"]
            and linha["code"] == params["code"]
            for linha in self.postos
        )
        if duplicado:
            raise errors.UniqueViolation(
                "duplicate key value violates unique constraint "
                '"work_post_tenant_id_unit_id_code_key"'
            )
        linha = {
            "id": self.novo_id(),
            "tenant_id": params["tenant_id"],
            "unit_id": params["unit_id"],
            "code": params["code"],
            "name": params["name"],
            "active": True,
            "created_at": datetime(2026, 9, 1, 12, 0),
        }
        self.postos.append(linha)
        return [self._posto(linha)]

    def _alterar_posto(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        for linha in self.postos:
            if linha["id"] != params["post_id"] or linha["tenant_id"] != params["tenant_id"]:
                continue
            if params["name"] is not None:
                linha["name"] = params["name"]
            if params["active"] is not None:
                linha["active"] = params["active"]
            return [self._posto(linha)]
        return []


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    estado = FakeDB()

    def tenant_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursor(estado, context, checar_tenant=True))

    def user_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursor(estado, context, checar_tenant=False))

    monkeypatch.setattr(beneficios, "tenant_scope", tenant_scope)
    monkeypatch.setattr(postos, "tenant_scope", tenant_scope)
    monkeypatch.setattr(postos, "user_scope", user_scope)
    # `check_permissions` mora em `operax/rh/repository.py` e é a mesma pergunta
    # que a rota de RH faz: os eixos vêm do banco, nunca do token.
    monkeypatch.setattr(rh_repository, "user_scope", user_scope)
    return estado


def cabecalho(issue_token: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token()}"}


# ---------------------------------------------------------------------------
# 3. Vigência — reajuste é linha nova, e a anterior guarda o valor que valeu
# ---------------------------------------------------------------------------
def reajustar_tarifa(client: TestClient, issue_token: Any, **overrides: Any) -> Any:
    corpo = {
        "target": "fare",
        "code": "302",
        "kind": "single",
        "effective_from": "2026-09-01",
        "amount": "5.10",
        "reason": "Decreto municipal 2026",
    } | overrides
    return client.post("/dp/beneficios/reajuste", json=corpo, headers=cabecalho(issue_token))


def test_reajuste_abre_vigencia_nova_e_fecha_a_anterior(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    antiga = fake_db.semear_tarifa("302", "single", "4.80")

    resposta = reajustar_tarifa(client, issue_token)

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert Decimal(str(corpo["amount"])) == Decimal("5.10")
    assert Decimal(str(corpo["previous_amount"])) == Decimal("4.80")
    assert corpo["previous_effective_to"] == "2026-08-31"

    faixas = [linha for linha in fake_db.tarifas if linha["code"] == "302"]
    assert len(faixas) == 2
    fechada = next(linha for linha in faixas if linha["id"] == antiga)
    # ⛔ A faixa que saiu MANTÉM o valor que valeu: o ciclo do mês passado foi
    #    apurado com ele, e reescrevê-lo mudaria o passado sem deixar rastro.
    assert fechada["amount"] == Decimal("4.80")
    assert fechada["effective_to"] == date(2026, 8, 31)
    assert len(fake_db.abertas(faixas, {"code": "302", "kind": "single"})) == 1


def test_nenhum_update_toca_o_valor(client: TestClient, issue_token: Any, fake_db: FakeDB) -> None:
    """A varredura: não existe `PUT` no valor porque não existe `update` no valor."""
    fake_db.semear_tarifa("302", "single", "4.80")

    reajustar_tarifa(client, issue_token)

    updates = [sql for sql, _ in fake_db.statements if sql.startswith("update")]
    assert updates, "o reajuste não fechou faixa nenhuma"
    for sql in updates:
        assert "amount" not in sql, f"update mexendo em valor publicado: {sql}"
        assert "set effective_to" in sql


def test_leitura_na_faixa_antiga_devolve_o_valor_antigo(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """A prova de que a vigência serve para alguma coisa: consultar o passado."""
    fake_db.semear_tarifa("302", "single", "4.80")
    reajustar_tarifa(client, issue_token)

    antes = client.get(
        "/dp/beneficios/catalogo", params={"em": "2026-08-15"}, headers=cabecalho(issue_token)
    ).json()
    depois = client.get(
        "/dp/beneficios/catalogo", params={"em": "2026-09-01"}, headers=cabecalho(issue_token)
    ).json()

    assert [Decimal(str(t["amount"])) for t in antes["fares"]] == [Decimal("4.80")]
    assert [Decimal(str(t["amount"])) for t in depois["fares"]] == [Decimal("5.10")]
    assert antes["on"] == "2026-08-15"


def test_sem_o_fechamento_o_indice_recusa_a_segunda_faixa_aberta(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ O invariante do banco, e a prova de que o fechamento é o que o respeita.

    `pular_fechamento` simula o código que esqueceu de fechar a faixa anterior.
    O índice único parcial `transport_fare_open_band_idx` recusa — é ele que
    impede o preço do mês de depender da ordem da leitura.

    A recusa chega ao cliente como **409**, e não como o texto cru do Postgres
    num 500: o pedido está bem formado e nada ficou gravado pela metade. É o
    mesmo cenário de dois reajustes simultâneos da mesma tarifa.
    """
    fake_db.semear_tarifa("302", "single", "4.80")
    fake_db.pular_fechamento = True

    resposta = reajustar_tarifa(client, issue_token)

    assert resposta.status_code == 409
    assert "UniqueViolation" not in resposta.text
    assert "duplicate key" not in resposta.text
    # E o estado continua íntegro: uma faixa aberta, nada auditado.
    assert len(fake_db.abertas(fake_db.tarifas, {"code": "302", "kind": "single"})) == 1
    assert fake_db.tarifas[0]["amount"] == Decimal("4.80")
    assert fake_db.audit == []


def test_vigencia_nova_nao_comeca_antes_da_vigente(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Sobrepor não é corrigir — e a mesma frase que a planilha de RH usa."""
    fake_db.semear_tarifa("302", "single", "4.80", desde=date(2026, 6, 1))

    resposta = reajustar_tarifa(client, issue_token, effective_from="2026-05-01")

    assert resposta.status_code == 422
    assert len(fake_db.tarifas) == 1
    assert fake_db.tarifas[0]["amount"] == Decimal("4.80")


def test_reajuste_sem_faixa_aberta_responde_404(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Reajuste não cria a primeira vigência; ele reajusta uma que existe."""
    resposta = reajustar_tarifa(client, issue_token)

    assert resposta.status_code == 404
    assert fake_db.tarifas == []


def test_reajuste_de_tarifa_nao_mexe_no_outro_kind(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """`round_trip` não é 2x `single`: integração e desconto quebram a conta."""
    fake_db.semear_tarifa("302", "single", "4.80")
    ida_e_volta = fake_db.semear_tarifa("302", "round_trip", "8.60")

    reajustar_tarifa(client, issue_token)

    intacta = next(linha for linha in fake_db.tarifas if linha["id"] == ida_e_volta)
    assert intacta["amount"] == Decimal("8.60")
    assert intacta["effective_to"] is None


def test_reajuste_de_plano_carrega_operadora_e_nome(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Preço muda; operadora e nome do plano são identidade e vêm da faixa que sai."""
    tipo = fake_db.semear_tipo("health_plan", composes_base=False)
    fake_db.semear_plano("unimed-basico", "180.00", benefit_type_id=tipo)

    resposta = client.post(
        "/dp/beneficios/reajuste",
        json={
            "target": "plan",
            "code": "unimed-basico",
            "effective_from": "2026-09-01",
            "amount": "199.90",
        },
        headers=cabecalho(issue_token),
    )

    assert resposta.status_code == 201
    nova = next(linha for linha in fake_db.planos if linha["effective_to"] is None)
    assert nova["provider"] == "Unimed"
    assert nova["name"] == "Plano unimed-basico"
    assert nova["amount"] == Decimal("199.90")


def test_reajuste_e_auditado_com_o_antes_e_o_depois(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_tarifa("302", "single", "4.80")

    reajustar_tarifa(client, issue_token)

    assert len(fake_db.audit) == 1
    linha = fake_db.audit[0]
    assert linha["entity"] == "transport_fare"
    assert linha["antes"].obj["amount"] == "4.80"
    assert linha["depois"].obj["amount"] == "5.10"


def test_reajuste_de_plano_recusa_kind(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    resposta = client.post(
        "/dp/beneficios/reajuste",
        json={
            "target": "plan",
            "code": "unimed-basico",
            "kind": "single",
            "effective_from": "2026-09-01",
            "amount": "199.90",
        },
        headers=cabecalho(issue_token),
    )

    assert resposta.status_code == 422


def test_reajuste_de_tarifa_exige_kind(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    resposta = reajustar_tarifa(client, issue_token, kind=None)

    assert resposta.status_code == 422
    assert fake_db.statements == []


# ---------------------------------------------------------------------------
# 4. Multi-tenant e domínio
# ---------------------------------------------------------------------------
def test_catalogo_de_um_tenant_nao_devolve_linha_do_outro(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    meu = fake_db.semear_tipo("meal_voucher", composes_base=False)
    alheio = fake_db.semear_tipo("meal_voucher", composes_base=True, tenant_id=OUTRO_TENANT)
    fake_db.semear_plano("meu-plano", "180.00", benefit_type_id=meu)
    fake_db.semear_plano("plano-alheio", "999.00", benefit_type_id=alheio, tenant_id=OUTRO_TENANT)
    fake_db.semear_tarifa("302", "single", "4.80")
    fake_db.semear_tarifa("999", "single", "99.90", tenant_id=OUTRO_TENANT)

    corpo = client.get("/dp/beneficios/catalogo", headers=cabecalho(issue_token)).json()

    assert [tipo["composes_base"] for tipo in corpo["types"]] == [False]
    assert [plano["code"] for plano in corpo["plans"]] == ["meu-plano"]
    assert [tarifa["code"] for tarifa in corpo["fares"]] == ["302"]
    assert "999" not in client.get("/dp/beneficios/catalogo", headers=cabecalho(issue_token)).text


def test_catalogo_sem_o_dominio_compensation_recusa(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.compensation = False
    fake_db.semear_tarifa("302", "single", "4.80")

    resposta = client.get("/dp/beneficios/catalogo", headers=cabecalho(issue_token))

    assert resposta.status_code == 403
    assert "302" not in resposta.text


def test_reajuste_com_o_dominio_mas_sem_ser_admin_recusa(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """`accounting` concilia a folha e não redigita preço — o terceiro eixo."""
    fake_db.admin = False
    fake_db.semear_tarifa("302", "single", "4.80")

    resposta = reajustar_tarifa(client, issue_token)

    assert resposta.status_code == 403
    assert fake_db.tarifas[0]["amount"] == Decimal("4.80")
    assert fake_db.tarifas[0]["effective_to"] is None
    assert fake_db.audit == []


def test_sem_token_o_catalogo_nao_chega_ao_banco(client: TestClient, fake_db: FakeDB) -> None:
    resposta = client.get("/dp/beneficios/catalogo")

    assert resposta.status_code == 401
    assert fake_db.statements == []


def contexto() -> Any:
    """O `TenantContext` do token do `conftest`, para as leituras assíncronas."""
    from operax.core.tenant import TenantContext, UserRole
    from tests.conftest import USER_ID

    return TenantContext(tenant_id=TENANT_ID, user_id=USER_ID, role=UserRole.UNIT_SUPERVISOR)


async def test_quem_foi_desligado_depois_continua_na_folha_da_competencia(
    fake_db: FakeDB,
) -> None:
    """⛔ A LEITURA É DATADA, E O VÍNCULO TAMBÉM TEM DE SER.

    Bruno saiu em 31/07. A folha de julho tem de continuar tendo Bruno para
    sempre — recortar por `status` (estado de HOJE) faria o número de uma
    competência fechada ENCOLHER retroativamente, sem sintoma nenhum, e é a
    reconciliação de S3 que reprovaria, longe daqui.
    """
    fake_db.colaboradores.append({"tenant_id": TENANT_ID, **pessoa(hired_on=date(2020, 1, 1))})
    fake_db.colaboradores.append(
        {
            "tenant_id": TENANT_ID,
            **pessoa(
                BRUNO,
                "Bruno Alves",
                hired_on=date(2020, 1, 1),
                terminated_on=date(2026, 7, 31),
                status="desligado",
            ),
        }
    )
    fake_db.salarios.append({"tenant_id": TENANT_ID, **salario("2000.00")})
    fake_db.salarios.append({"tenant_id": TENANT_ID, **salario("1500.00", employee_id=BRUNO)})

    julho = await beneficios.read_base_payroll(contexto(), on=date(2026, 7, 1))
    setembro = await beneficios.read_base_payroll(contexto(), on=HOJE)

    assert {linha.employee_id for linha in julho.lines} == {ANA, BRUNO}
    assert julho.total == Decimal("3500.00")
    # E setembro, depois da saída, não tem mais Bruno.
    assert {linha.employee_id for linha in setembro.lines} == {ANA}
    assert setembro.total == Decimal("2000.00")


async def test_admissao_futura_nao_entra_nem_infla_a_contagem(fake_db: FakeDB) -> None:
    """Quem entra em outubro não pesa na folha de setembro — e não vira pendência.

    A exclusão vem do MESMO recorte de vínculo que tira quem já saiu, e não de
    uma segunda regra dentro da soma: `without_salary` só conta quem estava na
    casa e não tem faixa salarial, que é cadastro incompleto de verdade.
    """
    fake_db.colaboradores.append({"tenant_id": TENANT_ID, **pessoa(hired_on=date(2020, 1, 1))})
    fake_db.colaboradores.append(
        {"tenant_id": TENANT_ID, **pessoa(BRUNO, "Bruno Alves", hired_on=date(2026, 10, 1))}
    )
    fake_db.salarios.append({"tenant_id": TENANT_ID, **salario("2000.00")})

    resultado = await beneficios.read_base_payroll(contexto(), on=HOJE)

    assert {linha.employee_id for linha in resultado.lines} == {ANA}
    assert resultado.without_salary == 0
    assert resultado.total == Decimal("2000.00")


async def test_folha_base_lida_do_banco_soma_o_que_compoe(fake_db: FakeDB) -> None:
    """O caminho assíncrono inteiro: três consultas com filtro de tenant e a soma."""
    fake_db.colaboradores.append({"tenant_id": TENANT_ID, **pessoa()})
    fake_db.colaboradores.append({"tenant_id": OUTRO_TENANT, **pessoa(BRUNO, "Bruno Alves")})
    fake_db.salarios.append({"tenant_id": TENANT_ID, **salario("2000.00")})
    fake_db.salarios.append({"tenant_id": OUTRO_TENANT, **salario("9000.00", employee_id=BRUNO)})
    for linha in folha_da_ficha():
        fake_db.verbas.append({"tenant_id": TENANT_ID, **linha})

    resultado = await beneficios.read_base_payroll(contexto(), on=HOJE)

    assert uma_linha(resultado).total == Decimal("3000.00")
    assert resultado.without_salary == 0


# ---------------------------------------------------------------------------
# 5. Quadro de Postos
# ---------------------------------------------------------------------------
def test_quadro_traz_so_as_unidades_que_o_papel_enxerga(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_unidade(UNIDADE_VISIVEL, "Shopping Norte")
    fake_db.semear_unidade(UNIDADE_DE_OUTRO_SUPERVISOR, "Shopping Sul")
    fake_db.semear_posto(POSTO_7703, UNIDADE_VISIVEL, "7703")
    fake_db.semear_posto(POSTO_DE_FORA, UNIDADE_DE_OUTRO_SUPERVISOR, "8801")

    resposta = client.get("/dp/postos", headers=cabecalho(issue_token))

    assert resposta.status_code == 200
    assert [linha["code"] for linha in resposta.json()["rows"]] == ["7703"]
    assert "8801" not in resposta.text


def test_posto_inativo_continua_na_lista(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Esconder o desativado faz o gestor recriá-lo com outro código."""
    fake_db.semear_unidade(UNIDADE_VISIVEL, "Shopping Norte")
    fake_db.semear_posto(POSTO_7703, UNIDADE_VISIVEL, "7703", active=False)

    corpo = client.get("/dp/postos", headers=cabecalho(issue_token)).json()

    assert [linha["active"] for linha in corpo["rows"]] == [False]


def test_codigo_repetido_na_mesma_unidade_e_recusado(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """A frase da tela de VT: ambíguo, o par (posto, unidade) acha a escala errada."""
    fake_db.semear_unidade(UNIDADE_VISIVEL, "Shopping Norte")
    fake_db.semear_posto(POSTO_7703, UNIDADE_VISIVEL, "7703")

    resposta = client.post(
        "/dp/postos",
        json={"unit_id": str(UNIDADE_VISIVEL), "code": "7703", "name": "Guarita 2"},
        headers=cabecalho(issue_token),
    )

    assert resposta.status_code == 409
    assert len(fake_db.postos) == 1


def test_posto_em_unidade_fora_do_alcance_responde_404(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_unidade(UNIDADE_DE_OUTRO_SUPERVISOR, "Shopping Sul")

    resposta = client.post(
        "/dp/postos",
        json={"unit_id": str(UNIDADE_DE_OUTRO_SUPERVISOR), "code": "8801"},
        headers=cabecalho(issue_token),
    )

    assert resposta.status_code == 404
    assert fake_db.postos == []


def test_criar_posto_sem_ser_admin_recusa(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.admin = False
    fake_db.semear_unidade(UNIDADE_VISIVEL, "Shopping Norte")

    resposta = client.post(
        "/dp/postos",
        json={"unit_id": str(UNIDADE_VISIVEL), "code": "7703"},
        headers=cabecalho(issue_token),
    )

    assert resposta.status_code == 403
    assert fake_db.postos == []
    # A recusa acontece antes de a unidade ser resolvida: quem não pode escrever
    # não descobre pela rota que a unidade existe.
    assert not any("can_see_unit" in sql for sql, _ in fake_db.statements)


def test_posto_sai_de_operacao_desativado_e_auditado(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Não há rota que apague: o histórico de VT do mês passado aponta para ele."""
    fake_db.semear_unidade(UNIDADE_VISIVEL, "Shopping Norte")
    fake_db.semear_posto(POSTO_7703, UNIDADE_VISIVEL, "7703")

    resposta = client.patch(
        f"/dp/postos/{POSTO_7703}", json={"active": False}, headers=cabecalho(issue_token)
    )

    assert resposta.status_code == 200
    assert resposta.json()["active"] is False
    assert fake_db.postos[0]["code"] == "7703"
    assert fake_db.audit[0]["antes"].obj["active"] is True
    assert fake_db.audit[0]["depois"].obj["active"] is False


def test_patch_de_posto_em_unidade_fora_do_alcance_responde_404(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """O `POST` já provava isto; o `PATCH` confere a mesma coisa e nada provava.

    404 e não 403: um 403 aqui confirmaria que o posto existe noutra unidade.
    """
    fake_db.semear_unidade(UNIDADE_DE_OUTRO_SUPERVISOR, "Shopping Sul")
    fake_db.semear_posto(POSTO_DE_FORA, UNIDADE_DE_OUTRO_SUPERVISOR, "8801")

    resposta = client.patch(
        f"/dp/postos/{POSTO_DE_FORA}",
        json={"active": False},
        headers=cabecalho(issue_token),
    )

    assert resposta.status_code == 404
    assert fake_db.postos[0]["active"] is True
    assert fake_db.audit == []


def test_patch_de_posto_de_outro_tenant_responde_404(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """A unidade é visível; o posto é de outro cliente. Quem recusa é o tenant."""
    fake_db.semear_unidade(UNIDADE_VISIVEL, "Shopping Norte")
    fake_db.semear_posto(POSTO_DE_FORA, UNIDADE_VISIVEL, "8801", tenant_id=OUTRO_TENANT)

    resposta = client.patch(
        f"/dp/postos/{POSTO_DE_FORA}",
        json={"name": "Guarita renomeada"},
        headers=cabecalho(issue_token),
    )

    assert resposta.status_code == 404
    assert fake_db.postos[0]["name"] == "Posto 8801"


def test_posto_de_outro_tenant_nao_aparece_na_listagem(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Mesma unidade visível, tenants diferentes: só o filtro de tenant separa."""
    fake_db.semear_unidade(UNIDADE_VISIVEL, "Shopping Norte")
    fake_db.semear_posto(POSTO_7703, UNIDADE_VISIVEL, "7703")
    fake_db.semear_posto(POSTO_DE_FORA, UNIDADE_VISIVEL, "8801", tenant_id=OUTRO_TENANT)

    resposta = client.get("/dp/postos", headers=cabecalho(issue_token))

    assert [linha["code"] for linha in resposta.json()["rows"]] == ["7703"]
    assert "8801" not in resposta.text


def test_patch_de_posto_sem_nada_a_mudar_e_recusado(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    resposta = client.patch(f"/dp/postos/{POSTO_7703}", json={}, headers=cabecalho(issue_token))

    assert resposta.status_code == 422
    assert fake_db.statements == []


def test_patch_de_posto_nao_aceita_codigo_nem_unidade(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Mudar código ou unidade quebraria o histórico do mesmo jeito que apagar."""
    resposta = client.patch(
        f"/dp/postos/{POSTO_7703}",
        json={"code": "9999", "unit_id": str(UNIDADE_VISIVEL)},
        headers=cabecalho(issue_token),
    )

    assert resposta.status_code == 422
