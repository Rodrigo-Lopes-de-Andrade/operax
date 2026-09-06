"""Varredura do gate do S3 — a conta bancária em TODA rota de `/dp`, não em três.

⛔ POR QUE ESTE ARQUIVO EXISTE AO LADO DE `test_dp_ciclo.py`
`test_nenhuma_resposta_json_de_dp_contem_a_conta` varre TRÊS respostas (apurar,
gerar, catálogo). O router tem ONZE rotas, e a que ficou de fora é a única que
recebe o número inteiro no corpo do pedido: `PATCH /dp/colaboradores/{id}/conta`.
Uma varredura que pula a rota que escreve o dado não é varredura.

⚠️ E ELA FICOU DE FORA POR UM MOTIVO MEDIDO, não por esquecimento: o `FakeDB`
não modela RLS, e essa rota depende dela (`resolve_employee` roda sob
`user_scope` sem `tenant_id` ligado, porque quem filtra é a policy). Então a
cobertura dela aqui é ESTRUTURAL — o contrato de resposta de toda rota do
router é varrido por reflexão, que é o que fecha o caminho para a rota que o
fake não alcança.
"""

from __future__ import annotations

import json
from typing import Any, get_args, get_origin

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

from operax.dp import banking, beneficios, ciclo, postos
from operax.rh import repository as rh_repository
from server.routers.dp import router as dp_router
from tests.test_dp_ciclo import (
    ANO,
    CONTA,
    MES,
    FakeCursor,
    FakeDB,
    FakeScope,
    apurar,
    apurar_e_gerar,
    cabecalho,
    cenario_remessa,
)


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    """Mesma montagem do `fake_db` de `test_dp_ciclo.py` — a fixture é local lá."""
    estado = FakeDB()

    def tenant_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursor(estado, context, checar_tenant=True))

    def user_scope(context: Any, schema: str = "app") -> FakeScope:
        return FakeScope(FakeCursor(estado, context, checar_tenant=False))

    monkeypatch.setattr(ciclo, "tenant_scope", tenant_scope)
    monkeypatch.setattr(beneficios, "tenant_scope", tenant_scope)
    monkeypatch.setattr(banking, "tenant_scope", tenant_scope)
    monkeypatch.setattr(banking, "user_scope", user_scope)
    monkeypatch.setattr(postos, "tenant_scope", tenant_scope)
    monkeypatch.setattr(postos, "user_scope", user_scope)
    monkeypatch.setattr(rh_repository, "user_scope", user_scope)
    monkeypatch.setattr("server.routers.dp.tenant_scope", tenant_scope)
    return estado


# ---------------------------------------------------------------------------
# 1. Varredura ESTRUTURAL: nenhum contrato de resposta do router tem `account`
# ---------------------------------------------------------------------------
def _campos_recursivos(modelo: type[BaseModel], vistos: set[type] | None = None) -> set[str]:
    """Todo nome de campo alcançável a partir de um modelo de resposta."""
    vistos = vistos if vistos is not None else set()
    if modelo in vistos or not (isinstance(modelo, type) and issubclass(modelo, BaseModel)):
        return set()
    vistos.add(modelo)
    nomes: set[str] = set()
    for nome, campo in modelo.model_fields.items():
        nomes.add(nome)
        anot = campo.annotation
        for candidato in (anot, *get_args(anot)):
            if isinstance(candidato, type) and issubclass(candidato, BaseModel):
                nomes |= _campos_recursivos(candidato, vistos)
            for interno in get_args(candidato) if get_origin(candidato) else ():
                if isinstance(interno, type) and issubclass(interno, BaseModel):
                    nomes |= _campos_recursivos(interno, vistos)
    return nomes


def test_nenhum_contrato_de_resposta_de_dp_tem_campo_account() -> None:
    """⛔ A rota que o fake não alcança é fechada AQUI.

    Se nenhum modelo de resposta do router tem campo `account`, então nenhuma
    rota do router pode devolver o número — inclusive a que o recebe no corpo.
    """
    achados: dict[str, set[str]] = {}
    for rota in dp_router.routes:
        if not isinstance(rota, APIRoute) or rota.response_model is None:
            continue
        campos = _campos_recursivos(rota.response_model)
        if "account" in campos:
            achados[f"{sorted(rota.methods)} {rota.path}"] = campos
    assert not achados, f"⛔ campo `account` cru em contrato de resposta: {achados}"


def test_toda_rota_de_dp_ou_declara_response_model_ou_devolve_bytes() -> None:
    """Sem esta linha, a varredura acima ficaria verde por rota SEM contrato."""
    sem_contrato = [
        f"{sorted(r.methods)} {r.path}"
        for r in dp_router.routes
        if isinstance(r, APIRoute) and r.response_model is None
    ]
    # A única sem contrato é o export, que devolve `Response` (bytes) de propósito.
    assert sem_contrato == ["['GET'] /dp/ciclos/{cycle_id}/export"], (
        f"rota nova sem contrato de resposta: {sem_contrato}"
    )


# ---------------------------------------------------------------------------
# 2. Varredura EXERCIDA: o JSON literal das rotas que o fake alcança
# ---------------------------------------------------------------------------
def _respostas_exercidas(client: TestClient, issue_token: Any) -> list[Any]:
    cab = cabecalho(issue_token)
    ciclo_id = apurar_e_gerar(client, issue_token)

    # A remessa roda ANTES da varredura: o número passa pela memória do processo
    # com o ciclo já congelado, que é o instante em que um eco apareceria.
    remessa = client.get(f"/dp/ciclos/{ciclo_id}/export?formato=banco", headers=cab)
    assert remessa.status_code == 200, remessa.text
    assert CONTA.encode() in remessa.content, "a remessa precisa carregar a conta"

    # ⚠️ `/dp/postos` fica de fora DESTA lista (e só desta): o `FakeDB` do S3 não
    # modela `select u.id from app.unit`. Quem a cobre é a varredura estrutural
    # acima, que não depende de fake nenhum.
    return [
        client.get("/dp/beneficios/catalogo", headers=cab),
        client.post(f"/dp/ciclos/{ciclo_id}/gerar", headers=cab),
        client.post(
            "/dp/ciclos",
            json={"kind": "transport_voucher", "period_year": ANO, "period_month": MES},
            headers=cab,
        ),
        client.get(f"/dp/ciclos/{ciclo_id}/export?formato=xlsx", headers=cab),
        client.get(f"/dp/ciclos/{ciclo_id}/export?formato=pdf", headers=cab),
    ]


def test_a_conta_nao_sai_em_nenhuma_resposta_exercida(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    cenario_remessa(fake_db)
    for resposta in _respostas_exercidas(client, issue_token):
        rota = resposta.request.url
        assert CONTA.encode() not in resposta.content, f"⛔ a conta vazou em {rota}"


def test_nenhuma_chave_account_crua_no_json_exercido(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    cenario_remessa(fake_db)
    for resposta in _respostas_exercidas(client, issue_token):
        tipo = resposta.headers.get("content-type", "")
        if "json" not in tipo:
            continue
        corpo = json.dumps(resposta.json())
        assert '"account"' not in corpo, f"⛔ chave `account` crua em {resposta.request.url}"


# ---------------------------------------------------------------------------
# 3. Os canais laterais: header, nome de arquivo, mensagem de erro
# ---------------------------------------------------------------------------
def test_a_conta_nao_vaza_por_header_nem_pelo_nome_do_arquivo(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """`Content-Disposition` é cabeçalho: ele vai para o log do proxy."""
    cenario_remessa(fake_db)
    ciclo_id = apurar_e_gerar(client, issue_token)
    resposta = client.get(
        f"/dp/ciclos/{ciclo_id}/export?formato=banco", headers=cabecalho(issue_token)
    )
    assert resposta.status_code == 200
    for nome, valor in resposta.headers.items():
        assert CONTA not in valor, f"⛔ a conta vazou no header {nome}: {valor}"


def test_a_conta_nao_vaza_por_mensagem_de_erro_da_remessa(
    client: TestClient, issue_token: Any, fake_db: FakeDB
) -> None:
    """A recusa de rascunho é a mensagem que mais anda — ela não carrega o número."""
    cenario_remessa(fake_db)
    ciclo_id = apurar(client, issue_token).json()["id"]
    resposta = client.get(
        f"/dp/ciclos/{ciclo_id}/export?formato=banco", headers=cabecalho(issue_token)
    )
    assert resposta.status_code == 409, resposta.text
    assert CONTA not in resposta.text, f"⛔ a conta vazou na recusa: {resposta.text}"


def test_a_mascara_nunca_devolve_o_numero_inteiro() -> None:
    """A máscara, no número deste cenário e nos curtos que dado real não tem."""
    assert CONTA not in banking.mask_account(CONTA)
    assert banking.mask_account(CONTA).endswith(CONTA[-4:])
    for curta in ("1", "12", "123", "1234"):
        assert curta not in banking.mask_account(curta), f"conta curta {curta} vazou inteira"
