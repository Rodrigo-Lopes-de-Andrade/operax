"""Todo corpo de requisição recusa campo que ninguém desenhou — e a lista de
exceções não tem sobra.

⛔ POR QUE ISSO É GUARDA DE SUPERFÍCIE, E NÃO HIGIENE DE FORMULÁRIO
`extra="forbid"` é o que faz um parâmetro desconhecido virar 422 em vez de ser
ignorado em silêncio. Sem ele, o cliente pode mandar `tenant_id` no corpo
acreditando que aquilo recorta a escrita — e o servidor, que resolve o tenant do
token, ignora o campo e grava no tenant certo por sorte, não por contrato. Esse é
o modo de falha que este repositório caça em toda camada: *a tela acreditando que
filtra*. O mesmo vale para um campo com erro de digitação, que hoje entra como se
o pedido tivesse sido aceito inteiro.

⚠️ ESTE TESTE NÃO CONSERTA AS OITO ROTAS FROUXAS — ele as PRENDE
Fechá-las é mudança de contrato de API (pedido que hoje é aceito passa a ser
recusado), e isso é decisão do dono, não de quem escreve teste (CLAUDE.md §1).
Enquanto a decisão não vem, a lista abaixo é o retrato exato de quem está de fora:
rota nova frouxa reprova, e rota da lista que fechar também reprova, para que a
lista não envelheça em silêncio — o mesmo cego que `scripts/95_teste_matriz_rh.py`
e `scripts/verificar_docs.py` fecharam em 12 e 26/09/2026.

Nasce do resíduo do C1 (`docs/SPRINTS-CANAIS.md`): *"o teste «sem tenant na URL»
checa só a URL; basta para GET, não cobriria corpo de POST"*. A resposta não é um
teste por tela — são 42 pontos de escrita no frontend — e sim a fronteira onde o
corpo é declarado.
"""

from __future__ import annotations

from typing import Any

from server.main import app

#: As rotas cujo corpo JSON **aceita** campo desconhecido hoje, medidas em
#: 26/09/2026. Não é lista de aprovadas: é a dívida, nomeada, esperando decisão
#: sobre fechar o contrato. Quem fechar uma delas tira o nome daqui.
CORPOS_FROUXOS = {
    "POST /assistente/configuracao/publicar",
    "POST /canais/credencial",
    "POST /canais/telegram/convites",
    "POST /curadoria/fora-do-motor",
    "POST /curadoria/rotacoes",
    "POST /curadoria/unidades",
    "PUT /canais/templates/{code}",
}


def _resolve(schema: dict[str, Any], componentes: dict[str, Any]) -> dict[str, Any]:
    """Segue `$ref` até o objeto — o OpenAPI aponta para `components/schemas`."""
    while "$ref" in schema:
        schema = componentes[schema["$ref"].rsplit("/", 1)[1]]
    return schema


def _corpos_json() -> dict[str, bool]:
    """`{"POST /rota": recusa_campo_extra}` para todo corpo `application/json`.

    Lido do OpenAPI, e não das assinaturas: é o schema que o cliente recebe, e
    `additionalProperties: false` é exatamente como `extra="forbid"` chega lá.
    """
    esquema = app.openapi()
    componentes = esquema.get("components", {}).get("schemas", {})
    corpos: dict[str, bool] = {}

    for caminho, metodos in esquema["paths"].items():
        for metodo, operacao in metodos.items():
            conteudo = (operacao.get("requestBody") or {}).get("content", {})
            corpo = conteudo.get("application/json")
            if corpo is None:
                continue
            resolvido = _resolve(corpo.get("schema", {}), componentes)
            corpos[f"{metodo.upper()} {caminho}"] = resolvido.get("additionalProperties") is False

    return corpos


def test_todo_corpo_novo_recusa_campo_extra() -> None:
    """Rota de escrita nova entra fechada, ou este teste fica vermelho."""
    frouxas = {rota for rota, estrita in _corpos_json().items() if not estrita}

    novas = frouxas - CORPOS_FROUXOS
    assert not novas, (
        "corpo(s) de requisição aceitando campo desconhecido, fora da dívida declarada: "
        f'{sorted(novas)}. O desenho do projeto é `extra="forbid"`: um campo que o '
        "servidor não conhece chegando no corpo é o cliente pedindo algo que ninguém "
        "desenhou — e `tenant_id` é o caso que importa."
    )


def test_a_divida_nao_tem_sobra() -> None:
    """A direção que ninguém escreve: a exceção que deixou de ser exceção."""
    corpos = _corpos_json()

    sumidas = CORPOS_FROUXOS - set(corpos)
    assert not sumidas, (
        f"rota(s) na dívida que não existem mais no OpenAPI: {sorted(sumidas)}. "
        "Apague o nome — lista que sobrevive à rota é furo esperando alguém acreditar nela."
    )

    fechadas = {rota for rota in CORPOS_FROUXOS if corpos[rota]}
    assert not fechadas, (
        f"rota(s) da dívida que JÁ recusam campo extra: {sorted(fechadas)}. "
        "Tire o nome da lista: a dívida foi paga e o registro tem de dizer isso."
    )


def test_a_maioria_ja_e_estrita_e_o_numero_esta_medido() -> None:
    """O positivo ao lado do negativo: sem ele os dois de cima passariam num
    OpenAPI vazio — nenhum corpo, nenhuma reclamação."""
    corpos = _corpos_json()

    assert len(corpos) >= 30, f"só {len(corpos)} corpos JSON no OpenAPI — o schema veio incompleto"
    assert sum(corpos.values()) >= 26, (
        f"{sum(corpos.values())} corpos estritos, e em 26/09/2026 eram 26: "
        "alguma rota afrouxou o contrato dela"
    )
