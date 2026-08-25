"""The wiring — a question in, typed events out, and no number the tool did not produce.

This is the half of the assistant that talks to a provider. The half that decides
what may be answered is `catalogo.py`, and this module is deliberately arranged
*around* it rather than beside it: the model's only reach into the data is one
tool, that tool calls `catalogo.choose` before it calls anything else, and
`executor.execute` runs the result as the person who asked. There is no second
path, so there is nothing to keep in sync.

WHAT THE MODEL IS ALLOWED TO KNOW
The catalogue offered in the prompt is already filtered by sensitive domain, so a
metric the person cannot reach is not named. The units are listed because `unit`
is a uuid and a person says "Shopping Norte": without the list the model either
guesses an identifier or silently drops the filter, and a total for every unit
presented as the answer for one unit is a wrong number with a confident sentence
in front of it. No table name and no column name is ever in the prompt.

THE REFUSAL ENDS THE TURN
When the tool refuses, the stream stops there. The refusal text names the
parameter or the metric that was wrong, which is what gets the next question
right — letting the model try again instead would spend tokens rewording the same
mistake, and would let a `filtro_ausente` be "fixed" by a period the model chose
for itself.

WHY THE `metrica` EVENT COMES AFTER THE QUERY, NOT BEFORE
The tool call the model emits is a proposal. Announcing it before `choose` had
approved it would show the person a metric that the next event then refuses.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from time import perf_counter
from typing import Any, Literal
from uuid import UUID

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel

from operax.agente import catalogo, e2e, executor
from operax.agente.catalogo import MAX_ROWS, Refusal
from operax.core.config import Settings, get_settings
from operax.core.tenant import TenantContext, user_scope

logger = logging.getLogger(__name__)

Provider = Literal["openai", "anthropic", "google"]

#: Os modelos que este backend aceita, por provider, e o primeiro de cada tupla é
#: o padrão daquele provider. A lista é fechada porque o id do modelo chega do
#: cliente: um id arbitrário é um jeito de escolher um modelo caro, um modelo de
#: outra conta ou um endpoint que não existe, e nenhum dos três deveria depender
#: de o frontend estar bem-comportado.
ALLOWED_MODELS: dict[Provider, tuple[str, ...]] = {
    "openai": ("gpt-5.4-mini", "gpt-5.4"),
    "anthropic": ("claude-haiku-4-5-20251001", "claude-sonnet-5"),
    "google": ("gemini-2.5-flash", "gemini-2.5-pro"),
}

#: A ordem em que um provider é escolhido quando o cliente não pede modelo. É a
#: mesma de `config.PROVIDER_KEYS`, e é a mesma de propósito: duas ordens para a
#: mesma decisão viram duas respostas diferentes para "qual modelo rodou?".
_PROVIDER_ORDER: tuple[Provider, ...] = ("openai", "anthropic", "google")


class ModelNotAllowedError(ValueError):
    """O modelo pedido não está na allowlist, ou o provider dele não tem chave."""


class NoProviderConfiguredError(RuntimeError):
    """Nenhuma chave de provider configurada. O `config.py` barra isso no startup."""


def _configured(settings: Settings) -> tuple[Provider, ...]:
    chaves = {
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "google": settings.google_api_key,
    }
    return tuple(p for p in _PROVIDER_ORDER if chaves[p] is not None)


def available_models() -> tuple[str, ...]:
    """Os modelos que esta instalação pode rodar — allowlist ∩ chaves presentes."""
    settings = get_settings()
    return tuple(m for p in _configured(settings) for m in ALLOWED_MODELS[p])


def build_model(requested: str | None = None) -> tuple[BaseChatModel, str]:
    """O modelo pedido e o id dele, se ele for permitido e o provider tiver chave.

    Devolve o par porque o id é o que vai para `app.ai_query`: quando o cliente
    não pede modelo, quem escolhe é esta função, e o registro precisa dizer qual
    modelo rodou — não "o padrão", que muda quando a allowlist muda.
    """
    if os.environ.get(e2e.FLAG) == "1":
        # O desvio fica aqui, na escolha do provider, e não dentro do turno: a
        # fronteira inteira — catálogo, domínio, RLS — continua no caminho.
        logger.warning("%s=1: o assistente está respondendo com um provider falso", e2e.FLAG)
        return e2e.E2EChatModel(), e2e.MODEL_ID

    settings = get_settings()
    configurados = _configured(settings)
    if not configurados:
        raise NoProviderConfiguredError("nenhuma chave de provider configurada")

    if requested is None:
        provider = configurados[0]
        model_id = ALLOWED_MODELS[provider][0]
    else:
        escolhido = next(
            (p for p in configurados if requested in ALLOWED_MODELS[p]),
            None,
        )
        if escolhido is None:
            permitidos = ", ".join(available_models())
            raise ModelNotAllowedError(
                f"modelo {requested!r} não disponível. Disponíveis: {permitidos}"
            )
        provider, model_id = escolhido, requested

    # Import tardio: os três providers são dependência declarada, e o do Google
    # arrasta grpc. Carregar os três para usar um custa segundos de startup no
    # Railway em troca de nada.
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model_id, api_key=settings.openai_api_key), model_id
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model_name=model_id, api_key=settings.anthropic_api_key), model_id
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(model=model_id, google_api_key=settings.google_api_key), model_id


# ---------------------------------------------------------------------------
# O que o turno produz
# ---------------------------------------------------------------------------
EventType = Literal["metrica", "token", "recusa", "error"]


@dataclass(frozen=True, slots=True)
class Event:
    """Um evento do turno. O router traduz para SSE; nada aqui sabe o que é SSE."""

    type: EventType
    data: dict[str, Any]


@dataclass(slots=True)
class Record:
    """A linha de `app.ai_query`, montada ao longo do turno.

    Custo de LLM é variável e sai da sustentação mensal: sem medir, não dá para
    saber se a margem virou negativa. Por isso o registro é preenchido mesmo
    quando o turno termina em recusa ou em erro.
    """

    question: str
    model: str
    metric_code: str | None = None
    parameters: dict[str, Any] | None = None
    rows_returned: int | None = None
    latency_ms: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    refused: bool = False
    refusal_reason: str | None = None


@dataclass(slots=True)
class _Pending:
    """O que a ferramenta viu, para o laço de streaming ler depois que ela roda."""

    events: list[Event] = field(default_factory=list)
    refusal: Refusal | None = None


def _json_default(value: Any) -> str:
    """O que o Postgres devolve e o `json` não sabe escrever.

    `time` está aqui porque faltava: `vw_deviation_event` tem `expected_time`, e
    a primeira pergunta real contra o banco de desenvolvimento morreu em
    `TypeError` — que o `except` largo do turno mostrou como "falha ao consultar
    o modelo". Fixture de teste com `{"total": 42}` nunca alcançaria isso.
    """
    if isinstance(value, UUID | date | datetime | time):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"{type(value).__name__} não é serializável")


_UNITS_SQL = """
select unit_id, code, name
from public.vw_unit
where active
order by name
"""


async def _units(tenant: TenantContext) -> list[dict[str, Any]]:
    """As unidades que esta pessoa alcança. A RLS de `vw_unit` decide quais são.

    Sem limite, e não por descuido: `app.unit` é dimensão curada à mão com o
    cliente — a fila de `app.unit_secullum_map` existe justamente porque nada a
    preenche sozinho. Ela cresce no ritmo de uma conversa, não no de uma
    sincronização.
    """
    async with user_scope(tenant) as scope:
        await scope.execute(_UNITS_SQL)
        return [dict(row) for row in await scope.fetchall()]


def _prompt(catalogo_texto: str, unidades: list[dict[str, Any]], hoje: date) -> str:
    if unidades:
        linhas = "\n".join(f"- {u['name']} ({u['code']}): {u['unit_id']}" for u in unidades)
    else:
        linhas = "- nenhuma unidade cadastrada; não use o parâmetro `unit`."
    return f"""Você é o assistente de gestão de ponto deste painel. Responda sempre em \
português do Brasil.

Hoje é {hoje.strftime("%d/%m/%Y")} ({hoje.isoformat()}).

Você não sabe nenhum número. Todo número que você disser precisa ter vindo da \
ferramenta `consultar_metrica` nesta conversa. Se a pergunta pede dado e você não \
chamou a ferramenta, você não tem resposta — diga isso em vez de estimar.

Métricas que você pode consultar:
{catalogo_texto}

Sobre os parâmetros:
- `start_date` e `end_date` são datas AAAA-MM-DD e são obrigatórias em toda métrica \
que as aceita. Traduza "este mês", "semana passada" ou "ontem" usando a data de hoje. \
Se a pergunta não disser período nenhum, use o mês corrente e diga qual período usou.
- `unit`, `company` e `employee` são identificadores no formato UUID. **Omita o \
parâmetro** quando não houver filtro — omitir é o caso normal, e o seu acesso já \
limita o que você enxerga. Nunca preencha com um nome, com `null`, nem com \
palavras como "all", "todos", "geral" ou o nome do mês.
- Só use `unit` se o identificador estiver na lista de unidades abaixo. Se a \
pergunta cita uma pessoa pelo nome, não invente identificador: omita o filtro e \
diga que você responde por unidade e por período.
- Não passe parâmetro que a métrica não declara aceitar.
- **Nunca acrescente um filtro que a pergunta não pediu.** Se a pergunta pede um \
recorte que a métrica não aceita — por tipo de desvio, por exemplo — trocá-lo por \
outro filtro dá um número certo para uma pergunta que ninguém fez. Nesse caso, \
`recusar`.
- Antes de recusar, releia a lista inteira de métricas: recuse só quando nenhuma \
delas se aproximar da pergunta.
- Se nenhuma métrica da lista responde à pergunta, chame `recusar` com o motivo \
em uma frase — não responda em texto. Recusar é resposta válida; estimar não é. \
`recusar` é só para isso: falta de período não é motivo de recusa.

Unidades:
{linhas}

Ao responder:
- diga qual período e quais filtros foram usados — os que a ferramenta \
devolveu em `filtros_aplicados`, nunca os que você pediu. Em português de \
negócio ("de 01/08 a 31/08, sem filtro de unidade"), nunca com o nome do \
parâmetro;
- o vocabulário é "desvio" e "indício". Nunca escreva "hora extra" — nem \
repetindo a expressão de quem perguntou: o registro oficial é o sistema de ponto, \
e o que este painel aponta é indício;
- seja curto — uma a três frases."""


class Turn:
    """Um turno do assistente, e o registro dele.

    É classe por um motivo só, e ele é o custo: `record` precisa ser legível
    **depois** que o stream terminou — inclusive quando ele terminou porque a
    pessoa fechou a aba no meio da resposta. Um gerador que devolvesse o registro
    como último evento perderia exatamente esse caso, que é o único em que os
    tokens já foram pagos e ninguém ficou sabendo.
    """

    def __init__(
        self,
        tenant: TenantContext,
        question: str,
        model: BaseChatModel,
        *,
        model_name: str = "desconhecido",
    ) -> None:
        self._tenant = tenant
        self._question = question
        self._model = model
        self.record = Record(question=question, model=model_name)

    async def stream(self) -> AsyncIterator[Event]:
        """O turno inteiro, como eventos tipados. A latência fecha em `finally`."""
        inicio = perf_counter()
        try:
            async for evento in self._run():
                yield evento
        finally:
            self.record.latency_ms = int((perf_counter() - inicio) * 1000)

    async def _run(self) -> AsyncIterator[Event]:
        tenant = self._tenant
        record = self.record
        pending = _Pending()

        try:
            metricas = catalogo.from_rows(await executor.load_catalog(tenant))
            alcance = await executor.domains(tenant)
            oferecidas = catalogo.reachable(metricas, alcance)
            unidades = await _units(tenant)
        except Exception:
            logger.exception("assistente: falha ao montar o catálogo do turno")
            yield Event("error", {"message": "Não consegui carregar as métricas agora."})
            return

        nomes = {str(unidade["unit_id"]): unidade["name"] for unidade in unidades}

        async def consultar_metrica(code: str, parameters: dict[str, Any] | None = None) -> str:
            """Consulta uma métrica do catálogo e devolve as linhas encontradas.

            Args:
                code: o código da métrica, exatamente como listado.
                parameters: só os parâmetros que a pergunta pediu, no formato
                    {"nome": valor}. Omita todos os outros — o padrão é sem
                    filtro, e acrescentar um que ninguém pediu dá um número certo
                    para uma pergunta que ninguém fez.
            """
            # `oferecidas`, e não `metricas`: se o modelo chutar o código de uma
            # métrica de domínio sensível, a recusa tem que ser "não tenho essa
            # métrica" e não "você não pode ver essa" — a segunda confirma que
            # existe dado de folha para quem não pode saber que ele existe.
            resposta = catalogo.choose(oferecidas, code, parameters or {}, domains=alcance)
            if isinstance(resposta, Refusal):
                pending.refusal = resposta
                return resposta.reason

            linhas = await executor.execute(tenant, resposta)
            # O que filtrou de verdade, e não o que foi pedido: um parâmetro que
            # o alvo não tem onde ligar sai da consulta em silêncio, e anunciá-lo
            # aqui faria a frase prometer um recorte que não aconteceu.
            aplicados, ignorados = catalogo.effective(resposta)
            legiveis = {k: str(v) for k, v in sorted(aplicados.items())}
            pending.events.append(
                Event(
                    "metrica",
                    {
                        "codigo": resposta.metric.code,
                        "titulo": resposta.metric.title,
                        # Nome, não uuid: o evento existe para a pessoa conferir
                        # o recorte, e `unidade: dede0000-…-a1` não é conferível.
                        # É o que segura o único desvio que o prompt não segura
                        # sozinho — o modelo estreitando o filtro por conta.
                        "parametros": {k: nomes.get(v, v) for k, v in legiveis.items()},
                        "ignorados": list(ignorados),
                        "linhas": len(linhas),
                    },
                )
            )
            record.metric_code = resposta.metric.code
            # O registro guarda o identificador, não o nome: ele é auditoria, e
            # um nome muda quando a unidade é renomeada.
            record.parameters = legiveis
            record.rows_returned = len(linhas)
            return json.dumps(
                {
                    "metrica": resposta.metric.code,
                    "filtros_aplicados": legiveis,
                    "filtros_ignorados": list(ignorados),
                    "aviso": (
                        f"{', '.join(ignorados)} não filtra esta métrica e foi descartado; "
                        f"não diga que a resposta está filtrada por isso."
                        if ignorados
                        else ""
                    ),
                    "linhas": linhas,
                    # Um teto silencioso vira "foram 200" quando foram mais. O
                    # modelo precisa saber para dizer que a lista está cortada.
                    "truncado": len(linhas) >= MAX_ROWS,
                },
                default=_json_default,
                ensure_ascii=False,
            )

        async def recusar(motivo: str) -> str:
            """Declare que nenhuma métrica do catálogo responde a esta pergunta.

            Args:
                motivo: em uma frase, o que exatamente não dá para responder.
            """
            pending.refusal = Refusal("sem_metrica", motivo)
            return motivo

        agent = create_agent(
            self._model,
            # Duas ferramentas, e a segunda existe por causa do que o modelo faz
            # quando acerta. Perguntado sobre folha sem alcançar o domínio, ele
            # recusa sozinho — em prosa, sem chamar nada. A resposta é boa e o
            # `event: recusa` nunca dispara: a UI não sabe que foi recusa e o
            # `app.ai_query` conta a pergunta como respondida. Aí a lista de
            # "métricas que faltam", que é o principal uso desse registro, nasce
            # errada. `recusar` dá ao modelo um jeito tipado de dizer não.
            tools=[consultar_metrica, recusar],
            system_prompt=_prompt(catalogo.describe(oferecidas), unidades, date.today()),
        )

        try:
            async for mode, payload in agent.astream(
                {"messages": [{"role": "user", "content": self._question}]},
                stream_mode=["messages", "updates"],
            ):
                if mode == "messages":
                    chunk, meta = payload
                    # Só o nó do modelo: o nó da ferramenta também emite mensagem,
                    # e ela é o JSON das linhas. Não é resposta para ninguém ler.
                    if meta.get("langgraph_node") != "model":
                        continue
                    if chunk.usage_metadata:
                        record.input_tokens += chunk.usage_metadata.get("input_tokens", 0)
                        record.output_tokens += chunk.usage_metadata.get("output_tokens", 0)
                    if chunk.text:
                        yield Event("token", {"content": chunk.text})
                    continue

                if "tools" not in payload:
                    continue
                for evento in pending.events:
                    yield evento
                pending.events.clear()
                if pending.refusal is not None:
                    record.refused = True
                    record.refusal_reason = pending.refusal.reason
                    yield Event(
                        "recusa",
                        {"codigo": pending.refusal.code, "motivo": pending.refusal.reason},
                    )
                    return
        except Exception:
            # A mensagem do provider não vai para a tela: ela varia por provider,
            # é em inglês, e às vezes carrega o corpo da requisição.
            logger.exception("assistente: falha no turno do modelo")
            yield Event("error", {"message": "Falha ao consultar o modelo. Tente novamente."})
