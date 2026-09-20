"""O turno do assistente e o contrato SSE.

O que estes testes cercam não é "o modelo respondeu bem" — isso não é testável e
não é o ponto. É o que acontece **em volta** da resposta: que a métrica anunciada
seja a que rodou, que uma recusa encerre o turno em vez de virar uma segunda
tentativa paga, que uma falha do provider chegue como evento e não como stack
trace no meio de um `text/event-stream`, e que a linha de custo seja gravada nos
três finais possíveis.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from operax.agente import agente, catalogo, executor
from operax.agente.agente import Event, Record, Turn
from operax.agente.prompt import PromptLayers
from operax.core.tenant import TenantContext, UserRole
from server.routers import assistente
from tests.fixtures.fake_llm import FakeChatModel

TENANT = TenantContext(
    tenant_id=UUID("22222222-2222-4222-8222-222222222222"),
    user_id=UUID("11111111-1111-4111-8111-111111111111"),
    role=UserRole.UNIT_SUPERVISOR,
)
UNIDADE = UUID("33333333-3333-4333-8333-333333333333")
PLATFORM_V1 = UUID("44444444-4444-4444-8444-444444444441")
TENANT_V1 = UUID("44444444-4444-4444-8444-444444444442")

#: As camadas no ar, como `prompt.load_layers` as devolveria. A plataforma pede
#: o modelo que a `conftest` configura (só `ANTHROPIC_API_KEY`); o texto é curto
#: e carrega os três tokens — o retrato byte a byte da v1 é `test_agente_prompt_seed`.
LAYERS = PromptLayers(
    platform_version_id=PLATFORM_V1,
    platform_content=(
        "Você é o assistente. Hoje é {{hoje}}.\n\n"
        "Métricas que você pode consultar:\n{{catalogo}}\n\n"
        "Unidades:\n{{unidades}}"
    ),
    provider="anthropic",
    model="claude-haiku-4-5-20251001",
    max_steps=None,
    tenant_version_id=None,
    tenant_content=None,
)

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
    modelo: FakeChatModel,
    pergunta: str = "quantos desvios este mês?",
    *,
    layers: PromptLayers = LAYERS,
    **turno_kwargs: Any,
) -> tuple[Turn, list[Event]]:
    turno = Turn(TENANT, pergunta, modelo, layers, model_name="fake-1", **turno_kwargs)
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
# O prompt vem do ponteiro, e o registro diz qual versão rodou (A3)
# ---------------------------------------------------------------------------
COM_TENANT = PromptLayers(
    platform_version_id=PLATFORM_V1,
    platform_content=LAYERS.platform_content,
    provider="anthropic",
    model="claude-haiku-4-5-20251001",
    max_steps=None,
    tenant_version_id=TENANT_V1,
    tenant_content="Vocabulário local: chame a unidade de 'praça'. Hoje: {{hoje}}.",
)


async def test_o_registro_leva_a_versao_de_tenant_no_ar(banco: dict[str, Any]):
    """Decisão 2: a versão de tenant apontada é a que o turno registra."""
    modelo = FakeChatModel(responses=[resposta("ok")], calls=[])

    turno, _ = await rodar(modelo, layers=COM_TENANT)

    assert turno.record.prompt_version_id == TENANT_V1
    assert turno.record.is_dry_run is False
    assert turno.record.draft_content_hash is None


async def test_sem_versao_de_tenant_o_registro_leva_a_plataforma(banco: dict[str, Any]):
    """Nunca nulo numa linha nova: nulo é "antes do versionamento"."""
    modelo = FakeChatModel(responses=[resposta("ok")], calls=[])

    turno, _ = await rodar(modelo, layers=LAYERS)

    assert turno.record.prompt_version_id == PLATFORM_V1


async def test_a_camada_do_tenant_entra_depois_da_plataforma_e_tambem_renderiza(
    banco: dict[str, Any],
):
    modelo = FakeChatModel(responses=[resposta("ok")], calls=[])

    await rodar(modelo, layers=COM_TENANT)

    prompt = modelo.calls[0][0].text
    assert prompt.index("Você é o assistente") < prompt.index("Vocabulário local")
    # O token da camada do tenant foi renderizado, não deixado literal.
    assert "{{" not in prompt
    assert prompt.count(date.today().isoformat()) == 2


async def test_o_teste_com_rascunho_e_dry_run_com_hash_e_aponta_para_a_plataforma(
    banco: dict[str, Any],
):
    """O rascunho substitui a camada de tenant sem virar versão (SPEC §7.1, decidida):
    a única camada que de fato é versão é a plataforma, e o texto fica pelo hash."""
    rascunho = "Rascunho: chame a unidade de 'pátio'."
    modelo = FakeChatModel(responses=[resposta("ok")], calls=[])

    turno, _ = await rodar(modelo, layers=COM_TENANT, dry_run=True, tenant_override=rascunho)

    assert turno.record.is_dry_run is True
    assert turno.record.prompt_version_id == PLATFORM_V1
    assert turno.record.draft_content_hash == hashlib.sha256(rascunho.encode("utf-8")).hexdigest()
    prompt = modelo.calls[0][0].text
    assert "pátio" in prompt
    assert "praça" not in prompt


async def test_o_teste_sem_rascunho_e_dry_run_com_as_camadas_normais(banco: dict[str, Any]):
    modelo = FakeChatModel(responses=[resposta("ok")], calls=[])

    turno, _ = await rodar(modelo, layers=COM_TENANT, dry_run=True)

    assert turno.record.is_dry_run is True
    assert turno.record.prompt_version_id == TENANT_V1
    assert turno.record.draft_content_hash is None
    assert "praça" in modelo.calls[0][0].text


def test_rascunho_fora_de_dry_run_e_recusado_na_construcao():
    """Um turno real sobre texto não publicado seria um registro que mente."""
    with pytest.raises(ValueError):
        Turn(TENANT, "oi", FakeChatModel(responses=[], calls=[]), LAYERS, tenant_override="x")


async def test_marcador_desconhecido_no_texto_publicado_vira_evento_de_erro(
    banco: dict[str, Any],
):
    """Erro de configuração, não de turno — e o modelo não é chamado."""
    quebrada = PromptLayers(
        platform_version_id=PLATFORM_V1,
        platform_content="{{hoje}} {{catalogo}} {{unidades}} {{papel}}",
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
        max_steps=None,
        tenant_version_id=None,
        tenant_content=None,
    )
    modelo = FakeChatModel(responses=[resposta("ok")], calls=[])

    turno, eventos = await rodar(modelo, layers=quebrada)

    assert tipos(eventos) == ["error"]
    assert "marcador" in eventos[0].data["message"]
    assert modelo.calls == []
    # Houve turno — o registro sai com a versão que o produziu.
    assert turno.record.prompt_version_id == PLATFORM_V1


def _com_teto(max_steps: int | None) -> PromptLayers:
    return PromptLayers(
        platform_version_id=PLATFORM_V1,
        platform_content=LAYERS.platform_content,
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
        max_steps=max_steps,
        tenant_version_id=None,
        tenant_content=None,
    )


async def test_max_steps_e_o_teto_de_idas_a_ferramenta(banco: dict[str, Any]):
    """`recursion_limit = 2 * max_steps + 2`, medido: com teto 1, uma ida passa e
    a segunda morre em `GraphRecursionError`, que chega como `event: error`."""
    duas_idas = [
        chamada("deviations_total", PERIODO),
        chamada("ranking_by_unit", PERIODO),
        resposta("Foram 42."),
    ]

    modelo = FakeChatModel(responses=list(duas_idas), calls=[])
    _, eventos = await rodar(modelo, layers=_com_teto(2))
    assert tipos(eventos)[-1] == "token"
    assert len(modelo.calls) == 3

    modelo = FakeChatModel(responses=list(duas_idas), calls=[])
    _, eventos = await rodar(modelo, layers=_com_teto(1))
    assert tipos(eventos)[-1] == "error"
    assert len(modelo.calls) == 2


async def test_sem_teto_o_comportamento_e_o_de_antes(banco: dict[str, Any]):
    """`max_steps` nulo = o padrão do LangGraph, como a v1 transcrita."""
    assert agente._step_ceiling(None) is None
    assert agente._step_ceiling(1) == {"recursion_limit": 4}
    assert agente._step_ceiling(10) == {"recursion_limit": 22}


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


def test_sem_pedido_e_sem_camadas_o_modelo_e_o_primeiro_disponivel():
    """Qual é o primeiro depende de quais chaves existem — e é isso que se afirma."""
    _, model_id = agente.build_model()

    assert model_id == agente.available_models()[0]


def test_sem_pedido_o_modelo_e_o_que_a_plataforma_no_ar_diz():
    """A camada platform escolhe o modelo: é ela quem paga (SPEC-AGENTE §6.2)."""
    _, model_id = agente.build_model(layers=LAYERS)

    assert model_id == "claude-haiku-4-5-20251001"


def test_o_pedido_do_cliente_vence_o_padrao_da_plataforma_mas_passa_pela_allowlist():
    _, model_id = agente.build_model("claude-sonnet-5", layers=LAYERS)
    assert model_id == "claude-sonnet-5"

    with pytest.raises(agente.ModelNotAllowedError) as erro:
        agente.build_model("gpt-4-turbo", layers=LAYERS)
    assert "gpt-4-turbo" in str(erro.value)


def test_a_plataforma_pedindo_modelo_que_a_instalacao_nao_roda_e_erro_de_configuracao(
    monkeypatch: pytest.MonkeyPatch,
):
    """Não roda outro em silêncio: numa instalação só com a chave da Anthropic, a
    v1 real (openai/gpt-5.4-mini) é 503 com o modelo nomeado — não um modelo trocado."""
    monkeypatch.setattr(agente, "_configured", lambda settings: ("anthropic",))
    camadas = PromptLayers(
        platform_version_id=PLATFORM_V1,
        platform_content="{{hoje}} {{catalogo}} {{unidades}}",
        provider="openai",
        model="gpt-5.4-mini",
        max_steps=None,
        tenant_version_id=None,
        tenant_content=None,
    )

    with pytest.raises(agente.NoProviderConfiguredError) as erro:
        agente.build_model(layers=camadas)

    assert "gpt-5.4-mini" in str(erro.value)


def test_provider_e_modelo_da_plataforma_em_desacordo_e_erro_de_configuracao():
    camadas = PromptLayers(
        platform_version_id=PLATFORM_V1,
        platform_content="{{hoje}} {{catalogo}} {{unidades}}",
        provider="openai",
        model="claude-haiku-4-5-20251001",
        max_steps=None,
        tenant_version_id=None,
        tenant_content=None,
    )

    with pytest.raises(agente.NoProviderConfiguredError):
        agente.build_model(layers=camadas)


def test_plataforma_sem_modelo_cai_no_padrao_da_instalacao():
    camadas = PromptLayers(
        platform_version_id=PLATFORM_V1,
        platform_content="{{hoje}} {{catalogo}} {{unidades}}",
        provider=None,
        model=None,
        max_steps=None,
        tenant_version_id=None,
        tenant_content=None,
    )

    _, model_id = agente.build_model(layers=camadas)

    assert model_id == agente.available_models()[0]


# ---------------------------------------------------------------------------
# O contrato SSE
# ---------------------------------------------------------------------------
class TurnoFalso:
    """Um turno com eventos prontos, para testar o transporte e nada mais.

    O `record` entra de fora porque o `done` passou a carregar o que RODOU
    (`prompt_version_id` e `draft_content_hash`): sem poder variá-lo, os três
    casos do evento seriam o mesmo caso.
    """

    def __init__(self, eventos: list[Event], record: Record | None = None) -> None:
        self._eventos = eventos
        self.record = record or Record(question="pergunta", model="fake-1", latency_ms=7)

    async def stream(self):
        for evento in self._eventos:
            yield evento


@pytest.fixture
def sse(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Substitui provider e banco, e guarda o que teria sido gravado."""
    estado: dict[str, Any] = {"gravados": [], "eventos": []}

    monkeypatch.setattr(assistente, "build_model", lambda pedido, **kw: (object(), "fake-1"))
    monkeypatch.setattr(
        assistente,
        "Turn",
        lambda *args, **kwargs: TurnoFalso(estado["eventos"], estado.get("record")),
    )

    async def load_layers(tenant: TenantContext) -> PromptLayers | None:
        return estado.get("camadas", LAYERS)

    monkeypatch.setattr(assistente, "load_layers", load_layers)

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


class _ScopeGravacao:
    """Um `tenant_scope` falso: guarda a instrução e os parâmetros do insert."""

    def __init__(self) -> None:
        self.statement = ""
        self.params: dict[str, Any] = {}

    async def __aenter__(self) -> _ScopeGravacao:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def execute(self, statement: str, params: dict[str, Any]) -> None:
        self.statement, self.params = statement, params

    async def fetchone(self) -> dict[str, Any]:
        return {"id": uuid4()}


async def test_registrar_grava_a_versao_o_dry_run_e_o_hash(monkeypatch: pytest.MonkeyPatch):
    """As três colunas da migration `assistant_run_link` saem do `Record`, e
    não de um valor fixo: sem isto, todo turno novo ficaria "antes do
    versionamento" com a coluna existindo."""
    escopo = _ScopeGravacao()
    monkeypatch.setattr(assistente, "tenant_scope", lambda _t: escopo)
    record = Record(
        question="q",
        model="fake-1",
        prompt_version_id=TENANT_V1,
        is_dry_run=True,
        draft_content_hash="a" * 64,
    )

    await assistente.registrar(TENANT, record)

    assert escopo.params["prompt_version_id"] == TENANT_V1
    assert escopo.params["is_dry_run"] is True
    assert escopo.params["draft_content_hash"] == "a" * 64
    colunas = escopo.statement[: escopo.statement.index("values")]
    for coluna in ("prompt_version_id", "is_dry_run", "draft_content_hash"):
        assert coluna in colunas
    # E um turno real leva o que o `Record` diz por padrão: false e sem hash.
    real = Record(question="q", model="m", prompt_version_id=PLATFORM_V1)
    await assistente.registrar(TENANT, real)
    assert escopo.params["prompt_version_id"] == PLATFORM_V1
    assert escopo.params["is_dry_run"] is False
    assert escopo.params["draft_content_hash"] is None


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


def test_o_done_diz_qual_versao_rodou_e_que_nao_houve_rascunho(
    client: TestClient, issue_token, sse: dict[str, Any]
):
    """Turno real: a versão preenchida e o hash nulo."""
    sse["record"] = Record(question="q", model="fake-1", prompt_version_id=TENANT_V1)
    sse["eventos"] = [Event("token", {"content": "oi"})]

    resposta_http = client.post(
        "/assistente/perguntar",
        json={"question": "oi"},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    _, dados = eventos_de(resposta_http.text)[-1]
    assert dados["prompt_version_id"] == str(TENANT_V1)
    assert dados["draft_content_hash"] is None


def test_o_done_de_um_dry_run_carrega_o_hash_do_texto_testado(
    client: TestClient, issue_token, sse: dict[str, Any]
):
    """Dry run com rascunho: o hash do texto e a versão da plataforma — a
    única camada que de fato é versão quando o que rodou foi rascunho."""
    sse["record"] = Record(
        question="q",
        model="fake-1",
        prompt_version_id=PLATFORM_V1,
        is_dry_run=True,
        draft_content_hash="b" * 64,
    )
    sse["eventos"] = [Event("token", {"content": "oi"})]

    resposta_http = client.post(
        "/assistente/perguntar",
        json={"question": "oi"},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    _, dados = eventos_de(resposta_http.text)[-1]
    assert dados["prompt_version_id"] == str(PLATFORM_V1)
    assert dados["draft_content_hash"] == "b" * 64


def test_o_done_de_uma_linha_sem_versao_manda_nulo_e_nunca_inventa(
    client: TestClient, issue_token, sse: dict[str, Any]
):
    """O `Record` default é a linha anterior ao versionamento: os dois campos
    saem nulos. Inventar a v1 aqui seria inventar procedência."""
    sse["eventos"] = [Event("token", {"content": "oi"})]

    resposta_http = client.post(
        "/assistente/perguntar",
        json={"question": "oi"},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    _, dados = eventos_de(resposta_http.text)[-1]
    assert dados["prompt_version_id"] is None
    assert dados["draft_content_hash"] is None
    # E o resto do evento continua inteiro: o custo do turno volta com ele.
    assert set(dados) == {
        "consulta_id",
        "modelo",
        "tokens_entrada",
        "tokens_saida",
        "latencia_ms",
        "prompt_version_id",
        "draft_content_hash",
    }


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


def test_sem_ponteiro_de_plataforma_sai_so_o_error_e_nada_e_gravado(
    client: TestClient, issue_token, sse: dict[str, Any]
):
    """Sem texto em código para cair: sem ponteiro não há turno — um `error`
    sozinho, sem `done`, e nenhuma linha em `app.ai_query`."""
    sse["camadas"] = None
    sse["eventos"] = [Event("token", {"content": "não deveria rodar"})]

    resposta_http = client.post(
        "/assistente/perguntar",
        json={"question": "oi"},
        headers={"Authorization": f"Bearer {issue_token()}"},
    )

    assert resposta_http.status_code == 200
    lidos = eventos_de(resposta_http.text)
    assert [nome for nome, _ in lidos] == ["error"]
    assert lidos[0][1]["message"] == "O assistente está sem configuração publicada."
    assert sse["gravados"] == []


def test_sem_token_o_stream_nem_comeca(client: TestClient, sse: dict[str, Any]):
    resposta_http = client.post("/assistente/perguntar", json={"question": "oi"})

    assert resposta_http.status_code == 401
    assert resposta_http.json()["detail"]
    assert sse["gravados"] == []


def test_modelo_fora_da_allowlist_responde_400_antes_do_primeiro_byte(
    client: TestClient, issue_token, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(assistente, "_limiter", assistente.RateLimiter())

    async def load_layers(tenant: TenantContext) -> PromptLayers | None:
        return LAYERS

    monkeypatch.setattr(assistente, "load_layers", load_layers)

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
