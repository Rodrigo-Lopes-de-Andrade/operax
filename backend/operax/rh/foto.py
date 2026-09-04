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

import hashlib
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


class PhotoOrigin(StrEnum):
    """De onde veio o rosto que está sendo exibido.

    ⚠️ **A origem vence na exibição** (§4-ter). O espelho é o registro de
    identidade; a foto enviada é tapa-buraco de uma lacuna da origem, e quando a
    origem preenche ela é mais provavelmente a atual. O inverso — rosto
    desatualizado sobrevivendo a uma origem corrigida — é o pior dos dois erros.
    """

    SECULLUM = "secullum"
    MANUAL = "manual"


@dataclass(frozen=True)
class Superseded:
    """A foto enviada que a origem substituiu. **Nunca apagada** (§4-ter)."""

    uploaded_at: datetime
    uploaded_by_name: str | None


@dataclass(frozen=True)
class PhotoInfo:
    """Metadado da foto — **nunca os bytes**. É isto que viaja no JSON da ficha."""

    state: PhotoState
    #: `None` quando não há foto nenhuma.
    origin: PhotoOrigin | None = None
    #: Quando a origem foi lida. `None` fora de `DISPONIVEL`.
    #: A idade do rosto é dado de tela pela mesma disciplina de idade do dado que
    #: vale no resto do produto: rosto de dois anos numa ficha de identificação é
    #: pior que rosto nenhum, e só a data revela.
    synced_at: datetime | None = None
    #: Quando o DP enviou, se o que se vê é a manual.
    uploaded_at: datetime | None = None
    uploaded_by_name: str | None = None
    #: Preenchido só quando a origem passou a ter foto DEPOIS de alguém enviar
    #: uma. É o que faz a ficha dizer "substituiu a foto enviada em DD/MM por
    #: [autor]" — porque trocar o rosto em silêncio é o erro que a revisão pegou.
    superseded: Superseded | None = None
    #: A tela só oferece o envio onde a origem declara não ter (§4-ter): assim as
    #: duas fontes não se sobrepõem por construção.
    can_upload: bool = False


@dataclass(frozen=True)
class Photo:
    """A imagem, para a resposta binária. Não serializa em JSON por desenho."""

    content: bytes
    mime: str
    origin: PhotoOrigin
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


#: A foto enviada que está ativa, com quem a enviou. `superseded_at is null` é a
#: cláusula inteira de "é esta que vale" — o índice único parcial garante uma só.
_MANUAL_META_SQL = """
select m.uploaded_at,
       u.email                as uploaded_by_name,
       length(m.content)      as bytes,
       m.superseded_at
  from app.employee_photo m
  left join auth.users u on u.id = m.uploaded_by
 where m.employee_id = %(employee_id)s
   and m.tenant_id   = %(tenant_id)s
 order by m.superseded_at nulls first, m.uploaded_at desc
 limit 1
"""

_MANUAL_BYTES_SQL = """
select m.content, m.mime, m.uploaded_at
  from app.employee_photo m
 where m.employee_id   = %(employee_id)s
   and m.tenant_id     = %(tenant_id)s
   and m.superseded_at is null
"""

#: Grava a foto enviada. ⛔ Sem `on conflict`: o índice único parcial é quem
#: recusa a segunda ativa, e recusar alto é o certo — sobrescrever em silêncio a
#: foto que outra pessoa enviou é o mesmo pecado da substituição silenciosa.
_MANUAL_INSERT_SQL = """
insert into app.employee_photo
       (tenant_id, employee_id, content, mime, bytes, sha256, uploaded_by)
select %(tenant_id)s, %(employee_id)s, %(content)s, %(mime)s,
       length(%(content)s::bytea), %(sha256)s, %(uploaded_by)s
returning id, uploaded_at
"""

#: Carimba a manual quando a origem passa a ter foto. A linha FICA (§4-ter).
_SUPERSEDE_SQL = """
update app.employee_photo
   set superseded_at     = now(),
       superseded_reason = %(reason)s
 where employee_id   = %(employee_id)s
   and tenant_id     = %(tenant_id)s
   and superseded_at is null
returning id
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
    """Em qual estado esta pessoa está, e de qual fonte. `None` = fora de alcance.

    ⚠️ **A precedência é a da §4-ter e não é simétrica:** a origem vence na
    exibição, e a foto enviada nunca é apagada — vira `superseded`, que a ficha
    mostra. Trocar o rosto que o DP escolheu em silêncio é o erro que a revisão
    apontou, e é por isso que este metadado carrega os dois lados.
    """
    secullum_id = await _autoriza(tenant, employee_id)
    if secullum_id is None:
        return None

    async with tenant_scope(tenant) as scope:
        await scope.execute(_META_SQL, {"secullum_id": secullum_id})
        origem = await scope.fetchone()
        await scope.execute(_MANUAL_META_SQL, {"employee_id": str(employee_id)})
        manual = await scope.fetchone()

    tem_origem = bool(origem and origem["possui"] and origem["bytes"] is not None)
    origem_declara = bool(origem and origem["possui"])
    manual_ativa = bool(manual and manual["superseded_at"] is None)

    if tem_origem:
        # A origem venceu. Se havia uma enviada e ela ainda não foi carimbada,
        # quem carimba é o `upload`/`supersede` — aqui só se REPORTA, para que a
        # leitura não escreva.
        substituida = (
            Superseded(
                uploaded_at=manual["uploaded_at"],
                uploaded_by_name=manual["uploaded_by_name"],
            )
            if manual
            else None
        )
        return PhotoInfo(
            state=PhotoState.DISPONIVEL,
            origin=PhotoOrigin.SECULLUM,
            synced_at=origem["synced_at"],
            superseded=substituida,
        )

    if manual_ativa:
        return PhotoInfo(
            state=PhotoState.DISPONIVEL,
            origin=PhotoOrigin.MANUAL,
            uploaded_at=manual["uploaded_at"],
            uploaded_by_name=manual["uploaded_by_name"],
        )

    # Sem foto de lado nenhum. Os dois estados que sobram são o §6: "a origem diz
    # que não tem" e "a origem diz que tem, e a fila não chegou". Só o primeiro
    # aceita envio — no segundo a origem vai preencher sozinha, e permitir enviar
    # ali criaria a sobreposição que a §4-ter evita por construção.
    if origem_declara:
        return PhotoInfo(state=PhotoState.PENDENTE)
    return PhotoInfo(state=PhotoState.AUSENTE, can_upload=True)


async def load_photo(tenant: TenantContext, employee_id: UUID) -> Photo | None:
    """A imagem: origem primeiro, enviada como fallback. `None` = não há."""
    secullum_id = await _autoriza(tenant, employee_id)
    if secullum_id is None:
        return None

    async with tenant_scope(tenant) as scope:
        await scope.execute(_BYTES_SQL, {"secullum_id": secullum_id})
        row = await scope.fetchone()
        if row is not None:
            return Photo(
                content=bytes(row["content"]),
                # O mime sai da data URI na sincronização. Faltando, `jpeg` é o
                # que a origem entrega em 100% das linhas medidas em 04/09/2026.
                mime=row["mime"] or "image/jpeg",
                origin=PhotoOrigin.SECULLUM,
                synced_at=row["synced_at"],
            )

        await scope.execute(_MANUAL_BYTES_SQL, {"employee_id": str(employee_id)})
        row = await scope.fetchone()

    if row is None:
        return None
    return Photo(
        content=bytes(row["content"]),
        mime=row["mime"],
        origin=PhotoOrigin.MANUAL,
        synced_at=row["uploaded_at"],
    )


# ---------------------------------------------------------------------------
# Imputação — §4-ter. Escrita de dado biométrico NOVO, não espelhamento.
# ---------------------------------------------------------------------------

#: Assinaturas de arquivo. ⛔ O mime é decidido pelo CONTEÚDO, nunca pelo que o
#: cliente declara: `Content-Type` é campo de quem envia, e aceitar a palavra
#: dele sobre o que os bytes são é como confiar no nome da extensão. O mesmo
#: princípio que o `sync-fotos` aplica na origem — lá o *magic number* confere e,
#: divergindo, o conteúdo vence.
_ASSINATURAS: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)

#: O mesmo teto do `check` da migration 36. Repetido aqui de propósito: recusar
#: com mensagem antes de o banco recusar com `check_violation` é a diferença
#: entre "arquivo grande demais" e um 500.
MAX_BYTES = 5 * 1024 * 1024


class UploadRecusadoError(Exception):
    """Motivo legível para a tela. Nunca carrega bytes."""


def detectar_mime(content: bytes) -> str:
    """O que os bytes SÃO. Levanta `UploadRecusadoError` se não for imagem aceita."""
    for assinatura, mime in _ASSINATURAS:
        if content.startswith(assinatura):
            return mime
    raise UploadRecusadoError("O arquivo não é uma imagem JPEG ou PNG.")


async def upload_photo(
    tenant: TenantContext,
    employee_id: UUID,
    content: bytes,
    uploaded_by: UUID | None,
) -> PhotoInfo | None:
    """Grava a foto enviada pelo DP. `None` = pessoa fora de alcance.

    ⛔ **Só onde a origem declara não ter** (§4-ter). Recusar aqui é o que faz as
    duas fontes não se sobreporem por construção — sem isso, precedência deixaria
    de ser regra de exibição e viraria disputa de escrita.
    """
    if not content:
        raise UploadRecusadoError("Arquivo vazio.")
    if len(content) > MAX_BYTES:
        raise UploadRecusadoError(
            f"A imagem tem {len(content) // 1024} KB; o limite é {MAX_BYTES // 1024} KB."
        )
    mime = detectar_mime(content)

    secullum_id = await _autoriza(tenant, employee_id)
    if secullum_id is None:
        return None

    async with tenant_scope(tenant) as scope:
        await scope.execute(_META_SQL, {"secullum_id": secullum_id})
        origem = await scope.fetchone()
        if origem and origem["possui"]:
            # Inclui o caso PENDENTE: a origem vai preencher sozinha, e aceitar
            # aqui criaria a sobreposição que a §4-ter evita.
            raise UploadRecusadoError(
                "O sistema de ponto declara que esta pessoa tem foto — "
                "a imputação existe só para quem a origem diz não ter."
            )

        await scope.execute(_MANUAL_META_SQL, {"employee_id": str(employee_id)})
        manual = await scope.fetchone()
        if manual and manual["superseded_at"] is None:
            raise UploadRecusadoError("Esta pessoa já tem uma foto enviada.")

        await scope.execute(
            _MANUAL_INSERT_SQL,
            {
                "employee_id": str(employee_id),
                "content": content,
                "mime": mime,
                # sha256 dos BYTES, nunca do base64 — o mesmo contrato do espelho,
                # para que as duas fotos sejam comparáveis sem decodificar.
                "sha256": hashlib.sha256(content).hexdigest(),
                "uploaded_by": str(uploaded_by) if uploaded_by else None,
            },
        )
        await scope.fetchone()

    return await photo_info(tenant, employee_id)


async def supersede_manual(tenant: TenantContext, employee_id: UUID) -> bool:
    """Carimba a foto enviada quando a origem passou a ter a dela.

    ⛔ **Carimba, não apaga** (§4-ter). A linha fica para a ficha poder dizer
    "substituiu a foto enviada em DD/MM por [autor]" — troca silenciosa é
    exatamente o que esta função existe para não fazer.
    """
    async with tenant_scope(tenant) as scope:
        await scope.execute(
            _SUPERSEDE_SQL,
            {
                "employee_id": str(employee_id),
                "reason": "o sistema de ponto passou a ter foto desta pessoa",
            },
        )
        return await scope.fetchone() is not None
