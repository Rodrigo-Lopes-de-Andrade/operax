"""A foto do colaborador — leitura pelo Caminho 2, sob o domínio `pii`.

Decisão do dono em 04/09/2026, a pedido do cliente: `docs/DECISAO-FOTO-DO-COLABORADOR.md`.
A exclusão anterior era um padrão com destrave nomeado ("fica de fora até o
cliente pedir"), não uma proibição.

**Por que este módulo existe separado, e por que ele faz duas consultas.**

A foto mora em `secullum."Funcionario"."Foto"`, e `authenticated` **não tem
`usage` no schema `secullum`** — de propósito, pela migration 01. Então a leitura
não pode acontecer inteira sob `user_scope`, que é como o resto do RH lê.

A saída não é subir o privilégio da consulta toda. É separar as duas perguntas:

1. **"quem pergunta pode ver esta pessoa?"** — respondida por `user_scope`, com a
   RLS decidindo, exatamente como `load_employee`. É a mesma fronteira do resto
   do produto, e ela continua sendo quem autoriza.
2. **"quais são os bytes?"** — só depois da primeira dizer sim, e aí sim por
   `tenant_scope`, filtrando por `tenant_id` e pelo `secullum_employee_id` que a
   primeira devolveu.

Trocar isso por uma consulta só com `service_role` faria a autorização virar
código em vez de policy — que é a Regra 4 do `CLAUDE.md` ao contrário.

🔴 **Nada aqui loga bytes.** As funções devolvem a imagem ou o metadado; o
`repr` de `bytes` nunca entra em mensagem de erro, e o tamanho é o único número
que sai. Ver §5 da decisão.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from operax.core.tenant import TenantContext, tenant_scope, user_scope


class PhotoState(StrEnum):
    """Os três estados que a ficha precisa distinguir.

    ⚠️ São **três**, não dois, e é o §6 da decisão: um vazio sem explicação numa
    tela de identificação parece defeito. `AUSENTE` é "a origem diz que não há";
    `PENDENTE` é "há, e ainda não buscamos" — no dia da decisão eram ~32 pessoas.
    """

    #: A origem diz que esta pessoa não tem foto. `"PossuiFoto" = false`.
    AUSENTE = "ausente"
    #: A origem diz que há foto, e a fila ainda não a alcançou.
    PENDENTE = "pendente"
    #: Temos a foto. Acompanha a data, porque idade de rosto é dado de tela.
    DISPONIVEL = "disponivel"


@dataclass(frozen=True)
class PhotoInfo:
    """Metadado da foto — **nunca os bytes**. É isto que viaja no JSON da ficha."""

    state: PhotoState
    #: Quando a origem foi lida. `None` fora de `DISPONIVEL`.
    #: A idade do rosto é dado de tela pela mesma disciplina de idade do dado que
    #: vale no resto do produto: rosto de dois anos numa ficha de identificação é
    #: pior que rosto nenhum, e só a data revela.
    synced_at: datetime | None = None


@dataclass(frozen=True)
class Photo:
    """A imagem, para a resposta binária. Não serializa em JSON por desenho."""

    content: bytes
    mime: str
    synced_at: datetime | None


#: Passo 1 — a autorização. Roda como o usuário, então quem responde é a RLS.
#: Devolve `null` tanto para "não existe" quanto para "existe e você não alcança",
#: e a rota transforma os dois em 404 — um 403 confirmaria que a pessoa existe
#: noutra unidade, que é a mesma razão de `load_employee` responder 404.
_AUTORIZA_SQL = """
select e.secullum_employee_id
  from app.employee e
 where e.id = %(employee_id)s
"""

#: ⚠️ O `tenant_id` NÃO viaja nos params: `bind_tenant` o injeta do contexto
#: autenticado, e passá-lo daqui é recusado com "tenant_id comes from the
#: authenticated context, never from the caller". A cláusula fica no SQL; o
#: valor vem de quem provou quem é.
#: Passo 2 — o metadado, já autorizado. `length("Foto")` em vez de `"Foto"`:
#: a coluna não sai daqui quando só se quer saber se ela existe.
_META_SQL = """
select f."PossuiFoto"            as possui,
       f.foto_sincronizada_em    as synced_at,
       length(f."Foto")          as bytes
  from secullum."Funcionario" f
 where f."FuncionarioId" = %(secullum_id)s
   and f.tenant_id       = %(tenant_id)s
"""

#: Passo 2 — os bytes. Única consulta do projeto que seleciona `"Foto"`.
_BYTES_SQL = """
select f."Foto"                  as content,
       f.foto_mime               as mime,
       f.foto_sincronizada_em    as synced_at
  from secullum."Funcionario" f
 where f."FuncionarioId" = %(secullum_id)s
   and f.tenant_id       = %(tenant_id)s
   and f."Foto" is not null
"""


async def _autoriza(tenant: TenantContext, employee_id: UUID) -> int | None:
    """O `FuncionarioId` do espelho, se — e só se — a RLS deixar ver a pessoa."""
    async with user_scope(tenant) as scope:
        await scope.execute(_AUTORIZA_SQL, {"employee_id": str(employee_id)})
        row = await scope.fetchone()
    if row is None or row["secullum_employee_id"] is None:
        return None
    return int(row["secullum_employee_id"])


async def photo_info(tenant: TenantContext, employee_id: UUID) -> PhotoInfo | None:
    """Em qual dos três estados esta pessoa está. `None` = fora de alcance."""
    secullum_id = await _autoriza(tenant, employee_id)
    if secullum_id is None:
        return None

    async with tenant_scope(tenant) as scope:
        await scope.execute(_META_SQL, {"secullum_id": secullum_id})
        row = await scope.fetchone()

    # Sem linha no espelho é o mesmo que a origem não declarar foto: a pessoa
    # existe no domínio e o espelho ainda não a alcançou.
    if row is None or not row["possui"]:
        return PhotoInfo(state=PhotoState.AUSENTE)
    if row["bytes"] is None:
        return PhotoInfo(state=PhotoState.PENDENTE)
    return PhotoInfo(state=PhotoState.DISPONIVEL, synced_at=row["synced_at"])


async def load_photo(tenant: TenantContext, employee_id: UUID) -> Photo | None:
    """A imagem de uma pessoa. `None` = fora de alcance, ou não temos a foto."""
    secullum_id = await _autoriza(tenant, employee_id)
    if secullum_id is None:
        return None

    async with tenant_scope(tenant) as scope:
        await scope.execute(_BYTES_SQL, {"secullum_id": secullum_id})
        row = await scope.fetchone()

    if row is None:
        return None
    return Photo(
        content=bytes(row["content"]),
        # O mime sai da data URI na sincronização. Faltando, `octet-stream`
        # faria o navegador baixar em vez de exibir; `jpeg` é o que a origem
        # entrega em 100% das linhas medidas em 04/09/2026.
        mime=row["mime"] or "image/jpeg",
        synced_at=row["synced_at"],
    )
