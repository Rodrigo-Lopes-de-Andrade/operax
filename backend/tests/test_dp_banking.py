"""Conta bancária: o que a resposta NÃO contém, e o que a rota pergunta antes de gravar.

O gate desta sprint tem um item que não se cumpre relendo o código: *nenhuma
resposta de rota contém `account` fora de máscara*. Então o teste **varre o
corpo bruto** — `response.text`, antes de virar dict — procurando o número que
foi enviado. Revisão de código vê o `mask_account` na linha de cima; a varredura
vê o que saiu pelo socket, que é o que a regra 10 do `PRD-DP.md` fala.

⚠️ O QUE ESTES TESTES **NÃO** COBREM: A MATRIZ DE PAPÉIS
Não há `hr` nem `personnel` aqui. O token do `conftest` é `unit_supervisor`
sempre, e `util.can_see_domain` e `util.is_admin` estão inteiramente falsificados
pelo `FakeDB` — quem responde os dois eixos é um booleano do fixture, não o
banco. O que se prova aqui é o **comportamento da rota** diante de cada resposta
possível do banco: com domínio e admin ela grava e devolve máscara, sem qualquer
um dos dois ela recusa com 403 e não abre a transação de escrita.

Quem prova que `accounting` tem `banking` e que `hr` não, e que a policy de
escrita exige `util.is_admin`, é `scripts/98_teste_isolamento_tenant.sql`, contra
Postgres de verdade. Esta suíte não substitui aquela e não tenta.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from operax.core.tenant import bind_tenant
from operax.dp import banking
from operax.dp.banking import mask_account

ANA = UUID("aaaa0000-0000-4000-8000-000000000001")

#: O número que não pode aparecer em lugar nenhum da resposta.
CONTA = "9876543210"
GRAVADA = "2233445566"


def payload(**overrides: Any) -> dict[str, Any]:
    return {
        "bank_code": "341",
        "branch": "1234",
        "account": CONTA,
        "account_type": "checking",
    } | overrides


class FakeCursor:
    """Cursor de mentira endereçado por trecho de statement.

    Nas escritas ele roda `bind_tenant` de verdade: um `upsert` sem filtro de
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
        self, *, banking_domain: bool = True, admin: bool = True, existe: bool = True
    ) -> None:
        self.banking = banking_domain
        self.admin = admin
        self.existe = existe
        #: A linha de `app.employee_bank_account`, quando alguém gravou.
        self.conta: dict[str, Any] | None = None
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.audit: list[dict[str, Any]] = []

    def responder(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if "util.can_see_domain" in sql:
            # Os dois eixos que não dependem da pessoa saem da mesma pergunta, como
            # no módulo: `banking` decide quem lê, `admin` decide quem grava.
            assert "util.is_admin" in sql, "a rota deixou de perguntar o papel ao banco"
            return [{"banking": self.banking, "admin": self.admin}]
        if "from app.employee e" in sql:
            # A RLS é quem decide: pessoa fora de alcance devolve vazio, e a rota
            # transforma em 404 sem revelar que ela existe noutra unidade.
            return [{"id": ANA}] if self.existe else []
        if "insert into app.employee_bank_account" in sql:
            # O fake MODELA a gravação: sem isto a leitura seguinte não muda, e um
            # teste que só confere o 200 não distingue "gravou" de "respondeu".
            self.conta = {
                "employee_id": params["employee_id"],
                "bank_code": params["bank_code"],
                "branch": params["branch"],
                "account": params["account"],
                "account_type": params["account_type"],
                "holder_document": params["holder_document"],
                "updated_at": datetime(2026, 9, 5, 12, 0),
            }
            return [dict(self.conta)]
        if "from app.employee_bank_account a" in sql:
            return [dict(self.conta)] if self.conta else []
        if "insert into app.audit_log" in sql:
            self.audit.append(dict(params))
            return []
        raise AssertionError(f"statement inesperado: {sql}")


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    estado = FakeDB()

    def tenant_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursor(estado, context, checar_tenant=True))

    def user_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursor(estado, context, checar_tenant=False))

    monkeypatch.setattr(banking, "tenant_scope", tenant_scope)
    monkeypatch.setattr(banking, "user_scope", user_scope)
    return estado


# ---------------------------------------------------------------------------
# A máscara
# ---------------------------------------------------------------------------
def test_mascara_mostra_so_a_cauda() -> None:
    assert mask_account("9876543210") == "•••• 3210"


def test_mascara_conta_curta_esconde_tudo() -> None:
    """Devolver o número inteiro porque ele é curto é a máscara falhando onde ela
    é a única proteção."""
    assert mask_account("321") == "••••"
    assert mask_account("4321") == "••••"


def test_conta_mascarada_nao_tem_campo_para_o_numero() -> None:
    """Regra 10 por construção: o tipo que sai do módulo não carrega a conta."""
    campos = banking.MaskedBankAccount.__dataclass_fields__
    assert "account" not in campos
    assert "account_masked" in campos


# ---------------------------------------------------------------------------
# A rota
# ---------------------------------------------------------------------------
def test_grava_e_devolve_mascarado(client: TestClient, issue_token: Any, fake_db: FakeDB) -> None:
    resposta = client.patch(
        f"/dp/colaboradores/{ANA}/conta",
        json=payload(),
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["account_masked"] == "•••• 3210"
    assert corpo["bank_code"] == "341"
    assert "account" not in corpo
    # E gravou de fato — o positivo do gate. Sem ele, "não vaza" ficaria verde
    # numa rota que não respondeu nada.
    assert fake_db.conta is not None
    assert fake_db.conta["account"] == CONTA


def test_nenhuma_resposta_contem_a_conta_fora_de_mascara(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """A varredura. Não olha o código: olha o corpo que saiu pelo socket."""
    resposta = client.patch(
        f"/dp/colaboradores/{ANA}/conta",
        json=payload(account=GRAVADA, holder_document="00000000191"),
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert resposta.status_code == 200
    assert GRAVADA not in resposta.text
    assert GRAVADA[:-4] not in resposta.text
    assert "•••• 5566" in resposta.text


def test_trilha_de_auditoria_tambem_e_mascarada(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """`app.audit_log` é lido por outras telas: o número ali seria a segunda cópia."""
    client.patch(
        f"/dp/colaboradores/{ANA}/conta",
        json=payload(),
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert len(fake_db.audit) == 1
    linha = fake_db.audit[0]
    assert linha["action"] == "insert"
    assert linha["antes"].obj is None
    depois = linha["depois"].obj
    assert depois["account"] == "•••• 3210"
    assert CONTA not in repr(depois)


def test_segunda_gravacao_audita_como_update(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    cabecalho = {"Authorization": f"Bearer {issue_token()}"}
    client.patch(f"/dp/colaboradores/{ANA}/conta", json=payload(), headers=cabecalho)
    client.patch(f"/dp/colaboradores/{ANA}/conta", json=payload(account=GRAVADA), headers=cabecalho)

    assert [linha["action"] for linha in fake_db.audit] == ["insert", "update"]
    # O `antes` guarda a conta anterior, e guarda mascarada — a trilha diz que
    # mudou e de quê, sem virar um segundo lugar onde o número existe.
    segunda = fake_db.audit[1]
    assert segunda["antes"].obj["account"] == "•••• 3210"
    assert segunda["depois"].obj["account"] == "•••• 5566"
    assert CONTA not in repr(segunda["antes"].obj)
    assert GRAVADA not in repr(segunda["depois"].obj)


def test_sem_o_dominio_banking_a_rota_recusa(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """O banco diz que o papel não alcança `banking` — no produto, o caso é o `hr`."""
    fake_db.banking = False

    resposta = client.patch(
        f"/dp/colaboradores/{ANA}/conta",
        json=payload(),
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert resposta.status_code == 403
    assert CONTA not in resposta.text
    # E nada foi gravado: a recusa acontece antes de a transação de escrita abrir.
    assert fake_db.conta is None
    assert fake_db.audit == []


def test_com_o_dominio_mas_sem_ser_admin_a_rota_recusa(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """O terceiro eixo, e é o `accounting` que ele separa.

    Ele tem `banking` — concilia a remessa — e não é admin. Sem esta recusa, seria
    o único papel do produto a gravar dado sensível sem ser admin.
    """
    fake_db.admin = False

    resposta = client.patch(
        f"/dp/colaboradores/{ANA}/conta",
        json=payload(),
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert resposta.status_code == 403
    assert CONTA not in resposta.text
    assert fake_db.conta is None
    assert fake_db.audit == []
    # E a recusa acontece antes de a pessoa ser resolvida: quem não pode gravar não
    # descobre pela rota que o colaborador existe.
    assert not any("from app.employee e" in sql for sql, _ in fake_db.statements)


def test_pessoa_fora_de_alcance_responde_404(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    fake_db.existe = False

    resposta = client.patch(
        f"/dp/colaboradores/{ANA}/conta",
        json=payload(),
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert resposta.status_code == 404
    assert CONTA not in resposta.text
    assert fake_db.conta is None


def test_tipo_de_conta_fora_da_lista_e_recusado(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    resposta = client.patch(
        f"/dp/colaboradores/{ANA}/conta",
        json=payload(account_type="poupanca"),
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert resposta.status_code == 422
    assert fake_db.conta is None


def test_campo_desconhecido_e_recusado(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    resposta = client.patch(
        f"/dp/colaboradores/{ANA}/conta",
        json=payload(pix="a@b.c"),
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert resposta.status_code == 422


def test_conta_em_branco_e_recusada(client: TestClient, issue_token: Any, fake_db: FakeDB) -> None:
    resposta = client.patch(
        f"/dp/colaboradores/{ANA}/conta",
        json=payload(account="   "),
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert resposta.status_code == 422
    assert fake_db.conta is None


def test_sem_token_nao_chega_ao_banco(client: TestClient, fake_db: FakeDB) -> None:
    resposta = client.patch(f"/dp/colaboradores/{ANA}/conta", json=payload())

    assert resposta.status_code == 401
    assert fake_db.statements == []
