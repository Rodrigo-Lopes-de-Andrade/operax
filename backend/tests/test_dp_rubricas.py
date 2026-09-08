"""O gate do S5, metade das rubricas: linha não validada não entrega categoria.

⛔ O QUE MUDOU NA LETRA DO GATE, E POR QUE
O gate dizia "código de rubrica não validado não aparece em indicador
financeiro". Medido em 07/09/2026: **não há indicador que leia categoria de
curadoria**. `public.vw_payroll_summary` soma `app.payroll_entry` por `nature`,
sem mapa nenhum, e a folha base do painel de DP não vem de `payroll_entry`. É o
mesmo formato do item 7 do despacho do S3, que o guardião derrubou por ser um par
impossível. Reenunciado pelo dono: a regra é propriedade de `read_curation` — a
função por onde qualquer indicador futuro terá de passar. Ela devolve **só** o
validado, e o que a folha usa e ninguém classificou volta **nomeado**.

A PERGUNTA DO FALSO VERDE, APLICADA AQUI
"O não validado não entra" é satisfeito por uma função que não devolve nada. Por
isso cada asserção negativa vem com o positivo do lado: na MESMA leitura, o
código validado entra em `categories` e o não validado sai em `pending`. Uma
curadoria que devolvesse dicionário vazio ficaria vermelha nas duas metades.

⚠️ A GUARDA DE TENANT DO DUBLÊ DO S3 NÃO ALCANÇA `with`, E AQUI ISSO MORDE
`FakeCursor` confere o filtro em statement que começa com `select`, `update` ou
`delete`. A leitura desta metade começa com `with` — e passava inteira, sem
guarda nenhuma. `FakeCursorComCTE` estende a guarda em vez de contorná-la, e o
dublê ainda ramifica no TEXTO das duas fontes: consulta que esqueça o filtro de
uma delas recebe as linhas do outro tenant e o teste fica vermelho. Sem isso, o
`union` seria a fuga que o próprio dublê do S1 declara não pegar.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from operax.core.tenant import TenantContext, UserRole
from operax.dp import rubricas
from operax.rh import repository as rh_repository
from tests.conftest import TENANT_ID, USER_ID
from tests.test_dp_ciclo import (
    _PREDICADO_TENANT,
    FakeCursor,
    FakeScope,
    _grupo_do_predicado_de_tenant,
    _no_mesmo_nivel,
    cabecalho,
)

OUTRO_TENANT = UUID("33333333-3333-4333-8333-000000000003")

CONTEXTO = TenantContext(tenant_id=TENANT_ID, user_id=USER_ID, role=UserRole.OWNER)


class FakeCursorComCTE(FakeCursor):
    """A guarda do S3, estendida a `with`.

    Não é zelo: a única consulta desta sprint que lê duas tabelas começa com
    `with`, e é justamente a que o `union` torna perigosa. Estender aqui, e não
    editar o dublê do S3, mantém a mudança dentro do arquivo que precisa dela.
    """

    async def execute(self, statement: str, params: Any = None) -> None:
        sql = " ".join(statement.split())
        if self._checar and sql.startswith("with"):
            assert _PREDICADO_TENANT in sql, f"consulta sem filtro de tenant: {sql}"
            grupo = _no_mesmo_nivel(_grupo_do_predicado_de_tenant(sql))
            assert " or " not in grupo, (
                f"o filtro de tenant é uma alternativa, não uma condição: {sql}"
            )
        await super().execute(statement, params)


class FakeDB:
    """A folha importada e o mapa curado, com as duas fontes ramificando no texto."""

    def __init__(self) -> None:
        self.admin = True
        self.compensation = True
        self.entries: list[dict[str, Any]] = []
        self.mapa: list[dict[str, Any]] = []
        self.audit: list[dict[str, Any]] = []
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self._ordem = 0

    # -- semeadura ----------------------------------------------------------
    def semear_entrada(
        self,
        code: str,
        description: str,
        nature: str = "earning",
        *,
        tenant_id: UUID = TENANT_ID,
    ) -> None:
        self._ordem += 1
        self.entries.append(
            {
                "tenant_id": tenant_id,
                "code": code,
                "description": description,
                "nature": nature,
                "created_at": datetime(2026, 8, 1, 0, self._ordem),
                "id": self._ordem,
            }
        )

    def semear_curadoria(
        self,
        code: str,
        category: str | None,
        *,
        validated: bool = False,
        label: str | None = None,
        nature: str | None = None,
        tenant_id: UUID = TENANT_ID,
    ) -> None:
        self.mapa.append(
            {
                "tenant_id": tenant_id,
                "code": code,
                "label": label,
                "nature": nature,
                "category": category,
                "validated_by": USER_ID if validated else None,
                "validated_at": datetime(2026, 9, 1, 12, 0) if validated else None,
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
        if sql.startswith("with entry as"):
            return self._listar(sql, params)
        if "insert into app.payroll_event_map" in sql:
            return self._curar(params)
        if "insert into app.audit_log" in sql:
            self.audit.append(dict(params))
            return []
        raise AssertionError(f"statement inesperado: {sql}")

    def _listar(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        # ⛔ O dublê NÃO filtra por conta própria: ele lê o texto. Consulta que
        #    esqueça o filtro de uma das fontes recebe o tenant alheio de volta,
        #    e é assim que o `union` deixa de ser fuga silenciosa.
        entradas = self.entries
        if "e.tenant_id = %(tenant_id)s" in sql:
            entradas = [linha for linha in entradas if linha["tenant_id"] == params["tenant_id"]]
        curadas = self.mapa
        if "m.tenant_id = %(tenant_id)s" in sql:
            curadas = [linha for linha in curadas if linha["tenant_id"] == params["tenant_id"]]

        if "distinct on (e.code)" in sql:
            # O rótulo que vale é o mais recente, com desempate estável.
            escolhidas: dict[str, dict[str, Any]] = {}
            for linha in sorted(entradas, key=lambda x: (x["created_at"], x["id"])):
                escolhidas[linha["code"]] = linha
            entradas = list(escolhidas.values())

        por_codigo = {linha["code"]: linha for linha in curadas}
        linhas: list[dict[str, Any]] = []
        for entrada in entradas:
            curada = por_codigo.get(entrada["code"])
            linhas.append(self._juntar(entrada["code"], entrada, curada))
        for curada in curadas:
            if not any(linha["code"] == curada["code"] for linha in entradas):
                linhas.append(self._juntar(curada["code"], None, curada))

        if "k.code = %(code)s::text" in sql and params.get("code") is not None:
            linhas = [linha for linha in linhas if linha["code"] == params["code"]]
        return sorted(linhas, key=lambda linha: linha["code"])

    def _juntar(
        self, code: str, entrada: dict[str, Any] | None, curada: dict[str, Any] | None
    ) -> dict[str, Any]:
        return {
            "code": code,
            "label": (curada or {}).get("label") or (entrada or {}).get("description"),
            "nature": (curada or {}).get("nature") or (entrada or {}).get("nature"),
            "category": (curada or {}).get("category"),
            "validated_at": (curada or {}).get("validated_at"),
            "in_payroll": entrada is not None,
        }

    def _curar(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        for linha in self.mapa:
            if linha["tenant_id"] == params["tenant_id"] and linha["code"] == params["code"]:
                linha["category"] = params["category"]
                linha["validated_by"] = params["validated_by"]
                linha["validated_at"] = params["validated_at"]
                return [{"code": linha["code"]}]
        self.mapa.append(
            {
                "tenant_id": params["tenant_id"],
                "code": params["code"],
                "label": None,
                "nature": None,
                "category": params["category"],
                "validated_by": params["validated_by"],
                "validated_at": params["validated_at"],
            }
        )
        return [{"code": params["code"]}]


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    estado = FakeDB()

    def tenant_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursorComCTE(estado, context, checar_tenant=True))

    def user_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursorComCTE(estado, context, checar_tenant=False))

    monkeypatch.setattr(rubricas, "tenant_scope", tenant_scope)
    monkeypatch.setattr(rh_repository, "user_scope", user_scope)
    return estado


def curar(client: TestClient, issue_token: Any, code: str, **overrides: Any) -> Any:
    corpo = {"category": "overtime", "validated": True} | overrides
    return client.patch(f"/dp/rubricas/{code}", json=corpo, headers=cabecalho(issue_token))


# ---------------------------------------------------------------------------
# 1. A lista: a folha do cliente e o que já foi curado
# ---------------------------------------------------------------------------
def test_a_lista_une_a_folha_e_a_curadoria(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_entrada("0050", "H.EXTRA 60%")
    fake_db.semear_curadoria("0090", "vacation", validated=True)

    linhas = client.get("/dp/rubricas", headers=cabecalho(issue_token)).json()["rows"]

    por_codigo = {linha["code"]: linha for linha in linhas}
    assert set(por_codigo) == {"0050", "0090"}
    # O que a folha usa e ninguém classificou: category nulo é um ESTADO, não um
    # buraco — e é o estado em que a semente entrega a lista.
    assert por_codigo["0050"]["category"] is None
    assert por_codigo["0050"]["validated"] is False
    assert por_codigo["0050"]["in_payroll"] is True
    # O curado que a folha não usa: aparece, mas não é pendência de ninguém.
    assert por_codigo["0090"]["in_payroll"] is False
    assert por_codigo["0090"]["validated"] is True


def test_o_mesmo_codigo_com_duas_descricoes_da_uma_linha_a_mais_recente(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """É o defeito que derrubaria a semente da §1i, do lado da leitura."""
    fake_db.semear_entrada("0050", "H EXTRA 60")
    fake_db.semear_entrada("0050", "H.EXTRA 60%")

    linhas = client.get("/dp/rubricas", headers=cabecalho(issue_token)).json()["rows"]

    assert len(linhas) == 1
    assert linhas[0]["label"] == "H.EXTRA 60%"


def test_a_lista_nao_atravessa_tenant_por_nenhuma_das_duas_fontes(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_entrada("0050", "H.EXTRA 60%")
    fake_db.semear_entrada("7777", "FOLHA ALHEIA", tenant_id=OUTRO_TENANT)
    fake_db.semear_curadoria("8888", "other", validated=True, tenant_id=OUTRO_TENANT)

    linhas = client.get("/dp/rubricas", headers=cabecalho(issue_token)).json()["rows"]

    assert [linha["code"] for linha in linhas] == ["0050"]


async def test_o_filtro_por_codigo_entra_e_some(fake_db: FakeDB) -> None:
    """O par. O defeito recorrente desta etapa é o parâmetro que não vira `where`."""
    fake_db.semear_entrada("0050", "H.EXTRA 60%")
    fake_db.semear_entrada("0060", "FERIAS GOZO")

    todos = await rubricas.list_codes(CONTEXTO)
    um = await rubricas.list_codes(CONTEXTO, code="0060")

    assert [linha.code for linha in todos] == ["0050", "0060"]
    assert [linha.code for linha in um] == ["0060"]


# ---------------------------------------------------------------------------
# 2. O gate: só o validado entrega categoria
# ---------------------------------------------------------------------------
async def test_nao_validado_fica_fora_da_categoria_e_volta_nomeado(fake_db: FakeDB) -> None:
    """As duas metades na MESMA leitura — o negativo com o positivo ao lado."""
    fake_db.semear_entrada("0050", "H.EXTRA 60%")
    fake_db.semear_entrada("0060", "FERIAS GOZO")
    fake_db.semear_curadoria("0050", "overtime", validated=True)
    # Classificado por alguém e ainda NÃO conferido: é o "provisório" que a
    # migration 30 tolerava e que aqui não vale.
    fake_db.semear_curadoria("0060", "vacation", validated=False)

    curadoria = await rubricas.read_curation(CONTEXTO)

    assert curadoria.categories == {"0050": "overtime"}
    assert curadoria.pending == ("0060",)


async def test_codigo_curado_que_a_folha_nao_usa_nao_e_pendencia(fake_db: FakeDB) -> None:
    """Pendência que não trava nada vira ruído que se aprende a ignorar."""
    fake_db.semear_entrada("0050", "H.EXTRA 60%")
    fake_db.semear_curadoria("0050", "overtime", validated=True)
    fake_db.semear_curadoria("9999", None, validated=False)

    curadoria = await rubricas.read_curation(CONTEXTO)

    assert curadoria.pending == ()
    assert curadoria.categories == {"0050": "overtime"}


def test_a_lista_publica_o_numero_de_pendencias(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_entrada("0050", "H.EXTRA 60%")
    fake_db.semear_entrada("0060", "FERIAS GOZO")
    fake_db.semear_curadoria("0050", "overtime", validated=True)

    corpo = client.get("/dp/rubricas", headers=cabecalho(issue_token)).json()

    # "Sem pendência" tem de ser afirmação, não ausência de aviso.
    assert corpo["pending"] == 1
    assert len(corpo["rows"]) == 2


# ---------------------------------------------------------------------------
# 3. A curadoria pela rota
# ---------------------------------------------------------------------------
def test_curar_classifica_e_registra_quem_conferiu(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_entrada("0050", "H.EXTRA 60%")

    resposta = curar(client, issue_token, "0050")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["category"] == "overtime"
    assert corpo["validated"] is True
    assert corpo["validated_at"] is not None
    # O rótulo continua vindo da folha: a curadoria não o reescreve.
    assert corpo["label"] == "H.EXTRA 60%"
    gravado = fake_db.mapa[0]
    assert gravado["validated_by"] == USER_ID


def test_curar_sem_validar_deixa_a_linha_fora_do_indicador(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Classificar e conferir são atos diferentes, e só o segundo libera a soma."""
    fake_db.semear_entrada("0050", "H.EXTRA 60%")

    resposta = curar(client, issue_token, "0050", validated=False)

    assert resposta.status_code == 200
    assert resposta.json()["category"] == "overtime"
    assert resposta.json()["validated"] is False
    assert fake_db.mapa[0]["validated_at"] is None
    assert fake_db.mapa[0]["validated_by"] is None


def test_curar_codigo_que_nao_existe_e_404(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_entrada("0050", "H.EXTRA 60%")

    ausente = curar(client, issue_token, "0051")
    assert ausente.status_code == 404
    assert "não aparece na folha" in ausente.json()["detail"]

    # O positivo ao lado: o código que existe é curado pela mesma rota.
    assert curar(client, issue_token, "0050").status_code == 200


def test_categoria_fora_das_nove_e_recusada_antes_do_banco(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_entrada("0050", "H.EXTRA 60%")

    assert curar(client, issue_token, "0050", category="hora_extra").status_code == 422
    assert fake_db.mapa == []


def test_reclassificar_troca_a_categoria_sem_apagar_a_linha(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Regra 6 estendida à curadoria: a trilha de quem classificou o quê fica."""
    fake_db.semear_entrada("0050", "H.EXTRA 60%")
    curar(client, issue_token, "0050")

    resposta = curar(client, issue_token, "0050", category="charge")

    assert resposta.status_code == 200
    assert len(fake_db.mapa) == 1
    assert fake_db.mapa[0]["category"] == "charge"
    apagaram = [sql for sql, _ in fake_db.statements if sql.startswith("delete")]
    assert apagaram == []


def test_a_trilha_guarda_a_categoria_anterior(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_entrada("0050", "H.EXTRA 60%")
    curar(client, issue_token, "0050")
    curar(client, issue_token, "0050", category="charge")

    assert len(fake_db.audit) == 2
    segunda = fake_db.audit[1]
    assert segunda["antes"].obj == {"category": "overtime", "validated": True}
    assert segunda["depois"].obj["category"] == "charge"
    assert segunda["depois"].obj["_origem"] == {"form": "dp_rubricas"}


# ---------------------------------------------------------------------------
# 4. Papel — os dois eixos, e a exclusão declarada
# ---------------------------------------------------------------------------
def test_sem_compensation_nao_le_nem_cura(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_entrada("0050", "H.EXTRA 60%")
    fake_db.compensation = False

    assert client.get("/dp/rubricas", headers=cabecalho(issue_token)).status_code == 403
    assert curar(client, issue_token, "0050").status_code == 403
    assert fake_db.mapa == []


def test_sem_admin_nao_le_nem_cura(client: TestClient, issue_token: Any, fake_db: FakeDB) -> None:
    """⚠️ A rota não pode ser mais frouxa que `payroll_event_map_admin`.

    É a exclusão declarada do S3: `accounting` tem `compensation` e não é admin,
    então não cura sozinho. O defeito que isto evita foi achado pelas duas
    revisões do S1 no catálogo de verbas — rota e policy discordando.
    """
    fake_db.semear_entrada("0050", "H.EXTRA 60%")
    fake_db.admin = False

    assert client.get("/dp/rubricas", headers=cabecalho(issue_token)).status_code == 403
    assert curar(client, issue_token, "0050").status_code == 403


def test_com_os_dois_eixos_le_e_cura(client: TestClient, issue_token: Any, fake_db: FakeDB) -> None:
    """O positivo dos dois testes acima — sem ele, os 403 ficariam verdes num 500."""
    fake_db.semear_entrada("0050", "H.EXTRA 60%")

    assert client.get("/dp/rubricas", headers=cabecalho(issue_token)).status_code == 200
    assert curar(client, issue_token, "0050").status_code == 200


def test_sem_token_nada_chega_ao_banco(client: TestClient, fake_db: FakeDB) -> None:
    assert client.get("/dp/rubricas").status_code == 401
    assert client.patch("/dp/rubricas/0050", json={"category": "overtime"}).status_code == 401
    assert fake_db.statements == []
