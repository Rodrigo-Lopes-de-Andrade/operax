"""O gate do S6: a porta que o apurador nomeava passa a existir — e não apaga nada.

⛔ O QUE ESTE ARQUIVO PROVA, E O QUE ELE NÃO PROVA
Ele prova a forma dos três atos e as recusas deles contra um dublê. Quem prova
que a apuração **deixa de recusar** depois de cinco strings validadas — e volta a
recusar sem validação — é `scripts/84_teste_curadoria_justificativa.py`, contra
Postgres de verdade, com as cinco justificativas que produção tem. O dublê não
tem `check` de canonicalização nem `grant`: dizer aqui que a chave é canônica
seria dizer que o fake concorda com o fake.

A PERGUNTA DO FALSO VERDE, APLICADA AQUI
"Provisório não entra em cálculo" é satisfeito por uma porta que nunca valida
nada, e "nunca apagar" por uma porta que nunca escreve. Por isso cada negativa
vem com o positivo ao lado: na MESMA sequência, classificar deixa `validated`
falso e validar o torna verdadeiro; reclassificar troca a categoria **e** a linha
continua uma só, com as duas passagens na trilha.

⚠️ A GUARDA DE `with` VEM DE `test_dp_rubricas`, IMPORTADA E NÃO COPIADA
A leitura desta sprint também começa com `with` e também une duas fontes — o
espelho e o mapa —, que é a forma que o dublê do S3 declara não pegar sozinho.
Copiar a guarda aqui seria provar uma cópia dela: a cópia fica verde exatamente
quando a original quebra.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from operax.core.tenant import TenantContext, UserRole
from operax.dp import justificativas
from operax.rh import repository as rh_repository
from tests.conftest import TENANT_ID, USER_ID
from tests.test_dp_ciclo import FakeScope, cabecalho
from tests.test_dp_rubricas import FakeCursorComCTE

OUTRO_TENANT = UUID("33333333-3333-4333-8333-000000000003")

CONTEXTO = TenantContext(tenant_id=TENANT_ID, user_id=USER_ID, role=UserRole.OWNER)

#: As cinco de produção, como a origem as escreve — quatro truncadas por ela.
FERIAS, ATESTED, ATEST_M, AFASTAD, FALTA = "Férias", "Atested", "ATEST M", "AFASTAD", "FALTA"


class FakeDB:
    """O espelho de afastamentos e o mapa curado, ramificando no TEXTO da consulta."""

    def __init__(self) -> None:
        self.admin = True
        self.afastamentos: list[dict[str, Any]] = []
        self.mapa: list[dict[str, Any]] = []
        self.audit: list[dict[str, Any]] = []
        self.statements: list[tuple[str, dict[str, Any]]] = []

    # -- semeadura ----------------------------------------------------------
    def semear_afastamento(
        self,
        justificativa: str | None,
        inicio: date = date(2026, 8, 3),
        fim: date = date(2026, 8, 4),
        *,
        tenant_id: UUID = TENANT_ID,
    ) -> None:
        self.afastamentos.append(
            {
                "tenant_id": tenant_id,
                "JustificativaNome": justificativa,
                "Inicio": inicio,
                "Fim": fim,
            }
        )

    def semear_curadoria(
        self,
        justification: str,
        category: str,
        *,
        validated: bool = False,
        notes: str | None = None,
        tenant_id: UUID = TENANT_ID,
    ) -> None:
        self.mapa.append(
            {
                "tenant_id": tenant_id,
                "justification": justification,
                "category": category,
                "notes": notes,
                "validated_by": USER_ID if validated else None,
                "validated_at": datetime(2026, 9, 1, 12, 0) if validated else None,
            }
        )

    # -- o despacho ---------------------------------------------------------
    def responder(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if "util.can_see_domain" in sql and "util.is_admin" in sql:
            return [{"admin": self.admin, "pii": True, "compensation": True, "health": True}]
        if sql.startswith("with mirror as"):
            return self._listar(sql, params)
        if "insert into app.leave_justification_map" in sql:
            return self._classificar(sql, params)
        if sql.startswith("update app.leave_justification_map"):
            return self._validar(params)
        if "insert into app.audit_log" in sql:
            self.audit.append(dict(params))
            return []
        raise AssertionError(f"statement inesperado: {sql}")

    def _listar(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        # ⛔ O dublê NÃO filtra por conta própria: ele lê o texto. Uma consulta que
        #    esqueça o filtro de uma das duas fontes recebe as linhas do outro
        #    cliente de volta — é assim que o `union` deixa de ser fuga muda.
        espelho = self.afastamentos
        if "a.tenant_id = %(tenant_id)s" in sql:
            espelho = [linha for linha in espelho if linha["tenant_id"] == params["tenant_id"]]
        curadas = self.mapa
        if "m.tenant_id = %(tenant_id)s" in sql:
            curadas = [linha for linha in curadas if linha["tenant_id"] == params["tenant_id"]]

        agrupado: dict[str, dict[str, Any]] = {}
        for linha in espelho:
            chave = (linha["JustificativaNome"] or "").strip().upper()
            grupo = agrupado.setdefault(
                chave,
                {"occurrences": 0, "first_leave": linha["Inicio"], "last_leave": linha["Fim"]},
            )
            grupo["occurrences"] += 1
            grupo["first_leave"] = min(grupo["first_leave"], linha["Inicio"])
            grupo["last_leave"] = max(grupo["last_leave"], linha["Fim"])

        # ⛔ E O DUBLÊ LÊ A FORMA DO JOIN, PELO MESMO MOTIVO. Uma leitura que
        #    trocasse `left join` por `join` esconderia exatamente quem precisa
        #    ser curado — e um fake que unisse as chaves por conta própria ficaria
        #    verde com a fila vazia de trabalho pendente.
        por_chave = {linha["justification"]: linha for linha in curadas}
        chaves = {*agrupado, *por_chave}
        if "left join curated" not in sql:
            chaves &= set(por_chave)
        if "left join mirror" not in sql:
            chaves &= set(agrupado)

        linhas: list[dict[str, Any]] = []
        for chave in chaves:
            grupo = agrupado.get(chave)
            curada = por_chave.get(chave)
            linhas.append(
                {
                    "justification": chave,
                    "occurrences": grupo["occurrences"] if grupo else 0,
                    "first_leave": grupo["first_leave"] if grupo else None,
                    "last_leave": grupo["last_leave"] if grupo else None,
                    "category": (curada or {}).get("category"),
                    "validated_at": (curada or {}).get("validated_at"),
                    "notes": (curada or {}).get("notes"),
                    "in_mirror": grupo is not None,
                }
            )

        if "k.justification = %(justification)s::text" in sql and params.get("justification"):
            linhas = [
                linha for linha in linhas if linha["justification"] == params["justification"]
            ]
        # A mesma ordem do `order by`: o que ninguém tocou primeiro, o validado
        # por último, e as mais frequentes na frente dentro de cada faixa.
        return sorted(
            linhas,
            key=lambda linha: (
                linha["validated_at"] is not None,
                linha["category"] is not None,
                -linha["occurrences"],
                linha["justification"],
            ),
        )

    def _classificar(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        # ⛔ O CARIMBO TAMBÉM SAI DO TEXTO, E ESTA LINHA FOI ESCRITA POR UMA
        #    MUTAÇÃO QUE PASSOU VERDE. O dublê zerava `validated_at` por conta
        #    própria, então uma classificação que carimbasse — os dois atos num
        #    clique só, o defeito que esta sprint existe para não ter — ficava
        #    invisível para as 22 asserções. Agora a linha nasce como a
        #    instrução disser.
        # E o `do update` é lido LITERALMENTE: "zera o carimbo" e "preserva o
        # carimbo" são instruções diferentes, e o dublê que decide sozinho não
        # distingue as duas. Uma mutação que trocasse `validated_at = null` por
        # `validated_at = <a coluna>` — revogando a decisão-título da sprint —
        # passava verde nas 22 asserções.
        carimbo = datetime(2026, 9, 23, 10, 0) if "now()" in sql else None
        quem = params.get("user_id") if carimbo else None
        zera_no_conflito = "validated_at = null" in " ".join(sql.split()).lower()
        for linha in self.mapa:
            if (
                linha["tenant_id"] == params["tenant_id"]
                and linha["justification"] == params["justification"]
            ):
                linha["category"] = params["category"]
                linha["notes"] = params["notes"]
                if zera_no_conflito or carimbo is not None:
                    linha["validated_by"] = quem
                    linha["validated_at"] = carimbo
                return [{"justification": linha["justification"]}]
        self.mapa.append(
            {
                "tenant_id": params["tenant_id"],
                "justification": params["justification"],
                "category": params["category"],
                "notes": params["notes"],
                "validated_by": quem,
                "validated_at": carimbo,
            }
        )
        return [{"justification": params["justification"]}]

    def _validar(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        for linha in self.mapa:
            if (
                linha["tenant_id"] == params["tenant_id"]
                and linha["justification"] == params["justification"]
            ):
                linha["validated_by"] = params["user_id"]
                linha["validated_at"] = datetime(2026, 9, 23, 10, 0)
                return [{"justification": linha["justification"]}]
        return []


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    estado = FakeDB()

    def tenant_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursorComCTE(estado, context, checar_tenant=True))

    def user_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursorComCTE(estado, context, checar_tenant=False))

    monkeypatch.setattr(justificativas, "tenant_scope", tenant_scope)
    monkeypatch.setattr(rh_repository, "user_scope", user_scope)
    return estado


def listar(client: TestClient, issue_token: Any) -> Any:
    return client.get("/dp/justificativas", headers=cabecalho(issue_token))


def classificar(client: TestClient, issue_token: Any, justificativa: str, **overrides: Any) -> Any:
    corpo = {"justification": justificativa, "category": "unjustified_absence"} | overrides
    return client.post("/dp/justificativas/classificar", json=corpo, headers=cabecalho(issue_token))


def validar(client: TestClient, issue_token: Any, justificativa: str) -> Any:
    return client.post(
        "/dp/justificativas/validar",
        json={"justification": justificativa},
        headers=cabecalho(issue_token),
    )


def cinco_de_producao(fake_db: FakeDB) -> None:
    """As cinco justificativas e as 64 ocorrências medidas em produção em 23/09."""
    for _ in range(43):
        fake_db.semear_afastamento(FERIAS)
    for _ in range(13):
        fake_db.semear_afastamento(ATESTED)
    for _ in range(5):
        fake_db.semear_afastamento(ATEST_M)
    for _ in range(2):
        fake_db.semear_afastamento(AFASTAD)
    fake_db.semear_afastamento(FALTA)


# ---------------------------------------------------------------------------
# 1. A fila — o que falta curar, que hoje não havia de onde tirar
# ---------------------------------------------------------------------------
def test_a_fila_traz_as_justificativas_do_espelho_canonicalizadas(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """A chave é a do banco: `upper(btrim(...))`, com acento preservado.

    `Atested` e `ATEST M` continuam duas linhas — são duas strings, e cada uma se
    cura sozinha. Juntá-las seria adivinhar, que é o que a curadoria existe para
    não fazer.
    """
    cinco_de_producao(fake_db)

    linhas = listar(client, issue_token).json()["rows"]

    assert [linha["justification"] for linha in linhas] == [
        "FÉRIAS",
        "ATESTED",
        "ATEST M",
        "AFASTAD",
        "FALTA",
    ]
    assert [linha["occurrences"] for linha in linhas] == [43, 13, 5, 2, 1]
    assert all(linha["category"] is None for linha in linhas)
    assert all(linha["validated"] is False for linha in linhas)
    assert all(linha["in_mirror"] is True for linha in linhas)


def test_a_fila_traz_o_periodo_de_cada_justificativa(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Quem cura decide olhando quantas vezes e desde quando — o resto é adivinhação."""
    fake_db.semear_afastamento(FALTA, date(2024, 7, 1), date(2024, 7, 2))
    fake_db.semear_afastamento(FALTA, date(2026, 9, 10), date(2026, 9, 12))

    linha = listar(client, issue_token).json()["rows"][0]

    assert (linha["occurrences"], linha["first_leave"], linha["last_leave"]) == (
        2,
        "2024-07-01",
        "2026-09-12",
    )


def test_a_curadoria_antiga_aparece_mesmo_sem_estar_no_espelho(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Sumir com ela esconderia uma decisão que alguém tomou — e não a desfaria."""
    fake_db.semear_afastamento(FALTA)
    fake_db.semear_curadoria("LICENÇA", "leave_of_absence", validated=True)

    linhas = listar(client, issue_token).json()["rows"]
    por_chave = {linha["justification"]: linha for linha in linhas}

    assert set(por_chave) == {"FALTA", "LICENÇA"}
    assert por_chave["LICENÇA"]["in_mirror"] is False
    assert por_chave["LICENÇA"]["occurrences"] == 0
    # E ela não é pendência: o espelho não a traz, então ela não trava apuração.
    assert por_chave["FALTA"]["in_mirror"] is True


def test_pendente_conta_o_que_o_espelho_traz_e_ninguem_validou(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Provisório trava a apuração igual ao não classificado, e conta como pendência."""
    cinco_de_producao(fake_db)
    fake_db.semear_curadoria("FÉRIAS", "vacation", validated=True)
    fake_db.semear_curadoria("ATESTED", "leave_period")  # classificada, sem aval
    fake_db.semear_curadoria("LICENÇA", "leave_of_absence")  # fora do espelho

    corpo = listar(client, issue_token).json()

    assert corpo["pending"] == 4
    assert len(corpo["rows"]) == 6


def test_afastamento_sem_justificativa_e_contado_e_nao_entra_na_fila(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ O FALSO VERDE DESTA SPRINT, FECHADO AQUI.

    `ciclo.resolve_absence_days` também para quando o Secullum manda afastamento
    sem justificativa nenhuma, e essa não tem o que classificar — a chave vazia é
    recusada pelo `check` da tabela. Escondendo-a, a tela diria "tudo curado"
    enquanto a competência continuasse recusando.
    """
    fake_db.semear_afastamento(FALTA)
    fake_db.semear_afastamento(None)
    fake_db.semear_afastamento("   ")

    corpo = listar(client, issue_token).json()

    assert [linha["justification"] for linha in corpo["rows"]] == ["FALTA"]
    assert corpo["without_justification"] == 2


def test_a_fila_nao_atravessa_tenant_por_nenhuma_das_duas_fontes(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_afastamento(FALTA)
    fake_db.semear_afastamento("FALTA ALHEIA", tenant_id=OUTRO_TENANT)
    fake_db.semear_curadoria("CURADA ALHEIA", "vacation", tenant_id=OUTRO_TENANT)

    linhas = listar(client, issue_token).json()["rows"]

    assert [linha["justification"] for linha in linhas] == ["FALTA"]


# ---------------------------------------------------------------------------
# 2. Classificar — e ficar provisório
# ---------------------------------------------------------------------------
def test_classificar_grava_a_categoria_e_deixa_provisorio(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ O ATO 1 NÃO CARIMBA NADA — é isso que o impede de virar dinheiro sozinho."""
    fake_db.semear_afastamento(FALTA)

    resposta = classificar(client, issue_token, FALTA, notes="tela do Secullum, 23/09")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["category"] == "unjustified_absence"
    assert corpo["validated"] is False
    assert corpo["validated_at"] is None
    assert corpo["notes"] == "tela do Secullum, 23/09"
    gravado = fake_db.mapa[0]
    assert gravado["validated_at"] is None
    assert gravado["validated_by"] is None


def test_classificar_usa_a_chave_canonica_do_banco(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """A tela manda a string como a origem a escreve; o que entra é `upper(btrim(...))`.

    Se esta porta gravasse `Férias`, o apurador procuraria `FÉRIAS`, não acharia,
    e a recusa diria "não mapeada" sobre uma justificativa que ESTÁ mapeada.
    """
    fake_db.semear_afastamento(FERIAS)

    resposta = classificar(client, issue_token, "  férias  ", category="vacation")

    assert resposta.status_code == 200
    assert resposta.json()["justification"] == "FÉRIAS"
    assert fake_db.mapa[0]["justification"] == "FÉRIAS"
    # O positivo ao lado: a linha gravada é a MESMA que a fila mostra.
    assert resposta.json()["occurrences"] == 1


def test_classificar_string_que_nao_existe_e_404_nomeado(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """A chave vem do corpo do pedido: um erro de digitação curaria o que nunca chega."""
    fake_db.semear_afastamento(FALTA)

    ausente = classificar(client, issue_token, "FALTAA")
    assert ausente.status_code == 404
    assert "FALTAA" in ausente.json()["detail"]
    assert fake_db.mapa == []

    # O positivo ao lado: a que existe é curada pela mesma rota.
    assert classificar(client, issue_token, FALTA).status_code == 200


def test_classificar_afastamento_sem_nome_e_recusado(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """A chave vazia é recusada pelo `check` da tabela — a recusa é nomeada antes dele."""
    fake_db.semear_afastamento(None)

    recusa = classificar(client, issue_token, "   ")

    assert recusa.status_code == 404
    assert "sem justificativa" in recusa.json()["detail"]
    assert fake_db.mapa == []


def test_categoria_fora_das_cinco_e_recusada_antes_do_banco(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_afastamento(FALTA)

    assert classificar(client, issue_token, FALTA, category="falta").status_code == 422
    assert fake_db.mapa == []


# ---------------------------------------------------------------------------
# 3. Validar — o ato separado, e o único que libera a apuração
# ---------------------------------------------------------------------------
def test_validar_carimba_quem_conferiu_e_quando(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_afastamento(FALTA)
    classificar(client, issue_token, FALTA)

    resposta = validar(client, issue_token, FALTA)

    assert resposta.status_code == 200
    assert resposta.json()["validated"] is True
    assert resposta.json()["validated_at"] is not None
    assert fake_db.mapa[0]["validated_by"] == USER_ID
    # E a categoria continua a que foi classificada: validar não reabre o ato 1.
    assert fake_db.mapa[0]["category"] == "unjustified_absence"


def test_validar_o_que_ninguem_classificou_e_recusa_nomeada(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ Validar é conferir uma classificação; sem linha no mapa não há o que conferir.

    Um `insert` aqui teria de inventar a categoria — exatamente o que a curadoria
    existe para não fazer.
    """
    fake_db.semear_afastamento(FALTA)

    recusa = validar(client, issue_token, FALTA)

    assert recusa.status_code == 422
    assert "não foi classificada" in recusa.json()["detail"]
    assert fake_db.mapa == []

    # O positivo ao lado: classificada antes, a mesma chamada passa.
    classificar(client, issue_token, FALTA)
    assert validar(client, issue_token, FALTA).status_code == 200


def test_validar_string_que_nao_existe_em_lugar_nenhum_e_recusado(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_afastamento(FALTA)

    recusa = validar(client, issue_token, "INVENTADA")

    assert recusa.status_code == 422
    assert "INVENTADA" in recusa.json()["detail"]
    assert fake_db.mapa == []


# ---------------------------------------------------------------------------
# 4. Reclassificar — sem apagar, e derrubando o aval
# ---------------------------------------------------------------------------
def test_reclassificar_troca_a_categoria_sem_apagar_a_linha(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Regra 6 estendida à curadoria: a trilha de quem classificou o quê fica de pé."""
    fake_db.semear_afastamento(ATEST_M)
    classificar(client, issue_token, ATEST_M, category="leave_period")

    resposta = classificar(client, issue_token, ATEST_M, category="unjustified_absence")

    assert resposta.status_code == 200
    assert len(fake_db.mapa) == 1
    assert fake_db.mapa[0]["category"] == "unjustified_absence"
    apagaram = [sql for sql, _ in fake_db.statements if sql.startswith("delete")]
    assert apagaram == []


def test_reclassificar_derruba_a_validacao(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """⛔ TROCAR A CATEGORIA DE UMA LINHA VALIDADA MUDARIA DINHEIRO SEM NINGUÉM VER.

    `FALTA` como `unjustified_absence` tira a cesta de quem faltou; como
    `vacation`, devolve. Se a linha seguisse validada, a troca entraria na
    próxima apuração sem conferência — o clique único que os dois atos existem
    para impedir. O lado para o qual isso erra é o de PARAR a apuração.
    """
    fake_db.semear_afastamento(FALTA)
    classificar(client, issue_token, FALTA)
    assert validar(client, issue_token, FALTA).json()["validated"] is True

    resposta = classificar(client, issue_token, FALTA, category="vacation")

    assert resposta.json()["validated"] is False
    assert fake_db.mapa[0]["validated_at"] is None
    assert fake_db.mapa[0]["validated_by"] is None
    # O positivo ao lado: validar de novo devolve o aval à categoria nova.
    assert validar(client, issue_token, FALTA).json()["validated"] is True
    assert fake_db.mapa[0]["category"] == "vacation"


# ---------------------------------------------------------------------------
# 5. A trilha — é ela que torna a curadoria auditável, e a razão de não haver delete
# ---------------------------------------------------------------------------
def test_a_trilha_guarda_os_dois_atos_com_o_estado_anterior(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_afastamento(FALTA)
    classificar(client, issue_token, FALTA, notes="conferido com o DP")
    validar(client, issue_token, FALTA)
    classificar(client, issue_token, FALTA, category="vacation")

    assert len(fake_db.audit) == 3
    primeira, segunda, terceira = fake_db.audit
    assert primeira["entity_id"] == "FALTA"
    assert primeira["antes"].obj == {"category": None, "validated": False, "notes": None}
    assert primeira["depois"].obj["category"] == "unjustified_absence"
    assert primeira["depois"].obj["_origem"] == {"form": "dp_justificativas"}
    # O ato 2 muda só o aval — e a trilha mostra os dois lados disso.
    assert (segunda["antes"].obj["validated"], segunda["depois"].obj["validated"]) == (False, True)
    # E a reclassificação registra que a validação caiu junto.
    assert terceira["antes"].obj == {
        "category": "unjustified_absence",
        "validated": True,
        "notes": "conferido com o DP",
    }
    assert terceira["depois"].obj["validated"] is False


# ---------------------------------------------------------------------------
# 6. Papel — admin, a mesma função que a policy chama
# ---------------------------------------------------------------------------
def test_sem_admin_nao_le_nem_cura_e_nada_e_escrito(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """403 ANTES de qualquer escopo: o único statement que roda é o da permissão."""
    fake_db.semear_afastamento(FALTA)
    fake_db.admin = False

    assert listar(client, issue_token).status_code == 403
    assert classificar(client, issue_token, FALTA).status_code == 403
    assert validar(client, issue_token, FALTA).status_code == 403

    assert fake_db.mapa == []
    assert fake_db.audit == []
    assert {sql.split()[0] for sql, _ in fake_db.statements} == {"select"}
    assert all("leave_justification_map" not in sql for sql, _ in fake_db.statements)


def test_com_admin_le_e_cura(client: TestClient, issue_token: Any, fake_db: FakeDB) -> None:
    """O positivo do teste acima — sem ele, os três 403 ficariam verdes num 500."""
    fake_db.semear_afastamento(FALTA)

    assert listar(client, issue_token).status_code == 200
    assert classificar(client, issue_token, FALTA).status_code == 200
    assert validar(client, issue_token, FALTA).status_code == 200


def test_sem_token_nada_chega_ao_banco(client: TestClient, fake_db: FakeDB) -> None:
    assert client.get("/dp/justificativas").status_code == 401
    assert (
        client.post(
            "/dp/justificativas/classificar",
            json={"justification": "FALTA", "category": "unjustified_absence"},
        ).status_code
        == 401
    )
    assert (
        client.post("/dp/justificativas/validar", json={"justification": "FALTA"}).status_code
        == 401
    )
    assert fake_db.statements == []


# ---------------------------------------------------------------------------
# 7. Nenhuma rota apaga linha do mapa — a metade final do gate
# ---------------------------------------------------------------------------
def test_nenhuma_rota_de_justificativa_emite_delete(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """A varredura, e não a confiança: o dublê guarda TODO statement que passou.

    `service_role` não tem `delete` nesta tabela (a migration falha alto se um dia
    tiver), então um `delete` aqui morreria em produção — mas morreria depois de a
    rota ter sido escrita, e é esta asserção que não deixa chegar lá.
    """
    fake_db.semear_afastamento(FALTA)
    fake_db.semear_afastamento(FERIAS)
    classificar(client, issue_token, FALTA)
    validar(client, issue_token, FALTA)
    classificar(client, issue_token, FALTA, category="vacation")
    classificar(client, issue_token, FERIAS, category="vacation")
    listar(client, issue_token)

    assert [sql for sql, _ in fake_db.statements if "delete" in sql] == []
    assert len(fake_db.mapa) == 2


async def test_o_filtro_por_justificativa_entra_e_some(fake_db: FakeDB) -> None:
    """O par do parâmetro: o defeito recorrente desta etapa é o que não vira `where`."""
    cinco_de_producao(fake_db)

    fila = await justificativas.read_queue(CONTEXTO)
    uma = await justificativas.classify(CONTEXTO, justification=ATEST_M, category="leave_period")

    assert len(fila.rows) == 5
    assert uma.justification == "ATEST M"
    assert uma.occurrences == 5


def test_o_carimbo_zerado_e_a_categoria_travada_estao_nas_instrucoes() -> None:
    """Duas decisões da sprint que só o texto da instrução guarda.

    A primeira: reclassificar derruba o aval — trocar `validated_at = null` por
    `validated_at = <a coluna>` no `do update` a revoga, e passava verde. A
    segunda: validar prende a categoria LIDA, sem o que duas sessões (uma
    validando, outra reclassificando) deixam validada a categoria que ninguém
    conferiu. As duas foram mutantes da revisão.
    """
    assert "validated_by = null" in justificativas._CLASSIFY_SQL
    assert "validated_at = null" in justificativas._CLASSIFY_SQL
    assert "and category = %(category)s" in justificativas._VALIDATE_SQL


def test_validar_canonicaliza_a_chave_como_classificar(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Classificar com uma grafia e validar com outra é a mesma linha.

    `canonical_justification` é a única régua das duas pontas; se `validar`
    deixasse de aplicá-la, a fila mostraria a linha classificada e validá-la
    diria "ainda não foi classificada" — a recusa que faz a pessoa desconfiar
    do conserto que ela acabou de fazer.
    """
    fake_db.semear_afastamento(FERIAS)

    resposta = classificar(client, issue_token, "Férias")
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["justification"] == "FÉRIAS"

    resposta = validar(client, issue_token, "  férias ")

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["justification"] == "FÉRIAS" and corpo["validated"] is True
    assert len([linha for linha in fake_db.mapa if linha["justification"] == "FÉRIAS"]) == 1
