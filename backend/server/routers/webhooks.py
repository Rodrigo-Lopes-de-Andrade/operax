"""O webhook do Telegram — a única superfície pública sem usuário (SPEC-CANAIS §6).

Quem chama é a plataforma, não uma pessoa com JWT. Então esta rota não tem
`CurrentTenant`, não aparece no OpenAPI, e trata **tudo** que recebe como dado
hostil: o caminho, o header, o corpo. A ordem dos passos é o contrato, e cada
um tem teste em `tests/test_canais_webhook.py`:

1. **rate limit por IP** — excedido, 429 sem corpo;
2. **resolver a integração pelo `path_token`** (`core.tenant.context_for_webhook`,
   o segundo SQL do backend que atravessa tenants, dito em voz alta lá). Não
   achou → 404 seco. O token não vai para o log: conta-se num contador de módulo;
3. **rate limit por `path_token`** — a segunda instância;
4. **o header `X-Telegram-Bot-Api-Secret-Token`**, comparado com o
   `webhook_secret` do cofre por `hmac.compare_digest`, **antes de ler o corpo**.
   Ausente ou diferente → 404 seco (não 401/403: quem não tem o segredo não
   recebe a confirmação de que o endereço existe). O `tenant_scope` que lê o
   segredo fecha antes do `await request.body()`;
5. só então o corpo: JSON, `message.chat.type == 'private'`, `message.chat.id`
   inteiro, `message.text` como `/start <token>`. Qualquer outro update é 200
   vazio e um `logger.info` com o **tipo** — nunca o texto, nunca o `chat_id`,
   nunca o `from`. **O bot não responde** (§6: o assistente não está do outro
   lado, e um bot que responde é o primeiro passo para ligar os dois);
6. `/start <token>`: uma transação — o convite por `sha256(token)` com
   `for update`, três recusas distinguíveis no log pelo código
   (`invite_unknown`, `invite_expired`, `invite_used`), e no válido: `used_at`,
   a identidade vigente anterior do mesmo titular revogada (`novo /start`), a
   nova inserida, e uma linha de auditoria **sem `chat_id`**. Se o índice de
   `external_id` vigente recusar — o mesmo `chat_id` já é de outra pessoa do
   tenant (o irmão da regra 7, §3.4) — a transação volta inteira, o convite
   **não** é consumido, e o código é `chat_in_use`;
7. nenhum eco do corpo em log ou erro: o parse que falha vira 200 vazio com
   `"corpo inválido"`, sem o corpo.

POR QUE `chat.type == 'private'`
A regra 7 diz que alerta de conteúdo individual nunca vai para grupo. Um
`/start` disparado num grupo traria o `chat_id` do grupo, e uma identidade
com esse `external_id` faria o sender entregar o alerta individual da pessoa
ao grupo inteiro — pela porta que `util.validate_alert_target` não vigia,
porque ela olha `contact.type`. Só chat privado vincula.

POR QUE 200 PARA O QUE SE RECUSA
O Telegram reenvia o que não recebe 200. Um convite expirado devolvido como
4xx viraria o mesmo update batendo aqui a cada poucos segundos até desistir.
Recusa é resposta: fica no log com o código, e a plataforma para.

⛔ O `chat_id` NUNCA SAI (§3.2)
Entra como `external_id` da identidade e em lugar nenhum mais: não no log
(nem em DEBUG), não na auditoria (`depois` leva canal e convite), não na
resposta (que é vazia). `tests/test_canais_webhook.py` varre os três com um
`chat_id` de sonda em todo cenário.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request, Response, status
from psycopg import errors
from psycopg.types.json import Jsonb

from operax.alertas.provedores import telegram
from operax.core.tenant import SystemContext, context_for_webhook, tenant_scope
from operax.core.vault import read_secret
from server.ratelimit import RateLimiter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"], include_in_schema=False)

TASK = "telegram-webhook"
CHANNEL = telegram.NAME

#: O header que a plataforma devolve com o `secret_token` do `setWebhook`.
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

#: A chave do cofre em que `POST /canais/telegram/conectar` guardou o segredo.
#: O mesmo literal de `canais._WEBHOOK_SECRET_KEY`; um teste prende a igualdade.
WEBHOOK_SECRET_KEY = "webhook_secret"

#: Os dois tetos, por minuto. Todo tráfego legítimo vem de poucos IPs do
#: Telegram — para todos os tenants —, então o de IP é o generoso: protege o
#: banco de um scanner, não a plataforma de si mesma. O de token é o que um
#: membro que copiou a URL de Conexões encontra se resolver martelar.
_IP_LIMIT = 300
_TOKEN_LIMIT = 120
_WINDOW_SECONDS = 60.0

#: A forma de um `path_token` (`secrets.token_urlsafe(24)` → 32 caracteres) e
#: do token do convite. O que não tem a forma não chega ao banco.
_PATH_TOKEN = re.compile(r"[A-Za-z0-9_\-]{16,128}")
_START = re.compile(r"/start (?P<token>[A-Za-z0-9_\-]{16,128})")

_REVOKED_REASON = "novo /start"

_ip_limiter = RateLimiter(limit=_IP_LIMIT, window=_WINDOW_SECONDS)
_token_limiter = RateLimiter(limit=_TOKEN_LIMIT, window=_WINDOW_SECONDS)

#: Quantas vezes um `path_token` que não existe bateu aqui — um número para o
#: operador olhar, no lugar de um log por requisição que carregaria o token.
unknown_path_tokens = 0

# ---------------------------------------------------------------------------
# O passo 6 em SQL — `scripts/97_teste_canais.py` executa as cinco contra o banco
# ---------------------------------------------------------------------------
#: O convite pelo hash, travado: dois `/start` do mesmo link ao mesmo tempo
#: esperam um pelo outro, e o segundo o encontra usado. `expired` é decidido
#: pelo relógio do banco, o mesmo que preencheu `expires_at`.
_INVITE_SQL = """
    select id, contact_id, employee_id, used_at, (expires_at <= now()) as expired
    from app.messaging_invite
    where tenant_id = %(tenant_id)s
      and channel = %(channel)s
      and token_hash = %(token_hash)s
    for update
"""

_CONSUME_INVITE_SQL = """
    update app.messaging_invite
       set used_at = now()
     where tenant_id = %(tenant_id)s
       and id = %(invite_id)s
       and used_at is null
    returning id
"""

#: A vigente anterior do MESMO titular — `is not distinct from` casa o par
#: exato, com o lado nulo incluído. Sem delete: `revoked_at`, como a §3.1 manda.
_REVOKE_PREVIOUS_SQL = """
    update app.messaging_identity
       set revoked_at = now(),
           revoked_reason = %(reason)s
     where tenant_id = %(tenant_id)s
       and channel = %(channel)s
       and revoked_at is null
       and contact_id is not distinct from %(contact_id)s
       and employee_id is not distinct from %(employee_id)s
    returning id
"""

_INSERT_IDENTITY_SQL = """
    insert into app.messaging_identity
      (tenant_id, channel, contact_id, employee_id, external_id)
    values
      (%(tenant_id)s, %(channel)s, %(contact_id)s, %(employee_id)s, %(external_id)s)
    returning id
"""

#: `user_id` nulo: não há pessoa autenticada — quem agiu foi o titular, pelo
#: bot. ⛔ `depois` leva canal e convite; o `chat_id` não.
_AUDIT_SQL = """
    insert into app.audit_log
      (tenant_id, user_id, action, entity, entity_id, antes, depois)
    values
      (%(tenant_id)s, null, 'insert', 'messaging_identity', %(entity_id)s, null, %(depois)s)
"""

#: O índice parcial da migration `ch_messaging_identity` que diz "este chat_id
#: vigente já é de outra pessoa deste tenant".
_EXTERNAL_ID_INDEX = "messaging_identity_vigente_external_uk"


class _RefusedError(Exception):
    """Uma recusa do passo 6. Sai da transação para que o pool a desfaça."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _empty(status_code: int, headers: dict[str, str] | None = None) -> Response:
    """A resposta desta rota: um status e nada mais."""
    return Response(status_code=status_code, headers=headers)


def _too_many(wait: int) -> Response:
    return _empty(status.HTTP_429_TOO_MANY_REQUESTS, {"Retry-After": str(wait)})


def _classify(update: Any) -> tuple[str, int] | str:
    """`(token, chat_id)` de um `/start <token>` em chat privado, ou o tipo do
    update ignorado — uma palavra deste módulo, nunca um pedaço do corpo."""
    if not isinstance(update, dict):
        return "nao_e_objeto"
    message = update.get("message")
    if not isinstance(message, dict):
        return "sem_mensagem"
    chat = message.get("chat")
    if not isinstance(chat, dict):
        return "sem_chat"
    if chat.get("type") != "private":
        return "chat_nao_privado"
    chat_id = chat.get("id")
    if not isinstance(chat_id, int) or isinstance(chat_id, bool):
        return "chat_id_invalido"
    text = message.get("text")
    if not isinstance(text, str):
        return "sem_texto"
    if not text.startswith("/start"):
        return "texto_livre"
    match = _START.fullmatch(text)
    if match is None:
        return "start_sem_token"
    return match.group("token"), chat_id


async def _bind(context: SystemContext, token: str, chat_id: int) -> UUID:
    """O passo 6, numa transação. Devolve o id da identidade, ou levanta `_RefusedError`."""
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    async with tenant_scope(context) as bound:
        await bound.execute(_INVITE_SQL, {"channel": CHANNEL, "token_hash": token_hash})
        invite = await bound.fetchone()
        if invite is None:
            raise _RefusedError("invite_unknown")
        if invite["used_at"] is not None:
            raise _RefusedError("invite_used")
        if invite["expired"]:
            raise _RefusedError("invite_expired")

        await bound.execute(_CONSUME_INVITE_SQL, {"invite_id": invite["id"]})
        if await bound.fetchone() is None:
            raise RuntimeError("o convite travado com for update não foi consumido")

        holder = {"contact_id": invite["contact_id"], "employee_id": invite["employee_id"]}
        await bound.execute(
            _REVOKE_PREVIOUS_SQL, {"channel": CHANNEL, "reason": _REVOKED_REASON, **holder}
        )
        await bound.fetchall()

        try:
            await bound.execute(
                _INSERT_IDENTITY_SQL,
                {"channel": CHANNEL, "external_id": str(chat_id), **holder},
            )
        except errors.UniqueViolation as violation:
            if violation.diag.constraint_name == _EXTERNAL_ID_INDEX:
                # `from None`: a mensagem do Postgres traz a chave duplicada,
                # e a chave é o chat_id.
                raise _RefusedError("chat_in_use") from None
            raise
        identity = await bound.fetchone()
        if identity is None:
            raise RuntimeError("o insert de app.messaging_identity não devolveu a linha")

        await bound.execute(
            _AUDIT_SQL,
            {
                "entity_id": str(identity["id"]),
                "depois": Jsonb({"channel": CHANNEL, "invite_id": str(invite["id"])}),
            },
        )
    return identity["id"]


@router.post(f"{telegram.WEBHOOK_PATH}/{{path_token}}")
async def telegram_update(path_token: str, request: Request) -> Response:
    """Um update do Telegram. Só `/start <token>` vincula; tudo o mais é 200 vazio."""
    global unknown_path_tokens

    # 1. Por IP.
    client_host = request.client.host if request.client is not None else ""
    wait = _ip_limiter.retry_after(client_host)
    if wait is not None:
        return _too_many(wait)

    # 2. A integração pelo caminho. Fora de forma nem chega ao banco.
    resolved = (
        await context_for_webhook(provider=telegram.NAME, path_token=path_token, task=TASK)
        if _PATH_TOKEN.fullmatch(path_token)
        else None
    )
    if resolved is None:
        unknown_path_tokens += 1
        return _empty(status.HTTP_404_NOT_FOUND)
    context, integration_id = resolved

    # 3. Por token.
    wait = _token_limiter.retry_after(path_token)
    if wait is not None:
        return _too_many(wait)

    # 4. O header, em tempo constante, com o corpo ainda no socket.
    async with tenant_scope(context) as bound:
        secret = await read_secret(bound, integration_id, WEBHOOK_SECRET_KEY)
    presented = request.headers.get(SECRET_HEADER, "")
    if secret is None or not hmac.compare_digest(presented.encode("utf-8"), secret.encode("utf-8")):
        return _empty(status.HTTP_404_NOT_FOUND)

    # 5. Só agora o corpo.
    try:
        update = json.loads(await request.body())
    except (ValueError, RecursionError):
        # `RecursionError` é JSON aninhado até o limite do interpretador — dado
        # hostil por definição, e tratado como o resto: 200 vazio, sem eco.
        logger.warning("telegram webhook: corpo inválido")
        return _empty(status.HTTP_200_OK)
    classified = _classify(update)
    if isinstance(classified, str):
        logger.info("telegram webhook: update ignorado (%s)", classified)
        return _empty(status.HTTP_200_OK)
    token, chat_id = classified

    # 6. O vínculo.
    try:
        await _bind(context, token, chat_id)
    except _RefusedError as refused:
        logger.info(
            "telegram webhook: /start recusado para o tenant %s (%s)",
            context.tenant_id,
            refused.code,
        )
        return _empty(status.HTTP_200_OK)
    logger.info("telegram webhook: identidade vinculada para o tenant %s", context.tenant_id)
    return _empty(status.HTTP_200_OK)
