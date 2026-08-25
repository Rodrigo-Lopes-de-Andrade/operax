"""O provider falso do E2E. Nada aqui roda quando `E2E_FAKE_LLM` não está ligado.

Existe porque o assistente é a única parte do produto cujo comportamento depende
de um serviço pago e não determinístico, e porque o que o E2E precisa provar não
é a qualidade da frase: é que o `text/event-stream` atravessa uvicorn, chega ao
`ReadableStream` do navegador e vira texto na tela. Isso é transporte, e um
modelo de verdade só acrescenta latência e variação a essa prova.

O QUE ELE NÃO CONTORNA
Nada da fronteira. Este falso escolhe um `code` e devolve parâmetros como
qualquer modelo escolheria; quem aprova continua sendo `catalogo.choose`, e quem
executa continua sendo `executor.execute`, como o usuário e sob RLS. Se a
variável vazasse para produção, o sintoma seria o assistente respondendo frases
bobas — não dado saindo por uma porta nova. É por isso que o desvio fica aqui, no
`build_model`, e não dentro do turno.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import date
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

#: A variável que liga isto. Uma só, e comparada com "1" — um valor qualquer
#: ligando um provider falso é um jeito de ligá-lo sem querer.
FLAG = "E2E_FAKE_LLM"
MODEL_ID = "e2e-fake"

#: Perguntas que caem na recusa. É o outro caminho que a tela precisa exercitar,
#: e ele tem de ser alcançável por uma frase que uma pessoa escreveria.
_SEM_METRICA = ("folha", "salári", "salario", "remunera")


class E2EChatModel(BaseChatModel):
    """Determinístico, sem rede, e com os dois desfechos que a tela desenha."""

    @property
    def _llm_type(self) -> str:
        return "operax-e2e"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> E2EChatModel:
        return self

    def _decide(self, messages: list[BaseMessage]) -> AIMessage:
        anterior = messages[-1] if messages else None

        if isinstance(anterior, ToolMessage):
            return AIMessage(content=_frase(str(anterior.content)))

        pergunta = _ultima_pergunta(messages).lower()

        if any(termo in pergunta for termo in _SEM_METRICA):
            return _chamada(
                "recusar",
                {"motivo": "Nenhuma métrica do catálogo responde sobre folha."},
            )

        hoje = date.today()
        return _chamada(
            "consultar_metrica",
            {
                "code": "deviations_total",
                "parameters": {
                    "start_date": hoje.replace(day=1).isoformat(),
                    "end_date": hoje.isoformat(),
                },
            },
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._decide(messages))])

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        mensagem = self._decide(messages)

        if mensagem.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": chamada["name"],
                            "args": json.dumps(chamada["args"]),
                            "id": chamada["id"],
                            "index": 0,
                            "type": "tool_call_chunk",
                        }
                        for chamada in mensagem.tool_calls
                    ],
                )
            )
            return

        # Em pedaços de propósito: um stream que chega inteiro não prova que o
        # `ReadableStream` do outro lado remonta quadro partido.
        for pedaco in _pedacos(mensagem.text):
            chunk = AIMessageChunk(content=pedaco)
            if run_manager is not None:
                await run_manager.on_llm_new_token(pedaco, chunk=ChatGenerationChunk(message=chunk))
            yield ChatGenerationChunk(message=chunk)

        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            )
        )


def _chamada(nome: str, argumentos: dict[str, Any]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": nome, "args": argumentos, "id": f"e2e-{nome}", "type": "tool_call"}],
    )


def _ultima_pergunta(messages: list[BaseMessage]) -> str:
    for mensagem in reversed(messages):
        if mensagem.type == "human":
            return mensagem.text
    return ""


def _frase(resultado: str) -> str:
    """A resposta a partir do que a ferramenta devolveu de verdade.

    Não é enfeite: o número na tela sai do banco, atravessa a RLS e volta. Um
    texto fixo aqui faria o E2E passar com a consulta quebrada.
    """
    try:
        linhas = json.loads(resultado).get("linhas", [])
    except (json.JSONDecodeError, AttributeError):
        return "Não consegui ler o resultado da consulta."
    if linhas and "eventos" in linhas[0]:
        return f"Foram {linhas[0]['eventos']} desvios no período consultado."
    return f"Encontrei {len(linhas)} registro(s) de desvio no período consultado."


def _pedacos(texto: str, tamanho: int = 8) -> Iterator[str]:
    for inicio in range(0, len(texto), tamanho):
        yield texto[inicio : inicio + tamanho]
