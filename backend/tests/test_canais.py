"""A tela de Conexões: o que ela nomeia, o que ela não recalcula e o que não vaza.

O gate desta sprint é uma frase: *"3 regras bloqueadas: template
`deviation_individual` está `pending` na Meta"*. Hoje `fn_channel_readiness`
sabe o "3" e não sabe o resto, e é o resto que faz alguém consertar. Então o
teste central é que a resposta traga **qual** regra e **qual** template — e que o
"3" da função e o tamanho da lista sejam o mesmo número.

Desde o C3 a tela tem duas linhas (`whatsapp` e `telegram`); esta suíte é a da
linha de WhatsApp, e a do Telegram é `tests/test_canais_telegram.py`.

⚠️ O QUE ESTA SUÍTE NÃO PODE PROVAR, E POR ISSO PROVA DE OUTRO JEITO
Nada aqui toca banco. Que uma regra **inativa** fique de fora da lista é
propriedade de um `where`, e um stub responde o que lhe mandarem responder. O que
está ao alcance é a deriva: as cláusulas desta rota são conferidas, como
conjuntos de tokens, **contra a CTE `blocked` da última migration que define
`fn_channel_readiness`** — que é quem produz a contagem. Divergência entre os
dois é exatamente o defeito que o gate teme, e é ela que o teste prende.

Quem executa `_BLOCKED_SQL` e `_READINESS_SQL` contra Postgres de verdade — como
`authenticated`, com uma regra ligada e uma desligada, e depois como `postgres`
para provar o recorte de `tenant_id` sem RLS — é `scripts/97_teste_canais.py`,
no `make db-test`. Esta suíte não substitui aquele.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from operax.alertas.capacidades import UnknownProviderError
from server.routers import canais

#: O tenant que `conftest.client` resolve para todo token.
TENANT_ID = "22222222-2222-4222-8222-222222222222"


def readiness(**overrides: Any) -> dict[str, Any]:
    """A linha de WhatsApp da função, menos o `tenant_id` e o `channel`."""
    return {
        "provider": "meta_cloud",
        "official": True,
        "templates_total": 4,
        "templates_approved": 3,
        "rules_blocked": 1,
        "health_status": None,
        "health_changed_at": None,
        "ready": False,
    } | overrides


def blocked_row(**overrides: Any) -> dict[str, Any]:
    return {
        "rule_name": "Desvio individual — Shopping Norte",
        "template_code": "deviation_individual",
        "meta_status": "pending",
    } | overrides


class StubScope:
    """Responde pelo assunto da instrução e guarda o que foi perguntado."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self._answers = answers
        self.statements: list[str] = []
        self.params: list[Any] = []
        self._current: Any = None

    async def execute(self, statement: str, params: Any = None) -> None:
        self.statements.append(statement)
        self.params.append(params)
        self._current = next(
            (value for marker, value in self._answers.items() if marker in statement), None
        )

    async def fetchone(self) -> dict[str, Any] | None:
        return self._current

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._current or []


class StubScopeContext:
    def __init__(self, scope: StubScope) -> None:
        self._scope = scope

    async def __aenter__(self) -> StubScope:
        return self._scope

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.fixture
def answer(monkeypatch: pytest.MonkeyPatch):
    """Enfileira a linha de WhatsApp da função e a lista, e devolve o espião do
    `user_scope`. O `tenant_scope` (a linha do bot) responde vazio: não há bot."""

    def install(
        linha: dict[str, Any] | None,
        lista: list[dict[str, Any]] | None = None,
    ) -> StubScope:
        scope = StubScope(
            {
                "fn_channel_readiness": [linha] if linha is not None else [],
                "from app.alert_rule": lista or [],
            }
        )
        monkeypatch.setattr(canais, "user_scope", lambda tenant: StubScopeContext(scope))
        monkeypatch.setattr(canais, "tenant_scope", lambda tenant: StubScopeContext(StubScope({})))
        return scope

    return install


def _whatsapp(client: TestClient, cabecalho: dict[str, str]) -> dict[str, Any]:
    resposta = client.get("/canais/conexoes", headers=cabecalho)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["whatsapp"]


@pytest.fixture
def cabecalho(issue_token: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token()}"}


# ---------------------------------------------------------------------------
# O cliente que ainda não tem canal — que é o estado da produção hoje
# ---------------------------------------------------------------------------
def test_cliente_sem_provedor_ativo_nao_e_erro(
    client: TestClient, cabecalho: dict[str, str], answer: Any
) -> None:
    """A tela existe para dizer "não há por onde entregar". Um 404 diria que a
    tela é que não existe."""
    answer(None)

    resposta = client.get("/canais/conexoes", headers=cabecalho)

    assert resposta.status_code == 200
    assert resposta.json() == {"whatsapp": None, "telegram": None}


def test_sem_provedor_a_lista_nem_e_consultada(
    client: TestClient, cabecalho: dict[str, str], answer: Any
) -> None:
    scope = answer(None)

    client.get("/canais/conexoes", headers=cabecalho)

    assert len(scope.statements) == 1


# ---------------------------------------------------------------------------
# O gate: qual regra, qual template
# ---------------------------------------------------------------------------
def test_a_lista_nomeia_a_regra_e_o_template_que_a_travam(
    client: TestClient, cabecalho: dict[str, str], answer: Any
) -> None:
    """⛔ É o gate. Sem estes dois campos a frase da tela não se escreve, e o
    estado continua invisível como está hoje."""
    answer(readiness(rules_blocked=1), [blocked_row()])

    corpo = _whatsapp(client, cabecalho)

    assert corpo["rules_blocked"] == 1
    assert len(corpo["blocked"]) == 1
    assert corpo["blocked"][0] == {
        "rule_name": "Desvio individual — Shopping Norte",
        "template_code": "deviation_individual",
        "meta_status": "pending",
    }


def test_a_contagem_da_funcao_e_o_tamanho_da_lista_sao_o_mesmo_numero(
    client: TestClient, cabecalho: dict[str, str], answer: Any
) -> None:
    """Duas leituras do mesmo fato. Divergirem é a tela afirmando um número que
    a própria lista não sustenta."""
    linhas = [
        blocked_row(rule_name="Atraso — Centro"),
        blocked_row(rule_name="Sem batida — Norte", template_code="no_punches"),
        blocked_row(rule_name="Resumo diário", template_code=None, meta_status=None),
    ]
    answer(readiness(rules_blocked=len(linhas)), linhas)

    corpo = _whatsapp(client, cabecalho)

    assert corpo["rules_blocked"] == len(corpo["blocked"]) == 3


def test_a_regra_sem_template_nenhum_tambem_entra_na_lista(
    client: TestClient, cabecalho: dict[str, str], answer: Any
) -> None:
    """A função a conta (`m.id is null`). Deixá-la de fora aqui quebraria o par
    das duas contagens no caso mais fácil de esquecer."""
    answer(readiness(), [blocked_row(template_code=None, meta_status=None)])

    corpo = _whatsapp(client, cabecalho)

    assert corpo["blocked"][0]["template_code"] is None
    assert corpo["blocked"][0]["meta_status"] is None
    assert corpo["blocked"][0]["rule_name"]


def test_template_aprovado_deixa_a_tela_pronta(
    client: TestClient, cabecalho: dict[str, str], answer: Any
) -> None:
    """O positivo do gate: com a regra ligada e o template aprovado, não há o que
    mostrar e `ready` é verdadeiro."""
    answer(readiness(templates_approved=4, rules_blocked=0, ready=True), [])

    corpo = _whatsapp(client, cabecalho)

    assert corpo["blocked"] == []
    assert corpo["rules_blocked"] == 0
    assert corpo["ready"] is True


# ---------------------------------------------------------------------------
# A lista é a mesma pergunta da função — conferida contra a migration
# ---------------------------------------------------------------------------
#: Literal entre aspas, placeholder do psycopg, `<>`, identificador (com ponto)
#: ou pontuação. O que não é isso (`*`, `::`) não aparece nas cláusulas comparadas.
_TOKEN = re.compile(r"'[^']*'|%\(\w+\)s|<>|[A-Za-z_][\w.]*|[(),=]")

Clause = tuple[str, ...]


def _tokens(sql: str) -> list[str]:
    return [t if t.startswith("'") else t.lower() for t in _TOKEN.findall(sql)]


def _conjuncts(tokens: list[str]) -> set[Clause]:
    """Quebra em `and` de nível zero. Cada cláusula é uma tupla de tokens inteira:
    `not r.active` e `r.active` são cláusulas diferentes, não uma dentro da outra."""
    clauses: set[Clause] = set()
    atual: list[str] = []
    profundidade = 0
    for token in tokens:
        profundidade += (token == "(") - (token == ")")
        if token == "and" and profundidade == 0:
            clauses.add(tuple(atual))
            atual = []
        else:
            atual.append(token)
    clauses.add(tuple(atual))
    return clauses


def _clauses(sql: str) -> tuple[set[Clause], set[Clause]]:
    """(cláusulas do `on` do join com o template, cláusulas do `where`).

    Duas coisas fora das cláusulas também são contrato, e a comparação por
    conjunto não as veria: o join tem de ser `left` — é o que torna alcançável
    o `m.id is null`, o caso mais fácil de esquecer —, e nada depois do `where`
    pode encurtar a lista (`limit`). Um `join` seco ou um `limit 1` deixam as
    cláusulas idênticas e a lista menor que a contagem; o `97` pegaria no
    `make db-test`, mas uma edição só em `canais.py` roda só o `make test`.
    """
    tokens = _tokens(sql)
    join = tokens.index("app.message_template")
    assert tokens[join - 1] == "join", "o template entra por join"
    assert tokens[join - 2] == "left", "o join com o template tem de ser LEFT"
    on = tokens.index("on", join)
    where = tokens.index("where", on)
    fim = next((i for i in range(where, len(tokens)) if tokens[i] in ("group", "order")), None)
    assert "limit" not in tokens[where:], "nada depois do where pode encurtar a lista"
    return _conjuncts(tokens[on + 1 : where]), _conjuncts(tokens[where + 1 : fim])


def test_o_predicado_da_lista_e_o_da_cte_da_funcao(
    last_migration_with: Callable[[str], str],
) -> None:
    """A lista tem de ser a decomposição da contagem, não uma consulta parecida.

    ⛔ É aqui que "regra inativa não entra" fica preso sem banco: `r.active` é
    uma cláusula inteira dos dois lados, e os dois lados têm de ser o **mesmo
    conjunto** — o `on` do join igual, e o `where` da rota igual ao da CTE menos
    `p.official` (que na rota é o `if`) mais o recorte de `tenant_id`. Lê a
    **última** migration que define a função: a aplicada não se edita, então é
    numa migration nova que a função mudaria sem a rota saber.
    """
    marcador = "create or replace function public.fn_channel_readiness"
    funcao = last_migration_with(marcador).split(marcador, 1)[1]
    cte = funcao.split("blocked as (", 1)[1]
    join_cte, where_cte = _clauses(cte)
    join_rota, where_rota = _clauses(canais._BLOCKED_SQL)

    # `p.official` e `p.channel = 'whatsapp'` saíram do `where` para o `join
    # prov` da função (C3): ela só conta na linha de WhatsApp oficial, e na rota
    # os dois são o `if`. Continuam presos — no lugar em que a função os pôs.
    prov_on = _conjuncts(_tokens(cte.split("join prov p on", 1)[1].split("left join", 1)[0]))
    assert ("p.official",) in prov_on
    assert ("p.channel", "=", "'whatsapp'") in prov_on
    assert ("r.active",) in where_cte
    assert ("p.official",) not in where_cte
    assert join_rota == join_cte
    assert where_rota == where_cte | {("r.tenant_id", "=", "%(tenant_id)s")}


def test_a_lista_nao_deduplica(client: TestClient, cabecalho: dict[str, str], answer: Any) -> None:
    """O mesmo `code` em dois idiomas casa duas vezes no `left join` e a função
    conta as duas. Um `distinct` aqui quebraria o par das contagens."""
    assert "distinct" not in canais._BLOCKED_SQL.lower()

    repetida = [blocked_row(), blocked_row()]
    answer(readiness(rules_blocked=2), repetida)
    corpo = _whatsapp(client, cabecalho)

    assert len(corpo["blocked"]) == 2


def test_provedor_nao_oficial_nao_consulta_a_lista(
    client: TestClient, cabecalho: dict[str, str], answer: Any
) -> None:
    """A CTE da função só conta regra bloqueada quando o provedor é o oficial —
    é ele que recusa template não aprovado. Perguntar fora disso devolveria
    linha que `rules_blocked` não conta."""
    scope = answer(readiness(provider="z_api", official=False, rules_blocked=0, ready=True), [])

    corpo = _whatsapp(client, cabecalho)

    assert len(scope.statements) == 1
    assert corpo["blocked"] == []


# ---------------------------------------------------------------------------
# O que a rota não faz: recalcular, e adivinhar
# ---------------------------------------------------------------------------
def test_as_contagens_saem_da_funcao_e_nao_sao_refeitas(
    client: TestClient, cabecalho: dict[str, str], answer: Any
) -> None:
    """Refazer a conta em Python passaria nos testes de contagem e mentiria no
    primeiro dia em que o predicado da função mudasse."""
    scope = answer(readiness(templates_total=9, templates_approved=2, rules_blocked=1), [])

    corpo = _whatsapp(client, cabecalho)

    assert corpo["templates_total"] == 9
    assert corpo["templates_approved"] == 2
    assert "fn_channel_readiness" in scope.statements[0]
    assert not any("count(" in statement for statement in scope.statements)


def test_a_contagem_continua_sendo_a_da_funcao_quando_a_lista_discorda(
    client: TestClient, cabecalho: dict[str, str], answer: Any
) -> None:
    """O estado que não deveria existir, e o que a rota faz com ele.

    `rules_blocked = len(blocked)` fecharia a divergência por definição: a tela
    nunca mais se contradiria, e o dia em que o predicado da função e o desta
    rota deixassem de ser o mesmo passaria despercebido. A contagem é a mesma que
    o gate de prontidão usa; ela vem da função, e uma lista mais curta ao lado é
    justamente o sintoma que alguém precisa ver.
    """
    answer(readiness(rules_blocked=3), [blocked_row()])

    corpo = _whatsapp(client, cabecalho)

    assert corpo["rules_blocked"] == 3
    assert len(corpo["blocked"]) == 1


def test_a_divergencia_entre_contagem_e_lista_fica_no_log(
    client: TestClient,
    cabecalho: dict[str, str],
    answer: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Manter a procedência dos dois números está certo; entregá-los calados,
    não. O aviso nomeia o tenant e os dois números — e não levanta, porque em
    READ COMMITTED uma aprovação entre os dois statements produz exatamente essa
    diferença por um instante."""
    answer(readiness(rules_blocked=3), [blocked_row()])

    with caplog.at_level(logging.WARNING, logger=canais.logger.name):
        resposta = client.get("/canais/conexoes", headers=cabecalho)

    assert resposta.status_code == 200
    [aviso] = [r for r in caplog.records if r.name == canais.logger.name]
    assert aviso.levelno == logging.WARNING
    assert re.search(r"\b3\b", aviso.getMessage())
    assert re.search(r"\b1\b", aviso.getMessage())
    assert TENANT_ID in aviso.getMessage()


def test_a_divergencia_no_outro_sentido_tambem_fica_no_log(
    client: TestClient,
    cabecalho: dict[str, str],
    answer: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Lista maior que a contagem é a deriva que uma migration nova produz ao
    ESTREITAR o predicado da função — e é justamente a que ficaria muda se o
    aviso só olhasse para um lado."""
    answer(readiness(rules_blocked=0), [blocked_row()])

    with caplog.at_level(logging.WARNING, logger=canais.logger.name):
        client.get("/canais/conexoes", headers=cabecalho)

    [aviso] = [r for r in caplog.records if r.name == canais.logger.name]
    assert re.search(r"\b0\b", aviso.getMessage())
    assert re.search(r"\b1\b", aviso.getMessage())


def test_sem_divergencia_nao_ha_aviso(
    client: TestClient,
    cabecalho: dict[str, str],
    answer: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """O par do teste acima: um aviso que sai sempre é um aviso que ninguém lê."""
    answer(readiness(rules_blocked=1), [blocked_row()])

    with caplog.at_level(logging.WARNING, logger=canais.logger.name):
        client.get("/canais/conexoes", headers=cabecalho)

    assert [r for r in caplog.records if r.name == canais.logger.name] == []


def test_ready_e_o_da_funcao_e_nao_a_lista_vazia(
    client: TestClient, cabecalho: dict[str, str], answer: Any
) -> None:
    """`ready` da função é `blocked = 0 and approved > 0`. Recalculado como
    `not blocked`, um cliente oficial sem template nenhum viraria "pronto" —
    com zero regra bloqueada porque não há o que bloquear."""
    answer(readiness(templates_total=0, templates_approved=0, rules_blocked=0, ready=False), [])

    corpo = _whatsapp(client, cabecalho)

    assert corpo["blocked"] == []
    assert corpo["ready"] is False


def test_o_provedor_desconhecido_derruba_a_tela_em_vez_de_inventar_capacidade(
    client: TestClient, cabecalho: dict[str, str], answer: Any
) -> None:
    """Fail-closed até aqui. "Canal sem restrição" numa tela de quem decide ligar
    regra é como o anti-ban é desarmado por engano."""
    answer(readiness(provider="evolution_api", official=False))

    with pytest.raises(UnknownProviderError):
        client.get("/canais/conexoes", headers=cabecalho)


def test_as_capacidades_vem_da_matriz_e_chegam_inteiras_na_resposta(
    client: TestClient, cabecalho: dict[str, str], answer: Any
) -> None:
    """`meta_cloud` exige template e não corre risco de banimento; os não
    oficiais, o inverso. É o que a tela usa para escolher qual aviso dar."""
    answer(readiness())
    oficial = _whatsapp(client, cabecalho)["capabilities"]

    answer(readiness(provider="uazapi", official=False, rules_blocked=0, ready=True))
    nao_oficial = _whatsapp(client, cabecalho)["capabilities"]

    assert oficial == {
        "official": True,
        "requires_templates": True,
        "ban_risk": False,
        "requires_recipient_opt_in": False,
    }
    assert nao_oficial == {
        "official": False,
        "requires_templates": False,
        "ban_risk": True,
        "requires_recipient_opt_in": False,
    }


# ---------------------------------------------------------------------------
# A varredura
# ---------------------------------------------------------------------------
def test_nenhum_campo_da_resposta_carrega_segredo(
    client: TestClient, cabecalho: dict[str, str], answer: Any
) -> None:
    """Não olha o código: olha o corpo que saiu pelo socket.

    A credencial do provedor vive no Vault e `app.integration_secret` guarda só o
    ponteiro — *"nenhum role do painel lê esta tabela, nem owner"*. Então as
    linhas do stub vêm envenenadas com o que uma consulta descuidada traria
    junto, e o teste procura o valor na resposta.
    """
    veneno = "EAAG-token-da-waba-que-nao-pode-sair-daqui"
    answer(
        readiness(vault_id="0d5f6b2e", access_token=veneno, phone_number_id="55219999"),
        [blocked_row(vault_id="0d5f6b2e", access_token=veneno)],
    )

    resposta = client.get("/canais/conexoes", headers=cabecalho)

    assert resposta.status_code == 200
    assert veneno not in resposta.text
    assert "vault" not in resposta.text.lower()
    assert "token" not in resposta.text.lower()


def test_a_resposta_tem_exatamente_os_campos_do_contrato(
    client: TestClient, cabecalho: dict[str, str], answer: Any
) -> None:
    """Campo novo na tela é decisão, não efeito colateral de um `select *`."""
    answer(readiness(), [blocked_row()])

    tela = json.loads(client.get("/canais/conexoes", headers=cabecalho).text)

    assert set(tela) == {"whatsapp", "telegram"}
    assert tela["telegram"] is None
    corpo = tela["whatsapp"]
    assert set(corpo) == {
        "provider",
        "capabilities",
        "templates_total",
        "templates_approved",
        "rules_blocked",
        "ready",
        "blocked",
    }
    assert set(corpo["capabilities"]) == {
        "official",
        "requires_templates",
        "ban_risk",
        "requires_recipient_opt_in",
    }
    assert set(corpo["blocked"][0]) == {"rule_name", "template_code", "meta_status"}


def test_a_consulta_carrega_o_tenant_do_token(
    client: TestClient, cabecalho: dict[str, str], answer: Any
) -> None:
    """Ritual, e declarado como tal: confere que o placeholder está escrito e que
    o valor ligado é o tenant do token — não que o recorte funciona. `user_scope`
    roda sob RLS, e um stub não tem linha de outro tenant para deixar de fora.
    Quem prova que o filtro escrito basta sozinho é `scripts/97_teste_canais.py`,
    que executa `_BLOCKED_SQL` como `postgres` (sem RLS) com dois tenants
    semeados e afirma que só o ligado volta."""
    scope = answer(readiness(), [blocked_row()])

    client.get("/canais/conexoes", headers=cabecalho)

    for statement, params in zip(scope.statements, scope.params, strict=True):
        assert "%(tenant_id)s" in statement
        assert params["tenant_id"] == TENANT_ID
