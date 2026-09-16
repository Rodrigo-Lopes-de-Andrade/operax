"""O convite de adesão ao Telegram e o vínculo na ficha (SPEC-CANAIS §3.3, C4).

O link `https://t.me/<bot>?start=<token>` É a credencial: quem o abre vira o
destinatário dos alertas individuais daquela pessoa. Esta suíte prende o que a
rota faz com ele — e, mais que isso, o que ela NÃO faz com ele. Sete portões:

1. **a ordem** — admin → titular visível (como o usuário) → número → bot,
   WhatsApp e template → as quatro escritas → a resposta. Uma linha do tempo
   dos dois escopos e a lista de instruções provam que **nada é escrito antes
   das quatro condições**;
2. **cada recusa tem código e fecha a transação** — 403 sem admin e 404 sem
   visibilidade **antes de qualquer `tenant_scope`**; os seis 422 nomeados
   (`not_a_person`, `no_phone`, `invalid_phone`, `no_bot`, `no_whatsapp`,
   `no_invite_template`) saem com zero escrita e com o escopo já fechado; a
   recusa do gatilho da fila sai por exceção (rollback) e vira 422;
3. **grupo não é convidado** — `not_a_person` para `whatsapp_group` e
   `email_list`: é a regra 7 pela porta do `chat_id` (§3.4);
4. **o número** — a tabela de normalização, e o mascarado com DDI, DDD e os
   quatro últimos;
5. **o token** — 43 caracteres de `token_urlsafe(32)`, a forma que o webhook
   aceita, ≤ 64 (o teto do `start` do Telegram); no banco só o `sha256`; no
   `payload.link` da fila, e em **lugar nenhum mais**: não na resposta, não na
   auditoria, não em log — a varredura sob DEBUG passa por todos os cenários;
6. **a fila** — a linha tem canal, provedor, template, destino E.164, chave de
   idempotência e um payload com exatamente `nome` e `link`; os convites em
   aberto do mesmo titular expiram antes do novo entrar;
7. **a ficha** — o `GET` nos quatro estados sem ler `external_id`; `revogar`
   com vigente (revoga, expira, audita, relê) e sem (409, nada muda).

⚠️ O QUE ESTA SUÍTE NÃO PODE PROVAR
Nada aqui toca banco. O gatilho `util.validate_alert_template` de verdade
aceitando a linha e recusando o payload sem `link`, o `expires_at = now()`
expirando o convite anterior sem apagar, `revoked_at` preenchido e a linha
ficando, e `util.can_see_employee` decidindo como o usuário são
`scripts/97_teste_canais.py`, sexta parte, contra o banco real, com o SQL
importado deste módulo.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from psycopg import errors
from pydantic import ValidationError

from operax.alertas import outbox
from operax.core.tenant import SystemContext, bind_tenant
from server.models import InviteRequest
from server.routers import canais, webhooks
from tests.conftest import TENANT_ID
from tests.test_canais_credencial import _all_text
from tests.test_canais_templates import (
    AnsweringScope,
    TimedScopeContext,
    _statements,
    _TriggerRefusal,
)

EMPLOYEE_ID = UUID("77777777-7777-4777-8777-777777777781")
CONTACT_ID = UUID("77777777-7777-4777-8777-777777777782")
INVITE_ID = UUID("55555555-5555-4555-8555-555555555561")
PREVIOUS_INVITE_ID = UUID("55555555-5555-4555-8555-555555555560")
QUEUE_ID = UUID("55555555-5555-4555-8555-555555555571")
IDENTITY_ID = UUID("66666666-6666-4666-8666-666666666671")
INTEGRATION_ID = UUID("33333333-3333-4333-8333-333333333335")

BOT_USERNAME = "@FastParkAlertasBot"
#: O número como está no cadastro, o E.164 que vai à fila e o que a tela vê.
PHONE = "+55 (11) 99999-0000"
E164 = "+5511999990000"
MASKED = "+55 11 •••••-0000"
#: As sondas: o que não pode aparecer em resposta, auditoria nem log.
PROBE_NAME = "Sonda Silva"
CHAT_ID = "987654321012"

EXPIRES_AT = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
OPTED_IN_AT = datetime(2026, 9, 10, 9, 30, tzinfo=UTC)
REVOKED_AT = datetime(2026, 9, 12, 18, 0, tzinfo=UTC)

TRIGGER_PHRASE = "Template telegram_invite está draft e o provedor é meta_cloud."


def bot_row(**overrides: Any) -> dict[str, Any]:
    return {
        "id": INTEGRATION_ID,
        "public_identity": BOT_USERNAME,
        "webhook_url": "https://api.exemplo.test/webhooks/telegram/cauda",
        "webhook_path_token": "cauda",
        "health_checked_at": None,
        "health_detail": None,
    } | overrides


def link_row(**overrides: Any) -> dict[str, Any]:
    """Uma linha de `_LINK_SQL`. `external_id` NÃO é coluna dessa consulta: a
    sonda está aqui para provar que, mesmo se o banco a devolvesse, a resposta
    não a carregaria."""
    return {
        "opted_in_at": None,
        "last_revoked_at": None,
        "invite_open_until": None,
        "external_id": CHAT_ID,
    } | overrides


@dataclass
class Stubs:
    user: AnsweringScope
    bound: AnsweringScope
    bound_ctx: TimedScopeContext
    timeline: list[str]


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Stubs]:
    def install(
        *,
        admin: bool = True,
        employee: dict[str, Any] | None | str = "default",
        contact: dict[str, Any] | None | str = "default",
        phone: str | None = PHONE,
        pii_row: bool = True,
        bot: dict[str, Any] | None | str = "default",
        provider: str | None = "z_api",
        template: dict[str, Any] | None | str = "default",
        previous_open: list[dict[str, Any]] | None = None,
        enqueue: Any = "default",
        link: dict[str, Any] | None = None,
        revoked: list[dict[str, Any]] | None = None,
    ) -> Stubs:
        if employee == "default":
            employee = {"id": EMPLOYEE_ID, "name": PROBE_NAME}
        if contact == "default":
            contact = {"id": CONTACT_ID, "name": "Gestora Sonda", "type": "person"}
        if bot == "default":
            bot = bot_row()
        if template == "default":
            template = {"code": "telegram_invite", "variables": ["nome", "link"]}
        if enqueue == "default":
            enqueue = {"id": QUEUE_ID}
        timeline: list[str] = []
        user = AnsweringScope(
            {
                "util.is_admin": {"admin": admin},
                "util.can_see_employee": employee,
                "select c.id, c.name, c.type": contact,
            }
        )
        bound = AnsweringScope(
            {
                "from app.employee_pii": {"phone": phone} if pii_row else None,
                "select c.whatsapp as phone": {"phone": phone},
                "h.checked_at as health_checked_at": bot,
                "select provider from app.integration": {"provider": provider}
                if provider
                else None,
                "select code, variables": template,
                "set expires_at = now()": previous_open or [],
                "insert into app.messaging_invite": {"id": INVITE_ID, "expires_at": EXPIRES_AT},
                "insert into app.alert_queue": enqueue,
                "insert into app.audit_log": None,
                "as invite_open_until": link if link is not None else link_row(),
                "update app.messaging_identity": revoked or [],
            }
        )
        bound_ctx = TimedScopeContext(bound, timeline, "tenant_scope")
        monkeypatch.setattr(
            canais, "user_scope", lambda _t: TimedScopeContext(user, timeline, "user_scope")
        )
        monkeypatch.setattr(canais, "tenant_scope", lambda _t: bound_ctx)
        return Stubs(user=user, bound=bound, bound_ctx=bound_ctx, timeline=timeline)

    return install


@pytest.fixture
def cabecalho(issue_token: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token()}"}


def _invite(client: TestClient, cabecalho: dict[str, str], body: Any = None) -> Any:
    if body is None:
        body = {"employee_id": str(EMPLOYEE_ID)}
    return client.post("/canais/telegram/convites", json=body, headers=cabecalho)


def _get_link(client: TestClient, cabecalho: dict[str, str], employee_id: UUID = EMPLOYEE_ID):
    return client.get(f"/canais/telegram/vinculos/{employee_id}", headers=cabecalho)


def _revoke(client: TestClient, cabecalho: dict[str, str], employee_id: UUID = EMPLOYEE_ID):
    return client.post(f"/canais/telegram/vinculos/{employee_id}/revogar", headers=cabecalho)


WRITE_MARKERS = (
    "update app.messaging",
    "insert into app.messaging",
    "insert into app.alert_queue",
    "insert into app.audit_log",
)
READ_MARKERS = (
    "from app.employee_pii",
    "select c.whatsapp as phone",
    "h.checked_at as health_checked_at",
    "select provider from app.integration",
    "select code, variables",
)


def _writes(scope: AnsweringScope) -> list[str]:
    return [s for s in scope.statements if any(m in s for m in WRITE_MARKERS)]


def _sequence(statements: list[str], markers: tuple[str, ...]) -> list[str]:
    """Os marcadores na ordem em que apareceram — um por instrução."""
    return [m for s in statements for m in markers if m in s]


def _queued(stubs: Stubs) -> dict[str, Any]:
    [(_, params)] = _statements(stubs.bound, "insert into app.alert_queue")
    return params


def _link_of(stubs: Stubs) -> str:
    return _queued(stubs)["payload"].obj["link"]


def _token_of(stubs: Stubs) -> str:
    return _link_of(stubs).rsplit("?start=", 1)[1]


def _app_log(caplog: pytest.LogCaptureFixture) -> str:
    # Todos os registros, `httpx`/`httpcore` incluídos: é por esse logger que,
    # no C5, a URL do provedor com o número vai passar.
    return "\n".join(r.getMessage() for r in caplog.records)


VALID_TIMELINE = [
    "user_scope:enter",
    "user_scope:exit",
    "user_scope:enter",
    "user_scope:exit",
    "tenant_scope:enter",
    "tenant_scope:exit",
]
BOUND_ORDER = (
    "from app.employee_pii",
    "h.checked_at as health_checked_at",
    "select provider from app.integration",
    "select code, variables",
    "set expires_at = now()",
    "insert into app.messaging_invite",
    "insert into app.alert_queue",
    "insert into app.audit_log",
)


# ---------------------------------------------------------------------------
# Gate 1 — a ordem, e nada escrito antes das quatro condições
# ---------------------------------------------------------------------------
def test_os_seis_passos_na_ordem_e_nada_escrito_antes_das_quatro_condicoes(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """Admin e visibilidade como o usuário, cada um no seu `user_scope`; depois
    UM `tenant_scope` com as quatro leituras (número, bot, WhatsApp, template)
    e só então as quatro escritas. ⛔ Mutação: mover o insert do convite para
    antes do template, ou o número para o `user_scope`, muda uma das listas."""
    stubs = db()

    resposta = _invite(client, cabecalho)

    assert resposta.status_code == 200, resposta.text
    assert stubs.timeline == VALID_TIMELINE
    assert _sequence(stubs.user.statements, ("util.is_admin", "util.can_see_employee")) == [
        "util.is_admin",
        "util.can_see_employee",
    ]
    assert _sequence(stubs.bound.statements, BOUND_ORDER) == list(BOUND_ORDER)
    reads = [i for i, s in enumerate(stubs.bound.statements) if any(m in s for m in READ_MARKERS)]
    writes = [i for i, s in enumerate(stubs.bound.statements) if any(m in s for m in WRITE_MARKERS)]
    assert len(reads) == 4 and len(writes) == 4
    assert max(reads) < min(writes)
    assert stubs.bound_ctx.opened == 1
    assert stubs.bound_ctx.exited_with is None  # commit


def test_sem_admin_e_403_com_a_frase_do_convite_sem_olhar_o_titular_nem_abrir_transacao(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(admin=False)

    resposta = _invite(client, cabecalho)

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Convidar para o Telegram é do administrador do cliente."
    assert stubs.bound_ctx.opened == 0
    assert not any("can_see_employee" in s for s in stubs.user.statements)
    assert stubs.timeline == ["user_scope:enter", "user_scope:exit"]


def test_colaborador_invisivel_e_404_antes_de_qualquer_tenant_scope(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """`util.can_see_employee` respondeu não (ou o id não é do tenant): 404, e
    o número não foi nem lido — o `tenant_scope` nunca abriu."""
    stubs = db(employee=None)

    resposta = _invite(client, cabecalho)

    assert resposta.status_code == 404
    assert stubs.bound_ctx.opened == 0
    assert stubs.timeline == VALID_TIMELINE[:4]
    assert _writes(stubs.bound) == []
    [(sql, params)] = _statements(stubs.user, "util.can_see_employee")
    assert params == {"tenant_id": str(TENANT_ID), "employee_id": str(EMPLOYEE_ID)}
    assert "e.tenant_id = %(tenant_id)s" in sql


# ---------------------------------------------------------------------------
# Gate 3 — grupo não é convidado (regra 7 pela porta do chat_id)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tipo", ["whatsapp_group", "email_list"])
def test_grupo_e_lista_sao_not_a_person_sem_abrir_transacao(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], tipo: str
) -> None:
    """Um convite para grupo viraria um `chat_id` de grupo, e o alerta
    individual da pessoa iria para o grupo inteiro — pela porta que
    `util.validate_alert_target` não vigia."""
    stubs = db(contact={"id": CONTACT_ID, "name": "Grupo Unidade", "type": tipo})

    resposta = _invite(client, cabecalho, {"contact_id": str(CONTACT_ID)})

    assert resposta.status_code == 422
    assert resposta.json()["code"] == "not_a_person"
    assert "grupo" in resposta.json()["detail"]
    assert stubs.bound_ctx.opened == 0
    assert _writes(stubs.bound) == []


def test_responsavel_inexistente_ou_inativo_e_404(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(contact=None)
    resposta = _invite(client, cabecalho, {"contact_id": str(CONTACT_ID)})
    assert resposta.status_code == 404
    assert stubs.bound_ctx.opened == 0
    [(sql, params)] = _statements(stubs.user, "select c.id, c.name, c.type")
    assert params == {"tenant_id": str(TENANT_ID), "contact_id": str(CONTACT_ID)}
    assert "c.active" in sql and "c.tenant_id = %(tenant_id)s" in sql


def test_responsavel_pessoa_e_convidado_pelo_contact_id_e_pelo_whatsapp_dele(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(phone="11988887777")

    resposta = _invite(client, cabecalho, {"contact_id": str(CONTACT_ID)})

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["destination_masked"] == "+55 11 •••••-7777"
    [(sql, params)] = _statements(stubs.bound, "select c.whatsapp as phone")
    assert params == {"contact_id": str(CONTACT_ID)}
    assert not any("employee_pii" in s for s in stubs.bound.statements)
    [(_, invite)] = _statements(stubs.bound, "insert into app.messaging_invite")
    assert invite["contact_id"] == str(CONTACT_ID) and invite["employee_id"] is None
    [(_, expire)] = _statements(stubs.bound, "set expires_at = now()")
    assert expire["contact_id"] == str(CONTACT_ID) and expire["employee_id"] is None
    assert _queued(stubs)["destination"] == "+5511988887777"
    assert _queued(stubs)["payload"].obj["nome"] == "Gestora"
    [(_, audit)] = _statements(stubs.bound, "insert into app.audit_log")
    assert audit["depois"].obj == {"titular": "contact", "invite_id": str(INVITE_ID)}


# ---------------------------------------------------------------------------
# Gate 2 — cada 422 com código, zero escrita, e o escopo já fechado
# ---------------------------------------------------------------------------
TELEGRAM_START_MAX_CHARS = 64

REFUSALS: list[tuple[str, dict[str, Any]]] = [
    ("no_phone", {"pii_row": False}),
    ("no_phone", {"phone": None}),
    ("no_phone", {"phone": ""}),
    ("no_phone", {"phone": "   "}),
    ("no_phone", {"phone": "sem telefone"}),
    ("invalid_phone", {"phone": "123"}),
    ("invalid_phone", {"phone": "999990000"}),
    ("invalid_phone", {"phone": "441234567890"}),
    ("invalid_phone", {"phone": "12345678901234567"}),
    ("no_bot", {"bot": None}),
    ("no_bot", {"bot": bot_row(public_identity=None)}),
    ("no_bot", {"bot": bot_row(public_identity="@")}),
    ("no_whatsapp", {"provider": None}),
    ("no_invite_template", {"template": None}),
    ("no_invite_template", {"template": {"code": "telegram_invite", "variables": ["nome"]}}),
    (
        "no_invite_template",
        {"template": {"code": "telegram_invite", "variables": ["nome", "link", "unidade"]}},
    ),
    (
        "no_invite_template",
        {"template": {"code": "telegram_invite", "variables": ["name", "link"]}},
    ),
]


@pytest.mark.parametrize(("code", "kwargs"), REFUSALS)
def test_cada_422_tem_codigo_nao_escreve_nada_e_fecha_a_transacao(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Callable[..., Stubs],
    code: str,
    kwargs: dict[str, Any],
) -> None:
    """A recusa sai de dentro do `tenant_scope` — que fecha (commit de nada)
    antes da resposta. ⛔ `no_invite_template` também para o template que não
    pede `link`: o gatilho da fila não pegaria esse, e um convite sem link
    não convida ninguém."""
    stubs = db(**kwargs)

    resposta = _invite(client, cabecalho)

    assert resposta.status_code == 422, resposta.text
    assert resposta.json()["code"] == code
    assert canais._INVITE_REFUSALS[code] == resposta.json()["detail"]
    assert _writes(stubs.bound) == []
    assert stubs.bound_ctx.opened == 1
    assert stubs.bound_ctx.exited_with is None
    assert stubs.timeline[-1] == "tenant_scope:exit"


def test_as_frases_dos_seis_codigos_sao_as_do_despacho() -> None:
    frases = canais._INVITE_REFUSALS
    assert frases["invalid_phone"] == "O número em cadastro não é um WhatsApp válido."
    assert frases["no_bot"] == "Conecte o bot do Telegram antes de convidar."
    assert frases["no_whatsapp"] == (
        "O convite viaja por WhatsApp, e este cliente não tem WhatsApp ativo."
    )
    assert frases["no_invite_template"] == (
        "O template `telegram_invite` precisa existir em Templates e declarar "
        "exatamente as variáveis `nome` e `link`."
    )
    assert set(frases) == {
        "not_a_person",
        "no_phone",
        "invalid_phone",
        "no_bot",
        "no_whatsapp",
        "no_invite_template",
        "not_linked",
    }


def test_a_recusa_do_gatilho_da_fila_sai_por_excecao_e_vira_422_com_a_frase_dele(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """`util.validate_alert_template` é o último juiz (template não aprovado no
    provedor oficial, variável a mais). O convite já inserido e a expiração
    dos anteriores têm de voltar: a saída é por exceção, que é o rollback do
    pool — e a auditoria nunca roda."""
    stubs = db(enqueue=_TriggerRefusal(TRIGGER_PHRASE))

    resposta = _invite(client, cabecalho)

    assert resposta.status_code == 422
    assert resposta.json() == {"detail": TRIGGER_PHRASE, "code": "invite_refused"}
    assert stubs.bound_ctx.exited_with is canais._QueueRefusedError
    assert _statements(stubs.bound, "insert into app.audit_log") == []
    assert len(_statements(stubs.bound, "insert into app.messaging_invite")) == 1


class _RefusalWithDetail(errors.RaiseException):
    """O `P0001` como o psycopg o entrega: `diag.message_primary` é a frase do
    `raise exception`; a mensagem da exceção (o que `str()` e um traceback
    mostram) traz o `DETAIL` — que, numa recusa de gatilho `before insert`,
    pode carregar a linha, e a linha tem o link."""

    def __init__(self, primary: str, detail: str) -> None:
        super().__init__(f"{primary}\nDETAIL:  {detail}")
        self._primary = primary

    @property
    def diag(self) -> Any:
        return SimpleNamespace(message_primary=self._primary)


async def test_a_recusa_do_gatilho_nasce_from_none_e_a_cadeia_nao_carrega_o_payload() -> None:
    """⛔ Mutação: tirar o `from None` deixa isto vermelho. Quem formatar a
    exceção com a cadeia (`exc_info=True`, Sentry) veria a mensagem do
    Postgres — e o `DETAIL` dela é a linha recusada, link incluído."""
    import traceback

    detalhe = "Failing row contains (..., https://t.me/x?start=segredo-de-sonda, ...)"
    bound = AnsweringScope(
        {"insert into app.alert_queue": _RefusalWithDetail(TRIGGER_PHRASE, detalhe)}
    )

    with pytest.raises(canais._QueueRefusedError) as erro:
        await canais._enqueue_invite(
            bound,  # type: ignore[arg-type]
            invite_id=INVITE_ID,
            destination=E164,
            provider="meta_cloud",
            payload={"nome": "Sonda", "link": "https://t.me/x?start=segredo-de-sonda"},
        )

    assert str(erro.value) == TRIGGER_PHRASE
    assert erro.value.__suppress_context__ is True
    assert erro.value.__cause__ is None
    formatado = "".join(traceback.format_exception(erro.value))
    assert "segredo-de-sonda" not in formatado
    assert "DETAIL" not in formatado


# ---------------------------------------------------------------------------
# Gate 4 — o número
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "e164"),
    [
        ("11999990000", "+5511999990000"),
        ("+55 (11) 99999-0000", "+5511999990000"),
        ("5511999990000", "+5511999990000"),
        ("55 11 99999-0000", "+5511999990000"),
        ("(11) 3333-4444", "+551133334444"),
        ("+5511999990000", "+5511999990000"),
        ("5599990000", "+555599990000"),  # DDD 55 com oito dígitos: dez, logo `+55` na frente
        ("123", None),
        ("999990000", None),  # nove: um celular sem DDD não tem para onde ir
        ("99990000", None),  # oito: idem
        ("", None),
        (None, None),
        ("441234567890", None),  # doze dígitos sem o 55 na frente não é Brasil
        ("5511999990000123", None),  # dezesseis: além do E.164
    ],
)
def test_a_normalizacao_do_numero(raw: str | None, e164: str | None) -> None:
    assert canais._e164(raw) == e164


@pytest.mark.parametrize(
    "raw", ["11999990000", "+55 (11) 99999-0000", "5511999990000", "+5511999990000"]
)
def test_o_numero_vai_a_fila_em_e164_e_a_resposta_so_o_mostra_mascarado(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], raw: str
) -> None:
    stubs = db(phone=raw)

    resposta = _invite(client, cabecalho)

    assert resposta.status_code == 200
    assert _queued(stubs)["destination"] == E164
    assert resposta.json()["destination_masked"] == MASKED
    assert "99999" not in resposta.text
    assert E164 not in resposta.text and E164.lstrip("+") not in resposta.text


def test_a_mascara_e_ddi_ddd_e_os_quatro_ultimos() -> None:
    assert canais._mask("+5511999990000") == "+55 11 •••••-0000"
    assert canais._mask("+552133334444") == "+55 21 •••••-4444"
    assert "9999" not in canais._mask("+5511999990000")


# ---------------------------------------------------------------------------
# Gate 5 — o token: forma, hash, e em lugar nenhum mais
# ---------------------------------------------------------------------------
def test_o_link_tem_a_forma_do_deep_link_e_o_token_cabe_no_start_do_telegram(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db()
    assert _invite(client, cabecalho).status_code == 200
    link = _link_of(stubs)
    match = re.fullmatch(r"https://t\.me/FastParkAlertasBot\?start=([A-Za-z0-9_\-]{43})", link)
    assert match is not None, link
    token = match.group(1)
    # O teto do Telegram para o parâmetro `start`; `token_urlsafe(32)` dá 43.
    assert len(token) == 43 <= TELEGRAM_START_MAX_CHARS
    # O par: é exatamente o que o webhook aceita num `/start`.
    assert webhooks._START.fullmatch(f"/start {token}")
    assert "@" not in link  # o `@` do `public_identity` não entra na URL


def test_cada_convite_tem_um_token_novo(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    tokens = set()
    for _ in range(3):
        stubs = db()
        assert _invite(client, cabecalho).status_code == 200
        tokens.add(_token_of(stubs))
    assert len(tokens) == 3


def test_o_banco_recebe_o_sha256_do_token_e_o_token_so_esta_no_payload_da_fila(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """Regra 3 da §3.3: `token_hash`, nunca o token. O token existe em UMA
    instrução — o `payload.link` da fila, que é por onde ele viaja — e em
    nenhuma outra, nem no texto, nem nos parâmetros."""
    stubs = db()
    assert _invite(client, cabecalho).status_code == 200
    token = _token_of(stubs)

    [(_, invite)] = _statements(stubs.bound, "insert into app.messaging_invite")
    assert invite["token_hash"] == hashlib.sha256(token.encode("ascii")).hexdigest()
    assert invite["channel"] == "telegram"
    assert invite["employee_id"] == str(EMPLOYEE_ID) and invite["contact_id"] is None

    for statement, params in zip(stubs.bound.statements, stubs.bound.params, strict=True):
        assert token not in statement
        if "insert into app.alert_queue" not in statement:
            assert token not in _all_text(params), statement
    for statement, params in zip(stubs.user.statements, stubs.user.params, strict=True):
        assert token not in statement and token not in _all_text(params)


def test_a_resposta_nao_tem_o_token_nem_o_link_nem_o_numero(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db()

    resposta = _invite(client, cabecalho)

    assert resposta.status_code == 200
    token = _token_of(stubs)
    assert token in _link_of(stubs)  # o positivo: a sonda existe
    assert token not in resposta.text
    assert "t.me" not in resposta.text
    assert "start=" not in resposta.text
    assert E164 not in resposta.text and "99999" not in resposta.text
    assert PROBE_NAME not in resposta.text
    assert set(resposta.json()) == {"invite_id", "expires_at", "queued", "destination_masked"}
    assert resposta.json()["invite_id"] == str(INVITE_ID)
    assert resposta.json()["queued"] is True
    assert resposta.json()["destination_masked"] == MASKED


def test_a_auditoria_leva_o_titular_e_o_convite_e_nao_leva_token_link_nem_numero(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db()
    assert _invite(client, cabecalho).status_code == 200
    token = _token_of(stubs)

    [(sql, audit)] = _statements(stubs.bound, "insert into app.audit_log")
    assert audit["action"] == "insert" and audit["entity"] == "messaging_invite"
    assert audit["entity_id"] == str(INVITE_ID)
    assert audit["depois"].obj == {"titular": "employee", "invite_id": str(INVITE_ID)}
    assert "null, %(depois)s" in sql  # `antes` é nulo: não havia convite
    texto = _all_text(audit)
    assert token not in texto
    assert "t.me" not in texto
    assert E164 not in texto and "99999" not in texto
    assert PROBE_NAME not in texto
    assert CHAT_ID not in texto


def test_varredura_sob_debug_token_link_numero_e_chat_id_em_lugar_nenhum_do_log(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Callable[..., Stubs],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Todos os cenários, um atrás do outro, com o logger raiz em DEBUG."""
    cenarios: list[tuple[dict[str, Any], Any]] = [
        ({}, None),
        ({}, {"contact_id": str(CONTACT_ID)}),
        ({"admin": False}, None),
        ({"employee": None}, None),
        (
            {"contact": {"id": CONTACT_ID, "name": "G", "type": "whatsapp_group"}},
            {"contact_id": str(CONTACT_ID)},
        ),
        ({"phone": "123"}, None),
        ({"bot": None}, None),
        ({"provider": None}, None),
        ({"template": None}, None),
        ({"enqueue": _TriggerRefusal(TRIGGER_PHRASE)}, None),
        ({"link": link_row(opted_in_at=OPTED_IN_AT)}, "get"),
        ({"revoked": [{"id": IDENTITY_ID}]}, "revogar"),
        ({"revoked": []}, "revogar"),
    ]
    tokens: list[str] = []
    with caplog.at_level(logging.DEBUG):
        for kwargs, body in cenarios:
            stubs = db(**kwargs)
            if body == "get":
                resposta = _get_link(client, cabecalho)
            elif body == "revogar":
                resposta = _revoke(client, cabecalho)
            else:
                resposta = _invite(client, cabecalho, body)
            queued = _statements(stubs.bound, "insert into app.alert_queue")
            if queued and resposta.status_code == 200:
                tokens.append(_token_of(stubs))
            assert CHAT_ID not in resposta.text
            assert "t.me" not in resposta.text
    assert len(tokens) == 2  # o positivo: dois convites saíram com token
    log = _app_log(caplog)
    for token in tokens:
        assert token not in log
    assert "t.me" not in log and "start=" not in log
    assert E164 not in log and "99999" not in log and "8888" not in log
    assert CHAT_ID not in log
    assert PROBE_NAME not in log
    assert f"convite de Telegram enfileirado para o tenant {TENANT_ID} (employee)" in log


# ---------------------------------------------------------------------------
# Gate 6 — a fila, e os convites anteriores
# ---------------------------------------------------------------------------
def test_a_linha_da_fila_e_um_convite_sem_regra_sob_o_contrato_de_template(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """A instrução é a de `outbox` — importada, não copiada —, com `rule_id` e
    `report_cycle_id` nulos: o convite não é alerta de desvio. O payload tem
    exatamente `nome` e `link`, que é o que o template `telegram_invite`
    declara e o que o gatilho confere."""
    stubs = db(provider="meta_cloud")
    assert _invite(client, cabecalho).status_code == 200

    [(sql, params)] = _statements(stubs.bound, "insert into app.alert_queue")
    assert sql == outbox._ENQUEUE_SQL
    assert params["channel"] == "whatsapp"
    assert params["provider"] == "meta_cloud"
    assert params["template_code"] == "telegram_invite"
    assert params["destination"] == E164
    assert params["idempotency_key"] == f"telegram_invite:{INVITE_ID}"
    assert params["rule_id"] is None and params["cycle_id"] is None
    assert set(params["payload"].obj) == {"nome", "link"}
    assert params["payload"].obj["nome"] == "Sonda"  # o primeiro nome, não o inteiro
    assert params["payload"].obj["link"].startswith("https://t.me/FastParkAlertasBot?start=")
    assert "tenant_id" not in params  # ligado pelo `tenant_scope`, nunca pelo chamador


def test_o_provedor_e_o_template_sao_os_do_outbox_lidos_do_tenant(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db()
    assert _invite(client, cabecalho).status_code == 200
    [(provider_sql, provider_params)] = _statements(
        stubs.bound, "select provider from app.integration"
    )
    assert provider_sql == outbox._PROVIDER_SQL and provider_params == {}
    [(template_sql, template_params)] = _statements(stubs.bound, "select code, variables")
    assert template_sql == outbox._TEMPLATE_SQL and template_params == {"code": "telegram_invite"}


def test_os_convites_em_aberto_do_mesmo_titular_expiram_antes_do_novo_entrar(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """Regra 2 da §3.3: dois links válidos circulando são dois vetores. Só os
    em aberto (`used_at is null and expires_at > now()`) e só deste titular;
    sem delete — a linha fica, com `expires_at = now()`."""
    stubs = db(previous_open=[{"id": PREVIOUS_INVITE_ID}])

    assert _invite(client, cabecalho).status_code == 200

    [(sql, params)] = _statements(stubs.bound, "set expires_at = now()")
    assert params == {"channel": "telegram", "employee_id": str(EMPLOYEE_ID), "contact_id": None}
    assert "used_at is null" in sql and "expires_at > now()" in sql
    assert "contact_id is not distinct from %(contact_id)s" in sql
    assert "employee_id is not distinct from %(employee_id)s" in sql
    assert "delete" not in sql.lower()
    posicoes = [
        next(i for i, s in enumerate(stubs.bound.statements) if m in s)
        for m in ("set expires_at = now()", "insert into app.messaging_invite")
    ]
    assert posicoes[0] < posicoes[1]


def test_a_fila_que_nao_devolve_linha_derruba_a_transacao(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """A chave de idempotência é do convite recém-criado: `on conflict do
    nothing` sem `returning` é impossível — e um convite gravado sem mensagem
    seria um link em lugar nenhum. Falha alto, e o convite volta."""
    stubs = db(enqueue=None)
    with pytest.raises(RuntimeError):
        _invite(client, cabecalho)
    assert stubs.bound_ctx.exited_with is RuntimeError
    assert _statements(stubs.bound, "insert into app.audit_log") == []


# ---------------------------------------------------------------------------
# O corpo: exatamente um titular, e o 422 não ecoa o que veio
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"employee_id": None, "contact_id": None},
        {"employee_id": str(EMPLOYEE_ID), "contact_id": str(CONTACT_ID)},
        {"employee_id": "nao-e-uuid"},
    ],
)
def test_corpo_sem_exatamente_um_titular_e_422_sem_tocar_o_banco(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs], body: Any
) -> None:
    stubs = db()
    resposta = _invite(client, cabecalho, body)
    assert resposta.status_code == 422
    assert stubs.user.statements == [] and stubs.bound_ctx.opened == 0
    assert "input" not in resposta.text


def test_invite_request_exige_exatamente_um_titular() -> None:
    assert InviteRequest(employee_id=EMPLOYEE_ID).contact_id is None
    assert InviteRequest(contact_id=CONTACT_ID).employee_id is None
    with pytest.raises(ValidationError, match="exatamente um titular"):
        InviteRequest()
    with pytest.raises(ValidationError, match="exatamente um titular"):
        InviteRequest(employee_id=EMPLOYEE_ID, contact_id=CONTACT_ID)


# ---------------------------------------------------------------------------
# Gate 7 — a ficha: o GET nos quatro estados, sem o chat_id
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("row", "esperado"),
    [
        (
            link_row(opted_in_at=OPTED_IN_AT, last_revoked_at=REVOKED_AT),
            {
                "linked": True,
                "opted_in_at": OPTED_IN_AT,
                "revoked_at": None,
                "invite_open_until": None,
            },
        ),
        (
            link_row(last_revoked_at=REVOKED_AT),
            {
                "linked": False,
                "opted_in_at": None,
                "revoked_at": REVOKED_AT,
                "invite_open_until": None,
            },
        ),
        (
            link_row(invite_open_until=EXPIRES_AT),
            {
                "linked": False,
                "opted_in_at": None,
                "revoked_at": None,
                "invite_open_until": EXPIRES_AT,
            },
        ),
        (
            link_row(),
            {"linked": False, "opted_in_at": None, "revoked_at": None, "invite_open_until": None},
        ),
    ],
    ids=["vinculado", "revogado", "convite em aberto", "nunca"],
)
def test_get_vinculo_nos_quatro_estados_e_a_revogacao_so_aparece_sem_vigente(
    client: TestClient,
    cabecalho: dict[str, str],
    db: Callable[..., Stubs],
    row: dict[str, Any],
    esperado: dict[str, Any],
) -> None:
    """`revoked_at` é da ÚLTIMA revogação e só quando não há vigente: quem saiu
    e voltou está vinculado, e a ficha diz isso, não "revogado em"."""
    stubs = db(admin=False, link=row)  # qualquer membro que vê o colaborador

    resposta = _get_link(client, cabecalho)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert set(corpo) == {"linked", "opted_in_at", "revoked_at", "invite_open_until"}
    for chave, valor in esperado.items():
        obtido = (
            datetime.fromisoformat(corpo[chave]) if isinstance(valor, datetime) else corpo[chave]
        )
        assert obtido == valor, chave
    assert CHAT_ID not in resposta.text  # a sonda estava na linha; não está na resposta
    assert not any("util.is_admin" in s for s in stubs.user.statements)
    assert stubs.timeline == [
        "user_scope:enter",
        "user_scope:exit",
        "tenant_scope:enter",
        "tenant_scope:exit",
    ]
    [(sql, params)] = _statements(stubs.bound, "as invite_open_until")
    assert params == {"channel": "telegram", "employee_id": str(EMPLOYEE_ID)}
    assert _writes(stubs.bound) == []


def test_get_vinculo_de_colaborador_invisivel_e_404_antes_de_qualquer_tenant_scope(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(employee=None)
    resposta = _get_link(client, cabecalho)
    assert resposta.status_code == 404
    assert stubs.bound_ctx.opened == 0


def test_a_consulta_do_vinculo_nao_seleciona_external_id() -> None:
    """⛔ O `chat_id` nunca sai (§3.2). Não é "não devolvido": a coluna não é
    nem lida. Três subconsultas, cada uma ligada ao tenant e ao titular."""
    sql = canais._LINK_SQL.lower()
    assert "external_id" not in sql
    assert "select *" not in sql and "mi.*" not in sql
    assert sql.count("tenant_id = %(tenant_id)s") == 3
    assert sql.count("employee_id = %(employee_id)s") == 3
    assert "revoked_at is null) as opted_in_at" in sql
    assert "max(mi.revoked_at)" in sql
    assert "used_at is null" in sql and "expires_at > now()" in sql


# ---------------------------------------------------------------------------
# Gate 7 — revogar: com vigente e sem
# ---------------------------------------------------------------------------
def test_revogar_com_vigente_revoga_expira_audita_e_rele_a_ficha(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    """A instrução é a do webhook (`_REVOKE_PREVIOUS_SQL`, importada) com outra
    razão; a linha fica (`revoked_at`, sem delete); os convites em aberto
    expiram junto; a trilha leva a razão; e o que volta é a ficha relida."""
    stubs = db(revoked=[{"id": IDENTITY_ID}], link=link_row(last_revoked_at=REVOKED_AT))

    resposta = _revoke(client, cabecalho)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["linked"] is False
    assert datetime.fromisoformat(resposta.json()["revoked_at"]) == REVOKED_AT
    assert CHAT_ID not in resposta.text

    [(revoke_sql, revoke)] = _statements(stubs.bound, "update app.messaging_identity")
    assert revoke_sql == webhooks._REVOKE_PREVIOUS_SQL
    assert revoke == {
        "channel": "telegram",
        "reason": "desvinculado pelo administrador",
        "employee_id": str(EMPLOYEE_ID),
        "contact_id": None,
    }
    assert "set revoked_at = now()" in revoke_sql and "delete" not in revoke_sql.lower()
    [(_, expire)] = _statements(stubs.bound, "set expires_at = now()")
    assert expire == {"channel": "telegram", "employee_id": str(EMPLOYEE_ID), "contact_id": None}
    [(_, audit)] = _statements(stubs.bound, "insert into app.audit_log")
    assert audit["action"] == "update" and audit["entity"] == "messaging_identity"
    assert audit["entity_id"] == str(IDENTITY_ID)
    assert audit["depois"].obj == {"reason": "desvinculado pelo administrador"}
    assert CHAT_ID not in _all_text(audit)
    assert _sequence(
        stubs.bound.statements,
        (
            "update app.messaging_identity",
            "set expires_at = now()",
            "insert into app.audit_log",
            "as invite_open_until",
        ),
    ) == [
        "update app.messaging_identity",
        "set expires_at = now()",
        "insert into app.audit_log",
        "as invite_open_until",
    ]
    assert stubs.timeline == VALID_TIMELINE
    assert stubs.bound_ctx.exited_with is None


def test_revogar_sem_vigente_e_409_not_linked_e_nada_muda(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(revoked=[])

    resposta = _revoke(client, cabecalho)

    assert resposta.status_code == 409
    assert resposta.json()["code"] == "not_linked"
    assert resposta.json()["detail"] == canais._INVITE_REFUSALS["not_linked"]
    assert len(_statements(stubs.bound, "update app.messaging_identity")) == 1
    assert _statements(stubs.bound, "set expires_at = now()") == []
    assert _statements(stubs.bound, "insert into app.audit_log") == []
    assert stubs.bound_ctx.exited_with is None


def test_revogar_sem_admin_e_403_e_invisivel_e_404_sem_transacao(
    client: TestClient, cabecalho: dict[str, str], db: Callable[..., Stubs]
) -> None:
    stubs = db(admin=False)
    resposta = _revoke(client, cabecalho)
    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Desvincular do Telegram é do administrador do cliente."
    assert stubs.bound_ctx.opened == 0

    stubs = db(employee=None)
    assert _revoke(client, cabecalho).status_code == 404
    assert stubs.bound_ctx.opened == 0


# ---------------------------------------------------------------------------
# As instruções: ligam o tenant, não apagam, e só leem o que o contrato mostra
# ---------------------------------------------------------------------------
ADHESION_SQL = (
    "_EMPLOYEE_PHONE_SQL",
    "_CONTACT_PHONE_SQL",
    "_EXPIRE_OPEN_INVITES_SQL",
    "_INSERT_INVITE_SQL",
    "_ADHESION_AUDIT_SQL",
    "_LINK_SQL",
)


def test_a_visibilidade_do_colaborador_esta_escrita_na_instrucao() -> None:
    # A policy `employee_read` já recorta; o predicado escrito na instrução é
    # o que faz a intenção sobreviver a um stub que não tem policy.
    assert "util.can_see_employee(e.id)" in canais._VISIBLE_EMPLOYEE_SQL


def test_as_instrucoes_do_tenant_scope_ligam_o_tenant_e_nenhuma_apaga() -> None:
    context = SystemContext(tenant_id=TENANT_ID, task="test")
    for name in (*ADHESION_SQL, "_VISIBLE_EMPLOYEE_SQL", "_VISIBLE_CONTACT_SQL"):
        sql = getattr(canais, name)
        assert bind_tenant(sql, {}, context)["tenant_id"] == TENANT_ID, name
        assert "delete" not in sql.lower(), name
    for name in ("_EMPLOYEE_PHONE_SQL", "_CONTACT_PHONE_SQL", "_EXPIRE_OPEN_INVITES_SQL"):
        assert "tenant_id = %(tenant_id)s" in getattr(canais, name), name
    assert "(%(tenant_id)s, %(channel)s" in canais._INSERT_INVITE_SQL
    assert "(%(tenant_id)s, %(user_id)s" in canais._ADHESION_AUDIT_SQL
    # O número: só a coluna do número, nada mais da PII.
    phone = canais._EMPLOYEE_PHONE_SQL.lower()
    assert re.search(r"select\s+p\.phone\s+from app\.employee_pii", phone)
    assert "cpf" not in phone and "*" not in phone
    # O que entra no convite é o hash; `token` sem `_hash` não aparece.
    assert "token_hash" in canais._INSERT_INVITE_SQL
    assert not re.search(r"\btoken\b", canais._INSERT_INVITE_SQL)


def test_o_template_do_convite_e_as_variaveis_sao_as_do_despacho() -> None:
    assert canais._INVITE_TEMPLATE_CODE == "telegram_invite"
    assert canais._INVITE_VARIABLES == {"nome", "link"}
    assert canais._UNLINK_REASON == "desvinculado pelo administrador"
