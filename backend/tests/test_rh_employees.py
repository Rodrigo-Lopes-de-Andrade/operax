"""A aba Colaboradores: o que some da resposta, e o que a resposta recusa.

Duas coisas valem teste aqui, e nenhuma é o SQL — as instruções fixas são
compiladas contra o schema real no `make db-test`.

A primeira é a **ausência**. Bloco de domínio que o papel não alcança tem de vir
`null`, não `[]`, porque é isso que faz a aba não existir no DOM em vez de
aparecer vazia ou desabilitada. `null` e `[]` são a mesma coisa para quem só olha
o status 200, e são o produto inteiro para quem lê a tela.

A segunda é que o formulário recusa exatamente o que a planilha recusa. Se um dia
`PATCH /rh/employees/{id}` aceitar um ID RH que o import recusaria, a regra 1 da
etapa deixou de valer sem ninguém notar.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from operax.core.tenant import bind_tenant
from operax.rh import employees as repo
from operax.rh import foto as foto_mod
from operax.rh import repository

ANA = UUID("aaaa0000-0000-4000-8000-000000000001")
BRUNO = UUID("bbbb0000-0000-4000-8000-000000000002")
UNIDADE = UUID("33333333-3333-4333-8333-333333333333")


def pessoa_detalhe(**overrides: Any) -> dict[str, Any]:
    return {
        "employee_id": ANA,
        "name": "Ana Personagem",
        "registration_number": "1001",
        "hr_code": "RH-01",
        "cargo": "Operadora",
        "status": "active",
        "hired_on": date(2024, 3, 1),
        "terminated_on": None,
        "employment_type": "clt",
        "unit_id": UNIDADE,
        "unit_name": "Shopping Norte",
        "company_name": "FastPark Norte",
        "department_name": "Operação",
        "manager_name": "Bruno Personagem",
    } | overrides


JPEG_DE_MENTIRA = b"\xff\xd8\xff-bytes-de-mentira"


class FakeCursor:
    """Cursor de mentira endereçado por trecho de statement.

    Nas escritas ele roda `bind_tenant` de verdade: um `update` sem filtro de
    tenant não chega ao banco de mentira, do mesmo jeito que não chegaria ao real.
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
    def __init__(
        self,
        *,
        admin: bool = True,
        pii: bool = True,
        compensation: bool = True,
        health: bool = True,
        existe: bool = True,
        foto: str = "disponivel",
    ) -> None:
        self.admin = admin
        self.pii = pii
        self.compensation = compensation
        self.health = health
        self.existe = existe
        #: 'ausente' | 'pendente' | 'disponivel' — os três estados do §6 da decisão.
        self.foto = foto
        #: A linha de `app.employee_photo`, quando alguém enviou.
        self.foto_manual: dict[str, Any] | None = None
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.audit: list[dict[str, Any]] = []
        self.pessoa = pessoa_detalhe()
        self.hr_codes = {"RH-01": ANA, "RH-02": BRUNO}
        self.open_compensation: date | None = date(2026, 1, 1)
        self.open_position: date | None = date(2024, 3, 1)

    def responder(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        # --- foto do colaborador (operax/rh/foto.py) -------------------------
        if "e.secullum_employee_id" in sql and "from app.employee e" in sql:
            # A RLS é quem decide: pessoa fora de alcance devolve vazio, e a rota
            # transforma em 404 sem revelar que ela existe noutra unidade.
            return [{"secullum_employee_id": 4242}] if self.existe else []
        if "from app.employee_photo" in sql:
            # A foto enviada. `None` = ninguém enviou nada para esta pessoa.
            return [self.foto_manual] if self.foto_manual else []
        if 'from secullum."Funcionario"' in sql:
            if self.foto == "ausente":
                return [{"possui": False, "synced_at": None, "bytes": None}]
            if self.foto == "pendente":
                return [{"possui": True, "synced_at": None, "bytes": None}]
            if "as content" in sql:
                return [
                    {
                        "content": JPEG_DE_MENTIRA,
                        "mime": "image/jpeg",
                        "synced_at": datetime(2026, 9, 2, 20, 31),
                    }
                ]
            return [{"possui": True, "synced_at": datetime(2026, 9, 2, 20, 31), "bytes": 6902}]
        if "util.is_admin" in sql:
            return [
                {
                    "admin": self.admin,
                    "pii": self.pii,
                    "compensation": self.compensation,
                    "health": self.health,
                }
            ]
        if "from app.payroll_period" in sql:
            return [{"ends_on": None}]
        if "left join lateral" in sql:
            return [] if not self.existe else [self._linha_lista()]
        if "left join app.company c" in sql:
            return [dict(self.pessoa)] if self.existe else []
        if "p.ctps" in sql and "from app.employee e" in sql:
            return (
                [
                    {
                        "employee_id": ANA,
                        "registration_number": "1001",
                        "name": "Ana Personagem",
                        "hr_code": "RH-01",
                        "employment_type": "clt",
                        "cargo": "Operadora",
                        "ctps": None,
                    }
                ]
                if self.existe
                else []
            )
        if "where e.hr_code is not null" in sql:
            return [{"employee_id": eid, "hr_code": code} for code, eid in self.hr_codes.items()]
        if "from app.employee_position p" in sql and "effective_to is null" in sql:
            return [{"effective_from": self.open_position}] if self.open_position else []
        if "from app.employee_position p" in sql:
            return [
                {
                    "effective_from": date(2024, 3, 1),
                    "effective_to": None,
                    "cargo": "Operadora",
                    "unit_name": "Shopping Norte",
                }
            ]
        if "from app.employee_compensation r" in sql and "effective_to is null" in sql:
            return [{"effective_from": self.open_compensation}] if self.open_compensation else []
        if "from app.employee_compensation r" in sql:
            return [
                {
                    "effective_from": date(2026, 1, 1),
                    "effective_to": None,
                    "salary": Decimal("2500.00"),
                    "reason": "admissão",
                }
            ]
        if "from app.employee_pii p" in sql:
            return [
                {
                    "cpf": "000.000.001-91",
                    "rg": None,
                    "pis": None,
                    "ctps": None,
                    "birth_date": date(1990, 5, 2),
                    "mother_name": "Mãe Personagem",
                    "father_name": None,
                    "phone": None,
                    "personal_email": None,
                }
            ]
        if "from app.document doc" in sql:
            return [
                {
                    "type_name": "CNH",
                    "issued_on": date(2020, 1, 10),
                    "valid_until": date(2026, 9, 10),
                    "status": "active",
                }
            ]
        if "from app.occupational_exam x" in sql:
            return [
                {
                    "type": "periodic",
                    "performed_on": date(2025, 9, 1),
                    "valid_until": date(2026, 9, 1),
                    "result": "fit",
                }
            ]
        if "from app.leave_period l" in sql:
            return [
                {
                    "category": "vacation",
                    "start_date": date(2026, 2, 1),
                    "end_date": date(2026, 2, 20),
                    "source": "secullum",
                }
            ]
        if "from app.workforce_movement m" in sql:
            return [
                {
                    "type": "transfer",
                    "event_date": date(2025, 6, 1),
                    "notes": None,
                    "unit_name": "Shopping Norte",
                }
            ]
        if "from app.financial_agreement a" in sql:
            return [
                {
                    "id": uuid4(),
                    "type": "vehicle_damage",
                    "description": "Retrovisor",
                    "total_amount": Decimal("1200.00"),
                    "installment_count": 3,
                    "agreement_date": date(2026, 1, 15),
                    "status": "active",
                    "pending_installments": 2,
                }
            ]
        if "insert into app.audit_log" in sql:
            self.audit.append(params)
            return []
        if "insert into app.employee_compensation" in sql:
            return [{"id": uuid4()}]
        if "insert into app.employee_position" in sql:
            return [{"id": uuid4()}]
        if "update app.employee set" in sql or "insert into app.employee_pii" in sql:
            return [{"id": ANA}]
        return []

    def _linha_lista(self) -> dict[str, Any]:
        return {
            "employee_id": ANA,
            "name": "Ana Personagem",
            "registration_number": "1001",
            "hr_code": "RH-01",
            "cargo": "Operadora",
            "status": "active",
            "hired_on": date(2024, 3, 1),
            "unit_id": UNIDADE,
            "unit_name": "Shopping Norte",
            "due_kind": "aso",
            "due_label": "ASO",
            "due_on": date(2026, 9, 1),
        }

    def escritas(self) -> list[str]:
        return [
            sql
            for sql, _ in self.statements
            if sql.startswith(("update app.employee", "insert into app.employee"))
        ]


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch):
    def instalar(**kwargs: Any) -> FakeDB:
        estado = FakeDB(**kwargs)
        for modulo in (repo, repository, foto_mod):
            monkeypatch.setattr(
                modulo,
                "tenant_scope",
                lambda context, schema="app": FakeScope(FakeCursor(estado, context, True)),
                raising=False,
            )
            monkeypatch.setattr(
                modulo,
                "user_scope",
                lambda context, schema="app": FakeScope(FakeCursor(estado, context, False)),
                raising=False,
            )
        return estado

    return instalar


def auth(issue_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token()}"}


# ---------------------------------------------------------------------------
# Lista
# ---------------------------------------------------------------------------
def test_a_lista_traz_o_prazo_mais_urgente_de_cada_pessoa(client: TestClient, issue_token, db):
    db()
    resposta = client.get("/rh/employees", headers=auth(issue_token))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["can_write"] is True
    assert corpo["truncated"] is False
    assert corpo["rows"][0]["due"] == {
        "kind": "aso",
        "label": "ASO",
        "due_on": "2026-09-01",
    }


def test_quem_nao_escreve_recebe_a_lista_dizendo_isso(client: TestClient, issue_token, db):
    db(admin=False)

    assert client.get("/rh/employees", headers=auth(issue_token)).json()["can_write"] is False


def test_filtro_fora_do_catalogo_e_recusado_com_a_lista_junto(client: TestClient, issue_token, db):
    db()
    resposta = client.get("/rh/employees?status=demitido", headers=auth(issue_token))

    assert resposta.status_code == 422
    assert "desligado" in resposta.json()["detail"]


def test_pendencia_desconhecida_e_recusada(client: TestClient, issue_token, db):
    db()

    resposta = client.get("/rh/employees?pendencia=uniforme", headers=auth(issue_token))

    assert resposta.status_code == 422


# ---------------------------------------------------------------------------
# Detalhe — a ausência é o produto
# ---------------------------------------------------------------------------
def test_sem_o_dominio_o_bloco_vem_ausente_e_nao_vazio(client: TestClient, issue_token, db):
    db(compensation=False, health=False)
    corpo = client.get(f"/rh/employees/{ANA}", headers=auth(issue_token)).json()

    # `None` e não `[]`: a tela não renderiza a aba, em vez de renderizar uma aba
    # vazia que anuncia a existência do dado.
    assert corpo["compensation"] is None
    assert corpo["agreements"] is None
    assert corpo["exams"] is None
    # PII continua, porque o domínio de PII continua.
    assert corpo["pii"]["cpf"] == "000.000.001-91"
    assert corpo["documents"][0]["type_name"] == "CNH"


def test_com_o_dominio_o_bloco_vem_mesmo_que_vazio(client: TestClient, issue_token, db):
    db()
    corpo = client.get(f"/rh/employees/{ANA}", headers=auth(issue_token)).json()

    assert corpo["compensation"][0]["salary"] == "2500.00"
    assert corpo["agreements"][0]["pending_installments"] == 2
    assert corpo["exams"][0]["result"] == "fit"


def test_o_bloco_do_sync_cita_a_coluna_de_onde_o_valor_vem(client: TestClient, issue_token, db):
    db()
    corpo = client.get(f"/rh/employees/{ANA}", headers=auth(issue_token)).json()
    campos = {campo["column"]: campo for campo in corpo["sync_fields"]}

    assert campos["name"]["mirror"] == "Funcionario.Nome"
    assert campos["name"]["value"] == "Ana Personagem"
    # O uuid da unidade não informa ninguém: o bloco mostra o nome resolvido.
    assert campos["unit_id"]["value"] == "Shopping Norte"
    # Os três pendentes ficam marcados em vez de afirmarem uma origem que
    # ninguém confirmou.
    assert campos["manager_employee_id"]["pending"] is True
    assert campos["terminated_on"]["pending"] is True


def test_quem_nao_escreve_nao_recebe_campo_editavel(client: TestClient, issue_token, db):
    db(admin=False)
    corpo = client.get(f"/rh/employees/{ANA}", headers=auth(issue_token)).json()

    assert corpo["can_write"] is False
    assert corpo["editable_fields"] == []


def test_sem_o_dominio_de_pii_a_ctps_sai_da_lista_de_editaveis(client: TestClient, issue_token, db):
    db(pii=False)
    corpo = client.get(f"/rh/employees/{ANA}", headers=auth(issue_token)).json()

    assert "ctps" not in corpo["editable_fields"]
    assert "hr_code" in corpo["editable_fields"]


def test_pessoa_fora_do_alcance_responde_o_mesmo_que_inexistente(
    client: TestClient, issue_token, db
):
    db(existe=False)

    assert client.get(f"/rh/employees/{ANA}", headers=auth(issue_token)).status_code == 404


# ---------------------------------------------------------------------------
# Formulário — recusa o que a planilha recusaria
# ---------------------------------------------------------------------------
def test_campo_do_sync_no_corpo_derruba_o_pedido_inteiro(client: TestClient, issue_token, db):
    estado = db()
    resposta = client.patch(
        f"/rh/employees/{ANA}", json={"name": "Ana P."}, headers=auth(issue_token)
    )

    # 422 do próprio pydantic: `extra="forbid"`. Ignorar a chave em silêncio
    # devolveria 204 e o usuário concluiria que gravou.
    assert resposta.status_code == 422
    assert estado.escritas() == []


def test_regime_fora_do_catalogo_e_recusado_com_os_valores_aceitos(
    client: TestClient, issue_token, db
):
    db()
    resposta = client.patch(
        f"/rh/employees/{ANA}", json={"employment_type": "efetivo"}, headers=auth(issue_token)
    )

    assert resposta.status_code == 422
    assert "clt" in resposta.json()["detail"]


def test_id_rh_de_outra_pessoa_e_recusado_no_formulario_como_no_import(
    client: TestClient, issue_token, db
):
    db()
    resposta = client.patch(
        f"/rh/employees/{ANA}", json={"hr_code": "RH-02"}, headers=auth(issue_token)
    )

    assert resposta.status_code == 422
    assert "já pertence a outro colaborador" in resposta.json()["detail"]


def test_quem_nao_e_do_dp_nao_edita(client: TestClient, issue_token, db):
    estado = db(admin=False)
    resposta = client.patch(
        f"/rh/employees/{ANA}", json={"hr_code": "RH-09"}, headers=auth(issue_token)
    )

    assert resposta.status_code == 403
    assert estado.escritas() == []


def test_sem_o_dominio_de_pii_ninguem_escreve_ctps(client: TestClient, issue_token, db):
    estado = db(pii=False)
    resposta = client.patch(
        f"/rh/employees/{ANA}", json={"ctps": "123456"}, headers=auth(issue_token)
    )

    assert resposta.status_code == 403
    assert estado.escritas() == []


def test_valor_igual_ao_que_esta_gravado_nao_escreve_nem_audita(
    client: TestClient, issue_token, db
):
    estado = db()
    resposta = client.patch(
        f"/rh/employees/{ANA}", json={"hr_code": "RH-01"}, headers=auth(issue_token)
    )

    assert resposta.status_code == 204
    assert estado.escritas() == []
    assert estado.audit == []


def test_a_edicao_grava_e_audita_com_a_origem(client: TestClient, issue_token, db):
    estado = db()
    resposta = client.patch(
        f"/rh/employees/{ANA}",
        json={"hr_code": "RH-09", "employment_type": "pj"},
        headers=auth(issue_token),
    )

    assert resposta.status_code == 204
    assert len(estado.audit) == 1
    registro = estado.audit[0]
    assert registro["action"] == "update"
    assert registro["depois"].obj["_origem"] == {"form": "rh_colaboradores"}
    assert registro["antes"].obj["hr_code"] == "RH-01"


# ---------------------------------------------------------------------------
# Vigências — corrigir é revogar e criar
# ---------------------------------------------------------------------------
def test_vigencia_de_salario_na_mesma_data_da_vigente_e_recusada(
    client: TestClient, issue_token, db
):
    estado = db()
    resposta = client.post(
        f"/rh/employees/{ANA}/compensation",
        json={"effective_from": "2026-01-01", "salary": "3000.00"},
        headers=auth(issue_token),
    )

    assert resposta.status_code == 422
    assert "revogue" in resposta.json()["detail"]
    assert estado.escritas() == []


def test_vigencia_de_salario_fecha_a_anterior_e_abre_a_proxima(client: TestClient, issue_token, db):
    estado = db()
    resposta = client.post(
        f"/rh/employees/{ANA}/compensation",
        json={"effective_from": "2026-08-01", "salary": "3000.00", "reason": "promoção"},
        headers=auth(issue_token),
    )

    assert resposta.status_code == 201
    escritas = estado.escritas()
    assert any(sql.startswith("update app.employee_compensation") for sql in escritas)
    assert any(sql.startswith("insert into app.employee_compensation") for sql in escritas)
    assert estado.audit[0]["action"] == "insert"


def test_sem_o_dominio_de_remuneracao_nao_se_cria_vigencia(client: TestClient, issue_token, db):
    estado = db(compensation=False)
    resposta = client.post(
        f"/rh/employees/{ANA}/compensation",
        json={"effective_from": "2026-08-01", "salary": "3000.00"},
        headers=auth(issue_token),
    )

    assert resposta.status_code == 403
    assert estado.escritas() == []


def test_vigencia_de_cargo_move_o_cargo_corrente_junto(client: TestClient, issue_token, db):
    estado = db()
    resposta = client.post(
        f"/rh/employees/{ANA}/position",
        json={"effective_from": "2026-08-01", "cargo": "Supervisora"},
        headers=auth(issue_token),
    )

    assert resposta.status_code == 201
    escritas = estado.escritas()
    # A vigência é quem manda, mas `employee.cargo` é o valor corrente: sem esta
    # segunda escrita a lista continuaria mostrando "Operadora".
    assert any(sql.startswith("update app.employee set cargo") for sql in escritas)
    assert any(sql.startswith("insert into app.employee_position") for sql in escritas)


def test_vigencia_de_cargo_no_futuro_e_recusada(client: TestClient, issue_token, db):
    estado = db()
    resposta = client.post(
        f"/rh/employees/{ANA}/position",
        json={"effective_from": "2099-01-01", "cargo": "Supervisora"},
        headers=auth(issue_token),
    )

    assert resposta.status_code == 422
    assert estado.escritas() == []


# ---------------------------------------------------------------------------
# Foto do colaborador — docs/DECISAO-FOTO-DO-COLABORADOR.md
#
# A forma da decisão é estreita, e cada teste abaixo guarda uma cláusula dela.
# ---------------------------------------------------------------------------
def test_a_foto_sai_como_imagem_e_nao_como_json(client: TestClient, issue_token, db):
    """O positivo: quem tem `pii` recebe a imagem, com o mime da origem."""
    db(pii=True)
    r = client.get(f"/rh/employees/{ANA}/foto", headers=auth(issue_token))

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")
    assert r.content.startswith(b"\xff\xd8\xff")


def test_sem_o_dominio_pii_a_foto_e_recusada(client: TestClient, issue_token, db):
    """O negativo, que só vale ao lado do positivo acima."""
    db(pii=False)
    r = client.get(f"/rh/employees/{ANA}/foto", headers=auth(issue_token))
    assert r.status_code == 403


def test_pessoa_fora_de_alcance_recebe_404_e_nao_403(client: TestClient, issue_token, db):
    """Um 403 aqui confirmaria que a pessoa existe noutra unidade."""
    db(existe=False)
    r = client.get(f"/rh/employees/{ANA}/foto", headers=auth(issue_token))
    assert r.status_code == 404


def test_a_resposta_da_foto_nao_entra_em_cache_compartilhado(client: TestClient, issue_token, db):
    """Sem URL pública e sem link que sobreviva à sessão — §5 da decisão."""
    db(pii=True)
    r = client.get(f"/rh/employees/{ANA}/foto", headers=auth(issue_token))
    assert "no-store" in r.headers["cache-control"]
    assert "private" in r.headers["cache-control"]


def test_a_ficha_distingue_sem_foto_de_sem_foto_ainda(client: TestClient, issue_token, db):
    """Três estados, não dois: vazio sem explicação parece defeito (§6)."""
    db(foto="ausente")
    ausente = client.get(f"/rh/employees/{ANA}", headers=auth(issue_token)).json()["photo"]
    assert ausente["state"] == "ausente"
    assert ausente["origin"] is None
    # Só aqui a tela oferece envio: a origem declarou não ter, então as duas
    # fontes não podem se sobrepor (§4-ter).
    assert ausente["can_upload"] is True

    db(foto="pendente")
    pendente = client.get(f"/rh/employees/{ANA}", headers=auth(issue_token)).json()["photo"]
    assert pendente["state"] == "pendente"
    # ⛔ PENDENTE não aceita envio: a origem vai preencher sozinha, e aceitar aqui
    # criaria a sobreposição que a precedência existe para não ter de arbitrar.
    assert pendente["can_upload"] is False

    db(foto="disponivel")
    disponivel = client.get(f"/rh/employees/{ANA}", headers=auth(issue_token)).json()["photo"]
    assert disponivel["state"] == "disponivel"
    assert disponivel["origin"] == "secullum"
    assert disponivel["can_upload"] is False
    # A idade do rosto é dado de tela: sem a data, não há como saber que o rosto
    # é de dois anos atrás — que numa ficha de identificação é pior que nenhum.
    assert disponivel["synced_at"] is not None


def test_sem_o_dominio_pii_a_ficha_nao_anuncia_que_ha_foto(client: TestClient, issue_token, db):
    """`null`, não `{"state": ...}`: a aba não existe no DOM."""
    db(pii=False)
    assert client.get(f"/rh/employees/{ANA}", headers=auth(issue_token)).json()["photo"] is None


def test_nenhuma_resposta_json_carrega_bytes_de_foto(client: TestClient, issue_token, db):
    """A varredura, não a leitura do serializer.

    ⛔ Procura o conteúdo no corpo da LISTA e da FICHA — as duas superfícies em
    que a foto nunca pode aparecer. 176 rostos numa listagem é exportação de
    biometria com outro nome (§5).
    """
    db(pii=True)
    for caminho in ("/rh/employees", f"/rh/employees/{ANA}"):
        bruto = client.get(caminho, headers=auth(issue_token)).text
        assert "data:image" not in bruto
        assert "/9j/" not in bruto  # JPEG em base64
        # ⚠️ A asserção anterior procurava `\\u00ff\\u00d8` e era INALCANÇÁVEL:
        # o FastAPI serializa com `ensure_ascii=False`, então o escape nunca
        # aparece no corpo. Uma linha verde que não vigiava nada — trocada pelas
        # duas formas que de fato escapavam da varredura, e que são exatamente o
        # que alguém escreve depois de bater no `PydanticSerializationError` de
        # `bytes` cru e querer "fazer serializar".
        assert JPEG_DE_MENTIRA.decode("latin-1") not in bruto
        assert JPEG_DE_MENTIRA.hex() not in bruto


# ---------------------------------------------------------------------------
# Imputação da foto — §4-ter. Cria dado biométrico; cada teste guarda uma trava.
# ---------------------------------------------------------------------------
PNG_DE_MENTIRA = b"\x89PNG\r\n\x1a\n-bytes-de-mentira"


def _enviar(client: TestClient, issue_token, conteudo: bytes, nome="foto.jpg"):
    return client.post(
        f"/rh/employees/{ANA}/foto",
        headers=auth(issue_token),
        files={"file": (nome, conteudo, "image/jpeg")},
    )


def test_o_dp_envia_foto_de_quem_a_origem_diz_nao_ter(client: TestClient, issue_token, db):
    """O positivo: `PossuiFoto = false` é exatamente onde a imputação existe."""
    db(foto="ausente")
    r = _enviar(client, issue_token, JPEG_DE_MENTIRA)

    assert r.status_code == 200, r.text
    assert r.json()["state"] in {"ausente", "disponivel"}


def test_nao_se_envia_foto_para_quem_a_origem_ja_tem(client: TestClient, issue_token, db):
    """A trava que faz as duas fontes não se sobreporem por construção."""
    db(foto="disponivel")
    r = _enviar(client, issue_token, JPEG_DE_MENTIRA)

    assert r.status_code == 422
    assert "sistema de ponto" in r.json()["detail"]


def test_nem_para_quem_esta_na_fila(client: TestClient, issue_token, db):
    """PENDENTE também recusa: a origem vai preencher sozinha."""
    db(foto="pendente")
    assert _enviar(client, issue_token, JPEG_DE_MENTIRA).status_code == 422


def test_o_mime_sai_dos_bytes_e_nao_do_que_o_cliente_declara(client: TestClient, issue_token, db):
    """Um `.jpg` que não é JPEG é recusado — magic number, não extensão."""
    db(foto="ausente")
    r = _enviar(client, issue_token, b"<?php system($_GET[0]); ?>", nome="foto.jpg")

    assert r.status_code == 422
    assert "JPEG ou PNG" in r.json()["detail"]


def test_png_tambem_entra(client: TestClient, issue_token, db):
    """O positivo do formato: a allowlist tem dois, não um."""
    db(foto="ausente")
    assert _enviar(client, issue_token, PNG_DE_MENTIRA).status_code == 200


def test_arquivo_grande_demais_e_recusado_com_mensagem(client: TestClient, issue_token, db):
    """Recusar antes do banco é a diferença entre uma mensagem e um 500."""
    db(foto="ausente")
    gigante = JPEG_DE_MENTIRA + b"\x00" * (5 * 1024 * 1024)
    r = _enviar(client, issue_token, gigante)

    assert r.status_code == 422
    assert "limite" in r.json()["detail"]


def test_sem_o_dominio_pii_nao_se_envia_foto(client: TestClient, issue_token, db):
    """Escrever biometria exige o mesmo domínio que lê — e mais: ser admin."""
    db(pii=False, foto="ausente")
    assert _enviar(client, issue_token, JPEG_DE_MENTIRA).status_code == 403


def test_quem_nao_escreve_cadastro_nao_envia_foto(client: TestClient, issue_token, db):
    db(admin=False, foto="ausente")
    assert _enviar(client, issue_token, JPEG_DE_MENTIRA).status_code == 403


def test_a_substituicao_pela_origem_aparece_na_ficha(client: TestClient, issue_token, db):
    """⛔ Nunca silenciosa: a ficha diz que houve troca, e de quando (§4-ter)."""
    estado = db(foto="disponivel")
    estado.foto_manual = {
        "uploaded_at": datetime(2026, 8, 20, 14, 0),
        "uploaded_by_name": "dp@fastpark.com.br",
        "bytes": 4096,
        "superseded_at": None,
    }
    corpo = client.get(f"/rh/employees/{ANA}", headers=auth(issue_token)).json()["photo"]

    # A origem venceu na exibição...
    assert corpo["origin"] == "secullum"
    # ...e a enviada NÃO sumiu: quem olha a ficha vê que houve substituição.
    assert corpo["superseded"]["uploaded_by_name"] == "dp@fastpark.com.br"
    assert corpo["superseded"]["uploaded_at"].startswith("2026-08-20")


def test_sem_foto_na_origem_a_enviada_e_a_que_aparece(client: TestClient, issue_token, db):
    """O outro lado da precedência: sem origem, a enviada é o rosto."""
    estado = db(foto="ausente")
    estado.foto_manual = {
        "uploaded_at": datetime(2026, 8, 20, 14, 0),
        "uploaded_by_name": "dp@fastpark.com.br",
        "bytes": 4096,
        "superseded_at": None,
    }
    corpo = client.get(f"/rh/employees/{ANA}", headers=auth(issue_token)).json()["photo"]

    assert corpo["origin"] == "manual"
    assert corpo["state"] == "disponivel"
    # Já há uma enviada ativa: a tela não oferece enviar outra por cima.
    assert corpo["can_upload"] is False
