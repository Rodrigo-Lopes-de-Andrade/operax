"""O turno do assistente e o contrato SSE.

O que estes testes cercam não é "o modelo respondeu bem" — isso não é testável e
não é o ponto. É o que acontece **em volta** da resposta: que a métrica anunciada
seja a que rodou, que uma recusa encerre o turno em vez de virar uma segunda
tentativa paga, que uma falha do provider chegue como evento e não como stack
trace no meio de um `text/event-stream`, e que a linha de custo seja gravada nos
três finais possíveis.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from operax.agente import agente, catalogo, executor
from operax.agente.agente import Event, Record, Turn
from operax.core.tenant import TenantContext, UserRole
from server.routers import assistente
from tests.fixtures.fake_llm import FakeChatModel

TENANT = TenantContext(
    tenant_id=UUID("22222222-2222-4222-8222-222222222222"),
    user_id=UUID("11111111-1111-4111-8111-111111111111"),
    role=UserRole.UNIT_SUPERVISOR,
)
UNIDADE = UUID("33333333-3333-4333-8333-333333333333")

CATALOGO_ROWS: list[dict[str, Any]] = [
    {
        "code": "deviations_total",
        "title": "Total de desvios no período",
        "description": "Contagem de ocorrências ativas",
        "target_view": "fn_kpi_period",
        "dimensions": ["unit", "company"],
        "filters": ["start_date", "end_date"],
        "domain": None,
    },
    {
        "code": "ranking_by_unit",
        "title": "Ranking de desvios por unidade",
        "description": "Unidades ordenadas por ocorrências",
        "target_view": "fn_ranking_by_unit",
        "dimensions": ["unit"],
        "filters": ["start_date", "end_date"],
        "domain": None,
    },
    {
        "code": "payroll_summary",
        "title": "Resumo da folha por competência",
        "description": "Valor total",
        "target_view": "vw_payroll_summary",
        "dimensions": ["company", "unit", "payroll_period"],
        "filters": ["year", "month"],
        "domain": "compensation",
    },
]

PERIODO = {"start_date": "2026-08-01", "end_date": "2026-08-25"}


def chamada(code: str, parameters: dict[str, Any], *, entrada: int = 200, saida: int = 20):
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "consultar_metrica",
                "args": {"code": code, "parameters": parameters},
                "id": "call-1",
                "type": "tool_call",
            }
        ],
        usage_metadata={
            "input_tokens": entrada,
            "output_tokens": saida,
            "total_tokens": entrada + saida,
        },
    )


def resposta(texto: str, *, entrada: int = 300, saida: int = 30):
    return AIMessage(
        content=texto,
        usage_metadata={
            "input_tokens": entrada,
            "output_tokens": saida,
            "total_tokens": entrada + saida,
        },
    )


@pytest.fixture
def banco(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """As quatro leituras que o turno faz, sem banco. Guarda o que foi executado."""
    visto: dict[str, Any] = {"executado": []}

    async def load_catalog(tenant: TenantContext) -> list[dict[str, Any]]:
        return [dict(linha) for linha in CATALOGO_ROWS]

    async def domains(tenant: TenantContext) -> frozenset[str]:
        return visto.get("dominios", frozenset())

    async def execute(tenant: TenantContext, choice: catalogo.Choice, **kwargs: Any) -> list[dict]:
        visto["executado"].append(choice)
        return visto.get("linhas", [{"total": 42}])

    async def units(tenant: TenantContext) -> list[dict[str, Any]]:
        return [{"unit_id": UNIDADE, "code": "U-001", "name": "Shopping Norte"}]

    monkeypatch.setattr(executor, "load_catalog", load_catalog)
    monkeypatch.setattr(executor, "domains", domains)
    monkeypatch.setattr(executor, "execute", execute)
    monkeypatch.setattr(agente, "_units", units)
    return visto


async def rodar(
    modelo: FakeChatModel, pergunta: str = "quantos desvios este mês?"
) -> tuple[Turn, list[Event]]:
    turno = Turn(TENANT, pergunta, modelo, model_name="fake-1")
    eventos = [evento async for evento in turno.stream()]
    return turno, eventos


def tipos(eventos: list[Event]) -> list[str]:
    return [evento.type for evento in eventos]


def texto(eventos: list[Event]) -> str:
    return "".join(e.data["content"] for e in eventos if e.type == "token")


# ---------------------------------------------------------------------------
# O caminho feliz
# ---------------------------------------------------------------------------
async def test_metrica_escolhida_e_anunciada_antes_da_resposta(banco: dict[str, Any]):
    """A UI mostra período e filtros para a pessoa conferir — antes do texto."""
    modelo = FakeChatModel(
        responses=[
            chamada("deviations_total", PERIODO),
            resposta("Foram 42 desvios entre 01/08 e 25/08."),
        ],
        calls=[],
    )

    turno, eventos = await rodar(modelo)

    assert tipos(eventos)[0] == "metrica"
    assert set(tipos(eventos)[1:]) == {"token"}
    metrica = eventos[0].data
    assert metrica["codigo"] == "deviations_total"
    assert metrica["parametros"] == {"end_date": "2026-08-25", "start_date": "2026-08-01"}
    assert "42 desvios" in texto(eventos)
    assert turno.record.metric_code == "deviations_total"
    assert turno.record.rows_returned == 1
    assert turno.record.refused is False


async def test_o_que_foi_anunciado_e_o_que_rodou_sao_a_mesma_coisa(banco: dict[str, Any]):
    """O evento `metrica` sai da escolha aprovada, não do que o modelo pediu."""
    modelo = FakeChatModel(
        responses=[chamada("deviations_total", PERIODO), resposta("Foram 42.")], calls=[]
    )

    _, eventos = await rodar(modelo)

    escolha = banco["executado"][0]
    anunciado = next(e for e in eventos if e.type == "metrica").data
    assert anunciado["codigo"] == escolha.metric.code
    assert anunciado["parametros"] == {k: str(v) for k, v in sorted(escolha.parameters.items())}


async def test_tokens_das_duas_chamadas_entram_no_registro(banco: dict[str, Any]):
    """Custo é a soma do turno, não da última chamada."""
    modelo = FakeChatModel(
        responses=[
            chamada("deviations_total", PERIODO, entrada=200, saida=20),
            resposta("Foram 42.", entrada=300, saida=30),
        ],
        calls=[],
    )

    turno, _ = await rodar(modelo)

    assert turno.record.input_tokens == 500
    assert turno.record.output_tokens == 50
    assert turno.record.latency_ms is not None


# ---------------------------------------------------------------------------
# As recusas
# ---------------------------------------------------------------------------
async def test_metrica_inventada_e_recusada_e_o_turno_acaba_ali(banco: dict[str, Any]):
    """Recusa encerra: deixar o modelo tentar de novo é pagar pelo mesmo erro."""
    modelo = FakeChatModel(responses=[chamada("custo_por_hora", PERIODO)], calls=[])

    turno, eventos = await rodar(modelo)

    assert tipos(eventos) == ["recusa"]
    assert eventos[0].data["codigo"] == "fora_do_catalogo"
    assert len(modelo.calls) == 1
    assert turno.record.refused is True
    assert turno.record.metric_code is None


async def test_valor_inventado_para_unidade_e_recusado_em_vez_de_ir_ao_banco(
    banco: dict[str, Any],
):
    """`unit="month"` foi o que o modelo real fez na primeira execução.

    O nome do parâmetro é válido; o valor não é um identificador. Sem esta
    recusa a string chega a uma coluna `uuid` e o turno morre em erro de cast.
    """
    modelo = FakeChatModel(
        responses=[chamada("deviations_total", {**PERIODO, "unit": "month"})], calls=[]
    )

    turno, eventos = await rodar(modelo)

    assert tipos(eventos) == ["recusa"]
    assert eventos[0].data["codigo"] == "valor_invalido"
    assert "month" in eventos[0].data["motivo"]
    assert banco["executado"] == []
    assert turno.record.refused is True


async def test_periodo_ausente_e_recusado_antes_de_varrer_o_historico(banco: dict[str, Any]):
    modelo = FakeChatModel(responses=[chamada("deviations_total", {})], calls=[])

    _, eventos = await rodar(modelo)

    assert eventos[0].data["codigo"] == "filtro_ausente"
    assert banco["executado"] == []


async def test_parametro_que_o_alvo_descarta_nao_e_anunciado_como_filtro(
    banco: dict[str, Any],
):
    """`unit` num ranking DE unidades descreve a saída — o mapa o descarta.

    Foi o segundo achado da primeira execução real: o modelo mandou `unit`, o
    `BINDINGS` descartou (a função ordena unidades e não tem `p_unit_id`), e o
    modelo respondeu "com filtro da unidade Shopping Norte". O número estava
    certo e a frase em cima dele não. O evento agora diz o que filtrou de fato.
    """
    modelo = FakeChatModel(
        responses=[
            chamada("ranking_by_unit", {**PERIODO, "unit": str(UNIDADE)}),
            resposta("Shopping Norte lidera."),
        ],
        calls=[],
    )

    _, eventos = await rodar(modelo)

    metrica = next(e for e in eventos if e.type == "metrica").data
    assert "unit" not in metrica["parametros"]
    assert metrica["ignorados"] == ["unit"]
    # E o modelo é avisado, para não afirmar um recorte que não aconteceu.
    ferramenta = modelo.calls[1][-1]
    assert "unit" in ferramenta.text and "descartado" in ferramenta.text


# ---------------------------------------------------------------------------
# O domínio filtra antes de o modelo ver
# ---------------------------------------------------------------------------
async def test_metrica_de_dominio_fora_de_alcance_nao_aparece_no_prompt(banco: dict[str, Any]):
    """Oferecer e recusar depois confirmaria que existe folha para quem não pode saber."""
    modelo = FakeChatModel(responses=[resposta("Não tenho esse dado.")], calls=[])

    await rodar(modelo, "qual foi a folha de agosto?")

    prompt = modelo.calls[0][0].text
    assert "deviations_total" in prompt
    assert "payroll_summary" not in prompt
    assert "folha" not in prompt.lower()


async def test_com_o_dominio_a_metrica_sensivel_entra_no_prompt(banco: dict[str, Any]):
    banco["dominios"] = frozenset({"compensation"})
    modelo = FakeChatModel(responses=[resposta("ok")], calls=[])

    await rodar(modelo)

    assert "payroll_summary" in modelo.calls[0][0].text


async def test_o_prompt_traz_as_unidades_porque_unit_e_identificador(banco: dict[str, Any]):
    """Sem a lista o modelo chuta um uuid ou some com o filtro — os dois mentem."""
    modelo = FakeChatModel(responses=[resposta("ok")], calls=[])

    await rodar(modelo)

    prompt = modelo.calls[0][0].text
    assert "Shopping Norte" in prompt
    assert str(UNIDADE) in prompt
    # Nenhum nome de tabela e nenhum nome de coluna chega ao modelo.
    assert "fn_kpi_period" not in prompt
    assert "tenant_id" not in prompt


# ---------------------------------------------------------------------------
# O erro
# ---------------------------------------------------------------------------
async def test_falha_do_provider_vira_evento_e_nao_excecao(banco: dict[str, Any]):
    """Depois do primeiro byte não há status code para mudar."""
    modelo = FakeChatModel(responses=[], raises=RuntimeError("connection reset"), calls=[])

    turno, eventos = await rodar(modelo)

    assert tipos(eventos) == ["error"]
    # A mensagem do provider não chega à tela.
    assert "connection reset" not in eventos[0].data["message"]
    assert turno.record.latency_ms is not None


async def test_falha_ao_ler_o_catalogo_tambem_vira_evento(monkeypatch: pytest.MonkeyPatch):
    async def explode(tenant: TenantContext) -> list[dict[str, Any]]:
        raise RuntimeError("pool fechado")

    monkeypatch.setattr(executor, "load_catalog", explode)
    modelo = FakeChatModel(responses=[], calls=[])

    _, eventos = await rodar(modelo)

    assert tipos(eventos) == ["error"]
    assert modelo.calls == []


# ---------------------------------------------------------------------------
# A allowlist de modelo
# ---------------------------------------------------------------------------
def test_modelo_fora_da_allowlist_e_recusado_pelo_nome():
    with pytest.raises(agente.ModelNotAllowedError) as erro:
        agente.build_model("gpt-4-turbo")

    assert "gpt-4-turbo" in str(erro.value)
    # A recusa lista o que existe — a mesma regra das recusas do catálogo.
    for disponivel in agente.available_models():
        assert disponivel in str(erro.value)


def test_estar_na_allowlist_nao_basta_sem_a_chave_do_provider(
    monkeypatch: pytest.MonkeyPatch,
):
    """Um modelo permitido cujo provider não tem chave não existe nesta instalação."""
    monkeypatch.setattr(agente, "_configured", lambda settings: ("anthropic",))

    with pytest.raises(agente.ModelNotAllowedError) as erro:
        agente.build_model("gpt-5.4-mini")

    assert "gpt-5.4-mini" in str(erro.value)


def test_sem_pedido_o_modelo_e_o_primeiro_disponivel():
    """Qual é o primeiro depende de quais chaves existem — e é isso que se afirma."""
    _, model_id = agente.build_model()

    assert model_id == agente.available_models()[0]


# ---------------------------------------------------------------------------
# O contrato SSE
# ---------------------------------------------------------------------------
class TurnoFalso:
    """Um turno com eventos prontos, para testar o transporte e nada mais."""

    def __init__(self, eventos: list[Event]) -> None:
        self._eventos = eventos
        self.record = Record(question="pergunta", model="fake-1", latency_ms=7)

    async def stream(self):
        for evento in self._eventos:
            yield evento


@pytest.fixture
def sse(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Substitui provider e banco, e guarda o que teria sido gravado."""
    estado: dict[str, Any] = {"gravados": [], "eventos": []}

    monkeypatch.setattr(assistente, "build_model", lambda pedido: (object(), "fake-1"))
    monkeypatch.setattr(assistente, "Turn", lambda *args, **kwargs: TurnoFalso(estado["eventos"]))

    async def registrar(tenant: TenantContext, record: Record) -> UUID:
        estado["gravados"].append(record)
        return uuid4()

    monkeypatch.setattr(assistente, "registrar", registrar)
    monkeypatch.setattr(assistente, "_limiter", assistente.RateLimiter())
    return estado


def eventos_de(corpo: str) -> list[tuple[str, dict]]:
    lidos = []
    for bloco in corpo.strip().split("\n\n"):
        linhas = dict(linha.split(": ", 1) for linha in bloco.splitlines() if ": " in linha)
        lidos.append((linhas["event"], json.loads(linhas["data"])))
    return lidos


def test_o_stream_entrega_os_eventos_do_turno_e_fecha_com_done(
    client: TestClient, issue_token, sse: dict[str, Any]
):
    sse["eventos"] = [
        Event("metrica", {"codigo": "deviations_total", "parametros": {}, "linhas": 1}),
        Event("token", {"content": "Foram "}),
        Event("token", {"content": "42."}),
    ]

    resposta_http = client.post(
        "/assistente/perguntar",
        json={"question": "quantos desvios?"},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert resposta_http.status_code == 200
    assert resposta_http.headers["content-type"].startswith("text/event-stream")
    assert resposta_http.headers["x-accel-buffering"] == "no"
    lidos = eventos_de(resposta_http.text)
    assert [nome for nome, _ in lidos] == ["metrica", "token", "token", "done"]
    assert lidos[-1][1]["consulta_id"]
    assert lidos[-1][1]["tokens_saida"] == 0


def test_a_recusa_chega_dentro_de_um_200_porque_e_resposta(
    client: TestClient, issue_token, sse: dict[str, Any]
):
    sse["eventos"] = [Event("recusa", {"codigo": "fora_do_catalogo", "motivo": "Não tenho."})]

    resposta_http = client.post(
        "/assistente/perguntar",
        json={"question": "qual o custo por hora?"},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert resposta_http.status_code == 200
    assert [nome for nome, _ in eventos_de(resposta_http.text)] == ["recusa", "done"]


def test_o_turno_e_gravado_uma_vez_so(client: TestClient, issue_token, sse: dict[str, Any]):
    sse["eventos"] = [Event("token", {"content": "oi"})]

    client.post(
        "/assistente/perguntar",
        json={"question": "oi"},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert len(sse["gravados"]) == 1
    assert sse["gravados"][0].model == "fake-1"


def test_sem_token_o_stream_nem_comeca(client: TestClient, sse: dict[str, Any]):
    resposta_http = client.post("/assistente/perguntar", json={"question": "oi"})

    assert resposta_http.status_code == 401
    assert resposta_http.json()["detail"]
    assert sse["gravados"] == []


def test_modelo_fora_da_allowlist_responde_400_antes_do_primeiro_byte(
    client: TestClient, issue_token, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(assistente, "_limiter", assistente.RateLimiter())

    resposta_http = client.post(
        "/assistente/perguntar",
        json={"question": "oi", "model": "gpt-4-turbo"},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert resposta_http.status_code == 400
    assert "gpt-4-turbo" in resposta_http.json()["detail"]


def test_pergunta_vazia_e_recusada_pelo_schema(client: TestClient, issue_token):
    resposta_http = client.post(
        "/assistente/perguntar",
        json={"question": ""},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert resposta_http.status_code == 422


def test_o_teto_por_usuario_responde_429_com_retry_after(
    client: TestClient, issue_token, sse: dict[str, Any]
):
    """LLM pago sem limite é abuso de custo trivial — e o limite é por pessoa."""
    monkeypatch_limite = assistente.RateLimiter(limit=2)
    assistente._limiter = monkeypatch_limite
    sse["eventos"] = [Event("token", {"content": "oi"})]
    cabecalho = {"Authorization": f"Bearer {issue_token()}"}

    for _ in range(2):
        assert (
            client.post("/assistente/perguntar", json={"question": "oi"}, headers=cabecalho)
        ).status_code == 200

    excedente = client.post("/assistente/perguntar", json={"question": "oi"}, headers=cabecalho)

    assert excedente.status_code == 429
    assert int(excedente.headers["retry-after"]) > 0


# ---------------------------------------------------------------------------
# O provider falso do E2E
# ---------------------------------------------------------------------------
def test_a_flag_de_e2e_troca_o_provider_e_dispensa_chave(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("E2E_FAKE_LLM", "1")
    monkeypatch.setattr(agente, "_configured", lambda settings: ())

    _, model_id = agente.build_model()

    assert model_id == "e2e-fake"


async def test_o_provider_falso_atravessa_a_mesma_fronteira(
    banco: dict[str, Any], monkeypatch: pytest.MonkeyPatch
):
    """Ele escolhe do catálogo como qualquer modelo — e é `choose` que aprova."""
    monkeypatch.setenv("E2E_FAKE_LLM", "1")
    modelo, _ = agente.build_model()

    turno, eventos = await rodar(modelo, "quantos desvios tivemos?")

    assert tipos(eventos)[0] == "metrica"
    assert turno.record.metric_code == "deviations_total"
    assert "1 registro" in texto(eventos)


async def test_o_provider_falso_recusa_o_que_nao_tem_metrica(
    banco: dict[str, Any], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("E2E_FAKE_LLM", "1")
    modelo, _ = agente.build_model()

    turno, eventos = await rodar(modelo, "quanto gastamos de folha em agosto?")

    assert tipos(eventos) == ["recusa"]
    assert turno.record.refused is True
