"""Um modelo de chat com roteiro, para exercitar o agente sem provider.

`GenericFakeChatModel` do `langchain_core` não serve: `bind_tools` levanta
`NotImplementedError`, e o agente inteiro deste projeto existe em volta de uma
ferramenta. Então o falso mora aqui, e ele faz as três coisas que o `create_agent`
precisa: aceita `bind_tools`, devolve uma mensagem por chamada e **transmite** —
sem streaming não existe evento `token` para testar.

O roteiro é uma lista de `AIMessage`: uma com `tool_calls` para o turno em que o
modelo escolhe a métrica, outra com texto para o turno em que ele responde.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolCallChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


class ScriptExhaustedError(AssertionError):
    """O agente chamou o modelo mais vezes do que o roteiro previa.

    É `AssertionError` de propósito: um laço de ferramenta que não termina é
    exatamente o que este falso tem de denunciar, e não silenciar com uma
    resposta vazia.
    """


class FakeChatModel(BaseChatModel):
    """Devolve as mensagens do roteiro, uma por chamada, em pedaços."""

    responses: list[AIMessage]
    #: Quando presente, a chamada levanta em vez de responder — o caminho do
    #: `event: error`.
    raises: Exception | None = None
    #: O que o agente mandou, por chamada. É onde um teste confere o prompt.
    calls: list[list[BaseMessage]] = []

    model_config = {"arbitrary_types_allowed": True}

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> FakeChatModel:
        return self

    def _next(self, messages: list[BaseMessage]) -> AIMessage:
        if self.raises is not None:
            raise self.raises
        self.calls.append(list(messages))
        if not self.responses:
            raise ScriptExhaustedError(
                f"modelo chamado {len(self.calls)}x e o roteiro tinha menos respostas"
            )
        return self.responses.pop(0)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next(messages))])

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        mensagem = self._next(messages)
        uso = mensagem.usage_metadata

        if mensagem.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        ToolCallChunk(
                            name=chamada["name"],
                            args=json.dumps(chamada["args"]),
                            id=chamada["id"],
                            index=indice,
                        )
                        for indice, chamada in enumerate(mensagem.tool_calls)
                    ],
                    usage_metadata=uso,
                )
            )
            return

        for pedaco in _pedacos(mensagem.text):
            chunk = AIMessageChunk(content=pedaco)
            if run_manager is not None:
                await run_manager.on_llm_new_token(pedaco, chunk=ChatGenerationChunk(message=chunk))
            yield ChatGenerationChunk(message=chunk)
        if uso is not None:
            yield ChatGenerationChunk(message=AIMessageChunk(content="", usage_metadata=uso))


def _pedacos(texto: str, tamanho: int = 4) -> Iterator[str]:
    """O texto em fatias, para que o teste veja mais de um `token`."""
    for inicio in range(0, len(texto), tamanho):
        yield texto[inicio : inicio + tamanho]
