"""A matriz de capacidades lida como matriz — e não provedor por provedor.

Três coisas aqui não são sobre uma linha da tabela:

1. **As duas famílias nunca coexistem.** Um canal com `ban_risk` e
   `requires_templates` ao mesmo tempo seria um canal que pode ser banido por
   dizer exatamente o que foi autorizado a dizer. A asserção existe antes do
   quarto canal de propósito: o candidato a desafiá-la tem *nenhuma* das duas, e
   *nenhuma* passa — é *ambas* que não pode.
2. **Capacidade que ninguém consome é código morto.** O teste percorre a árvore
   sintática do backend procurando quem **lê o atributo** de um valor que veio
   de `capabilities_for` (ou de `CONSERVATIVE_DEFAULT`, ou de um parâmetro
   tipado `ProviderCapabilities`), fora do módulo e fora desta suíte. A palavra
   num docstring, num SQL ou na declaração do campo em `models.py` não é leitura.
   Um campo novo que só a matriz menciona reprova aqui, que é o ponto.
3. **O fail-closed não vira default silencioso.** Provedor desconhecido levanta,
   e o positivo ao lado (os três conhecidos resolvem) é o que impede a versão
   "levanta sempre" de passar.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path

import pytest

from operax.alertas import capacidades, outbox
from operax.alertas.capacidades import (
    CHANNEL_PROVIDERS,
    CONSERVATIVE_DEFAULT,
    WHATSAPP_PROVIDERS,
    ProviderCapabilities,
    UnknownProviderError,
    capabilities_for,
)

#: `backend/` — a raiz da varredura do consumidor.
_BACKEND = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fail-closed, com o positivo ao lado
# ---------------------------------------------------------------------------
def test_provedor_desconhecido_levanta_excecao_nomeada() -> None:
    """Responder "sem restrição" sobre um canal que ninguém declarou é como um
    número banível passa a ser tratado como número seguro."""
    with pytest.raises(UnknownProviderError) as erro:
        capabilities_for("evolution_api")

    assert "evolution_api" in str(erro.value)


def test_os_quatro_conhecidos_resolvem() -> None:
    """O par do teste acima: "levanta sempre" também passaria sem ele."""
    assert set(CHANNEL_PROVIDERS) == {"meta_cloud", "z_api", "uazapi", "telegram"}
    for provider in CHANNEL_PROVIDERS:
        assert isinstance(capabilities_for(provider), ProviderCapabilities)


def test_a_capacidade_nao_e_editavel_depois_de_declarada() -> None:
    """Doutrina que um chamador consegue reescrever em runtime não é doutrina."""
    with pytest.raises(AttributeError):
        capabilities_for("meta_cloud").ban_risk = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# As duas famílias
# ---------------------------------------------------------------------------
def test_o_oficial_e_hetero_restrito_e_os_nao_oficiais_sao_auto_restritos() -> None:
    """`meta_cloud` tem template e não tem banimento; os outros dois, o inverso."""
    oficial = capabilities_for("meta_cloud")
    assert oficial.official is True
    assert oficial.requires_templates is True
    assert oficial.ban_risk is False

    for provider in ("z_api", "uazapi"):
        nao_oficial = capabilities_for(provider)
        assert nao_oficial.official is False
        assert nao_oficial.requires_templates is False
        assert nao_oficial.ban_risk is True


def test_as_duas_familias_nunca_coexistem_na_matriz_inteira() -> None:
    """Sobre toda a matriz, não sobre um provedor: é a asserção que o quarto
    canal vai desafiar, e ela precisa existir antes dele."""
    ambas = [
        provider
        for provider, capabilities in capacidades._CAPABILITIES.items()
        if capabilities.requires_templates and capabilities.ban_risk
    ]

    assert ambas == [], (
        f"{ambas} declara auto-restrição e hetero-restrição ao mesmo tempo: "
        "seria um canal banível por dizer o que foi autorizado a dizer"
    )


def test_o_telegram_e_a_terceira_familia_e_nenhum_whatsapp_esta_nela() -> None:
    """SPEC-CANAIS §1.1: o Telegram não tem NENHUMA das duas — e "nenhuma" não é
    "sem regra". A restrição dele é de destinatário: só alcança quem abriu o
    bot. Os três de WhatsApp endereçam um número que o empregador já tem, e por
    isso não carregam a terceira; se um dia carregarem, o sender passaria a
    exigir adesão de quem nunca precisou aderir."""
    telegram = capabilities_for("telegram")
    assert telegram.requires_templates is False
    assert telegram.ban_risk is False
    assert telegram.requires_recipient_opt_in is True

    for provider in WHATSAPP_PROVIDERS:
        assert capabilities_for(provider).requires_recipient_opt_in is False, provider

    assert "telegram" not in WHATSAPP_PROVIDERS


# ---------------------------------------------------------------------------
# O default declarado
# ---------------------------------------------------------------------------
def test_o_default_declarado_e_o_conservador() -> None:
    """Errar para o lado do `meta_cloud` desarmaria o anti-ban num número que
    pode ser banido — e disso não se volta. Template recusado se conserta."""
    assert CONSERVATIVE_DEFAULT.ban_risk is True
    assert CONSERVATIVE_DEFAULT.official is False
    assert CONSERVATIVE_DEFAULT != capabilities_for("meta_cloud")


def test_o_default_e_o_que_os_nao_oficiais_realmente_sao() -> None:
    """A suposição temerosa e a resposta dos dois não oficiais são a mesma
    resposta. Escrita duas vezes, ela divergiria na primeira edição."""
    assert capabilities_for("z_api") is CONSERVATIVE_DEFAULT
    assert capabilities_for("uazapi") is CONSERVATIVE_DEFAULT


# ---------------------------------------------------------------------------
# A lista de provedores de WhatsApp
# ---------------------------------------------------------------------------
def test_todo_provedor_de_whatsapp_esta_na_matriz() -> None:
    """A lista alimenta a consulta que descobre o provedor ativo do cliente;
    um nome nela que a matriz não conhece derrubaria a tela de Conexões."""
    for provider in WHATSAPP_PROVIDERS:
        assert capabilities_for(provider) is not None


def _names_in(clause: str) -> set[str]:
    """Os nomes entre aspas simples do `provider in (...)` de `clause`."""
    achado = re.search(r"provider in \(([^)]*)\)", clause)
    assert achado is not None, clause
    return set(re.findall(r"'([^']*)'", achado.group(1)))


def test_a_lista_de_whatsapp_e_a_mesma_do_indice_parcial(
    last_migration_with: Callable[[str], str],
) -> None:
    """`integration_whatsapp_unico_ativo` é quem garante um provedor ativo por
    cliente, e é a **última** migration que o define que vale — a aplicada não
    se edita. Igualdade nos dois sentidos: um nome a mais na lista é um provedor
    que o índice deixa duplicar; um a menos é um cliente para quem `enqueue`
    resolve `provider = None`, grava a fila com provedor nulo e o sender
    descarta — nenhum alerta, sem exceção."""
    marcador = "create unique index if not exists integration_whatsapp_unico_ativo"
    indice = last_migration_with(marcador).split(marcador, 1)[1].split(";", 1)[0]

    assert _names_in(indice) == set(WHATSAPP_PROVIDERS)


def test_a_lista_de_whatsapp_e_a_mesma_que_a_funcao_de_prontidao_reconhece(
    last_migration_with: Callable[[str], str],
) -> None:
    """A CTE `prov` de `fn_whatsapp_readiness` é a terceira cópia da lista, e é
    ela que diz à tela de Conexões qual provedor está ativo. Divergindo da
    tupla, a tela mostra um provedor que o `enqueue` não vê — ou o inverso."""
    marcador = "create or replace function public.fn_whatsapp_readiness"
    funcao = last_migration_with(marcador).split(marcador, 1)[1]
    prov = funcao.split("prov as (", 1)[1]

    assert _names_in(prov) == set(WHATSAPP_PROVIDERS)


def test_a_consulta_do_provedor_ativo_renderiza_exatamente_a_lista() -> None:
    """`outbox._PROVIDER_SQL` nasce da tupla em import time, como literal.

    Exatamente os nomes, na ordem, cada um entre aspas simples — nem um a mais,
    nem sem aspas (viraria coluna), nem a tupla inteira colada (`str(tuple)`
    vira um registro, e o driver responde com `malformed array literal`).
    """
    achado = re.search(r"provider in \(([^)]*)\)", outbox._PROVIDER_SQL)
    assert achado is not None, outbox._PROVIDER_SQL

    itens = [item.strip() for item in achado.group(1).split(",")]
    assert itens == [f"'{provider}'" for provider in WHATSAPP_PROVIDERS]


# ---------------------------------------------------------------------------
# Capacidade que ninguém consome é código morto
# ---------------------------------------------------------------------------
def _backend_sources() -> list[Path]:
    """Todo `.py` de `operax/` e `server/`, menos o próprio módulo.

    A suíte fica de fora porque senão o teste seria o consumidor: uma capacidade
    lida só por quem a testa continua sendo código morto com verde em cima.
    """
    modulo = Path(capacidades.__file__).resolve()
    return [
        caminho
        for pacote in ("operax", "server")
        for caminho in (_BACKEND / pacote).rglob("*.py")
        if caminho.resolve() != modulo and "__pycache__" not in caminho.parts
    ]


def _yields_capabilities(node: ast.AST, bound: set[str]) -> bool:
    """`capabilities_for(...)`, `CONSERVATIVE_DEFAULT`, ou um nome ligado a um deles."""
    if isinstance(node, ast.Call):
        func = node.func
        return (isinstance(func, ast.Name) and func.id == "capabilities_for") or (
            isinstance(func, ast.Attribute) and func.attr == "capabilities_for"
        )
    return isinstance(node, ast.Name) and (node.id == "CONSERVATIVE_DEFAULT" or node.id in bound)


def _capability_reads(caminho: Path) -> set[str]:
    """Os atributos lidos, neste arquivo, de um valor que é uma capacidade."""
    tree = ast.parse(caminho.read_text(encoding="utf-8"))
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _yields_capabilities(node.value, bound):
            bound |= {alvo.id for alvo in node.targets if isinstance(alvo, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None and _yields_capabilities(node.value, bound):
                bound.add(node.target.id)
        elif isinstance(node, ast.arg) and isinstance(node.annotation, ast.Name):
            if node.annotation.id == "ProviderCapabilities":
                bound.add(node.arg)
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and _yields_capabilities(node.value, bound)
    }


@pytest.mark.parametrize("capability", [campo.name for campo in fields(ProviderCapabilities)])
def test_toda_capacidade_declarada_tem_consumidor(capability: str) -> None:
    """Capacidade que ninguém lê é a diferença entre canais virando comentário.

    Consumidor é quem lê `.<capacidade>` de um valor que veio da matriz — não
    quem escreve a palavra. `readiness["official"]` na rota não é consumo da
    matriz, é a coluna da função; `official: bool` em `models.py` é declaração.
    """
    consumidores = [
        caminho.relative_to(_BACKEND).as_posix()
        for caminho in _backend_sources()
        if capability in _capability_reads(caminho)
    ]

    assert consumidores, (
        f"a capacidade {capability!r} não é lida em lugar nenhum do backend: "
        "ou alguém a consome, ou ela não deveria estar declarada"
    )


# ---------------------------------------------------------------------------
# A doutrina como teste, não como disciplina
# ---------------------------------------------------------------------------
_PROVIDER_NAMES = set(CHANNEL_PROVIDERS)

#: Onde os nomes podem aparecer como literal: a matriz, que é o dono, e os
#: módulos de `provedores/` — cada um é dono do próprio `NAME`, como `base.py`
#: já era do docstring que os cita. A contrapartida está em
#: `tests/test_canais_credencial.py`: `set(PROVIDERS) == set(WHATSAPP_PROVIDERS)`
#: nos dois sentidos, para que um módulo a mais ou a menos não passe calado.
_LITERAL_ALLOWED = {
    _BACKEND / "operax" / "alertas" / "capacidades.py",
    *(_BACKEND / "operax" / "alertas" / "provedores").glob("*.py"),
}


def _string_literals(caminho: Path) -> set[str]:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    return {
        no.value
        for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, str)
    }


def test_nenhum_arquivo_do_backend_escreve_um_provedor_como_literal() -> None:
    """A SPEC-CANAIS §1 é explícita: nenhum arquivo fora do módulo de capacidades
    escreve um provedor como string. Foi um `if provider == "meta_cloud"` na rota
    que a revisão do ciclo 2 mostrou passar verde — o "único lugar com essas
    strings" era disciplina, e disciplina não reprova ninguém. Este teste percorre
    o `ast` de `operax/` e `server/`; docstrings contam como literal e são
    permitidas só no contrato de provedor, que as usa como exemplo."""
    ofensores: dict[str, set[str]] = {}
    for pasta in ("operax", "server"):
        for caminho in (_BACKEND / pasta).rglob("*.py"):
            if caminho in _LITERAL_ALLOWED:
                continue
            achados = _string_literals(caminho) & _PROVIDER_NAMES
            if achados:
                ofensores[str(caminho.relative_to(_BACKEND))] = achados

    assert ofensores == {}, f"provedor escrito como literal fora da matriz: {ofensores}"


def test_o_sender_conhece_todo_provedor_de_whatsapp_da_matriz() -> None:
    """Desde o C5 o sender não tem mapa próprio: ele carrega as integrações
    ativas de `CHANNEL_PROVIDERS` e constrói cada uma pela fábrica. Um provedor
    que a matriz conhece e a lista não faz toda linha daquele canal virar
    `failed` "provedor não configurado" — degrada bem, e por isso ninguém vê.
    A lista é a da matriz, por identidade, e as chaves do cofre saem do módulo
    de cada um."""
    from operax.alertas import sender

    assert sender.CHANNEL_PROVIDERS is CHANNEL_PROVIDERS
    assert set(WHATSAPP_PROVIDERS) <= set(sender.CHANNEL_PROVIDERS)
    assert "list(CHANNEL_PROVIDERS)" in Path(sender.__file__).read_text(encoding="utf-8")
    for provider in WHATSAPP_PROVIDERS:
        assert sender._secret_keys(provider)
