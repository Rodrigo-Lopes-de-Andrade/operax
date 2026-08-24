"""The provider contract — `(template, variables, destination)` and nothing else.

Rule 11 of the project, and it is a one-way door. The official Meta Cloud API
accepts an approved template name plus ordered parameters; it does not accept a
sentence. Z-API and uazapi accept free text and have no concept of a template. An
interface shaped around free text can serve the two unofficial ones and can
**never** serve the official one — so the contract is template-first, and turning
a template into text is the provider's problem, not the caller's.

That is why `Message` carries a dict of facts. The renderer below exists for the
unofficial providers, which need the sentence built locally; `meta_cloud` never
calls it, because the sentence lives in the WABA.

`NullProvider` is not a test double. It is what the sender uses while the shadow
gate is open (rule 8): it records what would have gone out and delivers nothing.
A product that can send before its false-positive rate is known is a product that
will send a wrong accusation to a manager, once, and never be trusted again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Protocol

#: `{{1}}`, `{{2}}` — a ordem declarada em `app.message_template.variables`.
_PLACEHOLDER = re.compile(r"\{\{(\d+)\}\}")


@dataclass(frozen=True, slots=True)
class Message:
    """O que se entrega a um provedor. Nunca uma frase pronta."""

    destination: str
    #: `None` para e-mail e resumo livre; obrigatório no provedor oficial.
    template: str | None
    #: A ordem declarada no template, que é o que vira `{{1}}`, `{{2}}`...
    variables: tuple[str, ...]
    #: Os fatos, por nome. O provedor escolhe o que fazer com eles.
    facts: dict[str, str]

    def ordered(self) -> list[str]:
        """Os valores na ordem em que o template os declarou."""
        return [self.facts.get(nome, "") for nome in self.variables]


@dataclass(frozen=True, slots=True)
class Delivery:
    """O que o provedor respondeu. `cost_cents` desde o primeiro envio."""

    status: Literal["sent", "failed"]
    provider_message_id: str | None = None
    error: str | None = None
    cost_cents: int | None = None


class Provider(Protocol):
    """Um canal de saída. O motor conhece esta forma e mais nada."""

    name: str

    async def enviar(self, message: Message) -> Delivery: ...


def render(body: str, message: Message) -> str:
    """`{{n}}` trocado pelo n-ésimo valor declarado — para quem não tem template.

    Placeholder sem valor vira string vazia em vez de ficar literal na mensagem:
    o banco já recusa um corpo que use `{{4}}` declarando três variáveis
    (`util.validate_template_body`), então chegar aqui com um vão é sinal de
    template alterado por fora — e "texto faltando" é menos ruim do que "{{4}}"
    na tela de um gestor.
    """
    valores = message.ordered()

    def trocar(achado: re.Match[str]) -> str:
        indice = int(achado.group(1))
        return valores[indice - 1] if 1 <= indice <= len(valores) else ""

    return _PLACEHOLDER.sub(trocar, body)


@dataclass
class NullProvider:
    """Registra e não entrega. É o que roda enquanto o gate G4 está aberto."""

    name: str = "null"
    sent: list[Message] = field(default_factory=list)

    async def enviar(self, message: Message) -> Delivery:
        self.sent.append(message)
        return Delivery(status="failed", error="gate G4 aberto: nada é entregue em sombra")
