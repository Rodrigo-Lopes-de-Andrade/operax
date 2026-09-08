"""O gate do S5, metade dos laudos: uma vigente por (unidade, tipo), e nada se edita.

⛔ O QUE ESTA SUÍTE **NÃO** PROVA, E ONDE ISSO É PROVADO
A vigência única é de TRÊS constraints do banco — uma raiz por trio, um sucessor
por laudo, e a renovação presa ao próprio trio. Quem prova que elas existem e
recusam é `supabase/migrations/20260907182520_dp_unit_compliance.sql`, com prova
viva, contra Postgres de verdade; e quem prova que o supervisor de uma unidade
não lê o laudo de outra é `scripts/98_teste_isolamento_tenant.sql`. Esta suíte
não abre banco e não substitui aquelas.

O que ela prova é o outro lado: que este backend **não contorna** as três — que
ele não faz `update` na linha vigente, não aceita renovação que troque de
unidade ou de tipo, e traduz cada recusa na frase certa. O dublê modela as três
travas e falha alto quando o código as viola.

A PERGUNTA DO FALSO VERDE, APLICADA AQUI
"Não deixa duas vigentes" é satisfeito por um backend que não deixa cadastrar
nada. Então toda recusa vem com o positivo ao lado, avaliado contra a mesma
regra: o segundo laudo do mesmo tipo é recusado **e** o de outro tipo entra; a
segunda renovação do mesmo pai é recusada **e** a renovação da ponta entra. Uma
trava que barrasse a renovação legítima seria pior que a ausência dela — foi
exatamente o que a forma de índice com função `immutable` fazia, medido em
07/09/2026.

⚠️ A GUARDA DE TENANT DO DUBLÊ NÃO ALCANÇA `with`
`FakeCursor` do S3 confere o filtro em statement que começa com `select`,
`update` ou `delete`. Uma consulta que comece com `with` passa inteira. Não
morde nesta metade (nenhuma consulta de laudo usa CTE), mas mordeu na de
rubricas — ver `tests/test_dp_rubricas.py`, onde a guarda foi estendida.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from psycopg import errors

from operax.dp import laudos, postos
from operax.rh import repository as rh_repository
from tests.conftest import TENANT_ID, USER_ID
from tests.test_dp_ciclo import (
    FakeCursor,
    FakeScope,
    _grupo_do_predicado,
    _no_mesmo_nivel,
    cabecalho,
)

OUTRO_TENANT = UUID("33333333-3333-4333-8333-000000000003")

UNIDADE_VISIVEL = UUID("bbbb0000-0000-4000-8000-000000000001")
UNIDADE_DE_OUTRO_SUPERVISOR = UUID("bbbb0000-0000-4000-8000-000000000002")

HOJE = date.today()

#: O recorte de unidade de `laudos._LIST_SQL`. Ele recebe os ids que a policy
#: liberou, e é o ÚNICO recorte de unidade do `GET /dp/laudos`: a consulta roda
#: sob `tenant_scope`, que é `service_role` e não aplica RLS.
_PREDICADO_UNIDADE = "v.unit_id = any(%(units)s::uuid[])"


class FakeCursorComUnidade(FakeCursor):
    """A guarda do S3, estendida ao predicado de UNIDADE.

    ⛔ POR QUE O `98` NÃO COBRE ISTO, AO CONTRÁRIO DO QUE O DUBLÊ DECLARAVA
    `scripts/98_teste_isolamento_tenant.sql` exercita a policy como
    `authenticated`. `laudos._LIST_SQL` não roda como `authenticated`: roda sob
    `tenant_scope`, e aí a policy `unit_compliance_report_read` não é consultada.
    Então o recorte de unidade desta consulta só é conferido aqui.

    E CONFERIR A PRESENÇA DO TEXTO NÃO BASTA — foi o achado do ciclo 2. Duas
    mutações mantinham o predicado no statement e o desligavam, e as duas
    sobreviveram a 17 testes verdes:

        and (true or v.unit_id = any(%(units)s::uuid[]))
        and (%(units)s::uuid[] is null or v.unit_id = any(%(units)s::uuid[]))

    A segunda não é sintética: é a forma que nasce de "opção todas as unidades".
    A asserção abaixo é a mesma do predicado de tenant — o filtro é uma condição,
    não uma alternativa.
    """

    async def execute(self, statement: str, params: Any = None) -> None:
        sql = " ".join(statement.split())
        # A leitura por `report_id` não recorta por unidade de propósito: quem
        # recorta ali é a rota, que já carregou o laudo e conferiu a unidade dele.
        if "from public.vw_unit_compliance v" in sql and "%(report_id)s" not in sql:
            assert _PREDICADO_UNIDADE in sql, f"consulta de laudo sem recorte de unidade: {sql}"
            grupo = _no_mesmo_nivel(_grupo_do_predicado(sql, _PREDICADO_UNIDADE))
            assert " or " not in grupo, (
                f"o recorte de unidade é uma alternativa, não uma condição — "
                f"`or` no mesmo nível do predicado: {sql}"
            )
        await super().execute(statement, params)


class FakeDB:
    """Os laudos, com as TRÊS travas do banco modeladas e falhando alto.

    ⛔ O dublê filtrar por `params["tenant_id"]` não é evidência de nada — é
    conveniência. Quem contradiz uma consulta mal escrita é a asserção de
    `FakeCursor`, importada do S3.
    """

    def __init__(self) -> None:
        self.admin = True
        self.compensation = True
        self.unidades_visiveis: set[UUID] = {UNIDADE_VISIVEL}
        self.unidades: list[dict[str, Any]] = []
        self.laudos: list[dict[str, Any]] = []
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

    def semear_unidade(
        self, unit_id: UUID, nome: str, *, tenant_id: UUID = TENANT_ID, visivel: bool = True
    ) -> None:
        self.unidades.append({"id": unit_id, "tenant_id": tenant_id, "name": nome})
        if visivel:
            self.unidades_visiveis.add(unit_id)

    def semear_laudo(
        self,
        unit_id: UUID,
        type: str,
        valid_until: date,
        *,
        replaces_id: UUID | None = None,
        tenant_id: UUID = TENANT_ID,
        notes: str | None = None,
    ) -> UUID:
        laudo_id = self.novo_id()
        self.laudos.append(
            {
                "id": laudo_id,
                "tenant_id": tenant_id,
                "unit_id": unit_id,
                "type": type,
                "valid_until": valid_until,
                "notes": notes,
                "replaces_id": replaces_id,
                "created_by": USER_ID,
                "created_at": datetime(2026, 9, 1, 12, 0),
            }
        )
        return laudo_id

    # -- a view, como a migration a define ----------------------------------
    def _vigente(self, linha: dict[str, Any]) -> bool:
        return not any(outro["replaces_id"] == linha["id"] for outro in self.laudos)

    def _cadeia(self, linha: dict[str, Any]) -> int:
        return len(
            [
                outro
                for outro in self.laudos
                if outro["tenant_id"] == linha["tenant_id"]
                and outro["unit_id"] == linha["unit_id"]
                and outro["type"] == linha["type"]
            ]
        )

    def _da_view(self, linha: dict[str, Any]) -> dict[str, Any]:
        unidade = next(u for u in self.unidades if u["id"] == linha["unit_id"])
        return {
            "report_id": linha["id"],
            "tenant_id": linha["tenant_id"],
            "unit_id": linha["unit_id"],
            "unit_name": unidade["name"],
            "type": linha["type"],
            "valid_until": linha["valid_until"],
            "days_to_expiry": (linha["valid_until"] - HOJE).days,
            "renewal_count": self._cadeia(linha) - 1,
            "notes": linha["notes"],
            "created_at": linha["created_at"],
        }

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
        if "from app.unit u" in sql and "from app.unit_compliance_report" not in sql:
            return [
                {"id": unidade["id"]}
                for unidade in self.unidades
                if unidade["id"] in self.unidades_visiveis
            ]

        if "from public.vw_unit_compliance v" in sql:
            return self._ler_view(sql, params)
        if "from app.unit_compliance_report r" in sql:
            return self._carregar(params)
        if "insert into app.unit_compliance_report" in sql:
            return self._inserir(sql, params)

        if "insert into app.audit_log" in sql:
            self.audit.append(dict(params))
            return []
        raise AssertionError(f"statement inesperado: {sql}")

    def _ler_view(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        linhas = [linha for linha in self._do_tenant(self.laudos, params) if self._vigente(linha)]
        if "v.report_id = %(report_id)s" in sql:
            linhas = [linha for linha in linhas if linha["id"] == params["report_id"]]
        else:
            # ⛔ O dublê NÃO recorta por conta própria: ele lê o TEXTO. Um fake
            #    que filtra sozinho nunca contradiz a consulta — medido em
            #    07/09/2026, quando a mutação que apagava o recorte por unidade
            #    sobreviveu a 34 testes verdes.
            if "v.unit_id = any(%(units)s::uuid[])" in sql:
                linhas = [linha for linha in linhas if linha["unit_id"] in set(params["units"])]
            if (
                "%(unit_id)s::uuid is null or v.unit_id = %(unit_id)s::uuid" in sql
                and params["unit_id"] is not None
            ):
                linhas = [linha for linha in linhas if linha["unit_id"] == params["unit_id"]]
        return [self._da_view(linha) for linha in linhas]

    def _carregar(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        # ⚠️ Sem filtro de vigência: o `_LOAD_SQL` lê a TABELA de propósito, para
        # que renovar um laudo já substituído chegue ao banco e receba a frase
        # certa em vez de um "não encontrado".
        for linha in self._do_tenant(self.laudos, params):
            if linha["id"] == params["report_id"]:
                unidade = next(u for u in self.unidades if u["id"] == linha["unit_id"])
                return [{**linha, "unit_name": unidade["name"]}]
        return []

    def _inserir(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """As três travas do banco, aqui, e falhando alto.

        O `type` só é canonicalizado se o statement pedir `upper(btrim(...))` —
        o dublê ramifica no TEXTO, e não decide por conta própria. Sem isso,
        apagar a canonicalização do `insert` não teria sintoma nenhum.
        """
        tipo = params["type"]
        if "upper(btrim(%(type)s))" in sql:
            tipo = tipo.strip().upper()

        pai = None
        if params["replaces_id"] is not None:
            pai = next(
                (linha for linha in self.laudos if linha["id"] == params["replaces_id"]), None
            )
            # (C) replaces_same_scope
            if pai is None or (
                pai["tenant_id"] != params["tenant_id"]
                or pai["unit_id"] != params["unit_id"]
                or pai["type"] != tipo
            ):
                raise errors.ForeignKeyViolation(
                    "insert violates foreign key constraint "
                    '"unit_compliance_report_replaces_same_scope"'
                )
            # (B) single_successor_idx
            if any(linha["replaces_id"] == params["replaces_id"] for linha in self.laudos):
                raise errors.UniqueViolation(
                    "duplicate key value violates unique constraint "
                    '"unit_compliance_report_single_successor_idx"'
                )
        # (A) single_root_idx
        elif any(
            linha["tenant_id"] == params["tenant_id"]
            and linha["unit_id"] == params["unit_id"]
            and linha["type"] == tipo
            and linha["replaces_id"] is None
            for linha in self.laudos
        ):
            raise errors.UniqueViolation(
                "duplicate key value violates unique constraint "
                '"unit_compliance_report_single_root_idx"'
            )

        linha = {
            "id": self.novo_id(),
            "tenant_id": params["tenant_id"],
            "unit_id": params["unit_id"],
            "type": tipo,
            "valid_until": params["valid_until"],
            "notes": params["notes"],
            "replaces_id": params["replaces_id"],
            "created_by": params["created_by"],
            "created_at": datetime(2026, 9, 1, 12, 0),
        }
        self.laudos.append(linha)
        return [{"id": linha["id"]}]


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    estado = FakeDB()

    def tenant_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursorComUnidade(estado, context, checar_tenant=True))

    def user_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursorComUnidade(estado, context, checar_tenant=False))

    monkeypatch.setattr(laudos, "tenant_scope", tenant_scope)
    # `visible_units` e `can_see_unit` moram em `postos` — a pergunta
    # autorizadora tem uma implementação só, e o dublê a alcança por lá.
    monkeypatch.setattr(postos, "user_scope", user_scope)
    monkeypatch.setattr(rh_repository, "user_scope", user_scope)
    estado.semear_unidade(UNIDADE_VISIVEL, "Shopping Centro")
    estado.semear_unidade(UNIDADE_DE_OUTRO_SUPERVISOR, "Shopping Norte", visivel=False)
    return estado


def cadastrar(client: TestClient, issue_token: Any, **overrides: Any) -> Any:
    corpo = {
        "unit_id": str(UNIDADE_VISIVEL),
        "type": "PCMSO",
        "valid_until": "2026-12-31",
        "notes": None,
    } | overrides
    return client.post("/dp/laudos", json=corpo, headers=cabecalho(issue_token))


def renovar(client: TestClient, issue_token: Any, report_id: UUID, **overrides: Any) -> Any:
    corpo = {"valid_until": "2027-12-31", "notes": None} | overrides
    return client.post(
        f"/dp/laudos/{report_id}/renovar", json=corpo, headers=cabecalho(issue_token)
    )


# ---------------------------------------------------------------------------
# 1. A lista mostra a VIGENTE — e a substituída não é ela
# ---------------------------------------------------------------------------
def test_a_lista_traz_a_ponta_da_cadeia_e_nao_a_substituida(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    raiz = fake_db.semear_laudo(UNIDADE_VISIVEL, "PCMSO", date(2026, 6, 30))
    fake_db.semear_laudo(UNIDADE_VISIVEL, "PCMSO", date(2027, 6, 30), replaces_id=raiz)

    resposta = client.get("/dp/laudos", headers=cabecalho(issue_token))

    assert resposta.status_code == 200
    linhas = resposta.json()["rows"]
    assert len(linhas) == 1, "a substituída continua vigente na leitura"
    assert linhas[0]["valid_until"] == "2027-06-30"
    # O contador de histórico da tela do legado.
    assert linhas[0]["renewal_count"] == 1


def test_days_to_expiry_e_derivado_e_fica_negativo_no_vencido(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Situação é derivada de `valid_until` — a metade do gate que não é índice."""
    fake_db.semear_laudo(UNIDADE_VISIVEL, "PGR", HOJE + timedelta(days=10))
    fake_db.semear_laudo(UNIDADE_VISIVEL, "PCMSO", HOJE - timedelta(days=3))

    linhas = client.get("/dp/laudos", headers=cabecalho(issue_token)).json()["rows"]

    por_tipo = {linha["type"]: linha["days_to_expiry"] for linha in linhas}
    assert por_tipo == {"PGR": 10, "PCMSO": -3}
    # ⛔ E nenhuma coluna de situação viaja: a janela de "a vencer" não existe
    #    no schema para laudo, e uma constante aqui mentiria com cara de config.
    assert "situation" not in linhas[0]


def test_o_filtro_por_unidade_entra_e_some(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """O par — o defeito recorrente desta etapa é parâmetro que não vira `where`."""
    fake_db.semear_unidade(
        UUID("bbbb0000-0000-4000-8000-000000000009"), "Shopping Sul", visivel=True
    )
    fake_db.semear_laudo(UNIDADE_VISIVEL, "PCMSO", date(2026, 12, 31))
    fake_db.semear_laudo(UUID("bbbb0000-0000-4000-8000-000000000009"), "PCMSO", date(2027, 1, 31))

    todos = client.get("/dp/laudos", headers=cabecalho(issue_token)).json()["rows"]
    filtrado = client.get(
        f"/dp/laudos?unidade={UNIDADE_VISIVEL}", headers=cabecalho(issue_token)
    ).json()["rows"]

    assert len(todos) == 2
    assert [linha["unit_id"] for linha in filtrado] == [str(UNIDADE_VISIVEL)]


def test_laudo_de_unidade_fora_do_escopo_nao_aparece(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_laudo(UNIDADE_DE_OUTRO_SUPERVISOR, "PCMSO", date(2026, 12, 31))
    fake_db.semear_laudo(UNIDADE_VISIVEL, "PGR", date(2026, 12, 31))

    linhas = client.get("/dp/laudos", headers=cabecalho(issue_token)).json()["rows"]

    # O negativo com o positivo ao lado: some o de fora, fica o de dentro.
    assert [linha["type"] for linha in linhas] == ["PGR"]


def test_laudo_de_outro_tenant_nao_aparece(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_unidade(UNIDADE_VISIVEL, "Shopping Centro", tenant_id=OUTRO_TENANT)
    fake_db.semear_laudo(UNIDADE_VISIVEL, "LTCAT+LTIP", date(2026, 12, 31), tenant_id=OUTRO_TENANT)
    fake_db.semear_laudo(UNIDADE_VISIVEL, "PGR", date(2026, 12, 31))

    linhas = client.get("/dp/laudos", headers=cabecalho(issue_token)).json()["rows"]

    assert [linha["type"] for linha in linhas] == ["PGR"]


# ---------------------------------------------------------------------------
# 2. Cadastro — uma raiz por (unidade, tipo), e o positivo ao lado
# ---------------------------------------------------------------------------
def test_cadastra_o_primeiro_laudo(client: TestClient, issue_token: Any, fake_db: FakeDB) -> None:
    resposta = cadastrar(client, issue_token, notes="Renovação anual")

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["type"] == "PCMSO"
    assert corpo["renewal_count"] == 0
    assert corpo["unit_name"] == "Shopping Centro"
    assert len(fake_db.laudos) == 1
    assert fake_db.laudos[0]["created_by"] == USER_ID


def test_o_segundo_laudo_do_mesmo_tipo_e_recusado_e_o_de_outro_tipo_entra(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    assert cadastrar(client, issue_token).status_code == 201

    choque = cadastrar(client, issue_token, valid_until="2027-12-31")
    assert choque.status_code == 409
    assert "renove o vigente" in choque.json()["detail"]

    # O positivo: a trava é do TRIO, não do tipo nem da unidade.
    assert cadastrar(client, issue_token, type="PGR").status_code == 201
    assert (
        cadastrar(client, issue_token, unit_id=str(UNIDADE_DE_OUTRO_SUPERVISOR)).status_code == 404
    )


def test_o_tipo_e_canonicalizado_pelo_banco(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """`pcmso` e `PCMSO` são o mesmo laudo — e quem decide isso é o `insert`.

    A asserção olha o statement, e não o resultado: a canonicalização é uma
    expressão SQL, e o dublê só a aplica porque o texto a pede. Quem prova que o
    banco RECUSA o não canônico é a prova viva da migration.
    """
    assert cadastrar(client, issue_token, type=" pcmso ").status_code == 201
    assert fake_db.laudos[0]["type"] == "PCMSO"

    inserts = [
        sql for sql, _ in fake_db.statements if sql.startswith("insert into app.unit_compliance")
    ]
    assert inserts and all("upper(btrim(%(type)s))" in sql for sql in inserts)

    # E o segundo, escrito de outro jeito, colide com o primeiro.
    assert cadastrar(client, issue_token, type="PCMSO").status_code == 409


# ---------------------------------------------------------------------------
# 3. Renovar — linha nova, e o passado intacto
# ---------------------------------------------------------------------------
def test_renovar_cria_linha_nova_e_nao_toca_a_anterior(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    raiz = fake_db.semear_laudo(UNIDADE_VISIVEL, "PCMSO", date(2026, 6, 30), notes="original")

    resposta = renovar(client, issue_token, raiz, notes="laudo 2027")

    assert resposta.status_code == 201
    assert resposta.json()["valid_until"] == "2027-12-31"
    assert resposta.json()["renewal_count"] == 1

    anterior = next(linha for linha in fake_db.laudos if linha["id"] == raiz)
    # ⛔ O vencimento que valeu não se reescreve: foi com ele que a unidade foi
    #    fiscalizada.
    assert anterior["valid_until"] == date(2026, 6, 30)
    assert anterior["notes"] == "original"
    nova = next(linha for linha in fake_db.laudos if linha["id"] != raiz)
    assert nova["replaces_id"] == raiz


def test_renovar_duas_vezes_o_mesmo_laudo_e_recusado_e_a_ponta_renova(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    raiz = fake_db.semear_laudo(UNIDADE_VISIVEL, "PCMSO", date(2026, 6, 30))

    primeira = renovar(client, issue_token, raiz)
    assert primeira.status_code == 201
    ponta = UUID(primeira.json()["id"])

    segunda = renovar(client, issue_token, raiz, valid_until="2028-12-31")
    assert segunda.status_code == 409
    assert "já foi renovado" in segunda.json()["detail"]

    # O positivo: a cadeia continua pela ponta. Uma trava que barrasse isto
    # seria pior que a ausência dela.
    assert renovar(client, issue_token, ponta, valid_until="2029-12-31").status_code == 201
    assert len(fake_db.laudos) == 3


def test_renovar_nao_aceita_trocar_unidade_nem_tipo(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Unidade e tipo não estão no corpo — e mandá-los é 422, não silêncio."""
    raiz = fake_db.semear_laudo(UNIDADE_VISIVEL, "PCMSO", date(2026, 6, 30))

    resposta = client.post(
        f"/dp/laudos/{raiz}/renovar",
        json={"valid_until": "2027-12-31", "unit_id": str(UNIDADE_DE_OUTRO_SUPERVISOR)},
        headers=cabecalho(issue_token),
    )

    assert resposta.status_code == 422


def test_renovar_laudo_de_unidade_fora_do_escopo_e_404(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    de_fora = fake_db.semear_laudo(UNIDADE_DE_OUTRO_SUPERVISOR, "PCMSO", date(2026, 6, 30))
    de_dentro = fake_db.semear_laudo(UNIDADE_VISIVEL, "PCMSO", date(2026, 6, 30))

    assert renovar(client, issue_token, de_fora).status_code == 404
    # O positivo ao lado: o da unidade que ele enxerga renova.
    assert renovar(client, issue_token, de_dentro).status_code == 201


def test_renovar_laudo_de_outro_tenant_e_404(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.semear_unidade(UNIDADE_VISIVEL, "Shopping Centro", tenant_id=OUTRO_TENANT)
    alheio = fake_db.semear_laudo(
        UNIDADE_VISIVEL, "PCMSO", date(2026, 6, 30), tenant_id=OUTRO_TENANT
    )

    assert renovar(client, issue_token, alheio).status_code == 404


# ---------------------------------------------------------------------------
# 4. Nada se edita e nada se apaga — a varredura
# ---------------------------------------------------------------------------
def test_nenhum_update_e_nenhum_delete_tocam_o_laudo(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """Regra 6: o que existe é `insert`. A varredura vale mais que a leitura do módulo."""
    raiz = fake_db.semear_laudo(UNIDADE_VISIVEL, "PCMSO", date(2026, 6, 30))
    renovar(client, issue_token, raiz)
    cadastrar(client, issue_token, type="PGR")
    client.get("/dp/laudos", headers=cabecalho(issue_token))

    tocaram = [
        sql
        for sql, _ in fake_db.statements
        if ("unit_compliance_report" in sql and sql.startswith(("update", "delete")))
    ]
    assert tocaram == []


def test_a_trilha_distingue_cadastro_de_renovacao(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    cadastrar(client, issue_token)
    raiz = fake_db.laudos[0]["id"]
    renovar(client, issue_token, raiz)

    assert len(fake_db.audit) == 2
    cadastro, renovacao = fake_db.audit
    assert cadastro["antes"].obj is None
    assert cadastro["depois"].obj["valid_until"] == "2026-12-31"
    # `antes` preenchido é o que diz, na trilha, que houve renovação — e guarda
    # o vencimento que saiu, que é o que valeu na fiscalização.
    assert renovacao["antes"].obj["valid_until"] == "2026-12-31"
    assert renovacao["depois"].obj["valid_until"] == "2027-12-31"
    assert renovacao["depois"].obj["_origem"] == {"form": "dp_laudos"}


# ---------------------------------------------------------------------------
# 5. Papel — quem lê, quem escreve
# ---------------------------------------------------------------------------
def test_sem_admin_le_e_nao_escreve(client: TestClient, issue_token: Any, fake_db: FakeDB) -> None:
    fake_db.semear_laudo(UNIDADE_VISIVEL, "PCMSO", date(2026, 6, 30))
    fake_db.admin = False

    lista = client.get("/dp/laudos", headers=cabecalho(issue_token))
    assert lista.status_code == 200
    assert lista.json()["can_write"] is False
    assert len(lista.json()["rows"]) == 1

    assert cadastrar(client, issue_token, type="PGR").status_code == 403
    assert renovar(client, issue_token, fake_db.laudos[0]["id"]).status_code == 403


def test_sem_token_nada_chega_ao_banco(client: TestClient, fake_db: FakeDB) -> None:
    assert client.get("/dp/laudos").status_code == 401
    assert client.post("/dp/laudos", json={"unit_id": str(UNIDADE_VISIVEL)}).status_code == 401
    assert fake_db.statements == []
